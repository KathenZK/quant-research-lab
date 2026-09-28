"""Fill only official V2 across the frozen P1 scope; never rerun old arms."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from common import BASE, ENGINE_PATH, ENGINE_SHA256, INPUT, RESULTS, ROOT, load_engine, sha, write_json
from run_market import load_selected_frames, period_windows, save_result, select_scope, verify_inputs

SPEC = BASE / "specs/contract-v1-v3-comparison-20260910.md"
VERSION_MAP = ROOT / "research/hype/1d-ma7-cross-atr-ratchet/specs/version-map-20260910.json"
HYPE_BASE = VERSION_MAP.parent.parent
OUT = BASE / "artifacts/results_v2_20260910"
CASE = "V2"
LABEL = "盈利且MA止损停滞日收紧"
INPUT_SHA = "a2390b002883506a8f39522a31e708e76346e21be6a0a598e753b4a5b5e4891c"
RESULTS_SHA = "880d7201b4c23695265d80d2704e0ec03245dfdb8a274b50873f82fbfb50a13d"


def official_v2():
    mapping = json.loads(VERSION_MAP.read_text())
    v2 = next(v for v in mapping["versions"] if v["version"] == "V2")
    config = {**v2["frozen_engine_config"], "progress_source": "high_low", "entry_wait_days": 0}
    assert config["tighten_mode"] == "stall_only" and config["progress_days"] == 0
    assert not config["reverse"] and config["short_exit"] == "accel1_rsi30"
    return v2, load_engine().Config(**config)


def verify_previous():
    assert sha(INPUT / "checksums.json") == INPUT_SHA
    manifest_path = RESULTS / "artifact_checksums.json"
    assert sha(manifest_path) == RESULTS_SHA
    manifest = json.loads(manifest_path.read_text())
    checked = {}
    for relative in ["summary.csv", "stress.csv", "scope.csv", "completion.json", "run_manifest.json", "execution_failures.json"]:
        actual = sha(RESULTS / relative)
        assert actual == manifest[relative], "Original aggregate changed: " + relative
        checked[str((RESULTS / relative).relative_to(ROOT))] = actual
    v2, config = official_v2()
    for relative, expected in v2["source_files_sha256"].items():
        assert sha(HYPE_BASE / relative) == expected, "Official V2 result changed: " + relative
        checked[str((HYPE_BASE / relative).relative_to(ROOT))] = expected
    return v2, config, checked


def check_hype_saved_reference(out, result, v2):
    """Compare the one newly required HYPE V2 full result to existing old files."""
    current = out / "runs/HYPE/V2/full"
    old = (HYPE_BASE / v2["source_summary"]).parent
    reference = json.loads((old / "summary.json").read_text())
    new_summary = result[0]
    for key, value in reference.items():
        if key != "name":
            assert key in new_summary and new_summary[key] == value, f"HYPE summary differs: {key}"
    comparisons = []
    for filename in ["trades.csv", "stops.csv", "equity.parquet"]:
        if filename.endswith(".csv"):
            a = pd.read_csv(old / filename, float_precision="round_trip")
            b = pd.read_csv(current / filename, float_precision="round_trip")
        else:
            a = pd.read_parquet(old / filename)
            b = pd.read_parquet(current / filename)
        assert set(a.columns).issubset(b.columns)
        pd.testing.assert_frame_equal(a, b[a.columns], check_exact=True)
        comparisons.append({"file": filename, "rows": len(a), "old_columns": list(a.columns),
                            "added_columns": [c for c in b.columns if c not in a.columns],
                            "all_original_columns_exact_equal": True,
                            "reference_sha256": sha(old / filename), "new_sha256": sha(current / filename)})
    report = {"passed": True, "comparison": "New required V2 HYPE full against existing saved R3 B0_r2_stall; old engine was never run",
              "old_summary_fields_exact_except_name": True, "excluded_summary_fields": ["name"],
              "old_name": reference["name"], "new_name": new_summary["name"],
              "new_summary_fields": [k for k in new_summary if k not in reference],
              "csv_read": "pandas read_csv float_precision=round_trip; exact numeric equality, no tolerance",
              "comparisons": comparisons, "reused_in_market_loop": True,
              "return_pct": new_summary["return_pct"], "max_drawdown_pct": new_summary["max_drawdown_pct"], "trades": new_summary["trades"]}
    write_json(out / "hype_v2_existing_result_comparison.json", report)
    return report


def replay_coin(item, frame_manifest, out_string, config_dict):
    out = Path(out_string)
    h, d, _ = load_selected_frames(item, frame_manifest)
    windows = period_windows(item)
    engine = load_engine()
    config = engine.Config(**config_dict)
    rows, stress = [], []
    for window, (lo, hi) in windows.items():
        directory = out / "runs" / item["slug"] / CASE / window
        if item["symbol"] == "HYPE/USDT:USDT" and window == "full":
            summary = json.loads((directory / "summary.json").read_text())
        else:
            result = engine.simulate(h, d, config, pd.Timestamp(lo), pd.Timestamp(hi))
            save_result(directory, result)
            summary = result[0]
        assert pd.Timestamp(summary["start"]) == pd.Timestamp(lo)
        assert pd.Timestamp(summary["end_exclusive"]) == pd.Timestamp(hi)
        rows.append({"symbol": item["symbol"], "slug": item["slug"], "cohort": item["cohort"],
                     "trade_days": item["trade_days"], "case_id": CASE, "label": LABEL, "window": window, **summary})
    lo, hi = windows["full"]
    for scenario, cfg, carry in [("slippage_10bp", replace(config, slip=.001), 0), ("carry_5bp_day", config, .0005)]:
        result = engine.simulate(h, d, cfg, pd.Timestamp(lo), pd.Timestamp(hi), None, carry)
        save_result(out / "sensitivity" / item["slug"] / CASE / scenario, result)
        stress.append({"symbol": item["symbol"], "slug": item["slug"], "cohort": item["cohort"],
                       "case_id": CASE, "scenario": scenario, **result[0]})
    return rows, stress


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        parser.error("Fresh output directory required; no retained results may be overwritten")
    started = time.monotonic()
    v2, config, old_hashes = verify_previous()
    plan = verify_inputs()
    scope = select_scope()
    previous_scope = pd.read_csv(RESULTS / "scope.csv", float_precision="round_trip")
    compare_columns = [c for c in scope.columns if c != "status"]
    for column in compare_columns:
        a, b = scope[column], previous_scope[column]
        assert a.isna().equals(b.isna()), "Scope missingness changed: " + column
        valid = a.notna()
        assert a[valid].astype(str).equals(b[valid].astype(str)), "Scope selection changed: " + column
    assert scope.cohort.value_counts().to_dict() == {"main_full": 346, "partial": 193, "short": 72, "excluded": 41}
    frames = json.loads((INPUT / "frames_manifest.json").read_text())
    out.mkdir(parents=True)
    scope.to_csv(out / "scope.csv", index=False)
    write_json(out / "run_manifest.json", {
        "family_id": "BIN-1D-MA7-CAR-GEN", "round": "V1_V2_V3_COMPARISON_V2_ONLY", "created_before_new_results_utc": str(pd.Timestamp.now(tz="UTC")),
        "contract_path": str(SPEC.relative_to(ROOT)), "contract_sha256": sha(SPEC),
        "engine_path": str(ENGINE_PATH.relative_to(ROOT)), "engine_sha256": ENGINE_SHA256,
        "run_script_path": str(Path(__file__).relative_to(ROOT)), "run_script_sha256": sha(Path(__file__)),
        "common_sha256": sha(Path(__file__).with_name("common.py")), "run_market_sha256": sha(Path(__file__).with_name("run_market.py")),
        "input_checksums_sha256": INPUT_SHA, "input_plan_sha256": sha(INPUT / "frozen_plan.json"), "input_plan": plan,
        "version_map_path": str(VERSION_MAP.relative_to(ROOT)), "version_map_sha256": sha(VERSION_MAP),
        "cases": [{"case_id": CASE, "label": LABEL, "config": asdict(config)}],
        "reused_not_rerun": {"V1": {"source_case_id": "F0", "results": str(RESULTS.relative_to(ROOT))},
                             "V3": {"source_case_id": "H4_D0", "results": str(RESULTS.relative_to(ROOT))}},
        "original_result_manifest_sha256": RESULTS_SHA, "verified_original_files": old_hashes,
        "source_v2": v2, "observed_coins": len(scope), "cohort_counts": scope.cohort.value_counts().to_dict(),
        "scope_preserved_exact_excluding_execution_status": True, "buyhold_runs_planned": 0,
        "strategy_window_runs_planned": 1689, "stress_runs_planned": 1222,
        "hype_full_validation_run_reused": True, "old_engines_rerun": False,
        "classification": "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS", "funding_window_verified": False,
        "all_symbols_same_stresses": ["slippage_10bp", "carry_5bp_day"], "workers": args.workers})
    hype = scope[scope.symbol == "HYPE/USDT:USDT"].iloc[0].to_dict()
    h, d, _ = load_selected_frames(hype, frames)
    lo, hi = period_windows(hype)["full"]
    result = load_engine().simulate(h, d, config, pd.Timestamp(lo), pd.Timestamp(hi))
    save_result(out / "runs/HYPE/V2/full", result)
    report = check_hype_saved_reference(out, result, v2)
    del result, h, d
    print(f"HYPE V2 matches saved reference exactly: return={report['return_pct']:.8f} DD={report['max_drawdown_pct']:.8f} trades={report['trades']}; full reused", flush=True)
    candidates = scope[scope.cohort != "excluded"].to_dict("records")
    rows, stress, failures = [], [], []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(replay_coin, item, {"main/" + item["symbol"]: frames["main/" + item["symbol"]]}, str(out), asdict(config)): item for item in candidates}
        for n, future in enumerate(as_completed(jobs), 1):
            item = jobs[future]
            try:
                r, s = future.result()
            except Exception as exc:
                failures.append({"symbol": item["symbol"], "slug": item["slug"], "error_type": type(exc).__name__, "error": str(exc)})
                write_json(out / "execution_failures.json", failures)
                print("FAILED " + item["symbol"] + ": " + repr(exc), flush=True)
            else:
                rows.extend(r)
                stress.extend(s)
            if n % 20 == 0 or n == len(jobs):
                write_json(out / "progress.json", {"coins_finished": n, "coins_planned": len(jobs), "coins_failed": len(failures), "strategy_window_runs": len(rows), "stress_runs": len(stress), "elapsed_seconds": time.monotonic()-started})
                print(f"Completed {n}/{len(jobs)} coins; errors={len(failures)}; windows={len(rows)}; stresses={len(stress)}; elapsed={time.monotonic()-started:.1f}s", flush=True)
    pd.DataFrame(rows).sort_values(["symbol", "case_id", "window"]).to_csv(out / "summary.csv", index=False)
    pd.DataFrame(stress).sort_values(["symbol", "case_id", "scenario"]).to_csv(out / "stress.csv", index=False)
    write_json(out / "execution_failures.json", failures)
    done = set(r["symbol"] for r in rows)
    scope.loc[scope.symbol.isin(done), "status"] = "REPLAY_COMPLETED"
    scope.loc[scope.symbol.isin([r["symbol"] for r in failures]), "status"] = "EXECUTION_FAILED"
    scope.to_csv(out / "scope.csv", index=False)
    assert all(sha(ROOT / path) == digest for path, digest in old_hashes.items()), "An original file changed during the run"
    complete = not failures and len(done) == 611 and len(rows) == 1689 and len(stress) == 1222
    write_json(out / "completion.json", {"complete": complete, "coins_completed": len(done), "coins_failed": len(failures),
               "price_excluded": int((scope.cohort == "excluded").sum()), "strategy_window_runs": len(rows), "stress_runs": len(stress),
               "buyhold_runs": 0, "v1_runs": 0, "v3_runs": 0, "hype_full_simulations": 1,
               "old_files_verified_unchanged_after_run": True, "seconds": time.monotonic()-started})
    write_json(out / "artifact_checksums.json", {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()})
    if not complete:
        raise RuntimeError("Incomplete V2 execution retained; no silent exclusion")
    print(f"COMPLETE {len(done)} coins, {len(rows)} strategy-window rows, {len(stress)} stress rows", flush=True)


if __name__ == "__main__":
    main()
