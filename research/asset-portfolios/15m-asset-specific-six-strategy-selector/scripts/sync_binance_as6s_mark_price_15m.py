from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/15m-asset-specific-six-strategy-selector"
RAW_ROOT = (
    ROOT
    / "data/raw/mark_price_klines/exchange=binance/market_type=perp/timeframe=15m"
)
NORMALIZED_ROOT = (
    ROOT
    / "data/normalized/mark_price_klines/exchange=binance/market_type=perp/timeframe=15m"
)
OUTPUT = FAMILY_DIR / "artifacts/binance_as6s_mark_price_15m_quality_2026-07-15.json"
END = pd.Timestamp("2026-07-14T09:00:00Z")
DEFAULT_START = pd.Timestamp("2024-07-14T00:00:00Z")
SYMBOLS = {
    "BTCUSDT": ("BTC", "btc_usdt_usdt", DEFAULT_START),
    "ETHUSDT": ("ETH", "eth_usdt_usdt", DEFAULT_START),
    "SOLUSDT": ("SOL", "sol_usdt_usdt", DEFAULT_START),
    "BNBUSDT": ("BNB", "bnb_usdt_usdt", DEFAULT_START),
    "TRXUSDT": ("TRX", "trx_usdt_usdt", DEFAULT_START),
    "HYPEUSDT": (
        "HYPE",
        "hype_usdt_usdt",
        pd.Timestamp("2025-05-30T10:30:00Z"),
    ),
}
INTERVAL_MS = 15 * 60 * 1000


def fetch(symbol: str, start: pd.Timestamp) -> pd.DataFrame:
    rows: list[list[Any]] = []
    cursor = int(start.timestamp() * 1000)
    end_ms = int(END.timestamp() * 1000)
    while cursor < end_ms:
        params = urlencode(
            {
                "symbol": symbol,
                "interval": "15m",
                "startTime": cursor,
                "endTime": end_ms - 1,
                "limit": 1500,
            }
        )
        request = Request(
            f"https://fapi.binance.com/fapi/v1/markPriceKlines?{params}",
            headers={"User-Agent": "quant-research-lab-as6s-mark-price/0.1"},
        )
        with urlopen(request, timeout=60) as response:  # noqa: S310
            payload = json.load(response)
        if not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1][0]) + INTERVAL_MS
        if next_cursor <= cursor:
            raise RuntimeError(f"{symbol} pagination did not advance")
        cursor = next_cursor
        time.sleep(0.03)
    columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "ignore_volume",
        "close_time",
        "ignore_quote_volume",
        "ignore_count",
        "ignore_taker_volume",
        "ignore_taker_quote_volume",
        "ignore",
    ]
    frame = pd.DataFrame(rows, columns=columns)
    if frame.empty:
        raise RuntimeError(f"no mark-price bars returned for {symbol}")
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return (
        frame.loc[
            (frame["open_time"] >= start)
            & (frame["open_time"] < END)
            & (frame["close_time"] < END)
        ]
        .drop_duplicates("open_time", keep="last")
        .sort_values("open_time")
        .reset_index(drop=True)
    )


def normalized(symbol: str, frame: pd.DataFrame) -> pd.DataFrame:
    base, _slug, _start = SYMBOLS[symbol]
    output = frame.rename(columns={"open_time": "ts"})[
        ["ts", "open", "high", "low", "close"]
    ].copy()
    output.insert(1, "exchange", "binance")
    output.insert(2, "symbol", f"{base}/USDT:USDT")
    output.insert(3, "market_type", "perp")
    output.insert(4, "timeframe", "15m")
    output["source"] = "binance_mark_price_klines_api"
    return output


def write_daily(root: Path, slug: str, frame: pd.DataFrame) -> int:
    work = frame.copy()
    work["date"] = work["ts"].dt.date.astype(str)
    count = 0
    for date, group in work.groupby("date", sort=True):
        path = root / f"date={date}" / f"symbol={slug}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        group.drop(columns="date").to_parquet(path, index=False)
        count += 1
    return count


def quality(frame: pd.DataFrame, start: pd.Timestamp) -> dict[str, Any]:
    expected = pd.date_range(start, END - pd.Timedelta(minutes=15), freq="15min")
    actual = pd.DatetimeIndex(frame["ts"])
    missing = expected.difference(actual)
    extras = actual.difference(expected)
    duplicates = int(frame.duplicated("ts").sum())
    null_rows = int(frame[["open", "high", "low", "close"]].isna().any(axis=1).sum())
    violations = int((frame["high"] < frame[["open", "close"]].max(axis=1)).sum())
    violations += int((frame["low"] > frame[["open", "close"]].min(axis=1)).sum())
    violations += int((frame["high"] < frame["low"]).sum())
    violations += int((frame[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
    blockers = len(missing) + len(extras) + duplicates + null_rows + violations
    return {
        "rows": len(frame),
        "first_ts": frame["ts"].iloc[0].isoformat(),
        "last_ts": frame["ts"].iloc[-1].isoformat(),
        "missing_bars": len(missing),
        "extra_bars": len(extras),
        "duplicate_bars": duplicates,
        "critical_null_rows": null_rows,
        "ohlc_violations": violations,
        "blocker_count": blockers,
        "missing_examples": [value.isoformat() for value in missing[:10]],
    }


def main() -> None:
    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Binance USD-M /fapi/v1/markPriceKlines",
        "timeframe": "15m",
        "cutoff_exclusive": END.isoformat(),
        "future_oos_read": False,
        "symbols": {},
    }
    total_blockers = 0
    for symbol, (_base, slug, start) in SYMBOLS.items():
        print(f"sync {symbol} mark-price {start} -> {END}", flush=True)
        raw = fetch(symbol, start)
        norm = normalized(symbol, raw)
        raw_for_write = norm.copy()
        raw_for_write["source"] = "binance_mark_price_klines_api"
        writes = {
            "raw_partitions": write_daily(RAW_ROOT, slug, raw_for_write),
            "normalized_partitions": write_daily(NORMALIZED_ROOT, slug, norm),
        }
        audit = quality(norm, start)
        total_blockers += audit["blocker_count"]
        report["symbols"][symbol] = {"writes": writes, "quality": audit}
    report["total_blocker_count"] = total_blockers
    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(OUTPUT.relative_to(ROOT)),
                "total_blocker_count": total_blockers,
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
