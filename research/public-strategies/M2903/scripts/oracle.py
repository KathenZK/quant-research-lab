"""Independent Fraction operation graph, rounded after each Decimal50 operation.
No signal implementation or engine state transitions imported.
"""
from decimal import Decimal as D, localcontext, ROUND_HALF_EVEN
from fractions import Fraction as F


def rounded(value):
    with localcontext() as ctx:
        ctx.prec = 50
        ctx.rounding = ROUND_HALF_EVEN
        return F(D(value.numerator) / D(value.denominator))


def expected_features(rows):
    alpha = rounded(F(2, 21))
    seed, last_ema, last_price = F(0), None, None
    output = []
    for index, row in enumerate(rows):
        price = F(row['close'])
        if index < 20:
            seed = rounded(seed + price)
        if index < 19:
            ema = None
        elif index == 19:
            ema = rounded(seed / 20)
        else:
            difference = rounded(price - last_ema)
            step = rounded(alpha * difference)
            ema = rounded(last_ema + step)
        valid = ema is not None and last_ema is not None
        output.append(dict(ema20=ema, ready=ema is not None,
                           entry=bool(valid and price > ema and last_price <= last_ema),
                           exit=bool(valid and price < ema and last_price >= last_ema)))
        last_price, last_ema = price, ema
    return output


def verify_features(rows, actual):
    expected = expected_features(rows)
    assert len(actual) == len(expected)
    for i, (row, saved, want) in enumerate(zip(rows, actual, expected)):
        assert int(saved['canonical_feature_index']) == i
        assert saved['close'] == row['close']
        for key in ('open_time', 'close_time'):
            assert saved[key] == int(row[key])
        assert (saved['ema20'] == '') if want['ema20'] is None else F(saved['ema20']) == want['ema20']
        for key, dest in [('ready', 'ready'), ('raw_entry', 'entry'), ('raw_exit', 'exit')]:
            assert int(saved[key]) == want[dest], (i, key)
    return expected
