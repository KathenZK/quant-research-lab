"""Learn small, code-isolated forward-time admission/routing rules from retained episodes."""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeRegressor
import sklearn
from common import BASE,ROOT,sha,write_json
R=BASE/'artifacts/adaptation_20260911'
ARMS=['A_ASSET','B_ENTRY','C_ROUTE','D_JOINT']
ACTIONS=['v3','defense','extension']
CUTS=[pd.Timestamp('2023-01-01',tz='UTC'),pd.Timestamp('2025-01-01',tz='UTC')]
ASSET=['asset_observed_days_capped90','asset_efficiency60','asset_cross_frequency60','asset_return_autocorr60','asset_wick_ratio60','asset_atr_pct_median60','asset_gap_atr_p95_60','asset_log10_quote_volume_median60','asset_cost_to_tr60','asset_v3_closed_count12','asset_v3_mean_return12','asset_v3_pf_bounded12','asset_v3_win_rate12']
ENTRY=['entry_'+s for s in ['slope','previous_slope','slope_deceleration','rsi','ma7_distance_atr','ma30_distance_atr','ma30_slope_atr','body_atr','close_location','favorable_wick_atr','adverse_wick_atr','pre_displacement5_atr','pre_displacement10_atr','pre_displacement20_atr','pre_efficiency20','pre_tr_ratio5_20','pre_cross_count20','signal_stop_distance_pct','btc_return20','btc_return60','btc_ma30_distance']]

def fold(slug):return int(hashlib.sha256(str(slug).strip().upper().encode()).hexdigest(),16)%3

def matrix(frame,columns,medians=None):
    x=frame[columns].apply(pd.to_numeric,errors='raise').astype(float).replace([np.inf,-np.inf],np.nan)
    if medians is None:medians={k:float(x[k].median()) if x[k].notna().any() else 0. for k in columns}
    # Indicator columns are fixed by the declared original features, not test-set observations.
    missing=x.isna().astype(float).to_numpy()
    return np.concatenate([x.fillna(medians).to_numpy(),missing],axis=1).astype('float32'),medians

def paths(tree,features):
    out={}
    def walk(n,p):
        left=tree.children_left[n]
        if left<0:out[str(n)]=p;return
        key=features[tree.feature[n]];threshold=float(tree.threshold[n])
        walk(int(left),p+[{'feature':key,'operator':'<=','threshold':threshold}]);walk(int(tree.children_right[n]),p+[{'feature':key,'operator':'>','threshold':threshold}])
    walk(0,[]);return out

def leaf_advice(g,arm):
    # Each coin contributes its mean episode outcome exactly once.
    by=g.groupby('slug',sort=True)[['u_'+a for a in ACTIONS]].mean()
    means=by.mean();ses=by.std(ddof=1)/math.sqrt(len(by)) if len(by)>1 else means*0
    delta=by.subtract(by.u_v3,axis=0)
    dm=delta.mean();ds=delta.std(ddof=1)/math.sqrt(len(by)) if len(by)>1 else dm*0
    supported=len(g)>=120 and len(by)>=20
    allow=True;action='v3';reason='baseline_no_supported_advantage'
    if not supported:reason='insufficient_leaf_support'
    elif arm in ['A_ASSET','B_ENTRY']:
        if means.u_v3+ses.u_v3<0:allow=False;reason='negative_v3_upper_estimate'
    else:
        if arm=='D_JOINT' and max(float(means['u_'+a]+ses['u_'+a]) for a in ACTIONS)<0:
            allow=False;reason='all_actions_negative_upper_estimate'
        else:
            eligible=[a for a in ACTIONS[1:] if dm['u_'+a]>ds['u_'+a] and means['u_'+a]>means.u_v3]
            if eligible:action=max(eligible,key=lambda a:means['u_'+a]);reason='paired_exit_advantage'
    return {'allow':bool(allow),'action':action,'reason':reason,'rows':len(g),'coins':len(by),'supported':supported,
            'means':{a:float(means['u_'+a]) for a in ACTIONS},'standard_errors':{a:float(ses['u_'+a]) for a in ACTIONS},
            'paired_improvement':{a:float(dm['u_'+a]) for a in ACTIONS},'paired_standard_errors':{a:float(ds['u_'+a]) for a in ACTIONS},
            'coin_outcomes':[{'slug':s,**{a:float(z['u_'+a]) for a in ACTIONS}} for s,z in by.iterrows()]}

def train_one(frame,cutoff,heldout,arm):
    columns=ASSET if arm=='A_ASSET' else ENTRY if arm=='B_ENTRY' else ASSET+ENTRY
    use=frame.ready90 & ~frame.terminal_any & frame.label_end.lt(cutoff) & frame.fold.ne(heldout)
    g=frame.loc[use].copy();mid=f'{cutoff.year}_f{heldout}_{arm}'
    model={'model_id':mid,'cutoff':str(cutoff),'heldout_fold':heldout,'arm':arm,'columns':columns,
           'training_ids':g.case_id.tolist(),'training_slugs':sorted(g.slug.unique()),'training_rows':len(g),'training_coins':g.slug.nunique(),
           'max_training_label_end':str(g.label_end.max()) if len(g) else None,'fallback':len(g)<120 or g.slug.nunique()<20}
    assert not any(fold(s)==heldout for s in model['training_slugs'])
    if model['fallback']:
        model.update(medians={k:0. for k in columns},leaves={'0':{'allow':True,'action':'v3','reason':'insufficient_training_support','rows':len(g),'coins':g.slug.nunique(),'conditions':[]}});return model
    x,medians=matrix(g,columns);targets=['u_v3'] if arm in ['A_ASSET','B_ENTRY'] else ['u_'+a for a in ACTIONS]
    counts=g.groupby('slug').case_id.transform('count');weights=1/counts.to_numpy(float);weights*=len(g)/weights.sum()
    tree=DecisionTreeRegressor(max_depth=3,min_samples_leaf=120,random_state=0,criterion='squared_error')
    tree.fit(x,g[targets].to_numpy(float),sample_weight=weights)
    features=columns+[k+'__missing' for k in columns];leaves=tree.apply(x);cond=paths(tree.tree_,features)
    model.update(medians=medians,feature_names=features,targets=targets,tree={'children_left':tree.tree_.children_left.tolist(),'children_right':tree.tree_.children_right.tolist(),'feature':tree.tree_.feature.tolist(),'threshold':tree.tree_.threshold.tolist(),'n_node_samples':tree.tree_.n_node_samples.tolist(),'weighted_n_node_samples':tree.tree_.weighted_n_node_samples.tolist(),'value':tree.tree_.value.tolist(),'impurity':tree.tree_.impurity.tolist()},leaves={})
    for leaf in np.unique(leaves):
        info=leaf_advice(g.loc[leaves==leaf],arm);info['conditions']=cond[str(leaf)];info['training_ids']=g.loc[leaves==leaf,'case_id'].tolist();model['leaves'][str(leaf)]=info
    # Serialize-and-replay equality is checked on every training row before saving.
    predicted=infer(model,g)
    assert np.array_equal(predicted.leaf_id.to_numpy(),leaves)
    model['training_weight_per_coin_min']=float(pd.DataFrame({'slug':g.slug,'weight':weights}).groupby('slug').weight.sum().min())
    model['training_weight_per_coin_max']=float(pd.DataFrame({'slug':g.slug,'weight':weights}).groupby('slug').weight.sum().max())
    return model

def infer(model,frame):
    if not len(frame):return pd.DataFrame(columns=['model_id','fold','train_cutoff','leaf_id','allow','action','reason','rule_id'],index=frame.index)
    if model['fallback']:leaves=np.zeros(len(frame),dtype=int)
    else:
        x,_=matrix(frame,model['columns'],model['medians']);tr=model['tree'];leaves=np.zeros(len(frame),dtype=int)
        active=np.ones(len(frame),dtype=bool)
        while active.any():
            for node in np.unique(leaves[active]):
                ids=np.flatnonzero(active&(leaves==node));left=tr['children_left'][node]
                if left<0:active[ids]=False;continue
                col=tr['feature'][node];leaves[ids]=np.where(x[ids,col].astype(np.float64)<=float(tr['threshold'][node]),left,tr['children_right'][node])
    rows=[]
    for leaf in leaves:
        advice=model['leaves'][str(leaf)]
        rows.append({'model_id':model['model_id'],'fold':model['heldout_fold'],'train_cutoff':model['cutoff'],'leaf_id':int(leaf),'allow':advice['allow'],'action':advice['action'],'reason':advice['reason'],'rule_id':f"{model['model_id']}_L{leaf}"})
    return pd.DataFrame(rows,index=frame.index)

def schedules(d,slug,models):
    """Generate daily long/short decisions. No outcome columns are consumed here."""
    result={};group=fold(slug);decision=pd.to_datetime(d.timestamp,utc=True)+pd.Timedelta(days=1)
    for arm in ARMS+['U_READY']:
        q=d.copy()
        for side,prefix in [(1,'long'),(-1,'short')]:
            f=pd.DataFrame({k:d[k] for k in ASSET},index=d.index)
            for k in ENTRY:f[k]=d[prefix+'_'+k.removeprefix('entry_')]
            pred=pd.DataFrame({'allow':False,'action':'v3','rule_id':'BEFORE_EVALUATION','model_id':'NONE','fold':group,'train_cutoff':None,'leaf_id':-1,'reason':'before_evaluation'},index=d.index)
            if arm=='U_READY':
                mask=decision.ge(CUTS[0]);pred.loc[mask,['allow','rule_id','reason']]=[True,'U_READY','unfiltered_ready_control']
            else:
                for i,cut in enumerate(CUTS):
                    mask=decision.ge(cut)&(decision.lt(CUTS[i+1]) if i+1<len(CUTS) else True)
                    if mask.any():pred.loc[mask]=infer(models[f'{cut.year}_f{group}_{arm}'],f.loc[mask])
            young=~d.ready90.astype(bool);pred.loc[young,['allow','rule_id','reason']]=[False,'INSUFFICIENT_HISTORY90','insufficient_history90']
            q['admit_'+prefix]=pred.allow.astype(bool);q['route_'+prefix]=pred.action;q['rule_id_'+prefix]=pred.rule_id
            for k in ['model_id','fold','train_cutoff','leaf_id','reason']:q[prefix+'_'+k]=pred[k]
        result[arm]=q
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cases',type=Path,default=R/'cases');ap.add_argument('--output',type=Path,default=R/'learning');args=ap.parse_args()
    source=args.cases;out=args.output;assert not out.exists();assert json.loads((source/'completion.json').read_text())['complete']
    manifest=json.loads((source/'artifact_checksums.json').read_text())
    for rel,v in manifest.items():assert sha(source/rel)==v,rel
    pin=json.loads((BASE/'specs/adaptation-engine-pin-20260911.json').read_text())
    for rel,h in pin['contracts'].items():assert sha(ROOT/rel)==h
    out.mkdir(parents=True)
    write_json(out/'started.json',{'utc':str(pd.Timestamp.now(tz='UTC')),'source_manifest_sha256':sha(source/'artifact_checksums.json'),'source_script_sha256':sha(Path(__file__)),'sklearn_version':sklearn.__version__,'fixed_parameters':{'max_depth':3,'min_samples_leaf':120,'minimum_coins_per_leaf':20,'coin_folds':3,'random_state':0},'contract_pin':json.loads((R/'contract_pin.json').read_text())})
    (out/'source_script.py.txt').write_bytes(Path(__file__).read_bytes())
    df=pd.read_parquet(source/'cases.parquet');assert set(ASSET+ENTRY)<=set(df.columns)
    df['case_id']=df.run_key.astype(str)+'::'+df.source_trade_id.astype(str);assert not df.case_id.duplicated().any();df=df.sort_values('case_id',kind='stable').reset_index(drop=True)
    df['fold']=df.slug.map(fold);df['decision_time']=pd.to_datetime(df.signal_day,utc=True)+pd.Timedelta(days=1)
    for a in ACTIONS:
        df['exit_'+a]=pd.to_datetime(df['exit_'+a],utc=True);assert df['exit_'+a].notna().all(),a
        assert np.isfinite(df['u_'+a].to_numpy(float)).all(),a
    df['label_end']=df[['exit_'+a for a in ACTIONS]].max(axis=1);assert df.label_end.notna().all()
    df['entry_time']=pd.to_datetime(df.entry_time,utc=True);assert df.entry_time.equals(df.decision_time)
    models={};rules=[]
    for cut in CUTS:
        for heldout in range(3):
            for arm in ARMS:
                m=train_one(df,cut,heldout,arm);models[m['model_id']]=m
                for leaf,z in m['leaves'].items():rules.append({'model_id':m['model_id'],'rule_id':m['model_id']+'_L'+leaf,'cutoff':str(cut),'fold':heldout,'arm':arm,**{k:v for k,v in z.items() if k not in ['coin_outcomes','training_ids']}})
    write_json(out/'models.json',models);write_json(out/'rules.json',rules)
    validation=[]
    for cut in CUTS:
        stop=CUTS[CUTS.index(cut)+1] if CUTS.index(cut)+1<len(CUTS) else pd.Timestamp('2026-09-05',tz='UTC')
        for group in range(3):
            g=df[df.fold.eq(group)&df.decision_time.ge(cut)&df.decision_time.lt(stop)].copy()
            for arm in ARMS:
                pred=infer(models[f'{cut.year}_f{group}_{arm}'],g);q=pd.concat([g,pred.drop(columns=['fold'])],axis=1);q['arm']=arm
                q.loc[~q.ready90,['allow','reason','rule_id']]=[False,'insufficient_history90','INSUFFICIENT_HISTORY90']
                q['selected_u']=[float(row['u_'+row['action']]) if row['allow'] else 0. for row in q.to_dict('records')]
                q['delta_u']=q.selected_u-q.u_v3;validation.append(q)
    v=pd.concat(validation,ignore_index=True);v.to_parquet(out/'case_decisions.parquet',index=False)
    # Group summaries describe original-entry episodes, not a tradable combined equity curve.
    rows=[]
    for keys,g in v.groupby(['train_cutoff','arm','rule_id'],dropna=False):
        ok=g[~g.terminal_any&g.ready90];basewin=ok[ok.u_v3>0];baseloss=ok[ok.u_v3<0]
        rows.append(dict(zip(['train_cutoff','arm','rule_id'],keys))|{'cases':len(g),'natural_ready_cases':len(ok),'coins':ok.slug.nunique(),'kept':int(ok.allow.sum()),'rejected':int((~ok.allow).sum()),'baseline_mean_return':float(ok.u_v3.mean()) if len(ok) else None,'selected_mean_return':float(ok.selected_u.mean()) if len(ok) else None,'mean_delta':float(ok.delta_u.mean()) if len(ok) else None,'original_winners':len(basewin),'winners_rejected':int((~basewin.allow).sum()),'winners_turned_loss':int((basewin.selected_u<0).sum()),'original_losers':len(baseloss),'losers_improved':int((baseloss.delta_u>1e-12).sum()),'positive_winner_retention':float(basewin.selected_u.clip(lower=0).sum()/basewin.u_v3.sum()) if len(basewin) else None})
    pd.DataFrame(rows).to_csv(out/'rule_validation.csv',index=False)
    used=df[['case_id','run_key','slug','fold','entry_time','signal_day','label_end','terminal_any','ready90']].copy();used.to_parquet(out/'sample_inventory.parquet',index=False)
    write_json(out/'completion.json',{'complete':True,'models':len(models),'rules':len(rules),'all_cases':len(df),'validation_case_rows':len(v),'training_cutoffs':[str(x) for x in CUTS],'future_prices_used_for_features':False,'target_code_excluded_from_own_training':True})
    write_json(out/'artifact_checksums.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='artifact_checksums.json'})
    print(f'Learning complete: {len(models)} models, {len(rules)} rules, {len(v)} separated validation decisions',flush=True)
if __name__=='__main__':main()
