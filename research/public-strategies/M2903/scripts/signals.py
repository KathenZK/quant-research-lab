"""Frozen catalog EMA20 event hypothesis; full canonical input, Decimal50."""
from decimal import Decimal as D, localcontext, ROUND_HALF_EVEN


def cross(previous_close, previous_ema, close, ema):
    if previous_ema is None or ema is None:
        return False, False
    return (close > ema and previous_close <= previous_ema,
            close < ema and previous_close >= previous_ema)


def features(rows):
    result = []
    with localcontext() as ctx:
        ctx.prec = 50
        ctx.rounding = ROUND_HALF_EVEN
        alpha = D(2) / D(21)
        seed = D(0)
        previous_close = previous_ema = None
        for i, row in enumerate(rows):
            close = D(row['close'])
            if not close.is_finite() or close <= 0:
                raise ValueError('close must be finite and positive')
            if i < 20:
                seed = seed + close
            ema = None if i < 19 else seed / D(20) if i == 19 else previous_ema + alpha * (close - previous_ema)
            entry, exit_ = cross(previous_close, previous_ema, close, ema)
            result.append(dict(canonical_feature_index=i, open_time=int(row['open_time']),
                               close_time=int(row['close_time']), close=row['close'],
                               ema20='' if ema is None else str(ema),
                               ready=int(ema is not None), raw_entry=int(entry), raw_exit=int(exit_)))
            previous_close, previous_ema = close, ema
    return result
