from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pytest


SCRIPT_DIR = (
    Path(__file__).resolve().parents[1]
    / "research/hype/1d-ma7-asymmetric-body-trend/scripts"
)
PFT_PATH = SCRIPT_DIR / "hype_1d_ma7_v4_pft_engine.py"
ADAPTER_PATH = SCRIPT_DIR / "hype_1d_ma7_v4_fair_adapter.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PFT = load_module("hype_1d_ma7_v4_pft_engine", PFT_PATH)
ADAPTER = load_module("hype_1d_ma7_v4_pft_adapter", ADAPTER_PATH)


@pytest.fixture(scope="module")
def context():
    return ADAPTER.load_context()


def test_frozen_arm_matrix_is_exact_and_rejects_identity_drift() -> None:
    configs = PFT.arm_configs()
    assert [config.arm_id for config in configs] == list(PFT.ARM_ORDER)
    assert [
        (
            config.pending_enabled,
            config.forced_slope_enabled,
            config.rsi_take_profit_enabled,
        )
        for config in configs
    ] == [
        (False, False, False),
        (False, False, True),
        (False, True, False),
        (False, True, True),
        (True, False, False),
        (True, False, True),
        (True, True, False),
        (True, True, True),
    ]
    assert len({PFT.config_sha256(config) for config in configs}) == 8
    with pytest.raises(ValueError, match="flags do not match"):
        PFT.PFTConfig("A000_V4", True, False, False)
    with pytest.raises(ValueError, match="unknown PFT arm"):
        PFT.arm_config("A999")


def test_wilder_rsi6_known_boundaries_and_nonfinite_fail_closed() -> None:
    up = PFT.wilder_rsi6(np.arange(8.0))
    down = PFT.wilder_rsi6(np.arange(8.0, 0.0, -1.0))
    flat = PFT.wilder_rsi6(np.ones(8))
    assert np.isnan(up[:6]).all() and np.all(up[6:] == 100.0)
    assert np.isnan(down[:6]).all() and np.all(down[6:] == 0.0)
    assert np.isnan(flat[:6]).all() and np.all(flat[6:] == 50.0)
    assert np.isnan(PFT.wilder_rsi6([1, 2, np.nan, 4, 5, 6, 7])).all()
    with pytest.raises(ValueError, match="one-dimensional"):
        PFT.wilder_rsi6([[1.0, 2.0]])


def test_forced_reversal_filter_has_strict_ma_and_inclusive_slope() -> None:
    values = {
        "ma7": 100.0,
        "prior_ma7": 100.2,
        "atr7": 10.0,
        "slope_min_atr": 0.02,
    }
    assert PFT.forced_reversal_eligible(open_price=99.99, **values)
    assert not PFT.forced_reversal_eligible(open_price=100.0, **values)
    assert not PFT.forced_reversal_eligible(
        open_price=99.99,
        **{**values, "prior_ma7": 100.199999},
    )
    assert not PFT.forced_reversal_eligible(
        open_price=99.99,
        **{**values, "ma7": float("nan")},
    )


def test_rsi_tracker_starts_at_fill_and_uses_strict_profit_guard() -> None:
    tracker = PFT.RSITracker()
    assert tracker.observe_close(20.0, 90.0) == (False, False)
    tracker.on_fill(-1, 100.0)
    assert tracker.observe_close(25.0, 90.0) == (False, True)
    assert tracker.streak == 0
    assert tracker.observe_close(24.0, 99.72) == (False, False)
    assert tracker.observe_close(24.0, 99.72) == (False, False)
    assert tracker.streak == 2
    assert tracker.observe_close(24.0, 99.719) == (True, True)
    tracker.on_flat()
    assert tracker.observe_close(10.0, 80.0) == (False, False)


@dataclass
class FakeEngine:
    confirmed: dict[int, bool]
    trend: dict[int, bool]

    @staticmethod
    def close_entry_signal(config, book, features, index):
        return bool(index == 99)

    def _confirmed_side(self, config, book, features, index):
        return self.confirmed.get(index, False)

    def _trend_ok(self, config, book, features, index):
        return self.trend.get(index, False)


def pending_fixture(*, close, confirmed, trend):
    engine = FakeEngine(confirmed=confirmed, trend=trend)
    config = SimpleNamespace(
        side=-1,
        entry_mode="reclaim",
        pullback_touch_atr=0.25,
    )
    book = SimpleNamespace(close=np.asarray(close, dtype=float))
    features = SimpleNamespace(
        ma7=np.full(len(close), 100.0),
        atr7=np.full(len(close), 10.0),
    )
    signal = PFT.QualityShortPendingSignal(engine, enabled=True)
    return signal, config, book, features


def test_pending_short_preserves_same_day_v4_and_confirms_once_next_day() -> None:
    signal, config, book, features = pending_fixture(
        close=[101.0, 96.0, 95.0],
        confirmed={1: True, 2: True},
        trend={1: False, 2: True},
    )
    assert not signal(config, book, features, 1)
    assert signal.armed_at == 1
    assert signal(config, book, features, 2)
    assert signal.entry_was_delayed(-1, 2)
    assert signal.armed_at is None

    same_day, config, book, features = pending_fixture(
        close=[101.0, 96.0],
        confirmed={1: True},
        trend={1: True},
    )
    assert same_day(config, book, features, 1)
    assert not same_day.entry_was_delayed(-1, 1)


def test_pending_short_expires_invalidates_and_rejects_overextension() -> None:
    expire, config, book, features = pending_fixture(
        close=[101.0, 96.0, 96.0, 96.0],
        confirmed={1: True},
        trend={1: False, 2: False, 3: True},
    )
    assert not expire(config, book, features, 1)
    assert not expire(config, book, features, 2)
    assert not expire(config, book, features, 3)
    assert any(event["event"] == "expire_pending" for event in expire.events)

    invalid, config, book, features = pending_fixture(
        close=[101.0, 96.0, 101.0],
        confirmed={1: True},
        trend={1: False, 2: True},
    )
    assert not invalid(config, book, features, 1)
    assert not invalid(config, book, features, 2)
    assert any(
        event["event"] == "invalidate_across_ma7" for event in invalid.events
    )

    chase, config, book, features = pending_fixture(
        close=[101.0, 96.0, 92.0],
        confirmed={1: True, 2: True},
        trend={1: False, 2: True},
    )
    assert not chase(config, book, features, 1)
    assert not chase(config, book, features, 2)
    assert any(
        event["event"] == "reject_overextended_pending" for event in chase.events
    )


def test_disabled_or_long_pending_delegates_to_exact_v4_signal() -> None:
    engine = FakeEngine({}, {})
    signal = PFT.QualityShortPendingSignal(engine, enabled=False)
    config = SimpleNamespace(side=-1)
    assert signal(config, None, None, 99)
    signal = PFT.QualityShortPendingSignal(engine, enabled=True)
    config = SimpleNamespace(side=1)
    assert signal(config, None, None, 99)


def test_other_position_entry_cancels_an_armed_short() -> None:
    signal, config, book, features = pending_fixture(
        close=[101.0, 96.0],
        confirmed={1: True},
        trend={1: False},
    )
    assert not signal(config, book, features, 1)
    assert signal.armed_at == 1
    signal.on_position_entered(1, 2)
    assert signal.armed_at is None
    assert signal.events[-1]["event"] == "cancel_pending_other_entry"


@pytest.mark.local_data
def test_all_eight_sources_compile_without_running_candidate_history(context) -> None:
    rsi6 = PFT.wilder_rsi6(context.book.close)
    names = []
    hashes = []
    for config in PFT.arm_configs():
        pending = PFT.QualityShortPendingSignal(
            context.engine,
            enabled=config.pending_enabled,
        )
        function, source_hash = PFT.build_variant_function(
            context,
            config,
            pending_signal=pending,
            rsi6=rsi6,
        )
        names.append(function.__name__)
        hashes.append(source_hash)
    assert len(set(names)) == 8
    assert len(set(hashes)) == 8


@pytest.mark.local_data
def test_a000_is_economically_identical_to_exact_v4_on_development(context) -> None:
    exact = ADAPTER.run_v4(0, 259, retain=True)
    candidate = PFT.run_variant(
        context,
        PFT.arm_config("A000_V4"),
        start_index=0,
        terminal_index=259,
        retain=True,
    ).raw
    assert candidate.metrics == exact.metrics
    assert candidate.trades == exact.trades
    cleaned_path = [
        {key: value for key, value in row.items() if not key.startswith("pft_")}
        for row in candidate.path
    ]
    assert cleaned_path == exact.path
