from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace
import sys
from typing import Any

import numpy as np

import pytest



ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "research/hype/1d-ma7-asymmetric-body-trend/scripts"
ENGINE_PATH = SCRIPT_DIR / "hype_1d_ma7_v6_rsi6_memory_cross_engine.py"
ADAPTER_PATH = SCRIPT_DIR / "hype_1d_ma7_v4_fair_adapter.py"


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ENGINE = load(ENGINE_PATH, "test_v6_rsi6_memory_cross_engine")


def data(close: list[float], ma7: list[float]) -> tuple[Any, Any]:
    return (
        SimpleNamespace(close=np.asarray(close, dtype=float)),
        SimpleNamespace(ma7=np.asarray(ma7, dtype=float)),
    )


def side(side_value: int) -> Any:
    return SimpleNamespace(side=side_value)


def test_prior5_oversold_memory_crosses_long() -> None:
    book, features = data(
        [10.0, 9.9, 9.8, 9.7, 9.9, 9.9, 10.2],
        [10.0] * 7,
    )
    signal = ENGINE.RSIMemoryCrossSignal(
        lambda *_args: False,
        ENGINE.RSIMemoryCrossConfig("LONG"),
        np.asarray([50.0, 29.0, 28.0, 31.0, 20.0, 40.0, 60.0]),
    )
    assert signal(side(1), book, features, 6)
    assert not signal(side(-1), book, features, 6)
    assert signal.events[0]["extreme_days"] == 3


def test_prior5_overbought_memory_crosses_short() -> None:
    book, features = data(
        [10.0, 10.1, 10.2, 10.3, 10.1, 10.1, 9.8],
        [10.0] * 7,
    )
    signal = ENGINE.RSIMemoryCrossSignal(
        lambda *_args: False,
        ENGINE.RSIMemoryCrossConfig("SHORT"),
        np.asarray([50.0, 71.0, 72.0, 69.0, 80.0, 60.0, 40.0]),
    )
    assert signal(side(-1), book, features, 6)
    assert signal.events[0]["extreme_days"] == 3


def test_threshold_equality_does_not_count() -> None:
    book, features = data(
        [10.0, 9.9, 9.8, 9.7, 9.9, 9.9, 10.2],
        [10.0] * 7,
    )
    signal = ENGINE.RSIMemoryCrossSignal(
        lambda *_args: False,
        ENGINE.RSIMemoryCrossConfig("STRICT"),
        np.asarray([50.0, 30.0, 30.0, 29.0, 28.0, 40.0, 20.0]),
    )
    assert not signal(side(1), book, features, 6)
    assert signal.events[0]["extreme_days"] == 2


def test_inclusive_window_can_use_cross_day_rsi() -> None:
    book, features = data(
        [10.0, 9.9, 9.8, 9.7, 9.9, 9.9, 10.2],
        [10.0] * 7,
    )
    rsi = np.asarray([50.0, 50.0, 29.0, 28.0, 40.0, 40.0, 20.0])
    prior = ENGINE.RSIMemoryCrossSignal(
        lambda *_args: False,
        ENGINE.RSIMemoryCrossConfig("PRIOR"),
        rsi,
    )
    inclusive = ENGINE.RSIMemoryCrossSignal(
        lambda *_args: False,
        ENGINE.RSIMemoryCrossConfig("INCL", window_mode="INCLUSIVE5"),
        rsi,
    )
    assert not prior(side(1), book, features, 6)
    assert inclusive(side(1), book, features, 6)


def test_native_signal_is_preserved_or_can_be_disabled() -> None:
    book, features = data([10.0] * 7, [10.0] * 7)
    native = ENGINE.RSIMemoryCrossSignal(
        lambda *_args: True,
        ENGINE.RSIMemoryCrossConfig("NATIVE"),
        np.asarray([50.0] * 7),
    )
    no_native = ENGINE.RSIMemoryCrossSignal(
        lambda *_args: True,
        ENGINE.RSIMemoryCrossConfig("NO_NATIVE", native_enabled=False),
        np.asarray([50.0] * 7),
    )
    assert native(side(1), book, features, 6)
    assert not no_native(side(1), book, features, 6)


def test_config_and_hash_are_frozen() -> None:
    config = ENGINE.RSIMemoryCrossConfig("OK")
    assert config.canonical()["required_days"] == 3
    assert len(ENGINE.config_sha256(config)) == 64
    try:
        ENGINE.RSIMemoryCrossConfig("BAD", required_days=2)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid RSI count accepted")


@pytest.mark.local_data
def test_disabled_overlay_has_exact_v6_parity() -> None:
    adapter = load(ADAPTER_PATH, "test_v6_rsi_memory_adapter")
    context = adapter.load_context()
    exact = ENGINE.run_v6(
        context,
        start_index=0,
        terminal_index=context.book.count,
        retain=True,
    )
    off = ENGINE.run_variant(
        context,
        ENGINE.RSIMemoryCrossConfig(
            "OFF",
            long_enabled=False,
            short_enabled=False,
        ),
        start_index=0,
        terminal_index=context.book.count,
        retain=True,
    )
    assert exact.raw.metrics == off.raw.metrics
    assert exact.raw.trades == off.raw.trades
    assert exact.raw.path == off.raw.path
    assert math.isclose(exact.raw.metrics["net_return_pct"], 617.1070876096234)
