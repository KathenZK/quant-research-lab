"""Independent Decimal z-score and account validation for M0233 adaptation."""
import argparse
import csv
from decimal import Decimal, getcontext
import hashlib
import importlib.util
import json
from pathlib import Path

getcontext().prec = 40
D = Decimal
FAMILY = Path(__file__).resolve().parents[1]


def read(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def verify(input_path, results):
    assert hashlib.sha256(input_path.read_bytes()).hexdigest() == "48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5"
    raw = read(input_path)
    closes = [D(r["close"]) for r in raw]
    source = []
    zs = []
    for i in range(len(raw)):
        if i < 19:
            zs.append(None)
            source.append(0)
            continue
        sample = closes[i-19:i+1]
        average = sum(sample)/D(20)
        variance = sum((x-average)**2 for x in sample)/D(19)
        z = (closes[i]-average)/variance.sqrt() if variance else None
        zs.append(z)
        source.append(0 if z is None else 1 if z < D('-1.5') else -1 if z > D('1.5') else 0)
    numeric_checks = 0
    max_error = 0.0

    def near(actual, expected):
        nonlocal numeric_checks, max_error
        error = abs(float(actual)-float(expected))
        max_error = max(max_error, error)
        assert error <= 1e-7 + abs(float(expected))*1e-11, (actual,expected)
        numeric_checks += 1

    for name, fee, lag, benchmark in (("base",D('.0008'),1,False),("fee0",D(0),1,False),("fee20",D('.002'),1,False),("lag2",D('.0008'),2,False),("buy_hold",D('.0008'),1,True)):
        nav = read(results/f'{name}-nav.csv')
        trades = read(results/f'{name}-trades.csv')
        assert len(nav) == 731
        cash, quantity, peak = D(100000), D(0), D(100000)
        j = 0
        for n, row in enumerate(raw[31:]):
            target = 1 if benchmark else max(0,source[31+n-lag])
            side = 'BUY' if target and quantity == 0 else 'SELL' if not target and quantity else None
            if side:
                old_quantity = quantity
                price = D(row['open'])*(D('1.0002') if side == 'BUY' else D('.9998'))
                if side == 'BUY':
                    amount = cash * D('.95')
                    quantity = amount/price
                    fee_paid = amount*fee
                    cash *= 1-D('.95')*(1+fee)
                else:
                    amount = quantity*price
                    fee_paid = amount*fee
                    cash += amount*(1-fee)
                    quantity = D(0)
                t = trades[j]
                assert t['side'] == side and t['date'] == nav[n]['date']
                if not benchmark:
                    from datetime import datetime, timezone
                    expected_date = datetime.fromtimestamp(int(raw[31+n-lag]['open_time'])/1000,timezone.utc).date().isoformat()
                    assert t['signal_date'] == expected_date
                for key, value in (('quantity',quantity if side=='BUY' else old_quantity),('price',price),('fee',fee_paid),('cash_after',cash),('position_after',quantity)):
                    near(t[key],value)
                j += 1
            equity = cash+quantity*D(row['close'])
            peak = max(peak,equity)
            for key,value in (('equity',equity),('cash',cash),('quantity',quantity),('drawdown',equity/peak-1)):
                near(nav[n][key],value)
            assert int(nav[n]['target']) == target
        assert j == len(trades)
    s = importlib.util.spec_from_file_location('m0233_run',FAMILY/'scripts/run_replay.py')
    module = importlib.util.module_from_spec(s)
    s.loader.exec_module(module)
    config = json.loads((FAMILY/'specs/M0233-first-replay.json').read_text())
    rows = module.load(input_path)
    actual = module.signals(rows,config)
    for i, record in enumerate(actual):
        assert record['source_position'] == source[i]
        if zs[i] is not None:
            near(record['z'],zs[i])
    # Independently reproduce the inspected source's pandas rolling ddof=1 semantics.
    import pandas as pd
    series = pd.Series([float(x) for x in closes])
    pandas_z = (series-series.rolling(20).mean())/series.rolling(20).std()
    pandas_pos = pd.Series(0,index=series.index)
    pandas_pos[pandas_z < -1.5] = 1
    pandas_pos[pandas_z > 1.5] = -1
    pandas_pos[pandas_z.abs() < .5] = 0
    assert pandas_pos.tolist() == source
    constant = [dict(r,close=100.) for r in rows[:25]]
    assert all(r['source_position']==0 for r in module.signals(constant,config))
    assert module.signals(rows,dict(config,z_exit=.1)) == actual
    reference, trades = module.run(rows,config)
    mutated = [dict(r) for r in rows]
    for r in mutated:
        if r['date'] >= '2024-07-01':
            for field in ('open','high','low','close'):
                r[field] *= 1.7
    changed, changed_trades = module.run(mutated,config)
    assert [r for r in reference if r['date']<'2024-07-01'] == [r for r in changed if r['date']<'2024-07-01']
    assert [r for r in trades if r['date']<'2024-07-01'] == [r for r in changed_trades if r['date']<'2024-07-01']
    return dict(status='PASS',independent_method='Decimal 40-digit rolling sample variance and separate cash ledger; pandas source signal cross-check',configurations=5,daily_rows=3655,signal_rows=762,numeric_comparisons=numeric_checks,max_absolute_difference=max_error,future_perturbation='PASS: prices from 2024-07-01 multiplied by1.7; all earlier NAV/trades identical',zero_variance='PASS flat',z_exit_redundancy='PASS .1 and .5 identical',fidelity_class='ADAPTATION',strict_reproduction=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--results',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    result = verify(a.input,a.results)
    with a.output.open('x') as f:
        json.dump(result,f,indent=2)
        f.write('\n')
    print(json.dumps(result))
