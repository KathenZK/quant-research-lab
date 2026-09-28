"""Reachability proof checks for the fixed-original-entry ledger."""
import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT/'research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts'
sys.path.insert(0, str(SCRIPTS))
import pair_v3_opportunity_20260913 as pair

spec = importlib.util.spec_from_file_location('pair_fixture', ROOT/'tests/test_ma7_car_v3_opportunity.py')
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)


def test_original_tp_is_first_reachable_intervention_and_entry_is_exact():
    d, h = fixture.protecting()
    e = fixture.new
    a = e.simulate(h, d, fixture.cfg())
    original = a[1].iloc[0].to_dict()
    observations = pair.legacy_tp_observations(original, a[3], d.set_index('timestamp'))
    assert len(observations) == 1 and observations[0]['effective_at'] == original['exit_time']
    fixed = {key: original[key] for key in ['entry_time', 'entry_equity', 'qty', 'side']}
    b = e.simulate(h, d, fixture.cfg(short_exit='accel1_rsi30_protect'), fixed_episode=fixed)
    pair.compare_entry(original, b[1].iloc[0].to_dict())


def test_original_terminal_gap_can_be_reused_despite_same_boundary_eligible_tp():
    d, h = fixture.protecting()
    h.loc[h.timestamp == fixture.ZERO + pd.Timedelta(days=2), 'open'] = 140.
    a = fixture.new.simulate(h, d, fixture.cfg())
    original = a[1].iloc[0].to_dict()
    observations = pair.legacy_tp_observations(original, a[3], d.set_index('timestamp'))
    assert original['exit_reason'] == 'stop_gap'
    assert pair.prove_reuse(original, observations) == 'terminal_gap_precedes_eligible_tp'


def test_non_tp_reuse_rejects_any_earlier_reachable_intervention():
    trade = {'side': -1, 'exit_reason': 'stop_intrahour',
             'exit_time': fixture.ZERO + pd.Timedelta(days=5)}
    obs = [{'effective_at': fixture.ZERO + pd.Timedelta(days=2)}]
    with pytest.raises(AssertionError):
        pair.prove_reuse(trade, obs)
    obs = [{'effective_at': trade['exit_time']}]
    with pytest.raises(AssertionError):
        pair.prove_reuse(trade, obs)


def test_winner_retention_includes_winners_turned_negative():
    f = pd.DataFrame({'slug': ['A', 'A'], 'baseline_return_on_entry_equity': [.1, .1],
                      'new_return_on_entry_equity': [.2, -.1],
                      'method': ['fixed_original_entry_replay']*2,
                      'new_is_sample_end': [False, False], 'additional_holding_days': [1., 2.]})
    s = pair.summary(f, 'test', 'test')
    assert s['original_winner_signed_net_retention_pct'] == 50.
    assert s['winners_turned_loss'] == 1
