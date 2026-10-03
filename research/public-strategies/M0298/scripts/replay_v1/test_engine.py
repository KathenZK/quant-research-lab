#!/usr/bin/env python3
"""Authored synthetic engine fixtures; never loads market data."""
import json,resource,sys
from decimal import Decimal,localcontext
from pathlib import Path
import numpy as np
import pandas as pd
import replay as m

D=lambda x:Decimal(str(x))

def fixture(n=5):
    ts=m.START-m.STEP+np.arange(n,dtype=np.int64)*m.STEP
    d=pd.DataFrame({'open_time':ts,'open':np.full(n,100.),'high':np.full(n,100.),'low':np.full(n,100.),'close':np.full(n,100.)})
    s=pd.DataFrame({'enter_long':np.zeros(n,dtype=bool),'exit_long':np.zeros(n,dtype=bool)})
    return d,s

def setbar(d,i,o,h,l,c):d.loc[i,['open','high','low','close']]=[o,h,l,c]

def replay(d,s,fee=8,lag=1,bh=False):return m.simulate(d,s,fee,lag,bh,m.START,int(d.open_time.iloc[-1])+m.STEP)

def decimal_check(r,fee=8):
    """Test-side account reconstruction from sparse fills, not engine accounting."""
    with localcontext() as ctx:
        ctx.prec=50;cash=D(100000);qty=D(0);peak=cash;cost=D(fee)/10000+D('.0002');eventindex=0;maxerr=D(0)
        for row in r['curve'].itertuples():
            while eventindex<len(r['fills']) and r['fills'][eventindex]['bar_index']==row.bar_index:
                e=r['fills'][eventindex];price=D(e['fill_price'])
                if e['side']=='buy':
                    assert qty==0
                    budget=cash*D('.95');notional=budget/(1+cost);qty=notional/price;cash-=budget
                else:
                    assert qty>0
                    notional=qty*price;cash+=notional*(1-cost);qty=D(0)
                assert abs(D(e['fee'])-notional*D(fee)/10000)<D('0.0000001')
                assert abs(D(e['friction'])-notional*D('.0002'))<D('0.0000001')
                assert abs(D(e['cash_after'])-cash)<D('0.0000001')
                eventindex+=1
            value=cash+qty*D(row.close);peak=max(peak,value);dd=value/peak-1
            for actual,want in [(row.cash,cash),(row.quantity,qty),(row.equity,value),(row.drawdown,dd),(row.net_liquidation_equity,cash+qty*D(row.close)*(1-cost))]:
                err=abs(D(actual)-want);maxerr=max(maxerr,err);assert err<D('0.0000001'),(row.bar_index,actual,str(want))
        assert eventindex==len(r['fills'])
        return float(maxerr)

def run():
    outcomes=[]
    def check(name,d,s,expected_reason=None,fee=8,lag=1,bh=False):
        r=replay(d,s,fee,lag,bh)
        if expected_reason is not None:assert r['trades'][0]['exit_reason']==expected_reason,(name,r['trades'])
        err=decimal_check(r,fee);outcomes.append({'fixture':name,'bars':len(r['curve']),'fills':len(r['fills']),'orders':len(r['orders']),'Decimal_max_error':err})
        return r
    d,s=fixture();s.loc[0,'enter_long']=True;setbar(d,1,99,99,99,99)
    r=check('open_entry_price_improvement',d,s);assert r['fills'][0]['fill_price']==99
    d,s=fixture();s.loc[0,'enter_long']=True;setbar(d,1,101,150,100,101)
    r=check('intrabar_entry_suppresses_same_bar_ROI',d,s);assert len(r['fills'])==1 and r['fills'][0]['phase']=='intrabar'
    d,s=fixture();s.loc[0,'enter_long']=True;setbar(d,1,100,150,70,100)
    r=check('entry_open_stop_before_ROI',d,s,'stoploss');assert r['fills'][1]['fill_price']==75
    d,s=fixture();s.loc[0,'enter_long']=True;s.loc[1,'exit_long']=True;setbar(d,2,70,120,60,90)
    r=check('held_stop_gap_before_all_intrabar_exits',d,s,'stop_gap');assert r['fills'][1]['fill_price']==70
    d,s=fixture();s.loc[0,'enter_long']=True;s.loc[1,'exit_long']=True;setbar(d,2,110,115,50,100)
    r=check('open_signal_before_ROI_gap_and_future_stop',d,s,'exit_signal');assert r['fills'][1]['fill_price']==110
    d,s=fixture();s.loc[0,'enter_long']=True;setbar(d,2,110,115,50,100)
    r=check('known_ROI_gap_before_intrabar_stop',d,s,'roi_gap');assert r['fills'][1]['fill_price']==110
    d,s=fixture();s.loc[0,'enter_long']=True;s.loc[1,'exit_long']=True;setbar(d,1,100,101.1,99,101);setbar(d,2,100,110,74,100)
    check('intrabar_stop_before_signal_and_ROI',d,s,'stoploss')
    d,s=fixture();s.loc[0,'enter_long']=True;s.loc[1,'exit_long']=True;setbar(d,1,100,101.1,99,101);setbar(d,2,100,110,99,100)
    r=check('intrabar_signal_before_ROI',d,s,'exit_signal');assert r['fills'][1]['fill_price']==101
    d,s=fixture();s.loc[0,['enter_long','exit_long']]=True
    r=check('collision_suppresses_flat_entry',d,s);assert len(r['fills'])==0 and r['collision_signal_bars']==1
    d,s=fixture();s.loc[0,'enter_long']=True;s.loc[1,['enter_long','exit_long']]=True;setbar(d,2,100,102,99,100)
    r=check('collision_suppresses_signal_exit_but_ROI_remains',d,s,'roi');assert len(r['fills'])==2 and len(r['orders'])==1
    d,s=fixture();s.loc[0,'enter_long']=True;setbar(d,1,102,103,101,102);setbar(d,2,99,99,99,99)
    r=check('entry_timeout_no_carryover',d,s);assert len(r['fills'])==0 and len(r['orders'])==1 and r['orders'][0]['state']=='CANCELLED_TIMEOUT'
    d,s=fixture();s.loc[0,'enter_long']=True;s.loc[1,'exit_long']=True;setbar(d,1,100,101.1,99,101);setbar(d,2,100,100.5,99,100)
    r=check('exit_timeout_no_carryover_position_marked',d,s);assert len(r['fills'])==1 and r['orders'][-1]['state']=='CANCELLED_TIMEOUT'
    d,s=fixture();s.loc[0,'enter_long']=True;setbar(d,2,99,100,99,100)
    r=check('lag2_uses_original_signal_close',d,s,lag=2);assert r['fills'][0]['bar_index']==2 and r['fills'][0]['signal_index']==0
    d,s=fixture();s.loc[:,'exit_long']=True;setbar(d,1,100,200,10,100)
    r=check('buyhold_ignores_signals_ROI_and_stop',d,s,bh=True);assert len(r['fills'])==1 and r['open_position'] is not None
    for fee in (0,8,20):
        d,s=fixture();s.loc[0,'enter_long']=True;cost=fee/10000+m.FRICTION;target=100*(1+cost)*1.01/(1-cost);setbar(d,1,100,target,99,100)
        r=check('ROI_net1pct_fee_'+str(fee),d,s,'roi',fee=fee);assert abs(r['trades'][0]['return_on_budget']-.01)<1e-12
    d,s=fixture();s.loc[0,'enter_long']=True;setbar(d,1,101,150,74,100)
    r=check('intrabar_entry_can_stop_same_bar',d,s,'stoploss');assert r['fills'][0]['phase']=='intrabar'
    # Equity prefix conservation after arbitrary future OHLC/indicator changes.
    n=850;t=np.arange(n,dtype=float);cl=100+.008*t+2*np.sin(t/11)+np.cos(t/31)
    d=pd.DataFrame({'open_time':m.START-50*m.STEP+np.arange(n)*m.STEP,'open':cl,'high':cl*1.005,'low':cl*.995,'close':cl})
    s=m.indicators(cl);full=m.simulate(d,s,start=m.START,end=int(d.open_time.iloc[-1])+m.STEP)
    for cut in (200,500,750):
        pd_=d.iloc[:cut].copy();ps=m.indicators(pd_.close.to_numpy());pr=m.simulate(pd_,ps,start=m.START,end=int(pd_.open_time.iloc[-1])+m.STEP)
        pd.testing.assert_frame_equal(pr['curve'],full['curve'].iloc[:cut-50].reset_index(drop=True),check_exact=True)
        mutated=d.copy();mutated.loc[cut:,['open','high','low','close']]*=1.4;ms=m.indicators(mutated.close.to_numpy());mr=m.simulate(mutated,ms,start=m.START,end=int(mutated.open_time.iloc[-1])+m.STEP)
        pd.testing.assert_frame_equal(mr['curve'].iloc[:cut-50],full['curve'].iloc[:cut-50],check_exact=True)
    return {'status':'PASS_SYNTHETIC_ENGINE_ONLY','fixtures':outcomes,'causal_equity_prefixes':[200,500,750],'future_perturbations_pass':True,'historical_runs':0,'market_data_read':False,'execution_model':'declared diagnostic port; no original framework engine equivalence','peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}
if __name__=='__main__':
    m.verify_environment();out=run();assert out['peak_rss_bytes']<1024**3
    path=Path(sys.argv[1]);m.dump(path,out);print(json.dumps({'status':out['status'],'fixtures':len(out['fixtures']),'peak_rss_bytes':out['peak_rss_bytes']}))
