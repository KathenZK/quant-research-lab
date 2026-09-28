"""D6 quote/settlement position diagnostics, never complete USD account returns."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from public100_r2_inputs import ROOT,F,ART,sha,payload,raw_files,basic_metric

OUT=ART/'boros';OUT.mkdir(exist_ok=True)
CONTRACT=F/'specs/continuation-boros-contract-20260909.md'

def load():
    m=json.loads((ART/'boros-historical-manifest.json').read_text());meta=json.loads((ART/'boros-metadata-docs.json').read_text())['records'];data={}
    for i in range(3):
        p=payload(meta[i]);o=json.loads(p.read_text());market=f'{o["marketId"]}-{o["imData"]["symbol"]}';frames={}
        for kind in ['market-data','settlement']:
            files=[]
            for r in m['records']:
                if r['request']['path'].startswith(kind+'/'+market+'/'):payload(r['payload']);files.extend(r['files'])
            frames[kind]=raw_files(files)
        data[market]=(o,frames)
    return data

def pnl(direction,fixed,floating,exit_apr,hours,remaining_years):
    return direction*(floating-fixed)*hours/8760+direction*(exit_apr-fixed)*remaining_years

def run(meta,frames,multiple):
    coin=meta['metadata']['assetSymbol'];threshold={'HYPE':2.5,'BTC':2.2,'ETH':1.8}[coin];maturity=pd.Timestamp(meta['imData']['maturity'],unit='s',tz='UTC');a=pd.Timestamp('2025-12-01',tz='UTC');end=pd.Timestamp('2025-12-25T23:00Z')
    quotes=frames['market-data'].loc[a:end];settles=frames['settlement'];assert len(quotes)==600 and quotes.index.equals(pd.date_range(a,end,freq='h').as_unit('ns'))
    assert np.isfinite(quotes[['bestBid','bestAsk','markApr']]).all().all() and (quotes.bestBid<=quotes.bestAsk+1e-12).all()
    swap=float(meta['config']['takerFee'])/1e18*multiple;settlefee=float(meta['extConfig']['settleFeeRate'])/1e18*multiple;assert swap>0 and settlefee>0
    balance=1.;position=None;orders=[];payments=[];curve=[];fees=0.;spreadpnl=0.;mtmrealized=0.;skip=0;signal_count=0
    for t,row in quotes.iterrows():
        if position:
            previous=t-pd.Timedelta(hours=1);recent=settles.loc[(settles.index>previous)&(settles.index<=t)]
            assert len(recent)==1,('incomplete or multiple settlement updates',t,len(recent))
            for st,event in recent.iterrows():
                assert st>position['entry'];floating=float(event.settlementApr);cash=position['direction']*(floating-position['fixed'])/8760;fee=settlefee/8760;balance+=cash-fee;fees+=fee;spreadpnl+=cash;payments.append({'ts':str(st),'cash_flow':cash,'fee':fee,'floatingApr':floating})
            if t-position['entry']==pd.Timedelta(hours=168):
                exit_apr=row.bestBid if position['direction']==1 else row.bestAsk;remaining=(maturity-t).total_seconds()/(365*86400);profit=position['direction']*(exit_apr-position['fixed'])*remaining;fee=swap*remaining;balance+=profit-fee;fees+=fee;mtmrealized+=profit
                orders.append({'entry_time':str(position['entry']),'exit_time':str(t),'direction':position['direction'],'fixed_entry_apr':position['fixed'],'exit_apr':exit_apr,'hold_hours':168,'closing_mtm_pnl':profit,'closing_fee':fee});position=None
        if position is None:
            hist=settles.loc[settles.index<t].tail(169);assert len(hist)==169
            assert (hist.settlementApr.abs()<=2).all(),'source clipping would remove hours'
            hours=hist.index.floor('h');assert len(hours.unique())==169 and (hours[1:]-hours[:-1]==pd.Timedelta(hours=1)).all()
            values=hist.settlementApr.to_numpy();sd=values[:-1].std(ddof=0) or .01;z=(values[-1]-values[:-1].mean())/sd;direction=-1 if z>threshold else (1 if z<-threshold else 0)
            if direction:
                signal_count+=1
                if t+pd.Timedelta(hours=168)>end:skip+=1
                else:
                    fixed=row.bestAsk if direction==1 else row.bestBid;fee=swap*(maturity-t).total_seconds()/(365*86400);balance-=fee;fees+=fee;position={'entry':t,'direction':direction,'fixed':fixed,'entry_fee':fee,'z':z,'last_signal_publication':str(hist.index[-1])}
        value=balance
        if position:value+=position['direction']*(row.markApr-position['fixed'])*(maturity-t).total_seconds()/(365*86400)
        curve.append((t,value));assert value>0
    assert position is None;assert abs(balance-(1+spreadpnl+mtmrealized-fees))<1e-12
    eq=pd.Series([1]+[e for t,e in curve],index=pd.DatetimeIndex([a-pd.Timedelta(seconds=1)]+[t for t,e in curve]),name='collateral_units')
    return eq,orders,payments,{'settlement_pnl':spreadpnl,'closing_mtm_pnl':mtmrealized,'modeled_fees':fees,'accounting_difference':balance-(1+spreadpnl+mtmrealized-fees),'signals_with_no_full_tail':skip,'eligible_flat_signals':signal_count}

def main():
    rows=[]
    for market,(meta,frames) in load().items():
      for multiple in [1,2]:
        eq,orders,payments,extra=run(meta,frames,multiple);name=f'D6-{meta["metadata"]["assetSymbol"]}-cost{multiple}'
        eq.to_csv(OUT/f'{name}-collateral-curve.csv');pd.DataFrame(orders).to_csv(OUT/f'{name}-trades.csv',index=False);pd.DataFrame(payments).to_csv(OUT/f'{name}-settlements.csv',index=False)
        row={'id':'D6','variant':'D6_ACTUAL_QUOTES_POSITION_DIAGNOSTIC','market':market,'coin':meta['metadata']['assetSymbol'],'fee_multiple':multiple,'start':str(eq.index[0]),'end':str(eq.index[-1]),**basic_metric(eq,False),'round_trips':len(orders),'status':'PARTIAL_POSITION_DIAGNOSTIC_NOT_ACCOUNT_BACKTEST','return_unit':'native collateral, excludes collateral USD moves, gas, entrance fees, depth and historical margin changes',**extra};rows.append(row);print(name,row['total_return'],row['mdd'],len(orders),flush=True)
    (OUT/'results.json').write_text(json.dumps({'results':rows,'contract_sha256':sha(CONTRACT),'script_sha256':sha(Path(__file__))},indent=2,allow_nan=False)+'\n')

if __name__=='__main__':main()
