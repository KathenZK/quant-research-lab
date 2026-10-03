#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent-source fidelity checks and full-future corruption/truncation tests.
This imports the main engine intentionally; the separate Decimal validator does not.
"""
import argparse,ast,json,pathlib,types
import numpy as np
import pandas as pd
import run_replay as engine

def original_functions(d):
    source=ast.parse((engine.ROOT/'sources/AverageStrategy.py').read_text());klass=next(x for x in source.body if isinstance(x,ast.ClassDef))
    methods=[x for x in klass.body if isinstance(x,ast.FunctionDef)]
    module=ast.Module(body=methods,type_ignores=[]);ns={'DataFrame':pd.DataFrame,'ta':engine.ta,'qtpylib':engine.Q};exec(compile(module,'pinned AverageStrategy methods','exec'),ns)
    obj=types.SimpleNamespace(buy_range_short=types.SimpleNamespace(value=8,range=[8]),buy_range_long=types.SimpleNamespace(value=21,range=[21]))
    z=d.copy()
    for name in ('populate_indicators','populate_entry_trend','populate_exit_trend'):z=ns[name](obj,z,{})
    return z

def run(input_path,spec_path):
    spec=json.loads(pathlib.Path(spec_path).read_text());d=engine.load_input(input_path,spec);full=engine.features(d);original=original_functions(d)
    for k in ('ema8','ema21'):np.testing.assert_array_equal(full[k],original[k])
    np.testing.assert_array_equal(full.entry_signal,original.enter_long.fillna(0));np.testing.assert_array_equal(full.exit_signal,original.exit_long.fillna(0))
    checks=[]
    for point,kind in [('2023-06-15T12:00:00Z','intraday Thursday noon'),('2023-07-03T00:00:00Z','UTC Monday week boundary'),('2024-12-02T00:00:00Z','UTC Monday late sample')]:
        cut=pd.Timestamp(point).value//10**6;k=int(np.flatnonzero(d.open_time>=cut)[0]);changed=d.copy()
        changed.loc[k:,['open','high','low','close']]*=7;changed.loc[k:,'volume']*=3
        new=engine.features(changed);short=engine.features(d.iloc[:k].copy())
        pd.testing.assert_frame_equal(full.iloc[:k],new.iloc[:k],check_exact=True);pd.testing.assert_frame_equal(full.iloc[:k],short,check_exact=True)
        cases=[]
        for case in spec['cases']:
            nav,_,trade,_=engine.replay(full,spec,case);other,_,otrade,_=engine.replay(new,spec,case)
            pd.testing.assert_frame_equal(nav[nav.bar_index<k].reset_index(drop=True),other[other.bar_index<k].reset_index(drop=True),check_exact=True)
            a=trade[trade.bar_index<k].reset_index(drop=True);b=otrade[otrade.bar_index<k].reset_index(drop=True)
            pd.testing.assert_frame_equal(a,b,check_exact=True,check_dtype=False)
            cases.append({'case':case['name'],'prefix_bars':int((nav.bar_index<k).sum()),'prefix_trades':len(a),'status':'PASS'})
        checks.append({'perturb_from_inclusive':point,'boundary_type':kind,'action':'future OHLC times 7, volume times 3; independent feature truncation','cases':cases})
    return {'status':'PASS','source_methods_match':'All EMA8/EMA21, entry and exit signals bit-identical to original pinned AverageStrategy method AST; default parameters only','future_perturbation':checks,'limitation':'Tests enforce computational causality, not historical PIT/version availability or intrabar path truth'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--spec',default=str(engine.ROOT/'specs/M0256-first-replay.json'));p.add_argument('--output',required=True);a=p.parse_args();r=run(a.input,a.spec);pathlib.Path(a.output).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
