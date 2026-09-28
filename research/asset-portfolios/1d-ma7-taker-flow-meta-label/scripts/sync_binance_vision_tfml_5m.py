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
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-taker-flow-meta-label"
RAW_ROOT = ROOT / (
    "data/raw/taker_flow/exchange=binance/market_type=perp/"
    "timeframe=5m/source=binance_vision"
)
CACHE_DIR = ROOT / "data/cache/binance_1d_ma7_tfml_p0_unaccepted"
ARTIFACT_DIR = FAMILY_DIR / "artifacts/p0_data_2026-08-10"
S3_ENDPOINT = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DOWNLOAD_ROOT = "https://data.binance.vision"
END_EXCLUSIVE = pd.Timestamp("2025-05-31T00:00:00Z")
MIN_MONTH = pd.Period("2020-01", freq="M")
ASSET_SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "BNB": "BNBUSDT",
    "SOL": "SOLUSDT",
    "TRX": "TRXUSDT",
}
ASSET_SLUGS = {asset: symbol.lower() for asset, symbol in ASSET_SYMBOLS.items()}
KLINE_COLUMNS = (
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
)
OHLC_COLUMNS = ("open", "high", "low", "close")
FLOW_COLUMNS = (
    "volume",
    "quote_volume",
    "trade_count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
)


@dataclass(frozen=True)
class Archive:
    asset: str
    symbol: str
    month: str
    key: str
    etag: str
    size: int
    last_modified: str

    @property
    def url(self) -> str:
        return f"{DOWNLOAD_ROOT}/{self.key}"

    @property
    def raw_path(self) -> Path:
        return (
            RAW_ROOT
            / f"month={self.month}"
            / f"symbol={ASSET_SLUGS[self.asset]}.zip"
        )


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md5_bytes(payload: bytes) -> str:
    return hashlib.md5(payload).hexdigest()  # noqa: S324 - source ETag protocol


def s3_objects(prefix: str) -> list[dict[str, Any]]:
    if "HYPE" in prefix.upper():
        raise RuntimeError("HYPE source request is forbidden")
    objects: list[dict[str, Any]] = []
    continuation: str | None = None
    while True:
        params = {
            "list-type": "2",
            "prefix": prefix,
            "max-keys": "1000",
        }
        if continuation is not None:
            params["continuation-token"] = continuation
        request = urllib.request.Request(
            f"{S3_ENDPOINT}?{urllib.parse.urlencode(params)}",
            headers={"User-Agent": "quant-research-lab-tfml-p0/1.0"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            root = ET.fromstring(response.read())
        namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
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
        continuation = root.findtext(
            "s3:NextContinuationToken", default="", namespaces=namespace
        )
        if not truncated:
            break
    return objects


def list_archives(asset: str, symbol: str) -> list[Archive]:
    if asset == "HYPE" or symbol == "HYPEUSDT":
        raise RuntimeError("HYPE listing is forbidden")
    prefix = f"data/futures/um/monthly/klines/{symbol}/5m/"
    marker = f"{symbol}-5m-"
    archives: list[Archive] = []
    for item in s3_objects(prefix):
        key = str(item["key"])
        filename = Path(key).name
        if not filename.startswith(marker) or not filename.endswith(".zip"):
            continue
        month_text = filename[len(marker) : -4]
        try:
            month = pd.Period(month_text, freq="M")
        except ValueError:
            continue
        if MIN_MONTH <= month <= pd.Period("2025-05", freq="M"):
            archives.append(
                Archive(
                    asset=asset,
                    symbol=symbol,
                    month=str(month),
                    key=key,
                    etag=str(item["etag"]),
                    size=int(item["size"]),
                    last_modified=str(item["last_modified"]),
                )
            )
    archives.sort(key=lambda item: item.month)
    if not archives:
        raise RuntimeError(f"No 5m archives for {asset}")
    months = pd.PeriodIndex([item.month for item in archives], freq="M")
    expected = pd.period_range(months.min(), pd.Period("2025-05", freq="M"))
    if months.duplicated().any() or not months.equals(expected):
        raise RuntimeError(
            f"{asset} monthly listing incomplete: "
            f"first={months.min()} last={months.max()} rows={len(months)}"
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
                headers={"User-Agent": "quant-research-lab-tfml-p0/1.0"},
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
        except Exception as exc:  # noqa: BLE001 - bounded network retry
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(0.5 * (2**attempt))
    raise RuntimeError(f"Failed {archive.url}: {last_error}")


def download_all(archives: list[Archive], max_workers: int) -> dict[str, int]:
    counts = {"cached": 0, "downloaded": 0}
    completed = 0
    lock = threading.Lock()
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
                if completed % 50 == 0 or completed == len(archives):
                    print(f"DOWNLOAD_PROGRESS {completed}/{len(archives)}")
    return counts


def parse_epoch(values: pd.Series) -> pd.DatetimeIndex:
    numeric = pd.to_numeric(values, errors="raise").astype("int64")
    unit = "us" if int(numeric.abs().median()) >= 100_000_000_000_000 else "ms"
    return pd.DatetimeIndex(pd.to_datetime(numeric, unit=unit, utc=True))


def parse_archive(archive: Archive) -> pd.DataFrame:
    payload = archive.raw_path.read_bytes()
    if len(payload) != archive.size or md5_bytes(payload) != archive.etag:
        raise RuntimeError(f"{archive.raw_path} identity mismatch")
    with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
        if bundle.testzip() is not None:
            raise RuntimeError(f"{archive.raw_path} failed ZIP CRC")
        members = [name for name in bundle.namelist() if name.endswith(".csv")]
        if len(members) != 1:
            raise RuntimeError(f"{archive.raw_path} has {len(members)} CSV files")
        frame = pd.read_csv(bundle.open(members[0]), header=None)
    if frame.shape[1] != len(KLINE_COLUMNS):
        raise RuntimeError(f"{archive.raw_path} schema width changed")
    if str(frame.iloc[0, 0]).strip().lower() == "open_time":
        frame = frame.iloc[1:].reset_index(drop=True)
    frame.columns = KLINE_COLUMNS
    if frame.empty:
        raise RuntimeError(f"{archive.raw_path} is empty")
    frame["ts"] = parse_epoch(frame.pop("open_time"))
    frame["close_ts"] = parse_epoch(frame.pop("close_time"))
    for column in (*OHLC_COLUMNS, *FLOW_COLUMNS, "ignore"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    timestamps = pd.DatetimeIndex(frame["ts"])
    if (
        timestamps.duplicated().any()
        or not timestamps.is_monotonic_increasing
        or not timestamps.equals(timestamps.floor("5min"))
    ):
        raise RuntimeError(f"{archive.raw_path} timestamps are invalid")
    expected_close = timestamps + pd.Timedelta(minutes=5) - pd.Timedelta(
        milliseconds=1
    )
    if not pd.DatetimeIndex(frame["close_ts"]).equals(expected_close):
        raise RuntimeError(f"{archive.raw_path} close-time mismatch")
    archive_period = pd.Period(archive.month, freq="M")
    if not all(
        pd.Period(timestamp, freq="M") == archive_period
        for timestamp in timestamps
    ):
        raise RuntimeError(f"{archive.raw_path} contains cross-month rows")
    ohlc = frame[list(OHLC_COLUMNS)].to_numpy(dtype="float64")
    flows = frame[list(FLOW_COLUMNS)].to_numpy(dtype="float64")
    if not np.isfinite(ohlc).all() or np.any(ohlc <= 0.0):
        raise RuntimeError(f"{archive.raw_path} has invalid OHLC")
    if not np.isfinite(flows).all() or np.any(flows < 0.0):
        raise RuntimeError(f"{archive.raw_path} has invalid flow fields")
    if (
        np.any(frame["high"] < frame[["open", "close"]].max(axis=1))
        or np.any(frame["low"] > frame[["open", "close"]].min(axis=1))
        or np.any(frame["high"] < frame["low"])
    ):
        raise RuntimeError(f"{archive.raw_path} violates OHLC constraints")
    volume_tolerance = np.maximum(
        1e-12,
        np.abs(frame["volume"].to_numpy(dtype="float64")) * 1e-10,
    )
    quote_tolerance = np.maximum(
        1e-8,
        np.abs(frame["quote_volume"].to_numpy(dtype="float64")) * 1e-10,
    )
    invalid_base = (
        frame["taker_buy_volume"].to_numpy(dtype="float64")
        > frame["volume"].to_numpy(dtype="float64") + volume_tolerance
    )
    invalid_quote = (
        frame["taker_buy_quote_volume"].to_numpy(dtype="float64")
        > frame["quote_volume"].to_numpy(dtype="float64") + quote_tolerance
    )
    invalid_flow = invalid_base | invalid_quote
    invalid_flow_rows = [
        {
            "ts": pd.Timestamp(frame.iloc[index]["ts"]),
            "base_exceeds_total": bool(invalid_base[index]),
            "quote_exceeds_total": bool(invalid_quote[index]),
        }
        for index in np.flatnonzero(invalid_flow)
    ]
    if invalid_flow.any():
        frame = frame.loc[~invalid_flow].reset_index(drop=True)
        if frame.empty:
            raise RuntimeError(
                f"{archive.raw_path} has no rows after flow-quality admission"
            )
    frame.insert(1, "exchange", "binance")
    frame.insert(2, "market_type", "perp")
    frame.insert(3, "timeframe", "5m")
    frame.insert(4, "source", "binance_vision_monthly")
    frame.insert(5, "asset", archive.asset)
    frame.insert(6, "symbol", archive.symbol)
    frame.attrs["invalid_flow_rows"] = invalid_flow_rows
    return frame


def build_asset_cache(
    asset: str,
    archives: list[Archive],
) -> dict[str, Any]:
    parsed_frames: list[pd.DataFrame] = []
    invalid_flow_rows: list[dict[str, Any]] = []
    for archive in archives:
        parsed = parse_archive(archive)
        invalid_flow_rows.extend(parsed.attrs.get("invalid_flow_rows", []))
        parsed_frames.append(parsed)
    frame = pd.concat(parsed_frames, ignore_index=True)
    frame = frame.sort_values("ts").reset_index(drop=True)
    frame = frame.loc[frame["ts"] < END_EXCLUSIVE].reset_index(drop=True)
    timestamps = pd.DatetimeIndex(frame["ts"])
    if timestamps.duplicated().any():
        raise RuntimeError(f"{asset} combined flow has duplicate timestamps")
    expected = pd.date_range(
        timestamps.min(),
        END_EXCLUSIVE - pd.Timedelta(minutes=5),
        freq="5min",
        tz="UTC",
    )
    missing = expected.difference(timestamps)
    extra = timestamps.difference(expected)
    if len(extra):
        raise RuntimeError(f"{asset} has out-of-range 5m timestamps")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    output = CACHE_DIR / f"{ASSET_SLUGS[asset]}_perp_5m_taker_flow.parquet"
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    frame.to_parquet(temporary, index=False)
    temporary.replace(output)
    return {
        "asset": asset,
        "rows": int(len(frame)),
        "expected_rows": int(len(expected)),
        "start": timestamps.min(),
        "end": timestamps.max(),
        "missing_5m": int(len(missing)),
        "first_missing_5m": list(missing[:100]),
        "invalid_flow_rows_excluded": int(len(invalid_flow_rows)),
        "first_invalid_flow_rows": invalid_flow_rows[:100],
        "duplicate_ts": 0,
        "source_months": len(archives),
        "cache_path": str(output.relative_to(ROOT)),
        "cache_sha256": sha256_path(output),
    }


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return json_ready(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(json_ready(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_artifacts(
    archives: list[Archive],
    quality: dict[str, dict[str, Any]],
    download_counts: dict[str, int],
) -> dict[str, str]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    source_manifest = {
        "schema_version": "binance-1d-ma7-tfml-source-v1",
        "generated_at_utc": pd.Timestamp.now(tz="UTC"),
        "source": "Binance Vision public S3",
        "archive_count": len(archives),
        "compressed_bytes": int(sum(archive.size for archive in archives)),
        "download_counts": download_counts,
        "development_end_exclusive": END_EXCLUSIVE,
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
    source_continuity_pass = all(
        int(details["missing_5m"]) == 0 for details in quality.values()
    )
    quality_payload = {
        "schema_version": "binance-1d-ma7-tfml-quality-v1",
        "generated_at_utc": pd.Timestamp.now(tz="UTC"),
        "assets": quality,
        "archive_count": len(archives),
        "archive_identity_schema_pass": True,
        "source_continuity_pass": source_continuity_pass,
        "event_level_admission_required": not source_continuity_pass,
        "hype_rows_consumed": 0,
        "hype_files_opened": 0,
        "hype_requests_sent": 0,
    }
    source_path = ARTIFACT_DIR / "p0_source_manifest.json"
    quality_path = ARTIFACT_DIR / "p0_data_quality.json"
    write_json(source_path, source_manifest)
    write_json(quality_path, quality_payload)
    files: dict[str, Any] = {
        "source_manifest": {
            "path": source_path.name,
            "sha256": sha256_path(source_path),
        },
        "data_quality": {
            "path": quality_path.name,
            "sha256": sha256_path(quality_path),
        },
    }
    for asset, details in quality.items():
        files[f"{asset.lower()}_flow_cache"] = {
            "path": details["cache_path"],
            "sha256": details["cache_sha256"],
        }
    manifest = {
        "schema_version": "binance-1d-ma7-tfml-p0-manifest-v1",
        "generated_at_utc": pd.Timestamp.now(tz="UTC"),
        "files": files,
    }
    manifest_path = ARTIFACT_DIR / "manifest.json"
    write_json(manifest_path, manifest)
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
    parser.add_argument("--max-workers", type=int, default=20)
    parser.add_argument("--list-only", action="store_true")
    args = parser.parse_args()
    if args.max_workers < 1 or args.max_workers > 64:
        raise ValueError("--max-workers must be in [1, 64]")
    archive_map = {
        asset: list_archives(asset, symbol)
        for asset, symbol in ASSET_SYMBOLS.items()
    }
    archives = [
        archive for asset in ASSET_SYMBOLS for archive in archive_map[asset]
    ]
    listing = {
        asset: {
            "archives": len(asset_archives),
            "first": asset_archives[0].month,
            "last": asset_archives[-1].month,
            "compressed_bytes": int(
                sum(archive.size for archive in asset_archives)
            ),
        }
        for asset, asset_archives in archive_map.items()
    }
    if args.list_only:
        print(json.dumps(listing, indent=2))
        return
    download_counts = download_all(archives, args.max_workers)
    quality = {
        asset: build_asset_cache(asset, archive_map[asset])
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
