"""Reference values are frozen independently of production metrics calls."""
import importlib.util
import json
from math import sqrt
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('metrics_v2', ROOT / 'research/_shared-kernels/quantgraph-diagnostics/v2/metrics.py')
metrics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metrics)
FIXTURE = json.loads((ROOT / 'tests/fixtures/statistical_reference_v2.json').read_text())


@pytest.mark.parametrize('trials,skew,kurtosis,expected', [(100, -3, 10, .9004), (46, -3, 10, .9505), (88, 0, 3, .9505)])
def test_published_dsr_numerical_example(trials, skew, kurtosis, expected):
    # Bailey/Lopez de Prado 2014 pp. 9-10; 250 observations/year.
    result = metrics.dsr_from_moments(sr=2.5 / sqrt(250), trial_variance=.5 / 250,
                                     effective_trials=trials, observations=1250, skew=skew, kurtosis=kurtosis)
    assert result['value'] == pytest.approx(expected, abs=5e-5)
    if trials == 100:
        assert result['benchmark_sr'] == pytest.approx(.1132, abs=5e-5)


def test_moments_and_dsr_against_frozen_scipy_reference():
    case = FIXTURE['dsr']
    result = metrics.deflated_sharpe(case['returns'], trial_sharpes=case['trial_sharpes'], effective_trials=case['effective_trials'])
    for name, expected in case['expected'].items():
        assert result[name] == pytest.approx(expected, abs=1e-13)


def test_cscv_every_logit_against_fixed_benchmark():
    case = FIXTURE['pbo']
    result = metrics.pbo(case['returns_by_trial'], blocks=case['blocks'])
    expected = [(v, 1 / len(s['logits'])) for s in case['splits'] for v in s['logits']]
    np.testing.assert_allclose(result['weighted_logits'], expected, atol=1e-13)
    assert result['value'] == pytest.approx(2 / 3)
    assert result['splits'] == 6


def test_tie_mass_does_not_truncate_number_of_cscv_splits():
    x = np.tile([-.01, .03, .01, -.02], 16)
    result = metrics.pbo(np.column_stack([x, x, x]))
    assert result['splits'] == 70 and result['value'] == 1
    assert sum(w for _, w in result['weighted_logits']) == pytest.approx(70)


@pytest.mark.parametrize('returns,trials,n', [([1, 2, 3], [0, 1], 2), ([1, 1, 1, 1], [0, 1], 2),
                                            ([1, 2, 3, 4], [0], 1), ([1, 2, 3, 4], [0, 1], 3),
                                            ([1, 2, np.nan, 4], [0, 1], 2)])
def test_insufficient_dsr_samples_fail_closed(returns, trials, n):
    with pytest.raises(ValueError):
        metrics.deflated_sharpe(returns, trial_sharpes=trials, effective_trials=n)


@pytest.mark.parametrize('shape,blocks', [((7, 3), 4), ((8, 1), 4), ((8, 3), 3), ((8, 3), 8), ((8, 3), 4.0)])
def test_insufficient_cscv_samples_fail_closed(shape, blocks):
    with pytest.raises(ValueError):
        metrics.pbo(np.zeros(shape), blocks=blocks)
