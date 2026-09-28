from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    ROOT
    / "research/hype/15m-candle-count-reversal/scripts/"
    "research_hype_cc_v35_maker_entry_audit.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("hype_cc_maker_audit", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _frame(rows: int = 24) -> pd.DataFrame:
    index = pd.date_range("2026-08-01", periods=rows, freq="15min", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "mark_high": 101.0,
            "mark_low": 99.0,
            "funding_rate": 0.0,
            "signal": 0,
            "atr_pct_672": 0.006,
            "trend_return_96": 0.0,
            "limit_low_10": 95.0,
            "limit_high_10": 105.0,
            "ema24": 101.0,
            "ema672": 100.0,
        },
        index=index,
    )
    return frame


def _costs(module):
    return module.CostModel("test", fee_rate=0.0, taker_slippage_rate=0.0)


def test_maker_starts_after_signal_bar_and_records_fill_delay() -> None:
    module = _load_module()
    frame = _frame(8)
    frame.iloc[1, frame.columns.get_loc("signal")] = 1
    frame.iloc[2, frame.columns.get_loc("low")] = 96.0
    frame.iloc[3, frame.columns.get_loc("low")] = 95.0
    result = module.run_backtest(
        frame,
        variant=module.Variant("maker", "maker_extreme", "touch"),
        costs=_costs(module),
        tick_size=0.1,
        trade_start=frame.index[0],
        trade_end=frame.index[-1],
    )
    assert result.metrics["entries"] == 1
    assert result.trades.iloc[0].entry_ts == frame.index[3]
    assert result.trades.iloc[0].entry_price == 95.0
    assert result.trades.iloc[0].fill_delay_bars == 2


def test_maker_expires_after_sixteen_eligible_bars() -> None:
    module = _load_module()
    frame = _frame(22)
    frame.iloc[1, frame.columns.get_loc("signal")] = 1
    frame.loc[:, "low"] = 96.0
    result = module.run_backtest(
        frame,
        variant=module.Variant("maker", "maker_extreme", "touch"),
        costs=_costs(module),
        tick_size=0.1,
        trade_start=frame.index[0],
        trade_end=frame.index[-1],
    )
    assert result.metrics["entries"] == 0
    assert result.metrics["expired_orders"] == 1


def test_trade_through_requires_one_tick_beyond_limit() -> None:
    module = _load_module()
    frame = _frame(5)
    frame.iloc[1, frame.columns.get_loc("signal")] = 1
    frame.iloc[2:, frame.columns.get_loc("low")] = 95.0
    touch = module.run_backtest(
        frame,
        variant=module.Variant("touch", "maker_extreme", "touch"),
        costs=_costs(module),
        tick_size=0.1,
        trade_start=frame.index[0],
        trade_end=frame.index[-1],
    )
    strict = module.run_backtest(
        frame,
        variant=module.Variant(
            "strict", "maker_extreme", "trade_through_1tick"
        ),
        costs=_costs(module),
        tick_size=0.1,
        trade_start=frame.index[0],
        trade_end=frame.index[-1],
    )
    assert touch.metrics["entries"] == 1
    assert strict.metrics["entries"] == 0


def test_short_only_ma_filter_blocks_short_but_not_long() -> None:
    module = _load_module()
    frame = _frame(5)
    short_allowed, short_reason = module._signal_allowed(
        frame, 1, -1, "ema24_672_short_only"
    )
    long_allowed, long_reason = module._signal_allowed(
        frame, 1, 1, "ema24_672_short_only"
    )
    assert not short_allowed and short_reason == "ma_filter"
    assert long_allowed and long_reason is None


def test_same_bar_maker_fill_uses_conservative_stop_first() -> None:
    module = _load_module()
    frame = _frame(5)
    frame.iloc[1, frame.columns.get_loc("signal")] = 1
    frame.iloc[1, frame.columns.get_loc("limit_low_10")] = 100.0
    frame.iloc[2, frame.columns.get_loc("low")] = 90.0
    frame.iloc[2, frame.columns.get_loc("mark_low")] = 90.0
    frame.iloc[2, frame.columns.get_loc("high")] = 110.0
    frame.iloc[2, frame.columns.get_loc("mark_high")] = 110.0
    result = module.run_backtest(
        frame,
        variant=module.Variant("maker", "maker_extreme", "touch"),
        costs=_costs(module),
        tick_size=0.1,
        trade_start=frame.index[0],
        trade_end=frame.index[-1],
    )
    assert result.trades.iloc[0].exit_reason == "stop"
    assert bool(result.trades.iloc[0].same_bar_exit)

