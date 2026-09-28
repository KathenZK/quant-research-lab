"""Synthetic causal and accounting controls for the four-question kernel.

No historical market backtest is rerun: v1 comparison uses generated candles.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, version):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / f"research/_shared-kernels/ma7-cross-atr-ratchet/{version}/engine.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


new = load("ma7_car_four_tests_v2", "v2")
old = load("ma7_car_four_tests_v1", "v1")
ZERO = pd.Timestamp("2026-01-01", tz="UTC")


def path(side=1, count=17):
    price = 100.0 + side * 10
    d = pd.DataFrame({
        "timestamp": pd.date_range(ZERO, periods=count + 2, freq="D"),
        "open": price, "close": price, "high": price + 5, "low": price - 5,
        "ma": 100.0, "atr": 10.0, "rsi": 50.0, "slope": 0.0,
        "cross": 0, "ready": True, "accel1": False, "accel2": False,
        "ma30": 100.0, "prev_ma30": 100.0 - side,
    })
    d.loc[0, ["cross", "slope"]] = [side, side * .1]
    h = pd.DataFrame({
        "timestamp": pd.date_range(ZERO + pd.Timedelta(days=1), periods=count * 24, freq="h"),
        "open": price, "close": price, "high": price + .1, "low": price - .1,
    })
    return d, h


def config(**changes):
    return new.Config(**{"reverse": False, "short_exit": "none", "progress_days": 4,
                         "entry_wait_days": 0, **changes})


def run(d, h, **changes):
    events = []
    result = new.simulate(h, d, config(**changes), entry_events=events)
    return (*result, events)


def assert_legacy_equal(before, after):
    for key, value in before[0].items():
        assert after[0][key] == value, key
    for left, right in zip(before[1:], after[1:5]):
        pd.testing.assert_frame_equal(left, right[left.columns], check_exact=True)


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("delay", [0, 1])
@pytest.mark.parametrize("settings", [
    {}, {"progress_days": 4}, {"progress_days": 3, "progress_source": "close"},
    {"tighten_mode": "stall_only"}, {"tighten_mode": "armed_daily"},
    {"progress_days": 4, "stop_anchor": "extreme"}, {"initial_stop_cap_pct": .1},
])
def test_new_defaults_preserve_old_five_outputs_exactly(side, delay, settings):
    d, h = path(side)
    funds = pd.DataFrame({
        "timestamp": [ZERO + pd.Timedelta(days=3), ZERO + pd.Timedelta(days=5, minutes=7)],
        "funding_rate": [.0001, -.0002], "mark_price": [100., np.nan],
    })
    opts = {"reverse": False, "short_exit": "none", "delay_hours": delay, **settings}
    for funding, carry in [(None, 0.), (funds, .0005)]:
        before = old.simulate(h, d, old.Config(**opts), funding=funding, carry_daily=carry)
        after = new.simulate(h, d, new.Config(**opts), funding=funding, carry_daily=carry)
        assert_legacy_equal(before, after)


def generated_ohlc(count=180):
    rng = np.random.default_rng(71029)
    close = 100 * np.exp(np.cumsum(rng.normal(0, .07, count)))
    opening = np.r_[100., close[:-1]]
    dates = pd.date_range(ZERO, periods=count, freq="D")
    daily = pd.DataFrame({"timestamp": dates, "open": opening, "close": close,
                          "high": np.maximum(opening, close) * 1.01,
                          "low": np.minimum(opening, close) * .99})
    frames = []
    for i in range(count):
        p = np.linspace(opening[i], close[i], 25)
        frames.append(pd.DataFrame({"timestamp": pd.date_range(dates[i], periods=24, freq="h"),
                                    "open": p[:-1], "close": p[1:],
                                    "high": np.maximum(p[:-1], p[1:]) * 1.005,
                                    "low": np.minimum(p[:-1], p[1:]) * .995}))
    return daily, pd.concat(frames, ignore_index=True)


@pytest.mark.parametrize("opts", [{}, {"reverse": False, "progress_days": 4},
                                   {"entry_wait_days": 3, "progress_days": 4},
                                   {"entry_mode": "absolute_slowdown", "tighten_mode": "stall_only"}])
def test_generated_multi_trade_account_and_old_features_remain_exact(opts):
    d, h = generated_ohlc()
    old_features, new_features = old.features(d), new.features(d)
    pd.testing.assert_frame_equal(old_features, new_features[old_features.columns], check_exact=True)
    before = old.simulate(h, old_features, old.Config(**opts))
    after = new.simulate(h, new_features, new.Config(**opts))
    assert before[0]["trades"] > 4
    assert_legacy_equal(before, after)


@pytest.mark.parametrize("side,mode", [(1, "short"), (-1, "long")])
def test_direction_rejects_entry_without_rewriting_raw_cross(side, mode):
    d, h = path(side)
    result = run(d, h, direction_mode=mode)
    assert result[0]["trades"] == 0
    assert result[0]["direction_rejected"] == 1
    assert result[0]["flat_ready_crosses"] == 1
    assert result[5][0]["cross"] == side
    assert d.cross.iloc[0] == side
    assert result[5][0]["reason"] == "direction_rejected"


@pytest.mark.parametrize("side,mode", [(1, "long"), (-1, "short")])
def test_allowed_direction_still_uses_next_open(side, mode):
    d, h = path(side)
    result = run(d, h, direction_mode=mode)
    assert result[1].side.tolist() == [side]
    assert result[1].entry_time.iloc[0] == ZERO + pd.Timedelta(days=1)


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("bad", ["ma_equal", "slope_equal", "ma_wrong", "slope_wrong"])
def test_ma30_direction_requires_two_strict_comparisons(side, bad):
    d, h = path(side)
    if bad == "ma_equal":
        d.loc[0, "ma30"] = d.close.iloc[0]
        d.loc[0, "prev_ma30"] = d.ma30.iloc[0] - side
    elif bad == "slope_equal":
        d.loc[0, "prev_ma30"] = d.ma30.iloc[0]
    elif bad == "ma_wrong":
        d.loc[0, "ma30"] = d.close.iloc[0] + side
        d.loc[0, "prev_ma30"] = d.ma30.iloc[0] - side
    else:
        d.loc[0, "prev_ma30"] = d.ma30.iloc[0] + side
    result = run(d, h, trend_filter="ma30_direction")
    assert result[0]["ma30_direction_rejected"] == 1
    assert result[0]["trades"] == 0
    assert result[5][0]["signal_day"] == ZERO


@pytest.mark.parametrize("side", [1, -1])
def test_ma30_ready_control_does_not_apply_direction(side):
    d, h = path(side)
    d["ma30"] = d.close + side
    d["prev_ma30"] = d.ma30 + side
    result = run(d, h, trend_filter="ma30_ready")
    assert result[0]["trades"] == 1


@pytest.mark.parametrize("side", [1, -1])
def test_ma30_filter_only_controls_new_entry_and_does_not_reuse_rejection(side):
    d, h = path(side)
    d.loc[1:, "prev_ma30"] = 100 + side
    result = run(d, h, trend_filter="ma30_direction")
    assert result[1].exit_reason.tolist() == ["sample_end"]
    d.loc[0, "prev_ma30"] = 100 + side
    d.loc[1:, "prev_ma30"] = 100 - side
    result = run(d, h, trend_filter="ma30_direction")
    assert result[0]["trades"] == 0
    assert len(result[5]) == 1


def test_ma30_requires_31_closed_days_without_shifting_old_account_window():
    d, h = generated_ohlc(40)
    f = new.features(d)
    assert f.ready.iloc[28]
    assert not f.ma30_ready.iloc[29]
    assert f.ma30_ready.iloc[30]
    f["cross"] = 0
    f["slope"] = .1
    f.loc[[28, 29, 30], "cross"] = 1
    # Make all attempted stops valid without changing MA30 readiness.
    f["ma"] = 1.
    f["atr"] = .1
    events = []
    result = new.simulate(h, f, config(trend_filter="ma30_ready"), entry_events=events)
    assert pd.Timestamp(result[0]["start"]) == ZERO + pd.Timedelta(days=29)
    assert result[0]["ma30_not_ready_rejected"] == 2
    assert result[1].signal_day.iloc[0] == ZERO + pd.Timedelta(days=30)
    assert result[1].entry_time.iloc[0] == ZERO + pd.Timedelta(days=31)
    assert [e["status"] for e in events] == ["rejected", "rejected", "filled"]


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("slip", [.0003, .001])
def test_risk_budget_includes_stop_slippage_and_both_fees(side, slip):
    d, h = path(side)
    stop = 100 - side * 15
    h.loc[1, "low" if side == 1 else "high"] = stop
    result = run(d, h, risk_fraction=.005, slip=slip)
    p = result[1].iloc[0]
    fill = (100 + side * 10) * (1 + side * slip)
    stop_fill = stop * (1 - side * slip)
    unit_risk = side * (fill - stop_fill) + .0005 * (fill + stop_fill)
    assert p.qty == min(50 / unit_risk, 10000 / (fill * 1.0005))
    assert p.initial_planned_risk == pytest.approx(50.)
    assert p.initial_planned_risk_pct == pytest.approx(.5)
    assert p.net_pnl == pytest.approx(-50.)
    assert p.exit_reason == "stop_intrahour"
    assert result[5][0]["attempt_before_equity"] == 10000.
    assert result[5][0]["initial_stop_fill"] == stop_fill


@pytest.mark.parametrize("side", [1, -1])
def test_risk_sizing_honors_notional_cap_for_very_close_stop(side):
    d, h = path(side)
    d["ma"] = 100 + side * 10
    d["atr"] = .01
    p = run(d, h, risk_fraction=.005)[1].iloc[0]
    assert p.qty == p.qty_cap
    assert p.initial_planned_risk_pct < .5
    assert p.qty * p.entry_price * 1.0005 == pytest.approx(10000.)


@pytest.mark.parametrize("side", [1, -1])
def test_simple_small_position_changes_quantity_only(side):
    d, h = path(side)
    full = run(d, h)[1].iloc[0]
    small = run(d, h, notional_fraction=1 / 30)[1].iloc[0]
    assert small.qty == pytest.approx(full.qty / 30)
    for col in ["entry_time", "exit_time", "entry_price", "exit_price", "initial_stop", "exit_reason"]:
        assert small[col] == full[col]
    assert small.initial_planned_risk == pytest.approx(full.initial_planned_risk / 30)


@pytest.mark.parametrize("side", [1, -1])
def test_gap_loss_can_exceed_initial_budget(side):
    d, h = path(side)
    gap = 75 if side == 1 else 125
    h.loc[1, ["open", "high", "low", "close"]] = [gap, gap + .1, gap - .1, gap]
    p = run(d, h, risk_fraction=.005)[1].iloc[0]
    assert p.initial_planned_risk_pct == pytest.approx(.5)
    assert p.return_on_entry_equity < -.005
    assert p.exit_reason == "stop_gap"


@pytest.mark.parametrize("side", [1, -1])
def test_invalid_initial_gap_consumes_signal_and_logs_rejection(side):
    d, h = path(side)
    gap = 80 if side == 1 else 120
    h.loc[0, ["open", "high", "low", "close"]] = [gap, gap + .1, gap - .1, gap]
    result = run(d, h, risk_fraction=.005)
    assert result[0]["invalid_stop_rejected"] == 1
    assert result[0]["trades"] == 0
    assert len(result[5]) == 1


@pytest.mark.parametrize("side", [1, -1])
def test_reset_waits_four_new_stale_days_and_never_restores_multiplier(side):
    d, h = path(side)
    col = "high" if side == 1 else "low"
    d.loc[6:, col] += side
    result = run(d, h, progress_policy="reset_on_new_extreme")
    stops = result[3].set_index("signal_day")
    at = lambda day: stops.loc[ZERO + pd.Timedelta(days=day)]
    assert at(1).no_new_extreme_days == 0
    assert not at(4).new_armed
    assert at(5).new_mult == 1.3
    assert at(5).new_armed
    assert at(6).armed_reset
    assert not at(6).new_armed
    assert pd.isna(at(6).arm_day)
    assert at(6).new_mult == 1.3
    assert at(9).new_mult == 1.3
    assert at(10).new_mult == 1.1
    assert at(10).new_armed
    p = result[1].iloc[0]
    assert p.first_arm_day == ZERO + pd.Timedelta(days=5)
    assert p.arm_count == 2
    assert p.reset_count == 1
    assert p.ever_armed
    assert ((result[3].new_stop - result[3].old_stop) * side >= 0).all()
    assert (result[3].new_mult <= result[3].old_mult).all()
    assert result[0]["ever_armed_trades"] == 1


@pytest.mark.parametrize("side", [1, -1])
def test_reset_still_records_new_extreme_at_floor(side):
    d, h = path(side, 12)
    col = "high" if side == 1 else "low"
    d.loc[10:, col] += side
    result = run(d, h, progress_policy="reset_on_new_extreme")
    s = result[3].set_index("signal_day").loc[ZERO + pd.Timedelta(days=10)]
    assert s.old_mult == .5 and s.new_mult == .5
    assert s.armed_reset and not s.new_armed
    assert pd.isna(s.arm_day)
    assert result[0]["armed_trades"] == 0
    assert result[0]["ever_armed_trades"] == 1
    assert result[0]["reset_count"] == 1


@pytest.mark.parametrize("side", [1, -1])
def test_partial_holding_day_is_not_used_for_extreme_initialization(side):
    d, h = path(side)
    result = run(d, h, delay_hours=1, progress_policy="reset_on_new_extreme")
    assert result[3].tightening_trigger.iloc[1] == "partial_entry_day"
    assert result[3].extreme_day.iloc[2] == ZERO + pd.Timedelta(days=2)
    first_tight = result[3].loc[result[3].tightened].iloc[0]
    assert first_tight.signal_day == ZERO + pd.Timedelta(days=6)
    assert first_tight.timestamp == ZERO + pd.Timedelta(days=7)


def test_occupied_cross_and_exit_day_cross_are_not_filter_rejections():
    d, h = path(-1)
    d.loc[1, ["cross", "slope"]] = [1, .1]
    d.loc[2, ["cross", "slope", "close", "rsi", "accel1"]] = [1, .1, 88., 20., True]
    result = run(d, h, direction_mode="short", short_exit="accel1_rsi30")
    assert result[1].exit_reason.tolist() == ["accel1_rsi30"]
    assert result[0]["direction_rejected"] == 0
    assert result[0]["flat_ready_crosses"] == 1
    assert len(result[5]) == 1


def test_first_failure_slope_then_direction_then_ma30_and_entry_count_reconciliation():
    d, h = path(1)
    d.loc[0, "slope"] = .05
    d.loc[1, ["cross", "slope"]] = [1, .1]
    d.loc[2, ["cross", "slope"]] = [-1, -.1]
    d.loc[2, "ma30"] = np.nan
    result = run(d, h, direction_mode="short", trend_filter="ma30_ready")
    summary, events = result[0], result[5]
    assert [e["reason"] for e in events] == ["slope_rejected", "direction_rejected", "ma30_not_ready_rejected"]
    assert summary["flat_ready_crosses"] == 3
    assert summary["entry_attempts"] == 2
    assert summary["entry_fills"] == 0


def test_negative_initial_stop_is_flagged_without_new_rejection():
    d, h = path(1)
    d["atr"] = 100.
    result = run(d, h)
    assert result[0]["trades"] == 1
    assert result[1].initial_stop_price_nonpositive.iloc[0]
    assert result[5][0]["initial_stop_price_nonpositive"]


@pytest.mark.parametrize("changes", [
    {"direction_mode": "net"}, {"trend_filter": "ma20"}, {"risk_fraction": 0},
    {"risk_fraction": np.nan}, {"risk_fraction": 1.1}, {"notional_fraction": 0},
    {"notional_fraction": np.inf}, {"notional_fraction": 1.1}, {"progress_policy": "restore"},
])
def test_invalid_new_configuration_is_rejected(changes):
    with pytest.raises(ValueError):
        new.Config(**changes)


def test_short_tp_toggle_changes_actual_account_exit_not_only_reporting():
    d, h = path(-1)
    d.loc[1, ["close", "rsi", "accel1"]] = [88., 30., True]
    with_tp = run(d, h, direction_mode="short", short_exit="accel1_rsi30")
    without_tp = run(d, h, direction_mode="short", short_exit="none")
    assert with_tp[1].exit_reason.tolist() == ["accel1_rsi30"]
    assert with_tp[1].exit_time.iloc[0] == ZERO + pd.Timedelta(days=2)
    assert without_tp[1].exit_reason.tolist() == ["sample_end"]
    assert with_tp[0]["short_tp_exits"] == 1
    assert without_tp[0]["short_tp_exits"] == 0


@pytest.mark.parametrize("failed", ["rsi", "acceleration", "profit"])
def test_accelerated_short_tp_requires_each_condition(failed):
    d, h = path(-1)
    d.loc[1, ["close", "rsi", "accel1"]] = [88., 30., True]
    if failed == "rsi":
        d.loc[1, "rsi"] = 30.00001
    elif failed == "acceleration":
        d.loc[1, "accel1"] = False
    else:
        d.loc[1, "close"] = 90.
    result = run(d, h, short_exit="accel1_rsi30")
    assert result[0]["short_tp_exits"] == 0


@pytest.mark.parametrize("side", [1, -1])
def test_future_carry_is_excluded_from_initial_budget_but_charged_to_realized_loss(side):
    d, h = path(side)
    stop = 100 - side * 15
    h.loc[2, "low" if side == 1 else "high"] = stop
    events = []
    result = new.simulate(h, d, config(risk_fraction=.005), carry_daily=.0005, entry_events=events)
    p = result[1].iloc[0]
    assert p.initial_planned_risk == pytest.approx(50.)
    assert p.net_pnl < -50.
    assert p.carry_paid > 0
    assert p.net_pnl == pytest.approx(-50. - p.carry_paid)


def test_ma30_is_causal_under_future_close_changes():
    d, _ = generated_ohlc(60)
    before = new.features(d)
    changed = d.copy()
    changed.loc[40:, "close"] *= 10
    after = new.features(changed)
    pd.testing.assert_frame_equal(before.iloc[:40], after.iloc[:40], check_exact=True)
