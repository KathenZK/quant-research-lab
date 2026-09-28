from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1h-price-impulse-campaign"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
ENGINE_PATH = (
    ROOT / "research/hype/15m-ema-trend-breakout/scripts/fetch_hype_binance_15m.py"
)
RAW_ROOT = ROOT / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
NORMALIZED_ROOT = (
    ROOT / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
)
FUNDING_ROOT = (
    ROOT
    / "data/normalized/funding_rates/exchange=binance/market_type=perp"
)
SYMBOL = "ETHUSDT"
DISPLAY_SYMBOL = "ETH/USDT:USDT"
FILE_NAME = "symbol=eth_usdt_usdt.parquet"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh and fail-closed audit Binance ETHUSDT perpetual 15m data."
    )
    parser.add_argument("--timeout", type=float, default=45.0)
    return parser.parse_args()


def load_engine() -> Any:
    spec = importlib.util.spec_from_file_location("binance_eth_15m_fetch_engine", ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load fetch engine: {ENGINE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.SYMBOL = SYMBOL
    module.DISPLAY_SYMBOL = DISPLAY_SYMBOL
    module.USER_AGENT = "quant-research-lab-bin-1h-pic-eth-15m/0.1"
    module.RAW_ROOT = RAW_ROOT
    module.NORMALIZED_ROOT = NORMALIZED_ROOT
    module.FUNDING_ROOT = FUNDING_ROOT
    module.FILE_NAME = FILE_NAME
    return module


def main() -> None:
    args = parse_args()
    engine = load_engine()
    server_ms = engine.server_time_ms(args.timeout)
    raw = engine.fetch_klines(timeout=args.timeout, cutoff_ms=server_ms)
    raw["base_asset"] = "ETH"
    normalized = engine.normalize_klines(raw)
    normalized["base_asset"] = "ETH"
    quality = engine.audit_data(raw, normalized, cutoff_ms=server_ms)
    first_ms = int(normalized["ts"].iloc[0].timestamp() * 1000)
    funding = engine.fetch_funding(
        timeout=args.timeout,
        start_ms=first_ms,
        cutoff_ms=server_ms,
    )
    funding["base_asset"] = "ETH"
    if funding.empty or funding["funding_rate"].isna().any():
        raise RuntimeError("ETH funding history is empty or contains null rates")
    contract = engine.fetch_contract_snapshot(timeout=args.timeout)
    partitions = engine.write_daily_partitions(raw, normalized)
    funding_summary = engine.write_funding(funding)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    normalized.to_parquet(
        ARTIFACT_DIR / "eth_binance_15m_closed_klines_refresh.parquet",
        index=False,
    )
    funding.to_csv(
        ARTIFACT_DIR / "eth_binance_15m_funding_refresh.csv",
        index=False,
    )
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "binance_server_time": pd.to_datetime(
            server_ms, unit="ms", utc=True
        ).isoformat(),
        "symbol": SYMBOL,
        "display_symbol": DISPLAY_SYMBOL,
        "timeframe": "15m",
        "quality": quality,
        "partitions": partitions,
        "funding": funding_summary,
        "contract_snapshot": contract,
    }
    (ARTIFACT_DIR / "eth_binance_15m_refresh_quality.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
