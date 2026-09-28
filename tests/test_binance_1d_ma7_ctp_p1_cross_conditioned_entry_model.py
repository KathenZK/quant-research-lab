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
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
CATL_DIR = ROOT / "research/asset-portfolios/1d-cross-asset-trend-lifecycle"
SCRIPT_PATH = (
    FAMILY_DIR
    / "scripts/run_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py"
)
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
PANEL_GLOB = str(
    CATL_DIR / "artifacts/p0r_donor_directional_modeling_panel/**/*.parquet"
)
HYPE = "HYPE/USDT:USDT"
HYPER = "HYPER/USDT:USDT"


def load_module():
    spec = importlib.util.spec_from_file_location("ma7_ctp_p1", SCRIPT_PATH)
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
        (ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_summary.json").read_text(
            encoding="utf-8"
        )
    )


def test_frozen_objective_and_hype_boundary():
    mod = load_module()
    assert mod.HYPE_ASSET == HYPE
    assert mod.HYPER_ASSET == HYPER
    assert mod.SEED == 20260901
    assert mod.TARGET == "label_entry_success_20d"
    assert mod.LABEL_END == "label_end_ts_20d"
    assert "LONG_HEAD" in mod.HEADS
    assert "SHORT_HEAD" in mod.HEADS
    assert "POOLED_SIDE_ALIGNED_CONTROL" in mod.HEADS
    assert mod.LGBM_CANDIDATES["L1"]["num_leaves"] == 7
    assert mod.LGBM_CANDIDATES["L4"]["max_depth"] == 6
    assert mod.COMMON_LGBM_PARAMS["n_estimators"] == 1500
    assert mod.EXPECTED_EVENT_AUDIT["n"] == 101187


def test_input_manifest_hashes_match_and_hype_is_excluded():
    mod = load_module()
    feature_spec, audit = mod.validate_inputs()
    assert audit["p0r_artifact_hashes_all_match"]
    assert audit["panel_file_set_matches_manifest"]
    assert audit["panel_hype_rows"] == 0
    assert audit["panel_hyper_rows"] > 0
    assert feature_spec["hype_asset_excluded"] == HYPE
    assert feature_spec["holdout_read"] is False
    event_audit = mod.count_events_without_labels()
    assert event_audit["n"] == 101187
    assert event_audit["assets"] == 655
    assert event_audit["long"] == 50738
    assert event_audit["short"] == 50449
    assert event_audit["hype"] == 0
    assert event_audit["hyper"] > 0
    assert event_audit["labels_read"] is False


def test_all_training_rows_are_ma7_crosses_with_one_side_per_asset_ts():
    load_module()
    summary = load_summary()
    assert summary["objective_ma7_cross_only"] is True
    assert summary["event_audit"]["n"] == 101187
    assert summary["event_audit"]["non_cross"] == 0
    oof = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_oof_predictions.parquet")
    hist = pd.read_parquet(
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_historical_test_predictions.parquet"
    )
    for frame in (oof, hist):
        assert not frame["asset"].eq(HYPE).any()
        long = frame.loc[frame["head"].eq("LONG_HEAD")]
        short = frame.loc[frame["head"].eq("SHORT_HEAD")]
        pooled = frame.loc[frame["head"].eq("POOLED_SIDE_ALIGNED_CONTROL")]
        if not long.empty:
            assert long["side"].eq("long").all()
            assert not long.duplicated(["asset", "ts"]).any()
        if not short.empty:
            assert short["side"].eq("short").all()
            assert not short.duplicated(["asset", "ts"]).any()
        if not pooled.empty:
            assert not pooled.duplicated(["asset", "ts", "side"]).any()
            assert set(pooled["side"].unique()) <= {"long", "short"}
    con = duckdb.connect()
    n = con.execute(
        """
        SELECT count(*) FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        WHERE probe_raw_ma7_cross_dir = true AND model_eligible_entry_p0r = true
        """,
        [PANEL_GLOB],
    ).fetchone()[0]
    assert n == 101187


def test_hype_zero_everywhere_and_hyper_preserved():
    summary = load_summary()
    assert summary["hype_isolation"]["input_rows"] == 0
    assert summary["hype_isolation"]["event_rows"] == 0
    assert summary["hype_isolation"]["oof_rows"] == 0
    assert summary["hype_isolation"]["historical_rows"] == 0
    assert summary["hype_isolation"]["hype_reveal_executed"] is False
    assert summary["hyper_preservation"]["event_rows"] > 0
    for filename in (
        "binance_1d_ma7_ctp_p1_oof_predictions.parquet",
        "binance_1d_ma7_ctp_p1_historical_test_predictions.parquet",
    ):
        frame = pd.read_parquet(ARTIFACT_DIR / filename, columns=["asset"])
        assert not frame["asset"].eq(HYPE).any()
        text = filename
        assert "HYPE/USDT:USDT" not in frame["asset"].astype(str).unique()
        del text
    report = (
        FAMILY_DIR
        / "diagnostics/binance-1d-ma7-ctp-p1-cross-conditioned-entry-model-2026-09-01.md"
    ).read_text(encoding="utf-8")
    assert "HYPE 行数：输入 `0`，OOF `0`，历史测试 `0`" in report
    assert "HYPE 未读取、未预测、未揭示" in report
    card = json.loads(
        (ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_model_card.json").read_text(
            encoding="utf-8"
        )
    )
    assert card["hype_rows"] == 0
    assert card["hype_reveal_executed"] is False
    for path in ARTIFACT_DIR.glob("binance_1d_ma7_ctp_p1_*"):
        if path.suffix in {".json", ".md"}:
            payload = path.read_text(encoding="utf-8")
            assert payload.count("HYPE/USDT:USDT") <= 2


def test_allowlist_and_event_t0_and_t1_contract():
    mod = load_module()
    feature_spec = json.loads(
        (ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_feature_spec.json").read_text(
            encoding="utf-8"
        )
    )
    allowed = set(feature_spec["all_allowed_features"])
    assert "side" not in allowed
    assert "asset" not in allowed
    assert not any(name.startswith(("label_", "future_")) for name in allowed)
    assert "label_entry_net_return" not in allowed
    assert "probe_raw_ma7_cross_dir" not in allowed
    assert "dir_raw_ma7_cross" not in allowed
    t0 = set(feature_spec["feature_blocks"]["EVENT_T0"])
    assert t0 <= allowed
    assert "dir_ma7_slope_1d_atr" in t0
    assert all(
        name.startswith("t1_")
        for block, names in feature_spec["feature_blocks"].items()
        if block.startswith("T1_")
        for name in names
    )
    card = json.loads(
        (ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_model_card.json").read_text(
            encoding="utf-8"
        )
    )
    for head in card["heads"].values():
        assert set(head["features"]) <= allowed
        assert "side" not in head["features"]
    f0 = set(mod.scheme_features(feature_spec, "F0_MA7_CORE"))
    f3 = set(mod.scheme_features(feature_spec, "F3_MA7_FULL_MARKET"))
    assert f0 < f3
    assert set(feature_spec["slope_only_features"]) <= t0


def test_t1_features_are_strict_prior_day_lags():
    mod = load_module()
    feature_spec = json.loads(
        (ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_feature_spec.json").read_text(
            encoding="utf-8"
        )
    )
    events = pd.read_parquet(
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_oof_predictions.parquet",
        columns=["asset", "ts", "side"],
    )
    sample_asset = events["asset"].iloc[0]
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    raw = con.execute(
        """
        SELECT asset, side, ts, dir_ma7_slope_1d_atr, quote_volume_to_7d
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        WHERE asset = ?
        ORDER BY side, ts
        """,
        [PANEL_GLOB, sample_asset],
    ).fetch_df()
    raw["ts"] = pd.to_datetime(raw["ts"], utc=True)
    lagged = raw.sort_values(["asset", "side", "ts"]).copy()
    lagged["t1_dir_ma7_slope_1d_atr"] = lagged.groupby(["asset", "side"], sort=False)[
        "dir_ma7_slope_1d_atr"
    ].shift(1)
    full = mod.load_event_panel(feature_spec)
    merged = full.loc[full["asset"].eq(sample_asset), ["asset", "side", "ts", "t1_dir_ma7_slope_1d_atr"]].merge(
        lagged[["asset", "side", "ts", "t1_dir_ma7_slope_1d_atr"]],
        on=["asset", "side", "ts"],
        suffixes=("_event", "_prior"),
    )
    comparable = merged["t1_dir_ma7_slope_1d_atr_event"].notna() & merged[
        "t1_dir_ma7_slope_1d_atr_prior"
    ].notna()
    assert comparable.any()
    assert np.allclose(
        merged.loc[comparable, "t1_dir_ma7_slope_1d_atr_event"].astype(float),
        merged.loc[comparable, "t1_dir_ma7_slope_1d_atr_prior"].astype(float),
        atol=1e-5,
        rtol=1e-5,
        equal_nan=True,
    )


def test_every_fold_has_exact_purge_and_2025_is_not_used_for_selection():
    summary = load_summary()
    prehist = json.loads(
        (ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_prehistorical_lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert prehist["status"] == "LOCKED_BEFORE_HISTORICAL_TEST_READ"
    assert prehist["historical_rows_used_for_selection"] == 0
    assert prehist["hype_rows_used"] == 0
    assert prehist["hype_reveal_authorized"] is False
    for head in ("LONG_HEAD", "SHORT_HEAD", "POOLED_SIDE_ALIGNED_CONTROL"):
        development = summary["heads"][head]["development"]
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
        historical = summary["heads"][head]["historical"]
        assert pd.Timestamp(historical["training_max_label_end"]) < pd.Timestamp(
            "2025-01-01T00:00:00Z"
        )
        assert development["calibration"]["terminal_rows_used"] == 0
        for audit in development["preprocessing_audit"]:
            assert audit["fit_scope"] == "training_rows_only"


def test_oof_is_unique_and_heads_do_not_share_wrong_sides():
    oof = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_oof_predictions.parquet")
    assert not oof.duplicated(["head", "asset", "ts", "side"]).any()
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
    long = oof.loc[oof["head"].eq("LONG_HEAD")]
    short = oof.loc[oof["head"].eq("SHORT_HEAD")]
    pooled = oof.loc[oof["head"].eq("POOLED_SIDE_ALIGNED_CONTROL")]
    assert long["side"].eq("long").all()
    assert short["side"].eq("short").all()
    assert set(pooled["side"]) <= {"long", "short"}
    assert len(long) + len(short) == len(pooled)


def test_training_and_validation_metrics_exist_together():
    metrics = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_fold_metrics.parquet")
    selected = metrics.loc[
        metrics["row_type"].eq("metric") & metrics["evaluation"].eq("selected")
    ]
    for head in ("LONG_HEAD", "SHORT_HEAD", "POOLED_SIDE_ALIGNED_CONTROL"):
        for fold in ("D1", "D2", "D3"):
            splits = set(
                selected.loc[
                    selected["head"].eq(head) & selected["fold"].eq(fold), "split"
                ]
            )
            assert splits == {"training", "validation"}
        hist = metrics.loc[
            metrics["head"].eq(head)
            & metrics["evaluation"].eq("historical_test")
            & metrics["row_type"].eq("metric")
        ]
        assert {"training", "validation"} <= set(hist["split"])


def test_paired_bootstrap_uses_shared_indices():
    summary = load_summary()
    bootstrap = summary["system"]["bootstrap"]
    assert bootstrap["samples"] == 1000
    assert bootstrap["block_days"] == 28
    assert bootstrap["same_resampling_indices_for_all_models"] is True
    assert len(bootstrap["paired_draw_counts_sha256"]) == 64
    for metric in (
        "auc",
        "auc_diff_vs_slope",
        "auc_diff_vs_f0",
        "top_decile_uplift",
        "brier_skill_vs_const",
    ):
        assert bootstrap[metric]["ci95_low"] <= bootstrap[metric]["point"]
        assert bootstrap[metric]["point"] <= bootstrap[metric]["ci95_high"]


def test_summary_metrics_reconcile_to_predictions_and_fold_metrics():
    summary = load_summary()
    predictions = pd.read_parquet(
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_historical_test_predictions.parquet"
    )
    metrics = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_fold_metrics.parquet")
    system = predictions.loc[predictions["head"].isin(["LONG_HEAD", "SHORT_HEAD"])]
    auc = roc_auc_score(system["label_entry_success_20d"], system["p_lgbm_final"])
    assert np.isclose(auc, summary["system"]["hist_metrics"]["roc_auc"], atol=1e-12)
    for head in ("LONG_HEAD", "SHORT_HEAD"):
        frame = predictions.loc[predictions["head"].eq(head)]
        reported = summary["heads"][head]["historical"]["hist_metrics"]["roc_auc"]
        actual = roc_auc_score(frame["label_entry_success_20d"], frame["p_lgbm_final"])
        assert np.isclose(actual, reported, atol=1e-12)
        rows = metrics.loc[
            metrics["head"].eq(head)
            & metrics["row_type"].eq("metric")
            & metrics["evaluation"].eq("historical_test")
            & metrics["split"].eq("validation")
            & metrics["model_id"].astype(str).str.startswith("LGBM_")
        ]
        assert len(rows) == 1
        assert np.isclose(float(rows.iloc[0]["roc_auc"]), reported, atol=1e-12)


def test_system_year_gate_detects_combined_direction_flip():
    summary = load_summary()
    rows = {row["year"]: row for row in summary["system"]["year_rows"]}
    assert {2025, 2026} <= set(rows)
    assert rows[2025]["auc"] > 0.50
    assert rows[2026]["auc"] < 0.48
    assert rows[2026]["is_flip"] is True
    assert summary["system"]["year_flip"] is True
    assert summary["decision"]["head_year_ok"] is True
    assert summary["decision"]["system_year_ok"] is False
    assert summary["decision"]["year_ok"] is False
    report = (
        FAMILY_DIR
        / "diagnostics/binance-1d-ma7-ctp-p1-cross-conditioned-entry-model-2026-09-01.md"
    ).read_text(encoding="utf-8")
    assert "system gate=FAIL" in report
    assert "| SYSTEM | 2026 |" in report
    assert "| 0.4753 | YES |" in report


def test_outputs_are_diagnostic_not_strategy_or_live_artifacts():
    summary = load_summary()
    assert summary["no_strategy_no_portfolio_no_live_artifact"] is True
    assert summary["status"] == (
        "explore / diagnostic-only / not promoted / not live-ready"
    )
    card = json.loads(
        (ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_model_card.json").read_text(
            encoding="utf-8"
        )
    )
    assert card["not_live_ready"] is True
    assert "position sizing" in card["prohibited_uses"]
    manifest = json.loads(
        (ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["holdout_read"] is False
    assert manifest["hype_reveal_executed"] is False
    forbidden_tokens = ("trade", "equity", "position", "runner", "live-spec")
    artifact_names = [Path(item["path"]).name.lower() for item in manifest["artifacts"]]
    assert not any(
        token in name for name in artifact_names for token in forbidden_tokens
    )
    for item in manifest["artifacts"]:
        path = ROOT / item["path"]
        assert path.exists()
        assert path.stat().st_size == item["bytes"]
        assert sha256_file(path) == item["sha256"]
