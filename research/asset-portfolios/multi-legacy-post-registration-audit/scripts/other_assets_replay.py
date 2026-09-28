"""Replay registered single-asset 1h rules without rerunning any parameter search.

Inputs are the common audit's verified exported frames. Original family code and
documentation are read-only. No original load_data/main entrypoint is invoked.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "research/asset-portfolios/multi-legacy-post-registration-audit"
OUT = FAMILY / "artifacts/other_assets"
ENGINE_PATH = ROOT / "research/_shared-kernels/1h-adaptive-regime-search/v1/engine.py"
ENGINE_HASH = "0420ea44854201e17d4bf5b9142fb8335d143e78772656473a1dcf4594a5f04c"
END = pd.Timestamp("2026-09-05T15:00:00Z")

REGISTERED = {
    "BTC": ("V4", "2026-07-07", "notes/btc-1h-ar-v4-window-backtest-2026-07-07.md"),
    "ETH": ("V4", "2026-07-13", "specs/eth-1h-ar-v4-high-win-strategy-refined-spec-2026-07-13.md"),
    "SOL": ("V3", "2026-07-13", "specs/sol-1h-ar-v3-parameter-spec-2026-07-13.md"),
    "BNB": ("V3", "2026-07-07", "specs/bnb-1h-ar-v3-parameter-spec-2026-07-07.md"),
    "TRX": ("V3", "2026-07-06", "specs/trx-1h-ar-v3-parameter-spec-2026-07-06.md"),
}
UNREGISTERED = [
    "btc/15m-ema-trend-breakout", "btc/15m-keltner-trend-breakout",
    "btc/15m-trend-continuation", "btc/30m-trend-continuation",
    "bnb/15m-adaptive-regime", "sol/1h-pullback-bracket",
    "sol/1h-volatility-compression-breakout", "sol/4h-rs4-regime-switch",
]


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def frozen_configs(asset, engine, version_override=None):
    base = ROOT / f"research/{asset.lower()}/1h-adaptive-regime"
    sys.path.insert(0, str(base / "scripts"))
    if asset == "BTC":
        mod = load_module(base / "scripts/btc_1h_ar_v4.py", "audit_btc_v4")
        return mod.v4_configs(engine), None, None
    if asset == "ETH":
        mod = load_module(base / "scripts/eth_1h_ar_v4.py", "audit_eth_v4")
        clean = mod.clean21
        if version_override == "V3":
            spec_text = (base / "specs/eth-1h-ar-v3-clean-tuned-spec-2026-07-07.md").read_text()
            values = [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", spec_text, re.S)]
            bb_values = {k: v for k, v in values[0].items() if k not in ("ema_htf", "max_aligned_funding_bps")}
            bb = clean.BBBreakV21CleanConfig(**bb_values)
            rsi = clean.RSIV21CleanConfig(**values[1])
        else:
            bb, rsi = mod.V4_BB_BREAK, mod.V4_RSI
        return (
            clean.v1_clean.bb_break_to_base(engine, clean.bb_to_v1_clean(bb)),
            clean.v1_clean.rsi_to_base(engine, clean.rsi_to_v1_clean(rsi)),
        ), None, None
    if asset == "BNB":
        mod = load_module(base / "scripts/bnb_1h_ar_v3.py", "audit_bnb_v3")
        return mod.v3_configs(engine), mod.PRIORITIES, None
    if asset == "TRX":
        mod = load_module(base / "scripts/trx_1h_ar_v3.py", "audit_trx_v3")
        return (
            mod.v2.macd_to_base(engine, mod.macd_to_v2(mod.MACDV3Config())),
            mod.v2.stoch_to_base(engine, mod.stoch_to_v2(mod.StochV3Config())),
        ), None, None
    if asset == "SOL":
        # The deleted JSON is exactly reproduced from the complete V2 spec,
        # followed by the four V3 changes per leg documented in its spec.
        text = (base / "specs/sol-1h-ar-v2-parameter-spec-2026-07-07.md").read_text()
        sections = re.split(r"## Leg [12]：[^\n]+", text)[1:]
        configs = []
        for section in sections:
            config = {}
            for key, value in re.findall(r"^- `([^`]+)` = `([^`]+)`", section, re.M):
                try:
                    config[key] = json.loads(value)
                except json.JSONDecodeError:
                    config[key] = value
            configs.append(engine.StrategyConfig(**config))
        if version_override == "V2":
            return tuple(configs), None, None
        don = replace(configs[0], name="DON_SM_L3_TP1_SL4_H72", tp_atr=1., sl_atr=4., max_hold_bars=72, fixed_leverage=3.)
        vwap = replace(configs[1], name="VWAP_SM_W3_roc6_macd_L1_TP1.5_SL1.5_H12", tp_atr=1.5, sl_atr=1.5, max_hold_bars=12, fixed_leverage=1.)
        sm = load_module(base / "scripts/research_sol_1h_ar_v2_vwap_state_machine.py", "audit_sol_sm")
        return (don, vwap), None, sm
    raise ValueError(asset)


def signature(trades):
    return [(t.config, t.entry_ts, t.exit_ts, t.side, t.entry_price, t.exit_price, t.equity_ret) for t in trades]


def replay_asset(asset, start, version_override=None, *, slippage=.0004, extra_delay=0):
    """Export a frozen asset's candidates for the account-combination audit.

    No source loaders or selection scores run. Raises if a missing historic
    component priority changes this requested interval's trade path.
    """
    import audit_common as common
    start = pd.Timestamp(start)
    if hashlib.sha256(ENGINE_PATH.read_bytes()).hexdigest() != ENGINE_HASH:
        raise RuntimeError("Original engine hash drift")
    engine = load_module(ENGINE_PATH, f"audit_{asset.lower()}_export_engine")
    configs, priorities, special = frozen_configs(asset, engine, version_override)
    raw = common.load_prices(asset, "1h").reset_index(drop=True)
    funding = common.load_funding(asset)
    raw = raw[raw.ts >= funding.ts.min().ceil("h")].reset_index(drop=True)
    assert raw.ts.min() <= start - pd.Timedelta(days=30)
    frame = engine.add_features(raw, funding)
    sentinel = frame.iloc[-1:].copy()
    sentinel["ts"] = END
    for col in ("open", "high", "low", "close"):
        sentinel[col] = raw.close.iloc[-1]
    terminal_frame = pd.concat([frame, sentinel], ignore_index=True)
    ft, fc = engine.funding_prefix(funding)
    engine.FEE_PER_FILL, engine.SLIPPAGE_PER_FILL = .001, slippage
    legs = []
    for i, cfg in enumerate(configs):
        cfg = replace(cfg, entry_delay_bars=cfg.entry_delay_bars + extra_delay)
        signal = special.armed_vwap_signal(engine, frame, cfg, 3, "roc6_macd")[0] if special is not None and i == 1 else engine.build_signal(frame, cfg)
        entry_times = frame.ts + pd.Timedelta(hours=cfg.entry_delay_bars)
        signal[((frame.ts + pd.Timedelta(hours=1) < start) | (entry_times < start) | (entry_times >= END)).to_numpy()] = 0
        trades = engine.simulate_trades(terminal_frame, np.r_[signal, 0], cfg, ft, fc)
        for trade in trades:
            if trade.exit_ts == END:
                trade.exit_reason = "audit_terminal_close"
        legs.append(trades)
    trades = engine.merge_trade_sets(*legs, *(priorities or (1., 0.)))
    opposite = engine.merge_trade_sets(*legs, 0., 1.)
    equivalent = signature(trades) == signature(opposite)
    if priorities is None and not equivalent:
        raise RuntimeError(f"{asset} missing frozen priority affects the requested path")
    return {"asset": asset, "engine": engine, "frame": raw, "funding": funding, "trades": trades, "configs": configs, "priority_orders_trade_path_equal": equivalent}


def curve_and_summary(engine, frame, trades, start, end, funding, fee):
    """Close-marked ledger; native engine returns retained as a separate check.

    Intrabar trade exits have no exact timestamp in 1h OHLC. They are booked by
    the end of their exit bar. Native [entry,exit) funding semantics are kept.
    """
    rows = []
    balance = 1.0
    cursor = 0
    selected = frame[(frame.ts >= start) & (frame.ts < end)]
    for row in selected.itertuples(index=False):
        ts = row.ts
        close_time = ts + pd.Timedelta(hours=1)
        while cursor < len(trades) and trades[cursor].exit_ts <= ts:
            balance *= 1.0 + trades[cursor].equity_ret
            cursor += 1
        marked = balance
        if cursor < len(trades):
            trade = trades[cursor]
            if trade.entry_ts <= ts < trade.exit_ts:
                accrued = funding[(funding.ts >= trade.entry_ts) & (funding.ts < close_time)].funding_rate.sum()
                price_ret = trade.side * (row.close / trade.entry_price - 1.)
                marked = balance * (1. + trade.exposure * (price_ret - fee - trade.side * accrued))
        rows.append({"ts": close_time, "equity": marked, "closed_balance": balance})
    # Explicit forced liquidation at the final observed close, including exit fee.
    while cursor < len(trades):
        balance *= 1.0 + trades[cursor].equity_ret
        cursor += 1
    if rows:
        rows[-1]["equity"] = balance
        rows[-1]["closed_balance"] = balance
    curve = pd.DataFrame([{"ts": start, "equity": 1., "closed_balance": 1.}] + rows)
    curve["drawdown"] = curve.equity / curve.equity.cummax() - 1.
    native = engine.metrics(trades, start, end)
    assert abs(float(native["total_return"]) - (balance - 1.)) < 1e-10
    monthly = []
    prev = 1.
    for month, group in curve.iloc[1:].groupby((curve.ts.iloc[1:] - pd.Timedelta(nanoseconds=1)).dt.strftime("%Y-%m")):
        value = float(group.equity.iloc[-1])
        monthly.append({"month": month, "return": value / prev - 1., "ending_equity": value})
        prev = value
    return curve, pd.DataFrame(monthly), {
        "return": balance - 1., "final_equity": balance,
        "price_after_fee_slippage_return_excluding_funding": float(np.prod([1. + t.equity_ret - t.exposure * t.funding_ret_1x for t in trades]) - 1.),
        "close_marked_max_drawdown": float(curve.drawdown.min()),
        "legacy_engine_conservative_mae_drawdown": native["max_dd"],
        "trade_count": len(trades), "win_rate": native["win_rate"],
        "profit_factor": native["profit_factor"], "maximum_exposure": native["max_exposure"],
        "long_trades": native["long_trades"], "short_trades": native["short_trades"],
        "funding_rate_sum_1x": native["funding_return_1x"],
        "forced_terminal_liquidations": sum(t.exit_reason == "audit_terminal_close" for t in trades),
    }


def run_asset(asset, common):
    if hashlib.sha256(ENGINE_PATH.read_bytes()).hexdigest() != ENGINE_HASH:
        raise RuntimeError("Original shared engine hash drift")
    engine = load_module(ENGINE_PATH, f"audit_{asset.lower()}_engine")
    configs, priorities, special = frozen_configs(asset, engine)
    version, registered, source = REGISTERED[asset]
    start = pd.Timestamp(registered, tz="UTC") + pd.Timedelta(days=1)
    output = OUT / asset
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "frozen_contract.json", {
        "family": f"{asset}-1H-Adaptive-Regime", "version": version,
        "registration_date": registered, "registration_evidence": f"research/{asset.lower()}/1h-adaptive-regime/{source}",
        "start": start, "end": END, "initial_state": "flat",
        "configs": [asdict(c) for c in configs], "frozen_priorities": priorities,
        "missing_priority_policy": "enumerate both fixed orders; report exact equality or block",
        "funding_semantics": "original engine sum rates over [entry_bar_open,exit_bar_open); not exact mark-notional accounting",
        "end_policy": "forced liquidation at final observed close with frozen fee and scenario slippage",
        "engine_sha256": ENGINE_HASH,
    })
    raw = common.load_prices(asset, "1h").copy().reset_index(drop=True)
    funding = common.load_funding(asset).copy()
    if funding.ts.min() > raw.ts.min():
        # No silent fillna(0) at the beginning of the supplied prewarm frame.
        raw = raw[raw.ts >= funding.ts.min().ceil("h")].reset_index(drop=True)
    # All active high-timeframe filters are h4/h12 (maximum 48 h12 bars),
    # and the largest native EMA is 377h; 30 days includes both warmups.
    assert raw.ts.min() <= start - pd.Timedelta(days=30)
    assert raw.ts.max() + pd.Timedelta(hours=1) == END
    featured = engine.add_features(raw, funding)
    assert featured.loc[featured.ts >= start, "last_funding_rate"].notna().all()
    # Sentinel is only a liquidation price at the end, added AFTER features.
    # It is never consumed as a price bar or used to generate signals.
    sentinel = featured.iloc[-1:].copy()
    sentinel["ts"] = END
    for col in ("open", "high", "low", "close"):
        sentinel[col] = raw.close.iloc[-1]
    terminal_frame = pd.concat([featured, sentinel], ignore_index=True)
    ft, fc = engine.funding_prefix(funding)
    results = []
    for scenario, slippage, extra_delay in [("base", .0004, 0), ("slippage_8bps", .0008, 0), ("delay_plus_one_bar", .0004, 1)]:
        engine.FEE_PER_FILL = .001
        engine.SLIPPAGE_PER_FILL = slippage
        leg_trades = []
        for i, cfg in enumerate(configs):
            cfg = replace(cfg, entry_delay_bars=cfg.entry_delay_bars + extra_delay)
            if special is not None and i == 1:
                signal, _, _ = special.armed_vwap_signal(engine, featured, cfg, 3, "roc6_macd")
            else:
                signal = engine.build_signal(featured, cfg)
            # Decision must happen after registration and entry must be in range.
            signal[(featured.ts + pd.Timedelta(hours=1) < start).to_numpy()] = 0
            entry_times = featured.ts + pd.Timedelta(hours=cfg.entry_delay_bars)
            signal[(entry_times < start).to_numpy() | (entry_times >= END).to_numpy()] = 0
            if "research_window_valid" in featured:
                signal[~featured.research_window_valid.to_numpy(bool)] = 0
            trades = engine.simulate_trades(terminal_frame, np.r_[signal, 0], cfg, ft, fc)
            for t in trades:
                if t.exit_ts == END:
                    t.exit_reason = "audit_terminal_close"
            leg_trades.append(trades)
        normal = engine.merge_trade_sets(*leg_trades, *(priorities or (1., 0.)))
        reverse = engine.merge_trade_sets(*leg_trades, 0., 1.)
        equivalent = signature(normal) == signature(reverse)
        if priorities is None and not equivalent:
            for order, trades in [("left_first", normal), ("right_first", reverse)]:
                pd.DataFrame([asdict(t) for t in trades]).to_csv(output / f"{scenario}_{order}_trades.csv", index=False)
            results.append({"asset": asset, "version": version, "scenario": scenario, "status": "MISSING_FROZEN_PRIORITY_AFFECTS_PATH"})
            continue
        curve, monthly, summary = curve_and_summary(engine, raw, normal, start, END, funding, .001)
        pd.DataFrame([asdict(t) for t in normal]).to_csv(output / f"{scenario}_trades.csv", index=False)
        curve.to_csv(output / f"{scenario}_equity.csv", index=False)
        monthly.to_csv(output / f"{scenario}_monthly.csv", index=False)
        results.append({
            "asset": asset, "version": version, "scenario": scenario,
            "status": "REPLAYED_OBSERVED_FUNDING_ESTIMATE",
            "start": start, "end": END, "days": (END - start).total_seconds() / 86400.,
            "priority_orders_trade_path_equal": equivalent,
            "fee_per_fill": .001, "slippage_per_fill": slippage,
            **summary,
        })
    write_json(output / "results.json", results)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", choices=list(REGISTERED), action="append")
    parser.add_argument("--inventory-only", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.inventory_only:
        import other_assets_finalize
        other_assets_finalize.main()
        return
    import audit_common as common
    results = []
    for asset in args.asset or REGISTERED:
        try:
            asset_results = run_asset(asset, common)
            results.extend(asset_results)
            print(json.dumps(asset_results, default=str), flush=True)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            failure = {"asset": asset, "status": "REPLAY_FAILURE", "error": f"{type(exc).__name__}: {exc}"}
            write_json(OUT / asset / "failure.json", failure)
            results.append(failure)
    write_json(OUT / "results.json", results)
    pd.DataFrame(results).to_csv(OUT / "results.csv", index=False)
    pins = {}
    for mod in list(sys.modules.values()):
        file = getattr(mod, "__file__", None)
        if file:
            path = Path(file).resolve()
            if path.is_relative_to(ROOT / "research") and path.is_file():
                pins[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(OUT / "source_pins.json", pins)


if __name__ == "__main__":
    main()
