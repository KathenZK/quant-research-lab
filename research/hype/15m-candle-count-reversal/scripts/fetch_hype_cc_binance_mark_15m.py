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
FAMILY_DIR = ROOT / "research/hype/15m-candle-count-reversal"
ARTIFACT_PATH = (
    FAMILY_DIR / "artifacts/hype_cc_binance_mark_15m_refresh_2026-07-14.json"
)
OHLCV_ROOT = (
    ROOT / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
)
RAW_ROOT = (
    ROOT / "data/raw/mark_price_klines/exchange=binance/market_type=perp/timeframe=15m"
)
NORMALIZED_ROOT = (
    ROOT
    / "data/normalized/mark_price_klines/exchange=binance/market_type=perp/timeframe=15m"
)
FILE_NAME = "symbol=hype_usdt_usdt.parquet"
BASE_URL = "https://fapi.binance.com"
MARK_PATH = "/fapi/v1/markPriceKlines"
SYMBOL = "HYPEUSDT"
DISPLAY_SYMBOL = "HYPE/USDT:USDT"
INTERVAL = "15m"
INTERVAL_MS = 15 * 60 * 1000
USER_AGENT = "quant-research-lab-hype-cc-mark-refresh/0.1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh and audit Binance HYPEUSDT 15m mark-price candles."
    )
    parser.add_argument("--timeout", type=float, default=45.0)
    return parser.parse_args()


def request_json(
    path: str,
    *,
    params: dict[str, object],
    timeout: float,
    attempts: int = 6,
) -> object:
    url = f"{BASE_URL}{path}?{urlencode(params)}"
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
    raise RuntimeError(
        f"Binance request failed after {attempts} attempts: {url}"
    ) from last_error


def ohlcv_bounds() -> tuple[pd.Timestamp, pd.Timestamp]:
    files = sorted(OHLCV_ROOT.glob(f"date=*/{FILE_NAME}"))
    if not files:
        raise FileNotFoundError(f"no HYPE OHLCV partitions under {OHLCV_ROOT}")
    first = pd.read_parquet(files[0], columns=["ts"])
    last = pd.read_parquet(files[-1], columns=["ts"])
    start = pd.to_datetime(first["ts"], utc=True).min()
    end = pd.to_datetime(last["ts"], utc=True).max()
    if pd.isna(start) or pd.isna(end):
        raise RuntimeError("OHLCV bounds contain null timestamps")
    return pd.Timestamp(start), pd.Timestamp(end)


def fetch_mark(
    *, start: pd.Timestamp, end: pd.Timestamp, timeout: float
) -> pd.DataFrame:
    rows: list[list[object]] = []
    cursor = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    while cursor <= end_ms:
        payload = request_json(
            MARK_PATH,
            params={
                "symbol": SYMBOL,
                "interval": INTERVAL,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1500,
            },
            timeout=timeout,
        )
        if not isinstance(payload, list) or not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1][0]) + INTERVAL_MS
        if next_cursor <= cursor:
            raise RuntimeError("Binance mark-price pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1500:
            break
        time.sleep(0.05)
    if not rows:
        raise RuntimeError("Binance returned no HYPEUSDT mark-price candles")

    frame = pd.DataFrame(
        rows,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "ignore_1",
            "close_time",
            "ignore_2",
            "ignore_3",
            "ignore_4",
            "ignore_5",
            "ignore_6",
        ],
    )
    frame["ts"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["exchange"] = "binance"
    frame["symbol"] = DISPLAY_SYMBOL
    frame["market_type"] = "perp"
    frame["timeframe"] = INTERVAL
    frame["source"] = "binance_mark_price_klines"
    return (
        frame[
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
                "source",
            ]
        ]
        .sort_values("ts")
        .drop_duplicates("ts", keep="last")
        .reset_index(drop=True)
    )


def load_existing(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    files = sorted(NORMALIZED_ROOT.glob(f"date=*/{FILE_NAME}"))
    if not files:
        return pd.DataFrame()
    frame = pd.concat((pd.read_parquet(path) for path in files), ignore_index=True)
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    return frame.loc[frame["ts"].between(start, end)].sort_values("ts")


def audit(
    frame: pd.DataFrame,
    existing: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, object]:
    expected = pd.date_range(start, end, freq="15min", tz="UTC")
    missing = expected.difference(pd.DatetimeIndex(frame["ts"]))
    duplicate = int(frame.duplicated("ts").sum())
    nulls = {
        column: int(frame[column].isna().sum())
        for column in ("ts", "open", "high", "low", "close", "source")
    }
    violations = {
        "high_lt_open_or_close": int(
            (frame["high"] < frame[["open", "close"]].max(axis=1)).sum()
        ),
        "low_gt_open_or_close": int(
            (frame["low"] > frame[["open", "close"]].min(axis=1)).sum()
        ),
        "high_lt_low": int((frame["high"] < frame["low"]).sum()),
        "nonpositive_ohlc": int(
            ((frame[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum()
        ),
    }

    overlap_rows = 0
    overlap_mismatches = {column: 0 for column in ("open", "high", "low", "close")}
    if not existing.empty:
        overlap = existing[["ts", "open", "high", "low", "close"]].merge(
            frame[["ts", "open", "high", "low", "close"]],
            on="ts",
            suffixes=("_existing", "_api"),
        )
        overlap_rows = len(overlap)
        for column in overlap_mismatches:
            overlap_mismatches[column] = int(
                (
                    ~np.isclose(
                        overlap[f"{column}_existing"].astype(float),
                        overlap[f"{column}_api"].astype(float),
                        rtol=0.0,
                        atol=1e-10,
                    )
                ).sum()
            )

    blocker_count = (
        len(missing) + duplicate + sum(nulls.values()) + sum(violations.values())
    )
    summary = {
        "rows": int(len(frame)),
        "first_ts": frame["ts"].iloc[0].isoformat(),
        "last_ts": frame["ts"].iloc[-1].isoformat(),
        "expected_rows": int(len(expected)),
        "missing_bars": int(len(missing)),
        "first_missing": missing[0].isoformat() if len(missing) else None,
        "duplicate_ts": duplicate,
        "critical_nulls": nulls,
        "ohlc_violations": violations,
        "existing_overlap_rows": int(overlap_rows),
        "existing_overlap_mismatches": overlap_mismatches,
        "blocker_count": int(blocker_count),
    }
    if blocker_count:
        raise RuntimeError(f"mark-price data-quality blockers: {summary}")
    return summary


def write_partitions(frame: pd.DataFrame) -> int:
    output = frame.copy()
    output["date"] = output["ts"].dt.date
    count = 0
    for partition_date, group in output.groupby("date", sort=True):
        payload = group.drop(columns="date")
        for root in (RAW_ROOT, NORMALIZED_ROOT):
            path = root / f"date={partition_date}" / FILE_NAME
            path.parent.mkdir(parents=True, exist_ok=True)
            payload.to_parquet(path, index=False)
        count += 1
    return count


def main() -> None:
    args = parse_args()
    start, end = ohlcv_bounds()
    existing = load_existing(start, end)
    frame = fetch_mark(start=start, end=end, timeout=args.timeout)
    summary = audit(frame, existing, start=start, end=end)
    partitions = write_partitions(frame)
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "market": "Binance USD-M Futures",
        "symbol": SYMBOL,
        "timeframe": INTERVAL,
        "source_endpoint": f"{BASE_URL}{MARK_PATH}",
        "data_quality": summary,
        "partitions_written_to_each_root": partitions,
        "raw_root": str(RAW_ROOT.relative_to(ROOT)),
        "normalized_root": str(NORMALIZED_ROOT.relative_to(ROOT)),
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Wrote {ARTIFACT_PATH}")


if __name__ == "__main__":
    main()
