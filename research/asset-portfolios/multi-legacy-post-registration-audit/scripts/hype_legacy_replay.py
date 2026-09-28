"""Fixed post-registration replay of five HYPE 15m families.

Only audit_common provides market prices/funding. Original strategy modules are
imported for pure feature/state-machine functions; none of their loaders/main
functions is called. No strategy parameter is selected on the evaluation tail.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from collections import OrderedDict
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "research/asset-portfolios/multi-legacy-post-registration-audit"
OUT = FAMILY / "artifacts/hype_legacy"
for relative in (
    "src", "research/hype/15m-ema-trend-breakout/scripts",
    "research/hype/15m-ema-crossover/scripts",
    "research/hype/15m-multi-indicator-intraday/scripts",
    "research/hype/15m-trend-breakout-multi-indicator-ensemble/scripts",
    "research/hype/15m-candle-count-reversal/scripts",
):
    sys.path.insert(0, str(ROOT / relative))
sys.path.append(str(ROOT / "archive/scripts/research"))

REGISTRATIONS = {
    "HYPE-EMA-X-V18": {
        "family": "15m-ema-crossover", "registration": "2026-07-01",
        "start": "2026-07-02T00:00:00Z", "last_research_data": "2026-06-01T03:00:00Z",
        "source": "specs/hype-ema-x-v18-baseline-spec.md",
        "date_evidence": "spec Version identity and decision log dated 2026-07-01; date-only => next UTC day",
        "selection": "latest registered version; also dry-run version",
        "cost": "0.00085 per fill plus adverse price slippage 0.0005 per fill; original engine excludes funding",
    },
    "HYPE-EMA-TB-V41": {
        "family": "15m-ema-trend-breakout", "registration": "2026-07-20",
        "start": "2026-07-21T00:00:00Z", "last_research_data": "2026-07-17T08:45:00Z",
        "source": "specs/hype-trend-strategy-v41-spec.md",
        "date_evidence": "spec dated 2026-07-20; date-only => next UTC day",
        "selection": "latest registered V41; separate external live V35 and dry-run V35.1 are not substituted",
        "cost": "0.00085 per fill; original engine includes funding",
    },
    "HYPE-15M-MII-V1.4A": {
        "family": "15m-multi-indicator-intraday", "registration": "2026-07-09",
        "start": "2026-07-10T00:00:00Z", "last_research_data": "2026-07-09 date-only recent API report; exact tail unavailable",
        "source": "specs/hype-15m-mii-v1-4a-parameter-spec-not-live-ready-2026-07-09.md",
        "date_evidence": "spec dated 2026-07-09 includes recent API data that day; next UTC day excludes entire revealed date",
        "selection": "latest registered version; current documented dry-run version",
        "cost": "fee 0.001 + slippage 0.0004 per fill; fixed exposure 2.5; original engine excludes funding",
    },
    "HYPE-15M-TB-MII-ENS-V2": {
        "family": "15m-trend-breakout-multi-indicator-ensemble", "registration": "2026-07-09",
        "start": "2026-07-10T00:00:00Z", "last_research_data": "2026-07-08T05:30:00Z",
        "source": "live-specs/hype-15m-tb-mii-ens-v2-live-validation-spec-not-live-ready-2026-07-09.md",
        "date_evidence": "core ledger explicitly registers V2 on 2026-07-09; next UTC day",
        "selection": "latest registered combination; V39 trend priority + MII V1.4, preempt enabled, MII K+1",
        "cost": "trend 0.00085 per fill and funding; MII 0.001+0.0004 per fill, original MII excludes funding",
    },
    "HYPE-CC-V35": {
        "family": "15m-candle-count-reversal", "registration": "2026-06-08T03:36:54Z",
        "start": "2026-06-08T03:45:00Z", "last_research_data": "2026-06-01T03:00:00Z",
        "source": "specs/hype-v35-reproducible-params.md",
        "date_evidence": "git 78c0c72 first file save 2026-06-08 11:36:54 +0800; first fully subsequent 15m bar",
        "selection": "latest V35; subsequent maker/MA diagnostics explicitly did not register V36",
        "cost": "original spec fee 0.00045 + slippage 0.0004 per fill, funding included; later Binance handoff differs",
        "limitation": "Original spec/code disagree on entry/early-exit timing; next-open audit replay must be separately labelled. Independent mark high/low required.",
    },
}


def json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, Path)):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (pd.Series, pd.DataFrame)):
        return value.to_dict()
    raise TypeError(type(value).__name__)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=json_default) + "\n")


def frame_with_index(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "ts" in result:
        result["ts"] = pd.to_datetime(result["ts"], utc=True)
        result = result.set_index("ts")
    result.index = pd.to_datetime(result.index, utc=True)
    result.index.name = "ts"
    assert result.index.is_unique and result.index.is_monotonic_increasing
    assert not result[["open", "high", "low", "close", "volume"]].isna().any().any()
    return result


def funding_events(value: Any) -> pd.Series:
    if isinstance(value, tuple):
        value = value[0]
    if isinstance(value, pd.Series):
        result = value.copy()
    else:
        value = value.copy()
        col = next(x for x in ("ts", "funding_time", "timestamp") if x in value)
        result = value.set_index(col)["funding_rate"]
    result.index = pd.to_datetime(result.index, utc=True)
    assert result.index.is_unique and not result.isna().any()
    return result.sort_index().astype(float)


def observed_bar_funding(events: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    # Zero here means no OBSERVED event in that bar, never a coverage claim.
    rates = events.groupby(events.index.floor("15min")).sum()
    result = pd.Series(0.0, index=index)
    overlap = result.index.intersection(rates.index)
    result.loc[overlap] = rates.loc[overlap]
    return result


def post_features(features: pd.DataFrame, start: pd.Timestamp) -> pd.DataFrame:
    output = features.copy()
    output.loc[output.index < start, ["long_signal", "short_signal"]] = False
    return output


def terminal_trend(eq: pd.Series, trades: pd.DataFrame, position: dict | None, frame: pd.DataFrame, cost: float, leg: str = "trend"):
    eq = eq.copy()
    records = trades.to_dict("records")
    if position:
        allocation = float(position["allocation"])
        eq.iloc[-1] *= 1.0 - allocation * cost
        records.append({**position, "leg": leg, "exit_ts": frame.index[-1], "exit_price": frame.close.iloc[-1], "exit_reason": "terminal_mark", "exit_equity": eq.iloc[-1]})
    return eq, pd.DataFrame(records)


def summarize_save(key: str, eq: pd.Series, trades: pd.DataFrame, extra: dict, tag: str = "primary") -> dict:
    name = key.lower().replace(".", "_") + "__" + tag
    eq = eq.astype(float).copy()
    index = pd.to_datetime(eq.index, utc=True)
    eq.index = index
    assert np.isfinite(eq).all() and (eq > 0).all()
    prior = eq.shift(1).fillna(1.0)
    returns = eq / prior - 1
    dd = eq / eq.cummax().clip(lower=1.0) - 1
    ledger = trades.copy()
    if not ledger.empty:
        for col in ("entry_ts", "exit_ts"):
            ledger[col] = pd.to_datetime(ledger[col], utc=True)
        assert (ledger.entry_ts >= pd.Timestamp(REGISTRATIONS[key]["start"])).all()
        assert (ledger.exit_ts >= ledger.entry_ts).all()
    natural = ledger.loc[~ledger.exit_reason.isin(["terminal_mark", "open_at_end"])] if len(ledger) else ledger
    terminal_n = len(ledger) - len(natural)
    if len(ledger) and "trade_return" in ledger:
        trade_values=pd.to_numeric(natural.trade_return,errors="coerce")
        natural_wins=int(trade_values.gt(0).sum())
    else:
        natural_wins=None
    monthly = returns.groupby(index.strftime("%Y-%m")).apply(lambda x: (1+x).prod()-1).rename("return")
    curve_path = OUT / f"{name}_equity.csv"
    pd.DataFrame({"equity": eq, "return": returns, "drawdown": dd}).to_csv(curve_path, index_label="ts")
    ledger.to_csv(OUT / f"{name}_trades.csv", index=False)
    monthly.mul(100).to_csv(OUT / f"{name}_monthly.csv", index_label="month")
    windows = {}
    for days in (7, 30, 60):
        cutoff = index[0] + pd.Timedelta(days=days)
        if index[-1] + pd.Timedelta(minutes=15) >= cutoff:
            slice_ = eq[index < cutoff]
            windows[f"first_{days}d_return_pct"] = float((slice_.iloc[-1]-1)*100)
    result = {
        "strategy": key, "variant": tag, **REGISTRATIONS[key],
        "first_evaluation_bar": index[0], "last_evaluation_bar": index[-1],
        "end_exclusive": index[-1]+pd.Timedelta(minutes=15),
        "days": (index[-1]+pd.Timedelta(minutes=15)-index[0]).total_seconds()/86400,
        "return_pct": float((eq.iloc[-1]-1)*100), "max_drawdown_pct": float(dd.min()*100),
        "natural_closed_trades": len(natural), "terminal_marks": terminal_n,
        "natural_wins_original_trade_measure":natural_wins,
        "monthly_return_pct": monthly.mul(100).to_dict(), **windows, **extra,
        "equity_file": str(curve_path.relative_to(ROOT)),
        "trades_file": str((OUT/f"{name}_trades.csv").relative_to(ROOT)),
    }
    write_json(OUT / f"{name}_summary.json", result)
    return result


def observed_overlay(eq: pd.Series, trades: pd.DataFrame, events: pd.Series, leg_filter: str | None = None) -> pd.Series:
    factors = pd.Series(1.0, index=eq.index)
    for record in trades.to_dict("records"):
        if leg_filter and str(record.get("leg", "")) != leg_filter:
            continue
        entry, exit_ = pd.Timestamp(record["entry_ts"]), pd.Timestamp(record["exit_ts"])
        exposure = float(record.get("allocation", 2.5))
        held = events[(events.index > entry) & (events.index < exit_)]
        # Intrabar exits hold the position at that bar's opening settlement.
        if record["exit_reason"] in {"stop_loss", "take_profit", "stop", "take", "terminal_mark"}:
            held = events[(events.index > entry) & (events.index <= exit_)]
        for ts, rate in held.items():
            bar = ts.floor("15min")
            if bar in factors.index:
                factors.loc[bar] *= 1-float(record["direction"])*exposure*float(rate)
    return eq * factors.cumprod()


def replay_tb(frame: pd.DataFrame, events: pd.Series) -> list[dict]:
    base = importlib.import_module("research_hype_ema_tb_v35_profit_floor")
    ab = importlib.import_module("research_hype_ema_tb_v35_full_ablation_recent_tune")
    cd = importlib.import_module("research_hype_ema_tb_v35_cooldown4")
    key = "HYPE-EMA-TB-V41"
    start = pd.Timestamp(REGISTRATIONS[key]["start"])
    config = replace(base.V35Config(), warmup_bars=int(frame.index.searchsorted(start)))
    features = post_features(ab.build_signals(base.build_features(frame, config), config, ab.SignalFlags(short_use_h1_ema=False)), start)
    results = []
    for tag, rates in (("observed_funding", observed_bar_funding(events, frame.index)), ("funding_excluded_diagnostic", pd.Series(0.0,index=frame.index))):
        run = cd.run_backtest(cd.RunSpec("v41_fixed",1,False),frame,rates,features,config)
        eq, trades = terminal_trend(run.equity_curve,run.trades,run.open_position,frame,config.trade_cost_rate)
        results.append(summarize_save(key,eq,trades,{"funding_status":"observed-event estimate; settlement coverage NOT verified" if tag=="observed_funding" else "funding deliberately excluded for diagnostic", "parameters":asdict(config), "original_end_position":run.open_position},tag))
    return results


def replay_x(frame: pd.DataFrame, events: pd.Series) -> list[dict]:
    h = importlib.import_module("research_hype_v17_hybrid_ablation")
    retest = importlib.import_module("research_hype_ema_x_v18_retest")
    late = importlib.import_module("research_hype_v13_late_reentry")
    key="HYPE-EMA-X-V18"
    start=pd.Timestamp(REGISTRATIONS[key]["start"])
    features=h.add_v17_indicators(h.add_structure_features(h.add_oscillator_features(h.add_volume_features(h.build_features(frame.reset_index())))))
    candidate=retest.v18_candidate()
    base_signal,_,_=h.build_signal(features,h.SignalPlan("baseline","atr18"))
    capture={}
    original=late.metric_result
    def metric_capture(spec,curve,trades,**kwargs):
        capture["curve"]=curve.copy();capture["trades"]=pd.DataFrame(trades)
        return original(spec,curve,trades,**kwargs)
    late.metric_result=metric_capture
    try:
        h.run_candidate(features,candidate,start,base_signal,collect_trades=True)
    finally:
        late.metric_result=original
    eq=capture["curve"]
    trades=capture["trades"]
    if len(trades):
        terminal=trades.exit_reason.eq("open_at_end")
        for i,row in trades.loc[terminal].iterrows():
            exit_price=float(frame.close.iloc[-1])*(1-int(row.direction)*late.SLIPPAGE)
            eq.iloc[-1]*=(1+row.allocation*row.direction*(exit_price/float(frame.close.iloc[-1])-1))*(1-late.TRADE_COST*row.allocation)
            trades.loc[i,"exit_price"]=exit_price
            trades.loc[i,"exit_reason"]="terminal_mark"
            trades.loc[i,"equity_after"]=eq.iloc[-1]
    # Original 'pnl_pct' is gross of fees; derive net trade returns from equity endpoints.
    if len(trades):
        endpoints=trades.equity_after.astype(float)
        trades["trade_return"]=endpoints/endpoints.shift(1).fillna(1.0)-1
    original_result=summarize_save(key,eq,trades,{"funding_status":"original specification excludes funding","parameters":asdict(candidate)})
    funded=observed_overlay(eq,trades,events)
    funded_result=summarize_save(key,funded,trades,{"funding_status":"observed-event overlay estimate; coverage NOT verified; trade CSV is original engine ledger"},"observed_funding_overlay")
    return [original_result,funded_result]


def mii_context(frame: pd.DataFrame):
    v12=importlib.import_module("research_hype_15m_mii_v1_2_atr_bracket_exit")
    features=v12.evolution.add_rsi_features(v12.evolution.add_features(frame.reset_index(),[]))
    return v12.evolution.EvalContext(features,v12.build_market_arrays(features),frame.index[0],frame.index[-1]+pd.Timedelta(minutes=15),{},OrderedDict())


def mii_candidates(frame,context,start,tp,sl):
    v12=importlib.import_module("research_hype_15m_mii_v1_2_atr_bracket_exit")
    v1=importlib.import_module("research_hype_15m_mii_v1_full_ablation")
    candidate=v12.AtrBracketCandidate("fixed_registered","atr_bracket",96,tp,sl,24)
    raw=v12.simulate_atr_bracket_trades(context,candidate,1)
    filter_=replace(v12.BASE_CONFIG.filter,min_rvol96=0.85)
    by_entry={}
    for trade in raw:
        if context.features.ts.iloc[trade.signal_i] < start or not v1.passes_filter(trade,filter_):
            continue
        if trade.exit_reason=="max_hold" and trade.entry_i+24>len(frame)-1:
            price=float(frame.close.iloc[-1])
            trade=replace(trade,exit_price=price,raw_return=trade.direction*(price/trade.entry_price-1),exit_reason="terminal_mark")
        by_entry.setdefault(int(trade.entry_i),trade)
    return by_entry


def replay_mii_ensemble(frame: pd.DataFrame,events: pd.Series)->list[dict]:
    ens=importlib.import_module("research_hype_15m_tb_mii_ensemble_backtest")
    context=mii_context(frame)
    output=[]
    for key,tp,sl,trend in (("HYPE-15M-MII-V1.4A",1.4,3.0,False),("HYPE-15M-TB-MII-ENS-V2",1.25,5.0,True)):
        start=pd.Timestamp(REGISTRATIONS[key]["start"])
        config,flags=ens.trend_setup("v39")
        config=replace(config,warmup_bars=int(frame.index.searchsorted(start)))
        features=post_features(ens.tbab.build_signals(ens.tb.build_features(frame,config),config,flags),start)
        candidates=mii_candidates(frame,context,start,tp,sl)
        rates=observed_bar_funding(events,frame.index)
        run=ens.run_account(key,frame,rates,features,config,candidates,enable_v35=trend,enable_mii=True,preempt=True,trend_label="v39",mii_label="mii")
        eq,trades=terminal_trend(run["equity_curve"],run["trades"],run["open_position"]["trend"],frame,config.trade_cost_rate,leg="v39")
        if len(trades):
            trades.loc[trades.leg.eq("mii"),"allocation"]=2.5
        assert not run["open_position"]["mii"], "MII terminal mark must close remaining position"
        output.append(summarize_save(key,eq,trades,{"funding_status":"trend observed-event estimate, MII excluded" if trend else "original specification excludes funding", "parameters":{"tp_atr":tp,"sl_atr":sl,"exposure":2.5,"timeout":24,"min_rvol96":0.85}, "terminal_note":"Only dataset-truncated max_hold is valued at last close instead of original forced last open."}))
        funded=observed_overlay(eq,trades,events,leg_filter="mii")
        output.append(summarize_save(key,funded,trades,{"funding_status":"both legs observed-event estimate; coverage NOT verified; trade CSV is original engine ledger"},"observed_funding_overlay"))
    return output


def replay_cc(frame: pd.DataFrame,events: pd.Series)->list[dict]:
    key="HYPE-CC-V35"
    snapshot=ROOT/"research/hype/15m-candle-count-reversal/artifacts/hype_cc_v35_maker_entry_input_2026-09-07.parquet"
    receipt_path=snapshot.with_name("hype_cc_v35_maker_entry_summary_2026-09-07.json")
    receipt=json.loads(receipt_path.read_text())
    digest=hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert digest==receipt["artifact_identity"]["input_snapshot_sha256"]
    old=frame_with_index(pd.read_parquet(snapshot))
    assert frame.index.isin(old.index).all()
    old=old.loc[frame.index]
    differences={col:float((old[col]-frame[col]).abs().max()) for col in ("open","high","low","close","volume")}
    price_mismatch={col:int((old[col]-frame[col]).abs().gt(1e-9).sum()) for col in differences}
    mark=old[["mark_high","mark_low"]]
    assert np.isfinite(mark).all().all() and (mark>0).all().all() and (mark.mark_high>=mark.mark_low).all()
    assert not any(price_mismatch.values()),price_mismatch
    evidence={"snapshot":str(snapshot.relative_to(ROOT)),"sha256":digest,"receipt_sha256":hashlib.sha256(receipt_path.read_bytes()).hexdigest(),"source_quality":receipt["data_quality"],"rows":len(mark),"price_abs_max_difference":differences,"price_mismatching_rows":price_mismatch,"mark_rows_missing":0,"status":"observed mark supplementary input; NOT catalog trusted"}
    write_json(OUT/"cc_mark_input_audit.json",evidence)
    ccframe=frame.join(mark)
    ccframe["funding_rate"]=observed_bar_funding(events,ccframe.index)
    start=pd.Timestamp(REGISTRATIONS[key]["start"])
    maker=importlib.import_module("research_hype_cc_v35_maker_entry_audit")
    featured=maker.build_features(ccframe)
    rows=[]
    for label,fee in (("next_open_spec_cost",0.00045),("next_open_binance_cost_sensitivity",0.001)):
        run=maker.run_backtest(featured,variant=maker.Variant("next_open_v35","next_open","taker"),costs=maker.CostModel(label,fee),tick_size=0.001,trade_start=start,trade_end=ccframe.index[-1])
        rows.append(summarize_save(key,run.equity_curve,run.trades,{"funding_status":"observed funding events only; coverage NOT verified","mark_status":"observed supplementary mark, snapshot hash and full current price alignment verified","ranking_eligible":False,"reason":"Spec/code execution timing ambiguous; separately labelled next-open audited implementation", "actual_fee":fee,"actual_slippage":0.0004},label))
    loader=importlib.import_module("replay_hype_cc_v35_oos_proxy_2026_06_29")
    legacy=loader._load_archive_replay_module()
    run=legacy.run_v35(ccframe,legacy.hype_v35_config(),trade_start=start,trade_end=ccframe.index[-1])
    eq=run.equity_curve.copy()
    trades=run.trades.copy()
    if float(run.weights.iloc[-1])!=0:
        allocation=abs(float(run.weights.iloc[-1]))
        eq.iloc[-1]*=1-allocation*0.00085
        active=run.weights.ne(0) & run.weights.shift(1).fillna(0).eq(0)
        entry=run.weights.index[active][-1]
        trades=pd.concat([trades,pd.DataFrame([{"entry_ts":entry,"exit_ts":ccframe.index[-1],"direction":int(np.sign(run.weights.iloc[-1])),"entry_price":ccframe.close.loc[entry],"exit_price":ccframe.close.iloc[-1],"allocation":allocation,"exit_reason":"terminal_mark","exit_equity":eq.iloc[-1]}])],ignore_index=True)
    rows.append(summarize_save(key,eq,trades,{"funding_status":"observed funding events only; coverage NOT verified","ranking_eligible":False,"reason":"Original code: signal-close entry, next-open early exit; differs from original written spec and later handoff","mark_status":"observed supplementary mark; not catalog trusted"},"original_code_close_entry"))
    return rows


def source_hashes() -> dict:
    result={}
    for name,module in list(sys.modules.items()):
        path=getattr(module,"__file__",None)
        if path and str(ROOT) in path and (name.startswith("research_hype") or name.startswith("compare_hype") or name.startswith("hype_v35_replay") or name.startswith("hype_legacy")):
            p=Path(path)
            result[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    for info in REGISTRATIONS.values():
        p=ROOT/"research/hype"/info["family"]/info["source"]
        result[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    for relative in ("archive/code/platform/src/strategy_lab/strategies/candle_count_short/intrabar_backtest.py", "archive/scripts/research/research_hype_v35_dry_run_recovery.py", "research/asset-portfolios/multi-legacy-post-registration-audit/scripts/hype_legacy_replay.py", "research/asset-portfolios/multi-legacy-post-registration-audit/scripts/hype_legacy_verify.py"):
        p=ROOT/relative
        result[relative]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--metadata-only",action="store_true")
    parser.add_argument("--only",choices=("ema_tb","ema_x","mii_ensemble","cc"))
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    enriched={}
    for key,info in REGISTRATIONS.items():
        source=ROOT/"research/hype"/info["family"]/info["source"]
        enriched[key]={**info,"source_path":str(source.relative_to(ROOT)),"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest()}
    enriched["HYPE-CC-V35"]["first_save_git_commit"]="78c0c724199db96727f5ddc65fb451d397e35c59"
    enriched["HYPE-CC-V35"]["first_save_git_path"]="docs/hype-v35-reproducible-params.md"
    write_json(OUT/"registrations.json",enriched)
    if args.metadata_only:
        return
    from audit_common import load_prices,load_funding
    frame=frame_with_index(load_prices("HYPE","15m"))
    events=funding_events(load_funding("HYPE"))
    rows=json.loads((OUT/"summary.json").read_text()) if args.only and (OUT/"summary.json").exists() else []
    for name,func in (("ema_tb",replay_tb),("ema_x",replay_x),("mii_ensemble",replay_mii_ensemble),("cc",replay_cc)):
        if args.only and name!=args.only:
            continue
        print(f"Running {name}",flush=True)
        new=func(frame,events)
        identities={(r["strategy"],r["variant"]) for r in new}
        rows=[r for r in rows if (r["strategy"],r["variant"]) not in identities]+new
        write_json(OUT/"summary.json",rows)
    previous=json.loads((OUT/"source_sha256.json").read_text()) if (OUT/"source_sha256.json").exists() else {}
    write_json(OUT/"source_sha256.json",{**previous,**source_hashes()})
    print(json.dumps([{k:r[k] for k in ("strategy","variant","return_pct","max_drawdown_pct","natural_closed_trades")} for r in rows],indent=2))


if __name__=="__main__":
    main()
