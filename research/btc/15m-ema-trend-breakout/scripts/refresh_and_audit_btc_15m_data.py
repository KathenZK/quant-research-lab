from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http.client import IncompleteRead
from io import BytesIO
import json
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/btc/15m-ema-trend-breakout"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
REPORT_PATH = ARTIFACT_DIR / "btc_binance_15m_data_quality_latest.json"

FAPI = "https://fapi.binance.com"
VISION = "https://data.binance.vision"
USER_AGENT = "quant-research-lab-btc-15m-ema-tb-data/0.1"

SYMBOL = "BTCUSDT"
DISPLAY_SYMBOL = "BTC/USDT:USDT"
BASE_ASSET = "BTC"
QUOTE_ASSET = "USDT"
SYMBOL_SLUG = "btc_usdt_usdt"
TIMEFRAME = "15m"
START = pd.Timestamp("2024-07-14T00:00:00Z")
INTERVAL = pd.Timedelta(minutes=15)
INTERVAL_MS = 15 * 60 * 1000
MAX_FUNDING_GAP_HOURS = 8.01

RAW_OHLCV_ROOT = ROOT / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
NORMALIZED_OHLCV_ROOT = (
    ROOT / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
)
RAW_FUNDING_ROOT = ROOT / "data/raw/funding_rates/exchange=binance/market_type=perp"
NORMALIZED_FUNDING_ROOT = (
    ROOT / "data/normalized/funding_rates/exchange=binance/market_type=perp"
)
COMPAT_FUNDING_PATH = (
    ROOT
    / "data/normalized/funding/exchange=binance/market_type=perp"
    / f"symbol={SYMBOL_SLUG}"
    / "funding.parquet"
)
FUNDING_ARCHIVE_ROOT = (
    ROOT
    / "data/raw/_archives/binance/futures/um/monthly/fundingRate"
    / f"symbol={SYMBOL.lower()}"
)

RAW_KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
]
NORMALIZED_OHLCV_COLUMNS = [
    "ts",
    "exchange",
    "symbol",
    "market_type",
    "timeframe",
    "base_asset",
    "quote_asset",
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
]
RAW_FUNDING_COLUMNS = [
    "source_ts",
    "ts",
    "exchange",
    "symbol",
    "market_type",
    "base_asset",
    "quote_asset",
    "funding_rate",
    "funding_interval_hours",
    "next_funding_ts",
    "mark_price",
    "source",
]
NORMALIZED_FUNDING_COLUMNS = [
    "ts",
    "exchange",
    "symbol",
    "market_type",
    "base_asset",
    "quote_asset",
    "funding_rate",
    "next_funding_ts",
    "mark_price",
    "source",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh and audit Binance USD-M BTCUSDT perpetual 15m OHLCV and "
            "official funding history from 2024-07-14."
        )
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Fetch and audit without writing archives, data-lake partitions, or artifacts.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Per-request HTTP timeout in seconds (default: 60).",
    )
    args = parser.parse_args()
    if not np.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a positive finite number")
    return args


def request_bytes(url: str, *, timeout: float, attempts: int = 7) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except HTTPError:
            raise
        except (URLError, TimeoutError, IncompleteRead, ConnectionError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(min(12.0, 0.75 * 2**attempt))
    raise RuntimeError(
        f"request failed after {attempts} attempts: {url}"
    ) from last_error


def request_json(
    path: str,
    *,
    params: dict[str, object] | None,
    timeout: float,
) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    payload = json.loads(request_bytes(f"{FAPI}{path}{query}", timeout=timeout))
    if isinstance(payload, dict) and "code" in payload and int(payload["code"]) < 0:
        raise RuntimeError(f"Binance API error for {path}: {payload}")
    return payload


def milliseconds(ts: pd.Timestamp) -> int:
    timestamp = pd.Timestamp(ts)
    if timestamp.tzinfo is None:
        raise ValueError(f"timestamp must be timezone-aware: {timestamp}")
    return int(timestamp.tz_convert("UTC").timestamp() * 1000)


def binance_server_time(timeout: float) -> pd.Timestamp:
    payload = request_json("/fapi/v1/time", params=None, timeout=timeout)
    if not isinstance(payload, dict) or "serverTime" not in payload:
        raise RuntimeError(f"unexpected Binance server-time response: {payload!r}")
    return pd.to_datetime(int(payload["serverTime"]), unit="ms", utc=True)


def fetch_klines(
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    timeout: float,
) -> pd.DataFrame:
    rows: list[list[Any]] = []
    cursor = milliseconds(start)
    end_ms = milliseconds(end)
    while cursor < end_ms:
        payload = request_json(
            "/fapi/v1/klines",
            params={
                "symbol": SYMBOL,
                "interval": TIMEFRAME,
                "startTime": cursor,
                "endTime": end_ms - 1,
                "limit": 1500,
            },
            timeout=timeout,
        )
        if not isinstance(payload, list):
            raise RuntimeError(f"unexpected Binance kline response: {payload!r}")
        if not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1][0]) + INTERVAL_MS
        if next_cursor <= cursor:
            raise RuntimeError("BTCUSDT 15m kline pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1500:
            break
        time.sleep(0.03)
    if not rows:
        raise RuntimeError("Binance returned no BTCUSDT perpetual 15m klines")

    raw = pd.DataFrame(rows, columns=RAW_KLINE_COLUMNS)
    raw["open_time"] = pd.to_datetime(raw["open_time"], unit="ms", utc=True)
    raw["close_time"] = pd.to_datetime(raw["close_time"], unit="ms", utc=True)
    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_volume",
        "taker_buy_quote_volume",
    ]:
        raw[column] = pd.to_numeric(raw[column], errors="coerce")
    raw["source"] = "binance_futures_kline_api"
    raw["is_closed"] = raw["close_time"] < end
    return (
        raw.loc[
            (raw["open_time"] >= start) & (raw["open_time"] < end) & raw["is_closed"]
        ]
        .sort_values("open_time")
        .reset_index(drop=True)
    )


def normalize_klines(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.rename(columns={"open_time": "ts"}).copy()
    frame["exchange"] = "binance"
    frame["symbol"] = DISPLAY_SYMBOL
    frame["market_type"] = "perp"
    frame["timeframe"] = TIMEFRAME
    frame["base_asset"] = BASE_ASSET
    frame["quote_asset"] = QUOTE_ASSET
    frame["vwap"] = frame["quote_volume"] / frame["volume"].replace(0.0, np.nan)
    frame["vwap"] = frame["vwap"].fillna(frame["close"])
    return frame[NORMALIZED_OHLCV_COLUMNS].reset_index(drop=True)


def month_starts(
    start: pd.Timestamp,
    last_complete_month: pd.Timestamp,
) -> list[pd.Timestamp]:
    current = pd.Timestamp(year=start.year, month=start.month, day=1, tz="UTC")
    last = pd.Timestamp(
        year=last_complete_month.year,
        month=last_complete_month.month,
        day=1,
        tz="UTC",
    )
    months: list[pd.Timestamp] = []
    while current <= last:
        months.append(current)
        current += pd.offsets.MonthBegin(1)
    return months


def funding_archive_locations(
    month: pd.Timestamp,
) -> tuple[Path, Path, str, str]:
    stamp = month.strftime("%Y-%m")
    filename = f"{SYMBOL}-fundingRate-{stamp}.zip"
    directory = FUNDING_ARCHIVE_ROOT / f"year={month.year}"
    base_url = f"{VISION}/data/futures/um/monthly/fundingRate/{SYMBOL}/{filename}"
    return (
        directory / filename,
        directory / f"{filename}.CHECKSUM",
        base_url,
        f"{base_url}.CHECKSUM",
    )


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def verified_archive_bytes(
    month: pd.Timestamp,
    *,
    timeout: float,
    no_write: bool,
) -> tuple[bytes, str, str]:
    archive_path, checksum_path, archive_url, checksum_url = funding_archive_locations(
        month
    )
    if archive_path.exists() and checksum_path.exists():
        payload = archive_path.read_bytes()
        checksum_text = checksum_path.read_text(encoding="utf-8")
        location = "local_verified_archive"
    else:
        payload = request_bytes(archive_url, timeout=timeout)
        checksum_text = request_bytes(checksum_url, timeout=timeout).decode("utf-8")
        location = "downloaded_no_write" if no_write else "downloaded_and_archived"

    checksum_tokens = checksum_text.strip().split()
    if not checksum_tokens:
        raise RuntimeError(f"empty CHECKSUM for BTCUSDT funding archive {month:%Y-%m}")
    expected = checksum_tokens[0].lower()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise RuntimeError(
            f"BTCUSDT funding archive checksum mismatch for {month:%Y-%m}: "
            f"expected {expected}, got {actual}"
        )
    if not no_write and not (archive_path.exists() and checksum_path.exists()):
        atomic_write_bytes(archive_path, payload)
        atomic_write_text(checksum_path, checksum_text)
    return payload, actual, location


def infer_epoch_unit(values: pd.Series) -> str:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        raise RuntimeError("cannot infer timestamp unit from empty funding timestamps")
    magnitude = float(numeric.abs().median())
    return "us" if magnitude >= 100_000_000_000_000 else "ms"


def parse_funding_archive(
    month: pd.Timestamp,
    *,
    timeout: float,
    no_write: bool,
) -> tuple[pd.DataFrame, dict[str, str]]:
    payload, checksum, location = verified_archive_bytes(
        month,
        timeout=timeout,
        no_write=no_write,
    )
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RuntimeError(
                f"corrupt BTCUSDT funding archive member for {month:%Y-%m}: "
                f"{bad_member}"
            )
        members = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(members) != 1:
            raise RuntimeError(
                f"unexpected BTCUSDT funding archive members for {month:%Y-%m}: "
                f"{members}"
            )
        with archive.open(members[0]) as handle:
            frame = pd.read_csv(handle)

    required = {"calc_time", "funding_interval_hours", "last_funding_rate"}
    missing = required - set(frame.columns)
    if missing:
        raise RuntimeError(
            f"BTCUSDT funding archive {month:%Y-%m} missing columns: {sorted(missing)}"
        )
    epoch_unit = infer_epoch_unit(frame["calc_time"])
    frame["source_ts"] = pd.to_datetime(
        pd.to_numeric(frame["calc_time"], errors="coerce"),
        unit=epoch_unit,
        utc=True,
    )
    frame["ts"] = frame["source_ts"].dt.round("s")
    frame["funding_rate"] = pd.to_numeric(
        frame["last_funding_rate"],
        errors="coerce",
    )
    frame["funding_interval_hours"] = pd.to_numeric(
        frame["funding_interval_hours"],
        errors="coerce",
    )
    frame["mark_price"] = np.nan
    frame["source"] = "binance_vision_funding_archive"
    columns = [
        "source_ts",
        "ts",
        "funding_rate",
        "funding_interval_hours",
        "mark_price",
        "source",
    ]
    return frame[columns], {
        "sha256": checksum,
        "archive_access": location,
        "timestamp_unit": epoch_unit,
    }


def fetch_funding_api_tail(
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    timeout: float,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    cursor = milliseconds(start)
    end_ms = milliseconds(end)
    while cursor <= end_ms:
        payload = request_json(
            "/fapi/v1/fundingRate",
            params={
                "symbol": SYMBOL,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1000,
            },
            timeout=timeout,
        )
        if not isinstance(payload, list):
            raise RuntimeError(f"unexpected Binance funding response: {payload!r}")
        if not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise RuntimeError("BTCUSDT funding pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1000:
            break
        time.sleep(0.03)

    columns = [
        "source_ts",
        "ts",
        "funding_rate",
        "funding_interval_hours",
        "mark_price",
        "source",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(rows)
    frame["source_ts"] = pd.to_datetime(frame["fundingTime"], unit="ms", utc=True)
    frame["ts"] = frame["source_ts"].dt.round("s")
    frame["funding_rate"] = pd.to_numeric(frame["fundingRate"], errors="coerce")
    frame["funding_interval_hours"] = np.nan
    if "markPrice" in frame:
        frame["mark_price"] = pd.to_numeric(frame["markPrice"], errors="coerce")
    else:
        frame["mark_price"] = np.nan
    frame["source"] = "binance_futures_funding_rate_api"
    return frame[columns]


def build_funding(
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    timeout: float,
    no_write: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    current_month = pd.Timestamp(year=end.year, month=end.month, day=1, tz="UTC")
    last_complete_month = current_month - pd.offsets.MonthBegin(1)
    pieces: list[pd.DataFrame] = []
    archive_metadata: dict[str, dict[str, str]] = {}
    for month in month_starts(start, last_complete_month):
        frame, metadata = parse_funding_archive(
            month,
            timeout=timeout,
            no_write=no_write,
        )
        pieces.append(frame)
        archive_metadata[month.strftime("%Y-%m")] = metadata

    api_start = max(start, current_month)
    pieces.append(fetch_funding_api_tail(start=api_start, end=end, timeout=timeout))
    if not pieces:
        raise RuntimeError("no BTCUSDT funding sources were assembled")
    combined = pd.concat(pieces, ignore_index=True, sort=False)
    combined = combined.loc[(combined["ts"] >= start) & (combined["ts"] < end)].copy()
    combined["source_priority"] = combined["source"].map(
        {
            "binance_vision_funding_archive": 0,
            "binance_futures_funding_rate_api": 1,
        }
    )
    combined = (
        combined.sort_values(["ts", "source_priority"])
        .drop_duplicates("ts", keep="last")
        .drop(columns="source_priority")
        .sort_values("ts")
        .reset_index(drop=True)
    )
    if combined.empty:
        raise RuntimeError("assembled BTCUSDT funding history is empty")
    return combined, {
        "official_archive_months": len(archive_metadata),
        "official_archive_metadata": archive_metadata,
        "api_tail_start": api_start.isoformat(),
    }


def enrich_funding(
    funding: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    enriched = funding.copy()
    enriched["exchange"] = "binance"
    enriched["symbol"] = DISPLAY_SYMBOL
    enriched["market_type"] = "perp"
    enriched["base_asset"] = BASE_ASSET
    enriched["quote_asset"] = QUOTE_ASSET
    enriched["next_funding_ts"] = enriched["ts"].shift(-1)
    raw = enriched[RAW_FUNDING_COLUMNS].reset_index(drop=True)
    normalized = enriched[NORMALIZED_FUNDING_COLUMNS].reset_index(drop=True)
    return raw, normalized


def timezone_is_utc(series: pd.Series) -> bool:
    timezone_value = getattr(series.dt, "tz", None)
    return timezone_value is not None and str(timezone_value) == "UTC"


def numeric_equal(left: pd.Series, right: pd.Series) -> bool:
    return bool(
        np.allclose(
            pd.to_numeric(left, errors="coerce"),
            pd.to_numeric(right, errors="coerce"),
            rtol=0.0,
            atol=1e-12,
            equal_nan=True,
        )
    )


def value_equal(left: pd.Series, right: pd.Series) -> bool:
    left_values = left.reset_index(drop=True)
    right_values = right.reset_index(drop=True)
    return bool(left_values.equals(right_values))


def audit_ohlcv(
    raw: pd.DataFrame,
    normalized: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    expected = pd.date_range(start, end - INTERVAL, freq=INTERVAL)
    actual = pd.DatetimeIndex(normalized["ts"])
    missing = expected.difference(actual)
    extra = actual.difference(expected)

    raw_critical = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_volume",
        "trade_count",
        "source",
        "is_closed",
    ]
    normalized_critical = NORMALIZED_OHLCV_COLUMNS
    raw_null_rows = int(raw[raw_critical].isna().any(axis=1).sum())
    normalized_null_rows = int(normalized[normalized_critical].isna().any(axis=1).sum())
    raw_duplicates = int(raw.duplicated("open_time").sum())
    normalized_duplicates = int(normalized.duplicated("ts").sum())

    violations = {
        "high_below_open_or_close": int(
            (normalized["high"] < normalized[["open", "close"]].max(axis=1)).sum()
        ),
        "low_above_open_or_close": int(
            (normalized["low"] > normalized[["open", "close"]].min(axis=1)).sum()
        ),
        "high_below_low": int((normalized["high"] < normalized["low"]).sum()),
        "nonpositive_ohlc": int(
            ((normalized[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum()
        ),
        "negative_volume": int((normalized["volume"] < 0).sum()),
        "negative_quote_volume": int((normalized["quote_volume"] < 0).sum()),
        "negative_trade_count": int((normalized["trade_count"] < 0).sum()),
        "nonpositive_vwap": int((normalized["vwap"] <= 0).sum()),
    }

    expected_vwap = raw["quote_volume"] / raw["volume"].replace(0.0, np.nan)
    expected_vwap = expected_vwap.fillna(raw["close"])
    column_checks = {
        "ts": value_equal(raw["open_time"], normalized["ts"]),
        "exchange": bool((normalized["exchange"] == "binance").all()),
        "symbol": bool((normalized["symbol"] == DISPLAY_SYMBOL).all()),
        "market_type": bool((normalized["market_type"] == "perp").all()),
        "timeframe": bool((normalized["timeframe"] == TIMEFRAME).all()),
        "base_asset": bool((normalized["base_asset"] == BASE_ASSET).all()),
        "quote_asset": bool((normalized["quote_asset"] == QUOTE_ASSET).all()),
        "open": numeric_equal(raw["open"], normalized["open"]),
        "high": numeric_equal(raw["high"], normalized["high"]),
        "low": numeric_equal(raw["low"], normalized["low"]),
        "close": numeric_equal(raw["close"], normalized["close"]),
        "volume": numeric_equal(raw["volume"], normalized["volume"]),
        "quote_volume": numeric_equal(
            raw["quote_volume"],
            normalized["quote_volume"],
        ),
        "trade_count": numeric_equal(
            raw["trade_count"],
            normalized["trade_count"],
        ),
        "vwap": numeric_equal(expected_vwap, normalized["vwap"]),
        "is_closed": value_equal(raw["is_closed"], normalized["is_closed"]),
        "source": value_equal(raw["source"], normalized["source"]),
    }
    utc_checks = {
        "raw_open_time_utc": timezone_is_utc(raw["open_time"]),
        "raw_close_time_utc": timezone_is_utc(raw["close_time"]),
        "normalized_ts_utc": timezone_is_utc(normalized["ts"]),
    }
    closed_checks = {
        "all_raw_closed": bool(raw["is_closed"].all()),
        "all_normalized_closed": bool(normalized["is_closed"].all()),
        "raw_flag_matches_close_time": bool(
            raw["is_closed"].equals(raw["close_time"] < end)
        ),
        "last_bar_is_latest_closed": bool(
            not normalized.empty and normalized["ts"].iloc[-1] == end - INTERVAL
        ),
    }

    blocker_count = (
        len(missing)
        + len(extra)
        + raw_duplicates
        + normalized_duplicates
        + raw_null_rows
        + normalized_null_rows
        + sum(violations.values())
        + sum(not passed for passed in column_checks.values())
        + sum(not passed for passed in utc_checks.values())
        + sum(not passed for passed in closed_checks.values())
    )
    return {
        "rows": int(len(normalized)),
        "expected_rows": int(len(expected)),
        "first_ts": (
            normalized["ts"].iloc[0].isoformat() if not normalized.empty else None
        ),
        "last_ts": (
            normalized["ts"].iloc[-1].isoformat() if not normalized.empty else None
        ),
        "missing_bars": int(len(missing)),
        "missing_examples": [ts.isoformat() for ts in missing[:10]],
        "extra_bars": int(len(extra)),
        "extra_examples": [ts.isoformat() for ts in extra[:10]],
        "raw_duplicate_bars": raw_duplicates,
        "normalized_duplicate_bars": normalized_duplicates,
        "raw_critical_null_rows": raw_null_rows,
        "normalized_critical_null_rows": normalized_null_rows,
        "ohlcv_violations": violations,
        "utc_checks": utc_checks,
        "is_closed_checks": closed_checks,
        "raw_normalized_column_checks": column_checks,
        "blocker_count": int(blocker_count),
    }


def audit_funding(
    source: pd.DataFrame,
    raw: pd.DataFrame,
    normalized: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    gaps = source["ts"].diff().dropna()
    first_delay_hours = (source["ts"].iloc[0] - start).total_seconds() / 3600.0
    tail_age_hours = (end - source["ts"].iloc[-1]).total_seconds() / 3600.0
    max_gap_hours = float(gaps.max().total_seconds() / 3600.0) if len(gaps) else 0.0
    duplicate_rows = int(source.duplicated("ts").sum())
    critical_columns = ["source_ts", "ts", "funding_rate", "source"]
    critical_null_rows = int(source[critical_columns].isna().any(axis=1).sum())

    common_numeric = ["funding_rate", "mark_price"]
    common_exact = [
        "ts",
        "exchange",
        "symbol",
        "market_type",
        "base_asset",
        "quote_asset",
        "next_funding_ts",
        "source",
    ]
    column_checks = {
        column: numeric_equal(raw[column], normalized[column])
        for column in common_numeric
    }
    column_checks.update(
        {
            column: value_equal(raw[column], normalized[column])
            for column in common_exact
        }
    )
    utc_checks = {
        "source_ts_utc": timezone_is_utc(source["source_ts"]),
        "ts_utc": timezone_is_utc(source["ts"]),
    }
    interval_checks = {
        "first_event_within_max_interval": first_delay_hours <= MAX_FUNDING_GAP_HOURS,
        "max_gap_within_limit": max_gap_hours <= MAX_FUNDING_GAP_HOURS,
        "latest_event_fresh": tail_age_hours <= MAX_FUNDING_GAP_HOURS,
    }
    invalid_interval_rows = int(
        (
            source["funding_interval_hours"].notna()
            & (
                (source["funding_interval_hours"] <= 0)
                | (source["funding_interval_hours"] > MAX_FUNDING_GAP_HOURS)
            )
        ).sum()
    )
    blocker_count = (
        duplicate_rows
        + critical_null_rows
        + invalid_interval_rows
        + sum(not passed for passed in column_checks.values())
        + sum(not passed for passed in utc_checks.values())
        + sum(not passed for passed in interval_checks.values())
    )
    return {
        "rows": int(len(source)),
        "first_ts": source["ts"].iloc[0].isoformat(),
        "last_ts": source["ts"].iloc[-1].isoformat(),
        "first_delay_hours": float(first_delay_hours),
        "tail_age_hours": float(tail_age_hours),
        "max_gap_hours": max_gap_hours,
        "allowed_max_gap_hours": MAX_FUNDING_GAP_HOURS,
        "duplicate_rows": duplicate_rows,
        "critical_null_rows": critical_null_rows,
        "invalid_declared_interval_rows": invalid_interval_rows,
        "mark_price_null_rows": int(source["mark_price"].isna().sum()),
        "source_counts": {
            str(key): int(value)
            for key, value in source["source"].value_counts().items()
        },
        "utc_checks": utc_checks,
        "interval_checks": interval_checks,
        "raw_normalized_column_checks": column_checks,
        "blocker_count": int(blocker_count),
    }


def atomic_write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.parquet")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def write_daily_partitions(
    root: Path,
    *,
    timestamp_column: str,
    frame: pd.DataFrame,
) -> int:
    work = frame.copy()
    work["partition_date"] = work[timestamp_column].dt.date.astype(str)
    partition_count = 0
    for date, group in work.groupby("partition_date", sort=True):
        path = root / f"date={date}" / f"symbol={SYMBOL_SLUG}.parquet"
        atomic_write_parquet(path, group.drop(columns="partition_date"))
        partition_count += 1
    return partition_count


def write_data_lake(
    raw_ohlcv: pd.DataFrame,
    normalized_ohlcv: pd.DataFrame,
    raw_funding: pd.DataFrame,
    normalized_funding: pd.DataFrame,
) -> dict[str, Any]:
    raw_ohlcv_count = write_daily_partitions(
        RAW_OHLCV_ROOT,
        timestamp_column="open_time",
        frame=raw_ohlcv,
    )
    normalized_ohlcv_count = write_daily_partitions(
        NORMALIZED_OHLCV_ROOT,
        timestamp_column="ts",
        frame=normalized_ohlcv,
    )
    raw_funding_count = write_daily_partitions(
        RAW_FUNDING_ROOT,
        timestamp_column="ts",
        frame=raw_funding,
    )
    normalized_funding_count = write_daily_partitions(
        NORMALIZED_FUNDING_ROOT,
        timestamp_column="ts",
        frame=normalized_funding,
    )
    compatibility = normalized_funding[["ts", "funding_rate", "mark_price", "source"]]
    atomic_write_parquet(COMPAT_FUNDING_PATH, compatibility)
    return {
        "raw_ohlcv_partitions": raw_ohlcv_count,
        "normalized_ohlcv_partitions": normalized_ohlcv_count,
        "raw_funding_partitions": raw_funding_count,
        "normalized_funding_partitions": normalized_funding_count,
        "compatibility_funding_file": str(COMPAT_FUNDING_PATH.relative_to(ROOT)),
    }


def report_base(*, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "no-write" if args.no_write else "write",
        "market": "Binance USD-M Futures perpetual",
        "exchange": "binance",
        "symbol": SYMBOL,
        "display_symbol": DISPLAY_SYMBOL,
        "timeframe": TIMEFRAME,
        "research_start": START.isoformat(),
        "funding_source": (
            "Binance Vision official monthly fundingRate archives plus "
            "Binance FAPI fundingRate tail"
        ),
        "standard_data_targets": {
            "raw_ohlcv_root": str(RAW_OHLCV_ROOT.relative_to(ROOT)),
            "normalized_ohlcv_root": str(NORMALIZED_OHLCV_ROOT.relative_to(ROOT)),
            "raw_funding_root": str(RAW_FUNDING_ROOT.relative_to(ROOT)),
            "normalized_funding_root": str(NORMALIZED_FUNDING_ROOT.relative_to(ROOT)),
            "compatibility_funding_file": str(COMPAT_FUNDING_PATH.relative_to(ROOT)),
        },
        "writes": {
            "performed": False,
            "reason": "not started",
        },
        "fatal_errors": [],
        "total_blocker_count": 0,
    }


def persist_or_print_report(
    report: dict[str, Any],
    *,
    no_write: bool,
) -> None:
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if not no_write:
        atomic_write_text(REPORT_PATH, rendered + "\n")
    print(rendered, flush=True)


def main() -> None:
    args = parse_args()
    report = report_base(args=args)
    try:
        server_time = binance_server_time(args.timeout)
        cutoff = server_time.floor("15min")
        if cutoff <= START:
            raise RuntimeError(
                "Binance closed-bar cutoff is not after the research start"
            )
        report["binance_server_time"] = server_time.isoformat()
        report["closed_bar_cutoff_exclusive"] = cutoff.isoformat()

        raw_ohlcv = fetch_klines(
            start=START,
            end=cutoff,
            timeout=args.timeout,
        )
        normalized_ohlcv = normalize_klines(raw_ohlcv)
        funding_source, funding_metadata = build_funding(
            start=START,
            end=cutoff,
            timeout=args.timeout,
            no_write=args.no_write,
        )
        raw_funding, normalized_funding = enrich_funding(funding_source)

        ohlcv_quality = audit_ohlcv(
            raw_ohlcv,
            normalized_ohlcv,
            start=START,
            end=cutoff,
        )
        funding_quality = audit_funding(
            funding_source,
            raw_funding,
            normalized_funding,
            start=START,
            end=cutoff,
        )
        total_blockers = int(
            ohlcv_quality["blocker_count"] + funding_quality["blocker_count"]
        )
        report["funding_retrieval"] = funding_metadata
        report["ohlcv_quality"] = ohlcv_quality
        report["funding_quality"] = funding_quality
        report["total_blocker_count"] = total_blockers

        if args.no_write:
            report["writes"] = {
                "performed": False,
                "reason": "--no-write",
            }
        elif total_blockers:
            report["writes"] = {
                "performed": False,
                "reason": "data-quality blockers prevent standard data-lake refresh",
            }
        else:
            write_counts = write_data_lake(
                raw_ohlcv,
                normalized_ohlcv,
                raw_funding,
                normalized_funding,
            )
            report["writes"] = {
                "performed": True,
                "reason": "all data-quality gates passed",
                **write_counts,
            }
    except Exception as exc:
        report["fatal_errors"].append(
            {
                "type": type(exc).__name__,
                "message": str(exc),
            }
        )
        report["total_blocker_count"] = max(
            1,
            int(report.get("total_blocker_count", 0)),
        )
        report["writes"] = {
            "performed": False,
            "reason": "fatal refresh or audit error",
        }

    persist_or_print_report(report, no_write=args.no_write)
    if report["total_blocker_count"]:
        raise RuntimeError(
            f"BTCUSDT 15m data-quality blockers remain: {report['total_blocker_count']}"
        )


if __name__ == "__main__":
    main()
