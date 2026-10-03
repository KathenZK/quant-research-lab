# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned OHLC execution proxy, never original limit-fill reproduction."""

import hashlib
import json
import math
import pathlib
import numpy as np
import pandas as pd


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    pathlib.Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )


def load_input(path, spec):
    if sha(path) != spec["input"]["sha256"]:
        raise ValueError("INPUT_HASH_MISMATCH")
    d = pd.read_csv(path)
    expected = np.arange(
        pd.Timestamp(spec["input"]["start"]).value // 10**6,
        pd.Timestamp(spec["input"]["end_exclusive"]).value // 10**6,
        300000,
    )
    assert np.array_equal(d.open_time.to_numpy(), expected), (
        "nonexact UTC grid, missing, duplicate or unsorted"
    )
    assert np.array_equal(d.close_time.to_numpy(), expected + 300000 - 1)
    assert np.isfinite(d[["open", "high", "low", "close", "volume"]].to_numpy()).all()
    assert (d[["open", "high", "low", "close"]] > 0).all().all() and (
        d.volume >= 0
    ).all()
    assert (
        (d.low <= d.open)
        & (d.low <= d.close)
        & (d.high >= d.open)
        & (d.high >= d.close)
        & (d.high >= d.low)
    ).all()
    assert (
        set(d.native_symbol) == {"BTCUSDT"}
        and set(d.market_type) == {"spot"}
        and set(d.timeframe) == {"5m"}
    )
    return d


def roi_at_open(schedule, opened_ms, entry_ms):
    elapsed = int((opened_ms - entry_ms) // 60000)
    eligible = [int(k) for k in schedule if int(k) <= elapsed]
    key = max(eligible)
    return elapsed, key, float(schedule[str(key)])


def iso(ms):
    return pd.Timestamp(int(ms), unit="ms", tz="UTC").isoformat().replace("+00:00", "Z")


def replay(z, spec, case, closed_bar_cutoff_ms=None):
    start = pd.Timestamp(spec["evaluation"]["start"]).value // 10**6
    end = pd.Timestamp(spec["evaluation"]["end_exclusive"]).value // 10**6
    mask = (z.open_time >= start) & (z.open_time < end)
    if closed_bar_cutoff_ms is not None:
        mask &= z.close_time < closed_bar_cutoff_ms
    indices = np.flatnonzero(mask)
    first = int(indices[0])
    cash = float(spec["execution"]["initial_cash"])
    quantity = 0.0
    entry_price = 0.0
    buy_cost = 0.0
    fee = case["fee_bps"] / 1e4
    slip = spec["execution"]["slippage_bps"] / 1e4
    delay = case["delay_bars"]
    fraction = spec["execution"]["cash_budget_fraction"]
    trades = []
    nav = []
    ambiguous = 0
    unresolved = 0
    total_fees = 0.0
    roundtrips = []
    entry_trade = None
    entry_time_ms = 0
    rows = list(z.itertuples(index=False, name="ReplayBar"))
    for k in indices:
        r = rows[k]
        prior = int(k - delay)
        valid = prior >= first
        override = (
            spec["execution"]
            .get("open_execution_overrides", {})
            .get(str(int(r.open_time)))
        )
        effective_open = (
            int(override["effective_open_ms"]) if override else int(r.open_time)
        )
        assert int(r.open_time) <= effective_open <= int(r.close_time)
        intrabar_latest = int(
            spec["execution"]
            .get("intrabar_execution_latest_overrides", {})
            .get(str(int(r.open_time)), r.close_time)
        )
        ent = bool(valid and rows[prior].entry_signal)
        ext = bool(valid and rows[prior].exit_signal)
        hold = case.get("buy_hold", False)
        if hold:
            ent = k == first
            ext = False
        exited = False

        def fill(side, reference, reason, phase, signal_index=None):
            nonlocal \
                cash, \
                quantity, \
                entry_price, \
                buy_cost, \
                entry_trade, \
                total_fees, \
                exited, \
                entry_time_ms
            price = float(reference) * (1 + slip if side == "BUY" else 1 - slip)
            if side == "BUY":
                budget = cash * fraction
                size = budget / (price * (1 + fee))
                notional = size * price
                commission = notional * fee
                cash -= notional + commission
                quantity = size
                entry_price = price
                buy_cost = notional + commission
                entry_time_ms = effective_open
            else:
                size = quantity
                notional = size * price
                commission = notional * fee
                cash += notional - commission
                quantity = 0.0
                exited = True
                roundtrips.append((notional - commission) / buy_cost - 1)
            total_fees += commission
            event = {
                "trade_id": len(trades) + 1,
                "bar_index": int(k),
                "bar_open_utc": iso(r.open_time),
                "side": side,
                "reason": reason,
                "phase": phase,
                "signal_bar_index": signal_index,
                "signal_close_utc": iso(rows[signal_index].close_time)
                if signal_index is not None
                else None,
                "execution_time_utc": iso(effective_open)
                if phase in ("open", "open_gap")
                else None,
                "execution_earliest_utc": iso(effective_open),
                "execution_latest_utc": iso(
                    effective_open if phase in ("open", "open_gap") else intrabar_latest
                ),
                "execution_time_basis": override["basis"]
                if override
                else "native_5m_open_proxy",
                "reference_price": float(reference),
                "fill_price": price,
                "quantity": size,
                "notional": notional,
                "fee": commission,
                "cash_after": cash,
                "quantity_after": quantity,
            }
            trades.append(event)
            if side == "BUY":
                entry_trade = event

        signal_profit_ok = (
            (
                not spec["execution"].get("exit_profit_only", False)
                or r.open * (1 - fee) / (entry_price * (1 + fee)) - 1
                > spec["execution"].get("exit_profit_offset", 0.0)
            )
            if quantity > 0
            else False
        )
        if quantity > 0 and ext and not ent and signal_profit_ok:
            fill("SELL", r.open, "exit_signal", "open", prior)
        if quantity == 0 and ent and not ext and not exited:
            fill(
                "BUY",
                r.open,
                "buy_hold" if hold else "entry_signal",
                "open",
                None if hold else prior,
            )
        if quantity > 0 and not hold:
            elapsed, roi_key, roi_value = roi_at_open(
                spec["risk"]["minimal_roi"], effective_open, entry_time_ms
            )
            stop = entry_price * (1 + spec["risk"]["stoploss"])
            target = entry_price * (1 + fee) * (1 + roi_value) / (1 - fee)
            hit_stop = r.low <= stop
            hit_roi = r.high > target
            if hit_stop and hit_roi:
                ambiguous += 1
                if stop < r.open < target:
                    unresolved += 1
            if r.open <= stop:
                fill("SELL", r.open, "stoploss", "open_gap")
            elif r.open > target:
                fill("SELL", r.open, "roi", "open_gap")
            elif hit_stop:
                fill("SELL", stop, "stoploss", "intrabar_unknown")
            elif hit_roi:
                fill("SELL", target, "roi", "intrabar_unknown")
        equity = cash + quantity * float(r.close)
        nav.append(
            {
                "bar_index": int(k),
                "bar_open_utc": iso(r.open_time),
                "timestamp_utc": iso(r.close_time + 1),
                "cash": cash,
                "quantity": quantity,
                "close": float(r.close),
                "equity": equity,
                "nav": equity / spec["execution"]["initial_cash"],
            }
        )
    frame = pd.DataFrame(nav)
    eq = np.r_[spec["execution"]["initial_cash"], frame.equity.to_numpy()]
    ret = eq[1:] / eq[:-1] - 1
    dates = pd.to_datetime(frame.bar_open_utc, utc=True).dt.strftime("%Y-%m-%d")
    daily = frame.assign(date=dates).groupby("date", sort=True).tail(1).copy()
    deq = np.r_[spec["execution"]["initial_cash"], daily.equity.to_numpy()]
    dr = deq[1:] / deq[:-1] - 1

    def sharpe(x, scale):
        return (
            float(x.mean() / x.std(ddof=1) * math.sqrt(scale))
            if x.std(ddof=1) > 0
            else None
        )

    days = (end - start) / 86400000
    peak = np.maximum.accumulate(eq)
    metrics = {
        "start": spec["evaluation"]["start"],
        "end": spec["evaluation"]["end_exclusive"],
        "observations": len(frame),
        "daily_observations": len(daily),
        "total_return": float(eq[-1] / eq[0] - 1),
        "annualized_return": float((eq[-1] / eq[0]) ** (365 / days) - 1),
        "max_drawdown": float(np.max(1 - eq / peak)),
        "sharpe": sharpe(dr, 365),
        "sharpe_5m": sharpe(ret, 365 * 288),
        "final_equity": float(eq[-1]),
        "trades": len(trades),
        "round_trips": len(roundtrips),
        "winning_round_trip_fraction": float(np.mean(np.array(roundtrips) > 0))
        if roundtrips
        else None,
        "fees_paid": float(total_fees),
        "position_bar_fraction": float((frame.quantity > 0).mean()),
        "final_cash": cash,
        "final_quantity": quantity,
        "same_bar_stop_roi_hits": ambiguous,
        "intrabar_stop_roi_ambiguities": unresolved,
    }
    return frame, daily, pd.DataFrame(trades), metrics
