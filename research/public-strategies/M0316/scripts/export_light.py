#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse,json,pathlib,shutil,hashlib
import pandas as pd
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):
    with p.open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
p=argparse.ArgumentParser();p.add_argument('--work',required=True);a=p.parse_args();w=pathlib.Path(a.work);out=ROOT/'artifacts/results';out.mkdir(exist_ok=False);s=json.loads((w/'summary.json').read_text());spec=json.loads((ROOT/'specs/protocol.json').read_text());shutil.copyfile(w/'summary.json',out/'summary.json');metrics=[];years=[];curves={};diag={}
for name,result in s['results'].items():
    metrics.append({'case':name,**result['metrics']});d=pd.read_csv(w/f'{name}-daily-nav.csv');t=pd.read_csv(w/f'{name}-trades.csv');events=json.loads((w/f'{name}-events.json').read_text());last=100000
    for year,g in d.groupby(d.date.str[:4]):end=float(g.iloc[-1].equity);years.append({'case':name,'year':year,'marked_return':end/last-1});last=end
    month=d.groupby(d.date.str[:7]).tail(1);curves[name]=dict(zip(month.timestamp_utc,month.nav));diag[name]={'exit_reason_counts':t[t.side=='SELL'].reason.value_counts().to_dict(),'order_status_counts':pd.Series([e['status'] for e in events['orders']]).value_counts().to_dict(),'roi_boundary_candidates':len(events['roi_boundaries']),'trailing_activations':result['metrics']['trailing_activations'],'roi_suppressed_position_bars':result['metrics']['roi_suppressed_position_bars']}
pd.DataFrame(metrics).to_csv(out/'metrics.csv',index=False,float_format='%.17g');pd.DataFrame(years).to_csv(out/'calendar-year-attribution.csv',index=False,float_format='%.17g');curve=pd.DataFrame(curves);curve.index.name='timestamp_utc';curve.loc[spec['evaluation']['start']]=1;curve.sort_index().to_csv(out/'month-end-nav-light.csv',float_format='%.17g');shutil.copyfile(w/'base-trades.csv',out/'base-trades.csv');write(out/'trade-diagnostics.json',diag)
write(ROOT/'artifacts/result-manifest.json',{'id':'M0316','origin_run_id':spec['run_id'],'variant_id':spec['variant_id'],'fidelity_class':'HYPOTHESIS','protocol_sha256':sha(ROOT/'specs/protocol.json'),'light_files':{str(f.relative_to(ROOT)):{'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(out.iterdir())},'private_full_outputs':{f.name:{'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(w.iterdir())},'projection':'25 monthend+initial points; risk computed over4386 native close NAV and731 daily returns first; not raw candles','raw_or_full_candles_included':False})
print('Light projection only; no new experiments')
