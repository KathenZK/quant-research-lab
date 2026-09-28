"""Hand-auditable checks for the frozen R2 entry and tightening changes.

Precomputed daily features intentionally isolate execution from the R1 indicator
tests.  The entry tests derive the new velocity features from explicit MA paths.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest


ENGINE_PATH = Path(__file__).resolve().parents[1] / (
    "research/hype/1d-ma7-cross-atr-ratchet/scripts/engine_r2.py"
)
SPEC = importlib.util.spec_from_file_location("hype_car_r2_engine_tested", ENGINE_PATH)
assert SPEC is not None and SPEC.loader is not None
engine = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = engine
SPEC.loader.exec_module(engine)
DAY_ZERO = pd.Timestamp("2026-01-01", tz="UTC")


def days(count=12):
    return pd.DataFrame({
        "timestamp": pd.date_range(DAY_ZERO, periods=count, freq="D"),
        "close": 110.0, "ma": 100.0, "atr": 10.0, "rsi": 50.0,
        "slope": 0.0, "cross": 0, "ready": True,
        "accel1": False, "accel2": False,
    })


def hours(count=48, price=110.0, start_day=1):
    return pd.DataFrame({
        "timestamp": pd.date_range(DAY_ZERO + pd.Timedelta(days=start_day), periods=count, freq="h"),
        "open": price, "high": price + 0.1, "low": price - 0.1, "close": price,
    })


def config(**kwargs):
    return engine.Config(**{
        "fee": 0.0, "slip": 0.0, "short_exit": "none", "reverse": False,
        "entry_mode": "original", "tighten_mode": "stall_only",
        "profit_trigger_atr": 0.0, **kwargs,
    })


def holding_path(side=1, day_count=9):
    d = days(day_count + 3)
    d["close"] = 100.0 + side * 10.0
    d.loc[0, ["cross", "slope"]] = [side, side * 0.1]
    h = hours(24 * day_count, 100.0 + side * 10.0)
    h.loc[0, ["open", "high", "low"]] = [
        100.0, max(100.0, h.close.iloc[0]) + 0.1,
        min(100.0, h.close.iloc[0]) - 0.1,
    ]
    return d, h


def velocity_path(side, previous, current, atr=10.0):
    """previous/current are MA dollar changes expressed in the trade direction."""
    d = days(4)
    d["ma"] = [100.0, 100.0 + side * previous,
               100.0 + side * (previous + current), 100.0]
    d["atr"] = atr
    d["slope"] = d.ma.diff() / d.atr
    d["ready"] = [False, False, True, True]
    d["close"] = d.ma + side
    d.loc[2, "cross"] = side
    return engine.enrich_features(d)


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("current", [-0.2, 0.02])
def test_opposite_trend_slowdown_or_small_direction_flip_admits_cross(side, current):
    d = velocity_path(side, previous=-1.0, current=current)
    row = d.iloc[2]
    assert engine.entry_qualification(row, side, config(entry_mode="original")) is None
    assert engine.entry_qualification(row, side, config(entry_mode="opposite_slowdown")) == "opposite_slowdown"
    h = hours(2, row.close, start_day=3)
    _, trades, _, _, _ = engine.simulate(h, d, config(entry_mode="opposite_slowdown"))
    assert len(trades) == 1
    assert trades.iloc[0].qualification == "opposite_slowdown"
    assert trades.iloc[0].side == side
    assert trades.iloc[0].signal_day == d.timestamp.iloc[2]
    assert trades.iloc[0].entry_time == d.timestamp.iloc[2] + pd.Timedelta(days=1)


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("mode", ["opposite_slowdown", "absolute_slowdown"])
def test_atr_expansion_does_not_fake_ma_slowdown(side, mode):
    d = velocity_path(side, previous=-1.0, current=-1.0)
    d.loc[1, "atr"] = 1.0
    d.loc[2, "atr"] = 20.0
    d["slope"] = d.ma.diff() / d.atr
    d = engine.enrich_features(d)
    assert abs(d.slope.iloc[2]) < abs(d.slope.iloc[1])
    assert d.ma_step.iloc[2] == d.ma_step.iloc[1]
    assert engine.entry_qualification(d.iloc[2], side, config(entry_mode=mode)) is None


@pytest.mark.parametrize("side", [1, -1])
def test_absolute_variant_includes_same_direction_slowdown(side):
    d = velocity_path(side, previous=1.0, current=0.2)
    assert engine.entry_qualification(d.iloc[2], side, config(entry_mode="opposite_slowdown")) is None
    assert engine.entry_qualification(d.iloc[2], side, config(entry_mode="absolute_slowdown")) == "absolute_slowdown"


@pytest.mark.parametrize("mode", ["original", "opposite_slowdown", "absolute_slowdown", "no_slope"])
def test_original_qualification_has_recording_priority(mode):
    d = velocity_path(1, previous=-1.0, current=0.8)
    assert engine.entry_qualification(d.iloc[2], 1, config(entry_mode=mode)) == "original"


@pytest.mark.parametrize("mode", ["opposite_slowdown", "absolute_slowdown", "no_slope"])
def test_new_qualification_does_not_open_without_a_fresh_cross(mode):
    d = velocity_path(1, previous=-1.0, current=0.02)
    d.loc[2, "cross"] = 0
    assert engine.entry_qualification(d.iloc[2], 1, config(entry_mode=mode)) is not None
    result, trades, _, _, _ = engine.simulate(hours(2, d.close.iloc[2], start_day=3), d, config(entry_mode=mode))
    assert result["trades"] == 0
    assert trades.empty


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("mode", ["stall_only", "armed_daily"])
def test_five_daily_reductions_reach_half_atr_and_never_go_below(side, mode):
    d, h = holding_path(side)
    _, trades, _, stops, _ = engine.simulate(h, d, config(tighten_mode=mode))
    assert len(trades) == 1
    assert stops.new_mult.tolist() == pytest.approx([1.5, 1.3, 1.1, 0.9, 0.7, 0.5, 0.5, 0.5, 0.5])
    assert stops.new_stop.tolist() == pytest.approx([100.0 - side * 10.0 * m for m in stops.new_mult])
    assert int(stops.tightened.sum()) == 5
    assert int(trades.iloc[0].tightening_days) == 5
    assert bool(trades.iloc[0].stop_floor_reached)
    assert trades.iloc[0].initial_stop_mult == 1.5
    assert trades.iloc[0].entry_atr == 10.0
    assert (side * (stops.new_stop - stops.old_stop) >= 0).all()


@pytest.mark.parametrize("side", [1, -1])
def test_armed_daily_continues_when_natural_stop_resumes_progress(side):
    d, h = holding_path(side, 3)
    d.loc[2, "ma"] = 100.0 + side * 5.0
    _, _, _, stalled, _ = engine.simulate(h, d, config(tighten_mode="stall_only"))
    _, _, _, armed, _ = engine.simulate(h, d, config(tighten_mode="armed_daily"))
    assert stalled.new_mult.tolist() == pytest.approx([1.5, 1.3, 1.3])
    assert armed.new_mult.tolist() == pytest.approx([1.5, 1.3, 1.1])
    assert not bool(stalled.iloc[2].stalled)
    assert not bool(armed.iloc[2].stalled)
    assert stalled.new_stop.iloc[2] == pytest.approx(100.0 - side * 8.0)
    assert armed.new_stop.iloc[2] == pytest.approx(100.0 - side * 6.0)


@pytest.mark.parametrize("side", [1, -1])
def test_armed_daily_continues_after_profit_disappears_but_stall_only_waits(side):
    d, h = holding_path(side, 3)
    d.loc[2, "close"] = 100.0 - side
    _, _, _, stalled, _ = engine.simulate(h, d, config(tighten_mode="stall_only"))
    _, _, _, armed, _ = engine.simulate(h, d, config(tighten_mode="armed_daily"))
    assert not bool(stalled.iloc[2].profit_eligible)
    assert not bool(armed.iloc[2].profit_eligible)
    assert stalled.new_mult.tolist() == pytest.approx([1.5, 1.3, 1.3])
    assert armed.new_mult.tolist() == pytest.approx([1.5, 1.3, 1.1])


@pytest.mark.parametrize("side", [1, -1])
def test_stall_is_compared_at_current_multiplier_after_prior_tightening(side):
    d, h = holding_path(side, 3)
    # After first reduction the old stop is 87/113. At m=1.3 this
    # next candidate progresses by one dollar; m=1.5 would look stalled.
    d.loc[2, "ma"] = 100.0 + side
    _, _, _, stops, _ = engine.simulate(h, d, config())
    assert stops.new_mult.tolist() == pytest.approx([1.5, 1.3, 1.3])
    assert not bool(stops.iloc[2].stalled)
    assert stops.natural_candidate.iloc[2] == pytest.approx(100.0 - side * 12.0)


@pytest.mark.parametrize("side", [1, -1])
def test_tightening_requires_positive_profit_after_fees_and_slippage(side):
    d, h = holding_path(side, 3)
    d.loc[1, "close"] = 100.0 + side * 0.05
    d.loc[2, "close"] = 100.0 + side * 0.3
    _, _, _, stops, _ = engine.simulate(h, d, config(fee=0.0005, slip=0.0003))
    assert stops.expected_profit_at_close.iloc[1] < 0
    assert stops.expected_profit_at_close.iloc[2] > 0
    assert stops.new_mult.tolist() == pytest.approx([1.5, 1.5, 1.3])


@pytest.mark.parametrize("side", [1, -1])
def test_one_atr_trigger_uses_fixed_entry_atr_and_includes_exact_threshold(side):
    d, h = holding_path(side, 3)
    d.loc[1, ["close", "atr", "ma"]] = [100.0 + side * 5.0, 1.0, 100.0 - side * 13.5]
    d.loc[2, ["close", "atr", "ma"]] = [100.0 + side * 10.0, 1.0, 100.0 - side * 13.5]
    _, _, _, zero, _ = engine.simulate(h, d, config(profit_trigger_atr=0.0))
    _, _, _, one, _ = engine.simulate(h, d, config(profit_trigger_atr=1.0))
    assert zero.new_mult.tolist() == pytest.approx([1.5, 1.3, 1.1])
    assert one.new_mult.tolist() == pytest.approx([1.5, 1.5, 1.3])
    assert one.favorable_move_atr.iloc[1] == pytest.approx(0.5)
    assert one.favorable_move_atr.iloc[2] == pytest.approx(1.0)


@pytest.mark.parametrize("side", [1, -1])
def test_multiplier_floor_does_not_force_actual_stop_away_from_current_price(side):
    d, h = holding_path(side, 8)
    d.loc[6, "ma"] = 100.0 + side * 10.0
    d.loc[7, ["ma", "atr"]] = [100.0 + side * 7.0, 20.0]
    h.loc[24 * 6:, ["open", "high", "low", "close"]] = [
        100.0 + side * 6.0, 100.0 + side * 6.0 + 0.1,
        100.0 + side * 6.0 - 0.1, 100.0 + side * 6.0,
    ]
    _, trades, _, stops, _ = engine.simulate(h, d, config())
    assert trades.iloc[0].exit_reason == "sample_end"
    assert stops.new_mult.iloc[-1] == 0.5
    assert stops.new_stop.iloc[-2:].tolist() == pytest.approx([100.0 + side * 5.0] * 2)
    distance = side * (h.close.iloc[-1] - stops.new_stop.iloc[-1])
    assert distance == pytest.approx(1.0)
    assert distance < 0.5 * d.atr.iloc[7]


def test_new_daily_entry_resets_multiplier_arming_and_entry_atr():
    d, h = holding_path(day_count=9)
    h.loc[24 * 6, ["open", "high", "low", "close"]] = [94.0, 94.1, 93.9, 94.0]
    d.loc[7, ["cross", "slope", "atr"]] = [1, 0.1, 20.0]
    _, trades, _, stops, _ = engine.simulate(h, d, config(tighten_mode="armed_daily"))
    assert len(trades) == 2
    assert trades.iloc[0].stop_mult == 0.5
    assert trades.iloc[1].entry_atr == 20.0
    second_entry = stops[stops.trade_id == 2].iloc[0]
    assert second_entry.new_mult == 1.5
    assert not bool(second_entry.new_armed)
    assert second_entry.new_stop == 70.0


def test_stop_reversal_resets_multiplier_and_arming():
    d, h = holding_path(day_count=8)
    d.loc[6:, ["close", "slope"]] = [90.0, -0.1]
    d.loc[6, "cross"] = -1
    h.loc[24 * 6, ["open", "high", "low", "close"]] = [94.0, 94.1, 93.9, 94.0]
    h.loc[24 * 6 + 1:, ["open", "high", "low", "close"]] = [90.0, 90.1, 89.9, 90.0]
    _, trades, _, stops, _ = engine.simulate(h, d, config(reverse=True, tighten_mode="armed_daily"))
    assert len(trades) == 2
    assert trades.iloc[0].stop_mult == 0.5
    second = trades.iloc[1]
    assert second.entry_reason == "stop_reversal"
    assert second.side == -1
    assert second.entry_time == h.timestamp.iloc[24 * 6 + 1]
    second_entry = stops[stops.trade_id == 2].iloc[0]
    assert second_entry.new_mult == 1.5
    assert not bool(second_entry.new_armed)
    assert second_entry.new_stop == 115.0


def test_reversal_can_use_recent_cross_and_latest_slowdown_without_new_cross():
    d, h = holding_path(day_count=3)
    d.loc[1, ["ma", "cross", "close", "slope"]] = [101.0, -1, 100.0, 0.1]
    d.loc[2, ["ma", "cross", "close", "slope"]] = [101.2, 0, 100.0, 0.02]
    h.loc[60, ["low", "close"]] = [85.0, 86.0]
    h.loc[61:, ["open", "high", "low", "close"]] = [85.0, 85.1, 84.9, 85.0]
    original, _, _, _, _ = engine.simulate(h, d, config(reverse=True, tighten_mode="fixed"))
    modified, trades, _, _, _ = engine.simulate(
        h, d, config(reverse=True, tighten_mode="fixed", entry_mode="opposite_slowdown"),
    )
    assert original["reversal_entries"] == 0
    assert modified["reversal_entries"] == 1
    reverse = trades.iloc[1]
    assert reverse.qualification == "opposite_slowdown"
    assert reverse.entry_reason == "stop_reversal"
    assert reverse.cross_day == d.timestamp.iloc[1]
    assert reverse.signal_day == d.timestamp.iloc[2]
    assert reverse.entry_time == h.timestamp.iloc[61]


def test_newly_tightened_gap_stop_uses_open_and_precedes_rsi_profit_exit():
    d, h = holding_path(-1, 2)
    d.loc[1, ["close", "rsi", "accel1"]] = [80.0, 20.0, True]
    h.loc[24, ["open", "high", "low", "close"]] = [114.0, 114.1, 113.9, 114.0]
    _, trades, _, stops, _ = engine.simulate(h, d, config(short_exit="accel1_rsi30"))
    assert len(trades) == 1
    assert stops.new_stop.iloc[1] == 113.0
    assert trades.iloc[0].exit_reason == "stop_gap"
    assert trades.iloc[0].exit_reference == 114.0
    assert trades.iloc[0].exit_time == DAY_ZERO + pd.Timedelta(days=2)


@pytest.mark.parametrize("mode", ["stall_only", "armed_daily"])
def test_unclosed_daily_changes_do_not_change_any_historical_output(mode):
    d, h = holding_path(day_count=3)
    altered = d.copy()
    altered.loc[3:, ["close", "ma", "atr", "slope", "cross"]] = [1.0, 9000.0, 0.001, -5.0, -1]
    baseline = engine.simulate(h, d, config(tighten_mode=mode))
    changed = engine.simulate(h, altered, config(tighten_mode=mode))
    assert baseline[0] == changed[0]
    for before, after in zip(baseline[1:], changed[1:]):
        pd.testing.assert_frame_equal(before, after)
    assert baseline[3].timestamp.iloc[1] == DAY_ZERO + pd.Timedelta(days=2)


def test_profit_snapshot_precedes_funding_at_next_day_boundary():
    d, h = holding_path(day_count=2)
    d.loc[1, "close"] = 100.5
    funding = pd.DataFrame({
        "timestamp": [DAY_ZERO + pd.Timedelta(days=2)],
        "funding_rate": [0.02], "mark_price": [100.0],
    })
    _, _, _, stops, charges = engine.simulate(h, d, config(), funding=funding)
    assert len(charges) == 1
    assert stops.expected_profit_at_close.iloc[1] == pytest.approx(50.0)
    assert stops.new_mult.tolist() == pytest.approx([1.5, 1.3])


def test_new_velocity_features_are_causal_and_input_frame_is_not_mutated():
    original = days(8)
    original["ma"] = [100.0, 99.0, 98.8, 98.82, 99.0, 99.3, 99.2, 99.4]
    untouched = original.copy(deep=True)
    whole = engine.enrich_features(original)
    prefix = engine.enrich_features(original.iloc[:5])
    pd.testing.assert_frame_equal(original, untouched)
    pd.testing.assert_frame_equal(whole.iloc[:5], prefix)
    assert whole.ma_step.iloc[2] == pytest.approx(-0.2)
    assert whole.prev_ma_step.iloc[2] == pytest.approx(-1.0)
    assert whole.ma_step_change.iloc[2] == pytest.approx(0.8)
