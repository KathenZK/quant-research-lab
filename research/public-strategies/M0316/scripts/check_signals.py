#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Load exact private upstream strategy with a minimal interface, compare TA outputs."""
import argparse,ast,hashlib,json,pathlib,sys,types,importlib.util
import numpy as np,pandas as pd,talib.abstract as ta
from run_replay import features,sha,write,load_input
EXPECTED='bd4523d134b686b012947896ffd7a5a299add87ac12aa0d18fac36c9e7ca3822'
def native(source,d):
    assert sha(source)==EXPECTED
    # Exact pinned qtpylib semantics: current strict, previous inclusive.
    def cross(a,b,above=True):
        if not isinstance(b,pd.Series):b=pd.Series(b,index=a.index)
        return ((a>b)&(a.shift(1)<=b.shift(1))) if above else ((a<b)&(a.shift(1)>=b.shift(1)))
    fq=types.ModuleType('freqtrade');strategy=types.ModuleType('freqtrade.strategy');strategy.IStrategy=object
    vendor=types.ModuleType('freqtrade.vendor');qt=types.ModuleType('freqtrade.vendor.qtpylib');ind=types.ModuleType('freqtrade.vendor.qtpylib.indicators');ind.crossed_above=lambda a,b:cross(a,b);ind.crossed_below=lambda a,b:cross(a,b,False)
    for name,x in [('freqtrade',fq),('freqtrade.strategy',strategy),('freqtrade.vendor',vendor),('freqtrade.vendor.qtpylib',qt),('freqtrade.vendor.qtpylib.indicators',ind)]:sys.modules[name]=x
    spec=importlib.util.spec_from_file_location('source_hlhb',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);obj=m.hlhb()
    f=d[['open','high','low','close','volume']].copy();f=obj.populate_indicators(f,{});f=obj.populate_entry_trend(f,{});f=obj.populate_exit_trend(f,{})
    return f,obj
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    d=pd.read_csv(a.input);z=features(d);n,o=native(a.source,d)
    for c in ['hl2','rsi','ema5','ema10','adx']:assert np.allclose(z[c],n[c],equal_nan=True,rtol=0,atol=1e-12),c
    for ours,theirs in [('entry_signal','enter_long'),('exit_signal','exit_long')]:assert np.array_equal(z[ours].iloc[30:],n[theirs].fillna(0).astype(bool).iloc[30:])
    assert o.timeframe=='4h' and o.startup_candle_count==30 and o.position_stacking=='True'
    assert o.minimal_roi=={'0':.6225,'703':.2187,'2849':.0363,'5520':0};assert o.stoploss==-.3211
    assert o.trailing_stop and o.trailing_stop_positive==.0117 and o.trailing_stop_positive_offset==.0186 and o.trailing_only_offset_is_reached
    assert o.ignore_roi_if_entry_signal and o.use_exit_signal and not o.exit_profit_only
    checks=[]
    for cut in [31,80,185,186,300,678,679,680,1500,2500,3500,4571]:
        pre=features(d.iloc[:cut].copy())
        for c in ['hl2','rsi','ema5','ema10','adx','entry_signal','exit_signal']:assert np.allclose(pre[c],z[c].iloc[:cut],rtol=0,atol=1e-12,equal_nan=True),c
        checks.append(cut)
    rng=np.random.default_rng(316);syn=d.iloc[:96].copy();syn['open']=100+np.cumsum(rng.normal(0,2,96));syn['close']=syn.open+rng.normal(0,2,96);syn['high']=syn[['open','close']].max(axis=1)+3;syn['low']=syn[['open','close']].min(axis=1)-3
    ns,_=native(a.source,syn);fs=features(syn)
    for c in ['hl2','rsi','ema5','ema10','adx']:assert np.allclose(fs[c],ns[c],rtol=0,atol=1e-12,equal_nan=True)
    write(a.output,{'status':'PASS_SOURCE_INDICATORS_SIGNALS_PREFIX','source_sha256':sha(a.source),'input_sha256':sha(a.input),'rows':len(d),'columns':['hl2','rsi','ema5','ema10','adx'],'native_class_called':True,'framework_interface_stub':True,'qtpylib_cross_semantics_reimplemented_not_original_runtime':True,'prefix_lengths':checks,'synthetic_bars':96,'strategy_return_computed':False,'startup_bars':30,'position_stacking_runtime_assumption':False})
