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
FAMILY_DIR = ROOT / "research/hype/15m-factor-ml"
ARTIFACT_DIR = FAMILY_DIR / "artifacts/data_quality"

FAPI = "https://fapi.binance.com"
VISION = "https://data.binance.vision"
USER_AGENT = "quant-research-lab-hype-15m-factor-ml-data/0.2"

SYMBOL = "HYPEUSDT"
DISPLAY_SYMBOL = "HYPE/USDT:USDT"
SLUG = "hype_usdt_usdt"
TIMEFRAME = "15m"
INTERVAL_MS = 15 * 60 * 1000

RAW_OHLCV_ROOT = ROOT / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
NORMALIZED_OHLCV_ROOT = ROOT / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
RAW_MARK_ROOT = ROOT / "data/raw/mark_price_klines/exchange=binance/market_type=perp/timeframe=15m"
NORMALIZED_MARK_ROOT = ROOT / "data/normalized/mark_price_klines/exchange=binance/market_type=perp/timeframe=15m"
RAW_FUNDING_ROOT = ROOT / "data/raw/funding_rates/exchange=binance/market_type=perp"
NORMALIZED_FUNDING_ROOT = ROOT / "data/normalized/funding_rates/exchange=binance/market_type=perp"
COMPAT_FUNDING_PATH = (
    ROOT
    / "data/normalized/funding/exchange=binance/market_type=perp"
    / f"symbol={SLUG}/funding.parquet"
)
ARCHIVE_ROOT = (
    ROOT
    / "data/raw/_archives/binance/futures/um/monthly/fundingRate"
    / f"symbol={SYMBOL.lower()}"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh and hard-audit HYPEUSDT perpetual 15m market data."
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--cutoff",
        type=str,
        default=None,
        help="Optional exclusive UTC 15m cutoff used to reproduce a locked research snapshot.",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Run remote and local audits without replacing data-lake partitions.",
    )
    return parser.parse_args()


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
    raise RuntimeError(f"request failed after {attempts} attempts: {url}") from last_error


def request_json(
    path: str,
    *,
    params: dict[str, object] | None,
    timeout: float,
) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    return json.loads(request_bytes(f"{FAPI}{path}{query}", timeout=timeout))


def millis(ts: pd.Timestamp) -> int:
    return int(pd.Timestamp(ts).tz_convert("UTC").timestamp() * 1000)


def contract_snapshot(timeout: float) -> dict[str, Any]:
    payload = request_json("/fapi/v1/exchangeInfo", params=None, timeout=timeout)
    matches = [row for row in payload.get("symbols", []) if row.get("symbol") == SYMBOL]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {SYMBOL} exchangeInfo row, got {len(matches)}")
    row = matches[0]
    filters = {item["filterType"]: item for item in row.get("filters", [])}
    return {
        "symbol": SYMBOL,
        "status": row.get("status"),
        "contract_type": row.get("contractType"),
        "onboard_date": pd.to_datetime(row["onboardDate"], unit="ms", utc=True).isoformat(),
        "price_precision": row.get("pricePrecision"),
        "quantity_precision": row.get("quantityPrecision"),
        "price_filter": filters.get("PRICE_FILTER"),
        "lot_size": filters.get("LOT_SIZE"),
        "market_lot_size": filters.get("MARKET_LOT_SIZE"),
        "min_notional": filters.get("MIN_NOTIONAL"),
    }


def fetch_candles(
    path: str,
    *,
    start: pd.Timestamp,
    cutoff: pd.Timestamp,
    timeout: float,
) -> pd.DataFrame:
    rows: list[list[Any]] = []
    cursor = millis(start)
    end_ms = millis(cutoff)
    while cursor < end_ms:
        payload = request_json(
            path,
            params={
                "symbol": SYMBOL,
                "interval": TIMEFRAME,
                "startTime": cursor,
                "endTime": end_ms - 1,
                "limit": 1500,
            },
            timeout=timeout,
        )
        if not isinstance(payload, list) or not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1][0]) + INTERVAL_MS
        if next_cursor <= cursor:
            raise RuntimeError(f"{path} pagination stopped advancing")
        cursor = next_cursor
        time.sleep(0.03)
    if not rows:
        raise RuntimeError(f"no HYPEUSDT candles returned by {path}")
    columns = [
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
    frame = pd.DataFrame(rows, columns=columns)
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
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
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["is_closed"] = frame["close_time"] < cutoff
    return (
        frame.loc[
            (frame["open_time"] >= start)
            & (frame["open_time"] < cutoff)
            & frame["is_closed"]
        ]
        .drop_duplicates("open_time", keep="last")
        .sort_values("open_time")
        .reset_index(drop=True)
    )


def normalize_ohlcv(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.rename(columns={"open_time": "ts"}).copy()
    frame["exchange"] = "binance"
    frame["symbol"] = DISPLAY_SYMBOL
    frame["market_type"] = "perp"
    frame["timeframe"] = TIMEFRAME
    frame["base_asset"] = "HYPE"
    frame["quote_asset"] = "USDT"
    frame["vwap"] = frame["quote_volume"] / frame["volume"].replace(0.0, np.nan)
    frame["vwap"] = frame["vwap"].fillna(frame["close"])
    frame["source"] = "binance_futures_kline_api"
    return frame[
        [
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
            "taker_buy_volume",
            "taker_buy_quote_volume",
            "vwap",
            "is_closed",
            "source",
        ]
    ]


def normalize_mark(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.rename(columns={"open_time": "ts"}).copy()
    frame["exchange"] = "binance"
    frame["symbol"] = DISPLAY_SYMBOL
    frame["market_type"] = "perp"
    frame["timeframe"] = TIMEFRAME
    frame["source"] = "binance_mark_price_klines"
    return frame[
        [
            "ts",
            "exchange",
            "symbol",
            "market_type",
            "timeframe",
            "open",
            "high",
            "low",
            "close",
            "is_closed",
            "source",
        ]
    ]


def completed_months(start: pd.Timestamp, cutoff: pd.Timestamp) -> list[pd.Timestamp]:
    current = pd.Timestamp(year=start.year, month=start.month, day=1, tz="UTC")
    current_month = pd.Timestamp(year=cutoff.year, month=cutoff.month, day=1, tz="UTC")
    final = current_month - pd.offsets.MonthBegin(1)
    result: list[pd.Timestamp] = []
    while current <= final:
        result.append(current)
        current += pd.offsets.MonthBegin(1)
    return result


def archive_locations(month: pd.Timestamp) -> tuple[Path, Path, str, str]:
    stamp = month.strftime("%Y-%m")
    name = f"{SYMBOL}-fundingRate-{stamp}.zip"
    directory = ARCHIVE_ROOT / f"year={month.year}"
    url = f"{VISION}/data/futures/um/monthly/fundingRate/{SYMBOL}/{name}"
    return directory / name, directory / f"{name}.CHECKSUM", url, f"{url}.CHECKSUM"


def read_funding_archive(month: pd.Timestamp, timeout: float) -> tuple[pd.DataFrame, str]:
    archive_path, checksum_path, archive_url, checksum_url = archive_locations(month)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists() and checksum_path.exists():
        payload = archive_path.read_bytes()
        checksum_text = checksum_path.read_text(encoding="utf-8")
    else:
        payload = request_bytes(archive_url, timeout=timeout)
        checksum_text = request_bytes(checksum_url, timeout=timeout).decode("utf-8")
        archive_path.write_bytes(payload)
        checksum_path.write_text(checksum_text, encoding="utf-8")
    expected = checksum_text.strip().split()[0].lower()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise RuntimeError(f"funding archive checksum mismatch for {month:%Y-%m}")
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        if archive.testzip() is not None:
            raise RuntimeError(f"corrupt funding archive for {month:%Y-%m}")
        names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(names) != 1:
            raise RuntimeError(f"unexpected funding archive members: {names}")
        with archive.open(names[0]) as handle:
            frame = pd.read_csv(handle)
    required = {"calc_time", "funding_interval_hours", "last_funding_rate"}
    if missing := required - set(frame.columns):
        raise RuntimeError(f"funding archive missing columns: {sorted(missing)}")
    frame["source_ts"] = pd.to_datetime(frame["calc_time"], unit="ms", utc=True)
    frame["ts"] = frame["source_ts"].dt.round("s")
    frame["funding_rate"] = pd.to_numeric(frame["last_funding_rate"], errors="coerce")
    frame["funding_interval_hours"] = pd.to_numeric(
        frame["funding_interval_hours"], errors="coerce"
    )
    frame["mark_price"] = np.nan
    frame["source"] = "binance_vision_funding_archive"
    frame["archive_month"] = month.strftime("%Y-%m")
    frame["archive_sha256"] = actual
    return (
        frame[
            [
                "source_ts",
                "ts",
                "funding_rate",
                "funding_interval_hours",
                "mark_price",
                "source",
                "archive_month",
                "archive_sha256",
            ]
        ],
        actual,
    )


def fetch_funding_api(
    *,
    start: pd.Timestamp,
    cutoff: pd.Timestamp,
    timeout: float,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    cursor = millis(start)
    end_ms = millis(cutoff)
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
        if not isinstance(payload, list) or not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise RuntimeError("funding API pagination stopped advancing")
        cursor = next_cursor
        time.sleep(0.03)
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("funding API returned no HYPEUSDT rows")
    frame["source_ts"] = pd.to_datetime(frame["fundingTime"], unit="ms", utc=True)
    frame["ts"] = frame["source_ts"].dt.round("s")
    frame["funding_rate"] = pd.to_numeric(frame["fundingRate"], errors="coerce")
    frame["mark_price"] = pd.to_numeric(frame.get("markPrice"), errors="coerce")
    frame["funding_interval_hours"] = np.nan
    frame["source"] = "binance_futures_funding_rate_api"
    frame["archive_month"] = pd.NA
    frame["archive_sha256"] = pd.NA
    return (
        frame[
            [
                "source_ts",
                "ts",
                "funding_rate",
                "funding_interval_hours",
                "mark_price",
                "source",
                "archive_month",
                "archive_sha256",
            ]
        ]
        .drop_duplicates("ts", keep="last")
        .sort_values("ts")
        .reset_index(drop=True)
    )


def combine_funding(
    archive: pd.DataFrame,
    api: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    comparison = archive[["ts", "funding_rate"]].merge(
        api[["ts", "funding_rate", "mark_price", "source_ts"]],
        on="ts",
        how="left",
        suffixes=("_archive", "_api"),
        validate="one_to_one",
    )
    missing_from_api = int(comparison["funding_rate_api"].isna().sum())
    rate_mismatches = int(
        (
            ~np.isclose(
                comparison["funding_rate_archive"].to_numpy(dtype="float64"),
                comparison["funding_rate_api"].to_numpy(dtype="float64"),
                rtol=0.0,
                atol=1e-12,
                equal_nan=False,
            )
        ).sum()
    )
    if missing_from_api or rate_mismatches:
        raise RuntimeError(
            "funding archive/API cross-check failed: "
            f"missing={missing_from_api}, rate_mismatches={rate_mismatches}"
        )

    api_lookup = api.set_index("ts")
    archive_primary = archive.copy()
    archive_primary["mark_price"] = archive_primary["ts"].map(api_lookup["mark_price"])
    archive_primary["verified_by_api"] = True
    archive_primary["verification_source_ts"] = archive_primary["ts"].map(
        api_lookup["source_ts"]
    )
    api_only = api.loc[~api["ts"].isin(archive_primary["ts"])].copy()
    api_only["verified_by_api"] = True
    api_only["verification_source_ts"] = api_only["source_ts"]
    combined = (
        pd.concat([archive_primary, api_only], ignore_index=True, sort=False)
        .sort_values("ts")
        .drop_duplicates("ts", keep="first")
        .reset_index(drop=True)
    )
    combined["funding_interval_hours"] = combined["funding_interval_hours"].fillna(
        combined["ts"].diff().dt.total_seconds().div(3600.0)
    )
    combined["next_funding_ts"] = combined["ts"].shift(-1)
    return combined, {
        "archive_rows": int(len(archive)),
        "api_rows": int(len(api)),
        "archive_rows_missing_from_api": missing_from_api,
        "archive_api_rate_mismatches": rate_mismatches,
        "api_only_rows": int(len(api_only)),
        "combined_source_counts": {
            str(key): int(value)
            for key, value in combined["source"].value_counts(dropna=False).items()
        },
    }


def fetch_limited_history(
    path: str,
    *,
    base_params: dict[str, object],
    cutoff: pd.Timestamp,
    timeout: float,
) -> pd.DataFrame:
    # Binance documents these endpoints as retaining only the latest 30 days.
    start = cutoff - pd.Timedelta(days=29, hours=23)
    rows: list[dict[str, Any]] = []
    window_start = start
    # Keep each request below the 500-row endpoint cap.  These endpoints may
    # return the newest 500 rows rather than page forward when a wider range is
    # supplied, so explicit non-overlapping windows are required.
    window_span = pd.Timedelta(milliseconds=INTERVAL_MS * 499)
    while window_start < cutoff:
        window_end = min(window_start + window_span, cutoff)
        params = {
            **base_params,
            "period": TIMEFRAME,
            "startTime": millis(window_start),
            "endTime": millis(window_end) - 1,
            "limit": 500,
        }
        payload = request_json(path, params=params, timeout=timeout)
        if isinstance(payload, list):
            rows.extend(payload)
        window_start = window_end
        time.sleep(0.03)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["ts"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    return frame.drop_duplicates("ts", keep="last").sort_values("ts").reset_index(drop=True)


def write_daily_replace(root: Path, ts_column: str, frame: pd.DataFrame) -> int:
    for existing in root.glob(f"date=*/symbol={SLUG}.parquet"):
        existing.unlink()
    work = frame.copy()
    work["date"] = pd.to_datetime(work[ts_column], utc=True).dt.date.astype(str)
    count = 0
    for date, group in work.groupby("date", sort=True):
        path = root / f"date={date}" / f"symbol={SLUG}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        group.drop(columns="date").to_parquet(path, index=False)
        count += 1
    return count


def audit_candles(
    raw: pd.DataFrame,
    normalized: pd.DataFrame,
    *,
    start: pd.Timestamp,
    cutoff: pd.Timestamp,
    kind: str,
) -> dict[str, Any]:
    expected = pd.date_range(start, cutoff - pd.Timedelta(minutes=15), freq="15min")
    actual = pd.DatetimeIndex(normalized["ts"])
    missing = expected.difference(actual)
    extra = actual.difference(expected)
    duplicate_raw = int(raw.duplicated("open_time").sum())
    duplicate_normalized = int(normalized.duplicated("ts").sum())
    value_columns = ["open", "high", "low", "close"]
    if kind == "ohlcv":
        value_columns += [
            "volume",
            "quote_volume",
            "trade_count",
            "taker_buy_volume",
            "taker_buy_quote_volume",
        ]
    raw_values = raw.set_index("open_time")[value_columns].sort_index()
    normalized_values = normalized.set_index("ts")[value_columns].sort_index()
    mismatch = {
        column: int(
            (
                ~np.isclose(
                    raw_values[column].to_numpy(dtype="float64"),
                    normalized_values[column].to_numpy(dtype="float64"),
                    rtol=0.0,
                    atol=1e-12,
                    equal_nan=True,
                )
            ).sum()
        )
        for column in value_columns
    }
    critical = ["ts", *value_columns, "source", "is_closed"]
    null_rows = int(normalized[critical].isna().any(axis=1).sum())
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
        "unclosed_rows": int((~normalized["is_closed"]).sum()),
    }
    if kind == "ohlcv":
        violations.update(
            {
                "negative_volume": int((normalized["volume"] < 0).sum()),
                "negative_quote_volume": int((normalized["quote_volume"] < 0).sum()),
                "negative_trade_count": int((normalized["trade_count"] < 0).sum()),
                "negative_taker_buy_volume": int(
                    (normalized["taker_buy_volume"] < 0).sum()
                ),
                "negative_taker_buy_quote_volume": int(
                    (normalized["taker_buy_quote_volume"] < 0).sum()
                ),
                "taker_buy_volume_above_volume": int(
                    (normalized["taker_buy_volume"] > normalized["volume"] + 1e-12).sum()
                ),
                "taker_buy_quote_above_quote_volume": int(
                    (
                        normalized["taker_buy_quote_volume"]
                        > normalized["quote_volume"] + 1e-12
                    ).sum()
                ),
                "vwap_outside_high_low": int(
                    (
                        (normalized["volume"] > 0)
                        & (
                            (normalized["vwap"] < normalized["low"] * 0.999999)
                            | (normalized["vwap"] > normalized["high"] * 1.000001)
                        )
                    ).sum()
                ),
            }
        )
    blockers = (
        len(missing)
        + len(extra)
        + duplicate_raw
        + duplicate_normalized
        + null_rows
        + sum(mismatch.values())
        + sum(violations.values())
    )
    return {
        "rows": int(len(normalized)),
        "expected_rows": int(len(expected)),
        "first_ts": normalized["ts"].iloc[0].isoformat(),
        "last_ts": normalized["ts"].iloc[-1].isoformat(),
        "expected_last_ts": expected[-1].isoformat(),
        "missing_bars": int(len(missing)),
        "extra_bars": int(len(extra)),
        "duplicate_raw": duplicate_raw,
        "duplicate_normalized": duplicate_normalized,
        "critical_null_rows": null_rows,
        "raw_normalized_mismatches": mismatch,
        "violations": violations,
        "source_counts": {
            str(key): int(value)
            for key, value in normalized["source"].value_counts(dropna=False).items()
        },
        "blocker_count": int(blockers),
    }


def audit_funding(
    combined: pd.DataFrame,
    *,
    start: pd.Timestamp,
    cutoff: pd.Timestamp,
    crosscheck: dict[str, Any],
) -> dict[str, Any]:
    gaps = combined["ts"].diff().dropna().dt.total_seconds().div(3600.0)
    duplicates = int(combined.duplicated("ts").sum())
    null_rates = int(combined["funding_rate"].isna().sum())
    out_of_range = int(((combined["ts"] < start) | (combined["ts"] >= cutoff)).sum())
    blockers = (
        duplicates
        + null_rates
        + out_of_range
        + int(crosscheck["archive_rows_missing_from_api"])
        + int(crosscheck["archive_api_rate_mismatches"])
        + int(float(gaps.max()) > 8.01 if len(gaps) else 0)
    )
    return {
        "rows": int(len(combined)),
        "first_ts": combined["ts"].iloc[0].isoformat(),
        "last_ts": combined["ts"].iloc[-1].isoformat(),
        "first_delay_hours": float((combined["ts"].iloc[0] - start).total_seconds() / 3600.0),
        "max_gap_hours": float(gaps.max()) if len(gaps) else 0.0,
        "duplicate_rows": duplicates,
        "null_rates": null_rates,
        "out_of_range_rows": out_of_range,
        **crosscheck,
        "blocker_count": int(blockers),
    }


def limited_history_audit(
    frame: pd.DataFrame,
    *,
    full_start: pd.Timestamp,
    value_columns: list[str],
) -> dict[str, Any]:
    if frame.empty:
        return {
            "rows": 0,
            "first_ts": None,
            "last_ts": None,
            "full_lifecycle_coverage": 0.0,
            "null_counts": {},
            "complete_for_model": False,
            "decision": "excluded: endpoint returned no rows",
        }
    full_span = max((frame["ts"].max() - full_start).total_seconds(), 1.0)
    covered_span = max((frame["ts"].max() - frame["ts"].min()).total_seconds(), 0.0)
    return {
        "rows": int(len(frame)),
        "first_ts": frame["ts"].min().isoformat(),
        "last_ts": frame["ts"].max().isoformat(),
        "full_lifecycle_coverage": float(covered_span / full_span),
        "null_counts": {
            column: int(pd.to_numeric(frame.get(column), errors="coerce").isna().sum())
            for column in value_columns
        },
        "complete_for_model": False,
        "decision": "excluded: Binance endpoint retains only the latest 30 days",
    }


def write_funding(combined: pd.DataFrame) -> dict[str, Any]:
    enriched = combined.copy()
    enriched["exchange"] = "binance"
    enriched["symbol"] = DISPLAY_SYMBOL
    enriched["market_type"] = "perp"
    enriched["base_asset"] = "HYPE"
    enriched["quote_asset"] = "USDT"
    raw_columns = [
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
        "archive_month",
        "archive_sha256",
        "verified_by_api",
        "verification_source_ts",
    ]
    normalized_columns = [
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
        "archive_month",
        "archive_sha256",
        "verified_by_api",
    ]
    raw_count = write_daily_replace(RAW_FUNDING_ROOT, "ts", enriched[raw_columns])
    normalized_count = write_daily_replace(
        NORMALIZED_FUNDING_ROOT, "ts", enriched[normalized_columns]
    )
    COMPAT_FUNDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    enriched[["ts", "funding_rate", "mark_price", "source"]].to_parquet(
        COMPAT_FUNDING_PATH, index=False
    )
    return {
        "raw_partitions": raw_count,
        "normalized_partitions": normalized_count,
        "compatibility_path": str(COMPAT_FUNDING_PATH.relative_to(ROOT)),
    }


def main() -> None:
    args = parse_args()
    server_payload = request_json("/fapi/v1/time", params=None, timeout=args.timeout)
    server_time = pd.to_datetime(int(server_payload["serverTime"]), unit="ms", utc=True)
    live_cutoff = server_time.floor("15min")
    cutoff = pd.Timestamp(args.cutoff) if args.cutoff else live_cutoff
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")
    if cutoff != cutoff.floor("15min"):
        raise RuntimeError(f"cutoff must be 15m-aligned: {cutoff}")
    if cutoff > live_cutoff:
        raise RuntimeError(f"cutoff {cutoff} is later than live closed cutoff {live_cutoff}")
    contract = contract_snapshot(args.timeout)
    start = pd.Timestamp(contract["onboard_date"])
    if start != start.floor("15min"):
        raise RuntimeError(f"HYPE onboard date is not 15m-aligned: {start}")

    print(f"fetch OHLCV {start} -> {cutoff}", flush=True)
    raw_ohlcv = fetch_candles(
        "/fapi/v1/klines", start=start, cutoff=cutoff, timeout=args.timeout
    )
    raw_ohlcv["source"] = "binance_futures_kline_api"
    normalized_ohlcv = normalize_ohlcv(raw_ohlcv)

    print(f"fetch mark price {start} -> {cutoff}", flush=True)
    raw_mark_api = fetch_candles(
        "/fapi/v1/markPriceKlines", start=start, cutoff=cutoff, timeout=args.timeout
    )
    raw_mark_api["source"] = "binance_mark_price_klines"
    normalized_mark = normalize_mark(raw_mark_api)

    archive_pieces: list[pd.DataFrame] = []
    archive_checksums: dict[str, str] = {}
    for month in completed_months(start, cutoff):
        print(f"verify funding archive {month:%Y-%m}", flush=True)
        frame, checksum = read_funding_archive(month, args.timeout)
        archive_pieces.append(frame)
        archive_checksums[month.strftime("%Y-%m")] = checksum
    funding_archive = pd.concat(archive_pieces, ignore_index=True).sort_values("ts")
    funding_archive = funding_archive.loc[
        (funding_archive["ts"] >= start) & (funding_archive["ts"] < cutoff)
    ].reset_index(drop=True)
    funding_api = fetch_funding_api(start=start, cutoff=cutoff, timeout=args.timeout)
    funding_api = funding_api.loc[
        (funding_api["ts"] >= start) & (funding_api["ts"] < cutoff)
    ].reset_index(drop=True)
    funding, funding_crosscheck = combine_funding(funding_archive, funding_api)

    oi = fetch_limited_history(
        "/futures/data/openInterestHist",
        base_params={"symbol": SYMBOL},
        cutoff=cutoff,
        timeout=args.timeout,
    )
    basis = fetch_limited_history(
        "/futures/data/basis",
        base_params={"pair": SYMBOL, "contractType": "PERPETUAL"},
        cutoff=cutoff,
        timeout=args.timeout,
    )

    ohlcv_quality = audit_candles(
        raw_ohlcv, normalized_ohlcv, start=start, cutoff=cutoff, kind="ohlcv"
    )
    mark_quality = audit_candles(
        raw_mark_api, normalized_mark, start=start, cutoff=cutoff, kind="mark"
    )
    mark_timestamp_mismatches = int(
        (~normalized_mark["ts"].eq(normalized_ohlcv["ts"])).sum()
    )
    mark_quality["ohlcv_timestamp_mismatches"] = mark_timestamp_mismatches
    mark_quality["blocker_count"] += mark_timestamp_mismatches
    funding_quality = audit_funding(
        funding,
        start=start,
        cutoff=cutoff,
        crosscheck=funding_crosscheck,
    )
    oi_quality = limited_history_audit(
        oi,
        full_start=start,
        value_columns=["sumOpenInterest", "sumOpenInterestValue"],
    )
    basis_quality = limited_history_audit(
        basis,
        full_start=start,
        value_columns=["basis", "basisRate", "futuresPrice", "indexPrice"],
    )

    total_blockers = (
        int(ohlcv_quality["blocker_count"])
        + int(mark_quality["blocker_count"])
        + int(funding_quality["blocker_count"])
    )
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "binance_server_time": server_time.isoformat(),
        "closed_bar_cutoff_exclusive": cutoff.isoformat(),
        "market": "Binance USD-M Futures perpetual",
        "symbol": SYMBOL,
        "display_symbol": DISPLAY_SYMBOL,
        "timeframe": TIMEFRAME,
        "contract_snapshot": contract,
        "ohlcv": ohlcv_quality,
        "mark_price": mark_quality,
        "funding": {
            **funding_quality,
            "archive_month_count": len(archive_checksums),
            "archive_checksums": archive_checksums,
        },
        "open_interest": oi_quality,
        "basis": basis_quality,
        "model_input_decision": {
            "included": ["ohlcv", "mark_price", "funding"],
            "excluded": ["open_interest", "basis"],
            "reason": "OI and basis do not cover the full locked research lifecycle.",
        },
        "total_blocker_count": total_blockers,
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    if not args.no_write:
        writes = {
            "raw_ohlcv_partitions": write_daily_replace(
                RAW_OHLCV_ROOT, "open_time", raw_ohlcv
            ),
            "normalized_ohlcv_partitions": write_daily_replace(
                NORMALIZED_OHLCV_ROOT, "ts", normalized_ohlcv
            ),
            "raw_mark_partitions": write_daily_replace(
                RAW_MARK_ROOT, "open_time", raw_mark_api
            ),
            "normalized_mark_partitions": write_daily_replace(
                NORMALIZED_MARK_ROOT, "ts", normalized_mark
            ),
            "funding": write_funding(funding),
        }
        oi.to_parquet(ARTIFACT_DIR / "hype_15m_open_interest_available_30d.parquet", index=False)
        basis.to_parquet(ARTIFACT_DIR / "hype_15m_basis_available_30d.parquet", index=False)
    else:
        writes = {"mode": "no-write"}
    report["writes"] = writes
    report_path = ARTIFACT_DIR / "hype_15m_data_quality_round2.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "report": str(report_path.relative_to(ROOT)),
                "cutoff": cutoff.isoformat(),
                "ohlcv_rows": len(normalized_ohlcv),
                "mark_rows": len(normalized_mark),
                "funding_rows": len(funding),
                "oi_rows_available": len(oi),
                "basis_rows_available": len(basis),
                "total_blocker_count": total_blockers,
            },
            indent=2,
        ),
        flush=True,
    )
    if total_blockers:
        raise RuntimeError(f"HYPE 15m data-quality blockers remain: {total_blockers}")


if __name__ == "__main__":
    main()
