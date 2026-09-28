from __future__ import annotations

from dataclasses import asdict
import importlib.util
from pathlib import Path
import sys

import pandas as pd

import pytest



ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "research/asset-portfolios/1d-ma7-asset-specific-search/scripts/"
    "audit_binance_1d_ma7_shared_v1_long_history.py"
)


def load_script():
    spec = importlib.util.spec_from_file_location(
        "binance_ma7_shared_v1_long_history_tested", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v1_configs_match_registered_spec() -> None:
    module = load_script()
    transfer = module.load_module(
        module.TRANSFER_PATH,
        module.TRANSFER_SHA256,
        "binance_ma7_v1_test_transfer",
    )
    engine = transfer.load_engine()
    long_config, short_config = module.v1_configs(engine)
    assert asdict(long_config) == {
        "side": 1,
        "entry_mode": "reclaim",
        "slope_lookback": 5,
        "slope_min_atr": 0.0,
        "confirm_days": 1,
        "entry_buffer_atr": 0.25,
        "pullback_lookback": 10,
        "pullback_touch_atr": 0.1,
        "breakout_lookback": 7,
        "exit_confirm_days": 2,
        "exit_buffer_atr": 1.0,
        "slope_exit_lookback": 5,
        "hard_stop_atr": 0.0,
        "trail_atr": 0.0,
        "max_hold_days": 0,
        "cooldown_days": 0,
    }
    assert asdict(short_config) == {
        "side": -1,
        "entry_mode": "pullback_reclaim",
        "slope_lookback": 5,
        "slope_min_atr": 0.0,
        "confirm_days": 1,
        "entry_buffer_atr": 0.1,
        "pullback_lookback": 5,
        "pullback_touch_atr": -0.5,
        "breakout_lookback": 10,
        "exit_confirm_days": 2,
        "exit_buffer_atr": 0.75,
        "slope_exit_lookback": 0,
        "hard_stop_atr": 1.5,
        "trail_atr": 5.0,
        "max_hold_days": 10,
        "cooldown_days": 2,
    }


def test_frozen_boundaries_do_not_overlap() -> None:
    module = load_script()
    assert module.COMMON_START == pd.Timestamp("2019-12-24T00:00:00Z")
    assert module.DEVELOPMENT_END == pd.Timestamp("2025-08-07T00:00:00Z")
    assert module.EXPECTED_TERMINAL == pd.Timestamp("2026-08-10T00:00:00Z")
    assert module.COMMON_START < module.DEVELOPMENT_END < module.EXPECTED_TERMINAL


@pytest.mark.local_data
def test_frozen_p0_hashes_match_manifest() -> None:
    module = load_script()
    manifest = __import__("json").loads(
        module.P0_MANIFEST.read_text(encoding="utf-8")
    )
    for symbol, slug in module.ASSETS.items():
        _, _, quality = module.load_snapshot(symbol, slug, manifest)
        assert quality["blocker_count"] == 0
        assert quality["hashes"] == module.EXPECTED_FRAME_HASHES[symbol]

