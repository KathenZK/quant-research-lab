"""独立复核已落盘的本轮 API 返回帧投影；不重读湖、不计算收益。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
LAB = Path(__file__).resolve().parents[4]
OUT = FAMILY / "artifacts/lifecycle-inputs-20260908"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    summary = json.loads((OUT / "summary.json").read_text())
    frame = pd.read_parquet(OUT / summary["parquet_path"])
    coverage = pd.read_csv(OUT / summary["coverage_path"])
    request = summary["request"]
    checks = {
        "parquet_sha256": sha(OUT / summary["parquet_path"]) == summary["parquet_sha256"],
        "request_sha256": sha(LAB / summary["request_path"]) == summary["request_sha256"],
        "coverage_sha256": sha(OUT / summary["coverage_path"]) == summary["coverage_sha256"],
        "all_source_hashes": all(sha(LAB / path) == digest for path, digest in summary["source_sha256"].items()),
        "rows_match": len(frame) == summary["rows"] == 640378,
        "inventory_matches": sorted(frame.symbol.unique()) == request["symbols"] == sorted(coverage.symbol),
        "no_duplicate_keys": not frame.duplicated(["symbol", "ts"]).any(),
        "stable_symbol_ts_order": frame.equals(frame.sort_values(["symbol", "ts"], kind="stable").reset_index(drop=True)),
        "mask_equals_eligible_for_backward1_forward0": frame.research_window_valid.equals(frame.eligible),
        "invalid_segment_missing": frame.research_segment_id.isna().equals(~frame.eligible),
        "no_identity_claim": not frame.identity_verified.any(),
        "closed_before_cutoff": bool((frame.ts + pd.Timedelta(days=1)).le(pd.Timestamp(request["end"])).all()),
        "not_before_start": bool(frame.ts.ge(pd.Timestamp(request["start"])).all()),
        "size_under_50mib": (OUT / summary["parquet_path"]).stat().st_size < 50 * 1024 * 1024,
    }
    delta = frame.loc[frame.eligible].groupby(["symbol", "research_segment_id"]).ts.diff().dropna()
    checks["every_eligible_segment_daily_contiguous"] = bool(delta.eq(pd.Timedelta(days=1)).all())
    projection = dict(zip(coverage.symbol, coverage.dataframe_projection_sha256))
    mismatch = [symbol for symbol, group in frame.groupby("symbol", sort=False)
                if hashlib.sha256(pd.util.hash_pandas_object(group, index=False).values.tobytes()).hexdigest()
                != projection[symbol]]
    checks["roundtrip_matches_api_projection_for_every_symbol"] = not mismatch
    receipts = summary["startup_receipts"]
    checks["every_startup_receipt_hash_valid"] = all(
        sha(OUT / receipt["request_path"]) == receipt["request_sha256"]
        and sha(OUT / receipt["report_path"]) == receipt["report_sha256"] for receipt in receipts
    )
    helper_path = FAMILY / "scripts/load_binance_1d_mcsm_lifecycle_inputs_20260908.py"
    spec = importlib.util.spec_from_file_location("lifecycle_input_check", helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.validate_frozen_request(request)
    cases = [dict(request, symbols=request["symbols"][:-1]), dict(request, backward_bars=7),
             dict(request, asset_policy="crypto_only"), dict(request, bundle_sha256="0" * 64),
             dict(request, end="2026-09-06T00:00:00Z")]
    rejected = 0
    for case in cases:
        try:
            helper.validate_frozen_request(case)
        except ValueError:
            rejected += 1
    checks["all_five_request_tamper_cases_rejected"] = rejected == 5
    result = {
        "status": "PASS" if all(checks.values()) else "FAILED", "checks": checks,
        "check_count": len(checks), "projection_mismatch_symbols": mismatch,
        "request_tamper_rejections_tested": rejected, "startup_reports": len(receipts),
        "requested_symbols": summary["requested_symbols"], "returned_symbols": summary["returned_symbols"],
        "rows": len(frame), "eligible_rows": int(frame.eligible.sum()),
        "ineligible_rows_retained": int((~frame.eligible).sum()),
        "parquet_sha256": summary["parquet_sha256"], "summary_sha256": sha(OUT / "summary.json"),
        "qa_script_sha256": sha(Path(__file__)),
    }
    destination = OUT / "independent-input-qa.json"
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if destination.exists():
        if destination.read_text() != encoded:
            raise FileExistsError("Refusing to overwrite changed independent input QA")
    else:
        destination.write_text(encoded, encoding="utf-8")
    print(encoded)
    if result["status"] != "PASS":
        raise ValueError("Independent retained-frame checks failed")


if __name__ == "__main__":
    main()
