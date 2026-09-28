from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from http.client import IncompleteRead
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/15m-ema-cross-lightgbm-event-selector"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
INVENTORY_PATH = ARTIFACT_DIR / "binance_usdm_15m_inventory_2026-07-23.csv"
VISION = "https://data.binance.vision"
UA = "quant-research-lab-bin-15m-emax-lgbm-sync/0.1"

ARCHIVE_ROOT = ROOT / "data/raw/_archives/binance/futures/um/monthly"
RAW_ROOT = ROOT / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
NORMALIZED_ROOT = (
    ROOT / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
)
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


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    symbol: str
    month: str
    archive_path: str
    archive_sha256: str
    archive_bytes: int
    rows: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify, download, normalize, and persist Binance Vision USD-M monthly "
            "15m kline history for the BIN-15M-EMAX-LGBM research family. Legacy "
            "daily-partition files are never modified; overlapping (ts, symbol) keys "
            "are excluded from the new monthly partitions so the lake union stays "
            "duplicate-free."
        )
    )
    parser.add_argument("--inventory", type=Path, default=INVENTORY_PATH)
    parser.add_argument("--start-month", default="2020-01")
    parser.add_argument("--end-month", default="2026-06")
    parser.add_argument("--symbols", nargs="*", help="Optional archive symbols.")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--attempts", type=int, default=7)
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def request_bytes(url: str, *, timeout: float, attempts: int) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": UA})
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504}:
                raise
            last_error = exc
        except (URLError, TimeoutError, IncompleteRead, ConnectionError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(15.0, 0.75 * 2**attempt))
    raise RuntimeError(f"request failed after {attempts} attempts: {url}") from last_error


def archive_location(symbol: str, month: str) -> tuple[Path, str]:
    filename = f"{symbol}-15m-{month}.zip"
    remote = (
        f"{VISION}/data/futures/um/monthly/klines/"
        f"{quote(symbol, safe='')}/15m/{quote(filename, safe='-._')}"
    )
    local = ARCHIVE_ROOT.joinpath(
        "klines",
        f"symbol={symbol.lower()}",
        "timeframe=15m",
        f"year={month[:4]}",
        filename,
    )
    return local, remote


def checksum_value(text: str) -> str:
    value = text.strip().split()[0].lower()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise RuntimeError(f"invalid SHA256 checksum sidecar: {text!r}")
    return value


def verified_archive(
    symbol: str,
    month: str,
    *,
    timeout: float,
    attempts: int,
) -> tuple[bytes, str, Path]:
    archive_path, archive_url = archive_location(symbol, month)
    checksum_path = archive_path.with_name(f"{archive_path.name}.CHECKSUM")
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    if not checksum_path.exists():
        sidecar = request_bytes(
            f"{archive_url}.CHECKSUM", timeout=timeout, attempts=attempts
        )
        temporary = checksum_path.with_suffix(f"{checksum_path.suffix}.tmp")
        temporary.write_bytes(sidecar)
        os.replace(temporary, checksum_path)
    expected = checksum_value(checksum_path.read_text(encoding="utf-8"))

    payload = archive_path.read_bytes() if archive_path.exists() else b""
    actual = hashlib.sha256(payload).hexdigest() if payload else ""
    if actual != expected:
        payload = request_bytes(archive_url, timeout=timeout, attempts=attempts)
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected:
            raise RuntimeError(
                f"kline_15m {symbol} {month} checksum mismatch: {actual} != {expected}"
            )
        temporary = archive_path.with_suffix(f"{archive_path.suffix}.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, archive_path)

    with zipfile.ZipFile(BytesIO(payload)) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RuntimeError(f"corrupt member {bad_member}: {archive_path}")
    return payload, actual, archive_path


def parse_kline(payload: bytes, *, identity: str) -> pd.DataFrame:
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise RuntimeError(f"unexpected CSV members for {identity}: {members}")
        with archive.open(members[0]) as handle:
            frame = pd.read_csv(handle, header=None, low_memory=False)
    if frame.shape[1] != len(KLINE_COLUMNS):
        raise RuntimeError(f"unexpected kline column count for {identity}: {frame.shape[1]}")
    frame.columns = KLINE_COLUMNS
    frame["open_time"] = pd.to_numeric(frame["open_time"], errors="coerce")
    frame = frame.loc[frame["open_time"].notna()].copy()
    frame["close_time"] = pd.to_numeric(frame["close_time"], errors="coerce")
    for column in KLINE_COLUMNS[1:6] + KLINE_COLUMNS[7:11]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["ignore"] = pd.to_numeric(frame["ignore"], errors="coerce")
    frame["trade_count"] = frame["trade_count"].astype("Int64")
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    return frame.reset_index(drop=True)


def parse_archive(
    symbol: str,
    month: str,
    *,
    timeout: float,
    attempts: int,
) -> tuple[pd.DataFrame, ArchiveResult]:
    payload, checksum, path = verified_archive(
        symbol, month, timeout=timeout, attempts=attempts
    )
    frame = parse_kline(payload, identity=f"kline_15m/{symbol}/{month}")
    frame["archive_symbol"] = symbol
    frame["archive_month"] = month
    frame["archive_sha256"] = checksum
    return frame, ArchiveResult(
        symbol=symbol,
        month=month,
        archive_path=str(path.relative_to(ROOT)),
        archive_sha256=checksum,
        archive_bytes=len(payload),
        rows=len(frame),
    )


def canonical_symbol(archive_symbol: pd.Series) -> pd.Series:
    return archive_symbol.str.removesuffix("USDT") + "/USDT:USDT"


def normalize_kline(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    frame["ts"] = frame["open_time"]
    frame["exchange"] = "binance"
    frame["symbol"] = canonical_symbol(frame["archive_symbol"])
    frame["market_type"] = "perp"
    frame["timeframe"] = "15m"
    frame["base_asset"] = frame["archive_symbol"].str.removesuffix("USDT")
    frame["quote_asset"] = "USDT"
    frame["is_closed"] = True
    frame["source"] = "binance_vision_kline_monthly"
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
            "taker_buy_volume",
            "taker_buy_quote_volume",
            "vwap",
            "is_closed",
            "source",
            "archive_month",
            "archive_sha256",
        ]
    ]


def monthly_output_path(root: Path, month: str) -> Path:
    return root / "source=binance_vision_monthly" / f"month={month}" / "part-0000.parquet"


def completion_marker(path: Path) -> Path:
    return path.with_suffix(".complete.json")


def output_is_complete(
    raw_path: Path,
    normalized_path: Path,
    archive_symbols: list[str],
) -> bool:
    marker_path = completion_marker(normalized_path)
    if not raw_path.exists() or not normalized_path.exists() or not marker_path.exists():
        return False
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    return marker.get("archive_symbols") == sorted(archive_symbols)


def legacy_daily_keys(month: str) -> pd.DataFrame:
    paths = sorted(NORMALIZED_ROOT.glob(f"date={month}-*/*.parquet"))
    if not paths:
        return pd.DataFrame(columns=["ts", "symbol"])
    keys = []
    for path in paths:
        try:
            frame = pd.read_parquet(path, columns=["ts", "symbol"])
        except Exception as exc:  # noqa: BLE001
            if "symbol" not in str(exc):
                raise
            # minimal-schema exploratory files: derive symbol from the filename
            frame = pd.read_parquet(path, columns=["ts"])
            slug = path.stem.removeprefix("symbol=")
            base = slug.removesuffix("_usdt_usdt").upper()
            frame["symbol"] = f"{base}/USDT:USDT"
        frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
        keys.append(frame)
    return pd.concat(keys, ignore_index=True).drop_duplicates(["ts", "symbol"])


def atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    os.replace(temporary, path)


def inventory_symbols(
    inventory: pd.DataFrame,
    month: str,
    selected_symbols: set[str] | None,
) -> list[str]:
    symbols = []
    for row in inventory[["symbol", "kline_15m_month_list"]].itertuples(index=False):
        symbol = str(row.symbol)
        months = set(str(row.kline_15m_month_list or "").split(";"))
        if month in months and (selected_symbols is None or symbol in selected_symbols):
            symbols.append(symbol)
    return symbols


def process_month(
    inventory: pd.DataFrame,
    month: str,
    *,
    selected_symbols: set[str] | None,
    workers: int,
    timeout: float,
    attempts: int,
    overwrite_output: bool,
) -> dict[str, Any]:
    raw_path = monthly_output_path(RAW_ROOT, month)
    normalized_path = monthly_output_path(NORMALIZED_ROOT, month)
    symbols = inventory_symbols(inventory, month, selected_symbols)
    if not symbols:
        return {"month": month, "status": "no_archives", "symbols": 0}
    if not overwrite_output and output_is_complete(raw_path, normalized_path, symbols):
        return {"month": month, "status": "existing_output", "symbols": len(symbols)}

    frames: list[pd.DataFrame] = []
    archive_results: list[ArchiveResult] = []
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                parse_archive, symbol, month, timeout=timeout, attempts=attempts
            ): symbol
            for symbol in symbols
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                frame, result = future.result()
            except Exception as exc:  # noqa: BLE001
                failures.append({"symbol": symbol, "error": repr(exc)})
                continue
            frames.append(frame)
            archive_results.append(result)

    if failures:
        return {
            "month": month,
            "status": "failed",
            "symbols": len(symbols),
            "archives_ok": len(archive_results),
            "failures": failures,
        }

    raw = pd.concat(frames, ignore_index=True, sort=False)
    normalized = normalize_kline(raw)
    duplicate_rows = int(normalized.duplicated(["ts", "symbol"], keep=False).sum())
    if duplicate_rows:
        raise RuntimeError(f"kline_15m {month} has {duplicate_rows} duplicate rows")

    legacy = legacy_daily_keys(month)
    if legacy.empty:
        overlap = 0
    else:
        marked = normalized.merge(
            legacy.assign(_legacy=True), on=["ts", "symbol"], how="left"
        )
        overlap = int(marked["_legacy"].notna().sum())
        normalized = marked.loc[marked["_legacy"].isna()].drop(columns="_legacy")

    retained_keys = normalized[["ts", "symbol"]]
    raw["ts"] = raw["open_time"]
    raw["symbol"] = canonical_symbol(raw["archive_symbol"])
    raw = raw.merge(retained_keys.assign(_retain=True), on=["ts", "symbol"], how="inner")
    raw = raw.drop(columns="_retain")

    atomic_parquet(raw.sort_values(["ts", "symbol"]), raw_path)
    atomic_parquet(normalized.sort_values(["ts", "symbol"]), normalized_path)
    marker = {
        "dataset": "kline_15m",
        "month": month,
        "archive_symbols": sorted(symbols),
        "archive_rows": sum(item.rows for item in archive_results),
        "legacy_overlap_excluded": overlap,
        "legacy_files_modified": 0,
        "raw_rows_written": len(raw),
        "normalized_rows_written": len(normalized),
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
    }
    completion_marker(normalized_path).write_text(
        json.dumps(marker, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {
        "month": month,
        "status": "written",
        "symbols": len(symbols),
        "archive_bytes": sum(item.archive_bytes for item in archive_results),
        "archive_rows": sum(item.rows for item in archive_results),
        "legacy_overlap_excluded": overlap,
        "raw_rows_written": len(raw),
        "normalized_rows_written": len(normalized),
        "raw_path": str(raw_path.relative_to(ROOT)),
        "normalized_path": str(normalized_path.relative_to(ROOT)),
        "archives": [asdict(item) for item in archive_results],
    }


def append_manifest(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def main() -> None:
    args = parse_args()
    inventory = pd.read_csv(args.inventory, dtype={"symbol": str})
    selected_symbols = set(args.symbols) if args.symbols else None
    if args.start_month > args.end_month:
        raise ValueError("start month must not be after end month")
    months = pd.period_range(args.start_month, args.end_month, freq="M").astype(str).tolist()
    archives = sum(
        len(inventory_symbols(inventory, month, selected_symbols)) for month in months
    )
    print(f"months={len(months)} archives={archives} range={args.start_month}..{args.end_month}")
    if args.dry_run:
        return

    stamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    manifest_path = ARTIFACT_DIR / f"binance_usdm_15m_sync_manifest_{stamp}.jsonl"
    failed = 0
    for index, month in enumerate(months, start=1):
        started = time.monotonic()
        result = process_month(
            inventory,
            month,
            selected_symbols=selected_symbols,
            workers=args.workers,
            timeout=args.timeout,
            attempts=args.attempts,
            overwrite_output=args.overwrite_output,
        )
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["generated_at"] = pd.Timestamp.now("UTC").isoformat()
        append_manifest(manifest_path, result)
        if result["status"] == "failed":
            failed += 1
        print(
            f"[{index}/{len(months)}] {month} status={result['status']} "
            f"symbols={result['symbols']} elapsed={result['elapsed_seconds']}s",
            flush=True,
        )
    print(f"manifest -> {manifest_path}")
    if failed:
        raise RuntimeError(f"{failed} months failed; inspect manifest")


if __name__ == "__main__":
    main()
