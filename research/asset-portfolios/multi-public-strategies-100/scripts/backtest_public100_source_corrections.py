"""Fixed source-identity/time corrections; never overwrite original results."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import backtest_equity_diagnostic as old
from public100_r2_inputs import F,ART,sha,raw_files,payload,calendar,validate

OUT=ART/'source-corrections';OUT.mkdir(exist_ok=True)
CONTRACT=F/'specs/continuation-source-corrections-contract-20260909.json'

def weights(cl,op,variant,start='2011-01-03'):
    w=np.zeros(cl.shape);reb=np.zeros(len(cl),bool);last=np.zeros(len(cl.columns));decisions=[]
    for i,date in enumerate(cl.index):
        if date<pd.Timestamp(start):continue
        first=i==0 or date.to_period('M')!=cl.index[i-1].to_period('M')
        if first:
            h=cl.iloc[:i];target=None;detail={}
            if variant=='C1_GEM_SOURCE_IVV_VEU_BND':
                months=h.groupby(h.index.to_period('M')).last();assert len(months)>=13
                mom=months.iloc[-1]/months.iloc[-13]-1
                target=('IVV' if mom.IVV>=mom.VEU else 'VEU') if mom.IVV>mom.BIL else 'BND'
                detail={'momentum':mom.to_dict(),'last_input_date':str(h.index[-1].date())}
            elif date.month==1:target='SPY'
            elif date.month==2:
                jan=h[h.index.year==date.year];assert len(jan)>0
                if variant=='A36_JAN_FIRST_OPEN':base=op.loc[jan.index[0],'SPY'];base_date=jan.index[0]
                elif variant=='A36_PREVIOUS_DEC_CLOSE':
                    dec=h[h.index.year==date.year-1];base=dec.SPY.iloc[-1];base_date=dec.index[-1]
                else:raise ValueError(variant)
                change=float(jan.SPY.iloc[-1]/base-1);target='SPY' if change>0 else 'BIL'
                detail={'january_return':change,'base_date':str(base_date.date()),'base_price':float(base),'last_input_date':str(jan.index[-1].date())}
            if target is not None:
                last=np.array([float(s==target) for s in cl.columns]);reb[i]=True
                decisions.append({'trade_date':str(date.date()),'target':target,**detail})
        w[i]=last
    return w,reb,decisions

def main():
    c=json.loads(CONTRACT.read_text());old.OUT=OUT;data=old.load()
    m=json.loads((ART/'source-etfs-manifest.json').read_text());assert m['contract_sha256']==sha(CONTRACT);payload(m['source']);audit=[]
    for r in m['records']:
        payload(r['payload']);d=raw_files(r['files']);validate(d)
        assert d.adjclose.notna().all() and np.isfinite(d.adjclose).all() and (d.adjclose>0).all()
        d.index=d.index.tz_convert('America/New_York').normalize().tz_localize(None)
        expected=calendar(str(d.index.min().date()),str(d.index.max().date())).index
        assert d.index.equals(expected),(r['symbol'],'daily session mismatch')
        d['adjopen']=d.open*d.adjclose/d.close;data[r['symbol']]=d
        audit.append({'symbol':r['symbol'],'rows':len(d),'missing_sessions':0,'status':'RAW_BASIC_CHECK_PASS_NOT_ACCEPTED'})
    results=[]
    for variant in list(c['A36_variants'])+[c['C1_variant']]:
        symbols=['SPY','BIL'] if variant.startswith('A36') else ['IVV','VEU','BND','BIL']
        cl=pd.DataFrame({s:data[s].adjclose for s in symbols});op=pd.DataFrame({s:data[s].adjopen for s in symbols})
        assert cl.notna().all().all() and op.notna().all().all()
        w,reb,decisions=weights(cl,op,variant,c['window'][0]);mask=(cl.index>=c['window'][0])&(cl.index<=c['window'][1])
        np.savez_compressed(OUT/f'{variant}-targets.npz',weights=w[mask],rebalances=reb[mask],symbols=np.array(symbols),dates=cl.index[mask].values)
        (OUT/f'{variant}-decisions.json').write_text(json.dumps(decisions,indent=2)+'\n')
        for bps in c['cost_bps_per_side']:
            eq,orders,turns=old.simulate(op.loc[mask],cl.loc[mask],w[mask],reb[mask],bps/10000)
            eq.to_csv(OUT/f'{variant}-{bps}bps-equity.csv');od=pd.DataFrame(orders);od.to_csv(OUT/f'{variant}-{bps}bps-orders.csv',index=False)
            independent=-od.signed_notional.sum()-od.fee.sum();difference=float(independent-(eq.iloc[-1]-1));assert abs(difference)<1e-7
            r={'id':variant.split('_')[0],'variant':variant,'cost_bps':bps,'start':c['window'][0],'end':c['window'][1],**old.metric(eq),'order_count':len(orders),'accounting_difference':difference,'status':c['status']}
            ret=eq.pct_change().dropna();r['yearly']={str(y):float((1+g).prod()-1) for y,g in ret.groupby(ret.index.year)}
            results.append(r);print(variant,bps,r['total_return'],r['cagr'],r['mdd'],flush=True)
    (OUT/'supplement-data-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    sources=[CONTRACT,Path(__file__),Path(old.__file__),ART/'source-etfs-manifest.json',F/'artifacts/equity-raw-manifest.json',F/'artifacts/sources/extracted/A36.txt']
    out={'results':results,'contract_sha256':sha(CONTRACT),'script_sha256':sha(Path(__file__)),'sources':[{'path':str(p.relative_to(F)),'sha256':sha(p)} for p in sources]}
    (OUT/'results.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')

if __name__=='__main__':main()
