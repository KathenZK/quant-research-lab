from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py"

P2_FEATURE_SPEC = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_feature_spec.json"
P2_MANIFEST = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_manifest.json"
P3R_FEATURE_SPEC = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_feature_spec.json"
P3R_MANIFEST = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_manifest.json"
P4_FACTOR_SPEC = ARTIFACT_DIR / "binance_1d_ma7_ctp_p4_factor_group_spec.json"
P4_CONTRACT_LOCK = ARTIFACT_DIR / "binance_1d_ma7_ctp_p4_contract_lock.json"
P4_SUMMARY = ARTIFACT_DIR / "binance_1d_ma7_ctp_p4_summary.json"
P4_MANIFEST = ARTIFACT_DIR / "binance_1d_ma7_ctp_p4_manifest.json"
P4_OOF = ARTIFACT_DIR / "binance_1d_ma7_ctp_p4_oof_predictions.parquet"
P4_COMPARISONS = ARTIFACT_DIR / "binance_1d_ma7_ctp_p4_ablation_comparisons.parquet"
P4_HOLDOUT = ARTIFACT_DIR / "binance_1d_ma7_ctp_p4_asset_holdout_metrics.parquet"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_module():
    spec = importlib.util.spec_from_file_location("binance_1d_ma7_ctp_p4_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def require_p4_summary() -> dict:
    if not P4_SUMMARY.exists():
        pytest.skip("P4 generated outputs are not available before the full run")
    return read_json(P4_SUMMARY)


def p2_f1_features() -> list[str]:
    mod = load_module()
    return mod.scheme_features(read_json(P2_FEATURE_SPEC), "F1_MA7_PATH")


def test_p2_p3_p3r_files_are_not_overwritten_by_p4_outputs() -> None:
    mod = load_module()
    p4_outputs = {path.name for path in mod.output_paths()}
    assert all(name.startswith("binance_1d_ma7_ctp_p4_") or name.startswith("binance-1d-ma7-ctp-p4-") for name in p4_outputs)
    assert P2_MANIFEST.exists()
    assert P3R_MANIFEST.exists()
    assert "binance_1d_ma7_ctp_p2_summary.json" not in p4_outputs
    assert "binance_1d_ma7_ctp_p3r_summary.json" not in p4_outputs


def test_factor_group_spec_builds_before_label_read_and_matches_p2_f1() -> None:
    mod = load_module()
    spec = mod.build_factor_group_spec(read_json(P2_FEATURE_SPEC), read_json(P3R_FEATURE_SPEC))
    p2_order = p2_f1_features()
    assert spec["frozen_before_p4_label_read"] is True
    assert spec["p2_original_field_order"] == p2_order
    assert spec["union_matches_p2_f1"] is True
    assert spec["duplicate_fields"] == []
    assert spec["missing_fields_vs_p2_f1"] == []
    assert spec["extra_fields_vs_p2_f1"] == []
    assert sum(spec["group_counts"].values()) == 69
    assert len(p2_order) == 69
    assert spec["group_counts"] == {
        "G1_T1_MA7_STATE": 12,
        "G2_EVENT_GEOMETRY": 13,
        "G3_VOLATILITY_STATE": 11,
        "G4_VOLUME_ACTIVITY": 5,
        "G5_T1_MOMENTUM_LOCATION": 21,
        "G6_T1_PATH_REGIME": 7,
    }


def test_candidate_feature_sets_are_exact_and_preregistered() -> None:
    mod = load_module()
    p2_order = p2_f1_features()
    assert len(mod.candidate_features_from_order(p2_order, "R_FULL_B0_69")) == 69
    assert len(mod.candidate_features_from_order(p2_order, "M_EVENT_25")) == 25
    assert len(mod.candidate_features_from_order(p2_order, "M_EVENT_VOL_36")) == 36
    for candidate, group in mod.DELETION_CANDIDATES.items():
        features = mod.candidate_features_from_order(p2_order, candidate)
        removed = set(mod.FACTOR_GROUPS[group])
        assert len(features) == 69 - len(removed)
        assert removed.isdisjoint(features)
        assert set(features) | removed == set(p2_order)
    for candidate, group in mod.ONLY_CANDIDATES.items():
        assert mod.candidate_features_from_order(p2_order, candidate) == [f for f in p2_order if f in set(mod.FACTOR_GROUPS[group])]


def test_forbidden_fields_never_enter_x() -> None:
    mod = load_module()
    p2_order = p2_f1_features()
    for candidate in mod.ALL_CANDIDATES:
        features = set(mod.candidate_features_from_order(p2_order, candidate))
        assert features.isdisjoint(mod.FORBIDDEN_IN_X)
        for feature in features:
            if feature == "t1_volatility_state_p0r":
                continue
            assert not any(token in feature.lower() for token in mod.FORBIDDEN_PATTERNS)
        assert "asset" not in features
        assert "side" not in features
        assert "side_sign" not in features


def test_bh_q_values_sort_by_p_value_not_candidate_name() -> None:
    mod = load_module()
    q = mod.bh_q_values({"z_large": 0.20, "a_small": 0.01, "m_mid": 0.04})
    assert q["a_small"] == pytest.approx(0.03)
    assert q["m_mid"] == pytest.approx(0.06)
    assert q["z_large"] == pytest.approx(0.20)
    assert q["a_small"] <= q["m_mid"] <= q["z_large"]


def test_contract_lock_status_after_run() -> None:
    if not P4_CONTRACT_LOCK.exists():
        pytest.skip("P4 contract lock is written by the full run")
    lock = read_json(P4_CONTRACT_LOCK)
    assert lock["status"] == "FROZEN_BEFORE_P4_LABEL_READ"
    assert lock["event_filter_audit_without_labels"]["labels_read"] is False
    assert lock["event_filter_audit_without_labels"]["n"] == 54137
    assert lock["factor_group_spec_sha256"] == sha256_file(P4_FACTOR_SPEC)
    assert lock["candidate_set_frozen"] == list(load_module().ALL_CANDIDATES)


def test_strict_sample_time_gate_and_isolation_after_run() -> None:
    summary = require_p4_summary()
    strict = summary["strict_event_audit"]
    assert strict["n"] == 52563
    assert strict["assets"] == 338
    assert strict["long"] == 26237
    assert strict["short"] == 26326
    assert strict["min_ts"] == "2019-11-27T00:00:00+00:00"
    assert strict["max_ts"] == "2024-12-10T00:00:00+00:00"
    assert strict["max_label_end_ts_20d"] == "2024-12-31T00:00:00+00:00"
    assert strict["non_cross"] == 0
    assert strict["duplicate_asset_ts"] == 0
    assert strict["null_target"] == 0
    assert strict["incomplete_20d_future_path"] == 0
    assert strict["feature_known_at_lt_entry_ts"] == 0
    assert strict["feature_known_at_eq_entry_ts"] == 52563
    assert strict["feature_known_at_gt_entry_ts"] == 0
    assert strict["entry_ts_eq_ts_plus_1d"] == 52563
    assert strict["feature_known_at_eq_ts_plus_1d"] == 52563
    assert summary["hype_isolation"]["event_rows"] == 0
    assert summary["hype_isolation"]["oof_rows"] == 0
    assert summary["input_integrity"]["post_2025_event_rows_read"] == 0
    assert summary["input_integrity"]["post_2025_prediction_rows_written"] == 0
    assert summary["tradfi_audit"]["strict_sample_known_tradfi_events"] == 0


def test_all_candidates_same_samples_purge_and_preprocessing_contract_after_run() -> None:
    summary = require_p4_summary()
    assert summary["development"]["all_candidates_use_same_samples"] is True
    for item in summary["development"]["purge_audit"]:
        assert item["purge_pass"] is True
        assert pd.Timestamp(item["train_label_end_max"]) < pd.Timestamp(item["validation_start"])
    assert summary["one_pooled_model_only"] is True
    assert summary["independent_long_short_heads_trained"] == 0
    card = read_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p4_model_card.json")
    assert card["not_live_ready"] is True
    assert "live trading" in card["prohibited_uses"]


def test_forward_calibration_uses_only_prior_folds_after_run() -> None:
    summary = require_p4_summary()
    for candidate, audits in summary["development"]["calibration_audit"].items():
        assert audits[0]["evaluation_fold"] == "D1"
        assert audits[0]["calibration_train_rows"] == 0
        for item in audits[1:]:
            assert item["temporal_isolation_pass"] is True, candidate
            assert pd.Timestamp(item["calibration_train_label_end_max"]) < pd.Timestamp(item["evaluation_start"])
    oof = pd.read_parquet(P4_OOF)
    for candidate in load_module().ALL_CANDIDATES:
        raw_col = f"p_{candidate.lower()}_raw"
        cal_col = f"p_{candidate.lower()}_calibrated_forward"
        assert raw_col in oof.columns
        assert cal_col in oof.columns
        assert (oof.loc[oof["fold"].eq("D1"), raw_col] == oof.loc[oof["fold"].eq("D1"), cal_col]).all()


def test_top10_is_fold_relative_and_oof_keys_unique_after_run() -> None:
    summary = require_p4_summary()
    oof = pd.read_parquet(P4_OOF)
    assert not oof.duplicated(["asset", "ts", "side"]).any()
    assert (oof["asset"] == "HYPE/USDT:USDT").sum() == 0
    assert pd.to_datetime(oof["ts"], utc=True).max() < pd.Timestamp("2025-01-01T00:00:00Z")
    assert pd.to_datetime(oof["label_end_ts_20d"], utc=True).max() < pd.Timestamp("2025-01-01T00:00:00Z")
    for candidate in load_module().ALL_CANDIDATES:
        pct_col = f"score_percentile_{candidate.lower()}"
        dec_col = f"score_decile_{candidate.lower()}"
        assert pct_col in oof.columns
        assert dec_col in oof.columns
        for _, group in oof.groupby("fold"):
            assert group[pct_col].between(0, 1).all()
            assert set(group[dec_col].unique()) == set(range(1, 11))
    assert summary["development"]["candidate_summary"]["R_FULL_B0_69"]["fold_relative_top10"]["definition"].startswith("score_percentile computed inside each validation fold")


def test_bootstrap_same_draw_and_manifest_hashes_after_run() -> None:
    summary = require_p4_summary()
    comparisons = pd.read_parquet(P4_COMPARISONS)
    assert comparisons["bootstrap_draw_hash"].nunique() == 1
    assert comparisons["bootstrap_draw_hash"].iloc[0] == summary["stability"]["bootstrap"]["paired_draw_counts_sha256"]
    manifest = read_json(P4_MANIFEST)
    assert manifest["hype_reveal_executed"] is False
    assert manifest["post_2025_predictions_written"] == 0
    for artifact in manifest["artifacts"]:
        path = ROOT / artifact["path"]
        assert path.exists(), artifact["path"]
        assert sha256_file(path) == artifact["sha256"], artifact["path"]


def test_time_asset_holdout_excludes_target_group_after_run() -> None:
    require_p4_summary()
    holdout = pd.read_parquet(P4_HOLDOUT)
    assert len(holdout[["fold", "held_asset_group"]].drop_duplicates()) == 15
    assert holdout["train_asset_group_excludes_target"].all()
    assert set(holdout["candidate"]).issuperset({"R_FULL_B0_69", "M_EVENT_25", "M_EVENT_VOL_36"})


def test_summary_compression_checks_include_final_asset_holdout_results_after_run() -> None:
    summary = require_p4_summary()
    comparisons = pd.read_parquet(P4_COMPARISONS)
    compressed = comparisons.loc[comparisons["comparison_family"].eq("compressed_candidate")]
    assert set(compressed["candidate"]) == {"M_EVENT_25", "M_EVENT_VOL_36"}
    for row in compressed.itertuples():
        expected_checks = json.loads(row.compression_gate_checks_json)
        recorded = summary["stability"]["compression_decisions"][row.candidate]
        assert recorded["decision"] == row.decision
        assert recorded["checks"] == expected_checks
        assert recorded["checks"]["asset_holdout_not_obviously_worse"] is False


def test_p4_did_not_generate_strategy_or_live_ready_artifacts_after_run() -> None:
    summary = require_p4_summary()
    assert summary["no_strategy_no_portfolio_no_live_artifact"] is True
    assert summary["decision"]["status"] == "explore / diagnostic-only / not promoted / not live-ready"
    forbidden_names = ["live", "handoff", "trade_path", "equity_curve", "positions", "sharpe"]
    p4_names = [path.name for path in ARTIFACT_DIR.glob("binance_1d_ma7_ctp_p4_*")]
    assert not any(any(token in name for token in forbidden_names) for name in p4_names)
