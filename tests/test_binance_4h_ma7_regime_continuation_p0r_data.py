from __future__ import annotations

import hashlib
import importlib.util
import inspect
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import pytest

from strategy_lab.data.catalog import (
    BINANCE_PERP_1H_FROM_15M_V1,
    BINANCE_PERP_1H_NORMALIZED_LEGACY,
    BINANCE_PERP_4H_FROM_15M_V1,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    ROOT
    / "research/asset-portfolios/4h-ma7-regime-continuation/scripts"
    / "research_binance_4h_ma7_regime_continuation_p0r_data.py"
)
SPEC = importlib.util.spec_from_file_location("binance_4h_ma7_rc_p0r_data", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.local_data
def test_frozen_p0r_data_config_and_manifest_hashes_match() -> None:
    config = MODULE.validate_frozen_config()
    assert config["study_id"] == "BIN-4H-MA7-RC-P0R-DATA"
    assert sha256_file(MODULE.CONFIG_PATH) == MODULE.EXPECTED_CONFIG_SHA256
    assert (
        sha256_file(ROOT / config["data"]["dataset_manifest"])
        == MODULE.EXPECTED_MANIFEST_SHA256
    )
    assert config["data"]["native_4h_dataset_id"] == BINANCE_PERP_4H_FROM_15M_V1
    assert config["data"]["path_1h_dataset_id"] == BINANCE_PERP_1H_FROM_15M_V1
    assert "ohlcv_1h_globs" not in config["data"]


def test_p0r_data_outputs_do_not_collide_with_p0() -> None:
    MODULE.assert_no_p0_collision()
    p0_paths = {path.resolve() for path in MODULE.p0_protected_paths()}
    planned = {path.resolve() for path in [*MODULE.OUTPUTS.values(), MODULE.REPORT_PATH]}
    assert not (p0_paths & planned)


@pytest.mark.local_data
def test_p0_artifacts_remain_intact() -> None:
    MODULE.assert_p0_artifacts_intact()
    p0_summary = (
        ROOT
        / "research/asset-portfolios/4h-ma7-regime-continuation/artifacts"
        / "binance_4h_ma7_rc_p0_summary_2026-09-02.json"
    )
    sidecar = p0_summary.with_suffix(p0_summary.suffix + ".sha256")
    recorded = sidecar.read_text(encoding="utf-8").split()[0]
    assert sha256_file(p0_summary) == recorded


def test_legacy_1h_dataset_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="forbids"):
        MODULE.assert_allowed_dataset(
            BINANCE_PERP_1H_NORMALIZED_LEGACY,
            ROOT / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
        )
    with pytest.raises(RuntimeError, match="not under derived"):
        MODULE.assert_allowed_dataset(
            BINANCE_PERP_4H_FROM_15M_V1,
            ROOT / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
        )


def test_native_4h_panel_keeps_phase_zero_and_cutoff() -> None:
    ts = pd.date_range("2026-08-24T00:00:00Z", periods=4, freq="4h", tz="UTC")
    frame = pd.DataFrame(
        {
            "ts": ts,
            "symbol": ["BTC/USDT:USDT"] * 4,
            "timeframe": ["4h"] * 4,
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
        }
    )
    last = pd.Timestamp("2026-08-24T04:00:00Z")
    out = MODULE.prepare_native_4h(frame, last)
    assert out["phase_hour"].eq(0).all()
    assert out["ts"].max() == last
    assert len(out) == 2


def test_p0_statistical_blockers_are_reused_unfixed() -> None:
    source = inspect.getsource(MODULE.P0.side_verdicts)
    assert "between(2023, 2025)" in source
    horizon_source = inspect.getsource(MODULE.P0.build_horizon_stats)
    assert "**cluster" in horizon_source
    assert "四个" in MODULE.KNOWN_STATISTICAL_BLOCKERS[0] or "2023" in MODULE.KNOWN_STATISTICAL_BLOCKERS[0]


def test_fast_funding_schedule_matches_p0() -> None:
    original_times = MODULE.P0.expected_funding_times
    original_cost = MODULE.P0.funding_cost_for_window
    windows = [
        (pd.Timestamp("2024-01-01T00:00:00Z"), pd.Timestamp("2024-01-01T08:00:00Z")),
        (pd.Timestamp("2024-01-01T00:00:01Z"), pd.Timestamp("2024-01-01T16:00:00Z")),
        (pd.Timestamp("2024-01-01T07:59:59Z"), pd.Timestamp("2024-01-01T08:00:00Z")),
        (pd.Timestamp("2024-01-01T08:00:00Z"), pd.Timestamp("2024-01-02T00:00:00Z")),
    ]
    lookup = {
        "TEST/USDT:USDT": MODULE.P0.FundingLookup(
            timestamps=np.array([], dtype="datetime64[ns]"),
            rates=np.array([]),
            by_second={
                pd.Timestamp("2024-01-01T08:00:00Z"): 0.001,
                pd.Timestamp("2024-01-01T16:00:00Z"): 0.002,
                pd.Timestamp("2024-01-02T00:00:00Z"): 0.003,
            },
        )
    }
    try:
        MODULE.install_fast_funding(lookup)
        for entry, exit_ts in windows:
            assert original_times(entry, exit_ts) == MODULE.expected_funding_times_fast(entry, exit_ts)
            slow = original_cost(lookup, "TEST/USDT:USDT", entry, exit_ts, 1)
            fast = MODULE.fast_funding_cost_for_window(lookup, "TEST/USDT:USDT", entry, exit_ts, 1)
            if slow[1] is False:
                assert fast[1] is False
            else:
                assert fast[0] == pytest.approx(slow[0])
                assert fast[1:] == slow[1:]
    finally:
        MODULE.P0.expected_funding_times = original_times
        MODULE.P0.funding_cost_for_window = original_cost
