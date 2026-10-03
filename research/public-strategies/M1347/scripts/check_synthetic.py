"""Artificial prices and calendars only; no historical input or result reads."""
import argparse
import copy
import json
from datetime import date, timedelta
from decimal import Decimal as D, localcontext, ROUND_HALF_EVEN
from pathlib import Path
from kernel_loader import FAMILY, load
from signals import features
from oracle import verify_features
from run_replay import write_results

engine = load('engine')
account_qa = load('verify_account')
DAY = 86400000
EPOCH = date(1970, 1, 1)

def bars(start, count, constant=None):
    rows = []
    ms = (date.fromisoformat(start) - EPOCH).days * DAY
    for i in range(count):
        price = constant if constant is not None else str(100 + ((i * 7) % 19))
        rows.append(dict(zip(engine.COLS, [str(ms + i * DAY), price, price, price, price, '0',
                         str(ms + (i + 1) * DAY - 1), '0', '0', '0', '0', '0'])))
    return rows

def check(destination):
    engine.environment(FAMILY / 'specs/environment-lock.json')
    spec = json.loads((FAMILY / 'specs/protocol-v1.json').read_text())
    assert not destination.exists()
    destination.mkdir(parents=True)
    tests = []
    def passed(label): tests.append(label)

    # Gregorian leap cycle; expected oracle uses date subtraction rather than monthrange.
    cycle = bars('2000-01-01', 146097, '100')
    f = features(cycle)
    verify_features(cycle, f)
    assert sum(x['raw_entry'] for x in f) == sum(x['raw_exit'] for x in f) == 4800
    passed('400 Gregorian years / 146097 dates / 4800 entries and exits; independent calendar')
    for y, expected in [(2000, '2000-02-27'), (2023, '2023-02-26'), (2024, '2024-02-27'), (2100, '2100-02-26')]:
        f = features(bars(f'{y}-02-01', 29 if y in (2000, 2024) else 28, '10'))
        assert [x['utc_date'] for x in f if x['raw_entry']] == [expected]
        assert [x['utc_date'] for x in f if x['raw_exit']] == [f'{y}-02-03']
        passed(f'February leap/century {y}')
    for month, last in [(1, 29), (4, 28), (12, 29)]:
        f = features(bars(f'2023-{month:02}-01', last, '10'))
        assert f[-1]['raw_entry'] == 1
        passed(f'31/30 day month and year transition month={month}')
    try: features([dict(bars('2023-01-01', 1)[0], open_time='1672531200001')])
    except AssertionError: passed('Off-midnight calendar label rejects')
    else: raise AssertionError('offgrid accepted')

    rows = bars('2022-12-01', 762)
    feat = features(rows)
    expected = verify_features(rows, feat)
    assert feat[28]['raw_entry'] == 1 and feat[59]['raw_entry'] == 1
    assert feat[33]['raw_exit'] == 1
    # A full native12 artificial input exercises the actual input QA without touching market data.
    synthetic_input = destination / 'synthetic-native12.csv'
    engine.csvout(synthetic_input, rows, engine.COLS)
    synthetic_spec = copy.deepcopy(spec)
    synthetic_spec['input'].update(bytes=synthetic_input.stat().st_size, sha256=engine.sha(synthetic_input))
    assert engine.load_input(synthetic_input, synthetic_spec) == rows
    passed('Artificial native12 exact hash/grid/762rows/731eval accepted')
    for name, mutation in [('duplicate', lambda x: x.__setitem__(50, dict(x[49]))),
                           ('missing', lambda x: x.pop(50)),
                           ('nan', lambda x: x[50].__setitem__('close', 'NaN')),
                           ('negativevolume', lambda x: x[50].__setitem__('volume', '-1')),
                           ('OHLCbounds', lambda x: x[50].__setitem__('high', '1'))]:
        changed = copy.deepcopy(rows)
        mutation(changed)
        path = destination / f'rejected-{name}.csv'
        engine.csvout(path, changed, engine.COLS)
        modified = copy.deepcopy(spec)
        modified['input'].update(bytes=path.stat().st_size, sha256=engine.sha(path))
        try: engine.load_input(path, modified)
        except (AssertionError, ArithmeticError, ValueError): passed(f'Input rejection {name}')
        else: raise AssertionError(f'Invalid input accepted {name}')

    cuts = [32, 34, 58, 59, 60, 61, 64, 86, 90, 91, 365, 397, 455, 759, 761]
    for case in spec['cases']:
        result = engine.simulate(rows, feat, case)
        expected_buy = '2023-01-30T00:00:00Z' if case['delay_bars'] == 1 else '2023-01-31T00:00:00Z'
        expected_sell = '2023-02-04T00:00:00Z' if case['delay_bars'] == 1 else '2023-02-05T00:00:00Z'
        assert result['fills'][0]['effective_time'] == expected_buy
        assert result['fills'][1]['effective_time'] == expected_sell
        assert result['fills'][0]['signal_index'] == 28
        assert len(result['fills']) == 47 and len(result['roundtrips']) == 23
        assert result['summary']['final_cash'] == '0' and D(result['summary']['final_quantity']) > 0
        assert result['summary']['terminal_pending'] is None
        assert len(result['monthly']) == 24 and len(result['nav']) == 731
        assert all(D(x['quantity']) == 0 for x in result['nav'][:29 if case['delay_bars'] == 1 else 30])
        passed(case['name'] + ' calendar lag/warmup-flat/47fills/terminal inventory/24months')
        for cut in cuts:
            prefix_features = features(rows[:cut])
            assert prefix_features == feat[:cut]
            prefix = engine.simulate(rows[:cut], prefix_features, case)
            changed = copy.deepcopy(rows)
            for r in changed[cut:]:
                for field in ['open', 'high', 'low', 'close']: r[field] = '999'
            future_features = features(changed)
            assert [(x['raw_entry'], x['raw_exit']) for x in future_features] == [(x['raw_entry'], x['raw_exit']) for x in feat]
            future = engine.simulate(changed, future_features, case)
            limit = cut - 31
            for key in ['nav', 'decisions']:
                assert prefix[key] == result[key][:limit] == future[key][:limit]
            for key in ['fills', 'pending']:
                baseline = [x for x in result[key] if x['eval_index'] < limit]
                assert prefix[key] == baseline == [x for x in future[key] if x['eval_index'] < limit]
            passed(case['name'] + ' prefix+future@' + str(cut))
        # Ending on signal close must retain unfilled intent, never infer observed end as month end.
        for cut in [60, 61]:
            short = engine.simulate(rows[:cut], features(rows[:cut]), case)
            if cut == 60 or case['delay_bars'] == 2:
                assert not short['fills'] and short['summary']['terminal_pending'] == dict(side='BUY', signal_index=28, due_index=28 + case['delay_bars'])
            else: assert len(short['fills']) == 1
        passed(case['name'] + ' truncated month/terminal pending no future fill')

    for cash in [D('100000'), D('1e-100'), D('1e-400')]:
        for fee in [0, 8, 20]:
            after, qty, a = engine.fill_order(cash, D(0), '101', 'BUY', fee, 2)
            with localcontext() as ctx:
                ctx.prec = 50; ctx.rounding = ROUND_HALF_EVEN
                assert after == 0 and D(a['notional']) + D(a['fee']) == cash
                assert D(a['notional']) == cash / (1 + D(fee) / 10000)
            assert qty > 0
            passed(f'Fullcash exact budget fee={fee} cash={cash}')
    p = dict(side='BUY', signal_index=0, due_index=2)
    assert engine.reconcile(p, False, False, False, 1, 2) == (p, [])
    assert engine.reconcile(p, True, False, False, 1, 2)[0] == p
    assert engine.reconcile(p, False, True, False, 1, 2)[0] is None
    passed('Absent retains / same-side earliest / opposite cancels before holdings')
    zero = engine.metrics([dict(equity='100000')] * 10)
    assert zero['sharpe_zero_cash'] is None and zero['max_drawdown'] == 0
    passed('Cash-only metrics zero and Sharpe null')
    write_results(rows, destination / 'synthetic-results', spec, 'SYNTHETIC_ONLY_NO_REAL_CONTROL_READ')
    receipt = account_qa.verify_account(rows, destination / 'synthetic-results', spec, expected)
    assert receipt['nav_rows'] == 2924 and receipt['fill_rows'] == 188
    receipt['source_signal'] = 'Independent ordinal/nextmonth calendar features; no Fraction price indicator exists'
    passed('Full artificial 4case output serializer and independent v1 account/metrics')
    return dict(id='M1347', status='PASS', checks=len(tests), tests=tests,
                synthetic_only=True, real_market_data_read=False, historical_strategy_runs=0,
                new_controls=0, market_requests=0, independent_synthetic_account=receipt)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--fixture-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    receipt = check(a.fixture_dir)
    engine.dump(a.output, receipt)
    print(json.dumps(dict(status=receipt['status'], checks=receipt['checks'], synthetic_only=True)))
