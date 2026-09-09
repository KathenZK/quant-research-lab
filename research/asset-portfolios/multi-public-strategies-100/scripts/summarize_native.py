from pathlib import Path
import json,hashlib,zipfile,io
import numpy as np
import pandas as pd
F=Path(__file__).resolve().parents[1];ROOT=F.parents[2];OUT=F/'artifacts/freqtrade'
runs=json.loads((OUT/'run-manifest.json').read_text())['runs'];summ=[];audit=[]
for r in runs:
 assert r['returncode']==0
 zpath=F/r['files'][0];z=zipfile.ZipFile(zpath);p=next(k for k in z.namelist() if k.endswith('.json') and 'config'not in k);s=json.loads(z.read(p))['strategy'][r['strategy']]
 pnl=sum(t['profit_abs'] for t in s['trades']);difference=s['final_balance']-(s['starting_balance']+pnl)
 assert abs(difference)<1e-6
 maxerr=0.
 for t in s['trades']:
  calc=sum((1 if o['ft_order_side']=='sell' else -1)*o['safe_price']*o['amount']*(1-r['fee'] if o['ft_order_side']=='sell' else 1+r['fee']) for o in t['orders'])
  maxerr=max(maxerr,abs(calc-t['profit_abs']))
 assert maxerr<2e-5,maxerr
 walletkey=next(k for k in z.namelist() if k.endswith('_wallet.feather'));wallet=pd.read_feather(io.BytesIO(z.read(walletkey)));wallet.to_csv(OUT/f'{r["id"]}-{r["fee"]}-wallet.csv',index=False)
 if r==runs[0]:print('wallet',wallet.columns.tolist(),wallet.head(2).to_dict('records'))
 stats=s['wallet_stats'];audit.append({'id':r['id'],'fee':r['fee'],'capital_reconciliation_error':difference,'max_trade_fill_cashflow_error':maxerr,'result_zip_sha256':hashlib.sha256(zpath.read_bytes()).hexdigest()})
 summ.append({'id':r['id'],'strategy':r['strategy'],'fee':r['fee'],'status':'EXPLORE_UNTRUSTED','total_return':s['profit_total'],'cagr':s['cagr'],'realized_drawdown':s['max_drawdown_account'],'wallet_stats':stats,'trades':s['total_trades'],'winrate':s['winrate'],'profit_factor':s['profit_factor'],'final_balance':s['final_balance'],'last_trade':max(t['close_date'] for t in s['trades']),'start':s['backtest_start'],'end':s['backtest_end'],'yearly':s['periodic_breakdown'].get('year',[]),'result':r['files'][0]})
(OUT/'summary.json').write_text(json.dumps(summ,indent=2));(OUT/'independent-accounting-audit.json').write_text(json.dumps(audit,indent=2))
# Same dates and observed fixed universe: 48% invested / rest cash, and full deployment.
adapter=json.loads((F/'artifacts/freqtrade-adapter-manifest.json').read_text());prices={}
for x in adapter['files']:
 f=x['files'][0];p=ROOT/f['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256'];d=pd.read_feather(p);d=d[(d.date>=pd.Timestamp('2024-07-01',tz='UTC'))&(d.date<pd.Timestamp('2026-09-01',tz='UTC'))];prices[x['pair']]=pd.Series(np.r_[1.,d.close.to_numpy()/d.open.iloc[0]],index=pd.DatetimeIndex([d.date.iloc[0]-pd.Timedelta(minutes=15)]+list(d.date)))
panel=pd.DataFrame(prices);assert panel.notna().all().all();bench=[]
for allocation in [.48,.99]:
 for cost in [.001,.0015,.002]:
  eq=(1-allocation)+allocation/(1+cost)*panel.mean(axis=1);eq.iloc[0]=1.;eq.iloc[-1]-=allocation/(1+cost)*panel.iloc[-1].mean()*cost;eq.to_csv(OUT/f'benchmark-{allocation}-{cost}.csv');bench.append({'allocation':allocation,'fee':cost,'total_return':float(eq.iloc[-1]-1),'mdd':float((eq/eq.cummax()-1).min()),'model':'fixed equal-weight spot buyhold, fractional quantities; diagnostic comparison not historical lot-size proof'})
(OUT/'benchmarks.json').write_text(json.dumps(bench,indent=2));print('cashflow audit PASS',len(audit));print(bench)
