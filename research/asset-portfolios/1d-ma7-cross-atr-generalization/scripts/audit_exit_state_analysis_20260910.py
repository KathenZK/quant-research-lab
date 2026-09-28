"""Independent retained-ledger analysis audit. No strategy or producer imports."""
from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[2]
ROUND = BASE / 'artifacts/state_machine_20260910'
CURRENT = ROUND / 'results_current'
ANALYSIS = ROUND / 'analysis_current'
ACCEL = ROUND / 'acceleration_diagnostics'
MARKET = BASE / 'artifacts/results_20260909'
CASES = ['V3', 'S1_DEFENSE', 'S2_TREND', 'S3_EXTENSION']
COMPARISONS = [('S1_DEFENSE','V3'), ('S2_TREND','S1_DEFENSE'),
               ('S3_EXTENSION','S2_TREND'), ('S2_TREND','V3'), ('S3_EXTENSION','V3')]
FACTORS = ['atr_accel','pct5_accel','ma2_atr','rsi80_20','short_rsi30',
           'short_atr_accel_rsi30','atr_accel_ma2']
DAY = 86400000000000
HOUR = DAY // 24
CHECKS = Counter()
BOUND = {}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    try:
        return pd.read_csv(p, float_precision='round_trip')
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def bind(directory):
    manifest = directory / 'artifact_checksums.json'
    entries = json.loads(manifest.read_text())
    for name, expected in entries.items():
        assert sha(directory / name) == expected, (directory, name)
    BOUND[str(directory.relative_to(ROOT))] = {'manifest_sha256':sha(manifest), 'files':len(entries)}


def same(actual, expected, label):
    if pd.isna(expected):
        assert pd.isna(actual), (label, actual, expected)
    elif isinstance(expected, (bool, np.bool_)):
        assert isinstance(actual, (bool,np.bool_)) and actual == expected, (label,actual,expected)
    elif isinstance(expected, (int, float, np.integer, np.floating)):
        assert pd.notna(actual) and math.isclose(float(actual), float(expected), rel_tol=3e-11, abs_tol=1e-7), (label,actual,expected)
    else:
        assert str(actual) == str(expected), (label, actual, expected)
    CHECKS['compared_cells'] += 1


def table(expected, actual, keys, name):
    e = pd.DataFrame(expected) if not isinstance(expected, pd.DataFrame) else expected
    assert len(e) == len(actual), (name,'rows',len(e),len(actual))
    assert not e.duplicated(keys).any() and not actual.duplicated(keys).any(), (name,'duplicate keys')
    a = actual.set_index(keys)
    b = e.set_index(keys)
    assert set(a.index) == set(b.index), (name,'different keys')
    # Align once, then compare whole columns; no sampling and no repeated .loc.
    a = a.reindex(b.index)
    for field in b.columns:
        expected = b[field]
        actual_values = a[field]
        missing = expected.isna().to_numpy()
        actual_missing = actual_values.isna().to_numpy()
        ok = missing & actual_missing
        valid = ~missing & ~actual_missing
        if pd.api.types.is_bool_dtype(expected.dtype):
            ok[valid] = actual_values.to_numpy()[valid] == expected.to_numpy()[valid]
        elif pd.api.types.is_numeric_dtype(expected.dtype):
            ok[valid] = np.isclose(actual_values.to_numpy()[valid].astype(float), expected.to_numpy()[valid].astype(float),
                                   rtol=3e-11, atol=1e-7)
        else:
            ok[valid] = actual_values.astype(str).to_numpy()[valid] == expected.astype(str).to_numpy()[valid]
        if not ok.all():
            ix=int(np.flatnonzero(~ok)[0])
            same(actual_values.iloc[ix],expected.iloc[ix],(name,b.index[ix],field))
            raise AssertionError((name,field,'column comparison disagrees with scalar comparator'))
        CHECKS['compared_cells'] += len(b)
    CHECKS[name+'_rows'] = len(e)


def stats(t):
    net = t.net_pnl.to_numpy() if len(t) else np.array([],dtype=float)
    win = net[net>0]; loss = -net[net<0]; n = len(net)
    positive = math.fsum(win); negative = math.fsum(loss)
    aw = positive/len(win) if len(win) else np.nan
    al = negative/len(loss) if len(loss) else np.nan
    result = dict(trades=n,wins=len(win),losses=len(loss),flat_trades=int((net==0).sum()),
        win_rate_pct=len(win)*100/n if n else np.nan,average_win_cash=aw,average_loss_cash=al,
        payoff_ratio=aw/al if len(win) and len(loss) else np.nan,
        payoff_ratio_status='DEFINED' if len(win) and len(loss) else 'NO_WINNERS' if not len(win) else 'NO_LOSERS',
        expectancy_cash=math.fsum(net)/n if n else np.nan,
        profit_factor=positive/negative if negative else np.nan,
        profit_factor_status='DEFINED' if negative else 'NO_TRADES' if not n else 'NO_LOSSES',
        positive_cash=positive,negative_cash=negative,net_cash=math.fsum(net),
        terminal_trades=int(t.exit_reason.eq('sample_end').sum()) if n else 0)
    for field, col in [('gross_cash','gross_pnl'),('entry_fees_cash','entry_fee'),('exit_fees_cash','exit_fee'),
                       ('recorded_funding_cash','funding_paid'),('carry_cash','carry_paid')]:
        result[field]=math.fsum(t[col]) if n else 0.
    for field in ['average_trade_return_pct','median_trade_return_pct','average_winning_trade_return_pct',
                  'average_losing_trade_return_pct','worst_trade_return_pct','top5_winners_share_pct']:
        result[field]=np.nan
    if n:
        ret=t.net_pnl.to_numpy()/t.entry_equity.to_numpy()*100
        result.update(average_trade_return_pct=float(np.mean(ret)),median_trade_return_pct=float(np.median(ret)),
            average_winning_trade_return_pct=float(np.mean(ret[net>0])) if len(win) else np.nan,
            average_losing_trade_return_pct=float(-np.mean(ret[net<0])) if len(loss) else np.nan,
            worst_trade_return_pct=float(np.min(ret)),
            top5_winners_share_pct=math.fsum(sorted(win,reverse=True)[:5])/positive*100 if positive else np.nan)
    return result


def check_cash(t, fee=.001, slip=.0004):
    if not len(t):
        return
    side=t.side.to_numpy(); qty=t.qty.to_numpy()
    buy=t.entry_reference.to_numpy()*(1+side*slip)
    sell=t.exit_reference.to_numpy()*(1-side*slip)
    expected = {'entry_price':buy,'exit_price':sell,'entry_fee':buy*qty*fee,'exit_fee':sell*qty*fee,
                'gross_pnl':side*qty*(sell-buy)}
    expected['net_pnl']=expected['gross_pnl']-expected['entry_fee']-expected['exit_fee']-t.funding_paid.to_numpy()-t.carry_paid.to_numpy()
    for k,v in expected.items():
        assert np.allclose(t[k],v,rtol=3e-11,atol=1e-7),(k,'cash')
    CHECKS['cash_reconstructed_trades'] += len(t)


def audit_analysis(scope):
    ranking=[]; side_rows=[]; fixed=[]; stress_rows=[]
    audit=json.loads((ROUND/'audit_current.json').read_text())
    assert audit['status']=='PASS' and audit['accounts']==7332 and audit['fixed_pairs']==27525
    assert audit['identity']['result_manifest_sha256']==sha(CURRENT/'artifact_checksums.json')
    for count, item in enumerate(scope[scope.cohort.ne('excluded')].to_dict('records'),1):
        slug=item['slug']; symbol=item['symbol']; cohort=item['cohort']
        base=read(CURRENT/f'runs/{slug}/V3/full/trades.csv')
        good=base[base.net_pnl>0] if len(base) else base
        top=set(good.sort_values('net_pnl',ascending=False,kind='stable').head(5).trade_id) if len(good) else set()
        for case in CASES:
            directory=CURRENT/f'runs/{slug}/{case}/full'
            s=json.loads((directory/'summary.json').read_text()); t=read(directory/'trades.csv')
            check_cash(t); m=stats(t)
            same(s['ending_equity'],10000+m['net_cash'],(slug,case,'ending_equity'))
            same(s['fee_total'],m['entry_fees_cash']+m['exit_fees_cash'],(slug,case,'fee_total'))
            row={**s,**m,'symbol':symbol,'slug':slug,'cohort':cohort,'case_id':case,'trade_days':item['trade_days']}
            row['return_pct']=m['net_cash']/10000*100
            row['risk_pass']=bool(item['trade_days']>=180 and len(t)>=10 and row['return_pct']>0 and s['max_drawdown_pct']>=-30 and not s['bankrupt'])
            pass_stress=True
            for scenario in ['slippage_10bp','carry_5bp_day']:
                dr=CURRENT/f'sensitivity/{slug}/{case}/{scenario}'
                u=read(dr/'trades.csv'); check_cash(u,slip=.001 if scenario=='slippage_10bp' else .0004)
                z=json.loads((dr/'summary.json').read_text()); actual_return=math.fsum(u.net_pnl)/100 if len(u) else 0.
                same(z['return_pct'],actual_return,(slug,case,scenario,'return'))
                for field in ['return_pct','max_drawdown_pct','trades','bankrupt']:
                    row[scenario+'_'+field]=z[field]
                stress_rows.append(dict(slug=slug,case_id=case,scenario=scenario,return_pct=actual_return,
                                        max_drawdown_pct=z['max_drawdown_pct'],trades=len(u),bankrupt=z['bankrupt']))
                pass_stress=pass_stress and actual_return>0 and not z['bankrupt']
            row['stress_pass']=bool(row['risk_pass'] and pass_stress)
            ranking.append(row)
            for side in ['all','long','short']:
                ti=t if side=='all' or not len(t) else t[t.side==(1 if side=='long' else -1)]
                for bucket in ['all','nonterminal','sample_end']:
                    tt=ti if bucket=='all' or not len(ti) else ti[ti.exit_reason.eq('sample_end')==(bucket=='sample_end')]
                    side_rows.append(dict(symbol=symbol,slug=slug,cohort=cohort,case_id=case,side_group=side,exit_bucket=bucket,**stats(tt)))
            if case!='V3':
                f=read(CURRENT/f'fixed_entries/{slug}/{case}/trades.csv')
                assert len(f)==len(base),(slug,case,'fixed count')
                if len(f):
                    check_cash(f)
                    b=base.set_index('trade_id').loc[f.source_trade_id]
                    terminal=f.exit_reason.eq('sample_end').to_numpy()|b.exit_reason.eq('sample_end').to_numpy()
                    assert np.array_equal(f.either_terminal.to_numpy(),terminal),(slug,case,'terminal union')
                    f=f.copy();f['symbol']=symbol;f['slug']=slug;f['cohort']=cohort;f['case_id']=case
                    f['baseline_top5_winner']=f.source_trade_id.isin(top)
                    f['baseline_net_pnl']=b.net_pnl.to_numpy();f['either_terminal']=terminal
                    f['baseline_outcome']=np.where(f.baseline_net_pnl>0,'win',np.where(f.baseline_net_pnl<0,'loss','flat'))
                    f['delta_net_pnl']=f.net_pnl-f.baseline_net_pnl
                    f['delta_return']=f.delta_net_pnl/f.entry_equity
                    fixed.append(f)
        if count%100==0: print('Analysis audit coins',count,flush=True)
    rank=pd.DataFrame(ranking);fix=pd.concat(fixed,ignore_index=True)
    table(rank,read(ANALYSIS/'ranking.csv'),['slug','case_id'],'ranking')
    table(side_rows,read(ANALYSIS/'account_cash_by_side_exit.csv'),['slug','case_id','side_group','exit_bucket'],'side_exit')
    table(stress_rows,read(ANALYSIS/'stress.csv'),['slug','case_id','scenario'],'stress')
    table(fix,read(ANALYSIS/'fixed_entry_pairs.csv'),['slug','case_id','source_trade_id'],'fixed_pairs')
    median_fields=['win_rate_pct','average_win_cash','average_loss_cash','payoff_ratio','expectancy_cash',
                   'profit_factor','average_trade_return_pct','worst_trade_return_pct','top5_winners_share_pct','exposure_pct']
    cohorts=[]; pairs=[]; paircoins=[]
    for (cohort,case),g in rank.groupby(['cohort','case_id']):
        row=dict(cohort=cohort,case_id=case,accounts=len(g),coins=g.symbol.nunique(),positive_accounts=int((g.return_pct>0).sum()),
            zero_trade_accounts=int((g.trades==0).sum()),bankrupt_accounts=int(g.bankrupt.sum()),total_trades=int(g.trades.sum()),
            terminal_trades=int(g.terminal_trades.sum()),median_return_pct=g.return_pct.median(),median_drawdown_pct=g.max_drawdown_pct.median(),
            risk_pass_accounts=int(g.risk_pass.sum()),stress_pass_accounts=int(g.stress_pass.sum()))
        for field in median_fields:
            row['median_'+field]=g[field].median();row[field+'_defined_accounts']=int(g[field].notna().sum())
        cohorts.append(row)
    for cohort,g in rank.groupby('cohort'):
        for candidate,control in COMPARISONS:
            a=g[g.case_id==candidate].set_index('symbol');b=g[g.case_id==control].set_index('symbol').loc[a.index]
            dr=a.return_pct.to_numpy()-b.return_pct.to_numpy();dd=a.max_drawdown_pct.to_numpy()-b.max_drawdown_pct.to_numpy()
            row=dict(cohort=cohort,candidate=candidate,control=control,accounts=len(a),
                return_improved=int((dr>1e-9).sum()),return_worsened=int((dr< -1e-9).sum()),return_equal=int((abs(dr)<=1e-9).sum()),
                drawdown_improved=int((dd>1e-9).sum()),drawdown_worsened=int((dd< -1e-9).sum()),drawdown_equal=int((abs(dd)<=1e-9).sum()),
                return_improved_drawdown_not_worse=int(((dr>1e-9)&(dd>=-1e-9)).sum()),
                median_delta_return_pp=float(np.median(dr)),median_drawdown_reduction_pp=float(np.median(dd)))
            pairs.append(row)
            for symbol,r,d in zip(a.index,dr,dd):
                paircoins.append(dict(cohort=cohort,candidate=candidate,control=control,symbol=symbol,delta_return_pp=r,drawdown_reduction_pp=d))
    table(cohorts,read(ANALYSIS/'cohort_summary.csv'),['cohort','case_id'],'cohorts')
    table(pairs,read(ANALYSIS/'paired_comparisons.csv'),['cohort','candidate','control'],'paired')
    table(paircoins,read(ANALYSIS/'paired_coin_results.csv'),['cohort','candidate','control','symbol'],'paired_coins')
    fixed_summaries=[]
    for (cohort,case),g in fix.groupby(['cohort','case_id']):
        for side in ['all','long','short']:
            for terminal in ['all','neither_terminal','either_terminal']:
                for kind in ['all','baseline_win','baseline_loss','baseline_top5_winner']:
                    mask=np.ones(len(g),dtype=bool)
                    if side!='all':mask &= g.side.to_numpy()==(1 if side=='long' else -1)
                    if terminal!='all':mask &= g.either_terminal.to_numpy()==(terminal=='either_terminal')
                    if kind=='baseline_top5_winner':mask &= g.baseline_top5_winner.to_numpy()
                    elif kind!='all':mask &= g.baseline_outcome.to_numpy()==kind[9:]
                    p=g.iloc[np.flatnonzero(mask)];d=p.delta_net_pnl.to_numpy();dr=p.delta_return.to_numpy()*100
                    oldpositive=math.fsum(p.baseline_net_pnl[p.baseline_net_pnl>0]);newpositive=math.fsum(p.net_pnl[p.net_pnl>0])
                    fixed_summaries.append(dict(cohort=cohort,case_id=case,side_group=side,terminal_bucket=terminal,control_group=kind,
                        pairs=len(p),coins=p.symbol.nunique(),improved=int((d>1e-9).sum()),worsened=int((d< -1e-9).sum()),equal=int((abs(d)<=1e-9).sum()),
                        delta_cash_sum=math.fsum(d),median_delta_return_pp=float(np.median(dr)) if len(p) else np.nan,
                        mean_delta_return_pp=math.fsum(dr)/len(p) if len(p) else np.nan,baseline_cash_sum=math.fsum(p.baseline_net_pnl),candidate_cash_sum=math.fsum(p.net_pnl),
                        baseline_positive_cash=oldpositive,candidate_positive_cash=newpositive,positive_cash_retention_pct=newpositive/oldpositive*100 if oldpositive else np.nan,
                        positive_outcomes_retained=int((p.net_pnl>0).sum()),candidate_loss_count=int((p.net_pnl<0).sum())))
    table(fixed_summaries,read(ANALYSIS/'fixed_entry_summary.csv'),['cohort','case_id','side_group','terminal_bucket','control_group'],'fixed_summary')
    assert len(rank)==2444 and len(cohorts)==12 and len(pairs)==15 and len(fixed_summaries)==324
    return {'accounts':len(rank),'fixed_pairs':len(fix),'cohort_groups':len(cohorts),'paired_groups':len(pairs),'fixed_groups':len(fixed_summaries),
            'top_five_definition':'Each coin V3 actual strictly positive net-cash trades, descending, at most five; chosen before candidate comparison.',
            'terminal_pair_definition':'Union of baseline and candidate sample_end; all, neither, either inspected separately.',
            'cash_identity':'Gross less each entry/exit fee, recorded funding and carry; quantities and both adverse fills checked.',
            'drawdown_and_exposure_source':'Underlying per-account saved summary, already independently checked against every equity mark by audit_current.json.'}


def utc_ns(values):
    return pd.to_datetime(values,utc=True,format='mixed').astype('datetime64[ns, UTC]').astype('int64').to_numpy()


def audit_acceleration(scope):
    events=[]; coverage=[]; early=[]; state_count=0; terminal_days_excluded=0
    for count,item in enumerate(scope[scope.cohort.ne('excluded')].to_dict('records'),1):
        slug=item['slug'];symbol=item['symbol'];cohort=item['cohort']
        d=read(MARKET/f'market/{slug}/daily_features.csv');h=pd.read_parquet(MARKET/f'market/{slug}/hourly.parquet')
        dn=utc_ns(d.timestamp);hn=utc_ns(h.timestamp)
        assert (np.diff(hn)==HOUR).all() and (np.diff(dn)==DAY).all(),slug
        close=d.close.to_numpy();atr=d.atr.to_numpy();ma=d.ma.to_numpy();rsi=d.rsi.to_numpy()
        op=h.open.to_numpy();hi=h.high.to_numpy();lo=h.low.to_numpy();hc=h.close.to_numpy()
        t=read(CURRENT/f'runs/{slug}/V3/full/trades.csv')
        account=json.loads((CURRENT/f'runs/{slug}/V3/full/summary.json').read_text())
        end=pd.Timestamp(account['end_exclusive']).value
        for tr in t.to_dict('records'):
            assert tr['funding_paid']==0 and tr['carry_paid']==0, 'Nonzero carry/funding requires event-time accrued costs, not final trade totals'
            entry=pd.Timestamp(tr['entry_time']).value;exit=pd.Timestamp(tr['exit_time']).value;s=int(tr['side'])
            days=np.flatnonzero((dn>=entry)&(dn+DAY<=exit)&(dn+DAY<end))
            state_count+=len(days)
            if tr['exit_reason']=='sample_end' and exit==end and np.any(dn+DAY==end):terminal_days_excluded+=1
            seen=set()
            for held,i in enumerate(days,1):
                reference_close=close[i]*(1-s*.0004)
                net=s*tr['qty']*(reference_close-tr['entry_price'])-tr['entry_fee']-tr['qty']*reference_close*.001-tr['funding_paid']-tr['carry_paid']
                if net<=0:continue
                delta=s*(close[i]-close[i-1]);before=s*(close[i-1]-close[i-2])
                pct=s*(close[i]/close[i-1]-1);previouspct=s*(close[i-1]/close[i-2]-1)
                accel=delta>=atr[i-1] and delta>max(before,0)
                distance=s*(close[i]-ma[i])/atr[i]
                far=distance>=2;extreme=rsi[i]>=80 if s==1 else rsi[i]<=20;short30=s==-1 and rsi[i]<=30
                flags=[accel,pct>=.05 and pct>max(previouspct,0),far,extreme,short30,accel and short30,accel and far]
                for factor,hit in zip(FACTORS,flags):
                    if not hit or factor in seen:continue
                    seen.add(factor);when=dn[i]+DAY
                    base=dict(symbol=symbol,slug=slug,cohort=cohort,source_trade_id=int(tr['trade_id']),side=s,factor=factor,
                        signal_day=str(pd.Timestamp(dn[i],tz='UTC')),event_time=str(pd.Timestamp(when,tz='UTC')),held_days=held,
                        baseline_exit_time=str(pd.Timestamp(exit,tz='UTC')),baseline_already_exits_at_event=exit==when,
                        estimated_net_profit_at_event=net,final_baseline_outcome='win' if tr['net_pnl']>0 else 'loss' if tr['net_pnl']<0 else 'flat',
                        baseline_terminal=tr['exit_reason']=='sample_end',directional_pct=pct*100,directional_atr_speed=delta/atr[i-1],
                        directional_ma_distance_atr=distance,rsi6=rsi[i],atr=atr[i])
                    for length in [5,10,20]:
                        row={**base,'horizon_days':length}; loc=np.flatnonzero(hn==when)
                        if not len(loc):row.update(complete=False,censor_reason='NO_NEXT_OPEN')
                        else:
                            start=int(loc[0]);stop=start+length*24
                            valid=stop<=len(hn) and np.array_equal(hn[start:stop],when+np.arange(length*24,dtype=np.int64)*HOUR)
                            if not valid:row.update(complete=False,censor_reason='INCOMPLETE_FORWARD_WINDOW')
                            else:
                                ref=op[start];last=hc[stop-1]
                                favorable=max(0.,float(np.max(s*(np.where(s==1,hi[start:stop],lo[start:stop])-ref))))
                                adverse=max(0.,float(np.max(-s*(np.where(s==1,lo[start:stop],hi[start:stop])-ref))))
                                row.update(complete=True,censor_reason='',reference_next_open=ref,
                                    end_directional_atr=s*(last-ref)/atr[i],end_directional_pct=s*(last-ref)/ref*100,
                                    maximum_favorable_atr=favorable/atr[i],maximum_adverse_atr=adverse/atr[i],
                                    maximum_favorable_pct=favorable/ref*100,maximum_adverse_pct=adverse/ref*100)
                        events.append(row)
        for case in CASES[1:]:
            dr=CURRENT/f'runs/{slug}/{case}/full';ct=read(dr/'trades.csv');st=read(dr/'stops.csv')
            st=st[st.full_holding_day] if len(st) else st
            tests=[('sm_defense','sm_defense',True),('sm_healthy','sm_healthy',True),('sm_protect','sm_protect',True),
                   ('healthy_pause','tightening_trigger','healthy_pause'),('watch_started','sm_transition','watch_started'),('watch_cleared','sm_transition','watch_cleared')]
            for metric,col,val in tests:
                hits=st[st[col].eq(val)] if len(st) and col in st else st.iloc[:0]
                coverage.append(dict(symbol=symbol,cohort=cohort,case_id=case,metric=metric,days=len(hits),
                                     trades_with_state=hits.trade_id.nunique() if len(hits) else 0,total_trades=len(ct)))
            fixed=read(CURRENT/f'fixed_entries/{slug}/{case}/trades.csv')
            if len(fixed):
                b=t.set_index('trade_id').loc[fixed.source_trade_id]
                valid=(b.net_pnl.to_numpy()>0)&~(b.exit_reason.eq('sample_end').to_numpy()|fixed.exit_reason.eq('sample_end').to_numpy())
                fw=fixed.iloc[np.flatnonzero(valid)]
                before=utc_ns(fw.exit_time)-utc_ns(fw.entry_time)<3*DAY
                early.append(dict(symbol=symbol,cohort=cohort,case_id=case,original_winners=len(fw),
                                  exited_before_three_complete_days=int(before.sum()),became_loss_before_three_days=int((before&(fw.net_pnl.to_numpy()<0)).sum()),
                                  became_loss_total=int((fw.net_pnl<0).sum())))
        if count%100==0:print('Acceleration audit coins',count,flush=True)
    ev=pd.DataFrame(events);actual=read(ACCEL/'events_and_future_paths.csv')
    for col in ['signal_day','event_time','baseline_exit_time']:
        actual[col]=pd.to_datetime(actual[col],utc=True,format='mixed').astype(str)
    actual.censor_reason=actual.censor_reason.fillna('')
    table(ev,actual,['symbol','source_trade_id','factor','horizon_days'],'acceleration_paths')
    table(coverage,read(ACCEL/'state_coverage_by_coin.csv'),['symbol','case_id','metric'],'state_coverage_coin')
    table(early,read(ACCEL/'early_exit_original_winners.csv'),['symbol','case_id'],'early_winners_coin')
    summaries=[];coins=[]
    metrics=['end_directional_atr','end_directional_pct','maximum_favorable_atr','maximum_adverse_atr','maximum_favorable_pct','maximum_adverse_pct']
    for (cohort,side,factor,horizon),g in ev.groupby(['cohort','side','factor','horizon_days']):
        valid=g[g.complete]
        r=dict(cohort=cohort,side=side,factor=factor,horizon_days=horizon,events=len(g),coins=g.symbol.nunique(),
               complete_events=len(valid),censored_events=len(g)-len(valid),baseline_exits_at_event=int(g.baseline_already_exits_at_event.sum()),
               continuation_end_positive_pct=(valid.end_directional_atr>0).mean()*100 if len(valid) else np.nan)
        for key in metrics:r['median_'+key]=valid[key].median()
        summaries.append(r)
        for symbol,cg in g.groupby('symbol'):
            cv=cg[cg.complete]
            coins.append(dict(cohort=cohort,symbol=symbol,side=side,factor=factor,horizon_days=horizon,events=len(cg),complete_events=len(cv),
                median_end_directional_atr=cv.end_directional_atr.median(),median_maximum_favorable_atr=cv.maximum_favorable_atr.median(),median_maximum_adverse_atr=cv.maximum_adverse_atr.median()))
    table(summaries,read(ACCEL/'factor_summary.csv'),['cohort','side','factor','horizon_days'],'factor_summary')
    table(coins,read(ACCEL/'factor_by_coin.csv'),['cohort','symbol','side','factor','horizon_days'],'factor_by_coin')
    overlap=[];single=ev[ev.horizon_days==10]
    for (cohort,side),g in single.groupby(['cohort','side']):
        maps={f:{(r.symbol,r.source_trade_id):r.event_time for r in g[g.factor==f].itertuples()} for f in FACTORS}
        for a,b in combinations(FACTORS,2):
            aa=maps[a];bb=maps[b];shared=set(aa)&set(bb)
            overlap.append(dict(cohort=cohort,side=side,factor_a=a,factor_b=b,trades_a=len(aa),trades_b=len(bb),trades_both=len(shared),
                                first_event_same_time=sum(aa[k]==bb[k] for k in shared)))
    table(overlap,read(ACCEL/'first_event_overlap.csv'),['cohort','side','factor_a','factor_b'],'factor_overlap')
    cov=pd.DataFrame(coverage).groupby(['cohort','case_id','metric'],as_index=False)[['days','trades_with_state','total_trades']].sum()
    table(cov,read(ACCEL/'state_coverage_summary.csv'),['cohort','case_id','metric'],'state_coverage_summary')
    es=pd.DataFrame(early).groupby(['cohort','case_id'],as_index=False).sum(numeric_only=True)
    table(es,read(ACCEL/'early_winner_summary.csv'),['cohort','case_id'],'early_winner_summary')
    return dict(events=len(single),event_horizons=len(ev),reconstructed_complete_held_day_states=state_count,
        censored_horizon_rows=int((~ev.complete).sum()),terminal_final_day_without_saved_state=terminal_days_excluded,
        first_event_only=True,all_future_hour_timestamps_checked=True,net_profit_qualification_recomputed=True,
        no_forward_state_inputs=True,future_extrema_are_diagnostics_not_executable_profits=True,
        actual_baseline_funding_and_carry_exact_zero=True,
        final_day_scope='Only engine-observed complete held days before account end; terminal settlement day has no saved state and is not an event opportunity.',
        comparison_warning='Factors have different event dates and trade subsets; future medians do not identify a causal factor advantage.')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--section',choices=['all','analysis','acceleration'],default='all')
    ap.add_argument('--output',type=Path,default=ROUND/'audit_analysis_current_and_acceleration.json');args=ap.parse_args()
    assert not args.output.exists(),'Preserve previous audit reports'
    begin=time.monotonic();report={'status':'RUNNING','simulator_called':False,'producer_functions_imported':False}
    try:
        for directory in [CURRENT,ANALYSIS]:bind(directory)
        scope=read(CURRENT/'scope.csv')
        if args.section in ['all','analysis']:report['analysis']=audit_analysis(scope)
        if args.section in ['all','acceleration']:
            bind(ACCEL);bind(MARKET);report['acceleration']=audit_acceleration(scope)
        report['status']='PASS'
    except BaseException as exc:
        report.update(status='FAIL',error=repr(exc));raise
    finally:
        report.update(audit_script_sha256=sha(Path(__file__)),source_bindings=BOUND,checks=dict(CHECKS),elapsed_seconds=time.monotonic()-begin,
                      funding_window_verified=False,pit_universe_proven=False)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
