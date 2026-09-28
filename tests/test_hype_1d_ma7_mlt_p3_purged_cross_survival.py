from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest



ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "research/hype/1d-ma7-machine-learning-trend/scripts/"
    "run_hype_1d_ma7_mlt_p3_purged_cross_survival.py"
)
ARTIFACT_DIR = ROOT / "research/hype/1d-ma7-machine-learning-trend/artifacts"
STEM = "hype_1d_ma7_mlt_p3_purged_cross_survival_2026-08-27"


def load_module():
    spec = importlib.util.spec_from_file_location("test_hype_ma7_mlt_p3", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_feature_block_sizes_and_simple_tie_break() -> None:
    module = load_module()
    assert list(map(len, module.ENTRY_BLOCKS.values())) == [4, 8, 12, 16]
    assert list(map(len, module.SURVIVAL_BLOCKS.values())) == [6, 11, 15]
    results = {
        "small": {"available": True, "auc": 0.61, "feature_count": 4},
        "large": {"available": True, "auc": 0.619, "feature_count": 8},
    }
    assert module.choose_block(results) == "small"


@pytest.mark.local_data
def test_development_manifest_is_train_only_and_hashed() -> None:
    module = load_module()
    path = ARTIFACT_DIR / f"{STEM}_development_manifest.json"
    digest_path = path.with_suffix(path.suffix + ".sha256")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    expected = digest_path.read_text(encoding="utf-8").split()[0]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    assert manifest["data_boundary"]["daily_rows"] == module.TRAIN_DAYS
    assert manifest["data_boundary"]["last_ts"].startswith("2026-05-30")
    assert manifest["data_boundary"]["validation_rows_read_by_feature_pipeline"] == 0
    assert manifest["contract_sha256"] == hashlib.sha256(module.CONTRACT.read_bytes()).hexdigest()


@pytest.mark.local_data
def test_selected_blocks_and_validation_are_frozen_consistently() -> None:
    development = json.loads(
        (ARTIFACT_DIR / f"{STEM}_development_manifest.json").read_text(encoding="utf-8")
    )
    summary = json.loads(
        (ARTIFACT_DIR / f"{STEM}_summary.json").read_text(encoding="utf-8")
    )
    assert summary["selected"] == development["selected"]
    assert summary["development_manifest_sha256"] == hashlib.sha256(
        (ARTIFACT_DIR / f"{STEM}_development_manifest.json").read_bytes()
    ).hexdigest()
    assert summary["data"]["train_rows"] == 365
    assert summary["data"]["validation_rows"] == 81
    assert summary["verdict"] == "VALIDATION_FAILED"


@pytest.mark.local_data
def test_exact_cross_events_are_one_row_per_cross() -> None:
    module = load_module()
    _, p1, p0, full_market = module.load_dependencies()
    market = module.slice_market(full_market, module.TRAIN_DAYS)
    state = module.build_state(p1, p0, market)
    events = module.build_events(state, market)
    assert events["decision_index"].is_unique
    for event in events.to_dict("records"):
        index = int(event["decision_index"])
        side = int(event["side_value"])
        prior = state.iloc[index - 1]
        current = state.iloc[index]
        assert side * (float(prior["close"]) - float(prior["ma7"])) <= 0.0
        assert side * (float(current["close"]) - float(current["ma7"])) > 0.0


@pytest.mark.local_data
def test_training_labels_do_not_cross_training_boundary() -> None:
    module = load_module()
    p2, p1, p0, full_market = module.load_dependencies()
    market = module.slice_market(full_market, module.TRAIN_DAYS)
    state = module.build_state(p1, p0, market)
    events = module.build_events(state, market)
    labeled = module.label_entry_events(events, market, module.TRAIN_DAYS - 1, p2)
    survival = module.build_survival_rows(
        labeled,
        state,
        market,
        module.TRAIN_DAYS - 1,
        p2,
    )
    assert int(labeled["entry_label_end_index"].max()) <= module.TRAIN_DAYS - 1
    assert int(survival["survival_label_end_index"].max()) <= module.TRAIN_DAYS - 1
    group_weight = survival.groupby("cross_decision_index")["group_weight"].sum()
    assert (group_weight.sub(1.0).abs() < 1e-12).all()
