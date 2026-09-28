"""Recovered B5 source rules, two predeclared schedule variants, raw diagnostics."""
from pathlib import Path
import hashlib, importlib.util, json
import numpy as np
import pandas as pd
from backtest_equity_diagnostic import load, simulate, metric
import backtest_equity_diagnostic as equity_engine

F=Path(__file__).resolve().parents[1]
OUT=F/'artifacts/continuation-r2/b5';OUT.mkdir(parents=True,exist_ok=True)
CONTRACT=F/'specs/continuation-b5-contract-20260909.md'
RISK=['SPY','VGK','EWJ','EEM','VNQ','RWX','TLT','DBC','GLD','IEF']
SYMS=RISK+['VWO','BND']
src=F/'artifacts/sources/recovered-b5-original/OptimizerModules/optimizer.py'
spec=importlib.util.spec_from_file_location('b5_original_optimizer',src)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
original_minimize=mod.minimize
def checked_minimize(*args,**kwargs):
    result=original_minimize(*args,**kwargs)
    if not result.success:raise ValueError(('original optimizer did not converge',result.message))
    return result
mod.minimize=checked_minimize

def weights(cl, every, start='2011-01-03'):
    n=len(cl);w=np.zeros(cl.shape);reb=np.zeros(n,bool);count=0;last=np.zeros(len(SYMS));records=[]
    for i,date in enumerate(cl.index):
        if date<pd.Timestamp(start):continue
        count+=1
        if count<every:
            w[i]=last;continue
        count=0;h=cl.iloc[i-253:i]
        assert len(h)==253 and h.index.max()<date
        returns=h.pct_change(fill_method=None).dropna()
        mom=sum(k*((returns.tail(lag)+1).prod()-1) for lag,k in [(21,12),(63,4),(126,2),(252,1)])
        chosen=mom[RISK][mom[RISK]>0].sort_values(ascending=False,kind='stable').index[:5].tolist()
        aggressive=float((mom[['VWO','BND']]>0).mean())
        active=chosen.copy()
        if aggressive==0:active=['IEF'] if mom.IEF>0 else []
        elif aggressive<1 and mom.IEF>0 and 'IEF' not in active:active.append('IEF')
        target={}
        if active:
            optimized=active.copy()
            if len(optimized)>5:optimized.remove('IEF')
            logs=np.log1p(returns[optimized]);corr=sum(k*logs.tail(lag).corr() for lag,k in [(21,12),(63,4),(126,2),(252,1)])/19
            std=logs.tail(21).std();cov=corr*np.outer(std,std)
            optimizer=mod.CustomPortfolioOptimizer(minWeight=.001,maxWeight=1,objFunction='std')
            opt=np.asarray(optimizer.Optimize(logs,cov))
            assert np.isfinite(opt).all() and abs(opt.sum()-1)<1e-7 and opt.min()>=.001-1e-7 and opt.max()<=1+1e-7
            target=dict(zip(optimized,opt*aggressive))
            if 'IEF' in active and aggressive<1:target['IEF']=target.get('IEF',0)+1-aggressive
        last=np.array([target.get(s,0.) for s in SYMS]);assert last.min()>=-1e-9 and last.sum()<=1+1e-7
        w[i]=last;reb[i]=True
        records.append({'trade_date':str(date.date()),'last_input_date':str(h.index[-1].date()),'aggressive':aggressive,'weights':target})
    return w,reb,records

def main():
    equity_engine.OUT=OUT
    data=load();cl=pd.DataFrame({s:data[s].adjclose for s in SYMS});op=pd.DataFrame({s:data[s].adjopen for s in SYMS});mask=cl.index>=pd.Timestamp('2011-01-03');results=[]
    for variant,every in [('B5_CODE_COUNTER22',22),('B5_TEXT_EVERY21',21)]:
        w,reb,records=weights(cl,every);(OUT/f'{variant}-decisions.json').write_text(json.dumps(records,indent=2))
        np.savez_compressed(OUT/f'{variant}-targets.npz',weights=w[mask],rebalances=reb[mask],symbols=np.array(SYMS),dates=cl.index[mask].values)
        for bps in [5,10,20]:
            eq,orders,turns=simulate(op.loc[mask],cl.loc[mask],w[mask],reb[mask],bps/10000)
            eq.to_csv(OUT/f'{variant}-{bps}bps-equity.csv');od=pd.DataFrame(orders);od.to_csv(OUT/f'{variant}-{bps}bps-orders.csv',index=False)
            independent=-od.signed_notional.sum()-od.fee.sum();assert abs(independent-(eq.iloc[-1]-1))<1e-7
            r={'id':'B5','variant':variant,'cost_bps':bps,'start':'2011-01-03','end':'2026-08-31',**metric(eq),'order_count':len(orders),'rebalance_count':len(records),'turnover':sum(turns),'accounting_difference':float(independent-(eq.iloc[-1]-1)),'status':'EXPLORE_UNTRUSTED','source_identity':'recovered original forum model; daily-account translation, predeclared start phase'}
            rets=eq.pct_change().dropna();r['yearly']={str(y):float((1+g).prod()-1) for y,g in rets.groupby(rets.index.year)}
            results.append(r);print(variant,bps,r['total_return'],r['cagr'],r['mdd'],flush=True)
    out={'results':results,'contract_sha256':hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'original_optimizer_sha256':hashlib.sha256(src.read_bytes()).hexdigest()}
    (OUT/'results.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')

if __name__=='__main__':main()
