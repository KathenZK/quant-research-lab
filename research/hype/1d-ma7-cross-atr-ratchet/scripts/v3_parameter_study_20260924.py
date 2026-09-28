"""Frozen HYPE V3 parameter ablation; no data refresh and no winner selection."""
from pathlib import Path
from dataclasses import asdict, replace
import argparse
import importlib.util
import json
import sys
import time
import hashlib
import itertools
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[4]
BASE=Path(__file__).resolve().parents[1]
MARKET=ROOT/'research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts'
sys.path.insert(0,str(MARKET))
from common import sha,write_json
from v3_no_extra_warmup_20260913 import load_new,R as NATURAL,natural_ready
from run_market import save_result
from v3_opportunity_inputs_20260913 import table

R=BASE/'artifacts/v3_parameter_stability_20260924'
SPEC=BASE/'specs/v3-parameter-stability-registry-correction-20260924.md'
EP=ROOT/'research/_shared-kernels/ma7-cross-atr-ratchet/v8/engine.py'
PARENT=ROOT/'research/_shared-kernels/ma7-cross-atr-ratchet/v7/engine.py'
PARENT_SHA='9faaa9737ebf783079ec6d4981d7baa889cfbaad227daf9807979dfb83efb0bf'
GRID={
 'ma_period':('均线周期',[5,6,7,8,9]),
 'atr_period':('ATR周期',[10,12,14,16,18]),
 'rsi_period':('RSI周期',[4,5,6,7,8]),
 'slope':('顺向斜率门槛',[.025,.04,.05,.06,.075]),
 'initial_atr_mult':('初始ATR倍数',[1.1,1.3,1.5,1.7,1.9]),
 'progress_days':('未创新高低天数',[2,3,4,5,6]),
 'tighten_step':('每日收紧ATR倍数',[.1,.15,.2,.25,.3]),
 'atr_floor':('ATR倍数下限',[.3,.4,.5,.6,.7]),
 'rsi_threshold':('空单RSI止盈门槛',[20,25,30,35,40]),
 'accel_atr_mult':('单日跌幅/前日ATR门槛',[.6,.8,1.,1.2,1.4]),
 'accel_prev_mult':('跌幅/前日正跌幅门槛',[.75,.9,1.,1.1,1.25]),
}
ABLATIONS=[
 ('no_slope','移除全部斜率过滤',{'entry_mode':'no_slope'}),
 ('sign_only','移除斜率强度，仅保留顺向',{'slope':0.}),
 ('no_cross_event','移除穿越事件，只检查收盘所在侧',{'entry_trigger':'side'}),
 ('no_tightening','移除停滞收紧，固定1.5ATR',{'progress_days':0}),
 ('one_stagnant_day','仅1日不刷新就启动收紧',{'progress_days':1}),
 ('no_floor','移除0.5下限，允许收至MA',{'atr_floor':0.}),
 ('no_gradual','移除逐步收紧，触发即到0.5',{'tighten_step':1.}),
 ('no_short_tp','移除整个空单提前止盈',{'short_exit':'none'}),
 ('no_rsi_gate','移除空单RSI条件',{'require_rsi':False}),
 ('no_accel_gate','移除全部加速条件',{'short_exit':'rsi30'}),
 ('no_accel_size','移除跌幅达到1ATR条件',{'require_accel_size':False}),
 ('no_accel_increase','移除跌幅大于前日条件',{'require_accel_increase':False}),
 ('no_profit_gate','移除提前止盈须有净浮盈条件',{'require_tp_profit':False}),
 ('freeze_ma_anchor','止损均线锚冻结在入场信号日',{'trail_ma':False}),
 ('freeze_atr_anchor','持仓止损ATR冻结在入场信号日',{'trail_atr':False}),
 ('close_progress','高低价停滞替换为收盘价停滞',{'progress_source':'close'}),
 ('reset_arming','刷新极值后暂停收紧并重新计时',{'progress_policy':'reset_on_new_extreme'}),
 ('enable_reverse','恢复止损前5日反向穿越反手',{'reverse':True}),
 ('long_only','移除空单，只保留多单',{'direction_mode':'long'}),
 ('short_only','移除多单，只保留空单',{'direction_mode':'short'}),
]
PAIRS=[('ma_period','slope'),('initial_atr_mult','atr_floor'),
       ('progress_days','tighten_step'),('rsi_period','rsi_threshold'),
       ('rsi_threshold','accel_atr_mult'),('atr_period','initial_atr_mult')]

def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def engine():
 pin=json.loads((R/'started.json').read_text())
 assert sha(EP)==pin['engine_sha256'] and sha(PARENT)==PARENT_SHA
 return module('v3_parameters_v8',EP)

def base_config(e):return e.Config(reverse=False,progress_days=4,fee=.001,slip=.0004)

def registry(e):
 b=base_config(e);cases={};members=[];lookup={}
 def add(id,label,group,changes,**tags):
  cfg=replace(b,**changes);key=cfg
  if key not in lookup:lookup[key]=id;cases[id]={'case_id':id,'label':label,'config':asdict(cfg),'changes':changes}
  members.append({'case_id':lookup[key],'group':group,'label':label,**tags})
  return lookup[key]
 add('B','当前V3','baseline',{})
 for k,label,changes in ABLATIONS:add('A_'+k,label,'ablation',changes)
 for key,(label,values) in GRID.items():
  for value in values:add('N_'+key+'_'+str(value).replace('.','p'),f'{label}={value}','neighbor',{key:value},parameter=key,value=value)
 for x,y in PAIRS:
  for vx,vy in itertools.product(GRID[x][1][1:4],GRID[y][1][1:4]):
   add(f'J_{x}_{vx}_{y}_{vy}',f'{x}={vx}; {y}={vy}','pair',{x:vx,y:vy},pair=x+'__'+y,x=vx,y=vy)
 # Walsh sign columns: 32 runs, each parameter 16 low/16 high, every pair balanced.
 for row in range(32):
  changes={k:values[1 if (row & col).bit_count()%2==0 else 3] for col,(k,(_,values)) in zip([1,2,3,4,5,6,7,8,9,10,16],GRID.items())}
  add(f'M_{row:02d}',f'11参数同时扰动 {row+1:02d}','joint',changes)
 return list(cases.values()),members

def prepare():
 assert not R.exists(),'Never overwrite completed evidence'
 assert sha(PARENT)==PARENT_SHA
 e=module('v3_parameters_v8_prepare',EP);cases,members=registry(e)
 R.mkdir(parents=True)
 write_json(R/'started.json',{'created_before_results_utc':str(pd.Timestamp.now(tz='UTC')),
  'scope':['HYPE/USDT:USDT'],'engine_sha256':sha(EP),'parent_sha256':PARENT_SHA,
  'spec_sha256':sha(SPEC),'original_spec_sha256':sha(BASE/'specs/v3-parameter-stability-20260924.md'),'registry_correction':True,'runner_sha256':sha(Path(__file__)),
  'no_new_market_data':True,'no_selection_or_promotion':True,
  'grid':GRID,'pairs':PAIRS,'cases':cases,'memberships':members,
  'local_label_rule':'all four off-center neighbors ending wealth >=75% baseline AND MDD <=baseline+5pp; descriptive only',
  'common_start_rule':'latest natural indicator readiness over declared cases; all accounts start flat on that day',
  'reference_replay':'original V3 natural start separately; not mixed with common-start rankings'})
 print('Frozen',len(cases),'unique configurations;',len(members),'group memberships',flush=True)

def feature_frame(e,raw,cfg):
 d=e.features(raw,cfg)
 return natural_ready(d)

def trade_metrics(tr):
 r=tr.return_on_entry_equity if len(tr) else pd.Series(dtype=float)
 wins=r[r>0];losses=r[r<0]
 closed=tr[tr.exit_reason.ne('sample_end')] if len(tr) else tr
 return {'unit_payoff':float(wins.mean()/-losses.mean()) if len(wins) and len(losses) else None,
   'mean_win_pct':float(wins.mean()*100) if len(wins) else None,
   'mean_loss_pct':float(losses.mean()*100) if len(losses) else None,
   'median_trade_pct':float(r.median()*100) if len(r) else None,
   'worst_trade_pct':float(r.min()*100) if len(r) else None,
   'terminal_trades':int(tr.exit_reason.eq('sample_end').sum()) if len(tr) else 0,
   'closed_only_compounded_pct':float(((1+closed.return_on_entry_equity).prod()-1)*100) if len(closed) else 0.}

def matched_metrics(base,tr):
 old={(str(t.entry_time),int(t.side)):t for t in base.itertuples()}
 new={(str(t.entry_time),int(t.side)):t for t in tr.itertuples()}
 matched=old.keys()&new.keys();wins=[k for k in old if old[k].return_on_entry_equity>0]
 denom=sum(old[k].return_on_entry_equity for k in wins)
 top=sorted(wins,key=lambda k:old[k].return_on_entry_equity,reverse=True)[:5]
 return {'same_entries':len(matched),'missed_baseline_entries':len(old.keys()-new.keys()),
  'new_entries':len(new.keys()-old.keys()),
  'winners_to_loss':sum(old[k].return_on_entry_equity>0 and new[k].return_on_entry_equity<0 for k in matched),
  'losses_improved':sum(old[k].return_on_entry_equity<0 and new[k].return_on_entry_equity>old[k].return_on_entry_equity for k in matched),
  'all_baseline_winner_retention_pct':100*sum(new[k].return_on_entry_equity if k in new else 0 for k in wins)/denom if denom else None,
  'top5_retention_pct':100*sum(new[k].return_on_entry_equity if k in new else 0 for k in top)/sum(old[k].return_on_entry_equity for k in top) if top else None}

def run():
 frozen=json.loads((R/'started.json').read_text());assert sha(SPEC)==frozen['spec_sha256']
 assert sha(Path(__file__))==frozen['runner_sha256']
 e=engine();raw,h,meta=load_new('HYPE__seg001')
 # Persist the verified frozen source frames, avoiding later dependence on changing features.
 raw.to_parquet(R/'input_daily.parquet',index=False);h.to_parquet(R/'input_hourly.parquet',index=False)
 write_json(R/'input.json',meta)
 cases=frozen['cases'];frames={}
 starts=[]
 for c in cases:
  cfg=e.Config(**c['config']);d=feature_frame(e,raw,cfg);frames[c['case_id']]=d
  starts.append(d.loc[d.ready,'timestamp'].iloc[0]+pd.Timedelta(days=1))
 common=max(starts);end=pd.Timestamp(meta['end']);write_json(R/'window.json',{'common_start':str(common),'end':str(end),'original_start':meta['new_start'],'case_natural_starts':dict(zip([c['case_id'] for c in cases],map(str,starts)))})
 cfg=base_config(e);ref=e.simulate(h,frames['B'],cfg,pd.Timestamp(meta['new_start']),end)
 old_dir=NATURAL/'accounts/HYPE__seg001/V3';manifest=json.loads((NATURAL/'delivery/artifact_checksums.json').read_text())
 for file in ['summary.json','trades.csv','stops.csv','equity.parquet']:assert sha(old_dir/file)==manifest[str((old_dir/file).relative_to(NATURAL))]
 old=json.loads((old_dir/'summary.json').read_text());assert ref[0]['return_pct']==old['return_pct'] and ref[0]['max_drawdown_pct']==old['max_drawdown_pct']
 oldtr=table(old_dir/'trades.csv')
 for col in ['entry_time','exit_time','side','entry_price','exit_price','net_pnl','return_on_entry_equity']:
  pd.testing.assert_series_equal(ref[1][col],oldtr[col],check_dtype=False,check_names=False,rtol=1e-12,atol=1e-10)
 save_result(R/'reference_original_start',ref)
 rows=[];baseline=None;t0=time.monotonic()
 for i,c in enumerate(cases):
  events=[];cfg=e.Config(**c['config']);result=e.simulate(h,frames[c['case_id']],cfg,common,end,entry_events=events)
  result[0].update(trade_metrics(result[1]));p=R/'accounts'/c['case_id'];save_result(p,result)
  pd.DataFrame(events).reindex(columns=list(dict.fromkeys(e.ENTRY_EVENT_COLUMNS+e.CANDIDATE_EVENT_COLUMNS))).to_csv(p/'entry_events.csv',index=False)
  if c['case_id']=='B':baseline=result[1]
  rows.append({'case_id':c['case_id'],'label':c['label'],**result[0],**matched_metrics(baseline,result[1])})
  if i%10==0 or i==len(cases)-1:print(f'{i+1}/{len(cases)} complete; {time.monotonic()-t0:.1f}s',flush=True)
 pd.DataFrame(rows).to_csv(R/'comparison.csv',index=False)
 pd.DataFrame(frozen['memberships']).to_csv(R/'memberships.csv',index=False)
 write_json(R/'replay_complete.json',{'complete':True,'accounts':len(cases),'baseline_exact':True,'common_start':str(common),'end':str(end),'funding_verified':False,'no_other_coins':True})

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run']);args=parser.parse_args()
 prepare() if args.action=='prepare' else run()
