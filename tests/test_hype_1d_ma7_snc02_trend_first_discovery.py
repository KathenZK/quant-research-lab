from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import pytest
pytestmark = pytest.mark.local_data

ROOT = Path(__file__).resolve().parents[1]
BASE_SCRIPT = (
    ROOT
    / "research/hype/1d-ma7-asymmetric-body-trend/scripts/"
    "research_hype_1d_ma7_snc02_trend_first_discovery_audit.py"
)
BASE_ARTIFACT = (
    ROOT
    / "research/hype/1d-ma7-asymmetric-body-trend/artifacts/"
    "hype_1d_ma7_snc02_trend_first_discovery_audit_2026-08-20.json"
)
HCSM_ARTIFACT = (
    ROOT
    / "research/hype/1d-ma7-asymmetric-body-trend/artifacts/"
    "hype_1d_ma7_snc02_ema50_hierarchical_discovery_2026-08-20.json"
)


def load_module():
    spec = importlib.util.spec_from_file_location("snc02_trend_first_test", BASE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_control_parity_and_cross_audit_are_complete() -> None:
    payload = load(BASE_ARTIFACT)
    assert all(
        all(checks.values()) for checks in payload["control_parity"].values()
    )
    summary = payload["opportunity_summary"]
    assert summary["raw_cross_count"] == 103
    assert summary["accepted_cross_count"] == 40
    assert summary["rejected_cross_count"] == 63
    assert len(payload["cross_audit"]) == 103
    assert len(payload["rejected_crosses_ranked_by_mfe30"]) == 63


def test_naked_control_preserves_latest_trend_through_raw_recrosses() -> None:
    payload = load(BASE_ARTIFACT)
    latest = payload["trend_summaries"]["control"]["august_campaign"]
    assert payload["trend_summaries"]["control"]["august_09_long_to_terminal"]
    assert latest["entry_ts"] == "2026-08-09T00:00:00+00:00"
    assert latest["raw_ma7_recross_count"] == 2
    assert latest["terminal_censored"]
    assert math.isclose(latest["capture_ratio"], 0.8353162179085789)


def test_unfiltered_csm_recovers_opportunities_but_breaks_trend_gate() -> None:
    payload = load(BASE_ARTIFACT)
    summary = payload["opportunity_summary"]
    assert summary["recovered_major_by_csm02_count"] == 13
    assert summary["delayed_maturation_trade_count"] == 38
    assert summary["profitable_delayed_maturation_trade_count"] == 11
    assert not payload["trend_summaries"]["csm02"]["august_09_long_to_terminal"]
    assert not payload["verdict"]["csm02_continuation_worthy"]


def test_ema50_filter_still_fails_latest_continuity_and_capture() -> None:
    base = load(BASE_ARTIFACT)
    hcsm = load(HCSM_ARTIFACT)
    assert hcsm["opportunity_summary"]["delayed_trade_count"] == 16
    assert not hcsm["trend_summary"]["august_09_long_to_terminal"]
    assert (
        hcsm["trend_summary"]["major_mfe_weighted_capture"]
        < base["trend_summaries"]["control"]["major_mfe_weighted_capture"]
    )
    assert not hcsm["verdict"]["continuation_worthy"]


def test_artifact_sha256_sidecars() -> None:
    for artifact in (BASE_ARTIFACT, HCSM_ARTIFACT):
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        sidecar = Path(f"{artifact}.sha256").read_text(encoding="utf-8").split()[0]
        assert digest == sidecar
