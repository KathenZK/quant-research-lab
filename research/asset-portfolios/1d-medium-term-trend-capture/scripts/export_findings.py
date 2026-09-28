"""从保留的完整结果导出解释表；不改变任何候选、规则或账户。"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
RUN = FAMILY/'artifacts/research-20260909'


def metrics(values):
    a = pd.Series(values).dropna().astype(float)
    if not len(a):
        return {'n':0}
    pos, neg = a[a>0], a[a<0]
    return dict(n=len(a),mean=float(a.mean()),median=float(a.median()),win_fraction=float((a>0).mean()),
                mean_win=float(pos.mean()) if len(pos) else None,
                mean_loss=float(neg.mean()) if len(neg) else None,
                q05=float(a.quantile(.05)),q95=float(a.quantile(.95)),
                profit_factor=float(pos.sum()/abs(neg.sum())) if neg.sum()!=0 else None)


def main():
    out=FAMILY/'artifacts/interpretation'
    out.mkdir(exist_ok=False)
    roots=pd.read_parquet(RUN/'origins.parquet')
    obs=pd.read_parquet(RUN/'opportunities.parquet')
    acts=pd.read_parquet(RUN/'portfolio_actions.parquet')
    units=pd.read_parquet(RUN/'unit_daily.parquet')
    root_details={'origins':len(roots),'symbols':roots.symbol.nunique(),
                  'complete_window_60':int(roots.complete_window_60.sum()),
                  'first_observable':int(roots.first_observable.sum())}
    for h in (20,60):
        root_details[f'origin_{h}_outcomes']=roots[f'origin_{h}_outcome'].value_counts().to_dict()
        root_details[f'origin_{h}_endpoint']=metrics(roots[f'origin_{h}_endpoint_return'])
    summaries={}
    yearly=[]
    for (cost,policy),g in obs.groupby(['cost_id','policy']):
        common=g[g.complete_window_60 & g.normal_complete]
        traded=common[common.entered]
        key=f'{cost}.{policy}'
        account=acts[acts.cost_id.eq(cost)&acts.policy.eq(policy)]
        summary=dict(all_opportunities=len(g),entered=int(g.entered.sum()),
                     states=g.terminal_status.value_counts().to_dict(),
                     common_opportunity=metrics(common['return']),
                     common_traded=metrics(traded['return']),
                     completed_trades=metrics(g.loc[g.entered & g.normal_complete,'return']),
                     common_entry_fraction=float(common.entered.mean()),
                     mean_holding_days=float(traded.holding_days.mean()),
                     median_holding_days=float(traded.holding_days.median()),
                     stop_breach_before_daily_exit=int(g.intraday_stop_breach.sum()),
                     planned_stop_exceeded_trades=int((g.entered & g.normal_complete & (g['return']<-.1)).sum()),
                     fees_per_common_opportunity=float(common.fees.mean()),
                     carry_per_common_opportunity=float(common.carry.mean()),
                     account_rejections=account.loc[account.event.eq('REJECT'),'reason'].value_counts().to_dict())
        for h in (20,60):
            summary[f'entry_{h}_outcomes']=traded[f'entry_{h}_outcome'].value_counts().to_dict()
            summary[f'entry_{h}_endpoint']=metrics(traded[f'entry_{h}_endpoint_return'])
        summaries[key]=summary
        for year,year_group in common.groupby(common.origin_ts.dt.year):
            yearly.append(dict(cost_id=cost,policy=policy,year=int(year),
                               entered=int(year_group.entered.sum()),**metrics(year_group['return'])))
    paired=pd.read_parquet(RUN/'paired-base.parquet')
    paired['B_minus_A']=paired.B-paired.A
    paired['C_minus_B']=paired.C-paired.B
    paired=paired.merge(obs.loc[obs.cost_id.eq('base')&obs.policy.eq('C'),['origin_id','entered','release_reason']],
                        on='origin_id',validate='one_to_one')
    paired['year']=paired.origin_ts.dt.year
    no_c=paired[~paired.entered]
    miss=dict(common_origins=len(paired),c_no_entry=len(no_c),
              b_profitable_while_c_no_entry=int((no_c.B>0).sum()),
              b_unprofitable_while_c_no_entry=int((no_c.B<0).sum()),
              b_return_given_c_no_entry=metrics(no_c.B),
              paired_B_minus_A=metrics(paired.B_minus_A),paired_C_minus_B=metrics(paired.C_minus_B),
              no_c_reasons=no_c.release_reason.value_counts().to_dict())
    deletion=[]
    for key in ['A','B','C','B_minus_A','C_minus_B']:
        for grouping in ['symbol','year']:
            contribution=paired.groupby(grouping)[key].sum()
            largest=contribution.idxmax()
            kept=paired[paired[grouping]!=largest]
            deletion.append(dict(metric=key,removed_group=grouping,removed_value=str(largest),
                                 removed_n=int((paired[grouping]==largest).sum()),
                                 original_mean=float(paired[key].mean()),**metrics(kept[key])))
    base=obs[obs.cost_id.eq('base')&obs.entered&obs.normal_complete].copy()
    held=units[units.cost_id.eq('base')&units.qty_close.gt(0)]
    peaks=held.groupby(['origin_id','policy']).high.max().rename('maximum_observed_high')
    base=base.join(peaks,on=['origin_id','policy'])
    base['maximum_favorable_price_pnl']=np.maximum(0.,(base.maximum_observed_high-base.entry_price)*base.qty)
    base['realized_price_pnl']=(base.exit_price-base.entry_price)*base.qty
    base['giveback_from_high']=base.maximum_favorable_price_pnl-base.realized_price_pnl
    pathsummary={p:{'trades':len(g),'mean_peak_price_pnl':float(g.maximum_favorable_price_pnl.mean()),
                    'mean_realized_price_pnl':float(g.realized_price_pnl.mean()),
                    'mean_giveback':float(g.giveback_from_high.mean())} for p,g in base.groupby('policy')}
    pd.DataFrame(yearly).to_csv(out/'yearly-opportunities.csv',index=False)
    pd.DataFrame(deletion).to_csv(out/'largest-contributor-removal.csv',index=False)
    paired.to_parquet(out/'paired-opportunity-details.parquet',index=False)
    base.to_parquet(out/'holding-path-details.parquet',index=False)
    values={'origins':root_details,'summaries':summaries,'waiting_misses':miss,'holding_path':pathsummary}
    (out/'findings.json').write_text(json.dumps(values,ensure_ascii=False,indent=2,allow_nan=False,default=str)+'\n')
    print(json.dumps({'origins':root_details,'waiting_misses':miss,'holding_path':pathsummary},ensure_ascii=False,default=str))


if __name__=='__main__':
    main()
