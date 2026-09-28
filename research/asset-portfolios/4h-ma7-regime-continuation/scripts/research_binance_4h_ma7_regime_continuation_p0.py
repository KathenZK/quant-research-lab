#!/usr/bin/env python3
"""BIN-4H-MA7-RC P0 unconditional continuation kill test.

The script intentionally has no parameter search surface. It validates the
pre-outcome frozen config and input manifest before reading forward outcomes.
"""

# FAIL-FAST：本脚本是冻结历史复现入口，读取 legacy 1h glob。
# 复现请用 P0R（catalog 路径）：
#   scripts/research_binance_4h_ma7_regime_continuation_p0r_data.py
#   dataset_id = binance.perp.ohlcv.4h.from_15m.v1 / binance.perp.ohlcv.1h.from_15m.v1
# 不要把本文件当新研究取数模板。

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

import duckdb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/4h-ma7-regime-continuation"
CONFIG_PATH = FAMILY_DIR / "configs/binance-4h-ma7-regime-continuation-p0.json"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAGNOSTIC_DIR = FAMILY_DIR / "diagnostics"
REPORT_PATH = DIAGNOSTIC_DIR / "binance-4h-ma7-regime-continuation-p0-results-2026-09-02.md"

EXPECTED_CONFIG_SHA256 = "eb62108271cf1d22992fb53c0c1a7438d605581d96cb079d75b0579143c84642"
EXPECTED_MANIFEST_SHA256 = "c11074a7a064db42c0a53214e0756f106388c14e683376bc0fcdfb56d94ffd7e"
RUN_DATE = "2026-09-02"
SEED = 20260902
BOOTSTRAP_ITERATIONS = 1000
HORIZONS = (1, 3, 6, 12, 18, 30)
MA_PERIODS = (5, 7, 10, 42)
PRIMARY_MA = 7
ATR_PERIOD = 20
MAX_FUTURE_BARS = 30
FEE_PER_FILL = 0.001
SLIP_4BPS_PER_FILL = 0.0004
SLIP_8BPS_PER_FILL = 0.0008
ROUND_TRIP_4BPS = 2.0 * (FEE_PER_FILL + SLIP_4BPS_PER_FILL)
ROUND_TRIP_8BPS = 2.0 * (FEE_PER_FILL + SLIP_8BPS_PER_FILL)
MIN_LISTING_DAYS = 30
MIN_ADV_USDT = 10_000_000.0
MIN_COVERAGE = 0.95
TRADING_POOL_SIZE = 120
BARS_PER_DAY = 6

STABLE_BASES = {
    "AEUR",
    "AUD",
    "BFUSD",
    "BRL",
    "BUSD",
    "DAI",
    "EUR",
    "FDUSD",
    "GBP",
    "SUSD",
    "TUSD",
    "USD1",
    "USDC",
    "USDE",
    "USDP",
    "XUSD",
}
INDEX_BASES = {"BLUEBIRD", "DOTECO", "FOOTBALL"}
US_STOCK_LIKE_BASES = {
    "AAPL",
    "AMZN",
    "COIN",
    "CRCL",
    "GOOGL",
    "HOOD",
    "META",
    "MSFT",
    "MSTR",
    "NVDA",
    "PLTR",
    "TSLA",
}
EXCLUDED_BASES = STABLE_BASES | INDEX_BASES | US_STOCK_LIKE_BASES

OUTPUTS = {
    "data_audit": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0_data_audit_{RUN_DATE}.json",
    "universe": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0_universe_summary_{RUN_DATE}.csv",
    "events": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0_events_{RUN_DATE}.parquet",
    "metrics": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0_metrics_{RUN_DATE}.csv",
    "first_hit": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0_first_hit_{RUN_DATE}.csv",
    "horizon": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0_horizon_returns_{RUN_DATE}.csv",
    "survival": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0_survival_{RUN_DATE}.csv",
    "yearly": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0_yearly_{RUN_DATE}.csv",
    "concentration": ARTIFACT_DIR
    / f"binance_4h_ma7_rc_p0_symbol_concentration_{RUN_DATE}.csv",
    "phase": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0_phase_{RUN_DATE}.csv",
    "controls": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0_controls_{RUN_DATE}.csv",
    "recent": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0_recent_slices_{RUN_DATE}.csv",
    "summary": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0_summary_{RUN_DATE}.json",
}


@dataclass(slots=True)
class FundingLookup:
    timestamps: np.ndarray
    rates: np.ndarray
    by_second: dict[pd.Timestamp, float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run frozen BIN-4H-MA7-RC P0.")
    parser.add_argument("--run", action="store_true", help="Acknowledge outcome read.")
    parser.add_argument("--force", action="store_true", help="Replace existing outputs.")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sidecar(path: Path) -> str:
    digest = sha256_file(path)
    rel = path.relative_to(ROOT).as_posix()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {rel}\n", encoding="utf-8"
    )
    return digest


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_frozen_config() -> dict[str, Any]:
    actual = sha256_file(CONFIG_PATH)
    if actual != EXPECTED_CONFIG_SHA256:
        raise RuntimeError(
            f"frozen config hash mismatch: {actual} != {EXPECTED_CONFIG_SHA256}"
        )
    config = load_json(CONFIG_PATH)
    if config["study_id"] != "BIN-4H-MA7-RC-P0":
        raise RuntimeError("unexpected study_id")
    manifest_path = ROOT / config["data"]["dataset_manifest"]
    if sha256_file(manifest_path) != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("pre-outcome dataset manifest hash mismatch")
    manifest = load_json(manifest_path)
    if manifest.get("outcome_read") is not False:
        raise RuntimeError("dataset manifest is not marked pre-outcome")
    return config


def prepare_outputs(force: bool) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    DIAGNOSTIC_DIR.mkdir(parents=True, exist_ok=True)
    existing = [path for path in [*OUTPUTS.values(), REPORT_PATH] if path.exists()]
    if existing and not force:
        names = ", ".join(rel(path) for path in existing[:3])
        raise RuntimeError(f"P0 outputs already exist; pass --force. Existing: {names}")


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET enable_progress_bar=false")
    return con


def root_globs(config: dict[str, Any], key: str) -> list[str]:
    return [str(ROOT / item) for item in config["data"][key]]


def source_priority_case(column: str, priority: Sequence[str]) -> str:
    clauses = " ".join(
        f"WHEN {column} = '{source}' THEN {index}"
        for index, source in enumerate(priority)
    )
    return f"CASE {clauses} ELSE 999 END"


def _iso(value: Any) -> str | None:
    if pd.isna(value):
        return None
    return pd.Timestamp(value).tz_convert("UTC").isoformat()


def load_selected_ohlcv(config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    cutoff = pd.Timestamp(config["data"]["cutoff_exclusive_utc"])
    globs = root_globs(config, "ohlcv_1h_globs")
    priority = config["data"]["source_priority"]
    con = connect()
    raw_query = """
        SELECT
            count(*) AS raw_rows,
            count(DISTINCT symbol) AS raw_symbols,
            min(ts) AS min_ts,
            max(ts) AS max_ts,
            count(*) FILTER (
                WHERE symbol IS NULL OR ts IS NULL OR exchange IS NULL
                   OR market_type IS NULL OR open IS NULL OR high IS NULL
                   OR low IS NULL OR close IS NULL OR volume IS NULL
                   OR quote_volume IS NULL OR trade_count IS NULL
                   OR vwap IS NULL OR is_closed IS NULL OR source IS NULL
            ) AS critical_null_rows,
            count(*) FILTER (WHERE NOT is_closed) AS open_bar_rows,
            count(*) FILTER (
                WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0
                   OR volume < 0 OR quote_volume < 0 OR trade_count < 0
                   OR high < greatest(open, close, low)
                   OR low > least(open, close, high)
            ) AS invalid_ohlc_rows,
            count(*) FILTER (
                WHERE exchange != 'binance' OR market_type != 'perp'
                   OR (timeframe IS NOT NULL AND timeframe != '1h')
            ) AS identity_mismatch_rows
        FROM read_parquet(?, union_by_name=true)
        WHERE ts < ?
    """
    raw = con.execute(raw_query, [globs, cutoff.to_pydatetime()]).fetch_df().iloc[0]
    selected_query = f"""
        SELECT
            ts,
            exchange,
            symbol,
            market_type,
            coalesce(base_asset, replace(symbol, '/USDT:USDT', '')) AS base_asset,
            coalesce(quote_asset, 'USDT') AS quote_asset,
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
            taker_buy_volume,
            taker_buy_quote_volume
        FROM read_parquet(?, union_by_name=true)
        WHERE ts < ?
        QUALIFY row_number() OVER (
            PARTITION BY symbol, ts
            ORDER BY {source_priority_case("source", priority)}, source
        ) = 1
        ORDER BY symbol, ts
    """
    frame = con.execute(selected_query, [globs, cutoff.to_pydatetime()]).fetch_df()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    duplicate_selected = int(frame.duplicated(["symbol", "ts"]).sum())
    by_source = (
        frame.groupby("source", dropna=False)
        .agg(row_count=("symbol", "size"), symbols=("symbol", "nunique"))
        .reset_index()
        .to_dict("records")
    )
    audit = {
        "ohlcv_raw_rows_before_cutoff": int(raw["raw_rows"]),
        "ohlcv_selected_rows_before_cutoff": int(len(frame)),
        "ohlcv_raw_symbols_before_cutoff": int(raw["raw_symbols"]),
        "ohlcv_selected_symbols_before_cutoff": int(frame["symbol"].nunique()),
        "ohlcv_min_ts_utc": _iso(raw["min_ts"]),
        "ohlcv_max_ts_utc": _iso(raw["max_ts"]),
        "ohlcv_critical_null_rows": int(raw["critical_null_rows"]),
        "ohlcv_open_bar_rows": int(raw["open_bar_rows"]),
        "ohlcv_invalid_ohlc_rows": int(raw["invalid_ohlc_rows"]),
        "ohlcv_identity_mismatch_rows": int(raw["identity_mismatch_rows"]),
        "ohlcv_duplicate_selected_symbol_ts_rows": duplicate_selected,
        "ohlcv_selected_by_source": [
            {"source": str(row["source"]), "row_count": int(row["row_count"]), "symbols": int(row["symbols"])}
            for row in by_source
        ],
    }
    blockers = [
        key
        for key in (
            "ohlcv_critical_null_rows",
            "ohlcv_open_bar_rows",
            "ohlcv_invalid_ohlc_rows",
            "ohlcv_identity_mismatch_rows",
            "ohlcv_duplicate_selected_symbol_ts_rows",
        )
        if audit[key] != 0
    ]
    if blockers:
        raise RuntimeError(f"OHLCV data-quality blockers: {blockers}")
    return frame, audit


def load_selected_funding(config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    cutoff = pd.Timestamp(config["data"]["cutoff_exclusive_utc"])
    globs = root_globs(config, "funding_rate_globs")
    priority = config["data"]["funding_source_priority"]
    con = connect()
    raw_query = """
        SELECT
            count(*) AS raw_rows,
            count(DISTINCT symbol) AS raw_symbols,
            min(ts) AS min_ts,
            max(ts) AS max_ts,
            count(*) FILTER (
                WHERE symbol IS NULL OR ts IS NULL OR exchange IS NULL
                   OR market_type IS NULL OR funding_rate IS NULL OR source IS NULL
            ) AS critical_null_rows,
            count(*) FILTER (WHERE exchange != 'binance' OR market_type != 'perp') AS identity_mismatch_rows
        FROM read_parquet(?, union_by_name=true)
        WHERE ts <= ?
    """
    raw = con.execute(raw_query, [globs, cutoff.to_pydatetime()]).fetch_df().iloc[0]
    selected_query = f"""
        WITH nominal_rows AS (
            SELECT
                date_trunc('second', ts) AS nominal_ts,
                *
            FROM read_parquet(?, union_by_name=true)
            WHERE ts <= ?
        )
        SELECT
            nominal_ts AS ts,
            exchange,
            symbol,
            market_type,
            coalesce(base_asset, replace(symbol, '/USDT:USDT', '')) AS base_asset,
            coalesce(quote_asset, 'USDT') AS quote_asset,
            funding_rate,
            mark_price,
            source
        FROM nominal_rows
        QUALIFY row_number() OVER (
            PARTITION BY symbol, nominal_ts
            ORDER BY {source_priority_case("source", priority)}, source, ts DESC
        ) = 1
        ORDER BY symbol, ts
    """
    frame = con.execute(selected_query, [globs, cutoff.to_pydatetime()]).fetch_df()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True).dt.round("s")
    duplicate_selected = int(frame.duplicated(["symbol", "ts"]).sum())
    audit = {
        "funding_raw_rows_before_or_at_cutoff": int(raw["raw_rows"]),
        "funding_selected_rows_before_or_at_cutoff": int(len(frame)),
        "funding_raw_symbols_before_or_at_cutoff": int(raw["raw_symbols"]),
        "funding_selected_symbols_before_or_at_cutoff": int(frame["symbol"].nunique()),
        "funding_min_ts_utc": _iso(raw["min_ts"]),
        "funding_max_ts_utc": _iso(raw["max_ts"]),
        "funding_critical_null_rows": int(raw["critical_null_rows"]),
        "funding_identity_mismatch_rows": int(raw["identity_mismatch_rows"]),
        "funding_duplicate_selected_symbol_ts_rows": duplicate_selected,
    }
    blockers = [
        key
        for key in (
            "funding_critical_null_rows",
            "funding_identity_mismatch_rows",
            "funding_duplicate_selected_symbol_ts_rows",
        )
        if audit[key] != 0
    ]
    if blockers:
        raise RuntimeError(f"funding data-quality blockers: {blockers}")
    return frame, audit


def aggregate_4h(ohlcv: pd.DataFrame, phase_hour: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    frames: list[pd.DataFrame] = []
    audit_rows: list[dict[str, Any]] = []
    offset = pd.Timedelta(hours=phase_hour)
    for symbol, group in ohlcv.groupby("symbol", sort=True):
        ordered = group.sort_values("ts").copy()
        ordered["component_legal_ohlc"] = (
            ordered["open"].gt(0)
            & ordered["high"].gt(0)
            & ordered["low"].gt(0)
            & ordered["close"].gt(0)
            & ordered["high"].ge(ordered[["open", "close", "low"]].max(axis=1))
            & ordered["low"].le(ordered[["open", "close", "high"]].min(axis=1))
        )
        ordered["bar_start"] = (ordered["ts"] - offset).dt.floor("4h") + offset
        grouped = ordered.groupby("bar_start", sort=True)
        agg = grouped.agg(
            symbol=("symbol", "first"),
            base_asset=("base_asset", "first"),
            quote_asset=("quote_asset", "first"),
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            quote_volume=("quote_volume", "sum"),
            trade_count=("trade_count", "sum"),
            taker_buy_volume=("taker_buy_volume", "sum"),
            taker_buy_quote_volume=("taker_buy_quote_volume", "sum"),
            bars_1h=("ts", "size"),
            first_1h_ts=("ts", "min"),
            last_1h_ts=("ts", "max"),
            all_closed=("is_closed", "all"),
            all_components_legal=("component_legal_ohlc", "all"),
        ).reset_index()
        agg["phase_hour"] = phase_hour
        expected_last = agg["bar_start"] + pd.Timedelta(hours=3)
        legal_ohlc = (
            agg["open"].gt(0)
            & agg["high"].gt(0)
            & agg["low"].gt(0)
            & agg["close"].gt(0)
            & agg["high"].ge(agg[["open", "close", "low"]].max(axis=1))
            & agg["low"].le(agg[["open", "close", "high"]].min(axis=1))
        )
        complete = (
            agg["bars_1h"].eq(4)
            & agg["first_1h_ts"].eq(agg["bar_start"])
            & agg["last_1h_ts"].eq(expected_last)
            & agg["all_closed"].fillna(False)
            & agg["all_components_legal"].fillna(False)
            & legal_ohlc
        )
        audit_rows.append(
            {
                "symbol": symbol,
                "phase_hour": phase_hour,
                "raw_4h_groups": int(len(agg)),
                "complete_4h_bars": int(complete.sum()),
                "incomplete_or_illegal_4h_groups": int((~complete).sum()),
                "first_complete_4h_utc": _iso(agg.loc[complete, "bar_start"].min()),
                "last_complete_4h_utc": _iso(agg.loc[complete, "bar_start"].max()),
            }
        )
        valid = agg.loc[complete].copy()
        valid = valid.rename(columns={"bar_start": "ts"})
        frames.append(valid)
    result = pd.concat(frames, ignore_index=True).sort_values(["symbol", "ts"])
    if result.duplicated(["symbol", "ts", "phase_hour"]).any():
        raise RuntimeError(f"duplicate aggregated 4h bars for phase {phase_hour}")
    audit = {
        "phase_hour": phase_hour,
        "symbols": int(result["symbol"].nunique()),
        "complete_4h_bars": int(len(result)),
        "incomplete_or_illegal_4h_groups": int(
            sum(row["incomplete_or_illegal_4h_groups"] for row in audit_rows)
        ),
        "first_complete_4h_utc": _iso(result["ts"].min()),
        "last_complete_4h_utc": _iso(result["ts"].max()),
        "symbol_rows": audit_rows,
    }
    return result.reset_index(drop=True), audit


def rolling_causal_percentile(values: Sequence[float], min_periods: int = 20) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    out = np.full(len(arr), np.nan, dtype=float)
    seen: list[float] = []
    for idx, value in enumerate(arr):
        if np.isfinite(value):
            seen.append(float(value))
        if len(seen) >= min_periods and np.isfinite(value):
            current = float(value)
            out[idx] = sum(item <= current for item in seen) / len(seen)
    return out


def assign_quintile_from_percentile(values: Sequence[float]) -> pd.Series:
    arr = np.asarray(values, dtype=float)
    out = np.full(len(arr), np.nan, dtype=float)
    valid = np.isfinite(arr)
    out[valid] = np.minimum(5, np.floor(arr[valid] * 5.0).astype(int) + 1)
    return pd.Series(out, dtype="Int64")


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    outputs: list[pd.DataFrame] = []
    for (symbol, phase), group in frame.groupby(["symbol", "phase_hour"], sort=True):
        block = group.sort_values("ts").copy()
        prior_ts = block["ts"].shift(1)
        block["new_block"] = prior_ts.isna() | (
            (block["ts"] - prior_ts) != pd.Timedelta(hours=4)
        )
        block["block_id"] = block["new_block"].cumsum().astype(int)
        parts: list[pd.DataFrame] = []
        for _, segment in block.groupby("block_id", sort=False):
            part = segment.copy()
            close = part["close"].astype(float)
            prev_close = close.shift(1)
            tr = pd.concat(
                [
                    part["high"].astype(float) - part["low"].astype(float),
                    (part["high"].astype(float) - prev_close).abs(),
                    (part["low"].astype(float) - prev_close).abs(),
                ],
                axis=1,
            ).max(axis=1)
            part["tr"] = tr
            part["atr20"] = tr.rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean()
            part["atr_scale"] = part["atr20"].shift(1)
            for period in MA_PERIODS:
                part[f"sma{period}"] = close.rolling(period, min_periods=period).mean()
            part["atr_causal_pct"] = rolling_causal_percentile(part["atr_scale"])
            part["atr_quintile"] = assign_quintile_from_percentile(part["atr_causal_pct"]).to_numpy()
            parts.append(part)
        out = pd.concat(parts, ignore_index=True)
        out["symbol"] = symbol
        out["phase_hour"] = phase
        outputs.append(out)
    return pd.concat(outputs, ignore_index=True).sort_values(["phase_hour", "symbol", "ts"])


def build_universe(primary_4h: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = (
        primary_4h.groupby(["symbol", "base_asset", primary_4h["ts"].dt.normalize()], sort=True)
        .agg(quote_volume=("quote_volume", "sum"), bars=("ts", "size"))
        .reset_index()
        .rename(columns={"ts": "day"})
    )
    frames: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    archive_end = daily["day"].max()
    for symbol, group in daily.groupby("symbol", sort=True):
        base_asset = str(group["base_asset"].iloc[0])
        group = group.sort_values("day").set_index("day")
        full = group.reindex(pd.date_range(group.index.min(), group.index.max(), freq="D", tz="UTC"))
        full["symbol"] = symbol
        full["base_asset"] = base_asset
        full["quote_volume"] = full["quote_volume"].fillna(0.0)
        full["bars"] = full["bars"].fillna(0)
        adv = full["quote_volume"].rolling(30, min_periods=30).mean().shift(1)
        coverage = full["bars"].rolling(30, min_periods=30).sum().shift(1) / (
            30.0 * BARS_PER_DAY
        )
        listed_days = np.arange(len(full))
        eligible = (
            (listed_days >= MIN_LISTING_DAYS)
            & (adv.to_numpy() >= MIN_ADV_USDT)
            & (coverage.to_numpy() >= MIN_COVERAGE)
            & (~pd.Series(base_asset, index=full.index).isin(EXCLUDED_BASES).to_numpy())
        )
        table = pd.DataFrame(
            {
                "symbol": symbol,
                "base_asset": base_asset,
                "day": full.index,
                "adv_30d": adv.to_numpy(dtype=float),
                "coverage_30d": coverage.to_numpy(dtype=float),
                "listing_age_days": listed_days,
                "eligible": eligible,
            }
        )
        frames.append(table)
        summary_rows.append(
            {
                "symbol": symbol,
                "base_asset": base_asset,
                "first_day": group.index.min(),
                "last_day": group.index.max(),
                "complete_4h_bars": int(group["bars"].sum()),
                "eligible_days": int(table["eligible"].sum()),
                "excluded_base": base_asset in EXCLUDED_BASES,
                "left_truncated": bool(group.index.min() <= primary_4h["ts"].min().normalize()),
                "right_open": bool(group.index.max() >= archive_end),
            }
        )
    eligibility = pd.concat(frames, ignore_index=True)
    eligible = eligibility.loc[eligibility["eligible"]].copy()
    eligible["adv_rank"] = eligible.groupby("day")["adv_30d"].rank(
        method="first", ascending=False
    )
    eligible["symbols_in_eligible_day"] = eligible.groupby("day")["symbol"].transform("size")
    eligible["in_trading_pool"] = eligible["adv_rank"].le(TRADING_POOL_SIZE)
    eligible["pit_adv_quintile"] = (
        np.floor((eligible["adv_rank"].to_numpy(dtype=float) - 1.0) * 5.0 / eligible["symbols_in_eligible_day"].to_numpy(dtype=float))
        + 1
    ).clip(1, 5).astype(int)
    eligible["pit_adv_top20"] = eligible["adv_rank"].le(20)
    eligibility = eligibility.merge(
        eligible[["symbol", "day", "adv_rank", "symbols_in_eligible_day", "in_trading_pool", "pit_adv_quintile", "pit_adv_top20"]],
        on=["symbol", "day"],
        how="left",
    )
    eligibility["in_trading_pool"] = eligibility["in_trading_pool"].fillna(False)
    eligibility["pit_adv_top20"] = eligibility["pit_adv_top20"].fillna(False)
    summary = pd.DataFrame(summary_rows)
    return eligibility, summary


def attach_universe(panel: pd.DataFrame, eligibility: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    out["event_day"] = (out["ts"] + pd.Timedelta(hours=4)).dt.normalize()
    cols = [
        "symbol",
        "day",
        "adv_30d",
        "coverage_30d",
        "listing_age_days",
        "eligible",
        "adv_rank",
        "symbols_in_eligible_day",
        "in_trading_pool",
        "pit_adv_quintile",
        "pit_adv_top20",
    ]
    out = out.merge(
        eligibility[cols],
        left_on=["symbol", "event_day"],
        right_on=["symbol", "day"],
        how="left",
        validate="many_to_one",
    )
    out["eligible"] = out["eligible"].fillna(False)
    out["in_trading_pool"] = out["in_trading_pool"].fillna(False)
    out["pit_adv_top20"] = out["pit_adv_top20"].fillna(False)
    return out.drop(columns=["day"])


def build_funding_lookup(funding: pd.DataFrame) -> dict[str, FundingLookup]:
    lookup: dict[str, FundingLookup] = {}
    for symbol, group in funding.groupby("symbol", sort=True):
        ordered = group.sort_values("ts").drop_duplicates("ts", keep="last")
        ts = pd.to_datetime(ordered["ts"], utc=True).dt.round("s")
        rates = ordered["funding_rate"].to_numpy(dtype=float)
        lookup[symbol] = FundingLookup(
            timestamps=ts.to_numpy(dtype="datetime64[ns]"),
            rates=rates,
            by_second={pd.Timestamp(t).tz_localize("UTC"): float(r) for t, r in zip(ts.dt.tz_localize(None), rates, strict=True)},
        )
    return lookup


def expected_funding_times(entry_ts: pd.Timestamp, exit_ts: pd.Timestamp) -> list[pd.Timestamp]:
    start = entry_ts.floor("8h")
    if start <= entry_ts:
        start += pd.Timedelta(hours=8)
    if start > exit_ts:
        return []
    return list(pd.date_range(start, exit_ts.floor("s"), freq="8h", tz="UTC"))


def funding_cost_for_window(
    lookup: dict[str, FundingLookup],
    symbol: str,
    entry_ts: pd.Timestamp,
    exit_ts: pd.Timestamp,
    side: int,
) -> tuple[float, bool, int, int]:
    expected = expected_funding_times(entry_ts, exit_ts)
    if not expected:
        return 0.0, True, 0, 0
    table = lookup.get(symbol)
    if table is None:
        return math.nan, False, len(expected), len(expected)
    rates = []
    missing = 0
    for ts in expected:
        rate = table.by_second.get(ts)
        if rate is None:
            missing += 1
        else:
            rates.append(rate)
    if missing:
        return math.nan, False, len(expected), missing
    # Positive funding is a cost to longs and a benefit to shorts.
    return float(side * np.sum(rates)), True, len(expected), 0


def signal_close_ts(ts: pd.Series) -> pd.Series:
    return ts + pd.Timedelta(hours=4)


def build_event_candidates(panel: pd.DataFrame, ma_period: int) -> pd.DataFrame:
    grouped = panel.groupby(["symbol", "phase_hour", "block_id"], sort=False)
    prev_close = grouped["close"].shift(1)
    prev_sma = grouped[f"sma{ma_period}"].shift(1)
    next_ts = grouped["ts"].shift(-1)
    next_open = grouped["open"].shift(-1)
    base_mask = (
        panel["in_trading_pool"].fillna(False)
        & np.isfinite(panel[f"sma{ma_period}"])
        & np.isfinite(prev_sma)
        & np.isfinite(panel["atr_scale"])
        & panel["atr_scale"].gt(0)
        & next_ts.eq(panel["ts"] + pd.Timedelta(hours=4))
        & np.isfinite(next_open)
    )
    rows: list[pd.DataFrame] = []
    for direction, side in (("long", 1), ("short", -1)):
        if side == 1:
            trigger = prev_close.le(prev_sma) & panel["close"].gt(panel[f"sma{ma_period}"])
        else:
            trigger = prev_close.ge(prev_sma) & panel["close"].lt(panel[f"sma{ma_period}"])
        selected = panel.loc[base_mask & trigger].copy()
        if selected.empty:
            continue
        selected["ma_period"] = ma_period
        selected["direction"] = direction
        selected["side"] = side
        selected["signal_ts"] = signal_close_ts(selected["ts"])
        selected["entry_ts"] = next_ts.loc[selected.index].to_numpy()
        selected["entry_price"] = next_open.loc[selected.index].to_numpy(dtype=float)
        selected["cross_event"] = True
        rows.append(selected)
    if not rows:
        return pd.DataFrame()
    events = pd.concat(rows, ignore_index=True)
    events["event_id"] = (
        "phase"
        + events["phase_hour"].astype(str)
        + "|MA"
        + events["ma_period"].astype(str)
        + "|"
        + events["direction"].astype(str)
        + "|"
        + events["symbol"].astype(str)
        + "|"
        + events["signal_ts"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    if events["event_id"].duplicated().any():
        raise RuntimeError("duplicate event ids")
    return events.sort_values(["phase_hour", "ma_period", "signal_ts", "symbol"]).reset_index(drop=True)


def build_non_cross_controls(panel: pd.DataFrame) -> pd.DataFrame:
    primary = panel.loc[panel["phase_hour"].eq(0)].copy()
    grouped = primary.groupby(["symbol", "phase_hour", "block_id"], sort=False)
    prev_close = grouped["close"].shift(1)
    prev_sma = grouped["sma7"].shift(1)
    next_ts = grouped["ts"].shift(-1)
    next_open = grouped["open"].shift(-1)
    long_cross = prev_close.le(prev_sma) & primary["close"].gt(primary["sma7"])
    short_cross = prev_close.ge(prev_sma) & primary["close"].lt(primary["sma7"])
    base_mask = (
        primary["in_trading_pool"].fillna(False)
        & np.isfinite(primary["sma7"])
        & np.isfinite(prev_sma)
        & np.isfinite(primary["atr_scale"])
        & primary["atr_scale"].gt(0)
        & primary["atr_quintile"].notna()
        & next_ts.eq(primary["ts"] + pd.Timedelta(hours=4))
        & np.isfinite(next_open)
    )
    rows: list[pd.DataFrame] = []
    for direction, side, cross in (
        ("long", 1, long_cross),
        ("short", -1, short_cross),
    ):
        side_mask = primary["close"].gt(primary["sma7"]) if side == 1 else primary["close"].lt(primary["sma7"])
        selected = primary.loc[base_mask & side_mask & (~cross)].copy()
        if selected.empty:
            continue
        selected["ma_period"] = 7
        selected["direction"] = direction
        selected["side"] = side
        selected["signal_ts"] = signal_close_ts(selected["ts"])
        selected["entry_ts"] = next_ts.loc[selected.index].to_numpy()
        selected["entry_price"] = next_open.loc[selected.index].to_numpy(dtype=float)
        selected["cross_event"] = False
        selected["event_id"] = (
            "control|"
            + selected["direction"].astype(str)
            + "|"
            + selected["symbol"].astype(str)
            + "|"
            + selected["signal_ts"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        rows.append(selected)
    return pd.concat(rows, ignore_index=True).sort_values(["signal_ts", "symbol", "direction"])


def hourly_maps(ohlcv: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {symbol: group.sort_values("ts").set_index("ts") for symbol, group in ohlcv.groupby("symbol", sort=True)}


def panel_maps(panel: pd.DataFrame) -> dict[tuple[str, int], pd.DataFrame]:
    return {
        (symbol, int(phase)): group.sort_values("ts").set_index("ts")
        for (symbol, phase), group in panel.groupby(["symbol", "phase_hour"], sort=True)
    }


def datetime_index_ns(index: pd.DatetimeIndex) -> np.ndarray:
    return (
        pd.DatetimeIndex(index)
        .tz_convert("UTC")
        .tz_localize(None)
        .astype("datetime64[ns]")
        .astype(np.int64)
    )


def _directional_high_low(row: pd.Series, hourly: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    side = int(row["side"])
    if side == 1:
        favorable = hourly["high"].to_numpy(dtype=float) / float(row["entry_price"]) - 1.0
        adverse = hourly["low"].to_numpy(dtype=float) / float(row["entry_price"]) - 1.0
    else:
        favorable = 1.0 - hourly["low"].to_numpy(dtype=float) / float(row["entry_price"])
        adverse = 1.0 - hourly["high"].to_numpy(dtype=float) / float(row["entry_price"])
    return favorable, adverse


def enrich_outcomes(
    events: pd.DataFrame,
    hourly_by_symbol: dict[str, pd.DataFrame],
    fourh_by_symbol_phase: dict[tuple[str, int], pd.DataFrame],
    funding_lookup: dict[str, FundingLookup],
) -> pd.DataFrame:
    output = events.copy().reset_index(drop=True)
    hour_cache = {
        symbol: {
            "ts": datetime_index_ns(frame.index),
            "high": frame["high"].to_numpy(dtype=float),
            "low": frame["low"].to_numpy(dtype=float),
        }
        for symbol, frame in hourly_by_symbol.items()
    }
    fourh_cache = {
        key: {
            "ts": datetime_index_ns(frame.index),
            "open": frame["open"].to_numpy(dtype=float),
            "close": frame["close"].to_numpy(dtype=float),
            "sma7": frame["sma7"].to_numpy(dtype=float),
            "pos": {int(ts): idx for idx, ts in enumerate(datetime_index_ns(frame.index))},
        }
        for key, frame in fourh_by_symbol_phase.items()
    }
    labels: list[str] = []
    ambiguous: list[bool] = []
    first_hit_hours: list[float] = []
    recross_bars: list[float] = []
    survival_bars: list[float] = []
    for horizon in HORIZONS:
        for col in (
            f"gross_return_{horizon}",
            f"funding_cost_{horizon}",
            f"net_return_4bps_{horizon}",
            f"net_return_8bps_{horizon}",
            f"mfe_{horizon}",
            f"mae_{horizon}",
            f"mfe_bar_{horizon}",
            f"mae_bar_{horizon}",
        ):
            output[col] = np.nan
        output[f"funding_complete_{horizon}"] = False
        output[f"funding_events_expected_{horizon}"] = 0
        output[f"funding_events_missing_{horizon}"] = 0

    for idx, row in output.iterrows():
        symbol = str(row["symbol"])
        phase = int(row["phase_hour"])
        side = int(row["side"])
        entry_ts = pd.Timestamp(row["entry_ts"])
        signal_bar_ts = pd.Timestamp(row["ts"])
        entry_price = float(row["entry_price"])
        atr_scale = float(row["atr_scale"])
        hourly = hour_cache.get(symbol)
        fourh = fourh_cache.get((symbol, phase))
        if hourly is None or fourh is None:
            labels.append("incomplete_future")
            ambiguous.append(False)
            first_hit_hours.append(math.nan)
            recross_bars.append(math.nan)
            survival_bars.append(math.nan)
            continue

        first_hit_end = entry_ts + pd.Timedelta(hours=4 * MAX_FUTURE_BARS)
        entry_ns = int(entry_ts.value)
        first_hit_end_ns = int(first_hit_end.value)
        hour_ts = hourly["ts"]
        hour_start = int(np.searchsorted(hour_ts, entry_ns, side="left"))
        hour_end = int(np.searchsorted(hour_ts, first_hit_end_ns, side="left"))
        expected_hours = 4 * MAX_FUTURE_BARS
        window_ts = hour_ts[hour_start:hour_end]
        hourly_complete = (
            len(window_ts) == expected_hours
            and (len(window_ts) == 0 or int(window_ts[0]) == entry_ns)
            and (len(window_ts) <= 1 or bool(np.all(np.diff(window_ts) == 3_600_000_000_000)))
        )
        if not hourly_complete:
            labels.append("incomplete_future")
            ambiguous.append(False)
            first_hit_hours.append(math.nan)
        else:
            window_high = hourly["high"][hour_start:hour_end]
            window_low = hourly["low"][hour_start:hour_end]
            if side == 1:
                favorable_hit = window_high >= entry_price + 2.0 * atr_scale
                adverse_hit = window_low <= entry_price - 1.0 * atr_scale
            else:
                favorable_hit = window_low <= entry_price - 2.0 * atr_scale
                adverse_hit = window_high >= entry_price + 1.0 * atr_scale
            label = "neither"
            hit_hour = math.nan
            is_ambiguous = False
            for hour_idx, (fav, adv) in enumerate(zip(favorable_hit, adverse_hit, strict=True), start=1):
                if adv:
                    label = "adverse_first"
                    hit_hour = float(hour_idx)
                    is_ambiguous = bool(fav)
                    break
                if fav:
                    label = "favorable_first"
                    hit_hour = float(hour_idx)
                    break
            labels.append(label)
            ambiguous.append(is_ambiguous)
            first_hit_hours.append(hit_hour)

        signal_ns = int(signal_bar_ts.value)
        signal_pos = fourh["pos"].get(signal_ns)
        if signal_pos is None:
            recross_bars.append(math.nan)
            survival_bars.append(math.nan)
        else:
            end_pos = min(signal_pos + MAX_FUTURE_BARS, len(fourh["ts"]) - 1)
            future_slice = slice(signal_pos + 1, end_pos + 1)
            recross = math.nan
            survival = float(max(0, end_pos - signal_pos))
            if end_pos > signal_pos:
                if side == 1:
                    mask = fourh["close"][future_slice] <= fourh["sma7"][future_slice]
                else:
                    mask = fourh["close"][future_slice] >= fourh["sma7"][future_slice]
                if mask.any():
                    recross = float(np.flatnonzero(mask)[0] + 1)
                    survival = recross - 1.0
            recross_bars.append(recross)
            survival_bars.append(survival)

        for horizon in HORIZONS:
            exit_ts = entry_ts + pd.Timedelta(hours=4 * horizon)
            exit_ns = int(exit_ts.value)
            exit_pos = fourh["pos"].get(exit_ns)
            if exit_pos is not None:
                exit_open = float(fourh["open"][exit_pos])
                gross = side * (exit_open / entry_price - 1.0)
                fcost, complete, expected_count, missing_count = funding_cost_for_window(
                    funding_lookup, symbol, entry_ts, exit_ts, side
                )
                output.at[idx, f"gross_return_{horizon}"] = gross
                output.at[idx, f"funding_cost_{horizon}"] = fcost
                output.at[idx, f"funding_complete_{horizon}"] = complete
                output.at[idx, f"funding_events_expected_{horizon}"] = expected_count
                output.at[idx, f"funding_events_missing_{horizon}"] = missing_count
                if complete:
                    output.at[idx, f"net_return_4bps_{horizon}"] = gross - ROUND_TRIP_4BPS - fcost
                    output.at[idx, f"net_return_8bps_{horizon}"] = gross - ROUND_TRIP_8BPS - fcost

                horizon_end_ns = int(exit_ts.value)
                path_end = int(np.searchsorted(hour_ts, horizon_end_ns, side="left"))
                expected_path_hours = 4 * horizon
                path_ts = hour_ts[hour_start:path_end]
                path_complete = (
                    len(path_ts) == expected_path_hours
                    and (len(path_ts) == 0 or int(path_ts[0]) == entry_ns)
                    and (len(path_ts) <= 1 or bool(np.all(np.diff(path_ts) == 3_600_000_000_000)))
                )
                if path_complete:
                    if side == 1:
                        favorable = hourly["high"][hour_start:path_end] / entry_price - 1.0
                        adverse = hourly["low"][hour_start:path_end] / entry_price - 1.0
                    else:
                        favorable = 1.0 - hourly["low"][hour_start:path_end] / entry_price
                        adverse = 1.0 - hourly["high"][hour_start:path_end] / entry_price
                    output.at[idx, f"mfe_{horizon}"] = float(np.nanmax(favorable))
                    output.at[idx, f"mae_{horizon}"] = float(np.nanmin(adverse))
                    output.at[idx, f"mfe_bar_{horizon}"] = float(np.nanargmax(favorable) // 4 + 1)
                    output.at[idx, f"mae_bar_{horizon}"] = float(np.nanargmin(adverse) // 4 + 1)

    output["first_hit_label"] = labels
    output["same_1h_dual_hit_adverse_first"] = ambiguous
    output["first_hit_hour"] = first_hit_hours
    output["ma7_recross_bars"] = recross_bars
    output["same_side_survival_bars"] = survival_bars
    output["calendar_year"] = output["signal_ts"].dt.year.astype(int)
    output["utc_week"] = output["signal_ts"].dt.strftime("%G-W%V")
    return output


def weighted_mean(values: pd.Series, weights: pd.Series | None = None) -> float:
    valid = np.isfinite(values.to_numpy(dtype=float))
    if not valid.any():
        return math.nan
    arr = values.to_numpy(dtype=float)[valid]
    if weights is None:
        return float(np.mean(arr))
    w = weights.to_numpy(dtype=float)[valid]
    total = float(np.sum(w))
    if total <= 0:
        return math.nan
    return float(np.dot(arr, w) / total)


def summarize_distribution(values: pd.Series, weights: pd.Series | None = None) -> dict[str, float]:
    clean = values[np.isfinite(values.to_numpy(dtype=float))]
    if clean.empty:
        return {
            "mean": math.nan,
            "trimmed_mean_5pct": math.nan,
            "median": math.nan,
            "win_rate": math.nan,
            "top_1pct_contribution": math.nan,
            "top_5pct_contribution": math.nan,
        }
    arr = clean.to_numpy(dtype=float)
    sorted_arr = np.sort(arr)
    trim = int(math.floor(len(sorted_arr) * 0.05))
    trimmed = sorted_arr[trim : len(sorted_arr) - trim] if len(sorted_arr) - 2 * trim > 0 else sorted_arr
    total = float(np.sum(arr))
    positive = np.sort(arr[arr > 0])[::-1]
    def contribution(pct: float) -> float:
        if total <= 0 or len(positive) == 0:
            return math.nan
        n = max(1, int(math.ceil(len(arr) * pct)))
        return float(np.sum(positive[:n]) / total)
    return {
        "mean": weighted_mean(values, weights),
        "trimmed_mean_5pct": float(np.mean(trimmed)),
        "median": float(np.median(arr)),
        "win_rate": float(np.mean(arr > 0)),
        "top_1pct_contribution": contribution(0.01),
        "top_5pct_contribution": contribution(0.05),
    }


def cluster_se(values: pd.Series, symbols: pd.Series, weeks: pd.Series) -> dict[str, Any]:
    arr = values.to_numpy(dtype=float)
    valid = np.isfinite(arr)
    arr = arr[valid]
    if len(arr) < 2:
        return {"cluster_se": math.nan, "t_stat": math.nan, "p_value": math.nan}
    resid = arr - float(np.mean(arr))
    def variance(labels: pd.Series) -> tuple[float, int]:
        codes, uniques = pd.factorize(labels.loc[valid], sort=False)
        groups = len(uniques)
        if groups < 2:
            return math.nan, groups
        sums = np.bincount(codes, weights=resid)
        return (groups / (groups - 1.0)) * float(np.dot(sums, sums)) / len(arr) ** 2, groups
    v_symbol, n_symbol = variance(symbols)
    v_week, n_week = variance(weeks)
    obs = len(arr) / (len(arr) - 1.0) * float(np.dot(resid, resid)) / len(arr) ** 2
    combined = v_symbol + v_week - obs if np.isfinite(v_symbol) and np.isfinite(v_week) else math.nan
    if not np.isfinite(combined) or combined <= 0:
        combined = max(v for v in (v_symbol, v_week) if np.isfinite(v)) if any(np.isfinite(v) for v in (v_symbol, v_week)) else math.nan
    se = math.sqrt(combined) if np.isfinite(combined) and combined >= 0 else math.nan
    t_stat = float(np.mean(arr) / se) if se and np.isfinite(se) else math.nan
    p_value = math.erfc(abs(t_stat) / math.sqrt(2.0)) if np.isfinite(t_stat) else math.nan
    return {
        "cluster_se": se,
        "t_stat": t_stat,
        "p_value": p_value,
        "symbol_clusters": n_symbol,
        "week_clusters": n_week,
    }


def benjamini_hochberg(values: pd.Series) -> pd.Series:
    arr = values.to_numpy(dtype=float)
    out = np.full(len(arr), np.nan)
    valid = np.flatnonzero(np.isfinite(arr))
    if len(valid) == 0:
        return pd.Series(out, index=values.index)
    order = valid[np.argsort(arr[valid])]
    adjusted = arr[order] * len(order) / np.arange(1, len(order) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    out[order] = np.minimum(adjusted, 1.0)
    return pd.Series(out, index=values.index)


def bootstrap_diff(
    event: pd.DataFrame,
    control: pd.DataFrame,
    column: str,
    rng: np.random.Generator,
    *,
    event_weights: pd.Series | None = None,
    control_weights: pd.Series | None = None,
) -> dict[str, float]:
    event_valid = event.loc[np.isfinite(event[column].to_numpy(dtype=float))].copy()
    control_valid = control.loc[np.isfinite(control[column].to_numpy(dtype=float))].copy()
    if event_valid.empty or control_valid.empty:
        return {"diff": math.nan, "ci_low": math.nan, "ci_high": math.nan, "p_value": math.nan}

    def block_sums(frame: pd.DataFrame, weights: pd.Series | None) -> tuple[np.ndarray, np.ndarray]:
        local = frame[["symbol", "utc_week", column]].copy()
        local["_w"] = (
            weights.loc[frame.index].to_numpy(dtype=float)
            if weights is not None
            else np.ones(len(frame), dtype=float)
        )
        local["_xw"] = local[column].to_numpy(dtype=float) * local["_w"].to_numpy(dtype=float)
        grouped = local.groupby(["symbol", "utc_week"], sort=False).agg(
            xw=("_xw", "sum"), w=("_w", "sum")
        )
        return grouped["xw"].to_numpy(dtype=float), grouped["w"].to_numpy(dtype=float)

    e_xw, e_w = block_sums(event_valid, event_weights)
    c_xw, c_w = block_sums(control_valid, control_weights)
    if len(e_xw) == 0 or len(c_xw) == 0:
        return {"diff": math.nan, "ci_low": math.nan, "ci_high": math.nan, "p_value": math.nan}
    diffs = np.empty(BOOTSTRAP_ITERATIONS, dtype=float)
    for idx in range(BOOTSTRAP_ITERATIONS):
        e_idx = rng.integers(0, len(e_xw), size=len(e_xw))
        c_idx = rng.integers(0, len(c_xw), size=len(c_xw))
        e_mean = float(e_xw[e_idx].sum() / e_w[e_idx].sum())
        c_mean = float(c_xw[c_idx].sum() / c_w[c_idx].sum())
        diffs[idx] = e_mean - c_mean
    observed = weighted_mean(event_valid[column], event_weights.loc[event_valid.index] if event_weights is not None else None) - weighted_mean(
        control_valid[column], control_weights.loc[control_valid.index] if control_weights is not None else None
    )
    p_value = 2.0 * min(float(np.mean(diffs <= 0.0)), float(np.mean(diffs >= 0.0)))
    return {
        "diff": observed,
        "ci_low": float(np.quantile(diffs, 0.025)),
        "ci_high": float(np.quantile(diffs, 0.975)),
        "p_value": min(p_value, 1.0),
    }


def apply_control_weights(events: pd.DataFrame, controls: pd.DataFrame) -> pd.DataFrame:
    controls = controls.copy()
    strata = ["symbol", "calendar_year", "direction", "atr_quintile"]
    event_counts = events.groupby(strata, dropna=False).size().rename("event_count")
    control_counts = controls.groupby(strata, dropna=False).size().rename("control_count")
    weights = event_counts.to_frame().join(control_counts, how="left").fillna(0)
    weights["control_weight"] = np.where(
        weights["control_count"].gt(0),
        weights["event_count"] / weights["control_count"],
        np.nan,
    )
    controls = controls.merge(
        weights["control_weight"].reset_index(),
        on=strata,
        how="left",
        validate="many_to_one",
    )
    controls["control_weight"] = controls["control_weight"].fillna(0.0)
    controls["control_stratum_has_event"] = controls["control_weight"].gt(0)
    return controls


def build_first_hit_stats(events: pd.DataFrame, controls: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    primary = events.loc[events["phase_hour"].eq(0) & events["ma_period"].eq(7)].copy()
    primary["favorable_success"] = primary["first_hit_label"].eq("favorable_first").astype(float)
    controls = controls.copy()
    controls["favorable_success"] = controls["first_hit_label"].eq("favorable_first").astype(float)
    for direction in ("long", "short"):
        event_side = primary.loc[primary["direction"].eq(direction) & primary["first_hit_label"].ne("incomplete_future")]
        control_side = controls.loc[
            controls["direction"].eq(direction)
            & controls["first_hit_label"].ne("incomplete_future")
            & controls["control_stratum_has_event"]
        ]
        diff = bootstrap_diff(
            event_side,
            control_side,
            "favorable_success",
            rng,
            control_weights=control_side["control_weight"],
        )
        rows.append(
            {
                "ma_period": 7,
                "phase_hour": 0,
                "direction": direction,
                "event_count": int(len(event_side)),
                "control_count": int(len(control_side)),
                "event_favorable_rate": weighted_mean(event_side["favorable_success"]),
                "control_favorable_rate": weighted_mean(control_side["favorable_success"], control_side["control_weight"]),
                "diff": diff["diff"],
                "ci_low": diff["ci_low"],
                "ci_high": diff["ci_high"],
                "p_value": diff["p_value"],
                "event_adverse_rate": float(event_side["first_hit_label"].eq("adverse_first").mean()) if len(event_side) else math.nan,
                "event_neither_rate": float(event_side["first_hit_label"].eq("neither").mean()) if len(event_side) else math.nan,
                "incomplete_future_events": int(primary.loc[primary["direction"].eq(direction), "first_hit_label"].eq("incomplete_future").sum()),
                "same_1h_dual_hit_events": int(event_side["same_1h_dual_hit_adverse_first"].sum()),
            }
        )
    result = pd.DataFrame(rows)
    result["q_value_bh"] = benjamini_hochberg(result["p_value"])
    return result


def build_horizon_stats(events: pd.DataFrame, controls: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    primary = events.loc[events["phase_hour"].eq(0) & events["ma_period"].eq(7)]
    controls_valid = controls.loc[controls["control_stratum_has_event"]]
    for direction in ("long", "short"):
        event_side = primary.loc[primary["direction"].eq(direction)]
        control_side = controls_valid.loc[controls_valid["direction"].eq(direction)]
        for horizon in HORIZONS:
            for column, cost_case in (
                (f"gross_return_{horizon}", "gross"),
                (f"net_return_4bps_{horizon}", "fee_plus_4bps_funding_full_net"),
                (f"net_return_8bps_{horizon}", "fee_plus_8bps_funding_full_net"),
            ):
                diff = bootstrap_diff(
                    event_side,
                    control_side,
                    column,
                    rng,
                    control_weights=control_side["control_weight"],
                )
                stats = summarize_distribution(event_side[column])
                cluster = cluster_se(event_side[column], event_side["symbol"], event_side["utc_week"])
                rows.append(
                    {
                        "ma_period": 7,
                        "phase_hour": 0,
                        "direction": direction,
                        "horizon_4h_bars": horizon,
                        "cost_case": cost_case,
                        "event_count": int(np.isfinite(event_side[column].to_numpy(dtype=float)).sum()),
                        "control_count": int(np.isfinite(control_side[column].to_numpy(dtype=float)).sum()),
                        "event_mean": stats["mean"],
                        "event_trimmed_mean_5pct": stats["trimmed_mean_5pct"],
                        "event_median": stats["median"],
                        "event_win_rate": stats["win_rate"],
                        "event_top_1pct_contribution": stats["top_1pct_contribution"],
                        "event_top_5pct_contribution": stats["top_5pct_contribution"],
                        "control_mean": weighted_mean(control_side[column], control_side["control_weight"]),
                        "incremental_diff": diff["diff"],
                        "ci_low": diff["ci_low"],
                        "ci_high": diff["ci_high"],
                        "p_value": diff["p_value"],
                        **cluster,
                    }
                )
    result = pd.DataFrame(rows)
    result["q_value_bh"] = result.groupby(["direction", "horizon_4h_bars"], group_keys=False)["p_value"].transform(benjamini_hochberg)
    return result


def build_survival_stats(events: pd.DataFrame, controls: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    primary = events.loc[events["phase_hour"].eq(0) & events["ma_period"].eq(7)]
    controls_valid = controls.loc[controls["control_stratum_has_event"]]
    for direction in ("long", "short"):
        event_side = primary.loc[primary["direction"].eq(direction)]
        control_side = controls_valid.loc[controls_valid["direction"].eq(direction)]
        for column in ("same_side_survival_bars", "mfe_30", "mae_30"):
            diff = bootstrap_diff(
                event_side,
                control_side,
                column,
                rng,
                control_weights=control_side["control_weight"],
            )
            rows.append(
                {
                    "direction": direction,
                    "metric": column,
                    "event_count": int(np.isfinite(event_side[column].to_numpy(dtype=float)).sum()),
                    "control_count": int(np.isfinite(control_side[column].to_numpy(dtype=float)).sum()),
                    "event_mean": weighted_mean(event_side[column]),
                    "event_median": float(event_side[column].median()),
                    "control_mean": weighted_mean(control_side[column], control_side["control_weight"]),
                    "incremental_diff": diff["diff"],
                    "ci_low": diff["ci_low"],
                    "ci_high": diff["ci_high"],
                    "p_value": diff["p_value"],
                }
            )
    result = pd.DataFrame(rows)
    result["q_value_bh"] = result.groupby("metric", group_keys=False)["p_value"].transform(benjamini_hochberg)
    return result


def summarize_by_year(events: pd.DataFrame) -> pd.DataFrame:
    primary = events.loc[events["phase_hour"].eq(0) & events["ma_period"].eq(7)]
    rows = []
    for (direction, year), group in primary.groupby(["direction", "calendar_year"], sort=True):
        rows.append(
            {
                "direction": direction,
                "calendar_year": int(year),
                "events": int(len(group)),
                "first_hit_favorable_rate": float(group["first_hit_label"].eq("favorable_first").mean()),
                "gross_return_30_mean": weighted_mean(group["gross_return_30"]),
                "net_return_4bps_30_mean": weighted_mean(group["net_return_4bps_30"]),
                "net_return_8bps_30_mean": weighted_mean(group["net_return_8bps_30"]),
                "funding_complete_30_rate": float(group["funding_complete_30"].mean()),
            }
        )
    return pd.DataFrame(rows)


def concentration_rows(events: pd.DataFrame) -> pd.DataFrame:
    primary = events.loc[events["phase_hour"].eq(0) & events["ma_period"].eq(7)]
    rows: list[dict[str, Any]] = []
    for direction, group in primary.groupby("direction", sort=True):
        values = group["net_return_4bps_30"].dropna()
        total = float(values.sum())
        by_symbol = group.groupby("symbol")["net_return_4bps_30"].sum().sort_values(ascending=False)
        by_year = group.groupby("calendar_year")["net_return_4bps_30"].sum().sort_values(ascending=False)
        max_symbol = by_symbol.index[0] if len(by_symbol) else None
        max_year = int(by_year.index[0]) if len(by_year) else None
        def share(x: float) -> float:
            return float(x / total) if total > 0 else math.nan
        base = {
            "direction": direction,
            "total_net_return_30_sum": total,
            "mean_net_return_30": weighted_mean(group["net_return_4bps_30"]),
            "max_symbol": max_symbol,
            "max_symbol_contribution_share": share(float(by_symbol.iloc[0])) if len(by_symbol) else math.nan,
            "top5_symbol_contribution_share": share(float(by_symbol.head(5).sum())) if len(by_symbol) else math.nan,
            "max_year": max_year,
            "max_year_contribution_share": share(float(by_year.iloc[0])) if len(by_year) else math.nan,
        }
        sorted_events = values.sort_values(ascending=False)
        top1 = max(1, int(math.ceil(len(group) * 0.01))) if len(group) else 0
        top5 = max(1, int(math.ceil(len(group) * 0.05))) if len(group) else 0
        base["top1pct_event_contribution_share"] = share(float(sorted_events.head(top1).sum())) if top1 else math.nan
        base["top5pct_event_contribution_share"] = share(float(sorted_events.head(top5).sum())) if top5 else math.nan
        for label, filtered in (
            ("drop_btc", group.loc[~group["base_asset"].eq("BTC")]),
            ("drop_eth", group.loc[~group["base_asset"].eq("ETH")]),
            ("drop_max_symbol", group.loc[~group["symbol"].eq(max_symbol)] if max_symbol else group),
            ("drop_max_year", group.loc[~group["calendar_year"].eq(max_year)] if max_year else group),
        ):
            rows.append({**base, "stress_case": label, "stress_mean_net_return_30": weighted_mean(filtered["net_return_4bps_30"]), "stress_events": int(len(filtered))})
        rows.append({**base, "stress_case": "full", "stress_mean_net_return_30": weighted_mean(group["net_return_4bps_30"]), "stress_events": int(len(group))})
    return pd.DataFrame(rows)


def phase_stats(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (phase, direction), group in events.loc[events["ma_period"].eq(7)].groupby(["phase_hour", "direction"], sort=True):
        rows.append(
            {
                "phase_hour": int(phase),
                "direction": direction,
                "events": int(len(group)),
                "first_hit_favorable_rate": float(group["first_hit_label"].eq("favorable_first").mean()),
                "net_return_4bps_30_mean": weighted_mean(group["net_return_4bps_30"]),
                "net_return_8bps_30_mean": weighted_mean(group["net_return_8bps_30"]),
                "mfe_30_mean": weighted_mean(group["mfe_30"]),
                "mae_30_mean": weighted_mean(group["mae_30"]),
            }
        )
    result = pd.DataFrame(rows)
    med = result.groupby("direction")["net_return_4bps_30_mean"].median().rename("phase_median_net30")
    result = result.merge(med, on="direction", how="left")
    result["native_vs_phase_median_deviation"] = np.where(
        result["phase_hour"].eq(0),
        result["net_return_4bps_30_mean"] - result["phase_median_net30"],
        np.nan,
    )
    positive_share = (
        result.groupby("direction")["net_return_4bps_30_mean"]
        .apply(lambda x: float((x > 0).mean()))
        .rename("positive_phase_share")
    )
    return result.merge(positive_share, on="direction", how="left")


def ma_control_stats(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    phase0 = events.loc[events["phase_hour"].eq(0)]
    for (ma, direction), group in phase0.groupby(["ma_period", "direction"], sort=True):
        rows.append(
            {
                "control_type": "ma_period",
                "ma_period": int(ma),
                "direction": direction,
                "events": int(len(group)),
                "first_hit_favorable_rate": float(group["first_hit_label"].eq("favorable_first").mean()),
                "net_return_4bps_30_mean": weighted_mean(group["net_return_4bps_30"]),
                "net_return_8bps_30_mean": weighted_mean(group["net_return_8bps_30"]),
                "mfe_30_mean": weighted_mean(group["mfe_30"]),
                "mae_30_mean": weighted_mean(group["mae_30"]),
                "survival_bars_mean": weighted_mean(group["same_side_survival_bars"]),
            }
        )
    return pd.DataFrame(rows)


def recent_slices(events: pd.DataFrame) -> pd.DataFrame:
    primary = events.loc[events["phase_hour"].eq(0) & events["ma_period"].eq(7)]
    end = primary["signal_ts"].max()
    windows = {"1d": 1, "7d": 7, "1m": 30, "3m": 91, "6m": 182, "1y": 365}
    rows: list[dict[str, Any]] = []
    for label, days in windows.items():
        subset = primary.loc[primary["signal_ts"] >= end - pd.Timedelta(days=days)]
        for direction, group in subset.groupby("direction", sort=True):
            rows.append(
                {
                    "slice": label,
                    "anchor_end_utc": end.isoformat(),
                    "direction": direction,
                    "events": int(len(group)),
                    "first_hit_favorable_rate": float(group["first_hit_label"].eq("favorable_first").mean()) if len(group) else math.nan,
                    "net_return_4bps_30_mean": weighted_mean(group["net_return_4bps_30"]),
                    "net_return_8bps_30_mean": weighted_mean(group["net_return_8bps_30"]),
                }
            )
    return pd.DataFrame(rows)


def build_metrics_table(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    primary = events.loc[events["phase_hour"].eq(0) & events["ma_period"].eq(7)]
    for direction, group in primary.groupby("direction", sort=True):
        for metric in ("gross_return_30", "net_return_4bps_30", "net_return_8bps_30", "mfe_30", "mae_30", "same_side_survival_bars"):
            dist = summarize_distribution(group[metric])
            rows.append(
                {
                    "direction": direction,
                    "metric": metric,
                    "events": int(np.isfinite(group[metric].to_numpy(dtype=float)).sum()),
                    **dist,
                    **cluster_se(group[metric], group["symbol"], group["utc_week"]),
                }
            )
    return pd.DataFrame(rows)


def side_verdicts(
    first_hit: pd.DataFrame,
    horizon: pd.DataFrame,
    survival: pd.DataFrame,
    yearly: pd.DataFrame,
    concentration: pd.DataFrame,
    controls: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    verdicts: dict[str, dict[str, Any]] = {}
    for direction in ("long", "short"):
        fh = first_hit.loc[first_hit["direction"].eq(direction)].iloc[0]
        h30 = horizon.loc[
            horizon["direction"].eq(direction)
            & horizon["horizon_4h_bars"].eq(30)
            & horizon["cost_case"].eq("fee_plus_4bps_funding_full_net")
        ].iloc[0]
        h30_stress = horizon.loc[
            horizon["direction"].eq(direction)
            & horizon["horizon_4h_bars"].eq(30)
            & horizon["cost_case"].eq("fee_plus_8bps_funding_full_net")
        ].iloc[0]
        y = yearly.loc[yearly["direction"].eq(direction)]
        complete_years = y.loc[y["calendar_year"].between(2023, 2025)]
        positive_complete_years = int(complete_years["net_return_4bps_30_mean"].gt(0).sum())
        conc = concentration.loc[
            concentration["direction"].eq(direction) & concentration["stress_case"].eq("full")
        ].iloc[0]
        no_concentration_flip = bool(
            concentration.loc[
                concentration["direction"].eq(direction)
                & concentration["stress_case"].isin(["drop_btc", "drop_eth", "drop_max_symbol", "drop_max_year"])
            ]["stress_mean_net_return_30"].gt(0).all()
        )
        ma = controls.loc[controls["control_type"].eq("ma_period") & controls["direction"].eq(direction)]
        ma7_net = float(ma.loc[ma["ma_period"].eq(7), "net_return_4bps_30_mean"].iloc[0])
        neighbor_opposite = bool(
            (ma.loc[ma["ma_period"].isin([5, 10]), "net_return_4bps_30_mean"].dropna() < 0).all()
            and ma7_net > 0
        )
        supported = (
            fh["event_favorable_rate"] > fh["control_favorable_rate"]
            and fh["ci_low"] > 0
            and fh["q_value_bh"] < 0.05
            and h30["event_mean"] > 0
            and positive_complete_years >= 4
            and no_concentration_flip
            and (h30_stress["event_mean"] > 0)
            and not neighbor_opposite
        )
        survival_side = survival.loc[survival["direction"].eq(direction)]
        partial = bool(
            (fh["ci_low"] > 0 and fh["q_value_bh"] < 0.10)
            or (
                survival_side.loc[
                    survival_side["metric"].isin(["same_side_survival_bars", "mfe_30"]),
                    "ci_low",
                ]
                .dropna()
                .gt(0)
                .any()
            )
        )
        if supported:
            verdict = "SUPPORTED_WEAK_CONTINUATION"
            reason = "first-hit、净收益、年度、集中度与邻域对照同时过线"
        elif partial:
            verdict = "PARTIAL_STRUCTURAL_SEPARATION"
            reason = "存在 first-hit/MFE/生存分离，但净收益、年度或集中度不足以视为可交易"
        else:
            verdict = "NO-GO"
            reason = "相对同侧非穿越基准未形成稳定且可支付成本的无条件延续优势"
        verdicts[direction] = {
            "verdict": verdict,
            "reason": reason,
            "first_hit_diff": float(fh["diff"]),
            "first_hit_ci_low": float(fh["ci_low"]),
            "first_hit_q_value": float(fh["q_value_bh"]),
            "net30_4bps_mean": float(h30["event_mean"]),
            "net30_8bps_mean": float(h30_stress["event_mean"]),
            "positive_complete_years": positive_complete_years,
            "complete_years_available": int(len(complete_years)),
            "max_symbol_contribution_share": float(conc["max_symbol_contribution_share"]) if np.isfinite(conc["max_symbol_contribution_share"]) else math.nan,
            "top1pct_event_contribution_share": float(conc["top1pct_event_contribution_share"]) if np.isfinite(conc["top1pct_event_contribution_share"]) else math.nan,
            "neighbor_opposite": neighbor_opposite,
        }
    return verdicts


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")


def write_report(summary: dict[str, Any], tables: dict[str, pd.DataFrame]) -> None:
    verdict = summary["decision"]["side_verdicts"]
    event_counts = summary["events"]
    audit = summary["data_audit"]
    def md_table(frame: pd.DataFrame, columns: Sequence[str], n: int = 8) -> str:
        if frame.empty:
            return "_无数据_"
        view = frame.loc[:, columns].head(n).copy()
        def fmt(value: Any) -> str:
            if pd.isna(value):
                return ""
            if isinstance(value, float):
                return f"{value:.6f}"
            return str(value)
        header = "| " + " | ".join(columns) + " |"
        sep = "| " + " | ".join(["---"] * len(columns)) + " |"
        body = [
            "| " + " | ".join(fmt(value) for value in row) + " |"
            for row in view.to_numpy(dtype=object)
        ]
        return "\n".join([header, sep, *body])
    report = f"""# BIN-4H-MA7-RC P0 结果报告（2026-09-02）

## 结论先行

P0 最终裁决：long = `{verdict['long']['verdict']}`；short = `{verdict['short']['verdict']}`。本次仍保持 `explore / diagnostic-only / not promoted / not live-ready`，明确不登记 `V1`、不 promotion、不 live-ready、不创建 runner / live spec。

P0 只回答无条件 `4h SMA7` strict cross 后是否存在趋势延续。结果不得被用来事后选择 `MA5/MA10/SMA42`、方向、持仓期、币种或过滤器。

是否允许进入 P1：`{summary['decision']['p1_allowed']}`。理由：{summary['decision']['p1_reason']}

## 数据与 PIT 币池审计

- 市场：Binance USD-M USDT perpetual，24/7 UTC。
- 输入：normalized `1h` OHLCV + normalized funding，`4h` 由真实闭合 `1h` 重聚合。
- `audit_as_of`：`{summary['config']['data']['audit_as_of_utc']}`。
- 数据截止：`{summary['config']['data']['cutoff_exclusive_utc']}`；最后允许完整原生 `4h`：`{summary['config']['data']['last_allowed_complete_4h_open_utc']}`。
- 配置 SHA256：`{summary['input_lineage']['config_sha256']}`；输入 manifest SHA256：`{summary['input_lineage']['dataset_manifest_sha256']}`。
- OHLCV selected rows：`{audit['ohlcv_selected_rows_before_cutoff']}`，symbols：`{audit['ohlcv_selected_symbols_before_cutoff']}`，范围 `{audit['ohlcv_min_ts_utc']}` 至 `{audit['ohlcv_max_ts_utc']}`。
- Funding selected rows：`{audit['funding_selected_rows_before_or_at_cutoff']}`，symbols：`{audit['funding_selected_symbols_before_or_at_cutoff']}`，范围 `{audit['funding_min_ts_utc']}` 至 `{audit['funding_max_ts_utc']}`。
- PIT 交易池规则：上市龄 `>=30` 天、30 日 trailing ADV `>=10,000,000 USDT`、30 日覆盖率 `>=95%`、每日最多 ADV 前 `120`。

关键数据 blocker：`{summary['blockers']}`。

## 事件数量

- 主相位 `0h` / `SMA7`：总事件 `{event_counts['primary_ma7_phase0_total']}`，long `{event_counts['primary_ma7_phase0_long']}`，short `{event_counts['primary_ma7_phase0_short']}`，symbols `{event_counts['primary_ma7_phase0_symbols']}`。
- 全相位/全 MA 输出事件行：`{event_counts['all_event_rows']}`。
- 同侧非穿越对照行：`{event_counts['non_cross_control_rows']}`。

## Long / Short 无条件结果

{md_table(tables['first_hit'], ['direction', 'event_count', 'control_count', 'event_favorable_rate', 'control_favorable_rate', 'diff', 'ci_low', 'ci_high', 'p_value', 'q_value_bh'])}

## First-Hit 与生存曲线

first-hit 使用 `+2 ATR / -1 ATR / 30 bars`，`ATR_scale = ATR20[t-1]`；同一 `1h` 双障碍触发按 adverse-first。

{md_table(tables['survival'], ['direction', 'metric', 'event_mean', 'control_mean', 'incremental_diff', 'ci_low', 'ci_high', 'p_value', 'q_value_bh'])}

## 固定期限收益

固定期限收益以 `open[t+1]` 入场，在期限结束后的可执行 `4h` open 平仓；下表为主相位 `SMA7`：

{md_table(tables['horizon'], ['direction', 'horizon_4h_bars', 'cost_case', 'event_count', 'event_mean', 'control_mean', 'incremental_diff', 'ci_low', 'ci_high', 'q_value_bh'], n=36)}

## 成本与 Funding

成本列同时输出 gross、fee + 4bps、fee + 8bps 与 full net。Funding 按真实事件时间和方向累计，缺失不会填 0；`funding_complete_30_rate` 见年度表。若任一侧因 funding 缺失无法覆盖完整净收益，该侧不得给出可交易通过。

## 同侧非穿越基准

同侧非穿越基准按 `symbol × calendar_year × side × causal ATR quintile` 确定性加权，使对照分层权重与穿越事件一致；未使用随机时点或当前 TopN 回填。

## MA5/7/10/42 对照

{md_table(tables['controls'].loc[tables['controls']['control_type'].eq('ma_period')], ['ma_period', 'direction', 'events', 'first_hit_favorable_rate', 'net_return_4bps_30_mean', 'net_return_8bps_30_mean', 'mfe_30_mean', 'mae_30_mean'])}

## 年度、币种、流动性与集中度

年度结果：

{md_table(tables['yearly'], ['direction', 'calendar_year', 'events', 'first_hit_favorable_rate', 'net_return_4bps_30_mean', 'net_return_8bps_30_mean', 'funding_complete_30_rate'], n=20)}

集中度与 leave-one-out：

{md_table(tables['concentration'], ['direction', 'stress_case', 'stress_events', 'mean_net_return_30', 'stress_mean_net_return_30', 'max_symbol', 'max_symbol_contribution_share', 'top5_symbol_contribution_share', 'max_year', 'max_year_contribution_share', 'top1pct_event_contribution_share'], n=12)}

## Phase 检查

相位从真实 `1h` 分别重聚合 `0h/1h/2h/3h`，主结果仍只用原生 `0h`；非原生相位不替换主相位。

{md_table(tables['phase'], ['phase_hour', 'direction', 'events', 'first_hit_favorable_rate', 'net_return_4bps_30_mean', 'net_return_8bps_30_mean', 'mfe_30_mean', 'mae_30_mean', 'positive_phase_share', 'native_vs_phase_median_deviation'])}

## 最近切片

最近切片锚定本次可用主样本末尾，仅作审计，不参与选择。

{md_table(tables['recent'], ['slice', 'anchor_end_utc', 'direction', 'events', 'first_hit_favorable_rate', 'net_return_4bps_30_mean', 'net_return_8bps_30_mean'], n=20)}

## 数据或执行 Blocker

- P0 未发现可绕过的执行入口：信号 bar 收盘后下一根 `4h` open 入场，未使用信号 close 成交。
- Funding 缺失事件只阻断对应净收益，不以 0 填充。
- P0 不是策略回测；first-hit 障碍不是实际止盈止损。
- Live blocker：没有 runner 规格、没有账户组合、没有线上 open/close 对账，因此不允许 promotion 或 live-ready 声明。

## 是否进入 P1

`{summary['decision']['p1_allowed']}`。{summary['decision']['p1_reason']}

## 证据文件

- [P0 合同](../specs/binance-4h-ma7-regime-continuation-p0-contract-2026-09-02.md)
- [P0 配置](../configs/binance-4h-ma7-regime-continuation-p0.json)
- [数据审计](../artifacts/binance_4h_ma7_rc_p0_data_audit_2026-09-02.json)
- [事件表](../artifacts/binance_4h_ma7_rc_p0_events_2026-09-02.parquet)
- [summary](../artifacts/binance_4h_ma7_rc_p0_summary_2026-09-02.json)
- [脚本](../scripts/research_binance_4h_ma7_regime_continuation_p0.py)
"""
    REPORT_PATH.write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    if not args.run:
        raise SystemExit("pass --run to acknowledge frozen historical outcome read")
    config = validate_frozen_config()
    prepare_outputs(args.force)
    rng = np.random.default_rng(SEED)

    print("stage: load and audit selected 1h OHLCV/funding", flush=True)
    ohlcv, ohlcv_audit = load_selected_ohlcv(config)
    funding, funding_audit = load_selected_funding(config)
    hourly_by_sym = hourly_maps(ohlcv)
    funding_lookup = build_funding_lookup(funding)

    print("stage: aggregate 1h to 4h phases and compute indicators", flush=True)
    phase_panels: list[pd.DataFrame] = []
    phase_audits: list[dict[str, Any]] = []
    for phase in config["aggregation_4h"]["phases_hours"]:
        bars, audit = aggregate_4h(ohlcv, int(phase))
        bars = add_indicators(bars)
        phase_panels.append(bars)
        phase_audits.append(audit)
        print(f"  phase {phase}: {audit['complete_4h_bars']} complete 4h bars", flush=True)
    panel = pd.concat(phase_panels, ignore_index=True)
    primary_panel = panel.loc[panel["phase_hour"].eq(0)].copy()
    print("stage: build PIT universe", flush=True)
    eligibility, universe_summary = build_universe(primary_panel)
    panel = attach_universe(panel, eligibility)
    fourh_by_sym_phase = panel_maps(panel)

    print("stage: extract strict-cross events", flush=True)
    event_frames = [build_event_candidates(panel, period) for period in MA_PERIODS]
    events = pd.concat([frame for frame in event_frames if not frame.empty], ignore_index=True)
    print(f"  event rows before outcome enrichment: {len(events)}", flush=True)
    print("stage: label event outcomes", flush=True)
    events = enrich_outcomes(events, hourly_by_sym, fourh_by_sym_phase, funding_lookup)

    print("stage: build and label same-side non-cross controls", flush=True)
    controls_raw = build_non_cross_controls(panel)
    print(f"  control rows before outcome enrichment: {len(controls_raw)}", flush=True)
    controls = enrich_outcomes(controls_raw, hourly_by_sym, fourh_by_sym_phase, funding_lookup)
    controls = apply_control_weights(
        events.loc[events["phase_hour"].eq(0) & events["ma_period"].eq(7)],
        controls,
    )

    print("stage: aggregate statistics and bootstrap confidence intervals", flush=True)
    first_hit = build_first_hit_stats(events, controls, rng)
    horizon = build_horizon_stats(events, controls, rng)
    survival = build_survival_stats(events, controls, rng)
    yearly = summarize_by_year(events)
    concentration = concentration_rows(events)
    phase = phase_stats(events)
    ma_controls = ma_control_stats(events)
    recent = recent_slices(events)
    metrics = build_metrics_table(events)

    controls_summary = ma_controls.copy()
    controls_summary["control_weighted_rows"] = np.nan
    strata_coverage = (
        controls.groupby(["direction", "control_stratum_has_event"], dropna=False)
        .size()
        .reset_index(name="rows")
    )
    strata_coverage["control_type"] = "same_side_non_cross_coverage"
    strata_coverage["ma_period"] = 7
    for col in ("events", "first_hit_favorable_rate", "net_return_4bps_30_mean", "net_return_8bps_30_mean", "mfe_30_mean", "mae_30_mean", "survival_bars_mean", "control_weighted_rows"):
        if col not in strata_coverage:
            strata_coverage[col] = np.nan
    controls_out = pd.concat([controls_summary, strata_coverage[controls_summary.columns]], ignore_index=True)

    verdicts = side_verdicts(first_hit, horizon, survival, yearly, concentration, ma_controls)
    p1_allowed = any(
        item["verdict"] in {"SUPPORTED_WEAK_CONTINUATION", "PARTIAL_STRUCTURAL_SEPARATION"}
        for item in verdicts.values()
    )
    p1_reason = (
        "至少一侧存在可继续画 P1 状态地图的结构性分离；P1 仍须另行冻结。"
        if p1_allowed
        else "两侧均为 NO-GO；不应进入 P1，也不得用过滤器营救已揭示历史。"
    )

    data_audit = {
        **ohlcv_audit,
        **funding_audit,
        "aggregation_4h": phase_audits,
        "universe_days": int(eligibility["day"].nunique()),
        "universe_eligible_symbol_days": int(eligibility["eligible"].sum()),
        "universe_pool_symbol_days": int(eligibility["in_trading_pool"].sum()),
        "fail_closed_passed": True,
    }
    primary_events = events.loc[events["phase_hour"].eq(0) & events["ma_period"].eq(7)]
    summary = {
        "family": "Binance-4H-MA7-Regime-Continuation",
        "alias": "BIN-4H-MA7-RC",
        "stage": "P0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "explore / diagnostic-only / not promoted / not live-ready",
        "config": config,
        "input_lineage": {
            "config_path": rel(CONFIG_PATH),
            "config_sha256": EXPECTED_CONFIG_SHA256,
            "dataset_manifest_path": config["data"]["dataset_manifest"],
            "dataset_manifest_sha256": EXPECTED_MANIFEST_SHA256,
        },
        "data_audit": data_audit,
        "events": {
            "all_event_rows": int(len(events)),
            "primary_ma7_phase0_total": int(len(primary_events)),
            "primary_ma7_phase0_long": int(primary_events["direction"].eq("long").sum()),
            "primary_ma7_phase0_short": int(primary_events["direction"].eq("short").sum()),
            "primary_ma7_phase0_symbols": int(primary_events["symbol"].nunique()),
            "non_cross_control_rows": int(len(controls)),
        },
        "blockers": [],
        "decision": {
            "side_verdicts": verdicts,
            "p1_allowed": "YES" if p1_allowed else "NO",
            "p1_reason": p1_reason,
            "no_registration": True,
            "no_promotion": True,
            "not_live_ready": True,
        },
    }

    write_json(OUTPUTS["data_audit"], data_audit)
    universe_summary.to_csv(OUTPUTS["universe"], index=False)
    events.to_parquet(OUTPUTS["events"], index=False, compression="zstd")
    metrics.to_csv(OUTPUTS["metrics"], index=False)
    first_hit.to_csv(OUTPUTS["first_hit"], index=False)
    horizon.to_csv(OUTPUTS["horizon"], index=False)
    survival.to_csv(OUTPUTS["survival"], index=False)
    yearly.to_csv(OUTPUTS["yearly"], index=False)
    concentration.to_csv(OUTPUTS["concentration"], index=False)
    phase.to_csv(OUTPUTS["phase"], index=False)
    controls_out.to_csv(OUTPUTS["controls"], index=False)
    recent.to_csv(OUTPUTS["recent"], index=False)

    tables = {
        "first_hit": first_hit,
        "horizon": horizon,
        "survival": survival,
        "yearly": yearly,
        "concentration": concentration,
        "phase": phase,
        "controls": controls_out,
        "recent": recent,
    }
    write_report(summary, tables)
    artifact_hashes = {}
    for name, path in OUTPUTS.items():
        if name == "summary":
            continue
        artifact_hashes[rel(path)] = write_sidecar(path)
    artifact_hashes[rel(REPORT_PATH)] = write_sidecar(REPORT_PATH)
    summary["artifact_hashes"] = artifact_hashes
    write_json(OUTPUTS["summary"], summary)
    write_sidecar(OUTPUTS["summary"])

    print(
        json.dumps(
            {
                "events": summary["events"],
                "decision": summary["decision"],
                "summary": rel(OUTPUTS["summary"]),
                "report": rel(REPORT_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
