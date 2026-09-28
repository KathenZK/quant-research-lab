from pathlib import Path
import json
import numpy as np
import pandas as pd
D=Path(__file__).resolve().parents[1]/'artifacts/hype_other'; cutoff=pd.Timestamp('2026-08-15T00:00Z');inv=json.loads((D/'inventory.json').read_text());checks=[]
for family in inv['rows']:
 for case in family['cases']:
  full=D/case
  if not (full/'summary.json').exists():continue
  j=json.loads((full/'summary.json').read_text());m=j['metrics']; curve=pd.read_csv(full/'equity.csv'); curve.ts=pd.to_datetime(curve.ts,utc=True)
  assert np.isfinite(curve.equity).all() and (curve.equity>=0).all()
  assert abs(float(curve.equity.iloc[-1])-(1+j['curve_return']))<1e-12
  expected=None
  for k in ['ending_equity','final_equity','equity_multiple']:
   if k in m:expected=float(m[k]);break
  if expected is None:
   for k in ['total_return','net_return']:
    if k in m:expected=1+float(m[k]);break
  if expected is None:
   for k in ['return_pct','net_return_pct','total_return_pct']:
    if k in m:expected=1+float(m[k])/100;break
  if expected is not None:assert abs(curve.equity.iloc[-1]-expected)<1e-6,(case,curve.equity.iloc[-1],expected)
  trades=pd.read_csv(full/'trades.csv')
  last_account=None
  for column in ['exit_equity','equity_after']:
   if column in trades:last_account=float(trades[column].iloc[-1]);break
  if last_account is not None:assert abs(float(curve.equity.iloc[-1])-last_account)<1e-9,(case,'last closed account')
  monthly=pd.read_csv(full/'monthly.csv');assert abs(float((1+monthly['return']).prod())-float(curve.equity.iloc[-1]))<1e-9
  clock=j['equity_timestamp_semantics'];valuation=curve.ts+pd.Timedelta(minutes=clock['bar_duration_minutes'])
  valuation=valuation.where(curve.ts!=pd.Timestamp(j['end']),pd.Timestamp(j['end']))
  assert valuation.max()==pd.Timestamp(j['end'])
  assert j.get('open_position') is None,(case,'open position remains')
  for column in ['position']:
   if column in curve:assert float(curve[column].iloc[-1])==0
  trade_unit='closed_trades_or_campaigns';count_key='trades' if 'trades' in m else ('campaigns' if 'campaigns' in m else 'closed_trades')
  if case.startswith('mhef_1h'):
   trade_unit='rebalance_fills_including_terminal_close';count_key='rebalance_count'
   assert trades.position.iloc[-1]==0
  assert len(trades)==int(m[count_key]),(case,'count unit mismatch')
  terminal=j.get('terminal_settlement_detail')
  if case.startswith('bksb') and terminal:
   before=terminal['equity_before_exit_cost'];after=terminal['equity_after_exit_cost'];cfg=j['config']
   assert abs(after-before*(1-cfg['adverse_slippage_per_fill'])*(1-cfg['fee_per_fill']*cfg['allocation']))<1e-12
  if case.startswith('mhef_1h'):
   assert terminal['cost_amount']>0 and terminal['position']==0
  source_comparison='PASS_ORIGINAL_ENGINE_METRICS' if expected is not None else 'NOT_APPLICABLE_ORIGINAL_NET_METRIC_NOT_EXPORTED'
  if 'source_engine_metrics_before_terminal' in j:source_comparison='EXPLICIT_TERMINAL_ADAPTER_ADJUSTMENT_SOURCE_METRICS_RETAINED'
  base={'mhef_1h':'mhef_1h','mtpp':'mtpp','mapt':'mapt','keltner15':'keltner15','pktsc':'pktsc'}
  pre=case+'_prefix0815'
  for prefix in base:
   if case.startswith(prefix+'_'):pre=prefix+'_prefix0815'+case[len(prefix):];break
  p=D/pre/'equity.csv'; prefix_pass=None; common_rows=0
  if p.exists():
   b=pd.read_csv(p);b.ts=pd.to_datetime(b.ts,utc=True)
   a=curve.loc[curve.ts<cutoff-pd.Timedelta(hours=1),['ts','equity']].reset_index(drop=True)
   b=b.loc[b.ts<cutoff-pd.Timedelta(hours=1),['ts','equity']].reset_index(drop=True)
   pd.testing.assert_frame_equal(a,b,rtol=1e-9,atol=1e-10);prefix_pass=True;common_rows=len(a)
  checks.append({'case':case,'terminal_curve_matches_replay_summary':'PASS','original_engine_metric_comparison':source_comparison,'last_closed_account_matches_curve':'PASS' if last_account is not None else 'NOT_APPLICABLE_ACCOUNT_COLUMN_NOT_EXPORTED','monthly_returns_compound_to_terminal':'PASS','timestamp_reaches_exact_end':'PASS','prefix_equity_equal':prefix_pass,'prefix_rows':common_rows,'count_unit':trade_unit,'count':len(trades),'terminal_cost_check':'EXPLICIT_ORIGINAL_CLOSE_ADAPTER_VERIFIED' if terminal else 'SOURCE_TERMINAL_CLOSE_BRANCH_OR_ALREADY_FLAT','last_exit_reason':trades.iloc[-1].get('exit_reason',trades.iloc[-1].get('reason',trades.iloc[-1].get('execution_reason'))),'last_exit_ts':trades.iloc[-1].get('exit_ts',trades.iloc[-1].get('ts'))})
# Forecasts require no future outcomes and all fitted labels were already mature.
a=pd.read_csv(D/'pktsc/predictions.csv');b=pd.read_csv(D/'pktsc_prefix0815/predictions.csv')
a=a.loc[pd.to_datetime(a.ts,utc=True)<cutoff].reset_index(drop=True)
pd.testing.assert_frame_equal(a,b,rtol=1e-9,atol=1e-10)
t=pd.read_csv(D/'pktsc/training_windows.csv');assert (pd.to_datetime(t.latest_label_maturity,utc=True)<pd.to_datetime(t.fit_day,utc=True)).all()
(D/'verification_all.json').write_text(json.dumps({'curves':checks,'pktsc_predictions_prefix_equal':True,'pktsc_all_training_labels_strictly_mature':True},indent=2));print('PASS',len(checks),'curves;',sum(x['prefix_equity_equal'] is True for x in checks),'prefixes')
