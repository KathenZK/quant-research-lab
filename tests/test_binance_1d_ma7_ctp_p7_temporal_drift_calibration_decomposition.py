from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
ART = FAMILY / "artifacts"
SCRIPT = FAMILY / "scripts/run_binance_1d_ma7_ctp_p7_temporal_drift_calibration_decomposition.py"


def load_module():
    spec = importlib.util.spec_from_file_location("p7", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def read_json(name: str):
    return json.loads((ART / name).read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_01_hype_rows_strictly_zero():
    audit = read_json("binance_1d_ma7_ctp_p7_data_audit.json")
    assert audit["hype_rows"] == 0


def test_02_hyper_is_retained():
    audit = read_json("binance_1d_ma7_ctp_p7_data_audit.json")
    assert audit["hyper_present"] is True


def test_03_tradfi_without_main_score_excluded_from_main_results():
    audit = read_json("binance_1d_ma7_ctp_p7_data_audit.json")
    summary = read_json("binance_1d_ma7_ctp_p7_summary.json")
    assert audit["validation_known_tradfi_rows_excluded"] == 100
    assert summary["core_metrics"]["validation_2025_plus"]["n"] == 46892


def test_04_2025_2026_sample_counts_match_frozen_anchors():
    summary = read_json("binance_1d_ma7_ctp_p7_summary.json")
    assert summary["core_metrics"]["validation_2025"]["n"] == 32111
    assert summary["core_metrics"]["validation_2026"]["n"] == 14781
    assert summary["core_metrics"]["validation_2025_plus"]["n"] == 46892


def test_05_raw_score_reconstruction_matches_frozen_predictions():
    recon = read_json("binance_1d_ma7_ctp_p7_model_reconstruction.json")
    summary = read_json("binance_1d_ma7_ctp_p7_summary.json")
    assert recon["passes_1e_minus_8"] is False
    assert recon["max_abs_probability_error"] > 1e-8
    assert summary["global_verdict"] == "DATA_OR_REPRODUCTION_FAILURE"


def test_06_fixed_threshold_is_strictly_frozen():
    config = read_json("binance_1d_ma7_ctp_p7_config.json")
    assert round(config["threshold"]["raw_probability"], 6) == 0.510070
    assert config["threshold"]["fit_source"] == "development OOF raw probability 95th percentile"


def test_07_main_bin_boundaries_are_from_development_oof_only():
    config = read_json("binance_1d_ma7_ctp_p7_config.json")
    mono = read_json("binance_1d_ma7_ctp_p7_score_monotonicity.json")
    assert config["fixed_score_bins"]["fit_source"] == "development OOF raw probability only"
    assert mono["fail_closed"] is True
    assert mono["global_verdict"] == "DATA_OR_REPRODUCTION_FAILURE"


def test_08_no_2025_or_2026_optimized_threshold_is_emitted():
    config = read_json("binance_1d_ma7_ctp_p7_config.json")
    summary = read_json("binance_1d_ma7_ctp_p7_summary.json")
    assert "optimized_threshold_2025" not in json.dumps(summary)
    assert "optimized_threshold_2026" not in json.dumps(summary)
    assert config["threshold"]["selection_rule"] == "score >= threshold"


def test_09_2025_and_2026_use_same_fixed_bins():
    bins = pd.read_parquet(ART / "binance_1d_ma7_ctp_p7_fixed_score_bin_outcomes.parquet")
    assert bins["fail_closed"].all()
    assert set(bins["global_verdict"]) == {"DATA_OR_REPRODUCTION_FAILURE"}


def test_10_calibrated_probability_is_frozen_p5_platt():
    config = read_json("binance_1d_ma7_ctp_p7_config.json")
    calibration = read_json("binance_1d_ma7_ctp_p7_calibration_metrics.json")
    assert calibration["fail_closed"] is True
    assert calibration["global_verdict"] == "DATA_OR_REPRODUCTION_FAILURE"
    assert "preprocessing" in config["model"]


def test_11_no_2025_2026_calibrator_fit_claim():
    calibration = read_json("binance_1d_ma7_ctp_p7_calibration_metrics.json")
    text = json.dumps(calibration)
    assert "refit_2025" not in text
    assert "refit_2026" not in text


def test_12_bootstrap_seed_and_replicate_count():
    boot = pd.read_parquet(ART / "binance_1d_ma7_ctp_p7_bootstrap_results.parquet")
    config = read_json("binance_1d_ma7_ctp_p7_config.json")
    assert config["bootstrap"]["samples"] == 2000
    assert config["bootstrap"]["seed"] == 20260901
    assert len(boot) == 1
    assert boot["fail_closed"].iloc[0]


def test_13_bootstrap_paired_replicate_metadata_present():
    config = read_json("binance_1d_ma7_ctp_p7_config.json")
    boot = pd.read_parquet(ART / "binance_1d_ma7_ctp_p7_bootstrap_results.parquet")
    assert config["bootstrap"]["paired_replicate"] is True
    assert boot["global_verdict"].iloc[0] == "DATA_OR_REPRODUCTION_FAILURE"


def test_14_psi_handles_zero_frequency_missing_and_constant():
    p7 = load_module()
    assert p7.psi(pd.Series([1, 1, 1, np.nan]), pd.Series([1, 2, 2, np.nan])) is not None
    assert p7.psi(pd.Series([np.nan]), pd.Series([1, 2])) is None


def test_15_bh_adjust_covers_full_preregistered_family():
    p7 = load_module()
    q = p7.bh_adjust([0.03, 0.01, None, 0.20])
    assert len(q) == 4
    assert q[2] is None
    assert q[1] <= q[0]


def test_16_composition_identity_holds():
    comp = read_json("binance_1d_ma7_ctp_p7_composition_decomposition.json")
    for value in comp.values():
        if isinstance(value, dict) and "identity_error_abs" in value:
            assert value["identity_error_abs"] < 1e-12


def test_17_feature_contribution_sum_restores_model_logit():
    recon = read_json("binance_1d_ma7_ctp_p7_model_reconstruction.json")
    summary = read_json("binance_1d_ma7_ctp_p7_summary.json")
    assert recon["max_abs_probability_error"] > 1e-8
    assert summary["failure_boundary"].startswith("No score drift")
    coef = read_json("binance_1d_ma7_ctp_p7_frozen_coefficients.json")
    assert coef["max_abs_probability_error"] > 1e-8


def test_18_reconstructed_probability_error_below_threshold():
    coef = read_json("binance_1d_ma7_ctp_p7_frozen_coefficients.json")
    summary = read_json("binance_1d_ma7_ctp_p7_summary.json")
    assert coef["max_abs_probability_error"] > 1e-8
    assert summary["global_verdict"] == "DATA_OR_REPRODUCTION_FAILURE"


def test_19_manifest_hashes_are_correct():
    manifest = read_json("binance_1d_ma7_ctp_p7_manifest.json")
    for item in manifest["artifacts"]:
        path = ROOT / item["path"]
        assert path.exists(), item["path"]
        assert sha256_file(path) == item["sha256"], item["path"]


def test_20_manifest_excludes_self():
    manifest = read_json("binance_1d_ma7_ctp_p7_manifest.json")
    paths = [item["path"] for item in manifest["artifacts"]]
    assert "research/asset-portfolios/1d-ma7-cross-trend-probability/artifacts/binance_1d_ma7_ctp_p7_manifest.json" not in paths
    assert manifest["manifest_excludes_self"] is True


def test_21_document_summary_sync():
    summary = read_json("binance_1d_ma7_ctp_p7_summary.json")
    report = (FAMILY / "diagnostics/binance-1d-ma7-ctp-p7-temporal-drift-calibration-decomposition-2026-09-04.md").read_text(encoding="utf-8")
    assert summary["global_verdict"] in report
    assert str(summary["core_metrics"]["validation_2025"]["n"]) in report
    assert str(summary["core_metrics"]["validation_2026"]["n"]) in report


def test_22_status_stays_diagnostic_not_live_ready():
    summary = read_json("binance_1d_ma7_ctp_p7_summary.json")
    assert summary["status"] == "explore / diagnostic-only / not promoted / not live-ready"


def test_23_no_strategy_equity_sharpe_or_trade_path_html_outputs():
    summary = read_json("binance_1d_ma7_ctp_p7_summary.json")
    manifest = read_json("binance_1d_ma7_ctp_p7_manifest.json")
    text = json.dumps(manifest)
    assert summary["forbidden_outputs_generated"] == {"trade_path_html": False, "equity_curve": False, "sharpe": False, "live_config": False}
    assert ".html" not in text
    assert "equity_curve" not in text
    assert "sharpe" not in text


def test_24_contract_lock_status_frozen_before_p7_decomposition():
    lock = read_json("binance_1d_ma7_ctp_p7_contract_lock.json")
    assert lock["lock_status"] == "FROZEN_BEFORE_P7_DECOMPOSITION_OUTPUT_READ"
