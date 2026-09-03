from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import pytest



ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "research/hype/1d-ma7-asymmetric-body-trend/scripts/"
    "research_hype_1d_ma7_snc02_ma05_probe_sizing_stage_b.py"
)
ARTIFACT = (
    ROOT
    / "research/hype/1d-ma7-asymmetric-body-trend/artifacts/"
    "hype_1d_ma7_snc02_ma05_probe_sizing_stage_b_2026-08-20.json"
)


def load_module():
    spec = importlib.util.spec_from_file_location("snc02_stage_b_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_artifact() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_frozen_arms_do_not_change_exit_layer() -> None:
    module = load_module()
    assert module.MA_EXIT_BUFFER_ATR == 0.5
    assert module.CONFIRM_SLOPE_ATR == 0.02
    assert [arm.arm_id for arm in module.ARMS] == [
        "MA05_1X",
        "MA05_FIXED75",
        "MA05_FIXED50",
        "MA05_P50_C1",
        "MA05_P50_C2",
        "MA05_P25_C2",
    ]


@pytest.mark.local_data
def test_locked_artifact_has_exact_ma05_parity() -> None:
    payload = load_artifact()
    assert all(
        all(checks.values()) for checks in payload["ma05_parity"].values()
    )
    base = payload["primary_extended"]["MA05_1X"]
    assert math.isclose(base["net_return_pct"], 148.7933784775765, abs_tol=2e-10)
    assert math.isclose(
        base["chronological_1h_mdd_pct"],
        -33.60707383211267,
        abs_tol=2e-10,
    )


@pytest.mark.local_data
def test_fixed_half_is_only_mdd20_pass_but_fails_retention() -> None:
    payload = load_artifact()
    passing = [
        arm for arm, verdict in payload["verdict"].items() if verdict["mdd20_pass"]
    ]
    assert passing == ["MA05_FIXED50"]
    verdict = payload["verdict"]["MA05_FIXED50"]
    assert verdict["robustness_pass"]
    assert not verdict["return_retention_pass"]
    assert not verdict["latest_trend_capture_pass"]
    assert not verdict["continuation_candidate"]


@pytest.mark.local_data
def test_dynamic_promotions_fail_lag_and_candidate_gate() -> None:
    payload = load_artifact()
    for arm in ("MA05_P50_C1", "MA05_P50_C2", "MA05_P25_C2"):
        assert payload["primary_extended"][arm]["promoted_trades"] > 0
        assert payload["stress"][arm]["lag_1d"]["net_return_pct"] < 0.0
        assert not payload["verdict"][arm]["continuation_candidate"]


@pytest.mark.local_data
def test_artifact_sha256_sidecar() -> None:
    digest = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    sidecar = Path(f"{ARTIFACT}.sha256").read_text(encoding="utf-8").split()[0]
    assert digest == sidecar
