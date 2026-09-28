#!/usr/bin/env python3
"""Reconcile derived OHLCV with P0/P3, public 1d cache, and legacy 1h six-asset 4h."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from strategy_lab.data.catalog import DatasetRegistry
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import write_canonical_json
from strategy_lab.data.resample import SOURCE_PRIORITY_V1
from strategy_lab.data.settings import default_settings

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "research/platform/data-lake-governance"
ARTIFACT_DIR = FAMILY / "artifacts"
P0_CUTOFF = pd.Timestamp("2026-07-01T00:00:00Z")
P3_CUTOFF = pd.Timestamp("2026-08-25T00:00:00Z")
KNOWN_P0_DAYS = 586_612
KNOWN_P0_SYMBOLS = 790
KNOWN_P0_15M = 56_358_042
KNOWN_P3_15M = 60_266_362
KNOWN_P3_SYMBOLS = 853
SIX_ASSETS = (
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "BNB/USDT:USDT",
    "TRX/USDT:USDT",
    "HYPE/USDT:USDT",
)
LEGACY_1H_PRIORITY = (
    "binance_vision_kline_monthly_overlap_repair",
    "binance_vision_kline_daily_gap_repair",
    "binance_fapi_kline_freeze_gap",
    "binance_fapi_kline_prospective_oos",
    "binance_futures_kline_api",
)


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    con.execute("SET enable_progress_bar=false")
    return con


def hourly_to_complete_4h(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    working = frame.copy()
    working["ts"] = pd.to_datetime(working["ts"], utc=True)
    con = connect()
    con.register("hourly", working)
    out = con.execute(
        """
        WITH buckets AS (
            SELECT *,
                   to_timestamp(
                       CAST(epoch(ts) AS BIGINT)
                       - (CAST(epoch(ts) AS BIGINT) % 14400)
                   ) AS bar_ts
            FROM hourly
            WHERE is_closed
              AND CAST(epoch(ts) AS BIGINT) % 3600 = 0
        )
        SELECT
            bar_ts AS ts,
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
            END AS vwap
        FROM buckets
        GROUP BY bar_ts
        HAVING count(*) = 4
           AND count(DISTINCT ts) = 4
           AND min(ts) = bar_ts
           AND max(ts) = bar_ts + INTERVAL '10800 seconds'
        ORDER BY ts
        """
    ).fetch_df()
    con.close()
    if not out.empty:
        out["ts"] = pd.to_datetime(out["ts"], utc=True)
    return out


def selected_union(con: duckdb.DuckDBPyConnection, glob15: str, cutoff: pd.Timestamp) -> pd.Series:
    listed = "', '".join(SOURCE_PRIORITY_V1)
    return con.execute(
        f"""
        WITH raw AS (
            SELECT * FROM read_parquet('{glob15}', hive_partitioning=false, union_by_name=true)
            WHERE source IN ('{listed}') AND ts < ?
        ),
        selected AS (
            SELECT * EXCLUDE (rk) FROM (
                SELECT *, CASE source
                    WHEN '{SOURCE_PRIORITY_V1[0]}' THEN 0
                    WHEN '{SOURCE_PRIORITY_V1[1]}' THEN 1
                    ELSE 999 END AS rk
                FROM raw
            )
            QUALIFY row_number() OVER (PARTITION BY symbol, ts ORDER BY rk, source) = 1
        )
        SELECT count(*) AS selected_rows, count(DISTINCT symbol) AS symbols
        FROM selected
        """,
        [cutoff.to_pydatetime()],
    ).fetch_df().iloc[0]


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    layout = DataLakeLayout.from_settings(default_settings())
    registry = DatasetRegistry()
    n15 = registry.get("binance.perp.ohlcv.15m.normalized.v1").absolute_root(layout)
    derived_1d = registry.get("binance.perp.ohlcv.1d.from_15m.v1").absolute_root(layout)
    derived_4h = registry.get("binance.perp.ohlcv.4h.from_15m.v1").absolute_root(layout)
    legacy_1h = registry.get("binance.perp.ohlcv.1h.normalized.legacy").absolute_root(layout)
    cache = layout.cache_dir / "binance_perp_1d_from_15m" / "ohlcv_1d"
    con = connect()
    glob15 = str(n15 / "**/*.parquet")
    print("reconciling 15m P0/P3 unions", flush=True)
    p0 = selected_union(con, glob15, P0_CUTOFF)
    p3 = selected_union(con, glob15, P3_CUTOFF)
    result: dict = {
        "p0_15m": {
            "selected_rows": int(p0["selected_rows"]),
            "symbols": int(p0["symbols"]),
            "known_rows": KNOWN_P0_15M,
            "known_symbols": KNOWN_P0_SYMBOLS,
            "row_delta": int(p0["selected_rows"]) - KNOWN_P0_15M,
            "symbol_delta": int(p0["symbols"]) - KNOWN_P0_SYMBOLS,
        },
        "p3_15m": {
            "selected_rows": int(p3["selected_rows"]),
            "symbols": int(p3["symbols"]),
            "known_rows": KNOWN_P3_15M,
            "known_symbols": KNOWN_P3_SYMBOLS,
            "row_delta": int(p3["selected_rows"]) - KNOWN_P3_15M,
            "symbol_delta": int(p3["symbols"]) - KNOWN_P3_SYMBOLS,
        },
    }
    if derived_1d.exists():
        print("reconciling derived 1d vs P0 complete days and public cache", flush=True)
        glob1d = str(derived_1d / "**/*.parquet")
        daily = con.execute(
            f"""
            SELECT count(*) AS rows, count(DISTINCT symbol) AS symbols
            FROM read_parquet('{glob1d}', hive_partitioning=true, union_by_name=true)
            WHERE ts < ?
            """,
            [P0_CUTOFF.to_pydatetime()],
        ).fetch_df().iloc[0]
        result["p0_complete_1d"] = {
            "derived_rows": int(daily["rows"]),
            "derived_symbols": int(daily["symbols"]),
            "known_rows": KNOWN_P0_DAYS,
            "known_symbols": KNOWN_P0_SYMBOLS,
            "row_delta": int(daily["rows"]) - KNOWN_P0_DAYS,
            "symbol_delta": int(daily["symbols"]) - KNOWN_P0_SYMBOLS,
        }
        monthly = str(cache / "month=*.parquet")
        overlay = cache / "overlay_date_partitions.parquet"
        compare = con.execute(
            f"""
            WITH derived AS (
                SELECT
                    replace(symbol, '/USDT:USDT', '') AS sym_key,
                    CAST(ts AS DATE) AS day,
                    open, high, low, close, volume, quote_volume
                FROM read_parquet('{glob1d}', hive_partitioning=true, union_by_name=true)
            ),
            cache_all AS (
                SELECT * EXCLUDE (prio) FROM (
                    SELECT *, 0 AS prio FROM read_parquet('{monthly}')
                    UNION ALL BY NAME
                    SELECT *, 1 AS prio FROM read_parquet('{overlay}')
                )
                QUALIFY row_number() OVER (PARTITION BY sym_key, day ORDER BY prio) = 1
            ),
            cache_complete AS (
                SELECT * FROM cache_all
                WHERE bars_15m = 96 AND COALESCE(all_closed, FALSE)
            )
            SELECT
                (SELECT count(*) FROM derived d INNER JOIN cache_all c USING (sym_key, day)) AS matched_all_cache_keys,
                (SELECT count(*) FROM derived d ANTI JOIN cache_all c USING (sym_key, day)) AS derived_only_vs_all_cache,
                (SELECT count(*) FROM cache_all c ANTI JOIN derived d USING (sym_key, day)) AS all_cache_only,
                (SELECT count(*) FROM derived d INNER JOIN cache_complete cc USING (sym_key, day)) AS matched_complete_cache_keys,
                (SELECT count(*) FROM derived d ANTI JOIN cache_complete cc USING (sym_key, day)) AS derived_only_vs_complete_cache,
                (SELECT count(*) FROM cache_complete cc ANTI JOIN derived d USING (sym_key, day)) AS complete_cache_only,
                (
                    SELECT count(*)
                    FROM derived d INNER JOIN cache_complete cc USING (sym_key, day)
                    WHERE abs(d.open - cc.open) > 1e-8
                       OR abs(d.high - cc.high) > 1e-8
                       OR abs(d.low - cc.low) > 1e-8
                       OR abs(d.close - cc.close) > 1e-8
                ) AS complete_ohlc_mismatches
            """
        ).fetch_df().iloc[0]
        result["cache_vs_derived_1d"] = {key: int(compare[key]) for key in compare.index}
    else:
        result["p0_complete_1d"] = {"status": "derived_1d_not_published"}
        result["cache_vs_derived_1d"] = {"status": "derived_1d_not_published"}
    if derived_4h.exists():
        print("summarizing derived 4h coverage and six-asset mismatch", flush=True)
        glob4h = str(derived_4h / "**/*.parquet")
        coverage = con.execute(
            f"""
            SELECT CAST(date_part('year', ts) AS INTEGER) AS year,
                   count(DISTINCT symbol) AS symbols,
                   count(DISTINCT (symbol, CAST(ts AS DATE))) AS symbol_days,
                   count(*) AS bars
            FROM read_parquet('{glob4h}', hive_partitioning=true, union_by_name=true)
            GROUP BY 1 ORDER BY 1
            """
        ).fetch_df()
        hist = con.execute(
            f"""
            SELECT effective_days, count(*) AS symbols FROM (
                SELECT symbol, count(DISTINCT CAST(ts AS DATE)) AS effective_days
                FROM read_parquet('{glob4h}', hive_partitioning=true, union_by_name=true)
                GROUP BY 1
            )
            GROUP BY 1 ORDER BY 1
            """
        ).fetch_df()
        result["derived_4h_year_coverage"] = coverage.to_dict(orient="records")
        result["derived_4h_history_days"] = {
            "symbols_ge_365d": int(hist.loc[hist["effective_days"] >= 365, "symbols"].sum()),
            "symbols_ge_30d": int(hist.loc[hist["effective_days"] >= 30, "symbols"].sum()),
            "symbols_total": int(hist["symbols"].sum()),
        }
        eligible = int(hist.loc[hist["effective_days"] >= 30, "symbols"].sum())
        years_with_breadth = int((coverage["symbols"] >= 50).sum()) if not coverage.empty else 0
        result["full_market_p0r_data_support"] = {
            "can_support_all_market_history_p0r": bool(eligible >= 50 and years_with_breadth >= 4),
            "eligible_symbols_ge_30d": eligible,
            "years_with_at_least_50_symbols": years_with_breadth,
            "reason": (
                "derived 4h has multi-year breadth from accepted 15m; this is data-scope support only, not a strategy verdict"
                if eligible >= 50 and years_with_breadth >= 4
                else "derived 4h coverage is still too thin for all-market historical P0R"
            ),
        }
        rank_sql = " ".join(
            f"WHEN source = '{source}' THEN {index}" for index, source in enumerate(LEGACY_1H_PRIORITY)
        )
        listed_1h = "', '".join(LEGACY_1H_PRIORITY)
        mismatch_rows = []
        glob1h = str(legacy_1h / "**/*.parquet")
        for symbol in SIX_ASSETS:
            derived = con.execute(
                f"""
                SELECT ts, open, high, low, close, volume, quote_volume, trade_count, vwap
                FROM read_parquet('{glob4h}', hive_partitioning=true, union_by_name=true)
                WHERE symbol = ?
                ORDER BY ts
                """,
                [symbol],
            ).fetch_df()
            legacy = con.execute(
                f"""
                WITH raw AS (
                    SELECT * FROM read_parquet('{glob1h}', hive_partitioning=false, union_by_name=true)
                    WHERE replace(upper(symbol), '_', '/') = ?
                      AND source IN ('{listed_1h}')
                      AND is_closed
                ),
                selected AS (
                    SELECT * EXCLUDE (rk) FROM (
                        SELECT *, CASE {rank_sql} ELSE 999 END AS rk
                        FROM raw
                    )
                    QUALIFY row_number() OVER (PARTITION BY ts ORDER BY rk, source) = 1
                )
                SELECT * FROM selected ORDER BY ts
                """,
                [symbol],
            ).fetch_df()
            if derived.empty or legacy.empty:
                mismatch_rows.append(
                    {
                        "symbol": symbol,
                        "status": "missing_side",
                        "derived_4h_rows": int(len(derived)),
                        "legacy_1h_rows": int(len(legacy)),
                    }
                )
                continue
            derived["ts"] = pd.to_datetime(derived["ts"], utc=True)
            hourly = hourly_to_complete_4h(legacy)
            merged = derived.merge(hourly, on="ts", how="outer", suffixes=("_15m", "_1h"), indicator=True)
            fields = ["open", "high", "low", "close", "volume", "quote_volume"]
            row = {
                "symbol": symbol,
                "status": "compared",
                "derived_4h_rows": int(len(derived)),
                "legacy_1h_to_4h_rows": int(len(hourly)),
                "matched_ts": int(merged["_merge"].eq("both").sum()),
                "only_15m": int(merged["_merge"].eq("left_only").sum()),
                "only_1h": int(merged["_merge"].eq("right_only").sum()),
            }
            both = merged["_merge"].eq("both")
            for field in fields:
                left = merged.loc[both, f"{field}_15m"].astype(float)
                right = merged.loc[both, f"{field}_1h"].astype(float)
                diff = np.abs(left - right)
                row[f"{field}_mismatches"] = int((diff > 1e-8).sum())
                row[f"{field}_max_abs_error"] = float(diff.max()) if len(diff) else None
            mismatch_rows.append(row)
        result["six_asset_4h_mismatch"] = mismatch_rows
        pd.DataFrame(mismatch_rows).to_csv(
            ARTIFACT_DIR / "binance_4h_six_asset_15m_vs_1h_mismatch_2026-09-02.csv",
            index=False,
        )
        coverage.to_csv(ARTIFACT_DIR / "binance_4h_from_15m_year_coverage_2026-09-02.csv", index=False)
    else:
        result["full_market_p0r_data_support"] = {"status": "derived_4h_not_published"}
    write_canonical_json(ARTIFACT_DIR / "binance_ohlcv_reconciliation_2026-09-02.json", result)
    print(json.dumps(result, indent=2, default=str)[:5000], flush=True)


if __name__ == "__main__":
    main()
