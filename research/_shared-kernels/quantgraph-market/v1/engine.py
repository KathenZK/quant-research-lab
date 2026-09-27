"""Deterministic long-only account replay; no network, admission or promotion.

The caller owns data acceptance and closed-bar evidence. A run here is not a
ResearchRun until both V3 admission and full data quality independently pass.
"""
import numpy as np
import pandas as pd


def ema_sma_seed(close, n):
    n = int(n)
    out = np.full(len(close), np.nan)
    if len(close) >= n:
        out[n - 1] = np.mean(close[:n])
        for i in range(n, len(close)):
            out[i] = (2 / (n + 1)) * close[i] + (1 - 2 / (n + 1)) * out[i - 1]
    return out


def signals(bars, signal, parameters):
    close = bars.close
    n = int(parameters[0])
    if signal == 'PRICE_SMA':
        line = close.rolling(n, min_periods=n).mean()
        valid = line.notna().to_numpy()
        enter = (close > line).to_numpy() & valid
        leave = (close <= line).to_numpy() & valid
    elif signal == 'ZSCORE_REVERSION':
        sd = close.rolling(n, min_periods=n).std(ddof=1)
        z = (close - close.rolling(n, min_periods=n).mean()) / sd.replace(0, np.nan)
        valid = z.notna().to_numpy()
        enter = (z < -parameters[1]).to_numpy() & valid
        leave = (z >= -parameters[1]).to_numpy() & valid
    elif signal == 'EMA_CROSSOVER':
        fast = ema_sma_seed(close.to_numpy(), n)
        slow = ema_sma_seed(close.to_numpy(), parameters[1])
        valid = np.isfinite(fast) & np.isfinite(slow)
        above = fast > slow
        prior_above = np.r_[False, above[:-1]]
        prior_valid = np.r_[False, valid[:-1]]
        liquid = bars.volume.to_numpy() > 0
        enter = above & ~prior_above & valid & prior_valid & liquid
        leave = ~above & prior_above & valid & prior_valid & liquid
    else:
        raise ValueError('Unsupported explicitly frozen signal')
    return enter, leave


def replay(bars, contract, parameters=None, cost_multiplier=1.0):
    p = parameters if parameters is not None else contract['parameters']
    numeric = bars[['open', 'high', 'low', 'close', 'volume']].to_numpy(dtype=float)
    if not np.isfinite(numeric).all() or (numeric[:, :4] <= 0).any() or (numeric[:, 4] < 0).any():
        raise ValueError('Invalid observed prices or volumes')
    if (bars.high < bars[['open', 'close', 'low']].max(axis=1)).any() or (bars.low > bars[['open', 'close', 'high']].min(axis=1)).any():
        raise ValueError('Invalid OHLC range')
    ts = pd.DatetimeIndex(bars.ts)
    if ts.tz is None or str(ts.tz) != 'UTC' or not ts.is_monotonic_increasing or ts.has_duplicates:
        raise ValueError('Sorted unique UTC bars required')
    if not (ts[1:] - ts[:-1] == pd.Timedelta(minutes=contract['minutes'])).all():
        raise ValueError('Missing bars; no forward fill')
    if cost_multiplier <= 0:
        raise ValueError('Positive cost stress required')
    enter, leave = signals(bars, contract['signal'], p)
    fee = contract['fee_bps'] * cost_multiplier / 10000
    slip = contract['slippage_bps'] * cost_multiplier / 10000
    if not 0 <= fee < 1 or not 0 <= slip < 1:
        raise ValueError('Invalid execution costs')
    cash = prior_equity = float(contract['initial_cash'])
    qty, entry_price, entry_spend = 0., None, None
    entry_ts = None
    rows, fills, trades = [], [], []
    start = pd.Timestamp(contract['evaluation_start'])
    stop = contract.get('stop_loss_fraction')
    take = contract.get('take_profit_fraction')
    for i, bar in enumerate(bars.itertuples(index=False)):
        if ts[i] < start:
            continue
        bar_fee = bar_slip = notional = 0.
        held = qty > 0
        def sell(raw_price, reason):
            nonlocal cash, qty, bar_fee, bar_slip, notional
            filled = raw_price * (1 - slip)
            amount = qty * filled
            charge = amount * fee
            cash += amount - charge
            bar_fee += charge
            bar_slip += qty * (raw_price - filled)
            notional += amount
            fills.append(dict(ts=str(ts[i]), side='sell', price=filled, qty=qty, fee=charge, reason=reason))
            trades.append(dict(entry_ts=str(entry_ts), exit_ts=str(ts[i]), entry_price=entry_price,
                               exit_price=filled, qty=qty, pnl=amount-charge-entry_spend,
                               return_net=(amount-charge)/entry_spend-1, reason=reason))
            qty = 0.
        if i and leave[i - 1] and qty:
            sell(bar.open, 'prior_closed_signal')
        if i and enter[i - 1] and not qty:
            entry_price = bar.open * (1 + slip)
            entry_spend = cash
            qty = cash / (entry_price * (1 + fee))
            charge = qty * entry_price * fee
            bar_fee += charge
            bar_slip += qty * (entry_price - bar.open)
            notional += qty * entry_price
            cash = 0.
            held = True
            entry_ts = ts[i]
            fills.append(dict(ts=str(ts[i]), side='buy', price=entry_price, qty=qty, fee=charge, reason='prior_closed_signal'))
        ambiguous = False
        if qty and (stop is not None or take is not None):
            stop_price = entry_price * (1 - stop) if stop is not None else None
            take_price = entry_price * (1 + take) if take is not None else None
            hit_stop = stop_price is not None and bar.low <= stop_price
            hit_take = take_price is not None and bar.high >= take_price
            ambiguous = bool(hit_stop and hit_take)
            if hit_stop:
                sell(min(bar.open, stop_price), 'stop_gap' if bar.open < stop_price else 'stop')
            elif hit_take:
                sell(take_price, 'take_profit_conservative')
        # Terminal liquidation is a declared end-of-study close, never a signal.
        if i == len(bars) - 1 and qty:
            sell(bar.close, 'end_of_study')
        equity = cash + qty * bar.close
        rows.append(dict(ts=ts[i], equity=equity, return_net=equity/prior_equity-1,
                         fee=bar_fee, slippage_cost=bar_slip, traded_notional=notional,
                         turnover=notional/prior_equity, exposure=float(held or qty > 0),
                         ambiguous_bracket=ambiguous))
        prior_equity = equity
    if not rows:
        raise ValueError('No observed evaluation bars')
    return pd.DataFrame(rows), pd.DataFrame(fills), pd.DataFrame(trades)
