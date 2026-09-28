"""All-coin opportunity tables and separate account comparisons. No fitted rules."""
import json
from pathlib import Path
import time
import numpy as np
import pandas as pd
from v3_opportunity_study_20260913 import *
from v3_opportunity_inputs_20260913 import load_sources, table

EVENTS={'crosses':'全部MA7穿越','natural_exits':'原V3自然退出后','stagnation4':'四日停滞开始收紧后','short_tp':'原空单提前止盈后'}
FEATURES=['efficiency20_bin','cross20_bin','wick20_bin','initial_risk_bin','ma30_bin']

def records(d):return json.loads(d.to_json(orient='records',date_format='iso',double_precision=15))
def ratio(a,b):return float(a/b) if b else None
def finite(x):return float(x) if pd.notna(x) and np.isfinite(x) else None
def read_checked(directory,rel,kind='csv'):
    p=Path(directory)/rel;m=json.loads((Path(directory)/'artifact_checksums.json').read_text());assert sha(p)==m[rel]
    return pd.read_parquet(p) if kind=='parquet' else table(p)

def trade_stats(t,a,b,hi):
    if len(t):
        q=t[(t.exit_time>=a)&((t.exit_time<b)|((t.exit_time==b)&t.exit_reason.eq('sample_end')&(b==hi)))]
        involved=t[(t.entry_time<b)&((t.exit_interval_end>a)|(t.exit_time==a))]
        u=q.return_on_entry_equity; pnl=q.net_pnl; w=pnl[pnl>0];l=-pnl[pnl<0]
        return {'closed_trades':len(q),'participating_trades':len(involved),'terminal_trades':int(q.exit_reason.eq('sample_end').sum()),
                'win_rate_pct':ratio(len(w)*100,len(q)),'payoff_ratio':ratio(w.mean(),l.mean()) if len(w) and len(l) else None,
                'unit_payoff_ratio':ratio(u[u>0].mean(),-u[u<0].mean()) if (u>0).any() and (u<0).any() else None,
                'profit_factor':ratio(w.sum(),l.sum()),'closed_trade_net_pnl':pnl.sum(),'mean_unit_return_pct':u.mean()*100}
    return {'closed_trades':0,'participating_trades':0,'terminal_trades':0,'win_rate_pct':None,'payoff_ratio':None,'unit_payoff_ratio':None,'profit_factor':None,'closed_trade_net_pnl':0,'mean_unit_return_pct':None}

def accounts(sources,out):
    base=read_checked(R/'inputs','baseline_summary.csv'); blocks=read_checked(R/'inputs','baseline_blocks.csv')
    ss=[base]; bb=[blocks]
    for arm in ['E_STATE','TP_PROTECT']:
        ss.append(read_checked(R/'accounts'/arm,'summary.csv'));bb.append(read_checked(R/'accounts'/arm,'blocks.csv'))
    s=pd.concat(ss,ignore_index=True);b=pd.concat(bb,ignore_index=True);grouped={k:g for k,g in b.groupby(['run_key','case_id'])}
    manifests={arm:json.loads((R/'accounts'/arm/'artifact_checksums.json').read_text()) for arm in ['E_STATE','TP_PROTECT']}
    rows=[];alltrades=[]
    for i,a in enumerate(s.itertuples(),1):
        arm=a.case_id;key=a.run_key;info=sources[key]
        path=ROOT/info['baseline_dir'] if arm=='V3' else R/'accounts'/arm/'runs'/key/arm/'full'
        digest=info['baseline_sha256']['trades.csv'] if arm=='V3' else manifests[arm][str((path/'trades.csv').relative_to(R/'accounts'/arm))]
        assert sha(path/'trades.csv')==digest
        t=table(path/'trades.csv')
        if len(t):
            x=t.copy();x['run_key']=key;x['slug']=info['slug'];x['case_id']=arm;alltrades.append(x)
        lo=pd.Timestamp(a.start);hi=pd.Timestamp(a.end_exclusive)
        full={'block':'full_segment','status':'ORIGINAL_SEGMENT','actual_start':lo,'actual_end':hi,
              'return_pct':a.return_pct,'max_drawdown_pct':a.max_drawdown_pct,'complete_coverage':False}
        for row in [full,*grouped[(key,arm)].to_dict('records')]:
            if row['status']=='NO_OVERLAP':continue
            metrics=trade_stats(t,pd.Timestamp(row['actual_start']),pd.Timestamp(row['actual_end']),hi)
            rows.append({**row,'slug':info['slug'],'run_key':key,'case_id':arm,**metrics})
        if i%600==0:print('Account summaries',i,len(s),flush=True)
    p=pd.DataFrame(rows);keys=['run_key','block','status'];control=p[p.case_id.eq('V3')][keys+['return_pct','max_drawdown_pct']].rename(columns={'return_pct':'baseline_return_pct','max_drawdown_pct':'baseline_max_drawdown_pct'})
    p=p.merge(control,on=keys,validate='many_to_one');p['return_change_pp']=p.return_pct-p.baseline_return_pct
    p['drawdown_reduction_pp']=p.baseline_max_drawdown_pct.abs()-p.max_drawdown_pct.abs()
    sums=[]
    for (period,status,arm),g in p.groupby(['block','status','case_id']):
        common=status=='COMPLETE'
        if common:assert not g.slug.duplicated().any()
        sums.append({'block':period,'status':status,'case_id':arm,'coins':g.slug.nunique(),'segments':len(g),
            'profitable':int(((g.return_pct>1e-10)&g.participating_trades.gt(0)).sum()),'losing':int((g.return_pct< -1e-10).sum()),'zero_trades':int(g.participating_trades.eq(0).sum()),
            'median_return_pct':finite(g.return_pct.median()) if common else None,'median_drawdown_pct':finite(g.max_drawdown_pct.abs().median()) if common else None,
            'median_payoff':finite(g.payoff_ratio.median()) if common else None,'median_unit_payoff':finite(g.unit_payoff_ratio.median()) if common else None,
            'improved':int(g.return_change_pp.gt(1e-10).sum()),'worsened':int(g.return_change_pp.lt(-1e-10).sum()),
            'median_delta_pp':finite(g.return_change_pp.median()) if common else None,'trades':int(g.closed_trades.sum())})
    for name,data in [('segment_accounts',s),('period_accounts',p),('period_summary',pd.DataFrame(sums))]:data.to_csv(out/(name+'.csv'),index=False)
    pd.concat(alltrades,ignore_index=True).to_parquet(out/'all_account_trades.parquet',index=False)
    return p,pd.DataFrame(sums)

def observation_metrics(g,days):
    pre=f'f{days}_';ok=g[g[pre+'complete']].copy();actual=g[g.actual_trade_id.notna()&~g.actual_terminal.fillna(True).astype(bool)]
    percoin=ok.groupby('slug')[pre+'hypothetical_net_return'].mean()
    r={'events':len(g),'coins':g.slug.nunique(),'complete':len(ok),'censored':len(g)-len(ok),
       'positive_fixed_hold':int(ok[pre+'hypothetical_net_return'].gt(0).sum()),
       'mean_fixed_hold_pct':finite(ok[pre+'hypothetical_net_return'].mean()*100),
       'median_fixed_hold_pct':finite(ok[pre+'hypothetical_net_return'].median()*100),
       'equal_coin_mean_fixed_hold_pct':finite(percoin.mean()*100),
       'median_mfe_atr':finite(ok[pre+'mfe_atr'].median()),'median_mae_atr':finite(ok[pre+'mae_atr'].median()),
       'mfe_ge_2atr':int(ok[pre+'mfe_atr'].ge(2).sum()),
       'first2_favorable':int(ok[pre+'first_2atr'].eq('favorable_first').sum()),
       'first2_adverse':int(ok[pre+'first_2atr'].eq('adverse_first').sum()),
       'first2_ambiguous':int(ok[pre+'first_2atr'].eq('same_hour_ambiguous').sum()),
       'first2_neither':int(ok[pre+'first_2atr'].eq('neither').sum()),
       'actual_natural_cases':len(actual),'actual_winners':int(actual.actual_unit_return.gt(0).sum()),
       'actual_mean_unit_return_pct':finite(actual.actual_unit_return.mean()*100)}
    if pre+'old_extreme_recovered' in ok:
        rec=ok[ok[pre+'old_extreme_recovered'].fillna(False).astype(bool)]
        r.update(recovered=len(rec),median_recovery_day=finite(rec[pre+'recovery_first_day'].median()),
                 median_recovery_drawback_lower_atr=finite(rec[pre+'pre_recovery_retrace_lower_atr'].median()),
                 median_recovery_drawback_upper_atr=finite(rec[pre+'pre_recovery_retrace_upper_atr'].median()))
    return r

def diagnostics(sources,out):
    collected={n:[] for n in EVENTS};manifest=json.loads((R/'diagnostics/artifact_checksums.json').read_text())
    for key in sources:
        for name in EVENTS:
            p=R/'diagnostics/segments'/key/(name+'.parquet');assert sha(p)==manifest[str(p.relative_to(R/'diagnostics'))];x=pd.read_parquet(p)
            if len(x):collected[name].append(x)
    dfs={n:pd.concat(parts,ignore_index=True) for n,parts in collected.items()}
    groups=[];coins=[]
    for name,d in dfs.items():
        d.to_parquet(out/(name+'.parquet'),index=False)
        for phase in ['all',*sorted(d.phase.unique())]:
            phaseg=d if phase=='all' else d[d.phase.eq(phase)]
            for side in [0,1,-1]:
                g=phaseg if side==0 else phaseg[phaseg.side.eq(side)]
                dimensions=[('all','all',g)]
                for feature in FEATURES+(['entry_disposition'] if name=='crosses' else []):
                    dimensions.extend((feature,str(v),z) for v,z in g.groupby(feature,dropna=False))
                # Cross disposition is a required stratum for mechanism interpretation.
                if name=='crosses':
                    for disposition,z in g.groupby('entry_disposition'):
                        for feature in FEATURES:
                            dimensions.extend((disposition+'|'+feature,str(v),q) for v,q in z.groupby(feature,dropna=False))
                for feature,value,q in dimensions:
                    for days in [5,10,20]:groups.append({'event_set':name,'phase':phase,'side':side,'feature':feature,'value':value,'days':days,**observation_metrics(q,days)})
        for slug,g in d.groupby('slug'):coins.append({'slug':slug,'event_set':name,**observation_metrics(g,20)})
    pd.DataFrame(groups).to_csv(out/'opportunity_groups.csv',index=False);pd.DataFrame(coins).to_csv(out/'coin_opportunity.csv',index=False)
    return dfs,pd.DataFrame(groups)

def main():
    verify_preconditions()
    for arm in ['E_STATE','TP_PROTECT']:assert json.loads((R/'accounts'/arm/'completion.json').read_text())['complete']
    out=R/'analysis';assert not out.exists();out.mkdir()
    sources=load_sources();p,sums=accounts(sources,out);dfs,g=diagnostics(sources,out)
    write_json(out/'completion.json',{'complete':True,'utc':str(pd.Timestamp.now(tz='UTC')),'new_accounts':1950,'reused_baselines':975,'coins':676,'all_codes':680,'funding_verified':False,'engine_sha256':json.loads(PIN.read_text())['engine_sha256'],'source_script_sha256':sha(Path(__file__))})
    write_json(out/'artifact_checksums.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='artifact_checksums.json'})
    print('Complete opportunity and account tables',flush=True)

if __name__=='__main__':main()
