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
FAMILY_DIR = ROOT / "research/asset-portfolios/multi-timeframe-pullback-trend-campaign"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
ENGINE_PATH = ROOT / "research/hype/15m-ema-trend-breakout/scripts/fetch_hype_binance_15m.py"
RAW_ROOT = ROOT / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
NORMALIZED_ROOT = ROOT / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
FUNDING_ROOT = ROOT / "data/normalized/funding_rates/exchange=binance/market_type=perp"
ASSETS = {
    "BTC": ("BTCUSDT", "BTC/USDT:USDT", "symbol=btc_usdt_usdt.parquet"),
    "ETH": ("ETHUSDT", "ETH/USDT:USDT", "symbol=eth_usdt_usdt.parquet"),
    "HYPE": ("HYPEUSDT", "HYPE/USDT:USDT", "symbol=hype_usdt_usdt.parquet"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh Binance closed 15m OHLCV/funding.")
    parser.add_argument("--assets", nargs="+", choices=tuple(ASSETS), default=list(ASSETS))
    parser.add_argument("--timeout", type=float, default=45.0)
    return parser.parse_args()


def load_engine(asset: str) -> Any:
    symbol, display, file_name = ASSETS[asset]
    name = f"binance_mtf_ptc_{asset.lower()}_fetch_engine"
    spec = importlib.util.spec_from_file_location(name, ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load fetch engine: {ENGINE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.SYMBOL = symbol
    module.DISPLAY_SYMBOL = display
    module.USER_AGENT = f"quant-research-lab-bin-mtf-ptc-{asset.lower()}-15m/0.1"
    module.RAW_ROOT = RAW_ROOT
    module.NORMALIZED_ROOT = NORMALIZED_ROOT
    module.FUNDING_ROOT = FUNDING_ROOT
    module.FILE_NAME = file_name
    return module


def refresh(asset: str, timeout: float) -> dict[str, Any]:
    engine = load_engine(asset)
    symbol, display, _ = ASSETS[asset]
    server_ms = engine.server_time_ms(timeout)
    raw = engine.fetch_klines(timeout=timeout, cutoff_ms=server_ms)
    raw["base_asset"] = asset
    normalized = engine.normalize_klines(raw)
    normalized["base_asset"] = asset
    quality = engine.audit_data(raw, normalized, cutoff_ms=server_ms)
    first_ms = int(normalized["ts"].iloc[0].timestamp() * 1000)
    funding = engine.fetch_funding(timeout=timeout, start_ms=first_ms, cutoff_ms=server_ms)
    funding["base_asset"] = asset
    if funding.empty or funding["funding_rate"].isna().any():
        raise RuntimeError(f"{asset} funding history is empty or contains null rates")
    contract = engine.fetch_contract_snapshot(timeout=timeout)
    partitions = engine.write_daily_partitions(raw, normalized)
    funding_summary = engine.write_funding(funding)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "binance_server_time": pd.to_datetime(server_ms, unit="ms", utc=True).isoformat(),
        "asset": asset,
        "symbol": symbol,
        "display_symbol": display,
        "timeframe": "15m",
        "quality": quality,
        "partitions": partitions,
        "funding": funding_summary,
        "contract_snapshot": contract,
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / f"{asset.lower()}_binance_15m_refresh_quality.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def main() -> None:
    args = parse_args()
    results = {asset: refresh(asset, args.timeout) for asset in args.assets}
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
