from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/sol/1h-volatility-compression-breakout"
SOURCE_FETCH = (
    ROOT
    / "research/sol/1h-adaptive-regime/scripts/fetch_sol_binance_1h.py"
)


def load_fetcher() -> Any:
    spec = importlib.util.spec_from_file_location("sol_1h_vcb_fetcher", SOURCE_FETCH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load fetcher: {SOURCE_FETCH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.ARTIFACT_DIR = FAMILY_DIR / "artifacts"
    module.USER_AGENT = "quant-research-lab-sol-1h-vcb/0.1"
    return module


if __name__ == "__main__":
    load_fetcher().main()
