from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import json
import os
import shutil

import duckdb
import pandas as pd

from strategy_lab.data.authenticity import make_composite_source
from strategy_lab.data.manifest import (
    CANONICAL_DERIVED_QUALITY,
    DATASET_MANIFEST_FILENAME,
    DatasetManifest,
    inventory_fingerprint,
    parquet_inventory,
    resolve_parquet_inventory_fingerprint,
    sha256_file,
    utc_now_iso,
    write_canonical_json,
)
from strategy_lab.data.windows import require_aware_utc

FORMULA_VERSION = "ohlcv_resample_from_15m_v1"
PRIORITY_UNION_VERSION = "binance_perp_15m_priority_union_v1"
SOURCE_PRIORITY_V1 = (
    "binance_vision_kline_monthly",
    "binance_futures_kline_api",
)
NULL_FILL_POLICY = "no_gap_fill_no_interpolation; incomplete buckets dropped; zero_volume_vwap=output_close"
INPUT_TIMEFRAME = "15m"
INPUT_SECONDS = 900

RESAMPLE_SPECS = {
    "1h": {"component_count": 4, "bucket_seconds": 3600},
    "4h": {"component_count": 16, "bucket_seconds": 14400},
    "1d": {"component_count": 96, "bucket_seconds": 86400},
}


@dataclass(frozen=True, slots=True)
class SourceUnionPolicy:
    version: str
    priority: tuple[str, ...]
    reject_unlisted: bool = True
    passthrough: bool = False


DEFAULT_SOURCE_UNION = SourceUnionPolicy(
    version=PRIORITY_UNION_VERSION,
    priority=SOURCE_PRIORITY_V1,
    reject_unlisted=True,
)


def source_priority_sql(policy: SourceUnionPolicy, *, alias: str = "raw") -> tuple[str, list[Any]]:
    if policy.passthrough or not policy.priority:
        return f"SELECT * FROM {alias}", []
    cases = " ".join(
        f"WHEN source = ? THEN {index}" for index, _source in enumerate(policy.priority)
    )
    listed = ", ".join(["?"] * len(policy.priority))
    listed_filter = (
        f"WHERE source IN ({listed})" if policy.reject_unlisted else ""
    )
    sql = f"""
        SELECT * EXCLUDE (source_rank)
        FROM (
            SELECT
                {alias}.*,
                CASE {cases} ELSE 999 END AS source_rank
            FROM {alias}
            {listed_filter}
        )
        QUALIFY row_number() OVER (
            PARTITION BY exchange, symbol, market_type, timeframe, ts
            ORDER BY source_rank, source
        ) = 1
    """
    params: list[Any] = list(policy.priority)
    if policy.reject_unlisted:
        params.extend(policy.priority)
    return sql, params


def _legal_component_sql(alias: str = "selected") -> str:
    return f"""
        SELECT *
        FROM {alias}
        WHERE ts IS NOT NULL
          AND symbol IS NOT NULL
          AND source IS NOT NULL
          AND lower(source) NOT IN ('', 'unknown', 'none', 'null', 'nan', 'n/a')
          AND is_closed
          AND open > 0 AND high > 0 AND low > 0 AND close > 0
          AND volume >= 0 AND quote_volume >= 0 AND trade_count >= 0 AND vwap > 0
          AND high >= greatest(open, close, low)
          AND low <= least(open, close, high)
          AND CAST(epoch(ts) AS BIGINT) % {INPUT_SECONDS} = 0
    """


def resample_cte_sql(output_timeframe: str, *, source_alias: str = "legal") -> str:
    spec = RESAMPLE_SPECS[output_timeframe]
    component_count = spec["component_count"]
    bucket_seconds = spec["bucket_seconds"]
    last_offset = (component_count - 1) * INPUT_SECONDS
    return f"""
        buckets AS (
            SELECT
                *,
                to_timestamp(
                    CAST(epoch(ts) AS BIGINT)
                    - (CAST(epoch(ts) AS BIGINT) % {bucket_seconds})
                ) AS bar_ts
            FROM {source_alias}
        ),
        aggregated AS (
            SELECT
                bar_ts AS ts,
                any_value(exchange) AS exchange,
                symbol,
                any_value(market_type) AS market_type,
                '{output_timeframe}' AS timeframe,
                arg_min(open, ts) AS open,
                max(high) AS high,
                min(low) AS low,
                arg_max(close, ts) AS close,
                sum(volume) AS volume,
                sum(quote_volume) AS quote_volume,
                CAST(sum(trade_count) AS BIGINT) AS trade_count,
                CASE
                    WHEN sum(volume) = 0 THEN arg_max(close, ts)
                    ELSE sum(quote_volume) / sum(volume)
                END AS vwap,
                TRUE AS is_closed,
                CASE
                    WHEN count(DISTINCT source) = 1 THEN any_value(source)
                    ELSE 'composite:' || string_agg(DISTINCT source, '+' ORDER BY source)
                END AS source,
                string_agg(DISTINCT source, '+' ORDER BY source) AS source_components,
                count(*) AS component_count,
                count(DISTINCT ts) AS distinct_component_ts,
                min(ts) AS first_component_ts,
                max(ts) AS last_component_ts,
                count(DISTINCT exchange) AS exchange_count,
                count(DISTINCT market_type) AS market_type_count
            FROM buckets
            GROUP BY symbol, bar_ts
        ),
        complete_bars AS (
            SELECT
                ts,
                exchange,
                symbol,
                market_type,
                timeframe,
                open,
                high,
                low,
                close,
                volume,
                quote_volume,
                trade_count,
                vwap,
                is_closed,
                source,
                source_components,
                component_count,
                '{FORMULA_VERSION}' AS aggregation_formula_version,
                '{PRIORITY_UNION_VERSION}' AS priority_union_version,
                CAST(ts AS DATE) AS date
            FROM aggregated
            WHERE component_count = {component_count}
              AND distinct_component_ts = {component_count}
              AND first_component_ts = ts
              AND last_component_ts = ts + INTERVAL '{last_offset} seconds'
              AND exchange_count = 1
              AND market_type_count = 1
        )
    """


def resample_exclusion_cte_sql(output_timeframe: str, *, source_alias: str = "legal") -> str:
    spec = RESAMPLE_SPECS[output_timeframe]
    bucket_seconds = spec["bucket_seconds"]
    return f"""
        buckets AS (
            SELECT
                *,
                to_timestamp(
                    CAST(epoch(ts) AS BIGINT)
                    - (CAST(epoch(ts) AS BIGINT) % {bucket_seconds})
                ) AS bar_ts
            FROM {source_alias}
        ),
        bucket_stats AS (
            SELECT
                bar_ts,
                count(*) AS component_count,
                count(DISTINCT ts) AS distinct_component_ts,
                min(ts) AS first_component_ts,
                max(ts) AS last_component_ts,
                count(DISTINCT exchange) AS exchange_count,
                count(DISTINCT market_type) AS market_type_count
            FROM buckets
            GROUP BY symbol, bar_ts
        )
    """


def apply_source_union_frame(
    frame: pd.DataFrame,
    policy: SourceUnionPolicy | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    resolved = policy or DEFAULT_SOURCE_UNION
    if frame.empty:
        return frame.copy(), {
            "physical_rows": 0,
            "selected_rows": 0,
            "within_source_duplicate_rows": 0,
            "unlisted_rows": 0,
        }
    working = frame.copy()
    physical_rows = int(len(working))
    key = ["symbol", "ts", "source"]
    within = int(working.duplicated(subset=key, keep=False).sum()) if set(key).issubset(working.columns) else 0
    if within:
        raise ValueError(f"within-source duplicate business keys: {within} rows")
    unlisted_rows = 0
    if resolved.priority and not resolved.passthrough:
        listed = set(resolved.priority)
        unlisted_mask = ~working["source"].astype("string").isin(listed)
        unlisted_rows = int(unlisted_mask.sum())
        if resolved.reject_unlisted:
            working = working.loc[~unlisted_mask].copy()
        rank = {source: index for index, source in enumerate(resolved.priority)}
        working["_source_rank"] = working["source"].map(lambda value: rank.get(str(value), 999))
        working = working.sort_values(
            ["exchange", "symbol", "market_type", "timeframe", "ts", "_source_rank", "source"],
            kind="stable",
        )
        working = working.drop_duplicates(
            subset=["exchange", "symbol", "market_type", "timeframe", "ts"],
            keep="first",
        ).drop(columns=["_source_rank"])
    return working.reset_index(drop=True), {
        "physical_rows": physical_rows,
        "selected_rows": int(len(working)),
        "within_source_duplicate_rows": within,
        "unlisted_rows": unlisted_rows,
        "priority_union_version": resolved.version,
    }


def _exclusion_select_sql(output_timeframe: str) -> str:
    spec = RESAMPLE_SPECS[output_timeframe]
    component_count = spec["component_count"]
    last_offset = (component_count - 1) * INPUT_SECONDS
    return f"""
        SELECT
            count(*) AS candidate_buckets,
            count(*) FILTER (
                WHERE component_count != {component_count}
                   OR distinct_component_ts != {component_count}
                   OR first_component_ts != bar_ts
                   OR last_component_ts != bar_ts + INTERVAL '{last_offset} seconds'
                   OR exchange_count != 1
                   OR market_type_count != 1
            ) AS excluded_incomplete_buckets
        FROM bucket_stats
    """


def aggregate_complete_bars(
    frame: pd.DataFrame,
    output_timeframe: str,
    *,
    policy: SourceUnionPolicy | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if output_timeframe not in RESAMPLE_SPECS:
        raise ValueError(f"unsupported output timeframe: {output_timeframe}")
    selected, union_stats = apply_source_union_frame(frame, policy)
    if selected.empty:
        return selected.copy(), {
            **union_stats,
            "output_rows": 0,
            "excluded_incomplete_buckets": 0,
            "formula_version": FORMULA_VERSION,
        }
    connection = duckdb.connect()
    connection.execute("SET TimeZone='UTC'")
    connection.register("input_rows", selected)
    source_sql, source_params = source_priority_sql(
        SourceUnionPolicy(version="passthrough", priority=(), passthrough=True),
        alias="input_rows",
    )
    legal_sql = _legal_component_sql("selected")
    query = f"""
        WITH selected AS ({source_sql}),
        legal AS ({legal_sql}),
        {resample_cte_sql(output_timeframe, source_alias="legal")}
        SELECT * FROM complete_bars
    """
    output = connection.execute(query, source_params).fetch_df()
    excluded = connection.execute(
        f"""
        WITH selected AS ({source_sql}),
        legal AS ({legal_sql}),
        {resample_exclusion_cte_sql(output_timeframe, source_alias="legal")}
        {_exclusion_select_sql(output_timeframe)}
        """,
        source_params,
    ).fetch_df().iloc[0]
    connection.close()
    if "ts" in output.columns:
        output["ts"] = pd.to_datetime(output["ts"], utc=True)
        if getattr(output["ts"].dt, "tz", None) is None:
            output["ts"] = output["ts"].dt.tz_localize("UTC")
    if "is_closed" in output.columns:
        output["is_closed"] = output["is_closed"].astype(bool)
    stats = {
        **union_stats,
        "legal_input_rows": int(len(selected)),
        "output_rows": int(len(output)),
        "candidate_buckets": int(excluded["candidate_buckets"]),
        "excluded_incomplete_buckets": int(excluded["excluded_incomplete_buckets"]),
        "formula_version": FORMULA_VERSION,
        "null_fill_policy": NULL_FILL_POLICY,
        "output_timeframe": output_timeframe,
        "required_component_count": RESAMPLE_SPECS[output_timeframe]["component_count"],
        "primary_phase_utc": "00:00",
    }
    return output.reset_index(drop=True), stats


def mixed_source_label(sources: Iterable[str]) -> str:
    return make_composite_source(tuple(sources))


def aggregation_impl_sha256() -> str:
    """Content identity of the aggregation implementation module, not the outer CLI."""

    return sha256_file(Path(__file__))


def _normalize_cutoff(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def verify_existing_derived_publish(
    *,
    published_root: Path,
    dataset_id: str,
    input_fingerprint: str,
    formula_version: str,
    cache_dir: Path | None = None,
    cutoff_exclusive_utc: str | None = None,
    priority_union_version: str | None = None,
    aggregation_impl_sha256: str | None = None,
) -> dict[str, Any]:
    if not published_root.exists():
        return {"status": "missing", "path": str(published_root)}
    manifest_path = published_root / DATASET_MANIFEST_FILENAME
    if not manifest_path.exists():
        raise FileExistsError(
            f"published directory {published_root} exists without {DATASET_MANIFEST_FILENAME}"
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded_id = str(payload.get("dataset_id") or "")
    if recorded_id != dataset_id:
        raise FileExistsError(
            f"published {published_root} has dataset_id {recorded_id!r}, expected {dataset_id!r}"
        )
    mismatches: list[str] = []
    recorded_input = str(payload.get("input_manifest_sha256") or "")
    if recorded_input != input_fingerprint:
        mismatches.append(f"input {recorded_input} != {input_fingerprint}")
    recorded_formula = str(payload.get("aggregation_formula_version") or "")
    if recorded_formula != formula_version:
        mismatches.append(f"formula {recorded_formula} != {formula_version}")
    recorded_cutoff = _normalize_cutoff(payload.get("cutoff_exclusive_utc"))
    requested_cutoff = _normalize_cutoff(cutoff_exclusive_utc)
    if recorded_cutoff != requested_cutoff:
        mismatches.append(f"cutoff {recorded_cutoff!r} != {requested_cutoff!r}")
    if priority_union_version is not None:
        recorded_union = str(payload.get("priority_union_version") or "")
        if recorded_union != priority_union_version:
            mismatches.append(f"union {recorded_union} != {priority_union_version}")
    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    if aggregation_impl_sha256 is not None:
        recorded_impl = str(
            payload.get("aggregation_impl_sha256")
            or extra.get("aggregation_impl_sha256")
            or ""
        )
        if recorded_impl and recorded_impl != aggregation_impl_sha256:
            mismatches.append(f"aggregation impl {recorded_impl} != {aggregation_impl_sha256}")
    if mismatches:
        raise FileExistsError(
            f"published {dataset_id} identity changed ({mismatches}); "
            "publish a new dataset version instead of treating this as already_published"
        )
    recorded_fp = (
        payload.get("parquet_inventory_fingerprint")
        or extra.get("parquet_inventory_fingerprint")
    )
    actual_fp = resolve_parquet_inventory_fingerprint(
        published_root,
        cache_dir=None,
        expected=str(recorded_fp) if recorded_fp else None,
        mode="strict_content",
    )
    if recorded_fp and actual_fp != recorded_fp:
        raise ValueError(
            f"published {dataset_id} parquet files no longer match the frozen fingerprint"
        )
    return {
        "status": "already_published",
        "path": str(published_root),
        "input_manifest_sha256": recorded_input,
        "parquet_inventory_fingerprint": actual_fp,
        "builder_sha256": payload.get("builder_sha256"),
        "content_fingerprint": payload.get("content_fingerprint"),
        "cutoff_exclusive_utc": payload.get("cutoff_exclusive_utc"),
        "priority_union_version": payload.get("priority_union_version"),
    }


def _connect() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    connection.execute("SET TimeZone='UTC'")
    connection.execute("SET enable_progress_bar=false")
    connection.execute("SET preserve_insertion_order=false")
    connection.execute("SET temp_directory='/tmp/duckdb-ohlcv-resample'")
    return connection


def build_derived_ohlcv(
    *,
    input_files: list[Path],
    output_timeframe: str,
    staging_root: Path,
    policy: SourceUnionPolicy | None = None,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
    append: bool = False,
    write_stats: bool = True,
    skip_exclusion: bool = False,
) -> dict[str, Any]:
    if output_timeframe not in RESAMPLE_SPECS:
        raise ValueError(f"unsupported output timeframe: {output_timeframe}")
    if staging_root.exists() and not append:
        raise FileExistsError(f"staging root already exists: {staging_root}")
    resolved = policy or DEFAULT_SOURCE_UNION
    staging_root.mkdir(parents=True, exist_ok=append)
    ohlcv_root = staging_root / "ohlcv"
    ohlcv_root.mkdir(parents=True, exist_ok=True)
    Path("/tmp/duckdb-ohlcv-resample").mkdir(parents=True, exist_ok=True)
    start_ts = None if start is None else require_aware_utc(start, field="start")
    end_ts = None if end is None else require_aware_utc(end, field="end")
    filters = ["1=1"]
    params: list[Any] = [[str(path) for path in input_files]]
    if start_ts is not None:
        filters.append("ts >= ?")
        params.append(start_ts.to_pydatetime())
    if end_ts is not None:
        filters.append("ts < ?")
        params.append(end_ts.to_pydatetime())
    source_sql, source_params = source_priority_sql(resolved, alias="raw")
    params.extend(source_params)
    legal_sql = _legal_component_sql("selected")
    bucket_seconds = RESAMPLE_SPECS[output_timeframe]["bucket_seconds"]
    output_select = "SELECT * FROM complete_bars"
    output_params: list[Any] = []
    if end_ts is not None:
        output_select = (
            f"SELECT * FROM complete_bars "
            f"WHERE (ts + INTERVAL '{bucket_seconds} seconds') <= ?"
        )
        output_params.append(end_ts.to_pydatetime())
    copy_sql = f"""
        COPY (
            WITH raw AS (
                SELECT *
                FROM read_parquet(?, hive_partitioning = false, union_by_name = true)
                WHERE {' AND '.join(filters)}
            ),
            selected AS ({source_sql}),
            legal AS ({legal_sql}),
            {resample_cte_sql(output_timeframe, source_alias="legal")}
            {output_select}
        ) TO '{ohlcv_root.as_posix()}'
        (FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY (date), OVERWRITE_OR_IGNORE)
    """
    connection = _connect()
    try:
        dup = connection.execute(
            f"""
            SELECT count(*) - count(DISTINCT (symbol, ts, source)) AS within_source_duplicate_rows
            FROM read_parquet(?, hive_partitioning = false, union_by_name = true)
            WHERE {' AND '.join(filters)}
            """,
            params[: 1 + (1 if start is not None else 0) + (1 if end is not None else 0)],
        ).fetchone()[0]
        if int(dup):
            raise ValueError(f"input has {dup} within-source duplicate keys; refusing derived build")
        connection.execute(copy_sql, [*params, *output_params])
        if skip_exclusion:
            excluded = {"candidate_buckets": None, "excluded_incomplete_buckets": None}
        else:
            excluded = connection.execute(
                f"""
                WITH raw AS (
                    SELECT *
                    FROM read_parquet(?, hive_partitioning = false, union_by_name = true)
                    WHERE {' AND '.join(filters)}
                ),
                selected AS ({source_sql}),
                legal AS ({legal_sql}),
                {resample_exclusion_cte_sql(output_timeframe, source_alias="legal")}
                {_exclusion_select_sql(output_timeframe)}
                """,
                params,
            ).fetch_df().iloc[0]
        parquet_glob = f"{ohlcv_root.as_posix()}/**/*.parquet"
        produced = list(ohlcv_root.rglob("*.parquet"))
        if not produced:
            summary = {
                "output_rows": 0,
                "distinct_keys": 0,
                "symbols": 0,
                "start_ts": None,
                "end_ts": None,
                "mixed_source_rows": 0,
            }
            source_counts = pd.DataFrame(columns=["source", "rows"])
        else:
            summary = connection.execute(
                f"""
                SELECT
                    count(*) AS output_rows,
                    count(DISTINCT (symbol, ts)) AS distinct_keys,
                    count(DISTINCT symbol) AS symbols,
                    min(ts) AS start_ts,
                    max(ts) AS end_ts,
                    count(*) FILTER (WHERE starts_with(CAST(source AS VARCHAR), 'composite:')) AS mixed_source_rows
                FROM read_parquet('{parquet_glob}', hive_partitioning=true, union_by_name=true)
                """
            ).fetch_df().iloc[0]
            source_counts = connection.execute(
                f"""
                SELECT source, count(*) AS rows
                FROM read_parquet('{parquet_glob}', hive_partitioning=true, union_by_name=true)
                GROUP BY 1
                ORDER BY rows DESC
                """
            ).fetch_df()
    finally:
        connection.close()
    inventory = parquet_inventory(staging_root)
    stats = {
        "output_timeframe": output_timeframe,
        "formula_version": FORMULA_VERSION,
        "priority_union_version": resolved.version,
        "null_fill_policy": NULL_FILL_POLICY,
        "required_component_count": RESAMPLE_SPECS[output_timeframe]["component_count"],
        "primary_phase_utc": "00:00",
        "candidate_buckets": (
            None if excluded["candidate_buckets"] is None else int(excluded["candidate_buckets"])
        ),
        "excluded_incomplete_buckets": (
            None
            if excluded["excluded_incomplete_buckets"] is None
            else int(excluded["excluded_incomplete_buckets"])
        ),
        "output_rows": int(summary["output_rows"]),
        "distinct_keys": int(summary["distinct_keys"]),
        "symbols": int(summary["symbols"]),
        "start_utc": pd.Timestamp(summary["start_ts"]).isoformat() if pd.notna(summary["start_ts"]) else None,
        "end_utc": pd.Timestamp(summary["end_ts"]).isoformat() if pd.notna(summary["end_ts"]) else None,
        "mixed_source_rows": int(summary["mixed_source_rows"]),
        "source_counts": {
            str(row["source"]): int(row["rows"]) for _, row in source_counts.iterrows()
        },
        "file_count": len(inventory),
        "bytes": int(sum(item["size"] for item in inventory)),
        "parquet_inventory_fingerprint": inventory_fingerprint(inventory),
        "staging_root": str(staging_root),
        "cutoff_exclusive_utc": None if end_ts is None else end_ts.isoformat(),
        "input_start_utc": None if start_ts is None else start_ts.isoformat(),
        "input_end_utc": None if end_ts is None else end_ts.isoformat(),
    }
    if stats["output_rows"] != stats["distinct_keys"]:
        raise ValueError(
            f"derived {output_timeframe} has duplicate business keys: "
            f"rows={stats['output_rows']} keys={stats['distinct_keys']}"
        )
    if write_stats:
        write_canonical_json(staging_root / "build_stats.json", stats)
    return stats


def publish_staging_dataset(
    *,
    staging_root: Path,
    published_root: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    if not staging_root.exists():
        raise FileNotFoundError(f"staging root missing: {staging_root}")
    write_canonical_json(staging_root / DATASET_MANIFEST_FILENAME, manifest)
    published_root.parent.mkdir(parents=True, exist_ok=True)
    if published_root.exists():
        existing = published_root / DATASET_MANIFEST_FILENAME
        if existing.exists():
            current = json.loads(existing.read_text(encoding="utf-8"))
            current_fp = current.get("content_fingerprint")
            new_fp = manifest.get("content_fingerprint")
            if current_fp and new_fp and current_fp == new_fp:
                shutil.rmtree(staging_root)
                return {"status": "already_published", "path": str(published_root)}
        raise FileExistsError(
            f"refusing to overwrite published dataset {published_root}; "
            "create a new dataset_id / vN directory instead"
        )
    os.rename(staging_root, published_root)
    return {"status": "published", "path": str(published_root)}


def derived_manifest(
    *,
    dataset_id: str,
    status: str,
    timeframe: str,
    physical_root: str,
    input_dataset_id: str,
    input_manifest_sha256: str,
    builder_path: str,
    builder_sha256: str,
    stats: dict[str, Any],
    extra: dict[str, Any] | None = None,
    declared_scope: str = "FULL_MARKET",
) -> DatasetManifest:
    payload = DatasetManifest(
        schema_version="1.0",
        dataset_id=dataset_id,
        layer="derived",
        status=status,
        declared_scope=declared_scope,
        exchange="binance",
        market_type="perp",
        timeframe=timeframe,
        physical_root=physical_root,
        source_adjudication="15m priority union v1 then complete-bucket resample",
        priority_union_version=PRIORITY_UNION_VERSION,
        aggregation_formula_version=FORMULA_VERSION,
        input_dataset_id=input_dataset_id,
        input_manifest_sha256=input_manifest_sha256,
        builder_path=builder_path,
        builder_sha256=builder_sha256,
        generated_at=utc_now_iso(),
        cutoff_exclusive_utc=stats.get("cutoff_exclusive_utc"),
        start_utc=stats.get("start_utc"),
        end_utc=stats.get("end_utc"),
        file_count=int(stats.get("file_count") or 0),
        bytes=int(stats.get("bytes") or 0),
        rows=int(stats.get("output_rows") or 0),
        distinct_business_keys=int(stats.get("distinct_keys") or 0),
        duplicate_key_rows=0,
        symbol_count=int(stats.get("symbols") or 0),
        rebuildable=True,
        rebuild_command=stats.get("rebuild_command") or "",
        quality_status=CANONICAL_DERIVED_QUALITY,
        content_fingerprint="",
        extra=extra or {
            "null_fill_policy": NULL_FILL_POLICY,
            "excluded_incomplete_buckets": stats.get("excluded_incomplete_buckets"),
            "mixed_source_rows": stats.get("mixed_source_rows"),
            "source_counts": stats.get("source_counts"),
            "parquet_inventory_fingerprint": stats.get("parquet_inventory_fingerprint"),
            "aggregation_module": "strategy_lab.data.resample",
            "aggregation_impl_sha256": stats.get("aggregation_impl_sha256") or aggregation_impl_sha256(),
            "input_snapshot_fingerprint": stats.get("input_parquet_inventory_fingerprint")
            or stats.get("input_manifest_sha256"),
        },
    )
    return payload.with_fingerprint()
