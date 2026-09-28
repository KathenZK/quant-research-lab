from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
from http.client import IncompleteRead
import json
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from strategy_lab.data import (
    DataLakeLayout,
    DatasetKind,
    MarketType,
    audit_ohlcv_frame,
)
from strategy_lab.data.fs import atomic_write_path
from strategy_lab.data.normalize import normalize_dataset
from strategy_lab.data.settings import load_settings


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = (
    ROOT
    / "research/asset-portfolios/1d-ma7-rsi6-direction-aligned-pooled-ml"
)
ARTIFACT_DIR = FAMILY_DIR / "artifacts/p0_data_2026-08-10"
FEATURE_DIR = ROOT / "data/features/binance_1d_ma7_rsi6_dapml_p0"

API_ROOT = "https://fapi.binance.com"
USER_AGENT = "quant-research-lab-bin-1d-ma7-rsi6-dapml-p0/0.1"
KLINE_SOURCE = "binance_futures_kline_api_direct"
FUNDING_SOURCE = "binance_futures_funding_rate_api_direct"
MARK_SOURCE = "binance_mark_price"
HOUR_MS = 60 * 60 * 1000
MARK_INTERVAL = "1h"
MARK_INTERVAL_MS = HOUR_MS
MAX_FUNDING_GAP_HOURS = 8
REQUEST_PAGE_DELAY_SECONDS = 0.05
SEALED_START = pd.Timestamp("2025-08-07T00:00:00Z")
SEALED_END_EXCLUSIVE = pd.Timestamp("2026-08-07T00:00:00Z")

SYMBOLS = {
    "BTCUSDT": ("BTC", "BTC/USDT:USDT", "btcusdt"),
    "ETHUSDT": ("ETH", "ETH/USDT:USDT", "ethusdt"),
    "BNBUSDT": ("BNB", "BNB/USDT:USDT", "bnbusdt"),
    "SOLUSDT": ("SOL", "SOL/USDT:USDT", "solusdt"),
    "TRXUSDT": ("TRX", "TRX/USDT:USDT", "trxusdt"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build audited direct 1h, aggregated UTC 1d, and resolved funding/mark "
            "inputs for the five-asset MA7/RSI6 pooled P0 study."
        )
    )
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument(
        "--symbols",
        nargs="+",
        choices=sorted(SYMBOLS),
        default=list(SYMBOLS),
    )
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args()


def request_json(
    path: str,
    *,
    params: dict[str, object] | None = None,
    timeout: float,
    attempts: int = 7,
) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    url = f"{API_ROOT}{path}{query}"
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {418, 429, 500, 502, 503, 504}:
                raise
        except (
            URLError,
            TimeoutError,
            IncompleteRead,
            ConnectionError,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(15.0, 0.75 * 2**attempt))
    raise RuntimeError(
        f"Binance request failed after {attempts} attempts: {url}"
    ) from last_error


def fetch_contracts(timeout: float) -> dict[str, dict[str, Any]]:
    payload = request_json("/fapi/v1/exchangeInfo", timeout=timeout)
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected Binance exchangeInfo payload")
    by_symbol = {
        str(row.get("symbol")): row for row in payload.get("symbols", [])
    }
    contracts: dict[str, dict[str, Any]] = {}
    for symbol in SYMBOLS:
        if symbol not in by_symbol:
            raise RuntimeError(f"{symbol} missing from Binance exchangeInfo")
        row = by_symbol[symbol]
        contract = {
            "symbol": symbol,
            "status": row.get("status"),
            "contract_type": row.get("contractType"),
            "quote_asset": row.get("quoteAsset"),
            "margin_asset": row.get("marginAsset"),
            "onboard_date_ms": int(row["onboardDate"]),
            "onboard_date": pd.to_datetime(
                row["onboardDate"], unit="ms", utc=True
            ).isoformat(),
        }
        if (
            contract["status"] != "TRADING"
            or contract["contract_type"] != "PERPETUAL"
            or contract["quote_asset"] != "USDT"
            or contract["margin_asset"] != "USDT"
        ):
            raise RuntimeError(f"Unexpected contract identity: {contract}")
        contracts[symbol] = contract
    return contracts


def server_time_ms(timeout: float) -> int:
    payload = request_json("/fapi/v1/time", timeout=timeout)
    if not isinstance(payload, dict) or "serverTime" not in payload:
        raise RuntimeError(f"Unexpected Binance server-time payload: {payload!r}")
    return int(payload["serverTime"])


def fetch_paginated_klines(
    symbol: str,
    *,
    endpoint: str,
    interval: str,
    interval_ms: int,
    start_ms: int,
    cutoff_ms: int,
    timeout: float,
) -> list[list[Any]]:
    rows: list[list[Any]] = []
    cursor = start_ms
    while cursor < cutoff_ms:
        payload = request_json(
            endpoint,
            params={
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor,
                "endTime": cutoff_ms,
                "limit": 1500,
            },
            timeout=timeout,
        )
        if not isinstance(payload, list):
            raise RuntimeError(
                f"Unexpected {symbol} {endpoint} payload: {payload!r}"
            )
        if not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1][0]) + interval_ms
        if next_cursor <= cursor:
            raise RuntimeError(f"{symbol} {endpoint} pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1500:
            break
        time.sleep(REQUEST_PAGE_DELAY_SECONDS)
    if not rows:
        raise RuntimeError(f"Binance returned no {symbol} {interval} rows")
    return rows


def fetch_hourly(
    symbol: str,
    *,
    start_ms: int,
    cutoff_ms: int,
    timeout: float,
) -> pd.DataFrame:
    rows = fetch_paginated_klines(
        symbol,
        endpoint="/fapi/v1/klines",
        interval="1h",
        interval_ms=HOUR_MS,
        start_ms=start_ms,
        cutoff_ms=cutoff_ms,
        timeout=timeout,
    )
    columns = [
        "open_time_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time_ms",
        "quote_volume",
        "trade_count",
        "taker_buy_volume",
        "taker_buy_quote_volume",
        "ignore",
    ]
    frame = pd.DataFrame(rows, columns=columns)
    frame["open_time"] = pd.to_datetime(frame["open_time_ms"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(
        frame["close_time_ms"], unit="ms", utc=True
    )
    for column in (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_volume",
        "taker_buy_quote_volume",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame["trade_count"] = frame["trade_count"].astype("int64")
    frame["exchange"] = "binance"
    frame["symbol"] = SYMBOLS[symbol][1]
    frame["market_type"] = "perp"
    frame["timeframe"] = "1h"
    frame["is_closed"] = frame["close_time_ms"].lt(cutoff_ms)
    frame["source"] = KLINE_SOURCE
    return (
        frame.loc[frame["is_closed"]]
        .sort_values("open_time_ms")
        .drop_duplicates("open_time_ms", keep="last")
        .reset_index(drop=True)
    )


def derivation_provenance(
    *,
    generated_at: str,
    formula_version: str,
    fields: dict[str, Any],
) -> str:
    return json.dumps(
        {
            "mode": "explicit_opt_in",
            "formula_version": formula_version,
            "generated_at_utc": generated_at,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "fields": fields,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def normalize_hourly(
    symbol: str,
    raw: pd.DataFrame,
    *,
    generated_at: str,
) -> pd.DataFrame:
    duration_ms = raw["close_time_ms"] - raw["open_time_ms"] + 1
    aligned = (
        raw["open_time"].dt.minute.eq(0)
        & raw["open_time"].dt.second.eq(0)
        & raw["open_time"].dt.microsecond.eq(0)
        & duration_ms.eq(HOUR_MS)
    )
    if not aligned.all():
        raise RuntimeError(
            f"{symbol} has {int((~aligned).sum())} incomplete or unaligned hourly bars"
        )
    base, display, _ = SYMBOLS[symbol]
    volume_positive = raw["volume"].gt(0.0)
    provenance = derivation_provenance(
        generated_at=generated_at,
        formula_version="binance-hourly-vwap-v1",
        fields={
            "input_source": KLINE_SOURCE,
            "vwap": {
                "formula": "quote_volume / volume; close when volume == 0",
                "source_columns": ["quote_volume", "volume", "close"],
            }
        },
    )
    normalized = pd.DataFrame(
        {
            "ts": raw["open_time"],
            "exchange": "binance",
            "symbol": display,
            "market_type": "perp",
            "timeframe": "1h",
            "base_asset": base,
            "quote_asset": "USDT",
            "open": raw["open"],
            "high": raw["high"],
            "low": raw["low"],
            "close": raw["close"],
            "volume": raw["volume"],
            "quote_volume": raw["quote_volume"],
            "trade_count": raw["trade_count"],
            "vwap": np.where(
                volume_positive,
                raw["quote_volume"] / raw["volume"],
                raw["close"],
            ),
            "is_closed": raw["is_closed"].astype(bool),
            "source": KLINE_SOURCE,
            "derivation_provenance": provenance,
            "quality_flags": np.where(
                volume_positive,
                "derived_vwap_quote_volume_over_volume",
                "derived_vwap_close_fill_zero_volume",
            ),
        }
    )
    return normalize_dataset(DatasetKind.OHLCV, normalized)


def aggregate_daily(
    symbol: str,
    hourly: pd.DataFrame,
    *,
    generated_at: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    work = hourly.copy()
    work["day"] = work["ts"].dt.floor("1D")
    group_sizes = work.groupby("day", sort=True).size()
    complete_days = group_sizes.index[group_sizes.eq(24)]
    day_first = work.groupby("day", sort=True)["ts"].min()
    day_last = work.groupby("day", sort=True)["ts"].max()
    grid_complete = (
        day_first.eq(day_first.index)
        & day_last.eq(day_last.index + pd.Timedelta(hours=23))
    )
    accepted_days = complete_days.intersection(grid_complete.index[grid_complete])
    accepted = work.loc[work["day"].isin(accepted_days)].copy()
    grouped = accepted.groupby("day", sort=True)
    base, display, _ = SYMBOLS[symbol]
    daily = pd.DataFrame(
        {
            "ts": grouped["ts"].first().index,
            "exchange": "binance",
            "symbol": display,
            "market_type": "perp",
            "timeframe": "1d",
            "base_asset": base,
            "quote_asset": "USDT",
            "open": grouped["open"].first().to_numpy(),
            "high": grouped["high"].max().to_numpy(),
            "low": grouped["low"].min().to_numpy(),
            "close": grouped["close"].last().to_numpy(),
            "volume": grouped["volume"].sum().to_numpy(),
            "quote_volume": grouped["quote_volume"].sum().to_numpy(),
            "trade_count": grouped["trade_count"].sum().astype("int64").to_numpy(),
            "is_closed": True,
            "source": KLINE_SOURCE,
        }
    )
    daily["vwap"] = np.where(
        daily["volume"].gt(0.0),
        daily["quote_volume"] / daily["volume"],
        daily["close"],
    )
    daily["derivation_provenance"] = derivation_provenance(
        generated_at=generated_at,
        formula_version="utc-daily-from-24-hour-bars-v1",
        fields={
            "input_source": KLINE_SOURCE,
            "ohlc": "first/max/min/last",
            "volume_quote_volume_trade_count": "sum",
            "vwap": "daily quote_volume / daily volume; close when volume == 0",
            "required_hourly_rows": 24,
        },
    )
    daily["quality_flags"] = "aggregated_from_24_complete_hourly_bars"
    daily = normalize_dataset(DatasetKind.OHLCV, daily)
    audit = audit_ohlcv_frame(daily, expected_timeframe="1d")
    rejected = group_sizes.loc[~group_sizes.index.isin(accepted_days)]
    quality = {
        "rows": int(len(daily)),
        "start": daily["ts"].min().isoformat(),
        "end": daily["ts"].max().isoformat(),
        "source_hourly_rows": int(len(hourly)),
        "rejected_incomplete_days": {
            str(day.date()): int(count) for day, count in rejected.items()
        },
        "audit": audit.to_dict(),
    }
    if not audit.trusted:
        raise RuntimeError(f"{symbol} daily aggregate failed quality audit: {quality}")
    return daily, quality


def audit_hourly(
    symbol: str,
    raw: pd.DataFrame,
    hourly: pd.DataFrame,
) -> dict[str, Any]:
    audit = audit_ohlcv_frame(hourly, expected_timeframe="1h")
    merged = raw.merge(
        hourly,
        left_on="open_time",
        right_on="ts",
        how="outer",
        suffixes=("_raw", "_normalized"),
        indicator=True,
    )
    both = merged["_merge"].eq("both")
    mismatches: dict[str, int] = {}
    for column in (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
    ):
        mismatches[column] = int(
            (
                ~np.isclose(
                    merged.loc[both, f"{column}_raw"].to_numpy(dtype="float64"),
                    merged.loc[both, f"{column}_normalized"].to_numpy(
                        dtype="float64"
                    ),
                    rtol=0.0,
                    atol=0.0,
                )
            ).sum()
        )
    blockers = (
        (not audit.trusted)
        or int(merged["_merge"].ne("both").sum()) > 0
        or any(mismatches.values())
    )
    result = {
        "audit": audit.to_dict(),
        "raw_rows": int(len(raw)),
        "normalized_rows": int(len(hourly)),
        "raw_normalized_join": {
            str(key): int(value)
            for key, value in merged["_merge"].value_counts().sort_index().items()
        },
        "field_mismatches": mismatches,
        "sha256": frame_sha256(hourly),
        "blocker_count": int(bool(blockers)),
    }
    if blockers:
        raise RuntimeError(f"{symbol} hourly data-quality blockers: {result}")
    return result


def fetch_funding(
    symbol: str,
    *,
    start_ms: int,
    cutoff_ms: int,
    timeout: float,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    cursor = start_ms
    while cursor < cutoff_ms:
        payload = request_json(
            "/fapi/v1/fundingRate",
            params={
                "symbol": symbol,
                "startTime": cursor,
                "endTime": cutoff_ms,
                "limit": 1000,
            },
            timeout=timeout,
        )
        if not isinstance(payload, list):
            raise RuntimeError(f"Unexpected {symbol} funding payload: {payload!r}")
        if not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise RuntimeError(f"{symbol} funding pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1000:
            break
        time.sleep(REQUEST_PAGE_DELAY_SECONDS)
    if not rows:
        raise RuntimeError(f"Binance returned no {symbol} funding rows")
    frame = pd.DataFrame(rows)
    frame["funding_time_ms"] = pd.to_numeric(
        frame["fundingTime"], errors="raise"
    ).astype("int64")
    frame["ts"] = pd.to_datetime(frame["funding_time_ms"], unit="ms", utc=True)
    frame["funding_rate"] = pd.to_numeric(
        frame["fundingRate"], errors="raise"
    )
    frame["endpoint_mark_price"] = pd.to_numeric(
        frame.get("markPrice"), errors="coerce"
    )
    base, display, _ = SYMBOLS[symbol]
    frame["exchange"] = "binance"
    frame["symbol"] = display
    frame["market_type"] = "perp"
    frame["base_asset"] = base
    frame["quote_asset"] = "USDT"
    frame["source"] = FUNDING_SOURCE
    return (
        frame.sort_values("funding_time_ms")
        .drop_duplicates("funding_time_ms", keep="last")
        .reset_index(drop=True)
    )


def fetch_mark(
    symbol: str,
    *,
    start_ms: int,
    cutoff_ms: int,
    timeout: float,
) -> pd.DataFrame:
    rows = fetch_paginated_klines(
        symbol,
        endpoint="/fapi/v1/markPriceKlines",
        interval=MARK_INTERVAL,
        interval_ms=MARK_INTERVAL_MS,
        start_ms=start_ms,
        cutoff_ms=cutoff_ms,
        timeout=timeout,
    )
    columns = [
        "open_time_ms",
        "open",
        "high",
        "low",
        "close",
        "ignore_volume",
        "close_time_ms",
        "ignore_quote_volume",
        "observation_count",
        "ignore_taker_base",
        "ignore_taker_quote",
        "ignore",
    ]
    frame = pd.DataFrame(rows, columns=columns)
    frame["ts"] = pd.to_datetime(frame["open_time_ms"], unit="ms", utc=True)
    frame["close_ts"] = pd.to_datetime(
        frame["close_time_ms"], unit="ms", utc=True
    )
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame["observation_count"] = pd.to_numeric(
        frame["observation_count"], errors="raise"
    ).astype("int64")
    frame["exchange"] = "binance"
    frame["market_type"] = "perp"
    frame["symbol"] = SYMBOLS[symbol][1]
    frame["timeframe"] = MARK_INTERVAL
    frame["source"] = MARK_SOURCE
    frame["is_closed"] = frame["close_time_ms"].lt(cutoff_ms)
    return (
        frame.loc[frame["is_closed"]]
        .sort_values("ts")
        .drop_duplicates("ts", keep="last")
        .reset_index(drop=True)
    )


def audit_mark(symbol: str, frame: pd.DataFrame) -> dict[str, Any]:
    timestamps = pd.DatetimeIndex(frame["ts"])
    expected = pd.date_range(
        timestamps.min(), timestamps.max(), freq=MARK_INTERVAL
    )
    missing = expected.difference(timestamps)
    invalid_ohlc = frame["high"].lt(
        frame[["open", "close", "low"]].max(axis=1)
    ) | frame["low"].gt(frame[["open", "close", "high"]].min(axis=1))
    blockers = (
        int(timestamps.duplicated().sum())
        + int(len(missing))
        + int(invalid_ohlc.sum())
        + int(frame[["open", "high", "low", "close"]].isna().sum().sum())
        + int((~frame["is_closed"]).sum())
    )
    result = {
        "rows": int(len(frame)),
        "start": timestamps.min().isoformat(),
        "end": timestamps.max().isoformat(),
        "expected_rows": int(len(expected)),
        "missing_bars": int(len(missing)),
        "duplicate_rows": int(timestamps.duplicated().sum()),
        "invalid_ohlc": int(invalid_ohlc.sum()),
        "not_closed": int((~frame["is_closed"]).sum()),
        "blocker_count": int(blockers),
    }
    if blockers:
        raise RuntimeError(f"{symbol} mark-price quality blockers: {result}")
    return result


def resolve_funding(
    symbol: str,
    funding: pd.DataFrame,
    mark: pd.DataFrame,
    *,
    generated_at: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    work = funding.copy()
    work["funding_nominal_ts"] = work["ts"].dt.floor(MARK_INTERVAL)
    lag = (work["ts"] - work["funding_nominal_ts"]).dt.total_seconds()
    invalid_lag = lag.lt(0.0) | lag.gt(1.0)
    if invalid_lag.any():
        examples = work.loc[invalid_lag, "ts"].head(10).tolist()
        raise RuntimeError(
            f"{symbol} funding timestamps exceed one-second tolerance: {examples}"
        )
    mark_open = mark[["ts", "open"]].rename(
        columns={"ts": "funding_nominal_ts", "open": "mark_kline_open"}
    )
    merged = work.merge(
        mark_open,
        on="funding_nominal_ts",
        how="left",
        validate="one_to_one",
    )
    endpoint_mark = merged["endpoint_mark_price"]
    fallback_mark = merged["mark_kline_open"]
    merged["mark_price"] = endpoint_mark.fillna(fallback_mark)
    merged["mark_price_source"] = np.where(
        endpoint_mark.notna(),
        "binance_funding_history_mark_price",
        np.where(
            fallback_mark.notna(),
            "binance_mark_price_kline_1h_open",
            "unresolved",
        ),
    )
    merged["derivation_provenance"] = derivation_provenance(
        generated_at=generated_at,
        formula_version="pooled-funding-mark-resolution-v1",
        fields={
            "funding_source": FUNDING_SOURCE,
            "mark_fallback": f"{MARK_SOURCE} 1h open",
            "join_key": (
                "funding timestamp floored to its actual UTC hour after "
                "<=1 second lag audit"
            ),
        },
    )
    overlap = merged.loc[endpoint_mark.notna() & fallback_mark.notna()]
    overlap_diff_bps = (
        overlap["mark_kline_open"] / overlap["endpoint_mark_price"] - 1.0
    ).abs() * 10_000.0
    output = merged[
        [
            "ts",
            "funding_nominal_ts",
            "exchange",
            "symbol",
            "market_type",
            "base_asset",
            "quote_asset",
            "funding_rate",
            "mark_price",
            "mark_price_source",
            "source",
            "derivation_provenance",
        ]
    ]
    unresolved = output["mark_price"].isna()
    output = output.loc[~unresolved].reset_index(drop=True)
    nominal = pd.DatetimeIndex(output["funding_nominal_ts"])
    funding_gaps_hours = pd.Series(nominal).diff().dt.total_seconds().div(3600.0)
    invalid_funding_gaps = funding_gaps_hours.dropna().loc[
        funding_gaps_hours.dropna().le(0.0)
        | funding_gaps_hours.dropna().gt(MAX_FUNDING_GAP_HOURS)
        | np.mod(funding_gaps_hours.dropna(), 1.0).ne(0.0)
    ]
    critical_nulls = {
        column: int(output[column].isna().sum())
        for column in (
            "ts",
            "funding_nominal_ts",
            "funding_rate",
            "mark_price",
            "mark_price_source",
        )
    }
    blockers = (
        sum(critical_nulls.values())
        + int(output["ts"].duplicated().sum())
        + int(output["funding_nominal_ts"].duplicated().sum())
        + int((output["mark_price"] <= 0.0).sum())
        + int(len(invalid_funding_gaps))
    )
    quality = {
        "funding_rows": int(len(funding)),
        "funding_start": funding["ts"].min().isoformat(),
        "funding_end": funding["ts"].max().isoformat(),
        "funding_timestamp_lag_seconds": {
            "median": float(lag.median()),
            "p95": float(lag.quantile(0.95)),
            "max": float(lag.max()),
        },
        "endpoint_mark_rows": int(endpoint_mark.notna().sum()),
        "fallback_mark_rows": int(
            (endpoint_mark.isna() & fallback_mark.notna()).sum()
        ),
        "unresolved_rows_excluded": int(unresolved.sum()),
        "resolved_rows": int(len(output)),
        "resolved_start": output["ts"].min().isoformat(),
        "resolved_end": output["ts"].max().isoformat(),
        "funding_interval_hours": {
            str(float(interval)): int(count)
            for interval, count in funding_gaps_hours.dropna()
            .value_counts()
            .sort_index()
            .items()
        },
        "invalid_funding_gap_count": int(len(invalid_funding_gaps)),
        "max_funding_gap_hours": float(funding_gaps_hours.max()),
        "overlap_rows": int(len(overlap)),
        "overlap_mark_abs_diff_bps": {
            "median": (
                float(overlap_diff_bps.median()) if len(overlap_diff_bps) else None
            ),
            "p95": (
                float(overlap_diff_bps.quantile(0.95))
                if len(overlap_diff_bps)
                else None
            ),
            "max": (
                float(overlap_diff_bps.max()) if len(overlap_diff_bps) else None
            ),
        },
        "critical_nulls": critical_nulls,
        "duplicate_ts": int(output["ts"].duplicated().sum()),
        "duplicate_nominal_ts": int(
            output["funding_nominal_ts"].duplicated().sum()
        ),
        "sha256": frame_sha256(
            output,
            timestamp_column="ts",
            numeric_columns=["funding_rate", "mark_price"],
        ),
        "blocker_count": int(blockers),
    }
    if blockers:
        raise RuntimeError(f"{symbol} resolved funding quality blockers: {quality}")
    return output, quality


def frame_sha256(
    frame: pd.DataFrame,
    *,
    timestamp_column: str = "ts",
    numeric_columns: list[str] | None = None,
) -> str:
    digest = hashlib.sha256()
    timestamps = (
        pd.to_datetime(frame[timestamp_column], utc=True)
        .to_numpy(dtype="datetime64[ns]")
        .astype("int64")
    )
    digest.update(np.ascontiguousarray(timestamps, dtype="int64").tobytes())
    columns = numeric_columns or [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "vwap",
    ]
    for column in columns:
        values = pd.to_numeric(frame[column], errors="raise").to_numpy(
            dtype="float64"
        )
        digest.update(np.ascontiguousarray(values, dtype="float64").tobytes())
    if "trade_count" in frame.columns:
        counts = pd.to_numeric(frame["trade_count"], errors="raise").to_numpy(
            dtype="int64"
        )
        digest.update(np.ascontiguousarray(counts, dtype="int64").tobytes())
    return digest.hexdigest()


def write_raw_partitions(
    frame: pd.DataFrame,
    *,
    timestamp_column: str,
    kind: DatasetKind,
    symbol: str,
    timeframe: str | None,
    source: str,
    layout: DataLakeLayout,
) -> dict[str, Any]:
    paths: list[Path] = []
    dates = pd.to_datetime(frame[timestamp_column], utc=True).dt.date
    for partition_date, part in frame.groupby(dates, sort=True):
        path = layout.dataset_path(
            layer="raw",
            kind=kind,
            exchange="binance",
            market_type=MarketType.PERP,
            symbol=SYMBOLS[symbol][1],
            timeframe=timeframe,
            source=source,
            partition_date=partition_date,
        )
        paths.append(
            atomic_write_path(
                path,
                lambda temp_path, day=part.reset_index(drop=True): day.to_parquet(
                    temp_path, index=False
                ),
            )
        )
    return {
        "partitions_written": len(paths),
        "first_path": str(paths[0].relative_to(ROOT)),
        "last_path": str(paths[-1].relative_to(ROOT)),
    }


def write_feature(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_path(
        path,
        lambda temp_path: frame.to_parquet(temp_path, index=False),
    )


def process_symbol(
    symbol: str,
    *,
    contract: dict[str, Any],
    cutoff_ms: int,
    generated_at: str,
    timeout: float,
    no_write: bool,
    layout: DataLakeLayout,
) -> dict[str, Any]:
    _, _, slug = SYMBOLS[symbol]
    print(f"[{symbol}] fetching 1h klines", flush=True)
    raw_hourly = fetch_hourly(
        symbol,
        start_ms=int(contract["onboard_date_ms"]),
        cutoff_ms=cutoff_ms,
        timeout=timeout,
    )
    hourly = normalize_hourly(symbol, raw_hourly, generated_at=generated_at)
    hourly_quality = audit_hourly(symbol, raw_hourly, hourly)
    daily, daily_quality = aggregate_daily(
        symbol, hourly, generated_at=generated_at
    )
    print(f"[{symbol}] fetching funding and 1h mark", flush=True)
    raw_funding = fetch_funding(
        symbol,
        start_ms=int(contract["onboard_date_ms"]),
        cutoff_ms=cutoff_ms,
        timeout=timeout,
    )
    raw_mark = fetch_mark(
        symbol,
        start_ms=int(
            raw_funding["ts"].min().floor(MARK_INTERVAL).timestamp() * 1000
        ),
        cutoff_ms=cutoff_ms,
        timeout=timeout,
    )
    mark_quality = audit_mark(symbol, raw_mark)
    funding, funding_quality = resolve_funding(
        symbol, raw_funding, raw_mark, generated_at=generated_at
    )
    development_daily = daily.loc[daily["ts"].lt(SEALED_START)]
    sealed_daily = daily.loc[
        daily["ts"].ge(SEALED_START) & daily["ts"].lt(SEALED_END_EXCLUSIVE)
    ]
    result: dict[str, Any] = {
        "contract": contract,
        "hourly_quality": hourly_quality,
        "daily_quality": daily_quality,
        "daily_sha256": frame_sha256(daily),
        "funding_quality": funding_quality,
        "mark_quality": mark_quality,
        "research_boundaries": {
            "development_daily_rows": int(len(development_daily)),
            "development_start": development_daily["ts"].min().isoformat(),
            "development_end": development_daily["ts"].max().isoformat(),
            "sealed_daily_rows_available_not_consumed_by_p0_model": int(
                len(sealed_daily)
            ),
            "sealed_start": SEALED_START.isoformat(),
            "sealed_end_exclusive": SEALED_END_EXCLUSIVE.isoformat(),
        },
        "write_enabled": not no_write,
    }
    if not no_write:
        result["raw_hourly_write"] = write_raw_partitions(
            raw_hourly,
            timestamp_column="open_time",
            kind=DatasetKind.OHLCV,
            symbol=symbol,
            timeframe="1h",
            source=KLINE_SOURCE,
            layout=layout,
        )
        result["raw_funding_write"] = write_raw_partitions(
            raw_funding,
            timestamp_column="ts",
            kind=DatasetKind.FUNDING_RATES,
            symbol=symbol,
            timeframe=None,
            source=FUNDING_SOURCE,
            layout=layout,
        )
        result["raw_mark_write"] = write_raw_partitions(
            raw_mark,
            timestamp_column="ts",
            kind=DatasetKind.BASIS,
            symbol=symbol,
            timeframe=MARK_INTERVAL,
            source=MARK_SOURCE,
            layout=layout,
        )
        feature_paths = {
            "hourly": FEATURE_DIR / f"{slug}_perp_1h.parquet",
            "daily": FEATURE_DIR / f"{slug}_perp_1d.parquet",
            "funding": FEATURE_DIR / f"{slug}_perp_funding_mark.parquet",
        }
        write_feature(hourly, feature_paths["hourly"])
        write_feature(daily, feature_paths["daily"])
        write_feature(funding, feature_paths["funding"])
        result["feature_paths"] = {
            key: str(path.relative_to(ROOT)) for key, path in feature_paths.items()
        }
    print(
        f"[{symbol}] accepted {len(hourly)} hourly, {len(daily)} daily, "
        f"{len(funding)} funding rows",
        flush=True,
    )
    return result


def main() -> None:
    args = parse_args()
    generated_at = datetime.now(UTC).isoformat()
    cutoff_ms = server_time_ms(args.timeout)
    contracts = fetch_contracts(args.timeout)
    layout = DataLakeLayout.from_settings(load_settings(None))
    if not args.no_write:
        layout.ensure_directories()
    results: dict[str, Any] = {}
    for symbol in args.symbols:
        results[symbol] = process_symbol(
            symbol,
            contract=contracts[symbol],
            cutoff_ms=cutoff_ms,
            generated_at=generated_at,
            timeout=args.timeout,
            no_write=args.no_write,
            layout=layout,
        )
    summary: dict[str, Any] = {
        "generated_at_utc": generated_at,
        "binance_server_time": pd.to_datetime(
            cutoff_ms, unit="ms", utc=True
        ).isoformat(),
        "family": "BIN-1D-MA7-RSI6-DAPML",
        "symbols": args.symbols,
        "source_endpoints": {
            "hourly": "/fapi/v1/klines interval=1h",
            "funding": "/fapi/v1/fundingRate",
            "mark": "/fapi/v1/markPriceKlines interval=1h",
        },
        "sealed_policy": {
            "development_end_inclusive": "2025-08-06T23:59:59.999999999Z",
            "sealed_start": SEALED_START.isoformat(),
            "sealed_end_exclusive": SEALED_END_EXCLUSIVE.isoformat(),
            "p0_model_consumed_sealed_rows": 0,
        },
        "results": results,
        "blocker_count": int(
            sum(
                row["hourly_quality"]["blocker_count"]
                + int(not row["daily_quality"]["audit"]["trusted"])
                + row["funding_quality"]["blocker_count"]
                + row["mark_quality"]["blocker_count"]
                for row in results.values()
            )
        ),
        "write_enabled": not args.no_write,
    }
    if summary["blocker_count"]:
        raise RuntimeError(f"P0 data blockers remain: {summary['blocker_count']}")
    if not args.no_write:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        artifact = ARTIFACT_DIR / "p0_data_quality_manifest.json"
        summary["artifact"] = str(artifact.relative_to(ROOT))
        atomic_write_path(
            artifact,
            lambda temp_path: temp_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            ),
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
