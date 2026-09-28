from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import threading
import time
from typing import Any
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / (
    "research/asset-portfolios/1d-derivatives-structure-trend-opportunity"
)
RAW_ROOT = ROOT / (
    "data/raw/derivatives_metrics/exchange=binance/market_type=perp/"
    "timeframe=5m/source=binance_vision"
)
FEATURE_DIR = ROOT / "data/features/binance_1d_dsto_p0"
AUDIT_CACHE_DIR = ROOT / "data/cache/binance_1d_dsto_p0_unaccepted"
ARTIFACT_DIR = FAMILY_DIR / "artifacts/p0_data_2026-08-10"
S3_ENDPOINT = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DOWNLOAD_ROOT = "https://data.binance.vision"
START_DATE = pd.Timestamp("2021-12-01T00:00:00Z")
END_DATE_EXCLUSIVE = pd.Timestamp("2025-05-31T00:00:00Z")
ASSET_SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "BNB": "BNBUSDT",
    "SOL": "SOLUSDT",
    "TRX": "TRXUSDT",
}
ASSET_SLUGS = {asset: symbol.lower() for asset, symbol in ASSET_SYMBOLS.items()}
NATIVE_COLUMNS = (
    "create_time",
    "symbol",
    "sum_open_interest",
    "sum_open_interest_value",
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)
NUMERIC_COLUMNS = NATIVE_COLUMNS[2:]


@dataclass(frozen=True)
class Archive:
    asset: str
    symbol: str
    date: str
    key: str
    etag: str
    size: int
    last_modified: str

    @property
    def url(self) -> str:
        return f"{DOWNLOAD_ROOT}/{self.key}"

    @property
    def raw_path(self) -> Path:
        slug = ASSET_SLUGS[self.asset]
        return RAW_ROOT / f"date={self.date}" / f"symbol={slug}.zip"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md5_bytes(payload: bytes) -> str:
    return hashlib.md5(payload).hexdigest()  # noqa: S324 - source ETag protocol


def s3_page(symbol: str, continuation: str | None) -> tuple[list[dict[str, Any]], str | None]:
    if symbol == "HYPEUSDT" or symbol not in ASSET_SYMBOLS.values():
        raise RuntimeError(f"Forbidden metrics symbol: {symbol}")
    params = {
        "list-type": "2",
        "prefix": f"data/futures/um/daily/metrics/{symbol}/",
        "max-keys": "1000",
    }
    if continuation is not None:
        params["continuation-token"] = continuation
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{S3_ENDPOINT}?{query}",
        headers={"User-Agent": "quant-research-lab-dsto-p0/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
    root = ET.fromstring(payload)
    namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    objects: list[dict[str, Any]] = []
    for item in root.findall("s3:Contents", namespace):
        objects.append(
            {
                "key": item.findtext(
                    "s3:Key", default="", namespaces=namespace
                ),
                "etag": item.findtext(
                    "s3:ETag", default="", namespaces=namespace
                ).strip('"'),
                "size": int(
                    item.findtext("s3:Size", default="0", namespaces=namespace)
                ),
                "last_modified": item.findtext(
                    "s3:LastModified", default="", namespaces=namespace
                ),
            }
        )
    truncated = (
        root.findtext("s3:IsTruncated", default="false", namespaces=namespace)
        == "true"
    )
    token = root.findtext(
        "s3:NextContinuationToken", default="", namespaces=namespace
    )
    return objects, token if truncated else None


def list_archives(asset: str, symbol: str) -> list[Archive]:
    objects: list[dict[str, Any]] = []
    continuation: str | None = None
    while True:
        page, continuation = s3_page(symbol, continuation)
        objects.extend(page)
        if continuation is None:
            break
    marker = f"{symbol}-metrics-"
    archives: list[Archive] = []
    for item in objects:
        key = str(item["key"])
        filename = Path(key).name
        if not filename.endswith(".zip") or not filename.startswith(marker):
            continue
        date_text = filename[len(marker) : -4]
        date = pd.Timestamp(date_text, tz="UTC")
        if START_DATE <= date < END_DATE_EXCLUSIVE:
            archives.append(
                Archive(
                    asset=asset,
                    symbol=symbol,
                    date=date.strftime("%Y-%m-%d"),
                    key=key,
                    etag=str(item["etag"]),
                    size=int(item["size"]),
                    last_modified=str(item["last_modified"]),
                )
            )
    archives.sort(key=lambda item: item.date)
    expected_dates = pd.date_range(
        START_DATE,
        END_DATE_EXCLUSIVE - pd.Timedelta(days=1),
        freq="1D",
        tz="UTC",
    )
    actual_dates = pd.DatetimeIndex(
        [pd.Timestamp(item.date, tz="UTC") for item in archives]
    )
    missing = expected_dates.difference(actual_dates)
    duplicates = actual_dates[actual_dates.duplicated()]
    if len(missing) or len(duplicates) or len(archives) != len(expected_dates):
        raise RuntimeError(
            f"{asset} archive listing incomplete: "
            f"expected={len(expected_dates)} actual={len(archives)} "
            f"missing={list(missing[:5])} duplicates={list(duplicates[:5])}"
        )
    return archives


def valid_cached_archive(archive: Archive) -> bool:
    path = archive.raw_path
    if not path.exists() or path.stat().st_size != archive.size:
        return False
    payload = path.read_bytes()
    if md5_bytes(payload) != archive.etag:
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
            return bundle.testzip() is None
    except zipfile.BadZipFile:
        return False


def download_archive(archive: Archive, retries: int = 4) -> str:
    if valid_cached_archive(archive):
        return "cached"
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                archive.url,
                headers={"User-Agent": "quant-research-lab-dsto-p0/1.0"},
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
            if len(payload) != archive.size:
                raise RuntimeError(
                    f"size mismatch {len(payload)} != {archive.size}"
                )
            if md5_bytes(payload) != archive.etag:
                raise RuntimeError("ETag/MD5 mismatch")
            with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
                if bundle.testzip() is not None:
                    raise RuntimeError("ZIP CRC failure")
            path = archive.raw_path
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(
                f".{path.name}.tmp-{os.getpid()}-{threading.get_ident()}"
            )
            temporary.write_bytes(payload)
            temporary.replace(path)
            return "downloaded"
        except Exception as exc:  # noqa: BLE001 - retry captures network/ZIP errors
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(0.5 * (2**attempt))
    raise RuntimeError(f"Failed {archive.url}: {last_error}")


def download_all(archives: list[Archive], max_workers: int) -> dict[str, int]:
    counts = {"cached": 0, "downloaded": 0}
    lock = threading.Lock()
    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(download_archive, archive): archive
            for archive in archives
        }
        for future in as_completed(futures):
            status = future.result()
            with lock:
                counts[status] += 1
                completed += 1
                if completed % 250 == 0 or completed == len(archives):
                    print(f"DOWNLOAD_PROGRESS {completed}/{len(archives)}")
    return counts


def parse_archive(
    archive: Archive, *, allow_source_gaps: bool
) -> tuple[pd.DataFrame, dict[str, Any]]:
    payload = archive.raw_path.read_bytes()
    if len(payload) != archive.size or md5_bytes(payload) != archive.etag:
        raise RuntimeError(f"{archive.raw_path} identity mismatch")
    with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
        if bundle.testzip() is not None:
            raise RuntimeError(f"{archive.raw_path} failed ZIP CRC")
        members = [name for name in bundle.namelist() if name.endswith(".csv")]
        if len(members) != 1:
            raise RuntimeError(f"{archive.raw_path} has {len(members)} CSV files")
        frame = pd.read_csv(bundle.open(members[0]))
    if tuple(frame.columns) != NATIVE_COLUMNS:
        raise RuntimeError(f"{archive.raw_path} schema changed")
    if len(frame) > 288 or frame.empty:
        raise RuntimeError(f"{archive.raw_path} has invalid row count {len(frame)}")
    frame["ts"] = pd.to_datetime(frame.pop("create_time"), utc=True)
    expected_ts = pd.date_range(
        pd.Timestamp(archive.date, tz="UTC"),
        periods=288,
        freq="5min",
        tz="UTC",
    )
    actual_ts = pd.DatetimeIndex(frame["ts"])
    invalid_timestamp_rows = int((~actual_ts.isin(expected_ts)).sum())
    duplicate_timestamps = int(actual_ts.duplicated().sum())
    timestamps_invalid = (
        duplicate_timestamps > 0
        or not actual_ts.is_monotonic_increasing
        or invalid_timestamp_rows > 0
    )
    if timestamps_invalid and not allow_source_gaps:
        raise RuntimeError(f"{archive.raw_path} has invalid UTC 5m timestamps")
    missing_rows = len(expected_ts.difference(actual_ts))
    if missing_rows and not allow_source_gaps:
        raise RuntimeError(
            f"{archive.raw_path} has {len(frame)} rows, expected 288"
        )
    if frame["symbol"].nunique() != 1 or frame["symbol"].iloc[0] != archive.symbol:
        raise RuntimeError(f"{archive.raw_path} symbol mismatch")
    invalid_values: dict[str, int] = {}
    for column in NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        values = frame[column].to_numpy(dtype="float64")
        invalid = ~np.isfinite(values) | (values <= 0.0)
        invalid_values[column] = int(invalid.sum())
        if invalid.any() and not allow_source_gaps:
            raise RuntimeError(f"{archive.raw_path} invalid {column}")
    frame.insert(1, "exchange", "binance")
    frame.insert(2, "market_type", "perp")
    frame.insert(3, "timeframe", "5m")
    frame.insert(4, "source", "binance_vision_metrics")
    frame.insert(5, "asset", archive.asset)
    frame.insert(6, "date", archive.date)
    return frame, {
        "missing_timestamp_rows": missing_rows,
        "invalid_timestamp_rows": invalid_timestamp_rows,
        "duplicate_timestamps": duplicate_timestamps,
        "timestamps_monotonic": actual_ts.is_monotonic_increasing,
        "invalid_values": invalid_values,
        "has_invalid_values": any(invalid_values.values()),
    }


def build_asset_feature(
    asset: str,
    archives: list[Archive],
    *,
    allow_source_gaps: bool,
) -> dict[str, Any]:
    parsed = [
        parse_archive(archive, allow_source_gaps=allow_source_gaps)
        for archive in archives
    ]
    frames = [item[0] for item in parsed]
    archive_quality = [item[1] for item in parsed]
    archive_missing_rows = [
        int(item["missing_timestamp_rows"]) for item in archive_quality
    ]
    feature = pd.concat(frames, ignore_index=True)
    feature = feature.sort_values("ts").reset_index(drop=True)
    timestamps = pd.DatetimeIndex(feature["ts"])
    combined_duplicates = int(feature["ts"].duplicated().sum())
    if combined_duplicates and not allow_source_gaps:
        raise RuntimeError(f"{asset} metrics contain duplicate timestamps")
    expected = pd.date_range(
        START_DATE,
        END_DATE_EXCLUSIVE - pd.Timedelta(minutes=5),
        freq="5min",
        tz="UTC",
    )
    missing = expected.difference(timestamps)
    if len(missing) and not allow_source_gaps:
        raise RuntimeError(f"{asset} combined metrics are not continuous")
    output_root = AUDIT_CACHE_DIR if allow_source_gaps else FEATURE_DIR
    output_root.mkdir(parents=True, exist_ok=True)
    output = output_root / f"{ASSET_SLUGS[asset]}_metrics_5m.parquet"
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    feature.to_parquet(temporary, index=False)
    temporary.replace(output)
    return {
        "asset": asset,
        "rows": len(feature),
        "start": timestamps.min(),
        "end": timestamps.max(),
        "missing_5m": len(missing),
        "source_days_with_gaps": int(
            sum(value > 0 for value in archive_missing_rows)
        ),
        "source_days_with_invalid_values": int(
            sum(bool(item["has_invalid_values"]) for item in archive_quality)
        ),
        "source_days_with_invalid_timestamps": int(
            sum(
                item["invalid_timestamp_rows"] > 0
                or item["duplicate_timestamps"] > 0
                or not item["timestamps_monotonic"]
                for item in archive_quality
            )
        ),
        "invalid_timestamp_rows": int(
            sum(item["invalid_timestamp_rows"] for item in archive_quality)
        ),
        "maximum_missing_rows_in_day": int(max(archive_missing_rows)),
        "invalid_values_by_column": {
            column: int(
                sum(item["invalid_values"][column] for item in archive_quality)
            )
            for column in NUMERIC_COLUMNS
        },
        "duplicate_ts": combined_duplicates,
        "source_days": len(archives),
        "feature_path": str(output.relative_to(ROOT)),
        "feature_sha256": sha256_path(output),
    }


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_artifacts(
    archives: list[Archive],
    quality: dict[str, Any],
    download_counts: dict[str, int],
) -> dict[str, str]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    source_manifest = {
        "schema_version": "binance-1d-dsto-source-manifest-v1",
        "generated_at_utc": pd.Timestamp.now(tz="UTC"),
        "source": "Binance Vision public S3",
        "start_date": START_DATE,
        "end_date_exclusive": END_DATE_EXCLUSIVE,
        "archive_count": len(archives),
        "download_counts": download_counts,
        "hype_requests_sent": 0,
        "archives": [
            asdict(archive)
            | {
                "url": archive.url,
                "raw_path": str(archive.raw_path.relative_to(ROOT)),
                "sha256": sha256_path(archive.raw_path),
            }
            for archive in archives
        ],
    }
    quality_payload = {
        "schema_version": "binance-1d-dsto-p0-quality-v1",
        "generated_at_utc": pd.Timestamp.now(tz="UTC"),
        "assets": quality,
        "archive_count": len(archives),
        "expected_archive_count": len(
            pd.date_range(
                START_DATE,
                END_DATE_EXCLUSIVE - pd.Timedelta(days=1),
                freq="1D",
                tz="UTC",
            )
        )
        * len(ASSET_SYMBOLS),
        "hype_rows_consumed": 0,
        "hype_files_opened": 0,
        "hype_requests_sent": 0,
        "quality_pass": all(
            details["missing_5m"] == 0
            and details["duplicate_ts"] == 0
            and details["source_days_with_invalid_values"] == 0
            for details in quality.values()
        ),
    }
    source_path = ARTIFACT_DIR / "p0_source_manifest.json"
    quality_path = ARTIFACT_DIR / "p0_data_quality.json"
    source_path.write_text(
        json.dumps(json_ready(source_manifest), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    quality_path.write_text(
        json.dumps(json_ready(quality_payload), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "binance-1d-dsto-p0-manifest-v1",
        "files": {
            "source_manifest": {
                "path": source_path.name,
                "sha256": sha256_path(source_path),
            },
            "data_quality": {
                "path": quality_path.name,
                "sha256": sha256_path(quality_path),
            },
            **{
                f"{asset.lower()}_feature": {
                    "path": details["feature_path"],
                    "sha256": details["feature_sha256"],
                }
                for asset, details in quality.items()
            },
        },
    }
    manifest_path = ARTIFACT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(json_ready(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    checksum_path = ARTIFACT_DIR / "manifest.sha256"
    checksum_path.write_text(
        f"{sha256_path(manifest_path)}  {manifest_path.name}\n",
        encoding="utf-8",
    )
    return {
        "source_manifest": sha256_path(source_path),
        "data_quality": sha256_path(quality_path),
        "manifest": sha256_path(manifest_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-workers", type=int, default=24)
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--audit-source-gaps", action="store_true")
    args = parser.parse_args()
    if args.max_workers < 1 or args.max_workers > 64:
        raise ValueError("--max-workers must be in [1, 64]")
    archive_by_asset = {
        asset: list_archives(asset, symbol)
        for asset, symbol in ASSET_SYMBOLS.items()
    }
    archives = [
        archive
        for asset in ASSET_SYMBOLS
        for archive in archive_by_asset[asset]
    ]
    listing = {
        asset: {
            "archives": len(items),
            "first": items[0].date,
            "last": items[-1].date,
        }
        for asset, items in archive_by_asset.items()
    }
    if args.list_only:
        print(json.dumps(listing, indent=2))
        return
    download_counts = download_all(archives, args.max_workers)
    quality = {
        asset: build_asset_feature(
            asset,
            archive_by_asset[asset],
            allow_source_gaps=args.audit_source_gaps,
        )
        for asset in ASSET_SYMBOLS
    }
    hashes = write_artifacts(archives, quality, download_counts)
    print(
        json.dumps(
            json_ready(
                {
                    "listing": listing,
                    "download_counts": download_counts,
                    "quality": quality,
                    "artifact_sha256": hashes,
                }
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
