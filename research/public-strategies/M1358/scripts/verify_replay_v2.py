"""Independent Fraction features + Decimal account reconstruction: does not import runner or metrics."""
import argparse,csv,datetime,decimal,hashlib,json,math
from pathlib import Path
from fractions import Fraction
D=decimal.Decimal
decimal.getcontext().prec=50
DAY=86400000

def iso(ms):
    return datetime.datetime.fromtimestamp(ms/1000,datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def close(actual, expected):
    a=D(str(actual));b=D(expected.numerator)/D(expected.denominator) if isinstance(expected,Fraction) else D(str(expected))
    if b==0: assert a==0,(a,b)
    else: assert abs(a-b)<=abs(b)*D('1e-9'),(a,b)

def read(path):
    return list(csv.DictReader(path.open()))

def compare(got,want):
    assert len(got)==len(want),(len(got),len(want))
    for a,b in zip(got,want,strict=True):
        assert set(a)==set(b),(set(a),set(b))
        for k,v in b.items():
            if isinstance(v,(D,float,Fraction)):
                close(a[k],v)
            else: assert str(a[k])==str(v),(k,a[k],v)

def indicator(prices,n):
    out=[]
    for k,p in enumerate(prices):
        if k<n-1: v=Fraction(0)
        elif k==n-1:v=sum(prices[:n])/n
        else:v=(2*p+(n-1)*out[-1])/(n+1)
        out.append(v)
    return out

def metric(values,initial):
    path=[float(initial)]+[float(x) for x in values];r=[b/a-1 for a,b in zip(path,path[1:])]
    mean=math.fsum(r)/len(r);sd=math.sqrt(math.fsum((v-mean)**2 for v in r)/(len(r)-1)) if len(r)>1 else 0
    peak=path[0];draw=[]
    for v in path:peak=max(peak,v);draw.append(v/peak-1)
    return {'total_return':path[-1]/path[0]-1,'cagr':(path[-1]/path[0])**(365/len(values))-1,'max_drawdown':min(draw),'sharpe_zero_cash':mean/sd*math.sqrt(365) if sd else None,'observations':len(values),'final_equity':path[-1]}

def verify(input_path,out):
    allrows=read(input_path);rows=[r for r in allrows if int(r['open_time'])>=1672531200000]
    assert len(allrows)==762 and len(rows)==731
    prices=[D(r['close']) for r in rows];rational=[Fraction(r['close']) for r in rows];fast,slow=indicator(rational,13),indicator(rational,48)
    fs=[]
    for i,r in enumerate(rows):
        t=int(r['open_time']);fs.append({'bar_index':i,'date':iso(t)[:10],'close_time_utc':iso(t+DAY),'sample_count':i+1,'ema13':fast[i],'ema48':slow[i],'fast_ready':i>=12,'slow_ready':i>=47,'comparison':1 if fast[i]>slow[i] else -1 if fast[i]<slow[i] else 0})
    compare(read(out/'features.csv'),fs)
    summary=json.loads((out/'summary.json').read_text());report={}
    for name,rate,delay in [('base',D('.0008'),1),('fee0',D(0),1),('fee20',D('.002'),1),('lag2',D('.0008'),2)]:
        cash,quantity,peak=D(100000),D(0),D(100000)
        todo=[]; nav=[];fills=[];decisions=[];events=[]
        for i,r in enumerate(rows):
            t=int(r['open_time']);date=iso(t)[:10]
            due=[q for q in todo if q['due']==i];todo=[q for q in todo if q['due']!=i]
            for q in due:
                cb,qb=cash,quantity;side=q['side'];ok=(side=='BUY' and quantity==0) or (side=='SELL' and quantity>0)
                if ok:
                    p=D(r['open'])*(D('1.0002') if side=='BUY' else D('.9998'))
                    if side=='BUY':
                        amount=cash*D('.95');size=amount/p;fee=amount*rate;cash=cash-amount-fee;quantity=size
                    else:
                        size=quantity;amount=size*p;fee=amount*rate;cash=cash+amount-fee;quantity=D(0)
                    fills.append({'intent_id':q['id'],'bar_index':i,'date':date,'signal_bar_index':q['i'],'signal_date':q['date'],'signal_close_utc':q['time'],'execution_time_utc':iso(t),'phase':'OPEN','side':side,'quantity':size,'raw_open':D(r['open']),'price':p,'notional':amount,'fee':fee,'fee_currency':'USDT','cash_before':cb,'cash_after':cash,'position_before':qb,'position_after':quantity})
                events.append({'event':'FILLED' if ok else 'SKIPPED_STALE','intent_id':q['id'],'event_bar_index':i,'event_time_utc':iso(t),'signal_bar_index':q['i'],'due_bar_index':i,'due_time_utc':iso(t),'side':side,'reason':'due intent applied' if ok else 'BUY while long or SELL while flat'})
            equity=cash+quantity*prices[i];peak=max(peak,equity);ready=i>=47
            action=0
            if ready:
                if quantity==0 and fast[i]>slow[i]:action=1
                if quantity>0 and fast[i]<slow[i]:action=-1
            ident,di,dt='','',''
            if action:
                side='BUY' if action==1 else 'SELL';ident=f'{name}:{i}:{side}';di=i+delay;dt=iso(t+DAY*delay)
                todo.append({'id':ident,'i':i,'date':date,'time':iso(t+DAY),'due':di,'due_time':dt,'side':side,'action':action})
                events.append({'event':'QUEUED','intent_id':ident,'event_bar_index':i,'event_time_utc':iso(t+DAY),'signal_bar_index':i,'due_bar_index':di,'due_time_utc':dt,'side':side,'reason':'source state gate'})
            decisions.append({'bar_index':i,'date':date,'decision_time_utc':iso(t+DAY),'ready':ready,'ema13':fast[i],'ema48':slow[i],'holding_quantity':quantity,'action':action,'intent_id':ident,'due_bar_index':di,'due_time_utc':dt})
            nav.append({'bar_index':i,'date':date,'close_time_utc':iso(t+DAY),'equity':equity,'cash':cash,'quantity':quantity,'raw_close':prices[i],'drawdown':equity/peak-1,'ready':ready,'signal':action,'pending_count':len(todo)})
        for kind,want in [('nav',nav),('fills',fills),('decisions',decisions),('pending',events)]:compare(read(out/f'{name}-{kind}.csv'),want)
        terminal=[{'due_bar_index':q['due'],'id':q['id'],'action':q['action'],'signal_index':q['i'],'signal_date':q['date'],'decision_time':q['time'],'due_time':q['due_time']} for q in sorted(todo,key=lambda q:q['due'])]
        assert json.loads((out/f'{name}-terminal-pending.json').read_text())==terminal
        expected=metric([r['equity'] for r in nav],D(100000))
        for k,v in expected.items():
            if v is None:assert summary[name]['metrics'][k] is None
            elif k=='observations':assert summary[name]['metrics'][k]==v
            else:close(summary[name]['metrics'][k],v)
        for year,start,end in [('2023',0,365),('2024',365,731)]:
            m=metric([r['equity'] for r in nav[start:end]],D(100000) if start==0 else nav[start-1]['equity'])
            for k,v in m.items():
                if v is None:assert summary[name]['periods'][year][k] is None
                else:close(summary[name]['periods'][year][k],v)
        assert summary[name]['fills']==len(fills)
        assert summary[name]['completed_round_trips']==sum(f['side']=='SELL' for f in fills)
        assert summary[name]['skipped_stale_intents']==sum(e['event']=='SKIPPED_STALE' for e in events)
        assert all(n['cash']==100000 and n['quantity']==0 for n in nav[:48])
        close(summary[name]['terminal_cash'],cash);close(summary[name]['terminal_quantity'],quantity)
        report[name]={'status':'PASS','nav_rows':len(nav),'fills':len(fills),'decisions':len(decisions),'pending_events':len(events),'all_event_fields_checked':True}
    return {'status':'PASS','features':len(fs),'cases':report,'tolerance':'expected zero exact; otherwise Decimal rel1e-9 abs0','source_signals':'exact Fraction SMA seed and rational recurrence; all comparisons equal','metrics':'independent fsum/population path with sample return std','no_engine_import':True}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--results',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();r=verify(a.input,a.results)
    with a.report.open('x') as h:h.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r))
