"""只汇总已冻结结果：方向匹配的筛选增量、门槛、成本、年度和集中度。"""
from pathlib import Path
import argparse
import json
import math
import numpy as np
import pandas as pd
from run_research import FAMILY, save, sha
from statistical_review import wilson


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run-id',default='p5-final-evidence-20260908')
    p.add_argument('--evaluation-dir',default='p1-evaluation-20260908-r1')
    p.add_argument('--applicability-dir',default='p2-applicability-20260908-r2')
    args=p.parse_args();out=FAMILY/'artifacts'/args.run_id
    assert not out.exists();out.mkdir()
    ev=FAMILY/'artifacts'/args.evaluation_dir;ap=FAMILY/'artifacts'/args.applicability_dir
    for d in [ev,ap]:assert (d/'completed.json').exists() and not (d/'INVALIDATED.json').exists()
    df=pd.read_csv(ev/'results.csv');a=pd.read_csv(ap/'results.csv')
    monthly=pd.read_csv(ap/'monthly-returns.csv.gz')
    summaries=[];gate_rows=[];boot=[];rng=np.random.default_rng(20260909)
    for window in ['main','development','middle','held']:
        g=a[a.window.eq(window)]
        if window in ['middle','held']:g=g[g.full_requested_window]
        base=g[g.variant.eq('short_only')].set_index('symbol')
        for variant in ['low_er_short','liquid_short']:
            x=g[g.variant.eq(variant)].set_index('symbol').reindex(base.index)
            assert len(x)==len(base) and x.return_pct.notna().all()
            delta=x.return_pct-base.return_pct;k=int((delta>0).sum());lo,hi=wilson(k,len(x))
            summaries.append({'window':window,'variant':variant,'control':'short_only','n':len(x),
                'positive':int((x.return_pct>0).sum()),'control_positive':int((base.return_pct>0).sum()),
                'strict':int(x.strict.sum()),'control_strict':int(base.strict.sum()),
                'median_return_pct':x.return_pct.median(),'control_median_return_pct':base.return_pct.median(),
                'median_paired_increment_pp':delta.median(),'improved_assets':k,
                'improved_fraction':k/len(x),'improved_wilson95_lo':lo,'improved_wilson95_hi':hi,
                'median_natural_trades':x.natural_trades.median(),'median_mdd_pct':x.mdd_pct.median(),
                'selected_assets':int((x.n_trades>0).sum()),'mean_time_coverage':x.filter_time_coverage.mean(),
                'stress_positive':int((x.stress_return_pct>0).sum())})
            # Month block inference only on equal full windows; development windows differ by asset.
            if window=='development':continue
            m=monthly[monthly.window.eq(window)]
            b=m[m.variant.eq('short_only')].pivot(index='symbol',columns='month',values='month_return').reindex(base.index).sort_index(axis=1)
            v=m[m.variant.eq(variant)].pivot(index='symbol',columns='month',values='month_return').reindex(index=b.index,columns=b.columns)
            bv=b.to_numpy();vv=v.to_numpy();assert np.isfinite(bv).all() and np.isfinite(vv).all()
            n,t=bv.shape;increments=[];improved=[]
            for _ in range(500):
                assets=rng.integers(0,n,n);starts=rng.integers(0,t,math.ceil(t/3))
                months=np.concatenate([(s+np.arange(3))%t for s in starts])[:t]
                br=np.prod(1+bv[assets][:,months],axis=1)-1
                vr=np.prod(1+vv[assets][:,months],axis=1)-1
                increments.append(np.median(vr-br)*100);improved.append(np.mean(vr>br))
            boot.append({'window':window,'variant':variant,'control':'short_only','n':n,'months':t,
                'runs':500,'circular_month_block':3,'median_increment95_lo_pp':np.quantile(increments,.025),
                'median_increment95_hi_pp':np.quantile(increments,.975),
                'improved_fraction95_lo':np.quantile(improved,.025),'improved_fraction95_hi':np.quantile(improved,.975)})
        for variant,x in g.groupby('variant'):
            names=sorted({v for s in x.failed_gates.fillna('') for v in s.split(',') if v})
            for gate in names:
                gate_rows.append({'window':window,'variant':variant,'gate':gate,'n':len(x),
                    'failed':int(x.failed_gates.fillna('').str.split(',').map(lambda v:gate in v).sum())})
    pd.DataFrame(summaries).to_csv(out/'short-filter-controlled-comparison.csv',index=False)
    pd.DataFrame(boot).to_csv(out/'short-filter-block-bootstrap.csv',index=False)
    pd.DataFrame(gate_rows).to_csv(out/'strict-gate-failures.csv',index=False)
    chosen=df[df.candidate.eq('C3')&df.asset_class.eq('COIN')]
    annual=[]
    for window,g in chosen[chosen.full_requested_window].groupby('window'):
        annual.append({'window':window,'n':len(g),'positive':int((g.return_pct>0).sum()),'strict':int(g.strict.sum()),
            'median_return_pct':g.return_pct.median(),'median_mdd_pct':g.mdd_pct.median(),
            'gross_positive':int((g.gross_return_pct>0).sum()),'stress_positive':int((g.stress_return_pct>0).sum()),
            'gross_median_return_pct':g.gross_return_pct.median(),'stress_median_return_pct':g.stress_return_pct.median(),
            'median_long_log_growth':g.long_log_growth.median(),'median_short_log_growth':g.short_log_growth.median(),
            'median_long_largest_profit_share':g.long_largest_profit_share.median(),
            'median_short_largest_profit_share':g.short_largest_profit_share.median()})
    pd.DataFrame(annual).to_csv(out/'C3-annual-cost-direction-concentration.csv',index=False)
    recent=pd.read_csv(ev/'recent-slices.csv');recent=recent[recent.asset_class.eq('COIN')&recent.candidate.eq('C3')]
    recent.groupby('requested_days').agg(n=('symbol','size'),positive=('return_pct',lambda s:int((s>0).sum())),
        median_return_pct=('return_pct','median'),total_exits=('exits','sum')).to_csv(out/'C3-recent-slices.csv')
    # Every main account and every candidate must have the same eligible symbol set.
    main=df[df.window.eq('main')&df.asset_class.eq('COIN')]
    symbolsets=[set(g.symbol) for _,g in main.groupby('candidate')]
    assert len(symbolsets)==10 and all(s==symbolsets[0] for s in symbolsets) and len(symbolsets[0])==205
    for _,g in a[a.window.eq('main')].groupby('variant'):assert set(g.symbol)==symbolsets[0]
    reference=main[main.candidate.eq('C3')].set_index('symbol').sort_index()
    unfiltered=a[a.window.eq('main')&a.variant.eq('unfiltered')].set_index('symbol').sort_index()
    np.testing.assert_allclose(reference.return_pct,unfiltered.return_pct,rtol=0,atol=1e-12)
    save(out/'completed.json',{'status':'PASS','main_crypto_denominator':205,'main_candidates':10,
        'applicability_configurations':a.variant.nunique(),'no_reselection_or_new_strategy':True,
        'evaluation_sha256':sha(ev/'results.csv'),'applicability_sha256':sha(ap/'results.csv'),
        'source_sha256':sha(Path(__file__)),'inference_boundary':'block bootstrap is exploratory resampling of realized monthly returns, not counterfactual strategy replay'})
    print('FINAL EVIDENCE PASS',out)


if __name__=='__main__':main()
