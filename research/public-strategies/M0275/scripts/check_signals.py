#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""No return calculation: original AST methods, explicit formula, prefix causality."""
import argparse, ast, hashlib, json, pathlib, types
from functools import reduce
import numpy as np
import pandas as pd
import ta
from ta.utils import dropna
from run_replay import features,input_frame,sha,write,roi_at

def verify(d,source):
    assert sha(source)=='5b25d85297329243d7a3c65770975b5a70e52ec2684b1e007e5d8a3d1a7e3718'
    tree=ast.parse(pathlib.Path(source).read_text());cl=next(x for x in tree.body if isinstance(x,ast.ClassDef));values={}
    for node in cl.body:
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name):
            try: values[node.targets[0].id]=ast.literal_eval(node.value)
            except (ValueError,TypeError):pass
    assert values['buy_params']=={'buy_crossed_indicator_shift':9,'buy_div_max':.75,'buy_div_min':.16,'buy_indicator_shift':15}
    assert values['minimal_roi']=={'0':.598,'644':.166,'3269':.115,'7289':0}
    assert values['stoploss']==-.256 and values['timeframe']=='4h'
    methods=[x for x in cl.body if isinstance(x,ast.FunctionDef)]
    ns={'DataFrame':pd.DataFrame,'dropna':dropna,'ta':ta,'reduce':reduce}
    exec(compile(ast.Module(body=methods,type_ignores=[]),str(source),'exec'),ns)
    strategy=types.SimpleNamespace(**{k:types.SimpleNamespace(value=v) for k,v in values['buy_params'].items()})
    f=ns['populate_indicators'](strategy,input_frame(d),{});f=ns['populate_entry_trend'](strategy,f,{});f=ns['populate_exit_trend'](strategy,f,{})
    z=features(d);assert f.index.equals(d.index)
    np.testing.assert_allclose(f.volatility_kcw,z.kcw,rtol=0,atol=0,equal_nan=True);np.testing.assert_allclose(f.volatility_dcp,z.dcp,rtol=0,atol=0,equal_nan=True)
    np.testing.assert_array_equal(f.enter_long.fillna(0).eq(1),z.entry_signal);assert f.exit_long.eq(0).all()
    # Independent analytic implementation, does not call ta.
    H=d.high.rolling(10,min_periods=10).max();L=d.low.rolling(10,min_periods=10).min()
    dcp=(d.close-L)/(H-L)
    center=((d.high+d.low+d.close)/3).rolling(20,min_periods=20).mean()
    top=((4*d.high-2*d.low+d.close)/3).rolling(20,min_periods=0).mean()
    bottom=((-2*d.high+4*d.low+d.close)/3).rolling(20,min_periods=0).mean()
    kcw=100*(top-bottom)/center;ratio=dcp.shift(15)/kcw.shift(9)
    np.testing.assert_allclose(z.ratio,ratio,rtol=2e-14,atol=2e-14,equal_nan=True)
    np.testing.assert_array_equal(z.entry_signal,ratio.between(.16,.75))
    cuts=sorted(set([1,9,10,15,19,20,24,25,28,29,30,186,187,600,680,700,1000,2000,3000,4000,len(d)]+list(range(50,len(d),53))))
    for cut in cuts:
        a=features(d.iloc[:cut].copy())
        for col in ['dcp','kcw','ratio']:
            np.testing.assert_allclose(a[col],z.iloc[:cut][col],rtol=0,atol=0,equal_nan=True)
        np.testing.assert_array_equal(a.entry_signal,z.iloc[:cut].entry_signal)
    # dropna zero handling and threshold inclusivity are explicit, never silently filled.
    zero=input_frame(d.iloc[:40]).copy();zero.loc[2,'volume']=0
    assert 2 not in dropna(zero).index
    arr=pd.Series([float('nan'),float('inf'),-.1,.159,.16,.75,.751]);assert arr.between(.16,.75).tolist()==[False,False,False,False,True,True,False]
    for elapsed,key in [(0,0),(643,0),(644,644),(3268,644),(3269,3269),(7288,3269),(7289,7289)]: assert roi_at(elapsed,values['minimal_roi'])[0]==key
    return {'status':'PASS','real_strategy_returns_read':False,'source_sha256':sha(source),'source_function_execution':'unaltered AST bodies of populate_indicators/populate_entry_trend/populate_exit_trend; explicit buy_params values, no full Freqtrade runtime',
      'rows':len(d),'original_source_signal_matches':True,'independent_formula_matches':True,'prefix_cuts':cuts,'prefix_exact_matches':True,
      'source_dropna_removed_actual_rows':0,'input_columns':['date','open','high','low','close','volume'],'warmup_nan_counts':{c:int(z[c].isna().sum()) for c in ['dcp','kcw','ratio']},
      'first_defined_ratio_index':int(z.ratio.first_valid_index()),'shift':{'donchian':15,'keltner':9},'roi_exact_minute_boundary_tests':'PASS','zero_and_nan_tests':'PASS',
      'limits':'finite tested prefixes plus analytically backward-only rolling/positive shifts; not proof of framework trading parity'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args();r=verify(pd.read_csv(a.input),a.source);write(a.output,r);print(json.dumps(r,indent=2))
