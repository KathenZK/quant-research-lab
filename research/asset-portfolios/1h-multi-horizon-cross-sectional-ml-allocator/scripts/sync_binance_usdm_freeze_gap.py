from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / (
    "research/asset-portfolios/1h-multi-horizon-cross-sectional-ml-allocator"
)
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
FAPI = "https://fapi.binance.com"
UA = "quant-research-lab-bin-1h-mhcsml-freeze/1.0"
START = pd.Timestamp("2026-07-01T00:00:00Z")
HARD_END = pd.Timestamp("2026-07-19T00:00:00Z")
MONTH = "2026-07"

DATASETS = {
    "kline_1h": {
        "endpoint": "/fapi/v1/klines",
        "normalized_root": ROOT
        / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
        "raw_root": ROOT
        / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
    },
    "mark_1h": {
        "endpoint": "/fapi/v1/markPriceKlines",
        "normalized_root": ROOT
        / "data/normalized/mark_price_klines/exchange=binance/market_type=perp/timeframe=1h",
        "raw_root": ROOT
        / "data/raw/mark_price_klines/exchange=binance/market_type=perp/timeframe=1h",
    },
    "funding": {
        "endpoint": "/fapi/v1/fundingRate",
        "normalized_root": ROOT
        / "data/normalized/funding_rates/exchange=binance/market_type=perp",
        "raw_root": ROOT
        / "data/raw/funding_rates/exchange=binance/market_type=perp",
    },
}
KLINE_COLUMNS = [
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


class RateLimiter:
    def __init__(self, requests_per_second: float) -> None:
        self.interval = 1.0 / requests_per_second
        self.lock = threading.Lock()
        self.next_time = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_time - now)
            self.next_time = max(now, self.next_time) + self.interval
        if delay:
            time.sleep(delay)


LIMITER = RateLimiter(5.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Persist the unlabeled 2026-07-01..2026-07-19 Binance USD-M "
            "freeze-gap tail from FAPI into the standard data lake."
        )
    )
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--attempts", type=int, default=7)
    parser.add_argument("--symbols", nargs="*")
    return parser.parse_args()


def request_json(
    endpoint: str,
    params: dict[str, Any] | None,
    *,
    timeout: float,
    attempts: int,
) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    url = f"{FAPI}{endpoint}{query}"
    last_error: Exception | None = None
    for attempt in range(attempts):
        LIMITER.wait()
        try:
            request = Request(url, headers={"User-Agent": UA})
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.loads(response.read())
        except HTTPError as exc:
            if exc.code not in {403, 418, 429, 500, 502, 503, 504}:
                body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"HTTP {exc.code} for {url}: {body[:500]}"
                ) from exc
            last_error = exc
        except (URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(30.0, 1.0 * 2**attempt))
    raise RuntimeError(f"request failed after {attempts} attempts: {url}") from last_error


def canonical_symbol(api_symbol: pd.Series) -> pd.Series:
    return api_symbol.str.removesuffix("USDT") + "/USDT:USDT"


def closed_end() -> pd.Timestamp:
    now = pd.Timestamp.now("UTC")
    return min(now.floor("h"), HARD_END)


def current_symbols(exchange_info: dict[str, Any]) -> list[str]:
    rows = exchange_info.get("symbols")
    if not isinstance(rows, list):
        raise RuntimeError("unexpected exchangeInfo payload")
    symbols = sorted(
        str(row["symbol"])
        for row in rows
        if row.get("contractType") == "PERPETUAL"
        and row.get("quoteAsset") == "USDT"
        and row.get("status") == "TRADING"
        and str(row.get("symbol", "")).endswith("USDT")
    )
    if len(symbols) < 400:
        raise RuntimeError(f"implausibly small USD-M universe: {len(symbols)}")
    return symbols


def fetch_symbol(
    symbol: str, *, end: pd.Timestamp, timeout: float, attempts: int
) -> dict[str, Any]:
    start_ms = int(START.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000) - 1
    common = {
        "symbol": symbol,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": 1500,
    }
    kline = request_json(
        "/fapi/v1/klines",
        {**common, "interval": "1h"},
        timeout=timeout,
        attempts=attempts,
    )
    mark = request_json(
        "/fapi/v1/markPriceKlines",
        {**common, "interval": "1h"},
        timeout=timeout,
        attempts=attempts,
    )
    for name, payload in (("kline_1h", kline), ("mark_1h", mark)):
        if not isinstance(payload, list):
            raise RuntimeError(f"unexpected {name} payload for {symbol}")
    return {"symbol": symbol, "kline_1h": kline, "mark_1h": mark}


def fetch_funding_bulk(
    *, end: pd.Timestamp, timeout: float, attempts: int
) -> list[dict[str, Any]]:
    cursor = int(START.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000) - 1
    rows: list[dict[str, Any]] = []
    while cursor <= end_ms:
        payload = request_json(
            "/fapi/v1/fundingRate",
            {"startTime": cursor, "endTime": end_ms, "limit": 1000},
            timeout=timeout,
            attempts=attempts,
        )
        if not isinstance(payload, list):
            raise RuntimeError("unexpected bulk funding payload")
        if not payload:
            break
        rows.extend(payload)
        last_time = max(int(row["fundingTime"]) for row in payload)
        if last_time < cursor:
            raise RuntimeError("bulk funding pagination did not advance")
        cursor = last_time + 1
        if len(payload) < 1000:
            break
    return rows


def parse_kline(results: list[dict[str, Any]], *, mark_price: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    for result in results:
        key = "mark_1h" if mark_price else "kline_1h"
        if not result[key]:
            continue
        frame = pd.DataFrame(result[key], columns=KLINE_COLUMNS)
        frame["api_symbol"] = result["symbol"]
        frames.append(frame)
    if not frames:
        raise RuntimeError("FAPI returned no kline rows")
    raw = pd.concat(frames, ignore_index=True)
    raw["open_time"] = pd.to_numeric(raw["open_time"], errors="raise")
    raw["close_time"] = pd.to_numeric(raw["close_time"], errors="raise")
    numeric = KLINE_COLUMNS[1:6] + KLINE_COLUMNS[7:11]
    for column in numeric:
        raw[column] = pd.to_numeric(raw[column], errors="raise")
    raw["trade_count"] = pd.to_numeric(raw["trade_count"], errors="raise").astype("Int64")
    normalized = pd.DataFrame(
        {
            "ts": pd.to_datetime(raw["open_time"], unit="ms", utc=True),
            "exchange": "binance",
            "symbol": canonical_symbol(raw["api_symbol"]),
            "market_type": "perp",
            "timeframe": "1h",
            "base_asset": raw["api_symbol"].str.removesuffix("USDT"),
            "quote_asset": "USDT",
            "open": raw["open"],
            "high": raw["high"],
            "low": raw["low"],
            "close": raw["close"],
        }
    )
    if not mark_price:
        normalized["volume"] = raw["volume"]
        normalized["quote_volume"] = raw["quote_volume"]
        normalized["trade_count"] = raw["trade_count"]
        normalized["taker_buy_volume"] = raw["taker_buy_volume"]
        normalized["taker_buy_quote_volume"] = raw["taker_buy_quote_volume"]
        normalized["vwap"] = (
            normalized["quote_volume"] / normalized["volume"].replace(0.0, np.nan)
        ).fillna(normalized["close"])
    normalized["is_closed"] = True
    normalized["source"] = (
        "binance_fapi_mark_price_kline_freeze_gap"
        if mark_price
        else "binance_fapi_kline_freeze_gap"
    )
    normalized["archive_month"] = MONTH
    normalized["archive_sha256"] = pd.NA
    return raw, normalized


def parse_funding(rows: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not rows:
        raise RuntimeError("FAPI returned no funding rows")
    raw = pd.DataFrame(rows)
    raw = raw.rename(columns={"symbol": "api_symbol"})
    raw["fundingTime"] = pd.to_numeric(raw["fundingTime"], errors="raise")
    raw["fundingRate"] = pd.to_numeric(raw["fundingRate"], errors="raise")
    raw["markPrice"] = pd.to_numeric(raw["markPrice"], errors="coerce")
    raw["ts"] = pd.to_datetime(raw["fundingTime"], unit="ms", utc=True)
    raw = raw.sort_values(["api_symbol", "ts"])
    forward = raw.groupby("api_symbol")["ts"].shift(-1) - raw["ts"]
    backward = raw["ts"] - raw.groupby("api_symbol")["ts"].shift(1)
    interval = forward.fillna(backward).dt.total_seconds() / 3600.0
    normalized = pd.DataFrame(
        {
            "ts": raw["ts"],
            "exchange": "binance",
            "symbol": canonical_symbol(raw["api_symbol"]),
            "market_type": "perp",
            "base_asset": raw["api_symbol"].str.removesuffix("USDT"),
            "quote_asset": "USDT",
            "funding_rate": raw["fundingRate"],
            "funding_interval_hours": interval,
            "next_funding_ts": raw["ts"] + pd.to_timedelta(interval, unit="h"),
            "mark_price": raw["markPrice"],
            "source": "binance_fapi_funding_freeze_gap",
            "archive_month": MONTH,
            "archive_sha256": pd.NA,
        }
    )
    return raw.drop(columns="ts"), normalized


def existing_keys(root: Path, target: Path) -> pd.DataFrame:
    paths = [
        path
        for path in root.glob("**/*.parquet")
        if path != target and "2026-07" in str(path)
    ]
    frames: list[pd.DataFrame] = []
    for path in paths:
        try:
            frame = pd.read_parquet(path, columns=["ts", "symbol"])
        except Exception:
            continue
        frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
        frame = frame.loc[(frame["ts"] >= START) & (frame["ts"] < HARD_END)]
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["ts", "symbol"])
    return pd.concat(frames, ignore_index=True).drop_duplicates(["ts", "symbol"])


def atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def persist_dataset(
    name: str, raw: pd.DataFrame, normalized: pd.DataFrame
) -> dict[str, Any]:
    config = DATASETS[name]
    normalized_path = Path(config["normalized_root"]) / (
        "source=binance_fapi_freeze_gap/month=2026-07/part.parquet"
    )
    raw_path = Path(config["raw_root"]) / (
        "source=binance_fapi_freeze_gap/month=2026-07/part.parquet"
    )
    if normalized_path.exists():
        previous = pd.read_parquet(normalized_path)
        previous["ts"] = pd.to_datetime(previous["ts"], utc=True)
        normalized = pd.concat([previous, normalized], ignore_index=True)
    normalized = normalized.sort_values(["ts", "symbol"]).drop_duplicates(
        ["ts", "symbol"], keep="last"
    )
    overlap = existing_keys(Path(config["normalized_root"]), normalized_path)
    if not overlap.empty:
        marked = normalized.merge(
            overlap.assign(_existing=True), on=["ts", "symbol"], how="left"
        )
        excluded = int(marked["_existing"].fillna(False).sum())
        normalized = marked.loc[marked["_existing"].isna()].drop(columns="_existing")
    else:
        excluded = 0
    atomic_parquet(raw, raw_path)
    atomic_parquet(normalized, normalized_path)
    return {
        "dataset": name,
        "raw_path": str(raw_path.relative_to(ROOT)),
        "raw_rows": len(raw),
        "raw_sha256": sha256(raw_path),
        "normalized_path": str(normalized_path.relative_to(ROOT)),
        "normalized_rows": len(normalized),
        "normalized_sha256": sha256(normalized_path),
        "existing_key_rows_excluded": excluded,
        "first_ts": normalized["ts"].min().isoformat() if len(normalized) else None,
        "last_ts": normalized["ts"].max().isoformat() if len(normalized) else None,
        "duplicate_keys": int(normalized.duplicated(["ts", "symbol"]).sum()),
    }


def main() -> None:
    args = parse_args()
    end = closed_end()
    if end <= START:
        raise RuntimeError("no closed freeze-gap bars are available")
    exchange_info = request_json(
        "/fapi/v1/exchangeInfo", None, timeout=args.timeout, attempts=args.attempts
    )
    symbols = current_symbols(exchange_info)
    if args.symbols:
        requested = {symbol.upper() for symbol in args.symbols}
        unknown = sorted(requested - set(symbols))
        if unknown:
            raise RuntimeError(f"requested symbols are not current USDT perpetuals: {unknown}")
        symbols = [symbol for symbol in symbols if symbol in requested]
    fetched_at = pd.Timestamp.now("UTC")
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                fetch_symbol,
                symbol,
                end=end,
                timeout=args.timeout,
                attempts=args.attempts,
            ): symbol
            for symbol in symbols
        }
        for index, future in enumerate(as_completed(futures), start=1):
            symbol = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001
                failures.append({"symbol": symbol, "error": repr(exc)})
                if len(failures) <= 10:
                    print(f"failure {symbol}: {exc!r}", flush=True)
            if index % 50 == 0 or index == len(futures):
                print(f"fapi_symbols {index}/{len(futures)} failures={len(failures)}", flush=True)
    if failures:
        raise RuntimeError(f"freeze-gap fetch failures: {failures[:10]}")
    print("fetching bulk funding history", flush=True)
    funding_rows = fetch_funding_bulk(
        end=end, timeout=args.timeout, attempts=args.attempts
    )
    raw_kline, normalized_kline = parse_kline(results, mark_price=False)
    raw_mark, normalized_mark = parse_kline(results, mark_price=True)
    raw_funding, normalized_funding = parse_funding(funding_rows)
    datasets = [
        persist_dataset("kline_1h", raw_kline, normalized_kline),
        persist_dataset("mark_1h", raw_mark, normalized_mark),
        persist_dataset("funding", raw_funding, normalized_funding),
    ]
    snapshot_dir = ARTIFACT_DIR / "freeze"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    exchange_path = snapshot_dir / "exchange_info_prefreeze_2026-07-18.json"
    exchange_path.write_text(
        json.dumps(exchange_info, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    manifest = {
        "family": "Binance-1H-Multi-Horizon-Cross-Sectional-ML-Allocator",
        "generated_at": fetched_at.isoformat(),
        "status": "PASS",
        "role": "freeze-gap unlabeled data preparation",
        "start": START.isoformat(),
        "closed_end_exclusive": end.isoformat(),
        "hard_end_exclusive": HARD_END.isoformat(),
        "symbols_requested": len(symbols),
        "symbols_succeeded": len(results),
        "symbols_failed": 0,
        "exchange_info_path": str(exchange_path.relative_to(ROOT)),
        "exchange_info_sha256": sha256(exchange_path),
        "freeze_gap_outcomes_read": False,
        "prospective_oos_outcomes_read": False,
        "datasets": datasets,
        "blockers": [],
    }
    manifest_path = snapshot_dir / "freeze_gap_data_manifest_2026-07-18.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
