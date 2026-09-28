"""本轮 Top10 生命周期诊断的固定组合价格入口；不计算信号或收益。"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time
from typing import Any

import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
LAB = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(LAB / "src"))

from strategy_lab.data import catalog, research_bundle, research_inputs
from strategy_lab.data.research_bundle import read_bundle_contract, read_json, require_research_startup

REQUEST_PATH = FAMILY / "specs/lifecycle-input-request-20260908.json"
BUNDLE_SHA256 = "d2a729d03be71d67aa9c5522fb242bbf010b6c64400233c27d9cb2406f567008"
COMPACT_COLUMNS = [
    "ts", "symbol", "open", "high", "low", "close", "volume", "quote_volume",
    "trade_count", "is_closed", "observed_valid", "identity_verified", "eligible",
    "research_segment_id", "research_window_valid",
]


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")


def source_hashes() -> dict[str, str]:
    paths = [Path(__file__), REQUEST_PATH, Path(research_bundle.__file__),
             Path(catalog.__file__), Path(research_inputs.__file__)]
    return {str(path.relative_to(LAB)): sha(path) for path in paths}


def load_inputs(request: dict) -> Any:
    """唯一湖价格读取：消费本次治理入口返回帧，不读取其他家族/缓存。"""
    return require_research_startup(request, project_root=LAB, data_root=LAB / "data")


def validate_frozen_request(request: dict) -> dict:
    expected = {
        "bundle_sha256": BUNDLE_SHA256,
        "mode": "price_diagnostic", "timeframe": "1d",
        "start": "2019-09-09T00:00:00Z", "end": "2026-09-05T00:00:00Z",
        "gap_policy": "contiguous_segments", "asset_policy": "observed_mixed_diagnostic",
        "backward_bars": 1, "forward_bars": 0,
    }
    for key, value in expected.items():
        if request.get(key) != value:
            raise ValueError(f"Frozen lifecycle input request changed: {key}")
    bundle, _ = read_bundle_contract(LAB, pin={
        key: request[key] for key in ("bundle_path", "bundle_id", "bundle_sha256")
    })
    symbols = request.get("symbols")
    if symbols != sorted(bundle["observed_asset_classes"]) or len(symbols) != 874:
        raise ValueError("Request must retain the full sorted 874-symbol observed inventory")
    return bundle


def run(out: Path) -> tuple[pd.DataFrame, dict]:
    """输出为本次 API 返回帧的列投影，无筛行、插值、补零或频率转换。"""
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite retained input run: {out}")
    request = read_json(REQUEST_PATH)
    bundle = validate_frozen_request(request)
    initial_hashes = source_hashes()
    versions = {}
    for name in ("pandas", "pyarrow", "duckdb", "numpy"):
        versions[name] = importlib.metadata.version(name)
    started = time.monotonic()
    save_json(out / "started.json", {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "PRICE_INPUT_ONLY_NO_SIGNAL_NO_RETURN_CALCULATION",
        "request_path": str(REQUEST_PATH.relative_to(LAB)),
        "request_sha256": sha(REQUEST_PATH), "source_sha256": initial_hashes,
        "dependencies": versions, "python": sys.version, "executable": sys.executable,
        "requested_symbols": 874, "batch_size": 128,
        "retention_class": "regenerable-local-dataset; do not add parquet to ordinary Git",
    })
    coverage = {symbol: {
        "symbol": symbol, "observed_asset_class": bundle["observed_asset_classes"][symbol],
        "status": "NOT_PROCESSED", "rows": 0, "eligible_rows": 0,
        "research_window_valid_rows": 0, "frame_saved": False, "error": "",
    } for symbol in request["symbols"]}
    frames = []
    all_receipts = []
    for offset in range(0, 874, 128):
        remaining = request["symbols"][offset:offset + 128]
        attempt = 0
        while remaining:
            label = f"batch-{offset:04d}-attempt-{attempt:02d}"
            batch = dict(request, symbols=list(remaining))
            req_path = out / "requests" / f"{label}.json"
            save_json(req_path, batch)
            receipt = {"request_path": str(req_path.relative_to(out)),
                       "request_sha256": sha(req_path), "requested_symbols": len(remaining)}
            print(f"STARTUP {label} n={len(remaining)} elapsed={time.monotonic()-started:.1f}s", flush=True)
            try:
                inputs = load_inputs(batch)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                failure_path = out / "startup-failures" / f"{label}.json"
                save_json(failure_path, {**receipt, "error": error, "symbols": remaining,
                                         "fallback_used": False})
                receipt.update(status="FAILED", failure_path=str(failure_path.relative_to(out)),
                               failure_sha256=sha(failure_path))
                all_receipts.append(receipt)
                # Only an error explicitly identifying one symbol may be isolated.
                # The rejected symbol remains in the frozen universe and coverage table.
                # Global bundle/hash/schema failures cannot be repaired by excluding names.
                isolated = [s for s in remaining if str(exc).startswith(f"{s}:")]
                if not isinstance(exc, ValueError) or len(isolated) != 1:
                    raise
                rejected = isolated[0]
                coverage[rejected].update(status="SYMBOL_STARTUP_REJECTED", error=error,
                                           startup_evidence=receipt["failure_path"])
                print(f"EXPLICIT_SYMBOL_REJECTION {rejected} {error}", flush=True)
                remaining = [symbol for symbol in remaining if symbol != rejected]
                attempt += 1
                continue
            if set(inputs.prices) != set(remaining):
                raise ValueError("Startup returned an unexpected symbol inventory")
            if inputs.report["status"] != "PRICE_DIAGNOSTIC_INPUTS_VERIFIED":
                raise ValueError("Unexpected startup mode/status")
            if any(inputs.report[key] is not False for key in (
                "funding_window_verified", "pit_universe_proven", "tradability_proven", "strategy_approved"
            )):
                raise ValueError("Price input report must not approve funding/PIT/tradability/strategy")
            report_path = out / "startup-reports" / f"{label}.json"
            save_json(report_path, inputs.report)
            receipt.update(status=inputs.report["status"], report_path=str(report_path.relative_to(out)),
                           report_sha256=sha(report_path))
            all_receipts.append(receipt)
            for symbol in remaining:
                frame = inputs.prices[symbol]
                missing = set(COMPACT_COLUMNS) - set(frame)
                if missing:
                    raise ValueError(f"Returned frame lacks compact fields: {symbol} {sorted(missing)}")
                compact = frame.loc[:, COMPACT_COLUMNS].copy()
                if compact.empty or not compact.symbol.eq(symbol).all():
                    raise ValueError(f"Returned frame is empty or mixed: {symbol}")
                frames.append(compact)
                coverage[symbol].update(
                    status="PRICE_DIAGNOSTIC_INPUTS_VERIFIED", rows=len(frame),
                    eligible_rows=int(frame.eligible.sum()),
                    research_window_valid_rows=int(frame.research_window_valid.sum()),
                    observed_valid_rows=int(frame.observed_valid.sum()),
                    identity_verified_rows=int(frame.identity_verified.sum()),
                    ineligible_rows=int((~frame.eligible).sum()),
                    eligible_segments=int(frame.research_segment_id.nunique()),
                    first_open_utc=frame.ts.min().isoformat(), last_open_utc=frame.ts.max().isoformat(),
                    frame_saved=True, startup_evidence=receipt["report_path"],
                    dataframe_projection_sha256=hashlib.sha256(
                        pd.util.hash_pandas_object(compact, index=False).values.tobytes()
                    ).hexdigest(),
                )
            del inputs
            remaining = []
        print(f"PROGRESS resolved={offset+len(request['symbols'][offset:offset+128])}/874 "
              f"returned={len(frames)} elapsed={time.monotonic()-started:.1f}s", flush=True)
    if source_hashes() != initial_hashes:
        raise ValueError("Loader/request/source changed during startup; refusing final result")
    if any(row["status"] == "NOT_PROCESSED" for row in coverage.values()):
        raise ValueError("Unaccounted frozen symbols")
    if not frames:
        raise ValueError("No eligible symbol frames returned")
    daily = pd.concat(frames, ignore_index=True)
    if daily.duplicated(["symbol", "ts"]).any():
        raise ValueError("Duplicate returned symbol/open time")
    # Sorting only changes presentation, never segment membership or valid-window masks.
    daily = daily.sort_values(["symbol", "ts"], kind="stable").reset_index(drop=True)
    parquet = out / "daily-returned-frames.parquet"
    daily.to_parquet(parquet, index=False, compression="zstd", compression_level=9)
    if parquet.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Compact regenerated artifact exceeds frozen 50 MiB limit")
    coverage_path = out / "symbol-coverage.csv"
    pd.DataFrame(list(coverage.values())).to_csv(coverage_path, index=False)
    statuses = dict(Counter(row["status"] for row in coverage.values()))
    rejected = [symbol for symbol, row in coverage.items() if not row["frame_saved"]]
    summary = {
        "status": "PRICE_DIAGNOSTIC_INPUTS_VERIFIED" if not rejected else "PRICE_DIAGNOSTIC_PARTIAL_EXPLICIT_REJECTIONS",
        "purpose": "Returned 1d frame projection for Top10 lifecycle diagnosis; no alpha/backtest result",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.monotonic() - started,
        "request_path": str(REQUEST_PATH.relative_to(LAB)), "request_sha256": sha(REQUEST_PATH),
        "request": request, "source_sha256": initial_hashes,
        "dataset_component": bundle["components"]["1d"],
        "requested_symbols": 874, "returned_symbols": len(frames), "rejected_symbols": rejected,
        "status_counts": statuses, "rows": len(daily),
        "eligible_rows": int(daily.eligible.sum()),
        "research_window_valid_rows": int(daily.research_window_valid.sum()),
        "ineligible_rows_retained": int((~daily.eligible).sum()),
        "parquet_path": parquet.name, "parquet_sha256": sha(parquet),
        "parquet_bytes": parquet.stat().st_size, "columns": list(daily.columns),
        "coverage_path": coverage_path.name, "coverage_sha256": sha(coverage_path),
        "startup_receipts": all_receipts,
        "all_requested_symbols_accounted": True,
        "all_requested_symbols_passed": not rejected,
        "source_unchanged_during_run": True,
        "funding_window_verified": False, "pit_universe_proven": False,
        "tradability_proven": False, "strategy_approved": False,
        "known_limits": [
            "Mixed observed inventory is not a historical PIT universe or proof of tradability.",
            "Missing dates were not inserted; ineligible returned rows were not dropped.",
            "Any derived feature/label must respect research_segment_id and complete window lengths.",
            "Symbols wholly rejected by startup have explicit failure receipts and no consumable frame.",
            "This local parquet is a reproducible projection of this run's API frames, not a new trusted lake dataset.",
        ],
    }
    save_json(out / "summary.json", summary)
    print(json.dumps({key: summary[key] for key in (
        "status", "returned_symbols", "rejected_symbols", "rows", "eligible_rows", "parquet_bytes", "elapsed_seconds"
    )}, ensure_ascii=False), flush=True)
    return daily, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="lifecycle-inputs-20260908")
    args = parser.parse_args()
    if Path(args.run_id).name != args.run_id or args.run_id in (".", "..", ""):
        raise ValueError("run-id must be one directory basename")
    run(FAMILY / "artifacts" / args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
