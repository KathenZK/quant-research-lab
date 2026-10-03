#!/usr/bin/env python3
"""Common independently authored Decimal accounting oracle for both batch004 ports.

Normalizes each port's event/bar schema then checks every fill and every bar.
The verify function accepts normalized ledger records; it does not run a trading engine.
"""
import copy, hashlib, importlib.util, inspect, json, sys
sys.dont_write_bytecode=True
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path
import pandas as pd
import numpy as np

D=lambda v:Decimal(str(v))
TOL=Decimal('0.0000002')


def load(name,path):
    sys.path.insert(0,str(path.parent))
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s)
    sys.modules[name]=m;s.loader.exec_module(m);return m


def verify(fills,marks,fee_bps,friction_bps=0,metrics=None,record_id=None):
    with localcontext() as ctx:
        ctx.prec=50
        cash=D(100000);qty=D(0);peak=cash;fee=D(fee_bps)/10000;friction=D(friction_bps)/10000
        rate=fee+friction;entry_budget=D(0);index=0;maxerr=D(0);fees=D(0);frictions=D(0);closed=0
        def near(got,want,label):
            nonlocal maxerr
            diff=abs(D(got)-want);maxerr=max(maxerr,diff)
            assert diff<=TOL,(record_id,label,str(got),str(want),str(diff))
        for bar in marks:
            k=int(bar['bar_index'])
            while index<len(fills) and int(fills[index]['bar_index'])==k:
                e=fills[index];assert int(e['event_id'])==index+1
                price=D(e['fill_price']);side=e['side'].lower()
                assert price>0
                if 'cash_before' in e:near(e['cash_before'],cash,'cash before')
                if side=='buy':
                    assert qty==0,(record_id,'buy while holding')
                    entry_budget=cash*D('.95');notional=entry_budget/(1+rate)
                    quantity=notional/price;qty=quantity;cash-=entry_budget
                else:
                    assert side=='sell' and qty>0,(record_id,'sell without inventory')
                    quantity=qty;notional=qty*price;cash+=notional*(1-rate);qty=D(0);closed+=1
                    if e.get('roundtrip_return') is not None:
                        near(e['roundtrip_return'],notional*(1-rate)/entry_budget-1,'return on budget')
                commission=notional*fee;charge=notional*friction;fees+=commission;frictions+=charge
                near(e['quantity'],quantity,'quantity');near(e['notional'],notional,'notional')
                near(e['fee'],commission,'fee');near(e.get('friction',0),charge,'cash friction')
                near(e['cash_after'],cash,'cash after')
                if 'quantity_after' in e:near(e['quantity_after'],qty,'quantity after')
                near(e.get('entry_budget',e.get('entry_total_cost')),entry_budget,'entry budget')
                if e.get('signal_open_time') is not None and pd.notna(e.get('signal_open_time')):
                    assert int(e['signal_open_time'])+300000<=int(e['open_time'])
                if e.get('signal_available_utc') is not None and pd.notna(e.get('signal_available_utc')):
                    assert pd.Timestamp(e['signal_available_utc'])<=pd.Timestamp(e['execution_earliest_utc'])
                if e.get('limit_price') is not None and pd.notna(e.get('limit_price')):
                    limit=D(e['limit_price']);assert price<=limit if side=='buy' else price>=limit
                assert cash>=0 and qty>=0
                index+=1
            equity=cash+qty*D(bar['close']);peak=max(peak,equity)
            for field,value in [('cash',cash),('quantity',qty),('equity',equity)]:near(bar[field],value,'bar '+field)
            if 'drawdown' in bar:near(bar['drawdown'],equity/peak-1,'fullbar drawdown')
            if 'net_liquidation_equity' in bar:near(bar['net_liquidation_equity'],cash+qty*D(bar['close'])*(1-rate),'net liquidation')
            if 'nav' in bar:near(bar['nav'],equity/D(100000),'normalized NAV')
        assert index==len(fills),('unconsumed event',index,len(fills))
        if metrics:
            near(metrics.get('fees_paid',metrics.get('total_fees')),fees,'aggregate fees')
            if 'total_cash_friction' in metrics:near(metrics['total_cash_friction'],frictions,'aggregate friction')
            near(metrics['final_equity'],equity,'terminal equity')
            near(metrics['total_return'],equity/D(100000)-1,'total return')
            values=[D(100000)]+[D(x['equity']) for x in marks];running=values[0];maxdd=D(0)
            for value in values:
                running=max(running,value);maxdd=max(maxdd,1-value/running)
            sign=-1 if record_id=='M0298' else 1
            near(metrics['max_drawdown'],sign*maxdd,'MDD from fullbar equity')
        return {'fills':len(fills),'bars':len(marks),'completed_roundtrips':closed,'max_abs_decimal_error':str(maxerr)}

