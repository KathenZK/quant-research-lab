from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = (
    ROOT
    / "research/_shared-kernels/ema-trend-breakout/v2/engine.py"
)
SCRIPT_DIR = (
    ROOT
    / "research/hype/15m-ema-trend-breakout/scripts"
)


def _load_path(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ENGINE = _load_path("ema_trend_breakout_v1", ENGINE_PATH)


def _load_current_hype_modules() -> dict[str, Any]:
    path = str(SCRIPT_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    names = {
        "base": "research_hype_ema_tb_v35_profit_floor",
        "signals": "research_hype_ema_tb_v35_full_ablation_recent_tune",
        "cooldown": "research_hype_ema_tb_v35_cooldown4",
        "v39": "research_hype_ema_tb_v39_full_ablation",
        "data": "research_hype_ema_tb_v35_h4_rsi6_entry_filter",
    }
    return {
        key: importlib.import_module(module_name)
        for key, module_name in names.items()
    }


def _hype_like_fixture(rows: int = 3600) -> pd.DataFrame:
    rng = np.random.default_rng(20260717)
    ts = pd.date_range("2025-01-01", periods=rows, freq="15min", tz="UTC")
    regime = np.where(
        (np.arange(rows) // 360) % 2 == 0,
        0.0012,
        -0.0011,
    )
    log_return = (
        regime
        + 0.0018 * np.sin(np.arange(rows) / 17.0)
        + rng.normal(0.0, 0.0035, rows)
    )
    close = 25.0 * np.exp(np.cumsum(log_return))
    open_ = np.r_[close[0], close[:-1]]
    spread = 0.0025 + rng.random(rows) * 0.004
    high = np.maximum(open_, close) * (1.0 + spread)
    low = np.minimum(open_, close) * (1.0 - spread)
    volume = 1_000.0 * (1.0 + 0.2 * np.sin(np.arange(rows) / 11.0))
    volume *= np.where(np.arange(rows) % 29 == 0, 2.2, 1.0)
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=ts,
    )


def _kernel_config_from_legacy(legacy_config: Any, **changes: Any) -> Any:
    values = asdict(legacy_config)
    values.update(
        {
            "cooldown_bars": 1,
            "cost_mode": "legacy_cost",
            "execution_mode": "legacy_exact",
        }
    )
    values.update(changes)
    return ENGINE.V35Config(**values)


def test_features_and_signals_match_current_hype_script() -> None:
    modules = _load_current_hype_modules()
    base = modules["base"]
    signals = modules["signals"]
    v39 = modules["v39"]
    market = _hype_like_fixture()
    legacy_config = replace(v39.v39_config(), long_vol_min=0.25)
    legacy_flags = v39.v39_flags()
    kernel_config = _kernel_config_from_legacy(legacy_config)
    kernel_flags = ENGINE.SignalFlags(**asdict(legacy_flags))

    legacy_features = signals.build_signals(
        base.build_features(market, legacy_config),
        legacy_config,
        legacy_flags,
    )
    kernel_features = ENGINE.build_signals(
        ENGINE.build_features(market, kernel_config),
        kernel_config,
        kernel_flags,
    )

    feature_columns = [
        "atr",
        "ema_fast",
        "ema_slow",
        "ema_spread",
        "adx",
        "plus_di",
        "minus_di",
        "volume_surge",
        "h1_adx",
        "h1_plus_di",
        "h1_minus_di",
        "h1_ema_spread",
    ]
    pd.testing.assert_frame_equal(
        legacy_features[feature_columns],
        kernel_features[feature_columns],
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        legacy_features[["long_signal", "short_signal"]],
        kernel_features[["long_signal", "short_signal"]],
        check_exact=True,
    )
    assert int(
        kernel_features[["long_signal", "short_signal"]].to_numpy().sum()
    ) > 0


def test_legacy_mode_matches_current_hype_trade_path_and_equity() -> None:
    modules = _load_current_hype_modules()
    base = modules["base"]
    signals = modules["signals"]
    cooldown = modules["cooldown"]
    v39 = modules["v39"]
    market = _hype_like_fixture()
    funding = pd.Series(0.0, index=market.index, name="funding_rate")
    funding.iloc[::32] = 0.00005
    legacy_config = replace(v39.v39_config(), long_vol_min=0.25)
    legacy_flags = v39.v39_flags()
    legacy_features = signals.build_signals(
        base.build_features(market, legacy_config),
        legacy_config,
        legacy_flags,
    )
    legacy_run = cooldown.run_backtest(
        spec=cooldown.RunSpec(
            name="legacy_v40",
            cooldown_bars=1,
            use_rsi10_90=False,
        ),
        frame=market,
        funding=funding,
        features=legacy_features,
        config=legacy_config,
    )

    kernel_config = _kernel_config_from_legacy(legacy_config)
    kernel_features = ENGINE.build_signals(
        ENGINE.build_features(market, kernel_config),
        kernel_config,
        ENGINE.SignalFlags(**asdict(legacy_flags)),
    )
    kernel_run = ENGINE.run_backtest(
        "kernel_v40",
        market,
        funding,
        kernel_features,
        kernel_config,
    )
    report = ENGINE.parity_report(
        reference_features=legacy_features,
        candidate_features=kernel_features,
        reference_run=legacy_run,
        candidate_run=kernel_run,
    )

    assert len(kernel_run.trades) > 0
    assert report == {
        "signal_equal": True,
        "reference_trades": len(legacy_run.trades),
        "candidate_trades": len(legacy_run.trades),
        "trade_signatures_equal": True,
        "max_equity_diff": 0.0,
        "exact": True,
    }


def test_gap_open_mode_uses_worse_stop_fill_and_legacy_mode_does_not() -> None:
    ts = pd.date_range("2025-01-01", periods=9, freq="15min", tz="UTC")
    market = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0, 90.0, 90.0, 90.0, 90.0, 90.0],
            "high": [101.0, 101.0, 101.0, 101.0, 91.0, 91.0, 91.0, 91.0, 91.0],
            "low": [99.0, 99.0, 99.0, 99.0, 89.0, 89.0, 89.0, 89.0, 89.0],
            "close": [100.0, 100.0, 100.0, 100.0, 90.0, 90.0, 90.0, 90.0, 90.0],
            "volume": 1.0,
        },
        index=ts,
    )
    features = market.copy()
    features["atr"] = 1.0
    features["adx"] = 50.0
    features["long_signal"] = False
    features["short_signal"] = False
    features.loc[ts[1], "long_signal"] = True
    funding = pd.Series(0.0, index=ts)
    common = dict(
        warmup_bars=0,
        entry_delay_bars=2,
        hard_stop_atr=7.0,
        take_profit_atr=20.0,
        max_hold_bars=4,
        cooldown_bars=1,
        cost_mode="legacy_cost",
        trade_cost_rate=0.0,
    )
    gap_run = ENGINE.run_backtest(
        "gap",
        market,
        funding,
        features,
        ENGINE.V35Config(execution_mode="gap_open", **common),
    )
    legacy_run = ENGINE.run_backtest(
        "legacy",
        market,
        funding,
        features,
        ENGINE.V35Config(execution_mode="legacy_exact", **common),
    )

    assert float(gap_run.trades.iloc[0]["exit_price"]) == 90.0
    assert float(legacy_run.trades.iloc[0]["exit_price"]) == 93.0
    assert float(gap_run.equity_curve.iloc[-1]) < float(
        legacy_run.equity_curve.iloc[-1]
    )


def test_explicit_fee_and_slippage_are_separate_from_legacy_cost() -> None:
    legacy = ENGINE.v40_config(
        cost_mode="legacy_cost",
        trade_cost_rate=0.00085,
    )
    explicit = ENGINE.v40_config(
        cost_mode="explicit",
        fee_per_fill=0.001,
        adverse_slippage_per_fill=0.0004,
        fee_multiplier=2.0,
        slippage_multiplier=3.0,
    )
    assert legacy.cost_mode == "legacy_cost"
    assert legacy.trade_cost_rate == pytest.approx(0.00085)
    assert explicit.cost_mode == "explicit"
    assert explicit.fee_per_fill == pytest.approx(0.001)
    assert explicit.adverse_slippage_per_fill == pytest.approx(0.0004)
    assert ENGINE.explicit_cost_stress(explicit) == pytest.approx(
        {
            "fee_per_fill": 0.001,
            "fee_multiplier": 2.0,
            "effective_fee_per_fill": 0.002,
            "adverse_slippage_per_fill": 0.0004,
            "slippage_multiplier": 3.0,
            "effective_adverse_slippage_per_fill": 0.0012,
        }
    )


def test_fixed_allocation_is_not_derived_from_atr_target() -> None:
    fixed = ENGINE.V35Config(
        sizing_mode="fixed",
        fixed_allocation=1.0,
        long_target_atr_pct=0.00001,
        short_target_atr_pct=0.00001,
    )
    atr_risk = replace(
        fixed,
        sizing_mode="atr_risk",
        long_target_atr_pct=0.02,
        short_target_atr_pct=0.01,
    )

    assert ENGINE.allocation_for_entry(
        direction=1,
        entry_atr=1.0,
        entry_price=100.0,
        config=fixed,
    ) == 1.0
    assert ENGINE.allocation_for_entry(
        direction=-1,
        entry_atr=25.0,
        entry_price=100.0,
        config=fixed,
    ) == 1.0
    assert ENGINE.allocation_for_entry(
        direction=1,
        entry_atr=1.0,
        entry_price=100.0,
        config=atr_risk,
    ) == pytest.approx(2.0)
    assert ENGINE.allocation_for_entry(
        direction=1,
        entry_atr=4.0,
        entry_price=100.0,
        config=atr_risk,
    ) == pytest.approx(0.5)


def test_explicit_cost_multipliers_reduce_same_trade_equity() -> None:
    ts = pd.date_range("2025-01-01", periods=8, freq="15min", tz="UTC")
    market = pd.DataFrame(
        {
            "open": [100.0] * 8,
            "high": [101.0, 101.0, 101.0, 101.0, 110.0, 101.0, 101.0, 101.0],
            "low": [99.0] * 8,
            "close": [100.0] * 8,
            "volume": 1.0,
        },
        index=ts,
    )
    features = market.copy()
    features["atr"] = 1.0
    features["adx"] = 50.0
    features["long_signal"] = False
    features["short_signal"] = False
    features.loc[ts[1], "long_signal"] = True
    funding = pd.Series(0.0, index=ts)
    base_config = ENGINE.V35Config(
        warmup_bars=0,
        entry_delay_bars=2,
        max_hold_bars=4,
        sizing_mode="fixed",
        fixed_allocation=1.0,
        cost_mode="explicit",
        fee_per_fill=0.001,
        adverse_slippage_per_fill=0.0004,
        fee_multiplier=1.0,
        slippage_multiplier=1.0,
    )
    stressed_config = replace(
        base_config,
        fee_multiplier=2.0,
        slippage_multiplier=3.0,
    )
    base_run = ENGINE.run_backtest(
        "explicit_base",
        market,
        funding,
        features,
        base_config,
    )
    stressed_run = ENGINE.run_backtest(
        "explicit_stressed",
        market,
        funding,
        features,
        stressed_config,
    )

    assert base_run.trades["allocation"].tolist() == [1.0]
    assert stressed_run.trades["allocation"].tolist() == [1.0]
    assert float(stressed_run.equity_curve.iloc[-1]) < float(
        base_run.equity_curve.iloc[-1]
    )


@pytest.mark.local_data
def test_local_hype_v40_parity_when_data_lake_is_available() -> None:
    modules = _load_current_hype_modules()
    base = modules["base"]
    signals = modules["signals"]
    cooldown = modules["cooldown"]
    v39 = modules["v39"]
    data = modules["data"]
    warehouse = base.DuckDBWarehouse(
        base.DataLakeLayout.from_settings(base.load_settings(None))
    )
    try:
        market, funding, _quality = data.load_data(warehouse)
    except (FileNotFoundError, RuntimeError, ValueError):
        pytest.skip("local HYPE data lake is unavailable")

    legacy_config = replace(v39.v39_config(), long_vol_min=0.25)
    legacy_flags = v39.v39_flags()
    legacy_features = signals.build_signals(
        base.build_features(market, legacy_config),
        legacy_config,
        legacy_flags,
    )
    legacy_run = cooldown.run_backtest(
        spec=cooldown.RunSpec(
            name="legacy_v40_local",
            cooldown_bars=1,
            use_rsi10_90=False,
        ),
        frame=market,
        funding=funding,
        features=legacy_features,
        config=legacy_config,
    )
    kernel_config = _kernel_config_from_legacy(legacy_config)
    kernel_features = ENGINE.build_signals(
        ENGINE.build_features(market, kernel_config),
        kernel_config,
        ENGINE.SignalFlags(**asdict(legacy_flags)),
    )
    kernel_run = ENGINE.run_backtest(
        "kernel_v40_local",
        market,
        funding,
        kernel_features,
        kernel_config,
    )
    report = ENGINE.parity_report(
        reference_features=legacy_features,
        candidate_features=kernel_features,
        reference_run=legacy_run,
        candidate_run=kernel_run,
    )
    assert report["exact"], report
