"""Read retained ledgers; independently rebuild the newly highest-return observation."""
from pathlib import Path
import json, hashlib, math, re
import numpy as np
import pandas as pd
import audit_common as inputs

ROOT=Path(__file__).resolve().parents[4];FAMILY=Path(__file__).resolve().parents[1];OUT=FAMILY/'artifacts/repository_ranking_20260911'
TOL=1e-10
def same(a,b):return abs(float(a)-float(b))<TOL
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    rows=json.loads((OUT/'results.json').read_text());original=json.loads((FAMILY/'artifacts/all_results.json').read_text());checks=[];issues=[]
    for r in rows:
        p=Path(r['equity_path']);p=p if p.is_absolute() else ROOT/p
        curve=pd.read_csv(p);col=next(c for c in ['equity','net_equity','equity_net','post_action_equity'] if c in curve)
        eq=curve[col].to_numpy(float);flags={'ending_equity_matches':same(eq[-1]-1,r['return_value']),'source_hash_matches':sha(ROOT/r['source'])==r['source_sha256'],'finite_return_drawdown':math.isfinite(r['return_value']) and math.isfinite(r['drawdown']) and r['drawdown']>=0,'ratio_correct':r['return_drawdown_ratio'] is None if r['drawdown']==0 else same(r['return_drawdown_ratio'],r['return_value']/r['drawdown'])}
        if r['id'].startswith('legacy_') and r['id']!='legacy_22':
            old=original[r['original_result_index']];flags['unchanged_old_result']=same(r['return_value'],old['return']) and same(r['drawdown'],abs(old['drawdown'])) and r['trades']==old['trades']
        if not r['id'].startswith('legacy_'):
            native=json.loads((ROOT/r['source']).read_text());flags['native_summary_matches']=all(same(r[k],native[k]) for k in ['return_value','drawdown','trades'])
            t=pd.read_csv(p.with_name('trades.csv'))
            if 'position' in t and 'entry_ts' not in t:
                signs=np.sign(t.position.to_numpy());n=int(((signs!=0)&(signs!=np.r_[0,signs[:-1]])).sum())
            else:n=len(t)
            flags['count_matches_declared_unit']=n==r['trades']
            if 'entry_ts' in t:
                entry=pd.to_datetime(t.entry_ts,utc=True,format="ISO8601");exit_=pd.to_datetime(t.exit_ts,utc=True,format="ISO8601")
                flags['entries_after_start']=bool(entry.ge(pd.Timestamp(r['start'])).all());flags['exits_not_after_end']=bool(exit_.le(pd.Timestamp(r['end'])).all())
            if 'net_pnl' in t:flags['cash_pnl_matches']=same(t.net_pnl.sum(),r['return_value'])
            if 'exit_equity' in t and len(t):flags['last_trade_cash_matches']=same(t.exit_equity.iloc[-1]-1,r['return_value'])
            if r['id']=='rs4_v1':
                legs=pd.read_csv(p.with_name('legs.csv'));daily=legs.groupby('ts',sort=True)['return'].sum()
                flags['combined_legs_account_matches']=same(np.prod(1+daily)-1,r['return_value'])
            close_dd=-float((np.r_[1.,eq]/np.maximum.accumulate(np.r_[1.,eq])-1).min())
            flags['reported_dd_not_shallower_than_saved_curve']=r['drawdown']+TOL>=close_dd
            exact={'abt_v71','bksb_1d','bksb_4h','btc_cta_0.00','btc_cta_0.10','mhef_daily_0.00','mhef_daily_0.10','rs4_v1','hto_v3'}
            if r['id'] in exact:flags['drawdown_recomputed']=same(close_dd,r['drawdown'])
        checks.append({'id':r['id'],'checks':flags})
        issues.extend([r['id']+':'+k for k,v in flags.items() if not v])
    byid={r['id']:r for r in rows}
    for file,subset in [('rankings.json',rows),('registered_rankings.json',[r for r in rows if r['registered']])]:
        ranks=json.loads((OUT/file).read_text());positive=[r for r in subset if r['return_value']>0]
        expected={'高收益':sorted(subset,key=lambda r:(-r['return_value'],r['drawdown'],r['id'])),'盈利且低回撤':sorted(positive,key=lambda r:(r['drawdown'],-r['return_value'],r['id'])),'收益回撤比':sorted([r for r in positive if r['drawdown']>0],key=lambda r:(-r['return_value']/r['drawdown'],-r['return_value'],r['id']))}
        for name,values in expected.items():
            if ranks[name]!=[r['id'] for r in values]:issues.append(file+':'+name)
    # Separate algebraic account replay; never calls the strategy simulator.
    r=byid['four_rsi_v2'];trades=pd.read_csv(ROOT/r['source'].replace('summary.json','trades.csv'))
    hourly=inputs.load_prices(tf='1h').set_index('ts');fund=inputs.load_funding();fund['hour']=fund.ts.dt.floor('h');rates=fund.groupby('hour').funding_rate.sum()
    equity=peak=1.;mdd=0.;audit=[];cost=.0014
    for t in trades.itertuples():
        start=pd.Timestamp(t.entry_ts);end=pd.Timestamp(t.exit_ts);entry=float(t.entry_price);exit_=float(t.exit_price);direction=1 if t.side=='long' else -1;before=equity
        assert same(hourly.loc[start,'open'],entry) and same(hourly.loc[end,'open'],exit_)
        equity=before/(1+cost);qty=direction*equity/entry;mark=entry
        mdd=min(mdd,equity/peak-1)
        for ts,h in hourly.loc[(hourly.index>=start)&(hourly.index<end)].iterrows():
            equity+=qty*(float(h.open)-mark);mark=float(h.open)
            equity-=qty*float(h.open)*float(rates.get(ts,0))
            high=equity+qty*(float(h.high)-mark);low=equity+qty*(float(h.low)-mark)
            peak=max(peak,high,low);mdd=min(mdd,min(high,low)/peak-1)
            equity+=qty*(float(h.close)-mark);mark=float(h.close)
        equity+=qty*(exit_-mark);peak=max(peak,equity);equity-=abs(qty)*exit_*cost;mdd=min(mdd,equity/peak-1)
        audit.append({'entry':str(start),'exit':str(end),'net_return':equity/before-1,'native_net_return':float(t.net_return),'matches':same(equity/before-1,t.net_return)})
    independent={'method':'Independent fixed-quantity cash algebra, hourly conservative high/low drawdown, original hourly funding-price approximation; absent funding events remain a stated source gap.','return':equity-1,'max_drawdown':-mdd,'trades':audit,'return_matches':same(equity-1,r['return_value']),'drawdown_matches':same(-mdd,r['drawdown'])}
    if not independent['return_matches'] or not independent['drawdown_matches'] or not all(t['matches'] for t in audit):issues.append('four_hour_rsi_independent_cash_replay')
    # Independently rebuild the higher-return ETH pyramiding account from daily
    # quantities, observed funding, marks and transaction cash flows.
    r=byid['pyr_transfer_ETH'];directory=(ROOT/r['source']).parent
    curve=pd.read_csv(directory/'native_equity_before_terminal_settlement.csv')
    prices=inputs.load_prices('ETH','1h').set_index('ts');fund=inputs.load_funding('ETH')
    days=prices.resample('1D').agg(open=('open','first'),high=('high','max'),low=('low','min'))
    eq=peak=1.;dd=0.;qty=0.;last=None;cash_rows=[]
    for row in curve.itertuples():
        ts=pd.Timestamp(row.ts);price=float(prices.loc[ts,'open'])
        if last is not None:
            eq+=qty*(price-float(prices.loc[last,'open']))
            eq-=qty*price*float(fund.loc[fund.ts.gt(last)&fund.ts.le(ts),'funding_rate'].sum())
        # This retained winning run has only open executions; no intraday stop
        # would be accepted here without extending the separate reconstruction.
        assert row.action in ['entry','add','exit','hold']
        next_qty=float(row.position_qty);eq-=abs(next_qty-qty)*price*.0014;qty=next_qty
        peak=max(peak,eq);dd=min(dd,eq/peak-1)
        if ts<pd.Timestamp(r['end']) and qty:
            favorable=eq+qty*(float(days.loc[ts,'high'])-price)
            adverse=eq+qty*(float(days.loc[ts,'low'])-price)
            peak=max(peak,favorable);dd=min(dd,adverse/peak-1)
        cash_rows.append({'ts':str(ts),'cash_matches':same(eq,row.equity),'dd_matches':same(dd,row.max_drawdown_conservative)})
        last=ts
    eq-=abs(qty)*price*.0014;peak=max(peak,eq);dd=min(dd,eq/peak-1)
    highest={'id':r['id'],'method':'Independent daily fixed-quantity cash algebra with original next-open funding aggregation and original favorable-before-adverse daily drawdown; no strategy simulator used.','return':eq-1,'max_drawdown':-dd,'return_matches':same(eq-1,r['return_value']),'drawdown_matches':same(-dd,r['drawdown']),'daily_checks':cash_rows}
    if not highest['return_matches'] or not highest['drawdown_matches'] or not all(t['cash_matches'] and t['dd_matches'] for t in cash_rows):issues.append('pyramiding_independent_cash_replay')
    catalog=json.loads((OUT/'coverage.json').read_text());pub=json.loads((OUT/'public100_coverage.json').read_text())
    assert len(catalog)==143 and len(pub)==100 and len({r['id'] for r in pub})==100
    assert {r['family_path'] for r in rows}=={r['family_path'] for r in catalog if r['coverage_status']=='RANKED'}
    assert json.loads((OUT/'summary.json').read_text())['full_repository_backtesting_complete'] is False
    links=[]
    for name in ['repository-ranking-20260911.md','repository-coverage-20260911.md']:
        p=FAMILY/'diagnostics'/name
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
            if not target.startswith(('http','mailto:','#')):
                path=(p.parent/target.split('#')[0]).resolve();links.append(str(path));
                if not path.exists():issues.append('missing_link:'+str(path))
    payload={'checks_pass':not issues,'scope':'Saved-result correspondence, ranking arithmetic, coverage inclusion, linked evidence and independent cash/drawdown reconstruction of ETH pyramiding and HYPE 4h RSI observations. Not a full audit of every original strategy, input identity, funding completeness or live execution.','scenarios':len(rows),'result_checks':checks,'four_hour_rsi_independent':independent,'new_highest_observation_independent':highest,'local_links_checked':len(links),'issues':issues}
    (OUT/'verification.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
    print(json.dumps({k:payload[k] for k in ['checks_pass','scenarios','local_links_checked','issues']},ensure_ascii=False));print(json.dumps({k:v for k,v in independent.items() if k!='trades'},ensure_ascii=False))
    if issues:raise SystemExit(1)

if __name__=='__main__':run()
