"""Post-freeze additions. Reuse hash-checked audit inputs; never run searches."""
from pathlib import Path
import argparse, hashlib, inspect, json, sys, traceback
from dataclasses import asdict, replace
from types import SimpleNamespace
import numpy as np
import pandas as pd
import audit_common as data
import hype_other_replay as old

ROOT = Path(__file__).resolve().parents[4]
FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY/'artifacts/repository_ranking_20260911/replays'
OUT.mkdir(parents=True, exist_ok=True)
old.OUT = OUT

def module(path, name):
    return old.mod(path, name)

def write(case, name, family, start, end, metrics, trades, curve, cost, limitation, registered, sources):
    d=OUT/case; d.mkdir(exist_ok=True)
    trades.to_csv(d/'trades.csv',index=False)
    curve.to_csv(d/'equity.csv',index=False)
    row=dict(name=name, family_path='research/'+family, start=str(start), end=str(end),
             return_value=float(metrics['return']), drawdown=abs(float(metrics['drawdown'])),
             trades=int(metrics['trades']), cost=cost, limitation=limitation, registered=registered,
             source_metrics=metrics, flat_start=True, funding_window_verified=False,
             equity_path=str((d/'equity.csv').relative_to(ROOT)),source=str((d/'summary.json').relative_to(ROOT)),
             source_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources})
    row['loaded_rule_dependencies']={str(Path(m.__file__).resolve().relative_to(ROOT)):hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
       for m in list(sys.modules.values()) if getattr(m,'__file__',None) and str(Path(m.__file__).resolve()).startswith(str(ROOT/'research')) and Path(m.__file__).is_file()}
    ip=FAMILY/'artifacts/inputs/manifest.json'
    row['input_manifest']={'path':str(ip.relative_to(ROOT)),'sha256':hashlib.sha256(ip.read_bytes()).hexdigest()}
    (d/'summary.json').write_text(json.dumps(row,ensure_ascii=False,indent=2,default=str))
    print(case,{k:row[k] for k in ['return_value','drawdown','trades']},flush=True)

def aggregate(frame, tf, minutes):
    f=frame.set_index('ts').resample(tf).agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),volume=('volume','sum'),rows=('close','size'))
    return f.loc[f.rows.eq(minutes/15)].drop(columns='rows').reset_index()

def hto():
    family='hype/1d-15m-hierarchical-trend-opportunity'; base='research/'+family
    e=module(base+'/scripts/hto_engine.py','ranking_hto'); a=module(base+'/scripts/hto_v2.py','ranking_hto_v2')
    p=ROOT/base/'artifacts/hype_d15_hto_v3_tune_2026-07-29.json'
    frozen=json.loads(p.read_text())
    cfg=e.config_from_dict(frozen['engine_config'])
    assert e.config_sha256(cfg)==frozen['config_sha256']
    frame=data.load_prices(); funding=data.load_funding(); terminal=data.END
    # Preserve the exact feature-building body; replace only frozen-file loading.
    src=inspect.getsource(e.build_book); body=src[src.index('    ts = pd.DatetimeIndex(frame["ts"])'):]
    body=body.replace('    funding = pd.read_parquet(FUNDING_PATH)\n','')
    code='def from_frames(frame, funding, terminal):\n    oos_start = terminal\n'+body
    ns=dict(e.__dict__);exec(compile(code,str(Path(__file__)), 'exec'),ns)
    book=ns['from_frames'](frame,funding,terminal)
    start=pd.Timestamp('2026-07-30T00:00:00Z')
    r=e.run_backtest(book,cfg,start_ts=start,end_ts=terminal,detailed=True)
    assert all(pd.Timestamp(t['entry_ts'])>=start for t in r.trades)
    write('hto_v3','HYPE 日线+15分钟 HTO V3',family,start,terminal,
          dict(return_=0, **{'return':r.metrics['total_return'],'drawdown':r.metrics['max_drawdown'],'trades':len(r.trades),'native':r.metrics}),
          pd.DataFrame(r.trades),pd.DataFrame(r.equity_path),'手续费0.1%/次＋滑点0.04%/次；原2.5倍仓位；已取得资金费率估算',
          '最大回撤沿用原引擎盘中保守估计；资金费率不完整；日线只用前一完整日。',True,
          [base+'/scripts/hto_engine.py',str(p.relative_to(ROOT)),base+'/specs/hype-d15-hto-v3-spec.md',base+'/decision-log.md'])

def bksb(tf):
    start=pd.Timestamp('2026-07-24T00:00:00Z');end=data.END.floor(tf)
    frame=data.load_prices();frame=frame.loc[frame.ts<end].copy();funding=data.load_funding();funding=funding.loc[funding.ts<end]
    case='bksb_'+tf
    old.run_bksb(case,frame,funding,tf,start,end)
    d=OUT/case;payload=json.loads((d/'summary.json').read_text());t=pd.read_csv(d/'trades.csv');c=pd.read_csv(d/'equity.csv')
    # Keep the native payload as well as the normalized ranking row.
    (d/'native_summary.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
    write(case,f'HYPE {tf} BKSB 固定基线',f'hype/{tf}-bollinger-keltner-squeeze-breakout',start,end,
          {'return':payload['curve_return'],'drawdown':payload['curve_close_drawdown'],'trades':len(t)},t,c,
          '手续费0.1%/次＋滑点0.04%/次；原1倍仓位；已取得资金费率估算',
          '未登记基线；15分钟收盘估值，原引擎退出；资金费率不完整。',False,
          [f'research/hype/{tf}-bollinger-keltner-squeeze-breakout/scripts/run_baseline.py',f'research/hype/{tf}-bollinger-keltner-squeeze-breakout/decision-log.md','research/_shared-kernels/bollinger-keltner-squeeze-breakout/v1/engine.py'])

def mhef():
    family='hype/1d-multi-horizon-ema-forecast';base='research/'+family
    p=base+'/scripts/research_hype_1d_multi_horizon_ema_forecast.py';a=module(p,'ranking_daily_mhef');e=a.load_engine()
    frame,_=a.aggregate_complete_daily(data.load_prices(tf='1h'));funding=data.load_funding()
    features=a.build_classic_ewmac_forecasts(frame,e);cfg=e.ForecastConfig();start=pd.Timestamp('2026-07-15T00:00:00Z');end=pd.Timestamp('2026-09-05T00:00:00Z')
    i=int(pd.DatetimeIndex(features.ts).searchsorted(start))
    for buffer in [0.,.1]:
        case=f'mhef_daily_{buffer:.2f}'
        r=e.backtest_target(features,funding,features.forecast,name=case,timeframe='1d',buffer=buffer,config=cfg,start_index=i)
        # Source path values at open; settle its final real day and closing costs.
        last=r.path.iloc[-1];pos=float(last.position);mark=float(frame.close.iloc[-1]);eq=float(last.equity_net)
        fr=float(funding.loc[(funding.ts>pd.Timestamp(last.ts))&(funding.ts<end),'funding_rate'].sum())
        before=eq*(1+pos*(mark/float(last.open)-1));after=before-before*pos*fr
        final=after*(1-abs(pos)*(.001+.0004))
        c=r.path[['ts','equity_net']].rename(columns={'equity_net':'equity'})
        c=pd.concat([c,pd.DataFrame([{'ts':end,'equity':final}])],ignore_index=True)
        dd=float((c.equity/pd.concat([pd.Series([1.]),c.equity],ignore_index=True).cummax().iloc[1:].to_numpy()-1).min())
        pp=r.path.position.to_numpy();count=int(((np.sign(pp)!=np.r_[0,np.sign(pp[:-1])])&(pp!=0)).sum())
        write(case,f'HYPE 日线 MHEF 缓冲{buffer:.2f}',family,start,end,
              {'return':final-1,'drawdown':dd,'trades':count,'count_unit':'方向入场次数','native':r.metrics},r.path,c,
              '手续费0.1%/次＋滑点0.04%/次；动态目标仓位绝对值≤1；已取得资金费率估算',
              '计数为方向入场次数，非完整交易；连续调仓；每日开盘估值，资金费率不完整。',False,[p,base+'/decision-log.md','research/_shared-kernels/multi-horizon-ema-forecast/v1/engine.py'])

def rs4():
    family='hype/6h-rs4-regime-switch';base='research/'+family
    p=base+'/scripts/research_hype_6h_rs4_simplified_backtest.py';m=module(p,'ranking_rs4');a=m.abl
    raw=data.load_prices();bars=aggregate(raw,'6h',360);end=pd.Timestamp('2026-09-05T12:00:00Z')
    bars=bars.loc[bars.ts<end].copy()
    # A valuation sentinel uses the observed terminal open, never its future OHLC.
    opening=float(raw.loc[raw.ts.eq(end),'open'].iloc[0]);sentinel={'ts':end,'open':opening,'high':opening,'low':opening,'close':opening,'volume':0.}
    bars=pd.concat([bars,pd.DataFrame([sentinel])],ignore_index=True)
    spec=m.comparison_specs()[-1];features=a.attach_features_for_spec(bars,data.load_funding(),spec)
    start=pd.Timestamp('2026-06-29T00:00:00Z');f=features.loc[features.ts>=start].reset_index(drop=True)
    total=np.zeros(len(f));alltrades=[];legs=[]
    for name,calc,w in [('v10',a.simulate_v10,1.),('melt',a.simulate_melt,spec.weight)]:
        pos=calc(f,spec);pos[-1]=0 # do not initiate a new terminal signal; settle the old position
        leg=a.leg_returns(name,f,pos,spec);ret=leg.returns.copy()
        ret[-1]=-abs(float(pos[-2]))*m.base.ONE_WAY_COST*spec.cost_multiplier
        total+=w*ret
        alltrades+=m.base.extract_trades(name,f,pos,ret)
        legs.append(pd.DataFrame({'ts':f.ts,'leg':name,'position':pos,'return':ret}))
    eq=np.cumprod(1+total);dd=float((eq/np.maximum.accumulate(np.r_[1.,eq])[1:]-1).min())
    curve=pd.DataFrame({'ts':f.ts,'equity':eq});t=pd.DataFrame(alltrades)
    write('rs4_v1','HYPE 6小时 RS4 V1',family,start,end,{'return':eq[-1]-1,'drawdown':dd,'trades':len(t),'count_unit':'子策略交易'},t,curve,
          '手续费0.045%/次＋滑点0.05%/次；原双子策略相加；已取得资金费率估算',
          '原收益相加/开盘到开盘模型，非统一固定数量账户；没有盘中止损估值；仅Binance替代数据；资金费率不完整。',True,
          [p,base+'/scripts/research_hype_6h_rs4_parameter_ablation.py',base+'/decision-log.md'])
    pd.concat(legs).to_csv(OUT/'rs4_v1/legs.csv',index=False)

def abt():
    family='hype/1d-ma7-asymmetric-body-trend';base='research/'+family;pre=base+'/scripts/'
    adapter=module(pre+'hype_1d_ma7_v4_fair_adapter.py','ranking_abt_adapter')
    # Check all retained rule pins, while supplying the explicitly new audit data.
    for field in ['ORIGINAL_HARNESS','ORIGINAL_ENGINE','CONFIRMATION','FORMATION','SEARCH','BASE','SELECTED_SUMMARY']:
        adapter._assert_hash(getattr(adapter,field+'_PATH'),getattr(adapter,field+'_SHA256'))
    original=module(str(adapter.ORIGINAL_HARNESS_PATH.relative_to(ROOT)),'ranking_abt_original')
    oe,base_mod,search=original.modules();parent=base_mod.load_parent()
    hourly=data.load_prices(tf='1h');funding=data.load_funding();end=pd.Timestamp('2026-09-05T00:00:00Z')
    hourly=hourly.loc[hourly.ts<=end].copy();fq={'funding_window_verified':False,'source':'current audit observed events'}
    book=base_mod.build_book(parent,hourly,{},funding,fq,phase_hours=0);features=search.build_features(book,hourly,funding)
    market=SimpleNamespace(book=book,features=features,hourly=hourly,funding=funding,audit={})
    confirmation=module(str(adapter.CONFIRMATION_PATH.relative_to(ROOT)),'ranking_abt_confirm')
    formation=module(str(adapter.FORMATION_PATH.relative_to(ROOT)),'ranking_abt_formation')
    selected=json.loads(adapter.SELECTED_SUMMARY_PATH.read_text())['historically_profitable_all_checks'][0]
    assert selected['label']=='post_reveal_combined_observation_041'
    long=search.Config(**selected['long_config']);short=replace(search.Config(**selected['short_config']),exit_buffer_atr=.75,cooldown_days=3)
    context=adapter.V4FairContext(original,confirmation,formation,search,market,long,short,confirmation.build_filtered_backtest(formation,search,confirmation.MA_ONLY),())
    v6=module(pre+'audit_hype_1d_ma7_abt_v6_full_parameter_ablation.py','ranking_abt_v6')
    engine=module(pre+'hype_1d_ma7_profit_exit_handoff_continuity_engine.py','ranking_abt_pehc')
    run=module(pre+'diagnose_hype_1d_ma7_abt_v7_1_oapp_rebound_reset.py','ranking_abt_run')
    start=pd.Timestamp('2026-08-12T00:00:00Z');i=int(book.ts.searchsorted(start))
    metrics,result,_=run.run_arm(v6,engine,context,'CONTROL',window=(i,book.count),retain=True)
    # Retain the hourly accounting trace used by normalize, rather than labeling
    # the slightly different original daily curve as the same account result.
    src=inspect.getsource(v6.chronological_replay)
    src=src.replace('    equity = 1.0\n','    trace = []\n    equity = 1.0\n',1)
    src=src.replace('        peak = max(peak, equity)\n','        trace.append({"ts": ts, "kind": kind, "equity": equity, "qty": qty, "mark_price": mark_price})\n        peak = max(peak, equity)\n',1)
    src=src.replace('        "terminal_equity": equity,','        "trace": trace,\n        "terminal_equity": equity,',1)
    ns=dict(v6.__dict__);exec(compile(src,str(Path(__file__)),'exec'),ns)
    hourly_replay=ns['chronological_replay'](context,result.raw,slippage=.0004,include_funding=True)
    assert abs(hourly_replay['terminal_equity']-1-metrics['net_return_pct']/100)<1e-12
    c=pd.DataFrame(hourly_replay.pop('trace'));c=c.loc[c.ts>=start].copy()
    t=pd.DataFrame(result.raw.trades).rename(columns={'net_return':'engine_daily_net_return','net_pnl':'engine_daily_net_pnl'})
    for ix,tr in t.iterrows():
        en=c.loc[c.ts.eq(pd.Timestamp(tr.entry_ts))&c.kind.eq('entry')].iloc[-1]
        ex=c.loc[c.ts.eq(pd.Timestamp(tr.exit_ts))&c.kind.eq('exit')&c.qty.eq(0)].iloc[-1]
        before=float(en.equity)+abs(float(en.qty))*float(tr.entry_price)*.0014
        t.loc[ix,'entry_equity']=before;t.loc[ix,'exit_equity']=float(ex.equity)
        t.loc[ix,'net_return']=float(ex.equity)/before-1;t.loc[ix,'net_pnl']=float(ex.equity)-before
    assert t.empty or pd.to_datetime(t.entry_ts,utc=True).ge(start).all()
    write('abt_v71','HYPE 日线 MA7 ABT V7.1',family,start,end,
          {'return':metrics['net_return_pct']/100,'drawdown':metrics['chronological_1h_mdd_pct']/100,'trades':len(t),'native':metrics},t,c,
          '手续费0.1%/次＋滑点0.04%/次；1倍固定数量；已取得资金费率估算',
          '按1小时开盘及交易事件顺序估值的回撤；与线上模拟实例的启动日不同；资金费率不完整。',True,
          [base+'/specs/hype-1d-ma7-abt-v7-1-spec.md',pre+'hype_1d_ma7_profit_exit_handoff_continuity_engine.py',pre+'hype_1d_ma7_v4_fair_adapter.py'])

def shared_ma7():
    family='asset-portfolios/1d-ma7-asset-specific-search';base='research/'+family
    h=module(base+'/scripts/audit_binance_1d_ma7_shared_v1_long_history.py','ranking_shared_history')
    transfer=h.load_module(h.TRANSFER_PATH,h.TRANSFER_SHA256,'ranking_shared_transfer');e=transfer.load_engine()
    a=module(base+'/scripts/render_binance_1d_ma7_as_search_v2_trade_paths.py','ranking_shared_v2')
    long,short=a.v2_configs(h,e)
    start=pd.Timestamp('2026-08-18T00:00:00Z');end=pd.Timestamp('2026-09-05T00:00:00Z')
    for asset in ['BTC','ETH']:
        hourly=data.load_prices(asset,'1h');hourly=hourly.loc[hourly.ts<=end].copy();funding=data.load_funding(asset)
        book=transfer.build_book(asset+'USDT',hourly,{'funding':{'funding_window_verified':False}},phase_hours=0);features=e.build_features(book,hourly,funding)
        r=h.run_window(e,book,features,long,short,start=int(book.ts.searchsorted(start)),end=book.count,slippage=.0004,signal_lag=0,retain=True)
        write('shared_v2_'+asset,asset+' 日线 MA7共享参数 V2',family,start,end,
              {'return':r.metrics['net_return_pct']/100,'drawdown':r.metrics['max_drawdown_pct']/100,'trades':len(r.trades),'native':r.metrics},pd.DataFrame(r.trades),pd.DataFrame(r.path),
              '手续费0.1%/次＋滑点0.04%/次；1倍固定数量；已取得资金费率估算',
              '两个资产独立账户，不拼成组合；原引擎盘中保守回撤；资金费率不完整。',True,
              [base+'/specs/binance-1d-ma7-as-search-v2-spec.md',str(h.TRANSFER_PATH.relative_to(ROOT)),str(Path(e.__file__).relative_to(ROOT))])

def four_hour():
    family='hype/4h-ma7-close-reversal';base='research/'+family
    p=base+'/scripts/research_hype_4h_ma7_close_reversal.py';e=module(p,'ranking_four_cr')
    adapter=e.load_module(e.SOURCE_ADAPTER,e.SOURCE_ADAPTER_SHA256,'ranking_four_adapter')
    end=pd.Timestamp('2026-09-05T12:00:00Z');hourly=data.load_prices(tf='1h');hourly=hourly.loc[hourly.ts<=end].copy()
    bundle=e.build_bundle(adapter,hourly,{},data.load_funding(),{},phase_hours=0)
    rsi_family='hype/4h-ma7-rsi6-asymmetric-reversal';rsi_p='research/'+rsi_family+'/scripts/research_hype_4h_ma7_rsi6_asymmetric_reversal.py';a=module(rsi_p,'ranking_four_rsi')
    for case,start,fam,name,var in [('four_cr','2026-08-07',family,'HYPE 4小时 MA7收盘反手 固定基线',None),('four_rsi','2026-08-07',rsi_family,'HYPE 4小时 MA7+RSI6 固定基线',a.VARIANT_BASELINE),('four_rsi_v2','2026-08-08',rsi_family,'HYPE 4小时 MA7+RSI6 V2观察',a.VARIANT_CROSS_REENTRY)]:
        start=pd.Timestamp(start,tz='UTC');i=int(pd.DatetimeIndex(bundle.bars.ts).searchsorted(start))
        if var is None:r=e.backtest(bundle,route='combined',start_index=i,terminal_index=bundle.count,retain=True)
        else:r,_=a.run_strategy(e,bundle,start_index=i,terminal_index=bundle.count,retain=True,variant=var)
        write(case,name,fam,start,end,{'return':r.metrics['net_return_pct']/100,'drawdown':r.metrics['max_drawdown_pct']/100,'trades':len(r.trades),'native':r.metrics},pd.DataFrame(r.trades),pd.DataFrame(r.path),
              '手续费0.1%/次＋滑点0.04%/次；约1倍仓位；已取得资金费率估算',
              '未登记的固定观察；日内1小时风险估值；资金费率不完整。',False,[p,rsi_p,'research/'+fam+'/decision-log.md'])

def crisis():
    family='asset-portfolios/1d-btceth-crisis-override-shadow-trend';base='research/'+family
    p=base+'/scripts/research_binance_1d_be_cost_p0.py';e=module(p,'ranking_crisis');cb=e.load_cbct();helper=cb.load_data_helper()
    start=pd.Timestamp('2026-08-15T00:00:00Z');end=pd.Timestamp('2026-09-05T00:00:00Z')
    helper.COMMON_START=start;helper.DEVELOPMENT_END=end
    hourly={};funding={}
    for asset in ['BTC','ETH']:
        h=data.load_prices(asset,'1h');h=h.loc[h.ts<=end,['ts','open','high','low','close']].copy();hourly[asset+'USDT']=h
        f=data.load_funding(asset);f=f.loc[f.ts.ge(start)&f.ts.le(end)].copy()
        assert f.mark_price.notna().all() and f.mark_price.gt(0).all()
        funding[asset+'USDT']=f
    daily,hourly_book,df=cb.prepare_markets(helper,hourly,funding)
    shadow=e.shadow_replay(cb,helper,daily,hourly_book,df,slippage=.0004,delay_days=0)
    state=e.crisis_execution(df,e.Config(200,60,3))
    r=e.route_replay(cb,helper,daily,hourly_book,df,shadow,state,slippage=.0004,retain=True)
    write('crisis_v1','BTC/ETH 日线危机覆盖 V1',family,start,end,{'return':r.equity_multiple-1,'drawdown':r.ordered_mdd_pct/100,'trades':len(r.trades),'counts':r.counts},pd.DataFrame(r.trades),r.path,
          '手续费0.1%/次＋滑点0.04%/次；账户约1倍固定数量；已取得资金费率估算',
          '双资产完整账户；EMA200使用本轮自2025-05的预热；含已取得事件，完整资金费率日历未证明。',True,[p,str(cb.DATA_HELPER_PATH.relative_to(ROOT)),base+'/specs/binance-1d-be-cost-v1-spec.md'])

def cta():
    family='btc/1d-classic-cta-trend';base='research/'+family;p=base+'/scripts/research_btc_1d_classic_cta.py';a=module(p,'ranking_btc_cta');e=a.load_engine()
    m=module('research/hype/1d-multi-horizon-ema-forecast/scripts/research_hype_1d_multi_horizon_ema_forecast.py','ranking_cta_aggregate')
    frame,_=m.aggregate_complete_daily(data.load_prices('BTC','1h'));funding=data.load_funding('BTC');features=a.build_classic_cta_features(frame,e)
    cfg=e.ForecastConfig(ema_pairs=a.EMA_PAIRS,weights=a.EMA_WEIGHTS,max_abs_position=a.WEIGHT_CAP)
    start=pd.Timestamp('2026-08-18T00:00:00Z');end=pd.Timestamp('2026-09-05T00:00:00Z');i=int(pd.DatetimeIndex(features.ts).searchsorted(start))
    for buffer in [0.,.1]:
        case=f'btc_cta_{buffer:.2f}'
        r=a.run_named(e,features,funding,features.desired_position,name=case,start_index=i,config=cfg,buffer_series=features.position_buffer if buffer else None)
        last=r.path.iloc[-1];pos=float(last.position);mark=float(frame.close.iloc[-1]);eq=float(last.equity_net)
        fr=float(funding.loc[(funding.ts>pd.Timestamp(last.ts))&(funding.ts<end),'funding_rate'].sum())
        before=eq*(1+pos*(mark/float(last.open)-1));final=(before-before*pos*fr)*(1-abs(pos)*(.001+.0004))
        c=pd.concat([r.path[['ts','equity_net']].rename(columns={'equity_net':'equity'}),pd.DataFrame([{'ts':end,'equity':final}])],ignore_index=True)
        dd=float((c.equity/np.maximum.accumulate(np.r_[1.,c.equity])[1:]-1).min());pp=r.path.position.to_numpy();count=int(((np.sign(pp)!=np.r_[0,np.sign(pp[:-1])])&(pp!=0)).sum())
        write(case,f'BTC 日线经典CTA 缓冲{buffer:.2f}',family,start,end,{'return':final-1,'drawdown':dd,'trades':count,'count_unit':'方向入场次数'},r.path,c,
              '手续费0.1%/次＋滑点0.04%/次；20%目标波动、最高2倍目标仓位；已取得资金费率估算',
              '计数为方向入场次数；每日调仓，按每日开盘估值；EMA256使用2025-05起预热；资金费率不完整。',False,[p,base+'/specs/btc-1d-ccta-literature-baseline-2026-08-17.md'])

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('case',choices=['hto','bksb4h','bksb1d','mhef','rs4','abt','shared','four','crisis','cta']);args=parser.parse_args()
    try:
        {'hto':hto,'bksb4h':lambda:bksb('4h'),'bksb1d':lambda:bksb('1d'),'mhef':mhef,'rs4':rs4,'abt':abt,'shared':shared_ma7,'four':four_hour,'crisis':crisis,'cta':cta}[args.case]()
    except Exception as exc:
        (OUT/(args.case+'_failure.json')).write_text(json.dumps({'case':args.case,'error':str(exc),'traceback':traceback.format_exc()},indent=2))
        raise
