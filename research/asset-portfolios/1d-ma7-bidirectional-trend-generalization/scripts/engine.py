"""本家族单标的日线研究引擎；纯函数，不读取行情、配置或外部状态。"""
from dataclasses import dataclass, replace
import math
import numpy as np
import pandas as pd

@dataclass(frozen=True)
class Config:
    candidate: str = 'C1'
    fee: float = .001
    slip: float = .0004
    delay: int = 1
    size: float = 1.
    band: float = .25
    initial_atr: float = 2.
    trail_atr: float = 3.
    direction: int = 0
    filter_name: str = 'none'

CANDIDATES = tuple(f'B{i}' for i in range(4)) + tuple(f'C{i}' for i in range(6))
FILTERS = ('relative_strength','slow_trend','liquidity','volatility','persistence','maturity','low_er_short','liquid_short')
DAY = 86_400_000

def features(frame, btc=None):
    f = frame.reset_index(drop=True).copy()
    assert len(f) and f.ts.is_monotonic_increasing and not f.ts.duplicated().any()
    assert f.ts.diff().dropna().eq(pd.Timedelta(days=1)).all(), 'noncontinuous segment'
    assert f.eligible.all() and f.research_segment_id.nunique()==1
    c=f.close.to_numpy(float);h=f.high.to_numpy(float);l=f.low.to_numpy(float)
    assert np.isfinite(np.array([c,h,l,f.open])).all()
    assert (l<=f.open).all() and (l<=c).all() and (h>=f.open).all() and (h>=c).all() and (l>0).all()
    # Same summation and Wilder initialization as the immutable reference.
    ma=np.full(len(f),np.nan);atr=ma.copy();tr=[]
    # Python 3.12+ sum(float) uses compensated summation; summing numpy scalars
    # can change exact-equality cross decisions. Match the pinned reference.
    close_list=c.tolist();high_list=h.tolist();low_list=l.tolist()
    for i in range(len(f)):
        if i>=6:ma[i]=sum(close_list[i-6:i+1])/7
        tr.append(high_list[i]-low_list[i] if i==0 else max(high_list[i]-low_list[i],abs(high_list[i]-close_list[i-1]),abs(low_list[i]-close_list[i-1])))
        if i==13:atr[i]=sum(tr[:14])/14
        elif i>13:atr[i]=(atr[i-1]*13+tr[i])/14
    f['ma7']=ma;f['atr14']=atr
    f['ma30']=f.close.rolling(30).mean()
    f['slow_slope']=f.ma30-f.ma30.shift(7)
    f['ma7_delta2']=f.ma7-f.ma7.shift(2)
    f['momentum60']=f.close/f.close.shift(60)-1
    log=np.log(f.close)
    f['er30']=(log-log.shift(30)).abs()/log.diff().abs().rolling(30).sum()
    f['liquidity90']=f.quote_volume.rolling(90).median()
    f['atr_pct']=f.atr14/f.close
    f['age_days']=np.arange(len(f))+1
    f['btc_momentum60']=np.nan
    f['market_state']='UNKNOWN'
    if btc is not None:
        ref=btc.reindex(pd.DatetimeIndex(f.ts))
        f['btc_momentum60']=ref['momentum60'].to_numpy()
        f['market_state']=ref['market_state'].fillna('UNKNOWN').to_numpy()
    f['relative60']=f.momentum60-f.btc_momentum60
    return f

def filter_ok(f, i, side, name):
    if name=='none':return True
    if name=='relative_strength':return bool(side*f['relative60'][i]>0)
    if name=='slow_trend':return bool(side*(f['close'][i]-f['ma30'][i])>0 and side*f['slow_slope'][i]>0)
    if name in ('liquidity','liquid_short'):return bool(f['liquidity90'][i]>=1e7 and (name!='liquid_short' or side==-1))
    if name=='volatility':return bool(f['atr_pct'][i]<=.06)
    if name=='persistence':return bool(f['er30'][i]>=.25)
    if name=='maturity':return bool(f['age_days'][i]>=365)
    if name=='low_er_short':return bool(f['er30'][i]<.10 and side==-1)
    raise ValueError(name)

def signal(f, i, config, warmup):
    if i<max(14,warmup-1) or not f['research_window_valid'][i]:return 0,0
    c=f['close'];m=f['ma7'];a=f['atr14'];k=config.candidate
    raw=1 if c[i]>m[i] else -1 if c[i]<m[i] else 0
    if k.startswith('B'):
        sig=1 if c[i-1]<m[i-1] and c[i]>m[i] and m[i]>m[i-1] else -1 if c[i-1]>m[i-1] and c[i]<m[i] and m[i]<m[i-1] else 0
        return sig,sig
    if k=='C0':return raw,raw
    confirmed=0
    for side in [1,-1]:
        if (side*(c[i]-m[i])>config.band*a[i] and side*(c[i-1]-m[i-1])>config.band*a[i-1]
            and side*f['ma7_delta2'][i]>0):confirmed=side
    entry=confirmed
    if k in ('C3','C4','C5') and entry and not filter_ok(f,i,entry,'slow_trend'):entry=0
    return entry,confirmed

def replay(frame, config=Config(), *, start_idx=121, warmup=121, force_end=True):
    assert config.candidate in CANDIDATES and config.delay in (1,2)
    assert 0<config.size<=1 and config.fee>=0 and 0<=config.slip<1
    n=len(frame);assert n>start_idx
    f={k:frame[k].to_numpy() for k in frame.columns}
    nav=[];sides=[];stops=[];units_path=[];events=[];trades=[]
    cash=1.;pos=None;pending=None;bankrupt=False;last_exit=-100;rejected=0;eligible_days=0
    minimum=max(0,start_idx-1)

    def mark(price):
        return cash if pos is None else pos['equity_before']-pos['entry_fee']+pos['side']*pos['units']*(price-pos['entry_price'])

    def close(i, raw, reason, decision_idx=None):
        nonlocal pos,cash,bankrupt,last_exit
        s=pos['side'];u=pos['units'];fill=raw*(1-s*config.slip);fee=u*fill*config.fee
        uncapped=mark(fill)-fee
        bankrupt=uncapped<=0 or reason=='economic_bankruptcy'
        cash=0. if bankrupt else uncapped
        trade={**pos,'trade_id':len(trades)+1,'exit_idx':i,'exit_ts':str(f['ts'][i]),'exit_price':fill,
            'exit_raw_price':raw,'exit_fee':fee,'equity_after':cash,'uncapped_equity_after':uncapped,
            'ret_pct':100*(cash/pos['equity_before']-1),'reason':reason,'exit_decision_idx':decision_idx,
            'hold_days':i-pos['entry_idx'],'economic_bankruptcy':bankrupt,'stop_at_exit':pos['stop']}
        trades.append(trade);events.append({'i':i,'action':'exit','side':s,'price':fill,'reason':reason})
        pos=None;last_exit=i

    def enter(i, side, j, stop, reversal):
        nonlocal pos
        fill=f['open'][i]*(1+side*config.slip);u=config.size*cash/(fill*(1+config.fee))
        pos={'side':side,'entry_idx':i,'signal_idx':j,'entry_ts':str(f['ts'][i]),'signal_ts':str(f['ts'][j]),
            'entry_price':fill,'entry_raw_price':f['open'][i],'units':u,'equity_before':cash,
            'entry_fee':u*fill*config.fee,'stop':stop,'reversal_entry':reversal,'favorable_close':f['open'][i]}
        events.append({'i':i,'action':'entry','side':side,'signal_idx':j,'price':fill,'stop':stop,'reversal_entry':reversal})

    def barrier_check(i, intraday):
        if pos is None:return
        s=pos['side'];u=pos['units'];stop=pos['stop']
        zero_fill=(s*u*pos['entry_price']-pos['equity_before']+pos['entry_fee'])/(u*(s-config.fee))
        zero_raw=zero_fill/(1-s*config.slip)
        barrier=max(stop,zero_raw) if s==1 else min(stop,zero_raw)
        zero_first=s*(zero_raw-stop)>0
        if s*(f['open'][i]-barrier)<=0:close(i,f['open'][i],'gap_stop')
        elif intraday and (f['low'][i]<=barrier if s==1 else f['high'][i]>=barrier):
            close(i,barrier,'economic_bankruptcy' if zero_first else 'stop')

    for i in range(n):
        if i>=start_idx:
            barrier_check(i,False)
            if pending is not None and pending['due']==i:
                order=pending;pending=None
                if not bankrupt:
                    target=order['target']
                    if pos is not None and (target==0 or pos['side']!=target):
                        close(i,f['open'][i],order['reason'],order['signal_idx'])
                    if target and pos is None and not bankrupt:
                        enter(i,target,order['signal_idx'],order['stop'],order['reversal'])
            stops.append(pos['stop'] if pos else np.nan)
            sides.append(pos['side'] if pos else 0);units_path.append(pos['units'] if pos else 0.)
            barrier_check(i,True)
        else:
            stops.append(np.nan);sides.append(0);units_path.append(0.)
        if pos is not None:
            s=pos['side'];a=f['atr14'][i]
            if config.candidate.startswith('B'):
                st=f['ma7'][i]-s*1.5*a
                pos['stop']=max(pos['stop'],st) if s==1 else min(pos['stop'],st)
            if config.candidate in ('C4','C5'):
                pos['favorable_close']=max(pos['favorable_close'],f['close'][i]) if s==1 else min(pos['favorable_close'],f['close'][i])
                st=pos['favorable_close']-s*config.trail_atr*a
                pos['stop']=max(pos['stop'],st) if s==1 else min(pos['stop'],st)
        if i>=minimum and not bankrupt and pending is None:
            entry,opposite=signal(f,i,config,warmup)
            allowed=entry and (config.direction==0 or config.direction==entry)
            if config.candidate=='B0':allowed=allowed and entry==1
            if config.candidate=='B1':allowed=allowed and entry==-1
            if config.filter_name in ('low_er_short','liquid_short'):allowed=allowed and entry==-1
            filter_entry=bool(allowed and filter_ok(f,i,entry,config.filter_name))
            eligible_days+=int(filter_ok(f,i,entry or 1,config.filter_name) or filter_ok(f,i,-1,config.filter_name))
            if allowed and not filter_entry:rejected+=1
            target=None;reason='';reversal=False
            if pos is None:
                if filter_entry and (config.candidate!='C5' or i>last_exit):target=entry;reason='entry_signal'
            else:
                s=pos['side'];raw=1 if f['close'][i]>f['ma7'][i] else -1 if f['close'][i]<f['ma7'][i] else 0
                if not filter_ok(f,i,s,config.filter_name):target=0;reason='filter_exit'
                elif config.candidate=='C2' and raw==-s:
                    target=entry if filter_entry and entry==-s else 0;reason='reverse_signal' if target else 'raw_ma7_exit'
                elif config.candidate not in ('B0','B1','B2') and opposite==-s:
                    target=entry if filter_entry and config.candidate!='C5' else 0
                    reason='reverse_signal' if target else 'confirmed_exit'
                reversal=bool(target and target==-s)
            if target is not None:
                if target:
                    if config.candidate.startswith('B'):stop=f['ma7'][i]-target*1.5*f['atr14'][i]
                    elif config.candidate=='C0':stop=-np.inf if target==1 else np.inf
                    else:stop=f['close'][i]-target*config.initial_atr*f['atr14'][i]
                else:stop=np.nan
                pending={'due':i+config.delay,'target':target,'signal_idx':i,'stop':stop,'reason':reason,'reversal':reversal}
        if force_end and i==n-1 and pos is not None:close(i,f['close'][i],'end_of_test')
        value=mark(f['close'][i]);assert np.isfinite(value) and value>=0,(i,value)
        nav.append(value)
    actual=np.array(nav[start_idx:]);peaks=np.maximum.accumulate(np.r_[1.,actual])
    dd=float(np.max(1-np.r_[1.,actual]/peaks))*100
    natural=[t for t in trades if t['reason']!='end_of_test']
    metrics={'return_pct':(nav[-1]-1)*100,'equity':nav[-1],'mdd_pct':dd,'n_trades':len(trades),
        'natural_trades':len(natural),'n_long':sum(t['side']==1 for t in trades),'n_short':sum(t['side']==-1 for t in trades),
        'reversal_exits':sum(t['reason']=='reverse_signal' for t in trades),'bankrupt':bankrupt,
        'exposure_pct':100*np.mean(np.array(sides[start_idx:])!=0),'rejected_signals':rejected,
        'filter_time_coverage':eligible_days/max(1,n-minimum)}
    for side,name in [(1,'long'),(-1,'short')]:
        ts=[t for t in trades if t['side']==side]
        metrics[name+'_log_growth']=sum(math.log(t['equity_after']/t['equity_before']) for t in ts) if all(t['equity_after']>0 for t in ts) else None
        profits=[max(0,t['ret_pct']) for t in ts]
        metrics[name+'_largest_profit_share']=max(profits,default=0)/sum(profits) if sum(profits)>0 else None
    return {'metrics':metrics,'nav':nav,'trades':trades,'events':events,'active_stops':stops,
            'active_sides':sides,'active_units':units_path,'start_idx':start_idx}

def qualify(result, stress_return=None):
    m=result['metrics'];a=np.array(result['nav'][result['start_idx']:]);days=len(a)
    cagr=(a[-1]**(365/days)-1)*100 if a[-1]>0 else -100.
    cut=np.array_split(np.arange(days),3);prior=1.;parts=[]
    for indices in cut:
        value=a[indices[-1]];parts.append(value/prior-1 if prior>0 else -1);prior=value
    gates={'annualized_5pct':cagr>=5,'mdd_40pct':m['mdd_pct']<=40,
           'natural_20trades':m['natural_trades']>=20,'two_positive_thirds':sum(x>0 for x in parts)>=2,
           'worst_third_minus20':min(parts)>=-.20,'no_bankruptcy':not m['bankrupt']}
    if stress_return is not None:gates['stress_positive']=stress_return>0
    return {'cagr_pct':cagr,'third_returns':parts,'strict_without_stress':all(gates.values()),'gates':gates}
