"""Predeclared HYPE-CC milestone comparison, 2026-09-11.

Diagnostic adapters: common next-open execution and fixed-quantity account.
Only iteration_common/audit_common supplies this turn's hash-checked API-derived
prices and funding events.
The supplementary mark snapshot is separately hash/price aligned, not trusted
catalog data. This script never modifies original strategy or runner files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from iteration_common import END, INPUTS, load_funding, load_prices

ROOT = Path(__file__).resolve().parents[4]
FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/iteration_comparison_20260911/cc"
CC = ROOT / "research/hype/15m-candle-count-reversal"
STEP = pd.Timedelta(minutes=15)
COMMON_START = pd.Timestamp("2026-07-23T00:00:00Z")
LONG_START = pd.Timestamp("2026-06-08T03:45:00Z")


@dataclass(frozen=True)
class Config:
    version: str
    allocation_atr: int
    stop_atr: int
    take_atr: int
    take_multiplier: float = 6.0
    min_take: float = .025
    max_take: float = .035
    trend_limit: float = .06
    target_atr: float = .004
    min_risk: float = .125
    early_three: bool = False
    counter: bool = False
    stop_multiplier: float = 5.0
    min_stop: float = .025
    max_stop: float = .035
    max_allocation: float = 3.0
    lookback: int = 10
    min_count: int = 8
    cooldown: int = 8
    opposite_gap: int = 8
    risk_decay: float = .5


CONFIGS = [
    Config("V10", 96, 288, 192, min_take=.020, max_take=.040),
    Config("V13", 288, 288, 288),
    Config("V18", 672, 672, 672, trend_limit=.05),
    Config("V21", 672, 672, 672, trend_limit=.05, early_three=True),
    Config("V35", 672, 672, 672, take_multiplier=5.5, min_take=.020,
           trend_limit=.05, target_atr=.006, min_risk=.0625,
           early_three=True, counter=True),
]
SOURCES = {
    "V10": ("specs/hype-v10-atr-dynamic-stop-strategy-spec.md", "b73b76a0e2524d70ad423f376a1c61b2646b20f9", "2026-05-15T12:01:13Z"),
    "V13": ("specs/hype-v13-strategy-spec.md", "b73b76a0e2524d70ad423f376a1c61b2646b20f9", "2026-05-15T12:01:13Z"),
    "V18": ("specs/hype-v18-atr672-strategy-spec.md", "e92a1fd02bcc1e3d6d6dbf33a7e91e0154580ef8", "2026-05-19T10:40:56Z"),
    "V21": ("specs/hype-v21-reproducible-params.md", "ff006d3cd4518d5d185660ba6274c645b44f9793", "2026-05-31T10:36:13Z"),
    "V35": ("specs/hype-v35-reproducible-params.md", "78c0c724199db96727f5ddc65fb451d397e35c59", "2026-06-08T03:36:54Z"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n")


def plan() -> dict:
    cases = []
    for c in CONFIGS:
        for name, size, slip in (("fixed1x", "fixed1x", .0004),
                                 ("original_size", "original_size", .0004),
                                 ("fixed1x_slip8bps", "fixed1x", .0008)):
            cases.append(dict(case_id=f"{c.version}__{name}", config=asdict(c),
                              scenario=name, size=size, fee=.001, slip=slip,
                              start=str(COMMON_START), end=str(END), window="common"))
        cases.append(dict(case_id=f"{c.version}__long_fixed1x", config=asdict(c),
                          scenario="long_fixed1x", size="fixed1x", fee=.001,
                          slip=.0004, start=str(LONG_START), end=str(END), window="long"))
    return dict(
        status="FROZEN_BEFORE_RESULTS", cases=cases,
        result_pair_per_case=["funding_excluded", "observed_funding_estimate"],
        initial_equity=10000, capital_model="fixed signed quantity during each trade; no rebalance",
        signal="last 10 closed bars including signal bar, >=8 same colour; not consecutive 8",
        causal_timing="signal close -> next bar open; early close decision -> next bar open",
        early_window="strict written spec: exclude actual execution bar; check only bars +1..+3 or +1..+12",
        intrabar_exit="mark high/low triggers; stop first if both; threshold fill with adverse slippage; adverse trade-open gap respected",
        trigger_fill_limitation="15m mark OHLC establishes touches only, not actual trigger time or exchange fill",
        cooldown="exclude exit bar and next 8 signal bars; no entry/exit same-bar re-entry",
        funding="charge held positions before opening-boundary exits; exclude new entries at same settlement; native mark where available else trade-open proxy, labelled estimate",
        primary="common window fixed1x: disabling dynamic size and risk decay isolates signal/exit changes; not exact original reproduction",
        original_size="all original volatility sizing and stop loss multipliers retained, but causal timing, fee/slippage and quantity accounting remain common diagnostics",
        terminal="flatten at last closed trade price, deduct adverse slip and fee; timestamp = end exclusive",
        no_tuning=True, historical_period_already_revealed=True,
        missing_earliest="V0-V9 have milestone summaries but no complete standalone frozen spec located; earliest full spec V10, not renamed V1",
    )


def freeze_plan() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    p = plan()
    pp = OUT / "cases_plan.json"
    if pp.exists():
        old = json.loads(pp.read_text())
        assert old["plan"] == p, "Cannot change predeclared cases after freeze"
        return
    sources = []
    for version, (relative, commit, ts) in SOURCES.items():
        path = CC / relative
        sources.append(dict(version=version, path=str(path.relative_to(ROOT)),
                            sha256=digest(path), earliest_file_save_commit=commit,
                            earliest_file_save_utc=ts,
                            git_is_latest_known_save_not_actual_research_origin=True))
    for path in (CC / "hype-cc-core-ledger.md", CC / "hype-cc-15m-milestone-comparison.md",
                 CC / "specs/hype-v21-bidirectional-opposite-three-exit-strategy-spec.md",
                 CC / "scripts/research_hype_cc_v35_maker_entry_audit.py",
                 ROOT / "archive/code/platform/src/strategy_lab/strategies/candle_count_short/intrabar_backtest.py",
                 ROOT / "archive/scripts/research/research_hype_v35_dry_run_recovery.py"):
        sources.append(dict(path=str(path.relative_to(ROOT)), sha256=digest(path)))
    write_json(OUT / "sources_manifest.json", {"sources": sources})
    write_json(pp, {"created_utc": datetime.now(timezone.utc).isoformat(), "plan": p})


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = load_prices("HYPE", "15m").copy()
    frame["ts"] = pd.to_datetime(frame.ts, utc=True)
    frame = frame.set_index("ts").sort_index()
    snapshot = CC / "artifacts/hype_cc_v35_maker_entry_input_2026-09-07.parquet"
    receipt_path = CC / "artifacts/hype_cc_v35_maker_entry_summary_2026-09-07.json"
    receipt = json.loads(receipt_path.read_text())
    assert digest(snapshot) == receipt["artifact_identity"]["input_snapshot_sha256"]
    old = pd.read_parquet(snapshot)
    if "ts" in old:
        old = old.set_index("ts")
    old.index = pd.to_datetime(old.index, utc=True)
    assert old.index.is_unique and frame.index.isin(old.index).all()
    old = old.loc[frame.index]
    delta = {col: float((frame[col] - old[col]).abs().max()) for col in ("open", "high", "low", "close", "volume")}
    assert max(delta.values()) <= 1e-9, delta
    for col in ("mark_high", "mark_low"):
        frame[col] = old[col]
    assert np.isfinite(frame[["mark_high", "mark_low"]]).all().all()
    assert (frame.mark_high >= frame.mark_low).all() and (frame.mark_low > 0).all()
    assert (frame.index.to_series().diff().dropna() == STEP).all()
    assert frame.index[-1] + STEP == END
    funding = load_funding("HYPE")
    funding["ts"] = pd.to_datetime(funding.ts, utc=True)
    offsets = funding.ts-funding.ts.dt.floor("15min")
    scoped_offsets = offsets[funding.ts.between(LONG_START, END, inclusive="left")]
    assert scoped_offsets.max() <= pd.Timedelta(seconds=2), "A later intrabar event needs a finer execution model"
    mark_col = next((x for x in ("mark_price", "markPrice") if x in funding), None)
    if mark_col:
        funding["settlement_mark"] = pd.to_numeric(funding[mark_col], errors="coerce")
    else:
        funding["settlement_mark"] = np.nan
    write_json(OUT / "input_verification.json", dict(
        status="PASS_PRICE_AND_AUX_MARK_ALIGNMENT_NOT_NET_VERIFIED",
        price_manifest=str((INPUTS / "manifest.json").relative_to(ROOT)),
        price_manifest_sha256=digest(INPUTS / "manifest.json"),
        supplemental_mark_snapshot=str(snapshot.relative_to(ROOT)),
        supplemental_mark_sha256=digest(snapshot), receipt_sha256=digest(receipt_path),
        price_max_differences=delta, price_rows=len(frame), missing_bars=0,
        mark_rows_missing=0, mark_catalog_trusted=False, funding_window_verified=False,
        funding_columns=list(funding),
        native_funding_max_offset_seconds=float(scoped_offsets.max().total_seconds()),
        native_funding_off_grid_count=int(scoped_offsets.gt(pd.Timedelta(0)).sum()),
        observed_funding_events_common=int(funding.ts.between(COMMON_START, END, inclusive="left").sum()),
        missing_native_settlement_mark_common=int((funding.ts.between(COMMON_START, END, inclusive="left") & funding.settlement_mark.isna()).sum()),
    ))
    return frame, funding


def features(frame: pd.DataFrame) -> pd.DataFrame:
    f = frame.copy()
    f["bull"] = f.close.gt(f.open).astype(int)
    f["bear"] = f.close.lt(f.open).astype(int)
    f["bull10"] = f.bull.rolling(10, min_periods=10).sum()
    f["bear10"] = f.bear.rolling(10, min_periods=10).sum()
    f["signal"] = np.where(f.bull10.ge(8), -1, np.where(f.bear10.ge(8), 1, 0))
    tr = pd.concat([f.high - f.low, (f.high-f.close.shift()).abs(), (f.low-f.close.shift()).abs()], axis=1).max(axis=1)
    for n in (96, 192, 288, 672):
        f[f"atr{n}"] = tr.rolling(n, min_periods=n).mean() / f.close
    f["trend96"] = f.close.pct_change(96, fill_method=None)
    return f


def early_reason(arrays: dict, c: Config, entry_index: int, i: int, direction: int) -> str | None:
    held_after_entry = i-entry_index
    if c.early_three and held_after_entry == 3:
        colour = "bear" if direction > 0 else "bull"
        if sum(arrays[colour][entry_index+1:i+1]) == 3:
            return "early_main"
    if c.counter and held_after_entry == 12:
        opposite = sum(arrays["bear" if direction > 0 else "bull"][entry_index+1:i+1])
        favourable = sum(arrays["bull" if direction > 0 else "bear"][entry_index+1:i+1])
        if opposite >= 9:
            return "early_counter_opposite"
        if favourable >= 9:
            return "early_counter_favorable"
    return None


def verify_spec_parameters() -> list[dict]:
    checks = []
    for c in CONFIGS:
        text = (CC / SOURCES[c.version][0]).read_text()
        params = {}
        for line in text.splitlines():
            if line.startswith("|"):
                parts = [p.strip().strip("`") for p in line.split("|")]
                if len(parts) >= 4:
                    try:
                        params[parts[1]] = float(parts[2])
                    except ValueError:
                        pass
        required = dict(lookback=c.lookback, min_count=c.min_count,
                        long_allocation=c.max_allocation, short_allocation=c.max_allocation,
                        allocation_atr_window=c.allocation_atr, target_atr_pct=c.target_atr,
                        stop_loss_atr_window=c.stop_atr, stop_loss_atr_multiplier=c.stop_multiplier,
                        min_stop_loss_pct=c.min_stop, max_stop_loss_pct=c.max_stop,
                        take_profit_atr_window=c.take_atr, take_profit_atr_multiplier=c.take_multiplier,
                        min_take_profit_pct=c.min_take, max_take_profit_pct=c.max_take,
                        trend_window_bars=96, trend_block_pct=c.trend_limit,
                        cooldown_bars=c.cooldown, opposite_signal_gap_bars=c.opposite_gap,
                        stop_loss_risk_multiplier=c.risk_decay, min_risk_multiplier=c.min_risk)
        for key, value in required.items():
            assert key in params and abs(params[key]-value) < 1e-12, (c.version,key,params.get(key),value)
        assert "close > open" in text and "close < open" in text
        if c.early_three:
            assert ("不包含开仓 K" in text or "不含开仓 K" in text)
        checks.append(dict(test="source_spec_parameter_equality", version=c.version,
                           checked_fields=required, status="PASS"))
    c = CONFIGS[-1]
    # Three bearish bars including actual fill bar must not cause early exit.
    arr = dict(bear=np.array([1,1,1,0]), bull=np.array([0,0,0,1]))
    assert early_reason(arr,c,0,2,1) is None
    assert early_reason(arr,c,0,3,1) is None
    arr = dict(bear=np.array([0,1,1,1]), bull=np.array([1,0,0,0]))
    assert early_reason(arr,c,0,3,1) == "early_main"
    assert early_reason(arr,c,0,3,-1) is None
    # Same rule must not turn into an arbitrary rolling three-bar stop.
    arr = dict(bear=np.array([0,0,1,1,1]), bull=np.array([1,1,0,0,0]))
    assert early_reason(arr,c,0,4,1) is None
    arr = dict(bear=np.array([1]+[1]*8+[0]*4), bull=np.array([0]+[0]*8+[1]*4))
    assert early_reason(arr,c,0,12,1) is None
    arr = dict(bear=np.array([0]+[1]*9+[0]*3), bull=np.array([1]+[0]*9+[1]*3))
    assert early_reason(arr,c,0,12,1) == "early_counter_opposite"
    assert early_reason(arr,c,0,12,-1) == "early_counter_favorable"
    checks.append(dict(test="early_exit_excludes_actual_entry_bar_and_only_frozen_window", status="PASS"))
    return checks


def replay(f: pd.DataFrame, funding: pd.DataFrame, case: dict, funded: bool,
           terminal: bool = True) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    c = Config(**case["config"])
    start, end = pd.Timestamp(case["start"]), pd.Timestamp(case["end"])
    a, z = int(f.index.searchsorted(start)), int(f.index.searchsorted(end))
    assert a < z and f.index[a] == start and f.index[z-1] + STEP == end
    arrays = {col: f[col].to_numpy() for col in f.columns if col in ("open", "high", "low", "close", "mark_high", "mark_low", "bull", "bear", "signal", "trend96", "atr96", "atr192", "atr288", "atr672")}
    funds = {}
    for r in funding.itertuples():
        if start <= r.ts < end:
            funds.setdefault(r.ts.floor("15min"), []).append(r)
    cash = 10000.0
    risk = 1.0
    position = None
    pending = None
    pending_exit = None
    cooldown_end = -1
    trades, curve, fundrows = [], [], []
    fee_total = slip_total = gross_total = funding_total = 0.0
    counters = {"raw_signal_bars": 0, "fresh_signal_bars": 0, "blocked_cooldown_or_position": 0,
                "blocked_opposite": 0, "blocked_trend": 0, "same_bar_stop_and_take": 0}

    def settle_event(event, i):
        nonlocal cash, funding_total
        if not funded or position is None:
            return
        native = float(event.settlement_mark)
        mark = native if np.isfinite(native) and native > 0 else float(arrays["open"][i])
        payment = -position["direction"] * position["quantity"] * mark * float(event.funding_rate)
        cash += payment
        funding_total += payment
        position["funding_pnl"] += payment
        fundrows.append(dict(ts=event.ts, entry_ts=position["entry_ts"], direction=position["direction"],
                             quantity=position["quantity"], funding_rate=float(event.funding_rate),
                             settlement_mark=mark, native_mark_available=bool(np.isfinite(native) and native > 0),
                             funding_pnl=payment, event_id=event.event_id,
                             order_assumption="exact boundary before open executions" if event.ts==f.index[i] else "native milliseconds after open executions before intrabar protective evaluation"))

    def exit_trade(i: int, reference: float, reason: str, timing: str):
        nonlocal cash, position, risk, cooldown_end, fee_total, slip_total, gross_total, pending_exit
        p = position
        d, qty = p["direction"], p["quantity"]
        fill = reference * (1 - d * case["slip"])
        fee = qty * fill * case["fee"]
        pnl = d * qty * (fill - p["entry_fill"])
        slip_cost = qty * abs(fill-reference)
        gross = d * qty * (reference-p["entry_reference"])
        cash += pnl - fee
        fee_total += fee
        slip_total += slip_cost
        gross_total += gross
        exit_ts = f.index[i] if timing == "open" else f.index[i] + STEP
        trade = {**p, "exit_bar_open": f.index[i], "exit_ts": exit_ts,
                 "exit_timing": timing, "exit_reference": reference, "exit_fill": fill,
                 "exit_fee": fee, "exit_slippage_quote": slip_cost,
                 "gross_pnl_before_slippage": gross, "price_pnl_after_slippage": pnl,
                 "net_pnl": pnl - p["entry_fee"] - fee + p["funding_pnl"],
                 "exit_equity": cash, "exit_reason": reason,
                 "return_on_entry_equity": (cash-p["entry_equity"])/p["entry_equity"],
                 "bars_held": i-p["entry_index"]+1}
        assert abs(trade["net_pnl"]-(cash-p["entry_equity"])) < 1e-7
        trades.append(trade)
        if reason == "stop":
            risk = max(c.min_risk, risk*c.risk_decay)
        elif reason == "take":
            risk = 1.0
        cooldown_end = i+c.cooldown
        position = None
        pending_exit = None

    curve.append(dict(ts=start, bar_open=pd.NaT, equity=cash, cash=cash, direction=0, quantity=0.,
                      unrealized_pnl=0., risk_multiplier=risk, terminal_adjustment=False))
    for i in range(a, z):
        ts = f.index[i]
        exited = False
        for event in funds.get(ts, []):
            if event.ts == ts:
                settle_event(event, i)
        if position is not None and pending_exit is not None:
            exit_trade(i, float(arrays["open"][i]), pending_exit, "open")
            exited = True
        if position is None and pending is not None:
            sig_i, d, sl, tp, base, alloc, risk_at_entry = pending
            reference = float(arrays["open"][i])
            fill = reference * (1 + d * case["slip"])
            qty = cash * alloc / fill
            fee = qty * fill * case["fee"]
            position = dict(direction=d, quantity=qty, entry_index=i, signal_bar_open=f.index[sig_i],
                            signal_close_ts=f.index[sig_i]+STEP, entry_ts=ts, entry_reference=reference,
                            entry_fill=fill, allocation=alloc, base_allocation=base, risk_at_entry=risk_at_entry,
                            entry_equity=cash, entry_fee=fee, entry_slippage_quote=qty*abs(fill-reference),
                            funding_pnl=0., stop_pct=sl, take_pct=tp,
                            stop_price=fill*(1-d*sl), take_price=fill*(1+d*tp))
            cash -= fee
            fee_total += fee
            slip_total += position["entry_slippage_quote"]
            pending = None
        for event in funds.get(ts, []):
            if event.ts > ts:
                settle_event(event, i)
        if position is not None:
            p = position
            d = p["direction"]
            mh, ml = arrays["mark_high"][i], arrays["mark_low"][i]
            stop_hit = ml <= p["stop_price"] if d > 0 else mh >= p["stop_price"]
            take_hit = mh >= p["take_price"] if d > 0 else ml <= p["take_price"]
            if stop_hit or take_hit:
                counters["same_bar_stop_and_take"] += int(stop_hit and take_hit)
                reason = "stop" if stop_hit else "take"
                reference = p["stop_price"] if stop_hit else p["take_price"]
                if stop_hit:
                    reference = min(reference, arrays["open"][i]) if d > 0 else max(reference, arrays["open"][i])
                exit_trade(i, float(reference), reason, "intrabar_unknown_valued_at_close")
                exited = True
            else:
                pending_exit = early_reason(arrays,c,p["entry_index"],i,d)
        sig = int(arrays["signal"][i])
        if sig:
            counters["raw_signal_bars"] += 1
        fresh = sig != 0 and sig != int(arrays["signal"][i-1])
        if fresh:
            counters["fresh_signal_bars"] += 1
            if position is not None or exited or i <= cooldown_end:
                counters["blocked_cooldown_or_position"] += 1
            elif -sig in arrays["signal"][i-c.opposite_gap:i]:
                counters["blocked_opposite"] += 1
            elif not np.isfinite(arrays["trend96"][i]) or sig*arrays["trend96"][i] < -c.trend_limit:
                counters["blocked_trend"] += 1
            elif i < z-1:
                atr_alloc = float(arrays[f"atr{c.allocation_atr}"][i])
                atr_sl = float(arrays[f"atr{c.stop_atr}"][i])
                atr_tp = float(arrays[f"atr{c.take_atr}"][i])
                assert min(atr_alloc, atr_sl, atr_tp) > 0
                base = min(c.max_allocation, c.max_allocation*c.target_atr/atr_alloc)
                alloc = 1. if case["size"] == "fixed1x" else base*risk
                sl = float(np.clip(atr_sl*c.stop_multiplier, c.min_stop, c.max_stop))
                tp = float(np.clip(atr_tp*c.take_multiplier, c.min_take, c.max_take))
                pending = (i, sig, sl, tp, base, alloc, risk)
        is_terminal = i == z-1 and position is not None and terminal
        if is_terminal:
            exit_trade(i, float(arrays["close"][i]), "terminal", "close")
        unrealized = 0. if position is None else position["direction"]*position["quantity"]*(arrays["close"][i]-position["entry_fill"])
        eq = cash + unrealized
        assert eq > 0 and np.isfinite(eq), "Account insolvency needs explicit liquidation model"
        curve.append(dict(ts=ts+STEP, bar_open=ts, equity=eq, cash=cash,
                          direction=0 if position is None else position["direction"],
                          quantity=0. if position is None else position["quantity"],
                          unrealized_pnl=unrealized, risk_multiplier=risk,
                          terminal_adjustment=bool(is_terminal)))
    curves = pd.DataFrame(curve)
    curves["return"] = curves.equity.pct_change().fillna(0.)
    curves["drawdown"] = curves.equity/curves.equity.cummax()-1
    tf = pd.DataFrame(trades)
    realized = sum(t["net_pnl"] for t in trades)
    cash_expected = 10000 + realized
    if position is not None:
        cash_expected += position["funding_pnl"]-position["entry_fee"]
    assert abs(cash_expected-cash) < 1e-7
    if terminal:
        assert position is None and abs(10000+realized-curves.equity.iloc[-1]) < 1e-7
        assert abs(10000+gross_total-fee_total-slip_total+funding_total-curves.equity.iloc[-1]) < 1e-7
    if len(tf):
        assert (tf.entry_ts == tf.signal_close_ts).all()
        assert (tf.entry_ts == tf.signal_bar_open+STEP).all()
        assert (tf.entry_ts >= start).all() and (tf.exit_ts <= end).all()
        if case["size"] == "fixed1x":
            assert tf.allocation.eq(1.).all()
    monthly = curves.loc[curves.bar_open.notna()].groupby(curves.loc[curves.bar_open.notna(), "bar_open"].dt.strftime("%Y-%m"))["return"].apply(lambda s: (1+s).prod()-1)
    assert abs((1+monthly).prod()*10000-curves.equity.iloc[-1]) < 1e-7
    parts = {}
    for n in (15, 30):
        boundary = start+pd.Timedelta(days=n)
        if boundary < end:
            mid = float(curves.loc[curves.ts <= boundary, "equity"].iloc[-1])
            parts[f"first_{n}d_return_pct"] = (mid/10000-1)*100
            parts[f"after_{n}d_return_pct"] = (curves.equity.iloc[-1]/mid-1)*100
    summary = dict(case_id=case["case_id"], family="HYPE-CC", strategy=f"HYPE-CC-{c.version}", version=c.version,
                   role="early_complete_spec" if c.version=="V10" else "final" if c.version=="V35" else "milestone",
                   scenario=case["scenario"], window=case["window"], start=str(start), end=str(end),
                   funding_mode="observed_funding_estimate" if funded else "funding_excluded",
                   return_pct=(curves.equity.iloc[-1]/10000-1)*100,
                   max_drawdown_pct=-curves.drawdown.min()*100,
                   trades=len(trades), natural_trades=sum(t["exit_reason"]!="terminal" for t in trades),
                   terminal_trades=sum(t["exit_reason"]=="terminal" for t in trades),
                   long_trades=sum(t["direction"]==1 for t in trades), short_trades=sum(t["direction"]==-1 for t in trades),
                   net_wins=sum(t["net_pnl"]>0 for t in trades),
                   gross_pnl_before_cost_quote=gross_total, fee_quote=fee_total,
                   slippage_quote=slip_total, funding_pnl_quote=funding_total,
                   observed_settlement_events_held=len(fundrows),
                   held_events_without_native_mark=sum(not r["native_mark_available"] for r in fundrows),
                   average_entry_allocation=float(tf.allocation.mean()) if len(tf) else 0.,
                   exit_mix=tf.exit_reason.value_counts().to_dict() if len(tf) else {},
                   counters=counters, fee_rate=case["fee"], adverse_slip_rate=case["slip"],
                   monthly_return_pct=(monthly*100).to_dict(), **parts,
                   validation_account_arithmetic=True, equity_timestamp_semantics="valuation_time_bar_close",
                   drawdown_method="15m closing account equity including intrabar exits; not high frequency maximum")
    return summary, curves, tf, pd.DataFrame(fundrows)


def verify_features(f: pd.DataFrame) -> list[dict]:
    tests = []
    rawcols = ["open", "high", "low", "close", "volume", "mark_high", "mark_low"]
    featurecols = ["signal", "bull10", "bear10", "atr96", "atr192", "atr288", "atr672", "trend96"]
    for ts in (pd.Timestamp("2026-08-05T00:00Z"), pd.Timestamp("2026-08-23T00:00Z")):
        short = features(f.loc[f.index < ts, rawcols])
        pd.testing.assert_frame_equal(short[featurecols], f.loc[short.index, featurecols])
        tests.append(dict(test="feature_prefix", cutoff=str(ts), status="PASS"))
    # The user's phrase must mean >=8, not exactly 8 or eight consecutive.
    tiny = pd.DataFrame({"open": [1.]*10, "close": [2.,2.,0.,2.,2.,0.,2.,2.,2.,2.], "high": [2.]*10, "low": [0.]*10})
    assert int(features(tiny).signal.iloc[-1]) == -1
    tiny.loc[2, "close"] = 2.
    assert int(features(tiny).signal.iloc[-1]) == -1
    tiny.loc[[0,1], "close"] = 1.
    assert int(features(tiny).signal.iloc[-1]) == 0
    tests.append(dict(test="nonconsecutive_8_and_9_and_doji_signal", status="PASS"))
    return tests


def report(rows: list[dict]) -> None:
    def table(window, scenario):
        ss = [r for r in rows if r["window"]==window and r["scenario"]==scenario and r["funding_mode"]=="observed_funding_estimate"]
        lines = ["|版本|收益估计|不含资金费收益|最大回撤|交易数（多/空）|手续费+滑点|", "|---|---:|---:|---:|---:|---:|"]
        for r in ss:
            p = next(x for x in rows if x["case_id"]==r["case_id"] and x["funding_mode"]=="funding_excluded")
            lines.append(f"|{r['version']}|{r['return_pct']:+.2f}%|{p['return_pct']:+.2f}%|{r['max_drawdown_pct']:.2f}%|{r['trades']}（{r['long_trades']}/{r['short_trades']}）|{r['fee_quote']+r['slippage_quote']:.2f} USDT|")
        return "\n".join(lines)
    text = """# HYPE 15分钟「10根里8根同色反转」早期版与最终版比较

**这条策略不是越早越好，也不是版本越多越好。** 最近共同窗口内，中期 V18/V21 比早期 V10/V13 好；继续叠加到 V35 后，统一仓位收益却从 V21 的约9.77%降到约0.52%。V35在滑点加倍后转为约-0.72%，保留原动态仓位但统一成本时为约-3.58%。较早的改动在这段历史上改善了表现，后期增加的止盈/提前退出组合没有继续改善。

**但把窗口延长到V35最晚已落档之后，五个版本全部亏损约25%–44%。** 所以回退V21不能据此当成恢复盈利的方法；它只是最近一个多月比V35好。V21→V35同时改了止盈和counter退出等规则，本轮比较不能将差异单独归到某一个参数，更不能从这一段直接证明过拟合是唯一原因。

本轮在查看结果前选定 V10、V13、V18、V21、V35。V10 是目前找到的最早完整独立规格；V0–V9 只在里程碑里有摘要，不能将本次 V10 称为最原始 V1。所有结果均为已经看过历史的诊断，不是新的盲测，也不改变 runner 状态。

## 这条策略到底怎么交易

最近 **10 根已经收盘的15分钟K线，至少8根同色**才产生信号。8、9、10根均满足；这8根不必连续。阳线按 close>open 判断，阴线按 close<open；十字线两边都不计。阳线多就做空，阴线多就做多。它是在赌一段密集上涨或下跌后的反转，不是突破追涨。

只在信号刚出现时考虑入场。同一方向连续出现不重复进场；过去8根出现过反向信号也不进场。已有持仓时不加仓、不反手。平仓后的8根K线继续禁止产生入场订单。V10/V13 在过去24小时涨超6%时不做空、跌超6%时不做多；V18以后把门槛改成5%。

止损止盈在入场时确定，之后不移动。V10 仓位用 ATR96、止盈用 ATR192×6 并限制2%–4%、止损用 ATR288×5并限制2.5%–3.5%；V13全部改用 ATR288，止盈止损范围均为2.5%–3.5%；V18全部改 ATR672（7天平均真实波幅）。V21额外检查实际开仓K之后的前3根：若全部反向，下一根开盘平仓。**只检查这一组，不是持仓后每出现任意3连阴/阳都退出。** V35保留此规则，并在开仓K之后前12根里至少9根同向或反向时提前退出；止盈改为5.5ATR、下限改2%。

原始动态仓位为 `min(3, 3×目标ATR百分比/实际ATR百分比)×风险倍率`。V10至V21目标为0.4%，V35为0.6%。每次普通止损后倍率减半，V10至V21最低12.5%，V35最低6.25%；普通止盈后恢复1；提前退出不恢复也不减半。

## 同段比较：统一每次1倍账户名义仓位

2026-07-23 00:00 至 2026-09-05 15:00 UTC，初始10000 USDT，从空仓开始。所有版本每次成交手续费0.1%、价格向不利方向滑点0.04%。主表禁用动态仓位和连续止损减仓，专门比较交易规则的变化。1倍是名义仓位，不是每笔止损风险相同；各版止盈止损距离保持原规则。信号闭合后下一根开盘入场，提前退出也是下一根开盘执行。回撤用15分钟收盘账户权益计算，包括该根已发生的保护单退出，不能当作高频逐笔最大回撤。

""" + table("common", "fixed1x") + """

## 保留各版原仓位，仍使用相同成本与因果执行

这张表反映仓位变化的影响，不能替代上面的统一仓位比较。全部按实际成交数量持仓，不使用旧引擎每根K隐含再平衡的复利算法。

""" + table("common", "original_size") + """

## 滑点提高到每次0.08%，仍为1倍仓位

""" + table("common", "fixed1x_slip8bps") + """

滑点变化也会改变实际开仓价，进而改变以开仓价为基准的止盈止损触发和下一次入场。因此压力情景不是只从原路径扣一笔费用，交易数可能变化；V10压力情景亏损略小是路径变化，不能解释为成本越高越有利。

## 较长补充：V35最晚已落档后的共同历史

五个版本都从2026-06-08 03:45 UTC开始，截止同上，统一1倍仓位。起点由V35第一次可核验落档时间03:36:54后的完整15分钟网格确定；Git提交只证明最晚在该时刻已有文档，不证明真正开始研究的时间。这一补充窗口也在回放前固定。

""" + table("long", "long_fixed1x") + """

## 复现限制与核对

- 原文和旧脚本对 close/next-open 有冲突。本轮统一闭合信号下一根open，V21/V35提前退出窗口严格排除实际成交K。昨日maker适配器窗口包含实际成交K，且提前退出按当前close，因此本轮数值不能当作昨日结果的逐笔复现。
- 本轮重新通过正式价格启动检查，使用本轮接口返回且SHA固定的全部预热历史，价格与昨日逐值一致。标记价格是单独留存的观察数据，其SHA、与价格快照全部OHLCV一一对齐已复核；它不是新发布的受信任目录输入。使用mark高低触发、止损优先，遇成交价开盘已跨过止损时按更差的开盘价格加滑点。15分钟高低价仍不能还原真实成交时刻与交易所成交。
- 资金费仅计入已有原生事件；有原生结算mark时使用，缺mark时用该时点成交开盘价估算。恰在开盘边界的事件先结算旧仓，然后处理开盘退出/入场，新仓不付该事件。原生时间在开盘后数毫秒的事件则保留真实时间，在开盘退出/入场之后结算，不把时间抹平。该根盘中mark保护单放在这些毫秒事件之后检查；15分钟K无法核实两者精确顺序，仍属估计。历史应有事件日历和PIT身份未完整证明，故另列完全不含资金费结果。
- 期末按最后完整收盘价平仓并扣滑点手续费。每条净值记录是实际估值时刻；月收益按本根K所在月份归属，避免把月底最后一根移到次月。
- 保存每组逐笔成交、持仓数量/现金/浮盈净值、资金费明细和月表；逐笔损益与账户、总毛利润减费用加资金费、月收益复利均须相等。另做历史截断重算，已发生交易和净值不得改变。

结果文件：[全部结果](results.csv)、[方案与参数](cases_plan.json)、[规格来源](sources_manifest.json)、[输入核对](input_verification.json)、[因果与算术检查](verification.json)。
"""
    (OUT / "report.md").write_text(text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args()
    freeze_plan()
    if args.plan_only:
        print("Frozen cases_plan.json and sources_manifest.json; no replay executed.")
        return
    for source in json.loads((OUT / "sources_manifest.json").read_text())["sources"]:
        assert digest(ROOT/source["path"]) == source["sha256"], source
    amendment_path = OUT/"execution_clarification_01.json"
    if not amendment_path.exists():
        write_json(amendment_path, dict(created_utc=datetime.now(timezone.utc).isoformat(), before_first_results=True,
            reason="Input validation found native funding timestamps milliseconds after bar opens; do not round them into simultaneous opening events",
            handling="exact boundary settles old position before open executions; native +milliseconds after open executions, before unknown intrabar protective execution; save raw event_id/time; no rate/event merge",
            limitation="15m mark OHLC cannot prove event-versus-barrier execution sequence; estimated funding only",
            cases_parameters_changed=False, original_plan_sha256=digest(OUT/"cases_plan.json")))
    frame, funding = load_inputs()
    f = features(frame)
    checks = verify_spec_parameters() + verify_features(f)
    results = []
    for case in plan()["cases"]:
        for funded in (False, True):
            result, curve, trades, fundrows = replay(f, funding, case, funded)
            tag = case["case_id"] + ("__funding_estimate" if funded else "__no_funding")
            result["equity_file"] = str((OUT/f"{tag}_equity.csv").relative_to(ROOT))
            result["trades_file"] = str((OUT/f"{tag}_trades.csv").relative_to(ROOT))
            result["monthly_path"] = str((OUT/f"{tag}_monthly.csv").relative_to(ROOT))
            result["equity_path"] = result["equity_file"]
            result["trades_path"] = result["trades_file"]
            curve.to_csv(OUT/f"{tag}_equity.csv", index=False)
            trades.to_csv(OUT/f"{tag}_trades.csv", index=False)
            fundrows.to_csv(OUT/f"{tag}_funding.csv", index=False)
            pd.Series(result["monthly_return_pct"], name="return_pct").to_csv(OUT/f"{tag}_monthly.csv", index_label="month")
            write_json(OUT/f"{tag}_summary.json", result)
            results.append(result)
            # Prefix run must not liquidate at its artificial cutoff.
            cutoff = pd.Timestamp("2026-08-15T00:00Z")
            subcase = {**case, "end": str(cutoff)}
            sf = features(frame.loc[frame.index < cutoff])
            _, sc, st, _ = replay(sf, funding[funding.ts < cutoff], subcase, funded, terminal=False)
            fullprefix = curve[curve.ts <= cutoff].reset_index(drop=True)
            pd.testing.assert_frame_equal(sc.reset_index(drop=True), fullprefix, check_exact=False, atol=1e-10, rtol=1e-12)
            fulltrades = trades[(trades.exit_ts < cutoff) | ((trades.exit_ts == cutoff) & (trades.exit_timing != "open"))].reset_index(drop=True)
            pd.testing.assert_frame_equal(st.reset_index(drop=True), fulltrades, check_exact=False, atol=1e-9, rtol=1e-12)
            checks.append(dict(case_id=case["case_id"], funding_mode=result["funding_mode"], prefix_cutoff=str(cutoff),
                               status="PASS", price_feature_and_equity_prefix=True,
                               terminal_account_trade_monthly_arithmetic=True))
            print(tag, f"{result['return_pct']:+.4f}%", result["trades"], flush=True)
    # Sizing changes cannot alter the signal/exit path in this one-position engine.
    identity_cols = ["signal_bar_open", "entry_ts", "entry_reference", "entry_fill", "stop_price", "take_price", "exit_bar_open", "exit_ts", "exit_reference", "exit_fill", "direction", "exit_reason"]
    for c in CONFIGS:
        for funding_mode in ("funding_excluded", "observed_funding_estimate"):
            fixed = next(r for r in results if r["version"]==c.version and r["scenario"]=="fixed1x" and r["funding_mode"]==funding_mode)
            original = next(r for r in results if r["version"]==c.version and r["scenario"]=="original_size" and r["funding_mode"]==funding_mode)
            pd.testing.assert_frame_equal(pd.read_csv(ROOT/fixed["trades_path"])[identity_cols],
                                          pd.read_csv(ROOT/original["trades_path"])[identity_cols])
            checks.append(dict(test="sizing_only_preserves_signal_and_exit_identity", version=c.version, funding_mode=funding_mode, status="PASS"))
    combined = []
    for case in plan()["cases"]:
        ex = next(r for r in results if r["case_id"]==case["case_id"] and r["funding_mode"]=="funding_excluded")
        est = next(r for r in results if r["case_id"]==case["case_id"] and r["funding_mode"]=="observed_funding_estimate")
        combined.append({**est, "return_ex_funding": ex["return_pct"], "return_estimated_funding": est["return_pct"],
                         "max_drawdown": est["max_drawdown_pct"], "return_units":"percent", "ex_funding_equity_path":ex["equity_path"]})
    write_json(OUT/"comparison_summary.json", combined)
    pd.DataFrame(combined).to_csv(OUT/"comparison_summary.csv", index=False)
    write_json(OUT/"results.json", results)
    pd.DataFrame(results).to_csv(OUT/"results.csv", index=False)
    write_json(OUT/"verification.json", dict(status="PASS", cases=len(plan()["cases"]), runs=len(results), checks=checks,
                                             frozen_plan_sha256=digest(OUT/"cases_plan.json"),
                                             script_sha256=digest(Path(__file__))))
    report(results)
    write_json(OUT/"output_sha256.json", {str(p.relative_to(OUT)):digest(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "output_sha256.json"})


if __name__ == "__main__":
    main()
