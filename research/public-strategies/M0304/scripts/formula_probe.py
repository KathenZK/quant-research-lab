#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""M0304 first-party formula probe. Synthetic data only; no trading/replay engine.

The original strategy/framework files are inspected as text/AST, never imported.
"""
import argparse
import json
import resource
from pathlib import Path
import numpy as np
import pandas as pd
import talib

FEATURES = ['slowk', 'rsi', 'fisher_rsi', 'bb_lowerband', 'sar', 'CDLHAMMER', 'enter_long', 'exit_long']


def rules(d):
    """Preserve strict source inequalities, without adding an extra volume test."""
    return pd.DataFrame({
        'enter_long': (d.rsi < 30) & (d.slowk < 20) & (d.bb_lowerband > d.close) & (d.CDLHAMMER == 100),
        'exit_long': (d.sar > d.close) & (d.fisher_rsi > 0.3),
    }, index=d.index)


def features(d):
    z = d.copy()
    o, h, l, c = [z[x].to_numpy(dtype='float64') for x in ['open', 'high', 'low', 'close']]
    z['slowk'], _ = talib.STOCH(h, l, c, fastk_period=5, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
    z['rsi'] = talib.RSI(c, timeperiod=14)
    scaled = 0.1 * (z.rsi - 50)
    exp = np.exp(2 * scaled)
    z['fisher_rsi'] = (exp - 1) / (exp + 1)
    tp = (z.high + z.low + z.close) / 3.0
    z['bb_lowerband'] = tp.rolling(20, min_periods=1).mean() - 2 * tp.rolling(20, min_periods=1).std(ddof=1)
    z['sar'] = talib.SAR(h, l, acceleration=0.02, maximum=0.2)
    z['CDLHAMMER'] = talib.CDLHAMMER(o, h, l, c)
    z[['enter_long', 'exit_long']] = rules(z)
    return z


def fee_aware_profit(quote, entry_fill, entry_fee, exit_fee):
    """Unlevered spot return on entry notional plus entry fee, at a decision quote."""
    return quote * (1 - exit_fee) / (entry_fill * (1 + entry_fee)) - 1


def planned_exit_gate(quote, entry_fill, fee_bps):
    fee = fee_bps / 10000
    return fee_aware_profit(quote, entry_fill, fee, fee) > 0


def roi_at(age_minutes):
    return max(((0, .05), (20, .04), (30, .03), (60, .01)), key=lambda kv: kv[0] if kv[0] <= age_minutes else -1)


def synthetic(seed=304, n=2400):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, .015, n)))
    o = np.r_[100, c[:-1]] * np.exp(rng.normal(0, .002, n))
    h = np.maximum(o, c) * (1 + rng.uniform(.0001, .02, n))
    l = np.minimum(o, c) * (1 - rng.uniform(.0001, .03, n))
    return pd.DataFrame({'open': o, 'high': h, 'low': l, 'close': c, 'volume': rng.uniform(1, 100, n)})


def validate():
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    d = synthetic()
    whole = features(d)
    checks = []
    for n in [80, 600, 1600]:
        pd.testing.assert_frame_equal(whole.loc[:n-1, FEATURES], features(d.iloc[:n]).loc[:, FEATURES], check_exact=True)
        checks.append(f'exact_prefix_{n}')
        changed = d.copy()
        changed.loc[n:, ['open', 'high', 'low', 'close']] *= 2.1
        changed.loc[n:, 'volume'] *= 7
        pd.testing.assert_frame_equal(whole.loc[:n-1, FEATURES], features(changed).loc[:n-1, FEATURES], check_exact=True)
        checks.append(f'exact_future_perturbation_{n}')
    row = dict(close=100., rsi=29., slowk=19., bb_lowerband=101., CDLHAMMER=100, sar=101., fisher_rsi=.4)
    assert rules(pd.DataFrame([row])).iloc[0].all()
    checks.append('conjunction_true_with_injected_feature_values_not_a_real_RSI_Fisher_pair')
    for col, value in [('rsi',30),('slowk',20),('bb_lowerband',100),('CDLHAMMER',99),('rsi',np.nan)]:
        q = {**row, col:value}; assert not rules(pd.DataFrame([q])).enter_long.iloc[0]
        checks.append(f'entry_boundary_{col}_{value}')
    for col, value in [('sar',100),('fisher_rsi',.3),('sar',np.nan)]:
        assert not rules(pd.DataFrame([{**row,col:value}])).exit_long.iloc[0]
        checks.append(f'exit_boundary_{col}_{value}')
    assert whole.bb_lowerband.isna().iloc[0] and np.isfinite(whole.bb_lowerband.iloc[1])
    tp=(d.high+d.low+d.close)/3
    expected = tp.iloc[:2].mean()-2*np.std(tp.iloc[:2],ddof=1)
    assert abs(whole.bb_lowerband.iloc[1]-expected)<1e-12
    checks.append('bollinger_min_periods1_ddof1_second_bar')
    assert not planned_exit_gate(100,100,0)
    assert planned_exit_gate(100.1,100,0)
    assert not planned_exit_gate(100.1,100,8)
    assert planned_exit_gate(100.3,100,8)
    assert not planned_exit_gate(99,100,8)
    checks.append('exit_profit_gate_strict_positive_fee_aware')
    for minute,target in [(0,.05),(19,.05),(20,.04),(29,.04),(30,.03),(59,.03),(60,.01),(120,.01)]:
        assert roi_at(minute)[1]==target
    checks.append('roi_exact_20_30_60_minute_boundaries')
    assert not (whole.enter_long & whole.exit_long).any()
    checks.append('observed_no_signal_collision_on_consistent_RSI_Fisher')
    return {'record_id':'M0304','status':'SYNTHETIC_FORMULA_PASS_NOT_DATA_OR_EXECUTION_PASS','synthetic_rows':len(d),'seed':304,'checks_passed':len(checks),'checks':checks,'synthetic_entry_count':int(whole.enter_long.sum()),'synthetic_exit_count':int(whole.exit_long.sum()),'historical_market_data_read':False,'historical_replay_count':0,'original_third_party_code_executed':False,'full_execution_engine_implemented':False,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'limits':'Finite prefix/perturbation evidence is not a universal causality proof. Formula probe has no order, ledger, or historical replay engine.'}

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output', type=Path); a=p.parse_args()
    result=validate()
    txt=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if a.output:
        with a.output.open('x') as f: f.write(txt)
    print(txt)
