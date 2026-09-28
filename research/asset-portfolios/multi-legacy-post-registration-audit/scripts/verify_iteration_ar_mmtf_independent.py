"""Independent saved-artifact and original-rule review; no candidate replays/searches."""
from __future__ import annotations
import ast, hashlib, json, re
from pathlib import Path
import numpy as np
import pandas as pd
import iteration_common as inputs

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parents[1]/'artifacts/iteration_comparison_20260911'
GROUP=OUT/'ar_mmtf'
checks=[];errors=[]
def check(name,ok,detail=None):
 row={'check':name,'pass':bool(ok)}
 if detail is not None:row['detail']=detail
 checks.append(row)
 if not ok:errors.append(row)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def literal_assignments(path):
 result={}
 for node in ast.parse(path.read_text()).body:
  if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
   try:result[node.targets[0].id]=ast.literal_eval(node.value)
   except (ValueError,TypeError):pass
 return result
plan=json.loads((GROUP/'cases_plan.json').read_text());cases=plan['cases'];rows=json.loads((GROUP/'results.json').read_text())
check('18_predeclared_versions_54_scenarios',len(cases)==18 and len(rows)==54)
lookup={(c['family'],c['version']):c for c in cases}
check('9_families',len({c['family'] for c in cases})==9)
manifest=json.loads((GROUP/'sources_manifest.json').read_text())['files']
for path,digest in manifest.items():check('frozen_source_sha:'+path,sha(ROOT/path)==digest)
for case in cases:
 spec=ROOT/case['spec'];check('spec_sha:'+case['family']+case['version'],sha(spec)==case['spec_sha256'])
 # Literal JSON blocks are independent of the adapter constructors.
 blocks=re.findall(r'```json\n(.*?)\n```',spec.read_text(),re.S)
 if case['kind']=='ar' and len(blocks)==2:
  fields=0;bad=[]
  for cfg,block in zip(case['configs'],blocks):
   for k,v in json.loads(block).items():
    if k in cfg:
     fields+=1
     if cfg[k]!=v:bad.append([k,cfg[k],v])
  check('spec_literal_json_fields:'+case['family']+case['version'],not bad,{'fields':fields,'mismatches':bad})
 if case['family']=='SOL_1h_AR' and case['version']=='V1':
  values=literal_assignments(spec)
  check('SOL_V1_literal_source_dictionaries',case['configs']==[values['V1_DONCHIAN'],values['V1_BB_REVERT']])
# Spec statements read independently; only active parameters and execution contracts.
expected={
 ('BTC_1h_AR','V1'):[{'style':'keltner_break','indicator_window':20,'band_k':2.5,'min_adx':36.,'min_rvol':.8,'max_atr_bps':200.,'roc_window':24,'min_dir_roc_bps':0.,'htf_mode':'d1','max_aligned_funding_bps':2.,'tp_atr':1.5,'sl_atr':4.,'max_hold_bars':120,'cooldown_bars':6,'fixed_leverage':3.},{'style':'cci_reversal','side_mode':'long','indicator_window':20,'threshold_high':125.,'max_adx':36.,'min_rvol':1.5,'min_atr_bps':50.,'max_atr_bps':300.,'max_dist_ema_bps':1000.,'tp_atr':4.,'sl_atr':1.25,'max_hold_bars':96,'cooldown_bars':24,'fixed_leverage':4.}],
 ('BTC_1h_AR','V4'):[{'indicator_window':20,'band_k':2.,'min_adx':40.,'min_rvol':1.25,'htf_mode':'h4','tp_atr':1.5,'sl_atr':5.,'fixed_leverage':2.4,'max_atr_bps':10000.,'min_dir_roc_bps':-10000.,'max_aligned_funding_bps':10000.,'max_hold_bars':100000,'cooldown_bars':0},{'ema_htf':377,'indicator_window':20,'threshold_high':125.,'max_adx':40.,'min_rvol':1.25,'min_atr_bps':75.,'max_dist_ema_bps':750.,'tp_atr':5.5,'sl_atr':1.5,'max_hold_bars':72,'fixed_leverage':3.5,'max_atr_bps':10000.,'cooldown_bars':0}],
 ('HYPE_1h_AR','V1'):[{'style':'di_cross','ema_htf':89,'min_adx':12.,'max_adx':36.,'min_rvol':2.,'max_atr_bps':250.,'roc_window':24,'min_dir_roc_bps':-200.,'max_dist_ema_bps':750.,'htf_mode':'h12','require_body_dir':True,'max_aligned_funding_bps':8.,'tp_atr':1.5,'sl_atr':4.,'max_hold_bars':18,'fixed_leverage':3.},{'style':'stoch_reversal','indicator_window':21,'threshold_low':25.,'threshold_high':60.,'ema_htf':55,'min_adx':12.,'min_rvol':1.,'min_atr_bps':200.,'max_atr_bps':400.,'max_dist_ema_bps':2500.,'macd_fast':8,'macd_slow':21,'macd_signal':5,'require_macd_turn':True,'sl_atr':4.,'trail_activation_atr':1.,'trail_atr':1.,'max_hold_bars':8,'cooldown_bars':24,'fixed_leverage':2.}],
 ('HYPE_1h_AR','V4'):[{'min_adx':10.,'min_rvol':2.,'max_atr_bps':250.,'htf_mode':'h12','require_body_dir':False,'tp_atr':1.5,'sl_atr':4.5,'max_hold_bars':18,'fixed_leverage':3.},{'indicator_window':21,'threshold_low':25.,'threshold_high':55.,'min_adx':0.,'min_rvol':1.,'min_atr_bps':200.,'max_atr_bps':500.,'macd_fast':8,'macd_slow':55,'macd_signal':5,'require_macd_turn':True,'trail_activation_atr':1.,'trail_atr':1.,'max_hold_bars':8,'cooldown_bars':36,'fixed_leverage':2.}],
 ('BNB_1h_AR','V3'):[{'style':'ema_pullback','ema_fast':55,'ema_slow':144,'pullback_atr':-.25,'ema_htf':377,'max_dist_ema_bps':300.,'min_rvol':1.,'min_atr_bps':50.,'exit_kind':'trailing','sl_atr':5.,'trail_activation_atr':2.,'trail_atr':1.5,'max_hold_bars':240,'cooldown_bars':12,'entry_delay_bars':1,'fixed_leverage':2.5},{'style':'wick_reject','threshold_low':.4,'threshold_high':.75,'band_k':.5,'min_adx':28.,'min_rvol':2.,'htf_mode':'h12','exit_kind':'fixed','tp_atr':1.,'sl_atr':5.,'max_hold_bars':48,'cooldown_bars':24,'entry_delay_bars':1,'fixed_leverage':1.}],
 ('SOL_1h_AR','V3'):[{'style':'donchian_break','side_mode':'both','indicator_window':24,'ema_fast':144,'ema_slow':233,'ema_htf':377,'roc_window':24,'min_dir_roc_bps':100.,'macd_fast':34,'macd_slow':89,'macd_signal':13,'min_adx':36.,'min_rvol':1.,'min_atr_bps':100.,'max_dist_ema_bps':750.,'require_macd_turn':True,'max_aligned_funding_bps':2.,'tp_atr':1.,'sl_atr':4.,'max_hold_bars':72,'cooldown_bars':0,'fixed_leverage':3.},{'style':'vwap_revert','side_mode':'short','indicator_window':48,'band_k':1.25,'ema_htf':89,'htf_mode':'h12','require_body_dir':True,'min_atr_bps':125.,'max_dist_ema_bps':1000.,'max_aligned_funding_bps':1.,'tp_atr':1.5,'sl_atr':1.5,'max_hold_bars':12,'cooldown_bars':3,'fixed_leverage':1.}],
 ('TRX_1h_AR','V3'):[{'macd_fast':34,'macd_slow':89,'macd_signal':13,'ema_htf':89,'roc_window':6,'min_adx':20.,'max_adx':24.,'min_rvol':0.,'max_atr_bps':150.,'min_dir_roc_bps':-100.,'max_dist_ema_bps':10000.,'htf_mode':'h12','require_macd_turn':False,'tp_atr':2.,'sl_atr':5.,'max_hold_bars':120,'cooldown_bars':3,'entry_delay_bars':1,'fixed_leverage':5.},{'side_mode':'both','ema_htf':233,'indicator_window':21,'threshold_low':25.,'threshold_high':90.,'roc_window':3,'max_adx':24.,'min_rvol':1.,'min_dir_roc_bps':-300.,'require_body_dir':True,'sl_atr':6.,'trail_activation_atr':3.,'trail_atr':2.,'max_hold_bars':120,'cooldown_bars':6,'entry_delay_bars':2,'fixed_leverage':3.5}],
}
for key,components in expected.items():
 actual=lookup[key]['configs'];bad=[]
 for i,values in enumerate(components):
  bad.extend([[i,k,actual[i].get(k),v] for k,v in values.items() if actual[i].get(k)!=v])
 check('independent_spec_active_fields:'+str(key),not bad,{'fields':sum(map(len,components)),'mismatches':bad})
# TRX V1's text blocks map directly to the full base config.
c=lookup['TRX_1h_AR','V1'];blocks=re.findall(r'```text\n(.*?)\n```',(ROOT/c['spec']).read_text(),re.S)
for i,block in enumerate(blocks):
 bad=[];count=0
 for line in block.splitlines():
  if '=' not in line:continue
  k,v=line.split('=',1)
  if k=='MACD':
   check('TRX_V1_MACD_periods',[c['configs'][i][k] for k in ('macd_fast','macd_slow','macd_signal')]==[34,89,13]);continue
  try:value=json.loads(v)
  except json.JSONDecodeError:value=v
  count+=1
  if c['configs'][i].get(k)!=value:bad.append([k,c['configs'][i].get(k),value])
 check('TRX_V1_spec_text_component'+str(i),not bad,{'fields':count,'mismatches':bad})
# Frozen MMTF identity hashes and explicit period parameters.
for tf,window in [('15m',96),('1h',48)]:
 engine=(ROOT/f'research/hype/{tf}-multi-mechanism-trend-following/scripts/mmtf_engine.py').read_text()
 check('MMTF_RVOL_original_engine_'+tf,f'shift(1).rolling({window}, min_periods={window}).median()' in engine)
 for v in ('V1','V3'):
  c=lookup[f'HYPE_{tf}_MMTF',v]
  spec=(ROOT/c['spec']).read_text()
  if v=='V1':check('MMTF_V1_exact_original_hash_'+tf,c['config_sha256'] in spec)
  minimum={'mechanism':1,'ema_fast':24,'ema_slow':384,'atr_window':14,'adx_min':26.,'rvol_min':1.,'expansion_min':1.25,'sl_atr':6. if v=='V1' else 8.,'tp_atr':.75,'max_hold_bars':24,'leverage':2. if v=='V1' else 3.} if tf=='15m' else {'mechanism':3,'entry_window':120,'ema_fast':96,'ema_slow':120 if v=='V1' else 168,'atr_window':48,'rvol_min':.75,'expansion_min':2.,'sl_atr':4.,'tp_atr':1.5 if v=='V1' else 1.25,'trail_activation_atr':.75,'trail_atr':2.5 if v=='V1' else 2.,'cooldown_bars':24 if v=='V1' else 18,'leverage':2. if v=='V1' else 2.5}
  check('MMTF_spec_active_parameters_'+tf+v,all(c['config'].get(k)==value for k,value in minimum.items()),minimum)
  matching=[r for r in rows if r['family']==c['family'] and r['version']==v]
  check('MMTF_all_scenes_actual_RVOL_'+tf+v,all(r['details']['feature_assertions']['rvol_window']==window for r in matching))
eq=json.loads((GROUP/'mmtf_v2_equivalence.json').read_text())
check('MMTF_V2_equals_V1_four_declared_checks',len(eq)==4 and all(x['trade_signature_equal'] and x['v1_metrics']==x['v2_metrics'] for x in eq))
for v in ('V2.1','V3'):
 c=lookup['HYPE_30m_Keltner',v];expected_k={'keltner_ema':10,'keltner_atr':10,'keltner_mult':2.,'h1_ema_fast':16,'h1_ema_slow':44,'h1_slope_lag':5,'leverage_atr':84,'atr_target_pct':.027,'min_leverage':0.,'max_leverage':3.,'take_profit_pct':.1,'stop_loss_pct':.025,'max_hold_bars':30}
 check('Keltner_spec_frozen_base_'+v,c['config']==expected_k)
 check('Keltner_V3_only_two_filters_'+v,c['filters']==([] if v=='V2.1' else ['ATR84/entry<=0.0125','directional close location>=0.65']))
funding={a:inputs.load_funding(a) for a in ('HYPE','BTC','ETH','SOL','BNB','TRX')}
ledger_total=0;terminal_total=0
for r in rows:
 key=r['family']+'/'+r['version']+'/'+r['scenario'];case=lookup[r['family'],r['version']]
 t=pd.read_csv(ROOT/r['trades_path']);q=pd.read_csv(ROOT/r['equity_path']);m=pd.read_csv(ROOT/r['monthly_path']);q['ts']=pd.to_datetime(q.ts,utc=True)
 check('window:'+key,pd.Timestamp(r['start'])==pd.Timestamp('2026-07-23T00:00Z') and pd.Timestamp(r['end'])==pd.Timestamp('2026-09-05T15:00Z') and q.ts.iloc[-1]==pd.Timestamp(r['end']))
 check('saved_count:'+key,len(t)==r['trades']);ledger_total+=len(t)
 check('equity_vs_summary:'+key,abs(q.equity.iloc[-1]-1-r['return'])<1e-10 and abs(q.equity_excluding_funding.iloc[-1]-1-r['return_ex_funding'])<1e-10)
 dd=float((q.equity/q.equity.cummax()-1).min());check('drawdown:'+key,abs(dd-r['max_drawdown'])<1e-10)
 check('monthly_compounding:'+key,abs(np.prod(1+m['return'])-q.equity.iloc[-1])<1e-10 and abs(np.prod(1+m.return_excluding_funding)-q.equity_excluding_funding.iloc[-1])<1e-10)
 actual_monthly=q.iloc[1:].groupby((q.ts.iloc[1:]-pd.Timedelta(nanoseconds=1)).dt.strftime('%Y-%m')).equity.last()
 check('month_end_assignment:'+key,np.allclose(actual_monthly.to_numpy(),m.ending_equity.to_numpy(),rtol=0,atol=1e-10))
 if len(t):
  for col in ('signal_ts','entry_ts','exit_ts','funding_until'):t[col]=pd.to_datetime(t[col],utc=True)
  check('nonoverlap:'+key,bool((t.entry_ts.iloc[1:].reset_index(drop=True)>=t.exit_ts.iloc[:-1].reset_index(drop=True)).all()))
  check('actual_fill_notional:'+key,np.allclose(t.quantity*t.entry_price,t.entry_equity*t.leverage,rtol=0,atol=1e-10))
  check('fee_each_fill:'+key,np.allclose(t.entry_fee,.001*t.quantity*t.entry_price,rtol=0,atol=1e-10) and np.allclose(t.exit_fee,.001*t.quantity*t.exit_price,rtol=0,atol=1e-10))
  fixed=r['scenario'].startswith('fixed_1x');check('1x_or_original_allocation:'+key,(np.allclose(t.leverage,1.,rtol=0,atol=1e-12) if fixed else bool((t.leverage>0).all())))
  duration=pd.Timedelta(minutes={'1h':60,'15m':15,'30m':30}[case['timeframe']]);delays=t.entry_delay_bars if 'entry_delay_bars' in t else 1
  check('closed_signal_frozen_entry_delay:'+key,bool((t.entry_ts==t.signal_ts+duration*delays).all()) and bool((t.signal_ts>=pd.Timestamp(r['start'])).all()))
  if case['family']=='TRX_1h_AR' and case['version']=='V3':check('TRX_STOCH_two_bar_delay:'+key,bool((t.loc[t.component==1,'entry_delay_bars']==2).all()))
  flow=t.quantity*t.side*(t.exit_price-t.entry_price)-t.entry_fee-t.exit_fee+t.funding_estimate
  check('independent_linear_contract_account:'+key,np.allclose(flow,t.exit_equity-t.entry_equity,rtol=0,atol=1e-10) and abs(flow.sum()-(q.equity.iloc[-1]-1))<1e-10)
  rates=funding[case['asset']];est=[];counts=[]
  for row in t.itertuples():
   held=rates[(rates.ts>=row.entry_ts)&(rates.ts<row.funding_until)]
   est.append(-row.side*row.entry_equity*row.leverage*float(held.funding_rate.sum()));counts.append(len(held))
  check('declared_funding_estimate_reconciles:'+key,np.allclose(t.funding_estimate,est,rtol=0,atol=1e-10) and list(t.funding_event_count)==counts)
  term=t[t.exit_reason=='terminal'];terminal_total+=len(term)
  check('terminal_exit_fee_and_time:'+key,bool((term.exit_ts==pd.Timestamp(r['end'])).all()) and bool((term.exit_fee>0).all()))
 check('funding_limit_disclosed:'+key,'NOT_VERIFIED_FULL_NET' in r['funding_status'] and 'excluded' in r['funding_event_order_limitation'])
 if r['scenario']=='fixed_1x':
  prefix=pd.read_csv((ROOT/r['equity_path']).with_name('prefix_equity.csv'));prefix['ts']=pd.to_datetime(prefix.ts,utc=True)
  a=q[q.ts<pd.Timestamp('2026-08-15T00:00Z')];b=prefix[prefix.ts<pd.Timestamp('2026-08-15T00:00Z')]
  check('independent_saved_prefix:'+key,a.ts.reset_index(drop=True).equals(b.ts.reset_index(drop=True)) and np.allclose(a.equity,b.equity,rtol=0,atol=1e-10))
# Check selection against frozen versions, rather than return rank.
expected_pairs={family:tuple(c['version'] for c in cases if c['family']==family) for family in {c['family'] for c in cases}}
pairs=json.loads((OUT/'paired_results.json').read_text())
check('14_family_pairs_no_duplicate',len(pairs)==14 and len({p['family'] for p in pairs})==14)
for p in pairs:
 if p['family'] not in expected_pairs:continue
 check('pair_uses_predeclared_versions:'+p['family'],(p['early_version'],p['final_version'])==expected_pairs[p['family']])
 for field,role in [('early','early'),('final','latest')]:
  row=next(r for r in rows if r['family']==p['family'] and r['role']==role and r['scenario']=='fixed_1x')
  check('pair_value_matches_fixed_1x:'+p['family']+field,abs(p[field+'_return']-row['return'])<1e-12 and abs(p[field+'_return_ex_funding']-row['return_ex_funding'])<1e-12)
check('all_global_pair_choices_predeclared',all((p['early_version'],p['final_version'])=={'EMA-X':('V1','V18'),'EMA-TB':('V35','V41'),'MII':('V1','V1.4A'),'ENS':('V35+MII1.3','V2'),'HYPE-CC':('V10','V35')}[p['family']] for p in pairs if p['family'] not in expected_pairs))
payload={'status':'PASS' if not errors else 'FAIL','scope':'independent original-spec/source configuration checks and saved-account arithmetic for nine families; no rerun of 54 full scenarios','families':9,'versions':18,'scenarios':54,'ledger_rows':ledger_total,'terminal_closes':terminal_total,'checks':checks,'errors':errors,'limitations':['AR/MMTF funding uses observed events times fixed entry notional, not current marked quantity notional; exit-bar funding is omitted for unknown intrabar ordering. This differs from EMA/CC estimates and cannot establish exact full net.','Keltner original specs require complete 1m aggregation; this comparison uses complete two-15m and four-15m aggregation. This verifies common-input early/final comparison, not original 1m-input identity.','V2-equivalence acceptance checks saved original-engine evidence, configuration lineage and trade signatures; independent full numerical replay was intentionally not repeated.','All drawdowns are closed-bar marked equity; intrabar worst excursion/liquidation is not established.','All 54 accounts finish flat, so no actual terminal-close trades are present. Final cash is reconciled, but terminal fee assertions have no observed terminal examples.'],'artifact_sha256':{'results':sha(GROUP/'results.json'),'plan':sha(GROUP/'cases_plan.json'),'pairs':sha(OUT/'paired_results.json'),'review_script':sha(Path(__file__))}}
(OUT/'acceptance_ar_mmtf_independent.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':payload['status'],'checks':len(checks),'errors':errors,'ledger_rows':ledger_total,'terminal_closes':terminal_total},ensure_ascii=False,indent=2))
