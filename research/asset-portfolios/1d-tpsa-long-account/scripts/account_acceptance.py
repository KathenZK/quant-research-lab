import os
import sys,json,hashlib,importlib.util
from pathlib import Path
import pandas as pd,numpy as np
F=Path(__file__).resolve().parents[1];A=Path(os.environ.get('TPSA_R0_OUTPUT',str(F/'artifacts')));S=Path('/Users/ZK/OpenCode/quant-strategy-lab');sys.path.insert(0,str(S/'src'))
from strategy_lab.data.funding_v2 import load_funding_v2
fund=load_funding_v2(S/'data/derived/datasets/binance_perp_funding_v3_inputs_v2',expected_manifest_sha256='398cc19eac88d0e8c55258c118f6cae2481c6b2d1a5e6253778344b9f25a1076')
coverage=[]
for name in ['ML_p040','ALL_EVENTS','HASH20_EVENTS']:
    tr=pd.read_csv(A/name/'trades.csv');tr.entry_time=pd.to_datetime(tr.entry_time,utc=True);tr.exit_time=pd.to_datetime(tr.exit_time,utc=True)
    for r in tr.itertuples():
        h=fund.segments[fund.segments.symbol.eq(r.symbol)&fund.segments.start.le(r.entry_time)&fund.segments.end.ge(r.exit_time)]
        coverage.append({'variant':name,'event_id':r.event_id,'symbol':r.symbol,'entry':r.entry_time,'exit':r.exit_time,'calendar_segment_covers_trade':len(h)==1,'segment_id':str(h.segment_id.iloc[0]) if len(h)==1 else None,'identity_proven':False,'mark_price_at_funding_events_verified':False,'net_valid':False})
cv=pd.DataFrame(coverage);cv.to_csv(A/'funding_calendar_trade_scope.csv',index=False)
full=[]
for s in sorted(pd.read_parquet(A/'predictions.parquet',columns=['symbol']).symbol.unique()):
    q=fund.segments[fund.segments.symbol.eq(s)&fund.segments.start.le(pd.Timestamp('2025-01-01',tz='UTC'))&fund.segments.end.ge(pd.Timestamp('2026-07-02',tz='UTC'))]
    full.append({'symbol':s,'full_requested_calendar_segment':len(q)==1})
(A/'funding_calendar_audit.json').write_text(json.dumps({'full_requested_symbols':len(full),'full_requested_calendar_covered_symbols':sum(r['full_requested_calendar_segment'] for r in full),'trade_scope':cv.groupby('variant').calendar_segment_covers_trade.agg(['count','sum']).to_dict('index'),'no_rates_used_for_equity':True,'not_identity_review':True,'missing_event_mark_prices':True},indent=2))
# A hand-calculable fixture passed through the actual engine; no source market outcome optimization.
sp=importlib.util.spec_from_file_location('account_engine',F/'scripts/run_account.py');mod=importlib.util.module_from_spec(sp);sp.loader.exec_module(mod)
dates=pd.date_range('2025-01-01','2026-07-01',tz='UTC');p=pd.DataFrame({'symbol':'FIXTURE/USDT:USDT','ts':dates,'open':100.,'close':100.,'eligible':True,'research_window_valid':True,'research_segment_id':'FIXTURE#1'})
p.loc[1,['open','close']]=[101.,105.];p.loc[2,['open','close']]=[106.,108.];p.loc[3,['open','close']]=[110.,109.]
e=pd.DataFrame([{'event_id':'manual-case','symbol':'FIXTURE/USDT:USDT','event_date':dates[0],'probability':.5,'priority':'00','hash20_selected':True,'close':100.,'atr20_pre':3.}])
z=mod.simulate(p,e,('MANUAL_FIXTURE',.4,False,0,1,5,0))
qty=20.;entry=101*1.0004;exit=110*.9996;ef=qty*entry*.001;xf=qty*exit*.001;expected=10000+qty*(exit-entry)-ef-xf
assert abs(z['final_equity_ex_actual_funding']-expected)<1e-9
# A positive funding event is a long debit; this algebra fixture is not an observed funding claim.
long_charge=qty*105*.0001
(A/'manual_account_check.json').write_text(json.dumps({'signal_close':100.,'planned_budget':2000.,'quantity_fixed_before_open':qty,'entry_raw_open':101.,'entry_slipped':entry,'exit_raw_open':110.,'exit_slipped':exit,'entry_fee':ef,'exit_fee':xf,'expected_final_ex_funding':expected,'engine_final_ex_funding':z['final_equity_ex_actual_funding'],'absolute_error':abs(expected-z['final_equity_ex_actual_funding']),'positive_funding_long_debit_example':long_charge,'negative_funding_long_credit_example':long_charge,'actual_funding_status':'UNKNOWN; algebra only'},indent=2))
print('calendar scope + manual fixture verified')
