from __future__ import annotations

import importlib.util
import math
from pathlib import Path
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
    "hype_1d_ma7_wide_trend_lifecycle_engine",
    "hype_1d_ma7_wide_trend_lifecycle_engine.py",
)
ADAPTER = load_module(
    "hype_1d_ma7_wtl_adapter",
    "hype_1d_ma7_v4_fair_adapter.py",
)


@pytest.fixture(scope="module")
def context():
    return ADAPTER.load_context()


def test_stage_a_grid_is_exactly_frozen_555() -> None:
    entries = ENGINE.entry_specs()
    trails = ENGINE.trail_specs()
    rsis = ENGINE.rsi_specs()
    configs = ENGINE.stage_a_configs()
    assert len(entries) == 195
    assert len(trails) == 168
    assert len(rsis) == 24
    assert len(configs) == 555
    assert len({row.arm_id for row in configs}) == 555
    assert sum(row.entry.enabled for row in configs) == 195
    assert sum(row.long_exit.enabled for row in configs) == 168
    assert sum(row.short_exit.enabled for row in configs) == 168
    assert sum(row.short_rsi.enabled for row in configs) == 24


def test_maximum_combo_grid_is_624_and_deterministic() -> None:
    rows = ENGINE.build_combo_configs(
        ENGINE.entry_specs()[:4],
        ENGINE.trail_specs()[:4],
        ENGINE.trail_specs()[4:8],
        ENGINE.rsi_specs()[:4],
    )
    assert len(rows) == 624
    assert len({row.arm_id for row in rows}) == 624
    assert [row.arm_id for row in rows] == sorted(row.arm_id for row in rows)


def test_entry_metrics_are_directional_and_strict() -> None:
    close = np.arange(1.0, 12.0)
    assert ENGINE.signed_efficiency(close, 7, 1, 7) == pytest.approx(1.0)
    assert ENGINE.signed_efficiency(close, 7, -1, 7) == pytest.approx(-1.0)
    assert ENGINE.directional_persistence(close, 7, 1, 7) == 1.0
    assert ENGINE.directional_persistence(close, 7, -1, 7) == 0.0
    assert math.isnan(ENGINE.signed_efficiency(close, 2, 1, 3))
    broken = close.copy()
    broken[3] = np.nan
    assert math.isnan(ENGINE.directional_persistence(broken, 7, 1, 7))


def test_entry_scope_and_all_four_filter_boundaries() -> None:
    class Exact:
        @staticmethod
        def close_entry_signal(config, book, features, index):
            return index == 3

    class Box:
        pass

    book = Box()
    book.close = np.array([1.0, 2.0, 3.0, 4.0])
    features = Box()
    features.atr7 = np.ones(4)
    features.ma7 = np.array([1.0, 1.5, 2.0, 3.0])
    config = Box()
    config.side = 1
    er = ENGINE.EntryQualitySignal(Exact(), ENGINE.EntryFilter("er", "both", 3, 0.40))
    assert er(config, book, features, 3)
    chase = ENGINE.EntryQualitySignal(Exact(), ENGINE.EntryFilter("chase", "both", 0, 1.0))
    assert not chase(config, book, features, 3)
    assert chase.events[-1]["event"] == "entry_filter_reject"
    chase = ENGINE.EntryQualitySignal(Exact(), ENGINE.EntryFilter("chase", "short", 0, 0.25))
    assert chase(config, book, features, 3)
    assert not chase.events
    slope = ENGINE.EntryQualitySignal(Exact(), ENGINE.EntryFilter("slope", "both", 1, 0.10))
    assert slope(config, book, features, 3)
    persistence = ENGINE.EntryQualitySignal(
        Exact(), ENGINE.EntryFilter("persistence", "both", 3, 0.80)
    )
    assert persistence(config, book, features, 3)


def test_atr_trail_activation_confirmation_and_profit_guard() -> None:
    spec = ENGINE.TrailExit("atr", 1.0, 0.5, 2)
    kwargs = {
        "side": 1,
        "short_run": 9,
        "rsi_run": 9,
        "long_exit": spec,
        "short_exit": ENGINE.TrailExit(),
        "short_rsi": ENGINE.ShortRSIExit(),
        "highest_close": 104.0,
        "lowest_close": 100.0,
        "entry_price": 100.0,
        "atr": 2.0,
        "rsi6": 50.0,
    }
    reason, long_run, short_run, rsi_run = ENGINE.lifecycle_exit_decision(
        **kwargs,
        long_run=0,
        signal_close=103.0,
    )
    assert reason is None and long_run == 1 and short_run == 0 and rsi_run == 0
    reason, long_run, _, _ = ENGINE.lifecycle_exit_decision(
        **kwargs,
        long_run=long_run,
        signal_close=103.0,
    )
    assert reason == "long_mfe_atr_trail_exit" and long_run == 2
    reason, long_run, _, _ = ENGINE.lifecycle_exit_decision(
        **{**kwargs, "highest_close": 100.5},
        long_run=1,
        signal_close=100.4,
    )
    assert reason is None and long_run == 0


def test_fraction_trail_is_symmetric_and_equality_triggers() -> None:
    short = ENGINE.TrailExit("fraction", 1.0, 0.50, 1)
    reason, long_run, short_run, rsi_run = ENGINE.lifecycle_exit_decision(
        side=-1,
        long_run=4,
        short_run=0,
        rsi_run=0,
        long_exit=ENGINE.TrailExit(),
        short_exit=short,
        short_rsi=ENGINE.ShortRSIExit(),
        highest_close=100.0,
        lowest_close=90.0,
        signal_close=95.0,
        entry_price=100.0,
        atr=5.0,
        rsi6=50.0,
    )
    assert reason == "short_mfe_fraction_trail_exit"
    assert (long_run, short_run, rsi_run) == (0, 1, 0)


def test_short_rsi_has_priority_strict_threshold_and_profit_guard() -> None:
    reason, _, short_run, rsi_run = ENGINE.lifecycle_exit_decision(
        side=-1,
        long_run=0,
        short_run=0,
        rsi_run=1,
        long_exit=ENGINE.TrailExit(),
        short_exit=ENGINE.TrailExit("atr", 1.0, 0.5, 1),
        short_rsi=ENGINE.ShortRSIExit(25.0, 2),
        highest_close=100.0,
        lowest_close=90.0,
        signal_close=95.0,
        entry_price=100.0,
        atr=5.0,
        rsi6=24.999,
    )
    assert reason == "short_rsi_take_profit"
    assert short_run == 1 and rsi_run == 2
    equality = ENGINE.lifecycle_exit_decision(
        side=-1,
        long_run=0,
        short_run=0,
        rsi_run=1,
        long_exit=ENGINE.TrailExit(),
        short_exit=ENGINE.TrailExit(),
        short_rsi=ENGINE.ShortRSIExit(25.0, 2),
        highest_close=100.0,
        lowest_close=90.0,
        signal_close=95.0,
        entry_price=100.0,
        atr=5.0,
        rsi6=25.0,
    )
    assert equality[0] is None and equality[3] == 0


def test_wilder_rsi_known_boundaries() -> None:
    up = ENGINE.wilder_rsi6(np.arange(8.0))
    down = ENGINE.wilder_rsi6(np.arange(8.0, 0.0, -1.0))
    flat = ENGINE.wilder_rsi6(np.ones(8))
    assert np.isnan(up[:6]).all() and np.all(up[6:] == 100.0)
    assert np.isnan(down[:6]).all() and np.all(down[6:] == 0.0)
    assert np.isnan(flat[:6]).all() and np.all(flat[6:] == 50.0)


def test_oat_keep_only_and_neighbors_change_only_allowed_slots() -> None:
    config = ENGINE.WTLConfig(
        "C_TEST",
        entry=ENGINE.EntryFilter("er", "both", 7, 0.20),
        long_exit=ENGINE.TrailExit("atr", 1.0, 0.75, 1),
        short_rsi=ENGINE.ShortRSIExit(25.0, 2),
    )
    assert not ENGINE.disable_module(config, "entry").entry.enabled
    assert ENGINE.disable_module(config, "entry").long_exit == config.long_exit
    only = ENGINE.keep_only_module(config, "long_exit")
    assert only.enabled_modules() == ["long_exit"]
    neighbors = ENGINE.adjacent_neighbors(config)
    assert neighbors
    assert all(row.arm_id != config.arm_id for row in neighbors)
    assert any(row.entry.lookback == 5 for row in neighbors)
    assert any(row.long_exit.giveback == 0.50 for row in neighbors)


@pytest.mark.local_data
def test_all_off_compiles_and_is_exact_v4_on_exposed_d(context) -> None:
    config = ENGINE.WTLConfig("ALL_OFF")
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
        {key: value for key, value in row.items() if not key.startswith("wtl_")}
        for row in candidate.path
    ] == exact.path


@pytest.mark.local_data
def test_leverage_grid_and_three_x_cap(context) -> None:
    specs = ENGINE.leverage_specs()
    assert len(specs) == 9
    fixed = ENGINE.LeveragePolicy(context, specs[4])
    fixed.set_entry_context(1, 100.0, 20)
    assert fixed.last_entry_leverage == 3.0
    dynamic = ENGINE.LeveragePolicy(
        context, ENGINE.LeverageSpec("TEST", "atr_risk", 0.20)
    )
    dynamic.set_entry_context(1, 10_000.0, 20)
    assert dynamic.last_entry_leverage == 3.0
