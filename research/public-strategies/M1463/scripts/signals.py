"""Catalog20/2 population Bollinger strict-cross hypothesis, Decimal50."""
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN

def cross(previous_close,previous_upper,previous_middle,current_close,current_upper,current_middle):
    if previous_upper is None or current_upper is None:return False,False
    return previous_close<=previous_upper and current_close>current_upper,previous_close>=previous_middle and current_close<current_middle

def features(rows):
    out=[];closes=[];previous_upper=previous_middle=previous_close=None
    with localcontext() as ctx:
        ctx.prec=50;ctx.rounding=ROUND_HALF_EVEN
        for i,r in enumerate(rows):
            price=D(r['close']);closes.append(price);middle=variance=sd=upper=lower=None
            if i>=19:
                sample=closes[i-19:i+1];middle=sum(sample,D(0))/D(20)
                variance=sum(((v-middle)**2 for v in sample),D(0))/D(20)
                sd=variance.sqrt();upper=middle+D(2)*sd;lower=middle-D(2)*sd
            entry,exit_=cross(previous_close,previous_upper,previous_middle,price,upper,middle)
            out.append(dict(input_index=i,open_time=r['open_time'],close_time=r['close_time'],close=r['close'],middle='' if middle is None else str(middle),variance='' if variance is None else str(variance),std='' if sd is None else str(sd),upper='' if upper is None else str(upper),lower='' if lower is None else str(lower),previous_close='' if previous_close is None else str(previous_close),previous_upper='' if previous_upper is None else str(previous_upper),previous_middle='' if previous_middle is None else str(previous_middle),ready=int(middle is not None),raw_entry=int(entry),raw_exit=int(exit_)))
            previous_close=price;previous_upper=upper;previous_middle=middle
    return out
