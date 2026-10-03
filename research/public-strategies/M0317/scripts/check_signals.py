#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run original source AST and framework parameter constructors, without Freqtrade install.
No returns computed. Does not claim full Freqtrade resolver or execution parity.
"""
import argparse, ast, hashlib, json, pathlib, types, logging
from abc import ABC,abstractmethod
from collections.abc import Sequence
from typing import Any,Union
import numpy as np
import pandas as pd
import talib.abstract as ta
from run_replay import features,input_frame,sha,write,roi_at

def verify(d,source,parameters,interface):
    assert sha(source)=='1c483a549398a0244ca6d87f9736a76ed462056aca8a5ee9affd9aa65efd9393'
    pt=ast.parse(pathlib.Path(parameters).read_text())
    pc=[n for n in pt.body if isinstance(n,ast.ClassDef) and n.name in ['BaseParameter','NumericParameter','IntParameter','DecimalParameter']]
    ns={'ABC':ABC,'abstractmethod':abstractmethod,'Sequence':Sequence,'Any':Any,'Union':Union,'OperationalException':RuntimeError}
    exec(compile(ast.Module(body=pc,type_ignores=[]),str(parameters),'exec'),ns)
    it=ast.parse(pathlib.Path(interface).read_text());icl=next(n for n in it.body if isinstance(n,ast.ClassDef) and n.name=='IStrategy')
    defaults={n.target.id:ast.literal_eval(n.value) for n in icl.body if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id=='trailing_stop'}
    assert defaults['trailing_stop'] is False
    base=type('IStrategy',(),defaults);ns.update({'IStrategy':base,'DataFrame':pd.DataFrame,'ta':ta})
    tree=ast.parse(pathlib.Path(source).read_text());cl=next(x for x in tree.body if isinstance(x,ast.ClassDef));exec(compile(ast.Module(body=[cl],type_ignores=[]),str(source),'exec'),ns)
    strategy=ns['mabStra']();expected={'buy_mojo_ma_timeframe':7,'buy_fast_ma_timeframe':14,'buy_slow_ma_timeframe':28,'buy_div_min':.295,'buy_div_max':2.2545,'sell_mojo_ma_timeframe':7,'sell_fast_ma_timeframe':14,'sell_slow_ma_timeframe':28,'sell_div_min':2.8144,'sell_div_max':1.5459}
    actual={k:getattr(strategy,k).value for k in expected};assert actual==expected
    assert not hasattr(strategy,'buy_params') and not hasattr(strategy,'sell_params') and strategy.trailing_stop is False
    assert strategy.minimal_roi=={'0':.598,'644':.166,'3269':.115,'7289':0} and strategy.stoploss==-.128 and strategy.timeframe=='4h'
    f=strategy.populate_indicators(input_frame(d),{});f=strategy.populate_entry_trend(f,{});f=strategy.populate_exit_trend(f,{})
    z=features(d)
    for side in ['buy','sell']:
        for ma,period in [('mojo',7),('fast',14),('slow',28)]: np.testing.assert_allclose(f[f'{side}-{ma}MA'],z[f'sma{period}'],rtol=0,atol=0,equal_nan=True)
    np.testing.assert_array_equal(f.enter_long.fillna(0).eq(1),z.entry_signal);np.testing.assert_array_equal(f.exit_long.fillna(0).eq(1),z.exit_signal)
    analytic={p:d.close.rolling(p,min_periods=p).mean() for p in (7,14,28)}
    for p in analytic: np.testing.assert_allclose(analytic[p],z[f'sma{p}'],rtol=3e-14,atol=1e-8,equal_nan=True)
    ratio1=analytic[7]/analytic[14];ratio2=analytic[14]/analytic[28]
    np.testing.assert_array_equal((ratio1>.295)&(ratio1<2.2545)&(ratio2>.295)&(ratio2<2.2545),z.entry_signal)
    assert not z.exit_signal.any()
    cuts=sorted(set([1,6,7,13,14,27,28,186,187,600,680,700,1000,2000,3000,4000,len(d)]+list(range(50,len(d),53))))
    for cut in cuts:
        a=features(d.iloc[:cut].copy())
        for col in ['sma7','sma14','sma28','buy_ratio1','buy_ratio2','sell_ratio1','sell_ratio2']:
            np.testing.assert_allclose(a[col],z.iloc[:cut][col],rtol=0,atol=0,equal_nan=True)
        np.testing.assert_array_equal(a.entry_signal,z.iloc[:cut].entry_signal)
        np.testing.assert_array_equal(a.exit_signal,z.iloc[:cut].exit_signal)
    arr=pd.Series([float('nan'),float('inf'),.295, .295001, 2.254499,2.2545]);assert ((arr>.295)&(arr<2.2545)).tolist()==[False,False,False,True,True,False]
    for elapsed,key in [(0,0),(643,0),(644,644),(3268,644),(3269,3269),(7288,3269),(7289,7289)]:assert roi_at(elapsed,strategy.minimal_roi)[0]==key
    return {'status':'PASS','real_strategy_returns_read':False,'source_sha256':sha(source),'framework_parameters_sha256':sha(parameters),'framework_interface_sha256':sha(interface),
    'source_execution':'unaltered original class AST, original parameter constructor class AST, isolated IStrategy containing verified trailing_stop=False; no complete framework boot',
    'effective_parameter_values':actual,'out_of_hyperopt_bounds_preserved':['buy_div_max','sell_div_min'],'source_buy_params':None,'source_sell_params':None,
    'framework_trailing_default':False,'rows':len(d),'original_source_matches':True,'independent_pandas_rolling_matches':True,'prefix_cuts':cuts,'prefix_exact_matches':True,
    'warmup_nan_counts':{f'sma{p}':int(z[f'sma{p}'].isna().sum()) for p in (7,14,28)},'exit_interval_mathematically_empty':True,'roi_exact_minute_boundaries':'PASS','strict_threshold_boundary_tests':'PASS',
    'limits':'original author runtime unknown; parameter initialization is tested, full Freqtrade resolver/config/backtest is not run; no performance recovery claim'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--source',required=True);p.add_argument('--parameters',required=True);p.add_argument('--interface',required=True);p.add_argument('--output',required=True);a=p.parse_args();r=verify(pd.read_csv(a.input),a.source,a.parameters,a.interface);write(a.output,r);print(json.dumps(r,indent=2))
