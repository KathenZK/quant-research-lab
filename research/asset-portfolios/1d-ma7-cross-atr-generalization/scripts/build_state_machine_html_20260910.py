"""Verified saved-account analysis and offline interactive pages; never replay."""
from __future__ import annotations
import argparse
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor,as_completed
import hashlib
import json
import os
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import build_html as old
old.ms=lru_cache(maxsize=200000)(old.ms)
from diagnose_exit_states_20260910 import cash_stats, clean, write_json

BASE=Path(__file__).resolve().parents[1]
ROUND=BASE/'artifacts/state_machine_20260910'
CASES=['V3','S1_DEFENSE','S2_TREND','S3_EXTENSION']
LABELS=dict(zip(CASES,['V3 新成本基准','S1 失败与回撤防守','S2 加健康日暂停','S3 加延伸观察与衰竭保护']))
PAIRINGS=[('S1_DEFENSE','V3'),('S2_TREND','S1_DEFENSE'),('S3_EXTENSION','S2_TREND'),('S2_TREND','V3'),('S3_EXTENSION','V3')]
COHORTS=['main_full','partial','short']
ENGINE_SHA='31549725a5384303415763c05cb4cb91446e0682f88b519c95f815ef239778b2'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def finite(v):return old.finite(v)
def records(df):return clean(df.replace({np.nan:None}).to_dict('records'))
def emit(path,df):df.to_csv(path,index=False)
def freeze(p):write_json(p/'artifact_checksums.json',{str(f.relative_to(p)):sha(f) for f in sorted(p.rglob('*')) if f.is_file() and f.name!='artifact_checksums.json'})


class Saved:
    def __init__(self,directory,expected=None,engine=True):
        self.directory=Path(directory).resolve();manifest=self.directory/'artifact_checksums.json'
        self.manifest_sha=sha(manifest);assert expected is None or self.manifest_sha==expected
        self.hashes=json.loads(manifest.read_text());self.checked={}
        if engine:
            self.run=self.obj('run_manifest.json');assert self.run['engine_pin']['engine_sha256']==ENGINE_SHA
            assert self.run['engine_pin']['fee']==.001 and self.run['engine_pin']['slip']==.0004
            c=json.loads((self.directory/'completion.json').read_text());assert c['complete'] and c['manifest_sha256']==self.manifest_sha
            assert self.obj('execution_failures.json')==[]
            self.checked['completion.json_external_binding']=sha(self.directory/'completion.json')
    def path(self,name):
        name=str(name);assert name in self.hashes,(self.directory,name)
        if name not in self.checked:
            value=sha(self.directory/name);assert value==self.hashes[name],name;self.checked[name]=value
        return self.directory/name
    def csv(self,name):return old.read_csv(self.path(name))
    def obj(self,name):return json.loads(self.path(name).read_text())
    def manifest(self):return {'directory':str(self.directory),'manifest_sha256':self.manifest_sha,'consumed':self.checked}


def metrics(t):
    s=cash_stats(t)
    if len(t):
        ret=t.return_on_entry_equity*100;win=t[t.net_pnl>0];loss=t[t.net_pnl<0]
        s.update(average_trade_return_pct=float(ret.mean()),median_trade_return_pct=float(ret.median()),
          average_winning_trade_return_pct=float(win.return_on_entry_equity.mean()*100) if len(win) else None,
          average_losing_trade_return_pct=float(-loss.return_on_entry_equity.mean()*100) if len(loss) else None,
          worst_trade_return_pct=float(ret.min()),top5_winners_share_pct=float(win.net_pnl.nlargest(5).sum()/win.net_pnl.sum()*100) if len(win) else None,
          terminal_trades=int(t.exit_reason.eq('sample_end').sum()))
    else:s.update({k:None for k in ['average_trade_return_pct','median_trade_return_pct','average_winning_trade_return_pct','average_losing_trade_return_pct','worst_trade_return_pct','top5_winners_share_pct']});s['terminal_trades']=0
    return s


def validate_account(summary,t):
    assert len(t)==int(summary['trades'])
    assert np.isclose(10000+(t.net_pnl.sum() if len(t) else 0),summary['ending_equity'],atol=1e-6,rtol=0)
    assert summary['fee']==.001 and summary['slip']==.0004
    if len(t):
        assert np.allclose(t.side*t.qty*(t.exit_price-t.entry_price),t.gross_pnl,atol=1e-6)
        assert np.allclose(t.gross_pnl-t.entry_fee-t.exit_fee-t.funding_paid-t.carry_paid,t.net_pnl,atol=1e-6)
        assert np.allclose(t.entry_fee,t.qty*t.entry_price*.001,atol=1e-7)
        assert np.allclose(t.exit_fee,t.qty*t.exit_price*.001,atol=1e-7)
        assert np.allclose(t.entry_price,t.entry_reference*(1+t.side*.0004),atol=1e-9)
        assert np.allclose(t.exit_price,t.exit_reference*(1-t.side*.0004),atol=1e-9)


def summarize_cohorts(ranking,keys):
    rows=[]
    for group,g in ranking.groupby(keys,dropna=False):
        group=group if isinstance(group,tuple) else (group,)
        r=dict(zip(keys,group));r.update(accounts=len(g),coins=g.symbol.nunique(),positive_accounts=int(g.return_pct.gt(0).sum()),
          zero_trade_accounts=int(g.trades.eq(0).sum()),bankrupt_accounts=int(g.bankrupt.sum()),total_trades=int(g.trades.sum()),
          terminal_trades=int(g.terminal_trades.sum()),median_return_pct=float(g.return_pct.median()),median_drawdown_pct=float(g.max_drawdown_pct.median()))
        for key in ['win_rate_pct','average_win_cash','average_loss_cash','payoff_ratio','expectancy_cash','profit_factor','average_trade_return_pct','worst_trade_return_pct','top5_winners_share_pct','exposure_pct']:
            r['median_'+key]=finite(g[key].median());r[key+'_defined_accounts']=int(g[key].notna().sum())
        if 'risk_pass' in g:r['risk_pass_accounts']=int(g.risk_pass.sum());r['stress_pass_accounts']=int(g.stress_pass.sum())
        rows.append(r)
    return pd.DataFrame(rows)


def paired(ranking,groupkeys,identity):
    rows=[];coins=[]
    for groups,g in ranking.groupby(groupkeys,dropna=False):
        groups=groups if isinstance(groups,tuple) else (groups,)
        for candidate,control in PAIRINGS:
            a=g[g.case_id.eq(candidate)].set_index(identity);b=g[g.case_id.eq(control)].set_index(identity)
            assert a.index.equals(b.index) or set(a.index)==set(b.index)
            b=b.reindex(a.index);dr=a.return_pct-b.return_pct;dd=a.max_drawdown_pct-b.max_drawdown_pct
            base=dict(zip(groupkeys,groups));base.update(candidate=candidate,control=control)
            rows.append(dict(base,accounts=len(a),return_improved=int((dr>1e-9).sum()),return_worsened=int((dr< -1e-9).sum()),return_equal=int((dr.abs()<=1e-9).sum()),
              drawdown_improved=int((dd>1e-9).sum()),drawdown_worsened=int((dd< -1e-9).sum()),drawdown_equal=int((dd.abs()<=1e-9).sum()),
              return_improved_drawdown_not_worse=int(((dr>1e-9)&(dd>=-1e-9)).sum()),median_delta_return_pp=finite(dr.median()),median_drawdown_reduction_pp=finite(dd.median())))
            for idx in a.index:
                key=idx if isinstance(idx,tuple) else (idx,)
                coins.append(dict(base,**dict(zip(identity,key)),delta_return_pp=dr.loc[idx],drawdown_reduction_pp=dd.loc[idx]))
    return pd.DataFrame(rows),pd.DataFrame(coins)


def analyze_current(src,out):
    out.mkdir(parents=True,exist_ok=False);scope=src.csv('scope.csv');s=src.csv('summary.csv');stress=src.csv('stress.csv')
    assert len(scope)==652 and len(s)==611*4 and set(s.case_id)==set(CASES)
    rows=[];side_rows=[];fixed=[]
    for item in scope[scope.cohort.ne('excluded')].to_dict('records'):
        slug=item['slug'];group=s[s.slug.eq(slug)]
        base=src.csv(f'runs/{slug}/V3/full/trades.csv');top5=set(base[base.net_pnl.gt(0)].nlargest(5,'net_pnl').trade_id) if len(base) else set()
        for case in CASES:
            q=group[group.case_id.eq(case)].iloc[0].to_dict();t=src.csv(f'runs/{slug}/{case}/full/trades.csv');validate_account(q,t)
            q.update(metrics(t));q['risk_pass']=q['trade_days']>=180 and q['trades']>=10 and q['return_pct']>0 and q['max_drawdown_pct']>=-30 and not q['bankrupt']
            st=stress[stress.slug.eq(slug)&stress.case_id.eq(case)].set_index('scenario');assert set(st.index)=={'slippage_10bp','carry_5bp_day'}
            for scenario in st.index:
                for field in ['return_pct','max_drawdown_pct','trades','bankrupt']:q[scenario+'_'+field]=st.loc[scenario,field]
            q['stress_pass']=q['risk_pass'] and all(st.return_pct>0) and not st.bankrupt.any();rows.append(q)
            for side in ['all','long','short']:
                p=t if side=='all' or not len(t) else t[t.side.eq(1 if side=='long' else -1)]
                for bucket in ['all','nonterminal','sample_end']:
                    v=p if bucket=='all' or not len(p) else p[p.exit_reason.eq('sample_end') if bucket=='sample_end' else ~p.exit_reason.eq('sample_end')]
                    side_rows.append(dict(symbol=item['symbol'],slug=slug,cohort=item['cohort'],case_id=case,side_group=side,exit_bucket=bucket,**metrics(v)))
            if case!='V3':
                f=src.csv(f'fixed_entries/{slug}/{case}/trades.csv')
                assert len(f)==len(base)
                if len(f):
                    assert set(f.source_trade_id)==set(base.trade_id)
                    b=base.set_index('trade_id').reindex(f.source_trade_id)
                    for key in ['entry_price','entry_equity','entry_fee','qty','side','initial_stop']:assert np.allclose(f[key],b[key],atol=1e-9)
                    assert np.allclose(f.baseline_net_pnl,b.net_pnl,atol=1e-7)
                    assert np.allclose(f.delta_net_pnl,f.net_pnl-f.baseline_net_pnl,atol=1e-7)
                    f=f.assign(symbol=item['symbol'],slug=slug,cohort=item['cohort'],baseline_top5_winner=f.source_trade_id.isin(top5),
                      baseline_outcome=np.where(f.baseline_net_pnl>0,'win',np.where(f.baseline_net_pnl<0,'loss','flat')))
                    fixed.append(f)
    ranking=pd.DataFrame(rows);sidetable=pd.DataFrame(side_rows);fix=pd.concat(fixed,ignore_index=True)
    coh=summarize_cohorts(ranking,['cohort','case_id']);pairs,paircoins=paired(ranking,['cohort'],['symbol'])
    frows=[]
    for (cohort,case),g in fix.groupby(['cohort','case_id']):
        for side in ['all','long','short']:
            sg=g if side=='all' else g[g.side.eq(1 if side=='long' else -1)]
            for bucket in ['all','neither_terminal','either_terminal']:
                q=sg if bucket=='all' else sg[~sg.either_terminal if bucket=='neither_terminal' else sg.either_terminal]
                for control in ['all','baseline_win','baseline_loss','baseline_top5_winner']:
                    p=q if control=='all' else q[q.baseline_top5_winner] if control=='baseline_top5_winner' else q[q.baseline_outcome.eq(control.removeprefix('baseline_'))]
                    base_positive=float(p.baseline_net_pnl.clip(lower=0).sum());new_positive=float(p.net_pnl.clip(lower=0).sum())
                    frows.append(dict(cohort=cohort,case_id=case,side_group=side,terminal_bucket=bucket,control_group=control,pairs=len(p),coins=p.symbol.nunique(),
                      improved=int(p.delta_net_pnl.gt(1e-9).sum()),worsened=int(p.delta_net_pnl.lt(-1e-9).sum()),equal=int(p.delta_net_pnl.abs().le(1e-9).sum()),
                      delta_cash_sum=float(p.delta_net_pnl.sum()),median_delta_return_pp=finite((p.delta_return*100).median()),mean_delta_return_pp=finite((p.delta_return*100).mean()),
                      baseline_cash_sum=float(p.baseline_net_pnl.sum()),candidate_cash_sum=float(p.net_pnl.sum()),baseline_positive_cash=base_positive,candidate_positive_cash=new_positive,
                      positive_cash_retention_pct=new_positive/base_positive*100 if base_positive>0 else None,
                      positive_outcomes_retained=int(p.net_pnl.gt(0).sum()),candidate_loss_count=int(p.net_pnl.lt(0).sum())))
    tables={'ranking.csv':ranking,'account_cash_by_side_exit.csv':sidetable,'cohort_summary.csv':coh,'paired_comparisons.csv':pairs,'paired_coin_results.csv':paircoins,
      'fixed_entry_pairs.csv':fix,'fixed_entry_summary.csv':pd.DataFrame(frows),'scope.csv':scope,'stress.csv':stress}
    for name,df in tables.items():emit(out/name,df)
    write_json(out/'summary.json',dict(accounts=len(ranking),coins=ranking.symbol.nunique(),trades=int(ranking.trades.sum()),baseline_trades=int(ranking[ranking.case_id.eq('V3')].trades.sum()),
      fixed_pairs=len(fix),fee=.001,slip=.0004,real_funding_verified=False,cohorts=records(coh),paired=records(pairs),
      constraints=['Per-coin accounts are not a shared-capital portfolio.','Fixed-entry episodes overlap and are not executable together.','Top-five winners are selected from each baseline coin by actual positive net cash before candidate comparison.','Risk/pass uses prior return>0, drawdown<=30%, >=10 trades, >=180 days; stress_pass additionally requires both stress returns>0; no new early/late replay was run.']))
    return tables


def chart_rules(case):
    common='MA7收盘真实穿越且方向斜率>0.05ATR/日，次日开盘；关闭反手和延后入场。初始MA7±1.5ATR，实际止损只收窄，完整持仓日收盘更新后次日生效。'
    text={'V3':'日K高/低4天不刷新，永久启动，每天减0.2倍ATR至0.5；空单保留原加速下跌且RSI≤30、预计扣费用盈利后的次日退出。',
      'S1_DEFENSE':'V3加失败穿越、>=1.25ATR回撤或3日波折防守；当日最多减0.2，并加入收盘±0.5ATR候选；保留原空单RSI退出。',
      'S2_TREND':'S1加健康趋势日暂停减倍数：3段效率≥0.6、推进≥0.5ATR、MA正确一侧、回撤≤0.75ATR。自然MA止损仍推进，已有止损不放宽。',
      'S3_EXTENSION':'S2取消原空单RSI直接退出；多空加速且过度延伸先WATCH，固定观察ATR比较速度下降与回撤，两者达标PROTECT，加入观察极值±1ATR止损。'}[case]
    return common+text


def make_chart(src,market,identity,diags,daystates=None):
    slug=identity['slug'];key=identity.get('run_key',slug);summary=src.obj(f'runs/{key}/V3/full/summary.json')
    d=market.csv(f'market/{key}/daily_features.csv');assert not pd.to_datetime(d.timestamp,utc=True).duplicated().any()
    index={old.ms(r.timestamp):r for r in d.itertuples()}
    candles=[[old.ms(r.timestamp),r.open,r.high,r.low,r.close,finite(r.ma),finite(r.atr),finite(r.rsi),finite(r.slope),int(r.cross),bool(r.accel1)] for r in d.itertuples()]
    chart=dict(symbol=identity['symbol'],slug=key,cohortLabel=identity.get('cohortLabel',identity.get('cohort','历史连续段')),
      start=old.ms(summary['start']),end=old.ms(summary['end_exclusive']),candles=candles,defaultArm='V3',arms={},comparison=[],buyHold=None,
      dataEndedEarly=bool(identity.get('boundary_end_due_to_data',False)),fee=.001,slip=.0004)
    counts={}
    for case in CASES:
        rel=f'runs/{key}/{case}/full';s=src.obj(rel+'/summary.json');t=src.csv(rel+'/trades.csv');st=src.csv(rel+'/stops.csv');eq=pd.read_parquet(src.path(rel+'/equity.parquet'))
        validate_account(s,t);old.assert_account(s,t,st,eq)
        trades=[]
        for item in t.to_dict('records'):
            stop=st[st.trade_id.eq(item['trade_id'])].sort_values('timestamp',kind='stable');z=old.chart_trade(item,stop,index)
            for progress,r in zip(z['progress'],stop.to_dict('records')):
                progress['state']=clean({k:(None if pd.isna(v) else v) for k,v in r.items() if k.startswith('sm_')})
                state=progress['state'];watch_atr=state.get('sm_watch_atr')
                if watch_atr is not None and watch_atr>0:
                    bar=index[progress['signal']];prev=index.get(progress['signal']-86400000)
                    state['display_watch_retrace_atr']=item['side']*(state['sm_watch_extreme']-bar.close)/watch_atr
                    state['display_watch_current_speed']=item['side']*(bar.close-prev.close)/watch_atr if prev is not None else None
                progress['diagnostic']=(daystates or {}).get((identity['symbol'],int(item['trade_id']),progress['ts'])) if case=='V3' else None
            if case=='V3' and diags is not None:z['diagnostic']=diags.get((identity['symbol'],int(item['trade_id'])))
            trades.append(z)
        eq['timestamp']=pd.to_datetime(eq.timestamp,utc=True);eq=eq.groupby('timestamp',sort=True,as_index=False).last();eq=eq.groupby(eq.timestamp.dt.floor('D'),sort=True).tail(1)
        equity=[[old.ms(r.timestamp),r.equity] for r in eq.itertuples()]
        if equity[0][0]>chart['start']:equity.insert(0,[chart['start'],10000])
        chart['arms'][case]={'label':LABELS[case],'summary':s,'rules':chart_rules(case),'trades':trades,'equity':equity}
        m=metrics(t);stress={}
        for scenario in ['slippage_10bp','carry_5bp_day']:
            rel=f'sensitivity/{key}/{case}/{scenario}/summary.json'
            stress[scenario]=src.obj(rel)['return_pct'] if rel in src.hashes else None
        chart['comparison'].append(dict(case=case,label=LABELS[case],returnPct=s['return_pct'],drawdownPct=abs(s['max_drawdown_pct']),trades=len(t),
          winRate=m['win_rate_pct'],payoff=m['payoff_ratio'],expectancy=m['expectancy_cash'],slippage=stress['slippage_10bp'],carry=stress['carry_5bp_day']))
        counts[case]={'trades':len(t),'stop_rows':len(st),'bankrupt':bool(s['bankrupt'])}
    return chart,counts


def analyze_history(sources,out):
    out.mkdir(parents=True,exist_ok=False);rows=[];blocks=[];scopes=[];segments=[]
    for label,src in sources:
        summary=src.csv('summary.csv');b=src.csv('blocks.csv');sc=src.csv('scope.csv');sg=src.csv('segments.csv')
        assert set(summary.case_id)==set(CASES)
        scopes.append(sc.assign(source_group=label));segments.append(sg.assign(source_group=label));blocks.append(b.assign(source_group=label))
        for q in summary.to_dict('records'):
            t=src.csv(f"runs/{q['run_key']}/{q['case_id']}/full/trades.csv");validate_account(q,t);q.update(metrics(t));q['source_group']=label;rows.append(q)
    ranking=pd.DataFrame(rows);b=pd.concat(blocks,ignore_index=True);assert not ranking.duplicated(['source_group','run_key','case_id']).any()
    coh=summarize_cohorts(ranking,['source_group','case_id'])
    pairs,pc=paired(ranking,['source_group'],['run_key'])
    bs=[];bp=[]
    for (source_group,block),g in b.groupby(['source_group','block']):
        complete=g[g.status.eq('COMPLETE')];complete=complete.copy();complete['source_group']=source_group
        for case in CASES:
            p=g[g.case_id.eq(case)];q=complete[complete.case_id.eq(case)]
            bs.append(dict(source_group=source_group,block=block,case_id=case,total_segment_accounts=len(p),complete_segment_accounts=len(q),complete_coins=q.symbol.nunique(),
              partial_segment_accounts=int(p.status.eq('PARTIAL').sum()),no_overlap_segment_accounts=int(p.status.eq('NO_OVERLAP').sum()),
              defined_return_accounts=int(q.return_pct.notna().sum()),undefined_return_accounts=int(q.return_pct.isna().sum()),positive_accounts=int(q.return_pct.gt(0).sum()),
              median_return_pct=finite(q.return_pct.median()),median_drawdown_pct=finite(q.max_drawdown_pct.median())))
        if len(complete):
            for a,c in PAIRINGS:
                x=complete[complete.case_id.eq(a)].set_index('run_key');y=complete[complete.case_id.eq(c)].set_index('run_key').reindex(x.index)
                delta=x.return_pct-y.return_pct;dd=x.max_drawdown_pct-y.max_drawdown_pct
                bp.append(dict(source_group=source_group,block=block,candidate=a,control=c,complete_accounts=len(x),defined_pairs=int(delta.notna().sum()),
                  improved=int(delta.gt(1e-9).sum()),worsened=int(delta.lt(-1e-9).sum()),equal=int(delta.abs().le(1e-9).sum()),
                  median_delta_return_pp=finite(delta.median()),median_drawdown_reduction_pp=finite(dd.median())))
    tables={'ranking.csv':ranking,'blocks.csv':b,'block_summary.csv':pd.DataFrame(bs),'block_paired.csv':pd.DataFrame(bp),'cohort_summary.csv':coh,'paired_comparisons.csv':pairs,'paired_segment_results.csv':pc,
      'scope.csv':pd.concat(scopes,ignore_index=True),'segments.csv':pd.concat(segments,ignore_index=True)}
    for name,t in tables.items():emit(out/name,t)
    return tables


def load_tables(directory):
    s=Saved(directory,engine=False)
    for rel in s.hashes:s.path(rel)
    return {p.name:s.csv(p.name) for p in directory.glob('*.csv')},s


def chart_worker_init(source_dir,source_sha,market_dir,market_sha,diags,daystates,output,label):
    global CHART_SOURCE,CHART_MARKET,CHART_DIAGS,CHART_DAYSTATES,CHART_OUTPUT,CHART_LABEL
    CHART_SOURCE=Saved(source_dir,source_sha)
    CHART_MARKET=CHART_SOURCE if source_dir==market_dir else Saved(market_dir,market_sha,engine=False)
    CHART_DIAGS=diags;CHART_DAYSTATES=daystates;CHART_OUTPUT=Path(output);CHART_LABEL=label


def chart_worker(item):
    before_src=set(CHART_SOURCE.checked);before_market=set(CHART_MARKET.checked)
    chart,counts=make_chart(CHART_SOURCE,CHART_MARKET,item,CHART_DIAGS,CHART_DAYSTATES)
    key=item.get('run_key',item['slug']);page=f'coins/{key}.html' if CHART_LABEL=='current' else f'history/{CHART_LABEL}/{key}.html'
    rendered=old.render_template(Path(__file__).with_name('state_machine_coin_template.html'),chart)
    if CHART_LABEL!='current':
        rendered=rendered.replace('href="../index.html"','href="../../index.html"')
        rendered=rendered.replace('<p class="notice" id="boundaryNotice" hidden>', '<p class="notice">原冻结历史有已知来源不一致：2024-10-28小时数据与币安官方不一致。本页仅作受此限制的历史诊断，不能认定完整周期验证通过。此连续段独立注资，不能与同币其它段拼接收益。</p><p class="notice" id="boundaryNotice" hidden>')
    target=CHART_OUTPUT/page;assert not target.exists();target.write_text(rendered)
    return dict(page=page,sha256=sha(target),counts=counts,symbol=item['symbol'],run_key=key,
      source_hashes={k:v for k,v in CHART_SOURCE.checked.items() if k not in before_src},market_hashes={k:v for k,v in CHART_MARKET.checked.items() if k not in before_market})


def chart_batch(source,market,items,diags,daystates,output,label,audit,workers):
    with ProcessPoolExecutor(max_workers=workers,initializer=chart_worker_init,
      initargs=(source.directory,source.manifest_sha,market.directory,market.manifest_sha,diags,daystates,output,label)) as pool:
        futures=[pool.submit(chart_worker,item) for item in items]
        for n,future in enumerate(as_completed(futures),1):
            result=future.result();audit['outputs'][result['page']]=result['sha256']
            audit['pages'][result['page']]={'dataset':label,'symbol':result['symbol'],'run_key':result['run_key'],'cases':result['counts']}
            source.checked.update(result['source_hashes']);market.checked.update(result['market_hashes'])
            if n%100==0 or n==len(futures):print(f'Chart pages {label}: {n}/{len(futures)}',flush=True)


def build_pages(args,src,market,current,histories,hist):
    output=args.output;output.mkdir(parents=True,exist_ok=False);(output/'coins').mkdir()
    diagnostic=Saved(args.diagnostics/'state_features',engine=False);context=json.loads((args.diagnostics/'run_context.json').read_text())
    assert context['fee_rate']==.001 and context['slippage_rate']==.0004 and context['source_manifest_sha256']==src.manifest_sha
    dt=diagnostic.csv('all_trade_features.csv');ds=diagnostic.csv('all_complete_day_states.csv')
    assert len(dt)==int(current['ranking.csv'].query("case_id=='V3'").trades.sum())
    keep=['symbol','slug','cohort','trade_id','side','entry_time','exit_time','exit_reason','net_pnl','net_outcome','terminal_exit',
      'actual_net_return_on_entry_equity_pct','pre_directional_displacement_20_atr','pre_efficiency20','pre_volatility_ratio5_20',
      'pre_displacement20_bin','pre_efficiency20_bin','pre_volatility_ratio_bin','mfe_atr_lower','mfe_atr_upper',
      'profit_given_back_cash_lower','profit_given_back_cash_upper','mfe_1atr_status','mfe_2atr_status','first_complete_day_observed','third_complete_day_observed']
    diagnostics=records(dt[keep]);diags={(r['symbol'],int(r['trade_id'])):r for r in diagnostics}
    statekeys=['held_complete_day_number','pullback_from_favorable_extreme_atr','daily_mfe_entry_atr','directional_market_close_er3',
      'market_close_er3_missing_reason','market_close_er3_includes_preentry_close','directional_speed_atrprev','directional_ma7_offset_atr','net_liquidation_profit_at_close_cash']
    daystates={(r['symbol'],int(r['trade_id']),old.ms(r['state_available_at'])):{key:r[key] for key in statekeys} for r in records(ds)}
    rank=current['ranking.csv'];scope=current['scope.csv'];data=dict(labels=LABELS,cohorts=records(current['cohort_summary.csv']),diagnostics=diagnostics,
      fixed=records(current['fixed_entry_summary.csv']),coins=[],history=[],historySources=[label for label,s in histories],historyBlockNames=[],historyCoverage='',links=[],diagLinks=[],fixedLinks=[],historyLinks=[])
    audit={'outputs':{},'pages':{},'fee':.001,'slip':.0004,'browser_qa_performed':False,'diagnostics_manifest':diagnostic.manifest(),
      'diagnostic_context_sha256':sha(args.diagnostics/'run_context.json'),'diagnostic_trade_count':len(dt),'diagnostic_day_states':len(ds)}
    jobs=[]
    for item in scope.to_dict('records'):
        group=rank[rank.slug.eq(item['slug'])];row=dict(symbol=item['symbol'],slug=item['slug'],cohort=item['cohort'],days=int(item['trade_days']),
          start=item.get('trade_start'),end=item.get('end'),boundary=bool(item.get('boundary_end_due_to_data',False)),cases={},page=None,reason=item['status'])
        if len(group):
            assert len(group)==4
            row['cases']={r['case_id']:r for r in records(group)};row['page']=f"coins/{item['slug']}.html"
            jobs.append(item)
        data['coins'].append(row)
    chart_batch(src,market,jobs,diags,daystates,output,'current',audit,args.workers)
    if hist is not None:
        hr=hist['ranking.csv'];blocks=hist['blocks.csv'];data['historyBlockNames']=sorted(blocks.block.unique());fullcycles=blocks.query("block=='cycle_2020_2024' and case_id=='V3' and status=='COMPLETE'")
        data['historyCoverage']=f"主范围与补充范围共 {hist['scope.csv'].symbol.nunique()} 个代码，{hr.symbol.nunique()} 币有可交易段；{len(hr)//4} 个独立连续段、{len(hr)} 个账户。2020—2024完整连续覆盖只有 {fullcycles.symbol.nunique()} 币 / {len(fullcycles)} 段；这些段仍受上述冻结来源问题限制。"
        for label,source in histories:
            folder=output/'history'/label;folder.mkdir(parents=True)
            h=hr[hr.source_group.eq(label)];jobs=[]
            for key,g in h.groupby('run_key',sort=True):
                item=g[g.case_id.eq('V3')].iloc[0].to_dict();item['cohortLabel']=f"{label} · {key} · 独立连续段 · 历史来源有已知不一致"
                jobs.append(item);page=f'history/{label}/{key}.html'
                data['history'].append(dict(symbol=item['symbol'],run_key=key,source_group=label,block='full',status='独立连续段',start=item['start'],end=item['end_exclusive'],
                  cases={r['case_id']:{'return_pct':r['return_pct'],'max_drawdown_pct':r['max_drawdown_pct']} for r in records(g)},page=page))
                for block,b in blocks[blocks.source_group.eq(label)&blocks.run_key.eq(key)].groupby('block'):
                    v=b[b.case_id.eq('V3')].iloc[0];data['history'].append(dict(symbol=item['symbol'],run_key=key,source_group=label,block=block,status=v.status,
                      start=v.get('actual_start'),end=v.get('actual_end'),cases={r['case_id']:{'return_pct':r['return_pct'],'max_drawdown_pct':r['max_drawdown_pct']} for r in records(b)},page=page))
            chart_batch(source,source,jobs,None,None,output,label,audit,args.workers)
    else:data['historyCoverage']='本入口未装入长历史资料；长历史正在独立核验，不以当前433天代替完整周期。'
    def link(path,label):return dict(href=os.path.relpath(path,output),label=label)
    data['links']=[link(args.analysis/name,label) for name,label in [('ranking.csv','全部账户与指标'),('cohort_summary.csv','历史组汇总'),('paired_comparisons.csv','同币成对比较'),('account_cash_by_side_exit.csv','每币多空及终止退出现金'),('source_manifest.json','分析来源清单')]]
    data['diagLinks']=[link(args.diagnostics/'state_features'/name,label) for name,label in [('all_trade_features.csv','全交易特征'),('all_complete_day_states.csv','全部完整持仓日'),('landmark_survival_counts.csv','第1/3日存活分母'),('pre_cross_bin_cash_by_coin.csv','分币固定特征箱现金')]]
    data['diagLinks'].append(link(ROUND/'diagnostics_work/legacy_v3_old_costs/legacy_cost_and_location_note.json','旧成本诊断说明'))
    data['fixedLinks']=[link(args.analysis/'fixed_entry_pairs.csv','全部固定入场逐笔对照'),link(args.analysis/'fixed_entry_summary.csv','全部固定对照分组')]
    if hist is not None:data['historyLinks']=[link(args.history_analysis/name,label) for name,label in [('ranking.csv','全部独立段账户'),('blocks.csv','全部日历块与覆盖'),('block_summary.csv','完整覆盖组汇总'),('block_paired.csv','完整覆盖成对变化'),('scope.csv','包含排除项的全部历史代码'),('segments.csv','全部连续段与不足预热段')]]
    write_json(output/'index_payload.json',data)
    (output/'index.html').write_text(old.render_template(Path(__file__).with_name('state_machine_index_template.html'),data))
    for name in ['index_payload.json','index.html']:audit['outputs'][name]=sha(output/name)
    audit['total_chart_pages']=len(audit['pages']);audit['total_trades']=sum(c['trades'] for p in audit['pages'].values() for c in p['cases'].values());audit['total_stop_rows']=sum(c['stop_rows'] for p in audit['pages'].values() for c in p['cases'].values())
    audit['templates']={p.name:sha(p) for p in Path(__file__).parent.glob('state_machine_*_template.html')};audit['builder_sha256']=sha(Path(__file__))
    audit['sources']={'current':src.manifest(),'market':market.manifest(),'histories':{label:s.manifest() for label,s in histories}}
    write_json(output/'chart_audit.json',audit);shutil.copy2(Path(__file__),output/'source_builder.py.txt')
    for p in Path(__file__).parent.glob('state_machine_*_template.html'):shutil.copy2(p,output/(p.name+'.txt'))
    freeze(output)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--current',type=Path,default=ROUND/'results_current');ap.add_argument('--current-sha')
    ap.add_argument('--market',type=Path,default=BASE/'artifacts/results_20260909');ap.add_argument('--market-sha',default='880d7201b4c23695265d80d2704e0ec03245dfdb8a274b50873f82fbfb50a13d')
    ap.add_argument('--diagnostics',type=Path,default=ROUND/'diagnostics_work/current_v3_new_costs')
    ap.add_argument('--history',action='append',default=[],help='label=directory; include only complete producer manifests')
    ap.add_argument('--output',type=Path,default=ROUND/'html_current');ap.add_argument('--analysis',type=Path,default=ROUND/'analysis_current')
    ap.add_argument('--analysis-only',action='store_true');ap.add_argument('--reuse-analysis',action='store_true')
    ap.add_argument('--history-analysis',type=Path,default=ROUND/'analysis_history');ap.add_argument('--workers',type=int,default=3);args=ap.parse_args()
    src=Saved(args.current,args.current_sha);market=Saved(args.market,args.market_sha,engine=False)
    current,current_reader=load_tables(args.analysis) if args.reuse_analysis else (analyze_current(src,args.analysis),None)
    histories=[(part.split('=',1)[0],Saved(part.split('=',1)[1])) for part in args.history]
    if histories:
        hist,history_reader=load_tables(args.history_analysis) if args.history_analysis.exists() else (analyze_history(histories,args.history_analysis),None)
        if history_reader is None:
            write_json(args.history_analysis/'source_manifest.json',{'histories':{label:s.manifest() for label,s in histories},'script_sha256':sha(Path(__file__)),'simulation_performed':False})
            shutil.copy2(Path(__file__),args.history_analysis/'source_script.py.txt');freeze(args.history_analysis)
    else:hist=None
    if not args.analysis_only:build_pages(args,src,market,current,histories,hist)
    manifest={'current':src.manifest(),'market':market.manifest(),'histories':{label:s.manifest() for label,s in histories},'script_sha256':sha(Path(__file__)),
      'fee':.001,'slip':.0004,'simulation_performed':False,'templates':{p.name:sha(p) for p in Path(__file__).parent.glob('state_machine_*_template.html')}}
    if not args.reuse_analysis:
        shutil.copy2(Path(__file__),args.analysis/'source_script.py.txt');write_json(args.analysis/'source_manifest.json',manifest);freeze(args.analysis)
    print(json.dumps({'analysis':str(args.analysis),'html':str(args.output) if not args.analysis_only else None,'manifest_sha256':sha(args.analysis/'artifact_checksums.json')}))


if __name__=='__main__':main()
