"""Fixed-parameter full-market replay and predeclared mechanism data generation."""
from pathlib import Path
import ast,datetime as dt,gzip,hashlib,json,math,sys,time
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT.parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from strategy_lab.data.research_bundle import require_research_startup
from strategy_lab.data.research_inputs import complete_window_mask
import frozen_engine as engine
from run_transfer import oracle,bars_from_frame,dd
OUT=ROOT/'artifacts/full-market-20260908'
CONTRACT=ROOT/'specs/full-market-contract-20260908.json'
FEE=.001;SLIP=.0004;DAY=86400000

def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def save_gzip(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 with gzip.open(path,'wt',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,separators=(',',':'),allow_nan=False)

def load_inputs(request):
 return require_research_startup(request,project_root=PROJECT)

def verified_batches(symbols,base,label='batch'):
 request=dict(base,symbols=symbols)
 save(OUT/'startup-requests'/f'{label}.json',request)
 try:
  inputs=load_inputs(request)
 except (ValueError,AssertionError) as exc:
  save(OUT/'startup-failures'/f'{label}.json',{'symbols':symbols,'error':str(exc),'type':type(exc).__name__,'no_fallback':True})
  if len(symbols)==1:
   yield symbols[0],None,str(exc);return
  mid=len(symbols)//2
  yield from verified_batches(symbols[:mid],base,label+'L')
  yield from verified_batches(symbols[mid:],base,label+'R');return
 save(OUT/'startup-reports'/f'{label}.json',inputs.report)
 for symbol,frame in inputs.prices.items():yield symbol,frame,None

def price_features(bars,quotes):
 close=pd.Series([b['close'] for b in bars],dtype=float)
 ma,atr,_,_=engine.indicators(bars);ma=np.array(ma,dtype=float);atr=np.array(atr,dtype=float)
 log=np.log(close);change=log.diff();ma60=close.rolling(60).mean()
 er=(log-log.shift(30)).abs()/change.abs().rolling(30).sum()
 crosses=pd.Series(((close>ma)!=(close.shift(1)>pd.Series(ma).shift(1))).astype(float)).where(pd.Series(ma).notna() & pd.Series(ma).shift(1).notna())
 q=pd.Series(quotes,dtype=float).rolling(30).median()
 return {'ma':ma,'atr':atr,'trend60':((close>ma60)&(ma60>ma60.shift(20))).astype(float).where(ma60.shift(20).notna()).to_numpy(),'momentum30':(close/close.shift(30)-1).to_numpy(),'efficiency30':er.to_numpy(),'chop30':crosses.rolling(30).sum().to_numpy(),'atr_pct':atr/close.to_numpy()*100,'liquidity30':q.to_numpy(),'ma60':ma60.to_numpy(),'log_change':change.to_numpy(),'crosses':crosses.to_numpy()}

def finite_mean(a):
 a=np.asarray(a,dtype=float);a=a[np.isfinite(a)];return float(np.mean(a)) if len(a) else None

def finite_median(a):
 a=np.asarray(a,dtype=float);a=a[np.isfinite(a)];return float(np.median(a)) if len(a) else None

def economic_flags(bars,features):
 close=np.array([b['close'] for b in bars]);rat=close[1:]/close[:-1]
 return {'close_ratio_gt4_or_lt_quarter':bool(((rat>4)|(rat<.25)).any()),'intraday_range_gt10x':any(b['high']/b['low']>10 for b in bars),'atr_gt50pct':bool(np.nanmax(features['atr_pct'])>50)}

def check_replay(bars,runs,mask,deep=False):
 g,c,s=runs;nt=len(g['trades'])
 assert all(mask[e['signal_idx']] for e in c['events'] if e['action']=='entry')
 for result,fee,slip in [(g,0,0),(c,FEE,SLIP),(s,FEE,.0008)]:
  assert len(result['nav'])==len(bars)
  assert all(x>0 and math.isfinite(x) for x in result['nav'])
  expected=g['nav'][-1]*((1-fee)/(1+fee)*(1-slip)/(1+slip))**nt
  assert math.isclose(expected,result['nav'][-1],rel_tol=1e-10,abs_tol=1e-10)
  assert math.isclose(math.prod(1+t['ret_pct']/100 for t in result['trades']),result['nav'][-1],rel_tol=1e-10,abs_tol=1e-10)
  assert [(t['entry_idx'],t['exit_idx']) for t in result['trades']]==[(t['entry_idx'],t['exit_idx']) for t in g['trades']]
  assert all(e['i']==e['signal_idx']+1 for e in result['events'] if e['action']=='entry')
 if deep:
  tape,curve=oracle(bars)
  assert tape==[(t['entry_idx'],t['exit_idx'],t['entry_price'],t['exit_price']) for t in g['trades']]
  assert np.allclose(curve,g['nav'],rtol=1e-12,atol=1e-12)
  live=engine.execute(bars,mode='causal',force_end=False)
  for k in sorted(set([15,min(30,len(bars)-1),len(bars)//2,len(bars)-1])):
   p=engine.execute(bars[:k],mode='causal',force_end=False)
   assert p['nav']==live['nav'][:k]
   assert p['events']==[e for e in live['events'] if e['i']<k]
  src=ast.parse((ROOT/'scripts/source/hype_backtest.py').read_text());fn=next(x for x in src.body if isinstance(x,ast.FunctionDef) and x.name=='backtest')
  ma,atr,_,_=engine.indicators(bars);env={'bars':bars,'n':len(bars),'closes':[x['close'] for x in bars],'ma7':ma,'atr':atr}
  exec(compile(ast.Module(body=[fn],type_ignores=[]),'<reviewed-original-function>','exec'),env)
  old=env['backtest'](0);literal=engine.execute(bars,mode='literal')
  assert old['trades']==[(t['entry_idx'],t['exit_idx'],t['entry_price'],t['exit_price']) for t in literal['trades']]
  assert np.allclose(old['nav'],literal['nav'],rtol=1e-12,atol=1e-12)


def run_segment(symbol,cls,window,f,start,end,deep=False):
 f=f.reset_index(drop=True);bars=bars_from_frame(f);n=len(bars)
 assert f.eligible.all() and f.ts.diff().dropna().eq(pd.Timedelta(days=1)).all()
 mask=(complete_window_mask(f,backward=15,forward=0)&f.research_window_valid).tolist()
 runs=[engine.execute(bars,mode='causal',fee=fee,slip=slip) for fee,slip in [(0,0),(FEE,SLIP),(FEE,.0008)]]
 g,c,stress=runs;check_replay(bars,runs,mask,deep)
 features=price_features(bars,f.quote_volume.tolist());flags=economic_flags(bars,features)
 ident='|'.join([window,symbol,engine.iso(bars[0]['ts']),engine.iso(bars[-1]['ts'])]);m=c['metrics'];ts=c['trades'];gt=g['trades']
 logs=[math.log1p(t['ret_pct']/100) for t in ts];gross_logs=[math.log1p(t['ret_pct']/100) for t in gt]
 wins=[x for x in logs if x>0];losses=[x for x in logs if x<=0]
 top3=sum(sorted(logs,reverse=True)[:3]) if len(logs)>=3 else None
 cost_log=len(ts)*math.log((1-FEE)/(1+FEE)*(1-SLIP)/(1+SLIP))
 assert abs(sum(gross_logs)+cost_log-math.log(m['equity']))<1e-9
 bh=[b['close']/bars[0]['close'] for b in bars];close=np.array([b['close'] for b in bars]);givebacks=[];loss_after_profit=0;trade_rows=[]
 for k,(t,tg) in enumerate(zip(ts,gt)):
  signal_idx=t['entry_idx']-1
  prices=[t['entry_price']]+[b['close'] for b in bars[t['entry_idx']:t['exit_idx']]]
  if t['reason']=='end_of_test':prices.append(t['exit_price'])
  peak=max(prices);mfe=(peak/t['entry_price']-1)*100;giveback=(1-t['exit_price']/max(peak,t['exit_price']))*100
  if t['reason']!='end_of_test':givebacks.append(giveback)
  loss_after_profit+=int(t['ret_pct']<0 and mfe>0)
  row={'run_id':ident,'symbol':symbol,'asset_class':cls,'window':window,'trade_id':k+1,**t,'gross_return_pct':tg['ret_pct'],'log_return_pct':logs[k]*100,'max_close_mfe_pct':mfe,'close_peak_giveback_pct':giveback,'economic_flag':any(flags.values()),'natural_exit':t['reason']!='end_of_test','entry_features_valid':signal_idx>=79,'signal_ts':bars[signal_idx]['ts']}
  for key in ['trend60','momentum30','efficiency30','chop30','atr_pct','liquidity30']:
   val=features[key][signal_idx];row[key]=float(val) if np.isfinite(val) and signal_idx>=79 else None
  trade_rows.append(row)
 logret=math.log(m['equity']);rv=features['log_change'];rv=rv[np.isfinite(rv)]
 row={'run_id':ident,'symbol':symbol,'coin':symbol.split('/')[0],'asset_class':cls,'window':window,'start':m['first_date'],'end':m['last_date'],'n_bars':n,'full_requested_window':f.ts.iloc[0]==start and f.ts.iloc[-1]+pd.Timedelta(days=1)==end,'reaches_global_cutoff':f.ts.iloc[-1]==pd.Timestamp('2026-09-04',tz='UTC'),'economic_flag':any(flags.values()),'economic_flags':','.join(k for k,v in flags.items() if v),'gross_return_pct':g['metrics']['total_return_pct'],'cost_return_pct':m['total_return_pct'],'stress_return_pct':stress['metrics']['total_return_pct'],'cost_max_drawdown_pct':m['max_drawdown_pct'],'buyhold_return_pct':m['buyhold_return_pct'],'buyhold_max_drawdown_pct':dd(bh),'n_trades':len(ts),'n_natural_exits':sum(t['reason']!='end_of_test' for t in ts),'n_terminal_valuations':sum(t['reason']=='end_of_test' for t in ts),'win_rate_pct':m['win_rate_pct'],'mean_win_pct':finite_mean([t['ret_pct'] for t in ts if t['ret_pct']>0]),'mean_loss_pct':finite_mean([t['ret_pct'] for t in ts if t['ret_pct']<=0]),'avg_hold_days':m['avg_hold_days'],'exposure_pct':m['exposure_pct'],'log_growth_pct':logret*100,'gross_log_growth_pct':sum(gross_logs)*100,'winning_log_growth_pct':sum(wins)*100,'losing_log_growth_pct':sum(losses)*100,'cost_log_drag_pct':cost_log*100,'remove_top3_return_zero_pct':math.expm1(logret-top3)*100 if top3 is not None else None,'top3_share_positive_logs':sum(sorted(wins,reverse=True)[:3])/sum(wins) if wins else None,'fraction_close_above_ma60':finite_mean(np.where(np.isnan(features['ma60']),np.nan,close>features['ma60'])),'mean_efficiency30':finite_mean(features['efficiency30']),'crosses_per100bars':finite_mean(features['crosses'])*100 if finite_mean(features['crosses']) is not None else None,'median_atr_pct':finite_median(features['atr_pct']),'realized_log_vol_annual_pct':float(np.std(rv,ddof=1)*np.sqrt(365)*100),'median_quote_volume30':finite_median(features['liquidity30']),'median_close_peak_giveback_pct':finite_median(givebacks),'loss_after_profit_count':loss_after_profit,'representative':False}
 return row,trade_rows,{'bars':bars,'ma':[None if not np.isfinite(x) else float(x) for x in features['ma']],'atr':[None if not np.isfinite(x) else float(x) for x in features['atr']],'runs':{'causal':g,'causal_binance_cost':c,'causal_double_slippage':stress},'valid_signal_mask':mask}


def build_windows():
 w={'full_history':('2019-09-09','2026-09-05'),'main':('2024-12-05','2026-09-05'),'common7':('2025-12-24','2026-09-05')}
 for year in range(2020,2027):w[str(year)]=(f'{year}-01-01',f'{year+1}-01-01' if year<2026 else '2026-09-05')
 return {k:(pd.Timestamp(a,tz='UTC'),pd.Timestamp(b,tz='UTC')) for k,(a,b) in w.items()}

def main():
 assert not (OUT/'run-summary.json').exists(),'Do not overwrite retained results'
 contract=json.loads(CONTRACT.read_text());assert hashlib.sha256((ROOT/'scripts/frozen_engine.py').read_bytes()).hexdigest()==contract['engine_sha256']
 symbols=contract['requested_symbols'];inventory=[];summaries=[];trade_rows=[];recent=[];checks=[];windows=build_windows();parity=[]
 prior=ROOT/'artifacts/20260907';seven=['BTC','ETH','SOL','BNB','UNI','ARB','LIT'];counter=0;start_time=time.time()
 for offset in range(0,len(symbols),48):
  group=symbols[offset:offset+48];print('START batch',offset//48+1,'symbols',len(group),flush=True)
  for symbol,frame,error in verified_batches(group,contract['request_base'],f'b{offset//48+1:02d}'):
   counter+=1;cls=contract['universe_inventory'][symbol];coin=symbol.split('/')[0]
   if frame is None:
    inventory.append({'symbol':symbol,'asset_class':cls,'status':'STARTUP_FAILED','reason':error});continue
   keep=['symbol','ts','open','high','low','close','volume','quote_volume','trade_count','is_closed','timeframe','eligible','research_window_valid','research_segment_id']
   p=OUT/'verified-inputs'/f'{coin}.parquet';p.parent.mkdir(exist_ok=True);frame[keep].to_parquet(p,index=False,compression='zstd')
   inv={'symbol':symbol,'asset_class':cls,'status':'INPUT_VERIFIED','observed_rows':len(frame),'ineligible_rows':int((~frame.eligible).sum()),'segments':int(frame.research_segment_id.nunique()),'first_observed':frame.ts.min().isoformat(),'last_observed':frame.ts.max().isoformat(),'eligible_bars':int(frame.eligible.sum()),'segments_lt30':0,'main_segments':0};deep_done=False;symbol_summaries=[];symbol_trades=[]
   for window,(a,b) in windows.items():
    cut=frame.loc[frame.ts.ge(a)&frame.ts.lt(b)];valid=[]
    for seg,f in cut.groupby('research_segment_id',sort=False):
     if len(f)<30:
      if window=='full_history':inv['segments_lt30']+=1
      continue
     row,trades,chart=run_segment(symbol,cls,window,f,a,b,not deep_done);deep_done=True
     valid.append((row,trades,chart));symbol_summaries.append(row)
     if window=='full_history':symbol_trades.extend(trades)
    if valid:
     row,trades,chart=valid[-1];row['representative']=True
     if window=='main':
      inv['main_segments']=len(valid);inv['main_representative_run_id']=row['run_id']
      save_gzip(OUT/'main-replays'/f'{coin}.json.gz',{'summary':row,**chart})
      for days in [1,7,30,90,180,365]:
       curve=chart['runs']['causal_binance_cost'];bars=chart['bars'];j=max(0,len(bars)-1-days);nav=curve['nav'][j:];anchor=nav[0]
       recent.append({'symbol':symbol,'asset_class':cls,'requested_days':days,'actual_days':len(bars)-1-j,'start':engine.iso(bars[j]['ts']),'end':engine.iso(bars[-1]['ts']),'return_pct':(nav[-1]/anchor-1)*100,'max_drawdown_pct':dd([v/anchor for v in nav]),'entries':sum(e['action']=='entry' and e['i']>j for e in curve['events']),'exits':sum(t['exit_idx']>j for t in curve['trades']),'reaches_global_cutoff':row['reaches_global_cutoff']})
     if coin in seven and window in ['main','common7']:
      prev=json.loads((prior/'results'/('available' if window=='main' else 'common')/coin/'causal_binance_cost/result.json').read_text());now=chart['runs']['causal_binance_cost']
      assert now['nav']==prev['nav'] and now['trades']==prev['trades'],f'prior parity {coin} {window}'
      parity.append({'coin':coin,'window':window,'exact_nav_trade_parity':True})
   checks.append({'symbol':symbol,'checked_segments_windows':len(symbol_summaries),'deep_oracle_prefix_original_parity':deep_done,'status':'PASS' if deep_done else 'INSUFFICIENT_30_BAR_SEGMENT'})
   if not deep_done:inv['status']='INSUFFICIENT_30_BAR_SEGMENT'
   inventory.append(inv);summaries.extend(symbol_summaries);trade_rows.extend(symbol_trades)
   if counter%24==0:print('PROGRESS',counter,'/',len(symbols),'run windows',len(summaries),'full-history trades',len(trade_rows),'seconds',round(time.time()-start_time),flush=True)
  save(OUT/'progress.json',{'processed_symbols':counter,'summaries':len(summaries),'trades':len(trade_rows),'seconds':time.time()-start_time})
 pd.DataFrame(summaries).to_csv(OUT/'all-window-results.csv',index=False)
 pd.DataFrame(trade_rows).to_csv(OUT/'full-history-trades.csv.gz',index=False,compression='gzip')
 pd.DataFrame(recent).to_csv(OUT/'recent-slices.csv',index=False)
 save(OUT/'coverage-ledger.json',inventory);pd.DataFrame(inventory).to_csv(OUT/'coverage-ledger.csv',index=False)
 save(OUT/'replay-validation.json',{'checks':checks,'prior_seven_parity':parity,'prior_parity_count':len(parity),'parameters_unchanged':True})
 assert len(inventory)==len(symbols) and len(parity)==14
 save(OUT/'run-summary.json',{'status':'COMPLETED_WITH_EXPLICIT_COVERAGE','requested_symbols':len(symbols),'input_verified':sum(x['status']!='STARTUP_FAILED' for x in inventory),'usable_symbols':sum(x['status']=='INPUT_VERIFIED' for x in inventory),'startup_failures':[x for x in inventory if x['status']=='STARTUP_FAILED'],'segment_window_replays':len(summaries),'full_history_trades':len(trade_rows),'elapsed_seconds':time.time()-start_time,'contract_sha256':hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
 print('DONE',counter,'symbols',len(summaries),'segment/windows',len(trade_rows),'full-history trades',flush=True)

if __name__=='__main__':main()
