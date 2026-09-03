from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

import pandas as pd

import pytest
pytestmark = pytest.mark.local_data

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "research/hype/1d-ma7-machine-learning-trend/scripts/"
    "run_hype_1d_ma7_mlt_p4_v7_1_behavior_clone_residual.py"
)
ARTIFACT_DIR = ROOT / "research/hype/1d-ma7-machine-learning-trend/artifacts"
STEM = "hype_1d_ma7_mlt_p4_v7_1_behavior_clone_residual_2026-08-27"


def load_module():
    spec = importlib.util.spec_from_file_location("test_hype_ma7_mlt_p4", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_development_manifest_is_hashed_and_holdout_gated() -> None:
    manifest_path = ARTIFACT_DIR / f"{STEM}_development_manifest.json"
    digest_path = manifest_path.with_suffix(manifest_path.suffix + ".sha256")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert (
        hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        == digest_path.read_text(encoding="utf-8").split()[0]
    )
    assert manifest["train_days"] == 365
    assert manifest["total_days"] == 446
    assert manifest["clone_fit_gate"] is True
    assert manifest["residual_internal_gate"] is True
    assert manifest["holdout_permitted"] is True
    assert manifest["chosen_arm"] == "EXTEND_ONLY"


def test_clone_training_labels_stop_inside_first_365_days() -> None:
    predictions = pd.read_csv(ARTIFACT_DIR / f"{STEM}_clone_predictions.csv")
    assert pd.to_datetime(predictions["ts"], utc=True).max() <= pd.Timestamp(
        "2026-05-29T00:00:00Z"
    )
    assert pd.to_datetime(predictions["target_ts"], utc=True).max() <= pd.Timestamp(
        "2026-05-30T00:00:00Z"
    )
    assert len(predictions) == 362


def test_training_fit_and_oof_are_reported_separately() -> None:
    summary = json.loads(
        (ARTIFACT_DIR / f"{STEM}_development_summary.json").read_text(encoding="utf-8")
    )
    assert summary["clone"]["training_fit"]["accuracy"] == 1.0
    assert summary["clone"]["training_fit"]["transition_recall"] == 1.0
    assert summary["clone"]["expanding_oof"]["accuracy"] < 1.0
    assert summary["clone"]["expanding_oof"]["transition_recall"] < 1.0
    assert summary["teacher_v7_1"]["net_return_pct"] > 500.0
    assert (
        summary["residual"]["full_training_overlay"]["net_return_pct"]
        > summary["teacher_v7_1"]["net_return_pct"]
    )


def test_validation_is_frozen_failure_against_v7_1() -> None:
    summary = json.loads(
        (ARTIFACT_DIR / f"{STEM}_validation_summary.json").read_text(encoding="utf-8")
    )
    assert summary["boundary"]["days"] == 81
    assert summary["holdout_classification"] == "reused_holdout_not_clean_oos"
    assert summary["status"] == "V7_1_NOT_BEATEN"
    assert summary["v7_1_beaten"] is False
    assert (
        summary["ml_residual_overlay"]["net_return_pct"]
        < summary["teacher_v7_1"]["net_return_pct"]
    )


def test_overlay_keeps_teacher_entries_and_one_x_leverage() -> None:
    teacher = pd.read_csv(ARTIFACT_DIR / f"{STEM}_validation_teacher_trades.csv")
    overlay = pd.read_csv(ARTIFACT_DIR / f"{STEM}_validation_overlay_trades.csv")
    assert teacher[["entry_ts", "side", "entry_price"]].equals(
        overlay[["entry_ts", "side", "entry_price"]]
    )
    assert (overlay["entry_leverage"] == 1.0).all()
    changed = teacher["exit_ts"] != overlay["exit_ts"]
    assert changed.sum() == 1
    assert overlay.loc[changed, "exit_reason"].str.endswith("_ml_extend_3d").all()


def test_recent_slice_audit_has_terminal_parity_and_hash() -> None:
    path = ARTIFACT_DIR / f"{STEM}_recent_slices.json"
    sidecar = path.with_suffix(path.suffix + ".sha256")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest()
        == sidecar.read_text(encoding="utf-8").split()[0]
    )
    assert list(payload["arms"]["teacher_v7_1"]) == ["1d", "7d", "1m", "3m", "6m", "1y"]
    assert payload["arms"]["teacher_v7_1"]["3m"]["net_return_pct"] > 28.0
    assert payload["arms"]["ml_residual_overlay"]["3m"]["net_return_pct"] < 26.0


def test_v7_1_comparison_html_is_complete_and_interactive() -> None:
    html_path = ARTIFACT_DIR / f"{STEM}_v7_1_comparison_trade_paths.html"
    manifest_path = ARTIFACT_DIR / f"{STEM}_v7_1_comparison_trade_paths_manifest.json"
    for path in (html_path, manifest_path):
        sidecar = path.with_suffix(path.suffix + ".sha256")
        assert (
            hashlib.sha256(path.read_bytes()).hexdigest()
            == sidecar.read_text(encoding="utf-8").split()[0]
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["candles"] == 446
    assert manifest["ma7_points"] == 440
    assert manifest["equity_points"] == {"V7_1": 447, "P4": 447}
    assert manifest["trades_by_strategy"] == {"V7_1": 20, "P4": 20}
    assert manifest["paired_trades"] == 20
    assert manifest["changed_pairs"] == 7
    assert manifest["training_changed_pairs"] == 6
    assert manifest["validation_changed_pairs"] == 1
    assert manifest["line_render_count"] == 40
    assert manifest["entry_parity"] is True
    assert manifest["external_dependencies"] == 0

    html = html_path.read_text(encoding="utf-8")
    for token in (
        "setPointerCapture",
        "releasePointerCapture",
        "ondblclick=reset",
        "focusNextDiff",
        "focusTrain",
        "focusValidation",
        "DATA.window.boundaryT",
        "SMA7",
        "V7.1 实线",
        "P4 虚线",
        "黄色区域=延长持有",
    ):
        assert token in html
    match = re.search(r"const DATA=(.*),DAY=86400000", html)
    assert match is not None
    payload = json.loads(match.group(1))
    assert len(payload["candles"]) == 446
    assert len(payload["trades"]) == 40
    assert len(payload["pairs"]) == 20
    changed = [pair for pair in payload["pairs"] if pair["changed"]]
    assert len(changed) == 7
    assert sum(pair["segment"] == "training" for pair in changed) == 6
    validation_changed = [pair for pair in changed if pair["segment"] == "validation"]
    assert len(validation_changed) == 1
    assert validation_changed[0]["entryT"] == int(
        pd.Timestamp("2026-07-03T00:00:00Z").timestamp() * 1000
    )
    assert validation_changed[0]["teacherExitT"] == int(
        pd.Timestamp("2026-07-08T00:00:00Z").timestamp() * 1000
    )
    assert validation_changed[0]["overlayExitT"] == int(
        pd.Timestamp("2026-07-11T00:00:00Z").timestamp() * 1000
    )
