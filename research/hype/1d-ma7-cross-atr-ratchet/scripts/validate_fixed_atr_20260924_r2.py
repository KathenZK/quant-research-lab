"""Validate a single V3 exit-scale change on frozen HYPE and non-HYPE inputs."""
from pathlib import Path
from dataclasses import asdict,replace
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse,sys,json,time,math
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[4]
BASE=Path(__file__).resolve().parents[1]
MARKET=ROOT/'research/asset-portfolios/1d-ma7-cross-atr-generalization'
sys.path.insert(0,str(MARKET/'scripts'))
from common import sha,write_json
from v3_no_extra_warmup_20260913 import load_new,R as NATURAL
from v3_opportunity_inputs_20260913 import table,checked
from run_market import save_result
from run_exit_state_history_20260910 import time_blocks
import v3_parameter_study_20260924 as prior
import audit_fixed_atr_validation_20260924 as auditor

R=BASE/'artifacts/v3_fixed_atr_validation_20260924'
X=MARKET/'artifacts/v3_fixed_atr_validation_20260924'
P=BASE/'artifacts/v3_parameter_stability_20260924'
SPEC=BASE/'specs/v3-fixed-entry-atr-validation-20260924.md'
E=ROOT/'research/_shared-kernels/ma7-cross-atr-ratchet/v8/engine.py'
ESHA='6b153c4e8362252813083645695360643383ef1918ecae083bb90e4a9b917ff0'

def engine():
 checked(E,ESHA)
 return prior.module('fixed_atr_validation_engine',E)

@lru_cache(maxsize=2)
def manifest(base):
 base=Path(base)
 return json.loads((base/('delivery/artifact_checksums.json' if base==NATURAL else 'artifact_checksums.json')).read_text())

def verified_account(base,directory):
 base,directory=Path(base),Path(directory);m=manifest(str(base))
 for name in ['summary.json','trades.csv','stops.csv','equity.parquet']:
  checked(directory/name,m[str((directory/name).relative_to(base))])
 return (json.loads((directory/'summary.json').read_text()),table(directory/'trades.csv'),pd.read_parquet(directory/'equity.parquet'),table(directory/'stops.csv'),pd.DataFrame())

def read_result(directory):
 return (json.loads((directory/'summary.json').read_text()),table(directory/'trades.csv'),pd.read_parquet(directory/'equity.parquet'),table(directory/'stops.csv'),pd.DataFrame())

def execute(e,h,d,cfg,start,end,directory,fixed=None):
 if directory.exists():return read_result(directory)
 events=[];z=e.simulate(h,d,cfg,start,end,entry_events=events,fixed_episode=fixed)
 z[0].update(prior.trade_metrics(z[1]));save_result(directory,z)
 pd.DataFrame(events).reindex(columns=list(dict.fromkeys(e.ENTRY_EVENT_COLUMNS+e.CANDIDATE_EVENT_COLUMNS))).to_csv(directory/'entry_events.csv',index=False)
 return z

def pair_rows(d,f,ident):
 old={(str(t.entry_time),int(t.side)):t for t in d.itertuples()};new={(str(t.entry_time),int(t.side)):t for t in f.itertuples()};rows=[]
 for k in sorted(old.keys()|new.keys()):
  a,b=old.get(k),new.get(k)
  rows.append({**ident,'entry_time':k[0],'side':k[1],'relationship':'same' if a and b else 'missed' if a else 'new',
   'D_return_pct':a.return_on_entry_equity*100 if a else None,'F_return_pct':b.return_on_entry_equity*100 if b else None,
   'D_exit':str(a.exit_time) if a else None,'F_exit':str(b.exit_time) if b else None,
   'D_terminal':bool(a and a.exit_reason=='sample_end'),'F_terminal':bool(b and b.exit_reason=='sample_end'),
   'delta_pp':(b.return_on_entry_equity-a.return_on_entry_equity)*100 if a and b else None})
 return rows

def comparison(d,f,ident):
 ds,fs=d[0],f[0];out={**ident}
 for arm,z in [('D',d),('F',f)]:
  metrics={**z[0],**prior.trade_metrics(z[1])}
  for k in ['start','end_exclusive','return_pct','max_drawdown_pct','trades','win_rate_pct','unit_payoff','closed_only_compounded_pct','terminal_trades','long_pnl','short_pnl','bankrupt']:
   out[arm+'_'+k]=metrics.get(k)
 out.update(delta_return_pp=fs['return_pct']-ds['return_pct'],delta_drawdown_pp=abs(fs['max_drawdown_pct'])-abs(ds['max_drawdown_pct']),**prior.matched_metrics(d[1],f[1]))
 both=pair_rows(d[1],f[1],{})
 out['same_improved']=sum(x['relationship']=='same' and x['delta_pp']>1e-8 for x in both)
 out['same_worsened']=sum(x['relationship']=='same' and x['delta_pp']< -1e-8 for x in both)
 out['same_unchanged']=sum(x['relationship']=='same' and abs(x['delta_pp'])<=1e-8 for x in both)
 return out

def prepare():
 assert not R.exists() and not X.exists(),'Never overwrite a validation batch'
 checked(E,ESHA);f=json.loads((P/'started.json').read_text())
 scope_path=NATURAL/'inputs/scope.csv';catalog_path=NATURAL/'inputs/catalog.json';m=manifest(str(NATURAL))
 for p in [scope_path,catalog_path]:checked(p,m[str(p.relative_to(NATURAL))])
 scope=pd.read_csv(scope_path);catalog=json.loads(catalog_path.read_text());classes=dict(zip(scope.slug,scope.observed_class))
 universe=[];excluded=[]
 for key,s in sorted(catalog.items()):
  reason='HYPE_discovery_sample' if s['slug']=='HYPE' else 'not_CO IN'.replace(' ','') if classes[s['slug']]!='COIN' else 'no_natural_ready_execution_day' if pd.Timestamp(s['input_start'])+pd.Timedelta(days=15)>=pd.Timestamp(s['end']) else None
  rec={**s,'observed_class':classes[s['slug']]}
  (excluded if reason else universe).append({**rec,'exclusion':reason} if reason else rec)
 assert len(universe)==947 and len({s['slug'] for s in universe})==649
 ids=list(dict.fromkeys(['B']+[x['case_id'] for x in f['memberships'] if x['group']=='neighbor']))
 hyp=[x for x in f['cases'] if x['case_id'] in ids];assert len(hyp)==45
 pins={str(p.relative_to(ROOT)):sha(p) for p in [SPEC,Path(__file__),Path(prior.__file__),Path(auditor.__file__),E,scope_path,catalog_path,P/'artifact_checksums.json',NATURAL/'delivery/artifact_checksums.json',MARKET/'scripts/v3_no_extra_warmup_20260913.py',MARKET/'scripts/v3_opportunity_inputs_20260913.py',MARKET/'scripts/run_exit_state_history_20260910.py']}
 R.mkdir(parents=True);X.mkdir(parents=True)
 start={'created_before_results_utc':str(pd.Timestamp.now(tz='UTC')),'pins':pins,'HYPE_cases':hyp,'HYPE_neighbor_memberships':[x for x in f['memberships'] if x['group']=='neighbor'],
  'default_config':asdict(prior.base_config(engine())),'only_switch':'trail_atr','cross_coins':649,'cross_segments':947,
  'cross_rule':'observed COIN except HYPE; all natural-ready retained segments','source_refresh':False,'fees_per_side':.001,'slippage_per_side':.0004}
 write_json(R/'started.json',start);write_json(X/'started.json',start);write_json(X/'universe.json',universe);pd.DataFrame(excluded).to_csv(X/'excluded.csv',index=False)
 print('Frozen HYPE45 pairs + original start +18 fixed-entry pairs; cross649 coins/947 segments',flush=True)

def verify_started():
 f=json.loads((R/'started.json').read_text())
 revision=json.loads((R/'validation_revision.json').read_text())
 for rel,digest in revision['pins'].items():checked(ROOT/rel,digest)
 for rel,digest in f['pins'].items():checked(ROOT/rel,digest)
 return f

def audit_episode(z,original,daily,hourly,cfg):
 assert len(z[1])==1;t=z[1].iloc[0];s=z[0];daily=daily.set_index('timestamp',drop=False);h=hourly.set_index('timestamp',drop=False)
 for key in ['entry_time','side','qty','entry_equity','entry_price']:auditor.equal(t[key],original[key],'fixed-entry '+key)
 auditor.audit_stop_path(t,z[3],daily,s)
 net=int(t.side)*t.qty*(t.exit_price-t.entry_price)-t.entry_fee-t.exit_fee
 auditor.equal(net,t.net_pnl,'episode net');auditor.equal((t.end_equity/t.entry_equity-1)*100,t.return_on_entry_equity*100,'episode return')
 st=z[3];before=h[(h.index>=t.entry_time)&(h.index<t.exit_time)]
 eff=st.new_stop.to_numpy()[np.searchsorted(st.timestamp.astype('int64'),before.index.asi8,side='right')-1]
 prices=before.low if t.side==1 else before.high
 assert (t.side*(prices.to_numpy()-eff)>0).all(),'earlier episode stop ignored'
 for row in st.iloc[1:].itertuples():
  if auditor.tp_eligible(t,daily.loc[row.signal_day],s):assert t.exit_time==row.timestamp and t.exit_reason in ['stop_gap',s['short_exit']]
 if t.exit_reason=='stop_gap':assert t.side*(h.loc[t.exit_time,'open']-t.stop)<=0
 elif t.exit_reason=='stop_intrahour':
  bar=h.loc[t.exit_time];assert t.side*(bar.open-t.stop)>0 and (bar.low<=t.stop if t.side==1 else bar.high>=t.stop)
 elif t.exit_reason=='sample_end':assert t.exit_time==hourly.timestamp.iloc[-1]+pd.Timedelta(hours=1)
 else:assert auditor.tp_eligible(t,daily.loc[t.tp_signal_day],s)
 return {'trade_id':int(original.trade_id),'arm':'D' if cfg.trail_atr else 'F','status':'PASS','stop_records':len(st)}

def hype():
 frozen=verify_started();e=engine();raw,h,meta=load_new('HYPE__seg001');b=prior.base_config(e);end=pd.Timestamp(meta['end']);common=pd.Timestamp('2025-06-19',tz='UTC')
 write_json(R/'input.json',meta);raw.to_parquet(R/'input_daily.parquet',index=False);h.to_parquet(R/'input_hourly.parquet',index=False)
 result_rows=[];tr_pairs=[];audits=[]
 for i,c in enumerate(frozen['HYPE_cases']):
  cfg=e.Config(**c['config']);d=prior.feature_frame(e,raw,cfg);D=verified_account(P,P/'accounts'/c['case_id']);F=execute(e,h,d,replace(cfg,trail_atr=False),common,end,R/'accounts'/c['case_id']/'F')
  assert D[0]['start']==F[0]['start'] and D[0]['end_exclusive']==F[0]['end_exclusive']
  a=auditor.audit_run(R/'accounts'/c['case_id']/'F',auditor.indicators(raw,asdict(cfg)),h.set_index('timestamp',drop=False));audits.append({'case_id':c['case_id'],**a})
  result_rows.append(comparison(D,F,{'case_id':c['case_id'],'label':c['label'],'window':'common','D_path':str((P/'accounts'/c['case_id']).relative_to(ROOT)),'F_path':str((R/'accounts'/c['case_id']/'F').relative_to(ROOT))}))
  tr_pairs+=pair_rows(D[1],F[1],{'case_id':c['case_id'],'window':'common'})
  if c['case_id']=='B':
   old=verified_account(P,P/'accounts/A_freeze_atr_anchor');assert F[0]['return_pct']==old[0]['return_pct'];pd.testing.assert_frame_equal(read_result(R/'accounts'/c['case_id']/'F')[1][old[1].columns],old[1],check_dtype=False,rtol=1e-12,atol=1e-10)
  if i%10==0:print('HYPE pairs',i+1,'/45',flush=True)
 d=prior.feature_frame(e,raw,b);D=verified_account(P,P/'reference_original_start');F=execute(e,h,d,replace(b,trail_atr=False),pd.Timestamp(meta['new_start']),end,R/'accounts/original/F')
 audits.append({'case_id':'original',**auditor.audit_run(R/'accounts/original/F',auditor.indicators(raw,asdict(b)),h.set_index('timestamp',drop=False))})
 result_rows.append(comparison(D,F,{'case_id':'original','label':'原自然就绪起点','window':'original','D_path':str((P/'reference_original_start').relative_to(ROOT)),'F_path':str((R/'accounts/original/F').relative_to(ROOT))}))
 tr_pairs+=pair_rows(D[1],F[1],{'case_id':'original','window':'original'})
 episode_rows=[];episode_audits=[]
 for t in D[1].itertuples(index=False):
  original=pd.Series(t._asdict());fixed={k:original[k] for k in ['entry_time','side','qty','entry_equity']};out={}
  for arm,cfg in [('D',b),('F',replace(b,trail_atr=False))]:
   z=execute(e,h,d,cfg,t.entry_time,end,R/'episodes'/f'{t.trade_id:03d}'/arm,fixed)
   episode_audits.append(audit_episode(z,original,d,h,cfg));out[arm]=z
   if arm=='D':
    for k in ['exit_time','exit_price','net_pnl','return_on_entry_equity']:auditor.equal(z[1].iloc[0][k],original[k],'original episode reproduction '+k)
  episode_rows.append({'original_trade_id':t.trade_id,'entry_time':str(t.entry_time),'side':t.side,'D_return_pct':out['D'][1].iloc[0].return_on_entry_equity*100,'F_return_pct':out['F'][1].iloc[0].return_on_entry_equity*100,'D_exit':str(out['D'][1].iloc[0].exit_time),'F_exit':str(out['F'][1].iloc[0].exit_time),'D_terminal':out['D'][1].iloc[0].exit_reason=='sample_end','F_terminal':out['F'][1].iloc[0].exit_reason=='sample_end'})
 pd.DataFrame(result_rows).to_csv(R/'comparison.csv',index=False);pd.DataFrame(tr_pairs).to_csv(R/'trade_pairs.csv',index=False);pd.DataFrame(episode_rows).to_csv(R/'fixed_entry_pairs.csv',index=False)
 write_json(R/'audit_r2.json',{'complete':True,'accounts':audits,'episodes':episode_audits});write_json(R/'hype_complete.json',{'complete':True,'account_pairs':46,'new_full_accounts':46,'fixed_entry_pairs':18,'reused_original_D':True,'old_common_F_reproduced':True})
 print('HYPE complete',flush=True)

def cross_coin(item):
 slug,segments=item;e=engine();cfg=replace(prior.base_config(e),trail_atr=False);rows=[];blocks=[];pairs=[];audits=[];metas=[]
 for s in segments:
  key=s['run_key'];raw,h,meta=load_new(key);start=pd.Timestamp(meta['new_start']);end=pd.Timestamp(meta['end']);assert meta['tradable']
  D=verified_account(NATURAL,NATURAL/'accounts'/key/'V3')
  for field in ['fee','slip','slope','progress_days','progress_source','reverse','short_exit']:assert D[0][field]==getattr(cfg,field)
  out=X/'accounts'/key/'F';F=execute(e,h,raw,cfg,start,end,out)
  assert D[0]['start']==F[0]['start'] and D[0]['end_exclusive']==F[0]['end_exclusive']
  a=auditor.audit_run(out,auditor.indicators(raw,asdict(cfg)),h.set_index('timestamp',drop=False));audits.append({'run_key':key,**a})
  ident={'run_key':key,'slug':slug,'symbol':s['symbol']};rows.append(comparison(D,F,{**ident,'D_path':str((NATURAL/'accounts'/key/'V3').relative_to(ROOT)),'F_path':str(out.relative_to(ROOT)),'days':(end-start).days}))
  pairs+=pair_rows(D[1],F[1],ident)
  for arm,z in [('D',D),('F',F)]:
   for block in time_blocks(z[2],start,end):
    if block['status']!='NO_OVERLAP':blocks.append({**ident,'arm':arm,**block})
  metas.append(meta)
 out=X/'coins'/slug;out.mkdir(parents=True,exist_ok=True)
 pd.DataFrame(rows).to_csv(out/'comparison.csv',index=False);pd.DataFrame(blocks).to_csv(out/'periods.csv',index=False);pd.DataFrame(pairs).to_csv(out/'trade_pairs.csv',index=False)
 write_json(out/'audit_r2.json',{'complete':True,'accounts':audits});write_json(out/'inputs.json',metas);write_json(out/'completion_r2.json',{'complete':True,'slug':slug,'segments':len(segments)})
 return slug,len(segments),sum(a['trades'] for a in audits)

def cross(workers):
 verify_started();universe=json.loads((X/'universe.json').read_text());groups={}
 for s in universe:groups.setdefault(s['slug'],[]).append(s)
 todo=[]
 for slug,segs in groups.items():
  if not (X/'coins'/slug/'completion_r2.json').exists():todo.append((slug,sorted(segs,key=lambda s:s['input_start'])))
 failures=[];t0=time.monotonic();done=len(groups)-len(todo)
 with ProcessPoolExecutor(max_workers=workers) as pool:
  jobs={pool.submit(cross_coin,item):item[0] for item in todo}
  for future in as_completed(jobs):
   slug=jobs[future]
   try:future.result();done+=1
   except Exception as ex:
    import traceback
    failures.append({'slug':slug,'error':repr(ex),'traceback':traceback.format_exc()});print('FAILED',slug,repr(ex),flush=True)
   if done%25==0 or done==len(groups):print('cross',done,'/',len(groups),f'{time.monotonic()-t0:.0f}s',flush=True)
 write_json(X/'failures_r2.json',failures)
 if failures:raise RuntimeError(f'{len(failures)} coins failed; saved accounts retained for audit/resume')
 for name in ['comparison','periods','trade_pairs']:
  frames=[pd.read_csv(X/'coins'/slug/(name+'.csv')) for slug in sorted(groups)]
  pd.concat(frames,ignore_index=True).to_csv(X/(name+'.csv'),index=False)
 audits=[a for slug in groups for a in json.loads((X/'coins'/slug/'audit_r2.json').read_text())['accounts']]
 write_json(X/'audit_r2.json',{'complete':True,'accounts':audits,'new_F_accounts':len(audits),'trades':sum(a['trades'] for a in audits),'stops':sum(a['stop_records'] for a in audits),'equity_marks':sum(a['equity_marks_independently_rebuilt'] for a in audits)})
 write_json(X/'cross_complete.json',{'complete':True,'coins':len(groups),'segments':len(universe),'original_D_reused':len(universe),'new_F_accounts':len(universe),'full_market_parameter_search':False})
 print('Cross complete',flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','hype','cross']);p.add_argument('--workers',type=int,default=4);args=p.parse_args()
 if args.action=='prepare':prepare()
 elif args.action=='hype':hype()
 else:cross(args.workers)
