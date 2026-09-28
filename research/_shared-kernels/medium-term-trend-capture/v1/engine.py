"""MTTC v1：过去特征、共同候选与单位资金三臂路径；只接受调用方注入的帧。"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping

import numpy as np
import pandas as pd

from strategy_lab.data.research_inputs import complete_window_mask

DAY = pd.Timedelta(days=1)
POLICIES = ("A", "B", "C")
ORIGIN_COLUMNS = (
    "origin_id", "symbol", "segment", "origin_ts", "origin_index", "atr",
    "liquidity", "first_observable", "strength", "r20", "signal_ts",
)
DAILY_COLUMNS = (
    "origin_id", "policy", "cost_id", "ts", "local_index", "age", "has_bar",
    "origin_row", "open", "high", "low", "close", "r20", "open_before",
    "open_after", "close_value", "cash_open_before", "cash_open_after", "cash_close",
    "qty_open_before", "qty_open_after", "qty_close", "entry_open", "exit_open",
    "release_open", "release_reason", "fee_open", "slippage_open", "carry_close",
    "entry_fill", "exit_fill", "pending_close", "data_gap", "holding_day",
    "intraday_low_value", "intraday_high_value", "intraday_stop_breach",
    "stop_price", "pullback_close", "restart_close", "wait_peak_before",
    "wait_peak_after", "cost_cash_shortfall",
)
SCHEMA = {
    "timestamps": "UTC bar opens; signal_ts/entry_signal_ts/exit_signal_ts identify the preceding bar close",
    "origin_index": "zero-based local_index within one complete eligible research segment",
    "daily_scope": "origin information row through release row; unresolved paths end at last observed bar or first known missing open",
    "daily_values": "unit budget=1; open_before/open_after marked at unslipped open; close_value=cash_close+qty_close*close",
    "gap_row": "has_bar=False, data_gap=True, no price fill or carry invented; held quantity remains and is not released",
    "return": "final value minus 1 only for normal_complete; otherwise NaN, with observed_return always retained",
    "qty": "summary qty is original executed entry quantity, never overwritten by exit",
    "states": ["ENTRY_PENDING", "WAIT_PULLBACK", "WAIT_RESTART", "HOLDING",
               "EXIT_PENDING:RISK_STOP", "EXIT_PENDING:TREND_FAILURE", "EXIT_PENDING:TIME_20",
               "EXIT_PENDING:TIME_60", "RELEASE_PENDING:WAIT_TREND_FAILURE", "RELEASED",
               "UNRESOLVED_POSITION", "DATA_GAP_CANCELLED"],
}


def _check_config(config: Mapping) -> None:
    if config["direction"] != "LONG" or tuple(config["policies"]) != POLICIES:
        raise ValueError("this kernel implements only the frozen LONG A/B/C comparison")
    for name in ("warmup", "momentum_window", "atr_window", "wait_days", "fixed_hold_days", "max_hold_days"):
        value = config[name]
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if config["warmup"] < max(config["momentum_window"] + 1, config["atr_window"]):
        raise ValueError("warmup must contain complete momentum and ATR history")
    if not 2 <= config["wait_days"] <= config["max_hold_days"] or config["fixed_hold_days"] > config["max_hold_days"]:
        raise ValueError("waiting/fixed holding must fit the common maximum horizon")
    for name in ("strength_threshold", "pullback_atr", "stop_atr", "slot_risk_fraction", "slot_notional_fraction"):
        if not np.isfinite(config[name]) or config[name] <= 0:
            raise ValueError(f"{name} must be finite and positive")
    if config["slot_notional_fraction"] > 1 or config["slot_risk_fraction"] > 1:
        raise ValueError("unit allocation fractions cannot exceed one")
    for name in ("start", "end"):
        stamp = pd.Timestamp(config[name])
        if stamp.tz is None or stamp.tz_convert("UTC") != stamp.tz_convert("UTC").normalize():
            raise ValueError(f"{name} must be an aware UTC-daily boundary")
    if pd.Timestamp(config["start"]) >= pd.Timestamp(config["end"]):
        raise ValueError("empty or reversed study range")


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    if len(values) >= window:
        result[window-1:] = np.lib.stride_tricks.sliding_window_view(values, window).mean(axis=1)
    return result


def build_panel(frames: dict[str, pd.DataFrame], config: Mapping) -> pd.DataFrame:
    """保留注入的原始行与可信mask；不读取数据湖、不跨连续段计算。"""
    _check_config(config)
    if not isinstance(frames, dict) or not frames:
        raise ValueError("a nonempty symbol -> returned-frame mapping is required")
    begin, end = pd.Timestamp(config["start"]), pd.Timestamp(config["end"])
    warmup, window, atr_window = (config[k] for k in ("warmup", "momentum_window", "atr_window"))
    required = {"symbol", "ts", "open", "high", "low", "close", "volume", "quote_volume",
                "eligible", "research_segment_id", "research_window_valid"}
    parts = []
    for symbol, source in sorted(frames.items()):
        if source.empty or not required.issubset(source.columns):
            raise ValueError(f"{symbol}: missing required returned-frame fields")
        f = source.reset_index(drop=True).copy()
        if not f.symbol.eq(symbol).all() or f.symbol.isna().any():
            raise ValueError(f"{symbol}: returned-frame identity mismatch")
        if not isinstance(f.ts.dtype, pd.DatetimeTZDtype):
            raise ValueError(f"{symbol}: aware timestamps required")
        f["ts"] = f.ts.dt.tz_convert("UTC")
        if (f.ts.isna().any() or not f.ts.is_monotonic_increasing or f.ts.duplicated().any()
                or not f.ts.eq(f.ts.dt.normalize()).all() or (f.ts < begin).any() or (f.ts+DAY > end).any()):
            raise ValueError(f"{symbol}: unordered, duplicate, unclosed or out-of-range daily bars")
        for name in ("eligible", "research_window_valid"):
            if not pd.api.types.is_bool_dtype(f[name]) or f[name].isna().any():
                raise ValueError(f"{symbol}: {name} must be a nonmissing boolean mask")
        if (f.loc[f.eligible, "research_segment_id"].isna().any()
                or f.loc[~f.eligible, "research_segment_id"].notna().any()):
            raise ValueError(f"{symbol}: eligible/segment identity mismatch")
        official = complete_window_mask(f, backward=warmup, forward=0).to_numpy(bool)
        if not np.array_equal(official, f.research_window_valid.to_numpy(bool)):
            raise ValueError(f"{symbol}: verified past window differs from requested warmup")
        values = {name: np.full(len(f), np.nan) for name in
                  ("r20", "sigma20", "strength", "atr14", "liquidity20", "true_range")}
        local = np.full(len(f), -1, dtype=np.int64)
        for _, g in f.loc[f.eligible].groupby("research_segment_id", sort=False):
            idx = g.index.to_numpy()
            if not np.all(np.diff(idx) == 1) or not g.ts.diff().iloc[1:].eq(DAY).all():
                raise ValueError(f"{symbol}: eligible segment is not contiguous")
            o, high, low, close, quote = (g[name].to_numpy(float) for name in
                                         ("open", "high", "low", "close", "quote_volume"))
            if (not np.isfinite(np.column_stack((o, high, low, close, quote))).all()
                    or (np.column_stack((o, high, low, close)) <= 0).any() or (quote < 0).any()
                    or (high < np.maximum(o, close)).any() or (low > np.minimum(o, close)).any()):
                raise ValueError(f"{symbol}: invalid eligible OHLC or quote_volume")
            n = len(g)
            local[idx] = np.arange(n)
            previous = np.r_[close[0], close[:-1]]
            tr = np.maximum(high-low, np.maximum(np.abs(high-previous), np.abs(low-previous)))
            values["true_range"][idx] = tr
            values["atr14"][idx] = _rolling_mean(tr, atr_window)
            values["liquidity20"][idx] = _rolling_mean(quote, window)
            if n > window:
                returns = np.log(close[1:]/close[:-1])
                numerator = np.log(close[window:]/close[:-window])
                sigma = np.lib.stride_tricks.sliding_window_view(returns, window).std(axis=1, ddof=1)
                positions = idx[window:]
                values["r20"][positions], values["sigma20"][positions] = numerator, sigma
                okay = np.isfinite(sigma) & (sigma > 0) & np.isfinite(numerator)
                values["strength"][positions[okay]] = numerator[okay]/(sigma[okay]*np.sqrt(window))
        for name, array in values.items():
            f[name] = array
        f["segment"] = f.research_segment_id
        f["local_index"] = local
        f["source_index"] = np.arange(len(f), dtype=np.int64)
        f["feature_valid"] = (official & np.isfinite(f.strength) & np.isfinite(f.atr14) & f.atr14.gt(0)
                              & np.isfinite(f.liquidity20) & f.liquidity20.gt(0))
        parts.append(f)
    result = pd.concat(parts, ignore_index=True)
    result.attrs["kernel"] = "medium-term-trend-capture/v1"
    result.attrs["schema"] = SCHEMA
    return result


def build_origins(panel: pd.DataFrame, config: Mapping) -> pd.DataFrame:
    """每段armed起步；只有r20<=0才能重新arm，退出或等待失败不重置候选。"""
    _check_config(config)
    required = {"symbol", "ts", "segment", "local_index", "eligible", "research_window_valid",
                "r20", "strength", "atr14", "liquidity20", "feature_valid"}
    if not required.issubset(panel.columns):
        raise ValueError("build_origins requires the engine's complete past-only panel")
    rows = []
    columns = ["symbol", "ts", "local_index", "r20", "strength", "atr14", "liquidity20", "feature_valid"]
    for (symbol, segment_id), g in panel.loc[panel.eligible].groupby(["symbol", "segment"], sort=False):
        if (not g.ts.diff().iloc[1:].eq(DAY).all()
                or not np.array_equal(g.local_index.to_numpy(), np.arange(len(g)))):
            raise ValueError("origin discovery requires full, ordered eligible segments")
        armed = True
        for _, ts, index, r20, strength, atr, liquidity, valid in g[columns].itertuples(index=False, name=None):
            if np.isfinite(r20) and r20 <= 0:
                armed = True
            if armed and valid and strength > config["strength_threshold"]:
                identity = f"{symbol}\n{segment_id}\n{ts.isoformat()}"
                rows.append({"origin_id": hashlib.sha256(identity.encode()).hexdigest(),
                             "symbol": symbol, "segment": segment_id, "origin_ts": ts,
                             "origin_index": int(index), "atr": float(atr), "liquidity": float(liquidity),
                             "first_observable": bool(index == config["warmup"]-1),
                             "strength": float(strength), "r20": float(r20), "signal_ts": ts+DAY})
                armed = False
    result = pd.DataFrame(rows, columns=ORIGIN_COLUMNS)
    if len(result):
        result = result.sort_values(["origin_ts", "symbol", "origin_id"], kind="stable").reset_index(drop=True)
        if result.origin_id.duplicated().any():
            raise ValueError("origin identity collision")
    return result


def _unit_inputs(segment: pd.DataFrame, origin: Mapping, policy: str, cost: Mapping, config: Mapping):
    _check_config(config)
    if policy not in POLICIES:
        raise ValueError("unknown policy")
    for name in ("fee", "slippage", "daily_carry"):
        if not np.isfinite(cost[name]) or not 0 <= cost[name] < 1:
            raise ValueError(f"{name} must be finite in [0,1)")
    if not isinstance(cost["id"], str) or not cost["id"]:
        raise ValueError("named cost scenario required")
    g = segment.reset_index(drop=True)
    required = {"symbol", "segment", "ts", "local_index", "eligible", "open", "high", "low", "close", "r20"}
    if g.empty or not required.issubset(g.columns) or not g.eligible.all():
        raise ValueError("a complete eligible segment is required")
    if (g.symbol.nunique() != 1 or g.segment.nunique() != 1
            or not isinstance(g.ts.dtype, pd.DatetimeTZDtype)
            or not g.ts.diff().iloc[1:].eq(DAY).all()
            or not np.array_equal(g.local_index.to_numpy(), np.arange(len(g)))):
        raise ValueError("segment identity, daily continuity or local_index invalid")
    a = g[["open", "high", "low", "close"]].to_numpy(float)
    if (not np.isfinite(a).all() or (a <= 0).any() or (a[:, 1] < np.maximum(a[:, 0], a[:, 3])).any()
            or (a[:, 2] > np.minimum(a[:, 0], a[:, 3])).any()):
        raise ValueError("invalid segment OHLC")
    index = origin["origin_index"]
    if isinstance(index, (bool, np.bool_)) or int(index) != index or not 0 <= index < len(g):
        raise ValueError("origin_index is outside the full segment")
    index = int(index)
    if (origin["symbol"] != g.symbol.iloc[0] or origin["segment"] != g.segment.iloc[0]
            or pd.Timestamp(origin["origin_ts"]) != g.ts.iloc[index]):
        raise ValueError("origin does not identify the supplied segment row")
    if not np.isfinite(origin["atr"]) or origin["atr"] <= 0:
        raise ValueError("origin ATR must be positive and finite")
    if (g.ts+DAY > pd.Timestamp(config["end"])).any():
        raise ValueError("segment contains bars outside the frozen closed cutoff")
    return g, index


def simulate_opportunity(segment: pd.DataFrame, origin: Mapping, policy: str,
                         cost: Mapping, config: Mapping) -> dict:
    """单一origin、单位预算1、自融资固定数量路径；释放后的资金由组合调用方接管。

    daily中的origin行仅说明候选收盘后的单位预算初态，并无事前开盘准入。
    所有真实入/出场在后续开盘；最后一根收盘不会因为未来缺口而被强制平仓。
    """
    origin = dict(origin)
    g, first = _unit_inputs(segment, origin, policy, cost, config)
    dates = g.ts.tolist()
    opening, high, low, close, r20 = (g[name].to_numpy(float) for name in ("open", "high", "low", "close", "r20"))
    atr = float(origin["atr"])
    fee, slip, carry_rate = (float(cost[name]) for name in ("fee", "slippage", "daily_carry"))
    wait, fixed, maximum = (config[name] for name in ("wait_days", "fixed_hold_days", "max_hold_days"))
    hard_index = first + maximum + 1
    fixed_index = first + fixed + 1
    expiry_index = first + wait
    state = "WAIT_PULLBACK" if policy == "C" else "ENTRY_PENDING"
    cash, qty, original_qty = 1.0, 0.0, 0.0
    fee_total = carry_total = slip_total = 0.0
    entered = released = normal = False
    entry_ts = exit_ts = entry_signal_ts = exit_signal_ts = release_ts = None
    entry_index = exit_index = None
    entry_price = exit_price = entry_reference = exit_reference = np.nan
    entry_fee = exit_fee = 0.0
    entry_signal_ts = dates[first]+DAY if policy in ("A", "B") else None
    stop_price, peak = np.nan, close[first]
    pullback_index = restart_index = None
    pullback_ts = restart_ts = None
    exit_reason = release_reason = ""
    terminal_status = ""
    holding_days = 0
    any_shortfall = any_intraday_breach = False
    min_cash, min_value, min_intraday, peak_value, max_dd = 1.0, 1.0, 1.0, 1.0, 0.0
    rows = []

    def daily_row(i, *, real=True):
        ts = dates[i] if real else dates[-1]+DAY
        return {
            "origin_id": origin["origin_id"], "policy": policy, "cost_id": cost["id"],
            "ts": ts, "local_index": i, "age": i-first, "has_bar": real,
            "origin_row": i == first, "open": float(opening[i]) if real else np.nan,
            "high": float(high[i]) if real else np.nan, "low": float(low[i]) if real else np.nan,
            "close": float(close[i]) if real else np.nan, "r20": float(r20[i]) if real else np.nan,
            "entry_open": False, "exit_open": False, "release_open": False, "release_reason": "",
            "fee_open": 0.0, "slippage_open": 0.0, "carry_close": 0.0,
            "entry_fill": np.nan, "exit_fill": np.nan, "data_gap": not real,
            "holding_day": False, "intraday_stop_breach": False, "stop_price": stop_price,
            "pullback_close": False, "restart_close": False, "wait_peak_before": peak,
            "wait_peak_after": peak, "cost_cash_shortfall": False,
        }

    last_mark_ts = dates[first]+DAY
    for i in range(first, min(len(g), hard_index+1)):
        row = daily_row(i)
        row["cash_open_before"], row["qty_open_before"] = cash, qty
        row["open_before"] = cash+qty*opening[i]
        if i > first:
            if qty > 0 and (state.startswith("EXIT_PENDING:") or i >= (fixed_index if policy == "A" else hard_index)):
                reason = state.split(":", 1)[1] if state.startswith("EXIT_PENDING:") else ("TIME_20" if policy == "A" else "TIME_60")
                exit_reference, exit_price = opening[i], opening[i]*(1-slip)
                exit_fee = qty*exit_price*fee
                row["slippage_open"] = qty*(opening[i]-exit_price)
                cash += qty*exit_price-exit_fee
                qty = 0.0
                exit_ts, exit_index, exit_reason = dates[i], i, reason
                row["exit_open"], row["exit_fill"], row["fee_open"] = True, exit_price, exit_fee
                released = normal = True
                release_ts, release_reason = dates[i], reason
                terminal_status, state = "COMPLETED_TRADE", "RELEASED"
            elif state.startswith("RELEASE_PENDING:") or (policy == "C" and state in ("WAIT_PULLBACK", "WAIT_RESTART") and i >= expiry_index):
                reason = state.split(":", 1)[1] if state.startswith("RELEASE_PENDING:") else "WAIT_EXPIRED"
                released = normal = True
                release_ts, release_reason = dates[i], reason
                terminal_status, state = reason, "RELEASED"
            elif state == "ENTRY_PENDING":
                entry_reference, entry_price = opening[i], opening[i]*(1+slip)
                qty = min(config["slot_notional_fraction"]/(entry_price*(1+fee)),
                          config["slot_risk_fraction"]/(config["stop_atr"]*atr))
                if not np.isfinite(qty) or qty <= 0:
                    raise ValueError("nonpositive or nonfinite entry quantity")
                original_qty = qty
                entry_fee = qty*entry_price*fee
                cash -= qty*entry_price+entry_fee
                entered, entry_ts, entry_index = True, dates[i], i
                stop_price = entry_price-config["stop_atr"]*atr
                row["entry_open"], row["entry_fill"], row["fee_open"] = True, entry_price, entry_fee
                row["slippage_open"] = qty*(entry_price-opening[i])
                state = "HOLDING"
        fee_total += row["fee_open"]
        slip_total += row["slippage_open"]
        row["release_open"], row["release_reason"] = released, release_reason if released else ""
        row["cash_open_after"], row["qty_open_after"] = cash, qty
        row["open_after"] = cash+qty*opening[i]
        row["stop_price"] = stop_price
        row["intraday_low_value"] = cash+qty*low[i]
        row["intraday_high_value"] = cash+qty*high[i]
        if qty > 0:
            holding_days += 1
            row["holding_day"] = True
            row["intraday_stop_breach"] = bool(low[i] <= stop_price)
            any_intraday_breach |= row["intraday_stop_breach"]
            row["carry_close"] = qty*close[i]*carry_rate
            cash -= row["carry_close"]
            carry_total += row["carry_close"]
            if close[i] <= stop_price:
                state, exit_signal_ts = "EXIT_PENDING:RISK_STOP", dates[i]+DAY
            elif policy in ("B", "C") and r20[i] <= 0:
                state, exit_signal_ts = "EXIT_PENDING:TREND_FAILURE", dates[i]+DAY
            elif i+1 >= (fixed_index if policy == "A" else hard_index):
                state = "EXIT_PENDING:TIME_20" if policy == "A" else "EXIT_PENDING:TIME_60"
                exit_signal_ts = dates[i]+DAY
            else:
                state = "HOLDING"
        elif not released and policy == "C" and first < i < expiry_index:
            if r20[i] <= 0:
                state = "RELEASE_PENDING:WAIT_TREND_FAILURE"
            elif pullback_index is None:
                if close[i] <= peak-config["pullback_atr"]*atr:
                    pullback_index, pullback_ts = i, dates[i]
                    row["pullback_close"] = True
                    state = "WAIT_RESTART"
                peak = max(peak, close[i])
            elif i >= pullback_index+1 and close[i] > high[i-1]:
                restart_index, restart_ts = i, dates[i]
                row["restart_close"] = True
                entry_signal_ts, state = dates[i]+DAY, "ENTRY_PENDING"
        row["wait_peak_after"] = peak
        row["cash_close"], row["qty_close"] = cash, qty
        row["close_value"] = cash+qty*close[i]
        row["pending_close"] = state
        row["cost_cash_shortfall"] = bool(cash < 0)
        any_shortfall |= row["cost_cash_shortfall"]
        min_cash = min(min_cash, cash)
        min_value = min(min_value, row["close_value"])
        min_intraday = min(min_intraday, row["intraday_low_value"])
        peak_value = max(peak_value, row["close_value"])
        max_dd = min(max_dd, row["close_value"]/peak_value-1)
        last_mark_ts = dates[i] if released else dates[i]+DAY
        rows.append(row)
        if released:
            break

    data_interrupted = False
    if not released:
        # A missing execution open is represented only when it falls inside the
        # frozen study range. No liquidation price is invented at the prior close.
        missing_ts = dates[-1]+DAY
        if missing_ts < pd.Timestamp(config["end"]):
            data_interrupted = True
            row = daily_row(len(g), real=False)
            last_value = cash+qty*close[-1]
            for name in ("open_before", "open_after", "close_value", "intraday_low_value", "intraday_high_value"):
                row[name] = last_value
            for name in ("cash_open_before", "cash_open_after", "cash_close"):
                row[name] = cash
            for name in ("qty_open_before", "qty_open_after", "qty_close"):
                row[name] = qty
            row["cost_cash_shortfall"] = bool(cash < 0)
            if qty > 0:
                terminal_status, state = "UNRESOLVED_POSITION", "UNRESOLVED_POSITION"
            else:
                released = True
                release_ts, release_reason = missing_ts, "DATA_GAP_CANCELLED"
                terminal_status, state = "DATA_GAP_CANCELLED", "DATA_GAP_CANCELLED"
                row["release_open"], row["release_reason"] = True, release_reason
            row["pending_close"] = state
            rows.append(row)
        else:
            terminal_status = ("ADMIN_END_POSITION" if qty > 0 else
                               "ADMIN_END_PENDING_ENTRY" if state == "ENTRY_PENDING" else "ADMIN_END_WAIT")
    daily = pd.DataFrame(rows, columns=DAILY_COLUMNS)
    last_value = float(daily.close_value.iloc[-1])
    summary = {
        "origin_id": origin["origin_id"], "symbol": origin["symbol"], "segment": origin["segment"],
        "origin_ts": dates[first], "origin_index": first, "atr": atr, "liquidity": origin.get("liquidity", np.nan),
        "first_observable": bool(origin.get("first_observable", False)), "policy": policy, "cost_id": cost["id"],
        "budget": 1.0, "entered": entered, "entry_ts": entry_ts, "entry_index": entry_index,
        "entry_signal_ts": entry_signal_ts, "entry_reference_price": entry_reference, "entry_price": entry_price,
        "qty": original_qty, "stop_price": stop_price, "exit_ts": exit_ts, "exit_index": exit_index,
        "exit_signal_ts": exit_signal_ts, "exit_reference_price": exit_reference, "exit_price": exit_price,
        "exit_reason": exit_reason, "release_ts": release_ts, "release_reason": release_reason,
        "released": released, "normal_complete": normal, "unresolved": not released,
        "data_interrupted": data_interrupted, "terminal_status": terminal_status,
        "return": last_value-1 if normal else np.nan, "observed_return": last_value-1,
        "fees": fee_total, "entry_fee": entry_fee, "exit_fee": exit_fee, "slippage": slip_total,
        "carry": carry_total, "holding_days": holding_days, "last_mark_ts": last_mark_ts,
        "last_value": last_value, "last_cash": cash, "last_qty": qty,
        "pullback_index": pullback_index, "pullback_ts": pullback_ts,
        "restart_index": restart_index, "restart_ts": restart_ts,
        "cost_cash_shortfall": any_shortfall, "minimum_cash": min_cash,
        "minimum_close_value": min_value, "minimum_intraday_value": min_intraday,
        "intraday_stop_breach": any_intraday_breach, "max_close_drawdown": max_dd,
        "planned_fixed_exit_ts": dates[first]+(fixed+1)*DAY,
        "planned_hard_exit_ts": dates[first]+(maximum+1)*DAY,
        "planned_wait_expiry_ts": dates[first]+wait*DAY,
        "historical_funding_included": False,
    }
    if not np.isclose(daily.fee_open.sum(), fee_total) or not np.isclose(daily.carry_close.sum(), carry_total):
        raise ValueError("unit cost ledger did not reconcile")
    if normal and (qty != 0 or not released or not np.isfinite(summary["return"])):
        raise ValueError("normal completion requires released cash with no position")
    return {"summary": summary, "daily": daily}
