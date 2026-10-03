#!/usr/bin/env python3
"""GodStra feature-prefix diagnostic only. No backtest, returns or repairs.
SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse, hashlib, importlib.metadata, json, os, resource, time, warnings
from datetime import datetime, timezone
from pathlib import Path
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
import numpy as np
import pandas as pd
import ta
from ta import add_all_ta_features
from ta.utils import dropna

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
def pipeline(frame):
    # Exact Freqtrade OHLCV shape, not the archive's ignore=0 column.
    clean=dropna(frame.copy())
    if len(clean)!=len(frame):
        raise ValueError('DROPNA_REMOVED_INPUT_ROWS: no implicit grid repair permitted')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', FutureWarning)
        warnings.simplefilter('ignore', RuntimeWarning)
        return add_all_ta_features(clean,open='open',high='high',low='low',close='close',volume='volume',fillna=True)

def audit(args):
    started=now(); tick=time.monotonic()
    root=Path(args.snapshot); frozen=json.loads(Path(args.contract).read_text())
    manifest=json.loads((root/'manifest.json').read_text())
    path=root/manifest['canonical_csv']['path']
    assert sha(path)==manifest['canonical_csv']['sha256']==frozen['canonical_input_sha256']
    assert manifest['timeframe']=='12h' and manifest['canonical_csv']['rows']==1524
    assert frozen['performance_results_seen'] is False
    assert importlib.metadata.version('ta')=='0.11.0'
    dep_path=Path(args.contract).parent.parent/'artifacts/dependencies-v1.json'
    deps=json.loads(dep_path.read_text())
    for p,v in deps['packages'].items(): assert importlib.metadata.version(p)==v
    for f in deps['ta_module_files']:
        assert sha(Path(ta.__file__).parent/f['module'])==f['sha256']
    raw=pd.read_csv(path)
    frame=raw[['open','high','low','close','volume']].copy()
    frame.insert(0,'date',pd.to_datetime(raw['ts'],utc=True))
    full=pipeline(frame)
    columns=[c for c in full.columns if c not in frame.columns]
    selected=['trend_ichimoku_base','trend_kst_diff']
    tests=[]; aggregate={}
    for length in [64,96,128,256,512,1024,1523]:
        cropped=pipeline(frame.iloc[:length].copy())
        assert cropped.index.equals(full.iloc[:length].index)
        details=[]
        for col in columns:
            a=full.loc[cropped.index,col].to_numpy(dtype=float)
            b=cropped[col].to_numpy(dtype=float)
            exact=~((a==b)|(np.isnan(a)&np.isnan(b)))
            unequal=~np.isclose(a,b,rtol=1e-12,atol=1e-12,equal_nan=True)
            ix=np.flatnonzero(unequal)
            if len(ix):
                ev=ix[ix>=62]
                finite=np.isfinite(a)&np.isfinite(b)
                detail={'column':col,'changed_rows_exact':int(exact.sum()),'changed_rows_tolerance':len(ix),'first_changed_index':int(ix[0]),'last_changed_index':int(ix[-1]),'changed_evaluation_rows':len(ev),'max_absolute_difference':float(np.max(np.abs(a[finite]-b[finite]))) if finite.any() else None,'last_observation_changed':bool(unequal[-1])}
                details.append(detail)
                acc=aggregate.setdefault(col,{'prefix_tests_with_changes':0,'first_changed_index':int(ix[0]),'last_changed_index':int(ix[-1]),'max_changed_evaluation_rows_in_one_test':0,'max_absolute_difference':0.0})
                acc['prefix_tests_with_changes']+=1
                acc['first_changed_index']=min(acc['first_changed_index'],int(ix[0]))
                acc['last_changed_index']=max(acc['last_changed_index'],int(ix[-1]))
                acc['max_changed_evaluation_rows_in_one_test']=max(acc['max_changed_evaluation_rows_in_one_test'],len(ev))
                acc['max_absolute_difference']=max(acc['max_absolute_difference'],detail['max_absolute_difference'] or 0)
        pred={}
        for key,fn in [('entry',lambda f:f['trend_ichimoku_base'].to_numpy()<0.06295),('exit',lambda f:np.isclose(f['trend_kst_diff'].to_numpy(),0.8779))]:
            a=fn(full.iloc[:length]);b=fn(cropped); changed=np.flatnonzero(a!=b)
            pred[key]={'changed_rows':len(changed),'changed_evaluation_rows':int(sum(changed>=62))}
        tests.append({'prefix_rows':length,'last_prefix_bar_open_utc':str(frame.iloc[length-1]['date']),'changed_columns':details,'selected_predicate_comparison':pred})
    result={'schema':'godstra-causality-audit/v1','id':'M0274','started_at_utc':started,'completed_at_utc':now(),'pid':os.getpid(),'elapsed_seconds':time.monotonic()-tick,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'audit_script_sha256':sha(__file__),'contract_sha256':sha(args.contract),'source_sha256':frozen['source_sha256'],'input_sha256':sha(path),'dependency_manifest_sha256':sha(dep_path),'pipeline':'exact ta.utils.dropna then ta.add_all_ta_features(fillna=True) under source-shaped six columns','feature_columns':columns,'feature_count':len(columns),'input_rows':len(frame),'warmup_rows':62,'evaluation_rows':len(frame)-62,'input_rows_dropped':0,'comparison_tolerance':{'rtol':1e-12,'atol':1e-12},'full_pipeline_status':'FAIL_FUTURE_DEPENDENCE' if aggregate else 'PASS_TESTED_PREFIXES_ONLY','changed_column_summary':aggregate,'selected_column_summary':{c:aggregate.get(c,{'prefix_tests_with_changes':0}) for c in selected},'prefix_tests':tests,'source_signal_diagnostic':{'entry_true_evaluation_rows':int((full.iloc[62:]['trend_ichimoku_base']<0.06295).sum()),'exit_true_evaluation_rows':int(np.isclose(full.iloc[62:]['trend_kst_diff'],0.8779).sum()),'is_trade_result':False},'decision':'BLOCK_ORIGINAL_IMPLEMENTATION' if aggregate else 'CAUSALITY_PREFIX_TESTS_PASS_NOT_FULL_PROOF','performance_engine_executed':False,'strategy_returns_computed':False,'benchmark_returns_computed':False,'limitations':['Finite prefixes cannot prove absence of every future dependency. A single observed prefix revision is sufficient to fail the frozen full-pipeline gate.','No assertion that warmup-only KST changes altered evaluation-period signals.','Signal predicate counts are diagnostics only; zero entries must not be promoted to a completed zero-trade backtest.','No changes to ta fillna, indicator selection, source threshold or author rules.']}
    with Path(args.out).open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({k:result[k] for k in ['started_at_utc','completed_at_utc','full_pipeline_status','changed_column_summary','selected_column_summary','source_signal_diagnostic','decision','peak_rss_kib']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',required=True);p.add_argument('--contract',required=True);p.add_argument('--out',required=True)
    audit(p.parse_args())
