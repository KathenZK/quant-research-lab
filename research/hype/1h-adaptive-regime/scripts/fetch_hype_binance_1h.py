from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/hype/1h-adaptive-regime"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"

SYMBOL = "HYPEUSDT"
DISPLAY_SYMBOL = "HYPE/USDT:USDT"
INTERVAL = "1h"
INTERVAL_MS = 60 * 60 * 1000
BASE_URL = "https://fapi.binance.com"
KLINES_PATH = "/fapi/v1/klines"
FUNDING_PATH = "/fapi/v1/fundingRate"
EXCHANGE_INFO_PATH = "/fapi/v1/exchangeInfo"
TIME_PATH = "/fapi/v1/time"
USER_AGENT = "quant-research-lab-hype-1h/0.1"

RAW_ROOT = (
    ROOT
    / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=1h"
)
NORMALIZED_ROOT = (
    ROOT
    / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h"
)
FUNDING_ROOT = (
    ROOT
    / "data/normalized/funding/exchange=binance/market_type=perp"
    / "symbol=hype_usdt_usdt"
)
FILE_NAME = "symbol=hype_usdt_usdt.parquet"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch and audit all closed Binance HYPEUSDT perpetual 1h bars."
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--timeout", type=float, default=45.0)
    return parser.parse_args()


def request_json(
    path: str,
    *,
    params: dict[str, object] | None = None,
    timeout: float = 45.0,
    attempts: int = 6,
) -> object:
    query = f"?{urlencode(params)}" if params else ""
    url = f"{BASE_URL}{path}{query}"
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(min(8.0, 0.75 * 2**attempt))
    raise RuntimeError(f"Binance request failed after {attempts} attempts: {url}") from last_error


def server_time_ms(timeout: float) -> int:
    payload = request_json(TIME_PATH, timeout=timeout)
    if not isinstance(payload, dict) or "serverTime" not in payload:
        raise RuntimeError(f"Unexpected server-time payload: {payload!r}")
    return int(payload["serverTime"])


def closed_bar_mask(close_time: pd.Series, cutoff_ms: int) -> pd.Series:
    """Return true only when Binance server time is after the kline close time.

    Compare datetimes directly. Pandas can preserve ``datetime64[ms]`` when data
    originates from millisecond epochs, so integer conversion followed by a
    nanosecond divisor is not unit-stable.
    """
    cutoff = pd.to_datetime(cutoff_ms, unit="ms", utc=True)
    return pd.to_datetime(close_time, utc=True) < cutoff


def fetch_klines(*, timeout: float, cutoff_ms: int) -> pd.DataFrame:
    rows: list[list[object]] = []
    cursor = 0
    while cursor < cutoff_ms:
        payload = request_json(
            KLINES_PATH,
            params={
                "symbol": SYMBOL,
                "interval": INTERVAL,
                "startTime": cursor,
                "endTime": cutoff_ms,
                "limit": 1500,
            },
            timeout=timeout,
        )
        if not isinstance(payload, list) or not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1][0]) + INTERVAL_MS
        if next_cursor <= cursor:
            raise RuntimeError("Binance kline pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1500:
            break
        time.sleep(0.05)
    if not rows:
        raise RuntimeError("Binance returned no HYPEUSDT 1h klines")
    frame = pd.DataFrame(
        rows,
        columns=[
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
        ],
    )
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    numeric = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_volume",
        "taker_buy_quote_volume",
    ]
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["source"] = "binance_futures_kline_api"
    frame["is_closed"] = closed_bar_mask(frame["close_time"], cutoff_ms)
    return frame.sort_values("open_time").reset_index(drop=True)


def normalize_klines(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.loc[raw["is_closed"]].copy()
    frame = frame.rename(columns={"open_time": "ts"})
    frame["exchange"] = "binance"
    frame["symbol"] = DISPLAY_SYMBOL
    frame["market_type"] = "perp"
    frame["timeframe"] = INTERVAL
    frame["base_asset"] = "HYPE"
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


def fetch_funding(
    *,
    timeout: float,
    start_ms: int,
    cutoff_ms: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    cursor = start_ms
    while cursor <= cutoff_ms:
        payload = request_json(
            FUNDING_PATH,
            params={
                "symbol": SYMBOL,
                "startTime": cursor,
                "endTime": cutoff_ms,
                "limit": 1000,
            },
            timeout=timeout,
        )
        if not isinstance(payload, list) or not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise RuntimeError("Binance funding pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1000:
            break
        time.sleep(0.05)
    if not rows:
        return pd.DataFrame(columns=["ts", "funding_rate", "mark_price", "source"])
    frame = pd.DataFrame(rows)
    frame["ts"] = pd.to_datetime(frame["fundingTime"], unit="ms", utc=True)
    frame["funding_rate"] = pd.to_numeric(frame["fundingRate"], errors="coerce")
    frame["mark_price"] = pd.to_numeric(frame.get("markPrice"), errors="coerce")
    frame["source"] = "binance_futures_funding_rate_api"
    return (
        frame[["ts", "funding_rate", "mark_price", "source"]]
        .drop_duplicates("ts", keep="last")
        .sort_values("ts")
        .reset_index(drop=True)
    )


def fetch_contract_snapshot(*, timeout: float) -> dict[str, object]:
    payload = request_json(EXCHANGE_INFO_PATH, timeout=timeout)
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected exchangeInfo payload")
    matches = [item for item in payload.get("symbols", []) if item.get("symbol") == SYMBOL]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {SYMBOL} exchangeInfo row, got {len(matches)}")
    symbol = matches[0]
    filters = {item["filterType"]: item for item in symbol.get("filters", [])}
    return {
        "symbol": SYMBOL,
        "status": symbol.get("status"),
        "contract_type": symbol.get("contractType"),
        "onboard_date": pd.to_datetime(symbol.get("onboardDate"), unit="ms", utc=True).isoformat(),
        "price_precision": symbol.get("pricePrecision"),
        "quantity_precision": symbol.get("quantityPrecision"),
        "margin_asset": symbol.get("marginAsset"),
        "price_filter": filters.get("PRICE_FILTER"),
        "lot_size": filters.get("LOT_SIZE"),
        "market_lot_size": filters.get("MARKET_LOT_SIZE"),
        "min_notional": filters.get("MIN_NOTIONAL"),
        "percent_price": filters.get("PERCENT_PRICE"),
    }


def audit_data(
    raw: pd.DataFrame, normalized: pd.DataFrame, *, cutoff_ms: int
) -> dict[str, object]:
    duplicate_raw = int(raw.duplicated("open_time").sum())
    duplicate_normalized = int(normalized.duplicated("ts").sum())
    expected = pd.date_range(
        normalized["ts"].iloc[0], normalized["ts"].iloc[-1], freq="1h"
    )
    missing = expected.difference(pd.DatetimeIndex(normalized["ts"]))
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
        "source",
        "is_closed",
    ]
    nulls = {column: int(normalized[column].isna().sum()) for column in critical}
    cutoff = pd.to_datetime(cutoff_ms, unit="ms", utc=True)
    violations = {
        "high_lt_open_or_close": int(
            (normalized["high"] < normalized[["open", "close"]].max(axis=1)).sum()
        ),
        "low_gt_open_or_close": int(
            (normalized["low"] > normalized[["open", "close"]].min(axis=1)).sum()
        ),
        "high_lt_low": int((normalized["high"] < normalized["low"]).sum()),
        "nonpositive_ohlc": int(
            ((normalized[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum()
        ),
        "negative_volume": int((normalized["volume"] < 0).sum()),
        "negative_quote_volume": int((normalized["quote_volume"] < 0).sum()),
        "negative_trade_count": int((normalized["trade_count"] < 0).sum()),
        "vwap_outside_hilo": int(
            (
                (normalized["volume"] > 0)
                & (
                    (normalized["vwap"] < normalized["low"] * 0.999999)
                    | (normalized["vwap"] > normalized["high"] * 1.000001)
                )
            ).sum()
        ),
        "normalized_bar_not_closed_at_cutoff": int(
            ((normalized["ts"] + pd.Timedelta(hours=1)) > cutoff).sum()
        ),
        "raw_closed_flag_at_or_after_cutoff": int(
            (
                raw.loc[raw["is_closed"], "close_time"]
                >= cutoff
            ).sum()
        ),
    }
    raw_closed = raw.loc[raw["is_closed"]].sort_values("open_time").reset_index(drop=True)
    compare_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
    ]
    mismatch: dict[str, int] = {}
    for column in compare_columns:
        left = raw_closed[column].to_numpy("float64")
        right = normalized[column].to_numpy("float64")
        tolerance = 0.0 if column == "trade_count" else 1e-12
        mismatch[column] = int((~np.isclose(left, right, rtol=0.0, atol=tolerance)).sum())
    quality = {
        "rows_raw": int(len(raw)),
        "rows_raw_closed": int(raw["is_closed"].sum()),
        "rows_closed_normalized": int(len(normalized)),
        "first_ts": normalized["ts"].iloc[0].isoformat(),
        "last_ts": normalized["ts"].iloc[-1].isoformat(),
        "expected_rows_between_endpoints": int(len(expected)),
        "missing_bars": int(len(missing)),
        "first_missing": missing[0].isoformat() if len(missing) else None,
        "duplicate_raw": duplicate_raw,
        "duplicate_normalized": duplicate_normalized,
        "critical_nulls": nulls,
        "ohlcv_violations": violations,
        "raw_normalized_mismatch": mismatch,
        "closed_values": {
            str(key): int(value)
            for key, value in normalized["is_closed"].value_counts(dropna=False).items()
        },
        "source_values": {
            str(key): int(value)
            for key, value in normalized["source"].value_counts(dropna=False).items()
        },
        "zero_volume_bars": int((normalized["volume"] == 0).sum()),
    }
    blockers = (
        duplicate_raw
        + duplicate_normalized
        + len(missing)
        + sum(nulls.values())
        + sum(violations.values())
        + sum(mismatch.values())
        + int(set(normalized["is_closed"].unique()) != {True})
    )
    quality["blocker_count"] = int(blockers)
    if blockers:
        raise RuntimeError(f"HYPEUSDT 1h data-quality blockers found: {quality}")
    return quality


def write_daily_partitions(raw: pd.DataFrame, normalized: pd.DataFrame) -> dict[str, int]:
    raw_closed = raw.loc[raw["is_closed"]].copy()
    raw_closed["date"] = raw_closed["open_time"].dt.date
    normalized = normalized.copy()
    normalized["date"] = normalized["ts"].dt.date
    raw_count = 0
    normalized_count = 0
    for partition_date, group in raw_closed.groupby("date", sort=True):
        path = RAW_ROOT / f"date={partition_date}" / FILE_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        group.drop(columns="date").to_parquet(path, index=False)
        raw_count += 1
    for partition_date, group in normalized.groupby("date", sort=True):
        path = NORMALIZED_ROOT / f"date={partition_date}" / FILE_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        group.drop(columns="date").to_parquet(path, index=False)
        normalized_count += 1
    return {"raw_partitions": raw_count, "normalized_partitions": normalized_count}


def write_outputs(
    *,
    raw: pd.DataFrame,
    normalized: pd.DataFrame,
    funding: pd.DataFrame,
    quality: dict[str, object],
    contract: dict[str, object],
    server_ms: int,
) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    partitions = write_daily_partitions(raw, normalized)
    funding_path = FUNDING_ROOT / "funding.parquet"
    funding_path.parent.mkdir(parents=True, exist_ok=True)
    funding.to_parquet(funding_path, index=False)
    normalized.to_parquet(ARTIFACT_DIR / "hype_binance_1h_closed_klines.parquet", index=False)
    funding.to_csv(ARTIFACT_DIR / "hype_binance_funding_history.csv", index=False)

    funding_gaps = funding["ts"].diff().dropna() if len(funding) else pd.Series(dtype="timedelta64[ns]")
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "binance_server_time": pd.to_datetime(server_ms, unit="ms", utc=True).isoformat(),
        "market": "Binance USD-M Futures",
        "symbol": SYMBOL,
        "display_symbol": DISPLAY_SYMBOL,
        "timeframe": INTERVAL,
        "data_quality": quality,
        "partitions": partitions,
        "paths": {
            "raw_root": str(RAW_ROOT.relative_to(ROOT)),
            "normalized_root": str(NORMALIZED_ROOT.relative_to(ROOT)),
            "funding": str(funding_path.relative_to(ROOT)),
        },
        "funding": {
            "rows": int(len(funding)),
            "first_ts": funding["ts"].iloc[0].isoformat() if len(funding) else None,
            "last_ts": funding["ts"].iloc[-1].isoformat() if len(funding) else None,
            "null_rates": int(funding["funding_rate"].isna().sum()) if len(funding) else 0,
            "max_gap_hours": (
                float(funding_gaps.max().total_seconds() / 3600.0)
                if len(funding_gaps)
                else None
            ),
            "sum_rate": float(funding["funding_rate"].sum()) if len(funding) else 0.0,
        },
        "contract_snapshot": contract,
    }
    (ARTIFACT_DIR / "hype_binance_1h_data_quality.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2, ensure_ascii=False), flush=True)


def load_existing() -> tuple[pd.DataFrame, pd.DataFrame] | None:
    raw_files = sorted(RAW_ROOT.glob(f"date=*/{FILE_NAME}"))
    normalized_files = sorted(NORMALIZED_ROOT.glob(f"date=*/{FILE_NAME}"))
    if not raw_files or not normalized_files:
        return None
    raw = pd.concat([pd.read_parquet(path) for path in raw_files], ignore_index=True)
    normalized = pd.concat(
        [pd.read_parquet(path) for path in normalized_files], ignore_index=True
    )
    raw["open_time"] = pd.to_datetime(raw["open_time"], utc=True)
    raw["close_time"] = pd.to_datetime(raw["close_time"], utc=True)
    normalized["ts"] = pd.to_datetime(normalized["ts"], utc=True)
    return raw, normalized


def main() -> None:
    args = parse_args()
    server_ms = server_time_ms(args.timeout)
    existing = None if args.refresh else load_existing()
    if existing is None:
        raw = fetch_klines(timeout=args.timeout, cutoff_ms=server_ms)
        normalized = normalize_klines(raw)
    else:
        raw, _stored_normalized = existing
        raw["is_closed"] = closed_bar_mask(raw["close_time"], server_ms)
        normalized = normalize_klines(raw)
    quality = audit_data(raw, normalized, cutoff_ms=server_ms)
    first_ms = int(normalized["ts"].iloc[0].timestamp() * 1000)
    funding = fetch_funding(
        timeout=args.timeout,
        start_ms=first_ms,
        cutoff_ms=server_ms,
    )
    if funding["funding_rate"].isna().any():
        raise RuntimeError("Funding history contains null funding rates")
    contract = fetch_contract_snapshot(timeout=args.timeout)
    write_outputs(
        raw=raw,
        normalized=normalized,
        funding=funding,
        quality=quality,
        contract=contract,
        server_ms=server_ms,
    )


if __name__ == "__main__":
    main()
