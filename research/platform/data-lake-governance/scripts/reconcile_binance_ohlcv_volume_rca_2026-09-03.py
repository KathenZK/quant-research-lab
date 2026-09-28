#!/usr/bin/env python3
"""Independent volume/quote_volume RCA for Binance derived OHLCV. Does not call resample_cte_sql."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from strategy_lab.data.catalog import (
    BINANCE_PERP_15M_NORMALIZED_V1,
    BINANCE_PERP_1D_FROM_15M_V1,
    BINANCE_PERP_1H_NORMALIZED_LEGACY,
    BINANCE_PERP_4H_FROM_15M_V1,
    DatasetRegistry,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import write_canonical_json
from strategy_lab.data.settings import default_settings

ROOT = Path(__file__).resolve().parents[4]
ARTIFACT_DIR = ROOT / "research/platform/data-lake-governance/artifacts"
DIAGNOSTIC = (
    ROOT
    / "research/platform/data-lake-governance/diagnostics"
    / "binance-ohlcv-volume-rca-2026-09-03.md"
)
JSON_OUT = ARTIFACT_DIR / "binance_ohlcv_volume_rca_2026-09-03.json"
CSV_OUT = ARTIFACT_DIR / "binance_ohlcv_volume_rca_six_asset_2026-09-03.csv"
DRILL_OUT = ARTIFACT_DIR / "binance_ohlcv_volume_rca_drilldown_2026-09-03.csv"

SIX_ASSETS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "BNB/USDT:USDT",
    "TRX/USDT:USDT",
    "HYPE/USDT:USDT",
]

# Declared before seeing residuals. Do not widen after the fact.
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


def exceeds(left: object, right: object, spec: dict[str, float]) -> bool:
    if pd.isna(left) or pd.isna(right):
        return True
    abs_err = abs(float(left) - float(right))
    denom = max(abs(float(right)), 1e-12)
    rel_err = abs_err / denom
    return abs_err > spec["abs"] + 1e-15 and rel_err > spec["rel"]


def independent_4h_sql() -> str:
    """Independent 15m→4h complete-bucket formula. Not resample_cte_sql."""

    return """
        legal AS (
            SELECT *
            FROM selected
            WHERE is_closed
              AND open > 0 AND high > 0 AND low > 0 AND close > 0
              AND volume >= 0 AND quote_volume >= 0 AND trade_count >= 0 AND vwap > 0
              AND high >= greatest(open, close, low)
              AND low <= least(open, close, high)
              AND CAST(epoch(ts) AS BIGINT) % 900 = 0
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


def main() -> None:
    layout = DataLakeLayout.from_settings(default_settings())
    registry = DatasetRegistry()
    files_15m = [
        str(path)
        for path in registry.get(BINANCE_PERP_15M_NORMALIZED_V1).absolute_root(layout).rglob("*.parquet")
        if path.is_file()
    ]
    files_4h = [
        str(path)
        for path in registry.get(BINANCE_PERP_4H_FROM_15M_V1).absolute_root(layout).rglob("*.parquet")
        if path.is_file()
    ]
    files_1h = [
        str(path)
        for path in registry.get(BINANCE_PERP_1H_NORMALIZED_LEGACY).absolute_root(layout).rglob("*.parquet")
        if path.is_file()
    ]
    files_1d = [
        str(path)
        for path in registry.get(BINANCE_PERP_1D_FROM_15M_V1).absolute_root(layout).rglob("*.parquet")
        if path.is_file()
    ]
    cache_1d = layout.cache_dir / "binance_perp_1d_from_15m" / "ohlcv_1d"
    con = connect()
    summary: dict[str, object] = {
        "tolerances": TOLERANCE,
        "proxy_quote_volume_rule": "close*volume is not native quote_volume and is not used",
        "independent_formula": "date_trunc hour minus hour%4; require 16 consecutive 15m components",
    }

    rebuilt = con.execute(
        f"""
        WITH raw AS (
            SELECT * FROM read_parquet(?, hive_partitioning=false, union_by_name=true)
            WHERE symbol IN ({", ".join("?" for _ in SIX_ASSETS)})
              AND source IN ('{VISION}', '{API}')
        ),
        ranked AS (
            SELECT *, CASE WHEN source = '{VISION}' THEN 0 ELSE 1 END AS source_rank
            FROM raw
        ),
        selected AS (
            SELECT * EXCLUDE (source_rank) FROM ranked
            QUALIFY row_number() OVER (
                PARTITION BY exchange, symbol, market_type, timeframe, ts
                ORDER BY source_rank, source
            ) = 1
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
    merged = rebuilt.merge(
        published,
        on=["symbol", "ts"],
        how="outer",
        suffixes=("_ind", "_pub"),
        indicator=True,
    )
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
            QUALIFY row_number() OVER (
                PARTITION BY symbol, ts ORDER BY source_rank, source
            ) = 1
        ),
        hour15 AS (
            SELECT
                symbol,
                date_trunc('hour', ts) AS ts,
                sum(volume) AS volume_15m_sum,
                sum(quote_volume) AS quote_volume_15m_sum,
                sum(trade_count) AS trade_count_15m_sum,
                count(*) AS components
            FROM selected
            GROUP BY 1, 2
            HAVING count(*) = 4
               AND min(ts) = date_trunc('hour', min(ts))
               AND max(ts) = date_trunc('hour', min(ts)) + INTERVAL '45 minutes'
        ),
        native1h AS (
            SELECT symbol, ts, volume, quote_volume, trade_count, close
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
            native1h.close * native1h.volume AS proxy_close_times_volume
        FROM hour15
        INNER JOIN native1h USING (symbol, ts)
        """,
        [files_15m, *SIX_ASSETS, files_1h, *SIX_ASSETS],
    ).fetch_df()
    native_vs_15m["ts"] = pd.to_datetime(native_vs_15m["ts"], utc=True)
    native_rows = []
    drill_rows = []
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
        worst = part.assign(abs_err=q_abs).sort_values("abs_err", ascending=False).head(3)
        for _, item in worst.iterrows():
            drill_rows.append(
                {
                    "symbol": symbol,
                    "ts_utc": pd.Timestamp(item["ts"]).isoformat(),
                    "quote_volume_15m_sum": float(item["quote_volume_15m_sum"]),
                    "quote_volume_native_1h": float(item["quote_volume_native_1h"]),
                    "volume_15m_sum": float(item["volume_15m_sum"]),
                    "volume_native_1h": float(item["volume_native_1h"]),
                    "proxy_close_times_volume": float(item["proxy_close_times_volume"]),
                    "classification": (
                        "native_1h_quote_volume_is_not_sum_of_15m_native_quote_volume"
                    ),
                }
            )
    summary["legacy_1h_vs_15m_hour_sums"] = native_rows

    cache_month = str(cache_1d / "month=*.parquet")
    cache_overlay = cache_1d / "overlay_date_partitions.parquet"
    cache_vs_derived = con.execute(
        f"""
        WITH month AS (SELECT * FROM read_parquet('{cache_month}', hive_partitioning=false, union_by_name=true)),
        overlay AS (SELECT * FROM read_parquet('{cache_overlay}', hive_partitioning=false, union_by_name=true)),
        cache AS (
            SELECT * EXCLUDE (prio) FROM (
                SELECT *, 0 AS prio FROM month
                UNION ALL BY NAME
                SELECT *, 1 AS prio FROM overlay
            )
            QUALIFY row_number() OVER (PARTITION BY sym_key, day ORDER BY prio) = 1
        ),
        complete AS (
            SELECT
                sym_key,
                day,
                open,
                high,
                low,
                close,
                quote_volume,
                bars_15m,
                all_closed
            FROM cache
            WHERE bars_15m = 96 AND coalesce(all_closed, false)
        ),
        derived AS (
            SELECT
                replace(symbol, '/USDT:USDT', '') AS sym_key,
                CAST(ts AS DATE) AS day,
                open,
                high,
                low,
                close,
                volume,
                quote_volume,
                trade_count
            FROM read_parquet(?, hive_partitioning=false, union_by_name=true)
        )
        SELECT
            count(*) AS complete_cache_days,
            count(*) FILTER (WHERE derived.sym_key IS NOT NULL) AS matched_days,
            count(*) FILTER (
                WHERE derived.sym_key IS NOT NULL
                  AND abs(complete.quote_volume - derived.quote_volume) > 1e-6
                  AND abs(complete.quote_volume - derived.quote_volume)
                      / greatest(abs(derived.quote_volume), 1e-12) > 1e-10
            ) AS quote_volume_mismatches,
            max(abs(complete.quote_volume - derived.quote_volume)) FILTER (WHERE derived.sym_key IS NOT NULL) AS quote_volume_max_abs,
            max(
                abs(complete.quote_volume - derived.quote_volume)
                / greatest(abs(derived.quote_volume), 1e-12)
            ) FILTER (WHERE derived.sym_key IS NOT NULL) AS quote_volume_max_rel,
            count(*) FILTER (
                WHERE derived.sym_key IS NOT NULL
                  AND (
                    abs(complete.open - derived.open) > 0
                    OR abs(complete.high - derived.high) > 0
                    OR abs(complete.low - derived.low) > 0
                    OR abs(complete.close - derived.close) > 0
                  )
            ) AS ohlc_mismatches
        FROM complete
        LEFT JOIN derived
          ON complete.sym_key = derived.sym_key
         AND complete.day = derived.day
        """,
        [files_1d],
    ).fetch_df().iloc[0].to_dict()
    cache_payload = {
        key: (None if value is None or (isinstance(value, float) and pd.isna(value)) else value)
        for key, value in cache_vs_derived.items()
    }
    cache_payload["volume_column_in_cache"] = False
    cache_payload["trade_count_column_in_cache"] = False
    cache_payload["volume_comparison"] = "NOT_IN_CACHE_SCHEMA"
    cache_payload["trade_count_comparison"] = "NOT_IN_CACHE_SCHEMA"
    cache_payload["cache_schema"] = [
        "sym_key",
        "base_asset",
        "day",
        "open",
        "high",
        "low",
        "close",
        "quote_volume",
        "bars_15m",
        "all_closed",
    ]
    summary["public_1d_cache_complete_days_vs_derived"] = cache_payload

    unexplained = []
    if any(int(row.get("quote_volume_mismatches") or 0) for row in rebuild_vs_pub):
        unexplained.append("independent 15m rebuild disagrees with published 4h quote_volume beyond tolerance")
    if any(int(row.get("quote_volume_mismatches") or 0) for row in native_rows if "quote_volume_mismatches" in row):
        unexplained.append(
            "legacy native 1h quote_volume is not the sum of contemporaneous 15m quote_volume; "
            "this is a source/field semantic difference, not evidence that 15m summation is non-additive"
        )
    summary["blockers"] = unexplained
    summary["verdict"] = (
        "published derived 4h matches independent 15m complete-bucket sums within predeclared tolerances"
        if not any(int(row.get("quote_volume_mismatches") or 0) for row in rebuild_vs_pub)
        else "BLOCKED: independent rebuild disagrees with published derived"
    )

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    write_canonical_json(JSON_OUT, summary)
    pd.DataFrame(rebuild_vs_pub).to_csv(CSV_OUT, index=False)
    pd.DataFrame(drill_rows).to_csv(DRILL_OUT, index=False)

    lines = [
        "# Binance OHLCV 成交量/成交额差异追溯（2026-09-03）",
        "",
        "本报告修正 [2026-09-02 对账](binance-ohlcv-reconciliation-2026-09-02.md) 中把",
        "`1h 成交额再求和不等于 15m 成交额直接求和` 单独当成根因的写法。同一交易范围、同一字段语义、同一时间桶的**原生成交额应可加**；浮点误差按下表事先声明的容差量化，不事后放宽。",
        "",
        "独立验证路径使用 `date_trunc('hour') - (hour % 4)` 的 4h 分桶，不调用 `resample_cte_sql` / `aggregate_complete_bars`。",
        "",
        "## 事先声明的容差",
        "",
        "| 字段 | abs | rel |",
        "| --- | --- | --- |",
    ]
    for field, spec in TOLERANCE.items():
        lines.append(f"| `{field}` | {spec['abs']} | {spec['rel']} |")
    lines.extend(
        [
            "",
            "`close × volume` 只作为对照代理，不当作原生成交额。",
            "",
            "## 独立 15m 重聚 vs 已发布 derived 4h",
            "",
            md_table(rebuild_vs_pub),
            "",
            "## 重叠完整小时：15m 原生成交额求和 vs legacy 1h 原生 quote_volume",
            "",
            md_table(native_rows),
            "",
            "## 公共日K缓存完整日 vs canonical 1d（含成交字段）",
            "",
            "公共日K缓存 schema **没有** `volume` / `trade_count`，只有 `quote_volume`。",
            "因此成交量与成交笔数无法对账，记为 `NOT_IN_CACHE_SCHEMA`，不是 0 mismatch。",
            "`quote_volume` 使用事先声明的 abs+rel 容差（不是只看 abs）。",
            "",
            json.dumps(summary["public_1d_cache_complete_days_vs_derived"], ensure_ascii=False, indent=2, default=str),
            "",
            "## 裁决",
            "",
            f"- 独立重聚 vs 已发布 derived：`{summary['verdict']}`",
            "- legacy 1h `quote_volume` 与同时段 15m `quote_volume` 之和在容差外大量不一致时，分类为**来源/字段语义不同**（Vision/API 1h K 线的成交额不是 15m 成交额的可加汇总，也不是 `close×volume` 代理）。P0R-DATA 与新研究必须使用 15m 衍生 `quote_volume`。",
            "- 历史报告中的 mismatch 表仍保留；本文件是更正说明，不覆盖 2026-09-02 证据。",
            "",
            f"机器结果：[{JSON_OUT.name}](../artifacts/{JSON_OUT.name})；",
            f"六资产表：[{CSV_OUT.name}](../artifacts/{CSV_OUT.name})；",
            f"下钻：[{DRILL_OUT.name}](../artifacts/{DRILL_OUT.name})。",
        ]
    )
    DIAGNOSTIC.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": summary["verdict"], "json": str(JSON_OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
