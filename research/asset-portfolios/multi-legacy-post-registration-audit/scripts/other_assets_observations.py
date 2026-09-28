"""Clearly frozen but unregistered observations, separately labelled."""
from __future__ import annotations
import argparse
import hashlib
import json
import random
from dataclasses import asdict, replace
import numpy as np
import pandas as pd
import audit_common as common
import other_assets_replay as ar

ROOT, END = ar.ROOT, ar.END
OUT = ar.OUT / "unregistered_observations"


def save_result(output, scenario, trades, curve, monthly, summary):
    output.mkdir(parents=True, exist_ok=True)
    trades.to_csv(output / f"{scenario}_trades.csv", index=False)
    curve.to_csv(output / f"{scenario}_equity.csv", index=False)
    monthly.to_csv(output / f"{scenario}_monthly.csv", index=False)
    return {"scenario": scenario, "status": "UNREGISTERED_FROZEN_OBSERVATION_ESTIMATE", **summary}


def run_sol_pb(vcb=False):
    name = "SOL_1H_VCB_R002346" if vcb else "SOL_1H_PB_R01145"
    output = OUT / name
    path = ROOT / ("research/sol/1h-volatility-compression-breakout/scripts/research_sol_1h_vcb_search.py" if vcb else "research/sol/1h-pullback-bracket/scripts/research_sol_1h_pullback_bracket_search.py")
    module = ar.load_module(path, "audit_sol_pb_observation")
    engine = ar.load_module(ar.ENGINE_PATH, "audit_sol_pb_engine")
    assert hashlib.sha256(ar.ENGINE_PATH.read_bytes()).hexdigest() == ar.ENGINE_HASH
    if vcb:
        frozen_path = ROOT / "research/sol/1h-volatility-compression-breakout/artifacts/sol_1h_vcb_search_2026-07-13.json"
        selected = json.loads(frozen_path.read_text())["selected"]
        entry = module.EntryConfig(**{k.removeprefix("entry_"):v for k,v in selected.items() if k.startswith("entry_")})
        exit_cfg = engine.StrategyConfig(**{k.removeprefix("exit_"):v for k,v in selected.items() if k.startswith("exit_")})
    else:
        template = engine.curated_configs()[0]
        rng = random.Random(20260713)
        for i in range(1, 1146):
            entry = module.random_entry(rng)
            exit_cfg = module.random_exit(engine, rng, template, i)
    assert exit_cfg.name == name
    start = pd.Timestamp("2026-07-14T00:00:00Z")
    ar.write_json(output / "frozen_contract.json", {
        "name": name, "family": "SOL-1H-Volatility-Compression-Breakout" if vcb else "SOL-1H-Pullback-Bracket", "registered": False,
        "archive_date": "2026-07-13", "start": start, "end": END,
        "config_recovery": (str(frozen_path.relative_to(ROOT)) if vcb else "Frozen deterministic seed 20260713, config index 1145; no price data or performance used during recovery"),
        "entry": asdict(entry), "exit": asdict(exit_cfg),
        "source": str(path.relative_to(ROOT)), "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "identity_evidence": ("research/sol/1h-volatility-compression-breakout/diagnostics/sol-1h-vcb-search-2026-07-13.md" if vcb else "research/sol/1h-pullback-bracket/diagnostics/sol-1h-pullback-bracket-search-2026-07-13.md"),
    })
    raw = common.load_prices("SOL", "1h")
    funding = common.load_funding("SOL")
    raw = raw[raw.ts >= funding.ts.min().ceil("h")].reset_index(drop=True)
    frame = engine.add_features(raw, funding)
    signal, events = module.build_signal(engine, frame, entry) if vcb else module.build_signal(frame, entry)
    sentinel = frame.iloc[-1:].copy()
    sentinel["ts"] = END
    for col in ("open", "high", "low", "close"):
        sentinel[col] = raw.close.iloc[-1]
    terminal_frame = pd.concat([frame, sentinel], ignore_index=True)
    ft, fc = engine.funding_prefix(funding)
    results = []
    for scenario, slip, delay in [("base", .0004, 1), ("slippage_8bps", .0008, 1), ("delay_plus_one_bar", .0004, 2)]:
        cfg = replace(exit_cfg, entry_delay_bars=delay)
        engine.SLIPPAGE_PER_FILL, engine.FEE_PER_FILL = slip, .001
        active = signal.copy()
        entries = frame.ts + pd.Timedelta(hours=delay)
        active[((frame.ts + pd.Timedelta(hours=1) < start) | (entries < start) | (entries >= END)).to_numpy()] = 0
        trades = engine.simulate_trades(terminal_frame, np.r_[active, 0], cfg, ft, fc)
        for trade in trades:
            if trade.exit_ts == END:
                trade.exit_reason = "audit_terminal_close"
        curve, monthly, summary = ar.curve_and_summary(engine, raw, trades, start, END, funding, .001)
        results.append(save_result(output, scenario, pd.DataFrame([asdict(t) for t in trades]), curve, monthly, {"name": name, "start": start, "end": END, **summary}))
    ar.write_json(output / "results.json", results)
    return results


def run_btc_ema():
    name = "BTC-15M-EMA-TB-V40-transfer-near-miss"
    output = OUT / name
    path = ROOT / "research/btc/15m-ema-trend-breakout/scripts/_btc_15m_v40_common.py"
    helper = ar.load_module(path, "audit_btc_ema_common")
    engine = helper.load_kernel()
    frozen = ROOT / "research/btc/15m-ema-trend-breakout/artifacts/btc_15m_v40_frozen_selection_2026-07-17.json"
    selection = helper.read_verified_payload(frozen, "frozen selection")
    start = pd.Timestamp(selection["created_at_utc"]).ceil("15min")
    frame = common.load_prices("BTC", "15m").set_index("ts")
    frame.index = frame.index.astype("datetime64[ns, UTC]")
    funding = common.load_funding("BTC")
    features = helper.build_feature_base(engine, frame)
    cfg, flags, signals = helper.build_signals_for_selection(engine, features, selection["selection"])
    ar.write_json(output / "frozen_contract.json", {
        "name":name, "family":"BTC-15M-EMA-Trend-Breakout", "registered":False,
        "start":start, "end":END, "source":str(frozen.relative_to(ROOT)), "source_sha256":hashlib.sha256(frozen.read_bytes()).hexdigest(),
        "selection":selection["selection"], "config":asdict(cfg), "kernel_sha256":selection["kernel_sha256"],
        "start_policy":"First 15m grid after exact creation timestamp 2026-07-17T15:29:16.391144Z",
    })
    results = []
    for scenario, slip, fee in [("base",.0004,.001),("slippage_8bps",.0008,.001),("double_fee_slippage",.0008,.002)]:
        changed = replace(cfg, adverse_slippage_per_fill=slip, fee_per_fill=fee)
        metric, run = helper.evaluate_period(engine, name=scenario, frame=frame, funding=funding, signals=signals, config=changed, start=start, end=END)
        curve = run.equity_curve.loc[lambda s:(s.index>=start)&(s.index<END)].rename("equity").rename_axis("ts").reset_index()
        curve["ts"] += pd.Timedelta(minutes=15)
        curve["drawdown"] = curve.equity / np.maximum.accumulate(np.r_[1.,curve.equity])[1:] - 1.
        monthly, prev = [], 1.
        for month, rows in curve.groupby((curve.ts - pd.Timedelta(nanoseconds=1)).dt.strftime("%Y-%m")):
            value = float(rows.equity.iloc[-1]); monthly.append({"month":month,"return":value/prev-1.,"ending_equity":value}); prev=value
        summary = {"name":name,"timeframe":"15m","start":start,"end":END,"return":metric["return_pct"]/100.,"trade_count":metric["trades"],"close_marked_max_drawdown":metric["max_drawdown_pct"]/100.,"win_rate":metric["win_rate"],"fee_per_fill":fee,"slippage_per_fill":slip}
        results.append(save_result(output,scenario,run.trades,curve,pd.DataFrame(monthly),summary))
    ar.write_json(output / "results.json",results)
    return results


def annotate_rs4_trades(trades, end, melt_weight, one_way_cost, terminal_account_cost):
    """Preserve native sleeve diagnostics while exposing the audit-only close fee."""
    trades = trades.copy()
    terminal = pd.to_datetime(trades.exit_ts, utc=True).eq(end)
    trades["audit_terminal_exit"] = terminal
    trades["exit_reason"] = np.where(terminal, "audit_terminal_close", "original_position_change")
    trades["sleeve_weight_in_account"] = np.where(trades.strategy.eq("melt"), melt_weight, 1.)
    trades["net_return_semantics"] = "original_sleeve_diagnostic_before_extra_audit_terminal_cost"
    trades["terminal_liquidation_cost_1x"] = np.where(terminal, one_way_cost, 0.)
    trades["terminal_liquidation_cost_account_return_fraction"] = trades.terminal_liquidation_cost_1x * trades.sleeve_weight_in_account
    trades["terminal_cost_already_in_account_equity"] = terminal
    assert np.isclose(trades.terminal_liquidation_cost_account_return_fraction.sum(), terminal_account_cost)
    return trades


def run_sol_rs4():
    name = "SOL_4H_RS4_R0343"
    output = OUT / name
    path = ROOT / "research/sol/4h-rs4-regime-switch/scripts/research_sol_4h_rs4_search.py"
    helper = ar.load_module(path, "audit_sol_rs4")
    abl = ar.load_module(helper.ABLATION_PATH, "audit_sol_rs4_ablation")
    frozen = ROOT / "research/sol/4h-rs4-regime-switch/artifacts/sol_4h_rs4_search_2026-07-13.json"
    selected = json.loads(frozen.read_text())["selected"]
    spec = abl.Rs4Spec(**{k.removeprefix("spec_"):v for k,v in selected.items() if k.startswith("spec_")})
    start, end = pd.Timestamp("2026-07-14T00:00:00Z"), END.floor("4h")
    raw = common.load_prices("SOL", "1h").set_index("ts")
    counts = raw.close.resample("4h").count()
    bars = raw.resample("4h").agg({"open":"first", "high":"max", "low":"min", "close":"last", "volume":"sum"}).loc[counts==4]
    bars = bars.loc[bars.index < end]
    endpoint = bars.iloc[-1:].copy()
    endpoint.index = pd.DatetimeIndex([end])
    for col in ("open","high","low","close"):
        endpoint[col] = raw.loc[end,"open"]
    bars = pd.concat([bars, endpoint]).rename_axis("ts").reset_index()
    funding = common.load_funding("SOL")
    featured = helper.attach_features(bars, funding, spec)
    frame = featured[featured.ts >= start].reset_index(drop=True)
    ar.write_json(output / "frozen_contract.json", {"name":name,"family":"SOL-4H-RS4-Regime-Switch","registered":False,"start":start,"end":end,"spec":asdict(spec),"source":str(frozen.relative_to(ROOT)),"source_sha256":hashlib.sha256(frozen.read_bytes()).hexdigest(),"limitation":"Original open-to-open position-return model with no intrabar stop; final open endpoint is observed and liquidation cost is charged explicitly; not an executable bracket strategy"})
    results=[]
    for scenario,cost,delay in [("base",.0014,0),("slippage_8bps",.0018,0),("delay_plus_one_bar",.0014,1)]:
        abl.base.ONE_WAY_COST=cost
        vp=helper.shift_positions(abl.simulate_v10(frame,spec),delay)
        mp=helper.shift_positions(abl.simulate_melt(frame,spec),delay)
        vl=abl.leg_returns("v10",frame,vp,spec); ml=abl.leg_returns("melt",frame,mp,spec)
        returns=vl.returns+spec.weight*ml.returns
        # Last real bar PnL runs to the actual end open; close remaining legs there.
        terminal_cost=cost*(abs(vp[-2])+spec.weight*abs(mp[-2]))
        returns[-2]-=terminal_cost
        equity=np.cumprod(1.+returns[:-1])
        curve=pd.DataFrame({"ts":frame.ts.iloc[1:].to_numpy(),"equity":equity})
        curve["drawdown"]=curve.equity/np.maximum.accumulate(np.r_[1.,equity])[1:]-1.
        trades=pd.DataFrame([*vl.trades,*ml.trades])
        if not trades.empty:
            trades=trades[(pd.to_datetime(trades.entry_ts,utc=True)>=start)&(pd.to_datetime(trades.entry_ts,utc=True)<end)]
        trades=annotate_rs4_trades(trades,end,spec.weight,cost,terminal_cost)
        monthly,prev=[],1.
        for month,group in curve.groupby((curve.ts - pd.Timedelta(nanoseconds=1)).dt.strftime("%Y-%m")):
            value=float(group.equity.iloc[-1]);monthly.append({"month":month,"return":value/prev-1.,"ending_equity":value});prev=value
        summary={"name":name,"timeframe":"4h","start":start,"end":end,"return":float(equity[-1]-1.),"trade_count":len(trades),"close_marked_max_drawdown":float(curve.drawdown.min()),"win_rate":float(trades.net_return.gt(0).mean()) if not trades.empty else 0.,"terminal_liquidation_cost_fraction":float(terminal_cost),"fee_per_fill":.001,"slippage_per_fill":cost-.001,"execution_model":"original 4h open-to-open; no protective intrabar stop"}
        results.append(save_result(output,scenario,trades,curve,pd.DataFrame(monthly),summary))
    ar.write_json(output/"results.json",results)
    return results


def run_btc_lvcb(timeframe):
    m30 = timeframe == "30m"
    name = "lvcb-08816b18771a" if m30 else "lvcb-913f4ff89386"
    output = OUT / name
    path = ROOT / "research/btc/15m-trend-continuation/scripts/research_btc_15m_low_vol_compression_breakout.py"
    engine = ar.load_module(path, f"audit_btc_{timeframe}_lvcb")
    if m30:
        helper_path = ROOT / "research/btc/30m-trend-continuation/scripts/research_btc_30m_trend_continuation.py"
        helper = ar.load_module(helper_path, "audit_btc_30m_helper")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == helper.SOURCE_SHA256
        helper.configure(engine)
        cfg = engine.StrategyConfig(engine.SignalConfig(.35, 32, 48, 48, 192, 8, .00325), 5., 192)
        start = pd.Timestamp("2026-07-22T00:00:00Z")
    else:
        cfg = engine.StrategyConfig(engine.SignalConfig(.40, 16, 96, 96, 384, 16, .0035), 4., 192)
        start = pd.Timestamp("2026-07-21T00:00:00Z")
    assert engine.strategy_id(cfg) == name, (engine.strategy_id(cfg), name)
    raw = common.load_prices("BTC", "15m").set_index("ts")
    if m30:
        counts = raw.close.resample("30min").count()
        frame = raw.resample("30min").agg({"open":"first", "high":"max", "low":"min", "close":"last", "volume":"sum"})
        frame = frame.loc[counts == 2]
    else:
        frame = raw[["open", "high", "low", "close", "volume"]].copy()
    required_days = 180 if m30 else 90
    if frame.index.min() > start - pd.Timedelta(days=required_days + 2):
        raise RuntimeError(f"{timeframe} original quantile requires {required_days} days plus ATR warmup")
    assert frame.index.max() + engine.BAR == END
    funding = common.load_funding("BTC")
    fp = engine.funding_cumulative(frame.index, funding)
    features = engine.base_features(frame)
    signals = engine.build_signals(frame, features, cfg.signal)
    atr = features["atr"].to_numpy()
    ar.write_json(output / "frozen_contract.json", {
        "name": name, "family": f"BTC-{timeframe}-Trend-Continuation", "registered": False,
        "start": start, "end": END, "config": asdict(cfg), "config_hash_matches_frozen_strategy_id": True,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "input": "audited 15m prices" if not m30 else "UTC 30m aggregated from exactly two verified 15m bars; original selection used native 30m",
        "original_quantile_window_bars": 8640, "original_quantile_min_periods": 5760,
        "quantile_wall_clock_days": required_days,
        "end_policy": "Original engine forced liquidation at final observed close including frozen costs",
    })
    results = []
    for scenario, slip in [("base", .0004), ("slippage_8bps", .0008), ("double_fee_slippage", .0008)]:
        updated = replace(cfg, slippage_per_fill=slip, fee_per_fill=.002 if scenario == "double_fee_slippage" else .001)
        result = engine.simulate(frame, fp, atr, *signals, updated, start, END, label=scenario)
        trade_returns = result.trades.trade_return.to_numpy() if not result.trades.empty else np.array([])
        curve = result.equity.rename("equity").rename_axis("ts").reset_index()
        curve["ts"] = curve.ts + engine.BAR
        curve["drawdown"] = curve.equity / np.maximum.accumulate(np.r_[1.,curve.equity])[1:] - 1.
        monthly, prev = [], 1.
        for month, rows in curve.groupby((curve.ts - pd.Timedelta(nanoseconds=1)).dt.strftime("%Y-%m")):
            value = float(rows.equity.iloc[-1])
            monthly.append({"month": month, "return": value / prev - 1., "ending_equity": value})
            prev = value
        before_funding = float(np.prod(1. + trade_returns - result.trades.funding_return.to_numpy()) - 1.) if not result.trades.empty else 0.
        summary = {
            "name": name, "timeframe": timeframe, "start": start, "end": END,
            "return": result.metrics["return_pct"] / 100., "trade_count": result.metrics["trades"],
            "close_marked_max_drawdown": result.metrics["max_drawdown_pct"] / 100.,
            "win_rate": result.metrics["win_rate"], "profit_factor": result.metrics["profit_factor"],
            "price_after_fee_slippage_return_excluding_funding": before_funding,
            "fee_per_fill": updated.fee_per_fill, "slippage_per_fill": slip,
        }
        results.append(save_result(output, scenario, result.trades, curve, pd.DataFrame(monthly), summary))
    ar.write_json(output / "results.json", results)
    return results


def run_btc_keltner():
    name = "BTC-15M-Keltner-frozen-near-miss-20260720"
    output = OUT / name
    path = ROOT / "research/btc/15m-keltner-trend-breakout/scripts/research_btc_15m_keltner_trend_breakout.py"
    engine = ar.load_module(path, "audit_btc_keltner_observation")
    cfg = engine.StrategyConfig(10, 10, 2.5, "ema_slope", 48, 192, 4, "bracket", 2.5, 4., 0., 64)
    start = pd.Timestamp("2026-07-21T00:00:00Z")
    ar.write_json(output / "frozen_contract.json", {
        "name": name, "registered": False, "archive_date": "2026-07-20",
        "start": start, "end": END, "config": asdict(cfg),
        "source": str(path.relative_to(ROOT)), "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "config_source": "research/btc/15m-keltner-trend-breakout/diagnostics/btc-15m-keltner-trend-breakout-initial-search-2026-07-20.md:64",
        "recovery": "All active parameters in frozen near-miss paragraph; bracket inactive trailing_stop_atr=0 from original exit profile",
    })
    frame = common.load_prices("BTC", "15m").set_index("ts")[["open", "high", "low", "close", "volume"]]
    funding = common.load_funding("BTC")
    features = engine.feature_cache(frame)[engine.feature_key(cfg)]
    fp = engine.funding_cumulative_by_bar(frame.index, funding)
    results = []
    for scenario, slip in [("base", .0004), ("slippage_8bps", .0008), ("double_fee_slippage", .0008)]:
        changed = replace(cfg, fee_per_fill=.002 if scenario == "double_fee_slippage" else .001, slippage_per_fill=slip)
        result = engine.simulate(frame, fp, features, changed, start, END, label=scenario)
        curve = result.equity.rename("equity").rename_axis("ts").reset_index()
        curve["ts"] += pd.Timedelta(minutes=15)
        curve["drawdown"] = curve.equity / np.maximum.accumulate(np.r_[1., curve.equity])[1:] - 1.
        monthly, prev = [], 1.
        for month, rows in curve.groupby((curve.ts - pd.Timedelta(nanoseconds=1)).dt.strftime("%Y-%m")):
            value = float(rows.equity.iloc[-1])
            monthly.append({"month": month, "return": value / prev - 1., "ending_equity": value})
            prev = value
        trades = result.trades
        summary = {
            "name": name, "timeframe": "15m", "start": start, "end": END,
            "return": float(curve.equity.iloc[-1] - 1.), "trade_count": len(trades),
            "close_marked_max_drawdown": float(curve.drawdown.min()),
            "win_rate": float(trades.trade_return.gt(0).mean()) if not trades.empty else 0.,
            "price_after_fee_slippage_return_excluding_funding": float(np.prod(1. + trades.trade_return - trades.funding_return) - 1.) if not trades.empty else 0.,
            "fee_per_fill": changed.fee_per_fill, "slippage_per_fill": slip,
        }
        results.append(save_result(output, scenario, trades, curve, pd.DataFrame(monthly), summary))
    ar.write_json(output / "results.json", results)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["sol_pb", "sol_vcb", "sol_rs4", "btc_ema", "btc_15m", "btc_30m", "btc_keltner"])
    args = parser.parse_args()
    results = []
    for name, func in [("sol_pb", run_sol_pb), ("sol_vcb",lambda:run_sol_pb(True)), ("sol_rs4",run_sol_rs4), ("btc_ema",run_btc_ema), ("btc_15m", lambda: run_btc_lvcb("15m")), ("btc_30m", lambda: run_btc_lvcb("30m")), ("btc_keltner", run_btc_keltner)]:
        if args.only and name != args.only:
            continue
        try:
            values = func()
            results.extend(values)
            print(json.dumps(values, default=str), flush=True)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            results.append({"name": name, "status": "REPLAY_FAILURE", "error": f"{type(exc).__name__}: {exc}"})
    completed = [row for path in sorted(OUT.glob("*/results.json")) for row in json.loads(path.read_text())]
    ar.write_json(OUT / "results.json", completed)


if __name__ == "__main__":
    main()
