from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import duckdb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / (
    "research/asset-portfolios/1h-multi-horizon-cross-sectional-ml-allocator"
)
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
API_ROOT = "https://fapi.binance.com"
USER_AGENT = "quant-research-lab-bin-1h-mhcsml-api-gap-repair/0.1"
START = pd.Timestamp("2020-01-01T00:00:00Z")
END = pd.Timestamp("2026-07-01T00:00:00Z")
COLUMNS = [
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
DATASETS = {
    "kline_1h": {
        "endpoint": "/fapi/v1/klines",
        "normalized_glob": ROOT
        / "data/normalized/ohlcv/exchange=binance/market_type=perp/"
        "timeframe=1h/**/*.parquet",
        "raw_root": ROOT
        / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
        "normalized_root": ROOT
        / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
    },
    "mark_1h": {
        "endpoint": "/fapi/v1/markPriceKlines",
        "normalized_glob": ROOT
        / "data/normalized/mark_price_klines/exchange=binance/market_type=perp/"
        "timeframe=1h/**/*.parquet",
        "raw_root": ROOT
        / "data/raw/mark_price_klines/exchange=binance/market_type=perp/"
        "timeframe=1h",
        "normalized_root": ROOT
        / "data/normalized/mark_price_klines/exchange=binance/market_type=perp/"
        "timeframe=1h",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Repair remaining Binance USD-M history gaps through FAPI."
    )
    parser.add_argument(
        "--datasets", nargs="+", choices=sorted(DATASETS), default=sorted(DATASETS)
    )
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--attempts", type=int, default=6)
    parser.add_argument("--request-delay", type=float, default=0.10)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def gaps(dataset: str) -> pd.DataFrame:
    path = Path(DATASETS[dataset]["normalized_glob"])
    connection = duckdb.connect()
    result = connection.execute(
        f"""
        WITH ordered AS (
            SELECT
                symbol,
                ts,
                lag(ts) OVER (PARTITION BY symbol ORDER BY ts) AS previous_ts
            FROM read_parquet(
                '{sql_path(path)}', hive_partitioning=false, union_by_name=true
            )
            WHERE ts >= TIMESTAMPTZ '{START.isoformat()}'
              AND ts < TIMESTAMPTZ '{END.isoformat()}'
        )
        SELECT
            symbol,
            previous_ts + INTERVAL 1 HOUR AS gap_start,
            ts AS gap_end_exclusive,
            date_diff('hour', previous_ts, ts) - 1 AS missing_hours
        FROM ordered
        WHERE date_diff('hour', previous_ts, ts) > 1
        ORDER BY symbol, gap_start
        """
    ).fetch_df()
    connection.close()
    return result


def request_payload(
    url: str,
    *,
    timeout: float,
    attempts: int,
    request_delay: float,
) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            time.sleep(request_delay)
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except HTTPError as exc:
            if exc.code not in {418, 429, 500, 502, 503, 504}:
                raise
            last_error = exc
        except (URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(30.0, 1.0 * 2**attempt))
    raise RuntimeError(f"request failed after {attempts} attempts: {url}") from last_error


def archive_symbol(symbol: str) -> str:
    return f"{symbol.split('/')[0]}USDT"


def parse_rows(payload: bytes) -> pd.DataFrame:
    values = json.loads(payload)
    if not isinstance(values, list):
        raise RuntimeError(f"unexpected Binance API response: {values}")
    frame = pd.DataFrame(values, columns=COLUMNS)
    if frame.empty:
        return frame
    frame["open_time"] = pd.to_numeric(frame["open_time"], errors="raise")
    frame["close_time"] = pd.to_numeric(frame["close_time"], errors="raise")
    for column in COLUMNS[1:6] + COLUMNS[7:12]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    return frame


def fetch_gap(
    dataset: str,
    row: Any,
    *,
    timeout: float,
    attempts: int,
    request_delay: float,
) -> dict[str, Any]:
    symbol = str(row.symbol)
    api_symbol = archive_symbol(symbol)
    start = pd.Timestamp(row.gap_start)
    end = pd.Timestamp(row.gap_end_exclusive)
    missing_hours = int(row.missing_hours)
    parameters = {
        "symbol": api_symbol,
        "interval": "1h",
        "startTime": int(start.timestamp() * 1000),
        "endTime": int(end.timestamp() * 1000) - 1,
        "limit": min(1500, missing_hours + 2),
    }
    endpoint = str(DATASETS[dataset]["endpoint"])
    url = f"{API_ROOT}{endpoint}?{urlencode(parameters)}"
    payload = request_payload(
        url,
        timeout=timeout,
        attempts=attempts,
        request_delay=request_delay,
    )
    frame = parse_rows(payload)
    if not frame.empty:
        frame = frame.loc[
            frame["open_time"].ge(start) & frame["open_time"].lt(end)
        ].copy()
    return {
        "dataset": dataset,
        "symbol": symbol,
        "api_symbol": api_symbol,
        "gap_start": start.isoformat(),
        "gap_end_exclusive": end.isoformat(),
        "expected_hours": missing_hours,
        "returned_hours": len(frame),
        "request_url": url,
        "response_sha256": hashlib.sha256(payload).hexdigest(),
        "raw": frame,
    }


def normalize(dataset: str, result: dict[str, Any]) -> pd.DataFrame:
    frame = result["raw"].copy()
    if frame.empty:
        return frame
    api_symbol = str(result["api_symbol"])
    frame["ts"] = frame["open_time"]
    frame["exchange"] = "binance"
    frame["symbol"] = result["symbol"]
    frame["market_type"] = "perp"
    frame["timeframe"] = "1h"
    frame["base_asset"] = api_symbol.removesuffix("USDT")
    frame["quote_asset"] = "USDT"
    frame["is_closed"] = True
    frame["source"] = (
        "binance_fapi_mark_price_kline_gap_repair"
        if dataset == "mark_1h"
        else "binance_fapi_kline_gap_repair"
    )
    frame["response_sha256"] = result["response_sha256"]
    common = [
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
    ]
    if dataset == "mark_1h":
        return frame[common + ["is_closed", "source", "response_sha256"]]
    frame["vwap"] = frame["quote_volume"] / frame["volume"].replace(0.0, np.nan)
    frame["vwap"] = frame["vwap"].fillna(frame["close"])
    return frame[
        common
        + [
            "volume",
            "quote_volume",
            "trade_count",
            "taker_buy_volume",
            "taker_buy_quote_volume",
            "vwap",
            "is_closed",
            "source",
            "response_sha256",
        ]
    ]


def atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    os.replace(temporary, path)


def persist(dataset: str, results: list[dict[str, Any]]) -> None:
    usable = [result for result in results if not result["raw"].empty]
    if not usable:
        return
    normalized = pd.concat([normalize(dataset, result) for result in usable])
    raw_frames = []
    for result in usable:
        raw = result["raw"].copy()
        raw["symbol"] = result["symbol"]
        raw["api_symbol"] = result["api_symbol"]
        raw["gap_start"] = result["gap_start"]
        raw["gap_end_exclusive"] = result["gap_end_exclusive"]
        raw["response_sha256"] = result["response_sha256"]
        raw["source"] = "binance_fapi_gap_repair"
        raw_frames.append(raw)
    raw = pd.concat(raw_frames, ignore_index=True)
    if normalized.duplicated(["ts", "symbol"]).any():
        raise RuntimeError(f"duplicate normalized API repair keys for {dataset}")
    normalized["month"] = normalized["ts"].dt.strftime("%Y-%m")
    raw["month"] = raw["open_time"].dt.strftime("%Y-%m")
    config = DATASETS[dataset]
    for month, frame in normalized.groupby("month", sort=True):
        output = (
            Path(config["normalized_root"])
            / "source=binance_fapi_gap_repair"
            / f"month={month}"
            / "part-0000.parquet"
        )
        atomic_parquet(frame.drop(columns="month").sort_values(["ts", "symbol"]), output)
    for month, frame in raw.groupby("month", sort=True):
        output = (
            Path(config["raw_root"])
            / "source=binance_fapi_gap_repair"
            / f"month={month}"
            / "part-0000.parquet"
        )
        atomic_parquet(
            frame.drop(columns="month").sort_values(["open_time", "symbol"]), output
        )


def main() -> None:
    args = parse_args()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "family": "Binance-1H-Multi-Horizon-Cross-Sectional-ML-Allocator",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "range": {"start": START.isoformat(), "end_exclusive": END.isoformat()},
        "datasets": {},
    }
    for dataset in args.datasets:
        before = gaps(dataset)
        detail: dict[str, Any] = {
            "gap_events_before": len(before),
            "gap_hours_before": int(before["missing_hours"].sum()),
        }
        if args.dry_run:
            detail["status"] = "dry_run"
            report["datasets"][dataset] = detail
            continue
        results = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [
                executor.submit(
                    fetch_gap,
                    dataset,
                    row,
                    timeout=args.timeout,
                    attempts=args.attempts,
                    request_delay=args.request_delay,
                )
                for row in before.itertuples(index=False)
            ]
            for index, future in enumerate(as_completed(futures), start=1):
                results.append(future.result())
                if index % 250 == 0 or index == len(futures):
                    print(
                        f"{dataset}: completed {index}/{len(futures)} API gaps",
                        flush=True,
                    )
        persist(dataset, results)
        after = gaps(dataset)
        manifest_rows = []
        for result in results:
            manifest_rows.append(
                {key: value for key, value in result.items() if key != "raw"}
            )
        detail.update(
            {
                "status": "PASS" if after.empty else "BLOCKED",
                "returned_hours": int(
                    sum(result["returned_hours"] for result in results)
                ),
                "empty_api_responses": int(
                    sum(result["returned_hours"] == 0 for result in results)
                ),
                "gap_events_after": len(after),
                "gap_hours_after": int(after["missing_hours"].sum()),
                "requests": manifest_rows,
                "remaining_gaps": after.to_dict(orient="records"),
            }
        )
        report["datasets"][dataset] = detail
    report["status"] = (
        "PASS"
        if all(
            detail.get("status") in {"PASS", "dry_run"}
            for detail in report["datasets"].values()
        )
        else "BLOCKED"
    )
    stamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    output = ARTIFACT_DIR / f"fapi_gap_repair_manifest_{stamp}.json"
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    summary = {
        "status": report["status"],
        "manifest": str(output),
        "datasets": {
            name: {
                key: value
                for key, value in detail.items()
                if key not in {"requests", "remaining_gaps"}
            }
            for name, detail in report["datasets"].items()
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
