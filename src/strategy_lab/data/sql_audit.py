from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from strategy_lab.data.authenticity import (
    DEFAULT_BLOCKED_SOURCE_PATTERNS,
    DEFAULT_REAL_SOURCE_ALLOWLIST,
)
from strategy_lab.data.sessions import timeframe_delta

SQL_AUDIT_RULE_VERSION = "binance_ohlcv_sql_audit_v2"
REQUIRED_OHLCV_COLUMNS = (
    "ts",
    "exchange",
    "symbol",
    "market_type",
    "timeframe",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trade_count",
    "vwap",
    "is_closed",
    "source",
)
VARCHAR_COLUMNS = {"exchange", "symbol", "market_type", "timeframe", "source"}
FLOAT_COLUMNS = {"open", "high", "low", "close", "volume", "quote_volume", "vwap", "trade_count"}
BOOLEAN_COLUMNS = {"is_closed"}


def timeframe_seconds(timeframe: str) -> int:
    return int(timeframe_delta(timeframe).total_seconds())


def unverified_source_sql(column: str = "source") -> str:
    src = f"lower(trim({column}))"
    parts = (
        f"list_filter(string_split(replace({src}, 'composite:', ''), '+'), "
        "part -> length(trim(part)) > 0)"
    )
    part_bad = (
        "NOT list_contains(allowed_sources, trim(part)) "
        "OR len(list_filter(blocked_patterns, p -> contains(trim(part), p))) > 0"
    )
    atomic_bad = (
        f"NOT list_contains(allowed_sources, {src}) "
        f"OR len(list_filter(blocked_patterns, p -> contains({src}, p))) > 0"
    )
    return f"""
    (
      {column} IS NULL
      OR (
        starts_with({src}, 'composite:')
        AND (
          len({parts}) < 2
          OR len(list_filter({parts}, part -> {part_bad})) > 0
        )
      )
      OR (
        NOT starts_with({src}, 'composite:')
        AND ({atomic_bad})
      )
    )
    """


def describe_one_parquet(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
) -> dict[str, str]:
    described = connection.execute(
        "DESCRIBE SELECT * FROM read_parquet(?, hive_partitioning = false, union_by_name = false) LIMIT 0",
        [str(path)],
    ).fetch_df()
    return {str(row["column_name"]): str(row["column_type"]) for _, row in described.iterrows()}


def describe_parquet_columns(
    connection: duckdb.DuckDBPyConnection,
    files: list[Path],
) -> list[str]:
    if not files:
        return []
    return list(describe_one_parquet(connection, files[0]))


def _type_allowed(column: str, declared: str) -> bool:
    upper = declared.upper()
    if column == "ts":
        return "TIME ZONE" in upper and "TIMESTAMP" in upper
    if column in BOOLEAN_COLUMNS:
        return upper == "BOOLEAN"
    if column in VARCHAR_COLUMNS:
        return "VARCHAR" in upper or "TEXT" in upper
    if column in FLOAT_COLUMNS:
        return any(token in upper for token in ("DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "BIGINT", "INTEGER"))
    return True


def _type_class(column: str, declared: str) -> str:
    if not _type_allowed(column, declared):
        return f"illegal:{declared}"
    if column == "ts":
        return "timestamptz"
    if column in BOOLEAN_COLUMNS:
        return "boolean"
    if column in VARCHAR_COLUMNS:
        return "varchar"
    if column in FLOAT_COLUMNS:
        return "numeric"
    return declared.upper()


def audit_parquet_file_schemas(
    connection: duckdb.DuckDBPyConnection,
    files: list[Path],
    *,
    expected_exchange: str | None = None,
    expected_market_type: str | None = None,
    expected_timeframe: str | None = None,
) -> list[str]:
    errors: list[str] = []
    reference: dict[str, str] | None = None
    for path in files:
        try:
            types = describe_one_parquet(connection, path)
        except Exception as exc:  # noqa: BLE001 - schema probe must stay fail-closed
            errors.append(f"{path.name}: unreadable parquet schema ({exc})")
            continue
        missing = [name for name in REQUIRED_OHLCV_COLUMNS if name not in types]
        if missing:
            errors.append(f"{path.name}: missing columns {missing}")
            continue
        for column in REQUIRED_OHLCV_COLUMNS:
            if not _type_allowed(column, types[column]):
                errors.append(
                    f"{path.name}: column {column} has type {types[column]!r}, "
                    "which is not allowed for trusted OHLCV"
                )
        required_types = {name: _type_class(name, types[name]) for name in REQUIRED_OHLCV_COLUMNS}
        if reference is None:
            reference = required_types
        elif required_types != reference:
            errors.append(f"{path.name}: required-column types differ from the first file")
    if expected_exchange or expected_market_type or expected_timeframe:
        # Identity is checked on rows after schema; keep a reminder in schema errors only
        # when files themselves cannot be described.
        pass
    return errors


def _quality_status(schema_errors: list[str], blockers: dict[str, Any]) -> str:
    if schema_errors:
        return "FAIL"
    for key, value in blockers.items():
        if key == "schema_errors":
            continue
        if int(value or 0) > 0:
            return "FAIL"
    return "PASS"


def audit_selected_sql(
    connection: duckdb.DuckDBPyConnection,
    *,
    selected_cte: str,
    params: list[Any],
    timeframe: str,
    require_closed: bool,
    allowed_sources: tuple[str, ...] = DEFAULT_REAL_SOURCE_ALLOWLIST,
    blocked_source_patterns: tuple[str, ...] = DEFAULT_BLOCKED_SOURCE_PATTERNS,
    columns: list[str] | None = None,
    cutoff_unclosed_excluded_rows: int = 0,
    expected_exchange: str | None = None,
    expected_market_type: str | None = None,
    files: list[Path] | None = None,
) -> dict[str, Any]:
    schema_errors: list[str] = []
    if files:
        schema_errors.extend(
            audit_parquet_file_schemas(
                connection,
                files,
                expected_exchange=expected_exchange,
                expected_market_type=expected_market_type,
                expected_timeframe=timeframe,
            )
        )
    present = set(columns or [])
    missing = [name for name in REQUIRED_OHLCV_COLUMNS if name not in present]
    if missing:
        schema_errors.append(f"missing required columns: {missing}")
    if schema_errors:
        return {
            "rule_version": SQL_AUDIT_RULE_VERSION,
            "quality_status": "FAIL",
            "rows": 0,
            "trusted": False,
            "schema_errors": schema_errors,
            "blockers": {"schema_errors": schema_errors},
            "source_counts": {},
            "duplicate_rows": 0,
            "open_rows": 0,
            "timeframe_mismatches": 0,
            "internal_missing_bars": 0,
            "unaligned_gap_transitions": 0,
            "cutoff_unclosed_excluded_rows": int(cutoff_unclosed_excluded_rows),
        }

    seconds = timeframe_seconds(timeframe)
    micros = seconds * 1_000_000
    allowed = [source.strip().lower() for source in allowed_sources]
    blocked = [pattern.strip().lower() for pattern in blocked_source_patterns]
    source_pred = unverified_source_sql("source")
    numeric_cols = [name for name in FLOAT_COLUMNS]
    finite_pred = " OR ".join(f"NOT isfinite({name})" for name in numeric_cols)
    exchange_pred = "FALSE"
    market_pred = "FALSE"
    identity_params: list[Any] = []
    if expected_exchange:
        exchange_pred = "lower(trim(exchange)) != lower(trim(?))"
        identity_params.append(expected_exchange)
    if expected_market_type:
        market_pred = "lower(trim(market_type)) != lower(trim(?))"
        identity_params.append(expected_market_type)
    config_and_selected = f"""
        config AS (
            SELECT ?::VARCHAR[] AS allowed_sources, ?::VARCHAR[] AS blocked_patterns
        ),
        {selected_cte}
    """
    query_params = [allowed, blocked, *params]
    row = connection.execute(
        f"""
        WITH {config_and_selected}
        SELECT
            count(*) AS rows,
            count(DISTINCT symbol) AS symbol_count,
            min(ts) AS start_ts,
            max(ts) AS end_ts,
            count(*) - count(DISTINCT (exchange, symbol, market_type, timeframe, ts))
                AS duplicate_business_key_rows,
            count(*) FILTER (
                WHERE ts IS NULL OR exchange IS NULL OR symbol IS NULL
                   OR market_type IS NULL OR timeframe IS NULL
                   OR open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL
                   OR volume IS NULL OR quote_volume IS NULL OR trade_count IS NULL
                   OR vwap IS NULL OR is_closed IS NULL OR source IS NULL
                   OR trim(exchange) = ''
                   OR trim(market_type) = ''
                   OR trim(timeframe) = ''
            ) AS critical_null_rows,
            count(*) FILTER (WHERE {finite_pred}) AS non_finite_rows,
            count(*) FILTER (
                WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0
                   OR high < greatest(open, close, low)
                   OR low > least(open, close, high)
                   OR vwap <= 0
            ) AS illegal_ohlc_rows,
            count(*) FILTER (
                WHERE volume < 0 OR quote_volume < 0
                   OR trade_count < 0
                   OR NOT isfinite(trade_count)
                   OR trade_count != floor(trade_count)
            ) AS negative_volume_or_count_rows,
            count(*) FILTER (WHERE {source_pred}) AS unverified_source_rows,
            count(*) FILTER (WHERE is_closed IS DISTINCT FROM TRUE) AS open_rows,
            count(*) FILTER (
                WHERE lower(trim(timeframe)) != lower(trim(?))
            ) AS timeframe_mismatches,
            count(*) FILTER (WHERE {exchange_pred}) AS exchange_mismatches,
            count(*) FILTER (WHERE {market_pred}) AS market_type_mismatches,
            count(*) FILTER (
                WHERE epoch_us(ts) % {micros} != 0
            ) AS off_grid_rows
        FROM selected, config
        """,
        [*query_params, timeframe, *identity_params],
    ).fetch_df().iloc[0]

    sources = connection.execute(
        f"""
        WITH {selected_cte}
        SELECT source, count(*) AS rows
        FROM selected
        GROUP BY 1
        ORDER BY rows DESC
        """,
        params,
    ).fetch_df()
    source_counts = {str(item["source"]): int(item["rows"]) for _, item in sources.iterrows()}

    gaps = connection.execute(
        f"""
        WITH {selected_cte},
        ordered AS (
            SELECT
                symbol,
                ts,
                lag(ts) OVER (PARTITION BY symbol ORDER BY ts) AS prev_ts
            FROM selected
        ),
        gap_rows AS (
            SELECT datediff('microsecond', prev_ts, ts) AS delta_us
            FROM ordered
            WHERE prev_ts IS NOT NULL
        )
        SELECT
            count(*) FILTER (WHERE delta_us > {micros}) AS internal_gap_transitions,
            coalesce(
                sum(
                    CASE
                        WHEN delta_us > {micros} THEN (delta_us / {micros}) - 1
                        ELSE 0
                    END
                ),
                0
            ) AS internal_missing_bars,
            count(*) FILTER (
                WHERE delta_us > {micros} AND (delta_us % {micros}) != 0
            ) AS unaligned_gap_transitions
        FROM gap_rows
        """,
        params,
    ).fetch_df().iloc[0]

    blockers: dict[str, Any] = {
        "schema_errors": schema_errors,
        "duplicate_business_key_rows": int(row["duplicate_business_key_rows"] or 0),
        "critical_null_rows": int(row["critical_null_rows"] or 0),
        "non_finite_rows": int(row["non_finite_rows"] or 0),
        "illegal_ohlc_rows": int(row["illegal_ohlc_rows"] or 0),
        "negative_volume_or_count_rows": int(row["negative_volume_or_count_rows"] or 0),
        "unverified_source_rows": int(row["unverified_source_rows"] or 0),
        "timeframe_mismatches": int(row["timeframe_mismatches"] or 0),
        "exchange_mismatches": int(row["exchange_mismatches"] or 0),
        "market_type_mismatches": int(row["market_type_mismatches"] or 0),
        "off_grid_rows": int(row["off_grid_rows"] or 0),
        "unaligned_gap_transitions": int(gaps["unaligned_gap_transitions"] or 0),
    }
    if require_closed:
        blockers["open_rows"] = int(row["open_rows"] or 0)

    quality_status = _quality_status(schema_errors, blockers)
    start_ts = row["start_ts"]
    end_ts = row["end_ts"]
    visible_blockers = {
        key: value
        for key, value in blockers.items()
        if (key == "schema_errors" and value) or (key != "schema_errors" and int(value) > 0)
    }
    return {
        "rule_version": SQL_AUDIT_RULE_VERSION,
        "quality_status": quality_status,
        "rows": int(row["rows"] or 0),
        "symbol_count": int(row["symbol_count"] or 0),
        "start_utc": pd.Timestamp(start_ts).isoformat() if pd.notna(start_ts) else None,
        "end_utc": pd.Timestamp(end_ts).isoformat() if pd.notna(end_ts) else None,
        "duplicate_rows": int(row["duplicate_business_key_rows"] or 0),
        "duplicate_business_key_rows": int(row["duplicate_business_key_rows"] or 0),
        "critical_null_rows": int(row["critical_null_rows"] or 0),
        "non_finite_rows": int(row["non_finite_rows"] or 0),
        "illegal_ohlc_rows": int(row["illegal_ohlc_rows"] or 0),
        "negative_volume_or_count_rows": int(row["negative_volume_or_count_rows"] or 0),
        "unverified_source_rows": int(row["unverified_source_rows"] or 0),
        "open_rows": int(row["open_rows"] or 0),
        "timeframe_mismatches": int(row["timeframe_mismatches"] or 0),
        "exchange_mismatches": int(row["exchange_mismatches"] or 0),
        "market_type_mismatches": int(row["market_type_mismatches"] or 0),
        "off_grid_rows": int(row["off_grid_rows"] or 0),
        "internal_gap_transitions": int(gaps["internal_gap_transitions"] or 0),
        "internal_missing_bars": int(gaps["internal_missing_bars"] or 0),
        "unaligned_gap_transitions": int(gaps["unaligned_gap_transitions"] or 0),
        "missing_bars": int(gaps["internal_missing_bars"] or 0),
        "unexpected_intervals": int(gaps["unaligned_gap_transitions"] or 0),
        "cutoff_unclosed_excluded_rows": int(cutoff_unclosed_excluded_rows),
        "schema_errors": schema_errors,
        "source_counts": source_counts,
        "blockers": visible_blockers,
        "gap_classification": {
            "listing_boundary": (
                "symbol first/last bars are observed span edges, not confirmed listing/delisting"
            ),
            "internal_aligned_gaps": "missing multiples of the timeframe inside a symbol span",
            "unaligned_gaps": "internal jumps that are not a multiple of the timeframe",
            "incomplete_aggregation_buckets": (
                "derived complete-bucket formula drops incomplete windows; "
                "those appear as aligned internal gaps"
            ),
        },
        "trusted": quality_status == "PASS",
        "row_quality": quality_status,
    }
