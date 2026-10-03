"""Independent recorded-signal and risk-log checks; no tested-engine imports."""
import argparse,csv,json,hashlib
from pathlib import Path
from decimal import Decimal as D
from datetime import datetime,timezone
from independent_oracle import signs,timestamp
parser=argparse.ArgumentParser();parser.add_argument('--work',required=True);parser.add_argument('--input',required=True);args=parser.parse_args();S=Path(__file__).resolve().parents[1];R=Path(args.work);P=Path(args.input)
spec=json.loads((S/'specs/protocol.json').read_text());summary=json.loads((R/'summary.json').read_text());raw=list(csv.DictReader(P.open()));bars=[dict(time=int(r['open_time']),**{c:D(r[c]) for c in ['open','high','low','close','volume']}) for r in raw];ss=signs(bars);actual=list(csv.DictReader((R/'signals.csv').open()));assert len(ss)==len(actual)
assert all(int(a['open_time'])==b['time'] and (a['entry_signal']=='True')==s for a,b,s in zip(actual,bars,ss))
results=[]
for case in spec['cases']:
 name=case['name'];trades=list(csv.DictReader((R/f'{name}-trades.csv').open()));events={}
 for e in trades:events.setdefault(int(e['bar_index']),[]).append(e)
 qty=D(0);entry=None;entry_time=None;candidate=[];both=ambiguous=0;fee=D(case['fee_bps'])/10000
 for i in range(186,len(bars)):
  row=bars[i];t=row['time'];effective=1679666400000 if t==1679659200000 else t;nexttime=1679666400000 if t+14400000==1679659200000 else t+14400000
  for e in events.get(i,[]):
   if e['side']=='BUY':
    entry=D(e['fill_price']);entry_time=effective;qty=D(e['quantity'])
   if e['phase'] in ('open','open_gap'):assert timestamp(e['execution_time_utc'])==effective
   assert timestamp(e['execution_earliest_utc'])>=effective
   if t==1679644800000 and e['phase']=='intrabar_unknown':assert timestamp(e['execution_latest_utc'])==1679657220000-1
  if qty>0 and not case.get('buy_hold',False):
   minute,roi=max((int(k),D(str(v))) for k,v in spec['risk']['minimal_roi'].items() if int(k)<=(effective-entry_time)//60000)
   stop=entry*(1+D(str(spec['risk']['stoploss'])));roi_price=entry*(1+fee)*(1+roi)/(1-fee)
   if row['low']<=stop and row['high']>=roi_price:
    both+=1;ambiguous+=int(stop<row['open']<roi_price)
   for key in [644,3269,7289]:
    boundary=entry_time+key*60000
    if effective<boundary<nexttime:candidate.append((i,boundary,key,nexttime))
  for e in events.get(i,[]):
   if e['side']=='SELL':qty=D(0)
 logs=json.loads((R/f'{name}-roi-boundaries.json').read_text());actualevents=[(x['bar_index'],timestamp(x['boundary_utc']),x['minutes'],timestamp(x['observed_from_utc'])) for x in logs];assert actualevents==candidate,(name,'boundary log')
 m=summary['results'][name]['metrics'];assert m['both_stop_roi_touched']==both and m['unresolved_stop_roi_samebar']==ambiguous and m['roi_boundary_candidate_bars']==len(candidate)
 results.append({'case':name,'both_stop_roi_touched':both,'unresolved_stop_roi_samebar':ambiguous,'roi_boundary_candidates':len(candidate),'status':'PASS'})
res={'status':'PASS_SIGNALS_RISK_COUNTS_AND_EXECUTION_INTERVALS','signal_rows_checked':len(ss),'cases':results,'source_engine_imported':False,'no_1m_data_read':True,'auditor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'at_utc':datetime.now(timezone.utc).isoformat()};print(json.dumps(res,indent=2))
