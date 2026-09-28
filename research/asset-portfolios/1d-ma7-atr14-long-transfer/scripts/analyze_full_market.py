"""Describe fixed-parameter transfer and test frozen, ex-ante contrasts by year."""
from pathlib import Path
import hashlib,json,math
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/full-market-20260908'
SEED=20260908

def save(name,value):
 (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def num(x):return float(x) if pd.notna(x) and np.isfinite(x) else None

def stats(frame):
 if frame.empty:return {'n':0}
 x=frame.cost_return_pct;w=frame[x>0]
 return {'n':len(frame),'symbols':int(frame.symbol.nunique()),'profitable':int((x>0).sum()),'losing':int((x<0).sum()),'zero':int((x==0).sum()),'profitable_share_pct':float((x>0).mean()*100),'median_return_pct':num(x.median()),'mean_return_pct':num(x.mean()),'p10_return_pct':num(x.quantile(.1)),'p90_return_pct':num(x.quantile(.9)),'median_drawdown_pct':num(frame.cost_max_drawdown_pct.median()),'median_bh_return_pct':num(frame.buyhold_return_pct.median()),'beat_bh_share_pct':float((x>frame.buyhold_return_pct).mean()*100),'median_trades':num(frame.n_trades.median()),'no_trade_symbols':int((frame.n_trades==0).sum()),'gross_positive_cost_nonpositive':int(((frame.gross_return_pct>0)&(x<=0)).sum()),'median_cost_drag_arithmetic_pp':num((frame.gross_return_pct-x).median()),'median_cost_log_drag_pct':num(frame.cost_log_drag_pct.median()),'median_win_rate_pct':num(frame.win_rate_pct.median()),'economic_flag_count':int(frame.economic_flag.sum()),'winner_top3_removal_nonpositive':int((w.remove_top3_return_zero_pct<=0).sum()),'winner_top3_removal_eligible':int(w.remove_top3_return_zero_pct.notna().sum()),'median_winner_top3_share_positive_logs':num(w.top3_share_positive_logs.median())}

def assign_cohort(r):
 if r.full_requested_window:return 'complete_639_days'
 if not r.reaches_global_cutoff:return 'ended_before_cutoff'
 if r.n_bars>=180:return 'partial_180plus_to_cutoff'
 return 'short_30_179_to_cutoff'

def groupstats(t):
 return {'trades':len(t),'symbols':int(t.symbol.nunique()),'months':int(t.entry_month.nunique()),'mean_return_pct':num(t.ret_pct.mean()),'median_return_pct':num(t.ret_pct.median()),'win_rate_pct':num((t.ret_pct>0).mean()*100) if len(t) else None,'mean_log_return_pct':num(t.log_return_pct.mean()),'median_hold_days':num(t.hold_days.median())}

def contrast_masks(t,key):
 if key=='trend60':return t.trend60.eq(1),t.trend60.eq(0)
 if key=='momentum30':return t.momentum30.gt(0),t.momentum30.le(0)
 if key=='efficiency30':return t.efficiency30.ge(.25),t.efficiency30.lt(.1)
 if key=='chop30':return t.chop30.le(3),t.chop30.ge(8)
 if key=='atr_pct':return t.atr_pct.le(3),t.atr_pct.gt(6)
 if key=='liquidity30':return t.liquidity30.ge(1e7),t.liquidity30.lt(1e7)
 raise KeyError(key)

def bootstrap_contrast(t,positive,negative,seed):
 selected=positive|negative;t=t.loc[selected].copy();positive=positive.loc[selected].to_numpy();negative=negative.loc[selected].to_numpy()
 if not positive.any() or not negative.any():return {'estimate_log_pp':None,'ci95':None,'month_adjusted_log_pp':None}
 si,symbols=pd.factorize(t.symbol,sort=True);mi,months=pd.factorize(t.entry_month,sort=True);ns,nm=len(symbols),len(months);idx=si*nm+mi
 def mats(mask):
  count=np.bincount(idx[mask],minlength=ns*nm).reshape(ns,nm).astype(float)
  total=np.bincount(idx[mask],weights=t.log_return_pct.to_numpy()[mask],minlength=ns*nm).reshape(ns,nm)
  return count,total
 ca,sa=mats(positive);cb,sb=mats(negative)
 estimate=sa.sum()/ca.sum()-sb.sum()/cb.sum()
 rng=np.random.default_rng(seed);xs=rng.poisson(1,size=(500,ns)).astype(float);xm=rng.poisson(1,size=(500,nm)).astype(float)
 def draws(mat):return np.einsum('bi,ij,bj->b',xs,mat,xm,optimize=True)
 na,nb=draws(ca),draws(cb);a,b=draws(sa),draws(sb);valid=(na>0)&(nb>0);delta=a[valid]/na[valid]-b[valid]/nb[valid]
 # Same-entry-month comparison, descriptive control for shared market periods.
 cam,cbm=ca.sum(axis=0),cb.sum(axis=0);sam,sbm=sa.sum(axis=0),sb.sum(axis=0);both=(cam>0)&(cbm>0)
 weight=cam[both]*cbm[both]/(cam[both]+cbm[both]);monthly=sam[both]/cam[both]-sbm[both]/cbm[both]
 adjusted=float(np.average(monthly,weights=weight)) if both.any() else None
 return {'estimate_log_pp':float(estimate),'ci95':[float(x) for x in np.quantile(delta,[.025,.975])] if len(delta)>100 else None,'bootstrap_valid_draws':len(delta),'month_adjusted_log_pp':adjusted,'months_with_both_groups':int(both.sum())}

def main():
 assert (OUT/'run-summary.json').exists(),'Replay incomplete'
 assert not (OUT/'analysis.json').exists(),'Preserve retained analysis'
 r=pd.read_csv(OUT/'all-window-results.csv');t=pd.read_csv(OUT/'full-history-trades.csv.gz');coverage=json.loads((OUT/'coverage-ledger.json').read_text())
 main=r[r.window.eq('main')&r.representative].copy();main['cohort']=main.apply(assign_cohort,axis=1);main.to_csv(OUT/'main-symbol-results.csv',index=False)
 cohorts=[]
 for cls in ['COIN','UNKNOWN']:
  pool=main[main.asset_class.eq(cls)]
  for cohort in ['ALL_AVAILABLE','complete_639_days','partial_180plus_to_cutoff','short_30_179_to_cutoff','ended_before_cutoff']:
   subset=pool if cohort=='ALL_AVAILABLE' else pool[pool.cohort.eq(cohort)]
   for clean in [False,True]:
    x=subset[~subset.economic_flag] if clean else subset
    cohorts.append({'asset_class':cls,'cohort':cohort,'exclude_economic_flags':clean,**stats(x)})
 fixed=main[main.asset_class.eq('COIN')&main.cohort.eq('complete_639_days')]
 correlations=[]
 for clean in [False,True]:
  x=fixed[~fixed.economic_flag] if clean else fixed
  for feature in ['buyhold_return_pct','fraction_close_above_ma60','mean_efficiency30','crosses_per100bars','median_atr_pct','realized_log_vol_annual_pct','median_quote_volume30']:
   z=x[[feature,'log_growth_pct']].dropna();rho=spearmanr(z[feature],z.log_growth_pct).statistic if len(z)>2 and z[feature].nunique()>1 else None
   correlations.append({'exclude_economic_flags':clean,'feature':feature,'n':len(z),'spearman_rho':num(rho),'meaning':'contemporaneous descriptive relationship, not a tradable predictor'})
 shape_groups=[]
 for clean in [False,True]:
  x=fixed[~fixed.economic_flag].copy() if clean else fixed.copy()
  x['buyhold_bin']=pd.cut(x.buyhold_return_pct,[-np.inf,-50,0,100,np.inf],right=False,labels=['<-50%','-50..0%','0..100%','>=100%'])
  x['atr_bin']=pd.cut(x.median_atr_pct,[-np.inf,3,6,10,np.inf],right=False,labels=['<3%','3..6%','6..10%','>=10%'])
  x['er_bin']=pd.cut(x.mean_efficiency30,[-np.inf,.1,.25,np.inf],right=False,labels=['<0.10','0.10..0.25','>=0.25'])
  x['chop_bin']=pd.cut(x.crosses_per100bars,[-np.inf,10,20,np.inf],right=False,labels=['<10/100d','10..20/100d','>=20/100d'])
  for feature in ['buyhold_bin','atr_bin','er_bin','chop_bin']:
   for value,group in x.groupby(feature,observed=True):shape_groups.append({'exclude_economic_flags':clean,'feature':feature,'group':str(value),**stats(group)})
  for (direction,er),group in x.groupby([x.buyhold_return_pct.gt(0),'er_bin'],observed=True):shape_groups.append({'exclude_economic_flags':clean,'feature':'direction_x_efficiency','group':('up' if direction else 'down')+' / '+str(er),**stats(group)})
 by_year=[]
 for year in range(2020,2027):
  q=r[r.window.eq(str(year))&r.asset_class.eq('COIN')&r.full_requested_window]
  for clean in [False,True]:by_year.append({'year':year,'exclude_economic_flags':clean,**stats(q[~q.economic_flag] if clean else q)})
 persistence=[]
 for clean in [False,True]:
  for year in range(2020,2026):
   a=r[r.window.eq(str(year))&r.asset_class.eq('COIN')&r.full_requested_window];b=r[r.window.eq(str(year+1))&r.asset_class.eq('COIN')&r.full_requested_window]
   p=a.merge(b,on='symbol',suffixes=('_prev','_next'));p=p.loc[~(p.economic_flag_prev|p.economic_flag_next)] if clean else p
   if len(p)<4:continue
   cutoff=p.log_growth_pct_prev.quantile(.75);top=p.log_growth_pct_prev.ge(cutoff)
   rho=spearmanr(p.log_growth_pct_prev,p.log_growth_pct_next).statistic if p.log_growth_pct_prev.nunique()>1 else None
   persistence.append({'previous_year':year,'next_year':year+1,'exclude_economic_flags':clean,'pairs':len(p),'spearman_rho':num(rho),'prior_top_quartile_n':int(top.sum()),'next_median_return_prior_top':num(p.loc[top,'cost_return_pct_next'].median()),'next_median_return_others':num(p.loc[~top,'cost_return_pct_next'].median()),'next_positive_share_prior_top_pct':num(p.loc[top,'cost_return_pct_next'].gt(0).mean()*100),'next_positive_share_others_pct':num(p.loc[~top,'cost_return_pct_next'].gt(0).mean()*100),'conditioning':'Both complete calendar windows observed; survivor-pair diagnostic only'})
 t['entry']=pd.to_datetime(t.entry_date,utc=True);t['exit']=pd.to_datetime(t.exit_date,utc=True);t['entry_month']=t.entry_date.str[:7]
 available=t[t.asset_class.eq('COIN')&t.entry_features_valid].copy()
 natural=available[available.natural_exit].copy()
 periods={'all_2020plus':('2020-01-01','2026-09-05'),'development_2020_2023':('2020-01-01','2024-01-01'),'audit_2024':('2024-01-01','2025-01-01'),'audit_2025':('2025-01-01','2026-01-01'),'audit_2026':('2026-01-01','2026-09-05')}
 contrasts=[];purge=[]
 for period,(a,b) in periods.items():
  a=pd.Timestamp(a,tz='UTC');b=pd.Timestamp(b,tz='UTC');entry_period=natural[natural.entry.ge(a)&natural.entry.lt(b)];eligible=entry_period[entry_period.exit.lt(b)]
  purge.append({'period':period,'natural_entries':len(entry_period),'cross_boundary_exits_removed':len(entry_period)-len(eligible),'eligible_closed_trades':len(eligible),'terminal_valuations_excluded':int((available.entry.ge(a)&available.entry.lt(b)&~available.natural_exit).sum())})
  for clean in [False,True]:
   v=eligible[~eligible.economic_flag] if clean else eligible
   for j,key in enumerate(['trend60','momentum30','efficiency30','chop30','atr_pct','liquidity30']):
    positive,negative=contrast_masks(v,key);a_stat,b_stat=groupstats(v[positive]),groupstats(v[negative]);enough=all(z['trades']>=30 and z['symbols']>=10 and z['months']>=5 for z in [a_stat,b_stat])
    effect=bootstrap_contrast(v,positive,negative,SEED+j+sum(map(ord,period)))
    contrasts.append({'period':period,'exclude_economic_flags':clean,'feature':key,'positive_group':a_stat,'negative_group':b_stat,'adequate_sample':enough,**effect})
 # Label-censoring sensitivity is reported, not used for threshold selection.
 censoring=[]
 for key in ['trend60','momentum30','efficiency30','chop30','atr_pct','liquidity30']:
  aa=available[available.entry.ge(pd.Timestamp('2020-01-01',tz='UTC'))];p,n=contrast_masks(aa,key)
  censoring.append({'feature':key,'includes_terminal_valuation_labels':True,'positive':groupstats(aa[p]),'negative':groupstats(aa[n]),'mean_log_difference_pp':num(aa.loc[p,'log_return_pct'].mean()-aa.loc[n,'log_return_pct'].mean())})
 source_counts={'requested':len(coverage),'coin_requested':sum(x['asset_class']=='COIN' for x in coverage),'unknown_requested':sum(x['asset_class']=='UNKNOWN' for x in coverage),'startup_failed':sum(x['status']=='STARTUP_FAILED' for x in coverage),'no_30bar_segment':sum(x['status']=='INSUFFICIENT_30_BAR_SEGMENT' for x in coverage),'main_symbols':len(main),'main_coin_symbols':int(main.asset_class.eq('COIN').sum()),'main_unknown_symbols':int(main.asset_class.eq('UNKNOWN').sum()),'no_main_segment_symbols':[x['symbol'] for x in coverage if not x.get('main_segments',0)],'full_history_natural_trades':int(t.natural_exit.sum()),'full_history_terminal_trades':int((~t.natural_exit).sum()),'coin_entry_features_valid_trades':len(available),'coin_natural_feature_trades':len(natural)}
 result={'coverage':source_counts,'cohort_statistics':cohorts,'contemporaneous_correlations':correlations,'price_shape_groups':shape_groups,'calendar_years':by_year,'coin_persistence':persistence,'feature_contrasts':contrasts,'period_purge':purge,'terminal_label_sensitivity':censoring,'reference_symbols':main[main.coin.isin(['BTC','ETH','SOL','BNB','UNI','ARB','LIT','HYPE'])].replace({np.nan:None}).to_dict('records'),'methodology_sources':['https://arxiv.org/abs/1106.2125','https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanrho.html'],'not_blind_oos':True,'funding_included':False,'analysis_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 save('analysis.json',result)
 pd.DataFrame(cohorts).to_csv(OUT/'cohort-statistics.csv',index=False);pd.DataFrame(correlations).to_csv(OUT/'descriptive-correlations.csv',index=False);pd.DataFrame(shape_groups).to_csv(OUT/'price-shape-groups.csv',index=False);pd.DataFrame(persistence).to_csv(OUT/'coin-persistence.csv',index=False)
 flat=[]
 for x in contrasts:flat.append({**{k:v for k,v in x.items() if k not in ['positive_group','negative_group','ci95']},'ci_low':x['ci95'][0] if x['ci95'] else None,'ci_high':x['ci95'][1] if x['ci95'] else None,**{'positive_'+k:v for k,v in x['positive_group'].items()},**{'negative_'+k:v for k,v in x['negative_group'].items()}})
 pd.DataFrame(flat).to_csv(OUT/'entry-feature-contrasts.csv',index=False)
 print(json.dumps(source_counts,ensure_ascii=False));print('Analysis complete; every predeclared contrast retained.')

if __name__=='__main__':main()
