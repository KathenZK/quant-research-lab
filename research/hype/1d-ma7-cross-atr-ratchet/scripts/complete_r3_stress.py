"""Disclosed post-result completion of identical stresses for every R3 case."""
from dataclasses import replace
from pathlib import Path
import json

import pandas as pd

from engine_r3 import simulate
from run_r3 import BASE, OUTPUT, STRESS_IDS, WINDOWS, case_list, load_r3_inputs, save_result, sha, write_json


def main():
    out = BASE / "artifacts/r3_all_case_stress_20260909"
    out.mkdir(exist_ok=False)
    cases = [(i, label, c) for i, label, c in case_list() if i not in STRESS_IDS]
    write_json(out / "run_manifest.json", {
        "created_before_supplement_results_utc": str(pd.Timestamp.now(tz="UTC")),
        "timing": "POST_RESULT_GLOBAL_COMPLETENESS: original 42 rows and 24 stresses have been observed",
        "purpose": "Apply the exact same four already declared stresses to every remaining case, including poor ones; no new rules, thresholds, scenarios or winner-only tests",
        "source_result_manifest_sha256": sha(OUTPUT / "artifact_checksums.json"),
        "engine_sha256": sha(BASE / "scripts/engine_r3.py"), "script_sha256": sha(Path(__file__)),
        "additional_cases": [i for i, _, _ in cases], "additional_runs": 32,
        "classification": "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS", "funding_window_verified": False,
    })
    pins = json.loads((OUTPUT / "artifact_checksums.json").read_text())
    assert all(sha(OUTPUT / f) == h for f, h in pins.items())
    h, d, f = load_r3_inputs()
    rows = []
    for case_id, label, c in cases:
        for scenario, variant, funding, carry in [
            ("slippage_10bp", replace(c, slip=.001), None, 0),
            ("daily_signal_delay_1h", replace(c, delay_hours=1), None, 0),
            ("adverse_carry_5bp_day", c, None, .0005),
            ("observed_funding_unverified", c, f, 0),
        ]:
            result = simulate(h, d, variant, pd.Timestamp(WINDOWS["full"][0]), pd.Timestamp(WINDOWS["full"][1]), funding, carry)
            save_result(out / "runs" / case_id / scenario, result)
            rows.append({"case_id": case_id, "scenario": scenario, **result[0]})
        print("completed " + case_id, flush=True)
    extra = pd.DataFrame(rows)
    extra.to_csv(out / "supplemental_sensitivity.csv", index=False)
    original = pd.read_csv(OUTPUT / "sensitivity.csv")
    original["study_timing"] = "predeclared"
    extra["study_timing"] = "post_result_global_completeness"
    combined = pd.concat([original, extra], ignore_index=True)
    assert len(extra) == 32 and len(combined) == 56
    assert combined.groupby("case_id").size().eq(4).all()
    combined.to_csv(out / "all_14_case_sensitivity.csv", index=False)
    write_json(out / "artifact_checksums.json", {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()})


if __name__ == "__main__":
    main()
