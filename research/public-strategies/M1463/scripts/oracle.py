"""Independent rational population moments plus high precision sqrt oracle."""
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN
from fractions import Fraction as F

def expected_features(rows):
    output=[];last=None
    for i,row in enumerate(rows):
        price=F(row['close']);middle=variance=std=upper=lower=None
        with localcontext() as c:
            c.prec=80;c.rounding=ROUND_HALF_EVEN
            def dec(v):return D(v.numerator)/D(v.denominator)
            if i>=19:
                sample=[F(x['close']) for x in rows[i-19:i+1]]
                m=sum(sample,F(0))/20
                v=sum((x*x for x in sample),F(0))/20-m*m
                middle=dec(m);variance=dec(v);std=variance.sqrt();upper=middle+2*std;lower=middle-2*std
            p=dec(price)
            entry=last is not None and last['upper'] is not None and upper is not None and last['close']<=last['upper'] and p>upper
            exit_=last is not None and last['middle'] is not None and middle is not None and last['close']>=last['middle'] and p<middle
            result=dict(close=p,middle=middle,variance=variance,std=std,upper=upper,lower=lower,ready=middle is not None,entry=entry,exit=exit_,previous_close=None if last is None else last['close'],previous_upper=None if last is None else last['upper'],previous_middle=None if last is None else last['middle'])
            output.append(result);last=result
    return output

def verify_features(rows,actual):
    expected=expected_features(rows)
    assert len(actual)==len(rows)
    for i,(a,e,r) in enumerate(zip(actual,expected,rows)):
        assert int(a['input_index'])==i and a['open_time']==r['open_time'] and a['close']==r['close'] and a['close_time']==r['close_time']
        for k in ['middle','variance','std','upper','lower','previous_close','previous_upper','previous_middle']:
            if e[k] is None:assert a[k]==''
            else:
                got=D(a[k]);want=e[k]
                assert got==0 if want==0 else abs(got-want)<=abs(want)*D('1e-42'),(i,k,got,want)
        assert int(a['ready'])==e['ready'] and int(a['raw_entry'])==e['entry'] and int(a['raw_exit'])==e['exit'],i
    return expected
