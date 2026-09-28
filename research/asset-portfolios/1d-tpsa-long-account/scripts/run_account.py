import os
"""Fully collateralized long linear-futures accounting. Price/fees only, never verified net."""
import json,hashlib,math
from pathlib import Path
import pandas as pd,numpy as np
F=Path(__file__).resolve().parents[1];A=Path(os.environ.get('TPSA_R0_OUTPUT',str(F/'artifacts')));C=json.loads((F/'specs/frozen-config.json').read_text())
START=pd.Timestamp('2025-01-01',tz='UTC');END=pd.Timestamp('2026-07-01',tz='UTC')
VARIANTS=[('ML_p040',.4,False,0,1,5,0),('ALL_EVENTS',0,False,0,1,5,0),('HASH20_EVENTS',0,True,0,1,5,0),('ML_p035',.35,False,0,1,5,0),('ML_p045',.45,False,0,1,5,0),('ML_double_cost',.4,False,0,2,5,0),('ML_delay_1d',.4,False,1,1,5,0),('ML_min100',.4,False,0,1,100,0),('ML_funding_assumed_10pct',.4,False,0,1,5,.1),('ML_funding_assumed_30pct',.4,False,0,1,5,.3)]
def dump(path,v):path.write_text(json.dumps(v,indent=2,default=str))
def load_inputs():
    proof=json.loads((A/'price_startup_report.json').read_text());assert proof['status']=='PRICE_DIAGNOSTIC_INPUTS_VERIFIED'
    p=pd.read_parquet(A/'verified_price_frames.parquet');e=pd.read_parquet(A/'predictions.parquet');return p,e

def simulate(p,e,variant):
    name,threshold,hashonly,delay,cmult,minorder,holdrate=variant
    fee=C['cost']['fee_per_side']*cmult;slip=C['cost']['adverse_slippage_per_side']*cmult
    path=A/name;path.mkdir(exist_ok=True)
    p={s:g.set_index('ts').sort_index() for s,g in p.groupby('symbol')}
    e=e[e.probability.ge(threshold)&((not hashonly)|e.hash20_selected)].copy()
    e['entry_time']=e.event_date+pd.Timedelta(days=1+delay)
    signals={d:g.sort_values('priority').to_dict('records') for d,g in e.groupby('entry_time')}
    balance=10000.;held={};orders=[];positions=[];equity=[];trades=[];rejects=[];block=None;last_equity=10000.;last_close_values={}
    # balance is total wallet cash before reserved collateral, with realized PnL and fees/assumed charges.
    def row(s,d):
        g=p.get(s)
        if g is None or d not in g.index:return None
        r=g.loc[d]
        if not bool(r.eligible) or not bool(r.research_window_valid):return None
        return r
    for d in pd.date_range(START,END,freq='1D'):
        missing=[]
        for s,pos in held.items():
            r=row(s,d)
            if r is None or str(r.research_segment_id)!=pos['segment']:
                missing.append({'symbol':s,'entry_time':pos['entry_time'],'qty':pos['qty'],'entry_price':pos['entry_price']})
        if missing:
            block={'date':d,'reason':'HOLDING_PRICE_MISSING_INVALID_OR_SEGMENT_BREAK','positions':missing};break
        # The exit order was decided at the previous completed close.
        for s,pos in list(held.items()):
            r=row(s,d)
            if pos['exit_due']==d or d==END:
                price=float(r.open)*(1-slip);notional=pos['qty']*price;cost=notional*fee;gross=pos['qty']*(price-pos['entry_price']);balance+=gross-cost
                reason='TERMINAL' if d==END else pos['exit_reason'];order={'time':d,'symbol':s,'event_id':pos['event_id'],'side':'SELL','qty':pos['qty'],'reference_price':float(r.open),'fill_price':price,'notional_usd':notional,'fee_usd':cost,'actual_funding_usd':None,'reason':reason,'decision_time':pos['exit_decision_time'] if d!=END else END-pd.Timedelta(days=1)};orders.append(order)
                trades.append({**pos,'exit_time':d,'exit_price':price,'exit_reference_open':float(r.open),'exit_fee':cost,'gross_pnl':gross,'price_fee_pnl':gross-cost-pos['entry_fee'],'assumed_holding_charge':pos['assumed_charge'],'pnl_after_assumed_charge':gross-cost-pos['entry_fee']-pos['assumed_charge'],'exit_reason':reason})
                del held[s]
        # Quantity fixed from completed signal close, no sizing using a future day's return.
        if d<END:
            for ev in signals.get(d,[]):
                s=ev['symbol'];reason=None;r=row(s,d)
                if s in held:reason='ALREADY_HELD'
                elif len(held)>=C['max_positions']:reason='CAPACITY'
                elif r is None:reason='ENTRY_PRICE_UNAVAILABLE'
                elif not np.isfinite(ev['close']) or ev['close']<=0 or ev['atr20_pre']<=0:reason='INVALID_SIGNAL_PRICE_ATR'
                if reason:
                    rejects.append({'time':d,'symbol':s,'event_id':ev['event_id'],'reason':reason});continue
                source_day=row(s,ev['event_date'])
                if source_day is None or str(source_day.research_segment_id)!=str(r.research_segment_id):
                    rejects.append({'time':d,'symbol':s,'event_id':ev['event_id'],'reason':'SIGNAL_ENTRY_SEGMENT_DISCONTINUITY'});continue
                planned=C['position_fraction']*last_equity;qty=planned/float(ev['close']);price=float(r.open)*(1+slip);notional=qty*price;cost=notional*fee
                reserved=sum(z['entry_notional'] for z in held.values());free=balance-reserved
                # Full notional collateral must be available. The gross risk budget is checked at execution quote.
                open_eq=balance+sum(z['qty']*(float(row(ss,d).open)-z['entry_price']) for ss,z in held.items())
                open_gross=sum(z['qty']*float(row(ss,d).open) for ss,z in held.items())
                if notional<minorder:reason='MIN_ORDER'
                elif notional+cost>free:reason='INSUFFICIENT_FULL_COLLATERAL'
                elif open_gross+notional>C['gross_entry_cap']*open_eq:reason='GROSS_CAP'
                if reason:
                    rejects.append({'time':d,'symbol':s,'event_id':ev['event_id'],'reason':reason});continue
                balance-=cost
                held[s]={'event_id':ev['event_id'],'symbol':s,'signal_date':ev['event_date'],'entry_time':d,'entry_price':price,'entry_reference_open':float(r.open),'entry_notional':notional,'entry_fee':cost,'qty':qty,'atr':float(ev['atr20_pre']),'probability':float(ev['probability']),'segment':str(r.research_segment_id),'exit_due':None,'exit_reason':None,'exit_decision_time':None,'assumed_charge':0.}
                orders.append({'time':d,'symbol':s,'event_id':ev['event_id'],'side':'BUY','qty':qty,'reference_price':float(r.open),'fill_price':price,'notional_usd':notional,'fee_usd':cost,'actual_funding_usd':None,'reason':'ENTRY','decision_time':ev['event_date']+pd.Timedelta(days=1)})
        # Close valuation includes adverse entry fill and real fees. Actual funding remains unknown.
        for s,pos in held.items():
            r=row(s,d);close=float(r.close);charge=pos['qty']*close*holdrate/365.;balance-=charge;pos['assumed_charge']+=charge
            ret_atr=(close-pos['entry_price'])/pos['atr'];age=(d-pos['entry_time']).days+1
            if ret_atr>=2 or ret_atr<=-1 or age>=20:
                pos['exit_due']=d+pd.Timedelta(days=1);pos['exit_reason']='TP_CLOSE' if ret_atr>=2 else ('SL_CLOSE' if ret_atr<=-1 else 'TIME_20_CLOSES');pos['exit_decision_time']=d+pd.Timedelta(days=1)
            positions.append({'time':d+pd.Timedelta(days=1),'bar_open':d,'symbol':s,'event_id':pos['event_id'],'qty':pos['qty'],'entry_price':pos['entry_price'],'mark_close':close,'collateral_usd':pos['entry_notional'],'unrealized_pnl':pos['qty']*(close-pos['entry_price']),'notional_usd':pos['qty']*close,'actual_funding_usd':None,'assumed_holding_charge_usd':charge,'exit_due':pos['exit_due']})
        unreal=sum(z['qty']*(float(row(s,d).close)-z['entry_price']) for s,z in held.items());reserved=sum(z['entry_notional'] for z in held.values());gross=sum(z['qty']*float(row(s,d).close) for s,z in held.items());eq=balance+unreal
        assert balance-reserved>=-1e-8
        equity.append({'sequence':len(equity),'valuation_type':'DAILY_CLOSE' if d<END else 'TERMINAL_OPEN_LIQUIDATION','time':d+pd.Timedelta(days=1) if d<END else d,'bar_open':d,'wallet_balance':balance,'free_cash':balance-reserved,'reserved_collateral':reserved,'unrealized_pnl':unreal,'equity_ex_actual_funding':eq,'positions':len(held),'gross_notional':gross,'actual_funding_usd':None,'funding_assumption_annual':holdrate})
        last_equity=eq
    eq=pd.DataFrame(equity);od=pd.DataFrame(orders);tr=pd.DataFrame(trades);po=pd.DataFrame(positions);rej=pd.DataFrame(rejects)
    eq.to_csv(path/'account_equity.csv',index=False);od.to_csv(path/'orders.csv',index=False);tr.to_csv(path/'trades.csv',index=False);po.to_csv(path/'positions.csv',index=False);rej.to_csv(path/'rejections.csv',index=False)
    vals=np.r_[10000.,eq.equity_ex_actual_funding.to_numpy()];dd=vals/np.maximum.accumulate(vals)-1
    elapsed=(pd.Timestamp(eq.time.iloc[-1])-START).total_seconds()/86400
    metrics={'variant':name,'account_complete':block is None,'coverage_start':str(START),'coverage_end':str(eq.time.iloc[-1]),'blocked_at':str(block['date']) if block else None,'funding_status':'UNKNOWN_NOT_NET_VALID' if holdrate==0 else 'ASSUMED_SCENARIO_NOT_ACTUAL_NET','initial_capital_usd':10000.,'final_equity_ex_actual_funding':float(vals[-1]),'return_ex_actual_funding':float(vals[-1]/10000-1),'max_drawdown_ex_actual_funding':float(dd.min()),'cagr_ex_actual_funding':float((vals[-1]/10000)**(365.25/elapsed)-1) if vals[-1]>0 and elapsed>0 else None,'closed_trades':len(tr),'open_positions_at_block':len(held),'total_fee_usd':float(od.fee_usd.sum()) if len(od) else 0.,'turnover_initial_capital':float(od.notional_usd.sum()/10000) if len(od) else 0.,'mean_gross_exposure':float((eq.gross_notional/eq.equity_ex_actual_funding).mean()),'rejected':len(rej),'rejection_reasons':rej.reason.value_counts().to_dict() if len(rej) else {},'threshold':threshold,'assumed_annual_holding_charge':holdrate,'actual_funding_usd':None,'executable_lot_filters_verified':False,'min_order_assumed':minorder}
    if len(tr):
        pnl=tr.price_fee_pnl;metrics.update(win_rate_price_fee=float((pnl>0).mean()),mean_trade_price_fee_pnl=float(pnl.mean()),median_trade_price_fee_pnl=float(pnl.median()),largest_winning_trade_usd=float(pnl.max()),top5_winners_usd=float(pnl.nlargest(5).sum()),total_closed_price_fee_pnl=float(pnl.sum()))
    years=[]
    for year,g in eq.groupby(pd.to_datetime(eq.time,utc=True).dt.year):
        ix=g.index[0];prior=10000 if ix==0 else float(eq.equity_ex_actual_funding.iloc[ix-1]);years.append({'year':int(year),'return_ex_actual_funding':float(g.equity_ex_actual_funding.iloc[-1]/prior-1),'start_equity':prior,'end_equity':float(g.equity_ex_actual_funding.iloc[-1])})
    metrics['years']=years;dump(path/'metrics.json',metrics);dump(path/'blocker.json',block)
    return metrics

def main():
    p,e=load_inputs();metrics=[]
    for variant in VARIANTS:
        result=simulate(p,e,variant);metrics.append(result);print(json.dumps({k:result[k] for k in ['variant','account_complete','coverage_end','return_ex_actual_funding','max_drawdown_ex_actual_funding','closed_trades']},default=str),flush=True)
    dump(A/'variant_metrics.json',metrics)

if __name__=='__main__':main()
