"""Prehistory boundary tests; exclusively artificial prices, never real data."""
import argparse,json
from decimal import Decimal as D,localcontext
from pathlib import Path
from run_replay import features,simulate,fill_order,reconcile,metrics,environment,DAY,dump
from verify_replay import fraction_features,asdecimal,close

def bars(prices):
    return [dict(open_time=str(1672531200000+i*DAY),close_time=str(1672531200000+(i+1)*DAY-1),open=str(p),high=str(p),low=str(p),close=str(p),volume='0',trade_count='0') for i,p in enumerate(prices)]
def forced(n,signals):
    f=features(bars([100]*n))
    for i,x in enumerate(f):x['raw_entry']=int(signals.get(i)=='BUY');x['raw_exit']=int(signals.get(i)=='SELL')
    return f

def check():
    environment();tests=[]
    def passed(x):tests.append(x)
    cases=[dict(name=n,fee_bps_each_side=fee,slippage_bps_each_side=2,delay_bars=lag) for n,fee,lag in [('base',8,1),('fee0',0,1),('fee20',20,1),('delay2',8,2)]]
    sequences=[[p]*120 for p in ['0.1','0.3','1','10','100','1e-100','1e100']]+[list(range(1,121)),list(range(120,0,-1)),[100+i%2 for i in range(120)],[100+((i*7)%19) for i in range(120)]]
    for k,prices in enumerate(sequences):
        r=bars(prices);f=features(r);e=fraction_features(r)
        for a,b in zip(f,e):
            for key,other in [('mean_gain','gain'),('mean_loss','loss'),('rsi','rsi'),('previous_rsi','previous')]:
                if b[other] is None:assert a[key]==''
                else:close(a[key],asdecimal(b[other]))
            assert bool(a['raw_entry'])==b['entry'] and bool(a['raw_exit'])==b['exit']
        assert all(not x['ready'] for x in f[:5]) and f[5]['ready']
        if k<7:
            assert all(x['rsi']=='50' for x in f[5:])
            for case in cases:assert not simulate(r,f,case,start=0)['fills']
        passed('Fraction actual feature sequence '+str(k))
        for cut in [5,6,17,65]:
            assert features(r[:cut])==f[:cut]
            changed=r[:cut]+bars(['1234']*(len(r)-cut));assert features(changed)[:cut]==f[:cut]
        passed('prefix/future sequence '+str(k))
    f=features(bars([10,11,10,11,10,10,11,10]))
    assert f[5]['rsi']=='50' and f[6]['raw_entry']==1 and f[7]['raw_exit']==1
    passed('ready index5 flat50 equality and strict crosses')
    f=features(bars([1,2,3,4,5,6,7,8]));assert not any(x['raw_entry'] for x in f)
    passed('first ready above50 does not fabricate prior ready crossover')
    for held,side,entry,exit_ in [(False,'BUY',False,True),(True,'SELL',True,False)]:
        p,e=reconcile(dict(side=side,signal_index=0,due_index=2),entry,exit_,held,1,2)
        assert p is None and e[0]['event']=='CANCELLED_OPPOSITE'
    passed('opposite raw cancels while new order position-ineligible')
    for held,side,entry,exit_ in [(False,'BUY',True,False),(True,'SELL',False,True)]:
        p=dict(side=side,signal_index=0,due_index=2);q,e=reconcile(p,entry,exit_,held,1,2)
        assert q==p and e[0]['event']=='RETAINED_EARLIEST'
    passed('same side retains earliest due')
    p,e=reconcile(dict(side='BUY',signal_index=0,due_index=2),True,True,False,1,2);assert p is None
    passed('simultaneous raw signals cancel buy, no flat buy')
    r=bars([100]*6);f=forced(6,{0:'BUY',1:'SELL',3:'BUY'})
    result=simulate(r,f,cases[-1],start=0)
    assert [(x['side'],x['eval_index']) for x in result['fills']]==[('BUY',5)]
    assert result['summary']['cancelled_intents']==1
    passed('lag2 cancelled intent cannot fill; later valid buy due5')
    r=bars([100]*6);f=forced(6,{0:'BUY',1:'BUY',2:'SELL',3:'BUY',4:'SELL'})
    result=simulate(r,f,cases[-1],start=0)
    assert [(x['side'],x['eval_index']) for x in result['fills']]==[('BUY',2)]
    assert result['summary']['terminal_pending']==dict(side='SELL',signal_index=4,due_index=6)
    assert result['summary']['retained_intents']==1 and result['summary']['cancelled_intents']==1
    passed('lag2 actual holding plus opposite cancellation and outside-end pending')
    for cash in [D(100000),D('1e-100'),D('1e-400')]:
        for rate in [0,8,20]:
            c,q,a=fill_order(cash,D(0),'101','BUY',rate,2)
            with localcontext() as ctx:
                ctx.prec=50
                assert c==0 and D(a['notional'])+D(a['fee'])==cash and q>0
                assert D(a['notional'])==cash/(1+D(rate)/10000)
                cc,qq,s=fill_order(c,q,'101','SELL',rate,2)
                assert cc>0 and qq==0
            passed('full budget no epsilon '+str(cash)+' fee'+str(rate))
    r=bars([100]*35);f=forced(35,{30:'BUY',31:'BUY'})
    result=simulate(r,f,cases[0],start=31);assert result['fills'][0]['eval_index']==1
    assert not any(x['eval_index']==0 for x in result['fills'])
    passed('warmup signal not queued; evalclose firstorder nextopen')
    result=simulate(r,features(r),dict(name='buyhold',fee_bps_each_side=8,slippage_bps_each_side=2,delay_bars=0),start=31,benchmark=True)
    assert len(result['fills'])==1 and result['fills'][0]['eval_index']==0 and result['nav'][0]['cash']=='0'
    passed('new buyhold fullcash firstevaluationopen')
    m=metrics([{'equity':'100000'}]*10);assert m['total_return']==m['cagr']==m['max_drawdown']==0 and m['sharpe_zero_cash'] is None
    m=metrics([{'equity':'90000'},{'equity':'100000'}]);assert abs(m['max_drawdown']+.1)<1e-14
    passed('initial anchor and zero SD null')
    for tiny in ['1e-20','1e-100','1e-400']:
        try:close(0,D(tiny))
        except AssertionError:pass
        else:raise AssertionError('tiny accepted as zero')
    passed('oracle rejects tiny-to-zero')
    return dict(status='PASS',checks=len(tests),tests=tests,synthetic_only=True,history_runs=0,market_requests=0)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=check();dump(a.output,r);print(json.dumps(r))
