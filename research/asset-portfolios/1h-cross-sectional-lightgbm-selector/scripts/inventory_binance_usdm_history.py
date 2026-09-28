from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

import duckdb
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1h-cross-sectional-lightgbm-selector"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
FAPI = "https://fapi.binance.com"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
UA = "quant-research-lab-bin-1h-cslgbm-inventory/0.1"
START_MONTH = "2020-01"
END_MONTH = "2026-06"

DATASETS = {
    "kline_1h": "data/futures/um/monthly/klines/{symbol}/1h/",
    "mark_1h": "data/futures/um/monthly/markPriceKlines/{symbol}/1h/",
    "funding": "data/futures/um/monthly/fundingRate/{symbol}/",
}
ROOT_PREFIXES = {
    "kline_1h": "data/futures/um/monthly/klines/",
    "mark_1h": "data/futures/um/monthly/markPriceKlines/",
    "funding": "data/futures/um/monthly/fundingRate/",
}
MONTH_PATTERN = re.compile(r"-(20\d{2}-\d{2})\.zip$")


@dataclass(frozen=True, slots=True)
class InventoryItem:
    symbol: str
    dataset: str
    months: tuple[str, ...]
    keys: tuple[str, ...]
    archive_bytes: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inventory Binance Vision USD-M historical USDT perpetual datasets."
    )
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument(
        "--datasets",
        nargs="+",
        choices=sorted(DATASETS),
        default=sorted(DATASETS),
    )
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
        except (URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(10.0, 0.5 * 2**attempt))
    raise RuntimeError(f"request failed after {attempts} attempts: {url}") from last_error


def get_json(url: str, *, timeout: float) -> Any:
    return json.loads(request_bytes(url, timeout=timeout))


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
    root = s3_query(
        {"list-type": "2", "delimiter": "/", "prefix": prefix, "max-keys": 1000},
        timeout=timeout,
    )
    prefixes: list[str] = []
    for element in root:
        if local_name(element) != "CommonPrefixes":
            continue
        value = child_text(element, "Prefix")
        if value:
            prefixes.append(value)
    truncated = child_text(root, "IsTruncated")
    if truncated == "true":
        raise RuntimeError(f"common-prefix listing unexpectedly truncated: {prefix}")
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


def archive_symbols(dataset: str, *, timeout: float) -> set[str]:
    return {
        symbol_from_prefix(prefix)
        for prefix in list_common_prefixes(ROOT_PREFIXES[dataset], timeout=timeout)
        if is_usdt_perpetual_style(symbol_from_prefix(prefix))
    }


def inventory_symbol(
    symbol: str,
    dataset: str,
    *,
    timeout: float,
) -> InventoryItem:
    prefix = DATASETS[dataset].format(symbol=symbol)
    objects = tuple(
        (key, size)
        for key, size in list_objects(prefix, timeout=timeout)
        if key.endswith(".zip") and not key.endswith(".CHECKSUM")
    )
    keys = tuple(key for key, _ in objects)
    months = tuple(
        sorted(
            {
                match.group(1)
                for key in keys
                if (match := MONTH_PATTERN.search(key))
                and START_MONTH <= match.group(1) <= END_MONTH
            }
        )
    )
    selected_months = set(months)
    archive_bytes = sum(
        size
        for key, size in objects
        if (match := MONTH_PATTERN.search(key)) and match.group(1) in selected_months
    )
    return InventoryItem(
        symbol=symbol,
        dataset=dataset,
        months=months,
        keys=keys,
        archive_bytes=archive_bytes,
    )


def current_exchange_info(*, timeout: float) -> pd.DataFrame:
    payload = get_json(f"{FAPI}/fapi/v1/exchangeInfo", timeout=timeout)
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
                "margin_asset": item.get("marginAsset"),
                "current_contract_type": contract_type,
                "current_underlying_type": underlying_type,
                "current_underlying_subtype": ";".join(
                    item.get("underlyingSubType") or []
                ),
                "is_current_crypto_perpetual": (
                    contract_type == "PERPETUAL" and underlying_type == "COIN"
                ),
            }
        )
    return pd.DataFrame(rows).sort_values("symbol").reset_index(drop=True)


def local_lake_summary() -> dict[str, Any]:
    glob = str(
        ROOT
        / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h/**/*.parquet"
    )
    if not list((ROOT / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h").glob("**/*.parquet")):
        return {"rows": 0, "symbols": 0}
    connection = duckdb.connect()
    frame = connection.execute(
        """
        SELECT symbol, count(*) AS rows, min(ts) AS start_ts, max(ts) AS end_ts
        FROM read_parquet(?, hive_partitioning = false, union_by_name = true)
        GROUP BY symbol ORDER BY symbol
        """,
        [glob],
    ).fetch_df()
    return {
        "rows": int(frame["rows"].sum()),
        "symbols": int(len(frame)),
        "by_symbol": frame.to_dict("records"),
    }


def month_gap_count(months: tuple[str, ...]) -> int:
    if not months:
        return 0
    expected = pd.period_range(months[0], months[-1], freq="M").astype(str)
    return int(len(set(expected) - set(months)))


def main() -> None:
    args = parse_args()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    exchange_info = current_exchange_info(timeout=args.timeout)

    symbols_by_dataset = {
        dataset: archive_symbols(dataset, timeout=args.timeout)
        for dataset in args.datasets
    }
    all_symbols = sorted(
        set(exchange_info["symbol"]).union(*symbols_by_dataset.values())
    )
    tasks = [
        (symbol, dataset)
        for dataset in args.datasets
        for symbol in sorted(symbols_by_dataset[dataset])
    ]
    print(
        f"datasets={args.datasets} unique_usdt_symbols={len(all_symbols)} "
        f"inventory_requests={len(tasks)}"
    )

    items: dict[tuple[str, str], InventoryItem] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                inventory_symbol,
                symbol,
                dataset,
                timeout=args.timeout,
            ): (symbol, dataset)
            for symbol, dataset in tasks
        }
        completed = 0
        for future in as_completed(futures):
            key = futures[future]
            items[key] = future.result()
            completed += 1
            if completed % 250 == 0 or completed == len(futures):
                print(f"inventory {completed}/{len(futures)}")

    current_map = exchange_info.set_index("symbol").to_dict("index")
    rows: list[dict[str, Any]] = []
    for symbol in all_symbols:
        current = current_map.get(symbol, {})
        row: dict[str, Any] = {
            "symbol": symbol,
            "in_current_exchange_info": symbol in current_map,
            "current_status": current.get("current_status"),
            "onboard_ts": current.get("onboard_ts"),
            "base_asset": current.get("base_asset"),
            "margin_asset": current.get("margin_asset"),
            "current_contract_type": current.get("current_contract_type"),
            "current_underlying_type": current.get("current_underlying_type"),
            "current_underlying_subtype": current.get("current_underlying_subtype"),
            "is_current_crypto_perpetual": current.get("is_current_crypto_perpetual"),
        }
        for dataset in sorted(DATASETS):
            item = items.get((symbol, dataset))
            months = item.months if item else ()
            row[f"{dataset}_months"] = len(months)
            row[f"{dataset}_month_list"] = ";".join(months)
            row[f"{dataset}_first_month"] = months[0] if months else None
            row[f"{dataset}_last_month"] = months[-1] if months else None
            row[f"{dataset}_internal_month_gaps"] = month_gap_count(months)
            row[f"{dataset}_archive_bytes"] = item.archive_bytes if item else 0
        rows.append(row)
    inventory = pd.DataFrame(rows).sort_values("symbol").reset_index(drop=True)

    csv_path = ARTIFACT_DIR / "binance_usdm_historical_inventory_2026-07-17.csv"
    json_path = ARTIFACT_DIR / "binance_usdm_historical_inventory_2026-07-17.json"
    inventory.to_csv(csv_path, index=False)
    summary = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "archive": "Binance Vision official S3 listing",
        "current_metadata": "Binance USD-M /fapi/v1/exchangeInfo",
        "research_months": {"start": START_MONTH, "end": END_MONTH},
        "datasets": args.datasets,
        "archive_symbol_directory_counts": {
            dataset: len(symbols) for dataset, symbols in symbols_by_dataset.items()
        },
        "unique_usdt_perpetual_style_symbols": len(all_symbols),
        "current_exchange_info_usdt_contracts": len(exchange_info),
        "current_crypto_perpetuals": int(
            exchange_info["is_current_crypto_perpetual"].sum()
        ),
        "current_status_counts": {
            str(key): int(value)
            for key, value in exchange_info["current_status"].value_counts().items()
        },
        "inventory_counts": {
            "with_kline_1h": int(inventory["kline_1h_months"].gt(0).sum()),
            "with_mark_1h": int(inventory["mark_1h_months"].gt(0).sum()),
            "with_funding": int(inventory["funding_months"].gt(0).sum()),
            "historical_not_current": int((~inventory["in_current_exchange_info"]).sum()),
        },
        "archive_totals": {
            dataset: {
                "months": int(inventory[f"{dataset}_months"].sum()),
                "bytes": int(inventory[f"{dataset}_archive_bytes"].sum()),
                "gib": round(
                    float(inventory[f"{dataset}_archive_bytes"].sum()) / 1024**3,
                    3,
                ),
                "symbols_with_internal_month_gaps": int(
                    inventory[f"{dataset}_internal_month_gaps"].gt(0).sum()
                ),
            }
            for dataset in sorted(DATASETS)
        },
        "local_lake_before_backfill": local_lake_summary(),
        "inventory_csv": str(csv_path),
    }
    json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    print(f"inventory -> {csv_path}")
    print(f"summary -> {json_path}")


if __name__ == "__main__":
    main()
