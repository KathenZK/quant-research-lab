from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
import time
import zipfile
from datetime import datetime, timezone
from http.client import IncompleteRead
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1h-multi-leg-six-asset-selector"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"

FAPI = "https://fapi.binance.com"
VISION = "https://data.binance.vision"
UA = "quant-research-lab-bin-1h-ml6as-data/0.1"

RAW_OHLCV_ROOT = (
    ROOT / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=1h"
)
NORMALIZED_OHLCV_ROOT = (
    ROOT / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h"
)
RAW_FUNDING_ROOT = (
    ROOT / "data/raw/funding_rates/exchange=binance/market_type=perp"
)
NORMALIZED_FUNDING_ROOT = (
    ROOT / "data/normalized/funding_rates/exchange=binance/market_type=perp"
)
COMPAT_FUNDING_ROOT = (
    ROOT / "data/normalized/funding/exchange=binance/market_type=perp"
)
FUNDING_ARCHIVE_ROOT = (
    ROOT
    / "data/raw/_archives/binance/futures/um/monthly/fundingRate"
)

RESEARCH_START = pd.Timestamp("2025-05-30T10:00:00Z")
INTERVAL_MS = 60 * 60 * 1000
SYMBOLS = {
    "BTCUSDT": ("BTC", "btc_usdt_usdt"),
    "ETHUSDT": ("ETH", "eth_usdt_usdt"),
    "SOLUSDT": ("SOL", "sol_usdt_usdt"),
    "BNBUSDT": ("BNB", "bnb_usdt_usdt"),
    "TRXUSDT": ("TRX", "trx_usdt_usdt"),
    "HYPEUSDT": ("HYPE", "hype_usdt_usdt"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh and audit the common six-asset Binance perpetual 1h window, "
            "using Binance Vision monthly funding archives plus the REST API tail."
        )
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--skip-download", action="store_true")
    return parser.parse_args()


def request_bytes(url: str, *, timeout: float, attempts: int = 7) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": UA})
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
    params: dict[str, object] | None = None,
    timeout: float,
) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    return json.loads(request_bytes(f"{FAPI}{path}{query}", timeout=timeout))


def server_time(timeout: float) -> pd.Timestamp:
    payload = request_json("/fapi/v1/time", timeout=timeout)
    if not isinstance(payload, dict) or "serverTime" not in payload:
        raise RuntimeError(f"unexpected Binance server-time payload: {payload!r}")
    return pd.to_datetime(int(payload["serverTime"]), unit="ms", utc=True)


def milliseconds(ts: pd.Timestamp) -> int:
    return int(pd.Timestamp(ts).tz_convert("UTC").timestamp() * 1000)


def fetch_klines(
    symbol: str,
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
                "symbol": symbol,
                "interval": "1h",
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
            raise RuntimeError(f"{symbol} kline pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1500:
            break
        time.sleep(0.04)
    if not rows:
        raise RuntimeError(f"Binance returned no {symbol} 1h klines")
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
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["source"] = "binance_futures_kline_api"
    frame["is_closed"] = frame["close_time"] < end
    return (
        frame.loc[
            (frame["open_time"] >= start)
            & (frame["open_time"] < end)
            & frame["is_closed"]
        ]
        .drop_duplicates("open_time", keep="last")
        .sort_values("open_time")
        .reset_index(drop=True)
    )


def normalize_klines(symbol: str, raw: pd.DataFrame) -> pd.DataFrame:
    base_asset, _ = SYMBOLS[symbol]
    frame = raw.rename(columns={"open_time": "ts"}).copy()
    frame["exchange"] = "binance"
    frame["symbol"] = f"{base_asset}/USDT:USDT"
    frame["market_type"] = "perp"
    frame["timeframe"] = "1h"
    frame["base_asset"] = base_asset
    frame["quote_asset"] = "USDT"
    frame["vwap"] = frame["quote_volume"] / frame["volume"].replace(0.0, np.nan)
    frame["vwap"] = frame["vwap"].fillna(frame["close"])
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
            "vwap",
            "is_closed",
            "source",
        ]
    ].reset_index(drop=True)


def write_ohlcv_partitions(
    symbol: str, raw: pd.DataFrame, normalized: pd.DataFrame
) -> dict[str, int]:
    _, slug = SYMBOLS[symbol]
    filename = f"symbol={slug}.parquet"
    raw_frame = raw.copy()
    raw_frame["date"] = raw_frame["open_time"].dt.date.astype(str)
    normalized_frame = normalized.copy()
    normalized_frame["date"] = normalized_frame["ts"].dt.date.astype(str)
    raw_count = 0
    normalized_count = 0
    for date, group in raw_frame.groupby("date", sort=True):
        path = RAW_OHLCV_ROOT / f"date={date}" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        group.drop(columns="date").to_parquet(path, index=False)
        raw_count += 1
    for date, group in normalized_frame.groupby("date", sort=True):
        path = NORMALIZED_OHLCV_ROOT / f"date={date}" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        group.drop(columns="date").to_parquet(path, index=False)
        normalized_count += 1
    return {"raw": raw_count, "normalized": normalized_count}


def month_starts(start: pd.Timestamp, last_complete_month: pd.Timestamp) -> list[pd.Timestamp]:
    current = pd.Timestamp(
        year=start.year, month=start.month, day=1, tz="UTC"
    )
    last = pd.Timestamp(
        year=last_complete_month.year,
        month=last_complete_month.month,
        day=1,
        tz="UTC",
    )
    result: list[pd.Timestamp] = []
    while current <= last:
        result.append(current)
        current = current + pd.offsets.MonthBegin(1)
    return result


def funding_archive_paths(symbol: str, month: pd.Timestamp) -> tuple[Path, Path, str, str]:
    stamp = month.strftime("%Y-%m")
    filename = f"{symbol}-fundingRate-{stamp}.zip"
    directory = FUNDING_ARCHIVE_ROOT / f"symbol={symbol.lower()}" / f"year={month.year}"
    archive_path = directory / filename
    checksum_path = directory / f"{filename}.CHECKSUM"
    base_url = f"{VISION}/data/futures/um/monthly/fundingRate/{symbol}"
    return archive_path, checksum_path, f"{base_url}/{filename}", f"{base_url}/{filename}.CHECKSUM"


def verified_archive_bytes(
    symbol: str, month: pd.Timestamp, *, timeout: float
) -> tuple[bytes, str]:
    archive_path, checksum_path, archive_url, checksum_url = funding_archive_paths(
        symbol, month
    )
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
    if expected != actual:
        raise RuntimeError(
            f"{symbol} {month:%Y-%m} archive checksum mismatch: {expected} != {actual}"
        )
    return payload, actual


def parse_funding_archive(
    symbol: str, month: pd.Timestamp, *, timeout: float
) -> tuple[pd.DataFrame, str]:
    payload, checksum = verified_archive_bytes(symbol, month, timeout=timeout)
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RuntimeError(f"corrupt archive member: {bad_member}")
        members = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(members) != 1:
            raise RuntimeError(
                f"unexpected {symbol} {month:%Y-%m} archive members: {members}"
            )
        with archive.open(members[0]) as handle:
            frame = pd.read_csv(handle)
    required = {"calc_time", "funding_interval_hours", "last_funding_rate"}
    missing = required - set(frame.columns)
    if missing:
        raise RuntimeError(
            f"{symbol} {month:%Y-%m} archive missing columns: {sorted(missing)}"
        )
    frame["source_ts"] = pd.to_datetime(frame["calc_time"], unit="ms", utc=True)
    frame["ts"] = frame["source_ts"].dt.round("s")
    frame["funding_rate"] = pd.to_numeric(
        frame["last_funding_rate"], errors="coerce"
    )
    frame["funding_interval_hours"] = pd.to_numeric(
        frame["funding_interval_hours"], errors="coerce"
    )
    frame["mark_price"] = np.nan
    frame["source"] = "binance_vision_funding_archive"
    return frame[
        [
            "source_ts",
            "ts",
            "funding_rate",
            "funding_interval_hours",
            "mark_price",
            "source",
        ]
    ], checksum


def fetch_funding_api_tail(
    symbol: str,
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
                "symbol": symbol,
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
            raise RuntimeError(f"{symbol} funding pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1000:
            break
        time.sleep(0.04)
    if not rows:
        return pd.DataFrame(
            columns=[
                "source_ts",
                "ts",
                "funding_rate",
                "funding_interval_hours",
                "mark_price",
                "source",
            ]
        )
    frame = pd.DataFrame(rows)
    frame["source_ts"] = pd.to_datetime(frame["fundingTime"], unit="ms", utc=True)
    frame["ts"] = frame["source_ts"].dt.round("s")
    frame["funding_rate"] = pd.to_numeric(frame["fundingRate"], errors="coerce")
    frame["funding_interval_hours"] = np.nan
    frame["mark_price"] = pd.to_numeric(frame.get("markPrice"), errors="coerce")
    frame["source"] = "binance_futures_funding_rate_api"
    return frame[
        [
            "source_ts",
            "ts",
            "funding_rate",
            "funding_interval_hours",
            "mark_price",
            "source",
        ]
    ]


def build_funding(
    symbol: str,
    *,
    end: pd.Timestamp,
    timeout: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    current_month = pd.Timestamp(year=end.year, month=end.month, day=1, tz="UTC")
    last_complete_month = current_month - pd.offsets.MonthBegin(1)
    frames: list[pd.DataFrame] = []
    checksums: dict[str, str] = {}
    missing_archives: list[str] = []
    for month in month_starts(RESEARCH_START, last_complete_month):
        try:
            frame, checksum = parse_funding_archive(symbol, month, timeout=timeout)
        except HTTPError as exc:
            if exc.code != 404:
                raise
            missing_archives.append(month.strftime("%Y-%m"))
            continue
        frames.append(frame)
        checksums[month.strftime("%Y-%m")] = checksum
    if missing_archives:
        raise RuntimeError(f"{symbol} missing monthly funding archives: {missing_archives}")
    api_start = max(RESEARCH_START, end - pd.Timedelta(days=45))
    frames.append(
        fetch_funding_api_tail(
            symbol, start=api_start, end=end, timeout=timeout
        )
    )
    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined = combined.loc[
        (combined["ts"] >= RESEARCH_START) & (combined["ts"] <= end)
    ].copy()
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
    if combined.empty or combined["funding_rate"].isna().any():
        raise RuntimeError(f"{symbol} funding is empty or has null rates")
    return combined, {
        "archive_checksums": checksums,
        "archive_months": len(checksums),
        "api_tail_start": api_start.isoformat(),
    }


def write_funding_partitions(symbol: str, funding: pd.DataFrame) -> dict[str, int]:
    base_asset, slug = SYMBOLS[symbol]
    filename = f"symbol={slug}.parquet"
    enriched = funding.copy()
    enriched["exchange"] = "binance"
    enriched["symbol"] = f"{base_asset}/USDT:USDT"
    enriched["market_type"] = "perp"
    enriched["base_asset"] = base_asset
    enriched["quote_asset"] = "USDT"
    enriched["next_funding_ts"] = enriched["ts"].shift(-1)
    enriched["date"] = enriched["ts"].dt.date.astype(str)
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
    ]
    raw_count = 0
    normalized_count = 0
    for date, group in enriched.groupby("date", sort=True):
        raw_path = RAW_FUNDING_ROOT / f"date={date}" / filename
        normalized_path = NORMALIZED_FUNDING_ROOT / f"date={date}" / filename
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_path.parent.mkdir(parents=True, exist_ok=True)
        group[raw_columns].to_parquet(raw_path, index=False)
        group[normalized_columns].to_parquet(normalized_path, index=False)
        raw_count += 1
        normalized_count += 1
    compat_path = COMPAT_FUNDING_ROOT / f"symbol={slug}" / "funding.parquet"
    compat_path.parent.mkdir(parents=True, exist_ok=True)
    funding[["ts", "funding_rate", "mark_price", "source"]].to_parquet(
        compat_path, index=False
    )
    return {
        "raw": raw_count,
        "normalized": normalized_count,
        "compatibility_file": str(compat_path.relative_to(ROOT)),
    }


def audit_ohlcv(
    raw: pd.DataFrame,
    normalized: pd.DataFrame,
    *,
    expected_end: pd.Timestamp,
) -> dict[str, Any]:
    expected = pd.date_range(RESEARCH_START, expected_end - pd.Timedelta(hours=1), freq="1h")
    actual = pd.DatetimeIndex(normalized["ts"])
    missing = expected.difference(actual)
    extra = actual.difference(expected)
    critical = [
        "ts",
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
    raw_closed = raw.sort_values("open_time").reset_index(drop=True)
    norm = normalized.sort_values("ts").reset_index(drop=True)
    equality = {}
    for column in ["open", "high", "low", "close", "volume", "quote_volume", "trade_count"]:
        equality[column] = bool(
            np.allclose(
                pd.to_numeric(raw_closed[column]),
                pd.to_numeric(norm[column]),
                rtol=0.0,
                atol=1e-12,
                equal_nan=True,
            )
        )
    violations = {
        "high_lt_open_or_close": int(
            (norm["high"] < norm[["open", "close"]].max(axis=1)).sum()
        ),
        "low_gt_open_or_close": int(
            (norm["low"] > norm[["open", "close"]].min(axis=1)).sum()
        ),
        "high_lt_low": int((norm["high"] < norm["low"]).sum()),
        "nonpositive_ohlc": int(
            ((norm[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum()
        ),
        "negative_volume": int((norm["volume"] < 0).sum()),
        "not_closed": int((~norm["is_closed"]).sum()),
    }
    blockers = (
        len(missing)
        + len(extra)
        + int(norm.duplicated("ts").sum())
        + int(norm[critical].isna().any(axis=1).sum())
        + sum(violations.values())
        + sum(not value for value in equality.values())
    )
    return {
        "rows": int(len(norm)),
        "first_ts": norm["ts"].iloc[0].isoformat(),
        "last_ts": norm["ts"].iloc[-1].isoformat(),
        "missing_bars": int(len(missing)),
        "missing_examples": [ts.isoformat() for ts in missing[:10]],
        "extra_bars": int(len(extra)),
        "duplicate_bars": int(norm.duplicated("ts").sum()),
        "critical_null_rows": int(norm[critical].isna().any(axis=1).sum()),
        "raw_normalized_equal": equality,
        "violations": violations,
        "blocker_count": int(blockers),
    }


def audit_funding(funding: pd.DataFrame) -> dict[str, Any]:
    gaps = funding["ts"].diff().dropna()
    first_delay = (funding["ts"].iloc[0] - RESEARCH_START).total_seconds() / 3600.0
    duplicate_rows = int(funding.duplicated("ts").sum())
    null_rates = int(funding["funding_rate"].isna().sum())
    max_gap = float(gaps.max().total_seconds() / 3600.0) if len(gaps) else 0.0
    blockers = duplicate_rows + null_rates + int(first_delay > 8.01) + int(max_gap > 8.01)
    return {
        "rows": int(len(funding)),
        "first_ts": funding["ts"].iloc[0].isoformat(),
        "last_ts": funding["ts"].iloc[-1].isoformat(),
        "first_delay_hours": first_delay,
        "max_gap_hours": max_gap,
        "duplicate_rows": duplicate_rows,
        "null_rates": null_rates,
        "mark_price_null_rows": int(funding["mark_price"].isna().sum()),
        "source_counts": funding["source"].value_counts().to_dict(),
        "blocker_count": blockers,
    }


def main() -> None:
    args = parse_args()
    cutoff = server_time(args.timeout).floor("h")
    if cutoff <= RESEARCH_START:
        raise RuntimeError("Binance server cutoff is before the research window")
    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "market": "Binance USD-M Futures perpetual",
        "timeframe": "1h",
        "research_start": RESEARCH_START.isoformat(),
        "closed_bar_cutoff_exclusive": cutoff.isoformat(),
        "funding_source": "Binance Vision monthly archives plus REST API tail",
        "symbols": {},
    }
    total_blockers = 0
    for symbol in SYMBOLS:
        print(f"sync {symbol}", flush=True)
        raw = fetch_klines(
            symbol,
            start=RESEARCH_START,
            end=cutoff,
            timeout=args.timeout,
        )
        normalized = normalize_klines(symbol, raw)
        ohlcv_partitions = (
            {"raw": 0, "normalized": 0}
            if args.skip_download
            else write_ohlcv_partitions(symbol, raw, normalized)
        )
        funding, archive_meta = build_funding(
            symbol,
            end=cutoff,
            timeout=args.timeout,
        )
        funding_partitions = (
            {"raw": 0, "normalized": 0, "compatibility_file": None}
            if args.skip_download
            else write_funding_partitions(symbol, funding)
        )
        ohlcv_quality = audit_ohlcv(raw, normalized, expected_end=cutoff)
        funding_quality = audit_funding(funding)
        symbol_blockers = (
            ohlcv_quality["blocker_count"] + funding_quality["blocker_count"]
        )
        total_blockers += symbol_blockers
        report["symbols"][symbol] = {
            "ohlcv_partitions_written": ohlcv_partitions,
            "funding_partitions_written": funding_partitions,
            "funding_archive": archive_meta,
            "ohlcv_quality": ohlcv_quality,
            "funding_quality": funding_quality,
            "blocker_count": symbol_blockers,
        }
    report["total_blocker_count"] = int(total_blockers)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    output = ARTIFACT_DIR / "binance_six_asset_1h_data_quality_2026-07-14.json"
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
    if total_blockers:
        raise RuntimeError(f"data-quality blockers remain: {total_blockers}")


if __name__ == "__main__":
    main()
