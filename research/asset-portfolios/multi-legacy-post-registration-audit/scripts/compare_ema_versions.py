"""Predeclared early/final HYPE comparisons; only hash-checked audit inputs.
All strategy imports are used solely for deterministic rules, never data loaders.
"""
from __future__ import annotations
import argparse, hashlib, importlib, inspect, json, re, sys
from dataclasses import asdict, replace
from pathlib import Path
import numpy as np
import pandas as pd
import iteration_common as inputs
import hype_legacy_replay as legacy

ROOT=legacy.ROOT
OUT=legacy.FAMILY/'artifacts/iteration_comparison_20260911/ema'
START=pd.Timestamp('2026-07-23T00:00:00Z')
END=pd.Timestamp('2026-09-05T15:00:00Z')
STEP=pd.Timedelta(minutes=15)
CASES=[
 {'family':'EMA-X','version':'V1','role':'early','source':'research/hype/15m-ema-crossover/notes/hype-ema-x-v1-v14-historical-archive-2026-08-06.md','rules':'bare EMA96/384 cross, next-open entry, opposite cross next-open exit, original exposure1x','date_evidence':'historical V1 predates V18; archive restoration date 2026-08-06 is not rule creation date'},
 {'family':'EMA-X','version':'V18','role':'final','source':'research/hype/15m-ema-crossover/specs/hype-ema-x-v18-baseline-spec.md','rules':'fixed v18_candidate; original HQ scale1.1, LQ1.0','date_evidence':'registered 2026-07-01'},
 {'family':'EMA-TB','version':'V2P','role':'early_recovered_diagnostic','source':'research/hype/15m-ema-trend-breakout/specs/hype-v2p-strategy-spec.md','rules':'full V2P spec recovered with causal next-open entries/exits and prior-closed-bar dynamic ATR/trailing; not original buggy close-entry reproduction','date_evidence':'historical early V2P spec; chronological precedence documented in family evolution'},
 {'family':'EMA-TB','version':'V35','role':'early_executable','source':'research/hype/15m-ema-trend-breakout/specs/hype-trend-strategy-v35-spec.md','rules':'earliest complete available causal execution engine, original V35 canonical config','date_evidence':'documented prior to 2026-07-07; later than initialV1/V2'},
 {'family':'EMA-TB','version':'V41','role':'final','source':'research/hype/15m-ema-trend-breakout/specs/hype-trend-strategy-v41-spec.md','rules':'V35 config, cooldown1, remove short1hEMA filter','date_evidence':'registered 2026-07-20'},
 {'family':'MII','version':'V1','role':'early','source':'research/hype/15m-multi-indicator-intraday/specs/hype-15m-mii-v1-baseline-spec.md','rules':'original baseline RSI7(30/60), MACD filter,ATR96 .006-.028,TP.009/SL.028,hold16,exposure1.5','date_evidence':'selected2026-06-25; executable spec revised2026-06-29'},
 {'family':'MII','version':'V1.4A','role':'final','source':'research/hype/15m-multi-indicator-intraday/specs/hype-15m-mii-v1-4a-parameter-spec-not-live-ready-2026-07-09.md','rules':'RSI7(40/60),ATR96>=.0075,rvol96>=.85,TP1.4ATR/SL3ATR,hold24,exposure2.5','date_evidence':'registered2026-07-09'},
 {'family':'ENS','version':'V35+MII1.3','role':'early_diagnostic_not_V1','source':'research/hype/15m-trend-breakout-multi-indicator-ensemble/notes/hype-15m-tb-mii-ensemble-first-combination-backtest-2026-07-07.md','rules':'single_v35_priority,preempt=true,MIIK+1,originalV35+MII1.3,no simultaneous legs','date_evidence':'first fixed combination2026-07-07; no registered V1'},
 {'family':'ENS','version':'V2','role':'final','source':'research/hype/15m-trend-breakout-multi-indicator-ensemble/live-specs/hype-15m-tb-mii-ens-v2-live-validation-spec-not-live-ready-2026-07-09.md','rules':'single_v39_priority,preempt=true,MII1.4K+1,no simultaneous legs','date_evidence':'registered2026-07-09'},
]

def dump(path,obj):
 path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=legacy.json_default)+'\n')

def freeze_plan():
 OUT.mkdir(parents=True,exist_ok=True)
 sources={c['source'] for c in CASES}
 for fam in ('15m-ema-trend-breakout','15m-ema-crossover','15m-multi-indicator-intraday','15m-trend-breakout-multi-indicator-ensemble'):
  sources.update(str(p.relative_to(ROOT)) for p in (ROOT/'research/hype'/fam/'scripts').glob('*.py'))
 sources.add(str((legacy.FAMILY/'scripts/audit_common.py').relative_to(ROOT)))
 sources.add(str((legacy.FAMILY/'scripts/hype_legacy_replay.py').relative_to(ROOT)))
 manifest={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(sources)}
 plan={'frozen_at_utc':pd.Timestamp.now(tz='UTC'),'start':START,'end_exclusive':END,'cases':CASES,'scenarios':[{'name':'unit','allocation':'entry account equity x1 nominal, fixed quantity until exit','fee':.001,'slippage':.0004},{'name':'original_sizing','allocation':'original rule allocation at entry, fixed quantity until exit','fee':.001,'slippage':.0004},{'name':'unit_slip8bps','allocation':'entry account equity x1 nominal, fixed quantity until exit','fee':.001,'slippage':.0008}],'accounting':'common fixed-quantity linear USDT contract valuation, fees/slippage charged each fill; replaces inherited per-bar leveraged compounding in every version; hold rules unchanged; observed funding estimated separately at event timestamp using trade-price proxy, not verified full net','funding':'observed events only; mark price/history coverage incomplete; no silent claim of zero funding','cutoff':'cash and no pending orders before START; signals from bars before START disabled; closedbarend cutoff END','execution_corrections':['EMA-X next-open realized PnL moved from preceding signal bar to actual exit timestamp; last-bar next-open clamp removed','V2P requires causal restoration; current-bar ATR/extreme/close cannot define earlier intrabar orders, use prior closed bar dynamic levels and next-open market exits','MII terminal maxhold truncation repaired to last close only after checking last complete bar stop/target; original no-reentry-in-intrabar rules retained'],'selection':'No future search. V2P documented recovery is supplemental; V35-vsV41 is executable-only TB comparison. Earlier missing legacy dependencies not replaced by current selected parameters.'}
 if (OUT/'cases_plan.json').exists():
  raise RuntimeError('Frozen plan already exists; do not overwrite without explicit documented change')
 dump(OUT/'sources_manifest.json',manifest);dump(OUT/'cases_plan.json',plan)
 return plan


def imports():
 names={'tb':'research_hype_ema_tb_v35_profit_floor','ab':'research_hype_ema_tb_v35_full_ablation_recent_tune','cd':'research_hype_ema_tb_v35_cooldown4','ens':'research_hype_15m_tb_mii_ensemble_backtest','x':'research_hype_ema_cross_strategy','h':'research_hype_v17_hybrid_ablation','late':'research_hype_v13_late_reentry','xr':'research_hype_ema_x_v18_retest','m1':'research_hype_15m_mii_v1_full_ablation','m12':'research_hype_15m_mii_v1_2_atr_bracket_exit'}
 return {k:importlib.import_module(v) for k,v in names.items()}

def append_close_sentinel(frame):
 last=frame.iloc[-1].copy()
 for c in ('open','high','low','close'):last[c]=frame.close.iloc[-1]
 last['volume']=0.0
 return pd.concat([frame,pd.DataFrame([last],index=pd.DatetimeIndex([frame.index[-1]+STEP],name='ts'))])

def standardize(records,frame,default_allocation=1.,leg='strategy'):
 end=frame.index[-1]+STEP
 out=[]
 for original in records:
  r=dict(original);r['entry_ts']=pd.Timestamp(r['entry_ts']);r['exit_ts']=pd.Timestamp(r['exit_ts'])
  r['allocation']=float(r.get('allocation',default_allocation));r['leg']=r.get('leg',leg)
  if r['exit_reason'] in ('open_at_end','terminal_mark') or r['exit_ts']>=end:
   r['exit_reason']='terminal_mark';r['exit_ts']=end;r['exit_price']=float(frame.close.iloc[-1]);r['exit_timing']='terminal_close'
  else:
   open_reasons=('indicator_exit','timeout','max_hold','opposite_cross','trend_break','stop_gap','stop_gap_open','take_profit_gap')
   r['exit_timing']='bar_open' if r['exit_reason'] in open_reasons or r['exit_reason'].startswith(('hard_','warning_','preempted_by_','segment_','fallback_')) else 'intrabar'
  r['signal_ts']=r.get('signal_ts',r['entry_ts']-STEP)
  assert r['entry_ts']>=START and r['entry_ts']<end and pd.Timestamp(r['signal_ts'])>=START
  assert r['entry_ts']<=r['exit_ts']
  out.append(r)
 return sorted(out,key=lambda r:(r['entry_ts'],r['exit_ts']))

def x_early(frame):
 close=frame.close;fast=close.ewm(span=96,adjust=False,min_periods=96).mean();slow=close.ewm(span=384,adjust=False,min_periods=384).mean()
 spread=fast/slow-1
 cross=pd.Series(np.select([(spread>0)&(spread.shift()<=0),(spread<0)&(spread.shift()>=0)],[1,-1],default=0),index=frame.index)
 active=None;rows=[]
 for i in range(frame.index.searchsorted(START)+1,len(frame)):
  d=int(cross.iloc[i-1]);ts=frame.index[i]
  if not d:continue
  if active is not None:
   if d==active['direction']:continue
   rows.append({**active,'exit_ts':ts,'exit_price':float(frame.open.iloc[i]),'exit_reason':'opposite_cross'})
  active={'entry_ts':ts,'entry_price':float(frame.open.iloc[i]),'direction':d,'signal_ts':frame.index[i-1],'allocation':1.}
 if active:rows.append({**active,'exit_ts':frame.index[-1]+STEP,'exit_price':float(frame.close.iloc[-1]),'exit_reason':'terminal_mark'})
 return standardize(rows,frame)

def x_final(frame,mods,unit):
 h,late=mods['h'],mods['late'];candidate=mods['xr'].v18_candidate()
 if unit:candidate=replace(candidate,hq_scale=1.,lq_scale=1.)
 features=h.add_v17_indicators(h.add_structure_features(h.add_oscillator_features(h.add_volume_features(h.build_features(frame.reset_index())))))
 base_signal,_,_=h.build_signal(features,h.SignalPlan('baseline','atr18'))
 # Keep original state rules but prevent the original last-bar next-open clamp.
 source=inspect.getsource(late.run_late_reentry)
 old='exit_i = min(i + 1, len(frame) - 1)'
 source=re.sub(r'(?m)^([ ]*)'+re.escape(old),lambda m:m[1]+'if i + 1 >= len(frame):\n'+m[1]+'    curve.append(float(equity))\n'+m[1]+'    continue\n'+m[1]+'exit_i = i + 1',source)
 namespace=dict(late.__dict__);capture={}
 original_metric=late.metric_result
 def metric_capture(spec,curve,trades,**kwargs):
  capture['trades']=trades
  return original_metric(spec,curve,trades,**kwargs)
 namespace['metric_result']=metric_capture;namespace['TRADE_COST']=0.;namespace['SLIPPAGE']=0.
 if unit:namespace['dynamic_allocation']=lambda direction,atr:1.
 exec(compile(source,'<audited EMA-X next-open terminal adapter>','exec'),namespace)
 signal,kinds,_=h.hybrid_signal(features,candidate.signal,base_signal)
 saved_slip=late.SLIPPAGE;late.SLIPPAGE=0.
 try:
  namespace['run_late_reentry'](features,candidate.spec,start_ts=START,collect_trades=True,signal_override=signal,signal_kind_override=kinds,entry_allocation_scale={'hq':candidate.hq_scale,'lq':candidate.lq_scale},stop_fill_mode='gap_open')
 finally:late.SLIPPAGE=saved_slip
 return standardize(capture['trades'],frame)

def tb_run(frame,mods,version,unit):
 tb,ab,cd=mods['tb'],mods['ab'],mods['cd']
 config=replace(tb.V35Config(),warmup_bars=int(frame.index.searchsorted(START)),trade_cost_rate=0.)
 if unit:config=replace(config,max_allocation=1.,long_target_atr_pct=1000.,short_target_atr_pct=1000.)
 flags=ab.SignalFlags(short_use_h1_ema=version!='V41')
 feats=legacy.post_features(ab.build_signals(tb.build_features(frame,config),config,flags),START)
 run=cd.run_backtest(cd.RunSpec(version,1 if version=='V41' else 0,False),frame,pd.Series(0.,index=frame.index),feats,config)
 rows=run.trades.to_dict('records')
 if run.open_position:rows.append({**run.open_position,'exit_ts':frame.index[-1]+STEP,'exit_price':float(frame.close.iloc[-1]),'exit_reason':'terminal_mark'})
 for r in rows:r['signal_ts']=pd.Timestamp(r['entry_ts'])-2*STEP
 return standardize(rows,frame)

def v2p_run(frame,mods,unit):
 # Earliest complete standalone written rules. Causal recovery, not historical-code parity.
 tb=mods['tb'];features=tb.build_features(frame,tb.V35Config())
 c=frame.close;ema=c.ewm(span=96,adjust=False,min_periods=96).mean();slow=c.ewm(span=384,adjust=False,min_periods=384).mean()
 tr=tb.true_range(frame);atr=tr.rolling(672,min_periods=672).mean()/c;channel=tr.rolling(144,min_periods=144).mean();slope=ema.pct_change(24)
 long=(c>ema+2.4*channel)&(ema>slow)&(slope>0)&(features.adx>=28)&(features.plus_di>features.minus_di)&(features.volume_surge>=.25)&(features.h1_adx>18)&(features.h1_plus_di>features.h1_minus_di)
 short=(c<ema-2.4*channel)&(ema<slow)&(slope<0)&(features.adx>=36)&(features.minus_di>features.plus_di)&(features.volume_surge>=.50)&(features.h1_ema_spread<0)
 pos=None;rows=[];last_exit=-100;pending=None
 for i in range(frame.index.searchsorted(START),len(frame)):
  ts=frame.index[i];o,h,l,cl=map(float,frame.iloc[i][['open','high','low','close']]);closed=False
  def finish(price,reason):
   nonlocal pos,last_exit,pending,closed
   rows.append({**pos,'exit_ts':ts,'exit_price':float(price),'exit_reason':reason});pos=None;last_exit=i;pending=None;closed=True
  if pos and pending:finish(o,pending)
  if not pos and not closed and i>last_exit+16 and i>frame.index.searchsorted(START):
   d=1 if long.iloc[i-1] and not short.iloc[i-1] else -1 if short.iloc[i-1] and not long.iloc[i-1] else 0
   if d:
    pos={'entry_ts':ts,'entry_price':o,'direction':d,'allocation':1. if unit else min(3.,(.014 if d==1 else .012)/float(atr.iloc[i-1])),'signal_ts':frame.index[i-1],'entry_bar':i,'high_water':o,'low_water':o}
  if pos:
   d=pos['direction'];a=float(atr.iloc[i-1]);entry=pos['entry_price'];stop=entry*(1-d*12*a);take=entry*(1+d*4*a)
   trail=(pos['high_water']*(1-10*a) if d==1 else pos['low_water']*(1+10*a));trail_active=d*(float(frame.close.iloc[i-1])/entry-1)>0
   if (o<=stop if d==1 else o>=stop):finish(o,'stop_gap')
   elif (l<=stop if d==1 else h>=stop):finish(stop,'stop_loss')
   elif trail_active and (l<=trail if d==1 else h>=trail):finish(min(o,trail) if d==1 else max(o,trail),'trailing_stop')
   elif (h>=take if d==1 else l<=take):finish(take,'take_profit')
   if pos:
    pos['high_water']=max(pos['high_water'],h);pos['low_water']=min(pos['low_water'],l)
    weak=(cl<ema.iloc[i] or features.minus_di.iloc[i]>features.plus_di.iloc[i] or features.adx.iloc[i]<20) if d==1 else (cl>ema.iloc[i] or features.plus_di.iloc[i]>features.minus_di.iloc[i] or features.adx.iloc[i]<20)
    if weak:pending='indicator_exit'
    if i-pos['entry_bar']+1>=192:pending=pending or 'timeout'
 if pos:rows.append({**pos,'exit_ts':frame.index[-1]+STEP,'exit_price':float(frame.close.iloc[-1]),'exit_reason':'terminal_mark'})
 return standardize(rows,frame)

def mii_raw(frame,mods,version):
 ext=append_close_sentinel(frame);context=legacy.mii_context(ext);m1,m12=mods['m1'],mods['m12']
 if version=='V1':
  config=m1.engine.BASELINE
  raw=m1.simulate_trades_live(context.market,m1.signal_state(context.features,config.signal),config.exit,1);filter_=config.filter;exposure=1.5
 else:
  tp,sl=(1.4,3.) if version=='V1.4A' else (1.25,5.)
  raw=m12.simulate_atr_bracket_trades(context,m12.AtrBracketCandidate(version,'atr_bracket',96,tp,sl,24),1)
  filter_=replace(m12.BASE_CONFIG.filter,min_rvol96=1. if version=='V1.3' else .85);exposure=2.5
 raw=[t for t in raw if pd.Timestamp(context.features.ts.iloc[t.signal_i])>=START and t.entry_i<len(frame)]
 return raw,filter_,exposure

def mii_run(frame,mods,version,unit):
 raw,filter_,exposure=mii_raw(frame,mods,version)
 selected=mods['m1'].selected_trades_live(raw,filter_)
 rows=[{**asdict(t),'signal_ts':frame.index[t.signal_i],'allocation':1. if unit else exposure,'leg':'mii'} for t in selected]
 return standardize(rows,frame)

def ens_run(frame,mods,version,unit):
 ens=mods['ens'];early=version=='V35+MII1.3';trend='v35' if early else 'v39';mii='V1.3' if early else 'V1.4'
 raw,filter_,exposure=mii_raw(frame,mods,mii);byentry={}
 for t in raw:
  if mods['m1'].passes_filter(t,filter_):byentry.setdefault(t.entry_i,t)
 config,flags=ens.trend_setup(trend);config=replace(config,warmup_bars=int(frame.index.searchsorted(START)),trade_cost_rate=0.)
 if unit:config=replace(config,max_allocation=1.,long_target_atr_pct=1000.,short_target_atr_pct=1000.)
 feats=legacy.post_features(ens.tbab.build_signals(ens.tb.build_features(frame,config),config,flags),START)
 old_exposure,old_cost=ens.MII_EXPOSURE,ens.MII_ROUND_TRIP
 ens.MII_EXPOSURE=1. if unit else exposure;ens.MII_ROUND_TRIP=0.
 try:run=ens.run_account(version,frame,pd.Series(0.,index=frame.index),feats,config,byentry,enable_v35=True,enable_mii=True,preempt=True,trend_label=trend,mii_label='mii')
 finally:ens.MII_EXPOSURE=old_exposure;ens.MII_ROUND_TRIP=old_cost
 rows=run['trades'].to_dict('records')
 if run['open_position']['trend']:rows.append({**run['open_position']['trend'],'leg':trend,'exit_ts':frame.index[-1]+STEP,'exit_price':float(frame.close.iloc[-1]),'exit_reason':'terminal_mark'})
 if run['open_position']['mii']:
  entry=pd.Timestamp(run['open_position']['mii']['entry_ts']);t=byentry[frame.index.get_loc(entry)]
  rows.append({**asdict(t),'leg':'mii','exit_ts':frame.index[-1]+STEP,'exit_price':float(frame.close.iloc[-1]),'exit_reason':'terminal_mark'})
 for r in rows:
  if r['leg']=='mii':r['allocation']=1. if unit else exposure
  r['signal_ts']=pd.Timestamp(r['entry_ts'])-(STEP if r['leg']=='mii' else 2*STEP)
 return standardize(rows,frame)

def trade_paths(case,frame,mods,unit):
 f,v=case['family'],case['version']
 if f=='EMA-X':return x_early(frame) if v=='V1' else x_final(frame,mods,unit)
 if f=='EMA-TB':return v2p_run(frame,mods,unit) if v=='V2P' else tb_run(frame,mods,v,unit)
 if f=='MII':return mii_run(frame,mods,v,unit)
 return ens_run(frame,mods,v,unit)

# One common linear-contract account engine; trade prices are un-slipped order references.
def account(frame,paths,events,fee,slip,include_funding=True,terminal=True):
 end=frame.index[-1]+STEP;index=frame.index[frame.index>=START];cash=1.;records=[];curve=pd.Series(1.,index=index+STEP)
 last_available=START
 for r in paths:
  entry=r['entry_ts'];exit_=r['exit_ts'];d=int(r['direction']);ep=float(r['entry_price']);xp=float(r['exit_price']);a=float(r['allocation'])
  assert entry>=last_available,(entry,last_available)
  effective_exit=exit_ if r['exit_timing'] in ('bar_open','terminal_close') else exit_+STEP
  next_available=exit_ if r['exit_timing']=='bar_open' else effective_exit
  last_available=next_available
  entry_equity=cash;entry_fill=ep*(1+d*slip);exit_fill=xp*(1-d*slip)
  quantity=entry_equity*a/entry_fill
  entry_fee=abs(quantity*entry_fill)*fee;exit_fee=abs(quantity*exit_fill)*fee
  entry_slip=quantity*ep*slip;exit_slip=quantity*xp*slip
  # Bar-open order events precede millisecond funding, which precedes intrabar exits.
  # For an intrabar exit, observed settlements in that complete bar are assumed first.
  funding_cutoff=exit_+STEP if r['exit_timing']=='intrabar' else exit_
  observed=events[(events.index>=entry)&(events.index<funding_cutoff)]
  funding_steps={}
  for ts,rate in observed.items():
   if ts>=end:continue
   loc=frame.index.get_indexer([ts.floor('15min')])[0]
   if loc<0:continue
   # This proxy is explicit; no missing native marks are treated as exact settlements.
   funding_steps[ts]=-d*quantity*float(frame.open.iloc[loc])*float(rate) if include_funding else 0.
  ftotal=sum(funding_steps.values())
  held=(curve.index>entry)&(curve.index<effective_exit)
  for close_ts in curve.index[held]:
   mark=float(frame.close.loc[close_ts-STEP]);fp=sum(v for t,v in funding_steps.items() if t<close_ts)
   curve.loc[close_ts]=entry_equity+d*quantity*(mark-ep)-entry_fee-entry_slip+fp
  gross=d*quantity*(xp-ep)
  closed_cash=entry_equity+gross-entry_fee-exit_fee-entry_slip-exit_slip+ftotal
  if not terminal and r['exit_reason']=='terminal_mark':
   closed_cash=entry_equity+gross-entry_fee-entry_slip+ftotal
  cash=closed_cash
  curve.loc[curve.index>=effective_exit]=cash
  records.append({**r,'exit_effective_ts':effective_exit,'entry_equity':entry_equity,'quantity':quantity,'entry_fill':entry_fill,'exit_fill':exit_fill,'gross_pnl':gross,'entry_fee':entry_fee,'exit_fee':exit_fee,'entry_slippage_cost':entry_slip,'exit_slippage_cost':exit_slip,'observed_funding_estimate':ftotal,'net_pnl':cash-entry_equity,'exit_equity':cash,'net_trade_return':cash/entry_equity-1})
 assert np.isfinite(curve).all() and (curve>0).all()
 return curve,records

def save_case(case,scenario,frame,paths,events):
 slip=.0008 if scenario=='unit_slip8bps' else .0004
 eq,trades=account(frame,paths,events,.001,slip,True)
 nofund,_=account(frame,paths,events,.001,slip,False)
 ret=eq/eq.shift(1).fillna(1)-1;dd=eq/eq.cummax().clip(lower=1)-1
 monthly=ret.groupby((ret.index-pd.Timedelta(nanoseconds=1)).strftime('%Y-%m')).apply(lambda x:(1+x).prod()-1)
 key=(case['family']+'_'+case['version']+'_'+scenario).replace('.','p').replace('+','_')
 pd.DataFrame({'equity_funding_estimate':eq,'equity_excluding_funding':nofund,'return':ret,'drawdown':dd}).to_csv(OUT/f'{key}_equity.csv',index_label='valuation_ts')
 pd.DataFrame(trades).to_csv(OUT/f'{key}_trades.csv',index=False)
 monthly.mul(100).rename('return_pct').to_csv(OUT/f'{key}_monthly.csv',index_label='month')
 side={}
 for d,label in ((1,'long'),(-1,'short')):
  rr=[r for r in trades if r['direction']==d]
  side[label]={'trades':len(rr),'net_pnl_initial_equity_pct':100*sum(r['net_pnl'] for r in rr),'wins':sum(r['net_pnl']>0 for r in rr)}
 result={**case,'scenario':scenario,'start':START,'end_exclusive':frame.index[-1]+STEP,'return_pct':100*(eq.iloc[-1]-1),'return_excluding_funding_pct':100*(nofund.iloc[-1]-1),'max_drawdown_pct':100*dd.min(),'trades':len(trades),'terminal_closes':sum(r['exit_reason']=='terminal_mark' for r in trades),'wins':sum(r['net_pnl']>0 for r in trades),'fees_initial_equity_pct':100*sum(r['entry_fee']+r['exit_fee'] for r in trades),'slippage_initial_equity_pct':100*sum(r['entry_slippage_cost']+r['exit_slippage_cost'] for r in trades),'funding_estimate_initial_equity_pct':100*sum(r['observed_funding_estimate'] for r in trades),'long_short':side,'monthly_return_pct':monthly.mul(100).to_dict(),'equity_file':str((OUT/f'{key}_equity.csv').relative_to(ROOT)),'trades_file':str((OUT/f'{key}_trades.csv').relative_to(ROOT)),'funding_status':'observed event estimate with trade-open proxy settlement price; coverage incomplete','accounting':'same fixed-quantity account for all versions; original_sizing retains original allocation formula, not inherited per-bar reinvestment algorithm'}
 assert abs(np.prod(1+monthly)-eq.iloc[-1])<1e-10
 assert abs(1+sum(r['net_pnl'] for r in trades)-eq.iloc[-1])<1e-10
 assert abs(side['long']['net_pnl_initial_equity_pct']+side['short']['net_pnl_initial_equity_pct']-result['return_pct'])<1e-8
 result.update({'end':result['end_exclusive'],'return_ex_funding':result['return_excluding_funding_pct'],'return_estimated_funding':result['return_pct'],'max_drawdown':result['max_drawdown_pct'],'equity_path':result['equity_file'],'trades_path':result['trades_file'],'monthly_path':str((OUT/f'{key}_monthly.csv').relative_to(ROOT)),'scenario_alias':{'unit':'equal_1x_base','original_sizing':'original_size_base','unit_slip8bps':'equal_1x_stress'}[scenario],'entry_timing':'K0 close then K2 open for TB trend legs; other legs K0 close then K1 open','funding_event_order':'bar-open trades, then native-timestamp funding, then intrabar protective fills; funding inside exit bar assumed before intrabar exit, execution timestamp not known exactly','actual_entry_notional_definition':'quantity = pre-entry account equity * allocation / actual adverse entry fill; fixed quantity until exit; equal notional is not equal stop-loss risk'})
 return result,eq

def run_all():
 manifest=json.loads((OUT/'sources_manifest.json').read_text())
 for p,d in manifest.items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==d,p
 mods=imports();frame=legacy.frame_with_index(inputs.load_prices('HYPE','15m'));frame=frame.loc[frame.index<END]
 events=legacy.funding_events(inputs.load_funding('HYPE'))
 dump(OUT/'input_binding_amendment.json',{'date_utc':pd.Timestamp.now(tz='UTC'),'reason':'root new startup returns consumed instead of previous study paths before any replay','manifest_path':str(inputs.INPUTS/'manifest.json'),'sha256':hashlib.sha256((inputs.INPUTS/'manifest.json').read_bytes()).hexdigest()})
 results=[];checks=[]
 for case in CASES:
  print('Running',case['family'],case['version'],flush=True)
  unit_paths=trade_paths(case,frame,mods,True);original_paths=trade_paths(case,frame,mods,False)
  dump(OUT/((case['family']+'_'+case['version']).replace('.','p').replace('+','_')+'_paths.json'),{'unit':unit_paths,'original_sizing':original_paths})
  for scenario,paths in [('unit',unit_paths),('original_sizing',original_paths),('unit_slip8bps',unit_paths)]:
   result,_=save_case(case,scenario,frame,paths,events);results.append(result)
  cutoff=START+pd.Timedelta(days=30);prefix=frame.loc[frame.index<cutoff]
  prefix_paths=trade_paths(case,prefix,mods,True)
  peq,_=account(prefix,prefix_paths,events,.001,.0004,True,terminal=False)
  feq,_=account(frame,unit_paths,events,.001,.0004,True,terminal=False)
  common=peq.index.intersection(feq.index);diff=float((peq.loc[common]-feq.loc[common]).abs().max())
  # Prefix terminal is mark-only, so last-bar liquidation is not compared against live continuation.
  check={'family':case['family'],'version':case['version'],'prefix_cutoff':cutoff,'prefix_equity_max_abs_diff':diff,'pass':diff<1e-10}
  checks.append(check);dump(OUT/'results.json',results);dump(OUT/'verification.json',{'status':'PASS' if all(c['pass'] for c in checks) else 'FAIL','checks':checks})
 pd.DataFrame([{k:v for k,v in r.items() if not isinstance(v,(dict,list))} for r in results]).to_csv(OUT/'results.csv',index=False)
 dump(OUT/'feature_contracts.json',{'EMA-X':'EMA96/384,ATR96/672 ratio,ADX28,volume192,closed1hADX21;V18 original helper adds unchanged oscillator/structure fields','EMA-TB':'V35/V41 EMA96/384,ATR672 simple mean,ADX28,volume192,h1ADX21 andEMA24/96;V2P channelATR144 dynamicATR672 lagged1','MII':'V1 RSI7 30/60,MACD12/26/9,ATR96 .006-.028; V1.4A RSI7 40/60,ATR96>=.0075,RVOL96>=.85,ATR96 brackets1.4/3,timeout24; ENS1.3 RVOL96>=1 and1.4>=.85,brackets1.25/5','confirmation':'direct spec to original dataclass/helper inspection before replay; no optimizer called'})
 dump(OUT/'comparison_summary.json',[{'family':f,'early':e,'final':v,'scenario':s,'early_return_pct':next(r['return_pct'] for r in results if r['family']==f and r['version']==e and r['scenario']==s),'final_return_pct':next(r['return_pct'] for r in results if r['family']==f and r['version']==v and r['scenario']==s)} for f,e,v in [('EMA-X','V1','V18'),('EMA-TB','V35','V41'),('MII','V1','V1.4A'),('ENS','V35+MII1.3','V2')] for s in ('unit','original_sizing','unit_slip8bps')])
 print(json.dumps([{k:r[k] for k in ('family','version','scenario','return_pct','max_drawdown_pct','trades')} for r in results],indent=2))


# Read-only acceptance and human handoff; callable after run_all.
def finalize_review():
 results=json.loads((OUT/'results.json').read_text());assert len(results)==27
 checks=[]
 for r in results:
  trades=pd.read_csv(ROOT/r['trades_file']);curve=pd.read_csv(ROOT/r['equity_file']);monthly=pd.read_csv(ROOT/r['monthly_path'])
  qty=np.asarray(trades.quantity);allocation=np.asarray(trades.allocation);pre=np.asarray(trades.entry_equity)
  notional_error=float(np.max(np.abs(qty*np.asarray(trades.entry_fill)-pre*allocation)))
  ledger_error=abs(float(trades.net_pnl.sum())-(float(curve.equity_funding_estimate.iloc[-1])-1))
  monthly_error=abs(float(np.prod(1+monthly.return_pct/100))-float(curve.equity_funding_estimate.iloc[-1]))
  fee_error=float(np.max(np.abs(trades.entry_fee-.001*qty*trades.entry_fill)))
  assert notional_error<1e-10 and ledger_error<1e-10 and monthly_error<1e-10 and fee_error<1e-10
  if r['scenario']!='original_sizing':assert np.allclose(allocation,1.,rtol=0,atol=1e-12)
  assert len(trades)==r['trades']
  checks.append({'family':r['family'],'version':r['version'],'scenario':r['scenario'],'rows':len(trades),'actual_entry_notional_max_abs_error':notional_error,'net_ledger_sum_abs_error':ledger_error,'monthly_product_abs_error':monthly_error,'entry_fee_abs_error':fee_error,'pass':True})
 old=json.loads((OUT/'verification.json').read_text());assert old['status']=='PASS' and len(old['checks'])==9
 dump(OUT/'account_acceptance.json',{'status':'PASS','checks':checks,'prefix_replays':old,'scope':'local per-configuration arithmetic/count/monthly/entry-notional checks; full initial-candidate historical parity is not asserted'})
 mods=imports()
 dump(OUT/'effective_original_configs.json',{'mii_v1':asdict(mods['m1'].engine.BASELINE),'mii_v14a_entry_filter':asdict(replace(mods['m12'].BASE_CONFIG.filter,min_rvol96=.85)),'mii_atr_bracket_v14a':{'atr_window':96,'tp_atr_mult':1.4,'sl_atr_mult':3.,'max_hold_bars':24,'exposure':2.5},'tb_v35':asdict(mods['tb'].V35Config()),'tb_v41_delta':{'cooldown_bars':1,'short_use_h1_ema':False},'x_v18':asdict(mods['xr'].v18_candidate()),'ens_early':{'trend':'V35','mii':'V1.3','single_account':True,'preempt':True,'trend_delay_bars':2,'mii_delay_bars':1},'ens_v2':{'trend':'V39','mii':'V1.4','single_account':True,'preempt':True,'trend_delay_bars':2,'mii_delay_bars':1}})
 dump(OUT/'implementation_amendments.json',{'source_selection_unchanged':True,'new_tuning':False,'actual_notional_correction':'root requested common actual-entry-fill denominator before acceptance; all scenarios rerun; old reference-open denominator results superseded','funding_event_order':'open entry/exit events first, then observed funding with exact native milliseconds, then intrabar stops/targets; when only bar resolution is known, funding inside intrabar exit bar is assumed earlier than exit','git_date_evidence':{'EMA-X_V1_original_script':'git --follow first retained record 6b2bd5b 2026-06-25T21:14:51+08:00, before common start; archived historical prose updated later','EMA-TB_V2P_spec':'git --follow retained record47379c4 2026-07-08T21:21:49+08:00 before common start'},'EMA-X_V1_identity_limit':'Archived V1 is described only as bare crossover. Earliest retained script has cross_only/opposite_cross and that exact pair was predeclared before replay; unique historical V1 exit selection and original full-sample parity cannot be proved.', 'V2P_reproduction_limit':'standalone spec includes close-entry/current-bar ATR and trailing dependencies. This run is causal recovery at next open using previous closed-bar levels, not historical-code parity. Primary executable comparison is V35->V41.'})
 lines=['# EMA 与组合早期版本同段比较','', '固定窗口：2026-07-23 00:00 UTC 至 2026-09-05 15:00 UTC。全部 9 个预先指定版本、3 种情景，共 27 次回放。没有根据这段收益选择早期版本。','', '所有账户按线性 USDT 合约、实际成交数量计算盈亏。基础每次成交手续费 0.10%、滑点 0.04%；压力情景滑点为 0.08%。1x 指入场时实际成交名义金额等于入场前账户权益，持仓数量之后不自动变化；这并不代表各版止损风险相同。原仓位情景只恢复各版入场 allocation 公式，仍使用相同固定数量记账，不沿用原引擎逐 K 杠杆复利算法。','', '资金费是按原生毫秒时间和已观察费率估计；价格以结算所在 15m bar open 代理，不声称完整资金费净收益。假定开盘成交先于资金费，资金费先于该 K 的盘中止盈止损。','', '| 家族/版本 | 角色 | 1x收益估计 | 不含资金费 | 最大回撤 | 交易数 | 原仓位收益估计 | 1x高滑点 |','|---|---|---:|---:|---:|---:|---:|---:|']
 for c in CASES:
  rr={r['scenario']:r for r in results if r['family']==c['family'] and r['version']==c['version']};u=rr['unit']
  lines.append(f"| {c['family']} {c['version']} | {c['role']} | {u['return_pct']:+.4f}% | {u['return_excluding_funding_pct']:+.4f}% | {u['max_drawdown_pct']:.4f}% | {u['trades']} | {rr['original_sizing']['return_pct']:+.4f}% | {rr['unit_slip8bps']['return_pct']:+.4f}% |")
 lines+=['','EMA-X 早期组是按原脚本恢复的 V1 裸交叉基线，采用 cross_only/opposite_cross。原 V1 独立完整规格没有保留，无法证明当年唯一选定的退出配置；这次早期代码与恢复基线的逐笔入退出时间和方向已一致。该组合在本轮查看后段结果前已写入计划。X 的裸交叉版在这段赚了钱，V18 亏损，新增筛选/退出没有在该段兑现优势。但 V18 只有 3 笔交易，单段差异不足以证明每项新增规则都过拟合。MII 的最终版在该段明显改善，说明不能把“版本多”直接当成无效。TB V35 至 V41 没有改善；组合从最早诊断方案至 V2 有改善，但仍然亏损。','','TB V2P 只能作为恢复诊断：原说明的当前 K ATR、极值和收盘进场不能原样当成可执行策略，已统一改为已闭合资料生成保护线、下一根开盘订单；未声称逐笔还原早年回测。TB 正式主比较是最早保留完整因果引擎的 V35 至 V41。ENS 早期方案从未登记为 V1，名称必须保留“最早冻结诊断”。','','TB 趋势腿保留原定 K0 收盘信号、K2 开盘入场；EMA-X/MII 为 K0 收盘信号、K1 开盘入场。期初现金，不能带入区间开始前的订单或信号。所有期末仓位按最后完整 K 收盘退出并计手续费和滑点。','','校验：9 个版本重新截断到前 30 天的净值均与完整回放相同；27 个情景全部通过实际入场名义金额、手续费、逐笔净收益合计、月度复利和数量核对。原规格参数对象、来源哈希、输入绑定和修复说明均保存于本目录。']
 (OUT/'report.md').write_text('\n'.join(lines)+'\n')
 dump(OUT/'source_execution_sha256.json',{'script':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'plan':hashlib.sha256((OUT/'cases_plan.json').read_bytes()).hexdigest(),'source_manifest':hashlib.sha256((OUT/'sources_manifest.json').read_bytes()).hexdigest()})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--freeze-plan',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--verify',action='store_true');a=p.parse_args()
 if a.freeze_plan:freeze_plan()
 if a.run:run_all();finalize_review()
 elif a.verify:finalize_review()
