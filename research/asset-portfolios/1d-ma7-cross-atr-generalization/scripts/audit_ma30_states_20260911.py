"""Independent audit of adaptation learning, rule selection and routed accounts.

The monetary reconstruction below is copied from the SHA-pinned independent
2026-09-10 audit; only admission and per-trade exit dispatch are changed. The
strategy simulator and learner implementation are never imported or called.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import time
import traceback

import numpy as np
import pandas as pd
import audit_exit_state_machine_20260910 as previous

prior, money = previous.prior, previous.money
LAB, FAMILY, DAY, HOUR = previous.LAB, previous.FAMILY, previous.DAY, previous.HOUR
ROUND = FAMILY / "artifacts/ma30_states_20260911"
OLD = FAMILY / "artifacts/state_machine_20260910"
equal, sha, read_json = previous.equal, previous.sha, previous.read_json
write_json = previous.write_json
audit_quantity, audit_account_return = money.audit_quantity, money.audit_account_return
ENTRY_COLUMNS = money.ENTRY_COLUMNS
ROUTE_COLUMNS = {"admission_allowed", "admission_rule_id", "admission_signal_day", "exit_route", "route_short_exit"}


def read_frame(path):
    frame = previous.read_frame(path)
    for column in ("admission_signal_day", "decision_time", "train_cutoff", "label_end"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], utc=True, format="mixed").dt.as_unit("ns")
    return frame


def audit_stop_path(trade, records, daily, summary):
    route = trade.exit_route
    assert route in {"v3", "defense", "extension"}
    expected_short = "none" if route == "extension" else "accel1_rsi30"
    assert trade.route_short_exit == expected_short
    for field in ROUTE_COLUMNS:
        for actual in records[field]:
            equal(actual, getattr(trade, field), "Position route immutable " + field)
    cfg = {**summary, "exit_state_policy": route, "short_exit": expected_short}
    previous.audit_stop_path(trade, records, daily, cfg)


def audit_entry_lifecycle(trades, daily, hourly, summary, events):
    """Reconstruct every flat crossing and its first terminal rejection stage."""
    assert summary["entry_wait_days"] == summary["delay_hours"] == 0
    assert not summary["reverse"] and summary["entry_mode"] == "original"
    assert set(events.columns) == ENTRY_COLUMNS | ROUTE_COLUMNS, "Opportunity schema missing/extra fields"
    start, end = pd.Timestamp(summary["start"]), pd.Timestamp(summary["end_exclusive"])
    rows = list(trades.itertuples(index=False))
    entered = {row.entry_time: row for row in rows}
    assert len(entered) == len(rows)
    counts = dict.fromkeys(("flat_ready_crosses", "flat_not_ready_crosses", "entry_attempts", "entry_fills",
                           "slope_rejected", "direction_rejected", "ma30_not_ready_rejected",
                           "ma30_direction_rejected", "invalid_stop_rejected", "nonpositive_equity_rejected",
                           "invalid_unit_risk_rejected", "wait_candidates_created", "admission_rejected"), 0)
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
        label = "long" if side == 1 else "short"
        allowed = getattr(signal, "admit_" + label)
        assert isinstance(allowed, (bool, np.bool_)), "Nonboolean admission"
        route = getattr(signal, "route_" + label)
        assert route in {"v3", "defense", "extension"}
        routing = {"admission_allowed": bool(allowed), "admission_rule_id": getattr(signal, "rule_id_" + label),
                   "admission_signal_day": signal.timestamp, "exit_route": route,
                   "route_short_exit": "none" if route == "extension" else "accel1_rsi30"}
        detail = dict(routing)
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
                elif not allowed:
                    stage, reason = "admission", "admission_rejected"
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
                    for key, expected in routing.items():
                        equal(getattr(trade, key), expected, "entry routing " + key)
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



def audit_routed_account(directory, daily, hourly, carry_daily=0.0):
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
                assert trade.route_short_exit != "none" and trade.exit_reason == "accel1_rsi30" and side == -1
                signal = daily.loc[pd.Timestamp(trade.tp_signal_day)]
                assert signal.rsi <= 30 and signal.accel1
                if summary.get("ma30_mode", "none") != "none":
                    last=own_stops.iloc[-1]
                    assert not bool(last.get("m30_suppress_short_tp",False)), "Suppressed RSI order executed"
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
            if (trade.route_short_exit != "none" and side == -1 and day.rsi <= 30 and day.accel1 and profit > 0
                    and not (summary.get("ma30_mode", "none") != "none" and getattr(record, "m30_suppress_short_tp", False))):
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



LEGACY_ROUTE_STOP_AUDIT = audit_stop_path

class MA30ClosedState(previous.ClosedState):
    def observe_ma30(self, day, extreme, stale, mode, net_profit):
        out=super().observe(day,extreme,stale)
        s=self.side;a=float(day.atr);c=float(day.close)
        q=s*(float(day.ma30)-float(day.prev_ma30))/a
        x=s*(c-float(day.ma30))/a
        conflict=q<=-.05;aligned=q>=.05 and x>0
        pressure=(s*(c-float(day.ma))<=0 or s*(extreme-c)/a>=.75
                  or (self.held>=3 and out['sm_efficiency3']<=.2 and s*(c-self.entry_fill)<=0))
        defend=bool(mode in ('defense','both') and conflict and pressure)
        healthy=bool(mode in ('extend','both') and aligned and net_profit and out['sm_healthy'])
        event='unchanged'
        if mode in ('extend','both'):
            if self.phase=='NORMAL':
                if aligned and net_profit and out['sm_acceleration'] and out['sm_extended']:
                    self.phase='WATCH';self.began=day.timestamp;self.watch_atr=a
                    self.watch_extreme=float(day.high if s==1 else day.low)
                    self.peak_speed=max(s*float(day.audit_delta)/a,0.);event='watch_started'
            else:
                observed=float(day.high if s==1 else day.low)
                self.watch_extreme=(max if s==1 else min)(observed,self.watch_extreme)
                velocity=s*float(day.audit_delta)/self.watch_atr;self.peak_speed=max(velocity,self.peak_speed)
                retrace=s*(self.watch_extreme-c)/self.watch_atr
                if self.phase=='WATCH':
                    if retrace>=.75 and velocity<=self.peak_speed/2:
                        self.phase='PROTECT';self.protect_day=day.timestamp;event='exhaustion_protect'
                    elif not aligned or (out['sm_ma_distance']<2 and not (day.rsi>=80 if s==1 else day.rsi<=20)):
                        event='watch_alignment_lost' if not aligned else 'watch_cleared';self.phase='NORMAL'
                        self.began=self.watch_atr=self.watch_extreme=self.peak_speed=None
        protect=self.phase=='PROTECT'
        suppress=bool(not protect and mode in ('extend','both') and net_profit and (healthy or (self.phase=='WATCH' and aligned)))
        self.defense_days+=int(defend)-int(out['sm_defense'])
        self.healthy_days+=int(healthy)-int(out['sm_healthy'])
        self.protect_days+=int(protect)-int(out['sm_protect'])
        status=next((name for yes,name in [(protect,'PROTECT'),(defend,'DEFENSE'),(self.phase=='WATCH','WATCH'),(healthy,'HEALTHY'),(self.held<3,'PROBE')] if yes),'ORDINARY')
        out.update(sm_state=status,sm_transition=event,sm_defense=defend,sm_healthy=healthy,
            sm_watch=self.phase,sm_protect=protect,sm_watch_start=self.began,sm_watch_atr=self.watch_atr,
            sm_watch_extreme=self.watch_extreme,sm_peak_speed=self.peak_speed,
            sm_defensive_stop=c-s*.5*a if defend else None,
            sm_protection_stop=self.watch_extreme-s*self.watch_atr if protect else None,
            m30_q=q,m30_x=x,m30_conflict=bool(conflict),m30_aligned=bool(aligned),
            m30_pressure=bool(pressure),m30_profit_eligible=bool(net_profit),m30_suppress_short_tp=suppress)
        return out

def audit_stop_path(trade,records,daily,summary):
    if summary.get('ma30_mode','none')=='none':
        return LEGACY_ROUTE_STOP_AUDIT(trade,records,daily,summary)
    assert trade.exit_route=='v3' and trade.route_short_exit=='accel1_rsi30'
    mode=summary['ma30_mode'];s=int(trade.side);fee=summary['fee'];slip=summary['slip']
    signal=daily.loc[trade.signal_day];initial=float(signal.ma-s*1.5*signal.atr)
    equal(trade.initial_stop,initial,'initial stop');equal(trade.entry_atr,signal.atr,'entry ATR')
    dates=pd.date_range(trade.entry_time+DAY,trade.exit_time.floor('D'),freq='D')
    dates=dates[dates<pd.Timestamp(summary['end_exclusive'])]
    assert records.timestamp.tolist()==[trade.entry_time,*dates]
    old_stop=initial;mult=1.5;armed=False;extreme=extreme_day=arm_day=None;count=decreases=tp_count=0
    state=MA30ClosedState(s,float(trade.entry_reference),float(trade.entry_price),'v3');last=None
    first=records.iloc[0]
    for k,v in {'new_stop':initial,'old_stop':initial,'new_mult':1.5,'old_mult':1.5,'tightened':False,'full_holding_day':False}.items():equal(first[k],v,'initial '+k)
    for i,actual in enumerate(records.iloc[1:].itertuples(index=False)):
        day=daily.loc[actual.signal_day];assert actual.timestamp==actual.signal_day+DAY
        natural=float(day.ma-s*mult*day.atr);was_armed=armed
        observed=float(day.high if s==1 else day.low)
        if i==0:extreme=observed;extreme_day=actual.signal_day;count=0;fresh=True;trigger='extreme_initialize';decrease=False
        else:
            fresh=s*(observed-extreme)>0
            if fresh:extreme=observed;extreme_day=actual.signal_day;count=0
            else:count+=1
            if not armed and count>=4:armed=True;arm_day=actual.signal_day
            decrease=armed and mult>.5
            trigger='at_floor' if mult<=.5 else ('progress_armed_daily' if was_armed else 'no_new_extreme') if armed else 'progress_observed'
        fill=float(day.close)*(1-s*slip);profit=s*trade.qty*(fill-trade.entry_price)-trade.entry_fee-trade.qty*fill*fee
        eligible=profit>0 and s*(day.close-trade.entry_price)>=0
        z=state.observe_ma30(day,extreme,count,mode,eligible)
        if z['sm_defense'] or z['sm_protect']:
            decrease=mult>.5;trigger='state_protect' if z['sm_protect'] else 'state_defense'
        elif z['sm_healthy']:decrease=False;trigger='healthy_pause'
        old_mult=mult
        if decrease:mult=max(.5,round(mult-.2,10));decreases+=1
        candidates=[old_stop,float(day.ma-s*mult*day.atr)]+[z[k] for k in ['sm_defensive_stop','sm_protection_stop'] if z[k] is not None]
        stop=(max if s==1 else min)(candidates)
        expected={'old_stop':old_stop,'new_stop':stop,'old_mult':old_mult,'new_mult':mult,
            'old_armed':was_armed,'new_armed':armed,'initialized':True,'extreme_price':extreme,
            'extreme_day':extreme_day,'arm_day':arm_day,'no_new_extreme_days':count,
            'new_extreme':fresh,'tightened':decrease,'tightening_trigger':trigger,'natural_candidate':natural,
            'stalled':s*(natural-old_stop)<=1e-12*max(1.,abs(old_stop)),
            'full_holding_day':True,'armed_reset':False,'ever_armed':armed,'first_arm_day':arm_day,
            'arm_count':int(armed),'reset_count':0,'anchor_candidate':None,'anchor_decisive':False,**z}
        gap_first=trade.exit_time==actual.timestamp and trade.exit_reason=='stop_gap'
        suppressed=bool(s==-1 and day.rsi<=30 and day.accel1 and profit>0 and z['m30_suppress_short_tp'] and not gap_first)
        expected['m30_short_tp_actually_suppressed']=suppressed;tp_count+=int(suppressed)
        for k,v in expected.items():equal(getattr(actual,k),v,'MA30 closed state '+k)
        assert s*(stop-old_stop)>=0 and .5<=mult<=old_mult<=1.5
        old_stop=stop;last=z
    final={'stop':old_stop,'stop_mult':mult,'armed':armed,'initialized':len(records)>1,
        'extreme_price':extreme,'extreme_day':extreme_day,'arm_day':arm_day,
        'no_new_extreme_days':count,'tightening_days':decreases,'stop_floor_reached':mult==.5,
        'ever_armed':armed,'first_arm_day':arm_day,'arm_count':int(armed),'reset_count':0}
    if last:
        final.update(sm_state=last['sm_state'],sm_held_days=state.held,sm_defense_days=state.defense_days,
            sm_healthy_days=state.healthy_days,sm_protect_days=state.protect_days,sm_watch=state.phase,
            m30_suppress_short_tp=last['m30_suppress_short_tp'])
    for k,v in final.items():equal(getattr(trade,k),v,'MA30 final '+k)
    value=getattr(trade,'m30_short_tp_suppressed_count',None)
    equal(0 if value is None or pd.isna(value) else value,tp_count,'actual postponed RSI orders')

DEFINITIONS=[('cycle_2020_2024','2020-01-01','2025-01-01'),('calendar_2021_2023','2021-01-01','2024-01-01'),
 ('calendar_2023_2025','2023-01-01','2026-01-01'),('phase_2020_2021','2020-01-01','2022-01-01'),
 ('phase_2022','2022-01-01','2023-01-01'),('phase_2023_2024','2023-01-01','2025-01-01'),
 ('phase_2025_2026','2025-01-01','2026-09-05')]+[(f'year_{y}',f'{y}-01-01',f'{y+1}-01-01' if y<2026 else '2026-09-05') for y in range(2019,2027)]
MODES={'C_DEFENSE':'none','C_EXTENSION':'none','M_SKIP':'none','M_DEFEND':'defense','M_EXTEND':'extend','M_MANAGE':'both','M_FULL':'both','M_REPAIR':'both','M_BTC':'both'}

def independent_schedule(d,actual,arm):
    assert len(d)==len(actual) and actual.timestamp.tolist()==d.timestamp.tolist()
    q=d.ma30.sub(d.prev_ma30).div(d.atr)
    for side,label in [(1,'long'),(-1,'short')]:
        sq=side*q;x=side*(d.close-d.ma30)/d.atr
        conflict=sq<=-.05;repair=conflict&(sq>sq.shift())&(x>0)
        allow=pd.Series(True,index=d.index)
        if arm in ('M_SKIP','M_FULL','M_BTC'):allow=~conflict
        if arm=='M_REPAIR':allow=~conflict|repair
        if arm=='M_BTC':allow &= d[label+'_btc_return60'].notna()&d[label+'_btc_return60'].ge(0)
        ready=pd.Series(np.arange(len(d))>=89,index=d.index)&sq.notna()&x.notna()
        route={'C_DEFENSE':'defense','C_EXTENSION':'extension'}.get(arm,'v3')
        rule=np.where(~ready,'history90_or_ma30_unavailable',np.where(allow,arm+'_allow',arm+'_reject'))
        for name,value in [('admit_'+label,(ready&allow).to_numpy()),('route_'+label,np.repeat(route,len(d))),('rule_id_'+label,rule)]:
            assert np.array_equal(actual[name].to_numpy(),value),name
            d[name]=value
        assert np.allclose(actual[label+'_q'],sq,equal_nan=True) and np.allclose(actual[label+'_x'],x,equal_nan=True)
    return d

def audit_coin(slug,items):
    root=ROUND;results=root/'results';old=FAMILY/'artifacts/adaptation_20260911'
    checkpoint=read_json(results/'checkpoints'/(slug+'.json'))
    sums=pd.DataFrame(checkpoint['summary']);blocks=pd.DataFrame(checkpoint['blocks'])
    for col in ['requested_start','requested_end','actual_start','actual_end']:
        if col in blocks:blocks[col]=pd.to_datetime(blocks[col],utc=True,format='mixed')
    counts=dict.fromkeys(['accounts','segments','trades','stop_records','equity_marks','opportunity_events','calendar_rows','schedule_rows'],0)
    cache={};bound={str(results/'checkpoints'/(slug+'.json')):sha(results/'checkpoints'/(slug+'.json'))}
    for key,info in items:
        lo=max(pd.Timestamp(info['trade_start']),pd.Timestamp('2023-01-01',tz='UTC'));hi=pd.Timestamp(info['end'])
        if lo>=hi:continue
        hp=LAB/info['hourly_path']
        if hp not in cache:
            assert sha(hp)==info['hourly_sha256'];h=read_frame(hp).rename(columns={'ts':'timestamp'})
            h.timestamp=pd.to_datetime(h.timestamp,utc=True).dt.as_unit('ns');cache[hp]=h.set_index('timestamp',drop=False)
        h=cache[hp].loc[(cache[hp].index>=pd.Timestamp(info['input_start']))&(cache[hp].index<hi)]
        dp=old/'cases/daily_features'/(key+'.parquet');d=read_frame(dp)
        d.timestamp=pd.to_datetime(d.timestamp,utc=True).dt.as_unit('ns');d=previous.add_causal_audit_features(d)
        decpath=results/'decisions'/(key+'.parquet');dec=read_frame(decpath);bound[str(decpath)]=sha(decpath)
        assert set(dec.case_id)==set(MODES)
        for arm,mode in MODES.items():
            saved=dec[dec.case_id.eq(arm)].reset_index(drop=True)
            daily=independent_schedule(d.copy(),saved,arm).set_index('timestamp',drop=False)
            directory=results/'runs'/key/arm/'full';summary=read_json(directory/'summary.json')
            for field,value in {'fee':.001,'slip':.0004,'ma30_mode':mode,'reverse':False,'admission_routing':True,'progress_days':4,'entry_wait_days':0,'delay_hours':0}.items():equal(summary[field],value,'frozen config '+field)
            assert pd.Timestamp(summary['start'])==lo and pd.Timestamp(summary['end_exclusive'])==hi
            v=audit_routed_account(directory,daily,h);t=read_frame(directory/'trades.csv');previous.extra_stats(summary,t)
            prior.compare_summary_row(sums,{'run_key':key,'case_id':arm},summary)
            selected=blocks[blocks.run_key.eq(key)&blocks.case_id.eq(arm)]
            n=previous.audit_calendar_blocks(directory,lo,hi,DEFINITIONS,selected)
            for f in directory.iterdir():
                if f.is_file():bound[str(f)]=sha(f)
            counts['accounts']+=1;counts['trades']+=v['trades'];counts['stop_records']+=v['stop_records']
            counts['equity_marks']+=v['equity_marks_independently_rebuilt'];counts['opportunity_events']+=v['opportunity_events']
            counts['calendar_rows']+=n;counts['schedule_rows']+=len(saved)
        counts['segments']+=1
    result={'slug':slug,'status':'PASS',**counts,'files':bound,'audit_source_sha256':sha(Path(__file__))}
    write_json(root/'audit/checkpoints'/(slug+'.json'),result);return {k:v for k,v in result.items() if k!='files'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=3);ap.add_argument('--coins',nargs='*');a=ap.parse_args()
    out=ROUND/'audit';out.mkdir(exist_ok=True);source=read_json(FAMILY/'artifacts/adaptation_20260911/cases/sources.json');by={}
    for key,info in source.items():by.setdefault(info['slug'],[]).append((key,info))
    if a.coins:by={k:v for k,v in by.items() if k in a.coins}
    begin=time.monotonic();results=[];errors=[]
    (out/'source_script.py.txt').write_bytes(Path(__file__).read_bytes())
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs={}
        for slug,items in by.items():
            p=out/'checkpoints'/(slug+'.json')
            if p.exists():
                v=read_json(p);assert v['audit_source_sha256']==sha(Path(__file__))
                assert all(sha(Path(f))==s for f,s in v['files'].items());results.append({k:x for k,x in v.items() if k!='files'})
            else:jobs[pool.submit(audit_coin,slug,items)]=slug
        for n,f in enumerate(as_completed(jobs),1):
            try:results.append(f.result())
            except Exception as exc:errors.append({'slug':jobs[f],'error':repr(exc),'trace':traceback.format_exc()});write_json(out/'errors.json',errors);print('ERROR',jobs[f],repr(exc),flush=True)
            if n%20==0 or n==len(jobs):print(f'Audit {n}/{len(jobs)}, errors {len(errors)}, {time.monotonic()-begin:.1f}s',flush=True)
    totals={k:sum(r[k] for r in results) for k in ['accounts','segments','trades','stop_records','equity_marks','opportunity_events','calendar_rows','schedule_rows']}
    write_json(out/('smoke.json' if a.coins else 'accounts.json'),{'status':'PASS' if not errors else 'FAIL','totals':totals,'errors':errors,'coins':results,'elapsed_seconds':time.monotonic()-begin,'official_price_conflict_resolved':False})
    assert not errors

if __name__=='__main__':main()
