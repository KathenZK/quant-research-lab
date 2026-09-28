"""D1/D2/D5 with full account arithmetic and governed lake inputs."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from strategy_lab.data.research_bundle import require_research_startup
from strategy_lab.data.fs import atomic_write_path
from public100_r2_inputs import ROOT,F,ART,sha,payload,basic_metric

OUT=ART/'funding';OUT.mkdir(exist_ok=True)
REQUEST=F/'specs/continuation-perp-net-request-20260909.json'
CONTRACT=F/'specs/continuation-perp-contract-20260909.md'
VARIANTS=['D1_CODE_SPARSE','D1_TEXT_HYSTERESIS','D2_DEFAULT10_001','D2_EXAMPLE20_0015','D5_BASE90_15_HOLD8']

def load_inputs():
    request=json.loads(REQUEST.read_text());print('Checking pinned lake inputs and funding coverage',flush=True)
    inputs=require_research_startup(request,project_root=ROOT)
    assert inputs.report['funding_window_verified'] and inputs.report['price_inputs_verified']
    (OUT/'startup-report.json').write_text(json.dumps(inputs.report,indent=2,default=str))
    receipts=json.loads((ART/'earlier-funding-mark-source.json').read_text());marks={};sourcefiles=[]
    previous_manifest=OUT/'mark-price-partitions.json'
    previous_files={r['path']:r for r in json.loads(previous_manifest.read_text())} if previous_manifest.exists() else {}
    for rec in receipts['records']:
        rows=[]
        for r in rec['receipts']:
            p=payload(r);rows.extend([{**x,'raw_payload_sha256':r['sha256']} for x in json.loads(p.read_text())])
        d=pd.DataFrame(rows);d['ts']=pd.to_datetime(d.fundingTime,unit='ms',utc=True);d['markPrice']=pd.to_numeric(d.markPrice,errors='coerce');d['fundingRate']=pd.to_numeric(d.fundingRate)
        d=d[d.ts.between(pd.Timestamp(request['start']),pd.Timestamp(request['end']))].copy()
        assert not d.ts.duplicated().any() and np.isfinite(d.markPrice).all() and (d.markPrice>0).all()
        for day,g in d.groupby(d.ts.dt.strftime('%Y-%m-%d')):
            p=ROOT/f'data/raw/funding/exchange=binance/market_type=perp/source=binance_funding_api_earlier/date={day}/symbol={rec["symbol"]}__public100_r2_20260909.parquet'
            g=g.assign(exchange='binance',market_type='perp',source='binance_funding_api',source_dataset_id='binance_funding_api.public100_r2_20260909',acceptance_status='raw_unaccepted')
            if not p.exists():atomic_write_path(p,lambda q,g=g:g.to_parquet(q,index=False))
            else:assert sha(p)==previous_files[str(p.relative_to(ROOT))]['sha256'], 'Previously captured mark partition changed'
            sourcefiles.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'rows':len(g)})
        marks[rec['symbol']]=d.set_index('ts')
    (OUT/'mark-price-partitions.json').write_text(json.dumps(sourcefiles,indent=2))
    result={};audits=[]
    for symbol,bars in inputs.prices.items():
        assert bars.research_window_valid.all() and bars.eligible.all();fund=inputs.funding[symbol].copy();native=symbol.replace('/','').split(':')[0];d=marks[native]
        matched=fund.merge(d,left_on='ts',right_index=True,how='left',validate='one_to_one')
        assert matched.markPrice.notna().all() and np.isclose(matched.funding_rate,matched.fundingRate,atol=1e-12,rtol=0).all()
        price=bars.set_index('ts').sort_index();price.index=price.index.as_unit('ns');matched=matched.set_index('ts').sort_index();matched.index=matched.index.as_unit('ns')
        audits.append({'symbol':symbol,'bars':len(price),'funding_events':len(matched),'matched_marks':int(matched.markPrice.notna().sum()),'max_rate_difference':float(abs(matched.funding_rate-matched.fundingRate).max()),'source':'existing governed price/funding frames; supplementary API marks only'})
        result[symbol]=(price,matched)
    (OUT/'input-audit.json').write_text(json.dumps(audits,indent=2));print('Inputs verified',audits,flush=True);return result

def signals(fund,variant):
    r=fund.funding_rate
    if variant.startswith('D2'):
        n,th=(10,.01) if 'DEFAULT' in variant else (20,.015);mom=r.rolling(n).mean();s=pd.Series(np.where(mom>th,1,np.where(mom<-th,-1,0)),index=r.index)
        return s,{'max_absolute_mean_rate':float(mom.abs().max()),'threshold_fraction':th,'nonzero_signals':int((s!=0).sum())}
    n=90 if variant.startswith('D5') else 30;th=1.5 if n==90 else 2.;z=(r-r.rolling(n).mean())/r.rolling(n).std(ddof=1).replace(0,np.nan)
    raw=pd.Series(np.where(z>th,-1,np.where(z<-th,1,0)),index=r.index);s=raw.copy()
    if 'HYSTERESIS' in variant:
        state=0
        for t,v in z.items():
            if abs(v)<.5:state=0
            elif v>2:state=-1
            elif v<-2:state=1
            s.loc[t]=state
    return s,{'nonzero_signals':int((raw!=0).sum()),'z_window':n,'threshold_z':th}

def simulate(bars,fund,s,variant,cost,start='2023-12-01T00:00:00Z'):
    start=pd.Timestamp(start);end=bars.index[-1]+pd.Timedelta(hours=1);b=bars.loc[bars.index>=start];execution={t.floor('h')+pd.Timedelta(hours=1):(int(v),t) for t,v in s.items() if t.floor('h')+pd.Timedelta(hours=1)>=start}
    events={t.floor('h'):(t,float(r.funding_rate),float(r.markPrice)) for t,r in fund.iterrows() if start<=t<=end};assert len(events)==len(fund[(fund.index>=start)&(fund.index<=end)])
    q=0.;eq=1.;previous=None;expire=None;points=[(start-pd.Timedelta(nanoseconds=1),1.)];orders=[];payments=[];pricepnl=0.;fundpnl=0.;fees=0.;worst_ratio=1.;tail_skipped=0
    for t,r in b.iterrows():
        if previous is not None:
            move=q*(r.open-previous);eq+=move;pricepnl+=move
        if t in events:
            event,rate,mark=events[t];assert t not in execution, 'order and funding within same hour need exact sequencing'
            amount=-q*mark*rate;eq+=amount;fundpnl+=amount
            if q:payments.append({'ts':str(event),'quantity':q,'markPrice':mark,'funding_rate':rate,'cash_flow':amount})
        target=None;source_time=None
        if variant.startswith('BENCHMARK') and t==b.index[0]:target=1
        elif variant.startswith('D5'):
            if expire is not None and t>=expire:target=0
            if t in execution:
                value,source_time=execution[t]
                if (q==0 or target==0) and value:
                    if t+pd.Timedelta(hours=8)<=end:target=value
                    else:tail_skipped+=1
        elif t in execution:target,source_time=execution[t]
        points.append((t,eq))
        if target is not None and (np.sign(q)!=target or (variant.startswith('D5') and expire is not None and t>=expire)):
            if q:
                fee=abs(q*r.open)*cost;eq-=fee;fees+=fee;orders.append({'ts':str(t),'quantity':-q,'price':float(r.open),'fee':fee,'reason':'close'});q=0.;expire=None
            if target:
                assert source_time is None or source_time<t
                q=target*eq/(1+cost)/r.open;fee=abs(q*r.open)*cost;eq-=fee;fees+=fee;orders.append({'ts':str(t),'last_signal_ts':str(source_time),'quantity':q,'price':float(r.open),'fee':fee,'reason':'entry'})
                if variant.startswith('D5'):expire=t+pd.Timedelta(hours=8)
            points.append((t+pd.Timedelta(nanoseconds=1),eq))
        adverse=r.low if q>=0 else r.high;worst=eq+q*(adverse-r.open);ratio=worst/max(abs(q*adverse),1e-15);worst_ratio=min(worst_ratio,ratio);assert worst>0 and (q==0 or ratio>.05),'insolvency or margin ambiguity; no net result'
        move=q*(r.close-r.open);eq+=move;pricepnl+=move;previous=r.close;points.append((t+pd.Timedelta(hours=1)-pd.Timedelta(nanoseconds=1),eq))
    if end in events:
        event,rate,mark=events[end];amount=-q*mark*rate;eq+=amount;fundpnl+=amount
        if q:payments.append({'ts':str(event),'quantity':q,'markPrice':mark,'funding_rate':rate,'cash_flow':amount})
    if q:
        fee=abs(q*previous)*cost;eq-=fee;fees+=fee;orders.append({'ts':str(end),'quantity':-q,'price':float(previous),'fee':fee,'reason':'final_liquidation'});q=0
    points.append((end,eq));independent=-sum(o['quantity']*o['price']+o['fee'] for o in orders)+fundpnl
    assert abs((eq-1)-independent)<1e-8 and abs(eq-(1+pricepnl+fundpnl-fees))<1e-8
    curve=pd.Series([e for t,e in points],index=pd.DatetimeIndex([t for t,e in points]),name='equity')
    return curve,orders,payments,{'gross_price_pnl_fraction_initial':pricepnl,'funding_pnl_fraction_initial':fundpnl,'fees_fraction_initial':fees,'accounting_difference':eq-1-independent,'min_adverse_equity_notional_ratio':worst_ratio,'incomplete_tail_signals_not_opened':tail_skipped}

def main():
    data=load_inputs();results=[];curves={}
    for symbol,(bars,fund) in data.items():
      for variant in VARIANTS+['BENCHMARK_PERP_BUY_HOLD']:
        sig,stats=signals(fund,variant) if not variant.startswith('BENCHMARK') else (pd.Series(dtype=int),{})
        for bps in [4,6,10]:
            eq,orders,payments,extras=simulate(bars,fund,sig,variant,bps/10000);name=f'{variant}-{symbol.split("/")[0]}-{bps}bps'
            eq.to_csv(OUT/f'{name}-equity.csv');pd.DataFrame(orders).to_csv(OUT/f'{name}-orders.csv',index=False);pd.DataFrame(payments).to_csv(OUT/f'{name}-funding.csv',index=False)
            row={'id':variant.split('_')[0],'variant':variant,'symbol':symbol,'cost_bps':bps,'start':str(eq.index[0]),'end':str(eq.index[-1]),**basic_metric(eq),'order_count':len(orders),'status':'CORRECTED_ACCOUNT_DIAGNOSTIC','input_status':'NET_INPUT_WINDOW_VERIFIED',**stats,**extras}
            results.append(row);curves[(symbol,variant,bps)]=eq;print(name,row['total_return'],row['mdd'],flush=True)
    syms=list(data)
    for variant in VARIANTS+['BENCHMARK_PERP_BUY_HOLD']:
      for bps in [4,6,10]:
        # Event grids may differ only at order-cost instants; carry actual last marked equity.
        eq=pd.concat([curves[(s,variant,bps)] for s in syms],axis=1,sort=True).sort_index().ffill().mean(axis=1);eq.to_csv(OUT/f'{variant}-HALF_BTC_ETH-{bps}bps-equity.csv')
        results.append({'id':variant.split('_')[0],'variant':variant,'symbol':'HALF_BTC_ETH','cost_bps':bps,'start':str(eq.index[0]),'end':str(eq.index[-1]),**basic_metric(eq),'status':'CORRECTED_ACCOUNT_DIAGNOSTIC','allocation':'half of initial capital in each independent account, no transfers'})
    (OUT/'results.json').write_text(json.dumps({'results':results,'contract_sha256':sha(CONTRACT),'request_sha256':sha(REQUEST),'script_sha256':sha(Path(__file__))},indent=2,allow_nan=False)+'\n')

if __name__=='__main__':main()
