"""Independent stop arithmetic; the prior auditor rebuilds execution and cash.

This file does not import the new simulator. Its copied progress counter is
extended with the two user-declared closed-day tests, independently of v7.
"""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
MARKET=ROOT/'research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts'
if str(MARKET) not in sys.path:sys.path.insert(0,str(MARKET))
import pandas as pd
import audit_v3_opportunity_20260913 as prior
DAY=prior.DAY
equal=prior.equal
protection_initial=prior.protection_initial
observe_protection=prior.observe_protection

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
        threshold = summary.get("adverse_ma_floor_atr")
        distance = -side * (float(day.close) - float(day.ma)) / float(day.atr)
        adverse = bool(full_day and threshold is not None and side * (float(day.close)-float(day.ma)) < -threshold*float(day.atr))
        stagnant = bool(full_day and summary.get("stagnation_floor", False) and initialized and count >= 4)
        jump = old_mult > .5 and (adverse or stagnant)
        if jump:
            tightened = True
            trigger = "floor_both" if adverse and stagnant else "floor_adverse_ma" if adverse else "floor_stagnation"
            if not armed:
                armed, ever, arm_day = True, True, row.signal_day
                arms += 1
                if first_arm_day is None: first_arm_day = row.signal_day
        if tightened:
            mult = .5 if jump else max(.5, round(mult-.2, 10))
            reductions += 1
        for key,value in {"adverse_ma_distance_atr":distance,"adverse_ma_floor_hit":adverse,
                          "stagnation_floor_hit":stagnant,"jump_to_floor":jump}.items():
            equal(getattr(row,key),value,"immediate floor "+key)
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

def audit_run(directory,daily,hourly):
    original=prior.audit_stop_path
    try:
        prior.audit_stop_path=audit_stop_path
        return prior.audit_run(directory,daily,hourly)
    finally:
        prior.audit_stop_path=original
