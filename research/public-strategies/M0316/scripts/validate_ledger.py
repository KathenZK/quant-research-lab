#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Second implementation: Decimal recomputation of recorded fills and marked ledger.
Does not import/call the replay engine. Not an independent intrabar price oracle.
"""
import argparse,csv,decimal,hashlib,json,pathlib
D=decimal.Decimal;decimal.getcontext().prec=40

def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def validate(work,input_path,spec_path):
    work=pathlib.Path(work);spec=json.loads(pathlib.Path(spec_path).read_text());summ=json.loads((work/'summary.json').read_text())
    assert sha(input_path)==spec['input']['sha256'];bars=list(csv.DictReader(open(input_path)))
    reports={}
    for case in spec['cases']:
        name=case['name'];trades=list(csv.DictReader(open(work/f'{name}-trades.csv')));nav=list(csv.DictReader(open(work/f'{name}-nav.csv')))
        events={}
        for e in trades:events.setdefault(int(e['bar_index']),[]).append(e)
        cash=D(str(spec['execution']['initial_cash']));qty=D(0);fees=D(0);lastside='SELL';maxerr=D(0)
        for n in nav:
            k=int(n['bar_index']);r=bars[k]
            for e in events.get(k,[]):
                size=D(e['quantity']);price=D(e['fill_price']);fee=price*size*D(case['fee_bps'])/D(10000)
                assert e['side']!=lastside;lastside=e['side']
                assert abs(fee-D(e['fee']))<D('1e-7')
                expected_price=D(e['reference_price'])*(1+(D(1) if e['side']=='BUY' else D(-1))*D(spec['execution']['slippage_bps'])/D(10000))
                if e['limit_price']:
                    lim=D(e['limit_price']);expected_price=min(expected_price,lim) if e['side']=='BUY' else max(expected_price,lim)
                assert abs(price-expected_price)<D('1e-7')
                if e['side']=='BUY':
                    assert qty==0
                    expected_budget=cash*D(str(spec['execution']['cash_budget_fraction']))
                    assert abs(size*price+fee-expected_budget)<D('1e-6')
                    if not case.get('buy_hold'):
                        prior=int(e['signal_bar_index']);assert prior==k-case['delay_bars'];assert int(bars[prior]['close_time'])<int(r['open_time'])
                    cash-=size*price+fee;qty=size
                else:
                    assert abs(qty-size)<D('1e-12');cash+=size*price-fee;qty=D(0)
                fees+=fee
                assert abs(cash-D(e['cash_after']))<D('1e-6') and abs(qty-D(e['quantity_after']))<D('1e-10')
            eq=cash+qty*D(r['close']);err=abs(eq-D(n['equity']));maxerr=max(maxerr,err);assert err<D('1e-6')
        assert abs(eq-D(str(summ['results'][name]['metrics']['final_equity'])))<D('1e-6')
        reports[name]={'fill_events':len(trades),'nav_rows':len(nav),'max_equity_error_usdt':float(maxerr),'final_equity':float(eq),'total_fees':float(fees),'status':'PASS'}
    return {'status':'PASS','validation_method':'independent Decimal ledger; no engine import','input_sha256':sha(input_path),'protocol_sha256':sha(spec_path),'cases':reports,'limits':['uses recorded fills, checks arithmetic/signals/timing but cannot independently resolve OHLC intrabar path','separate source/formula/prefix checks validate signal generation']}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work',required=True);p.add_argument('--input',required=True);p.add_argument('--spec',required=True);p.add_argument('--output',required=True);a=p.parse_args();r=validate(a.work,a.input,a.spec)
    with open(a.output,'x') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps(r,indent=2))
