import os
"""Independent source/label and hybrid-surface audits; no repaired old artifact writes."""
import json,hashlib,importlib.util,sys
from pathlib import Path
import pandas as pd,numpy as np
F=Path(__file__).resolve().parents[1];A=Path(os.environ.get('TPSA_R0_OUTPUT',str(F/'artifacts')));S=Path('/Users/ZK/OpenCode/quant-strategy-lab');C=json.loads((F/'specs/frozen-config.json').read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(name,v):(A/name).write_text(json.dumps(v,indent=2,default=str))
pd.set_option('mode.chained_assignment','raise')
p=pd.read_parquet(A/'verified_price_frames.parquet');e=pd.read_parquet(A/'predictions.parquet')
rows=[]
for s,g in p.groupby('symbol'):
    g=g.sort_values('ts').copy();g['audit_segment']=g.research_segment_id.fillna('INVALID');seg=g.groupby('audit_segment');g['ma7']=seg.close.transform(lambda x:x.rolling(7,min_periods=7).mean());g['prev_close']=seg.close.shift(1);g['prev_ma7']=g.groupby('audit_segment').ma7.shift(1);g['ma7_available']=g.prev_ma7.notna();g['v3_upcross']=g.prev_close.le(g.prev_ma7)&g.close.gt(g.ma7)
    # At least 61 observations including signal row; strict segment restarts on invalid/zero/gap.
    g['v3_pre60_valid']=g.eligible & (g.groupby('audit_segment').cumcount()>=60)
    rows.append(g[['symbol','ts','close','v3_upcross','v3_pre60_valid','ma7_available']])
pv=pd.concat(rows);j=e[['event_id','symbol','event_date','close']].merge(pv,left_on=['symbol','event_date'],right_on=['symbol','ts'],how='left',suffixes=('_old','_v3'))
j['close_relative_difference']=j.close_v3/j.close_old-1;j['exact_close_equal']=j.close_old.eq(j.close_v3);j.to_parquet(A/'hybrid_price_event_audit.parquet',index=False)
dump('hybrid_price_event_audit.json',{'events':len(j),'v3_day_missing':int(j.close_v3.isna().sum()),'exact_close_equal':int(j.exact_close_equal.sum()),'relative_difference_above_1e8':int(j.close_relative_difference.abs().gt(1e-8).sum()),'maximum_absolute_relative_close_difference':float(j.close_relative_difference.abs().max()),'v3_cross_false_or_unavailable':int((~j.v3_upcross.fillna(False)).sum()),'v3_cross_false_when_ma_available':int((j.ma7_available.fillna(False)&~j.v3_upcross.fillna(False)).sum()),'v3_ma7_unavailable':int((~j.ma7_available.fillna(False)).sum()),'v3_pre60_unproven_in_requested_slice':int((~j.v3_pre60_valid.fillna(False)).sum()),'warmup_boundary_note':'price request begins 2025-01-01; first60 days cannot verify old feature window against v3 in this slice; false/unavailable separated in row artifact; no dropping or fixing events to improve account','all_events_use_old_tpsa_feature_surface':True})
# Recompute original features/labels for three symbols from historical cache, independent from model predictions.
source=S/'research/asset-portfolios/1d-trend-prebreakout-state-atlas/scripts/run_binance_1d_trend_prebreakout_state_atlas_p0.py';spec=importlib.util.spec_from_file_location('original_tpsa_source',source);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
cache=S/'data/cache/binance-1d-ma7-rc-p3/binance_1d_ma7_rc_p3_daily_panel.parquet';symbols=['BTC/USDT:USDT','ETH/USDT:USDT','DOGS/USDT:USDT'];cachep=pd.read_parquet(cache,filters=[('symbol','in',symbols)]);cachep=cachep[cachep.is_complete_day & cachep.event_date.lt(pd.Timestamp('2026-07-01',tz='UTC'))]
featured=pd.concat([mod.feature_block(g) for _,g in cachep.groupby(['symbol','block_id'])],ignore_index=True)
core=['atr20_pre','atr_pct_pre','raw_return_60_pre_atr','raw_prior_50_return_atr','raw_recent_10_return_atr','raw_location_60','er60_pre','range_ratio_10_60_pre','atr_level_percentile_60_pre','atr_path_percentile_60_pre','rv10_rv60_pre']
featured['eligible_prestate']=np.isfinite(featured[core].astype(float).to_numpy()).all(axis=1)&featured.listing_age_days.ge(120)
rebuilt=mod.build_events(featured);old=pd.read_parquet(C['source_events'],columns=['event_id','symbol','event_date','ma_period','direction','barrier_success_20','atr20_pre','close',*C['features']]);old=old[(old.symbol.isin(symbols))&(old.ma_period==7)&(old.direction=='long')]
r=old.merge(rebuilt,on='event_id',suffixes=('_old','_rebuild'));diff={f:float(np.nanmax(np.abs(r[f+'_old']-r[f+'_rebuild']))) for f in C['features']}
labels=r[['event_id','barrier_success_20_old','barrier_success_20_rebuild']].copy();labels['equal']=labels.iloc[:,1].eq(labels.iloc[:,2])|(labels.iloc[:,1].isna()&labels.iloc[:,2].isna())
manual=[]
for s in symbols:
    ev=old[(old.symbol==s)&old.barrier_success_20.notna()].sort_values('event_date').iloc[len(old[(old.symbol==s)&old.barrier_success_20.notna()])//2]
    bars=cachep[cachep.symbol.eq(s)].sort_values('event_date');future=bars[bars.event_date.gt(ev.event_date)].head(20);base=float(ev.close);atr=float(ev.atr20_pre);good=next((i+1 for i,c in enumerate(future.close) if c>=base+2*atr),None);bad=next((i+1 for i,c in enumerate(future.close) if c<=base-atr),None);success=int(good is not None and (bad is None or good<bad))
    manual.append({'event_id':ev.event_id,'base_close':base,'atr_pre':atr,'upper':base+2*atr,'lower':base-atr,'future_closes':future.close.tolist(),'first_upper_session':good,'first_lower_session':bad,'manual_label':success,'saved_label':int(ev.barrier_success_20),'equal':success==ev.barrier_success_20})
dump('original_feature_label_audit.json',{'source_feature_script':str(source),'source_feature_script_sha256':sha(source),'source_cache':str(cache),'source_cache_sha256':sha(cache),'original_event_sha256':C['source_events_sha256'],'symbols':symbols,'source_bars':len(cachep),'old_ma7_long_events':len(old),'rebuilt_matches':len(r),'feature_max_abs_differences':diff,'label_mismatches':int((~labels.equal).sum()),'manual_examples':manual,'scope':'three original-source symbols; not whole-pool same-source migration or prospective pipeline validation'})
print('source/execution audits saved')
