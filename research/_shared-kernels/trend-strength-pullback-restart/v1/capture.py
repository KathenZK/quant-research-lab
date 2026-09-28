"""本家族的单标的固定数量持有账户；只计算 fee/slippage，不模拟资金费或强平。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


TRADE_COLUMNS = [
    "trade_id", "direction", "signal_index", "signal_bar_ts", "signal_close_ts",
    "entry_index", "entry_ts", "entry_reference_price", "entry_fill_price",
    "quantity", "entry_nav", "entry_notional", "entry_fee", "entry_slippage_cost",
    "scheduled_exit_index", "holding_bars_observed", "ignored_signals",
    "intraday_insolvency_breach", "min_intraday_nav", "max_favorable_price_pnl",
    "max_adverse_price_pnl", "exit_index", "exit_ts", "exit_reference_price",
    "exit_fill_price", "exit_notional", "exit_fee", "exit_slippage_cost",
    "last_observed_index", "last_observed_bar_ts", "terminal_mark_price",
    "terminal_nav_after_fee_slippage", "price_pnl", "total_fees", "total_slippage_cost",
    "pnl_after_fee_slippage", "return_on_entry_nav_after_fee_slippage", "completed", "status",
]

EQUITY_COLUMNS = [
    "row_index", "ts", "observed_close", "mark_price", "direction", "quantity",
    "holding_bars", "trade_id", "entry_executed", "exit_executed", "signal_selected",
    "signal_action", "fee_paid", "slippage_cost", "equity_open_after_fee_slippage",
    "min_intraday_equity_after_entry_fee", "intraday_insolvency_breach",
    "equity_after_fee_slippage", "daily_return_after_fee_slippage",
    "drawdown_after_fee_slippage", "halted", "equity_state",
]


def _validated_inputs(
    bars: pd.DataFrame, selected: np.ndarray, direction: int, fee: float,
    slippage: float, horizon: int,
) -> tuple[pd.DataFrame, np.ndarray]:
    if not isinstance(bars, pd.DataFrame):
        raise TypeError("bars must be a pandas DataFrame")
    required = {"ts", "open", "high", "low", "close"}
    if not required.issubset(bars.columns):
        raise ValueError(f"missing required columns: {sorted(required - set(bars.columns))}")
    if isinstance(direction, (bool, np.bool_)) or direction not in (-1, 1):
        raise ValueError("direction must be +1 or -1")
    if isinstance(horizon, (bool, np.bool_)) or not isinstance(horizon, (int, np.integer)) or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    for name, value in (("fee", fee), ("slippage", slippage)):
        if not np.isscalar(value) or not np.isfinite(value) or value < 0 or value >= 1:
            raise ValueError(f"{name} must be finite and in [0, 1)")
    signals = np.asarray(selected)
    if signals.ndim != 1 or len(signals) != len(bars) or signals.dtype != np.dtype(bool):
        raise ValueError("selected must be a one-dimensional boolean array aligned by row position")
    frame = bars.reset_index(drop=True).copy()
    for column in ("symbol", "research_segment_id"):
        if column in frame and len(frame):
            if frame[column].isna().any() or frame[column].nunique(dropna=False) != 1:
                raise ValueError(f"bars must contain exactly one nonmissing {column}")
    if pd.api.types.is_numeric_dtype(frame["ts"].dtype) and len(frame):
        raise ValueError("ts must be datetime-like; numeric timestamp units must be resolved upstream")
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="raise")
    if frame["ts"].isna().any():
        raise ValueError("ts cannot contain missing values")
    if not frame["ts"].eq(frame["ts"].dt.normalize()).all():
        raise ValueError("ts must identify UTC daily bar opens")
    if len(frame) > 1 and not frame["ts"].diff().iloc[1:].eq(pd.Timedelta(days=1)).all():
        raise ValueError("bars must be strictly ordered, unique, and continuous daily rows")
    try:
        prices = frame[["open", "high", "low", "close"]].to_numpy(dtype=float)
    except (ValueError, TypeError) as exc:
        raise ValueError("OHLC must be numeric") from exc
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("OHLC must be finite and strictly positive")
    if len(prices):
        op, high, low, close = prices.T
        if (high < np.maximum(op, close)).any() or (low > np.minimum(op, close)).any() or (high < low).any():
            raise ValueError("OHLC bounds are inconsistent")
    frame[["open", "high", "low", "close"]] = prices
    return frame, signals.copy()


def run_hold20_account(
    bars: pd.DataFrame,
    selected: np.ndarray,
    direction: int,
    fee: float = 0.001,
    slippage: float = 0.0004,
    horizon: int = 20,
) -> dict[str, Any]:
    """从 NAV=1 开始，顺序回放单 symbol、单连续 research segment。

    selected[i] 在第 i 根收盘后已知，空仓时排队，在第 i+1 根开盘成交。
    p_entry = open * (1 + direction * slippage)。固定正数量
    q = NAV_before_entry / (p_entry * (1 + fee))，故实际入场名义额加
    入场手续费恰等于预算；实际成交名义杠杆不超过 1x，持有期不再调仓。
    多空统一线性 NAV(mark) = entry_NAV - entry_fee
    + direction * q * (mark - p_entry)，空头绝不采用价格倒数收益。

    入场当日为持有第1根，在第 horizon 根收盘按
    p_exit = close * (1 - direction * slippage) 退出，退出费=q*p_exit*fee。
    当日预定退出完成后，可接受当日收盘的新信号；仍在持仓的信号只计数。
    不预看未来长度。段尾未到期持仓仅按最后 close 盯市，不造退出成交或费用。

    close-mark NAV<=0 时停止经济账，保留未截断负值；此时未退出仓位
    标为 OPEN_HALTED_NONPOSITIVE_CLOSE_NAV。之后行只冻结该失败快照，
    不声称继续盯市。若正常到期退出费用使 NAV<=0，则先记真实假设退出
    再停止。日内 high/low 触及非正 NAV 单列 insolvency boundary，
    不用未知盘中路径推定强平价格。任何该边界出现均不具交易认证资格。
    本函数不含 funding、保证金阶梯、强平、容量或成交可得性模型。
    """
    frame, signals = _validated_inputs(bars, selected, direction, fee, slippage, horizon)
    nav = peak = 1.0
    pending: int | None = None
    position: dict[str, Any] | None = None
    unresolved_halted_position: dict[str, Any] | None = None
    trade_rows: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    halted = False
    halt_index: int | None = None
    n_ignored_open = n_ignored_halted = n_entries = 0
    fees_total = slippage_total = 0.0
    breach_bars = 0
    one_day = pd.Timedelta(days=1)

    def finish_record(pos: dict[str, Any], index: int, mark: float, status: str, completed: bool) -> dict[str, Any]:
        record = dict(pos)
        record.update(
            last_observed_index=index,
            last_observed_bar_ts=frame.at[index, "ts"],
            terminal_mark_price=mark,
            terminal_nav_after_fee_slippage=nav,
            price_pnl=direction * pos["quantity"] * (mark - pos["entry_fill_price"]),
            total_fees=pos["entry_fee"] + pos["exit_fee"],
            total_slippage_cost=pos["entry_slippage_cost"] + pos["exit_slippage_cost"],
            pnl_after_fee_slippage=nav - pos["entry_nav"],
            return_on_entry_nav_after_fee_slippage=nav / pos["entry_nav"] - 1.0,
            completed=completed,
            status=status,
        )
        return record

    for i, bar in enumerate(frame.itertuples(index=False)):
        previous_nav = nav
        was_halted = halted
        entry_executed = exit_executed = False
        day_fee = day_slippage = 0.0
        open_nav = intraday_min = nav
        intraday_breach = False
        row_trade_id = None
        holding_bars = 0
        mark_price = float(bar.close) if not halted else np.nan

        if not halted and pending is not None:
            if position is not None or pending != i - 1:
                raise AssertionError("invalid pending-entry state")
            fill = float(bar.open) * (1.0 + direction * slippage)
            quantity = nav / (fill * (1.0 + fee))
            entry_notional = quantity * fill
            day_fee = entry_notional * fee
            day_slippage = quantity * abs(fill - float(bar.open))
            n_entries += 1
            position = dict(
                trade_id=n_entries, direction=direction, signal_index=pending,
                signal_bar_ts=frame.at[pending, "ts"],
                signal_close_ts=frame.at[pending, "ts"] + one_day,
                entry_index=i, entry_ts=bar.ts, entry_reference_price=float(bar.open),
                entry_fill_price=fill, quantity=quantity, entry_nav=nav,
                entry_notional=entry_notional, entry_fee=day_fee,
                entry_slippage_cost=day_slippage, scheduled_exit_index=i + horizon - 1,
                holding_bars_observed=0, ignored_signals=0,
                intraday_insolvency_breach=False, min_intraday_nav=np.inf,
                max_favorable_price_pnl=-np.inf, max_adverse_price_pnl=np.inf,
                exit_index=None, exit_ts=pd.NaT, exit_reference_price=np.nan,
                exit_fill_price=np.nan, exit_notional=0.0, exit_fee=0.0,
                exit_slippage_cost=0.0,
            )
            pending = None
            entry_executed = True

        if not halted and position is not None:
            pos = position
            row_trade_id = pos["trade_id"]
            holding_bars = i - pos["entry_index"] + 1
            pos["holding_bars_observed"] = holding_bars
            base = pos["entry_nav"] - pos["entry_fee"]
            quantity = pos["quantity"]
            fill = pos["entry_fill_price"]
            open_nav = base + direction * quantity * (float(bar.open) - fill)
            adverse = float(bar.low if direction == 1 else bar.high)
            favorable = float(bar.high if direction == 1 else bar.low)
            intraday_min = base + direction * quantity * (adverse - fill)
            intraday_breach = intraday_min <= 0.0
            breach_bars += int(intraday_breach)
            pos["intraday_insolvency_breach"] |= intraday_breach
            pos["min_intraday_nav"] = min(pos["min_intraday_nav"], intraday_min)
            pos["max_favorable_price_pnl"] = max(pos["max_favorable_price_pnl"], direction * quantity * (favorable - fill))
            pos["max_adverse_price_pnl"] = min(pos["max_adverse_price_pnl"], direction * quantity * (adverse - fill))
            nav = base + direction * quantity * (float(bar.close) - fill)

            if nav <= 0.0:
                halted, halt_index = True, i
                trade_rows.append(finish_record(pos, i, float(bar.close), "OPEN_HALTED_NONPOSITIVE_CLOSE_NAV", False))
                unresolved_halted_position = pos
                position = None
            elif holding_bars == horizon:
                exit_fill = float(bar.close) * (1.0 - direction * slippage)
                exit_notional = quantity * exit_fill
                exit_fee = exit_notional * fee
                exit_slippage = quantity * abs(exit_fill - float(bar.close))
                nav = base + direction * quantity * (exit_fill - fill) - exit_fee
                pos.update(exit_index=i, exit_ts=bar.ts + one_day,
                           exit_reference_price=float(bar.close), exit_fill_price=exit_fill,
                           exit_notional=exit_notional, exit_fee=exit_fee,
                           exit_slippage_cost=exit_slippage)
                day_fee += exit_fee
                day_slippage += exit_slippage
                trade_rows.append(finish_record(pos, i, exit_fill, "COMPLETED_HORIZON", True))
                mark_price = exit_fill
                position = None
                exit_executed = True
                if nav <= 0.0:
                    halted, halt_index = True, i

        signal_action = "NOT_SELECTED"
        if signals[i]:
            if halted:
                signal_action = "IGNORED_HALTED"
                n_ignored_halted += 1
            elif position is not None:
                signal_action = "IGNORED_OPEN_POSITION"
                position["ignored_signals"] += 1
                n_ignored_open += 1
            else:
                pending = i
                signal_action = "QUEUED_NEXT_OPEN"
        fees_total += day_fee
        slippage_total += day_slippage
        peak = max(peak, nav)
        if was_halted:
            equity_state = "HALTED_FROZEN_FAILURE_SNAPSHOT_NOT_CURRENT_MTM"
            open_nav = intraday_min = np.nan
        elif halted:
            equity_state = "HALTED_AT_NONPOSITIVE_NAV"
        elif position is not None:
            equity_state = "OPEN_MARKED_AT_CLOSE"
        else:
            equity_state = "FLAT"
        residual_position = position if position is not None else unresolved_halted_position
        if was_halted and residual_position is not None:
            row_trade_id = residual_position["trade_id"]
            holding_bars = residual_position["holding_bars_observed"]
        equity_rows.append(dict(
            row_index=i, ts=bar.ts, observed_close=float(bar.close), mark_price=mark_price,
            direction=direction if residual_position is not None else 0,
            quantity=residual_position["quantity"] if residual_position is not None else 0.0,
            holding_bars=holding_bars, trade_id=row_trade_id,
            entry_executed=entry_executed, exit_executed=exit_executed,
            signal_selected=bool(signals[i]), signal_action=signal_action,
            fee_paid=day_fee, slippage_cost=day_slippage,
            equity_open_after_fee_slippage=open_nav,
            min_intraday_equity_after_entry_fee=intraday_min,
            intraday_insolvency_breach=intraday_breach,
            equity_after_fee_slippage=nav,
            daily_return_after_fee_slippage=(nav / previous_nav - 1.0) if not was_halted and previous_nav > 0 else np.nan,
            drawdown_after_fee_slippage=nav / peak - 1.0,
            halted=halted, equity_state=equity_state,
        ))

    if position is not None:
        trade_rows.append(finish_record(position, len(frame) - 1, float(frame.iloc[-1]["close"]), "OPEN_CENSORED_SEGMENT_END", False))
    trades = pd.DataFrame(trade_rows, columns=TRADE_COLUMNS)
    equity = pd.DataFrame(equity_rows, columns=EQUITY_COLUMNS)
    equity["trade_id"] = pd.array(equity["trade_id"], dtype="Int64")
    completed_count = sum(bool(row["completed"]) for row in trade_rows)
    censored_count = sum(row["status"] == "OPEN_CENSORED_SEGMENT_END" for row in trade_rows)
    open_halted_count = sum(row["status"] == "OPEN_HALTED_NONPOSITIVE_CLOSE_NAV" for row in trade_rows)
    summary = dict(
        accounting="close-mark economic ledger plus intraday insolvency boundary, not exchange liquidation simulator",
        cost_scope="after_fee_slippage; funding not included and never assumed zero",
        sizing="fixed quantity; filled entry notional plus entry fee equals entry NAV; no rebalancing",
        horizon=int(horizon), direction=int(direction), fee=float(fee), slippage=float(slippage),
        n_bars=len(frame), initial_equity=1.0, final_equity_after_fee_slippage=float(nav),
        total_return_after_fee_slippage=float(nav - 1.0),
        max_drawdown_after_fee_slippage=float(-equity["drawdown_after_fee_slippage"].min()) if len(equity) else 0.0,
        total_fees=float(fees_total), total_slippage_cost=float(slippage_total),
        selected_signals=int(signals.sum()), entered_trades=n_entries,
        completed_trades=completed_count, censored_open_trades=censored_count,
        halted_open_trades=open_halted_count, ignored_signals_while_open=n_ignored_open,
        ignored_signals_after_halt=n_ignored_halted, pending_signals_at_segment_end=int(pending is not None),
        intraday_insolvency_breach=bool(breach_bars), intraday_insolvency_breach_bars=breach_bars,
        halted=halted, halt_index=halt_index,
        final_equity_is_frozen_failure_snapshot=halted,
        executable_certification=False,
        execution_blockers=["FUNDING_NOT_INCLUDED", "MARGIN_AND_LIQUIDATION_NOT_SIMULATED", "FILL_AND_CAPACITY_NOT_VERIFIED"]
            + (["INTRADAY_INSOLVENCY_BOUNDARY_BREACHED"] if breach_bars else [])
            + (["NONPOSITIVE_ECONOMIC_NAV"] if halted else []),
    )
    return {"trades": trades, "equity": equity, "summary": summary}
