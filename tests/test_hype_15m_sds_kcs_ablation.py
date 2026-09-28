from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "research/hype/15m-sequential-drift-state/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT_PATH = SCRIPT_DIR / "research_hype_15m_sds_kcs_full_ablation.py"
SPEC = importlib.util.spec_from_file_location(
    "hype_15m_sds_kcs_ablation_test",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
ABLATION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ABLATION
SPEC.loader.exec_module(ABLATION)


def test_every_active_signal_parameter_has_ablation_values() -> None:
    active = set(ABLATION.kcs.KCSConfig.__dataclass_fields__)
    assert set(ABLATION.SIGNAL_VALUES) == active


def test_every_effective_backtest_parameter_has_ablation_values() -> None:
    assert set(ABLATION.RISK_VALUES) == {
        "stop_atr",
        "max_hold_bars",
        "leverage",
    }


@pytest.mark.local_data
def test_frozen_reference_value_is_present_for_each_parameter() -> None:
    if not ABLATION.kcs.SUMMARY_PATH.is_file():
        pytest.skip("local SDS frozen reference evidence is unavailable")
    signal, risk = ABLATION._reference_configs()
    for parameter, values in ABLATION.SIGNAL_VALUES.items():
        assert getattr(signal, parameter) in values
    for parameter, values in ABLATION.RISK_VALUES.items():
        assert getattr(risk, parameter) in values
