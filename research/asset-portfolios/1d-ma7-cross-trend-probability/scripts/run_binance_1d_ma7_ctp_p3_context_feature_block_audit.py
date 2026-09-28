#!/usr/bin/env python3
"""Run BIN-1D-MA7-CTP P3 independent context feature block audit.

P3 trains only pooled direction-aligned logistic regressions on strict MA7 cross
events whose 20-day label is complete before 2025-01-01 UTC. It compares P2's
F1 baseline with one context block at a time and emits diagnostic evidence only.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import duckdb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
CATL_DIR = ROOT / "research/asset-portfolios/1d-cross-asset-trend-lifecycle"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAGNOSTIC_DIR = FAMILY_DIR / "diagnostics"
SPEC_PATH = FAMILY_DIR / "specs/binance-1d-ma7-ctp-p3-context-feature-block-audit-contract-2026-09-01.md"
FEATURE_SPEC_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_feature_spec.json"
P2_FEATURE_SPEC_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_feature_spec.json"
P2_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_summary.json"
P2_MODEL_CARD_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_model_card.json"
P2_SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p2_pooled_minimal_stability.py"
P0R_FEATURE_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_feature_blocks.json"
P0R_MANIFEST_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_manifest.json"
PANEL_DIR = CATL_DIR / "artifacts/p0r_donor_directional_modeling_panel"
PANEL_GLOB = PANEL_DIR / "**/*.parquet"

CONTRACT_LOCK_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_contract_lock.json"
FOLD_METRICS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_fold_metrics.parquet"
OOF_PREDICTIONS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_oof_predictions.parquet"
INCREMENTAL_COMPARISONS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_incremental_comparisons.parquet"
SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_summary.json"
MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_manifest.json"
MODEL_CARD_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_model_card.json"
REPORT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p3-context-feature-block-audit-2026-09-01.md"
AUDIT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p3-modeling-audit-2026-09-01.md"
TEST_PATH = ROOT / "tests/test_binance_1d_ma7_ctp_p3_context_feature_block_audit.py"

HYPE_ASSET = "HYPE/USDT:USDT"
HYPER_ASSET = "HYPER/USDT:USDT"
SEED = 20260901
CUTOFF = pd.Timestamp("2025-01-01T00:00:00Z")
STATUS = "explore / diagnostic-only / not promoted / not live-ready"
TARGET = "label_entry_success_20d"
LABEL_END = "label_end_ts_20d"
NET_RETURN = "label_entry_net_return"
HEAD = "POOLED_DIRECTION_ALIGNED_LOGIT"
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_BLOCK_DAYS = 28

EXPECTED_RAW_PRE2025_EVENTS = 54137
EXPECTED_STRICT_ROWS = 52563
EXPECTED_STRICT_ASSETS = 338
EXPECTED_STRICT_MIN_TS = pd.Timestamp("2019-11-27T00:00:00Z")
EXPECTED_STRICT_MAX_TS = pd.Timestamp("2024-12-10T00:00:00Z")

FOLDS = (
    ("D1", pd.Timestamp("2022-01-01T00:00:00Z"), pd.Timestamp("2023-01-01T00:00:00Z")),
    ("D2", pd.Timestamp("2023-01-01T00:00:00Z"), pd.Timestamp("2024-01-01T00:00:00Z")),
    ("D3", pd.Timestamp("2024-01-01T00:00:00Z"), CUTOFF),
)

CANDIDATES = (
    "B0_P2_F1_LOGIT",
    "B1_LIQUIDITY_LOGIT",
    "B2_MA30_CONTEXT_LOGIT",
    "B3_CROSS_MARKET_LOGIT",
    "B4_FUNDING_LOGIT",
)

INCREMENTAL_CANDIDATES = CANDIDATES[1:]


def load_p2_module() -> Any:
    spec = importlib.util.spec_from_file_location("binance_1d_ma7_ctp_p2", P2_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import P2 helper script")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


P2 = load_p2_module()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="execute P3")
    parser.add_argument("--force", action="store_true", help="overwrite P3 outputs")
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
    if isinstance(value, np.ndarray):
        return value.tolist()
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


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def output_paths() -> tuple[Path, ...]:
    return (
        CONTRACT_LOCK_PATH,
        FOLD_METRICS_PATH,
        OOF_PREDICTIONS_PATH,
        INCREMENTAL_COMPARISONS_PATH,
        SUMMARY_PATH,
        MANIFEST_PATH,
        MODEL_CARD_PATH,
        REPORT_PATH,
        AUDIT_PATH,
    )


def ensure_output_policy(force: bool) -> None:
    existing = [path for path in output_paths() if path.exists()]
    if existing and not force:
        raise FileExistsError("P3 outputs already exist; pass --force to reproduce: " + ", ".join(str(p.relative_to(ROOT)) for p in existing))


def scheme_features(feature_spec: dict[str, Any], scheme: str) -> list[str]:
    names: list[str] = []
    for block in feature_spec["schemes"][scheme]:
        names.extend(feature_spec["feature_blocks"][block])
    if len(names) != len(set(names)):
        raise RuntimeError(f"{scheme} has duplicate features")
    return names


def candidate_features(feature_spec: dict[str, Any], candidate: str) -> list[str]:
    names: list[str] = []
    for block in feature_spec["candidate_feature_blocks"][candidate]:
        names.extend(feature_spec["feature_blocks"][block])
    if len(names) != len(set(names)):
        raise RuntimeError(f"{candidate} has duplicate features")
    return names


def incremental_block_for_candidate(feature_spec: dict[str, Any], candidate: str) -> list[str]:
    blocks = [b for b in feature_spec["candidate_feature_blocks"][candidate] if b != "B0_P2_F1"]
    return feature_spec["feature_blocks"][blocks[0]] if blocks else []


def t1_source_name(feature: str) -> str:
    if not feature.startswith("t1_"):
        raise ValueError(feature)
    return feature[3:]


def source_columns_for_features(feature_spec: dict[str, Any]) -> list[str]:
    columns: set[str] = set()
    for candidate in CANDIDATES:
        for feature in candidate_features(feature_spec, candidate):
            if feature == "liquidity_rank_centered_sq":
                columns.add("liquidity_rank_pct_p0r")
            elif feature.startswith("t1_"):
                columns.add(t1_source_name(feature))
            else:
                columns.add(feature)
    return sorted(columns)


def asset_group(asset: str) -> int:
    return int(hashlib.sha256(asset.encode("utf-8")).hexdigest(), 16) % 5


def validate_feature_spec(feature_spec: dict[str, Any], p2_feature_spec: dict[str, Any], p0r_feature_blocks: dict[str, Any]) -> None:
    if tuple(feature_spec["candidate_feature_blocks"]) != CANDIDATES:
        raise RuntimeError("P3 candidate set changed")
    if feature_spec["feature_blocks"]["B0_P2_F1"] != scheme_features(p2_feature_spec, "F1_MA7_PATH"):
        raise RuntimeError("B0 does not exactly reuse P2 F1_MA7_PATH")
    if sha256_file(P2_FEATURE_SPEC_PATH) != feature_spec["source_inputs"]["p2_feature_spec"]["sha256"]:
        raise RuntimeError("P2 feature spec SHA mismatch")

    all_p0r_allowed = set(p0r_feature_blocks["all_allowed_features"])
    all_features = set()
    for candidate in CANDIDATES:
        all_features.update(candidate_features(feature_spec, candidate))
    allowed_derived = set(feature_spec["derived_features"])
    missing = {f for f in all_features if not f.startswith("t1_") and f not in all_p0r_allowed and f not in allowed_derived}
    missing.update({t1_source_name(f) for f in all_features if f.startswith("t1_") and t1_source_name(f) not in all_p0r_allowed})
    if missing:
        raise RuntimeError(f"P3 features absent from P0R allowlist: {sorted(missing)}")

    forbidden = set(feature_spec["forbidden_in_x"])
    leaked = sorted(all_features & forbidden)
    if leaked:
        raise RuntimeError(f"forbidden columns leaked into P3 X: {leaked}")
    for feature in all_features:
        lower = feature.lower()
        if any(token.rstrip("*") in lower for token in feature_spec["forbidden_feature_patterns"]):
            raise RuntimeError(f"forbidden feature pattern leaked into P3 X: {feature}")
    if "B_ALL" in feature_spec.get("candidate_feature_blocks", {}):
        raise RuntimeError("P3 must not create B_ALL")


def validate_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    feature_spec = load_json(FEATURE_SPEC_PATH)
    p2_feature_spec = load_json(P2_FEATURE_SPEC_PATH)
    p2_summary = load_json(P2_SUMMARY_PATH)
    p2_model_card = load_json(P2_MODEL_CARD_PATH)
    p0r_feature_blocks = load_json(P0R_FEATURE_PATH)
    p0r_manifest = load_json(P0R_MANIFEST_PATH)
    validate_feature_spec(feature_spec, p2_feature_spec, p0r_feature_blocks)

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
    row = con.execute(
        """
        SELECT
          count(*) FILTER (WHERE asset = ?) AS hype_all_rows,
          count(*) FILTER (WHERE asset = ?) AS hyper_all_rows,
          count(*) FILTER (WHERE ts >= TIMESTAMPTZ '2025-01-01 00:00:00+00:00') AS post_2025_rows_available,
          count(*) FILTER (WHERE ts < TIMESTAMPTZ '2025-01-01 00:00:00+00:00') AS pre_2025_rows_available
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        """,
        [HYPE_ASSET, HYPER_ASSET, str(PANEL_GLOB)],
    ).fetchone()
    audit = {
        "p0r_manifest_path": str(P0R_MANIFEST_PATH.relative_to(ROOT)),
        "p0r_manifest_sha256": sha256_file(P0R_MANIFEST_PATH),
        "p0r_feature_blocks_sha256": sha256_file(P0R_FEATURE_PATH),
        "p2_feature_spec_sha256": sha256_file(P2_FEATURE_SPEC_PATH),
        "p2_summary_sha256": sha256_file(P2_SUMMARY_PATH),
        "p2_model_card_sha256": sha256_file(P2_MODEL_CARD_PATH),
        "p2_script_sha256": sha256_file(P2_SCRIPT_PATH),
        "p0r_artifact_hash_checks": checks,
        "p0r_artifact_hashes_all_match": all(item["match"] for item in checks),
        "panel_file_set_matches_manifest": panel_globbed == sorted(panel_manifest_paths),
        "holdout_read": bool(p0r_manifest.get("holdout_read", True)),
        "hype_asset_excluded": p0r_manifest.get("hype_asset_excluded"),
        "panel_hype_rows": int(row[0]),
        "panel_hyper_rows": int(row[1]),
        "post_2025_rows_available_but_not_modeled": int(row[2]),
        "pre_2025_rows_available": int(row[3]),
        "post_2025_event_rows_read": 0,
        "post_2025_prediction_rows_written": 0,
        "hype_model_rows_read": 0,
    }
    if not audit["p0r_artifact_hashes_all_match"] or not audit["panel_file_set_matches_manifest"]:
        raise RuntimeError("DATA_BLOCK_NOT_READY: P0R manifest hash or panel file-set mismatch")
    if audit["holdout_read"] is not False or audit["hype_asset_excluded"] != HYPE_ASSET:
        raise RuntimeError("DATA_BLOCK_NOT_READY: P0R holdout/HYPE boundary mismatch")
    if audit["panel_hype_rows"] != 0:
        raise RuntimeError("HOLDOUT_CONTAMINATED")
    if audit["panel_hyper_rows"] <= 0:
        raise RuntimeError("DATA_BLOCK_NOT_READY: HYPER missing")
    if p2_summary["hype_isolation"]["input_rows"] != 0 or p2_model_card["hype_rows"] != 0:
        raise RuntimeError("HOLDOUT_CONTAMINATED: P2 baseline metadata contaminated")
    if p2_summary["input_integrity"]["post_2025_model_rows_read"] != 0 or p2_model_card["post_2025_predictions_written"] != 0:
        raise RuntimeError("DATA_BLOCK_NOT_READY: P2 baseline used 2025+ modeling rows")
    return feature_spec, p2_feature_spec, audit


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
          count(*) - count(DISTINCT asset || '|' || CAST(ts AS VARCHAR) || '|' || side) AS duplicate_asset_ts_side,
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
        "min_ts": pd.Timestamp(row[6]),
        "max_ts": pd.Timestamp(row[7]),
        "non_cross": int(row[8]),
        "ineligible": int(row[9]),
        "duplicate_asset_ts": int(row[10]),
        "duplicate_asset_ts_side": int(row[11]),
        "post_2025_rows": int(row[12]),
        "labels_read": False,
    }
    if audit["n"] != EXPECTED_RAW_PRE2025_EVENTS or audit["hype"] != 0 or audit["non_cross"] != 0 or audit["duplicate_asset_ts"] != 0:
        raise RuntimeError(f"DATA_BLOCK_NOT_READY: raw event audit mismatch: {json_ready(audit)}")
    return audit


def load_strict_event_panel(feature_spec: dict[str, Any]) -> pd.DataFrame:
    source_cols = source_columns_for_features(feature_spec)
    base_cols = [
        "asset",
        "asset_slug",
        "side",
        "side_sign",
        "ts",
        "feature_known_at",
        "entry_ts",
        "entry_ref",
        "atr_anchor",
        "probe_raw_ma7_cross_dir",
        "dir_raw_ma7_cross",
        "model_eligible_entry_p0r",
        "future_path_complete_20d",
        TARGET,
        LABEL_END,
        NET_RETURN,
        "volatility_state_p0r",
        "listing_age_days",
        "liquidity_rank_pct_p0r",
        "pit_universe_size_p0r",
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
    raw["feature_known_at"] = pd.to_datetime(raw["feature_known_at"], utc=True)
    raw["entry_ts"] = pd.to_datetime(raw["entry_ts"], utc=True)
    raw[LABEL_END] = pd.to_datetime(raw[LABEL_END], utc=True)

    raw = raw.sort_values(["asset", "side", "ts"]).copy()
    for feature in [f for f in feature_spec["feature_blocks"]["B0_P2_F1"] if f.startswith("t1_")]:
        raw[feature] = raw.groupby(["asset", "side"], sort=False)[t1_source_name(feature)].shift(1)

    events = raw.loc[
        raw["probe_raw_ma7_cross_dir"].eq(True)
        & raw["model_eligible_entry_p0r"].eq(True)
        & raw["ts"].lt(CUTOFF)
        & raw[LABEL_END].lt(CUTOFF)
    ].copy()
    events["liquidity_rank_centered_sq"] = (pd.to_numeric(events["liquidity_rank_pct_p0r"], errors="coerce") - 0.5) ** 2
    events["asset_group"] = events["asset"].map(asset_group).astype("int8")
    events["event_year"] = events["ts"].dt.year.astype("int16")

    if len(events) != EXPECTED_STRICT_ROWS:
        raise RuntimeError(f"DATA_BLOCK_NOT_READY: expected strict rows {EXPECTED_STRICT_ROWS}, got {len(events)}")
    if events["asset"].nunique() != EXPECTED_STRICT_ASSETS:
        raise RuntimeError(f"DATA_BLOCK_NOT_READY: expected strict assets {EXPECTED_STRICT_ASSETS}, got {events['asset'].nunique()}")
    if events["ts"].min() != EXPECTED_STRICT_MIN_TS or events["ts"].max() != EXPECTED_STRICT_MAX_TS:
        raise RuntimeError("DATA_BLOCK_NOT_READY: strict date range mismatch")
    if events["asset"].eq(HYPE_ASSET).any():
        raise RuntimeError("HOLDOUT_CONTAMINATED")
    if events["ts"].ge(CUTOFF).any() or events[LABEL_END].ge(CUTOFF).any():
        raise RuntimeError("DATA_BLOCK_NOT_READY: 2025+ row entered P3 strict sample")
    if events[TARGET].isna().any():
        raise RuntimeError("DATA_BLOCK_NOT_READY: null target label")
    if not events["future_path_complete_20d"].all():
        raise RuntimeError("DATA_BLOCK_NOT_READY: incomplete 20d future path")
    if not (events["feature_known_at"] < events["entry_ts"]).all():
        raise RuntimeError("DATA_BLOCK_NOT_READY: feature_known_at must precede entry_ts")
    if not events["probe_raw_ma7_cross_dir"].all() or not events["dir_raw_ma7_cross"].eq(1).all():
        raise RuntimeError("OBJECTIVE_MISALIGNED")
    if events.duplicated(["asset", "ts"]).any() or events.duplicated(["asset", "ts", "side"]).any():
        raise RuntimeError("DATA_BLOCK_NOT_READY: duplicate directional cross")
    if set(events["side"].unique()) != {"long", "short"}:
        raise RuntimeError("DATA_BLOCK_NOT_READY: side must be long/short")
    assert_t1_is_prior_valid_day(raw, events, feature_spec)
    return events.reset_index(drop=True)


def assert_t1_is_prior_valid_day(raw: pd.DataFrame, events: pd.DataFrame, feature_spec: dict[str, Any]) -> None:
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


def fold_split(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = frame.loc[frame["ts"].lt(start) & frame[LABEL_END].lt(start)].copy()
    validation = frame.loc[frame["ts"].ge(start) & frame["ts"].lt(end)].copy()
    if train.empty or validation.empty:
        raise RuntimeError("DATA_BLOCK_NOT_READY: empty P3 fold split")
    if not train[LABEL_END].max() < start:
        raise RuntimeError("DATA_BLOCK_NOT_READY: purge failed")
    if validation["ts"].ge(CUTOFF).any() or train["ts"].ge(CUTOFF).any() or validation[LABEL_END].ge(CUTOFF).any():
        raise RuntimeError("DATA_BLOCK_NOT_READY: 2025+ row entered split")
    return train, validation


def clip_probability(probability: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(probability, dtype=float), 1e-6, 1 - 1e-6)


def fit_logit(train: pd.DataFrame, valid: pd.DataFrame, features: list[str], categorical: list[str]) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    prep = P2.TabularPreprocessor(features, [c for c in categorical if c in features]).fit(train)
    x_train = prep.transform(train)
    x_valid = prep.transform(valid)
    scaler = StandardScaler()
    x_train_s = scaler.fit_transform(x_train)
    x_valid_s = scaler.transform(x_valid)
    model = LogisticRegression(max_iter=1000, solver="lbfgs", random_state=SEED)
    model.fit(x_train_s, train[TARGET].astype(int).to_numpy())
    coef_rows = []
    for name, coef in zip(prep.output_features or [], model.coef_[0], strict=False):
        coef_rows.append({"expanded_feature": name, "base_feature": name.split("__", 1)[0], "coef": float(coef)})
    return (
        model.predict_proba(x_train_s)[:, 1],
        model.predict_proba(x_valid_s)[:, 1],
        {"preprocessor": prep, "scaler": scaler, "model": model, "coef_rows": coef_rows},
    )


def metric_values(frame: pd.DataFrame, probability: np.ndarray) -> dict[str, Any]:
    return P2.metric_values(frame, probability)


def metric_row(
    *,
    candidate: str,
    fold: str,
    split: str,
    frame: pd.DataFrame,
    probability: np.ndarray,
    train_n: int,
    train_label_end_max: pd.Timestamp | None,
    probability_type: str,
    train_val_auc_gap: float | None = None,
    train_val_top_uplift_gap: float | None = None,
    overfit_flag: str = "",
    row_type: str = "metric",
    stratum_type: str = "all",
    stratum_value: str = "all",
) -> dict[str, Any]:
    values = metric_values(frame, probability)
    values.update(
        {
            "head": HEAD,
            "row_type": row_type,
            "candidate": candidate,
            "fold": fold,
            "split": split,
            "probability_type": probability_type,
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


def decile_stats(frame: pd.DataFrame, probability: np.ndarray) -> dict[str, Any]:
    y = frame[TARGET].astype(int).to_numpy()
    dec = P2.decile_codes(probability)
    top = frame.loc[dec == 10]
    bottom = frame.loc[dec == 1]
    return {
        "top_n": int(len(top)),
        "top_success_rate": float(top[TARGET].mean()) if len(top) else None,
        "top_uplift": float(top[TARGET].mean() - y.mean()) if len(top) else None,
        "top_net_return_mean": float(top[NET_RETURN].mean()) if len(top) else None,
        "top_net_return_median": float(top[NET_RETURN].median()) if len(top) else None,
        "bottom_n": int(len(bottom)),
        "bottom_success_rate": float(bottom[TARGET].mean()) if len(bottom) else None,
        "top_bottom_success_rate_diff": float(top[TARGET].mean() - bottom[TARGET].mean()) if len(top) and len(bottom) else None,
    }


@dataclass(frozen=True)
class BootstrapDraws:
    blocks: list[int]
    groups: dict[int, np.ndarray]
    draws: np.ndarray
    draw_hash: str


def make_block_draws(frame: pd.DataFrame) -> BootstrapDraws:
    tmp = frame.copy()
    block0 = tmp["ts"].min().normalize()
    tmp["_block_id"] = ((tmp["ts"].dt.normalize() - block0).dt.days // BOOTSTRAP_BLOCK_DAYS).astype(int)
    blocks = sorted(tmp["_block_id"].unique().tolist())
    groups = {block: tmp.index[tmp["_block_id"].eq(block)].to_numpy() for block in blocks}
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, len(blocks), size=(BOOTSTRAP_SAMPLES, len(blocks)))
    return BootstrapDraws(blocks=blocks, groups=groups, draws=draws, draw_hash=hashlib.sha256(draws.tobytes()).hexdigest())


def bootstrap_ci(values: list[float]) -> dict[str, float | None]:
    clean = np.asarray([v for v in values if v is not None and math.isfinite(v)], dtype=float)
    if clean.size == 0:
        return {"ci95_low": None, "ci95_high": None}
    return {"ci95_low": float(np.quantile(clean, 0.025)), "ci95_high": float(np.quantile(clean, 0.975))}


def brier_skill(frame: pd.DataFrame, probability: np.ndarray) -> float | None:
    y = frame[TARGET].astype(int).to_numpy()
    const = np.full(len(y), float(np.mean(y)))
    base = brier_score_loss(y, const)
    if base <= 0:
        return None
    return float(1 - brier_score_loss(y, clip_probability(probability)) / base)


def paired_bootstrap_diff(frame: pd.DataFrame, candidate: str, baseline: str, draws: BootstrapDraws) -> dict[str, Any]:
    auc_diff: list[float] = []
    pr_diff: list[float] = []
    brier_skill_diff: list[float] = []
    top_success_diff: list[float] = []
    top_net_diff: list[float] = []
    cand_col = f"p_{candidate.lower()}_raw"
    base_col = f"p_{baseline.lower()}_raw"
    for draw in draws.draws:
        idx = np.concatenate([draws.groups[draws.blocks[i]] for i in draw])
        sample = frame.loc[idx]
        y = sample[TARGET].astype(int).to_numpy()
        if len(np.unique(y)) < 2:
            continue
        cand_p = sample[cand_col].to_numpy()
        base_p = sample[base_col].to_numpy()
        auc_diff.append(float(roc_auc_score(y, cand_p) - roc_auc_score(y, base_p)))
        pr_diff.append(float(average_precision_score(y, cand_p) - average_precision_score(y, base_p)))
        cand_skill = brier_skill(sample, cand_p)
        base_skill = brier_skill(sample, base_p)
        if cand_skill is not None and base_skill is not None:
            brier_skill_diff.append(float(cand_skill - base_skill))
        cand_dec = P2.decile_codes(cand_p)
        base_dec = P2.decile_codes(base_p)
        cand_top = sample.loc[cand_dec == 10]
        base_top = sample.loc[base_dec == 10]
        top_success_diff.append(float(cand_top[TARGET].mean() - base_top[TARGET].mean()))
        top_net_diff.append(float(cand_top[NET_RETURN].mean() - base_top[NET_RETURN].mean()))
    full_y = frame[TARGET].astype(int).to_numpy()
    cand_p = frame[cand_col].to_numpy()
    base_p = frame[base_col].to_numpy()
    cand_dec = P2.decile_codes(cand_p)
    base_dec = P2.decile_codes(base_p)
    cand_top = frame.loc[cand_dec == 10]
    base_top = frame.loc[base_dec == 10]
    one_sided_p = float((np.sum(np.asarray(auc_diff) <= 0) + 1) / (len(auc_diff) + 1)) if auc_diff else None
    return {
        "candidate": candidate,
        "baseline": baseline,
        "samples": BOOTSTRAP_SAMPLES,
        "block_days": BOOTSTRAP_BLOCK_DAYS,
        "block_count": len(draws.blocks),
        "same_resampling_indices_for_all_models": True,
        "paired_draw_counts_sha256": draws.draw_hash,
        "auc_diff": {
            "point": float(roc_auc_score(full_y, cand_p) - roc_auc_score(full_y, base_p)),
            **bootstrap_ci(auc_diff),
            "one_sided_p": one_sided_p,
        },
        "pr_auc_diff": {
            "point": float(average_precision_score(full_y, cand_p) - average_precision_score(full_y, base_p)),
            **bootstrap_ci(pr_diff),
        },
        "brier_skill_diff": {
            "point": float((brier_skill(frame, cand_p) or 0.0) - (brier_skill(frame, base_p) or 0.0)),
            **bootstrap_ci(brier_skill_diff),
        },
        "top10_success_rate_diff": {
            "point": float(cand_top[TARGET].mean() - base_top[TARGET].mean()),
            **bootstrap_ci(top_success_diff),
        },
        "top10_net_return_mean_diff": {
            "point": float(cand_top[NET_RETURN].mean() - base_top[NET_RETURN].mean()),
            **bootstrap_ci(top_net_diff),
        },
    }


def bh_q_values(p_values: dict[str, float | None]) -> dict[str, float | None]:
    valid = sorted((candidate, p) for candidate, p in p_values.items() if p is not None)
    m = len(valid)
    q: dict[str, float | None] = {candidate: None for candidate in p_values}
    prev = 1.0
    for rank_from_end, (candidate, p) in enumerate(reversed(valid), start=1):
        rank = m - rank_from_end + 1
        value = min(prev, p * m / rank)
        q[candidate] = float(min(value, 1.0))
        prev = value
    return q


def forward_oof_calibration(oof: pd.DataFrame, raw_col: str) -> tuple[np.ndarray, dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
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
        calibration = P2.fit_platt(fit_frame[raw_col].to_numpy(), fit_frame[TARGET].astype(int).to_numpy())
        forward[eval_mask] = P2.apply_calibration(raw[eval_mask], calibration)
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
    final_fit_frame = oof.loc[oof[LABEL_END].lt(CUTOFF)]
    final_calibration = P2.fit_platt(final_fit_frame[raw_col].to_numpy(), final_fit_frame[TARGET].astype(int).to_numpy())
    final_calibration.update(
        {
            "selection_basis": "forward_oof_D2_D3",
            "final_fit_rows": int(len(final_fit_frame)),
            "final_fit_label_end_max": final_fit_frame[LABEL_END].max(),
            "fit_scope": "completed_D1_D3_oof_before_2025_cutoff",
        }
    )
    forward_eval = oof["fold"].isin(fold_names[1:]).to_numpy()
    comparison = {
        "evaluation_folds": fold_names[1:],
        "eval_rows": int(forward_eval.sum()),
        "raw": metric_values(oof.loc[forward_eval], raw[forward_eval]),
        "forward_calibrated": metric_values(oof.loc[forward_eval], forward[forward_eval]),
        "improved_brier_or_log_loss": bool(
            metric_values(oof.loc[forward_eval], forward[forward_eval])["brier"] < metric_values(oof.loc[forward_eval], raw[forward_eval])["brier"]
            or metric_values(oof.loc[forward_eval], forward[forward_eval])["log_loss"] < metric_values(oof.loc[forward_eval], raw[forward_eval])["log_loss"]
        ),
        "d1_probability_policy": "raw_no_prior_oof",
    }
    return forward, final_calibration, audits, comparison


def run_development(frame: pd.DataFrame, feature_spec: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    categorical = feature_spec["categorical_features"]
    metric_rows: list[dict[str, Any]] = []
    coefficient_rows: list[dict[str, Any]] = []
    oof_rows: list[pd.DataFrame] = []
    purge_audit: list[dict[str, Any]] = []

    for fold, start, end in FOLDS:
        train, valid = fold_split(frame, start, end)
        print(f"P3 {fold}: train={len(train)} valid={len(valid)}", flush=True)
        base = valid[
            [
                "asset",
                "side",
                "ts",
                "feature_known_at",
                "entry_ts",
                TARGET,
                LABEL_END,
                NET_RETURN,
                "asset_group",
                "event_year",
                "volatility_state_p0r",
                "listing_age_days",
                "liquidity_rank_pct_p0r",
                "pit_universe_size_p0r",
            ]
        ].copy()
        base["fold"] = fold
        for candidate in CANDIDATES:
            features = candidate_features(feature_spec, candidate)
            p_train, p_valid, detail = fit_logit(train, valid, features, categorical)
            raw_col = f"p_{candidate.lower()}_raw"
            base[raw_col] = p_valid
            train_metric = metric_values(train, p_train)
            valid_metric = metric_values(valid, p_valid)
            gap = None if train_metric["roc_auc"] is None or valid_metric["roc_auc"] is None else train_metric["roc_auc"] - valid_metric["roc_auc"]
            uplift_gap = None
            if train_metric["top_decile_uplift"] is not None and valid_metric["top_decile_uplift"] is not None:
                uplift_gap = train_metric["top_decile_uplift"] - valid_metric["top_decile_uplift"]
            flag = "SEVERE_OVERFIT_WARNING" if gap is not None and gap > 0.10 else ""
            metric_rows.append(metric_row(candidate=candidate, fold=fold, split="training", frame=train, probability=p_train, train_n=len(train), train_label_end_max=train[LABEL_END].max(), probability_type="raw", train_val_auc_gap=gap, train_val_top_uplift_gap=uplift_gap, overfit_flag=flag))
            metric_rows.append(metric_row(candidate=candidate, fold=fold, split="validation", frame=valid, probability=p_valid, train_n=len(train), train_label_end_max=train[LABEL_END].max(), probability_type="raw", train_val_auc_gap=gap, train_val_top_uplift_gap=uplift_gap, overfit_flag=flag))
            incremental_features = set(incremental_block_for_candidate(feature_spec, candidate))
            for coef in detail["coef_rows"]:
                coefficient_rows.append(
                    {
                        "candidate": candidate,
                        "fold": fold,
                        "expanded_feature": coef["expanded_feature"],
                        "base_feature": coef["base_feature"],
                        "coef": coef["coef"],
                        "is_incremental_feature": bool(coef["base_feature"] in incremental_features),
                    }
                )
        oof_rows.append(base)
        purge_audit.append({"fold": fold, "train_n": len(train), "validation_n": len(valid), "train_label_end_max": train[LABEL_END].max(), "validation_start": start, "purge_pass": bool(train[LABEL_END].max() < start)})

    oof = pd.concat(oof_rows, ignore_index=True)
    if oof["ts"].ge(CUTOFF).any() or oof[LABEL_END].ge(CUTOFF).any() or oof["asset"].eq(HYPE_ASSET).any():
        raise RuntimeError("P3 OOF contamination")
    if oof.duplicated(["asset", "ts", "side"]).any():
        raise RuntimeError("P3 OOF duplicate")

    calibration_audit: dict[str, list[dict[str, Any]]] = {}
    calibration_comparison: dict[str, dict[str, Any]] = {}
    for candidate in CANDIDATES:
        raw_col = f"p_{candidate.lower()}_raw"
        forward, final_calibration, audit, comparison = forward_oof_calibration(oof, raw_col)
        cal_col = f"p_{candidate.lower()}_calibrated_forward"
        oof[cal_col] = forward
        calibration_audit[candidate] = audit
        calibration_comparison[candidate] = {"final_calibration": final_calibration, "forward_validation": comparison}
        for fold, _, _ in FOLDS:
            fold_frame = oof.loc[oof["fold"].eq(fold)]
            metric_rows.append(metric_row(candidate=candidate, fold=fold, split="validation", frame=fold_frame, probability=fold_frame[cal_col].to_numpy(), train_n=0, train_label_end_max=None, probability_type="forward_calibrated"))

    metric_df = pd.DataFrame(metric_rows)
    coefficient_df = pd.DataFrame(coefficient_rows)
    candidate_summary: dict[str, dict[str, Any]] = {}
    for candidate in CANDIDATES:
        raw_validation = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["split"].eq("validation")) & (metric_df["probability_type"].eq("raw"))]
        cal_validation = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["split"].eq("validation")) & (metric_df["probability_type"].eq("forward_calibrated"))]
        candidate_summary[candidate] = {
            "fold_auc": [float(x) for x in raw_validation.sort_values("fold")["roc_auc"].tolist()],
            "worst_fold_auc": float(raw_validation["roc_auc"].min()),
            "macro_auc": float(raw_validation["roc_auc"].mean()),
            "macro_pr_auc": float(raw_validation["pr_auc"].mean()),
            "macro_forward_brier": float(cal_validation["brier"].mean()),
            "macro_forward_log_loss": float(cal_validation["log_loss"].mean()),
            "oof_raw": metric_values(oof, oof[f"p_{candidate.lower()}_raw"].to_numpy()),
            "oof_forward_calibrated": metric_values(oof, oof[f"p_{candidate.lower()}_calibrated_forward"].to_numpy()),
            "decile_raw": decile_stats(oof, oof[f"p_{candidate.lower()}_raw"].to_numpy()),
            "calibration": calibration_comparison[candidate],
        }
    development = {
        "candidate_summary": candidate_summary,
        "purge_audit": purge_audit,
        "calibration_audit": calibration_audit,
        "selection_rows": int(len(oof)),
        "selection_data_max_ts": oof["ts"].max(),
        "historical_2025_plus_rows_used_for_selection": 0,
        "hype_rows_used_for_selection": 0,
        "one_pooled_model_only": True,
    }
    return metric_df, oof, coefficient_df, development


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


def stratum_label(frame: pd.DataFrame, kind: str) -> pd.Series:
    if kind == "side":
        return frame["side"].astype(str)
    if kind == "year":
        return frame["event_year"].astype(str)
    if kind == "asset_group":
        return frame["asset_group"].astype(str)
    if kind == "volatility_state":
        return frame["volatility_state_p0r"].fillna("missing").astype(str)
    if kind == "liquidity_quintile":
        return pd.qcut(frame["liquidity_rank_pct_p0r"].rank(method="first"), q=5, labels=["q1_low", "q2", "q3", "q4", "q5_high"]).astype(str)
    if kind == "listing_age":
        return pd.cut(frame["listing_age_days"], bins=[-1, 180, 365, 730, np.inf], labels=["lt_180d", "180_365d", "365_730d", "gt_730d"]).astype(str)
    if kind == "pit_universe_size":
        return pd.cut(frame["pit_universe_size_p0r"], bins=[-1, 19, 49, np.inf], labels=["lt_20", "20_49", "ge_50"]).astype(str)
    raise ValueError(kind)


def stratum_rows(oof: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for kind in ["side", "year", "asset_group", "volatility_state", "liquidity_quintile", "listing_age", "pit_universe_size"]:
        labels = stratum_label(oof, kind)
        tmp = oof.copy()
        tmp["_stratum"] = labels
        for value, group in tmp.groupby("_stratum", observed=True):
            if len(group) < 20:
                continue
            for candidate in CANDIDATES:
                raw_col = f"p_{candidate.lower()}_raw"
                rows.append(metric_row(candidate=candidate, fold="OOF", split="validation", frame=group, probability=group[raw_col].to_numpy(), train_n=0, train_label_end_max=None, probability_type="raw", row_type="stratum", stratum_type=kind, stratum_value=str(value)))
    return rows


def fixed_threshold_results(oof: pd.DataFrame, candidate: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cal_col = f"p_{candidate.lower()}_calibrated_forward"
    for fold_index, (fold, start, _) in enumerate(FOLDS):
        if fold_index == 0:
            continue
        prior_folds = [name for name, _, _ in FOLDS[:fold_index]]
        prior = oof.loc[oof["fold"].isin(prior_folds) & oof[LABEL_END].lt(start)]
        current = oof.loc[oof["fold"].eq(fold)]
        threshold = float(np.quantile(prior[cal_col], 0.90))
        chosen = current.loc[current[cal_col] >= threshold]
        out.append(
            {
                "candidate": candidate,
                "fold": fold,
                "threshold_source_folds": prior_folds,
                "threshold": threshold,
                "n": int(len(chosen)),
                "success_rate": float(chosen[TARGET].mean()) if len(chosen) else None,
                "net_return_mean": float(chosen[NET_RETURN].mean()) if len(chosen) else None,
                "net_return_median": float(chosen[NET_RETURN].median()) if len(chosen) else None,
            }
        )
    return out


def liquidity_special_report(oof: pd.DataFrame, coef_df: pd.DataFrame, draws: BootstrapDraws) -> dict[str, Any]:
    labels = stratum_label(oof, "liquidity_quintile")
    tmp = oof.copy()
    tmp["liquidity_quintile"] = labels
    quintiles: dict[str, Any] = {}
    for value, group in tmp.groupby("liquidity_quintile", observed=True):
        q = {
            "n": int(len(group)),
            "success_rate": float(group[TARGET].mean()),
            "net_return_mean": float(group[NET_RETURN].mean()),
            "net_return_median": float(group[NET_RETURN].median()),
            "b0_auc": float(roc_auc_score(group[TARGET], group["p_b0_p2_f1_logit_raw"])) if group[TARGET].nunique() >= 2 else None,
            "b1_auc": float(roc_auc_score(group[TARGET], group["p_b1_liquidity_logit_raw"])) if group[TARGET].nunique() >= 2 else None,
        }
        q["b1_minus_b0_auc"] = None if q["b0_auc"] is None or q["b1_auc"] is None else float(q["b1_auc"] - q["b0_auc"])
        side_rates = {}
        for side, side_group in group.groupby("side"):
            side_rates[str(side)] = {"n": int(len(side_group)), "success_rate": float(side_group[TARGET].mean())}
        year_rates = {}
        for year, year_group in group.groupby("event_year"):
            year_rates[str(year)] = {"n": int(len(year_group)), "success_rate": float(year_group[TARGET].mean())}
        q["side_success_rate"] = side_rates
        q["year_success_rate"] = year_rates
        quintiles[str(value)] = q

    high_low_diffs: list[float] = []
    high_low_net_diffs: list[float] = []
    for draw in draws.draws:
        idx = np.concatenate([draws.groups[draws.blocks[i]] for i in draw])
        sample = tmp.loc[idx]
        high = sample.loc[sample["liquidity_quintile"].eq("q5_high")]
        low = sample.loc[sample["liquidity_quintile"].eq("q1_low")]
        if len(high) and len(low):
            high_low_diffs.append(float(high[TARGET].mean() - low[TARGET].mean()))
            high_low_net_diffs.append(float(high[NET_RETURN].mean() - low[NET_RETURN].mean()))

    rank_coefs = coef_df.loc[(coef_df["candidate"].eq("B1_LIQUIDITY_LOGIT")) & (coef_df["base_feature"].eq("liquidity_rank_pct_p0r"))]
    signs = [int(np.sign(v)) for v in rank_coefs.sort_values("fold")["coef"].tolist()]
    return {
        "liquidity_rank_definition": "同日 PIT 可交易池内 30 日 quote volume 排名；流动性/交易额代理，不是真实市值。",
        "p2_relative_volume_note": "P2 B0 已含 volume_to_7d/30d 与 quote_volume_to_7d/30d，但不含绝对流动性排名。",
        "quintiles": quintiles,
        "q5_minus_q1_success_rate": {
            "point": float(tmp.loc[tmp["liquidity_quintile"].eq("q5_high"), TARGET].mean() - tmp.loc[tmp["liquidity_quintile"].eq("q1_low"), TARGET].mean()),
            **bootstrap_ci(high_low_diffs),
        },
        "q5_minus_q1_net_return_mean": {
            "point": float(tmp.loc[tmp["liquidity_quintile"].eq("q5_high"), NET_RETURN].mean() - tmp.loc[tmp["liquidity_quintile"].eq("q1_low"), NET_RETURN].mean()),
            **bootstrap_ci(high_low_net_diffs),
        },
        "liquidity_rank_coef_by_fold": {row.fold: float(row.coef) for row in rank_coefs.itertuples()},
        "liquidity_rank_coef_same_sign": bool(len(set(signs)) == 1),
    }


def summarize_incremental(oof: pd.DataFrame, metric_df: pd.DataFrame, coef_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    draws = make_block_draws(oof)
    non_overlap = non_overlap_sample(oof)
    comparisons: list[dict[str, Any]] = []
    boot_by_candidate: dict[str, Any] = {}
    p_values: dict[str, float | None] = {}
    for candidate in INCREMENTAL_CANDIDATES:
        boot = paired_bootstrap_diff(oof, candidate, "B0_P2_F1_LOGIT", draws)
        boot_by_candidate[candidate] = boot
        p_values[candidate] = boot["auc_diff"]["one_sided_p"]
    q_values = bh_q_values(p_values)

    for candidate in INCREMENTAL_CANDIDATES:
        cand_col = f"p_{candidate.lower()}_raw"
        base_col = "p_b0_p2_f1_logit_raw"
        boot = boot_by_candidate[candidate]
        raw_val = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["split"].eq("validation")) & (metric_df["probability_type"].eq("raw"))].sort_values("fold")
        base_val = metric_df.loc[(metric_df["candidate"].eq("B0_P2_F1_LOGIT")) & (metric_df["split"].eq("validation")) & (metric_df["probability_type"].eq("raw"))].sort_values("fold")
        fold_deltas = (raw_val["roc_auc"].to_numpy() - base_val["roc_auc"].to_numpy()).tolist()
        fold_improve_count = int(sum(delta > 0 for delta in fold_deltas))
        non_overlap_auc = float(roc_auc_score(non_overlap[TARGET], non_overlap[cand_col])) if non_overlap[TARGET].nunique() >= 2 else None
        non_overlap_base_auc = float(roc_auc_score(non_overlap[TARGET], non_overlap[base_col])) if non_overlap[TARGET].nunique() >= 2 else None
        side_deltas = {}
        for side, group in oof.groupby("side", sort=True):
            side_deltas[side] = float(roc_auc_score(group[TARGET], group[cand_col]) - roc_auc_score(group[TARGET], group[base_col]))
        cand_top = decile_stats(oof, oof[cand_col].to_numpy())
        base_top = decile_stats(oof, oof[base_col].to_numpy())
        top_success_worse = cand_top["top_success_rate"] is not None and base_top["top_success_rate"] is not None and cand_top["top_success_rate"] < base_top["top_success_rate"]
        top_net_worse = cand_top["top_net_return_mean"] is not None and base_top["top_net_return_mean"] is not None and cand_top["top_net_return_mean"] < base_top["top_net_return_mean"]
        confirmed = (
            boot["auc_diff"]["point"] > 0
            and boot["auc_diff"]["ci95_low"] is not None
            and boot["auc_diff"]["ci95_low"] > 0
            and q_values[candidate] is not None
            and q_values[candidate] < 0.10
            and fold_improve_count >= 2
            and min(fold_deltas) >= -0.005
            and non_overlap_auc is not None
            and non_overlap_base_auc is not None
            and non_overlap_auc - non_overlap_base_auc > 0
            and min(side_deltas.values()) >= -0.01
            and not (top_success_worse and top_net_worse)
        )
        suggestive = boot["auc_diff"]["point"] > 0 and fold_improve_count >= 2 and not confirmed
        decision = "INCREMENTAL_BLOCK_CONFIRMED" if confirmed else "SUGGESTIVE_INCREMENT_NOT_CONFIRMED" if suggestive else "NO_INCREMENT_BEYOND_P2"
        block_features = incremental_block_for_candidate(load_json(FEATURE_SPEC_PATH), candidate)
        inc_coefs = coef_df.loc[(coef_df["candidate"].eq(candidate)) & (coef_df["base_feature"].isin(block_features))]
        sign_stability = {}
        for base_feature, group in inc_coefs.groupby("base_feature", sort=True):
            signs = [int(np.sign(v)) for v in group.sort_values("fold")["coef"].tolist()]
            sign_stability[base_feature] = {
                "fold_coefs": {row.fold: float(row.coef) for row in group.itertuples()},
                "same_nonzero_sign": bool(0 not in signs and len(set(signs)) == 1),
            }
        comparisons.append(
            {
                "candidate": candidate,
                "baseline": "B0_P2_F1_LOGIT",
                "decision": decision,
                "auc_diff": boot["auc_diff"]["point"],
                "auc_diff_ci95_low": boot["auc_diff"]["ci95_low"],
                "auc_diff_ci95_high": boot["auc_diff"]["ci95_high"],
                "auc_diff_p": boot["auc_diff"]["one_sided_p"],
                "auc_diff_bh_q": q_values[candidate],
                "pr_auc_diff": boot["pr_auc_diff"]["point"],
                "brier_skill_diff": boot["brier_skill_diff"]["point"],
                "top10_success_rate_diff": boot["top10_success_rate_diff"]["point"],
                "top10_net_return_mean_diff": boot["top10_net_return_mean_diff"]["point"],
                "fold_auc_deltas_json": json.dumps([float(x) for x in fold_deltas], ensure_ascii=False),
                "fold_improve_count": fold_improve_count,
                "worst_fold_delta": float(min(fold_deltas)),
                "non_overlap_auc": non_overlap_auc,
                "non_overlap_auc_diff": None if non_overlap_auc is None or non_overlap_base_auc is None else float(non_overlap_auc - non_overlap_base_auc),
                "long_auc_diff": side_deltas.get("long"),
                "short_auc_diff": side_deltas.get("short"),
                "top10_success_rate": cand_top["top_success_rate"],
                "top10_net_return_mean": cand_top["top_net_return_mean"],
                "bootstrap_samples": BOOTSTRAP_SAMPLES,
                "bootstrap_draw_hash": draws.draw_hash,
                "incremental_coefficient_sign_stability_json": json.dumps(json_ready(sign_stability), ensure_ascii=False, sort_keys=True),
            }
        )

    comparison_df = pd.DataFrame(comparisons)
    if (comparison_df["decision"] == "INCREMENTAL_BLOCK_CONFIRMED").any():
        global_verdict = "ONE_OR_MORE_CONTEXT_BLOCKS_CONFIRMED"
    elif (comparison_df["decision"] == "SUGGESTIVE_INCREMENT_NOT_CONFIRMED").any():
        global_verdict = "SUGGESTIVE_CONTEXT_INCREMENT_ONLY"
    else:
        global_verdict = "NO_CONTEXT_INCREMENT_BEYOND_P2"
    stability = {
        "bootstrap": {
            "samples": BOOTSTRAP_SAMPLES,
            "block_days": BOOTSTRAP_BLOCK_DAYS,
            "block_count": len(draws.blocks),
            "same_resampling_indices_for_all_models": True,
            "paired_draw_counts_sha256": draws.draw_hash,
        },
        "block_decisions": {row.candidate: row.decision for row in comparison_df.itertuples()},
        "global_verdict": global_verdict,
        "non_overlap_n": int(len(non_overlap)),
        "liquidity_special": liquidity_special_report(oof, coef_df, draws),
    }
    return comparison_df, stability


def final_refit_metrics(frame: pd.DataFrame, feature_spec: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for candidate in CANDIDATES:
        p_train, _, _ = fit_logit(frame, frame, candidate_features(feature_spec, candidate), feature_spec["categorical_features"])
        out[candidate] = {
            "train_rows": int(len(frame)),
            "train_max_ts": frame["ts"].max(),
            "train_max_label_end": frame[LABEL_END].max(),
            "train_metrics_raw": metric_values(frame, p_train),
        }
    return out


def build_top10_by_year(oof: pd.DataFrame) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for candidate in CANDIDATES:
        raw_col = f"p_{candidate.lower()}_raw"
        out[candidate] = {}
        for year, group in oof.groupby("event_year", sort=True):
            out[candidate][str(year)] = decile_stats(group, group[raw_col].to_numpy())
    return out


def build_forward_probability_reports(oof: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    d2d3 = oof.loc[oof["fold"].isin(["D2", "D3"])].copy()
    for candidate in CANDIDATES:
        cal_col = f"p_{candidate.lower()}_calibrated_forward"
        out[candidate] = {
            "d2_d3_forward_calibrated_top10": decile_stats(d2d3, d2d3[cal_col].to_numpy()),
            "fixed_threshold_from_prior_oof": fixed_threshold_results(oof, candidate),
        }
    return out


def fmt(value: Any, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "NA"
    return f"{float(value):.{digits}f}"


def pct(value: Any) -> str:
    if value is None:
        return "NA"
    return f"{100 * float(value):.2f}%"


def write_reports(summary: dict[str, Any], metric_df: pd.DataFrame, comparison_df: pd.DataFrame) -> None:
    candidate_summary = summary["development"]["candidate_summary"]
    lines = [
        "# BIN-1D-MA7-CTP P3：Independent Context Feature Block Audit",
        "",
        f"> {summary['generated_at_utc']}。状态：`{STATUS}`。",
        "> P3 只使用 2025 年前且 20 日标签完整结束的真实 MA7 穿越事件；没有读取 HYPE 或 2025+ 事件做训练/预测。",
        "> 本轮不是策略，不生成仓位、账户权益、年化收益、Sharpe 或 live-ready 产物。",
        "",
        "## 裁决",
        "",
        f"**{summary['decision']['global_verdict']}** / `{STATUS}`",
        "",
        f"- 严格样本：`{summary['strict_event_audit']['n']}` 行，资产 `{summary['strict_event_audit']['assets']}`，多头 `{summary['strict_event_audit']['long']}`，空头 `{summary['strict_event_audit']['short']}`。",
        f"- HYPE：输入 `{summary['hype_isolation']['input_rows']}`，严格事件 `{summary['hype_isolation']['event_rows']}`，OOF `{summary['hype_isolation']['oof_rows']}`，模型卡 `{summary['hype_isolation']['model_card_rows']}`。",
        f"- 2025+：事件读取 `{summary['input_integrity']['post_2025_event_rows_read']}`，预测写出 `{summary['input_integrity']['post_2025_prediction_rows_written']}`。",
        "",
        "## 数据审计",
        "",
        f"- P0R manifest artifact 哈希全部匹配：`{summary['input_integrity']['p0r_artifact_hashes_all_match']}`；HYPER 输入行 `{summary['hyper_preservation']['input_rows']}`，严格样本行 `{summary['hyper_preservation']['event_rows']}`。",
        f"- 原始 pre-2025 MA7 事件：`{summary['raw_event_audit_without_labels']['n']}`；严格样本日期：`{summary['strict_event_audit']['min_ts']}` 至 `{summary['strict_event_audit']['max_ts']}`。",
        "- `feature_known_at < entry_ts`、非穿越为 0、重复键为 0、空标签为 0、不完整 20 日未来路径为 0 均通过。",
        "",
        "## 候选总体",
        "",
        "| Candidate | Worst fold AUC | Macro AUC | OOF raw AUC | OOF PR-AUC | OOF forward Brier | Top10 成功率 | Top10 净收益均值 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for candidate, stats in candidate_summary.items():
        lines.append(
            f"| {candidate} | {fmt(stats['worst_fold_auc'])} | {fmt(stats['macro_auc'])} | {fmt(stats['oof_raw']['roc_auc'])} | {fmt(stats['oof_raw']['pr_auc'])} | "
            f"{fmt(stats['oof_forward_calibrated']['brier'])} | {pct(stats['decile_raw']['top_success_rate'])} | {fmt(stats['decile_raw']['top_net_return_mean'])} |"
        )
    lines.extend(
        [
            "",
            "## D1/D2/D3 训练与验证对照",
            "",
            "| Candidate | Fold | Train n | Train AUC | Train PR-AUC | Val n | Val AUC | Val PR-AUC | Val forward Brier | Val forward logloss | AUC 差 | Uplift 差 | 标记 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for candidate in CANDIDATES:
        for fold in ["D1", "D2", "D3"]:
            tr = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["fold"].eq(fold)) & (metric_df["split"].eq("training")) & (metric_df["probability_type"].eq("raw"))].iloc[0]
            va_raw = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["fold"].eq(fold)) & (metric_df["split"].eq("validation")) & (metric_df["probability_type"].eq("raw"))].iloc[0]
            va_cal = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["fold"].eq(fold)) & (metric_df["split"].eq("validation")) & (metric_df["probability_type"].eq("forward_calibrated"))].iloc[0]
            lines.append(
                f"| {candidate} | {fold} | {int(tr.eval_n)} | {fmt(tr.roc_auc)} | {fmt(tr.pr_auc)} | {int(va_raw.eval_n)} | {fmt(va_raw.roc_auc)} | {fmt(va_raw.pr_auc)} | "
                f"{fmt(va_cal.brier)} | {fmt(va_cal.log_loss)} | {fmt(va_raw.train_val_auc_gap)} | {fmt(va_raw.train_val_top_uplift_gap)} | {va_raw.overfit_flag or ''} |"
            )
    lines.extend(
        [
            "",
            "## 单块增量裁决",
            "",
            "| Block | Decision | AUC diff | 95% CI | BH q | Folds improved | Worst fold delta | Non-overlap diff | Long diff | Short diff | Top10 success diff | Top10 net diff |",
            "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in comparison_df.itertuples():
        lines.append(
            f"| {row.candidate} | `{row.decision}` | {fmt(row.auc_diff)} | [{fmt(row.auc_diff_ci95_low)}, {fmt(row.auc_diff_ci95_high)}] | {fmt(row.auc_diff_bh_q)} | "
            f"{row.fold_improve_count}/3 | {fmt(row.worst_fold_delta)} | {fmt(row.non_overlap_auc_diff)} | {fmt(row.long_auc_diff)} | {fmt(row.short_auc_diff)} | "
            f"{fmt(row.top10_success_rate_diff)} | {fmt(row.top10_net_return_mean_diff)} |"
        )
    liq = summary["liquidity_special"]
    lines.extend(
        [
            "",
            "## B1 流动性专项",
            "",
            f"- 定义：{liq['liquidity_rank_definition']}",
            f"- P2 对照：{liq['p2_relative_volume_note']}",
            f"- 最高 20% - 最低 20% 成功率差：`{fmt(liq['q5_minus_q1_success_rate']['point'])}`，95% CI `[{fmt(liq['q5_minus_q1_success_rate']['ci95_low'])}, {fmt(liq['q5_minus_q1_success_rate']['ci95_high'])}]`；净收益均值差 `{fmt(liq['q5_minus_q1_net_return_mean']['point'])}`。",
            f"- `liquidity_rank_pct_p0r` 三折系数同号：`{liq['liquidity_rank_coef_same_sign']}`；系数：{', '.join(f'{k}={fmt(v)}' for k, v in liq['liquidity_rank_coef_by_fold'].items())}。",
            "",
            "| Liquidity quintile | n | 成功率 | 净收益均值 | B0 AUC | B1 AUC | B1-B0 AUC |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for value, item in liq["quintiles"].items():
        lines.append(f"| {value} | {item['n']} | {pct(item['success_rate'])} | {fmt(item['net_return_mean'])} | {fmt(item['b0_auc'])} | {fmt(item['b1_auc'])} | {fmt(item['b1_minus_b0_auc'])} |")
    lines.extend(
        [
            "",
            "## 前向校准与阈值",
            "",
            f"- D1 无更早 OOF，保持 raw；D2/D3 只用更早且标签已完成的 OOF 拟合 Platt。所有候选 raw 与 forward-calibrated probability 分列保存。",
            f"- B0 D2-D3 前向校准 Brier：raw `{fmt(candidate_summary['B0_P2_F1_LOGIT']['calibration']['forward_validation']['raw']['brier'])}`，calibrated `{fmt(candidate_summary['B0_P2_F1_LOGIT']['calibration']['forward_validation']['forward_calibrated']['brier'])}`。",
            "",
            "## 边界",
            "",
            "- 本轮没有 2025+ historical test；2025+ 对本家族已是 hypothesis-revealed historical period，本轮按合同完全不使用。",
            "- 没有读取 HYPE、没有 HYPE reveal，没有训练退出/持仓/反手模型，没有策略产物，not live-ready。",
        ]
    )
    atomic_write_text(REPORT_PATH, "\n".join(lines) + "\n")

    audit_lines = [
        "# BIN-1D-MA7-CTP P3 建模审计",
        "",
        f"状态：`{STATUS}`。裁决：`{summary['decision']['global_verdict']}`。",
        "",
        "## 输入与隔离",
        "",
        f"- P0R manifest SHA256：`{summary['input_integrity']['p0r_manifest_sha256']}`；artifact 哈希全部匹配：`{summary['input_integrity']['p0r_artifact_hashes_all_match']}`。",
        f"- P2 feature spec SHA256：`{summary['input_integrity']['p2_feature_spec_sha256']}`；B0 精确复用 P2 F1：`{summary['b0_exactly_reuses_p2_f1']}`。",
        f"- HYPE 输入/事件/OOF/模型卡：`{summary['hype_isolation']['input_rows']}/{summary['hype_isolation']['event_rows']}/{summary['hype_isolation']['oof_rows']}/{summary['hype_isolation']['model_card_rows']}`。",
        f"- HYPER 输入/严格事件/OOF：`{summary['hyper_preservation']['input_rows']}/{summary['hyper_preservation']['event_rows']}/{summary['hyper_preservation']['oof_rows']}`。",
        f"- 2025+ 事件读取/预测写出：`{summary['input_integrity']['post_2025_event_rows_read']}/{summary['input_integrity']['post_2025_prediction_rows_written']}`。",
        "",
        "## 样本与时点",
        "",
        f"- 原始 pre-2025 MA7 事件 `{summary['raw_event_audit_without_labels']['n']}`；严格样本 `{summary['strict_event_audit']['n']}`。",
        "- 所有训练/验证行满足 `probe_raw_ma7_cross_dir=true`、`model_eligible_entry_p0r=true`、`label_end_ts_20d < 2025-01-01`。",
        "- `asset+ts` 与 `asset+ts+side` 重复键为 0；`feature_known_at < entry_ts` 通过；T1 字段经 `asset+side` 前一有效日 shift 审计通过。",
        "",
        "## 模型与校准",
        "",
        "- 所有候选使用同一严格样本行；只训练 pooled Logistic Regression，不训练 long/short heads，不训练 LightGBM。",
        "- 数值中位数、类别 one-hot 和 StandardScaler 均只在训练折拟合。",
        "- paired bootstrap 使用完全相同的 28 日日期块重采样索引。",
        f"- bootstrap draw hash：`{summary['stability']['bootstrap']['paired_draw_counts_sha256']}`。",
        "",
        "## 禁止产物",
        "",
        "- 无 HYPE、无 2025+、无策略、无仓位、无权益曲线、无 live spec、无 live-ready。",
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
            "alias": "BIN-1D-MA7-CTP",
            "experiment": "P3 Independent Context Feature Block Audit",
            "generated_at_utc": datetime.now(UTC),
            "status": STATUS,
            "holdout_read": False,
            "hype_asset_excluded": HYPE_ASSET,
            "hype_reveal_executed": False,
            "post_2025_event_rows_read": 0,
            "post_2025_predictions_written": 0,
            "input_lineage": {
                "p0r_manifest_path": str(P0R_MANIFEST_PATH.relative_to(ROOT)),
                "p0r_manifest_sha256": input_audit["p0r_manifest_sha256"],
                "p0r_feature_blocks_sha256": input_audit["p0r_feature_blocks_sha256"],
                "p2_feature_spec_path": str(P2_FEATURE_SPEC_PATH.relative_to(ROOT)),
                "p2_feature_spec_sha256": input_audit["p2_feature_spec_sha256"],
                "p2_summary_sha256": input_audit["p2_summary_sha256"],
                "p2_model_card_sha256": input_audit["p2_model_card_sha256"],
                "p2_script_sha256": input_audit["p2_script_sha256"],
                "contract_sha256": sha256_file(SPEC_PATH),
                "feature_spec_sha256": sha256_file(FEATURE_SPEC_PATH),
            },
            "artifacts": artifacts,
        },
    )


def main() -> None:
    args = parse_args()
    if not args.run:
        raise SystemExit("Pass --run to execute P3.")
    ensure_output_policy(args.force)
    feature_spec, p2_feature_spec, input_audit = validate_inputs()
    raw_event_audit = count_events_without_labels()
    atomic_write_json(
        CONTRACT_LOCK_PATH,
        {
            "status": "FROZEN_BEFORE_P3_LABEL_READ",
            "generated_at_utc": datetime.now(UTC),
            "contract_sha256": sha256_file(SPEC_PATH),
            "feature_spec_sha256": sha256_file(FEATURE_SPEC_PATH),
            "p2_feature_spec_sha256": input_audit["p2_feature_spec_sha256"],
            "event_filter_audit_without_labels": raw_event_audit,
        },
    )
    print("P3 contract lock written; loading labels after lock.", flush=True)
    frame = load_strict_event_panel(feature_spec)
    metric_df, oof, coef_df, development = run_development(frame, feature_spec)
    comparison_df, stability = summarize_incremental(oof, metric_df, coef_df)
    stratum_metric_df = pd.DataFrame(stratum_rows(oof))
    if not stratum_metric_df.empty:
        metric_df = pd.concat([metric_df, stratum_metric_df], ignore_index=True)
    final_metrics = final_refit_metrics(frame, feature_spec)
    top10_by_year = build_top10_by_year(oof)
    forward_probability = build_forward_probability_reports(oof)
    strict_audit = {
        "n": int(len(frame)),
        "assets": int(frame["asset"].nunique()),
        "long": int(frame["side"].eq("long").sum()),
        "short": int(frame["side"].eq("short").sum()),
        "hype": int(frame["asset"].eq(HYPE_ASSET).sum()),
        "hyper": int(frame["asset"].eq(HYPER_ASSET).sum()),
        "min_ts": frame["ts"].min(),
        "max_ts": frame["ts"].max(),
        "max_label_end": frame[LABEL_END].max(),
        "non_cross": int((~frame["probe_raw_ma7_cross_dir"]).sum()),
        "duplicate_asset_ts": int(frame.duplicated(["asset", "ts"]).sum()),
        "duplicate_asset_ts_side": int(frame.duplicated(["asset", "ts", "side"]).sum()),
        "null_target": int(frame[TARGET].isna().sum()),
        "incomplete_20d_future_path": int((~frame["future_path_complete_20d"]).sum()),
        "feature_known_at_ge_entry_ts": int((frame["feature_known_at"] >= frame["entry_ts"]).sum()),
        "positive_rate": float(frame[TARGET].mean()),
    }
    summary: dict[str, Any] = {
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "alias": "BIN-1D-MA7-CTP",
        "experiment": "P3 Independent Context Feature Block Audit",
        "generated_at_utc": datetime.now(UTC),
        "status": STATUS,
        "objective_ma7_cross_only": True,
        "one_pooled_model_only": True,
        "independent_long_short_heads_trained": 0,
        "no_strategy_no_portfolio_no_live_artifact": True,
        "input_integrity": input_audit,
        "raw_event_audit_without_labels": raw_event_audit,
        "strict_event_audit": strict_audit,
        "b0_exactly_reuses_p2_f1": feature_spec["feature_blocks"]["B0_P2_F1"] == scheme_features(p2_feature_spec, "F1_MA7_PATH"),
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
            "event_rows": int(frame["asset"].eq(HYPER_ASSET).sum()),
            "oof_rows": int(oof["asset"].eq(HYPER_ASSET).sum()),
        },
        "development": development,
        "incremental_comparisons": comparison_df.to_dict(orient="records"),
        "stability": stability,
        "liquidity_special": stability["liquidity_special"],
        "top10_by_validation_year_raw": top10_by_year,
        "forward_probability_reports": forward_probability,
        "final_refit_pre_2025": final_metrics,
        "decision": {
            "global_verdict": stability["global_verdict"],
            "block_decisions": stability["block_decisions"],
            "status": STATUS,
            "not_live_ready": True,
            "no_2025_plus_historical_test": True,
        },
    }
    model_card = {
        "family": summary["family"],
        "experiment": summary["experiment"],
        "model_role": "pooled direction-aligned MA7-cross context block audit",
        "candidates": {candidate: candidate_features(feature_spec, candidate) for candidate in CANDIDATES},
        "feature_spec_sha256": sha256_file(FEATURE_SPEC_PATH),
        "contract_sha256": sha256_file(SPEC_PATH),
        "seed": SEED,
        "status": STATUS,
        "hype_rows": 0,
        "hype_reveal_executed": False,
        "post_2025_event_rows_read": 0,
        "post_2025_predictions_written": 0,
        "not_live_ready": True,
        "prohibited_uses": ["position sizing", "account backtest", "live trading", "long/short head deployment", "continuation or exit modeling", "HYPE reveal"],
    }
    atomic_write_parquet(FOLD_METRICS_PATH, metric_df)
    atomic_write_parquet(OOF_PREDICTIONS_PATH, oof)
    atomic_write_parquet(INCREMENTAL_COMPARISONS_PATH, comparison_df)
    atomic_write_json(SUMMARY_PATH, summary)
    atomic_write_json(MODEL_CARD_PATH, model_card)
    write_reports(summary, metric_df, comparison_df)
    build_manifest(
        [
            SPEC_PATH,
            FEATURE_SPEC_PATH,
            Path(__file__).resolve(),
            TEST_PATH,
            CONTRACT_LOCK_PATH,
            FOLD_METRICS_PATH,
            OOF_PREDICTIONS_PATH,
            INCREMENTAL_COMPARISONS_PATH,
            SUMMARY_PATH,
            MODEL_CARD_PATH,
            REPORT_PATH,
            AUDIT_PATH,
        ],
        input_audit,
    )
    print(f"P3 complete: {summary['decision']['global_verdict']}", flush=True)


if __name__ == "__main__":
    main()
