"""Read-only, independent verification of every saved R3 ledger.

This script never calls or imports a strategy simulator. It checks recorded
decisions against frozen daily/hourly inputs and verifies account arithmetic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


BASE = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = BASE / "artifacts/r3_price_progress_20260909"
DEFAULT_AUDIT = BASE / "artifacts/r3_audit_20260909.json"
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
            frame[name] = pd.to_datetime(frame[name], utc=True)
    return frame


def audit_stop_path(trade, records, daily, config, window_end):
    """Recalculate only each logged stop decision, never select any trades."""
    label = f"trade {trade.trade_id}"
    side = int(trade.side)
    entry = records.iloc[0]
    equal(entry.timestamp, trade.entry_time, label + " initial stop time")
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
                observation = float(day.high if side == 1 else day.low)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()
    results, output = args.results.resolve(), args.audit_output.resolve()
    if output.exists():
        parser.error("Preserve the prior audit; use a new --audit-output path")
    manifest = read_json(results / "run_manifest.json")
    for key, path in {"engine_sha256": BASE / "scripts/engine_r3.py",
                      "run_script_sha256": BASE / "scripts/run_r3.py",
                      "contract_sha256": BASE / "specs/r3-price-progress-20260909.md",
                      "input_checksums_sha256": INPUT / "checksums.json",
                      "r2_checksum_manifest_sha256": BASE / "artifacts/r2_slowdown_tightening_20260909/artifact_checksums.json"}.items():
        assert sha(path) == manifest[key], "Frozen source changed: " + key
    hashed_results = verify_hash_map(results, exact=True)
    hashed_inputs = verify_hash_map(INPUT, "checksums.json")
    verify_hash_map(BASE / "artifacts/r2_slowdown_tightening_20260909")
    assert manifest["primary_case"] == "P2_extreme" and not manifest["funding_window_verified"]
    cases = {row["case_id"]: row["config"] for row in manifest["cases"]}
    assert len(cases) == 14
    daily = parse_times(pd.read_csv(results / "daily_features.csv"), ["timestamp"]).set_index("timestamp")
    original_daily = pd.read_parquet(INPUT / "daily.parquet").set_index("ts")
    pd.testing.assert_frame_equal(daily[["open", "high", "low", "close"]], original_daily[["open", "high", "low", "close"]], check_names=False, check_exact=False, atol=1e-12, rtol=0)
    hourly = pd.read_parquet(INPUT / "hourly.parquet").set_index("ts")
    baselines = read_json(results / "baseline_reproduction.json")
    assert len(baselines) == 6
    assert all(x["live_r2_r3_exact_equal"] and x["frozen_csv_max_absolute_difference"] <= 1e-8 for x in baselines)
    grid, stress = pd.read_csv(results / "all_results.csv"), pd.read_csv(results / "sensitivity.csv")
    assert len(grid) == 42 and len(stress) == 24
    expected_dirs, checks, full_trades = set(), [], {}
    for case_id, config in cases.items():
        for window in manifest["windows"]:
            directory = results / "runs" / case_id / window
            expected_dirs.add(directory)
            check, trades = audit_ledger(directory, config, daily, hourly)
            checks.append(check)
            saved = read_json(directory / "summary.json")
            row = grid[(grid.case_id == case_id) & (grid.window == window)]
            assert len(row) == 1
            for key in ["return_pct", "max_drawdown_pct", "fee_total", "trades", "ending_equity"]:
                equal(row.iloc[0][key], saved[key], "grid versus ledger " + key)
            if window == "full":
                full_trades[case_id] = trades
        if case_id in manifest["sensitivity_cases"]:
            for scenario in ["slippage_10bp", "daily_signal_delay_1h", "adverse_carry_5bp_day", "observed_funding_unverified"]:
                variant = dict(config)
                if scenario == "slippage_10bp":
                    variant["slip"] = .001
                if scenario == "daily_signal_delay_1h":
                    variant["delay_hours"] = 1
                directory = results / "sensitivity" / case_id / scenario
                expected_dirs.add(directory)
                check, _ = audit_ledger(directory, variant, daily, hourly)
                checks.append(check)
                row = stress[(stress.case_id == case_id) & (stress.scenario == scenario)]
                assert len(row) == 1
                saved = read_json(directory / "summary.json")
                for key in ["return_pct", "max_drawdown_pct", "fee_total", "trades", "ending_equity"]:
                    equal(row.iloc[0][key], saved[key], "stress versus ledger " + key)
    actual_dirs = {p.parent for p in results.rglob("summary.json")}
    assert actual_dirs == expected_dirs and len(checks) == 66, "Missing/unexpected ledgers"
    review_count = audit_global_review(results, hourly, full_trades)
    full = grid[grid.window == "full"]
    global_fields = ["case_id", "return_pct", "max_drawdown_pct", "trades", "fee_total", "exposure_pct", "progress_armed_trades", "opposite_cross_exits", "initial_cap_trades"]
    audit = {"status": "PASS", "method": "Read-only ledger/input checks; no strategy simulation called",
             "audit_script_sha256": sha(Path(__file__)), "result_manifest_sha256": sha(results / "run_manifest.json"),
             "result_checksum_manifest_sha256": sha(results / "artifact_checksums.json"),
             "source_hashes_verified": True, "result_files_hashed": hashed_results,
             "input_files_hashed": hashed_inputs, "baseline_controls": baselines,
             "ledgers_verified": len(checks), "main_result_rows": len(grid), "sensitivity_rows": len(stress),
             "all_full_window_trades_verified": review_count, "all_ledger_trades_verified": sum(c["trades"] for c in checks),
             "all_stop_records_verified": sum(c["stop_records"] for c in checks),
             "price_extrema_use_daily_high_low": True, "ambiguous_exit_hour_excluded_from_excursion": True,
             "funding_window_verified": False, "classification": manifest["classification"],
             "global_full_window_comparison": full[global_fields].to_dict("records"), "ledgers": checks}
    output.write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: audit[k] for k in ["status", "ledgers_verified", "all_full_window_trades_verified", "all_ledger_trades_verified", "all_stop_records_verified"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
