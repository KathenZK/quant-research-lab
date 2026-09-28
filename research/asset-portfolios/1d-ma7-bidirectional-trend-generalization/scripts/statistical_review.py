"""冻结回放的覆盖、隔离验证、回归与不确定性分析；不再选择参数。"""
from pathlib import Path
import json
import math
import argparse
import numpy as np
import pandas as pd
from scipy.stats import t as student_t
from run_research import FAMILY,INPUT,save,sha,groups,btc_reference

EVAL=FAMILY/'artifacts/p1-evaluation-20260908-r1'
APP=FAMILY/'artifacts/p2-applicability-20260908-r2'

def clustered_ols(x,y,group1,group2):
    """OLS + 两维聚类 inclusion-exclusion 协方差，逐维有限样本校正。"""
    x=np.asarray(x,float);y=np.asarray(y,float);n,k=x.shape
    beta=np.linalg.lstsq(x,y,rcond=None)[0];residual=y-x@beta
    bread=np.linalg.pinv(x.T@x);scores=x*residual[:,None]
    def one(groups):
        ids,unique=pd.factorize(groups);g=len(unique);assert g>1 and n>k
        sums=np.zeros((g,k));np.add.at(sums,ids,scores)
        return bread@(sums.T@sums)@bread*(g/(g-1))*((n-1)/(n-k))
    joint=pd.MultiIndex.from_arrays([group1,group2])
    covariance=one(group1)+one(group2)-one(joint)
    r2=1-np.sum(residual**2)/np.sum((y-y.mean())**2)
    return beta,covariance,r2

def bh_qvalues(values):
    p=np.asarray(values,float);order=np.argsort(p);ranked=p[order]
    corrected=np.minimum.accumulate((ranked*len(p)/np.arange(1,len(p)+1))[::-1])[::-1]
    result=np.empty_like(p);result[order]=np.minimum(1,corrected);return result

def split_trades(df):
    signal=pd.to_datetime(df.signal_ts,utc=True)+pd.Timedelta(days=1)
    exit_close=pd.to_datetime(df.exit_ts,utc=True)+pd.Timedelta(days=1)
    return {
        'development':df[(df.asset_fold<60)&(signal>=pd.Timestamp('2020-01-01',tz='UTC'))&(exit_close<pd.Timestamp('2023-12-01',tz='UTC'))],
        'middle':df[(df.asset_fold>=60)&(df.asset_fold<80)&(signal>=pd.Timestamp('2024-02-01',tz='UTC'))&(exit_close<pd.Timestamp('2025-01-01',tz='UTC'))],
        'held':df[(df.asset_fold>=80)&(signal>=pd.Timestamp('2025-02-01',tz='UTC'))&(exit_close<=pd.Timestamp('2026-09-05',tz='UTC'))]}

def wilson(k,n):
    if n==0:return None,None
    z=1.959963984540054;p=k/n;d=1+z*z/n
    centre=(p+z*z/(2*n))/d;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return centre-half,centre+half

def fractions(g):
    n=g.symbol.nunique();assert len(g)==n,'one row per underlying required'
    k=int((g.return_pct>0).sum());s=int(g.strict.sum());lo,hi=wilson(k,n)
    slo,shi=wilson(s,n)
    return {'n':n,'positive':k,'positive_fraction':k/n if n else None,'positive_wilson95_lo':lo,'positive_wilson95_hi':hi,
        'strict':s,'strict_fraction':s/n if n else None,'strict_wilson95_lo':slo,'strict_wilson95_hi':shi,
        'median_return_pct':g.return_pct.median(),'median_mdd_pct':g.mdd_pct.median(),
        'median_trades':g.n_trades.median(),'bankruptcies':int(g.bankrupt.sum())}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',default='p3-statistics-20260908-r1')
    parser.add_argument('--evaluation-dir',default=EVAL.name);parser.add_argument('--applicability-dir',default=APP.name)
    parser.add_argument('--selection-dir',default='p1-development-20260908-r1');args=parser.parse_args()
    ev=FAMILY/'artifacts'/args.evaluation_dir;apath=FAMILY/'artifacts'/args.applicability_dir
    out=FAMILY/'artifacts'/args.run_id;assert not out.exists();out.mkdir()
    assert (ev/'completed.json').exists() and (apath/'completed.json').exists()
    assert not (ev/'INVALIDATED.json').exists() and not (apath/'INVALIDATED.json').exists()
    df=pd.read_csv(ev/'results.csv');ap=pd.read_csv(apath/'results.csv')
    lock=json.loads((FAMILY/'artifacts'/args.selection_dir/'selection-lock.json').read_text());candidate=lock['selected_bidirectional_candidate']
    mainrows=[]
    mainframe=df[df.window.eq('main')&df.asset_class.eq('COIN')]
    for c,g in mainframe.groupby('candidate'):mainrows.append({'asset_class':'COIN','candidate':c,**fractions(g)})
    pd.DataFrame(mainrows).to_csv(out/'main-breadth.csv',index=False)
    # Every denominator is fixed before candidate returns. Missing/short stocks remain unverified.
    primary=pd.DataFrame(mainrows).set_index('candidate').loc[candidate].to_dict()
    population={'main_crypto':primary,'stock_main':{'eligible_denominator':0,'positive_fraction':None,'strict_fraction':None,'status':'INSUFFICIENT_CONTRACT_HISTORY'},
        'combined_main':{**primary,'warning':'identical to crypto because no eligible stock contract; not a cross-market success'},
        'both_asset_classes_above_half':False,'observed_crypto_inventory':652,
        'crypto_observed_positive_lower_bound':primary['positive']/652,
        'crypto_observed_positive_upper_bound':(primary['positive']+652-primary['n'])/652,
        'full_cost_effectiveness':'UNVERIFIED; zero full-calendar main windows and no full historical identity review'}
    save(out/'population-verdict.json',population)
    validation=[]
    for label,condition in [('middle',df.asset_fold.between(60,79)),('held',df.asset_fold>=80)]:
        g=df[df.window.eq(label)&condition&df.asset_class.eq('COIN')&df.full_requested_window]
        for c,x in g.groupby('candidate'):validation.append({'split':label,'candidate':c,**fractions(x)})
    pd.DataFrame(validation).to_csv(out/'isolated-validation.csv',index=False)
    # Annual pairs on exactly the same fully observable symbol-years.
    pairs=[]
    for window in ['main']+[str(y) for y in range(2020,2027)]:
        g=df[df.window.eq(window)&df.asset_class.eq('COIN')&df.full_requested_window]
        wide=g.pivot(index='symbol',columns='candidate',values='return_pct').reindex(columns=['B2','B3','C1','C2','C4','C5'])
        for a,b,label in [('B3','B2','mechanical_reversal_vs_wait_stop'),('C4','C5','same_open_reversal_vs_flat_day'),('C1','C2','hold_until_confirm_vs_early_flat')]:
            delta=(wide[a]-wide[b]).dropna();lo,hi=wilson(int((delta>0).sum()),len(delta))
            pairs.append({'window':window,'comparison':label,'a':a,'b':b,'n':len(delta),'improved':int((delta>0).sum()),
                'fraction_improved':(delta>0).mean(),'median_return_delta_pp':delta.median(),'improved_wilson95_lo':lo,'improved_wilson95_hi':hi})
    pd.DataFrame(pairs).to_csv(out/'reversal-paired.csv',index=False)
    filtered=[]
    for label in ['main','development','middle','held']:
        g=ap[ap.window.eq(label)]
        if label in ['middle','held']:g=g[g.full_requested_window]
        for variant,x in g.groupby('variant'):
            base=g[g.variant.eq('unfiltered')][['symbol','return_pct','strict']].rename(columns={'return_pct':'base_return','strict':'base_strict'})
            paired=x.merge(base,on='symbol',validate='one_to_one')
            selected=x[x.n_trades>0]
            filtered.append({'window':label,'variant':variant,**fractions(x),'selected_assets':len(selected),
                'selected_asset_fraction':len(selected)/len(x),'mean_time_coverage':x.filter_time_coverage.mean(),
                'median_paired_increment_pp':(paired.return_pct-paired.base_return).median(),
                'strict_increment':int(paired.strict.sum()-paired.base_strict.sum()),
                'selected_positive':int((selected.return_pct>0).sum()),
                'selected_positive_fraction':(selected.return_pct>0).mean(),
                'rejected_signals':int(x.rejected_signals.sum()),'stress_positive_assets':int((x.stress_return_pct>0).sum())})
    pd.DataFrame(filtered).to_csv(out/'filter-and-sensitivity.csv',index=False)
    # Keep all trades but regress only nonoverlapping available-segment runs of the locked mechanism.
    chosen=[]
    for chunk in pd.read_csv(ev/'trades.csv.gz',chunksize=100000):
        chosen.append(chunk[chunk.window.eq('available_segment')&chunk.candidate.eq(candidate)&chunk.asset_class.eq('COIN')&chunk.reason.ne('end_of_test')])
    trades=pd.concat(chosen,ignore_index=True);trades['signal_close']=np.nan
    manifest=json.loads((INPUT/'frame-manifest.json').read_text());btc=btc_reference(manifest)
    for symbol,ids in trades.groupby('symbol').groups.items():
        lookup={str(g.research_segment_id.iloc[0]):g for g in groups(symbol,manifest,btc)}
        for idx in ids:
            row=trades.loc[idx];g=lookup[str(row.segment_id)]
            j=int(row.signal_idx);assert str(g.ts.iloc[j])==row.signal_ts
            trades.loc[idx,'signal_close']=g.close.iloc[j]
    trades['x_relative']=trades.side*trades.relative60
    trades['x_slow']=trades.side*(trades.signal_close-trades.ma30)/(trades.atr_pct*trades.signal_close)
    trades['x_liquidity']=np.log10(trades.liquidity90)
    trades['x_volatility']=trades.atr_pct
    trades['x_persistence']=trades.er30
    trades['x_maturity']=np.log1p(trades.age_days)
    xcols=['x_relative','x_slow','x_liquidity','x_volatility','x_persistence','x_maturity']
    finite=np.isfinite(trades[xcols]).all(axis=1)
    split=split_trades(trades[finite]);dev=split['development'];means=dev[xcols].mean();std=dev[xcols].std().replace(0,np.nan)
    coefs=[];split_audit={}
    for label,g in split.items():
        g=g.copy();g['year']=pd.to_datetime(g.signal_ts,utc=True).dt.year;g['month']=pd.to_datetime(g.signal_ts,utc=True).dt.strftime('%Y-%m')
        x=(g[xcols]-means)/std;x['side']=g.side
        x=pd.concat([x,pd.get_dummies(g.year.astype(str),prefix='year',drop_first=True,dtype=float)],axis=1)
        x=x.astype(float);x.insert(0,'const',1.);y=g.ret_pct.astype(float)
        beta,cov,r2=clustered_ols(x,y,g.symbol,g.month)
        se=np.sqrt(np.where(np.diag(cov)>0,np.diag(cov),np.nan));dof=max(1,min(g.symbol.nunique(),g.month.nunique())-1)
        for col in xcols:
            j=x.columns.get_loc(col);coef=beta[j];st=se[j];pvalue=2*student_t.sf(abs(coef/st),dof) if st>0 else np.nan
            critical=student_t.ppf(.975,dof)
            coefs.append({'split':label,'feature':col,'coefficient_pp_per_dev_sd':coef,'cluster_se':st,'p_value':pvalue,
                'ci95_lo':coef-critical*st,'ci95_hi':coef+critical*st,'trades':len(g),'assets':g.symbol.nunique(),'months':g.month.nunique()})
        split_audit[label]={'trades':len(g),'assets':sorted(g.symbol.unique()),'first_signal':g.signal_ts.min(),'last_exit':g.exit_ts.max(),'r_squared':r2,'rank':np.linalg.matrix_rank(x),'columns':len(x.columns)}
    coef=pd.DataFrame(coefs);coef['bh_q_18']=bh_qvalues(coef.p_value.fillna(1));coef.to_csv(out/'controlled-feature-associations.csv',index=False)
    sets=[set(v['assets']) for v in split_audit.values()];assert all(not sets[i]&sets[j] for i in range(3) for j in range(i))
    save(out/'split-and-regression-audit.json',{'splits':split_audit,'natural_trades_total':len(trades),'feature_missing_excluded':int((~finite).sum()),
        'purged_or_outside_splits':int(finite.sum()-sum(len(g) for g in split.values())),
        'train_means':means.to_dict(),'train_sd':std.to_dict(),'inference':'two-way asset/month cluster covariance; six features plus year and direction; no predictive or trading rule fitted'})
    state=trades.assign(year=pd.to_datetime(trades.signal_ts,utc=True).dt.year).groupby(['year','market_state','side','reversal_entry']).agg(
        n=('ret_pct','size'),mean_trade_return_pct=('ret_pct','mean'),median_trade_return_pct=('ret_pct','median'),bankruptcies=('economic_bankruptcy','sum')).reset_index()
    state.to_csv(out/'direction-regime-trades.csv',index=False)
    # Clustered exploratory uncertainty: resample assets and circular blocks of three calendar months.
    monthly=pd.read_csv(apath/'monthly-returns.csv.gz');monthly=monthly[monthly.window.eq('main')]
    base=monthly[monthly.variant.eq('unfiltered')].pivot(index='symbol',columns='month',values='month_return').sort_index(axis=0).sort_index(axis=1)
    rng=np.random.default_rng(20260908);boot=[];n,m=base.shape
    for variant,g in monthly.groupby('variant'):
        a=g.pivot(index='symbol',columns='month',values='month_return').reindex(index=base.index,columns=base.columns).to_numpy()
        assert np.isfinite(a).all();values=[];increments=[]
        for k in range(500):
            assets=rng.integers(0,n,n);starts=rng.integers(0,m,math.ceil(m/3));months=np.concatenate([(s+np.arange(3))%m for s in starts])[:m]
            rr=np.prod(1+a[assets][:,months],axis=1)-1;br=np.prod(1+base.to_numpy()[assets][:,months],axis=1)-1
            values.append(np.mean(rr>0));increments.append(np.median(rr-br)*100)
        boot.append({'variant':variant,'bootstrap_runs':500,'asset_resampling':True,'month_block':3,
            'positive_fraction_ci95_lo':np.quantile(values,.025),'positive_fraction_ci95_hi':np.quantile(values,.975),
            'median_increment_ci95_lo_pp':np.quantile(increments,.025),'median_increment_ci95_hi_pp':np.quantile(increments,.975)})
    pd.DataFrame(boot).to_csv(out/'asset-month-block-bootstrap.csv',index=False)
    stocks=df[df.window.eq('available_segment')&df.symbol.str.split('/').str[0].isin(['AMZN','COIN','CRCL','HOOD','INTC','MSTR','PLTR','TSLA'])]
    stocks.to_csv(out/'eight-stock-short-history.csv',index=False)
    save(out/'completed.json',{'status':'ANALYSIS_COMPLETE','candidate':candidate,'input_result_sha256':sha(ev/'results.csv'),
        'applicability_result_sha256':sha(apath/'results.csv'),'source_sha256':sha(Path(__file__)),
        'no_candidate_reselection':True,'all_funding_claims_unverified':True})
    print('STATISTICS DONE',out)

if __name__=='__main__':main()
