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
ENGINE_PATH = SCRIPT_DIR / "hype_1d_ma7_v6_structural_sizing_engine.py"
ADAPTER_PATH = SCRIPT_DIR / "hype_1d_ma7_v4_fair_adapter.py"


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ENGINE = load(ENGINE_PATH, "test_v6_structural_sizing_engine")


def test_frozen_arm_count_and_config_contract() -> None:
    rows = ENGINE.frozen_configs()
    assert len(rows) == 10
    assert rows[0].arm_id == "CTRL_EXACT_V6"
    assert rows[-1].arm_id == "B_CONSERVATIVE_ALL"
    assert len({ENGINE.config_sha256(row) for row in rows}) == 10
    try:
        ENGINE.StructuralConfig(
            "BAD", memory_long_enabled=True, long_probe_leverage=0.50, long_confirm_days=1
        )
    except ValueError:
        pass
    else:
        raise AssertionError("non-frozen confirm window accepted")


def test_probe_confirmation_is_strict_and_directional() -> None:
    passed = ENGINE.probe_confirmation(
        side=1,
        close=101.0,
        ma7=100.0,
        previous_ma7=99.0,
        atr7=10.0,
    )
    equality = ENGINE.probe_confirmation(
        side=1,
        close=101.0,
        ma7=100.0,
        previous_ma7=99.8,
        atr7=10.0,
    )
    wrong_regime = ENGINE.probe_confirmation(
        side=1,
        close=99.0,
        ma7=100.0,
        previous_ma7=99.0,
        atr7=10.0,
    )
    assert passed["passed"]
    assert not equality["passed"]
    assert math.isclose(equality["slope_atr"], 0.02)
    assert not wrong_regime["passed"]


def test_memory_only_long_gets_probe_but_forced_entry_does_not() -> None:
    context = SimpleNamespace(
        features=SimpleNamespace(atr7=np.asarray([10.0])),
    )
    signal = SimpleNamespace(
        classifications={(0, 1): {"native": False, "memory": True, "memory_only": True}}
    )
    config = ENGINE.StructuralConfig(
        "LONG",
        memory_long_enabled=True,
        long_probe_leverage=0.50,
        long_confirm_days=2,
    )
    policy = ENGINE.StructuralLeveragePolicy(context, config, signal)
    policy.set_entry_context(1, 100.0, 0, "natural")
    assert policy.last_entry_is_probe
    assert policy.last_entry_leverage == 0.50
    policy.set_entry_context(1, 100.0, 0, "forced_reversal")
    assert not policy.last_entry_is_probe
    assert policy.last_entry_leverage == 1.0


def test_short_probe_stays_small_and_atr_cap_never_increases_it() -> None:
    context = SimpleNamespace(
        features=SimpleNamespace(atr7=np.asarray([20.0])),
    )
    signal = SimpleNamespace(
        classifications={(0, -1): {"native": False, "memory": True, "memory_only": True}}
    )
    config = ENGINE.StructuralConfig(
        "SHORT",
        memory_short_enabled=True,
        short_probe_leverage=0.25,
        volatility_cap_enabled=True,
    )
    policy = ENGINE.StructuralLeveragePolicy(context, config, signal)
    policy.set_entry_context(-1, 100.0, 0, "natural")
    assert policy.last_entry_leverage == 0.25
    qty, equity, turnover = policy(1.0, 0.0, -1, 100.0, 0.0014)
    assert qty < 0.0
    assert abs(qty) * 100.0 / equity < 0.251
    assert turnover > 0.0


def test_atr_cap_is_causal_bounded_and_applies_to_promotion() -> None:
    context = SimpleNamespace(
        features=SimpleNamespace(atr7=np.asarray([10.0])),
    )
    signal = SimpleNamespace(
        classifications={(0, 1): {"native": True, "memory": False, "memory_only": False}}
    )
    config = ENGINE.StructuralConfig("VOL", volatility_cap_enabled=True)
    policy = ENGINE.StructuralLeveragePolicy(context, config, signal)
    policy.set_entry_context(1, 100.0, 0, "natural")
    assert policy.last_entry_leverage == 0.50
    policy.set_promotion_context(100.0, 0)
    qty, equity, _turnover = policy(1.0, 0.0, 1, 100.0, 0.0014)
    assert 0.49 < qty * 100.0 / equity < 0.51


@pytest.mark.local_data
def test_structural_control_has_exact_v6_parity() -> None:
    adapter = load(ADAPTER_PATH, "test_v6_structural_adapter")
    context = adapter.load_context()
    exact = ENGINE.run_exact_v6(
        context,
        start_index=0,
        terminal_index=context.book.count,
        retain=True,
    )
    control = ENGINE.run_variant(
        context,
        ENGINE.frozen_configs()[0],
        start_index=0,
        terminal_index=context.book.count,
        retain=True,
    )
    assert exact.raw.metrics == control.raw.metrics
    for left, right in zip(exact.raw.trades, control.raw.trades, strict=True):
        stripped = {
            key: value for key, value in right.items() if not key.startswith("structural_")
        }
        assert left == stripped
    for left, right in zip(exact.raw.path, control.raw.path, strict=True):
        stripped = {key: value for key, value in right.items() if not key.startswith("struct_")}
        assert left == stripped
    assert math.isclose(control.raw.metrics["net_return_pct"], 617.1070876096234)
    replay = ENGINE.replay_structural_chronological_1h(context, control)
    assert all(replay.parity.values())
    assert math.isclose(replay.chronological_1h_mdd_pct, -18.391735672691034)


@pytest.mark.local_data
def test_long_probe_promotion_replay_has_full_ledger_parity() -> None:
    adapter = load(ADAPTER_PATH, "test_v6_structural_promotion_adapter")
    context = adapter.load_context()
    candidate = ENGINE.run_variant(
        context,
        next(row for row in ENGINE.frozen_configs() if row.arm_id == "A_LONG_P05_C2"),
        start_index=0,
        terminal_index=context.book.count,
        retain=True,
    )
    replay = ENGINE.replay_structural_chronological_1h(context, candidate)
    assert all(replay.parity.values())
    assert replay.promotion_count == candidate.activation_counts["long_probe_promotions"]
