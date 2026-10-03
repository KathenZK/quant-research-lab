"""Independent stdlib Decimal oracle. No tested-engine, pandas, numpy or ta import."""
import csv,json,hashlib,math,statistics,sys
from decimal import Decimal as D, getcontext
from datetime import datetime,timezone
from pathlib import Path
getcontext().prec=45

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def timestamp(s):return int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000)
def date_ms(t):return datetime.fromtimestamp(t/1000,timezone.utc).isoformat().replace('+00:00','Z')
def close(a,b,label,abs_tol=1e-7,rel_tol=1e-10):
 if a is None or b is None: assert a==b,(label,a,b)
 else: assert math.isclose(float(a),float(b),abs_tol=abs_tol,rel_tol=rel_tol),(label,str(a),str(b))
def signs(rows):
 dcp=[];kcw=[];signals=[]
 for i,row in enumerate(rows):
  last10=rows[max(0,i-9):i+1]; last20=rows[max(0,i-19):i+1]
  low=min(r['low'] for r in last10); high=max(r['high'] for r in last10)
  dcp.append((row['close']-low)/(high-low) if i>=9 and high>low else None)
  if i<19:kcw.append(None)
  else:
   center=sum((r['high']+r['low']+r['close'])/3 for r in last20)/20
   width=sum(2*(r['high']-r['low']) for r in last20)/20
   kcw.append(width/center*100)
  signals.append(i>=28 and dcp[i-15] is not None and kcw[i-9] is not None and D('.16')<=dcp[i-15]/kcw[i-9]<=D('.75'))
 return signals

def oracle(rows,spec,case,signal):
 start=timestamp(spec['evaluation']['start']);end=timestamp(spec['evaluation']['end_exclusive']);first=next(i for i,r in enumerate(rows) if r['time']>=start)
 cash=D(str(spec['execution']['initial_cash']));initial=cash;quantity=D(0);fraction=D(str(spec['execution']['cash_budget_fraction']));fee=D(case['fee_bps'])/10000;slip=D(spec['execution']['slippage_bps'])/10000
 buyhold=case.get('buy_hold',False); entries=[];curve=[];trip=[];fees=D(0);opened_cost=None;entry_price=None;entry_time=None;rois=sorted((int(k),D(str(v))) for k,v in spec['risk']['minimal_roi'].items());loss=D(str(spec['risk']['stoploss']))
 for i in range(first,len(rows)):
  row=rows[i];t=row['time']
  if t>=end:break
  effective=1679666400000 if t==1679659200000 else t
  eligible=i==first if buyhold else i-case['delay_bars']>=first and signal[i-case['delay_bars']]
  if quantity==0 and eligible:
   price=row['open']*(1+slip);cost=cash*fraction;quantity=cost/(price*(1+fee));commission=quantity*price*fee;cash-=cost;fees+=commission;entry_time=effective;entry_price=price;opened_cost=cost
   entries.append({'bar_index':i,'side':'BUY','reason':'buy_hold' if buyhold else 'entry_signal','phase':'open','reference_price':row['open'],'fill_price':price,'quantity':quantity,'fee':commission,'cash_after':cash,'quantity_after':quantity,'roi_step_minutes':None,'roi_target':None})
  if quantity>0 and not buyhold:
   age=(effective-entry_time)//60000;key,roi=max(x for x in rois if x[0]<=age)
   floor=entry_price*(1+loss);ceiling=entry_price*(1+fee)*(1+roi)/(1-fee)
   # Derive candidate event priorities rather than consume any tested-engine decision.
   candidates=[]
   if row['open']<=floor:candidates.append((0,'stoploss','open_gap',row['open']))
   if row['open']>=ceiling:candidates.append((1,'roi','open_gap',row['open']))
   if row['low']<=floor:candidates.append((2,'stoploss','intrabar_unknown',floor))
   if row['high']>=ceiling:candidates.append((3,'roi','intrabar_unknown',ceiling))
   if candidates:
    _,reason,phase,reference=min(candidates);price=reference*(1-slip);commission=quantity*price*fee;proceeds=quantity*price-commission;cash+=proceeds;fees+=commission;trip.append(proceeds/opened_cost-1)
    entries.append({'bar_index':i,'side':'SELL','reason':reason,'phase':phase,'reference_price':reference,'fill_price':price,'quantity':quantity,'fee':commission,'cash_after':cash,'quantity_after':D(0),'roi_step_minutes':key,'roi_target':roi});quantity=D(0)
  curve.append({'bar_index':i,'cash':cash,'quantity':quantity,'equity':cash+quantity*row['close'],'close':row['close'],'time':t,'valuation':t+14400000})
 equities=[initial]+[r['equity'] for r in curve];daily=[]
 for i,r in enumerate(curve):
  if i+1==len(curve) or r['time']//86400000!=curve[i+1]['time']//86400000:daily.append(r)
 deq=[initial]+[r['equity'] for r in daily]
 returns=[b/a-1 for a,b in zip(equities,equities[1:])];dr=[b/a-1 for a,b in zip(deq,deq[1:])]
 def sharpe(x,mult):
  f=[float(z) for z in x]; sd=statistics.stdev(f)
  return statistics.mean(f)/sd*math.sqrt(mult) if sd else None
 peak=initial;dd=D(0)
 for e in equities:peak=max(peak,e);dd=max(dd,1-e/peak)
 metrics={'total_return':equities[-1]/initial-1,'annualized_return':float(equities[-1]/initial)**(365/((end-start)/86400000))-1,'max_drawdown':dd,'sharpe_daily':sharpe(dr,365),'sharpe_4h':sharpe(returns,365*6),'final_equity':equities[-1],'final_cash':cash,'final_quantity':quantity,'fill_events':len(entries),'completed_roundtrips':len(trip),'winning_roundtrip_fraction':D(sum(x>0 for x in trip))/len(trip) if trip else None,'fees_paid':fees,'position_bar_fraction':D(sum(x['quantity']>0 for x in curve))/len(curve),'observations':len(curve),'daily_observations':len(daily)}
 return entries,curve,daily,metrics

def main(spec_path,input_path,result_dir,out):
 spec=json.loads(spec_path.read_text());raw=list(csv.DictReader(input_path.open()));summary=json.loads((result_dir/'summary.json').read_text());assert summary['protocol_sha256']==sha(spec_path) and summary['input_sha256']==sha(input_path)
 for p,h in spec['frozen_file_hashes'].items():assert sha(spec_path.parents[1]/p)==h,p
 rows=[dict(time=int(r['open_time']),**{c:D(r[c]) for c in ['open','high','low','close','volume']}) for r in raw];signal=signs(rows);reports=[]
 for case in spec['cases']:
  name=case['name'];trades,nav,daily,m=oracle(rows,spec,case,signal);actual=list(csv.DictReader((result_dir/(name+'-trades.csv')).open()));assert len(actual)==len(trades),(name,'trade_count')
  for j,(a,b) in enumerate(zip(actual,trades)):
   for key in ['bar_index','side','reason','phase']:assert str(a[key])==str(b[key]),(name,j,key,a[key],b[key])
   for key in ['reference_price','fill_price','quantity','fee','cash_after','quantity_after']:close(a[key],b[key],(name,j,key))
   if b['side']=='SELL':close(a['roi_step_minutes'],b['roi_step_minutes'],(name,j,'roi_minutes'));close(a['roi_target'],b['roi_target'],(name,j,'roi_target'))
  for suffix,expected in [('nav',nav),('daily-nav',daily)]:
   actualnav=list(csv.DictReader((result_dir/(name+'-'+suffix+'.csv')).open()));assert len(actualnav)==len(expected)
   for j,(a,b) in enumerate(zip(actualnav,expected)):
    assert int(a['bar_index'])==b['bar_index'] and timestamp(a['timestamp_utc'])==b['valuation']
    for key in ['cash','quantity','equity','close']:close(a[key],b[key],(name,suffix,j,key))
    close(a['nav'],b['equity']/D(str(spec['execution']['initial_cash'])),(name,suffix,j,'nav'))
  actualm=summary['results'][name]['metrics']
  for key,v in m.items():close(actualm[key],v,(name,'metric',key))
  reports.append({'case':name,'status':'PASS_INDEPENDENT_DECIMAL_LEDGER_CURVES_AND_METRICS','fills_checked':len(trades),'nav_rows_checked':len(nav),'daily_rows_checked':len(daily),'metric_fields_checked':list(m),'computed_metrics':{k:float(v) if isinstance(v,D) else v for k,v in m.items()}})
 result={'status':'PASS_INDEPENDENT_REPLAY','protocol_sha256':sha(spec_path),'input_sha256':sha(input_path),'summary_sha256':sha(result_dir/'summary.json'),'auditor_sha256':sha(__file__),'cases':reports,'stdlib_decimal_only':True,'tested_engine_imported':False,'strict_reproductions':0,'limitations':'Agreement validates declared diagnostic port only; cannot establish Freqtrade fidelity, intrabar tradability, PIT or OOS. Stop/ROI simultaneous-hit and boundary log separate checks.','at_utc':datetime.now(timezone.utc).isoformat()}
 out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main(*map(Path,sys.argv[1:]))
