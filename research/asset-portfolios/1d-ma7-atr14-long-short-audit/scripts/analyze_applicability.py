"""Frozen applicability contrasts, prospective-in-time asset groups and persistence."""
from pathlib import Path
import hashlib,json,math
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/applicability-20260908'
PARENT=ROOT/'artifacts/20260908-r1'
FEATURES=['trend_aligned','momentum_aligned','efficiency30','chop30','atr_pct','liquidity30']
SEED=202609081


def finite(x):
    return float(x) if pd.notna(x) and np.isfinite(x) else None


def describe(t):
    ratio=t.equity_after/t.equity_before
    n=len(t)
    return dict(trades=n,symbols=int(t.symbol.nunique()),months=int(t.month.nunique()),
        mean_return_pct=finite(t.ret_pct.mean()),median_return_pct=finite(t.ret_pct.median()),
        win_rate_pct=finite(t.ret_pct.gt(0).mean()*100) if n else None,
        big_loss_pct=finite(t.ret_pct.le(-30).mean()*100) if n else None,
        bankruptcies=int(ratio.le(0).sum()),
        mean_log_return_pct=finite(np.log(ratio).mean()*100) if n and ratio.gt(0).all() else None)


def masks(t,key):
    if key=='trend_aligned':
        a=(t.trend_state*t.side).eq(1);return a,~a
    if key=='momentum_aligned':
        a=(t.momentum30*t.side).gt(0);return a,~a
    if key=='efficiency30':return t.efficiency30.ge(.25),t.efficiency30.lt(.10)
    if key=='chop30':return t.chop30.le(3),t.chop30.ge(8)
    if key=='atr_pct':return t.atr_pct.le(3),t.atr_pct.gt(6)
    if key=='liquidity30':return t.liquidity30.ge(1e7),t.liquidity30.lt(1e7)
    raise KeyError(key)


def bootstrap(t,a,b,seed=SEED):
    choose=a|b;t=t.loc[choose];a=a.loc[choose].to_numpy();b=b.loc[choose].to_numpy()
    if not a.any() or not b.any():return dict(effect_pp=None,ci_low=None,ci_high=None,month_adjusted_pp=None)
    si,syms=pd.factorize(t.symbol,sort=True);mi,months=pd.factorize(t.month,sort=True)
    ns,nm=len(syms),len(months);idx=si*nm+mi;y=t.ret_pct.to_numpy()
    def matrix(m):
        n=np.bincount(idx[m],minlength=ns*nm).reshape(ns,nm)
        s=np.bincount(idx[m],weights=y[m],minlength=ns*nm).reshape(ns,nm)
        return n,s
    na,sa=matrix(a);nb,sb=matrix(b)
    rng=np.random.default_rng(seed);ws=rng.poisson(1,(500,ns)).astype(float);wm=rng.poisson(1,(500,nm)).astype(float)
    def draw(x):return np.einsum('bi,ij,bj->b',ws,x,wm,optimize=True)
    da,db=draw(na),draw(nb);good=(da>0)&(db>0)
    delta=draw(sa)[good]/da[good]-draw(sb)[good]/db[good]
    nac,nbc=na.sum(axis=0),nb.sum(axis=0);ok=(nac>0)&(nbc>0)
    adjust=np.average(sa.sum(axis=0)[ok]/nac[ok]-sb.sum(axis=0)[ok]/nbc[ok],weights=nac[ok]*nbc[ok]/(nac[ok]+nbc[ok])) if ok.any() else None
    ci=np.quantile(delta,[.025,.975]) if len(delta)>100 else [None,None]
    return dict(effect_pp=float(y[a].mean()-y[b].mean()),ci_low=finite(ci[0]),ci_high=finite(ci[1]),
        month_adjusted_pp=finite(adjust),paired_months=int(ok.sum()),valid_draws=len(delta))


def enough(d):return d['trades']>=30 and d['symbols']>=10 and d['months']>=5


def annual_labels(a):
    return dict(trend_state=a.trend_state.map({1.:'上涨且MA60上行',-1.:'下跌且MA60下行',0.:'方向混合'}),
        momentum30=np.where(a.momentum30>0,'过去30日上涨','过去30日未上涨'),
        efficiency30=pd.cut(a.efficiency30,[-np.inf,.1,.25,np.inf],right=False,labels=['ER<0.10','ER0.10..0.25','ER>=0.25']),
        chop30=pd.cut(a.chop30,[-np.inf,3,7,np.inf],right=True,labels=['穿越<=3','穿越4..7','穿越>=8']),
        atr90=pd.cut(a.atr90,[-np.inf,3,6,np.inf],right=True,labels=['ATR<=3%','ATR3..6%','ATR>6%']),
        liquidity90=np.where(a.liquidity90>=1e7,'日成交额>=1000万美元','日成交额<1000万美元'))


def prior_quartile(previous,next_frame):
    """The historical cutoff does not depend on next-year availability."""
    threshold=previous.return_pct.quantile(.75)
    selected=set(previous.loc[previous.return_pct.ge(threshold),'symbol'])
    pair=previous.merge(next_frame,on='symbol',suffixes=('_prev','_next'))
    pair['selected']=pair.symbol.isin(selected)
    return float(threshold),selected,pair


def main():
    assert not (OUT/'analysis.json').exists(),'Preserve retained analysis'
    c=json.loads((ROOT/'specs/applicability-contract-20260908.json').read_text())
    manifest=json.loads((OUT/'feature-manifest.json').read_text())
    for rel,sha in manifest.items():assert hashlib.sha256((OUT/rel).read_bytes()).hexdigest()==sha,rel
    t=pd.read_csv(OUT/'trade-features.csv.gz');t['month']=t.entry_date.str[:7]
    t['entry']=pd.to_datetime(t.entry_date,utc=True);t['exit']=pd.to_datetime(t.exit_date,utc=True)
    t['leg']=t.variant+np.where(t.side.eq(1),'_long','_short')
    base=t.loc[t.asset_class.eq('COIN')&t.feature_valid&t.natural_exit].copy()
    contrasts=[];purges=[]
    for period,(start,end) in c['periods'].items():
        start=pd.Timestamp(start,tz='UTC');end=pd.Timestamp(end,tz='UTC')
        entries=base.loc[base.entry.ge(start)&base.entry.lt(end)];eligible=entries.loc[entries.exit.lt(end)]
        purges.append(dict(period=period,natural_entries=len(entries),eligible=len(eligible),cross_boundary_removed=len(entries)-len(eligible)))
        scopes={'raw':eligible}
        if period=='all':
            scopes['remove_named_nine']=eligible.loc[~eligible.coin.isin(c['sensitivities']['remove_named_nine'])]
            scopes['exclude_flagged_and_three_non_native']=eligible.loc[~eligible.economic_flag&~eligible.coin.isin(c['sensitivities']['exclude_flagged_and_three_non_native'])]
        for scope,pool in scopes.items():
            for leg,g in pool.groupby('leg',sort=True):
                for j,key in enumerate(FEATURES):
                    am,bm=masks(g,key);ad,bd=describe(g.loc[am]),describe(g.loc[bm])
                    effect=bootstrap(g,am,bm,SEED+j+sum(map(ord,leg+period+scope)))
                    contrasts.append(dict(period=period,scope=scope,leg=leg,feature=key,adequate=enough(ad)&enough(bd),
                        **effect,**{'a_'+k:v for k,v in ad.items()},**{'b_'+k:v for k,v in bd.items()}))
        print('PERIOD DONE',period,len(contrasts),flush=True)
    d=pd.DataFrame(contrasts);d.to_csv(OUT/'entry-feature-contrasts.csv',index=False)
    rules=[]
    for (leg,key),g in d.groupby(['leg','feature'],sort=True):
        allrow=g.loc[g.period.eq('all')&g.scope.eq('raw')].iloc[0]
        yearly=g.loc[g.period.isin(['2024','2025','2026'])&g.scope.eq('raw')]
        s=int(np.sign(allrow.effect_pp)) if pd.notna(allrow.effect_pp) else 0
        annual_ok=len(yearly)==3 and yearly.adequate.all()
        same=annual_ok and s!=0 and bool((yearly.effect_pp*s>0).all())
        ci_ok=bool(pd.notna(allrow.ci_low) and (allrow.ci_low>0 if s>0 else allrow.ci_high<0)) if s else False
        month_ok=bool((yearly.month_adjusted_pp*s>0).all()) if same else False
        sens=g.loc[g.period.eq('all')&~g.scope.eq('raw')]
        sens_ok=len(sens)==2 and bool((sens.effect_pp*s>0).all()) and bool(sens.adequate.all()) if s else False
        association=bool(same and ci_ok and month_ok and sens_ok)
        side='a' if s>0 else 'b'
        profit=association and bool(yearly[f'{side}_mean_return_pct'].gt(0).all()) and bool(yearly[f'{side}_mean_log_return_pct'].gt(0).all())
        rules.append(dict(leg=leg,feature=key,favored=side.upper(),direction=s,all_effect_pp=finite(allrow.effect_pp),
            all_ci_low=finite(allrow.ci_low),all_ci_high=finite(allrow.ci_high),all_years_adequate=bool(annual_ok),
            three_year_effect_sign=bool(same),pooled_ci_excludes_zero=ci_ok,three_year_month_adjusted_sign=month_ok,
            two_sensitivities_sign=bool(sens_ok),robust_association_screen=association,positive_log_profit_candidate=bool(profit)))
    rules=pd.DataFrame(rules);rules.to_csv(OUT/'rule-stability.csv',index=False)
    # Terminal valuations do not become natural-exit labels in the primary table.
    terminal=[]
    all_labels=t.loc[t.asset_class.eq('COIN')&t.feature_valid&t.entry.ge(pd.Timestamp('2020-01-01',tz='UTC'))]
    for leg,g in all_labels.groupby('leg'):
        for key in FEATURES:
            a,b=masks(g,key);ad,bd=describe(g.loc[a]),describe(g.loc[b])
            terminal.append(dict(leg=leg,feature=key,including_terminal=True,effect_pp=finite(g.loc[a,'ret_pct'].mean()-g.loc[b,'ret_pct'].mean()),a_trades=ad['trades'],b_trades=bd['trades']))
    pd.DataFrame(terminal).to_csv(OUT/'terminal-label-sensitivity.csv',index=False)
    # Fixed asset characteristics known before the target year, with whole-year outcomes.
    a=pd.read_csv(OUT/'annual-asset-features.csv.gz');a.window=a.window.astype(str)
    coin=a.loc[a.asset_class.eq('COIN')];valid=coin.loc[coin.features_valid].copy()
    atlas=[]
    for feature,labels in annual_labels(valid).items():
        z=valid.assign(feature_group=labels)
        for (year,v,label),g in z.groupby(['window','variant','feature_group'],observed=True,sort=True):
            baseline=valid.loc[valid.window.eq(year)&valid.variant.eq(v),'return_pct']
            atlas.append(dict(year=year,variant=v,feature=feature,group=str(label),n=len(g),adequate=len(g)>=20,
                median_return_pct=float(g.return_pct.median()),profitable_pct=float(g.return_pct.gt(0).mean()*100),
                median_mdd_pct=float(g.mdd_pct.median()),bankrupt=int(g.bankrupt.sum()),
                baseline_median_return_pct=float(baseline.median()),delta_vs_baseline_median_pp=float(g.return_pct.median()-baseline.median())))
    atlas=pd.DataFrame(atlas);atlas.to_csv(OUT/'annual-asset-type-atlas.csv',index=False)
    types=[]
    for (v,f,label),g in atlas.groupby(['variant','feature','group'],observed=True):
        ys=g.loc[g.year.isin(['2024','2025','2026'])]
        adequate=len(ys)==3 and bool(ys.adequate.all())
        types.append(dict(variant=v,feature=f,group=label,three_year_adequate=adequate,
            positive_median_all_three=adequate and bool(ys.median_return_pct.gt(0).all()),
            above_unfiltered_median_all_three=adequate and bool(ys.delta_vs_baseline_median_pp.gt(0).all()),
            **{f'{r.year}_n':int(r.n) for r in ys.itertuples()},
            **{f'{r.year}_median':r.median_return_pct for r in ys.itertuples()}))
    pd.DataFrame(types).to_csv(OUT/'annual-type-stability.csv',index=False)
    # Cutoffs learned from all previous-year complete observations, before future intersection.
    r=pd.read_csv(PARENT/'all-window-results.csv.gz');r=r.loc[r.asset_class.eq('COIN')]
    persistence=[]
    for v in ['long','short','both','reverse']:
        for year in range(2020,2026):
            prev=r.loc[r.variant.eq(v)&r.window.eq(str(year))&r.full_requested_window]
            next_all=r.loc[r.variant.eq(v)&r.window.eq(str(year+1))&r.representative]
            nxt=next_all.loc[next_all.full_requested_window]
            cutoff,selected,pair=prior_quartile(prev,nxt)
            full_selected=pair.loc[pair.selected];others=pair.loc[~pair.selected]
            next_known=set(next_all.symbol)
            rho=spearmanr(pair.return_pct_prev,pair.return_pct_next).statistic if len(pair)>=4 and pair.return_pct_prev.nunique()>1 and pair.return_pct_next.nunique()>1 else None
            persistence.append(dict(variant=v,previous_year=year,next_year=year+1,previous_all=len(prev),pairs=len(pair),
                prior_cutoff_pct=cutoff,selected_total=len(selected),selected_next_complete=len(full_selected),
                selected_next_partial=len(selected&next_known)-len(full_selected),selected_next_absent=len(selected-next_known),
                spearman_rho=finite(rho),next_median_prior_top=finite(full_selected.return_pct_next.median()),
                next_median_others=finite(others.return_pct_next.median()),next_profitable_prior_top_pct=finite(full_selected.return_pct_next.gt(0).mean()*100)))
    pd.DataFrame(persistence).to_csv(OUT/'coin-year-persistence.csv',index=False)
    coverage=coin.groupby(['window','variant']).agg(all_complete=('symbol','size'),features_valid=('features_valid','sum')).reset_index()
    coverage.to_csv(OUT/'annual-feature-coverage.csv',index=False)
    result=dict(status='REUSED_HISTORY_APPLICABILITY_DIAGNOSTIC',all_trades=len(t),coin_feature_valid_natural_trades=len(base),
        raw_trade_labels_including_bankruptcies=int(base.bankrupt.sum()),purges=purges,
        contrasts=len(d),rules=rules.astype(object).where(pd.notna(rules),None).to_dict('records'),annual_types=types,persistence=persistence,
        robust_association_count=int(rules.robust_association_screen.sum()),positive_log_profit_candidate_count=int(rules.positive_log_profit_candidate.sum()),
        annual_positive_types=[x for x in types if x['positive_median_all_three']],funding_included=False,new_filter_backtest=False)
    (OUT/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print('RULES',rules.to_string(index=False),flush=True)
    print('ANNUAL POSITIVE TYPES',result['annual_positive_types'],flush=True)


if __name__=='__main__':main()
