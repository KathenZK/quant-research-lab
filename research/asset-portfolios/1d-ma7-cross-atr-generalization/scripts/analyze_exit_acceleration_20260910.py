"""Predeclared acceleration events and exit-state coverage, price diagnostics only."""
from __future__ import annotations
import itertools,json,time
from pathlib import Path
import numpy as np
import pandas as pd
from common import BASE,ROOT,RESULTS,sha,write_json
ROUND=BASE/'artifacts/state_machine_20260910';CURRENT=ROUND/'results_current'
DIAG=ROUND/'diagnostics_work/current_v3_new_costs/state_features'
OUT=ROUND/'acceleration_diagnostics'
CONTRACT=BASE/'specs/exit-acceleration-diagnostics-20260910.md'
FACTORS=['atr_accel','pct5_accel','ma2_atr','rsi80_20','short_rsi30','short_atr_accel_rsi30','atr_accel_ma2']


def factor_flags(d,i,side):
    b=d.iloc[i];prev=d.iloc[i-1];older=d.iloc[i-2]
    step=side*(b.close-prev.close);old=side*(prev.close-older.close)
    pct=side*(b.close/prev.close-1);op=side*(prev.close/older.close-1)
    acceleration=step>=prev.atr and step>max(old,0)
    far=side*(b.close-b.ma)/b.atr>=2
    rsi_ext=b.rsi>=80 if side==1 else b.rsi<=20
    short30=side==-1 and b.rsi<=30
    flags=[acceleration,pct>=.05 and pct>max(op,0),far,rsi_ext,short30,acceleration and short30,acceleration and far]
    return dict(zip(FACTORS,map(bool,flags))),{'directional_pct':float(pct*100),'directional_atr_speed':float(step/prev.atr),
            'directional_ma_distance_atr':float(side*(b.close-b.ma)/b.atr),'rsi6':float(b.rsi),'atr':float(b.atr)}


def follow(h,stamps,lo,atr,side,days):
    hi=lo+pd.Timedelta(days=days);a=int(np.searchsorted(stamps,lo.value));b=int(np.searchsorted(stamps,hi.value))
    if a>=len(h) or stamps[a]!=lo.value:return {'horizon_days':days,'complete':False,'censor_reason':'NO_NEXT_OPEN'}
    if b-a!=days*24 or b==0 or stamps[b-1]+pd.Timedelta(hours=1).value!=hi.value:
        return {'horizon_days':days,'complete':False,'censor_reason':'INCOMPLETE_FORWARD_WINDOW'}
    ref=float(h.open.iloc[a]);window=h.iloc[a:b]
    favorable=float(window.high.max() if side==1 else window.low.min())
    adverse=float(window.low.min() if side==1 else window.high.max());last=float(window.close.iloc[-1])
    return {'horizon_days':days,'complete':True,'censor_reason':'','reference_next_open':ref,
            'end_directional_atr':side*(last-ref)/atr,'end_directional_pct':side*(last/ref-1)*100,
            'maximum_favorable_atr':max(0.,side*(favorable-ref)/atr),
            'maximum_adverse_atr':max(0.,side*(ref-adverse)/atr),
            'maximum_favorable_pct':max(0.,side*(favorable/ref-1)*100),
            'maximum_adverse_pct':max(0.,side*(1-adverse/ref)*100)}


def audit_follow_boundaries():
    ts=pd.date_range('2026-01-01',periods=48,freq='h',tz='UTC')
    h=pd.DataFrame({'timestamp':ts,'open':100.,'high':110.,'low':90.,'close':105.})
    for unit in ['ns','us']:
        ns=h.timestamp.dt.as_unit(unit).dt.as_unit('ns').astype('int64').to_numpy()
        a=follow(h,ns,ts[0],10.,1,1);b=follow(h,ns,ts[0],10.,-1,1)
        assert a['complete'] and a['end_directional_atr']==.5 and b['end_directional_atr']==-.5
        assert a['maximum_favorable_atr']==a['maximum_adverse_atr']==1.
        assert not follow(h,ns,ts[1],10.,1,2)['complete']
    return {'long_short_signs':True,'exact_forward_rows':True,'late_censor_preserved':True,'timestamp_units':True}


def main():
    assert not OUT.exists();OUT.mkdir(parents=True)
    assert json.loads((CURRENT/'completion.json').read_text())['complete']
    cm=json.loads((CURRENT/'artifact_checksums.json').read_text());dm=json.loads((DIAG/'artifact_checksums.json').read_text())
    om=json.loads((RESULTS/'artifact_checksums.json').read_text())
    for name in ['all_complete_day_states.csv','all_trade_features.csv']:
        assert sha(DIAG/name)==dm[name]
    for name in ['scope.csv','summary.csv']:assert sha(CURRENT/name)==cm[name]
    write_json(OUT/'started.json',{'created_before_factor_results_utc':str(pd.Timestamp.now(tz='UTC')),'contract_sha256':sha(CONTRACT),
        'script_sha256':sha(Path(__file__)),'current_manifest_sha256':sha(CURRENT/'artifact_checksums.json'),
        'diagnostic_manifest_sha256':sha(DIAG/'artifact_checksums.json'),'follow_checks':audit_follow_boundaries()})
    state=pd.read_csv(DIAG/'all_complete_day_states.csv',float_precision='round_trip')
    for col in ['signal_day','state_available_at','exit_time','entry_time']:state[col]=pd.to_datetime(state[col],utc=True,format='mixed')
    scope=pd.read_csv(CURRENT/'scope.csv');rows=[];coverage=[];early=[];begin=time.monotonic()
    for count,item in enumerate(scope[scope.cohort.ne('excluded')].to_dict('records'),1):
        slug=item['slug'];symbol=item['symbol'];cohort=item['cohort'];price_path=RESULTS/'market'/slug
        for file in ['daily_features.csv','hourly.parquet']:assert sha(price_path/file)==om[str((price_path/file).relative_to(RESULTS))]
        d=pd.read_csv(price_path/'daily_features.csv',float_precision='round_trip');d.timestamp=pd.to_datetime(d.timestamp,utc=True)
        h=pd.read_parquet(price_path/'hourly.parquet');h.timestamp=pd.to_datetime(h.timestamp,utc=True)
        assert h.timestamp.diff().dropna().eq(pd.Timedelta(hours=1)).all()
        stamps=h.timestamp.dt.as_unit('ns').astype('int64').to_numpy();index={t:i for i,t in enumerate(d.timestamp)}
        for tid,ss in state[state.symbol.eq(symbol)].groupby('trade_id',sort=False):
            selected={}
            for s in ss.sort_values('state_available_at').to_dict('records'):
                if s['net_liquidation_profit_at_close_cash']<=0:continue
                flags,features=factor_flags(d,index[s['signal_day']],int(s['side']))
                for factor in FACTORS:
                    if flags[factor] and factor not in selected:
                        selected[factor]={**features,'symbol':symbol,'slug':slug,'cohort':cohort,'source_trade_id':int(tid),
                            'side':int(s['side']),'factor':factor,'signal_day':s['signal_day'],
                            'event_time':s['state_available_at'],'held_days':s['held_complete_day_number'],
                            'baseline_exit_time':s['exit_time'],'baseline_already_exits_at_event':s['exit_time']==s['state_available_at'],
                            'estimated_net_profit_at_event':s['net_liquidation_profit_at_close_cash'],
                            'final_baseline_outcome':s['net_outcome'],'baseline_terminal':s['terminal_exit']}
            for event in selected.values():
                for days in [5,10,20]:rows.append({**event,**follow(h,stamps,event['event_time'],event['atr'],event['side'],days)})
        for cid in ['S1_DEFENSE','S2_TREND','S3_EXTENSION']:
            cp=CURRENT/'runs'/slug/cid/'full';fp=CURRENT/'fixed_entries'/slug/cid
            for f in [cp/'trades.csv',cp/'stops.csv',fp/'trades.csv']:assert sha(f)==cm[str(f.relative_to(CURRENT))]
            tr=pd.read_csv(cp/'trades.csv',float_precision='round_trip');st=pd.read_csv(cp/'stops.csv',float_precision='round_trip')
            st=st[st.get('full_holding_day',pd.Series(False,index=st.index)).eq(True)]
            for metric in ['sm_defense','sm_healthy','sm_protect']:
                hit=st[st.get(metric,pd.Series(False,index=st.index)).eq(True)]
                coverage.append({'symbol':symbol,'cohort':cohort,'case_id':cid,'metric':metric,'days':len(hit),
                    'trades_with_state':int(hit.trade_id.nunique()),'total_trades':len(tr)})
            for metric,field,val in [('healthy_pause','tightening_trigger','healthy_pause'),('watch_started','sm_transition','watch_started'),('watch_cleared','sm_transition','watch_cleared')]:
                hit=st[st.get(field,pd.Series('',index=st.index)).eq(val)]
                coverage.append({'symbol':symbol,'cohort':cohort,'case_id':cid,'metric':metric,'days':len(hit),
                    'trades_with_state':int(hit.trade_id.nunique()),'total_trades':len(tr)})
            try:
                pairs=pd.read_csv(fp/'trades.csv',float_precision='round_trip')
            except pd.errors.EmptyDataError:
                assert json.loads((fp/'summary.json').read_text())['pairs']==0 and len(tr)==0
                pairs=pd.DataFrame()
            if len(pairs):
                for col in ['entry_time','exit_time']:pairs[col]=pd.to_datetime(pairs[col],utc=True,format='mixed')
                w=pairs[(pairs.baseline_net_pnl>0)&~pairs.either_terminal]
                before=w.exit_time<w.entry_time+pd.Timedelta(days=3)
                early.append({'symbol':symbol,'cohort':cohort,'case_id':cid,'original_winners':len(w),
                    'exited_before_three_complete_days':int(before.sum()),
                    'became_loss_before_three_days':int((before&w.net_pnl.lt(0)).sum()),
                    'became_loss_total':int(w.net_pnl.lt(0).sum())})
        if count%100==0:print('Acceleration diagnostic coins',count,'seconds',time.monotonic()-begin,flush=True)
    events=pd.DataFrame(rows);events.to_csv(OUT/'events_and_future_paths.csv',index=False)
    pd.DataFrame(coverage).to_csv(OUT/'state_coverage_by_coin.csv',index=False);pd.DataFrame(early).to_csv(OUT/'early_exit_original_winners.csv',index=False)
    summary=[];coins=[]
    metrics=['end_directional_atr','end_directional_pct','maximum_favorable_atr','maximum_adverse_atr','maximum_favorable_pct','maximum_adverse_pct']
    for (cohort,side,factor,days),g in events.groupby(['cohort','side','factor','horizon_days']):
        valid=g[g.complete];record={'cohort':cohort,'side':side,'factor':factor,'horizon_days':days,
            'events':len(g),'coins':g.symbol.nunique(),'complete_events':len(valid),'censored_events':int((~g.complete).sum()),
            'baseline_exits_at_event':int(g.baseline_already_exits_at_event.sum()),
            'continuation_end_positive_pct':float(valid.end_directional_atr.gt(0).mean()*100) if len(valid) else None}
        for key in metrics:record['median_'+key]=float(valid[key].median()) if len(valid) else None
        summary.append(record)
        for symbol,coin in g.groupby('symbol'):
            c=coin[coin.complete];coins.append({'cohort':cohort,'symbol':symbol,'side':side,'factor':factor,'horizon_days':days,
              'events':len(coin),'complete_events':len(c),'median_end_directional_atr':float(c.end_directional_atr.median()) if len(c) else None,
              'median_maximum_favorable_atr':float(c.maximum_favorable_atr.median()) if len(c) else None,
              'median_maximum_adverse_atr':float(c.maximum_adverse_atr.median()) if len(c) else None})
    pd.DataFrame(summary).to_csv(OUT/'factor_summary.csv',index=False);pd.DataFrame(coins).to_csv(OUT/'factor_by_coin.csv',index=False)
    event=events[events.horizon_days.eq(10)];overlap=[]
    for (cohort,side),g in event.groupby(['cohort','side']):
        p=g.pivot(index=['symbol','source_trade_id'],columns='factor',values='event_time')
        for a,b in itertools.combinations(FACTORS,2):
            aa=p[a] if a in p else pd.Series(pd.NaT,index=p.index);bb=p[b] if b in p else pd.Series(pd.NaT,index=p.index)
            both=aa.notna()&bb.notna();overlap.append({'cohort':cohort,'side':side,'factor_a':a,'factor_b':b,
                'trades_a':int(aa.notna().sum()),'trades_b':int(bb.notna().sum()),'trades_both':int(both.sum()),
                'first_event_same_time':int((both&aa.eq(bb)).sum())})
    pd.DataFrame(overlap).to_csv(OUT/'first_event_overlap.csv',index=False)
    cov=pd.DataFrame(coverage).groupby(['cohort','case_id','metric'],as_index=False)[['days','trades_with_state','total_trades']].sum()
    cov.to_csv(OUT/'state_coverage_summary.csv',index=False)
    pd.DataFrame(early).groupby(['cohort','case_id'],as_index=False).sum(numeric_only=True).to_csv(OUT/'early_winner_summary.csv',index=False)
    write_json(OUT/'summary.json',{'events':len(event),'event_horizons':len(events),'all_rows_preserve_censoring':True,
      'factor_results_are_price_paths_not_executable_profit':True,'fee_per_side':.001,'slip_per_side':.0004,'cohorts':scope.cohort.value_counts().to_dict(),
      'elapsed_seconds':time.monotonic()-begin,'script_sha256':sha(Path(__file__))})
    (OUT/'source_script.py.txt').write_bytes(Path(__file__).read_bytes())
    write_json(OUT/'artifact_checksums.json',{str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file()})

if __name__=='__main__':main()
