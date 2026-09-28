from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
pytestmark = pytest.mark.local_data

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "research/hype/1d-ma7-asymmetric-body-trend/artifacts/"
    "hype_1d_ma7_snc02_ma05_equity_drawdown_governor_stage_d_2026-08-20.json"
)


def load_artifact() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_control_parity_and_no_continuation_candidate() -> None:
    payload = load_artifact()
    assert all(
        all(checks.values()) for checks in payload["ma05_parity"].values()
    )
    assert not any(
        verdict["continuation_candidate"]
        for arm, verdict in payload["verdict"].items()
        if arm != "MA05_CTRL"
    )


def test_mdd20_arms_are_stuck_at_low_risk_and_fail_retention() -> None:
    payload = load_artifact()
    for arm in ("DG08_L25_R04", "DG10_L25_R05"):
        assert payload["verdict"][arm]["mdd20_pass"]
        assert not payload["verdict"][arm]["return_retention_pass"]
        assert payload["primary_extended"][arm]["low_risk_state_pct"] > 92.0


def test_artifact_sha256_sidecar() -> None:
    digest = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    sidecar = Path(f"{ARTIFACT}.sha256").read_text(encoding="utf-8").split()[0]
    assert digest == sidecar
