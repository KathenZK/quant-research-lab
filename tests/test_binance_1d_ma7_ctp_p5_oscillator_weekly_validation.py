from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability/scripts/run_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py"
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAG_DIR = FAMILY_DIR / "diagnostics"


def load_p5():
    spec = importlib.util.spec_from_file_location("p5_module", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["p5_module"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def independent_wilder_rsi(close: list[float], period: int = 6) -> list[float]:
    out = [np.nan] * len(close)
    deltas = [close[i] - close[i - 1] for i in range(1, len(close))]
    gains = [max(x, 0.0) for x in deltas]
    losses = [max(-x, 0.0) for x in deltas]
    if len(close) <= period:
        return out
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def value(g: float, loss: float) -> float:
        if g == 0 and loss == 0:
            return 50.0
        if loss == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + g / loss)

    out[period] = value(avg_gain, avg_loss)
    for i in range(period + 1, len(close)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = value(avg_gain, avg_loss)
    return out


def test_p5_candidate_feature_counts_and_p4_b0_reproduction():
    p5 = load_p5()
    feature_spec = p5.build_feature_spec()
    p4_spec = load_json(p5.P4_FACTOR_GROUP_SPEC_PATH)
    assert feature_spec["feature_blocks"]["B0_P4_FULL"] == p4_spec["p2_original_field_order"]
    assert [len(feature_spec["candidates"][name]["features"]) for name in feature_spec["candidates"]] == [69, 58, 79, 80, 90, 79]
    assert all(row["count_ok"] for row in feature_spec["checks"]["candidate_checks"].values())
    assert feature_spec["feature_blocks"]["G7_RSI6_OSCILLATOR"] == p5.G7_RSI6
    assert feature_spec["feature_blocks"]["G8_COMPLETED_WEEKLY_REGIME"] == p5.G8_WEEKLY


def test_wilder_rsi6_matches_independent_small_example():
    p5 = load_p5()
    close = pd.Series([10, 11, 12, 11, 13, 14, 13, 15, 16, 15, 17, 18, 17], dtype=float)
    actual = p5.wilder_rsi(close, 6).to_numpy()
    expected = np.asarray(independent_wilder_rsi(close.tolist(), 6), dtype=float)
    np.testing.assert_allclose(actual[6:], expected[6:], rtol=1e-12, atol=1e-12)


def test_rsi_features_do_not_read_future_close():
    p5 = load_p5()
    base = pd.DataFrame(
        {
            "asset": ["A/USDT:USDT"] * 12,
            "ts": pd.date_range("2024-01-01", periods=12, tz="UTC"),
            "close": [10, 11, 12, 11, 13, 14, 13, 15, 16, 15, 17, 18],
        }
    )
    changed_future = base.copy()
    changed_future.loc[11, "close"] = 1000.0
    rsi_a = p5.build_rsi_daily(base)
    rsi_b = p5.build_rsi_daily(changed_future)
    cols = ["rsi6", "rsi6_delta_1d_raw", "rsi6_delta_3d_raw", "rsi6_recovery_long_raw", "rsi6_cross_long_raw"]
    pd.testing.assert_frame_equal(rsi_a.loc[:10, cols], rsi_b.loc[:10, cols])


def test_weekly_features_use_only_complete_utc_weeks_and_asof_join():
    p5 = load_p5()
    days = pd.date_range("2024-01-01", periods=20, tz="UTC")
    prices = pd.DataFrame(
        {
            "asset": ["A/USDT:USDT"] * len(days),
            "asset_slug": ["a_usdt_usdt"] * len(days),
            "base_asset": ["A"] * len(days),
            "ts": days,
            "feature_known_at": days + pd.Timedelta(days=1),
            "open": np.arange(len(days), dtype=float) + 100.0,
            "high": np.arange(len(days), dtype=float) + 101.0,
            "low": np.arange(len(days), dtype=float) + 99.0,
            "close": np.arange(len(days), dtype=float) + 100.5,
            "complete_day": [True] * len(days),
        }
    )
    weekly = p5.build_weekly_features(prices)
    assert len(weekly) == 2
    assert weekly["week_start"].tolist() == [pd.Timestamp("2024-01-01T00:00:00Z"), pd.Timestamp("2024-01-08T00:00:00Z")]
    event = pd.DataFrame(
        {
            "asset": ["A/USDT:USDT"],
            "ts": [pd.Timestamp("2024-01-16T00:00:00Z")],
            "feature_known_at": [pd.Timestamp("2024-01-17T00:00:00Z")],
            "side": ["long"],
            "side_sign": [1.0],
        }
    )
    joined, audit = p5.add_weekly_features(event, weekly)
    assert joined.loc[0, "weekly_feature_known_at"] == pd.Timestamp("2024-01-15T00:00:00Z")
    assert audit["weekly_feature_known_at_gt_feature_known_at"] == 0


def test_feature_spec_and_contract_lock_are_frozen_before_label_reads_after_run():
    lock = load_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_contract_lock.json")
    assert lock["status"] == "FROZEN_BEFORE_P5_LABEL_AND_2025_VALIDATION_READ"
    assert lock["labels_or_2025_validation_read_before_lock"] is False
    feature_spec_path = ROOT / lock["feature_spec"]["path"]
    assert sha256_file(feature_spec_path) == lock["feature_spec"]["sha256"]


def test_p5_data_audit_hype_hyper_tradfi_and_strict_sample_after_run():
    data = load_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_data_audit.json")
    strict = data["strict_sample"]
    assert strict["p4_strict_sample_reproduced"] is True
    assert strict["strict_rows"] == 52563
    assert strict["strict_assets"] == 338
    assert strict["strict_long"] == 26237
    assert strict["strict_short"] == 26326
    assert strict["strict_hype_rows"] == 0
    assert strict["validation_hype_rows"] == 0
    assert data["price_panel"]["hype_raw_file_read"] is False
    assert data["price_panel"]["hype_rows_read"] == 0
    assert data["price_panel"]["hyper_rows_read"] > 0
    assert strict["validation_known_tradfi_rows"] >= 0
    assert data["tradfi_policy"]["excluded_from_main_training_and_validation_statistics"] is True


def test_2025_plus_not_used_for_training_calibration_or_thresholds_after_run():
    calibration = load_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_calibration.json")
    for row in calibration.values():
        assert row["platt_fitted_on"] == "pre_2025_D1_D2_D3_OOF_only"
        assert row["threshold_fitted_on"] == "pre_2025_D1_D2_D3_OOF_only"
        assert row["validation_used_for_fit"] is False
        assert row["train_rows"] == 52563


def test_forward_calibration_uses_only_labels_completed_before_each_fold_after_run():
    summary = load_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_summary.json")
    for candidate in summary["development_aggregate"].values():
        audits = candidate["forward_calibration_audit"]
        assert [row["evaluation_fold"] for row in audits] == ["D1", "D2", "D3"]
        assert audits[0]["calibration_train_rows"] == 0
        assert audits[0]["method"] == "raw_no_prior_completed_oof"
        for row in audits[1:]:
            assert row["temporal_isolation_pass"] is True
            assert pd.Timestamp(row["calibration_train_label_end_max"]) < pd.Timestamp(row["evaluation_start"])


def test_frozen_threshold_uses_one_probability_space_and_matches_saved_decisions_after_run():
    p5 = load_p5()
    calibration = load_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_calibration.json")
    oof = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_pre2025_oof_predictions.parquet")
    validation = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_validation_2025_plus_predictions.parquet")
    for candidate, row in calibration.items():
        raw_col = f"{candidate}_raw_probability"
        cal_col = f"{candidate}_calibrated_probability"
        selected_col = f"{candidate}_frozen_threshold_selected"
        expected_raw_threshold = float(np.quantile(oof[raw_col].to_numpy(), 0.90))
        expected_oof_cal = p5.P2.apply_calibration(oof[raw_col].to_numpy(), row["platt_parameters"])
        expected_cal_threshold = float(np.quantile(expected_oof_cal, 0.90))
        assert row["frozen_raw_probability_threshold_90pct"] == expected_raw_threshold
        assert row["frozen_calibrated_probability_threshold_90pct"] == expected_cal_threshold
        np.testing.assert_array_equal(validation[selected_col], validation[raw_col] >= expected_raw_threshold)
        np.testing.assert_array_equal(validation[selected_col], validation[cal_col] >= expected_cal_threshold)
        assert row["validation_raw_calibrated_selection_parity"] is True


def test_d1_d2_d3_purge_and_2025_prediction_keys_unique_after_run():
    oof = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_pre2025_oof_predictions.parquet")
    assert set(oof["fold"].unique()) == {"D1", "D2", "D3"}
    assert oof.loc[oof["fold"] == "D1", "ts"].between(pd.Timestamp("2022-01-01T00:00:00Z"), pd.Timestamp("2022-12-31T00:00:00Z")).all()
    assert oof.loc[oof["fold"] == "D2", "ts"].between(pd.Timestamp("2023-01-01T00:00:00Z"), pd.Timestamp("2023-12-31T00:00:00Z")).all()
    assert oof.loc[oof["fold"] == "D3", "label_end_ts_20d"].lt(pd.Timestamp("2025-01-01T00:00:00Z")).all()
    validation = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_validation_2025_plus_predictions.parquet")
    assert validation[["asset", "side", "ts"]].duplicated().sum() == 0
    assert not (validation["asset"] == "HYPE/USDT:USDT").any()


def test_bootstrap_draws_shared_json_parquet_markdown_verdict_consistency_after_run():
    summary = load_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_summary.json")
    comparisons = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_paired_comparisons.parquet")
    for period, g in comparisons.groupby("period"):
        assert g["draw_hash"].nunique() == 1
        assert g["draw_hash"].iloc[0] == summary["bootstrap_draw_hashes"][period]
    report = (DIAG_DIR / "binance-1d-ma7-ctp-p5-oscillator-weekly-validation-2026-09-02.md").read_text(encoding="utf-8")
    assert summary["adjudication"]["global_verdict"] in report


def test_block_bootstrap_recomputes_nonlinear_metrics_on_full_resampled_draw(monkeypatch):
    p5 = load_p5()
    monkeypatch.setattr(p5, "BOOTSTRAP_SAMPLES", 40)
    rows = []
    for fold_index, fold in enumerate(["D1", "D2"]):
        start = pd.Timestamp("2022-01-01T00:00:00Z") + pd.Timedelta(days=365 * fold_index)
        for block in range(4):
            ts = start + pd.Timedelta(days=28 * block)
            labels = [0, 0, 1, 1]
            for within, label in enumerate(labels):
                base_probability = [0.15, 0.45, 0.55, 0.85][within]
                challenger_probability = (
                    [0.10, 0.20, 0.80, 0.90][within]
                    if block % 2 == 0
                    else [0.30, 0.70, 0.40, 0.60][within]
                )
                rows.append(
                    {
                        "asset": f"A{fold_index}_{block}_{within}/USDT:USDT",
                        "side": "long" if within % 2 == 0 else "short",
                        "fold": fold,
                        "ts": ts,
                        p5.LABEL_END: ts + pd.Timedelta(days=20),
                        p5.TARGET: label,
                        p5.NET_RETURN: 0.1 if label else -0.1,
                        "R_B0_69_raw_probability": base_probability,
                        "C_TEST_raw_probability": challenger_probability,
                    }
                )
    frame = pd.DataFrame(rows)
    actual, _ = p5.paired_comparisons(
        frame,
        {"R_B0_69": [], "C_TEST": []},
        period="toy",
        probability_suffix="raw_probability",
        top_group_cols=["fold"],
        period_col_for_draws="fold",
    )

    prepared = frame.reset_index(drop=True).copy()
    prepared["_non_overlap_flag"] = True
    draws, _ = p5.make_block_draws(prepared, period_col="fold")
    expected_auc_diffs = []
    for draw_index in range(p5.BOOTSTRAP_SAMPLES):
        sampled_indices = np.concatenate([draws[key][draw_index] for key in sorted(draws)])
        sample = prepared.loc[sampled_indices].reset_index(drop=True)
        base = p5._score_metric(sample, sample["R_B0_69_raw_probability"].to_numpy(), "roc_auc", top_group_cols=["fold"])
        challenger = p5._score_metric(sample, sample["C_TEST_raw_probability"].to_numpy(), "roc_auc", top_group_cols=["fold"])
        expected_auc_diffs.append(challenger - base)

    row = actual.iloc[0]
    assert row["bootstrap_period_stratification"] == "fold"
    assert "recomputed on each full resampled paired-event draw" in row["bootstrap_method_note"]
    assert row["roc_auc_diff_ci_low"] == float(np.quantile(expected_auc_diffs, 0.025))
    assert row["roc_auc_diff_ci_high"] == float(np.quantile(expected_auc_diffs, 0.975))


def test_weekly_causality_manifest_and_no_forbidden_outputs_after_run():
    data = load_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_data_audit.json")
    weekly = data["new_features"]["weekly_causality"]
    assert weekly["weekly_feature_known_at_gt_feature_known_at"] == 0
    assert weekly["verdict"] == "PASS_NO_WEEKLY_LOOKAHEAD"
    manifest = load_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_manifest.json")
    assert not any(item["path"].endswith("binance_1d_ma7_ctp_p5_manifest.json") for item in manifest["artifacts"])
    for item in manifest["artifacts"]:
        path = ROOT / item["path"]
        assert path.exists()
        assert sha256_file(path) == item["sha256"]
    generated = [p.name for p in ARTIFACT_DIR.glob("binance_1d_ma7_ctp_p5_*")]
    forbidden = ["equity", "sharpe", "live", "handoff", "trade_path", "hype"]
    assert not any(any(token in name.lower() for token in forbidden) for name in generated)
