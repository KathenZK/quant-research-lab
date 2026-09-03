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
ENGINE_PATH = SCRIPT_DIR / "hype_1d_ma7_v6_transition_repair_engine.py"
ADAPTER_PATH = SCRIPT_DIR / "hype_1d_ma7_v4_fair_adapter.py"


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ENGINE = load(ENGINE_PATH, "test_v6_transition_repair_engine")


def side_config(side: int) -> SimpleNamespace:
    return SimpleNamespace(
        side=side,
        slope_lookback=1 if side > 0 else 2,
        slope_min_atr=0.02,
        entry_buffer_atr=0.0 if side > 0 else 0.10,
    )


def series(
    close: list[float], ma7: list[float], atr7: list[float] | None = None
) -> tuple[SimpleNamespace, SimpleNamespace]:
    atr = atr7 or [1.0] * len(close)
    return (
        SimpleNamespace(close=np.asarray(close, dtype=float)),
        SimpleNamespace(
            ma7=np.asarray(ma7, dtype=float),
            atr7=np.asarray(atr, dtype=float),
        ),
    )


def signal(
    config: Any,
    rsi6: list[float],
    native: Any | None = None,
) -> Any:
    native_fn = native or (lambda *_args: False)
    return ENGINE.TransitionEntrySignal(
        native_fn,
        side_config(1),
        side_config(-1),
        config,
        np.asarray(rsi6, dtype=float),
    )


def decisions(entry_signal: Any, book: Any, features: Any) -> list[tuple[bool, bool]]:
    long_config = side_config(1)
    short_config = side_config(-1)
    return [
        (
            entry_signal(long_config, book, features, index),
            entry_signal(short_config, book, features, index),
        )
        for index in range(len(book.close))
    ]


def test_buffer_can_mature_after_short_cross() -> None:
    book, features = series(
        [10.2, 10.0, 9.95, 9.70],
        [10.1, 10.0, 10.0, 9.95],
    )
    config = ENGINE.TransitionRepairConfig(
        "BUFFER",
        episode_enabled=True,
        maturity_mode="BUFFER",
        anti_chase_cap_atr=1.0,
    )
    entry_signal = signal(config, [50.0] * 4)
    rows = decisions(entry_signal, book, features)
    assert rows[2] == (False, False)
    assert rows[3] == (False, True)
    assert any(row["event"] == "episode_confirm" for row in entry_signal.events)


def test_slope_can_mature_after_long_cross() -> None:
    book, features = series(
        [9.8, 10.05, 10.20],
        [10.0, 10.0, 10.10],
    )
    config = ENGINE.TransitionRepairConfig(
        "SLOPE",
        episode_enabled=True,
        maturity_mode="SLOPE",
        anti_chase_cap_atr=1.0,
    )
    entry_signal = signal(config, [50.0] * 3)
    rows = decisions(entry_signal, book, features)
    assert rows[1] == (False, False)
    assert rows[2] == (True, False)


def test_recross_cancels_episode() -> None:
    book, features = series(
        [9.8, 10.05, 9.95, 10.30],
        [9.9, 10.0, 10.0, 10.10],
    )
    config = ENGINE.TransitionRepairConfig(
        "RECROSS",
        episode_enabled=True,
        maturity_mode="SLOPE",
        recross_cancels=True,
    )
    entry_signal = signal(config, [50.0] * 4)
    rows = decisions(entry_signal, book, features)
    assert rows[3] == (False, False)
    assert any(
        row["event"] == "episode_cancel_recross" for row in entry_signal.events
    )


def test_anti_chase_cap_is_strict() -> None:
    book, features = series(
        [9.8, 10.05, 10.75],
        [10.0, 10.0, 10.0],
    )
    config = ENGINE.TransitionRepairConfig(
        "CAP",
        episode_enabled=True,
        maturity_mode="SLOPE",
        anti_chase_cap_atr=0.75,
    )
    entry_signal = signal(config, [50.0] * 3)
    rows = decisions(entry_signal, book, features)
    assert rows[2] == (False, False)


def test_rsi_take_profit_requires_reset_then_new_decline() -> None:
    book, features = series(
        [10.0, 9.8, 9.7, 9.8, 9.6],
        [10.2, 10.1, 10.0, 9.95, 9.9],
    )
    config = ENGINE.TransitionRepairConfig(
        "RSI",
        rsi_reobserve_enabled=True,
        rsi_reset_threshold=30.0,
        anti_chase_cap_atr=1.0,
    )
    entry_signal = signal(config, [15.0, 15.0, 25.0, 31.0, 24.0])
    entry_signal.notify_exit(-1, 1, "short_rsi_take_profit")
    rows = decisions(entry_signal, book, features)
    assert rows[2] == (False, False)
    assert rows[3] == (False, False)
    assert rows[4] == (False, True)


def test_raw_episode_without_maturity_is_dormant_when_cross_failed() -> None:
    book, features = series(
        [10.2, 10.0, 9.95, 9.70],
        [10.0, 10.0, 10.0, 9.95],
    )
    config = ENGINE.TransitionRepairConfig(
        "RAW_ONLY",
        episode_enabled=True,
        maturity_mode="NONE",
    )
    entry_signal = signal(config, [50.0] * 4)
    assert decisions(entry_signal, book, features)[3] == (False, False)
    assert any(
        row["event"] == "episode_reject_raw_cross" for row in entry_signal.events
    )


def test_config_validation_and_canonical_infinity() -> None:
    config = ENGINE.TransitionRepairConfig("OK")
    assert config.canonical()["anti_chase_cap_atr"] == "INF"
    assert len(ENGINE.config_sha256(config)) == 64
    try:
        ENGINE.TransitionRepairConfig("BAD", same_side_cooldown_days=5)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid cooldown accepted")


@pytest.mark.local_data
def test_transformed_global_off_has_exact_v6_parity() -> None:
    adapter = load(ADAPTER_PATH, "test_v6_transition_repair_adapter")
    context = adapter.load_context()
    exact = ENGINE.run_v6(
        context,
        start_index=0,
        terminal_index=context.book.count,
        retain=True,
    )
    off = ENGINE.run_variant(
        context,
        ENGINE.TransitionRepairConfig("OFF"),
        start_index=0,
        terminal_index=context.book.count,
        retain=True,
    )
    assert exact.raw.metrics == off.raw.metrics
    assert exact.raw.trades == off.raw.trades
    assert exact.raw.path == off.raw.path
    assert math.isclose(exact.raw.metrics["net_return_pct"], 617.1070876096234)
