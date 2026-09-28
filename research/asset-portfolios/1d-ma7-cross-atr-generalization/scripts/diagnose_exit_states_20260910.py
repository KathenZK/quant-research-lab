"""Saved V3 cash-ledger and causally available state diagnostics; no replay engine."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

BASE=Path(__file__).resolve().parents[1]
SOURCE=BASE/'artifacts/results_20260909'
OUT=BASE/'artifacts/state_machine_20260910/diagnostics_work'
ENGINE=BASE.parents[1]/'_shared-kernels/ma7-cross-atr-ratchet/v1/engine.py'
MANIFEST_SHA='880d7201b4c23695265d80d2704e0ec03245dfdb8a274b50873f82fbfb50a13d'
ENGINE_SHA='54f559748b557c81ec21ca53e4f30e09264547e5d0e8cb658716e33cf2f8d72b'
COHORTS=['main_full','partial','short']
MARKET_SOURCE=SOURCE
MARKET_MANIFEST_SHA=MANIFEST_SHA
CASE_ID='H4_D0'
FEE=.0005
SLIP=.0003
RUN_LABEL='legacy_v3_old_costs'
EXPECTED_ACCOUNTS=611
EXPECTED_CANDIDATES=652
EXPECTED_TRADES=None
EXPECTED_TERMINAL=None
DEFINITION_CONTRACT=BASE/'specs/contract-exit-state-diagnostics-20260910.md'
DEFINITION_SHA='c59e7823a520d99839fe2c07eebed96e52e43ebe8655660a77778a71c6ceb799'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    if isinstance(x,np.bool_):return bool(x)
    if isinstance(x,np.integer):return int(x)
    if isinstance(x,(float,np.floating)):return float(x) if np.isfinite(x) else None
    return x

def write_json(path,value):path.write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def freeze(directory):write_json(directory/'artifact_checksums.json',{str(p.relative_to(directory)):sha(p) for p in sorted(directory.rglob('*')) if p.is_file() and p!=directory/'artifact_checksums.json'})


class Saved:
    def __init__(self,directory=None,manifest_sha=None):
        self.directory=SOURCE if directory is None else directory
        self.manifest_sha=MANIFEST_SHA if manifest_sha is None else manifest_sha
        assert sha(self.directory/'artifact_checksums.json')==self.manifest_sha
        assert sha(ENGINE)==ENGINE_SHA
        self.hashes=json.loads((self.directory/'artifact_checksums.json').read_text());self.checked={}
    def path(self,name):
        assert name in self.hashes,name
        if name not in self.checked:
            actual=sha(self.directory/name);assert actual==self.hashes[name],name;self.checked[name]=actual
        return self.directory/name
    def csv(self,name):
        try:return pd.read_csv(self.path(name))
        except pd.errors.EmptyDataError:return pd.DataFrame()
    def obj(self,name):return json.loads(self.path(name).read_text())
    def manifest(self):return {'result_directory':str(self.directory),'result_manifest_sha256':self.manifest_sha,'engine_sha256':ENGINE_SHA,'consumed_file_hashes':self.checked}


def cash_stats(t):
    n=len(t);net=t.net_pnl if n else pd.Series(dtype=float);win=net[net>0];loss=-net[net<0]
    positive=float(win.sum());negative=float(loss.sum());avgwin=float(win.mean()) if len(win) else None;avgloss=float(loss.mean()) if len(loss) else None
    expectancy=float(net.mean()) if n else None
    if n:
        reconstructed=(len(win)/n*(avgwin or 0))-(len(loss)/n*(avgloss or 0))
        assert np.isclose(expectancy,reconstructed,atol=1e-7,rtol=1e-12)
    return dict(trades=n,wins=len(win),losses=len(loss),flat_trades=int((net==0).sum()),
       win_rate_pct=float(len(win)/n*100) if n else None,average_win_cash=avgwin,average_loss_cash=avgloss,
       payoff_ratio=avgwin/avgloss if avgwin is not None and avgloss is not None and avgloss>0 else None,
       payoff_ratio_status='DEFINED' if avgwin is not None and avgloss is not None else 'NO_WINNERS' if not len(win) else 'NO_LOSERS',
       expectancy_cash=expectancy,profit_factor=positive/negative if negative>0 else None,
       profit_factor_status='DEFINED' if negative>0 else 'NO_TRADES' if not n else 'NO_LOSSES',
       positive_cash=positive,negative_cash=negative,net_cash=float(net.sum()),
       gross_cash=float(t.gross_pnl.sum()) if n else 0.,entry_fees_cash=float(t.entry_fee.sum()) if n else 0.,
       exit_fees_cash=float(t.exit_fee.sum()) if n else 0.,recorded_funding_cash=float(t.funding_paid.sum()) if n else 0.,
       carry_cash=float(t.carry_paid.sum()) if n else 0.)


def select_exit(t,bucket):
    return t if bucket=='all' else t[t.terminal_exit] if bucket=='sample_end' else t[~t.terminal_exit]


def basic_cash():
    target=OUT/'basic_cash';assert not target.exists(),'Preserve prior cash diagnostics'
    src=Saved()
    if 'completion.json' in src.hashes:
        completion=src.obj('completion.json');assert completion['complete'] and completion['coins_completed']==EXPECTED_ACCOUNTS and not completion['coins_failed']
    else:
        completion=json.loads((SOURCE/'completion.json').read_text());assert completion['complete'] and completion['coins']==EXPECTED_ACCOUNTS
        assert completion['manifest_sha256']==MANIFEST_SHA and src.obj('execution_failures.json')==[]
        src.checked['completion.json_external_binding']=sha(SOURCE/'completion.json')
    scope=src.csv('scope.csv');summary=src.csv('summary.csv').query("case_id==@CASE_ID and window=='full'").set_index('symbol')
    assert len(scope)==EXPECTED_CANDIDATES and len(summary)==EXPECTED_ACCOUNTS
    assert np.allclose(summary.fee,FEE,atol=0,rtol=0) and np.allclose(summary.slip,SLIP,atol=0,rtol=0)
    frames=[];accounts=[]
    for r in scope[scope.cohort.ne('excluded')].itertuples():
        t=src.csv(f'runs/{r.slug}/{CASE_ID}/full/trades.csv');a=summary.loc[r.symbol]
        assert len(t)==int(a.trades)
        net=float(t.net_pnl.sum()) if len(t) else 0.
        assert np.isclose(10000+net,a.ending_equity,atol=1e-6,rtol=0)
        if len(t):
            assert not t.trade_id.duplicated().any()
            assert np.allclose(t.side*t.qty*(t.exit_price-t.entry_price),t.gross_pnl,atol=1e-6,rtol=1e-12)
            assert np.allclose(t.gross_pnl-t.entry_fee-t.exit_fee-t.funding_paid-t.carry_paid,t.net_pnl,atol=1e-6,rtol=1e-12)
            assert np.allclose(t.end_equity-t.entry_equity,t.net_pnl,atol=1e-6,rtol=1e-12)
            assert np.allclose(t.entry_equity,np.r_[10000,t.end_equity.to_numpy()[:-1]],atol=1e-6,rtol=0)
            assert set(t.exit_reason)<= {'stop_gap','stop_intrahour','accel1_rsi30','sample_end'}
            assert t.funding_paid.eq(0).all() and t.carry_paid.eq(0).all(), 'Expected original price-only baseline'
            t=t.assign(symbol=r.symbol,slug=r.slug,cohort=r.cohort,terminal_exit=t.exit_reason.eq('sample_end'),
                       data_boundary_end=bool(r.boundary_end_due_to_data),source_case_id=CASE_ID,
                       actual_fee_cash=t.entry_fee+t.exit_fee,net_outcome=np.where(t.net_pnl>0,'win',np.where(t.net_pnl<0,'loss','flat')))
            frames.append(t)
        accounts.append(dict(symbol=r.symbol,slug=r.slug,cohort=r.cohort,trade_days=int(r.trade_days),trades=len(t),
          ending_equity=float(a.ending_equity),net_cash=net,return_pct=float(a.return_pct),max_drawdown_pct=float(a.max_drawdown_pct),
          data_boundary_end=bool(r.boundary_end_due_to_data),zero_trades=not len(t),account_reconciled=True))
    trades=pd.concat(frames,ignore_index=True);assert len(trades)==int(summary.trades.sum())
    if EXPECTED_TRADES is not None:assert len(trades)==EXPECTED_TRADES
    if EXPECTED_TERMINAL is not None:assert int(trades.terminal_exit.sum())==EXPECTED_TERMINAL
    assert not trades.duplicated(['symbol','trade_id']).any()
    pooled=[];coin=[]
    for cohort in ['all_cohorts']+COHORTS:
        g=trades if cohort=='all_cohorts' else trades[trades.cohort.eq(cohort)]
        for side in ['all','long','short']:
            p=g if side=='all' else g[g.side.eq(1 if side=='long' else -1)]
            for bucket in ['all','nonterminal','sample_end']:
                v=select_exit(p,bucket);pooled.append(dict(run_label=RUN_LABEL,fee_rate=FEE,slippage_rate=SLIP,cohort=cohort,side_group=side,exit_bucket=bucket,coins_with_trades=v.symbol.nunique(),**cash_stats(v)))
    for a in accounts:
        g=trades[trades.symbol.eq(a['symbol'])]
        for side in ['all','long','short']:
            p=g if side=='all' else g[g.side.eq(1 if side=='long' else -1)]
            for bucket in ['all','nonterminal','sample_end']:
                coin.append(dict(run_label=RUN_LABEL,fee_rate=FEE,slippage_rate=SLIP,symbol=a['symbol'],slug=a['slug'],cohort=a['cohort'],side_group=side,exit_bucket=bucket,**cash_stats(select_exit(p,bucket))))
    coin_df=pd.DataFrame(coin);medians=[]
    for (cohort,side,bucket),g in coin_df.groupby(['cohort','side_group','exit_bucket']):
        r=dict(cohort=cohort,side_group=side,exit_bucket=bucket,coins_total=len(g),coins_with_trades=int(g.trades.gt(0).sum()),coins_without_trades=int(g.trades.eq(0).sum()))
        for key in ['win_rate_pct','average_win_cash','average_loss_cash','payoff_ratio','expectancy_cash','profit_factor']:
            r[key+'_coin_median']=float(g[key].median()) if g[key].notna().any() else None
            r[key+'_defined_coins']=int(g[key].notna().sum())
        medians.append(r)
    target.mkdir(parents=True);trades.to_csv(target/'all_v3_trades.csv',index=False);pd.DataFrame(accounts).to_csv(target/'account_reconciliation.csv',index=False)
    pd.DataFrame(pooled).to_csv(target/'cash_by_cohort_side_exit.csv',index=False);coin_df.to_csv(target/'cash_by_coin_side_exit.csv',index=False);pd.DataFrame(medians).to_csv(target/'coin_median_cash_metrics.csv',index=False)
    scope.to_csv(target/'scope.csv',index=False)
    write_json(target/'summary.json',dict(run_label=RUN_LABEL,source_case_id=CASE_ID,fee_rate=FEE,slippage_rate=SLIP,accounts=len(accounts),scope_candidates=len(scope),trades=len(trades),nonterminal_exits=int((~trades.terminal_exit).sum()),sample_end_exits=int(trades.terminal_exit.sum()),
      cohorts=scope.cohort.value_counts().to_dict(),trade_cash_statistics=pooled,coin_medians=medians,
      notes=['All cash statistics use saved qty, actual entry/exit fills and actual saved net_pnl; no trade-return proxy.',
             'Pooled cross-coin cash statistics are descriptive and weight trades by actual changing account amounts. They are not a funded portfolio or independent market-event sample.',
             'Per-coin cash metrics and coin-median summaries are supplied separately; differing entry account equity still affects cash sizes.',
             'Sample-end settlements are separated from strategy-triggered exits and are not forced-liquidation events.',
             'Recorded funding is zero because the original baseline did not include verified actual funding. This is not a claim that actual perpetual funding was zero.']))
    shutil.copy2(Path(__file__),target/'source_script_at_basic_run.py.txt')
    write_json(target/'source_manifest.json',dict(run_label=RUN_LABEL,source_case_id=CASE_ID,fee_rate=FEE,slippage_rate=SLIP,source=src.manifest(),script_snapshot='source_script_at_basic_run.py.txt',script_sha256=sha(Path(__file__)),simulation_performed=False))
    freeze(target)
    print(pd.DataFrame(pooled).query("cohort!='all_cohorts' and side_group!='all' and exit_bucket=='nonterminal'")[['cohort','side_group','trades','win_rate_pct','average_win_cash','average_loss_cash','payoff_ratio','expectancy_cash','profit_factor']].to_string(index=False))

def divide(n,d):return float(n/d) if np.isfinite(n) and np.isfinite(d) and d>0 else np.nan

def bin_value(v,edges,labels):
    if pd.isna(v):return 'MISSING'
    return labels[int(np.searchsorted(edges,float(v),side='right'))]


def net_liquidation_at_price(t,price,fee=None,slip=None):
    fee=FEE if fee is None else fee;slip=SLIP if slip is None else slip
    fill=price*(1-int(t['side'])*slip)
    return int(t['side'])*t['qty']*(fill-t['entry_price'])-t['entry_fee']-t['qty']*fill*fee-t['funding_paid']-t['carry_paid']


def pre_cross_features(t,d,i):
    p=i-1;side=int(t['side']);r={'pre_features_end_day':d.timestamp.iloc[p].isoformat() if p>=0 else None}
    atrprev=float(d.atr.iloc[p]) if p>=0 else np.nan
    for n in [5,10,20]:
        r[f'pre_directional_displacement_{n}_atr']=divide(side*(float(d.close.iloc[p])-float(d.close.iloc[p-n])),atrprev) if p>=n else np.nan
    if p>=20:
        window=d.iloc[p-19:p+1]
        delta=d.close.diff().iloc[p-19:p+1]
        r['pre_range20_atr']=divide(float(window.high.max()-window.low.min()),atrprev)
        r['pre_efficiency20']=divide(abs(float(d.close.iloc[p]-d.close.iloc[p-20])),float(delta.abs().sum()))
        tr=d.true_range.iloc[p-19:p+1]
        r['pre_volatility_ratio5_20']=divide(float(tr.iloc[-5:].mean()),float(tr.mean()))
        r['pre_ma7_cross_count20']=int(window.cross.ne(0).sum())
    else:
        for k in ['pre_range20_atr','pre_efficiency20','pre_volatility_ratio5_20','pre_ma7_cross_count20']:r[k]=np.nan
    row=d.iloc[i]
    r.update(cross_day_directional_move_atrprev=divide(side*(row.close-d.close.iloc[p]),atrprev) if p>=0 else np.nan,
             cross_day_ma_offset_atr=divide(side*(row.close-row.ma),row.atr),cross_day_rsi6=float(row.rsi),
             pre_displacement20_bin=bin_value(r['pre_directional_displacement_20_atr'],[-3,-1,1,3],['lt_-3','[-3,-1)','[-1,1)','[1,3)','ge_3']),
             pre_efficiency20_bin=bin_value(r['pre_efficiency20'],[.25,.5],['lt_0.25','[0.25,0.5)','ge_0.5']),
             pre_volatility_ratio_bin=bin_value(r['pre_volatility_ratio5_20'],[.75,1.25],['lt_0.75','[0.75,1.25)','ge_1.25']))
    r['pre_features_missing']=bool(any(pd.isna(r[k]) for k in ['pre_directional_displacement_20_atr','pre_range20_atr','pre_efficiency20','pre_volatility_ratio5_20']))
    return r


def hourly_excursions(t,h):
    side=int(t['side']);entry=pd.Timestamp(t['entry_time']);end=pd.Timestamp(t['exit_time']);interval_end=pd.Timestamp(t['exit_interval_end'])
    assert entry==entry.floor('h') and end==end.floor('h')
    a=int(h.timestamp.searchsorted(entry));b=int(h.timestamp.searchsorted(end));full=h.iloc[a:b]
    if len(full):assert full.timestamp.iloc[0]>=entry and full.timestamp.iloc[-1]+pd.Timedelta(hours=1)<=end
    assert len(full)==int((end-entry)/pd.Timedelta(hours=1))
    favorable=[float(t['entry_reference']),float(t['exit_reference'])]
    adverse=list(favorable)
    if len(full):
        favorable.append(float(full.high.max()) if side==1 else float(full.low.min()))
        adverse.append(float(full.low.min()) if side==1 else float(full.high.max()))
    best=max(favorable) if side==1 else min(favorable);worst=min(adverse) if side==1 else max(adverse)
    best_upper=best;worst_upper=worst;ambiguous=t['exit_reason']=='stop_intrahour'
    if ambiguous:
        bar=h.iloc[b];assert bar.timestamp==end and interval_end==end+pd.Timedelta(hours=1)
        other_best=float(bar.high) if side==1 else float(bar.low);other_worst=float(bar.low) if side==1 else float(bar.high)
        best_upper=max(best,other_best) if side==1 else min(best,other_best)
        worst_upper=min(worst,other_worst) if side==1 else max(worst,other_worst)
    else:assert interval_end==end
    r=dict(fully_held_hours_before_exit=len(full),exit_hour_order_unknown=ambiguous,
      favorable_price_confirmed=best,favorable_price_possible=best_upper,adverse_price_confirmed=worst,adverse_price_possible=worst_upper,
      mfe_atr_lower=max(0.,divide(side*(best-t['entry_price']),t['entry_atr'])),
      mfe_atr_upper=max(0.,divide(side*(best_upper-t['entry_price']),t['entry_atr'])),
      mae_atr_lower=max(0.,divide(-side*(worst-t['entry_price']),t['entry_atr'])),
      mae_atr_upper=max(0.,divide(-side*(worst_upper-t['entry_price']),t['entry_atr'])))
    assert r['mfe_atr_lower']<=r['mfe_atr_upper']+1e-10 and r['mae_atr_lower']<=r['mae_atr_upper']+1e-10
    assert np.isclose(net_liquidation_at_price(t,t['exit_reference']),t['net_pnl'],atol=1e-6,rtol=1e-12)
    peak_lower=max(0.,net_liquidation_at_price(t,best),t['net_pnl']);peak_upper=max(peak_lower,net_liquidation_at_price(t,best_upper))
    r.update(peak_net_profit_cash_lower=peak_lower,peak_net_profit_cash_upper=peak_upper,
       profit_given_back_cash_lower=max(0.,peak_lower-max(t['net_pnl'],0.)),profit_given_back_cash_upper=max(0.,peak_upper-max(t['net_pnl'],0.)),
       peak_to_exit_cash_lower=peak_lower-t['net_pnl'],peak_to_exit_cash_upper=peak_upper-t['net_pnl'],
       profit_given_back_fraction_lower=divide(max(0.,peak_lower-max(t['net_pnl'],0.)),peak_lower),
       profit_given_back_fraction_upper=divide(max(0.,peak_upper-max(t['net_pnl'],0.)),peak_upper))
    for threshold in [1,2]:
        r[f'mfe_{threshold}atr_status']='confirmed_reached' if r['mfe_atr_lower']>=threshold else 'confirmed_below' if r['mfe_atr_upper']<threshold else 'exit_hour_ambiguous'
    return r


def build_day_states(t,d,index,st):
    fhd=st[st.full_holding_day].sort_values('timestamp');assert not fhd.signal_day.duplicated().any()
    rows=[];extreme=None;entry=pd.Timestamp(t['entry_time']);side=int(t['side'])
    for n,stop in enumerate(fhd.to_dict('records'),start=1):
        signal=pd.Timestamp(stop['signal_day']);available=pd.Timestamp(stop['timestamp']);i=index[signal];bar=d.iloc[i]
        assert signal>=entry and available==signal+pd.Timedelta(days=1) and available<=pd.Timestamp(t['exit_time'])
        price=float(bar.high) if side==1 else float(bar.low)
        extreme=price if extreme is None else max(extreme,price) if side==1 else min(extreme,price)
        assert np.isclose(extreme,stop['extreme_price'],atol=1e-8,rtol=1e-12)
        er3=np.nan;er_start=None;preentry=False;er_missing='FEWER_THAN_THREE_COMPLETE_HELD_DAYS'
        if n>=3 and i>=3:
            er_start=d.timestamp.iloc[i-3];den=float(d.close.diff().iloc[i-2:i+1].abs().sum())
            er3=divide(side*(bar.close-d.close.iloc[i-3]),den);preentry=er_start<entry
            er_missing='' if pd.notna(er3) else 'ZERO_OR_INVALID_THREE_DAY_PRICE_CHANGE_SUM'
        expected=net_liquidation_at_price(t,float(bar.close))
        assert np.isclose(expected,stop['expected_profit_at_close'],atol=1e-5,rtol=1e-12)
        r=dict(symbol=t['symbol'],slug=t['slug'],cohort=t['cohort'],trade_id=int(t['trade_id']),side=side,
          entry_time=t['entry_time'],exit_time=t['exit_time'],terminal_exit=bool(t['terminal_exit']),net_outcome=t['net_outcome'],net_pnl=float(t['net_pnl']),
          held_complete_day_number=n,signal_day=signal.isoformat(),state_available_at=available.isoformat(),
          close=float(bar.close),ma7=float(bar.ma),atr14=float(bar.atr),cumulative_favorable_day_extreme=extreme,
          pullback_from_favorable_extreme_atr=divide(side*(extreme-bar.close),bar.atr),
          daily_mfe_entry_atr=max(0.,divide(side*(extreme-t['entry_price']),t['entry_atr'])),
          directional_market_close_er3=er3,market_close_er3_missing_reason=er_missing,
          market_close_er3_start_day=er_start.isoformat() if er_start is not None else None,
          market_close_er3_includes_preentry_close=preentry,
          directional_speed_atrprev=divide(side*(bar.close-d.close.iloc[i-1]),d.atr.iloc[i-1]) if i else np.nan,
          directional_ma7_offset_atr=divide(side*(bar.close-bar.ma),bar.atr),net_liquidation_profit_at_close_cash=expected,
          old_stop=stop['old_stop'],new_stop=stop['new_stop'],old_mult=stop['old_mult'],new_mult=stop['new_mult'],
          old_armed=stop['old_armed'],new_armed=stop['new_armed'],new_extreme=stop['new_extreme'],
          no_new_extreme_days=stop['no_new_extreme_days'],tightening_trigger=stop['tightening_trigger'],tightened=stop['tightened'])
        rows.append(r)
    return rows


def add_cash_normalization(t):
    side=int(t['side']);stop_fill=t['initial_stop']*(1-side*SLIP)
    unit_risk=side*(t['entry_price']-stop_fill)+FEE*(t['entry_price']+stop_fill)
    planned=t['qty']*unit_risk
    return dict(actual_net_return_on_entry_equity_pct=divide(t['net_pnl']*100,t['entry_equity']),
      initial_planned_risk_cash=planned,initial_planned_risk_pct=divide(planned*100,t['entry_equity']),
      actual_net_pnl_in_initial_r=divide(t['net_pnl'],planned),initial_stop_nonpositive=bool(t['initial_stop']<=0))


def extended_cash_stats(t):
    r=cash_stats(t)
    for k in ['actual_net_return_on_entry_equity_pct','actual_net_pnl_in_initial_r']:
        r[k+'_mean']=float(t[k].mean()) if len(t) and t[k].notna().any() else None
        r[k+'_median']=float(t[k].median()) if len(t) and t[k].notna().any() else None
        r[k+'_defined_trades']=int(t[k].notna().sum()) if len(t) else 0
    return r


def summarize_feature_bins(trades):
    bins={'pre_displacement20_bin':['lt_-3','[-3,-1)','[-1,1)','[1,3)','ge_3','MISSING'],
          'pre_efficiency20_bin':['lt_0.25','[0.25,0.5)','ge_0.5','MISSING'],
          'pre_volatility_ratio_bin':['lt_0.75','[0.75,1.25)','ge_1.25','MISSING']}
    rows=[];coin_rows=[]
    for cohort in COHORTS:
        group=trades[trades.cohort.eq(cohort)]
        for side in ['all','long','short']:
            p=group if side=='all' else group[group.side.eq(1 if side=='long' else -1)]
            for bucket in ['all','nonterminal','sample_end']:
                q=select_exit(p,bucket)
                for feature,levels in bins.items():
                    for level in levels:
                        part=q[q[feature].eq(level)];row=dict(cohort=cohort,side_group=side,exit_bucket=bucket,feature=feature,bin=level,
                          total_side_exit_trades=len(q),coins_with_trades=part.symbol.nunique(),**extended_cash_stats(part))
                        coin_stats=[]
                        for symbol,v in part.groupby('symbol'):
                            c=dict(cohort=cohort,symbol=symbol,side_group=side,exit_bucket=bucket,feature=feature,bin=level,**extended_cash_stats(v));coin_rows.append(c);coin_stats.append(c)
                        for k in ['win_rate_pct','average_win_cash','average_loss_cash','payoff_ratio','expectancy_cash','profit_factor','actual_net_return_on_entry_equity_pct_mean','actual_net_pnl_in_initial_r_mean']:
                            vals=[c[k] for c in coin_stats if c[k] is not None and pd.notna(c[k])]
                            row[k+'_coin_median']=float(np.median(vals)) if vals else None;row[k+'_defined_coins']=len(vals)
                        rows.append(row)
    return rows,coin_rows


def summarize_mfe(trades):
    rows=[]
    for cohort in COHORTS:
        for side in ['all','long','short']:
            p=trades[trades.cohort.eq(cohort)]
            if side!='all':p=p[p.side.eq(1 if side=='long' else -1)]
            for bucket in ['all','nonterminal','sample_end']:
                q=select_exit(p,bucket)
                for outcome in ['all','win','loss','flat']:
                    v=q if outcome=='all' else q[q.net_outcome.eq(outcome)]
                    for threshold in [1,2]:
                        for status in ['confirmed_below','confirmed_reached','exit_hour_ambiguous']:
                            g=v[v[f'mfe_{threshold}atr_status'].eq(status)]
                            rows.append(dict(cohort=cohort,side_group=side,exit_bucket=bucket,net_outcome=outcome,threshold_atr=threshold,status=status,
                              outcome_trades_total=len(v),coins_with_trades=g.symbol.nunique(),**extended_cash_stats(g)))
    return rows


def landmark_analysis(trades,states):
    availability=[];summaries=[];features=[]
    indexed=states.set_index(['symbol','trade_id','held_complete_day_number'])
    keys=['daily_mfe_entry_atr','pullback_from_favorable_extreme_atr','directional_market_close_er3','directional_speed_atrprev','directional_ma7_offset_atr','net_liquidation_profit_at_close_cash']
    for t in trades.to_dict('records'):
        for day in [1,3]:
            when=pd.Timestamp(t['entry_time']).normalize()+pd.Timedelta(days=day);key=(t['symbol'],int(t['trade_id']),day);observed=key in indexed.index
            if observed:why='OBSERVED_FULL_HELD_DAY_STATE'
            elif t['terminal_exit'] and pd.Timestamp(t['exit_time'])<when:why='SAMPLE_END_BEFORE_LANDMARK'
            elif t['terminal_exit'] and pd.Timestamp(t['exit_time'])==when:why='SAMPLE_END_AT_LANDMARK_NO_SAVED_STATE'
            elif not t['terminal_exit'] and pd.Timestamp(t['exit_time'])<when:why='STRATEGY_EXIT_BEFORE_LANDMARK'
            else:why='NO_SAVED_COMPLETE_DAY_STATE'
            row=dict(t,landmark_day=day,landmark_expected_time=when.isoformat(),landmark_observed=observed,landmark_availability_reason=why)
            if observed:
                state=indexed.loc[key];assert not isinstance(state,pd.DataFrame)
                for k in keys:row[k]=state[k]
                row['market_close_er3_missing_reason']=state.market_close_er3_missing_reason
                row['market_close_er3_includes_preentry_close']=bool(state.market_close_er3_includes_preentry_close)
            else:
                for k in keys:row[k]=np.nan
                row['market_close_er3_missing_reason']='LANDMARK_NOT_OBSERVED';row['market_close_er3_includes_preentry_close']=False
            availability.append(row)
    av=pd.DataFrame(availability)
    for cohort in COHORTS:
        for side in ['all','long','short']:
            g=av[av.cohort.eq(cohort)]
            if side!='all':g=g[g.side.eq(1 if side=='long' else -1)]
            for bucket in ['all','nonterminal','sample_end']:
                p=select_exit(g,bucket)
                for day in [1,3]:
                    q=p[p.landmark_day.eq(day)];observed=q[q.landmark_observed]
                    reason=q.landmark_availability_reason.value_counts().to_dict()
                    summaries.append(dict(cohort=cohort,side_group=side,exit_bucket=bucket,landmark_day=day,total_original_trades=len(q),
                       strategy_exits_before_landmark=reason.get('STRATEGY_EXIT_BEFORE_LANDMARK',0),sample_end_before_landmark=reason.get('SAMPLE_END_BEFORE_LANDMARK',0),
                       sample_end_at_landmark_no_state=reason.get('SAMPLE_END_AT_LANDMARK_NO_SAVED_STATE',0),other_no_state=reason.get('NO_SAVED_COMPLETE_DAY_STATE',0),
                       **{'observed_'+k:v for k,v in extended_cash_stats(observed).items()}))
                    for outcome in ['all','win','loss','flat']:
                        v=observed if outcome=='all' else observed[observed.net_outcome.eq(outcome)]
                        r=dict(cohort=cohort,side_group=side,exit_bucket=bucket,landmark_day=day,final_net_outcome=outcome,
                          total_original_trades=len(q),observed_trades=len(observed),outcome_observed_trades=len(v))
                        for k in keys:
                            r[k+'_median']=float(v[k].median()) if v[k].notna().any() else None;r[k+'_missing_trades']=int(v[k].isna().sum())
                        features.append(r)
    return av,summaries,features


def full_states():
    contract=DEFINITION_CONTRACT
    assert sha(contract)==DEFINITION_SHA;target=OUT/'state_features';assert not target.exists(),'Preserve completed feature diagnostic'
    basic=OUT/'basic_cash'
    if not basic.exists():basic_cash()
    hashes=json.loads((basic/'artifact_checksums.json').read_text())
    for name,digest in hashes.items():assert sha(basic/name)==digest
    trades=pd.read_csv(basic/'all_v3_trades.csv');scope=pd.read_csv(basic/'scope.csv');src=Saved();prices=Saved(MARKET_SOURCE,MARKET_MANIFEST_SHA);features=[];states=[]
    assert trades.entry_atr.gt(0).all()
    assert np.allclose(trades.entry_fee,trades.qty*trades.entry_price*FEE,atol=1e-7,rtol=1e-12)
    assert np.allclose(trades.exit_fee,trades.qty*trades.exit_price*FEE,atol=1e-7,rtol=1e-12)
    assert np.allclose(trades.entry_price,trades.entry_reference*(1+trades.side*SLIP),atol=1e-9,rtol=1e-12)
    assert np.allclose(trades.exit_price,trades.exit_reference*(1-trades.side*SLIP),atol=1e-9,rtol=1e-12)
    for market in scope[scope.cohort.ne('excluded')].itertuples():
        d=prices.csv(f'market/{market.slug}/daily_features.csv');d['timestamp']=pd.to_datetime(d.timestamp,utc=True);d=d.sort_values('timestamp').reset_index(drop=True)
        assert d.timestamp.is_unique and d.is_closed.all() and d.eligible.all()
        assert d.timestamp.diff().dropna().eq(pd.Timedelta(days=1)).all()
        prev=d.close.shift(1);d['true_range']=pd.concat([d.high-d.low,(d.high-prev).abs(),(d.low-prev).abs()],axis=1).max(axis=1)
        index={x:i for i,x in enumerate(d.timestamp)}
        h=pd.read_parquet(prices.path(f'market/{market.slug}/hourly.parquet'));h['timestamp']=pd.to_datetime(h.timestamp,utc=True);h=h.sort_values('timestamp').reset_index(drop=True)
        assert h.timestamp.is_unique and h.is_closed.all() and h.eligible.all() and h.timestamp.diff().dropna().eq(pd.Timedelta(hours=1)).all()
        stops=src.csv(f'runs/{market.slug}/{CASE_ID}/full/stops.csv')
        if len(stops):
            stops['timestamp']=pd.to_datetime(stops.timestamp,utc=True);stops['signal_day']=pd.to_datetime(stops.signal_day,utc=True)
            byst={int(k):v for k,v in stops.groupby('trade_id')}
        else:byst={}
        for t in trades[trades.symbol.eq(market.symbol)].to_dict('records'):
            signal=pd.Timestamp(t['signal_day']);i=index[signal];entry=pd.Timestamp(t['entry_time']);assert entry==entry.normalize()
            assert signal<entry and entry==signal+pd.Timedelta(days=1)
            row=dict(t);row.update(pre_cross_features(t,d,i));row.update(hourly_excursions(t,h));row.update(add_cash_normalization(t))
            daily=build_day_states(t,d,index,byst[int(t['trade_id'])]);row['saved_complete_held_day_states']=len(daily)
            row['first_complete_day_observed']=len(daily)>=1;row['third_complete_day_observed']=len(daily)>=3
            features.append(row);states.extend(daily)
    features=pd.DataFrame(features);states=pd.DataFrame(states);assert len(features)==len(trades)
    assert not features.duplicated(['symbol','trade_id']).any() and not states.duplicated(['symbol','trade_id','held_complete_day_number']).any()
    bins,coin_bins=summarize_feature_bins(features);mfe=summarize_mfe(features);landmarks,landmark_summary,landmark_features=landmark_analysis(features,states)
    target.mkdir(parents=True);features.to_csv(target/'all_trade_features.csv',index=False);states.to_csv(target/'all_complete_day_states.csv',index=False)
    pd.DataFrame(bins).to_csv(target/'pre_cross_bin_cash_stats.csv',index=False);pd.DataFrame(coin_bins).to_csv(target/'pre_cross_bin_cash_by_coin.csv',index=False)
    pd.DataFrame(mfe).to_csv(target/'mfe_outcome_thresholds.csv',index=False);landmarks.to_csv(target/'all_trade_landmarks.csv',index=False)
    pd.DataFrame(landmark_summary).to_csv(target/'landmark_survival_counts.csv',index=False);pd.DataFrame(landmark_features).to_csv(target/'landmark_features_by_final_outcome.csv',index=False)
    feature_cash=[]
    for (cohort,symbol,side),g in features.groupby(['cohort','symbol','side']):
        for bucket in ['all','nonterminal','sample_end']:
            v=select_exit(g,bucket);feature_cash.append(dict(cohort=cohort,symbol=symbol,side=int(side),exit_bucket=bucket,**extended_cash_stats(v)))
    pd.DataFrame(feature_cash).to_csv(target/'cash_return_r_by_coin_side.csv',index=False)
    write_json(target/'summary.json',dict(run_label=RUN_LABEL,source_case_id=CASE_ID,fee_rate=FEE,slippage_rate=SLIP,trades=len(features),day_state_rows=len(states),landmark_rows=len(landmarks),
      pre_cross_bin_rows=len(bins),pre_cross_coin_bin_rows=len(coin_bins),mfe_threshold_rows=len(mfe),
      terminal_exits=int(features.terminal_exit.sum()),intrahour_uncertain_exit_rows=int(features.exit_hour_order_unknown.sum()),
      missing_pre_features=int(features.pre_features_missing.sum()),
      market_er3_missing_day_states=int(states.directional_market_close_er3.isna().sum()),
      market_er3_includes_preentry_close_day_states=int(states.market_close_er3_includes_preentry_close.sum()),
      definition_notes=['Pre-cross features end on signal_day minus one closed day; crossing-day fields have an independent prefix.',
       'Only fixed univariate feature bins from the precommitted diagnostic contract are summarized. Winners, losers, flat trades, and sample-end settlements are retained.',
       'Cash statistics use actual saved trade money. Per-entry-equity returns and net PnL / initial modeled stop risk are additional separate measures.',
       'MFE/MAE lower bounds use only fully held hours ending no later than exit_time plus observed entry and exit references. Upper bounds may add the unordered intrahour exit candle; no claim its favorable extreme was available before the stop.',
       'Price movements use actual entry fill and entry ATR. Hypothetical liquidation cash uses actual quantity, entry fill, entry fee and original exit cost model; actual net_pnl stays separate.',
       'Profit-given-back cash clips realized profit at zero, while peak-to-exit cash also includes loss below breakeven. These measures are explicitly separate.',
       'Daily states only use saved full_holding_day stop rows and become observable at their recorded next-day timestamp.',
       'directional_market_close_er3 uses market C-C3 over three daily changes. At the third full held day its C3 can precede entry. It is not the separately defined candidate strategy entry-reference ER3.',
       'Landmark statistics condition on surviving to an observed saved complete-day state; exits before the landmark and sample-end/no-state cases remain explicit denominators.',
       'Cross-coin observations share market regimes. No independence, significance, portfolio or complete bull/bear-cycle claim is made.']))
    shutil.copy2(Path(__file__),target/'source_script_at_state_run.py.txt')
    write_json(target/'source_manifest.json',dict(run_label=RUN_LABEL,fee_rate=FEE,slippage_rate=SLIP,trade_source=src.manifest(),market_source=prices.manifest(),contract_path=str(contract.relative_to(BASE)),contract_sha256=sha(contract),
      definition_contract_sha256=DEFINITION_SHA,basic_cash_manifest_sha256=sha(basic/'artifact_checksums.json'),
      script_snapshot='source_script_at_state_run.py.txt',script_sha256=sha(Path(__file__)),simulation_performed=False))
    freeze(target);print(json.dumps(json.loads((target/'summary.json').read_text()),ensure_ascii=False,indent=2))


def configure(args):
    global SOURCE,MARKET_SOURCE,MANIFEST_SHA,MARKET_MANIFEST_SHA,CASE_ID,FEE,SLIP,RUN_LABEL,OUT,ENGINE,ENGINE_SHA,EXPECTED_TRADES,EXPECTED_TERMINAL,EXPECTED_ACCOUNTS,EXPECTED_CANDIDATES,DEFINITION_CONTRACT,DEFINITION_SHA
    import re
    assert re.fullmatch(r'[a-zA-Z0-9_-]+',args.run_label),'Use an explicit safe output label'
    SOURCE=Path(args.source_results).resolve();MARKET_SOURCE=Path(args.market_results).resolve()
    MANIFEST_SHA=args.source_manifest_sha;MARKET_MANIFEST_SHA=args.market_manifest_sha;CASE_ID=args.case_id;FEE=args.fee;SLIP=args.slip;RUN_LABEL=args.run_label
    assert 0<=FEE<1 and 0<=SLIP<1
    ENGINE=Path(args.engine_path).resolve();ENGINE_SHA=args.engine_sha
    EXPECTED_TRADES=args.expected_trades;EXPECTED_TERMINAL=args.expected_terminal;EXPECTED_ACCOUNTS=args.expected_accounts;EXPECTED_CANDIDATES=args.expected_candidates
    DEFINITION_CONTRACT=Path(args.definition_contract).resolve();DEFINITION_SHA=args.definition_sha
    OUT=Path(args.output_base).resolve()/RUN_LABEL
    OUT.mkdir(parents=True,exist_ok=True)
    context=dict(run_label=RUN_LABEL,source_results=str(SOURCE),source_manifest_sha256=MANIFEST_SHA,market_results=str(MARKET_SOURCE),market_manifest_sha256=MARKET_MANIFEST_SHA,
      case_id=CASE_ID,fee_rate=FEE,slippage_rate=SLIP,engine_path=str(ENGINE),engine_sha256=ENGINE_SHA,definition_contract=str(DEFINITION_CONTRACT),definition_sha256=DEFINITION_SHA,
      actual_funding_verified=False,output_label_required=True,diagnosis_only_no_strategy_replay=True)
    context_path=OUT/'run_context.json'
    if context_path.exists():assert json.loads(context_path.read_text())==context,'Do not change an existing diagnostic source/cost context'
    else:write_json(context_path,context)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--basic-only',action='store_true')
    parser.add_argument('--run-label',required=True);parser.add_argument('--source-results',required=True);parser.add_argument('--source-manifest-sha',required=True)
    parser.add_argument('--market-results',required=True);parser.add_argument('--market-manifest-sha',required=True);parser.add_argument('--case-id',required=True)
    parser.add_argument('--fee',type=float,required=True);parser.add_argument('--slip',type=float,required=True);parser.add_argument('--engine-path',required=True);parser.add_argument('--engine-sha',required=True)
    parser.add_argument('--output-base',default=str(BASE/'artifacts/state_machine_20260910/diagnostics_work'))
    parser.add_argument('--definition-contract',default=str(BASE/'specs/contract-exit-state-diagnostics-20260910.md'));parser.add_argument('--definition-sha',default='c59e7823a520d99839fe2c07eebed96e52e43ebe8655660a77778a71c6ceb799')
    parser.add_argument('--expected-accounts',type=int,default=611);parser.add_argument('--expected-candidates',type=int,default=652)
    parser.add_argument('--expected-trades',type=int);parser.add_argument('--expected-terminal',type=int)
    args=parser.parse_args();configure(args)
    if args.basic_only:basic_cash()
    else:full_states()
