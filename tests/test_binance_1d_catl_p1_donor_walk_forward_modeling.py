from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score


ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = (
    ROOT / "research/asset-portfolios/1d-cross-asset-trend-lifecycle"
)
SCRIPT_PATH = (
    FAMILY_DIR / "scripts/run_binance_1d_catl_p1_donor_walk_forward_modeling.py"
)
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
PANEL_GLOB = str(
    ARTIFACT_DIR / "p0r_donor_directional_modeling_panel/**/*.parquet"
)


def load_module():
    spec = importlib.util.spec_from_file_location("catl_p1", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_summary() -> dict:
    return json.loads(
        (ARTIFACT_DIR / "binance_1d_catl_p1_summary.json").read_text(
            encoding="utf-8"
        )
    )


def test_frozen_targets_and_exact_hype_boundary():
    mod = load_module()
    assert mod.HYPE_ASSET == "HYPE/USDT:USDT"
    assert mod.HYPER_ASSET == "HYPER/USDT:USDT"
    assert mod.SEED == 20260831
    assert mod.BOOTSTRAP_SAMPLES == 1000
    assert mod.BOOTSTRAP_BLOCK_DAYS == 28
    targets = {item.name: item for item in mod.TARGETS}
    assert targets["entry"].eligibility == "model_eligible_entry_p0r"
    assert targets["entry"].target == "label_entry_success_20d"
    assert targets["entry"].label_end == "label_end_ts_20d"
    assert targets["entry"].non_overlap_days == 20
    assert targets["continuation"].eligibility == "model_eligible_continue_p0r"
    assert targets["continuation"].target == "label_continue_success_5d"
    assert targets["continuation"].label_end == "label_end_ts_5d"
    assert targets["continuation"].non_overlap_days == 5


def test_input_manifest_and_p1_manifest_hashes_are_complete():
    mod = load_module()
    feature_spec, audit = mod.validate_inputs()
    assert audit["p0r_artifact_hashes_all_match"]
    assert audit["panel_file_set_matches_manifest"]
    assert audit["panel_hype_rows"] == 0
    assert audit["panel_hyper_rows"] > 0
    assert feature_spec["hype_asset_excluded"] == mod.HYPE_ASSET

    manifest = json.loads(
        (ARTIFACT_DIR / "binance_1d_catl_p1_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["holdout_read"] is False
    assert manifest["hype_asset_excluded"] == mod.HYPE_ASSET
    assert manifest["hype_reveal_executed"] is False
    for item in manifest["artifacts"]:
        path = ROOT / item["path"]
        assert path.exists()
        assert path.stat().st_size == item["bytes"]
        assert sha256_file(path) == item["sha256"]


def test_hype_is_zero_everywhere_and_hyper_is_preserved():
    mod = load_module()
    summary = load_summary()
    assert set(summary["hype_isolation"].values()) >= {0, False, mod.HYPE_ASSET}
    assert summary["hype_isolation"]["input_rows"] == 0
    assert summary["hype_isolation"]["oof_rows"] == 0
    assert summary["hype_isolation"]["terminal_prediction_rows"] == 0
    assert summary["hype_isolation"]["model_card_rows"] == 0
    assert summary["hype_isolation"]["hype_reveal_executed"] is False
    assert summary["hyper_preservation"]["input_rows"] > 0
    assert (
        summary["hyper_preservation"]["oof_rows"]
        + summary["hyper_preservation"]["terminal_prediction_rows"]
        > 0
    )
    output_frames = []
    for filename in (
        "binance_1d_catl_p1_oof_predictions.parquet",
        "binance_1d_catl_p1_terminal_predictions.parquet",
    ):
        frame = pd.read_parquet(
            ARTIFACT_DIR / filename, columns=["asset"]
        )
        assert not frame["asset"].eq(mod.HYPE_ASSET).any()
        output_frames.append(frame)
    assert any(
        frame["asset"].eq(mod.HYPER_ASSET).any() for frame in output_frames
    )
    card = json.loads(
        (ARTIFACT_DIR / "binance_1d_catl_p1_model_card.json").read_text(
            encoding="utf-8"
        )
    )
    assert card["hype_asset"] == mod.HYPE_ASSET
    assert card["hype_rows"] == 0
    assert card["hype_reveal_executed"] is False


def test_allowlist_is_the_only_model_feature_source():
    mod = load_module()
    feature_spec = json.loads(
        (ARTIFACT_DIR / "binance_1d_catl_p0r_feature_blocks.json").read_text(
            encoding="utf-8"
        )
    )
    allowed = set(feature_spec["all_allowed_features"])
    forbidden = {
        "asset",
        "asset_slug",
        "side",
        "side_sign",
        "ts",
        "entry_ref",
        "atr_anchor",
    }
    assert not (allowed & forbidden)
    assert not any(
        name.startswith(("label_", "future_")) for name in allowed
    )
    card = json.loads(
        (ARTIFACT_DIR / "binance_1d_catl_p1_model_card.json").read_text(
            encoding="utf-8"
        )
    )
    for target in card["targets"].values():
        assert set(target["features"]).issubset(allowed)
        assert not (set(target["features"]) & forbidden)
    assert set(mod.ma_probe_features(feature_spec)).issubset(allowed)


def test_target_specific_eligibility_matches_prediction_counts():
    oof = pd.read_parquet(
        ARTIFACT_DIR / "binance_1d_catl_p1_oof_predictions.parquet",
        columns=["target_name", "asset", "ts", "side"],
    )
    terminal = pd.read_parquet(
        ARTIFACT_DIR / "binance_1d_catl_p1_terminal_predictions.parquet",
        columns=["target_name", "asset", "ts", "side"],
    )
    con = duckdb.connect()
    expected = {}
    for target, eligibility in (
        ("entry", "model_eligible_entry_p0r"),
        ("continuation", "model_eligible_continue_p0r"),
    ):
        expected[(target, "oof")] = con.execute(
            f"""
            SELECT count(*) FROM read_parquet(
                ?, union_by_name=true, hive_partitioning=true
            )
            WHERE {eligibility}
              AND ts >= TIMESTAMPTZ '2022-01-01 00:00:00+00:00'
              AND ts < TIMESTAMPTZ '2025-01-01 00:00:00+00:00'
            """,
            [PANEL_GLOB],
        ).fetchone()[0]
        expected[(target, "terminal")] = con.execute(
            f"""
            SELECT count(*) FROM read_parquet(
                ?, union_by_name=true, hive_partitioning=true
            )
            WHERE {eligibility}
              AND ts >= TIMESTAMPTZ '2025-01-01 00:00:00+00:00'
            """,
            [PANEL_GLOB],
        ).fetchone()[0]
    for target in ("entry", "continuation"):
        assert int(oof["target_name"].eq(target).sum()) == expected[(target, "oof")]
        assert int(terminal["target_name"].eq(target).sum()) == expected[
            (target, "terminal")
        ]


def test_every_fold_has_exact_purge_and_no_terminal_selection():
    summary = load_summary()
    preterminal = json.loads(
        (ARTIFACT_DIR / "binance_1d_catl_p1_preterminal_lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert preterminal["status"] == "LOCKED_BEFORE_DONOR_TERMINAL_READ"
    assert preterminal["terminal_rows_used_for_selection"] == 0
    assert preterminal["hype_rows_used"] == 0
    assert preterminal["hype_reveal_authorized"] is False
    for target in ("entry", "continuation"):
        development = summary["targets"][target]["development"]
        assert development["selection_terminal_rows_used"] == 0
        assert pd.Timestamp(development["selection_data_max_ts"]) < pd.Timestamp(
            "2025-01-01T00:00:00Z"
        )
        for row in development["purge_audit"]:
            assert row["purge_pass"]
            assert pd.Timestamp(row["train_max_label_end"]) < pd.Timestamp(
                row["validation_start"]
            )
            assert row["same_timestamp_overlap"] == 0
        for row in development["leave_asset_group_out"]["purge_audit"]:
            assert row["purge_pass"]
            assert pd.Timestamp(row["train_max_label_end"]) < pd.Timestamp(
                row["validation_start"]
            )
        terminal = summary["targets"][target]["terminal"]
        assert pd.Timestamp(
            terminal["sample"]["training_max_label_end"]
        ) < pd.Timestamp("2025-01-01T00:00:00Z")
        assert development["calibration"]["terminal_rows_used"] == 0


def test_all_preprocessors_are_fit_on_training_only():
    summary = load_summary()
    for target in ("entry", "continuation"):
        development = summary["targets"][target]["development"]
        assert development["preprocessing_audit"]
        for audit in development["preprocessing_audit"]:
            assert audit["fit_scope"] == "training_rows_only"
            validation_start = audit.get(
                "validation_start", audit.get("validation_min_ts")
            )
            assert validation_start is not None
            assert pd.Timestamp(audit["train_max_label_end"]) < pd.Timestamp(
                validation_start
            )
        terminal = summary["targets"][target]["terminal"]
        for audit in terminal["terminal_preprocessing_audit"]:
            assert audit["fit_scope"] == "training_rows_only"
            assert pd.Timestamp(audit["train_max_label_end"]) < pd.Timestamp(
                "2025-01-01T00:00:00Z"
            )


def test_oof_identity_is_unique_and_fold_dates_are_exact():
    oof = pd.read_parquet(
        ARTIFACT_DIR / "binance_1d_catl_p1_oof_predictions.parquet"
    )
    assert not oof.duplicated(["target_name", "asset", "ts", "side"]).any()
    assert not oof["asset"].eq("HYPE/USDT:USDT").any()
    boundaries = {
        "D1": ("2022-01-01T00:00:00Z", "2023-01-01T00:00:00Z"),
        "D2": ("2023-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
        "D3": ("2024-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    }
    for fold, (start, end) in boundaries.items():
        frame = oof.loc[oof["fold"].eq(fold)]
        assert not frame.empty
        assert frame["ts"].min() >= pd.Timestamp(start)
        assert frame["ts"].max() < pd.Timestamp(end)


def test_paired_bootstrap_uses_shared_indices_per_target():
    summary = load_summary()
    for target in ("entry", "continuation"):
        bootstrap = summary["targets"][target]["terminal"]["bootstrap"]
        assert bootstrap["samples"] == 1000
        assert bootstrap["block_days"] == 28
        assert bootstrap["same_resampling_indices_for_all_models"] is True
        assert len(bootstrap["paired_draw_counts_sha256"]) == 64
        for metric in (
            "auc",
            "auc_diff_vs_ma_probe",
            "auc_diff_vs_g_only",
            "top_decile_uplift",
            "brier_skill_vs_const",
        ):
            assert bootstrap[metric]["ci95_low"] <= bootstrap[metric]["point"]
            assert bootstrap[metric]["point"] <= bootstrap[metric]["ci95_high"]


def test_summary_metrics_reconcile_to_predictions_and_fold_metrics():
    summary = load_summary()
    predictions = pd.read_parquet(
        ARTIFACT_DIR / "binance_1d_catl_p1_terminal_predictions.parquet"
    )
    metrics = pd.read_parquet(
        ARTIFACT_DIR / "binance_1d_catl_p1_fold_metrics.parquet"
    )
    for target in ("entry", "continuation"):
        target_spec = (
            "label_entry_success_20d"
            if target == "entry"
            else "label_continue_success_5d"
        )
        frame = predictions.loc[predictions["target_name"].eq(target)]
        auc = roc_auc_score(frame[target_spec], frame["p_lgbm_final"])
        reported = summary["targets"][target]["terminal"]["overall"]["roc_auc"]
        assert np.isclose(auc, reported, atol=1e-12)
        rows = metrics.loc[
            metrics["target_name"].eq(target)
            & metrics["row_type"].eq("metric")
            & metrics["evaluation"].eq("terminal")
            & metrics["model_id"].astype(str).str.startswith("LGBM_")
        ]
        assert len(rows) == 1
        assert np.isclose(float(rows.iloc[0]["roc_auc"]), reported, atol=1e-12)


def test_outputs_are_diagnostic_not_strategy_or_live_artifacts():
    summary = load_summary()
    assert summary["no_strategy_no_portfolio_no_live_artifact"] is True
    card = json.loads(
        (ARTIFACT_DIR / "binance_1d_catl_p1_model_card.json").read_text(
            encoding="utf-8"
        )
    )
    assert card["not_live_ready"] is True
    assert "position sizing" in card["prohibited_uses"]
    manifest = json.loads(
        (ARTIFACT_DIR / "binance_1d_catl_p1_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    forbidden_tokens = ("trade", "equity", "position", "runner", "live-spec")
    artifact_names = [
        Path(item["path"]).name.lower() for item in manifest["artifacts"]
    ]
    assert not any(
        token in name
        for name in artifact_names
        for token in forbidden_tokens
    )
