"""Independent, hand-calculated execution checks for R3 high/low progress.

These fixtures do not read historical strategy results or select parameters.
Daily indicators are explicit so timing, extrema and fill accounting can be
checked separately from the already-tested R1 indicator construction.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "research/hype/1d-ma7-cross-atr-ratchet/scripts"


def load_engine(version):
    spec = importlib.util.spec_from_file_location(f"hype_car_{version}_independent_tests", SCRIPTS / f"engine_{version}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


engine = load_engine("r3")
r2 = load_engine("r2")
ZERO = pd.Timestamp("2026-01-01", tz="UTC")


def path(side=1, count=9):
    """Signal on day 0, entry day 1, then complete stable holding days."""
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
        "entry_mode": "original", "tighten_mode": "stall_only",
        "progress_days": 2, **changes,
    })


def simulate(d, h, **changes):
    return engine.simulate(h, d, cfg(**changes))


@pytest.mark.parametrize("side", [1, -1])
def test_first_complete_day_initializes_then_two_equal_extremes_arm_next_open(side):
    d, h = path(side)
    _, trades, _, stops, _ = simulate(d, h)
    assert len(trades) == 1
    assert stops.new_mult.tolist() == pytest.approx([1.5, 1.5, 1.5, 1.3, 1.1, 0.9, 0.7, 0.5, 0.5])
    assert stops.no_new_extreme_days.iloc[1:4].tolist() == [0, 1, 2]
    assert stops.timestamp.iloc[3] == ZERO + pd.Timedelta(days=4)
    assert stops.signal_day.iloc[3] == ZERO + pd.Timedelta(days=3)
    assert trades.iloc[0].arm_day == ZERO + pd.Timedelta(days=3)
    assert int(trades.iloc[0].tightening_days) == 5
    assert trades.iloc[0].stop_floor_reached
    assert (side * (stops.new_stop - stops.old_stop) >= 0).all()
    assert (stops.new_mult >= 0.5).all()


@pytest.mark.parametrize("side", [1, -1])
def test_daily_wick_refreshes_extreme_even_when_close_moves_against_position(side):
    d, h = path(side, 5)
    column = "high" if side == 1 else "low"
    d.loc[2, column] = d.loc[1, column] + side
    d.loc[2, "close"] = d.loc[1, "close"] - side * 2.0
    d.loc[3, column] = d.loc[2, column]  # Equal wick does not refresh.
    d.loc[3, "close"] = d.loc[2, "close"] + side
    d.loc[4, column] = d.loc[2, column] - side
    d.loc[4, "close"] = d.loc[3, "close"] + side
    _, _, _, stops, _ = simulate(d, h)
    assert stops.new_extreme.iloc[2]
    assert stops.no_new_extreme_days.iloc[2:5].tolist() == [0, 1, 2]
    assert stops.new_mult.tolist() == pytest.approx([1.5, 1.5, 1.5, 1.5, 1.3])
    assert stops.extreme_day.iloc[-1] == ZERO + pd.Timedelta(days=2)


@pytest.mark.parametrize("side", [1, -1])
def test_pre_entry_extreme_is_excluded_from_holding_progress(side):
    d, h = path(side, 3)
    column = "high" if side == 1 else "low"
    d.loc[0, column] = 10000.0 if side == 1 else 0.01
    d.loc[2, column] = d.loc[1, column] + side
    _, _, _, stops, _ = simulate(d, h)
    assert stops.extreme_price.iloc[1] == d.loc[1, column]
    assert stops.extreme_price.iloc[2] == d.loc[2, column]
    assert stops.no_new_extreme_days.iloc[2] == 0


@pytest.mark.parametrize("side", [1, -1])
def test_delayed_entry_skips_partial_day_including_pre_entry_hour_wick(side):
    d, h = path(side, 5)
    column = "high" if side == 1 else "low"
    d.loc[1, column] = 10000.0 if side == 1 else 0.01
    h.loc[0, column] = d.loc[1, column]
    _, trades, _, stops, _ = simulate(d, h, delay_hours=1)
    assert trades.iloc[0].entry_time == ZERO + pd.Timedelta(days=1, hours=1)
    assert not stops.full_holding_day.iloc[1]
    assert not stops.initialized.iloc[1]
    assert stops.initialized.iloc[2]
    assert stops.extreme_price.iloc[2] == d.loc[2, column]
    assert stops.no_new_extreme_days.iloc[2:5].tolist() == [0, 1, 2]
    assert stops.new_mult.tolist() == pytest.approx([1.5, 1.5, 1.5, 1.5, 1.3])


@pytest.mark.parametrize("side", [1, -1])
def test_arming_ignores_profit_and_never_disarms_on_new_extreme(side):
    d, h = path(side, 8)
    column = "high" if side == 1 else "low"
    d.loc[1:, "close"] = 100.0 - side  # A losing position is still tightened.
    d.loc[4:, column] = d.loc[1, column] + side * 10.0
    _, trades, _, stops, _ = simulate(d, h, fee=0.0005, slip=0.0003)
    assert not stops.profit_eligible.iloc[3]
    assert stops.new_mult.iloc[3:8].tolist() == pytest.approx([1.3, 1.1, 0.9, 0.7, 0.5])
    assert stops.new_extreme.iloc[4]
    assert stops.no_new_extreme_days.iloc[4] == 0
    assert stops.new_armed.iloc[3:].all()
    assert trades.iloc[0].stop_floor_reached


@pytest.mark.parametrize("side", [1, -1])
def test_progress_rule_replaces_old_profit_stall_rule_even_when_ma_keeps_advancing(side):
    d, h = path(side, 5)
    d.loc[1:, "ma"] = [100.0 + side * k for k in range(1, len(d))]
    _, _, _, stops, _ = simulate(d, h)
    assert not stops.stalled.iloc[3]
    assert stops.new_mult.iloc[3] == 1.3
    # Conversely an old-rule profitable stall does not tighten before N days.
    d.loc[1:, "ma"] = 100.0
    _, _, _, stops, _ = simulate(d, h)
    assert stops.stalled.iloc[1]
    assert stops.profit_eligible.iloc[1]
    assert stops.new_mult.iloc[1:3].tolist() == [1.5, 1.5]


@pytest.mark.parametrize("side", [1, -1])
def test_extreme_stop_anchor_activates_only_after_arming(side):
    d, h = path(side, 5)
    _, _, _, stops, _ = simulate(d, h, stop_anchor="extreme")
    assert stops.new_stop.iloc[:3].tolist() == [100.0 - side * 15.0] * 3
    extreme = 100.0 + side * 15.0
    assert stops.new_stop.iloc[3] == pytest.approx(extreme - side * 13.0)
    assert stops.anchor_decisive.iloc[3]
    assert stops.anchor_candidate.iloc[3] == pytest.approx(extreme - side * 13.0)


@pytest.mark.parametrize("side", [1, -1])
def test_extreme_anchor_keeps_old_stop_when_atr_expands(side):
    d, h = path(side, 5)
    d.loc[4, "atr"] = 30.0
    _, _, _, stops, _ = simulate(d, h, stop_anchor="extreme")
    assert stops.new_mult.iloc[3:5].tolist() == [1.3, 1.1]
    assert stops.new_stop.iloc[4] == stops.new_stop.iloc[3]
    assert (side * (stops.new_stop - stops.old_stop) >= 0).all()


@pytest.mark.parametrize("side", [1, -1])
def test_new_extreme_anchor_across_open_fills_at_open_not_candidate(side):
    d, h = path(side, 5)
    column = "high" if side == 1 else "low"
    d.loc[3, column] = d.loc[1, column]  # Arm on the second unchanged day.
    price = 100.0 + side * 10.0
    h.loc[72, ["open", "high", "low", "close"]] = [100.0, max(price, 100.0), min(price, 100.0), 100.0]
    _, trades, _, stops, _ = simulate(d, h, stop_anchor="extreme", slip=0.0003)
    assert stops.new_stop.iloc[-1] == pytest.approx(100.0 + side * 2.0)
    assert len(trades) == 1
    assert trades.iloc[0].exit_reason == "stop_gap"
    assert trades.iloc[0].exit_reference == 100.0
    assert trades.iloc[0].exit_price == pytest.approx(100.0 * (1 - side * 0.0003))
    assert trades.iloc[0].exit_reference != stops.new_stop.iloc[-1]


@pytest.mark.parametrize("side", [1, -1])
def test_opposite_cross_exits_next_open_and_cannot_reenter_same_signal(side):
    d, h = path(side, 4)
    d.loc[2, ["cross", "slope", "close"]] = [-side, -side * 0.1, 100.0 - side]
    _, trades, _, _, _ = simulate(d, h, exit_opposite_cross=True)
    assert len(trades) == 1
    assert trades.iloc[0].exit_reason == "opposite_cross"
    assert trades.iloc[0].exit_time == ZERO + pd.Timedelta(days=3)
    assert trades.iloc[0].exit_reference == h.open.iloc[48]


@pytest.mark.parametrize("side", [1, -1])
def test_stop_gap_precedes_opposite_cross_exit(side):
    d, h = path(side, 4)
    d.loc[2, ["cross", "slope", "close"]] = [-side, -side * 0.1, 100.0 - side]
    gap = 100.0 - side * 25.0
    h.loc[48, ["open", "high", "low", "close"]] = [gap, gap + 0.1, gap - 0.1, gap]
    _, trades, _, _, _ = simulate(d, h, exit_opposite_cross=True)
    assert len(trades) == 1
    assert trades.iloc[0].exit_reason == "stop_gap"
    assert trades.iloc[0].exit_reference == gap


@pytest.mark.parametrize("side", [1, -1])
def test_initial_cap_uses_adverse_entry_fill_and_leaves_position_size_unchanged(side):
    d, h = path(side, 2)
    d["ma"] = 100.0 - side * 20.0
    free = simulate(d, h, fee=0.0005, slip=0.0003)
    capped = simulate(d, h, fee=0.0005, slip=0.0003, initial_stop_cap_pct=0.10)
    t = capped[1].iloc[0]
    fill = 100.0 * (1 + side * 0.0003)
    expected_stop = fill * (1 - side * 0.10)
    assert t.entry_price == pytest.approx(fill)
    assert t.initial_stop == pytest.approx(expected_stop)
    assert t.uncapped_initial_stop == pytest.approx(100.0 - side * 35.0)
    assert t.initial_stop_risk_pct == pytest.approx(10.0)
    assert t.cap_applied
    assert t.qty == free[1].iloc[0].qty
    assert t.entry_fee == free[1].iloc[0].entry_fee
    assert capped[0]["ending_equity"] == free[0]["ending_equity"]
    assert capped[0]["ending_equity"] == pytest.approx(10000.0 + capped[1].net_pnl.sum())


@pytest.mark.parametrize("side", [1, -1])
def test_cap_cannot_admit_an_entry_whose_original_stop_is_on_wrong_side(side):
    d, h = path(side, 2)
    d.loc[0, "ma"] = 100.0 + side * 20.0
    summary, trades, _, stops, _ = simulate(d, h, initial_stop_cap_pct=0.10)
    assert summary["trades"] == 0
    assert trades.empty
    assert stops.empty


def test_new_entry_resets_extreme_counter_multiplier_and_arming():
    d, h = path(1, 7)
    h.loc[72, ["open", "high", "low", "close"]] = [80.0, 80.1, 79.9, 80.0]
    d.loc[4, ["cross", "slope"]] = [1, 0.1]
    _, trades, _, stops, _ = simulate(d, h)
    assert len(trades) == 2
    assert trades.iloc[0].armed
    second = stops[stops.trade_id == 2]
    assert second.iloc[0].new_mult == 1.5
    assert not second.iloc[0].new_armed
    assert not second.iloc[0].initialized
    assert second.iloc[1].no_new_extreme_days == 0
    assert second.iloc[1].extreme_day == ZERO + pd.Timedelta(days=5)


def test_stop_reversal_resets_progress_and_skips_its_partial_entry_day():
    d, h = path(1, 6)
    d.loc[2, ["cross", "slope", "close"]] = [-1, -0.1, 90.0]
    d.loc[3, "low"] = 0.01  # The reversal does not own this whole daily bar.
    h.loc[48:, ["open", "high", "low", "close"]] = [80.0, 80.1, 79.9, 80.0]
    _, trades, _, stops, _ = simulate(d, h, reverse=True, progress_days=1)
    assert len(trades) == 2
    assert trades.iloc[0].stop_mult == 1.3
    assert trades.iloc[1].entry_reason == "stop_reversal"
    assert trades.iloc[1].entry_time == ZERO + pd.Timedelta(days=3, hours=1)
    second = stops[stops.trade_id == 2].reset_index(drop=True)
    assert second.iloc[0].new_mult == 1.5
    assert not second.iloc[0].new_armed
    assert not second.iloc[1].initialized
    assert not second.iloc[1].full_holding_day
    assert second.iloc[2].initialized
    assert second.iloc[2].extreme_price == d.loc[4, "low"]
    assert second.iloc[2].no_new_extreme_days == 0


def test_opposite_exit_blocks_only_its_consumed_signal_and_allows_a_later_cross():
    d, h = path(1, 6)
    d.loc[2, ["cross", "slope", "close"]] = [-1, -0.1, 99.0]
    d.loc[4, ["cross", "slope", "close"]] = [-1, -0.1, 99.0]
    _, trades, _, _, _ = simulate(d, h, exit_opposite_cross=True)
    assert len(trades) == 2
    assert trades.iloc[0].exit_time == ZERO + pd.Timedelta(days=3)
    assert trades.iloc[1].entry_time == ZERO + pd.Timedelta(days=5)
    assert trades.iloc[1].side == -1


@pytest.mark.parametrize("side", [1, -1])
def test_initial_cap_does_not_loosen_an_already_closer_ma_stop(side):
    d, h = path(side, 2)
    d.loc[0, "ma"] = 100.0 + side * 8.0
    _, trades, _, stops, _ = simulate(d, h, initial_stop_cap_pct=0.10)
    assert not trades.iloc[0].cap_applied
    assert stops.new_stop.iloc[0] == 100.0 - side * 7.0


@pytest.mark.parametrize("anchor", ["ma", "extreme"])
def test_unclosed_daily_wicks_cannot_change_still_open_position_history(anchor):
    d, h = path(1, 5)
    changed = d.copy(deep=True)
    changed.loc[5:, ["high", "low", "close", "ma", "atr", "cross", "slope"]] = [99999.0, 0.001, 1000.0, 9000.0, 0.001, -1, -9.0]
    baseline = simulate(d, h, stop_anchor=anchor)
    altered = simulate(changed, h, stop_anchor=anchor)
    assert baseline[0] == altered[0]
    assert baseline[1].iloc[-1].exit_reason == "sample_end"
    for before, after in zip(baseline[1:], altered[1:]):
        pd.testing.assert_frame_equal(before, after, check_exact=True)


def test_exit_day_extreme_and_future_daily_bars_cannot_change_executed_history():
    d, h = path(1, 4)
    h.loc[48, ["open", "high", "low", "close"]] = [80.0, 80.1, 79.9, 80.0]
    changed = d.copy(deep=True)
    changed.loc[3:, ["high", "low", "close", "ma", "atr", "cross", "slope"]] = [99999.0, 0.001, 1000.0, 9000.0, 0.001, 0, 9.0]
    baseline = simulate(d, h)
    altered = simulate(changed, h)
    assert baseline[0] == altered[0]
    for before, after in zip(baseline[1:], altered[1:]):
        pd.testing.assert_frame_equal(before, after, check_exact=True)


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("mode", ["fixed", "stall_only", "armed_daily"])
def test_r3_disabled_controls_reproduce_every_r2_output_exactly(side, mode):
    d, h = path(side, 7)
    settings = dict(fee=0.0005, slip=0.0003, short_exit="none", reverse=False,
                    entry_mode="original", tighten_mode=mode)
    before = r2.simulate(h, d, r2.Config(**settings))
    after = engine.simulate(h, d, engine.Config(**settings))
    for key, value in before[0].items():
        if key != "name":
            assert after[0][key] == value, key
    for old, new in zip(before[1:], after[1:]):
        pd.testing.assert_frame_equal(old, new[old.columns], check_exact=True)


@pytest.mark.parametrize("settings", [
    {"progress_days": -1}, {"progress_days": 1.5}, {"progress_days": True},
    {"stop_anchor": "close"}, {"progress_days": 0, "stop_anchor": "extreme"},
    {"initial_stop_cap_pct": 0}, {"initial_stop_cap_pct": 1},
])
def test_invalid_r3_parameters_are_rejected(settings):
    with pytest.raises(ValueError):
        cfg(**settings)
