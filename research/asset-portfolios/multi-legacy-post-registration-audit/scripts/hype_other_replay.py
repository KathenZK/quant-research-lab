"""Fixed legacy HYPE replays; prices/funding only through the audit's frozen input helper.

Original engines are imported for execution. No original strategy is edited, no search run.
Funding values are observed-event estimates, not verified full funding-inclusive net returns.
"""
from __future__ import annotations
import argparse, importlib.util, json, sys, hashlib
from dataclasses import asdict, replace
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[4]
FAMILY=ROOT/'research/asset-portfolios/multi-legacy-post-registration-audit'
OUT=FAMILY/'artifacts/hype_other'
sys.path.insert(0,str(Path(__file__).parent))

def mod(path,name):
    path=ROOT/path
    sys.path.insert(0,str(path.parent))
    sp=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(sp)
    sys.modules[name]=m; sp.loader.exec_module(m); return m

def funding_series(frame,funding):
    idx=pd.DatetimeIndex(frame.index)
    events=funding.set_index('ts').funding_rate
    # Only events map into the grid; absent events remain an explicit source-coverage limitation.
    return events.groupby(events.index.floor('15min')).sum().reindex(idx,fill_value=0.)

def write(case,payload,trades,curve):
    dest=OUT/case; dest.mkdir(parents=True,exist_ok=True)
    trades.to_csv(dest/'trades.csv',index=False)
    if isinstance(curve,pd.Series): curve=curve.rename('equity').to_frame()
    if 'ts' in curve: curve=curve.set_index(pd.to_datetime(curve.pop('ts'),utc=True))
    curve.index=pd.to_datetime(curve.index,utc=True)
    curve=curve[~curve.index.duplicated(keep='last')].sort_index()
    start=pd.Timestamp(payload['start']); end=pd.Timestamp(payload['end'])
    curve=curve.loc[(curve.index>=start)&(curve.index<=end)].copy()
    if not len(curve): curve=pd.DataFrame({'equity':[1.]},index=[start])
    anchored=pd.concat([pd.DataFrame({'equity':[1.]},index=[start-pd.Timedelta(nanoseconds=1)]),curve[['equity']]])
    ending=float(curve.equity.iloc[-1]); dd=float((anchored.equity/anchored.equity.cummax()-1).min())
    payload['curve_return']=ending-1.; payload['curve_close_drawdown']=dd
    curve.to_csv(dest/'equity.csv',index_label='ts')
    duration=0 if case.startswith('mhef_1h') else (60 if case.startswith(('ar_v4','mmtf_1h','pktsc')) else (30 if case.startswith('keltner_v3') else 15))
    label='valuation_time' if duration==0 else 'bar_open'
    payload['equity_timestamp_semantics']={'label':label,'bar_duration_minutes':duration,'terminal_row_time':end.isoformat(),'raw_row_exactly_at_end_is_already_valuation_time':True}
    valuation_times=curve.index+pd.Timedelta(minutes=duration)
    valuation_times=pd.DatetimeIndex([end if raw==end else val for raw,val in zip(curve.index,valuation_times)])
    actual=curve[['equity']].copy();actual.index=valuation_times;actual=actual.loc[actual.index<=end]
    month_keys=(actual.index-pd.Timedelta(nanoseconds=1)).tz_localize(None).to_period('M')
    monthly=actual.equity.groupby(month_keys).last();monthly=monthly.loc[monthly.index>=start.tz_localize(None).to_period('M')]
    ret=monthly/monthly.shift(1)-1
    ret.iloc[0]=monthly.iloc[0]-1.; ret.rename('return').to_csv(dest/'monthly.csv',index_label='month')
    payload.update({'case':case,'symbol':'HYPEUSDT','funding_status':'OBSERVED_EVENT_ESTIMATE_NOT_VERIFIED_FULL_NET','flat_start':True,'no_retuning':True,'artifacts':{'trades':str((dest/'trades.csv').relative_to(ROOT)),'equity':str((dest/'equity.csv').relative_to(ROOT)),'monthly':str((dest/'monthly.csv').relative_to(ROOT))}})
    (dest/'summary.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,default=str))
    print(json.dumps({'case':case,**{k:payload.get(k) for k in ('start','end','curve_return','curve_close_drawdown','metrics')}},default=str),flush=True)

def build_book(e,frame,funding,tf):
    ts=pd.DatetimeIndex(frame.ts); h=frame.high.to_numpy(float); l=frame.low.to_numpy(float); c=frame.close.to_numpy(float); v=frame.volume.to_numpy(float)
    atr={w:e._atr(h,l,c,w) for w in e.ATR_WINDOWS}; ema={w:e._ema(c,w) for w in e.EMA_SPANS}
    wins=sorted(set(e.ENTRY_WINDOWS+e.EXIT_WINDOWS)); prior_h={w:e._prior_roll(h,w,'max') for w in wins}; prior_l={w:e._prior_roll(l,w,'min') for w in wins}
    mom={(w,aw):(c-np.r_[np.full(w,np.nan),c[:-w]])/a for w in wins for aw,a in atr.items()}
    prev=np.r_[np.nan,c[:-1]]; tr=np.maximum(h-l,np.maximum(abs(h-prev),abs(l-prev)))
    return e.FeatureBook(ts=ts,terminal_ts=ts[-1]+pd.Timedelta(tf),open=frame.open.to_numpy(float),high=h,low=l,close=c,volume=v,atr=atr,adx=e._adx(h,l,c),ema=ema,prior_high=prior_h,prior_low=prior_l,momentum_atr=mom,rvol=v/pd.Series(v).shift(1).rolling(48,min_periods=48).median().to_numpy(float),tr_over_atr={w:tr/a for w,a in atr.items()},funding_by_bar=e._funding_by_bar(ts,funding),source_start=ts[0],selection_end=ts[-1]+pd.Timedelta(tf))

def run_mmtf(case,frame,funding,tf,start,end):
    base=f'research/hype/{tf}-multi-mechanism-trend-following'
    e=mod(base+'/scripts/mmtf_engine.py','mmtf_engine'); a=mod(base+'/scripts/mmtf_v2.py','mmtf_v2')
    p=ROOT/base/'artifacts'/f'hype_{tf}_mmtf_v2_clean_tune_2026-07-22.json'; frozen=json.loads(p.read_text())['v3_tuned_freeze']
    cfg=a.to_engine_config(a.clean_from_dict(frozen['config'])); assert e.config_sha256(cfg)==frozen['engine_config_sha256']
    book=build_book(e,frame,funding,{'1h':'1h','15m':'15min'}[tf]); r=e.run_backtest(book,cfg,start_ts=start,end_ts=end,detailed=True)
    curve=pd.Series(1.,index=pd.DatetimeIndex(frame.ts),name='equity')
    for t in r.trades:
        entry=pd.Timestamp(t['entry_ts']); exit_=pd.Timestamp(t['exit_ts']); eq=t['entry_equity']; side=t['side']; lev=t['leverage']
        mask=(curve.index>=entry)&(curve.index<exit_)
        fi=np.flatnonzero(mask); cumul=np.cumsum(book.funding_by_bar[fi])
        curve.loc[mask]=eq*(1+lev*side*(frame.close.to_numpy()[fi]/t['entry_price']-1)-lev*.001-lev*side*cumul)
        curve.loc[curve.index>=exit_]=t['exit_equity']
    write(case,{'version':f'HYPE-{tf}-MMTF-V3','start':start,'end':end,'date_evidence':base+'/decision-log.md','config':asdict(cfg),'engine_sha256':hashlib.sha256(Path(e.__file__).read_bytes()).hexdigest(),'metrics':r.metrics},pd.DataFrame(r.trades),curve)

def run_keltner(case,frame,funding,start,end):
    p='research/hype/30m-keltner-trend-breakout/scripts/audit_hype_30m_keltner_v3_latest.py'; m=mod(p,'hype_keltner_audit')
    f,cfg,q=m.v3_features(frame,rows_per_30m=2,rows_per_1h=4)
    r=m.strict.simulate(case,f,funding,cfg,m.strict.ExecutionConfig(),start_ts=start,end_ts=end)
    write(case,{'version':'HYPE-30M-Keltner-Trend-Breakout-V3','start':start,'end':end,'date_evidence':'research/hype/30m-keltner-trend-breakout/decision-log.md','config':asdict(cfg),'aggregation':q,'metrics':r.metrics},r.trades,r.equity)

def run_ar(case,frame,funding,start,end):
    p='research/hype/1h-adaptive-regime/scripts/audit_hype_1h_ar_v4_pressure_optimization.py'; m=mod(p,'hype_ar_exact')
    f=m.v3ab.ensure_extra_macd_features(m.base.add_features(frame,funding))
    # Compute indicators using full warmup, then reset position/cooldown at cutoff.
    f=f.loc[(f.ts>=start)&(f.ts<end)].reset_index(drop=True)
    # One explicit settlement sentinel at last actual close; never a new market observation.
    sentinel=f.iloc[-1:].copy(); sentinel['ts']=end
    for col in ('open','high','low','close'): sentinel[col]=float(f.close.iloc[-1])
    f=pd.concat([f,sentinel],ignore_index=True)
    ft,fc=m.base.funding_prefix(funding); engine=m.ExactJointEngine(f,ft,fc); di,st=m.v4_engine_configs()
    tt=[t for t in engine.exact_joint(di,st,('base',.001,.0004,1)) if t.entry_ts<end]
    tt=[replace(t,exit_reason='audit_terminal_close') if t.exit_ts==end else t for t in tt]
    metrics=m.base.metrics(tt,start,end)
    # Hourly close marks, with the original frozen entry-notional funding estimate.
    curve=pd.Series(1.,index=pd.DatetimeIndex(f.ts),name='equity'); eq=1.
    for t in tt:
        mask=(curve.index>=t.entry_ts)&(curve.index<t.exit_ts)
        for ii in np.flatnonzero(mask):
            bar_end=min(pd.Timestamp(f.ts.iloc[ii])+pd.Timedelta(hours=1),t.exit_ts)
            fr=m.base.trade_funding(t.entry_ts.value,bar_end.value,t.side,ft,fc)
            curve.iloc[ii]=eq*(1+t.exposure*(t.side*(float(f.close.iloc[ii])/t.entry_price-1)-.001+fr))
        eq*=max(.001,1+t.equity_ret); curve.loc[curve.index>=t.exit_ts]=eq
    write(case,{'version':'HYPE-1H-Adaptive-Regime-V4','start':start,'end':end,'date_evidence':'research/hype/1h-adaptive-regime/decision-log.md','execution_correction_date':'2026-07-10','curve_type':'hourly close marks; max_dd in metrics includes original conservative within-trade MAE','funding_model':'original fixed entry-notional approximation; native timestamps retained','terminal_settlement':'explicit sentinel at last actual close, never tradable after end','config':{'di':asdict(di),'stoch':asdict(st)},'metrics':metrics},pd.DataFrame([asdict(t) for t in tt]),curve)

def run_mdtp(case,frame,funding,start,end):
    m=mod('research/hype/15m-multidimensional-trend-pyramiding/scripts/research_hype_15m_mdtp.py','hype_mdtp')
    f=frame.set_index('ts'); w=m.FeatureWindows(); cfg=m.StrategyConfig(); var=[x for x in m.VARIANTS if x.name=='full'][0]
    feat=m.build_feature_set(f,w); state=m.build_state(f,feat,cfg,var)
    r=m.simulate(name=case,frame=f,funding=funding_series(f,funding),state=state,features=feat,config=cfg,variant=var,fee_per_fill=.001,slippage_per_fill=.0004,include_funding=True,active_start=start,active_end=end)
    write(case,{'version':'HYPE-15M-MDTP-V1','start':start,'end':end,'date_evidence':'research/hype/15m-multidimensional-trend-pyramiding/diagnostics/hype-15m-mdtp-v1-initial-research-2026-07-31.md','limitation':'original allocation-return simulator is not an explicit quantity ledger; strategy-rule diagnostic only','config':asdict(cfg),'metrics':r.metrics},r.trades,r.equity)
    r.actions.to_csv(OUT/case/'actions.csv',index=False)

def run_bksb(case,frame,funding,tf,start,end):
    m=mod(f'research/hype/{tf}-bollinger-keltner-squeeze-breakout/scripts/run_baseline.py','hype_bksb_loader'); e=m.load_engine(); cfg=e.StrategyConfig()
    f=frame.set_index('ts'); bars,q=e.aggregate_complete_bars(f,tf); feat=e.build_features(bars,cfg)
    # Preserve warmup and historical indicator states, suppress all pre-cutoff signals.
    feat.loc[feat.index<start,['long_signal','short_signal']]=False
    r=e.run_backtest(f,funding_series(f,funding),bars,feat,tf,e.RunSpec(name='primary_k1'),cfg)
    t=r.trades.copy(); curve=r.equity_curve.loc[r.equity_curve.index>=start]
    terminal=None
    if r.open_position is not None:
        p=r.open_position; before=float(curve.iloc[-1]); mark=float(f.close.iloc[-1]); entry_ts=pd.Timestamp(p['entry_ts'])
        entry_equity=before/(1+float(p['unrealized_trade_return_pct'])/100)
        pos=e.Position(direction=p['direction'],signal_ts=pd.Timestamp(p['signal_ts']),entry_ts=entry_ts,entry_price=p['entry_price'],entry_atr=p['entry_atr'],entry_equity=entry_equity,previous_price=mark,entry_tf_pos=int(bars.index.searchsorted(entry_ts)),entry_base_pos=int(f.index.searchsorted(entry_ts)))
        closed=[]; final,_=e._close_position(equity=before,position=pos,raw_exit_price=mark,exit_ts=end,exit_base_pos=len(f),reason='audit_terminal_close',config=cfg,trades=closed)
        t=pd.concat([t,pd.DataFrame(closed)],ignore_index=True);curve.loc[end]=final
        terminal={'equity_before_exit_cost':before,'equity_after_exit_cost':final,'exit_fee_and_slippage_equity':before-final,'last_actual_close':mark,'original_close_function':'_close_position','closed_trade':closed[0]}
    write(case,{'version':f'HYPE-{tf}-BKSB fixed baseline observation','start':start,'end':end,'date_evidence':f'research/hype/{tf}-bollinger-keltner-squeeze-breakout/diagnostics/hype-{tf}-bksb-baseline-2026-07-23.md','config':asdict(cfg),'metrics':{'trades':len(t),'total_return':float(curve.iloc[-1])-1},'source_engine_metrics_before_terminal':r.metrics,'source_open_position_before_terminal':r.open_position,'open_position':None,'terminal_settlement_detail':terminal,'terminal_settlement':'original close function at last actual close; added exit fee/slippage when source left a position open','funding_model':'legacy bar assignment; native ms events mapped to bar; estimate only','registered':False},t,curve)

def run_mhef_1h(case,frame,funding,start,end):
    e=mod('research/_shared-kernels/multi-horizon-ema-forecast/v1/engine.py','hype_mhef_engine'); cfg=e.ForecastConfig(); features=e.build_forecasts(frame,cfg)
    i=int(np.searchsorted(pd.DatetimeIndex(frame.ts).as_unit('ns').asi8,start.value))
    for buffer in (0.,.1):
        name=f'{case}_buffer{buffer:.2f}'; r=e.backtest_target(features,funding,features.forecast,name=name,timeframe='1h',buffer=buffer,config=cfg,start_index=i)
        curve=r.path[['ts','equity_net']].rename(columns={'equity_net':'equity'})
        # Mark the final real bar through its actual close, then charge a terminal closing fill.
        last=r.path.iloc[-1]; pos=float(last.position); mark=float(frame.close.iloc[-1]); eq=float(last.equity_net)
        event_sum=float(funding.loc[(funding.ts>pd.Timestamp(last.ts))&(funding.ts<end),'funding_rate'].sum())
        price_return=mark/float(last.open)-1
        before_funding=eq*(1+pos*price_return); funding_amount=before_funding*pos*event_sum
        before_exit=before_funding-funding_amount; closing_cost=before_exit*abs(pos)*(.001+.0004)
        final=before_exit-closing_cost
        source_metrics=dict(r.metrics)
        terminal={'ts':end,'open':mark,'desired_position':0.,'position':0.,'turnover':abs(pos),'market_return':price_return,'funding_rate_interval':event_sum,'cost_amount':closing_cost,'funding_amount':funding_amount,'equity_gross':float(last.equity_gross)*(1+pos*price_return),'equity_net':final,'execution_reason':'audit_terminal_close'}
        settled_path=pd.concat([r.path,pd.DataFrame([terminal])],ignore_index=True)
        metrics=e.compute_metrics(settled_path,timeframe='1h',total_cost_amount=float(r.path.cost_amount.sum())+closing_cost,total_funding_amount=float(r.path.funding_amount.sum())+funding_amount)
        curve=settled_path[['ts','equity_net']].rename(columns={'equity_net':'equity'})
        trades=settled_path.loc[settled_path.turnover>1e-12].copy()
        write(name,{'version':'HYPE-1H-MHEF baseline observation','start':start,'end':end,'date_evidence':'research/hype/1h-multi-horizon-ema-forecast/notes/hype-1h-mhef-baseline-backtest-2026-07-14.md','config':asdict(cfg),'buffer':buffer,'metrics':metrics,'source_engine_metrics_before_terminal':source_metrics,'registered':False,'trade_unit':'rebalance fills including explicit terminal close; no defined closed campaigns','terminal_mark':'last actual close with explicit exit fee/slippage; final-bar native event rates remain the original proportional-position estimate','terminal_settlement_detail':terminal},trades,curve)

def run_mtpp(case,frame,funding,start,end):
    e=mod('research/hype/15m-multi-timeframe-probe-pyramiding/scripts/research_hype_15m_mtpp.py','hype_mtpp_engine'); f=frame.set_index('ts'); signals,q=e.build_signals(f)
    for side in (1,-1):
        for risk in (.01,.03,.10):
            name=f'{case}_{"long" if side>0 else "short"}_{int(risk*100)}pct'; r=e.run_backtest(f,funding_series(f,funding),signals,side=side,policy='trader_full',risk_budget=risk,start=start,end=end)
            write(name,{'version':'HYPE-15M-MTPP trader_full frozen observation','start':start,'end':end,'date_evidence':'research/hype/15m-multi-timeframe-probe-pyramiding/specs/hype-15m-mtpp-initial-research-contract-2026-08-03.md','side':side,'policy':'trader_full','risk_budget':risk,'metrics':r.metrics,'registered':False,'aggregation':q},r.campaigns,r.equity)
            r.actions.to_csv(OUT/name/'actions.csv',index=False)

def run_keltner15(case,frame,funding,start,end):
    e=mod('research/hype/15m-keltner-trend-breakout/scripts/research_hype_15m_keltner_mechanisms.py','hype_keltner15'); cfg=e.base.KeltnerConfig(hard_stop_atr=4.,max_hold_bars=192,cooldown_bars=4)
    f=frame.set_index('ts'); feat=e.base.build_features(f,cfg); signals=e.build_hypothesis_signals(feat)
    for mechanism,signal in signals.items():
        signal.loc[signal.index<start,['long_signal','short_signal']]=False
        name=case+'_'+mechanism; spec=e.HypothesisSpec(name,mechanism,mechanism,1)
        r=e.run_backtest(f,funding_series(f,funding),signal,spec,cfg)
        assert r.open_position is None, 'this selected cutoff needs an explicit original-rule terminal settlement before reporting'
        write(name,{'version':'HYPE-15M-Keltner mechanism observation','start':start,'end':end,'date_evidence':'research/hype/15m-keltner-trend-breakout/diagnostics/hype-15m-keltner-mechanism-hypotheses-2026-07-21.md','config':asdict(cfg),'mechanism':mechanism,'metrics':{'trades':len(r.trades)},'registered':False,'open_position':r.open_position,'funding_model':'legacy bar assignment; native ms events mapped to bar; estimate only'},r.trades,r.equity_curve)

def basic_book(e,frame,funding,end,atr_window):
    ts=pd.DatetimeIndex(frame.ts); h=frame.high.to_numpy(float); l=frame.low.to_numpy(float); c=frame.close.to_numpy(float)
    return e.FeatureBook(ts=ts,terminal_ts=end,open=frame.open.to_numpy(float),high=h,low=l,close=c,volume=frame.volume.to_numpy(float),atr=e._atr(h,l,c,atr_window),funding_by_bar=e._funding_by_bar(ts,funding),source_start=ts[0])

def run_sma(case,frame,funding,start,end):
    family='research/hype/15m-sma-crossover-slope'; e=mod(family+'/scripts/sma_xs_engine.py','hype_sma_engine')
    frozen=json.loads((ROOT/family/'artifacts/hype_15m_sma_xs_prefit_selection.json').read_text()); cfg=e.Config(**frozen['reference_config']); assert e.config_sha256(cfg)==frozen['reference_config_sha256']
    book=basic_book(e,frame,funding,end,cfg.atr_window); state=e.generate_states(book.close,book.atr,cfg)
    start_i=int(book.ts.searchsorted(start)); after=np.flatnonzero((state.golden_cross|state.dead_cross)&(np.arange(book.rows)>=start_i)); first=int(after[0]) if len(after) else book.rows
    state.desired_state[:first]=0
    r=e.run_backtest(book,cfg,states=state)
    write(case,{'version':'HYPE-15M-SMA-XS frozen failed reference','start':start,'end':end,'date_evidence':family+'/notes/hype-15m-sma-xs-baseline-and-slope-exits-2026-07-28.md','config':asdict(cfg),'metrics':{'trades':len(r.trades)},'registered':False,'reference_only':True,'initialization':'flat until first new crossover after cutoff'},pd.DataFrame(r.trades),pd.DataFrame(r.equity_path))

def run_sds(case,frame,funding,start,end):
    family='research/hype/15m-sequential-drift-state'; e=mod(family+'/scripts/sds_engine.py','sds_engine'); k=mod(family+'/scripts/research_hype_15m_sds_kalman_cusum_structure.py','hype_kcs')
    ref=json.loads((ROOT/family/'artifacts/hype_15m_sds_kcs_prefit_search.json').read_text())['reference']; cfg=k.KCSConfig(**{x:ref[x] for x in k.KCSConfig.__dataclass_fields__}); exec_cfg=e.Config(stop_atr=4.,max_hold_bars=384,leverage=1.)
    book=basic_book(e,frame,funding,end,exec_cfg.atr_window); feat=k.build_features(book,cfg); i=int(book.ts.searchsorted(start))
    # Carry only causal numerical estimates; reset campaign and CUSUM trigger state at launch.
    sub=replace(book,**{x:getattr(book,x)[i:] for x in ('ts','open','high','low','close','volume','atr','funding_by_bar')},source_start=start)
    features=replace(feat,**{x:getattr(feat,x)[i:] for x in k.KCSFeatures.__dataclass_fields__})
    state=k.generate_kcs_states(sub,cfg,features=features); r=e.run_backtest(sub,exec_cfg,states=state)
    write(case,{'version':'HYPE-15M-SDS KCS frozen failed reference','start':start,'end':end,'date_evidence':family+'/notes/hype-15m-sds-kalman-cusum-structure-2026-07-28.md','config':asdict(cfg),'execution_config':asdict(exec_cfg),'metrics':r.metrics,'registered':False,'reference_only':True,'initialization':'causal Kalman estimate warm; campaign/CUSUM signal state reset flat'},pd.DataFrame(r.trades),pd.DataFrame(r.equity_path))

def run_mapt(case,frame,funding,start,end):
    family='research/hype/15m-ma7-ma30-pyramiding'; m=mod(family+'/scripts/research_hype_15m_ma7_exit_comparison.py','hype_ma_comparison'); ma=m.load_ma_module(); ma._target_quantity=m.stable_target_quantity; parent=ma._load_parent()
    h=frame.high.to_numpy(float); l=frame.low.to_numpy(float); c=frame.close.to_numpy(float); ts=pd.DatetimeIndex(frame.ts)
    book=ma.Book(ts=ts,terminal_ts=end,open=frame.open.to_numpy(float),high=h,low=l,close=c,ma7={0:ma._sma(c,7),1:ma._ema(c,7)},ma30={0:ma._sma(c,30),1:ma._ema(c,30)},atr={w:parent._atr(h,l,c,w) for w in (5,7,10,14,20,30)},adx={w:parent._adx(h,l,c,w) for w in (5,7,10,14,20,30)},prior_high={w:parent._prior_roll(h,w,'max') for w in (2,3,5,7,10,14,20)},prior_low={w:parent._prior_roll(l,w,'min') for w in (2,3,5,7,10,14,20)},funding_by_open=parent._funding_by_open(pd.DatetimeIndex([*ts,end]),funding),quality={'terminal_open':float(c[-1])},funding_quality={'verified':False})
    cfg=m.frozen_control(ma)
    for exit_mode,name in [(0,'opposite_cross'),(1,'close_through_ma7')]:
        r=ma.backtest(replace(cfg,exit_mode=exit_mode),book,start_index=int(ts.searchsorted(start)),terminal_index=len(ts),retain=True)
        # Convert the source's after-open/account-action values to bar-close values.
        for point in r.path:
            stamp=pd.Timestamp(point['ts'])
            if stamp<end:
                bi=int(ts.searchsorted(stamp));point['equity']+=float(point.get('position_qty',0.))*(float(c[bi])-float(frame.open.iloc[bi]))
        r.path.append({'ts':end,'equity':r.metrics['equity_multiple'],'terminal_flatten_record':True})
        write(case+'_'+name,{'version':'HYPE-15M-MA7-MA30-Pyramiding frozen paired observation','start':start,'end':end,'date_evidence':family+'/specs/hype-15m-ma7-exit-comparison-contract-2026-07-30.md','config':asdict(replace(cfg,exit_mode=exit_mode)),'metrics':r.metrics,'registered':False,'terminal_settlement':'explicit settlement at last actual close'},pd.DataFrame(r.trades),pd.DataFrame(r.path))

def run_pbtr(case,frame,funding,start,end):
    family='research/hype/15m-pullback-trail'; e=mod(family+'/scripts/research_hype_15m_pbtr_bracket_search.py','hype_pbtr_bracket')
    # The family ledger states 10bp fee and 4bp adverse slippage; inherited live fill averages are not its frozen stated cost.
    e.FEE_RATE_PER_FILL=.001; e.ENTRY_SLIPPAGE_RATE=.0004; e.EXIT_SLIPPAGE_RATE=.0004
    cfg=e.SignalSpec(21,96,.015,'long',False); filt=e.FilterSpec(ret_window=32,min_dir_ret_bps=600); ex=e.ExitSpec(2.,4.,24)
    f=e.add_features(frame); signal=e.filter_signal(f,e.build_signal(f,cfg),cfg,filt); signal[f.ts<start]=0
    sentinel=f.iloc[-1:].copy();sentinel.ts=end;sentinel['_ts_ns']=end.value
    for c in ('open','high','low','close'):sentinel[c]=float(f.close.iloc[-1])
    f=pd.concat([f,sentinel],ignore_index=True); signal=np.r_[signal,0]
    raw=e.simulate_bracket(f,signal,ex,case);raw=[t for t in raw if t.entry_ts<end]
    trades=[]; curve=pd.Series(1.,index=pd.DatetimeIndex(f.ts),name='equity');eq=1.
    for t in raw:
        events=funding.loc[(funding.ts>=t.entry_ts)&(funding.ts<t.exit_ts),'funding_rate']; fr=-t.side*float(events.sum()); adj=replace(t,net_ret_1x=t.net_ret_1x+fr)
        for i in np.flatnonzero((curve.index>=t.entry_ts)&(curve.index<t.exit_ts)):
            stop=min(pd.Timestamp(f.ts.iloc[i])+pd.Timedelta(minutes=15),t.exit_ts)
            funding_mark=-t.side*float(funding.loc[(funding.ts>=t.entry_ts)&(funding.ts<stop),'funding_rate'].sum())
            curve.iloc[i]=eq*(1+t.side*(float(f.close.iloc[i])/t.entry_price-1)-.001+funding_mark)
        eq*=max(.001,1+adj.net_ret_1x);curve.loc[curve.index>=t.exit_ts]=eq;trades.append(adj)
    metrics=e.metric_from_trades(trades,start=start,end=end)
    write(case,{'version':'HYPE-15M-PBTR bracket frozen representative observation','start':start,'end':end,'date_evidence':family+'/hype-15m-pbtr-core-ledger.md','config':{'signal':asdict(cfg),'filter':asdict(filt),'exit':asdict(ex)},'metrics':metrics,'registered':False,'legacy_cost_adapter':'override inherited live fill averages to family ledger fee .001 + adverse .0004','funding_model':'observed events applied on fixed entry notional; absent coverage not verified','original_trailing_migration':'not replayed: known non-executable unlocked stop state machine'},pd.DataFrame([asdict(t) for t in trades]),curve)

def run_pktsc(case,frame,funding,start,end):
    family='research/hype/1h-price-kinematic-trend-survival-control'; e=mod(family+'/scripts/research_hype_1h_pktsc.py','hype_pktsc')
    hourly,visible,q=e.build_complete_hourly(frame.set_index('ts')); state=e.build_price_state(visible); labelled=e.add_future_labels(state,(24,)); anchors=labelled.loc[labelled.is_anchor].copy()
    train_ready=anchors.dropna(subset=[*e.FULL_FEATURES,'future_z_24','continuation_24']); test_ready=anchors.dropna(subset=list(e.FULL_FEATURES)); rows=[]; training=[]
    # The original diagnostic drops missing future labels on test rows. A running strategy
    # cannot know them: test availability is features only; fitting still uses matured labels.
    for day in pd.date_range(start.normalize(),end, freq='1D',inclusive='left'):
        for side,direction in ((1,'long'),(-1,'short')):
            tr=train_ready.loc[(train_ready.index<day-pd.Timedelta(hours=24))&train_ready.direction.eq(side)]
            te=test_ready.loc[(test_ready.index>=day)&(test_ready.index<min(day+pd.Timedelta(days=1),end))&test_ready.direction.eq(side)]
            if len(tr)<e.MIN_TRAIN_ROWS or te.empty or tr.continuation_24.nunique()<2: continue
            z,p=e._fit_models(tr,te,e.FULL_FEATURES,24)
            training.append({'fit_day':day,'side':side,'train_rows':len(tr),'latest_training_anchor':tr.index.max(),'latest_label_maturity':tr.index.max()+pd.Timedelta(hours=24),'test_rows':len(te)})
            assert tr.index.max()+pd.Timedelta(hours=24)<day
            for j,(ts,row) in enumerate(te.iterrows()):
                rows.append({'ts':ts,'direction':direction,'side':side,'horizon_hours':24,'full_z_pred':float(z[j]),'full_prob':float(p[j]),'slow_alignment':int(row.slow_alignment),'stop_distance_log':float(row.stop_distance_log)})
    predictions=pd.DataFrame(rows).sort_values(['ts','side']); e.WF_START=start;e.PROSPECTIVE_START=end
    dest=OUT/case;dest.mkdir(parents=True,exist_ok=True);predictions.to_csv(dest/'predictions.csv',index=False);pd.DataFrame(training).to_csv(dest/'training_windows.csv',index=False)
    fr=funding.set_index('ts').funding_rate; fr=fr.groupby(fr.index.floor('1h')).sum().reindex(hourly.index,fill_value=0.)
    for side,direction in ((1,'long'),(-1,'short')):
        schedule,campaigns=e.build_campaign_schedule(hourly,predictions,side=side,use_mfe_floor=True)
        name=case+'_'+direction; r=e.simulate_policy(hourly,fr,schedule,campaigns,policy='dynamic')
        write(name,{'version':'HYPE-1H-PKTSC dynamic frozen observation','start':start,'end':end,'date_evidence':family+'/specs/hype-1h-pktsc-initial-research-contract-2026-08-03.md','registered':False,'side':side,'metrics':r.metrics,'config':{'ridge_alpha':e.RIDGE_ALPHA,'logit_c':e.LOGIT_C,'min_train_rows':e.MIN_TRAIN_ROWS,'horizon_hours':24,'risk_fraction':e.RISK_FRACTION,'disaster_fraction':e.DISASTER_FRACTION,'max_leverage':e.MAX_LEVERAGE},'execution_adapter':'original daily refit retained; test rows require only known features, never completed future labels; training maturity strictly < fit day','funding_model':'original hourly event assignment; observed estimate only'},r.trades,r.equity)
        r.actions.to_csv(OUT/name/'actions.csv',index=False)

CASES={'pktsc':('15m','2026-08-04',run_pktsc),'pbtr':('15m','2026-07-01',run_pbtr),'sma':('15m','2026-07-29',run_sma),'sds':('15m','2026-07-29',run_sds),'mapt':('15m','2026-07-31',run_mapt),'keltner15':('15m','2026-07-22',run_keltner15),'mhef_1h':('1h','2026-07-15',run_mhef_1h),'mtpp':('15m','2026-08-04',run_mtpp),'ar_v4':('1h','2026-07-08',run_ar),'keltner_v3':('15m','2026-07-14',run_keltner),'mmtf_1h_v3':('1h','2026-07-23',run_mmtf),'mmtf_15m_v3':('15m','2026-07-23',run_mmtf),'mdtp_v1':('15m','2026-08-01',run_mdtp),'bksb_15m':('15m','2026-07-24',run_bksb),'bksb_1h':('15m','2026-07-24',run_bksb)}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('case',choices=CASES); parser.add_argument('--end',default='2026-09-05T15:00:00Z'); parser.add_argument('--suffix',default=''); args=parser.parse_args()
    from audit_common import load_prices,load_funding
    tf,date,fn=CASES[args.case]; frame=load_prices('HYPE',tf).copy(); funding=load_funding('HYPE').copy()
    frame['ts']=pd.to_datetime(frame['ts'],utc=True); funding['ts']=pd.to_datetime(funding['ts'],utc=True)
    assert not funding.empty and funding.funding_rate.notna().all()
    start=pd.Timestamp(date,tz='UTC'); end=pd.Timestamp(args.end)
    frame=frame.loc[frame.ts<end].sort_values('ts').reset_index(drop=True)
    if fn==run_mmtf: fn(args.case+args.suffix,frame,funding,tf,start,end)
    elif fn==run_bksb: fn(args.case+args.suffix,frame,funding,'1h' if '1h' in args.case else '15m',start,end)
    else: fn(args.case+args.suffix,frame,funding,start,end)
if __name__=='__main__': main()
