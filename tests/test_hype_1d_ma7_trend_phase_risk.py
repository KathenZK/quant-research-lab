from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pytest


SCRIPT_DIR = (
    Path(__file__).resolve().parents[1]
    / "research/hype/1d-ma7-asymmetric-body-trend/scripts"
)


def load_module(name: str, filename: str):
    path = SCRIPT_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ENGINE = load_module(
    "hype_1d_ma7_trend_phase_risk_engine",
    "hype_1d_ma7_trend_phase_risk_engine.py",
)
METRICS = load_module(
    "hype_1d_ma7_trend_phase_risk_metrics",
    "hype_1d_ma7_trend_phase_risk_metrics.py",
)
ADAPTER = load_module(
    "hype_1d_ma7_tpr_adapter",
    "hype_1d_ma7_v4_fair_adapter.py",
)


@pytest.fixture(scope="module")
def context():
    return ADAPTER.load_context()


def test_ranked_grid_is_exactly_four_by_three() -> None:
    configs = ENGINE.ranked_configs()
    assert len(configs) == 12
    assert len({config.arm_id for config in configs}) == 12
    assert {(config.q_threshold, config.e_days) for config in configs} == {
        (q, e) for q in ENGINE.Q_VALUES for e in ENGINE.E_VALUES
    }
    assert all(config.t_enabled for config in configs)


def test_signed_efficiency_direction_equality_and_nonfinite() -> None:
    close = np.arange(1.0, 10.0)
    assert ENGINE.signed_efficiency(close, 7, 1) == pytest.approx(1.0)
    assert ENGINE.signed_efficiency(close, 7, -1) == pytest.approx(-1.0)
    assert math.isnan(ENGINE.signed_efficiency(close, 6, 1))
    broken = close.copy()
    broken[4] = np.nan
    assert math.isnan(ENGINE.signed_efficiency(broken, 7, 1))
    flat = np.ones(8)
    assert math.isnan(ENGINE.signed_efficiency(flat, 7, 1))


def test_entry_quality_is_strict_and_delegates_exact_signal() -> None:
    class FakeEngine:
        @staticmethod
        def close_entry_signal(config, book, features, index):
            return bool(index == 7)

    config = SimpleNamespace(side=1)
    signal = ENGINE.EntryQualitySignal(FakeEngine(), np.arange(8.0), 1.0)
    assert not signal(config, None, None, 6)
    assert not signal(config, None, None, 7)
    assert signal.events[-1]["signed_er7"] == pytest.approx(1.0)
    assert signal.events[-1]["event"] == "q_reject"
    signal = ENGINE.EntryQualitySignal(FakeEngine(), np.arange(8.0), 0.40)
    assert signal(config, None, None, 7)


def test_wilder_rsi_boundaries() -> None:
    up = ENGINE.wilder_rsi6(np.arange(8.0))
    down = ENGINE.wilder_rsi6(np.arange(8.0, 0.0, -1.0))
    flat = ENGINE.wilder_rsi6(np.ones(8))
    assert np.isnan(up[:6]).all() and np.all(up[6:] == 100.0)
    assert np.isnan(down[:6]).all() and np.all(down[6:] == 0.0)
    assert np.isnan(flat[:6]).all() and np.all(flat[6:] == 50.0)


def test_long_decay_uses_inclusive_zero_slope_strict_profit_and_reset() -> None:
    kwargs = {
        "side": 1,
        "short_rsi_run": 7,
        "current_ma": 100.0,
        "prior_ma": 100.0,
        "current_atr": 2.0,
        "current_rsi": 50.0,
        "entry_price": 100.0,
        "e_days": 2,
        "t_enabled": True,
    }
    reason, decay, short_run = ENGINE.phase_exit_decision(
        **kwargs,
        long_decay_run=0,
        signal_close=100.0 * (1.0 + ENGINE.ROUNDTRIP_GUARD),
    )
    assert reason is None and decay == 1 and short_run == 0
    reason, decay, _ = ENGINE.phase_exit_decision(
        **kwargs,
        long_decay_run=decay,
        signal_close=100.0 * (1.0 + ENGINE.ROUNDTRIP_GUARD),
    )
    assert reason is None and decay == 2
    reason, decay, _ = ENGINE.phase_exit_decision(
        **kwargs,
        long_decay_run=1,
        signal_close=100.2800000001,
    )
    assert reason == "long_slope_decay_exit" and decay == 2
    reason, decay, _ = ENGINE.phase_exit_decision(
        **{**kwargs, "current_ma": 100.01},
        long_decay_run=9,
        signal_close=101.0,
    )
    assert reason is None and decay == 0


def test_short_rsi_uses_strict_threshold_profit_guard_and_side_reset() -> None:
    kwargs = {
        "side": -1,
        "long_decay_run": 4,
        "current_ma": 100.0,
        "prior_ma": 99.0,
        "current_atr": 2.0,
        "entry_price": 100.0,
        "e_days": 2,
        "t_enabled": True,
    }
    reason, long_run, rsi_run = ENGINE.phase_exit_decision(
        **kwargs,
        short_rsi_run=1,
        current_rsi=25.0,
        signal_close=90.0,
    )
    assert reason is None and long_run == 0 and rsi_run == 0
    reason, _, rsi_run = ENGINE.phase_exit_decision(
        **kwargs,
        short_rsi_run=1,
        current_rsi=24.999,
        signal_close=100.0 * (1.0 - ENGINE.ROUNDTRIP_GUARD),
    )
    assert reason is None and rsi_run == 2
    reason, _, rsi_run = ENGINE.phase_exit_decision(
        **kwargs,
        short_rsi_run=1,
        current_rsi=24.999,
        signal_close=99.7199999999,
    )
    assert reason == "short_rsi_take_profit" and rsi_run == 2
    assert ENGINE.phase_exit_decision(
        **{**kwargs, "side": 0},
        short_rsi_run=5,
        current_rsi=10.0,
        signal_close=90.0,
    ) == (None, 0, 0)


def test_oat_disables_only_requested_module() -> None:
    config = ENGINE.TPRConfig("Q30_E2_T25X2", 0.30, 2)
    assert ENGINE.oat_config(config, "Q").q_threshold is None
    assert ENGINE.oat_config(config, "Q").e_days == 2
    assert ENGINE.oat_config(config, "E").q_threshold == 0.30
    assert ENGINE.oat_config(config, "E").e_days == 0
    assert not ENGINE.oat_config(config, "T").t_enabled


@pytest.mark.local_data
def test_leverage_grid_and_dynamic_formula_are_capped(context) -> None:
    specs = ENGINE.leverage_specs()
    assert len(specs) == 9
    assert [spec.id for spec in specs[:5]] == [
        "FIXED_1.25X",
        "FIXED_1.50X",
        "FIXED_2.00X",
        "FIXED_2.50X",
        "FIXED_3.00X",
    ]
    fixed = ENGINE.LeveragePolicy(context, specs[4])
    fixed.set_entry_context(1, 100.0, 20)
    assert fixed.last_entry_leverage == 3.0
    dynamic = ENGINE.LeveragePolicy(
        context,
        ENGINE.LeverageSpec("TEST_R20", "atr_risk", 0.20),
    )
    dynamic.set_entry_context(1, 10_000.0, 20)
    assert dynamic.last_entry_leverage == 3.0


@pytest.mark.local_data
def test_target_quantity_matches_exact_one_x_kernel(context) -> None:
    expected = context.engine._target_quantity(1.0, 0.0, 1, 25.0, 0.0014)
    actual = METRICS.target_quantity(1.0, 0.0, 1, 25.0, 0.0014, 1.0)
    assert actual == pytest.approx(expected, rel=0.0, abs=1e-14)
    with pytest.raises(ValueError, match="within"):
        METRICS.target_quantity(1.0, 0.0, 1, 25.0, 0.0014, 3.01)


@pytest.mark.local_data
def test_all_sources_compile_without_candidate_performance(context) -> None:
    rsi6 = ENGINE.wilder_rsi6(context.book.close)
    hashes = []
    for config in ENGINE.ranked_configs():
        signal = ENGINE.EntryQualitySignal(
            context.engine, context.book.close, config.q_threshold
        )
        policy = ENGINE.LeveragePolicy(context, None)
        function, source_hash = ENGINE.build_variant_function(
            context,
            config,
            entry_signal=signal,
            leverage_policy=policy,
            rsi6=rsi6,
        )
        assert callable(function)
        hashes.append(source_hash)
    assert len(set(hashes)) == 12


@pytest.mark.local_data
def test_all_off_is_exact_v4_on_development(context) -> None:
    config = ENGINE.TPRConfig("ALL_OFF", None, 0, False)
    candidate = ENGINE.run_variant(
        context,
        config,
        start_index=0,
        terminal_index=259,
        retain=True,
    ).raw
    exact = ADAPTER.run_v4(0, 259, retain=True)
    assert candidate.metrics == exact.metrics
    assert [
        {key: value for key, value in trade.items() if key != "entry_leverage"}
        for trade in candidate.trades
    ] == exact.trades
    assert [
        {key: value for key, value in row.items() if not key.startswith("tpr_")}
        for row in candidate.path
    ] == exact.path


@pytest.mark.local_data
def test_exact_v4_chronological_replay_has_full_ledger_parity(context) -> None:
    exact = ADAPTER.run_v4(0, 259, retain=True)
    replay = METRICS.replay_chronological_1h(context, exact)
    assert all(replay.parity.values())
    assert replay.terminal_equity == pytest.approx(
        exact.metrics["equity_multiple"], rel=1e-12, abs=1e-12
    )
    assert replay.chronological_1h_mdd_pct == pytest.approx(
        -21.656074926092085, rel=1e-12, abs=1e-12
    )
    assert replay.worst_ts == "2025-09-01T23:00:00+00:00"


@pytest.mark.local_data
def test_funding_off_candidate_replay_has_full_ledger_parity(context) -> None:
    config = ENGINE.TPRConfig("ALL_OFF_NO_FUNDING", None, 0, False)
    candidate = ENGINE.run_variant(
        context,
        config,
        start_index=0,
        terminal_index=259,
        include_funding=False,
        retain=True,
    ).raw
    replay = METRICS.replay_chronological_1h(
        context,
        candidate,
        include_funding=False,
    )
    assert all(replay.parity.values())
    assert replay.funding_equity_units == 0.0


def test_pareto_and_mdd_cap_selection() -> None:
    rows = [
        {"id": "A", "net_return_pct": 100.0, "chronological_1h_mdd_pct": -20.0},
        {"id": "B", "net_return_pct": 120.0, "chronological_1h_mdd_pct": -25.0},
        {"id": "C", "net_return_pct": 90.0, "chronological_1h_mdd_pct": -30.0},
    ]
    assert [row["id"] for row in METRICS.pareto_frontier(rows)] == ["A", "B"]
    caps = METRICS.best_by_mdd_caps(rows, (20.0, 25.0, 50.0))
    assert caps["20"]["id"] == "A"
    assert caps["25"]["id"] == "B"
    assert caps["50"]["id"] == "B"
