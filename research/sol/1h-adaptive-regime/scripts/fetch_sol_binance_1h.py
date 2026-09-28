from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/sol/1h-adaptive-regime"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
ENGINE_PATH = ROOT / "research/hype/1h-adaptive-regime/scripts/fetch_hype_binance_1h.py"
ENGINE_SHA256 = "a02f9bb03e86ea8f6d8a231f4e92d322dd9372be76e101484531fc45e96a7a99"
RAW_ROOT = ROOT / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=1h"
NORMALIZED_ROOT = (
    ROOT / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h"
)
FUNDING_ROOT = (
    ROOT
    / "data/normalized/funding/exchange=binance/market_type=perp"
    / "symbol=sol_usdt_usdt"
)

SYMBOL = "SOLUSDT"
DISPLAY_SYMBOL = "SOL/USDT:USDT"
FILE_NAME = "symbol=sol_usdt_usdt.parquet"
INTERVAL_MS = 60 * 60 * 1000
USER_AGENT = "quant-research-lab-sol-1h/0.1"


def load_engine() -> Any:
    actual_hash = hashlib.sha256(ENGINE_PATH.read_bytes()).hexdigest()
    if actual_hash != ENGINE_SHA256:
        raise RuntimeError(
            f"Fetch engine drift: expected {ENGINE_SHA256}, got {actual_hash}"
        )
    spec = importlib.util.spec_from_file_location("sol_1h_fetch_engine", ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load fetch engine: {ENGINE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.SYMBOL = SYMBOL
    module.DISPLAY_SYMBOL = DISPLAY_SYMBOL
    module.USER_AGENT = USER_AGENT
    module.RAW_ROOT = RAW_ROOT
    module.NORMALIZED_ROOT = NORMALIZED_ROOT
    module.FUNDING_ROOT = FUNDING_ROOT
    module.FILE_NAME = FILE_NAME
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch and audit the latest two years of closed Binance SOLUSDT "
            "perpetual 1h bars."
        )
    )
    parser.add_argument("--timeout", type=float, default=45.0)
    return parser.parse_args()


def fetch_two_year_klines(
    engine: Any, *, timeout: float, cutoff_ms: int
) -> pd.DataFrame:
    cutoff = pd.to_datetime(cutoff_ms, unit="ms", utc=True).floor("h")
    start = cutoff - pd.DateOffset(years=2)
    cursor = int(start.timestamp() * 1000)
    end_ms = int(cutoff.timestamp() * 1000)
    rows: list[list[object]] = []
    while cursor < end_ms:
        payload = engine.request_json(
            engine.KLINES_PATH,
            params={
                "symbol": SYMBOL,
                "interval": engine.INTERVAL,
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
            raise RuntimeError("Binance kline pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1500:
            break
        time.sleep(0.05)
    if not rows:
        raise RuntimeError("Binance returned no SOLUSDT 1h klines")
    frame = pd.DataFrame(
        rows,
        columns=[
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
        ],
    )
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_volume",
        "taker_buy_quote_volume",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["source"] = "binance_futures_kline_api"
    frame["is_closed"] = engine.closed_bar_mask(frame["close_time"], cutoff_ms)
    frame = frame.loc[frame["open_time"] >= start].copy()
    return (
        frame.drop_duplicates("open_time", keep="last")
        .sort_values("open_time")
        .reset_index(drop=True)
    )


def normalize(engine: Any, raw: pd.DataFrame) -> pd.DataFrame:
    frame = engine.normalize_klines(raw)
    frame["base_asset"] = "SOL"
    frame["quote_asset"] = "USDT"
    frame["symbol"] = DISPLAY_SYMBOL
    return frame


def write_daily_partitions(
    raw: pd.DataFrame, normalized: pd.DataFrame
) -> dict[str, int]:
    raw_closed = raw.loc[raw["is_closed"]].copy()
    raw_closed["date"] = raw_closed["open_time"].dt.date
    normalized = normalized.copy()
    normalized["date"] = normalized["ts"].dt.date
    raw_count = 0
    normalized_count = 0
    for partition_date, group in raw_closed.groupby("date", sort=True):
        path = RAW_ROOT / f"date={partition_date}" / FILE_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        group.drop(columns="date").to_parquet(path, index=False)
        raw_count += 1
    for partition_date, group in normalized.groupby("date", sort=True):
        path = NORMALIZED_ROOT / f"date={partition_date}" / FILE_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        group.drop(columns="date").to_parquet(path, index=False)
        normalized_count += 1
    return {
        "raw_partitions": raw_count,
        "normalized_partitions": normalized_count,
    }


def main() -> None:
    args = parse_args()
    engine = load_engine()
    server_ms = engine.server_time_ms(args.timeout)
    raw = fetch_two_year_klines(engine, timeout=args.timeout, cutoff_ms=server_ms)
    normalized = normalize(engine, raw)
    quality = engine.audit_data(raw, normalized, cutoff_ms=server_ms)
    first_ms = int(normalized["ts"].iloc[0].timestamp() * 1000)
    funding = engine.fetch_funding(
        timeout=args.timeout,
        start_ms=first_ms,
        cutoff_ms=server_ms,
    )
    if funding.empty or funding["funding_rate"].isna().any():
        raise RuntimeError("Funding history is empty or contains null rates")
    contract = engine.fetch_contract_snapshot(timeout=args.timeout)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    partitions = write_daily_partitions(raw, normalized)
    funding_path = FUNDING_ROOT / "funding.parquet"
    funding_path.parent.mkdir(parents=True, exist_ok=True)
    funding.to_parquet(funding_path, index=False)
    research_frame_path = ARTIFACT_DIR / "sol_binance_1h_closed_klines_2y.parquet"
    normalized.to_parquet(research_frame_path, index=False)
    funding.to_csv(ARTIFACT_DIR / "sol_binance_funding_history_2y.csv", index=False)

    funding_gaps = funding["ts"].diff().dropna()
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "binance_server_time": pd.to_datetime(
            server_ms, unit="ms", utc=True
        ).isoformat(),
        "market": "Binance USD-M Futures",
        "symbol": SYMBOL,
        "display_symbol": DISPLAY_SYMBOL,
        "timeframe": "1h",
        "requested_window": "latest_two_years",
        "data_quality": quality,
        "partitions": partitions,
        "paths": {
            "raw_root": str(RAW_ROOT.relative_to(ROOT)),
            "normalized_root": str(NORMALIZED_ROOT.relative_to(ROOT)),
            "funding": str(funding_path.relative_to(ROOT)),
            "exact_research_frame": str(research_frame_path.relative_to(ROOT)),
        },
        "funding": {
            "rows": int(len(funding)),
            "first_ts": funding["ts"].iloc[0].isoformat(),
            "last_ts": funding["ts"].iloc[-1].isoformat(),
            "null_rates": int(funding["funding_rate"].isna().sum()),
            "max_gap_hours": float(funding_gaps.max().total_seconds() / 3600.0),
            "sum_rate": float(funding["funding_rate"].sum()),
        },
        "contract_snapshot": contract,
        "checksum": {
            "close_sum": float(np.round(normalized["close"].sum(), 8)),
            "volume_sum": float(np.round(normalized["volume"].sum(), 8)),
            "quote_volume_sum": float(np.round(normalized["quote_volume"].sum(), 8)),
            "trade_count_sum": int(normalized["trade_count"].sum()),
        },
    }
    output = ARTIFACT_DIR / "sol_binance_1h_data_quality_2y.json"
    output.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
