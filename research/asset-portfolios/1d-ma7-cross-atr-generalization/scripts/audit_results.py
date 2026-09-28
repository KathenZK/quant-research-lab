"""Read-only, independent reconstruction of persisted cross-market accounts.

No strategy engine or simulator is imported. Entries are checked against their
finite candidate lifecycle; saved stops and every equity mark are reconstructed
from the accepted daily/hourly inputs and the persisted trade ledger.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
LAB = FAMILY.parents[2]
DAY, HOUR = pd.Timedelta(days=1), pd.Timedelta(hours=1)
TIME_FIELDS = ("timestamp", "entry_time", "exit_time", "exit_interval_end",
               "signal_day", "cross_day", "extreme_day", "arm_day", "tp_signal_day")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def equal(actual, expected, label):
    """Relative arithmetic tolerance; no one-dollar floor on token prices."""
    if expected is None:
        assert actual is None or pd.isna(actual), f"{label}: expected missing, got {actual}"
    elif isinstance(expected, (bool, np.bool_)):
        assert bool(actual) == bool(expected), f"{label}: {actual} != {expected}"
    elif isinstance(expected, (int, float, np.integer, np.floating)):
        target = float(expected)
        if math.isnan(target):
            assert actual is None or pd.isna(actual), f"{label}: expected missing, got {actual}"
        else:
            value = float(actual)
            # Exact scalar equivalent of the former np.isclose(rtol=2e-10,
            # atol=1e-14). Avoid millions of scalar NumPy array allocations.
            assert math.isfinite(target) and math.isfinite(value) and abs(value - target) <= 1e-14 + 2e-10 * abs(target), (
                f"{label}: {actual} != {expected}")
    elif isinstance(expected, pd.Timestamp):
        assert pd.Timestamp(actual) == expected, f"{label}: {actual} != {expected}"
    elif pd.isna(expected):
        assert actual is None or pd.isna(actual), f"{label}: expected missing, got {actual}"
    else:
        assert actual == expected, f"{label}: {actual} != {expected}"


def read_frame(path):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    if path.suffix == ".parquet":
        frame = pd.read_parquet(path)
    else:
        try:
            frame = pd.read_csv(path, float_precision="round_trip")
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
    for column in TIME_FIELDS:
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], utc=True, format="mixed").dt.as_unit("ns")
    return frame


def verify_hash_map(directory, name="checksums.json"):
    hashes = read_json(directory / name)
    for relative, expected in hashes.items():
        assert sha(directory / relative) == expected, f"Changed artifact: {relative}"
    return len(hashes)


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def audit_input_provenance(inputs):
    """Accept the pinned implementation, requiring its full verification chain.

    This verifies receipts/content rather than requiring one historical wrapper
    function name. The batch implementation must retain the original validators
    and establish fresh bundle/catalog approvals within this preparation run.
    """
    started = read_json(inputs / "started.json")
    plan = read_json(inputs / "frozen_plan.json")
    assert not started["candidate_results_computed"]
    assert sha(LAB / started["plan_path"]) == started["plan_sha256"]
    assert plan == read_json(LAB / started["plan_path"]), "Frozen plan differs from declared source plan"
    implementations = [p for p in Path(__file__).parent.glob("prepare_inputs*.py")
                       if sha(p) == started["script_sha256"]]
    assert len(implementations) == 1, "Preparation implementation missing/changed"
    pin_file = inputs / "source_pins.json"
    source_pins = read_json(pin_file) if pin_file.exists() else plan["source_pins"]
    for path, digest in source_pins.items():
        assert sha(LAB / path) == digest, "Preparation source changed: " + path
    assert all(source_pins[k] == v for k, v in plan["source_pins"].items())
    assert sha(LAB / plan["contract_path"]) == plan["contract_sha256"]
    supplement = plan.get("input_loading_supplement_path")
    if supplement:
        assert sha(LAB / supplement) == plan["input_loading_supplement_sha256"]
    bundle_pin = plan["bundle_pin"]
    assert sha(LAB / bundle_pin["bundle_path"]) == bundle_pin["bundle_sha256"]
    bundle = read_json(LAB / bundle_pin["bundle_path"])
    expected_components = {role: {"manifest_sha256": c["manifest_sha256"],
                                  "parquet_inventory_fingerprint": c["parquet_inventory_fingerprint"]}
                           for role, c in bundle["components"].items()}
    context_files = [p for p in inputs.glob("startup_context_*.json") if not p.stem.endswith("_initial")]
    tokens, contexts = {}, []
    for file in context_files:
        context = read_json(file)
        assert context["verified_components"] == expected_components
        assert context["symbols"] == plan["symbols"] and context["bundle_content_verifications"] == 1
        assert context["funding_window_verified"] is False and context["pit_universe_proven"] is False
        assert set(context["catalog_receipts"]) == {"1d", "1h"}
        for timeframe, receipt in context["catalog_receipts"].items():
            token_payload = {k: v for k, v in receipt.items() if k != "scope_token_sha256"}
            assert canonical_sha(token_payload) == receipt["scope_token_sha256"]
            assert receipt["start"] == context["start"] and receipt["end"] == context["end"]
            assert receipt["fingerprint_mode"] == "STRICT_CONTENT"
            assert receipt["gap_policy"] == "contiguous_segments" and not receipt["materialized"]
            assert receipt["dataset_id"] == bundle["components"][timeframe]["dataset_id"]
            assert receipt["manifest_sha256"] == expected_components[timeframe]["manifest_sha256"]
            assert receipt["parquet_inventory_fingerprint"] == expected_components[timeframe]["parquet_inventory_fingerprint"]
            assert receipt["audit"]["row_quality"] == "PASS" and receipt["verified_parquet_files"]
            tokens[(context["start"], context["end"], timeframe)] = receipt["scope_token_sha256"]
        contexts.append(str(file.relative_to(inputs)))
    reports, seen, successful, failed = {}, set(), set(), set()
    for path in sorted((inputs / "startup_reports").glob("*.json")):
        report = read_json(path)
        request = report["request"]
        assert report["verified_components"] == expected_components
        assert report["request_canonical_sha256"] == canonical_sha(request)
        assert all(request[k] == v for k, v in bundle_pin.items())
        assert request["mode"] == "price_diagnostic" and request["asset_policy"] == "crypto_only"
        assert request["gap_policy"] == "contiguous_segments" and request["forward_bars"] == 0
        assert request["backward_bars"] == (29 if request["timeframe"] == "1d" else 1)
        assert report["funding_window_verified"] is False and report["pit_universe_proven"] is False
        if contexts:
            assert report["scope_token_sha256"] == tokens[(request["start"], request["end"], request["timeframe"])]
            assert report["original_api_modified"] is False
            assert set(report["symbol_status"]) == set(request["symbols"])
        for symbol in request["symbols"]:
            key = (request["start"], request["end"], request["timeframe"], symbol)
            assert key not in seen, "Symbol/timeframe evaluated twice in final input set"
            seen.add(key)
            if symbol in report.get("failures", {}):
                error = report["failures"][symbol]
                assert error == f"{symbol}: no complete eligible feature/label window"
                assert report["symbol_status"][symbol]["data_returned"] is False
                assert symbol not in report["symbols"]
                failed.add(key)
            else:
                assert report["symbols"][symbol]["complete_windows"] > 0
                successful.add(key)
        reports[str(path.relative_to(inputs))] = report
    expected = {(window["input_start"], window["end"], tf, symbol)
                for window in plan["windows"] for tf in ("1d", "1h") for symbol in plan["symbols"]}
    assert seen == expected and successful.isdisjoint(failed)
    frames = read_json(inputs / "frames_manifest.json")
    returned = set()
    for identity, entries in frames.items():
        symbol = identity.split("/", 1)[1]
        for tf in ("1d", "1h"):
            if tf not in entries:
                continue
            item = entries[tf]
            assert sha(inputs / item["request_path"]) == item["request_sha256"]
            assert sha(inputs / item["startup_report_path"]) == item["startup_report_sha256"]
            request = read_json(inputs / item["request_path"])
            report = reports[item["startup_report_path"]]
            assert report["request"] == request and request["timeframe"] == tf
            key = (request["start"], request["end"], tf, symbol)
            assert key in successful and key not in returned
            returned.add(key)
            assert item["rows"] == report["symbols"][symbol]["rows"]
            assert sha(inputs / item["path"]) == item["sha256"]
    assert returned == successful, "Missing successful frame or a failed frame was returned"
    return {"implementation_path": str(implementations[0].relative_to(LAB)),
            "implementation_sha256": started["script_sha256"], "same_run_context_receipts": contexts,
            "symbol_timeframe_requests": len(seen), "accepted_symbol_timeframes": len(successful),
            "unavailable_symbol_timeframes": len(failed), "source_pins_checked": len(source_pins),
            "input_loading_supplement_path": supplement, "status": "PASS"}


def reconstruct_features(daily):
    """Independent explicit Wilder recursion, retaining the joint segment mask."""
    d = daily.copy().reset_index(drop=True)
    if "ts" in d and "timestamp" not in d:
        d = d.rename(columns={"ts": "timestamp"})
    d.timestamp = pd.to_datetime(d.timestamp, utc=True).dt.as_unit("ns")
    assert d.timestamp.diff().dropna().eq(DAY).all()
    assert not d.timestamp.duplicated().any()
    values = d[["open", "high", "low", "close"]].to_numpy(float)
    assert np.isfinite(values).all() and (values > 0).all()
    assert (d.high >= d[["open", "close", "low"]].max(axis=1)).all()
    assert (d.low <= d[["open", "close", "high"]].min(axis=1)).all()
    previous = d.close.shift()
    delta = d.close - previous
    true_range = pd.concat([d.high - d.low, (d.high - previous).abs(),
                            (d.low - previous).abs()], axis=1).max(axis=1)
    true_range.iloc[0] = np.nan

    def smooth(series, period):
        x = series.to_numpy(float)
        out = np.full(len(x), np.nan)
        good = []
        current = np.nan
        for i, value in enumerate(x):
            if not np.isfinite(value):
                good, current = [], np.nan
            elif not np.isfinite(current):
                good.append(value)
                if len(good) == period:
                    current = sum(good) / period
            else:
                current = ((period - 1) * current + value) / period
            out[i] = current
        return out

    d["ma"] = d.close.rolling(7).mean()
    d["atr"] = smooth(true_range, 14)
    gains, losses = smooth(delta.clip(lower=0), 6), smooth((-delta).clip(lower=0), 6)
    with np.errstate(divide="ignore", invalid="ignore"):
        d["rsi"] = 100 - 100 / (1 + gains / losses)
    d.loc[(gains == 0) & (losses == 0), "rsi"] = 50
    d.loc[(gains > 0) & (losses == 0), "rsi"] = 100
    d["slope"] = d.ma.diff() / d.atr
    d["cross"] = np.where((previous <= d.ma.shift()) & (d.close > d.ma), 1,
                          np.where((previous >= d.ma.shift()) & (d.close < d.ma), -1, 0))
    fall = -delta
    d["accel1"] = (fall >= d.atr.shift()) & (fall > fall.shift().clip(lower=0))
    d["ready"] = (np.arange(len(d)) >= 28) & d[["ma", "atr", "rsi", "slope"]].notna().all(axis=1)
    if "research_window_valid" in d:
        d["ready"] &= d.research_window_valid.astype(bool)
    return d.set_index("timestamp", drop=False)


def audit_entry_lifecycle(trades, daily, hourly, summary):
    """Check expected fill attempts from the book's carried/flat state, not PnL."""
    start, end = pd.Timestamp(summary["start"]), pd.Timestamp(summary["end_exclusive"])
    assert summary["delay_hours"] == 0 and not summary["reverse"]
    rows = list(trades.itertuples(index=False))
    entered = {t.entry_time: t for t in rows}
    assert len(entered) == len(rows), "Two entries at one timestamp"
    pending, candidates, confirmations, checked, rejected = None, 0, 0, 0, 0
    for timestamp in pd.date_range(start, end - DAY, freq="D"):
        signal = daily.loc[timestamp - DAY]
        # A carried trade consumes the day's signal, even if a stop or RSI exit
        # takes place at this exact hour. Intrahour exits are not deemed earlier.
        carried = [t for t in rows if t.entry_time < timestamp <= t.exit_time]
        if carried:
            pending = None
            assert timestamp not in entered, "Exit-hour entry/reversal"
            continue
        if not bool(signal.ready):
            pending = None
            assert timestamp not in entered, "Entry from ineligible closed day"
            continue
        side = int(signal.cross)
        intent = None
        if side:
            pending = None
            if side * signal.slope > summary["slope"]:
                intent = (side, signal.timestamp, "daily_cross", 0)
            elif summary["entry_wait_days"] and side * (signal.close - signal.ma) > 0:
                pending = (side, signal.timestamp, float(signal.close))
                candidates += 1
        elif pending is not None:
            direction, cross_day, cross_close = pending
            age = int((signal.timestamp - cross_day) / DAY)
            if age > summary["entry_wait_days"] or direction * (signal.close - signal.ma) <= 0:
                pending = None
            elif (age > 0 and direction * signal.slope > summary["slope"]
                  and direction * (signal.close - cross_close) > 0):
                intent = (direction, cross_day, "delayed_cross", age)
                pending = None
                confirmations += 1
        if intent is None:
            assert timestamp not in entered, "Entry without an active qualifying cross"
            continue
        direction, cross_day, reason, age = intent
        stop = signal.ma - direction * 1.5 * signal.atr
        closed = [t for t in rows if t.exit_time < timestamp]
        cash = closed[-1].end_equity if closed else 10000.0
        valid = direction * (hourly.loc[timestamp, "open"] - stop) > 0 and cash > 0
        if not valid:
            assert timestamp not in entered, "Invalid initial stop or nonpositive capital entered"
            rejected += 1
            continue
        assert timestamp in entered, f"Missing qualifying entry at {timestamp}"
        trade = entered[timestamp]
        for field, expected in {"side": direction, "cross_day": cross_day,
                                "signal_day": signal.timestamp, "entry_reason": reason,
                                "entry_wait_days_used": age}.items():
            equal(getattr(trade, field), expected, "entry " + field)
        checked += 1
    assert checked == len(trades), "Entry outside an allowed daily execution boundary"
    return {"entries_verified": checked, "pending_candidates": candidates,
            "delayed_confirmations": confirmations, "rejected_fill_attempts": rejected}


def audit_stop_path(trade, records, daily, summary):
    side = int(trade.side)
    signal = daily.loc[trade.signal_day]
    initial = float(signal.ma - side * 1.5 * signal.atr)
    equal(trade.initial_stop, initial, "initial stop from confirmation day")
    equal(trade.uncapped_initial_stop, initial, "uncapped initial stop")
    equal(trade.entry_atr, signal.atr, "entry ATR")
    assert not trade.cap_applied and trade.progress_source == "high_low"
    end = pd.Timestamp(summary["end_exclusive"])
    dates = pd.date_range(trade.entry_time.floor("D") + DAY, trade.exit_time.floor("D"), freq="D")
    dates = dates[dates < end]
    assert records.timestamp.tolist() == [trade.entry_time, *dates], "Missing/extra daily stop update"
    first = records.iloc[0]
    equal(first.new_stop, initial, "initial executable stop")
    equal(first.old_stop, initial, "initial prior stop")
    equal(first.new_mult, 1.5, "initial multiple")
    assert not first.tightened and not first.initialized
    old_stop, mult, armed, initialized = initial, 1.5, False, False
    extreme, extreme_day, arm_day, count, reductions = None, None, None, 0, 0
    for row in records.iloc[1:].itertuples(index=False):
        assert row.timestamp == row.signal_day + DAY, "Unclosed bar controls stop"
        day = daily.loc[row.signal_day]
        equal(row.old_stop, old_stop, "prior stop")
        equal(row.old_mult, mult, "prior stop multiple")
        equal(row.old_armed, armed, "prior arming state")
        equal(row.natural_candidate, day.ma - side * mult * day.atr, "natural MA stop")
        full_day = row.signal_day >= trade.entry_time
        new_extreme, tightened = False, False
        if summary["progress_days"] and full_day:
            observed = float(day.high if side == 1 else day.low)
            if not initialized:
                initialized, extreme, extreme_day = True, observed, row.signal_day
                new_extreme = True
            else:
                new_extreme = side * (observed - extreme) > 0
                if new_extreme:
                    extreme, extreme_day, count = observed, row.signal_day, 0
                else:
                    count += 1
                if not armed and count >= 4:
                    armed, arm_day = True, row.signal_day
                tightened = armed and mult > 0.5
        if tightened:
            mult = max(0.5, round(mult - 0.2, 10))
            reductions += 1
        candidate = float(day.ma - side * mult * day.atr)
        stop = max(old_stop, candidate) if side == 1 else min(old_stop, candidate)
        for field, expected in {"new_stop": stop, "new_mult": mult, "new_armed": armed,
                                "initialized": initialized, "extreme_price": extreme,
                                "extreme_day": extreme_day, "arm_day": arm_day,
                                "new_extreme": new_extreme, "no_new_extreme_days": count,
                                "tightened": tightened, "full_holding_day": full_day}.items():
            equal(getattr(row, field), expected, "stop " + field)
        assert side * (stop - old_stop) >= 0 and 0.5 <= mult <= 1.5
        old_stop = stop
    for field, expected in {"stop": old_stop, "stop_mult": mult, "armed": armed,
                            "initialized": initialized, "extreme_price": extreme,
                            "extreme_day": extreme_day, "arm_day": arm_day,
                            "no_new_extreme_days": count, "tightening_days": reductions,
                            "stop_floor_reached": mult == 0.5}.items():
        equal(getattr(trade, field), expected, "final stop " + field)


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
    result = audit_entry_lifecycle(trades, daily, h, summary)
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
        equal(trade.qty, cash / (trade.entry_price * (1 + fee)), "quantity")
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
        equal(trade.return_on_entry_equity, net / cash, "trade account return")
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
                assert trade.exit_reason == "accel1_rsi30" and side == -1
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
            if side == -1 and day.rsi <= 30 and day.accel1 and profit > 0:
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
        }.items():
            equal(summary[field], expected, "summary " + field)
        for side, prefix in ((1, "long"), (-1, "short")):
            group = trades.loc[trades.side == side]
            equal(summary[prefix + "_trades"], len(group), prefix + " count")
            equal(summary[prefix + "_pnl"], float(group.net_pnl.sum()), prefix + " PnL")
    return {**result, "trades": len(trades), "stop_records": len(stops),
            "equity_marks_independently_rebuilt": verified_marks, "status": "PASS"}


def audit_buy_hold(directory, hourly, bounds):
    saved = read_json(directory / "summary.json")
    curve = read_frame(directory / "equity.parquet")
    lo, hi = map(pd.Timestamp, bounds)
    h = hourly.loc[(hourly.index >= lo) & (hourly.index < hi)]
    fee, slip = saved["fee"], saved["slip"]
    equal(fee, 0.0005, "buy hold fee")
    equal(slip, 0.0003, "buy hold slip")
    fill = float(h.iloc[0].open) * (1 + slip)
    quantity = 10000 / (fill * (1 + fee))
    entry_fee = quantity * fill * fee
    prices = np.column_stack([h.open.to_numpy(), h.close.to_numpy()]).ravel()
    marked = 10000 - entry_fee + quantity * (prices - fill)
    exit_fill = h.iloc[-1].close * (1 - slip)
    exit_fee = quantity * exit_fill * fee
    settled = 10000 - entry_fee + quantity * (exit_fill - fill) - exit_fee
    expected = np.r_[10000.0, marked, settled]
    assert len(curve) == len(expected) and np.allclose(curve.equity, expected, rtol=2e-10, atol=1e-9)
    equal(saved["ending_equity"], settled, "buy hold settled account")
    equal(saved["return_pct"], (settled / 10000 - 1) * 100, "buy hold return")
    equal(saved["max_drawdown_pct"], np.min(expected / np.maximum.accumulate(expected) - 1) * 100,
          "buy hold drawdown")
    equal(saved["fee_total"], entry_fee + exit_fee, "buy hold total fees")
    equal(pd.Timestamp(saved["start"]), lo, "buy hold start")
    equal(pd.Timestamp(saved["end_exclusive"]), hi, "buy hold end")
    return len(curve)


def audit_scope(inputs, results, manifest):
    plan = read_json(inputs / "frozen_plan.json")
    universe = read_frame(inputs / "universe.csv")
    original_scope = read_frame(inputs / "scope.csv")
    segments = read_frame(inputs / "segments.csv")
    selected = read_frame(results / "scope.csv")
    assert len(universe) == 874 and universe.symbol.nunique() == 874
    included = set(universe.loc[universe.included, "symbol"])
    assert included == set(plan["symbols"]) and len(included) == 652
    assert set(original_scope.symbol) == included and len(original_scope) == 652
    assert set(selected.symbol) == included and len(selected) == 652
    assert selected.slug.nunique() == 652
    for row in selected.itertuples(index=False):
        options = segments.loc[(segments.symbol == row.symbol) & (segments.trade_days > 0)]
        options = options.sort_values(["trade_days", "input_start"], ascending=[False, True])
        if options.empty:
            assert row.cohort == "excluded" and row.trade_days == 0
            assert row.status == "NO_USABLE_TRADING_WINDOW"
            continue
        best = options.iloc[0]
        expected_cohort = ("main_full" if best.full_window_contiguous and best.trade_days == 433
                           else "partial" if best.trade_days >= 180 else "short")
        assert row.cohort == expected_cohort, "Wrong complete/partial denominator"
        assert row.selected_segment_id == best.segment_id, "Selected segment is not longest/earliest"
        equal(row.trade_days, best.trade_days, "selected trading days")
        for actual, expected in [(row.input_start, best.input_start),
                                  (row.trade_start, best.first_trade_open), (row.end, best.end)]:
            equal(pd.Timestamp(actual), pd.Timestamp(expected), "selected segment boundary")
        assert row.status == "REPLAY_COMPLETED", "Incomplete execution cannot pass all-market audit"
    counts = {str(k): int(v) for k, v in selected.cohort.value_counts().items()}
    assert counts == manifest["cohort_counts"]
    return selected, counts


def compare_summary_row(table, selectors, saved):
    chosen = table
    for key, value in selectors.items():
        chosen = chosen.loc[chosen[key] == value]
    assert len(chosen) == 1, f"Missing/duplicate summary row: {selectors}"
    actual = chosen.iloc[0]
    for key, expected in saved.items():
        assert key in actual.index, f"Summary omitted field {key}"
        equal(actual[key], expected, "summary table " + key)


def audit_saved_hype_controls(results):
    old_base = LAB / "research/hype/1d-ma7-cross-atr-ratchet/artifacts"
    references = {"H4_D0": ("r4_close_progress_20260909", "H4_ma"),
                  "F0": ("r3_price_progress_20260909", "B1_r1_fixed")}
    checked = []
    for case, (folder, old_case) in references.items():
        parent = old_base / folder
        hashes = read_json(parent / "artifact_checksums.json")
        for window in ("full", "early60", "late40"):
            old = parent / "runs" / old_case / window
            new = results / "runs/HYPE" / case / window
            for filename in ("summary.json", "trades.csv", "stops.csv", "equity.parquet"):
                relative = str((old / filename).relative_to(parent))
                assert sha(old / filename) == hashes[relative], "Frozen HYPE output changed"
            original, current = read_json(old / "summary.json"), read_json(new / "summary.json")
            for key, expected in original.items():
                if key != "name":
                    equal(current[key], expected, "saved HYPE control " + key)
            for filename in ("trades.csv", "stops.csv", "equity.parquet"):
                a, b = read_frame(old / filename), read_frame(new / filename)
                pd.testing.assert_frame_equal(a, b[a.columns], check_exact=True)
            checked.append({"case_id": case, "window": window,
                            "original_directory": str(old.relative_to(LAB)),
                            "original_checksum_manifest_sha256": sha(parent / "artifact_checksums.json"),
                            "all_original_trade_stop_equity_columns_exact_equal": True})
    return checked


def load_market_inputs(inputs, results, row, frames):
    """Compare persisted market files to exact accepted source segment."""
    source = frames["main/" + row.symbol]
    raw = pd.read_parquet(inputs / source["joint_daily"]["path"])
    raw = raw.loc[raw.joint_segment_id == row.selected_segment_id].copy()
    raw = raw.sort_values("ts").rename(columns={"ts": "timestamp"})
    assert raw.joint_eligible.all() and raw.eligible.all() and raw.is_closed.all()
    reconstructed = reconstruct_features(raw)
    market = results / "market" / row.slug
    meta = read_json(market / "metadata.json")
    assert meta["input_source"] == source
    assert meta["selected_segment_id"] == row.selected_segment_id
    assert sha(market / "daily_features.csv") == meta["daily_features_sha256"]
    assert sha(market / "hourly.parquet") == meta["hourly_sha256"]
    saved = read_frame(market / "daily_features.csv").set_index("timestamp", drop=False)
    assert saved.index.equals(reconstructed.index)
    for column in ("open", "high", "low", "close", "ma", "atr", "rsi", "slope"):
        assert np.allclose(saved[column], reconstructed[column], equal_nan=True, rtol=2e-10, atol=1e-14), column
    for column in ("cross", "ready", "accel1", "research_window_valid"):
        assert saved[column].tolist() == reconstructed[column].tolist(), column
    raw_h = pd.read_parquet(inputs / source["1h"]["path"])
    lo, hi = pd.Timestamp(row.input_start), pd.Timestamp(row.end)
    raw_h = raw_h.loc[(raw_h.ts >= lo) & (raw_h.ts < hi)].sort_values("ts").rename(columns={"ts": "timestamp"})
    raw_h.timestamp = pd.to_datetime(raw_h.timestamp, utc=True).dt.as_unit("ns")
    hourly = read_frame(market / "hourly.parquet")
    for column in raw_h.columns:
        pd.testing.assert_series_equal(raw_h[column].reset_index(drop=True), hourly[column].reset_index(drop=True),
                                       check_exact=True, check_names=False, check_dtype=False)
    hourly = hourly.set_index("timestamp", drop=False)
    assert hourly.eligible.all() and hourly.is_closed.all()
    assert hourly.index.equals(pd.date_range(lo, hi - HOUR, freq="h").as_unit("ns"))
    aggregate = hourly.groupby(hourly.timestamp.dt.floor("D")).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
        hours=("open", "size"))
    assert aggregate.hours.eq(24).all() and aggregate.index.equals(saved.index)
    assert np.allclose(aggregate[["open", "high", "low", "close"]],
                       saved[["open", "high", "low", "close"]], rtol=2e-10, atol=1e-14)
    start, end = pd.Timestamp(row.trade_start), pd.Timestamp(row.end)
    windows = {"full": [str(start), str(end)]}
    if row.trade_days >= 180:
        split = (pd.Timestamp("2026-03-15T00:00:00Z") if row.cohort == "main_full"
                 else start + int(row.trade_days * 0.6) * DAY)
        windows.update(early60=[str(start), str(split)], late40=[str(split), str(end)])
    assert set(meta["windows"]) == set(windows)
    for name, bounds in windows.items():
        assert list(map(pd.Timestamp, meta["windows"][name])) == list(map(pd.Timestamp, bounds))
    # Account arithmetic uses the persisted double precision feature values after
    # the separate independent indicator check, avoiding insignificant seed-sum
    # differences becoming artificial strict-threshold disagreements.
    return saved, hourly, windows


def audit_coin(item, inputs, results, cases, source, summary, stress, bh):
    """One isolated worker reads only one coin and verifies every saved account."""
    row = SimpleNamespace(**item)
    daily, hourly, windows = load_market_inputs(inputs, results, row, {"main/" + row.symbol: source})
    coin = {"symbol": row.symbol, "cohort": row.cohort, "runs": 0, "trades": 0,
            "stop_records": 0, "equity_marks": 0, "candidates_by_case": {},
            "main_rows": 0, "stress_rows": 0, "buy_hold_accounts": 0, "buy_hold_marks": 0}
    verified_dirs = []
    for case, config in cases.items():
        scenarios = [("runs", window, bounds, 0.0) for window, bounds in windows.items()]
        scenarios += [("sensitivity", scenario, windows["full"], carry)
                      for scenario, carry in (("slippage_10bp", 0.0), ("carry_5bp_day", 0.0005))]
        for group, name, bounds, carry in scenarios:
            directory = results / group / row.slug / case / name
            verified_dirs.append(str(directory.relative_to(results)))
            saved_summary = read_json(directory / "summary.json")
            for key, value in config.items():
                expected = 0.001 if group == "sensitivity" and name == "slippage_10bp" and key == "slip" else value
                equal(saved_summary[key], expected, "fixed case parameter " + key)
            assert [pd.Timestamp(saved_summary["start"]), pd.Timestamp(saved_summary["end_exclusive"])] == list(map(pd.Timestamp, bounds))
            result = audit_run(directory, daily, hourly, carry)
            selectors = {"symbol": row.symbol, "case_id": case, "cohort": row.cohort,
                         "window" if group == "runs" else "scenario": name}
            compare_summary_row(summary if group == "runs" else stress, selectors, saved_summary)
            coin["runs"] += 1
            coin["trades"] += result["trades"]
            coin["stop_records"] += result["stop_records"]
            coin["equity_marks"] += result["equity_marks_independently_rebuilt"]
            if group == "runs":
                coin["main_rows"] += 1
                if name == "full":
                    coin["candidates_by_case"][case] = {k: result[k] for k in (
                        "pending_candidates", "delayed_confirmations", "rejected_fill_attempts", "entries_verified")}
            else:
                coin["stress_rows"] += 1
    # Buy-and-hold is shared by four comparisons and is verified only once.
    for window, bounds in windows.items():
        directory = results / "buy_hold" / row.slug / window
        verified_dirs.append(str(directory.relative_to(results)))
        coin["buy_hold_marks"] += audit_buy_hold(directory, hourly, bounds)
        coin["buy_hold_accounts"] += 1
        compare_summary_row(bh, {"symbol": row.symbol, "window": window, "cohort": row.cohort},
                            read_json(directory / "summary.json"))
    return coin, verified_dirs


def audit_all(inputs, results, workers=4):
    assert isinstance(workers, int) and 1 <= workers <= 4, "Audit supports one to four workers"
    manifest = read_json(results / "run_manifest.json")
    assert sha(inputs / "checksums.json") == manifest["input_checksums_sha256"]
    assert sha(inputs / "frozen_plan.json") == manifest["input_plan_sha256"]
    input_files = verify_hash_map(inputs)
    input_provenance = audit_input_provenance(inputs)
    result_files = verify_hash_map(results, "artifact_checksums.json")
    for name in ("engine", "contract"):
        assert sha(LAB / manifest[name + "_path"]) == manifest[name + "_sha256"]
    assert sha(Path(__file__).with_name("run_market.py")) == manifest["run_script_sha256"]
    assert sha(Path(__file__).with_name("common.py")) == manifest["common_sha256"]
    assert manifest["primary_case"] == "H4_D0" and manifest["primary_entry_extension"] == "H4_D3"
    assert not manifest["funding_window_verified"]
    cases = {item["case_id"]: item["config"] for item in manifest["cases"]}
    assert set(cases) == {"F0", "H4_D0", "H4_D2", "H4_D3"}
    for case, config in cases.items():
        assert config["entry_wait_days"] == {"F0": 0, "H4_D0": 0, "H4_D2": 2, "H4_D3": 3}[case]
        assert config["progress_days"] == (0 if case == "F0" else 4)
        assert config["progress_source"] == "high_low" and config["stop_anchor"] == "ma"
        assert not config["reverse"] and not config["exit_opposite_cross"]
        assert config["initial_stop_cap_pct"] is None and config["tighten_mode"] == "fixed"
    scope, counts = audit_scope(inputs, results, manifest)
    frames = read_json(inputs / "frames_manifest.json")
    summary, stress, bh = (read_frame(results / name) for name in ("summary.csv", "stress.csv", "buy_hold.csv"))
    controls = read_json(results / "hype_original_controls.json")
    assert len(controls) == 6 and all(x["all_old_columns_exact_equal"] for x in controls)
    saved_controls = audit_saved_hype_controls(results)
    assert read_json(results / "execution_failures.json") == []
    verified_dirs, per_coin = set(), []
    candidates = scope.loc[scope.cohort != "excluded"].to_dict("records")
    # The parent checks global hashes/universe once. Worker arguments include only
    # the current coin's receipts and compact summary rows, never all price frames.
    jobs = []
    for item in candidates:
        symbol = item["symbol"]
        jobs.append((item, inputs, results, cases, frames["main/" + symbol],
                     summary.loc[summary.symbol == symbol], stress.loc[stress.symbol == symbol],
                     bh.loc[bh.symbol == symbol]))

    def collect(value):
        coin, directories = value
        per_coin.append(coin)
        verified_dirs.update(results / relative for relative in directories)
        if len(per_coin) % 20 == 0:
            print(f"AUDITED {len(per_coin)} coins; "
                  f"{sum(c['runs'] for c in per_coin)} strategy accounts; "
                  f"{sum(c['trades'] for c in per_coin)} trades", flush=True)

    if workers == 1:
        for arguments in jobs:
            collect(audit_coin(*arguments))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(audit_coin, *arguments): arguments[0]["symbol"] for arguments in jobs}
            for future in as_completed(futures):
                try:
                    collect(future.result())
                except Exception as exc:
                    for pending_future in futures:
                        pending_future.cancel()
                    raise AssertionError(f"Independent audit failed for {futures[future]}: {exc}") from exc
    per_coin.sort(key=lambda item: item["symbol"])
    all_runs = sum(c["runs"] for c in per_coin)
    all_stops = sum(c["stop_records"] for c in per_coin)
    all_trades = sum(c["trades"] for c in per_coin)
    all_marks = sum(c["equity_marks"] for c in per_coin)
    all_bh = sum(c["buy_hold_accounts"] for c in per_coin)
    bh_marks = sum(c["buy_hold_marks"] for c in per_coin)
    main_rows = sum(c["main_rows"] for c in per_coin)
    stress_rows = sum(c["stress_rows"] for c in per_coin)
    expected_dirs = {p.parent for p in results.glob("runs/*/*/*/summary.json")}
    expected_dirs |= {p.parent for p in results.glob("sensitivity/*/*/*/summary.json")}
    expected_dirs |= {p.parent for p in results.glob("buy_hold/*/*/summary.json")}
    assert expected_dirs == verified_dirs
    assert len(summary) == main_rows and len(stress) == stress_rows and len(bh) == all_bh
    done = read_json(results / "completion.json")
    assert done["complete"] and done["coins_failed"] == 0
    equal(done["coins_completed"], len(per_coin), "complete coin denominator")
    equal(done["strategy_window_runs"], main_rows, "window run count")
    equal(done["stress_runs"], stress_rows, "stress count")
    equal(done["buyhold_runs"], all_bh, "buy hold count")
    return {"status": "PASS", "audit_script_sha256": sha(Path(__file__)),
            "input_manifest_sha256": sha(inputs / "checksums.json"),
            "result_manifest_sha256": sha(results / "artifact_checksums.json"),
            "hashed_input_files": input_files, "hashed_result_files": result_files,
            "input_provenance": input_provenance,
            "observed_contracts": 874, "included_coins": 652, "cohort_counts": counts,
            "coins_independently_audited": len(per_coin), "strategy_accounts_audited": all_runs,
            "trades_audited": all_trades, "stop_records_audited": all_stops,
            "equity_marks_independently_rebuilt": all_marks, "buy_hold_accounts_audited": all_bh,
            "buy_hold_marks_independently_rebuilt": bh_marks, "per_coin": per_coin,
            "frozen_saved_hype_controls": saved_controls,
            "simulator_called": False, "workers": workers, "funding_window_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=FAMILY / "artifacts/inputs_20260909")
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Audit output already exists; use a fresh file")
    audit = audit_all(args.inputs.resolve(), args.results.resolve(), args.workers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(audit, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({k: v for k, v in audit.items() if k != "per_coin"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
