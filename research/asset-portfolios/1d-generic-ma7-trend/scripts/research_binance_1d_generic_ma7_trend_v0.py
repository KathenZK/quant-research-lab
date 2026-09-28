"""Run the frozen BIN-1D-GMA7T-v0 current-market-cap transfer audit.

The script deliberately separates three layers:
1. a runtime CoinGecko market-cap snapshot and Binance USD-M eligibility gate;
2. one frozen, symmetric generic MA7 strategy applied unchanged to every asset;
3. a separately reported inverse-volatility/equal-risk portfolio.

It also reuses the repository's V7.1 public-API reproduction engine for the
HYPE control.  No result from this script is used to select v0 parameters.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import pickle
import statistics
import sys
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
FAMILY_DIR = SCRIPT_DIR.parent
ROOT = SCRIPT_DIR.parents[3]
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
CACHE_DIR = ARTIFACT_DIR / ".runtime-cache"
CONFIG_PATH = FAMILY_DIR / "configs/binance-1d-generic-ma7-trend-v0.json"
V71_SCRIPT = (
    ROOT
    / "research/hype/1d-ma7-asymmetric-body-trend/scripts/"
    "audit_hype_1d_ma7_abt_v7_1_top15_binance_perp_transfer.py"
)

RUN_DATE = "2026-08-18"
PREFIX = f"binance_1d_gma7t_v0_{RUN_DATE}"
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"
MS_HOUR = 3_600_000
MS_DAY = 24 * MS_HOUR
RECENT_SLICES = {"1d": 1, "7d": 7, "1m": 30, "3m": 91, "6m": 182, "1y": 365}

# Explicit high-rank identities make the one-time snapshot reproducible.  The
# generic name/symbol rules below fail closed for future obvious wrappers/pegs.
EXCLUDED_ECONOMIC_EXPOSURES: dict[str, str] = {
    "tether": "fiat_stablecoin",
    "usd-coin": "fiat_stablecoin",
    "usds": "fiat_stablecoin",
    "dai": "fiat_stablecoin",
    "usd1-wlfi": "fiat_stablecoin",
    "ethena-usde": "yield_bearing_usd_peg",
    "global-dollar": "fiat_stablecoin",
    "hashnote-usyc": "tokenized_treasury_usd_peg",
    "paypal-usd": "fiat_stablecoin",
    "blackrock-usd-institutional-digital-liquidity-fund": "tokenized_fund",
    "figure-heloc": "tokenized_credit_nav_exposure",
    "tether-gold": "gold_pegged_asset",
    "pax-gold": "gold_pegged_asset",
    "ondo-us-dollar-yield": "yield_bearing_usd_peg",
    "ripple-usd": "fiat_stablecoin",
    "wrapped-bitcoin": "wrapped_duplicate_bitcoin",
    "coinbase-wrapped-btc": "wrapped_duplicate_bitcoin",
    "wrapped-steth": "wrapped_or_staked_duplicate_ethereum",
    "staked-ether": "staked_duplicate_ethereum",
}

BINANCE_SYMBOL_OVERRIDES = {"shiba-inu": "1000SHIBUSDT"}


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    ma_length: int = 7
    atr_length: int = 7
    slope_lookback: int = 1
    slope_min_atr: float = 0.02
    entry_buffer_atr: float = 0.0
    exit_buffer_atr: float = 0.75
    hard_stop_atr: float = 1.5
    trail_stop_atr: float = 1.5
    fee_rate: float = 0.001
    slippage: float = 0.0004
    funding_enabled: bool = True


@dataclass(slots=True)
class Position:
    side: int
    entry_ts: int
    entry_ref: float
    entry_fill: float
    quantity: float
    equity_basis: float
    entry_atr: float
    entry_fee: float
    trail_anchor: float
    active_atr: float
    funding_pnl: float = 0.0
    bars_held: int = 0


@dataclass(frozen=True, slots=True)
class ScheduledOrder:
    action: str
    side: int
    reason: str


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def json_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_v71_module() -> Any:
    name = "quant_strategy_lab_hype_v71_transfer_engine"
    spec = importlib.util.spec_from_file_location(name, V71_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load V7.1 engine: {V71_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def request_json(url: str, params: dict[str, Any], retries: int = 5) -> tuple[Any, bytes]:
    query = urlencode(params)
    full = f"{url}?{query}"
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = Request(full, headers={"User-Agent": "quant-research-lab-research/1.0"})
            with urlopen(req, timeout=45) as response:
                raw = response.read()
            return json.loads(raw.decode("utf-8")), raw
        except Exception as exc:  # pragma: no cover - live network path
            last = exc
            if attempt + 1 == retries:
                break
    raise RuntimeError(f"request failed: {full}: {last}")


def exclusion_reason(row: dict[str, Any]) -> str | None:
    coin_id = str(row.get("id", "")).lower()
    if coin_id in EXCLUDED_ECONOMIC_EXPOSURES:
        return EXCLUDED_ECONOMIC_EXPOSURES[coin_id]
    name = str(row.get("name", "")).lower()
    symbol = str(row.get("symbol", "")).lower()
    obvious = (
        "wrapped",
        "bridged",
        "liquid staked",
        "tokenized treasury",
        "institutional digital liquidity fund",
    )
    if any(token in name for token in obvious):
        return "name_rule_wrapped_or_asset_backed"
    if symbol in {"usdt", "usdc", "dai", "usde", "usds", "usdg", "pyusd", "usyc"}:
        return "symbol_rule_usd_peg"
    return None


def market_cap_top30_nonpegged(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    seen_exposure: set[str] = set()
    for row in sorted(rows, key=lambda item: int(item.get("market_cap_rank") or 10**9)):
        reason = exclusion_reason(row)
        coin_id = str(row["id"])
        exposure_key = {
            "the-open-network": "ton_gram",
            "bitcoin": "bitcoin",
            "ethereum": "ethereum",
        }.get(coin_id, coin_id)
        if reason is None and exposure_key in seen_exposure:
            reason = "duplicate_economic_exposure"
        decision = {
            "market_cap_rank": row.get("market_cap_rank"),
            "id": coin_id,
            "symbol": str(row.get("symbol", "")).upper(),
            "name": row.get("name"),
            "market_cap_usd": row.get("market_cap"),
            "last_updated": row.get("last_updated"),
            "classification": "excluded" if reason else "eligible_nonpegged_crypto",
            "reason": reason,
        }
        decisions.append(decision)
        if reason is None:
            seen_exposure.add(exposure_key)
            selected.append(decision)
            if len(selected) == 30:
                break
    if len(selected) < 30:
        raise RuntimeError(f"market-cap response yielded only {len(selected)} eligible exposures")
    return selected, decisions


def fetch_market_cap_snapshot() -> dict[str, Any]:
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 100,
        "page": 1,
        "sparkline": "false",
        "locale": "en",
    }
    fetched = utc_now()
    rows, raw = request_json(COINGECKO_URL, params)
    selected, decisions = market_cap_top30_nonpegged(rows)
    return {
        "source": "CoinGecko coins/markets",
        "url": f"{COINGECKO_URL}?{urlencode(params)}",
        "fetched_utc": fetched.isoformat(),
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "rows": rows,
        "decisions_through_top30_nonpegged": decisions,
        "top30_nonpegged": selected,
    }


def binance_contract_map(v71: Any) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    payload = v71.request_json("/fapi/v1/exchangeInfo")
    contracts: dict[str, dict[str, Any]] = {}
    for row in payload.get("symbols", []):
        if (
            row.get("quoteAsset") == "USDT"
            and row.get("contractType") == "PERPETUAL"
            and row.get("status") == "TRADING"
        ):
            contracts[str(row["symbol"])] = row
    return contracts, payload


def candidate_binance_symbol(coin: dict[str, Any]) -> str:
    return BINANCE_SYMBOL_OVERRIDES.get(str(coin["id"]), f"{str(coin['symbol']).upper()}USDT")


def candle_hash(candles: Iterable[Any]) -> str:
    rows = [
        [row.ts, row.open, row.high, row.low, row.close, row.volume, row.quote_volume, row.trade_count, row.close_time]
        for row in candles
    ]
    return json_sha256(rows)


def funding_hash(rows: list[dict[str, Any]]) -> str:
    return json_sha256([[row["funding_time"], row["funding_rate"]] for row in rows])


def fetch_dataset(v71: Any, symbol: str, history_days: int, end_ms: int) -> dict[str, Any]:
    dataset = v71.fetch_symbol_dataset(symbol, "perp_usdt", history_days, end_ms)
    daily = dataset["daily"]
    hourly = dataset["hourly"]
    funding = dataset["funding"]
    dq = v71.quality(daily, MS_DAY)
    hq = v71.quality(hourly, MS_HOUR)
    close_time_fail = sum(row.close_time >= end_ms for row in daily) + sum(row.close_time >= end_ms for row in hourly)
    status = "PASS"
    reasons: list[str] = []
    if dq["status"] != "PASS":
        status = "FAIL"
        reasons.append("daily_quality")
    if hq["status"] != "PASS":
        status = "FAIL"
        reasons.append("hourly_quality")
    if close_time_fail:
        status = "FAIL"
        reasons.append("not_closed_by_snapshot")
    return {
        **dataset,
        "quality_status": status,
        "quality_reasons": reasons,
        "daily_quality": dq,
        "hourly_quality": hq,
        "provider_close_time_failures": close_time_fail,
        "daily_sha256": candle_hash(daily),
        "hourly_sha256": candle_hash(hourly),
        "funding_sha256": funding_hash(funding),
        "funding_events": len(funding),
    }


def dataset_cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{RUN_DATE}_{symbol}_{PREFIX}.pickle"


def load_cached_dataset(symbol: str, history_days: int, end_ms: int) -> dict[str, Any] | None:
    path = dataset_cache_path(symbol)
    if not path.exists():
        return None
    with path.open("rb") as handle:
        payload = pickle.load(handle)  # noqa: S301 - task-owned, ignored runtime cache
    if payload.get("history_days") != history_days:
        return None
    if abs(int(payload.get("end_ms", 0)) - end_ms) > 6 * MS_HOUR:
        return None
    return payload["dataset"]


def save_cached_dataset(symbol: str, history_days: int, end_ms: int, dataset: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with dataset_cache_path(symbol).open("wb") as handle:
        pickle.dump(
            {"history_days": history_days, "end_ms": end_ms, "dataset": dataset},
            handle,
            protocol=pickle.HIGHEST_PROTOCOL,
        )


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


def atr(candles: list[Any], length: int) -> list[float]:
    tr: list[float] = []
    for index, row in enumerate(candles):
        if index == 0:
            tr.append(row.high - row.low)
        else:
            previous = candles[index - 1].close
            tr.append(max(row.high - row.low, abs(row.high - previous), abs(row.low - previous)))
    return sma(tr, length)


def fill_price(reference: float, side: int, action: str, slippage: float) -> float:
    if action == "entry":
        return reference * (1.0 + slippage) if side > 0 else reference * (1.0 - slippage)
    return reference * (1.0 - slippage) if side > 0 else reference * (1.0 + slippage)


def mark_equity(cash: float, position: Position | None, mark: float) -> float:
    if position is None:
        return cash
    return cash + position.side * position.quantity * (mark - position.entry_fill)


def max_drawdown(values: Iterable[float]) -> float:
    peak = -math.inf
    worst = 0.0
    for value in values:
        if not math.isfinite(value):
            continue
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst


def profit_factor(trades: list[dict[str, Any]]) -> float | None:
    gains = sum(max(float(row["net_pnl"]), 0.0) for row in trades)
    losses = -sum(min(float(row["net_pnl"]), 0.0) for row in trades)
    if losses == 0:
        return math.inf if gains > 0 else None
    return gains / losses


def series_metrics(equity: pd.Series, trades: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    clean = equity.dropna().astype(float)
    if clean.empty:
        return {}
    returns = clean.pct_change(fill_method=None).dropna()
    span_days = max(1.0, (clean.index[-1] - clean.index[0]).total_seconds() / 86_400.0)
    total = clean.iloc[-1] / clean.iloc[0] - 1.0 if clean.iloc[0] > 0 else math.nan
    cagr = (clean.iloc[-1] / clean.iloc[0]) ** (365.0 / span_days) - 1.0 if clean.iloc[0] > 0 and clean.iloc[-1] > 0 else None
    std = float(returns.std(ddof=1)) if len(returns) > 1 else math.nan
    downside = returns[returns < 0]
    downside_std = float(downside.std(ddof=1)) if len(downside) > 1 else math.nan
    mean = float(returns.mean()) if len(returns) else math.nan
    sharpe = mean / std * math.sqrt(365.0) if math.isfinite(std) and std > 0 else None
    sortino = mean / downside_std * math.sqrt(365.0) if math.isfinite(downside_std) and downside_std > 0 else None
    mdd = max_drawdown(clean.to_numpy())
    calmar = cagr / abs(mdd) if cagr is not None and mdd < 0 else None
    out: dict[str, Any] = {
        "total_return_pct": total * 100.0,
        "cagr_pct": cagr * 100.0 if cagr is not None else None,
        "sharpe": sharpe,
        "sortino": sortino,
        "mdd_pct": mdd * 100.0,
        "calmar": calmar,
        "days": int(round(span_days)) + 1,
    }
    if trades is not None:
        wins = [row for row in trades if float(row["net_pnl"]) > 0]
        out.update(
            {
                "profit_factor": profit_factor(trades),
                "closed_trades": len(trades),
                "win_rate": len(wins) / len(trades) if trades else None,
                "avg_hold_days": statistics.mean(float(row["hold_days"]) for row in trades) if trades else None,
            }
        )
    return out


def side_breakdown(trades: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for label in ("long", "short"):
        subset = [row for row in trades if row["side"] == label]
        pnl = sum(float(row["net_pnl"]) for row in subset)
        output[label] = {
            "trades": len(subset),
            "wins": sum(float(row["net_pnl"]) > 0 for row in subset),
            "win_rate": sum(float(row["net_pnl"]) > 0 for row in subset) / len(subset) if subset else None,
            "profit_factor": profit_factor(subset),
            "pnl_contribution_pct_initial": pnl * 100.0,
            "avg_hold_days": statistics.mean(float(row["hold_days"]) for row in subset) if subset else None,
        }
    return output


def run_generic(
    symbol: str,
    daily: list[Any],
    hourly: list[Any],
    funding: list[dict[str, Any]],
    config: StrategyConfig,
) -> dict[str, Any]:
    if len(daily) < max(config.ma_length, config.atr_length) + 3:
        raise ValueError("insufficient daily warmup")
    closes = [row.close for row in daily]
    ma = sma(closes, config.ma_length)
    atr_values = atr(daily, config.atr_length)
    hours = {row.ts: row for row in hourly}
    funding_rows = sorted(funding, key=lambda row: row["funding_time"])
    funding_index = 0
    cash = 1.0
    position: Position | None = None
    scheduled: ScheduledOrder | None = None
    trades: list[dict[str, Any]] = []
    chronological_equity: list[float] = [1.0]
    daily_rows: list[dict[str, Any]] = []
    cost_total = 0.0
    funding_total = 0.0
    exposure_hours = 0
    total_hours = 0

    def open_position(ts: int, reference: float, side: int, entry_atr: float) -> None:
        nonlocal cash, position, cost_total
        fill = fill_price(reference, side, "entry", config.slippage)
        equity_basis = cash
        quantity = equity_basis / fill
        entry_fee = abs(quantity * fill) * config.fee_rate
        cash -= entry_fee
        cost_total += entry_fee
        position = Position(
            side=side,
            entry_ts=ts,
            entry_ref=reference,
            entry_fill=fill,
            quantity=quantity,
            equity_basis=equity_basis,
            entry_atr=entry_atr,
            entry_fee=entry_fee,
            trail_anchor=reference,
            active_atr=entry_atr,
        )
        chronological_equity.append(mark_equity(cash, position, reference))

    def close_position(ts: int, reference: float, reason: str) -> None:
        nonlocal cash, position, cost_total
        if position is None:
            return
        fill = fill_price(reference, position.side, "exit", config.slippage)
        exit_fee = abs(position.quantity * fill) * config.fee_rate
        gross_pnl = position.side * position.quantity * (fill - position.entry_fill)
        cash += gross_pnl - exit_fee
        cost_total += exit_fee
        net_pnl = gross_pnl + position.funding_pnl - position.entry_fee - exit_fee
        trades.append(
            {
                "trade_id": f"{symbol}-{len(trades) + 1:04d}",
                "side": "long" if position.side > 0 else "short",
                "entry_ts": iso(position.entry_ts),
                "entry_ts_ms": position.entry_ts,
                "entry_reference": position.entry_ref,
                "entry_fill": position.entry_fill,
                "exit_ts": iso(ts),
                "exit_ts_ms": ts,
                "exit_reference": reference,
                "exit_fill": fill,
                "exit_reason": reason,
                "hold_days": (ts - position.entry_ts) / MS_DAY,
                "bars_held": position.bars_held,
                "gross_pnl_after_slippage": gross_pnl,
                "funding_pnl": position.funding_pnl,
                "fees": position.entry_fee + exit_fee,
                "net_pnl": net_pnl,
                "net_return_pct_on_entry_equity": net_pnl / position.equity_basis * 100.0,
            }
        )
        position = None
        chronological_equity.append(cash)

    for index, day in enumerate(daily):
        if scheduled is not None:
            if scheduled.action == "exit" and position is not None:
                close_position(day.ts, day.open, scheduled.reason)
            elif scheduled.action == "entry" and position is None and index > 0 and math.isfinite(atr_values[index - 1]):
                open_position(day.ts, day.open, scheduled.side, atr_values[index - 1])
            scheduled = None

        side_at_day_start = position.side if position is not None else 0
        next_day_ts = daily[index + 1].ts if index + 1 < len(daily) else day.ts + MS_DAY
        day_hours = [hours[ts] for ts in range(day.ts, next_day_ts, MS_HOUR) if ts in hours]
        total_hours += len(day_hours)
        for hour in day_hours:
            while funding_index < len(funding_rows) and funding_rows[funding_index]["funding_time"] <= hour.ts:
                event = funding_rows[funding_index]
                if config.funding_enabled and position is not None and event["funding_time"] >= position.entry_ts:
                    value = -position.side * abs(position.quantity * hour.close) * float(event["funding_rate"])
                    cash += value
                    position.funding_pnl += value
                    funding_total += value
                funding_index += 1
            if position is not None:
                exposure_hours += 1
                if position.side > 0:
                    hard = position.entry_ref - config.hard_stop_atr * position.entry_atr
                    trail = position.trail_anchor - config.trail_stop_atr * position.active_atr
                    stop = max(hard, trail)
                    if hour.open <= stop:
                        close_position(hour.ts, hour.open, "gap_protective_stop")
                    elif hour.low <= stop:
                        close_position(hour.ts, stop, "protective_stop")
                else:
                    hard = position.entry_ref + config.hard_stop_atr * position.entry_atr
                    trail = position.trail_anchor + config.trail_stop_atr * position.active_atr
                    stop = min(hard, trail)
                    if hour.open >= stop:
                        close_position(hour.ts, hour.open, "gap_protective_stop")
                    elif hour.high >= stop:
                        close_position(hour.ts, stop, "protective_stop")
            chronological_equity.append(mark_equity(cash, position, hour.close))

        if position is not None:
            position.bars_held += 1
            if position.side > 0:
                position.trail_anchor = max(position.trail_anchor, day.close)
            else:
                position.trail_anchor = min(position.trail_anchor, day.close)
            if math.isfinite(atr_values[index]):
                position.active_atr = atr_values[index]

        if position is not None:
            if position.side > 0 and math.isfinite(ma[index]) and math.isfinite(atr_values[index]):
                if day.close < ma[index] - config.exit_buffer_atr * atr_values[index]:
                    scheduled = ScheduledOrder("exit", 0, "ma_atr_hysteresis_exit")
            elif position.side < 0 and math.isfinite(ma[index]) and math.isfinite(atr_values[index]):
                if day.close > ma[index] + config.exit_buffer_atr * atr_values[index]:
                    scheduled = ScheduledOrder("exit", 0, "ma_atr_hysteresis_exit")
        elif index >= max(config.ma_length, config.atr_length, config.slope_lookback) + 1:
            previous = index - 1
            slope_base = index - config.slope_lookback
            finite = all(
                math.isfinite(value)
                for value in (ma[index], ma[previous], ma[slope_base], atr_values[index])
            )
            if finite and atr_values[index] > 0:
                slope = (ma[index] - ma[slope_base]) / atr_values[index]
                long_reclaim = (
                    daily[previous].close <= ma[previous]
                    and day.close > ma[index] + config.entry_buffer_atr * atr_values[index]
                    and slope >= config.slope_min_atr
                )
                short_reclaim = (
                    daily[previous].close >= ma[previous]
                    and day.close < ma[index] - config.entry_buffer_atr * atr_values[index]
                    and slope <= -config.slope_min_atr
                )
                if long_reclaim:
                    scheduled = ScheduledOrder("entry", 1, "symmetric_reclaim")
                elif short_reclaim:
                    scheduled = ScheduledOrder("entry", -1, "symmetric_reclaim")

        daily_rows.append(
            {
                "ts": pd.Timestamp(day.ts, unit="ms", tz="UTC"),
                "open": day.open,
                "high": day.high,
                "low": day.low,
                "close": day.close,
                "ma": ma[index] if math.isfinite(ma[index]) else np.nan,
                "atr": atr_values[index] if math.isfinite(atr_values[index]) else np.nan,
                "equity": mark_equity(cash, position, day.close),
                "side_start": side_at_day_start,
                "side_close": position.side if position is not None else 0,
            }
        )

    if position is not None:
        close_position(daily[-1].ts + MS_DAY - 1, daily[-1].close, "terminal_close")
        daily_rows[-1]["equity"] = cash
        daily_rows[-1]["side_close"] = 0

    frame = pd.DataFrame(daily_rows).set_index("ts")
    metrics = series_metrics(frame["equity"], trades)
    metrics.update(
        {
            "chronological_1h_mdd_pct": max_drawdown(chronological_equity) * 100.0,
            "cost_pct_initial": cost_total * 100.0,
            "funding_pct_initial": funding_total * 100.0,
            "exposure_pct": exposure_hours / total_hours * 100.0 if total_hours else 0.0,
        }
    )
    return {
        "symbol": symbol,
        "metrics": metrics,
        "side_breakdown": side_breakdown(trades),
        "trades": trades,
        "daily": frame,
        "config": config,
    }


def period_rows(symbol: str, result: dict[str, Any], frequency: str, label: str) -> list[dict[str, Any]]:
    equity = result["daily"]["equity"]
    rows: list[dict[str, Any]] = []
    grouped = equity.groupby(equity.index.tz_localize(None).to_period(frequency))
    for period, values in grouped:
        if len(values) < 2:
            continue
        metrics = series_metrics(values)
        start = values.index[0]
        end = values.index[-1]
        trades = [
            row
            for row in result["trades"]
            if start <= pd.Timestamp(row["exit_ts"]) <= end + pd.Timedelta(days=1)
        ]
        rows.append(
            {
                "symbol": symbol,
                "slice_kind": label,
                "period": str(period),
                "return_pct": metrics.get("total_return_pct"),
                "sharpe": metrics.get("sharpe"),
                "mdd_pct": metrics.get("mdd_pct"),
                "trades_exited": len(trades),
            }
        )
    return rows


def recent_rows(symbol: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    equity = result["daily"]["equity"]
    rows = []
    for label, days in RECENT_SLICES.items():
        values = equity.iloc[-min(len(equity), days + 1) :]
        metrics = series_metrics(values)
        rows.append(
            {
                "symbol": symbol,
                "slice_kind": "recent",
                "period": label,
                "return_pct": metrics.get("total_return_pct"),
                "sharpe": metrics.get("sharpe"),
                "mdd_pct": metrics.get("mdd_pct"),
                "trades_exited": sum(
                    pd.Timestamp(row["exit_ts"]) >= values.index[0] for row in result["trades"]
                ),
            }
        )
    return rows


def build_portfolio(results: dict[str, dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    assets = sorted(results)
    equity = pd.concat({sym: results[sym]["daily"]["equity"] for sym in assets}, axis=1)
    gross_equity = pd.concat({sym: results[sym]["gross_daily"]["equity"] for sym in assets}, axis=1)
    side_start = pd.concat({sym: results[sym]["daily"]["side_start"] for sym in assets}, axis=1)
    returns = equity.pct_change(fill_method=None)
    gross_returns = gross_equity.pct_change(fill_method=None)
    halflife = int(config["asset_vol_ewm_halflife_days"])
    sigma = returns.ewm(halflife=halflife, min_periods=halflife).std().shift(1) * math.sqrt(365.0)
    inverse = (1.0 / sigma).where((sigma > 0) & np.isfinite(sigma))
    weights = inverse.div(inverse.sum(axis=1), axis=0).fillna(0.0)
    active_count = (weights > 0).sum(axis=1)
    weights = weights.where(active_count >= int(config["minimum_active_assets"]), 0.0)
    raw_return = (weights * returns.fillna(0.0)).sum(axis=1)
    raw_gross_return = (weights * gross_returns.fillna(0.0)).sum(axis=1)
    p_half = int(config["portfolio_vol_ewm_halflife_days"])
    p_sigma = raw_return.ewm(halflife=p_half, min_periods=p_half).std().shift(1) * math.sqrt(365.0)
    scale = (float(config["target_annual_vol"]) / p_sigma).where(p_sigma > 0)
    scale = scale.clip(upper=float(config["gross_leverage_cap"])).fillna(0.0)
    targets = weights.mul(scale, axis=0)
    sleeve_return = raw_return * scale
    sleeve_gross_return = raw_gross_return * scale

    # Internal strategy entry/exit fees are already present in each net sleeve.
    # Charge only same-side notional drift caused by risk-weight/scale changes.
    previous_targets = targets.shift(1).fillna(0.0)
    previous_side = side_start.shift(1).fillna(0.0)
    same_open_side = (side_start == previous_side) & (side_start != 0)
    drift_turnover = (targets - previous_targets).abs().where(same_open_side, 0.0).sum(axis=1)
    rebalance_cost_rate = 0.001 + 0.0004
    rebalance_cost = drift_turnover * rebalance_cost_rate
    adjusted_return = sleeve_return - rebalance_cost
    net_equity = (1.0 + adjusted_return.fillna(0.0)).cumprod()
    upper_equity = (1.0 + sleeve_return.fillna(0.0)).cumprod()
    gross_curve = (1.0 + sleeve_gross_return.fillna(0.0)).cumprod()
    frame = pd.DataFrame(
        {
            "gross_return": sleeve_gross_return,
            "net_sleeve_return_before_rebalance": sleeve_return,
            "rebalance_turnover": drift_turnover,
            "rebalance_cost": rebalance_cost,
            "net_return": adjusted_return,
            "gross_equity": gross_curve,
            "net_equity_before_rebalance": upper_equity,
            "net_equity": net_equity,
            "n_active": active_count,
            "portfolio_scale": scale,
        }
    )
    return {
        "daily": frame,
        "metrics": series_metrics(frame["net_equity"]),
        "gross_metrics": series_metrics(frame["gross_equity"]),
        "upper_bound_metrics": series_metrics(frame["net_equity_before_rebalance"]),
        "weights": targets,
    }


def registered_window_hype_comparison(dataset: dict[str, Any], base: StrategyConfig) -> dict[str, Any]:
    start_ms = int(pd.Timestamp("2025-05-31", tz="UTC").timestamp() * 1000)
    end_exclusive_ms = int(pd.Timestamp("2026-08-06", tz="UTC").timestamp() * 1000)
    daily = [row for row in dataset["daily"] if start_ms <= row.ts < end_exclusive_ms]
    hourly = [row for row in dataset["hourly"] if start_ms <= row.ts < end_exclusive_ms]
    funding = [row for row in dataset["funding"] if start_ms <= int(row["funding_time"]) < end_exclusive_ms]
    if len(daily) != 432:
        raise RuntimeError(f"registered HYPE comparison expected 432 daily bars, got {len(daily)}")
    net = run_generic("HYPEUSDT", daily, hourly, funding, base)
    gross = run_generic(
        "HYPEUSDT",
        daily,
        hourly,
        [],
        replace(base, fee_rate=0.0, slippage=0.0, funding_enabled=False),
    )
    stress = run_generic("HYPEUSDT", daily, hourly, funding, replace(base, slippage=0.0008))
    anchor_return = 711.04
    generic_return = float(net["metrics"]["total_return_pct"])
    gap = anchor_return - generic_return
    return {
        "window": {
            "start": "2025-05-31T00:00:00+00:00",
            "end_exclusive": "2026-08-06T00:00:00+00:00",
            "daily_bars": len(daily),
            "hourly_bars": len(hourly),
        },
        "exact_registered_v71_anchor": {
            "net_return_pct": anchor_return,
            "chronological_1h_mdd_pct": -18.40,
            "closed_trades": 20,
            "profit_factor": 17.51,
            "source_role": "authoritative frozen registered result from the V7 core ledger",
        },
        "generic_v0_same_registered_window": net["metrics"],
        "generic_v0_gross_same_registered_window": gross["metrics"],
        "generic_v0_stress_8bps_same_registered_window": stress["metrics"],
        "registered_return_gap_pp": gap,
        "generic_return_retention_ratio": generic_return / anchor_return,
        "gap_share_of_registered_return": gap / anchor_return,
        "attribution_caveat": (
            "The return gap is associated with replacing the complete V7.1 rule set by frozen generic v0. "
            "It is not causal module-by-module attribution and includes all removed asymmetry and event arms."
        ),
    }


def run_v71_hype_control(v71: Any, dataset: dict[str, Any]) -> dict[str, Any]:
    original_fee = v71.FEE_RATE
    try:
        v71.FEE_RATE = 0.001
        net = v71.run_backtest(
            "HYPEUSDT",
            dataset["daily"],
            dataset["hourly"],
            dataset["funding"],
            ma_length=7,
            slippage=0.0004,
        )
        stress = v71.run_backtest(
            "HYPEUSDT",
            dataset["daily"],
            dataset["hourly"],
            dataset["funding"],
            ma_length=7,
            slippage=0.0008,
        )
        v71.FEE_RATE = 0.0
        gross = v71.run_backtest(
            "HYPEUSDT", dataset["daily"], dataset["hourly"], [], ma_length=7, slippage=0.0
        )
    finally:
        v71.FEE_RATE = original_fee
    return {
        "engine": "repository V7.1 portable public-API reproduction engine reused without rule changes",
        "evidence_role": "same-current-window portability diagnostic; the exact registered V7.1 anchor remains authoritative",
        "window": {
            "start": iso(dataset["daily"][0].ts),
            "end": iso(dataset["daily"][-1].ts),
            "daily_bars": len(dataset["daily"]),
        },
        "gross": gross["metrics"],
        "net": net["metrics"],
        "stress_8bps": stress["metrics"],
        "trades": net["trades"],
        "registered_anchor_2025_05_31_to_2026_08_06": {
            "net_return_pct": 711.04,
            "chronological_1h_mdd_pct": -18.40,
            "closed_trades": 20,
            "profit_factor": 17.51,
            "evidence_role": "historical registered anchor; not forced onto current common window",
        },
    }


def aggregate_cross_section(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    metrics = [row["metrics"] for row in results.values()]
    sharpes = [float(row["sharpe"]) for row in metrics if row.get("sharpe") is not None]
    pfs = [float(row["profit_factor"]) for row in metrics if row.get("profit_factor") is not None]
    cagr = [float(row["cagr_pct"]) for row in metrics if row.get("cagr_pct") is not None]
    returns = [float(row["total_return_pct"]) for row in metrics]
    return {
        "assets": len(metrics),
        "mean_sharpe": statistics.mean(sharpes) if sharpes else None,
        "median_sharpe": statistics.median(sharpes) if sharpes else None,
        "sharpe_gt_0_count": sum(value > 0 for value in sharpes),
        "sharpe_gt_0_ratio": sum(value > 0 for value in sharpes) / len(sharpes) if sharpes else None,
        "mean_cagr_pct": statistics.mean(cagr) if cagr else None,
        "median_cagr_pct": statistics.median(cagr) if cagr else None,
        "mean_total_return_pct": statistics.mean(returns),
        "median_total_return_pct": statistics.median(returns),
        "pf_gt_1_count": sum(value > 1 for value in pfs),
        "pf_gt_1_ratio": sum(value > 1 for value in pfs) / len(pfs) if pfs else None,
        "total_trades": sum(int(row["closed_trades"]) for row in metrics),
        "long_positive_pnl_assets": sum(row["side_breakdown"]["long"]["pnl_contribution_pct_initial"] > 0 for row in results.values()),
        "short_positive_pnl_assets": sum(row["side_breakdown"]["short"]["pnl_contribution_pct_initial"] > 0 for row in results.values()),
    }


def cross_cost_summary(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    gross_returns = [float(row["gross_metrics"]["total_return_pct"]) for row in results.values()]
    net_returns = [float(row["metrics"]["total_return_pct"]) for row in results.values()]
    stress_returns = [float(row["stress_8bps_metrics"]["total_return_pct"]) for row in results.values()]
    return {
        "gross_positive_assets": sum(value > 0 for value in gross_returns),
        "net_positive_assets": sum(value > 0 for value in net_returns),
        "stress_8bps_positive_assets": sum(value > 0 for value in stress_returns),
        "gross_median_total_return_pct": statistics.median(gross_returns),
        "net_median_total_return_pct": statistics.median(net_returns),
        "stress_8bps_median_total_return_pct": statistics.median(stress_returns),
        "median_gross_to_net_drag_pp": statistics.median(
            gross - net for gross, net in zip(gross_returns, net_returns, strict=True)
        ),
        "mean_cost_pct_initial": statistics.mean(float(row["metrics"]["cost_pct_initial"]) for row in results.values()),
        "mean_funding_pct_initial": statistics.mean(float(row["metrics"]["funding_pct_initial"]) for row in results.values()),
    }


def direction_summary(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for side in ("long", "short"):
        trades = [trade for result in results.values() for trade in result["trades"] if trade["side"] == side]
        asset_pnl = [float(result["side_breakdown"][side]["pnl_contribution_pct_initial"]) for result in results.values()]
        output[side] = {
            "trades": len(trades),
            "wins": sum(float(row["net_pnl"]) > 0 for row in trades),
            "win_rate": sum(float(row["net_pnl"]) > 0 for row in trades) / len(trades) if trades else None,
            "profit_factor": profit_factor(trades),
            "positive_pnl_assets": sum(value > 0 for value in asset_pnl),
            "negative_pnl_assets": sum(value < 0 for value in asset_pnl),
            "median_asset_pnl_contribution_pct_initial": statistics.median(asset_pnl),
            "aggregate_pnl_contribution_pct_initial": sum(asset_pnl),
        }
    return output


def universe_period_summary(period_rows_input: list[dict[str, Any]], portfolio: dict[str, Any]) -> list[dict[str, Any]]:
    frame = pd.DataFrame(period_rows_input)
    rows: list[dict[str, Any]] = []
    for (slice_kind, period), group in frame.groupby(["slice_kind", "period"], sort=True):
        returns = group["return_pct"].dropna().astype(float)
        sharpes = group["sharpe"].dropna().astype(float)
        rows.append(
            {
                "scope": "universe_cross_section",
                "slice_kind": slice_kind,
                "period": period,
                "symbols": len(group),
                "mean_return_pct": returns.mean() if len(returns) else None,
                "median_return_pct": returns.median() if len(returns) else None,
                "positive_return_ratio": (returns > 0).mean() if len(returns) else None,
                "mean_sharpe": sharpes.mean() if len(sharpes) else None,
                "median_sharpe": sharpes.median() if len(sharpes) else None,
                "trades_exited_total": int(group["trades_exited"].sum()),
            }
        )

    p_equity = portfolio["daily"]["net_equity"]
    for frequency, label in (("Y", "year"), ("Q", "quarter")):
        grouped = p_equity.groupby(p_equity.index.tz_localize(None).to_period(frequency))
        for period, values in grouped:
            if len(values) < 2:
                continue
            metrics = series_metrics(values)
            rows.append(
                {
                    "scope": "equal_risk_portfolio",
                    "slice_kind": label,
                    "period": str(period),
                    "symbols": None,
                    "mean_return_pct": metrics.get("total_return_pct"),
                    "median_return_pct": None,
                    "positive_return_ratio": None,
                    "mean_sharpe": metrics.get("sharpe"),
                    "median_sharpe": None,
                    "trades_exited_total": None,
                }
            )
    for label, days in RECENT_SLICES.items():
        values = p_equity.iloc[-min(len(p_equity), days + 1) :]
        metrics = series_metrics(values)
        rows.append(
            {
                "scope": "equal_risk_portfolio",
                "slice_kind": "recent",
                "period": label,
                "symbols": None,
                "mean_return_pct": metrics.get("total_return_pct"),
                "median_return_pct": None,
                "positive_return_ratio": None,
                "mean_sharpe": metrics.get("sharpe"),
                "median_sharpe": None,
                "trades_exited_total": None,
            }
        )
    return rows


def perturbation_configs(base: StrategyConfig) -> list[tuple[str, str, float | int, StrategyConfig]]:
    rows: list[tuple[str, str, float | int, StrategyConfig]] = [("baseline", "baseline", 0, base)]
    variations: list[tuple[str, list[float | int], str]] = [
        ("ma_length", [6, 8], "ma_length"),
        ("atr_length", [6, 8], "atr_length"),
        ("slope_min_atr", [0.016, 0.024], "slope_min_atr"),
        ("exit_buffer_atr", [0.60, 0.90], "exit_buffer_atr"),
    ]
    for label, values, field in variations:
        for value in values:
            rows.append((f"{label}_{value}", label, value, replace(base, **{field: value})))
    for value in (1.2, 1.8):
        rows.append(
            (
                f"protective_stop_atr_{value}",
                "protective_stop_atr",
                value,
                replace(base, hard_stop_atr=value, trail_stop_atr=value),
            )
        )
    return rows


def stability_label(rows: list[dict[str, Any]]) -> str:
    baseline = next(row for row in rows if row["variant"] == "baseline")
    neighbors = [row for row in rows if row["variant"] != "baseline"]
    base_sign = 1 if float(baseline["median_sharpe"] or 0) > 0 else -1
    sign_same = sum((1 if float(row["median_sharpe"] or 0) > 0 else -1) == base_sign for row in neighbors)
    ratio_floor = float(baseline["sharpe_gt_0_ratio"] or 0) - 0.15
    breadth_ok = sum(float(row["sharpe_gt_0_ratio"] or 0) >= ratio_floor for row in neighbors)
    if sign_same >= 8 and breadth_ok >= 8:
        stop_row = next(row for row in rows if row["variant"] == "protective_stop_atr_1.2")
        if float(stop_row["portfolio_sharpe"] or 0) < 0.25:
            return "PLATEAU_LIKE_WITH_PROTECTIVE_STOP_SENSITIVITY"
        return "PLATEAU_LIKE"
    return "SHARP_OR_UNSTABLE"


def safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, StrategyConfig):
        return {name: getattr(value, name) for name in value.__dataclass_fields__}
    return value


def write_json(path: Path, payload: Any, *, force: bool) -> str:
    if path.exists() and not force:
        raise RuntimeError(f"artifact exists: {path}")
    encoded = json.dumps(safe(payload), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    path.write_bytes(encoded)
    digest = hashlib.sha256(encoded).hexdigest()
    Path(f"{path}.sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def write_csv(path: Path, rows: list[dict[str, Any]], *, force: bool) -> None:
    if path.exists() and not force:
        raise RuntimeError(f"artifact exists: {path}")
    pd.DataFrame([safe(row) for row in rows]).to_csv(path, index=False)


def html_payload(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    assets: dict[str, Any] = {}
    for symbol, result in sorted(results.items()):
        frame = result["daily"]
        trades = result["trades"]
        ids = [row["trade_id"] for row in trades]
        if len(ids) != len(set(ids)) or len(trades) != int(result["metrics"]["closed_trades"]):
            raise RuntimeError(f"trade-path validation failed for {symbol}")
        for trade in trades:
            if int(trade["entry_ts_ms"]) > int(trade["exit_ts_ms"]):
                raise RuntimeError(f"trade timestamps inverted for {trade['trade_id']}")
        assets[symbol] = {
            "metrics": safe(result["metrics"]),
            "dates": [value.strftime("%Y-%m-%d") for value in frame.index],
            "open": frame["open"].tolist(),
            "high": frame["high"].tolist(),
            "low": frame["low"].tolist(),
            "close": frame["close"].tolist(),
            "ma": [None if pd.isna(value) else float(value) for value in frame["ma"]],
            "equity": frame["equity"].tolist(),
            "trades": safe(trades),
        }
    return {"assets": assets}


def render_html(path: Path, results: dict[str, dict[str, Any]], summary: dict[str, Any], *, force: bool) -> None:
    if path.exists() and not force:
        raise RuntimeError(f"artifact exists: {path}")
    payload = html_payload(results)
    data = json.dumps(safe(payload), ensure_ascii=False, separators=(",", ":"))
    summary_json = json.dumps(safe(summary), ensure_ascii=False)
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BIN-1D-GMA7T-v0 Frozen Cross-Asset Audit</title>
<style>
:root{{--bg:#0b0f14;--panel:#121923;--ink:#e6edf3;--muted:#93a4b7;--grid:#263244;--long:#2dd4bf;--short:#fb7185;--ma:#fbbf24}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px ui-monospace,SFMono-Regular,Menlo,monospace}}
header{{padding:28px 32px;border-bottom:1px solid var(--grid)}}h1{{margin:0 0 8px;font-size:26px}}.muted{{color:var(--muted)}}
.wrap{{padding:24px 32px;display:grid;gap:18px}}.cards{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}
.card,.panel{{background:var(--panel);border:1px solid var(--grid);padding:16px}}.card b{{display:block;font-size:22px;margin-top:6px}}
.controls{{display:flex;gap:16px;align-items:center;flex-wrap:wrap}}select,input{{background:#0b111a;color:var(--ink);border:1px solid var(--grid);padding:8px}}
canvas{{width:100%;height:auto;background:#0d131c;border:1px solid var(--grid)}}#price,#equity{{touch-action:none;cursor:grab;user-select:none}}#price.dragging,#equity.dragging{{cursor:grabbing}}.chart-help{{margin:8px 0 12px;color:var(--muted);font-size:12px}}.chart-help b{{color:var(--ink);font-weight:600}}table{{width:100%;border-collapse:collapse;font-size:12px}}
th,td{{padding:7px;border-bottom:1px solid var(--grid);text-align:right}}th:first-child,td:first-child{{text-align:left}}tr[data-trade]{{cursor:pointer}}
@media(max-width:900px){{.cards{{grid-template-columns:1fr 1fr}}header,.wrap{{padding-left:14px;padding-right:14px}}}}
</style></head><body>
<header><h1>BIN-1D-GMA7T-v0 · Frozen Cross-Asset Audit</h1><div class="muted">Current-top30 retrospective · same parameters · net includes fee, slippage and funding</div></header>
<main class="wrap"><section class="cards" id="cards"></section>
<section class="panel"><h2>横截面 Sharpe 分布</h2><canvas id="cross" width="1200" height="440"></canvas></section>
<section class="panel"><div class="controls"><label>Asset <select id="asset"></select></label><label>Window <input id="window" type="range" min="60" max="730" value="220"></label><span id="assetMetrics" class="muted"></span></div>
<h2>完整交易路径（蜡烛 / SMA7 / 入出场连线）</h2><div class="chart-help"><b>拖动 K 线或净值图</b>平移 · <b>滚轮</b>缩放 · <b>双击</b>回到最新 · <span id="viewRange"></span></div><canvas id="price" width="1200" height="520" tabindex="0" aria-label="可拖动的 K 线交易路径图"></canvas><h2>Net equity</h2><canvas id="equity" width="1200" height="220" tabindex="0" aria-label="与 K 线同步的可拖动净值图"></canvas></section>
<section class="panel"><h2>Trades</h2><div style="max-height:420px;overflow:auto"><table><thead><tr><th>ID</th><th>Side</th><th>Entry</th><th>Exit</th><th>Reason</th><th>Net PnL</th></tr></thead><tbody id="trades"></tbody></table></div></section>
</main><script>
const DATA={data}; const SUMMARY={summary_json}; const symbols=Object.keys(DATA.assets);
const fmt=(x,d=2)=>x==null?'NA':Number(x).toFixed(d); const cards=document.getElementById('cards');
[['Assets',SUMMARY.assets],['Median Sharpe',fmt(SUMMARY.median_sharpe)],['Sharpe > 0',fmt(100*SUMMARY.sharpe_gt_0_ratio,1)+'%'],['PF > 1',fmt(100*SUMMARY.pf_gt_1_ratio,1)+'%']].forEach(([a,b])=>cards.insertAdjacentHTML('beforeend',`<div class="card"><span class="muted">${{a}}</span><b>${{b}}</b></div>`));
const sel=document.getElementById('asset'); symbols.forEach(s=>sel.add(new Option(s,s)));
function cross(){{const c=document.getElementById('cross'),x=c.getContext('2d');x.clearRect(0,0,c.width,c.height);const rows=symbols.map(s=>[s,DATA.assets[s].metrics.sharpe||0]).sort((a,b)=>b[1]-a[1]);const vals=rows.map(r=>r[1]);const lo=Math.min(-.1,...vals),hi=Math.max(.1,...vals),zero=70+(0-lo)/(hi-lo)*(c.width-110);x.strokeStyle='#526173';x.beginPath();x.moveTo(zero,18);x.lineTo(zero,c.height-20);x.stroke();rows.forEach((r,i)=>{{const y=18+i*(c.height-36)/rows.length,h=(c.height-36)/rows.length-2,end=70+(r[1]-lo)/(hi-lo)*(c.width-110);x.fillStyle=r[1]>=0?'#2dd4bf':'#fb7185';x.fillRect(Math.min(zero,end),y,Math.abs(end-zero),h);x.fillStyle='#dbe7f3';x.font='11px monospace';x.fillText(r[0],4,y+h-2);x.fillText(fmt(r[1]),Math.max(74,Math.min(c.width-42,end+4)),y+h-2);}})}}
function dayIndex(a,ts){{const d=new Date(ts).toISOString().slice(0,10);let best=0;for(let i=0;i<a.dates.length;i++)if(a.dates[i]<=d)best=i;return best}}
const clamp=(value,low,high)=>Math.max(low,Math.min(high,value));let viewStart=null,lastViewport=null;
function draw(){{const s=sel.value,a=DATA.assets[s],n=a.dates.length,range=document.getElementById('window');range.max=n;const w=Math.min(n,Number(range.value)),maxStart=Math.max(0,n-w),start=Math.round(clamp(viewStart==null?maxStart:viewStart,0,maxStart)),end=Math.min(n,start+w);viewStart=start;lastViewport={{start,end,w,n}};document.getElementById('viewRange').textContent=`${{a.dates[start]}} → ${{a.dates[end-1]}}`;const m=a.metrics;document.getElementById('assetMetrics').textContent=`CAGR ${{fmt(m.cagr_pct)}}% · Sharpe ${{fmt(m.sharpe)}} · MDD ${{fmt(m.chronological_1h_mdd_pct)}}% · Trades ${{m.closed_trades}}`;
const c=document.getElementById('price'),x=c.getContext('2d');x.clearRect(0,0,c.width,c.height);const hi=Math.max(...a.high.slice(start,end)),lo=Math.min(...a.low.slice(start,end)),px=i=>45+(i-start+.5)*(c.width-70)/(end-start),py=v=>20+(hi-v)/(hi-lo)*(c.height-55);x.strokeStyle='#263244';for(let j=0;j<6;j++){{let y=20+j*(c.height-55)/5;x.beginPath();x.moveTo(40,y);x.lineTo(c.width-20,y);x.stroke()}}for(let i=start;i<end;i++){{const up=a.close[i]>=a.open[i];x.strokeStyle=x.fillStyle=up?'#2dd4bf':'#fb7185';x.beginPath();x.moveTo(px(i),py(a.low[i]));x.lineTo(px(i),py(a.high[i]));x.stroke();const y1=py(Math.max(a.open[i],a.close[i])),y2=py(Math.min(a.open[i],a.close[i]));x.fillRect(px(i)-2,y1,4,Math.max(1,y2-y1));}}x.strokeStyle='#fbbf24';x.beginPath();let begun=false;for(let i=start;i<end;i++){{if(a.ma[i]==null)continue;begun?x.lineTo(px(i),py(a.ma[i])):(x.moveTo(px(i),py(a.ma[i])),begun=true)}}x.stroke();a.trades.forEach(t=>{{const i=dayIndex(a,t.entry_ts),j=dayIndex(a,t.exit_ts);if(j<start||i>=end)return;x.strokeStyle=t.side==='long'?'#67e8f9':'#fda4af';x.lineWidth=1.5;x.beginPath();x.moveTo(px(Math.max(start,i)),py(t.entry_reference));x.lineTo(px(Math.min(end-1,j)),py(t.exit_reference));x.stroke();}});x.lineWidth=1;
const ec=document.getElementById('equity'),e=ec.getContext('2d');e.clearRect(0,0,ec.width,ec.height);const ev=a.equity.slice(start,end),eh=Math.max(...ev),el=Math.min(...ev);e.strokeStyle='#60a5fa';e.beginPath();ev.forEach((v,k)=>{{const xx=35+k*(ec.width-55)/Math.max(1,ev.length-1),yy=15+(eh-v)/Math.max(1e-9,eh-el)*(ec.height-35);k?e.lineTo(xx,yy):e.moveTo(xx,yy)}});e.stroke();
const tb=document.getElementById('trades');tb.innerHTML='';a.trades.forEach(t=>{{const tr=document.createElement('tr');tr.dataset.trade=t.trade_id;tr.innerHTML=`<td>${{t.trade_id}}</td><td>${{t.side}}</td><td>${{t.entry_ts.slice(0,10)}}</td><td>${{t.exit_ts.slice(0,10)}}</td><td>${{t.exit_reason}}</td><td>${{fmt(t.net_pnl,4)}}</td>`;tr.onclick=()=>{{viewStart=dayIndex(a,t.entry_ts)-Math.floor(Number(document.getElementById('window').value)/2);draw()}};tb.appendChild(tr)}})}}
function zoomAt(event){{event.preventDefault();if(!lastViewport)return;const range=document.getElementById('window'),rect=event.currentTarget.getBoundingClientRect(),anchorFraction=clamp((event.clientX-rect.left)/Math.max(1,rect.width),0,1),anchor=lastViewport.start+anchorFraction*lastViewport.w,next=clamp(Number(range.value)+(event.deltaY>0?30:-30),Number(range.min),Number(range.max));if(next===Number(range.value))return;range.value=next;viewStart=anchor-anchorFraction*next;draw()}}
const drag={{active:false,pointerId:null,startX:0,startView:0,canvas:null}};
function beginPan(event){{if(event.pointerType==='mouse'&&event.button!==0||!lastViewport)return;drag.active=true;drag.pointerId=event.pointerId;drag.startX=event.clientX;drag.startView=viewStart;drag.canvas=event.currentTarget;drag.canvas.setPointerCapture(event.pointerId);drag.canvas.classList.add('dragging')}}
function movePan(event){{if(!drag.active||event.pointerId!==drag.pointerId||!lastViewport)return;const rect=drag.canvas.getBoundingClientRect(),bars=-(event.clientX-drag.startX)/Math.max(1,rect.width-70)*lastViewport.w;viewStart=drag.startView+bars;draw()}}
function endPan(event){{if(!drag.active||event.pointerId!==drag.pointerId)return;if(drag.canvas.hasPointerCapture(event.pointerId))drag.canvas.releasePointerCapture(event.pointerId);drag.canvas.classList.remove('dragging');drag.active=false;drag.pointerId=null;drag.canvas=null}}
function keyPan(event){{if(!lastViewport)return;const step=Math.max(1,Math.round(lastViewport.w*.1));if(event.key==='ArrowLeft')viewStart-=step;else if(event.key==='ArrowRight')viewStart+=step;else if(event.key==='Home')viewStart=0;else if(event.key==='End')viewStart=null;else return;event.preventDefault();draw()}}
function attachTimelineInteractions(canvas){{canvas.addEventListener('wheel',zoomAt,{{passive:false}});canvas.addEventListener('pointerdown',beginPan);canvas.addEventListener('pointermove',movePan);canvas.addEventListener('pointerup',endPan);canvas.addEventListener('pointercancel',endPan);canvas.addEventListener('dblclick',()=>{{viewStart=null;draw()}});canvas.addEventListener('keydown',keyPan)}}
sel.onchange=()=>{{viewStart=null;draw()}};document.getElementById('window').oninput=()=>{{if(lastViewport)viewStart=lastViewport.start+lastViewport.w/2-Number(document.getElementById('window').value)/2;draw()}};attachTimelineInteractions(document.getElementById('price'));attachTimelineInteractions(document.getElementById('equity'));cross();sel.value=symbols.includes('HYPEUSDT')?'HYPEUSDT':symbols[0];draw();
</script></body></html>"""
    if "PLACEHOLDER" in html:
        raise RuntimeError("HTML placeholder remains")
    path.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-perturbations", action="store_true")
    args = parser.parse_args()
    if not args.run:
        raise SystemExit("use --run")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    config_payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config_hash = hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()
    v71 = load_v71_module()

    print("[universe] fetching CoinGecko market-cap snapshot", flush=True)
    snapshot = fetch_market_cap_snapshot()
    contracts, exchange_info = binance_contract_map(v71)
    top30 = snapshot["top30_nonpegged"]
    decisions: list[dict[str, Any]] = []
    fetch_candidates: list[tuple[dict[str, Any], str]] = []
    for coin in top30:
        symbol = candidate_binance_symbol(coin)
        listed = symbol in contracts
        decision = {**coin, "binance_symbol": symbol, "binance_trading_usdt_perpetual": listed}
        if not listed:
            decision.update({"final_status": "EXCLUDED", "final_reason": "no_trading_binance_usdt_perpetual"})
        else:
            fetch_candidates.append((coin, symbol))
        decisions.append(decision)

    end_dt = utc_now()
    end_ms = int(end_dt.timestamp() * 1000)
    history_days = int(config_payload["data"]["history_days_requested"])
    minimum_days = int(config_payload["data"]["minimum_closed_daily_bars"])
    print(f"[data] fetching {len(fetch_candidates)} Binance datasets through {end_dt.isoformat()}", flush=True)
    datasets: dict[str, dict[str, Any]] = {}
    failures: dict[str, str] = {}
    pending_candidates: list[tuple[dict[str, Any], str]] = []
    for coin, symbol in fetch_candidates:
        cached = load_cached_dataset(symbol, history_days, end_ms)
        if cached is None:
            pending_candidates.append((coin, symbol))
        else:
            datasets[symbol] = cached
            print(f"[data] {symbol}: reused task-owned runtime cache", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(fetch_dataset, v71, symbol, history_days, end_ms): symbol for _, symbol in pending_candidates}
        for future in as_completed(jobs):
            symbol = jobs[future]
            try:
                dataset = future.result()
                datasets[symbol] = dataset
                save_cached_dataset(symbol, history_days, end_ms, dataset)
                print(f"[data] {symbol}: {len(dataset['daily'])}d/{len(dataset['hourly'])}h {dataset['quality_status']}", flush=True)
            except Exception as exc:  # pragma: no cover - live network path
                failures[symbol] = str(exc)
                print(f"[data] {symbol}: FAIL {exc}", flush=True)

    eligible: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        symbol = decision["binance_symbol"]
        if symbol not in contracts:
            continue
        if symbol in failures:
            decision.update({"final_status": "EXCLUDED", "final_reason": f"data_fetch_failure: {failures[symbol]}"})
            continue
        dataset = datasets[symbol]
        decision.update(
            {
                "daily_bars": len(dataset["daily"]),
                "hourly_bars": len(dataset["hourly"]),
                "daily_start": iso(dataset["daily"][0].ts),
                "daily_end": iso(dataset["daily"][-1].ts),
                "data_quality": dataset["quality_status"],
            }
        )
        if len(dataset["daily"]) < minimum_days:
            decision.update({"final_status": "EXCLUDED", "final_reason": f"history_below_{minimum_days}_closed_daily_bars"})
        elif dataset["quality_status"] != "PASS":
            decision.update({"final_status": "EXCLUDED", "final_reason": "data_quality_fail"})
        else:
            decision.update({"final_status": "INCLUDED", "final_reason": "passes_frozen_rules"})
            eligible[symbol] = dataset
    if not eligible:
        raise RuntimeError("frozen universe is empty")

    base = StrategyConfig()
    results: dict[str, dict[str, Any]] = {}
    print(f"[backtest] frozen generic v0 on {len(eligible)} assets", flush=True)
    for symbol, dataset in sorted(eligible.items()):
        net = run_generic(symbol, dataset["daily"], dataset["hourly"], dataset["funding"], base)
        gross_config = replace(base, fee_rate=0.0, slippage=0.0, funding_enabled=False)
        gross = run_generic(symbol, dataset["daily"], dataset["hourly"], [], gross_config)
        stress = run_generic(symbol, dataset["daily"], dataset["hourly"], dataset["funding"], replace(base, slippage=0.0008))
        net["gross_metrics"] = gross["metrics"]
        net["stress_8bps_metrics"] = stress["metrics"]
        net["gross_daily"] = gross["daily"]
        results[symbol] = net
        print(f"[backtest] {symbol}: net={net['metrics']['total_return_pct']:.2f}% sharpe={net['metrics']['sharpe']}", flush=True)

    portfolio = build_portfolio(results, config_payload["portfolio"])
    loao_rows: list[dict[str, Any]] = []
    if len(results) > 2:
        for omitted in sorted(results):
            subset = {symbol: row for symbol, row in results.items() if symbol != omitted}
            metrics = build_portfolio(subset, config_payload["portfolio"])["metrics"]
            loao_rows.append({"omitted": omitted, **metrics})

    hype_control = run_v71_hype_control(v71, eligible["HYPEUSDT"]) if "HYPEUSDT" in eligible else None
    hype_comparison = registered_window_hype_comparison(eligible["HYPEUSDT"], base) if "HYPEUSDT" in eligible else None
    if hype_control is not None:
        generic_hype = results["HYPEUSDT"]["metrics"]
        hype_control["generic_v0_same_window"] = generic_hype
        hype_control["specialization_gap_net_return_pp"] = (
            float(hype_control["net"]["net_return_pct"]) - float(generic_hype["total_return_pct"])
        )
        if hype_comparison is not None:
            hype_comparison["portable_current_window_supplement"] = hype_control

    perturbation_rows: list[dict[str, Any]] = []
    if not args.skip_perturbations:
        print("[stability] running frozen OAT perturbations; no selection", flush=True)
        baseline_trade_counts = {symbol: len(row["trades"]) for symbol, row in results.items()}
        for variant, parameter, value, variant_config in perturbation_configs(base):
            if variant == "baseline":
                variant_results = results
            else:
                variant_results = {}
                for symbol, dataset in eligible.items():
                    row = run_generic(symbol, dataset["daily"], dataset["hourly"], dataset["funding"], variant_config)
                    gross = run_generic(
                        symbol,
                        dataset["daily"],
                        dataset["hourly"],
                        [],
                        replace(variant_config, fee_rate=0.0, slippage=0.0, funding_enabled=False),
                    )
                    row["gross_daily"] = gross["daily"]
                    variant_results[symbol] = row
            cross = aggregate_cross_section(variant_results)
            p_metrics = build_portfolio(variant_results, config_payload["portfolio"])["metrics"]
            perturbation_rows.append(
                {
                    "variant": variant,
                    "parameter": parameter,
                    "value": value,
                    **cross,
                    "portfolio_total_return_pct": p_metrics.get("total_return_pct"),
                    "portfolio_sharpe": p_metrics.get("sharpe"),
                    "portfolio_mdd_pct": p_metrics.get("mdd_pct"),
                    "assets_trade_count_changed": sum(
                        len(variant_results[symbol]["trades"]) != baseline_trade_counts[symbol]
                        for symbol in results
                    ),
                }
            )
            print(f"[stability] {variant}: median_sharpe={cross['median_sharpe']}", flush=True)

    stability = stability_label(perturbation_rows) if perturbation_rows else "NOT_RUN"
    cross_summary = aggregate_cross_section(results)
    cost_summary = cross_cost_summary(results)
    directions = direction_summary(results)
    per_asset_rows: list[dict[str, Any]] = []
    side_rows: list[dict[str, Any]] = []
    period_output: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    for symbol, result in sorted(results.items()):
        per_asset_rows.append(
            {
                "symbol": symbol,
                **result["metrics"],
                **{f"gross_{key}": value for key, value in result["gross_metrics"].items()},
                **{f"stress_8bps_{key}": value for key, value in result["stress_8bps_metrics"].items()},
            }
        )
        for side, values in result["side_breakdown"].items():
            side_rows.append({"symbol": symbol, "side": side, **values})
        period_output.extend(period_rows(symbol, result, "Y", "year"))
        period_output.extend(period_rows(symbol, result, "Q", "quarter"))
        period_output.extend(recent_rows(symbol, result))
        dataset = eligible[symbol]
        quality_rows.append(
            {
                "symbol": symbol,
                "daily_bars": len(dataset["daily"]),
                "hourly_bars": len(dataset["hourly"]),
                "funding_events": dataset["funding_events"],
                "daily_quality": dataset["daily_quality"]["status"],
                "hourly_quality": dataset["hourly_quality"]["status"],
                "provider_close_time_failures": dataset["provider_close_time_failures"],
                "daily_sha256": dataset["daily_sha256"],
                "hourly_sha256": dataset["hourly_sha256"],
                "funding_sha256": dataset["funding_sha256"],
                "start": iso(dataset["daily"][0].ts),
                "end": iso(dataset["daily"][-1].ts),
            }
        )
    universe_period_rows = universe_period_summary(period_output, portfolio)

    market_path = ARTIFACT_DIR / f"{PREFIX}_market_cap_snapshot.json"
    universe_path = ARTIFACT_DIR / f"{PREFIX}_universe.csv"
    metrics_path = ARTIFACT_DIR / f"{PREFIX}_per_asset_metrics.csv"
    side_path = ARTIFACT_DIR / f"{PREFIX}_long_short.csv"
    period_path = ARTIFACT_DIR / f"{PREFIX}_period_slices.csv"
    universe_period_path = ARTIFACT_DIR / f"{PREFIX}_universe_period_summary.csv"
    quality_path = ARTIFACT_DIR / f"{PREFIX}_data_quality.csv"
    perturb_path = ARTIFACT_DIR / f"{PREFIX}_perturbations.csv"
    portfolio_path = ARTIFACT_DIR / f"{PREFIX}_portfolio_daily.csv"
    loao_path = ARTIFACT_DIR / f"{PREFIX}_portfolio_loao.csv"
    result_path = ARTIFACT_DIR / f"{PREFIX}_summary.json"
    html_path = ARTIFACT_DIR / f"{PREFIX}_interactive_trade_paths.html"

    market_digest = write_json(market_path, snapshot, force=args.force)
    write_csv(universe_path, decisions, force=args.force)
    write_csv(metrics_path, per_asset_rows, force=args.force)
    write_csv(side_path, side_rows, force=args.force)
    write_csv(period_path, period_output, force=args.force)
    write_csv(universe_period_path, universe_period_rows, force=args.force)
    write_csv(quality_path, quality_rows, force=args.force)
    write_csv(perturb_path, perturbation_rows, force=args.force)
    portfolio["daily"].reset_index(names="ts").to_csv(portfolio_path, index=False)
    write_csv(loao_path, loao_rows, force=args.force)

    machine = {
        "schema": "binance-1d-generic-ma7-trend-v0-audit-v1",
        "status": "COMPLETED_DIAGNOSTIC",
        "generated_utc": utc_now().isoformat(),
        "run_end_utc": end_dt.isoformat(),
        "family": "Binance-1D-Generic-MA7-Trend",
        "version": "v0",
        "main_status": "explore",
        "promotion": False,
        "live_ready": False,
        "clean_oos_claim": False,
        "universe_interpretation": "current-top30 retrospective backtest; no historical dynamic membership",
        "config_sha256": config_hash,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "market_snapshot_artifact": market_path.name,
        "market_snapshot_sha256": market_digest,
        "binance_exchange_info_sha256": json_sha256(exchange_info),
        "top30_nonpegged": top30,
        "final_included_symbols": sorted(results),
        "final_included_count": len(results),
        "universe_decisions": decisions,
        "data_quality": quality_rows,
        "generic_config": safe(base),
        "cross_section_summary": cross_summary,
        "cost_summary": cost_summary,
        "direction_summary": directions,
        "universe_period_summary": universe_period_rows,
        "per_asset_metrics": per_asset_rows,
        "long_short": side_rows,
        "portfolio": {
            "metrics": portfolio["metrics"],
            "gross_metrics": portfolio["gross_metrics"],
            "upper_bound_before_rebalance_metrics": portfolio["upper_bound_metrics"],
            "rebalance_cost_note": "same-side risk-weight/scale drift only; internal strategy entry/exit costs already remain in net sleeves",
            "loao": loao_rows,
        },
        "hype_comparison": hype_comparison,
        "perturbations": perturbation_rows,
        "stability_label": stability,
        "limitations": [
            "Current market-cap membership is applied retrospectively to all history; survivorship bias remains.",
            "CoinGecko market cap is a runtime snapshot, not historical point-in-time constituents.",
            "Funding mark is approximated with the event hour close, matching the reused research infrastructure.",
            "The equal-risk portfolio combines independently netted sleeves and adds same-side rebalance drift costs; it is separate from single-asset evidence.",
            "All perturbations are report-only and cannot select or rewrite v0.",
        ],
        "artifact_files": [
            path.name
            for path in (
                market_path,
                universe_path,
                metrics_path,
                side_path,
                period_path,
                universe_period_path,
                quality_path,
                perturb_path,
                portfolio_path,
                loao_path,
                html_path,
            )
        ],
    }
    digest = write_json(result_path, machine, force=args.force)
    render_html(html_path, results, cross_summary, force=args.force)
    print(
        json.dumps(
            {
                "status": machine["status"],
                "included": machine["final_included_symbols"],
                "cross_section_summary": cross_summary,
                "portfolio": portfolio["metrics"],
                "stability": stability,
                "artifact": str(result_path),
                "sha256": digest,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
