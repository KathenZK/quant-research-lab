"""Synthetic boundary tests of frozen engine, separate from independent real oracle."""
import copy,hashlib,importlib.util,json,pathlib
import pandas as pd
S=pathlib.Path(__file__).resolve().parents[1];spec=json.loads((S/'specs/protocol.json').read_text())
p=S/'scripts/run_replay.py'; assert hashlib.sha256(p.read_bytes()).hexdigest()==spec['frozen_file_hashes']['scripts/run_replay.py']
module=importlib.util.spec_from_file_location('frozen_m0275_test_target',p);engine=importlib.util.module_from_spec(module);module.loader.exec_module(engine)
CASE={'name':'synthetic','fee_bps':8,'delay_bars':1}
def frame(n,start='2023-01-01T00:00:00Z'):
 t=int(pd.Timestamp(start).value//10**6)
 return pd.DataFrame({'open_time':[t+i*14400000 for i in range(n)],'close_time':[t+(i+1)*14400000-1 for i in range(n)],'open':100.,'high':100.,'low':100.,'close':100.,'entry_signal':[True]+[False]*(n-1),'exit_signal':False})
def run(f,case=CASE):
 s=copy.deepcopy(spec);s['evaluation']['start']=engine.iso(f.iloc[0].open_time);s['evaluation']['end_exclusive']=engine.iso(f.iloc[-1].close_time+1)
 return engine.replay(f,s,case)
checks=[]
f=frame(3);f.loc[1,['high','low']]=[200,50];n,d,t,m,e=run(f);assert t.side.tolist()==['BUY','SELL'] and t.iloc[1].reason=='stoploss' and t.iloc[1].phase=='intrabar_unknown'; assert m['unresolved_stop_roi_samebar']==1;checks.append('same_bar_dual_touch_stop_first')
f=frame(3);f.loc[2,['open','high','low','close']]=[70,70,60,65];n,d,t,m,e=run(f);assert t.iloc[1].reason=='stoploss' and t.iloc[1].phase=='open_gap' and t.iloc[1].reference_price==70;checks.append('gap_stop_worse_observed_open')
f=frame(3);f.loc[2,['open','high','low','close']]=[180,190,170,185];n,d,t,m,e=run(f);assert t.iloc[1].reason=='roi' and t.iloc[1].phase=='open_gap' and t.iloc[1].reference_price==180;checks.append('gap_roi_observed_open')
f=frame(5);f.loc[3,'high']=130.;f.loc[4,'high']=130.;n,d,t,m,e=run(f);assert int(t.iloc[1].bar_index)==4 and int(t.iloc[1].roi_step_minutes)==644;assert e[0]['bar_index']==3;checks.append('644_minute_boundary_deferred_until_next_open')
f=frame(34);f.loc[32,'high']=101.;n,d,t,m,e=run(f);assert int(t.iloc[1].bar_index)==32 and int(t.iloc[1].roi_step_minutes)==7289;cashin=t.iloc[0].notional+t.iloc[0].fee;cashout=t.iloc[1].notional-t.iloc[1].fee;assert cashout/cashin-1<0;checks.append('zero_roi_tier_adverse_slippage_net_loss')
f=frame(6);n,d,t,m,e=run(f,dict(CASE,delay_bars=2));assert int(t.iloc[0].bar_index)==2 and int(t.iloc[0].signal_bar_index)==0;checks.append('delay2_and_no_warmup_order')
f=frame(4,'2023-03-24T08:00:00Z');n,d,t,m,e=run(f);assert t.iloc[0].execution_time_utc=='2023-03-24T14:00:00Z' and t.iloc[0].entry_time_utc=='2023-03-24T14:00:00Z';checks.append('halt_entry_timestamp_is_resume14')
f=frame(6,'2023-03-23T20:00:00Z');f.loc[4,'high']=130.;n,d,t,m,e=run(f);assert int(t.iloc[1].bar_index)==4 and t.iloc[1].roi_step_minutes==644;candidate=[x for x in e if x['minutes']==644][0];assert candidate['observed_from_utc']=='2023-03-24T14:00:00Z';checks.append('halt_delayed_roi_observation14')
f=frame(6,'2023-03-23T20:00:00Z');f.loc[3,'high']=200.;n,d,t,m,e=run(f);assert t.iloc[1].execution_latest_utc=='2023-03-24T11:26:59.999000Z';checks.append('prehault_intrabar_latest_before_suspension')
assert m['final_quantity']==0
result={'status':'PASS_SYNTHETIC_EXECUTION_CONTRACT_TESTS','checks':checks,'target_engine_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'protocol_sha256':hashlib.sha256((S/'specs/protocol.json').read_bytes()).hexdigest(),'auditor_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'synthetic_only':True,'scope':'Driving tested engine with synthetic examples is distinct from independent stdlib/Decimal real-result oracle; not empirical fills or framework parity.'}
print(json.dumps(result,indent=2))
