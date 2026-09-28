"""Independent synthetic checks of the fixed S1/S2/S3 exit contract.

No lake, historical runner, or strategy search is used. Direct transition
checks specify outcomes from the contract; integration checks additionally
verify money, causal timing, default compatibility and irreversible stops.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
ZERO = pd.Timestamp("2026-01-01", tz="UTC")


def load(version):
    name = f"ma7_exit_independent_{version}"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / f"research/_shared-kernels/ma7-cross-atr-ratchet/{version}/engine.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


new, old = load("v3"), load("v2")


def config(policy="defense", **kw):
    return new.Config(**{"reverse": False, "progress_days": 4,
                         "short_exit": "none" if policy == "extension" else "accel1_rsi30",
                         "exit_state_policy": policy, **kw})


def position(side=1, reference=100., fill=None, extreme=None, stale=0):
    return {"side": side, "entry_reference": reference,
            "entry_price": reference if fill is None else fill,
            "extreme_price": reference if extreme is None else extreme,
            "no_new_extreme_days": stale}


def point(side=1, day=1, close=3., ma=0., atr=10., high=None, low=None,
          delta=1., previous_delta=0., previous_atr=10., previous_atr2=10., rsi=50.):
    # Inputs are favorable-direction offsets, so reflection covers long/short.
    high = close + .1 if high is None else high
    low = close - .1 if low is None else low
    return SimpleNamespace(
        timestamp=ZERO + pd.Timedelta(days=day), close=100. + side * close,
        ma=100. + side * ma, atr=atr,
        high=100. + (high if side == 1 else -low),
        low=100. + (low if side == 1 else -high),
        sm_delta=side * delta, sm_previous_delta=side * previous_delta,
        sm_previous_atr=previous_atr, sm_previous_atr2=previous_atr2,
        rsi=rsi if side == 1 else 100. - rsi)


def step(p, row, policy="extension", *, extreme=None, stale=None):
    """Supply the already-updated V3 high/low counter expected by the API."""
    if extreme is not None:
        p["extreme_price"] = extreme
    else:
        observed = row.high if p["side"] == 1 else row.low
        p["extreme_price"] = (max if p["side"] == 1 else min)(p["extreme_price"], observed)
    if stale is not None:
        p["no_new_extreme_days"] = stale
    return new.exit_state_step(p, row, policy)


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("gap,expected", [(1.25 - 1e-8, False), (1.25, True), (1.25 + 1e-8, True)])
def test_defense_retrace_threshold_is_inclusive_and_symmetric(side, gap, expected):
    p = position(side)
    r = point(side, close=5., atr=8.)
    got = step(p, r, "defense", extreme=r.close + side * gap * 8.)
    assert got["sm_large_retrace"] is expected
    assert got["sm_defense"] is expected
    assert got["sm_defensive_stop"] == (r.close - side * 4. if expected else None)


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("close,ma,expected", [(0., 0., True), (-1., 0., True),
    (0., -1., False), (1., 1., False)])
def test_failed_cross_requires_wrong_or_equal_ma_and_nonpositive_price_pnl(side, close, ma, expected):
    p = position(side)
    r = point(side, close=close, ma=ma, high=max(close, 0.))
    got = step(p, r, "defense")
    assert got["sm_failed_cross"] is expected


@pytest.mark.parametrize("side", [1, -1])
def test_three_real_held_closes_start_from_entry_reference_not_fill_or_prior_close(side):
    p = position(side, reference=100., fill=100. + side * .04)
    for day, close in enumerate([2., 1., 3.], 1):
        got = step(p, point(side, day, close=close, atr=6., high=7.5), "trend")
        if day < 3:
            assert not got["sm_ready3"]
            assert np.isnan(got["sm_efficiency3"])
            assert not got["sm_healthy"]
    assert got["sm_held_days"] == 3
    assert got["sm_efficiency3"] == pytest.approx(.6)
    assert got["sm_speed3"] == pytest.approx(.5)
    assert got["sm_healthy"]
    assert p["_sm_closes"][0] == 100.


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("condition", ["all_equal", "efficiency_below", "speed_below", "ma_equal", "retrace_above"])
def test_healthy_thresholds_and_ma_strictness(side, condition):
    p = position(side)
    close, atr, ma, high = 3., 6., 0., 7.5
    if condition == "efficiency_below":
        close -= 1e-7
    elif condition == "speed_below":
        atr += 1e-7
    elif condition == "ma_equal":
        ma = close
    elif condition == "retrace_above":
        high += 1e-7
    step(p, point(side, 1, close=2., atr=6., high=2.1), "trend")
    step(p, point(side, 2, close=1., atr=6., high=2.1), "trend")
    got = step(p, point(side, 3, close=close, atr=atr, ma=ma, high=high), "trend")
    assert got["sm_healthy"] is (condition == "all_equal")


@pytest.mark.parametrize("side", [1, -1])
def test_flat_efficiency_is_zero_not_healthy_and_chop_needs_three_stale_days(side):
    p = position(side)
    for day in range(1, 4):
        got = step(p, point(side, day, close=0., ma=-1., high=0.), "defense", stale=2)
    assert got["sm_flat3"] and got["sm_efficiency3"] == 0.
    assert not got["sm_healthy"] and not got["sm_chopped"]
    got = step(p, point(side, 4, close=0., ma=-1., high=0.), "defense", stale=3)
    assert got["sm_chopped"] and got["sm_defense"]


@pytest.mark.parametrize("side", [1, -1])
def test_rsi_extreme_without_acceleration_never_starts_watch(side):
    p = position(side)
    got = step(p, point(side, close=4., rsi=100., delta=1., previous_delta=2.))
    assert got["sm_extended"] and not got["sm_acceleration"]
    assert got["sm_watch"] == "NORMAL"
    assert not got["sm_protect"]


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("speed,previous,ma_dist,rsi,expected", [
    (10., 0., 20., 50., True),
    (10. - 1e-7, 0., 20., 50., False),
    (10., 10., 20., 50., False),
    (10., 0., 20. - 1e-7, 50., False),
    (10., 0., 10., 80., True),
    (10., 0., 10., 80. - 1e-7, False),
])
def test_watch_acceleration_and_extension_boundary(side, speed, previous, ma_dist, rsi, expected):
    p = position(side)
    got = step(p, point(side, close=30., ma=30. - ma_dist, delta=speed,
                        previous_delta=previous, rsi=rsi))
    assert (got["sm_watch"] == "WATCH") is expected


@pytest.mark.parametrize("side", [1, -1])
def test_watch_entering_day_is_not_protected_even_with_large_same_day_retrace(side):
    p = position(side)
    got = step(p, point(side, close=30., high=40., delta=10.))
    assert got["sm_watch"] == "WATCH"
    assert got["sm_transition"] == "watch_started"
    assert not got["sm_protect"] and got["sm_protection_stop"] is None
    assert got["sm_watch_atr"] == 10.


@pytest.mark.parametrize("side", [1, -1])
def test_watch_checks_protection_before_clearing_normalized_conditions(side):
    p = position(side)
    step(p, point(side, 1, close=30., high=30., delta=10.))
    got = step(p, point(side, 2, close=22.5, high=30., delta=-7.5, ma=10., rsi=50.))
    assert got["sm_ma_distance"] < 2.
    assert got["sm_watch"] == "PROTECT"
    assert got["sm_transition"] == "exhaustion_protect"
    assert got["sm_protection_stop"] == 100. + side * 20.


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("speed,giveback,expected", [(5., 7.5, True),
    (5. + 1e-7, 7.5, False), (5., 7.5 - 1e-7, False)])
def test_watch_both_decay_and_retrace_thresholds_are_inclusive(side, speed, giveback, expected):
    p = position(side)
    step(p, point(side, 1, close=30., high=30., delta=10.))
    got = step(p, point(side, 2, close=35., high=35. + giveback, delta=speed))
    assert got["sm_protect"] is expected


@pytest.mark.parametrize("side", [1, -1])
def test_atr_expansion_cannot_fake_watch_velocity_decay(side):
    p = position(side)
    step(p, point(side, 1, close=30., high=30., delta=10., atr=10.))
    got = step(p, point(side, 2, close=40., high=48., delta=10.,
                        atr=100., previous_atr=100., rsi=90.))
    assert got["sm_speed1"] == pytest.approx(.1)
    assert got["sm_watch_atr"] == 10.
    assert got["sm_peak_speed"] == 1.
    assert got["sm_watch"] == "WATCH" and not got["sm_protect"]


@pytest.mark.parametrize("side", [1, -1])
def test_protection_uses_watch_extreme_not_old_trade_extreme_and_frozen_atr(side):
    p = position(side, extreme=100. + side * 60.)
    started = step(p, point(side, 1, close=30., high=30., delta=10.))
    assert started["sm_watch_extreme"] == 100. + side * 30.
    got = step(p, point(side, 2, close=22.5, high=30., delta=-7.5,
                        atr=40., previous_atr=40.))
    assert got["sm_protection_stop"] == 100. + side * 20.
    assert got["sm_watch_atr"] == 10.
    assert got["sm_state"] == "PROTECT"


@pytest.mark.parametrize("side", [1, -1])
def test_watch_clears_only_after_no_protection_and_new_watch_resets_all_fields(side):
    p = position(side)
    step(p, point(side, 1, close=30., high=30., delta=10.))
    cleared = step(p, point(side, 2, close=34., high=34., delta=4., ma=20.))
    assert cleared["sm_transition"] == "watch_cleared"
    for key in ("sm_watch_start", "sm_watch_atr", "sm_watch_extreme", "sm_peak_speed"):
        assert cleared[key] is None
    started = step(p, point(side, 3, close=50., high=52., delta=16., atr=8., previous_atr=8.))
    assert started["sm_transition"] == "watch_started"
    assert started["sm_watch_start"] == ZERO + pd.Timedelta(days=3)
    assert started["sm_watch_atr"] == 8.
    assert started["sm_watch_extreme"] == 100. + side * 52.
    assert started["sm_peak_speed"] == 2.


@pytest.mark.parametrize("side", [1, -1])
def test_protect_is_absorbing_even_after_health_recovers(side):
    p = position(side)
    step(p, point(side, 1, close=30., high=30., delta=10.))
    step(p, point(side, 2, close=22., high=30., delta=-8.))
    got = step(p, point(side, 3, close=50., high=50., delta=28., ma=48., atr=20.))
    assert got["sm_watch"] == "PROTECT"
    assert got["sm_state"] == "PROTECT"
    assert got["sm_protection_stop"] == 100. + side * 40.


def generated_ohlc(count=180):
    rng = np.random.default_rng(88214)
    close = 100 * np.exp(np.cumsum(rng.normal(0, .065, count)))
    opening = np.r_[100., close[:-1]]
    dates = pd.date_range(ZERO, periods=count, freq="D")
    daily = pd.DataFrame({"timestamp": dates, "open": opening, "close": close,
                          "high": np.maximum(opening, close) * 1.005,
                          "low": np.minimum(opening, close) * .995})
    frames = []
    for i in range(count):
        p = np.linspace(opening[i], close[i], 25)
        frames.append(pd.DataFrame({"timestamp": pd.date_range(dates[i], periods=24, freq="h"),
            "open": p[:-1], "close": p[1:], "high": np.maximum(p[:-1], p[1:]) * 1.005,
            "low": np.minimum(p[:-1], p[1:]) * .995}))
    return daily, pd.concat(frames, ignore_index=True)


def assert_old_equal(before, after):
    for key, value in before[0].items():
        assert after[0][key] == value, key
    for left, right in zip(before[1:], after[1:5]):
        pd.testing.assert_frame_equal(left, right[left.columns], check_exact=True)


@pytest.mark.parametrize("opts", [{}, {"reverse": False, "progress_days": 4},
    {"entry_wait_days": 3, "progress_days": 4},
    {"entry_mode": "absolute_slowdown", "tighten_mode": "stall_only"},
    {"direction_mode": "short", "trend_filter": "ma30_direction"},
    {"risk_fraction": .005, "fee": .001, "slip": .0004},
    {"progress_days": 4, "progress_policy": "reset_on_new_extreme"}])
def test_v3_disabled_policy_preserves_all_v2_fields_exactly(opts):
    d, h = generated_ohlc()
    before_f, after_f = old.features(d), new.features(d)
    pd.testing.assert_frame_equal(before_f, after_f[before_f.columns], check_exact=True)
    funds = pd.DataFrame({"timestamp": [ZERO + pd.Timedelta(days=45),
        ZERO + pd.Timedelta(days=88, minutes=7)], "funding_rate": [.0001, -.0002],
        "mark_price": [100., np.nan]})
    for funding, carry in [(None, 0.), (funds, .0005)]:
        before = old.simulate(h, before_f, old.Config(**opts), funding=funding, carry_daily=carry)
        after = new.simulate(h, after_f, new.Config(**opts), funding=funding, carry_daily=carry)
        assert_old_equal(before, after)


def artificial_path(side=1, closes=(2., 2., 2., 2., 2., 2., 3., 6., 9., 12.),
                    favorable_high=8., ma_offset=-1., atr=10.):
    """Explicit closed-bar fixtures; prices and hourly execution agree on closes."""
    rows = []
    for i, close in enumerate([1., *closes, closes[-1]]):
        prior = 0. if i == 1 else (1. if i == 0 else closes[i-2])
        favorable = max(favorable_high, close, prior)
        adverse = min(close, prior) - .01
        rows.append({"timestamp": ZERO + pd.Timedelta(days=i),
            "open": 100. + side * prior, "close": 100. + side * close,
            "high": 100. + (favorable if side == 1 else -adverse),
            "low": 100. + (adverse if side == 1 else -favorable),
            "ma": 100. + side * ma_offset, "atr": atr, "rsi": 50.,
            "slope": side * .1 if i == 0 else 0., "cross": side if i == 0 else 0,
            "ready": True, "accel1": False, "accel2": False,
            "ma30": 100., "prev_ma30": 100.})
    d = pd.DataFrame(rows)
    frames = []
    for i in range(1, len(closes)+1):
        a, b = d.open.iloc[i], d.close.iloc[i]
        p = np.linspace(a, b, 25)
        f = pd.DataFrame({"timestamp": pd.date_range(ZERO + pd.Timedelta(days=i), periods=24, freq="h"),
            "open": p[:-1], "close": p[1:], "high": np.maximum(p[:-1], p[1:]) + .01,
            "low": np.minimum(p[:-1], p[1:]) - .01})
        f.loc[23, "high" if side == 1 else "low"] = d.high.iloc[i] if side == 1 else d.low.iloc[i]
        frames.append(f)
    return d, pd.concat(frames, ignore_index=True)


@pytest.mark.parametrize("side", [1, -1])
def test_healthy_pause_keeps_armed_and_cannot_restore_old_multiplier_or_stop(side):
    d, h = artificial_path(side)
    a = new.simulate(h, d, config("defense"))
    b = new.simulate(h, d, config("trend"))
    stops = b[3]
    paused = stops.loc[stops.tightening_trigger.eq("healthy_pause")]
    assert len(paused) > 0
    assert paused.new_armed.all()
    assert (paused.new_mult == paused.old_mult).all()
    assert (paused.new_mult < 1.5).all()
    assert ((stops.new_stop - stops.old_stop) * side >= 0).all()
    assert (stops.new_mult <= stops.old_mult).all()
    assert a[3].tightened.sum() > b[3].tightened.sum()


@pytest.mark.parametrize("side", [1, -1])
def test_defense_and_four_day_clock_same_day_decrease_only_once(side):
    d, h = artificial_path(side, closes=(2., 2., 2., 2., 2., 2.), favorable_high=8.)
    # At day 5 a changed ATR makes the existing high a 1.25ATR retrace.
    d.loc[5, "atr"] = 4.8
    result = new.simulate(h, d, config("defense"))
    at = result[3].set_index("signal_day").loc[ZERO + pd.Timedelta(days=5)]
    assert at.new_armed and at.sm_defense
    assert at.old_mult == 1.5 and at.new_mult == 1.3
    assert at.tightening_trigger == "state_defense"


@pytest.mark.parametrize("side", [1, -1])
def test_defense_closed_day_stop_is_next_day_effective_and_gap_uses_open(side):
    d, h = artificial_path(side, closes=(-1., -2., -2.), favorable_high=0., ma_offset=0.)
    # Day 1's later close creates a 94/106 stop; the day-1 wick crosses it
    # before the close but cannot execute a line not yet known.
    h.loc[5, "low" if side == 1 else "high"] = 100. - side * 10.
    day2 = h.timestamp.eq(ZERO + pd.Timedelta(days=2))
    h.loc[day2, ["open", "high", "low", "close"]] = 100. - side * 8.
    out = new.simulate(h, d, config("defense", fee=.001, slip=.0004))
    tr = out[1].iloc[0]
    assert tr.exit_time == ZERO + pd.Timedelta(days=2)
    assert tr.exit_reason == "stop_gap"
    assert tr.exit_price == pytest.approx((100. - side * 8.) * (1. - side * .0004))
    assert out[3].timestamp.max() <= tr.exit_time


@pytest.mark.parametrize("policy", ["defense", "trend", "extension"])
def test_future_candles_cannot_change_prefix_state_or_cash(policy):
    d, h = generated_ohlc(110)
    f = new.features(d)
    cutoff = ZERO + pd.Timedelta(days=76)
    d2, h2 = d.copy(), h.copy()
    d2.loc[d2.timestamp >= cutoff, ["open", "high", "low", "close"]] *= 2
    h2.loc[h2.timestamp >= cutoff, ["open", "high", "low", "close"]] *= 2
    before = new.simulate(h, f, config(policy, fee=.001, slip=.0004))
    after = new.simulate(h2, new.features(d2), config(policy, fee=.001, slip=.0004))
    for idx in [2, 3]:
        l, r = before[idx], after[idx]
        pd.testing.assert_frame_equal(l.loc[l.timestamp < cutoff].reset_index(drop=True),
                                      r.loc[r.timestamp < cutoff].reset_index(drop=True), check_exact=True)


@pytest.mark.parametrize("side", [1, -1])
def test_new_trades_reset_held_days_watch_and_entry_reference(side):
    d, h = artificial_path(side, closes=(-1., -2., 0., 1., 2., 3., 4.), favorable_high=0., ma_offset=0.)
    # Force first trade out, then offer a genuinely new cross on day 3.
    hit = h.timestamp.eq(ZERO + pd.Timedelta(days=2, hours=2))
    h.loc[hit, "low" if side == 1 else "high"] = 100. - side * 8.
    d.loc[3, ["cross", "slope"]] = [side, side * .1]
    out = new.simulate(h, d, config("extension"))
    assert len(out[1]) == 2
    for trade_id, logs in out[3].groupby("trade_id"):
        held = logs.loc[logs.get("sm_held_days", pd.Series(index=logs.index, dtype=float)).notna()]
        assert held.sm_held_days.iloc[0] == 1
        assert not held.sm_ready3.iloc[0]
        assert held.sm_watch.iloc[0] != "PROTECT"


@pytest.mark.parametrize("policy", ["v3", "defense", "trend", "extension"])
def test_fixed_episode_honors_requested_capital_quantity_and_stops_at_first_exit(policy):
    d, h = generated_ohlc(110)
    f = new.features(d)
    cfg = config(policy, fee=.001, slip=.0004)
    regular = new.simulate(h, f, cfg)
    target = regular[1].iloc[0]
    fixed = {"entry_equity": 4321., "entry_time": target.entry_time,
             "side": int(target.side), "qty": 2.5}
    out = new.simulate(h, f, cfg, start=target.entry_time, fixed_episode=fixed)
    assert len(out[1]) == 1
    tr = out[1].iloc[0]
    assert tr.qty == 2.5
    assert tr.entry_time == target.entry_time and tr.exit_time == target.exit_time
    assert tr.entry_price == target.entry_price and tr.exit_price == target.exit_price
    expected = tr.side * 2.5 * (tr.exit_price - tr.entry_price) - 2.5 * .001 * (tr.entry_price + tr.exit_price)
    assert tr.net_pnl == pytest.approx(expected)
    assert tr.return_on_entry_equity == pytest.approx(expected / 4321.)
    assert out[2].timestamp.max() <= tr.exit_interval_end


@pytest.mark.parametrize("side", [1, -1])
def test_fixed_episode_gap_exit_has_no_artificial_post_exit_flat_hour(side):
    d, h = artificial_path(side, closes=(-1., -2., -2.), favorable_high=0., ma_offset=0.)
    opening = ZERO + pd.Timedelta(days=2)
    hit = h.timestamp.eq(opening)
    h.loc[hit, ["open", "high", "low", "close"]] = 100. - side * 8.
    fixed = {"entry_equity": 4321., "entry_time": ZERO + pd.Timedelta(days=1),
             "side": side, "qty": 2.5}
    out = new.simulate(h, d, config("defense", fee=.001, slip=.0004),
                       start=fixed["entry_time"], fixed_episode=fixed)
    tr = out[1].iloc[0]
    assert tr.exit_reason == "stop_gap" and tr.exit_time == opening
    assert pd.Timestamp(out[0]["end_exclusive"]) == opening
    assert out[2].timestamp.max() == opening
    assert out[0]["exposure_pct"] == 100.


@pytest.mark.parametrize("bad_field,bad_value", [("qty", 0.), ("qty", -1.),
    ("qty", float("nan")), ("entry_equity", 0.), ("entry_equity", -1.),
    ("entry_equity", float("inf"))])
def test_fixed_episode_requires_finite_positive_quantity_and_capital(bad_field, bad_value):
    d, h = artificial_path()
    fixed = {"entry_equity": 4321., "entry_time": ZERO + pd.Timedelta(days=1),
             "side": 1, "qty": 2.5, bad_field: bad_value}
    with pytest.raises(ValueError):
        new.simulate(h, d, config("defense"), start=fixed["entry_time"], fixed_episode=fixed)


def test_changed_costs_can_remove_old_short_rsi_profit_qualification():
    d, h = artificial_path(-1, closes=(.2, .2, .2, .2), favorable_high=2.)
    d.loc[1, ["rsi", "accel1"]] = [20., True]
    cheap = new.simulate(h, d, config("defense", fee=.0005, slip=.0003))
    changed = new.simulate(h, d, config("defense", fee=.001, slip=.0004))
    assert cheap[1].exit_reason.iloc[0] == "accel1_rsi30"
    assert cheap[1].exit_time.iloc[0] == ZERO + pd.Timedelta(days=2)
    assert changed[1].exit_reason.iloc[0] == "sample_end"
    assert changed[1].exit_time.iloc[0] > cheap[1].exit_time.iloc[0]


@pytest.mark.parametrize("side", [1, -1])
def test_multiplier_floor_does_not_continue_decrementing(side):
    d, h = artificial_path(side, closes=tuple([2.] * 14), favorable_high=8.)
    out = new.simulate(h, d, config("trend"))
    logs = out[3]
    assert logs.new_mult.min() == .5
    floor = logs.loc[logs.old_mult.eq(.5)]
    assert len(floor) > 0
    assert floor.new_mult.eq(.5).all()
    assert not floor.tightened.any()
    assert ((logs.new_stop - logs.old_stop) * side >= 0).all()
