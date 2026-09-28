"""Reconcile presentation to audited blocks; recompute paired gains and lost winners."""
import json
from pathlib import Path
import pandas as pd
import numpy as np
from ma30_study_20260911 import ROOT,BASE,R,OLD,sha,write_json,verify_manifest

def close(a,b):
    if pd.isna(b):assert pd.isna(a)
    else:assert np.isclose(a,b,rtol=2e-10,atol=1e-12),(a,b)

def main():
    out=R/'summary_audit';out.mkdir(exist_ok=False)
    verify_manifest(R/'analysis/artifact_checksums.json');verify_manifest(R/'pairs/artifact_checksums.json')
    p=pd.read_csv(R/'analysis/period_accounts.csv');s=pd.read_csv(R/'analysis/period_summary.csv')
    blocks=pd.concat([pd.read_csv(R/'results/blocks.csv'),pd.read_csv(OLD/'results/blocks.csv').query('case_id == "U_READY"')],ignore_index=True)
    blocks=blocks[blocks.status.ne('NO_OVERLAP')];keys=['run_key','case_id','block']
    merged=p.merge(blocks,on=keys,suffixes=('_shown','_source'),validate='one_to_one');assert len(merged)==len(p)==len(blocks)
    for col in ['return_pct','max_drawdown_pct','days','start_equity','end_equity']:
        assert np.allclose(merged[col+'_shown'],merged[col+'_source'],equal_nan=True,rtol=2e-10,atol=1e-12),col
    for col in ['status','complete_coverage','actual_start','actual_end']:assert merged[col+'_shown'].equals(merged[col+'_source']),col
    u=p[p.case_id.eq('U_READY')].set_index(['run_key','block'])
    for row in p.itertuples(index=False):
        base=u.loc[(row.run_key,row.block)];close(row.return_change_pp,row.return_pct-base.return_pct)
        close(row.drawdown_reduction_pp,abs(base.max_drawdown_pct)-abs(row.max_drawdown_pct))
    for row in s.itertuples(index=False):
        g=p[p.block.eq(row.block)&p.status.eq(row.status)&p.case_id.eq(row.case_id)]
        assert row.segments==len(g) and row.coins==g.slug.nunique()
        for field,expected in [('profitable_segments',g.outcome.eq('PROFIT').sum()),('losing_segments',g.outcome.eq('LOSS').sum()),('zero_trade_segments',g.zero_trades.sum())]:assert getattr(row,field)==expected
        if row.status=='COMPLETE':
            assert not g.slug.duplicated().any()
            for field,v in [('median_return_pct',g.return_pct.median()),('median_drawdown_pct',g.max_drawdown_pct.abs().median()),('median_return_change_pp',g.return_change_pp.median()),('median_drawdown_reduction_pp',g.drawdown_reduction_pp.median()),('median_closed_trade_payoff',g.closed_trade_payoff_ratio.median()),('median_closed_trade_pf',g.closed_trade_profit_factor.median())]:close(getattr(row,field),v)
        else:assert pd.isna(row.median_return_pct) and pd.isna(row.profitable_fraction_all_segments)
    c=pd.read_parquet(R/'pairs/cases.parquet');phase=np.where(c.entry_time<pd.Timestamp('2025-01-01',tz='UTC'),'phase_2023_2024','phase_2025_2026');c['phase']=phase
    terminal=c[[x for x in c if x.startswith('terminal_')]].any(axis=1);nat=c[~terminal].copy()
    fixed=pd.read_csv(R/'analysis/fixed_case_summary.csv');net_rows=[]
    for rec in fixed.itertuples(index=False):
        g=nat[nat.phase.eq(rec.phase)].copy();before=g.u_U_READY;after=g['u_'+rec.arm]
        allowed=g['allow_'+rec.arm] if 'allow_'+rec.arm in g else pd.Series(True,index=g.index)
        winners=before>0;losers=before<0;delta=after-before
        assert len(g)==rec.natural_ready_cases and g.slug.nunique()==rec.coins
        assert int((winners&~allowed).sum())==rec.winners_rejected
        assert int((winners&(after<0)).sum())==rec.winners_turned_loss
        assert int((losers&(delta>1e-12)).sum())==rec.losers_improved
        per=pd.DataFrame({'slug':g.slug,'before':before,'after':after,'delta':delta}).groupby('slug').mean()
        close(rec.equal_coin_mean_improvement_pp,per.delta.mean()*100)
        close(rec.equal_coin_mean_selected_return_pct,per.after.mean()*100)
        close(rec.positive_winner_retention,after[winners].clip(lower=0).sum()/before[winners].sum())
        # Keep negative outcomes of former winners in this supplementary net measure.
        top=g[winners].sort_values(['slug','u_U_READY','case_id'],ascending=[True,False,True]).groupby('slug').head(5)
        top_after=top['u_'+rec.arm];close(rec.top5_positive_profit_retention,top_after.clip(lower=0).sum()/top.u_U_READY.sum())
        net_rows.append({'phase':rec.phase,'arm':rec.arm,'original_winner_net_retention':after[winners].sum()/before[winners].sum(),
            'original_winner_positive_retention':rec.positive_winner_retention,'top5_net_retention':top_after.sum()/top.u_U_READY.sum(),
            'top5_positive_retention':rec.top5_positive_profit_retention,'original_winners':int(winners.sum()),
            'winners_turned_loss':rec.winners_turned_loss,'winners_rejected':rec.winners_rejected})
    pd.DataFrame(net_rows).to_csv(out/'winner_net_retention.csv',index=False)
    meta=json.loads((OLD/'cases/sources.json').read_text());cache={};market=[]
    for row in p[p.case_id.eq('U_READY')&p.status.eq('COMPLETE')].itertuples(index=False):
        key=row.run_key
        if key not in cache:
            d=pd.read_parquet(OLD/'cases/daily_features'/(key+'.parquet'));d.timestamp=pd.to_datetime(d.timestamp,utc=True);cache[key]=d.set_index('timestamp')
        d=cache[key];a=pd.Timestamp(row.actual_start)-pd.Timedelta(days=1);b=pd.Timestamp(row.actual_end)-pd.Timedelta(days=1)
        ret=(float(d.loc[b,'close'])/float(d.loc[a,'close'])-1)*100
        market.append({'block':row.block,'slug':row.slug,'run_key':key,'close_to_close_gross_pct':ret})
    m=pd.DataFrame(market);m.to_csv(out/'market_background_by_coin.csv',index=False)
    rows=[]
    for block,g in m.groupby('block'):
        btc=g.loc[g.slug.eq('BTC'),'close_to_close_gross_pct']
        rows.append({'block':block,'coins':g.slug.nunique(),'positive_price_coins':int(g.close_to_close_gross_pct.gt(0).sum()),'median_price_change_pct':g.close_to_close_gross_pct.median(),'btc_price_change_pct':None if btc.empty else btc.iloc[0]})
    pd.DataFrame(rows).to_csv(out/'market_background.csv',index=False)
    (out/'source_script.py.txt').write_bytes(Path(__file__).read_bytes())
    write_json(out/'final.json',{'status':'PASS','period_account_rows':len(p),'period_summary_groups':len(s),'same_entry_summary_groups':len(fixed),'same_entry_cases':len(c),'natural_common_cases':len(nat),'analysis_manifest_sha256':sha(R/'analysis/artifact_checksums.json'),'pairs_manifest_sha256':sha(R/'pairs/artifact_checksums.json'),'market_background_is_gross_price_change_not_strategy_return':True,'source_script_sha256':sha(Path(__file__))})
    write_json(out/'artifact_checksums.json',{str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file() and f.name!='artifact_checksums.json'})
    print('Summary and net-winner reconciliation PASS')

if __name__=='__main__':main()
