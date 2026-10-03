"""Frozen independent daily account verifier extracted from M1258 C0; no runner calls."""
import csv,hashlib,json,math,statistics
from datetime import datetime,timezone
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN
from pathlib import Path
DAY=86400000

def read(path):
    with path.open(newline='') as h:return list(csv.DictReader(h))
def stamp(ms):return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat().replace('+00:00','Z')
def close(actual,expected,rel=D('1e-42')):
    a,b=D(str(actual)),D(str(expected));assert a.is_finite() and b.is_finite()
    if b==0:assert a==0,(a,b)
    else:assert abs(a-b)<=abs(b)*rel,(a,b)
def verify_account(rows,out,spec,expected):
    all_summaries=[];fillcount=0
    with localcontext() as ctx:
        ctx.prec=50;ctx.rounding=ROUND_HALF_EVEN
        for case in spec['cases']:
            name=case['name'];control=False;fee=D(case['fee_bps_each_side'])/10000;slip=D(case['slippage_bps_each_side'])/10000;lag=case['delay_bars']
            nav=read(out/f'{name}-nav.csv');dec=read(out/f'{name}-decisions.csv');savedfill=read(out/f'{name}-fills.csv');savedpending=read(out/f'{name}-pending.csv');savedtrips=read(out/f'{name}-roundtrips.csv')
            assert len(nav)==len(dec)==731
            cash=D(100000);units=D(0);intent=None;fillpos=0;events=[];efills=[];trips=[];entry=None;monthgroups={};equities=[]
            def event(j,phase,kind,p):
                events.append(dict(event_id=len(events),eval_index=j,effective_time=stamp(int(rows[j+31]['open_time'])+(DAY if phase=='CLOSE' else 0)),phase=phase,event=kind,held=int(units>0),**p))
            for j,row in enumerate(rows[31:]):
                i=j+31;e=expected[i];openms=int(row['open_time']);a=nav[j];d=dec[j]
                if control and j==0:intent={'side':'BUY','signal_index':-1,'due_index':0}
                if intent and intent['due_index']<=j:
                    current=intent;intent=None
                    allowed=(current['side']=='BUY' and units==0) or(current['side']=='SELL' and units>0)
                    event(j,'OPEN','FILLED' if allowed else 'STALE_DISCARDED',current)
                    if allowed:
                        before_cash,before_qty=cash,units
                        price=D(row['open'])*(1+slip if current['side']=='BUY' else 1-slip)
                        if current['side']=='BUY':
                            principal=cash/(1+fee);commission=cash-principal;units=principal/price;cash=D(0)
                        else:
                            principal=units*price;commission=principal*fee;cash=cash+principal-commission;units=D(0)
                        assert cash>=0 and units>=0
                        f=dict(fill_id=fillpos,eval_index=j,input_index=i,effective_time=stamp(openms),phase='OPEN',**current,raw_open=row['open'],fill_price=str(price),notional=str(principal),fee=str(commission),cash_before=str(before_cash),quantity_before=str(before_qty),cash_after=str(cash),quantity_after=str(units))
                        assert fillpos<len(savedfill)
                        for k,v in f.items():assert savedfill[fillpos][k]==str(v),(name,'fill',j,k,savedfill[fillpos][k],v)
                        efills.append(f);fillpos+=1
                        if current['side']=='BUY':entry=f
                        else:
                            start=D(entry['cash_before']);t=dict(entry_fill_id=entry['fill_id'],exit_fill_id=f['fill_id'],entry_index=entry['eval_index'],exit_index=j,holding_bars=j-entry['eval_index'],capital_before=str(start),capital_after=str(cash),net_pnl=str(cash-start),net_return=str(cash/start-1));trips.append(t);entry=None
                before='' if intent is None else intent['side']
                if not control:
                    if intent and ((intent['side']=='BUY' and e['exit']) or(intent['side']=='SELL' and e['entry'] and not e['exit'])):
                        event(j,'CLOSE','CANCELLED_OPPOSITE',intent);intent=None
                    target=None
                    if units>0 and e['exit']:target='SELL'
                    elif units==0 and e['entry'] and not e['exit']:target='BUY'
                    if target:
                        if intent:
                            assert intent['side']==target;event(j,'CLOSE','RETAINED_EARLIEST',intent)
                        else:
                            intent={'side':target,'signal_index':j,'due_index':j+lag};event(j,'CLOSE','QUEUED',intent)
                equity=cash+units*D(row['close']);equities.append(float(equity))
                n=dict(eval_index=j,input_index=i,open_time=stamp(openms),mark_time=stamp(openms+DAY),cash=str(cash),quantity=str(units),raw_close=row['close'],equity=str(equity),pending_side='' if intent is None else intent['side'],pending_signal_index='' if intent is None else intent['signal_index'],pending_due_index='' if intent is None else intent['due_index'])
                for k,v in n.items():assert a[k]==str(v),(name,'nav',j,k)
                decision=dict(eval_index=j,input_index=i,effective_time=stamp(openms+DAY),raw_entry=int(e['entry']),raw_exit=int(e['exit']),held=int(units>0),pending_before=before,pending_after='' if intent is None else intent['side'],pending_due_index='' if intent is None else intent['due_index'])
                for k,v in decision.items():assert d[k]==str(v),(name,'decision',j,k)
                monthgroups.setdefault(stamp(openms)[:7],[]).append(a)
            assert fillpos==len(savedfill);fillcount+=fillpos
            assert len(events)==len(savedpending) and len(trips)==len(savedtrips)
            for records,save in [(events,savedpending),(trips,savedtrips)]:
                for expectedrow,savedrow in zip(records,save):
                    assert {k:str(v) for k,v in expectedrow.items()}==savedrow
            last=D(100000);months=[]
            for month,group in monthgroups.items():
                end=D(group[-1]['equity']);f=[x for x in efills if x['effective_time'][:7]==month]
                m=dict(month=month,end_equity=str(end),**{'return':str(end/last-1)},days=len(group),days_long=sum(D(x['quantity'])>0 for x in group),buy_fills=sum(x['side']=='BUY' for x in f),sell_fills=sum(x['side']=='SELL' for x in f));months.append({k:str(v) for k,v in m.items()});last=end
            assert months==read(out/f'{name}-monthly.csv') and len(months)==24
            s=json.loads((out/f'{name}-summary.json').read_text());all_summaries.append(s)
            rets=[v/p-1 for p,v in zip([100000.]+equities[:-1],equities)];peak=100000.;drawdown=0.
            for v in equities:peak=max(peak,v);drawdown=min(drawdown,v/peak-1)
            sd=statistics.stdev(rets);metric=dict(total_return=equities[-1]/100000-1,cagr=(equities[-1]/100000)**(365/731)-1,max_drawdown=drawdown,sharpe_zero_cash=statistics.mean(rets)/sd*math.sqrt(365) if sd>0 else None,final_equity=equities[-1])
            for k,v in metric.items():
                if v is None:assert s[k] is None
                else:close(s[k],v,D('1e-12'))
            extra=dict(case=name,kind='CONTROL' if control else 'STRATEGY',fee_bps=int(fee*10000),slippage_bps=int(slip*10000),delay_bars=lag,observations=731,fills=len(efills),closed_roundtrips=len(trips),winning_roundtrips=sum(D(x['net_pnl'])>0 for x in trips),losing_roundtrips=sum(D(x['net_pnl'])<0 for x in trips),win_rate=sum(D(x['net_pnl'])>0 for x in trips)/len(trips) if trips else None,exposure_fraction=sum(D(x['quantity'])>0 for x in nav)/731,total_fees=str(sum((D(x['fee']) for x in efills),D(0))),final_cash=str(cash),final_quantity=str(units),queued_intents=sum(x['event']=='QUEUED' for x in events),cancelled_intents=sum(x['event']=='CANCELLED_OPPOSITE' for x in events),retained_intents=sum(x['event']=='RETAINED_EARLIEST' for x in events),stale_intents=sum(x['event']=='STALE_DISCARDED' for x in events),terminal_pending=intent,monthly_observations=24)
            for k,v in extra.items():assert s[k]==v,(name,k,s[k],v)
    top=json.loads((out/'summary.json').read_text());assert top['cases']==all_summaries and top['strategy_configurations']==4 and top['new_controls']==0 and top['strict_reproductions']==0
    for f in json.loads((out/'manifest.json').read_text()):
        p=out/f['path'];assert len(p.read_bytes())==f['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256']
    return dict(status='PASS',features=762,nav_rows=2924,decision_rows=2924,monthly_rows=96,fill_rows=fillcount,strategy_configurations=4,new_control_configurations=0,source_signal='family independent Fraction features supplied and verified separately',account='independent Decimal50; exact serialized every fill/nav/event/monthly/roundtrip field',metrics='stdlib statistics independent from numpy,relative1e-12,zeroexact',engine_runs=0)
