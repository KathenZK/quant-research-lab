"""Read-only four-question comparison and strictly post-exit price diagnostics.

This module never imports a replay engine. Saved result files are hash-verified.
The post-exit price study is descriptive and does not feed strategy decisions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
import pandas as pd

from common import BASE, sha, write_json

OLD=BASE/'artifacts/results_20260909'
NEW=BASE/'artifacts/results_four_tests_20260910'
OUT=BASE/'artifacts/analysis_four_tests_20260910'
CONTRACT=BASE/'specs/contract-four-tests-20260910.md'
OLD_SHA='880d7201b4c23695265d80d2704e0ec03245dfdb8a274b50873f82fbfb50a13d'
NEW_CASES=['A_LONG','A_SHORT','A_SHORT_NO_TP','B_MA30_READY','B_MA30','C_RISK005','C_SMALL','D_RESET','D_NO_TP']
CASES=['V3']+NEW_CASES+['V1']
LABELS={'V3':'V3 原版多空','V1':'V1 固定1.5ATR', 'A_LONG':'只做多','A_SHORT':'只做空，保留提前止盈',
'A_SHORT_NO_TP':'只做空，关闭提前止盈','B_MA30_READY':'仅增加MA30预热对照','B_MA30':'MA30方向过滤',
'C_RISK005':'每笔计划风险0.5%','C_SMALL':'统一小仓位对照','D_RESET':'创新高低后停止继续收紧','D_NO_TP':'关闭空单提前止盈'}
QUESTIONS={
'A':{'title':'1 · 分开看多单和空单','cases':['V3','A_LONG','A_SHORT','A_SHORT_NO_TP'],
'note':'只做多与只做空分别使用独立账户。两者收益不能直接相加；持仓占用与之后的开仓机会也会改变。'},
'B':{'title':'2 · 增加MA30方向过滤','cases':['V3','B_MA30_READY','B_MA30'],
'note':'先用B_MA30_READY控制额外预热，再比较MA30过滤本身。少做交易或暴露变少不等于选入的信号更有优势。'},
'C':{'title':'3 · 固定计划风险与简单降仓位','cases':['V3','C_RISK005','C_SMALL'],
'note':'同时比较按初始止损距离分配仓位与统一小仓位。小仓位对照不是严格等风险匹配，风险目标也不保证跳空后的实际损失。'},
'D':{'title':'4 · 修改收紧与空单提前止盈','cases':['V3','D_RESET','D_NO_TP','V1'],
'note':'真正的退出规则效果以完整账户对照为准。退出之后的涨跌只解释当时离场后的价格变化，不能直接当成已验证可赚利润。'}}
PAIR_LIST=[('A_LONG','V3'),('A_SHORT','V3'),('A_SHORT_NO_TP','A_SHORT'),('B_MA30','B_MA30_READY'),('B_MA30_READY','V3'),('C_RISK005','V3'),('C_SMALL','V3'),('C_RISK005','C_SMALL'),('D_RESET','V3'),('D_NO_TP','V3'),('V3','V1')]
COHORTS=['main_full','partial','short']


def clean(v):
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [clean(x) for x in v]
    if isinstance(v,np.bool_):return bool(v)
    if isinstance(v,np.integer):return int(v)
    if isinstance(v,(float,np.floating)):return float(v) if np.isfinite(v) else None
    return v


class Source:
    def __init__(self,directory,pinned=None):
        self.directory=directory;self.manifest_sha=sha(directory/'artifact_checksums.json')
        if pinned:assert self.manifest_sha==pinned, f'Manifest changed: {directory}'
        self.hashes=json.loads((directory/'artifact_checksums.json').read_text());self.checked={}
    def path(self,name):
        assert name in self.hashes, f'Unregistered saved source: {name}'
        p=self.directory/name
        if name not in self.checked:
            actual=sha(p);assert actual==self.hashes[name],f'Saved source changed: {p}'
            self.checked[name]=actual
        return p
    def csv(self,name):
        try:return pd.read_csv(self.path(name))
        except pd.errors.EmptyDataError:return pd.DataFrame()
    def obj(self,name):return json.loads(self.path(name).read_text())
    def manifest(self):return {'directory':str(self.directory.relative_to(BASE)),'artifact_checksums_sha256':self.manifest_sha,'consumed_files':self.checked}


def save_checksums(directory):
    write_json(directory/'artifact_checksums.json',{str(p.relative_to(directory)):sha(p) for p in sorted(directory.rglob('*')) if p.is_file() and p!=directory/'artifact_checksums.json'})


def summarize_exit_events(events):
    group_rows=[];coin_rows=[]
    groups={'stop_all':events.exit_kind.eq('stop'),'stop_armed_then_refreshed':events.exit_kind.eq('stop')&events.armed_then_new_extreme,
            'short_rsi_tp':events.exit_kind.eq('short_rsi_tp')}
    fields=['directional_end_return_pct','favorable_excursion_pct','adverse_excursion_pct']
    for cohort in COHORTS:
        for group,mask in groups.items():
            for side in ['all','long','short']:
                side_mask=True if side=='all' else events.side.eq(1 if side=='long' else -1)
                for horizon in [5,10,20]:
                    p=events[mask&events.cohort.eq(cohort)&side_mask&events.horizon_days.eq(horizon)]
                    valid=p[~p.censored]
                    r={'cohort':cohort,'exit_group':group,'side':side,'horizon_days':horizon,'events_total':len(p),
                       'events_complete':len(valid),'events_censored':int(p.censored.sum()),'coins_total':p.symbol.nunique(),
                       'coins_with_complete_events':valid.symbol.nunique(),
                       'continuation_positive_events':int((valid.directional_end_return_pct>0).sum()),
                       'continuation_negative_events':int((valid.directional_end_return_pct<0).sum()),
                       'continuation_flat_events':int((valid.directional_end_return_pct==0).sum()),
                       'continuation_positive_pct':float((valid.directional_end_return_pct>0).mean()*100) if len(valid) else None}
                    for field in fields:
                        r['event_median_'+field]=float(valid[field].median()) if len(valid) else None
                        coin_medians=valid.groupby('symbol')[field].median()
                        r['coin_median_'+field]=float(coin_medians.median()) if len(coin_medians) else None
                    r['event_q25_directional_end_return_pct']=float(valid.directional_end_return_pct.quantile(.25)) if len(valid) else None
                    r['event_q75_directional_end_return_pct']=float(valid.directional_end_return_pct.quantile(.75)) if len(valid) else None
                    group_rows.append(r)
                    for symbol,q in p.groupby('symbol'):
                        good=q[~q.censored]
                        cr={'cohort':cohort,'exit_group':group,'side':side,'horizon_days':horizon,'symbol':symbol,
                            'events_total':len(q),'events_complete':len(good),'events_censored':int(q.censored.sum()),
                            'continuation_positive_events':int((good.directional_end_return_pct>0).sum())}
                        for field in fields:cr['median_'+field]=float(good[field].median()) if len(good) else None
                        coin_rows.append(cr)
    return group_rows,coin_rows


def diagnose_exits():
    assert CONTRACT.exists(),'Freeze four-test specification before computing diagnostics'
    target=OUT/'exit_diagnostics'
    assert not target.exists(),'Preserve existing post-exit study'
    source=Source(OLD,OLD_SHA);scope=source.csv('scope.csv');rows=[];totals={'all_v3_trades':0,'terminal_exits_excluded':0,'eligible_exit_events':0,'armed_then_new_extreme_exits':0}
    for market in scope[scope.status.eq('REPLAY_COMPLETED')].itertuples():
        slug=market.slug;tr=source.csv(f'runs/{slug}/H4_D0/full/trades.csv');st=source.csv(f'runs/{slug}/H4_D0/full/stops.csv')
        hourly=pd.read_parquet(source.path(f'market/{slug}/hourly.parquet'))
        hourly['timestamp']=pd.to_datetime(hourly.timestamp,utc=True);hourly=hourly.sort_values('timestamp').reset_index(drop=True)
        assert hourly.timestamp.is_unique and hourly.eligible.all() and hourly.is_closed.all()
        end=pd.Timestamp(market.end);start_segment=pd.Timestamp(market.input_start)
        assert hourly.timestamp.iloc[0]==start_segment and hourly.timestamp.iloc[-1]+pd.Timedelta(hours=1)==end
        assert hourly.timestamp.diff().dropna().eq(pd.Timedelta(hours=1)).all()
        if len(st):
            st['timestamp']=pd.to_datetime(st.timestamp,utc=True)
            by_st={int(k):g for k,g in st.groupby('trade_id')}
        else:by_st={}
        for t in tr.to_dict('records'):
            totals['all_v3_trades']+=1
            if t['exit_reason']=='sample_end':totals['terminal_exits_excluded']+=1;continue
            assert t['exit_reason'] in ['stop_gap','stop_intrahour','accel1_rsi30'],t['exit_reason']
            totals['eligible_exit_events']+=1
            exit_time=pd.Timestamp(t['exit_time'])
            after=pd.Timestamp(t['exit_interval_end']) if pd.notna(t.get('exit_interval_end')) else exit_time
            assert after>=exit_time and after==after.floor('h')
            ref=float(t['exit_reference']);assert ref>0
            updates=by_st[int(t['trade_id'])];assert (updates.timestamp<=exit_time).all()
            resumed=bool((updates.old_armed&updates.new_extreme&updates.full_holding_day).any())
            if resumed:totals['armed_then_new_extreme_exits']+=1
            kind='stop' if t['exit_reason'].startswith('stop') else 'short_rsi_tp'
            if kind=='short_rsi_tp':assert t['side']==-1
            for horizon in [5,10,20]:
                finish=after+pd.Timedelta(days=horizon)
                post=hourly[(hourly.timestamp>=after)&(hourly.timestamp<finish)]
                complete=bool(after>=start_segment and finish<=end and len(post)==horizon*24 and
                              len(post)>0 and post.timestamp.iloc[0]==after and post.timestamp.iloc[-1]+pd.Timedelta(hours=1)==finish)
                r={k:t[k] for k in ['trade_id','side','exit_reason','exit_time','exit_interval_end','exit_reference','entry_time','entry_price','net_pnl','arm_day','armed']}
                r.update(symbol=market.symbol,slug=slug,cohort=market.cohort,exit_kind=kind,
                         armed_then_new_extreme=resumed,horizon_days=horizon,followup_start=after.isoformat(),followup_end_exclusive=finish.isoformat(),
                         selected_data_end_exclusive=end.isoformat(),available_hours=len(post),required_hours=horizon*24,censored=not complete,
                         censor_reason='' if complete else 'FROZEN_SEGMENT_END_BEFORE_FULL_FOLLOWUP' if finish>end else 'INCOMPLETE_FUTURE_HOURLY_WINDOW',
                         directional_end_return_pct=None,favorable_excursion_pct=None,adverse_excursion_pct=None,followup_end_close=None)
                if complete:
                    side=int(t['side']);close=float(post.close.iloc[-1]);fav=float(post.high.max()) if side==1 else float(post.low.min());adv=float(post.low.min()) if side==1 else float(post.high.max())
                    r.update(followup_end_close=close,directional_end_return_pct=side*(close/ref-1)*100,
                             favorable_excursion_pct=max(0.,side*(fav/ref-1)*100),adverse_excursion_pct=max(0.,-side*(adv/ref-1)*100))
                rows.append(r)
    events=pd.DataFrame(rows);assert len(events)==3*totals['eligible_exit_events']
    assert not events.duplicated(['symbol','trade_id','horizon_days']).any()
    groups,coins=summarize_exit_events(events)
    target.mkdir(parents=True);events.to_csv(target/'exit_events.csv',index=False);pd.DataFrame(groups).to_csv(target/'exit_summary.csv',index=False);pd.DataFrame(coins).to_csv(target/'exit_coin_summary.csv',index=False)
    write_json(target/'summary.json',clean(dict(totals=totals,groups=groups,primary_horizon_days=10,sensitivity_horizons_days=[5,20],
       counts_note='Exit groups overlap: armed-then-refreshed stops are a subset of all stops. All-side rows overlap long/short rows. Censored events remain in each denominator.',
       price_note='Directional post-exit price movement only; no hypothetical profit or claim that holding would have earned this return.',
       future_window_note='Start at exit_interval_end, falling back to exit_time only if absent. Use hourly candles whose open timestamps are >=start and <start+N days. Require all N*24 hours inside the selected frozen segment.',
       excursions_note='Both excursions include zero. Favorable uses max high for longs/min low for shorts; adverse uses min low for longs/max high for shorts. Reference is saved exit_reference, before slippage.',
       aggregation_note='Event medians and equal-coin medians are both supplied. No dollar-PnL weighting. Main/partial/short and long/short remain separate.')))
    write_json(target/'source_manifest.json',dict(contract_sha256=sha(CONTRACT),analysis_script_sha256=sha(Path(__file__)),source=source.manifest(),strategy_simulation_performed=False))
    shutil.copy2(Path(__file__),target/'analysis_script_at_exit_diagnostic.py.txt')
    save_checksums(target)
    print(json.dumps(totals,ensure_ascii=False))


def quality(r):
    r['historically_profitable']=bool(r['return_pct']>0)
    r['risk_count_pass']=bool(r['trade_days']>=180 and r['trades']>=10 and r['return_pct']>0 and r['max_drawdown_pct']>=-30 and not r['bankrupt'])
    r['stable_candidate']=bool(r['risk_count_pass'] and r['early60_return_pct']>0 and r['late40_return_pct']>0 and r['early60_trades']>=3 and r['late40_trades']>=3 and r['slippage_10bp_return_pct']>0 and r['carry_5bp_day_return_pct']>0)


def trade_risk_frame(tr,fee,slip):
    """Reconstruct planned stop risk independently from saved fills and stop prices."""
    q=tr.copy()
    if q.empty:return q
    stop_fill=q.initial_stop*(1-q.side*slip)
    unit=q.side*(q.entry_price-stop_fill)+fee*(q.entry_price+stop_fill)
    planned=q.qty*unit
    if 'initial_planned_risk' in q:
        assert np.allclose(q.initial_planned_risk,planned,atol=1e-7,rtol=1e-12)
    q['initial_planned_risk_rebuilt']=planned
    q['initial_planned_risk_pct_rebuilt']=planned/q.entry_equity*100
    q['initial_notional_equity_pct']=q.qty*q.entry_price/q.entry_equity*100
    q['actual_trade_return_pct']=q.net_pnl/q.entry_equity*100
    q['net_pnl_in_initial_r']=q.net_pnl/planned.where(planned>0)
    q['initial_stop_nonpositive']=q.initial_stop<=0
    q['actual_loss_exceeds_half_percent']=q.actual_trade_return_pct < -.5-1e-9
    q['loss_exceeds_half_percent_before_carry']=(q.net_pnl+q.carry_paid)/q.entry_equity*100 < -.5-1e-9
    q['carry_pushes_over_half_percent']=q.actual_loss_exceeds_half_percent & ~q.loss_exceeds_half_percent_before_carry
    q['gap_exit_on_excess']=q.actual_loss_exceeds_half_percent & q.exit_reason.eq('stop_gap')
    q['execution_worse_than_initial_stop']=q.side*(q.exit_price-stop_fill)<-1e-10
    return q


def risk_study(old,new):
    rows=[]
    for case in ['V3','C_RISK005','C_SMALL']:
        source=old if case=='V3' else new;cid='H4_D0' if case=='V3' else case
        full=source.csv('summary.csv').query("case_id==@cid and window=='full'")
        stresses=source.csv('stress.csv').query('case_id==@cid')
        for scenario,summary in [('full',full),('slippage_10bp',stresses[stresses.scenario.eq('slippage_10bp')]),('carry_5bp_day',stresses[stresses.scenario.eq('carry_5bp_day')])]:
            for r in summary.itertuples():
                relative=f'runs/{r.slug}/{cid}/full/trades.csv' if scenario=='full' else f'sensitivity/{r.slug}/{cid}/{scenario}/trades.csv'
                tr=trade_risk_frame(source.csv(relative),float(r.fee),float(r.slip))
                if not len(tr):continue
                keep=['trade_id','side','entry_time','exit_time','exit_reason','entry_equity','entry_price','exit_price','initial_stop','qty','net_pnl','carry_paid',
                      'initial_planned_risk_rebuilt','initial_planned_risk_pct_rebuilt','initial_notional_equity_pct','actual_trade_return_pct','net_pnl_in_initial_r',
                      'initial_stop_nonpositive','actual_loss_exceeds_half_percent','loss_exceeds_half_percent_before_carry','carry_pushes_over_half_percent',
                      'gap_exit_on_excess','execution_worse_than_initial_stop']
                for record in tr[keep].to_dict('records'):
                    rows.append(dict(record,symbol=r.symbol,slug=r.slug,cohort=r.cohort,case_id=case,scenario=scenario))
    events=pd.DataFrame(rows);groups=[]
    for (cohort,case,scenario),part in events.groupby(['cohort','case_id','scenario']):
        for reason in ['ALL_EXITS']+sorted(part.exit_reason.unique().tolist()):
            p=part if reason=='ALL_EXITS' else part[part.exit_reason.eq(reason)]
            breach=p.actual_loss_exceeds_half_percent
            groups.append(dict(cohort=cohort,case_id=case,scenario=scenario,exit_reason=reason,trades=len(p),coins=p.symbol.nunique(),
                planned_risk_median_pct=float(p.initial_planned_risk_pct_rebuilt.median()),
                notional_equity_median_pct=float(p.initial_notional_equity_pct.median()),
                planned_risk_coin_median_pct=float(p.groupby('symbol').initial_planned_risk_pct_rebuilt.median().median()),
                notional_equity_coin_median_pct=float(p.groupby('symbol').initial_notional_equity_pct.median().median()),
                net_pnl_initial_r_median=float(p.net_pnl_in_initial_r.median()),
                net_pnl_initial_r_coin_median=float(p.groupby('symbol').net_pnl_in_initial_r.median().median()),
                initial_stop_nonpositive_trades=int(p.initial_stop_nonpositive.sum()),
                initial_stop_nonpositive_coins=int(p.loc[p.initial_stop_nonpositive,'symbol'].nunique()),
                loss_exceeds_half_percent_trades=int(breach.sum()),loss_exceeds_half_percent_pct=float(breach.mean()*100),
                loss_exceeds_half_percent_coins=int(p.loc[breach,'symbol'].nunique()),
                max_actual_loss_pct=float(max(0.,-p.actual_trade_return_pct.min())),
                breach_before_carry_trades=int(p.loss_exceeds_half_percent_before_carry.sum()),
                carry_pushes_over_half_percent_trades=int(p.carry_pushes_over_half_percent.sum()),
                gap_exit_on_excess_trades=int(p.gap_exit_on_excess.sum()),
                execution_worse_than_initial_stop_on_excess_trades=int((breach&p.execution_worse_than_initial_stop).sum())))
    return events,groups


def build_ranking(old,new):
    scope=old.csv('scope.csv');other=new.csv('scope.csv');assert len(scope)==len(other)==652
    for key in ['symbol','cohort','trade_days','trade_start','end','boundary_end_due_to_data']:
        pd.testing.assert_series_equal(scope.sort_values('symbol')[key].reset_index(drop=True),other.sort_values('symbol')[key].reset_index(drop=True),check_names=False)
    byscope=scope.set_index('symbol');old_summary=old.csv('summary.csv');old_stress=old.csv('stress.csv');new_summary=new.csv('summary.csv');new_stress=new.csv('stress.csv')
    assert set(new_summary.case_id)==set(NEW_CASES) and set(new_stress.case_id)==set(NEW_CASES)
    assert len(new_summary)==1689*9 and len(new_stress)==1222*9
    hold=old.csv('buy_hold.csv').query("window=='full'").set_index('symbol');rows=[]
    for case in CASES:
        source,cid,g,s=(old,'H4_D0' if case=='V3' else 'F0',old_summary,old_stress) if case in ['V1','V3'] else (new,case,new_summary,new_stress)
        allg=g[g.case_id.eq(cid)].set_index(['symbol','window']);alls=s[s.case_id.eq(cid)].set_index(['symbol','scenario']);full=allg.xs('full',level='window')
        assert len(full)==611 and allg.index.is_unique and alls.index.is_unique
        for symbol,r in full.iterrows():
            item=dict(r);item.update(symbol=symbol,case_id=case,source_case_id=cid,label=LABELS[case],window='full',
               source_origin='复用已有回测' if case in ['V1','V3'] else '本次新回测',
               boundary_end_due_to_data=bool(byscope.loc[symbol].boundary_end_due_to_data),
               buy_hold_return_pct=hold.loc[symbol].return_pct,buy_hold_drawdown_pct=hold.loc[symbol].max_drawdown_pct,
               zero_trades=bool(r.trades==0))
            for period in ['early60','late40']:
                part=allg.loc[(symbol,period)] if (symbol,period) in allg.index else None
                for key in ['return_pct','max_drawdown_pct','trades','exposure_pct']:
                    item[period+'_'+key]=part[key] if part is not None else np.nan
                for key in ['start','end_exclusive']:item[period+'_'+key]=part[key] if part is not None else None
            for scenario in ['slippage_10bp','carry_5bp_day']:
                part=alls.loc[(symbol,scenario)]
                for key in ['return_pct','max_drawdown_pct','trades','bankrupt','exposure_pct']:item[scenario+'_'+key]=part[key]
            relative=f'runs/{r.slug}/{cid}/full/trades.csv';tr=trade_risk_frame(source.csv(relative),float(r.fee),float(r.slip));assert len(tr)==int(r.trades)
            pnl=tr.net_pnl if len(tr) else pd.Series(dtype=float)
            assert np.isclose(10000+pnl.sum(),r.ending_equity,atol=1e-6,rtol=0)
            item.update(winning_trades=int((pnl>0).sum()),losing_trades=int((pnl<0).sum()),flat_trades=int((pnl==0).sum()),
               trades_csv_path='../'+source.directory.name+'/'+relative,
               path_url=f'../html_20260909_v2/coins/{r.slug}.html#{cid}' if case in ['V1','V3'] else '../'+source.directory.name+'/'+relative)
            if len(tr):
                for prefix,mask in [('long',tr.side.eq(1)),('short',tr.side.eq(-1))]:
                    item[prefix+'_trade_return_median_pct']=float((tr.loc[mask,'return_on_entry_equity']*100).median()) if mask.any() else np.nan
                item['initial_stop_distance_median_pct']=float(tr.initial_stop_risk_pct.median())
                item['initial_notional_equity_median_pct']=float(tr.initial_notional_equity_pct.median())
                item['initial_planned_risk_median_pct']=float(tr.initial_planned_risk_pct_rebuilt.median())
                item['net_pnl_initial_r_median']=float(tr.net_pnl_in_initial_r.median())
                item['loss_exceeds_half_percent_trades']=int(tr.actual_loss_exceeds_half_percent.sum())
                item['initial_stop_nonpositive_trades']=int(tr.initial_stop_nonpositive.sum())
            else:
                for field in ['long_trade_return_median_pct','short_trade_return_median_pct','initial_stop_distance_median_pct','initial_notional_equity_median_pct','initial_planned_risk_median_pct','net_pnl_initial_r_median']:item[field]=np.nan
                item['loss_exceeds_half_percent_trades']=0;item['initial_stop_nonpositive_trades']=0
            quality(item);rows.append(item)
    ranking=pd.DataFrame(rows).sort_values(['cohort','case_id','return_pct'],ascending=[True,True,False]);assert len(ranking)==611*len(CASES)
    return scope,ranking


def aggregate(ranking):
    cohorts=[];pairs=[];coin_pairs=[]
    for cohort in COHORTS:
        for case in CASES:
            p=ranking[ranking.cohort.eq(cohort)&ranking.case_id.eq(case)]
            r=dict(cohort=cohort,case_id=case,label=LABELS[case],coins=len(p),positive_coins=int((p.return_pct>0).sum()),
              negative_coins=int((p.return_pct<0).sum()),flat_coins=int((p.return_pct==0).sum()),zero_trade_coins=int(p.zero_trades.sum()),
              positive_pct=float((p.return_pct>0).mean()*100),median_return_pct=float(p.return_pct.median()),
              median_max_drawdown_pct=float(p.max_drawdown_pct.median()),worst_max_drawdown_pct=float(p.max_drawdown_pct.min()),
              median_exposure_pct=float(p.exposure_pct.median()),all_trades=int(p.trades.sum()),median_trades=float(p.trades.median()),
              winning_trades=int(p.winning_trades.sum()),losing_trades=int(p.losing_trades.sum()),flat_trades=int(p.flat_trades.sum()),
              long_trades=int(p.long_trades.sum()),short_trades=int(p.short_trades.sum()),
              median_long_trade_return_pct=float(p.long_trade_return_median_pct.median()),median_short_trade_return_pct=float(p.short_trade_return_median_pct.median()),
              risk_count_pass_coins=int(p.risk_count_pass.sum()),stable_candidate_coins=int(p.stable_candidate.sum()),bankrupt_coins=int(p.bankrupt.sum()),
              median_initial_stop_distance_pct=float(p.initial_stop_distance_median_pct.median()),median_initial_notional_equity_pct=float(p.initial_notional_equity_median_pct.median()),
              median_slippage_10bp_return_pct=float(p.slippage_10bp_return_pct.median()),median_carry_5bp_day_return_pct=float(p.carry_5bp_day_return_pct.median()),
              median_early60_return_pct=float(p.early60_return_pct.median()),median_late40_return_pct=float(p.late40_return_pct.median()),
              both_subperiods_positive_coins=int(((p.early60_return_pct>0)&(p.late40_return_pct>0)).sum()))
            for column in p.columns:
                if column in ['flat_ready_crosses','flat_not_ready_crosses','entry_attempts','entry_fills','slope_rejected','direction_rejected','ma30_not_ready_rejected','ma30_direction_rejected','invalid_stop_rejected','nonpositive_equity_rejected','invalid_unit_risk_rejected']:
                    r['all_'+column]=float(p[column].sum()) if p[column].notna().any() else None
            r['median_initial_planned_risk_pct']=float(p.initial_planned_risk_median_pct.median())
            r['median_net_pnl_initial_r']=float(p.net_pnl_initial_r_median.median())
            r['loss_exceeds_half_percent_trades']=int(p.loss_exceeds_half_percent_trades.sum())
            r['initial_stop_nonpositive_trades']=int(p.initial_stop_nonpositive_trades.sum())
            cohorts.append(r)
        p=ranking[ranking.cohort.eq(cohort)]
        for newer,older in PAIR_LIST:
            a=p[p.case_id.eq(newer)].set_index('symbol').sort_index();b=p[p.case_id.eq(older)].set_index('symbol').sort_index();assert a.index.equals(b.index)
            dr=a.return_pct-b.return_pct;dd=a.max_drawdown_pct-b.max_drawdown_pct;eps=1e-9
            pairs.append(dict(cohort=cohort,comparison=newer+'-'+older,newer_case=newer,older_case=older,coins=len(a),
              return_up_coins=int((dr>eps).sum()),return_down_coins=int((dr< -eps).sum()),return_same_coins=int((dr.abs()<=eps).sum()),
              drawdown_improved_coins=int((dd>eps).sum()),drawdown_worse_coins=int((dd< -eps).sum()),drawdown_same_coins=int((dd.abs()<=eps).sum()),
              return_up_drawdown_not_worse_coins=int(((dr>eps)&(dd>= -eps)).sum()),both_strictly_improved_coins=int(((dr>eps)&(dd>eps)).sum()),
              median_paired_return_change_pp=float(dr.median()),median_paired_drawdown_reduction_pp=float(dd.median()),
              median_paired_exposure_change_pp=float((a.exposure_pct-b.exposure_pct).median()),median_paired_trade_count_change=float((a.trades-b.trades).median()),
              older_nonpositive_newer_positive_coins=int(((b.return_pct<=0)&(a.return_pct>0)).sum()),older_positive_newer_nonpositive_coins=int(((b.return_pct>0)&(a.return_pct<=0)).sum()),
              both_positive_coins=int(((b.return_pct>0)&(a.return_pct>0)).sum()),both_nonpositive_coins=int(((b.return_pct<=0)&(a.return_pct<=0)).sum())))
            for symbol in a.index:coin_pairs.append(dict(cohort=cohort,symbol=symbol,comparison=newer+'-'+older,newer_case=newer,older_case=older,
               return_change_pp=float(dr.loc[symbol]),drawdown_reduction_pp=float(dd.loc[symbol]),exposure_change_pp=float(a.loc[symbol].exposure_pct-b.loc[symbol].exposure_pct),
               trade_count_change=int(a.loc[symbol].trades-b.loc[symbol].trades)))
    return cohorts,pairs,coin_pairs


def main(new_manifest_sha):
    assert CONTRACT.exists(),'Freeze specification first';assert not (OUT/'ranking.csv').exists(),'Preserve prior completed analysis'
    old,new=Source(OLD,OLD_SHA),Source(NEW,new_manifest_sha)
    for source in [old,new]:
        c=source.obj('completion.json');assert c['complete'] and c['coins_completed']==611 and c['coins_failed']==0
        source.obj('run_manifest.json')
    scope,ranking=build_ranking(old,new);cohorts,pairs,coin_pairs=aggregate(ranking)
    risk_events,risk_summary=risk_study(old,new)
    diag=OUT/'exit_diagnostics'
    if not diag.exists():diagnose_exits()
    diag_hashes=json.loads((diag/'artifact_checksums.json').read_text())
    for relative,digest in diag_hashes.items():assert sha(diag/relative)==digest
    exit_summary=json.loads((diag/'summary.json').read_text())
    # Directly compare retained V1/V3 full rows with the previous three-version analysis.
    prior=BASE/'artifacts/comparison_v123_20260910';prior_hashes=json.loads((prior/'artifact_checksums.json').read_text());assert sha(prior/'ranking.csv')==prior_hashes['ranking.csv']
    old_rank=pd.read_csv(prior/'ranking.csv');fields=['return_pct','max_drawdown_pct','trades','exposure_pct','winning_trades','losing_trades','flat_trades','risk_count_pass','stable_candidate','early60_return_pct','late40_return_pct','slippage_10bp_return_pct','carry_5bp_day_return_pct']
    for case in ['V1','V3']:
        p=old_rank[old_rank.version.eq(case)].sort_values('symbol');q=ranking[ranking.case_id.eq(case)].sort_values('symbol')
        pd.testing.assert_frame_equal(p[fields].reset_index(drop=True),q[fields].reset_index(drop=True),check_dtype=False,rtol=1e-12,atol=1e-12)
    by=ranking.set_index(['symbol','case_id']);html_rows=[];wide=[]
    for r in scope.to_dict('records'):
        excluded=r['status']!='REPLAY_COMPLETED';reason='未找到足够连续且满足预热的有效日K和小时K窗口' if excluded else ''
        item=dict(symbol=r['symbol'],slug=r['slug'],cohort=r['cohort'],days=int(r['trade_days']),excluded=excluded,reason=reason,
             start=None if excluded else str(r['trade_start'])[:10],end=None if excluded else (pd.Timestamp(r['end'])-pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
             dataEndedEarly=False if excluded else bool(r['boundary_end_due_to_data']),cases={})
        w=dict(r,exclusion_reason=reason)
        if not excluded:
            for case in CASES:
                a=by.loc[(r['symbol'],case)].to_dict();item['cases'][case]=a
                for field in ['return_pct','max_drawdown_pct','trades','exposure_pct','zero_trades','risk_count_pass','stable_candidate','bankrupt']:w[case+'_'+field]=a[field]
                assert (OUT/a['path_url'].split('#')[0]).resolve().exists()
        html_rows.append(item);wide.append(w)
    summary=clean(dict(family_id='BIN-1D-MA7-CAR-GEN',round='four-tests-20260910',observed_contracts=874,candidate_coins=652,completed_coins=611,
      excluded_price_coins=41,execution_failed_coins=0,cohort_counts=scope.cohort.value_counts().to_dict(),new_cases=NEW_CASES,reused_cases=['V3','V1'],
      cohorts=cohorts,paired_comparisons=pairs,questions=QUESTIONS,labels=LABELS,full_account_count=len(ranking),full_trade_ledger_count=len(ranking),
      all_full_period_trades=int(ranking.trades.sum()),funding_window_verified=False,independent_single_coin_accounts=True,
      previous_V1_V3_comparison_verified=True,quality_definition='>=180 days, >=10 trades, positive return, DD<=30%, not bankrupt; stable additionally both independent subperiods positive and >=3 trades each, both stresses positive.',
      note='All comparisons use independent per-coin accounts, separate history cohorts, common costs and declared uniform parameters. No per-coin best-arm selection is a strategy.'))
    OUT.mkdir(parents=True,exist_ok=True);ranking.to_csv(OUT/'ranking.csv',index=False);pd.DataFrame(wide).to_csv(OUT/'comparison.csv',index=False)
    pd.DataFrame(cohorts).to_csv(OUT/'cohort_summary.csv',index=False);pd.DataFrame(pairs).to_csv(OUT/'paired_comparisons.csv',index=False);pd.DataFrame(coin_pairs).to_csv(OUT/'coin_paired_comparisons.csv',index=False)
    ranking[ranking.risk_count_pass].to_csv(OUT/'candidates.csv',index=False);write_json(OUT/'summary.json',summary)
    risk_events.to_csv(OUT/'risk_trade_events.csv',index=False);pd.DataFrame(risk_summary).to_csv(OUT/'risk_summary.csv',index=False)
    write_json(OUT/'risk_summary.json',clean(dict(groups=risk_summary,note='Actual return is net_pnl/entry_equity. Planned risk includes modeled entry and stop-exit costs; nominal position is qty*entry_fill/entry_equity. Half-percent excess applies to actual loss, not a guarantee. Cause flags may overlap. Nonpositive initial stops remain present and flagged.')))
    template_path=BASE/'scripts/four_tests_template.html';template=template_path.read_text();assert template.count('__FROZEN_DATA__')==1
    assert not re.search(r'<(?:script|link|iframe|img)\b[^>]+\b(?:src|href)\s*=',template,re.I)
    script=re.findall(r'<script>(.*?)</script>',template,re.S);assert len(script)==1 and not re.search(r'\b(?:fetch|XMLHttpRequest|WebSocket|EventSource)\b',script[0]);subprocess.run(['node','--check','-'],input=script[0],text=True,check=True,capture_output=True)
    risk_global=[]
    for scenario in ['full','slippage_10bp','carry_5bp_day']:
        p=risk_events[risk_events.case_id.eq('C_RISK005')&risk_events.scenario.eq(scenario)];worst=p.loc[p.actual_trade_return_pct.idxmin()]
        risk_global.append(dict(scenario=scenario,trades=len(p),loss_exceeds_half_percent_trades=int(p.actual_loss_exceeds_half_percent.sum()),initial_stop_nonpositive_trades=int(p.initial_stop_nonpositive.sum()),worst_symbol=worst.symbol,worst_trade_id=int(worst.trade_id),worst_loss_pct=float(-worst.actual_trade_return_pct),worst_exit_reason=worst.exit_reason,worst_carry_paid=float(worst.carry_paid)))
    data=clean(dict(summary=summary,rows=html_rows,exitSummary=exit_summary,riskSummary=risk_summary,riskGlobal=risk_global));encoded=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/')
    (OUT/'index.html').write_text(template.replace('__FROZEN_DATA__',encoded))
    write_json(OUT/'source_manifest.json',dict(contract_sha256=sha(CONTRACT),analysis_script_sha256=sha(Path(__file__)),template_sha256=sha(template_path),
      old_source=old.manifest(),new_source=new.manifest(),exit_diagnostics_manifest_sha256=sha(diag/'artifact_checksums.json'),
      prior_comparison_ranking_sha256=sha(prior/'ranking.csv'),strategy_simulation_performed=False))
    save_checksums(OUT)
    print(pd.DataFrame(cohorts).query("cohort=='main_full'")[['case_id','positive_coins','median_return_pct','median_max_drawdown_pct','all_trades','stable_candidate_coins']].to_string(index=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--diagnostics-only',action='store_true');parser.add_argument('--new-manifest-sha')
    args=parser.parse_args()
    if args.diagnostics_only:diagnose_exits()
    else:
        assert args.new_manifest_sha,'Pin completed new-result manifest before analysis'
        main(args.new_manifest_sha)
