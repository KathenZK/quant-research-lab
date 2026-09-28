"""Audit HYPE-1D-MA7-ABT V7.1 transfer on top-volume Binance USD-M perps."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/hype/1d-ma7-asymmetric-body-trend"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"

BASE_URL = "https://fapi.binance.com"
RUN_DATE = "2026-08-11"
OUTPUT_PATH = ARTIFACT_DIR / f"hype_1d_ma7_abt_v7_1_top15_binance_perp_transfer_{RUN_DATE}.json"
FEE_RATE = 0.001
BASE_SLIPPAGE = 0.0004
STRESS_SLIPPAGE = 0.0008
TARGET_LEVERAGE = 1.0
MS_PER_HOUR = 60 * 60 * 1000
MS_PER_DAY = 24 * MS_PER_HOUR
U_MARGIN_QUOTES = {"USDT", "USDC"}
U_MARGIN_CONTRACT_TYPES = {"PERPETUAL", "TRADIFI_PERPETUAL"}


@dataclass(frozen=True, slots=True)
class Candle:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trade_count: int
    close_time: int


@dataclass(slots=True)
class Position:
    side: int
    entry_ts: int
    entry_price_ref: float
    entry_fill: float
    quantity: float
    equity_basis: float
    entry_atr: float
    bars_held: int = 0
    highest_close: float = -math.inf
    lowest_close: float = math.inf
    max_favorable_price: float = 0.0
    oapp_long_run: int = 0
    short_rsi_run: int = 0


@dataclass(slots=True)
class ScheduledOrder:
    action: str
    side: int
    reason: str


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def utc_ms_now() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def request_json(
    path: str,
    params: dict[str, Any] | None = None,
    retries: int = 5,
    *,
    base_url: str = BASE_URL,
) -> Any:
    query = f"?{urlencode(params or {})}" if params else ""
    url = f"{base_url}{path}{query}"
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "quant-research-lab-research/1.0"})
            with urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - network path
            last_error = exc
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"request failed after retries: {url}: {last_error}")


def parse_candle(row: list[Any]) -> Candle:
    return Candle(
        ts=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
        close_time=int(row[6]),
        quote_volume=float(row[7]),
        trade_count=int(row[8]),
    )


def fetch_klines(
    symbol: str,
    interval: str,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int = 1500,
    base_url: str = BASE_URL,
) -> list[Candle]:
    rows: list[Candle] = []
    current = start_ms
    while True:
        params: dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
        if current is not None:
            params["startTime"] = current
        if end_ms is not None:
            params["endTime"] = end_ms
        path = "/fapi/v1/klines" if base_url == BASE_URL else "/api/v3/klines"
        payload = request_json(path, params, base_url=base_url)
        if not payload:
            break
        batch = [parse_candle(row) for row in payload]
        rows.extend(batch)
        if len(batch) < limit:
            break
        next_ts = batch[-1].ts + (MS_PER_DAY if interval == "1d" else MS_PER_HOUR)
        if current is not None and next_ts <= current:
            break
        current = next_ts
        if end_ms is not None and current > end_ms:
            break
        time.sleep(0.03)
    now = utc_ms_now()
    closed = [row for row in rows if row.close_time < now]
    dedup: dict[int, Candle] = {}
    for row in closed:
        dedup[row.ts] = row
    return [dedup[key] for key in sorted(dedup)]


def fetch_funding(symbol: str, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current = start_ms
    while current <= end_ms:
        payload = request_json(
            "/fapi/v1/fundingRate",
            {"symbol": symbol, "startTime": current, "endTime": end_ms, "limit": 1000},
        )
        if not payload:
            break
        for row in payload:
            rows.append(
                {
                    "funding_time": int(row["fundingTime"]),
                    "funding_rate": float(row["fundingRate"]),
                }
            )
        last = int(payload[-1]["fundingTime"])
        current = last + 1
        if len(payload) < 1000:
            break
        time.sleep(0.03)
    return rows


def u_margin_futures_contracts(quote_assets: set[str]) -> list[tuple[str, str]]:
    payload = request_json("/fapi/v1/exchangeInfo")
    contracts: list[tuple[str, str]] = []
    for row in payload.get("symbols", []):
        if (
            row.get("contractType") in U_MARGIN_CONTRACT_TYPES
            and row.get("quoteAsset") in quote_assets
            and row.get("status") == "TRADING"
        ):
            quote = str(row.get("quoteAsset"))
            contract_type = str(row.get("contractType"))
            if contract_type == "TRADIFI_PERPETUAL":
                market_type = "tradifi_perp"
            elif quote == "USDC":
                market_type = "perp_usdc"
            else:
                market_type = "perp_usdt"
            contracts.append((str(row["symbol"]), market_type))
    return sorted(contracts)


def quality(candles: list[Candle], interval_ms: int) -> dict[str, Any]:
    if not candles:
        return {"status": "FAIL", "bars": 0, "reason": "empty"}
    duplicate_count = len(candles) - len({row.ts for row in candles})
    bad_ohlc = sum(
        1
        for row in candles
        if not (
            row.low <= row.open <= row.high
            and row.low <= row.close <= row.high
            and row.open > 0
            and row.high > 0
            and row.low > 0
            and row.close > 0
            and row.volume >= 0
            and row.quote_volume >= 0
            and row.trade_count >= 0
        )
    )
    gaps = 0
    for prev, cur in zip(candles, candles[1:]):
        if cur.ts - prev.ts != interval_ms:
            gaps += 1
    status = "PASS" if duplicate_count == 0 and bad_ohlc == 0 and gaps == 0 else "FAIL"
    return {
        "status": status,
        "bars": len(candles),
        "start_ts": iso(candles[0].ts),
        "end_ts": iso(candles[-1].ts),
        "duplicate_count": duplicate_count,
        "bad_ohlc_count": bad_ohlc,
        "gap_count": gaps,
    }


def sma(values: list[float], length: int) -> list[float]:
    out = [math.nan] * len(values)
    rolling = 0.0
    for index, value in enumerate(values):
        rolling += value
        if index >= length:
            rolling -= values[index - length]
        if index >= length - 1:
            out[index] = rolling / length
    return out


def atr(candles: list[Candle], length: int) -> list[float]:
    tr: list[float] = []
    for index, row in enumerate(candles):
        if index == 0:
            tr.append(row.high - row.low)
        else:
            prev = candles[index - 1].close
            tr.append(max(row.high - row.low, abs(row.high - prev), abs(row.low - prev)))
    return sma(tr, length)


def rsi_wilder(closes: list[float], length: int) -> list[float]:
    out = [math.nan] * len(closes)
    gains = [0.0] * len(closes)
    losses = [0.0] * len(closes)
    for index in range(1, len(closes)):
        delta = closes[index] - closes[index - 1]
        gains[index] = max(delta, 0.0)
        losses[index] = max(-delta, 0.0)
    if len(closes) <= length:
        return out
    avg_gain = sum(gains[1 : length + 1]) / length
    avg_loss = sum(losses[1 : length + 1]) / length
    out[length] = rsi_value(avg_gain, avg_loss)
    for index in range(length + 1, len(closes)):
        avg_gain = (avg_gain * (length - 1) + gains[index]) / length
        avg_loss = (avg_loss * (length - 1) + losses[index]) / length
        out[index] = rsi_value(avg_gain, avg_loss)
    return out


def rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def fill_price(price: float, side: int, action: str, slippage: float) -> float:
    if action == "entry":
        return price * (1.0 + slippage) if side > 0 else price * (1.0 - slippage)
    return price * (1.0 - slippage) if side > 0 else price * (1.0 + slippage)


def fee(notional: float) -> float:
    return abs(notional) * FEE_RATE


def funding_pnl(position: Position, funding_rate: float, mark_price: float) -> float:
    notional = abs(position.quantity * mark_price)
    # Positive funding is paid by longs and received by shorts.
    return -position.side * notional * funding_rate


def mark_equity(equity_cash: float, position: Position | None, mark_price: float) -> float:
    if position is None:
        return equity_cash
    if position.side > 0:
        unrealized = position.quantity * (mark_price - position.entry_fill)
    else:
        unrealized = position.quantity * (position.entry_fill - mark_price)
    return equity_cash + unrealized


def max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst * 100.0


def profit_factor(trades: list[dict[str, Any]]) -> float | None:
    gains = sum(max(float(row["net_pnl"]), 0.0) for row in trades)
    losses = -sum(min(float(row["net_pnl"]), 0.0) for row in trades)
    if losses == 0.0:
        return None if gains == 0.0 else math.inf
    return gains / losses


def annualized_return(equity_multiple: float, days: int) -> float | None:
    if days <= 0 or equity_multiple <= 0:
        return None
    return (equity_multiple ** (365.0 / days) - 1.0) * 100.0


def daily_returns(equity_by_day: list[float]) -> list[float]:
    out: list[float] = []
    for prev, cur in zip(equity_by_day, equity_by_day[1:]):
        if prev > 0:
            out.append(cur / prev - 1.0)
    return out


def sharpe(equity_by_day: list[float]) -> float | None:
    returns = daily_returns(equity_by_day)
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((row - mean) ** 2 for row in returns) / (len(returns) - 1)
    if variance <= 0:
        return None
    return mean / math.sqrt(variance) * math.sqrt(365.0)


def hourly_index(candles: list[Candle]) -> dict[int, Candle]:
    return {row.ts: row for row in candles}


def closed_hourly_between(hours: dict[int, Candle], start_ms: int, end_ms: int) -> list[Candle]:
    return [hours[ts] for ts in range(start_ms, end_ms, MS_PER_HOUR) if ts in hours]


def nearest_hour_close(hours: dict[int, Candle], ts: int, fallback: float) -> float:
    bucket = ts - (ts % MS_PER_HOUR)
    row = hours.get(bucket)
    return row.close if row is not None else fallback


def run_backtest(
    symbol: str,
    daily: list[Candle],
    hourly: list[Candle],
    funding: list[dict[str, Any]],
    *,
    ma_length: int = 7,
    slippage: float = BASE_SLIPPAGE,
) -> dict[str, Any]:
    closes = [row.close for row in daily]
    ma = sma(closes, ma_length)
    atr7 = atr(daily, 7)
    rsi6 = rsi_wilder(closes, 6)
    hours = hourly_index(hourly)
    funding_sorted = sorted(funding, key=lambda row: row["funding_time"])
    funding_index = 0
    equity_cash = 1.0
    equity_curve = [1.0]
    daily_equity = [1.0]
    position: Position | None = None
    scheduled: ScheduledOrder | None = None
    long_cooldown = 0
    short_cooldown = 0
    trades: list[dict[str, Any]] = []
    cost_total = 0.0
    funding_total = 0.0
    exposure_hours = 0
    total_hours = 0
    pehc_shadow: dict[str, Any] | None = None
    pehc_counts = {"shadow_start": 0, "handoff_accept": 0, "shadow_expire": 0}

    def close_position(ts: int, price_ref: float, reason: str) -> None:
        nonlocal equity_cash, position, cost_total, funding_total, long_cooldown, short_cooldown, pehc_shadow
        if position is None:
            return
        exit_fill = fill_price(price_ref, position.side, "exit", slippage)
        exit_notional = abs(position.quantity * exit_fill)
        exit_fee = fee(exit_notional)
        cost_total += exit_fee
        if position.side > 0:
            gross = position.quantity * (exit_fill - position.entry_fill)
            long_cooldown = 2
            pehc_shadow = {
                "origin_ts": ts,
                "expiry_left": 8,
                "highest_close": position.highest_close,
                "stop_price": position.highest_close - 1.5 * position.entry_atr if math.isfinite(position.entry_atr) else math.nan,
            }
            pehc_counts["shadow_start"] += 1
        else:
            gross = position.quantity * (position.entry_fill - exit_fill)
            short_cooldown = 3
        net_pnl = gross - exit_fee
        equity_cash += gross - exit_fee
        trades.append(
            {
                "side": "long" if position.side > 0 else "short",
                "entry_ts": iso(position.entry_ts),
                "entry_price": position.entry_price_ref,
                "exit_ts": iso(ts),
                "exit_price": price_ref,
                "bars_held": position.bars_held,
                "exit_reason": reason,
                "net_pnl": net_pnl,
                "net_return_pct": net_pnl / position.equity_basis * 100.0 if position.equity_basis else math.nan,
            }
        )
        position = None

    def open_position(ts: int, price_ref: float, side: int, entry_atr: float) -> None:
        nonlocal equity_cash, position, cost_total
        entry_fill = fill_price(price_ref, side, "entry", slippage)
        target_notional = equity_cash * TARGET_LEVERAGE
        quantity = target_notional / entry_fill
        entry_fee = fee(target_notional)
        cost_total += entry_fee
        equity_cash -= entry_fee
        position = Position(
            side=side,
            entry_ts=ts,
            entry_price_ref=price_ref,
            entry_fill=entry_fill,
            quantity=quantity,
            equity_basis=equity_cash + entry_fee,
            entry_atr=entry_atr,
            highest_close=price_ref,
            lowest_close=price_ref,
            max_favorable_price=price_ref,
        )

    for index, day in enumerate(daily):
        day_start = day.ts
        next_day = daily[index + 1].ts if index + 1 < len(daily) else day.ts + MS_PER_DAY

        if scheduled is not None:
            if scheduled.action == "exit" and position is not None:
                close_position(day_start, day.open, scheduled.reason)
            elif scheduled.action == "entry" and position is None and math.isfinite(atr7[index - 1] if index > 0 else math.nan):
                open_position(day_start, day.open, scheduled.side, atr7[index - 1])
            scheduled = None

        day_hours = closed_hourly_between(hours, day_start, next_day)
        total_hours += len(day_hours)
        for hour in day_hours:
            while funding_index < len(funding_sorted) and funding_sorted[funding_index]["funding_time"] <= hour.ts:
                event = funding_sorted[funding_index]
                if position is not None and event["funding_time"] >= position.entry_ts:
                    fpnl = funding_pnl(position, event["funding_rate"], hour.close)
                    equity_cash += fpnl
                    funding_total += fpnl
                funding_index += 1
            if position is not None:
                exposure_hours += 1
                prev_atr = atr7[index - 1] if index > 0 else math.nan
                if position.side > 0 and math.isfinite(prev_atr):
                    stop = position.highest_close - 1.5 * prev_atr
                    if hour.low <= stop:
                        close_position(hour.ts, stop, "protective_stop")
                elif position.side < 0:
                    stop_candidates: list[float] = []
                    if math.isfinite(position.entry_atr):
                        stop_candidates.append(position.entry_price_ref + 1.5 * position.entry_atr)
                    if math.isfinite(prev_atr):
                        stop_candidates.append(position.lowest_close + 4.0 * prev_atr)
                    if stop_candidates and hour.high >= min(stop_candidates):
                        close_position(hour.ts, min(stop_candidates), "protective_stop")
            if position is None and pehc_shadow is not None and index > 0 and math.isfinite(ma[index - 1]) and math.isfinite(atr7[index - 1]):
                stop = pehc_shadow.get("stop_price", math.nan)
                if math.isfinite(stop) and hour.low <= stop and hour.close < ma[index - 1]:
                    scheduled = ScheduledOrder("entry", -1, "pehc_handoff")
                    pehc_shadow = None
                    pehc_counts["handoff_accept"] += 1
            equity_curve.append(mark_equity(equity_cash, position, hour.close))

        if position is not None:
            position.highest_close = max(position.highest_close, day.close)
            position.lowest_close = min(position.lowest_close, day.close)
            position.bars_held += 1
            if position.side > 0:
                position.max_favorable_price = max(position.max_favorable_price, day.close)
            else:
                position.max_favorable_price = min(position.max_favorable_price, day.close)

        if pehc_shadow is not None:
            pehc_shadow["expiry_left"] -= 1
            pehc_shadow["highest_close"] = max(float(pehc_shadow["highest_close"]), day.close)
            if math.isfinite(atr7[index]):
                pehc_shadow["stop_price"] = float(pehc_shadow["highest_close"]) - 1.5 * atr7[index]
            if pehc_shadow["expiry_left"] <= 0:
                pehc_shadow = None
                pehc_counts["shadow_expire"] += 1

        if position is not None and scheduled is None:
            if position.side > 0:
                exit_reason = ""
                if math.isfinite(ma[index]) and math.isfinite(atr7[index]) and day.close < ma[index] - 0.75 * atr7[index]:
                    exit_reason = f"ma{ma_length}_hysteresis_exit"
                mfe = position.max_favorable_price - position.entry_price_ref
                if (
                    not exit_reason
                    and math.isfinite(atr7[index])
                    and mfe >= 0.5 * atr7[index]
                    and mfe > 0.0
                ):
                    giveback = (position.max_favorable_price - day.close) / mfe
                    roundtrip = (day.close - position.entry_price_ref) / position.entry_price_ref
                    if giveback >= 0.10 and roundtrip >= 0.0028:
                        position.oapp_long_run += 1
                    else:
                        position.oapp_long_run = 0
                    if position.oapp_long_run >= 2:
                        exit_reason = "long_mfe_fraction_trail_exit"
                if not exit_reason and position.bars_held >= 90:
                    exit_reason = "max_hold"
                if exit_reason:
                    scheduled = ScheduledOrder("exit", 0, exit_reason)
            else:
                exit_reason = ""
                if index > 0 and math.isfinite(ma[index]) and math.isfinite(ma[index - 1]) and ma[index] - ma[index - 1] >= 0:
                    exit_reason = f"ma{ma_length}_slope_exit"
                if (
                    not exit_reason
                    and math.isfinite(ma[index])
                    and math.isfinite(atr7[index])
                    and day.close > ma[index] + 0.75 * atr7[index]
                ):
                    exit_reason = f"ma{ma_length}_hysteresis_exit"
                if not exit_reason and math.isfinite(rsi6[index]):
                    roundtrip = (position.entry_price_ref - day.close) / position.entry_price_ref
                    if rsi6[index] <= 20.0 and roundtrip >= 0.0028:
                        position.short_rsi_run += 1
                    else:
                        position.short_rsi_run = 0
                    if position.short_rsi_run >= 2:
                        exit_reason = "short_rsi_take_profit"
                if not exit_reason and position.bars_held >= 20:
                    exit_reason = "max_hold"
                if exit_reason:
                    scheduled = ScheduledOrder("exit", 0, exit_reason)

        if position is None and scheduled is None and index > 7:
            if long_cooldown > 0:
                long_cooldown -= 1
            if short_cooldown > 0:
                short_cooldown -= 1
            prev_same_long = daily[index - 1].close <= ma[index - 1] if math.isfinite(ma[index - 1]) else False
            long_reclaim = prev_same_long and day.close > ma[index]
            long_slope = ma[index] - ma[index - 1] >= 0.02 * atr7[index] if math.isfinite(ma[index]) and math.isfinite(ma[index - 1]) and math.isfinite(atr7[index]) else False
            prev_same_short = daily[index - 1].close >= ma[index - 1] if math.isfinite(ma[index - 1]) else False
            short_reclaim = prev_same_short and day.close < ma[index] - 0.10 * atr7[index] if math.isfinite(ma[index]) and math.isfinite(atr7[index]) else False
            short_slope = ma[index] - ma[index - 2] <= -0.02 * atr7[index] if index >= 2 and math.isfinite(ma[index]) and math.isfinite(ma[index - 2]) and math.isfinite(atr7[index]) else False
            if long_cooldown == 0 and long_reclaim and long_slope:
                scheduled = ScheduledOrder("entry", 1, "native_reclaim")
            elif short_cooldown == 0 and short_reclaim and short_slope:
                scheduled = ScheduledOrder("entry", -1, "native_reclaim")

        daily_equity.append(mark_equity(equity_cash, position, day.close))
        equity_curve.append(daily_equity[-1])

    if position is not None:
        close_position(daily[-1].ts, daily[-1].close, "terminal_close")
        equity_curve.append(equity_cash)
        daily_equity.append(equity_cash)

    days = max(1, int(round((daily[-1].ts - daily[0].ts) / MS_PER_DAY)) + 1)
    wins = sum(1 for row in trades if row["net_pnl"] > 0.0)
    long_trades = sum(1 for row in trades if row["side"] == "long")
    metrics = {
        "net_return_pct": (equity_cash - 1.0) * 100.0,
        "equity_multiple": equity_cash,
        "chronological_1h_mdd_pct": max_drawdown(equity_curve),
        "daily_mdd_pct": max_drawdown(daily_equity),
        "annualized_return_pct": annualized_return(equity_cash, days),
        "closed_trades": len(trades),
        "long_trades": long_trades,
        "short_trades": len(trades) - long_trades,
        "win_rate": wins / len(trades) if trades else None,
        "profit_factor": profit_factor(trades),
        "sharpe": sharpe(daily_equity),
        "cost_pct_initial": cost_total * 100.0,
        "funding_pct_initial": funding_total * 100.0,
        "exposure_pct": exposure_hours / total_hours * 100.0 if total_hours else 0.0,
        "pehc_shadow_start": pehc_counts["shadow_start"],
        "pehc_handoff_accept": pehc_counts["handoff_accept"],
    }
    return {
        "symbol": symbol,
        "status": "PASS",
        "metrics": metrics,
        "trades": trades,
        "trade_sample": trades[:3] + ([{"ellipsis": len(trades) - 6}] if len(trades) > 6 else []) + trades[-3:],
    }


def rank_symbol(symbol: str, ranking_days: int, market_type: str) -> dict[str, Any]:
    candles = fetch_klines(symbol, "1d", limit=ranking_days + 2)
    ranked = candles[-ranking_days:]
    return {
        "symbol": symbol,
        "market_type": market_type,
        "ranking_bars": len(ranked),
        "start_ts": iso(ranked[0].ts) if ranked else None,
        "end_ts": iso(ranked[-1].ts) if ranked else None,
        "quote_volume_30d": sum(row.quote_volume for row in ranked),
        "quality": quality(ranked, MS_PER_DAY),
    }


def fetch_symbol_dataset(symbol: str, market_type: str, history_days: int, end_ms: int) -> dict[str, Any]:
    start_ms = end_ms - (history_days + 5) * MS_PER_DAY
    daily = fetch_klines(symbol, "1d", start_ms=start_ms, end_ms=end_ms, limit=1500)
    if not daily:
        raise RuntimeError(f"{symbol} daily empty")
    retained_days = min(history_days, len(daily))
    left_ts = daily[-retained_days].ts
    hour_start = daily[0].ts
    hour_end = daily[-1].ts + MS_PER_DAY
    hourly = fetch_klines(symbol, "1h", start_ms=hour_start, end_ms=hour_end, limit=1500)
    funding = fetch_funding(symbol, hour_start, hour_end)
    return {
        "symbol": symbol,
        "market_type": market_type,
        "daily": daily[-retained_days:],
        "available_daily_bars": len(daily),
        "retained_daily_bars": retained_days,
        "short_history": retained_days < history_days,
        "hourly": [row for row in hourly if row.ts >= left_ts],
        "funding": [row for row in funding if row["funding_time"] >= left_ts],
    }


def sanitize(value: Any) -> Any:
    if isinstance(value, Candle):
        return {
            "ts": iso(value.ts),
            "open": value.open,
            "high": value.high,
            "low": value.low,
            "close": value.close,
            "volume": value.volume,
            "quote_volume": value.quote_volume,
            "trade_count": value.trade_count,
            "close_time": iso(value.close_time),
        }
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_locked(payload: dict[str, Any], output_path: Path, *, force: bool = False) -> str:
    sidecar = Path(f"{output_path}.sha256")
    if not force and (output_path.exists() or sidecar.exists()):
        raise RuntimeError(f"locked artifact exists: {output_path.name}")
    encoded = json.dumps(sanitize(payload), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    digest = hashlib.sha256(encoded).hexdigest()
    output_path.write_bytes(encoded)
    sidecar.write_text(f"{digest}  {output_path.name}\n", encoding="utf-8")
    return digest


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    passed = [row for row in results if row.get("status") == "PASS"]
    positives = [row for row in passed if row["metrics"]["net_return_pct"] > 0]
    tradeful = [row for row in passed if row["metrics"]["closed_trades"] > 0]
    by_return = sorted(
        passed,
        key=lambda row: row["metrics"]["net_return_pct"],
        reverse=True,
    )
    median_return = None
    if passed:
        vals = sorted(row["metrics"]["net_return_pct"] for row in passed)
        median_return = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2
    return {
        "symbols_passed": len(passed),
        "symbols_positive": len(positives),
        "symbols_with_trades": len(tradeful),
        "median_return_pct": median_return,
        "best": by_return[0]["symbol"] if by_return else None,
        "best_return_pct": by_return[0]["metrics"]["net_return_pct"] if by_return else None,
        "worst": by_return[-1]["symbol"] if by_return else None,
        "worst_return_pct": by_return[-1]["metrics"]["net_return_pct"] if by_return else None,
        "verdict": (
            "TRANSFER_FAIL"
            if len(positives) < max(1, len(passed) // 2) or (median_return is not None and median_return <= 0)
            else "TRANSFER_MIXED_POSITIVE"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--ranking-days", type=int, default=30)
    parser.add_argument("--history-days", type=int, default=520)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--quote-assets", default="USDT,USDC", help="Comma-separated quote assets to include, e.g. USDT or USDT,USDC")
    parser.add_argument("--ma-length", type=int, default=7, help="Moving average length for the reclaim/slope/hysteresis rules")
    parser.add_argument("--output-path", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not args.run:
        raise SystemExit("use --run")

    quote_assets = {item.strip().upper() for item in args.quote_assets.split(",") if item.strip()}
    invalid_quotes = quote_assets - U_MARGIN_QUOTES
    if invalid_quotes:
        raise ValueError(f"unsupported quote assets: {sorted(invalid_quotes)}")

    symbol_universe = u_margin_futures_contracts(quote_assets)
    universe_counts: dict[str, int] = {}
    for _, market_type in symbol_universe:
        universe_counts[market_type] = universe_counts.get(market_type, 0) + 1
    ranking_rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(rank_symbol, symbol, args.ranking_days, market_type): (symbol, market_type)
            for symbol, market_type in symbol_universe
        }
        for future in as_completed(futures):
            symbol, market_type = futures[future]
            try:
                row = future.result()
                if row["quality"]["status"] == "PASS" and row["ranking_bars"] >= args.ranking_days:
                    ranking_rows.append(row)
            except Exception as exc:
                ranking_rows.append(
                    {"symbol": symbol, "market_type": market_type, "status": "RANKING_FETCH_FAIL", "error": str(exc)}
                )

    ranked = sorted(
        [row for row in ranking_rows if "quote_volume_30d" in row],
        key=lambda row: row["quote_volume_30d"],
        reverse=True,
    )
    top = ranked[: args.limit]
    if len(top) < args.limit:
        raise RuntimeError(f"only ranked {len(top)} symbols")

    end_ms = utc_ms_now()
    datasets = []
    for row in top:
        symbol = row["symbol"]
        market_type = row["market_type"]
        print(f"[fetch] {symbol} ({market_type})")
        dataset = fetch_symbol_dataset(symbol, market_type, args.history_days, end_ms)
        datasets.append(dataset)

    results: list[dict[str, Any]] = []
    for dataset in datasets:
        symbol = dataset["symbol"]
        print(f"[backtest] {symbol}")
        daily = dataset["daily"]
        hourly = dataset["hourly"]
        dq = quality(daily, MS_PER_DAY)
        hq = quality(hourly, MS_PER_HOUR)
        if dq["status"] != "PASS" or hq["status"] != "PASS":
            results.append(
                {
                    "symbol": symbol,
                    "market_type": dataset["market_type"],
                    "status": "DATA_QUALITY_FAIL",
                    "daily_quality": dq,
                    "hourly_quality": hq,
                }
            )
            continue
        try:
            base = run_backtest(symbol, daily, hourly, dataset["funding"], ma_length=args.ma_length, slippage=BASE_SLIPPAGE)
            base["market_type"] = dataset["market_type"]
            stress = run_backtest(symbol, daily, hourly, dataset["funding"], ma_length=args.ma_length, slippage=STRESS_SLIPPAGE)
            base["daily_quality"] = dq
            base["hourly_quality"] = hq
            base["funding_events"] = len(dataset["funding"])
            base["stress_8bps"] = stress["metrics"]
            base["daily_tail"] = daily[-5:]
            results.append(base)
        except Exception as exc:
            results.append(
                {
                    "symbol": symbol,
                    "market_type": dataset["market_type"],
                    "status": "BACKTEST_FAIL",
                    "error": str(exc),
                    "daily_quality": dq,
                    "hourly_quality": hq,
                }
            )

    payload = {
        "schema": "hype-1d-ma7-abt-v7-1-binance-u-margin-transfer-v3",
        "status": "COMPLETED_DIAGNOSTIC",
        "run_date": RUN_DATE,
        "generated_utc": datetime.now(tz=timezone.utc).isoformat(),
        "purpose": f"Cross-asset diagnostic of HYPE-1D-MA7-ABT-V7.1 rules with SMA{args.ma_length} substituted into the MA rules on top {args.limit} Binance U-margined futures by recent {args.ranking_days} closed daily quote volume.",
        "promotion": False,
        "live_ready": False,
        "clean_oos_claim": False,
        "data_source": {
            "exchange": "binance",
            "market_type": "u_margin_futures_all",
            "source": "binance_fapi_public_api",
            "ranking_days": args.ranking_days,
            "history_days_requested": args.history_days,
            "quote_assets": sorted(quote_assets),
            "selection": "sum daily kline quote_volume over the latest closed UTC daily bars; includes TRADING futures with contractType PERPETUAL or TRADIFI_PERPETUAL and requested quote assets",
            "universe_count": len(symbol_universe),
            "universe_counts": universe_counts,
        },
        "cost_model": {
            "fee_per_fill": FEE_RATE,
            "base_slippage_per_fill": BASE_SLIPPAGE,
            "stress_slippage_per_fill": STRESS_SLIPPAGE,
            "funding": "Binance fundingRate events; approximate mark uses hourly close",
        },
        "v7_1_parameters": {
            "ma_length": args.ma_length,
            "atr_length": 7,
            "rsi_length": 6,
            "long": {
                "entry_mode": "reclaim",
                "slope_lookback": 1,
                "slope_min_atr": 0.02,
                "entry_buffer_atr": 0.0,
                "exit_buffer_atr": 0.75,
                "trail_atr": 1.5,
                "max_hold_days": 90,
                "cooldown_days": 2,
            },
            "short": {
                "entry_mode": "reclaim",
                "slope_lookback": 2,
                "slope_min_atr": 0.02,
                "entry_buffer_atr": 0.10,
                "exit_buffer_atr": 0.75,
                "slope_exit_lookback": 1,
                "hard_stop_atr": 1.5,
                "trail_atr": 4.0,
                "max_hold_days": 20,
                "cooldown_days": 3,
            },
            "oapp": {
                "long_activation_atr": 0.5,
                "long_giveback": 0.10,
                "long_confirm_days": 2,
                "short_rsi_threshold": 20.0,
                "short_rsi_days": 2,
                "roundtrip_guard": 0.0028,
            },
            "pehc": {
                "enabled": True,
                "entry_enabled": True,
                "expiry_days": 8,
                "slope_threshold": None,
                "chase_cap_atr": "INF",
            },
        },
        "ranking_top": top,
        "ranking_top15": top[:15],
        "ranking_tradifi": [row for row in ranked if row.get("market_type") == "tradifi_perp"],
        "ranking_usdc": [row for row in ranked if row.get("market_type") == "perp_usdc"],
        "ranking_failures": [row for row in ranking_rows if row.get("status") == "RANKING_FETCH_FAIL"][:20],
        "results": results,
        "summary": summarize_results(results),
        "notes": [
            "This is a transfer diagnostic, not a parameter search and not a promotion review.",
            "The script downloads fresh Binance public API data at run time and performs in-script quality gates instead of promoting data into the repository data lake.",
            "Funding PnL uses Binance funding timestamps with hourly close as the mark approximation.",
            "The implementation follows the V7.1 external reproduction spec; exact legacy HYPE dynamic-code engine is not reused for non-HYPE symbols.",
        ],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    digest = write_locked(payload, args.output_path, force=args.force)
    print(json.dumps({"status": payload["status"], "summary": payload["summary"], "artifact": str(args.output_path), "sha256": digest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
