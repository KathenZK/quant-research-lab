from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "research/hype/1d-ma7-asymmetric-body-trend/scripts"
    / "research_hype_1d_ma7_trend_phase_risk.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("hype_tpr_research", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RESEARCH = load_module()


def metrics(
    return_pct: float,
    chronological_mdd: float,
    daily_mdd: float = -20.0,
    trades: int = 9,
    *,
    long_trades: int = 4,
    short_trades: int = 5,
    bankrupt: bool = False,
) -> dict[str, object]:
    return {
        "equity_multiple": 1.0 + return_pct / 100.0,
        "net_return_pct": return_pct,
        "chronological_1h_mdd_pct": chronological_mdd,
        "daily_extreme_mdd_pct": daily_mdd,
        "closed_trades": trades,
        "long_trades": long_trades,
        "short_trades": short_trades,
        "bankrupt_intraday": bankrupt,
        "max_marked_leverage": 1.0,
    }


def result(row: dict[str, object]) -> dict[str, object]:
    return {"metrics": row}


def trial_bundle(base: dict[str, object]) -> dict[str, object]:
    folds = [result(base), result(base), result(base)]
    return {
        "base_full": result(base),
        "base_wfo": base,
        "base_folds": folds,
        "stress_full": result(base),
        "stress_wfo": base,
    }


def test_window_start_semantics_are_frozen() -> None:
    assert RESEARCH.engine_start((0, 259)) == 0
    assert RESEARCH.engine_start((130, 173)) == 131
    assert RESEARCH.engine_start((269, 346)) == 270


def test_fold_aggregation_compounds_and_keeps_both_worst_mdds() -> None:
    folds = [
        result(metrics(10.0, -5.0, -6.0, trades=2, long_trades=1, short_trades=1)),
        result(metrics(-10.0, -8.0, -7.0, trades=1, long_trades=0, short_trades=1)),
    ]
    row = RESEARCH.aggregate_folds(folds)
    assert row["equity_multiple"] == pytest.approx(0.99)
    assert row["net_return_pct"] == pytest.approx(-1.0)
    assert row["chronological_1h_mdd_pct"] == -8.0
    assert row["daily_extreme_mdd_pct"] == -7.0
    assert row["closed_trades"] == 3


def test_comparison_is_strict_and_materiality_is_pre_registered() -> None:
    control = metrics(100.0, -20.0)
    good = RESEARCH.compare(metrics(105.0, -19.999), control)
    assert good["return_higher"]
    assert good["chronological_mdd_smaller"]
    assert good["material"]
    equality = RESEARCH.compare(metrics(100.0, -18.0), control)
    assert not equality["return_higher"]
    assert equality["chronological_mdd_smaller"]
    assert equality["material"]
    assert RESEARCH.compare(metrics(99.0, -21.0), control)["double_worse"]


def test_numeric_gate_requires_dual_dominance_and_trade_floors() -> None:
    control = trial_bundle(metrics(100.0, -20.0))
    candidate = trial_bundle(metrics(106.0, -18.0))
    passed = RESEARCH.numeric_gate(candidate, control)
    assert passed["status"] == "PASS"
    candidate["base_full"]["metrics"]["short_trades"] = 2
    failed = RESEARCH.numeric_gate(candidate, control)
    assert failed["status"] == "FAIL"
    assert not failed["checks"]["short_floor"]


def test_module_mapping_and_activation_are_effect_based() -> None:
    assert RESEARCH.enabled_modules(
        {"q_threshold": 0.3, "e_days": 2, "t_enabled": True}
    ) == ["Q", "E", "T"]
    assert RESEARCH.enabled_modules(
        {"q_threshold": None, "e_days": 0, "t_enabled": True}
    ) == ["T"]
    assert RESEARCH.module_active("Q", {"q_reject": 1})
    assert RESEARCH.module_active("E", {"e_exit": 1})
    assert RESEARCH.module_active("T", {"t_exit": 1})
    assert not RESEARCH.module_active("Q", {"q_accept": 9})


def test_evaluation_gate_is_fail_closed_on_trade_floor() -> None:
    control = result(metrics(100.0, -20.0, trades=4))
    candidate = result(metrics(106.0, -18.0, trades=2))
    gate = RESEARCH.evaluation_gate(candidate, control)
    assert gate["comparison"]["return_higher"]
    assert gate["status"] == "FAIL"
    assert not gate["checks"]["candidate_trade_floor"]


def test_leverage_eligibility_requires_both_domains_and_solvency() -> None:
    row = {
        "D": {
            "one_x_metrics": metrics(100.0, -20.0),
            "base": result(metrics(120.0, -30.0)),
            "stress": result(metrics(110.0, -32.0)),
        },
        "V": {
            "one_x_metrics": metrics(10.0, -10.0),
            "base": result(metrics(15.0, -15.0)),
            "stress": result(metrics(12.0, -18.0)),
        },
    }
    assert RESEARCH.leverage_eligible(row, 35.0)
    row["V"]["stress"]["metrics"]["bankrupt_intraday"] = True
    assert not RESEARCH.leverage_eligible(row, 35.0)


def test_locked_json_is_exclusive_and_hash_verified(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    digest = RESEARCH.write_locked(path, {"value": 1})
    loaded, actual = RESEARCH.read_locked(path)
    assert loaded == {"value": 1}
    assert actual == digest
    with pytest.raises(RuntimeError, match="already exists"):
        RESEARCH.write_locked(path, {"value": 2})


def test_frontier_row_keeps_risk_units_and_frozen_eligibility() -> None:
    evidence = result(metrics(25.0, -15.0, -18.0, trades=6))
    row = RESEARCH.frontier_row(
        "FIXED_1.5X",
        "fixed",
        evidence,
        target_leverage=1.5,
        frozen_eligible_35=True,
        frozen_eligible_50=True,
    )
    assert row["net_return_pct"] == 25.0
    assert row["chronological_1h_mdd_pct"] == -15.0
    assert row["daily_extreme_mdd_pct"] == -18.0
    assert row["target_leverage"] == 1.5
    assert row["frozen_eligible_35"]


@pytest.mark.local_data
def test_self_test_does_not_create_performance_artifacts() -> None:
    paths = (
        RESEARCH.MANIFEST_PATH,
        RESEARCH.TRIALS_PATH,
        RESEARCH.DEVELOPMENT_PATH,
        RESEARCH.VALIDATION_PATH,
        RESEARCH.HOLDOUT_PATH,
    )
    before = {path: path.exists() for path in paths}
    assert RESEARCH.self_test() == {
        "status": "PASS",
        "candidate_count": 12,
        "leverage_count": 9,
    }
    assert {path: path.exists() for path in paths} == before
