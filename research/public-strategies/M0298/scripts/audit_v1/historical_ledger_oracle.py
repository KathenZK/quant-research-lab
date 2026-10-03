#!/usr/bin/env python3
"""Shared independent actual-output ledger/metric validation after C0 release."""
import argparse, hashlib, json, resource, sys
sys.dont_write_bytecode=True
from datetime import datetime, timezone
from decimal import Decimal,localcontext
from pathlib import Path
import numpy as np
import pandas as pd
from ledger_decimal_core import verify,D


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--record-id',choices=['M0298','M0304'],required=True);p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));root=a.results;summary=read(root/'summary.json');checks=[]
    assert summary['record_id']==a.record_id and set(summary['results'])=={'base','fee0','fee20','delay2','buyhold'}
    signals=pd.read_csv(root/'signals.csv',float_precision='round_trip')
    assert len(signals)==114336 and np.array_equal(signals.open_time,np.arange(1701388800000,1735689600000,300000))
    ent=signals.enter_long.to_numpy(bool);ext=signals.exit_long.to_numpy(bool)
    for name,r in summary['results'].items():
        nav=pd.read_csv(root/f'{name}-nav.csv',float_precision='round_trip');daily=pd.read_csv(root/f'{name}-daily-nav.csv',float_precision='round_trip');metrics=r['metrics']
        assert len(nav)==105408 and len(daily)==366 and np.array_equal(nav.bar_index,np.arange(8928,114336))
        fee=0 if name=='fee0' else 20 if name=='fee20' else 8;lag=2 if name=='delay2' else 1
        if a.record_id=='M0298':
            fills=read(root/f'{name}-fills.json');orders=read(root/f'{name}-orders.json');dates=nav.open_time//86400000
        else:
            fills=pd.read_csv(root/f'{name}-trades.csv',float_precision='round_trip').to_dict('records');orders=read(root/f'{name}-events.json')['orders'];dates=nav.bar_open_utc.str[:10]
        case=verify(fills,nav.to_dict('records'),fee,2 if a.record_id=='M0298' else 0,metrics,a.record_id)
        for e in fills:
            idx=e.get('signal_index',e.get('signal_bar_index'))
            if idx is not None and pd.notna(idx):
                idx=int(idx);assert int(e['bar_index'])-idx==lag
                if e['side'].lower()=='buy':assert ent[idx] and not ext[idx]
                else:assert ext[idx] and not ent[idx]
            elif e['side'].lower()=='buy':assert name=='buyhold'
        for order in orders:
            side=order['side'].lower()
            if a.record_id=='M0298':
                k=int(order['activation_index']);signal=int(order['signal_index']);state=order['state'];assert order['expires_exclusive']==1701388800000+(k+1)*300000
                assert k-signal==lag and order['time_in_force']=='GTC'
                matching=[e for e in fills if int(e['bar_index'])==k and e['side'].lower()==side and e.get('signal_index')==signal]
                assert len(matching)==(1 if state=='FILLED' else 0)
                assert state in ['FILLED','CANCELLED_TIMEOUT','CANCELLED_SUPERSEDED']
            else:
                state=order['status'];assert state in ['filled','timeout_unfilled','terminal_cancelled','cancelled_by_risk']
                if order.get('order_type')=='market':assert name=='buyhold' and state=='filled' and order['limit'] is None
                else:
                    assert pd.Timestamp(order['timeout_utc'])-pd.Timestamp(order['placed_utc'])==pd.Timedelta(minutes=5)
                    assert int(order['bar_index'])-int(order['signal'])==lag
                fill_id=order.get('fill_event_id')
                if state=='filled':
                    assert fill_id is not None
                    e=fills[int(fill_id)-1];assert e['side'].lower()==side and e['bar_index']==order['bar_index']
        if a.record_id=='M0304':
            gates=read(root/f'{name}-events.json')['profit_gates']
            for g in gates:
                f=D(fee)/10000;pr=D(g['decision_quote'])*(1-f)/(D(g['entry_fill'])*(1+f))-1
                assert g['allowed']==(pr>D(g['strict_offset']))
            assert len(gates)==metrics['signal_exit_gate_checks'] and sum(not g['allowed'] for g in gates)==metrics['signal_exit_gate_denials']
            assert metrics['trailing_activations']==0
        expected_daily=nav.assign(_date=dates).groupby('_date',sort=True).tail(1)
        assert np.array_equal(expected_daily.bar_index.to_numpy(),daily.bar_index.to_numpy())
        assert np.array_equal(expected_daily.equity.to_numpy(),daily.equity.to_numpy())
        with localcontext() as ctx:
            ctx.prec=50
            values=[D(100000)]+list(map(D,daily.equity));returns=[values[i]/values[i-1]-1 for i in range(1,len(values))]
            mean=sum(returns)/len(returns);var=sum((x-mean)**2 for x in returns)/(len(returns)-1)
            sharpe=mean/var.sqrt()*D(365).sqrt() if var else None
            if sharpe is None:assert metrics['sharpe_daily'] is None
            else:assert abs(D(metrics['sharpe_daily'])-sharpe)<D('0.000000001')
            annual=(D(nav.equity.iloc[-1])/100000)**(D(365)/366)-1
            assert abs(D(metrics['annualized_return'])-annual)<D('0.000000001')
        assert all(np.isfinite(v) for v in metrics.values() if isinstance(v,(int,float)))
        assert metrics['observations']==105408 and metrics['daily_observations']==366
        assert metrics.get('closed_trades',metrics.get('completed_roundtrips'))==sum(e['side'].lower()=='sell' for e in fills)
        case.update({'case':name,'orders_checked':len(orders),'all_signal_events_closed_and_correct':True,'fullbar_MDD_verified':True,'daily_selection_and_Decimal_Sharpe_verified':True,'annualized_365_over_366_verified':True,'finite_metrics':True})
        checks.append(case)
    out={'schema':'independent-historical-event-ledger-metrics-audit/v1','record_id':a.record_id,'status':'PASS_ALL_ACTUAL_FILL_BAR_LEDGER_AND_METRICS',
         'at_utc':datetime.now(timezone.utc).isoformat(),'summary_sha256':sha(root/'summary.json'),'checks':checks,
         'historical_strategy_configurations_verified':4,'historical_same_window_controls_verified':1,'parameter_searches':0,
         'total_fills_checked':sum(c['fills'] for c in checks),'total_bar_marks_checked':sum(c['bars'] for c in checks),
         'fidelity_class':'HYPOTHESIS','data_quality_status':'DIAGNOSTIC_ONLY','strict_reproductions':0,'oos':False,
         'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
         'scope':'Independent accounting/metrics/order and signal-availability check of actual frozen outputs. Does not assert original-runtime reproduction, PIT/finality/tradability or a general no-lookahead proof.'}
    with a.output.open('x') as f:json.dump(out,f,indent=2);f.write('\n')
    print(json.dumps({k:out[k] for k in ['record_id','status','total_fills_checked','total_bar_marks_checked','peak_rss_bytes']}))


if __name__=='__main__':main()
