"""Independent exact rational hl2/SMA and integer UTC-weekday calculation."""
from decimal import Decimal as D,localcontext
from fractions import Fraction as F

def expected_features(rows):
    output=[]
    for i,row in enumerate(rows):
        value=(F(row['high'])+F(row['low']))/2
        average=sum(((F(x['high'])+F(x['low']))/2 for x in rows[i-3:i+1]),F(0))/4 if i>=3 else None
        weekday=(int(row['open_time'])//86400000+3)%7
        def dec(v):
            if v is None:return None
            with localcontext() as c:c.prec=80;return D(v.numerator)/D(v.denominator)
        output.append(dict(hl2=dec(value),sma4=dec(average),weekday_utc=weekday,ready=average is not None,entry=weekday==1 and average is not None and value>average,exit=weekday==5))
    return output

def verify_features(rows,actual):
    expected=expected_features(rows)
    assert len(actual)==len(rows)
    for i,(a,e,r) in enumerate(zip(actual,expected,rows)):
        assert int(a['input_index'])==i and a['open_time']==r['open_time'] and a['close']==r['close'] and a['close_time']==r['close_time']
        for k in ['hl2','sma4']:
            if e[k] is None:assert a[k]==''
            else:
                got=D(a[k]);want=e[k]
                assert got==0 if want==0 else abs(got-want)<=abs(want)*D('1e-45')
        assert int(a['weekday_utc'])==e['weekday_utc'] and int(a['ready'])==e['ready']
        assert int(a['raw_entry'])==e['entry'] and int(a['raw_exit'])==e['exit']
    return expected
