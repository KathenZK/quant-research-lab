"""Bounded offline trace of legacy funding parents; missing archives are not authenticated."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

SCRIPT = Path(__file__).with_name("audit_mcsm_all_funding_sources_20260910.py")
SPEC = importlib.util.spec_from_file_location("mcsm_legacy_lineage", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
ROOT = audit.ROOT
OUT = audit.OUT.parent / "legacy-lineage"


def main():
    started, _ = audit.verify_frozen_inputs()
    v2 = ROOT / "data/derived/datasets/binance_perp_funding_v3_inputs_v2/_MANIFEST.json"
    v1 = ROOT / "data/derived/datasets/binance_perp_funding_v3_inputs_v1/_MANIFEST.json"
    if audit.sha(v1) != json.loads(v2.read_text())["input_manifest_sha256"]:
        raise ValueError("Frozen v1 parent manifest changed")
    v1_info = json.loads(v1.read_text())
    v1_index = ROOT / v1_info["input_receipts_index"]
    if audit.sha(v1_index) != v1_info["input_receipts_index_sha256"]:
        raise ValueError("Frozen v1 parent receipt index changed")
    v2_index = ROOT / "research/platform/data-lake-governance/artifacts/binance_funding_v3_inputs_v2_20260907/input_receipts.json"
    if audit.sha(v2_index) != json.loads(v2.read_text())["input_receipts_sha256"]:
        raise ValueError("Frozen v2 receipt index changed")
    old = {(r["path"], r["sha256"]) for r in json.loads(v1_index.read_text())["receipts"]}
    current = {(r["path"], r["sha256"]) for r in json.loads(v2_index.read_text())["receipts"]}
    monthly_root = ROOT / "data/raw/funding_rates/exchange=binance/market_type=perp/source=binance_vision_monthly"
    legacy_root = ROOT / "data/raw/funding_rates/exchange=binance/market_type=perp/source=binance_vision_monthly_funding_rate"
    archive_root = ROOT / "data/raw/_archives/binance/futures/um/monthly/fundingRate"
    loader = ROOT / "research/asset-portfolios/1h-cross-sectional-lightgbm-selector/scripts/sync_binance_usdm_history.py"
    holding = pd.read_parquet(ROOT / started["paths"]["holdings"])
    archive_paths = set()
    month_paths = set()
    for row in holding.itertuples():
        code = row.symbol.split("/")[0] + "USDT"
        begin = row.entry_ts.normalize().replace(day=1)
        end = row.exit_ts.normalize().replace(day=1)
        for month in pd.date_range(begin, end, freq="MS"):
            tag = month.strftime("%Y-%m")
            archive_paths.add(archive_root / f"symbol={code.lower()}" / f"year={month.year}" / f"{code}-fundingRate-{tag}.zip")
            month_paths.add(monthly_root / f"month={tag}" / "part-0000.parquet")
    audit.save_new(OUT / "plan.json", {"status": "OFFLINE_LEGACY_LINEAGE_INSPECTION_ONLY", "frozen_at": audit.stamp(),
                                       "original_holdings_sha256": started["sha256"]["holdings"],
                                       "manifest_chain": {str(p.relative_to(ROOT)): audit.sha(p) for p in [v2, v1, v2_index, v1_index]},
                                       "bounded_archive_targets": [str(p.relative_to(ROOT)) for p in sorted(archive_paths)],
                                       "bounded_monthly_raw_files": [str(p.relative_to(ROOT)) for p in sorted(month_paths)],
                                       "original_downloader_path": str(loader.relative_to(ROOT)), "original_downloader_sha256": audit.sha(loader),
                                       "do_not_run_original_downloader": True, "network_requests": 0})
    raw_inventory = []
    for path in sorted(month_paths):
        raw_inventory.append({"path": str(path.relative_to(ROOT)), "exists": path.exists(),
                              "sha256_now_for_lineage_only": audit.sha(path) if path.exists() else None,
                              "columns": pq.ParquetFile(path).schema.names if path.exists() else [],
                              "not_independently_authenticated_original_zip": True})
    example = legacy_root / "date=2023-04-27/symbol=bch-usdt-perp.parquet"
    summary = {"status": "LEGACY_CONVERTED_ROWS_RETAINED_BUT_ORIGINAL_MONTHLY_ZIPS_NOT_AVAILABLE_AT_DECLARED_PATH",
               "v1_manifest_hash_verified_against_v2": True, "v1_source_receipt_count": len(old),
               "v1_receipts_already_in_v2_index": len(old & current), "additional_v1_receipts_not_yet_examined": len(old - current),
               "holding_windows": len(holding), "expected_original_archive_targets": len(archive_paths),
               "existing_original_archive_targets": sum(p.exists() for p in archive_paths),
               "original_monthly_funding_archive_directory_exists": archive_root.exists(),
               "bounded_raw_monthly_files": len(raw_inventory), "existing_raw_monthly_files": sum(x["exists"] for x in raw_inventory),
               "raw_monthly_inventory": raw_inventory,
               "legacy_daily_example": {"path": str(example.relative_to(ROOT)), "exists": example.exists(),
                                         "sha256_now_for_lineage_only": audit.sha(example) if example.exists() else None,
                                         "columns": pq.ParquetFile(example).schema.names if example.exists() else []},
               "interpretation": "Stored archive_sha256 columns are provenance claims, not substitute bytes. Original archive location comes from the original downloader. Missing files do not prove why or when they disappeared. No new source certification is granted to converted raw Parquet.",
               "additional_verified_funding_events": 0, "network_requests": 0,
               "stop_scope_here": True, "plan_sha256": audit.sha(OUT / "plan.json")}
    audit.save_new(OUT / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in ["raw_monthly_inventory", "legacy_daily_example"]}), flush=True)


if __name__ == "__main__":
    main()
