"""M1258 only: catalog RSI5 hypothesis. No downloads or previous strategy runner."""
import argparse,csv,hashlib,importlib.metadata,json,os,sys
from datetime import datetime,timezone
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN
from pathlib import Path
import numpy as np
FAMILY=Path(__file__).resolve().parents[1]
DAY=86400000
COLS=['open_time','open','high','low','close','volume','close_time','quote_volume','trade_count','taker_base','taker_quote','ignore']
def dump(path,obj):
    with Path(path).open('x') as h:json.dump(obj,h,ensure_ascii=False,indent=2,allow_nan=False);h.write('\n')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def csvout(path,records,columns):
    with Path(path).open('x',newline='') as h:
        w=csv.DictWriter(h,fieldnames=columns);w.writeheader();w.writerows(records)
def iso(ms):return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat().replace('+00:00','Z')
def environment():
    lock=json.loads((FAMILY/'specs/environment-lock.json').read_text())
    assert sys.version==lock['python'],sys.version
    for k,v in lock['packages'].items():assert importlib.metadata.version(k)==v,k
    for k,v in lock['threads'].items():assert os.environ.get(k)==v,k

def load_input(path,protocol):
    data=Path(path).read_bytes();s=protocol['input']
    assert len(data)==s['bytes'] and hashlib.sha256(data).hexdigest()==s['sha256']
    with Path(path).open(newline='') as h:
        r=csv.DictReader(h);assert r.fieldnames==COLS;rows=list(r)
    assert len(rows)==762
    start=1669852800000
    for i,r in enumerate(rows):
        assert int(r['open_time'])==start+i*DAY and int(r['close_time'])==start+(i+1)*DAY-1
        for k in ['open','high','low','close']:assert D(r[k]).is_finite() and D(r[k])>0
        for k in ['volume','quote_volume','taker_base','taker_quote']:assert D(r[k]).is_finite() and D(r[k])>=0
        assert D(r['trade_count'])==int(r['trade_count']) and int(r['trade_count'])>=0
        assert D(r['low'])<=min(D(r['open']),D(r['close']))<=max(D(r['open']),D(r['close']))<=D(r['high'])
    assert int(rows[31]['open_time'])==protocol['evaluation_start_ms']
    assert int(rows[-1]['open_time'])+DAY==protocol['evaluation_end_ms']
    return rows

def features(rows):
    out=[];gains=[];losses=[];ag=al=None;prev=None;prev_rsi=None
    with localcontext() as c:
        c.prec=50;c.rounding=ROUND_HALF_EVEN
        for i,r in enumerate(rows):
            price=D(r['close']);rsi=None
            if prev is not None:
                delta=price-prev;g=max(delta,D(0));l=max(-delta,D(0))
                if i<=5:gains.append(g);losses.append(l)
                if i==5:ag=sum(gains,D(0))/D(5);al=sum(losses,D(0))/D(5)
                elif i>5:ag=ag+(g-ag)/D(5);al=al+(l-al)/D(5)
                if ag is not None:
                    if ag==0 and al==0:rsi=D(50)
                    elif al==0:rsi=D(100)
                    elif ag==0:rsi=D(0)
                    else:rsi=D(100)-D(100)/(D(1)+ag/al)
            entry=prev_rsi is not None and rsi is not None and prev_rsi<=50 and rsi>50
            exit_=prev_rsi is not None and rsi is not None and prev_rsi>=50 and rsi<50
            out.append(dict(input_index=i,open_time=r['open_time'],close_time=r['close_time'],close=r['close'],mean_gain='' if ag is None else str(ag),mean_loss='' if al is None else str(al),rsi='' if rsi is None else str(rsi),previous_rsi='' if prev_rsi is None else str(prev_rsi),ready=int(rsi is not None),raw_entry=int(entry),raw_exit=int(exit_)))
            prev=price;prev_rsi=rsi
    return out

def reconcile(pending,entry,exit_,held,index,delay):
    """Raw opposite cancellation first, then position eligibility; never postpone."""
    events=[]
    def add(event,p):events.append(dict(event=event,side=p['side'],signal_index=p['signal_index'],due_index=p['due_index']))
    if pending is not None and ((pending['side']=='BUY' and exit_) or (pending['side']=='SELL' and entry)):
        add('CANCELLED_OPPOSITE',pending);pending=None
    desired='SELL' if held and exit_ else 'BUY' if not held and entry and not exit_ else None
    if desired:
        if pending is not None:
            assert pending['side']==desired
            add('RETAINED_EARLIEST',pending)
        else:
            pending=dict(side=desired,signal_index=index,due_index=index+delay);add('QUEUED',pending)
    return pending,events

def fill_order(cash,qty,rawopen,side,fee_bps,slip_bps):
    with localcontext() as c:
        c.prec=50;c.rounding=ROUND_HALF_EVEN
        rate=D(fee_bps)/D(10000);slip=D(slip_bps)/D(10000)
        cb,qb=cash,qty
        if side=='BUY':
            assert qty==0 and cash>0
            fill=D(rawopen)*(D(1)+slip);notional=cash/(D(1)+rate);fee=cash-notional;qty=notional/fill;cash=D(0)
        else:
            assert side=='SELL' and qty>0
            fill=D(rawopen)*(D(1)-slip);notional=qty*fill;fee=notional*rate;cash=cash+notional-fee;qty=D(0)
        assert cash>=0 and qty>=0
        return cash,qty,dict(raw_open=str(rawopen),fill_price=str(fill),notional=str(notional),fee=str(fee),cash_before=str(cb),quantity_before=str(qb),cash_after=str(cash),quantity_after=str(qty))

def metrics(nav,initial=D(100000)):
    values=np.r_[float(initial),np.array([float(x['equity']) for x in nav],dtype=np.float64)]
    returns=values[1:]/values[:-1]-1;sd=returns.std(ddof=1)
    return dict(total_return=float(values[-1]/float(initial)-1),cagr=float((values[-1]/float(initial))**(365/len(nav))-1),max_drawdown=float(np.min(values/np.maximum.accumulate(values)-1)),sharpe_zero_cash=float(returns.mean()/sd*np.sqrt(365)) if sd>0 else None,observations=len(nav),final_equity=float(values[-1]))

NAV=['eval_index','input_index','open_time','mark_time','cash','quantity','raw_close','equity','pending_side','pending_signal_index','pending_due_index']
FILL=['fill_id','eval_index','input_index','effective_time','phase','side','signal_index','due_index','raw_open','fill_price','notional','fee','cash_before','quantity_before','cash_after','quantity_after']
EVENT=['event_id','eval_index','effective_time','phase','event','side','signal_index','due_index','held']
DEC=['eval_index','input_index','effective_time','rsi','previous_rsi','raw_entry','raw_exit','held','pending_before','pending_after','pending_due_index']
MONTH=['month','end_equity','return','days','days_long','buy_fills','sell_fills']
TRIP=['entry_fill_id','exit_fill_id','entry_index','exit_index','holding_bars','capital_before','capital_after','net_pnl','net_return']
def simulate(rows,feat,case,start=31,benchmark=False):
    cash=D(100000);qty=D(0);pending=None;nav=[];fills=[];events=[];decisions=[];trips=[];entryfill=None
    fee=case['fee_bps_each_side'];slip=case['slippage_bps_each_side'];delay=case['delay_bars']
    with localcontext() as c:
        c.prec=50;c.rounding=ROUND_HALF_EVEN
        for j,r in enumerate(rows[start:]):
            i=start+j;op=int(r['open_time']);cl=op+DAY;f=feat[i]
            if benchmark and j==0:pending=dict(side='BUY',signal_index=-1,due_index=0)
            if pending is not None and pending['due_index']<=j:
                p=pending;pending=None;eligible=(p['side']=='BUY' and qty==0) or(p['side']=='SELL' and qty>0)
                events.append(dict(event_id=len(events),eval_index=j,effective_time=iso(op),phase='OPEN',event='FILLED' if eligible else 'STALE_DISCARDED',held=int(qty>0),**p))
                if eligible:
                    cash,qty,a=fill_order(cash,qty,r['open'],p['side'],fee,slip)
                    fill=dict(fill_id=len(fills),eval_index=j,input_index=i,effective_time=iso(op),phase='OPEN',**p,**a);fills.append(fill)
                    if p['side']=='BUY':entryfill=fill
                    else:
                        before=D(entryfill['cash_before']);after=cash
                        trips.append(dict(entry_fill_id=entryfill['fill_id'],exit_fill_id=fill['fill_id'],entry_index=entryfill['eval_index'],exit_index=j,holding_bars=j-entryfill['eval_index'],capital_before=str(before),capital_after=str(after),net_pnl=str(after-before),net_return=str(after/before-1)));entryfill=None
            prior='' if pending is None else pending['side']
            if not benchmark:
                pending,new_events=reconcile(pending,bool(f['raw_entry']),bool(f['raw_exit']),qty>0,j,delay)
                for e in new_events:events.append(dict(event_id=len(events),eval_index=j,effective_time=iso(cl),phase='CLOSE',held=int(qty>0),**e))
            decisions.append(dict(eval_index=j,input_index=i,effective_time=iso(cl),rsi=f['rsi'],previous_rsi=f['previous_rsi'],raw_entry=f['raw_entry'],raw_exit=f['raw_exit'],held=int(qty>0),pending_before=prior,pending_after='' if pending is None else pending['side'],pending_due_index='' if pending is None else pending['due_index']))
            nav.append(dict(eval_index=j,input_index=i,open_time=iso(op),mark_time=iso(cl),cash=str(cash),quantity=str(qty),raw_close=r['close'],equity=str(cash+qty*D(r['close'])),pending_side='' if pending is None else pending['side'],pending_signal_index='' if pending is None else pending['signal_index'],pending_due_index='' if pending is None else pending['due_index']))
        months=[];groups={}
        for x in nav:groups.setdefault(x['open_time'][:7],[]).append(x)
        previous=D(100000)
        for month,group in groups.items():
            end=D(group[-1]['equity']);mfill=[x for x in fills if x['effective_time'][:7]==month]
            months.append(dict(month=month,end_equity=str(end),**{'return':str(end/previous-1)},days=len(group),days_long=sum(D(x['quantity'])>0 for x in group),buy_fills=sum(x['side']=='BUY' for x in mfill),sell_fills=sum(x['side']=='SELL' for x in mfill)));previous=end
        summary=dict(case=case['name'],kind='CONTROL' if benchmark else 'STRATEGY',fee_bps=fee,slippage_bps=slip,delay_bars=delay,**metrics(nav),fills=len(fills),closed_roundtrips=len(trips),winning_roundtrips=sum(D(x['net_pnl'])>0 for x in trips),losing_roundtrips=sum(D(x['net_pnl'])<0 for x in trips),win_rate=sum(D(x['net_pnl'])>0 for x in trips)/len(trips) if trips else None,exposure_fraction=sum(D(x['quantity'])>0 for x in nav)/len(nav),total_fees=str(sum((D(x['fee']) for x in fills),D(0))),final_cash=str(cash),final_quantity=str(qty),queued_intents=sum(x['event']=='QUEUED' for x in events),cancelled_intents=sum(x['event']=='CANCELLED_OPPOSITE' for x in events),retained_intents=sum(x['event']=='RETAINED_EARLIEST' for x in events),stale_intents=sum(x['event']=='STALE_DISCARDED' for x in events),terminal_pending=pending,monthly_observations=len(months))
    return dict(nav=nav,fills=fills,pending=events,decisions=decisions,monthly=months,roundtrips=trips,summary=summary)

def run(input_path,out):
    environment();protocol=json.loads((FAMILY/'specs/protocol-v1.json').read_text());rows=load_input(input_path,protocol)
    assert not out.exists();out.mkdir(parents=True)
    feat=features(rows);csvout(out/'features.csv',feat,list(feat[0]));summaries=[]
    for case in protocol['cases']+[protocol['benchmark']]:
        result=simulate(rows,feat,case,benchmark=case['name']=='buyhold');prefix=case['name'];summaries.append(result['summary'])
        for name,columns in [('nav',NAV),('fills',FILL),('pending',EVENT),('decisions',DEC),('monthly',MONTH),('roundtrips',TRIP)]:csvout(out/f'{prefix}-{name}.csv',result[name],columns)
        dump(out/f'{prefix}-summary.json',result['summary'])
    dump(out/'summary.json',{'id':'M1258','classification':'HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED','strict_reproductions':0,'strategy_configurations':4,'new_controls':1,'native_nav_equals_daily_nav':'*-nav.csv; native timeframe1d, no additional aggregation','cases':summaries})
    manifest=[dict(path=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(out.iterdir())]
    dump(out/'manifest.json',manifest)
    return {'status':'COMPLETE','payloads':len(manifest),'strategy_configurations':4,'new_controls':1,'historical_result_manifest_sha256':sha(out/'manifest.json')}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.input,a.output)))
