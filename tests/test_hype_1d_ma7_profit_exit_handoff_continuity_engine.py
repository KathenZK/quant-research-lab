from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "research/hype/1d-ma7-asymmetric-body-trend/scripts/hype_1d_ma7_profit_exit_handoff_continuity_engine.py"
RESEARCH_PATH = ROOT / "research/hype/1d-ma7-asymmetric-body-trend/scripts/research_hype_1d_ma7_opportunity_aware_profit_protection.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_frozen_grid_has_490_unique_configs() -> None:
    engine = load(ENGINE_PATH, "pehc_engine_grid_test")
    rows = engine.grid_configs()
    assert len(rows) == 490
    assert len({engine.config_sha256(row) for row in rows}) == 490
    assert {row.execution for row in rows} == {"same_1h_open", "next_utc_open"}
    assert sum(row.slope_threshold is None for row in rows) == 98


def test_handoff_filters_are_strict_at_all_boundaries() -> None:
    engine = load(ENGINE_PATH, "pehc_engine_filter_test")
    common = {
        "ma7": 100.0,
        "previous_ma7": 101.0,
        "atr7": 10.0,
        "slope_threshold": 0.05,
        "chase_cap_atr": 0.5,
    }
    assert not engine.handoff_eligibility(price=100.0, **common)["passed"]
    assert not engine.handoff_eligibility(price=95.0, **common)["passed"]
    assert engine.handoff_eligibility(price=95.0001, **common)["passed"]
    slope_equal = {**common, "previous_ma7": 100.5}
    assert not engine.handoff_eligibility(price=99.0, **slope_equal)["passed"]


@pytest.mark.parametrize("field", ["price", "ma7", "previous_ma7", "atr7"])
def test_handoff_rejects_nonfinite_inputs(field: str) -> None:
    engine = load(ENGINE_PATH, f"pehc_engine_nonfinite_{field}")
    values = {
        "price": 99.0,
        "ma7": 100.0,
        "previous_ma7": 101.0,
        "atr7": 10.0,
        "slope_threshold": 0.01,
        "chase_cap_atr": math.inf,
    }
    values[field] = math.nan
    assert not engine.handoff_eligibility(**values)["passed"]


def test_slope_off_does_not_require_previous_ma() -> None:
    engine = load(ENGINE_PATH, "pehc_engine_slope_off_test")
    result = engine.handoff_eligibility(
        price=99.0,
        ma7=100.0,
        previous_ma7=math.nan,
        atr7=10.0,
        slope_threshold=None,
        chase_cap_atr=math.inf,
    )
    assert result["passed"]
    assert result["slope_atr"] is None


@pytest.mark.local_data
def test_disabled_pehc_is_exact_fixed_oapp_parity_on_real_book() -> None:
    engine = load(ENGINE_PATH, "pehc_engine_real_parity")
    research = load(RESEARCH_PATH, "pehc_oapp_research_real_parity")
    oapp, _, _, _, context = research.load_runtime()
    disabled = engine.PEHCConfig("PEHC_OFF", enabled=False)
    candidate = engine.run_variant(
        context,
        disabled,
        start_index=0,
        terminal_index=120,
        retain=True,
    )
    control = oapp.run_variant(
        context,
        engine.fixed_oapp_config(),
        start_index=0,
        terminal_index=120,
        retain=True,
    )
    assert candidate.raw.metrics == control.raw.metrics
    assert candidate.raw.trades == control.raw.trades
    projected = [
        {key: row[key] for key in control.raw.path[0]}
        for row in candidate.raw.path
    ]
    assert projected == control.raw.path
    assert candidate.handoff_events == []


@pytest.mark.local_data
def test_real_candidate_creates_isolated_shadow_events() -> None:
    engine = load(ENGINE_PATH, "pehc_engine_real_shadow")
    research = load(RESEARCH_PATH, "pehc_oapp_research_real_shadow")
    _, _, _, _, context = research.load_runtime()
    config = engine.PEHCConfig(
        "PEHC_REAL",
        expiry_days=5,
        slope_threshold=None,
        chase_cap_atr=math.inf,
        execution="same_1h_open",
    )
    result = engine.run_variant(
        context,
        config,
        start_index=0,
        terminal_index=432,
        retain=True,
    )
    assert result.activation_counts["shadow_start"] > 0
    assert all("equity" not in row for row in result.handoff_events)
    assert not result.raw.metrics["bankrupt_intraday"]


@pytest.mark.local_data
def test_old_h_expiry_boundary_and_execution_timing_are_exact() -> None:
    engine = load(ENGINE_PATH, "pehc_engine_old_h_timing")
    research = load(RESEARCH_PATH, "pehc_oapp_research_old_h_timing")
    _, _, _, _, context = research.load_runtime()
    expired = engine.run_variant(
        context,
        engine.PEHCConfig("E1", expiry_days=1),
        start_index=356,
        terminal_index=432,
        retain=True,
    )
    assert expired.activation_counts["handoff_accept"] == 0
    same = engine.run_variant(
        context,
        engine.PEHCConfig("E3_SAME", expiry_days=3),
        start_index=356,
        terminal_index=432,
        retain=True,
    )
    delayed = engine.run_variant(
        context,
        engine.PEHCConfig("E3_NEXT", expiry_days=3, execution="next_utc_open"),
        start_index=356,
        terminal_index=432,
        retain=True,
    )
    same_accept = next(row for row in same.handoff_events if row["event"] == "handoff_accept")
    delayed_accept = next(
        row for row in delayed.handoff_events if row["event"] == "handoff_accept"
    )
    assert same_accept["ts"] == "2026-07-11T06:00:00+00:00"
    assert same_accept["price"] == 66.536
    assert delayed_accept["ts"] == "2026-07-12T00:00:00+00:00"
    assert delayed_accept["price"] == 66.743


@pytest.mark.local_data
def test_shadow_only_control_changes_no_funded_path() -> None:
    engine = load(ENGINE_PATH, "pehc_engine_shadow_only")
    research = load(RESEARCH_PATH, "pehc_oapp_research_shadow_only")
    oapp, _, _, _, context = research.load_runtime()
    config = engine.PEHCConfig("SHADOW_ONLY", expiry_days=8, entry_enabled=False)
    shadow = engine.run_variant(
        context, config, start_index=0, terminal_index=432, retain=True
    )
    control = oapp.run_variant(
        context,
        engine.fixed_oapp_config(),
        start_index=0,
        terminal_index=432,
        retain=True,
    )
    assert shadow.activation_counts["handoff_opportunity"] > 0
    assert shadow.raw.metrics == control.raw.metrics
    assert shadow.raw.trades == control.raw.trades
    assert shadow.raw.path == control.raw.path
