#!/usr/bin/env python3
"""Round 3 quote_volume RCA. Independent of resample_cte_sql / aggregate_complete_bars.

Traces every material legacy-1h vs 15m hour-sum mismatch for the six assets
to local normalized and raw parquet evidence. Does not download missing raw.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from strategy_lab.data.catalog import (
    BINANCE_PERP_15M_NORMALIZED_V1,
    BINANCE_PERP_1H_NORMALIZED_LEGACY,
    BINANCE_PERP_4H_FROM_15M_V1,
    DatasetRegistry,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import sha256_file, write_canonical_json
from strategy_lab.data.settings import default_settings

ROOT = Path(__file__).resolve().parents[4]
ARTIFACT_DIR = ROOT / "research/platform/data-lake-governance/artifacts"
DIAGNOSTIC = (
    ROOT
    / "research/platform/data-lake-governance/diagnostics"
    / "binance-ohlcv-volume-rca-r3-2026-09-03.md"
)
JSON_OUT = ARTIFACT_DIR / "binance_ohlcv_volume_rca_r3_2026-09-03.json"
CSV_OUT = ARTIFACT_DIR / "binance_ohlcv_volume_rca_r3_six_asset_2026-09-03.csv"
TRACE_OUT = ARTIFACT_DIR / "binance_ohlcv_volume_rca_r3_hour_trace_2026-09-03.csv"
COMP_OUT = ARTIFACT_DIR / "binance_ohlcv_volume_rca_r3_components_2026-09-03.csv"

SIX_ASSETS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "BNB/USDT:USDT",
    "TRX/USDT:USDT",
    "HYPE/USDT:USDT",
]

# Frozen before inspecting residuals. Do not widen after the fact.
TOLERANCE = {
    "open": {"abs": 0.0, "rel": 0.0},
    "high": {"abs": 0.0, "rel": 0.0},
    "low": {"abs": 0.0, "rel": 0.0},
    "close": {"abs": 0.0, "rel": 0.0},
    "volume": {"abs": 1e-9, "rel": 1e-12},
    "quote_volume": {"abs": 1e-6, "rel": 1e-10},
    "trade_count": {"abs": 0.0, "rel": 0.0},
    "vwap": {"abs": 1e-8, "rel": 1e-10},
}

VISION = "binance_vision_kline_monthly"
API = "binance_futures_kline_api"


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    con.execute("SET enable_progress_bar=false")
    return con


def exceeds(left: object, right: object, spec: dict[str, float]) -> bool:
    if pd.isna(left) or pd.isna(right):
        return True
    abs_err = abs(float(left) - float(right))
    denom = max(abs(float(right)), 1e-12)
    rel_err = abs_err / denom
    return abs_err > spec["abs"] + 1e-15 and rel_err > spec["rel"]


def md_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "_无数据_"
    columns = list(rows[0].keys())
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []
    for row in rows:
        cells = []
        for column in columns:
            value = row[column]
            if isinstance(value, float):
                cells.append(f"{value:.6g}")
            else:
                cells.append(str(value))
        body.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep, *body])


def parquet_list(root: Path) -> list[str]:
    return [str(path) for path in sorted(root.rglob("*.parquet")) if path.is_file()]


def independent_4h_sql() -> str:
    return """
        legal AS (
            SELECT *
            FROM selected
            WHERE is_closed
              AND open > 0 AND high > 0 AND low > 0 AND close > 0
              AND volume >= 0 AND quote_volume >= 0 AND trade_count >= 0 AND vwap > 0
              AND high >= greatest(open, close, low)
              AND low <= least(open, close, high)
              AND epoch_us(ts) % 900000000 = 0
        ),
        bucketed AS (
            SELECT
                *,
                date_trunc('hour', ts)
                    - (CAST(date_part('hour', ts) AS INTEGER) % 4) * INTERVAL '1 hour' AS bar_ts
            FROM legal
        ),
        agg AS (
            SELECT
                bar_ts AS ts,
                symbol,
                arg_min(open, ts) AS open,
                max(high) AS high,
                min(low) AS low,
                arg_max(close, ts) AS close,
                sum(volume) AS volume,
                sum(quote_volume) AS quote_volume,
                CAST(sum(trade_count) AS BIGINT) AS trade_count,
                CASE WHEN sum(volume) = 0 THEN arg_max(close, ts)
                     ELSE sum(quote_volume) / sum(volume) END AS vwap,
                count(*) AS component_count,
                count(DISTINCT ts) AS distinct_ts,
                min(ts) AS first_ts,
                max(ts) AS last_ts
            FROM bucketed
            GROUP BY symbol, bar_ts
        )
        SELECT *
        FROM agg
        WHERE component_count = 16
          AND distinct_ts = 16
          AND first_ts = ts
          AND last_ts = ts + INTERVAL '225 minutes'
    """


def symbol_file_token(symbol: str) -> str:
    return symbol.lower().replace("/", "_").replace(":", "_")


def raw_path(layout: DataLakeLayout, timeframe: str, ts: pd.Timestamp, symbol: str) -> Path:
    day = pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%d")
    token = symbol_file_token(symbol)
    return (
        layout.raw_dir
        / "ohlcv"
        / "exchange=binance"
        / "market_type=perp"
        / f"timeframe={timeframe}"
        / f"date={day}"
        / f"symbol={token}.parquet"
    )


def load_raw_quotes(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    ts: pd.Timestamp,
    timeframe: str,
) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    hour_end = ts + pd.Timedelta(hours=1)
    columns = {
        str(row[0])
        for row in con.execute(
            "DESCRIBE SELECT * FROM read_parquet(?, hive_partitioning=false, union_by_name=false) LIMIT 0",
            [str(path)],
        ).fetchall()
    }
    ts_col = "open_time" if "open_time" in columns else "ts" if "ts" in columns else None
    if ts_col is None or "quote_volume" not in columns:
        return pd.DataFrame()
    extras = [name for name in ("volume", "source", "is_closed") if name in columns]
    extra_sql = (", " + ", ".join(extras)) if extras else ""
    if timeframe == "1h":
        frame = con.execute(
            f"""
            SELECT {ts_col} AS ts, quote_volume{extra_sql}
            FROM read_parquet(?, hive_partitioning=false, union_by_name=false)
            WHERE {ts_col} = ?
            """,
            [str(path), ts.to_pydatetime()],
        ).fetch_df()
    else:
        frame = con.execute(
            f"""
            SELECT {ts_col} AS ts, quote_volume{extra_sql}
            FROM read_parquet(?, hive_partitioning=false, union_by_name=false)
            WHERE {ts_col} >= ? AND {ts_col} < ?
            ORDER BY {ts_col}
            """,
            [str(path), ts.to_pydatetime(), hour_end.to_pydatetime()],
        ).fetch_df()
    if not frame.empty:
        frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    return frame


def classify_hour(row: dict[str, object], components: pd.DataFrame, native: pd.DataFrame) -> tuple[str, str]:
    hour_ts = pd.Timestamp(row.get("ts_utc") or row.get("ts"))
    if hour_ts.tzinfo is None:
        hour_ts = hour_ts.tz_localize("UTC")
    else:
        hour_ts = hour_ts.tz_convert("UTC")
    if len(components) != 4:
        return "MISSING_OR_DUPLICATE_COMPONENTS", f"15m component count={len(components)}"
    expected = [
        hour_ts,
        hour_ts + pd.Timedelta(minutes=15),
        hour_ts + pd.Timedelta(minutes=30),
        hour_ts + pd.Timedelta(minutes=45),
    ]
    if "ts" not in components.columns:
        return "UNRESOLVED", "normalized 15m query missing ts column"
    got = list(pd.to_datetime(components["ts"], utc=True).sort_values())
    if got != expected:
        return "BOUNDARY_MISALIGNMENT", f"component ts={got}"
    if native.empty:
        return "MISSING_OR_DUPLICATE_COMPONENTS", "native 1h row missing"
    if len(native) != 1:
        return "MISSING_OR_DUPLICATE_COMPONENTS", f"native 1h rows={len(native)}"
    if (not bool(components["is_closed"].all())) or (not bool(native.iloc[0]["is_closed"])):
        return "UNCLOSED_SNAPSHOT", "unclosed 15m or 1h bar"
    native_q = float(native.iloc[0]["quote_volume"])
    native_proxy = float(native.iloc[0]["close"]) * float(native.iloc[0]["volume"])
    if not exceeds(native_q, native_proxy, TOLERANCE["quote_volume"]):
        return "PROXY_FIELD", "native 1h quote_volume equals close*volume within frozen tolerance"
    sources_15m = sorted({str(value) for value in components["source"].tolist()})
    source_1h = str(native.iloc[0]["source"])
    if source_1h not in sources_15m and not any(source_1h in item for item in sources_15m):
        return "SOURCE_REVISION", f"15m sources={sources_15m} native_1h source={source_1h}"
    missing: list[str] = []
    if row.get("raw_15m_missing") or row.get("raw_1h_missing"):
        missing.append("raw parquet")
    if missing:
        return "UNRESOLVED", "missing " + ",".join(missing)
    raw_15m_sum = row.get("raw_15m_quote_sum")
    raw_1h_q = row.get("raw_1h_quote_volume")
    first_15m = row.get("raw_15m_first_quote")
    if raw_15m_sum is None or raw_1h_q is None:
        return "UNRESOLVED", "raw files exist but quote_volume could not be read"
    if first_15m is not None and not exceeds(raw_1h_q, first_15m, TOLERANCE["quote_volume"]):
        return (
            "RAW_1H_EQUALS_FIRST_15M_COMPONENT",
            "raw 1h quote_volume equals the first 15m bar, not the hour sum",
        )
    norm_15m = float(row["quote_volume_15m_sum"])
    norm_1h = float(row["quote_volume_native_1h"])
    if exceeds(raw_15m_sum, norm_15m, TOLERANCE["quote_volume"]) or exceeds(
        raw_1h_q, norm_1h, TOLERANCE["quote_volume"]
    ):
        return "NORMALIZE_MAPPING_DIVERGENCE", "raw quote_volume does not match normalized values"
    return (
        "SEMANTIC_DIFFERENCE_WITH_LOCAL_RAW_EVIDENCE",
        "raw 15m sum and raw 1h quote_volume match normalized files and still differ beyond frozen tolerance",
    )


def main() -> None:
    layout = DataLakeLayout.from_settings(default_settings())
    registry = DatasetRegistry.from_layout(layout)
    files_15m = parquet_list(registry.get(BINANCE_PERP_15M_NORMALIZED_V1).absolute_root(layout))
    files_1h = parquet_list(registry.get(BINANCE_PERP_1H_NORMALIZED_LEGACY).absolute_root(layout))
    files_4h = parquet_list(registry.get(BINANCE_PERP_4H_FROM_15M_V1).absolute_root(layout))
    con = connect()
    summary: dict[str, object] = {
        "round": "R3",
        "tolerance": TOLERANCE,
        "independent_of_production_resample": True,
        "assets": SIX_ASSETS,
    }

    print("independent 15m->4h vs published 4h", flush=True)
    rebuilt = con.execute(
        f"""
        WITH raw15 AS (
            SELECT * FROM read_parquet(?, hive_partitioning=false, union_by_name=true)
            WHERE symbol IN ({", ".join("?" for _ in SIX_ASSETS)})
              AND source IN ('{VISION}', '{API}')
        ),
        ranked AS (
            SELECT *, CASE WHEN source = '{VISION}' THEN 0 ELSE 1 END AS source_rank FROM raw15
        ),
        selected AS (
            SELECT * EXCLUDE (source_rank) FROM ranked
            QUALIFY row_number() OVER (PARTITION BY symbol, ts ORDER BY source_rank, source) = 1
        ),
        {independent_4h_sql()}
        """,
        [files_15m, *SIX_ASSETS],
    ).fetch_df()
    published = con.execute(
        f"""
        SELECT ts, symbol, open, high, low, close, volume, quote_volume, trade_count, vwap
        FROM read_parquet(?, hive_partitioning=false, union_by_name=true)
        WHERE symbol IN ({", ".join("?" for _ in SIX_ASSETS)})
        """,
        [files_4h, *SIX_ASSETS],
    ).fetch_df()
    rebuilt["ts"] = pd.to_datetime(rebuilt["ts"], utc=True)
    published["ts"] = pd.to_datetime(published["ts"], utc=True)
    merged = rebuilt.merge(published, on=["symbol", "ts"], how="outer", suffixes=("_ind", "_pub"), indicator=True)
    fields = ["open", "high", "low", "close", "volume", "quote_volume", "trade_count", "vwap"]
    rebuild_vs_pub = []
    for symbol in SIX_ASSETS:
        part = merged.loc[merged["symbol"].eq(symbol)]
        row = {
            "symbol": symbol,
            "independent_complete_4h": int(part["_merge"].isin(["both", "left_only"]).sum()),
            "published_4h": int(part["_merge"].isin(["both", "right_only"]).sum()),
            "matched": int(part["_merge"].eq("both").sum()),
            "only_independent": int(part["_merge"].eq("left_only").sum()),
            "only_published": int(part["_merge"].eq("right_only").sum()),
        }
        both = part.loc[part["_merge"].eq("both")]
        for field in fields:
            abs_err = (both[f"{field}_ind"] - both[f"{field}_pub"]).abs()
            rel_err = abs_err / both[f"{field}_pub"].abs().clip(lower=1e-12)
            mismatch = [
                exceeds(left, right, TOLERANCE[field])
                for left, right in zip(both[f"{field}_ind"], both[f"{field}_pub"], strict=True)
            ]
            row[f"{field}_mismatches"] = int(sum(mismatch))
            row[f"{field}_max_abs"] = float(abs_err.max()) if len(abs_err) else 0.0
            row[f"{field}_max_rel"] = float(rel_err.max()) if len(rel_err) else 0.0
        rebuild_vs_pub.append(row)
    summary["independent_15m_vs_published_4h"] = rebuild_vs_pub

    print("legacy 1h vs 15m hour sums, all mismatch hours", flush=True)
    native_vs_15m = con.execute(
        f"""
        WITH raw15 AS (
            SELECT * FROM read_parquet(?, hive_partitioning=false, union_by_name=true)
            WHERE symbol IN ({", ".join("?" for _ in SIX_ASSETS)})
              AND source IN ('{VISION}', '{API}')
        ),
        ranked AS (
            SELECT *, CASE WHEN source = '{VISION}' THEN 0 ELSE 1 END AS source_rank FROM raw15
        ),
        selected AS (
            SELECT * EXCLUDE (source_rank) FROM ranked
            QUALIFY row_number() OVER (PARTITION BY symbol, ts ORDER BY source_rank, source) = 1
        ),
        hour15 AS (
            SELECT
                symbol,
                date_trunc('hour', ts) AS ts,
                sum(volume) AS volume_15m_sum,
                sum(quote_volume) AS quote_volume_15m_sum,
                sum(trade_count) AS trade_count_15m_sum,
                count(*) AS components,
                bool_and(is_closed) AS all_closed
            FROM selected
            GROUP BY 1, 2
            HAVING count(*) = 4
               AND min(ts) = date_trunc('hour', min(ts))
               AND max(ts) = date_trunc('hour', min(ts)) + INTERVAL '45 minutes'
        ),
        native1h AS (
            SELECT symbol, ts, volume, quote_volume, trade_count, close, is_closed, source
            FROM read_parquet(?, hive_partitioning=false, union_by_name=true)
            WHERE symbol IN ({", ".join("?" for _ in SIX_ASSETS)})
        )
        SELECT
            hour15.symbol,
            hour15.ts,
            hour15.volume_15m_sum,
            native1h.volume AS volume_native_1h,
            hour15.quote_volume_15m_sum,
            native1h.quote_volume AS quote_volume_native_1h,
            hour15.trade_count_15m_sum,
            native1h.trade_count AS trade_count_native_1h,
            native1h.close,
            native1h.close * native1h.volume AS proxy_close_times_volume,
            native1h.is_closed AS native_is_closed,
            native1h.source AS native_source,
            hour15.all_closed AS components_all_closed
        FROM hour15
        INNER JOIN native1h USING (symbol, ts)
        """,
        [files_15m, *SIX_ASSETS, files_1h, *SIX_ASSETS],
    ).fetch_df()
    native_vs_15m["ts"] = pd.to_datetime(native_vs_15m["ts"], utc=True)
    native_rows = []
    mismatch_hours = []
    for symbol in SIX_ASSETS:
        part = native_vs_15m.loc[native_vs_15m["symbol"].eq(symbol)].copy()
        if part.empty:
            native_rows.append({"symbol": symbol, "status": "no_overlap"})
            continue
        q_abs = (part["quote_volume_15m_sum"] - part["quote_volume_native_1h"]).abs()
        q_rel = q_abs / part["quote_volume_native_1h"].abs().clip(lower=1e-12)
        v_abs = (part["volume_15m_sum"] - part["volume_native_1h"]).abs()
        proxy_abs = (part["quote_volume_native_1h"] - part["proxy_close_times_volume"]).abs()
        q_mismatch = [
            exceeds(a, b, TOLERANCE["quote_volume"])
            for a, b in zip(part["quote_volume_15m_sum"], part["quote_volume_native_1h"], strict=True)
        ]
        native_rows.append(
            {
                "symbol": symbol,
                "overlap_complete_hours": int(len(part)),
                "quote_volume_mismatches": int(sum(q_mismatch)),
                "quote_volume_max_abs": float(q_abs.max()),
                "quote_volume_max_rel": float(q_rel.max()),
                "volume_max_abs": float(v_abs.max()),
                "native_1h_vs_close_x_volume_max_abs": float(proxy_abs.max()),
                "native_1h_equals_proxy": bool(float(proxy_abs.max()) <= 1e-6),
            }
        )
        flagged = part.loc[list(q_mismatch)].copy()
        flagged["abs_err"] = (
            flagged["quote_volume_15m_sum"] - flagged["quote_volume_native_1h"]
        ).abs()
        mismatch_hours.append(flagged)
    hours = pd.concat(mismatch_hours, ignore_index=True) if mismatch_hours else pd.DataFrame()
    summary["legacy_1h_vs_15m_hour_sums"] = native_rows
    summary["material_mismatch_hours"] = int(len(hours))

    traces: list[dict[str, object]] = []
    component_rows: list[dict[str, object]] = []
    if not hours.empty:
        print(f"tracing {len(hours)} mismatch hours to files", flush=True)
        hour_keys = hours[["symbol", "ts"]].drop_duplicates()
        symbols = sorted(hour_keys["symbol"].unique())
        bounds = (hour_keys["ts"].min(), hour_keys["ts"].max() + pd.Timedelta(hours=1))
        comps = con.execute(
            f"""
            WITH raw15 AS (
                SELECT filename, ts, symbol, open, high, low, close, volume, quote_volume,
                       trade_count, vwap, is_closed, source, exchange, market_type, timeframe
                FROM read_parquet(?, filename=true, hive_partitioning=false, union_by_name=true)
                WHERE symbol IN ({", ".join("?" for _ in symbols)})
                  AND ts >= ? AND ts < ?
                  AND source IN ('{VISION}', '{API}')
            ),
            ranked AS (
                SELECT *, CASE WHEN source = '{VISION}' THEN 0 ELSE 1 END AS source_rank FROM raw15
            )
            SELECT * EXCLUDE (source_rank) FROM ranked
            QUALIFY row_number() OVER (PARTITION BY symbol, ts ORDER BY source_rank, source) = 1
            """,
            [files_15m, *symbols, bounds[0].to_pydatetime(), bounds[1].to_pydatetime()],
        ).fetch_df()
        natives = con.execute(
            f"""
            SELECT filename, ts, symbol, open, high, low, close, volume, quote_volume,
                   trade_count, vwap, is_closed, source, exchange, market_type, timeframe
            FROM read_parquet(?, filename=true, hive_partitioning=false, union_by_name=true)
            WHERE symbol IN ({", ".join("?" for _ in symbols)})
              AND ts >= ? AND ts < ?
            """,
            [files_1h, *symbols, bounds[0].to_pydatetime(), bounds[1].to_pydatetime()],
        ).fetch_df()
        comps["ts"] = pd.to_datetime(comps["ts"], utc=True)
        natives["ts"] = pd.to_datetime(natives["ts"], utc=True)
        file_hashes: dict[str, str] = {}

        def hashed(path: str | Path) -> str | None:
            text = str(path)
            if not text or not Path(text).exists():
                return None
            if text not in file_hashes:
                file_hashes[text] = sha256_file(Path(text))
            return file_hashes[text]

        for _, hour in hours.iterrows():
            symbol = str(hour["symbol"])
            ts = pd.Timestamp(hour["ts"])
            hour_end = ts + pd.Timedelta(hours=1)
            hour_comps = comps.loc[comps["symbol"].eq(symbol) & comps["ts"].ge(ts) & comps["ts"].lt(hour_end)].copy()
            hour_native = natives.loc[natives["symbol"].eq(symbol) & natives["ts"].eq(ts)].copy()
            raw_15m = raw_path(layout, "15m", ts, symbol)
            raw_1h = raw_path(layout, "1h", ts, symbol)
            payload = {
                "symbol": symbol,
                "ts_utc": ts.isoformat(),
                "quote_volume_15m_sum": float(hour["quote_volume_15m_sum"]),
                "quote_volume_native_1h": float(hour["quote_volume_native_1h"]),
                "volume_15m_sum": float(hour["volume_15m_sum"]),
                "volume_native_1h": float(hour["volume_native_1h"]),
                "proxy_close_times_volume": float(hour["proxy_close_times_volume"]),
                "abs_err": float(hour["abs_err"]),
                "component_count": int(len(hour_comps)),
                "native_1h_rows": int(len(hour_native)),
                "normalized_15m_files": sorted({str(value) for value in hour_comps["filename"].tolist()}),
                "normalized_1h_files": sorted({str(value) for value in hour_native["filename"].tolist()}),
                "normalized_15m_file_sha256": [
                    hashed(value) for value in sorted({str(item) for item in hour_comps["filename"].tolist()})
                ],
                "normalized_1h_file_sha256": [
                    hashed(value) for value in sorted({str(item) for item in hour_native["filename"].tolist()})
                ],
                "raw_15m_path": str(raw_15m),
                "raw_1h_path": str(raw_1h),
                "raw_15m_missing": not raw_15m.exists(),
                "raw_1h_missing": not raw_1h.exists(),
                "raw_15m_sha256": hashed(raw_15m),
                "raw_1h_sha256": hashed(raw_1h),
                "raw_15m_quote_sum": None,
                "raw_1h_quote_volume": None,
                "raw_15m_first_quote": None,
                "raw_15m_sources": [],
                "raw_1h_sources": [],
                "field_mapping": {
                    "normalized_ts": "ts",
                    "raw_ts": "open_time",
                    "quote_volume": "native quote_volume compared to sum of 15m quote_volume",
                    "proxy": "close * volume is a control only",
                },
            }
            raw_15m_frame = load_raw_quotes(con, raw_15m, ts, "15m")
            raw_1h_frame = load_raw_quotes(con, raw_1h, ts, "1h")
            if not raw_15m_frame.empty:
                payload["raw_15m_quote_sum"] = float(raw_15m_frame["quote_volume"].sum())
                payload["raw_15m_first_quote"] = float(raw_15m_frame.sort_values("ts").iloc[0]["quote_volume"])
                if "source" in raw_15m_frame.columns:
                    payload["raw_15m_sources"] = sorted({str(value) for value in raw_15m_frame["source"].tolist()})
            if not raw_1h_frame.empty:
                payload["raw_1h_quote_volume"] = float(raw_1h_frame.iloc[0]["quote_volume"])
                if "source" in raw_1h_frame.columns:
                    payload["raw_1h_sources"] = sorted({str(value) for value in raw_1h_frame["source"].tolist()})
            classification, note = classify_hour(payload, hour_comps, hour_native)
            payload["classification"] = classification
            payload["classification_note"] = note
            traces.append(payload)
            for _, item in hour_comps.iterrows():
                component_rows.append(
                    {
                        "symbol": symbol,
                        "hour_ts_utc": ts.isoformat(),
                        "component_ts_utc": pd.Timestamp(item["ts"]).isoformat(),
                        "quote_volume": float(item["quote_volume"]),
                        "volume": float(item["volume"]),
                        "is_closed": bool(item["is_closed"]),
                        "source": str(item["source"]),
                        "filename": str(item["filename"]),
                        "file_sha256": hashed(item["filename"]),
                        "layer": "normalized_15m",
                    }
                )
            for _, item in hour_native.iterrows():
                component_rows.append(
                    {
                        "symbol": symbol,
                        "hour_ts_utc": ts.isoformat(),
                        "component_ts_utc": pd.Timestamp(item["ts"]).isoformat(),
                        "quote_volume": float(item["quote_volume"]),
                        "volume": float(item["volume"]),
                        "is_closed": bool(item["is_closed"]),
                        "source": str(item["source"]),
                        "filename": str(item["filename"]),
                        "file_sha256": hashed(item["filename"]),
                        "layer": "normalized_1h_legacy",
                    }
                )

    class_counts = {}
    for item in traces:
        class_counts[str(item["classification"])] = class_counts.get(str(item["classification"]), 0) + 1
    summary["hour_classification_counts"] = class_counts
    summary["hour_traces"] = traces

    unexplained = []
    if any(int(row.get("quote_volume_mismatches") or 0) for row in rebuild_vs_pub):
        unexplained.append("independent 15m rebuild disagrees with published 4h quote_volume beyond tolerance")
    unresolved_hours = [item for item in traces if item["classification"] == "UNRESOLVED"]
    if unresolved_hours:
        unexplained.append(
            f"{len(unresolved_hours)} legacy-1h mismatch hours remain UNRESOLVED because local raw evidence is missing"
        )
    if traces and not unresolved_hours:
        unexplained.append(
            "legacy native 1h quote_volume mismatches 15m sums; see hour classifications, not a blanket semantic claim"
        )
    summary["blockers"] = unexplained
    derived_ok = not any(int(row.get("quote_volume_mismatches") or 0) for row in rebuild_vs_pub)
    summary["derived_verdict"] = (
        "published derived 4h matches independent 15m complete-bucket sums within predeclared tolerances"
        if derived_ok
        else "BLOCKED: independent rebuild disagrees with published derived"
    )
    summary["legacy_verdict"] = (
        "UNRESOLVED"
        if unresolved_hours
        else ("explained_with_local_evidence" if traces else "no_material_legacy_mismatches")
    )

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    write_canonical_json(JSON_OUT, summary)
    pd.DataFrame(rebuild_vs_pub).to_csv(CSV_OUT, index=False)
    pd.DataFrame(traces).to_csv(TRACE_OUT, index=False)
    pd.DataFrame(component_rows).to_csv(COMP_OUT, index=False)

    slim_traces = [
        {
            "symbol": item["symbol"],
            "ts_utc": item["ts_utc"],
            "abs_err": item["abs_err"],
            "classification": item["classification"],
            "raw_15m_missing": item["raw_15m_missing"],
            "raw_1h_missing": item["raw_1h_missing"],
        }
        for item in traces
    ]
    lines = [
        "# Binance OHLCV 成交额差异追溯 R3（2026-09-03）",
        "",
        "本轮不覆盖 [第二轮 RCA](binance-ohlcv-volume-rca-2026-09-03.md)。容差与第二轮相同，事先冻结，不事后扩大。",
        "独立 4h 重聚不调用 `resample_cte_sql` / `aggregate_complete_bars`。",
        "新派生聚合正确 ≠ 旧 1h 差异已解释。缺本地 raw 记 `UNRESOLVED`，本轮不下载补证。",
        "",
        "## 事先冻结的容差",
        "",
        md_table([{"field": key, **value} for key, value in TOLERANCE.items()]),
        "",
        "## 独立 15m 重聚 vs 已发布 derived 4h",
        "",
        md_table(rebuild_vs_pub),
        "",
        f"裁决：`{summary['derived_verdict']}`",
        "",
        "## 重叠完整小时：15m quote_volume 求和 vs legacy 1h 原生 quote_volume",
        "",
        md_table(native_rows),
        "",
        f"实质差异小时数：`{summary['material_mismatch_hours']}`。分类计数：`{json.dumps(class_counts, ensure_ascii=False)}`。",
        "",
        "## 逐小时追溯",
        "",
        md_table(slim_traces) if slim_traces else "_无实质差异小时_",
        "",
        "## Blockers",
        "",
    ]
    if unexplained:
        lines.extend(f"- {item}" for item in unexplained)
    else:
        lines.append("- 无")
    lines.extend(
        [
            "",
            f"旧源裁决：`{summary['legacy_verdict']}`。",
            "",
            f"机器结果：[{JSON_OUT.name}](../artifacts/{JSON_OUT.name})；",
            f"六资产表：[{CSV_OUT.name}](../artifacts/{CSV_OUT.name})；",
            f"小时追溯：[{TRACE_OUT.name}](../artifacts/{TRACE_OUT.name})；",
            f"组成 K 线：[{COMP_OUT.name}](../artifacts/{COMP_OUT.name})。",
        ]
    )
    DIAGNOSTIC.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"derived_verdict": summary["derived_verdict"], "legacy_verdict": summary["legacy_verdict"], "blockers": unexplained}, ensure_ascii=False))


if __name__ == "__main__":
    main()
