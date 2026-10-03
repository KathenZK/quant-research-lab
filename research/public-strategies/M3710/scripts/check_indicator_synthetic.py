"""Generated decimal strings only. No market files or account calls."""
if not __debug__:
    raise RuntimeError('M3710 rejects Python -O')
import argparse
import copy
import json
from pathlib import Path
from decimal import Decimal, localcontext
from signals import features
from oracle import verify_features

DAY = 86400000
START = 1663891200000

def bars(prices):
    return [dict(open_time=str(START + i * DAY), close_time=str(START + (i+1)*DAY-1),
                 close=str(price)) for i, price in enumerate(prices)]

def check():
    checks = []
    def passed(text): checks.append(text)
    for constant in ['0.1', '0.3', '10', '100', '1e-100', '1e100']:
        rows = bars([constant] * 831)
        f = features(rows)
        verify_features(rows, f)
        assert all(x['ready']==0 and x['sma20']=='' and not x['raw_entry'] and not x['raw_exit'] for x in f[:19])
        assert all(x['ready']==1 and not x['raw_entry'] and x['raw_exit']==1 for x in f[19:])
        passed('constant equality cash / readiness19 / Fraction ' + constant)
    for prices, direction in [(list(range(1,832)), 'up'), (list(range(900,69,-1)), 'down')]:
        rows=bars(prices);f=features(rows);verify_features(rows,f)
        assert all(x['raw_entry']==(direction=='up') and x['raw_exit']==(direction=='down') for x in f[19:])
        assert f[100]['raw_entry']==f[99]['raw_entry']
        passed(direction + ' sustained state includes first evaluation without cross')
    rows=bars(['100']*19+['120']);f=features(rows);assert f[-1]['sma20']=='101' and f[-1]['raw_entry']==1
    verify_features(rows,f);passed('first SMA uses20 observations/current close included')
    prices=['100']*20+['99'];rows=bars(prices);f=features(rows);verify_features(rows,f)
    assert f[-1]['raw_exit']==1 and f[-1]['sma20']=='99.95';passed('current below SMA exits')
    # Decimal50 rounding under large dynamic range and ties, not exact aggregate substitution.
    prices=['1'+'0'*60, '1', '3.00000000000000000000000000000000000000000000000005']*280
    rows=bars(prices);f=features(rows);verify_features(rows,f);passed('rational per-operation rounding / large dynamic range')
    rows=bars([f'{100+(i*7)%31}.{(i*13)%100:02d}' for i in range(831)])
    f=features(rows);verify_features(rows,f);passed('831 generated decimal observations exact independent Fraction')
    for cut in [0,1,18,19,20,21,68,69,70,99,100,101,400,830,831]:
        assert features(rows[:cut])==f[:cut]
        changed=copy.deepcopy(rows)
        for row in changed[cut:]:row['close']='999999.99'
        assert features(changed)[:cut]==f[:cut]
        passed('prefix/future isolation ' + str(cut))
    for invalid in ['NaN','Infinity','-1','0']:
        try: features(bars([invalid]))
        except ValueError: passed('reject invalid close ' + invalid)
        else: raise AssertionError(invalid)
    try: features([dict(bars(['1'])[0],close=1.0)])
    except TypeError: passed('reject binary float input')
    else: raise AssertionError('float accepted')
    return dict(id='M3710',status='PASS',checks=len(checks),tests=checks,synthetic_only=True,
        historical_features=0,historical_runs=0,new_controls=0,account_calls=0,market_data_read=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=check()
    with a.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({k:result[k] for k in ['status','checks','synthetic_only']}))
