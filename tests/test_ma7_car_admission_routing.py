"""Causal, account-level checks of externally frozen admission/exit routes.

These synthetic cases do not train admission rules or read market data. The
old engine is imported independently as an exact execution comparator.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
ZERO = pd.Timestamp("2026-01-01", tz="UTC")


def load(version):
    name = f"ma7_admission_test_{version}"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / f"research/_shared-kernels/ma7-cross-atr-ratchet/{version}/engine.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


old, new = load("v3"), load("v4")
META = {"admission_allowed", "admission_rule_id", "admission_signal_day",
        "exit_route", "route_short_exit"}


def routed_config(**kw):
    return new.Config(**{"reverse": False, "progress_days": 4, "fee": .001,
                         "slip": .0004, "admission_routing": True, **kw})


def routes(d, route="v3", allowed=True):
    d = d.copy()
    for direction in ("long", "short"):
        d["admit_" + direction] = allowed
        d["route_" + direction] = route
        d["rule_id_" + direction] = "frozen-" + direction
    return d


def random_market(count=130):
    rng = np.random.default_rng(88732)
    close = 100 * np.exp(np.cumsum(rng.normal(0, .06, count)))
    opening = np.r_[100., close[:-1]]
    dates = pd.date_range(ZERO, periods=count, freq="D")
    d = pd.DataFrame({"timestamp": dates, "open": opening, "close": close,
                      "high": np.maximum(opening, close) * 1.004,
                      "low": np.minimum(opening, close) * .996})
    frames = []
    for i in range(count):
        p = np.linspace(opening[i], close[i], 25)
        frames.append(pd.DataFrame({
            "timestamp": pd.date_range(dates[i], periods=24, freq="h"),
            "open": p[:-1], "close": p[1:], "high": np.maximum(p[:-1], p[1:]) * 1.004,
            "low": np.minimum(p[:-1], p[1:]) * .996}))
    return d, pd.concat(frames, ignore_index=True)


def path(side=1, closes=(2., 2., 2., 2., 2.), favorable=3., ma=-1., atr=10.):
    rows = []
    for i, close in enumerate([1., *closes, closes[-1]]):
        prior = 0. if i == 1 else 1. if i == 0 else closes[i-2]
        high, low = max(favorable, close, prior), min(close, prior) - .01
        rows.append({"timestamp": ZERO + pd.Timedelta(days=i),
            "open": 100. + side * prior, "close": 100. + side * close,
            "high": 100. + (high if side == 1 else -low),
            "low": 100. + (low if side == 1 else -high),
            "ma": 100. + side * ma, "atr": atr, "rsi": 50.,
            "slope": side * .1 if i == 0 else 0., "cross": side if i == 0 else 0,
            "ready": True, "accel1": False, "accel2": False,
            "ma30": 100., "prev_ma30": 100.})
    d = pd.DataFrame(rows)
    frames = []
    for i in range(1, len(closes) + 1):
        p = np.linspace(d.open.iloc[i], d.close.iloc[i], 25)
        h = pd.DataFrame({"timestamp": pd.date_range(ZERO + pd.Timedelta(days=i), periods=24, freq="h"),
            "open": p[:-1], "close": p[1:], "high": np.maximum(p[:-1], p[1:]) + .01,
            "low": np.minimum(p[:-1], p[1:]) - .01})
        h.loc[23, "high" if side == 1 else "low"] = d.high.iloc[i] if side == 1 else d.low.iloc[i]
        frames.append(h)
    return d, pd.concat(frames, ignore_index=True)


def assert_old_fields_equal(a, b, excluded_summary=()):
    for key, value in a[0].items():
        if key not in excluded_summary:
            assert b[0][key] == value, key
    for left, right in zip(a[1:], b[1:]):
        pd.testing.assert_frame_equal(left, right[left.columns], check_exact=True)


@pytest.mark.parametrize("kw", [{}, {"reverse": False, "progress_days": 4},
    {"entry_wait_days": 3}, {"entry_mode": "absolute_slowdown", "tighten_mode": "stall_only"},
    {"direction_mode": "short", "trend_filter": "ma30_direction"},
    {"risk_fraction": .005, "fee": .001, "slip": .0004},
    {"progress_days": 4, "progress_policy": "reset_on_new_extreme"},
    {"reverse": False, "progress_days": 4, "exit_state_policy": "defense"},
    {"reverse": False, "progress_days": 4, "exit_state_policy": "trend"},
    {"reverse": False, "progress_days": 4, "exit_state_policy": "extension", "short_exit": "none"}])
def test_disabled_preserves_every_v3_result_and_entry_event_exactly(kw):
    d, h = random_market()
    a_events, b_events = [], []
    funding = pd.DataFrame({"timestamp": [ZERO + pd.Timedelta(days=45),
        ZERO + pd.Timedelta(days=68, minutes=7)], "funding_rate": [.0001, -.0002],
        "mark_price": [100., np.nan]})
    for f, carry in [(None, 0.), (funding, .0005)]:
        a_events.clear()
        b_events.clear()
        a = old.simulate(h, old.features(d), old.Config(**kw), funding=f,
                         carry_daily=carry, entry_events=a_events)
        b = new.simulate(h, new.features(d), new.Config(**kw), funding=f,
                         carry_daily=carry, entry_events=b_events)
        assert_old_fields_equal(a, b)
        pd.testing.assert_frame_equal(pd.DataFrame(a_events), pd.DataFrame(b_events), check_exact=True)


@pytest.mark.parametrize("policy", ["v3", "defense", "trend", "extension"])
def test_uniform_allowed_route_exactly_matches_original_selected_exit_engine(policy):
    d, h = random_market()
    f = routes(new.features(d), policy)
    cfg = {"reverse": False, "progress_days": 4, "fee": .001, "slip": .0004,
           "exit_state_policy": policy, "short_exit": "none" if policy == "extension" else "accel1_rsi30"}
    a_events, b_events = [], []
    a = old.simulate(h, old.features(d), old.Config(**cfg), entry_events=a_events)
    b = new.simulate(h, f, routed_config(), entry_events=b_events)
    assert_old_fields_equal(a, b, {"name", "exit_state_policy", "short_exit"})
    assert b[1].exit_route.eq(policy).all()
    assert b[3].exit_route.eq(policy).all()
    assert set(pd.DataFrame(b_events).columns) - set(pd.DataFrame(a_events).columns) == META
    pd.testing.assert_frame_equal(pd.DataFrame(a_events), pd.DataFrame(b_events)[pd.DataFrame(a_events).columns], check_exact=True)


@pytest.mark.parametrize("side", [1, -1])
def test_admission_rejection_keeps_cross_attempt_statistics_and_reason(side):
    d, h = path(side)
    d = routes(d)
    direction = "long" if side == 1 else "short"
    d.loc[0, "admit_" + direction] = False
    events = []
    out = new.simulate(h, d, routed_config(), entry_events=events)
    assert out[0]["flat_ready_crosses"] == 1
    assert out[0]["entry_attempts"] == 1
    assert out[0]["admission_rejected"] == 1
    assert out[0]["slope_rejected"] == 0 and out[0]["trades"] == 0
    assert out[0]["ending_equity"] == 10000.
    assert out[1].empty and out[3].empty
    assert len(events) == 1
    assert events[0]["stage"] == "admission" and events[0]["reason"] == "admission_rejected"
    assert events[0]["admission_rule_id"] == "frozen-" + direction
    assert events[0]["admission_signal_day"] == ZERO


@pytest.mark.parametrize("side", [1, -1])
def test_router_cannot_admit_a_cross_that_fails_original_slope(side):
    d, h = path(side)
    d = routes(d)
    d.loc[0, "slope"] = side * .05
    events = []
    out = new.simulate(h, d, routed_config(), entry_events=events)
    assert out[0]["slope_rejected"] == 1
    assert out[0]["admission_rejected"] == 0 and out[0]["entry_attempts"] == 0
    assert events[0]["reason"] == "slope_rejected"


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("admitted", [False, True])
def test_only_preceding_closed_row_decides_today_entry_not_today_or_later(side, admitted):
    d, h = path(side)
    d = routes(d, allowed=not admitted)
    direction = "long" if side == 1 else "short"
    d.loc[0, "admit_" + direction] = admitted
    d.loc[0, "rule_id_" + direction] = "known-yesterday"
    events = []
    out = new.simulate(h, d, routed_config(), entry_events=events)
    assert out[0]["trades"] == int(admitted)
    assert events[0]["admission_rule_id"] == "known-yesterday"
    assert events[0]["timestamp"] == ZERO + pd.Timedelta(days=1)
    assert events[0]["signal_day"] == ZERO


@pytest.mark.parametrize("side", [1, -1])
def test_position_keeps_entry_route_and_rule_despite_all_future_route_changes(side):
    d, h = path(side, closes=(-1., -2., -2.), favorable=0., ma=0.)
    a = routes(d, "defense")
    b = a.copy()
    for direction in ("long", "short"):
        b.loc[1:, "route_" + direction] = "extension"
        b.loc[1:, "admit_" + direction] = False
        b.loc[1:, "rule_id_" + direction] = "future-rule"
    before = new.simulate(h, a, routed_config())
    after = new.simulate(h, b, routed_config())
    assert_old_fields_equal(before, after)
    assert after[1].exit_route.eq("defense").all()
    assert after[3].exit_route.eq("defense").all()
    assert after[3].admission_signal_day.eq(ZERO).all()
    assert not after[3].admission_rule_id.eq("future-rule").any()


@pytest.mark.parametrize("policy,expected", [("v3", "accel1_rsi30"),
    ("defense", "accel1_rsi30"), ("trend", "accel1_rsi30"), ("extension", "sample_end")])
def test_each_short_route_selects_its_frozen_take_profit_rule(policy, expected):
    d, h = path(-1, closes=(2., 2., 2., 2.), favorable=2.)
    d.loc[1, ["rsi", "accel1"]] = [20., True]
    out = new.simulate(h, routes(d, policy), routed_config())
    assert out[1].exit_reason.iloc[0] == expected
    assert out[1].route_short_exit.iloc[0] == ("none" if policy == "extension" else "accel1_rsi30")


@pytest.mark.parametrize("policy", ["v3", "defense", "trend", "extension"])
def test_gap_stop_precedes_route_take_profit_and_never_reopens_same_hour(policy):
    d, h = path(-1, closes=(2., 2., 2., 2.), favorable=2.)
    d.loc[1, ["rsi", "accel1", "cross", "slope"]] = [20., True, 1, .1]
    gap = h.timestamp.eq(ZERO + pd.Timedelta(days=2))
    h.loc[gap, ["open", "high", "low", "close"]] = 120.
    out = new.simulate(h, routes(d, policy), routed_config())
    tr = out[1].iloc[0]
    assert len(out[1]) == 1
    assert tr.exit_reason == "stop_gap" and tr.exit_time == ZERO + pd.Timedelta(days=2)
    assert tr.exit_price == pytest.approx(120. * 1.0004)
    assert out[0]["entry_attempts"] == 1


@pytest.mark.parametrize("column,bad", [("admit_long", 1), ("admit_short", "False"),
    ("admit_long", None), ("admit_short", np.nan), ("route_long", "V3"),
    ("route_short", ""), ("route_long", None), ("rule_id_short", 2),
    ("rule_id_long", "  "), ("rule_id_short", None)])
def test_invalid_decision_even_on_non_signal_future_row_fails_closed(column, bad):
    d, h = path()
    d = routes(d)
    d[column] = d[column].astype(object)
    d.loc[d.index[-1], column] = bad
    with pytest.raises(ValueError, match="Invalid admission-routing value"):
        new.simulate(h, d, routed_config())


@pytest.mark.parametrize("column", ["admit_long", "admit_short", "route_long", "route_short",
    "rule_id_long", "rule_id_short"])
def test_missing_column_fails_closed(column):
    d, h = path()
    with pytest.raises(ValueError, match="Missing admission-routing column"):
        new.simulate(h, routes(d).drop(columns=column), routed_config())


@pytest.mark.parametrize("kw", [{"admission_routing": "true"}, {"reverse": True},
    {"progress_days": 3}, {"delay_hours": 1}, {"entry_wait_days": 2},
    {"entry_mode": "no_slope"}, {"exit_state_policy": "defense"},
    {"short_exit": "none"}, {"exit_opposite_cross": True}])
def test_router_rejects_conflicting_base_controls(kw):
    with pytest.raises(ValueError):
        routed_config(**kw)


def test_disabled_router_ignores_absent_or_malformed_route_columns():
    d, h = path()
    a = new.simulate(h, d, new.Config(reverse=False, progress_days=4))
    d = routes(d)
    d["admit_long"], d["route_short"] = "garbage", None
    b = new.simulate(h, d, new.Config(reverse=False, progress_days=4))
    assert_old_fields_equal(a, b)


def test_mixed_routes_each_trade_reconciles_to_independent_original_fixed_episode():
    d, h = random_market(230)
    f = routes(new.features(d))
    eligible = f.index[f.ready & f.cross.ne(0) & (f.cross * f.slope).gt(.05)]
    choices = ["v3", "defense", "trend", "extension"]
    for number, index in enumerate(eligible):
        for direction in ("long", "short"):
            f.loc[index, "route_" + direction] = choices[number % 4]
            f.loc[index, "rule_id_" + direction] = f"row-{index}-{direction}"
    out = new.simulate(h, f, routed_config())
    assert out[1].exit_route.nunique() == 4
    for _, trade in out[1].iterrows():
        selected = old.Config(reverse=False, progress_days=4, fee=.001, slip=.0004,
            exit_state_policy=trade.exit_route, short_exit=trade.route_short_exit)
        episode = {"entry_equity": trade.entry_equity, "entry_time": trade.entry_time,
                   "qty": trade.qty, "side": int(trade.side)}
        expected = old.simulate(h, new.features(d), selected,
                               start=trade.entry_time, fixed_episode=episode)[1].iloc[0]
        for key, value in expected.drop("trade_id").items():
            # A multi-trade frame promotes a missing date from None to NaT;
            # every nonmissing field must still be exactly identical.
            if pd.isna(value) and pd.isna(trade[key]):
                continue
            assert value == trade[key], (trade.trade_id, key)
        stop_rows = out[3].loc[out[3].trade_id.eq(trade.trade_id)]
        assert stop_rows.exit_route.eq(trade.exit_route).all()
        assert stop_rows.admission_rule_id.eq(trade.admission_rule_id).all()
        assert stop_rows.admission_signal_day.eq(trade.signal_day).all()


@pytest.mark.parametrize("side", [1, -1])
def test_selected_defense_uses_completed_close_and_next_open_stop_only(side):
    d, h = path(side, closes=(-1., -2., -2.), favorable=0., ma=0.)
    # The first day's intrahour move crosses the yet-unknown defensive line.
    h.loc[5, "low" if side == 1 else "high"] = 100. - side * 10.
    opening = ZERO + pd.Timedelta(days=2)
    h.loc[h.timestamp.eq(opening), ["open", "high", "low", "close"]] = 100. - side * 8.
    out = new.simulate(h, routes(d, "defense"), routed_config())
    trade = out[1].iloc[0]
    assert trade.exit_time == opening and trade.exit_reason == "stop_gap"
    assert trade.exit_price == pytest.approx((100. - side * 8.) * (1. - side * .0004))
    assert out[3].timestamp.max() == opening


@pytest.mark.parametrize("side", [1, -1])
def test_year_2025_model_switch_never_rewrites_an_inherited_position(side):
    d, h = path(side, closes=(2., 2., 2., 2., 2., 2.), favorable=3.)
    shift = ZERO - pd.Timestamp("2024-12-28", tz="UTC")
    d["timestamp"] -= shift
    h["timestamp"] -= shift
    before = routes(d, "v3")
    after = before.copy()
    cut = pd.Timestamp("2025-01-01", tz="UTC")
    for direction in ("long", "short"):
        after.loc[after.timestamp.ge(cut), "route_" + direction] = "extension"
        after.loc[after.timestamp.ge(cut), "rule_id_" + direction] = "model-2025"
    a = new.simulate(h, before, routed_config())
    b = new.simulate(h, after, routed_config())
    assert_old_fields_equal(a, b)
    inherited = b[3].loc[b[3].timestamp.ge(cut)]
    assert len(inherited) > 0 and inherited.exit_route.eq("v3").all()
    assert inherited.admission_signal_day.eq(pd.Timestamp("2024-12-28", tz="UTC")).all()
