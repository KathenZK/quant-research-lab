#!/usr/bin/env python3
"""Field inventory for Binance OHLCV data-lake governance. Read-only except artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from strategy_lab.data.catalog import (
    BINANCE_PERP_15M_NORMALIZED_V1,
    BINANCE_PERP_1D_CACHE_FROM_15M,
    BINANCE_PERP_1D_FROM_15M_V1,
    BINANCE_PERP_1D_MA7_RC_P0_PANEL,
    BINANCE_PERP_1D_MA7_RC_P3_PANEL,
    BINANCE_PERP_1H_FROM_15M_V1,
    BINANCE_PERP_1H_NORMALIZED_LEGACY,
    BINANCE_PERP_4H_FROM_15M_V1,
    DatasetRegistry,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import write_canonical_json
from strategy_lab.data.resample import PRIORITY_UNION_VERSION, SOURCE_PRIORITY_V1
from strategy_lab.data.settings import default_settings

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "research/platform/data-lake-governance"
ARTIFACT_DIR = FAMILY / "artifacts"
DIAGNOSTIC_DIR = FAMILY / "diagnostics"
NEEDLES = (
    "data/cache/binance_perp_1d_from_15m",
    "data/cache/binance-1d-ma7-rc-p0",
    "data/cache/binance-1d-ma7-rc-p3",
    "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
    "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m",
)
P0_CUTOFF = pd.Timestamp("2026-07-01T00:00:00Z")
P3_CUTOFF = pd.Timestamp("2026-08-25T00:00:00Z")
KNOWN = {
    "p0_15m_rows": 56_358_042,
    "p0_symbols": 790,
    "p0_complete_days": 586_612,
    "p3_15m_rows": 60_266_362,
    "p3_symbols": 853,
    "n15m_bytes": 2.9e9,
    "n15m_files": 8913,
    "n1h_bytes": 76e6,
    "n1h_files": 4758,
    "n1h_rows": 399_679,
    "n1h_symbols": 543,
}


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    con.execute("SET enable_progress_bar=false")
    return con


def file_stats(root: Path) -> dict[str, Any]:
    files = sorted(root.rglob("*.parquet")) if root.exists() else []
    bytes_total = sum(path.stat().st_size for path in files)
    return {
        "physical_path": str(root),
        "file_count": len(files),
        "bytes": bytes_total,
        "exists": root.exists(),
    }


def glob_parquet(root: Path) -> str:
    return str(root / "**/*.parquet")


def source_and_quality(con: duckdb.DuckDBPyConnection, root: Path) -> dict[str, Any]:
    glob = glob_parquet(root)
    sources = con.execute(
        f"""
        SELECT source, count(*) AS rows, count(DISTINCT symbol) AS symbols,
               min(ts) AS start_ts, max(ts) AS end_ts
        FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
        GROUP BY 1 ORDER BY rows DESC
        """
    ).fetch_df()
    quality = con.execute(
        f"""
        SELECT
            count(*) AS physical_rows,
            count(DISTINCT (symbol, ts)) AS distinct_symbol_ts,
            count(*) - count(DISTINCT (symbol, ts)) AS duplicate_business_key_rows,
            count(*) - count(DISTINCT (symbol, ts, source)) AS within_source_duplicate_rows,
            count(DISTINCT symbol) AS symbols,
            min(ts) AS start_ts,
            max(ts) AS end_ts,
            count(*) FILTER (
                WHERE open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL
                   OR volume IS NULL OR quote_volume IS NULL OR trade_count IS NULL
                   OR vwap IS NULL OR is_closed IS NULL OR source IS NULL OR ts IS NULL
            ) AS critical_null_rows,
            count(*) FILTER (WHERE NOT is_closed) AS unclosed_rows,
            count(*) FILTER (
                WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0
                   OR high < greatest(open, close, low)
                   OR low > least(open, close, high)
            ) AS illegal_ohlc_rows
        FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
        """
    ).fetch_df().iloc[0]
    years = con.execute(
        f"""
        SELECT CAST(date_part('year', ts) AS INTEGER) AS year,
               count(DISTINCT symbol) AS symbols,
               count(*) AS rows
        FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
        GROUP BY 1 ORDER BY 1
        """
    ).fetch_df()
    spans = con.execute(
        f"""
        SELECT symbol, min(ts) AS start_ts, max(ts) AS end_ts,
               count(DISTINCT CAST(ts AS DATE)) AS effective_days, count(*) AS rows
        FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
        GROUP BY 1 ORDER BY effective_days DESC, symbol
        """
    ).fetch_df()
    one = con.execute(
        f"SELECT * FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true) LIMIT 1"
    ).fetch_df()
    return {
        "sources": [
            {
                "source": str(row["source"]),
                "rows": int(row["rows"]),
                "symbols": int(row["symbols"]),
                "start_utc": pd.Timestamp(row["start_ts"]).isoformat(),
                "end_utc": pd.Timestamp(row["end_ts"]).isoformat(),
            }
            for _, row in sources.iterrows()
        ],
        "physical_rows": int(quality["physical_rows"]),
        "distinct_business_keys": int(quality["distinct_symbol_ts"]),
        "duplicate_key_rows": int(quality["duplicate_business_key_rows"]),
        "within_source_duplicate_rows": int(quality["within_source_duplicate_rows"]),
        "symbol_count": int(quality["symbols"]),
        "start_utc": pd.Timestamp(quality["start_ts"]).isoformat() if pd.notna(quality["start_ts"]) else None,
        "end_utc": pd.Timestamp(quality["end_ts"]).isoformat() if pd.notna(quality["end_ts"]) else None,
        "critical_null_rows": int(quality["critical_null_rows"]),
        "unclosed_rows": int(quality["unclosed_rows"]),
        "illegal_ohlc_rows": int(quality["illegal_ohlc_rows"]),
        "schema": {str(column): str(one[column].dtype) for column in one.columns},
        "symbols_by_year": {str(int(row["year"])): int(row["symbols"]) for _, row in years.iterrows()},
        "rows_by_year": {str(int(row["year"])): int(row["rows"]) for _, row in years.iterrows()},
        "short_snapshot_symbols": int((spans["effective_days"] < 60).sum()),
        "long_history_365d_symbols": int((spans["effective_days"] >= 365).sum()),
        "per_symbol": [
            {
                "symbol": str(row["symbol"]),
                "start_utc": pd.Timestamp(row["start_ts"]).isoformat(),
                "end_utc": pd.Timestamp(row["end_ts"]).isoformat(),
                "effective_days": int(row["effective_days"]),
                "rows": int(row["rows"]),
            }
            for _, row in spans.iterrows()
        ],
    }


def selected_union_stats(con: duckdb.DuckDBPyConnection, root: Path, cutoff: pd.Timestamp) -> dict[str, Any]:
    glob = glob_parquet(root)
    listed = "', '".join(SOURCE_PRIORITY_V1)
    row = con.execute(
        f"""
        WITH raw AS (
            SELECT * FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
            WHERE source IN ('{listed}') AND ts < ?
        ),
        selected AS (
            SELECT * EXCLUDE (source_rank) FROM (
                SELECT *, CASE source
                    WHEN '{SOURCE_PRIORITY_V1[0]}' THEN 0
                    WHEN '{SOURCE_PRIORITY_V1[1]}' THEN 1
                    ELSE 999 END AS source_rank
                FROM raw
            )
            QUALIFY row_number() OVER (
                PARTITION BY symbol, ts ORDER BY source_rank, source
            ) = 1
        )
        SELECT count(*) AS selected_rows, count(DISTINCT symbol) AS symbols,
               min(ts) AS start_ts, max(ts) AS end_ts
        FROM selected
        """,
        [cutoff.to_pydatetime()],
    ).fetch_df().iloc[0]
    return {
        "cutoff_exclusive_utc": cutoff.isoformat(),
        "selected_rows": int(row["selected_rows"]),
        "symbols": int(row["symbols"]),
        "start_utc": pd.Timestamp(row["start_ts"]).isoformat(),
        "end_utc": pd.Timestamp(row["end_ts"]).isoformat(),
    }


def cache_1d_stats(con: duckdb.DuckDBPyConnection, root: Path) -> dict[str, Any]:
    ohlcv = root / "ohlcv_1d"
    monthly = str(ohlcv / "month=*.parquet")
    overlay = ohlcv / "overlay_date_partitions.parquet"
    month_rows = int(con.execute(f"SELECT count(*) FROM read_parquet('{monthly}')").fetchone()[0])
    overlay_rows = int(con.execute(f"SELECT count(*) FROM read_parquet('{overlay}')").fetchone()[0])
    overlap = int(
        con.execute(
            f"""
            SELECT count(*) FROM (
                SELECT DISTINCT sym_key, day FROM read_parquet('{monthly}')
                INTERSECT
                SELECT DISTINCT sym_key, day FROM read_parquet('{overlay}')
            )
            """
        ).fetchone()[0]
    )
    effective = con.execute(
        f"""
        SELECT * EXCLUDE (prio) FROM (
            SELECT *, 0 AS prio FROM read_parquet('{monthly}')
            UNION ALL BY NAME
            SELECT *, 1 AS prio FROM read_parquet('{overlay}')
        )
        QUALIFY row_number() OVER (PARTITION BY sym_key, day ORDER BY prio) = 1
        """
    ).fetch_df()
    complete = effective.loc[effective["bars_15m"].eq(96) & effective["all_closed"].fillna(False)]
    return {
        "physical_rows": month_rows + overlay_rows,
        "monthly_rows": month_rows,
        "overlay_rows": overlay_rows,
        "overlap_keys": overlap,
        "month_first_effective_keys": int(len(effective)),
        "complete_days_96_closed": int(len(complete)),
        "symbols": int(effective["sym_key"].nunique()),
        "start_utc": pd.Timestamp(effective["day"].min()).isoformat(),
        "end_utc": pd.Timestamp(effective["day"].max()).isoformat(),
        "schema": list(effective.columns),
    }


def panel_stats(path: Path) -> dict[str, Any]:
    frame = pd.read_parquet(path)
    return {
        "physical_rows": int(len(frame)),
        "columns": list(frame.columns),
        "is_standard_ohlcv": set(
            ["open", "high", "low", "close", "volume", "quote_volume", "trade_count", "vwap", "is_closed", "source"]
        ).issubset(frame.columns),
        "symbol_count": int(frame["symbol"].nunique()) if "symbol" in frame.columns else None,
        "start_utc": pd.to_datetime(frame["ts"], utc=True).min().isoformat() if "ts" in frame.columns else None,
        "end_utc": pd.to_datetime(frame["ts"], utc=True).max().isoformat() if "ts" in frame.columns else None,
    }


def write_inventory_markdown(summary: dict[str, Any]) -> Path:
    lines = [
        "# Binance OHLCV 数据湖现场目录审计",
        "",
        f"- 生成时间：`{summary['generated_at']}`",
        f"- 来源裁决：`{summary['priority_union_version']}`（Vision monthly 优先于 Futures API；未列入来源不进入 trusted union）",
        "- 本报告只描述现场身份与覆盖，不改变策略假设。",
        "",
        "## 分层结论",
        "",
        "```text",
        "Binance 原始来源 → raw → accepted normalized 15m",
        "                 → versioned derived 1h/4h/1d",
        "                 → family cache",
        "                 → research artifacts",
        "```",
        "",
        "normalized 1h 登记为 `PARTIAL_SCOPE_LEGACY`，不得因 distinct symbol 数量被当成全市场。",
        "",
        "## 数据集登记",
        "",
        "| dataset_id | layer | status | 文件 | 字节 | 物理行 | 业务键 | 重复键 | symbols | 起止 UTC |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in summary["datasets"]:
        lines.append(
            "| `{dataset_id}` | {layer} | `{status}` | {file_count} | {bytes} | {physical_rows} | {keys} | {dups} | {symbols} | {start} → {end} |".format(
                dataset_id=item["dataset_id"],
                layer=item.get("layer"),
                status=item.get("status"),
                file_count=item.get("file_count"),
                bytes=item.get("bytes"),
                physical_rows=item.get("physical_rows", "n/a"),
                keys=item.get("distinct_business_keys", item.get("distinct_keys", "n/a")),
                dups=item.get("duplicate_key_rows", "n/a"),
                symbols=item.get("symbol_count", item.get("symbols", "n/a")),
                start=item.get("start_utc"),
                end=item.get("end_utc"),
            )
        )
    lines.extend(["", "## 逐数据集说明", ""])
    for item in summary["datasets"]:
        lines.append(f"### `{item['dataset_id']}`")
        lines.append("")
        lines.append(f"- layer / timeframe：`{item.get('layer')}` / `{item.get('timeframe')}`")
        lines.append(f"- 物理路径：`{item.get('physical_path')}`")
        lines.append(f"- 状态 / 声明 scope：`{item.get('status')}` / `{item.get('declared_scope')}`")
        lines.append(f"- 来源裁决：{item.get('source_adjudication')}")
        lines.append(f"- 是否可重建：`{item.get('rebuildable')}`")
        lines.append(f"- 是否标准 OHLCV：`{item.get('is_standard_ohlcv')}`")
        lines.append(f"- builder：`{item.get('builder')}`")
        if item.get("sources"):
            lines.append("- 行级来源：")
            for source in item["sources"]:
                lines.append(
                    f"  - `{source['source']}`：{source['rows']} 行，{source['symbols']} 个代码，"
                    f"{source['start_utc']} → {source['end_utc']}"
                )
        if item.get("symbols_by_year"):
            lines.append(f"- 每年有效 symbol 数：`{item['symbols_by_year']}`")
        if item.get("p0_union"):
            delta = item.get("known_delta") or {}
            lines.append(
                f"- P0 union `< 2026-07-01T00:00:00Z`：{item['p0_union']['selected_rows']} 行 / "
                f"{item['p0_union']['symbols']} 个代码；相对已知值 Δ rows `{delta.get('p0_rows')}`、"
                f"Δ symbols `{delta.get('p0_symbols')}`"
            )
        if item.get("p3_union"):
            delta = item.get("known_delta") or {}
            lines.append(
                f"- P3 union `< 2026-08-25T00:00:00Z`：{item['p3_union']['selected_rows']} 行 / "
                f"{item['p3_union']['symbols']} 个代码；相对已知值 Δ rows `{delta.get('p3_rows')}`、"
                f"Δ symbols `{delta.get('p3_symbols')}`"
            )
        for key in (
            "monthly_rows",
            "overlay_rows",
            "overlap_keys",
            "month_first_effective_keys",
            "complete_days_96_closed",
            "critical_null_rows",
            "unclosed_rows",
            "illegal_ohlc_rows",
            "short_snapshot_symbols",
            "long_history_365d_symbols",
            "classification_note",
        ):
            if item.get(key) is not None:
                lines.append(f"- {key}：`{item[key]}`")
        lines.append("")
    lines.extend(
        [
            "## 消费者",
            "",
            "详见 [binance_ohlcv_consumers_2026-09-02.csv](../artifacts/binance_ohlcv_consumers_2026-09-02.csv)。",
            "逐 symbol 起止见 [binance_ohlcv_symbol_spans_2026-09-02.csv](../artifacts/binance_ohlcv_symbol_spans_2026-09-02.csv)。",
            "",
            "## 已知数字差异",
            "",
            "若现场数字与任务简述不同，以本报告 JSON 为准，不得静默沿用旧数字。",
            "",
        ]
    )
    path = DIAGNOSTIC_DIR / "binance-ohlcv-dataset-inventory-2026-09-02.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def find_consumers() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {needle: [] for needle in NEEDLES}
    search_roots = [ROOT / name for name in ("research", "src", "tests", "docs", "archive")]
    for base in search_roots:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".md", ".json"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            rel = path.relative_to(ROOT).as_posix()
            for needle in NEEDLES:
                if needle in text:
                    found[needle].append(rel)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    DIAGNOSTIC_DIR.mkdir(parents=True, exist_ok=True)
    layout = DataLakeLayout.from_settings(default_settings())
    registry = DatasetRegistry()
    con = connect()
    datasets: list[dict[str, Any]] = []
    n15 = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
    n1h = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h"
    print("auditing normalized 15m", flush=True)
    q15 = source_and_quality(con, n15)
    p0 = selected_union_stats(con, n15, P0_CUTOFF)
    p3 = selected_union_stats(con, n15, P3_CUTOFF)
    print("auditing normalized 1h", flush=True)
    q1h = source_and_quality(con, n1h)
    print("auditing public 1d cache", flush=True)
    cache_root = layout.cache_dir / "binance_perp_1d_from_15m"
    cache_stats = cache_1d_stats(con, cache_root)
    print("auditing family panels", flush=True)
    p0_panel = panel_stats(layout.cache_dir / "binance-1d-ma7-rc-p0" / "binance_1d_ma7_rc_p0_daily_panel.parquet")
    p3_panel = panel_stats(layout.cache_dir / "binance-1d-ma7-rc-p3" / "binance_1d_ma7_rc_p3_daily_panel.parquet")
    consumers = find_consumers()
    records = {item.dataset_id: item for item in registry.records()}

    def pack(dataset_id: str, quality: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
        record = records[dataset_id]
        stats = file_stats(record.absolute_root(layout))
        payload = {
            "dataset_id": dataset_id,
            "layer": record.layer,
            "exchange": record.exchange,
            "market_type": record.market_type.value,
            "timeframe": record.timeframe,
            "status": record.status.value,
            "declared_scope": record.declared_scope.value,
            "source_adjudication": record.source_adjudication,
            "priority_union_version": record.priority_union_version,
            "rebuildable": record.rebuildable,
            "is_standard_ohlcv": record.is_standard_ohlcv,
            "builder": record.builder,
            "input_dataset_id": record.input_dataset_id,
            **stats,
            **quality,
            **extra,
        }
        return payload

    datasets.append(
        pack(
            BINANCE_PERP_15M_NORMALIZED_V1,
            q15,
            {
                "p0_union": p0,
                "p3_union": p3,
                "known_delta": {
                    "p0_rows": p0["selected_rows"] - KNOWN["p0_15m_rows"],
                    "p0_symbols": p0["symbols"] - KNOWN["p0_symbols"],
                    "p3_rows": p3["selected_rows"] - KNOWN["p3_15m_rows"],
                    "p3_symbols": p3["symbols"] - KNOWN["p3_symbols"],
                    "file_count": file_stats(n15)["file_count"] - KNOWN["n15m_files"],
                    "bytes": file_stats(n15)["bytes"] - KNOWN["n15m_bytes"],
                },
            },
        )
    )
    datasets.append(
        pack(
            BINANCE_PERP_1H_NORMALIZED_LEGACY,
            q1h,
            {
                "classification_note": "PARTIAL_SCOPE_LEGACY: distinct symbol count is not full-market history",
                "known_delta": {
                    "file_count": file_stats(n1h)["file_count"] - KNOWN["n1h_files"],
                    "bytes": file_stats(n1h)["bytes"] - KNOWN["n1h_bytes"],
                    "rows": q1h["physical_rows"] - KNOWN["n1h_rows"],
                    "symbols": q1h["symbol_count"] - KNOWN["n1h_symbols"],
                },
            },
        )
    )
    for dataset_id, extra in (
        (BINANCE_PERP_1H_FROM_15M_V1, {"published": (layout.root_dir / records[BINANCE_PERP_1H_FROM_15M_V1].relative_root).exists()}),
        (BINANCE_PERP_4H_FROM_15M_V1, {"published": (layout.root_dir / records[BINANCE_PERP_4H_FROM_15M_V1].relative_root).exists()}),
        (BINANCE_PERP_1D_FROM_15M_V1, {"published": (layout.root_dir / records[BINANCE_PERP_1D_FROM_15M_V1].relative_root).exists()}),
    ):
        datasets.append(pack(dataset_id, {}, extra))
    datasets.append(pack(BINANCE_PERP_1D_CACHE_FROM_15M, cache_stats, {"consumer_cutoff_note": "MCSM-LS3 clips to 2026-06-30"}))
    datasets.append(pack(BINANCE_PERP_1D_MA7_RC_P0_PANEL, p0_panel, {}))
    datasets.append(pack(BINANCE_PERP_1D_MA7_RC_P3_PANEL, p3_panel, {}))

    snapshot_src = Path("/tmp/binance-ohlcv-governance-snapshot/pre_governance_parquet_inventory.csv")
    if snapshot_src.exists():
        shutil.copy2(snapshot_src, ARTIFACT_DIR / "pre_governance_parquet_inventory.csv")

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "priority_union_version": PRIORITY_UNION_VERSION,
        "datasets": datasets,
        "consumers": consumers,
        "known_reference": KNOWN,
    }
    write_canonical_json(ARTIFACT_DIR / "binance_ohlcv_dataset_inventory_2026-09-02.json", summary)
    write_inventory_markdown(summary)
    span_rows = []
    for item in datasets:
        for symbol_row in item.get("per_symbol") or []:
            span_rows.append({"dataset_id": item["dataset_id"], **symbol_row})
    if span_rows:
        pd.DataFrame(span_rows).to_csv(
            ARTIFACT_DIR / "binance_ohlcv_symbol_spans_2026-09-02.csv",
            index=False,
        )
    consumer_rows = [
        {"path_needle": needle, "consumer": path}
        for needle, paths in consumers.items()
        for path in paths
    ]
    pd.DataFrame(consumer_rows).to_csv(
        ARTIFACT_DIR / "binance_ohlcv_consumers_2026-09-02.csv",
        index=False,
    )
    print(json.dumps({k: (v if k != "datasets" else [d["dataset_id"] for d in v]) for k, v in summary.items() if k != "consumers"}, indent=2, default=str)[:2000])
    print("wrote inventory artifacts", flush=True)


if __name__ == "__main__":
    main()
