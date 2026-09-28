#!/usr/bin/env python3
"""Full SQL quality audit of accepted 15m and published derived 1h/4h/1d."""

from __future__ import annotations

import json
from pathlib import Path

from strategy_lab.data.catalog import (
    BINANCE_PERP_15M_NORMALIZED_V1,
    BINANCE_PERP_1D_FROM_15M_V1,
    BINANCE_PERP_1H_FROM_15M_V1,
    BINANCE_PERP_4H_FROM_15M_V1,
    DatasetScope,
    inspect_dataset,
    load_trusted_dataset,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import write_canonical_json
from strategy_lab.data.settings import default_settings

ROOT = Path(__file__).resolve().parents[4]
ARTIFACT = (
    ROOT
    / "research/platform/data-lake-governance/artifacts"
    / "binance_ohlcv_trusted_quality_audit_2026-09-03.json"
)
REPORT = (
    ROOT
    / "research/platform/data-lake-governance/diagnostics"
    / "binance-ohlcv-trusted-quality-audit-2026-09-03.md"
)
DATASETS = (
    BINANCE_PERP_15M_NORMALIZED_V1,
    BINANCE_PERP_1H_FROM_15M_V1,
    BINANCE_PERP_4H_FROM_15M_V1,
    BINANCE_PERP_1D_FROM_15M_V1,
)


def slim_audit(audit: dict) -> dict:
    skip = {"gap_classification", "source_counts"}
    return {key: value for key, value in audit.items() if key not in skip}


def main() -> None:
    layout = DataLakeLayout.from_settings(default_settings())
    results: list[dict] = []
    for dataset_id in DATASETS:
        print(f"inspect {dataset_id}", flush=True)
        preview = inspect_dataset(dataset_id, layout=layout, requested_scope=DatasetScope.FULL_MARKET)
        print(f"trusted-load {dataset_id} rows={preview.coverage.get('rows')}", flush=True)
        loaded = load_trusted_dataset(
            dataset_id,
            layout=layout,
            requested_scope=DatasetScope.FULL_MARKET,
            require_contiguous=False,
            require_closed=True,
            max_materialize_rows=0,
        )
        results.append(
            {
                "dataset_id": dataset_id,
                "inspection_trusted_flag": preview.trusted,
                "quality_status": loaded.audit.get("quality_status"),
                "materialized": loaded.materialized,
                "coverage": preview.coverage,
                "audit": slim_audit(loaded.audit),
                "source_counts": loaded.source_counts,
                "parquet_inventory_fingerprint": loaded.manifest.get("parquet_inventory_fingerprint"),
                "cutoff_exclusive_utc": loaded.verified_identity.get("cutoff_exclusive_utc"),
                "observed_end_utc": loaded.coverage.get("end_utc"),
                "verified_file_count": len(loaded.verified_parquet_files),
            }
        )
        print(f"  status={loaded.audit.get('quality_status')} files={len(loaded.verified_parquet_files)}", flush=True)
    payload = {
        "mode": "FULL_SQL_AUDIT",
        "partial": False,
        "results": results,
        "all_pass": all(item["quality_status"] == "PASS" for item in results),
    }
    write_canonical_json(ARTIFACT, payload)
    lines = [
        "# Binance OHLCV 全量 SQL 质量审计（2026-09-03）",
        "",
        "本轮对 accepted 15m 与已发布 1h/4h/1d 派生集做 DuckDB 全量质量扫描，不把覆盖预览当作 trusted，也不把抽样当作全量。",
        "",
        f"总体：`{'PASS' if payload['all_pass'] else 'FAIL/PARTIAL'}`；`partial={payload['partial']}`。",
        "",
    ]
    for item in results:
        audit = item["audit"]
        lines.extend(
            [
                f"## `{item['dataset_id']}`",
                "",
                f"- quality_status：`{item['quality_status']}`",
                f"- materialized：`{item['materialized']}`（应为 false）",
                f"- inspect.trusted：`{item['inspection_trusted_flag']}`（预览不得为 true）",
                f"- rows / symbols：`{item['coverage'].get('rows')}` / `{item['coverage'].get('symbol_count')}`",
                f"- 范围：`{item['coverage'].get('start_utc')}` → `{item['coverage'].get('end_utc')}`",
                f"- cutoff_exclusive_utc：`{item['cutoff_exclusive_utc']}`",
                f"- parquet_inventory_fingerprint：`{item['parquet_inventory_fingerprint']}`",
                f"- internal_missing_bars：`{audit.get('internal_missing_bars')}`（report_only）",
                f"- unaligned_gap_transitions：`{audit.get('unaligned_gap_transitions')}`",
                f"- unverified_source_rows：`{audit.get('unverified_source_rows')}`",
                f"- illegal_ohlc_rows：`{audit.get('illegal_ohlc_rows')}`",
                f"- duplicate_business_key_rows：`{audit.get('duplicate_business_key_rows')}`",
                "",
            ]
        )
    lines.append(f"机器结果：[{ARTIFACT.name}](../artifacts/{ARTIFACT.name})。")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"all_pass": payload["all_pass"], "path": str(ARTIFACT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
