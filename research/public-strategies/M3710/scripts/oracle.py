"""Independent rational SMA oracle; no production signals or Decimal arithmetic."""
if not __debug__:
    raise RuntimeError('M3710 rejects Python -O')
from fractions import Fraction


def round_significant(value, precision=50):
    """Rational implementation of decimal significant-digit half-even rounding."""
    if value == 0:
        return Fraction(0)
    sign = -1 if value < 0 else 1
    value = abs(value)
    n, d = value.numerator, value.denominator
    exponent = len(str(n)) - len(str(d))
    power = Fraction(10 ** exponent) if exponent >= 0 else Fraction(1, 10 ** (-exponent))
    if value < power:
        exponent -= 1
    shift = precision - 1 - exponent
    numerator = n * 10 ** shift if shift >= 0 else n
    denominator = d if shift >= 0 else d * 10 ** (-shift)
    quotient, remainder = divmod(numerator, denominator)
    if 2 * remainder > denominator or (2 * remainder == denominator and quotient % 2):
        quotient += 1
    return sign * (Fraction(quotient, 10 ** shift) if shift >= 0 else Fraction(quotient * 10 ** (-shift)))


def expected_features(rows):
    output = []
    for index, row in enumerate(rows):
        ready = index >= 19
        average = None
        if ready:
            total = Fraction(0)
            for prior in range(index - 19, index + 1):
                total = round_significant(total + Fraction(rows[prior]['close']))
            average = round_significant(total / 20)
        price = Fraction(row['close'])
        output.append(dict(ready=ready, sma20=average,
            entry=ready and price > average, exit=ready and price <= average))
    return output


def verify_features(rows, saved):
    expected = expected_features(rows)
    assert len(rows) == len(saved)
    for index, (row, actual, want) in enumerate(zip(rows, saved, expected)):
        assert int(actual['canonical_feature_index']) == index
        for key in ['open_time', 'close_time']:
            assert int(actual[key]) == int(row[key]), (index, key)
        assert actual['close'] == row['close']
        assert int(actual['ready']) == int(want['ready'])
        assert int(actual['raw_entry']) == int(want['entry'])
        assert int(actual['raw_exit']) == int(want['exit'])
        if want['ready']:
            assert Fraction(actual['sma20']) == want['sma20'], index
        else:
            assert actual['sma20'] == ''
    return expected
