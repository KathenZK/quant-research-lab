"""Reuse exact startup-returned 22-asset and mixed-MU prices, with explicit funding estimates."""
from replay_repository_additions_20260911 import *
import prepare_inputs as capture

PROBES=FAMILY/'artifacts/repository_ranking_20260911/input_probes'
_native_write=write
def write(*args,**kwargs):
    _native_write(*args,**kwargs)
    key='generic' if args[0].startswith('generic_') else 'mu'
    path=OUT/args[0]/'summary.json';row=json.loads(path.read_text());proof=PROBES/(key+'.json')
    row['input_manifest']={'path':str(proof.relative_to(ROOT)),'sha256':hashlib.sha256(proof.read_bytes()).hexdigest()}
    path.write_text(json.dumps(row,ensure_ascii=False,indent=2,default=str))

def checked_frame(key,symbol):
    proof=json.loads((PROBES/(key+'.json')).read_text());f=proof['files'][symbol];path=ROOT/f['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==f['sha256']
    raw=pd.read_parquet(path)
    for col in raw:
        if col=='ts':raw[col]=pd.to_datetime(raw[col].tolist(),utc=True)
        elif isinstance(raw[col].dtype,pd.ArrowDtype) and pd.api.types.is_numeric_dtype(raw[col].dtype):raw[col]=raw[col].astype(float)
    assert raw.research_window_valid.all() and raw.research_segment_id.nunique()==1
    return raw

def observed(key):
    req=json.loads((FAMILY/f'specs/repository-{key}-input-request-20260911.json').read_text());bundle=json.loads((ROOT/req['bundle_path']).read_text());f=capture.load_observed_funding(bundle)
    out={};manifest={}
    for symbol in req['symbols']:
        events=f.events.loc[f.events.symbol.eq(symbol)&f.events.ts.ge(pd.Timestamp(req['start']))&f.events.ts.lt(pd.Timestamp(req['end']))].copy()
        assert events.event_unambiguous.all() and not events.ts.duplicated().any()
        p=PROBES/(key+'_'+symbol.split('/')[0]+'_funding.parquet');events.to_parquet(p,index=False);out[symbol]=events
        manifest[symbol]={'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'events':len(events)}
    path=PROBES/(key+'_funding_manifest.json');path.write_text(json.dumps({'bundle_sha256':req['bundle_sha256'],'files':manifest,'funding_window_verified':False},ensure_ascii=False,indent=2));return out,str(path.relative_to(ROOT))

def mu():
    family='mu/15m-donchian-trend-breakout';base='research/'+family;p=base+'/scripts/research_mu_15m_dtb.py';a=module(p,'rank_mu');frozen=a.load_freeze();selected=frozen['selected'];cfg=a.StrategyConfig(entry_window=int(selected['entry_window']),stop_atr=float(selected['stop_atr']),use_ema_regime=bool(selected['use_ema_regime']));assert a.strategy_id(cfg)==selected['strategy_id']
    symbol='MU/USDT:USDT';raw=checked_frame('mu',symbol);events,manifest=observed('mu');rates=events[symbol].groupby(events[symbol].ts.dt.floor('15min')).funding_rate.sum();raw['funding_rate']=rates.reindex(pd.DatetimeIndex(raw.ts)).fillna(0.).to_numpy();features=a.build_features(raw);start=pd.Timestamp('2026-07-21',tz='UTC')
    r=a.simulate(features,cfg,start=start,end_exclusive=data.END);t=r.trades if not r.trades.empty else pd.DataFrame(columns=['entry_ts','exit_ts'])
    write('mu_dtb','MU 15分钟 Donchian 固定观察',family,start,data.END,{'return':r.metrics['return'],'drawdown':r.metrics['max_drawdown'],'trades':len(t),'native':r.metrics},t,r.equity,
          f'手续费{cfg.fee_per_fill:.2%}/次＋滑点{cfg.slippage_per_fill:.2%}/次；原配置仓位{cfg.allocation}；已取得资金费事件估算',
          'MU为美股挂钩永续，非加密币；保留原15分钟收盘估值及比例仓位模型；特殊结算完整性未核实。',False,[p,str(a.SEARCH_PATH.relative_to(ROOT)),str((PROBES/'mu.json').relative_to(ROOT)),manifest])

def generic():
    family='asset-portfolios/1d-generic-ma7-trend';base='research/'+family;p=base+'/scripts/research_binance_1d_generic_ma7_trend_v0.py';a=module(p,'rank_generic');original_path=base+'/artifacts/binance_1d_gma7t_v0_2026-08-18_summary.json';original=json.loads((ROOT/original_path).read_text());cfg=a.StrategyConfig(**original['generic_config']);start=pd.Timestamp('2026-08-19',tz='UTC');end=pd.Timestamp('2026-09-05',tz='UTC');events,manifest=observed('generic')
    src=inspect.getsource(a.run_generic);src=src.replace('    for index, day in enumerate(daily):\n','    for index, day in enumerate(daily):\n        if day.ts < ranking_start_ms:\n            continue\n',1)
    ns=dict(a.__dict__);ns['ranking_start_ms']=int(start.timestamp()*1000);exec(compile(src,str(Path(__file__)),'exec'),ns)
    results={};sources=[p,original_path,base+'/configs/binance-1d-generic-ma7-trend-v0.json',str((PROBES/'generic.json').relative_to(ROOT)),manifest]
    for asset in original['final_included_symbols']:
        symbol=asset.removesuffix('USDT')+'/USDT:USDT';raw=checked_frame('generic',symbol);raw=raw.loc[raw.ts<end];daily=raw.set_index('ts').resample('1D').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),rows=('close','size'));assert daily.rows.eq(24).all()
        days=[SimpleNamespace(ts=int(ts.timestamp()*1000),open=float(r.open),high=float(r.high),low=float(r.low),close=float(r.close)) for ts,r in daily.iterrows()]
        hours=[SimpleNamespace(ts=int(r.ts.timestamp()*1000),open=float(r.open),high=float(r.high),low=float(r.low),close=float(r.close)) for r in raw.itertuples()]
        f=[{'funding_time':int(r.ts.timestamp()*1000),'funding_rate':float(r.funding_rate)} for r in events[symbol].itertuples()]
        r=ns['run_generic'](asset,days,hours,f,cfg);gross=ns['run_generic'](asset,days,hours,f,replace(cfg,fee_rate=0.,slippage=0.,funding_enabled=False));r['gross_daily']=gross['daily'];results[asset]=r
        c=r['daily'][['equity']].reset_index();c.ts+=pd.Timedelta(days=1);t=pd.DataFrame(r['trades']) if r['trades'] else pd.DataFrame(columns=['entry_ts','exit_ts'])
        write('generic_'+asset,asset.removesuffix('USDT')+' 日线 Generic MA7 V0',family,start,end,{'return':float(c.equity.iloc[-1])-1,'drawdown':r['metrics']['chronological_1h_mdd_pct']/100,'trades':len(t),'native':r['metrics']},t,c,
              '手续费0.1%/次＋滑点0.04%/次；原1倍固定数量；已取得资金费率估算',
              '原8月18日22币观察名单中的独立账户，非当前重新选币；1小时收盘及成交事件估值；原资金费使用事件所在小时收盘价近似，非原生标记价；资金费率不完整。',False,sources)
    conf=json.loads((ROOT/base/'configs/binance-1d-generic-ma7-trend-v0.json').read_text())['portfolio'];portfolio=a.build_portfolio(results,conf);c=portfolio['daily'][['net_equity']].rename(columns={'net_equity':'equity'}).reset_index();c.ts+=pd.Timedelta(days=1)
    # Original two-stage return-volatility warmup cannot form targets in 17 days.
    assert portfolio['weights'].eq(0).all().all()
    write('generic_portfolio','22币 日线 Generic MA7 V0 新账户组合',family,start,end,{'return':float(c.equity.iloc[-1])-1,'drawdown':0.,'trades':0,'native':portfolio['metrics']},pd.DataFrame(columns=['entry_ts','exit_ts']),c,
          '原逆波动分配、20%波动目标及3倍上限；本窗口无交易、无费用',
          '空仓新账户只有17天，原两层20日波动预热未完成，组合没有交易；不是已有历史仓位的持续运行结果，不据0回撤评价稳定。',False,sources)

if __name__=='__main__':globals()[sys.argv[1]]()
