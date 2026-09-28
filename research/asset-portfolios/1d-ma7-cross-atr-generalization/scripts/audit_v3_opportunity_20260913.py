"""Independent V3 opportunity audit: no simulator imported or executed.

The monetary and V3 ratchet arithmetic is retained from the previous independent
four-tests auditor. New candidate and TP protection expectations are calculated
here from closed data, never obtained from the new strategy implementation.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
from types import SimpleNamespace
import time
import traceback
import numpy as np
import pandas as pd
import audit_exit_state_machine_20260910 as previous
from v3_opportunity_inputs_20260913 import ROOT, BASE, R, load_sources, load_segment, sha, read_json, write_json
money=previous.money
DAY=pd.Timedelta(days=1)
HOUR=pd.Timedelta(hours=1)
equal=previous.equal
audit_quantity=money.audit_quantity
audit_account_return=money.audit_account_return
OUT=R/'audit'

def read_frame(path):
    f=previous.read_frame(path)
    for c in ['tp_protect_signal_day','requested_start','requested_end','actual_start','actual_end']:
        if c in f: f[c]=pd.to_datetime(f[c],utc=True,format='mixed').dt.as_unit('ns')
    return f


def protection_initial():
    return dict(tp_protect_active=False,tp_protect_signal_day=None,tp_protect_event_atr=None,
                tp_protect_extreme_low=None,tp_protect_candidate=None,tp_protect_trigger_rsi=None,
                tp_protect_trigger_close=None,tp_protect_eligible_signal_count=0,tp_protect_suppressed_count=0)


def observe_protection(state,trade,row,day,stop,summary):
    triggered=eligible=False
    if trade.side==-1 and row.signal_day>=trade.entry_time:
        fill=float(day.close)*(1+summary['slip'])
        net=trade.qty*(trade.entry_price-fill)-trade.entry_fee-trade.qty*fill*summary['fee']
        eligible=bool(day.rsi<=30 and bool(day.accel1) and net>0)
        if eligible:
            state['tp_protect_eligible_signal_count']+=1
            if not state['tp_protect_active']:
                triggered=True
                state.update(tp_protect_active=True,tp_protect_signal_day=row.signal_day,
                    tp_protect_event_atr=float(day.atr),tp_protect_extreme_low=float(day.low),
                    tp_protect_trigger_rsi=float(day.rsi),tp_protect_trigger_close=float(day.close))
        if state['tp_protect_active']:
            state['tp_protect_extreme_low']=min(state['tp_protect_extreme_low'],float(day.low))
            state['tp_protect_candidate']=state['tp_protect_extreme_low']+state['tp_protect_event_atr']
            stop=min(stop,state['tp_protect_candidate'])
    suppressed=eligible and not (trade.exit_time==row.timestamp and trade.exit_reason=='stop_gap')
    state['tp_protect_suppressed_count']+=int(suppressed)
    return stop,{**state,'tp_protect_triggered_this_day':triggered,
                  'tp_protect_eligible_signal':eligible,'tp_protect_actually_suppressed':suppressed}

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
    protect = summary['short_exit']=='accel1_rsi30_protect'
    pstate=protection_initial()
    if protect:
        for k,v in pstate.items(): equal(first[k],v,'initial protection '+k)
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
        pexpected={}
        if protect: stop,pexpected=observe_protection(pstate,trade,row,day,stop,summary)
        expected = {"new_stop": stop, "new_mult": mult, "new_armed": armed,
                    "initialized": initialized, "extreme_price": extreme,
                    "extreme_day": extreme_day, "arm_day": arm_day,
                    "new_extreme": new_extreme, "no_new_extreme_days": count,
                    "tightened": tightened, "full_holding_day": bool(full_day),
                    "armed_reset": bool(reset), "ever_armed": ever,
                    "first_arm_day": first_arm_day, "arm_count": arms, "reset_count": resets,
                    "progress_policy": policy, "tightening_trigger": trigger,
                    "anchor_candidate": None, "anchor_decisive": False}
        expected.update(pexpected)
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
    if protect: expected.update(pstate)
    for key, value in expected.items():
        equal(getattr(trade, key), value, "final stop " + key)

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
                assert summary["short_exit"] == "accel1_rsi30" and trade.exit_reason == "accel1_rsi30" and side == -1
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
            if summary["short_exit"] == "accel1_rsi30" and side == -1 and day.rsi <= 30 and day.accel1 and profit > 0:
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
    if summary['short_exit']=='accel1_rsi30_protect':
        for field,col in [('short_protection_activated_trades','tp_protect_active'),('short_protection_eligible_signals','tp_protect_eligible_signal_count'),('short_protection_suppressed_tp_calls','tp_protect_suppressed_count')]:
            equal(summary[field],int(trades[col].sum()) if len(trades) else 0,'TP aggregate '+field)
    previous.extra_stats(summary,trades)
    return {**result, "trades": len(trades), "stop_records": len(stops),
            "equity_marks_independently_rebuilt": verified_marks, "status": "PASS"}


def audit_entry_lifecycle(trades,daily,hourly,summary,events):
    assert summary['entry_wait_days']==summary['delay_hours']==0 and not summary['reverse']
    assert summary['entry_mode']=='original' and summary['trend_filter']=='none'
    assert summary['direction_mode']=='both' and summary['risk_fraction'] is None
    assert summary['notional_fraction']==1 and not summary['admission_routing']
    stateful=summary['entry_wait_policy']=='until_invalid'
    start,end=pd.Timestamp(summary['start']),pd.Timestamp(summary['end_exclusive'])
    rows=list(trades.itertuples(index=False)); entered={x.entry_time:x for x in rows}
    assert len(entered)==len(rows)
    counts=dict.fromkeys(['flat_ready_crosses','flat_not_ready_crosses','entry_attempts','entry_fills',
        'slope_rejected','direction_rejected','ma30_not_ready_rejected','ma30_direction_rejected',
        'invalid_stop_rejected','nonpositive_equity_rejected','invalid_unit_risk_rejected','wait_candidates_created'],0)
    if stateful: counts.update(wait_candidates_confirmed=0,wait_candidates_cancelled=0,
                              wait_candidate_observations=0,wait_candidates_unresolved=0)
    expected=[]; candidate=None; cash=10000.; filled_times=[]
    def emit(t,signal,side,entry_reason,cross_day,stage,reason,status,details=None):
        expected.append(dict(timestamp=t,signal_day=signal.timestamp,side=side,cross=int(signal.cross),
            entry_reason=entry_reason,cross_day=cross_day,stage=stage,reason=reason,status=status,
            entry_filter='none',direction_mode='both',entry_slope=signal.slope,entry_close=signal.close,
            entry_ma=signal.ma,entry_ma30=signal.ma30,entry_prev_ma30=signal.prev_ma30,
            trade_id=entered[t].trade_id if status=='filled' else None,
            attempt_before_equity=cash,risk_fraction=None,notional_fraction=1.,**(details or {})))
    def candidate_row(t,signal,c,reason,status):
        assert stateful
        side,cd,cc=c
        emit(t,signal,side,'delayed_cross',cd,'candidate',reason,status,
            dict(candidate_wait_policy='until_invalid',candidate_cross_close=cc,
                 candidate_age_days=(signal.timestamp-cd).days,
                 candidate_correct_side=side*(signal.close-signal.ma)>0,
                 candidate_slope_met=side*signal.slope>.05,
                 candidate_breaks_cross_close=side*(signal.close-cc)>0))
        counts['wait_candidate_observations']+=1
        suffix={'confirmed':'confirmed','cancelled':'cancelled','unresolved':'unresolved'}.get(status)
        if suffix: counts['wait_candidates_'+suffix]+=1
    def attempt(t,signal,side,cd):
        counts['entry_attempts']+=1
        stop=signal.ma-side*1.5*signal.atr;ref=hourly.loc[t,'open']
        reason='invalid_stop_rejected' if not np.isfinite(stop) or side*(ref-stop)<=0 else 'nonpositive_equity_rejected' if cash<=0 else 'filled'
        detail={}; entry_reason='daily_cross' if cd==signal.timestamp else 'delayed_cross'
        if reason=='filled':
            assert t in entered,('Missing eligible entry',t)
            tr=entered[t]; filled_times.append(t); counts['entry_fills']+=1
            for k,v in dict(side=side,signal_day=signal.timestamp,cross_day=cd,entry_reason=entry_reason,
                            entry_wait_days_used=(signal.timestamp-cd).days,qualification='original',
                            entry_slope=signal.slope,entry_ma30=signal.ma30,entry_prev_ma30=signal.prev_ma30).items():
                equal(getattr(tr,k),v,'entry intent '+k)
            audit_quantity(tr,summary,cash)
            detail={k:getattr(tr,k) for k in ['entry_price','initial_stop','initial_stop_fill','initial_stop_unit_risk',
                'qty_cap','qty','initial_planned_risk','initial_planned_risk_pct','initial_stop_price_nonpositive']}
        else:
            assert t not in entered;counts[reason]+=1
            if reason=='invalid_stop_rejected':detail={'initial_stop':stop}
        emit(t,signal,side,entry_reason,cd,'fill',reason,'filled' if reason=='filled' else 'rejected',detail)
    for t in pd.date_range(start,end-DAY,freq='D'):
        signal=daily.loc[t-DAY]
        if any(x.entry_time<t<=x.exit_time for x in rows):
            assert t not in entered and candidate is None
            continue
        closed=[x for x in rows if x.exit_time<t]
        cash=float(closed[-1].end_equity) if closed else 10000.
        side=int(signal.cross)
        if not signal.ready:
            if candidate is not None:candidate_row(t,signal,candidate,'not_ready','cancelled')
            candidate=None
            if side:
                counts['flat_not_ready_crosses']+=1
                emit(t,signal,side,'daily_cross',signal.timestamp,'ready','not_ready','rejected')
        elif side:
            counts['flat_ready_crosses']+=1
            if candidate is not None:candidate_row(t,signal,candidate,'fresh_cross_supersedes','cancelled')
            candidate=None
            if side*signal.slope>.05:attempt(t,signal,side,signal.timestamp)
            else:
                counts['slope_rejected']+=1
                wait=stateful and np.isfinite(signal.slope) and side*(signal.close-signal.ma)>0
                emit(t,signal,side,'daily_cross',signal.timestamp,'slope','slope_rejected','waiting' if wait else 'rejected')
                if wait:
                    counts['wait_candidates_created']+=1;candidate=(side,signal.timestamp,float(signal.close))
                    candidate_row(t,signal,candidate,'created','pending')
        elif candidate is not None:
            cs,cd,cc=candidate
            if cs*(signal.close-signal.ma)<=0:
                candidate_row(t,signal,candidate,'ma_side_invalid','cancelled');candidate=None
            elif cs*signal.slope>.05 and cs*(signal.close-cc)>0 and signal.timestamp>cd:
                candidate_row(t,signal,candidate,'confirmed','confirmed');candidate=None
                attempt(t,signal,cs,cd)
            else:candidate_row(t,signal,candidate,'conditions_pending','pending')
        else:assert t not in entered,'Unexpected non-cross entry'
    if candidate is not None:
        # Last executed hour sees the preceding complete daily signal.
        candidate_row(end,daily.loc[end-2*DAY],candidate,'sample_end_unresolved','unresolved')
    assert filled_times==trades.entry_time.tolist() if len(trades) else not filled_times
    assert len(events)==len(expected),('entry event rows',len(events),len(expected))
    for actual,exp in zip(events.to_dict('records'),expected):
        for k in events: equal(actual[k],exp.get(k),'entry/candidate event '+k)
    for k,v in counts.items():equal(summary[k],v,'entry count '+k)
    return dict(entries_verified=len(trades),opportunity_events=len(events),entry_counts=counts,
                candidate_daily_observations=counts.get('wait_candidate_observations',0))


def verify_manifest(directory):
    manifest=read_json(directory/'artifact_checksums.json')
    for rel,digest in manifest.items():assert sha(directory/rel)==digest,(directory,rel)
    return len(manifest)


def independent_path_record(h,start,side,atr,days):
    end=start+days*DAY
    f=h.loc[(h.timestamp>=start)&(h.timestamp<end)]
    complete=len(f)==24*days and len(f)>0 and f.timestamp.iloc[0]==start and f.timestamp.iloc[-1]+HOUR==end and np.isfinite(atr) and atr>0
    r={'complete':bool(complete)}
    if not complete:return r
    ref=float(f.open.iloc[0]);final=float(f.close.iloc[-1]);
    fav=float(f.high.max() if side==1 else f.low.min());adv=float(f.low.min() if side==1 else f.high.max())
    fill_in=ref*(1+side*.0004);fill_out=final*(1-side*.0004);qty=1/(fill_in*1.001)
    r.update(close_reference=final,directional_close_pct=side*(final/ref-1)*100,
             hypothetical_net_return=qty*(side*(fill_out-fill_in)-.001*(fill_in+fill_out)),
             close_atr=side*(final-ref)/atr,mfe_atr=max(0.,side*(fav-ref)/atr),
             mae_atr=max(0.,-side*(adv-ref)/atr),peak_to_final_close_atr=max(0.,side*(fav-final)/atr))
    favorable=(f.high.to_numpy() if side==1 else f.low.to_numpy())
    adverse=(f.low.to_numpy() if side==1 else f.high.to_numpy())
    for n in [1,2]:
        a=np.flatnonzero(side*(favorable-ref)>=n*atr);b=np.flatnonzero(side*(adverse-ref)<=-n*atr)
        ia=int(a[0]) if len(a) else None;ib=int(b[0]) if len(b) else None
        outcome=('neither' if ia is None and ib is None else 'adverse_first' if ia is None else
                 'favorable_first' if ib is None else 'favorable_first' if ia<ib else
                 'adverse_first' if ib<ia else 'same_hour_ambiguous')
        r.update({f'first_{n}atr':outcome,f'first_favorable_{n}atr_hour':ia,f'first_adverse_{n}atr_hour':ib})
    return r


def audit_diagnostics(key,d,h,meta,trades,stops):
    dest=R/'diagnostics/segments'/key
    frames={name:pd.read_parquet(dest/(name+'.parquet')) for name in ['crosses','natural_exits','stagnation4','short_tp']}
    events=read_frame(ROOT/meta['baseline_dir']/'entry_events.csv')
    tmap={int(t.trade_id):t for t in trades.itertuples(index=False)}
    start,end=pd.Timestamp(meta['trade_start']),pd.Timestamp(meta['end'])
    expected_days=d.loc[d.ready & d.cross.ne(0) & (d.timestamp+DAY>=start) & (d.timestamp+DAY<end),'timestamp'].tolist()
    crosses=frames['crosses']; assert (crosses.signal_day.tolist() if len(crosses) else [])==expected_days
    classified=0; samples=0; complete_checks=0
    for row in crosses.itertuples(index=False):
        at=pd.Timestamp(row.observation_start);side=int(row.side)
        signal=d.loc[d.timestamp.eq(row.signal_day)].iloc[0]
        equal(row.slope_qualified,side*signal.slope>.05,'diagnostic slope qualification')
        logged=events.loc[events.timestamp.eq(at)&events.side.eq(side)]
        if len(logged):
            assert len(logged)==1;expected=logged.reason.iloc[0]
            if expected=='filled':
                tid=int(logged.trade_id.iloc[0]);equal(row.actual_trade_id,tid,'diagnostic entry id')
                equal(row.actual_unit_return,tmap[tid].return_on_entry_equity,'diagnostic actual trade return')
        else:
            exits=[t for t in tmap.values() if t.exit_time==at and t.exit_reason in ['stop_gap','accel1_rsi30']]
            busy=[t for t in tmap.values() if t.entry_time<at and (t.exit_time>at or (t.exit_time==at and t.exit_reason=='stop_intrahour'))]
            expected='exit_priority_same_hour' if exits else 'position_occupied' if busy else None
            assert expected is not None
        equal(row.entry_disposition,expected,'cross disposition');classified+=1
    natural=frames['natural_exits'];expect_ids={i for i,t in tmap.items() if t.exit_reason!='sample_end'}
    assert (set(natural.actual_trade_id.astype(int)) if len(natural) else set())==expect_ids
    for row in natural.itertuples(index=False):
        trade=tmap[int(row.actual_trade_id)]
        equal(row.observation_start,trade.exit_interval_end,'post-exit observation starts outside ambiguous exit bar')
        assert row.features_known_at<=trade.exit_time
    stall=frames['stagnation4']
    ex=stops.loc[stops.full_holding_day.fillna(False)&stops.no_new_extreme_days.ge(4)].sort_values('timestamp').drop_duplicates('trade_id') if len(stops) else stops
    assert len(stall)==len(ex)
    for row in stall.itertuples(index=False):
        sr=ex.loc[ex.trade_id.eq(row.actual_trade_id)].iloc[0]
        equal(row.event_time,sr.timestamp,'first stagnation time');equal(row.event_extreme_price,sr.extreme_price,'frozen event extreme')
    tp=frames['short_tp'];tpids={i for i,t in tmap.items() if t.exit_reason=='accel1_rsi30'}
    assert (set(tp.actual_trade_id.astype(int)) if len(tp) else set())==tpids
    for kind,frame in frames.items():
        if not len(frame):continue
        assert frame.event_id.is_unique and frame.features_known_at.le(frame.event_time).all()
        for horizon in [5,10,20]:
            expected=frame.observation_start.ge(pd.Timestamp(meta['input_start'])) & (frame.observation_start+horizon*DAY<=end) & frame.observation_atr.gt(0) & np.isfinite(frame.observation_atr)
            assert np.array_equal(frame[f'f{horizon}_complete'],expected)
            incomplete=~expected
            for field in ['close_reference','hypothetical_net_return','mfe_atr','mae_atr']:
                assert frame.loc[incomplete,f'f{horizon}_'+field].isna().all()
            complete_checks+=len(frame)
        selected={0,len(frame)//2,len(frame)-1}
        if meta['slug']=='HYPE':selected=set(range(len(frame)))
        if 'entry_disposition' in frame:
            selected.update(frame.reset_index(drop=True).groupby('entry_disposition',sort=False).head(1).index)
        for idx in sorted(selected):
            row=frame.iloc[idx]
            for horizon in [5,10,20]:
                values=independent_path_record(h,pd.Timestamp(row.observation_start),int(row.side),float(row.observation_atr),horizon)
                for field,target in values.items():equal(row[f'f{horizon}_'+field],target,'forward '+kind+' '+field)
                samples+=1
            # Independent direct trailing-window features; no diagnostic helper.
            j=int(d.timestamp.searchsorted(row.features_signal_day))
            assert j<len(d) and d.timestamp.iloc[j]==row.features_signal_day
            c=d.close.iloc[max(0,j-20):j+1].to_numpy(float)
            efficiency=(c[-1]-c[0])/np.abs(np.diff(c)).sum() if len(c)==21 and np.abs(np.diff(c)).sum()>0 else np.nan
            equal(row.efficiency20_signed,efficiency,'causal efficiency20')
            count=float(d.cross.iloc[j-19:j+1].ne(0).sum()) if j>=19 else np.nan
            equal(row.cross_count20,count,'causal cross20')
    return dict(raw_cross_classifications=classified,forward_complete_checks=complete_checks,
                independent_horizon_samples=samples,diagnostic_events=sum(len(f) for f in frames.values()))


def audit_coin(slug,keys,arm,check_diag=False):
    reports=[]
    blocks=read_frame(R/'accounts'/arm/'blocks.csv') if arm else None
    definitions=read_json(ROOT/load_sources()[keys[0]]['source_result']/'run_manifest.json')['calendar_blocks']
    for key in sorted(keys):
        d,h,m,bt,bs=load_segment(key);row={'run_key':key,'slug':slug}
        if check_diag:row.update(audit_diagnostics(key,d,h,m,bt,bs))
        d=d.set_index('timestamp',drop=False);h=h.set_index('timestamp',drop=False)
        if arm:
            directory=R/'accounts'/arm/'runs'/key/arm/'full'
            row.update(audit_run(directory,d,h))
            row['calendar_rows']=previous.audit_calendar_blocks(directory,pd.Timestamp(m['trade_start']),pd.Timestamp(m['end']),definitions,blocks.loc[blocks.run_key.eq(key)])
        reports.append(row)
    return reports


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=['E_STATE','TP_PROTECT'])
    ap.add_argument('--diagnostics',action='store_true');ap.add_argument('--workers',type=int,default=4)
    ap.add_argument('--smoke',nargs='*');ap.add_argument('--output',type=Path);args=ap.parse_args()
    assert args.arm or args.diagnostics
    name=args.arm or 'diagnostics';out=args.output or OUT/name
    assert not out.exists(),'Fresh audit directory required'
    assert read_json(R/'inputs/completion.json')['complete']
    if args.arm: assert read_json(R/'accounts'/args.arm/'completion.json')['complete']
    if args.diagnostics:assert read_json(R/'diagnostics/completion.json')['complete']
    out.mkdir(parents=True);start=time.monotonic();srcs=load_sources();groups={}
    for key,s in srcs.items():
        if not args.smoke or s['slug'] in args.smoke:groups.setdefault(s['slug'],[]).append(key)
    consumed=[R/'inputs/artifact_checksums.json']
    if args.arm:consumed.append(R/'accounts'/args.arm/'artifact_checksums.json')
    if args.diagnostics:consumed.append(R/'diagnostics/artifact_checksums.json')
    pins={str(p.relative_to(ROOT)):sha(p) for p in consumed}
    for script in [Path(__file__),Path(previous.__file__),Path(money.__file__),Path(previous.prior.__file__),Path(__file__).with_name('v3_opportunity_inputs_20260913.py')]:
        pins[str(script.relative_to(ROOT))]=sha(script)
    write_json(out/'started.json',dict(utc=str(pd.Timestamp.now(tz='UTC')),pins=pins,arm=args.arm,
        diagnostics=args.diagnostics,smoke=args.smoke,simulator_not_imported=True))
    (out/'source_script.py.txt').write_text(Path(__file__).read_text())
    for p in consumed:verify_manifest(p.parent)
    results=[];fail=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs={pool.submit(audit_coin,slug,keys,args.arm,args.diagnostics):slug for slug,keys in groups.items()}
        for n,future in enumerate(as_completed(jobs),1):
            slug=jobs[future]
            try:
                record=future.result();results.extend(record);write_json(out/'checkpoints'/(slug+'.json'),record)
            except Exception as exc:
                fail.append(dict(slug=slug,error=repr(exc),traceback=traceback.format_exc()));print('FAILED',slug,repr(exc),flush=True)
            if n%25==0 or n==len(jobs):print(f'Audit {name} coins {n}/{len(jobs)} failures {len(fail)} elapsed {time.monotonic()-start:.1f}s',flush=True)
    write_json(out/'failures.json',fail)
    totals={field:sum(r.get(field,0) for r in results) for field in ['trades','stop_records','equity_marks_independently_rebuilt','opportunity_events','candidate_daily_observations','calendar_rows','raw_cross_classifications','forward_complete_checks','independent_horizon_samples','diagnostic_events']}
    write_json(out/'final.json',dict(status='PASS' if not fail else 'FAIL',segments=len(results),coins=len(groups),failures=len(fail),**totals,elapsed_seconds=time.monotonic()-start))
    write_json(out/'artifact_checksums.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='artifact_checksums.json'})
    assert not fail



def audit_fixed_pair_trade(trade,base,records,daily,hourly,cfg,global_end):
    for name in ['entry_time','entry_reference','entry_price','entry_equity','entry_fee','qty','side','initial_stop','signal_day','cross_day','entry_atr']:
        equal(getattr(trade,name),getattr(base,name),'fixed original '+name)
    assert trade.trade_id==1 and trade.baseline_trade_id==base.trade_id
    side,fee,slip=int(trade.side),.001,.0004
    assert side==-1 and trade.entry_time<=base.exit_time<=trade.exit_time<=global_end
    audit_quantity(trade,cfg,base.entry_equity)
    equal(trade.entry_price,trade.entry_reference*(1+side*slip),'fixed entry fill')
    equal(trade.exit_price,trade.exit_reference*(1-side*slip),'fixed exit fill')
    equal(trade.entry_fee,trade.qty*trade.entry_price*fee,'fixed entry fee')
    equal(trade.exit_fee,trade.qty*trade.exit_price*fee,'fixed exit fee')
    assert trade.carry_paid==trade.funding_paid==0
    gross=side*trade.qty*(trade.exit_price-trade.entry_price)
    net=gross-trade.entry_fee-trade.exit_fee
    equal(trade.gross_pnl,gross,'fixed gross');equal(trade.net_pnl,net,'fixed net')
    equal(trade.end_equity,trade.entry_equity+net,'fixed cash')
    audit_account_return(trade.return_on_entry_equity,trade.entry_equity,trade.end_equity,net,trade.entry_fee,trade.exit_fee,gross,[])
    config={**cfg,'start':str(trade.entry_time),'end_exclusive':str(global_end)}
    audit_stop_path(trade,records,daily,config)
    held=hourly.loc[(hourly.index>=trade.entry_time)&(hourly.index<trade.exit_time)]
    which=np.searchsorted(records.timestamp.astype('int64'),held.index.asi8,side='right')-1
    assert (which>=0).all()
    lines=records.new_stop.to_numpy()[which]
    assert (held.high.to_numpy()<lines).all(),'Fixed earlier short stop ignored'
    if trade.exit_reason=='sample_end':
        equal(trade.exit_time,global_end,'fixed end');equal(trade.exit_reference,hourly.loc[global_end-HOUR,'close'],'fixed final close')
    else:
        bar=hourly.loc[trade.exit_time]
        if trade.exit_reason=='stop_gap':
            assert bar.open>=trade.stop;equal(trade.exit_reference,bar.open,'fixed gap')
        else:
            assert trade.exit_reason=='stop_intrahour' and bar.open<trade.stop<=bar.high
            equal(trade.exit_reference,trade.stop,'fixed stop fill')
    equal(trade.exit_interval_end,trade.exit_time+(HOUR if trade.exit_reason=='stop_intrahour' else pd.Timedelta(0)),'fixed interval end')
    for record in records.iloc[1:].itertuples(index=False):
        day=daily.loc[record.signal_day];fill=float(day.close)*(1-side*slip)
        profit=side*trade.qty*(fill-trade.entry_price)-trade.entry_fee-trade.qty*fill*fee
        equal(record.expected_profit_at_close,profit,'fixed profit snapshot')
        equal(record.favorable_move_atr,side*(day.close-trade.entry_price)/trade.entry_atr,'fixed favorable')
        equal(record.profit_eligible,profit>0 and side*(day.close-trade.entry_price)>=0,'fixed profit eligible')
    assert trade.tp_protect_active
    equal(trade.tp_protect_signal_day,base.tp_signal_day,'first intervention day')


def audit_recovery_samples(key,d,h,m,bt,bs):
    """Independent upper/lower drawdown bracket before event extreme recovery."""
    frame=pd.read_parquet(R/'diagnostics/segments'/key/'stagnation4.parquet')
    if not len(frame):return 0
    ids={0,len(frame)//2,len(frame)-1}
    if m['slug']=='HYPE':ids=set(range(len(frame)))
    count=0
    for i in sorted(ids):
        row=frame.iloc[i];side=int(row.side);ext=float(row.event_extreme_price);atr=float(row.observation_atr)
        start=pd.Timestamp(row.observation_start)
        for days in [5,10,20]:
            prefix=f'f{days}_'
            if not row[prefix+'complete']:continue
            f=h.loc[(h.timestamp>=start)&(h.timestamp<start+days*DAY)].reset_index(drop=True)
            fav=f.high.to_numpy() if side==1 else f.low.to_numpy()
            adv=f.low.to_numpy() if side==1 else f.high.to_numpy()
            hits=np.flatnonzero(side*(fav-ext)>0);first=int(hits[0]) if len(hits) else None
            equal(row[prefix+'old_extreme_recovered'],first is not None,'extreme recovery')
            equal(row[prefix+'recovery_first_hour'],first,'recovery hour')
            equal(row[prefix+'recovery_first_day'],first//24+1 if first is not None else None,'recovery day')
            worst=float(min(adv) if side==1 else max(adv))
            equal(row[prefix+'event_extreme_to_worst_atr'],max(0.,side*(ext-worst)/atr),'event worst')
            equal(row[prefix+'event_extreme_to_final_atr'],side*(ext-f.close.iloc[-1])/atr,'event final')
            if first is None:lower=upper=max(0.,side*(ext-worst)/atr)
            else:
                known=np.r_[adv[:first],f.open.iloc[0],f.open.iloc[first]]
                best_known=float(min(known) if side==1 else max(known))
                possible=best_known
                if side*(f.open.iloc[first]-ext)<=0:
                    possible=min(best_known,adv[first]) if side==1 else max(best_known,adv[first])
                lower=max(0.,side*(ext-best_known)/atr);upper=max(0.,side*(ext-possible)/atr)
            equal(row[prefix+'pre_recovery_retrace_lower_atr'],lower,'recovery drawdown lower')
            equal(row[prefix+'pre_recovery_retrace_upper_atr'],upper,'recovery drawdown upper');count+=1
    return count


def audit_pair_coin(slug,keys):
    part=pd.read_parquet(R/'pairs/parts'/(slug+'.parquet'))
    cfg=read_json(R/'accounts/TP_PROTECT/started.json')['config']
    result=dict(slug=slug,pair_rows=0,reused=0,replayed=0,recovery_samples=0)
    for key in keys:
        d,h,m,bt,bs=load_segment(key)
        result['recovery_samples']+=audit_recovery_samples(key,d,h,m,bt,bs)
        d=d.set_index('timestamp',drop=False);h=h.set_index('timestamp',drop=False)
        selected=part.loc[part.run_key.eq(key)] if len(part) else part
        assert len(selected)==len(bt)
        for base in bt.itertuples(index=False):
            pr=selected.loc[selected.baseline_trade_id.eq(base.trade_id)]
            assert len(pr)==1;pr=pr.iloc[0];result['pair_rows']+=1
            observations=[]
            if base.side==-1:
                records=bs.loc[bs.trade_id.eq(base.trade_id)]
                for row in records.itertuples(index=False):
                    if not row.full_holding_day:continue
                    day=d.loc[row.signal_day];fill=float(day.close)*1.0004
                    pnl=base.qty*(base.entry_price-fill)-base.entry_fee-base.qty*fill*.001
                    if day.accel1 and day.rsi<=30 and pnl>0:observations.append(row.timestamp)
            equal(pr.baseline_eligible_tp_boundary_count,len(observations),'pair eligible count')
            if base.exit_reason=='accel1_rsi30':
                assert observations==[base.exit_time] and pr.method=='fixed_original_entry_replay'
                tr=read_frame(ROOT/pr.new_trade_path);st=read_frame(ROOT/pr.new_stop_path);assert len(tr)==1
                changed=next(tr.itertuples(index=False))
                audit_fixed_pair_trade(changed,base,st,d,h,cfg,pd.Timestamp(m['end']))
                result['replayed']+=1
            else:
                assert pr.method=='exact_original_reused'
                if observations:assert all(t==base.exit_time for t in observations) and base.exit_reason=='stop_gap'
                changed=base;result['reused']+=1
                assert pr.new_trade_path==m['baseline_dir']+'/trades.csv' and pr.new_stop_path==m['baseline_dir']+'/stops.csv'
            values=dict(entry_equity=base.entry_equity,qty=base.qty,entry_price=base.entry_price,
                entry_reference=base.entry_reference,entry_fee=base.entry_fee,
                baseline_net_pnl=base.net_pnl,new_net_pnl=changed.net_pnl,
                baseline_exit_time=base.exit_time,new_exit_time=changed.exit_time,
                baseline_exit_interval_end=base.exit_interval_end,new_exit_interval_end=changed.exit_interval_end,
                baseline_exit_reason=base.exit_reason,new_exit_reason=changed.exit_reason,
                baseline_return_on_entry_equity=base.net_pnl/base.entry_equity,
                new_return_on_entry_equity=changed.net_pnl/base.entry_equity,
                delta_net_pnl=changed.net_pnl-base.net_pnl,
                delta_return_on_entry_equity=(changed.net_pnl-base.net_pnl)/base.entry_equity,
                common_natural=base.exit_reason!='sample_end' and changed.exit_reason!='sample_end')
            for field,target in values.items():equal(pr[field],target,'pair row '+field)
    return result


def pairs_main():
    ap=argparse.ArgumentParser();ap.add_argument('--pairs',action='store_true');ap.add_argument('--workers',type=int,default=4)
    ap.add_argument('--smoke',nargs='*');ap.add_argument('--output',type=Path);args=ap.parse_args()
    out=args.output or OUT/'pairs';assert not out.exists()
    assert read_json(R/'pairs/completion.json')['complete'];out.mkdir(parents=True);begin=time.monotonic()
    pins={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),R/'pairs/artifact_checksums.json',R/'inputs/artifact_checksums.json',R/'diagnostics/artifact_checksums.json']}
    write_json(out/'started.json',dict(utc=str(pd.Timestamp.now(tz='UTC')),pins=pins,smoke=args.smoke))
    (out/'source_script.py.txt').write_text(Path(__file__).read_text())
    verify_manifest(R/'pairs')
    write_json(out/'tamper_checks.json',tamper_checks())
    write_json(out/'exported_summary_checks.json',audit_exported_summaries())
    groups={}
    for key,s in load_sources().items():
        if not args.smoke or s['slug'] in args.smoke:groups.setdefault(s['slug'],[]).append(key)
    results=[];fail=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs={pool.submit(audit_pair_coin,slug,keys):slug for slug,keys in groups.items()}
        for n,future in enumerate(as_completed(jobs),1):
            slug=jobs[future]
            try:
                record=future.result();results.append(record);write_json(out/'checkpoints'/(slug+'.json'),record)
            except Exception as exc:
                fail.append(dict(slug=slug,error=repr(exc),traceback=traceback.format_exc()));print('FAILED',slug,repr(exc),flush=True)
            if n%25==0 or n==len(jobs):print(f'Pair audit {n}/{len(jobs)} failures {len(fail)} elapsed {time.monotonic()-begin:.1f}s',flush=True)
    write_json(out/'failures.json',fail)
    totals={k:sum(r[k] for r in results) for k in ['pair_rows','reused','replayed','recovery_samples']}
    write_json(out/'final.json',dict(status='PASS' if not fail else 'FAIL',coins=len(results),failures=len(fail),**totals,elapsed_seconds=time.monotonic()-begin))
    write_json(out/'artifact_checksums.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='artifact_checksums.json'})
    assert not fail

def tamper_checks():
    d,h,m,bt,bs=load_segment('HYPE__seg001');d=d.set_index('timestamp',drop=False);h=h.set_index('timestamp',drop=False)
    tpdir=R/'accounts/TP_PROTECT/runs/HYPE__seg001/TP_PROTECT/full'
    summary=read_json(tpdir/'summary.json');trades=read_frame(tpdir/'trades.csv');stops=read_frame(tpdir/'stops.csv')
    tr=next(trades.loc[trades.tp_protect_active].itertuples(index=False));sr=stops.loc[stops.trade_id.eq(tr.trade_id)].copy().reset_index(drop=True)
    audit_stop_path(tr,sr,d,summary)
    def must_fail(label,call):
        try:call()
        except AssertionError:return label
        raise AssertionError('Tampered evidence was accepted: '+label)
    accepted=[]
    changed=sr.copy();ix=changed.index[changed.tp_protect_active][0];changed.loc[ix,'tp_protect_event_atr']*=1.01
    accepted.append(must_fail('changed fixed event ATR',lambda:audit_stop_path(tr,changed,d,summary)))
    changed_stop=sr.copy();changed_stop.loc[ix,'new_stop']+=.1
    accepted.append(must_fail('widened short protection stop',lambda:audit_stop_path(tr,changed_stop,d,summary)))
    changed_qty=SimpleNamespace(**{**tr._asdict(),'qty':tr.qty*1.01})
    accepted.append(must_fail('changed fixed entry quantity',lambda:audit_quantity(changed_qty,summary,tr.entry_equity)))
    edir=R/'accounts/E_STATE/runs/HYPE__seg001/E_STATE/full';es=read_json(edir/'summary.json');et=read_frame(edir/'trades.csv');ev=read_frame(edir/'entry_events.csv')
    audit_entry_lifecycle(et,d,h,es,ev)
    changed_event=ev.copy();ci=changed_event.index[changed_event.stage.eq('candidate')][0]
    changed_event.loc[ci,'candidate_age_days']+=1
    accepted.append(must_fail('changed candidate observation age',lambda:audit_entry_lifecycle(et,d,h,es,changed_event)))
    return dict(status='PASS',expected_rejections=accepted)

def audit_exported_summaries():
    checks=0
    for arm in ['E_STATE','TP_PROTECT']:
        summary=read_frame(R/'accounts'/arm/'summary.csv')
        assert len(summary)==975 and summary.run_key.nunique()==975
        for row in summary.to_dict('records'):
            saved=read_json(R/'accounts'/arm/'runs'/row['run_key']/arm/'full/summary.json')
            for field,value in saved.items():equal(row[field],value,'exported account '+field);checks+=1
    cases=pd.read_parquet(R/'pairs/cases.parquet');summary=read_frame(R/'pairs/summary.csv')
    assert len(cases)==22028 and not cases.duplicated(['run_key','baseline_trade_id']).any()
    years=pd.to_datetime(cases.entry_time,utc=True).dt.year
    for row in summary.itertuples(index=False):
        period=str(row.period)
        mask=np.ones(len(cases),bool) if period=='ALL' else years.between(2023,2024) if period=='2023_2024' else years.ge(2025) if period=='2025_PLUS' else years.eq(int(period))
        if row.cohort=='common_natural':mask=mask&cases.common_natural
        if row.cohort=='original_short_tp':mask=mask&cases.method.eq('fixed_original_entry_replay')
        f=cases.loc[mask];old=f.baseline_return_on_entry_equity;new=f.new_return_on_entry_equity
        wins=old.gt(0);losers=old.lt(0);top=wins&old.ge(old.loc[wins].quantile(.95))
        expected=dict(trades=len(f),coins=f.slug.nunique(),replayed=int(f.method.eq('fixed_original_entry_replay').sum()),
            baseline_mean_return_pct=old.mean()*100,new_mean_return_pct=new.mean()*100,
            equal_coin_mean_improvement_pp=f.assign(delta=new-old).groupby('slug').delta.mean().mean()*100,
            improved_trades=int(new.gt(old).sum()),worsened_trades=int(new.lt(old).sum()),unchanged_trades=int(new.eq(old).sum()),
            losers_improved=int((losers&new.gt(old)).sum()),winners_turned_loss=int((wins&new.lt(0)).sum()),
            winners_turned_zero=int((wins&new.eq(0)).sum()),
            original_winner_signed_net_retention_pct=new[wins].sum()/old[wins].sum()*100 if old[wins].sum()!=0 else None,
            original_top5pct_signed_net_retention_pct=new[top].sum()/old[top].sum()*100 if old[top].sum()!=0 else None,
            new_sample_end_count=int(f.new_is_sample_end.sum()),
            median_added_holding_days_replayed=f.loc[f.method.eq('fixed_original_entry_replay'),'additional_holding_days'].median())
        for field,value in expected.items():equal(getattr(row,field),value,'exported pair summary '+field);checks+=1
    return dict(status='PASS',exported_summary_fields_checked=checks,pair_rows=len(cases))


if __name__=='__main__':
    import sys
    pairs_main() if '--pairs' in sys.argv else main()
