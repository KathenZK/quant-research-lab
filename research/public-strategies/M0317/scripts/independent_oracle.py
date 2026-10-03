# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent Decimal execution/accounting oracle. Does NOT import tested engine."""
import csv,json,hashlib,sys,statistics,math
from pathlib import Path
from decimal import Decimal as D,getcontext
from datetime import datetime,timezone
from independent_indicators import features
getcontext().prec=45
B=14400000;HB=1679659200000;HR=1679666400000;HP=1679644800000;HS=1679657220000
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
ms=lambda s:int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000)
iso=lambda t:datetime.fromtimestamp(t/1000,timezone.utc).isoformat().replace('+00:00','Z')

def close(a,b,tol=D('0.00000015')):
 assert abs(D(str(a))-D(str(b)))<=tol,(a,b,abs(D(str(a))-D(str(b))))

def oracle(sid,rows,f,spec,case):
 fee=D(str(case['fee_bps']))/10000;slip=D(str(spec['execution']['slippage_bps']))/10000;frac=D(str(spec['execution']['cash_budget_fraction']));initial=D(str(spec['execution']['initial_cash']));cash=initial;q=D(0);entry=D(0);cost=D(0);origin=None;stop=D(0);peak=D(0);active=False
 hold=case.get('buy_hold',False);delay=case['delay_bars'];events=[];nav=[];wins=[];fees=D(0);orders=[];risks=[];boundary=[];nactive=nsup=both=ambig=0
 start=ms(spec['evaluation']['start']);end=ms(spec['evaluation']['end_exclusive']);indices=[i for i,r in enumerate(rows) if start<=int(r['open_time'])<end];first=indices[0]
 roitable={int(k):D(str(v)) for k,v in spec['risk']['minimal_roi'].items()}
 for i in indices:
  r=rows[i];t=int(r['open_time']);eff=HR if t==HB else t;last=HS-1 if t==HP else t+B-1;nex=HR if t+B==HB else t+B
  o,h,l,c=[D(r[k]) for k in ['open','high','low','close']];j=i-delay;valid=j>=first
  en=(i==first) if hold else bool(valid and f['mab_entry' if sid=='M0317' else 'hlhb_entry'][j])
  ex=False if hold else bool(valid and f['mab_exit' if sid=='M0317' else 'hlhb_exit'][j]);pending=None;exited=False;key=0;roi=roitable[0];suppress=en and not hold and sid=='M0316'
  def transact(side,ref,reason,phase,limit=None):
   nonlocal cash,q,entry,origin,cost,fees,stop,peak,active,pending,exited,key,roi
   price=ref*(1+slip if side=='BUY' else 1-slip)
   if limit is not None:price=min(price,limit) if side=='BUY' else max(price,limit)
   isopen=phase in ['open','open_gap'];signal=j if reason=='entry_signal' and side=='BUY' else (pending['signal'] if pending and reason=='exit_signal' else None)
   if side=='BUY':
    qty=cash*frac/(price*(1+fee));notional=qty*price;commission=notional*fee;cash-=notional+commission;q=qty;entry=price;origin=eff if isopen else last+1;cost=notional+commission;stop=entry*(1+D(str(spec['risk']['stoploss'])));peak=entry;active=False;key=0;roi=roitable[0]
   else:
    qty=q;notional=qty*price;commission=notional*fee;cash+=notional-commission;q=D(0);wins.append((notional-commission)/cost-1);exited=True
   fees+=commission
   events.append({'bar_index':i,'side':side,'reason':reason,'phase':phase,'reference_price':ref,'fill_price':price,'quantity':qty,'notional':notional,'fee':commission,'cash_after':cash,'quantity_after':q,'signal_bar_index':signal,'effective':eff,'last':eff if isopen else last,'exact':eff if isopen else None,'roi_step_minutes':key,'roi_target':roi,'origin':origin,'limit_price':limit,'stop_level':stop})
   if pending:
    pending['status']='filled' if pending['side']==side and reason in ['entry_signal','exit_signal','buy_hold'] else 'cancelled_by_risk';pending['resolved_phase']=phase;pending=None
  def move_peak(price,phase):
   nonlocal peak,active,stop,nactive
   if not q or hold:return
   peak=max(peak,price);threshold=entry*(1+fee)*(1+D(str(spec['risk']['trailing_offset'])))/(1-fee)
   if peak>threshold and not active:active=True;nactive+=1;risks.append({'bar_index':i,'event':'trailing_activation','phase':phase,'activation_price_threshold':threshold,'observed_path_price':price,'fee_bps':case['fee_bps']})
   if active:stop=max(stop,peak*(1-D(str(spec['risk']['trailing_positive']))))
   elif peak==threshold:stop=max(stop,peak*(1+D(str(spec['risk']['stoploss']))))
  def target():return entry*(1+fee)*(1+roi)/(1-fee)
  if sid=='M0317':
   if q==0 and en:transact('BUY',o,'buy_hold' if hold else 'entry_signal','open')
   if q and not hold:
    elapsed=(eff-origin)//60000;key=max(k for k in roitable if k<=elapsed);roi=roitable[key];stop=entry*(1+D(str(spec['risk']['stoploss'])));tar=target();sh=l<=stop;rh=h>=tar
    both+=int(sh and rh);ambig+=int(sh and rh and stop<o<tar)
    for minute in roitable:
     bt=origin+minute*60000
     if minute>0 and eff<bt<nex:boundary.append({'bar_index':i,'boundary_utc':iso(bt),'minutes':minute,'observed_from_utc':iso(nex)})
    if o<=stop:transact('SELL',o,'stoploss','open_gap')
    elif o>=tar:transact('SELL',o,'roi','open_gap')
    elif sh:transact('SELL',stop,'stoploss','intrabar_unknown')
    elif rh:transact('SELL',tar,'roi','intrabar_unknown')
  else:
   if not q and en and not ex:pending={'order_id':len(orders)+1,'side':'BUY','limit':o if hold else D(rows[j]['close']),'signal':None if hold else j,'status':'open','bar_index':i,'placed_utc':iso(eff),'timeout_utc':iso(nex),'tif':'gtc'}
   elif q and ex and not en:pending={'order_id':len(orders)+1,'side':'SELL','limit':D(rows[j]['close']),'signal':j,'status':'open','bar_index':i,'placed_utc':iso(eff),'timeout_utc':iso(nex),'tif':'gtc'}
   if pending:orders.append(pending)
   if pending and pending['side']=='BUY' and o<=pending['limit']:transact('BUY',o,'buy_hold' if hold else 'entry_signal','open',None if hold else pending['limit'])
   if q and not hold:
    elapsed=max(0,(eff-origin)//60000);key=max(k for k in roitable if k<=elapsed);roi=roitable[key];nsup+=int(suppress)
    for minute in roitable:
     bt=origin+minute*60000
     if minute>0 and eff<bt<nex:boundary.append({'bar_index':i,'boundary_utc':iso(bt),'minute':minute,'deferred_to_utc':iso(nex)})
    risks.append({'bar_index':i,'event':'open_state','entry':entry,'stop':stop,'trailing_active':active,'peak':peak,'roi_step':key,'roi':roi,'roi_suppressed':suppress,'age_origin_utc':iso(origin),'effective_utc':iso(eff)})
    if o<=stop:transact('SELL',o,'trailing_stop' if active else 'stoploss','open')
    elif pending and pending['side']=='SELL' and o>=pending['limit']:transact('SELL',o,'exit_signal','open',pending['limit'])
    elif not suppress and o>=target():transact('SELL',o,'roi','open',target())
    else:move_peak(o,'open')
   if not hold:
    points=[o,l,h,c]
    for seg in range(3):
     a,b=points[seg:seg+2];phase=['open_to_low','low_to_high','high_to_close'][seg]
     if q==0 and pending and pending['side']=='BUY' and not exited and b<=pending['limit']<=a:
      a=pending['limit'];transact('BUY',a,'entry_signal',phase,a)
     if not q:continue
     if b<a:
      if b<=stop<=a:transact('SELL',stop,'trailing_stop' if active else 'stoploss',phase)
     else:
      crosses=[]
      if pending and pending['side']=='SELL' and a<=pending['limit']<=b:crosses.append((pending['limit'],0,'exit_signal'))
      if not suppress and a<=target()<=b:crosses.append((target(),1,'roi'))
      if crosses:
       price,_,reason=min(crosses);move_peak(price,phase);transact('SELL',price,reason,phase,price)
      else:move_peak(b,phase)
   if pending:pending['status']='timeout_unfilled';pending['resolved_phase']='next_effective_open';pending=None
  equity=cash+q*c
  nav.append({'bar_index':i,'cash':cash,'quantity':q,'close':c,'equity':equity,'nav':equity/initial})
 daily=nav[5::6];eq=[initial]+[x['equity'] for x in nav];dq=[initial]+[x['equity'] for x in daily]
 def sh(xs,sc):
  rets=[float(b/a-1) for a,b in zip(xs,xs[1:])];st=statistics.stdev(rets);return statistics.mean(rets)/st*math.sqrt(sc) if st else None
 peakv=initial;mdd=D(0)
 for x in eq:peakv=max(peakv,x);mdd=max(mdd,1-x/peakv)
 m={'total_return':eq[-1]/initial-1,'annualized_return':float(eq[-1]/initial)**(365/731)-1,'max_drawdown':mdd,'sharpe_daily':sh(dq,365),'sharpe_4h':sh(eq,2190),'final_equity':eq[-1],'final_cash':cash,'final_quantity':q,'fill_events':len(events),'completed_roundtrips':len(wins),'winning_roundtrip_fraction':sum(x>0 for x in wins)/len(wins) if wins else None,'fees_paid':fees,'position_bar_fraction':sum(x['quantity']>0 for x in nav)/len(nav),'observations':len(nav),'daily_observations':len(daily)}
 if sid=='M0317':m.update(both_stop_roi_touched=both,unresolved_stop_roi_samebar=ambig,roi_boundary_candidate_bars=len(boundary),exit_signal_count=sum(f['mab_exit'][i] for i in indices),entry_signal_count=sum(f['mab_entry'][i] for i in indices))
 else:m.update(orders=len(orders),timeout_orders=sum(x['status']=='timeout_unfilled' for x in orders),trailing_activations=nactive,roi_suppressed_position_bars=nsup)
 return events,nav,daily,m,orders,risks,boundary

def check_events(actual,expected,sid):
 assert len(actual)==len(expected),(len(actual),len(expected))
 for k,(a,e) in enumerate(zip(actual,expected)):
  for f in ['bar_index','side','reason','phase']:assert str(e[f])==a[f],(k,f,e[f],a[f])
  for f in ['reference_price','fill_price','quantity','notional','fee','cash_after','quantity_after']:close(e[f],a[f])
  assert a['signal_bar_index']==('' if e['signal_bar_index'] is None else str(float(e['signal_bar_index'])) ) or a['signal_bar_index']==('' if e['signal_bar_index'] is None else str(e['signal_bar_index'])),(k,'signal')
  for f,t in [('execution_earliest_utc',e['effective']),('execution_latest_utc',e['last'])]:assert ms(a[f])==t,(k,f)
  assert (not a['execution_time_utc']) if e['exact'] is None else ms(a['execution_time_utc'])==e['exact']
  if e['signal_bar_index'] is not None:assert ms(a['signal_close_utc'])<e['effective']
  assert not HS<=e['effective']<HR and not HS<=e['last']<HR
  if e['side']=='SELL' or sid=='M0316':
   close(e['roi_step_minutes'],a['roi_step_minutes']);close(e['roi_target'],a['roi_target'])
  if sid=='M0316':
   close(e['stop_level'],a['stop_level']);assert ms(a['entry_age_origin_utc'])==e['origin']
   if e['limit_price'] is not None:close(e['limit_price'],a['limit_price']);assert (e['fill_price']<=e['limit_price'] if e['side']=='BUY' else e['fill_price']>=e['limit_price'])
  else:assert ms(a['entry_time_utc'])==e['origin']

def check_nav(actual,expected):
 assert len(actual)==len(expected)
 maxerr=0
 for a,e in zip(actual,expected):
  assert int(a['bar_index'])==e['bar_index']
  for f in ['cash','quantity','close','equity','nav']:close(e[f],a[f]);maxerr=max(maxerr,float(abs(D(a[f])-e[f])))
 return maxerr

def deepcheck(actual,expected):
 assert len(actual)==len(expected),(len(actual),len(expected))
 for a,e in zip(actual,expected):
  for k,v in e.items():
   if isinstance(v,D):close(v,a[k])
   elif k.endswith('_utc'):assert ms(a[k])==ms(v),(k,a[k],v)
   else:assert v==a[k],(k,v,a[k])

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--spec',required=True);p.add_argument('--work',required=True);p.add_argument('--output',required=True);args=p.parse_args()
 sid='M0317';res=Path(args.work);INPUT=Path(args.input);spec_path=Path(args.spec);spec=json.loads(spec_path.read_text());rows=list(csv.DictReader(INPUT.open()));f=features(rows);summary=json.loads((res/'summary.json').read_text());cases=[]
 for i in range(30):f['hlhb_entry'][i]=f['hlhb_exit'][i]=False
 assert sha(spec_path)==summary['protocol_sha256'];assert summary['strict_reproductions']==0 and summary['fidelity_class']=='HYPOTHESIS' and summary['data_quality_status']=='DIAGNOSTIC_ONLY'
 sf=list(csv.DictReader((res/'signals.csv').open()));assert len(sf)==len(rows)
 for i,a in enumerate(sf):
  assert int(a['open_time'])==int(rows[i]['open_time'])
  for k in (['rsi','ema5','ema10','adx','hl2'] if sid=='M0316' else ['sma7','sma14','sma28']):
   if f[k][i] is None:assert not a[k]
   else:close(f[k][i],a[k])
  for ak,fk in [('entry_signal','hlhb_entry' if sid=='M0316' else 'mab_entry'),('exit_signal','hlhb_exit' if sid=='M0316' else 'mab_exit')]:assert (a[ak]=='True')==f[fk][i]
 for case in spec['cases']:
  name=case['name'];ev,n,d,m,orders,risk,bt=oracle(sid,rows,f,spec,case);actual=list(csv.DictReader((res/f'{name}-trades.csv').open()));check_events(actual,ev,sid);err=check_nav(list(csv.DictReader((res/f'{name}-nav.csv').open())),n);check_nav(list(csv.DictReader((res/f'{name}-daily-nav.csv').open())),d)
  for k,v in m.items():
   a=summary['results'][name]['metrics'][k]
   if v is None:assert a is None
   else:close(v,a)
  if sid=='M0316':
   es=json.loads((res/f'{name}-events.json').read_text());deepcheck(es['orders'],orders);deepcheck(es['risk'],risk);deepcheck(es['roi_boundaries'],bt)
  else:deepcheck(json.loads((res/f'{name}-roi-boundaries.json').read_text()),bt)
  cases.append({'name':name,'status':'PASS_ALL_LEDGER_NAV_RISK_METRICS','fill_events':len(ev),'nav_rows':len(n),'daily_rows':len(d),'max_abs_account_difference':err,'orders':len(orders),'risk_events':len(risk),'roi_boundary_candidates':len(bt),'total_return':float(m['total_return']),'max_drawdown':float(m['max_drawdown'])})
 out={'status':'PASS_INDEPENDENT_DECIMAL_ALL_CASE_EXECUTION_AND_METRICS','id':sid,'at_utc':datetime.now(timezone.utc).isoformat(),'protocol_sha256':sha(spec_path),'summary_sha256':sha(res/'summary.json'),'auditor_sha256':sha(__file__),'indicator_oracle_sha256':sha(Path(__file__).with_name('independent_indicators.py')),'engine_imported':False,'market_requests':0,'input_sha256':sha(INPUT),'cases':cases,'strict_reproductions':0,'fidelity_class':'HYPOTHESIS','data_quality_status':'DIAGNOSTIC_ONLY','remaining':['synthetic branch coverage review','recovery and execution prefixes','public/private final manifests']}
 with Path(args.output).open('x') as o: o.write(json.dumps(out,indent=2)+'\n')
 print(json.dumps(out,indent=2))
