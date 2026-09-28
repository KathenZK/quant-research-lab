"""Nine fixed four-question experiments on frozen, verified family inputs."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

from common import BASE, INPUT, RESULTS, ROOT, sha, write_json
from run_market import load_selected_frames, period_windows, save_result, select_scope, verify_inputs

CONTRACT = BASE / "specs/contract-four-tests-20260910.md"
ENGINE_PIN = BASE / "specs/four-tests-engine-pin-20260910.json"
OUTPUT = BASE / "artifacts/results_four_tests_20260910"
INPUT_SHA = "a2390b002883506a8f39522a31e708e76346e21be6a0a598e753b4a5b5e4891c"
OLD_RESULT_SHA = "880d7201b4c23695265d80d2704e0ec03245dfdb8a274b50873f82fbfb50a13d"


def load_new_engine():
    pin = json.loads(ENGINE_PIN.read_text())
    path = ROOT / pin["engine_path"]
    assert sha(path) == pin["engine_sha256"], "Pinned v2 engine changed"
    name = "ma7_car_four_tests_shared_v2"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def cases():
    e = load_new_engine()
    base = e.Config(reverse=False, progress_days=4, progress_source="high_low")
    return [
        ("A_LONG", "只做多", replace(base, direction_mode="long")),
        ("A_SHORT", "只做空·保留提前止盈", replace(base, direction_mode="short")),
        ("A_SHORT_NO_TP", "只做空·取消提前止盈", replace(base, direction_mode="short", short_exit="none")),
        ("B_MA30_READY", "MA30额外预热对照", replace(base, trend_filter="ma30_ready")),
        ("B_MA30", "MA30方向过滤", replace(base, trend_filter="ma30_direction")),
        ("C_RISK005", "每笔计划风险0.5%", replace(base, risk_fraction=.005)),
        ("C_SMALL", "固定1/30名义仓位", replace(base, notional_fraction=1 / 30)),
        ("D_RESET", "创新高低后重新等待4天收紧", replace(base, progress_policy="reset_on_new_extreme")),
        ("D_NO_TP", "双向·取消空单提前止盈", replace(base, short_exit="none")),
    ]


def verify_reused():
    assert sha(INPUT / "checksums.json") == INPUT_SHA
    assert sha(RESULTS / "artifact_checksums.json") == OLD_RESULT_SHA
    hashes = json.loads((RESULTS / "artifact_checksums.json").read_text())
    files = ["summary.csv", "stress.csv", "buy_hold.csv", "scope.csv", "completion.json", "run_manifest.json"]
    result = {}
    for rel in files:
        actual = sha(RESULTS / rel)
        assert actual == hashes[rel], "Changed original result: " + rel
        result[str((RESULTS / rel).relative_to(ROOT))] = actual
    complete = json.loads((RESULTS / "completion.json").read_text())
    assert complete["complete"] and complete["coins_completed"] == 611 and not complete["coins_failed"]
    return result


def enrich_and_check(engine, old_features):
    new = engine.enrich_features(engine.features(old_features))
    for key in ["timestamp", "ma", "atr", "rsi", "slope", "cross", "ready"]:
        pd.testing.assert_series_equal(old_features[key], new[key], check_exact=True)
    return new


def save_account(engine, directory, hourly, daily, cfg, lo, hi, carry):
    events = []
    result = engine.simulate(hourly, daily, cfg, pd.Timestamp(lo), pd.Timestamp(hi),
                             None, carry, entry_events=events)
    summary = result[0]
    assert pd.Timestamp(summary["start"]) == pd.Timestamp(lo)
    assert pd.Timestamp(summary["end_exclusive"]) == pd.Timestamp(hi)
    save_result(directory, result)
    event_frame = pd.DataFrame(events).reindex(columns=engine.ENTRY_EVENT_COLUMNS)
    event_frame.to_csv(directory / "entry_events.csv", index=False)
    return summary


def replay_coin(item, frame_manifest, out_string, configurations):
    out = Path(out_string)
    h, old, source = load_selected_frames(item, frame_manifest)
    engine = load_new_engine()
    d = enrich_and_check(engine, old)
    windows = period_windows(item)
    metadata = out / "inputs_used" / (item["slug"] + ".json")
    write_json(metadata, {**item, "windows": windows, "input_source": source,
                          "market_source": str((RESULTS / "market" / item["slug"]).relative_to(ROOT)),
                          "original_features_exact": True,
                          "ma30_ready_rule": "SMA30 and preceding SMA30 both finite within the selected continuous segment; entry only"})
    rows, stresses = [], []
    for cid, label, config in configurations:
        cfg = engine.Config(**config)
        for window, (lo, hi) in windows.items():
            summary = save_account(engine, out / "runs" / item["slug"] / cid / window,
                                   h, d, cfg, lo, hi, 0.)
            rows.append({"symbol": item["symbol"], "slug": item["slug"], "cohort": item["cohort"],
                         "trade_days": item["trade_days"], "case_id": cid, "label": label,
                         "window": window, **summary})
        lo, hi = windows["full"]
        for scenario, altered, carry in [("slippage_10bp", replace(cfg, slip=.001), 0.),
                                          ("carry_5bp_day", cfg, .0005)]:
            summary = save_account(engine, out / "sensitivity" / item["slug"] / cid / scenario,
                                   h, d, altered, lo, hi, carry)
            stresses.append({"symbol": item["symbol"], "slug": item["slug"], "cohort": item["cohort"],
                             "trade_days": item["trade_days"], "case_id": cid, "label": label,
                             "scenario": scenario, **summary})
    return rows, stresses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        parser.error("Use a fresh output directory; prior results may not be overwritten")
    started = time.monotonic()
    old_hashes = verify_reused()
    plan = verify_inputs()
    scope = select_scope()
    old_scope = pd.read_csv(RESULTS / "scope.csv", float_precision="round_trip")
    for column in scope.columns:
        if column == "status":
            continue
        a, b = scope[column], old_scope[column]
        assert a.isna().equals(b.isna()), "Scope missingness differs: " + column
        valid = a.notna()
        assert a[valid].astype(str).equals(b[valid].astype(str)), "Scope changed: " + column
    assert scope.cohort.value_counts().to_dict() == {"main_full": 346, "partial": 193, "short": 72, "excluded": 41}
    frame_manifest = json.loads((INPUT / "frames_manifest.json").read_text())
    configurations = [(cid, label, asdict(cfg)) for cid, label, cfg in cases()]
    assert len(configurations) == 9 and len({cid for cid, _, _ in configurations}) == 9
    pin = json.loads(ENGINE_PIN.read_text())
    assert sha(CONTRACT) == pin["contract_sha256"], "Contract changed after engine validation"
    out.mkdir(parents=True)
    scope.to_csv(out / "scope.csv", index=False)
    write_json(out / "run_manifest.json", {
        "family_id": "BIN-1D-MA7-CAR-GEN", "round": "FOUR_TESTS_20260910",
        "created_before_new_strategy_results_utc": str(pd.Timestamp.now(tz="UTC")),
        "contract_path": str(CONTRACT.relative_to(ROOT)), "contract_sha256": sha(CONTRACT),
        "engine_pin_path": str(ENGINE_PIN.relative_to(ROOT)), "engine_pin_sha256": sha(ENGINE_PIN),
        "engine_path": pin["engine_path"], "engine_sha256": pin["engine_sha256"],
        "run_script_path": str(Path(__file__).relative_to(ROOT)), "run_script_sha256": sha(Path(__file__)),
        "common_sha256": sha(Path(__file__).with_name("common.py")),
        "run_market_sha256": sha(Path(__file__).with_name("run_market.py")),
        "input_checksums_sha256": INPUT_SHA, "input_plan": plan,
        "input_plan_sha256": sha(INPUT / "frozen_plan.json"),
        "original_result_manifest_sha256": OLD_RESULT_SHA, "verified_original_files": old_hashes,
        "cases": [{"case_id": cid, "label": label, "config": cfg} for cid, label, cfg in configurations],
        "reused_without_market_replay": {"V3": "H4_D0", "V1": "F0", "buy_hold": "BUY_HOLD"},
        "observed_coins": len(scope), "cohort_counts": scope.cohort.value_counts().to_dict(),
        "strategy_window_runs_planned": 1689 * 9, "stress_runs_planned": 1222 * 9,
        "funding_window_verified": False, "pit_universe_proven": False,
        "classification": "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS", "portfolio_replay": False,
        "workers": args.workers,
    })
    candidates = scope[scope.cohort != "excluded"].to_dict("records")
    rows, stresses, failures = [], [], []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(replay_coin, item,
                            {"main/" + item["symbol"]: frame_manifest["main/" + item["symbol"]]},
                            str(out), configurations): item for item in candidates}
        for n, future in enumerate(as_completed(jobs), 1):
            item = jobs[future]
            try:
                r, s = future.result()
            except Exception as exc:
                failures.append({"symbol": item["symbol"], "slug": item["slug"],
                                 "error_type": type(exc).__name__, "error": str(exc)})
                write_json(out / "execution_failures.json", failures)
                print("FAILED " + item["symbol"] + ": " + repr(exc), flush=True)
            else:
                rows.extend(r)
                stresses.extend(s)
            if n % 20 == 0 or n == len(jobs):
                state = {"coins_finished": n, "coins_planned": len(jobs), "coins_failed": len(failures),
                         "strategy_window_runs": len(rows), "stress_runs": len(stresses),
                         "elapsed_seconds": time.monotonic() - started}
                write_json(out / "progress.json", state)
                print(json.dumps(state), flush=True)
    pd.DataFrame(rows).sort_values(["symbol", "case_id", "window"]).to_csv(out / "summary.csv", index=False)
    pd.DataFrame(stresses).sort_values(["symbol", "case_id", "scenario"]).to_csv(out / "stress.csv", index=False)
    write_json(out / "execution_failures.json", failures)
    done = {r["symbol"] for r in rows}
    failed = {r["symbol"] for r in failures}
    scope.loc[scope.symbol.isin(done), "status"] = "REPLAY_COMPLETED"
    scope.loc[scope.symbol.isin(failed), "status"] = "EXECUTION_FAILED"
    scope.to_csv(out / "scope.csv", index=False)
    for relative, digest in old_hashes.items():
        assert sha(ROOT / relative) == digest, "Original changed: " + relative
    assert sha(ROOT / pin["engine_path"]) == pin["engine_sha256"]
    complete = not failures and len(done) == 611 and len(rows) == 1689 * 9 and len(stresses) == 1222 * 9
    write_json(out / "completion.json", {"complete": complete, "coins_completed": len(done),
               "coins_failed": len(failures), "price_excluded": 41, "new_cases": 9,
               "strategy_window_runs": len(rows), "stress_runs": len(stresses), "buyhold_runs": 0,
               "old_v1_v3_market_runs": 0, "old_files_verified_unchanged": True,
               "seconds": time.monotonic() - started})
    write_json(out / "artifact_checksums.json", {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()})
    if not complete:
        raise RuntimeError("Incomplete four-question replay; failures retained, no silent deletion")
    print(f"COMPLETE: {len(done)} coins, {len(rows)} windows, {len(stresses)} stresses", flush=True)


if __name__ == "__main__":
    main()
