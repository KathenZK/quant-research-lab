from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from http.client import IncompleteRead
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/15m-ema-cross-lightgbm-event-selector"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
FAPI = "https://fapi.binance.com"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
UA = "quant-research-lab-bin-15m-emax-lgbm-inventory/0.1"
START_MONTH = "2020-01"
END_MONTH = "2026-06"

DATASET = "kline_15m"
SYMBOL_PREFIX_ROOT = "data/futures/um/monthly/klines/"
MONTH_PATTERN = re.compile(r"-(20\d{2}-\d{2})\.zip$")


@dataclass(frozen=True, slots=True)
class InventoryItem:
    symbol: str
    months: tuple[str, ...]
    archive_bytes: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory Binance Vision USD-M monthly 15m kline archives for the "
            "BIN-15M-EMAX-LGBM research family."
        )
    )
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=45.0)
    return parser.parse_args()


def request_bytes(url: str, *, timeout: float, attempts: int = 6) -> bytes:
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
        except (URLError, TimeoutError, ConnectionError, IncompleteRead) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(10.0, 0.5 * 2**attempt))
    raise RuntimeError(f"request failed after {attempts} attempts: {url}") from last_error


def s3_query(params: dict[str, object], *, timeout: float) -> ET.Element:
    url = f"{S3}?{urlencode(params)}"
    return ET.fromstring(request_bytes(url, timeout=timeout))


def local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def child_text(element: ET.Element, name: str) -> str | None:
    for child in element:
        if local_name(child) == name:
            return child.text
    return None


def list_common_prefixes(prefix: str, *, timeout: float) -> list[str]:
    token: str | None = None
    prefixes: list[str] = []
    while True:
        params: dict[str, object] = {
            "list-type": "2",
            "delimiter": "/",
            "prefix": prefix,
            "max-keys": 1000,
        }
        if token:
            params["continuation-token"] = token
        root = s3_query(params, timeout=timeout)
        for element in root:
            if local_name(element) != "CommonPrefixes":
                continue
            value = child_text(element, "Prefix")
            if value:
                prefixes.append(value)
        if child_text(root, "IsTruncated") != "true":
            break
        token = child_text(root, "NextContinuationToken")
        if not token:
            raise RuntimeError(f"missing S3 continuation token: {prefix}")
    return prefixes


def list_objects(prefix: str, *, timeout: float) -> list[tuple[str, int]]:
    token: str | None = None
    objects: list[tuple[str, int]] = []
    while True:
        params: dict[str, object] = {
            "list-type": "2",
            "prefix": prefix,
            "max-keys": 1000,
        }
        if token:
            params["continuation-token"] = token
        root = s3_query(params, timeout=timeout)
        for element in root:
            if local_name(element) != "Contents":
                continue
            key = child_text(element, "Key")
            size = child_text(element, "Size")
            if key:
                objects.append((key, int(size or 0)))
        if child_text(root, "IsTruncated") != "true":
            break
        token = child_text(root, "NextContinuationToken")
        if not token:
            raise RuntimeError(f"missing S3 continuation token: {prefix}")
    return objects


def symbol_from_prefix(prefix: str) -> str:
    return prefix.rstrip("/").rsplit("/", 1)[-1]


def is_usdt_perpetual_style(symbol: str) -> bool:
    return symbol.endswith("USDT") and "_" not in symbol and len(symbol) > 4


def inventory_symbol(symbol: str, *, timeout: float) -> InventoryItem:
    prefix = f"{SYMBOL_PREFIX_ROOT}{symbol}/15m/"
    objects = [
        (key, size)
        for key, size in list_objects(prefix, timeout=timeout)
        if key.endswith(".zip")
    ]
    months = tuple(
        sorted(
            {
                match.group(1)
                for key, _ in objects
                if (match := MONTH_PATTERN.search(key))
                and START_MONTH <= match.group(1) <= END_MONTH
            }
        )
    )
    selected = set(months)
    archive_bytes = sum(
        size
        for key, size in objects
        if (match := MONTH_PATTERN.search(key)) and match.group(1) in selected
    )
    return InventoryItem(symbol=symbol, months=months, archive_bytes=archive_bytes)


def current_exchange_info(*, timeout: float) -> pd.DataFrame:
    payload = json.loads(request_bytes(f"{FAPI}/fapi/v1/exchangeInfo", timeout=timeout))
    rows = []
    for item in payload.get("symbols", []):
        if item.get("quoteAsset") != "USDT":
            continue
        contract_type = item.get("contractType")
        underlying_type = item.get("underlyingType")
        rows.append(
            {
                "symbol": item["symbol"],
                "current_status": item.get("status"),
                "onboard_ts": pd.to_datetime(item.get("onboardDate"), unit="ms", utc=True),
                "base_asset": item.get("baseAsset"),
                "current_contract_type": contract_type,
                "current_underlying_type": underlying_type,
                "is_current_crypto_perpetual": (
                    contract_type == "PERPETUAL" and underlying_type == "COIN"
                ),
            }
        )
    return pd.DataFrame(rows).sort_values("symbol").reset_index(drop=True)


def month_gap_count(months: tuple[str, ...]) -> int:
    if not months:
        return 0
    expected = pd.period_range(months[0], months[-1], freq="M").astype(str)
    return int(len(set(expected) - set(months)))


def main() -> None:
    args = parse_args()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    exchange_info = current_exchange_info(timeout=args.timeout)

    archive_symbols = sorted(
        symbol_from_prefix(prefix)
        for prefix in list_common_prefixes(SYMBOL_PREFIX_ROOT, timeout=args.timeout)
        if is_usdt_perpetual_style(symbol_from_prefix(prefix))
    )
    print(f"archive_symbol_directories={len(archive_symbols)}")

    items: dict[str, InventoryItem] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(inventory_symbol, symbol, timeout=args.timeout): symbol
            for symbol in archive_symbols
        }
        completed = 0
        for future in as_completed(futures):
            symbol = futures[future]
            items[symbol] = future.result()
            completed += 1
            if completed % 200 == 0 or completed == len(futures):
                print(f"inventory {completed}/{len(futures)}")

    current_map = exchange_info.set_index("symbol").to_dict("index")
    all_symbols = sorted(set(archive_symbols) | set(exchange_info["symbol"]))
    rows: list[dict[str, Any]] = []
    for symbol in all_symbols:
        current = current_map.get(symbol, {})
        item = items.get(symbol)
        months = item.months if item else ()
        rows.append(
            {
                "symbol": symbol,
                "in_current_exchange_info": symbol in current_map,
                "current_status": current.get("current_status"),
                "onboard_ts": current.get("onboard_ts"),
                "base_asset": current.get("base_asset"),
                "current_contract_type": current.get("current_contract_type"),
                "current_underlying_type": current.get("current_underlying_type"),
                "is_current_crypto_perpetual": current.get("is_current_crypto_perpetual"),
                "kline_15m_months": len(months),
                "kline_15m_month_list": ";".join(months),
                "kline_15m_first_month": months[0] if months else None,
                "kline_15m_last_month": months[-1] if months else None,
                "kline_15m_internal_month_gaps": month_gap_count(months),
                "kline_15m_archive_bytes": item.archive_bytes if item else 0,
            }
        )
    inventory = pd.DataFrame(rows).sort_values("symbol").reset_index(drop=True)

    csv_path = ARTIFACT_DIR / "binance_usdm_15m_inventory_2026-07-23.csv"
    json_path = ARTIFACT_DIR / "binance_usdm_15m_inventory_2026-07-23.json"
    inventory.to_csv(csv_path, index=False)
    summary = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "archive": "Binance Vision official S3 listing",
        "current_metadata": "Binance USD-M /fapi/v1/exchangeInfo",
        "research_months": {"start": START_MONTH, "end": END_MONTH},
        "dataset": DATASET,
        "archive_symbol_directories": len(archive_symbols),
        "unique_usdt_perpetual_style_symbols": len(all_symbols),
        "symbols_with_kline_15m": int(inventory["kline_15m_months"].gt(0).sum()),
        "historical_not_current": int((~inventory["in_current_exchange_info"]).sum()),
        "total_archive_months": int(inventory["kline_15m_months"].sum()),
        "total_archive_gib": round(
            float(inventory["kline_15m_archive_bytes"].sum()) / 1024**3, 3
        ),
        "symbols_with_internal_month_gaps": int(
            inventory["kline_15m_internal_month_gaps"].gt(0).sum()
        ),
        "inventory_csv": str(csv_path.relative_to(ROOT)),
    }
    json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
