"""沪深300价格指数日K上的 HYPE-1D-MA7-ABT-V7.1 零调参迁移诊断。"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
import hashlib
import json
import math
from pathlib import Path
import time as time_module
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/cn-indexes/1d-hype-ma7-v7-1-transfer"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DATA_ROOT = ROOT / "data/raw/ohlcv"

RUN_DATE = "2026-08-17"
DEFAULT_START = date(2022, 8, 17)
DEFAULT_END = date(2026, 8, 17)
WARMUP_CALENDAR_DAYS = 120

EASTMONEY_BASE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
YAHOO_BASE_URL = "https://query2.finance.yahoo.com/v8/finance/chart"
SOURCE = "eastmoney_kline_api"
EXCHANGE = "sse"
SYMBOL = "000300"
TIMEFRAME = "1d"
MARKET_TYPE = "equity"

BASE_FRICTION = 0.0
STRESS_FRICTION = 0.001


@dataclass(slots=True)
class Position:
    side: int
    entry_index: int
    entry_ts: str
    entry_event: str
    entry_reference: float
    entry_fill: float
    quantity: float
    equity_basis: float
    entry_atr: float
    stop_price: float | None
    bars_held: int = 0
    high_water: float = -math.inf
    low_water: float = math.inf
    oapp_confirm_count: int = 0
    short_rsi_count: int = 0


@dataclass(slots=True)
class ScheduledOrder:
    action: str
    side: int
    reason: str
    execute_index: int
    signal_index: int
    entry_atr: float | None = None
    pehc_eligible: bool = False


@dataclass(slots=True)
class PehcShadow:
    origin_exit_index: int
    remaining_days: int
    highest_close: float
    stop_price: float
    bars_held: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END)
    return parser.parse_args()


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def fetch_bytes(url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 quant-research-lab-research/1.0"
                },
            )
            with urlopen(request, timeout=45) as response:
                content = response.read()
            if content:
                return content
        except Exception as exc:  # pragma: no cover - network retry
            last_error = exc
        time_module.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after retries: {url}: {last_error}")


def retained_fetch(
    url: str,
    path: Path,
    *,
    refresh: bool,
    force: bool,
) -> bytes:
    if path.exists() and not refresh:
        return path.read_bytes()
    if path.exists() and not force:
        raise RuntimeError(f"retained source exists; use --force: {path}")
    content = fetch_bytes(url)
    atomic_write(path, content)
    atomic_write(
        Path(f"{path}.sha256"),
        f"{sha256_bytes(content)}  {path.name}\n".encode(),
    )
    return content


def eastmoney_url(start: date, end: date) -> str:
    params = {
        "secid": "1.000300",
        "klt": "101",
        "fqt": "0",
        "beg": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "lmt": "1000000",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }
    return f"{EASTMONEY_BASE_URL}?{urlencode(params)}"


def yahoo_url(start: date, end: date) -> str:
    period1 = int(datetime.combine(start, time.min, tzinfo=UTC).timestamp())
    period2 = int(
        datetime.combine(end + timedelta(days=2), time.min, tzinfo=UTC).timestamp()
    )
    encoded = quote("000300.SS", safe="")
    return (
        f"{YAHOO_BASE_URL}/{encoded}?period1={period1}&period2={period2}"
        "&interval=1d&events=div%2Csplits"
    )


def parse_eastmoney(content: bytes) -> tuple[pd.DataFrame, dict[str, Any]]:
    payload = json.loads(content)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"Eastmoney returned no data: {payload.get('rc')}")
    if data.get("code") != SYMBOL or data.get("name") != "沪深300":
        raise RuntimeError(
            f"Eastmoney identity mismatch: {data.get('code')} {data.get('name')}"
        )
    rows: list[dict[str, Any]] = []
    for raw in data.get("klines") or []:
        fields = raw.split(",")
        if len(fields) != 11:
            raise RuntimeError(f"unexpected Eastmoney kline field count: {raw}")
        session = date.fromisoformat(fields[0])
        local_open = datetime.combine(
            session,
            time(9, 30),
            tzinfo=pd.Timestamp("2020-01-01", tz="Asia/Shanghai").tzinfo,
        )
        rows.append(
            {
                "session_date": session.isoformat(),
                "ts": pd.Timestamp(local_open).tz_convert("UTC"),
                "open": float(fields[1]),
                "close": float(fields[2]),
                "high": float(fields[3]),
                "low": float(fields[4]),
                "volume": float(fields[5]),
                "amount": float(fields[6]),
                "amplitude_pct": float(fields[7]),
                "change_pct": float(fields[8]),
                "change": float(fields[9]),
                "turnover_pct": float(fields[10]),
            }
        )
    frame = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    if frame.empty:
        raise RuntimeError("Eastmoney returned zero CSI 300 bars")
    quality = audit_source_frame(frame)
    quality.update(
        {
            "provider": "Eastmoney",
            "provider_code": data.get("code"),
            "provider_name": data.get("name"),
            "provider_market": data.get("market"),
            "provider_total_bars": data.get("dktotal"),
            "price_adjustment": "none / fqt=0",
            "session_timezone": "Asia/Shanghai",
            "quality_status": "raw_unaccepted",
        }
    )
    return frame, quality


def audit_source_frame(frame: pd.DataFrame) -> dict[str, Any]:
    numeric = ["open", "high", "low", "close", "volume", "amount"]
    nulls = {column: int(frame[column].isna().sum()) for column in numeric}
    invalid_ohlc = int(
        (
            (frame[["open", "high", "low", "close"]] <= 0.0).any(axis=1)
            | frame["high"].lt(frame[["open", "close", "low"]].max(axis=1))
            | frame["low"].gt(frame[["open", "close", "high"]].min(axis=1))
            | frame["volume"].lt(0.0)
            | frame["amount"].lt(0.0)
        ).sum()
    )
    duplicate_dates = int(frame["session_date"].duplicated().sum())
    duplicate_ts = int(frame["ts"].duplicated().sum())
    monotonic = bool(frame["ts"].is_monotonic_increasing)
    gaps = pd.to_datetime(frame["session_date"]).diff().dt.days.dropna()
    blockers = sum(nulls.values()) + invalid_ohlc + duplicate_dates + duplicate_ts
    if not monotonic:
        blockers += 1
    return {
        "status": "PASS_SOURCE_LEVEL" if blockers == 0 else "FAIL",
        "rows": int(len(frame)),
        "first_session": str(frame["session_date"].iloc[0]),
        "last_session": str(frame["session_date"].iloc[-1]),
        "nulls": nulls,
        "invalid_ohlc_rows": invalid_ohlc,
        "duplicate_session_dates": duplicate_dates,
        "duplicate_timestamps": duplicate_ts,
        "timestamps_monotonic": monotonic,
        "max_calendar_gap_days": int(gaps.max()) if len(gaps) else 0,
        "zero_volume_rows": int(frame["volume"].eq(0.0).sum()),
        "source_level_blockers": blockers,
        "exchange_calendar_audit": "NOT_IMPLEMENTED",
        "is_closed_provenance": "UNAVAILABLE",
        "standard_trade_count": "UNAVAILABLE",
        "standard_vwap": "UNAVAILABLE",
    }


def parse_yahoo(content: bytes) -> pd.DataFrame:
    payload = json.loads(content)
    chart = payload.get("chart", {})
    if chart.get("error") is not None:
        raise RuntimeError(f"Yahoo chart error: {chart['error']}")
    result = (chart.get("result") or [None])[0]
    if not isinstance(result, dict):
        raise RuntimeError("Yahoo returned no CSI 300 result")
    if result["meta"].get("symbol") != "000300.SS":
        raise RuntimeError("Yahoo symbol mismatch")
    timestamps = result.get("timestamp") or []
    quote_row = result["indicators"]["quote"][0]
    frame = pd.DataFrame(
        {
            "ts": pd.to_datetime(timestamps, unit="s", utc=True),
            "open": quote_row["open"],
            "high": quote_row["high"],
            "low": quote_row["low"],
            "close": quote_row["close"],
        }
    )
    frame["session_date"] = (
        frame["ts"].dt.tz_convert("Asia/Shanghai").dt.date.astype(str)
    )
    return frame


def cross_source_check(primary: pd.DataFrame, yahoo: pd.DataFrame) -> dict[str, Any]:
    yahoo_valid = yahoo.dropna(subset=["open", "high", "low", "close"]).copy()
    merged = primary.merge(
        yahoo_valid[["session_date", "open", "high", "low", "close"]],
        on="session_date",
        suffixes=("_eastmoney", "_yahoo"),
        how="inner",
    )
    difference_rows: list[dict[str, Any]] = []
    for column in ["open", "high", "low", "close"]:
        column_differences = (
            (
                merged[f"{column}_eastmoney"]
                / merged[f"{column}_yahoo"]
                - 1.0
            ).abs()
            * 10_000.0
        )
        difference_rows.extend(
            {
                "session_date": str(merged.iloc[index]["session_date"]),
                "field": column,
                "eastmoney": float(
                    merged.iloc[index][f"{column}_eastmoney"]
                ),
                "yahoo": float(merged.iloc[index][f"{column}_yahoo"]),
                "absolute_diff_bps": float(value),
            }
            for index, value in enumerate(column_differences)
        )
    differences = [row["absolute_diff_bps"] for row in difference_rows]
    array = np.asarray(differences, dtype=float)
    return {
        "yahoo_rows": int(len(yahoo)),
        "yahoo_valid_rows": int(len(yahoo_valid)),
        "yahoo_null_ohlc_rows": int(len(yahoo) - len(yahoo_valid)),
        "overlap_sessions": int(len(merged)),
        "overlap_first": (
            str(merged["session_date"].iloc[0]) if not merged.empty else None
        ),
        "overlap_last": (
            str(merged["session_date"].iloc[-1]) if not merged.empty else None
        ),
        "ohlc_comparisons": int(len(array)),
        "mean_absolute_diff_bps": float(array.mean()) if len(array) else None,
        "p95_absolute_diff_bps": (
            float(np.quantile(array, 0.95)) if len(array) else None
        ),
        "max_absolute_diff_bps": float(array.max()) if len(array) else None,
        "largest_differences": sorted(
            difference_rows,
            key=lambda row: row["absolute_diff_bps"],
            reverse=True,
        )[:5],
        "role": "secondary cross-check only; Yahoo missing rows are not used",
    }


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    previous_close = output["close"].shift(1)
    true_range = pd.concat(
        [
            output["high"] - output["low"],
            (output["high"] - previous_close).abs(),
            (output["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    output["sma7"] = output["close"].rolling(7, min_periods=7).mean()
    output["atr7"] = true_range.rolling(7, min_periods=7).mean()
    delta = output["close"].diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    rsi = pd.Series(np.nan, index=output.index, dtype=float)
    length = 6
    if len(output) > length:
        avg_gain = float(gain.iloc[1 : length + 1].mean())
        avg_loss = float(loss.iloc[1 : length + 1].mean())
        rsi.iloc[length] = rsi_value(avg_gain, avg_loss)
        for index in range(length + 1, len(output)):
            avg_gain = (avg_gain * (length - 1) + float(gain.iloc[index])) / length
            avg_loss = (avg_loss * (length - 1) + float(loss.iloc[index])) / length
            rsi.iloc[index] = rsi_value(avg_gain, avg_loss)
    output["rsi6"] = rsi
    return output


def rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    relative_strength = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def slipped_price(
    reference: float,
    side: int,
    action: str,
    friction_per_fill: float,
) -> float:
    if action == "entry":
        return reference * (
            1.0 + friction_per_fill if side > 0 else 1.0 - friction_per_fill
        )
    return reference * (
        1.0 - friction_per_fill if side > 0 else 1.0 + friction_per_fill
    )


def max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0.0:
            worst = min(worst, value / peak - 1.0)
    return worst * 100.0


def annualized_return(equity: float, days: int) -> float | None:
    if equity <= 0.0 or days <= 0:
        return None
    return (equity ** (365.25 / days) - 1.0) * 100.0


def sharpe(equity: list[float]) -> float | None:
    series = pd.Series(equity, dtype=float)
    returns = series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    if len(returns) < 2 or float(returns.std(ddof=1)) <= 0.0:
        return None
    return float(np.sqrt(252.0) * returns.mean() / returns.std(ddof=1))


def mark_equity(cash: float, position: Position | None, price: float) -> float:
    if position is None:
        return cash
    gross = (
        position.quantity * (price - position.entry_fill)
        if position.side > 0
        else position.quantity * (position.entry_fill - price)
    )
    return cash + gross


def run_backtest(
    source_frame: pd.DataFrame,
    *,
    start: date,
    end: date,
    friction_per_fill: float,
    signal_lag_sessions: int = 0,
    allow_long: bool = True,
    allow_short: bool = True,
) -> dict[str, Any]:
    frame = add_indicators(
        source_frame[
            pd.to_datetime(source_frame["session_date"]).dt.date.le(end)
        ].reset_index(drop=True)
    )
    dates = pd.to_datetime(frame["session_date"]).dt.date.to_numpy()
    start_index = int(np.searchsorted(dates, start, side="left"))
    if start_index >= len(frame):
        raise RuntimeError(f"no sessions on or after {start}")
    if len(frame) - start_index < 1:
        raise RuntimeError("empty study window")

    cash = 1.0
    position: Position | None = None
    scheduled: ScheduledOrder | None = None
    cooldown_remaining = 0
    pehc_shadow: PehcShadow | None = None
    pehc_pending_due: int | None = None
    trades: list[dict[str, Any]] = []
    path: list[dict[str, Any]] = []
    equity_points = [1.0]
    close_equity = [1.0]
    exposure_sessions = 0
    counts = {
        "protective_stop": 0,
        "forced_short": 0,
        "pehc_shadow_start": 0,
        "pehc_opportunity": 0,
        "pehc_handoff": 0,
    }

    def row_ts(index: int, event: str) -> str:
        base = pd.Timestamp(frame.iloc[index]["ts"])
        return f"{base.isoformat()}#{event}"

    def open_position(
        index: int,
        reference: float,
        side: int,
        entry_atr: float,
        reason: str,
        event: str,
    ) -> None:
        nonlocal position
        fill = slipped_price(reference, side, "entry", friction_per_fill)
        quantity = cash / fill
        initial_stop = (
            reference + 1.5 * entry_atr if side < 0 else None
        )
        position = Position(
            side=side,
            entry_index=index,
            entry_ts=row_ts(index, event),
            entry_event=reason,
            entry_reference=reference,
            entry_fill=fill,
            quantity=quantity,
            equity_basis=cash,
            entry_atr=entry_atr,
            stop_price=initial_stop,
            high_water=reference,
            low_water=reference,
        )

    def close_position(
        index: int,
        reference: float,
        reason: str,
        event: str,
        *,
        arm_pehc: bool = False,
    ) -> int | None:
        nonlocal cash, position, cooldown_remaining, pehc_shadow
        if position is None:
            return None
        closed = position
        exit_fill = slipped_price(
            reference,
            closed.side,
            "exit",
            friction_per_fill,
        )
        gross = (
            closed.quantity * (exit_fill - closed.entry_fill)
            if closed.side > 0
            else closed.quantity * (closed.entry_fill - exit_fill)
        )
        cash += gross
        return_on_basis = gross / closed.equity_basis if closed.equity_basis else 0.0
        trades.append(
            {
                "trade_id": len(trades) + 1,
                "side": "long" if closed.side > 0 else "short",
                "entry_ts": closed.entry_ts,
                "entry_event": closed.entry_event,
                "entry_reference": closed.entry_reference,
                "entry_fill": closed.entry_fill,
                "exit_ts": row_ts(index, event),
                "exit_reason": reason,
                "exit_reference": reference,
                "exit_fill": exit_fill,
                "bars_held": closed.bars_held,
                "net_pnl": gross,
                "net_return_pct": return_on_basis * 100.0,
            }
        )
        cooldown_remaining = 2 if closed.side > 0 else 3
        if (
            closed.side > 0
            and reason == "long_mfe_fraction_trail_exit"
            and arm_pehc
            and return_on_basis > 0.0028
            and closed.stop_price is not None
        ):
            pehc_shadow = PehcShadow(
                origin_exit_index=index,
                remaining_days=8,
                highest_close=closed.high_water,
                stop_price=closed.stop_price,
                bars_held=closed.bars_held,
            )
            counts["pehc_shadow_start"] += 1
        elif closed.side > 0:
            pehc_shadow = None
        side = closed.side
        position = None
        return side

    for index in range(start_index, len(frame)):
        row = frame.iloc[index]
        current_date = date.fromisoformat(str(row["session_date"]))
        if current_date > end:
            break
        events: list[str] = []
        exposed_today = position is not None
        previous_ma = (
            float(frame.iloc[index - 1]["sma7"]) if index > 0 else math.nan
        )
        previous_atr = (
            float(frame.iloc[index - 1]["atr7"]) if index > 0 else math.nan
        )

        # Overnight gap protection precedes any scheduled market-at-open exit.
        if position is not None and position.stop_price is not None:
            gap_hit = (
                position.side > 0 and float(row["open"]) <= position.stop_price
            ) or (
                position.side < 0 and float(row["open"]) >= position.stop_price
            )
            if gap_hit:
                stopped_side = close_position(
                    index,
                    float(row["open"]),
                    "protective_stop_gap_open",
                    "open",
                )
                counts["protective_stop"] += 1
                events.append("protective_stop_gap_open")
                scheduled = None
                if (
                    stopped_side == 1
                    and allow_short
                    and math.isfinite(previous_ma)
                    and math.isfinite(previous_atr)
                    and float(row["open"]) < previous_ma
                ):
                    open_position(
                        index,
                        float(row["open"]),
                        -1,
                        previous_atr,
                        "forced_short_after_protective_stop",
                        "open",
                    )
                    counts["forced_short"] += 1
                    events.append("forced_short")

        if scheduled is not None and scheduled.execute_index == index:
            if scheduled.action == "exit" and position is not None:
                close_position(
                    index,
                    float(row["open"]),
                    scheduled.reason,
                    "open",
                    arm_pehc=scheduled.pehc_eligible,
                )
                events.append(scheduled.reason)
            elif (
                scheduled.action == "entry"
                and position is None
                and scheduled.entry_atr is not None
            ):
                open_position(
                    index,
                    float(row["open"]),
                    scheduled.side,
                    scheduled.entry_atr,
                    scheduled.reason,
                    "open",
                )
                events.append(scheduled.reason)
            scheduled = None

        if (
            position is None
            and pehc_pending_due == index
            and allow_short
            and math.isfinite(previous_ma)
            and math.isfinite(previous_atr)
        ):
            if float(row["open"]) < previous_ma:
                open_position(
                    index,
                    float(row["open"]),
                    -1,
                    previous_atr,
                    "pehc_short_handoff",
                    "open",
                )
                counts["pehc_handoff"] += 1
                events.append("pehc_short_handoff")
            pehc_pending_due = None

        exposed_today = exposed_today or position is not None
        forced_intraday = False
        if position is not None and position.stop_price is not None:
            stop_hit = (
                position.side > 0 and float(row["low"]) <= position.stop_price
            ) or (
                position.side < 0 and float(row["high"]) >= position.stop_price
            )
            if stop_hit:
                stop_reference = float(position.stop_price)
                stopped_side = close_position(
                    index,
                    stop_reference,
                    "protective_stop",
                    "intraday_unknown",
                )
                counts["protective_stop"] += 1
                events.append("protective_stop")
                if (
                    stopped_side == 1
                    and allow_short
                    and math.isfinite(previous_ma)
                    and math.isfinite(previous_atr)
                    and stop_reference < previous_ma
                ):
                    open_position(
                        index,
                        stop_reference,
                        -1,
                        previous_atr,
                        "forced_short_after_protective_stop",
                        "intraday_unknown",
                    )
                    counts["forced_short"] += 1
                    forced_intraday = True
                    exposed_today = True
                    events.append("forced_short")

        if (
            position is None
            and pehc_shadow is not None
            and pehc_pending_due is None
            and index > pehc_shadow.origin_exit_index
        ):
            if float(row["low"]) <= pehc_shadow.stop_price:
                opportunity_price = min(float(row["open"]), pehc_shadow.stop_price)
                counts["pehc_opportunity"] += 1
                if (
                    allow_short
                    and math.isfinite(previous_ma)
                    and opportunity_price < previous_ma
                ):
                    pehc_pending_due = index + 1
                pehc_shadow = None
                events.append("pehc_opportunity")

        if position is not None:
            if forced_intraday:
                adverse_equity = mark_equity(cash, position, float(row["close"]))
            else:
                adverse_price = (
                    float(row["low"]) if position.side > 0 else float(row["high"])
                )
                adverse_equity = mark_equity(cash, position, adverse_price)
            equity_points.append(adverse_equity)

            position.high_water = max(position.high_water, float(row["close"]))
            position.low_water = min(position.low_water, float(row["close"]))
            position.bars_held += 1

            current_ma = float(row["sma7"])
            current_atr = float(row["atr7"])
            current_rsi = float(row["rsi6"])
            boundary = False
            max_hold_hit = False
            profit_exit = False
            exit_reason: str | None = None
            pehc_eligible = False

            if position.side > 0:
                if math.isfinite(current_ma) and math.isfinite(current_atr):
                    boundary = (
                        float(row["close"]) < current_ma - 0.75 * current_atr
                    )
                    mfe = position.high_water - position.entry_reference
                    if mfe >= 0.5 * current_atr and mfe > 0.0:
                        giveback = (
                            position.high_water - float(row["close"])
                        ) / mfe
                        profitable = (
                            float(row["close"]) / position.entry_reference - 1.0
                        ) > 0.0028
                        position.oapp_confirm_count = (
                            position.oapp_confirm_count + 1
                            if giveback >= 0.10 and profitable
                            else 0
                        )
                    else:
                        position.oapp_confirm_count = 0
                    profit_exit = position.oapp_confirm_count >= 2
                max_hold_hit = position.bars_held >= 90
                if profit_exit:
                    exit_reason = "long_mfe_fraction_trail_exit"
                    pehc_eligible = not boundary and not max_hold_hit
                elif boundary:
                    exit_reason = "ma7_hysteresis_exit"
                elif max_hold_hit:
                    exit_reason = "max_hold"
            else:
                if math.isfinite(current_rsi):
                    profitable = (
                        position.entry_reference / float(row["close"]) - 1.0
                    ) > 0.0028
                    position.short_rsi_count = (
                        position.short_rsi_count + 1
                        if current_rsi < 20.0 and profitable
                        else 0
                    )
                    profit_exit = position.short_rsi_count >= 2
                if math.isfinite(current_ma) and math.isfinite(current_atr):
                    boundary = (
                        float(row["close"]) > current_ma + 0.75 * current_atr
                    )
                slope_exit = (
                    index > 0
                    and math.isfinite(current_ma)
                    and math.isfinite(previous_ma)
                    and current_ma - previous_ma >= 0.0
                )
                max_hold_hit = position.bars_held >= 20
                if profit_exit:
                    exit_reason = "short_rsi_take_profit"
                elif boundary:
                    exit_reason = "ma7_hysteresis_exit"
                elif slope_exit:
                    exit_reason = "ma7_slope_exit"
                elif max_hold_hit:
                    exit_reason = "max_hold"

            if math.isfinite(current_atr):
                if position.side > 0:
                    next_stop = position.high_water - 1.5 * current_atr
                    if position.stop_price is None or next_stop > position.stop_price:
                        position.stop_price = next_stop
                else:
                    hard_stop = (
                        position.entry_reference + 1.5 * position.entry_atr
                    )
                    trailing_stop = position.low_water + 4.0 * current_atr
                    next_stop = min(hard_stop, trailing_stop)
                    if position.stop_price is None or next_stop < position.stop_price:
                        position.stop_price = next_stop

            if exit_reason is not None and index + 1 < len(frame):
                scheduled = ScheduledOrder(
                    action="exit",
                    side=0,
                    reason=exit_reason,
                    execute_index=index + 1 + signal_lag_sessions,
                    signal_index=index,
                    pehc_eligible=pehc_eligible,
                )

        if pehc_shadow is not None:
            current_ma = float(row["sma7"])
            current_atr = float(row["atr7"])
            shadow_boundary = (
                math.isfinite(current_ma)
                and math.isfinite(current_atr)
                and float(row["close"]) < current_ma - 0.75 * current_atr
            )
            if shadow_boundary or pehc_shadow.bars_held >= 90:
                pehc_shadow = None
            else:
                pehc_shadow.remaining_days -= 1
                pehc_shadow.bars_held += 1
                pehc_shadow.highest_close = max(
                    pehc_shadow.highest_close,
                    float(row["close"]),
                )
                if math.isfinite(current_atr):
                    pehc_shadow.stop_price = max(
                        pehc_shadow.stop_price,
                        pehc_shadow.highest_close - 1.5 * current_atr,
                    )
                if pehc_shadow.remaining_days <= 0:
                    pehc_shadow = None

        if position is None and scheduled is None and pehc_pending_due is None:
            cooldown_blocked = cooldown_remaining > 0
            if cooldown_blocked:
                cooldown_remaining -= 1
            current_ma = float(row["sma7"])
            current_atr = float(row["atr7"])
            if (
                not cooldown_blocked
                and index >= 2
                and math.isfinite(current_ma)
                and math.isfinite(current_atr)
                and math.isfinite(previous_ma)
                and index + 1 + signal_lag_sessions < len(frame)
            ):
                previous_close = float(frame.iloc[index - 1]["close"])
                long_signal = (
                    allow_long
                    and previous_close <= previous_ma
                    and float(row["close"]) > current_ma
                    and current_ma - previous_ma >= 0.02 * current_atr
                )
                previous_two_ma = float(frame.iloc[index - 2]["sma7"])
                short_signal = (
                    allow_short
                    and math.isfinite(previous_two_ma)
                    and previous_close >= previous_ma
                    and float(row["close"]) < current_ma - 0.10 * current_atr
                    and current_ma - previous_two_ma <= -0.02 * current_atr
                )
                if long_signal or short_signal:
                    side = 1 if long_signal else -1
                    scheduled = ScheduledOrder(
                        action="entry",
                        side=side,
                        reason="native_reclaim",
                        execute_index=index + 1 + signal_lag_sessions,
                        signal_index=index,
                        entry_atr=current_atr,
                    )
                    pehc_shadow = None

        marked = mark_equity(cash, position, float(row["close"]))
        close_equity.append(marked)
        equity_points.append(marked)
        if exposed_today:
            exposure_sessions += 1
        path.append(
            {
                "session_date": current_date.isoformat(),
                "ts": pd.Timestamp(row["ts"]).isoformat(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "sma7": (
                    float(row["sma7"]) if math.isfinite(float(row["sma7"])) else None
                ),
                "atr7": (
                    float(row["atr7"]) if math.isfinite(float(row["atr7"])) else None
                ),
                "rsi6": (
                    float(row["rsi6"]) if math.isfinite(float(row["rsi6"])) else None
                ),
                "position": position.side if position is not None else 0,
                "equity_close": marked,
                "events": "|".join(events),
            }
        )

    if position is not None:
        terminal_index = len(frame) - 1
        terminal = frame.iloc[terminal_index]
        close_position(
            terminal_index,
            float(terminal["close"]),
            "terminal_close",
            "close",
        )
        equity_points.append(cash)
        close_equity.append(cash)
        if path:
            path[-1]["equity_close"] = cash
            path[-1]["position"] = 0
            path[-1]["events"] = (
                f"{path[-1]['events']}|terminal_close".strip("|")
            )

    gains = sum(max(float(row["net_pnl"]), 0.0) for row in trades)
    losses = -sum(min(float(row["net_pnl"]), 0.0) for row in trades)
    study_first = date.fromisoformat(path[0]["session_date"])
    study_last = date.fromisoformat(path[-1]["session_date"])
    elapsed_days = max(1, (study_last - study_first).days + 1)
    metrics = {
        "study_start": study_first.isoformat(),
        "study_end": study_last.isoformat(),
        "sessions": len(path),
        "net_return_pct": (cash - 1.0) * 100.0,
        "equity_multiple": cash,
        "daily_ohlc_mdd_pct": max_drawdown(equity_points),
        "daily_close_mdd_pct": max_drawdown(close_equity),
        "annualized_return_pct": annualized_return(cash, elapsed_days),
        "sharpe_252": sharpe(close_equity),
        "closed_trades": len(trades),
        "long_trades": sum(row["side"] == "long" for row in trades),
        "short_trades": sum(row["side"] == "short" for row in trades),
        "win_rate": (
            sum(float(row["net_pnl"]) > 0.0 for row in trades) / len(trades)
            if trades
            else None
        ),
        "profit_factor": (
            gains / losses if losses > 0.0 else (math.inf if gains > 0.0 else None)
        ),
        "exposure_pct": (
            exposure_sessions / len(path) * 100.0 if path else 0.0
        ),
        **counts,
    }
    return {
        "metrics": metrics,
        "trades": trades,
        "path": path,
    }


def buy_and_hold(
    frame: pd.DataFrame,
    start: date,
    end: date,
    *,
    friction_per_fill: float = 0.0,
) -> dict[str, Any]:
    sessions = frame[
        pd.to_datetime(frame["session_date"]).dt.date.between(start, end)
    ].reset_index(drop=True)
    if sessions.empty:
        raise RuntimeError("empty buy-and-hold window")
    entry = slipped_price(
        float(sessions.iloc[0]["open"]),
        1,
        "entry",
        friction_per_fill,
    )
    values = (sessions["close"] / entry).astype(float).tolist()
    terminal_fill = slipped_price(
        float(sessions.iloc[-1]["close"]),
        1,
        "exit",
        friction_per_fill,
    )
    equity = terminal_fill / entry
    values[-1] = equity
    return {
        "entry_session": str(sessions.iloc[0]["session_date"]),
        "exit_session": str(sessions.iloc[-1]["session_date"]),
        "net_return_pct": (equity - 1.0) * 100.0,
        "daily_close_mdd_pct": max_drawdown([1.0, *values]),
        "annualized_return_pct": annualized_return(
            equity,
            (
                date.fromisoformat(str(sessions.iloc[-1]["session_date"]))
                - date.fromisoformat(str(sessions.iloc[0]["session_date"]))
            ).days
            + 1,
        ),
        "friction_per_fill": friction_per_fill,
    }


def recent_slice_starts(end: date) -> dict[str, date]:
    end_ts = pd.Timestamp(end)
    return {
        "1d": end,
        "7d": end - timedelta(days=6),
        "1m": (end_ts - pd.DateOffset(months=1)).date(),
        "3m": (end_ts - pd.DateOffset(months=3)).date(),
        "6m": (end_ts - pd.DateOffset(months=6)).date(),
        "1y": (end_ts - pd.DateOffset(years=1)).date(),
    }


def write_data_lake_raw(frame: pd.DataFrame) -> dict[str, Any]:
    paths: list[str] = []
    for _, row in frame.iterrows():
        partition_date = pd.Timestamp(row["ts"]).date().isoformat()
        path = (
            DATA_ROOT
            / f"exchange={EXCHANGE}"
            / f"market_type={MARKET_TYPE}"
            / f"timeframe={TIMEFRAME}"
            / f"source={SOURCE}"
            / f"date={partition_date}"
            / f"symbol={SYMBOL}.parquet"
        )
        output = pd.DataFrame(
            [
                {
                    **row.to_dict(),
                    "exchange": EXCHANGE,
                    "symbol": SYMBOL,
                    "market_type": MARKET_TYPE,
                    "timeframe": TIMEFRAME,
                    "source": SOURCE,
                    "source_dataset_identity": "Eastmoney secid=1.000300 klt=101 fqt=0",
                    "quality_status": "raw_unaccepted",
                }
            ]
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        output.to_parquet(temporary, index=False)
        temporary.replace(path)
        paths.append(str(path.relative_to(ROOT)))
    return {
        "root": str(
            (
                DATA_ROOT
                / f"exchange={EXCHANGE}"
                / f"market_type={MARKET_TYPE}"
                / f"timeframe={TIMEFRAME}"
                / f"source={SOURCE}"
            ).relative_to(ROOT)
        ),
        "partitions_written": len(paths),
        "first_partition": paths[0],
        "last_partition": paths[-1],
        "quality_status": "raw_unaccepted",
    }


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return sanitize(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(path: Path, payload: dict[str, Any], *, force: bool) -> str:
    if path.exists() and not force:
        raise RuntimeError(f"artifact exists; use --force: {path}")
    encoded = (
        json.dumps(
            sanitize(payload),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode()
        + b"\n"
    )
    digest = sha256_bytes(encoded)
    atomic_write(path, encoded)
    atomic_write(
        Path(f"{path}.sha256"),
        f"{digest}  {path.name}\n".encode(),
    )
    return digest


def self_test() -> None:
    assert rsi_value(1.0, 0.0) == 100.0
    assert rsi_value(0.0, 0.0) == 50.0
    assert slipped_price(100.0, 1, "entry", 0.001) == 100.1
    assert slipped_price(100.0, -1, "entry", 0.001) == 99.9
    assert max_drawdown([1.0, 1.2, 0.9]) == -25.0
    dates = pd.bdate_range("2024-01-02", periods=40, tz="Asia/Shanghai")
    closes = np.linspace(100.0, 120.0, len(dates))
    synthetic = pd.DataFrame(
        {
            "session_date": dates.date.astype(str),
            "ts": dates.tz_convert("UTC"),
            "open": closes - 0.2,
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": 1.0,
            "amount": 1.0,
        }
    )
    result = run_backtest(
        synthetic,
        start=date(2024, 1, 10),
        end=date(2024, 2, 26),
        friction_per_fill=0.0,
    )
    assert result["metrics"]["sessions"] > 20
    assert result["metrics"]["daily_ohlc_mdd_pct"] <= 0.0


def main() -> None:
    args = parse_args()
    if args.self_test:
        self_test()
        print("self-test: PASS")
        return
    if not args.run:
        raise SystemExit("use --run or --self-test")
    if args.start >= args.end:
        raise ValueError("--start must be earlier than --end")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    fetch_start = args.start - timedelta(days=WARMUP_CALENDAR_DAYS)
    suffix = args.end.isoformat()
    eastmoney_raw_path = (
        ARTIFACT_DIR / f"csi300_eastmoney_1d_raw_{suffix}.json"
    )
    yahoo_raw_path = ARTIFACT_DIR / f"csi300_yahoo_1d_crosscheck_{suffix}.json"
    source_csv_path = ARTIFACT_DIR / f"csi300_eastmoney_1d_{suffix}.csv"
    trades_csv_path = (
        ARTIFACT_DIR / f"csi300_1d_hype_ma7_v7_1_trades_{suffix}.csv"
    )
    path_csv_path = (
        ARTIFACT_DIR / f"csi300_1d_hype_ma7_v7_1_path_{suffix}.csv"
    )
    output_path = (
        ARTIFACT_DIR / f"csi300_1d_hype_ma7_v7_1_transfer_{suffix}.json"
    )

    primary_url = eastmoney_url(fetch_start, args.end)
    primary_content = retained_fetch(
        primary_url,
        eastmoney_raw_path,
        refresh=args.refresh,
        force=args.force,
    )
    frame, quality = parse_eastmoney(primary_content)
    if quality["status"] != "PASS_SOURCE_LEVEL":
        raise RuntimeError(f"source-level data quality failed: {quality}")
    if args.end.isoformat() not in set(frame["session_date"]):
        raise RuntimeError(f"terminal session missing: {args.end}")

    secondary_url = yahoo_url(fetch_start, args.end)
    secondary_content = retained_fetch(
        secondary_url,
        yahoo_raw_path,
        refresh=args.refresh,
        force=args.force,
    )
    yahoo = parse_yahoo(secondary_content)
    crosscheck = cross_source_check(frame, yahoo)
    lake_manifest = write_data_lake_raw(frame)

    base = run_backtest(
        frame,
        start=args.start,
        end=args.end,
        friction_per_fill=BASE_FRICTION,
    )
    stress = run_backtest(
        frame,
        start=args.start,
        end=args.end,
        friction_per_fill=STRESS_FRICTION,
    )
    lag = run_backtest(
        frame,
        start=args.start,
        end=args.end,
        friction_per_fill=BASE_FRICTION,
        signal_lag_sessions=1,
    )
    long_only = run_backtest(
        frame,
        start=args.start,
        end=args.end,
        friction_per_fill=BASE_FRICTION,
        allow_short=False,
    )
    short_only = run_backtest(
        frame,
        start=args.start,
        end=args.end,
        friction_per_fill=BASE_FRICTION,
        allow_long=False,
    )
    benchmark = buy_and_hold(frame, args.start, args.end)
    stress_benchmark = buy_and_hold(
        frame,
        args.start,
        args.end,
        friction_per_fill=STRESS_FRICTION,
    )
    slices = {
        label: run_backtest(
            frame,
            start=max(args.start, slice_start),
            end=args.end,
            friction_per_fill=BASE_FRICTION,
        )["metrics"]
        for label, slice_start in recent_slice_starts(args.end).items()
    }
    year_rows = []
    for year in range(args.start.year, args.end.year + 1):
        year_start = max(args.start, date(year, 1, 1))
        year_end = min(args.end, date(year, 12, 31))
        if year_start <= year_end:
            year_rows.append(
                {
                    "year": year,
                    **run_backtest(
                        frame,
                        start=year_start,
                        end=year_end,
                        friction_per_fill=BASE_FRICTION,
                    )["metrics"],
                }
            )

    frame.to_csv(source_csv_path, index=False)
    pd.DataFrame(base["trades"]).to_csv(trades_csv_path, index=False)
    pd.DataFrame(base["path"]).to_csv(path_csv_path, index=False)

    payload = {
        "schema": "csi300-1d-hype-ma7-v7-1-transfer-v1",
        "status": "COMPLETED_DIAGNOSTIC",
        "run_date": RUN_DATE,
        "generated_utc": datetime.now(tz=UTC).isoformat(),
        "identity": {
            "family": "CSI300-1D-HYPE-MA7-V7.1-Transfer",
            "source_version": "HYPE-1D-MA7-Asymmetric-Body-Trend-V7.1",
            "instrument": "CSI 300 price index",
            "exchange_identity": EXCHANGE,
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "study_window": [args.start.isoformat(), args.end.isoformat()],
            "position_target": "fixed 1x index-path exposure",
            "registration": False,
            "promotion": False,
            "live_ready": False,
        },
        "data": {
            "primary_url": primary_url,
            "primary_raw_path": str(eastmoney_raw_path.relative_to(ROOT)),
            "primary_raw_sha256": sha256_bytes(primary_content),
            "secondary_url": secondary_url,
            "secondary_raw_path": str(yahoo_raw_path.relative_to(ROOT)),
            "secondary_raw_sha256": sha256_bytes(secondary_content),
            "quality": quality,
            "cross_source_check": crosscheck,
            "lake_manifest": lake_manifest,
        },
        "execution_contract": {
            "daily_signal": "closed Asia/Shanghai regular-session daily bar",
            "entry_and_soft_exit": "next session open",
            "intraday_protection": (
                "daily OHLC adapter; gap-through fills at open, otherwise stop; "
                "within-session ordering is unavailable"
            ),
            "forced_short": (
                "after long protective stop, immediate same reference price if "
                "below previous complete session SMA7; daily-only approximation"
            ),
            "pehc": (
                "only pure profitable OAPP long exits arm the 8-session shadow; "
                "daily low approximates stop opportunity and next session open "
                "rechecks MA eligibility"
            ),
            "funding": "none",
            "dividends": "not applicable to price index; no total-return series",
            "base_cost": "zero-cost index-path diagnostic",
            "stress_cost": "10 bps adverse friction per fill",
            "known_blocker": (
                "no 1h path; not exact V7.1 execution parity and not a tradable "
                "ETF/futures backtest"
            ),
        },
        "parameters": {
            "sma_length": 7,
            "atr_length": 7,
            "rsi_length": 6,
            "long": {
                "entry_slope_lookback": 1,
                "entry_slope_min_atr": 0.02,
                "entry_buffer_atr": 0.0,
                "exit_buffer_atr": 0.75,
                "trail_atr": 1.5,
                "max_hold_sessions": 90,
                "cooldown_sessions": 2,
            },
            "short": {
                "entry_slope_lookback": 2,
                "entry_slope_min_atr": 0.02,
                "entry_buffer_atr": 0.10,
                "exit_buffer_atr": 0.75,
                "hard_stop_atr": 1.5,
                "trail_atr": 4.0,
                "max_hold_sessions": 20,
                "cooldown_sessions": 3,
            },
            "oapp": {
                "long_activation_atr": 0.5,
                "long_giveback": 0.10,
                "long_confirm_sessions": 2,
                "short_rsi_threshold_strictly_below": 20.0,
                "short_rsi_sessions": 2,
                "roundtrip_guard": 0.0028,
            },
            "pehc": {
                "enabled": True,
                "expiry_sessions": 8,
                "execution": "next_session_open_adapter",
            },
        },
        "results": {
            "base_zero_cost": base["metrics"],
            "stress_10bps_per_fill": stress["metrics"],
            "one_extra_session_lag": lag["metrics"],
            "long_only_zero_cost": long_only["metrics"],
            "short_only_zero_cost": short_only["metrics"],
            "buy_and_hold_price_index": benchmark,
            "buy_and_hold_10bps_per_fill": stress_benchmark,
            "excess_return_vs_buy_hold_pct": (
                base["metrics"]["net_return_pct"]
                - benchmark["net_return_pct"]
            ),
            "stress_excess_return_vs_buy_hold_pct": (
                stress["metrics"]["net_return_pct"]
                - stress_benchmark["net_return_pct"]
            ),
            "recent_slices_audit_only": slices,
            "calendar_year_cold_flat": year_rows,
        },
        "artifacts": {
            "source_csv": str(source_csv_path.relative_to(ROOT)),
            "trades_csv": str(trades_csv_path.relative_to(ROOT)),
            "path_csv": str(path_csv_path.relative_to(ROOT)),
        },
        "decision": (
            "TRANSFER_PASS_DIAGNOSTIC_ONLY"
            if base["metrics"]["net_return_pct"] > 0.0
            and base["metrics"]["net_return_pct"] > benchmark["net_return_pct"]
            and stress["metrics"]["net_return_pct"] > 0.0
            and stress["metrics"]["net_return_pct"]
            > stress_benchmark["net_return_pct"]
            and slices["1y"]["net_return_pct"] > 0.0
            else "TRANSFER_FAIL"
        ),
        "limitations": [
            "CSI 300 is a non-tradable price index; this is not IF futures or ETF 510300.",
            "Eastmoney rows remain raw_unaccepted because exchange-calendar, is_closed, trade_count and vwap provenance are incomplete.",
            "Daily OHLC cannot recover intraday stop order or PEHC opportunity ordering.",
            "Short exposure is only an index-path counterfactual; borrow, margin and futures basis are not modeled.",
            "Recent slices are audit-only and did not participate in parameter selection.",
        ],
    }
    digest = write_json(output_path, payload, force=args.force)
    print(
        json.dumps(
            {
                "output": str(output_path),
                "sha256": digest,
                "decision": payload["decision"],
                "base": base["metrics"],
                "stress": stress["metrics"],
                "buy_and_hold": benchmark,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
