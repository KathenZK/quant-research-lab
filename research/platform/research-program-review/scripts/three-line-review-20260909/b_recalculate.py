from pathlib import Path
import json, hashlib, joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

F=Path('/Users/ZK/.codex/worktrees/5f41/quant-strategy-lab/research/asset-portfolios/1d-tpsa-long-account')
A=F/'artifacts';O=Path('/tmp/three-line-b-recalc-20260909');O.mkdir(exist_ok=True)
END=pd.Timestamp('2026-07-01',tz='UTC'); C=json.loads((F/'specs/frozen-config.json').read_text())
p=pd.read_parquet(A/'verified_price_frames.parquet');e=pd.read_parquet(A/'predictions.parquet')
prices={s:g.set_index('ts').sort_index() for s,g in p.groupby('symbol')}
model=joblib.load(A/'new_frozen_model.joblib')
pred=model['model'].predict_proba(pd.DataFrame(model['imputer'].transform(e[C['features']]),columns=C['features']))[:,1]
original=Path(C['source_events'])
checks={'source_event_sha_matches':hashlib.sha256(original.read_bytes()).hexdigest()==C['source_events_sha256'],'reloaded_prediction_max_diff':float(np.max(abs(pred-e.probability)))}
oldp=pd.read_parquet('/Users/ZK/OpenCode/quant-strategy-lab/research/asset-portfolios/1d-trend-prebreakout-state-atlas/artifacts/binance_1d_tpsa_p1_barrier_ml_predictions.parquet')
oldp=oldp[(oldp.ma_period==7)&(oldp.direction=='long')&(oldp.model=='LIGHTGBM')&(oldp.event_date.dt.year==2025)]
j=e.merge(oldp[['event_id','probability']],on='event_id',suffixes=('_new','_old'))
checks.update(original_2025_pairs=len(j),original_2025_probability_max_diff=float(abs(j.probability_new-j.probability_old).max()))

audits=[]
for met in json.loads((A/'variant_metrics.json').read_text()):
    name=met['variant']; od=pd.read_csv(A/name/'orders.csv');eq=pd.read_csv(A/name/'account_equity.csv')
    od['time']=pd.to_datetime(od.time,utc=True);eq['bar_open']=pd.to_datetime(eq.bar_open,utc=True)
    wallet=10000.;held={};err={'equity':0.,'wallet':0.,'reserved':0.,'free':0.,'fill':0.,'fee':0.};buf=[]
    fee=.001*(2 if name=='ML_double_cost' else 1);slip=.0004*(2 if name=='ML_double_cost' else 1)
    for q in eq.itertuples():
        d=q.bar_open
        for r in od[od.time.eq(d)].itertuples():
            ref=float(prices[r.symbol].loc[d,'open']); fill=ref*(1+slip if r.side=='BUY' else 1-slip)
            err['fill']=max(err['fill'],abs(fill-r.fill_price));cost=r.qty*fill*fee;err['fee']=max(err['fee'],abs(cost-r.fee_usd))
            if r.side=='BUY':
                assert r.symbol not in held
                held[r.symbol]={'qty':r.qty,'entry':fill,'reserved':r.qty*fill}
                wallet-=cost
            else:
                h=held.pop(r.symbol);assert abs(h['qty']-r.qty)<1e-7
                wallet+=r.qty*(fill-h['entry'])-cost
        if q.valuation_type!='TERMINAL_OPEN_LIQUIDATION':
            wallet-=sum(z['qty']*float(prices[s].loc[d,'close'])*met['assumed_annual_holding_charge']/365 for s,z in held.items())
        unreal=sum(z['qty']*(float(prices[s].loc[d,'close'])-z['entry']) for s,z in held.items())
        reserve=sum(z['reserved'] for z in held.values());value=wallet+unreal
        for key,calc,saved in [('equity',value,q.equity_ex_actual_funding),('wallet',wallet,q.wallet_balance),('reserved',reserve,q.reserved_collateral),('free',wallet-reserve,q.free_cash)]:err[key]=max(err[key],abs(calc-saved))
        buf.append(value)
    vals=np.r_[10000.,buf];dd=float((vals/np.maximum.accumulate(vals)-1).min())
    audits.append({'variant':name,'rows':len(eq),'errors_usd':err,'final_equity':float(vals[-1]),'drawdown':dd,'complete':met['account_complete'],'max_positions':int(eq.positions.max()),'position_count_distribution':eq.positions.value_counts().sort_index().to_dict()})

def shadow(ev):
    g=prices[ev.symbol];entry=ev.event_date+pd.Timedelta(days=1)
    row={'event_id':ev.event_id,'symbol':ev.symbol,'event_date':ev.event_date,'probability':ev.probability,'label':ev.barrier_success_20,'selected':ev.probability>=.4,'entry':entry,'status':'UNRESOLVED'}
    if entry>=END:row['status']='NO_ENTRY_BEFORE_END';return row
    if entry not in g.index or ev.event_date not in g.index:row['status']='ENTRY_MISSING';return row
    en=g.loc[entry];sg=g.loc[ev.event_date]
    valid=lambda r: bool(r.eligible) and bool(r.research_window_valid)
    if not valid(en) or not valid(sg) or en.research_segment_id!=sg.research_segment_id:row['status']='ENTRY_INVALID_SEGMENT';return row
    ent=float(en.open)*1.0004;segment=en.research_segment_id
    for age in range(1,21):
        d=entry+pd.Timedelta(days=age-1)
        if d not in g.index:row['status']='HOLD_MISSING';return row
        z=g.loc[d]
        if not valid(z) or z.research_segment_id!=segment:row['status']='HOLD_INVALID_SEGMENT';return row
        if d==END: exdate=d;reason='TERMINAL';break
        rr=(float(z.close)-ent)/ev.atr20_pre
        if rr>=2 or rr<=-1 or age==20:
            exdate=d+pd.Timedelta(days=1);reason='TP_CLOSE' if rr>=2 else ('SL_CLOSE' if rr<=-1 else 'TIME_20_CLOSES');break
    if exdate not in g.index:row['status']='EXIT_MISSING';return row
    ex=g.loc[exdate]
    if not valid(ex) or ex.research_segment_id!=segment:row['status']='EXIT_INVALID_SEGMENT';return row
    price=float(ex.open)*.9996
    row.update(status='RESOLVED',entry_price=ent,exit_price=price,exit_time=exdate,reason='TERMINAL' if exdate==END else reason,price_return=price/ent-1,price_fee_return=(price/ent-1)-.001-.001*price/ent,atr_fraction=ev.atr20_pre/ent,entry_gap=float(en.open)/ev.close-1)
    return row
sh=pd.DataFrame([shadow(ev) for ev in e.itertuples()]);sh.to_csv(O/'independent_event_shadow.csv',index=False)
summ=[]
for scope,g in [('all',sh),('p040_selected',sh[sh.selected]),('not_selected',sh[~sh.selected])]:
    lab=g[g.label.notna()];v=g[g.status.eq('RESOLVED')]
    summ.append({'scope':scope,'n':len(g),'status_counts':g.status.value_counts().to_dict(),'label_n':len(lab),'label_success':float(lab.label.mean()),'resolved_n':len(v),'mean_return':float(v.price_fee_return.mean()),'median_return':float(v.price_fee_return.median()),'win_rate':float(v.price_fee_return.gt(0).mean()),'auc_original_label':float(roc_auc_score(lab.label,lab.probability)),'probability_return_spearman':float(v[['probability','price_fee_return']].corr(method='spearman').iloc[0,1]),'auc_executed_positive_return':float(roc_auc_score(v.price_fee_return.gt(0),v.probability)),'exit_counts':v.reason.value_counts().to_dict()})
for name in ['ML_p040','ALL_EVENTS','HASH20_EVENTS']:
    tr=pd.read_csv(A/name/'trades.csv');tr['return']=tr.price_fee_pnl/tr.entry_notional
    jj=tr.merge(sh,on='event_id',suffixes=('_account','_shadow'))
    labs=jj[jj.label.notna()]
    summ.append({'scope':name+'_admitted','n':len(jj),'label_n':len(labs),'label_success':float(labs.label.mean()),'mean_return':float(tr['return'].mean()),'median_return':float(tr['return'].median()),'win_rate':float(tr['return'].gt(0).mean()),'shadow_return_max_error':float(abs(jj['return']-jj.price_fee_return).max()),'shadow_exit_reason_mismatches':int((jj.exit_reason!=jj.reason).sum()),'probability_return_spearman':float(tr[['probability','return']].corr(method='spearman').iloc[0,1]),'old_label_vs_account_exit':pd.crosstab(jj.label,jj.exit_reason).to_dict(),'reason_mean_return':tr.groupby('exit_reason')['return'].agg(['count','mean','median']).to_dict('index')})
    jj.to_csv(O/(name+'_admitted_join.csv'),index=False)
main=pd.read_csv(A/'ML_p040/trades.csv');joined=sh.merge(main[['event_id']],on='event_id')
sel=sh[sh.selected&sh.label.notna()].copy();ad=joined[joined.label.notna()].copy()
perdate=sel.groupby('event_date').label.agg(['size','mean']);counts=ad.groupby('event_date').size();matched=float((counts*perdate.loc[counts.index,'mean']).sum()/counts.sum())
monthly=[]
for month,g in sh[sh.selected].groupby(sh.event_date.dt.strftime('%Y-%m')):
    z=joined[joined.event_date.dt.strftime('%Y-%m').eq(month)]
    monthly.append({'month':month,'selected_events':len(g),'selected_success':float(g.label.mean()),'admitted_events':len(z),'admitted_success':float(z.label.mean()),'selected_shadow_mean_return':float(g.price_fee_return.mean()),'admitted_mean_return':float(z.price_fee_return.mean())})
pd.DataFrame(monthly).to_csv(O/'monthly_admission_diagnostic.csv',index=False)
admission={'selected_full_label_success':float(sel.label.mean()),'admitted_full_label_success':float(ad.label.mean()),'selected_success_weighted_by_actual_admitted_dates':matched,'admitted_signal_dates':len(counts),'selected_signal_dates':len(perdate),'interpretation':'Date weighting is attribution only, not an implementable account comparator. Remaining difference can reflect deterministic hash draw, same-asset constraints and path-dependent holdings; no causal attribution established.'}
out={'checks':checks,'independent_account_reconstruction':audits,'event_shadow_summaries':summ,'admission_attribution':admission,'limitations':'Post-result mechanism diagnostic only. Independent event returns overlap and are not portfolio returns or new OOS. Real funding, identity, executable lot filters remain unverified.'}
(O/'review_recalculation.json').write_text(json.dumps(out,indent=2,default=str));print(json.dumps(out,indent=2,default=str))
