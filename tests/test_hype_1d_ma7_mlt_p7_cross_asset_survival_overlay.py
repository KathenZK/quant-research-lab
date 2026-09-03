from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pandas as pd

import pytest



ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "research/hype/1d-ma7-machine-learning-trend/scripts/"
    "run_hype_1d_ma7_mlt_p7_cross_asset_survival_overlay.py"
)
ARTIFACT_DIR = ROOT / "research/hype/1d-ma7-machine-learning-trend/artifacts"
PREFIX = "hype_1d_ma7_mlt_p7_cross_asset_survival_overlay_2026-08-28"


def load_subject():
    spec = importlib.util.spec_from_file_location("hype_p7_test_subject", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_survival_only_contract_excludes_hype_and_protective_stops() -> None:
    subject = load_subject()
    result = subject.self_test()
    assert result["heads"] == ["survival"]
    assert result["feature_count"] == 36
    assert result["hype_in_training_pool"] is False
    assert result["protective_stops_delegated"] is True
    assert "HYPEUSDT" not in subject.DONOR_ASSETS
    assert subject.DONOR_ASSETS == ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT")
    assert subject.EXTEND_START_THRESHOLD == 0.60
    assert subject.SURVIVAL_EXIT_THRESHOLD == 0.35
    assert subject.HOLDOUT_TERMINAL == pd.Timestamp("2026-08-20T00:00:00Z")
    assert subject.DEVELOPMENT_BOUNDARY == pd.Timestamp("2026-03-12T00:00:00Z")


def test_survival_features_match_frozen_p6_block() -> None:
    subject = load_subject()
    p5 = subject.load_module(subject.P5_SCRIPT, "hype_p7_test_p5")
    p6 = subject.load_module(subject.P6_SCRIPT, "hype_p7_test_p6")
    features = subject.survival_features(p5, p6)
    assert features == list(p5.ROOT_FEATURES) + list(p6.ENTRY_ADDITIONS) + list(
        p6.SURVIVAL_ADDITIONS
    )
    assert len(features) == 36


def test_calendar_oof_splits_by_timestamp_not_local_index() -> None:
    subject = load_subject()
    frame = pd.DataFrame(
        {
            "asset": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"],
            "index": [240, 240, 240, 240],
            "ts": [
                "2025-10-01T00:00:00+00:00",
                "2025-11-12T00:00:00+00:00",
                "2026-01-31T00:00:00+00:00",
                "2026-03-12T00:00:00+00:00",
            ],
            subject.COMPLETE: [True, True, True, True],
            subject.TARGET: [1, 0, 1, 0],
        }
    )
    before_boundary = subject.complete_rows_by_ts(
        frame, end=subject.DEVELOPMENT_BOUNDARY - pd.Timedelta(days=subject.PURGE_DAYS)
    )
    at_or_after_boundary = subject.complete_rows_by_ts(
        frame, start=subject.DEVELOPMENT_BOUNDARY
    )
    assert before_boundary["asset"].tolist() == ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    assert at_or_after_boundary["asset"].tolist() == ["SOLUSDT"]
    fold_two = subject.complete_rows_by_ts(
        frame,
        start=pd.Timestamp("2025-11-12T00:00:00Z"),
        end=pd.Timestamp("2025-12-22T00:00:00Z"),
    )
    assert fold_two["asset"].tolist() == ["ETHUSDT"]
    assert fold_two["index"].tolist() == [240]


def test_validation_cannot_run_without_frozen_manifest(tmp_path, monkeypatch) -> None:
    subject = load_subject()
    monkeypatch.setattr(subject, "MANIFEST_PATH", tmp_path / "missing.json")
    try:
        subject.validate()
    except RuntimeError as exc:
        assert "develop first" in str(exc)
    else:
        raise AssertionError("validation bypassed development manifest")


def test_locked_manifest_forbids_holdout_read(tmp_path, monkeypatch) -> None:
    subject = load_subject()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"holdout_permitted": False, "sources": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(subject, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(subject, "verify_manifest", lambda manifest: None)
    try:
        subject.validate()
    except RuntimeError as exc:
        assert "forbids holdout read" in str(exc)
    else:
        raise AssertionError("validation ignored holdout lock")


def test_overlay_refuses_trade_count_drift() -> None:
    subject = load_subject()
    p6 = subject.load_module(subject.P6_SCRIPT, "hype_p7_test_p6_overlay")

    def fake_extend(*args, **kwargs):
        return ([{"source": "core"}, {"source": "p6_supplemental"}], [])

    p6.extend_core_trades = fake_extend
    try:
        subject.apply_survival_overlay(
            None,
            p6,
            None,
            pd.DataFrame({"index": [0], "root_side": [1]}),
            [{"source": "core"}],
            pd.DataFrame({"index": [0], "probability": [0.9]}),
            1,
        )
    except RuntimeError as exc:
        assert "trade count" in str(exc)
    else:
        raise AssertionError("overlay accepted a supplemental trade")


@pytest.mark.local_data
def test_development_context_is_physically_train_only() -> None:
    subject = load_subject()
    p4 = subject.load_module(subject.P4_SCRIPT, "hype_p7_test_p4")
    _, _, _, _, context = subject.load_hype_context(p4, train_only=True)
    assert context.book.count == subject.TRAIN_DAYS == 365
    assert pd.Timestamp(context.book.terminal_ts) == subject.TRAIN_TERMINAL
    assert pd.Timestamp(context.market.audit["hourly_end"]) <= subject.TRAIN_TERMINAL
    assert pd.Timestamp(context.market.audit["funding_end"]) <= subject.TRAIN_TERMINAL
    assert context.original_harness is not None


@pytest.mark.local_data
def test_failed_development_manifest_keeps_holdout_locked() -> None:
    subject = load_subject()
    manifest = json.loads(
        (ARTIFACT_DIR / f"{PREFIX}_development_manifest.json").read_text(encoding="utf-8")
    )
    summary = json.loads(
        (ARTIFACT_DIR / f"{PREFIX}_development_summary.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "DEVELOPMENT_FAILED_HOLDOUT_LOCKED"
    assert manifest["development_gate"] is False
    assert manifest["holdout_permitted"] is False
    assert manifest["hype_in_training_pool"] is False
    assert tuple(manifest["donor_assets"]) == subject.DONOR_ASSETS
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
def test_donor_pool_excludes_hype_and_reported_metrics_are_reproducible() -> None:
    subject = load_subject()
    pool = pd.read_csv(ARTIFACT_DIR / f"{PREFIX}_donor_survival_rows.csv", usecols=["asset"])
    assert sorted(pool["asset"].unique()) == sorted(subject.DONOR_ASSETS)
    assert not any("HYPE" in asset.upper() for asset in pool["asset"].unique())
    summary = json.loads(
        (ARTIFACT_DIR / f"{PREFIX}_development_summary.json").read_text(encoding="utf-8")
    )
    assert summary["oof"]["auc"] == 0.6174935177182368
    confirmation = summary["development_gate"]["internal_confirmation"]
    assert confirmation["p7"]["net_return_pct"] == confirmation["v7_1"]["net_return_pct"]
    assert confirmation["p7"]["net_return_pct"] == 21.697801700630095
    assert confirmation["extended_trades"] == 0
    assert confirmation["p7"]["trades"] == confirmation["v7_1"]["trades"] == 2
    assert summary["development_gate"]["passed"] is False
    assert summary["hype_365_transfer_not_a_gate"]["p7"]["net_return_pct"] == 398.6088368127232
    assert summary["hype_365_transfer_not_a_gate"]["v7_1"]["net_return_pct"] == 515.7305076229405
