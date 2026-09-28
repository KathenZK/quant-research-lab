"""Remaining fixed transfers; import original rules, replace only audited input loading."""
from replay_repository_additions_20260911 import *

FQ={'funding_window_verified':False,'source':'current audit observed funding events'}
COST='手续费0.1%/次＋滑点0.04%/次；原1倍固定数量；已取得资金费率估算'

def save_raw(case,name,family,start,result,sources,limitation='原引擎盘中保守估值；资金费率不完整。',cost=COST):
    t=pd.DataFrame(result.trades)
    if t.empty:t=pd.DataFrame(columns=['entry_ts','exit_ts'])
    c=pd.DataFrame(result.path)
    # Some original engines retain the last pre-liquidation mark only.
    equity_column=next(col for col in ['equity','net_equity','post_action_equity'] if col in c)
    if abs(float(c[equity_column].iloc[-1])-float(result.metrics['equity_multiple']))>1e-12:
        native=c.copy();d=OUT/case;d.mkdir(exist_ok=True);native.to_csv(d/'native_equity_before_terminal_settlement.csv',index=False)
        c=pd.concat([c,pd.DataFrame([{'ts':result.metrics['end_ts'],equity_column:result.metrics['equity_multiple'],'action':'terminal_settlement'}])],ignore_index=True)
    write(case,name,family,start,result.metrics['end_ts'],
          {'return':result.metrics['net_return_pct']/100,'drawdown':result.metrics['max_drawdown_pct']/100,'trades':len(t),'native':result.metrics},t,c,cost,limitation,False,sources)

def four_abt():
    family='hype/4h-ma7-asymmetric-body-trend';base='research/'+family
    p=base+'/scripts/research_hype_4h_ma7_v1_transfer.py';a=module(p,'rank_four_abt')
    e=a.load_module(a.ENGINE_PATH,a.ENGINE_SHA256,'rank_four_abt_engine');b=a.load_module(a.BASE_PATH,a.BASE_SHA256,'rank_four_abt_base')
    hourly=data.load_prices(tf='1h');hourly=hourly.loc[hourly.ts<=pd.Timestamp('2026-09-05T12:00Z')]
    book=a.build_book(b,hourly,{},FQ,phase_hours=0);f=a.build_features(e,book,hourly,data.load_funding());lc,sc=a.frozen_configs(e)
    variants=[('bar','按K线根数直迁','2026-08-06',(lc,sc)),('clock','按原持有天数直迁','2026-08-06',(replace(lc,max_hold_days=lc.max_hold_days*6,cooldown_days=lc.cooldown_days*6),replace(sc,max_hold_days=sc.max_hold_days*6,cooldown_days=sc.cooldown_days*6)))]
    selected_path=base+'/artifacts/hype_4h_ma7_native_trend_summary_2026-08-06.json';s=json.loads((ROOT/selected_path).read_text())['selected']
    variants.append(('native','固定原生观察','2026-08-07',(e.Config(**s['long_config']),e.Config(**s['short_config']))))
    for key,label,day,(long,short) in variants:
        start=pd.Timestamp(day,tz='UTC');r=a.run(e,book,f,long,short,start=int(book.ts.searchsorted(start)),end=book.count)
        save_raw('four_abt_'+key,'HYPE 4小时 ABT '+label,family,start,r,[p,selected_path,base+'/decision-log.md'])

def weekly():
    family='btc/1w-ma7-asymmetric-body-trend';base='research/'+family;p=base+'/scripts/research_btc_1w_ma7_v1_transfer.py';a=module(p,'rank_weekly')
    x=a.load_module(a.TRANSFER_PATH,a.TRANSFER_SHA256,'rank_weekly_transfer');e=x.load_engine();a.adapt_weekly_backtest(e)
    hourly=data.load_prices('BTC','1h');book,_=a.build_weekly_book(x,hourly,{'funding':FQ},phase_hours=0);f=a.build_weekly_features(e,book,hourly,data.load_funding('BTC'));start=pd.Timestamp('2026-08-10',tz='UTC')
    for key,(lc,sc) in a.time_contracts(e,x).items():
        r=a.run(e,book,f,lc,sc,start=int(book.ts.searchsorted(start)),end=book.count)
        save_raw('weekly_'+key,'BTC 周线 ABT '+('按根数直迁' if key=='bar_transfer' else '按原天数直迁'),family,start,r,[p,base+'/specs/btc-1w-ma7-v1-transfer-contract-2026-08-05.md'], '周一完整周线，期末仅到8月31日；原引擎盘中保守估值；资金费率不完整。')

def pyramiding():
    family='asset-portfolios/1d-ma7-ma30-pyramiding-transfer';base='research/'+family;p=base+'/scripts/research_binance_1d_ma7_ma30_pyramiding_transfer.py';a=module(p,'rank_pyr')
    assert hashlib.sha256(a.MA_SCRIPT.read_bytes()).hexdigest()==a.MA_SCRIPT_SHA256
    ma=a.load_module(a.MA_SCRIPT,'rank_pyr_ma');parent=ma._load_parent();cfg=a.frozen_config(ma);start=pd.Timestamp('2026-07-31',tz='UTC');a.TERMINAL_TS=pd.Timestamp('2026-09-05',tz='UTC')
    for asset in ['BTC','ETH']:
        hourly=data.load_prices(asset,'1h');funding=data.load_funding(asset)
        a.load_and_audit_hourly=lambda symbol,spec:(hourly,funding,{'funding':FQ})
        book=a.build_book(ma,parent,asset+'USDT',{});r=ma.backtest(cfg,book,start_index=int(book.ts.searchsorted(start)),terminal_index=book.daily_count,retain=True)
        save_raw('pyr_transfer_'+asset,asset+' 日线 MA7/MA30 加仓直迁',family,start,r,[p,base+'/specs/binance-1d-ma7-ma30-pyramiding-transfer-contract-2026-07-30.md'], '原日线盘中保守估值及分次加仓模型；实际杠杆可能超过3倍；资金费率不完整。','手续费0.1%/次＋滑点0.04%/次；原0.5倍起仓及1.5倍加仓增量；已取得资金费率估算')

def separated():
    family='asset-portfolios/1d-ma7-separated-trend-transfer';base='research/'+family;p=base+'/scripts/research_binance_1d_ma7_abt_v6_transfer.py';a=module(p,'rank_v6_transfer')
    x=a.load_module(a.XFER_PATH,'rank_v6_xfer');e=x.load_engine();adapter=a.load_module(a.ADAPTER_PATH,'rank_v6_adapter');pehc=a.load_module(a.PEHC_ENGINE_PATH,'rank_v6_pehc')
    # Construct the original pinned rule context without its historical data reader.
    for field in ['ORIGINAL_HARNESS','ORIGINAL_ENGINE','CONFIRMATION','FORMATION','SEARCH','BASE','SELECTED_SUMMARY']:
        adapter._assert_hash(getattr(adapter,field+'_PATH'),getattr(adapter,field+'_SHA256'))
    original=module(str(adapter.ORIGINAL_HARNESS_PATH.relative_to(ROOT)),'rank_v6_original')
    confirmation=module(str(adapter.CONFIRMATION_PATH.relative_to(ROOT)),'rank_v6_confirmation');formation=module(str(adapter.FORMATION_PATH.relative_to(ROOT)),'rank_v6_formation')
    selected=json.loads(adapter.SELECTED_SUMMARY_PATH.read_text())['historically_profitable_all_checks'][0];assert selected['label']=='post_reveal_combined_observation_041'
    long=e.Config(**selected['long_config']);short=replace(e.Config(**selected['short_config']),exit_buffer_atr=.75,cooldown_days=3)
    start=pd.Timestamp('2026-08-11',tz='UTC');end=pd.Timestamp('2026-09-05',tz='UTC')
    for asset in ['BTC','ETH']:
        hourly=data.load_prices(asset,'1h');hourly=hourly.loc[hourly.ts<=end];funding=data.load_funding(asset)
        book=x.build_book(asset+'USDT',hourly,{'funding':FQ},phase_hours=0);f=e.build_features(book,hourly,funding)
        market=SimpleNamespace(book=book,features=f,hourly=hourly,funding=funding,audit={})
        template=adapter.V4FairContext(original,confirmation,formation,e,market,long,short,confirmation.build_filtered_backtest(formation,e,confirmation.MA_ONLY),())
        context=a.TransferContext(template,book,f);r=a.run_v6(pehc,context,a.fixed_v6_config(pehc),start=int(book.ts.searchsorted(start)),end=book.count,retain=True)
        save_raw('v6_transfer_'+asset,asset+' 日线 MA7 ABT V6 直迁',family,start,r.raw,[p,str(a.ADAPTER_PATH.relative_to(ROOT)),base+'/decision-log.md'])

def pic():
    family='asset-portfolios/1h-price-impulse-campaign';base='research/'+family;p=base+'/scripts/research_binance_1h_pic_v2.py';a=module(p,'rank_pic');v1=a.load_v1_module();shared=v1.load_v0_module();start=pd.Timestamp('2026-08-04',tz='UTC');end=data.END
    for asset in ['ETH','BTC','HYPE','SOL']:
        raw=data.load_prices(asset,'1h');raw=raw.loc[raw.ts<end].copy();funding=data.load_funding(asset)
        # Original frame clock is the close/visibility time; funding belongs to its open.
        raw=raw.set_index('ts');rates=funding.groupby(funding.ts.dt.floor('h')).funding_rate.sum()
        raw['funding_rate']=rates.reindex(raw.index).fillna(0.)
        raw.index=raw.index+pd.Timedelta(hours=1)
        r=v1.run_backtest(raw,a.config_for(v1),shared,start,end)
        t=r.campaigns if not r.campaigns.empty else pd.DataFrame(columns=['entry_ts','exit_ts']);c=r.equity
        write('pic_v2_'+asset,asset+' 1小时 PIC V2 固定观察',family,start,end,{'return':r.metrics['total_return_pct']/100,'drawdown':r.metrics['max_drawdown_pct']/100,'trades':len(t),'count_unit':'段交易（含加减仓）','native':r.metrics},t,c,
              '手续费0.1%/次＋滑点0.04%/次；原风险预算1%/操作0.9%，最高3倍；已取得资金费率估算',
              '1小时收盘净值回撤；ETH为原主资产，其余为原对照；没有事件的小时仅表示本次未取得事件，资金费率完整性未证明。',False,[p,base+'/scripts/research_binance_1h_pic_v1.py',base+'/specs/binance-1h-pic-v2-risk-invariant-contract-2026-08-03.md'])
        r.actions.to_csv(OUT/('pic_v2_'+asset)/'actions.csv',index=False)

def mii():
    family='asset-portfolios/15m-multi-indicator-intraday';base='research/'+family;p=base+'/scripts/research_binance_15m_mii_btc_eth_constrained_search.py';a=module(p,'rank_mii_transfer');start=pd.Timestamp('2026-07-01',tz='UTC')
    for asset,cfg in [('BTC',a.TransferConfig(9,35,60,'long',.0035,1.,.009,.024,8)),('ETH',a.TransferConfig(9,40,60,'short',.0045,1.,.0075,.024,24))]:
        raw=data.load_prices(asset);raw=raw.loc[raw.ts<data.END];context=a.build_context(raw)
        state=a.signal_state(context.features,cfg.signal);mask=context.features.ts.iloc[state.signal_i].ge(start).to_numpy();state=replace(state,signal_i=state.signal_i[mask],directions=state.directions[mask]);context.signal_cache[cfg.signal.name]=state
        trades=a.raw_trades(context,cfg,1);picked=a.v1.engine.selected_trades(trades,cfg.filter)
        metric=a.evaluate_window(trades,cfg,start,data.END);eq=1.;curve=[{'ts':start,'equity':eq}];records=[]
        for tr in picked:
            before=eq;eq*=max(0.,1+cfg.exposure*(tr.raw_return-a.ROUND_TRIP_COST));rec=asdict(tr);rec.update(net_pnl=eq-before,entry_equity=before,exit_equity=eq);records.append(rec);curve.append({'ts':tr.exit_ts,'equity':eq})
        assert abs(eq-1-metric['total_return_pct']/100)<1e-10
        curve.append({'ts':data.END,'equity':eq});t=pd.DataFrame(records) if records else pd.DataFrame(columns=['entry_ts','exit_ts'])
        write('mii_transfer_'+asset,asset+' 15分钟 MII 固定迁移观察',family,start,data.END,{'return':eq-1,'drawdown':metric['max_drawdown_pct']/100,'trades':len(t),'native':metric},t,pd.DataFrame(curve),
              '手续费0.1%/次＋滑点0.04%/次；原1倍；原研究不计资金费率',
              '原逐笔复利模型；原最差交易路径估算回撤，未逐时更新未实现盈利高点；资金费率未计入；仅K+1主回放，非延迟稳健性结论。',False,[p,base+'/README.md',base+'/decision-log.md'])

def turtle():
    family='asset-portfolios/1d-turtle-breakout';base='research/'+family;p=base+'/scripts/research_binance_1d_turtle_breakout.py';a=module(p,'rank_turtle')
    # Preserve full indicator warmup, then reset the account at the post-freeze start.
    src=inspect.getsource(a.backtest_symbol);needle='    equity_gross = 1.0\n';src=src.replace(needle,"    data = data.loc[data.ts >= ranking_start].reset_index(drop=True)\n"+needle,1)
    ns=dict(a.__dict__);ns['ranking_start']=pd.Timestamp('2026-06-28',tz='UTC');exec(compile(src,str(Path(__file__)),'exec'),ns)
    for asset in ['BTC','ETH','HYPE']:
        raw=data.load_prices(asset,'1h');bars=raw.set_index('ts').resample('1d').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),rows=('close','size'))
        bars=bars.loc[bars.rows.eq(24)&(bars.index<pd.Timestamp('2026-09-05',tz='UTC'))].drop(columns='rows').reset_index()
        for i,spec in enumerate(a.SIZING_SPECS):
            r=ns['backtest_symbol'](bars,asset+'USDT',spec);t=pd.DataFrame(r.trades) if r.trades else pd.DataFrame(columns=['entry_ts','exit_ts']);c=r.equity[['ts','equity_net']].rename(columns={'equity_net':'equity'})
            for col in ['entry_ts','exit_ts']:t[col]=pd.to_datetime(t[col],utc=True)+pd.Timedelta(days=1)
            c.ts=pd.to_datetime(c.ts,utc=True)+pd.Timedelta(days=1)
            write('turtle_'+asset+'_'+str(i),asset+' 日线海龟20/10·'+spec.name,family,ns['ranking_start'],c.ts.iloc[-1],{'return':r.summary['strategy_total_return_net_pct']/100,'drawdown':r.summary['strategy_max_drawdown_net_pct']/100,'trades':len(t),'native':r.summary},t,c,
                  '手续费0.05%/次＋滑点0.025%/次；'+spec.description+'；原研究未计资金费率',
                  '同日收盘产生信号并按同收盘价成交的原诊断假设，不能视为可实时实现；日线收盘回撤；资金费率未计入。',False,[p,base+'/decision-log.md'])

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('case',choices=['four_abt','weekly','pyramiding','separated','pic','mii','turtle']);args=parser.parse_args();globals()[args.case]()
