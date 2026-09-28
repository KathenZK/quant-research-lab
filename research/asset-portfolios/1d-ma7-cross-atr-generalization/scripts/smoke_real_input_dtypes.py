"""Exercise real Arrow inputs through joint segments, persistence and runner loading."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import prepare_inputs_v4 as prep
import run_market
from startup_batch import create_startup_context, require_research_startup_batch

FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/input_dtype_smoke_20260909"
SYMBOLS = ["BTC/USDT:USDT", "HYPE/USDT:USDT", "0G/USDT:USDT", "1000BONK/USDT:USDT", "USDC/USDT:USDT"]


def load_test_frames(plan):
    if OUT.exists():
        raise FileExistsError(OUT)
    OUT.mkdir(parents=True)
    window = plan["windows"][0]
    context = create_startup_context(project_root=prep.LAB, data_root=prep.LAB / "data",
        pin=plan["bundle_pin"], symbols=SYMBOLS, start=window["input_start"], end=window["end"])
    frames, manifest, items = {}, {}, []
    for tf, backward in (("1d", 29), ("1h", 1)):
        request = {"schema_version": 1, **plan["bundle_pin"], "mode": "price_diagnostic",
                   "timeframe": tf, "symbols": SYMBOLS, "start": window["input_start"], "end": window["end"],
                   "gap_policy": "contiguous_segments", "asset_policy": "crypto_only",
                   "backward_bars": backward, "forward_bars": 0}
        result = require_research_startup_batch(request, context=context)
        if result.failures:
            raise ValueError(result.failures)
        prep.save_json(OUT / f"startup_{tf}.json", result.report)
        for symbol, frame in result.prices.items():
            key, coin = f"main/{symbol}", symbol.split("/")[0]
            manifest.setdefault(key, {})[tf] = prep.save_frame(OUT, frame, f"returned/main/{tf}/{coin}.parquet", {})
            frames[symbol, tf] = frame
    for symbol in SYMBOLS:
        key, coin = f"main/{symbol}", symbol.split("/")[0]
        j, audit = prep.joint_daily_projection(frames[symbol, "1d"], frames[symbol, "1h"], 29)
        manifest[key]["joint_daily"] = prep.save_frame(OUT, j, f"joint/main/{coin}.parquet", {})
        reread = pd.read_parquet(OUT / manifest[key]["joint_daily"]["path"])
        pd.testing.assert_frame_equal(j, reread, check_exact=True)
        segments = prep.segment_rows(j, window, 29)
        selected = sorted(segments, key=lambda r: (-r["trade_days"], r["input_start"]))[0]
        items.append({**selected, "selected_segment_id": selected["segment_id"], "slug": coin,
                      "cohort": "main_full" if selected["full_window_contiguous"] else "partial",
                      "projection_audit": audit})
    prep.save_json(OUT / "manifest.json", manifest)
    prep.save_json(OUT / "items.json", items)
    prep.save_json(OUT / "context.json", context.receipt())
    prep.save_json(OUT / "checksums.json", {str(p.relative_to(OUT)): prep.sha(p) for p in sorted(OUT.rglob("*")) if p.is_file()})


def check_runner(label):
    manifest = json.loads((OUT / "manifest.json").read_text())
    items = json.loads((OUT / "items.json").read_text())
    for name, digest in json.loads((OUT / "checksums.json").read_text()).items():
        if prep.sha(OUT / name) != digest:
            raise ValueError("Smoke fixture changed")
    original_input = run_market.INPUT
    run_market.INPUT = OUT  # Test fixture routing only; no production/data API patch.
    records = []
    try:
        for item in items:
            try:
                h, feature, _ = run_market.load_selected_frames(item, manifest)
                record = {"symbol": item["symbol"], "runner_load": "PASS", "hourly_rows": len(h),
                          "daily_rows": len(feature), "ready_rows": int(feature.ready.sum()),
                          "ready_dtype": str(feature.ready.dtype)}
            except AssertionError as exc:
                d = pd.read_parquet(OUT / manifest[f"main/{item['symbol']}"]["joint_daily"]["path"])
                d = d[d.joint_segment_id == item["selected_segment_id"]].reset_index(drop=True).rename(columns={"ts": "timestamp"})
                feature = run_market.load_engine().features(d)
                record = {"symbol": item["symbol"], "runner_load": "FAIL", "error": str(exc),
                          "ready_dtype": str(feature.ready.dtype), "input_mask_dtype": str(d.research_window_valid.dtype),
                          "ready_values_equal": bool((feature.ready.to_numpy(bool) == d.research_window_valid.to_numpy(bool)).all()),
                          "atr_zero_rows": int(feature.atr.eq(0).sum()),
                          "warm_mask_atr_zero_rows": int((d.research_window_valid & feature.atr.eq(0)).sum())}
            records.append(record)
            print(record, flush=True)
    finally:
        run_market.INPUT = original_input
    report = {"status": "PASS" if all(r["runner_load"] == "PASS" for r in records) else "FAIL",
              "candidate_results_computed": False, "records": records,
              "prepare_v4_sha256": prep.sha(FAMILY / "scripts/prepare_inputs_v4.py"),
              "runner_sha256": prep.sha(FAMILY / "scripts/run_market.py")}
    prep.save_json(OUT / f"runner_check_{label}.json", report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--label", default="initial")
    args = parser.parse_args()
    if not args.check_only:
        load_test_frames(json.loads((FAMILY / "specs/input-plan-v4-20260909.json").read_text()))
    report = check_runner(args.label)
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
