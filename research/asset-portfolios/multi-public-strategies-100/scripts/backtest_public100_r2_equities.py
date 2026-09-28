"""A2 / A55 / C10 frozen clock translations; exact raw inputs, separate artifacts."""
import json
import numpy as np
import pandas as pd
import backtest_equity_diagnostic as old
from public100_r2_inputs import F,ART,sha,yahoo,coinbase,validate,calendar,session,basic_metric

OUT=ART/'equities';OUT.mkdir(exist_ok=True)
CONTRACT=F/'specs/continuation-equity-clock-contract-20260909.md'

def save(variant,cost,points,orders,extras,annualize=True):
    eq=pd.Series([v for t,v in points],index=pd.DatetimeIndex([t for t,v in points]),name='equity')
    assert eq.index.is_monotonic_increasing and (eq>0).all()
    eq.to_csv(OUT/f'{variant}-{cost}bps-equity.csv');pd.DataFrame(orders).to_csv(OUT/f'{variant}-{cost}bps-orders.csv',index=False)
    r={'id':variant.split('_')[0],'variant':variant,'cost_bps':cost,'start':str(eq.index[0]),'end':str(eq.index[-1]),**basic_metric(eq,annualize),'order_count':len(orders),'status':'EXPLORE_UNTRUSTED',**extras}
    daily=eq.groupby(eq.index.normalize()).last();r['daily_mdd']=float((daily/daily.cummax().clip(lower=1)-1).min())
    prior=1.;r['yearly']={}
    for year,g in daily.groupby(daily.index.year):
        r['yearly'][str(year)]=float(g.iloc[-1]/prior-1);prior=float(g.iloc[-1])
    print(variant,cost,r['total_return'],r['cagr'],r['mdd'],flush=True);return r

def a2(daily):
    raw=yahoo('60m','SPY');cal=calendar('2026-02-03','2026-08-31');frames=[]
    for date,row in cal.iterrows():
        d=session(raw,row,60).copy();factor=daily['SPY'].loc[date,'adjclose']/daily['SPY'].loc[date,'close']
        d[['open','high','low','close']]*=factor;d['end']=[min(t+pd.Timedelta(hours=1),row.close) for t in d.index];d['date']=date;frames.append(d)
    bars=pd.concat(frames);d=daily['SPY'].copy();factor=d.adjclose/d.close
    thresholds={}
    for date,row in cal.iterrows():
        h=d[d.index<date].tail(4);a=h[['high','low','close']].mul(factor.loc[h.index],axis=0)
        width=max(a.high.max()-a.close.min(),a.close.max()-a.low.min());thresholds[date]=(width,float(a.close.iloc[-1]))
    results=[]
    for variant in ['A2_DAY_OPEN','A2_PREVIOUS_CLOSE']:
      for bps in [5,10,20]:
        cost=bps/10000;cash=1.;q=0.;pending=None;lasttime=bars.index[0];orders=[];points=[(lasttime-pd.Timedelta(seconds=1),1.)];fees=0.;borrow=0.;bases={}
        for t,r in bars.iterrows():
            carry=max(-q*r.open,0)*.03*(t-lasttime).total_seconds()/(365.25*86400);cash-=carry;borrow+=carry
            if pending is not None:
                target,input_time=pending;assert input_time<=t
                eq=cash+q*r.open;post=eq
                for _ in range(40):post=eq-cost*abs(target*post-q*r.open)
                delta=target*post-q*r.open;fee=cost*abs(delta);q=target*post/r.open;cash=post-q*r.open;fees+=fee
                if abs(delta)>1e-12:orders.append({'ts':str(t),'last_input_time':str(input_time),'signed_notional':float(delta),'price':r.open,'fee':fee})
            if r.date not in bases:bases[r.date]=r.open if variant.endswith('DAY_OPEN') else thresholds[r.date][1]
            half=thresholds[r.date][0]*.5;base=bases[r.date];pending=(.8,r.end) if r.close>=base+half else ((-.8,r.end) if r.close<base-half else None)
            carry=max(-q*r.close,0)*.03*(r.end-t).total_seconds()/(365.25*86400);cash-=carry;borrow+=carry
            points.append((r.end,cash+q*r.close));lasttime=r.end
        p=float(bars.close.iloc[-1]);delta=-q*p;fee=cost*abs(delta);cash-=delta+fee;fees+=fee
        if q:orders.append({'ts':str(lasttime),'signed_notional':delta,'price':p,'fee':fee,'reason':'final_liquidation'})
        points[-1]=(lasttime,cash);independent=1-sum(x['signed_notional']+x['fee'] for x in orders)-borrow;assert abs(cash-independent)<1e-8
        results.append(save(variant,bps,points,orders,{'sessions':len(cal),'bars':len(bars),'fees_fraction_initial':fees,'borrow_fraction_initial':borrow,'accounting_difference':cash-independent,'sample_limit':'2026 complete-tail hourly sample; not long-history rank'}))
    return results

def a55():
    syms=['SPY','IWM','IYR'];five={s:yahoo('5m',s) for s in syms};two={s:yahoo('2m',s) for s in syms};cal=calendar('2026-07-15','2026-08-31');days=[];prev=None
    for date,row in cal.iterrows():
        step=5 if date<pd.Timestamp('2026-07-27') else 2;source=five if step==5 else two
        blocks={s:session(source[s],row,step) for s in syms};cl=np.array([blocks[s].close.iloc[-1] for s in syms])
        if prev is not None:
            morning=np.array([blocks[s].loc[row.open+pd.Timedelta(minutes=30-step),'close'] for s in syms]);sign=np.sign(morning/prev-1);n=np.count_nonzero(sign);w=sign/n if n else sign
            entry=row.close-pd.Timedelta(minutes=30);op=np.array([blocks[s].loc[entry,'open'] for s in syms]);marks=[]
            for end in pd.date_range(entry+pd.Timedelta(minutes=10),row.close,freq='10min'):
                marks.append((end,np.array([blocks[s].loc[end-pd.Timedelta(minutes=step),'close'] for s in syms])))
            days.append((date,entry,op,marks,w))
        prev=cl
    out=[]
    for bps in [5,10,20]:
        cost=bps/10000;cash=1.;points=[(days[0][1].normalize(),1.)];orders=[];profits=0.;fees=0.;borrows=0.;wins=0
        for date,entry,op,marks,w in days:
            initial=cash;post=cash/(1+cost*abs(w).sum());q=w*post/op;notional=q*op;fee=cost*abs(notional).sum();cash-=notional.sum()+fee;fees+=fee
            for j,s in enumerate(syms):
                if q[j]:orders.append({'ts':str(entry),'symbol':s,'signed_notional':float(notional[j]),'price':float(op[j]),'fee':float(cost*abs(notional[j]))})
            points.append((entry,cash+float(q@op)))
            last=entry
            for end,prices in marks:
                borrow=float(np.maximum(-q*prices,0).sum())*.03*(end-last).total_seconds()/(365.25*86400);cash-=borrow;borrows+=borrow;points.append((end,cash+float(q@prices)));last=end
            profits+=float(q@(prices-op));delta=-q*prices;fee=cost*abs(delta).sum();cash-=delta.sum()+fee;fees+=fee
            for j,s in enumerate(syms):
                if q[j]:orders.append({'ts':str(end),'symbol':s,'signed_notional':float(delta[j]),'price':float(prices[j]),'fee':float(cost*abs(delta[j]))})
            points[-1]=(end,cash);wins+=cash>initial
        assert abs(cash-(1+profits-fees-borrows))<1e-10
        out.append(save('A55_LAST30_MINUTES',bps,points,orders,{'sessions':len(days),'winning_days':wins,'gross_price_pnl_fraction_initial':profits,'fees_fraction_initial':fees,'borrow_fraction_initial':borrows,'accounting_difference':cash-(1+profits-fees-borrows),'sample_limit':'33 sessions only; annualized return deliberately omitted'},False))
    return out

def c10(daily):
    spot=coinbase(86400);intra=coinbase(900);validate(spot);assert spot.index.equals(pd.date_range('2017-01-01','2026-09-01',tz='UTC',freq='D',inclusive='left').as_unit('ns'))
    cal=calendar('2021-01-04','2026-08-31');spy=daily['SPY'];ma=spy.adjclose.rolling(200).mean();btcma=spot.close.rolling(50).mean();scheduled={}
    for date,row in cal.iterrows():
        bp=intra.loc[row.open];validate(bp.to_frame().T[['open','high','low','close','volume']].astype(float))
        sh=spy[spy.index<date].iloc[-1];shdate=spy.index[spy.index<date][-1];bdate=row.open.normalize()-pd.Timedelta(days=1)
        assert bdate+pd.Timedelta(days=1)<=row.open and shdate<date
        prices=np.array([spy.loc[date,'adjopen'],bp.open],float);signal=np.array([sh.adjclose>ma.loc[shdate],spot.loc[bdate,'close']>btcma.loc[bdate]])
        scheduled[row.open]=(prices,signal,shdate,bdate)
    end=cal.iloc[-1].close;closeprices=np.array([spy.loc[cal.index[-1],'adjclose'],intra.loc[end-pd.Timedelta(minutes=15),'close']],float)
    events=set(scheduled)|set(pd.date_range('2021-01-05','2026-08-31',freq='D',tz='UTC'))|{end};out=[]
    for variant in ['C10_SMA200_50','BENCHMARK_C10_HOLD60_30','BENCHMARK_C10_SPY_HOLD']:
      for bps in [5,10,20]:
        costs=np.array([bps,2*bps])/10000;cash=1.;q=np.zeros(2);orders=[];points=[(pd.Timestamp('2021-01-04',tz='UTC'),1.)];caps=0;fees=0.
        for t in sorted(events):
            if t in scheduled:
                p,signal,shdate,bdate=scheduled[t];eq=cash+float(q@p)
                if variant.startswith('BENCHMARK'):signal=np.array([True,'HOLD60_30' in variant])
                for j in range(2):
                    if q[j] and not signal[j]:
                        delta=-q[j]*p[j];fee=abs(delta)*costs[j];cash-=delta+fee;fees+=fee;q[j]=0.;orders.append({'ts':str(t),'symbol':['SPY','BTC-USD'][j],'signed_notional':float(delta),'price':float(p[j]),'fee':float(fee),'reason':'signal_exit'})
                desired=np.where((q==0)&signal,np.array([1.,0.]) if variant.endswith('SPY_HOLD') else np.array([.6,.3]),0)*eq
                needed=float((desired*(1+costs)).sum())
                if needed>cash+1e-12:desired*=cash/needed;caps+=1
                for j in range(2):
                    if desired[j]>1e-12:
                        delta=desired[j];fee=delta*costs[j];cash-=delta+fee;fees+=fee;q[j]+=delta/p[j];orders.append({'ts':str(t),'symbol':['SPY','BTC-USD'][j],'signed_notional':float(delta),'price':float(p[j]),'fee':float(fee),'spy_signal_date':str(shdate),'btc_signal_day':str(bdate),'reason':'new_entry'})
                assert cash>=-1e-10
            if t.hour==0:
                sh=spy[spy.index<t.tz_localize(None)].iloc[-1];p=np.array([sh.adjclose,spot.loc[t-pd.Timedelta(days=1),'close']]);points.append((t,cash+float(q@p)))
            if t==end:
                delta=-q*closeprices
                for j in range(2):
                    fee=abs(delta[j])*costs[j];cash-=delta[j]+fee;fees+=fee
                    if q[j]:orders.append({'ts':str(t),'symbol':['SPY','BTC-USD'][j],'signed_notional':float(delta[j]),'price':float(closeprices[j]),'fee':float(fee),'reason':'final_liquidation'})
                q[:]=0;points.append((t,cash))
        independent=1-sum(x['signed_notional']+x['fee'] for x in orders);assert abs(cash-independent)<1e-9
        out.append(save(variant,bps,points,orders,{'accounting_difference':cash-independent,'fees_fraction_initial':fees,'cash_limited_buy_dates':caps,'btc_cost_bps':bps*2,'drawdown_sampling':'UTC daily and final liquidation; not continuous intraday','clock_translation':'US regular session open; previous completed daily signals'}))
    return out

def main():
    old.OUT=OUT;daily=old.load();rows=a2(daily)+a55()+c10(daily)
    (OUT/'results.json').write_text(json.dumps({'results':rows,'contract_sha256':sha(CONTRACT),'script_sha256':sha(__import__('pathlib').Path(__file__))},indent=2,allow_nan=False,default=lambda x:x.item())+'\n')

if __name__=='__main__':main()
