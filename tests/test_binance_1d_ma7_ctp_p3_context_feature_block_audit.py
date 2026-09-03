import hashlib
import json
from pathlib import Path

import pytest
pytestmark = pytest.mark.local_data

ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"

FEATURE_SPEC = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_feature_spec.json"
P2_FEATURE_SPEC = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_feature_spec.json"
SUMMARY = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_summary.json"
MANIFEST = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_manifest.json"
CONTRACT_LOCK = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_contract_lock.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def p2_scheme_features(feature_spec: dict, scheme: str) -> list[str]:
    features = []
    for block in feature_spec["schemes"][scheme]:
        features.extend(feature_spec["feature_blocks"][block])
    return features


def test_p3_feature_spec_freezes_only_b0_plus_single_blocks() -> None:
    spec = read_json(FEATURE_SPEC)
    p2 = read_json(P2_FEATURE_SPEC)
    assert spec["feature_blocks"]["B0_P2_F1"] == p2_scheme_features(p2, "F1_MA7_PATH")
    assert list(spec["candidate_feature_blocks"]) == [
        "B0_P2_F1_LOGIT",
        "B1_LIQUIDITY_LOGIT",
        "B2_MA30_CONTEXT_LOGIT",
        "B3_CROSS_MARKET_LOGIT",
        "B4_FUNDING_LOGIT",
    ]
    assert "B_ALL" not in spec["candidate_feature_blocks"]
    assert spec["feature_blocks"]["B1_LIQUIDITY_SIZE_PROXY"] == [
        "liquidity_rank_pct_p0r",
        "log1p_listing_age_days",
        "liquidity_rank_centered_sq",
    ]
    assert spec["feature_blocks"]["B4_FUNDING_CARRY"][0] == "funding_missing"


def test_p3_feature_spec_has_no_identity_or_outcome_leakage() -> None:
    spec = read_json(FEATURE_SPEC)
    features = set()
    for blocks in spec["candidate_feature_blocks"].values():
        for block in blocks:
            features.update(spec["feature_blocks"][block])
    assert not (features & set(spec["forbidden_in_x"]))
    forbidden_substrings = ["open_interest", "taker", "market_cap", "future_", "label_", "net_return", "mfe", "mae"]
    assert all(not any(token in feature.lower() for token in forbidden_substrings) for feature in features)
    assert "side" not in features
    assert "side_sign" not in features
    assert "asset" not in features
    assert "ts" not in features


def test_p3_stopped_before_training_on_feature_known_at_gate() -> None:
    summary = read_json(SUMMARY)
    assert summary["decision"]["global_verdict"] == "DATA_BLOCK_NOT_READY"
    assert summary["decision"]["training_executed"] is False
    assert summary["decision"]["oof_predictions_written"] is False
    assert summary["raw_event_audit_without_labels"]["n"] == 54137
    strict = summary["strict_event_audit"]
    assert strict["n"] == 52563
    assert strict["assets"] == 338
    assert strict["long"] == 26237
    assert strict["short"] == 26326
    assert strict["max_ts"] == "2024-12-10T00:00:00+00:00"
    assert strict["max_label_end_ts_20d"] == "2024-12-31T00:00:00+00:00"
    assert strict["non_cross"] == 0
    assert strict["null_target"] == 0
    assert strict["incomplete_20d_future_path"] == 0
    assert strict["feature_known_at_lt_entry_ts"] == 0
    assert strict["feature_known_at_eq_entry_ts"] == 52563
    assert strict["feature_known_at_gt_entry_ts"] == 0
    assert strict["feature_known_at_before_entry_contract_pass"] is False


def test_p3_hype_isolated_and_hyper_preserved_at_input_layer() -> None:
    summary = read_json(SUMMARY)
    assert summary["hype_isolation"]["input_rows"] == 0
    assert summary["hype_isolation"]["event_rows"] == 0
    assert summary["hype_isolation"]["oof_rows"] == 0
    assert summary["hype_isolation"]["model_card_rows"] == 0
    assert summary["hype_isolation"]["hype_reveal_executed"] is False
    assert summary["hyper_preservation"]["input_rows"] == 806
    assert summary["input_integrity"]["post_2025_event_rows_read"] == 0
    assert summary["input_integrity"]["post_2025_prediction_rows_written"] == 0


def test_p3_contract_lock_precedes_label_read_and_records_event_audit() -> None:
    lock = read_json(CONTRACT_LOCK)
    assert lock["status"] == "FROZEN_BEFORE_P3_LABEL_READ"
    assert lock["event_filter_audit_without_labels"]["labels_read"] is False
    assert lock["event_filter_audit_without_labels"]["n"] == 54137
    assert lock["event_filter_audit_without_labels"]["hype"] == 0
    assert lock["contract_sha256"] == sha256_file(FAMILY_DIR / "specs/binance-1d-ma7-ctp-p3-context-feature-block-audit-contract-2026-09-01.md")
    assert lock["feature_spec_sha256"] == sha256_file(FEATURE_SPEC)


def test_p3_did_not_emit_training_or_live_ready_artifacts_after_data_gate() -> None:
    summary = read_json(SUMMARY)
    for rel in summary["not_generated_due_to_data_gate"]:
        assert not (FAMILY_DIR / rel).exists()
    for rel in [
        "live-specs/binance-1d-ma7-ctp-p3.md",
        "artifacts/binance_1d_ma7_ctp_p3_equity_curve.parquet",
        "artifacts/binance_1d_ma7_ctp_p3_positions.parquet",
    ]:
        assert not (FAMILY_DIR / rel).exists()


def test_p3_manifest_hashes_match_generated_failure_artifacts() -> None:
    manifest = read_json(MANIFEST)
    assert manifest["decision"] == "DATA_BLOCK_NOT_READY"
    assert manifest["training_executed"] is False
    assert manifest["hype_reveal_executed"] is False
    for artifact in manifest["artifacts"]:
        path = ROOT / artifact["path"]
        assert path.exists(), artifact["path"]
        assert sha256_file(path) == artifact["sha256"], artifact["path"]
