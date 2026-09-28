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
SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p3r_time_boundary_repair_context_feature_block_audit.py"

P3_FEATURE_SPEC = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_feature_spec.json"
P3_SUMMARY = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_summary.json"
P3R_FEATURE_SPEC = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_feature_spec.json"
P3R_CONTRACT_LOCK = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_contract_lock.json"
P3R_SUMMARY = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_summary.json"
P3R_MANIFEST = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_manifest.json"
P3R_OOF = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_oof_predictions.parquet"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_p3r_module():
    spec = importlib.util.spec_from_file_location("binance_1d_ma7_ctp_p3r_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def require_p3r_outputs() -> dict:
    if not P3R_SUMMARY.exists():
        pytest.skip("P3R generated outputs are not available before the full run")
    return read_json(P3R_SUMMARY)


def test_original_p3_remains_data_block_not_ready() -> None:
    summary = read_json(P3_SUMMARY)
    assert summary["decision"]["global_verdict"] == "DATA_BLOCK_NOT_READY"
    assert summary["decision"]["training_executed"] is False
    assert summary["strict_event_audit"]["feature_known_at_lt_entry_ts"] == 0
    assert summary["strict_event_audit"]["feature_known_at_eq_entry_ts"] == 52563
    assert summary["strict_event_audit"]["feature_known_at_before_entry_contract_pass"] is False


def test_p3r_feature_arrays_match_original_p3_exactly() -> None:
    p3 = read_json(P3_FEATURE_SPEC)
    p3r = read_json(P3R_FEATURE_SPEC)
    for key in ["feature_blocks", "candidate_feature_blocks", "categorical_features", "derived_features"]:
        assert p3r[key] == p3[key]
    assert p3r["source_inputs"]["original_p3_feature_spec"]["sha256"] == sha256_file(P3_FEATURE_SPEC)
    assert list(p3r["candidate_feature_blocks"]) == [
        "B0_P2_F1_LOGIT",
        "B1_LIQUIDITY_LOGIT",
        "B2_MA30_CONTEXT_LOGIT",
        "B3_CROSS_MARKET_LOGIT",
        "B4_FUNDING_LOGIT",
    ]
    assert "B_ALL" not in p3r["candidate_feature_blocks"]


def test_p3r_feature_spec_has_no_forbidden_x_fields() -> None:
    spec = read_json(P3R_FEATURE_SPEC)
    features = set()
    for blocks in spec["candidate_feature_blocks"].values():
        for block in blocks:
            features.update(spec["feature_blocks"][block])
    assert not (features & set(spec["forbidden_in_x"]))
    forbidden_substrings = ["open_interest", "taker", "market_cap", "future_", "label_", "net_return", "mfe", "mae"]
    assert all(not any(token in feature.lower() for token in forbidden_substrings) for feature in features)
    for forbidden in ["asset", "asset_slug", "side", "side_sign", "ts", "event_year"]:
        assert forbidden not in features


def test_p3r_time_boundary_helper_requires_equal_next_utc_open() -> None:
    p3r = load_p3r_module()
    frame = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"], utc=True),
            "feature_known_at": pd.to_datetime(["2024-01-02T00:00:00Z", "2024-01-03T00:00:00Z"], utc=True),
            "entry_ts": pd.to_datetime(["2024-01-02T00:00:00Z", "2024-01-03T00:00:00Z"], utc=True),
        }
    )
    audit = p3r.validate_p3r_time_boundary(frame)
    assert audit["feature_known_at_eq_entry_ts"] == 2
    assert audit["entry_ts_eq_ts_plus_1d"] == 2

    later_feature = frame.copy()
    later_feature.loc[0, "feature_known_at"] = pd.Timestamp("2024-01-02T01:00:00Z")
    with pytest.raises(RuntimeError, match="feature_known_at must equal entry_ts"):
        p3r.validate_p3r_time_boundary(later_feature)

    wrong_entry = frame.copy()
    wrong_entry.loc[0, "entry_ts"] = pd.Timestamp("2024-01-03T00:00:00Z")
    wrong_entry.loc[0, "feature_known_at"] = pd.Timestamp("2024-01-03T00:00:00Z")
    with pytest.raises(RuntimeError, match="entry_ts/feature_known_at must equal ts"):
        p3r.validate_p3r_time_boundary(wrong_entry)


def test_p3r_contract_lock_precedes_label_read() -> None:
    if not P3R_CONTRACT_LOCK.exists():
        pytest.skip("P3R contract lock is written by the full run")
    lock = read_json(P3R_CONTRACT_LOCK)
    assert lock["status"] == "FROZEN_BEFORE_P3R_LABEL_READ"
    assert lock["time_boundary_repair_only"] is True
    assert lock["event_filter_audit_without_labels"]["labels_read"] is False
    assert lock["event_filter_audit_without_labels"]["n"] == 54137
    assert lock["feature_spec_sha256"] == sha256_file(P3R_FEATURE_SPEC)


def test_p3r_strict_sample_and_isolation_after_run() -> None:
    summary = require_p3r_outputs()
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


def test_p3r_purge_and_forward_calibration_after_run() -> None:
    summary = require_p3r_outputs()
    for item in summary["development"]["purge_audit"]:
        assert item["purge_pass"] is True
        assert item["train_label_end_max"] < item["validation_start"]
    for audits in summary["development"]["calibration_audit"].values():
        assert audits[0]["evaluation_fold"] == "D1"
        assert audits[0]["calibration_train_rows"] == 0
        for item in audits[1:]:
            assert item["temporal_isolation_pass"] is True
            assert item["calibration_train_label_end_max"] < item["evaluation_start"]


def test_p3r_oof_has_unique_keys_and_no_2025_or_hype_after_run() -> None:
    if not P3R_OOF.exists():
        pytest.skip("P3R OOF predictions are written by the full run")
    oof = pd.read_parquet(P3R_OOF)
    assert not oof.duplicated(["asset", "ts", "side"]).any()
    assert (oof["asset"] == "HYPE/USDT:USDT").sum() == 0
    assert pd.to_datetime(oof["ts"], utc=True).max() < pd.Timestamp("2025-01-01T00:00:00Z")
    assert pd.to_datetime(oof["label_end_ts_20d"], utc=True).max() < pd.Timestamp("2025-01-01T00:00:00Z")


def test_p3r_manifest_hashes_match_after_run() -> None:
    if not P3R_MANIFEST.exists():
        pytest.skip("P3R manifest is written by the full run")
    manifest = read_json(P3R_MANIFEST)
    assert manifest["hype_reveal_executed"] is False
    assert manifest["post_2025_event_rows_read"] == 0
    assert manifest["post_2025_predictions_written"] == 0
    for artifact in manifest["artifacts"]:
        path = ROOT / artifact["path"]
        assert path.exists(), artifact["path"]
        assert sha256_file(path) == artifact["sha256"], artifact["path"]
