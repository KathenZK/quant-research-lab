"""Fixed-rule ETF account diagnostics on UNACCEPTED Yahoo daily raw snapshots.
Total-return price units (provider adjclose/close applied to open), never trusted
OHLCV or original LEAN fill replication. Missing sessions fail closed.
"""
from pathlib import Path
import json,hashlib,calendar,shutil
import numpy as np
import pandas as pd
from scipy.optimize import minimize
import exchange_calendars as xc
ROOT=Path(__file__).resolve().parents[4];F=Path(__file__).resolve().parents[1]
C=json.loads((F/'specs/run-contract-v1.json').read_text());OUT=F/'artifacts/equity-diagnostic';OUT.mkdir(exist_ok=True)
GROUP=['SPY','EFA','BND','VNQ','GSG'];SECTOR=['VNQ','XLK','XLE','XLV','XLF','KBE','VAW','XLY','XLP','VGT'];STYLE=['IJJ','IJK','IJS','IJT','IVE','IVW'];KDA=['SPY','VGK','EWJ','EEM','VNQ','RWX','IEF','TLT','DBC','GLD','VWO','BND']
def load():
 m=json.loads((F/'artifacts/equity-raw-manifest.json').read_text());data={};audit=[]
 for r in m['records']:
  if 'error' in r:raise ValueError(r)
  p=ROOT/r['payload_path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==r['payload_sha256']
  # Verify data-lake partitions without silently replacing them with the payload.
  for f in r['files']:
   raw=ROOT/f['path'];assert hashlib.sha256(raw.read_bytes()).hexdigest()==f['sha256']
  obj=json.loads(p.read_text())['chart']['result'][0];d=pd.DataFrame(obj['indicators']['quote'][0]);d.index=pd.to_datetime(obj['timestamp'],unit='s',utc=True).tz_convert('America/New_York').normalize().tz_localize(None)
  d['adjclose']=obj['indicators']['adjclose'][0]['adjclose'];d=d[d.index<pd.Timestamp(C['cutoff']).tz_localize(None)]
  d=d[['open','high','low','close','volume','adjclose']]
  assert not d.index.has_duplicates
  valid=d.notna().all(axis=1)&np.isfinite(d).all(axis=1)&(d[['open','high','low','close','adjclose']]>0).all(axis=1)&(d.volume>=0)&(d.high>=d[['open','low','close']].max(axis=1))&(d.low<=d[['open','high','close']].min(axis=1))
  if not valid.all():raise ValueError((r['symbol'],'invalid raw rows',d.index[~valid].tolist()))
  sessions=xc.get_calendar('XNYS',start='2007-01-01',end='2027-01-01').sessions_in_range(d.index.min(),d.index.max()).tz_localize(None)
  missing=sessions.difference(d.index);extra=d.index.difference(sessions)
  if len(missing) or len(extra):raise ValueError((r['symbol'],'session gaps',list(missing),list(extra)))
  factor=d.adjclose/d.close;d['adjopen']=d.open*factor
  data[r['symbol']]=d;audit.append({'symbol':r['symbol'],'rows':len(d),'missing_sessions':len(missing),'extra_sessions':len(extra),'status':'RAW_BASIC_CHECK_PASS_NOT_ACCEPTED'})
 (OUT/'data-audit.json').write_text(json.dumps(audit,indent=2))
 return data

def metric(eq):
 rets=eq.pct_change().dropna();total=float(eq.iloc[-1]/eq.iloc[0]-1);years=(eq.index[-1]-eq.index[0]).total_seconds()/86400/365.25
 dd=eq/eq.cummax()-1
 return {'total_return':total,'cagr':float((1+total)**(1/years)-1),'mdd':float(dd.min()),'annual_vol':float(rets.std(ddof=1)*np.sqrt(252)),'sharpe_rf0':float(rets.mean()/rets.std(ddof=1)*np.sqrt(252)) if rets.std()>0 else None}

def simulate(op,cl,w,reb,cost,borrow=.03):
 # Target row t is formed using at most close(t-1), or pre-known calendar.
 n,p=cl.shape;q=np.zeros(p);cash=1.;prev=1.;out=[];turns=[];orders=[]
 for i,date in enumerate(cl.index):
  o=op.iloc[i].to_numpy();c=cl.iloc[i].to_numpy();eqopen=cash+float(q@o);turn=0.
  if reb[i]:
   target=w[i];post=eqopen
   for _ in range(30):post=eqopen-cost*np.abs(target*post-q*o).sum()
   delta=target*post-q*o;fee=cost*np.abs(delta).sum();cash=eqopen-fee-float((target*post).sum());q=target*post/o;turn=np.abs(delta).sum()/eqopen
   for j in np.flatnonzero(np.abs(delta)>1e-10):orders.append({'date':str(date.date()),'symbol':cl.columns[j],'signed_notional':float(delta[j]),'fill_total_return_price':float(o[j]),'fee':float(cost*abs(delta[j]))})
  days=(date-cl.index[i-1]).days if i else 1
  cash-=float(np.maximum(-q*c,0).sum())*borrow*days/365.25
  equity=cash+float(q@c)
  if equity<=0:raise ValueError('insolvent')
  out.append(equity);turns.append(turn);prev=equity
 # Explicit final close liquidation costs; no infinite unclosed end position.
 liquidation=cost*np.abs(q*cl.iloc[-1].to_numpy()).sum();out[-1]-=liquidation
 if np.abs(q).sum()>0:
  for j in np.flatnonzero(np.abs(q)>1e-14):orders.append({'date':str(cl.index[-1].date()),'symbol':cl.columns[j],'signed_notional':float(-q[j]*cl.iloc[-1,j]),'fill_total_return_price':float(cl.iloc[-1,j]),'fee':float(cost*abs(q[j]*cl.iloc[-1,j])),'reason':'final_liquidation'})
 eq=pd.Series([1.]+out,index=pd.DatetimeIndex([cl.index[0]-pd.Timedelta(days=1)]+list(cl.index)),name='equity');return eq,orders,turns

def make_weights(allcl,variant):
 idx=allcl.index;N=len(idx);syms=list(allcl.columns);w=np.zeros((N,len(syms)));reb=np.zeros(N,bool);last=np.zeros(len(syms));ends=np.flatnonzero(idx.to_period('M')!=pd.Series(idx.to_period('M')).shift(-1).to_numpy())
 def put(d):
  x=np.zeros(len(syms))
  for s,v in d.items():x[syms.index(s)]=v
  return x
 returns=allcl.pct_change(fill_method=None)
 for i,date in enumerate(idx):
  if i<756:continue
  monthfirst=i==0 or date.month!=idx[i-1].month;prev=allcl.iloc[i-1];hist=allcl.iloc[:i]
  target=None
  if variant=='SPY_BUY_HOLD':
   if i==756:target={'SPY':1.}
  elif variant=='A6_CODE_DAILY210':
   chosen=[s for s in GROUP if prev[s]>hist[s].iloc[-210:].mean()];target={s:1/len(chosen) for s in chosen}
  elif variant=='A6_TEXT_MONTHLY10':
   if monthfirst:
    m=hist[GROUP].groupby(hist.index.to_period('M')).last();chosen=[s for s in GROUP if prev[s]>m[s].iloc[-10:].mean()];target={s:1/len(chosen) for s in chosen}
  elif variant=='A7_TEXT_ROC252':
   if monthfirst:
    score=prev[GROUP]/allcl.iloc[i-253][GROUP]-1;chosen=score.sort_values(ascending=False,kind='stable').index[:3];target={s:1/3 for s in chosen}
  elif variant in ('A9_CODE_MOM63','A9_TEXT_ROC252'):
   if monthfirst:
    L=63 if 'CODE' in variant else 252;score=prev[SECTOR]-allcl.iloc[i-1-L][SECTOR] if 'CODE' in variant else prev[SECTOR]/allcl.iloc[i-1-L][SECTOR]-1;chosen=score.sort_values(ascending=False,kind='stable').index[:3];target={s:1/3 for s in chosen}
  elif variant=='A20_OPEN_PROXY':
   if monthfirst and date.month in (1,4,7,10):
    base=hist[hist.index>=date-pd.Timedelta(days=90)].iloc[0];score=(prev[['SPY','AGG']]-base[['SPY','AGG']])/prev[['SPY','AGG']];target={score.idxmax():1.}
  elif variant=='A22_CALENDAR_PROXY':
   # Last trading day open through third trading day next month close.
   per=idx.to_period('M');future=idx[(per==per[i])];rank=list(future).index(date);monthend=rank==len(future)-1
   hold=monthend or rank<3;target={'SPY':float(hold)}
  elif variant in ('A29_CODE_REVERSED','A29_TEXT_ROC252'):
   if monthfirst:
    if 'CODE' in variant:score=prev[STYLE]-allcl.iloc[i-241][STYLE];target={score.idxmin():.5,score.idxmax():-.5}
    else:score=prev[STYLE]/allcl.iloc[i-253][STYLE]-1;target={score.idxmax():.5,score.idxmin():-.5}
  elif variant=='A36_JANUARY_BAROMETER':
   if monthfirst and date.month==1:target={'SPY':1.}
   if monthfirst and date.month==2:
    jan=hist[hist.index.year==date.year];target={'SPY' if jan.SPY.iloc[-1]>jan.SPY.iloc[0] else 'BIL':1.}
  elif variant=='A38_VIX_SOURCE_RULE':
   vh=VIX[VIX.index<=idx[i-1]].iloc[-504:]
   if len(vh)==504:
    if vh.iloc[-1]>vh.quantile(.9):target={'OEF':1.}
    elif vh.iloc[-1]<vh.quantile(.1):target={'OEF':-1.}
  elif variant=='A40_CALENDAR_PROXY':
   look=pd.date_range(date,date+pd.Timedelta(days=2),freq='D');holidays=[d for d in look if d.weekday()<5 and d not in SESSION_SET];target={'SPY':float(bool(holidays))}
  elif variant=='A53_TEXT_DAILY200':target={'SSO' if prev.SSO>hist.SSO.iloc[-200:].mean() else 'SHY':1.}
  elif variant=='C1_GEM':
   if monthfirst:
    months=hist.groupby(hist.index.to_period('M')).last();mom=months.iloc[-1]/months.iloc[-13]-1;target={('SPY' if mom.SPY>=mom.EFA else 'EFA') if mom.SPY>=mom.BIL else 'BIL':1.}
  elif variant=='C4_KDA100':
   if monthfirst:
    months=hist[KDA].groupby(hist.index.to_period('M')).last();mom=sum(mult*(months.iloc[-1]/months.iloc[-lag-1]-1) for lag,mult in [(1,12),(3,4),(6,2),(12,1)])
    risk=mom.iloc[:10];chosen=[s for s in risk.sort_values(ascending=False,kind='stable').index[:5] if risk[s]>0];a=float((mom[['VWO','BND']]>0).mean());target={}
    if len(chosen)==1:target={chosen[0]:a}
    elif len(chosen)>1:
     def window(lag):return returns.loc[(returns.index>months.index.to_timestamp(how='end')[-lag-1].normalize())&(returns.index<date),chosen]
     cors=sum(mult*window(lag).corr().to_numpy() for lag,mult in [(1,12),(3,4),(6,2),(12,1)])/19
     vol=window(1).std(ddof=1).to_numpy();cov=cors*np.outer(vol,vol);scale=max(np.diag(cov).max(),1e-12);cov=cov/scale
     opt=minimize(lambda x:float(x@cov@x),np.ones(len(chosen))/len(chosen),jac=lambda x:2*cov@x,bounds=[(0,1)]*len(chosen),constraints={'type':'eq','fun':lambda x:x.sum()-1,'jac':lambda x:np.ones_like(x)},method='SLSQP',options={'ftol':1e-12,'maxiter':500})
     if not opt.success:raise ValueError(('KDA optimizer failed',date,opt.message))
     target=dict(zip(chosen,a*opt.x))
    if mom.IEF>0:target['IEF']=target.get('IEF',0)+1-a
  if target is not None:
   last=put(target);reb[i]=True
  w[i]=last
 return w,reb

VARIANTS=['A6_CODE_DAILY210','A6_TEXT_MONTHLY10','A7_TEXT_ROC252','A9_CODE_MOM63','A9_TEXT_ROC252','A20_OPEN_PROXY','A22_CALENDAR_PROXY','A29_CODE_REVERSED','A29_TEXT_ROC252','A36_JANUARY_BAROMETER','A38_VIX_SOURCE_RULE','A40_CALENDAR_PROXY','A53_TEXT_DAILY200','C1_GEM','C4_KDA100']
if __name__=='__main__':
 data=load();cl=pd.DataFrame({s:d.adjclose for s,d in data.items()});op=pd.DataFrame({s:d.adjopen for s,d in data.items()});assert cl.notna().all().all() and op.notna().all().all()
 cal=xc.get_calendar('XNYS',start='2007-01-01',end='2027-01-01');SESSION_SET=set(cal.sessions.tz_localize(None))
 vp=ROOT/'data/raw/source_payloads/source=cboe/date=2026-09-08/public100_vix_history.csv';vp.parent.mkdir(parents=True,exist_ok=True)
 if not vp.exists():shutil.copy2('/tmp/public100-vix.csv',vp)
 v=pd.read_csv(vp);VIX=pd.Series(v.CLOSE.to_numpy(),index=pd.to_datetime(v.DATE));VIX=VIX[VIX.index<pd.Timestamp(C['cutoff']).tz_localize(None)]
 (OUT/'vix-source.json').write_text(json.dumps({'source':'https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv','path':str(vp.relative_to(ROOT)),'sha256':hashlib.sha256(vp.read_bytes()).hexdigest(),'status':'raw_unaccepted index values only'},indent=2))
 start=max(pd.Timestamp(C['equity_evaluation_start']),cl.index[756]);mask=cl.index>=start;optest=op.loc[mask];cltest=cl.loc[mask];results=[]
 for var in VARIANTS:
  w,reb=make_weights(cl,var);wt=w[mask];rb=reb[mask];rb[0]=True
  np.savez_compressed(OUT/f'{var}-targets.npz',weights=wt,rebalances=rb,symbols=np.array(cl.columns),dates=cltest.index.values)
  for bps in C['equity_one_way_cost_bps']:
   eq,orders,turns=simulate(optest,cltest,wt,rb,bps/10000)
   eq.to_csv(OUT/f'{var}-{bps}bps-equity.csv');pd.DataFrame(orders).to_csv(OUT/f'{var}-{bps}bps-orders.csv',index=False)
   r={'id':var.split('_')[0],'variant':var,'status':'EXPLORE_UNTRUSTED','cost_bps':bps,'start':str(start.date()),'end':str(cltest.index[-1].date()),**metric(eq),'order_count':len(orders),'turnover':sum(turns)}
   r['yearly']={str(y):float(np.prod(1+g)-1) for y,g in eq.pct_change().dropna().groupby(eq.pct_change().dropna().index.year)};results.append(r)
  print(var,results[-2]['total_return'],flush=True)
 # Overnight SPY: fixed known close->next-open schedule, independent of price signal.
 s=data['SPY'];s=s[s.index>=start];g=s.adjopen.shift(-1)/s.adjclose
 for bps in C['equity_one_way_cost_bps']:
  returns=(g*(1-bps/10000)/(1+bps/10000)-1).iloc[:-1];eq=pd.Series(np.r_[1.,np.cumprod(1+returns)],index=pd.DatetimeIndex([s.index[0]-pd.Timedelta(days=1)]+list(s.index[1:])),name='equity')
  eq.to_csv(OUT/f'A10_OVERNIGHT-{bps}bps-equity.csv');results.append({'id':'A10','variant':'A10_OVERNIGHT','status':'EXPLORE_UNTRUSTED','cost_bps':bps,**metric(eq),'order_count':2*len(returns),'start':str(s.index[0].date()),'end':str(s.index[-1].date()),'yearly':{str(y):float(np.prod(1+g)-1) for y,g in eq.pct_change().dropna().groupby(eq.pct_change().dropna().index.year)}})
 # Same-window buy-and-hold benchmark, costs at both endpoints.
 for bps in C['equity_one_way_cost_bps']:
  w=np.zeros(cltest.shape);w[:,list(cltest.columns).index('SPY')]=1;reb=np.zeros(len(cltest),bool);reb[0]=True
  eq,orders,_=simulate(optest,cltest,w,reb,bps/10000);eq.to_csv(OUT/f'SPY_BUY_HOLD-{bps}bps-equity.csv');results.append({'id':'BENCHMARK','variant':'SPY_BUY_HOLD','cost_bps':bps,**metric(eq),'yearly':{str(y):float(np.prod(1+g)-1) for y,g in eq.pct_change().dropna().groupby(eq.pct_change().dropna().index.year)}})
 (OUT/'results.json').write_text(json.dumps({'results':results,'contract_sha256':hashlib.sha256((F/'specs/run-contract-v1.json').read_bytes()).hexdigest(),'engine_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'status':'EXPLORE_UNTRUSTED'},indent=2,allow_nan=False))
