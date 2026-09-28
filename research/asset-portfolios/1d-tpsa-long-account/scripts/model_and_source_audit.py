import os
import sys,json,hashlib,platform,importlib.util
from pathlib import Path
import pandas as pd,numpy as np,joblib,lightgbm,sklearn
from lightgbm import LGBMClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score,brier_score_loss
F=Path(__file__).resolve().parents[1]; A=Path(os.environ.get('TPSA_R0_OUTPUT',str(F/'artifacts'))); C=json.loads((F/'specs/frozen-config.json').read_text()); S=Path('/Users/ZK/OpenCode/quant-strategy-lab'); OLD=S/'research/asset-portfolios/1d-trend-prebreakout-state-atlas'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(name,v):(A/name).write_text(json.dumps(v,indent=2,default=str))
assert sha(C['source_events'])==C['source_events_sha256']
cols=['event_id','symbol','event_date','outcome_end_date_20','ma_period','direction','barrier_success_20','atr20_pre','close',*C['features']]
e=pd.read_parquet(C['source_events'],columns=list(dict.fromkeys(cols)))
e=e[(e.ma_period==7)&(e.direction=='long')].copy()
cut=pd.Timestamp('2025-01-01',tz='UTC')
train=e[e.outcome_end_date_20.lt(cut)&e.barrier_success_20.notna()].copy()
test=e[e.event_date.ge(cut)].copy()
imp=SimpleImputer(strategy='median');x=imp.fit_transform(train[C['features']]);m=LGBMClassifier(**C['model']);m.fit(pd.DataFrame(x,columns=C['features']),train.barrier_success_20.astype(int))
test['probability']=m.predict_proba(pd.DataFrame(imp.transform(test[C['features']]),columns=C['features']))[:,1]
test['priority']=test.event_id.map(lambda v:hashlib.sha256(str(v).encode()).hexdigest());test['hash20_selected']=test.priority.map(lambda v:int(v,16)/2**256<.20)
joblib.dump({'model':m,'imputer':imp,'features':C['features'],'training_cutoff':str(cut),'config_sha256':sha(F/'specs/frozen-config.json')},A/'new_frozen_model.joblib')
m.booster_.save_model(str(A/'new_frozen_model.txt'))
dump('preprocessing.json',{'feature_names':C['features'],'median_statistics':imp.statistics_.tolist(),'training_cutoff':str(cut),'infinite_handling':'error; source finite audit','model_parameters':C['model']})
reload=joblib.load(A/'new_frozen_model.joblib');rp=reload['model'].predict_proba(pd.DataFrame(reload['imputer'].transform(test[C['features']]),columns=C['features']))[:,1]
assert np.array_equal(rp,test.probability.values)
test.to_parquet(A/'predictions.parquet',index=False)
origpath=OLD/'artifacts/binance_1d_tpsa_p1_barrier_ml_predictions.parquet'
orig=pd.read_parquet(origpath);orig=orig[(orig.ma_period==7)&(orig.direction=='long')&(orig.model=='LIGHTGBM')]
orig=orig[orig.event_date.ge(cut)&orig.event_date.lt(pd.Timestamp('2026-01-01',tz='UTC'))]
pairs=test[['event_id','probability']].merge(orig[['event_id','probability']],on='event_id',suffixes=('_new','_old'))
year_metrics=[]
for y,g in test[test.barrier_success_20.notna()].groupby(test.event_date.dt.year):
    yy=g.barrier_success_20.astype(int);selected=g[g.probability.ge(.40)];year_metrics.append({'year':int(y),'events':len(g),'auc':roc_auc_score(yy,g.probability),'brier':brier_score_loss(yy,g.probability),'base_label_success':yy.mean(),'selected_count':len(selected),'selected_label_success':selected.barrier_success_20.mean()})
overlap=e.sort_values(['symbol','event_date']).groupby('symbol').apply(lambda z:(z.event_date.shift(-1)<=z.outcome_end_date_20).sum(),include_groups=False).sum()
audit={'train_count':len(train),'train_max_event':train.event_date.max(),'train_max_label_end':train.outcome_end_date_20.max(),'test_count':len(test),'test_label_missing':int(test.barrier_success_20.isna().sum()),'duplicate_event_ids':int(e.event_id.duplicated().sum()),'duplicate_symbol_dates':int(e.duplicated(['symbol','event_date']).sum()),'train_test_event_id_intersection':len(set(train.event_id)&set(test.event_id)),'train_label_end_before_test':bool(train.outcome_end_date_20.lt(cut).all()),'overlapping_next_same_symbol_20d_events':int(overlap),'infinite_train_values':int(np.isinf(train[C['features']].to_numpy()).sum()),'train_missing_feature_cells':int(train[C['features']].isna().sum().sum()),'new_model_reload_maxdiff':float(np.max(abs(rp-test.probability.values))),'original_2025_prediction_comparison_count':len(pairs),'original_2025_prediction_max_abs_diff':float(abs(pairs.probability_new-pairs.probability_old).max()),'original_prediction_sha256':sha(origpath),'identity':'newly saved R0 object; overlap comparison does not recreate a missing original final object or prove input lake quality','year_metrics':year_metrics,'environment':{'python':sys.version,'platform':platform.platform(),'pandas':pd.__version__,'numpy':np.__version__,'lightgbm':lightgbm.__version__,'sklearn':sklearn.__version__,'joblib':joblib.__version__}}
dump('model_audit.json',audit)
print(json.dumps(audit,default=str,indent=2))
