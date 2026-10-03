#!/usr/bin/env python3
"""Execute the exact hash-verified author's signal methods and compare the port.
The IStrategy import is shimmed ONLY to instantiate the source's pure methods.
No claim of running a configured Freqtrade backtester or full strategy lifecycle.
GPL-3.0-or-later; authored 2026-10-03.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import numpy as np
from replay import load_data,load_qtp,indicators

STRATEGY_SHA='65718e8d0c14094b67be82b66238ea60a4af4bbf6fd9a6e1879dad5c48125547'

def compare(data,source,qtp_path):
    content=Path(source).read_bytes()
    if hashlib.sha256(content).hexdigest()!=STRATEGY_SHA:raise ValueError('Original strategy MISMATCH')
    qtp=load_qtp(qtp_path)
    own=indicators(data,qtp)
    freqtrade=types.ModuleType('freqtrade');freqtrade.__path__=[]
    strategy=types.ModuleType('freqtrade.strategy');strategy.IStrategy=type('IStrategy',(),{})
    vendor=types.ModuleType('freqtrade.vendor');vendor.__path__=[]
    qtp_parent=types.ModuleType('freqtrade.vendor.qtpylib');qtp_parent.__path__=[]
    qtp_parent.indicators=qtp;vendor.qtpylib=qtp_parent;freqtrade.strategy=strategy;freqtrade.vendor=vendor
    injected={'freqtrade':freqtrade,'freqtrade.strategy':strategy,'freqtrade.vendor':vendor,
              'freqtrade.vendor.qtpylib':qtp_parent,'freqtrade.vendor.qtpylib.indicators':qtp}
    old={k:sys.modules.get(k) for k in injected}
    try:
        sys.modules.update(injected)
        spec=importlib.util.spec_from_file_location('exact_BbandRsi',source)
        original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
        obj=original.BbandRsi()
        actual=obj.populate_indicators(data.copy(),{})
        actual=obj.populate_entry_trend(actual,{})
        actual=obj.populate_exit_trend(actual,{})
        errors={}
        for port,key in [('rsi','rsi'),('bb_lower','bb_lowerband'),('bb_mid','bb_middleband'),('bb_upper','bb_upperband')]:
            np.testing.assert_array_equal(own[port].to_numpy(),actual[key].to_numpy())
            errors[port]=0.
        np.testing.assert_array_equal(own.entry.to_numpy(),actual.enter_long.fillna(0).eq(1).to_numpy())
        np.testing.assert_array_equal(own.exit.to_numpy(),actual.exit_long.fillna(0).eq(1).to_numpy())
        assert obj.minimal_roi=={'0':.1} and obj.stoploss==-.25 and obj.timeframe=='1h'
    finally:
        for k,v in old.items():
            if v is None:sys.modules.pop(k,None)
            else:sys.modules[k]=v
    return {'status':'PASS','source_sha256':STRATEGY_SHA,'rows':len(data),'exact_indicator_differences':errors,
            'entry_mismatches':0,'exit_mismatches':0,'risk_parameters':{'minimal_roi':{'0':.1},'stoploss':-.25,'timeframe':'1h'},
            'method':'execute unchanged original populate methods using import-only IStrategy shim; exact NaN-aware array equality',
            'limitation':'full configured Freqtrade strategy/backtester not executed'}

def main():
    p=argparse.ArgumentParser()
    for x in ['input','source','qtpylib','out']:p.add_argument('--'+x,required=True)
    a=p.parse_args();d=load_data(a.input);result=compare(d,a.source,a.qtpylib)
    result['input_sha256']=hashlib.sha256(Path(a.input).read_bytes()).hexdigest()
    with open(a.out,'x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print('PASS exact original-class indicators / signals / source risks')
if __name__=='__main__':main()
