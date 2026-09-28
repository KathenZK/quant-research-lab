"""Read-only, independent verification of every saved R4 ledger.

This script never calls or imports a strategy simulator. It checks recorded
decisions against frozen daily/hourly inputs and verifies account arithmetic.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


BASE = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = BASE / "artifacts/r4_close_progress_20260909"
DEFAULT_AUDIT = BASE / "artifacts/r4_audit_20260909.json"
INPUT = BASE / "artifacts/inputs_20260909"
DAY = pd.Timedelta(days=1)
HOUR = pd.Timedelta(hours=1)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def equal(actual, expected, label, atol=1e-8):
    if expected is None or pd.isna(expected):
        assert actual is None or pd.isna(actual), f"{label}: {actual!r} != missing"
    elif isinstance(expected, (bool, np.bool_)):
        assert bool(actual) == bool(expected), f"{label}: {actual!r} != {expected!r}"
    elif isinstance(expected, (int, float, np.integer, np.floating)):
        assert np.isfinite(actual) and abs(float(actual) - float(expected)) <= atol, (
            f"{label}: {actual!r} != {expected!r}")
    elif isinstance(expected, pd.Timestamp):
        assert pd.Timestamp(actual) == expected, f"{label}: {actual!r} != {expected!r}"
    else:
        assert actual == expected, f"{label}: {actual!r} != {expected!r}"


def verify_hash_map(directory, filename="artifact_checksums.json", exact=False):
    hashes = read_json(directory / filename)
    for name, expected in hashes.items():
        assert sha(directory / name) == expected, f"Checksum mismatch: {directory / name}"
    if exact:
        actual = {str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file()}
        assert actual == set(hashes) | {filename}, "Unmanifested/missing result files"
    return len(hashes)


def parse_times(frame, names):
    for name in names:
        if name in frame:
            frame[name] = pd.to_datetime(frame[name], utc=True, format="mixed").dt.as_unit("ns")
    return frame


def audit_stop_path(trade, records, daily, config, window_end):
    """Recalculate only each logged stop decision, never select any trades."""
    label = f"trade {trade.trade_id}"
    side = int(trade.side)
    entry = records.iloc[0]
    equal(entry.timestamp, trade.entry_time, label + " initial stop time")
    equal(trade.progress_source, config["progress_source"], label + " trade source")
    assert records.progress_source.eq(config["progress_source"]).all(), label + " stop source"
    signal = daily.loc[trade.signal_day]
    uncapped = float(signal.ma - side * 1.5 * signal.atr)
    assert side * (trade.entry_reference - uncapped) > 0, label + " invalid original stop"
    initial = uncapped
    if config["initial_stop_cap_pct"] is not None:
        capped = trade.entry_price * (1 - side * config["initial_stop_cap_pct"])
        initial = max(initial, capped) if side == 1 else min(initial, capped)
    equal(trade.uncapped_initial_stop, uncapped, label + " uncapped stop")
    equal(trade.initial_stop, initial, label + " capped stop")
    equal(trade.cap_applied, initial != uncapped, label + " cap applied")
    equal(trade.initial_stop_risk_price, side * (trade.entry_price - initial), label + " risk price")
    equal(trade.initial_stop_risk_pct, side * (trade.entry_price - initial) / trade.entry_price * 100, label + " risk pct")
    expected_updates = pd.date_range(trade.entry_time.floor("D") + DAY, trade.exit_time.floor("D"), freq="D")
    expected_updates = expected_updates[expected_updates < window_end]
    assert records.timestamp.tolist() == [trade.entry_time, *expected_updates], label + " daily update times"
    for field, expected in {"new_mult": 1.5, "new_armed": False, "initialized": False,
                            "extreme_price": None, "extreme_day": None, "no_new_extreme_days": 0,
                            "arm_day": None, "new_stop": initial, "old_stop": initial,
                            "natural_candidate": uncapped}.items():
        equal(entry[field], expected, label + " initial " + field)
    old_stop, mult, armed, initialized = initial, 1.5, False, False
    extreme, extreme_day, arm_day, count, reductions, decisive_count = None, None, None, 0, 0, 0
    for record in records.iloc[1:].itertuples(index=False):
        day = daily.loc[record.signal_day]
        assert record.timestamp == record.signal_day + DAY, label + " used unclosed daily bar"
        equal(record.old_stop, old_stop, label + " old stop")
        equal(record.old_mult, mult, label + " old multiplier")
        equal(record.old_armed, armed, label + " prior arming")
        natural = float(day.ma - side * mult * day.atr)
        stalled = side * (natural - old_stop) <= 1e-12 * max(1.0, abs(old_stop))
        equal(record.natural_candidate, natural, label + " MA candidate")
        equal(record.stalled, stalled, label + " MA stall")
        full_day = record.signal_day >= trade.entry_time
        equal(record.full_holding_day, full_day, label + " complete holding day")
        new_extreme, tighten = False, False
        if config["progress_days"]:
            if full_day:
                observation = float(day.close if config["progress_source"] == "close"
                                    else day.high if side == 1 else day.low)
                if not initialized:
                    initialized, extreme, extreme_day, count = True, observation, record.signal_day, 0
                    new_extreme = True
                else:
                    new_extreme = side * (observation - extreme) > 0
                    if new_extreme:
                        extreme, extreme_day, count = observation, record.signal_day, 0
                    else:
                        count += 1
                    if not armed and count >= config["progress_days"]:
                        armed, arm_day = True, record.signal_day
                    tighten = armed and mult > .5
        elif config["tighten_mode"] != "fixed" and mult > .5:
            if config["tighten_mode"] == "armed_daily" and armed:
                tighten = True
            elif bool(record.profit_eligible) and stalled:
                tighten = True
                if config["tighten_mode"] == "armed_daily":
                    armed = True
        if tighten:
            mult = max(.5, round(mult - .2, 10))
            reductions += 1
        proposed = float(day.ma - side * mult * day.atr)
        new_stop = max(old_stop, proposed) if side == 1 else min(old_stop, proposed)
        anchor, decisive = None, False
        if config["stop_anchor"] == "extreme" and armed and initialized:
            anchor = float(extreme - side * mult * day.atr)
            decisive = side * (anchor - new_stop) > 0
            if decisive:
                new_stop = anchor
                decisive_count += 1
        expected = {"initialized": initialized, "extreme_price": extreme, "extreme_day": extreme_day,
                    "no_new_extreme_days": count, "arm_day": arm_day, "new_armed": armed,
                    "new_extreme": new_extreme, "new_mult": mult, "tightened": tighten,
                    "anchor_candidate": anchor, "anchor_decisive": decisive, "new_stop": new_stop}
        for field, value in expected.items():
            equal(getattr(record, field), value, label + " " + field)
        assert side * (new_stop - old_stop) >= -1e-12, label + " stop loosened"
        assert .5 <= mult <= 1.5, label + " invalid ATR floor"
        old_stop = new_stop
    for field, value in {"stop": old_stop, "stop_mult": mult, "armed": armed, "initialized": initialized,
                         "extreme_price": extreme, "extreme_day": extreme_day, "no_new_extreme_days": count,
                         "arm_day": arm_day, "tightening_days": reductions,
                         "anchor_decisive_days": decisive_count, "stop_floor_reached": mult == .5}.items():
        equal(getattr(trade, field), value, label + " final " + field)


def audit_ledger(directory, config, daily, hourly):
    summary = read_json(directory / "summary.json")
    for field, expected in config.items():
        equal(summary[field], expected, directory.name + " config " + field)
    assert summary["funding_window_verified"] is False
    trades = parse_times(pd.read_csv(directory / "trades.csv"), ["entry_time", "exit_time", "exit_interval_end", "signal_day", "cross_day", "extreme_day", "arm_day", "opposite_cross_signal_day"])
    stops = parse_times(pd.read_csv(directory / "stops.csv"), ["timestamp", "signal_day", "extreme_day", "arm_day"])
    curve = pd.read_parquet(directory / "equity.parquet")
    equal(len(trades), summary["trades"], "trade count")
    equal(10000 + trades.net_pnl.sum(), summary["ending_equity"], "account reconciliation")
    equal(curve.equity.iloc[-1], summary["ending_equity"], "final equity mark")
    equal((summary["ending_equity"] / 10000 - 1) * 100, summary["return_pct"], "total return")
    values = curve.equity.to_numpy()
    drawdown = float(np.min(values / np.maximum.accumulate(np.r_[10000., values])[1:] - 1) * 100)
    equal(drawdown, summary["max_drawdown_pct"], "drawdown")
    equal(trades.entry_fee.sum() + trades.exit_fee.sum(), summary["fee_total"], "fee total")
    equal(trades.funding_paid.sum(), summary["funding_paid"], "funding total")
    equal(trades.carry_paid.sum(), summary["carry_paid"], "carry total")
    if (directory / "funding.csv").exists():
        funding = pd.read_csv(directory / "funding.csv")
        equal(funding.cost.sum(), summary["funding_paid"], "funding events total")
    assert trades.trade_id.tolist() == list(range(1, len(trades) + 1))
    assert set(stops.trade_id) == set(trades.trade_id)
    previous_end_equity, previous_exit = 10000., None
    for trade in trades.itertuples(index=False):
        side, fee, slip = int(trade.side), config["fee"], config["slip"]
        equal(trade.entry_equity, previous_end_equity, "next position equity")
        if previous_exit is not None:
            assert trade.entry_time >= previous_exit, "Overlapping positions"
        previous_end_equity, previous_exit = trade.end_equity, trade.exit_time
        equal(trade.entry_price, trade.entry_reference * (1 + side * slip), "entry slip")
        equal(trade.exit_price, trade.exit_reference * (1 - side * slip), "exit slip")
        equal(trade.qty, trade.entry_equity / (trade.entry_price * (1 + fee)), "1x entry size")
        equal(trade.entry_fee, trade.qty * trade.entry_price * fee, "entry fee")
        equal(trade.exit_fee, trade.qty * trade.exit_price * fee, "exit fee")
        gross = side * trade.qty * (trade.exit_price - trade.entry_price)
        equal(trade.gross_pnl, gross, "gross PnL")
        net = gross - trade.entry_fee - trade.exit_fee - trade.funding_paid - trade.carry_paid
        equal(trade.net_pnl, net, "net PnL")
        equal(trade.end_equity, trade.entry_equity + net, "exit equity")
        equal(trade.return_on_entry_equity, net / trade.entry_equity, "trade account return")
        signal = daily.loc[trade.signal_day]
        assert int(signal.cross) == side and side * signal.slope > config["slope"], "Nonqualifying entry"
        assert trade.entry_reason == "daily_cross" and not config["reverse"], "Unexpected reversal"
        equal(trade.entry_time, trade.signal_day + DAY + HOUR * config["delay_hours"], "entry time")
        equal(trade.entry_reference, hourly.loc[trade.entry_time, "open"], "entry open")
        records = stops[stops.trade_id == trade.trade_id].reset_index(drop=True)
        audit_stop_path(trade, records, daily, config, pd.Timestamp(summary["end_exclusive"]))
        if trade.exit_reason == "sample_end":
            equal(trade.exit_time, pd.Timestamp(summary["end_exclusive"]), "terminal settlement time")
            equal(trade.exit_reference, hourly.loc[trade.exit_time - HOUR, "close"], "terminal settlement price")
        else:
            bar = hourly.loc[trade.exit_time]
            if trade.exit_reason == "stop_gap":
                assert side * (bar.open - trade.stop) <= 1e-8, "Gap not through stop"
                equal(trade.exit_reference, bar.open, "gap fill")
            elif trade.exit_reason == "stop_intrahour":
                assert side * (bar.open - trade.stop) > 0, "Gap wrongly filled at stop"
                assert bar.low <= trade.stop if side == 1 else bar.high >= trade.stop, "Stop not touched"
                equal(trade.exit_reference, trade.stop, "intrahour stop fill")
                equal(trade.exit_interval_end, trade.exit_time + HOUR, "uncertain stop interval")
            else:
                assert side * (bar.open - trade.stop) > 0, "Exit ignored gap-stop priority"
                equal(trade.exit_reference, bar.open, "daily exit open")
                if trade.exit_reason == "opposite_cross":
                    assert config["exit_opposite_cross"]
                    signal_day = trade.opposite_cross_signal_day
                    equal(daily.loc[signal_day, "cross"], -side, "opposite exit cross")
                    equal(trade.exit_time, signal_day + DAY + HOUR * config["delay_hours"], "opposite exit time")
                    assert not ((trades.signal_day == signal_day) & (trades.entry_time >= trade.exit_time)).any(), "Cross exit signal reopened"
                else:
                    assert trade.exit_reason == "accel1_rsi30", "Unrecognized exit"
                    signal_day = pd.Timestamp(trade.tp_signal_day)
                    rsi_day = daily.loc[signal_day]
                    assert side == -1 and rsi_day.rsi <= 30 and bool(rsi_day.accel1)
                    expected_fill = rsi_day.close * (1 + config["slip"])
                    expected_profit = trade.qty * (trade.entry_price - expected_fill) - trade.entry_fee - trade.qty * expected_fill * config["fee"] - trade.funding_paid - trade.carry_paid
                    assert expected_profit > 0, "Short RSI exit lacks expected profit after costs"
                    equal(trade.exit_time, signal_day + DAY + HOUR * config["delay_hours"], "RSI exit time")
                    assert not config["exit_opposite_cross"] or int(rsi_day.cross) != 1, "RSI ignored cross priority"
        if trade.exit_reason != "stop_intrahour":
            equal(trade.exit_interval_end, trade.exit_time, "exact fill time")
    equal(int(trades.tightening_days.sum()), int(stops.tightened.sum()), "tightening counts")
    equal(int(trades.anchor_decisive_days.sum()), int(stops.anchor_decisive.sum()), "anchor counts")
    equal(summary["opposite_cross_exits"], int((trades.exit_reason == "opposite_cross").sum()), "cross exits")
    return {"directory": str(directory.relative_to(BASE)), "trades": len(trades), "stop_records": len(stops),
            "equity_records": len(curve), "progress_armed_trades": summary["progress_armed_trades"],
            "status": "PASS"}, trades


def audit_global_review(results, hourly, full_trades):
    review = parse_times(pd.read_csv(results / "all_full_window_trades.csv"), ["entry_time", "exit_time"])
    assert len(review) == sum(len(t) for t in full_trades.values()), "Missing full-window trades"
    old = full_trades["B0_r2_stall"]
    old_lookup = {(t.entry_time, int(t.side)): int(t.trade_id) for t in old.itertuples(index=False)}
    for row in review.itertuples(index=False):
        trade = full_trades[row.case_id].set_index("trade_id").loc[row.trade_id]
        for field, expected in trade.items():
            equal(getattr(row, field), expected, "review trade field " + field)
        equal(row.same_entry_old_trade_id, old_lookup.get((row.entry_time, int(row.side))), "review same entry")
        held = hourly[(hourly.index >= row.entry_time) & (hourly.index + HOUR <= row.exit_time)]
        observed = float(held.high.max() if row.side == 1 else held.low.min()) if len(held) else row.entry_price
        favorable = max(observed, row.entry_price, row.exit_price) if row.side == 1 else min(observed, row.entry_price, row.exit_price)
        mfe = max(0., row.side * (favorable / row.entry_price - 1) * 100)
        realized = row.side * (row.exit_price / row.entry_price - 1) * 100
        equal(row.favorable_price_in_completed_held_hours, favorable, "review favorable price")
        equal(row.favorable_excursion_lower_bound_pct, mfe, "review favorable excursion")
        equal(row.giveback_lower_bound_pct, max(0., mfe - realized), "review giveback")
    return len(review)


def audit_source_only_change():
    """Prove the AST equals R3 after removing the documented source selector."""
    counts = {"field": 0, "validation": 0, "name": 0, "log": 0, "observation": 0}

    class RemoveSelector(ast.NodeTransformer):
        def visit_AnnAssign(self, node):
            if isinstance(node.target, ast.Name) and node.target.id == "progress_source":
                counts["field"] += 1
                return None
            return self.generic_visit(node)

        def visit_If(self, node):
            if "self.progress_source" in ast.unparse(node.test):
                assert ast.unparse(node.test) == "self.progress_source not in {'high_low', 'close'}"
                counts["validation"] += 1
                return None
            return self.generic_visit(node)

        def visit_JoinedStr(self, node):
            if (len(node.values) >= 2 and isinstance(node.values[-2], ast.Constant)
                    and node.values[-2].value == "_source"
                    and ast.unparse(node.values[-1].value) == "self.progress_source"):
                node.values = node.values[:-2]
                counts["name"] += 1
            return self.generic_visit(node)

        def visit_Dict(self, node):
            pairs = []
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "progress_source":
                    assert ast.unparse(value) == "config.progress_source"
                    counts["log"] += 1
                else:
                    pairs.append((key, value))
            node.keys, node.values = [p[0] for p in pairs], [p[1] for p in pairs]
            return self.generic_visit(node)

        def visit_IfExp(self, node):
            if ast.unparse(node.test) == "config.progress_source == 'close'":
                assert ast.unparse(node.body) == "row.close"
                assert ast.unparse(node.orelse) == "row.high if side == 1 else row.low"
                counts["observation"] += 1
                return self.generic_visit(node.orelse)
            return self.generic_visit(node)

    old = ast.parse((BASE / "scripts/engine_r3.py").read_text())
    new = ast.parse((BASE / "scripts/engine_r4.py").read_text())
    old.body, new.body = old.body[1:], new.body[1:]
    new = RemoveSelector().visit(new)
    assert counts == {"field": 1, "validation": 1, "name": 1, "log": 3, "observation": 2}, counts
    assert ast.dump(old, include_attributes=False) == ast.dump(new, include_attributes=False), "R4 changed code beyond the declared source selector"
    return counts


def audit_costs_and_marks(directory, config, hourly, native_funding, carry_daily):
    """Rebuild accounting for saved trades, including each intraperiod equity mark."""
    summary = read_json(directory / "summary.json")
    trades = parse_times(pd.read_csv(directory / "trades.csv"), ["entry_time", "exit_time"])
    stops = parse_times(pd.read_csv(directory / "stops.csv"), ["timestamp", "signal_day"])
    marks = pd.read_parquet(directory / "equity.parquet")
    marks["timestamp"] = pd.to_datetime(marks.timestamp, utc=True).dt.as_unit("ns")
    fund_path = directory / "funding.csv"
    funds = (parse_times(pd.read_csv(fund_path), ["timestamp", "accounted_at_hour"])
             if fund_path.exists() else pd.DataFrame(columns=["timestamp", "trade_id", "cost", "accounted_at_hour"]))
    all_expected_events, verified_marks = 0, 0
    for trade in trades.itertuples(index=False):
        held = hourly[(hourly.index >= trade.entry_time) &
                      ((hourly.index < trade.exit_time) |
                       ((hourly.index == trade.exit_time) & (trade.exit_reason == "stop_intrahour")))]
        carry = held.open.to_numpy() * trade.qty * carry_daily / 24
        equal(trade.carry_paid, carry.sum(), "carry reconstructed from held hours")
        one = funds[funds.trade_id == trade.trade_id].reset_index(drop=True)
        if native_funding is not None:
            # Boundary events precede entries/exits; intrahour events are assigned
            # before hourly stop detection, as explicitly disclosed in the engine.
            end_cut = trade.exit_time + (HOUR if trade.exit_reason == "stop_intrahour" else pd.Timedelta(0))
            if trade.exit_reason == "stop_intrahour":
                selected = native_funding[(native_funding.index > trade.entry_time) & (native_funding.index < end_cut)]
            else:
                selected = native_funding[(native_funding.index > trade.entry_time) & (native_funding.index <= end_cut)]
            assert one.timestamp.tolist() == selected.index.tolist(), "Missing/unexpected charged funding events"
            all_expected_events += len(selected)
            for event, source in zip(one.itertuples(index=False), selected.itertuples()):
                proxy = not (pd.notna(source.mark_price) and source.mark_price > 0)
                boundary = source.Index.floor("h")
                reference = hourly.loc[boundary, "open"] if boundary in hourly.index else hourly.loc[boundary - HOUR, "close"]
                mark = reference if proxy else source.mark_price
                equal(event.mark_proxy, proxy, "funding proxy flag")
                equal(event.accounted_at_hour, boundary, "funding accounting hour")
                equal(event.mark_price_used, mark, "funding mark")
                equal(event.rate, source.funding_rate, "funding rate")
                equal(event.cost, trade.side * trade.qty * mark * source.funding_rate, "funding cost")
        else:
            assert one.empty and trade.funding_paid == 0, "Unexpected funding in price-only run"
        equal(trade.funding_paid, one.cost.sum(), "trade funding reconciliation")
        mark_part = marks[(marks.side == trade.side) & (marks.timestamp >= trade.entry_time) &
                          (marks.timestamp <= trade.exit_time)].copy()
        assert mark_part.kind.isin(["entry", "open", "hour_close"]).all()
        times = mark_part.timestamp.astype("int64").to_numpy()
        carry_prefix = np.r_[0., np.cumsum(carry)]
        carried = carry_prefix[np.searchsorted(held.index.asi8, times, side="left")]
        fund_times = pd.DatetimeIndex(one.timestamp).asi8
        fund_prefix = np.r_[0., np.cumsum(one.cost.to_numpy(dtype=float))]
        funded = fund_prefix[np.searchsorted(fund_times, times, side="left")]
        open_mask = mark_part.kind.to_numpy() == "open"
        funded[open_mask] = fund_prefix[np.searchsorted(fund_times, times[open_mask], side="right")]
        expected = trade.entry_equity - trade.entry_fee - carried - funded + trade.side * trade.qty * (mark_part.price.to_numpy() - trade.entry_price)
        assert np.allclose(mark_part.equity.to_numpy(), expected, rtol=0, atol=1e-8), "Held-position equity marks fail independent reconstruction"
        verified_marks += len(mark_part)
        own_stops = stops[(stops.trade_id == trade.trade_id) & (stops.tightening_trigger != "entry")]
        for record in own_stops.itertuples(index=False):
            prior_carry = carry_prefix[np.searchsorted(held.index.asi8, record.timestamp.value, side="left")]
            prior_fund = fund_prefix[np.searchsorted(fund_times, record.timestamp.value, side="left")]
            # The prior daily close is the hourly close immediately before midnight.
            close = hourly.loc[record.timestamp - HOUR, "close"]
            fill = close * (1 - trade.side * config["slip"])
            profit = trade.side * trade.qty * (fill - trade.entry_price) - trade.entry_fee - trade.qty * fill * config["fee"] - prior_carry - prior_fund
            favorable = trade.side * (close - trade.entry_price)
            equal(record.expected_profit_at_close, profit, "prior-close expected profit")
            equal(record.favorable_move_atr, favorable / trade.entry_atr, "prior-close favorable movement")
            equal(record.profit_eligible, profit > 0 and favorable >= config["profit_trigger_atr"] * trade.entry_atr, "prior-close profit eligibility")
        before_exit = hourly[(hourly.index >= trade.entry_time) & (hourly.index < trade.exit_time)]
        position_stops = stops[stops.trade_id == trade.trade_id]
        stop_index = np.searchsorted(position_stops.timestamp.astype("int64").to_numpy(), before_exit.index.asi8, side="right") - 1
        assert (stop_index >= 0).all(), "Held hour has no prior executable stop"
        stop_values = position_stops.new_stop.to_numpy()[stop_index]
        adverse = before_exit.low.to_numpy() if trade.side == 1 else before_exit.high.to_numpy()
        assert (trade.side * (adverse - stop_values) > 0).all(), "A preceding held hour already crossed its effective stop"
    flat = marks[marks.side == 0]
    exits = trades.exit_time.astype("int64").to_numpy()
    flat_times = flat.timestamp.astype("int64").to_numpy()
    indexes = np.searchsorted(exits, flat_times, side="left")
    settled = flat.kind.to_numpy() == "exit"
    indexes[settled] = np.searchsorted(exits, flat_times[settled], side="right")
    ends = np.r_[10000., trades.end_equity.to_numpy()]
    expected_flat = ends[indexes]
    assert np.allclose(flat.equity.to_numpy(), expected_flat, rtol=0, atol=1e-8), "Flat equity does not match latest settled trade"
    verified_marks += len(flat)
    assert verified_marks == len(marks), "Unassigned/double-counted equity marks"
    equal(summary["funding_events_charged"], all_expected_events, "charged funding count")
    return {"equity_marks_independently_rebuilt": verified_marks, "funding_events_rebuilt": all_expected_events,
            "carry_hourly_amounts_rebuilt": True, "prior_close_profit_flags_rebuilt": True}


def audit_saved_controls(results, baselines):
    parent = BASE / "artifacts/r3_price_progress_20260909"
    count = 0
    assert len(baselines) == 15 and all(x["live_r3_r4_exact_equal"] for x in baselines)
    assert sum(x["has_frozen_r3_result"] for x in baselines) == 12
    for item in baselines:
        if not item["has_frozen_r3_result"]:
            assert item["case_id"] == "H1_ma" and item["frozen_csv_max_absolute_difference"] is None
            continue
        assert item["frozen_csv_max_absolute_difference"] <= 1e-8
        old_dir = parent / "runs" / item["prior_case_id"] / item["window"]
        new_dir = results / "runs" / item["case_id"] / item["window"]
        for filename in ["trades.csv", "stops.csv"]:
            old, new = pd.read_csv(old_dir / filename), pd.read_csv(new_dir / filename)
            pd.testing.assert_frame_equal(old, new[old.columns], check_exact=True)
        pd.testing.assert_frame_equal(pd.read_parquet(old_dir / "equity.parquet"), pd.read_parquet(new_dir / "equity.parquet"), check_exact=True)
        old_summary, new_summary = read_json(old_dir / "summary.json"), read_json(new_dir / "summary.json")
        for field, expected in old_summary.items():
            if field != "name":
                equal(new_summary[field], expected, "saved R3 control summary " + field, atol=0)
        count += 1
    return count


def audit_source_pairs(results, full_trades, grid):
    pairs = parse_times(pd.read_csv(results / "source_trade_pairs.csv"), ["entry_time", "exit_time_high_low", "exit_time_close", "arm_day_high_low", "arm_day_close"])
    compared = 0
    for n in [1, 2, 3, 4]:
        left = full_trades[f"H{n}_ma"].set_index(["entry_time", "side"])
        right = full_trades[f"C{n}_ma"].set_index(["entry_time", "side"])
        part = pairs[pairs.days == n]
        expected_keys = set(left.index) | set(right.index)
        assert set(zip(part.entry_time, part.side)) == expected_keys and len(part) == len(expected_keys), "Incomplete source-paired opportunity ledger"
        for row in part.itertuples(index=False):
            key = (row.entry_time, int(row.side))
            expected_type = "both" if key in left.index and key in right.index else "left_only" if key in left.index else "right_only"
            equal(row.match_type, expected_type, "source-pair type")
            for label, source in [("high_low", left), ("close", right)]:
                for field in ["trade_id", "exit_time", "entry_price", "exit_price", "return_on_entry_equity", "arm_day", "tightening_days", "net_pnl", "exit_reason"]:
                    expected = source.loc[key, field] if key in source.index else None
                    equal(getattr(row, field + "_" + label), expected, "source-pair " + field)
            if expected_type == "both":
                equal(row.close_minus_high_low_trade_return_pp, 100 * (right.loc[key, "return_on_entry_equity"] - left.loc[key, "return_on_entry_equity"]), "source-pair return difference")
                equal(row.close_exit_earlier, right.loc[key, "exit_time"] < left.loc[key, "exit_time"], "source-pair earlier exit")
                equal(row.close_exit_later, right.loc[key, "exit_time"] > left.loc[key, "exit_time"], "source-pair later exit")
            else:
                equal(row.close_minus_high_low_trade_return_pp, None, "unmatched entry has no causal return difference")
            compared += 1
    comparison = pd.read_csv(results / "source_comparison.csv")
    assert len(comparison) == 12
    for row in comparison.itertuples(index=False):
        old = grid[(grid.case_id == f"H{row.days}_ma") & (grid.window == row.window)].iloc[0]
        new = grid[(grid.case_id == f"C{row.days}_ma") & (grid.window == row.window)].iloc[0]
        for field, expected in {"high_low_return_pct": old.return_pct, "close_return_pct": new.return_pct,
                                "return_change_pp": new.return_pct - old.return_pct,
                                "high_low_drawdown_pct": old.max_drawdown_pct, "close_drawdown_pct": new.max_drawdown_pct,
                                "drawdown_reduction_pp": new.max_drawdown_pct - old.max_drawdown_pct,
                                "high_low_trades": old.trades, "close_trades": new.trades}.items():
            equal(getattr(row, field), expected, "source comparison " + field)
    return compared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()
    results, output = args.results.resolve(), args.audit_output.resolve()
    if output.exists():
        parser.error("Preserve the prior audit; use a new --audit-output path")
    manifest = read_json(results / "run_manifest.json")
    parent = BASE / "artifacts/r3_price_progress_20260909"
    parent_manifest = read_json(parent / "run_manifest.json")
    for key, path in {"engine_sha256": BASE / "scripts/engine_r4.py",
                      "run_script_sha256": BASE / "scripts/run_r4.py",
                      "contract_sha256": BASE / "specs/r4-close-progress-20260909.md",
                      "input_checksums_sha256": INPUT / "checksums.json",
                      "r3_checksum_manifest_sha256": parent / "artifact_checksums.json"}.items():
        assert sha(path) == manifest[key], "Frozen R4 source changed: " + key
    for key, path in {"engine_sha256": BASE / "scripts/engine_r3.py",
                      "run_script_sha256": BASE / "scripts/run_r3.py",
                      "contract_sha256": BASE / "specs/r3-price-progress-20260909.md",
                      "input_checksums_sha256": INPUT / "checksums.json"}.items():
        assert sha(path) == parent_manifest[key], "Frozen R3 source changed: " + key
    hashed_results = verify_hash_map(results, exact=True)
    hashed_inputs = verify_hash_map(INPUT, "checksums.json")
    hashed_parent = verify_hash_map(parent, exact=True)
    verify_hash_map(BASE / "artifacts/r2_slowdown_tightening_20260909", exact=True)
    source_guard = audit_source_only_change()
    assert manifest["round"] == "R4" and manifest["primary_case"] == "C1_ma" and not manifest["funding_window_verified"]
    assert manifest["classification"] == "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS"
    assert manifest["windows"] == parent_manifest["windows"]
    cases = {row["case_id"]: row["config"] for row in manifest["cases"]}
    assert set(cases) == {"B0_r2_stall", *[f"{p}{n}_ma" for p in ["H", "C"] for n in [1, 2, 3, 4]]}
    assert set(manifest["sensitivity_cases"]) == set(cases)
    base_config = parent_manifest["cases"][0]["config"]
    for case_id, config in cases.items():
        expected = {**base_config, "progress_source": "high_low"}
        if case_id != "B0_r2_stall":
            expected.update(tighten_mode="fixed", progress_days=int(case_id[1]), progress_source="close" if case_id.startswith("C") else "high_low")
        assert config == expected, "Undeclared parameter variation: " + case_id
    pd.testing.assert_frame_equal(pd.read_csv(results / "daily_features.csv"), pd.read_csv(parent / "daily_features.csv"), check_exact=True)
    daily = parse_times(pd.read_csv(results / "daily_features.csv"), ["timestamp"]).set_index("timestamp")
    hourly = pd.read_parquet(INPUT / "hourly.parquet").set_index("ts")
    hourly.index = hourly.index.as_unit("ns")
    native_funding = pd.read_parquet(INPUT / "funding_observed_unverified.parquet").set_index("ts").sort_index()
    native_funding.index = native_funding.index.as_unit("ns")
    baselines = read_json(results / "baseline_reproduction.json")
    baseline_frames = audit_saved_controls(results, baselines)
    grid, stress = pd.read_csv(results / "all_results.csv"), pd.read_csv(results / "sensitivity.csv")
    assert len(grid) == 27 and len(stress) == 36
    expected_dirs, checks, full_trades = set(), [], {}
    for case_id, config in cases.items():
        for window in manifest["windows"]:
            directory = results / "runs" / case_id / window
            expected_dirs.add(directory)
            check, trades = audit_ledger(directory, config, daily, hourly)
            check.update(audit_costs_and_marks(directory, config, hourly, None, 0))
            checks.append(check)
            saved = read_json(directory / "summary.json")
            row = grid[(grid.case_id == case_id) & (grid.window == window)]
            assert len(row) == 1
            for key in ["return_pct", "max_drawdown_pct", "fee_total", "trades", "ending_equity"]:
                equal(row.iloc[0][key], saved[key], "grid versus ledger " + key)
            if window == "full":
                full_trades[case_id] = trades
        for scenario in ["slippage_10bp", "daily_signal_delay_1h", "adverse_carry_5bp_day", "observed_funding_unverified"]:
            variant = dict(config)
            if scenario == "slippage_10bp":
                variant["slip"] = .001
            if scenario == "daily_signal_delay_1h":
                variant["delay_hours"] = 1
            directory = results / "sensitivity" / case_id / scenario
            expected_dirs.add(directory)
            check, _ = audit_ledger(directory, variant, daily, hourly)
            check.update(audit_costs_and_marks(directory, variant, hourly,
                                              native_funding if scenario == "observed_funding_unverified" else None,
                                              .0005 if scenario == "adverse_carry_5bp_day" else 0))
            checks.append(check)
            row = stress[(stress.case_id == case_id) & (stress.scenario == scenario)]
            assert len(row) == 1
            saved = read_json(directory / "summary.json")
            for key in ["return_pct", "max_drawdown_pct", "fee_total", "trades", "ending_equity"]:
                equal(row.iloc[0][key], saved[key], "stress versus ledger " + key)
    actual_dirs = {p.parent for p in results.rglob("summary.json")}
    assert actual_dirs == expected_dirs and len(checks) == 63, "Missing/unexpected ledgers"
    review_count = audit_global_review(results, hourly, full_trades)
    paired_count = audit_source_pairs(results, full_trades, grid)
    audit = {"status": "PASS", "method": "Read-only independent ledger/input reconstruction; no simulator imported or called",
             "audit_script_sha256": sha(Path(__file__)), "result_manifest_sha256": sha(results / "run_manifest.json"),
             "result_checksum_manifest_sha256": sha(results / "artifact_checksums.json"),
             "source_hashes_verified": True, "result_files_hashed": hashed_results,
             "input_files_hashed": hashed_inputs, "parent_r3_files_hashed": hashed_parent,
             "source_only_ast_equivalence_after_removing_declared_changes": source_guard,
             "baseline_controls": baselines, "saved_r3_r4_ledgers_exact_equal": baseline_frames,
             "ledgers_verified": len(checks), "main_result_rows": len(grid), "sensitivity_rows": len(stress),
             "all_full_window_trades_verified": review_count, "all_ledger_trades_verified": sum(c["trades"] for c in checks),
             "all_stop_records_verified": sum(c["stop_records"] for c in checks),
             "all_equity_marks_independently_rebuilt": sum(c["equity_marks_independently_rebuilt"] for c in checks),
             "all_charged_funding_events_rebuilt": sum(c["funding_events_rebuilt"] for c in checks),
             "source_pair_rows_verified": paired_count, "source_specific_daily_progress_independently_rebuilt": True,
             "preceding_hour_stop_nontrigger_verified": True, "ambiguous_exit_hour_excluded_from_excursion": True,
             "funding_window_verified": False, "classification": manifest["classification"], "ledgers": checks}
    output.write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: audit[k] for k in ["status", "ledgers_verified", "all_full_window_trades_verified", "all_ledger_trades_verified", "all_stop_records_verified", "all_equity_marks_independently_rebuilt", "source_pair_rows_verified"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
