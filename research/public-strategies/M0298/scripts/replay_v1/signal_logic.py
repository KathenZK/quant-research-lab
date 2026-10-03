#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""M0298 source AST inspection + synthetic diagnostics; never reads market data.
Third-party source is parsed only, never compiled/imported/executed.
No historical replay, download, order execution, or parameter search is provided.
"""
from __future__ import annotations
import argparse, ast, hashlib, json, os, platform, resource
from pathlib import Path
import numpy as np
import pandas as pd
import talib
from talib import abstract

EXPECTED_SOURCE='812a8d63b0e0ddff6b9bae582c4d573ab9a4ffec6dd0d1c5b8f8180f11db6d0b'
BUDGET=1024**3

def sha(b): return hashlib.sha256(b).hexdigest()
def dump(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as f: json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')

def source_audit(path):
    raw=Path(path).read_bytes()
    assert len(raw)==2695 and sha(raw)==EXPECTED_SOURCE
    tree=ast.parse(raw)
    classes=[n for n in tree.body if isinstance(n,ast.ClassDef)]
    assert len(classes)==1 and classes[0].name=='Simple'
    cls=classes[0]
    attrs={n.target.id if isinstance(n,ast.AnnAssign) else n.targets[0].id:ast.literal_eval(n.value)
           for n in cls.body if isinstance(n,(ast.Assign,ast.AnnAssign))}
    assert attrs=={'INTERFACE_VERSION':3,'minimal_roi':{'0':0.01},'stoploss':-0.25,'timeframe':'5m'}
    methods={n.name:n for n in cls.body if isinstance(n,ast.FunctionDef)}
    assert set(methods)=={'populate_indicators','populate_entry_trend','populate_exit_trend'}
    calls=[ast.unparse(n) for n in ast.walk(methods['populate_indicators']) if isinstance(n,ast.Call)]
    expected=["ta.MACD(dataframe)","ta.RSI(dataframe, timeperiod=7)","qtpylib.bollinger_bands(dataframe['close'], window=12, stds=2)"]
    assert calls==expected
    conditions={}
    for side in ('entry','exit'):
        method=methods[f'populate_{side}_trend']
        assignment=next(n for n in method.body if isinstance(n,ast.Assign))
        assert len(assignment.targets)==1 and ast.literal_eval(assignment.value)==1
        target=assignment.targets[0]
        assert isinstance(target,ast.Subscript) and isinstance(target.slice,ast.Tuple)
        conditions[side]=ast.unparse(target.slice.elts[0])
        assert ast.literal_eval(target.slice.elts[1])==('enter_long' if side=='entry' else 'exit_long')
    assert conditions['entry']=="(dataframe['macd'] > 0) & (dataframe['macd'] > dataframe['macdsignal']) & (dataframe['bb_upperband'] > dataframe['bb_upperband'].shift(1)) & (dataframe['rsi'] > 70)"
    assert conditions['exit']=="dataframe['rsi'] > 80"
    return {'status':'PASS_AST_ONLY','source_bytes':len(raw),'source_sha256':sha(raw),
            'class':'Simple','all_explicit_class_attributes':attrs,'indicator_calls':calls,
            'raw_signal_conditions':conditions,'method_ast_sha256':{k:sha(ast.dump(v,include_attributes=False).encode()) for k,v in methods.items()},
            'third_party_code_executed':False,'market_data_read':False}

def signals(macd,signal,upper,previous_upper,rsi):
    entry=(macd>0)&(macd>signal)&(upper>previous_upper)&(rsi>70)
    exit_=rsi>80
    return entry,exit_

def indicators(close):
    close=pd.Series(np.asarray(close,dtype=np.float64))
    assert talib.get_compatibility()==0
    assert talib.get_unstable_period('RSI')==0 and talib.get_unstable_period('EMA')==0
    macd,signal,hist=talib.MACD(close.to_numpy(),fastperiod=12,slowperiod=26,signalperiod=9)
    rsi=talib.RSI(close.to_numpy(),timeperiod=7)
    mid=close.rolling(window=12,min_periods=1).mean()
    std=close.rolling(window=12,min_periods=1).std(ddof=1)
    upper=mid+2*std
    entry,exit_=signals(macd,signal,upper,upper.shift(1),rsi)
    return pd.DataFrame({'macd':macd,'macdsignal':signal,'macdhist':hist,'rsi':rsi,
                         'bb_lowerband':mid-2*std,'bb_middleband':mid,'bb_upperband':upper,
                         'enter_long':entry,'exit_long':exit_})

def limit_boundary(side,limit,open_,high,low):
    """Draft touch-fill convention, one eligible bar only; no historical runner."""
    assert side in ('buy','sell') and low<=open_<=high
    if side=='buy':
        return (open_,'open') if open_<=limit else ((limit,'intrabar') if low<=limit else (None,'timeout_cancel'))
    return (open_,'open') if open_>=limit else ((limit,'intrabar') if high>=limit else (None,'timeout_cancel'))

def effective_signals(entry,exit_):
    return bool(entry and not exit_),bool(exit_ and not entry)

def run_synthetic():
    # Deterministic, invented price series. No real prices, downloads or random search.
    n=2400;x=np.arange(n,dtype=float)
    close=100+0.013*x+4*np.sin(x/17)+2*np.cos(x/31)+0.7*np.sin(x/3)
    full=indicators(close)
    checks=[]
    for cut in (120,800,1700):
        prefix=indicators(close[:cut]);pd.testing.assert_frame_equal(prefix,full.iloc[:cut],check_exact=True)
        future=close.copy();future[cut:]=future[cut:]*(1.2+0.1*np.sin(x[cut:]))
        altered=indicators(future);pd.testing.assert_frame_equal(altered.iloc[:cut],full.iloc[:cut],check_exact=True)
        checks.append({'prefix_rows':cut,'prefix_identical':True,'future_perturbation_prefix_identical':True})
    # Independent elementary BB sample-moment check on synthetic windows.
    for end in (1,5,11,50,2399):
        a=close[max(0,end-11):end+1];mean=sum(map(float,a))/len(a)
        var=sum((float(z)-mean)**2 for z in a)/(len(a)-1)
        assert abs(float(full.bb_upperband.iloc[end])-(mean+2*var**0.5))<1e-9
    threshold_tests=[]
    for rsi,e,xit in ((70,False,False),(70.0001,True,False),(80,True,False),(80.0001,True,True),(90,True,True)):
        got=signals(2.,1.,11.,10.,rsi);assert tuple(map(bool,got))==(e,xit)
        threshold_tests.append({'rsi':rsi,'raw_entry':e,'raw_exit':xit,'effective_entry_exit':effective_signals(e,xit)})
    assert signals(0.,-1.,11.,10.,90.)==(False,True)
    assert signals(1.,1.,11.,10.,90.)==(False,True)
    assert signals(2.,1.,10.,10.,90.)==(False,True)
    assert signals(np.nan,1.,11.,10.,90.)==(False,True)
    assert effective_signals(True,True)==(False,False)
    assert effective_signals(False,True)==(False,True)
    orders=[('buy',100,99,103,98,(99,'open')),('buy',100,101,103,100,(100,'intrabar')),
            ('buy',100,101,103,100.01,(None,'timeout_cancel')),
            ('sell',100,101,102,98,(101,'open')),('sell',100,99,100,98,(100,'intrabar')),
            ('sell',100,99,99.99,98,(None,'timeout_cancel'))]
    for side,limit,open_,high,low,wanted in orders: assert limit_boundary(side,limit,open_,high,low)==wanted
    grid=pd.date_range('2024-01-01T00:00:00Z','2025-01-01T00:00:00Z',inclusive='left',freq='5min')
    assert len(grid)==105408 and grid[1]-grid[0]==pd.Timedelta(minutes=5)
    assert pd.Timestamp('2024-01-01T23:55:00Z')+pd.Timedelta(minutes=5)==pd.Timestamp('2024-01-02T00:00:00Z')
    assert full.enter_long.dtype=='bool' and full.exit_long.dtype=='bool'
    assert full.loc[:32,'macd'].isna().all() and full.macd.iloc[33:].notna().all()
    assert full.rsi.iloc[:7].isna().all() and full.rsi.iloc[7:].notna().all()
    return {'status':'PASS_SYNTHETIC_ONLY','invented_bars':n,'causal_prefix_checks':checks,
            'rsi_threshold_collision_tests':threshold_tests,'limit_boundary_test_count':len(orders),
            'bb_independent_moment_checks':5,'native_5m_2024_grid_rows':len(grid),
            'nan_warmup_checked':True,'first_MACD_valid_index':33,'first_RSI_valid_index':7,
            'signal_collision_policy':'raw signals retained; entry and signal exit both suppressed; ROI remains independently eligible in draft plan',
            'all_tests_passed':True,'historical_runs':0,'historical_ledger_validation':'NOT_RUN',
            'universal_causality_proof':False,'execution_engine_validation':'LIMIT_BOUNDARY_HELPER_ONLY_NOT_HISTORICAL_ENGINE'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    assert [np.__version__,pd.__version__,talib.__version__]==['2.3.5','2.2.3','0.6.8']
    assert talib.__ta_version__.decode().split()[0]=='0.6.4'
    assert dict(abstract.Function('MACD').parameters)=={'fastperiod':12,'slowperiod':26,'signalperiod':9}
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):assert os.environ.get(key)=='1',key
    report={'record_id':'M0298','stage':'BLOCKED_SOURCE_INPUT','historical_runs':0,
            'source':source_audit(a.source),'synthetic':run_synthetic(),
            'environment':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,
              'TA_Lib_python':talib.__version__,'TA_Lib_C':talib.__ta_version__.decode(),
              'compatibility':talib.get_compatibility(),'unstable_period_RSI':talib.get_unstable_period('RSI'),
              'unstable_period_EMA':talib.get_unstable_period('EMA'),'blas_threads':1,
              'script_sha256':sha(Path(__file__).read_bytes())},
            'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            'peak_budget_bytes':BUDGET}
    assert report['peak_rss_bytes']<BUDGET
    dump(a.output,report);print(json.dumps({'stage':report['stage'],'synthetic':'PASS','historical_runs':0,'peak_rss_bytes':report['peak_rss_bytes']}))
if __name__=='__main__':main()
