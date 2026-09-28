from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

import pytest



ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p2_pooled_minimal_stability.py"
CUTOFF = pd.Timestamp("2025-01-01T00:00:00Z")
HYPE = "HYPE/USDT:USDT"
HYPER = "HYPER/USDT:USDT"


def load_module():
    spec = importlib.util.spec_from_file_location("ma7_ctp_p2", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_summary() -> dict:
    return json.loads((ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_summary.json").read_text(encoding="utf-8"))


def test_frozen_objective_and_single_pooled_model_contract():
    mod = load_module()
    assert mod.HEAD == "POOLED_DIRECTION_ALIGNED"
    assert mod.SEED == 20260901
    assert mod.TARGET == "label_entry_success_20d"
    assert mod.LABEL_END == "label_end_ts_20d"
    assert mod.HYPE_ASSET == HYPE
    assert mod.HYPER_ASSET == HYPER
    assert set(mod.LGBM_CANDIDATES) == {"T1", "T2"}
    assert mod.LGBM_CANDIDATES["T1"]["max_depth"] == 3
    assert mod.LGBM_CANDIDATES["T2"]["min_data_in_leaf"] == 2000
    assert mod.COMMON_LGBM_PARAMS["learning_rate"] == 0.02
    assert mod.COMMON_LGBM_PARAMS["n_estimators"] == 1000


@pytest.mark.local_data
def test_input_hashes_hype_boundary_hyper_and_event_counts():
    mod = load_module()
    feature_spec, audit = mod.validate_inputs()
    assert audit["p0r_artifact_hashes_all_match"]
    assert audit["panel_file_set_matches_manifest"]
    assert audit["holdout_read"] is False
    assert audit["hype_asset_excluded"] == HYPE
    assert audit["panel_hype_rows"] == 0
    assert audit["panel_hyper_rows"] > 0
    assert audit["post_2025_model_rows_read"] == 0
    assert audit["hype_model_rows_read"] == 0
    assert feature_spec["model"]["pooled_only"] is True
    event_audit = mod.count_events_without_labels()
    assert event_audit["labels_read"] is False
    assert event_audit["n"] == 54137
    assert event_audit["non_cross"] == 0
    assert event_audit["hype"] == 0
    assert event_audit["post_2025_rows"] == 0
    assert event_audit["duplicate_asset_ts"] == 0


@pytest.mark.local_data
def test_feature_allowlist_only_f0_f1_and_no_forbidden_x():
    feature_spec = json.loads((ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_feature_spec.json").read_text(encoding="utf-8"))
    assert set(feature_spec["schemes"]) == {"F0_MA7_CORE", "F1_MA7_PATH"}
    assert set(feature_spec["forbidden_feature_blocks"]) >= {
        "T1_SLOW_MA_CONTEXT",
        "T1_FLOW",
        "T1_CROSS_MARKET",
        "F2_MA7_CONTEXT",
        "F3_MA7_FULL_MARKET",
    }
    allowed = set(feature_spec["all_allowed_features"])
    forbidden_literals = {
        "asset",
        "side",
        "side_sign",
        "ts",
        "label_entry_success_20d",
        "label_entry_net_return",
        "label_end_ts_20d",
        "probe_raw_ma7_cross_dir",
        "dir_raw_ma7_cross",
        "model_eligible_entry_p0r",
    }
    assert allowed.isdisjoint(forbidden_literals)
    forbidden_tokens = [
        "funding",
        "liquidity",
        "pit_universe",
        "market_",
        "btc_",
        "relative_to_btc",
        "relative_to_market",
        "dir_ma14",
        "dir_ma30",
        "dir_ma60",
        "ma_stack",
        "fast_slow",
        "ma7_cross_with_ma30",
        "price_ma7_ma30",
        "future_",
        "label_",
        "net_return",
        "mfe",
        "mae",
    ]
    assert not any(any(token in feature.lower() for token in forbidden_tokens) for feature in allowed)
    assert "t1_volatility_state_p0r" in allowed
    card = json.loads((ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_model_card.json").read_text(encoding="utf-8"))
    assert set(card["features"]) <= allowed
    assert not any(any(token in feature.lower() for token in forbidden_tokens) for feature in card["features"])


@pytest.mark.local_data
def test_oof_contains_only_real_pre2025_ma7_crosses_and_one_direction():
    summary = load_summary()
    assert summary["objective_ma7_cross_only"] is True
    assert summary["one_pooled_model_only"] is True
    assert summary["independent_long_short_heads_trained"] == 0
    assert summary["event_audit"]["n"] == 54137
    assert summary["event_audit"]["final_train_rows"] == 52563
    assert summary["hype_isolation"]["event_rows"] == 0
    assert summary["hype_isolation"]["oof_rows"] == 0
    oof = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_oof_predictions.parquet")
    oof["ts"] = pd.to_datetime(oof["ts"], utc=True)
    assert not oof.empty
    assert oof["ts"].max() < CUTOFF
    assert not oof["asset"].eq(HYPE).any()
    assert not oof.duplicated(["asset", "ts", "side"]).any()
    assert set(oof["side"].unique()) == {"long", "short"}
    assert set(oof["selected_model_id"].unique()) == {summary["development"]["selected_model_id"]}


@pytest.mark.local_data
def test_t1_features_are_strict_prior_day_lags():
    mod = load_module()
    feature_spec = json.loads((ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_feature_spec.json").read_text(encoding="utf-8"))
    events = mod.load_event_panel(feature_spec)
    sample_asset = events["asset"].iloc[0]
    con = mod.duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    raw = con.execute(
        """
        SELECT asset, side, ts, dir_ma7_slope_1d_atr, dir_ret_30d
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        WHERE asset = ? AND ts < TIMESTAMPTZ '2025-01-01 00:00:00+00:00'
        ORDER BY side, ts
        """,
        [str(mod.PANEL_GLOB), sample_asset],
    ).fetch_df()
    raw["ts"] = pd.to_datetime(raw["ts"], utc=True)
    lagged = raw.sort_values(["asset", "side", "ts"]).copy()
    lagged["t1_dir_ma7_slope_1d_atr"] = lagged.groupby(["asset", "side"], sort=False)["dir_ma7_slope_1d_atr"].shift(1)
    lagged["t1_dir_ret_30d"] = lagged.groupby(["asset", "side"], sort=False)["dir_ret_30d"].shift(1)
    merged = events.loc[
        events["asset"].eq(sample_asset),
        ["asset", "side", "ts", "t1_dir_ma7_slope_1d_atr", "t1_dir_ret_30d"],
    ].merge(
        lagged[["asset", "side", "ts", "t1_dir_ma7_slope_1d_atr", "t1_dir_ret_30d"]],
        on=["asset", "side", "ts"],
        suffixes=("_event", "_prior"),
    )
    for feature in ("t1_dir_ma7_slope_1d_atr", "t1_dir_ret_30d"):
        comparable = merged[f"{feature}_event"].notna() & merged[f"{feature}_prior"].notna()
        assert comparable.any()
        assert np.allclose(
            merged.loc[comparable, f"{feature}_event"].astype(float),
            merged.loc[comparable, f"{feature}_prior"].astype(float),
            atol=1e-8,
            rtol=1e-8,
        )


@pytest.mark.local_data
def test_exact_purge_training_validation_metrics_and_no_2025_selection():
    summary = load_summary()
    metrics = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_fold_metrics.parquet")
    metrics["date_max"] = pd.to_datetime(metrics["date_max"], utc=True)
    assert metrics["date_max"].dropna().max() < CUTOFF
    candidates = {"CONST_PRIOR", "SLOPE_ONLY_LOGIT", "F0_LOGIT", "F1_LOGIT", "F0_T1", "F0_T2", "F1_T1", "F1_T2"}
    dev = metrics[(metrics["row_type"].eq("metric")) & (metrics["evaluation"].eq("development"))]
    for candidate in candidates:
        for fold in ("D1", "D2", "D3"):
            subset = dev[(dev["model_id"].eq(candidate)) & (dev["fold"].eq(fold))]
            assert set(subset["split"]) == {"training", "validation"}
    for audit in summary["development"]["purge_audit"]:
        assert audit["purge_pass"] is True
        assert pd.Timestamp(audit["train_label_end_max"]) < pd.Timestamp(audit["validation_start"])
    assert summary["development"]["historical_2025_plus_rows_used_for_selection"] == 0
    assert summary["final_refit"]["post_2025_predictions_written"] == 0
    assert not any(ARTIFACT_DIR.glob("binance_1d_ma7_ctp_p2_historical*"))


def test_platt_method_is_not_overwritten_when_calibration_improves():
    mod = load_module()
    raw = np.linspace(0.45, 0.55, 40)
    y = np.array([0] * 20 + [1] * 20)
    calibration = mod.fit_platt(raw, y)
    assert calibration["method"] == "platt"
    calibrated = mod.apply_calibration(raw, calibration)
    assert not np.allclose(calibrated, raw)
    assert calibration["calibrated_log_loss"] < calibration["raw_log_loss"]


@pytest.mark.local_data
def test_forward_calibration_is_temporally_isolated_and_separate_from_ranking():
    summary = load_summary()
    selected = summary["development"]["selected_model_id"]
    calibration = summary["probability_calibration"]
    final_calibrator = calibration["final_calibrator"]
    audits = summary["development"]["calibration_audit"][selected]
    assert calibration["primary_ranking_uses_raw_oof"] is True
    assert calibration["forward_validation"]["evaluation_folds"] == ["D2", "D3"]
    assert final_calibrator["selection_basis"] == "forward_oof_D2_D3"
    assert pd.Timestamp(final_calibrator["final_fit_label_end_max"]) < CUTOFF
    for audit in audits:
        assert audit["temporal_isolation_pass"] is True
        if audit["calibration_train_rows"]:
            assert pd.Timestamp(audit["calibration_train_label_end_max"]) < pd.Timestamp(audit["evaluation_start"])

    oof = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_oof_predictions.parquet")
    raw_col = f"p_{selected.lower()}_raw"
    assert np.allclose(oof["p_selected"], oof[raw_col])
    assert np.allclose(
        oof.loc[oof["fold"].eq("D1"), "p_selected_calibrated_forward"],
        oof.loc[oof["fold"].eq("D1"), raw_col],
    )
    if final_calibrator["method"] == "platt":
        forward = calibration["forward_validation"]
        assert (
            forward["forward_calibrated"]["brier"] < forward["raw"]["brier"]
            or forward["forward_calibrated"]["log_loss"] < forward["raw"]["log_loss"]
        )
        assert not np.allclose(
            oof.loc[oof["fold"].isin(["D2", "D3"]), "p_selected_calibrated_forward"],
            oof.loc[oof["fold"].isin(["D2", "D3"]), raw_col],
        )


@pytest.mark.local_data
def test_pooled_not_split_into_long_short_heads_and_side_strata_exist():
    summary = load_summary()
    assert summary["one_pooled_model_only"] is True
    assert summary["independent_long_short_heads_trained"] == 0
    assert set(summary["side_metrics"]) == {"long", "short"}
    oof = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_oof_predictions.parquet")
    assert "p_selected" in oof.columns
    assert not any(col.startswith("p_long") or col.startswith("p_short") for col in oof.columns)


@pytest.mark.local_data
def test_bootstrap_lago_non_overlap_and_recomputed_metrics():
    summary = load_summary()
    assert summary["bootstrap"]["same_resampling_indices_for_all_models"] is True
    assert summary["bootstrap"]["samples"] == 1000
    assert summary["bootstrap"]["block_days"] == 28
    assert set(summary["leave_asset_group_out"]) == {"0", "1", "2", "3", "4"}
    assert summary["non_overlap_n"] < summary["oof_metrics"]["eval_n"]
    oof = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_oof_predictions.parquet")
    auc = roc_auc_score(oof["label_entry_success_20d"], oof["p_selected"])
    assert abs(auc - summary["oof_metrics"]["roc_auc"]) < 1e-12
    f1_diff = roc_auc_score(oof["label_entry_success_20d"], oof["p_f1_reference"]) - roc_auc_score(oof["label_entry_success_20d"], oof["p_f0_reference"])
    assert abs(f1_diff - summary["bootstrap"]["f1_minus_f0_auc_diff"]["point"]) < 1e-12


@pytest.mark.local_data
def test_deciles_and_no_strategy_live_ready_artifacts():
    summary = load_summary()
    deciles = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_decile_metrics.parquet")
    assert set(deciles["decile"]) == set(range(1, 11))
    assert int(deciles["n"].sum()) == summary["oof_metrics"]["eval_n"]
    assert summary["no_strategy_no_portfolio_no_live_artifact"] is True
    card = json.loads((ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_model_card.json").read_text(encoding="utf-8"))
    assert card["not_live_ready"] is True
    assert card["post_2025_predictions_written"] == 0
    assert "live trading" in card["prohibited_uses"]
    report = (FAMILY_DIR / "diagnostics/binance-1d-ma7-ctp-p2-pooled-minimal-stability-2026-09-01.md").read_text(encoding="utf-8")
    assert "没有 2025+ 建模读取" in report
    assert "没有读取 HYPE" in report
