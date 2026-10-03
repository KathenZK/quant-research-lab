"""Catalog weekday/hl2 hypothesis only, Decimal50, UTC labels."""
from datetime import datetime,timezone
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN

def features(rows):
    output=[];values=[]
    with localcontext() as ctx:
        ctx.prec=50;ctx.rounding=ROUND_HALF_EVEN
        for i,r in enumerate(rows):
            value=(D(r['high'])+D(r['low']))/D(2);values.append(value)
            avg=sum(values[i-3:i+1],D(0))/D(4) if i>=3 else None
            weekday=datetime.fromtimestamp(int(r['open_time'])/1000,timezone.utc).weekday()
            entry=weekday==1 and avg is not None and value>avg
            exit_=weekday==5
            output.append(dict(input_index=i,open_time=r['open_time'],close_time=r['close_time'],close=r['close'],hl2=str(value),sma4='' if avg is None else str(avg),weekday_utc=weekday,ready=int(avg is not None),raw_entry=int(entry),raw_exit=int(exit_)))
    return output
