"""Hand-calculated R4 close progress checks; no historical performance inputs."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "research/hype/1d-ma7-cross-atr-ratchet/scripts"


def load_engine(version):
    spec = importlib.util.spec_from_file_location(f"hype_car_{version}_close_tests", SCRIPTS / f"engine_{version}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


engine = load_engine("r4")
r3 = load_engine("r3")
ZERO = pd.Timestamp("2026-01-01", tz="UTC")


def path(side=1, count=10):
    """Explicit indicator fixture isolates stop scheduling from indicators."""
    price = 100.0 + side * 10.0
    d = pd.DataFrame({
        "timestamp": pd.date_range(ZERO, periods=count + 3, freq="D"),
        "open": price, "high": price + 5.0, "low": price - 5.0,
        "close": price, "ma": 100.0, "atr": 10.0, "rsi": 50.0,
        "slope": 0.0, "cross": 0, "ready": True,
        "accel1": False, "accel2": False,
    })
    d.loc[0, ["cross", "slope"]] = [side, side * 0.1]
    h = pd.DataFrame({
        "timestamp": pd.date_range(ZERO + pd.Timedelta(days=1), periods=24 * count, freq="h"),
        "open": price, "high": price + 0.1, "low": price - 0.1, "close": price,
    })
    h.loc[0, ["open", "high", "low"]] = [100.0, max(price, 100.0) + 0.1, min(price, 100.0) - 0.1]
    d.loc[1, ["open", "high", "low"]] = [100.0, max(price + 5.0, 100.0), min(price - 5.0, 100.0)]
    return d, h


def cfg(**changes):
    return engine.Config(**{
        "fee": 0.0, "slip": 0.0, "short_exit": "none", "reverse": False,
        "tighten_mode": "stall_only", "progress_days": 1,
        "progress_source": "close", **changes,
    })


def simulate(d, h, **changes):
    return engine.simulate(h, d, cfg(**changes))


@pytest.mark.parametrize("side", [1, -1])
def test_close_refreshes_when_wick_does_not(side):
    d, h = path(side, 4)
    d.loc[2, "close"] = d.loc[1, "close"] + side
    close = simulate(d, h)
    wick = simulate(d, h, progress_source="high_low")
    assert close[3].new_extreme.iloc[2]
    assert close[3].no_new_extreme_days.iloc[2] == 0
    assert close[3].new_mult.iloc[2] == 1.5
    assert not wick[3].new_extreme.iloc[2]
    assert wick[3].new_mult.iloc[2] == 1.3
    assert close[3].extreme_price.iloc[2] == d.loc[2, "close"]


@pytest.mark.parametrize("side", [1, -1])
def test_wick_refresh_does_not_block_close_tightening(side):
    d, h = path(side, 4)
    col = "high" if side == 1 else "low"
    d.loc[2, col] = d.loc[1, col] + side
    d.loc[2, "close"] = d.loc[1, "close"] - side
    close = simulate(d, h)
    wick = simulate(d, h, progress_source="high_low")
    assert close[3].no_new_extreme_days.iloc[2] == 1
    assert close[3].new_mult.iloc[2] == 1.3
    assert wick[3].new_extreme.iloc[2]
    assert wick[3].new_mult.iloc[2] == 1.5


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("days", [1, 4])
def test_equal_close_counts_and_exact_arming_day(side, days):
    d, h = path(side)
    _, trades, _, stops, _ = simulate(d, h, progress_days=days)
    assert stops.tightening_trigger.iloc[1] == "extreme_initialize"
    assert stops.extreme_price.iloc[1] == d.close.iloc[1]
    assert stops.no_new_extreme_days.iloc[1] == 0
    assert stops.new_mult.iloc[1] == 1.5
    assert stops.new_mult.iloc[days + 1] == 1.3
    assert stops.new_mult.iloc[:days + 1].eq(1.5).all()
    assert stops.signal_day.iloc[days + 1] == ZERO + pd.Timedelta(days=days + 1)
    assert stops.timestamp.iloc[days + 1] == ZERO + pd.Timedelta(days=days + 2)
    assert trades.iloc[0].arm_day == ZERO + pd.Timedelta(days=days + 1)
    assert stops.no_new_extreme_days.iloc[1:days + 2].tolist() == list(range(days + 1))


@pytest.mark.parametrize("side", [1, -1])
def test_reference_is_holding_running_close_not_previous_day_close(side):
    d, h = path(side, 5)
    d.loc[2, "close"] = d.loc[1, "close"] - side * 2
    d.loc[3, "close"] = d.loc[1, "close"] - side
    _, _, _, stops, _ = simulate(d, h, progress_days=2)
    assert stops.no_new_extreme_days.iloc[2:4].tolist() == [1, 2]
    assert stops.new_mult.iloc[3] == 1.3
    assert stops.extreme_day.iloc[3] == ZERO + pd.Timedelta(days=1)


@pytest.mark.parametrize("side", [1, -1])
def test_signal_day_close_and_partial_entry_day_do_not_initialize(side):
    d, h = path(side, 6)
    d.loc[0:1, "close"] = 10000.0 if side == 1 else 0.01
    _, trades, _, stops, _ = simulate(d, h, delay_hours=1)
    assert trades.iloc[0].entry_time == ZERO + pd.Timedelta(days=1, hours=1)
    assert stops.tightening_trigger.iloc[1] == "partial_entry_day"
    assert not stops.initialized.iloc[1]
    assert stops.extreme_price.iloc[2] == d.loc[2, "close"]
    assert stops.extreme_day.iloc[2] == ZERO + pd.Timedelta(days=2)
    assert stops.no_new_extreme_days.iloc[2] == 0
    assert stops.new_mult.iloc[3] == 1.3


@pytest.mark.parametrize("side", [1, -1])
def test_armed_continues_through_losing_close_new_record_and_floor(side):
    d, h = path(side, 9)
    d.loc[1:2, "close"] = 100.0 - side
    d.loc[3:, "close"] = 100.0 + side * 11.0
    _, trades, _, stops, _ = simulate(d, h)
    assert not stops.profit_eligible.iloc[2]
    assert stops.new_extreme.iloc[3]
    assert stops.no_new_extreme_days.iloc[3] == 0
    assert stops.new_armed.iloc[2:].all()
    assert stops.new_mult.iloc[2:].tolist() == [1.3, 1.1, 0.9, 0.7, 0.5, 0.5, 0.5]
    assert trades.iloc[0].tightening_days == 5
    assert trades.iloc[0].stop_floor_reached
    assert (side * (stops.new_stop - stops.old_stop) >= 0).all()


@pytest.mark.parametrize("side", [1, -1])
def test_close_extreme_anchor_uses_same_source_if_explicitly_requested(side):
    d, h = path(side, 4)
    _, _, _, stops, _ = simulate(d, h, stop_anchor="extreme")
    expected = d.close.iloc[1] - side * 1.3 * d.atr.iloc[2]
    assert stops.anchor_candidate.iloc[2] == expected
    assert stops.extreme_price.iloc[2] == d.close.iloc[1]


def test_unclosed_and_future_closes_cannot_change_executed_history():
    d, h = path(1, 5)
    changed = d.copy(deep=True)
    changed.loc[5:, ["high", "low", "close", "ma", "atr", "cross", "slope"]] = [99999.0, 0.001, 1000.0, 9000.0, 0.001, -1, -9.0]
    baseline = simulate(d, h)
    altered = simulate(changed, h)
    assert baseline[0] == altered[0]
    for old, new in zip(baseline[1:], altered[1:]):
        pd.testing.assert_frame_equal(old, new, check_exact=True)


def test_new_position_resets_close_record_and_counter():
    d, h = path(1, 7)
    h.loc[72, ["open", "high", "low", "close"]] = [80.0, 80.1, 79.9, 80.0]
    d.loc[4, ["cross", "slope"]] = [1, 0.1]
    d.loc[5, "close"] = 109.0
    _, trades, _, stops, _ = simulate(d, h)
    assert len(trades) == 2
    assert trades.iloc[0].armed
    second = stops[stops.trade_id == 2].reset_index(drop=True)
    assert not second.initialized.iloc[0]
    assert not second.new_armed.iloc[0]
    assert second.new_mult.iloc[0] == 1.5
    assert second.extreme_price.iloc[1] == 109.0
    assert second.no_new_extreme_days.iloc[1] == 0


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("days,anchor", [(0, "ma"), (1, "ma"), (4, "ma"), (1, "extreme")])
def test_default_high_low_reproduces_all_r3_outputs_exactly(side, days, anchor):
    d, h = path(side, 8)
    settings = dict(fee=0.0005, slip=0.0003, short_exit="none", reverse=False,
                    tighten_mode="stall_only", progress_days=days, stop_anchor=anchor)
    old = r3.simulate(h, d, r3.Config(**settings))
    new = engine.simulate(h, d, engine.Config(**settings))
    assert new[0]["progress_source"] == "high_low"
    assert new[0]["name"] == old[0]["name"] + "_sourcehigh_low"
    for key, value in old[0].items():
        if key != "name":
            assert new[0][key] == value, key
    for before, after in zip(old[1:], new[1:]):
        pd.testing.assert_frame_equal(before, after[before.columns], check_exact=True)


def test_invalid_progress_source_rejected():
    with pytest.raises(ValueError, match="progress source"):
        cfg(progress_source="open")
