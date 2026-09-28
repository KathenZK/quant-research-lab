from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


FAMILY_ROOT = Path("research/asset-portfolios/1d-turtle-breakout")
ARTIFACT_ROOT = FAMILY_ROOT / "artifacts"
DIAG_ROOT = FAMILY_ROOT / "diagnostics"

RUN_DATE = datetime.now(UTC).date().isoformat()
SYMBOLS = ("BTCUSDT", "ETHUSDT", "HYPEUSDT")
DISPLAY_SYMBOLS = {
    "BTCUSDT": "BTC/USDT:USDT",
    "ETHUSDT": "ETH/USDT:USDT",
    "HYPEUSDT": "HYPE/USDT:USDT",
}
INTERVAL = "1d"
FAPI_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"

# Use only fully closed UTC daily candles. On the run date this means the
# requested range ends at today's 00:00 UTC boundary and excludes today's bar.
END_EXCLUSIVE = datetime.now(UTC).date()
START_DATE = END_EXCLUSIVE - timedelta(days=365)

ENTRY_LOOKBACK = 20
EXIT_LOOKBACK = 10
VOL_LOOKBACK = 20
ONE_WAY_COST = 0.00075  # 5 bp taker fee + 2.5 bp close-fill slippage assumption.
ROUND_TRIP_COST = 2 * ONE_WAY_COST


@dataclass(frozen=True, slots=True)
class SizingSpec:
    name: str
    description: str
    kind: str
    max_leverage: float
    target_ann_vol: float | None = None
    risk_budget: float | None = None
    drawdown_throttle: bool = False


SIZING_SPECS = (
    SizingSpec(
        name="fixed_1x",
        description="固定 1.0x 名义仓位",
        kind="fixed",
        max_leverage=1.0,
    ),
    SizingSpec(
        name="vol20_target20_cap1x",
        description="按前 20 日 realized vol 目标年化 20%，最高 1.0x",
        kind="vol_target",
        target_ann_vol=0.20,
        max_leverage=1.0,
    ),
    SizingSpec(
        name="risk1_prev10stop_cap1x",
        description="以前 10 日低点为风险距离，单笔风险 1%，最高 1.0x",
        kind="risk_to_stop",
        risk_budget=0.01,
        max_leverage=1.0,
    ),
    SizingSpec(
        name="risk2_prev10stop_cap1p5x",
        description="以前 10 日低点为风险距离，单笔风险 2%，最高 1.5x",
        kind="risk_to_stop",
        risk_budget=0.02,
        max_leverage=1.5,
    ),
    SizingSpec(
        name="fixed_1x_dd_throttle",
        description="固定 1.0x，净值回撤超过 10%/20% 时降到 0.5x/0.25x",
        kind="fixed",
        max_leverage=1.0,
        drawdown_throttle=True,
    ),
    SizingSpec(
        name="risk1_prev10stop_dd_cap1x",
        description="单笔风险 1% + 回撤降档，最高 1.0x",
        kind="risk_to_stop",
        risk_budget=0.01,
        max_leverage=1.0,
        drawdown_throttle=True,
    ),
)

SUMMARY_JSON = ARTIFACT_ROOT / f"binance_1d_turtle_breakout_summary_{RUN_DATE}.json"
SUMMARY_CSV = ARTIFACT_ROOT / f"binance_1d_turtle_breakout_summary_{RUN_DATE}.csv"
QUALITY_CSV = ARTIFACT_ROOT / f"binance_1d_turtle_breakout_quality_{RUN_DATE}.csv"
CANDLES_CSV = ARTIFACT_ROOT / f"binance_1d_turtle_breakout_candles_{RUN_DATE}.csv"
TRADES_CSV = ARTIFACT_ROOT / f"binance_1d_turtle_breakout_trades_{RUN_DATE}.csv"
EQUITY_CSV = ARTIFACT_ROOT / f"binance_1d_turtle_breakout_equity_{RUN_DATE}.csv"
REPORT_MD = DIAG_ROOT / f"binance-1d-turtle-breakout-{RUN_DATE}.md"


@dataclass(slots=True)
class BacktestResult:
    symbol: str
    summary: dict[str, object]
    trades: list[dict[str, object]]
    equity: pd.DataFrame


def fetch_klines(symbol: str, start_date: date, end_exclusive: date) -> pd.DataFrame:
    start_ms = int(datetime(start_date.year, start_date.month, start_date.day, tzinfo=UTC).timestamp() * 1000)
    end_ms = int(
        datetime(end_exclusive.year, end_exclusive.month, end_exclusive.day, tzinfo=UTC).timestamp() * 1000
    )
    params = {
        "symbol": symbol,
        "interval": INTERVAL,
        "startTime": start_ms,
        "endTime": end_ms - 1,
        "limit": 1500,
    }
    request = Request(f"{FAPI_KLINES_URL}?{urlencode(params)}", headers={"User-Agent": "quant-research-lab/0.1"})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"unexpected Binance response for {symbol}: {payload}")

    columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_volume",
        "trade_count",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "ignore",
    ]
    frame = pd.DataFrame(payload, columns=columns)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "ts",
                "exchange",
                "market_type",
                "symbol",
                "timeframe",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "quote_volume",
                "trade_count",
                "is_closed",
                "source",
            ]
        )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["trade_count"] = pd.to_numeric(frame["trade_count"], errors="coerce").astype("Int64")
    frame["ts"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_ts"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    frame["exchange"] = "binance"
    frame["market_type"] = "um_futures"
    frame["symbol"] = symbol
    frame["display_symbol"] = DISPLAY_SYMBOLS.get(symbol, symbol)
    frame["timeframe"] = INTERVAL
    frame["is_closed"] = frame["close_ts"] < pd.Timestamp.now(tz=UTC)
    frame["source"] = "binance_fapi_klines"
    return frame[
        [
            "ts",
            "close_ts",
            "exchange",
            "market_type",
            "symbol",
            "display_symbol",
            "timeframe",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
            "trade_count",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
            "is_closed",
            "source",
        ]
    ].sort_values("ts")


def quality_checks(frame: pd.DataFrame, symbol: str, start_date: date, end_exclusive: date) -> dict[str, object]:
    expected = pd.date_range(
        datetime(start_date.year, start_date.month, start_date.day, tzinfo=UTC),
        datetime(end_exclusive.year, end_exclusive.month, end_exclusive.day, tzinfo=UTC) - timedelta(days=1),
        freq="1D",
    )
    ts = pd.DatetimeIndex(pd.to_datetime(frame["ts"], utc=True)) if not frame.empty else pd.DatetimeIndex([])
    missing = expected.difference(ts)
    extra = ts.difference(expected)
    duplicates = int(frame.duplicated("ts").sum()) if not frame.empty else 0
    critical_columns = ["open", "high", "low", "close", "volume", "quote_volume", "trade_count"]
    null_counts = {column: int(frame[column].isna().sum()) for column in critical_columns if column in frame.columns}
    invalid_ohlc = 0
    if not frame.empty:
        invalid_ohlc = int(
            (
                (frame["open"] <= 0)
                | (frame["high"] <= 0)
                | (frame["low"] <= 0)
                | (frame["close"] <= 0)
                | (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
                | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
            ).sum()
        )
    return {
        "exchange": "binance",
        "market_type": "um_futures",
        "symbol": symbol,
        "display_symbol": DISPLAY_SYMBOLS.get(symbol, symbol),
        "timeframe": INTERVAL,
        "requested_start_utc": start_date.isoformat(),
        "requested_end_exclusive_utc": end_exclusive.isoformat(),
        "first_bar_utc": str(ts.min()) if len(ts) else None,
        "last_bar_utc": str(ts.max()) if len(ts) else None,
        "rows": int(len(frame)),
        "expected_rows": int(len(expected)),
        "missing_daily_bars": int(len(missing)),
        "first_missing_daily_bar": str(missing[0]) if len(missing) else None,
        "extra_daily_bars": int(len(extra)),
        "duplicate_ts": duplicates,
        "critical_nulls": null_counts,
        "invalid_ohlc_rows": invalid_ohlc,
        "non_closed_rows": int((~frame["is_closed"].astype(bool)).sum()) if not frame.empty else 0,
        "source_counts": frame["source"].value_counts(dropna=False).astype(int).to_dict() if not frame.empty else {},
    }


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return math.nan
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min())


def safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return math.inf if numerator > 0 else math.nan
    return numerator / denominator


def drawdown_multiplier(equity_net: float, peak_net: float) -> float:
    if peak_net <= 0:
        return 1.0
    drawdown = equity_net / peak_net - 1.0
    if drawdown <= -0.20:
        return 0.25
    if drawdown <= -0.10:
        return 0.50
    return 1.0


def compute_entry_position_size(spec: SizingSpec, row: pd.Series, equity_net: float, peak_net: float) -> tuple[float, str]:
    close = float(row["close"])
    sizing_note = spec.description

    if spec.kind == "fixed":
        size = 1.0
    elif spec.kind == "vol_target":
        realized_vol = float(row["realized_vol20_ann"]) if pd.notna(row["realized_vol20_ann"]) else math.nan
        if np.isfinite(realized_vol) and realized_vol > 0 and spec.target_ann_vol is not None:
            size = spec.target_ann_vol / realized_vol
            sizing_note = f"{sizing_note}; realized_vol20_ann={realized_vol:.4f}"
        else:
            size = 1.0
            sizing_note = f"{sizing_note}; realized_vol unavailable, fallback 1.0x"
    elif spec.kind == "risk_to_stop":
        prev10_low = float(row["prev10_low"]) if pd.notna(row["prev10_low"]) else math.nan
        if np.isfinite(prev10_low) and prev10_low < close and spec.risk_budget is not None:
            stop_distance = (close - prev10_low) / close
            size = spec.risk_budget / stop_distance
            sizing_note = f"{sizing_note}; stop_distance={stop_distance:.4f}"
        else:
            size = 0.0
            sizing_note = f"{sizing_note}; invalid stop distance, skip entry"
    else:
        raise ValueError(f"unknown sizing kind: {spec.kind}")

    if spec.drawdown_throttle:
        throttle = drawdown_multiplier(equity_net, peak_net)
        size *= throttle
        sizing_note = f"{sizing_note}; drawdown_throttle={throttle:.2f}"

    size = min(max(size, 0.0), spec.max_leverage)
    return size, sizing_note


def backtest_symbol(frame: pd.DataFrame, symbol: str, spec: SizingSpec) -> BacktestResult:
    data = frame.copy().sort_values("ts").reset_index(drop=True)
    data["ret1"] = data["close"].pct_change()
    data["realized_vol20_ann"] = data["ret1"].shift(1).rolling(VOL_LOOKBACK).std() * math.sqrt(365.25)
    data["prev20_high"] = data["high"].shift(1).rolling(ENTRY_LOOKBACK).max()
    data["prev10_low"] = data["low"].shift(1).rolling(EXIT_LOOKBACK).min()

    equity_gross = 1.0
    equity_net = 1.0
    peak_net = 1.0
    in_position = False
    position_size = 0.0
    entry_i: int | None = None
    entry_ts: pd.Timestamp | None = None
    entry_price: float | None = None
    trade_position_size: float | None = None
    entry_sizing_note: str | None = None
    prev_close: float | None = None
    trades: list[dict[str, object]] = []
    equity_rows: list[dict[str, object]] = []
    overnight_position_days = 0
    overnight_position_size_days = 0.0

    for i, row in data.iterrows():
        close = float(row["close"])
        if prev_close is not None and in_position:
            close_return = close / prev_close - 1.0
            equity_gross *= 1.0 + position_size * close_return
            equity_net *= 1.0 + position_size * close_return
            overnight_position_days += 1
            overnight_position_size_days += position_size

        action = "hold_long" if in_position else "flat"
        exit_level = row["prev10_low"]
        entry_level = row["prev20_high"]

        if in_position and pd.notna(exit_level) and close < float(exit_level):
            assert entry_i is not None and entry_ts is not None and entry_price is not None
            assert trade_position_size is not None and entry_sizing_note is not None
            exit_cost_multiplier = 1.0 - position_size * ONE_WAY_COST
            equity_net *= exit_cost_multiplier
            underlying_return = close / entry_price - 1.0
            gross_return = trade_position_size * underlying_return
            net_return = (1.0 + gross_return) * (1.0 - trade_position_size * ONE_WAY_COST) * exit_cost_multiplier - 1.0
            trades.append(
                {
                    "sizing_model": spec.name,
                    "sizing_description": spec.description,
                    "symbol": symbol,
                    "display_symbol": DISPLAY_SYMBOLS.get(symbol, symbol),
                    "entry_ts": entry_ts.isoformat(),
                    "exit_ts": row["ts"].isoformat(),
                    "entry_price": entry_price,
                    "exit_price": close,
                    "entry_position_size": trade_position_size,
                    "bars_held": int(i - entry_i),
                    "exit_reason": "close_below_prev10_low",
                    "underlying_return_pct": underlying_return * 100.0,
                    "gross_return_pct": gross_return * 100.0,
                    "net_return_pct": net_return * 100.0,
                    "entry_prev20_high": float(data.loc[entry_i, "prev20_high"]),
                    "exit_prev10_low": float(exit_level),
                    "sizing_note": entry_sizing_note,
                }
            )
            in_position = False
            position_size = 0.0
            entry_i = None
            entry_ts = None
            entry_price = None
            trade_position_size = None
            entry_sizing_note = None
            action = "exit_close"
        elif (not in_position) and pd.notna(entry_level) and close > float(entry_level):
            size, sizing_note = compute_entry_position_size(spec, row, equity_net, peak_net)
            if size > 0:
                in_position = True
                position_size = size
                entry_i = int(i)
                entry_ts = row["ts"]
                entry_price = close
                trade_position_size = size
                entry_sizing_note = sizing_note
                equity_net *= 1.0 - size * ONE_WAY_COST
                action = "entry_close"
            else:
                action = f"entry_skipped:{sizing_note}"

        equity_rows.append(
            {
                "ts": row["ts"],
                "sizing_model": spec.name,
                "symbol": symbol,
                "display_symbol": DISPLAY_SYMBOLS.get(symbol, symbol),
                "close": close,
                "prev20_high": entry_level,
                "prev10_low": exit_level,
                "realized_vol20_ann": row["realized_vol20_ann"],
                "is_long_after_close": int(in_position),
                "position_after_close": position_size if in_position else 0.0,
                "action": action,
                "equity_gross": equity_gross,
                "equity_net": equity_net,
            }
        )
        peak_net = max(peak_net, equity_net)
        prev_close = close

    if in_position and len(data):
        final_row = data.iloc[-1]
        close = float(final_row["close"])
        assert entry_i is not None and entry_ts is not None and entry_price is not None
        assert trade_position_size is not None and entry_sizing_note is not None
        exit_cost_multiplier = 1.0 - position_size * ONE_WAY_COST
        equity_net *= exit_cost_multiplier
        underlying_return = close / entry_price - 1.0
        gross_return = trade_position_size * underlying_return
        net_return = (1.0 + gross_return) * (1.0 - trade_position_size * ONE_WAY_COST) * exit_cost_multiplier - 1.0
        trades.append(
            {
                "sizing_model": spec.name,
                "sizing_description": spec.description,
                "symbol": symbol,
                "display_symbol": DISPLAY_SYMBOLS.get(symbol, symbol),
                "entry_ts": entry_ts.isoformat(),
                "exit_ts": final_row["ts"].isoformat(),
                "entry_price": entry_price,
                "exit_price": close,
                "entry_position_size": trade_position_size,
                "bars_held": int(len(data) - 1 - entry_i),
                "exit_reason": "period_end_mark",
                "underlying_return_pct": underlying_return * 100.0,
                "gross_return_pct": gross_return * 100.0,
                "net_return_pct": net_return * 100.0,
                "entry_prev20_high": float(data.loc[entry_i, "prev20_high"]),
                "exit_prev10_low": float(final_row["prev10_low"]) if pd.notna(final_row["prev10_low"]) else math.nan,
                "sizing_note": entry_sizing_note,
            }
        )
        equity_rows[-1]["equity_net"] = equity_net
        equity_rows[-1]["is_long_after_close"] = 0
        equity_rows[-1]["position_after_close"] = 0
        equity_rows[-1]["action"] = "period_end_mark"

    equity = pd.DataFrame(equity_rows)
    closed = pd.DataFrame(trades)
    net_trade_returns = closed["net_return_pct"] / 100.0 if not closed.empty else pd.Series(dtype="float64")
    positive = net_trade_returns[net_trade_returns > 0].sum()
    negative = net_trade_returns[net_trade_returns < 0].sum()

    first_close = float(data["close"].iloc[0])
    last_close = float(data["close"].iloc[-1])
    buy_hold_gross = last_close / first_close - 1.0
    buy_hold_net = (last_close / first_close) * (1.0 - ONE_WAY_COST) ** 2 - 1.0
    total_days = max(1, int((data["ts"].iloc[-1] - data["ts"].iloc[0]).days) + 1)

    final_equity_gross = float(equity["equity_gross"].iloc[-1]) if not equity.empty else math.nan
    final_equity_net = float(equity["equity_net"].iloc[-1]) if not equity.empty else math.nan
    summary = {
        "sizing_model": spec.name,
        "sizing_description": spec.description,
        "symbol": symbol,
        "display_symbol": DISPLAY_SYMBOLS.get(symbol, symbol),
        "start_ts": data["ts"].iloc[0].isoformat(),
        "end_ts": data["ts"].iloc[-1].isoformat(),
        "bars": int(len(data)),
        "entry_rule": "close > prior 20 daily highs",
        "exit_rule": "close < prior 10 daily lows",
        "fill_model": "same-day close diagnostic fill",
        "one_way_cost_bps": ONE_WAY_COST * 10_000,
        "round_trip_cost_bps": ROUND_TRIP_COST * 10_000,
        "max_leverage": spec.max_leverage,
        "target_ann_vol_pct": spec.target_ann_vol * 100.0 if spec.target_ann_vol is not None else math.nan,
        "risk_budget_pct": spec.risk_budget * 100.0 if spec.risk_budget is not None else math.nan,
        "drawdown_throttle": spec.drawdown_throttle,
        "strategy_total_return_gross_pct": (final_equity_gross - 1.0) * 100.0,
        "strategy_total_return_net_pct": (final_equity_net - 1.0) * 100.0,
        "strategy_cagr_gross_pct": (final_equity_gross ** (365.25 / total_days) - 1.0) * 100.0,
        "strategy_cagr_net_pct": (final_equity_net ** (365.25 / total_days) - 1.0) * 100.0,
        "strategy_max_drawdown_gross_pct": max_drawdown(equity["equity_gross"]) * 100.0,
        "strategy_max_drawdown_net_pct": max_drawdown(equity["equity_net"]) * 100.0,
        "buy_hold_total_return_gross_pct": buy_hold_gross * 100.0,
        "buy_hold_total_return_net_pct": buy_hold_net * 100.0,
        "buy_hold_cagr_net_pct": ((1.0 + buy_hold_net) ** (365.25 / total_days) - 1.0) * 100.0,
        "trades": int(len(trades)),
        "win_rate_net_pct": float((net_trade_returns > 0).mean() * 100.0) if len(net_trade_returns) else math.nan,
        "profit_factor_net": safe_div(float(positive), abs(float(negative))),
        "avg_trade_net_pct": float(net_trade_returns.mean() * 100.0) if len(net_trade_returns) else math.nan,
        "median_trade_net_pct": float(net_trade_returns.median() * 100.0) if len(net_trade_returns) else math.nan,
        "best_trade_net_pct": float(net_trade_returns.max() * 100.0) if len(net_trade_returns) else math.nan,
        "worst_trade_net_pct": float(net_trade_returns.min() * 100.0) if len(net_trade_returns) else math.nan,
        "time_in_market_pct": overnight_position_days / len(data) * 100.0,
        "avg_position_pct": overnight_position_size_days / len(data) * 100.0,
        "max_position_pct": float(equity["position_after_close"].max() * 100.0) if not equity.empty else math.nan,
        "period_end_mark_trades": int((closed["exit_reason"] == "period_end_mark").sum()) if not closed.empty else 0,
    }
    return BacktestResult(symbol=symbol, summary=summary, trades=trades, equity=equity)


def pct(value: object, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(number):
        return "n/a"
    return f"{number:.{digits}f}%"


def num(value: object, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(number):
        return "n/a"
    return f"{number:.{digits}f}"


def render_report(summary: pd.DataFrame, quality: pd.DataFrame, output: dict[str, object]) -> str:
    summary_rows = []
    for row in summary.to_dict("records"):
        summary_rows.append(
            "| {display_symbol} | `{sizing_model}` | {strategy_net} | {bh_net} | {mdd} | {trades} | {win} | {pf} | {avg_pos} | {max_pos} |".format(
                display_symbol=row["display_symbol"],
                sizing_model=row["sizing_model"],
                strategy_net=pct(row["strategy_total_return_net_pct"]),
                bh_net=pct(row["buy_hold_total_return_net_pct"]),
                mdd=pct(row["strategy_max_drawdown_net_pct"]),
                trades=int(row["trades"]),
                win=pct(row["win_rate_net_pct"]),
                pf=num(row["profit_factor_net"]),
                avg_pos=pct(row["avg_position_pct"]),
                max_pos=pct(row["max_position_pct"]),
            )
        )
    best_rows = []
    for row in (
        summary.sort_values(["display_symbol", "strategy_total_return_net_pct"], ascending=[True, False])
        .groupby("display_symbol", as_index=False)
        .head(1)
        .to_dict("records")
    ):
        best_rows.append(
            "| {display_symbol} | `{sizing_model}` | {strategy_net} | {mdd} | {avg_pos} | {buy_hold} |".format(
                display_symbol=row["display_symbol"],
                sizing_model=row["sizing_model"],
                strategy_net=pct(row["strategy_total_return_net_pct"]),
                mdd=pct(row["strategy_max_drawdown_net_pct"]),
                avg_pos=pct(row["avg_position_pct"]),
                buy_hold=pct(row["buy_hold_total_return_net_pct"]),
            )
        )
    sizing_rows = [
        f"- `{spec.name}`：{spec.description}。"
        for spec in SIZING_SPECS
    ]
    quality_rows = []
    for row in quality.to_dict("records"):
        quality_rows.append(
            "| {display_symbol} | {rows}/{expected_rows} | {missing} | {dup} | {invalid} | {non_closed} | {start} | {end} |".format(
                display_symbol=row["display_symbol"],
                rows=int(row["rows"]),
                expected_rows=int(row["expected_rows"]),
                missing=int(row["missing_daily_bars"]),
                dup=int(row["duplicate_ts"]),
                invalid=int(row["invalid_ohlc_rows"]),
                non_closed=int(row["non_closed_rows"]),
                start=row["first_bar_utc"],
                end=row["last_bar_utc"],
            )
        )
    best = summary.sort_values("strategy_total_return_net_pct", ascending=False).iloc[0]
    return "\n".join(
        [
            "# Binance 1D Turtle Breakout 20/10 动态仓位诊断",
            "",
            f"- 运行日期：`{RUN_DATE}`",
            "- 数据源：Binance USD-M Futures `/fapi/v1/klines`，`1d`，UTC 日线。",
            f"- 请求范围：`{START_DATE.isoformat()}` 至 `{END_EXCLUSIVE.isoformat()}`（右开，排除运行日未收盘日K）。",
            "- 标的：`BTCUSDT`、`ETHUSDT`、`HYPEUSDT`。",
            f"- 策略：空仓时 `close > 前 {ENTRY_LOOKBACK} 根日K high 的最高值`，按当日 close 买入；持仓后 `close < 前 {EXIT_LOOKBACK} 根日K low 的最低值`，按当日 close 卖出；不做空、不加仓。",
            "- 仓位：入场当日收盘计算，持仓期间不重算；未使用资金按现金处理。",
            f"- 成本：净收益口径每边扣 `{ONE_WAY_COST * 10_000:.1f}bp`（5bp taker fee + 2.5bp 收盘成交滑点假设），毛收益不扣成本。",
            "- 执行限制：这是 same-day close fill 诊断；真实 live 执行无法在确认日收盘价后再精确按该收盘价成交，应至少再做 next-open/next-bar 可执行审计。",
            "",
            "## 仓位模型",
            "",
            *sizing_rows,
            "",
            "## 结论",
            "",
            f"按净收益排序，本次最佳组合是 `{best['display_symbol']}` + `{best['sizing_model']}`，策略净收益 `{pct(best['strategy_total_return_net_pct'])}`，最大回撤 `{pct(best['strategy_max_drawdown_net_pct'])}`，买入持有净收益 `{pct(best['buy_hold_total_return_net_pct'])}`。动态仓位主要通过降低平均仓位来减少亏损和回撤，没有修复信号本身的负期望。",
            "",
            "## 各标的最佳仓位模型",
            "",
            "| 标的 | 最佳仓位模型 | 策略净收益 | 最大回撤(净) | 平均仓位 | 买入持有净收益 |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
            *best_rows,
            "",
            "## 结果汇总",
            "",
            "| 标的 | 仓位模型 | 策略净收益 | 买入持有净收益 | 策略最大回撤(净) | 交易数 | 胜率(净) | Profit factor | 平均仓位 | 最高仓位 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            *summary_rows,
            "",
            "## 数据质量",
            "",
            "| 标的 | 行数/期望 | 缺失日K | 重复ts | OHLC异常 | 未收盘行 | 首根 | 末根 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
            *quality_rows,
            "",
            "## 保留产物",
            "",
            f"- Summary JSON：`{SUMMARY_JSON}`",
            f"- Summary CSV：`{SUMMARY_CSV}`",
            f"- Quality CSV：`{QUALITY_CSV}`",
            f"- Candles CSV：`{CANDLES_CSV}`",
            f"- Trades CSV：`{TRADES_CSV}`",
            f"- Equity CSV：`{EQUITY_CSV}`",
            "",
            "## 状态",
            "",
            "本报告仅为 diagnostic only，不构成 paper-live/live candidate。若要推进，需要补充 next-open 或 next-day VWAP 可执行成交、资金费率、真实手续费等级、滑点敏感性、缺失数据重试与下单状态机审计。",
            "",
            "<!-- output-manifest -->",
            "```json",
            json.dumps(output, ensure_ascii=False, indent=2),
            "```",
        ]
    )


def main() -> None:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    DIAG_ROOT.mkdir(parents=True, exist_ok=True)

    candle_frames: list[pd.DataFrame] = []
    quality_rows: list[dict[str, object]] = []
    results: list[BacktestResult] = []
    for symbol in SYMBOLS:
        frame = fetch_klines(symbol, START_DATE, END_EXCLUSIVE)
        candle_frames.append(frame)
        quality_rows.append(quality_checks(frame, symbol, START_DATE, END_EXCLUSIVE))
        if frame.empty:
            raise RuntimeError(f"no candles returned for {symbol}")
        for spec in SIZING_SPECS:
            results.append(backtest_symbol(frame, symbol, spec))

    candles = pd.concat(candle_frames, ignore_index=True)
    quality = pd.DataFrame(quality_rows)
    summary = pd.DataFrame([result.summary for result in results]).sort_values(
        "strategy_total_return_net_pct", ascending=False
    )
    trades = pd.DataFrame([trade for result in results for trade in result.trades])
    equity = pd.concat([result.equity for result in results], ignore_index=True)

    candles.to_csv(CANDLES_CSV, index=False)
    quality.to_csv(QUALITY_CSV, index=False)
    summary.to_csv(SUMMARY_CSV, index=False)
    trades.to_csv(TRADES_CSV, index=False)
    equity.to_csv(EQUITY_CSV, index=False)

    output = {
        "run_date": RUN_DATE,
        "source": "binance_fapi_klines",
        "market_type": "um_futures",
        "symbols": list(SYMBOLS),
        "timeframe": INTERVAL,
        "start_date_utc": START_DATE.isoformat(),
        "end_exclusive_utc": END_EXCLUSIVE.isoformat(),
        "entry_lookback": ENTRY_LOOKBACK,
        "exit_lookback": EXIT_LOOKBACK,
        "vol_lookback": VOL_LOOKBACK,
        "one_way_cost": ONE_WAY_COST,
        "sizing_models": [
            {
                "name": spec.name,
                "description": spec.description,
                "kind": spec.kind,
                "max_leverage": spec.max_leverage,
                "target_ann_vol": spec.target_ann_vol,
                "risk_budget": spec.risk_budget,
                "drawdown_throttle": spec.drawdown_throttle,
            }
            for spec in SIZING_SPECS
        ],
        "artifacts": {
            "summary_json": str(SUMMARY_JSON),
            "summary_csv": str(SUMMARY_CSV),
            "quality_csv": str(QUALITY_CSV),
            "candles_csv": str(CANDLES_CSV),
            "trades_csv": str(TRADES_CSV),
            "equity_csv": str(EQUITY_CSV),
            "report_md": str(REPORT_MD),
        },
        "summary": summary.to_dict("records"),
        "quality": quality.to_dict("records"),
    }
    SUMMARY_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text(render_report(summary, quality, output), encoding="utf-8")

    print(summary.to_string(index=False))
    print(f"\nWrote {REPORT_MD}")


if __name__ == "__main__":
    main()
