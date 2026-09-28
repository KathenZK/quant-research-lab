from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
import os
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from http.client import IncompleteRead
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1h-cross-sectional-lightgbm-selector"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
INVENTORY_PATH = ARTIFACT_DIR / "binance_usdm_historical_inventory_2026-07-17.csv"
VISION = "https://data.binance.vision"
UA = "quant-research-lab-bin-1h-cslgbm-sync/0.1"

ARCHIVE_ROOT = ROOT / "data/raw/_archives/binance/futures/um/monthly"
DATASET_CONFIG = {
    "kline_1h": {
        "vision_dir": "klines",
        "remote_suffix": "1h",
        "filename_tag": "1h",
        "raw_root": ROOT
        / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
        "normalized_root": ROOT
        / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
    },
    "mark_1h": {
        "vision_dir": "markPriceKlines",
        "remote_suffix": "1h",
        "filename_tag": "1h",
        "raw_root": ROOT
        / "data/raw/mark_price_klines/exchange=binance/market_type=perp/timeframe=1h",
        "normalized_root": ROOT
        / "data/normalized/mark_price_klines/exchange=binance/market_type=perp/timeframe=1h",
    },
    "funding": {
        "vision_dir": "fundingRate",
        "remote_suffix": "",
        "filename_tag": "fundingRate",
        "raw_root": ROOT
        / "data/raw/funding_rates/exchange=binance/market_type=perp",
        "normalized_root": ROOT
        / "data/normalized/funding_rates/exchange=binance/market_type=perp",
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


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    dataset: str
    symbol: str
    month: str
    archive_path: str
    archive_sha256: str
    archive_bytes: int
    rows: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify, download, normalize, and persist Binance Vision USD-M "
            "monthly history for the cross-sectional 1h research family."
        )
    )
    parser.add_argument("--inventory", type=Path, default=INVENTORY_PATH)
    parser.add_argument(
        "--datasets",
        nargs="+",
        choices=sorted(DATASET_CONFIG),
        default=sorted(DATASET_CONFIG),
    )
    parser.add_argument("--start-month", default="2020-01")
    parser.add_argument("--end-month", default="2026-06")
    parser.add_argument(
        "--symbols",
        nargs="*",
        help="Optional archive symbols such as BTCUSDT XRPUSDT.",
    )
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--attempts", type=int, default=7)
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def request_bytes(
    url: str,
    *,
    timeout: float,
    attempts: int,
) -> bytes:
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
        except (
            URLError,
            TimeoutError,
            IncompleteRead,
            ConnectionError,
        ) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(15.0, 0.75 * 2**attempt))
    raise RuntimeError(f"request failed after {attempts} attempts: {url}") from last_error


def archive_location(dataset: str, symbol: str, month: str) -> tuple[Path, str]:
    config = DATASET_CONFIG[dataset]
    vision_dir = str(config["vision_dir"])
    suffix = str(config["remote_suffix"])
    tag = str(config["filename_tag"])
    filename = f"{symbol}-{tag}-{month}.zip"
    remote_parts = [
        "data/futures/um/monthly",
        vision_dir,
        quote(symbol, safe=""),
    ]
    local_parts = [vision_dir, f"symbol={symbol.lower()}"]
    if suffix:
        remote_parts.append(suffix)
        local_parts.append(f"timeframe={suffix}")
    remote_parts.append(quote(filename, safe="-._"))
    local_parts.extend([f"year={month[:4]}", filename])
    return ARCHIVE_ROOT.joinpath(*local_parts), f"{VISION}/{'/'.join(remote_parts)}"


def checksum_value(text: str) -> str:
    value = text.strip().split()[0].lower()
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise RuntimeError(f"invalid SHA256 checksum sidecar: {text!r}")
    return value


def verified_archive(
    dataset: str,
    symbol: str,
    month: str,
    *,
    timeout: float,
    attempts: int,
) -> tuple[bytes, str, Path]:
    archive_path, archive_url = archive_location(dataset, symbol, month)
    checksum_path = archive_path.with_name(f"{archive_path.name}.CHECKSUM")
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    if not checksum_path.exists():
        sidecar = request_bytes(
            f"{archive_url}.CHECKSUM",
            timeout=timeout,
            attempts=attempts,
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
                f"{dataset} {symbol} {month} checksum mismatch: {actual} != {expected}"
            )
        temporary = archive_path.with_suffix(f"{archive_path.suffix}.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, archive_path)

    with zipfile.ZipFile(BytesIO(payload)) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RuntimeError(f"corrupt member {bad_member}: {archive_path}")
    return payload, actual, archive_path


def one_csv_member(payload: bytes, *, identity: str) -> pd.DataFrame:
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise RuntimeError(f"unexpected CSV members for {identity}: {members}")
        with archive.open(members[0]) as handle:
            return pd.read_csv(handle, header=None, low_memory=False)


def parse_kline(payload: bytes, *, identity: str) -> pd.DataFrame:
    frame = one_csv_member(payload, identity=identity)
    if frame.shape[1] != len(KLINE_COLUMNS):
        raise RuntimeError(
            f"unexpected kline column count for {identity}: {frame.shape[1]}"
        )
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


def parse_funding(payload: bytes, *, identity: str) -> pd.DataFrame:
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise RuntimeError(f"unexpected CSV members for {identity}: {members}")
        with archive.open(members[0]) as handle:
            frame = pd.read_csv(handle, low_memory=False)
    required = {"calc_time", "funding_interval_hours", "last_funding_rate"}
    missing = required - set(frame.columns)
    if missing:
        raise RuntimeError(f"missing funding columns for {identity}: {sorted(missing)}")
    frame["calc_time"] = pd.to_numeric(frame["calc_time"], errors="coerce")
    frame["funding_interval_hours"] = pd.to_numeric(
        frame["funding_interval_hours"], errors="coerce"
    )
    frame["last_funding_rate"] = pd.to_numeric(
        frame["last_funding_rate"], errors="coerce"
    )
    return frame.loc[frame["calc_time"].notna()].reset_index(drop=True)


def parse_archive(
    dataset: str,
    symbol: str,
    month: str,
    *,
    timeout: float,
    attempts: int,
) -> tuple[pd.DataFrame, ArchiveResult]:
    payload, checksum, path = verified_archive(
        dataset,
        symbol,
        month,
        timeout=timeout,
        attempts=attempts,
    )
    identity = f"{dataset}/{symbol}/{month}"
    frame = (
        parse_funding(payload, identity=identity)
        if dataset == "funding"
        else parse_kline(payload, identity=identity)
    )
    frame["archive_symbol"] = symbol
    frame["archive_month"] = month
    frame["archive_sha256"] = checksum
    return frame, ArchiveResult(
        dataset=dataset,
        symbol=symbol,
        month=month,
        archive_path=str(path.relative_to(ROOT)),
        archive_sha256=checksum,
        archive_bytes=len(payload),
        rows=len(frame),
    )


def canonical_symbol(archive_symbol: pd.Series) -> pd.Series:
    return archive_symbol.str.removesuffix("USDT") + "/USDT:USDT"


def normalize_kline(raw: pd.DataFrame, *, mark_price: bool) -> pd.DataFrame:
    frame = raw.copy()
    frame["ts"] = frame["open_time"]
    frame["exchange"] = "binance"
    frame["symbol"] = canonical_symbol(frame["archive_symbol"])
    frame["market_type"] = "perp"
    frame["timeframe"] = "1h"
    frame["base_asset"] = frame["archive_symbol"].str.removesuffix("USDT")
    frame["quote_asset"] = "USDT"
    frame["is_closed"] = True
    frame["source"] = (
        "binance_vision_mark_price_kline_monthly"
        if mark_price
        else "binance_vision_kline_monthly"
    )
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
    if mark_price:
        return frame[
            common
            + [
                "is_closed",
                "source",
                "archive_month",
                "archive_sha256",
            ]
        ]
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
            "archive_month",
            "archive_sha256",
        ]
    ]


def normalize_funding(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    frame["ts"] = pd.to_datetime(frame["calc_time"], unit="ms", utc=True).dt.round("s")
    frame["exchange"] = "binance"
    frame["symbol"] = canonical_symbol(frame["archive_symbol"])
    frame["market_type"] = "perp"
    frame["base_asset"] = frame["archive_symbol"].str.removesuffix("USDT")
    frame["quote_asset"] = "USDT"
    frame["funding_rate"] = frame["last_funding_rate"]
    frame["next_funding_ts"] = frame["ts"] + pd.to_timedelta(
        frame["funding_interval_hours"], unit="h"
    )
    frame["mark_price"] = np.nan
    frame["source"] = "binance_vision_funding_monthly"
    return frame[
        [
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


def legacy_daily_keys(root: Path, month: str, *, timestamp_column: str) -> pd.DataFrame:
    paths = sorted(root.glob(f"date={month}-*/*.parquet"))
    if not paths:
        return pd.DataFrame(columns=[timestamp_column, "symbol"])
    keys = []
    for path in paths:
        try:
            frame = pd.read_parquet(path, columns=[timestamp_column, "symbol"])
        except Exception as exc:  # noqa: BLE001
            if "symbol" not in str(exc):
                raise
            frame = pd.read_parquet(path, columns=[timestamp_column])
            slug = path.stem.removeprefix("symbol=")
            base = slug.removesuffix("_usdt_usdt").upper()
            frame["symbol"] = f"{base}/USDT:USDT"
        frame[timestamp_column] = pd.to_datetime(frame[timestamp_column], utc=True)
        keys.append(frame)
    return pd.concat(keys, ignore_index=True).drop_duplicates(
        [timestamp_column, "symbol"]
    )


def remove_legacy_overlap(
    frame: pd.DataFrame,
    root: Path,
    month: str,
    *,
    timestamp_column: str,
) -> tuple[pd.DataFrame, int]:
    legacy = legacy_daily_keys(root, month, timestamp_column=timestamp_column)
    if legacy.empty:
        return frame, 0
    marked = frame.merge(
        legacy.assign(_legacy=True),
        on=[timestamp_column, "symbol"],
        how="left",
    )
    overlap = int(marked["_legacy"].fillna(False).sum())
    return marked.loc[marked["_legacy"].isna()].drop(columns="_legacy"), overlap


def atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    os.replace(temporary, path)


def legacy_symbol_slug(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_").lower()


def enrich_legacy_daily_files(
    dataset: str,
    normalized_archive: pd.DataFrame,
    normalized_root: Path,
) -> dict[str, int]:
    if dataset == "mark_1h":
        return {"files_enriched": 0, "rows_compared": 0, "value_mismatches": 0}
    source_columns = (
        [
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
        ]
        if dataset == "kline_1h"
        else [
            "funding_rate",
            "funding_interval_hours",
            "next_funding_ts",
            "mark_price",
        ]
    )
    compare_columns = (
        ["open", "high", "low", "close"]
        if dataset == "kline_1h"
        else []
    )
    archive = normalized_archive.copy()
    archive["date"] = archive["ts"].dt.strftime("%Y-%m-%d")
    files_enriched = 0
    rows_compared = 0
    value_mismatches = 0
    for (date, symbol), supplement in archive.groupby(["date", "symbol"], sort=False):
        path = normalized_root / f"date={date}" / f"symbol={legacy_symbol_slug(symbol)}.parquet"
        if not path.exists():
            continue
        legacy = pd.read_parquet(path)
        legacy["ts"] = pd.to_datetime(legacy["ts"], utc=True)
        available_sources = [column for column in source_columns if column in supplement.columns]
        right_columns = list(dict.fromkeys(["ts", *compare_columns, *available_sources]))
        right = supplement[right_columns].drop_duplicates("ts")
        joined = legacy.merge(right, on="ts", how="left", suffixes=("", "_archive"))
        probe = compare_columns[0] if compare_columns else available_sources[0]
        probe_column = f"{probe}_archive" if probe in legacy.columns else probe
        overlap = joined[probe_column].notna()
        rows_compared += int(overlap.sum())
        for column in compare_columns:
            left = pd.to_numeric(joined.loc[overlap, column], errors="coerce")
            right_value = pd.to_numeric(
                joined.loc[overlap, f"{column}_archive"], errors="coerce"
            )
            value_mismatches += int(
                (~np.isclose(left, right_value, rtol=1e-10, atol=1e-12, equal_nan=True)).sum()
            )
            if column not in available_sources:
                joined = joined.drop(columns=f"{column}_archive")
        changed = False
        for column in available_sources:
            archive_column = f"{column}_archive" if column in legacy.columns else column
            if column not in legacy.columns:
                joined = joined.rename(columns={archive_column: column})
                changed = True
            else:
                replace_mask = overlap & joined[archive_column].notna()
                if replace_mask.any():
                    joined.loc[replace_mask, column] = joined.loc[
                        replace_mask, archive_column
                    ]
                    changed = True
                joined = joined.drop(columns=archive_column)
        if overlap.any():
            if "legacy_source" not in joined.columns:
                joined["legacy_source"] = (
                    joined["source"] if "source" in joined.columns else pd.NA
                )
            if "source" not in joined.columns:
                joined["source"] = pd.NA
            joined.loc[overlap, "source"] = (
                "binance_vision_kline_monthly_overlap_repair"
                if dataset == "kline_1h"
                else "binance_vision_funding_monthly_overlap_repair"
            )
            changed = True
        if changed:
            atomic_parquet(joined, path)
            files_enriched += 1
    return {
        "files_enriched": files_enriched,
        "rows_compared": rows_compared,
        "value_mismatches": value_mismatches,
    }


def inventory_tasks(
    inventory: pd.DataFrame,
    dataset: str,
    month: str,
    selected_symbols: set[str] | None,
) -> list[str]:
    month_column = f"{dataset}_month_list"
    symbols = []
    for row in inventory[["symbol", month_column]].itertuples(index=False):
        symbol = str(row.symbol)
        months = set(str(getattr(row, month_column) or "").split(";"))
        if month in months and (selected_symbols is None or symbol in selected_symbols):
            symbols.append(symbol)
    return symbols


def month_range(start: str, end: str) -> list[str]:
    return pd.period_range(start, end, freq="M").astype(str).tolist()


def process_month(
    inventory: pd.DataFrame,
    dataset: str,
    month: str,
    *,
    selected_symbols: set[str] | None,
    workers: int,
    timeout: float,
    attempts: int,
    overwrite_output: bool,
    download_only: bool,
) -> dict[str, Any]:
    config = DATASET_CONFIG[dataset]
    raw_root = Path(config["raw_root"])
    normalized_root = Path(config["normalized_root"])
    raw_path = monthly_output_path(raw_root, month)
    normalized_path = monthly_output_path(normalized_root, month)
    symbols = inventory_tasks(inventory, dataset, month, selected_symbols)
    if not symbols:
        return {"dataset": dataset, "month": month, "status": "no_archives", "symbols": 0}
    if (
        not overwrite_output
        and not download_only
        and output_is_complete(raw_path, normalized_path, symbols)
    ):
        return {
            "dataset": dataset,
            "month": month,
            "status": "existing_output",
            "symbols": len(symbols),
        }

    frames: list[pd.DataFrame] = []
    archive_results: list[ArchiveResult] = []
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                parse_archive,
                dataset,
                symbol,
                month,
                timeout=timeout,
                attempts=attempts,
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
            if not download_only:
                frames.append(frame)
            archive_results.append(result)

    if failures:
        return {
            "dataset": dataset,
            "month": month,
            "status": "failed",
            "symbols": len(symbols),
            "archives_ok": len(archive_results),
            "failures": failures,
        }
    if download_only:
        return {
            "dataset": dataset,
            "month": month,
            "status": "downloaded",
            "symbols": len(symbols),
            "archive_bytes": sum(item.archive_bytes for item in archive_results),
            "archive_rows": sum(item.rows for item in archive_results),
        }

    raw = pd.concat(frames, ignore_index=True, sort=False)
    normalized = (
        normalize_funding(raw)
        if dataset == "funding"
        else normalize_kline(raw, mark_price=dataset == "mark_1h")
    )
    duplicate_rows = int(normalized.duplicated(["ts", "symbol"], keep=False).sum())
    duplicate_conflict_groups = 0
    if duplicate_rows:
        if dataset != "funding":
            raise RuntimeError(
                f"{dataset} {month} has {duplicate_rows} duplicate normalized rows"
            )
        duplicate_frame = normalized.loc[
            normalized.duplicated(["ts", "symbol"], keep=False)
        ]
        conflicts = duplicate_frame.groupby(["ts", "symbol"])[
            ["funding_rate", "funding_interval_hours"]
        ].nunique(dropna=False)
        duplicate_conflict_groups = int(conflicts.gt(1).any(axis=1).sum())
        normalized = normalized.drop_duplicates(["ts", "symbol"], keep="last")
    legacy_enrichment = enrich_legacy_daily_files(
        dataset,
        normalized,
        normalized_root,
    )
    normalized, overlap = remove_legacy_overlap(
        normalized,
        normalized_root,
        month,
        timestamp_column="ts",
    )
    retained_keys = normalized[["ts", "symbol"]]
    raw["ts"] = (
        pd.to_datetime(raw["calc_time"], unit="ms", utc=True).dt.round("s")
        if dataset == "funding"
        else raw["open_time"]
    )
    raw["symbol"] = canonical_symbol(raw["archive_symbol"])
    if dataset == "funding":
        raw["source_revision_order"] = raw.groupby(["ts", "symbol"]).cumcount()
    raw = raw.merge(retained_keys.assign(_retain=True), on=["ts", "symbol"], how="inner")
    raw = raw.drop(columns="_retain")

    atomic_parquet(raw.sort_values(["ts", "symbol"]), raw_path)
    atomic_parquet(normalized.sort_values(["ts", "symbol"]), normalized_path)
    marker = {
        "dataset": dataset,
        "month": month,
        "archive_symbols": sorted(symbols),
        "archive_rows": sum(item.rows for item in archive_results),
        "legacy_overlap_excluded": overlap,
        "duplicate_source_rows_deduplicated": duplicate_rows,
        "duplicate_conflict_groups_resolved_by_archive_order": (
            duplicate_conflict_groups
        ),
        "legacy_enrichment": legacy_enrichment,
        "raw_rows_written": len(raw),
        "normalized_rows_written": len(normalized),
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
    }
    marker_path = completion_marker(normalized_path)
    marker_path.write_text(
        json.dumps(marker, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "dataset": dataset,
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
    months = month_range(args.start_month, args.end_month)
    if args.start_month > args.end_month:
        raise ValueError("start month must not be after end month")
    units = [(dataset, month) for month in months for dataset in args.datasets]
    tasks = sum(
        len(inventory_tasks(inventory, dataset, month, selected_symbols))
        for dataset, month in units
    )
    print(
        f"units={len(units)} archives={tasks} datasets={args.datasets} "
        f"months={args.start_month}..{args.end_month}"
    )
    if args.dry_run:
        return

    stamp = pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    manifest_path = ARTIFACT_DIR / f"binance_usdm_sync_manifest_{stamp}.jsonl"
    failed_units = 0
    for index, (dataset, month) in enumerate(units, start=1):
        started = time.monotonic()
        result = process_month(
            inventory,
            dataset,
            month,
            selected_symbols=selected_symbols,
            workers=args.workers,
            timeout=args.timeout,
            attempts=args.attempts,
            overwrite_output=args.overwrite_output,
            download_only=args.download_only,
        )
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["generated_at"] = pd.Timestamp.now("UTC").isoformat()
        append_manifest(manifest_path, result)
        if result["status"] == "failed":
            failed_units += 1
        print(
            f"[{index}/{len(units)}] {dataset} {month} "
            f"status={result['status']} symbols={result['symbols']} "
            f"elapsed={result['elapsed_seconds']}s"
        )
    print(f"manifest -> {manifest_path}")
    if failed_units:
        raise RuntimeError(f"{failed_units} dataset-month units failed; inspect manifest")


if __name__ == "__main__":
    main()
