"""Declared catalog SMA20 state hypothesis. No order/account/data-loading code."""
if not __debug__:
    raise RuntimeError('M3710 rejects Python -O')
from decimal import Decimal, localcontext, ROUND_HALF_EVEN

PERIOD = 20
COLUMNS = ['canonical_feature_index', 'open_time', 'close_time', 'close',
           'sma20', 'ready', 'raw_entry', 'raw_exit']

def features(rows):
    """Current close included; recompute each sum left-to-right in Decimal50."""
    prices = []
    out = []
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        for index, row in enumerate(rows):
            if not isinstance(row['close'], str):
                raise TypeError('Close must retain original decimal text')
            price = Decimal(row['close'])
            if not price.is_finite() or price <= 0:
                raise ValueError('Close must be positive finite decimal text')
            prices.append(price)
            ready = index >= PERIOD - 1
            average = None
            if ready:
                total = Decimal(0)
                for previous in prices[index - PERIOD + 1:index + 1]:
                    total = total + previous
                average = total / Decimal(PERIOD)
            out.append(dict(canonical_feature_index=index, open_time=int(row['open_time']),
                close_time=int(row['close_time']), close=row['close'],
                sma20='' if average is None else str(average), ready=int(ready),
                raw_entry=int(ready and price > average),
                raw_exit=int(ready and price <= average)))
    return out
