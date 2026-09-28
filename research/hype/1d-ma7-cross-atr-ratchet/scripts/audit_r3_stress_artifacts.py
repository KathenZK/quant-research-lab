"""Independently audit the disclosed 32 supplemental R3 stress ledgers."""
from pathlib import Path
import json

import pandas as pd

from audit_r3_artifacts import (
    BASE, DEFAULT_RESULTS, INPUT, audit_ledger, equal, parse_times,
    read_json, sha, verify_hash_map,
)


def main():
    extra = BASE / "artifacts/r3_all_case_stress_20260909"
    output = BASE / "artifacts/r3_all_case_stress_audit_20260909.json"
    assert not output.exists(), "Preserve prior supplemental audit"
    manifest = read_json(extra / "run_manifest.json")
    original_manifest = read_json(DEFAULT_RESULTS / "run_manifest.json")
    assert manifest["timing"].startswith("POST_RESULT_GLOBAL_COMPLETENESS")
    assert sha(DEFAULT_RESULTS / "artifact_checksums.json") == manifest["source_result_manifest_sha256"]
    assert sha(BASE / "scripts/engine_r3.py") == manifest["engine_sha256"]
    assert sha(BASE / "scripts/complete_r3_stress.py") == manifest["script_sha256"]
    hashed = verify_hash_map(extra, exact=True)
    verify_hash_map(DEFAULT_RESULTS, exact=True)
    cases = {x["case_id"]: x["config"] for x in original_manifest["cases"]}
    assert set(manifest["additional_cases"]) == set(cases) - set(original_manifest["sensitivity_cases"])
    daily = parse_times(pd.read_csv(DEFAULT_RESULTS / "daily_features.csv"), ["timestamp"]).set_index("timestamp")
    hourly = pd.read_parquet(INPUT / "hourly.parquet").set_index("ts")
    rows = pd.read_csv(extra / "supplemental_sensitivity.csv")
    checks = []
    for case_id in manifest["additional_cases"]:
        for scenario in ["slippage_10bp", "daily_signal_delay_1h", "adverse_carry_5bp_day", "observed_funding_unverified"]:
            config = dict(cases[case_id])
            if scenario == "slippage_10bp":
                config["slip"] = .001
            if scenario == "daily_signal_delay_1h":
                config["delay_hours"] = 1
            directory = extra / "runs" / case_id / scenario
            check, _ = audit_ledger(directory, config, daily, hourly)
            checks.append(check)
            row = rows[(rows.case_id == case_id) & (rows.scenario == scenario)]
            assert len(row) == 1
            summary = read_json(directory / "summary.json")
            for key in ["return_pct", "max_drawdown_pct", "trades", "fee_total", "ending_equity"]:
                equal(row.iloc[0][key], summary[key], "supplement summary " + key)
    assert len(checks) == len(rows) == 32
    actual_dirs = {str(p.parent.relative_to(BASE)) for p in extra.rglob("summary.json")}
    assert actual_dirs == {check["directory"] for check in checks}
    combined = pd.read_csv(extra / "all_14_case_sensitivity.csv")
    original = pd.read_csv(DEFAULT_RESULTS / "sensitivity.csv")
    assert len(combined) == 56 and combined.groupby("case_id").size().eq(4).all()
    for source, timing in [(original, "predeclared"), (rows, "post_result_global_completeness")]:
        part = combined[combined.study_timing == timing]
        assert len(part) == len(source)
        keys = ["case_id", "scenario"]
        pd.testing.assert_frame_equal(part[source.columns].sort_values(keys).reset_index(drop=True),
                                      source.sort_values(keys).reset_index(drop=True), check_exact=False, rtol=0, atol=1e-8)
    # Independently compare the six saved old-control ledgers, beyond their
    # runner's recorded assertion; no historical strategy is rerun here.
    baseline_frames = 0
    for case_id, mode in [("B0_r2_stall", "stall_only"), ("B1_r1_fixed", "fixed")]:
        old_root = BASE / f"artifacts/r2_slowdown_tightening_20260909/runs/s0.05_rev0_accel1_rsi30_original_{mode}_p0"
        for window in original_manifest["windows"]:
            new_root = DEFAULT_RESULTS / "runs" / case_id / window
            for filename in ["trades.csv", "stops.csv"]:
                old = pd.read_csv(old_root / window / filename)
                new = pd.read_csv(new_root / filename)
                pd.testing.assert_frame_equal(old, new[old.columns], check_exact=True)
            pd.testing.assert_frame_equal(pd.read_parquet(old_root / window / "equity.parquet"),
                                          pd.read_parquet(new_root / "equity.parquet"), check_exact=True)
            baseline_frames += 1
    result = {"status": "PASS", "method": "Read-only saved-ledger checks; no simulator imported or run",
              "timing": manifest["timing"], "audit_script_sha256": sha(Path(__file__)),
              "shared_ledger_auditor_sha256": sha(BASE / "scripts/audit_r3_artifacts.py"),
              "supplement_manifest_sha256": sha(extra / "run_manifest.json"),
              "supplement_checksum_manifest_sha256": sha(extra / "artifact_checksums.json"),
              "files_hashed": hashed, "supplemental_ledgers_verified": len(checks),
              "supplemental_trades_verified": sum(x["trades"] for x in checks),
              "supplemental_stop_records_verified": sum(x["stop_records"] for x in checks),
              "all_case_sensitivity_rows_verified": len(combined),
              "separate_study_timing_preserved": True, "saved_r2_r3_baseline_frames_exact_equal": baseline_frames,
              "funding_window_verified": False, "ledgers": checks}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: result[k] for k in ["status", "supplemental_ledgers_verified", "supplemental_trades_verified", "all_case_sensitivity_rows_verified", "saved_r2_r3_baseline_frames_exact_equal"]}))


if __name__ == "__main__":
    main()
