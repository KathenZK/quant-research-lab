"""Additional prespecified calendar tests on already frozen untrusted ETF inputs."""
from pathlib import Path
import json,subprocess,datetime,hashlib,importlib.util
import numpy as np
import pandas as pd
import exchange_calendars as xc
F=Path(__file__).resolve().parents[1];ROOT=F.parents[2];OUT=F/'artifacts/equity-diagnostic'
sp=importlib.util.spec_from_file_location('etf',F/'scripts/backtest_equity_diagnostic.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
SPEC=F/'specs/calendar-supplement-v1.json'
if not SPEC.exists():SPEC.write_text(json.dumps({'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'ids':['A31','A37'],'A31':'OEF regular monthly expiry third Friday adjusted to preceding XNYS session. Enter Monday open, exit expiry open (daily proxy for source Monday10:00 and expiry first intraday data). Monday holiday means no entry as original Monday scheduling.','A37':'EEM long from last-quarter date open; short from first-quarter date open. Known astronomical quarter dates calculated with ephem4.2.1; use UTC calendar dates to mirror source truncation. Reversals on next equity session if quarter occurs on holiday. Calendar provider substitution explicit.','shared_contract':'run-contract-v1.json','status':'EXPLORE_UNTRUSTED'},indent=2))
moon=ROOT/'data/features/public100_lunar_calendar_v1';moon.mkdir(parents=True,exist_ok=True)
script="""import ephem,json
out=[]
for phase,fn in [('First Quarter',ephem.next_first_quarter_moon),('Last Quarter',ephem.next_last_quarter_moon)]:
 t=ephem.Date('2008/1/1')
 while True:
  t=fn(t)
  if t.datetime().year>2026:break
  out.append({'ts_utc':t.datetime().isoformat()+'Z','phase':phase})
  t=ephem.Date(float(t)+1)
print(json.dumps(sorted(out,key=lambda x:x['ts_utc'])))
"""
p=moon/'events.json'
if not p.exists():p.write_text(subprocess.check_output(['/tmp/public100-freqtrade-env/bin/python','-c',script],text=True))
(moon/'_MANIFEST.json').write_text(json.dumps({'dataset_id':'astronomy.lunar_quarters.public100.v1','status':'DIAGNOSTIC_DERIVED_NOT_MARKET_DATA','algorithm':'ephem4.2.1 next_first_quarter_moon and next_last_quarter_moon','generator_sha256':hashlib.sha256(script.encode()).hexdigest(),'events_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'source_market_inputs':[],'generation_time':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2))
records=json.loads((F/'artifacts/equity-raw-manifest.json').read_text())['records'];data={}
for r in records:
 if r['symbol'] not in ['OEF','EEM']:continue
 pp=ROOT/r['payload_path'];assert hashlib.sha256(pp.read_bytes()).hexdigest()==r['payload_sha256'];o=json.loads(pp.read_text())['chart']['result'][0];q=pd.DataFrame(o['indicators']['quote'][0]);q.index=pd.to_datetime(o['timestamp'],unit='s',utc=True).tz_convert('America/New_York').normalize().tz_localize(None);q['adjclose']=o['indicators']['adjclose'][0]['adjclose'];q['adjopen']=q.open*q.adjclose/q.close;data[r['symbol']]=q
existing=json.loads((OUT/'results.json').read_text())['results'];start=pd.Timestamp(existing[0]['start']);cl=pd.DataFrame({s:d.adjclose for s,d in data.items()}).loc[start:];op=pd.DataFrame({s:d.adjopen for s,d in data.items()}).loc[start:];assert cl.notna().all().all();idx=cl.index
sessions=xc.get_calendar('XNYS',start='2007-01-01',end='2027-01-01').sessions.tz_localize(None)
events=json.loads(p.read_text());quarter=pd.Series({pd.Timestamp(e['ts_utc']).tz_localize(None).normalize():1 if e['phase']=='Last Quarter' else -1 for e in events}).sort_index()
results=[]
for var in ['A31_EXPIRY_OPEN_PROXY','A37_QUARTER_CALENDAR_PROXY']:
 w=np.zeros(cl.shape);reb=np.zeros(len(cl),bool)
 if var.startswith('A31'):
  for year in sorted(set(idx.year)):
   for month in range(1,13):
    d=pd.Timestamp(year,month,1);friday=d+pd.Timedelta(days=(4-d.weekday())%7+14);expiry=max(sessions[sessions<=friday]);monday=friday-pd.Timedelta(days=4)
    if monday not in idx:continue
    w[(idx>=monday)&(idx<expiry),list(cl.columns).index('OEF')]=1
  reb[:]=True
 else:
  for i,d in enumerate(idx):
   e=quarter[quarter.index<=d];w[i,list(cl.columns).index('EEM')]=float(e.iloc[-1]) if len(e) else 0
  reb[0]=True;reb[1:]=np.any(w[1:]!=w[:-1],axis=1)
 np.savez_compressed(OUT/f'{var}-targets.npz',weights=w,rebalances=reb,symbols=np.array(cl.columns),dates=idx.values)
 for bps in m.C['equity_one_way_cost_bps']:
  eq,orders,turns=m.simulate(op,cl,w,reb,bps/10000);eq.to_csv(OUT/f'{var}-{bps}bps-equity.csv');pd.DataFrame(orders).to_csv(OUT/f'{var}-{bps}bps-orders.csv',index=False)
  results.append({'id':var.split('_')[0],'variant':var,'status':'EXPLORE_UNTRUSTED','cost_bps':bps,'start':str(idx[0].date()),'end':str(idx[-1].date()),**m.metric(eq),'order_count':len(orders),'yearly':{str(y):float(np.prod(1+g)-1) for y,g in eq.pct_change().dropna().groupby(eq.pct_change().dropna().index.year)}})
(OUT/'calendar-results.json').write_text(json.dumps({'status':'EXPLORE_UNTRUSTED','spec_sha256':hashlib.sha256(SPEC.read_bytes()).hexdigest(),'results':results},indent=2,allow_nan=False));print([(r['variant'],r['total_return']) for r in results if r['cost_bps']==10])
