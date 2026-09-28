from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/hype/15m-sequential-drift-state"
SOURCE = (
    ROOT
    / "research/hype/15m-ema-trend-breakout/scripts/fetch_hype_binance_15m.py"
)


def main() -> None:
    spec = importlib.util.spec_from_file_location("hype_15m_sds_data_refresh", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load data refresh implementation: {SOURCE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ARTIFACT_DIR = FAMILY_DIR / "artifacts"
    module.USER_AGENT = "quant-research-lab-hype-15m-sds-data/0.1"
    module.main()


if __name__ == "__main__":
    main()
