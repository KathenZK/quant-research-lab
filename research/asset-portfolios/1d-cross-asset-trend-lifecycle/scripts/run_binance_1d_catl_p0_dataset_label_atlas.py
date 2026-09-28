#!/usr/bin/env python3
"""Build BIN-1D-CATL P0 causal feature and label atlas.

This script intentionally does not train models, tune parameters, or create a
strategy/backtest. It builds auditable panels and diagnostics only.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import random
import shutil
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research" / "asset-portfolios" / "1d-cross-asset-trend-lifecycle"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAGNOSTIC_DIR = FAMILY_DIR / "diagnostics"
SPEC_PATH = (
    FAMILY_DIR
    / "specs"
    / "binance-1d-catl-p0-dataset-label-atlas-contract-2026-08-31.md"
)

PRICE_15M_DIR = (
    ROOT
    / "data"
    / "normalized"
    / "ohlcv"
    / "exchange=binance"
    / "market_type=perp"
    / "timeframe=15m"
)
FUNDING_DIR = (
    ROOT
    / "data"
    / "normalized"
    / "funding_rates"
    / "exchange=binance"
    / "market_type=perp"
)

CUTOFF_UTC = pd.Timestamp("2026-05-31 00:00:00+00:00")
MAX_FEATURE_TS = pd.Timestamp("2026-05-30 00:00:00+00:00")
FEE_PER_FILL = 0.001
SLIPPAGE_PER_FILL = 0.0004
ROUND_TRIP_COST = 2.0 * (FEE_PER_FILL + SLIPPAGE_PER_FILL)
LEVERAGE = 1.0
PRIMARY_ENTRY_FAV_ATR = 2.0
PRIMARY_ENTRY_ADV_ATR = 1.0
PRIMARY_ENTRY_HORIZON_DAYS = 20
PRIMARY_CONTINUE_FAV_ATR = 1.0
PRIMARY_CONTINUE_ADV_ATR = 0.75
PRIMARY_CONTINUE_HORIZON_DAYS = 5
FAV_THRESHOLDS = (0.5, 1.0, 1.5, 2.0, 3.0)
ADV_THRESHOLDS = (0.5, 0.75, 1.0, 1.5, 2.0)
HORIZON_DAYS = (3, 5, 7, 14, 20, 30)
MAX_HORIZON_HOURS = max(HORIZON_DAYS) * 24
RANDOM_SEED = 20260831
HOLDOUT_READ = False


@dataclass(frozen=True)
class Paths:
    work_db: Path
    hourly_parquet: Path
    feature_panel_dir: Path
    landmark_panel_dir: Path
    field_dictionary: Path
    data_quality_report: Path
    label_report: Path
    summary_json: Path
    manifest_json: Path
    html_atlas: Path


def p0_paths() -> Paths:
    return Paths(
        work_db=ARTIFACT_DIR / "_catl_p0_work.duckdb",
        hourly_parquet=ARTIFACT_DIR / "_catl_p0_hourly_from_15m.parquet",
        feature_panel_dir=ARTIFACT_DIR / "p0_asset_day_feature_panel",
        landmark_panel_dir=ARTIFACT_DIR / "p0_directional_landmark_panel",
        field_dictionary=ARTIFACT_DIR / "binance_1d_catl_p0_field_dictionary.md",
        data_quality_report=DIAGNOSTIC_DIR
        / "binance-1d-catl-p0-data-quality-2026-08-31.md",
        label_report=DIAGNOSTIC_DIR
        / "binance-1d-catl-p0-label-distribution-2026-08-31.md",
        summary_json=ARTIFACT_DIR / "binance_1d_catl_p0_summary.json",
        manifest_json=ARTIFACT_DIR / "binance_1d_catl_p0_manifest.json",
        html_atlas=ARTIFACT_DIR / "binance_1d_catl_p0_label_quality_atlas.html",
    )


def ensure_dirs(paths: Paths) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    DIAGNOSTIC_DIR.mkdir(parents=True, exist_ok=True)
    for path in (paths.feature_panel_dir, paths.landmark_panel_dir):
        path.mkdir(parents=True, exist_ok=True)


def normalize_ts(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True).dt.tz_convert("UTC").astype("datetime64[ns, UTC]")


def list_part_files(base: Path) -> list[str]:
    files = sorted(str(path) for path in base.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No partition parquet files found under {base}")
    return files


def symbol_slug(symbol: str) -> str:
    return (
        symbol.lower()
        .replace("/", "_")
        .replace(":", "_")
        .replace("-", "_")
        .replace(".", "_")
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_partitioned(df: pd.DataFrame, out_dir: Path, *, side_partition: bool = False) -> int:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    df["year"] = pd.to_datetime(df["ts"], utc=True).dt.year.astype(int)
    group_cols = ["asset_slug", "year"] + (["side"] if side_partition else [])
    count = 0
    for keys, group in df.groupby(group_cols, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        asset_slug_value = keys[0]
        year_value = int(keys[1])
        parts = [f"asset_slug_partition={asset_slug_value}", f"year={year_value}"]
        if side_partition:
            parts.append(f"side_partition={keys[2]}")
        target_dir = out_dir.joinpath(*parts)
        target_dir.mkdir(parents=True, exist_ok=True)
        group.drop(columns=["year"]).to_parquet(target_dir / "part-0000.parquet", index=False)
        count += 1
    return count


def build_hourly_from_15m(paths: Paths, *, force: bool) -> None:
    if paths.hourly_parquet.exists() and not force:
        return
    if paths.work_db.exists():
        paths.work_db.unlink()

    price_files = list_part_files(PRICE_15M_DIR)
    con = duckdb.connect(str(paths.work_db))
    con.execute("SET TimeZone='UTC'")
    con.execute("SET threads TO 8")
    con.execute(
        """
        CREATE OR REPLACE TABLE hourly AS
        WITH dedup_15m AS (
            SELECT
                symbol,
                any_value(base_asset) AS base_asset,
                any_value(quote_asset) AS quote_asset,
                ts,
                any_value(open) AS open,
                max(high) AS high,
                min(low) AS low,
                any_value(close) AS close,
                any_value(volume) AS volume,
                any_value(quote_volume) AS quote_volume,
                any_value(trade_count) AS trade_count,
                bool_and(is_closed) AS is_closed
            FROM read_parquet($price_files, union_by_name=true, hive_partitioning=false)
            WHERE ts < TIMESTAMPTZ '2026-05-31 00:00:00+00:00'
              AND is_closed = true
              AND quote_asset = 'USDT'
              AND market_type = 'perp'
            GROUP BY symbol, ts
        )
        SELECT
            symbol,
            any_value(base_asset) AS base_asset,
            date_trunc('hour', ts) AS hour_ts,
            arg_min(open, ts) AS open,
            max(high) AS high,
            min(low) AS low,
            arg_max(close, ts) AS close,
            sum(volume) AS volume,
            sum(quote_volume) AS quote_volume,
            sum(trade_count) AS trade_count,
            count(*) AS bars_15m,
            bool_and(is_closed) AS all_closed,
            min(ts) AS first_15m_ts,
            max(ts) AS last_15m_ts
        FROM dedup_15m
        GROUP BY symbol, date_trunc('hour', ts)
        HAVING count(*) = 4 AND bool_and(is_closed)
        ORDER BY symbol, hour_ts
        """,
        {"price_files": price_files},
    )
    con.execute(
        """
        COPY hourly TO $target
        (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
        """,
        {"target": str(paths.hourly_parquet)},
    )
    con.close()


def connect_work_db(paths: Paths) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(paths.work_db))
    con.execute("SET TimeZone='UTC'")
    con.execute("SET threads TO 8")
    if not table_exists(con, "hourly"):
        con.execute(
            """
            CREATE OR REPLACE TABLE hourly AS
            SELECT * FROM read_parquet($hourly, union_by_name=true, hive_partitioning=false)
            """,
            {"hourly": str(paths.hourly_parquet)},
        )
    return con


def table_exists(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    row = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = $name",
        {"name": name},
    ).fetchone()
    return bool(row and row[0])


def load_daily_from_hourly(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    daily = con.execute(
        """
        SELECT
            symbol AS asset,
            any_value(base_asset) AS base_asset,
            date_trunc('day', hour_ts) AS ts,
            arg_min(open, hour_ts) AS open,
            max(high) AS high,
            min(low) AS low,
            arg_max(close, hour_ts) AS close,
            sum(volume) AS volume,
            sum(quote_volume) AS quote_volume,
            sum(trade_count) AS trade_count,
            count(*) AS hours_in_day,
            min(bars_15m) AS min_15m_per_hour,
            bool_and(all_closed) AS all_closed,
            min(hour_ts) AS first_hour_ts,
            max(hour_ts) AS last_hour_ts
        FROM hourly
        GROUP BY symbol, date_trunc('day', hour_ts)
        ORDER BY symbol, ts
        """
    ).df()
    daily["ts"] = normalize_ts(daily["ts"])
    daily["first_hour_ts"] = normalize_ts(daily["first_hour_ts"])
    daily["last_hour_ts"] = normalize_ts(daily["last_hour_ts"])
    daily["complete_day"] = (
        (daily["hours_in_day"] == 24)
        & (daily["min_15m_per_hour"] == 4)
        & daily["all_closed"].astype(bool)
    )
    daily = daily.loc[daily["ts"] <= MAX_FEATURE_TS].copy()
    daily = daily.loc[daily["complete_day"]].copy()
    return daily


def load_funding_daily() -> pd.DataFrame:
    files = list_part_files(FUNDING_DIR)
    con = duckdb.connect(":memory:")
    con.execute("SET TimeZone='UTC'")
    funding = con.execute(
        """
        WITH dedup_funding AS (
            SELECT
                symbol,
                ts,
                avg(funding_rate) AS funding_rate
            FROM read_parquet($files, union_by_name=true, hive_partitioning=false)
            WHERE ts < TIMESTAMPTZ '2026-05-31 00:00:00+00:00'
              AND market_type = 'perp'
            GROUP BY symbol, ts
        )
        SELECT
            symbol AS asset,
            date_trunc('day', ts) AS ts,
            sum(funding_rate) AS funding_rate_sum,
            avg(funding_rate) AS funding_rate_mean,
            count(*) AS funding_obs
        FROM dedup_funding
        GROUP BY symbol, date_trunc('day', ts)
        ORDER BY symbol, ts
        """,
        {"files": files},
    ).df()
    con.close()
    funding["ts"] = normalize_ts(funding["ts"])
    return funding


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    ranges = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def run_lengths(mask: pd.Series) -> pd.Series:
    arr = mask.fillna(False).to_numpy(dtype=bool)
    out = np.zeros(len(arr), dtype=np.int32)
    current = 0
    for i, value in enumerate(arr):
        current = current + 1 if value else 0
        out[i] = current
    return pd.Series(out, index=mask.index)


def days_since_last_cross(cross: pd.Series) -> pd.Series:
    arr = cross.to_numpy(dtype=np.int8)
    out = np.full(len(arr), np.nan)
    last = math.nan
    for i, value in enumerate(arr):
        if value != 0:
            last = 0
        elif not math.isnan(last):
            last += 1
        out[i] = last
    return pd.Series(out, index=cross.index)


def add_asset_features(daily: pd.DataFrame, funding: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    funding = funding.copy()
    merged = daily.merge(funding, how="left", on=["asset", "ts"])
    for asset, group in merged.groupby("asset", sort=False):
        g = group.sort_values("ts").copy()
        g["asset_slug"] = symbol_slug(asset)
        g["feature_known_at"] = g["ts"] + pd.Timedelta(days=1)
        g["next_entry_ts"] = g["ts"] + pd.Timedelta(days=1)
        first_ts = g["ts"].iloc[0]
        g["listing_age_days"] = (g["ts"] - first_ts).dt.days.astype(int)
        g["calendar_month"] = g["ts"].dt.strftime("%Y-%m")
        g["calendar_quarter"] = (
            g["ts"].dt.year.astype(str) + "Q" + g["ts"].dt.quarter.astype(str)
        )
        g["gap_since_prev_days"] = g["ts"].diff().dt.days.fillna(1).astype(int)
        g["gap_before_day"] = g["gap_since_prev_days"] > 1

        idxed = g.set_index("ts")
        g["complete_days_30d"] = (
            idxed["complete_day"].astype(float).rolling("30D").sum().to_numpy()
        )
        denom = np.minimum(30.0, g["listing_age_days"].to_numpy(dtype=float) + 1.0)
        g["continuity_30d"] = g["complete_days_30d"] / denom
        g["quote_volume_30d"] = (
            idxed["quote_volume"].rolling("30D", min_periods=1).mean().to_numpy()
        )

        tr = true_range(g)
        g["tr"] = tr
        for n in (7, 14, 30):
            g[f"atr{n}"] = tr.rolling(n, min_periods=n).mean()
            g[f"atr{n}_pct"] = g[f"atr{n}"] / g["close"]
        g["atr14_to_atr30"] = g["atr14"] / g["atr30"]
        g["atr7_to_atr30"] = g["atr7"] / g["atr30"]

        ret1 = g["close"].pct_change()
        g["ret_1d"] = ret1
        for n in (3, 7, 14, 30, 60):
            g[f"ret_{n}d"] = g["close"].pct_change(n)
            roll_high = g["high"].rolling(n, min_periods=n).max()
            roll_low = g["low"].rolling(n, min_periods=n).min()
            g[f"range_pos_{n}d"] = (g["close"] - roll_low) / (roll_high - roll_low)
            g[f"drawdown_from_high_{n}d"] = g["close"] / roll_high - 1.0
            g[f"distance_to_high_{n}d_atr"] = (roll_high - g["close"]) / g["atr14"]
            g[f"distance_to_low_{n}d_atr"] = (g["close"] - roll_low) / g["atr14"]
        for n in (7, 14, 30, 60):
            abs_path = g["close"].diff().abs().rolling(n, min_periods=n).sum()
            g[f"path_efficiency_{n}d"] = (g["close"] - g["close"].shift(n)).abs() / abs_path
        g["up_run_days"] = run_lengths(g["close"] > g["close"].shift(1))
        g["down_run_days"] = run_lengths(g["close"] < g["close"].shift(1))
        g["shock_day"] = (ret1.abs() > 2.0 * ret1.rolling(30, min_periods=20).std()).fillna(False)
        g["repair_state"] = ((g["ret_3d"] > 0) & (g["drawdown_from_high_30d"] > -0.15)).fillna(False)
        g["sideways_state"] = ((g["atr7_to_atr30"] < 0.75) & (g["path_efficiency_14d"] < 0.35)).fillna(False)
        g["reexpansion_state"] = ((g["atr7_to_atr30"] > 1.25) & (g["path_efficiency_7d"] > 0.45)).fillna(False)

        above_map: dict[int, pd.Series] = {}
        slope_sign_map: dict[int, pd.Series] = {}
        cross_map: dict[int, pd.Series] = {}
        for n in (7, 14, 30, 60):
            ma = g["close"].rolling(n, min_periods=n).mean()
            g[f"ma{n}"] = ma
            g[f"close_ma{n}_dist_atr"] = (g["close"] - ma) / g["atr14"]
            above = (g["close"] > ma).astype("Int8")
            above_map[n] = above
            g[f"above_ma{n}"] = above
            for k in (1, 3, 5):
                g[f"ma{n}_slope_{k}d_atr"] = (ma - ma.shift(k)) / (k * g["atr14"])
            g[f"ma{n}_slope_change_3d"] = (
                g[f"ma{n}_slope_1d_atr"] - g[f"ma{n}_slope_1d_atr"].shift(3)
            )
            g[f"ma{n}_slope_accel_5d"] = (
                g[f"ma{n}_slope_1d_atr"]
                - 2.0 * g[f"ma{n}_slope_1d_atr"].shift(2)
                + g[f"ma{n}_slope_1d_atr"].shift(4)
            )
            slope_sign = np.where(g[f"ma{n}_slope_3d_atr"] > 0.02, 1, np.where(g[f"ma{n}_slope_3d_atr"] < -0.02, -1, 0))
            slope_sign_map[n] = pd.Series(slope_sign, index=g.index)
            cross = np.where(
                (g["close"] > ma) & (g["close"].shift(1) <= ma.shift(1)),
                1,
                np.where((g["close"] < ma) & (g["close"].shift(1) >= ma.shift(1)), -1, 0),
            )
            cross_s = pd.Series(cross, index=g.index).astype(np.int8)
            cross_map[n] = cross_s
            g[f"raw_ma{n}_cross_dir"] = cross_s
            g[f"days_since_ma{n}_cross"] = days_since_last_cross(cross_s)
            g[f"ma{n}_cross_count_7d"] = (cross_s != 0).rolling(7, min_periods=1).sum()
            g[f"ma{n}_cross_count_14d"] = (cross_s != 0).rolling(14, min_periods=1).sum()

        g["ma_stack_score"] = (
            (g["ma7"] > g["ma14"]).astype(int)
            + (g["ma14"] > g["ma30"]).astype(int)
            + (g["ma30"] > g["ma60"]).astype(int)
        )
        g["fast_slow_ma_direction_aligned"] = (
            (slope_sign_map[7] == slope_sign_map[30]) & (slope_sign_map[7] != 0)
        )
        g["ma7_cross_with_ma30_opposite_slope"] = (
            (cross_map[7] != 0) & (cross_map[7] * slope_sign_map[30] < 0)
        )
        g["price_ma7_ma30_joint_state"] = np.select(
            [
                (above_map[7] == 1) & (above_map[30] == 1),
                (above_map[7] == 1) & (above_map[30] == 0),
                (above_map[7] == 0) & (above_map[30] == 1),
                (above_map[7] == 0) & (above_map[30] == 0),
            ],
            ["above_both", "above_ma7_only", "above_ma30_only", "below_both"],
            default="unknown",
        )

        g["daily_range_atr"] = (g["high"] - g["low"]) / g["atr14"]
        g["body_atr"] = (g["close"] - g["open"]).abs() / g["atr14"]
        g["upper_wick_atr"] = (g["high"] - g[["open", "close"]].max(axis=1)) / g["atr14"]
        g["lower_wick_atr"] = (g[["open", "close"]].min(axis=1) - g["low"]) / g["atr14"]
        g["close_location"] = (g["close"] - g["low"]) / (g["high"] - g["low"])
        g["large_cross_degree_atr"] = g[
            [f"close_ma{n}_dist_atr" for n in (7, 14, 30, 60)]
        ].abs().max(axis=1)

        for n in (7, 30):
            g[f"volume_to_{n}d"] = g["volume"] / g["volume"].rolling(n, min_periods=n).mean()
            g[f"quote_volume_to_{n}d"] = g["quote_volume"] / g["quote_volume"].rolling(n, min_periods=n).mean()
        g["volume_change_1d"] = g["volume"].pct_change()
        g["funding_rate_sum"] = g["funding_rate_sum"].fillna(0.0)
        g["funding_missing"] = g["funding_obs"].isna()
        g["funding_mean_7d"] = g["funding_rate_sum"].rolling(7, min_periods=1).mean()
        g["funding_mean_30d"] = g["funding_rate_sum"].rolling(30, min_periods=1).mean()
        g["funding_change_3d"] = g["funding_rate_sum"] - g["funding_rate_sum"].shift(3)

        g["probe_raw_ma7_cross"] = g["raw_ma7_cross_dir"] != 0
        g["probe_raw_ma14_cross"] = g["raw_ma14_cross_dir"] != 0
        g["probe_raw_ma30_cross"] = g["raw_ma30_cross_dir"] != 0
        g["probe_raw_ma60_cross"] = g["raw_ma60_cross_dir"] != 0
        g["probe_20d_range_breakout_up"] = g["close"] >= g["high"].shift(1).rolling(20, min_periods=20).max()
        g["probe_20d_range_breakout_down"] = g["close"] <= g["low"].shift(1).rolling(20, min_periods=20).min()
        g["probe_same_side_ma7_no_cross"] = (g["above_ma7"].notna()) & (~g["probe_raw_ma7_cross"])
        g["probe_same_side_ma30_no_cross"] = (g["above_ma30"].notna()) & (~g["probe_raw_ma30_cross"])
        g["probe_ma7_ma30_direction_aligned"] = g["fast_slow_ma_direction_aligned"]
        g["probe_ma7_cross_ma30_opposite"] = g["ma7_cross_with_ma30_opposite_slope"]
        if g["atr14_pct"].notna().sum() >= 3:
            g["volatility_state"] = pd.qcut(
                g["atr14_pct"].rank(method="first"),
                q=3,
                labels=["low", "mid", "high"],
                duplicates="drop",
            ).astype(str)
        else:
            g["volatility_state"] = "insufficient_history"

        rows.append(g)

    features = pd.concat(rows, ignore_index=True)
    features["tradable_marker_p0"] = (
        features["complete_day"].astype(bool)
        & (features["listing_age_days"] >= 60)
        & (features["continuity_30d"] >= 0.95)
        & np.isfinite(features["quote_volume_30d"])
        & (features["quote_volume_30d"] > 0.0)
    )
    features = add_market_features(features)
    return features.sort_values(["asset", "ts"]).reset_index(drop=True)


def add_market_features(features: pd.DataFrame) -> pd.DataFrame:
    df = features.copy()
    universe = df.loc[df["tradable_marker_p0"]].copy()
    grouped = universe.groupby("ts", sort=True)
    market = grouped.agg(
        pit_universe_size=("asset", "nunique"),
        market_breadth_above_ma7=("above_ma7", "mean"),
        market_breadth_above_ma30=("above_ma30", "mean"),
        market_up_ratio_1d=("ret_1d", lambda s: float((s > 0).mean()) if len(s) else np.nan),
        market_ret_1d_dispersion=("ret_1d", "std"),
        market_ret_7d_median=("ret_7d", "median"),
        market_ret_30d_median=("ret_30d", "median"),
    ).reset_index()
    df = df.merge(market, on="ts", how="left")
    btc = df.loc[df["asset"] == "BTC/USDT:USDT", ["ts", "ret_7d", "ret_30d", "above_ma7", "above_ma30"]].rename(
        columns={
            "ret_7d": "btc_ret_7d",
            "ret_30d": "btc_ret_30d",
            "above_ma7": "btc_above_ma7",
            "above_ma30": "btc_above_ma30",
        }
    )
    df = df.merge(btc, on="ts", how="left")
    df["relative_to_btc_ret_7d"] = df["ret_7d"] - df["btc_ret_7d"]
    df["relative_to_btc_ret_30d"] = df["ret_30d"] - df["btc_ret_30d"]
    df["relative_to_market_median_ret_7d"] = df["ret_7d"] - df["market_ret_7d_median"]
    df["relative_to_market_median_ret_30d"] = df["ret_30d"] - df["market_ret_30d_median"]
    df["liquidity_rank_pct"] = df.groupby("ts")["quote_volume_30d"].rank(pct=True)
    return df


def threshold_col(prefix: str, threshold: float) -> str:
    return f"{prefix}_{str(threshold).replace('.', '_')}atr_hours"


def result_from_hours(fav_hour: float, adv_hour: float, horizon_hours: int) -> tuple[str, bool, bool, float]:
    fav = np.isfinite(fav_hour) and fav_hour <= horizon_hours
    adv = np.isfinite(adv_hour) and adv_hour <= horizon_hours
    if fav and adv:
        if fav_hour < adv_hour:
            return "favorable_first", True, True, fav_hour
        if adv_hour < fav_hour:
            return "adverse_first", False, False, adv_hour
        return "ambiguous_same_hour", False, True, adv_hour
    if fav:
        return "favorable_first", True, True, fav_hour
    if adv:
        return "adverse_first", False, False, adv_hour
    return "timeout", False, False, float(horizon_hours)


def build_funding_lookup(funding: pd.DataFrame) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    lookup: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for asset, group in funding.groupby("asset", sort=False):
        g = group.sort_values("ts")
        times = g["ts"].astype("int64").to_numpy()
        csum = np.r_[0.0, g["funding_rate_sum"].fillna(0.0).to_numpy(dtype=float).cumsum()]
        lookup[asset] = (times, csum)
    return lookup


def funding_sum_between(
    lookup: dict[str, tuple[np.ndarray, np.ndarray]],
    asset: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> float:
    item = lookup.get(asset)
    if item is None:
        return 0.0
    times, csum = item
    start_ns = pd.Timestamp(start_ts).value
    end_ns = pd.Timestamp(end_ts).value
    left = np.searchsorted(times, start_ns, side="left")
    right = np.searchsorted(times, end_ns, side="right")
    return float(csum[right] - csum[left])


def hit_net_return(
    *,
    side_sign: int,
    result: str,
    fav_atr: float,
    adv_atr: float,
    atr_anchor: float,
    entry_ref: float,
    terminal_return: float,
    funding_sum: float,
) -> float:
    if result == "favorable_first":
        price_ret = fav_atr * atr_anchor / entry_ref
    elif result in ("adverse_first", "ambiguous_same_hour"):
        price_ret = -adv_atr * atr_anchor / entry_ref
    else:
        price_ret = terminal_return
    funding_ret = -side_sign * funding_sum
    return LEVERAGE * price_ret + funding_ret - ROUND_TRIP_COST


def build_landmarks(
    features: pd.DataFrame,
    con: duckdb.DuckDBPyConnection,
    funding: pd.DataFrame,
    *,
    max_assets: int | None = None,
) -> pd.DataFrame:
    funding_lookup = build_funding_lookup(funding)
    assets = list(features["asset"].drop_duplicates())
    if max_assets is not None:
        assets = assets[:max_assets]
    rows: list[pd.DataFrame] = []

    feature_cols_for_direction = [
        "ret_1d",
        "ret_3d",
        "ret_7d",
        "ret_14d",
        "ret_30d",
        "ret_60d",
        "close_ma7_dist_atr",
        "close_ma14_dist_atr",
        "close_ma30_dist_atr",
        "close_ma60_dist_atr",
        "ma7_slope_3d_atr",
        "ma14_slope_3d_atr",
        "ma30_slope_3d_atr",
        "ma60_slope_3d_atr",
        "distance_to_high_30d_atr",
        "distance_to_low_30d_atr",
        "relative_to_btc_ret_7d",
        "relative_to_btc_ret_30d",
        "relative_to_market_median_ret_7d",
        "relative_to_market_median_ret_30d",
    ]

    for asset in assets:
        feats = features.loc[features["asset"] == asset].sort_values("ts").reset_index(drop=True)
        hourly = con.execute(
            """
            SELECT hour_ts, open, high, low, close
            FROM hourly
            WHERE symbol = $asset
            ORDER BY hour_ts
            """,
            {"asset": asset},
        ).df()
        if hourly.empty:
            continue
        hourly["hour_ts"] = normalize_ts(hourly["hour_ts"])
        hour_ns = hourly["hour_ts"].astype("int64").to_numpy()
        hour_pos = {int(ts): i for i, ts in enumerate(hour_ns)}
        high = hourly["high"].to_numpy(dtype=float)
        low = hourly["low"].to_numpy(dtype=float)
        close = hourly["close"].to_numpy(dtype=float)
        hclose = hourly["close"].to_numpy(dtype=float)

        base = feats.copy()
        base["entry_ts"] = base["next_entry_ts"]
        entry_ns = base["entry_ts"].astype("int64").to_numpy()
        positions = np.array([hour_pos.get(int(ts), -1) for ts in entry_ns], dtype=np.int64)
        base["entry_pos"] = positions
        base["entry_ref"] = np.where(positions >= 0, hourly["open"].to_numpy(dtype=float)[np.clip(positions, 0, len(hourly) - 1)], np.nan)
        base["atr_anchor"] = base["atr14"]
        valid_anchor = (
            (positions >= 0)
            & np.isfinite(base["entry_ref"].to_numpy(dtype=float))
            & np.isfinite(base["atr_anchor"].to_numpy(dtype=float))
            & (base["atr_anchor"].to_numpy(dtype=float) > 0)
        )

        for side_name, side_sign in (("long", 1), ("short", -1)):
            out = base[[
                "asset",
                "asset_slug",
                "ts",
                "calendar_month",
                "calendar_quarter",
                "entry_ts",
                "entry_ref",
                "atr_anchor",
                "tradable_marker_p0",
                "volatility_state",
                "raw_ma7_cross_dir",
                "raw_ma14_cross_dir",
                "raw_ma30_cross_dir",
                "raw_ma60_cross_dir",
                "above_ma7",
                "above_ma30",
                "probe_20d_range_breakout_up",
                "probe_20d_range_breakout_down",
                "probe_same_side_ma7_no_cross",
                "probe_same_side_ma30_no_cross",
                "probe_ma7_ma30_direction_aligned",
                "probe_ma7_cross_ma30_opposite",
            ]].copy()
            out["side"] = side_name
            out["side_sign"] = side_sign
            for col in feature_cols_for_direction:
                out[f"dir_{col}"] = side_sign * base[col]
            out["label_start_ts"] = out["entry_ts"]
            out["label_end_ts_5d"] = out["entry_ts"] + pd.Timedelta(days=PRIMARY_CONTINUE_HORIZON_DAYS)
            out["label_end_ts_20d"] = out["entry_ts"] + pd.Timedelta(days=PRIMARY_ENTRY_HORIZON_DAYS)
            out["label_observation_end_ts_30d"] = out["entry_ts"] + pd.Timedelta(days=max(HORIZON_DAYS))

            for threshold in FAV_THRESHOLDS:
                out[threshold_col("future_first_favorable", threshold)] = np.nan
            for threshold in ADV_THRESHOLDS:
                out[threshold_col("future_first_adverse", threshold)] = np.nan
            for days in HORIZON_DAYS:
                out[f"future_path_complete_{days}d"] = False
            for days in (5, 20):
                out[f"future_mfe_atr_{days}d"] = np.nan
                out[f"future_mae_atr_{days}d"] = np.nan
                out[f"future_terminal_direction_return_{days}d"] = np.nan
            out["future_path_efficiency_20d"] = np.nan

            valid_idx = np.where(valid_anchor)[0]
            valid_pos = positions[valid_idx]
            valid_entry_ns = entry_ns[valid_idx]
            valid_entry_ref = base["entry_ref"].to_numpy(dtype=float)[valid_idx]
            valid_atr = base["atr_anchor"].to_numpy(dtype=float)[valid_idx]
            hour_ns_delta = pd.Timedelta(hours=1).value

            complete_cache: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
            for days in HORIZON_DAYS:
                h = days * 24
                if len(valid_idx) == 0 or len(hour_ns) < h:
                    complete_cache[h] = (
                        np.array([], dtype=int),
                        np.array([], dtype=int),
                        np.array([], dtype=float),
                        np.array([], dtype=float),
                    )
                    continue
                in_bounds = (valid_pos >= 0) & (valid_pos + h - 1 < len(hour_ns))
                expected_end = valid_entry_ns + (h - 1) * hour_ns_delta
                contiguous = np.zeros(len(valid_idx), dtype=bool)
                contiguous[in_bounds] = hour_ns[valid_pos[in_bounds] + h - 1] == expected_end[in_bounds]
                idx = valid_idx[contiguous]
                complete_cache[h] = (
                    idx,
                    valid_pos[contiguous],
                    valid_entry_ref[contiguous],
                    valid_atr[contiguous],
                )
                if len(idx):
                    out.loc[idx, f"future_path_complete_{days}d"] = True

            def fill_window(hours: int) -> None:
                idx, pos_arr, entry_ref_arr, atr_arr = complete_cache.get(
                    hours,
                    (
                        np.array([], dtype=int),
                        np.array([], dtype=int),
                        np.array([], dtype=float),
                        np.array([], dtype=float),
                    ),
                )
                if len(idx) == 0 or len(high) < hours:
                    return
                high_win = np.lib.stride_tricks.sliding_window_view(high, hours)[pos_arr]
                low_win = np.lib.stride_tricks.sliding_window_view(low, hours)[pos_arr]
                close_win = np.lib.stride_tricks.sliding_window_view(close, hours)[pos_arr]
                if side_sign == 1:
                    fav_path = (high_win - entry_ref_arr[:, None]) / atr_arr[:, None]
                    adv_path = (entry_ref_arr[:, None] - low_win) / atr_arr[:, None]
                else:
                    fav_path = (entry_ref_arr[:, None] - low_win) / atr_arr[:, None]
                    adv_path = (high_win - entry_ref_arr[:, None]) / atr_arr[:, None]

                for threshold in FAV_THRESHOLDS:
                    col = threshold_col("future_first_favorable", threshold)
                    hit = fav_path >= threshold
                    vals = np.where(hit.any(axis=1), hit.argmax(axis=1) + 1, np.nan)
                    current = out.loc[idx, col].to_numpy(dtype=float)
                    fill = np.isnan(current) & np.isfinite(vals)
                    if fill.any():
                        out.loc[idx[fill], col] = vals[fill]
                for threshold in ADV_THRESHOLDS:
                    col = threshold_col("future_first_adverse", threshold)
                    hit = adv_path >= threshold
                    vals = np.where(hit.any(axis=1), hit.argmax(axis=1) + 1, np.nan)
                    current = out.loc[idx, col].to_numpy(dtype=float)
                    fill = np.isnan(current) & np.isfinite(vals)
                    if fill.any():
                        out.loc[idx[fill], col] = vals[fill]

                days = hours // 24
                if days in (5, 20):
                    out.loc[idx, f"future_mfe_atr_{days}d"] = np.nanmax(fav_path, axis=1)
                    out.loc[idx, f"future_mae_atr_{days}d"] = np.nanmax(adv_path, axis=1)
                    terminal = side_sign * (close_win[:, -1] / entry_ref_arr - 1.0)
                    out.loc[idx, f"future_terminal_direction_return_{days}d"] = terminal
                    if days == 20:
                        prev = np.concatenate([entry_ref_arr[:, None], close_win[:, :-1]], axis=1)
                        path_sum = np.abs(close_win / prev - 1.0).sum(axis=1)
                        efficiency = np.full(len(path_sum), np.nan, dtype=float)
                        np.divide(np.abs(terminal), path_sum, out=efficiency, where=path_sum > 0)
                        out.loc[idx, "future_path_efficiency_20d"] = efficiency

            for hours in (MAX_HORIZON_HOURS, PRIMARY_ENTRY_HORIZON_DAYS * 24, PRIMARY_CONTINUE_HORIZON_DAYS * 24):
                fill_window(hours)

            entry_fav = out[threshold_col("future_first_favorable", PRIMARY_ENTRY_FAV_ATR)].to_numpy(dtype=float)
            entry_adv = out[threshold_col("future_first_adverse", PRIMARY_ENTRY_ADV_ATR)].to_numpy(dtype=float)
            cont_fav = out[threshold_col("future_first_favorable", PRIMARY_CONTINUE_FAV_ATR)].to_numpy(dtype=float)
            cont_adv = out[threshold_col("future_first_adverse", PRIMARY_CONTINUE_ADV_ATR)].to_numpy(dtype=float)

            entry_results = [
                result_from_hours(f, a, PRIMARY_ENTRY_HORIZON_DAYS * 24)
                for f, a in zip(entry_fav, entry_adv, strict=False)
            ]
            cont_results = [
                result_from_hours(f, a, PRIMARY_CONTINUE_HORIZON_DAYS * 24)
                for f, a in zip(cont_fav, cont_adv, strict=False)
            ]
            out["label_entry_result"] = [r[0] for r in entry_results]
            out["label_entry_success_20d"] = [r[1] for r in entry_results]
            out["label_entry_success_20d_optimistic"] = [r[2] for r in entry_results]
            out["label_entry_hours_to_hit"] = [r[3] for r in entry_results]
            out["label_entry_ambiguous_same_hour"] = out["label_entry_result"] == "ambiguous_same_hour"
            out["label_continue_result"] = [r[0] for r in cont_results]
            out["label_continue_success_5d"] = [r[1] for r in cont_results]
            out["label_continue_success_5d_optimistic"] = [r[2] for r in cont_results]
            out["label_continue_hours_to_hit"] = [r[3] for r in cont_results]
            out["label_continue_ambiguous_same_hour"] = out["label_continue_result"] == "ambiguous_same_hour"

            out["future_mfe_giveback_20d"] = (
                out["future_mfe_atr_20d"]
                - out["future_terminal_direction_return_20d"] * out["entry_ref"] / out["atr_anchor"]
            )
            valid_20 = out["future_path_complete_20d"].astype(bool) & np.isfinite(out["entry_ref"])
            valid_5 = out["future_path_complete_5d"].astype(bool) & np.isfinite(out["entry_ref"])
            out.loc[~valid_20, ["label_entry_result", "label_entry_success_20d", "label_entry_success_20d_optimistic", "label_entry_hours_to_hit"]] = [
                "incomplete",
                False,
                False,
                np.nan,
            ]
            out.loc[~valid_5, ["label_continue_result", "label_continue_success_5d", "label_continue_success_5d_optimistic", "label_continue_hours_to_hit"]] = [
                "incomplete",
                False,
                False,
                np.nan,
            ]

            entry_net: list[float] = []
            cont_net: list[float] = []
            for rec in out.to_dict("records"):
                if rec["label_entry_result"] == "incomplete":
                    entry_net.append(np.nan)
                else:
                    end_hours = rec["label_entry_hours_to_hit"]
                    if not np.isfinite(end_hours):
                        end_hours = PRIMARY_ENTRY_HORIZON_DAYS * 24
                    end_ts = pd.Timestamp(rec["entry_ts"]) + pd.Timedelta(hours=int(end_hours))
                    fs = funding_sum_between(funding_lookup, asset, pd.Timestamp(rec["entry_ts"]), end_ts)
                    entry_net.append(
                        hit_net_return(
                            side_sign=side_sign,
                            result=rec["label_entry_result"],
                            fav_atr=PRIMARY_ENTRY_FAV_ATR,
                            adv_atr=PRIMARY_ENTRY_ADV_ATR,
                            atr_anchor=rec["atr_anchor"],
                            entry_ref=rec["entry_ref"],
                            terminal_return=rec["future_terminal_direction_return_20d"],
                            funding_sum=fs,
                        )
                    )
                if rec["label_continue_result"] == "incomplete":
                    cont_net.append(np.nan)
                else:
                    end_hours = rec["label_continue_hours_to_hit"]
                    if not np.isfinite(end_hours):
                        end_hours = PRIMARY_CONTINUE_HORIZON_DAYS * 24
                    end_ts = pd.Timestamp(rec["entry_ts"]) + pd.Timedelta(hours=int(end_hours))
                    fs = funding_sum_between(funding_lookup, asset, pd.Timestamp(rec["entry_ts"]), end_ts)
                    cont_net.append(
                        hit_net_return(
                            side_sign=side_sign,
                            result=rec["label_continue_result"],
                            fav_atr=PRIMARY_CONTINUE_FAV_ATR,
                            adv_atr=PRIMARY_CONTINUE_ADV_ATR,
                            atr_anchor=rec["atr_anchor"],
                            entry_ref=rec["entry_ref"],
                            terminal_return=rec["future_terminal_direction_return_5d"],
                            funding_sum=fs,
                        )
                    )
            out["label_entry_net_return"] = entry_net
            out["label_continue_net_return"] = cont_net

            out["probe_raw_ma7_cross_dir"] = out["raw_ma7_cross_dir"] == side_sign
            out["probe_raw_ma14_cross_dir"] = out["raw_ma14_cross_dir"] == side_sign
            out["probe_raw_ma30_cross_dir"] = out["raw_ma30_cross_dir"] == side_sign
            out["probe_raw_ma60_cross_dir"] = out["raw_ma60_cross_dir"] == side_sign
            out["probe_20d_range_breakout_dir"] = np.where(
                side_sign == 1,
                out["probe_20d_range_breakout_up"],
                out["probe_20d_range_breakout_down"],
            ).astype(bool)
            rows.append(out)

    return pd.concat(rows, ignore_index=True).sort_values(["asset", "ts", "side"]).reset_index(drop=True)


def summarize(features: pd.DataFrame, landmarks: pd.DataFrame) -> dict[str, Any]:
    complete_entry = landmarks.loc[landmarks["future_path_complete_20d"].astype(bool)]
    complete_continue = landmarks.loc[landmarks["future_path_complete_5d"].astype(bool)]
    hype_rows = features.loc[features["asset"] == "HYPE/USDT:USDT"]
    summary: dict[str, Any] = {
        "family": "Binance-1D-Cross-Asset-Trend-Lifecycle",
        "alias": "BIN-1D-CATL",
        "experiment": "P0 Dataset and Label Atlas",
        "cutoff_utc": str(CUTOFF_UTC),
        "max_feature_ts": str(MAX_FEATURE_TS),
        "holdout_read": HOLDOUT_READ,
        "asset_count": int(features["asset"].nunique()),
        "feature_rows": int(len(features)),
        "tradable_feature_rows": int(features["tradable_marker_p0"].sum()),
        "landmark_rows": int(len(landmarks)),
        "complete_entry_20d_landmarks": int(len(complete_entry)),
        "complete_continue_5d_landmarks": int(len(complete_continue)),
        "entry_success_rate_20d": float(complete_entry["label_entry_success_20d"].mean()) if len(complete_entry) else None,
        "continue_success_rate_5d": float(complete_continue["label_continue_success_5d"].mean()) if len(complete_continue) else None,
        "entry_ambiguous_count": int(complete_entry["label_entry_ambiguous_same_hour"].sum()) if len(complete_entry) else 0,
        "continue_ambiguous_count": int(complete_continue["label_continue_ambiguous_same_hour"].sum()) if len(complete_continue) else 0,
        "hype_max_feature_ts": str(hype_rows["ts"].max()) if not hype_rows.empty else None,
        "hype_rows_after_cutoff": int((hype_rows["ts"] >= CUTOFF_UTC).sum()) if not hype_rows.empty else 0,
    }
    if len(complete_entry):
        by_asset = complete_entry.groupby("asset").size().sort_values(ascending=False)
        by_year = complete_entry.assign(year=complete_entry["ts"].dt.year).groupby("year").size().sort_values(ascending=False)
        summary["top_asset_entry_label_share"] = float(by_asset.iloc[0] / len(complete_entry))
        summary["top_asset_entry_label_asset"] = str(by_asset.index[0])
        summary["top_year_entry_label_share"] = float(by_year.iloc[0] / len(complete_entry))
        summary["top_year_entry_label_year"] = int(by_year.index[0])
    else:
        summary["top_asset_entry_label_share"] = None
        summary["top_asset_entry_label_asset"] = None
        summary["top_year_entry_label_share"] = None
        summary["top_year_entry_label_year"] = None
    summary["final_verdict"] = p0_verdict(summary, features, landmarks)
    return summary


def p0_verdict(summary: dict[str, Any], features: pd.DataFrame, landmarks: pd.DataFrame) -> str:
    if summary["hype_rows_after_cutoff"] != 0:
        return "DATASET_INTEGRITY_FAILED"
    if features["asset"].nunique() < 100 or summary["complete_entry_20d_landmarks"] < 100_000:
        return "BLOCKED_DATA_ACCESS"
    if not bool(HOLDOUT_READ) and landmarks["future_path_complete_20d"].any() and landmarks["future_path_complete_5d"].any():
        return "DATASET_READY_FOR_MODELING_RESEARCH"
    return "DATASET_INTEGRITY_FAILED"


def grouped_rate(df: pd.DataFrame, group_cols: list[str], label_col: str) -> pd.DataFrame:
    good = df.loc[df[label_col].notna()].copy()
    return (
        good.groupby(group_cols, dropna=False)
        .agg(
            rows=(label_col, "size"),
            positive_rate=(label_col, "mean"),
            mean_entry_net_return=("label_entry_net_return", "mean"),
            mean_continue_net_return=("label_continue_net_return", "mean"),
        )
        .reset_index()
        .sort_values(group_cols)
    )


def label_autocorr(landmarks: pd.DataFrame, label_col: str) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    base = landmarks.loc[landmarks[label_col].notna(), ["asset", "side", "ts", label_col]].copy()
    base[label_col] = base[label_col].astype(float)
    for lag in (1, 3, 5, 10):
        pairs: list[pd.DataFrame] = []
        for _, g in base.groupby(["asset", "side"], sort=False):
            shifted = g[[label_col]].shift(lag).rename(columns={label_col: "lagged"})
            pair = pd.concat([g[[label_col]], shifted], axis=1).dropna()
            if len(pair):
                pairs.append(pair)
        if not pairs:
            out[f"lag_{lag}d"] = None
            continue
        both = pd.concat(pairs, ignore_index=True)
        out[f"lag_{lag}d"] = float(both[label_col].corr(both["lagged"])) if len(both) > 2 else None
    return out


def nonoverlap_sensitivity(landmarks: pd.DataFrame) -> dict[str, Any]:
    rows: list[pd.DataFrame] = []
    base = landmarks.loc[landmarks["future_path_complete_20d"].astype(bool)].copy()
    for _, group in base.groupby(["asset", "side"], sort=False):
        g = group.sort_values("entry_ts")
        selected = []
        next_allowed = pd.Timestamp.min.tz_localize("UTC")
        for _, row in g.iterrows():
            if pd.Timestamp(row["entry_ts"]) >= next_allowed:
                selected.append(row)
                next_allowed = pd.Timestamp(row["entry_ts"]) + pd.Timedelta(days=20)
        if selected:
            rows.append(pd.DataFrame(selected))
    if not rows:
        return {"rows": 0, "entry_success_rate_20d": None, "entry_net_return_mean": None}
    out = pd.concat(rows, ignore_index=True)
    return {
        "rows": int(len(out)),
        "entry_success_rate_20d": float(out["label_entry_success_20d"].mean()),
        "entry_net_return_mean": float(out["label_entry_net_return"].mean()),
    }


def compute_diagnostics(features: pd.DataFrame, landmarks: pd.DataFrame) -> dict[str, Any]:
    complete_entry = landmarks.loc[landmarks["future_path_complete_20d"].astype(bool)].copy()
    complete_continue = landmarks.loc[landmarks["future_path_complete_5d"].astype(bool)].copy()
    complete_entry["year"] = complete_entry["ts"].dt.year
    complete_continue["year"] = complete_continue["ts"].dt.year

    probe_cols = [
        "probe_raw_ma7_cross_dir",
        "probe_raw_ma14_cross_dir",
        "probe_raw_ma30_cross_dir",
        "probe_raw_ma60_cross_dir",
        "probe_20d_range_breakout_dir",
        "probe_same_side_ma7_no_cross",
        "probe_same_side_ma30_no_cross",
        "probe_ma7_ma30_direction_aligned",
        "probe_ma7_cross_ma30_opposite",
    ]
    probes: dict[str, dict[str, Any]] = {}
    for col in probe_cols:
        stats = []
        for value, group in complete_entry.groupby(col, dropna=False):
            stats.append(
                {
                    "probe_value": str(value),
                    "rows": int(len(group)),
                    "entry_success_rate_20d": float(group["label_entry_success_20d"].mean()),
                    "entry_net_return_mean": float(group["label_entry_net_return"].mean()),
                    "continue_success_rate_5d": float(
                        complete_continue.loc[complete_continue.index.intersection(group.index), "label_continue_success_5d"].mean()
                    )
                    if len(complete_continue.index.intersection(group.index))
                    else None,
                }
            )
        probes[col] = {"stats": stats}

    feature_missing = (
        features.isna()
        .mean()
        .sort_values(ascending=False)
        .head(30)
        .rename("missing_rate")
        .reset_index()
        .rename(columns={"index": "field"})
        .to_dict("records")
    )
    feature_extremes = {}
    numeric = features.select_dtypes(include=[np.number]).columns
    for col in numeric:
        values = features[col].replace([np.inf, -np.inf], np.nan).dropna()
        if len(values) and values.abs().quantile(0.999) > 100:
            feature_extremes[col] = {
                "p001": float(values.quantile(0.001)),
                "p999": float(values.quantile(0.999)),
            }

    return {
        "asset_year_side_entry": grouped_rate(complete_entry, ["asset", "year", "side"], "label_entry_success_20d").to_dict("records"),
        "year_side_entry": grouped_rate(complete_entry, ["year", "side"], "label_entry_success_20d").to_dict("records"),
        "asset_month_counts": complete_entry.groupby(["asset", "calendar_month"]).size().rename("rows").reset_index().to_dict("records"),
        "asset_quarter_counts": complete_entry.groupby(["asset", "calendar_quarter"]).size().rename("rows").reset_index().to_dict("records"),
        "probe_stats": probes,
        "entry_autocorr": label_autocorr(complete_entry, "label_entry_success_20d"),
        "continue_autocorr": label_autocorr(complete_continue, "label_continue_success_5d"),
        "nonoverlap_20d": nonoverlap_sensitivity(landmarks),
        "feature_missing_top30": feature_missing,
        "feature_extreme_fields": feature_extremes,
        "entry_net_distribution": complete_entry["label_entry_net_return"].describe(percentiles=[0.01, 0.05, 0.5, 0.95, 0.99]).to_dict(),
        "continue_net_distribution": complete_continue["label_continue_net_return"].describe(percentiles=[0.01, 0.05, 0.5, 0.95, 0.99]).to_dict(),
        "mfe_mae_distribution": {
            "mfe_20d": complete_entry["future_mfe_atr_20d"].describe(percentiles=[0.05, 0.5, 0.95]).to_dict(),
            "mae_20d": complete_entry["future_mae_atr_20d"].describe(percentiles=[0.05, 0.5, 0.95]).to_dict(),
            "mfe_5d": complete_continue["future_mfe_atr_5d"].describe(percentiles=[0.05, 0.5, 0.95]).to_dict(),
            "mae_5d": complete_continue["future_mae_atr_5d"].describe(percentiles=[0.05, 0.5, 0.95]).to_dict(),
        },
    }


def fmt_pct(value: Any, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "n/a"
    return f"{100.0 * float(value):.{digits}f}%"


def fmt_num(value: Any, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "n/a"
    return f"{float(value):.{digits}f}"


def write_data_quality_report(features: pd.DataFrame, summary: dict[str, Any], diagnostics: dict[str, Any], paths: Paths) -> None:
    asset_counts = features.groupby("asset").size().sort_values(ascending=False)
    daily_universe = features.groupby("ts")["tradable_marker_p0"].sum()
    funding_missing_rate = float(features["funding_missing"].mean()) if "funding_missing" in features else math.nan
    lines = [
        "# BIN-1D-CATL-P0 数据质量报告",
        "",
        f"- Family：`{summary['family']}`（`{summary['alias']}`）",
        f"- 数据截断：`{summary['cutoff_utc']}`；最后特征日：`{summary['max_feature_ts']}`",
        "- 价格源：normalized Binance perp `15m` closed K；四根 `15m` 聚合闭合 `1h`，24 根连续 `1h` 聚合完整 UTC 日。",
        f"- `holdout_read={str(HOLDOUT_READ).lower()}`；HYPE 最大特征日：`{summary['hype_max_feature_ts']}`。",
        f"- P0 裁决：`{summary['final_verdict']}`；状态保持 `explore / diagnostic-only / not promoted / not live-ready`。",
        "",
        "## 覆盖",
        "",
        f"- 历史资产数：`{summary['asset_count']}`。",
        f"- Asset-Day 行数：`{summary['feature_rows']}`；P0 tradable marker 行数：`{summary['tradable_feature_rows']}`。",
        f"- 每日 point-in-time universe：最小 `{int(daily_universe.min())}`，中位 `{int(daily_universe.median())}`，最大 `{int(daily_universe.max())}`。",
        f"- 单资产行数：最小 `{int(asset_counts.min())}`，中位 `{int(asset_counts.median())}`，最大 `{int(asset_counts.max())}`。",
        "",
        "## 质量边界",
        "",
        f"- funding 缺失日比例：`{fmt_pct(funding_missing_rate)}`；缺失时净收益只用已存在 funding 记录，报告保留缺失边界。",
        "- OI 历史点位覆盖本轮未确认，不纳入 P0 特征。",
        "- `complete_day` 只接受 24 根完整 `1h`；每根 `1h` 必须由 4 根闭合连续 `15m` 聚合。",
        "- 资产资格在标签计算前冻结为 `tradable_marker_p0`，没有按标签表现修改流动性、上市年龄或连续性条件。",
        "",
        "## 特征缺失率 Top 30",
        "",
        "| 字段 | 缺失率 |",
        "| --- | ---: |",
    ]
    for row in diagnostics["feature_missing_top30"]:
        lines.append(f"| `{row['field']}` | {fmt_pct(row['missing_rate'])} |")
    lines.extend([
        "",
        "## 隔离检查",
        "",
        f"- HYPE cutoff 之后特征行：`{summary['hype_rows_after_cutoff']}`。",
        "- 未读取 HYPE validation 预测、validation 交易路径或后 81 日验证产物。",
        "- 所有标签窗口不足的 landmark 均标记为 incomplete，不向 `2026-05-31` 之后补未来路径。",
    ])
    paths.data_quality_report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_label_report(summary: dict[str, Any], diagnostics: dict[str, Any], paths: Paths) -> None:
    lines = [
        "# BIN-1D-CATL-P0 标签分布诊断报告",
        "",
        "本报告只描述数据集和 future path 标签质量，不训练模型、不挑参数、不形成策略。",
        "",
        "## 总览",
        "",
        f"- 资产数：`{summary['asset_count']}`；Asset-Day：`{summary['feature_rows']}`；Directional Landmark：`{summary['landmark_rows']}`。",
        f"- 完整 20 日 entry 标签：`{summary['complete_entry_20d_landmarks']}`；成功率：`{fmt_pct(summary['entry_success_rate_20d'])}`。",
        f"- 完整 5 日 continuation 标签：`{summary['complete_continue_5d_landmarks']}`；成功率：`{fmt_pct(summary['continue_success_rate_5d'])}`。",
        f"- Entry 同小时冲突：`{summary['entry_ambiguous_count']}`；Continuation 同小时冲突：`{summary['continue_ambiguous_count']}`。",
        f"- 20 日 entry 标签最大资产占比：`{summary['top_asset_entry_label_asset']}` / `{fmt_pct(summary['top_asset_entry_label_share'])}`。",
        f"- 20 日 entry 标签最大年份占比：`{summary['top_year_entry_label_year']}` / `{fmt_pct(summary['top_year_entry_label_share'])}`。",
        "",
        "## 重叠样本",
        "",
        "每天一个 landmark 会让未来路径高度重叠，行数不等于独立样本数。后续模型必须按时间切分、purge 和 embargo，禁止随机拆分。",
        "",
        f"- Entry 标签自相关：`{json.dumps(diagnostics['entry_autocorr'], ensure_ascii=False)}`。",
        f"- Continuation 标签自相关：`{json.dumps(diagnostics['continue_autocorr'], ensure_ascii=False)}`。",
        f"- 严格非重叠 20 日敏感性：行数 `{diagnostics['nonoverlap_20d']['rows']}`，entry 成功率 `{fmt_pct(diagnostics['nonoverlap_20d']['entry_success_rate_20d'])}`，净收益均值 `{fmt_num(diagnostics['nonoverlap_20d']['entry_net_return_mean'])}`。",
        "",
        "## 预注册探针",
        "",
        "| 探针 | 取值 | 行数 | entry 成功率 | entry 净收益均值 | continuation 成功率 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    probe_order = [
        "probe_raw_ma7_cross_dir",
        "probe_raw_ma14_cross_dir",
        "probe_raw_ma30_cross_dir",
        "probe_raw_ma60_cross_dir",
        "probe_20d_range_breakout_dir",
        "probe_same_side_ma7_no_cross",
        "probe_same_side_ma30_no_cross",
        "probe_ma7_ma30_direction_aligned",
        "probe_ma7_cross_ma30_opposite",
    ]
    for probe in probe_order:
        for row in diagnostics["probe_stats"][probe]["stats"]:
            lines.append(
                f"| `{probe}` | `{row['probe_value']}` | {row['rows']} | "
                f"{fmt_pct(row['entry_success_rate_20d'])} | {fmt_num(row['entry_net_return_mean'])} | "
                f"{fmt_pct(row['continue_success_rate_5d'])} |"
            )
    lines.extend([
        "",
        "MA7/MA30 在本轮只是探针：表中的差异只能说明标签分布与状态有关，不能在 P0 选择赢家或宣布交易规则。",
        "",
        "## 成本后分布",
        "",
        f"- Entry net return 分布：`{json.dumps(diagnostics['entry_net_distribution'], ensure_ascii=False, default=str)}`。",
        f"- Continuation net return 分布：`{json.dumps(diagnostics['continue_net_distribution'], ensure_ascii=False, default=str)}`。",
        f"- MFE/MAE 分布：`{json.dumps(diagnostics['mfe_mae_distribution'], ensure_ascii=False, default=str)}`。",
        "",
        "## P0 裁决",
        "",
        f"`{summary['final_verdict']}`。研究线保持 `explore / diagnostic-only / not promoted / not live-ready`。",
    ])
    paths.label_report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_field_dictionary(paths: Paths) -> None:
    lines = [
        "# BIN-1D-CATL-P0 标签定义和字段字典",
        "",
        "## 表",
        "",
        "- `p0_asset_day_feature_panel/`：每个 asset-day 一行，只含评估日收盘前可知字段。",
        "- `p0_directional_landmark_panel/`：每个 asset-day-side 一行，future/outcome/label 字段描述下一 UTC open 后路径。",
        "",
        "## 关键字段",
        "",
        "| 字段 | 含义 | 时点 |",
        "| --- | --- | --- |",
        "| `asset` | Binance perp symbol，如 `BTC/USDT:USDT` | 身份字段 |",
        "| `ts` | 评估 UTC 日开盘时间；特征在该日收盘后可知 | causal |",
        "| `feature_known_at` | 下一 UTC 日 `00:00`，即该日特征最早可用时点 | causal |",
        "| `next_entry_ts` / `entry_ts` | 下一 UTC 日开盘，标签路径起点 | label anchor |",
        "| `tradable_marker_p0` | 冻结资格标记：完整日、上市 60 日、30 日连续性和流动性 | causal |",
        "| `atr_anchor` | 评估日及以前 `ATR14`，作为屏障单位 | causal |",
        "| `future_first_favorable_*atr_hours` | 30 日内顺向屏障首次触及小时；未触及为空 | future primitive |",
        "| `future_first_adverse_*atr_hours` | 30 日内反向屏障首次触及小时；未触及为空 | future primitive |",
        "| `label_entry_success_20d` | 20 日内先触及 `+2 ATR` 且未先触及 `-1 ATR` | label |",
        "| `label_continue_success_5d` | 5 日内先触及 `+1 ATR` 且未先触及 `-0.75 ATR` | label |",
        "| `label_*_success_*_optimistic` | 同小时冲突按有利先触发的敏感性字段 | label sensitivity |",
        "| `label_*_net_return` | 1x、双边 fee/slippage、实际 funding 后的独立事件收益 | outcome |",
        "| `future_mfe_atr_*d` / `future_mae_atr_*d` | 指定 horizon 内顺向/反向最大路径，ATR 单位 | outcome |",
        "| `calendar_month` / `calendar_quarter` | purge/walk-forward 分组辅助字段 | causal grouping |",
        "",
        "## 主标签",
        "",
        "Entry label：下一 UTC open 进入，20 日内先顺向 `+2 ATR`，且此前没有触及反向 `-1 ATR`。",
        "",
        "Continuation label：下一 UTC open 继续暴露，5 日内先新增顺向 `+1 ATR`，且此前没有触及反向 `-0.75 ATR`。",
    ]
    paths.field_dictionary.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_html_payload(features: pd.DataFrame, landmarks: pd.DataFrame, *, sample_n: int = 96) -> dict[str, Any]:
    rng = random.Random(RANDOM_SEED)
    complete = landmarks.loc[
        landmarks["future_path_complete_20d"].astype(bool)
        & landmarks["label_entry_result"].isin(["favorable_first", "adverse_first", "timeout", "ambiguous_same_hour"])
    ].copy()
    strata = []
    for side in ("long", "short"):
        for success in (True, False):
            part = complete.loc[(complete["side"] == side) & (complete["label_entry_success_20d"] == success)]
            if not part.empty:
                strata.extend(part.sample(min(sample_n // 4, len(part)), random_state=RANDOM_SEED).to_dict("records"))
    if len(strata) < sample_n and len(complete):
        extra = complete.sample(min(sample_n - len(strata), len(complete)), random_state=RANDOM_SEED + 1).to_dict("records")
        strata.extend(extra)
    rng.shuffle(strata)
    events = strata[:sample_n]

    by_asset = {asset: g.sort_values("ts") for asset, g in features.groupby("asset", sort=False)}
    payload_events = []
    for idx, event in enumerate(events):
        g = by_asset[event["asset"]]
        start = pd.Timestamp(event["ts"]) - pd.Timedelta(days=20)
        end = pd.Timestamp(event["entry_ts"]) + pd.Timedelta(days=30)
        window = g.loc[(g["ts"] >= start) & (g["ts"] <= end)]
        candles = [
            {
                "ts": str(row["ts"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "ma7": None if pd.isna(row["ma7"]) else float(row["ma7"]),
                "ma30": None if pd.isna(row["ma30"]) else float(row["ma30"]),
            }
            for row in window.to_dict("records")
        ]
        payload_events.append(
            {
                "id": idx,
                "asset": event["asset"],
                "side": event["side"],
                "ts": str(event["ts"]),
                "entry_ts": str(event["entry_ts"]),
                "entry_ref": float(event["entry_ref"]),
                "label_entry_result": event["label_entry_result"],
                "label_entry_success_20d": bool(event["label_entry_success_20d"]),
                "label_continue_result": event["label_continue_result"],
                "label_continue_success_5d": bool(event["label_continue_success_5d"]),
                "mfe20": None if pd.isna(event["future_mfe_atr_20d"]) else float(event["future_mfe_atr_20d"]),
                "mae20": None if pd.isna(event["future_mae_atr_20d"]) else float(event["future_mae_atr_20d"]),
                "hit_hours": None if pd.isna(event["label_entry_hours_to_hit"]) else float(event["label_entry_hours_to_hit"]),
                "candles": candles,
            }
        )
    return {
        "notice": "Label quality atlas only. Not a trading strategy. No frozen validation period after 2026-05-31 is used.",
        "events": payload_events,
    }


def write_html_atlas(features: pd.DataFrame, landmarks: pd.DataFrame, paths: Paths) -> None:
    payload = make_html_payload(features, landmarks)
    payload_json = json.dumps(payload, ensure_ascii=False)
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BIN-1D-CATL-P0 Label Quality Atlas</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #101214; color: #e9ecef; }}
    header {{ padding: 18px 24px; border-bottom: 1px solid #2b3035; }}
    main {{ display: grid; grid-template-columns: 320px 1fr; min-height: calc(100vh - 82px); }}
    aside {{ border-right: 1px solid #2b3035; overflow: auto; padding: 14px; }}
    button {{ width: 100%; text-align: left; margin: 4px 0; padding: 8px; background: #171a1d; color: #e9ecef; border: 1px solid #343a40; border-radius: 6px; cursor: pointer; }}
    button.active {{ border-color: #74c0fc; background: #10243a; }}
    #chartWrap {{ padding: 18px; }}
    svg {{ width: 100%; height: 620px; background: #0b0d0f; border: 1px solid #2b3035; border-radius: 8px; touch-action: none; }}
    .meta {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; }}
    .card {{ background: #171a1d; border: 1px solid #2b3035; border-radius: 8px; padding: 10px; }}
    .small {{ color: #adb5bd; font-size: 12px; }}
    .up {{ color: #69db7c; }}
    .down {{ color: #ff8787; }}
  </style>
</head>
<body>
<header>
  <h2 style="margin:0">BIN-1D-CATL-P0 Label Quality Atlas</h2>
  <div class="small">自包含 HTML；只用于标签质量检查；不是交易策略；未使用 2026-05-31 之后冻结验证期。</div>
</header>
<main>
  <aside>
    <button onclick="resetZoom()">复位缩放</button>
    <div id="eventList"></div>
  </aside>
  <section id="chartWrap">
    <div id="meta" class="meta"></div>
    <svg id="chart" viewBox="0 0 1100 620"></svg>
  </section>
</main>
<script id="payload" type="application/json">{html.escape(payload_json)}</script>
<script>
const data = JSON.parse(document.getElementById('payload').textContent);
let current = 0;
let zoom = {{start: 0, end: 1}};
const svg = document.getElementById('chart');
function $(id) {{ return document.getElementById(id); }}
function renderList() {{
  const list = $('eventList');
  list.innerHTML = '';
  data.events.forEach((e, i) => {{
    const b = document.createElement('button');
    b.className = i === current ? 'active' : '';
    b.innerHTML = `<b>${{e.asset}}</b><br><span class="small">${{e.side}} | ${{e.ts.slice(0,10)}} | ${{e.label_entry_result}}</span>`;
    b.onclick = () => {{ current = i; zoom = {{start:0,end:1}}; draw(); renderList(); }};
    list.appendChild(b);
  }});
}}
function resetZoom() {{ zoom = {{start:0,end:1}}; draw(); }}
function draw() {{
  const e = data.events[current];
  const c = e.candles || [];
  $('meta').innerHTML = [
    ['资产/方向', `${{e.asset}} / ${{e.side}}`],
    ['Entry Label', `${{e.label_entry_result}} / success=${{e.label_entry_success_20d}}`],
    ['Continue Label', `${{e.label_continue_result}} / success=${{e.label_continue_success_5d}}`],
    ['MFE/MAE 20d', `${{e.mfe20?.toFixed(2)}} / ${{e.mae20?.toFixed(2)}} ATR`],
  ].map(x => `<div class="card"><div class="small">${{x[0]}}</div><div>${{x[1]}}</div></div>`).join('');
  svg.innerHTML = '';
  if (!c.length) return;
  const n = c.length, left = Math.floor(zoom.start*n), right = Math.max(left+5, Math.ceil(zoom.end*n));
  const view = c.slice(left, right);
  const w = 1100, h = 620, pad = 50;
  const lows = view.map(d => d.low), highs = view.map(d => d.high);
  const ymin = Math.min(...lows), ymax = Math.max(...highs), yr = ymax-ymin || 1;
  const x = i => pad + i * ((w - 2*pad) / Math.max(1, view.length-1));
  const y = v => h - pad - (v - ymin) / yr * (h - 2*pad);
  function line(points, color, width=1.5) {{
    const p = points.map((d,i) => d == null ? null : `${{x(i)}},${{y(d)}}`).filter(Boolean).join(' ');
    svg.insertAdjacentHTML('beforeend', `<polyline points="${{p}}" fill="none" stroke="${{color}}" stroke-width="${{width}}"/>`);
  }}
  for (let i=0;i<view.length;i++) {{
    const d=view[i], xx=x(i), open=y(d.open), close=y(d.close), hi=y(d.high), lo=y(d.low);
    const color=d.close>=d.open?'#69db7c':'#ff8787';
    svg.insertAdjacentHTML('beforeend', `<line x1="${{xx}}" x2="${{xx}}" y1="${{hi}}" y2="${{lo}}" stroke="${{color}}"/>`);
    svg.insertAdjacentHTML('beforeend', `<rect x="${{xx-3}}" y="${{Math.min(open,close)}}" width="6" height="${{Math.max(1,Math.abs(close-open))}}" fill="${{color}}"/>`);
    if (d.ts.slice(0,10) === e.ts.slice(0,10)) svg.insertAdjacentHTML('beforeend', `<line x1="${{xx}}" x2="${{xx}}" y1="20" y2="${{h-pad}}" stroke="#ffd43b" stroke-dasharray="4 4"/>`);
    if (d.ts.slice(0,10) === e.entry_ts.slice(0,10)) svg.insertAdjacentHTML('beforeend', `<line x1="${{xx}}" x2="${{xx}}" y1="20" y2="${{h-pad}}" stroke="#74c0fc" stroke-dasharray="4 4"/>`);
  }}
  line(view.map(d=>d.ma7), '#74c0fc', 1.2);
  line(view.map(d=>d.ma30), '#ffa94d', 1.2);
  svg.insertAdjacentHTML('beforeend', `<text x="60" y="28" fill="#ffd43b">评估日</text><text x="130" y="28" fill="#74c0fc">下一开盘</text><text x="220" y="28" fill="#74c0fc">MA7</text><text x="270" y="28" fill="#ffa94d">MA30</text>`);
}}
let dragX = null;
svg.addEventListener('pointerdown', ev => dragX = ev.clientX);
svg.addEventListener('pointerup', ev => {{
  if (dragX == null) return;
  const dx = ev.clientX - dragX; dragX = null;
  const span = zoom.end - zoom.start;
  const shift = -dx / 900 * span;
  zoom.start = Math.max(0, Math.min(1-span, zoom.start + shift));
  zoom.end = zoom.start + span; draw();
}});
svg.addEventListener('wheel', ev => {{
  ev.preventDefault();
  const mid = (zoom.start + zoom.end)/2, span = (zoom.end - zoom.start) * (ev.deltaY > 0 ? 1.2 : 0.8);
  const clamped = Math.max(0.08, Math.min(1, span));
  zoom.start = Math.max(0, mid - clamped/2); zoom.end = Math.min(1, zoom.start + clamped);
  zoom.start = Math.max(0, zoom.end - clamped); draw();
}});
renderList(); draw();
</script>
</body>
</html>
"""
    paths.html_atlas.write_text(html_text, encoding="utf-8")


def build_manifest(paths: Paths, summary: dict[str, Any]) -> dict[str, Any]:
    include_paths = [
        SPEC_PATH,
        Path(__file__),
        paths.hourly_parquet,
        paths.field_dictionary,
        paths.data_quality_report,
        paths.label_report,
        paths.summary_json,
        paths.html_atlas,
    ]
    partition_files = sorted(paths.feature_panel_dir.rglob("*.parquet")) + sorted(paths.landmark_panel_dir.rglob("*.parquet"))
    entries = []
    for path in include_paths + partition_files:
        entries.append(
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "family": summary["family"],
        "alias": summary["alias"],
        "experiment": summary["experiment"],
        "created_utc": pd.Timestamp.now("UTC").isoformat(),
        "cutoff_utc": str(CUTOFF_UTC),
        "holdout_read": HOLDOUT_READ,
        "final_verdict": summary["final_verdict"],
        "source_price_15m_dir": str(PRICE_15M_DIR.relative_to(ROOT)),
        "source_funding_dir": str(FUNDING_DIR.relative_to(ROOT)),
        "artifacts": entries,
        "directory_digests": {
            "feature_panel": hashlib.sha256(
                "".join(e["sha256"] for e in entries if "p0_asset_day_feature_panel/" in e["path"]).encode()
            ).hexdigest(),
            "landmark_panel": hashlib.sha256(
                "".join(e["sha256"] for e in entries if "p0_directional_landmark_panel/" in e["path"]).encode()
            ).hexdigest(),
        },
    }
    paths.manifest_json.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def write_summary(summary: dict[str, Any], diagnostics: dict[str, Any], paths: Paths) -> None:
    payload = {"summary": summary, "diagnostics": diagnostics}
    paths.summary_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def validate_outputs(features: pd.DataFrame, landmarks: pd.DataFrame, manifest: dict[str, Any]) -> None:
    assert HOLDOUT_READ is False
    assert features["ts"].max() <= MAX_FEATURE_TS
    hype = features.loc[features["asset"] == "HYPE/USDT:USDT"]
    if not hype.empty:
        assert hype["ts"].max() <= MAX_FEATURE_TS
    assert (features["hours_in_day"] == 24).all()
    assert (features["min_15m_per_hour"] == 4).all()
    assert (landmarks["entry_ts"] == landmarks["ts"] + pd.Timedelta(days=1)).all()
    feature_future_cols = [c for c in features.columns if c.startswith(("label_", "future_", "outcome_"))]
    assert not feature_future_cols, feature_future_cols
    paths = [item["path"] for item in manifest["artifacts"]]
    assert not any("validation" in path.lower() for path in paths)
    assert Path(manifest["source_price_15m_dir"]).as_posix().startswith("data/normalized/")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Regenerate intermediate hourly parquet")
    parser.add_argument("--max-assets", type=int, default=None, help="Debug only: limit assets")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = p0_paths()
    ensure_dirs(paths)
    build_hourly_from_15m(paths, force=args.force)
    con = connect_work_db(paths)
    daily = load_daily_from_hourly(con)
    funding = load_funding_daily()
    features = add_asset_features(daily, funding)
    if args.max_assets is not None:
        keep_assets = list(features["asset"].drop_duplicates())[: args.max_assets]
        features = features.loc[features["asset"].isin(keep_assets)].copy()
    landmarks = build_landmarks(features, con, funding, max_assets=args.max_assets)
    con.close()

    write_partitioned(features, paths.feature_panel_dir, side_partition=False)
    write_partitioned(landmarks, paths.landmark_panel_dir, side_partition=True)
    diagnostics = compute_diagnostics(features, landmarks)
    summary = summarize(features, landmarks)
    write_summary(summary, diagnostics, paths)
    write_field_dictionary(paths)
    write_data_quality_report(features, summary, diagnostics, paths)
    write_label_report(summary, diagnostics, paths)
    write_html_atlas(features, landmarks, paths)
    manifest = build_manifest(paths, summary)
    validate_outputs(features, landmarks, manifest)
    if paths.work_db.exists():
        paths.work_db.unlink()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
