from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_PATH = ROOT / (
    "research/hype/1d-ma7-asymmetric-body-trend/scripts/"
    "research_hype_1d_ma7_ctls_r6_intraday_context.py"
)


def load_research():
    spec = importlib.util.spec_from_file_location("ctls_r6_research_tested", RESEARCH_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def inputs(days: int = 30):
    daily_index = pd.date_range("2026-01-01", periods=days, tz="UTC", freq="D")
    close = 100.0 + np.arange(days) * 0.2
    daily = pd.DataFrame(
        {
            "open": close - 0.05,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "ma7": close - 0.1,
            "atr7": 1.0,
            "rsi6": 55.0,
        },
        index=daily_index,
    )
    hourly_index = pd.date_range(daily_index[0], periods=days * 24, tz="UTC", freq="h")
    hour = np.arange(days * 24)
    price = 100.0 + hour * 0.01
    hourly = pd.DataFrame(
        {
            "ts": hourly_index,
            "open": price,
            "high": price + 0.1,
            "low": price - 0.1,
            "close": price + 0.02,
            "volume": 1000.0 + hour,
        }
    )
    btc = hourly.copy()
    btc.loc[:, ["open", "high", "low", "close"]] *= 500.0
    funding = pd.DataFrame(
        {
            "ts": daily_index + pd.Timedelta(hours=8),
            "funding_rate": np.linspace(-0.0001, 0.0001, days),
        }
    )
    return daily, hourly, funding, btc


def test_day_context_requires_exactly_24_finite_bars() -> None:
    research = load_research()
    _, hourly, _, _ = inputs(2)
    with pytest.raises(RuntimeError, match="24 hourly"):
        research._day_context(hourly.iloc[:23], 1.0, "test")
    result = research._day_context(hourly.iloc[:24], 1.0, "test")
    assert result["test_positive_hour_share"] == 1.0
    assert 0.0 <= result["test_volume_concentration"] <= 1.0


def test_augmented_features_are_causal_under_future_change() -> None:
    research = load_research()
    r3 = research._load(research.R3_PATH, "ctls_r6_test_r3_causal")
    daily, hourly, funding, btc = inputs()
    original = research.build_augmented_features(daily, hourly, funding, btc, r3)
    changed_hourly = hourly.copy()
    changed_hourly.loc[changed_hourly["ts"].ge(daily.index[25]), "close"] *= 2.0
    changed = research.build_augmented_features(daily, changed_hourly, funding, btc, r3)
    pd.testing.assert_frame_equal(original.loc[: daily.index[24]], changed.loc[: daily.index[24]])


def test_augmented_features_are_finite_after_backward_warmup() -> None:
    research = load_research()
    r3 = research._load(research.R3_PATH, "ctls_r6_test_r3_finite")
    daily, hourly, funding, btc = inputs()
    features = research.build_augmented_features(daily, hourly, funding, btc, r3)
    assert features.shape[1] > len(r3.FEATURE_COLUMNS)
    assert np.isfinite(features.iloc[12:].to_numpy()).all()


def test_final_search_grid_cardinality_is_4464() -> None:
    research = load_research()
    r3 = research._load(research.R3_PATH, "ctls_r6_test_r3_grid")
    r5 = research._load(research.R5_PATH, "ctls_r6_test_r5_grid")
    assert (
        len(r3.model_configs())
        * len(r5.EMA_ALPHAS)
        * len(r5.base_post_configs(r3))
        * len(r5.duration_configs())
        == 4464
    )


@pytest.mark.local_data
def test_btc_file_hash_is_nonempty_and_deterministic() -> None:
    research = load_research()
    digest = research.sha256(research.BTC_PATH)
    assert len(digest) == 64
    assert digest == research.sha256(research.BTC_PATH)

