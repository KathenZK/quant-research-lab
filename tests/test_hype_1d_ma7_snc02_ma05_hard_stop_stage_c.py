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
    "research_hype_1d_ma7_snc02_ma05_hard_stop_stage_c.py"
)
ARTIFACT = (
    ROOT
    / "research/hype/1d-ma7-asymmetric-body-trend/artifacts/"
    "hype_1d_ma7_snc02_ma05_hard_stop_stage_c_2026-08-20.json"
)


def load_module():
    spec = importlib.util.spec_from_file_location("snc02_stage_c_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_artifact() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_frozen_stop_grid_and_normalized_reasons() -> None:
    module = load_module()
    assert [arm.hard_stop_atr for arm in module.ARMS] == [None, 1.0, 1.5, 2.0]
    assert module.hard_stop_reason(module.ARMS[1]) == "hard_stop_1p0atr"
    assert module.hard_stop_reason(module.ARMS[2]) == "hard_stop_1p5atr"


@pytest.mark.local_data
def test_locked_artifact_has_exact_ma05_parity() -> None:
    payload = load_artifact()
    assert all(
        all(checks.values()) for checks in payload["ma05_parity"].values()
    )
    control = payload["primary_extended"]["MA05_CTRL"]
    assert math.isclose(
        control["net_return_pct"], 148.7933784775765, abs_tol=2e-10
    )
    assert math.isclose(
        control["chronological_1h_mdd_pct"],
        -33.60707383211267,
        abs_tol=2e-10,
    )


@pytest.mark.local_data
def test_no_hard_stop_arm_passes_mdd20_or_candidate_gate() -> None:
    payload = load_artifact()
    for arm in ("MA05_HS10", "MA05_HS15", "MA05_HS20"):
        assert not payload["verdict"][arm]["mdd20_pass"]
        assert not payload["verdict"][arm]["continuation_candidate"]
    assert payload["verdict"]["MA05_HS10"]["hard_stop_count"] == 7
    assert payload["verdict"]["MA05_HS15"]["hard_stop_count"] == 4
    assert payload["verdict"]["MA05_HS20"]["hard_stop_count"] == 0


@pytest.mark.local_data
def test_latest_august_long_is_preserved() -> None:
    payload = load_artifact()
    for arm in payload["verdict"]:
        trade = payload["verdict"][arm]["latest_august_long"]
        assert trade["entry_ts"] == "2026-08-09T00:00:00+00:00"
        assert trade["exit_reason"] == "terminal_flatten"
        assert math.isclose(trade["net_return_pct"], 26.076396828846203)


@pytest.mark.local_data
def test_artifact_sha256_sidecar() -> None:
    digest = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    sidecar = Path(f"{ARTIFACT}.sha256").read_text(encoding="utf-8").split()[0]
    assert digest == sidecar
