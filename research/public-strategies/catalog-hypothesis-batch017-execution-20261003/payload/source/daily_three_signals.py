"""Unfrozen batch017 per-ID signals only. No account, order queue or market I/O.

The eventual SHA-pinned shared execution kernel owns orders and holdings.
For M1349 it supplies the count AFTER incrementing the current completed
close while actually long, and preserves the mandatory-exit latch until sale.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext, ROUND_HALF_EVEN

IDS = ('M1346', 'M1349', 'M1270')
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

def _decimal(value):
    if not isinstance(value, (str, Decimal)):
        raise TypeError('Price must be original decimal text or Decimal, never float')
    value = Decimal(value)
    if not value.is_finite() or value <= 0:
        raise ValueError('Price must be finite and positive')
    return value

def feature_at_close(strategy_id, rows, index):
    """Pure closed-bar features; reads only rows <= index and no position state."""
    if strategy_id not in IDS:
        raise ValueError('Strategy is outside the batch017 allocation')
    if type(index) is not int or not 0 <= index < len(rows):
        raise ValueError('Invalid closed-bar index')
    row = rows[index]
    ms = int(row['open_time'])
    stamp = EPOCH + timedelta(milliseconds=ms)
    if ms % 86400000:
        raise ValueError('Expected native UTC daily open timestamp')
    close = _decimal(row['close'])
    ready = strategy_id == 'M1270' or index >= 25
    lag = _decimal(rows[index-25]['close']) if index >= 25 and strategy_id != 'M1270' else None
    roc = None
    raw_entry = False
    price_or_calendar_exit = False
    with localcontext() as ctx:
        ctx.prec = 50
        ctx.rounding = ROUND_HALF_EVEN
        if strategy_id == 'M1346' and ready:
            raw_entry, price_or_calendar_exit = close > lag, close < lag
        elif strategy_id == 'M1349' and ready:
            roc = close / lag - Decimal(1)
            raw_entry = roc < Decimal('-0.10')
        elif strategy_id == 'M1270':
            raw_entry, price_or_calendar_exit = stamp.weekday() == 6, stamp.weekday() == 0
    return dict(index=index, open_time=ms, bar_date=stamp.date().isoformat(),
                signal_available_ms=ms + 86400000, weekday=stamp.weekday(),
                ready=ready, close=close, lag25_close=lag, roc25=roc,
                raw_entry=raw_entry, price_or_calendar_exit=price_or_calendar_exit)

def events_at_close(strategy_id, rows, index, *, held_completed_bars=0,
                    mandatory_exit_latched=False):
    """Pure event adapter; held count and latch come from actual kernel state.

    The kernel must increment entry close to 1 before this call. Opposite-event
    cancellation precedes position gating except that a mandatory time25 sell
    cannot be canceled by entry. This function neither schedules nor fills.
    """
    if type(held_completed_bars) is not int or held_completed_bars < 0:
        raise ValueError('Held completed bars must be a nonnegative integer')
    if mandatory_exit_latched and held_completed_bars == 0:
        raise ValueError('A flat account cannot retain a mandatory-exit latch')
    feature = feature_at_close(strategy_id, rows, index)
    mandatory = strategy_id == 'M1349' and (held_completed_bars >= 25 or mandatory_exit_latched)
    raw_exit = mandatory if strategy_id == 'M1349' else feature['price_or_calendar_exit']
    return dict(**feature, raw_exit=raw_exit, mandatory_exit=mandatory,
                exit_reason='time25' if mandatory else ('calendar_monday' if strategy_id == 'M1270' and raw_exit else ('momentum25_down' if raw_exit else None)),
                entry_reason={'M1346':'momentum25_up','M1349':'roc25_below_minus10','M1270':'calendar_sunday'}[strategy_id] if feature['raw_entry'] else None)

def build_features(strategy_id, rows):
    return [feature_at_close(strategy_id, rows, i) for i in range(len(rows))]
