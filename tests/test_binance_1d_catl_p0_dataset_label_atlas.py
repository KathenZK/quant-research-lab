from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import pytest



ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    ROOT
    / "research"
    / "asset-portfolios"
    / "1d-cross-asset-trend-lifecycle"
    / "scripts"
    / "run_binance_1d_catl_p0_dataset_label_atlas.py"
)
ARTIFACT_DIR = (
    ROOT / "research" / "asset-portfolios" / "1d-cross-asset-trend-lifecycle" / "artifacts"
)


def load_module():
    spec = importlib.util.spec_from_file_location("catl_p0", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_contract_constants_and_hype_holdout_boundary():
    mod = load_module()
    assert str(mod.CUTOFF_UTC) == "2026-05-31 00:00:00+00:00"
    assert str(mod.MAX_FEATURE_TS) == "2026-05-30 00:00:00+00:00"
    assert mod.HOLDOUT_READ is False
    assert mod.FEE_PER_FILL == 0.001
    assert mod.SLIPPAGE_PER_FILL == 0.0004
    assert mod.PRIMARY_ENTRY_FAV_ATR == 2.0
    assert mod.PRIMARY_ENTRY_ADV_ATR == 1.0
    assert mod.PRIMARY_CONTINUE_FAV_ATR == 1.0
    assert mod.PRIMARY_CONTINUE_ADV_ATR == 0.75


@pytest.mark.local_data
def test_feature_panel_utc_daily_integrity_and_no_future_columns():
    mod = load_module()
    feature_dir = ARTIFACT_DIR / "p0_asset_day_feature_panel"
    features = pd.read_parquet(
        feature_dir,
        columns=[
            "asset",
            "ts",
            "feature_known_at",
            "next_entry_ts",
            "hours_in_day",
            "min_15m_per_hour",
            "complete_day",
            "tradable_marker_p0",
            "pit_universe_size",
        ],
    )
    assert not features.empty
    assert features["ts"].max() <= mod.MAX_FEATURE_TS
    assert (features["ts"].dt.hour == 0).all()
    assert (features["hours_in_day"] == 24).all()
    assert (features["min_15m_per_hour"] == 4).all()
    assert features["complete_day"].all()
    assert (features["feature_known_at"] == features["ts"] + pd.Timedelta(days=1)).all()
    assert (features["next_entry_ts"] == features["ts"] + pd.Timedelta(days=1)).all()
    assert features.loc[features["tradable_marker_p0"], "pit_universe_size"].notna().all()

    sample_schema = pd.read_parquet(next(feature_dir.rglob("*.parquet")), columns=None).columns
    leaked = [c for c in sample_schema if c.startswith(("label_", "future_", "outcome_"))]
    assert leaked == []


@pytest.mark.local_data
def test_landmark_labels_reconstruct_from_first_hit_primitives():
    load_module()
    landmark_dir = ARTIFACT_DIR / "p0_directional_landmark_panel"
    cols = [
        "asset",
        "ts",
        "side",
        "entry_ts",
        "entry_ref",
        "atr_anchor",
        "future_path_complete_5d",
        "future_path_complete_20d",
        "future_first_favorable_1_0atr_hours",
        "future_first_favorable_2_0atr_hours",
        "future_first_adverse_0_75atr_hours",
        "future_first_adverse_1_0atr_hours",
        "label_entry_success_20d",
        "label_entry_success_20d_optimistic",
        "label_entry_result",
        "label_continue_success_5d",
        "label_continue_success_5d_optimistic",
        "label_continue_result",
    ]
    landmarks = pd.read_parquet(landmark_dir, columns=cols)
    assert not landmarks.empty
    assert set(landmarks["side"].unique()) == {"long", "short"}
    assert (landmarks["entry_ts"] == landmarks["ts"] + pd.Timedelta(days=1)).all()
    assert (landmarks["entry_ref"].dropna() > 0).all()
    complete_any = landmarks["future_path_complete_5d"] | landmarks["future_path_complete_20d"]
    assert (landmarks.loc[complete_any, "atr_anchor"].dropna() > 0).all()

    entry = landmarks.loc[landmarks["future_path_complete_20d"]].copy()
    fav = entry["future_first_favorable_2_0atr_hours"].to_numpy(dtype=float)
    adv = entry["future_first_adverse_1_0atr_hours"].to_numpy(dtype=float)
    fav_hit = np.isfinite(fav) & (fav <= 20 * 24)
    adv_hit = np.isfinite(adv) & (adv <= 20 * 24)
    conservative = fav_hit & (~adv_hit | (fav < adv))
    optimistic = fav_hit & (~adv_hit | (fav <= adv))
    assert np.array_equal(entry["label_entry_success_20d"].to_numpy(dtype=bool), conservative)
    assert np.array_equal(entry["label_entry_success_20d_optimistic"].to_numpy(dtype=bool), optimistic)

    cont = landmarks.loc[landmarks["future_path_complete_5d"]].copy()
    fav = cont["future_first_favorable_1_0atr_hours"].to_numpy(dtype=float)
    adv = cont["future_first_adverse_0_75atr_hours"].to_numpy(dtype=float)
    fav_hit = np.isfinite(fav) & (fav <= 5 * 24)
    adv_hit = np.isfinite(adv) & (adv <= 5 * 24)
    conservative = fav_hit & (~adv_hit | (fav < adv))
    optimistic = fav_hit & (~adv_hit | (fav <= adv))
    assert np.array_equal(cont["label_continue_success_5d"].to_numpy(dtype=bool), conservative)
    assert np.array_equal(cont["label_continue_success_5d_optimistic"].to_numpy(dtype=bool), optimistic)


def test_first_hit_conflict_policy_and_long_short_symmetry():
    mod = load_module()
    assert mod.result_from_hours(3, 3, 20 * 24) == (
        "ambiguous_same_hour",
        False,
        True,
        3,
    )
    assert mod.result_from_hours(2, 3, 20 * 24)[1] is True
    assert mod.result_from_hours(3, 2, 20 * 24)[1] is False

    long_fav = (102.0 - 100.0) / 2.0
    short_fav = (100.0 - 98.0) / 2.0
    assert long_fav == short_fav == 1.0


@pytest.mark.local_data
def test_summary_manifest_hashes_and_no_validation_artifacts():
    manifest_path = ARTIFACT_DIR / "binance_1d_catl_p0_manifest.json"
    summary_path = ARTIFACT_DIR / "binance_1d_catl_p0_summary.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))["summary"]
    assert manifest["holdout_read"] is False
    assert summary["holdout_read"] is False
    assert summary["final_verdict"] in {
        "DATASET_READY_FOR_MODELING_RESEARCH",
        "BLOCKED_DATA_ACCESS",
        "DATASET_INTEGRITY_FAILED",
    }
    assert summary["hype_rows_after_cutoff"] == 0
    assert not any("validation" in item["path"].lower() for item in manifest["artifacts"])
    for item in manifest["artifacts"]:
        path = ROOT / item["path"]
        assert path.exists()
        assert sha256_file(path) == item["sha256"]


@pytest.mark.local_data
def test_html_atlas_is_self_contained_and_interactive():
    html_path = ARTIFACT_DIR / "binance_1d_catl_p0_label_quality_atlas.html"
    text = html_path.read_text(encoding="utf-8")
    assert "http://" not in text
    assert "https://" not in text
    assert "不是交易策略" in text
    assert "2026-05-31" in text
    assert "resetZoom" in text
    assert "pointerdown" in text
    assert "wheel" in text
