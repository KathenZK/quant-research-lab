"""Forward-label timing and event classification checks; no market results."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1]/'research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('v3_diag', SCRIPTS/'diagnose_v3_opportunity_20260913.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def hours(n=480):
    return pd.DataFrame(dict(timestamp=pd.date_range('2025-01-01', periods=n, freq='h', tz='UTC'),
                             open=np.full(n, 100.), high=np.full(n, 100.),
                             low=np.full(n, 100.), close=np.full(n, 100.)))


@pytest.mark.parametrize('side', [1, -1])
def test_fixed_return_fees_and_slip(side):
    entry = 100*(1+side*.0004)
    end = 110*(1-side*.0004)
    qty = 1/(entry*1.001)
    expected = qty*(side*(end-entry)-.001*(entry+end))
    assert m.hypothetical_return(100, 110, side) == expected
    assert m.hypothetical_return(100, 100, side) < 0


def test_observation_does_not_consume_exit_hour_and_requires_whole_window():
    h = hours(481)
    h.loc[0, ['high', 'low']] = [1000, 1]
    r = m.HourlyPath(h).observe(h.timestamp.iloc[1], 1, 10.)
    assert r['f20_complete'] and r['f20_mfe_atr'] == 0 and r['f20_mae_atr'] == 0
    r = m.HourlyPath(h.iloc[:-1]).observe(h.timestamp.iloc[1], 1, 10.)
    assert not r['f20_complete'] and np.isnan(r['f20_mfe_atr'])
    assert r['f10_complete']


@pytest.mark.parametrize('side', [1, -1])
def test_same_hour_first_touch_stays_ambiguous(side):
    h = hours()
    h.loc[2, ['high', 'low']] = [125, 75]
    r = m.HourlyPath(h).observe(h.timestamp.iloc[0], side, 10.)
    assert r['f20_first_1atr'] == 'same_hour_ambiguous'
    assert r['f20_first_2atr'] == 'same_hour_ambiguous'
    assert r['f20_first_favorable_1atr_hour'] == r['f20_first_adverse_1atr_hour'] == 2


def test_first_touch_has_direction_and_first_occurrence():
    h = hours()
    h.loc[1, 'high'] = 111
    h.loc[2, 'low'] = 89
    assert m.HourlyPath(h).observe(h.timestamp.iloc[0], 1, 10)['f5_first_1atr'] == 'favorable_first'
    assert m.HourlyPath(h).observe(h.timestamp.iloc[0], -1, 10)['f5_first_1atr'] == 'adverse_first'


def test_recovery_strict_extreme_and_ambiguous_retrace_bounds():
    h = hours()
    h.loc[1, 'high'] = 110  # equality is not a new high
    h.loc[2, ['high', 'low']] = [111, 80]
    r = m.HourlyPath(h).observe(h.timestamp.iloc[0], 1, 10., 110.)
    assert r['f20_old_extreme_recovered']
    assert r['f20_recovery_first_hour'] == 2
    assert r['f20_pre_recovery_retrace_lower_atr'] == 1
    assert r['f20_pre_recovery_retrace_upper_atr'] == 3


def test_recovery_gap_open_excludes_later_adverse_range():
    h = hours()
    h.loc[2, ['open', 'high', 'low']] = [111, 111, 80]
    r = m.HourlyPath(h).observe(h.timestamp.iloc[0], 1, 10., 110.)
    assert r['f20_pre_recovery_retrace_lower_atr'] == r['f20_pre_recovery_retrace_upper_atr'] == 1


def test_gap_rejected_not_stitched():
    with pytest.raises(AssertionError):
        m.HourlyPath(hours().drop(index=20))


def test_busy_and_exit_priority_not_mislabeled_slope():
    start = pd.Timestamp('2025-01-02', tz='UTC')
    empty = pd.DataFrame()
    t = pd.DataFrame([dict(entry_time=start-pd.Timedelta(days=1), exit_time=start,
                           exit_reason='stop_intrahour')])
    assert m.classify_cross(start, 1, empty, t, {})[0] == 'position_occupied'
    t.loc[0, 'exit_reason'] = 'stop_gap'
    assert m.classify_cross(start, 1, empty, t, {})[0] == 'exit_priority_same_hour'
    with pytest.raises(AssertionError):
        m.classify_cross(start, 1, empty, pd.DataFrame(), {})


def test_logged_slope_rejection_and_fill_identity():
    start = pd.Timestamp('2025-01-02', tz='UTC')
    e = pd.DataFrame([dict(timestamp=start, side=1, status='rejected', reason='slope_rejected', stage='slope', trade_id=None)])
    assert m.classify_cross(start, 1, e, pd.DataFrame(), {})[0] == 'slope_rejected'
    e.loc[0, ['status', 'reason', 'stage', 'trade_id']] = ['filled', 'filled', 'fill', 3]
    assert m.classify_cross(start, 1, e, pd.DataFrame(), {(start, 1): SimpleNamespace(trade_id=3)})[0] == 'filled'


def daily(n=60):
    c = np.arange(n, dtype=float)+100
    return pd.DataFrame(dict(timestamp=pd.date_range('2025-01-01', periods=n, freq='D', tz='UTC'),
                             open=c-1, high=c+1, low=c-2, close=c, atr=np.full(n, 5.),
                             ma=c-2, cross=np.where(np.arange(n)%7 == 0, 1, 0)))


def test_feature_prefix_and_fixed_bins():
    full = m.causal_features(daily())
    prefix = m.causal_features(daily().iloc[:45])
    pd.testing.assert_frame_equal(full.iloc[:45], prefix)
    r = m.feature_record(full, 40, 1)
    assert r['features_known_at'] == full.timestamp.iloc[40]+pd.Timedelta(days=1)
    assert r['efficiency20_bin'] == 'ge_0.5'
    assert m.category(.2, [.2, .5], ['low', 'mid', 'high']) == 'mid'
    full.loc[40, 'feature_ma30_q'] = .05
    assert m.feature_record(full, 40, 1)['ma30_bin'] == 'middle'
    full.loc[40, 'feature_ma30_q'] = -.05
    assert m.feature_record(full, 40, 1)['ma30_bin'] == 'conflict_le_-0.05'
