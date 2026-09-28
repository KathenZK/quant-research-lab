"""MTTC 独立重建器：不用共享引擎的特征、候选或会计函数。

只接受本家族可信启动返回的原价格与保留结果。所有 reference_* 函数
可直接用合成输入执行；主程序适配在结果 schema 锁定后补齐。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import datetime as dt
import hashlib
import json
import math
import time

import numpy as np
import pandas as pd


DAY = pd.Timedelta(days=1)
FAMILY = Path(__file__).resolve().parents[1]


def read_config(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or FAMILY / "specs/config.json").read_text())


def checked_prices(bars: pd.DataFrame) -> pd.DataFrame:
    required = {"symbol", "ts", "open", "high", "low", "close", "quote_volume", "eligible", "research_segment_id"}
    if not isinstance(bars, pd.DataFrame) or required - set(bars):
        raise ValueError(f"missing input columns: {sorted(required - set(bars))}")
    p = bars.copy()
    if p.symbol.isna().any() or not p.symbol.map(lambda x: isinstance(x, str) and bool(x)).all():
        raise ValueError("symbol must be a nonmissing string")
    if pd.api.types.is_numeric_dtype(p.ts.dtype):
        raise ValueError("timestamp units must be resolved upstream")
    p["ts"] = pd.to_datetime(p.ts, utc=True, errors="raise")
    if p.ts.isna().any() or not p.ts.eq(p.ts.dt.normalize()).all() or p.duplicated(["symbol", "ts"]).any():
        raise ValueError("input must have unique UTC daily symbol/time keys")
    for name in ("eligible",):
        if not pd.api.types.is_bool_dtype(p[name].dtype) or p[name].isna().any():
            raise ValueError(f"{name} must be nonmissing boolean")
    if "is_closed" in p and (not pd.api.types.is_bool_dtype(p.is_closed.dtype) or not p.is_closed.all()):
        raise ValueError("input contains unclosed bars")
    numeric = p.loc[p.eligible, ["open", "high", "low", "close", "quote_volume"]].to_numpy(dtype=float)
    if not np.isfinite(numeric).all() or (numeric[:, :4] <= 0).any() or (numeric[:, 4] < 0).any():
        raise ValueError("invalid OHLCV values")
    op, hi, lo, close, _ = numeric.T
    if (hi < np.maximum(op, close)).any() or (lo > np.minimum(op, close)).any() or (hi < lo).any():
        raise ValueError("inconsistent OHLC bounds")
    if p.loc[p.eligible, "research_segment_id"].isna().any():
        raise ValueError("eligible rows require source segment identity")
    return p.sort_values(["symbol", "ts"], kind="stable").reset_index(drop=True)


def reference_features(bars: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """逐日原式算强度和简单ATR，并以armed状态生成全部事前origin。"""
    p = checked_prices(bars)
    p["segment"] = p.research_segment_id
    p["local_index"] = -1
    for name in ("r20", "sigma20", "strength", "atr14", "liquidity20"):
        p[name] = np.nan
    p["feature_valid"] = False
    w, aw, warmup = config["momentum_window"], config["atr_window"], config["warmup"]
    origins = []
    for symbol, source in p.groupby("symbol", sort=False):
        runs: list[list[int]] = []
        current: list[int] = []
        previous_ts, previous_segment = None, None
        for row in source.itertuples():
            same_run = bool(row.eligible and current and row.ts - previous_ts == DAY and row.research_segment_id == previous_segment)
            if not same_run and current:
                runs.append(current)
                current = []
            if row.eligible:
                current.append(row.Index)
            previous_ts, previous_segment = row.ts, row.research_segment_id
        if current:
            runs.append(current)
        for indices in runs:
            run = p.loc[indices]
            close, high, low, volume = (run[c].to_numpy(dtype=float) for c in ("close", "high", "low", "quote_volume"))
            returns = np.log(close[1:] / close[:-1])
            tr = np.empty(len(run))
            tr[0] = high[0] - low[0]
            for j in range(1, len(run)):
                tr[j] = max(high[j] - low[j], abs(high[j] - close[j - 1]), abs(low[j] - close[j - 1]))
            armed = True
            for j, idx in enumerate(indices):
                p.at[idx, "local_index"] = j
                if j >= aw - 1:
                    p.at[idx, "atr14"] = float(np.mean(tr[j - aw + 1:j + 1]))
                if j >= w - 1:
                    p.at[idx, "liquidity20"] = float(np.mean(volume[j - w + 1:j + 1]))
                if j < w:
                    continue
                r = float(math.log(close[j] / close[j - w]))
                sigma = float(np.std(returns[j - w:j], ddof=1))
                x = r / (sigma * math.sqrt(w)) if sigma > 0 and np.isfinite(sigma) else np.nan
                p.at[idx, "r20"], p.at[idx, "sigma20"], p.at[idx, "strength"] = r, sigma, x
                valid = j >= warmup - 1 and np.isfinite(x) and np.isfinite(p.at[idx, "atr14"]) and p.at[idx, "atr14"] > 0 and np.isfinite(p.at[idx, "liquidity20"]) and p.at[idx, "liquidity20"] > 0
                p.at[idx, "feature_valid"] = bool(valid)
                if r <= 0:
                    armed = True
                if valid and armed and x > config["strength_threshold"]:
                    origins.append({"symbol": symbol, "segment": p.at[idx, "segment"], "origin_ts": p.at[idx, "ts"], "origin_index": j, "atr": p.at[idx, "atr14"], "liquidity": p.at[idx, "liquidity20"], "first_observable": j == warmup - 1, "strength": x, "r20": r})
                    armed = False
    columns = ["symbol", "segment", "origin_ts", "origin_index", "atr", "liquidity", "first_observable", "strength", "r20"]
    return p, pd.DataFrame(origins, columns=columns)


def reference_unit(segment: pd.DataFrame, origin: dict[str, Any] | pd.Series, policy: str, cost: dict[str, Any], config: dict[str, Any], budget: float = 1.0) -> tuple[dict[str, Any], pd.DataFrame]:
    """单共同机会的独立逐日现金账；不以未来长度决定是否入场。"""
    if policy not in ("A", "B", "C") or not np.isfinite(budget) or budget <= 0:
        raise ValueError("invalid policy/budget")
    p = segment.sort_values("ts", kind="stable").reset_index(drop=True)
    if p.empty or not p.ts.diff().iloc[1:].eq(DAY).all() or p.symbol.nunique() != 1 or p.segment.nunique() != 1:
        raise ValueError("reference_unit needs one continuous symbol/segment")
    oi = int(origin["origin_index"])
    if oi < 0 or oi >= len(p) or pd.Timestamp(origin["origin_ts"]) != p.at[oi, "ts"]:
        raise ValueError("origin does not identify the supplied segment")
    atr = float(origin["atr"])
    if not np.isfinite(atr) or atr <= 0:
        raise ValueError("origin ATR must be positive and finite")
    fee, slip, carry_rate = cost["fee"], cost["slippage"], cost["daily_carry"]
    cash, qty = float(budget), 0.0
    pending = "ENTRY" if policy in ("A", "B") else ""
    waiting, pullback_index = policy == "C", None
    peak = float(p.at[oi, "close"])
    entry_ts, exit_ts = pd.NaT, pd.NaT
    entry_price = exit_price = np.nan
    original_qty, fees, slips, carrying, hold_days = 0.0, 0.0, 0.0, 0.0, 0
    exit_reason = ""
    normal_complete, entered, shortfall = False, False, False
    restart_index = entry_index = exit_index = None
    daily = []
    for j in range(oi, len(p)):
        bar = p.iloc[j]
        cash_before, qty_before = cash, qty
        before = cash + qty * bar.open if j > oi else budget
        entry_open = exit_open = release_open = False
        fee_today = slip_today = carry_today = 0.0
        reason = ""
        if j > oi:
            if pending in ("CANCEL", "EXPIRE"):
                reason = pending
                waiting = False
                normal_complete = release_open = True
                pending = ""
            elif qty > 0 and pending in ("RISK", "TREND", "TIME"):
                reason = pending
                exit_price = float(bar.open) * (1 - slip)
                fee_today = qty * exit_price * fee
                slip_today = qty * (float(bar.open) - exit_price)
                cash += qty * exit_price - fee_today
                qty = 0.0
                exit_ts, exit_reason = bar.ts, reason
                exit_index = j
                normal_complete = exit_open = release_open = True
                pending = ""
            elif pending == "ENTRY":
                entry_price = float(bar.open) * (1 + slip)
                qty = min(config["slot_notional_fraction"] * budget / (entry_price * (1 + fee)), config["slot_risk_fraction"] * budget / (config["stop_atr"] * atr))
                fee_today = qty * entry_price * fee
                slip_today = qty * (entry_price - float(bar.open))
                cash -= qty * entry_price + fee_today
                entry_ts, original_qty = bar.ts, qty
                entry_index = j
                entered = entry_open = True
                waiting = False
                reason, pending = "ENTRY", ""
            elif waiting and j >= oi + config["wait_days"]:
                reason = "EXPIRE"
                waiting = False
                normal_complete = release_open = True
        cash_after, qty_after = cash, qty
        after = cash + qty * float(bar.open) if j > oi else budget
        if qty > 0:
            hold_days += 1
            carry_today = qty * float(bar.close) * carry_rate
            cash -= carry_today
            shortfall |= cash < -1e-12
            if float(bar.close) <= entry_price - config["stop_atr"] * atr:
                pending = "RISK"
            elif policy in ("B", "C") and float(bar.r20) <= 0:
                pending = "TREND"
            elif j >= oi + (config["fixed_hold_days"] if policy == "A" else config["max_hold_days"]):
                pending = "TIME"
        elif waiting and j > oi and not normal_complete:
            if float(bar.r20) <= 0:
                pending = "CANCEL"
            elif j <= oi + config["wait_days"] - 1:
                if pullback_index is None and float(bar.close) <= peak - config["pullback_atr"] * atr:
                    pullback_index = j
                if pullback_index is not None and j > pullback_index and float(bar.close) > float(p.at[j - 1, "high"]):
                    pending = "ENTRY"
                    restart_index = j
                peak = max(peak, float(bar.close))
        value = cash + qty * float(bar.close)
        fees += fee_today
        slips += slip_today
        carrying += carry_today
        daily.append({"ts": bar.ts, "has_bar": True, "data_gap": False, "open_before": before, "open_after": after, "close_value": value, "qty_close": qty, "cash_close": cash, "release_open": release_open, "entry_open": entry_open, "exit_open": exit_open, "fee_open": fee_today, "slippage_open": slip_today, "carry_close": carry_today, "pending_close": pending, "cash_open_before": cash_before, "cash_open_after": cash_after, "qty_open_before": qty_before, "qty_open_after": qty_after, "reference_open": float(bar.open), "reference_high": float(bar.high), "reference_low": float(bar.low), "reference_close": float(bar.close), "intraday_low_value": cash_after + qty_after * float(bar.low), "reason": reason})
        if normal_complete:
            break
    last_mark_ts = daily[-1]["ts"] if normal_complete else daily[-1]["ts"] + DAY
    released = normal_complete
    release_reason = {"CANCEL": "WAIT_TREND_FAILURE", "EXPIRE": "WAIT_EXPIRED", "RISK": "RISK_STOP", "TREND": "TREND_FAILURE", "TIME": "TIME_20" if policy == "A" else "TIME_60"}.get(daily[-1]["reason"], "")
    terminal_status = "COMPLETED_TRADE" if normal_complete and entered else release_reason
    data_interrupted = False
    if not normal_complete:
        if p.ts.iloc[-1] + DAY < pd.Timestamp(config["end"]):
            data_interrupted = True
            row = daily[-1].copy()
            row.update(ts=p.ts.iloc[-1] + DAY, has_bar=False, data_gap=True, entry_open=False, exit_open=False, release_open=qty == 0, fee_open=0., slippage_open=0., carry_close=0.)
            for col in ("open_before", "open_after", "intraday_low_value"):
                row[col] = row["close_value"]
            row.update(cash_open_before=cash, cash_open_after=cash, qty_open_before=qty, qty_open_after=qty)
            for col in ("reference_open", "reference_high", "reference_low", "reference_close"):
                row[col] = np.nan
            terminal_status = "UNRESOLVED_POSITION" if qty > 0 else "DATA_GAP_CANCELLED"
            released = qty == 0
            release_reason = "DATA_GAP_CANCELLED" if released else ""
            row.update(reason=release_reason, pending_close=terminal_status)
            daily.append(row)
        else:
            terminal_status = "ADMIN_END_POSITION" if qty > 0 else "ADMIN_END_PENDING_ENTRY" if pending == "ENTRY" else "ADMIN_END_WAIT"
    for row in daily:
        row["release_reason"] = release_reason if row["release_open"] else ""
    last_value = float(daily[-1]["close_value"])
    summary = {"normal_complete": normal_complete, "released": released, "unresolved": not released, "terminal_status": terminal_status, "data_interrupted": data_interrupted, "entered": entered, "entry_ts": entry_ts, "entry_index": entry_index, "entry_price": entry_price, "qty": original_qty, "exit_ts": exit_ts, "exit_index": exit_index, "exit_price": exit_price, "exit_reason": exit_reason, "return": last_value / budget - 1 if normal_complete else np.nan, "observed_return": last_value / budget - 1, "fees": fees, "slippage": slips, "carry": carrying, "holding_days": hold_days, "last_mark_ts": last_mark_ts, "last_value": last_value, "last_cash": cash, "last_qty": qty, "cost_cash_shortfall": shortfall, "pullback_index": pullback_index, "restart_index": restart_index, "pending_terminal": pending, "release_ts": daily[-1]["ts"] if released else pd.NaT, "release_reason": release_reason, "zero_residual_value_return": cash / budget - 1}
    return summary, pd.DataFrame(daily)


def reference_label(segment: pd.DataFrame, first_day: int, reference_price: float, atr: float, horizon: int) -> dict[str, Any]:
    """固定未来收盘标签；不提供给候选或交易状态机。"""
    if horizon <= 0 or reference_price <= 0 or atr <= 0:
        raise ValueError("invalid label scale/window")
    stop = first_day + horizon
    if first_day >= len(segment):
        return {"first_hit": "CENSORED", "hit_day": None, "complete": False, "endpoint_atr": np.nan, "endpoint_return": np.nan}
    closes = segment.close.iloc[first_day:min(stop, len(segment))].to_numpy(dtype=float)
    first_hit, hit_day = "TIMEOUT", None
    for j, close in enumerate(closes):
        if close >= reference_price + 2 * atr:
            first_hit, hit_day = "UP_FIRST", j + 1
            break
        if close <= reference_price - 2 * atr:
            first_hit, hit_day = "DOWN_FIRST", j + 1
            break
    complete = stop <= len(segment)
    if first_hit == "TIMEOUT" and not complete:
        first_hit = "CENSORED"
    endpoint = float(segment.close.iloc[stop - 1]) if complete else np.nan
    return {"first_hit": first_hit, "hit_day": hit_day, "complete": complete, "endpoint_atr": (endpoint - reference_price) / atr, "endpoint_return": endpoint / reference_price - 1}


def compare_numeric(actual: np.ndarray, expected: np.ndarray, label: str, *, atol: float = 1e-8, rtol: float = 1e-10) -> float:
    actual, expected = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    if actual.shape != expected.shape or not np.array_equal(np.isfinite(actual), np.isfinite(expected)):
        raise AssertionError(f"{label}: shape/finite-mask mismatch")
    if not np.array_equal(np.isnan(actual), np.isnan(expected)):
        raise AssertionError(f"{label}: NaN mismatch")
    finite = np.isfinite(expected)
    if not np.allclose(actual[finite], expected[finite], atol=atol, rtol=rtol):
        raise AssertionError(f"{label}: numeric mismatch, max={np.max(np.abs(actual[finite] - expected[finite]))}")
    return float(np.max(np.abs(actual[finite] - expected[finite]))) if finite.any() else 0.0


def recent_account_slices(daily: pd.DataFrame, end: pd.Timestamp, days: list[int], initial_equity: float | None = None) -> pd.DataFrame:
    """使用持续账户的窗口前权益；不重跑策略或清空已有持仓。"""
    table = daily.sort_values("ts", kind="stable")
    ts = pd.to_datetime(table.ts, utc=True)
    rows = []
    for horizon in days:
        begin = pd.Timestamp(end) - horizon * DAY
        in_window = (ts >= begin) & (ts < end)
        previous = table.loc[ts < begin]
        selected = table.loc[in_window]
        if selected.empty:
            rows.append({"days": horizon, "start": begin, "end": end, "observations": 0, "return": np.nan, "max_drawdown": np.nan})
            continue
        initial = float(previous.iloc[-1].equity) if len(previous) else float(initial_equity if initial_equity is not None else selected.iloc[0].equity_open_before)
        values = np.r_[initial, selected.equity.to_numpy(dtype=float)]
        peaks = np.maximum.accumulate(values)
        rows.append({"days": horizon, "start": begin, "end": end, "observations": len(selected), "initial_equity": initial, "terminal_equity": values[-1], "return": values[-1] / initial - 1 if initial > 0 else np.nan, "max_drawdown": float(np.min(values / peaks - 1)) if (peaks > 0).all() else np.nan})
    return pd.DataFrame(rows)


def reference_portfolio(origins: pd.DataFrame, paths: dict[str, pd.DataFrame], policy: str, cost_id: str, config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """由参考单位路径重建独立槽位账；无未来长度、收益或标签准入过滤。"""
    schedule = {}
    for item in origins.to_dict("records"):
        schedule.setdefault(pd.Timestamp(item["origin_ts"]) + DAY, []).append(item)
    for items in schedule.values():
        items.sort(key=lambda x: (-float(x["liquidity"]), str(x["symbol"])))
    indexed = {key: value.set_index("ts").to_dict("index") for key, value in paths.items()}
    unreserved = float(config["initial_equity"])
    positions, unavailable_symbols = {}, set()
    dates = pd.date_range(config["start"], pd.Timestamp(config["end"]) - DAY, freq="D")
    records, actions = [], []
    highest = unreserved

    def record(day, origin_id, event, **fields):
        actions.append(dict(ts=day, origin_id=origin_id, policy=policy, cost_id=cost_id, event=event, **fields))

    for day in dates:
        current = {}
        dayfees = dayslips = daycarry = 0.
        for oid, position in positions.items():
            observation = indexed[oid].get(day)
            if observation is None:
                prior = position["last"]
                observation = {**prior, "open_before": prior["close_value"], "open_after": prior["close_value"], "cash_open_before": prior["cash_close"], "cash_open_after": prior["cash_close"], "qty_open_before": prior["qty_close"], "qty_open_after": prior["qty_close"], "entry_open": False, "exit_open": False, "release_open": False, "fee_open": 0., "slippage_open": 0., "carry_close": 0., "data_gap": True, "intraday_low_value": prior["close_value"]}
            current[oid] = observation
            if observation["data_gap"] and observation["qty_open_before"] > 0:
                unavailable_symbols.add(position["symbol"])
                if not position["missing"]:
                    record(day, oid, "UNRESOLVED_POSITION", symbol=position["symbol"], budget=position["capital"])
                position["missing"] = True

        def release(oid):
            nonlocal unreserved, dayfees, dayslips
            position, observation = positions[oid], current[oid]
            returned = position["capital"] * observation["open_after"]
            unreserved += returned
            dayfees += position["capital"] * observation["fee_open"]
            dayslips += position["capital"] * observation["slippage_open"]
            record(day, oid, "RELEASE", symbol=position["symbol"], budget=position["capital"], released=returned, pnl=returned-position["capital"], reason=observation["release_reason"], fee=position["capital"]*observation["fee_open"])
            del positions[oid]

        for oid in list(positions):
            if current[oid]["release_open"]:
                release(oid)
        opening_assets = unreserved + sum(p["capital"] * current[oid]["open_before"] for oid, p in positions.items())
        per_origin_limit = max(0., opening_assets * config["budget_fraction"])
        for origin in schedule.get(day, []):
            oid, symbol = origin["origin_id"], origin["symbol"]
            cash_debt = sum(min(0., p["capital"] * current[k]["cash_open_before"]) for k, p in positions.items())
            spendable = max(0., unreserved + cash_debt)
            rejection = None
            if symbol in unavailable_symbols:
                rejection = "SYMBOL_DATA_UNRESOLVED"
            elif symbol in {p["symbol"] for p in positions.values()}:
                rejection = "SYMBOL_OCCUPIED"
            elif len(positions) >= config["max_slots"]:
                rejection = "SLOTS_FULL"
            elif spendable <= 1e-12 or per_origin_limit <= 0:
                rejection = "NO_FREE_CASH"
            elif day not in indexed[oid]:
                rejection = "NO_EXECUTABLE_BAR_TODAY"
            if rejection:
                record(day, oid, "REJECT", symbol=symbol, reason=rejection, budget=0.)
                continue
            allocation = min(per_origin_limit, spendable)
            unreserved -= allocation
            observation = indexed[oid][day]
            positions[oid] = dict(symbol=symbol, capital=allocation, last=observation, missing=False)
            current[oid] = observation
            record(day, oid, "ADMIT", symbol=symbol, budget=allocation, nav_at_batch=opening_assets)
            if observation["release_open"]:
                release(oid)
        for oid, position in positions.items():
            observation, b = current[oid], position["capital"]
            dayfees += b * observation["fee_open"]
            dayslips += b * observation["slippage_open"]
            daycarry += b * observation["carry_close"]
            if observation["entry_open"]:
                record(day, oid, "ENTRY", symbol=position["symbol"], budget=b, quantity=b*observation["qty_open_after"], fee=b*observation["fee_open"])
            position["last"] = observation
        equity = unreserved + sum(p["capital"] * current[k]["close_value"] for k, p in positions.items())
        all_cash = unreserved + sum(p["capital"] * current[k]["cash_close"] for k, p in positions.items())
        zero_price_equity = unreserved + sum(p["capital"] * current[k]["cash_close" if p["missing"] else "close_value"] for k, p in positions.items())
        low_equity = unreserved + sum(p["capital"] * current[k]["intraday_low_value"] for k, p in positions.items())
        highest = max(highest, equity)
        records.append(dict(ts=day, close_ts=day+DAY, policy=policy, cost_id=cost_id, equity=equity, free_cash=unreserved, total_cash=all_cash, exposure=equity-all_cash, active_slots=len(positions), positions=sum(current[k]["qty_close"] > 0 for k in positions), unresolved_positions=sum(p["missing"] for p in positions.values()), fee=dayfees, slippage=dayslips, hypothetical_carry=daycarry, drawdown=equity/highest-1, unresolved_zero_value_equity=zero_price_equity, intraday_simultaneous_low_bound=low_equity, cost_cash_shortfall=all_cash < -1e-9))
    for day, items in schedule.items():
        if day >= pd.Timestamp(config["end"]):
            for origin in items:
                record(day, origin["origin_id"], "PENDING_AFTER_DATA_END", symbol=origin["symbol"], budget=0.)
    return pd.DataFrame(records), pd.DataFrame(actions)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assert_values(actual, expected, label: str) -> None:
    a, e = pd.Series(actual).reset_index(drop=True), pd.Series(expected).reset_index(drop=True)
    if len(a) != len(e) or not ((a.isna() & e.isna()) | a.eq(e)).all():
        mismatch = ~((a.isna() & e.isna()) | a.eq(e)) if len(a) == len(e) else []
        raise AssertionError(f"{label}: discrete values differ; first={list(np.flatnonzero(mismatch)[:5])}")


def compare_actions(actual: pd.DataFrame, expected: pd.DataFrame) -> float:
    if len(actual) != len(expected):
        raise AssertionError("portfolio action count differs")
    numeric = {"budget", "released", "pnl", "fee", "nav_at_batch", "quantity"}
    maxerr = 0.
    for col in sorted(set(actual) | set(expected)):
        a = actual[col] if col in actual else pd.Series(np.nan, index=range(len(actual)))
        e = expected[col] if col in expected else pd.Series(np.nan, index=range(len(expected)))
        if col in numeric:
            maxerr = max(maxerr, compare_numeric(a, e, f"actions.{col}"))
        else:
            assert_values(a, e, f"actions.{col}")
    return maxerr


def reference_paired_statistics(paired: pd.DataFrame, config: dict[str, Any]) -> tuple[dict, dict[str, np.ndarray]]:
    """独立按循环日历逐日累加块充分量，不导入生产推断函数。"""
    dates = pd.date_range(config["start"], pd.Timestamp(config["end"]) - DAY, freq="D")
    x = paired[["A", "B", "C"]].to_numpy(float)
    raw_points = x.mean(axis=0)
    points = np.r_[raw_points, raw_points[1]-raw_points[0], raw_points[2]-raw_points[1]]
    day_numbers = dates.get_indexer(pd.to_datetime(paired.origin_ts, utc=True))
    if (day_numbers < 0).any() or not np.isfinite(x).all():
        raise ValueError("paired input outside calendar or nonfinite")
    daily = np.zeros((len(dates), 4))
    np.add.at(daily, day_numbers, np.column_stack((x, np.ones(len(x)))))
    intervals, saved = [], {}
    for length in config["bootstrap"]["blocks"]:
        count, remainder = divmod(len(dates), length)
        full, tail = np.zeros_like(daily), np.zeros_like(daily)
        for offset in range(length):
            shifted = daily[(np.arange(len(dates)) + offset) % len(dates)]
            full += shifted
            if offset < remainder:
                tail += shifted
        generator = np.random.Generator(np.random.PCG64(config["bootstrap"]["seed"] + length))
        replicas = []
        for start in range(0, config["bootstrap"]["repetitions"], 250):
            batch = min(250, config["bootstrap"]["repetitions"] - start)
            indices = generator.integers(0, len(dates), size=(batch, count))
            sampled = full[indices].sum(axis=1)
            if remainder:
                sampled += tail[generator.integers(0, len(dates), size=batch)]
            if (sampled[:, 3] <= 0).any():
                raise AssertionError("zero-opportunity bootstrap replicate")
            m = sampled[:, :3] / sampled[:, 3, None]
            replicas.append(np.c_[m, m[:, 1]-m[:, 0], m[:, 2]-m[:, 1]])
        replicas = np.vstack(replicas)
        sd = np.std(replicas, axis=0, ddof=1)
        cutoff = float(np.quantile(np.max(abs((replicas-points)/np.where(sd > 0, sd, 1.)), axis=1), config["bootstrap"]["confidence"]))
        lo, hi = points-cutoff*sd, points+cutoff*sd
        intervals.append(dict(block_days=length, repetitions=len(replicas), critical=cutoff, standard_error=sd.tolist(), lower=lo.tolist(), upper=hi.tolist()))
        saved[f"block_{length}"] = replicas
    return dict(n=len(paired), points=points.tolist(), lower=np.min([i["lower"] for i in intervals], axis=0).tolist(), upper=np.max([i["upper"] for i in intervals], axis=0).tolist(), blocks=intervals), saved


def verify_production_inputs(family: Path, result_dir: Path) -> dict:
    repo = family.parents[2]
    lock_path = family / "specs/computation-lock.json"
    lock = json.loads(lock_path.read_text())
    for relative, expected in lock["files"].items():
        if sha256(repo / relative) != expected:
            raise AssertionError(f"production lock changed: {relative}")
    complete_path = result_dir / "completed.json"
    completed = json.loads(complete_path.read_text())
    for relative, expected in completed["files"].items():
        if sha256(result_dir / relative) != expected:
            raise AssertionError(f"completed output changed: {relative}")
    return dict(computation_lock=sha256(lock_path), completed_receipt=sha256(complete_path))


def audit_result(family: Path, result_dir: Path, output_dir: Path) -> dict:
    """读取新P0帧，逐层重建全部记录；任何失败写明阶段，绝不改生产产物。"""
    output_dir.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    receipt = dict(status="RUNNING", started_utc=dt.datetime.now(dt.timezone.utc).isoformat(), auditor_sha256=sha256(Path(__file__)), tests_sha256=sha256(Path(__file__).with_name("test_audit.py")), stages={})

    def stage(name, **details):
        receipt["stage"] = name
        receipt["stages"][name] = dict(status="PASS", elapsed_seconds=time.monotonic()-start, **details)
        print(f"AUDIT {name} PASS elapsed={time.monotonic()-start:.1f}s", flush=True)

    try:
        receipt["stage"] = "input_identity"
        before = verify_production_inputs(family, result_dir)
        config = read_config(family / "specs/config.json")
        manifest_path = family / "artifacts/p0-inputs/frame-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        frames = []
        for symbol, record in manifest.items():
            path = manifest_path.parent / record["path"]
            if sha256(path) != record["sha256"]:
                raise AssertionError(f"P0 frame checksum: {symbol}")
            frame = pd.read_pickle(path, compression="gzip")
            if len(frame) != record["rows"] or not frame.symbol.eq(symbol).all():
                raise AssertionError(f"P0 frame identity: {symbol}")
            frame.attrs = {}
            frames.append(frame)
        raw = pd.concat(frames, ignore_index=True).sort_values(["symbol", "ts"], kind="stable").reset_index(drop=True)
        panel = pd.read_parquet(result_dir / "panel.parquet").sort_values(["symbol", "ts"], kind="stable").reset_index(drop=True)
        if len(raw) != len(panel):
            raise AssertionError("input panel changed number of rows")
        for col in raw:
            if col not in panel:
                raise AssertionError(f"input column not retained: {col}")
            if pd.api.types.is_numeric_dtype(raw[col].dtype) and not pd.api.types.is_bool_dtype(raw[col].dtype):
                compare_numeric(panel[col], raw[col], f"retained original {col}", atol=0, rtol=0)
            else:
                assert_values(panel[col], raw[col], f"retained original {col}")
        stage("input_identity", symbols=len(frames), rows=len(raw), hashes=before)
        receipt["stage"] = "features_and_origins"
        reference, origins_expected = reference_features(raw, config)
        errors = {}
        for col in ("r20", "sigma20", "strength", "atr14", "liquidity20", "local_index"):
            errors[col] = compare_numeric(panel[col], reference[col], col)
        assert_values(panel.feature_valid, reference.feature_valid, "feature_valid")
        assert_values(panel.segment, reference.segment, "segment")
        origins = pd.read_parquet(result_dir / "origins.parquet")
        if origins.origin_id.duplicated().any():
            raise AssertionError("duplicate origin identity")
        keys = ["symbol", "segment", "origin_ts"]
        ao = origins.sort_values(keys).reset_index(drop=True)
        eo = origins_expected.sort_values(keys).reset_index(drop=True)
        if len(ao) != len(eo):
            raise AssertionError("origin set size mismatch; possible future filtering")
        for col in keys + ["origin_index", "first_observable"]:
            assert_values(ao[col], eo[col], f"origins {col}")
        for col in ("atr", "liquidity", "strength", "r20"):
            errors[f"origin_{col}"] = compare_numeric(ao[col], eo[col], col)
        assert_values(ao.signal_ts, ao.origin_ts + DAY, "origin known only at completed close")
        # Production identifiers are only keys; every selection/price field above is independently rebuilt.
        eo["origin_id"] = ao.origin_id
        origin_lookup = eo.set_index("origin_id").to_dict("index")
        segments = {(str(s), str(k)): g.reset_index(drop=True) for (s, k), g in reference.loc[reference.eligible].groupby(["symbol", "segment"], sort=False)}

        def check_label(actual, segment, first, baseline, atr, horizon, prefix, entered=True):
            if not entered:
                expected = dict(first_hit="NOT_ENTERED", endpoint_return=np.nan, hit_day=None)
            elif first >= len(segment):
                expected = dict(first_hit="CENSORED", endpoint_return=np.nan, hit_day=None)
            else:
                expected = reference_label(segment, first, baseline, atr, horizon)
            mapping = {"UP_FIRST": "CONTINUATION", "DOWN_FIRST": "FAILURE"}
            assert_values([actual[f"{prefix}_{horizon}_outcome"]], [mapping.get(expected["first_hit"], expected["first_hit"])], "label outcome")
            compare_numeric([actual[f"{prefix}_{horizon}_endpoint_return"]], [expected["endpoint_return"]], "label endpoint")
            compare_numeric([actual[f"{prefix}_{horizon}_first_hit_day"]], [expected["hit_day"]], "first hit day")

        complete_set = set()
        for row in origins.to_dict("records"):
            r = origin_lookup[row["origin_id"]]
            segment = segments[(str(r["symbol"]), str(r["segment"]))]
            oi = int(r["origin_index"])
            complete = oi + 61 < len(segment)
            if complete:
                complete_set.add(row["origin_id"])
            if bool(row["complete_window_60"]) != complete or row["segment_rows_after_origin"] != len(segment)-oi-1:
                raise AssertionError("common origin+61 completeness label")
            for horizon in (20, 60):
                check_label(row, segment, oi+1, float(segment.open.iloc[oi+1]) if oi+1 < len(segment) else np.nan, r["atr"], horizon, "origin")
        stage("features_and_origins", origins=len(eo), feature_max_errors=errors, complete_origin_61=len(complete_set))
        receipt["stage"] = "unit_paths_and_portfolios"
        summaries = pd.read_parquet(result_dir / "opportunities.parquet")
        unit = pd.read_parquet(result_dir / "unit_daily.parquet")
        accounts = pd.read_parquet(result_dir / "portfolio_daily.parquet")
        actions = pd.read_parquet(result_dir / "portfolio_actions.parquet")
        metrics = json.loads((result_dir / "account-metrics.json").read_text())
        statistics = json.loads((result_dir / "paired-statistics.json").read_text())
        expected_count = len(origins) * len(config["policies"]) * len(config["costs"])
        if len(summaries) != expected_count or summaries.duplicated(["origin_id", "policy", "cost_id"]).any():
            raise AssertionError("unit opportunity grid size/uniqueness")
        if unit.duplicated(["origin_id", "policy", "cost_id", "ts"]).any():
            raise AssertionError("unit daily grid uniqueness")
        if accounts.duplicated(["policy", "cost_id", "ts"]).any():
            raise AssertionError("portfolio daily grid uniqueness")
        daily_numbers = ["open_before", "open_after", "close_value", "cash_open_before", "cash_open_after", "cash_close", "qty_open_before", "qty_open_after", "qty_close", "fee_open", "slippage_open", "carry_close", "intraday_low_value"]
        summary_numbers = ["entry_price", "exit_price", "qty", "return", "observed_return", "fees", "slippage", "carry", "holding_days", "last_value", "last_cash", "last_qty", "entry_index", "exit_index", "pullback_index", "restart_index"]
        summary_exact = ["normal_complete", "released", "unresolved", "terminal_status", "data_interrupted", "entered", "entry_ts", "exit_ts", "release_ts", "release_reason", "last_mark_ts"]
        count_units = count_days = 0
        max_unit_error = max_portfolio_error = max_action_error = 0.
        for cost in config["costs"]:
            reference_summary = []
            for policy in config["policies"]:
                sub = summaries.loc[(summaries.cost_id == cost["id"]) & (summaries.policy == policy)].set_index("origin_id")
                rows = unit.loc[(unit.cost_id == cost["id"]) & (unit.policy == policy)].reset_index(drop=True)
                groups = rows.groupby("origin_id", sort=False).indices
                if set(sub.index) != set(origin_lookup) or set(groups) != set(origin_lookup):
                    raise AssertionError("future-gated candidate or missing unit arm")
                paths = {}
                for oid, r in origin_lookup.items():
                    segment = segments[(str(r["symbol"]), str(r["segment"]))]
                    expected, path = reference_unit(segment, r, policy, cost, config)
                    actual = sub.loc[oid]
                    ad = rows.iloc[groups[oid]].sort_values("ts").reset_index(drop=True)
                    assert_values(ad.ts, path.ts, "unit daily timestamps")
                    max_unit_error = max(max_unit_error, compare_numeric(ad[daily_numbers], path[daily_numbers], f"unit daily {oid}"))
                    for col in ("entry_open", "exit_open", "release_open", "data_gap", "has_bar", "release_reason"):
                        assert_values(ad[col], path[col], f"unit daily {col}")
                    max_unit_error = max(max_unit_error, compare_numeric([actual[c] for c in summary_numbers], [expected[c] for c in summary_numbers], "unit summary"))
                    for col in summary_exact:
                        assert_values([actual[col]], [expected[col]], f"unit summary {col}")
                    reason = {"RISK": "RISK_STOP", "TREND": "TREND_FAILURE", "TIME": "TIME_20" if policy == "A" else "TIME_60"}.get(expected["exit_reason"], "")
                    assert_values([actual.exit_reason], [reason], "risk/trend/time precedence")
                    if bool(actual.complete_window_60) != (oid in complete_set):
                        raise AssertionError("unit complete-window metadata")
                    for horizon in (20, 60):
                        check_label(actual, segment, expected["entry_index"] if expected["entered"] else 0, expected["entry_price"], r["atr"], horizon, "entry", expected["entered"])
                    paths[oid] = path
                    reference_summary.append(dict(origin_id=oid, policy=policy, cost_id=cost["id"], normal_complete=expected["normal_complete"], return_=expected["return"]))
                    count_units += 1
                    count_days += len(path)
                expected_daily, expected_actions = reference_portfolio(eo, paths, policy, cost["id"], config)
                actual_daily = accounts.loc[(accounts.cost_id == cost["id"]) & (accounts.policy == policy)].sort_values("ts").reset_index(drop=True)
                actual_actions = actions.loc[(actions.cost_id == cost["id"]) & (actions.policy == policy)].reset_index(drop=True)
                for col in ("ts", "close_ts", "policy", "cost_id"):
                    assert_values(actual_daily[col], expected_daily[col], f"account {col}")
                numeric = [c for c in expected_daily if c not in ("ts", "close_ts", "policy", "cost_id")]
                max_portfolio_error = max(max_portfolio_error, compare_numeric(actual_daily[numeric], expected_daily[numeric], "account daily"))
                max_action_error = max(max_action_error, compare_actions(actual_actions, expected_actions))
                reported = metrics[cost["id"] + "." + policy]
                recent = recent_account_slices(expected_daily, pd.Timestamp(config["end"]), config["recent_days"], config["initial_equity"])
                for row in recent.to_dict("records"):
                    a = reported["recent"][str(row["days"])]
                    compare_numeric([a["return_"], a["max_drawdown"]], [row["return"], row["max_drawdown"]], "inherited recent account slices")
                compare_numeric([reported["total_return"], reported["end_equity"], reported["max_drawdown"], reported["fees"], reported["slippage"], reported["hypothetical_carry"], reported["unresolved_zero_value_return"]], [expected_daily.equity.iloc[-1]/config["initial_equity"]-1, expected_daily.equity.iloc[-1], expected_daily.drawdown.min(), expected_daily.fee.sum(), expected_daily.slippage.sum(), expected_daily.hypothetical_carry.sum(), expected_daily.unresolved_zero_value_equity.iloc[-1]/config["initial_equity"]-1], "account aggregate metrics")
                if reported["event_counts"] != expected_actions.event.value_counts().to_dict():
                    raise AssertionError("opportunity admission/miss counts")
                print(f"AUDIT reconstructed {cost['id']} {policy} units={len(paths)} elapsed={time.monotonic()-start:.1f}s", flush=True)
            expected_table = pd.DataFrame(reference_summary)
            good = expected_table.normal_complete & expected_table.origin_id.isin(complete_set)
            paired = expected_table.loc[good].pivot(index="origin_id", columns="policy", values="return_").dropna().sort_index()
            actual = pd.read_parquet(result_dir / f"paired-{cost['id']}.parquet").sort_values("origin_id").reset_index(drop=True)
            assert_values(actual.origin_id, paired.index, "common three-arm paired set")
            compare_numeric(actual[["A", "B", "C"]], paired[["A", "B", "C"]], "paired returns")
            for col in ("symbol", "origin_ts"):
                assert_values(actual[col], [origin_lookup[oid][col] for oid in paired.index], f"paired {col}")
            means = paired[["A", "B", "C"]].mean().to_numpy()
            points = np.r_[means, means[1]-means[0], means[2]-means[1]]
            report = statistics[cost["id"]]
            values = report["points"] if cost["id"] == "base" else [report["points"][k] for k in ("A", "B", "C", "B_minus_A", "C_minus_B")]
            compare_numeric(values, points, "paired mean contrasts")
            if report["n"] != len(paired):
                raise AssertionError("paired n")
            if cost["id"] == "base":
                inferred, replicas = reference_paired_statistics(actual, config)
                for col in ("points", "lower", "upper"):
                    compare_numeric(report[col], inferred[col], "independent simultaneous " + col)
                for a, e in zip(report["blocks"], inferred["blocks"], strict=True):
                    for col in ("standard_error", "lower", "upper", "critical"):
                        compare_numeric(a[col], e[col], "independent block " + col)
                np.savez_compressed(output_dir / "independent-paired-bootstrap.npz", **replicas)
        if count_units != expected_count or count_days != len(unit):
            raise AssertionError("all unit paths were not audited")
        stage("unit_paths_and_portfolios", units=count_units, unit_days=count_days, portfolio_rows=len(accounts), actions=len(actions), max_unit_error=max_unit_error, max_portfolio_error=max_portfolio_error, max_action_error=max_action_error)
        if verify_production_inputs(family, result_dir) != before:
            raise AssertionError("production changed during audit")
        receipt.update(status="PASS", completed_utc=dt.datetime.now(dt.timezone.utc).isoformat(), elapsed_seconds=time.monotonic()-start, independent_of_production_modules=True)
        print("INDEPENDENT AUDIT PASS", flush=True)
    except Exception as exc:
        receipt.update(status="DATA_OR_REPRODUCTION_FAILURE", error_type=type(exc).__name__, error=str(exc), elapsed_seconds=time.monotonic()-start)
        raise
    finally:
        (output_dir / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2, default=str, allow_nan=False) + "\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", type=Path, default=FAMILY)
    parser.add_argument("--results", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    audit_result(args.family, args.results or args.family / "artifacts/research-20260909", args.output or args.family / "artifacts/audit-research-20260909")


if __name__ == "__main__":
    main()
