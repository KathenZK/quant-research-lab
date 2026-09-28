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
ROUND = FAMILY / "artifacts/adaptation_20260911"
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
            if trade.route_short_exit != "none" and side == -1 and day.rsi <= 30 and day.accel1 and profit > 0:
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


# Explicit immutable feature lists, independent of the learning implementation.
ASSET_FEATURES = ['asset_observed_days_capped90','asset_efficiency60','asset_cross_frequency60','asset_return_autocorr60','asset_wick_ratio60','asset_atr_pct_median60','asset_gap_atr_p95_60','asset_log10_quote_volume_median60','asset_cost_to_tr60','asset_v3_closed_count12','asset_v3_mean_return12','asset_v3_pf_bounded12','asset_v3_win_rate12']
ENTRY_FEATURES = ['entry_'+x for x in ['slope','previous_slope','slope_deceleration','rsi','ma7_distance_atr','ma30_distance_atr','ma30_slope_atr','body_atr','close_location','favorable_wick_atr','adverse_wick_atr','pre_displacement5_atr','pre_displacement10_atr','pre_displacement20_atr','pre_efficiency20','pre_tr_ratio5_20','pre_cross_count20','signal_stop_distance_pct','btc_return20','btc_return60','btc_ma30_distance']]
ARMS = ('A_ASSET','B_ENTRY','C_ROUTE','D_JOINT')
ACTIONS = ('v3','defense','extension')
CUTS = [pd.Timestamp('2023-01-01',tz='UTC'),pd.Timestamp('2025-01-01',tz='UTC')]


def code_group(code):
    normalized = str(code).strip().upper()
    return int.from_bytes(hashlib.sha256(normalized.encode()).digest(), 'big') % 3


def checksums(directory):
    directory = Path(directory)
    manifest = directory / 'artifact_checksums.json'
    entries = read_json(manifest)
    for relative, digest in entries.items():
        assert sha(directory / relative) == digest, 'Changed artifact ' + relative
    return {'path':str(directory.relative_to(LAB)), 'manifest_sha256':sha(manifest), 'files':len(entries)}


def model_matrix(frame, columns, medians):
    raw = frame[columns].to_numpy(dtype=float)
    missing = ~np.isfinite(raw)
    expected_medians = np.array([medians[k] for k in columns],dtype=float)
    raw = np.where(missing, expected_medians[None,:], raw)
    return np.concatenate((raw, missing.astype(float)),axis=1).astype(np.float32)


def walk_model(model, frame):
    if model['fallback']:
        return np.zeros(len(frame),dtype=np.int64)
    x = model_matrix(frame, model['columns'], model['medians'])
    t = model['tree']; result=[]
    for row in x:
        node=0
        while t['children_left'][node] >= 0:
            node=t['children_left'][node] if float(row[t['feature'][node]]) <= float(t['threshold'][node]) else t['children_right'][node]
        result.append(node)
    return np.array(result,dtype=np.int64)


def expected_leaf(group, arm):
    per_code = group.groupby('slug',sort=True)[['u_'+a for a in ACTIONS]].mean()
    count=len(per_code)
    means=per_code.mean().to_numpy(float)
    standard=per_code.std(ddof=1).to_numpy(float)/math.sqrt(count) if count>1 else np.zeros(3)
    differences=per_code.to_numpy(float)-per_code.u_v3.to_numpy(float)[:,None]
    difference_mean=np.mean(differences,axis=0)
    difference_se=np.std(differences,axis=0,ddof=1)/math.sqrt(count) if count>1 else np.zeros(3)
    supported=len(group)>=120 and count>=20
    allow,action,reason=True,'v3','baseline_no_supported_advantage'
    if not supported:
        reason='insufficient_leaf_support'
    elif arm in {'A_ASSET','B_ENTRY'}:
        if means[0]+standard[0]<0:
            allow,reason=False,'negative_v3_upper_estimate'
    elif arm=='D_JOINT' and np.max(means+standard)<0:
        allow,reason=False,'all_actions_negative_upper_estimate'
    else:
        eligible=[i for i in (1,2) if difference_mean[i]>difference_se[i] and means[i]>means[0]]
        if eligible:
            chosen=max(eligible,key=lambda i:means[i]);action=ACTIONS[chosen];reason='paired_exit_advantage'
    return {'allow':allow,'action':action,'reason':reason,'rows':len(group),'coins':count,'supported':supported,
            'means':dict(zip(ACTIONS,means)),'standard_errors':dict(zip(ACTIONS,standard)),
            'paired_improvement':dict(zip(ACTIONS,difference_mean)),
            'paired_standard_errors':dict(zip(ACTIONS,difference_se)),
            'coin_outcomes':[{'slug':slug,**dict(zip(ACTIONS,values))} for slug,values in zip(per_code.index,per_code.to_numpy())]}


def compare_nested(actual, expected, label):
    if isinstance(expected,dict):
        for key,value in expected.items():
            assert key in actual, label+' missing '+key
            compare_nested(actual[key],value,label+'.'+key)
    elif isinstance(expected,list):
        assert len(actual)==len(expected), label+' length'
        for i,(a,b) in enumerate(zip(actual,expected)):
            compare_nested(a,b,label+f'[{i}]')
    else:
        equal(actual,expected,label)


def prepare_cases(directory):
    frame=read_frame(Path(directory)/'cases.parquet')
    frame['case_id']=frame.run_key.astype(str)+'::'+frame.source_trade_id.astype(str)
    assert frame.case_id.is_unique
    frame['fold']=frame.slug.map(code_group)
    for column in ['signal_day','entry_time']+['exit_'+a for a in ACTIONS]+['exit_interval_end_'+a for a in ACTIONS]:
        frame[column]=pd.to_datetime(frame[column],utc=True).dt.as_unit('ns')
    frame['decision_time']=frame.signal_day+DAY
    assert frame.entry_time.equals(frame.decision_time), 'Non-next-open label entry'
    frame['label_end']=frame[['exit_'+a for a in ACTIONS]].max(axis=1)
    assert frame[['exit_'+a for a in ACTIONS]+['exit_interval_end_'+a for a in ACTIONS]].notna().all().all()
    frame['knowledge_end']=frame[['exit_interval_end_'+a for a in ACTIONS]].max(axis=1)
    assert frame.knowledge_end.ge(frame.label_end).all()
    assert (frame[['exit_'+a for a in ACTIONS]].ge(frame.entry_time,axis=0)).all().all()
    for column in ['ready90','terminal_any']:
        assert frame[column].map(lambda x:isinstance(x,(bool,np.bool_))).all()
    return frame


def audit_models(directory=ROUND):
    from sklearn.tree import DecisionTreeRegressor
    root=Path(directory); cases=prepare_cases(root/'cases'); learning=root/'learning'
    models=read_json(learning/'models.json')
    assert set(models)=={f'{cut.year}_f{group}_{arm}' for cut in CUTS for group in range(3) for arm in ARMS}
    checks={'models':0,'leaf_rules':0,'training_memberships':0,'inferred_validation_rows':0}
    for name,model in models.items():
        cut=pd.Timestamp(model['cutoff']); group=model['heldout_fold']; arm=model['arm']
        assert cut in CUTS and group in range(3) and arm in ARMS
        assert name==f'{cut.year}_f{group}_{arm}' and model['model_id']==name
        columns=ASSET_FEATURES if arm=='A_ASSET' else ENTRY_FEATURES if arm=='B_ENTRY' else ASSET_FEATURES+ENTRY_FEATURES
        assert model['columns']==columns
        mask=cases.ready90 & ~cases.terminal_any & cases.label_end.lt(cut) & cases.fold.ne(group)
        train=cases.loc[mask].copy().sort_values('case_id',kind='stable')
        assert model['training_ids']==train.case_id.tolist(), 'Training membership/order'
        assert model['training_slugs']==sorted(train.slug.unique())
        assert model['training_rows']==len(train) and model['training_coins']==train.slug.nunique()
        assert all(code_group(s)!=group for s in model['training_slugs'])
        assert train.label_end.lt(cut).all() and train.decision_time.lt(cut).all()
        assert train.knowledge_end.lt(cut).all(), 'Unmatured exit interval at training cutoff'
        conservative=cases.ready90 & ~cases.terminal_any & cases.knowledge_end.lt(cut) & cases.fold.ne(group)
        assert mask.equals(conservative), 'Old exit timestamp and conservative knowledge membership differ'
        assert not train.terminal_any.any()
        fallback=len(train)<120 or train.slug.nunique()<20
        assert model['fallback']==fallback
        checks['models']+=1; checks['training_memberships']+=len(train)
        if fallback:
            advice=model['leaves']['0']
            assert advice['allow'] and advice['action']=='v3' and advice['reason']=='insufficient_training_support'
            continue
        raw=train[columns].replace([np.inf,-np.inf],np.nan)
        medians={c:float(raw[c].median()) if raw[c].notna().any() else 0. for c in columns}
        compare_nested(model['medians'],medians,'training-only medians')
        assert model['feature_names']==columns+[x+'__missing' for x in columns]
        targets=['u_v3'] if arm in {'A_ASSET','B_ENTRY'} else ['u_'+a for a in ACTIONS]
        assert model['targets']==targets
        weights=1/train.groupby('slug').case_id.transform('count').to_numpy(float)
        weights*=len(train)/weights.sum()
        per_code=pd.Series(weights,index=train.index).groupby(train.slug).sum()
        assert np.allclose(per_code,per_code.iloc[0],rtol=1e-12)
        tree=DecisionTreeRegressor(max_depth=3,min_samples_leaf=120,random_state=0,criterion='squared_error')
        matrix=model_matrix(train,columns,medians)
        tree.fit(matrix,train[targets].to_numpy(float),sample_weight=weights)
        for key in ['children_left','children_right','feature','threshold']:
            expected=getattr(tree.tree_,key).tolist()
            compare_nested(model['tree'][key],expected,'independent tree '+key)
        for key in ['n_node_samples','value']:
            if key in model['tree']:
                compare_nested(model['tree'][key],getattr(tree.tree_,key).tolist(),'independent tree '+key)
        leaves=walk_model(model,train)
        assert np.array_equal(leaves,tree.apply(matrix))
        assert set(model['leaves'])==set(map(str,np.unique(leaves)))
        conditions={}
        def visit(node,path):
            if tree.tree_.children_left[node]<0:
                conditions[str(node)]=path;return
            column=model['feature_names'][tree.tree_.feature[node]]; threshold=float(tree.tree_.threshold[node])
            visit(tree.tree_.children_left[node],path+[{'feature':column,'operator':'<=','threshold':threshold}])
            visit(tree.tree_.children_right[node],path+[{'feature':column,'operator':'>','threshold':threshold}])
        visit(0,[])
        for leaf in np.unique(leaves):
            selected=train.loc[leaves==leaf]; saved=model['leaves'][str(leaf)]
            assert saved['training_ids']==selected.case_id.tolist()
            compare_nested(saved['conditions'],conditions[str(leaf)],'human rule path')
            compare_nested(saved,expected_leaf(selected,arm),'leaf advice '+name+f'/{leaf}')
            checks['leaf_rules']+=1
    validation=read_frame(learning/'case_decisions.parquet')
    expected_count=sum(int((cases.decision_time.ge(cut)&cases.decision_time.lt(CUTS[i+1] if i+1<len(CUTS) else pd.Timestamp('2026-09-05',tz='UTC'))).sum())*4 for i,cut in enumerate(CUTS))
    assert len(validation)==expected_count
    assert not validation.duplicated(['case_id','arm']).any()
    source=cases.set_index('case_id',drop=False)
    for (name,arm),group in validation.groupby(['model_id','arm'],sort=False):
        model=models[name]; original=source.loc[group.case_id].reset_index(drop=True); group=group.reset_index(drop=True)
        assert model['arm']==arm
        assert original.fold.eq(model['heldout_fold']).all()
        cut=pd.Timestamp(model['cutoff']); end=pd.Timestamp('2025-01-01' if cut.year==2023 else '2026-09-05',tz='UTC')
        assert original.decision_time.ge(cut).all() and original.decision_time.lt(end).all()
        nodes=walk_model(model,original)
        for i,node in enumerate(nodes):
            actual=group.iloc[i]; original_row=original.iloc[i]; saved=model['leaves'][str(node)]
            ready=bool(original_row.ready90)
            allowed=bool(saved['allow']) if ready else False
            rule=f'{name}_L{node}' if ready else 'INSUFFICIENT_HISTORY90'
            reason=saved['reason'] if ready else 'insufficient_history90'
            for field,target in {'leaf_id':int(node),'allow':allowed,'action':saved['action'],'rule_id':rule,'reason':reason,'fold':model['heldout_fold']}.items():
                equal(actual[field],target,'validation '+field)
            expected_u=float(original_row['u_'+saved['action']]) if allowed else 0.
            equal(actual.selected_u,expected_u,'selected label')
            equal(actual.delta_u,expected_u-original_row.u_v3,'label improvement')
            for action in ACTIONS:
                equal(actual['u_'+action],original_row['u_'+action],'validation outcome unchanged')
        checks['inferred_validation_rows']+=len(group)
    rule_table=read_json(learning/'rules.json')
    assert len(rule_table)==sum(len(m['leaves']) for m in models.values())
    assert len({r['rule_id'] for r in rule_table})==len(rule_table)
    for rule in rule_table:
        model=models[rule['model_id']];node=rule['rule_id'].rsplit('_L',1)[1]
        assert rule['arm']==model['arm'] and rule['fold']==model['heldout_fold'] and rule['cutoff']==model['cutoff']
        expected={k:v for k,v in model['leaves'][node].items() if k not in ['coin_outcomes','training_ids']}
        compare_nested(rule,expected,'exported rule')
    tab=read_frame(learning/'rule_validation.csv');verified_groups=0
    for keys,group in validation.groupby(['train_cutoff','arm','rule_id'],dropna=False):
        good=group.loc[~group.terminal_any & group.ready90]
        wins=good.loc[good.u_v3>0];losses=good.loc[good.u_v3<0]
        saved=tab.loc[tab.train_cutoff.eq(keys[0])&tab.arm.eq(keys[1])&tab.rule_id.eq(keys[2])]
        assert len(saved)==1
        values={'cases':len(group),'natural_ready_cases':len(good),'coins':good.slug.nunique(),'kept':int(good.allow.sum()),
          'rejected':int((~good.allow).sum()),'baseline_mean_return':float(good.u_v3.mean()) if len(good) else None,
          'selected_mean_return':float(good.selected_u.mean()) if len(good) else None,'mean_delta':float(good.delta_u.mean()) if len(good) else None,
          'original_winners':len(wins),'winners_rejected':int((~wins.allow).sum()),'winners_turned_loss':int((wins.selected_u<0).sum()),
          'original_losers':len(losses),'losers_improved':int((losses.delta_u>1e-12).sum()),
          'positive_winner_retention':float(wins.selected_u.clip(lower=0).sum()/wins.u_v3.sum()) if len(wins) else None}
        compare_nested(saved.iloc[0].to_dict(),values,'rule separated outcomes');verified_groups+=1
    assert verified_groups==len(tab)
    checks['rule_validation_groups']=verified_groups
    checks['status']='PASS'
    return checks

def independent_daily_features(d, baseline, btc):
    """Reconstruct declared information from prices and strictly matured shadow trades."""
    def ratio(x,y):
        with np.errstate(divide='ignore',invalid='ignore'):
            z=x/y
        return z.replace([np.inf,-np.inf],np.nan)
    c=d.close; a=d.atr; change=c.diff(); daily_return=c.pct_change(fill_method=None)
    tr=pd.concat((d.high-d.low,abs(d.high-c.shift()),abs(d.low-c.shift())),axis=1).max(axis=1)
    width=d.high-d.low
    upper=d.high-np.maximum(d.open,c); lower=np.minimum(d.open,c)-d.low
    output=pd.DataFrame(index=d.index)
    output['ready90']=np.arange(len(d))>=89
    output['asset_observed_days_capped90']=np.minimum(np.arange(len(d))+1,90)
    output['asset_efficiency60']=ratio(abs(c-c.shift(60)),abs(change).rolling(60).sum())
    output['asset_cross_frequency60']=d.cross.abs().rolling(60).sum()/60
    output['asset_return_autocorr60']=daily_return.rolling(60).corr(daily_return.shift())
    output['asset_wick_ratio60']=ratio(upper+lower,width).rolling(60).median()
    output['asset_atr_pct_median60']=ratio(a,c).rolling(60).median()
    output['asset_gap_atr_p95_60']=ratio(abs(d.open-c.shift()),a.shift()).rolling(60).quantile(.95)
    output['asset_log10_quote_volume_median60']=np.log10(d.quote_volume.where(d.quote_volume>0).rolling(60).median())
    output['asset_cost_to_tr60']=.0028/ratio(tr,c).rolling(60).median()
    history=np.full((len(d),4),np.nan);history[:,0]=0
    natural=baseline.loc[baseline.exit_reason.ne('sample_end')].copy() if len(baseline) else baseline
    if len(natural):
        natural=natural.sort_values('exit_time')
        for i,stamp in enumerate(d.timestamp):
            selected=natural.loc[natural.exit_time < stamp+DAY].tail(12)
            values=selected.return_on_entry_equity.to_numpy(float)
            history[i,0]=len(values)
            if len(values):
                gross_wins=values[values>0].sum(); gross_losses=-values[values<0].sum()
                history[i,1]=np.mean(values)
                history[i,2]=gross_wins/(gross_wins+gross_losses) if gross_wins+gross_losses>0 else np.nan
                history[i,3]=np.mean(values>0)
    for i,column in enumerate(ASSET_FEATURES[-4:]):output[column]=history[:,i]
    market=btc.reindex(pd.DatetimeIndex(d.timestamp))
    for side,prefix in [(1,'long_'),(-1,'short_')]:
        values={'slope':side*d.slope,'previous_slope':side*d.slope.shift(),
                'slope_deceleration':side*(d.slope.shift()-d.slope),'rsi':side*(d.rsi-50)/50,
                'ma7_distance_atr':side*ratio(c-d.ma,a),'ma30_distance_atr':side*ratio(c-d.ma30,a),
                'ma30_slope_atr':side*ratio(d.ma30-d.prev_ma30,a),'body_atr':side*ratio(c-d.open,a),
                'close_location':ratio(c-d.low if side==1 else d.high-c,width),
                'favorable_wick_atr':ratio(upper if side==1 else lower,a),
                'adverse_wick_atr':ratio(lower if side==1 else upper,a),
                'pre_efficiency20':ratio(abs(c-c.shift(20)),abs(change).rolling(20).sum()).shift(),
                'pre_tr_ratio5_20':ratio(tr.rolling(5).mean(),tr.rolling(20).mean()).shift(),
                'pre_cross_count20':d.cross.abs().rolling(20).sum().shift(),
                'signal_stop_distance_pct':ratio(side*(c-d.ma)+1.5*a,c),
                'btc_return20':side*market.btc_return20.to_numpy(),
                'btc_return60':side*market.btc_return60.to_numpy(),
                'btc_ma30_distance':side*market.btc_ma30_distance.to_numpy()}
        for days in (5,10,20):values[f'pre_displacement{days}_atr']=side*ratio(c-c.shift(days),a).shift()
        for key,value in values.items():output[prefix+key]=value
    return output.replace([np.inf,-np.inf],np.nan)


def independent_episode(base, daily, hourly, policy, end):
    """Independent exit-only mathematical reconstruction, with no simulator import."""
    side=int(base.side); fee=.001; slip=.0004
    entry=pd.Timestamp(base.entry_time); capital=float(base.entry_equity); quantity=float(base.qty)
    fill=float(base.entry_price); entry_fee=float(base.entry_fee)
    stop=float(base.initial_stop); mult=1.5; armed=False; extreme=None; stale=0
    state=previous.ClosedState(side,float(base.entry_reference),fill,policy)
    h=hourly.loc[(hourly.index>=entry)&(hourly.index<end)]
    assert len(h)
    short_tp=False
    final=None
    for bar in h.itertuples(index=False):
        stamp=bar.timestamp
        if stamp.hour==0 and stamp>entry:
            day=daily.loc[stamp-DAY]
            observed=float(day.high if side==1 else day.low)
            if extreme is None:
                extreme=observed; stale=0
            elif side*(observed-extreme)>0:
                extreme=observed; stale=0
            else:
                stale+=1
            if stale>=4:armed=True
            decrease=armed and mult>.5
            defensive_stop=protective_stop=None
            if policy!='v3':
                info=state.observe(day,extreme,stale)
                if info['sm_defense'] or info['sm_protect']:
                    decrease=mult>.5
                elif policy=='extension' and info['sm_healthy']:
                    decrease=False
                defensive_stop=info['sm_defensive_stop']; protective_stop=info['sm_protection_stop']
            if decrease:mult=max(.5,round(mult-.2,10))
            possible=[stop,float(day.ma)-side*mult*float(day.atr)]
            possible.extend(x for x in [defensive_stop,protective_stop] if x is not None)
            stop=(max if side==1 else min)(possible)
            close_fill=float(day.close)*(1-side*slip)
            close_net=side*quantity*(close_fill-fill)-entry_fee-quantity*close_fill*fee
            short_tp=policy!='extension' and side==-1 and day.rsi<=30 and bool(day.accel1) and close_net>0
        if side*(float(bar.open)-stop)<=0:
            final=(stamp,stamp,float(bar.open),'stop_gap');break
        if short_tp:
            final=(stamp,stamp,float(bar.open),'accel1_rsi30');break
        if (side==1 and bar.low<=stop) or (side==-1 and bar.high>=stop):
            final=(stamp,stamp+HOUR,stop,'stop_intrahour');break
    if final is None:final=(end,end,float(h.iloc[-1].close),'sample_end')
    stamp,interval,reference,reason=final
    exit_fill=reference*(1-side*slip)
    value=(side*quantity*(exit_fill-fill)-entry_fee-quantity*exit_fill*fee)/capital
    return {'exit':stamp,'exit_interval_end':interval,'reason':reason,'u':value,'terminal':reason=='sample_end'}


def audit_case_coin(jobs, root_string, btc):
    root=Path(root_string); aggregate={'segments':0,'daily_rows':0,'cases':0,'reused_labels':0,'independent_replayed_labels':0}
    first=jobs[0][1]; raw_hour=read_frame(LAB/first['hourly_path'])
    if 'ts' in raw_hour:
        raw_hour=raw_hour.rename(columns={'ts':'timestamp'})
        raw_hour.timestamp=pd.to_datetime(raw_hour.timestamp,utc=True).dt.as_unit('ns')
    raw_hour=raw_hour.set_index('timestamp',drop=False)
    assert sha(LAB/first['hourly_path'])==first['hourly_sha256']
    for run_key,source in jobs:
        d=read_frame(root/'cases/daily_features'/f'{run_key}.parquet')
        d.timestamp=pd.to_datetime(d.timestamp,utc=True).dt.as_unit('ns')
        old=LAB/source['source_result']
        baseline=read_frame(old/'runs'/run_key/'V3/full/trades.csv')
        original_daily=read_frame(old/'market'/run_key/'daily_features.csv')
        assert d.timestamp.equals(original_daily.timestamp)
        for column in original_daily.columns:
            if column in d and column!='timestamp':
                a,b=d[column],original_daily[column]
                if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
                    assert np.allclose(a,b,rtol=2e-10,atol=1e-14,equal_nan=True), 'Changed old feature '+column
                else:
                    assert a.fillna('').tolist()==b.fillna('').tolist(),column
        expected=independent_daily_features(d,baseline,btc)
        for column in expected:
            assert np.allclose(d[column],expected[column],rtol=2e-10,atol=1e-12,equal_nan=True), run_key+' feature '+column
        part=read_frame(root/'cases/case_parts'/f'{run_key}.parquet')
        audit=read_frame(root/'cases/label_audits'/f'{run_key}.parquet')
        assert len(part)==len(baseline)
        assert len(audit)==len(baseline)*2
        candidate_tables={action:read_frame(old/'runs'/run_key/cid/'full/trades.csv') for action,cid in [('defense','S1_DEFENSE'),('extension','S3_EXTENSION')]}
        daily=previous.add_causal_audit_features(d).set_index('timestamp',drop=False)
        end=pd.Timestamp(source['end']); start=pd.Timestamp(source['input_start'])
        h=raw_hour.loc[(raw_hour.index>=start)&(raw_hour.index<end)]
        for original,case in zip(baseline.itertuples(index=False),part.itertuples(index=False)):
            assert original.trade_id==case.source_trade_id
            assert original.entry_time==case.entry_time and original.signal_day==case.signal_day and original.side==case.side
            f=daily.loc[case.signal_day]; prefix='long_' if case.side==1 else 'short_'
            for column in ASSET_FEATURES:
                equal(getattr(case,column),f[column],'case '+column)
            for column in ENTRY_FEATURES:
                equal(getattr(case,column),f[prefix+column.removeprefix('entry_')],'case '+column)
            equal(case.ready90,f.ready90,'case ready90')
            expected_u=(int(original.side)*float(original.qty)*(float(original.exit_price)-float(original.entry_price))-float(original.entry_fee)-float(original.exit_fee))/float(original.entry_equity)
            assert abs(expected_u-case.u_v3)<=1e-12+abs(expected_u)*2e-12
            for field,actual in [('exit',original.exit_time),('exit_interval_end',original.exit_interval_end),('reason',original.exit_reason),('terminal',original.exit_reason=='sample_end')]:
                equal(getattr(case,field+'_v3'),actual,'original label '+field)
            for action in ('defense','extension'):
                record=audit.loc[audit.source_trade_id.eq(original.trade_id)&audit.action.eq(action)]
                assert len(record)==1; record=record.iloc[0]
                if getattr(case,'label_source_'+action)=='matching_natural_account':
                    assert record.reused
                    t=candidate_tables[action]
                    selected=t.loc[t.entry_time.eq(original.entry_time)&t.side.eq(original.side)]
                    assert len(selected)==1
                    candidate=selected.iloc[0]
                    assert candidate.trade_id==record.candidate_source_trade_id
                    for field in ('entry_reference','entry_price','initial_stop','initial_stop_fill','initial_stop_unit_risk','entry_atr'):
                        assert np.isclose(getattr(original,field),candidate[field],rtol=2e-12,atol=1e-14),field
                    for field in ('qty','entry_fee','initial_planned_risk'):
                        assert np.isclose(getattr(original,field)/original.entry_equity,candidate[field]/candidate.entry_equity,rtol=2e-12,atol=1e-14),field
                    expect={'exit':candidate.exit_time,'exit_interval_end':candidate.exit_interval_end,'reason':candidate.exit_reason,'u':candidate.return_on_entry_equity,'terminal':candidate.exit_reason=='sample_end'}
                    aggregate['reused_labels']+=1
                else:
                    assert getattr(case,'label_source_'+action)=='fixed_episode_replay' and not record.reused
                    expect=independent_episode(original,daily,h,action,end)
                    aggregate['independent_replayed_labels']+=1
                for field,value in expect.items():
                    actual=getattr(case,field+'_'+action)
                    if field=='u':
                        assert np.isclose(actual,value,rtol=2e-12,atol=1e-12),f'{run_key} {original.trade_id} {action} {field}: {actual} != {value}'
                    else:equal(actual,value,f'{run_key} {original.trade_id} {action} {field}')
            equal(case.terminal_any,any(getattr(case,'terminal_'+a) for a in ACTIONS),'terminal triad')
            equal(case.label_known_at,max(getattr(case,'exit_'+a) for a in ACTIONS),'label maturity')
        aggregate['segments']+=1; aggregate['cases']+=len(part); aggregate['daily_rows']+=len(d)
    aggregate['status']='PASS'; aggregate['slug']=first['slug']
    return aggregate


def audit_cases(root=ROUND,workers=2):
    root=Path(root); source=root/'cases'; complete=read_json(source/'completion.json')
    assert complete['complete'] and complete['segments']==975 and complete['cases']==22028
    manifest=checksums(source)
    jobs=read_json(source/'sources.json'); assert len(jobs)==975
    # Prior full accounting audits are reused by their frozen manifests. No old
    # net-value curves are scanned again; changed feature and label outputs are.
    provenance=read_json(source/'started.json')
    for relative,digest in provenance['consumed_manifests'].items():assert sha(LAB/relative)==digest
    for relative,digest in read_json(source/'input_pins.json').items():assert sha(LAB/relative)==digest
    assert provenance['fee_per_side']==.001 and provenance['slippage_per_side']==.0004
    btc=read_frame(source/'btc_closed_features.parquet').set_index('timestamp')
    bsource=jobs['BTC__seg001']; bd=read_frame(LAB/bsource['source_result']/'market/BTC__seg001/daily_features.csv').set_index('timestamp')
    assert btc.index.equals(bd.index)
    for name,value in [('btc_return20',bd.close.pct_change(20,fill_method=None)),('btc_return60',bd.close.pct_change(60,fill_method=None)),('btc_ma30_distance',bd.close/bd.ma30-1)]:
        assert np.allclose(btc[name],value,equal_nan=True,rtol=2e-10,atol=1e-14)
    groups={}
    for key,meta in jobs.items():groups.setdefault(meta['slug'],[]).append((key,meta))
    totals={k:0 for k in ['segments','daily_rows','cases','reused_labels','independent_replayed_labels']}
    errors=[];start=time.monotonic(); records=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending={pool.submit(audit_case_coin,job,str(root),btc):slug for slug,job in groups.items()}
        for i,future in enumerate(as_completed(pending),1):
            slug=pending[future]
            try:
                result=future.result();records.append(result)
                for key in totals:totals[key]+=result[key]
            except Exception as error:
                errors.append({'slug':slug,'error':repr(error),'traceback':traceback.format_exc()}); print('CASE AUDIT ERROR',slug,repr(error),flush=True)
            if i%25==0 or i==len(pending):print(f'Case audit {i}/{len(pending)}, failures {len(errors)}, seconds {time.monotonic()-start:.1f}',flush=True)
    report={'status':'PASS' if not errors else 'FAIL','totals':totals,'errors':errors,'coins':records,'manifest':manifest,'elapsed_seconds':time.monotonic()-start}
    write_json(root/'audit/cases.json',report)
    assert not errors
    assert totals['segments']==975 and totals['cases']==22028
    assert totals['reused_labels']==complete['reused_labels'] and totals['independent_replayed_labels']==complete['calculated_labels']
    return report


def verify_schedule(d, saved, slug, arm, models):
    assert len(saved)==len(d)
    assert saved.timestamp.equals(d.timestamp)
    assert saved.ready90.tolist()==d.ready90.tolist()
    assert saved.cross.tolist()==d.cross.tolist() and saved.ready.tolist()==d.ready.tolist()
    assert np.allclose(saved.slope,d.slope,equal_nan=True,rtol=2e-10,atol=1e-14)
    group=code_group(slug); decision=d.timestamp+DAY; size=len(d)
    result=d.copy()
    for prefix in ('long','short'):
        features=d[ASSET_FEATURES].copy()
        for column in ENTRY_FEATURES:features[column]=d[prefix+'_'+column.removeprefix('entry_')]
        expected={'allow':np.full(size,False,dtype=bool),'action':np.full(size,'v3',dtype=object),
                  'rule_id':np.full(size,'BEFORE_EVALUATION',dtype=object),'model_id':np.full(size,'NONE',dtype=object),
                  'fold':np.full(size,group,dtype=int),'train_cutoff':np.full(size,None,dtype=object),
                  'leaf_id':np.full(size,-1,dtype=int),'reason':np.full(size,'before_evaluation',dtype=object)}
        if arm=='U_READY':
            mask=(decision>=CUTS[0]).to_numpy()
            expected['allow'][mask]=True;expected['rule_id'][mask]='U_READY';expected['reason'][mask]='unfiltered_ready_control'
        else:
            for i,cut in enumerate(CUTS):
                mask=((decision>=cut)&((decision<CUTS[i+1]) if i+1<len(CUTS) else True)).to_numpy()
                ids=np.flatnonzero(mask)
                model=models[f'{cut.year}_f{group}_{arm}']
                assert slug not in model['training_slugs']
                nodes=walk_model(model,features.loc[mask])
                expected['model_id'][ids]=model['model_id'];expected['train_cutoff'][ids]=model['cutoff'];expected['leaf_id'][ids]=nodes
                for node in np.unique(nodes):
                    selected=ids[nodes==node]; advice=model['leaves'][str(node)]
                    expected['allow'][selected]=advice['allow'];expected['action'][selected]=advice['action']
                    expected['rule_id'][selected]=f'{model["model_id"]}_L{node}';expected['reason'][selected]=advice['reason']
        young=~d.ready90.to_numpy(bool)
        expected['allow'][young]=False;expected['rule_id'][young]='INSUFFICIENT_HISTORY90';expected['reason'][young]='insufficient_history90'
        for a,b in [('allow','admit_'+prefix),('action','route_'+prefix),('rule_id','rule_id_'+prefix)]+[(c,prefix+'_'+c) for c in ['model_id','fold','train_cutoff','leaf_id','reason']]:
            actual=saved[b]; target=expected[a]
            if a in ['allow','fold','leaf_id']:
                if a=='allow':assert pd.api.types.is_bool_dtype(actual)
                assert np.array_equal(actual.to_numpy(),target),f'schedule {slug}/{arm}/{prefix} {a}'
            else:
                actual=actual.where(actual.notna(),'').astype(str).to_numpy()
                target=pd.Series(target).fillna('').astype(str).to_numpy()
                assert np.array_equal(actual,target),f'schedule {slug}/{arm}/{prefix} {a}'
        for name in ('admit_'+prefix,'route_'+prefix,'rule_id_'+prefix):result[name]=saved[name].to_numpy()
    return result


def audit_account_coin(slug, jobs, root_string, models, summary_table, block_table, definitions):
    root=Path(root_string); results=root/'results'; counts={'accounts':0,'segments':0,'trades':0,'stop_records':0,'equity_marks':0,'opportunity_events':0,'calendar_rows':0,'schedule_rows':0}
    hourly=None; hourly_path=None
    records=[]
    for run_key,source in jobs:
        lo=max(pd.Timestamp(source['trade_start']),CUTS[0]);hi=pd.Timestamp(source['end'])
        if lo>=hi:continue
        meta=read_json(results/'inputs_used'/f'{run_key}.json')
        compare_nested(meta,source,'source identity')
        assert meta['run_key']==run_key and meta['slug']==slug
        equal(meta['eval_start'],str(lo),'start');equal(meta['eval_end'],str(hi),'end')
        path=LAB/source['hourly_path']
        if hourly_path!=path:
            assert sha(path)==source['hourly_sha256']
            hourly=read_frame(path).rename(columns={'ts':'timestamp'})
            hourly.timestamp=pd.to_datetime(hourly.timestamp,utc=True).dt.as_unit('ns')
            hourly=hourly.set_index('timestamp',drop=False);hourly_path=path
        d=read_frame(root/'cases/daily_features'/f'{run_key}.parquet')
        d.timestamp=pd.to_datetime(d.timestamp,utc=True).dt.as_unit('ns')
        decisions=read_frame(results/'inputs_used'/f'{run_key}_decisions.parquet')
        assert set(decisions.case_id)==set(ARMS)|{'U_READY'}
        h=hourly.loc[(hourly.index>=pd.Timestamp(source['input_start']))&(hourly.index<hi)]
        for arm in ('U_READY',*ARMS):
            schedule=decisions.loc[decisions.case_id.eq(arm)].reset_index(drop=True)
            observed=verify_schedule(d,schedule,slug,arm,models)
            daily=previous.add_causal_audit_features(observed).set_index('timestamp',drop=False)
            directory=results/'runs'/run_key/arm/'full'
            summary=read_json(directory/'summary.json')
            for key,value in {'fee':.001,'slip':.0004,'admission_routing':True,'reverse':False,'progress_days':4,
                              'notional_fraction':1.,'risk_fraction':None,'exit_state_policy':'v3','short_exit':'accel1_rsi30',
                              'direction_mode':'both','trend_filter':'none','entry_wait_days':0,'delay_hours':0}.items():
                equal(summary[key],value,'account configuration '+key)
            assert pd.Timestamp(summary['start'])==lo and pd.Timestamp(summary['end_exclusive'])==hi
            verified=audit_routed_account(directory,daily,h)
            trades=read_frame(directory/'trades.csv')
            previous.extra_stats(summary,trades)
            prior.compare_summary_row(summary_table,{'run_key':run_key,'case_id':arm},summary)
            row=summary_table.loc[summary_table.run_key.eq(run_key)&summary_table.case_id.eq(arm)].iloc[0]
            for action in ACTIONS:
                target=int(trades.exit_route.eq(action).sum()) if len(trades) else 0
                equal(row['route_'+action+'_trades'],target,'route trade count')
            expected_retention=summary['entry_fills']/summary['entry_attempts'] if summary['entry_attempts'] else None
            equal(row.admission_retained_ratio,expected_retention,'actual fills per entry attempt')
            selected=block_table.loc[block_table.run_key.eq(run_key)&block_table.case_id.eq(arm)]
            count=previous.audit_calendar_blocks(directory,lo,hi,definitions,selected)
            counts['accounts']+=1;counts['trades']+=verified['trades'];counts['stop_records']+=verified['stop_records']
            counts['equity_marks']+=verified['equity_marks_independently_rebuilt'];counts['opportunity_events']+=verified['opportunity_events']
            counts['calendar_rows']+=count;counts['schedule_rows']+=len(schedule)
        counts['segments']+=1
    return {'slug':slug,'status':'PASS',**counts}


def audit_accounts(root=ROUND,workers=2):
    root=Path(root);results=root/'results'
    complete=read_json(results/'completion.json');assert complete['complete']
    manifest=checksums(results); source=read_json(root/'cases/sources.json');models=read_json(root/'learning/models.json')
    started=read_json(results/'started.json')
    assert started['costs']=={'fee_per_side':.001,'slip_per_side':.0004}
    for relative,digest in started['source_pins'].items():assert sha(LAB/relative)==digest,relative
    pin=started['engine_pin'];assert sha(LAB/pin['engine_path'])==pin['engine_sha256']
    for relative,digest in pin['contracts'].items():assert sha(LAB/relative)==digest
    summary=read_frame(results/'summary.csv');blocks=read_frame(results/'blocks.csv');scope=read_frame(results/'scope.csv')
    assert len(scope)==len(source)==975
    assert not scope.run_key.duplicated().any()
    grouped={}
    for key,info in source.items():
        grouped.setdefault(info['slug'],[]).append((key,info))
        row=scope.loc[scope.run_key.eq(key)].iloc[0]
        lo=max(pd.Timestamp(info['trade_start']),CUTS[0]);hi=pd.Timestamp(info['end'])
        if lo>=hi:
            assert row.status=='NO_EVALUATION_OVERLAP' and not summary.run_key.eq(key).any()
        else:
            d=read_frame(root/'cases/daily_features'/f'{key}.parquet')
            times=pd.to_datetime(d.timestamp,utc=True)+DAY
            ready=int((d.ready90&times.ge(lo)&times.lt(hi)).sum())
            assert row.status==('ELIGIBLE' if ready else 'INSUFFICIENT_HISTORY90')
            assert row.ready90_signal_days==ready
            assert len(summary.loc[summary.run_key.eq(key)])==5
    definitions=[('cycle_2020_2024','2020-01-01','2025-01-01'),('calendar_2021_2023','2021-01-01','2024-01-01'),
        ('calendar_2023_2025','2023-01-01','2026-01-01'),('phase_2020_2021','2020-01-01','2022-01-01'),
        ('phase_2022','2022-01-01','2023-01-01'),('phase_2023_2024','2023-01-01','2025-01-01'),('phase_2025_2026','2025-01-01','2026-09-05')]
    definitions += [(f'year_{year}',f'{year}-01-01',f'{year+1}-01-01' if year<2026 else '2026-09-05') for year in range(2019,2027)]
    totals={k:0 for k in ['accounts','segments','trades','stop_records','equity_marks','opportunity_events','calendar_rows','schedule_rows']}
    errors=[];rows=[];start=time.monotonic()
    todo={}; identity=account_receipt_identity(root); result_hashes=read_json(results/'artifact_checksums.json')
    for slug,jobs in grouped.items():
        receipt_path=root/'audit/account_checkpoints'/f'{slug}.json'
        if receipt_path.exists():
            receipt=read_json(receipt_path);assert receipt['identity']==identity
            for path,digest in receipt['result_files'].items():assert result_hashes[path]==digest
            result=receipt['coin'];assert result['status']=='PASS';rows.append(result)
            for key in totals:totals[key]+=result[key]
        else:todo[slug]=jobs
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending={pool.submit(audit_checkpoint_coin,slug,jobs,str(root),models,identity):slug for slug,jobs in todo.items()}
        for i,future in enumerate(as_completed(pending),1):
            slug=pending[future]
            try:
                result=future.result();rows.append(result)
                for key in totals:totals[key]+=result[key]
            except Exception as error:
                errors.append({'slug':slug,'error':repr(error),'traceback':traceback.format_exc()});print('ACCOUNT AUDIT ERROR',slug,repr(error),flush=True)
            if i%25==0 or i==len(pending):print(f'Account audit {i}/{len(pending)}, errors {len(errors)}, seconds {time.monotonic()-start:.1f}',flush=True)
    report={'status':'PASS' if not errors else 'FAIL','totals':totals,'errors':errors,'coins':rows,'manifest':manifest,'elapsed_seconds':time.monotonic()-start}
    write_json(root/'audit/accounts.json',report)
    assert not errors
    assert totals['accounts']==len(summary)==complete['account_runs']
    return report



def verify_frozen_audits(root=ROUND):
    scripts=Path(__file__).parent
    expected={'audit_exit_state_machine_20260910.py':'0d730d508954a147cf3acda157c1d69f093b9e7060a6e709bb6c5a91d191d229',
              'audit_four_tests_20260910.py':'2da134653f63c06d621e2b66bb1fdd566c879192690d9bf3eaf31a24f93ef920',
              'audit_results.py':'f376e8560d724a039dc5612962ce719602dc2e21157683ed6f8c177e5a1d9dc1'}
    for name,digest in expected.items():assert sha(scripts/name)==digest,name
    audits={}
    for report_name,result_name,digest in [
        ('audit_history.json','history_results','063fb70b55f22d8d51070c0d9421c448351872ecfbe47e00de0fff4a1fac2836'),
        ('audit_history_verified.json','history_verified_results','6b1ae136475c443011c8c939db659f5443f7189873fa2e89e2536ea3f1b4ecc0')]:
        path=OLD/report_name;assert sha(path)==digest
        report=read_json(path);assert report['calculation_status']=='PASS'
        assert report['identity']['result_manifest_sha256']==sha(OLD/result_name/'artifact_checksums.json')
        raw=report['raw_calculation_report'];assert sha(LAB/raw['path'])==raw['sha256']
        audits[report_name]={'sha256':digest,'result_manifest_sha256':report['identity']['result_manifest_sha256'],
                            'status':report['status'],'accounts':report['accounts'],'segments':report['segments']}
    write_json(Path(root)/'audit/frozen_audit_provenance.json',{'audit_sources':expected,'reused_old_account_audits':audits,
      'old_account_equity_rescanned':False,'official_market_price_truth_verified':False,'status':'PASS'})



def account_receipt_identity(root):
    return {'audit_source_sha256':sha(Path(__file__)),
        'result_started_sha256':sha(root/'results/started.json'),
        'cases_manifest_sha256':sha(root/'cases/artifact_checksums.json'),
        'learning_manifest_sha256':sha(root/'learning/artifact_checksums.json')}


def audit_checkpoint_coin(slug,jobs,root_string,models,identity):
    root=Path(root_string); checkpoint=root/'results/checkpoints'/f'{slug}.json'
    body=read_json(checkpoint)
    summary=pd.DataFrame(body['summary']);blocks=pd.DataFrame(body['blocks'])
    definitions=[('cycle_2020_2024','2020-01-01','2025-01-01'),('calendar_2021_2023','2021-01-01','2024-01-01'),
        ('calendar_2023_2025','2023-01-01','2026-01-01'),('phase_2020_2021','2020-01-01','2022-01-01'),
        ('phase_2022','2022-01-01','2023-01-01'),('phase_2023_2024','2023-01-01','2025-01-01'),('phase_2025_2026','2025-01-01','2026-09-05')]
    definitions += [(f'year_{year}',f'{year}-01-01',f'{year+1}-01-01' if year<2026 else '2026-09-05') for year in range(2019,2027)]
    coin=audit_account_coin(slug,jobs,root_string,models,summary,blocks,definitions)
    files=[checkpoint]
    for run_key,source in jobs:
        files.extend((root/'results/runs'/run_key).rglob('*'))
        for tail in ['.json','_decisions.parquet']:
            path=root/'results/inputs_used'/(run_key+tail)
            if path.exists():files.append(path)
    retained={str(path.relative_to(root/'results')):sha(path) for path in files if path.is_file()}
    receipt={'identity':identity,'coin':coin,'result_files':retained}
    write_json(root/'audit/account_checkpoints'/f'{slug}.json',receipt)
    return coin


def audit_partial_accounts(root=ROUND,workers=2):
    root=Path(root); sources=read_json(root/'cases/sources.json'); models=read_json(root/'learning/models.json')
    groups={}
    for key,meta in sources.items():groups.setdefault(meta['slug'],[]).append((key,meta))
    identity=account_receipt_identity(root); pending=[]
    for slug,jobs in groups.items():
        saved=root/'audit/account_checkpoints'/f'{slug}.json'
        if saved.exists():
            assert read_json(saved)['identity']==identity
        elif (root/'results/checkpoints'/f'{slug}.json').exists():pending.append((slug,jobs))
    start=time.monotonic(); errors=[];done=0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(audit_checkpoint_coin,slug,jobs,str(root),models,identity):slug for slug,jobs in pending}
        for i,future in enumerate(as_completed(futures),1):
            slug=futures[future]
            try:future.result();done+=1
            except Exception as error:
                errors.append({'slug':slug,'error':repr(error),'traceback':traceback.format_exc()});print('PARTIAL ACCOUNT AUDIT ERROR',slug,repr(error),flush=True)
            if i%25==0 or i==len(futures):print(f'Finished-account audit {i}/{len(futures)}, errors {len(errors)}, seconds {time.monotonic()-start:.1f}',flush=True)
    report={'status':'PASS' if not errors else 'FAIL','checked_coins':done,'errors':errors,'identity':identity,'partial':True}
    write_json(root/'audit/partial_accounts.json',report)
    assert not errors
    return report


def audit_label_clock(root=ROUND):
    frame=prepare_cases(Path(root)/'cases')
    rows=[]
    for cut in CUTS:
        old=frame.ready90 & ~frame.terminal_any & frame.label_end.lt(cut)
        conservative=frame.ready90 & ~frame.terminal_any & frame.knowledge_end.lt(cut)
        difference=frame.loc[old.ne(conservative),'case_id'].tolist()
        rows.append({'cutoff':str(cut),'old_candidates':int(old.sum()),'conservative_candidates':int(conservative.sum()),'changed_members':difference})
        assert not difference
    result={'status':'PASS_ZERO_ACTUAL_MODEL_MEMBERSHIP_CHANGE','cutoffs':rows,
        'future_training_rule':'maximum exit_interval_end of all three actions strictly before cutoff',
        'past_shadow_history_rule':'exit_time strictly before decision_time AND exit_interval_end at or before decision_time',
        'reason':'Intrahour exit timestamp is interval start; exact next-open gap or TP exits at decision time must remain excluded from signal features.',
        'actual_model_decisions_affected':False,'original_case_fields_preserved':True}
    write_json(Path(root)/'audit/label_clock_clarification.json',result)
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['cases','models','accounts','accounts-partial','all'],default='all')
    parser.add_argument('--root',type=Path,default=ROUND)
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    verify_frozen_audits(args.root)
    audit_label_clock(args.root)
    if args.mode=='accounts-partial':audit_partial_accounts(args.root,args.workers)
    if args.mode in ['cases','all']:
        audit_cases(args.root,args.workers)
    if args.mode in ['models','all']:
        result=audit_models(args.root)
        write_json(args.root/'audit/models.json',result)
        print(json.dumps(result),flush=True)
    if args.mode in ['accounts','all']:
        audit_accounts(args.root,args.workers)


if __name__=='__main__':main()
