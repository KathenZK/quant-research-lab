#!/usr/bin/env python3
"""Deterministic feature-transform counterexample. Synthetic only; no returns.
SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse,hashlib,importlib.metadata,json,os,resource,warnings
from datetime import datetime,timezone
from pathlib import Path
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import numpy as np
import pandas as pd
from ta import add_all_ta_features
from ta.utils import dropna

def h(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def transform(f):
 with warnings.catch_warnings():
  warnings.simplefilter('ignore',FutureWarning)
  return add_all_ta_features(dropna(f.copy()),open='open',high='high',low='low',close='close',volume='volume',fillna=True)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);a=ap.parse_args()
 x=np.arange(240,dtype=float);price=100+.1*x+np.sin(x/7)
 f=pd.DataFrame({'open':price,'high':price+1.2,'low':price-.8,'close':price+.2*np.sin(x),'volume':100+x})
 full=transform(f);assert len(full)==240
 checks=[]
 for n in [62,80,124,239]:
  short=transform(f.iloc[:n]);changed={}
  for c in full.select_dtypes(include=np.number).columns:
   bad=np.flatnonzero(~np.isclose(full[c].iloc[:n],short[c],rtol=1e-12,atol=1e-10,equal_nan=True))
   if len(bad):changed[c]={'count':len(bad),'first_index':int(bad[0]),'last_index':int(bad[-1]),'max_abs_difference':float(np.nanmax(np.abs(full[c].iloc[:n].to_numpy()-short[c].to_numpy())))}
  checks.append({'prefix_rows':n,'changed_columns':changed,'active_columns':{c:changed.get(c,{'count':0}) for c in ['trend_ichimoku_base','trend_kst_diff']},'evaluation_rows_changed':{c:int(sum(~np.isclose(full[c].iloc[62:n],short[c].iloc[62:n],rtol=1e-12,atol=1e-10,equal_nan=True))) for c in ['trend_ichimoku_base','trend_kst_diff']}})
 result={'schema':'godstra-synthetic-counterexample/v1','id':'M0274','at_utc':datetime.now(timezone.utc).isoformat(),'input':'synthetic_indicator_only_not_market_evidence','synthetic_formula':'x=arange(240); p=100+0.1*x+sin(x/7); open=p; high=p+1.2; low=p-0.8; close=p+0.2*sin(x); volume=100+x','rows':len(f),'synthetic_ohlcv_sha256':hashlib.sha256(f.to_csv(index=False,lineterminator='\n').encode()).hexdigest(),'status':'FAIL_FULL_TRANSFORM_PREFIX_CAUSALITY','checks':checks,'script_sha256':h(__file__),'dependencies':{p:importlib.metadata.version(p) for p in ['ta','numpy','pandas']},'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'strategy_returns_computed':False,'strict_reproductions':0,'complete_real_window_audit':'NOT_RUN_INCOMPLETE_INPUT','warning':'No conclusion about actual evaluation signals is inferred from synthetic counterexamples; full transform causality fails, selected synthetic columns show only pre-62 warmup KST revisions.'}
 assert all(len(c['changed_columns'])==11 for c in checks)
 with Path(a.out).open('x') as out:json.dump(result,out,ensure_ascii=False,indent=2,sort_keys=True);out.write('\n')
 print(json.dumps({'status':result['status'],'synthetic_ohlcv_sha256':result['synthetic_ohlcv_sha256'],'changed_columns':11,'peak_rss_kib':result['peak_rss_kib']}))
