from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
P1E_SCRIPT = ROOT / (
    "research/asset-portfolios/1d-ma7-taker-flow-meta-label/"
    "scripts/research_binance_1d_ma7_tfml_p1e.py"
)
FLOW_SYNC_SCRIPT = ROOT / (
    "research/asset-portfolios/1d-ma7-taker-flow-meta-label/"
    "scripts/sync_binance_vision_tfml_p0e_5m.py"
)
PRICE_SYNC_SCRIPT = ROOT / (
    "research/asset-portfolios/1d-ma7-taker-flow-meta-label/"
    "scripts/sync_binance_tfml_p0e_price_funding.py"
)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p1e = load_module(P1E_SCRIPT, "tfml_p1e_test_module")
flow_sync = load_module(FLOW_SYNC_SCRIPT, "tfml_p0e_flow_sync_test_module")
price_sync = load_module(PRICE_SYNC_SCRIPT, "tfml_p0e_price_sync_test_module")


def passing_full_summary() -> dict:
    return {
        "side_counts": {"long": 80, "short": 80},
        "choice_frequency": {
            "alpha=1000|threshold=0.0010|route=combined": 24
        },
        "selected_events": 160,
        "per_asset": {
            asset: {"selected": {"events": 20}} for asset in p1e.FRESH_ASSETS
        },
        "selected_90d_blocks": 24,
        "main": {"mean": 0.001, "profit_factor": 1.2},
        "positive_asset_count": 6,
        "positive_outer_fold_count": 24,
        "ranking_spearman": 0.04,
        "positive_ranking_asset_count": 6,
        "cluster_bootstrap": {"positive_probability": 0.90},
        "variants": {
            column: {"mean": 0.001, "profit_factor": 1.1}
            for column in ("z_4bps", "z_funding_off", "z_lag1")
        },
        "lag_executable_rate": 0.75,
        "dual_improved_asset_count": 5,
    }


def test_fresh_universe_is_disjoint_and_hype_locked() -> None:
    assert len(p1e.LEGACY_ASSETS) == 5
    assert len(p1e.FRESH_ASSETS) == 8
    assert not set(p1e.LEGACY_ASSETS) & set(p1e.FRESH_ASSETS)
    assert len(p1e.ALL_ASSETS) == 13
    assert "HYPE" not in p1e.ALL_ASSETS
    assert tuple(flow_sync.FRESH_ASSETS) == p1e.FRESH_ASSETS
    assert {
        values[0] for values in price_sync.SYMBOLS.values()
    } == set(p1e.FRESH_ASSETS)


def test_scaled_gate_requires_fresh_asset_and_fold_coverage() -> None:
    capacity = {"p0e_capacity_pass": True}
    delta = {"positive_probability": 0.90}
    importance = {
        "flow_a": {"folds": 24, "median": 0.001},
        "flow_b": {"folds": 24, "median": 0.001},
    }
    full = passing_full_summary()
    gate = p1e.apply_gate(
        capacity=capacity,
        full=full,
        delta=delta,
        importance=importance,
    )
    assert gate["development_gate_pass"]

    insufficient_asset = copy.deepcopy(full)
    insufficient_asset["per_asset"]["XRP"]["selected"]["events"] = 14
    assert not p1e.apply_gate(
        capacity=capacity,
        full=insufficient_asset,
        delta=delta,
        importance=importance,
    )["checks"]["accepted_total_and_per_asset"]

    insufficient_folds = copy.deepcopy(full)
    insufficient_folds["positive_outer_fold_count"] = 23
    assert not p1e.apply_gate(
        capacity=capacity,
        full=insufficient_folds,
        delta=delta,
        importance=importance,
    )["checks"]["positive_outer_folds"]


def test_importance_cannot_pass_with_legacy_fold_count() -> None:
    importance = {
        "flow_a": {"folds": 23, "median": 0.001},
        "flow_b": {"folds": 23, "median": 0.001},
    }
    gate = p1e.apply_gate(
        capacity={"p0e_capacity_pass": True},
        full=passing_full_summary(),
        delta={"positive_probability": 0.90},
        importance=importance,
    )
    assert not gate["checks"]["flow_permutation_importance"]


def test_expansion_preserves_original_model_contract() -> None:
    base = p1e.load_base_module()
    assert len(base.PRICE_FEATURES) == 47
    assert len(base.FLOW_FEATURES) == 23
    assert len(base.FULL_FEATURES) == 70
    assert base.ALPHA_GRID == (1.0, 10.0, 100.0, 300.0, 1000.0)
    assert base.THRESHOLD_GRID == (0.0, 0.0005, 0.0010, 0.0015)
    assert "asset" not in base.FULL_FEATURES


def test_exposed_global_aggregate_result_is_fail_closed() -> None:
    with pytest.raises(RuntimeError, match="global 13-asset panel"):
        p1e.enforce_fold_local_aggregate_pipeline()


def test_empty_source_manifest_cannot_satisfy_identity_gate(
    tmp_path: Path,
) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "binance-1d-ma7-tfml-p0-manifest-v1",
                "files": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="file identity mismatch"):
        p1e.verify_file_manifest(
            tmp_path,
            expected_schema="binance-1d-ma7-tfml-p0-manifest-v1",
            required_files={"source_manifest", "data_quality"},
        )


@pytest.mark.local_data
def test_retained_p0e_inputs_fail_closed_on_lost_generator_source() -> None:
    assert p1e.verify_event_manifest()["file_count"] == 2
    flow = p1e.verify_flow_manifest(
        p1e.FRESH_FLOW_DIR,
        expected_assets=p1e.FRESH_ASSETS,
        expected_archives=491,
        expected_bytes=169_255_752,
    )
    assert flow["archive_count"] == 491
    payload = json.loads(p1e.PRICE_QUALITY_PATH.read_text(encoding="utf-8"))
    assert payload["provenance_blocker_count"] == 1
    assert not payload["provenance"]["generator_source_retained"]
    with pytest.raises(RuntimeError, match="source identity mismatch"):
        p1e.verify_price_quality()
