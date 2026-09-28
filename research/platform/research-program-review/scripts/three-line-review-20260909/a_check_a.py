import json, hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import exchange_calendars as xc
from pandas.tseries.holiday import USFederalHolidayCalendar
R=Path('/Users/ZK/.codex/worktrees/5f41/quant-strategy-lab/research/asset-portfolios/1d-small-account-slow-trend')
A=R/'artifacts'; O=Path('/tmp/three-line-a-review-20260909')
cfg=json.loads((R/'specs/p0-contract.json').read_text()); syms=cfg['symbols']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((A/'raw-manifest.json').read_text())
assert sha(R/'specs/p0-contract.json')==manifest['contract_sha256']
assert sha(R/'specs/data-admissibility.json')==manifest['admissibility_sha256']
for s in manifest['sources']: assert sha(R/s['path'])==s['sha256']
hashes=json.loads((A/'hashes.json').read_text());bad_hashes=[p for p,h in hashes.items() if not (R/p).exists() or sha(R/p)!=h]
cal=xc.get_calendar('XNYS',start='2014-01-01',end='2027-01-15'); ix=pd.DatetimeIndex(cal.sessions).tz_localize(None)
ix=ix[(ix>='2015-12-01')&(ix<='2026-09-04')]
rawframes={};bars={};data=[]
for s in syms:
 r=json.loads((A/'raw'/f'{s}.json').read_text())['chart']['result'][0]
 dates=pd.to_datetime(r['timestamp'],unit='s',utc=True).tz_convert('America/New_York').tz_localize(None).normalize()
 f=pd.DataFrame(r['indicators']['quote'][0],index=dates).loc[ix]
 dist=pd.Series(0.,index=ix);events=[]
 for kind in ('dividends','capitalGains'):
  for d in r.get('events',{}).get(kind,{}).values():
   day=pd.Timestamp(d['date'],unit='s',tz='UTC').tz_convert('America/New_York').tz_localize(None).normalize()
   if day in ix: dist.loc[day]+=d['amount'];events.append((day,kind,d['amount']))
 assert not r.get('events',{}).get('splits',{})
 f['distribution']=dist
 f['ret']=(f.close+dist).div(f.close.shift()).sub(1);f.loc[ix[0],'ret']=0.
 f['tri']=(1+f.ret).cumprod()
 f['adj']=pd.Series(r['indicators']['adjclose'][0]['adjclose'],index=dates).loc[ix]
 b=pd.read_csv(A/f'bars-{s}.csv',parse_dates=['date']).set_index('date')
 rawframes[s]=f;bars[s]=b
 errs={k:float((f[k]-b[k]).abs().max()) for k in ['open','high','low','close','volume','distribution']}
 assert max(errs.values())<1e-7
 assert (f.volume>0).all() and not f.index.duplicated().any() and np.isfinite(f[['open','high','low','close']]).all().all()
 data.append({'symbol':s,'rows':len(f),'raw_export_errors':errs,'event_types':{k:len(r.get('events',{}).get(k,{})) for k in ('dividends','capitalGains','splits')}})
rets=pd.DataFrame({s:rawframes[s].ret for s in syms});tri=pd.DataFrame({s:rawframes[s].tri for s in syms})
months=pd.Series(ix,index=ix).groupby(ix.to_period('M')).last().tolist()[:-1]
summary=json.loads((A/'summary.json').read_text());out=[];signflip=[]
settle_ix=ix.difference(USFederalHolidayCalendar().holidays(ix[0],ix[-1]))
for mm in summary['variant_metrics']:
 v=mm['variant'];p=A/v;q=pd.read_csv(p/'account.csv',parse_dates=['date']).set_index('date');od=pd.read_csv(p/'orders.csv',parse_dates=['date','signal_date','quantity_decision_date','settlement_date']);ce=pd.read_csv(p/'cash-events.csv',parse_dates=['date'])
 pos=pd.DataFrame(0.,index=q.index,columns=syms);cash=pd.Series(10000.,index=q.index);sales=pd.Series(0.,index=q.index);claims=pd.Series(0.,index=q.index)
 for row in od.itertuples():
  assert row.quantity>0 and row.quantity==int(row.quantity) and row.date>row.signal_date and row.date>row.quantity_decision_date
  assert row.status=='FILLED_OPEN_PROXY'
  sgn=1 if row.side=='BUY' else -1;slip=.002 if 'cost20bps' in v else .005 if 'cost50bps' in v else .0005
  expected=rawframes[row.symbol].loc[row.date,'open']*(1+sgn*slip)
  assert abs(expected-row.fill_price)<1e-8
  assert abs(row.quantity*expected-row.notional_usd)<1e-6
  assert abs(max(1,.005*row.quantity)+.00005*row.notional_usd-row.fee_usd)<1e-8
  n=3 if row.date<pd.Timestamp('2017-09-05') else 2 if row.date<pd.Timestamp('2024-05-28') else 1
  loc=settle_ix.searchsorted(row.date,side='right')+n-1
  if loc<len(settle_ix): assert row.settlement_date==settle_ix[loc]
  pos.loc[row.date:,row.symbol]+=sgn*row.quantity
  if sgn==1:cash.loc[row.date:]-=row.notional_usd+row.fee_usd
  else:sales.loc[row.date:]+=row.notional_usd-row.fee_usd
 for row in ce.itertuples():
  if row.type=='sale_settlement':cash.loc[row.date:]+=row.amount_usd;sales.loc[row.date:]-=row.amount_usd
  elif row.type=='dividend_payment':cash.loc[row.date:]+=row.amount_usd;claims.loc[row.date:]-=row.amount_usd
  else:
   shares=pos.loc[pos.index<row.date,row.symbol].iloc[-1]
   expected=shares*rawframes[row.symbol].loc[row.date,'distribution']
   assert abs(expected-row.gross_usd)<1e-8
   claims.loc[row.date:]+=row.amount_usd
 mark=sum(pos[s]*rawframes[s].close.reindex(q.index) for s in syms)
 nav=cash+sales+claims+mark
 errs={'nav':float((nav-q.equity).abs().max()),'shares':float(np.max(np.abs(pos.to_numpy()-q[[f'shares_{s}' for s in syms]].to_numpy()))),'cash':float((cash-q.settled_cash).abs().max()),'sale_receivable':float((sales-q.unsettled_sale_proceeds).abs().max()),'dividend_receivable':float((claims-q.dividend_receivable).abs().max())}
 assert max(errs.values())<1e-5
 cagr=float((nav.iloc[-1]/10000)**(365.25/(nav.index[-1]-nav.index[0]).days)-1);dd=float((nav/nav.cummax()-1).min())
 assert abs(cagr-mm['cagr'])<1e-9 and abs(dd-mm['max_drawdown'])<1e-9
 ds=pd.read_csv(p/'decisions.csv',parse_dates=['signal_date'])
 maxerr=0;sgn_flips=0
 for row in ds.itertuples():
  i=ix.get_loc(row.signal_date);mi=months.index(row.signal_date);lb=row.lookback_months
  cov=rets.iloc[i-125:i+1].cov().to_numpy()*252;w=np.ones(7)/7;vol=np.sqrt(w@cov@w)
  momentum=tri.loc[row.signal_date,row.symbol]/tri.loc[months[mi-lb],row.symbol]-1
  sc=1 if v in ('static_equal_weight','spy_only','trend_12m_unscaled') else min(1,.10/vol)
  target=(1 if row.symbol=='SPY' else 0) if v=='spy_only' else sc/7*((momentum>0) if v.startswith('trend') else 1)
  maxerr=max(maxerr,abs(row.momentum-momentum),abs(row.risk_scale-sc),abs(row.target_weight-target))
  if v=='trend_12m_risk10':
   ad=rawframes[row.symbol]['adj'];am=ad.loc[row.signal_date]/ad.loc[months[mi-lb]]-1
   if (am>0)!=(momentum>0):signflip.append({'symbol':row.symbol,'date':str(row.signal_date.date()),'explicit':momentum,'adj':am})
 assert maxerr<1e-8
 out.append({'variant':v,'rows':len(q),'orders':len(od),'cagr':cagr,'mdd':dd,'max_errors':errs,'decision_max_error':maxerr})
res={'status':'CONDITIONAL_ACCOUNT_ARITHMETIC_AND_SIGNAL_PASS','scope':'Read-only raw snapshot -> exported bars and independent ledger/signal reconstruction, no strategy engine import, no live data verification.','data':data,'hash_mismatches':bad_hashes,'variants':out,'explicit_vs_adj_12m_sign_flips':signflip}
(O/'independent-checks.json').write_text(json.dumps(res,indent=2))
print(json.dumps({'status':res['status'],'hash_mismatches':bad_hashes,'variants':len(out),'main':out[0],'raw_event_types':data,'12m_adj_sign_flip_count':len(signflip)},indent=2))
