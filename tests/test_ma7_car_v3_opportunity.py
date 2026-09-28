"""Synthetic account and causal-timing checks; no real-market outcomes used."""
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'opportunity_fixture', ROOT / 'tests/test_ma7_car_admission_routing.py')
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
old, new = fixture.load('v5'), fixture.load('v6')
ZERO = fixture.ZERO


def cfg(**kw):
    return new.Config(**dict(reverse=False, progress_days=4, fee=.001, slip=.0004, **kw))


def waiting(side=1):
    d, h = fixture.path(side=side, closes=(2., 2., 2., 2., 3., 4., 5., 6.),
                        favorable=6., ma=-1., atr=10.)
    d['slope'] = 0.
    d.loc[5, 'slope'] = side * .1
    return d, h


def protecting():
    d, h = fixture.path(side=-1, closes=(20., 30., 34., 33., 32., 31., 30.),
                        favorable=20., ma=-20., atr=10.)
    d['rsi'] = 10.
    d['accel1'] = True
    return d, h


@pytest.mark.parametrize('kw', [{}, {'reverse': False, 'progress_days': 4},
    {'entry_wait_days': 3}, {'entry_mode': 'absolute_slowdown', 'tighten_mode': 'stall_only'},
    {'risk_fraction': .005, 'fee': .001, 'slip': .0004},
    {'reverse': False, 'progress_days': 4, 'exit_state_policy': 'extension', 'short_exit': 'none'},
    {'reverse': False, 'progress_days': 4, 'admission_routing': True, 'ma30_mode': 'both'}])
def test_disabled_exactly_preserves_v5_every_table_and_event(kw):
    raw, h = fixture.random_market()
    d = fixture.routes(old.features(raw), 'v3')
    f = pd.DataFrame({'timestamp': [ZERO + pd.Timedelta(days=40),
                                   ZERO + pd.Timedelta(days=53, minutes=17)],
                      'funding_rate': [.0001, -.0003], 'mark_price': [100., np.nan]})
    for funding, carry in [(None, 0.), (f, .0002)]:
        ae, be = [], []
        a = old.simulate(h, d, old.Config(**kw), funding=funding, carry_daily=carry, entry_events=ae)
        b = new.simulate(h, d, new.Config(**kw), funding=funding, carry_daily=carry, entry_events=be)
        for k, v in a[0].items():
            assert b[0][k] == v, k
        for x, y in zip(a[1:], b[1:]):
            pd.testing.assert_frame_equal(x, y, check_exact=True)
        pd.testing.assert_frame_equal(pd.DataFrame(ae), pd.DataFrame(be), check_exact=True)


@pytest.mark.parametrize('side', [-1, 1])
def test_candidate_can_confirm_after_five_days_and_uses_confirmation_stop(side):
    d, h = waiting(side)
    d.loc[5, 'ma'] += side * 2.
    d.loc[5, 'atr'] = 12.
    events = []
    b = new.simulate(h, d, cfg(entry_wait_policy='until_invalid'), entry_events=events)
    t = b[1].iloc[0]
    assert t.entry_time == ZERO + pd.Timedelta(days=6)
    assert t.cross_day == ZERO and t.entry_wait_days_used == 5
    assert t.initial_stop == d.ma.iloc[5] - side * 1.5 * d.atr.iloc[5]
    assert t.entry_reason == 'delayed_cross'
    e = pd.DataFrame(events)
    assert e.status.eq('confirmed').sum() == 1
    assert e.reason.eq('conditions_pending').sum() == 4
    assert b[0]['wait_candidates_confirmed'] == 1
    # The preexisting bounded wait still expires and cannot reuse the signal.
    a = new.simulate(h, d, cfg(entry_wait_days=3))
    assert a[1].empty


@pytest.mark.parametrize('side', [-1, 1])
@pytest.mark.parametrize('condition', ['equal_ma', 'wrong_ma', 'not_ready', 'opposite_cross'])
def test_candidate_invalidations_are_logged_and_cannot_later_reopen(side, condition):
    d, h = waiting(side)
    if condition == 'equal_ma':
        d.loc[2, 'close'] = d.ma.iloc[2]
    elif condition == 'wrong_ma':
        d.loc[2, 'close'] = d.ma.iloc[2] - side
    elif condition == 'not_ready':
        d.loc[2, 'ready'] = False
    else:
        d.loc[2, 'cross'] = -side
        # Fresh opposite crossing replaces the older candidate, but has no
        # eligible slope and no matching MA side, so it cannot create a new one.
    events = []
    b = new.simulate(h, d, cfg(entry_wait_policy='until_invalid'), entry_events=events)
    assert b[1].empty and b[0]['wait_candidates_cancelled'] == 1
    assert sum(e['status'] == 'cancelled' for e in events) == 1


@pytest.mark.parametrize('side', [-1, 1])
def test_strict_threshold_and_original_close_both_required(side):
    d, h = waiting(side)
    d.loc[1, 'slope'] = side * .05  # Equality is not qualified.
    d.loc[2, 'slope'] = side * .1
    d.loc[2, 'close'] = d.close.iloc[0]  # Equal original close is not progress.
    events = []
    b = new.simulate(h, d, cfg(entry_wait_policy='until_invalid'), entry_events=events)
    assert b[1].iloc[0].entry_wait_days_used == 5
    e = pd.DataFrame(events)
    assert e[e.signal_day == ZERO + pd.Timedelta(days=1)].iloc[-1].candidate_slope_met == False
    assert e[e.signal_day == ZERO + pd.Timedelta(days=2)].iloc[-1].candidate_breaks_cross_close == False


@pytest.mark.parametrize('side', [-1, 1])
def test_invalid_confirmation_open_consumes_candidate_once(side):
    d, h = waiting(side)
    at = ZERO + pd.Timedelta(days=6)
    bad_price = float(d.ma.iloc[5] - side * 1.5 * d.atr.iloc[5] - side)
    h.loc[h.timestamp == at, 'open'] = bad_price
    d.loc[6:, 'slope'] = side * .1
    events = []
    b = new.simulate(h, d, cfg(entry_wait_policy='until_invalid'), entry_events=events)
    assert b[1].empty and b[0]['entry_attempts'] == 1
    assert b[0]['invalid_stop_rejected'] == 1
    assert sum(e['status'] == 'confirmed' for e in events) == 1


def test_unresolved_candidate_is_reported_without_forced_entry():
    d, h = waiting()
    d['slope'] = 0.
    events = []
    b = new.simulate(h, d, cfg(entry_wait_policy='until_invalid'), entry_events=events)
    assert b[1].empty and b[0]['wait_candidates_unresolved'] == 1
    assert events[-1]['reason'] == 'sample_end_unresolved'
    assert events[-1]['timestamp'] == h.timestamp.iloc[-1] + pd.Timedelta(hours=1)


def test_cross_while_holding_does_not_become_later_candidate():
    d, h = fixture.path(closes=(2., 2., 2., 2., 2.), ma=-1., atr=10.)
    d.loc[1, 'cross'] = -1
    d.loc[1, 'slope'] = 0.
    h.loc[h.timestamp == ZERO + pd.Timedelta(days=3), 'low'] = 80.
    d.loc[3:, 'slope'] = -.1
    events = []
    b = new.simulate(h, d, cfg(entry_wait_policy='until_invalid'), entry_events=events)
    assert len(b[1]) == 1 and b[0]['wait_candidates_created'] == 0
    assert not any(e['stage'] == 'candidate' for e in events)


def test_protection_begins_next_day_and_never_retroactively_hits_signal_high():
    d, h = protecting()
    a = new.simulate(h, d, cfg())
    b = new.simulate(h, d, cfg(short_exit='accel1_rsi30_protect'))
    t = b[1].iloc[0]
    assert a[1].iloc[0].exit_time == ZERO + pd.Timedelta(days=2)
    assert t.exit_time > a[1].iloc[0].exit_time
    active = b[3][b[3].tp_protect_active]
    assert active.iloc[0].timestamp == ZERO + pd.Timedelta(days=2)
    assert active.iloc[0].signal_day == ZERO + pd.Timedelta(days=1)
    assert active.iloc[0].tp_protect_candidate == 90.
    assert d.high.iloc[1] > active.iloc[0].new_stop
    assert t.tp_protect_signal_day == ZERO + pd.Timedelta(days=1)


def test_protection_gap_uses_open_slippage_and_precedes_tp_or_new_cross():
    d, h = protecting()
    at = ZERO + pd.Timedelta(days=2)
    h.loc[h.timestamp == at, ['open', 'high']] = [92., 94.]
    d.loc[1, 'cross'] = 1
    d.loc[1, 'slope'] = .1
    b = new.simulate(h, d, cfg(short_exit='accel1_rsi30_protect'))
    t = b[1].iloc[0]
    assert len(b[1]) == 1 and t.exit_time == at and t.exit_reason == 'stop_gap'
    assert t.exit_reference == 92. and t.exit_price == 92. * 1.0004
    assert t.tp_protect_eligible_signal_count == 1
    assert t.tp_protect_suppressed_count == 0  # Gap takes priority before TP call.


def test_intrahour_low_cannot_tighten_before_same_hour_high():
    d, h = protecting()
    at = ZERO + pd.Timedelta(days=2)
    h.loc[h.timestamp == at, ['open', 'high', 'low', 'close']] = [80., 91., 60., 70.]
    d.loc[2, 'low'] = 60.
    b = new.simulate(h, d, cfg(short_exit='accel1_rsi30_protect'))
    t = b[1].iloc[0]
    assert t.exit_time == at and t.exit_interval_end == at + pd.Timedelta(hours=1)
    assert t.exit_reason == 'stop_intrahour' and t.exit_reference == 90.
    assert t.tp_protect_suppressed_count == 1


def test_fixed_event_atr_running_low_and_v3_progress_never_widen():
    d, h = protecting()
    d.loc[2:, 'atr'] = 30.
    b = new.simulate(h, d, cfg(short_exit='accel1_rsi30_protect'))
    s = b[3][b[3].tp_protect_active]
    assert s.tp_protect_event_atr.eq(10.).all()
    assert np.allclose(s.tp_protect_candidate, s.tp_protect_extreme_low + 10.)
    assert s.tp_protect_extreme_low.diff().dropna().le(0).all()
    assert s.new_stop.le(s.old_stop).all() and s.new_stop.le(s.tp_protect_candidate).all()
    assert s.new_mult.le(s.old_mult).all() and s.new_mult.ge(.5).all()
    assert s.tp_protect_triggered_this_day.sum() == 1
    assert s.tp_protect_actually_suppressed.sum() == b[1].iloc[0].tp_protect_suppressed_count


def test_four_day_permanent_v3_tightening_continues_under_protection():
    d, h = fixture.path(side=-1, closes=(20.,) * 12, favorable=20., ma=-20., atr=10.)
    d['rsi'], d['accel1'] = 10., True
    b = new.simulate(h, d, cfg(short_exit='accel1_rsi30_protect'))
    s = b[3]
    first = s[s.tightened].iloc[0]
    assert first.signal_day == ZERO + pd.Timedelta(days=5)
    assert first.no_new_extreme_days == 4 and first.new_mult == 1.3
    assert b[1].iloc[0].stop_mult == .5
    assert s.new_mult.diff().dropna().le(0).all()
    assert s[s.tp_protect_active].new_stop.le(90.).all()


def test_original_ma_stop_can_be_tighter_than_protection_line():
    d, h = protecting()
    d.loc[1, 'ma'] = 70.
    b = new.simulate(h, d, cfg(short_exit='accel1_rsi30_protect'))
    first = b[3][b[3].tp_protect_active].iloc[0]
    assert first.tp_protect_candidate == 90. and first.new_stop == 85.


def test_boundary_funding_is_included_in_legacy_trigger_qualification():
    d, h = protecting()
    funding = pd.DataFrame({'timestamp': [ZERO + pd.Timedelta(days=2)],
                            'funding_rate': [-.5], 'mark_price': [100.]})
    a = new.simulate(h, d, cfg(), funding=funding)
    b = new.simulate(h, d, cfg(short_exit='accel1_rsi30_protect'), funding=funding)
    assert a[0]['short_tp_exits'] == 0 and not b[3].tp_protect_active.any()
    assert b[1].iloc[0].funding_paid > 0


def test_protection_is_not_a_breakeven_or_profit_guarantee():
    d, h = fixture.path(side=-1, closes=(1., 0., 0.), favorable=1., ma=-20., atr=10.)
    d['rsi'], d['accel1'] = 10., True
    at = ZERO + pd.Timedelta(days=2)
    h.loc[h.timestamp == at, ['open', 'high', 'low', 'close']] = [110., 111., 109., 110.]
    b = new.simulate(h, d, cfg(short_exit='accel1_rsi30_protect'))
    t = b[1].iloc[0]
    assert t.tp_protect_trigger_close == 99. and t.tp_protect_candidate == 109.
    assert t.exit_reason == 'stop_gap' and t.exit_reference == 110.
    assert t.net_pnl < 0


@pytest.mark.parametrize('missing', ['profit', 'rsi', 'acceleration'])
def test_all_original_tp_conditions_are_required(missing):
    d, h = protecting()
    if missing == 'profit':
        d['close'] = 110.
    elif missing == 'rsi':
        d['rsi'] = 30.001
    else:
        d['accel1'] = False
    b = new.simulate(h, d, cfg(short_exit='accel1_rsi30_protect'))
    assert not b[3].tp_protect_active.any()
    assert b[1].tp_protect_eligible_signal_count.eq(0).all()


def test_protection_fixed_episode_keeps_original_quantity_equity_and_first_exit():
    d, h = protecting()
    a = new.simulate(h, d, cfg())
    t = a[1].iloc[0]
    fixed = {k: t[k] for k in ['entry_time', 'entry_equity', 'qty', 'side']}
    b = new.simulate(h, d, cfg(short_exit='accel1_rsi30_protect'), fixed_episode=fixed)
    assert len(b[1]) == 1
    assert b[1].iloc[0].qty == t.qty and b[1].iloc[0].entry_equity == t.entry_equity
    assert np.isclose(b[0]['ending_equity'], t.entry_equity + b[1].iloc[0].net_pnl)


@pytest.mark.parametrize('kw', [{'entry_wait_policy': 'until_invalid'},
                               {'short_exit': 'accel1_rsi30_protect'}])
def test_future_changes_cannot_change_past_decisions(kw):
    raw, h = fixture.random_market()
    d = old.features(raw)
    ae, be = [], []
    a = new.simulate(h, d, cfg(**kw), entry_events=ae)
    cut = ZERO + pd.Timedelta(days=95)
    raw2, h2 = raw.copy(), h.copy()
    raw2.loc[raw2.timestamp >= cut, ['open', 'high', 'low', 'close']] *= 1.4
    h2.loc[h2.timestamp >= cut, ['open', 'high', 'low', 'close']] *= 1.4
    b = new.simulate(h2, old.features(raw2), cfg(**kw), entry_events=be)
    for x, y in [(a[3], b[3]), (pd.DataFrame(ae), pd.DataFrame(be))]:
        pd.testing.assert_frame_equal(x[x.timestamp < cut].reset_index(drop=True),
                                      y[y.timestamp < cut].reset_index(drop=True), check_exact=True)


@pytest.mark.parametrize('kw', [{'entry_wait_policy': 'bad'},
    {'entry_wait_policy': 'until_invalid', 'short_exit': 'accel1_rsi30_protect'},
    {'entry_wait_policy': 'until_invalid', 'entry_wait_days': 3},
    {'entry_wait_policy': 'until_invalid', 'short_exit': 'none'},
    {'short_exit': 'accel1_rsi30_protect', 'exit_state_policy': 'defense'},
    {'short_exit': 'accel1_rsi30_protect', 'admission_routing': True},
    {'short_exit': 'accel1_rsi30_protect', 'trend_filter': 'ma30_direction'}])
def test_invalid_or_mixed_experiments_fail_closed(kw):
    with pytest.raises(ValueError):
        cfg(**kw)
