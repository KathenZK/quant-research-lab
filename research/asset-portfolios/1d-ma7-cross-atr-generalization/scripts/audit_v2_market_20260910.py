"""Independent V2 ledger audit; original V1/V3 accounts are hash-reused only.

The frozen original audit supplies account, input and entry checks. This module
adds an independent reconstruction of V2's daily profit-and-stall decision.
No strategy engine is imported and no simulator is called.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

import audit_results as prior

FAMILY, LAB, DAY, HOUR = prior.FAMILY, prior.LAB, prior.DAY, prior.HOUR
PRIOR_AUDIT_SHA = "f376e8560d724a039dc5612962ce719602dc2e21157683ed6f8c177e5a1d9dc1"
PRIOR_REPORT_SHA = "08e12de5e6bd68ac93a24fd94e6a0bc072ff20f450146c0a10f3631175c1c580"
ENGINE_SHA = "54f559748b557c81ec21ca53e4f30e09264547e5d0e8cb658716e33cf2f8d72b"
INPUTS = FAMILY / "artifacts/inputs_20260909"
ORIGINAL = FAMILY / "artifacts/results_20260909"
RESULTS = FAMILY / "artifacts/results_v2_20260910"
equal, sha, read_json, read_frame = prior.equal, prior.sha, prior.read_json, prior.read_frame


def audit_v2_stop_path(trade, records, daily, summary, hourly, carry_daily):
    """Rebuild decisions from prices and hourly carry, never trust saved flags."""
    assert summary["tighten_mode"] == "stall_only" and summary["progress_days"] == 0
    assert summary["profit_trigger_atr"] == 0 and summary["entry_wait_days"] == 0
    side, fee, slip = int(trade.side), summary["fee"], summary["slip"]
    signal = daily.loc[trade.signal_day]
    initial = float(signal.ma - side * 1.5 * signal.atr)
    for key, value in {"initial_stop": initial, "uncapped_initial_stop": initial,
                       "entry_atr": signal.atr, "initial_stop_mult": 1.5}.items():
        equal(getattr(trade, key), value, "V2 entry " + key)
    assert not trade.cap_applied and trade.progress_source == "high_low"
    end = pd.Timestamp(summary["end_exclusive"])
    dates = pd.date_range(trade.entry_time.floor("D") + DAY, trade.exit_time.floor("D"), freq="D")
    dates = dates[dates < end]
    assert records.timestamp.tolist() == [trade.entry_time, *dates], "V2 daily update dates"
    first = records.iloc[0]
    for key, value in {"new_stop": initial, "old_stop": initial, "new_mult": 1.5,
                       "old_mult": 1.5, "new_armed": False, "old_armed": False,
                       "natural_candidate": initial, "stalled": False,
                       "profit_eligible": False, "expected_profit_at_close": None,
                       "favorable_move_atr": None, "tightening_trigger": "entry",
                       "tightened": False, "initialized": False, "extreme_price": None,
                       "extreme_day": None, "no_new_extreme_days": 0, "arm_day": None,
                       "full_holding_day": False, "new_extreme": False}.items():
        equal(getattr(first, key), value, "V2 initial stop " + key)

    held = hourly.loc[(hourly.index >= trade.entry_time) & (hourly.index <= trade.exit_time)]
    held_ns = pd.DatetimeIndex(held.index).as_unit("ns").asi8
    carried = np.r_[0.0, np.cumsum(held.open.to_numpy() * trade.qty * carry_daily / 24)]
    old_stop, mult, reductions = initial, 1.5, 0
    for row in records.iloc[1:].itertuples(index=False):
        assert row.timestamp == row.signal_day + DAY, "Unclosed day controls V2 stop"
        day = daily.loc[row.signal_day]
        # The close-time decision includes costs before midnight, not the
        # new hour's carry. Rebuild these independently of the stop ledger.
        before_boundary = carried[np.searchsorted(held_ns, row.timestamp.value, side="left")]
        close = float(hourly.loc[row.timestamp - HOUR, "close"])
        equal(close, day.close, "V2 daily close vs hourly close")
        fill = close * (1 - side * slip)
        profit = (side * trade.qty * (fill - trade.entry_price) - trade.entry_fee
                  - trade.qty * fill * fee - before_boundary)
        favorable = side * (close - trade.entry_price)
        eligible = profit > 0 and favorable >= summary["profit_trigger_atr"] * trade.entry_atr
        natural = float(day.ma - side * mult * day.atr)
        stalled = side * (natural - old_stop) <= 1e-12 * max(1.0, abs(old_stop))
        if mult <= 0.5:
            trigger, tightened = "at_floor", False
        elif eligible and stalled:
            trigger, tightened = "stall_profit", True
        else:
            trigger, tightened = ("not_stalled" if eligible else "not_profitable"), False
        new_mult = max(0.5, round(mult - 0.2, 10)) if tightened else mult
        proposed = float(day.ma - side * new_mult * day.atr)
        stop = max(old_stop, proposed) if side == 1 else min(old_stop, proposed)
        expected = {"old_stop": old_stop, "new_stop": stop, "old_mult": mult,
                    "new_mult": new_mult, "old_armed": False, "new_armed": False,
                    "natural_candidate": natural, "stalled": bool(stalled),
                    "expected_profit_at_close": profit, "profit_eligible": bool(eligible),
                    "favorable_move_atr": favorable / trade.entry_atr,
                    "tightening_trigger": trigger, "tightened": bool(tightened),
                    "initialized": False, "extreme_price": None, "extreme_day": None,
                    "no_new_extreme_days": 0, "arm_day": None,
                    "full_holding_day": bool(row.signal_day >= trade.entry_time),
                    "new_extreme": False, "anchor_candidate": None,
                    "anchor_decisive": False}
        for key, value in expected.items():
            equal(getattr(row, key), value, "V2 stop " + key)
        assert side * (stop - old_stop) >= 0 and 0.5 <= new_mult <= mult <= 1.5
        reductions += int(tightened)
        old_stop, mult = stop, new_mult
    for key, value in {"stop": old_stop, "stop_mult": mult, "armed": False,
                       "initialized": False, "extreme_price": None, "extreme_day": None,
                       "arm_day": None, "no_new_extreme_days": 0,
                       "tightening_days": reductions, "stop_floor_reached": mult == 0.5,
                       "anchor_decisive_days": 0}.items():
        equal(getattr(trade, key), value, "V2 final stop " + key)


def audit_v2_run(directory, daily, hourly, carry_daily=0.0):
    # Each process handles accounts sequentially. This replaces only the old
    # audit's stop checker, leaving its independent full-account checks intact.
    original_checker = prior.audit_stop_path
    prior.audit_stop_path = lambda trade, rows, days, summary: audit_v2_stop_path(
        trade, rows, days, summary, hourly, carry_daily)
    try:
        return prior.audit_run(directory, daily, hourly, carry_daily)
    finally:
        prior.audit_stop_path = original_checker


def audit_coin(item, inputs, original, results, config, source, summary, stress):
    row = SimpleNamespace(**item)
    daily, hourly, windows = prior.load_market_inputs(
        inputs, original, row, {"main/" + row.symbol: source})
    coin = {"symbol": row.symbol, "cohort": row.cohort, "runs": 0, "trades": 0,
            "stop_records": 0, "equity_marks": 0, "main_rows": 0, "stress_rows": 0}
    directories = []
    scenarios = [("runs", window, bounds, 0.0) for window, bounds in windows.items()]
    scenarios += [("sensitivity", name, windows["full"], carry) for name, carry in
                  (("slippage_10bp", 0.0), ("carry_5bp_day", 0.0005))]
    for group, name, bounds, carry in scenarios:
        directory = results / group / row.slug / "V2" / name
        saved = read_json(directory / "summary.json")
        for key, value in config.items():
            if group == "sensitivity" and name == "slippage_10bp" and key == "slip":
                value = .001
            equal(saved[key], value, "V2 frozen parameter " + key)
        assert [pd.Timestamp(saved["start"]), pd.Timestamp(saved["end_exclusive"])] == list(map(pd.Timestamp, bounds))
        checked = audit_v2_run(directory, daily, hourly, carry)
        selectors = {"symbol": row.symbol, "case_id": "V2", "cohort": row.cohort,
                     "window" if group == "runs" else "scenario": name}
        prior.compare_summary_row(summary if group == "runs" else stress, selectors, saved)
        coin["runs"] += 1
        coin["trades"] += checked["trades"]
        coin["stop_records"] += checked["stop_records"]
        coin["equity_marks"] += checked["equity_marks_independently_rebuilt"]
        coin["main_rows" if group == "runs" else "stress_rows"] += 1
        directories.append(str(directory.relative_to(results)))
    return coin, directories


def saved_hype_controls(results):
    old = LAB / "research/hype/1d-ma7-cross-atr-ratchet/artifacts/r2_slowdown_tightening_20260909"
    checks = read_json(old / "artifact_checksums.json")
    case = "s0.05_rev0_accel1_rsi30_original_stall_only_p0"
    evidence = []
    for window in ("full", "early60", "late40"):
        native, new = old / "runs" / case / window, results / "runs/HYPE/V2" / window
        for name in ("summary.json", "trades.csv", "stops.csv", "equity.parquet"):
            assert sha(native / name) == checks[str((native / name).relative_to(old))]
        original, current = read_json(native / "summary.json"), read_json(new / "summary.json")
        for key, value in original.items():
            if key != "name":
                equal(current[key], value, "V2 saved HYPE " + key)
        for name in ("trades.csv", "stops.csv", "equity.parquet"):
            a, b = read_frame(native / name), read_frame(new / name)
            pd.testing.assert_frame_equal(a, b[a.columns], check_exact=True)
        evidence.append({"window": window, "native_directory": str(native.relative_to(LAB)),
                         "native_checksums_sha256": sha(old / "artifact_checksums.json"),
                         "all_original_trade_stop_equity_fields_exact_equal": True})
    return evidence


def stop_fixture(side=1, carry_daily=0.0, carry_gate=False):
    """Hand-specified stop path, not produced by a strategy implementation."""
    entry = pd.Timestamp("2026-01-02T00:00Z")
    n = 1 if carry_gate else 8
    dates = pd.date_range(entry - DAY, periods=n + 1, freq="D")
    # Day 2 advances naturally; day 3 loses money; later plateau days tighten.
    ma = [100.0] + [100.0, 100.0 + side, 100.0 + side, *([100.0 + side] * 5)][:n]
    close = [100.0] + [100.0 + side, 100.0 + side, 100.0 - side, *([100.0 + side] * 5)][:n]
    daily = pd.DataFrame({"timestamp": dates, "ma": ma, "atr": 2.0, "close": close}).set_index("timestamp", drop=False)
    hours = pd.date_range(entry, entry + n * DAY + HOUR, freq="h")
    hourly = pd.DataFrame({"open": 100.0, "close": 100.0}, index=hours)
    for day, value in zip(dates[1:], close[1:]):
        hourly.loc[day + DAY - HOUR, "close"] = value
    initial = 100.0 - side * 3
    first = {"timestamp": entry, "signal_day": entry - DAY, "new_stop": initial,
             "old_stop": initial, "new_mult": 1.5, "old_mult": 1.5, "new_armed": False,
             "old_armed": False, "natural_candidate": initial, "stalled": False,
             "profit_eligible": False, "expected_profit_at_close": None,
             "favorable_move_atr": None, "tightening_trigger": "entry", "tightened": False,
             "initialized": False, "extreme_price": None, "extreme_day": None,
             "no_new_extreme_days": 0, "arm_day": None, "full_holding_day": False,
             "new_extreme": False, "anchor_candidate": None, "anchor_decisive": False}
    multiples = ([1.5] if carry_gate else [1.3, 1.3, 1.3, 1.1, .9, .7, .5, .5])
    distances = ([3.0] if carry_gate else [2.6, 1.6, 1.6, 1.2, .8, .4, 0.0, 0.0])
    natural_distances = [3.0, 1.6, 1.6, 1.6, 1.2, .8, .4, 0.0][:n]
    triggers = (["not_profitable"] if carry_gate else
                ["stall_profit", "not_stalled", "not_profitable", *(["stall_profit"] * 4), "at_floor"])
    rows, old_stop, old_mult = [first], initial, 1.5
    for i in range(n):
        price = close[i + 1]
        expected_profit = side * (price - 100.0) - .1 - price * .001 - (i + 1) * 100 * carry_daily
        row = {**first, "timestamp": entry + (i + 1) * DAY, "signal_day": entry + i * DAY,
               "old_stop": old_stop, "new_stop": 100.0 - side * distances[i],
               "old_mult": old_mult, "new_mult": multiples[i],
               "natural_candidate": 100.0 - side * natural_distances[i],
               "stalled": i != 1, "profit_eligible": expected_profit > 0,
               "expected_profit_at_close": expected_profit,
               "favorable_move_atr": side * (price - 100.0) / 2,
               "tightening_trigger": triggers[i], "tightened": triggers[i] == "stall_profit",
               "full_holding_day": True}
        rows.append(row)
        old_stop, old_mult = row["new_stop"], row["new_mult"]
    trade = SimpleNamespace(side=side, signal_day=entry - DAY, entry_time=entry,
                            exit_time=entry + n * DAY + HOUR, initial_stop=initial,
                            uncapped_initial_stop=initial, entry_atr=2.0, initial_stop_mult=1.5,
                            cap_applied=False, progress_source="high_low", entry_price=100.0,
                            entry_fee=.1, qty=1.0, stop=old_stop, stop_mult=old_mult, armed=False,
                            initialized=False, extreme_price=None, extreme_day=None, arm_day=None,
                            no_new_extreme_days=0, tightening_days=0 if carry_gate else 5,
                            stop_floor_reached=not carry_gate, anchor_decisive_days=0)
    summary = {"tighten_mode": "stall_only", "progress_days": 0, "profit_trigger_atr": 0,
               "entry_wait_days": 0, "fee": .001, "slip": 0,
               "end_exclusive": str(entry + (n + 2) * DAY)}
    return trade, pd.DataFrame(rows), daily, summary, hourly, carry_daily


def self_checks():
    assert sha(Path(prior.__file__)) == PRIOR_AUDIT_SHA, "Original independent audit changed"
    evidence = []
    for side in (1, -1):
        fixture = stop_fixture(side)
        audit_v2_stop_path(*fixture)
        evidence.append({"check": "long" if side == 1 else "short", "status": "PASS",
                         "covers": "daily recheck, nonstall, loss stall, five reductions, floor, never armed"})
        fixture = stop_fixture(side, carry_daily=.01, carry_gate=True)
        audit_v2_stop_path(*fixture)
        evidence.append({"check": f"carry_blocks_side_{side}", "status": "PASS"})
    baseline = stop_fixture()
    mutations = [(1, "new_armed", True), (1, "tightening_trigger", "armed_daily"),
                 (2, "tightened", True), (3, "tightened", True),
                 (4, "old_mult", 1.5), (8, "new_mult", .3),
                 (1, "stalled", False), (1, "profit_eligible", False),
                 (1, "new_stop", 96.0), (1, "signal_day", pd.Timestamp("2026-01-03T00:00Z"))]
    for row, column, value in mutations:
        fixture = copy.deepcopy(baseline)
        fixture[1].at[row, column] = value
        try:
            audit_v2_stop_path(*fixture)
        except AssertionError:
            evidence.append({"check": f"reject_{row}_{column}", "status": "PASS"})
        else:
            raise AssertionError(f"Mutation escaped stop audit: {row}/{column}")
    # Carry charged at the new boundary must not enter the preceding close's
    # decision. Altering only that hour's open leaves the one-day fixture valid.
    fixture = stop_fixture(carry_daily=.01, carry_gate=True)
    fixture[4].loc[fixture[1].iloc[-1].timestamp, "open"] = 1e9
    audit_v2_stop_path(*fixture)
    evidence.append({"check": "carry_boundary_is_exclusive", "status": "PASS"})
    return {"status": "PASS", "audit_script_sha256": sha(Path(__file__)),
            "base_audit_sha256": PRIOR_AUDIT_SHA, "simulator_called": False,
            "checks": evidence, "check_count": len(evidence)}


def audit_all(inputs, original, results, workers=4):
    assert 1 <= workers <= 4
    done = read_json(results / "completion.json")
    assert done["complete"] and done["coins_failed"] == 0, "V2 results are not complete"
    assert done["v1_runs"] == done["v3_runs"] == done["buyhold_runs"] == 0
    proof = self_checks()
    manifest = read_json(results / "run_manifest.json")
    original_manifest = read_json(original / "run_manifest.json")
    prior_report_path = FAMILY / "artifacts/audit_results_20260909.json"
    assert sha(prior_report_path) == PRIOR_REPORT_SHA, "Original audit report changed"
    prior_report = read_json(prior_report_path)
    assert prior_report["status"] == "PASS" and not prior_report["simulator_called"]
    assert sha(inputs / "checksums.json") == manifest["input_checksums_sha256"] == prior_report["input_manifest_sha256"]
    assert sha(inputs / "frozen_plan.json") == manifest["input_plan_sha256"]
    assert read_json(inputs / "frozen_plan.json") == manifest["input_plan"]
    assert sha(original / "artifact_checksums.json") == manifest["original_result_manifest_sha256"] == prior_report["result_manifest_sha256"]
    input_count = prior.verify_hash_map(inputs)
    input_provenance = prior.audit_input_provenance(inputs)
    print(f"VERIFIED {input_count} frozen input files", flush=True)
    for role in ("engine", "contract", "run_script", "version_map"):
        assert sha(LAB / manifest[role + "_path"]) == manifest[role + "_sha256"], role
    assert manifest["engine_sha256"] == ENGINE_SHA == original_manifest["engine_sha256"]
    for role in ("common", "run_market"):
        assert sha(Path(__file__).with_name(role + ".py")) == manifest[role + "_sha256"]
    version_map = read_json(LAB / manifest["version_map_path"])
    source_v2 = next(row for row in version_map["versions"] if row["version"] == "V2")
    assert source_v2 == manifest["source_v2"]
    config = {**source_v2["frozen_engine_config"], "progress_source": "high_low", "entry_wait_days": 0}
    assert len(manifest["cases"]) == 1 and manifest["cases"][0]["case_id"] == "V2"
    assert manifest["cases"][0]["config"] == config
    assert not config["reverse"] and config["progress_days"] == 0 and config["tighten_mode"] == "stall_only"
    assert not manifest["funding_window_verified"] and not manifest["old_engines_rerun"]
    assert manifest["all_symbols_same_stresses"] == ["slippage_10bp", "carry_5bp_day"]
    old_checks = read_json(original / "artifact_checksums.json")
    for path, digest in manifest["verified_original_files"].items():
        assert sha(LAB / path) == digest, "Reused original file changed: " + path
    # Only verify hashes for original V1/V3/BH accounts. They are not simulated
    # or independently replayed again; their original full audit remains pinned.
    reused = {}
    common_names = {"run_manifest.json", "scope.csv", "summary.csv", "stress.csv", "buy_hold.csv",
                    "completion.json", "execution_failures.json", "hype_original_controls.json"}
    for name, digest in old_checks.items():
        parts = Path(name).parts
        required = (name in common_names or parts[0] in {"market", "buy_hold"}
                    or (parts[0] in {"runs", "sensitivity"} and len(parts) > 2
                        and parts[2] in {"F0", "H4_D0"}))
        if required:
            assert sha(original / name) == digest, "Reused V1/V3 source changed: " + name
            reused[name] = digest
    assert set(manifest["reused_not_rerun"]) == {"V1", "V3"}
    for version, case in (("V1", "F0"), ("V3", "H4_D0")):
        assert manifest["reused_not_rerun"][version] == {"source_case_id": case, "results": str(original.relative_to(LAB))}
        old_config = next(c["config"] for c in original_manifest["cases"] if c["case_id"] == case)
        mapped = next(c["frozen_engine_config"] for c in version_map["versions"] if c["version"] == version)
        assert old_config == {**mapped, "progress_source": "high_low", "entry_wait_days": 0}
    result_count = prior.verify_hash_map(results, "artifact_checksums.json")
    print(f"VERIFIED {len(reused)} reused original files and {result_count} V2 result files", flush=True)
    original_scope, counts = prior.audit_scope(inputs, original, original_manifest)
    scope, counts_v2 = prior.audit_scope(inputs, results, manifest)
    pd.testing.assert_frame_equal(original_scope, scope, check_exact=True)
    assert counts == counts_v2 == {"main_full": 346, "partial": 193, "short": 72, "excluded": 41}
    assert read_json(results / "execution_failures.json") == []
    summary, stress = (read_frame(results / name) for name in ("summary.csv", "stress.csv"))
    assert set(summary.case_id) == set(stress.case_id) == {"V2"}
    assert not (results / "buy_hold").exists() and not (results / "market").exists()
    assert len(summary) == 1689 and len(stress) == 1222
    frames = read_json(inputs / "frames_manifest.json")
    per_coin, verified_dirs = [], set()
    jobs = [(item, inputs, original, results, config, frames["main/" + item["symbol"]],
             summary.loc[summary.symbol == item["symbol"]], stress.loc[stress.symbol == item["symbol"]])
            for item in scope.loc[scope.cohort != "excluded"].to_dict("records")]

    def collect(value):
        coin, directories = value
        per_coin.append(coin)
        verified_dirs.update(results / name for name in directories)
        if len(per_coin) % 40 == 0:
            print(f"AUDITED V2 {len(per_coin)} coins; {sum(c['runs'] for c in per_coin)} accounts; "
                  f"{sum(c['trades'] for c in per_coin)} trades", flush=True)

    if workers == 1:
        for args in jobs:
            collect(audit_coin(*args))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            pending = {pool.submit(audit_coin, *args): args[0]["symbol"] for args in jobs}
            for future in as_completed(pending):
                try:
                    collect(future.result())
                except Exception as exc:
                    for outstanding in pending:
                        outstanding.cancel()
                    raise AssertionError(f"V2 independent audit failed for {pending[future]}: {exc}") from exc
    per_coin.sort(key=lambda item: item["symbol"])
    expected_dirs = {p.parent for p in results.glob("runs/*/*/*/summary.json")}
    expected_dirs |= {p.parent for p in results.glob("sensitivity/*/*/*/summary.json")}
    assert expected_dirs == verified_dirs
    accounts = sum(c["runs"] for c in per_coin)
    assert accounts == 2911 and len(per_coin) == done["coins_completed"] == 611
    assert sum(c["main_rows"] for c in per_coin) == done["strategy_window_runs"] == 1689
    assert sum(c["stress_rows"] for c in per_coin) == done["stress_runs"] == 1222
    controls = saved_hype_controls(results)
    return {"status": "PASS", "audit_script_sha256": sha(Path(__file__)),
            "base_audit_script_sha256": PRIOR_AUDIT_SHA, "prior_audit_report_sha256": PRIOR_REPORT_SHA,
            "input_manifest_sha256": sha(inputs / "checksums.json"),
            "original_result_manifest_sha256": sha(original / "artifact_checksums.json"),
            "result_manifest_sha256": sha(results / "artifact_checksums.json"),
            "hashed_input_files": input_count, "hashed_v2_result_files": result_count,
            "hashed_reused_original_files": len(reused),
            "reused_hash_map_canonical_sha256": prior.canonical_sha(reused),
            "input_provenance": input_provenance, "self_checks": proof,
            "observed_contracts": 874, "included_coins": 652, "cohort_counts": counts,
            "coins_independently_audited": len(per_coin), "strategy_accounts_audited": accounts,
            "trades_audited": sum(c["trades"] for c in per_coin),
            "stop_records_audited": sum(c["stop_records"] for c in per_coin),
            "equity_marks_independently_rebuilt": sum(c["equity_marks"] for c in per_coin),
            "per_coin": per_coin, "frozen_saved_hype_controls": controls,
            "v1_v3_reused_via_hash_only": True, "old_accounts_recomputed": 0,
            "simulator_called": False, "workers": workers, "funding_window_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=INPUTS)
    parser.add_argument("--original", type=Path, default=ORIGINAL)
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--self-check-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Audit output already exists; preserve it and choose a new file")
    report = self_checks() if args.self_check_only else audit_all(
        args.inputs.resolve(), args.original.resolve(), args.results.resolve(), args.workers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({k: v for k, v in report.items() if k not in {"per_coin", "input_provenance", "self_checks"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
