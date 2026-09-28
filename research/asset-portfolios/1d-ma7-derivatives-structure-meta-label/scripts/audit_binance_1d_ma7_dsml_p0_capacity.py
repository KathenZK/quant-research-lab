from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / (
    "research/asset-portfolios/1d-ma7-derivatives-structure-meta-label"
)
EVENT_PATH = ROOT / (
    "research/asset-portfolios/1d-ma7-later-maturity-meta-label/"
    "artifacts/p1_development_2026-08-10/p0_p1_events.parquet"
)
ARTIFACT_DIR = FAMILY_DIR / "artifacts/p0_capacity_2026-08-10"
ASSET_SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "BNB": "BNBUSDT",
    "SOL": "SOLUSDT",
    "TRX": "TRXUSDT",
}
EXPECTED_EVENTS = 1_448
CONTEXT_DAYS = 30
S3_LIST_ENDPOINT = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def first_archive(symbol: str) -> dict[str, Any]:
    if symbol == "HYPEUSDT" or symbol not in ASSET_SYMBOLS.values():
        raise RuntimeError(f"Forbidden symbol: {symbol}")
    prefix = f"data/futures/um/daily/metrics/{symbol}/"
    query = urllib.parse.urlencode(
        {"list-type": "2", "prefix": prefix, "max-keys": "2"}
    )
    request = urllib.request.Request(
        f"{S3_LIST_ENDPOINT}?{query}",
        headers={"User-Agent": "quant-research-lab-dsml-p0/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
    root = ET.fromstring(payload)
    namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    entries = []
    for item in root.findall("s3:Contents", namespace):
        key = item.findtext("s3:Key", default="", namespaces=namespace)
        if not key.endswith(".zip"):
            continue
        entries.append(
            {
                "key": key,
                "last_modified": item.findtext(
                    "s3:LastModified", default="", namespaces=namespace
                ),
                "etag": item.findtext(
                    "s3:ETag", default="", namespaces=namespace
                ).strip('"'),
                "size": int(
                    item.findtext("s3:Size", default="0", namespaces=namespace)
                ),
            }
        )
    if len(entries) != 1:
        raise RuntimeError(f"{symbol} first archive listing is ambiguous")
    archive = entries[0]
    filename = Path(archive["key"]).name
    marker = f"{symbol}-metrics-"
    if not filename.startswith(marker) or not filename.endswith(".zip"):
        raise RuntimeError(f"Unexpected archive key: {archive['key']}")
    date_text = filename[len(marker) : -4]
    first_date = pd.Timestamp(date_text, tz="UTC")
    return {
        "symbol": symbol,
        "listing_url": f"{S3_LIST_ENDPOINT}?{query}",
        "first_archive_date": first_date,
        **archive,
    }


def event_ready_dates(
    first_dates: dict[str, pd.Timestamp],
) -> dict[str, pd.Timestamp]:
    ready: dict[str, pd.Timestamp] = {}
    for asset in ASSET_SYMBOLS:
        local_ready = first_dates[asset] + pd.Timedelta(days=CONTEXT_DAYS)
        peer_ready = sorted(
            first_dates[peer] + pd.Timedelta(days=CONTEXT_DAYS)
            for peer in ASSET_SYMBOLS
            if peer != asset
        )
        third_peer_ready = peer_ready[2]
        ready[asset] = max(local_ready, third_peer_ready)
    return ready


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
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def build_payload() -> dict[str, Any]:
    if "hype" in str(EVENT_PATH).lower():
        raise RuntimeError("HYPE path reached DSML capacity audit")
    events = pd.read_parquet(EVENT_PATH)
    if len(events) != EXPECTED_EVENTS:
        raise RuntimeError(
            f"LMML event identity changed: {len(events)} != {EXPECTED_EVENTS}"
        )
    if set(events["asset"]) != set(ASSET_SYMBOLS):
        raise RuntimeError("LMML event universe changed")
    archives = {
        asset: first_archive(symbol)
        for asset, symbol in ASSET_SYMBOLS.items()
    }
    first_dates = {
        asset: pd.Timestamp(details["first_archive_date"])
        for asset, details in archives.items()
    }
    ready_dates = event_ready_dates(first_dates)
    usable_mask = pd.Series(False, index=events.index)
    for asset, ready in ready_dates.items():
        usable_mask |= (events["asset"] == asset) & (events["signal_ts"] >= ready)
    usable = events.loc[usable_mask].copy()
    per_asset = {
        asset: int((usable["asset"] == asset).sum()) for asset in ASSET_SYMBOLS
    }
    per_side = {
        "long": int((usable["side"] == 1).sum()),
        "short": int((usable["side"] == -1).sum()),
    }
    checks = {
        "usable_events_gte_1300": len(usable) >= 1_300,
        "each_asset_gte_200": all(value >= 200 for value in per_asset.values()),
        "each_side_gte_550": all(value >= 550 for value in per_side.values()),
        "usable_rate_gte_90pct": len(usable) / len(events) >= 0.90,
    }
    return {
        "schema_version": "binance-1d-ma7-dsml-p0-capacity-v1",
        "generated_at_utc": pd.Timestamp.now(tz="UTC"),
        "source": "Binance Vision public S3 object listing",
        "event_path": str(EVENT_PATH.relative_to(ROOT)),
        "event_sha256": sha256_path(EVENT_PATH),
        "event_rows": len(events),
        "context_days": CONTEXT_DAYS,
        "archives": archives,
        "event_ready_dates": ready_dates,
        "maximum_usable_events": len(usable),
        "maximum_usable_rate": len(usable) / len(events),
        "per_asset": per_asset,
        "per_side": per_side,
        "p0_gate_checks": checks,
        "p0_capacity_pass": all(checks.values()),
        "hype_rows_consumed": 0,
        "hype_files_opened": 0,
        "hype_requests_sent": 0,
        "decision": "P0_CAPACITY_FAILED_NO_DOWNLOAD_NO_MODEL",
    }


def write_payload(payload: dict[str, Any]) -> dict[str, str]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    output = ARTIFACT_DIR / "p0_archive_capacity.json"
    output.write_text(
        json.dumps(json_ready(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    checksum = ARTIFACT_DIR / "p0_archive_capacity.sha256"
    checksum.write_text(
        f"{sha256_path(output)}  {output.name}\n", encoding="utf-8"
    )
    return {
        "output": sha256_path(output),
        "checksum": sha256_path(checksum),
    }


def main() -> None:
    payload = build_payload()
    payload["artifact_sha256"] = write_payload(payload)
    print(json.dumps(json_ready(payload), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
