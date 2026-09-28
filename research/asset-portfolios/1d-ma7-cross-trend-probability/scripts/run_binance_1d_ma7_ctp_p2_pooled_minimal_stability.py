#!/usr/bin/env python3
"""Run BIN-1D-MA7-CTP P2 pooled-minimal MA7-cross stability audit.

P2 trains exactly one pooled direction-aligned event scorer on real MA7 crosses
strictly before 2025-01-01 UTC. It does not train long/short heads, does not
read HYPE, does not emit 2025+ predictions, and is not a strategy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", message="X does not have valid feature names")
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")

ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
CATL_DIR = ROOT / "research/asset-portfolios/1d-cross-asset-trend-lifecycle"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAGNOSTIC_DIR = FAMILY_DIR / "diagnostics"
SPEC_PATH = FAMILY_DIR / "specs/binance-1d-ma7-ctp-p2-pooled-minimal-stability-contract-2026-09-01.md"
FEATURE_SPEC_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_feature_spec.json"
P1_FEATURE_SPEC_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_feature_spec.json"
P1_MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_manifest.json"
P0R_FEATURE_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_feature_blocks.json"
P0R_MANIFEST_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_manifest.json"
PANEL_DIR = CATL_DIR / "artifacts/p0r_donor_directional_modeling_panel"
PANEL_GLOB = PANEL_DIR / "**/*.parquet"

CONTRACT_LOCK_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_contract_lock.json"
FOLD_METRICS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_fold_metrics.parquet"
OOF_PREDICTIONS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_oof_predictions.parquet"
DECILE_METRICS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_decile_metrics.parquet"
MODEL_CARD_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_model_card.json"
SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_summary.json"
MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_manifest.json"
REPORT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p2-pooled-minimal-stability-2026-09-01.md"
AUDIT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p2-modeling-audit-2026-09-01.md"
TEST_PATH = ROOT / "tests/test_binance_1d_ma7_ctp_p2_pooled_minimal_stability.py"

HYPE_ASSET = "HYPE/USDT:USDT"
HYPER_ASSET = "HYPER/USDT:USDT"
SEED = 20260901
CUTOFF = pd.Timestamp("2025-01-01T00:00:00Z")
STATUS = "explore / diagnostic-only / not promoted / not live-ready"
TARGET = "label_entry_success_20d"
LABEL_END = "label_end_ts_20d"
NET_RETURN = "label_entry_net_return"
HEAD = "POOLED_DIRECTION_ALIGNED"
BOOTSTRAP_SAMPLES = 1000
BOOTSTRAP_BLOCK_DAYS = 28

FOLDS = (
    ("D1", pd.Timestamp("2022-01-01T00:00:00Z"), pd.Timestamp("2023-01-01T00:00:00Z")),
    ("D2", pd.Timestamp("2023-01-01T00:00:00Z"), pd.Timestamp("2024-01-01T00:00:00Z")),
    ("D3", pd.Timestamp("2024-01-01T00:00:00Z"), CUTOFF),
)

LGBM_CANDIDATES: dict[str, dict[str, Any]] = {
    "T1": {"num_leaves": 7, "max_depth": 3, "min_data_in_leaf": 1000, "feature_fraction": 0.75, "lambda_l2": 10.0},
    "T2": {"num_leaves": 15, "max_depth": 4, "min_data_in_leaf": 2000, "feature_fraction": 0.75, "lambda_l2": 20.0},
}

COMMON_LGBM_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "metric": "auc",
    "learning_rate": 0.02,
    "n_estimators": 1000,
    "bagging_fraction": 1.0,
    "bagging_freq": 0,
    "random_state": SEED,
    "bagging_seed": SEED,
    "feature_fraction_seed": SEED,
    "data_random_seed": SEED,
    "deterministic": True,
    "force_col_wise": True,
    "n_jobs": 8,
    "verbosity": -1,
}

EXPECTED_PRE2025_EVENTS = 54137
EXPECTED_FINAL_TRAIN_ROWS = 52563


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return json_ready(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(json_ready(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    os.replace(temporary, path)


def output_paths() -> tuple[Path, ...]:
    return (
        CONTRACT_LOCK_PATH,
        FOLD_METRICS_PATH,
        OOF_PREDICTIONS_PATH,
        DECILE_METRICS_PATH,
        MODEL_CARD_PATH,
        SUMMARY_PATH,
        MANIFEST_PATH,
        REPORT_PATH,
        AUDIT_PATH,
    )


def ensure_output_policy(force: bool) -> None:
    existing = [path for path in output_paths() if path.exists()]
    if existing and not force:
        raise FileExistsError("P2 outputs already exist; pass --force to reproduce: " + ", ".join(str(p.relative_to(ROOT)) for p in existing))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def scheme_features(feature_spec: dict[str, Any], scheme: str) -> list[str]:
    names: list[str] = []
    for block in feature_spec["schemes"][scheme]:
        names.extend(feature_spec["feature_blocks"][block])
    if len(names) != len(set(names)):
        raise RuntimeError(f"{scheme} has duplicate features")
    return names


def t1_source_name(feature: str) -> str:
    if not feature.startswith("t1_"):
        raise ValueError(feature)
    return feature[3:]


def source_columns_for_features(feature_spec: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for feature in feature_spec["all_allowed_features"]:
        out.append(t1_source_name(feature) if feature.startswith("t1_") else feature)
    return sorted(set(out))


def asset_group(asset: str) -> int:
    return int(hashlib.sha256(asset.encode("utf-8")).hexdigest(), 16) % 5


def validate_feature_spec(feature_spec: dict[str, Any], p1_feature_spec: dict[str, Any]) -> None:
    if set(feature_spec["schemes"]) != {"F0_MA7_CORE", "F1_MA7_PATH"}:
        raise RuntimeError("P2 may only allow F0/F1")
    p2_allowed = set(feature_spec["all_allowed_features"])
    p1_f0 = set(scheme_features(p1_feature_spec, "F0_MA7_CORE"))
    p1_f1 = set(scheme_features(p1_feature_spec, "F1_MA7_PATH"))
    if set(scheme_features(feature_spec, "F0_MA7_CORE")) != p1_f0:
        raise RuntimeError("P2 F0 does not match P1 F0")
    if set(scheme_features(feature_spec, "F1_MA7_PATH")) != p1_f1:
        raise RuntimeError("P2 F1 does not match P1 F1")
    forbidden_tokens = feature_spec["forbidden_feature_patterns"]
    for feature in p2_allowed:
        lower = feature.lower()
        if any(token in lower for token in forbidden_tokens):
            if feature != "t1_volatility_state_p0r":
                raise RuntimeError(f"forbidden feature leaked into P2 X: {feature}")


def validate_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    feature_spec = load_json(FEATURE_SPEC_PATH)
    p1_feature_spec = load_json(P1_FEATURE_SPEC_PATH)
    p1_manifest = load_json(P1_MANIFEST_PATH)
    p0r_manifest = load_json(P0R_MANIFEST_PATH)
    validate_feature_spec(feature_spec, p1_feature_spec)

    p1_feature_sha = sha256_file(P1_FEATURE_SPEC_PATH)
    if p1_feature_sha != p1_manifest["input_lineage"]["feature_spec_sha256"]:
        raise RuntimeError("P1 feature spec sha256 does not match P1 manifest")
    if p1_feature_sha != feature_spec["source_feature_spec"]["sha256"]:
        raise RuntimeError("P2 source feature spec sha256 mismatch")

    checks: list[dict[str, Any]] = []
    panel_manifest_paths: list[str] = []
    for artifact in p0r_manifest["artifacts"]:
        rel = artifact["path"]
        path = ROOT / rel
        actual = sha256_file(path)
        checks.append({"path": rel, "expected_sha256": artifact["sha256"], "actual_sha256": actual, "match": actual == artifact["sha256"]})
        if rel.startswith("research/asset-portfolios/1d-cross-asset-trend-lifecycle/artifacts/p0r_donor_directional_modeling_panel/"):
            panel_manifest_paths.append(rel)

    panel_globbed = sorted(str(path.relative_to(ROOT)) for path in PANEL_DIR.glob("**/*.parquet"))
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    panel_path = str(PANEL_GLOB)
    row = con.execute(
        """
        SELECT
          count(*) FILTER (WHERE asset = ?) AS hype_all_rows,
          count(*) FILTER (WHERE asset = ?) AS hyper_all_rows,
          count(*) FILTER (WHERE ts >= TIMESTAMPTZ '2025-01-01 00:00:00+00:00') AS post_2025_rows_available,
          count(*) FILTER (WHERE ts < TIMESTAMPTZ '2025-01-01 00:00:00+00:00') AS pre_2025_rows_available
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        """,
        [HYPE_ASSET, HYPER_ASSET, panel_path],
    ).fetchone()
    audit = {
        "p0r_manifest_path": str(P0R_MANIFEST_PATH.relative_to(ROOT)),
        "p0r_manifest_sha256": sha256_file(P0R_MANIFEST_PATH),
        "p0r_feature_blocks_sha256": sha256_file(P0R_FEATURE_PATH),
        "p1_feature_spec_sha256": p1_feature_sha,
        "p0r_artifact_hash_checks": checks,
        "p0r_artifact_hashes_all_match": all(item["match"] for item in checks),
        "panel_file_set_matches_manifest": panel_globbed == sorted(panel_manifest_paths),
        "holdout_read": bool(p0r_manifest.get("holdout_read", True)),
        "hype_asset_excluded": p0r_manifest.get("hype_asset_excluded"),
        "panel_hype_rows": int(row[0]),
        "panel_hyper_rows": int(row[1]),
        "post_2025_rows_available_but_not_modeled": int(row[2]),
        "pre_2025_rows_available": int(row[3]),
        "post_2025_model_rows_read": 0,
        "hype_model_rows_read": 0,
    }
    if not audit["p0r_artifact_hashes_all_match"] or not audit["panel_file_set_matches_manifest"]:
        raise RuntimeError("P0R manifest hash or panel file-set mismatch")
    if audit["holdout_read"] is not False or audit["hype_asset_excluded"] != HYPE_ASSET:
        raise RuntimeError("P0R holdout/HYPE boundary mismatch")
    if audit["panel_hype_rows"] != 0 or audit["panel_hyper_rows"] <= 0:
        raise RuntimeError("HYPE contamination or HYPER missing")
    return feature_spec, audit


def count_events_without_labels() -> dict[str, Any]:
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    row = con.execute(
        """
        SELECT
          count(*) AS n,
          count(DISTINCT asset) AS assets,
          count(*) FILTER (WHERE side = 'long') AS long,
          count(*) FILTER (WHERE side = 'short') AS short,
          count(*) FILTER (WHERE asset = ?) AS hype,
          count(*) FILTER (WHERE asset = ?) AS hyper,
          min(ts) AS min_ts,
          max(ts) AS max_ts,
          count(*) FILTER (WHERE NOT probe_raw_ma7_cross_dir) AS non_cross,
          count(*) FILTER (WHERE NOT model_eligible_entry_p0r) AS ineligible,
          count(*) - count(DISTINCT asset || '|' || CAST(ts AS VARCHAR)) AS duplicate_asset_ts,
          count(*) FILTER (WHERE ts >= TIMESTAMPTZ '2025-01-01 00:00:00+00:00') AS post_2025_rows
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        WHERE probe_raw_ma7_cross_dir = true
          AND model_eligible_entry_p0r = true
          AND ts < TIMESTAMPTZ '2025-01-01 00:00:00+00:00'
        """,
        [HYPE_ASSET, HYPER_ASSET, str(PANEL_GLOB)],
    ).fetchone()
    audit = {
        "n": int(row[0]),
        "assets": int(row[1]),
        "long": int(row[2]),
        "short": int(row[3]),
        "hype": int(row[4]),
        "hyper": int(row[5]),
        "min_ts": pd.Timestamp(row[6]).isoformat(),
        "max_ts": pd.Timestamp(row[7]).isoformat(),
        "non_cross": int(row[8]),
        "ineligible": int(row[9]),
        "duplicate_asset_ts": int(row[10]),
        "post_2025_rows": int(row[11]),
        "labels_read": False,
    }
    if audit["n"] != EXPECTED_PRE2025_EVENTS or audit["hype"] != 0 or audit["non_cross"] != 0 or audit["duplicate_asset_ts"] != 0:
        raise RuntimeError(f"P2 event audit mismatch: {audit}")
    return audit


def load_event_panel(feature_spec: dict[str, Any]) -> pd.DataFrame:
    source_cols = source_columns_for_features(feature_spec)
    base_cols = [
        "asset",
        "side",
        "side_sign",
        "ts",
        "entry_ts",
        "probe_raw_ma7_cross_dir",
        "dir_raw_ma7_cross",
        "model_eligible_entry_p0r",
        TARGET,
        LABEL_END,
        NET_RETURN,
        "volatility_state_p0r",
        "listing_age_days",
        "liquidity_rank_pct_p0r",
    ]
    cols = sorted(set(base_cols + source_cols))
    select_sql = ", ".join(f'"{col}"' for col in cols)
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    raw = con.execute(
        f"""
        SELECT {select_sql}
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        WHERE ts < TIMESTAMPTZ '2025-01-01 00:00:00+00:00'
        ORDER BY asset, side, ts
        """,
        [str(PANEL_GLOB)],
    ).fetch_df()
    raw["ts"] = pd.to_datetime(raw["ts"], utc=True)
    raw[LABEL_END] = pd.to_datetime(raw[LABEL_END], utc=True)
    raw["entry_ts"] = pd.to_datetime(raw["entry_ts"], utc=True)

    raw = raw.sort_values(["asset", "side", "ts"]).copy()
    for feature in [f for f in feature_spec["all_allowed_features"] if f.startswith("t1_")]:
        raw[feature] = raw.groupby(["asset", "side"], sort=False)[t1_source_name(feature)].shift(1)

    events = raw.loc[
        raw["probe_raw_ma7_cross_dir"].eq(True)
        & raw["model_eligible_entry_p0r"].eq(True)
        & raw["ts"].lt(CUTOFF)
    ].copy()
    if events.empty:
        raise RuntimeError("no P2 events")
    if len(events) != EXPECTED_PRE2025_EVENTS:
        raise RuntimeError(f"expected {EXPECTED_PRE2025_EVENTS} P2 events, got {len(events)}")
    if events["asset"].eq(HYPE_ASSET).any():
        raise RuntimeError("HOLDOUT_CONTAMINATED")
    if events["ts"].ge(CUTOFF).any():
        raise RuntimeError("P2 loaded post-2025 modeling row")
    if not events["probe_raw_ma7_cross_dir"].all() or not events["dir_raw_ma7_cross"].eq(1).all():
        raise RuntimeError("OBJECTIVE_MISALIGNED")
    if events.duplicated(["asset", "ts"]).any():
        raise RuntimeError("asset+ts duplicate directional cross")
    if set(events["side"].unique()) - {"long", "short"}:
        raise RuntimeError("unknown side")

    events["asset_group"] = events["asset"].map(asset_group).astype("int8")
    events["event_year"] = events["ts"].dt.year.astype("int16")
    assert_t1_is_prior_day(raw, events, feature_spec)
    return events.reset_index(drop=True)


def assert_t1_is_prior_day(raw: pd.DataFrame, events: pd.DataFrame, feature_spec: dict[str, Any]) -> None:
    sample_features = [
        "t1_dir_ma7_slope_1d_atr",
        "t1_dir_close_ma7_dist_atr",
        "t1_dir_ret_30d",
        "t1_volatility_state_p0r",
    ]
    raw_key = raw[["asset", "side", "ts"] + [t1_source_name(f) for f in sample_features]].sort_values(["asset", "side", "ts"]).copy()
    for feature in sample_features:
        raw_key[f"check_{feature}"] = raw_key.groupby(["asset", "side"], sort=False)[t1_source_name(feature)].shift(1)
    merged = events[["asset", "side", "ts"] + sample_features].merge(
        raw_key[["asset", "side", "ts"] + [f"check_{f}" for f in sample_features]],
        on=["asset", "side", "ts"],
        how="left",
    )
    for feature in sample_features:
        expected = merged[f"check_{feature}"]
        actual = merged[feature]
        if pd.api.types.is_numeric_dtype(actual):
            comparable = actual.notna() & expected.notna()
            if comparable.any() and not np.allclose(actual[comparable].astype(float), expected[comparable].astype(float), atol=1e-8, rtol=1e-8):
                raise RuntimeError(f"T1 lag mismatch for {feature}")
        else:
            comparable = actual.notna() & expected.notna()
            if comparable.any() and not actual[comparable].astype(str).eq(expected[comparable].astype(str)).all():
                raise RuntimeError(f"T1 lag mismatch for {feature}")


@dataclass
class TabularPreprocessor:
    features: list[str]
    categorical: list[str]
    medians: dict[str, float] | None = None
    categories: dict[str, list[str]] | None = None
    output_features: list[str] | None = None

    def fit(self, frame: pd.DataFrame) -> "TabularPreprocessor":
        numeric = [f for f in self.features if f not in self.categorical]
        medians: dict[str, float] = {}
        for feature in numeric:
            values = pd.to_numeric(frame[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
            median = float(values.median()) if values.notna().any() else 0.0
            medians[feature] = median if math.isfinite(median) else 0.0
        categories = {
            feature: sorted(frame[feature].dropna().astype(str).unique().tolist())
            for feature in self.categorical
            if feature in self.features
        }
        out = numeric[:]
        for feature, levels in categories.items():
            out.extend([f"{feature}__{level}" for level in levels])
        self.medians = medians
        self.categories = categories
        self.output_features = out
        return self

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        if self.medians is None or self.categories is None or self.output_features is None:
            raise RuntimeError("preprocessor is not fitted")
        parts: list[np.ndarray] = []
        for feature, median in self.medians.items():
            values = pd.to_numeric(frame[feature], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(median).astype(float)
            parts.append(values.to_numpy()[:, None])
        for feature, levels in self.categories.items():
            values = frame[feature].astype(str).fillna("__NA__")
            for level in levels:
                parts.append(values.eq(level).astype(float).to_numpy()[:, None])
        if not parts:
            return np.zeros((len(frame), 0), dtype=float)
        return np.hstack(parts)


def fold_split(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = frame.loc[frame["ts"].lt(start) & frame[LABEL_END].lt(start)].copy()
    validation = frame.loc[frame["ts"].ge(start) & frame["ts"].lt(end)].copy()
    if not train.empty and not train[LABEL_END].max() < start:
        raise RuntimeError("purge failed")
    if validation["ts"].ge(CUTOFF).any() or train["ts"].ge(CUTOFF).any():
        raise RuntimeError("post-2025 row entered P2 split")
    return train, validation


def clip_probability(probability: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(probability, dtype=float), 1e-6, 1 - 1e-6)


def calibration_shape(y: np.ndarray, probability: np.ndarray) -> tuple[float | None, float | None]:
    y = np.asarray(y, dtype=int)
    p = clip_probability(probability)
    if len(np.unique(y)) < 2:
        return None, None
    x = np.log(p / (1 - p)).reshape(-1, 1)
    model = LogisticRegression(solver="lbfgs", max_iter=1000)
    model.fit(x, y)
    return float(model.intercept_[0]), float(model.coef_[0, 0])


def ece_10(y: np.ndarray, probability: np.ndarray) -> float | None:
    if len(y) == 0:
        return None
    frame = pd.DataFrame({"y": np.asarray(y, dtype=float), "p": clip_probability(probability)})
    frame["bin"] = pd.cut(frame["p"], bins=np.linspace(0, 1, 11), include_lowest=True, labels=False)
    total = len(frame)
    value = 0.0
    for _, group in frame.groupby("bin", observed=True):
        value += len(group) / total * abs(float(group["y"].mean()) - float(group["p"].mean()))
    return float(value)


def decile_codes(probability: np.ndarray) -> np.ndarray:
    ranks = pd.Series(probability).rank(method="first")
    return np.ceil(ranks / len(ranks) * 10).clip(1, 10).astype(int).to_numpy()


def metric_values(frame: pd.DataFrame, probability: np.ndarray) -> dict[str, Any]:
    y = frame[TARGET].astype(int).to_numpy()
    p = clip_probability(probability)
    if len(np.unique(y)) >= 2:
        auc = float(roc_auc_score(y, p))
        pr_auc = float(average_precision_score(y, p))
    else:
        auc = None
        pr_auc = None
    const = np.full(len(y), float(np.mean(y)))
    intercept, slope = calibration_shape(y, p)
    decile = decile_codes(p)
    top = y[decile == 10]
    bottom = y[decile == 1]
    weights = asset_balanced_weights(frame)
    return {
        "eval_n": int(len(frame)),
        "asset_count": int(frame["asset"].nunique()),
        "date_min": frame["ts"].min(),
        "date_max": frame["ts"].max(),
        "positive_rate": float(np.mean(y)),
        "pr_baseline": float(np.mean(y)),
        "roc_auc": auc,
        "pr_auc": pr_auc,
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "brier": float(brier_score_loss(y, p)),
        "brier_const": float(brier_score_loss(y, const)),
        "brier_skill_vs_const": float(1 - brier_score_loss(y, p) / brier_score_loss(y, const)) if brier_score_loss(y, const) > 0 else None,
        "calibration_intercept": intercept,
        "calibration_slope": slope,
        "ece_10": ece_10(y, p),
        "top_decile_success_rate": float(np.mean(top)) if len(top) else None,
        "top_decile_uplift": float(np.mean(top) - np.mean(y)) if len(top) else None,
        "bottom_decile_success_rate": float(np.mean(bottom)) if len(bottom) else None,
        "top_bottom_success_rate_diff": float(np.mean(top) - np.mean(bottom)) if len(top) and len(bottom) else None,
        "asset_balanced_auc": float(roc_auc_score(y, p, sample_weight=weights)) if len(np.unique(y)) >= 2 else None,
        "asset_balanced_brier": float(np.average((p - y) ** 2, weights=weights)),
    }


def asset_balanced_weights(frame: pd.DataFrame) -> np.ndarray:
    counts = frame.groupby("asset")["asset"].transform("count").astype(float)
    weights = 1.0 / counts
    return (weights / weights.mean()).to_numpy()


def metric_row(
    *,
    model_id: str,
    feature_scheme: str,
    fold: str,
    split: str,
    train_n: int,
    train_label_end_max: pd.Timestamp | None,
    frame: pd.DataFrame,
    probability: np.ndarray,
    train_val_auc_gap: float | None = None,
    train_val_top_uplift_gap: float | None = None,
    overfit_flag: str = "",
    evaluation: str = "development",
    stratum_type: str = "all",
    stratum_value: str = "all",
) -> dict[str, Any]:
    values = metric_values(frame, probability)
    values.update(
        {
            "head": HEAD,
            "row_type": "metric",
            "evaluation": evaluation,
            "fold": fold,
            "split": split,
            "model_id": model_id,
            "feature_scheme": feature_scheme,
            "stratum_type": stratum_type,
            "stratum_value": stratum_value,
            "train_n": int(train_n),
            "train_label_end_max": train_label_end_max,
            "train_val_auc_gap": train_val_auc_gap,
            "train_val_top_uplift_gap": train_val_top_uplift_gap,
            "overfit_flag": overfit_flag,
        }
    )
    return values


def decile_rows(frame: pd.DataFrame, probability: np.ndarray, *, model_id: str, evaluation: str) -> list[dict[str, Any]]:
    y = frame[TARGET].astype(int).to_numpy()
    p = clip_probability(probability)
    decile = decile_codes(p)
    base = float(np.mean(y))
    rows: list[dict[str, Any]] = []
    for code in range(1, 11):
        mask = decile == code
        group = frame.loc[mask]
        yy = y[mask]
        rows.append(
            {
                "head": HEAD,
                "row_type": "decile",
                "evaluation": evaluation,
                "model_id": model_id,
                "decile": code,
                "n": int(mask.sum()),
                "success_rate": float(np.mean(yy)) if len(yy) else None,
                "uplift": float(np.mean(yy) - base) if len(yy) else None,
                "net_return_mean": float(group[NET_RETURN].mean()) if len(group) else None,
                "net_return_median": float(group[NET_RETURN].median()) if len(group) else None,
            }
        )
    return rows


def fit_logit(train: pd.DataFrame, valid: pd.DataFrame, features: list[str], categorical: list[str]) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    prep = TabularPreprocessor(features, [c for c in categorical if c in features]).fit(train)
    x_train = prep.transform(train)
    x_valid = prep.transform(valid)
    scaler = StandardScaler()
    x_train_s = scaler.fit_transform(x_train)
    x_valid_s = scaler.transform(x_valid)
    model = LogisticRegression(max_iter=1000, solver="lbfgs", random_state=SEED)
    model.fit(x_train_s, train[TARGET].astype(int).to_numpy())
    return (
        model.predict_proba(x_train_s)[:, 1],
        model.predict_proba(x_valid_s)[:, 1],
        {"preprocessor": prep, "scaler": scaler, "model": model, "features": features},
    )


def fit_lgbm(
    train: pd.DataFrame,
    valid: pd.DataFrame,
    features: list[str],
    categorical: list[str],
    candidate_id: str,
    rounds: int | None = None,
) -> tuple[np.ndarray, np.ndarray, int, dict[str, Any]]:
    prep = TabularPreprocessor(features, [c for c in categorical if c in features]).fit(train)
    x_train = prep.transform(train)
    x_valid = prep.transform(valid)
    params = {**COMMON_LGBM_PARAMS, **LGBM_CANDIDATES[candidate_id]}
    if rounds is not None:
        params["n_estimators"] = int(rounds)
    model = lgb.LGBMClassifier(**params)
    callbacks = [] if rounds is not None else [lgb.early_stopping(100, verbose=False)]
    model.fit(
        x_train,
        train[TARGET].astype(int).to_numpy(),
        eval_set=[(x_valid, valid[TARGET].astype(int).to_numpy())],
        eval_metric="auc",
        callbacks=callbacks,
    )
    best_iter = int(getattr(model, "best_iteration_", None) or params["n_estimators"])
    return (
        model.predict_proba(x_train)[:, 1],
        model.predict_proba(x_valid)[:, 1],
        best_iter,
        {"preprocessor": prep, "model": model, "features": features, "best_iteration": best_iter},
    )


def fit_candidate(
    model_id: str,
    train: pd.DataFrame,
    valid: pd.DataFrame,
    feature_sets: dict[str, list[str]],
    categorical: list[str],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    if model_id == "CONST_PRIOR":
        prior = float(train[TARGET].mean())
        return np.full(len(train), prior), np.full(len(valid), prior), {"prior": prior}
    if model_id == "SLOPE_ONLY_LOGIT":
        p_train, p_valid, detail = fit_logit(train, valid, feature_sets["SLOPE_ONLY"], categorical)
        return p_train, p_valid, detail
    if model_id in {"F0_LOGIT", "F1_LOGIT"}:
        scheme = "F0_MA7_CORE" if model_id.startswith("F0") else "F1_MA7_PATH"
        p_train, p_valid, detail = fit_logit(train, valid, feature_sets[scheme], categorical)
        return p_train, p_valid, detail
    scheme, lgbm_id = model_id.split("_")
    feature_scheme = "F0_MA7_CORE" if scheme == "F0" else "F1_MA7_PATH"
    p_train, p_valid, best_iter, detail = fit_lgbm(train, valid, feature_sets[feature_scheme], categorical, lgbm_id)
    detail["best_iteration"] = best_iter
    return p_train, p_valid, detail


def model_feature_scheme(model_id: str) -> str:
    if model_id == "CONST_PRIOR":
        return "NONE"
    if model_id == "SLOPE_ONLY_LOGIT":
        return "SLOPE_ONLY"
    if model_id.startswith("F0"):
        return "F0_MA7_CORE"
    if model_id.startswith("F1"):
        return "F1_MA7_PATH"
    raise ValueError(model_id)


def model_complexity(model_id: str) -> int:
    if model_id == "CONST_PRIOR":
        return 0
    if model_id == "SLOPE_ONLY_LOGIT":
        return 1
    if model_id == "F0_LOGIT":
        return 2
    if model_id == "F1_LOGIT":
        return 3
    if model_id == "F0_T1":
        return 4
    if model_id == "F0_T2":
        return 5
    if model_id == "F1_T1":
        return 6
    if model_id == "F1_T2":
        return 7
    return 99


def select_model(candidate_summary: dict[str, dict[str, Any]]) -> str:
    ranked = sorted(
        candidate_summary,
        key=lambda m: (
            candidate_summary[m]["worst_fold_auc"] if candidate_summary[m]["worst_fold_auc"] is not None else -1,
            candidate_summary[m]["macro_auc"] if candidate_summary[m]["macro_auc"] is not None else -1,
            -(candidate_summary[m]["macro_brier"] if candidate_summary[m]["macro_brier"] is not None else 9),
            -(candidate_summary[m]["macro_log_loss"] if candidate_summary[m]["macro_log_loss"] is not None else 9),
            -model_complexity(m),
        ),
        reverse=True,
    )
    best = ranked[0]
    best_stats = candidate_summary[best]
    for model_id in sorted(candidate_summary, key=model_complexity):
        if model_id == best:
            return best
        stats = candidate_summary[model_id]
        if best_stats["worst_fold_auc"] - stats["worst_fold_auc"] < 0.005 and best_stats["macro_auc"] - stats["macro_auc"] < 0.005:
            return model_id
    return best


def fit_platt(raw: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    raw = clip_probability(raw)
    y = np.asarray(y, dtype=int)
    base = {"method": "raw", "raw_brier": float(brier_score_loss(y, raw)), "raw_log_loss": float(log_loss(y, raw, labels=[0, 1]))}
    if len(np.unique(y)) < 2:
        return base
    x = np.log(raw / (1 - raw)).reshape(-1, 1)
    model = LogisticRegression(solver="lbfgs", max_iter=1000)
    model.fit(x, y)
    calibrated = clip_probability(model.predict_proba(x)[:, 1])
    cal_brier = float(brier_score_loss(y, calibrated))
    cal_ll = float(log_loss(y, calibrated, labels=[0, 1]))
    if cal_brier < base["raw_brier"] or cal_ll < base["raw_log_loss"]:
        return {
            **base,
            "method": "platt",
            "intercept": float(model.intercept_[0]),
            "slope": float(model.coef_[0, 0]),
            "calibrated_brier": cal_brier,
            "calibrated_log_loss": cal_ll,
        }
    return {**base, "calibrated_brier": cal_brier, "calibrated_log_loss": cal_ll}


def apply_calibration(probability: np.ndarray, calibration: dict[str, Any]) -> np.ndarray:
    probability = clip_probability(probability)
    if calibration.get("method") != "platt":
        return probability
    logit = np.log(probability / (1 - probability))
    z = calibration["intercept"] + calibration["slope"] * logit
    return clip_probability(1 / (1 + np.exp(-z)))


def forward_oof_calibration(
    oof: pd.DataFrame,
    raw_col: str,
) -> tuple[np.ndarray, dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Cross-fit calibration through time, then fit the frozen future calibrator.

    D1 stays raw because no earlier OOF predictions exist. D2 is calibrated only
    from completed D1 labels, and D3 only from completed D1-D2 labels. The final
    calibrator is selected by the forward D2-D3 comparison and then fitted on all
    OOF rows whose 20-day label is complete before the P2 cutoff.
    """

    raw = clip_probability(oof[raw_col].to_numpy())
    forward = raw.copy()
    audits: list[dict[str, Any]] = []
    fold_names = [fold for fold, _, _ in FOLDS]

    for fold_index, (fold, start, _) in enumerate(FOLDS):
        eval_mask = oof["fold"].eq(fold).to_numpy()
        if fold_index == 0:
            audits.append(
                {
                    "evaluation_fold": fold,
                    "calibration_train_folds": [],
                    "calibration_train_rows": 0,
                    "calibration_train_label_end_max": None,
                    "evaluation_start": start,
                    "method": "raw_no_prior_oof",
                    "temporal_isolation_pass": True,
                }
            )
            continue

        prior_folds = fold_names[:fold_index]
        fit_mask = oof["fold"].isin(prior_folds) & oof[LABEL_END].lt(start)
        fit_frame = oof.loc[fit_mask]
        if fit_frame.empty:
            raise RuntimeError(f"no prior completed OOF labels available to calibrate {fold}")
        calibration = fit_platt(
            fit_frame[raw_col].to_numpy(),
            fit_frame[TARGET].astype(int).to_numpy(),
        )
        forward[eval_mask] = apply_calibration(raw[eval_mask], calibration)
        max_label_end = fit_frame[LABEL_END].max()
        audits.append(
            {
                "evaluation_fold": fold,
                "calibration_train_folds": prior_folds,
                "calibration_train_rows": int(len(fit_frame)),
                "calibration_train_label_end_max": max_label_end,
                "evaluation_start": start,
                "method": calibration["method"],
                "temporal_isolation_pass": bool(max_label_end < start),
            }
        )

    forward_eval_mask = oof["fold"].isin(fold_names[1:]).to_numpy()
    forward_frame = oof.loc[forward_eval_mask]
    raw_metrics = metric_values(forward_frame, raw[forward_eval_mask])
    calibrated_metrics = metric_values(forward_frame, forward[forward_eval_mask])
    forward_improved = bool(
        calibrated_metrics["brier"] < raw_metrics["brier"]
        or calibrated_metrics["log_loss"] < raw_metrics["log_loss"]
    )

    final_fit_mask = oof[LABEL_END].lt(CUTOFF).to_numpy()
    final_fit_frame = oof.loc[final_fit_mask]
    final_candidate = fit_platt(
        final_fit_frame[raw_col].to_numpy(),
        final_fit_frame[TARGET].astype(int).to_numpy(),
    )
    if forward_improved and final_candidate["method"] == "platt":
        final_calibration = {
            **final_candidate,
            "selection_basis": "forward_oof_D2_D3",
            "forward_eval_rows": int(forward_eval_mask.sum()),
            "forward_raw_brier": raw_metrics["brier"],
            "forward_calibrated_brier": calibrated_metrics["brier"],
            "forward_raw_log_loss": raw_metrics["log_loss"],
            "forward_calibrated_log_loss": calibrated_metrics["log_loss"],
            "final_fit_rows": int(final_fit_mask.sum()),
            "final_fit_label_end_max": final_fit_frame[LABEL_END].max(),
            "fit_scope": "completed_D1_D3_oof_before_2025_cutoff",
        }
        selected_forward = forward
    else:
        final_calibration = {
            "method": "raw",
            "selection_basis": "forward_oof_D2_D3",
            "forward_eval_rows": int(forward_eval_mask.sum()),
            "forward_raw_brier": raw_metrics["brier"],
            "forward_calibrated_brier": calibrated_metrics["brier"],
            "forward_raw_log_loss": raw_metrics["log_loss"],
            "forward_calibrated_log_loss": calibrated_metrics["log_loss"],
            "final_fit_rows": int(final_fit_mask.sum()),
            "final_fit_label_end_max": final_fit_frame[LABEL_END].max(),
            "fit_scope": "completed_D1_D3_oof_before_2025_cutoff",
        }
        selected_forward = raw

    comparison = {
        "evaluation_folds": fold_names[1:],
        "eval_rows": int(forward_eval_mask.sum()),
        "raw": raw_metrics,
        "forward_calibrated": calibrated_metrics,
        "improved_brier_or_log_loss": forward_improved,
        "d1_probability_policy": "raw_no_prior_oof",
    }
    return selected_forward, final_calibration, audits, comparison


def run_development(frame: pd.DataFrame, feature_spec: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    feature_sets = {
        "SLOPE_ONLY": feature_spec["slope_only_features"],
        "F0_MA7_CORE": scheme_features(feature_spec, "F0_MA7_CORE"),
        "F1_MA7_PATH": scheme_features(feature_spec, "F1_MA7_PATH"),
    }
    categorical = feature_spec["categorical_features"]
    candidate_ids = ["CONST_PRIOR", "SLOPE_ONLY_LOGIT", "F0_LOGIT", "F1_LOGIT", "F0_T1", "F0_T2", "F1_T1", "F1_T2"]

    oof_rows: list[pd.DataFrame] = []
    metric_rows: list[dict[str, Any]] = []
    best_iterations: dict[str, list[int]] = {m: [] for m in candidate_ids}
    purge_audit: list[dict[str, Any]] = []

    for fold, start, end in FOLDS:
        train, valid = fold_split(frame, start, end)
        print(f"P2 {fold}: train={len(train)} valid={len(valid)}", flush=True)
        base = valid[["asset", "side", "ts", TARGET, LABEL_END, NET_RETURN, "asset_group", "event_year", "volatility_state_p0r", "listing_age_days", "liquidity_rank_pct_p0r"]].copy()
        base["fold"] = fold
        base["p_const_prior_raw"] = np.nan
        for model_id in candidate_ids:
            p_train, p_valid, detail = fit_candidate(model_id, train, valid, feature_sets, categorical)
            col = f"p_{model_id.lower()}_raw"
            base[col] = p_valid
            if "best_iteration" in detail:
                best_iterations[model_id].append(int(detail["best_iteration"]))

            train_metric = metric_values(train, p_train)
            valid_metric = metric_values(valid, p_valid)
            gap = None if train_metric["roc_auc"] is None or valid_metric["roc_auc"] is None else train_metric["roc_auc"] - valid_metric["roc_auc"]
            uplift_gap = None
            if train_metric["top_decile_uplift"] is not None and valid_metric["top_decile_uplift"] is not None:
                uplift_gap = train_metric["top_decile_uplift"] - valid_metric["top_decile_uplift"]
            flag = "SEVERE_OVERFIT_WARNING" if gap is not None and gap > 0.10 else ""
            metric_rows.append(metric_row(model_id=model_id, feature_scheme=model_feature_scheme(model_id), fold=fold, split="training", train_n=len(train), train_label_end_max=train[LABEL_END].max(), frame=train, probability=p_train, train_val_auc_gap=gap, train_val_top_uplift_gap=uplift_gap, overfit_flag=flag))
            metric_rows.append(metric_row(model_id=model_id, feature_scheme=model_feature_scheme(model_id), fold=fold, split="validation", train_n=len(train), train_label_end_max=train[LABEL_END].max(), frame=valid, probability=p_valid, train_val_auc_gap=gap, train_val_top_uplift_gap=uplift_gap, overfit_flag=flag))

        oof_rows.append(base)
        purge_audit.append({"fold": fold, "train_n": len(train), "validation_n": len(valid), "train_label_end_max": train[LABEL_END].max(), "validation_start": start, "purge_pass": bool(train[LABEL_END].max() < start)})

    oof = pd.concat(oof_rows, ignore_index=True)
    if oof["ts"].ge(CUTOFF).any() or oof["asset"].eq(HYPE_ASSET).any():
        raise RuntimeError("P2 OOF contamination")
    if oof.duplicated(["asset", "ts", "side"]).any():
        raise RuntimeError("OOF duplicate")

    metric_df = pd.DataFrame(metric_rows)
    candidate_summary: dict[str, dict[str, Any]] = {}
    for model_id in candidate_ids:
        vals = metric_df.loc[(metric_df["model_id"].eq(model_id)) & (metric_df["split"].eq("validation"))].copy()
        candidate_summary[model_id] = {
            "worst_fold_auc": float(vals["roc_auc"].min()),
            "macro_auc": float(vals["roc_auc"].mean()),
            "macro_brier": float(vals["brier"].mean()),
            "macro_log_loss": float(vals["log_loss"].mean()),
            "fold_auc": [float(x) for x in vals.sort_values("fold")["roc_auc"].tolist()],
            "median_best_iteration": int(np.median(best_iterations[model_id])) if best_iterations[model_id] else None,
        }
    selected = select_model(candidate_summary)

    calibration_audit: dict[str, list[dict[str, Any]]] = {}
    calibration_comparison: dict[str, dict[str, Any]] = {}
    for model_id in candidate_ids:
        raw_col = f"p_{model_id.lower()}_raw"
        calibrated, final_calibration, audit, comparison = forward_oof_calibration(oof, raw_col)
        cal_col = f"p_{model_id.lower()}_calibrated_forward"
        oof[cal_col] = calibrated
        candidate_summary[model_id]["calibration"] = final_calibration
        candidate_summary[model_id]["calibration_validation"] = comparison
        candidate_summary[model_id]["oof_raw"] = metric_values(oof, oof[raw_col].to_numpy())
        candidate_summary[model_id]["oof_selected_probability"] = metric_values(oof, oof[cal_col].to_numpy())
        calibration_audit[model_id] = audit
        calibration_comparison[model_id] = comparison

    selected_raw_col = f"p_{selected.lower()}_raw"
    selected_calibrated_col = f"p_{selected.lower()}_calibrated_forward"
    # Ranking gates remain on untouched raw OOF scores. Forward-calibrated
    # probabilities are reported separately and feed only the frozen future
    # probability layer.
    oof["p_selected"] = oof[selected_raw_col]
    oof["p_selected_calibrated_forward"] = oof[selected_calibrated_col]
    oof["selected_model_id"] = selected
    f0_ref = select_model({k: v for k, v in candidate_summary.items() if k.startswith("F0")})
    f1_ref = select_model({k: v for k, v in candidate_summary.items() if k.startswith("F1")})
    oof["p_f0_reference"] = oof[f"p_{f0_ref.lower()}_raw"]
    oof["p_f1_reference"] = oof[f"p_{f1_ref.lower()}_raw"]
    oof["p_slope_only"] = oof["p_slope_only_logit_raw"]
    oof["p_const_prior"] = oof["p_const_prior_raw"]

    development = {
        "candidate_summary": candidate_summary,
        "selected_model_id": selected,
        "selected_feature_scheme": model_feature_scheme(selected),
        "f0_reference_model_id": f0_ref,
        "f1_reference_model_id": f1_ref,
        "selected_rounds": candidate_summary[selected]["median_best_iteration"],
        "purge_audit": purge_audit,
        "calibration_audit": calibration_audit,
        "calibration_comparison": calibration_comparison,
        "selection_rows": int(len(oof)),
        "selection_data_max_ts": oof["ts"].max(),
        "historical_2025_plus_rows_used_for_selection": 0,
        "hype_rows_used_for_selection": 0,
        "one_pooled_model_only": True,
    }
    return metric_df, oof, development


def non_overlap_sample(frame: pd.DataFrame, spacing_days: int = 20) -> pd.DataFrame:
    rows: list[int] = []
    for _, group in frame.sort_values(["asset", "side", "ts"]).groupby(["asset", "side"], sort=False):
        last: pd.Timestamp | None = None
        for idx, row in group.iterrows():
            ts = row["ts"]
            if last is None or (ts - last).days >= spacing_days:
                rows.append(idx)
                last = ts
    return frame.loc[rows].sort_values("ts")


def bootstrap_ci(values: list[float]) -> dict[str, float | None]:
    clean = np.asarray([v for v in values if v is not None and math.isfinite(v)], dtype=float)
    if clean.size == 0:
        return {"ci95_low": None, "ci95_high": None}
    return {"ci95_low": float(np.quantile(clean, 0.025)), "ci95_high": float(np.quantile(clean, 0.975))}


def paired_block_bootstrap(frame: pd.DataFrame, selected_col: str, f0_col: str, f1_col: str) -> dict[str, Any]:
    tmp = frame.copy()
    block0 = tmp["ts"].min().normalize()
    tmp["block_id"] = ((tmp["ts"].dt.normalize() - block0).dt.days // BOOTSTRAP_BLOCK_DAYS).astype(int)
    blocks = sorted(tmp["block_id"].unique())
    groups = {block: tmp.index[tmp["block_id"].eq(block)].to_numpy() for block in blocks}
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, len(blocks), size=(BOOTSTRAP_SAMPLES, len(blocks)))
    aucs: list[float] = []
    top_success_rates: list[float] = []
    top_uplifts: list[float] = []
    brier_skills: list[float] = []
    f1_minus_f0: list[float] = []
    slope_diff: list[float] = []
    for draw in draws:
        idx = np.concatenate([groups[blocks[i]] for i in draw])
        sample = tmp.loc[idx]
        y = sample[TARGET].astype(int).to_numpy()
        if len(np.unique(y)) < 2:
            continue
        p = sample[selected_col].to_numpy()
        p0 = sample[f0_col].to_numpy()
        p1 = sample[f1_col].to_numpy()
        ps = sample["p_slope_only"].to_numpy()
        const = np.full(len(y), float(np.mean(y)))
        aucs.append(float(roc_auc_score(y, p)))
        f1_minus_f0.append(float(roc_auc_score(y, p1) - roc_auc_score(y, p0)))
        slope_diff.append(float(roc_auc_score(y, p) - roc_auc_score(y, ps)))
        brier_const = brier_score_loss(y, const)
        brier_skills.append(float(1 - brier_score_loss(y, p) / brier_const) if brier_const > 0 else np.nan)
        dec = decile_codes(p)
        top_success_rates.append(float(np.mean(y[dec == 10])))
        top_uplifts.append(float(np.mean(y[dec == 10]) - np.mean(y)))
    draw_hash = hashlib.sha256(draws.tobytes()).hexdigest()
    return {
        "samples": BOOTSTRAP_SAMPLES,
        "seed": SEED,
        "block_days": BOOTSTRAP_BLOCK_DAYS,
        "block_count": len(blocks),
        "same_resampling_indices_for_all_models": True,
        "paired_draw_counts_sha256": draw_hash,
        "auc": {"point": metric_values(frame, frame[selected_col].to_numpy())["roc_auc"], **bootstrap_ci(aucs)},
        "top_decile_success_rate": {"point": metric_values(frame, frame[selected_col].to_numpy())["top_decile_success_rate"], **bootstrap_ci(top_success_rates)},
        "top_decile_uplift": {"point": metric_values(frame, frame[selected_col].to_numpy())["top_decile_uplift"], **bootstrap_ci(top_uplifts)},
        "brier_skill_vs_const": {"point": metric_values(frame, frame[selected_col].to_numpy())["brier_skill_vs_const"], **bootstrap_ci(brier_skills)},
        "f1_minus_f0_auc_diff": {"point": float(roc_auc_score(frame[TARGET], frame[f1_col]) - roc_auc_score(frame[TARGET], frame[f0_col])), **bootstrap_ci(f1_minus_f0)},
        "selected_minus_slope_auc_diff": {"point": float(roc_auc_score(frame[TARGET], frame[selected_col]) - roc_auc_score(frame[TARGET], frame["p_slope_only"])), **bootstrap_ci(slope_diff)},
    }


def stratum_rows(oof: pd.DataFrame, probability: np.ndarray) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    specs = [
        ("side", oof["side"]),
        ("year", oof["event_year"].astype(str)),
        ("asset_group", oof["asset_group"].astype(str)),
        ("volatility_state", oof["volatility_state_p0r"].fillna("missing").astype(str)),
        ("listing_age", pd.cut(oof["listing_age_days"], bins=[-1, 180, 365, 730, np.inf], labels=["lt_180d", "180_365d", "365_730d", "gt_730d"]).astype(str)),
        ("liquidity", pd.qcut(oof["liquidity_rank_pct_p0r"].rank(method="first"), q=3, labels=["low", "mid", "high"]).astype(str)),
    ]
    base = oof.copy()
    base["p"] = probability
    for stratum_type, labels in specs:
        base["_stratum"] = labels
        for value, group in base.groupby("_stratum", observed=True):
            if len(group) < 20:
                continue
            row = metric_row(
                model_id=str(oof["selected_model_id"].iloc[0]),
                feature_scheme=model_feature_scheme(str(oof["selected_model_id"].iloc[0])),
                fold="OOF",
                split="validation",
                train_n=0,
                train_label_end_max=None,
                frame=group,
                probability=group["p"].to_numpy(),
                evaluation="oof",
                stratum_type=stratum_type,
                stratum_value=str(value),
            )
            row["row_type"] = "stratum"
            rows.append(row)
    return rows


def final_refit(frame: pd.DataFrame, feature_spec: dict[str, Any], development: dict[str, Any]) -> dict[str, Any]:
    selected = development["selected_model_id"]
    features = {
        "SLOPE_ONLY": feature_spec["slope_only_features"],
        "F0_MA7_CORE": scheme_features(feature_spec, "F0_MA7_CORE"),
        "F1_MA7_PATH": scheme_features(feature_spec, "F1_MA7_PATH"),
    }
    final = frame.loc[frame[LABEL_END].lt(CUTOFF)].copy()
    if len(final) != EXPECTED_FINAL_TRAIN_ROWS:
        raise RuntimeError(f"expected {EXPECTED_FINAL_TRAIN_ROWS} final rows, got {len(final)}")
    if final["ts"].ge(CUTOFF).any() or final["asset"].eq(HYPE_ASSET).any():
        raise RuntimeError("final train contamination")
    if selected in {"CONST_PRIOR", "SLOPE_ONLY_LOGIT", "F0_LOGIT", "F1_LOGIT"}:
        p_train, _, _ = fit_candidate(selected, final, final, features, feature_spec["categorical_features"])
        rounds = None
    else:
        scheme_id, lgbm_id = selected.split("_")
        scheme = "F0_MA7_CORE" if scheme_id == "F0" else "F1_MA7_PATH"
        rounds = int(development["selected_rounds"] or 100)
        p_train, _, _, _ = fit_lgbm(final, final, features[scheme], feature_spec["categorical_features"], lgbm_id, rounds=rounds)
    calibration = development["candidate_summary"][selected]["calibration"]
    p_selected = apply_calibration(p_train, calibration)
    return {
        "train_rows": int(len(final)),
        "train_max_ts": final["ts"].max(),
        "train_max_label_end": final[LABEL_END].max(),
        "selected_model_id": selected,
        "selected_feature_scheme": model_feature_scheme(selected),
        "selected_rounds": rounds,
        "calibration": calibration,
        "train_metrics": metric_values(final, p_selected),
        "post_2025_predictions_written": 0,
        "new_oos_available": False,
    }


def decide(summary: dict[str, Any]) -> dict[str, Any]:
    oof = summary["oof_metrics"]
    boot = summary["bootstrap"]
    folds = summary["development"]["candidate_summary"][summary["development"]["selected_model_id"]]["fold_auc"]
    overfit_flags = summary["selected_fold_overfit_flags"]
    lago = summary["leave_asset_group_out"]
    side = summary["side_metrics"]
    year_flip = any(v["roc_auc"] is not None and v["roc_auc"] < 0.50 for v in summary["year_metrics"].values())
    candidate_pass = (
        min(folds) > 0.52
        and float(np.mean(folds)) > 0.55
        and not any(overfit_flags)
        and boot["auc"]["ci95_low"] is not None
        and boot["auc"]["ci95_low"] > 0.50
        and boot["top_decile_uplift"]["ci95_low"] is not None
        and boot["top_decile_uplift"]["ci95_low"] > 0
        and summary["non_overlap_auc"] > 0.52
        and np.median(list(lago.values())) > 0.52
        and min(lago.values()) >= 0.49
        and side["long"]["roc_auc"] > 0.50
        and side["short"]["roc_auc"] > 0.50
        and not year_flip
    )
    f1_incremental = boot["f1_minus_f0_auc_diff"]["ci95_low"] is not None and boot["f1_minus_f0_auc_diff"]["ci95_low"] > 0
    if candidate_pass and not f1_incremental:
        verdict = "SIGNAL_EXPLAINED_BY_MA7_CORE"
    elif candidate_pass:
        verdict = "POOLED_MINIMAL_CANDIDATE_FROZEN_AWAITING_NEW_OOS"
    elif oof["roc_auc"] is not None and oof["roc_auc"] > 0.51:
        verdict = "UNSTABLE_POOLED_SIGNAL"
    else:
        verdict = "NO_LEARNABLE_POOLED_SIGNAL"
    return {
        "verdict": verdict,
        "pooled_candidate_gate_pass": bool(candidate_pass),
        "f1_incremental_gate_pass": bool(f1_incremental),
        "year_flip": bool(year_flip),
        "status": STATUS,
    }


def fmt(value: Any, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "NA"
    return f"{float(value):.{digits}f}"


def pct(value: Any) -> str:
    if value is None:
        return "NA"
    return f"{100 * float(value):.2f}%"


def write_reports(summary: dict[str, Any], metric_df: pd.DataFrame, deciles: pd.DataFrame) -> None:
    selected = summary["development"]["selected_model_id"]
    cand = summary["development"]["candidate_summary"]
    probability_calibration = summary["probability_calibration"]
    forward_calibration = probability_calibration["forward_validation"]
    final_calibrator = probability_calibration["final_calibrator"]
    selected_rows = metric_df.loc[(metric_df["model_id"].eq(selected)) & (metric_df["row_type"].eq("metric")) & (metric_df["evaluation"].eq("development"))]
    lines = [
        "# BIN-1D-MA7-CTP P2：Pooled-Minimal MA7 穿越稳定性审计",
        "",
        f"> {summary['generated_at_utc']}。状态：`{STATUS}`。",
        "> P2 不读取 2025+ 建模行，不生成 2025+ 预测；当前没有合法新 OOS。",
        "> 本轮没有读取 HYPE、没有训练多空独立头、不是策略、not live-ready。",
        "",
        "## 裁决",
        "",
        f"**{summary['decision']['verdict']}** / `{STATUS}`",
        "",
        f"- 确认只训练真实 MA7 穿越事件：`{summary['event_audit']['n']}` 行，非穿越 `{summary['event_audit']['non_cross']}` 行。",
        f"- 只训练一个 pooled 方向对齐模型：`{summary['one_pooled_model_only']}`；独立 long/short heads：`0`。",
        f"- HYPE 行数：输入 `{summary['hype_isolation']['input_rows']}`，OOF `{summary['hype_isolation']['oof_rows']}`，报告/模型卡 `{summary['hype_isolation']['model_card_rows']}`。",
        f"- 2025+ 建模读取行数 `{summary['input_integrity']['post_2025_model_rows_read']}`；2025+ 预测行数 `{summary['final_refit']['post_2025_predictions_written']}`。",
        "",
        "## 事件样本",
        "",
        f"- 选择/OOF 事件 `{summary['event_audit']['n']}`，资产 `{summary['event_audit']['assets']}`，多头 `{summary['event_audit']['long']}`，空头 `{summary['event_audit']['short']}`。",
        f"- 区间 `{summary['event_audit']['min_ts']}` 至 `{summary['event_audit']['max_ts']}`；最终重训 `label_end_ts_20d < 2025-01-01` 行数 `{summary['final_refit']['train_rows']}`。",
        "",
        "## D1/D2/D3 训练与验证对照（锁定模型）",
        "",
        "| Fold | Train n | Train 正例率 | Train AUC | Train PR-AUC | Train logloss | Train Brier | Val n | Val 正例率 | Val AUC | Val PR-AUC | Val logloss | Val Brier | AUC 差 | Uplift 差 | 标记 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for fold in ["D1", "D2", "D3"]:
        tr = selected_rows.loc[(selected_rows["fold"].eq(fold)) & (selected_rows["split"].eq("training"))].iloc[0]
        va = selected_rows.loc[(selected_rows["fold"].eq(fold)) & (selected_rows["split"].eq("validation"))].iloc[0]
        lines.append(
            f"| {fold} | {int(tr.eval_n)} | {pct(tr.positive_rate)} | {fmt(tr.roc_auc)} | {fmt(tr.pr_auc)} | {fmt(tr.log_loss)} | {fmt(tr.brier)} | "
            f"{int(va.eval_n)} | {pct(va.positive_rate)} | {fmt(va.roc_auc)} | {fmt(va.pr_auc)} | {fmt(va.log_loss)} | {fmt(va.brier)} | "
            f"{fmt(va.train_val_auc_gap)} | {fmt(va.train_val_top_uplift_gap)} | {va.overfit_flag or ''} |"
        )
    lines.extend(
        [
            "",
            "## F0 / F1 与候选选择",
            "",
            "| Model | Worst fold AUC | Macro AUC | Macro Brier | Macro logloss | Fold AUC |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for model_id, stats in cand.items():
        lines.append(
            f"| {model_id} | {fmt(stats['worst_fold_auc'])} | {fmt(stats['macro_auc'])} | {fmt(stats['macro_brier'])} | {fmt(stats['macro_log_loss'])} | "
            f"{', '.join(fmt(x) for x in stats['fold_auc'])} |"
        )
    boot = summary["bootstrap"]
    lines.extend(
        [
            "",
            "## OOF 稳定性门禁",
            "",
            f"- 锁定模型：`{selected}` / `{summary['development']['selected_feature_scheme']}`；原始 OOF 排序 AUC `{fmt(summary['oof_metrics']['roc_auc'])}`，PR-AUC `{fmt(summary['oof_metrics']['pr_auc'])}`，raw Brier `{fmt(summary['oof_metrics']['brier'])}`。",
            f"- 28 日 block bootstrap AUC 95% CI：`[{fmt(boot['auc']['ci95_low'])}, {fmt(boot['auc']['ci95_high'])}]`。",
            f"- top-decile 成功率 `{pct(boot['top_decile_success_rate']['point'])}`，95% CI `[{pct(boot['top_decile_success_rate']['ci95_low'])}, {pct(boot['top_decile_success_rate']['ci95_high'])}]`。",
            f"- top-decile uplift `{fmt(boot['top_decile_uplift']['point'])}`，95% CI `[{fmt(boot['top_decile_uplift']['ci95_low'])}, {fmt(boot['top_decile_uplift']['ci95_high'])}]`。",
            f"- F1 - F0 paired AUC 差 `{fmt(boot['f1_minus_f0_auc_diff']['point'])}`，95% CI `[{fmt(boot['f1_minus_f0_auc_diff']['ci95_low'])}, {fmt(boot['f1_minus_f0_auc_diff']['ci95_high'])}]`。",
            f"- selected - SLOPE_ONLY paired AUC 差 `{fmt(boot['selected_minus_slope_auc_diff']['point'])}`，95% CI `[{fmt(boot['selected_minus_slope_auc_diff']['ci95_low'])}, {fmt(boot['selected_minus_slope_auc_diff']['ci95_high'])}]`。",
            f"- 20 日 non-overlap OOF AUC：`{fmt(summary['non_overlap_auc'])}`；asset-balanced AUC：`{fmt(summary['oof_metrics']['asset_balanced_auc'])}`。",
            f"- LAGO 五组 AUC：{', '.join(f'{k}={fmt(v)}' for k, v in summary['leave_asset_group_out'].items())}。",
            "",
            "## 概率校准审计",
            "",
            "- 主排序门禁继续使用未改动的 raw OOF score；AUC、十分位和 F1-F0 比较不受校准层影响。",
            f"- 前向校准只在 `{', '.join(forward_calibration['evaluation_folds'])}` 评价，共 `{forward_calibration['eval_rows']}` 行；D1 因没有更早 OOF，保持 raw。",
            f"- 前向验证 raw/calibrated Brier：`{fmt(forward_calibration['raw']['brier'])}` / `{fmt(forward_calibration['forward_calibrated']['brier'])}`；raw/calibrated log loss：`{fmt(forward_calibration['raw']['log_loss'])}` / `{fmt(forward_calibration['forward_calibrated']['log_loss'])}`。",
            f"- 最终未来概率层：`{final_calibrator['method']}`；选择依据 `{final_calibrator['selection_basis']}`；最终校准拟合只使用标签在 cutoff 前完整结束的 `{final_calibrator['final_fit_rows']}` 条 OOF。",
            f"- 前向验证最高十分位实际成功率 `{pct(probability_calibration['forward_top_decile']['observed_success_rate'])}`，该组平均前向校准概率 `{pct(probability_calibration['forward_top_decile']['mean_forward_calibrated_probability'])}`。",
            "",
            "## Long / Short 分层",
            "",
            "| Side | n | 正例率 | AUC | PR-AUC | Brier | Top uplift |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for side, metrics in summary["side_metrics"].items():
        lines.append(f"| {side} | {metrics['eval_n']} | {pct(metrics['positive_rate'])} | {fmt(metrics['roc_auc'])} | {fmt(metrics['pr_auc'])} | {fmt(metrics['brier'])} | {fmt(metrics['top_decile_uplift'])} |")
    lines.extend(["", "## Top/Bottom 十分位（OOF）", "", "| Decile | n | 成功率 | uplift | 净收益均值 | 净收益中位数 |", "| ---: | ---: | ---: | ---: | ---: | ---: |"])
    for _, row in deciles.sort_values("decile").iterrows():
        lines.append(f"| {int(row.decile)} | {int(row.n)} | {pct(row.success_rate)} | {fmt(row.uplift)} | {fmt(row.net_return_mean)} | {fmt(row.net_return_median)} |")
    lines.extend(
        [
            "",
            "## 一般 asset-day 控制组",
            "",
            f"- 当前工作树未发现可合法对齐的 CATL P1 冻结预测文件；控制组状态：`{summary['general_day_control']['status']}`。",
            "- 因唯一输入合同限制，本轮未另找替代预测，也未用一般 asset-day 模型参与选择。",
            "",
            "## 边界",
            "",
            "- 没有读取 HYPE、没有 HYPE reveal。",
            "- 没有 2025+ 建模读取、没有 2025+ 预测、没有新 OOS。",
            "- 没有 long/short 独立头，没有策略、账户、仓位、权益曲线或 live-ready 产物。",
        ]
    )
    atomic_write_text(REPORT_PATH, "\n".join(lines) + "\n")

    audit_lines = [
        "# BIN-1D-MA7-CTP P2 建模审计",
        "",
        f"状态：`{STATUS}`。裁决：`{summary['decision']['verdict']}`。",
        "",
        "## 输入完整性",
        "",
        f"- P0R artifact 哈希全部匹配：`{summary['input_integrity']['p0r_artifact_hashes_all_match']}`",
        f"- P1 feature spec SHA256 匹配 manifest：`{summary['input_integrity']['p1_feature_spec_sha256']}`",
        f"- HYPE 输入行：`{summary['hype_isolation']['input_rows']}`",
        f"- HYPER 输入行：`{summary['hyper_preservation']['input_rows']}`",
        f"- 2025+ 建模读取行：`{summary['input_integrity']['post_2025_model_rows_read']}`",
        f"- 事件过滤与冻结审计值一致：`{summary['event_audit']['n']}`",
        "",
        "## 时间与样本隔离",
        "",
        "- D1-D3 每折 `max(train.label_end_ts_20d) < validation_start`。",
        "- P2 OOF、fold metrics、decile metrics 均只含 `<2025-01-01` 事件。",
        "- 只训练 `POOLED_DIRECTION_ALIGNED` 一个模型；long/short 仅作分层评价。",
        "- paired bootstrap 对 selected、F0、F1、SLOPE 使用同一日期块重采样索引。",
        "- D2 校准器只用标签在 D2 开始前结束的 D1 OOF；D3 校准器只用标签在 D3 开始前结束的 D1-D2 OOF。",
        f"- 最终校准器方法：`{final_calibrator['method']}`；选择依据：`{final_calibrator['selection_basis']}`；最终拟合标签截止：`{final_calibrator['final_fit_label_end_max']}`。",
        "- 原始排序概率与前向交叉校准概率分列保存；没有用同一验证标签拟合并评价其校准器。",
        "",
        "## 禁止产物",
        "",
        "- 无 2025+ 预测、无 HYPE reveal、无策略、仓位、账户、live-ready。",
    ]
    atomic_write_text(AUDIT_PATH, "\n".join(audit_lines) + "\n")


def build_manifest(paths: Iterable[Path], input_audit: dict[str, Any]) -> None:
    artifacts = []
    for path in paths:
        if path.exists():
            artifacts.append({"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    atomic_write_json(
        MANIFEST_PATH,
        {
            "family": "Binance-1D-MA7-Cross-Trend-Probability",
            "experiment": "P2 Pooled-Minimal MA7 Cross Stability Audit",
            "generated_at_utc": datetime.now(UTC),
            "status": STATUS,
            "holdout_read": False,
            "hype_asset_excluded": HYPE_ASSET,
            "hype_reveal_executed": False,
            "post_2025_predictions_written": 0,
            "input_lineage": {
                "p0r_manifest_path": str(P0R_MANIFEST_PATH.relative_to(ROOT)),
                "p0r_manifest_sha256": input_audit["p0r_manifest_sha256"],
                "p1_feature_spec_path": str(P1_FEATURE_SPEC_PATH.relative_to(ROOT)),
                "p1_feature_spec_sha256": input_audit["p1_feature_spec_sha256"],
                "contract_sha256": sha256_file(SPEC_PATH),
                "feature_spec_sha256": sha256_file(FEATURE_SPEC_PATH),
            },
            "artifacts": artifacts,
        },
    )


def main() -> None:
    args = parse_args()
    if not args.run:
        raise SystemExit("Pass --run to execute P2.")
    ensure_output_policy(args.force)
    feature_spec, input_audit = validate_inputs()
    event_audit = count_events_without_labels()
    atomic_write_json(
        CONTRACT_LOCK_PATH,
        {
            "status": "FROZEN_BEFORE_P2_LABEL_READ",
            "generated_at_utc": datetime.now(UTC),
            "contract_sha256": sha256_file(SPEC_PATH),
            "feature_spec_sha256": sha256_file(FEATURE_SPEC_PATH),
            "p1_feature_spec_sha256": input_audit["p1_feature_spec_sha256"],
            "event_filter_audit_without_labels": event_audit,
        },
    )
    print("P2 contract lock written; loading labels after lock.", flush=True)
    frame = load_event_panel(feature_spec)
    metric_df, oof, development = run_development(frame, feature_spec)
    selected = development["selected_model_id"]
    selected_col = "p_selected"
    oof_metrics = metric_values(oof, oof[selected_col].to_numpy())
    selected_calibration = development["candidate_summary"][selected]["calibration"]
    calibration_comparison = development["calibration_comparison"][selected]
    calibration_eval_mask = oof["fold"].isin(calibration_comparison["evaluation_folds"])
    calibration_eval = oof.loc[calibration_eval_mask].copy()
    calibration_eval_decile = decile_codes(calibration_eval[selected_col].to_numpy())
    calibration_top_mask = calibration_eval_decile == 10
    probability_calibration = {
        "ranking_probability_column": selected_col,
        "forward_probability_column": "p_selected_calibrated_forward",
        "primary_ranking_uses_raw_oof": True,
        "forward_validation": calibration_comparison,
        "all_oof_forward_metrics": metric_values(oof, oof["p_selected_calibrated_forward"].to_numpy()),
        "forward_top_decile": {
            "n": int(calibration_top_mask.sum()),
            "observed_success_rate": float(calibration_eval.loc[calibration_top_mask, TARGET].mean()),
            "mean_raw_probability": float(calibration_eval.loc[calibration_top_mask, selected_col].mean()),
            "mean_forward_calibrated_probability": float(calibration_eval.loc[calibration_top_mask, "p_selected_calibrated_forward"].mean()),
        },
        "final_calibrator": selected_calibration,
    }
    non_overlap = non_overlap_sample(oof)
    non_overlap_auc = float(roc_auc_score(non_overlap[TARGET], non_overlap[selected_col])) if len(non_overlap[TARGET].unique()) >= 2 else None
    bootstrap = paired_block_bootstrap(oof, selected_col, "p_f0_reference", "p_f1_reference")
    side_metrics = {side: metric_values(group, group[selected_col].to_numpy()) for side, group in oof.groupby("side", sort=True)}
    year_metrics = {str(year): metric_values(group, group[selected_col].to_numpy()) for year, group in oof.groupby("event_year", sort=True)}
    lago = {str(group): float(roc_auc_score(g[TARGET], g[selected_col])) for group, g in oof.groupby("asset_group", sort=True) if len(g[TARGET].unique()) >= 2}
    decile_df = pd.DataFrame(decile_rows(oof, oof[selected_col].to_numpy(), model_id=selected, evaluation="oof"))
    stratum_metric_df = pd.DataFrame(stratum_rows(oof, oof[selected_col].to_numpy()))
    if not stratum_metric_df.empty:
        metric_df = pd.concat([metric_df, stratum_metric_df], ignore_index=True)
    final = final_refit(frame, feature_spec, development)
    selected_fold_flags = (
        metric_df.loc[(metric_df["model_id"].eq(selected)) & (metric_df["split"].eq("validation")) & (metric_df["evaluation"].eq("development")), "overfit_flag"]
        .fillna("")
        .eq("SEVERE_OVERFIT_WARNING")
        .tolist()
    )
    summary: dict[str, Any] = {
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "alias": "BIN-1D-MA7-CTP",
        "experiment": "P2 Pooled-Minimal MA7 Cross Stability Audit",
        "generated_at_utc": datetime.now(UTC),
        "status": STATUS,
        "objective_ma7_cross_only": True,
        "one_pooled_model_only": True,
        "independent_long_short_heads_trained": 0,
        "no_strategy_no_portfolio_no_live_artifact": True,
        "input_integrity": input_audit,
        "event_audit": {
            **event_audit,
            "positive_rate": float(frame[TARGET].mean()),
            "final_train_rows": final["train_rows"],
        },
        "hype_isolation": {
            "asset": HYPE_ASSET,
            "input_rows": input_audit["panel_hype_rows"],
            "model_rows_read": 0,
            "event_rows": int(frame["asset"].eq(HYPE_ASSET).sum()),
            "oof_rows": int(oof["asset"].eq(HYPE_ASSET).sum()),
            "model_card_rows": 0,
            "hype_reveal_executed": False,
        },
        "hyper_preservation": {
            "asset": HYPER_ASSET,
            "input_rows": input_audit["panel_hyper_rows"],
            "event_rows_pre_2025": int(frame["asset"].eq(HYPER_ASSET).sum()),
            "oof_rows": int(oof["asset"].eq(HYPER_ASSET).sum()),
        },
        "development": development,
        "selected_fold_overfit_flags": selected_fold_flags,
        "oof_metrics": oof_metrics,
        "probability_calibration": probability_calibration,
        "bootstrap": bootstrap,
        "non_overlap_auc": non_overlap_auc,
        "non_overlap_n": int(len(non_overlap)),
        "leave_asset_group_out": lago,
        "side_metrics": side_metrics,
        "year_metrics": year_metrics,
        "final_refit": final,
        "general_day_control": {
            "status": "unavailable_no_legal_aligned_prediction_file_found",
            "used_for_selection": False,
        },
    }
    summary["decision"] = decide(summary)

    model_card = {
        "family": summary["family"],
        "experiment": summary["experiment"],
        "model_role": "single pooled direction-aligned MA7-cross event scorer",
        "selected_model_id": selected,
        "selected_feature_scheme": development["selected_feature_scheme"],
        "features": scheme_features(feature_spec, development["selected_feature_scheme"]) if development["selected_feature_scheme"] in feature_spec["schemes"] else feature_spec["slope_only_features"],
        "feature_spec_sha256": sha256_file(FEATURE_SPEC_PATH),
        "contract_sha256": sha256_file(SPEC_PATH),
        "seed": SEED,
        "calibration": selected_calibration,
        "calibration_evaluation": calibration_comparison,
        "selected_rounds": final["selected_rounds"],
        "status": STATUS,
        "hype_rows": 0,
        "hype_reveal_executed": False,
        "post_2025_predictions_written": 0,
        "not_live_ready": True,
        "prohibited_uses": ["position sizing", "account backtest", "live trading", "long/short head deployment", "continuation or exit modeling", "HYPE reveal"],
    }
    if any("funding" in f or "market_" in f or "btc_" in f or "liquidity" in f for f in model_card["features"]):
        raise RuntimeError("forbidden P2 feature leaked")

    atomic_write_parquet(OOF_PREDICTIONS_PATH, oof)
    atomic_write_parquet(FOLD_METRICS_PATH, metric_df)
    atomic_write_parquet(DECILE_METRICS_PATH, decile_df)
    atomic_write_json(MODEL_CARD_PATH, model_card)
    atomic_write_json(SUMMARY_PATH, summary)
    write_reports(summary, metric_df, decile_df)
    build_manifest(
        [
            SPEC_PATH,
            FEATURE_SPEC_PATH,
            Path(__file__).resolve(),
            TEST_PATH,
            CONTRACT_LOCK_PATH,
            FOLD_METRICS_PATH,
            OOF_PREDICTIONS_PATH,
            DECILE_METRICS_PATH,
            MODEL_CARD_PATH,
            SUMMARY_PATH,
            REPORT_PATH,
            AUDIT_PATH,
        ],
        input_audit,
    )
    print(f"P2 complete: {summary['decision']['verdict']} selected={selected}", flush=True)


if __name__ == "__main__":
    main()
