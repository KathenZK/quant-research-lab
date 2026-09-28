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
FAMILY_DIR = ROOT / "research/asset-portfolios/15m-asset-specific-six-strategy-selector"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
FAPI = "https://fapi.binance.com"
VISION = "https://data.binance.vision"
UA = "quant-research-lab-bin-15m-as6s-data/0.1"
INTERVAL_MS = 15 * 60 * 1000
TIMEFRAME = "15m"

RAW_OHLCV_ROOT = ROOT / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
NORMALIZED_OHLCV_ROOT = ROOT / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
RAW_FUNDING_ROOT = ROOT / "data/raw/funding_rates/exchange=binance/market_type=perp"
NORMALIZED_FUNDING_ROOT = ROOT / "data/normalized/funding_rates/exchange=binance/market_type=perp"
COMPAT_FUNDING_ROOT = ROOT / "data/normalized/funding/exchange=binance/market_type=perp"
ARCHIVE_ROOT = ROOT / "data/raw/_archives/binance/futures/um/monthly/fundingRate"

DEFAULT_START = pd.Timestamp("2024-07-14T00:00:00Z")
HYPE_START = pd.Timestamp("2025-05-30T10:30:00Z")
SYMBOLS = {
    "BTCUSDT": ("BTC", "btc_usdt_usdt", DEFAULT_START),
    "ETHUSDT": ("ETH", "eth_usdt_usdt", DEFAULT_START),
    "SOLUSDT": ("SOL", "sol_usdt_usdt", DEFAULT_START),
    "BNBUSDT": ("BNB", "bnb_usdt_usdt", DEFAULT_START),
    "TRXUSDT": ("TRX", "trx_usdt_usdt", DEFAULT_START),
    "HYPEUSDT": ("HYPE", "hype_usdt_usdt", HYPE_START),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh and audit six Binance perpetual 15m datasets and funding."
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args()


def request_bytes(url: str, *, timeout: float, attempts: int = 7) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, headers={"User-Agent": UA}), timeout=timeout) as response:  # noqa: S310
                return response.read()
        except HTTPError:
            raise
        except (URLError, TimeoutError, IncompleteRead, ConnectionError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(min(12.0, 0.75 * 2**attempt))
    raise RuntimeError(f"request failed after {attempts} attempts: {url}") from last_error


def request_json(path: str, *, params: dict[str, object] | None, timeout: float) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    return json.loads(request_bytes(f"{FAPI}{path}{query}", timeout=timeout))


def millis(ts: pd.Timestamp) -> int:
    return int(pd.Timestamp(ts).tz_convert("UTC").timestamp() * 1000)


def fetch_klines(symbol: str, start: pd.Timestamp, end: pd.Timestamp, timeout: float) -> pd.DataFrame:
    rows: list[list[Any]] = []
    cursor = millis(start)
    end_ms = millis(end)
    while cursor < end_ms:
        payload = request_json(
            "/fapi/v1/klines",
            params={
                "symbol": symbol,
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
            raise RuntimeError(f"{symbol} kline pagination stopped")
        cursor = next_cursor
        time.sleep(0.03)
    if not rows:
        raise RuntimeError(f"no klines returned for {symbol}")
    columns = [
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "trade_count", "taker_buy_volume",
        "taker_buy_quote_volume", "ignore",
    ]
    frame = pd.DataFrame(rows, columns=columns)
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    numeric = [
        "open", "high", "low", "close", "volume", "quote_volume", "trade_count",
        "taker_buy_volume", "taker_buy_quote_volume",
    ]
    for column in numeric:
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
    base, _, _ = SYMBOLS[symbol]
    frame = raw.rename(columns={"open_time": "ts"}).copy()
    frame["exchange"] = "binance"
    frame["symbol"] = f"{base}/USDT:USDT"
    frame["market_type"] = "perp"
    frame["timeframe"] = TIMEFRAME
    frame["base_asset"] = base
    frame["quote_asset"] = "USDT"
    frame["vwap"] = frame["quote_volume"] / frame["volume"].replace(0.0, np.nan)
    frame["vwap"] = frame["vwap"].fillna(frame["close"])
    return frame[
        [
            "ts", "exchange", "symbol", "market_type", "timeframe", "base_asset",
            "quote_asset", "open", "high", "low", "close", "volume",
            "quote_volume", "trade_count", "vwap", "is_closed", "source",
        ]
    ]


def write_daily(root: Path, slug: str, ts_column: str, frame: pd.DataFrame) -> int:
    work = frame.copy()
    work["date"] = work[ts_column].dt.date.astype(str)
    count = 0
    for date, group in work.groupby("date", sort=True):
        path = root / f"date={date}" / f"symbol={slug}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        group.drop(columns="date").to_parquet(path, index=False)
        count += 1
    return count


def month_range(start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    current = start.to_period("M").start_time.tz_localize("UTC")
    last = (end.to_period("M").start_time.tz_localize("UTC") - pd.offsets.MonthBegin(1))
    months: list[pd.Timestamp] = []
    while current <= last:
        months.append(current)
        current += pd.offsets.MonthBegin(1)
    return months


def archive_paths(symbol: str, month: pd.Timestamp) -> tuple[Path, Path, str, str]:
    stamp = month.strftime("%Y-%m")
    name = f"{symbol}-fundingRate-{stamp}.zip"
    directory = ARCHIVE_ROOT / f"symbol={symbol.lower()}" / f"year={month.year}"
    base = f"{VISION}/data/futures/um/monthly/fundingRate/{symbol}/{name}"
    return directory / name, directory / f"{name}.CHECKSUM", base, f"{base}.CHECKSUM"


def read_archive(symbol: str, month: pd.Timestamp, timeout: float) -> tuple[pd.DataFrame, str]:
    archive_path, checksum_path, archive_url, checksum_url = archive_paths(symbol, month)
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
        raise RuntimeError(f"{symbol} {month:%Y-%m} funding checksum mismatch")
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        if archive.testzip() is not None:
            raise RuntimeError(f"{symbol} {month:%Y-%m} corrupt archive")
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
    frame["funding_interval_hours"] = pd.to_numeric(frame["funding_interval_hours"], errors="coerce")
    frame["mark_price"] = np.nan
    frame["source"] = "binance_vision_funding_archive"
    return frame[["source_ts", "ts", "funding_rate", "funding_interval_hours", "mark_price", "source"]], actual


def fetch_funding_tail(symbol: str, start: pd.Timestamp, end: pd.Timestamp, timeout: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    cursor = millis(start)
    end_ms = millis(end)
    while cursor <= end_ms:
        payload = request_json(
            "/fapi/v1/fundingRate",
            params={"symbol": symbol, "startTime": cursor, "endTime": end_ms, "limit": 1000},
            timeout=timeout,
        )
        if not isinstance(payload, list) or not payload:
            break
        rows.extend(payload)
        cursor = int(payload[-1]["fundingTime"]) + 1
        time.sleep(0.03)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["source_ts", "ts", "funding_rate", "funding_interval_hours", "mark_price", "source"])
    frame["source_ts"] = pd.to_datetime(frame["fundingTime"], unit="ms", utc=True)
    frame["ts"] = frame["source_ts"].dt.round("s")
    frame["funding_rate"] = pd.to_numeric(frame["fundingRate"], errors="coerce")
    frame["funding_interval_hours"] = np.nan
    frame["mark_price"] = pd.to_numeric(frame.get("markPrice"), errors="coerce")
    frame["source"] = "binance_futures_funding_rate_api"
    return frame[["source_ts", "ts", "funding_rate", "funding_interval_hours", "mark_price", "source"]]


def build_funding(symbol: str, start: pd.Timestamp, end: pd.Timestamp, timeout: float) -> tuple[pd.DataFrame, dict[str, str]]:
    pieces: list[pd.DataFrame] = []
    checksums: dict[str, str] = {}
    for month in month_range(start, end):
        frame, checksum = read_archive(symbol, month, timeout)
        pieces.append(frame)
        checksums[month.strftime("%Y-%m")] = checksum
    pieces.append(fetch_funding_tail(symbol, max(start, end - pd.Timedelta(days=45)), end, timeout))
    combined = pd.concat(pieces, ignore_index=True, sort=False)
    combined = combined.loc[(combined["ts"] >= start) & (combined["ts"] < end)].copy()
    combined["priority"] = combined["source"].map({
        "binance_vision_funding_archive": 0,
        "binance_futures_funding_rate_api": 1,
    })
    combined = (
        combined.sort_values(["ts", "priority"])
        .drop_duplicates("ts", keep="last")
        .drop(columns="priority")
        .sort_values("ts")
        .reset_index(drop=True)
    )
    return combined, checksums


def enrich_funding(symbol: str, funding: pd.DataFrame) -> pd.DataFrame:
    base, _, _ = SYMBOLS[symbol]
    frame = funding.copy()
    frame["exchange"] = "binance"
    frame["symbol"] = f"{base}/USDT:USDT"
    frame["market_type"] = "perp"
    frame["base_asset"] = base
    frame["quote_asset"] = "USDT"
    frame["next_funding_ts"] = frame["ts"].shift(-1)
    return frame


def write_funding(symbol: str, funding: pd.DataFrame) -> dict[str, Any]:
    _, slug, _ = SYMBOLS[symbol]
    frame = enrich_funding(symbol, funding)
    raw_columns = [
        "source_ts", "ts", "exchange", "symbol", "market_type", "base_asset",
        "quote_asset", "funding_rate", "funding_interval_hours", "next_funding_ts",
        "mark_price", "source",
    ]
    normalized_columns = [
        "ts", "exchange", "symbol", "market_type", "base_asset", "quote_asset",
        "funding_rate", "next_funding_ts", "mark_price", "source",
    ]
    raw_count = write_daily(RAW_FUNDING_ROOT, slug, "ts", frame[raw_columns])
    norm_count = write_daily(NORMALIZED_FUNDING_ROOT, slug, "ts", frame[normalized_columns])
    compat = COMPAT_FUNDING_ROOT / f"symbol={slug}" / "funding.parquet"
    compat.parent.mkdir(parents=True, exist_ok=True)
    funding[["ts", "funding_rate", "mark_price", "source"]].to_parquet(compat, index=False)
    return {"raw_partitions": raw_count, "normalized_partitions": norm_count, "compatibility_file": str(compat.relative_to(ROOT))}


def audit_ohlcv(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, Any]:
    expected = pd.date_range(start, end - pd.Timedelta(minutes=15), freq="15min")
    actual = pd.DatetimeIndex(frame["ts"])
    critical = ["ts", "open", "high", "low", "close", "volume", "quote_volume", "trade_count", "vwap", "is_closed", "source"]
    violations = int((frame["high"] < frame[["open", "close"]].max(axis=1)).sum())
    violations += int((frame["low"] > frame[["open", "close"]].min(axis=1)).sum())
    violations += int((frame["high"] < frame["low"]).sum())
    violations += int(((frame[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum())
    violations += int((frame["volume"] < 0).sum()) + int((~frame["is_closed"]).sum())
    missing = expected.difference(actual)
    extra = actual.difference(expected)
    duplicates = int(frame.duplicated("ts").sum())
    nulls = int(frame[critical].isna().any(axis=1).sum())
    blockers = len(missing) + len(extra) + duplicates + nulls + violations
    return {
        "rows": len(frame), "first_ts": frame["ts"].iloc[0].isoformat(),
        "last_ts": frame["ts"].iloc[-1].isoformat(), "missing_bars": len(missing),
        "extra_bars": len(extra), "duplicate_bars": duplicates,
        "critical_null_rows": nulls, "ohlc_violations": violations,
        "blocker_count": blockers,
    }


def audit_funding(frame: pd.DataFrame, start: pd.Timestamp) -> dict[str, Any]:
    gaps = frame["ts"].diff().dropna()
    first_delay = (frame["ts"].iloc[0] - start).total_seconds() / 3600.0
    max_gap = gaps.max().total_seconds() / 3600.0 if len(gaps) else 0.0
    duplicates = int(frame.duplicated("ts").sum())
    nulls = int(frame["funding_rate"].isna().sum())
    blockers = duplicates + nulls + int(first_delay > 8.01) + int(max_gap > 8.01)
    return {
        "rows": len(frame), "first_ts": frame["ts"].iloc[0].isoformat(),
        "last_ts": frame["ts"].iloc[-1].isoformat(), "first_delay_hours": first_delay,
        "max_gap_hours": max_gap, "duplicate_rows": duplicates, "null_rates": nulls,
        "source_counts": frame["source"].value_counts().to_dict(),
        "blocker_count": blockers,
    }


def main() -> None:
    args = parse_args()
    server = request_json("/fapi/v1/time", params=None, timeout=args.timeout)
    cutoff = pd.to_datetime(int(server["serverTime"]), unit="ms", utc=True).floor("15min")
    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "market": "Binance USD-M Futures perpetual", "timeframe": TIMEFRAME,
        "closed_bar_cutoff_exclusive": cutoff.isoformat(), "symbols": {},
    }
    total_blockers = 0
    for symbol, (_, slug, start) in SYMBOLS.items():
        print(f"sync {symbol} from {start} to {cutoff}", flush=True)
        raw = fetch_klines(symbol, start, cutoff, args.timeout)
        normalized = normalize_klines(symbol, raw)
        funding, checksums = build_funding(symbol, start, cutoff, args.timeout)
        if args.no_write:
            writes = {"raw_ohlcv": 0, "normalized_ohlcv": 0, "funding": {}}
        else:
            writes = {
                "raw_ohlcv": write_daily(RAW_OHLCV_ROOT, slug, "open_time", raw),
                "normalized_ohlcv": write_daily(NORMALIZED_OHLCV_ROOT, slug, "ts", normalized),
                "funding": write_funding(symbol, funding),
            }
        ohlcv_quality = audit_ohlcv(normalized, start, cutoff)
        funding_quality = audit_funding(funding, start)
        blockers = ohlcv_quality["blocker_count"] + funding_quality["blocker_count"]
        total_blockers += blockers
        report["symbols"][symbol] = {
            "research_start": start.isoformat(), "writes": writes,
            "archive_months": len(checksums), "archive_checksums": checksums,
            "ohlcv_quality": ohlcv_quality, "funding_quality": funding_quality,
            "blocker_count": blockers,
        }
    report["total_blocker_count"] = total_blockers
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / "binance_six_asset_15m_data_quality_2026-07-14.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(path), "total_blocker_count": total_blockers}, indent=2), flush=True)
    if total_blockers:
        raise RuntimeError(f"data quality blockers remain: {total_blockers}")


if __name__ == "__main__":
    main()
