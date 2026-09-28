from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "research/hype/1d-ma7-machine-learning-trend/scripts/"
    "run_hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas.py"
)
ARTIFACT_DIR = ROOT / "research/hype/1d-ma7-machine-learning-trend/artifacts"
PREFIX = "hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31"


def load_subject():
    spec = importlib.util.spec_from_file_location("hype_p8_test_subject", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def require_artifacts(*paths: Path) -> None:
    missing = [path for path in paths if not path.exists()]
    if missing:
        pytest.skip("P8 retained artifacts unavailable: " + ", ".join(path.name for path in missing))


def assert_hashed(path: Path) -> None:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    assert sidecar.exists()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sidecar.read_text(encoding="utf-8").split()[0]


def test_p8_contract_constants_are_frozen() -> None:
    subject = load_subject()
    subject.self_test()
    assert len(subject.FAVORABLE_BARRIERS) * len(subject.ADVERSE_BARRIERS) * len(subject.HORIZONS) == 64
    assert subject.PRIMARY_FAVORABLE_ATR == 2.0
    assert subject.PRIMARY_ADVERSE_ATR == 1.0
    assert subject.PRIMARY_HORIZON_DAYS == 14
    assert subject.HYPE_FIRST_DAY == pd.Timestamp("2025-05-31T00:00:00Z")
    assert subject.HYPE_LAST_DAY == pd.Timestamp("2026-05-30T00:00:00Z")
    assert subject.TRAIN_TERMINAL == pd.Timestamp("2026-05-31T00:00:00Z")
    assert subject.DONOR_ASSETS == ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT")
    assert subject.FEE_RATE == 0.001
    assert subject.SLIPPAGE == 0.0004


@pytest.mark.local_data
def test_p8_development_manifest_locks_hype_holdout_and_hashes_sources() -> None:
    manifest_path = ARTIFACT_DIR / f"{PREFIX}_development_manifest.json"
    summary_path = ARTIFACT_DIR / f"{PREFIX}_summary.json"
    require_artifacts(manifest_path, summary_path)
    assert_hashed(manifest_path)
    assert_hashed(summary_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert manifest["holdout_read"] is False
    assert manifest["hype_days"] == 365
    assert manifest["hype_terminal"].startswith("2026-05-31")
    assert manifest["no_ml_trained"] is True
    assert "p7_loader" in manifest["source_modules"]
    assert summary["holdout_read"] is False
    assert summary["no_ml_trained"] is True
    assert summary["hype_window"]["feature_last_day"].startswith("2026-05-30")
    assert summary["hype_window"]["forbidden_holdout_start"].startswith("2026-05-31")
    assert not (ARTIFACT_DIR / f"{PREFIX}_validation_summary.json").exists()


@pytest.mark.local_data
def test_p8_events_and_first_hit_matrix_integrity() -> None:
    events_path = ARTIFACT_DIR / f"{PREFIX}_events.csv"
    matrix_path = ARTIFACT_DIR / f"{PREFIX}_first_hit_matrix.csv"
    require_artifacts(events_path, matrix_path)
    assert_hashed(events_path)
    assert_hashed(matrix_path)
    events = pd.read_csv(events_path)
    matrix = pd.read_csv(matrix_path)
    assert set(events["asset"].unique()) == {"HYPEUSDT", "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"}
    hype = events.loc[events["asset"] == "HYPEUSDT"].copy()
    assert pd.to_datetime(hype["ts"], utc=True).min() >= pd.Timestamp("2025-05-31T00:00:00Z")
    assert pd.to_datetime(hype["ts"], utc=True).max() <= pd.Timestamp("2026-05-30T00:00:00Z")
    assert not hype["hype_holdout_forbidden"].astype(bool).any()
    assert events["entry_is_next_utc_open"].astype(bool).all()
    assert (
        pd.to_datetime(events["entry_ts"], utc=True)
        == pd.to_datetime(events["ts"], utc=True) + pd.Timedelta(days=1)
    ).all()
    assert not events[list(load_subject().FEATURE_FIELDS)].isna().all(axis=None)
    assert (matrix.groupby("event_id").size() == 64).all()
    primary = matrix.loc[
        (matrix["favorable_atr"] == 2.0)
        & (matrix["adverse_atr"] == 1.0)
        & (matrix["horizon_days"] == 14)
    ]
    assert len(primary) == len(events)
    ambiguous = primary.loc[primary["ambiguous_same_hour"].astype(bool)]
    assert (ambiguous["conservative_result"] == "adverse").all()
    assert (ambiguous["optimistic_result"] == "favorable").all()
    assert set(events["side"].astype(int).unique()) == {-1, 1}


@pytest.mark.local_data
def test_p8_state_matrices_controls_and_bootstrap_exist() -> None:
    feature_path = ARTIFACT_DIR / f"{PREFIX}_feature_bin_stats.csv"
    two_way_path = ARTIFACT_DIR / f"{PREFIX}_two_way_state_matrix.csv"
    controls_path = ARTIFACT_DIR / f"{PREFIX}_matched_controls.csv"
    boot_path = ARTIFACT_DIR / f"{PREFIX}_cluster_bootstrap.csv"
    require_artifacts(feature_path, two_way_path, controls_path, boot_path)
    for path in (feature_path, two_way_path, controls_path, boot_path):
        assert_hashed(path)
    two_way = pd.read_csv(two_way_path)
    assert set(two_way["matrix"].unique()) == {
        "slope_x_cross_jump",
        "slope_x_prior_opposite_run",
        "slope_x_return3",
        "slope_x_cross_count14",
        "slope_x_vol_regime",
        "slope_x_rsi6",
        "direction_x_slope",
        "asset_x_direction",
        "asset_x_slope",
        "cross_jump_x_prior_opposite_run",
    }
    assert "INSUFFICIENT_SAMPLE" in set(two_way["sample_flag"].unique())
    controls = pd.read_csv(controls_path)
    assert {"B_NON_CROSS_SAME_SIDE", "C_MOMENTUM_7D", "D_RANDOM_MATCHED"}.issubset(
        set(controls["baseline"].unique())
    )
    boot = pd.read_csv(boot_path)
    assert {"all", "long", "short"}.issubset(set(boot["scope"].unique()))


@pytest.mark.local_data
def test_p8_html_contains_ma7_paths_and_interactivity() -> None:
    html_path = ARTIFACT_DIR / f"{PREFIX}.html"
    manifest_path = ARTIFACT_DIR / f"{PREFIX}_html_manifest.json"
    require_artifacts(html_path, manifest_path)
    assert_hashed(html_path)
    assert_hashed(manifest_path)
    html = html_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for token in (
        "MA7",
        "后81日未读取",
        "onmousedown",
        "onmousemove",
        "onwheel",
        "ondblclick",
        "focusEvent",
        "ctx.lineTo",
        "P8 MA7 Cross First-Hit Event Atlas",
    ):
        assert token in html
    assert "http://" not in html
    assert "https://" not in html
    match = re.search(r"const DATA = (.*?);\nconst DAY", html, re.S)
    assert match is not None
    payload = json.loads(match.group(1))
    assert payload["holdout_read"] is False
    assert payload["primary"] == {"favorable_atr": 2.0, "adverse_atr": 1.0, "horizon_days": 14}
    assert manifest["holdout_read"] is False
    assert manifest["has_ma7"] is True
    assert manifest["has_drag"] is True
    assert manifest["has_zoom"] is True
    assert manifest["has_reset"] is True
    assert manifest["has_focus"] is True
    assert manifest["path_line_count"] == manifest["primary_complete_events"]
