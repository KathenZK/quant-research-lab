from pathlib import Path
import json,pandas as pd,numpy as np
O=Path('/tmp/three-line-b-recalc-20260909');A=Path('/Users/ZK/.codex/worktrees/5f41/quant-strategy-lab/research/asset-portfolios/1d-tpsa-long-account/artifacts')
s=pd.read_csv(O/'independent_event_shadow.csv',parse_dates=['event_date']);tr=pd.read_csv(A/'ML_p040/trades.csv');tr['signal_date']=pd.to_datetime(tr.signal_date,utc=True)
ad=s.merge(tr[['event_id','entry_notional']],on='event_id');sel=s[s.selected]
def values(sel,ad):
    a=sel[sel.label.notna()];b=ad[ad.label.notna()];g=a.groupby('event_date').label.agg(['mean','size']);n=b.groupby('event_date').size()
    return {'selected_events':len(sel),'selected_label_n':len(a),'selected_success_count':int(a.label.sum()),'selected_success_rate':float(a.label.mean()),'selected_dates':len(g),'selected_date_equal_success_rate':float(g['mean'].mean()),'admitted_events':len(ad),'admitted_label_n':len(b),'admitted_success_count':int(b.label.sum()),'admitted_success_rate':float(b.label.mean()),'admitted_dates':len(n),'selected_success_actual_admission_date_weighted':float((n*g.loc[n.index,'mean']).sum()/n.sum()),'formula':'sum_d(n_admitted_labeled_d * mean(label | candidate p>=0.4, same signal date d, label available)) / sum_d n_admitted_labeled_d','availability':'Both populations require original barrier_success_20 non-null. No old-label imputation. Shadow resolved eligibility is separately reported, not mixed into primary original-label decomposition.'}
out={'full':values(sel,ad),'resolved_only_sensitivity':values(sel[sel.status.eq('RESOLVED')],ad[ad.status.eq('RESOLVED')]),'by_year':{},'missing_admitted_labels':ad[ad.label.isna()][['event_id','event_date','exit_time','reason']].to_dict('records')}
for y in [2025,2026]:out['by_year'][str(y)]=values(sel[sel.event_date.dt.year.eq(y)],ad[ad.event_date.dt.year.eq(y)])
e=pd.read_parquet(A/'predictions.parquet');q=pd.read_csv(A/'ML_p040/account_equity.csv');q['time']=pd.to_datetime(q.time,utc=True)
previous=q[q.valuation_type.eq('DAILY_CLOSE')].set_index('time').equity_ex_actual_funding
t=tr.merge(e[['event_id','close']],on='event_id');t['entry_time']=pd.to_datetime(t.entry_time,utc=True);t['expected_qty']=t.apply(lambda r:.2*float(previous.loc[r.entry_time])/r.close,axis=1)
out['quantity_from_previous_close_equity_max_error']=float(abs(t.qty-t.expected_qty).max())
out['no_optimization']='No capacity/priority/threshold variants added. Date weights use realized admissions and are attribution only, not executable policy.'
(O/'admission_decomposition.json').write_text(json.dumps(out,indent=2,default=str));print(json.dumps(out,indent=2,default=str))
