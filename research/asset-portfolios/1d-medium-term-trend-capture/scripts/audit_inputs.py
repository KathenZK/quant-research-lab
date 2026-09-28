"""MTTC P0：两阶段可信价格启动与过去窗口覆盖；不构造信号或标签。"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time
from typing import Any, Iterator

FAMILY = Path(__file__).resolve().parents[1]
LAB = Path("/Users/ZK/OpenCode/quant-strategy-lab")
sys.path.insert(0, str(LAB / "src"))

import pandas as pd  # noqa: E402 - explicit formal-Lab code root is established above
from strategy_lab.data.research_bundle import read_bundle_contract, require_research_startup  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite retained evidence: {path}")
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def load_inputs(request: dict) -> Any:
    """唯一研究价格读取入口；消费本次 API 返回帧，绝不回退旧家族。"""
    return require_research_startup(request, project_root=LAB, data_root=LAB / "data")


def verify_source_pins(pins: dict) -> dict[str, str]:
    for key, expected in (("formal_lab", LAB), ("data_root", LAB / "data")):
        if key in pins and Path(pins[key]).resolve() != expected.resolve():
            raise ValueError(f"{key} differs from explicit formal Lab root")
    files = pins.get("files")
    if not isinstance(files, dict):
        raise ValueError("source-pins.json requires a files mapping")
    verified = {}
    for relative, expected in files.items():
        if not isinstance(relative, str) or not relative.startswith("src/"):
            continue
        path = (LAB / relative).resolve()
        if not path.is_relative_to((LAB / "src").resolve()):
            raise ValueError(f"Source pin escapes src: {relative}")
        actual = sha(path)
        if actual != expected:
            raise ValueError(f"Pinned source changed: {relative}")
        verified[relative] = actual
    if not verified:
        raise ValueError("No src files pinned; refusing unpinned startup")
    return verified


def load_batch(
    request: dict, out: Path, stage: str, label: str
) -> Iterator[tuple[str, pd.DataFrame | None, dict, str | None]]:
    """失败请求留证并按标的二分；不改变 mode、数据版本或其他范围。"""
    request_path = out / "requests" / f"{stage}-{label}.json"
    save_json(request_path, request)
    receipt = {
        "request_path": str(request_path.relative_to(out)),
        "request_sha256": sha(request_path),
    }
    try:
        inputs = load_inputs(request)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        failure_path = out / "startup-failures" / f"{stage}-{label}.json"
        save_json(failure_path, {
            **receipt, "stage": stage, "symbols": request["symbols"],
            "error": error, "fallback_used": False,
        })
        print(f"STARTUP_REJECTED {stage} {label} n={len(request['symbols'])} {error}", flush=True)
        # A bundle/hash/code failure is global: splitting symbols cannot repair it.
        # Only an explicitly symbol-scoped validation error may be isolated.
        if not isinstance(exc, ValueError) or not any(
            f"{symbol}:" in str(exc) for symbol in request["symbols"]
        ):
            raise
        if len(request["symbols"]) == 1:
            yield request["symbols"][0], None, receipt, error
        else:
            midpoint = len(request["symbols"]) // 2
            for suffix, symbols in (
                ("L", request["symbols"][:midpoint]),
                ("R", request["symbols"][midpoint:]),
            ):
                yield from load_batch(dict(request, symbols=symbols), out, stage, label + suffix)
        return
    if set(inputs.prices) != set(request["symbols"]):
        raise ValueError("Trusted startup returned a different symbol set")
    report_path = out / "startup-reports" / f"{stage}-{label}.json"
    save_json(report_path, inputs.report)
    receipt.update(
        startup_report_path=str(report_path.relative_to(out)),
        startup_report_sha256=sha(report_path),
    )
    for symbol in request["symbols"]:
        yield symbol, inputs.prices[symbol], receipt, None


def frame_summary(frame: pd.DataFrame, symbol: str, stage: str) -> tuple[dict, list[dict]]:
    groups = [
        g for _, g in frame.loc[frame.eligible].groupby("research_segment_id", sort=False)
    ]
    segments = [{
        "stage": stage, "symbol": symbol,
        "research_segment_id": str(g.research_segment_id.iloc[0]),
        "bars": len(g), "first_open": g.ts.iloc[0], "last_open": g.ts.iloc[-1],
        "complete_past_windows": int(g.research_window_valid.sum()),
    } for g in groups]
    stats = {
        "rows": len(frame), "eligible_bars": int(frame.eligible.sum()),
        "observed_valid_bars": int(frame.observed_valid.sum()),
        "identity_verified_bars": int(frame.identity_verified.sum()),
        "complete_past_windows": int(frame.research_window_valid.sum()),
        "max_segment_bars": max((len(g) for g in groups), default=0),
        "segments": len(groups), "first_open": frame.ts.iloc[0],
        "last_open": frame.ts.iloc[-1],
    }
    return stats, segments


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="p0-inputs")
    args = parser.parse_args()
    if not args.run_id or Path(args.run_id).name != args.run_id or args.run_id in (".", ".."):
        raise ValueError("run-id must be one output directory name")
    out = FAMILY / "artifacts" / args.run_id
    if out.exists():
        raise FileExistsError(f"Retained run exists; choose a new run-id: {out}")

    request_path = FAMILY / "specs" / "input-request.json"
    pins_path = FAMILY / "specs" / "source-pins.json"
    contract_path = FAMILY / "specs" / "input-contract.md"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    pins = json.loads(pins_path.read_text(encoding="utf-8"))
    if (request.get("mode") != "price_diagnostic" or request.get("timeframe") != "1d"
            or request.get("backward_bars") != 60 or request.get("forward_bars") != 0
            or request.get("gap_policy") != "contiguous_segments"):
        raise ValueError("MTTC P0 requires frozen 1d price_diagnostic contiguous_segments backward=60 forward=0")
    symbols = request.get("symbols")
    if not isinstance(symbols, list) or not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("Frozen request requires explicit unique symbols")
    verified_sources = verify_source_pins(pins)
    bundle, pin = read_bundle_contract(LAB, pin={
        k: request[k] for k in ("bundle_path", "bundle_id", "bundle_sha256")
    })
    expected_symbols = sorted(s for s, c in bundle["observed_asset_classes"].items() if c == "COIN")
    if len(expected_symbols) != 652 or symbols != expected_symbols:
        raise ValueError("MTTC P0 requires the full sorted 652-COIN pinned observed inventory")
    if (request.get("asset_policy") != "crypto_only"
            or request.get("start") != "2019-09-09T00:00:00Z"
            or request.get("end") != "2026-09-05T00:00:00Z"):
        raise ValueError("MTTC P0 frozen asset policy or time range changed")
    universe_path = FAMILY / "specs" / "observed-universe.json"
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    if (universe["included"] != symbols
            or universe["bundle_sha256"] != request["bundle_sha256"]
            or pins["files"].get(request["bundle_path"]) != request["bundle_sha256"]):
        raise ValueError("Observed universe or source pins differ from fixed request")

    frozen_files = {
        "specs/input-request.json": sha(request_path),
        "specs/source-pins.json": sha(pins_path),
        "specs/observed-universe.json": sha(universe_path),
        "specs/input-contract.md": sha(contract_path),
        "scripts/audit_inputs.py": sha(Path(__file__)),
    }
    versions = {}
    for name in ("numpy", "pandas", "duckdb", "pyarrow", "scipy"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "unavailable"
    started = time.time()
    save_json(out / "started.json", {
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "trusted input coverage and past-only windows; no signals or labels",
        "python": sys.version, "executable": sys.executable,
        "dependencies": versions, "family_files_sha256": frozen_files,
        "verified_src_files": verified_sources, "bundle_pin": pin,
        "requested_symbols": len(symbols), "batch_size": 128,
        "survey_backward_bars": 1, "research_backward_bars": 60, "forward_bars": 0,
    })

    coverage = {s: {
        "symbol": s, "asset_class": bundle["observed_asset_classes"][s],
        "status": "NOT_PROCESSED", "stage1_status": "NOT_STARTED",
        "stage2_status": "NOT_STARTED", "qualifies_past60": False,
        "frame_saved": False, "stage1_error": "", "stage2_error": "",
    } for s in symbols}
    all_segments = []
    manifest = {}
    for offset in range(0, len(symbols), 128):
        batch_symbols = symbols[offset:offset + 128]
        batch_label = f"b{offset:04d}"
        survey = dict(request, symbols=batch_symbols, backward_bars=1, forward_bars=0)
        qualified = []
        print(f"SURVEY {batch_label} n={len(batch_symbols)} elapsed={time.time()-started:.1f}s", flush=True)
        for symbol, frame, receipt, error in load_batch(survey, out, "survey", batch_label):
            row = coverage[symbol]
            if frame is None:
                row.update(status="COVERAGE_STARTUP_FAILED", stage1_status="FAILED",
                           stage1_error=error, stage2_status="NOT_REQUESTED")
                continue
            stats, segments = frame_summary(frame, symbol, "survey")
            row.update({f"stage1_{k}": v for k, v in stats.items()})
            row["stage1_status"] = "PRICE_DIAGNOSTIC_INPUTS_VERIFIED"
            row["stage1_report"] = receipt["startup_report_path"]
            all_segments.extend(segments)
            if stats["max_segment_bars"] < 60:
                row.update(status="INSUFFICIENT_CONTIGUOUS_PAST_60",
                           stage2_status="NOT_REQUESTED")
            else:
                row["qualifies_past60"] = True
                qualified.append(symbol)
        print(f"RESEARCH {batch_label} qualified={len(qualified)}/{len(batch_symbols)}", flush=True)
        if qualified:
            research_request = dict(request, symbols=qualified)
            for symbol, frame, receipt, error in load_batch(research_request, out, "research", batch_label):
                row = coverage[symbol]
                if frame is None:
                    row.update(status="RESEARCH_STARTUP_FAILED", stage2_status="FAILED", stage2_error=error)
                    continue
                stats, segments = frame_summary(frame, symbol, "research")
                if stats["complete_past_windows"] <= 0:
                    raise ValueError(f"Research startup returned no valid past window: {symbol}")
                row.update({f"stage2_{k}": v for k, v in stats.items()})
                row.update(status="PRICE_DIAGNOSTIC_INPUTS_VERIFIED",
                           stage2_status="PRICE_DIAGNOSTIC_INPUTS_VERIFIED",
                           stage2_report=receipt["startup_report_path"])
                all_segments.extend(segments)
                # Hash-derived filenames avoid symbol/path ambiguity without changing identity.
                basename = hashlib.sha256(symbol.encode("utf-8")).hexdigest() + ".pkl.gz"
                frame_path = out / "returned-frames" / basename
                frame_path.parent.mkdir(parents=True, exist_ok=True)
                if frame_path.exists():
                    raise FileExistsError(f"Duplicate frame output: {frame_path}")
                frame.to_pickle(frame_path, compression="gzip")
                manifest[symbol] = {
                    "path": str(frame_path.relative_to(out)), "sha256": sha(frame_path),
                    "dataframe_hash": hashlib.sha256(
                        pd.util.hash_pandas_object(frame, index=True).values.tobytes()
                    ).hexdigest(),
                    "rows": len(frame), "columns": list(frame.columns),
                    "complete_past_windows": stats["complete_past_windows"],
                    "asset_class": row["asset_class"], "stage": "research",
                    "backward_bars": 60, "forward_bars": 0, **receipt,
                }
                row["frame_saved"] = True
        print(f"PROGRESS audited={offset+len(batch_symbols)}/{len(symbols)} saved={len(manifest)} elapsed={time.time()-started:.1f}s", flush=True)

    source_unchanged = verify_source_pins(pins) == verified_sources
    changed_family_files = [relative for relative, digest in frozen_files.items()
                            if sha(FAMILY / relative) != digest]
    rows = [coverage[s] for s in symbols]
    pd.DataFrame(rows).to_csv(out / "coverage.csv", index=False)
    pd.DataFrame(all_segments, columns=[
        "stage", "symbol", "research_segment_id", "bars", "first_open", "last_open",
        "complete_past_windows",
    ]).to_csv(out / "segments.csv", index=False)
    save_json(out / "frame-manifest.json", manifest)
    counts = dict(Counter(row["status"] for row in rows))
    failed = sum(row["stage1_status"] == "FAILED" or row["stage2_status"] == "FAILED" for row in rows)
    complete = bool(manifest) and failed == 0 and source_unchanged and not changed_family_files
    summary = {
        "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "seconds": time.time() - started,
        "status": "PRICE_INPUTS_READY_WITH_RECORDED_EXCLUSIONS" if complete else "INPUT_AUDIT_INCOMPLETE",
        "requested_symbols": len(symbols), "frames": len(manifest),
        "status_counts": counts, "startup_failed_symbols": failed,
        "source_pins_unchanged": source_unchanged, "changed_family_files": changed_family_files,
        "frame_manifest_sha256": sha(out / "frame-manifest.json"),
        "coverage_sha256": sha(out / "coverage.csv"), "segments_sha256": sha(out / "segments.csv"),
        "saved_frames_source": "second require_research_startup return only",
        "funding_window_verified": False, "pit_universe_proven": False,
        "tradability_proven": False, "signals_computed": False, "labels_computed": False,
        "old_family_frames_read": False, "data_lake_written": False,
    }
    save_json(out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
