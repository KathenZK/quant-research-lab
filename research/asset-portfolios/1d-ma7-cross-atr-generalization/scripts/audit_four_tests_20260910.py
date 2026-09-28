"""Independent ledgers and opportunity audit for the nine four-test cases.

Reads frozen artifacts only. No strategy simulator is imported or called.
Original V1/V3 ledgers are reused by hash, never recomputed here.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

import audit_results as prior

FAMILY, LAB, DAY, HOUR = prior.FAMILY, prior.LAB, prior.DAY, prior.HOUR
BASE_AUDIT_SHA = "f376e8560d724a039dc5612962ce719602dc2e21157683ed6f8c177e5a1d9dc1"
PRIOR_REPORT_SHA = "08e12de5e6bd68ac93a24fd94e6a0bc072ff20f450146c0a10f3631175c1c580"
INPUTS = FAMILY / "artifacts/inputs_20260909"
ORIGINAL = FAMILY / "artifacts/results_20260909"
RESULTS = FAMILY / "artifacts/results_four_tests_20260910"
equal, sha, read_json, read_frame = prior.equal, prior.sha, prior.read_json, prior.read_frame
ENTRY_COLUMNS = {
    "timestamp", "signal_day", "side", "cross", "entry_reason", "cross_day",
    "stage", "reason", "status", "entry_filter", "direction_mode", "entry_slope",
    "entry_close", "entry_ma", "entry_ma30", "entry_prev_ma30", "trade_id",
    "attempt_before_equity", "entry_price", "initial_stop", "initial_stop_fill",
    "initial_stop_unit_risk", "qty_cap", "qty", "initial_planned_risk",
    "initial_planned_risk_pct", "risk_fraction", "notional_fraction",
    "initial_stop_price_nonpositive",
}


def account_return_roundoff_bound(equity, entry_fee, exit_fee, gross, carry):
    """Bound cancellation after repeated cash subtractions, in return units.

    epsilon is twice binary64 unit roundoff. The four extra operations cover
    entry/exit fees, settlement and final capital subtraction. Zero carry
    hours perform no cash operation. Prices and dollar checks retain equal().
    """
    operations = int(np.count_nonzero(carry)) + 4
    epsilon = np.finfo(float).eps
    gamma = operations * epsilon / (1 - operations * epsilon)
    scale = math.fsum([abs(equity), abs(entry_fee), abs(exit_fee), abs(gross),
                       *map(abs, carry)])
    return gamma * scale / abs(equity)


def audit_account_return(actual, equity, end_equity, net, entry_fee, exit_fee, gross, carry):
    # First verify the saved definition with the original strict tolerance.
    equal(actual, (end_equity - equity) / equity, "trade return cash identity")
    target = net / equity
    bound = account_return_roundoff_bound(equity, entry_fee, exit_fee, gross, carry)
    tolerance = 1e-14 + 2e-10 * abs(target) + bound
    assert math.isfinite(actual) and math.isfinite(target) and abs(actual - target) <= tolerance, (
        f"trade return independent net: {actual} != {target}; numerical bound {bound}")


def audit_quantity(trade, summary, equity):
    """Sizing comes from per-unit planned stop loss, not saved quantity fields."""
    side, fee, slip = int(trade.side), float(summary["fee"]), float(summary["slip"])
    entry_fill = float(trade.entry_reference) * (1 + side * slip)
    stop_fill = float(trade.initial_stop) * (1 - side * slip)
    unit_risk = side * (entry_fill - stop_fill) + fee * (entry_fill + stop_fill)
    cap = equity / (entry_fill * (1 + fee))
    fraction = float(summary["notional_fraction"])
    risk_fraction = summary["risk_fraction"]
    expected = cap * fraction
    if risk_fraction is not None:
        assert np.isfinite(unit_risk) and unit_risk > 0
        expected = min(expected, float(risk_fraction) * equity / unit_risk)
    equal(trade.qty, expected, "sized quantity")
    for key, value in {"initial_stop_fill": stop_fill,
                       "initial_stop_unit_risk": unit_risk, "initial_planned_risk": expected * unit_risk,
                       "initial_planned_risk_pct": expected * unit_risk / equity * 100,
                       "qty_cap": cap * fraction, "notional_fraction": fraction, "risk_fraction": risk_fraction,
                       "initial_stop_price_nonpositive": bool(trade.initial_stop <= 0),
                       "initial_stop_risk_price": side * (entry_fill - trade.initial_stop),
                       "initial_stop_risk_pct": side * (entry_fill - trade.initial_stop) / entry_fill * 100}.items():
        equal(getattr(trade, key), value, "quantity record " + key)
    assert expected <= cap * (1 + 1e-12)
    if risk_fraction is not None:
        assert expected * unit_risk <= equity * float(risk_fraction) * (1 + 1e-12)


def audit_stop_path(trade, records, daily, summary):
    """Reconstruct high/low progress and active/history arming separately."""
    side = int(trade.side)
    assert summary["progress_days"] == 4 and summary["progress_source"] == "high_low"
    assert summary["stop_anchor"] == "ma" and summary["tighten_mode"] == "fixed"
    policy = summary["progress_policy"]
    signal = daily.loc[trade.signal_day]
    initial = float(signal.ma - side * 1.5 * signal.atr)
    equal(trade.initial_stop, initial, "initial stop from signal day")
    equal(trade.uncapped_initial_stop, initial, "uncapped initial stop")
    equal(trade.entry_atr, signal.atr, "entry ATR")
    assert not trade.cap_applied and trade.progress_source == "high_low"
    assert trade.progress_policy == policy
    end = pd.Timestamp(summary["end_exclusive"])
    dates = pd.date_range(trade.entry_time.floor("D") + DAY, trade.exit_time.floor("D"), freq="D")
    dates = dates[dates < end]
    assert records.timestamp.tolist() == [trade.entry_time, *dates], "Missing/extra stop update"
    first = records.iloc[0]
    for key, value in {"new_stop": initial, "old_stop": initial, "new_mult": 1.5,
                       "old_mult": 1.5, "new_armed": False, "old_armed": False,
                       "initialized": False, "tightened": False, "ever_armed": False,
                       "first_arm_day": None, "arm_count": 0, "reset_count": 0,
                       "armed_reset": False, "progress_policy": policy}.items():
        equal(getattr(first, key), value, "initial stop " + key)
    old_stop, mult = initial, 1.5
    armed, initialized, ever = False, False, False
    extreme, extreme_day, arm_day, first_arm_day = None, None, None, None
    count, reductions, arms, resets = 0, 0, 0, 0
    for row in records.iloc[1:].itertuples(index=False):
        assert row.timestamp == row.signal_day + DAY, "Unclosed bar controls stop"
        day = daily.loc[row.signal_day]
        equal(row.old_stop, old_stop, "old stop")
        equal(row.old_mult, mult, "old multiple")
        equal(row.old_armed, armed, "old armed")
        equal(row.natural_candidate, day.ma - side * mult * day.atr, "natural MA stop")
        equal(row.stalled, side * (row.natural_candidate - old_stop) <= 1e-12 * max(1.0, abs(old_stop)), "candidate stalled")
        full_day = row.signal_day >= trade.entry_time
        new_extreme, tightened, reset = False, False, False
        was_armed, old_mult = armed, mult
        trigger = "partial_entry_day"
        if full_day:
            observed = float(day.high if side == 1 else day.low)
            if not initialized:
                initialized, extreme, extreme_day = True, observed, row.signal_day
                new_extreme = True
                trigger = "extreme_initialize"
            else:
                new_extreme = side * (observed - extreme) > 0
                if new_extreme:
                    extreme, extreme_day, count = observed, row.signal_day, 0
                    if policy == "reset_on_new_extreme":
                        reset = armed
                        resets += int(reset)
                        armed, arm_day = False, None
                else:
                    count += 1
                if not armed and count >= 4:
                    armed, ever, arm_day = True, True, row.signal_day
                    arms += 1
                    if first_arm_day is None:
                        first_arm_day = row.signal_day
                tightened = armed and mult > 0.5
                trigger = ("at_floor" if old_mult <= 0.5 else
                           ("progress_armed_daily" if was_armed else "no_new_extreme") if armed else
                           "progress_reset" if reset else "progress_observed")
        if tightened:
            mult = max(0.5, round(mult - 0.2, 10))
            reductions += 1
        candidate = float(day.ma - side * mult * day.atr)
        stop = max(old_stop, candidate) if side == 1 else min(old_stop, candidate)
        expected = {"new_stop": stop, "new_mult": mult, "new_armed": armed,
                    "initialized": initialized, "extreme_price": extreme,
                    "extreme_day": extreme_day, "arm_day": arm_day,
                    "new_extreme": new_extreme, "no_new_extreme_days": count,
                    "tightened": tightened, "full_holding_day": bool(full_day),
                    "armed_reset": bool(reset), "ever_armed": ever,
                    "first_arm_day": first_arm_day, "arm_count": arms, "reset_count": resets,
                    "progress_policy": policy, "tightening_trigger": trigger,
                    "anchor_candidate": None, "anchor_decisive": False}
        for key, value in expected.items():
            equal(getattr(row, key), value, "stop " + key)
        assert side * (stop - old_stop) >= 0 and 0.5 <= mult <= 1.5
        old_stop = stop
    expected = {"stop": old_stop, "stop_mult": mult, "armed": armed,
                "initialized": initialized, "extreme_price": extreme,
                "extreme_day": extreme_day, "arm_day": arm_day,
                "no_new_extreme_days": count, "tightening_days": reductions,
                "stop_floor_reached": mult == 0.5, "ever_armed": ever,
                "first_arm_day": first_arm_day, "arm_count": arms, "reset_count": resets,
                "anchor_decisive_days": 0}
    for key, value in expected.items():
        equal(getattr(trade, key), value, "final stop " + key)


def audit_entry_lifecycle(trades, daily, hourly, summary, events):
    """Reconstruct every flat crossing and its first terminal rejection stage."""
    assert summary["entry_wait_days"] == summary["delay_hours"] == 0
    assert not summary["reverse"] and summary["entry_mode"] == "original"
    assert set(events.columns) == ENTRY_COLUMNS, "Opportunity schema missing/extra fields"
    start, end = pd.Timestamp(summary["start"]), pd.Timestamp(summary["end_exclusive"])
    rows = list(trades.itertuples(index=False))
    entered = {row.entry_time: row for row in rows}
    assert len(entered) == len(rows)
    counts = dict.fromkeys(("flat_ready_crosses", "flat_not_ready_crosses", "entry_attempts", "entry_fills",
                           "slope_rejected", "direction_rejected", "ma30_not_ready_rejected",
                           "ma30_direction_rejected", "invalid_stop_rejected", "nonpositive_equity_rejected",
                           "invalid_unit_risk_rejected", "wait_candidates_created"), 0)
    expected_events = []
    fee, slip = summary["fee"], summary["slip"]
    for timestamp in pd.date_range(start, end - DAY, freq="D"):
        signal = daily.loc[timestamp - DAY]
        if any(t.entry_time < timestamp <= t.exit_time for t in rows):
            assert timestamp not in entered, "Exit-hour entry or reverse"
            continue
        side = int(signal.cross)
        if not side:
            assert timestamp not in entered, "Entry without a cross"
            continue
        closed = [t for t in rows if t.exit_time < timestamp]
        cash = float(closed[-1].end_equity) if closed else 10000.0
        detail = {}
        if not bool(signal.ready):
            counts["flat_not_ready_crosses"] += 1
            stage, reason = "ready", "not_ready"
        else:
            counts["flat_ready_crosses"] += 1
            if not side * signal.slope > summary["slope"]:
                stage, reason = "slope", "slope_rejected"
            else:
                counts["entry_attempts"] += 1
                direction = summary["direction_mode"]
                trend = summary["trend_filter"]
                ready30 = np.isfinite(signal.ma30) and np.isfinite(signal.prev_ma30)
                stop = float(signal.ma - side * 1.5 * signal.atr)
                reference = float(hourly.loc[timestamp, "open"])
                fill = reference * (1 + side * slip)
                stop_fill = stop * (1 - side * slip)
                unit_risk = side * (fill - stop_fill) + fee * (fill + stop_fill)
                if (direction == "long" and side != 1) or (direction == "short" and side != -1):
                    stage, reason = "filter", "direction_rejected"
                elif trend != "none" and not ready30:
                    stage, reason = "filter", "ma30_not_ready_rejected"
                elif (trend == "ma30_direction" and not
                      (side * (signal.close - signal.ma30) > 0 and side * (signal.ma30 - signal.prev_ma30) > 0)):
                    stage, reason = "filter", "ma30_direction_rejected"
                elif not np.isfinite(stop) or side * (reference - stop) <= 0:
                    stage, reason = "fill", "invalid_stop_rejected"
                    detail["initial_stop"] = stop
                elif cash <= 0:
                    stage, reason = "fill", "nonpositive_equity_rejected"
                elif summary["risk_fraction"] is not None and (not np.isfinite(unit_risk) or unit_risk <= 0):
                    stage, reason = "sizing", "invalid_unit_risk_rejected"
                    detail.update(entry_price=fill, initial_stop=stop, initial_stop_fill=stop_fill,
                                  initial_stop_unit_risk=unit_risk)
                else:
                    stage, reason = "fill", "filled"
                    assert timestamp in entered, f"Missing qualifying entry at {timestamp}"
                    trade = entered[timestamp]
                    for key, value in {"side": side, "cross_day": signal.timestamp, "signal_day": signal.timestamp,
                                       "entry_reason": "daily_cross", "entry_wait_days_used": 0,
                                       "entry_ma30": signal.ma30, "entry_prev_ma30": signal.prev_ma30,
                                       "entry_filter": trend, "direction_mode": direction}.items():
                        equal(getattr(trade, key), value, "entry " + key)
                    audit_quantity(trade, summary, cash)
                    detail.update({key: getattr(trade, key) for key in (
                        "entry_price", "initial_stop", "initial_stop_fill", "initial_stop_unit_risk",
                        "qty_cap", "qty", "initial_planned_risk", "initial_planned_risk_pct",
                        "initial_stop_price_nonpositive")})
        filled = reason == "filled"
        if filled:
            counts["entry_fills"] += 1
        else:
            assert timestamp not in entered, f"Rejected opportunity entered: {reason}"
            if reason in counts:
                counts[reason] += 1
        expected_events.append({"timestamp": timestamp, "signal_day": signal.timestamp,
                                "side": side, "cross": side, "entry_reason": "daily_cross",
                                "cross_day": signal.timestamp, "stage": stage, "reason": reason,
                                "status": "filled" if filled else "rejected",
                                "entry_filter": summary["trend_filter"], "direction_mode": summary["direction_mode"],
                                "entry_slope": signal.slope, "entry_close": signal.close,
                                "entry_ma": signal.ma, "entry_ma30": signal.ma30,
                                "entry_prev_ma30": signal.prev_ma30,
                                "trade_id": entered[timestamp].trade_id if filled else None,
                                "attempt_before_equity": cash, "risk_fraction": summary["risk_fraction"],
                                "notional_fraction": summary["notional_fraction"], **detail})
    assert len(events) == len(expected_events), "Opportunity event count differs"
    for actual, expected in zip(events.itertuples(index=False), expected_events):
        for key in events.columns:
            equal(getattr(actual, key), expected.get(key), "entry event " + key)
    assert counts["entry_fills"] == len(trades), "Unexplained entry"
    for key, value in counts.items():
        equal(summary[key], value, "entry counter " + key)
    return {"entries_verified": len(trades), "opportunity_events": len(events),
            "pending_candidates": 0, "delayed_confirmations": 0,
            "rejected_fill_attempts": counts["invalid_stop_rejected"] + counts["nonpositive_equity_rejected"]
                                      + counts["invalid_unit_risk_rejected"], "entry_counts": counts}



# Account reconstruction retained from the pinned independent audit; sizing,
# entry lifecycle and optional short TP dispatch are the only changed checks.
def audit_run(directory, daily, hourly, carry_daily=0.0):
    """Rebuild all ledger fields/marks; input indices are UTC timestamps."""
    directory = Path(directory)
    daily, hourly = daily.copy(), hourly.copy()
    daily.index = pd.DatetimeIndex(daily.index).as_unit("ns")
    hourly.index = pd.DatetimeIndex(hourly.index).as_unit("ns")
    summary = read_json(directory / "summary.json")
    trades, stops, marks = (read_frame(directory / name)
                            for name in ("trades.csv", "stops.csv", "equity.parquet"))
    start, end = pd.Timestamp(summary["start"]), pd.Timestamp(summary["end_exclusive"])
    h = hourly.loc[(hourly.index >= start) & (hourly.index < end)]
    assert h.index.tolist() == pd.date_range(start, end - HOUR, freq="h").tolist()
    assert summary["funding_window_verified"] is False and summary["price_only_diagnostic"] is True
    assert summary["funding_paid"] == 0 and not (directory / "funding.csv").exists()
    equal(len(trades), summary["trades"], "trade count")
    for kind, times, prices in (("open", h.index, h.open), ("hour_close", h.index + HOUR, h.close)):
        one = marks.loc[marks.kind == kind]
        assert one.timestamp.tolist() == times.tolist(), "Missing/extra hourly equity marks"
        assert np.allclose(one.price, prices, rtol=2e-10, atol=1e-14), "Mark source price mismatch"
    for kind, field in (("entry", "entry_time"), ("exit", "exit_time")):
        expected_times = trades[field].tolist() if len(trades) else []
        assert marks.loc[marks.kind == kind, "timestamp"].tolist() == expected_times
    assert marks.kind.isin(["open", "hour_close", "entry", "exit"]).all()
    if len(trades):
        assert set(stops.trade_id) == set(trades.trade_id), "Unassigned stop records"
    result = audit_entry_lifecycle(trades, daily, h, summary, read_frame(directory / "entry_events.csv"))
    cash, previous_exit, previous_interval_end = 10000.0, None, None
    fees, carry_total, verified_marks, exposure_hours = 0.0, 0.0, 0, 0
    for expected_id, trade in enumerate(trades.itertuples(index=False), 1):
        assert trade.trade_id == expected_id
        side, fee, slip = int(trade.side), summary["fee"], summary["slip"]
        if previous_exit is not None:
            assert trade.entry_time > previous_exit and trade.entry_time >= previous_interval_end
        equal(trade.entry_equity, cash, "next entry capital")
        equal(trade.entry_reference, h.loc[trade.entry_time, "open"], "entry reference")
        equal(trade.entry_price, trade.entry_reference * (1 + side * slip), "entry slippage")
        equal(trade.exit_price, trade.exit_reference * (1 - side * slip), "exit slippage")
        audit_quantity(trade, summary, cash)
        equal(trade.entry_fee, trade.qty * trade.entry_price * fee, "entry fee")
        equal(trade.exit_fee, trade.qty * trade.exit_price * fee, "exit fee")
        held = h.loc[(h.index >= trade.entry_time) & ((h.index < trade.exit_time)
                         | ((h.index == trade.exit_time) & (trade.exit_reason == "stop_intrahour")))]
        carry = held.open.to_numpy() * trade.qty * carry_daily / 24
        equal(trade.carry_paid, carry.sum(), "hourly carry cost")
        equal(trade.funding_paid, 0.0, "unverified funding not imputed")
        gross = side * trade.qty * (trade.exit_price - trade.entry_price)
        net = gross - trade.entry_fee - trade.exit_fee - trade.carry_paid
        equal(trade.gross_pnl, gross, "gross PnL")
        equal(trade.net_pnl, net, "net PnL")
        equal(trade.end_equity, cash + net, "settled capital")
        audit_account_return(trade.return_on_entry_equity, cash, trade.end_equity, net,
                             trade.entry_fee, trade.exit_fee, gross, carry)
        own_stops = stops.loc[stops.trade_id == trade.trade_id].reset_index(drop=True)
        audit_stop_path(trade, own_stops, daily, summary)
        before_exit = h.loc[(h.index >= trade.entry_time) & (h.index < trade.exit_time)]
        which = np.searchsorted(own_stops.timestamp.astype("int64"), before_exit.index.asi8,
                                side="right") - 1
        assert (which >= 0).all()
        effective = own_stops.new_stop.to_numpy()[which]
        adverse = before_exit.low.to_numpy() if side == 1 else before_exit.high.to_numpy()
        assert (side * (adverse - effective) > 0).all(), "Earlier stop hit ignored"
        if trade.exit_reason == "sample_end":
            equal(trade.exit_time, end, "sample settlement time")
            equal(trade.exit_reference, h.iloc[-1].close, "sample settlement price")
        else:
            bar = h.loc[trade.exit_time]
            if trade.exit_reason == "stop_gap":
                assert side * (bar.open - trade.stop) <= 0
                equal(trade.exit_reference, bar.open, "gap fill")
            elif trade.exit_reason == "stop_intrahour":
                assert side * (bar.open - trade.stop) > 0
                assert bar.low <= trade.stop if side == 1 else bar.high >= trade.stop
                equal(trade.exit_reference, trade.stop, "native stop fill")
                equal(trade.exit_interval_end, trade.exit_time + HOUR, "stop uncertainty interval")
            else:
                assert summary["short_exit"] != "none" and trade.exit_reason == "accel1_rsi30" and side == -1
                signal = daily.loc[pd.Timestamp(trade.tp_signal_day)]
                assert signal.rsi <= 30 and signal.accel1
                assert trade.exit_time == signal.timestamp + DAY
                expected = trade.qty * (trade.entry_price - signal.close * (1 + slip))
                expected -= trade.entry_fee + trade.qty * signal.close * (1 + slip) * fee + trade.carry_paid
                assert expected > 0 and side * (bar.open - trade.stop) > 0
                equal(trade.exit_reference, bar.open, "RSI exit fill")
        if trade.exit_reason != "stop_intrahour":
            equal(trade.exit_interval_end, trade.exit_time, "exact exit boundary")
        selected = marks.loc[(marks.side == side) & (marks.timestamp >= trade.entry_time)
                             & (marks.timestamp <= trade.exit_time)]
        assert selected.kind.isin(["entry", "open", "hour_close"]).all()
        carry_prefix = np.r_[0.0, np.cumsum(carry)]
        paid = carry_prefix[np.searchsorted(held.index.asi8, selected.timestamp.astype("int64"), side="left")]
        expected_marks = cash - trade.entry_fee - paid + side * trade.qty * (selected.price.to_numpy() - trade.entry_price)
        assert np.allclose(selected.equity, expected_marks, rtol=2e-10, atol=1e-9), "Held equity marks differ"
        verified_marks += len(selected)
        for record in own_stops.iloc[1:].itertuples(index=False):
            prior_carry = carry_prefix[np.searchsorted(held.index.asi8, record.timestamp.value, side="left")]
            close = h.loc[record.timestamp - HOUR, "close"]
            fill = close * (1 - side * slip)
            profit = side * trade.qty * (fill - trade.entry_price) - trade.entry_fee - trade.qty * fill * fee - prior_carry
            equal(record.expected_profit_at_close, profit, "closed-day expected profit")
            favorable = side * (close - trade.entry_price)
            equal(record.favorable_move_atr, favorable / trade.entry_atr, "favorable ATR distance")
            equal(record.profit_eligible, profit > 0 and favorable >= 0, "profit eligibility")
            day = daily.loc[record.signal_day]
            if summary["short_exit"] != "none" and side == -1 and day.rsi <= 30 and day.accel1 and profit > 0:
                assert trade.exit_time == record.timestamp and trade.exit_reason in {"stop_gap", "accel1_rsi30"}, (
                    "First eligible short RSI exit ignored or lost priority to intrahour stop")
        cash, previous_exit, previous_interval_end = trade.end_equity, trade.exit_time, trade.exit_interval_end
        fees += trade.entry_fee + trade.exit_fee
        carry_total += trade.carry_paid
        exposure_hours += len(held)
    flat = marks.loc[marks.side == 0]
    if len(trades):
        exits = trades.exit_time.astype("int64").to_numpy()
        flat_times = flat.timestamp.astype("int64").to_numpy()
        indexes = np.searchsorted(exits, flat_times, side="left")
        is_exit = flat.kind.to_numpy() == "exit"
        indexes[is_exit] = np.searchsorted(exits, flat_times[is_exit], side="right")
        ends = np.r_[10000.0, trades.end_equity.to_numpy()]
        expected_flat = ends[indexes]
    else:
        expected_flat = np.full(len(flat), 10000.0)
        assert stops.empty
    assert np.allclose(flat.equity, expected_flat, rtol=2e-10, atol=1e-9), "Flat equity marks differ"
    verified_marks += len(flat)
    assert verified_marks == len(marks)
    equal(cash, summary["ending_equity"], "ending account")
    equal(marks.equity.iloc[-1], cash, "last mark")
    equal((cash / 10000 - 1) * 100, summary["return_pct"], "account return")
    equity = marks.equity.to_numpy()
    mdd = np.min(equity / np.maximum.accumulate(np.r_[10000.0, equity])[1:] - 1) * 100
    equal(mdd, summary["max_drawdown_pct"], "mark drawdown")
    equal(fees, summary["fee_total"], "fees total")
    equal(carry_total, summary["carry_paid"], "carry total")
    equal(exposure_hours / len(h) * 100, summary["exposure_pct"], "exposure")
    equal(summary["delayed_entries"], int(trades.entry_reason.eq("delayed_cross").sum()) if len(trades) else 0,
          "delayed trade count")
    if len(trades):
        for field, expected in {
            "tightening_days": int(trades.tightening_days.sum()),
            "tightened_trades": int(trades.tightening_days.gt(0).sum()),
            "armed_trades": int(trades.armed.sum()), "floor_trades": int(trades.stop_floor_reached.sum()),
            "progress_armed_trades": int(trades.arm_day.notna().sum()),
            "short_tp_exits": int(trades.exit_reason.eq("accel1_rsi30").sum()),
            "win_rate_pct": float(trades.net_pnl.gt(0).mean() * 100),
            "ever_armed_trades": int(trades.ever_armed.sum()),
            "arm_count": int(trades.arm_count.sum()), "reset_count": int(trades.reset_count.sum()),
            "initial_stop_nonpositive_trades": int(trades.initial_stop_price_nonpositive.sum()),
        }.items():
            equal(summary[field], expected, "summary " + field)
        for side, prefix in ((1, "long"), (-1, "short")):
            group = trades.loc[trades.side == side]
            equal(summary[prefix + "_trades"], len(group), prefix + " count")
            equal(summary[prefix + "_pnl"], float(group.net_pnl.sum()), prefix + " PnL")
    return {**result, "trades": len(trades), "stop_records": len(stops),
            "equity_marks_independently_rebuilt": verified_marks, "status": "PASS"}


def quantity_fixture(side=1, risk=.005, fraction=1.0, scale=1.0, distance=10.0):
    """Decimal oracle for planned quantity; no engine or account replay."""
    from decimal import Decimal as D
    e, f, l, s = D(10000), D("0.0005"), D("0.0003"), D(side)
    reference, stop = D(100) * D(str(scale)), (D(100) - s * D(str(distance))) * D(str(scale))
    fill, stop_fill = reference * (1 + s * l), stop * (1 - s * l)
    unit = s * (fill - stop_fill) + f * (fill + stop_fill)
    cap = e * D(str(fraction)) / (fill * (1 + f))
    qty = cap if risk is None else min(cap, e * D(str(risk)) / unit)
    trade = SimpleNamespace(side=side, entry_reference=float(reference), initial_stop=float(stop),
                            entry_price=float(fill), entry_fee=float(qty * fill * f),
                            qty=float(qty), qty_cap=float(cap), initial_stop_fill=float(stop_fill),
                            initial_stop_unit_risk=float(unit), initial_planned_risk=float(qty * unit),
                            initial_planned_risk_pct=float(qty * unit / e * 100),
                            risk_fraction=risk, notional_fraction=fraction,
                            initial_stop_price_nonpositive=bool(stop <= 0),
                            initial_stop_risk_price=float(s * (fill - stop)),
                            initial_stop_risk_pct=float(s * (fill - stop) / fill * 100))
    summary = {"fee": float(f), "slip": float(l), "risk_fraction": risk, "notional_fraction": fraction}
    return trade, summary, 10000.0


def stop_fixture(side=1, policy="reset_on_new_extreme"):
    """22 hand-specified days cover reset, rearm, ties and reset at the floor."""
    entry = pd.Timestamp("2026-01-02T00:00Z")
    dates = pd.date_range(entry - DAY, periods=23, freq="D")
    levels = [10] * 5 + [11] * 5 + [12] * 7 + [13] * 5
    favorable = [100.0 + side * x for x in levels]
    highs = [110.0] + (favorable if side == 1 else [110.0] * 22)
    lows = [90.0] + (favorable if side == -1 else [90.0] * 22)
    daily = pd.DataFrame({"timestamp": dates, "ma": 100.0, "atr": 2.0,
                          "high": highs, "low": lows}).set_index("timestamp", drop=False)
    reset_mode = policy == "reset_on_new_extreme"
    arm_days = [5, 10, 15, 22] if reset_mode else [5]
    reset_days = [6, 11, 18] if reset_mode else []
    mults = ([1.5] * 4 + [1.3] * 5 + [1.1] * 5 + [.9, .7] + [.5] * 6 if reset_mode else
             [1.5] * 4 + [1.3, 1.1, .9, .7] + [.5] * 14)
    active = ([False] * 4 + [True] + [False] * 4 + [True] + [False] * 4 + [True] * 3
              + [False] * 4 + [True] if reset_mode else [False] * 4 + [True] * 18)
    initial = 100.0 - side * 3
    first = {"timestamp": entry, "signal_day": entry - DAY, "old_stop": initial, "new_stop": initial,
             "old_mult": 1.5, "new_mult": 1.5, "old_armed": False, "new_armed": False,
             "initialized": False, "tightened": False, "ever_armed": False, "first_arm_day": None,
             "arm_count": 0, "reset_count": 0, "armed_reset": False, "progress_policy": policy,
             "natural_candidate": initial, "stalled": False, "extreme_price": None,
             "extreme_day": None, "arm_day": None, "new_extreme": False, "no_new_extreme_days": 0,
             "full_holding_day": False, "tightening_trigger": "entry",
             "anchor_candidate": None, "anchor_decisive": False}
    records = [first]
    old_stop, old_mult, prior_active, current_arm = initial, 1.5, False, None
    for day in range(1, 23):
        recent = max(k for k in [1, 6, 11, 18] if k <= day)
        new = day == recent
        reset = day in reset_days
        if reset:
            current_arm = None
        if day in arm_days:
            current_arm = entry + (day - 1) * DAY
        tightened = mults[day - 1] < old_mult
        trigger = ("extreme_initialize" if day == 1 else "at_floor" if old_mult <= .5 else
                   ("progress_armed_daily" if prior_active else "no_new_extreme") if active[day - 1] else
                   "progress_reset" if reset else "progress_observed")
        row = {**first, "timestamp": entry + day * DAY, "signal_day": entry + (day - 1) * DAY,
               "old_stop": old_stop, "new_stop": 100.0 - side * 2 * mults[day - 1],
               "old_mult": old_mult, "new_mult": mults[day - 1], "old_armed": prior_active,
               "new_armed": active[day - 1], "initialized": True, "tightened": tightened,
               "ever_armed": day >= 5, "first_arm_day": entry + 4 * DAY if day >= 5 else None,
               "arm_count": sum(k <= day for k in arm_days), "reset_count": sum(k <= day for k in reset_days),
               "armed_reset": reset, "natural_candidate": 100.0 - side * 2 * old_mult,
               "stalled": True, "extreme_price": favorable[day - 1],
               "extreme_day": entry + (recent - 1) * DAY, "arm_day": current_arm,
               "new_extreme": new, "no_new_extreme_days": day - recent,
               "full_holding_day": True, "tightening_trigger": trigger}
        records.append(row)
        old_stop, old_mult, prior_active = row["new_stop"], row["new_mult"], row["new_armed"]
    trade = SimpleNamespace(side=side, signal_day=entry - DAY, entry_time=entry,
                            exit_time=entry + 22 * DAY + HOUR, initial_stop=initial,
                            uncapped_initial_stop=initial, entry_atr=2.0, cap_applied=False,
                            progress_source="high_low", progress_policy=policy, stop=old_stop,
                            stop_mult=.5, armed=True, initialized=True, extreme_price=favorable[-1],
                            extreme_day=entry + 17 * DAY, arm_day=current_arm, no_new_extreme_days=4,
                            tightening_days=5, stop_floor_reached=True, ever_armed=True,
                            first_arm_day=entry + 4 * DAY, arm_count=len(arm_days), reset_count=len(reset_days),
                            anchor_decisive_days=0)
    summary = {"progress_days": 4, "progress_source": "high_low", "progress_policy": policy,
               "stop_anchor": "ma", "tighten_mode": "fixed", "end_exclusive": str(entry + 24 * DAY)}
    return trade, pd.DataFrame(records), daily, summary


def entry_fixture(reason="filled", side=1, carried_second_day=False):
    """Single known opportunity with an explicitly selected expected outcome."""
    entry = pd.Timestamp("2026-01-02T00:00Z")
    trade, cost, _ = quantity_fixture(side, risk=None, distance=3.)
    summary = {**cost, "entry_wait_days": 0, "delay_hours": 0, "reverse": False,
               "entry_mode": "original", "slope": .05, "direction_mode": "both", "trend_filter": "none",
               "start": str(entry), "end_exclusive": str(entry + (2 if carried_second_day else 1) * DAY)}
    signal = {"timestamp": entry - DAY, "ready": True, "cross": side, "slope": side * .1,
              "close": 100 + side, "ma": 100., "atr": 2., "ma30": 100 - side * 5, "prev_ma30": 100 - side * 6}
    stage, reference = "fill", 100.
    if reason == "slope_rejected":
        signal["slope"], stage = side * .05, "slope"
    elif reason == "direction_rejected":
        summary["direction_mode"], stage = ("short" if side == 1 else "long"), "filter"
    elif reason == "ma30_not_ready_rejected":
        summary["trend_filter"], stage = "ma30_ready", "filter"
        signal["prev_ma30"] = np.nan
    elif reason == "ma30_direction_rejected":
        summary["trend_filter"], stage = "ma30_direction", "filter"
        signal["ma30"] = signal["prev_ma30"]
    elif reason == "invalid_stop_rejected":
        reference = 100 - side * 10
    daily = pd.DataFrame([signal]).set_index("timestamp", drop=False)
    if carried_second_day:
        daily.loc[entry] = {**signal, "timestamp": entry, "cross": -side, "slope": -side * .1}
    hourly = pd.DataFrame({"open": reference}, index=pd.date_range(entry, pd.Timestamp(summary["end_exclusive"]) - HOUR, freq="h"))
    filled = reason == "filled"
    event = {key: None for key in ENTRY_COLUMNS}
    event.update(timestamp=entry, signal_day=entry - DAY, side=side, cross=side,
                 entry_reason="daily_cross", cross_day=entry - DAY, stage=stage, reason=reason,
                 status="filled" if filled else "rejected", entry_filter=summary["trend_filter"],
                 direction_mode=summary["direction_mode"], entry_slope=signal["slope"],
                 entry_close=signal["close"], entry_ma=signal["ma"], entry_ma30=signal["ma30"],
                 entry_prev_ma30=signal["prev_ma30"], attempt_before_equity=10000.,
                 risk_fraction=None, notional_fraction=1.)
    if filled:
        trade.trade_id, trade.entry_time, trade.exit_time = 1, entry, entry + (DAY if carried_second_day else 12 * HOUR)
        trade.cross_day = trade.signal_day = entry - DAY
        trade.entry_reason, trade.entry_wait_days_used = "daily_cross", 0
        trade.entry_ma30, trade.entry_prev_ma30 = signal["ma30"], signal["prev_ma30"]
        trade.entry_filter, trade.direction_mode = summary["trend_filter"], summary["direction_mode"]
        trade.end_equity = 10000.
        for key in ("entry_price", "initial_stop", "initial_stop_fill", "initial_stop_unit_risk",
                    "qty_cap", "qty", "initial_planned_risk", "initial_planned_risk_pct", "initial_stop_price_nonpositive"):
            event[key] = getattr(trade, key)
        event["trade_id"] = 1
        trades = pd.DataFrame([vars(trade)])
    else:
        trades = pd.DataFrame()
        if reason == "invalid_stop_rejected":
            event["initial_stop"] = 100 - side * 3
    counters = dict.fromkeys(("flat_ready_crosses", "flat_not_ready_crosses", "entry_attempts", "entry_fills",
                             "slope_rejected", "direction_rejected", "ma30_not_ready_rejected",
                             "ma30_direction_rejected", "invalid_stop_rejected", "nonpositive_equity_rejected",
                             "invalid_unit_risk_rejected", "wait_candidates_created"), 0)
    counters["flat_ready_crosses"] = 1
    counters["entry_attempts"] = int(reason != "slope_rejected")
    counters["entry_fills"] = int(filled)
    if not filled:
        counters[reason] = 1
    summary.update(counters)
    return trades, daily, hourly, summary, pd.DataFrame([event])


def self_checks():
    assert sha(Path(prior.__file__)) == BASE_AUDIT_SHA
    checks = []
    # Independent constant-carry case exposes subtraction/cancellation without
    # importing a simulator or reading one of the strategy result accounts.
    for hours in (0, 243, 10392):
        for equity in (100., 10000., 1e8):
            entry_fee, exit_fee, gross = equity * .000018, equity * .0000179, equity * .000245
            carry = np.full(hours, equity * .00000072)
            end = equity - entry_fee
            for paid in carry:
                end -= paid
            end += gross - exit_fee
            net = gross - entry_fee - exit_fee - math.fsum(carry)
            actual = (end - equity) / equity
            audit_account_return(actual, equity, end, net, entry_fee, exit_fee, gross, carry)
            checks.append(f"return_roundoff_{hours}_{equity}")
            for label, changed_actual, changed_end, changed_net in (
                    ("saved_ratio", actual + 1e-10, end, net),
                    ("net_amount", actual, end, net + equity * 1e-6),
                    ("coordinated_balance", actual + 1e-6, end + equity * 1e-6, net)):
                try:
                    audit_account_return(changed_actual, equity, changed_end, changed_net,
                                         entry_fee, exit_fee, gross, carry)
                except AssertionError:
                    checks.append(f"reject_return_{label}_{hours}_{equity}")
                else:
                    raise AssertionError("Return mutation escaped: " + label)
    for side in (1, -1):
        for scale in (1.0, 1e-8, 1e6):
            for risk, fraction, distance in ((None, 1., 10.), (.005, 1., 10.),
                                             (None, 1 / 30, 10.), (.005, 1., .001), (.005, 1., 120.)):
                fixture = quantity_fixture(side, risk, fraction, scale, distance)
                audit_quantity(*fixture)
                checks.append(f"quantity_{side}_{scale}_{risk}_{fraction}_{distance}")
        for policy in ("permanent", "reset_on_new_extreme"):
            audit_stop_path(*stop_fixture(side, policy))
            checks.append(f"22day_stop_{side}_{policy}")
    for key, factor in (("qty", 1.2), ("initial_stop_unit_risk", .9), ("initial_planned_risk_pct", 2.0)):
        fixture = quantity_fixture()
        setattr(fixture[0], key, getattr(fixture[0], key) * factor)
        try:
            audit_quantity(*fixture)
        except AssertionError:
            checks.append("reject_quantity_" + key)
        else:
            raise AssertionError("Quantity mutation escaped: " + key)
    for day, key, value in ((6, "new_armed", True), (6, "new_mult", 1.5), (10, "new_armed", False),
                             (18, "armed_reset", False), (18, "arm_day", pd.Timestamp("2026-01-06T00:00Z")),
                             (22, "arm_count", 1), (5, "signal_day", pd.Timestamp("2026-01-07T00:00Z"))):
        fixture = stop_fixture()
        fixture[1].at[day, key] = value
        try:
            audit_stop_path(*fixture)
        except AssertionError:
            checks.append(f"reject_stop_{day}_{key}")
        else:
            raise AssertionError(f"Stop mutation escaped: {day}/{key}")
    for side in (1, -1):
        for reason in ("filled", "slope_rejected", "direction_rejected", "ma30_not_ready_rejected",
                       "ma30_direction_rejected", "invalid_stop_rejected"):
            audit_entry_lifecycle(*entry_fixture(reason, side))
            checks.append(f"entry_{side}_{reason}")
        audit_entry_lifecycle(*entry_fixture(side=side, carried_second_day=True))
        checks.append(f"entry_exit_midnight_does_not_reopen_{side}")
    for key, value in (("reason", "filled"), ("entry_slope", .2), ("attempt_before_equity", 9999.)):
        fixture = entry_fixture("slope_rejected")
        fixture[4].at[0, key] = value
        try:
            audit_entry_lifecycle(*fixture)
        except AssertionError:
            checks.append("reject_entry_event_" + key)
        else:
            raise AssertionError("Event mutation escaped: " + key)
    return {"status": "PASS", "audit_script_sha256": sha(Path(__file__)),
            "base_audit_script_sha256": BASE_AUDIT_SHA, "simulator_called": False,
            "check_count": len(checks), "checks": checks}


def audit_coin(item, inputs, original, results, cases, source, summary=None, stress=None):
    row = SimpleNamespace(**item)
    daily, hourly, windows = prior.load_market_inputs(inputs, original, row, {"main/" + row.symbol: source})
    daily = daily.copy()
    daily["ma30"] = daily.close.rolling(30).mean()
    daily["prev_ma30"] = daily.ma30.shift()
    daily["ma30_ready"] = daily.ma30.notna() & daily.prev_ma30.notna()
    assert not daily.ma30_ready.iloc[:30].any() and daily.ma30_ready.iloc[30:].all()
    used = read_json(results / "inputs_used" / (row.slug + ".json"))
    assert used["input_source"] == source and used["selected_segment_id"] == row.selected_segment_id
    assert used["market_source"] == str((original / "market" / row.slug).relative_to(LAB))
    assert used["original_features_exact"]
    assert set(used["windows"]) == set(windows)
    for name, bounds in windows.items():
        assert list(map(pd.Timestamp, used["windows"][name])) == list(map(pd.Timestamp, bounds))
    coin = {"symbol": row.symbol, "cohort": row.cohort, "runs": 0, "trades": 0,
            "stop_records": 0, "equity_marks": 0, "opportunity_events": 0,
            "main_rows": 0, "stress_rows": 0, "by_case": {}}
    directories = []
    scenarios = [("runs", window, bounds, 0.0) for window, bounds in windows.items()]
    scenarios += [("sensitivity", name, windows["full"], carry) for name, carry in
                  (("slippage_10bp", 0.0), ("carry_5bp_day", 0.0005))]
    for case, config in cases.items():
        coin["by_case"][case] = {"runs": 0, "trades": 0, "opportunity_events": 0}
        for group, name, bounds, carry in scenarios:
            directory = results / group / row.slug / case / name
            saved = read_json(directory / "summary.json")
            for key, value in config.items():
                if group == "sensitivity" and name == "slippage_10bp" and key == "slip":
                    value = .001
                equal(saved[key], value, "frozen parameter " + key)
            assert [pd.Timestamp(saved["start"]), pd.Timestamp(saved["end_exclusive"])] == list(map(pd.Timestamp, bounds))
            checked = audit_run(directory, daily, hourly, carry)
            table = summary if group == "runs" else stress
            if table is not None:
                selectors = {"symbol": row.symbol, "case_id": case, "cohort": row.cohort,
                             "window" if group == "runs" else "scenario": name}
                prior.compare_summary_row(table, selectors, saved)
            coin["runs"] += 1
            coin["trades"] += checked["trades"]
            coin["stop_records"] += checked["stop_records"]
            coin["equity_marks"] += checked["equity_marks_independently_rebuilt"]
            coin["opportunity_events"] += checked["opportunity_events"]
            coin["main_rows" if group == "runs" else "stress_rows"] += 1
            for key in ("runs", "trades", "opportunity_events"):
                coin["by_case"][case][key] += 1 if key == "runs" else checked[key]
            directories.append(str(directory.relative_to(results)))
    return coin, directories


def expected_cases(original_manifest):
    base = dict(next(c["config"] for c in original_manifest["cases"] if c["case_id"] == "H4_D0"))
    base.update(direction_mode="both", trend_filter="none", risk_fraction=None,
                notional_fraction=1.0, progress_policy="permanent")
    differences = {
        "A_LONG": {"direction_mode": "long"},
        "A_SHORT": {"direction_mode": "short"},
        "A_SHORT_NO_TP": {"direction_mode": "short", "short_exit": "none"},
        "B_MA30_READY": {"trend_filter": "ma30_ready"},
        "B_MA30": {"trend_filter": "ma30_direction"},
        "C_RISK005": {"risk_fraction": .005},
        "C_SMALL": {"notional_fraction": 1 / 30},
        "D_RESET": {"progress_policy": "reset_on_new_extreme"},
        "D_NO_TP": {"short_exit": "none"},
    }
    return {name: {**base, **changes} for name, changes in differences.items()}


def audit_all(inputs, original, results, workers=4, checkpoints=None):
    assert 1 <= workers <= 4
    done = read_json(results / "completion.json")
    assert done["complete"] and done["coins_failed"] == 0, "Results are not complete"
    assert done["old_v1_v3_market_runs"] == done["buyhold_runs"] == 0 and done["new_cases"] == 9
    proof = self_checks()
    manifest = read_json(results / "run_manifest.json")
    old_manifest = read_json(original / "run_manifest.json")
    prior_report_path = FAMILY / "artifacts/audit_results_20260909.json"
    assert sha(prior_report_path) == PRIOR_REPORT_SHA, "Original full audit report changed"
    prior_report = read_json(prior_report_path)
    assert prior_report["status"] == "PASS" and not prior_report["simulator_called"]
    assert sha(inputs / "checksums.json") == manifest["input_checksums_sha256"] == prior_report["input_manifest_sha256"]
    assert sha(inputs / "frozen_plan.json") == manifest["input_plan_sha256"]
    assert read_json(inputs / "frozen_plan.json") == manifest["input_plan"]
    assert sha(original / "artifact_checksums.json") == manifest["original_result_manifest_sha256"] == prior_report["result_manifest_sha256"]
    input_count = prior.verify_hash_map(inputs)
    input_provenance = prior.audit_input_provenance(inputs)
    print(f"VERIFIED {input_count} frozen input files", flush=True)
    for role in ("engine", "engine_pin", "contract", "run_script"):
        assert sha(LAB / manifest[role + "_path"]) == manifest[role + "_sha256"], role
    pin = read_json(LAB / manifest["engine_pin_path"])
    for key in ("engine_path", "engine_sha256", "contract_sha256"):
        assert pin[key] == manifest[key]
    for role in ("common", "run_market"):
        assert sha(Path(__file__).with_name(role + ".py")) == manifest[role + "_sha256"]
    assert not manifest["funding_window_verified"] and not manifest["pit_universe_proven"]
    assert not manifest["portfolio_replay"]
    cases = {c["case_id"]: c["config"] for c in manifest["cases"]}
    assert len(manifest["cases"]) == 9 and cases == expected_cases(old_manifest)
    assert manifest["reused_without_market_replay"] == {"V3": "H4_D0", "V1": "F0", "buy_hold": "BUY_HOLD"}
    for path, digest in manifest["verified_original_files"].items():
        assert sha(LAB / path) == digest, "Original source changed: " + path
    # Old accounts are hash-checked only. No old-account reconstruction is run.
    old_checks = read_json(original / "artifact_checksums.json")
    reused = {}
    common_names = {"run_manifest.json", "scope.csv", "summary.csv", "stress.csv", "buy_hold.csv",
                    "completion.json", "execution_failures.json", "hype_original_controls.json"}
    for name, digest in old_checks.items():
        parts = Path(name).parts
        wanted = (name in common_names or parts[0] in {"market", "buy_hold"}
                  or (parts[0] in {"runs", "sensitivity"} and len(parts) > 2
                      and parts[2] in {"F0", "H4_D0"}))
        if wanted:
            assert sha(original / name) == digest, "Reused V1/V3 file changed: " + name
            reused[name] = digest
    result_count = prior.verify_hash_map(results, "artifact_checksums.json")
    print(f"VERIFIED {len(reused)} reused original files and {result_count} new result files", flush=True)
    old_scope, counts = prior.audit_scope(inputs, original, old_manifest)
    scope, new_counts = prior.audit_scope(inputs, results, manifest)
    pd.testing.assert_frame_equal(old_scope, scope, check_exact=True)
    assert counts == new_counts == {"main_full": 346, "partial": 193, "short": 72, "excluded": 41}
    assert read_json(results / "execution_failures.json") == []
    assert not (results / "buy_hold").exists() and not (results / "market").exists()
    summary, stress = (read_frame(results / name) for name in ("summary.csv", "stress.csv"))
    assert set(summary.case_id) == set(stress.case_id) == set(cases)
    assert len(summary) == 1689 * 9 and len(stress) == 1222 * 9
    for case in cases:
        assert summary.case_id.eq(case).sum() == 1689 and stress.case_id.eq(case).sum() == 1222
    frames = read_json(inputs / "frames_manifest.json")
    per_coin, verified_dirs = [], set()
    jobs = [(item, inputs, original, results, cases, frames["main/" + item["symbol"]],
             summary.loc[summary.symbol == item["symbol"]], stress.loc[stress.symbol == item["symbol"]])
            for item in scope.loc[scope.cohort != "excluded"].to_dict("records")]
    checkpoint_identity = {
        "schema": "four_tests_independent_account_pass_v1",
        "audit_script_sha256": sha(Path(__file__)), "base_audit_script_sha256": BASE_AUDIT_SHA,
        "prior_audit_report_sha256": PRIOR_REPORT_SHA,
        "input_manifest_sha256": sha(inputs / "checksums.json"),
        "original_result_manifest_sha256": sha(original / "artifact_checksums.json"),
        "new_result_manifest_sha256": sha(results / "artifact_checksums.json"),
        "new_run_manifest_sha256": sha(results / "run_manifest.json"),
        "reused_original_hash_map_sha256": prior.canonical_sha(reused),
        "input_root": str(inputs), "original_root": str(original), "result_root": str(results),
    }
    checkpoint_fingerprint = prior.canonical_sha(checkpoint_identity)
    resumed = 0
    if checkpoints is not None:
        checkpoints.mkdir(parents=True, exist_ok=True)
        identity_path = checkpoints / "identity.json"
        if identity_path.exists():
            assert read_json(identity_path) == checkpoint_identity, "Checkpoint source identity changed"
        else:
            with identity_path.open("x") as handle:
                json.dump(checkpoint_identity, handle, indent=2, allow_nan=False)
                handle.write("\n")
        expected_names = {item[0]["slug"] + ".json" for item in jobs} | {"identity.json"}
        assert {p.name for p in checkpoints.glob("*.json")} <= expected_names

    def collect(value, checkpoint_slug=None):
        coin, directories = value
        if checkpoint_slug is not None:
            payload = {"status": "PASS", "identity_sha256": checkpoint_fingerprint,
                       "coin": coin, "directories": directories}
            record = {**payload, "payload_sha256": prior.canonical_sha(payload)}
            path = checkpoints / (checkpoint_slug + ".json")
            assert not path.exists(), "Do not overwrite a completed coin audit"
            temporary = path.with_suffix(".json.tmp")
            with temporary.open("w") as handle:
                json.dump(record, handle, indent=2, allow_nan=False)
                handle.write("\n")
            temporary.replace(path)
        per_coin.append(coin)
        verified_dirs.update(results / name for name in directories)
        if len(per_coin) % 20 == 0:
            print(f"AUDITED {len(per_coin)} coins; {sum(c['runs'] for c in per_coin)} accounts; "
                  f"{sum(c['trades'] for c in per_coin)} trades", flush=True)

    remaining_jobs = []
    for args in jobs:
        path = checkpoints / (args[0]["slug"] + ".json") if checkpoints is not None else None
        if path is not None and path.exists():
            record = read_json(path)
            digest = record.pop("payload_sha256")
            assert prior.canonical_sha(record) == digest, "Checkpoint content changed"
            assert record["status"] == "PASS" and record["identity_sha256"] == checkpoint_fingerprint
            assert record["coin"]["symbol"] == args[0]["symbol"]
            assert record["coin"]["cohort"] == args[0]["cohort"]
            collect((record["coin"], record["directories"]))
            resumed += 1
        else:
            remaining_jobs.append(args)
    if workers == 1:
        for args in remaining_jobs:
            collect(audit_coin(*args), args[0]["slug"] if checkpoints is not None else None)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            pending = {pool.submit(audit_coin, *args): args[0] for args in remaining_jobs}
            for future in as_completed(pending):
                try:
                    collect(future.result(), pending[future]["slug"] if checkpoints is not None else None)
                except Exception as exc:
                    for outstanding in pending:
                        outstanding.cancel()
                    raise AssertionError(f"Independent audit failed for {pending[future]['symbol']}: {exc}") from exc
    per_coin.sort(key=lambda item: item["symbol"])
    expected_dirs = {p.parent for p in results.glob("runs/*/*/*/summary.json")}
    expected_dirs |= {p.parent for p in results.glob("sensitivity/*/*/*/summary.json")}
    assert expected_dirs == verified_dirs
    assert {p.stem for p in (results / "inputs_used").glob("*.json")} == set(scope.loc[scope.cohort != "excluded", "slug"])
    accounts = sum(c["runs"] for c in per_coin)
    assert accounts == 26199 and len(per_coin) == done["coins_completed"] == 611
    assert sum(c["main_rows"] for c in per_coin) == done["strategy_window_runs"] == 15201
    assert sum(c["stress_rows"] for c in per_coin) == done["stress_runs"] == 10998
    return {"status": "PASS", "audit_script_sha256": sha(Path(__file__)),
            "base_audit_script_sha256": BASE_AUDIT_SHA, "prior_audit_report_sha256": PRIOR_REPORT_SHA,
            "input_manifest_sha256": sha(inputs / "checksums.json"),
            "original_result_manifest_sha256": sha(original / "artifact_checksums.json"),
            "result_manifest_sha256": sha(results / "artifact_checksums.json"),
            "engine_sha256": manifest["engine_sha256"], "engine_pin_sha256": manifest["engine_pin_sha256"],
            "hashed_input_files": input_count, "hashed_new_result_files": result_count,
            "hashed_reused_original_files": len(reused),
            "reused_hash_map_canonical_sha256": prior.canonical_sha(reused),
            "input_provenance": input_provenance, "self_checks": proof,
            "observed_contracts": 874, "included_coins": 652, "cohort_counts": counts,
            "cases": list(cases), "coins_independently_audited": len(per_coin),
            "strategy_accounts_audited": accounts, "trades_audited": sum(c["trades"] for c in per_coin),
            "stop_records_audited": sum(c["stop_records"] for c in per_coin),
            "opportunity_events_independently_rebuilt": sum(c["opportunity_events"] for c in per_coin),
            "equity_marks_independently_rebuilt": sum(c["equity_marks"] for c in per_coin),
            "per_coin": per_coin, "v1_v3_reused_via_hash_only": True, "old_accounts_recomputed": 0,
            "simulator_called": False, "workers": workers, "funding_window_verified": False,
            "checkpoint_identity": checkpoint_identity, "checkpoint_identity_sha256": checkpoint_fingerprint,
            "checkpoint_directory": str(checkpoints) if checkpoints is not None else None,
            "coins_reused_from_identical_pass_checkpoints": resumed,
            "coins_audited_this_invocation": len(per_coin) - resumed,
            "numeric_reconciliation": {
                "initial_attempt": "artifacts/audit_four_tests_20260910_initial_failure.json",
                "diagnosis": "artifacts/audit_four_tests_20260910_ong_numeric_diagnosis.json",
                "ratio_check": "strict saved balance-difference identity plus independent net/entry with bounded binary64 accumulation error",
                "dollar_and_price_tolerances_unchanged": True}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=INPUTS)
    parser.add_argument("--original", type=Path, default=ORIGINAL)
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--self-check-only", action="store_true")
    parser.add_argument("--checkpoints", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve old audit output and choose a fresh filename")
    report = self_checks() if args.self_check_only else audit_all(
        args.inputs.resolve(), args.original.resolve(), args.results.resolve(), args.workers,
        args.checkpoints.resolve() if args.checkpoints else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({k: v for k, v in report.items() if k not in {"per_coin", "input_provenance", "self_checks"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
