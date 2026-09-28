from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
import sys

import pandas as pd
import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "research/hype/1d-ma7-asymmetric-body-trend/scripts"
    / "hype_1d_ma7_v4_fair_adapter.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("hype_1d_ma7_v4_fair_adapter", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ADAPTER = load_module()


@pytest.fixture(scope="module")
def context():
    return ADAPTER.load_context()


@pytest.fixture(scope="module")
def full_baseline(context):
    assert context is ADAPTER.load_context()
    return ADAPTER.verify_full_baseline()


def test_public_api_and_defaults_do_not_drift() -> None:
    assert callable(ADAPTER.load_context)
    assert callable(ADAPTER.run_v4)
    assert callable(ADAPTER.verify_full_baseline)
    signature = inspect.signature(ADAPTER.run_v4)
    assert list(signature.parameters) == [
        "start_index",
        "terminal_index",
        "slippage",
        "signal_lag",
        "retain",
    ]
    assert signature.parameters["slippage"].default == pytest.approx(0.0004)
    assert signature.parameters["signal_lag"].default == 0
    assert signature.parameters["retain"].default is False


@pytest.mark.local_data
def test_context_is_cached_and_pinned(context) -> None:
    assert ADAPTER.load_context() is context
    cache = ADAPTER.load_context.cache_info()
    assert cache.currsize == 1
    assert cache.misses == 1
    assert context.backtest.__name__ == "v3_ma_only_backtest"
    assert context.confirmation.MA_ONLY == "MA_ONLY"
    assert dict(context.pins) == {
        "original_harness": ADAPTER.ORIGINAL_HARNESS_SHA256,
        "original_engine": ADAPTER.ORIGINAL_ENGINE_SHA256,
        "confirmation": ADAPTER.CONFIRMATION_SHA256,
        "formation": ADAPTER.FORMATION_SHA256,
        "search": ADAPTER.SEARCH_SHA256,
        "base": ADAPTER.BASE_SHA256,
        "selected_summary": ADAPTER.SELECTED_SUMMARY_SHA256,
        "hourly": ADAPTER.EXPECTED_HOURLY_SHA256,
        "funding": ADAPTER.EXPECTED_FUNDING_SHA256,
    }


@pytest.mark.local_data
def test_frozen_market_and_v4_configs_do_not_drift(context) -> None:
    assert context.book.count == 432
    assert pd.Timestamp(context.book.terminal_ts) == pd.Timestamp(
        "2026-08-06T00:00:00Z"
    )
    assert context.market.audit["hourly_sha256"] == ADAPTER.EXPECTED_HOURLY_SHA256
    assert context.market.audit["funding_sha256"] == ADAPTER.EXPECTED_FUNDING_SHA256
    assert context.long_config.side == 1
    assert context.long_config.entry_mode == "reclaim"
    assert context.long_config.exit_buffer_atr == pytest.approx(0.75)
    assert context.short_config.side == -1
    assert context.short_config.entry_mode == "reclaim"
    assert context.short_config.exit_buffer_atr == pytest.approx(0.75)


@pytest.mark.local_data
def test_run_v4_supports_a_bounded_window_without_full_verification(context) -> None:
    result = ADAPTER.run_v4(0, 30)
    assert result.metrics["start_ts"] == context.book.ts[0].isoformat()
    assert result.metrics["end_ts"] == context.book.ts[30].isoformat()
    assert result.metrics["days"] == pytest.approx(30.0)


@pytest.mark.local_data
def test_explicit_full_baseline_anchor(full_baseline) -> None:
    assert full_baseline.metrics["equity_multiple"] == pytest.approx(
        4.988406741729143,
        rel=1e-12,
        abs=1e-12,
    )
    assert full_baseline.metrics["closed_trades"] == 17
    assert full_baseline.metrics["max_drawdown_pct"] == pytest.approx(
        -26.813853621046835,
        rel=1e-12,
        abs=1e-12,
    )
    assert len(full_baseline.trades) == 17
    assert full_baseline.metrics["start_ts"] == "2025-05-31T00:00:00+00:00"
    assert full_baseline.metrics["end_ts"] == "2026-08-06T00:00:00+00:00"
