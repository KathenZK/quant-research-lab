"""Paired descriptive comparisons from this topic's frozen outputs only."""
from pathlib import Path
import argparse, hashlib, json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
NAMES={'long':'原版只做多','short':'对称只做空','both':'双向，等待止损','reverse':'双向，信号反手'}


def save(p,x):
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',default='20260908-r1');args=parser.parse_args()
    out=ROOT/'artifacts'/args.run_id
    assert not (out/'analysis.json').exists(),'Refuse to overwrite retained analysis'
    manifest=json.loads((out/'run-manifest.json').read_text())
    for name,sha in manifest.items():
        assert hashlib.sha256((out/name).read_bytes()).hexdigest()==sha,name
    d=pd.read_csv(out/'all-window-results.csv.gz')
    m=d.loc[d.window.eq('main')&d.representative].copy()
    cohorts={'main_full':m.loc[m.asset_class.eq('COIN')&m.full_requested_window],
             'main_full_clean':m.loc[m.asset_class.eq('COIN')&m.full_requested_window&~m.economic_flag],
             'main_all_coin':m.loc[m.asset_class.eq('COIN')],
             'main_all_coin_clean':m.loc[m.asset_class.eq('COIN')&~m.economic_flag],
             'main_unknown':m.loc[m.asset_class.eq('UNKNOWN')]}
    for key in ['partial_180plus','short_30_179','ended']:
        cohorts['main_'+key]=m.loc[m.asset_class.eq('COIN')&m.cohort.eq(key)]
    for year in range(2020,2027):
        a=d.loc[d.window.eq(str(year))&d.asset_class.eq('COIN')&d.full_requested_window]
        cohorts[str(year)]=a
        cohorts[str(year)+'_clean']=a.loc[~a.economic_flag]
    stats=[];paired=[]
    for key,a in cohorts.items():
        piv=a.pivot(index='run_id',columns='variant',values='return_pct')
        for variant,g in a.groupby('variant',sort=False):
            r=g.return_pct
            stats.append(dict(cohort=key,variant=variant,n=len(g),profitable=int((r>0).sum()),
                profitable_pct=float((r>0).mean()*100),median_return_pct=float(r.median()),
                p10_return_pct=float(r.quantile(.1)),p90_return_pct=float(r.quantile(.9)),
                median_mdd_pct=float(g.mdd_pct.median()),median_trades=float(g.n_trades.median()),
                median_win_rate_pct=float(g.win_rate_pct.median()),bankrupt=int(g.bankrupt.sum()),
                flags=int(g.economic_flag.sum()),median_buyhold_pct=float(g.buyhold_return_pct.median()),
                gross_median_return_pct=float(g.gross_return_pct.median()),stress_median_return_pct=float(g.stress_return_pct.median()),
                gross_profitable_pct=float((g.gross_return_pct>0).mean()*100),stress_profitable_pct=float((g.stress_return_pct>0).mean()*100),
                gross_bankrupt=int(g.gross_bankrupt.sum()),stress_bankrupt=int(g.stress_bankrupt.sum()),
                reversal_exits=int(g.reversal_exits.sum()),n_long=int(g.n_long.sum()),n_short=int(g.n_short.sum())))
        if len(piv):
            for v,base in [('short','long'),('both','long'),('reverse','long'),('reverse','both')]:
                diff=piv[v]-piv[base]
                paired.append(dict(cohort=key,variant=v,baseline=base,n=len(diff),improved=int((diff>1e-8).sum()),
                    improved_pct=float((diff>1e-8).mean()*100),median_return_delta_pp=float(diff.median()),
                    turned_profitable=int(((piv[base]<=0)&(piv[v]>0)).sum()),lost_profitability=int(((piv[base]>0)&(piv[v]<=0)).sum())))
    stats=pd.DataFrame(stats);paired=pd.DataFrame(paired)
    strength=[]
    for key in ['main_full']+[str(y) for y in range(2020,2027)]:
        a=cohorts[key]
        for label,low,high in [('跌超50%',-np.inf,-50),('下跌0至50%',-50,0),('上涨0至100%',0,100),('上涨100%以上',100,np.inf)]:
            sub=a.loc[a.buyhold_return_pct.ge(low)&a.buyhold_return_pct.lt(high)]
            for v,g in sub.groupby('variant',sort=False):
                strength.append(dict(window=key,buyhold_bin=label,variant=v,n=len(g),median_return_pct=float(g.return_pct.median()),
                    profitable_pct=float((g.return_pct>0).mean()*100),median_buyhold_pct=float(g.buyhold_return_pct.median()),median_mdd_pct=float(g.mdd_pct.median())))
    reference=m.loc[m.coin.isin(['BTC','ETH','SOL','BNB','UNI','ARB','LIT','HYPE','ZEC'])].copy()
    annual_ref=d.loc[d.window.isin([str(y) for y in range(2020,2027)])&d.representative&d.coin.isin(reference.coin.unique())].copy()
    t=pd.read_csv(out/'main-window-trades.csv.gz')
    decomp=[]
    ids=set(cohorts['main_full'].run_id)
    for v,g in t.loc[t.run_id.isin(ids)].groupby('variant',sort=False):
        for side,h in g.groupby('side'):
            decomp.append(dict(variant=v,side=int(side),n=len(h),wins=int((h.ret_pct>0).sum()),
                win_rate_pct=float((h.ret_pct>0).mean()*100),mean_win_pct=float(h.loc[h.ret_pct>0,'ret_pct'].mean()) if (h.ret_pct>0).any() else None,
                mean_loss_pct=float(h.loc[h.ret_pct<=0,'ret_pct'].mean()) if (h.ret_pct<=0).any() else None,
                mean_trade_pct=float(h.ret_pct.mean()),reverse_exits=int(h.reason.eq('reverse_signal').sum()),
                terminal_valuations=int(h.reason.eq('end_of_test').sum()),bankruptcy_trades=int(h.economic_bankruptcy.sum())))
    stats.to_csv(out/'cohort-statistics.csv',index=False)
    paired.to_csv(out/'paired-comparisons.csv',index=False)
    pd.DataFrame(strength).to_csv(out/'realized-strength-groups.csv',index=False)
    reference.to_csv(out/'reference-coins.csv',index=False)
    annual_ref.to_csv(out/'reference-coins-annual.csv',index=False)
    m.to_csv(out/'main-symbol-results.csv',index=False)
    pd.DataFrame(decomp).to_csv(out/'main-trade-decomposition.csv',index=False)
    # All default/gross/stress rows with economic bankruptcy stay visible.
    d.loc[d.bankrupt|d.gross_bankrupt|d.stress_bankrupt].to_csv(out/'bankruptcy-ledger.csv',index=False)
    save(out/'analysis.json',dict(status='DESCRIPTIVE_PAIRED_AUDIT',cohorts=stats.to_dict('records'),paired=paired.to_dict('records'),
        strength=strength,main_trade_decomposition=decomp,full_sample_counts={key:int(len(a)//4) for key,a in cohorts.items()},
        funding_included=False,all_windows_reused_history=True))
    print(stats.loc[stats.cohort.isin(['main_full','main_full_clean','2021','2022','2024','2025','2026']),['cohort','variant','n','profitable_pct','median_return_pct','median_mdd_pct','median_trades','bankrupt']].to_string(index=False))
    print(reference.pivot(index='coin',columns='variant',values='return_pct').to_string())


if __name__=='__main__':main()
