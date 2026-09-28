"""Execution-contract checks using small, hand-auditable synthetic paths."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


ENGINE_PATH = Path(__file__).resolve().parents[1] / (
    "research/hype/1d-ma7-cross-atr-ratchet/scripts/engine.py"
)
SPEC = importlib.util.spec_from_file_location("hype_car_engine_tested", ENGINE_PATH)
assert SPEC is not None and SPEC.loader is not None
engine = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = engine
SPEC.loader.exec_module(engine)
DAY_ZERO = pd.Timestamp("2026-01-01", tz="UTC")


def days(count=10):
    """Precomputed inputs isolate execution from the separately tested indicators."""
    return pd.DataFrame({
        "timestamp": pd.date_range(DAY_ZERO, periods=count, freq="D"),
        "close": 100.0, "ma": 100.0, "atr": 10.0, "rsi": 50.0,
        "slope": 0.0, "cross": 0, "ready": True,
        "accel1": False, "accel2": False,
    })


def hours(count=48, price=100.0):
    return pd.DataFrame({
        "timestamp": pd.date_range(DAY_ZERO + pd.Timedelta(days=1), periods=count, freq="h"),
        "open": price, "high": price + 1, "low": price - 1, "close": price,
    })


def config(**kwargs):
    return engine.Config(**{"fee": 0.0, "slip": 0.0, "short_exit": "none", **kwargs})


def signal(d, day, side):
    d.loc[day, ["cross", "slope", "close"]] = [side, side * 0.1, 100 + side * 5]


def test_wilder_initialization_warmup_and_feature_prefix_invariance():
    values = np.r_[np.nan, np.arange(1, 17, dtype=float)]
    smoothed = engine.wilder(values, 14)
    assert np.isnan(smoothed[:14]).all()
    assert smoothed[14] == pytest.approx(7.5)
    assert smoothed[15] == pytest.approx((13 * 7.5 + 15) / 14)

    close = 100 + np.arange(45) * 0.2 + np.sin(np.arange(45)) * 2
    raw = pd.DataFrame({
        "timestamp": pd.date_range(DAY_ZERO, periods=45, freq="D"),
        "open": close, "high": close + 1, "low": close - 1, "close": close,
    })
    baseline = engine.features(raw)
    mutated = raw.copy()
    mutated.loc[32:, ["open", "high", "low", "close"]] *= 8
    pd.testing.assert_frame_equal(baseline.iloc[:32], engine.features(mutated).iloc[:32])
    pd.testing.assert_frame_equal(baseline.iloc[:32], engine.features(raw.iloc[:32]))
    assert not baseline.ready.iloc[:28].any()
    assert baseline.ready.iloc[28:].all()
    flat = raw.assign(open=100.0, high=101.0, low=99.0, close=100.0)
    assert engine.features(flat).rsi.iloc[6:].eq(50).all()


@pytest.mark.parametrize("side", [1, -1])
def test_stops_ratchet_both_sides_and_ignore_same_day_future_features(side):
    d, h = days(), hours(96, 100 + side * 5)
    signal(d, 0, side)
    d.loc[1, "ma"] = 100 + side * 3
    d.loc[2, ["ma", "atr"]] = [100 - side * 2, 20]
    d.loc[3, "ma"] = 100 + side * 6
    # The bar labelled day 4 is not closed until after the execution window.
    d.loc[4:, ["ma", "atr", "cross", "slope"]] = [1_000_000, 0.01, -side, -side]
    _, trades, _, stops, _ = engine.simulate(h, d, config())
    assert stops.new_stop.tolist() == pytest.approx(
        [100 - side * 15, 100 - side * 12, 100 - side * 12, 100 - side * 9]
    )
    assert trades.iloc[0].exit_reason == "sample_end"
    assert trades.iloc[0].entry_time == DAY_ZERO + pd.Timedelta(days=1)


def test_gap_stop_uses_open_and_precedes_rsi_profit_exit():
    d, h = days(), hours(25)
    signal(d, 0, -1)
    d.loc[1, ["ma", "atr", "close", "rsi", "accel1"]] = [70, 10, 75, 20, True]
    h.loc[24, ["open", "high", "low", "close"]] = [90, 91, 89, 90]
    _, trades, _, _, _ = engine.simulate(h, d, config(short_exit="accel1_rsi30"))
    assert len(trades) == 1
    # Updated stop is 85; the gap fills at 90, not the better stop price of 85.
    assert trades.iloc[0].stop == 85
    assert trades.iloc[0].exit_reason == "stop_gap"
    assert trades.iloc[0].exit_reference == 90
    assert trades.iloc[0].exit_time == DAY_ZERO + pd.Timedelta(days=2)


@pytest.mark.parametrize("cross_day,recross,expect_reverse", [(2, False, True), (1, False, False), (2, True, False)])
def test_reversal_five_closed_day_window_latest_cross_and_next_hour(cross_day, recross, expect_reverse):
    d, h = days(), hours(24 * 7, 105)
    signal(d, 0, 1)
    signal(d, cross_day, -1)
    d.loc[cross_day:6, ["slope", "close"]] = [-0.1, 95]
    if recross:
        d.loc[5, "cross"] = 1
    stop_index = 24 * 6 + 12  # Day 7; the five known days are 2 through 6.
    h.loc[stop_index, ["low", "close"]] = [84, 90]
    h.loc[stop_index + 1:, ["open", "high", "low", "close"]] = [90, 91, 89, 90]
    result, trades, _, _, _ = engine.simulate(h, d, config())
    assert result["reversal_entries"] == int(expect_reverse)
    assert trades.iloc[0].exit_reason == "stop_intrahour"
    assert trades.iloc[0].exit_time == h.timestamp.iloc[stop_index]
    assert trades.iloc[0].exit_interval_end == h.timestamp.iloc[stop_index + 1]
    if expect_reverse:
        reverse = trades.iloc[1]
        assert reverse.side == -1
        assert reverse.entry_time == h.timestamp.iloc[stop_index + 1]
        assert reverse.cross_day == d.timestamp.iloc[cross_day]
        assert reverse.entry_reason == "stop_reversal"
    else:
        assert len(trades) == 1


def test_intrahour_stop_does_not_reuse_consumed_daily_entry_signal():
    d, h = days(), hours(48, 105)
    signal(d, 0, 1)
    h.loc[0, "low"] = 84  # Entry and exit occur in the first execution hour.
    result, trades, _, _, _ = engine.simulate(h, d, config())
    assert result["trades"] == 1
    assert trades.iloc[0].exit_reason == "stop_intrahour"
    assert trades.iloc[0].entry_time == h.timestamp.iloc[0]


@pytest.mark.parametrize("mode,accel1,accel2,profitable,expected", [
    ("none", True, True, True, False),
    ("rsi30", False, False, True, True),
    ("accel1_rsi30", True, False, True, True),
    ("accel1_rsi30", False, True, True, False),
    ("accel2_rsi30", False, True, True, True),
    ("accel1_rsi30", True, True, False, False),
])
def test_short_rsi_exit_requires_profit_and_requested_acceleration(mode, accel1, accel2, profitable, expected):
    d, h = days(), hours(26)
    signal(d, 0, -1)
    d.loc[1, ["close", "rsi", "accel1", "accel2"]] = [80 if profitable else 101, 25, accel1, accel2]
    # A fresh opposite entry signal must not immediately reopen after RSI exit.
    d.loc[1, ["cross", "slope"]] = [1, 0.1]
    result, trades, _, _, _ = engine.simulate(h, d, config(short_exit=mode))
    assert result["short_tp_exits"] == int(expected)
    assert len(trades) == 1
    assert trades.iloc[0].exit_reason == (mode if expected else "sample_end")
    if expected:
        assert trades.iloc[0].exit_time == DAY_ZERO + pd.Timedelta(days=2)
        assert trades.iloc[0].tp_signal_day == DAY_ZERO + pd.Timedelta(days=1)


@pytest.mark.parametrize("side", [1, -1])
def test_fees_slippage_and_funding_match_independent_account_arithmetic(side):
    d, h = days(), hours(2)
    signal(d, 0, side)
    fee, slip, rate, official_mark = 0.001, 0.002, 0.0004, 110.0
    fund = pd.DataFrame({
        "timestamp": [h.timestamp.iloc[0], h.timestamp.iloc[1]],
        "funding_rate": [rate * 100, rate], "mark_price": [official_mark, official_mark],
    })
    summary, trades, _, _, charges = engine.simulate(h, d, config(fee=fee, slip=slip), funding=fund)
    entry = 100 * (1 + side * slip)
    qty = 10000 / (entry * (1 + fee))
    exit_fill = 100 * (1 - side * slip)
    funding_cost = side * qty * official_mark * rate
    expected = 10000 + side * qty * (exit_fill - entry) - qty * (entry + exit_fill) * fee - funding_cost
    assert summary["ending_equity"] == pytest.approx(expected)
    assert summary["funding_paid"] == pytest.approx(funding_cost)
    # No position existed before the entry-hour funding event.
    assert len(charges) == 1
    assert charges.iloc[0].timestamp == h.timestamp.iloc[1]
    assert trades.iloc[0].net_pnl == pytest.approx(expected - 10000)
    assert qty * entry <= 10000 - qty * entry * fee + 1e-8


def test_acceleration_uses_prior_atr_and_one_sided_downside_changes():
    close = np.r_[np.repeat(100.0, 29), 99.0, 96.0, 100.0]
    raw = pd.DataFrame({
        "timestamp": pd.date_range(DAY_ZERO, periods=len(close), freq="D"),
        "open": close, "high": close + 1, "low": close - 1, "close": close,
    })
    featured = engine.features(raw)
    assert not featured.accel1.iloc[29]
    assert featured.accel1.iloc[30]
    assert featured.accel2.iloc[30]
    assert not featured.accel1.iloc[31]
    assert not featured.accel2.iloc[31]
    # Raising only today's range may change today's ATR, but not accel1 threshold.
    raw.loc[30, ["high", "low"]] = [196.0, 1.0]
    large_today = engine.features(raw)
    assert large_today.atr.iloc[30] > 3
    assert large_today.accel1.iloc[30]


def test_missing_daily_and_hourly_bars_are_rejected():
    d, h = days(), hours(48)
    signal(d, 0, 1)
    with pytest.raises(ValueError, match="Missing/empty hourly"):
        engine.simulate(h.drop(index=12), d, config())
    raw = pd.DataFrame({
        "timestamp": pd.date_range(DAY_ZERO, periods=40, freq="D"),
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
    })
    with pytest.raises(ValueError, match="Daily gaps/duplicates"):
        engine.features(raw.drop(index=20))


@pytest.mark.parametrize("side", [1, -1])
def test_cross_from_equal_ma_and_strict_slope_threshold(side):
    close = np.r_[np.repeat(100.0, 29), 100.0 + side * 5]
    raw = pd.DataFrame({
        "timestamp": pd.date_range(DAY_ZERO, periods=30, freq="D"),
        "open": close, "high": close + 1, "low": close - 1, "close": close,
    })
    d = engine.features(raw)
    assert d.close.iloc[28] == d.ma.iloc[28]
    assert d.cross.iloc[29] == side
    h = hours(24, close[-1])
    h["timestamp"] = pd.date_range(DAY_ZERO + pd.Timedelta(days=30), periods=24, freq="h")
    threshold = side * d.slope.iloc[29]
    equal, _, _, _, _ = engine.simulate(h, d, config(slope=threshold), start=h.timestamp.iloc[0])
    passed, trades, _, _, _ = engine.simulate(h, d, config(slope=threshold - 1e-10), start=h.timestamp.iloc[0])
    assert equal["trades"] == 0
    assert passed["trades"] == 1
    assert trades.iloc[0].entry_time == h.timestamp.iloc[0]
    assert trades.iloc[0].signal_day == d.timestamp.iloc[29]
