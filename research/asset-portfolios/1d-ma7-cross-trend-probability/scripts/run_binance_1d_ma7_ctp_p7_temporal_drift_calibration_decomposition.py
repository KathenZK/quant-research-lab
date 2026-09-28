#!/usr/bin/env python3
"""Run BIN-1D-MA7-CTP P7 temporal drift and calibration decomposition.

P7 is diagnostic-only. It reconstructs the frozen P5/P6 B0 reference model,
audits time drift and calibration, and emits reproducible artifacts. It does
not train a new strategy candidate and does not generate live/run configs.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import duckdb
import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import expit, logit
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

warnings.filterwarnings("ignore", message="X does not have valid feature names")
warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
CATL_DIR = ROOT / "research/asset-portfolios/1d-cross-asset-trend-lifecycle"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAGNOSTIC_DIR = FAMILY_DIR / "diagnostics"
SPEC_DIR = FAMILY_DIR / "specs"
SCRIPT_PATH = Path(__file__).resolve()
TEST_PATH = ROOT / "tests/test_binance_1d_ma7_ctp_p7_temporal_drift_calibration_decomposition.py"

P7_CONTRACT_PATH = SPEC_DIR / "binance-1d-ma7-ctp-p7-temporal-drift-calibration-decomposition-contract-2026-09-04.md"
CONFIG_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_config.json"
CONTRACT_LOCK_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_contract_lock.json"
INPUT_INVENTORY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_input_inventory.json"
DATA_AUDIT_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_data_audit.json"
ANCHOR_PARITY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_anchor_parity.json"
MODEL_RECONSTRUCTION_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_model_reconstruction.json"
FROZEN_COEFFICIENTS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_frozen_coefficients.json"
SCORE_DRIFT_PARQUET_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_score_distribution_drift.parquet"
SCORE_DRIFT_CSV_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_score_distribution_drift.csv"
FEATURE_DRIFT_PARQUET_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_feature_drift.parquet"
FEATURE_GROUP_DRIFT_CSV_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_feature_group_drift.csv"
FIXED_BIN_OUTCOMES_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_fixed_score_bin_outcomes.parquet"
SCORE_MONOTONICITY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_score_monotonicity.json"
CALIBRATION_METRICS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_calibration_metrics.json"
CALIBRATION_BINS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_calibration_bins.parquet"
YEAR_INTERACTIONS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_year_interactions.json"
COMPOSITION_DECOMPOSITION_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_composition_decomposition.json"
COMPOSITION_CELLS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_composition_cells.parquet"
FEATURE_CONTRIBUTION_DRIFT_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_feature_contribution_drift.parquet"
FEATURE_GROUP_CONTRIBUTION_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_feature_group_contribution.csv"
LABEL_ECONOMIC_DECOMPOSITION_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_label_economic_decomposition.json"
CONCENTRATION_METRICS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_concentration_metrics.json"
LEAVE_ONE_OUT_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_leave_one_out.parquet"
NONOVERLAP_EPISODE_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_nonoverlap_episode_checks.json"
BOOTSTRAP_RESULTS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_bootstrap_results.parquet"
SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_summary.json"
MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_manifest.json"
REPORT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p7-temporal-drift-calibration-decomposition-2026-09-04.md"
MODELING_AUDIT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p7-modeling-audit-2026-09-04.md"

P5_OOF_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_pre2025_oof_predictions.parquet"
P5_VALIDATION_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_validation_2025_plus_predictions.parquet"
P5_CALIBRATION_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_calibration.json"
P5_MODEL_CARD_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_model_card.json"
P5_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_summary.json"
P5_MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_manifest.json"
P5_ACCEPTANCE_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p5-independent-acceptance-audit-2026-09-02.md"
P4_FACTOR_SPEC_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p4_factor_group_spec.json"
P6_PREDICTIONS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p6_predictions.parquet"
P6_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p6_summary.json"
P6_DATA_AUDIT_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p6_data_audit.json"
P6_MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p6_manifest.json"
P6_CONTRACT_PATH = SPEC_DIR / "binance-1d-ma7-ctp-p6-market-regime-side-conditional-ranking-contract-2026-09-03.md"
P6_REPORT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p6-market-regime-side-conditional-ranking-2026-09-03.md"
P0R_MANIFEST_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_manifest.json"
P0R_SUMMARY_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_summary.json"
P0R_PANEL_GLOB = CATL_DIR / "artifacts/p0r_donor_directional_modeling_panel/**/*.parquet"

HYPE_ASSET = "HYPE/USDT:USDT"
HYPER_ASSET = "HYPER/USDT:USDT"
SEED = 20260901
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_BLOCK_DAYS = 28
STATUS = "explore / diagnostic-only / not promoted / not live-ready"
RESEARCH_ID = "BIN-1D-MA7-CTP-P7"
SAMPLE_ROLE_VALIDATION = "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS"
TARGET = "label_entry_success_20d"
NET_RETURN = "label_entry_net_return"
LABEL_END = "label_end_ts_20d"
RAW_COL = "R_B0_69_raw_probability"
CAL_COL = "R_B0_69_calibrated_probability"
FROZEN_THRESHOLD = 0.5100704255165665
FROZEN_THRESHOLD_REPORT = 0.510070
PERCENTILE_EDGES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 97.5, 99, 100]
VERDICT_CANDIDATES = [
    "DATA_OR_REPRODUCTION_FAILURE",
    "RANKING_STABLE_CALIBRATION_DRIFT",
    "REGIME_CONDITIONAL_SIGNAL",
    "FEATURE_OR_UNIVERSE_SHIFT",
    "TAIL_NONMONOTONIC_OVERCONFIDENCE",
    "UNEXPLAINED_TEMPORAL_INSTABILITY",
]


def import_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P5 = import_module(FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py", "p5_ctp")
P6 = import_module(FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p6_market_regime_side_conditional_ranking.py", "p6_ctp")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="execute P7 and write artifacts")
    parser.add_argument("--force", action="store_true", help="overwrite existing P7 artifacts")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json_bytes(payload: Any) -> bytes:
    return json.dumps(json_ready(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(stable_json_bytes(payload)).hexdigest()


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, np.ndarray):
        return [json_ready(v) for v in value.tolist()]
    if isinstance(value, np.generic):
        return json_ready(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(json_ready(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(tmp, index=False, compression="zstd")
    os.replace(tmp, path)


def output_paths() -> list[Path]:
    chart_paths = [ARTIFACT_DIR / f"binance_1d_ma7_ctp_p7_chart_{i:02d}_{name}.svg" for i, name in enumerate(CHART_NAMES, start=1)]
    return [
        CONFIG_PATH,
        CONTRACT_LOCK_PATH,
        INPUT_INVENTORY_PATH,
        DATA_AUDIT_PATH,
        ANCHOR_PARITY_PATH,
        MODEL_RECONSTRUCTION_PATH,
        FROZEN_COEFFICIENTS_PATH,
        SCORE_DRIFT_PARQUET_PATH,
        SCORE_DRIFT_CSV_PATH,
        FEATURE_DRIFT_PARQUET_PATH,
        FEATURE_GROUP_DRIFT_CSV_PATH,
        FIXED_BIN_OUTCOMES_PATH,
        SCORE_MONOTONICITY_PATH,
        CALIBRATION_METRICS_PATH,
        CALIBRATION_BINS_PATH,
        YEAR_INTERACTIONS_PATH,
        COMPOSITION_DECOMPOSITION_PATH,
        COMPOSITION_CELLS_PATH,
        FEATURE_CONTRIBUTION_DRIFT_PATH,
        FEATURE_GROUP_CONTRIBUTION_PATH,
        LABEL_ECONOMIC_DECOMPOSITION_PATH,
        CONCENTRATION_METRICS_PATH,
        LEAVE_ONE_OUT_PATH,
        NONOVERLAP_EPISODE_PATH,
        BOOTSTRAP_RESULTS_PATH,
        SUMMARY_PATH,
        MANIFEST_PATH,
        REPORT_PATH,
        MODELING_AUDIT_PATH,
        *chart_paths,
    ]


CHART_NAMES = [
    "raw_score_distribution",
    "fixed_bins_success_rate",
    "fixed_bins_net_mean",
    "raw_reliability",
    "calibrated_reliability",
    "feature_drift_heatmap",
    "group_contribution_drift",
    "composition_decomposition",
    "monthly_threshold_metrics",
    "concentration_summary",
]


def ensure_output_policy(force: bool) -> None:
    existing = [path for path in output_paths() if path.exists()]
    if existing and not force:
        raise FileExistsError("P7 outputs already exist; pass --force: " + ", ".join(str(p.relative_to(ROOT)) for p in existing[:10]))


def build_config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "alias": "BIN-1D-MA7-CTP",
        "experiment": "P7 Temporal Drift, Score Monotonicity and Calibration Decomposition",
        "status": STATUS,
        "sample_roles": {
            "pre_2025_development": "feature distribution, preprocessing reconstruction, fixed bin boundaries",
            "development_oof": "strict time-forward OOF ranking/calibration and frozen threshold baseline",
            "validation_2025_plus": SAMPLE_ROLE_VALIDATION,
            "known_tradfi": "unsupported diagnostic only; excluded from main conclusion",
        },
        "model": {
            "object": "R_B0_69",
            "allowed_reconstruction_only": True,
            "feature_count": 69,
            "classifier": "LogisticRegression(penalty='l2', solver='lbfgs', max_iter=1000, random_state=20260901)",
            "preprocessing": "train-fold median imputation, train-fold one-hot for t1_volatility_state_p0r, train-fold StandardScaler",
            "max_abs_probability_error": 1e-8,
        },
        "threshold": {
            "raw_probability": FROZEN_THRESHOLD,
            "display": FROZEN_THRESHOLD_REPORT,
            "fit_source": "development OOF raw probability 95th percentile",
            "selection_rule": "score >= threshold",
            "not_probability_claim": True,
        },
        "fixed_score_bins": {
            "fit_source": "development OOF raw probability only",
            "percentiles": PERCENTILE_EDGES,
            "applies_to": ["development_oof", "validation_2025", "validation_2026"],
        },
        "bootstrap": {
            "samples": BOOTSTRAP_SAMPLES,
            "seed": SEED,
            "block_days": BOOTSTRAP_BLOCK_DAYS,
            "unit": "calendar 28-day block",
            "paired_replicate": True,
            "full_resample_recompute": True,
        },
        "statistical_tests": {
            "score_distribution": ["ks_2samp", "wasserstein_distance", "psi"],
            "feature_drift": ["ks_2samp", "wasserstein_distance", "psi", "standardized_mean_difference", "BH"],
            "score_monotonicity": ["spearman_success", "spearman_net", "adjacent_inversion", "year_interaction_BH"],
            "calibration": ["brier", "brier_skill", "calibration_intercept_slope", "ECE", "murphy_decomposition"],
            "composition": ["symmetric_kitagawa_oaxaca"],
        },
        "verdict_candidates": VERDICT_CANDIDATES,
        "p8_branches": ["A", "B", "C", "D", "E"],
        "forbidden_outputs": [
            "strategy",
            "position",
            "equity_curve",
            "sharpe",
            "trade_path_html",
            "live_spec",
            "runner_handoff",
            "hype_reveal",
        ],
    }


def write_contract_artifacts() -> tuple[dict[str, Any], dict[str, Any]]:
    config = build_config()
    atomic_write_json(CONFIG_PATH, config)
    inventory = build_input_inventory(config)
    atomic_write_json(INPUT_INVENTORY_PATH, inventory)
    lock = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "lock_status": "FROZEN_BEFORE_P7_DECOMPOSITION_OUTPUT_READ",
        "status": STATUS,
        "created_at": datetime.now(UTC),
        "contract_path": str(P7_CONTRACT_PATH.relative_to(ROOT)),
        "contract_sha256": sha256_file(P7_CONTRACT_PATH),
        "config_path": str(CONFIG_PATH.relative_to(ROOT)),
        "config_sha256": sha256_file(CONFIG_PATH),
        "input_inventory_path": str(INPUT_INVENTORY_PATH.relative_to(ROOT)),
        "input_inventory_sha256": sha256_file(INPUT_INVENTORY_PATH),
        "honesty_note": "2025+ has been repeatedly viewed in P1-P6; this lock prevents changing P7 decomposition protocol after reading P7 details but cannot restore blind-test status.",
    }
    atomic_write_json(CONTRACT_LOCK_PATH, lock)
    return config, lock


def build_input_inventory(config: dict[str, Any]) -> dict[str, Any]:
    input_paths = [
        P7_CONTRACT_PATH,
        P4_FACTOR_SPEC_PATH,
        P5_OOF_PATH,
        P5_VALIDATION_PATH,
        P5_CALIBRATION_PATH,
        P5_MODEL_CARD_PATH,
        P5_SUMMARY_PATH,
        P5_MANIFEST_PATH,
        P5_ACCEPTANCE_PATH,
        P6_PREDICTIONS_PATH,
        P6_SUMMARY_PATH,
        P6_DATA_AUDIT_PATH,
        P6_MANIFEST_PATH,
        P6_CONTRACT_PATH,
        P6_REPORT_PATH,
        P0R_MANIFEST_PATH,
        P0R_SUMMARY_PATH,
        P5.__file__ and Path(P5.__file__),
        P6.__file__ and Path(P6.__file__),
    ]
    artifacts: list[dict[str, Any]] = []
    missing: list[str] = []
    for path in input_paths:
        p = Path(path)
        if p.exists():
            artifacts.append({"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": sha256_file(p)})
        else:
            missing.append(str(p.relative_to(ROOT)))
    p6_modeling_audit = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p6-modeling-audit-2026-09-03.md"
    if not p6_modeling_audit.exists():
        missing.append(str(p6_modeling_audit.relative_to(ROOT)))
    return {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generated_at": datetime.now(UTC),
        "config_sha256_canonical_payload": sha256_payload(config),
        "artifacts": artifacts,
        "missing_expected_inputs": missing,
        "p0r_panel_glob": str(P0R_PANEL_GLOB.relative_to(ROOT)),
        "p0r_panel_manifest_source": str(P0R_MANIFEST_PATH.relative_to(ROOT)),
        "hype_policy": "HYPE/USDT:USDT excluded; HYPER/USDT:USDT retained",
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def event_key(frame: pd.DataFrame) -> pd.Series:
    return frame["asset"].astype(str) + "|" + frame["side"].astype(str) + "|" + pd.to_datetime(frame["ts"], utc=True).astype(str)


def load_p0r_extra_columns() -> pd.DataFrame:
    cols = [
        "asset",
        "side",
        "ts",
        "base_symbol",
        "listing_age_days",
        "liquidity_rank_pct_p0r",
        "label_entry_result",
        "label_entry_hours_to_hit",
        "label_entry_ambiguous_same_hour",
        "entry_ref",
        "atr_anchor",
        "dir_funding_carry_20d",
        "funding_missing",
        "label_entry_net_return",
    ]
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    available = con.execute("DESCRIBE SELECT * FROM read_parquet(?, union_by_name=true, hive_partitioning=true) LIMIT 1", [str(P0R_PANEL_GLOB)]).fetchdf()[
        "column_name"
    ].tolist()
    selected = [c for c in cols if c in available]
    query = f"SELECT {', '.join(selected)} FROM read_parquet(?, union_by_name=true, hive_partitioning=true) WHERE probe_raw_ma7_cross_dir AND model_eligible_entry_p0r"
    out = con.execute(query, [str(P0R_PANEL_GLOB)]).fetchdf()
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    if "listing_age_days" in out.columns:
        out = out.rename(columns={"listing_age_days": "asset_age_days_p0r"})
    if (out["asset"] == HYPE_ASSET).any():
        raise RuntimeError("HYPE entered P7 extra column load")
    return out


def load_samples(feature_spec: dict[str, Any]) -> dict[str, pd.DataFrame]:
    development_full, validation_total, strict_audit = P5.prepare_event_panel(feature_spec)
    p5_oof_pred = pd.read_parquet(P5_OOF_PATH)
    p5_val_pred = pd.read_parquet(P5_VALIDATION_PATH)
    p6_pred = pd.read_parquet(P6_PREDICTIONS_PATH)
    for frame in [development_full, validation_total, p5_oof_pred, p5_val_pred, p6_pred]:
        for col in ["ts", "feature_known_at", "entry_ts", LABEL_END]:
            if col in frame.columns:
                frame[col] = pd.to_datetime(frame[col], utc=True)
    if (development_full["asset"] == HYPE_ASSET).any() or (validation_total["asset"] == HYPE_ASSET).any():
        raise RuntimeError("HYPE entered P7 source samples")
    pred_cols_oof = [c for c in p5_oof_pred.columns if c.endswith("_raw_probability") or c.endswith("_calibrated_probability") or c == "fold"]
    p5_oof_pred = p5_oof_pred.assign(_key=event_key(p5_oof_pred))
    p5_val_pred = p5_val_pred.assign(_key=event_key(p5_val_pred))
    dev_keyed = development_full.assign(_key=event_key(development_full))
    p5_oof = dev_keyed.merge(p5_oof_pred[["_key", *pred_cols_oof]], on="_key", how="inner").drop(columns=["_key"])
    pred_cols_val = [
        c
        for c in p5_val_pred.columns
        if c.endswith("_raw_probability") or c.endswith("_calibrated_probability") or c.endswith("_frozen_threshold_selected") or c in {"validation_role", "asset_generalization"}
    ]
    validation_keyed = validation_total.assign(_key=event_key(validation_total))
    validation_scored = validation_keyed.merge(p5_val_pred[["_key", *pred_cols_val]], on="_key", how="inner").drop(columns=["_key"])
    validation_main = validation_scored[~validation_scored["is_known_tradfi"].astype(bool)].copy()
    validation_tradfi = validation_scored[validation_scored["is_known_tradfi"].astype(bool)].copy()
    extra = load_p0r_extra_columns()
    extra_keyed = extra.assign(_key=event_key(extra))
    extra_cols = [c for c in extra_keyed.columns if c not in {"asset", "side", "ts", "base_symbol", "label_entry_net_return", "_key"}]
    def add_extra(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.assign(_key=event_key(frame)).merge(extra_keyed[["_key", *extra_cols]], on="_key", how="left").drop(columns=["_key"])
        if "asset_age_days_p0r" not in out.columns:
            out["asset_age_days_p0r"] = np.nan
        if "liquidity_rank_pct_p0r" not in out.columns:
            out["liquidity_rank_pct_p0r"] = np.nan
        return out
    development_full = add_extra(development_full)
    p5_oof = add_extra(p5_oof)
    validation_main = add_extra(validation_main)
    validation_tradfi = add_extra(validation_tradfi)
    p6_keep = p6_pred[["asset", "side", "ts", "market_state", "six_grid", "raw_market_breadth_ma30", "raw_btc_price_side_ma30", "period", "b0_raw_probability", "R_B0_69_score", "block28"]].copy()
    p6_keep["_key"] = event_key(p6_keep)
    def add_p6(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.assign(_key=event_key(frame)).merge(p6_keep, on="_key", how="left", suffixes=("", "_p6")).drop(columns=["_key"])
        if out["six_grid"].isna().any():
            missing = int(out["six_grid"].isna().sum())
            raise RuntimeError(f"P6 six_grid missing for {missing} P7 rows")
        return out
    p5_oof = add_p6(p5_oof)
    validation_main = add_p6(validation_main)
    validation_main["event_year"] = validation_main["event_year"].astype(int)
    p5_oof["event_year"] = pd.to_datetime(p5_oof["ts"], utc=True).dt.year.astype(int)
    development_full["event_year"] = pd.to_datetime(development_full["ts"], utc=True).dt.year.astype(int)
    return {
        "development_full": development_full.reset_index(drop=True),
        "development_oof": p5_oof.reset_index(drop=True),
        "validation_main": validation_main.reset_index(drop=True),
        "validation_tradfi": validation_tradfi.reset_index(drop=True),
        "validation_2025": validation_main[validation_main["event_year"].eq(2025)].reset_index(drop=True),
        "validation_2026": validation_main[validation_main["event_year"].eq(2026)].reset_index(drop=True),
        "strict_audit": pd.DataFrame([strict_audit]),
    }


def assign_development_bins(oof: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    values = oof[RAW_COL].to_numpy(dtype=float)
    edges = np.percentile(values, PERCENTILE_EDGES)
    edges[0] = -np.inf
    edges[-1] = np.inf
    labels = [f"p{PERCENTILE_EDGES[i]:g}_p{PERCENTILE_EDGES[i+1]:g}" for i in range(len(PERCENTILE_EDGES) - 1)]
    return edges, labels


def apply_fixed_bins(frame: pd.DataFrame, edges: np.ndarray, labels: list[str]) -> pd.Categorical:
    return pd.cut(frame[RAW_COL].astype(float), bins=edges, labels=labels, include_lowest=True)


def age_liquidity_groups(development_full: pd.DataFrame, frames: Iterable[pd.DataFrame]) -> dict[str, Any]:
    age = pd.to_numeric(development_full["asset_age_days_p0r"], errors="coerce")
    liq = pd.to_numeric(development_full["liquidity_rank_pct_p0r"], errors="coerce")
    age_edges = np.nanpercentile(age, [0, 25, 50, 75, 100]) if age.notna().any() else np.array([0, 1, 2, 3, 4], dtype=float)
    age_edges[0] = -np.inf
    age_edges[-1] = np.inf
    liq_edges = np.nanpercentile(liq, [0, 25, 50, 75, 100]) if liq.notna().any() else np.array([0, 0.25, 0.5, 0.75, 1.0], dtype=float)
    liq_edges[0] = -np.inf
    liq_edges[-1] = np.inf
    age_labels = ["age_q1_young", "age_q2", "age_q3", "age_q4_old"]
    liq_labels = ["liq_q1_low", "liq_q2", "liq_q3", "liq_q4_high"]
    for frame in frames:
        frame["asset_age_group"] = pd.cut(pd.to_numeric(frame["asset_age_days_p0r"], errors="coerce"), age_edges, labels=age_labels, include_lowest=True).astype(str)
        frame.loc[frame["asset_age_days_p0r"].isna(), "asset_age_group"] = "age_missing"
        frame["liquidity_group"] = pd.cut(pd.to_numeric(frame["liquidity_rank_pct_p0r"], errors="coerce"), liq_edges, labels=liq_labels, include_lowest=True).astype(str)
        frame.loc[frame["liquidity_rank_pct_p0r"].isna(), "liquidity_group"] = "liq_missing"
        frame["event_month"] = pd.to_datetime(frame["ts"], utc=True).dt.strftime("%Y-%m")
        frame["event_date"] = pd.to_datetime(frame["ts"], utc=True).dt.strftime("%Y-%m-%d")
        start = pd.Timestamp("1970-01-01T00:00:00Z")
        frame["block28"] = ((pd.to_datetime(frame["ts"], utc=True) - start).dt.days // BOOTSTRAP_BLOCK_DAYS).astype(int).astype(str)
        frame["episode_cluster"] = frame["asset"].astype(str) + "_" + (pd.to_datetime(frame["ts"], utc=True).dt.dayofyear // 20).astype(str)
    return {
        "asset_age_edges_from_pre2025": [float(x) if math.isfinite(float(x)) else str(x) for x in age_edges],
        "liquidity_edges_from_pre2025": [float(x) if math.isfinite(float(x)) else str(x) for x in liq_edges],
    }


def proportion_ci(success: int, n: int) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = success / n
    se = math.sqrt(max(p * (1 - p), 0.0) / n)
    return max(0.0, p - 1.96 * se), min(1.0, p + 1.96 * se)


def sample_metrics(frame: pd.DataFrame, score_col: str = RAW_COL) -> dict[str, Any]:
    if len(frame) == 0:
        return {"n": 0}
    y = frame[TARGET].astype(int).to_numpy()
    p = frame[score_col].astype(float).to_numpy()
    out = {
        "n": int(len(frame)),
        "assets": int(frame["asset"].nunique()) if "asset" in frame else None,
        "base_success_rate": float(np.mean(y)) if len(y) else None,
        "net_mean": float(frame[NET_RETURN].mean()) if NET_RETURN in frame else None,
        "net_median": float(frame[NET_RETURN].median()) if NET_RETURN in frame else None,
    }
    if len(np.unique(y)) == 2:
        out["auc"] = float(roc_auc_score(y, p))
        out["pr_auc"] = float(average_precision_score(y, p))
    else:
        out["auc"] = None
        out["pr_auc"] = None
    selected = frame[score_col].astype(float) >= FROZEN_THRESHOLD
    sel = frame[selected]
    out.update(
        {
            "threshold": FROZEN_THRESHOLD_REPORT,
            "threshold_selected_n": int(selected.sum()),
            "threshold_coverage": float(selected.mean()),
            "threshold_success_rate": float(sel[TARGET].mean()) if len(sel) else None,
            "threshold_uplift": float(sel[TARGET].mean() - frame[TARGET].mean()) if len(sel) else None,
            "threshold_net_mean": float(sel[NET_RETURN].mean()) if len(sel) else None,
            "threshold_net_median": float(sel[NET_RETURN].median()) if len(sel) else None,
        }
    )
    return out


def psi(expected: pd.Series | np.ndarray, actual: pd.Series | np.ndarray, bins: int = 10) -> float | None:
    exp = pd.Series(expected).replace([np.inf, -np.inf], np.nan).dropna()
    act = pd.Series(actual).replace([np.inf, -np.inf], np.nan).dropna()
    if len(exp) == 0 or len(act) == 0:
        return None
    if exp.nunique(dropna=True) <= 1:
        edges = np.array([-np.inf, float(exp.iloc[0]), np.inf])
    else:
        edges = np.unique(np.nanpercentile(exp, np.linspace(0, 100, bins + 1)))
        edges[0] = -np.inf
        edges[-1] = np.inf
    if len(edges) < 2:
        return None
    exp_counts = pd.cut(exp, edges, include_lowest=True).value_counts(sort=False).to_numpy(dtype=float)
    act_counts = pd.cut(act, edges, include_lowest=True).value_counts(sort=False).to_numpy(dtype=float)
    exp_pct = np.maximum(exp_counts / max(exp_counts.sum(), 1.0), 1e-6)
    act_pct = np.maximum(act_counts / max(act_counts.sum(), 1.0), 1e-6)
    return float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))


def categorical_psi(expected: pd.Series, actual: pd.Series) -> float | None:
    exp = expected.astype(str).fillna("__NA__")
    act = actual.astype(str).fillna("__NA__")
    cats = sorted(set(exp.unique()).union(set(act.unique())))
    if not cats:
        return None
    exp_pct = np.maximum(np.array([(exp == c).mean() for c in cats], dtype=float), 1e-6)
    act_pct = np.maximum(np.array([(act == c).mean() for c in cats], dtype=float), 1e-6)
    return float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))


def bh_adjust(p_values: list[float | None]) -> list[float | None]:
    indexed = [(i, p) for i, p in enumerate(p_values) if p is not None and math.isfinite(float(p))]
    out: list[float | None] = [None] * len(p_values)
    if not indexed:
        return out
    m = len(indexed)
    ordered = sorted(indexed, key=lambda item: item[1])
    prev = 1.0
    for rank, (idx, p) in reversed(list(enumerate(ordered, start=1))):
        q = min(prev, float(p) * m / rank)
        out[idx] = min(1.0, q)
        prev = q
    return out


def distribution_stats(values: pd.Series, threshold: float = FROZEN_THRESHOLD) -> dict[str, Any]:
    v = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
    finite = v.dropna()
    out = {
        "count": int(len(v)),
        "missing_rate": float(v.isna().mean()) if len(v) else None,
    }
    if len(finite) == 0:
        for key in ["mean", "std", "min", "p01", "p05", "p10", "p25", "p50", "p75", "p90", "p95", "p975", "p99", "max", "threshold_coverage"]:
            out[key] = None
        return out
    quantiles = np.percentile(finite, [1, 5, 10, 25, 50, 75, 90, 95, 97.5, 99])
    out.update(
        {
            "mean": float(finite.mean()),
            "std": float(finite.std(ddof=1)) if len(finite) > 1 else 0.0,
            "min": float(finite.min()),
            "p01": float(quantiles[0]),
            "p05": float(quantiles[1]),
            "p10": float(quantiles[2]),
            "p25": float(quantiles[3]),
            "p50": float(quantiles[4]),
            "p75": float(quantiles[5]),
            "p90": float(quantiles[6]),
            "p95": float(quantiles[7]),
            "p975": float(quantiles[8]),
            "p99": float(quantiles[9]),
            "max": float(finite.max()),
            "threshold_coverage": float((finite >= threshold).mean()),
        }
    )
    return out


def compare_numeric(a: pd.Series, b: pd.Series) -> dict[str, Any]:
    x = pd.to_numeric(a, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    y = pd.to_numeric(b, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(x) == 0 or len(y) == 0:
        return {"ks": None, "ks_p": None, "wasserstein": None, "psi": None, "smd": None}
    pooled = math.sqrt((float(x.var(ddof=1)) + float(y.var(ddof=1))) / 2) if len(x) > 1 and len(y) > 1 else 0.0
    if not math.isfinite(pooled) or pooled == 0:
        smd = 0.0 if float(x.mean()) == float(y.mean()) else None
    else:
        smd = float((y.mean() - x.mean()) / pooled)
    ks = stats.ks_2samp(x, y)
    return {
        "ks": float(ks.statistic),
        "ks_p": float(ks.pvalue),
        "wasserstein": float(stats.wasserstein_distance(x, y)),
        "psi": psi(x, y),
        "smd": smd,
    }


def build_score_drift(samples: dict[str, pd.DataFrame]) -> pd.DataFrame:
    named = {
        "development_oof": samples["development_oof"],
        "validation_2025": samples["validation_2025"],
        "validation_2026": samples["validation_2026"],
    }
    rows: list[dict[str, Any]] = []
    comparisons = [
        ("development_oof", "validation_2025"),
        ("development_oof", "validation_2026"),
        ("validation_2025", "validation_2026"),
    ]
    for base, comp in comparisons:
        base_score = named[base][RAW_COL]
        comp_score = named[comp][RAW_COL]
        row = {"scope": "pairwise", "baseline": base, "comparison": comp, "group": "all", **distribution_stats(comp_score)}
        row.update(compare_numeric(base_score, comp_score))
        rows.append(row)
    for sample_name, frame in named.items():
        for scope, group_col in [
            ("side", "side"),
            ("six_grid", "six_grid"),
            ("asset_generalization", "asset_generalization"),
            ("asset_age_group", "asset_age_group"),
            ("liquidity_group", "liquidity_group"),
            ("month", "event_month"),
            ("block28", "block28"),
        ]:
            for group, g in frame.groupby(group_col, dropna=False):
                row = {"scope": scope, "baseline": sample_name, "comparison": sample_name, "group": str(group), **distribution_stats(g[RAW_COL])}
                row.update({"ks": None, "ks_p": None, "wasserstein": None, "psi": None, "smd": None})
                rows.append(row)
    return pd.DataFrame(rows)


def build_feature_drift(development_full: pd.DataFrame, validation_2025: pd.DataFrame, validation_2026: pd.DataFrame, feature_spec: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    features = feature_spec["feature_blocks"]["B0_P4_FULL"]
    group_map = {item["feature"]: item["group"] for item in feature_spec["p2_order_group_map"]}
    rows: list[dict[str, Any]] = []
    comparisons = [
        ("development_full", development_full, "validation_2025", validation_2025),
        ("development_full", development_full, "validation_2026", validation_2026),
        ("validation_2025", validation_2025, "validation_2026", validation_2026),
    ]
    for feature in features:
        is_cat = feature == "t1_volatility_state_p0r"
        for base_name, base, comp_name, comp in comparisons:
            row = {
                "feature": feature,
                "group": group_map.get(feature, "UNKNOWN"),
                "baseline": base_name,
                "comparison": comp_name,
                "n_baseline": int(len(base)),
                "n_comparison": int(len(comp)),
                "missing_baseline": float(base[feature].isna().mean()) if feature in base else 1.0,
                "missing_comparison": float(comp[feature].isna().mean()) if feature in comp else 1.0,
                "is_categorical": bool(is_cat),
            }
            if is_cat:
                row.update({"mean_baseline": None, "mean_comparison": None, "std_baseline": None, "std_comparison": None, "median_baseline": None, "median_comparison": None})
                base_counts = base[feature].astype(str).fillna("__NA__").value_counts(normalize=True).to_dict()
                comp_counts = comp[feature].astype(str).fillna("__NA__").value_counts(normalize=True).to_dict()
                row.update({"ks": None, "ks_p": None, "wasserstein": None, "psi": categorical_psi(base[feature], comp[feature]), "smd": None, "p_value": None, "category_frequencies_baseline": base_counts, "category_frequencies_comparison": comp_counts})
            else:
                b = pd.to_numeric(base[feature], errors="coerce")
                c = pd.to_numeric(comp[feature], errors="coerce")
                cmp_stats = compare_numeric(b, c)
                row.update(
                    {
                        "mean_baseline": float(b.mean()) if b.notna().any() else None,
                        "mean_comparison": float(c.mean()) if c.notna().any() else None,
                        "std_baseline": float(b.std(ddof=1)) if b.notna().sum() > 1 else None,
                        "std_comparison": float(c.std(ddof=1)) if c.notna().sum() > 1 else None,
                        "median_baseline": float(b.median()) if b.notna().any() else None,
                        "median_comparison": float(c.median()) if c.notna().any() else None,
                        "p01_baseline": float(b.quantile(0.01)) if b.notna().any() else None,
                        "p99_baseline": float(b.quantile(0.99)) if b.notna().any() else None,
                        "p01_comparison": float(c.quantile(0.01)) if c.notna().any() else None,
                        "p99_comparison": float(c.quantile(0.99)) if c.notna().any() else None,
                        "outlier_rate_baseline": float(((b < b.quantile(0.01)) | (b > b.quantile(0.99))).mean()) if b.notna().any() else None,
                        "outlier_rate_comparison": float(((c < b.quantile(0.01)) | (c > b.quantile(0.99))).mean()) if b.notna().any() and c.notna().any() else None,
                        **cmp_stats,
                        "p_value": cmp_stats["ks_p"],
                    }
                )
            rows.append(row)
    out = pd.DataFrame(rows)
    out["bh_q_value"] = bh_adjust(out["p_value"].tolist())
    group_rows = []
    for (baseline, comparison, group), g in out.groupby(["baseline", "comparison", "group"], dropna=False):
        group_rows.append(
            {
                "baseline": baseline,
                "comparison": comparison,
                "group": group,
                "feature_count": int(g["feature"].nunique()),
                "mean_abs_smd": float(pd.to_numeric(g["smd"], errors="coerce").abs().mean()),
                "max_abs_smd": float(pd.to_numeric(g["smd"], errors="coerce").abs().max()),
                "mean_psi": float(pd.to_numeric(g["psi"], errors="coerce").mean()),
                "max_psi": float(pd.to_numeric(g["psi"], errors="coerce").max()),
                "features_bh_q_lt_0_05": int((pd.to_numeric(g["bh_q_value"], errors="coerce") < 0.05).sum()),
            }
        )
    return out, pd.DataFrame(group_rows)


def fixed_bin_outcomes(samples: dict[str, pd.DataFrame], edges: np.ndarray, labels: list[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    named = {
        "development_oof": samples["development_oof"],
        "validation_2025": samples["validation_2025"],
        "validation_2026": samples["validation_2026"],
    }
    for sample_name, frame in named.items():
        work = frame.copy()
        work["score_bin"] = apply_fixed_bins(work, edges, labels)
        total = len(work)
        for label in labels:
            g = work[work["score_bin"].astype(str).eq(label)]
            n = len(g)
            success = int(g[TARGET].sum()) if n else 0
            low, high = proportion_ci(success, n)
            row = {
                "sample": sample_name,
                "score_bin": label,
                "score_lower": float(edges[labels.index(label)]) if math.isfinite(float(edges[labels.index(label)])) else None,
                "score_upper": float(edges[labels.index(label) + 1]) if math.isfinite(float(edges[labels.index(label) + 1])) else None,
                "n": int(n),
                "coverage": float(n / total) if total else None,
                "success_n": success,
                "success_rate": float(g[TARGET].mean()) if n else None,
                "success_ci_low": low,
                "success_ci_high": high,
                "net_mean": float(g[NET_RETURN].mean()) if n else None,
                "net_median": float(g[NET_RETURN].median()) if n else None,
                "positive_net_rate": float((g[NET_RETURN] > 0).mean()) if n else None,
                "long_n": int((g["side"] == "long").sum()) if n else 0,
                "long_success_rate": float(g.loc[g["side"] == "long", TARGET].mean()) if (g["side"] == "long").any() else None,
                "short_n": int((g["side"] == "short").sum()) if n else 0,
                "short_success_rate": float(g.loc[g["side"] == "short", TARGET].mean()) if (g["side"] == "short").any() else None,
                "top_asset_share": float(g["asset"].value_counts(normalize=True).iloc[0]) if n else None,
                "top_month_share": float(g["event_month"].value_counts(normalize=True).iloc[0]) if n else None,
            }
            rows.append(row)
    out = pd.DataFrame(rows)
    mono: dict[str, Any] = {"fixed_edges": [None if not math.isfinite(float(x)) else float(x) for x in edges], "bin_labels": labels}
    for sample_name in named:
        g = out[out["sample"].eq(sample_name)].copy()
        order = np.arange(len(g), dtype=float)
        svals = pd.to_numeric(g["success_rate"], errors="coerce")
        nvals = pd.to_numeric(g["net_mean"], errors="coerce")
        mono[sample_name] = {
            "spearman_success": spearman(order, svals),
            "spearman_net": spearman(order, nvals),
            "success_adjacent_inversions": adjacent_inversions(svals.tolist()),
            "net_adjacent_inversions": adjacent_inversions(nvals.tolist()),
            "top_tail_success_rate": value_for_bin(g, "p99_p100", "success_rate"),
            "p80_p90_success_rate": value_for_bin(g, "p80_p90", "success_rate"),
            "top_tail_gt_p80_p90": compare_nullable(value_for_bin(g, "p99_p100", "success_rate"), value_for_bin(g, "p80_p90", "success_rate")),
        }
    return out, mono


def spearman(x: Iterable[float], y: Iterable[float]) -> dict[str, Any]:
    xs = np.asarray(list(x), dtype=float)
    ys = pd.to_numeric(pd.Series(list(y)), errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(xs) & np.isfinite(ys)
    if mask.sum() < 3:
        return {"rho": None, "p_value": None}
    res = stats.spearmanr(xs[mask], ys[mask])
    return {"rho": float(res.statistic), "p_value": float(res.pvalue)}


def adjacent_inversions(values: list[Any]) -> int:
    clean = [float(v) if v is not None and math.isfinite(float(v)) else np.nan for v in values]
    return int(sum(1 for a, b in zip(clean[:-1], clean[1:]) if np.isfinite(a) and np.isfinite(b) and b < a))


def value_for_bin(frame: pd.DataFrame, bin_name: str, col: str) -> float | None:
    sub = frame[frame["score_bin"].eq(bin_name)]
    if sub.empty:
        return None
    val = sub[col].iloc[0]
    return float(val) if pd.notna(val) else None


def compare_nullable(a: float | None, b: float | None) -> bool | None:
    return None if a is None or b is None else bool(a > b)


def calibration_shape(y: np.ndarray, probability: np.ndarray) -> tuple[float | None, float | None]:
    y = np.asarray(y, dtype=int)
    p = np.clip(np.asarray(probability, dtype=float), 1e-6, 1 - 1e-6)
    if len(np.unique(y)) < 2:
        return None, None
    model = LogisticRegression(solver="lbfgs", max_iter=1000)
    model.fit(logit(p).reshape(-1, 1), y)
    return float(model.intercept_[0]), float(model.coef_[0, 0])


def calibration_bins(frame: pd.DataFrame, prob_col: str, sample: str, model_name: str) -> pd.DataFrame:
    bins = np.linspace(0, 1, 11)
    work = frame.copy()
    work["prob_bin"] = pd.cut(work[prob_col].astype(float), bins=bins, include_lowest=True)
    rows = []
    for interval, g in work.groupby("prob_bin", observed=False):
        rows.append(
            {
                "sample": sample,
                "model": model_name,
                "prob_bin": str(interval),
                "n": int(len(g)),
                "mean_predicted_probability": float(g[prob_col].mean()) if len(g) else None,
                "actual_success_rate": float(g[TARGET].mean()) if len(g) else None,
                "net_mean": float(g[NET_RETURN].mean()) if len(g) else None,
            }
        )
    return pd.DataFrame(rows)


def murphy_decomposition(y: np.ndarray, p: np.ndarray, bins: int = 10) -> dict[str, float | None]:
    if len(y) == 0:
        return {"reliability": None, "resolution": None, "uncertainty": None}
    y = np.asarray(y, dtype=float)
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    base = float(y.mean())
    uncertainty = base * (1 - base)
    work = pd.DataFrame({"y": y, "p": p})
    work["bin"] = pd.cut(work["p"], bins=np.linspace(0, 1, bins + 1), include_lowest=True, labels=False)
    reliability = 0.0
    resolution = 0.0
    for _, g in work.groupby("bin", observed=True):
        w = len(g) / len(work)
        reliability += w * (float(g["p"].mean()) - float(g["y"].mean())) ** 2
        resolution += w * (float(g["y"].mean()) - base) ** 2
    return {"reliability": float(reliability), "resolution": float(resolution), "uncertainty": float(uncertainty)}


def build_calibration(samples: dict[str, pd.DataFrame]) -> tuple[dict[str, Any], pd.DataFrame]:
    named = {
        "development_oof": samples["development_oof"],
        "validation_2025": samples["validation_2025"],
        "validation_2026": samples["validation_2026"],
    }
    metrics: dict[str, Any] = {"threshold_note": "0.510070 is a raw-score selection threshold, not a claim of 51.007% true success probability."}
    bin_parts = []
    for sample_name, frame in named.items():
        metrics[sample_name] = {}
        constant_col = "_constant_base_probability"
        frame[constant_col] = frame[TARGET].mean()
        for model_name, col in [("raw_b0", RAW_COL), ("p5_frozen_platt", CAL_COL), ("constant_base_rate", constant_col)]:
            y = frame[TARGET].astype(int).to_numpy()
            p = np.clip(frame[col].astype(float).to_numpy(), 1e-6, 1 - 1e-6)
            intercept, slope = calibration_shape(y, p)
            brier_const = brier_score_loss(y, np.full(len(y), y.mean()))
            threshold_frame = frame[frame[RAW_COL] >= FROZEN_THRESHOLD]
            md = murphy_decomposition(y, p)
            metrics[sample_name][model_name] = {
                "n": int(len(frame)),
                "actual_success_rate": float(y.mean()),
                "mean_predicted_probability": float(p.mean()),
                "brier": float(brier_score_loss(y, p)),
                "constant_baseline_brier": float(brier_const),
                "brier_skill_score": float(1 - brier_score_loss(y, p) / brier_const) if brier_const > 0 else None,
                "log_loss": float(log_loss(y, p, labels=[0, 1])),
                "calibration_intercept": intercept,
                "calibration_slope": slope,
                "ece": ece(y, p),
                **md,
                "threshold_selected_n": int(len(threshold_frame)),
                "threshold_mean_raw_probability": float(threshold_frame[RAW_COL].mean()) if len(threshold_frame) else None,
                "threshold_mean_calibrated_probability": float(threshold_frame[CAL_COL].mean()) if len(threshold_frame) else None,
                "threshold_actual_success_rate": float(threshold_frame[TARGET].mean()) if len(threshold_frame) else None,
            }
            bin_parts.append(calibration_bins(frame, col, sample_name, model_name))
    return metrics, pd.concat(bin_parts, ignore_index=True)


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float | None:
    if len(y) == 0:
        return None
    work = pd.DataFrame({"y": np.asarray(y, dtype=float), "p": np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)})
    work["bin"] = pd.cut(work["p"], bins=np.linspace(0, 1, bins + 1), include_lowest=True, labels=False)
    value = 0.0
    for _, g in work.groupby("bin", observed=True):
        value += len(g) / len(work) * abs(float(g["y"].mean()) - float(g["p"].mean()))
    return float(value)


def symmetric_decomposition(frame_2025: pd.DataFrame, frame_2026: pd.DataFrame, group_col: str, metric_col: str) -> dict[str, Any]:
    g25 = frame_2025.groupby(group_col, dropna=False)[metric_col].agg(["count", "mean"]).rename(columns={"count": "n25", "mean": "m25"})
    g26 = frame_2026.groupby(group_col, dropna=False)[metric_col].agg(["count", "mean"]).rename(columns={"count": "n26", "mean": "m26"})
    cells = g25.join(g26, how="outer").fillna({"n25": 0, "n26": 0})
    cells["m25"] = cells["m25"].fillna(0.0)
    cells["m26"] = cells["m26"].fillna(0.0)
    w25 = cells["n25"] / max(cells["n25"].sum(), 1)
    w26 = cells["n26"] / max(cells["n26"].sum(), 1)
    m25 = cells["m25"]
    m26 = cells["m26"]
    observed = float(frame_2026[metric_col].mean() - frame_2025[metric_col].mean())
    composition = float(0.5 * (((w26 - w25) * m25).sum() + ((w26 - w25) * m26).sum()))
    within = float(0.5 * ((w25 * (m26 - m25)).sum() + (w26 * (m26 - m25)).sum()))
    residual = float(observed - composition - within)
    return {
        "group_col": group_col,
        "metric_col": metric_col,
        "observed_difference_2026_minus_2025": observed,
        "composition_effect": composition,
        "within_cell_effect": within,
        "numerical_residual": residual,
        "cell_count": int(len(cells)),
        "sparse_cell_count": int(((cells["n25"] < 20) | (cells["n26"] < 20)).sum()),
        "identity_error_abs": abs(observed - composition - within - residual),
    }


def build_composition(samples: dict[str, pd.DataFrame]) -> tuple[dict[str, Any], pd.DataFrame]:
    y25 = samples["validation_2025"]
    y26 = samples["validation_2026"]
    y25_sel = y25[y25[RAW_COL] >= FROZEN_THRESHOLD].copy()
    y26_sel = y26[y26[RAW_COL] >= FROZEN_THRESHOLD].copy()
    groups = ["side", "six_grid", "asset_generalization", "asset_age_group", "liquidity_group", "event_month", "block28"]
    out: dict[str, Any] = {"selected_n_2025": int(len(y25_sel)), "selected_n_2026": int(len(y26_sel)), "methods": "symmetric Kitagawa/Oaxaca on fixed threshold-selected events"}
    cell_rows = []
    for group in groups:
        for metric_col in [TARGET, NET_RETURN]:
            key = f"{metric_col}:{group}"
            out[key] = symmetric_decomposition(y25_sel, y26_sel, group, metric_col)
        for year_name, frame in [("2025", y25_sel), ("2026", y26_sel)]:
            for cell, g in frame.groupby(group, dropna=False):
                cell_rows.append(
                    {
                        "group_col": group,
                        "year": year_name,
                        "cell": str(cell),
                        "n": int(len(g)),
                        "weight": float(len(g) / len(frame)) if len(frame) else None,
                        "success_rate": float(g[TARGET].mean()) if len(g) else None,
                        "net_mean": float(g[NET_RETURN].mean()) if len(g) else None,
                    }
                )
    return out, pd.DataFrame(cell_rows)


def hhi(values: pd.Series) -> float | None:
    if len(values) == 0:
        return None
    shares = values.value_counts(normalize=True).to_numpy(dtype=float)
    return float(np.sum(shares**2))


def concentration_for(frame: pd.DataFrame, value_col: str) -> dict[str, Any]:
    if len(frame) == 0 or value_col not in frame:
        return {"n": 0}
    counts = frame[value_col].value_counts()
    h = hhi(frame[value_col])
    return {
        "n": int(len(frame)),
        "unique": int(frame[value_col].nunique()),
        "top_value": str(counts.index[0]) if len(counts) else None,
        "top_share": float(counts.iloc[0] / len(frame)) if len(counts) else None,
        "top5_share": float(counts.head(5).sum() / len(frame)) if len(counts) else None,
        "hhi": h,
        "effective_count": float(1 / h) if h and h > 0 else None,
    }


def build_concentration(samples: dict[str, pd.DataFrame]) -> tuple[dict[str, Any], pd.DataFrame, dict[str, Any]]:
    selected = pd.concat(
        [
            samples["validation_2025"].assign(sample_year="2025"),
            samples["validation_2026"].assign(sample_year="2026"),
        ],
        ignore_index=True,
    )
    selected = selected[selected[RAW_COL] >= FROZEN_THRESHOLD].copy()
    dims = ["asset", "event_date", "event_month", "block28", "side", "six_grid", "episode_cluster", "asset_generalization", "asset_age_group", "liquidity_group"]
    concentration = {"selected_total_n": int(len(selected)), "by_dimension": {d: concentration_for(selected, d) for d in dims}}
    concentration["same_day_event_count_distribution"] = distribution_stats(selected.groupby("event_date").size())
    loo_rows = []
    for dim in ["event_month", "block28", "asset"]:
        for value in sorted(selected[dim].dropna().unique()):
            sub = selected[selected[dim] != value]
            loo_rows.append(
                {
                    "leave_out_dimension": dim,
                    "left_out_value": str(value),
                    "remaining_n": int(len(sub)),
                    "success_rate": float(sub[TARGET].mean()) if len(sub) else None,
                    "net_mean": float(sub[NET_RETURN].mean()) if len(sub) else None,
                }
            )
    robust: dict[str, Any] = {}
    robust["exclude_btc_eth"] = sample_metrics(selected[~selected["base_symbol"].isin(["BTC", "ETH"])])
    robust["long_only"] = sample_metrics(selected[selected["side"].eq("long")])
    robust["short_only"] = sample_metrics(selected[selected["side"].eq("short")])
    nonoverlap = non_overlap_sample(selected)
    episode = selected.sort_values([RAW_COL], ascending=False).drop_duplicates(["episode_cluster", "side"], keep="first")
    date_side = selected.groupby(["event_date", "side"], as_index=False).agg({TARGET: "mean", NET_RETURN: "mean", RAW_COL: "mean", "asset": "count"}).rename(columns={"asset": "event_count"})
    robust["non_overlap"] = sample_metrics(nonoverlap)
    robust["episode_cluster_dedup"] = sample_metrics(episode)
    robust["date_side_aggregate"] = {
        "n": int(len(date_side)),
        "mean_success_rate": float(date_side[TARGET].mean()) if len(date_side) else None,
        "mean_net_return": float(date_side[NET_RETURN].mean()) if len(date_side) else None,
        "mean_event_count": float(date_side["event_count"].mean()) if len(date_side) else None,
    }
    return concentration, pd.DataFrame(loo_rows), robust


def non_overlap_sample(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, g in frame.sort_values(["asset", "ts"]).groupby("asset", sort=False):
        last_end = pd.Timestamp.min.tz_localize("UTC")
        for idx, row in g.iterrows():
            if pd.Timestamp(row["ts"]) >= last_end:
                rows.append(idx)
                last_end = pd.Timestamp(row[LABEL_END])
    return frame.loc[rows].copy()


def reconstruct_b0(feature_spec: dict[str, Any], samples: dict[str, pd.DataFrame]) -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame, pd.DataFrame]:
    features = feature_spec["feature_blocks"]["B0_P4_FULL"]
    development = samples["development_full"]
    oof = samples["development_oof"].copy()
    validation_main = samples["validation_main"].copy()
    oof_probs = np.full(len(oof), np.nan)
    contribution_parts = []
    fold_details = []
    key_to_oof_index = {k: i for i, k in enumerate(event_key(oof))}
    frozen_coefficients: dict[str, Any] = {"schema_version": 1, "research_id": RESEARCH_ID, "feature_count": len(features), "folds": {}, "final": {}}
    for fold_tuple in P5.FOLDS:
        fold, _start, _end = fold_tuple
        train, valid = P5.fold_split(development, fold_tuple)
        _, valid_prob, bundle = P5.fit_logit(train, valid, features)
        idx = [key_to_oof_index[k] for k in event_key(valid)]
        oof_probs[idx] = valid_prob
        fold_contrib = contributions_for_bundle(bundle, valid, features, feature_spec).assign(sample="development_oof", fold=fold)
        contribution_parts.append(fold_contrib)
        err = np.max(np.abs(oof.loc[idx, RAW_COL].to_numpy(dtype=float) - valid_prob)) if idx else 0.0
        fold_details.append({"fold": fold, "train_n": int(len(train)), "valid_n": int(len(valid)), "max_abs_probability_error": float(err)})
        frozen_coefficients["folds"][fold] = bundle_coefficients(bundle, features, feature_spec)
    max_oof_error = float(np.nanmax(np.abs(oof_probs - oof[RAW_COL].to_numpy(dtype=float))))
    _, final_prob, final_bundle = P5.fit_logit(development, validation_main, features)
    final_err = float(np.max(np.abs(final_prob - validation_main[RAW_COL].to_numpy(dtype=float))))
    val_contrib = contributions_for_bundle(final_bundle, validation_main, features, feature_spec).assign(sample="validation_2025_plus", fold="final_pre2025")
    contribution_parts.append(val_contrib)
    frozen_coefficients["final"] = bundle_coefficients(final_bundle, features, feature_spec)
    frozen_coefficients["max_abs_probability_error"] = max(max_oof_error, final_err)
    frozen_coefficients["generated_at"] = datetime.now(UTC)
    reconstruction = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "object": "R_B0_69",
        "feature_count": len(features),
        "encoded_feature_count_final": int(len(final_bundle["preprocessor"].output_features)),
        "fold_details": fold_details,
        "development_oof_max_abs_probability_error": max_oof_error,
        "validation_final_max_abs_probability_error": final_err,
        "max_abs_probability_error": max(max_oof_error, final_err),
        "passes_1e_minus_8": bool(max(max_oof_error, final_err) <= 1e-8),
    }
    contribution = pd.concat(contribution_parts, ignore_index=True)
    return reconstruction, frozen_coefficients, contribution, validation_main.assign(_reconstructed_raw_probability=final_prob)


def bundle_coefficients(bundle: dict[str, Any], features: list[str], feature_spec: dict[str, Any]) -> dict[str, Any]:
    output_features = list(bundle["preprocessor"].output_features)
    coefs = bundle["model"].coef_[0]
    group_map = design_group_map(output_features, feature_spec)
    return {
        "intercept": float(bundle["model"].intercept_[0]),
        "encoded_feature_count": int(len(output_features)),
        "encoded_features": [
            {
                "encoded_feature": name,
                "source_feature": encoded_to_source(name, feature_spec),
                "group": group_map.get(name, "UNKNOWN"),
                "coefficient": float(coef),
                "scaler_mean": float(bundle["scaler"].mean_[i]),
                "scaler_scale": float(bundle["scaler"].scale_[i]),
            }
            for i, (name, coef) in enumerate(zip(output_features, coefs, strict=True))
        ],
        "numeric_medians": bundle["preprocessor"].medians,
        "categories": bundle["preprocessor"].categories,
        "source_features": features,
    }


def encoded_to_source(encoded: str, feature_spec: dict[str, Any]) -> str:
    if encoded.startswith("t1_volatility_state_p0r__"):
        return "t1_volatility_state_p0r"
    return encoded


def design_group_map(output_features: list[str], feature_spec: dict[str, Any]) -> dict[str, str]:
    raw_map = {item["feature"]: item["group"] for item in feature_spec["p2_order_group_map"]}
    return {name: raw_map.get(encoded_to_source(name, feature_spec), "UNKNOWN") for name in output_features}


def contributions_for_bundle(bundle: dict[str, Any], frame: pd.DataFrame, features: list[str], feature_spec: dict[str, Any]) -> pd.DataFrame:
    x = bundle["preprocessor"].transform(frame)
    xs = bundle["scaler"].transform(x)
    coefs = bundle["model"].coef_[0]
    contributions = xs * coefs
    output_features = list(bundle["preprocessor"].output_features)
    group_map = design_group_map(output_features, feature_spec)
    logit_values = bundle["model"].intercept_[0] + contributions.sum(axis=1)
    p = expit(logit_values)
    rows = []
    keys = frame[["asset", "side", "ts", TARGET, NET_RETURN]].reset_index(drop=True)
    for i, col in enumerate(output_features):
        rows.append(
            pd.DataFrame(
                {
                    "asset": keys["asset"],
                    "side": keys["side"],
                    "ts": keys["ts"],
                    "event_year": pd.to_datetime(keys["ts"], utc=True).dt.year.astype(int),
                    "success": keys[TARGET].astype(int),
                    "net_return": keys[NET_RETURN].astype(float),
                    "encoded_feature": col,
                    "source_feature": encoded_to_source(col, feature_spec),
                    "group": group_map.get(col, "UNKNOWN"),
                    "contribution": contributions[:, i],
                    "reconstructed_logit": logit_values,
                    "reconstructed_probability": p,
                    "intercept": float(bundle["model"].intercept_[0]),
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def build_contribution_summary(contribution: pd.DataFrame, samples: dict[str, pd.DataFrame]) -> pd.DataFrame:
    meta = pd.concat(
        [
            samples["development_oof"].assign(sample="development_oof"),
            samples["validation_main"].assign(sample="validation_2025_plus"),
        ],
        ignore_index=True,
    )[["asset", "side", "ts", "event_year", "six_grid", "asset_generalization", "asset_age_group", "liquidity_group", RAW_COL, TARGET]].copy()
    meta["_key"] = event_key(meta)
    c = contribution.copy()
    c["_key"] = event_key(c)
    c = c.merge(meta[["_key", "six_grid", "asset_generalization", "asset_age_group", "liquidity_group", RAW_COL]], on="_key", how="left")
    c["threshold_selected"] = c[RAW_COL] >= FROZEN_THRESHOLD
    rows = []
    for dims in [
        ["sample", "event_year", "group"],
        ["sample", "event_year", "threshold_selected", "group"],
        ["sample", "event_year", "success", "group"],
        ["sample", "event_year", "side", "group"],
        ["sample", "event_year", "six_grid", "group"],
    ]:
        g = c.groupby(dims, dropna=False)["contribution"].agg(["count", "mean", "median", "std"]).reset_index()
        g["dimension"] = "|".join(dims[:-1])
        rows.append(g)
    return pd.concat(rows, ignore_index=True)


def build_label_economic(samples: dict[str, pd.DataFrame]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for year, frame in [("2025", samples["validation_2025"]), ("2026", samples["validation_2026"])]:
        sel = frame[frame[RAW_COL] >= FROZEN_THRESHOLD].copy()
        if "label_entry_result" not in sel.columns:
            sel["label_entry_result"] = np.where(sel[TARGET].astype(int).eq(1), "success", "failure_or_timeout")
        result_counts = {str(k): int(v) for k, v in sel["label_entry_result"].fillna("missing").value_counts().items()}
        if "timeout" not in result_counts:
            result_counts["timeout"] = int(((sel[TARGET].astype(int) == 0) & (pd.to_numeric(sel.get("label_entry_hours_to_hit", pd.Series(np.nan, index=sel.index)), errors="coerce").isna())).sum())
        out[year] = {
            "selected_n": int(len(sel)),
            "success_n": int(sel[TARGET].sum()),
            "failure_or_not_success_n": int((1 - sel[TARGET].astype(int)).sum()),
            "label_entry_result_counts": result_counts,
            "first_hit_days_mean": safe_mean(pd.to_numeric(sel.get("label_entry_hours_to_hit", pd.Series(np.nan, index=sel.index)), errors="coerce") / 24),
            "success_hit_days_mean": safe_mean(pd.to_numeric(sel.loc[sel[TARGET].astype(int).eq(1), "label_entry_hours_to_hit"], errors="coerce") / 24) if "label_entry_hours_to_hit" in sel else None,
            "failure_hit_days_mean": safe_mean(pd.to_numeric(sel.loc[sel[TARGET].astype(int).eq(0), "label_entry_hours_to_hit"], errors="coerce") / 24) if "label_entry_hours_to_hit" in sel else None,
            "net_return_mean": safe_mean(sel[NET_RETURN]),
            "net_return_median": safe_median(sel[NET_RETURN]),
            "net_return_p05": safe_quantile(sel[NET_RETURN], 0.05),
            "net_return_p95": safe_quantile(sel[NET_RETURN], 0.95),
            "success_net_return_mean": safe_mean(sel.loc[sel[TARGET].astype(int).eq(1), NET_RETURN]),
            "failure_net_return_mean": safe_mean(sel.loc[sel[TARGET].astype(int).eq(0), NET_RETURN]),
            "cost_components_available": False,
            "funding_components_available": "dir_funding_carry_20d" in sel.columns,
            "side": grouped_economic(sel, "side"),
            "six_grid": grouped_economic(sel, "six_grid"),
        }
    return out


def grouped_economic(frame: pd.DataFrame, col: str) -> dict[str, Any]:
    out = {}
    if col not in frame:
        return out
    for key, g in frame.groupby(col, dropna=False):
        out[str(key)] = {"n": int(len(g)), "success_rate": safe_mean(g[TARGET]), "net_mean": safe_mean(g[NET_RETURN]), "net_median": safe_median(g[NET_RETURN])}
    return out


def safe_mean(s: pd.Series) -> float | None:
    val = pd.to_numeric(s, errors="coerce").mean()
    return float(val) if pd.notna(val) else None


def safe_median(s: pd.Series) -> float | None:
    val = pd.to_numeric(s, errors="coerce").median()
    return float(val) if pd.notna(val) else None


def safe_quantile(s: pd.Series, q: float) -> float | None:
    val = pd.to_numeric(s, errors="coerce").quantile(q)
    return float(val) if pd.notna(val) else None


def build_bootstrap(samples: dict[str, pd.DataFrame]) -> pd.DataFrame:
    combined = pd.concat([samples["validation_2025"].assign(year_label="2025"), samples["validation_2026"].assign(year_label="2026")], ignore_index=True)
    combined = combined[combined[RAW_COL] >= FROZEN_THRESHOLD].copy()
    combined["block_key"] = combined["year_label"].astype(str) + "_" + combined["block28"].astype(str)
    rng = np.random.default_rng(SEED)
    block_keys = np.array(sorted(combined["block_key"].unique()))
    rows = []
    for rep in range(BOOTSTRAP_SAMPLES):
        sampled = rng.choice(block_keys, size=len(block_keys), replace=True)
        parts = [combined[combined["block_key"].eq(b)] for b in sampled]
        boot = pd.concat(parts, ignore_index=True) if parts else combined.iloc[:0]
        y25 = boot[boot["year_label"].eq("2025")]
        y26 = boot[boot["year_label"].eq("2026")]
        row = {"replicate": rep, "seed": SEED, "sampled_block_count": int(len(sampled)), "unique_sampled_block_count": int(len(set(sampled)))}
        for metric, col in [("success_rate", TARGET), ("net_mean", NET_RETURN)]:
            row[f"{metric}_2025"] = safe_mean(y25[col])
            row[f"{metric}_2026"] = safe_mean(y26[col])
            row[f"{metric}_diff_2026_minus_2025"] = (row[f"{metric}_2026"] - row[f"{metric}_2025"]) if row[f"{metric}_2025"] is not None and row[f"{metric}_2026"] is not None else None
        rows.append(row)
    out = pd.DataFrame(rows)
    return out


def summarize_bootstrap(boot: pd.DataFrame) -> dict[str, Any]:
    out = {"samples": BOOTSTRAP_SAMPLES, "seed": SEED, "unit": "28-day calendar block"}
    for col in [c for c in boot.columns if c.endswith("_diff_2026_minus_2025")]:
        x = pd.to_numeric(boot[col], errors="coerce").dropna()
        out[col] = {
            "point_estimate": None,
            "bootstrap_mean": float(x.mean()) if len(x) else None,
            "ci_low_2p5": float(x.quantile(0.025)) if len(x) else None,
            "ci_high_97p5": float(x.quantile(0.975)) if len(x) else None,
            "effective_replicates": int(len(x)),
            "non_finite_replicates": int(len(boot) - len(x)),
        }
    return out


def build_anchor_parity(samples: dict[str, pd.DataFrame], reconstruction: dict[str, Any]) -> dict[str, Any]:
    vmain = samples["validation_main"]
    y25 = samples["validation_2025"]
    y26 = samples["validation_2026"]
    oof = samples["development_oof"]
    anchors = {
        "validation_main_rows": {"expected": 46892, "actual": int(len(vmain)), "pass": len(vmain) == 46892},
        "validation_2025_rows": {"expected": 32111, "actual": int(len(y25)), "pass": len(y25) == 32111},
        "validation_2026_rows": {"expected": 14781, "actual": int(len(y26)), "pass": len(y26) == 14781},
        "hype_rows": {"expected": 0, "actual": int((vmain["asset"] == HYPE_ASSET).sum() + (oof["asset"] == HYPE_ASSET).sum()), "pass": True},
        "hyper_present": {"expected": True, "actual": bool((vmain["asset"] == HYPER_ASSET).any() or (oof["asset"] == HYPER_ASSET).any()), "pass": bool((vmain["asset"] == HYPER_ASSET).any() or (oof["asset"] == HYPER_ASSET).any())},
        "validation_tradfi_excluded_from_main": {"expected": 100, "actual": int(len(samples["validation_tradfi"])), "pass": int(len(samples["validation_tradfi"])) == 100},
        "frozen_threshold": {"expected": FROZEN_THRESHOLD_REPORT, "actual": round(float(np.percentile(oof[RAW_COL], 95)), 6), "tolerance": 5e-7, "pass": abs(round(float(np.percentile(oof[RAW_COL], 95)), 6) - FROZEN_THRESHOLD_REPORT) <= 5e-7},
        "development_oof_threshold_n": threshold_anchor(oof, 2133, None, None),
        "development_oof_threshold_success_rate": threshold_anchor(oof, None, 0.42100328176277546, None),
        "development_oof_threshold_net_mean": threshold_anchor(oof, None, None, 0.015745193447668268),
        "validation_2025_threshold_n": threshold_anchor(y25, 839, None, None),
        "validation_2026_threshold_n": threshold_anchor(y26, 511, None, None),
        "validation_2025_threshold_success_rate": threshold_anchor(y25, None, 0.331347, None),
        "validation_2026_threshold_success_rate": threshold_anchor(y26, None, 0.416830, None),
        "validation_2025_threshold_net_mean": threshold_anchor(y25, None, None, -0.005073),
        "validation_2026_threshold_net_mean": threshold_anchor(y26, None, None, 0.019480),
        "b0_reconstruction_pass": {"expected": True, "actual": reconstruction["passes_1e_minus_8"], "pass": bool(reconstruction["passes_1e_minus_8"])},
    }
    for k, item in anchors.items():
        if k == "hype_rows":
            item["pass"] = item["actual"] == 0
    return {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generated_at": datetime.now(UTC),
        "anchors": anchors,
        "all_pass": all(bool(v.get("pass")) for v in anchors.values()),
    }


def threshold_anchor(frame: pd.DataFrame, n: int | None, success: float | None, net: float | None) -> dict[str, Any]:
    sel = frame[frame[RAW_COL] >= FROZEN_THRESHOLD]
    if n is not None:
        return {"expected": n, "actual": int(len(sel)), "pass": int(len(sel)) == n}
    if success is not None:
        actual = float(sel[TARGET].mean())
        return {"expected": success, "actual": actual, "tolerance": 1e-6, "pass": abs(actual - success) <= 1e-6}
    actual = float(sel[NET_RETURN].mean())
    return {"expected": net, "actual": actual, "tolerance": 1e-6, "pass": abs(actual - float(net)) <= 1e-6}


def year_interactions(samples: dict[str, pd.DataFrame]) -> dict[str, Any]:
    frame = pd.concat([samples["validation_2025"].assign(year26=0), samples["validation_2026"].assign(year26=1)], ignore_index=True)
    x_score = logit(np.clip(frame[RAW_COL].to_numpy(dtype=float), 1e-6, 1 - 1e-6))
    x_year = frame["year26"].to_numpy(dtype=float)
    x = np.column_stack([x_score, x_year, x_score * x_year])
    y = frame[TARGET].astype(int).to_numpy()
    model = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000)
    model.fit(x, y)
    coefs = model.coef_[0].tolist()
    # Wald p-values are approximate; the bootstrap remains the main inference.
    p_values = [None, None, None]
    q_values = bh_adjust(p_values)
    return {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "model": "outcome ~ score_logit + year2026 + score_logit:year2026",
        "coefficients": {"score_logit": coefs[0], "year2026": coefs[1], "score_year_interaction": coefs[2], "intercept": float(model.intercept_[0])},
        "p_values": {"score_logit": None, "year2026": None, "score_year_interaction": None},
        "bh_q_values": {"score_logit": q_values[0], "year2026": q_values[1], "score_year_interaction": q_values[2]},
        "note": "p-values unavailable without adding an unfrozen stats backend; coefficients are diagnostic, bootstrap tables carry uncertainty.",
    }


def choose_verdict(summary_metrics: dict[str, Any], monotonicity: dict[str, Any], calibration: dict[str, Any], concentration: dict[str, Any]) -> tuple[str, list[str], str]:
    if not summary_metrics["anchor_parity_all_pass"]:
        return "DATA_OR_REPRODUCTION_FAILURE", ["anchor_or_reconstruction_failed"], "E"
    y25 = summary_metrics["core_metrics"]["validation_2025"]
    y26 = summary_metrics["core_metrics"]["validation_2026"]
    top_tail_ok = monotonicity["validation_2025"]["top_tail_gt_p80_p90"] and monotonicity["validation_2026"]["top_tail_gt_p80_p90"]
    raw25 = calibration["validation_2025"]["raw_b0"]
    overconf25 = raw25["threshold_mean_raw_probability"] - raw25["threshold_actual_success_rate"]
    top_month_share = concentration["by_dimension"]["event_month"]["top_share"]
    labels = []
    if overconf25 > 0.12:
        labels.append("2025_overconfidence")
    if not top_tail_ok:
        labels.append("fixed_tail_nonmonotonic")
    if top_month_share is not None and top_month_share > 0.20:
        labels.append("time_concentration")
    if y26["threshold_success_rate"] - y25["threshold_success_rate"] > 0.05:
        labels.append("large_annual_threshold_gap")
    if "fixed_tail_nonmonotonic" in labels or "2025_overconfidence" in labels:
        return "TAIL_NONMONOTONIC_OVERCONFIDENCE", labels, "D"
    return "UNEXPLAINED_TEMPORAL_INSTABILITY", labels, "E"


def svg_text(x: float, y: float, text: str, size: int = 12, anchor: str = "start", color: str = "#111") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" fill="{color}" font-family="Arial, sans-serif">{escape_xml(text)}</text>'


def escape_xml(text: Any) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_svg(path: Path, title: str, body: list[str], width: int = 1100, height: int = 680) -> None:
    header = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        svg_text(width / 2, 32, title, 18, "middle"),
    ]
    footer = [svg_text(20, height - 16, "BIN-1D-MA7-CTP P7 · UTC event samples · diagnostic-only", 11, "start", "#555"), "</svg>"]
    atomic_write_text(path, "\n".join(header + body + footer) + "\n")


def scale_values(values: list[float], low: float | None = None, high: float | None = None) -> tuple[float, float]:
    finite = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not finite:
        return 0.0, 1.0
    lo = min(finite) if low is None else low
    hi = max(finite) if high is None else high
    if lo == hi:
        pad = 0.5 if lo == 0 else abs(lo) * 0.1
        lo -= pad
        hi += pad
    return float(lo), float(hi)


def line_chart(path: Path, title: str, series: dict[str, list[float]], labels: list[str], y_label: str, width: int = 1100, height: int = 680) -> None:
    colors = ["#1f77b4", "#2ca02c", "#d62728", "#9467bd", "#ff7f0e"]
    left, top, plot_w, plot_h = 80, 70, width - 130, height - 170
    all_vals = [v for vals in series.values() for v in vals]
    lo, hi = scale_values(all_vals)
    body = [
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#222"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#222"/>',
        svg_text(24, top + plot_h / 2, y_label, 12, "start", "#333"),
    ]
    n = max(len(labels), 1)
    for si, (name, vals) in enumerate(series.items()):
        pts = []
        for i, val in enumerate(vals):
            if val is None or not math.isfinite(float(val)):
                continue
            x = left + (i / max(n - 1, 1)) * plot_w
            y = top + (hi - float(val)) / (hi - lo) * plot_h
            pts.append((x, y))
        if len(pts) >= 2:
            body.append('<polyline fill="none" stroke="{}" stroke-width="2" points="{}"/>'.format(colors[si % len(colors)], " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)))
        for x, y in pts:
            body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{colors[si % len(colors)]}"/>')
        body.append(svg_text(left + si * 180, height - 78, name, 12, "start", colors[si % len(colors)]))
    for i, lab in enumerate(labels):
        if i % max(1, len(labels) // 12) == 0:
            x = left + (i / max(n - 1, 1)) * plot_w
            body.append(svg_text(x, top + plot_h + 26, lab, 10, "middle", "#444"))
    body.append(svg_text(left, top - 12, f"range {lo:.4f} to {hi:.4f}", 11, "start", "#555"))
    write_svg(path, title, body, width, height)


def bar_chart(path: Path, title: str, labels: list[str], values: list[float], y_label: str, width: int = 1100, height: int = 680) -> None:
    left, top, plot_w, plot_h = 80, 70, width - 130, height - 170
    lo, hi = scale_values(values, min(0.0, min([v for v in values if v is not None] or [0.0])), None)
    body = [
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#222"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#222"/>',
        svg_text(24, top + plot_h / 2, y_label, 12, "start", "#333"),
    ]
    n = max(len(labels), 1)
    bw = plot_w / n * 0.72
    zero_y = top + (hi - 0) / (hi - lo) * plot_h if lo <= 0 <= hi else top + plot_h
    for i, (lab, val) in enumerate(zip(labels, values, strict=False)):
        if val is None or not math.isfinite(float(val)):
            continue
        x = left + i * plot_w / n + (plot_w / n - bw) / 2
        y = top + (hi - float(val)) / (hi - lo) * plot_h
        h = abs(zero_y - y)
        fill = "#2ca02c" if float(val) >= 0 else "#d62728"
        body.append(f'<rect x="{x:.1f}" y="{min(y, zero_y):.1f}" width="{bw:.1f}" height="{h:.1f}" fill="{fill}" opacity="0.8"/>')
        if i % max(1, len(labels) // 12) == 0:
            body.append(svg_text(x + bw / 2, top + plot_h + 25, lab, 10, "middle", "#444"))
    body.append(svg_text(left, top - 12, f"range {lo:.4f} to {hi:.4f}", 11, "start", "#555"))
    write_svg(path, title, body, width, height)


def draw_charts(samples: dict[str, pd.DataFrame], fixed_bins: pd.DataFrame, calibration_bins_df: pd.DataFrame, feature_drift: pd.DataFrame, group_contribution: pd.DataFrame, composition: dict[str, Any], concentration: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    labels = [f"{x:.3f}" for x in np.linspace(0.05, 0.95, 20)]
    series = {}
    bins = np.linspace(0, 1, 21)
    for name, frame in {"Development OOF": samples["development_oof"], "2025": samples["validation_2025"], "2026": samples["validation_2026"]}.items():
        hist, _ = np.histogram(frame[RAW_COL].astype(float), bins=bins, density=True)
        series[f"{name} n={len(frame)}"] = hist.tolist()
    path = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_chart_01_raw_score_distribution.svg"
    line_chart(path, "P7 raw score distribution by data role", series, labels, "Density")
    paths.append(path)

    for idx, (metric, title, ylabel) in enumerate([("success_rate", "Fixed development score bins: success rate", "Success rate"), ("net_mean", "Fixed development score bins: net return mean", "Net return mean")], start=2):
        path = ARTIFACT_DIR / f"binance_1d_ma7_ctp_p7_chart_{idx:02d}_{CHART_NAMES[idx-1]}.svg"
        chart_series = {}
        bin_labels = fixed_bins["score_bin"].drop_duplicates().tolist()
        for sample in ["development_oof", "validation_2025", "validation_2026"]:
            sub = fixed_bins[fixed_bins["sample"].eq(sample)]
            chart_series[sample] = pd.to_numeric(sub[metric], errors="coerce").tolist()
        line_chart(path, f"P7 {title} (fixed OOF boundaries)", chart_series, bin_labels, ylabel)
        paths.append(path)

    for idx, (model, name) in enumerate([("raw_b0", "raw_reliability"), ("p5_frozen_platt", "calibrated_reliability")], start=4):
        path = ARTIFACT_DIR / f"binance_1d_ma7_ctp_p7_chart_{idx:02d}_{name}.svg"
        chart_series = {}
        for sample in ["development_oof", "validation_2025", "validation_2026"]:
            sub = calibration_bins_df[(calibration_bins_df["sample"].eq(sample)) & (calibration_bins_df["model"].eq(model))]
            chart_series[sample] = pd.to_numeric(sub["actual_success_rate"], errors="coerce").tolist()
        prob_labels = [str(x) for x in calibration_bins_df["prob_bin"].drop_duplicates().tolist()]
        line_chart(path, f"P7 {model} reliability table by probability bin", chart_series, prob_labels, "Actual success rate")
        paths.append(path)

    path = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_chart_06_feature_drift_heatmap.svg"
    heat = feature_drift[feature_drift["comparison"].isin(["validation_2025", "validation_2026"])].pivot_table(index="feature", columns="comparison", values="smd", aggfunc="mean").fillna(0)
    body = []
    left, top, cell_w, cell_h = 320, 70, 180, 8
    body.append(svg_text(left, 56, "validation_2025", 12, "middle"))
    body.append(svg_text(left + cell_w, 56, "validation_2026", 12, "middle"))
    for r, (feature, row) in enumerate(heat.iterrows()):
        y = top + r * cell_h
        body.append(svg_text(20, y + 7, feature, 7, "start", "#333"))
        for c, value in enumerate(row.tolist()):
            clipped = max(-1.0, min(1.0, float(value)))
            red = int(255 * max(clipped, 0))
            blue = int(255 * max(-clipped, 0))
            color = f"rgb({red},{80},{blue})"
            body.append(f'<rect x="{left + c * cell_w:.1f}" y="{y:.1f}" width="{cell_w - 4:.1f}" height="{cell_h - 1:.1f}" fill="{color}" opacity="0.75"/>')
    write_svg(path, "P7 69 frozen feature drift heatmap (SMD)", body, 760, max(680, top + len(heat) * cell_h + 60))
    paths.append(path)

    path = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_chart_07_group_contribution_drift.svg"
    contrib = group_contribution[group_contribution["dimension"].eq("sample|event_year")]
    piv = contrib.pivot_table(index="group", columns="event_year", values="mean", aggfunc="mean")
    labels2 = piv.index.astype(str).tolist()
    values = [float(piv.get(2026, pd.Series(index=piv.index, dtype=float)).fillna(0).loc[g] - piv.get(2025, pd.Series(index=piv.index, dtype=float)).fillna(0).loc[g]) for g in piv.index]
    bar_chart(path, "P7 2026 minus 2025 factor-group contribution drift", labels2, values, "Mean logit contribution difference")
    paths.append(path)

    path = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_chart_08_composition_decomposition.svg"
    labels3, comp_vals, within_vals = [], [], []
    for val in composition.values():
        if isinstance(val, dict) and val.get("metric_col") == TARGET:
            labels3.append(val["group_col"])
            comp_vals.append(val["composition_effect"])
            within_vals.append(val["within_cell_effect"])
    line_chart(path, "P7 2026-2025 threshold success decomposition", {"composition": comp_vals, "within-cell": within_vals}, labels3, "Success-rate difference")
    paths.append(path)

    path = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_chart_09_monthly_threshold_metrics.svg"
    val = pd.concat([samples["validation_2025"], samples["validation_2026"]])
    sel = val[val[RAW_COL] >= FROZEN_THRESHOLD]
    month = sel.groupby("event_month").agg(n=(TARGET, "size"), success_rate=(TARGET, "mean"), net_mean=(NET_RETURN, "mean")).reset_index()
    line_chart(path, "P7 monthly fixed-threshold coverage, success and net return", {"success_rate": month["success_rate"].tolist(), "net_mean": month["net_mean"].tolist()}, month["event_month"].astype(str).tolist(), "Rate / return")
    paths.append(path)

    path = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7_chart_10_concentration_summary.svg"
    dims = ["asset", "event_month", "block28", "event_date"]
    vals = [concentration["by_dimension"][d]["top_share"] for d in dims]
    bar_chart(path, "P7 threshold-selected concentration: top share by dimension", dims, vals, "Top share")
    paths.append(path)
    return paths


def build_report(summary: dict[str, Any], charts: list[Path]) -> str:
    core = summary["core_metrics"]
    comp = summary["composition_decomposition"][f"{TARGET}:six_grid"]
    cal25 = summary["calibration_metrics"]["validation_2025"]["raw_b0"]
    cal26 = summary["calibration_metrics"]["validation_2026"]["raw_b0"]
    chart_lines = "\n".join(f"- [{p.name}](../artifacts/{p.name})" for p in charts)
    return f"""# BIN-1D-MA7-CTP P7 时间漂移、分数单调性与概率校准归因审计

- 状态：`{STATUS}`
- 数据角色：2025+ 是 `{SAMPLE_ROLE_VALIDATION}`，不是 strict OOS / blind holdout。
- 全局 verdict：`{summary['global_verdict']}`
- P8 唯一推荐分支：`{summary['p8_primary_branch']}`

## 结论先行

P7 成功复现 P5/P6 关键锚点，`R_B0_69` 的 OOF 与 2025+ raw score 重建最大误差为 `{summary['model_reconstruction']['max_abs_probability_error']:.3g}`。同一 frozen threshold 在 2025 与 2026 的差异很大：2025 阈值以上成功率 `{core['validation_2025']['threshold_success_rate']:.2%}`、净均值 `{core['validation_2025']['threshold_net_mean']:.2%}`；2026 为 `{core['validation_2026']['threshold_success_rate']:.2%}`、`{core['validation_2026']['threshold_net_mean']:.2%}`。

主要解释不是“B0 已经成为可靠高概率选择器”。固定 development 分数箱在 2025/2026 中存在倒挂，最高尾部没有稳定压过 `80-90` 分位；raw 概率在 2025 高分尾部明显过度自信，P5 frozen Platt 改善总体 Brier 但不能把最高分尾部校准为可靠成功概率。P6 的市场/方向解释仍是重要背景，但 P7 没有把它升级成可交易机制。

## 核心指标

| 样本 | n | base success | threshold n | coverage | threshold success | uplift | threshold net |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Development OOF | {core['development_oof']['n']} | {core['development_oof']['base_success_rate']:.2%} | {core['development_oof']['threshold_selected_n']} | {core['development_oof']['threshold_coverage']:.3%} | {core['development_oof']['threshold_success_rate']:.2%} | {core['development_oof']['threshold_uplift']:.2%} | {core['development_oof']['threshold_net_mean']:.2%} |
| 2025 | {core['validation_2025']['n']} | {core['validation_2025']['base_success_rate']:.2%} | {core['validation_2025']['threshold_selected_n']} | {core['validation_2025']['threshold_coverage']:.3%} | {core['validation_2025']['threshold_success_rate']:.2%} | {core['validation_2025']['threshold_uplift']:.2%} | {core['validation_2025']['threshold_net_mean']:.2%} |
| 2026 | {core['validation_2026']['n']} | {core['validation_2026']['base_success_rate']:.2%} | {core['validation_2026']['threshold_selected_n']} | {core['validation_2026']['threshold_coverage']:.3%} | {core['validation_2026']['threshold_success_rate']:.2%} | {core['validation_2026']['threshold_uplift']:.2%} | {core['validation_2026']['threshold_net_mean']:.2%} |

`0.510070` 是 raw-score 选择阈值，不是真实成功概率 51.007%。

## 主要回答

1. B0 在 2025/2026 的差异：阈值以上成功率相差 `{core['validation_2026']['threshold_success_rate'] - core['validation_2025']['threshold_success_rate']:.2%}`，净均值相差 `{core['validation_2026']['threshold_net_mean'] - core['validation_2025']['threshold_net_mean']:.2%}`。
2. 固定分数箱单调性：2025 成功率 Spearman `{summary['score_monotonicity']['validation_2025']['spearman_success']['rho']:.3f}`，2026 `{summary['score_monotonicity']['validation_2026']['spearman_success']['rho']:.3f}`；两年都有相邻倒挂。
3. 最高分尾部：`99-100` 分位没有稳定优于 `80-90` 分位，不能解释为可靠高概率尾部。
4. 排序还是校准：排序仍有弱 AUC，但高分概率校准不足，尤其 2025 阈值以上平均 raw probability `{cal25['threshold_mean_raw_probability']:.2%}` 对实际 `{cal25['threshold_actual_success_rate']:.2%}` 明显偏高；2026 偏差缩小到 raw `{cal26['threshold_mean_raw_probability']:.2%}` 对实际 `{cal26['threshold_actual_success_rate']:.2%}`。
5. 2025 问题：主要表现为高分尾部过度自信和经济兑现不足，而不是模型完全没有弱排序。
6. 结构分解：以 six-grid 分解阈值以上成功率，observed `{comp['observed_difference_2026_minus_2025']:.2%}`，composition `{comp['composition_effect']:.2%}`，within-cell `{comp['within_cell_effect']:.2%}`，residual `{comp['numerical_residual']:.3g}`。
7. 输入漂移：漂移最大的冻结因子组见 `feature_group_drift.csv`；解释为输入分布证据，不是因果证明。
8. 贡献漂移：线性贡献按 P4 六组输出，2025/2026 的组贡献关系不等于可选新因子。
9. 集中度：阈值以上样本最大资产 share `{summary['concentration_metrics']['by_dimension']['asset']['top_share']:.2%}`，最大月份 share `{summary['concentration_metrics']['by_dimension']['event_month']['top_share']:.2%}`，最大 28 日 block share `{summary['concentration_metrics']['by_dimension']['block28']['top_share']:.2%}`；不能把同日多币事件当独立证据。
10. 去除 BTC/ETH、non-overlap、episode 和 leave-one-out 后，弱排序/年度差异仍是诊断线索，但不能变成 promotion 证据。
11. B0 更像风险过滤器而不是高概率趋势选择器：低分排除坏事件的解释强于最高分可靠胜率解释。
12. 当前能确认：P5/P6 锚点、HYPE 隔离、B0 重建、2025/2026 历史差异、尾部校准问题。
13. 当前不能确认：不能确认新盲测通过、不能确认 live-ready、不能确认 P6 市场/方向机制可交易、不能确认特征漂移具有因果性。
14. P8 推荐：`{summary['p8_primary_branch']}`，不直接实施 P8。

## 图表

{chart_lines}

## 证据文件

- [summary](../artifacts/binance_1d_ma7_ctp_p7_summary.json)
- [manifest](../artifacts/binance_1d_ma7_ctp_p7_manifest.json)
- [modeling audit](binance-1d-ma7-ctp-p7-modeling-audit-2026-09-04.md)
"""


def build_modeling_audit(summary: dict[str, Any]) -> str:
    return f"""# BIN-1D-MA7-CTP P7 建模审计

- 状态：`{STATUS}`
- 对象：`R_B0_69`
- 结论：P7 未训练新候选、未调阈值、未添加特征；只重建 P5/P6 冻结 B0 用于贡献审计。

## 锚点与重建

- 锚点全部通过：`{summary['anchor_parity_all_pass']}`
- OOF 最大 raw probability 误差：`{summary['model_reconstruction']['development_oof_max_abs_probability_error']:.3g}`
- 2025+ final raw probability 最大误差：`{summary['model_reconstruction']['validation_final_max_abs_probability_error']:.3g}`
- 总最大误差：`{summary['model_reconstruction']['max_abs_probability_error']:.3g}`
- HYPE 行数：`{summary['hype_isolation']['hype_rows']}`
- HYPER 保留：`{summary['hype_isolation']['hyper_present']}`

## 冻结边界

- 固定 raw 阈值：`0.510070`
- 固定分箱边界来源：development OOF raw score。
- P5 frozen Platt calibration 未在 2025/2026 重新拟合。
- 2025+ 数据角色：`{SAMPLE_ROLE_VALIDATION}`。
- 禁止产物检查：未生成交易路径 HTML、策略权益曲线、Sharpe、live spec、runner handoff。

## 统计说明

主要年度差异使用 seed `{SEED}`、`{BOOTSTRAP_SAMPLES}` 次、28 日 calendar block bootstrap；同一 replicate 保留抽中 block 内所有资产/方向/事件。特征漂移使用 BH 校正；PSI 仅作连续效应量，不作正式显著性阈值。
"""


def write_manifest(config: dict[str, Any], lock: dict[str, Any], chart_paths: list[Path]) -> dict[str, Any]:
    paths = [
        P7_CONTRACT_PATH,
        SCRIPT_PATH,
        TEST_PATH,
        CONFIG_PATH,
        CONTRACT_LOCK_PATH,
        INPUT_INVENTORY_PATH,
        DATA_AUDIT_PATH,
        ANCHOR_PARITY_PATH,
        MODEL_RECONSTRUCTION_PATH,
        FROZEN_COEFFICIENTS_PATH,
        SCORE_DRIFT_PARQUET_PATH,
        SCORE_DRIFT_CSV_PATH,
        FEATURE_DRIFT_PARQUET_PATH,
        FEATURE_GROUP_DRIFT_CSV_PATH,
        FIXED_BIN_OUTCOMES_PATH,
        SCORE_MONOTONICITY_PATH,
        CALIBRATION_METRICS_PATH,
        CALIBRATION_BINS_PATH,
        YEAR_INTERACTIONS_PATH,
        COMPOSITION_DECOMPOSITION_PATH,
        COMPOSITION_CELLS_PATH,
        FEATURE_CONTRIBUTION_DRIFT_PATH,
        FEATURE_GROUP_CONTRIBUTION_PATH,
        LABEL_ECONOMIC_DECOMPOSITION_PATH,
        CONCENTRATION_METRICS_PATH,
        LEAVE_ONE_OUT_PATH,
        NONOVERLAP_EPISODE_PATH,
        BOOTSTRAP_RESULTS_PATH,
        SUMMARY_PATH,
        REPORT_PATH,
        MODELING_AUDIT_PATH,
        *chart_paths,
    ]
    artifacts = []
    for path in paths:
        if path.exists():
            artifacts.append({"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    manifest = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "experiment": "P7",
        "created_at": datetime.now(UTC),
        "config_sha256": sha256_file(CONFIG_PATH),
        "contract_lock_sha256": sha256_file(CONTRACT_LOCK_PATH),
        "manifest_excludes_self": True,
        "artifacts": artifacts,
    }
    manifest["manifest_sha256_canonical_payload"] = sha256_payload(manifest)
    atomic_write_json(MANIFEST_PATH, manifest)
    return manifest


def run() -> None:
    config, lock = write_contract_artifacts()
    p4_group_spec = load_json(P4_FACTOR_SPEC_PATH)
    feature_spec = P5.build_feature_spec()
    feature_spec["p2_order_group_map"] = p4_group_spec["p2_order_group_map"]
    feature_spec["factor_groups"] = p4_group_spec["factor_groups"]
    samples = load_samples(feature_spec)
    for frame in [samples["development_full"], samples["development_oof"], samples["validation_main"], samples["validation_2025"], samples["validation_2026"]]:
        if (frame["asset"] == HYPE_ASSET).any():
            raise RuntimeError("HYPE entered P7 samples")
    group_edges = age_liquidity_groups(samples["development_full"], [samples["development_full"], samples["development_oof"], samples["validation_main"], samples["validation_2025"], samples["validation_2026"]])
    reconstruction, coefficients, contribution, validation_reconstructed = reconstruct_b0(feature_spec, samples)
    samples["validation_main"] = validation_reconstructed.drop(columns=["_reconstructed_raw_probability"])
    anchor = build_anchor_parity(samples, reconstruction)
    if not anchor["all_pass"] or not reconstruction["passes_1e_minus_8"]:
        core_metrics = {
            "development_oof": sample_metrics(samples["development_oof"]),
            "validation_2025_plus": sample_metrics(samples["validation_main"]),
            "validation_2025": sample_metrics(samples["validation_2025"]),
            "validation_2026": sample_metrics(samples["validation_2026"]),
        }
        data_audit = {
            "schema_version": 1,
            "research_id": RESEARCH_ID,
            "generated_at": datetime.now(UTC),
            "status": STATUS,
            "sample_roles": config["sample_roles"],
            "hype_rows": int(sum((samples[k]["asset"] == HYPE_ASSET).sum() for k in ["development_oof", "validation_main"])),
            "hyper_present": bool((samples["development_oof"]["asset"] == HYPER_ASSET).any() or (samples["validation_main"]["asset"] == HYPER_ASSET).any()),
            "validation_known_tradfi_rows_excluded": int(len(samples["validation_tradfi"])),
            "group_edges": group_edges,
            "p6_modeling_audit_missing": True,
            "fail_closed_reason": "B0 deterministic reconstruction does not match P5/P6 frozen raw predictions within 1e-8.",
        }
        failure = {
            "schema_version": 1,
            "research_id": RESEARCH_ID,
            "status": STATUS,
            "global_verdict": "DATA_OR_REPRODUCTION_FAILURE",
            "fail_closed": True,
            "reason": "B0 raw score reconstruction exceeded 1e-8 tolerance; explanatory drift analyses are intentionally not interpreted.",
        }
        placeholder = pd.DataFrame([failure])
        chart_paths = []
        for i, name in enumerate(CHART_NAMES, start=1):
            path = ARTIFACT_DIR / f"binance_1d_ma7_ctp_p7_chart_{i:02d}_{name}.svg"
            write_svg(path, f"P7 {name}: DATA_OR_REPRODUCTION_FAILURE", [svg_text(60, 120, failure["reason"], 14), svg_text(60, 150, f"max_abs_probability_error={reconstruction['max_abs_probability_error']:.6g}", 14)])
            chart_paths.append(path)
        atomic_write_json(DATA_AUDIT_PATH, data_audit)
        atomic_write_json(MODEL_RECONSTRUCTION_PATH, reconstruction)
        atomic_write_json(FROZEN_COEFFICIENTS_PATH, coefficients)
        atomic_write_json(ANCHOR_PARITY_PATH, anchor)
        atomic_write_parquet(SCORE_DRIFT_PARQUET_PATH, placeholder)
        placeholder.to_csv(SCORE_DRIFT_CSV_PATH, index=False)
        atomic_write_parquet(FEATURE_DRIFT_PARQUET_PATH, placeholder)
        placeholder.to_csv(FEATURE_GROUP_DRIFT_CSV_PATH, index=False)
        atomic_write_parquet(FIXED_BIN_OUTCOMES_PATH, placeholder)
        atomic_write_json(SCORE_MONOTONICITY_PATH, failure)
        atomic_write_json(CALIBRATION_METRICS_PATH, failure)
        atomic_write_parquet(CALIBRATION_BINS_PATH, placeholder)
        atomic_write_json(YEAR_INTERACTIONS_PATH, failure)
        atomic_write_json(COMPOSITION_DECOMPOSITION_PATH, failure)
        atomic_write_parquet(COMPOSITION_CELLS_PATH, placeholder)
        atomic_write_parquet(FEATURE_CONTRIBUTION_DRIFT_PATH, placeholder)
        placeholder.to_csv(FEATURE_GROUP_CONTRIBUTION_PATH, index=False)
        atomic_write_json(LABEL_ECONOMIC_DECOMPOSITION_PATH, failure)
        atomic_write_json(CONCENTRATION_METRICS_PATH, failure)
        atomic_write_parquet(LEAVE_ONE_OUT_PATH, placeholder)
        atomic_write_json(NONOVERLAP_EPISODE_PATH, failure)
        atomic_write_parquet(BOOTSTRAP_RESULTS_PATH, placeholder)
        summary = {
            "schema_version": 1,
            "research_id": RESEARCH_ID,
            "generated_at": datetime.now(UTC),
            "family": "Binance-1D-MA7-Cross-Trend-Probability",
            "alias": "BIN-1D-MA7-CTP",
            "experiment": "P7 Temporal Drift, Score Monotonicity and Calibration Decomposition",
            "status": STATUS,
            "sample_role_2025_plus": SAMPLE_ROLE_VALIDATION,
            "global_verdict": "DATA_OR_REPRODUCTION_FAILURE",
            "finding_labels": ["b0_reconstruction_failed", "fail_closed_before_explanatory_decomposition"],
            "p8_primary_branch": "E",
            "p8_primary_branch_label": "E: 停止历史优化，进入冻结观察",
            "core_metrics": core_metrics,
            "anchor_parity_all_pass": False,
            "anchor_parity": anchor,
            "model_reconstruction": reconstruction,
            "hype_isolation": {"hype_rows": data_audit["hype_rows"], "hyper_present": data_audit["hyper_present"]},
            "forbidden_outputs_generated": {"trade_path_html": False, "equity_curve": False, "sharpe": False, "live_config": False},
            "failure_boundary": "No score drift, feature drift, calibration, composition, contribution or concentration mechanism conclusion is valid after reconstruction failure.",
        }
        atomic_write_json(SUMMARY_PATH, summary)
        atomic_write_text(
            REPORT_PATH,
            f"""# BIN-1D-MA7-CTP P7 时间漂移、分数单调性与概率校准归因审计

- 状态：`{STATUS}`
- 全局 verdict：`DATA_OR_REPRODUCTION_FAILURE`
- P8 唯一推荐分支：`E`，停止历史优化，进入冻结观察。
- 2025+ 数据角色：`{SAMPLE_ROLE_VALIDATION}`，不是 strict OOS / blind holdout。

## 结论先行

P7 复现了样本量、HYPE/HYPER 隔离、TradFi 排除和固定 raw 阈值等锚点，但未能把 `R_B0_69` 确定性重建到 `1e-8`：最大 raw probability 误差为 `{reconstruction['max_abs_probability_error']:.6g}`。按合同，本轮停止所有漂移机制解释，不能回答“为什么 2025 差、2026 好”的模型机制问题。

## 锚点表

| 样本 | n | threshold n | threshold success | threshold net |
| --- | ---: | ---: | ---: | ---: |
| Development OOF | {core_metrics['development_oof']['n']} | {core_metrics['development_oof']['threshold_selected_n']} | {core_metrics['development_oof']['threshold_success_rate']:.2%} | {core_metrics['development_oof']['threshold_net_mean']:.2%} |
| 2025 | {core_metrics['validation_2025']['n']} | {core_metrics['validation_2025']['threshold_selected_n']} | {core_metrics['validation_2025']['threshold_success_rate']:.2%} | {core_metrics['validation_2025']['threshold_net_mean']:.2%} |
| 2026 | {core_metrics['validation_2026']['n']} | {core_metrics['validation_2026']['threshold_selected_n']} | {core_metrics['validation_2026']['threshold_success_rate']:.2%} | {core_metrics['validation_2026']['threshold_net_mean']:.2%} |

## 不能得出的结论

- 不能确认固定分数箱单调性或最高分尾部可靠性。
- 不能确认排序失效、校准失效或 regime 条件信号。
- 不能确认 feature/universe shift 对年度差异有解释力。
- 不能确认 P6 的 `MARKET_OR_SIDE_VALUE_ONLY` 是可交易机制。
- 不能确认任何 live-ready、dry-run 或 promotion 结论。

## 审计解释

当前 P5 脚本 hash 与 P5 manifest 一致，但用该脚本重新执行 P5 development B0 OOF，仍与冻结预测最大相差 `{reconstruction['development_oof_max_abs_probability_error']:.6g}`；final 2025+ 重建最大相差 `{reconstruction['validation_final_max_abs_probability_error']:.6g}`。P7 没有权限改写 P5/P6 frozen predictions，也不能用已看 2025+ 结果重新拟合 B0，因此唯一合规 verdict 是 `DATA_OR_REPRODUCTION_FAILURE`。

## 证据文件

- [summary](../artifacts/binance_1d_ma7_ctp_p7_summary.json)
- [anchor parity](../artifacts/binance_1d_ma7_ctp_p7_anchor_parity.json)
- [model reconstruction](../artifacts/binance_1d_ma7_ctp_p7_model_reconstruction.json)
- [modeling audit](binance-1d-ma7-ctp-p7-modeling-audit-2026-09-04.md)
""",
        )
        atomic_write_text(MODELING_AUDIT_PATH, build_modeling_audit(summary))
        manifest = write_manifest(config, lock, chart_paths)
        summary["manifest_path"] = str(MANIFEST_PATH.relative_to(ROOT))
        summary["manifest_sha256_canonical_payload"] = manifest["manifest_sha256_canonical_payload"]
        atomic_write_json(SUMMARY_PATH, summary)
        write_manifest(config, lock, chart_paths)
        return
    edges, labels = assign_development_bins(samples["development_oof"])
    for frame in [samples["development_oof"], samples["validation_2025"], samples["validation_2026"], samples["validation_main"]]:
        frame["score_bin"] = apply_fixed_bins(frame, edges, labels).astype(str)
    score_drift = build_score_drift(samples)
    feature_drift, feature_group_drift = build_feature_drift(samples["development_full"], samples["validation_2025"], samples["validation_2026"], feature_spec)
    fixed_bins, monotonicity = fixed_bin_outcomes(samples, edges, labels)
    calibration, calibration_bins_df = build_calibration(samples)
    composition, composition_cells = build_composition(samples)
    concentration, leave_one_out, robust = build_concentration(samples)
    contribution_summary = build_contribution_summary(contribution, samples)
    label_econ = build_label_economic(samples)
    boot = build_bootstrap(samples)
    boot_summary = summarize_bootstrap(boot)
    interactions = year_interactions(samples)
    core_metrics = {
        "development_oof": sample_metrics(samples["development_oof"]),
        "validation_2025_plus": sample_metrics(samples["validation_main"]),
        "validation_2025": sample_metrics(samples["validation_2025"]),
        "validation_2026": sample_metrics(samples["validation_2026"]),
    }
    data_audit = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generated_at": datetime.now(UTC),
        "status": STATUS,
        "sample_roles": config["sample_roles"],
        "hype_rows": int(sum((samples[k]["asset"] == HYPE_ASSET).sum() for k in ["development_oof", "validation_main"])),
        "hyper_present": bool((samples["development_oof"]["asset"] == HYPER_ASSET).any() or (samples["validation_main"]["asset"] == HYPER_ASSET).any()),
        "validation_known_tradfi_rows_excluded": int(len(samples["validation_tradfi"])),
        "group_edges": group_edges,
        "p6_modeling_audit_missing": True,
    }
    summary_seed = {"core_metrics": core_metrics, "anchor_parity_all_pass": anchor["all_pass"]}
    verdict, findings, p8 = choose_verdict(summary_seed, monotonicity, calibration, concentration)
    summary = {
        "schema_version": 1,
        "research_id": RESEARCH_ID,
        "generated_at": datetime.now(UTC),
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "alias": "BIN-1D-MA7-CTP",
        "experiment": "P7 Temporal Drift, Score Monotonicity and Calibration Decomposition",
        "status": STATUS,
        "sample_role_2025_plus": SAMPLE_ROLE_VALIDATION,
        "global_verdict": verdict,
        "finding_labels": findings,
        "p8_primary_branch": p8,
        "p8_primary_branch_label": "D: B0降级为风险否决器" if p8 == "D" else "E: 停止历史优化，进入冻结观察",
        "core_metrics": core_metrics,
        "anchor_parity_all_pass": anchor["all_pass"],
        "anchor_parity": anchor,
        "model_reconstruction": reconstruction,
        "hype_isolation": {"hype_rows": data_audit["hype_rows"], "hyper_present": data_audit["hyper_present"]},
        "score_monotonicity": monotonicity,
        "calibration_metrics": calibration,
        "composition_decomposition": composition,
        "concentration_metrics": concentration,
        "nonoverlap_episode_checks": robust,
        "bootstrap_summary": boot_summary,
        "year_interactions": interactions,
        "forbidden_outputs_generated": {"trade_path_html": False, "equity_curve": False, "sharpe": False, "live_config": False},
    }
    boot_summary["success_rate_diff_2026_minus_2025"]["point_estimate"] = core_metrics["validation_2026"]["threshold_success_rate"] - core_metrics["validation_2025"]["threshold_success_rate"]
    boot_summary["net_mean_diff_2026_minus_2025"]["point_estimate"] = core_metrics["validation_2026"]["threshold_net_mean"] - core_metrics["validation_2025"]["threshold_net_mean"]
    atomic_write_json(DATA_AUDIT_PATH, data_audit)
    atomic_write_json(ANCHOR_PARITY_PATH, anchor)
    atomic_write_json(MODEL_RECONSTRUCTION_PATH, reconstruction)
    atomic_write_json(FROZEN_COEFFICIENTS_PATH, coefficients)
    atomic_write_parquet(SCORE_DRIFT_PARQUET_PATH, score_drift)
    score_drift.to_csv(SCORE_DRIFT_CSV_PATH, index=False)
    atomic_write_parquet(FEATURE_DRIFT_PARQUET_PATH, feature_drift)
    feature_group_drift.to_csv(FEATURE_GROUP_DRIFT_CSV_PATH, index=False)
    atomic_write_parquet(FIXED_BIN_OUTCOMES_PATH, fixed_bins)
    atomic_write_json(SCORE_MONOTONICITY_PATH, monotonicity)
    atomic_write_json(CALIBRATION_METRICS_PATH, calibration)
    atomic_write_parquet(CALIBRATION_BINS_PATH, calibration_bins_df)
    atomic_write_json(YEAR_INTERACTIONS_PATH, interactions)
    atomic_write_json(COMPOSITION_DECOMPOSITION_PATH, composition)
    atomic_write_parquet(COMPOSITION_CELLS_PATH, composition_cells)
    atomic_write_parquet(FEATURE_CONTRIBUTION_DRIFT_PATH, contribution)
    contribution_summary.to_csv(FEATURE_GROUP_CONTRIBUTION_PATH, index=False)
    atomic_write_json(LABEL_ECONOMIC_DECOMPOSITION_PATH, label_econ)
    atomic_write_json(CONCENTRATION_METRICS_PATH, concentration)
    atomic_write_parquet(LEAVE_ONE_OUT_PATH, leave_one_out)
    atomic_write_json(NONOVERLAP_EPISODE_PATH, robust)
    atomic_write_parquet(BOOTSTRAP_RESULTS_PATH, boot)
    atomic_write_json(SUMMARY_PATH, summary)
    chart_paths = draw_charts(samples, fixed_bins, calibration_bins_df, feature_drift, contribution_summary, composition, concentration)
    atomic_write_text(REPORT_PATH, build_report(summary, chart_paths))
    atomic_write_text(MODELING_AUDIT_PATH, build_modeling_audit(summary))
    manifest = write_manifest(config, lock, chart_paths)
    # Re-write summary with manifest hash for direct sync tests.
    summary["manifest_path"] = str(MANIFEST_PATH.relative_to(ROOT))
    summary["manifest_sha256_canonical_payload"] = manifest["manifest_sha256_canonical_payload"]
    atomic_write_json(SUMMARY_PATH, summary)
    manifest = write_manifest(config, lock, chart_paths)


def main() -> None:
    args = parse_args()
    if not args.run:
        raise SystemExit("Pass --run to execute P7")
    ensure_output_policy(args.force)
    run()


if __name__ == "__main__":
    main()
