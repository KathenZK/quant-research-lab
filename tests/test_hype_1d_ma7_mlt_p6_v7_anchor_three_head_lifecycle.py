from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

import pytest



ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "research/hype/1d-ma7-machine-learning-trend/scripts/"
    "run_hype_1d_ma7_mlt_p6_v7_anchor_three_head_lifecycle.py"
)
ARTIFACT_DIR = ROOT / "research/hype/1d-ma7-machine-learning-trend/artifacts"
PREFIX = "hype_1d_ma7_mlt_p6_v7_anchor_three_head_lifecycle_2026-08-28"


def load_subject():
    spec = importlib.util.spec_from_file_location("hype_p6_test_subject", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_three_head_contract_and_protective_stop_delegation() -> None:
    subject = load_subject()
    result = subject.self_test()
    assert result["three_heads"] == ["entry", "survival", "reversal"]
    assert result["protective_stops_delegated"] is True
    assert subject.ENTRY_THRESHOLD == 0.65
    assert subject.EXTEND_START_THRESHOLD == 0.60
    assert subject.SURVIVAL_EXIT_THRESHOLD == 0.35
    assert subject.REVERSAL_THRESHOLD == 0.70


@pytest.mark.local_data
def test_development_context_is_physically_train_only() -> None:
    subject = load_subject()
    p4 = subject.load_module(subject.P4_SCRIPT, "hype_p6_test_p4")
    _, _, _, _, context = p4.load_dependencies(train_only=True)
    assert context.book.count == subject.TRAIN_DAYS == 365
    assert pd.Timestamp(context.market.audit["hourly_end"]) <= pd.Timestamp(
        context.book.terminal_ts
    )
    assert pd.Timestamp(context.market.audit["funding_end"]) <= pd.Timestamp(
        context.book.terminal_ts
    )


def test_validation_cannot_run_without_frozen_manifest(tmp_path, monkeypatch) -> None:
    subject = load_subject()
    monkeypatch.setattr(subject, "MANIFEST_PATH", tmp_path / "missing.json")
    try:
        subject.validate()
    except RuntimeError as exc:
        assert "develop first" in str(exc)
    else:
        raise AssertionError("validation bypassed development manifest")


def test_complete_rows_honors_time_and_label_boundary() -> None:
    subject = load_subject()
    frame = pd.DataFrame(
        {
            "index": [0, 1, 2, 3],
            "complete": [True, True, False, True],
            "target": [0.0, 1.0, float("nan"), 1.0],
        }
    )
    result = subject.complete_rows(frame, "target", "complete", 1, 3)
    assert result["index"].tolist() == [1]


@pytest.mark.local_data
def test_failed_development_manifest_keeps_holdout_locked() -> None:
    subject = load_subject()
    manifest_path = ARTIFACT_DIR / f"{PREFIX}_development_manifest.json"
    summary_path = ARTIFACT_DIR / f"{PREFIX}_development_summary.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "DEVELOPMENT_FAILED_HOLDOUT_LOCKED"
    assert manifest["development_gate"] is False
    assert manifest["holdout_permitted"] is False
    assert summary["data_boundary"]["holdout_read"] is False
    assert not (ARTIFACT_DIR / f"{PREFIX}_validation_summary.json").exists()
    subject.verify_manifest(manifest)


@pytest.mark.local_data
def test_development_artifacts_match_frozen_hashes() -> None:
    subject = load_subject()
    manifest = json.loads(
        (ARTIFACT_DIR / f"{PREFIX}_development_manifest.json").read_text(encoding="utf-8")
    )
    for artifact in manifest["development_artifacts"].values():
        path = ROOT / artifact["path"]
        assert path.exists()
        assert subject.sha256(path) == artifact["sha256"]


@pytest.mark.local_data
def test_reported_oof_and_confirmation_failure_are_reproducible() -> None:
    summary = json.loads(
        (ARTIFACT_DIR / f"{PREFIX}_development_summary.json").read_text(encoding="utf-8")
    )
    assert summary["oof"]["entry"]["auc"] == 0.5807291666666666
    assert summary["oof"]["survival"]["auc"] == 0.5296769346356123
    assert summary["oof"]["reversal"]["auc"] == 0.5138888888888888
    confirmation = summary["development_gate"]["internal_confirmation"]
    assert confirmation["p6"]["net_return_pct"] == 9.34115717438262
    assert confirmation["v7_1"]["net_return_pct"] == 21.697801700630095
    assert summary["development_gate"]["passed"] is False


@pytest.mark.local_data
def test_exported_trade_returns_are_complete_and_match_summary() -> None:
    summary = json.loads(
        (ARTIFACT_DIR / f"{PREFIX}_development_summary.json").read_text(encoding="utf-8")
    )
    for label, node in [
        ("training", summary["full_training_resubstitution"]["p6"]),
        ("internal_confirmation", summary["development_gate"]["internal_confirmation"]["p6"]),
    ]:
        trades = pd.read_csv(ARTIFACT_DIR / f"{PREFIX}_{label}_trades.csv")
        assert trades["net_return"].notna().all()
        assert np.allclose(
            trades["net_return"].to_numpy(), node["per_trade_returns"], rtol=0.0, atol=1e-15
        )


@pytest.mark.local_data
def test_future_labels_end_inside_training_boundary() -> None:
    cases = [
        ("entry", "entry_label_complete", "entry_value"),
        ("survival", "survival_label_complete", "survival_3d"),
        ("reversal", "reversal_label_complete", "reversal_value"),
    ]
    for name, complete, target in cases:
        rows = pd.read_csv(ARTIFACT_DIR / f"{PREFIX}_{name}_rows.csv")
        known = rows.loc[rows[complete].astype(bool) & rows[target].notna()]
        assert int(known["index"].max()) < 365
        assert pd.Timestamp(known["ts"].max()) < pd.Timestamp("2026-05-31T00:00:00Z")
