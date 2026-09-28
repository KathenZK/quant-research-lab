"""Read-only PUBLIC100 ETF replay/attribution, outputs confined to this temp dir.
Frozen batch inputs only; no downloaded data, fitting, candidate search or promotion.
Controls are a finite retrospective attribution exercise, not predeclared validation.
"""
from pathlib import Path
import json, hashlib, datetime
import numpy as np
import pandas as pd
P=Path(__file__).resolve().parent
S=P/'snapshot'; E=S/'artifacts/equity-diagnostic'
V=['A7_TEXT_ROC252','A9_CODE_MOM63','A9_TEXT_ROC252','A36_JANUARY_BAROMETER','C1_GEM','C4_KDA100']
GROUP=['SPY','EFA','BND','VNQ','GSG']; SECTOR=['VNQ','XLK','XLE','XLV','XLF','KBE','VAW','XLY','XLP','VGT']
data={}
for f in (P/'raw').glob('*.json'):
    o=json.loads(f.read_text())['chart']['result'][0]
    d=pd.DataFrame(o['indicators']['quote'][0],index=pd.to_datetime(o['timestamp'],unit='s',utc=True).tz_convert('America/New_York').normalize().tz_localize(None))
    d['adjclose']=o['indicators']['adjclose'][0]['adjclose'];d=d.loc[d.index<'2026-09-01']
    d['adjopen']=d.open*d.adjclose/d.close
    data[f.stem]=d
T=np.load(E/f'{V[0]}-targets.npz',allow_pickle=True);symbols=list(T['symbols']);dates=pd.DatetimeIndex(T['dates'])
AC=pd.DataFrame({s:data[s].adjclose for s in symbols}); AO=pd.DataFrame({s:data[s].adjopen for s in symbols})
C=AC.loc[dates].to_numpy(); O=AO.loc[dates].to_numpy()
assert np.isfinite(C).all() and np.isfinite(O).all()

def stats(eq):
    r=eq.pct_change().dropna();years=(eq.index[-1]-eq.index[0]).days/365.25
    return dict(total_return=float(eq.iloc[-1]/eq.iloc[0]-1),cagr=float((eq.iloc[-1]/eq.iloc[0])**(1/years)-1),mdd=float((eq/eq.cummax()-1).min()),annual_vol=float(r.std()*np.sqrt(252)),sharpe_rf0=float(r.mean()/r.std()*np.sqrt(252)))

def replay(W,R,cost=.001):
    # Independent cash/share implementation with bisection solving post-fee equity.
    # No original module imported; all audited strategies/controls are long-only.
    q=np.zeros(len(symbols)); cash=1.; values=[]; turnover=0.; mincash=1.
    for i,dt in enumerate(dates):
        if R[i]:
            current=q*O[i];before=cash+current.sum();lo,hi=0.,before
            assert W[i].min()>-1e-12 and W[i].sum()<1+1e-10
            for _ in range(70):
                mid=(lo+hi)/2
                if mid+cost*np.abs(W[i]*mid-current).sum()>before:hi=mid
                else:lo=mid
            target=W[i]*((lo+hi)/2); trades=target-current
            cash-=trades.sum()+cost*np.abs(trades).sum();q+=trades/O[i]
            turnover+=np.abs(trades).sum()/before
        values.append(cash+q@C[i]);mincash=min(mincash,cash)
    values[-1]-=cost*np.abs(q*C[-1]).sum()
    eq=pd.Series([1.]+values,index=[dates[0]-pd.Timedelta(days=1)]+list(dates))
    return eq,float(turnover),float(mincash)

def fixed(pool,weights=None):
    w=np.zeros((len(dates),len(symbols)))
    for s,v in zip(pool,weights if weights is not None else [1/len(pool)]*len(pool)):w[:,symbols.index(s)]=v
    rb=np.r_[True,dates.to_period('M')[1:]!=dates.to_period('M')[:-1]]
    return replay(w,rb)[0]

pub=json.loads((E/'results.json').read_text())['results']; pub={x['variant']:x for x in pub if x['cost_bps']==10}
eqs={};out={'status':'EXPLORE_UNTRUSTED_RETROSPECTIVE_QUALITY_AUDIT','window':[str(dates[0].date()),str(dates[-1].date())],'variants':{},'controls':{},'selection_checks':{}}
for v in V:
    t=np.load(E/f'{v}-targets.npz',allow_pickle=True);W=t['weights'];R=t['rebalances']; eq,turn,mincash=replay(W,R)
    saved=pd.read_csv(E/f'{v}-10bps-equity.csv',index_col=0,parse_dates=True).iloc[:,0]
    assert list(eq.index)==list(saved.index)
    err=float(np.max(np.abs(eq.to_numpy()-saved.to_numpy())))
    assert err<1e-10,(v,err)
    orders=pd.read_csv(E/f'{v}-10bps-orders.csv')
    asset_profit=(-(orders.signed_notional+orders.fee)).groupby(orders.symbol).sum()
    assert abs(asset_profit.sum()-(eq.iloc[-1]-1))<1e-10
    diag=stats(eq);diag.update({'max_abs_equity_replay_error':err,'min_cash':mincash,'turnover_one_way':turn,'annual_turnover':turn/((dates[-1]-dates[0]).days/365.25),'asset_profit_initial_capital_units':asset_profit.to_dict(),'order_count':len(orders),'mean_target_weight':dict(zip(symbols,W.mean(axis=0))),'max_target_weight':float(W.max()),'mean_target_cash':float((1-W.sum(axis=1)).mean()),'monthly_rebalance_count':int(R.sum())})
    trough=(eq/eq.cummax()-1).idxmin();peak=eq.loc[:trough].idxmax()
    diag['drawdown_dates']={'peak_before_max_dd':str(peak.date()),'max_dd_trough':str(trough.date())}
    diag['cost_cagr']={str(x['cost_bps']):x['cagr'] for x in json.loads((E/'results.json').read_text())['results'] if x['variant']==v}
    eqs[v]=eq;out['variants'][v]=diag
    if v.startswith('A9'):
        tech=W[:,[symbols.index('XLK'),symbols.index('VGT')]]
        fin=W[:,[symbols.index('XLF'),symbols.index('KBE')]]
        diag['overlap']={'fraction_sessions_holding_both_tech':float((tech.min(axis=1)>0).mean()),'fraction_rebalances_holding_both_tech':float((tech[R].min(axis=1)>0).mean()),'mean_target_tech_weight':float(tech.sum(axis=1).mean()),'fraction_sessions_holding_both_financial':float((fin.min(axis=1)>0).mean()),'mean_target_financial_weight':float(fin.sum(axis=1).mean()),'tech_fraction_of_net_profit':float(asset_profit.reindex(['XLK','VGT']).sum()/asset_profit.sum())}
    if v=='C4_KDA100':
        diag['fraction_sessions_target_one_asset_gt_50pct']=float((W.max(axis=1)>.5+1e-8).mean())
        diag['fraction_sessions_cash_eq_50pct']=float(np.isclose(1-W.sum(axis=1),.5).mean())
        diag['fraction_sessions_cash_eq_100pct']=float(np.isclose(1-W.sum(axis=1),1).mean())

spy=pd.read_csv(E/'SPY_BUY_HOLD-10bps-equity.csv',index_col=0,parse_dates=True).iloc[:,0];eqs['SPY_BUY_HOLD']=spy
for name,pool,ws in [('STATIC_SPY60_BIL40_MONTHLY',['SPY','BIL'],[.6,.4]),('STATIC_SECTOR10_EQ_MONTHLY',SECTOR,None),('STATIC_GROUP5_EQ_MONTHLY',GROUP,None)]:
    eq=fixed(pool,ws);eqs[name]=eq;out['controls'][name]=stats(eq);eq.to_csv(P/f'{name}-equity.csv')

for v,eq in eqs.items():
    rec=out['variants'].get(v,out['controls'].get(v))
    if rec is None:out['controls'][v]=rec=stats(eq)
    r=eq.pct_change().dropna();years={str(y):float((1+g).prod()-1) for y,g in r.groupby(r.index.year)};rec['yearly']=years
    paired={y:float(np.log1p(r)-np.log1p(pub['SPY_BUY_HOLD']['yearly'][y])) for y,r in years.items()}
    rec['log_relative_wealth_contribution_by_year_vs_spy']=paired
    rec['years_beating_spy_with_1e_10_tolerance']=sum(x>1e-10 for x in paired.values());rec['years_tied_spy_with_1e_10_tolerance']=sum(abs(x)<=1e-10 for x in paired.values())
    rec['periods']={}
    for label,start,end in [('2011-2015','2011-01-01','2015-12-31'),('2016-2020','2016-01-01','2020-12-31'),('2021-2026_partial','2021-01-01','2026-08-31')]:
        rr=r.loc[start:end];base=eq.index[eq.index<rr.index[0]][-1];pe=eq.loc[base:rr.index[-1]];rec['periods'][label]=stats(pe)

month_dates=dates[np.r_[True,dates.to_period('M')[1:]!=dates.to_period('M')[:-1]]]
selection={v:[] for v in V[:-1]};unit_changes={}; jan=[]
for v in V[:-1]:
    T=np.load(E/f'{v}-targets.npz',allow_pickle=True);check=[]
    for dt in month_dates:
        i=AC.index.get_loc(dt);p=AC.iloc[i-1];hist=AC.iloc[:i];wanted=None
        if v=='A7_TEXT_ROC252':wanted=list((p[GROUP]/AC.iloc[i-253][GROUP]-1).sort_values(ascending=False,kind='stable').index[:3])
        elif v.startswith('A9'):
            L=63 if 'CODE' in v else 252
            score=p[SECTOR]-AC.iloc[i-1-L][SECTOR] if L==63 else p[SECTOR]/AC.iloc[i-1-L][SECTOR]-1
            wanted=list(score.sort_values(ascending=False,kind='stable').index[:3])
        elif v=='C1_GEM':
            months=hist.groupby(hist.index.to_period('M')).last();m=months.iloc[-1]/months.iloc[-13]-1
            wanted=[('SPY' if m.SPY>=m.EFA else 'EFA') if m.SPY>=m.BIL else 'BIL']
        elif v=='A36_JANUARY_BAROMETER':
            if dt.month==1:wanted=['SPY']
            elif dt.month==2:
                jd=hist[hist.index.year==dt.year];wanted=['SPY' if jd.SPY.iloc[-1]>jd.SPY.iloc[0] else 'BIL']
        if wanted is not None:
            row=T['weights'][dates.get_loc(dt)];actual=[s for s,x in zip(symbols,row) if x>1e-10]
            assert set(wanted)==set(actual),(v,dt,wanted,actual)
            check.append(str(dt.date()))
    selection[v]={'checked_signal_dates':len(check),'mismatches':0,'causal_inputs':'prior completed daily close or known month/year'}
out['selection_checks']=selection

# Unit-scaling invariance diagnostic, not a backtest or parameter comparison.
# Rescale VGT alone by 10 for all times (same investment returns, new quote unit).
for code in [True,False]:
    L=63 if code else 252;changes=[]
    for dt in month_dates:
        i=AC.index.get_loc(dt);p=AC.iloc[i-1][SECTOR].copy();b=AC.iloc[i-1-L][SECTOR].copy()
        orig=p-b if code else p/b-1
        p['VGT']*=10;b['VGT']*=10
        scaled=p-b if code else p/b-1
        if set(orig.nlargest(3).index)!=set(scaled.nlargest(3).index):changes.append(str(dt.date()))
    unit_changes['MOM63' if code else 'ROC252']={'months_changed':len(changes),'months_checked':len(month_dates),'changed_dates':changes}
out['unit_scaling_test_VGT_times_10']=unit_changes

for yr in range(2011,2027):
    jd=AC.loc[(AC.index.year==yr)&(AC.index.month==1),'SPY'];dec=AC.loc[AC.index<jd.index[0],'SPY'].iloc[-1]
    sourceproxy=float(jd.iloc[-1]/jd.iloc[0]-1);fulljan=float(jd.iloc[-1]/dec-1)
    priorjanopen=float(AO.loc[jd.index[0],'SPY']);febdate=AC.index[(AC.index.year==yr)&(AC.index.month==2)][0]
    nextopenproxy=float(AO.loc[febdate,'SPY']/priorjanopen-1)
    # Open-to-open proxy is only a timing sensitivity, not exact source LEAN reproduction.
    jan.append({'year':yr,'first_last_close_january_return':sourceproxy,'dec_last_close_to_jan_last_close_return':fulljan,'jan_first_open_to_feb_first_open_return_proxy':nextopenproxy,'published_feb_dec_asset':'SPY' if sourceproxy>0 else 'BIL','full_january_signal_differs':bool((sourceproxy>0)!=(fulljan>0)),'open_proxy_signal_differs':bool((sourceproxy>0)!=(nextopenproxy>0)),'published_year_return':out['variants']['A36_JANUARY_BAROMETER']['yearly'][str(yr)],'spy_year_return':pub['SPY_BUY_HOLD']['yearly'][str(yr)]})
out['A36_january_sensitivity']=jan

# Parent-requested single identified timing audit: only the 2021 February
# decision is changed. This is exposed-history sensitivity, not source replication
# or a new optimized candidate. All other positions/dates/costs remain fixed.
t=np.load(E/'A36_JANUARY_BAROMETER-targets.npz',allow_pickle=True)
w=t['weights'].copy();r=t['rebalances'].copy()
mask=(dates>='2021-02-01')&(dates<'2022-01-01');w[mask]=0.;w[mask,symbols.index('BIL')]=1.
timing,_,_=replay(w,r)
timing.to_csv(P/'A36_only_2021_feb_dec_BIL_sensitivity-equity.csv')
out['A36_only_2021_feb_dec_BIL_sensitivity']={
    'status':'POST_HOC_SINGLE_IDENTIFIED_TIMING_SENSITIVITY_NOT_SOURCE_REPLICATION',
    **stats(timing),'terminal_initial_capital_units':float(timing.iloc[-1]),
    'year_2021_return':float((1+timing.pct_change().dropna().loc['2021']).prod()-1),
    'published_terminal_initial_capital_units':float(eqs['A36_JANUARY_BAROMETER'].iloc[-1]),
    'published_year_2021_return':out['variants']['A36_JANUARY_BAROMETER']['yearly']['2021']}

# C4 semantic and optimizer KKT audit, reconstruct prior-close moments/covariance
# without importing original engine or solving for an alternative portfolio.
kda=['SPY','VGK','EWJ','EEM','VNQ','RWX','IEF','TLT','DBC','GLD','VWO','BND']
T=np.load(E/'C4_KDA100-targets.npz',allow_pickle=True);rets=AC.pct_change(fill_method=None);c4checks=[]
for dt in month_dates:
    hist=AC.loc[AC.index<dt,kda];m=hist.groupby(hist.index.to_period('M')).last()
    mom=sum(mult*(m.iloc[-1]/m.iloc[-lag-1]-1) for lag,mult in [(1,12),(3,4),(6,2),(12,1)])
    chosen=[s for s in mom.iloc[:10].sort_values(ascending=False,kind='stable').index[:5] if mom[s]>0]
    a=float((mom[['VWO','BND']]>0).mean());row=pd.Series(T['weights'][dates.get_loc(dt)],index=symbols).copy()
    if mom.IEF>0:row['IEF']-=1-a
    assert row.min()>-1e-10
    outside=[s for s in symbols if s not in chosen];assert abs(row[outside]).max()<1e-10
    if chosen:assert abs(row.sum()-a)<1e-9
    kkt=None
    if len(chosen)>1 and a>0:
        cs=[]
        for lag,mult in [(1,12),(3,4),(6,2),(12,1)]:
            start=m.index[-lag-1].end_time.normalize(); rr=rets.loc[(rets.index>start)&(rets.index<dt),chosen]
            cs.append(mult*rr.corr().to_numpy())
            if lag==1:sd=rr.std().to_numpy()
        cov=sum(cs)/19*np.outer(sd,sd);cov/=max(np.diag(cov).max(),1e-12)
        x=row[chosen].to_numpy()/a;g=2*cov@x;active=x>1e-7;lam=g[active].mean()
        kkt=float(max(np.max(abs(g[active]-lam)),max(0,float(lam-g[~active].min())) if (~active).any() else 0))
        assert kkt<1e-5,(dt,kkt)
    c4checks.append({'date':str(dt.date()),'risk_fraction':a,'positive_top_assets':chosen,'kkt_stationarity_residual':kkt})
out['C4_semantics']={'monthly_checks':len(c4checks),'failures':0,'max_normalized_kkt_residual':max(x['kkt_stationarity_residual'] or 0 for x in c4checks),'risk_fraction_month_counts':{str(a):sum(x['risk_fraction']==a for x in c4checks) for a in [0.,.5,1.]}}

manifest=json.loads((P/'snapshot-manifest.json').read_text());changes=[]
for r in manifest['files']:
    f=Path(r['path']);now=hashlib.sha256(f.read_bytes()).hexdigest() if f.exists() else None
    if now!=r['sha256']:changes.append({'path':str(f),'snapshot_sha256':r['sha256'],'current_sha256':now})
out['input_stability']={'initial_snapshot_utc':manifest['snapshot_utc'],'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checked_file_count':len(manifest['files']),'changed_files':changes}
(P/'audit-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False))
print(json.dumps({'stats':{v:{k:d[k] for k in ['cagr','mdd','annual_vol','sharpe_rf0','max_abs_equity_replay_error','cost_cagr']} for v,d in out['variants'].items()},'controls':{v:{k:d[k] for k in ['cagr','mdd','annual_vol','sharpe_rf0']} for v,d in out['controls'].items()},'unit_scale':{v:{k:d[k] for k in ['months_changed','months_checked']} for v,d in unit_changes.items()},'jan':jan,'C4_semantics':out['C4_semantics'],'input_stability':out['input_stability']},ensure_ascii=False,indent=2))
