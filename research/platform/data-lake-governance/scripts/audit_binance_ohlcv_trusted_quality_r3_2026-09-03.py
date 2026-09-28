#!/usr/bin/env python3
"""Round 3 full trusted-quality audit. Does not reuse Round 2 SQL PASS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd

from strategy_lab.data.catalog import (
    BINANCE_PERP_15M_NORMALIZED_V1,
    BINANCE_PERP_1D_FROM_15M_V1,
    BINANCE_PERP_1H_FROM_15M_V1,
    BINANCE_PERP_4H_FROM_15M_V1,
    DatasetScope,
    inspect_dataset,
    list_dataset_parquet_files,
    load_trusted_dataset,
    resolve_dataset,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import FingerprintMode, write_canonical_json
from strategy_lab.data.sessions import timeframe_delta
from strategy_lab.data.settings import default_settings
from strategy_lab.data.sql_audit import SQL_AUDIT_RULE_VERSION
from strategy_lab.data.windows import bar_close

ROOT = Path(__file__).resolve().parents[4]
ARTIFACT = (
    ROOT
    / "research/platform/data-lake-governance/artifacts"
    / "binance_ohlcv_trusted_quality_audit_r3_2026-09-03.json"
)
GAP_CSV = (
    ROOT
    / "research/platform/data-lake-governance/artifacts"
    / "binance_ohlcv_4h_gap_table_r3_2026-09-03.csv"
)
REPORT = (
    ROOT
    / "research/platform/data-lake-governance/diagnostics"
    / "binance-ohlcv-trusted-quality-audit-r3-2026-09-03.md"
)
DATASETS = (
    BINANCE_PERP_15M_NORMALIZED_V1,
    BINANCE_PERP_1H_FROM_15M_V1,
    BINANCE_PERP_4H_FROM_15M_V1,
    BINANCE_PERP_1D_FROM_15M_V1,
)


def slim_audit(audit: dict) -> dict:
    skip = {"gap_classification", "source_counts", "gap_intervals"}
    return {key: value for key, value in audit.items() if key not in skip}


def export_4h_gaps(layout, record) -> list[dict]:
    files = [str(path) for path in list_dataset_parquet_files(record, layout)]
    seconds = int(timeframe_delta(record.timeframe or "4h").total_seconds())
    micros = seconds * 1_000_000
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    con.execute("SET enable_progress_bar=false")
    frame = con.execute(
        f"""
        WITH raw AS (
            SELECT symbol, ts
            FROM read_parquet(?, hive_partitioning=false, union_by_name=false)
        ),
        ordered AS (
            SELECT
                symbol,
                ts,
                lag(ts) OVER (PARTITION BY symbol ORDER BY ts) AS prev_ts
            FROM raw
        )
        SELECT
            symbol,
            prev_ts,
            ts AS next_ts,
            CAST((epoch_us(ts) - epoch_us(prev_ts)) / {micros} - 1 AS BIGINT) AS missing_bars,
            ((epoch_us(ts) - epoch_us(prev_ts)) % {micros}) = 0 AS aligned
        FROM ordered
        WHERE prev_ts IS NOT NULL
          AND epoch_us(ts) - epoch_us(prev_ts) > {micros}
        ORDER BY symbol, prev_ts
        """,
        [files],
    ).fetch_df()
    rows = []
    for _, item in frame.iterrows():
        rows.append(
            {
                "symbol": item["symbol"],
                "prev_ts_utc": pd.Timestamp(item["prev_ts"]).isoformat(),
                "next_ts_utc": pd.Timestamp(item["next_ts"]).isoformat(),
                "missing_bars": int(item["missing_bars"]),
                "aligned": bool(item["aligned"]),
                "listing_evidence": "unknown",
                "known_cause": "unknown",
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", action="append", dest="dataset_ids")
    args = parser.parse_args()
    wanted = tuple(args.dataset_ids) if args.dataset_ids else DATASETS
    layout = DataLakeLayout.from_settings(default_settings())
    results: list[dict] = []
    gap_rows: list[dict] = []
    for dataset_id in wanted:
        print(f"inspect {dataset_id}", flush=True)
        preview = inspect_dataset(dataset_id, layout=layout, requested_scope=DatasetScope.FULL_MARKET)
        print(
            f"trusted-load {dataset_id} files={preview.parquet_file_count} "
            f"rows={preview.coverage.get('rows')} rule={SQL_AUDIT_RULE_VERSION}",
            flush=True,
        )
        loaded = load_trusted_dataset(
            dataset_id,
            layout=layout,
            requested_scope=DatasetScope.FULL_MARKET,
            purpose="governance_audit",
            gap_policy="report_only",
            require_contiguous=False,
            require_closed=True,
            max_materialize_rows=0,
            fingerprint_mode=FingerprintMode.STRICT_CONTENT,
        )
        research_reject = None
        if dataset_id == BINANCE_PERP_4H_FROM_15M_V1:
            try:
                last_open = pd.Timestamp(loaded.coverage["end_utc"])
                load_trusted_dataset(
                    dataset_id,
                    layout=layout,
                    requested_scope=DatasetScope.FULL_MARKET,
                    purpose="research",
                    gap_policy="reject",
                    end=bar_close(last_open, "4h"),
                    require_closed=True,
                    max_materialize_rows=0,
                    expected_parquet_fingerprint=loaded.manifest.get("parquet_inventory_fingerprint"),
                )
                research_reject = {"status": "PASS"}
            except Exception as exc:  # noqa: BLE001 - record the research-window refusal
                research_reject = {"status": "REJECTED", "error": str(exc)[:500]}
            print("export 4h gap table", flush=True)
            gap_rows = export_4h_gaps(layout, resolve_dataset(dataset_id, layout=layout))
        results.append(
            {
                "dataset_id": dataset_id,
                "inspection_trusted_flag": preview.trusted,
                "quality_status": loaded.audit.get("quality_status"),
                "row_quality": loaded.audit.get("row_quality"),
                "historical_coverage": loaded.audit.get("historical_coverage"),
                "research_window_fitness": loaded.audit.get("research_window_fitness"),
                "listing_evidence": loaded.audit.get("listing_evidence"),
                "materialized": loaded.materialized,
                "coverage": {key: value for key, value in loaded.coverage.items() if key != "per_symbol"},
                "audit": slim_audit(loaded.audit),
                "source_counts": loaded.source_counts,
                "parquet_inventory_fingerprint": loaded.manifest.get("parquet_inventory_fingerprint"),
                "manifest_file_sha256": loaded.verified_identity.get("manifest_file_sha256"),
                "content_fingerprint": loaded.verified_identity.get("content_fingerprint"),
                "cutoff_exclusive_utc": loaded.verified_identity.get("cutoff_exclusive_utc"),
                "fingerprint_mode": loaded.verified_identity.get("fingerprint_mode"),
                "observed_end_utc": loaded.coverage.get("end_utc"),
                "verified_file_count": len(loaded.verified_parquet_files),
                "sql_audit_rule_version": SQL_AUDIT_RULE_VERSION,
                "research_reject": research_reject,
            }
        )
        print(
            f"  status={loaded.audit.get('quality_status')} "
            f"row_quality={loaded.audit.get('row_quality')} "
            f"coverage={loaded.audit.get('historical_coverage')} "
            f"fitness={loaded.audit.get('research_window_fitness')} "
            f"files={len(loaded.verified_parquet_files)}",
            flush=True,
        )
    payload = {
        "mode": "R3_FULL_SQL_AUDIT_STRICT_CONTENT",
        "sql_audit_rule_version": SQL_AUDIT_RULE_VERSION,
        "partial": False,
        "reused_round2_sql_pass": False,
        "results": results,
        "all_row_quality_pass": all(item.get("row_quality") == "PASS" for item in results),
        "gap_table_rows": len(gap_rows),
    }
    write_canonical_json(ARTIFACT, payload)
    if gap_rows:
        pd.DataFrame(gap_rows).to_csv(GAP_CSV, index=False)
    lines = [
        "# Binance OHLCV 全量质量审计 R3（2026-09-03）",
        "",
        "本轮使用 `SQL_AUDIT_RULE_VERSION=binance_ohlcv_sql_audit_v2` 与 `fingerprint_mode=strict_content`。",
        "不复用第二轮 SQL PASS。整库扫描声明 `purpose=governance_audit`；4h 内部缺口另行报告研究窗口适用性。",
        "首尾 K 线没有上市/退市证据，`listing_evidence=unknown`。",
        "",
        f"行质量全部 PASS：`{payload['all_row_quality_pass']}`；`partial={payload['partial']}`。",
        "",
    ]
    for item in results:
        audit = item["audit"]
        lines.extend(
            [
                f"## `{item['dataset_id']}`",
                "",
                f"- row_quality / quality_status：`{item['row_quality']}` / `{item['quality_status']}`",
                f"- historical_coverage：`{item['historical_coverage']}`",
                f"- research_window_fitness（report_only）：`{item['research_window_fitness']}`",
                f"- listing_evidence：`{item['listing_evidence']}`",
                f"- materialized：`{item['materialized']}`（应为 false）",
                f"- inspect.trusted：`{item['inspection_trusted_flag']}`（预览不得为 true）",
                f"- rows / symbols：`{item['coverage'].get('rows')}` / `{item['coverage'].get('symbol_count')}`",
                f"- 范围：`{item['coverage'].get('start_utc')}` → `{item['coverage'].get('end_utc')}`",
                f"- cutoff_exclusive_utc：`{item['cutoff_exclusive_utc']}`",
                f"- parquet_inventory_fingerprint：`{item['parquet_inventory_fingerprint']}`",
                f"- fingerprint_mode：`{item['fingerprint_mode']}`",
                f"- internal_missing_bars：`{audit.get('internal_missing_bars')}`",
                f"- unaligned_gap_transitions：`{audit.get('unaligned_gap_transitions')}`",
                f"- schema_errors：`{audit.get('schema_errors')}`",
                f"- research reject：`{item.get('research_reject')}`",
                "",
            ]
        )
    if gap_rows:
        lines.extend(
            [
                "## 4h 逐 symbol 缺口表",
                "",
                f"共 `{len(gap_rows)}` 段内部缺口。原因未知则标 `unknown`，不得把首尾当成已确认上市/退市。",
                f"机器表：[{GAP_CSV.name}](../artifacts/{GAP_CSV.name})。",
                "",
            ]
        )
    lines.append(f"机器结果：[{ARTIFACT.name}](../artifacts/{ARTIFACT.name})。")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"all_row_quality_pass": payload["all_row_quality_pass"], "path": str(ARTIFACT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
