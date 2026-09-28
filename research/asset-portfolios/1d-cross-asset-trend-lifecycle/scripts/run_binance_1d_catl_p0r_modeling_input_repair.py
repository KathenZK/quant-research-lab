#!/usr/bin/env python3
"""Build the donor-only BIN-1D-CATL P0R modeling input.

P0 remains immutable evidence. P0R repairs three pre-modeling issues only:
causal volatility buckets, donor-tradable PIT market ranks, and explicit price
scale eligibility. It does not train a model or read the protected HYPE tail.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import duckdb


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research" / "asset-portfolios" / "1d-cross-asset-trend-lifecycle"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAGNOSTIC_DIR = FAMILY_DIR / "diagnostics"
SPEC_PATH = (
    FAMILY_DIR
    / "specs"
    / "binance-1d-catl-p0r-modeling-input-repair-contract-2026-08-31.md"
)
P0_MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_catl_p0_manifest.json"
P0_FEATURE_GLOB = ARTIFACT_DIR / "p0_asset_day_feature_panel" / "**" / "*.parquet"
P0_LANDMARK_GLOB = ARTIFACT_DIR / "p0_directional_landmark_panel" / "**" / "*.parquet"

OUTPUT_PANEL_DIR = ARTIFACT_DIR / "p0r_donor_directional_modeling_panel"
FEATURE_BLOCKS_PATH = ARTIFACT_DIR / "binance_1d_catl_p0r_feature_blocks.json"
SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_catl_p0r_summary.json"
MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_catl_p0r_manifest.json"
REPORT_PATH = (
    DIAGNOSTIC_DIR / "binance-1d-catl-p0r-modeling-input-repair-2026-08-31.md"
)
WORK_DB = ARTIFACT_DIR / "_catl_p0r_work.duckdb"

HYPE_ASSET = "HYPE/USDT:USDT"
CUTOFF_UTC = "2026-05-31 00:00:00+00:00"
MAX_FEATURE_TS = "2026-05-30 00:00:00+00:00"
MIN_CAUSAL_VOL_HISTORY = 30
MAX_ATR_TO_ENTRY = 0.50
MAX_ABS_RET_1D = 3.00
HOLDOUT_READ = False


FEATURE_BLOCKS: dict[str, list[str]] = {
    "ma_geometry": [
        *[f"dir_close_ma{n}_dist_atr" for n in (7, 14, 30, 60)],
        *[
            f"dir_ma{n}_slope_{k}d_atr"
            for n in (7, 14, 30, 60)
            for k in (1, 3, 5)
        ],
        *[f"dir_ma{n}_slope_change_3d" for n in (7, 14, 30, 60)],
        *[f"dir_ma{n}_slope_accel_5d" for n in (7, 14, 30, 60)],
        *[f"dir_raw_ma{n}_cross" for n in (7, 14, 30, 60)],
        *[f"dir_price_side_ma{n}" for n in (7, 14, 30, 60)],
        *[f"days_since_ma{n}_cross" for n in (7, 14, 30, 60)],
        *[f"ma{n}_cross_count_7d" for n in (7, 14, 30, 60)],
        *[f"ma{n}_cross_count_14d" for n in (7, 14, 30, 60)],
        "dir_ma_stack_score",
        "fast_slow_ma_direction_aligned",
        "ma7_cross_with_ma30_opposite_slope",
        "dir_price_ma7_ma30_joint_state",
        "large_cross_degree_atr",
    ],
    "price_path": [
        *[f"dir_ret_{n}d" for n in (1, 3, 7, 14, 30, 60)],
        *[f"dir_range_pos_{n}d" for n in (3, 7, 14, 30, 60)],
        *[f"dir_distance_to_favorable_extreme_{n}d_atr" for n in (3, 7, 14, 30, 60)],
        *[f"dir_distance_from_adverse_extreme_{n}d_atr" for n in (3, 7, 14, 30, 60)],
        *[f"path_efficiency_{n}d" for n in (7, 14, 30, 60)],
        "dir_favorable_run_days",
        "dir_opposite_run_days",
        "shock_day",
        "sideways_state",
        "reexpansion_state",
        "log1p_listing_age_days",
    ],
    "volatility_and_candle": [
        "atr7_pct",
        "atr14_pct",
        "atr30_pct",
        "atr14_to_atr30",
        "atr7_to_atr30",
        "daily_range_atr",
        "body_atr",
        "dir_close_location",
        "dir_favorable_wick_atr",
        "dir_adverse_wick_atr",
        "volatility_state_p0r",
    ],
    "flow_and_carry": [
        "volume_to_7d",
        "quote_volume_to_7d",
        "volume_to_30d",
        "quote_volume_to_30d",
        "volume_change_1d",
        "funding_missing",
        "dir_funding_carry_1d",
        "dir_funding_carry_7d",
        "dir_funding_carry_30d",
        "dir_funding_carry_change_3d",
        "liquidity_rank_pct_p0r",
    ],
    "cross_market": [
        "pit_universe_size_p0r",
        "dir_market_breadth_ma7_p0r",
        "dir_market_breadth_ma30_p0r",
        "dir_market_up_ratio_1d_p0r",
        "market_ret_1d_dispersion_p0r",
        "dir_market_ret_7d_median_p0r",
        "dir_market_ret_30d_median_p0r",
        "dir_btc_ret_7d",
        "dir_btc_ret_30d",
        "dir_btc_price_side_ma7",
        "dir_btc_price_side_ma30",
        "dir_relative_to_btc_ret_7d",
        "dir_relative_to_btc_ret_30d",
        "dir_relative_to_market_median_ret_7d_p0r",
        "dir_relative_to_market_median_ret_30d_p0r",
    ],
    "event_probes": [
        "probe_raw_ma7_cross_dir",
        "probe_raw_ma14_cross_dir",
        "probe_raw_ma30_cross_dir",
        "probe_raw_ma60_cross_dir",
        "probe_20d_range_breakout_dir",
        "probe_same_side_ma7_no_cross",
        "probe_same_side_ma30_no_cross",
        "probe_ma7_ma30_direction_aligned",
        "probe_ma7_cross_ma30_opposite",
    ],
}

IDENTITY_AUDIT_COLUMNS = [
    "asset",
    "asset_slug",
    "ts",
    "feature_known_at",
    "entry_ts",
    "side",
    "side_sign",
    "calendar_month",
    "calendar_quarter",
    "listing_age_days",
    "entry_ref",
    "atr_anchor",
    "atr_to_entry_p0r",
    "p0r_prior_atr_count",
    "tradable_marker_p0",
    "price_scale_discontinuity_p0r",
    "extreme_atr_scale_p0r",
    "base_model_eligible_p0r",
    "model_eligible_entry_p0r",
    "model_eligible_continue_p0r",
]

LABEL_AUDIT_COLUMNS = [
    "label_start_ts",
    "label_end_ts_5d",
    "label_end_ts_20d",
    "label_observation_end_ts_30d",
    "future_path_complete_5d",
    "future_path_complete_20d",
    "label_entry_result",
    "label_entry_success_20d",
    "label_entry_success_20d_optimistic",
    "label_entry_hours_to_hit",
    "label_entry_ambiguous_same_hour",
    "label_continue_result",
    "label_continue_success_5d",
    "label_continue_success_5d_optimistic",
    "label_continue_hours_to_hit",
    "label_continue_ambiguous_same_hour",
    "future_mfe_atr_5d",
    "future_mae_atr_5d",
    "future_terminal_direction_return_5d",
    "future_mfe_atr_20d",
    "future_mae_atr_20d",
    "future_terminal_direction_return_20d",
    "future_path_efficiency_20d",
    "future_mfe_giveback_20d",
    "label_entry_net_return",
    "label_continue_net_return",
]

FORBIDDEN_FEATURE_PATTERNS = [
    "asset",
    "asset_slug",
    "side",
    "side_sign",
    "ts",
    "feature_known_at",
    "entry_ts",
    "entry_ref",
    "atr_anchor",
    "label_*",
    "future_*",
    "*_result",
    "*_hours_to_hit",
    "volatility_state",
    "liquidity_rank_pct",
    "pit_universe_size",
    "market_breadth_above_ma7",
    "market_breadth_above_ma30",
    "market_up_ratio_1d",
    "market_ret_1d_dispersion",
    "market_ret_7d_median",
    "market_ret_30d_median",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def _safe_replace_dir(path: Path) -> None:
    resolved = path.resolve()
    if resolved.parent != ARTIFACT_DIR.resolve() or resolved.name != OUTPUT_PANEL_DIR.name:
        raise RuntimeError(f"Refusing to replace unexpected directory: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def _json_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _row_dict(cursor: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    columns = [item[0] for item in cursor.description]
    row = cursor.fetchone()
    if row is None:
        return {}
    return {key: _json_scalar(value) for key, value in zip(columns, row, strict=True)}


def _feature_expressions() -> list[str]:
    expressions: list[str] = []
    for n in (1, 3, 7, 14, 30, 60):
        expressions.append(f"l.side_sign * f.ret_{n}d AS dir_ret_{n}d")
    for n in (3, 7, 14, 30, 60):
        expressions.extend(
            [
                f"CASE WHEN l.side_sign = 1 THEN f.range_pos_{n}d ELSE 1.0 - f.range_pos_{n}d END AS dir_range_pos_{n}d",
                f"CASE WHEN l.side_sign = 1 THEN f.distance_to_high_{n}d_atr ELSE f.distance_to_low_{n}d_atr END AS dir_distance_to_favorable_extreme_{n}d_atr",
                f"CASE WHEN l.side_sign = 1 THEN f.distance_to_low_{n}d_atr ELSE f.distance_to_high_{n}d_atr END AS dir_distance_from_adverse_extreme_{n}d_atr",
            ]
        )
    expressions.extend([f"f.path_efficiency_{n}d" for n in (7, 14, 30, 60)])
    expressions.extend(
        [
            "CASE WHEN l.side_sign = 1 THEN f.up_run_days ELSE f.down_run_days END AS dir_favorable_run_days",
            "CASE WHEN l.side_sign = 1 THEN f.down_run_days ELSE f.up_run_days END AS dir_opposite_run_days",
            "f.shock_day",
            "f.sideways_state",
            "f.reexpansion_state",
            "ln(1.0 + f.listing_age_days) AS log1p_listing_age_days",
        ]
    )

    for n in (7, 14, 30, 60):
        expressions.append(f"l.side_sign * f.close_ma{n}_dist_atr AS dir_close_ma{n}_dist_atr")
        for k in (1, 3, 5):
            expressions.append(
                f"l.side_sign * f.ma{n}_slope_{k}d_atr AS dir_ma{n}_slope_{k}d_atr"
            )
        expressions.extend(
            [
                f"l.side_sign * f.ma{n}_slope_change_3d AS dir_ma{n}_slope_change_3d",
                f"l.side_sign * f.ma{n}_slope_accel_5d AS dir_ma{n}_slope_accel_5d",
                f"l.side_sign * f.raw_ma{n}_cross_dir AS dir_raw_ma{n}_cross",
                f"l.side_sign * (2 * f.above_ma{n} - 1) AS dir_price_side_ma{n}",
                f"f.days_since_ma{n}_cross",
                f"f.ma{n}_cross_count_7d",
                f"f.ma{n}_cross_count_14d",
            ]
        )
    expressions.extend(
        [
            "l.side_sign * (f.ma_stack_score - 1.5) AS dir_ma_stack_score",
            "f.fast_slow_ma_direction_aligned",
            "f.ma7_cross_with_ma30_opposite_slope",
            "CASE WHEN l.side_sign * (2 * f.above_ma7 - 1) = 1 AND l.side_sign * (2 * f.above_ma30 - 1) = 1 THEN 'with_both' WHEN l.side_sign * (2 * f.above_ma7 - 1) = 1 THEN 'with_ma7_only' WHEN l.side_sign * (2 * f.above_ma30 - 1) = 1 THEN 'with_ma30_only' ELSE 'against_both' END AS dir_price_ma7_ma30_joint_state",
            "f.large_cross_degree_atr",
            "f.atr7_pct",
            "f.atr14_pct",
            "f.atr30_pct",
            "f.atr14_to_atr30",
            "f.atr7_to_atr30",
            "f.daily_range_atr",
            "f.body_atr",
            "CASE WHEN l.side_sign = 1 THEN f.close_location ELSE 1.0 - f.close_location END AS dir_close_location",
            "CASE WHEN l.side_sign = 1 THEN f.lower_wick_atr ELSE f.upper_wick_atr END AS dir_favorable_wick_atr",
            "CASE WHEN l.side_sign = 1 THEN f.upper_wick_atr ELSE f.lower_wick_atr END AS dir_adverse_wick_atr",
            "f.volatility_state_p0r",
            "f.volume_to_7d",
            "f.quote_volume_to_7d",
            "f.volume_to_30d",
            "f.quote_volume_to_30d",
            "f.volume_change_1d",
            "f.funding_missing",
            "-l.side_sign * f.funding_rate_sum AS dir_funding_carry_1d",
            "-l.side_sign * f.funding_mean_7d AS dir_funding_carry_7d",
            "-l.side_sign * f.funding_mean_30d AS dir_funding_carry_30d",
            "-l.side_sign * f.funding_change_3d AS dir_funding_carry_change_3d",
            "f.liquidity_rank_pct_p0r",
            "f.pit_universe_size_p0r",
            "CASE WHEN l.side_sign = 1 THEN f.market_breadth_above_ma7_p0r ELSE 1.0 - f.market_breadth_above_ma7_p0r END AS dir_market_breadth_ma7_p0r",
            "CASE WHEN l.side_sign = 1 THEN f.market_breadth_above_ma30_p0r ELSE 1.0 - f.market_breadth_above_ma30_p0r END AS dir_market_breadth_ma30_p0r",
            "CASE WHEN l.side_sign = 1 THEN f.market_up_ratio_1d_p0r ELSE 1.0 - f.market_up_ratio_1d_p0r END AS dir_market_up_ratio_1d_p0r",
            "f.market_ret_1d_dispersion_p0r",
            "l.side_sign * f.market_ret_7d_median_p0r AS dir_market_ret_7d_median_p0r",
            "l.side_sign * f.market_ret_30d_median_p0r AS dir_market_ret_30d_median_p0r",
            "l.side_sign * f.btc_ret_7d AS dir_btc_ret_7d",
            "l.side_sign * f.btc_ret_30d AS dir_btc_ret_30d",
            "l.side_sign * (2 * f.btc_above_ma7 - 1) AS dir_btc_price_side_ma7",
            "l.side_sign * (2 * f.btc_above_ma30 - 1) AS dir_btc_price_side_ma30",
            "l.side_sign * (f.ret_7d - f.btc_ret_7d) AS dir_relative_to_btc_ret_7d",
            "l.side_sign * (f.ret_30d - f.btc_ret_30d) AS dir_relative_to_btc_ret_30d",
            "l.side_sign * (f.ret_7d - f.market_ret_7d_median_p0r) AS dir_relative_to_market_median_ret_7d_p0r",
            "l.side_sign * (f.ret_30d - f.market_ret_30d_median_p0r) AS dir_relative_to_market_median_ret_30d_p0r",
            "l.probe_raw_ma7_cross_dir",
            "l.probe_raw_ma14_cross_dir",
            "l.probe_raw_ma30_cross_dir",
            "l.probe_raw_ma60_cross_dir",
            "l.probe_20d_range_breakout_dir",
            "l.probe_same_side_ma7_no_cross",
            "l.probe_same_side_ma30_no_cross",
            "l.probe_ma7_ma30_direction_aligned",
            "l.probe_ma7_cross_ma30_opposite",
        ]
    )
    return expressions


def _label_expressions() -> list[str]:
    return [f"l.{column}" for column in LABEL_AUDIT_COLUMNS]


def _create_tables(con: duckdb.DuckDBPyConnection) -> None:
    feature_glob = _sql_path(P0_FEATURE_GLOB)
    landmark_glob = _sql_path(P0_LANDMARK_GLOB)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE donor_features_p0r AS
        WITH donor_base AS (
            SELECT * EXCLUDE (
                volatility_state,
                pit_universe_size,
                market_breadth_above_ma7,
                market_breadth_above_ma30,
                market_up_ratio_1d,
                market_ret_1d_dispersion,
                market_ret_7d_median,
                market_ret_30d_median,
                relative_to_market_median_ret_7d,
                relative_to_market_median_ret_30d,
                liquidity_rank_pct,
                asset_slug_partition,
                year
            )
            FROM read_parquet('{feature_glob}', union_by_name=true, hive_partitioning=true)
            WHERE asset <> '{HYPE_ASSET}'
              AND ts < TIMESTAMPTZ '{CUTOFF_UTC}'
        ),
        causal_vol AS (
            SELECT
                *,
                count(atr14_pct) OVER prior_rows AS p0r_prior_atr_count,
                quantile_cont(atr14_pct, 0.3333333333333333) OVER prior_rows AS p0r_atr_q33,
                quantile_cont(atr14_pct, 0.6666666666666666) OVER prior_rows AS p0r_atr_q67
            FROM donor_base
            WINDOW prior_rows AS (
                PARTITION BY asset ORDER BY ts
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            )
        ),
        donor_market AS (
            SELECT
                ts,
                count(DISTINCT asset) AS pit_universe_size_p0r,
                avg(above_ma7) AS market_breadth_above_ma7_p0r,
                avg(above_ma30) AS market_breadth_above_ma30_p0r,
                avg(CASE WHEN ret_1d > 0 THEN 1.0 ELSE 0.0 END) AS market_up_ratio_1d_p0r,
                stddev_samp(ret_1d) AS market_ret_1d_dispersion_p0r,
                median(ret_7d) AS market_ret_7d_median_p0r,
                median(ret_30d) AS market_ret_30d_median_p0r
            FROM causal_vol
            WHERE tradable_marker_p0
            GROUP BY ts
        ),
        donor_liquidity AS (
            SELECT
                asset,
                ts,
                percent_rank() OVER (
                    PARTITION BY ts ORDER BY quote_volume_30d
                ) AS liquidity_rank_pct_p0r
            FROM causal_vol
            WHERE tradable_marker_p0
        )
        SELECT
            c.*,
            CASE
                WHEN c.p0r_prior_atr_count < {MIN_CAUSAL_VOL_HISTORY} OR c.atr14_pct IS NULL
                    THEN 'insufficient_history'
                WHEN c.atr14_pct <= c.p0r_atr_q33 THEN 'low'
                WHEN c.atr14_pct <= c.p0r_atr_q67 THEN 'mid'
                ELSE 'high'
            END AS volatility_state_p0r,
            m.pit_universe_size_p0r,
            m.market_breadth_above_ma7_p0r,
            m.market_breadth_above_ma30_p0r,
            m.market_up_ratio_1d_p0r,
            m.market_ret_1d_dispersion_p0r,
            m.market_ret_7d_median_p0r,
            m.market_ret_30d_median_p0r,
            q.liquidity_rank_pct_p0r
        FROM causal_vol c
        LEFT JOIN donor_market m USING (ts)
        LEFT JOIN donor_liquidity q USING (asset, ts)
        """
    )

    feature_sql = ",\n            ".join(_feature_expressions())
    label_sql = ",\n            ".join(_label_expressions())
    con.execute(
        f"""
        CREATE OR REPLACE TABLE donor_modeling_p0r AS
        SELECT
            l.asset,
            l.asset_slug,
            l.ts,
            f.feature_known_at,
            l.entry_ts,
            l.side,
            l.side_sign,
            l.calendar_month,
            l.calendar_quarter,
            f.listing_age_days,
            l.entry_ref,
            l.atr_anchor,
            l.atr_anchor / l.entry_ref AS atr_to_entry_p0r,
            f.p0r_prior_atr_count,
            l.tradable_marker_p0,
            abs(f.ret_1d) > {MAX_ABS_RET_1D} AS price_scale_discontinuity_p0r,
            l.atr_anchor / l.entry_ref > {MAX_ATR_TO_ENTRY} AS extreme_atr_scale_p0r,
            (
                l.tradable_marker_p0
                AND l.entry_ref > 0
                AND l.atr_anchor > 0
                AND l.atr_anchor / l.entry_ref <= {MAX_ATR_TO_ENTRY}
                AND abs(f.ret_1d) <= {MAX_ABS_RET_1D}
            ) AS base_model_eligible_p0r,
            (
                l.tradable_marker_p0
                AND l.entry_ref > 0
                AND l.atr_anchor > 0
                AND l.atr_anchor / l.entry_ref <= {MAX_ATR_TO_ENTRY}
                AND abs(f.ret_1d) <= {MAX_ABS_RET_1D}
                AND l.future_path_complete_20d
            ) AS model_eligible_entry_p0r,
            (
                l.tradable_marker_p0
                AND l.entry_ref > 0
                AND l.atr_anchor > 0
                AND l.atr_anchor / l.entry_ref <= {MAX_ATR_TO_ENTRY}
                AND abs(f.ret_1d) <= {MAX_ABS_RET_1D}
                AND l.future_path_complete_5d
            ) AS model_eligible_continue_p0r,
            {feature_sql},
            {label_sql}
        FROM read_parquet('{landmark_glob}', union_by_name=true, hive_partitioning=true) l
        INNER JOIN donor_features_p0r f USING (asset, ts)
        WHERE l.asset <> '{HYPE_ASSET}'
          AND l.ts < TIMESTAMPTZ '{CUTOFF_UTC}'
        """
    )


def _write_panel(con: duckdb.DuckDBPyConnection) -> None:
    _safe_replace_dir(OUTPUT_PANEL_DIR)
    out_path = _sql_path(OUTPUT_PANEL_DIR)
    con.execute(
        f"""
        COPY (
            SELECT
                *,
                year(ts) AS year,
                side AS side_partition
            FROM donor_modeling_p0r
            ORDER BY ts, asset, side
        ) TO '{out_path}' (
            FORMAT PARQUET,
            COMPRESSION ZSTD,
            PARTITION_BY (year, side_partition),
            ROW_GROUP_SIZE 100000
        )
        """
    )


def _build_summary(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    base = _row_dict(
        con.execute(
            """
            SELECT
                count(*) AS donor_landmark_rows,
                count(DISTINCT asset) AS donor_asset_count,
                min(ts) AS min_ts,
                max(ts) AS max_ts,
                count(*) FILTER (WHERE asset = ?) AS hype_rows_in_output,
                count(*) FILTER (WHERE tradable_marker_p0) AS tradable_landmark_rows,
                count(*) FILTER (WHERE base_model_eligible_p0r) AS base_model_eligible_rows,
                count(*) FILTER (WHERE model_eligible_entry_p0r) AS entry_eligible_rows,
                count(*) FILTER (WHERE model_eligible_continue_p0r) AS continue_eligible_rows,
                count(*) FILTER (WHERE price_scale_discontinuity_p0r) AS price_scale_discontinuity_rows,
                count(*) FILTER (WHERE extreme_atr_scale_p0r) AS extreme_atr_scale_rows,
                count(*) FILTER (WHERE volatility_state_p0r = 'insufficient_history') AS insufficient_causal_vol_rows,
                count(*) FILTER (WHERE NOT tradable_marker_p0 AND liquidity_rank_pct_p0r IS NOT NULL) AS nontradable_with_liquidity_rank_rows,
                avg(CASE WHEN model_eligible_entry_p0r THEN CAST(label_entry_success_20d AS INTEGER) END) AS entry_success_rate_eligible,
                avg(CASE WHEN model_eligible_continue_p0r THEN CAST(label_continue_success_5d AS INTEGER) END) AS continue_success_rate_eligible
            FROM donor_modeling_p0r
            """,
            [HYPE_ASSET],
        )
    )
    side_rows = con.execute(
        """
        SELECT
            side,
            count(*) FILTER (WHERE model_eligible_entry_p0r) AS entry_n,
            avg(CASE WHEN model_eligible_entry_p0r THEN CAST(label_entry_success_20d AS INTEGER) END) AS entry_success_rate,
            avg(CASE WHEN model_eligible_entry_p0r THEN label_entry_net_return END) AS entry_net_return_mean,
            median(CASE WHEN model_eligible_entry_p0r THEN label_entry_net_return END) AS entry_net_return_median,
            avg(CASE WHEN model_eligible_entry_p0r THEN future_mfe_atr_20d END) AS entry_mfe_atr_mean,
            avg(CASE WHEN model_eligible_entry_p0r THEN future_mae_atr_20d END) AS entry_mae_atr_mean,
            count(*) FILTER (WHERE model_eligible_continue_p0r) AS continue_n,
            avg(CASE WHEN model_eligible_continue_p0r THEN CAST(label_continue_success_5d AS INTEGER) END) AS continue_success_rate,
            avg(CASE WHEN model_eligible_continue_p0r THEN label_continue_net_return END) AS continue_net_return_mean,
            median(CASE WHEN model_eligible_continue_p0r THEN label_continue_net_return END) AS continue_net_return_median
        FROM donor_modeling_p0r
        GROUP BY side
        ORDER BY side
        """
    ).fetchall()
    columns = [item[0] for item in con.description]
    by_side = [
        {key: _json_scalar(value) for key, value in zip(columns, row, strict=True)}
        for row in side_rows
    ]
    state_rows = con.execute(
        """
        SELECT
            volatility_state_p0r AS state,
            count(*) FILTER (WHERE model_eligible_entry_p0r) AS entry_n,
            avg(CASE WHEN model_eligible_entry_p0r THEN CAST(label_entry_success_20d AS INTEGER) END) AS entry_success_rate,
            count(*) FILTER (WHERE model_eligible_continue_p0r) AS continue_n,
            avg(CASE WHEN model_eligible_continue_p0r THEN CAST(label_continue_success_5d AS INTEGER) END) AS continue_success_rate
        FROM donor_modeling_p0r
        GROUP BY volatility_state_p0r
        ORDER BY volatility_state_p0r
        """
    ).fetchall()
    columns = [item[0] for item in con.description]
    by_state = [
        {key: _json_scalar(value) for key, value in zip(columns, row, strict=True)}
        for row in state_rows
    ]
    return {
        "family": "Binance-1D-Cross-Asset-Trend-Lifecycle",
        "alias": "BIN-1D-CATL",
        "experiment": "P0R Modeling Input Repair",
        "cutoff_utc": CUTOFF_UTC,
        "max_feature_ts": MAX_FEATURE_TS,
        "holdout_read": HOLDOUT_READ,
        "hype_asset": HYPE_ASSET,
        "hype_policy": "entire_asset_sealed_for_post_lock_reveal",
        "eligibility_thresholds": {
            "max_atr_to_entry": MAX_ATR_TO_ENTRY,
            "max_abs_ret_1d": MAX_ABS_RET_1D,
            "min_causal_vol_history": MIN_CAUSAL_VOL_HISTORY,
        },
        "summary": base,
        "by_side": by_side,
        "by_causal_volatility_state": by_state,
        "final_verdict": "MODELING_INPUT_READY",
        "strategy_status": "diagnostic-only / not promoted / not live-ready",
    }


def _write_feature_blocks() -> None:
    payload = {
        "family": "Binance-1D-Cross-Asset-Trend-Lifecycle",
        "experiment": "P0R Modeling Input Repair",
        "hype_asset_excluded": HYPE_ASSET,
        "feature_blocks": FEATURE_BLOCKS,
        "all_allowed_features": [
            feature for block in FEATURE_BLOCKS.values() for feature in block
        ],
        "categorical_features": [
            "volatility_state_p0r",
            "dir_price_ma7_ma30_joint_state",
        ],
        "identity_and_audit_columns": IDENTITY_AUDIT_COLUMNS,
        "label_and_outcome_columns": LABEL_AUDIT_COLUMNS,
        "forbidden_feature_patterns": FORBIDDEN_FEATURE_PATTERNS,
        "target_definitions": {
            "entry": {
                "eligibility": "model_eligible_entry_p0r",
                "target": "label_entry_success_20d",
                "purge_days": 20,
            },
            "continuation": {
                "eligibility": "model_eligible_continue_p0r",
                "target": "label_continue_success_5d",
                "purge_days": 5,
            },
        },
    }
    FEATURE_BLOCKS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _write_report(summary: dict[str, Any]) -> None:
    def pct(value: Any) -> str:
        return "NA" if value is None else f"{float(value):.2%}"

    def num(value: Any, digits: int = 3) -> str:
        return "NA" if value is None else f"{float(value):.{digits}f}"

    s = summary["summary"]
    side_lines = []
    for row in summary["by_side"]:
        side_lines.append(
            f"| {row['side']} | {int(row['entry_n']):,} | {pct(row['entry_success_rate'])} | "
            f"{pct(row['entry_net_return_mean'])} | {num(row['entry_mfe_atr_mean'])} | "
            f"{num(row['entry_mae_atr_mean'])} | {int(row['continue_n']):,} | "
            f"{pct(row['continue_success_rate'])} |"
        )
    state_lines = []
    for row in summary["by_causal_volatility_state"]:
        state_lines.append(
            f"| {row['state']} | {int(row['entry_n']):,} | {pct(row['entry_success_rate'])} | "
            f"{int(row['continue_n']):,} | {pct(row['continue_success_rate'])} |"
        )
    text = f"""# BIN-1D-CATL-P0R 建模输入修复报告

## 裁决

`MODELING_INPUT_READY / diagnostic-only / not promoted / not live-ready`

P0 原始证据未覆盖；P0R 只生成 donor-only 建模输入。`{HYPE_ASSET}` 全资产封存，输出为 `{int(s['hype_rows_in_output'])}` 行；HYPE 不参与 donor 市场聚合、流动性排名或任何标签统计。本轮仍未读取 `2026-05-31 00:00 UTC` 及之后的 HYPE 冻结验证数据。

## 修复结果

- donor：`{int(s['donor_asset_count']):,}` 个资产，`{int(s['donor_landmark_rows']):,}` 条 long/short landmark。
- tradable landmarks：`{int(s['tradable_landmark_rows']):,}`；基础模型资格：`{int(s['base_model_eligible_rows']):,}`。
- 完整且合格的 20d entry：`{int(s['entry_eligible_rows']):,}`，成功率 `{s['entry_success_rate_eligible']:.2%}`。
- 完整且合格的 5d continuation：`{int(s['continue_eligible_rows']):,}`，成功率 `{s['continue_success_rate_eligible']:.2%}`。
- 单日价格尺度异常：`{int(s['price_scale_discontinuity_rows']):,}` 行；ATR/entry 超过 0.50：`{int(s['extreme_atr_scale_rows']):,}` 行。
- 非 tradable 却带 P0R 流动性排名：`{int(s['nontradable_with_liquidity_rank_rows']):,}` 行（必须为 0）。
- 因果波动状态只使用更早历史；不足 30 条历史的方向行：`{int(s['insufficient_causal_vol_rows']):,}`。

## 按方向审计

| side | entry n | entry 成功率 | entry 净收益均值 | 20d MFE/ATR 均值 | 20d MAE/ATR 均值 | continuation n | continuation 成功率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(side_lines)}

MFE 与 MAE 必须按方向分别看；把 long/short 成对汇总会因为路径镜像而产生相同总体分布，这不是标签生成错误。

## 因果波动状态审计

| state | entry n | entry 成功率 | continuation n | continuation 成功率 |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(state_lines)}

这里的状态差异仅用于数据诊断，不能据此选特征、调阈值或宣称策略有效。

## P1 边界

P1 只能读取 `artifacts/p0r_donor_directional_modeling_panel/` 和冻结 allowlist；Entry 与 continuation 分开做 walk-forward。HYPE 只能在模型、特征集、超参数、校准和判定规则全部锁定后，进入一次性独立 reveal。
"""
    REPORT_PATH.write_text(text, encoding="utf-8")


def _write_manifest() -> None:
    artifacts: list[dict[str, str]] = []
    paths = [SPEC_PATH, Path(__file__), FEATURE_BLOCKS_PATH, SUMMARY_PATH, REPORT_PATH]
    paths.extend(sorted(OUTPUT_PANEL_DIR.rglob("*.parquet")))
    for path in paths:
        artifacts.append(
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256_file(path),
            }
        )
    payload = {
        "family": "Binance-1D-Cross-Asset-Trend-Lifecycle",
        "experiment": "P0R Modeling Input Repair",
        "holdout_read": HOLDOUT_READ,
        "hype_asset_excluded": HYPE_ASSET,
        "input_lineage": {
            "p0_manifest_path": str(P0_MANIFEST_PATH.relative_to(ROOT)),
            "p0_manifest_sha256": sha256_file(P0_MANIFEST_PATH),
        },
        "artifacts": artifacts,
    }
    MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def run(*, keep_work_db: bool = False) -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    DIAGNOSTIC_DIR.mkdir(parents=True, exist_ok=True)
    required = [SPEC_PATH, P0_MANIFEST_PATH]
    required.extend([P0_FEATURE_GLOB.parent.parent, P0_LANDMARK_GLOB.parent.parent])
    for path in required:
        if not path.exists():
            raise FileNotFoundError(path)
    if WORK_DB.exists():
        WORK_DB.unlink()
    con = duckdb.connect(str(WORK_DB))
    con.execute("SET TimeZone='UTC'")
    con.execute("SET threads TO 8")
    try:
        _create_tables(con)
        _write_panel(con)
        summary = _build_summary(con)
        if summary["summary"]["hype_rows_in_output"] != 0:
            summary["final_verdict"] = "DATASET_INTEGRITY_FAILED"
        if summary["summary"]["nontradable_with_liquidity_rank_rows"] != 0:
            summary["final_verdict"] = "DATASET_INTEGRITY_FAILED"
        if str(summary["summary"]["max_ts"]) >= CUTOFF_UTC:
            summary["final_verdict"] = "DATASET_INTEGRITY_FAILED"
        _write_feature_blocks()
        SUMMARY_PATH.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _write_report(summary)
        _write_manifest()
        if summary["final_verdict"] != "MODELING_INPUT_READY":
            raise RuntimeError(f"P0R failed closed: {summary['final_verdict']}")
        return summary
    finally:
        con.close()
        if not keep_work_db and WORK_DB.exists():
            WORK_DB.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-work-db", action="store_true")
    args = parser.parse_args()
    summary = run(keep_work_db=args.keep_work_db)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
