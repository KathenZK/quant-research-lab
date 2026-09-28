from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/btc/15m-trend-continuation"
SOURCE_PATH = (
    ROOT
    / "research/btc/15m-ema-trend-breakout/scripts"
    / "refresh_and_audit_btc_15m_data.py"
)
SOURCE_SHA256 = "507ec927d1cd947ebf30efd0c200cea92ceb1b00b035449a29c47d644190e3eb"
START = pd.Timestamp("2020-01-01T00:00:00Z")
REPORT_PATH = FAMILY_DIR / "artifacts/btc_binance_15m_long_data_quality_latest.json"


def load_source() -> object:
    actual = hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest()
    if actual != SOURCE_SHA256:
        raise RuntimeError(
            "BTC 15m refresh source SHA mismatch: "
            f"expected {SOURCE_SHA256}, got {actual}"
        )
    module_name = "btc_15m_long_data_refresh_source"
    spec = importlib.util.spec_from_file_location(module_name, SOURCE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load refresh source: {SOURCE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    source = load_source()
    source.START = START
    source.FAMILY_DIR = FAMILY_DIR
    source.ARTIFACT_DIR = FAMILY_DIR / "artifacts"
    source.REPORT_PATH = REPORT_PATH
    source.USER_AGENT = "quant-research-lab-btc-15m-trend-continuation-data/0.1"
    source.main()


if __name__ == "__main__":
    main()
