"""R2 daily MA7 slowdown entries and tightening ATR ratchet simulation.

Copied from the frozen R1 engine; original/fixed retains its economic behavior.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Config:
    slope: float = 0.05
    reverse: bool = True
    short_exit: str = "accel1_rsi30"
    fee: float = 0.0005
    slip: float = 0.0003
    delay_hours: int = 0
    entry_mode: str = "original"
    tighten_mode: str = "fixed"
    profit_trigger_atr: float = 0.0

    def __post_init__(self):
        if self.entry_mode not in {"original", "opposite_slowdown", "absolute_slowdown", "no_slope"}:
            raise ValueError(f"Unknown entry mode: {self.entry_mode}")
        if self.tighten_mode not in {"fixed", "stall_only", "armed_daily"}:
            raise ValueError(f"Unknown tightening mode: {self.tighten_mode}")
        if not np.isfinite(self.profit_trigger_atr) or self.profit_trigger_atr < 0:
            raise ValueError("profit_trigger_atr must be finite and nonnegative")

    @property
    def name(self):
        return (f"s{self.slope:g}_rev{int(self.reverse)}_{self.short_exit}"
                f"_{self.entry_mode}_{self.tighten_mode}_p{self.profit_trigger_atr:g}")


def wilder(values, period):
    a = np.asarray(values, dtype=float)
    out = np.full(len(a), np.nan)
    seed = []
    last = np.nan
    for i, value in enumerate(a):
        if not np.isfinite(value):
            seed, last = [], np.nan
            continue
        if not np.isfinite(last):
            seed.append(value)
            if len(seed) == period:
                last = float(np.mean(seed))
        else:
            last = ((period - 1) * last + value) / period
        out[i] = last
    return out


def features(daily):
    d = daily.copy().reset_index(drop=True)
    d["timestamp"] = pd.to_datetime(d.timestamp, utc=True)
    if d.timestamp.duplicated().any() or not d.timestamp.diff().dropna().eq(pd.Timedelta(days=1)).all():
        raise ValueError("Daily gaps/duplicates must not be bridged")
    if "research_segment_id" in d and d.research_segment_id.nunique() != 1:
        raise ValueError("This experiment requires one continuous segment")
    close = d.close
    delta = close.diff()
    tr = pd.concat([d.high - d.low, (d.high - close.shift()).abs(), (d.low - close.shift()).abs()], axis=1).max(axis=1)
    tr.iloc[0] = np.nan
    d["ma"] = close.rolling(7).mean()
    d["atr"] = wilder(tr, 14)
    up = wilder(delta.clip(lower=0), 6)
    down = wilder((-delta).clip(lower=0), 6)
    with np.errstate(divide="ignore", invalid="ignore"):
        rsi = 100 - 100 / (1 + up / down)
    rsi[(up == 0) & (down == 0)] = 50
    rsi[(up > 0) & (down == 0)] = 100
    d["rsi"] = rsi
    d["slope"] = d.ma.diff() / d.atr
    d["cross"] = np.select([(close.shift() <= d.ma.shift()) & (close > d.ma), (close.shift() >= d.ma.shift()) & (close < d.ma)], [1, -1], 0)
    drop = -delta
    d["accel1"] = (drop >= d.atr.shift()) & (drop > drop.shift().clip(lower=0))
    two = drop + drop.shift()
    d["accel2"] = (drop > 0) & (drop.shift() > 0) & (two >= 1.5 * d.atr.shift(2)) & (two > (drop.shift(2) + drop.shift(3)).clip(lower=0))
    d["ready"] = (np.arange(len(d)) >= 28) & d[["ma", "atr", "rsi", "slope"]].notna().all(axis=1)
    if "research_window_valid" in d:
        d["ready"] &= d.research_window_valid.astype(bool)
    return d


def enrich_features(daily_features):
    """Add causal MA dollar steps without recalculating the frozen R1 indicators."""
    d = daily_features.copy().reset_index(drop=True)
    d["ma_step"] = d.ma.diff()
    d["prev_ma_step"] = d.ma_step.shift()
    d["ma_step_change"] = d.ma_step - d.prev_ma_step
    return d


def entry_qualification(row, side, config=Config()):
    """Return the first qualifying reason; crossing/position rules are external."""
    if side not in (-1, 1) or not bool(row.ready):
        return None
    if side * row.slope > config.slope:
        return "original"
    if config.entry_mode == "no_slope":
        return "no_slope"
    if config.entry_mode == "opposite_slowdown":
        if side * row.prev_ma_step < 0 and side * (row.ma_step - row.prev_ma_step) > 0:
            return "opposite_slowdown"
    elif config.entry_mode == "absolute_slowdown":
        if abs(row.ma_step) < abs(row.prev_ma_step):
            return "absolute_slowdown"
    return None


def simulate(hourly, daily_features, config=Config(), start=None, end=None, funding=None, carry_daily=0.0):
    """Funding=None explicitly means price-only diagnostic, never verified net."""
    h = hourly.copy()
    h["timestamp"] = pd.to_datetime(h.timestamp, utc=True)
    d = enrich_features(daily_features)
    d["timestamp"] = pd.to_datetime(d.timestamp, utc=True)
    first_start = d.loc[d.ready, "timestamp"].iloc[0] + pd.Timedelta(days=1)
    start = first_start if start is None else max(pd.Timestamp(start), first_start)
    end = h.timestamp.iloc[-1] + pd.Timedelta(hours=1) if end is None else pd.Timestamp(end)
    h = h[(h.timestamp >= start) & (h.timestamp < end)].reset_index(drop=True)
    if h.empty or not h.timestamp.diff().dropna().eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Missing/empty hourly execution grid")
    if h.timestamp.iloc[0] != start or h.timestamp.iloc[-1] + pd.Timedelta(hours=1) != end:
        raise ValueError("Incomplete requested execution window")
    day_map = {t: i for i, t in enumerate(d.timestamp)}
    fund = []
    if funding is not None:
        f = funding.copy()
        f["timestamp"] = pd.to_datetime(f.timestamp, utc=True)
        f = f[(f.timestamp >= start) & (f.timestamp <= end)].sort_values("timestamp")
        fund = f.to_dict("records")
    fidx = 0
    cash, position = 10000.0, None
    trades, marks, stops, funding_log = [], [], [], []
    pending_reverse, pending_day = None, None
    peak, adverse_mdd, exposure_hours = 10000.0, 0.0, 0
    trade_id = 0

    def equity(price):
        return cash if position is None else cash + position["side"] * position["qty"] * (price - position["entry_price"])

    def mark(timestamp, price, kind):
        nonlocal peak
        value = equity(price)
        peak = max(peak, value)
        marks.append({"timestamp": timestamp, "equity": value, "side": 0 if position is None else position["side"], "price": price, "kind": kind})

    def close_position(timestamp, price, reason, interval_end=None):
        nonlocal cash, position
        p = position
        fill = price * (1 - p["side"] * config.slip)
        pnl = p["side"] * p["qty"] * (fill - p["entry_price"])
        fee = p["qty"] * fill * config.fee
        cash += pnl - fee
        trades.append({**p, "exit_time": timestamp, "exit_interval_end": interval_end or timestamp,
                       "exit_price": fill, "exit_reference": price, "exit_reason": reason,
                       "gross_pnl": pnl, "exit_fee": fee, "net_pnl": pnl - p["entry_fee"] - fee - p["funding_paid"] - p["carry_paid"],
                       "end_equity": cash, "return_on_entry_equity": (cash - p["entry_equity"]) / p["entry_equity"]})
        position = None
        mark(timestamp, price, "exit")

    def open_position(timestamp, price, side, j, reason, cross_time):
        nonlocal position, cash, trade_id
        row = d.iloc[j]
        stop = float(row.ma - side * 1.5 * row.atr)
        if not np.isfinite(stop) or side * (price - stop) <= 0 or cash <= 0:
            return
        fill = price * (1 + side * config.slip)
        before = cash
        qty = before / (fill * (1 + config.fee))
        fee = qty * fill * config.fee
        cash -= fee
        trade_id += 1
        position = {"trade_id": trade_id, "side": side, "qty": qty, "entry_time": timestamp,
                    "entry_price": fill, "entry_reference": price, "entry_fee": fee, "entry_equity": before,
                    "entry_reason": reason, "signal_day": row.timestamp, "cross_day": cross_time,
                    "stop": stop, "funding_paid": 0.0, "carry_paid": 0.0,
                    "entry_slope": float(row.slope), "entry_rsi": float(row.rsi),
                    "qualification": entry_qualification(row, side, config),
                    "entry_ma_step": float(row.ma_step), "entry_prev_ma_step": float(row.prev_ma_step),
                    "entry_atr": float(row.atr), "initial_stop_mult": 1.5,
                    "stop_mult": 1.5, "armed": False, "tightening_days": 0,
                    "stop_floor_reached": False}
        stops.append({"timestamp": timestamp, "trade_id": trade_id, "side": side,
                      "old_stop": stop, "new_stop": stop, "signal_day": row.timestamp,
                      "old_mult": 1.5, "new_mult": 1.5, "old_armed": False, "new_armed": False,
                      "natural_candidate": stop, "stalled": False, "profit_eligible": False,
                      "expected_profit_at_close": None, "favorable_move_atr": None,
                      "tightening_trigger": "entry", "tightened": False})
        mark(timestamp, price, "entry")

    def reverse_intent(j, p):
        if not config.reverse or j < 0:
            return None
        row = d.iloc[j]
        side = -p["side"]
        # A bar that closes exactly at entry was known before entry, so exclude it.
        history = d.iloc[max(0, j - 4):j + 1]
        history = history[(history.timestamp + pd.Timedelta(days=1) > p["entry_time"]) & (history.cross != 0)]
        if history.empty or int(history.iloc[-1].cross) != side:
            return None
        if entry_qualification(row, side, config) is None or side * (row.close - row.ma) <= 0:
            return None
        return {"side": side, "cross_time": history.iloc[-1].timestamp}

    def close_profit_snapshot(row):
        """Use closed-day price and costs carried into the next day's boundary."""
        p = position
        fill = float(row.close) * (1 - p["side"] * config.slip)
        expected_profit = (p["side"] * p["qty"] * (fill - p["entry_price"])
                           - p["entry_fee"] - p["qty"] * fill * config.fee
                           - p["funding_paid"] - p["carry_paid"])
        favorable_move = p["side"] * (float(row.close) - p["entry_price"])
        eligible = (expected_profit > 0
                    and favorable_move >= config.profit_trigger_atr * p["entry_atr"])
        return {"expected_profit_at_close": expected_profit,
                "favorable_move_atr": favorable_move / p["entry_atr"],
                "profit_eligible": bool(eligible)}

    def update_stop(timestamp, row, profit_snapshot):
        p = position
        side, old_stop, old_mult, old_armed = p["side"], p["stop"], p["stop_mult"], p["armed"]
        natural = float(row.ma - side * old_mult * row.atr)
        stalled = side * (natural - old_stop) <= 1e-12 * max(1.0, abs(old_stop))
        eligible = profit_snapshot["profit_eligible"]
        trigger = "fixed"
        should_tighten = False
        if config.tighten_mode != "fixed":
            if old_mult <= 0.5:
                trigger = "at_floor"
            elif config.tighten_mode == "armed_daily" and old_armed:
                trigger, should_tighten = "armed_daily", True
            elif eligible and stalled:
                trigger, should_tighten = "stall_profit", True
                if config.tighten_mode == "armed_daily":
                    p["armed"] = True
            elif not eligible:
                trigger = "not_profitable"
            else:
                trigger = "not_stalled"
        if should_tighten:
            p["stop_mult"] = max(0.5, round(old_mult - 0.2, 10))
            p["tightening_days"] += 1
            if p["stop_mult"] == 0.5:
                p["stop_floor_reached"] = True
        # Keep R1's original arithmetic and max/min ordering for fixed mode.
        proposed = float(row.ma - side * p["stop_mult"] * row.atr)
        p["stop"] = max(old_stop, proposed) if side == 1 else min(old_stop, proposed)
        stops.append({"timestamp": timestamp, "trade_id": p["trade_id"], "side": side,
                      "old_stop": old_stop, "new_stop": p["stop"], "signal_day": row.timestamp,
                      "old_mult": old_mult, "new_mult": p["stop_mult"],
                      "old_armed": old_armed, "new_armed": p["armed"],
                      "natural_candidate": natural, "stalled": bool(stalled),
                      **profit_snapshot, "tightening_trigger": trigger,
                      "tightened": should_tighten})

    def charge_event(event, price, timestamp):
        nonlocal cash
        if position is None:
            return
        official_mark = event.get("mark_price", np.nan)
        proxy = not (official_mark is not None and np.isfinite(float(official_mark)) and float(official_mark) > 0)
        used = price if proxy else float(official_mark)
        cost = position["side"] * position["qty"] * used * float(event["funding_rate"])
        cash -= cost
        position["funding_paid"] += cost
        funding_log.append({"timestamp": event["timestamp"], "trade_id": position["trade_id"], "rate": event["funding_rate"], "mark_price_used": used, "mark_proxy": proxy, "cost": cost, "accounted_at_hour": timestamp})

    for bar in h.itertuples(index=False):
        t = bar.timestamp
        j = day_map.get(t.floor("D") - pd.Timedelta(days=1), -1)
        if j < 0:
            raise ValueError("Missing preceding closed daily bar")
        row = d.iloc[j]
        # Freeze the closed-day profitability decision before boundary funding.
        profit_snapshot = close_profit_snapshot(row) if t.hour == 0 and position is not None else None
        # Events precisely at an hour belong to the position carried into that hour.
        while fidx < len(fund) and fund[fidx]["timestamp"] <= t:
            charge_event(fund[fidx], bar.open, t)
            fidx += 1
        mark(t, bar.open, "open")
        if t.hour == 0:
            if position is not None:
                update_stop(t, row, profit_snapshot)
            pending_day = {"at": t + pd.Timedelta(hours=config.delay_hours), "j": j}

        # A gap through an existing stop always takes precedence at the open.
        stopped_this_hour = False
        if position is not None and position["side"] * (bar.open - position["stop"]) <= 0:
            intent = reverse_intent(j, position)
            close_position(t, bar.open, "stop_gap")
            pending_reverse = None if intent is None else {**intent, "at": t + pd.Timedelta(hours=1)}
            stopped_this_hour = True
            pending_day = None

        if not stopped_this_hour and pending_reverse is not None and pending_reverse["at"] <= t:
            intent = pending_reverse
            pending_reverse = None
            # Recheck the latest fully closed day if the hour crossed midnight.
            if (position is None and entry_qualification(row, intent["side"], config) is not None
                    and intent["side"] * (row.close - row.ma) > 0):
                open_position(t, bar.open, intent["side"], j, "stop_reversal", intent["cross_time"])
            pending_day = None

        if not stopped_this_hour and pending_day is not None and pending_day["at"] <= t:
            signal = d.iloc[pending_day["j"]]
            signal_j = pending_day["j"]
            pending_day = None
            if position is not None and position["side"] == -1 and config.short_exit != "none":
                expected_fill = signal.close * (1 + config.slip)
                expected_profit = position["qty"] * (position["entry_price"] - expected_fill) - position["entry_fee"] - position["qty"] * expected_fill * config.fee - position["funding_paid"] - position["carry_paid"]
                accelerated = (config.short_exit == "rsi30" or
                               (config.short_exit == "accel1_rsi30" and signal.accel1) or
                               (config.short_exit == "accel2_rsi30" and signal.accel2))
                if signal.rsi <= 30 and expected_profit > 0 and accelerated:
                    position["tp_signal_day"] = signal.timestamp
                    position["tp_signal_rsi"] = float(signal.rsi)
                    close_position(t, bar.open, config.short_exit)
                    stopped_this_hour = True  # Prevent using the same daily cross to reopen.
            if position is None and not stopped_this_hour and signal.ready:
                side = int(signal.cross)
                if side and entry_qualification(signal, side, config) is not None:
                    open_position(t, bar.open, side, signal_j, "daily_cross", signal.timestamp)

        # Native millisecond events inside the stop hour are charged to its opening
        # position before stop detection: explicit scheduling estimate, not a bound.
        while fidx < len(fund) and fund[fidx]["timestamp"] < t + pd.Timedelta(hours=1):
            charge_event(fund[fidx], bar.open, t)
            fidx += 1
        if position is not None:
            exposure_hours += 1
            if carry_daily:
                paid = position["qty"] * bar.open * carry_daily / 24
                cash -= paid
                position["carry_paid"] += paid
            side, stop = position["side"], position["stop"]
            hit = (bar.low <= stop) if side == 1 else (bar.high >= stop)
            adverse = max(bar.low, stop) if side == 1 else min(bar.high, stop)
            # Includes estimated liquidation transaction cost at the adverse price.
            adverse_equity = equity(adverse) - position["qty"] * adverse * (config.fee + config.slip)
            adverse_mdd = min(adverse_mdd, adverse_equity / peak - 1)
            if hit:
                intent = reverse_intent(j, position)
                close_position(t, stop, "stop_intrahour", t + pd.Timedelta(hours=1))
                pending_reverse = None if intent is None else {**intent, "at": t + pd.Timedelta(hours=1)}
                pending_day = None
        mark(t + pd.Timedelta(hours=1), bar.close, "hour_close")
    while fidx < len(fund) and fund[fidx]["timestamp"] <= end:
        charge_event(fund[fidx], float(h.iloc[-1].close), end)
        fidx += 1
    if position is not None:
        close_position(end, float(h.iloc[-1].close), "sample_end")
    curve = pd.DataFrame(marks)
    tr = pd.DataFrame(trades)
    eq = curve.equity.to_numpy()
    mdd = float(np.min(eq / np.maximum.accumulate(np.r_[10000.0, eq])[1:] - 1))
    trade_pnl = tr.net_pnl if len(tr) else pd.Series(dtype=float)
    wins, losses = trade_pnl[trade_pnl > 0].sum(), -trade_pnl[trade_pnl < 0].sum()
    gain = cash / 10000 - 1
    days = (end - start).total_seconds() / 86400
    summary = {"name": config.name, **asdict(config), "start": str(start), "end_exclusive": str(end),
               "return_pct": gain * 100, "ending_equity": cash, "max_drawdown_pct": mdd * 100,
               "adverse_hour_check_pct": min(adverse_mdd, mdd) * 100,
               "annualized_return_pct": ((cash / 10000) ** (365 / days) - 1) * 100 if cash > 0 else -100,
               "trades": len(tr), "win_rate_pct": float((trade_pnl > 0).mean() * 100) if len(tr) else 0,
               "profit_factor": float(wins / losses) if losses else None,
               "exposure_pct": exposure_hours / len(h) * 100,
               "fee_total": float(tr.entry_fee.sum() + tr.exit_fee.sum()) if len(tr) else 0,
               "funding_paid": float(tr.funding_paid.sum()) if len(tr) else 0,
               "carry_paid": float(tr.carry_paid.sum()) if len(tr) else 0,
               "reversal_entries": int((tr.entry_reason == "stop_reversal").sum()) if len(tr) else 0,
               "short_tp_exits": int(tr.exit_reason.isin(["rsi30", "accel1_rsi30", "accel2_rsi30"]).sum()) if len(tr) else 0,
               "price_only_diagnostic": funding is None, "funding_window_verified": False,
               "funding_price_proxy_events": sum(x["mark_proxy"] for x in funding_log),
               "funding_events_charged": len(funding_log), "bankrupt": cash <= 0}
    for qualification in ("original", "opposite_slowdown", "absolute_slowdown", "no_slope"):
        summary["qualification_" + qualification + "_entries"] = (
            int((tr.qualification == qualification).sum()) if len(tr) else 0)
    summary["tightened_trades"] = int((tr.tightening_days > 0).sum()) if len(tr) else 0
    summary["tightening_days"] = int(tr.tightening_days.sum()) if len(tr) else 0
    summary["floor_trades"] = int(tr.stop_floor_reached.sum()) if len(tr) else 0
    summary["armed_trades"] = int(tr.armed.sum()) if len(tr) else 0
    for side, label in [(1, "long"), (-1, "short")]:
        subset = tr[tr.side == side] if len(tr) else tr
        summary[label + "_trades"] = len(subset)
        summary[label + "_pnl"] = float(subset.net_pnl.sum()) if len(subset) else 0
        summary[label + "_wins"] = int((subset.net_pnl > 0).sum()) if len(subset) else 0
    assert math.isclose(10000 + float(tr.net_pnl.sum() if len(tr) else 0), cash, abs_tol=1e-7), "Account reconciliation failed"
    for item in stops:
        assert item["side"] * (item["new_stop"] - item["old_stop"]) >= -1e-12, "Stop widened"
        assert 0.5 <= item["new_mult"] <= item["old_mult"] <= 1.5, "ATR multiple widened or crossed floor"
    assert summary["tightening_days"] == sum(item["tightened"] for item in stops), "Tightening log mismatch"
    return summary, tr, curve, pd.DataFrame(stops), pd.DataFrame(funding_log)
