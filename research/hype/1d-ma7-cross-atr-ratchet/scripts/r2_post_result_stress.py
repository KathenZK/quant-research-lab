"""Disclosed post-result stress checks; no rule or parameter selection."""
from dataclasses import replace
from pathlib import Path

import pandas as pd

from engine_r2 import Config, simulate
from run_r2 import BASE, DEFAULT_OUT, WINDOWS, load_r2_inputs, save_result, sha, write_json


def main():
    out = BASE / "artifacts/r2_post_result_stress_20260909"
    out.mkdir(exist_ok=False)
    write_json(out / "run_manifest.json", {
        "created_before_supplement_results_utc": str(pd.Timestamp.now(tz="UTC")),
        "timing": "POST_RESULT_DIAGNOSTIC: 28-case R2 results were already observed",
        "reason": "Original entry plus stall-only tightening improved observed returns; apply the same four stresses without changing any entry, exit, sizing, or threshold",
        "cases": "original + stall_only + profit_trigger_atr=0, reverse off/on",
        "scenarios": ["slippage_10bp", "daily_signal_delay_1h", "adverse_carry_5bp_day", "observed_funding_unverified"],
        "r2_artifact_checksums_sha256": sha(DEFAULT_OUT / "artifact_checksums.json"),
        "script_sha256": sha(Path(__file__)),
        "engine_sha256": sha(BASE / "scripts/engine_r2.py"),
        "funding_window_verified": False,
    })
    h, d, f = load_r2_inputs()
    rows = []
    for reverse in [False, True]:
        c = Config(entry_mode="original", tighten_mode="stall_only", reverse=reverse)
        for scenario, variant, funding, carry in [
            ("slippage_10bp", replace(c, slip=.001), None, 0),
            ("daily_signal_delay_1h", replace(c, delay_hours=1), None, 0),
            ("adverse_carry_5bp_day", c, None, .0005),
            ("observed_funding_unverified", c, f, 0),
        ]:
            result = simulate(h, d, variant, pd.Timestamp(WINDOWS["full"][0]), pd.Timestamp(WINDOWS["full"][1]), funding, carry)
            save_result(out / c.name / scenario, result)
            rows.append({"scenario": scenario, **result[0]})
    table = pd.DataFrame(rows)
    table.to_csv(out / "sensitivity.csv", index=False)
    write_json(out / "artifact_checksums.json", {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()})
    print(table[["scenario", "reverse", "return_pct", "max_drawdown_pct"]].to_string(index=False))


if __name__ == "__main__":
    main()
