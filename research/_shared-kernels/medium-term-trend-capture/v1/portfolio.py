"""固定机会流的独立资金账户；只按当日已出现的单位路径事件分配资金。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def simulate_portfolio(origins, trajectories, policy, cost_id, config):
    days = pd.date_range(config['start'], pd.Timestamp(config['end']) - pd.Timedelta(days=1), freq='D')
    queue = {}
    for r in origins.to_dict('records'):
        d = pd.Timestamp(r['origin_ts']) + pd.Timedelta(days=1)
        queue.setdefault(d, []).append(r)
    for rows in queue.values():
        rows.sort(key=lambda r: (-r['liquidity'], r['symbol']))
    paths = {key: {pd.Timestamp(r['ts']): r for r in value.to_dict('records')}
             for key, value in trajectories.items()}
    cash = float(config['initial_equity'])
    active, blocked = {}, set()
    daily, actions = [], []
    peak = cash

    def action(day, oid, event, **extra):
        actions.append(dict(ts=day, origin_id=oid, policy=policy, cost_id=cost_id,
                            event=event, **extra))

    for day in days:
        today = {}
        fees, carry, slippage = 0., 0., 0.
        for oid, slot in active.items():
            row = paths[oid].get(day)
            if row is None:
                # A missing future quote is never used to force a prior sale.
                row = dict(slot['last_row'])
                row.update(ts=day, open_before=row['close_value'], open_after=row['close_value'],
                           cash_open_before=row['cash_close'], cash_open_after=row['cash_close'],
                           qty_open_before=row['qty_close'], qty_open_after=row['qty_close'],
                           entry_open=False, exit_open=False, release_open=False,
                           fee_open=0., slippage_open=0., carry_close=0., data_gap=True,
                           intraday_low_value=row['close_value'])
            today[oid] = row
            if bool(row.get('data_gap', False)) and float(row['qty_open_before']) > 0:
                blocked.add(slot['symbol'])
                if not slot.get('unresolved', False):
                    action(day, oid, 'UNRESOLVED_POSITION', symbol=slot['symbol'], budget=slot['budget'])
                slot['unresolved'] = True
        # Exits and known waiting cancellations free capital before new admissions.
        for oid in list(active):
            row, slot = today[oid], active[oid]
            if bool(row['release_open']):
                released = slot['budget'] * float(row['open_after'])
                cash += released
                fees += slot['budget'] * float(row['fee_open'])
                slippage += slot['budget'] * float(row['slippage_open'])
                action(day, oid, 'RELEASE', symbol=slot['symbol'], budget=slot['budget'],
                       released=released, pnl=released-slot['budget'], reason=row.get('release_reason', row.get('reason', '')),
                       fee=slot['budget']*float(row['fee_open']))
                del active[oid]
        nav_open = cash + sum(s['budget']*float(today[o]['open_before']) for o, s in active.items())
        batch_budget = max(0., nav_open * config['budget_fraction'])
        for origin in queue.get(day, []):
            oid, symbol = origin['origin_id'], origin['symbol']
            available = max(0., cash + sum(min(0., s['budget']*float(today[o]['cash_open_before']))
                                           for o, s in active.items()))
            reason = ('SYMBOL_DATA_UNRESOLVED' if symbol in blocked else
                      'SYMBOL_OCCUPIED' if any(s['symbol'] == symbol for s in active.values()) else
                      'SLOTS_FULL' if len(active) >= config['max_slots'] else
                      'NO_FREE_CASH' if available <= 1e-12 or batch_budget <= 0 else None)
            if reason:
                action(day, oid, 'REJECT', symbol=symbol, reason=reason, budget=0.)
                continue
            budget = min(batch_budget, available)
            row = paths[oid].get(day)
            # Only the missing quote of this very day is inspected.
            if row is None:
                action(day, oid, 'REJECT', symbol=symbol, reason='NO_EXECUTABLE_BAR_TODAY', budget=0.)
                continue
            cash -= budget
            slot = dict(symbol=symbol, budget=budget, last_row=row, unresolved=False)
            active[oid], today[oid] = slot, row
            action(day, oid, 'ADMIT', symbol=symbol, budget=budget, nav_at_batch=nav_open)
            if bool(row['release_open']):
                cash += budget * float(row['open_after'])
                action(day, oid, 'RELEASE', symbol=symbol, budget=budget,
                       released=budget*float(row['open_after']), pnl=budget*(float(row['open_after'])-1),
                       reason=row.get('release_reason', row.get('reason', '')), fee=budget*float(row['fee_open']))
                fees += budget*float(row['fee_open'])
                del active[oid]
        for oid, slot in active.items():
            row = today[oid]
            fees += slot['budget'] * float(row['fee_open'])
            slippage += slot['budget'] * float(row['slippage_open'])
            carry += slot['budget'] * float(row['carry_close'])
            if bool(row['entry_open']):
                action(day, oid, 'ENTRY', symbol=slot['symbol'], budget=slot['budget'],
                       quantity=slot['budget']*float(row['qty_open_after']),
                       fee=slot['budget']*float(row['fee_open']))
            slot['last_row'] = row
        equity = cash + sum(s['budget']*float(today[o]['close_value']) for o, s in active.items())
        all_cash = cash + sum(s['budget']*float(today[o]['cash_close']) for o, s in active.items())
        exposure = equity - all_cash
        zero_value = cash + sum(s['budget']*float(today[o]['cash_close'] if s.get('unresolved')
                                                  else today[o]['close_value']) for o, s in active.items())
        low_bound = cash + sum(s['budget']*float(today[o]['intraday_low_value']) for o, s in active.items())
        peak = max(peak, equity)
        daily.append(dict(ts=day, close_ts=day+pd.Timedelta(days=1), policy=policy, cost_id=cost_id,
                          equity=equity, free_cash=cash, total_cash=all_cash, exposure=exposure,
                          active_slots=len(active), positions=sum(float(today[o]['qty_close'])>0 for o in active),
                          unresolved_positions=sum(bool(s.get('unresolved')) for s in active.values()),
                          fee=fees, slippage=slippage, hypothetical_carry=carry,
                          drawdown=equity/peak-1., unresolved_zero_value_equity=zero_value,
                          intraday_simultaneous_low_bound=low_bound,
                          cost_cash_shortfall=all_cash < -1e-9))
    for day, rows in queue.items():
        if day > days[-1]:
            for r in rows:
                action(day, r['origin_id'], 'PENDING_AFTER_DATA_END', symbol=r['symbol'], budget=0.)
    return pd.DataFrame(daily), pd.DataFrame(actions)


def portfolio_metrics(frame, actions, config):
    initial = config['initial_equity']
    result = dict(total_return=float(frame.equity.iloc[-1]/initial-1),
                  end_equity=float(frame.equity.iloc[-1]),
                  max_drawdown=float(frame.drawdown.min()),
                  fees=float(frame.fee.sum()), slippage=float(frame.slippage.sum()),
                  hypothetical_carry=float(frame.hypothetical_carry.sum()),
                  mean_exposure_fraction=float((frame.exposure/frame.equity).mean()),
                  cost_cash_shortfall_days=int(frame.cost_cash_shortfall.sum()),
                  unresolved_positions=int(frame.unresolved_positions.iloc[-1]),
                  unresolved_zero_value_return=float(frame.unresolved_zero_value_equity.iloc[-1]/initial-1),
                  event_counts=actions.event.value_counts().to_dict(),
                  years={}, recent={})
    start_nav = initial
    for year, g in frame.groupby(frame.ts.dt.year):
        nav = np.r_[start_nav, g.equity.to_numpy()]
        result['years'][str(year)] = dict(return_=float(nav[-1]/nav[0]-1),
                                         max_drawdown=float((nav/np.maximum.accumulate(nav)-1).min()))
        start_nav = nav[-1]
    values = frame.set_index('close_ts').equity
    end = values.index[-1]
    for h in config['recent_days']:
        threshold = end - pd.Timedelta(days=h)
        prior = values[values.index <= threshold]
        baseline = float(prior.iloc[-1]) if len(prior) else initial
        sub = values[values.index > threshold]
        nav = np.r_[baseline, sub.to_numpy()]
        result['recent'][str(h)] = dict(start=str(threshold), end=str(end),
                                        return_=float(nav[-1]/nav[0]-1),
                                        max_drawdown=float((nav/np.maximum.accumulate(nav)-1).min()))
    return result
