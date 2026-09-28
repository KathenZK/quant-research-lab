"""Causal delayed-cross and frozen-engine controls using synthetic inputs only."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_engine(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


engine = load_engine("ma7_car_generalization_test_engine", "research/_shared-kernels/ma7-cross-atr-ratchet/v1/engine.py")
old_engine = load_engine("ma7_car_generalization_frozen_r4", "research/hype/1d-ma7-cross-atr-ratchet/scripts/engine_r4.py")
ZERO = pd.Timestamp("2026-01-01", tz="UTC")


def path(side=1, count=9):
    price = 100.0 + side * 10.0
    daily = pd.DataFrame({
        "timestamp": pd.date_range(ZERO, periods=count + 3, freq="D"),
        "open": price, "high": price + 5, "low": price - 5,
        "close": price, "ma": 100.0, "atr": 10.0, "rsi": 50.0,
        "slope": 0.0, "cross": 0, "ready": True,
        "accel1": False, "accel2": False,
    })
    daily.loc[0, ["cross", "slope"]] = [side, side * 0.02]
    hourly = pd.DataFrame({
        "timestamp": pd.date_range(ZERO + pd.Timedelta(days=1), periods=24 * count, freq="h"),
        "open": price, "high": price + 0.1, "low": price - 0.1, "close": price,
    })
    return daily, hourly


def cfg(**changes):
    return engine.Config(**{
        "fee": 0.0, "slip": 0.0, "short_exit": "none", "reverse": False,
        "progress_source": "high_low", "progress_days": 4,
        "entry_wait_days": 3, **changes,
    })


def run(daily, hourly, **changes):
    return engine.simulate(hourly, daily, cfg(**changes))


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("wait", [1, 2, 3])
def test_first_qualifying_confirmation_uses_confirm_day_stop_and_next_open(side, wait):
    d, h = path(side)
    d.loc[wait:, ["slope", "close", "ma", "atr"]] = [side * 0.1, 100 + side * 11, 101, 9]
    summary, trades, _, _, _ = run(d, h, entry_wait_days=wait)
    assert summary["delayed_entries"] == 1
    assert len(trades) == 1
    p = trades.iloc[0]
    assert p.entry_reason == "delayed_cross"
    assert p.cross_day == ZERO
    assert p.signal_day == ZERO + pd.Timedelta(days=wait)
    assert p.entry_time == ZERO + pd.Timedelta(days=wait + 1)
    assert p.entry_wait_days_used == wait
    assert p.initial_stop == 101 - side * 1.5 * 9
    assert p.entry_atr == 9


@pytest.mark.parametrize("side", [1, -1])
def test_d2_window_expires_before_third_day_while_d3_accepts(side):
    d, h = path(side)
    d.loc[3:, ["slope", "close"]] = [side * 0.1, 100 + side * 11]
    assert run(d, h, entry_wait_days=2)[0]["trades"] == 0
    assert run(d, h, entry_wait_days=3)[1].entry_wait_days_used.tolist() == [3]


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("invalid_close", ["equal_ma", "other_side"])
def test_ma_touch_or_wrong_side_cancels_pending_forever(side, invalid_close):
    d, h = path(side)
    d.loc[1, "close"] = 100 if invalid_close == "equal_ma" else 100 - side
    d.loc[2:, ["slope", "close"]] = [side * 0.1, 100 + side * 11]
    assert run(d, h)[0]["trades"] == 0


@pytest.mark.parametrize("side", [1, -1])
def test_opposite_cross_replaces_pending_with_new_direction(side):
    d, h = path(side)
    d.loc[1, ["cross", "slope", "close"]] = [-side, -side * 0.02, 100 - side * 10]
    d.loc[2:, ["slope", "close"]] = [-side * 0.1, 100 - side * 11]
    trades = run(d, h)[1]
    assert len(trades) == 1
    assert trades.iloc[0].side == -side
    assert trades.iloc[0].cross_day == ZERO + pd.Timedelta(days=1)
    assert trades.iloc[0].signal_day == ZERO + pd.Timedelta(days=2)


@pytest.mark.parametrize("side", [1, -1])
def test_slope_threshold_and_cross_close_progress_are_both_strict(side):
    d, h = path(side)
    # Day 1: slope exactly at threshold; day 2: close equals original cross.
    d.loc[1, ["slope", "close"]] = [side * 0.05, 100 + side * 11]
    d.loc[2, ["slope", "close"]] = [side * 0.1, 100 + side * 10]
    d.loc[3, ["slope", "close"]] = [side * 0.1, 100 + side * 11]
    trades = run(d, h)[1]
    assert trades.iloc[0].signal_day == ZERO + pd.Timedelta(days=3)


@pytest.mark.parametrize("side", [1, -1])
def test_confirmed_signal_is_consumed_even_if_gap_rejects_fill(side):
    d, h = path(side)
    d.loc[1:, ["slope", "close"]] = [side * 0.1, 100 + side * 11]
    gap = 80 if side == 1 else 120
    h.loc[24, ["open", "high", "low", "close"]] = [gap, gap + 0.1, gap - 0.1, gap]
    assert run(d, h)[0]["trades"] == 0


@pytest.mark.parametrize("side", [1, -1])
def test_failed_original_fill_never_creates_waiting_intent(side):
    d, h = path(side)
    d.loc[0:, ["slope", "close"]] = [side * 0.1, 100 + side * 11]
    gap = 80 if side == 1 else 120
    h.loc[0, ["open", "high", "low", "close"]] = [gap, gap + 0.1, gap - 0.1, gap]
    assert run(d, h)[0]["trades"] == 0


@pytest.mark.parametrize("side", [1, -1])
def test_cross_while_held_is_not_reused_after_stop(side):
    d, h = path(side)
    d.loc[0, "slope"] = side * 0.1
    d.loc[1, ["cross", "slope"]] = [side, side * 0.02]
    d.loc[2:, ["slope", "close"]] = [side * 0.1, 100 + side * 11]
    gap = 80 if side == 1 else 120
    h.loc[48, ["open", "high", "low", "close"]] = [gap, gap + 0.1, gap - 0.1, gap]
    result = run(d, h)
    assert len(result[1]) == 1
    assert result[0]["delayed_entries"] == 0
    assert result[1].exit_reason.iloc[0] == "stop_gap"


def test_cross_on_same_rsi_exit_hour_cannot_create_later_intent():
    d, h = path(-1)
    d.loc[0, "slope"] = -0.1
    d.loc[1, ["cross", "slope", "close", "rsi", "accel1"]] = [-1, -0.02, 89.0, 20.0, True]
    d.loc[2:, ["slope", "close"]] = [-0.1, 88.0]
    result = run(d, h, short_exit="accel1_rsi30")
    assert len(result[1]) == 1
    assert result[1].exit_reason.iloc[0] == "accel1_rsi30"


@pytest.mark.parametrize("side", [1, -1])
def test_no_warmup_or_previous_window_pending_is_inherited(side):
    d, h = path(side)
    d.loc[1:, ["slope", "close"]] = [side * 0.1, 100 + side * 11]
    result = engine.simulate(h, d, cfg(), start=ZERO + pd.Timedelta(days=2))
    assert result[0]["trades"] == 0


@pytest.mark.parametrize("side", [1, -1])
def test_pending_cancels_if_a_closed_bar_is_not_eligible(side):
    d, h = path(side)
    d.loc[1, "ready"] = False
    d.loc[2:, ["slope", "close"]] = [side * 0.1, 100 + side * 11]
    assert run(d, h)[0]["trades"] == 0


@pytest.mark.parametrize("side", [1, -1])
def test_day_after_longest_window_is_already_expired(side):
    d, h = path(side)
    d.loc[4:, ["slope", "close"]] = [side * 0.1, 100 + side * 11]
    assert run(d, h, entry_wait_days=3)[0]["trades"] == 0


@pytest.mark.parametrize("side", [1, -1])
def test_cross_on_gap_stop_hour_is_discarded(side):
    d, h = path(side)
    d.loc[0, "slope"] = side * 0.1
    d.loc[1, ["cross", "slope"]] = [side, side * 0.02]
    d.loc[2:, ["slope", "close"]] = [side * 0.1, 100 + side * 11]
    gap = 80 if side == 1 else 120
    h.loc[24, ["open", "high", "low", "close"]] = [gap, gap + 0.1, gap - 0.1, gap]
    result = run(d, h)
    assert len(result[1]) == 1
    assert result[1].exit_reason.iloc[0] == "stop_gap"
    assert result[0]["delayed_entries"] == 0


@pytest.mark.parametrize("side", [1, -1])
def test_valid_delayed_fill_is_not_reused_after_position_stops(side):
    d, h = path(side)
    d.loc[1:, ["slope", "close"]] = [side * 0.1, 100 + side * 11]
    gap = 80 if side == 1 else 120
    h.loc[48, ["open", "high", "low", "close"]] = [gap, gap + 0.1, gap - 0.1, gap]
    result = run(d, h)
    assert len(result[1]) == 1
    assert result[1].exit_reason.iloc[0] == "stop_gap"
    assert result[0]["delayed_entries"] == 1


@pytest.mark.parametrize("side", [1, -1])
def test_confirmation_execution_delay_uses_only_completed_held_days(side):
    d, h = path(side)
    d.loc[1:, ["slope", "close"]] = [side * 0.1, 100 + side * 11]
    _, trades, _, stops, _ = run(d, h, delay_hours=1)
    assert trades.iloc[0].entry_time == ZERO + pd.Timedelta(days=2, hours=1)
    assert stops.tightening_trigger.iloc[1] == "partial_entry_day"
    assert stops.extreme_day.iloc[2] == ZERO + pd.Timedelta(days=3)


def assert_original_outputs_equal(before, after):
    for key, value in before[0].items():
        if key != "name":
            assert after[0][key] == value, key
    assert after[0]["name"] == before[0]["name"] + "_wait0"
    for original, new in zip(before[1:], after[1:]):
        pd.testing.assert_frame_equal(original, new[original.columns], check_exact=True)


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("delay", [0, 1])
@pytest.mark.parametrize("source,days", [("high_low", 0), ("high_low", 4), ("close", 3)])
def test_wait_zero_all_five_outputs_reproduce_frozen_r4(side, delay, source, days):
    d, h = path(side)
    d.loc[0, "slope"] = side * 0.1
    settings = dict(reverse=False, short_exit="none", delay_hours=delay,
                    progress_days=days, progress_source=source)
    funds = pd.DataFrame({"timestamp": [ZERO + pd.Timedelta(days=3, hours=4, minutes=7),
                                      ZERO + pd.Timedelta(days=4)],
                          "funding_rate": [0.0001, -0.0002], "mark_price": [np.nan, 110.0]})
    for funding, carry in [(None, 0.0), (funds, 0.0005)]:
        before = old_engine.simulate(h, d, old_engine.Config(**settings), funding=funding, carry_daily=carry)
        after = engine.simulate(h, d, engine.Config(**settings), funding=funding, carry_daily=carry)
        assert_original_outputs_equal(before, after)


def test_cached_execution_matches_r4_on_seeded_433_day_ohlc_account():
    rng = np.random.default_rng(7941)
    count = 462
    daily_close = 100 * np.exp(np.cumsum(rng.normal(0, 0.035, count)))
    daily_open = np.r_[100.0, daily_close[:-1]]
    dates = pd.date_range(ZERO, periods=count, freq="D")
    d = pd.DataFrame({"timestamp": dates, "open": daily_open,
                      "close": daily_close, "high": np.maximum(daily_open, daily_close) * 1.01,
                      "low": np.minimum(daily_open, daily_close) * 0.99})
    frames = []
    for day in range(count):
        prices = np.linspace(daily_open[day], daily_close[day], 25)
        frames.append(pd.DataFrame({"timestamp": pd.date_range(dates[day], periods=24, freq="h"),
                                    "open": prices[:-1], "close": prices[1:],
                                    "high": np.maximum(prices[:-1], prices[1:]) * 1.005,
                                    "low": np.minimum(prices[:-1], prices[1:]) * 0.995}))
    h = pd.concat(frames, ignore_index=True)
    feature_frame = engine.features(d)
    pd.testing.assert_frame_equal(old_engine.features(d), feature_frame, check_exact=True)
    for reverse in (False, True):
        settings = dict(reverse=reverse, progress_days=4, progress_source="high_low")
        before = old_engine.simulate(h, feature_frame, old_engine.Config(**settings))
        after = engine.simulate(h, feature_frame, engine.Config(**settings))
        assert_original_outputs_equal(before, after)


def test_unclosed_future_daily_values_cannot_change_executed_history():
    d, h = path(1, count=5)
    d.loc[1, ["slope", "close"]] = [0.1, 111.0]
    changed = d.copy(deep=True)
    changed.loc[5:, ["high", "low", "close", "ma", "atr", "cross", "slope"]] = [99999.0, 0.001, 1000.0, 9000.0, 0.001, -1, -9.0]
    before, after = run(d, h), run(changed, h)
    assert before[0] == after[0]
    for original, new in zip(before[1:], after[1:]):
        pd.testing.assert_frame_equal(original, new, check_exact=True)


@pytest.mark.parametrize("invalid", [-1, True, 1.5, "3"])
def test_invalid_wait_rejected(invalid):
    with pytest.raises(ValueError, match="entry_wait_days"):
        cfg(entry_wait_days=invalid)


def test_deferred_entry_cannot_silently_mix_other_entry_families():
    with pytest.raises(ValueError, match="original entry_mode"):
        cfg(entry_mode="opposite_slowdown")
