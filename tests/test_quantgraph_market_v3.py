"""Synthetic unit tests only; no fixture is ever a counted market backtest."""
import copy
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from strategy_lab.knowledge.results import market_evidence_envelope

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('market_v1', ROOT/'research/_shared-kernels/quantgraph-market/v1/engine.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def sample():
    close = [100, 101, 102, 110, 104, 90, 91, 98]
    bars = pd.DataFrame(dict(ts=pd.date_range('2020-01-01', periods=8, tz='UTC'),
                             open=close, close=close, high=np.array(close)+1, low=np.array(close)-1, volume=1.))
    c = dict(signal='PRICE_SMA', parameters=[2], initial_cash=1000, evaluation_start='2020-01-01T00:00:00Z',
             minutes=1440, fee_bps=10, slippage_bps=4, stop_loss_fraction=None, take_profit_fraction=None)
    return bars, c


def test_signal_is_closed_before_next_open_and_future_has_no_effect():
    bars, c = sample()
    a, f, t = engine.replay(bars, c)
    assert f.iloc[0].ts == str(bars.ts.iloc[2])
    assert f.iloc[0].price == pytest.approx(bars.open.iloc[2]*1.0004)
    changed = bars.copy()
    changed.loc[6:, ['open', 'high', 'low', 'close']] *= 10
    b, g, _ = engine.replay(changed, c)
    np.testing.assert_allclose(a.equity[:6], b.equity[:6])
    pd.testing.assert_frame_equal(f[f.ts < str(bars.ts.iloc[6])], g[g.ts < str(bars.ts.iloc[6])])
    # Cash accounting telescopes across fully closed trades, fees included.
    assert a.equity.iloc[-1] == pytest.approx(c['initial_cash']+t.pnl.sum())
    assert f.fee.sum() == pytest.approx(a.fee.sum())


def test_zscore_source_is_stateless_not_invented_hysteresis():
    bars, _ = sample()
    enter, leave = engine.signals(bars, 'ZSCORE_REVERSION', [3, .7])
    z = (bars.close-bars.close.rolling(3).mean())/bars.close.rolling(3).std(ddof=1)
    assert enter.tolist() == (z < -.7).to_list()
    assert leave.tolist() == (z >= -.7).to_list()


def test_ema_seed_and_strict_gap_failure():
    np.testing.assert_allclose(engine.ema_sma_seed(np.array([1., 2., 3., 4.]), 3)[2:], [2., 3.])
    bars, c = sample()
    with pytest.raises(ValueError, match='Missing bars'):
        engine.replay(bars.drop(index=4), c)
    bars.loc[2, 'close'] = np.nan
    with pytest.raises(ValueError, match='Invalid'):
        engine.replay(bars, c)


def test_same_bar_double_touch_stops_first_and_gap_does_not_fill_stale_stop():
    bars, c = sample()
    c.update(fee_bps=0, slippage_bps=0, stop_loss_fraction=.1, take_profit_fraction=.1)
    bars.loc[2, ['low', 'high']] = [80, 130]
    a, _, t = engine.replay(bars, c)
    assert t.iloc[0].exit_price == pytest.approx(91.8)
    assert t.iloc[0].reason == 'stop'
    assert bool(a.iloc[2].ambiguous_bracket)
    bars, c = sample()
    c.update(fee_bps=0, slippage_bps=0, stop_loss_fraction=.1)
    bars.loc[3, ['open', 'close', 'high', 'low']] = [70, 72, 73, 69]
    _, _, t = engine.replay(bars, c)
    assert t.iloc[0].exit_price == 70 and t.iloc[0].reason == 'stop_gap'


def test_larger_costs_reduce_same_signal_terminal_equity():
    bars, c = sample()
    a, _, _ = engine.replay(bars, c)
    b, _, _ = engine.replay(bars, c, cost_multiplier=2)
    assert b.equity.iloc[-1] < a.equity.iloc[-1]


def test_market_envelope_rejects_untrusted_fixture_and_missing_gate():
    args = dict(family_id='unit-test', candidate_rows=[], contract={}, parameter_grid=[{}], artifact_uri='fixture:local',
                artifact_sha256='a'*64, code_sha256='b'*64, config_sha256='c'*64,
                data_provenance={}, results={}, research_status='INCONCLUSIVE', limitations=['unit test'])
    with pytest.raises(ValueError, match='No admitted'):
        market_evidence_envelope(**args)
    args['candidate_rows'] = [{'candidate_gate': {}}]
    with pytest.raises(ValueError, match='UPSTREAM_CONTRACT'):
        market_evidence_envelope(**args)
    data = dict(real_market_data=True, quality_status='UNVERIFIED', data_availability_status='PENDING')
    args['data_provenance'] = data
    args['candidate_rows'] = [dict(candidate_gate=dict(gate_version='research-candidate-gate-v3', status='ELIGIBLE', eligible=True),
                                  variant=dict(strategy_concept_id='c1', strategy_template_id='t1'),
                                  reviewed_evidence=dict(data_requirement=copy.deepcopy(data)))]
    with pytest.raises(ValueError, match='Untrusted'):
        market_evidence_envelope(**args)
