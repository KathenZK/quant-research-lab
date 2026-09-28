"""Independent retained-ledger audit of V3/S1/S2/S3 and fixed-entry pairs.

Imports only prior independent auditing utilities, never a strategy simulator.
Reconstructs the new states from closed prices and entry reference. Reuses the
pinned prior monetary/event audit with its stop checker replaced in memory.
No frozen source file is edited, and no historical baseline is simulated.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from types import SimpleNamespace
import time
import traceback

import numpy as np
import pandas as pd

import audit_results as prior
import audit_four_tests_20260910 as money

LAB, FAMILY, DAY, HOUR = prior.LAB, prior.FAMILY, prior.DAY, prior.HOUR
ROUND = FAMILY / "artifacts/state_machine_20260910"
RESULTS = ROUND / "results_current"
INPUTS = FAMILY / "artifacts/inputs_20260909"
ORIGINAL = FAMILY / "artifacts/results_20260909"
BASE_MONEY_SHA = "2da134653f63c06d621e2b66bb1fdd566c879192690d9bf3eaf31a24f93ef920"
BASE_INPUT_AUDIT_SHA = "f376e8560d724a039dc5612962ce719602dc2e21157683ed6f8c177e5a1d9dc1"
INPUT_SHA = "a2390b002883506a8f39522a31e708e76346e21be6a0a598e753b4a5b5e4891c"
ORIGINAL_MANIFEST_SHA = "880d7201b4c23695265d80d2704e0ec03245dfdb8a274b50873f82fbfb50a13d"
sha, equal, read_json = prior.sha, prior.equal, prior.read_json
BASE_STOP_CHECKER = money.audit_stop_path


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False) + "\n")


def read_frame(path):
    result = prior.read_frame(path)
    for column in ("first_arm_day", "sm_watch_start", "sm_protect_day", "baseline_exit_time"):
        if column in result:
            result[column] = pd.to_datetime(result[column], utc=True, format="mixed").dt.as_unit("ns")
    return result


@dataclass
class ClosedState:
    """Small independent mathematical state, not an account or order engine."""
    side: int
    entry_reference: float
    entry_fill: float
    policy: str
    closes: list = field(default_factory=list)
    held: int = 0
    phase: str = "NORMAL"
    began: pd.Timestamp | None = None
    watch_atr: float | None = None
    watch_extreme: float | None = None
    peak_speed: float | None = None
    protect_day: pd.Timestamp | None = None
    defense_days: int = 0
    healthy_days: int = 0
    protect_days: int = 0

    def observe(self, day, trade_extreme, stale_days):
        s, a, c = self.side, float(day.atr), float(day.close)
        assert a > 0 and math.isfinite(a)
        if not self.closes:
            self.closes = [self.entry_reference]
        self.closes.append(c)
        self.closes = self.closes[-4:]
        self.held += 1
        ready = self.held >= 3
        moves = [self.closes[i+1] - self.closes[i] for i in range(len(self.closes)-1)]
        # np.sum order matches the explicit three-segment mathematical sum;
        # all prices were independently checked against the frozen input.
        signed_move = s * float(np.asarray(moves).sum())
        total_distance = float(np.abs(np.asarray(moves)).sum())
        eff = (signed_move / total_distance if total_distance else 0.) if ready else float("nan")
        speed3 = signed_move / a if ready else float("nan")
        retrace = s * (trade_extreme - c) / a
        floating_price = s * (c - self.entry_fill)
        distance_ma = s * (c - float(day.ma)) / a
        speed1 = s * float(day.audit_delta) / float(day.audit_prior_atr)
        speed0 = s * float(day.audit_prior_delta) / float(day.audit_prior2_atr)
        failed = distance_ma <= 0 and floating_price <= 0
        back = retrace >= 1.25
        chopped = ready and eff <= .2 and stale_days >= 3 and floating_price <= 0
        defensive = failed or back or chopped
        healthy = ready and eff >= .6 and speed3 >= .5 and distance_ma > 0 and retrace <= .75
        rsi_extreme = float(day.rsi) >= 80 if s == 1 else float(day.rsi) <= 20
        accelerated = (speed1 >= 1 and speed1 > max(speed0, 0)) or (ready and speed3 >= 2 and eff >= .6)
        extended = distance_ma >= 2 or rsi_extreme
        observed = float(day.high if s == 1 else day.low)
        event = "unchanged"
        if self.policy == "extension":
            if self.phase == "NORMAL":
                if accelerated and extended:
                    self.phase, self.began = "WATCH", day.timestamp
                    self.watch_atr, self.watch_extreme = a, observed
                    self.peak_speed = max(s * float(day.audit_delta) / a, 0.)
                    event = "watch_started"
            else:
                self.watch_extreme = (max if s == 1 else min)(self.watch_extreme, observed)
                velocity = s * float(day.audit_delta) / self.watch_atr
                self.peak_speed = max(self.peak_speed, velocity)
                draw = s * (self.watch_extreme - c) / self.watch_atr
                if self.phase == "WATCH":
                    if velocity <= self.peak_speed / 2 and draw >= .75:
                        self.phase, self.protect_day, event = "PROTECT", day.timestamp, "exhaustion_protect"
                    elif distance_ma < 2 and not rsi_extreme:
                        self.phase, event = "NORMAL", "watch_cleared"
                        self.began = self.watch_atr = self.watch_extreme = self.peak_speed = None
        protecting = self.phase == "PROTECT"
        choices = [(protecting, "PROTECT"), (defensive, "DEFENSE"),
                   (self.phase == "WATCH", "WATCH"), (healthy, "HEALTHY"), (not ready, "PROBE")]
        state = next((name for active, name in choices if active), "ORDINARY")
        self.defense_days += int(defensive)
        self.healthy_days += int(healthy)
        self.protect_days += int(protecting)
        return {"sm_state": state, "sm_transition": event, "sm_held_days": self.held,
                "sm_ready3": bool(ready), "sm_flat3": bool(ready and total_distance == 0),
                "sm_efficiency3": eff, "sm_speed3": speed3, "sm_speed1": speed1,
                "sm_speed0": speed0, "sm_retrace_atr": retrace, "sm_ma_distance": distance_ma,
                "sm_failed_cross": bool(failed), "sm_large_retrace": bool(back),
                "sm_chopped": bool(chopped), "sm_defense": bool(defensive), "sm_healthy": bool(healthy),
                "sm_acceleration": bool(accelerated), "sm_extended": bool(extended),
                "sm_watch": self.phase, "sm_protect": bool(protecting), "sm_watch_start": self.began,
                "sm_watch_atr": self.watch_atr, "sm_watch_extreme": self.watch_extreme,
                "sm_peak_speed": self.peak_speed,
                "sm_defensive_stop": c - s * .5 * a if defensive else None,
                "sm_protection_stop": self.watch_extreme - s * self.watch_atr if protecting else None}


def add_causal_audit_features(daily):
    daily = daily.copy()
    daily["ma30"] = daily.close.rolling(30).mean()
    daily["prev_ma30"] = daily.ma30.shift()
    daily["audit_delta"] = daily.close.diff()
    daily["audit_prior_delta"] = daily.audit_delta.shift()
    daily["audit_prior_atr"] = daily.atr.shift()
    daily["audit_prior2_atr"] = daily.atr.shift(2)
    return daily


def audit_stop_path(trade, records, daily, summary):
    policy = summary["exit_state_policy"]
    if policy == "v3":
        BASE_STOP_CHECKER(trade, records, daily, summary)
        return
    assert policy in {"defense", "trend", "extension"}
    assert summary["progress_days"] == 4 and summary["progress_source"] == "high_low"
    assert summary["progress_policy"] == "permanent" and summary["stop_anchor"] == "ma"
    assert summary["delay_hours"] == 0 and summary["entry_wait_days"] == 0
    side = int(trade.side)
    signal = daily.loc[trade.signal_day]
    initial = float(signal.ma - side * 1.5 * signal.atr)
    equal(trade.initial_stop, initial, "initial stop from pre-entry day")
    equal(trade.uncapped_initial_stop, initial, "uncapped initial")
    equal(trade.entry_atr, signal.atr, "entry ATR")
    assert not trade.cap_applied
    end = pd.Timestamp(summary["end_exclusive"])
    dates = pd.date_range(trade.entry_time + DAY, trade.exit_time.floor("D"), freq="D")
    dates = dates[dates < end]
    assert records.timestamp.tolist() == [trade.entry_time, *dates], "State update dates differ"
    first = records.iloc[0]
    for field, target in {"old_stop": initial, "new_stop": initial, "old_mult": 1.5, "new_mult": 1.5,
                           "old_armed": False, "new_armed": False, "tightened": False,
                           "initialized": False, "full_holding_day": False,
                           "tightening_trigger": "entry"}.items():
        equal(getattr(first, field), target, "initial state " + field)
    if "sm_held_days" in records:
        assert pd.isna(first.sm_held_days), "Entry counted as completed holding day"
    old_stop, mult, armed = initial, 1.5, False
    extreme = extreme_day = arm_day = None
    count, decreases = 0, 0
    state = ClosedState(side, float(trade.entry_reference), float(trade.entry_price), policy)
    last_snapshot = None
    for i, actual in enumerate(records.iloc[1:].itertuples(index=False)):
        assert actual.timestamp == actual.signal_day + DAY
        assert actual.signal_day >= trade.entry_time
        day = daily.loc[actual.signal_day]
        natural = float(day.ma - side * mult * day.atr)
        for field, target in {"old_stop": old_stop, "old_mult": mult, "old_armed": armed,
                               "natural_candidate": natural,
                               "stalled": side * (natural - old_stop) <= 1e-12 * max(1., abs(old_stop))}.items():
            equal(getattr(actual, field), target, "previous stop " + field)
        observed = float(day.high if side == 1 else day.low)
        was_armed = armed
        if i == 0:
            extreme, extreme_day, count, refreshed = observed, actual.signal_day, 0, True
            normal_trigger, decrease = "extreme_initialize", False
        else:
            refreshed = side * (observed - extreme) > 0
            if refreshed:
                extreme, extreme_day, count = observed, actual.signal_day, 0
            else:
                count += 1
            if not armed and count >= 4:
                armed, arm_day = True, actual.signal_day
            decrease = armed and mult > .5
            normal_trigger = ("at_floor" if mult <= .5 else
                              ("progress_armed_daily" if was_armed else "no_new_extreme") if armed
                              else "progress_observed")
        snapshot = state.observe(day, extreme, count)
        trigger = normal_trigger
        if snapshot["sm_defense"] or snapshot["sm_protect"]:
            decrease = mult > .5
            trigger = "state_protect" if snapshot["sm_protect"] else "state_defense"
        elif policy in {"trend", "extension"} and snapshot["sm_healthy"]:
            decrease, trigger = False, "healthy_pause"
        if decrease:
            mult = max(.5, round(mult - .2, 10))
            decreases += 1
        candidates = [old_stop, float(day.ma - side * mult * day.atr)]
        candidates += [snapshot[x] for x in ("sm_defensive_stop", "sm_protection_stop") if snapshot[x] is not None]
        stop = (max if side == 1 else min)(candidates)
        expected = {"new_stop": stop, "new_mult": mult, "new_armed": armed, "initialized": True,
                    "extreme_price": extreme, "extreme_day": extreme_day, "arm_day": arm_day,
                    "new_extreme": refreshed, "no_new_extreme_days": count, "tightened": decrease,
                    "full_holding_day": True, "armed_reset": False, "ever_armed": armed,
                    "first_arm_day": arm_day, "arm_count": int(armed), "reset_count": 0,
                    "progress_policy": "permanent", "tightening_trigger": trigger,
                    "anchor_candidate": None, "anchor_decisive": False, **snapshot}
        for field, target in expected.items():
            equal(getattr(actual, field), target, "state record " + field)
        assert side * (stop - old_stop) >= 0 and .5 <= mult <= float(actual.old_mult) <= 1.5
        old_stop, last_snapshot = stop, snapshot
    final = {"stop": old_stop, "stop_mult": mult, "armed": armed, "initialized": bool(len(records) > 1),
             "extreme_price": extreme, "extreme_day": extreme_day, "arm_day": arm_day,
             "no_new_extreme_days": count, "tightening_days": decreases, "stop_floor_reached": mult == .5,
             "ever_armed": armed, "first_arm_day": arm_day, "arm_count": int(armed), "reset_count": 0,
             "anchor_decisive_days": 0}
    if last_snapshot:
        final.update(sm_state=last_snapshot["sm_state"], sm_held_days=state.held,
                     sm_defense_days=state.defense_days, sm_healthy_days=state.healthy_days,
                     sm_protect_days=state.protect_days)
        if policy == "extension":
            final.update(sm_watch=state.phase)
            for name in ("sm_watch_start", "sm_watch_atr", "sm_watch_extreme", "sm_peak_speed"):
                final[name] = last_snapshot[name]
            if state.protect_day is not None:
                final["sm_protect_day"] = state.protect_day
    for field, target in final.items():
        # A trade which never entered WATCH has no optional WATCH fields in
        # the engine's position dictionary; CSV union may supply NaN instead.
        actual = getattr(trade, field, None) if field.startswith("sm_") and target is None else getattr(trade, field)
        equal(actual, target, "final state " + field)


def extra_stats(summary, trades):
    pnl = trades.net_pnl if len(trades) else pd.Series(dtype=float)
    wins, losses = pnl[pnl > 0], -pnl[pnl < 0]
    targets = {"profit_factor": float(wins.sum() / losses.sum()) if len(losses) else None,
               "terminal_trades": int(trades.exit_reason.eq("sample_end").sum()) if len(trades) else 0,
               "average_win": float(wins.mean()) if len(wins) else None,
               "average_loss": float(losses.mean()) if len(losses) else None,
               "payoff_ratio": float(wins.mean() / losses.mean()) if len(wins) and len(losses) else None,
               "expectancy_cash": float(pnl.mean()) if len(pnl) else None,
               "worst_trade_pct": float(trades.return_on_entry_equity.min() * 100) if len(trades) else None,
               "top5_winners_share_pct": float(wins.nlargest(5).sum() / wins.sum() * 100) if len(wins) else None}
    if len(trades):
        targets["average_trade_pct"] = float(trades.return_on_entry_equity.mean() * 100)
    for name, target in targets.items():
        equal(summary[name], target, "extra statistic " + name)
    for side, label in [(1, "long"), (-1, "short")]:
        g = trades.loc[trades.side == side] if len(trades) else trades
        equal(summary[label + "_wins"], int(g.net_pnl.gt(0).sum()) if len(g) else 0, "direction wins")


def audit_continuous(directory, daily, hourly, carry=0.):
    # Inject into a prior independent checker, not the backtest engine. Each
    # worker is one process; restoration prevents unintended later reuse.
    previous = money.audit_stop_path
    money.audit_stop_path = audit_stop_path
    try:
        result = money.audit_run(directory, daily, hourly, carry)
    finally:
        money.audit_stop_path = previous
    summary, trades = read_json(directory / "summary.json"), read_frame(directory / "trades.csv")
    extra_stats(summary, trades)
    return result


def audit_fixed_trade(trade, base, records, daily, hourly, cfg, global_end):
    for name in ("entry_time", "entry_reference", "entry_price", "entry_equity", "entry_fee", "qty", "side", "initial_stop"):
        assert getattr(trade, name) == getattr(base, name), "Fixed entry changed: " + name
    equal(trade.source_trade_id, base.trade_id, "source entry identifier")
    equal(trade.trade_id, 1, "independent episode trade identifier")
    side, fee, slip = int(trade.side), float(cfg["fee"]), float(cfg["slip"])
    assert trade.entry_time <= trade.exit_time <= global_end
    sig = daily.loc[trade.entry_time - DAY]
    assert bool(sig.ready) and int(sig.cross) == side and side * sig.slope > cfg["slope"]
    equal(trade.signal_day, sig.timestamp, "fixed signal close")
    equal(trade.entry_reference, hourly.loc[trade.entry_time, "open"], "fixed open price")
    equal(trade.entry_price, trade.entry_reference * (1 + side * slip), "fixed entry slippage")
    equal(trade.exit_price, trade.exit_reference * (1 - side * slip), "fixed exit slippage")
    money.audit_quantity(trade, cfg, float(base.entry_equity))
    equal(trade.entry_fee, trade.qty * trade.entry_price * fee, "fixed entry fee")
    equal(trade.exit_fee, trade.qty * trade.exit_price * fee, "fixed exit fee")
    equal(trade.carry_paid, 0., "fixed carry")
    equal(trade.funding_paid, 0., "fixed funding not imputed")
    gross = side * trade.qty * (trade.exit_price - trade.entry_price)
    net = gross - trade.entry_fee - trade.exit_fee
    equal(trade.gross_pnl, gross, "fixed gross")
    equal(trade.net_pnl, net, "fixed net")
    equal(trade.end_equity, trade.entry_equity + net, "fixed end equity")
    money.audit_account_return(trade.return_on_entry_equity, trade.entry_equity, trade.end_equity, net,
                               trade.entry_fee, trade.exit_fee, gross, [])
    summary = {**cfg, "start": str(trade.entry_time), "end_exclusive": str(global_end)}
    audit_stop_path(trade, records, daily, summary)
    held = hourly.loc[(hourly.index >= trade.entry_time) & (hourly.index < trade.exit_time)]
    which = np.searchsorted(records.timestamp.astype("int64"), held.index.asi8, side="right") - 1
    assert (which >= 0).all()
    lines = records.new_stop.to_numpy()[which]
    adverse = held.low.to_numpy() if side == 1 else held.high.to_numpy()
    assert (side * (adverse - lines) > 0).all(), "Fixed earlier stop ignored"
    if trade.exit_reason == "sample_end":
        equal(trade.exit_time, global_end, "fixed censor boundary")
        equal(trade.exit_reference, hourly.loc[global_end - HOUR, "close"], "fixed censor close")
    else:
        bar = hourly.loc[trade.exit_time]
        if trade.exit_reason == "stop_gap":
            assert side * (bar.open - trade.stop) <= 0
            equal(trade.exit_reference, bar.open, "fixed gap reference")
        elif trade.exit_reason == "stop_intrahour":
            assert side * (bar.open - trade.stop) > 0
            assert bar.low <= trade.stop if side == 1 else bar.high >= trade.stop
            equal(trade.exit_reference, trade.stop, "fixed stop reference")
        else:
            assert side == -1 and cfg["short_exit"] == "accel1_rsi30" and trade.exit_reason == "accel1_rsi30"
            signal = daily.loc[trade.exit_time - DAY]
            assert signal.rsi <= 30 and signal.accel1
            assert side * (bar.open - trade.stop) > 0, "Fixed RSI exit displaced a gap stop"
            equal(trade.exit_reference, bar.open, "fixed RSI reference")
    equal(trade.exit_interval_end, trade.exit_time + (HOUR if trade.exit_reason == "stop_intrahour" else pd.Timedelta(0)), "fixed exit interval")
    for record in records.iloc[1:].itertuples(index=False):
        day = daily.loc[record.signal_day]
        fill = float(day.close) * (1 - side * slip)
        profit = side * trade.qty * (fill - trade.entry_price) - trade.entry_fee - trade.qty * fill * fee
        equal(record.expected_profit_at_close, profit, "fixed close-profit snapshot")
        equal(record.favorable_move_atr, side * (float(day.close) - trade.entry_price) / trade.entry_atr, "fixed favorable move")
        equal(record.profit_eligible, profit > 0 and side * (day.close - trade.entry_price) >= 0, "fixed profit eligibility")
        if side == -1 and cfg["short_exit"] != "none" and day.rsi <= 30 and day.accel1 and profit > 0:
            assert trade.exit_time == record.timestamp and trade.exit_reason in {"stop_gap", "accel1_rsi30"}
    for name, target in {"baseline_exit_time": base.exit_time, "baseline_exit_reason": base.exit_reason,
                         "baseline_net_pnl": base.net_pnl, "baseline_return": base.return_on_entry_equity,
                         "delta_net_pnl": net - base.net_pnl,
                         "delta_return": trade.return_on_entry_equity - base.return_on_entry_equity,
                         "either_terminal": trade.exit_reason == "sample_end" or base.exit_reason == "sample_end"}.items():
        equal(getattr(trade, name), target, "fixed pair " + name)


def audit_fixed(directory, baseline, daily, hourly, cfg, global_end):
    trades, stops = read_frame(directory / "trades.csv"), read_frame(directory / "stops.parquet")
    saved = read_json(directory / "summary.json")
    assert len(trades) == len(baseline) == saved["pairs"]
    if len(trades):
        assert trades.source_trade_id.tolist() == baseline.trade_id.tolist()
        assert set(stops.source_trade_id) == set(baseline.trade_id)
        base_map = {x.trade_id: x for x in baseline.itertuples(index=False)}
        for trade in trades.itertuples(index=False):
            own = stops.loc[stops.source_trade_id == trade.source_trade_id].reset_index(drop=True)
            audit_fixed_trade(trade, base_map[trade.source_trade_id], own, daily, hourly, cfg, global_end)
    else:
        assert stops.empty
    targets = {"fixed_entry_fields_exact": True, "improved": int(trades.delta_net_pnl.gt(1e-9).sum()) if len(trades) else 0,
               "worsened": int(trades.delta_net_pnl.lt(-1e-9).sum()) if len(trades) else 0,
               "equal": int(trades.delta_net_pnl.abs().le(1e-9).sum()) if len(trades) else 0,
               "either_terminal": int(trades.either_terminal.sum()) if len(trades) else 0,
               "delta_cash_sum": float(trades.delta_net_pnl.sum()) if len(trades) else 0.,
               "delta_return_mean_pct": float(trades.delta_return.mean() * 100) if len(trades) else None}
    for name, target in targets.items():
        equal(saved[name], target, "fixed summary " + name)
    return {"fixed_pairs": len(trades), "fixed_stop_records": len(stops), "status": "PASS"}


def expected_cases():
    old_manifest = read_json(ORIGINAL / "run_manifest.json")
    base = dict(next(x["config"] for x in old_manifest["cases"] if x["case_id"] == "H4_D0"))
    base.update(fee=.001, slip=.0004, direction_mode="both", trend_filter="none", risk_fraction=None,
                notional_fraction=1., progress_policy="permanent", exit_state_policy="v3")
    return {"V3": base, "S1_DEFENSE": {**base, "exit_state_policy": "defense"},
            "S2_TREND": {**base, "exit_state_policy": "trend"},
            "S3_EXTENSION": {**base, "exit_state_policy": "extension", "short_exit": "none"}}


def audit_coin(item, results, frames, configs, summary_table=None, stress_table=None, fixed_table=None):
    row = SimpleNamespace(**item)
    daily, hourly, windows = prior.load_market_inputs(INPUTS, ORIGINAL, row, {"main/" + row.symbol: frames})
    daily = add_causal_audit_features(daily)
    used = read_json(results / "inputs_used" / (row.slug + ".json"))
    assert used["selected_segment_id"] == row.selected_segment_id and used["features_old_columns_exact"]
    for name in ("symbol", "slug", "cohort", "input_start", "trade_start", "end", "trade_days"):
        equal(used[name], item[name], "input selection " + name)
    totals = {"symbol": row.symbol, "slug": row.slug, "cohort": row.cohort, "accounts": 0,
              "trades": 0, "stop_records": 0, "equity_marks": 0, "opportunity_events": 0,
              "fixed_pairs": 0, "fixed_stop_records": 0, "by_case": {}, "status": "PASS"}
    directories = []
    for case, cfg in configs.items():
        totals["by_case"][case] = {"accounts": 0, "trades": 0, "fixed_pairs": 0}
        for kind, scenario, carry in [("runs", "full", 0.), ("sensitivity", "slippage_10bp", 0.),
                                      ("sensitivity", "carry_5bp_day", .0005)]:
            directory = results / kind / row.slug / case / scenario
            saved = read_json(directory / "summary.json")
            for key, value in cfg.items():
                equal(saved[key], .001 if scenario == "slippage_10bp" and key == "slip" else value, "frozen config " + key)
            assert [pd.Timestamp(saved["start"]), pd.Timestamp(saved["end_exclusive"])] == list(map(pd.Timestamp, windows["full"]))
            checked = audit_continuous(directory, daily, hourly, carry)
            table = summary_table if kind == "runs" else stress_table
            if table is not None:
                prior.compare_summary_row(table, {"symbol": row.symbol, "case_id": case,
                    "window" if kind == "runs" else "scenario": scenario}, saved)
            totals["accounts"] += 1
            for key, source in [("trades", "trades"), ("stop_records", "stop_records"),
                                ("equity_marks", "equity_marks_independently_rebuilt"), ("opportunity_events", "opportunity_events")]:
                totals[key] += checked[source]
            totals["by_case"][case]["accounts"] += 1
            totals["by_case"][case]["trades"] += checked["trades"]
            directories.append(str(directory.relative_to(results)))
    baseline = read_frame(results / "runs" / row.slug / "V3/full/trades.csv")
    for case, cfg in configs.items():
        if case == "V3":
            continue
        directory = results / "fixed_entries" / row.slug / case
        checked = audit_fixed(directory, baseline, daily, hourly, cfg, pd.Timestamp(row.end))
        for key in ("fixed_pairs", "fixed_stop_records"):
            totals[key] += checked[key]
        totals["by_case"][case]["fixed_pairs"] = checked["fixed_pairs"]
        if fixed_table is not None:
            prior.compare_summary_row(fixed_table, {"symbol": row.symbol, "case_id": case}, read_json(directory / "summary.json"))
        directories.append(str(directory.relative_to(results)))
    return totals, directories


def self_checks():
    """Manual dimensional/threshold fixtures, with no simulator import."""
    checks = 0
    for s in [1, -1]:
        def row(day, close, peak, delta, ma=0., atr=10., prior_atr=10., rsi=50.):
            return SimpleNamespace(timestamp=pd.Timestamp("2026-01-01", tz="UTC") + day * DAY,
                close=100+s*close, high=100+(peak if s == 1 else -(close-.1)),
                low=100+((close-.1) if s == 1 else -peak), ma=100+s*ma, atr=atr,
                audit_delta=s*delta, audit_prior_delta=0., audit_prior_atr=prior_atr,
                audit_prior2_atr=10., rsi=rsi if s == 1 else 100-rsi)
        state = ClosedState(s, 100., 100., "extension")
        a = state.observe(row(1, 30., 30., 10.), 100+s*30., 0)
        assert a["sm_watch"] == "WATCH" and not a["sm_protect"] and not a["sm_ready3"]
        checks += 1
        b = state.observe(row(2, 22.5, 30., -7.5, ma=10.), 100+s*30., 1)
        assert b["sm_watch"] == "PROTECT" and b["sm_transition"] == "exhaustion_protect"
        equal(b["sm_protection_stop"], 100+s*20., "manual watch stop")
        checks += 1
        state = ClosedState(s, 100., 100., "extension")
        state.observe(row(1, 30., 30., 10.), 100+s*30., 0)
        c = state.observe(row(2, 40., 48., 10., atr=100., prior_atr=100., rsi=90.), 100+s*48., 0)
        assert c["sm_watch"] == "WATCH" and c["sm_peak_speed"] == 1 and c["sm_watch_atr"] == 10
        checks += 1
        state = ClosedState(s, 100., 100+s*.04, "trend")
        for n, close in enumerate([2., 1., 3.], 1):
            c = state.observe(row(n, close, 7.5, 0., atr=6.), 100+s*7.5, 0)
        equal(c["sm_efficiency3"], .6, "manual entry reference efficiency")
        assert c["sm_ready3"] and c["sm_healthy"]
        checks += 1
        # A tampered recorded boundary/amount must fail the actual scalar
        # comparison used for every saved state field.
        for field in ["sm_speed3", "sm_efficiency3", "sm_retrace_atr"]:
            target = c[field]
            try:
                equal(target + .001, target, "intentional corrupt " + field)
            except AssertionError:
                checks += 1
            else:
                raise AssertionError("State corruption accepted")
    return {"checks": checks, "status": "PASS", "simulator_called": False}


def retained_tamper_checks(results, scope, frames, configs):
    """Corrupt in-memory copies only; every retained source stays untouched."""
    item = scope.loc[scope.slug.eq("0G")].iloc[0]
    daily, hourly, _ = prior.load_market_inputs(INPUTS, ORIGINAL, SimpleNamespace(**item.to_dict()),
                                                 {"main/" + item.symbol: frames["main/" + item.symbol]})
    daily = add_causal_audit_features(daily)
    baseline = read_frame(results / "runs/0G/V3/full/trades.csv")
    pairs = read_frame(results / "fixed_entries/0G/S3_EXTENSION/trades.csv")
    stops = read_frame(results / "fixed_entries/0G/S3_EXTENSION/stops.parquet")
    targets = pairs.loc[pairs.source_trade_id.isin(stops.groupby("source_trade_id").size().loc[lambda x:x > 3].index)]
    assert len(targets)
    trade = targets.iloc[0]
    base = baseline.loc[baseline.trade_id == trade.source_trade_id].iloc[0]
    own = stops.loc[stops.source_trade_id == trade.source_trade_id].reset_index(drop=True)
    cfg = configs["S3_EXTENSION"]
    cases = []
    for field, delta in [("qty", 1.), ("net_pnl", 1.), ("exit_reference", 1.), ("delta_return", .01)]:
        changed = trade.to_dict()
        changed[field] += delta
        cases.append(("trade_" + field, SimpleNamespace(**changed), own, hourly))
    for field in ("new_stop", "sm_efficiency3"):
        changed = own.copy()
        idx = changed.index[changed[field].notna()][-1]
        changed.loc[idx, field] += .01
        cases.append(("stop_" + field, SimpleNamespace(**trade.to_dict()), changed, hourly))
    changed = own.copy()
    changed.loc[1, "sm_ready3"] = not bool(changed.loc[1, "sm_ready3"])
    cases.append(("premature_ready3", SimpleNamespace(**trade.to_dict()), changed, hourly))
    changed = own.iloc[1:].copy()
    cases.append(("missing_initial_stop", SimpleNamespace(**trade.to_dict()), changed, hourly))
    before_exit = hourly.loc[(hourly.index >= trade.entry_time) & (hourly.index < trade.exit_time)]
    assert len(before_exit)
    changed_hourly = hourly.copy()
    stamp = before_exit.index[0]
    field = "low" if trade.side == 1 else "high"
    changed_hourly.loc[stamp, field] = float(own.new_stop.iloc[0]) - trade.side
    cases.append(("ignored_earlier_stop_hit", SimpleNamespace(**trade.to_dict()), own, changed_hourly))
    refused = []
    for label, altered, altered_stops, altered_hourly in cases:
        try:
            audit_fixed_trade(altered, SimpleNamespace(**base.to_dict()), altered_stops,
                              daily, altered_hourly, cfg, pd.Timestamp(item.end))
        except AssertionError:
            refused.append(label)
        else:
            raise AssertionError("Corrupted saved ledger accepted: " + label)
    return {"status": "PASS", "mutations_rejected": refused, "source_symbol": item.symbol,
            "source_trade_id": int(trade.source_trade_id), "sources_modified": False}


def audit_all(results, workers=4, smoke_slugs=None, checkpoint_dir=None):
    assert sha(Path(money.__file__)) == BASE_MONEY_SHA
    assert sha(Path(prior.__file__)) == BASE_INPUT_AUDIT_SHA
    assert sha(INPUTS / "checksums.json") == INPUT_SHA
    assert sha(ORIGINAL / "artifact_checksums.json") == ORIGINAL_MANIFEST_SHA
    checks = self_checks()
    manifest = read_json(results / "run_manifest.json")
    configs = {x["case_id"]: x["config"] for x in manifest["cases"]}
    assert configs == expected_cases()
    assert manifest["expected_accounts"] == 7332 and not manifest["funding_window_verified"]
    for path, digest in manifest["source_pins"].items():
        assert sha(LAB / path) == digest, "Changed run source: " + path
    pin = manifest["engine_pin"]
    assert sha(LAB / pin["engine_path"]) == pin["engine_sha256"]
    for name in ("strategy_contract_pin.json", "cost_amendment_pin.json"):
        contract = read_json(ROUND / name)
        assert sha(LAB / contract["path"]) == contract["sha256"]
    scope = read_frame(results / "scope.csv")
    old_scope = read_frame(ORIGINAL / "scope.csv")
    for key in ("symbol", "slug", "cohort", "selected_segment_id", "input_start", "trade_start", "end", "trade_days"):
        left = scope.sort_values("symbol")[key].fillna("__MISSING__").tolist()
        right = old_scope.sort_values("symbol")[key].fillna("__MISSING__").tolist()
        assert left == right, "Scope changed: " + key
    eligible = scope.loc[scope.cohort.ne("excluded")]
    assert len(eligible) == 611
    frames = read_json(INPUTS / "frames_manifest.json")
    tamper_checks = retained_tamper_checks(results, scope, frames, configs)
    done = None
    result_hash = None
    summary_table = stress_table = fixed_table = None
    if smoke_slugs is None:
        done = read_json(results / "completion.json")
        assert done["complete"] and done["coins"] == 611 and done["accounts"] == 7332
        result_hash = sha(results / "artifact_checksums.json")
        assert result_hash == done["manifest_sha256"]
        input_files = prior.verify_hash_map(INPUTS)
        result_files = prior.verify_hash_map(results, "artifact_checksums.json")
        actual_files = {str(p.relative_to(results)) for p in results.rglob("*") if p.is_file()}
        assert actual_files == set(read_json(results / "artifact_checksums.json")) | {"completion.json", "artifact_checksums.json"}
        summary_table, stress_table, fixed_table = [read_frame(results / (name + ".csv")) for name in ("summary", "stress", "fixed")]
        assert len(summary_table) == 2444 and len(stress_table) == 4888 and len(fixed_table) == 1833
    else:
        assert smoke_slugs and set(smoke_slugs) <= set(eligible.slug)
        eligible = eligible.loc[eligible.slug.isin(smoke_slugs)]
        input_files = result_files = None
    identity = {"audit_script_sha256": sha(Path(__file__)), "source_manifest_sha256": sha(results / "run_manifest.json"),
                "result_manifest_sha256": result_hash, "input_manifest_sha256": INPUT_SHA,
                "engine_sha256": pin["engine_sha256"], "smoke_slugs": smoke_slugs}
    if checkpoint_dir is not None:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        identity_path = checkpoint_dir / "identity.json"
        if identity_path.exists():
            assert read_json(identity_path) == identity, "Audit checkpoint belongs to different inputs or code"
        else:
            write_json(identity_path, identity)
    jobs, receipts, visited = [], [], []
    for item in eligible.to_dict("records"):
        record = checkpoint_dir / (item["slug"] + ".json") if checkpoint_dir else None
        if record and record.exists():
            cached = read_json(record)
            assert cached["identity"] == identity and cached["coin"]["status"] == "PASS"
            receipts.append(cached["coin"])
            visited.extend(cached["directories"])
        else:
            jobs.append(item)
    began = time.monotonic()
    with ProcessPoolExecutor(max_workers=workers) as executor:
        pending = {executor.submit(audit_coin, item, results, frames["main/" + item["symbol"]], configs,
                                   summary_table, stress_table, fixed_table): item for item in jobs}
        for future in as_completed(pending):
            item = pending[future]
            try:
                coin, paths = future.result()
            except Exception:
                raise AssertionError("Coin independent audit failed: " + item["symbol"] + "\n" + traceback.format_exc())
            receipts.append(coin)
            visited.extend(paths)
            if checkpoint_dir:
                write_json(checkpoint_dir / (item["slug"] + ".json"), {"identity": identity, "coin": coin, "directories": paths})
            if len(receipts) % 10 == 0 or len(receipts) == len(eligible):
                print(f"AUDITED {len(receipts)}/{len(eligible)} coins; elapsed={time.monotonic()-began:.1f}s", flush=True)
    totals = {name: sum(x[name] for x in receipts) for name in
              ("accounts", "trades", "stop_records", "equity_marks", "opportunity_events", "fixed_pairs", "fixed_stop_records")}
    assert totals["accounts"] == len(eligible) * 12
    if done:
        assert totals["fixed_pairs"] == done["fixed_pairs"]
        actual_dirs = {str(p.parent.relative_to(results)) for p in results.glob("runs/*/*/*/summary.json")}
        actual_dirs |= {str(p.parent.relative_to(results)) for p in results.glob("sensitivity/*/*/*/summary.json")}
        actual_dirs |= {str(p.parent.relative_to(results)) for p in results.glob("fixed_entries/*/*/summary.json")}
        assert len(visited) == len(set(visited)) and set(visited) == actual_dirs
        assert sha(results / "artifact_checksums.json") == result_hash
    return {"status": "PASS", "complete_market_audit": smoke_slugs is None, "simulator_called": False,
            "old_account_replayed": False, "smoke_slugs": smoke_slugs, "coins": len(receipts), **totals,
            "identity": identity, "base_money_audit_sha256": BASE_MONEY_SHA, "base_input_audit_sha256": BASE_INPUT_AUDIT_SHA,
            "self_checks": checks, "retained_tamper_checks": tamper_checks,
            "verified_input_files": input_files, "verified_result_files": result_files,
            "elapsed_seconds": time.monotonic()-began, "coin_receipts": sorted(receipts, key=lambda x:x["symbol"]),
            "fixed_equity_curves_saved": False, "fixed_pair_scope": "same entry, quantity, cash, prices, fees, causal stops, first exit and pair deltas",
            "funding_window_verified": False, "pit_universe_proven": False}


def audit_calendar_blocks(directory, lo, hi, definitions, saved):
    """Use first boundary mark, except final settlement; keep carried positions."""
    curve = read_frame(directory / "equity.parquet")
    assert len(saved) == len(definitions)
    timestamps = pd.DatetimeIndex(curve.timestamp).as_unit("ns")
    values = curve.equity.to_numpy(float)
    for name, begin, finish in definitions:
        matched = saved.loc[saved.block.eq(name)]
        assert len(matched) == 1
        actual = matched.iloc[0]
        request_start, request_end = pd.Timestamp(begin, tz="UTC"), pd.Timestamp(finish, tz="UTC")
        start, end = max(lo, request_start), min(hi, request_end)
        complete = lo <= request_start and hi >= request_end
        equal(actual.requested_start, request_start, "calendar requested start")
        equal(actual.requested_end, request_end, "calendar requested end")
        equal(actual.complete_coverage, complete, "calendar coverage")
        assert actual.account_position_inherited
        if start >= end:
            assert actual.status == "NO_OVERLAP"
            continue
        assert actual.status == ("COMPLETE" if complete else "PARTIAL")
        beginning = np.flatnonzero(timestamps == start)
        ending = np.flatnonzero(timestamps == end)
        assert len(beginning) and len(ending), "Missing exact calendar boundary"
        ia, ib = int(beginning[0]), int(ending[-1] if end == hi else ending[0])
        span = values[ia:ib+1]
        capital, final = float(span[0]), float(span[-1])
        target_return = (final / capital - 1) * 100 if capital > 0 else None
        target_dd = float(np.min(span / np.maximum.accumulate(span) - 1) * 100) if capital > 0 else None
        for key, target in {"actual_start": start, "actual_end": end, "days": (end-start).days,
                            "start_equity": capital, "end_equity": final,
                            "return_pct": target_return, "max_drawdown_pct": target_dd}.items():
            equal(actual[key], target, "calendar " + key)
    return len(saved)


def audit_history_coin(item, segments, frame_manifest, input_source, results, configs,
                       blocks, summary_table=None, block_table=None):
    symbol, slug = item["symbol"], item["slug"]
    for name in ("joint_daily", "1h"):
        info = frame_manifest[name]
        assert sha(input_source / info["path"]) == info["sha256"]
    raw_daily = pd.read_parquet(input_source / frame_manifest["joint_daily"]["path"])
    raw_hourly = pd.read_parquet(input_source / frame_manifest["1h"]["path"])
    totals = {"symbol": symbol, "slug": slug, "accounts": 0, "segments": 0, "trades": 0,
              "stop_records": 0, "equity_marks": 0, "opportunity_events": 0,
              "calendar_rows": 0, "status": "PASS"}
    visited = []
    for n, seg in enumerate(sorted(segments, key=lambda x:x["input_start"]), 1):
        if int(seg["trade_days"]) <= 0:
            continue
        key = f"{slug}__seg{n:03d}"
        meta = read_json(results / "inputs_used" / (key + ".json"))
        assert meta["source_frames"] == frame_manifest
        assert meta["source_input_directory"] == str(input_source.relative_to(LAB))
        for name, value in seg.items():
            equal(meta[name], value, "history selected segment " + name)
        assert meta["run_key"] == key and meta["slug"] == slug
        lo, hi, beginning = map(pd.Timestamp, [seg["first_trade_open"], seg["end"], seg["input_start"]])
        assert lo == beginning + 29 * DAY and hi > lo
        selected = raw_daily.loc[raw_daily.joint_segment_id.eq(seg["segment_id"])].sort_values("ts").reset_index(drop=True)
        h = raw_hourly.loc[(raw_hourly.ts >= beginning) & (raw_hourly.ts < hi)].sort_values("ts").reset_index(drop=True)
        assert len(selected) == int(seg["input_days"]) and len(h) == len(selected) * 24
        for frame in (selected, h):
            assert frame.eligible.all() and frame.is_closed.all()
        assert selected.joint_eligible.all()
        assert not selected.research_window_valid.iloc[:28].any() and selected.research_window_valid.iloc[28:].all()
        reconstructed = prior.reconstruct_features(selected)
        daily = read_frame(results / "market" / key / "daily_features.csv").set_index("timestamp", drop=False)
        assert daily.index.equals(pd.date_range(beginning, hi-DAY, freq="D").as_unit("ns"))
        assert daily.index.equals(reconstructed.index)
        for column in ("open", "high", "low", "close", "ma", "atr", "rsi", "slope"):
            assert np.allclose(daily[column], reconstructed[column], equal_nan=True, rtol=2e-10, atol=1e-14), column
        for column in ("cross", "ready", "accel1", "research_window_valid"):
            assert daily[column].tolist() == reconstructed[column].tolist(), column
        daily = add_causal_audit_features(daily)
        h = h.rename(columns={"ts": "timestamp"})
        h.timestamp = pd.to_datetime(h.timestamp, utc=True).dt.as_unit("ns")
        h = h.set_index("timestamp", drop=False)
        assert h.index.equals(pd.date_range(beginning, hi-HOUR, freq="h").as_unit("ns"))
        aggregate = h.groupby(h.timestamp.dt.floor("D")).agg(open=("open", "first"),
            close=("close", "last"), high=("high", "max"), low=("low", "min"), hours=("open", "size"))
        assert aggregate.hours.eq(24).all() and aggregate.index.equals(daily.index)
        assert np.allclose(aggregate[["open", "high", "low", "close"]],
                           daily[["open", "high", "low", "close"]], rtol=2e-10, atol=1e-14)
        for case, cfg in configs.items():
            directory = results / "runs" / key / case / "full"
            summary = read_json(directory / "summary.json")
            for name, value in cfg.items():
                equal(summary[name], value, "history frozen config " + name)
            assert list(map(pd.Timestamp, [summary["start"], summary["end_exclusive"]])) == [lo, hi]
            checked = audit_continuous(directory, daily, h)
            totals["accounts"] += 1
            for target, source in [("trades", "trades"), ("stop_records", "stop_records"),
                                   ("equity_marks", "equity_marks_independently_rebuilt"), ("opportunity_events", "opportunity_events")]:
                totals[target] += checked[source]
            if summary_table is not None:
                prior.compare_summary_row(summary_table, {"symbol": symbol, "run_key": key, "case_id": case}, summary)
            if block_table is not None:
                subset = block_table.loc[block_table.run_key.eq(key) & block_table.case_id.eq(case)]
                totals["calendar_rows"] += audit_calendar_blocks(directory, lo, hi, blocks, subset)
            visited.append(str(directory.relative_to(results)))
        totals["segments"] += 1
    assert totals["accounts"] == sum(int(x["trade_days"]) > 0 for x in segments) * 4
    return totals, visited


def audit_history(results, workers=4, smoke_slugs=None, checkpoint_dir=None):
    assert sha(Path(money.__file__)) == BASE_MONEY_SHA
    assert sha(Path(prior.__file__)) == BASE_INPUT_AUDIT_SHA
    manifest = read_json(results / "run_manifest.json")
    input_source = LAB / manifest["input_source"]
    input_done = read_json(input_source / "completion.json")
    assert input_done["complete"] and not input_done["candidate_results_computed"]
    assert manifest["all_segments_preserved"] and not manifest["new_candidates_selected_by_current_results"]
    assert not manifest["funding_window_verified"]
    for path, digest in manifest["source_pins"].items():
        assert sha(LAB / path) == digest, "Changed history source: " + path
    pin = manifest["engine_pin"]
    assert sha(LAB / pin["engine_path"]) == pin["engine_sha256"]
    for path, digest in pin["contracts"].items():
        assert sha(LAB / path) == digest
    assert pin["fee"] == .001 and pin["slip"] == .0004
    configs = expected_cases()
    scope, segments = read_frame(results / "scope.csv"), read_frame(results / "segments.csv")
    # The historical runner copies metadata after pandas' default CSV parse.
    # Reproduce that metadata-only round trip exactly; prices and ledgers keep
    # round_trip parsing and the independent indicator/price checks above.
    source_scope = pd.read_csv(input_source / "scope.csv")
    source_segments = pd.read_csv(input_source / "segments.csv")
    pd.testing.assert_frame_equal(scope, source_scope, check_exact=True)
    pd.testing.assert_frame_equal(segments, source_segments, check_exact=True)
    frames = read_json(input_source / "frames_manifest.json")
    assert set(scope.symbol) == set(frames)
    expected_count = int(segments.trade_days.gt(0).sum()) * 4
    assert manifest["expected_segment_accounts"] == expected_count
    done = None
    result_hash = None
    summary_table = block_table = None
    input_files = result_files = None
    if smoke_slugs is None:
        done = read_json(results / "completion.json")
        assert done["complete"] and done["coins"] == len(scope)
        assert done["segment_accounts"] == done["expected_segment_accounts"] == expected_count
        result_hash = sha(results / "artifact_checksums.json")
        assert result_hash == done["manifest_sha256"]
        input_files = prior.verify_hash_map(input_source)
        result_files = prior.verify_hash_map(results, "artifact_checksums.json")
        files = {str(p.relative_to(results)) for p in results.rglob("*") if p.is_file()}
        assert files == set(read_json(results / "artifact_checksums.json")) | {"artifact_checksums.json", "completion.json"}
        summary_table, block_table = read_frame(results / "summary.csv"), read_frame(results / "blocks.csv")
        assert len(summary_table) == expected_count
        assert len(block_table) == expected_count * len(manifest["calendar_blocks"])
    else:
        assert smoke_slugs and set(smoke_slugs) <= set(scope.slug)
        scope = scope.loc[scope.slug.isin(smoke_slugs)]
    identity = {"audit_script_sha256": sha(Path(__file__)), "source_manifest_sha256": sha(results / "run_manifest.json"),
                "result_manifest_sha256": result_hash, "input_manifest_sha256": sha(input_source / "checksums.json"),
                "engine_sha256": pin["engine_sha256"], "smoke_slugs": smoke_slugs, "mode": "all_history_segments"}
    if checkpoint_dir:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        old = checkpoint_dir / "identity.json"
        if old.exists():
            assert read_json(old) == identity
        else:
            write_json(old, identity)
    jobs, receipts, visited = [], [], []
    for item in scope.to_dict("records"):
        saved = checkpoint_dir / (item["slug"] + ".json") if checkpoint_dir else None
        if saved and saved.exists():
            prior_receipt = read_json(saved)
            assert prior_receipt["identity"] == identity and prior_receipt["coin"]["status"] == "PASS"
            receipts.append(prior_receipt["coin"])
            visited.extend(prior_receipt["directories"])
        else:
            jobs.append(item)
    began = time.monotonic()
    with ProcessPoolExecutor(max_workers=workers) as executor:
        pending = {executor.submit(audit_history_coin, item,
            segments.loc[segments.symbol.eq(item["symbol"])].to_dict("records"), frames[item["symbol"]],
            input_source, results, configs, manifest["calendar_blocks"], summary_table, block_table): item for item in jobs}
        for future in as_completed(pending):
            item = pending[future]
            try:
                coin, paths = future.result()
            except Exception:
                raise AssertionError("History independent audit failed: " + item["symbol"] + "\n" + traceback.format_exc())
            receipts.append(coin)
            visited.extend(paths)
            if checkpoint_dir:
                write_json(checkpoint_dir / (item["slug"] + ".json"), {"identity": identity, "coin": coin, "directories": paths})
            if len(receipts) % 10 == 0 or len(receipts) == len(scope):
                print(f"HISTORY AUDITED {len(receipts)}/{len(scope)} coins; elapsed={time.monotonic()-began:.1f}s", flush=True)
    totals = {key: sum(x[key] for x in receipts) for key in
              ("accounts", "segments", "trades", "stop_records", "equity_marks", "opportunity_events", "calendar_rows")}
    if done:
        assert totals["accounts"] == expected_count
        assert totals["calendar_rows"] == len(block_table)
        expected_dirs = {str(p.parent.relative_to(results)) for p in results.glob("runs/*/*/*/summary.json")}
        assert len(set(visited)) == len(visited) and set(visited) == expected_dirs
        assert sha(results / "artifact_checksums.json") == result_hash
    return {"status": "PASS", "complete_history_audit": smoke_slugs is None, "simulator_called": False,
            "old_account_replayed": False, "coins": len(receipts), **totals, "identity": identity,
            "base_money_audit_sha256": BASE_MONEY_SHA, "base_input_audit_sha256": BASE_INPUT_AUDIT_SHA,
            "self_checks": self_checks(), "verified_input_files": input_files, "verified_result_files": result_files,
            "elapsed_seconds": time.monotonic()-began, "coin_receipts": sorted(receipts, key=lambda x:x["symbol"]),
            "funding_window_verified": False, "pit_universe_proven": False,
            "calendar_blocks_are_descriptive_not_trading_signals": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--output", type=Path, default=ROUND / "audit_current.json")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--smoke-slugs", nargs="+")
    parser.add_argument("--checkpoints", type=Path)
    parser.add_argument("--self-check-only", action="store_true")
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    if args.self_check_only:
        report = self_checks()
    else:
        try:
            audit = audit_history if args.history else audit_all
            report = audit(args.results.resolve(), args.workers, args.smoke_slugs, args.checkpoints)
        except Exception:
            report = {"status": "FAIL", "complete_market_audit": False, "simulator_called": False,
                      "audit_script_sha256": sha(Path(__file__)), "error": traceback.format_exc()}
            write_json(args.output, report)
            raise
    write_json(args.output, report)
    print(json.dumps({k:v for k,v in report.items() if k not in {"coin_receipts", "error"}}, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
