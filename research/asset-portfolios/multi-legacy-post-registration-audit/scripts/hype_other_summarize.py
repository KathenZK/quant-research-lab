from pathlib import Path
import json,hashlib
import pandas as pd
D=Path(__file__).resolve().parents[1]/'artifacts/hype_other'; ROOT=Path(__file__).resolve().parents[4]
inv=json.loads((D/'inventory.json').read_text()); rows=[]
for family in inv['rows']:
 for case in family['cases']:
  p=D/case/'summary.json'
  if not p.exists():continue
  s=json.loads(p.read_text());m=s['metrics']; originals=[]
  for k in ['max_drawdown','max_dd']:
   if k in m:originals.append(abs(float(m[k])))
  for k in ['max_drawdown_pct','max_drawdown_net_pct']:
   if k in m:originals.append(abs(float(m[k]))/100)
  dd=max([abs(s['curve_close_drawdown']),*originals]); s['audit_drawdown']=dd
  s['replay_script_sha256']=hashlib.sha256((ROOT/'research/asset-portfolios/multi-legacy-post-registration-audit/scripts/hype_other_replay.py').read_bytes()).hexdigest()
  s['funding_coverage_verified']=False;s['cost_contract']={'fee_per_fill_or_turnover':.001,'adverse_slippage':.0004}
  if 'funding_model' not in s:s['funding_model']='source engine original event/bar or entry-notional semantics; observed-event estimate only'
  s['family_count_unit']=family['family']
  s['variant_role']='coequal_predeclared_observation_no_selected_winner' if len(family['cases'])>1 else 'single_named_frozen_observation'
  s['number_of_equal_variants_in_family']=len(family['cases'])
  s['registered_latest_version']=case in ['ar_v4','keltner_v3','mmtf_1h_v3','mmtf_15m_v3','mdtp_v1']
  s['trade_count_unit']='directional_entries; rebalance fills separately in metrics' if case.startswith('mhef_1h') else 'closed_trades_or_campaigns'
  p.write_text(json.dumps(s,ensure_ascii=False,indent=2,default=str))
  trades=m.get('trades',m.get('campaigns',m.get('closed_trades')))
  if trades is None and 'directional_entries' in m:trades=m['directional_entries']
  rows.append({'family':family['family'],'case':case,'version':s['version'],'freeze_date':family['freeze_date'],'start':s['start'],'end':s['end'],'return_pct':100*s['curve_return'],'drawdown_pct':100*dd,'curve_drawdown_pct':100*abs(s['curve_close_drawdown']),'trades_or_directional_entries':trades,'trade_count_unit':s['trade_count_unit'],'variant_role':s['variant_role'],'funding':'observed estimate only','summary':str(p.relative_to(ROOT))})
pd.DataFrame(rows).to_csv(D/'results.csv',index=False)
(D/'summary.json').write_text(json.dumps({'assigned_families':21,'replayed_families':len(set(x['family'] for x in rows)),'rows_are_not_distinct_strategies':True,'results':rows,'remaining':[x for x in inv['rows'] if not x['replay_artifacts_present']]},ensure_ascii=False,indent=2))
print('families',len(set(x['family'] for x in rows)),'rows',len(rows))
