"""M1266 isolated frozen consumer v1. No network, global state, or shared kernel.

Decimal50 HALF_EVEN. Price inputs are text. Strategy decisions consume completed
closes only. Account opens run before each close. No historical command is exposed
here; run_m1266_v1.py requires the exact C0 and coordinator release first.
"""
from dataclasses import dataclass, asdict
from decimal import Decimal as D, localcontext, ROUND_HALF_EVEN
import datetime as dt
import json

PRECISION = 50
ROUNDING = ROUND_HALF_EVEN
INITIAL = D('100000')
ALLOCATION = D('0.9')
TRAIL = D('0.95')
PERIODS = (20, 50, 100)


def decimal_context():
    ctx = localcontext()
    return ctx


def decimal50(fn):
    def call(*args, **kwargs):
        with localcontext() as ctx:
            ctx.prec = PRECISION
            ctx.rounding = ROUNDING
            return fn(*args, **kwargs)
    call.__name__ = fn.__name__
    call.__doc__ = fn.__doc__
    return call


def serial(value):
    """Fixed-point Decimal text without quantization; preserve trailing zeroes."""
    if isinstance(value, D):
        if not value.is_finite():
            raise ValueError('nonfinite decimal')
        return format(value, 'f')
    if isinstance(value, dict):
        return {str(k): serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    return value


def canonical_bytes(value):
    return (json.dumps(serial(value), ensure_ascii=False, sort_keys=True,
                       indent=2, allow_nan=False) + '\n').encode('utf-8')


@dataclass(frozen=True)
class Case:
    name: str
    fee_bps_each_side: int
    slippage_bps_each_side: int
    delay_bars: int

    def __post_init__(self):
        if self.delay_bars not in (1, 2):
            raise ValueError('lag must be 1 or 2')
        if self.fee_bps_each_side < 0 or not 0 <= self.slippage_bps_each_side < 10000:
            raise ValueError('invalid costs')


CASES = (Case('base', 8, 2, 1), Case('fee0', 0, 2, 1),
         Case('fee20', 20, 2, 1), Case('delay2', 8, 2, 2))


class EMA:
    @decimal50
    def __init__(self, period):
        if period <= 0:
            raise ValueError('period')
        self.period = period
        self.alpha = D(2) / D(period + 1)
        self.count = 0
        self.total = D(0)
        self.value = None

    @decimal50
    def update(self, close):
        close = D(close)
        if not close.is_finite() or close <= 0:
            raise ValueError('invalid close')
        self.count += 1
        if self.count <= self.period:
            self.total = self.total + close
            if self.count == self.period:
                self.value = self.total / D(self.period)
        else:
            self.value = self.value + self.alpha * (close - self.value)
        return self.value


@decimal50
def ema_series(closes, period):
    e = EMA(period)
    return [e.update(c) for c in closes]


@decimal50
def entry_condition(close, ema20, ema50, ema100):
    return None not in (ema20, ema50, ema100) and ema20 > close > ema50 > ema100


@decimal50
def exit_condition(close, ema50, holding_high):
    return close <= ema50 or close < TRAIL * holding_high


class Account:
    @decimal50
    def __init__(self, case, initial=INITIAL):
        self.case = case
        self.cash = D(initial)
        self.qty = D(0)
        self.high = None
        self.pending = None
        self.fee_rate = D(case.fee_bps_each_side) / D(10000)
        self.slip_rate = D(case.slippage_bps_each_side) / D(10000)
        self.fills = []
        self.rejections = []
        self.intents = []
        self.events = []
        self.trips = []
        self.entry_fill = None

    def snapshot(self):
        return dict(cash=self.cash, qty=self.qty, holding_high=self.high,
                    pending=None if self.pending is None else dict(self.pending))

    @decimal50
    def queue_buy(self, index, close):
        assert self.qty == 0 and self.pending is None
        target = ALLOCATION * self.cash / close - self.qty
        self.pending = dict(side='BUY', signal_index=index,
                            due_index=index + self.case.delay_bars,
                            signal_close=close, qty=target, high_seed=close)
        self.intents.append(dict(self.pending))
        self.events.append(dict(index=index, phase='close', event='BUY_SUBMITTED',
                                order=dict(self.pending)))

    @decimal50
    def queue_sell(self, index, close):
        assert self.qty > 0 and self.pending is None
        self.pending = dict(side='SELL', signal_index=index,
                            due_index=index + self.case.delay_bars,
                            signal_close=close, qty=self.qty, high_seed=self.high)
        self.intents.append(dict(self.pending))
        self.events.append(dict(index=index, phase='close', event='SELL_SUBMITTED',
                                order=dict(self.pending)))

    @decimal50
    def on_open(self, index, raw_open):
        raw_open = D(raw_open)
        assert raw_open.is_finite() and raw_open > 0
        order = self.pending
        if order is None:
            return None
        assert order['due_index'] >= index, 'overdue order / skipped bar'
        if order['due_index'] != index:
            return None
        before = self.snapshot()
        side = order['side']
        price = raw_open * (D(1) + self.slip_rate if side == 'BUY' else D(1) - self.slip_rate)
        notional = order['qty'] * price
        fee = notional * self.fee_rate
        self.pending = None
        if side == 'BUY':
            assert self.qty == 0 and self.high is None
            required = notional + fee
            if required > self.cash:
                event = dict(index=index, phase='open', event='REJECTED_INSUFFICIENT_CASH',
                             order=dict(order), raw_open=raw_open, executed_price=price,
                             principal=notional, quoted_fee=fee, required=required,
                             available=self.cash, actual_fee=D(0), before=before,
                             after=self.snapshot())
                self.rejections.append(event)
                self.events.append(event)
                return event
            self.cash = self.cash - required
            self.qty = order['qty']
            self.high = order['high_seed']
            fill = dict(index=index, side=side, order=dict(order), raw_open=raw_open,
                        price=price, qty=self.qty, notional=notional, fee=fee,
                        required=required, before=before, after=self.snapshot())
            self.entry_fill = fill
        else:
            assert side == 'SELL' and self.qty > 0 and order['qty'] == self.qty
            proceeds = notional - fee
            self.cash = self.cash + proceeds
            self.qty = D(0)
            self.high = None
            fill = dict(index=index, side=side, order=dict(order), raw_open=raw_open,
                        price=price, qty=order['qty'], notional=notional, fee=fee,
                        proceeds=proceeds, before=before, after=self.snapshot())
            assert self.entry_fill is not None
            cost = self.entry_fill['required']
            self.trips.append(dict(entry_index=self.entry_fill['index'], exit_index=index,
                                   qty=order['qty'], entry_cost=cost, sale_proceeds=proceeds,
                                   buy_fee=self.entry_fill['fee'], sell_fee=fee,
                                   net_pnl=proceeds-cost, net_return=proceeds/cost-D(1)))
            self.entry_fill = None
        self.fills.append(fill)
        self.events.append(dict(index=index, phase='open', event=side+'_FILLED', fill=fill))
        assert self.cash >= 0
        return fill

    @decimal50
    def on_close(self, index, close, ema20, ema50, ema100, control=False):
        close = D(close)
        held = self.qty > 0
        if held:
            assert self.high is not None
            self.high = max(self.high, close)
        raw_entry = entry_condition(close, ema20, ema50, ema100)
        raw_exit = held and ema50 is not None and exit_condition(close, ema50, self.high)
        action = 'HOLD'
        if control:
            action = 'CONTROL_HOLD'
        elif self.pending is not None:
            action = 'RETAIN_PENDING'
        elif held:
            if raw_exit:
                self.queue_sell(index, close)
                action = 'SELL_SUBMITTED'
        elif raw_entry:
            self.queue_buy(index, close)
            action = 'BUY_SUBMITTED'
        equity = self.cash + self.qty * close
        return dict(index=index, close=close, ema20=ema20, ema50=ema50,
                    ema100=ema100, raw_entry=raw_entry, raw_exit=bool(raw_exit),
                    action=action, equity=equity, **self.snapshot())


@decimal50
def statistics(states, fills, rejections, trips, initial=INITIAL):
    if not states:
        raise ValueError('empty evaluation')
    previous = D(initial)
    peak = D(initial)
    returns = []
    drawdowns = []
    month_ends = {}
    for state in states:
        nav = state['equity']
        returns.append(nav / previous - D(1))
        peak = max(peak, nav)
        drawdowns.append(nav / peak - D(1))
        previous = nav
        date = dt.datetime.fromtimestamp(int(state['open_time']) / 1000, dt.timezone.utc)
        month_ends[date.strftime('%Y-%m')] = nav
    n = len(returns)
    mean = sum(returns, D(0)) / D(n)
    variance = sum(((r - mean) ** 2 for r in returns), D(0)) / D(n - 1) if n > 1 else D(0)
    constant_returns = all(r == returns[0] for r in returns)
    sharpe = mean / variance.sqrt() * D(365).sqrt() if variance and not constant_returns else None
    prior = D(initial)
    months = []
    for month, nav in month_ends.items():
        months.append(dict(month=month, start_equity=prior, end_equity=nav,
                           return_value=nav / prior - D(1)))
        prior = nav
    metrics = dict(observations=n, initial_equity=D(initial), final_equity=previous,
                   total_return=previous/D(initial)-D(1),
                   CAGR=(previous/D(initial)) ** (D(365)/D(n))-D(1),
                   Sharpe=sharpe, max_drawdown=min(drawdowns),
                   exposure=D(sum(s['qty'] > 0 for s in states))/D(n),
                   fill_count=len(fills), rejected_order_count=len(rejections),
                   closed_roundtrips=len(trips), monthly_count=len(months),
                   fees_paid=sum((f['fee'] for f in fills), D(0)))
    return dict(metrics=metrics, daily_returns=returns, drawdowns=drawdowns,
                monthly=months)


@decimal50
def run(bars, case, warmup=100, control=False):
    """Pure deterministic consumer. Synthetic QA may call directly.

    Only the guarded runner may feed frozen historical input. The caller must
    provide exactly the selected input prefix; we never prepend archive rows.
    """
    if warmup != 100 or len(bars) <= warmup:
        raise ValueError('requires exactly 100 selected warmup bars plus evaluation')
    account = Account(case)
    emas = [EMA(n) for n in PERIODS]
    features = []
    states = []
    for index, bar in enumerate(bars):
        if index >= warmup:
            account.on_open(index, D(bar['open']))
        close = D(bar['close'])
        values = [e.update(close) for e in emas]
        features.append(dict(index=index, open_time=int(bar['open_time']), close=close,
                             ema20=values[0], ema50=values[1], ema100=values[2],
                             warmup=index < warmup))
        if index == warmup - 1:
            assert all(v is not None for v in values)
            if control:
                if case != CASES[0]:
                    raise ValueError('only frozen base buyhold authorized')
                account.queue_buy(index, close)
        elif index >= warmup:
            state = account.on_close(index, close, *values, control=control)
            state['open_time'] = int(bar['open_time'])
            states.append(state)
    summary = statistics(states, account.fills, account.rejections, account.trips)
    return dict(schema='m1266-fixedqty/v1', case=asdict(case), control=control,
                warmup_rows=warmup, evaluation_rows=len(states), features=features,
                decisions=states, fills=account.fills, rejections=account.rejections,
                intents=account.intents, events=account.events, closed_trips=account.trips,
                terminal=account.snapshot(), **summary)
