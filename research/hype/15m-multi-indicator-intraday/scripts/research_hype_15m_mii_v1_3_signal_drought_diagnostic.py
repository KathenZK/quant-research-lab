from __future__ import annotations

import json
import sys
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import research_hype_15m_mii_v1_2_atr_bracket_exit as v12  # noqa: E402
import research_hype_15m_mii_v1_full_ablation as v1  # noqa: E402
from research_hype_15m_mii_search import (  # noqa: E402
    FAPI_KLINES_URL,
    INTERVAL,
    INTERVAL_MS,
    build_market_arrays,
    signal_state,
)


FAMILY = "HYPE-15M-Multi-Indicator-Intraday"
ALIAS = "HYPE-15M-MII"
VERSION = "HYPE-15M-MII-V1.3"
RUN_DATE = "2026-07-06"
FAMILY_DIR = Path("research/hype/15m-multi-indicator-intraday")
SCRIPT_PATH = FAMILY_DIR / "scripts" / "research_hype_15m_mii_v1_3_signal_drought_diagnostic.py"
ARTIFACTS_DIR = FAMILY_DIR / "artifacts"
NOTES_DIR = FAMILY_DIR / "notes"
SUMMARY_CSV_PATH = ARTIFACTS_DIR / "hype_15m_mii_v1_3_signal_drought_2026-07-06.csv"
JSON_PATH = ARTIFACTS_DIR / "hype_15m_mii_v1_3_signal_drought_2026-07-06.json"
MARKDOWN_PATH = NOTES_DIR / "hype-15m-mii-v1-3-signal-drought-2026-07-06.md"

SYMBOL = "HYPEUSDT"
FETCH_DAYS = 130
RECENT_WINDOWS: tuple[tuple[str, pd.Timedelta], ...] = (
    ("最近24h", pd.Timedelta(hours=24)),
    ("最近72h", pd.Timedelta(hours=72)),
    ("最近7d", pd.Timedelta(days=7)),
    ("最近15d", pd.Timedelta(days=15)),
    ("最近30d", pd.Timedelta(days=30)),
    ("最近90d", pd.Timedelta(days=90)),
)
HISTORICAL_WINDOWS: tuple[tuple[str, pd.Timestamp, pd.Timestamp], ...] = (
    (
        "历史高开单窗口_2025-05-30_to_2025-06-30",
        pd.Timestamp("2025-05-30T10:30:00Z"),
        pd.Timestamp("2025-06-30T00:00:00Z"),
    ),
    (
        "历史中段_2025-07-01_to_2026-03-31",
        pd.Timestamp("2025-07-01T00:00:00Z"),
        pd.Timestamp("2026-03-31T00:00:00Z"),
    ),
    (
        "近期数据湖_2026-04-01_to_2026-06-26",
        pd.Timestamp("2026-04-01T00:00:00Z"),
        pd.Timestamp("2026-06-26T04:15:00Z"),
    ),
)


def fetch_recent_fapi_klines() -> pd.DataFrame:
    end_ms = int(pd.Timestamp.now("UTC").timestamp() * 1000)
    start_ms = end_ms - int(pd.Timedelta(days=FETCH_DAYS).total_seconds() * 1000)
    rows: list[list[Any]] = []
    while start_ms <= end_ms:
        params = urlencode(
            {
                "symbol": SYMBOL,
                "interval": INTERVAL,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": 1500,
            }
        )
        request = Request(
            f"{FAPI_KLINES_URL}?{params}",
            headers={"User-Agent": "quant-research-lab/0.1"},
        )
        with urlopen(request, timeout=45) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        if not payload:
            break
        rows.extend(payload)
        next_start = int(payload[-1][0]) + INTERVAL_MS
        if next_start <= start_ms:
            break
        start_ms = next_start
        time.sleep(0.05)
    if not rows:
        raise RuntimeError("Binance FAPI returned no HYPEUSDT rows.")
    return normalize_fapi_rows(rows)


def normalize_fapi_rows(rows: list[list[Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(
        rows,
        columns=[
            "ts",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trade_count",
            "taker_base",
            "taker_quote",
            "ignore",
        ],
    )
    frame = frame[
        [
            "ts",
            "close_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
            "trade_count",
        ]
    ].copy()
    frame["ts"] = pd.to_datetime(frame["ts"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    for column in ["open", "high", "low", "close", "volume", "quote_volume", "trade_count"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["exchange"] = "binance"
    frame["symbol"] = "HYPE/USDT:USDT"
    frame["market_type"] = "perp"
    frame["timeframe"] = "15m"
    frame["source"] = "binance_futures_kline_api_direct"
    frame["is_closed"] = frame["close_time"] < pd.Timestamp.now("UTC")
    frame["vwap"] = np.where(
        frame["volume"].to_numpy("float64") > 0,
        frame["quote_volume"].to_numpy("float64") / frame["volume"].to_numpy("float64"),
        np.nan,
    )
    frame = (
        frame.loc[frame["is_closed"]]
        .drop(columns=["close_time"])
        .drop_duplicates("ts")
        .sort_values("ts")
        .reset_index(drop=True)
    )
    return frame


def load_data_lake_context() -> tuple[v12.evolution.EvalContext, dict[str, Any], dict[str, Any]]:
    return v12.build_context()


def build_context(frame: pd.DataFrame) -> v12.evolution.EvalContext:
    features = v12.evolution.add_rsi_features(v12.evolution.add_features(frame, []))
    return v12.evolution.EvalContext(
        features=features,
        market=build_market_arrays(features),
        start_ts=pd.Timestamp(features["ts"].min()),
        end_ts=pd.Timestamp(features["ts"].max()) + pd.Timedelta(minutes=15),
        signal_cache={},
        trade_cache=OrderedDict(),
    )


def data_quality(frame: pd.DataFrame) -> dict[str, Any]:
    expected = pd.Timedelta(minutes=15)
    gaps = frame["ts"].diff().dropna()
    numeric_columns = ["open", "high", "low", "close", "volume", "quote_volume", "trade_count", "vwap"]
    invalid_ohlc = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
        | (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (frame["volume"] < 0)
        | (frame["quote_volume"] < 0)
        | (frame["trade_count"] < 0)
        | (
            frame["volume"].gt(0)
            & (
                frame["vwap"].lt(frame["low"])
                | frame["vwap"].gt(frame["high"])
            )
        )
    )
    report = {
        "source": "binance_futures_kline_api_direct",
        "symbol": SYMBOL,
        "timeframe": "15m",
        "rows": int(len(frame)),
        "first_ts": frame["ts"].min().isoformat() if len(frame) else None,
        "last_ts": frame["ts"].max().isoformat() if len(frame) else None,
        "gap_count": int(gaps.ne(expected).sum()),
        "duplicates": int(frame["ts"].duplicated().sum()),
        "critical_nulls": int(frame[["ts", *numeric_columns, "source", "is_closed"]].isna().sum().sum()),
        "invalid_ohlc_rows": int(invalid_ohlc.sum()),
        "open_bar_rows": int((~frame["is_closed"].astype(bool)).sum()),
        "unknown_source_rows": int(frame["source"].astype(str).str.strip().eq("").sum()),
    }
    report["quality_gate_pass"] = not any(
        [
            report["rows"] == 0,
            report["gap_count"],
            report["duplicates"],
            report["critical_nulls"],
            report["invalid_ohlc_rows"],
            report["open_bar_rows"],
            report["unknown_source_rows"],
        ]
    )
    return report


def raw_signal_mask(features: pd.DataFrame) -> pd.Series:
    rsi = features["rsi7"]
    long_raw = (rsi > 40.0) & (rsi.shift(1) <= 40.0)
    short_raw = (rsi < 60.0) & (rsi.shift(1) >= 60.0)
    return (long_raw | short_raw).fillna(False)


def direction_series(features: pd.DataFrame) -> pd.Series:
    rsi = features["rsi7"]
    direction = pd.Series(0, index=features.index, dtype="int64")
    direction[(rsi > 40.0) & (rsi.shift(1) <= 40.0)] = 1
    direction[(rsi < 60.0) & (rsi.shift(1) >= 60.0)] = -1
    return direction


def final_signal_indices(context: v12.evolution.EvalContext) -> set[int]:
    state = signal_state(context.features, v12.BASE_CONFIG.signal)
    raw_trades = v12.simulate_atr_bracket_trades(context, v12.AtrBracketCandidate(
        label="atr96_tp1p25x_sl5x_hold24",
        family="atr_bracket",
        atr_window=96,
        tp_atr_mult=1.25,
        sl_atr_mult=5.0,
        max_hold_bars=24,
    ), entry_delay_bars=1)
    selected = v1.selected_trades_live(raw_trades, v12.BASE_CONFIG.filter)
    return {int(trade.signal_i) for trade in selected}


def window_stats(
    context: v12.evolution.EvalContext,
    *,
    label: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    source_scope: str,
) -> dict[str, Any]:
    features = context.features
    raw_all = raw_signal_mask(features)
    direction_all = direction_series(features)
    window_mask = (features["ts"] >= start_ts) & (features["ts"] < end_ts)
    window = features.loc[window_mask].copy()
    if window.empty:
        return {
            "source_scope": source_scope,
            "window": label,
            "start_ts": start_ts.isoformat(),
            "end_ts": end_ts.isoformat(),
            "bars": 0,
        }
    raw = raw_all.loc[window.index]
    direction = direction_all.loc[window.index]
    atr_ok = window["atr_pct96"].between(0.0075, 0.028, inclusive="both")
    rvol_ok = window["rvol96"] >= 1.0
    macd_hist = window["macd_12_26_9_hist"]
    macd_ok = (direction * macd_hist) >= 0
    final_indices = final_signal_indices(context)
    final_mask = window.index.to_series().map(lambda idx: int(idx) in final_indices)
    raw_atr = raw & atr_ok
    raw_atr_rvol = raw_atr & rvol_ok
    raw_atr_rvol_macd = raw_atr_rvol & macd_ok
    atr_values = window["atr_pct96"].dropna()
    rvol_values = window["rvol96"].dropna()
    raw_rows = window.loc[raw]
    last_final = window.loc[final_mask]
    return {
        "source_scope": source_scope,
        "window": label,
        "start_ts": pd.Timestamp(window["ts"].min()).isoformat(),
        "end_ts": (pd.Timestamp(window["ts"].max()) + pd.Timedelta(minutes=15)).isoformat(),
        "bars": int(len(window)),
        "raw_rsi_cross": int(raw.sum()),
        "raw_pass_atr": int(raw_atr.sum()),
        "raw_pass_atr_rvol": int(raw_atr_rvol.sum()),
        "raw_pass_atr_rvol_macd": int(raw_atr_rvol_macd.sum()),
        "final_signals": int(final_mask.sum()),
        "atr_ok_bars": int(atr_ok.sum()),
        "atr_ok_rate_pct": float(atr_ok.mean() * 100.0),
        "rvol_ok_bars": int(rvol_ok.sum()),
        "rvol_ok_rate_pct": float(rvol_ok.mean() * 100.0),
        "atr_pct96_latest": float(atr_values.iloc[-1]) if len(atr_values) else None,
        "atr_pct96_median": float(atr_values.median()) if len(atr_values) else None,
        "atr_pct96_p25": float(atr_values.quantile(0.25)) if len(atr_values) else None,
        "atr_pct96_p75": float(atr_values.quantile(0.75)) if len(atr_values) else None,
        "rvol96_median": float(rvol_values.median()) if len(rvol_values) else None,
        "last_raw_signal_ts": pd.Timestamp(raw_rows["ts"].iloc[-1]).isoformat() if len(raw_rows) else None,
        "last_final_signal_ts": pd.Timestamp(last_final["ts"].iloc[-1]).isoformat() if len(last_final) else None,
    }


def evaluate() -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    recent_frame = fetch_recent_fapi_klines()
    recent_quality = data_quality(recent_frame)
    if not recent_quality["quality_gate_pass"]:
        raise ValueError(f"recent data-quality blocker: {json.dumps(recent_quality, ensure_ascii=False)}")
    recent_context = build_context(recent_frame)
    rows: list[dict[str, Any]] = []
    for label, duration in RECENT_WINDOWS:
        end_ts = recent_context.end_ts
        start_ts = max(recent_context.start_ts, end_ts - duration)
        rows.append(
            window_stats(
                recent_context,
                label=label,
                start_ts=start_ts,
                end_ts=end_ts,
                source_scope="recent_binance_api",
            )
        )

    lake_context, metadata, lake_quality = load_data_lake_context()
    for label, start_ts, end_ts in HISTORICAL_WINDOWS:
        rows.append(
            window_stats(
                lake_context,
                label=label,
                start_ts=start_ts,
                end_ts=end_ts,
                source_scope="standard_data_lake",
            )
        )
    return pd.DataFrame(rows), recent_quality, lake_quality


def fmt_pct(value: Any, digits: int = 3) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "-"
    return f"{float(value) * 100.0:.{digits}f}%"


def table(rows: pd.DataFrame) -> list[str]:
    lines = [
        "| 数据源 | 窗口 | bars | RSI raw | 过 ATR | 过 ATR+RVOL | 过 ATR+RVOL+MACD | 最终信号 | ATR96% 中位/最新 | ATR 过线率 | 最后最终信号 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for row in rows.to_dict(orient="records"):
        median_latest = (
            f"{fmt_pct(row.get('atr_pct96_median'))} / {fmt_pct(row.get('atr_pct96_latest'))}"
        )
        last_final = row.get("last_final_signal_ts")
        if last_final is None or pd.isna(last_final):
            last_final = "-"
        lines.append(
            f"| `{row['source_scope']}` | `{row['window']}` | `{int(row.get('bars', 0))}` | "
            f"`{int(row.get('raw_rsi_cross', 0))}` | `{int(row.get('raw_pass_atr', 0))}` | "
            f"`{int(row.get('raw_pass_atr_rvol', 0))}` | `{int(row.get('raw_pass_atr_rvol_macd', 0))}` | "
            f"`{int(row.get('final_signals', 0))}` | `{median_latest}` | "
            f"`{float(row.get('atr_ok_rate_pct', 0.0)):.2f}%` | "
            f"`{last_final}` |"
        )
    return lines


def render_markdown(rows: pd.DataFrame, recent_quality: dict[str, Any], lake_quality: dict[str, Any]) -> str:
    recent_90 = rows.loc[
        rows["source_scope"].eq("recent_binance_api") & rows["window"].eq("最近90d")
    ].iloc[0]
    recent_7 = rows.loc[
        rows["source_scope"].eq("recent_binance_api") & rows["window"].eq("最近7d")
    ].iloc[0]
    recent_72h = rows.loc[
        rows["source_scope"].eq("recent_binance_api") & rows["window"].eq("最近72h")
    ].iloc[0]
    recent_30 = rows.loc[
        rows["source_scope"].eq("recent_binance_api") & rows["window"].eq("最近30d")
    ].iloc[0]
    hist_early = rows.loc[
        rows["window"].eq("历史高开单窗口_2025-05-30_to_2025-06-30")
    ].iloc[0]
    lines = [
        f"# HYPE-15M-MII V1.3 近期不开单诊断 {RUN_DATE}",
        "",
        f"Family：`{FAMILY}`（alias：`{ALIAS}`）",
        "",
        "## 结论",
        "",
        "这次直接按当前 Binance futures public kline 重新拆了 `V1.3` 的信号漏斗。结论是：近期不开单主要是波动率过滤卡住，尤其 `ATR96% >= 0.75%`；不是 runner 线上漏单。",
        "",
        (
            f"- 最近 90 天 Binance API 数据里，`RSI raw cross` 有 `{int(recent_90['raw_rsi_cross'])}` 次，"
            f"但通过 `ATR96% >= 0.75%` 的只有 `{int(recent_90['raw_pass_atr'])}` 次，"
            f"最终信号 `{int(recent_90['final_signals'])}` 次。"
        ),
        (
            f"- 最近 7 天 `RSI raw cross` 有 `{int(recent_7['raw_rsi_cross'])}` 次，"
            f"但 `ATR96%` 过线 `{int(recent_7['raw_pass_atr'])}` 次，最终信号 `{int(recent_7['final_signals'])}` 次。"
        ),
        (
            f"- 最近 72 小时 `RSI raw cross` 仍有 `{int(recent_72h['raw_rsi_cross'])}` 次，"
            f"但 `ATR96%` 过线 `{int(recent_72h['raw_pass_atr'])}` 次；最新 `ATR96%` 为 "
            f"`{fmt_pct(recent_72h['atr_pct96_latest'])}`，离 `0.75%` 门槛仍有距离。"
        ),
        (
            f"- 历史高开单窗口（2025-05-30 到 2025-06-30）最终信号 `{int(hist_early['final_signals'])}` 次，"
            f"ATR96% 中位 `{fmt_pct(hist_early['atr_pct96_median'])}`；最近 90 天 ATR96% 中位 "
            f"`{fmt_pct(recent_90['atr_pct96_median'])}`，明显低于 `0.75%` 门槛。"
        ),
        "",
        (
            "所以，最近三个月相对早期高波动窗口确实更低波动；但更准确地说，"
            f"最近 30 天中位 `ATR96%` 仍有 `{fmt_pct(recent_30['atr_pct96_median'])}`，"
            "真正造成当前不开单的是 6 月底以后、尤其最近 72 小时的波动率塌到门槛以下。"
            "策略现在处在“看见 RSI 反转，但波动率不允许交易”的状态。若为了让它现在多开单，只能放宽 "
            "`min_atr_pct96` 或改信号/出场，但那就不是当前 SPEC 的 `V1.3`，且之前 ATR/RVOL 消融已经显示简单放开过滤会显著伤害收益和回撤。"
        ),
        "",
        "## 信号漏斗",
        "",
        *table(rows),
        "",
        "## 数据质量",
        "",
        f"- Recent Binance API：`{recent_quality['first_ts']}` 到 `{recent_quality['last_ts']}`，rows `{recent_quality['rows']}`，quality gate `{recent_quality['quality_gate_pass']}`。",
        f"- Standard data lake：`{lake_quality['first_ts']}` 到 `{lake_quality['last_ts']}`，rows `{lake_quality['rows']}`，quality gate `{lake_quality['quality_gate_pass']}`。",
        "",
        "## 状态",
        "",
        "本诊断只解释 `V1.3` 近期不开单原因，不改变 `NO-GO / not live-ready` 状态。任何降低 `min_atr_pct96`、降低 `min_rvol96` 或去掉 `MACD` 的尝试都必须重新回测 K+1/K+2、资金费、滑点和 live-executable 状态机。",
        "",
        "## 产物",
        "",
        f"- 脚本：`{SCRIPT_PATH}`",
        f"- CSV：`{SUMMARY_CSV_PATH}`",
        f"- JSON：`{JSON_PATH}`",
    ]
    return "\n".join(lines) + "\n"


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [json_safe(child) for child in value]
    if isinstance(value, tuple):
        return [json_safe(child) for child in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def main() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    rows, recent_quality, lake_quality = evaluate()
    rows.to_csv(SUMMARY_CSV_PATH, index=False)
    MARKDOWN_PATH.write_text(render_markdown(rows, recent_quality, lake_quality), encoding="utf-8")
    JSON_PATH.write_text(
        json.dumps(
            json_safe(
                {
                    "family": FAMILY,
                    "alias": ALIAS,
                    "version": VERSION,
                    "run_date": RUN_DATE,
                    "status": "signal_drought_diagnostic_not_promoted",
                    "recent_data_quality": recent_quality,
                    "lake_data_quality": lake_quality,
                    "rows": rows.to_dict(orient="records"),
                    "outputs": {
                        "markdown": str(MARKDOWN_PATH),
                        "csv": str(SUMMARY_CSV_PATH),
                    },
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(rows.to_string(index=False))
    print(f"Wrote {MARKDOWN_PATH}")


if __name__ == "__main__":
    main()
