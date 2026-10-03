"""Prehistory artificial-only feature/account/calendar boundary suite."""
import argparse,json
from decimal import Decimal as D,localcontext
from pathlib import Path
from kernel_loader import FAMILY,load
from signals import features
from oracle import verify_features
engine=load('engine');account_qa=load('verify_account');DAY=86400000

def bars(prices):
    return [dict(open_time=str(1672531200000+i*DAY),close_time=str(1672531200000+(i+1)*DAY-1),open=str(p),high=str(p),low=str(p),close=str(p),volume='0',trade_count='0') for i,p in enumerate(prices)]
def forced(n,signals):
    f=features(bars([100]*n))
    for i,x in enumerate(f):x['raw_entry']=int(signals.get(i)=='BUY');x['raw_exit']=int(signals.get(i)=='SELL')
    return f

def check(fixture_dir):
    engine.environment(FAMILY/'specs/environment-lock.json');spec=json.loads((FAMILY/'specs/protocol-v1.json').read_text());tests=[]
    def passed(label):tests.append(label)
    cases=spec['cases'];ident=spec['id']
    sequences=[[p]*120 for p in ['0.1','0.3','1','10','100','1e-100','1e100']]+[list(range(1,121)),list(range(120,0,-1)),[100+i%2 for i in range(120)],[100+((i*7)%19) for i in range(120)]]
    for k,prices in enumerate(sequences):
        rows=bars(prices);f=features(rows);verify_features(rows,f)
        passed('Independent rational features sequence '+str(k))
        for cut in [3,4,19,20,21,65]:
            assert features(rows[:cut])==f[:cut]
            changed=[dict(x) for x in rows]
            for x in changed[cut:]:
                for key in ['open','high','low','close']:x[key]='1234'
            assert features(changed)[:cut]==f[:cut]
        passed('Prefix and future mutation sequence '+str(k))
        if k<7:
            for case in cases:assert not engine.simulate(rows,f,case,start=0)['fills']
    for cash in [D(100000),D('1e-100'),D('1e-400')]:
        for rate in [0,8,20]:
            cash_after,qty,a=engine.fill_order(cash,D(0),'101','BUY',rate,2)
            with localcontext() as ctx:
                ctx.prec=50
                assert cash_after==0 and D(a['notional'])+D(a['fee'])==cash and qty>0
                assert D(a['notional'])==cash/(1+D(rate)/10000)
                c,q,_=engine.fill_order(cash_after,qty,'101','SELL',rate,2);assert c>0 and q==0
            passed('Full fee-inclusive Decimal budget '+str(cash)+' fee'+str(rate))
    for held,side,entry,exit_ in [(False,'BUY',False,True),(True,'SELL',True,False)]:
        p,e=engine.reconcile(dict(side=side,signal_index=0,due_index=2),entry,exit_,held,1,2)
        assert p is None and e[0]['event']=='CANCELLED_OPPOSITE'
        passed('Cancel opposite before eligibility '+side)
    for held,side,entry,exit_ in [(False,'BUY',True,False),(True,'SELL',False,True)]:
        p=dict(side=side,signal_index=0,due_index=2);q,e=engine.reconcile(p,entry,exit_,held,1,2)
        assert q==p and e[0]['event']=='RETAINED_EARLIEST'
        absent,event=engine.reconcile(p,False,False,held,1,2);assert absent==p and event==[]
        passed('Repeat earliest and absent retention '+side)
    p,e=engine.reconcile(dict(side='BUY',signal_index=0,due_index=2),True,True,False,1,2);assert p is None
    passed('Both signals cancel BUY and prohibit flat reentry')
    original=dict(side='SELL',signal_index=0,due_index=2);p,e=engine.reconcile(original,True,True,True,1,2);assert p==original and e[0]['event']=='RETAINED_EARLIEST'
    passed('Both signals exit priority retains earlier SELL')
    rows=bars([100]*6);f=forced(6,{0:'BUY',1:'SELL',3:'BUY'});a=engine.simulate(rows,f,cases[-1],start=0)
    assert [(x['side'],x['eval_index']) for x in a['fills']]==[('BUY',5)] and a['summary']['cancelled_intents']==1
    passed('Lag2 cancelled buy no fill, valid later entry')
    rows=bars([100]*6);f=forced(6,{0:'BUY',1:'BUY',2:'SELL',3:'BUY',4:'SELL'});a=engine.simulate(rows,f,cases[-1],start=0)
    assert [(x['side'],x['eval_index']) for x in a['fills']]==[('BUY',2)] and a['summary']['terminal_pending']==dict(side='SELL',signal_index=4,due_index=6)
    passed('Terminal pending no outside fill and no sameopen roundtrip')
    rows=bars([100]*35);f=forced(35,{30:'BUY',31:'BUY'});a=engine.simulate(rows,f,cases[0],start=31)
    assert a['fills'][0]['eval_index']==1 and not any(x['eval_index']==0 for x in a['fills'])
    passed('No warmup intent; firstevaluation close earliest nextopen')
    m=engine.metrics([{'equity':'100000'}]*10);assert m['total_return']==m['cagr']==m['max_drawdown']==0 and m['sharpe_zero_cash'] is None
    passed('Cash-only return and null zero-vol Sharpe')
    m=engine.metrics([{'equity':'90000'},{'equity':'100000'}]);assert abs(m['max_drawdown']+.1)<1e-14
    passed('Initial drawdown anchor preserved')
    for tiny in ['1e-20','1e-100','1e-400']:
        try:account_qa.close(0,D(tiny))
        except AssertionError:pass
        else:raise AssertionError('Tiny nonzero treated as zero')
    passed('Independent tolerance rejects tiny-to-zero')
    from signals import cross
    f=features(bars([100]*19+[200,100]));assert all(not x['ready'] for x in f[:19]) and f[19]['ready'] and not f[19]['raw_entry'];passed('EMA seed at19 no fabricated cross')
    assert D(f[19]['ema20'])==105;passed('Left-to-right20 seed')
    assert cross(D(100),D(100),D(101),D(100))==(True,False);passed('Previous equality permits upcross')
    assert cross(D(100),D(100),D(99),D(100))==(False,True);passed('Previous equality permits downcross')
    assert cross(D(99),D(100),D(100),D(100))==(False,False);passed('Current equality neutral')
    assert cross(D(101),D(100),D(102),D(100))==(False,False);passed('State above is not crossing')
    rows=bars(range(1,151));f=features(rows)
    assert not engine.simulate(rows,f,cases[0],start=100)['fills'];passed('Initial above remainsflat without new event')
    # Complete independent serialization/account validation on a 24month artificial calendar.
    prices=[str(100+((i*7)%19)) for i in range(831)];rows=bars(prices)
    for i,r in enumerate(rows):r['open_time']=str(1663891200000+i*DAY);r['close_time']=str(1663891200000+(i+1)*DAY-1)
    fullfeat=features(rows);fullexpected=verify_features(rows,fullfeat);rows=rows[69:];feat=fullfeat[69:];expected=fullexpected[69:];assert not fixture_dir.exists();fixture_dir.mkdir(parents=True)
    engine.csvout(fixture_dir/'features.csv',feat,list(feat[0]));summaries=[]
    for case in cases:
        a=engine.simulate(rows,feat,case);summaries.append(a['summary'])
        for name,columns in [('nav',engine.NAV),('fills',engine.FILL),('pending',engine.EVENT),('decisions',engine.DEC),('monthly',engine.MONTH),('roundtrips',engine.TRIP)]:engine.csvout(fixture_dir/f"{case['name']}-{name}.csv",a[name],columns)
        engine.dump(fixture_dir/f"{case['name']}-summary.json",a['summary'])
    engine.dump(fixture_dir/'summary.json',dict(cases=summaries,strategy_configurations=4,new_controls=0,strict_reproductions=0))
    engine.dump(fixture_dir/'manifest.json',[dict(path=p.name,bytes=p.stat().st_size,sha256=engine.sha(p)) for p in sorted(fixture_dir.iterdir())])
    receipt=account_qa.verify_account(rows,fixture_dir,spec,expected)
    passed('Independent full synthetic 2924NAV/decisions/96months/account/metrics')
    return dict(status='PASS',id=ident,checks=len(tests),tests=tests,independent_synthetic_account=receipt,synthetic_only=True,new_history_runs=0,new_controls=0,market_requests=0,independent_external_review='PENDING_ROOT_ASSIGNMENT')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--fixture-dir',type=Path,required=True);a=p.parse_args();r=check(a.fixture_dir);engine.dump(a.output,r);print(json.dumps(r))
