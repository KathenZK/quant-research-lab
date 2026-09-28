from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

import duckdb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / (
    "research/asset-portfolios/1h-multi-horizon-cross-sectional-ml-allocator"
)
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
ARCHIVE_ROOT = ROOT / "data/raw/_archives/binance/futures/um/daily"
VISION_ROOT = "https://data.binance.vision/data/futures/um/daily"
USER_AGENT = "quant-research-lab-bin-1h-mhcsml-gap-repair/0.1"
START = pd.Timestamp("2020-01-01T00:00:00Z")
END = pd.Timestamp("2026-07-01T00:00:00Z")
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
DATASETS = {
    "kline_1h": {
        "vision_dir": "klines",
        "normalized_glob": ROOT
        / "data/normalized/ohlcv/exchange=binance/market_type=perp/"
        "timeframe=1h/**/*.parquet",
        "raw_root": ROOT
        / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
        "normalized_root": ROOT
        / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
    },
    "mark_1h": {
        "vision_dir": "markPriceKlines",
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
        description="Repair internal monthly Binance Vision gaps from daily archives."
    )
    parser.add_argument(
        "--datasets", nargs="+", choices=sorted(DATASETS), default=sorted(DATASETS)
    )
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def request_bytes(url: str, *, timeout: float, attempts: int) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise
            if exc.code not in {429, 500, 502, 503, 504}:
                raise
            last_error = exc
        except (URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(8.0, 0.5 * 2**attempt))
    raise RuntimeError(f"request failed after {attempts} attempts: {url}") from last_error


def archive_paths(dataset: str, symbol: str, date: str) -> tuple[Path, str]:
    vision_dir = str(DATASETS[dataset]["vision_dir"])
    filename = f"{symbol}-1h-{date}.zip"
    local = (
        ARCHIVE_ROOT
        / vision_dir
        / f"symbol={symbol.lower()}"
        / "timeframe=1h"
        / f"year={date[:4]}"
        / filename
    )
    url = f"{VISION_ROOT}/{vision_dir}/{symbol}/1h/{filename}"
    return local, url


def verified_daily_archive(
    dataset: str,
    symbol: str,
    date: str,
    *,
    timeout: float,
    attempts: int,
) -> tuple[bytes, str, Path]:
    path, url = archive_paths(dataset, symbol, date)
    checksum_path = path.with_name(f"{path.name}.CHECKSUM")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not checksum_path.exists():
        payload = request_bytes(
            f"{url}.CHECKSUM", timeout=timeout, attempts=attempts
        )
        temporary = checksum_path.with_suffix(f"{checksum_path.suffix}.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, checksum_path)
    expected = checksum_path.read_text(encoding="utf-8").strip().split()[0].lower()
    if len(expected) != 64:
        raise RuntimeError(f"invalid checksum sidecar: {checksum_path}")
    payload = path.read_bytes() if path.exists() else b""
    actual = hashlib.sha256(payload).hexdigest() if payload else ""
    if actual != expected:
        payload = request_bytes(url, timeout=timeout, attempts=attempts)
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected:
            raise RuntimeError(f"checksum mismatch: {url}")
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RuntimeError(f"corrupt ZIP member {bad_member}: {path}")
    return payload, actual, path


def parse_kline(payload: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        members = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(members) != 1:
            raise RuntimeError(f"unexpected CSV members: {members}")
        with archive.open(members[0]) as handle:
            frame = pd.read_csv(handle, header=None, low_memory=False)
    if frame.shape[1] != len(KLINE_COLUMNS):
        raise RuntimeError(f"unexpected kline column count: {frame.shape[1]}")
    frame.columns = KLINE_COLUMNS
    frame["open_time"] = pd.to_numeric(frame["open_time"], errors="coerce")
    frame = frame.loc[frame["open_time"].notna()].copy()
    frame["close_time"] = pd.to_numeric(frame["close_time"], errors="coerce")
    numeric = KLINE_COLUMNS[1:6] + KLINE_COLUMNS[7:11]
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["ignore"] = pd.to_numeric(frame["ignore"], errors="coerce")
    frame["trade_count"] = frame["trade_count"].astype("Int64")
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    return frame.reset_index(drop=True)


def canonical_symbol(archive_symbol: str) -> str:
    return f"{archive_symbol.removesuffix('USDT')}/USDT:USDT"


def normalized_kline(
    raw: pd.DataFrame,
    *,
    dataset: str,
    archive_symbol: str,
    archive_date: str,
    archive_sha256: str,
) -> pd.DataFrame:
    result = raw.copy()
    result["ts"] = result["open_time"]
    result["exchange"] = "binance"
    result["symbol"] = canonical_symbol(archive_symbol)
    result["market_type"] = "perp"
    result["timeframe"] = "1h"
    result["base_asset"] = archive_symbol.removesuffix("USDT")
    result["quote_asset"] = "USDT"
    result["is_closed"] = True
    result["source"] = (
        "binance_vision_mark_price_kline_daily_gap_repair"
        if dataset == "mark_1h"
        else "binance_vision_kline_daily_gap_repair"
    )
    result["archive_date"] = archive_date
    result["archive_sha256"] = archive_sha256
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
        return result[
            common
            + ["is_closed", "source", "archive_date", "archive_sha256"]
        ]
    result["vwap"] = result["quote_volume"] / result["volume"].replace(0.0, np.nan)
    result["vwap"] = result["vwap"].fillna(result["close"])
    return result[
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
            "archive_date",
            "archive_sha256",
        ]
    ]


def gap_tasks(
    dataset: str, *, include_existing_repairs: bool = False
) -> tuple[dict[tuple[str, str], set[pd.Timestamp]], int]:
    path = Path(DATASETS[dataset]["normalized_glob"])
    connection = duckdb.connect()
    repair_filter = (
        ""
        if include_existing_repairs
        else "AND source NOT LIKE '%daily_gap_repair%'"
    )
    gaps = connection.execute(
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
              {repair_filter}
        )
        SELECT symbol, previous_ts, ts
        FROM ordered
        WHERE date_diff('hour', previous_ts, ts) > 1
        """
    ).fetch_df()
    connection.close()
    tasks: dict[tuple[str, str], set[pd.Timestamp]] = {}
    missing_hours = 0
    for row in gaps.itertuples(index=False):
        timestamps = pd.date_range(
            pd.Timestamp(row.previous_ts) + pd.Timedelta(hours=1),
            pd.Timestamp(row.ts) - pd.Timedelta(hours=1),
            freq="1h",
        )
        missing_hours += len(timestamps)
        archive_symbol = f"{str(row.symbol).split('/')[0]}USDT"
        for timestamp in timestamps:
            timestamp_utc = pd.Timestamp(timestamp).tz_convert("UTC")
            key = (archive_symbol, timestamp_utc.strftime("%Y-%m-%d"))
            tasks.setdefault(key, set()).add(timestamp_utc)
    return tasks, missing_hours


def fetch_task(
    dataset: str,
    symbol: str,
    date: str,
    expected_timestamps: set[pd.Timestamp],
    *,
    timeout: float,
    attempts: int,
) -> dict[str, Any]:
    try:
        payload, checksum, path = verified_daily_archive(
            dataset,
            symbol,
            date,
            timeout=timeout,
            attempts=attempts,
        )
    except HTTPError as exc:
        if exc.code == 404:
            return {
                "status": "archive_not_found",
                "dataset": dataset,
                "symbol": symbol,
                "date": date,
                "expected_hours": len(expected_timestamps),
            }
        raise
    raw = parse_kline(payload)
    normalized = normalized_kline(
        raw,
        dataset=dataset,
        archive_symbol=symbol,
        archive_date=date,
        archive_sha256=checksum,
    )
    mask = normalized["ts"].isin(expected_timestamps)
    normalized = normalized.loc[mask].copy()
    raw = raw.loc[raw["open_time"].isin(expected_timestamps)].copy()
    raw["archive_symbol"] = symbol
    raw["archive_date"] = date
    raw["archive_sha256"] = checksum
    raw["source"] = "binance_vision_daily_gap_repair"
    return {
        "status": "downloaded",
        "dataset": dataset,
        "symbol": symbol,
        "date": date,
        "expected_hours": len(expected_timestamps),
        "repaired_hours": len(normalized),
        "archive_path": str(path.relative_to(ROOT)),
        "archive_sha256": checksum,
        "raw": raw,
        "normalized": normalized,
    }


def atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    os.replace(temporary, path)


def persist_frames(dataset: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    config = DATASETS[dataset]
    normalized = pd.concat(
        [result.pop("normalized") for result in results], ignore_index=True
    )
    raw = pd.concat([result.pop("raw") for result in results], ignore_index=True)
    if normalized.duplicated(["ts", "symbol"]).any():
        raise RuntimeError(f"duplicate repair keys for {dataset}")
    if normalized[["open", "high", "low", "close"]].isna().any().any():
        raise RuntimeError(f"null OHLC in repair rows for {dataset}")
    invalid = (
        (normalized["high"] < normalized[["open", "close"]].max(axis=1))
        | (normalized["low"] > normalized[["open", "close"]].min(axis=1))
        | (normalized["low"] <= 0.0)
    )
    if invalid.any():
        raise RuntimeError(f"invalid OHLC in repair rows for {dataset}")
    normalized["month"] = normalized["ts"].dt.strftime("%Y-%m")
    raw["month"] = raw["open_time"].dt.strftime("%Y-%m")
    for month, frame in normalized.groupby("month", sort=True):
        output = (
            Path(config["normalized_root"])
            / "source=binance_vision_daily_gap_repair"
            / f"month={month}"
            / "part-0000.parquet"
        )
        atomic_parquet(frame.drop(columns="month").sort_values(["ts", "symbol"]), output)
    for month, frame in raw.groupby("month", sort=True):
        output = (
            Path(config["raw_root"])
            / "source=binance_vision_daily_gap_repair"
            / f"month={month}"
            / "part-0000.parquet"
        )
        atomic_parquet(
            frame.drop(columns="month").sort_values(["open_time", "archive_symbol"]),
            output,
        )
    return results


def main() -> None:
    args = parse_args()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "family": "Binance-1H-Multi-Horizon-Cross-Sectional-ML-Allocator",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "range": {"start": START.isoformat(), "end_exclusive": END.isoformat()},
        "datasets": {},
    }
    for dataset in args.datasets:
        tasks, missing_hours = gap_tasks(dataset)
        detail: dict[str, Any] = {
            "gap_hours_before": missing_hours,
            "daily_archive_tasks": len(tasks),
        }
        if args.dry_run:
            detail["status"] = "dry_run"
            manifest["datasets"][dataset] = detail
            continue
        completed: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    fetch_task,
                    dataset,
                    symbol,
                    date,
                    expected,
                    timeout=args.timeout,
                    attempts=args.attempts,
                ): (symbol, date)
                for (symbol, date), expected in tasks.items()
            }
            for index, future in enumerate(as_completed(futures), start=1):
                result = future.result()
                completed.append(result)
                if index % 250 == 0 or index == len(futures):
                    print(
                        f"{dataset}: completed {index}/{len(futures)} daily archives",
                        flush=True,
                    )
        downloaded = [row for row in completed if row["status"] == "downloaded"]
        unavailable = [row for row in completed if row["status"] != "downloaded"]
        if downloaded:
            persist_frames(dataset, downloaded)
        _, remaining_hours = gap_tasks(dataset, include_existing_repairs=True)
        detail.update(
            {
                "status": "PASS" if remaining_hours == 0 else "BLOCKED",
                "downloaded_archives": len(downloaded),
                "unavailable_archives": len(unavailable),
                "repaired_hours": int(
                    sum(row["repaired_hours"] for row in downloaded)
                ),
                "gap_hours_after": remaining_hours,
                "unavailable": unavailable,
                "archives": downloaded,
            }
        )
        manifest["datasets"][dataset] = detail
    manifest["status"] = (
        "PASS"
        if all(
            detail.get("status") in {"PASS", "dry_run"}
            for detail in manifest["datasets"].values()
        )
        else "BLOCKED"
    )
    stamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    output = ARTIFACT_DIR / f"daily_gap_repair_manifest_{stamp}.json"
    output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    summary = {
        "status": manifest["status"],
        "manifest": str(output),
        "datasets": {
            name: {
                key: value
                for key, value in detail.items()
                if key not in {"archives", "unavailable"}
            }
            for name, detail in manifest["datasets"].items()
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
