"""Synthetic-only implementation gate. Never opens market input."""
import argparse,hashlib,json,math,time,resource
from pathlib import Path
import pandas as pd
from run_replay_v2 import features,run,source_action,DAY
from verify_replay import close
from decimal import Decimal as D

def frame(n,prices=None):
    p=prices or [100.+i for i in range(n)]
    return pd.DataFrame({'open_time':[1672531200000+i*DAY for i in range(n)],'open':p,'close':p})
def test():
    checks=[]
    def ok(n,c):assert c,n;checks.append(n)
    for qty in (0,1):
        ok(f'unready_{qty}',source_action(False,qty,2,1)==0)
        ok(f'equality_{qty}',source_action(True,qty,1,1)==0)
    ok('state_no_cross_entry',source_action(True,0,2,1)==1)
    ok('state_no_cross_exit',source_action(True,1,1,2)==-1)
    ok('no_short',source_action(True,0,1,2)==0)
    f=frame(60);fs=features(f)
    ok('EMA48_seed',fs[47]['ema48']==sum(D(str(x)) for x in f.close[:48])/48 and all(not x['slow_ready'] for x in fs[:47]))
    ok('EMA13_seed',fs[12]['ema13']==sum(D(str(x)) for x in f.close[:13])/13)
    for fee in (0,8,20):
        for lag in (1,2):
            r=run(f,fee,lag);fill=r['fills'][0]
            ok(f'first_fill_{fee}_{lag}',fill['bar_index']==47+lag)
            close(fill['notional'],D(95000));close(fill['fee'],D(95000)*D(fee)/10000)
            ok(f'cash_budget_{fee}_{lag}',fill['cash_after']==100000-95000-95000*fee/10000)
            ok(f'first48_cash_{fee}_{lag}',all(n['quantity']==0 and n['cash']==100000 for n in r['nav'][:48]))
            if lag==2:ok(f'duplicate_skip_{fee}',sum(e['event']=='SKIPPED_STALE' for e in r['pending'])==1)
    # Handcrafted feature rows isolate queue semantics from indicator implementation.
    z=frame(6,[100]*6);ff=features(z)
    for i,x in enumerate(ff):x.update(slow_ready=True,ema13=2 if i<2 else 0,ema48=1)
    r=run(z,8,2,feature_rows=ff)
    ok('no_cancel_opposite',[(x['bar_index'],x['side']) for x in r['fills']]==[(2,'BUY'),(4,'SELL')])
    ok('stale_buy_and_sell_skip',[(x['event_bar_index'],x['side']) for x in r['pending'] if x['event']=='SKIPPED_STALE']==[(3,'BUY'),(5,'SELL')])
    z=frame(48);r=run(z,8,1)
    ok('endwindow_intent_retained',len(r['fills'])==0 and len(r['terminal_pending'])==1)
    ok('48th_decision_date',r['decisions'][47]['decision_time_utc']=='2023-02-18T00:00:00Z')
    for k in (12,47,48,49,55):
        full=run(f,8,2);prefix=run(f.iloc[:k],8,2)
        ok(f'prefix_nav_{k}',prefix['nav']==full['nav'][:k])
        ok(f'prefix_features_{k}',features(f.iloc[:k])==fs[:k])
    pert=f.copy();pert.loc[55:,'close']=99999
    ok('future_perturbation',run(pert,8,2)['nav'][:55]==run(f,8,2)['nav'][:55])
    for a,b in [('1e-400','0'),('0','1e-400')]:
        try:close(a,b)
        except AssertionError:checks.append('tiny_zero_rejected_'+a+'_'+b)
        else:raise AssertionError('zero tolerance')
    # Entire feature + account path must preserve a constant series exactly.
    from fractions import Fraction
    for constant in ('0.1','0.3','10','100'):
        cframe=frame(120,[float(constant)]*120);cff=features(cframe)
        ok('constant_equal_'+constant,all(x['ema13']==x['ema48']==D(constant) for x in cff[47:]))
        for fee,lag in ((8,1),(0,1),(20,1),(8,2)):
            rr=run(cframe,fee,lag)
            ok(f'constant_no_orders_{constant}_{fee}_{lag}',not rr['fills'] and not rr['pending'] and all(x['equity']==100000 for x in rr['nav']))
    # Independent exact-rational synthetic EMA, not a second call to runner.
    values=[Fraction(str(100+(i%17)*0.3)) for i in range(160)]
    rf=frame(160,[float(x) for x in values]);rf['close_decimal']=[str(float(x)) for x in values]
    rfeatures=features(rf)
    rational={}
    for period in (13,48):
        a=[]
        for i,x in enumerate(values):
            value=Fraction(0) if i+1<period else sum(values[:period])/period if i+1==period else (2*x+(period-1)*a[-1])/(period+1)
            a.append(value)
        rational[period]=a
        for i,x in enumerate(a): close(rfeatures[i]['ema'+str(period)],D(x.numerator)/D(x.denominator))
    ok('rational_state_comparisons',all(rfeatures[i]['comparison']==(1 if rational[13][i]>rational[48][i] else -1 if rational[13][i]<rational[48][i] else 0) for i in range(160)))
    return {'status':'PASS','checks':checks,'count':len(checks),'historical_runs':0,'market_requests':0}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);a=p.parse_args();t=time.perf_counter();c=time.process_time();r=test();r.update(wall_seconds=time.perf_counter()-t,cpu_seconds=time.process_time()-c,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    with a.report.open('x') as h:h.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r))
