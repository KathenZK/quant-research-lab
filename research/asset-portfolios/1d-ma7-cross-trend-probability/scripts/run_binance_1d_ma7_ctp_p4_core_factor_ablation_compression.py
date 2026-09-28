#!/usr/bin/env python3
"""Run BIN-1D-MA7-CTP P4 core factor ablation and compression audit."""

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

SPEC_PATH = FAMILY_DIR / "specs/binance-1d-ma7-ctp-p4-core-factor-ablation-compression-contract-2026-09-02.md"
SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py"
TEST_PATH = ROOT / "tests/test_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py"

P2_SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p2_pooled_minimal_stability.py"
P3R_SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p3r_time_boundary_repair_context_feature_block_audit.py"
P2_FEATURE_SPEC_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_feature_spec.json"
P2_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_summary.json"
P2_MODEL_CARD_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_model_card.json"
P3R_FEATURE_SPEC_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_feature_spec.json"
P3R_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_summary.json"
P3R_MODEL_CARD_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_model_card.json"

P0R_FEATURE_BLOCKS_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_feature_blocks.json"
P0R_MANIFEST_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_manifest.json"
PANEL_DIR = CATL_DIR / "artifacts/p0r_donor_directional_modeling_panel"
PANEL_GLOB = PANEL_DIR / "**/*.parquet"

PREFIX = "binance_1d_ma7_ctp_p4_"
FACTOR_GROUP_SPEC_PATH = ARTIFACT_DIR / f"{PREFIX}factor_group_spec.json"
CONTRACT_LOCK_PATH = ARTIFACT_DIR / f"{PREFIX}contract_lock.json"
FOLD_METRICS_PATH = ARTIFACT_DIR / f"{PREFIX}fold_metrics.parquet"
OOF_PREDICTIONS_PATH = ARTIFACT_DIR / f"{PREFIX}oof_predictions.parquet"
ABLATION_COMPARISONS_PATH = ARTIFACT_DIR / f"{PREFIX}ablation_comparisons.parquet"
ONLY_GROUP_METRICS_PATH = ARTIFACT_DIR / f"{PREFIX}only_group_metrics.parquet"
ASSET_HOLDOUT_METRICS_PATH = ARTIFACT_DIR / f"{PREFIX}asset_holdout_metrics.parquet"
DECILE_METRICS_PATH = ARTIFACT_DIR / f"{PREFIX}decile_metrics.parquet"
COEFFICIENT_STABILITY_PATH = ARTIFACT_DIR / f"{PREFIX}coefficient_stability.parquet"
MODEL_CARD_PATH = ARTIFACT_DIR / f"{PREFIX}model_card.json"
SUMMARY_PATH = ARTIFACT_DIR / f"{PREFIX}summary.json"
MANIFEST_PATH = ARTIFACT_DIR / f"{PREFIX}manifest.json"
REPORT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p4-core-factor-ablation-compression-2026-09-02.md"
AUDIT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p4-modeling-audit-2026-09-02.md"

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
EXPECTED_STRICT_LONG = 26237
EXPECTED_STRICT_SHORT = 26326
EXPECTED_STRICT_MIN_TS = pd.Timestamp("2019-11-27T00:00:00Z")
EXPECTED_STRICT_MAX_TS = pd.Timestamp("2024-12-10T00:00:00Z")
EXPECTED_MAX_LABEL_END = pd.Timestamp("2024-12-31T00:00:00Z")

FOLDS = (
    ("D1", pd.Timestamp("2022-01-01T00:00:00Z"), pd.Timestamp("2023-01-01T00:00:00Z")),
    ("D2", pd.Timestamp("2023-01-01T00:00:00Z"), pd.Timestamp("2024-01-01T00:00:00Z")),
    ("D3", pd.Timestamp("2024-01-01T00:00:00Z"), CUTOFF),
)

TRADFI_BASE_SYMBOLS = {
    "AAPL",
    "AMZN",
    "COIN",
    "CRCL",
    "GOOGL",
    "HOOD",
    "META",
    "MSFT",
    "MSTR",
    "NVDA",
    "PLTR",
    "TSLA",
    "SPX",
    "SPY",
    "QQQ",
    "TSM",
    "UBER",
    "XAU",
    "XAG",
    "XPD",
    "XPT",
}

FACTOR_GROUPS: dict[str, list[str]] = {
    "G1_T1_MA7_STATE": [
        "t1_dir_close_ma7_dist_atr",
        "t1_dir_ma7_slope_1d_atr",
        "t1_dir_ma7_slope_3d_atr",
        "t1_dir_ma7_slope_5d_atr",
        "t1_dir_ma7_slope_change_3d",
        "t1_dir_ma7_slope_accel_5d",
        "t1_days_since_ma7_cross",
        "t1_ma7_cross_count_7d",
        "t1_ma7_cross_count_14d",
        "t1_dir_price_side_ma7",
        "t1_dir_favorable_run_days",
        "t1_dir_opposite_run_days",
    ],
    "G2_EVENT_GEOMETRY": [
        "dir_close_ma7_dist_atr",
        "dir_ma7_slope_1d_atr",
        "dir_ma7_slope_3d_atr",
        "dir_ma7_slope_5d_atr",
        "dir_ma7_slope_change_3d",
        "dir_ma7_slope_accel_5d",
        "large_cross_degree_atr",
        "dir_ret_1d",
        "daily_range_atr",
        "body_atr",
        "dir_close_location",
        "dir_favorable_wick_atr",
        "dir_adverse_wick_atr",
    ],
    "G3_VOLATILITY_STATE": [
        "atr7_pct",
        "atr14_pct",
        "atr30_pct",
        "atr14_to_atr30",
        "atr7_to_atr30",
        "t1_atr7_pct",
        "t1_atr14_pct",
        "t1_atr30_pct",
        "t1_atr14_to_atr30",
        "t1_atr7_to_atr30",
        "t1_volatility_state_p0r",
    ],
    "G4_VOLUME_ACTIVITY": [
        "volume_to_7d",
        "quote_volume_to_7d",
        "volume_to_30d",
        "quote_volume_to_30d",
        "volume_change_1d",
    ],
    "G5_T1_MOMENTUM_LOCATION": [
        "t1_dir_ret_1d",
        "t1_dir_ret_3d",
        "t1_dir_ret_7d",
        "t1_dir_ret_14d",
        "t1_dir_ret_30d",
        "t1_dir_ret_60d",
        "t1_dir_range_pos_3d",
        "t1_dir_range_pos_7d",
        "t1_dir_range_pos_14d",
        "t1_dir_range_pos_30d",
        "t1_dir_range_pos_60d",
        "t1_dir_distance_to_favorable_extreme_3d_atr",
        "t1_dir_distance_to_favorable_extreme_7d_atr",
        "t1_dir_distance_to_favorable_extreme_14d_atr",
        "t1_dir_distance_to_favorable_extreme_30d_atr",
        "t1_dir_distance_to_favorable_extreme_60d_atr",
        "t1_dir_distance_from_adverse_extreme_3d_atr",
        "t1_dir_distance_from_adverse_extreme_7d_atr",
        "t1_dir_distance_from_adverse_extreme_14d_atr",
        "t1_dir_distance_from_adverse_extreme_30d_atr",
        "t1_dir_distance_from_adverse_extreme_60d_atr",
    ],
    "G6_T1_PATH_REGIME": [
        "t1_path_efficiency_7d",
        "t1_path_efficiency_14d",
        "t1_path_efficiency_30d",
        "t1_path_efficiency_60d",
        "t1_shock_day",
        "t1_sideways_state",
        "t1_reexpansion_state",
    ],
}

DELETION_CANDIDATES = {
    "D_NO_G1_T1_MA7": "G1_T1_MA7_STATE",
    "D_NO_G2_EVENT_GEOMETRY": "G2_EVENT_GEOMETRY",
    "D_NO_G3_VOLATILITY": "G3_VOLATILITY_STATE",
    "D_NO_G4_VOLUME": "G4_VOLUME_ACTIVITY",
    "D_NO_G5_T1_MOMENTUM_LOCATION": "G5_T1_MOMENTUM_LOCATION",
    "D_NO_G6_T1_PATH_REGIME": "G6_T1_PATH_REGIME",
}

ONLY_CANDIDATES = {
    "O_G1_T1_MA7_ONLY": "G1_T1_MA7_STATE",
    "O_G2_EVENT_GEOMETRY_ONLY": "G2_EVENT_GEOMETRY",
    "O_G3_VOLATILITY_ONLY": "G3_VOLATILITY_STATE",
    "O_G4_VOLUME_ONLY": "G4_VOLUME_ACTIVITY",
    "O_G5_T1_MOMENTUM_LOCATION_ONLY": "G5_T1_MOMENTUM_LOCATION",
    "O_G6_T1_PATH_REGIME_ONLY": "G6_T1_PATH_REGIME",
}

COMPRESSED_CANDIDATES = {
    "M_EVENT_25": ["G1_T1_MA7_STATE", "G2_EVENT_GEOMETRY"],
    "M_EVENT_VOL_36": ["G1_T1_MA7_STATE", "G2_EVENT_GEOMETRY", "G3_VOLATILITY_STATE"],
}

REFERENCE_CANDIDATE = "R_FULL_B0_69"
ALL_CANDIDATES = tuple([REFERENCE_CANDIDATE, *DELETION_CANDIDATES, *ONLY_CANDIDATES, *COMPRESSED_CANDIDATES])
HOLDOUT_CANDIDATES = tuple([REFERENCE_CANDIDATE, *DELETION_CANDIDATES, *COMPRESSED_CANDIDATES])

FORBIDDEN_IN_X = {
    "asset",
    "asset_slug",
    "side",
    "side_sign",
    "ts",
    "event_year",
    "feature_known_at",
    "entry_ts",
    "entry_ref",
    "atr_anchor",
    "calendar_month",
    "calendar_quarter",
    "listing_age_days",
    "probe_raw_ma7_cross_dir",
    "dir_raw_ma7_cross",
    "model_eligible_entry_p0r",
    "future_path_complete_20d",
    TARGET,
    NET_RETURN,
    LABEL_END,
}
FORBIDDEN_PATTERNS = (
    "funding",
    "liquidity",
    "pit_universe",
    "market_",
    "btc_",
    "relative_to_btc",
    "relative_to_market",
    "dir_close_ma14",
    "dir_close_ma30",
    "dir_close_ma60",
    "dir_ma14",
    "dir_ma30",
    "dir_ma60",
    "ma_stack",
    "fast_slow",
    "ma7_cross_with_ma30",
    "price_ma7_ma30",
    "date",
    "year",
    "label_",
    "future_",
    "net_return",
    "mfe",
    "mae",
)


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


P2 = load_module(P2_SCRIPT_PATH, "binance_1d_ma7_ctp_p2_for_p4")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="execute P4")
    parser.add_argument("--force", action="store_true", help="overwrite P4 outputs")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(json.dumps(json_ready(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


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
        FACTOR_GROUP_SPEC_PATH,
        CONTRACT_LOCK_PATH,
        FOLD_METRICS_PATH,
        OOF_PREDICTIONS_PATH,
        ABLATION_COMPARISONS_PATH,
        ONLY_GROUP_METRICS_PATH,
        ASSET_HOLDOUT_METRICS_PATH,
        DECILE_METRICS_PATH,
        COEFFICIENT_STABILITY_PATH,
        MODEL_CARD_PATH,
        SUMMARY_PATH,
        MANIFEST_PATH,
        REPORT_PATH,
        AUDIT_PATH,
    )


def ensure_output_policy(force: bool) -> None:
    existing = [path for path in output_paths() if path.exists()]
    if existing and not force:
        rel = ", ".join(str(path.relative_to(ROOT)) for path in existing)
        raise FileExistsError(f"P4 outputs already exist; pass --force to reproduce: {rel}")


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


def feature_group_for(feature: str) -> str:
    for group, features in FACTOR_GROUPS.items():
        if feature in features:
            return group
    raise KeyError(feature)


def ordered_filter(p2_order: list[str], groups: Iterable[str]) -> list[str]:
    allowed = set()
    for group in groups:
        allowed.update(FACTOR_GROUPS[group])
    return [feature for feature in p2_order if feature in allowed]


def candidate_features_from_order(p2_order: list[str], candidate: str) -> list[str]:
    if candidate == REFERENCE_CANDIDATE:
        return p2_order[:]
    if candidate in DELETION_CANDIDATES:
        removed = set(FACTOR_GROUPS[DELETION_CANDIDATES[candidate]])
        return [feature for feature in p2_order if feature not in removed]
    if candidate in ONLY_CANDIDATES:
        return ordered_filter(p2_order, [ONLY_CANDIDATES[candidate]])
    if candidate in COMPRESSED_CANDIDATES:
        return ordered_filter(p2_order, COMPRESSED_CANDIDATES[candidate])
    raise ValueError(candidate)


def build_factor_group_spec(p2_feature_spec: dict[str, Any], p3r_feature_spec: dict[str, Any]) -> dict[str, Any]:
    p2_order = scheme_features(p2_feature_spec, "F1_MA7_PATH")
    flat = [feature for features in FACTOR_GROUPS.values() for feature in features]
    duplicate_fields = sorted({feature for feature in flat if flat.count(feature) > 1})
    missing_fields = [feature for feature in p2_order if feature not in flat]
    extra_fields = [feature for feature in flat if feature not in p2_order]
    counts = {group: len(features) for group, features in FACTOR_GROUPS.items()}
    if sum(counts.values()) != 69:
        raise RuntimeError("P4 factor group count must sum to 69")
    if duplicate_fields or missing_fields or extra_fields or len(p2_order) != 69:
        raise RuntimeError(f"P4 factor group mismatch: duplicate={duplicate_fields} missing={missing_fields} extra={extra_fields}")
    if p3r_feature_spec["feature_blocks"]["B0_P2_F1"] != p2_order:
        raise RuntimeError("P3R B0 does not match P2 F1")
    group_by_p2_order = [{"ordinal": i + 1, "feature": feature, "group": feature_group_for(feature)} for i, feature in enumerate(p2_order)]
    candidates = {
        candidate: {
            "feature_count": len(candidate_features_from_order(p2_order, candidate)),
            "features": candidate_features_from_order(p2_order, candidate),
            "role": "reference"
            if candidate == REFERENCE_CANDIDATE
            else "deletion_ablation"
            if candidate in DELETION_CANDIDATES
            else "only_group_diagnostic"
            if candidate in ONLY_CANDIDATES
            else "compressed_preregistered",
        }
        for candidate in ALL_CANDIDATES
    }
    payload = {
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "alias": "BIN-1D-MA7-CTP",
        "experiment": "P4 Core Factor Ablation + Compressed Tail-Ranking Audit",
        "status": STATUS,
        "frozen_before_p4_label_read": True,
        "source_p2_feature_scheme": "F1_MA7_PATH",
        "p2_original_field_order": p2_order,
        "factor_groups": {
            group: {"field_count": len(features), "fields": features}
            for group, features in FACTOR_GROUPS.items()
        },
        "group_count_identity": "12 + 13 + 11 + 5 + 21 + 7 = 69",
        "group_counts": counts,
        "p2_order_group_map": group_by_p2_order,
        "union_matches_p2_f1": flat_set_equal_ordered_union(p2_order),
        "duplicate_fields": duplicate_fields,
        "missing_fields_vs_p2_f1": missing_fields,
        "extra_fields_vs_p2_f1": extra_fields,
        "candidate_models": candidates,
        "categorical_features": ["t1_volatility_state_p0r"],
        "forbidden_in_x": sorted(FORBIDDEN_IN_X),
        "forbidden_feature_patterns": list(FORBIDDEN_PATTERNS),
        "p2_feature_spec_sha256": sha256_file(P2_FEATURE_SPEC_PATH),
        "p3r_feature_spec_sha256": sha256_file(P3R_FEATURE_SPEC_PATH),
    }
    payload["payload_sha256"] = canonical_sha256(payload)
    return payload


def flat_set_equal_ordered_union(p2_order: list[str]) -> bool:
    union_in_p2_order = [feature for feature in p2_order if any(feature in features for features in FACTOR_GROUPS.values())]
    return union_in_p2_order == p2_order and len({feature for features in FACTOR_GROUPS.values() for feature in features}) == len(p2_order)


def write_factor_group_spec() -> dict[str, Any]:
    spec = build_factor_group_spec(load_json(P2_FEATURE_SPEC_PATH), load_json(P3R_FEATURE_SPEC_PATH))
    atomic_write_json(FACTOR_GROUP_SPEC_PATH, spec)
    return spec


def source_columns_for_features(p2_order: list[str]) -> list[str]:
    columns: set[str] = set()
    for feature in p2_order:
        columns.add(t1_source_name(feature) if feature.startswith("t1_") else feature)
    return sorted(columns)


def asset_group(asset: str) -> int:
    return int(hashlib.sha256(asset.encode("utf-8")).hexdigest(), 16) % 5


def validate_inputs(factor_spec: dict[str, Any]) -> dict[str, Any]:
    p2_summary = load_json(P2_SUMMARY_PATH)
    p2_card = load_json(P2_MODEL_CARD_PATH)
    p3r_summary = load_json(P3R_SUMMARY_PATH)
    p3r_card = load_json(P3R_MODEL_CARD_PATH)
    p0r_features = load_json(P0R_FEATURE_BLOCKS_PATH)
    p0r_manifest = load_json(P0R_MANIFEST_PATH)

    p2_order = factor_spec["p2_original_field_order"]
    all_p0r_allowed = set(p0r_features["all_allowed_features"])
    missing_sources = sorted(
        {
            t1_source_name(feature) if feature.startswith("t1_") else feature
            for feature in p2_order
            if (t1_source_name(feature) if feature.startswith("t1_") else feature) not in all_p0r_allowed
        }
    )
    if missing_sources:
        raise RuntimeError(f"DATA_BLOCK_NOT_READY: P4 source columns absent from P0R allowlist: {missing_sources}")
    forbidden_leaks = sorted(set(p2_order) & FORBIDDEN_IN_X)
    pattern_leaks = sorted(
        feature
        for feature in p2_order
        if feature != "t1_volatility_state_p0r" and any(token in feature.lower() for token in FORBIDDEN_PATTERNS)
    )
    if forbidden_leaks or pattern_leaks:
        raise RuntimeError(f"OBJECTIVE_MISALIGNED: forbidden P4 X features leaked: {forbidden_leaks + pattern_leaks}")
    if p2_summary["hype_isolation"]["event_rows"] != 0 or p2_card["hype_rows"] != 0 or p3r_summary["hype_isolation"]["event_rows"] != 0 or p3r_card["hype_rows"] != 0:
        raise RuntimeError("HOLDOUT_CONTAMINATED: source model metadata contains HYPE")
    if p2_summary["input_integrity"]["post_2025_model_rows_read"] != 0 or p2_card["post_2025_predictions_written"] != 0:
        raise RuntimeError("DATA_BLOCK_NOT_READY: P2 source used 2025+ rows")
    if p3r_summary["input_integrity"]["post_2025_event_rows_read"] != 0 or p3r_card["post_2025_predictions_written"] != 0:
        raise RuntimeError("DATA_BLOCK_NOT_READY: P3R source used 2025+ rows")

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
        "p0r_feature_blocks_sha256": sha256_file(P0R_FEATURE_BLOCKS_PATH),
        "p2_feature_spec_sha256": sha256_file(P2_FEATURE_SPEC_PATH),
        "p2_summary_sha256": sha256_file(P2_SUMMARY_PATH),
        "p2_model_card_sha256": sha256_file(P2_MODEL_CARD_PATH),
        "p3r_feature_spec_sha256": sha256_file(P3R_FEATURE_SPEC_PATH),
        "p3r_summary_sha256": sha256_file(P3R_SUMMARY_PATH),
        "p3r_model_card_sha256": sha256_file(P3R_MODEL_CARD_PATH),
        "p2_script_sha256": sha256_file(P2_SCRIPT_PATH),
        "p3r_script_sha256": sha256_file(P3R_SCRIPT_PATH),
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
        "factor_group_spec_file_sha256": sha256_file(FACTOR_GROUP_SPEC_PATH),
        "factor_group_payload_sha256": factor_spec["payload_sha256"],
    }
    if not audit["p0r_artifact_hashes_all_match"] or not audit["panel_file_set_matches_manifest"]:
        raise RuntimeError("DATA_BLOCK_NOT_READY: P0R manifest hash or panel file set mismatch")
    if audit["holdout_read"] is not False or audit["hype_asset_excluded"] != HYPE_ASSET:
        raise RuntimeError("DATA_BLOCK_NOT_READY: P0R holdout/HYPE boundary mismatch")
    if audit["panel_hype_rows"] != 0:
        raise RuntimeError("HOLDOUT_CONTAMINATED")
    if audit["panel_hyper_rows"] <= 0:
        raise RuntimeError("DATA_BLOCK_NOT_READY: HYPER missing")
    return audit


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


def validate_time_boundary(frame: pd.DataFrame) -> dict[str, Any]:
    audit = {
        "feature_known_at_lt_entry_ts": int((frame["feature_known_at"] < frame["entry_ts"]).sum()),
        "feature_known_at_eq_entry_ts": int((frame["feature_known_at"] == frame["entry_ts"]).sum()),
        "feature_known_at_gt_entry_ts": int((frame["feature_known_at"] > frame["entry_ts"]).sum()),
        "entry_ts_eq_ts_plus_1d": int((frame["entry_ts"] == frame["ts"] + pd.Timedelta(days=1)).sum()),
        "feature_known_at_eq_ts_plus_1d": int((frame["feature_known_at"] == frame["ts"] + pd.Timedelta(days=1)).sum()),
    }
    if audit["feature_known_at_lt_entry_ts"] != 0 or audit["feature_known_at_gt_entry_ts"] != 0:
        raise RuntimeError("DATA_BLOCK_NOT_READY: feature_known_at must equal entry_ts")
    if audit["entry_ts_eq_ts_plus_1d"] != len(frame) or audit["feature_known_at_eq_ts_plus_1d"] != len(frame):
        raise RuntimeError("DATA_BLOCK_NOT_READY: entry_ts/feature_known_at must equal ts+1d")
    return audit


def load_strict_event_panel(factor_spec: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    p2_order = factor_spec["p2_original_field_order"]
    source_cols = source_columns_for_features(p2_order)
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
    for feature in [f for f in p2_order if f.startswith("t1_")]:
        raw[feature] = raw.groupby(["asset", "side"], sort=False)[t1_source_name(feature)].shift(1)

    events = raw.loc[
        raw["probe_raw_ma7_cross_dir"].eq(True)
        & raw["model_eligible_entry_p0r"].eq(True)
        & raw["ts"].lt(CUTOFF)
        & raw[LABEL_END].lt(CUTOFF)
    ].copy()
    events["asset_group"] = events["asset"].map(asset_group).astype("int8")
    events["event_year"] = events["ts"].dt.year.astype("int16")
    tradfi_mask = events["asset"].astype(str).str.split("/", n=1).str[0].isin(TRADFI_BASE_SYMBOLS)
    time_audit = validate_time_boundary(events)

    if len(events) != EXPECTED_STRICT_ROWS:
        raise RuntimeError(f"DATA_BLOCK_NOT_READY: expected strict rows {EXPECTED_STRICT_ROWS}, got {len(events)}")
    if events["asset"].nunique() != EXPECTED_STRICT_ASSETS:
        raise RuntimeError("DATA_BLOCK_NOT_READY: strict asset count mismatch")
    if int(events["side"].eq("long").sum()) != EXPECTED_STRICT_LONG or int(events["side"].eq("short").sum()) != EXPECTED_STRICT_SHORT:
        raise RuntimeError("DATA_BLOCK_NOT_READY: strict long/short count mismatch")
    if events["ts"].min() != EXPECTED_STRICT_MIN_TS or events["ts"].max() != EXPECTED_STRICT_MAX_TS:
        raise RuntimeError("DATA_BLOCK_NOT_READY: strict date range mismatch")
    if events[LABEL_END].max() != EXPECTED_MAX_LABEL_END:
        raise RuntimeError("DATA_BLOCK_NOT_READY: strict label end max mismatch")
    if events["asset"].eq(HYPE_ASSET).any():
        raise RuntimeError("HOLDOUT_CONTAMINATED")
    if events["ts"].ge(CUTOFF).any() or events[LABEL_END].ge(CUTOFF).any():
        raise RuntimeError("DATA_BLOCK_NOT_READY: 2025+ row entered P4 strict sample")
    if events[TARGET].isna().any():
        raise RuntimeError("DATA_BLOCK_NOT_READY: null target label")
    if not events["future_path_complete_20d"].all():
        raise RuntimeError("DATA_BLOCK_NOT_READY: incomplete 20d future path")
    if not events["probe_raw_ma7_cross_dir"].all() or not events["dir_raw_ma7_cross"].eq(1).all():
        raise RuntimeError("OBJECTIVE_MISALIGNED")
    if events.duplicated(["asset", "ts"]).any() or events.duplicated(["asset", "ts", "side"]).any():
        raise RuntimeError("DATA_BLOCK_NOT_READY: duplicate directional cross")
    if set(events["side"].unique()) != {"long", "short"}:
        raise RuntimeError("DATA_BLOCK_NOT_READY: side must be long/short")
    if int(tradfi_mask.sum()) != 0:
        raise RuntimeError("DATA_BLOCK_NOT_READY: known TradFi strict events entered P4")
    assert_t1_is_prior_valid_day(raw, events)

    audit = {
        "n": int(len(events)),
        "assets": int(events["asset"].nunique()),
        "long": int(events["side"].eq("long").sum()),
        "short": int(events["side"].eq("short").sum()),
        "hype": int(events["asset"].eq(HYPE_ASSET).sum()),
        "hyper": int(events["asset"].eq(HYPER_ASSET).sum()),
        "min_ts": events["ts"].min(),
        "max_ts": events["ts"].max(),
        "max_label_end_ts_20d": events[LABEL_END].max(),
        "non_cross": int((~events["probe_raw_ma7_cross_dir"]).sum()),
        "duplicate_asset_ts": int(events.duplicated(["asset", "ts"]).sum()),
        "duplicate_asset_ts_side": int(events.duplicated(["asset", "ts", "side"]).sum()),
        "null_target": int(events[TARGET].isna().sum()),
        "incomplete_20d_future_path": int((~events["future_path_complete_20d"]).sum()),
        "known_tradfi_events": int(tradfi_mask.sum()),
        "positive_rate": float(events[TARGET].mean()),
        **time_audit,
    }
    return events.reset_index(drop=True), audit


def assert_t1_is_prior_valid_day(raw: pd.DataFrame, events: pd.DataFrame) -> None:
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
        comparable = actual.notna() & expected.notna()
        if not comparable.any():
            continue
        if pd.api.types.is_numeric_dtype(actual):
            if not np.allclose(actual[comparable].astype(float), expected[comparable].astype(float), atol=1e-8, rtol=1e-8):
                raise RuntimeError(f"T1 lag mismatch for {feature}")
        elif not actual[comparable].astype(str).eq(expected[comparable].astype(str)).all():
            raise RuntimeError(f"T1 lag mismatch for {feature}")


def fold_split(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = frame.loc[frame["ts"].lt(start) & frame[LABEL_END].lt(start)].copy()
    valid = frame.loc[frame["ts"].ge(start) & frame["ts"].lt(end)].copy()
    if train.empty or valid.empty:
        raise RuntimeError("DATA_BLOCK_NOT_READY: empty P4 fold")
    if not train[LABEL_END].max() < start:
        raise RuntimeError("DATA_BLOCK_NOT_READY: purge failed")
    if train["ts"].ge(CUTOFF).any() or valid["ts"].ge(CUTOFF).any() or train[LABEL_END].ge(CUTOFF).any() or valid[LABEL_END].ge(CUTOFF).any():
        raise RuntimeError("DATA_BLOCK_NOT_READY: 2025+ row entered P4 split")
    return train, valid


def clip_probability(probability: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(probability, dtype=float), 1e-6, 1 - 1e-6)


def percentile_and_decile(probability: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    probability = np.asarray(probability, dtype=float)
    ranks = pd.Series(probability).rank(method="first", pct=True).to_numpy()
    decile = np.ceil(ranks * 10).clip(1, 10).astype(int)
    return ranks, decile


def asset_balanced_weights(frame: pd.DataFrame) -> np.ndarray:
    counts = frame.groupby("asset")["asset"].transform("count").astype(float)
    weights = 1.0 / counts
    return (weights / weights.mean()).to_numpy()


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


def metric_values(frame: pd.DataFrame, probability: np.ndarray, *, top_mode: str = "local") -> dict[str, Any]:
    y = frame[TARGET].astype(int).to_numpy()
    p = clip_probability(probability)
    auc = float(roc_auc_score(y, p)) if len(np.unique(y)) >= 2 else None
    pr_auc = float(average_precision_score(y, p)) if len(np.unique(y)) >= 2 else None
    const = np.full(len(y), float(np.mean(y)))
    if top_mode == "fold_relative" and "_top10_mask" in frame:
        top_mask = frame["_top10_mask"].to_numpy(dtype=bool)
        bottom_mask = frame["_bottom10_mask"].to_numpy(dtype=bool)
    else:
        _, decile = percentile_and_decile(p)
        top_mask = decile == 10
        bottom_mask = decile == 1
    top = frame.loc[top_mask]
    bottom = frame.loc[bottom_mask]
    brier_const = float(brier_score_loss(y, const))
    return {
        "eval_n": int(len(frame)),
        "asset_count": int(frame["asset"].nunique()) if "asset" in frame else None,
        "date_min": frame["ts"].min() if "ts" in frame else None,
        "date_max": frame["ts"].max() if "ts" in frame else None,
        "positive_rate": float(np.mean(y)),
        "pr_baseline": float(np.mean(y)),
        "roc_auc": auc,
        "pr_auc": pr_auc,
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "brier": float(brier_score_loss(y, p)),
        "brier_const": brier_const,
        "brier_skill_vs_const": float(1 - brier_score_loss(y, p) / brier_const) if brier_const > 0 else None,
        "ece_10": ece_10(y, p),
        "top10_n": int(len(top)),
        "top10_success_rate": float(top[TARGET].mean()) if len(top) else None,
        "top10_uplift": float(top[TARGET].mean() - np.mean(y)) if len(top) else None,
        "top10_net_return_mean": float(top[NET_RETURN].mean()) if len(top) else None,
        "top10_net_return_median": float(top[NET_RETURN].median()) if len(top) else None,
        "bottom10_n": int(len(bottom)),
        "bottom10_success_rate": float(bottom[TARGET].mean()) if len(bottom) else None,
        "top_bottom_success_rate_diff": float(top[TARGET].mean() - bottom[TARGET].mean()) if len(top) and len(bottom) else None,
        "asset_balanced_auc": float(roc_auc_score(y, p, sample_weight=asset_balanced_weights(frame))) if "asset" in frame and len(np.unique(y)) >= 2 else None,
    }


def fit_logit(train: pd.DataFrame, valid: pd.DataFrame, features: list[str]) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    categorical = ["t1_volatility_state_p0r"] if "t1_volatility_state_p0r" in features else []
    prep = P2.TabularPreprocessor(features, categorical).fit(train)
    x_train = prep.transform(train)
    x_valid = prep.transform(valid)
    scaler = StandardScaler()
    x_train_s = scaler.fit_transform(x_train)
    x_valid_s = scaler.transform(x_valid)
    model = LogisticRegression(max_iter=1000, solver="lbfgs", random_state=SEED)
    model.fit(x_train_s, train[TARGET].astype(int).to_numpy())
    coef_rows = [
        {"expanded_feature": name, "base_feature": name.split("__", 1)[0], "coef": float(coef)}
        for name, coef in zip(prep.output_features or [], model.coef_[0], strict=False)
    ]
    return (
        model.predict_proba(x_train_s)[:, 1],
        model.predict_proba(x_valid_s)[:, 1],
        {"preprocessor": prep, "scaler": scaler, "model": model, "coef_rows": coef_rows},
    )


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
    forward_eval_mask = oof["fold"].isin(fold_names[1:]).to_numpy()
    raw_metrics = metric_values(oof.loc[forward_eval_mask], raw[forward_eval_mask])
    calibrated_metrics = metric_values(oof.loc[forward_eval_mask], forward[forward_eval_mask])
    final_fit_frame = oof.loc[oof[LABEL_END].lt(CUTOFF)]
    final_calibration = P2.fit_platt(final_fit_frame[raw_col].to_numpy(), final_fit_frame[TARGET].astype(int).to_numpy())
    final_calibration.update(
        {
            "selection_basis": "forward_oof_D2_D3",
            "forward_eval_rows": int(forward_eval_mask.sum()),
            "forward_raw_brier": raw_metrics["brier"],
            "forward_calibrated_brier": calibrated_metrics["brier"],
            "forward_raw_log_loss": raw_metrics["log_loss"],
            "forward_calibrated_log_loss": calibrated_metrics["log_loss"],
            "final_fit_rows": int(len(final_fit_frame)),
            "final_fit_label_end_max": final_fit_frame[LABEL_END].max(),
            "fit_scope": "completed_D1_D3_oof_before_2025_cutoff",
        }
    )
    comparison = {
        "evaluation_folds": fold_names[1:],
        "eval_rows": int(forward_eval_mask.sum()),
        "raw": raw_metrics,
        "forward_calibrated": calibrated_metrics,
        "improved_brier_or_log_loss": bool(calibrated_metrics["brier"] < raw_metrics["brier"] or calibrated_metrics["log_loss"] < raw_metrics["log_loss"]),
        "d1_probability_policy": "raw_no_prior_oof",
    }
    return forward, final_calibration, audits, comparison


def run_development(frame: pd.DataFrame, factor_spec: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    p2_order = factor_spec["p2_original_field_order"]
    metric_rows: list[dict[str, Any]] = []
    coef_rows: list[dict[str, Any]] = []
    oof_rows: list[pd.DataFrame] = []
    purge_audit: list[dict[str, Any]] = []
    sample_keys_by_fold: dict[str, dict[str, Any]] = {}

    for fold, start, end in FOLDS:
        train, valid = fold_split(frame, start, end)
        print(f"P4 {fold}: train={len(train)} valid={len(valid)}", flush=True)
        base = valid[["asset", "side", "ts", "feature_known_at", "entry_ts", TARGET, LABEL_END, NET_RETURN, "asset_group", "event_year", "volatility_state_p0r", "listing_age_days", "liquidity_rank_pct_p0r", "pit_universe_size_p0r"]].copy()
        base["fold"] = fold
        sample_keys_by_fold[fold] = {
            "train_n": int(len(train)),
            "validation_n": int(len(valid)),
            "train_key_hash": row_key_hash(train),
            "validation_key_hash": row_key_hash(valid),
        }
        for candidate in ALL_CANDIDATES:
            features = candidate_features_from_order(p2_order, candidate)
            p_train, p_valid, detail = fit_logit(train, valid, features)
            raw_col = f"p_{candidate.lower()}_raw"
            pct_col = f"score_percentile_{candidate.lower()}"
            dec_col = f"score_decile_{candidate.lower()}"
            base[raw_col] = p_valid
            percentile, decile = percentile_and_decile(p_valid)
            base[pct_col] = percentile
            base[dec_col] = decile
            train_metric = metric_values(train, p_train)
            valid_metric = metric_values(valid, p_valid)
            gap = None if train_metric["roc_auc"] is None or valid_metric["roc_auc"] is None else train_metric["roc_auc"] - valid_metric["roc_auc"]
            uplift_gap = None
            if train_metric["top10_uplift"] is not None and valid_metric["top10_uplift"] is not None:
                uplift_gap = train_metric["top10_uplift"] - valid_metric["top10_uplift"]
            flag = "SEVERE_OVERFIT_WARNING" if gap is not None and gap > 0.10 else ""
            for split, split_frame, probability in [("training", train, p_train), ("validation", valid, p_valid)]:
                row = metric_values(split_frame, probability)
                row.update(
                    {
                        "head": HEAD,
                        "row_type": "metric",
                        "candidate": candidate,
                        "candidate_role": factor_spec["candidate_models"][candidate]["role"],
                        "feature_count": len(features),
                        "fold": fold,
                        "split": split,
                        "probability_type": "raw",
                        "train_n": int(len(train)),
                        "train_label_end_max": train[LABEL_END].max(),
                        "train_val_auc_gap": gap,
                        "train_val_top_uplift_gap": uplift_gap,
                        "overfit_flag": flag,
                    }
                )
                metric_rows.append(row)
            for coef in detail["coef_rows"]:
                coef_rows.append(
                    {
                        "candidate": candidate,
                        "fold": fold,
                        "expanded_feature": coef["expanded_feature"],
                        "base_feature": coef["base_feature"],
                        "factor_group": feature_group_for(coef["base_feature"]),
                        "coef": coef["coef"],
                    }
                )
        oof_rows.append(base)
        purge_audit.append({"fold": fold, "train_n": len(train), "validation_n": len(valid), "train_label_end_max": train[LABEL_END].max(), "validation_start": start, "purge_pass": bool(train[LABEL_END].max() < start)})

    oof = pd.concat(oof_rows, ignore_index=True)
    if oof["ts"].ge(CUTOFF).any() or oof[LABEL_END].ge(CUTOFF).any() or oof["asset"].eq(HYPE_ASSET).any():
        raise RuntimeError("P4 OOF contamination")
    if oof.duplicated(["asset", "ts", "side"]).any():
        raise RuntimeError("P4 OOF duplicate")

    calibration_audit: dict[str, list[dict[str, Any]]] = {}
    calibration_comparison: dict[str, dict[str, Any]] = {}
    for candidate in ALL_CANDIDATES:
        raw_col = f"p_{candidate.lower()}_raw"
        forward, final_calibration, audit, comparison = forward_oof_calibration(oof, raw_col)
        cal_col = f"p_{candidate.lower()}_calibrated_forward"
        oof[cal_col] = forward
        calibration_audit[candidate] = audit
        calibration_comparison[candidate] = {"final_calibration": final_calibration, "forward_validation": comparison}
        for fold, _, _ in FOLDS:
            fold_frame = oof.loc[oof["fold"].eq(fold)]
            row = metric_values(fold_frame, fold_frame[cal_col].to_numpy())
            row.update(
                {
                    "head": HEAD,
                    "row_type": "metric",
                    "candidate": candidate,
                    "candidate_role": factor_spec["candidate_models"][candidate]["role"],
                    "feature_count": factor_spec["candidate_models"][candidate]["feature_count"],
                    "fold": fold,
                    "split": "validation",
                    "probability_type": "forward_calibrated",
                    "train_n": 0,
                    "train_label_end_max": None,
                    "train_val_auc_gap": None,
                    "train_val_top_uplift_gap": None,
                    "overfit_flag": "",
                }
            )
            metric_rows.append(row)

    metric_df = pd.DataFrame(metric_rows)
    coef_df = pd.DataFrame(coef_rows)
    candidate_summary = build_candidate_summary(oof, metric_df, factor_spec, calibration_comparison)
    development = {
        "candidate_summary": candidate_summary,
        "purge_audit": purge_audit,
        "calibration_audit": calibration_audit,
        "sample_keys_by_fold": sample_keys_by_fold,
        "all_candidates_use_same_samples": True,
        "selection_rows": int(len(oof)),
        "selection_data_max_ts": oof["ts"].max(),
        "historical_2025_plus_rows_used_for_selection": 0,
        "hype_rows_used_for_selection": 0,
        "one_pooled_model_only": True,
    }
    return metric_df, oof, coef_df, development


def row_key_hash(frame: pd.DataFrame) -> str:
    keys = frame[["asset", "side", "ts"]].copy()
    keys["ts"] = pd.to_datetime(keys["ts"], utc=True).astype(str)
    text = "\n".join("|".join(row) for row in keys.astype(str).to_numpy())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_candidate_summary(oof: pd.DataFrame, metric_df: pd.DataFrame, factor_spec: dict[str, Any], calibration: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for candidate in ALL_CANDIDATES:
        raw_val = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["split"].eq("validation")) & (metric_df["probability_type"].eq("raw")) & (metric_df["row_type"].eq("metric"))].sort_values("fold")
        cal_val = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["split"].eq("validation")) & (metric_df["probability_type"].eq("forward_calibrated")) & (metric_df["row_type"].eq("metric"))].sort_values("fold")
        raw_col = f"p_{candidate.lower()}_raw"
        cal_col = f"p_{candidate.lower()}_calibrated_forward"
        fold_top = fold_relative_top_stats(oof, raw_col)
        summary[candidate] = {
            "candidate_role": factor_spec["candidate_models"][candidate]["role"],
            "feature_count": factor_spec["candidate_models"][candidate]["feature_count"],
            "fold_auc": [float(x) for x in raw_val["roc_auc"].tolist()],
            "fold_top10_success_rate": [float(x) for x in raw_val["top10_success_rate"].tolist()],
            "worst_fold_auc": float(raw_val["roc_auc"].min()),
            "macro_auc": float(raw_val["roc_auc"].mean()),
            "macro_pr_auc": float(raw_val["pr_auc"].mean()),
            "macro_forward_brier": float(cal_val["brier"].mean()),
            "macro_forward_log_loss": float(cal_val["log_loss"].mean()),
            "train_validation_auc_gap_mean": float(raw_val["train_val_auc_gap"].mean()),
            "train_validation_top_uplift_gap_mean": float(raw_val["train_val_top_uplift_gap"].mean()),
            "overfit_warning_folds": raw_val.loc[raw_val["overfit_flag"].fillna("").ne(""), "fold"].tolist(),
            "oof_raw": metric_values(oof, oof[raw_col].to_numpy()),
            "oof_forward_calibrated": metric_values(oof, oof[cal_col].to_numpy()),
            "fold_relative_top10": fold_top,
            "legacy_pooled_raw_top10": legacy_top_stats(oof, raw_col),
            "calibration": calibration[candidate],
        }
    return summary


def fold_relative_top_stats(frame: pd.DataFrame, score_col: str) -> dict[str, Any]:
    pieces = []
    per_fold: dict[str, Any] = {}
    for fold, group in frame.groupby("fold", sort=True):
        _, decile = percentile_and_decile(group[score_col].to_numpy())
        top = group.loc[decile == 10]
        bottom = group.loc[decile == 1]
        per_fold[str(fold)] = {
            "n": int(len(top)),
            "base_success_rate": float(group[TARGET].mean()),
            "success_rate": float(top[TARGET].mean()) if len(top) else None,
            "uplift": float(top[TARGET].mean() - group[TARGET].mean()) if len(top) else None,
            "net_return_mean": float(top[NET_RETURN].mean()) if len(top) else None,
            "net_return_median": float(top[NET_RETURN].median()) if len(top) else None,
            "bottom_success_rate": float(bottom[TARGET].mean()) if len(bottom) else None,
            "top_bottom_success_rate_diff": float(top[TARGET].mean() - bottom[TARGET].mean()) if len(top) and len(bottom) else None,
        }
        pieces.append(top)
    combined = pd.concat(pieces, ignore_index=True) if pieces else frame.iloc[0:0]
    fold_success = [item["success_rate"] for item in per_fold.values() if item["success_rate"] is not None]
    return {
        "definition": "score_percentile computed inside each validation fold; top10 is score_percentile >= 0.90",
        "n": int(len(combined)),
        "success_rate": float(combined[TARGET].mean()) if len(combined) else None,
        "uplift_vs_all_oof": float(combined[TARGET].mean() - frame[TARGET].mean()) if len(combined) else None,
        "net_return_mean": float(combined[NET_RETURN].mean()) if len(combined) else None,
        "net_return_median": float(combined[NET_RETURN].median()) if len(combined) else None,
        "worst_fold_success_rate": float(min(fold_success)) if fold_success else None,
        "fold_success_rate_std": float(np.std(fold_success, ddof=0)) if fold_success else None,
        "per_fold": per_fold,
    }


def legacy_top_stats(frame: pd.DataFrame, score_col: str) -> dict[str, Any]:
    _, decile = percentile_and_decile(frame[score_col].to_numpy())
    top = frame.loc[decile == 10]
    bottom = frame.loc[decile == 1]
    return {
        "label": "legacy pooled-raw diagnostic",
        "n": int(len(top)),
        "success_rate": float(top[TARGET].mean()) if len(top) else None,
        "uplift_vs_all_oof": float(top[TARGET].mean() - frame[TARGET].mean()) if len(top) else None,
        "net_return_mean": float(top[NET_RETURN].mean()) if len(top) else None,
        "net_return_median": float(top[NET_RETURN].median()) if len(top) else None,
        "bottom_success_rate": float(bottom[TARGET].mean()) if len(bottom) else None,
        "top_bottom_success_rate_diff": float(top[TARGET].mean() - bottom[TARGET].mean()) if len(top) and len(bottom) else None,
    }


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


def stratum_labels(frame: pd.DataFrame, kind: str) -> pd.Series:
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
    raise ValueError(kind)


@dataclass(frozen=True)
class FoldBlockDraws:
    fold_groups: dict[str, dict[int, np.ndarray]]
    fold_blocks: dict[str, list[int]]
    draws: dict[str, np.ndarray]
    draw_hash: str


def make_fold_block_draws(frame: pd.DataFrame) -> FoldBlockDraws:
    fold_groups: dict[str, dict[int, np.ndarray]] = {}
    fold_blocks: dict[str, list[int]] = {}
    draws: dict[str, np.ndarray] = {}
    rng = np.random.default_rng(SEED)
    hash_parts: list[bytes] = []
    for fold, group in frame.groupby("fold", sort=True):
        tmp = group.copy()
        block0 = tmp["ts"].min().normalize()
        tmp["_block_id"] = ((tmp["ts"].dt.normalize() - block0).dt.days // BOOTSTRAP_BLOCK_DAYS).astype(int)
        blocks = sorted(tmp["_block_id"].unique().tolist())
        groups = {block: tmp.index[tmp["_block_id"].eq(block)].to_numpy() for block in blocks}
        draw = rng.integers(0, len(blocks), size=(BOOTSTRAP_SAMPLES, len(blocks)))
        fold_groups[str(fold)] = groups
        fold_blocks[str(fold)] = blocks
        draws[str(fold)] = draw
        hash_parts.append(str(fold).encode("utf-8") + draw.tobytes())
    return FoldBlockDraws(fold_groups=fold_groups, fold_blocks=fold_blocks, draws=draws, draw_hash=hashlib.sha256(b"".join(hash_parts)).hexdigest())


def bootstrap_ci(values: list[float]) -> tuple[float | None, float | None]:
    clean = np.asarray([v for v in values if v is not None and math.isfinite(v)], dtype=float)
    if clean.size == 0:
        return None, None
    return float(np.quantile(clean, 0.025)), float(np.quantile(clean, 0.975))


def combined_draw_sample(frame: pd.DataFrame, draws: FoldBlockDraws, i: int) -> pd.DataFrame:
    indices: list[np.ndarray] = []
    for fold in sorted(draws.draws):
        fold_draw = draws.draws[fold][i]
        blocks = draws.fold_blocks[fold]
        groups = draws.fold_groups[fold]
        indices.extend(groups[blocks[j]] for j in fold_draw)
    return frame.loc[np.concatenate(indices)]


def fold_macro_auc(frame: pd.DataFrame, score_col: str) -> float | None:
    aucs = []
    for _, group in frame.groupby("fold", sort=True):
        if group[TARGET].nunique() >= 2:
            aucs.append(float(roc_auc_score(group[TARGET], group[score_col])))
    return float(np.mean(aucs)) if aucs else None


def fold_relative_stats_for_score(frame: pd.DataFrame, score_col: str) -> dict[str, Any]:
    top_parts: list[pd.DataFrame] = []
    per_fold_success: dict[str, float] = {}
    for fold, group in frame.groupby("fold", sort=True):
        _, dec = percentile_and_decile(group[score_col].to_numpy())
        top = group.loc[dec == 10]
        top_parts.append(top)
        per_fold_success[str(fold)] = float(top[TARGET].mean()) if len(top) else np.nan
    top_all = pd.concat(top_parts, ignore_index=True)
    return {
        "top_success_rate": float(top_all[TARGET].mean()),
        "top_net_return_mean": float(top_all[NET_RETURN].mean()),
        "top_net_return_median": float(top_all[NET_RETURN].median()),
        "per_fold_success_rate": per_fold_success,
    }


def paired_bootstrap_comparison(oof: pd.DataFrame, candidate: str, baseline: str, draws: FoldBlockDraws) -> dict[str, Any]:
    cand_col = f"p_{candidate.lower()}_raw"
    base_col = f"p_{baseline.lower()}_raw"
    macro_auc_diff: list[float] = []
    pr_diff: list[float] = []
    top_success_diff: list[float] = []
    top_net_mean_diff: list[float] = []
    top_net_median_diff: list[float] = []
    asset_balanced_diff: list[float] = []
    for i in range(BOOTSTRAP_SAMPLES):
        sample = combined_draw_sample(oof, draws, i)
        if sample[TARGET].nunique() < 2:
            continue
        cand_macro = fold_macro_auc(sample, cand_col)
        base_macro = fold_macro_auc(sample, base_col)
        if cand_macro is not None and base_macro is not None:
            macro_auc_diff.append(cand_macro - base_macro)
        pr_diff.append(float(average_precision_score(sample[TARGET], sample[cand_col]) - average_precision_score(sample[TARGET], sample[base_col])))
        cand_top = fold_relative_stats_for_score(sample, cand_col)
        base_top = fold_relative_stats_for_score(sample, base_col)
        top_success_diff.append(cand_top["top_success_rate"] - base_top["top_success_rate"])
        top_net_mean_diff.append(cand_top["top_net_return_mean"] - base_top["top_net_return_mean"])
        top_net_median_diff.append(cand_top["top_net_return_median"] - base_top["top_net_return_median"])
        asset_balanced_diff.append(
            float(
                roc_auc_score(sample[TARGET], sample[cand_col], sample_weight=asset_balanced_weights(sample))
                - roc_auc_score(sample[TARGET], sample[base_col], sample_weight=asset_balanced_weights(sample))
            )
        )
    full_cand_top = fold_relative_stats_for_score(oof, cand_col)
    full_base_top = fold_relative_stats_for_score(oof, base_col)
    full_macro_cand = fold_macro_auc(oof, cand_col)
    full_macro_base = fold_macro_auc(oof, base_col)
    two_sided_p = None
    if top_success_diff:
        arr = np.asarray(top_success_diff)
        one_tail = min(np.mean(arr <= 0), np.mean(arr >= 0))
        two_sided_p = float(min(1.0, 2.0 * one_tail))
    return {
        "candidate": candidate,
        "baseline": baseline,
        "bootstrap_samples": BOOTSTRAP_SAMPLES,
        "block_days": BOOTSTRAP_BLOCK_DAYS,
        "same_draw_hash": draws.draw_hash,
        "macro_auc_diff": {"point": None if full_macro_cand is None or full_macro_base is None else float(full_macro_cand - full_macro_base), "ci95_low": bootstrap_ci(macro_auc_diff)[0], "ci95_high": bootstrap_ci(macro_auc_diff)[1]},
        "pr_auc_diff": {"point": float(average_precision_score(oof[TARGET], oof[cand_col]) - average_precision_score(oof[TARGET], oof[base_col])), "ci95_low": bootstrap_ci(pr_diff)[0], "ci95_high": bootstrap_ci(pr_diff)[1]},
        "top10_success_rate_diff": {"point": full_cand_top["top_success_rate"] - full_base_top["top_success_rate"], "ci95_low": bootstrap_ci(top_success_diff)[0], "ci95_high": bootstrap_ci(top_success_diff)[1], "two_sided_p": two_sided_p},
        "top10_net_return_mean_diff": {"point": full_cand_top["top_net_return_mean"] - full_base_top["top_net_return_mean"], "ci95_low": bootstrap_ci(top_net_mean_diff)[0], "ci95_high": bootstrap_ci(top_net_mean_diff)[1]},
        "top10_net_return_median_diff": {"point": full_cand_top["top_net_return_median"] - full_base_top["top_net_return_median"], "ci95_low": bootstrap_ci(top_net_median_diff)[0], "ci95_high": bootstrap_ci(top_net_median_diff)[1]},
        "asset_balanced_auc_diff": {"point": metric_values(oof, oof[cand_col].to_numpy())["asset_balanced_auc"] - metric_values(oof, oof[base_col].to_numpy())["asset_balanced_auc"], "ci95_low": bootstrap_ci(asset_balanced_diff)[0], "ci95_high": bootstrap_ci(asset_balanced_diff)[1]},
    }


def bh_q_values(p_values: dict[str, float | None]) -> dict[str, float | None]:
    valid = sorted(((candidate, p) for candidate, p in p_values.items() if p is not None), key=lambda item: item[1])
    m = len(valid)
    q: dict[str, float | None] = {candidate: None for candidate in p_values}
    prev = 1.0
    for rank_from_end, (candidate, p) in enumerate(reversed(valid), start=1):
        rank = m - rank_from_end + 1
        value = min(prev, p * m / rank)
        q[candidate] = float(min(value, 1.0))
        prev = value
    return q


def summarize_comparisons(oof: pd.DataFrame, metric_df: pd.DataFrame, coef_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    draws = make_fold_block_draws(oof)
    candidates = [*DELETION_CANDIDATES, *COMPRESSED_CANDIDATES]
    boot = {candidate: paired_bootstrap_comparison(oof, candidate, REFERENCE_CANDIDATE, draws) for candidate in candidates}
    deletion_q = bh_q_values({candidate: boot[candidate]["top10_success_rate_diff"]["two_sided_p"] for candidate in DELETION_CANDIDATES})
    compression_q = bh_q_values({candidate: boot[candidate]["top10_success_rate_diff"]["two_sided_p"] for candidate in COMPRESSED_CANDIDATES})
    rows: list[dict[str, Any]] = []
    factor_decisions: dict[str, str] = {}
    compression_decisions: dict[str, Any] = {}

    for candidate in candidates:
        row = comparison_point_row(oof, metric_df, coef_df, candidate, boot[candidate])
        row["comparison_family"] = "deletion_factor_role" if candidate in DELETION_CANDIDATES else "compressed_candidate"
        row["top10_success_rate_p"] = boot[candidate]["top10_success_rate_diff"]["two_sided_p"]
        row["top10_success_rate_bh_q"] = deletion_q.get(candidate) if candidate in DELETION_CANDIDATES else compression_q.get(candidate)
        if candidate in DELETION_CANDIDATES:
            decision = decide_factor_role(row)
            row["decision"] = decision
            factor_decisions[DELETION_CANDIDATES[candidate]] = decision
        else:
            decision, checks = decide_compression(row)
            row["decision"] = decision
            row["compression_gate_checks_json"] = json.dumps(json_ready(checks), ensure_ascii=False, sort_keys=True)
            compression_decisions[candidate] = {"decision": decision, "checks": checks}
        rows.append(row)

    comparison_df = pd.DataFrame(rows)
    if any(v["decision"] == "COMPRESSED_CANDIDATE_NONINFERIOR_DEVELOPMENT_ONLY" for v in compression_decisions.values()):
        global_verdict = "COMPRESSED_CORE_CANDIDATE_FROZEN"
        frozen = "M_EVENT_25" if compression_decisions.get("M_EVENT_25", {}).get("decision") == "COMPRESSED_CANDIDATE_NONINFERIOR_DEVELOPMENT_ONLY" else "M_EVENT_VOL_36"
    elif b0_unstable(oof):
        global_verdict = "NO_STABLE_FACTOR_STRUCTURE"
        frozen = REFERENCE_CANDIDATE
    elif any(decision == "REMOVABLE_NONINFERIOR" for decision in factor_decisions.values()):
        global_verdict = "PARTIAL_REDUNDANCY_IDENTIFIED_NO_LOCKED_COMPRESSION"
        frozen = REFERENCE_CANDIDATE
    else:
        global_verdict = "FULL_B0_REMAINS_REFERENCE"
        frozen = REFERENCE_CANDIDATE
    stability = {
        "bootstrap": {
            "samples": BOOTSTRAP_SAMPLES,
            "block_days": BOOTSTRAP_BLOCK_DAYS,
            "same_resampling_indices_for_all_models": True,
            "paired_draw_counts_sha256": draws.draw_hash,
            "fold_block_counts": {fold: len(blocks) for fold, blocks in draws.fold_blocks.items()},
        },
        "factor_decisions": factor_decisions,
        "compression_decisions": compression_decisions,
        "global_verdict": global_verdict,
        "frozen_candidate_for_future_oos": frozen,
    }
    return comparison_df, stability


def comparison_point_row(oof: pd.DataFrame, metric_df: pd.DataFrame, coef_df: pd.DataFrame, candidate: str, boot: dict[str, Any]) -> dict[str, Any]:
    cand_col = f"p_{candidate.lower()}_raw"
    base_col = f"p_{REFERENCE_CANDIDATE.lower()}_raw"
    raw_val = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["split"].eq("validation")) & (metric_df["probability_type"].eq("raw")) & (metric_df["row_type"].eq("metric"))].sort_values("fold")
    base_val = metric_df.loc[(metric_df["candidate"].eq(REFERENCE_CANDIDATE)) & (metric_df["split"].eq("validation")) & (metric_df["probability_type"].eq("raw")) & (metric_df["row_type"].eq("metric"))].sort_values("fold")
    fold_auc_diffs = (raw_val["roc_auc"].to_numpy() - base_val["roc_auc"].to_numpy()).astype(float).tolist()
    fold_top_diffs = (raw_val["top10_success_rate"].to_numpy() - base_val["top10_success_rate"].to_numpy()).astype(float).tolist()
    non_overlap = non_overlap_sample(oof)
    group_diffs = {}
    group_top_diffs = {}
    for group_id, group in oof.groupby("asset_group", sort=True):
        if group[TARGET].nunique() >= 2:
            group_diffs[str(group_id)] = float(roc_auc_score(group[TARGET], group[cand_col]) - roc_auc_score(group[TARGET], group[base_col]))
            group_top_diffs[str(group_id)] = fold_relative_stats_for_score(group.assign(fold="asset_group"), cand_col)["top_success_rate"] - fold_relative_stats_for_score(group.assign(fold="asset_group"), base_col)["top_success_rate"]
    side_diffs = {}
    for side, group in oof.groupby("side", sort=True):
        side_diffs[side] = float(roc_auc_score(group[TARGET], group[cand_col]) - roc_auc_score(group[TARGET], group[base_col]))
    year_top_diffs = {}
    year_auc_diffs = {}
    for year, group in oof.groupby("event_year", sort=True):
        year_top_diffs[str(year)] = fold_relative_stats_for_score(group.assign(fold=str(year)), cand_col)["top_success_rate"] - fold_relative_stats_for_score(group.assign(fold=str(year)), base_col)["top_success_rate"]
        year_auc_diffs[str(year)] = float(roc_auc_score(group[TARGET], group[cand_col]) - roc_auc_score(group[TARGET], group[base_col]))
    coef_redistribution = coefficient_redistribution(coef_df, candidate)
    return {
        "candidate": candidate,
        "baseline": REFERENCE_CANDIDATE,
        "removed_group": DELETION_CANDIDATES.get(candidate),
        "feature_count": int(raw_val["feature_count"].iloc[0]),
        "macro_auc_diff": boot["macro_auc_diff"]["point"],
        "macro_auc_diff_ci95_low": boot["macro_auc_diff"]["ci95_low"],
        "macro_auc_diff_ci95_high": boot["macro_auc_diff"]["ci95_high"],
        "fold_auc_diffs_json": json.dumps(fold_auc_diffs),
        "fold_top10_success_rate_diffs_json": json.dumps(fold_top_diffs),
        "fold_top10_not_down_more_than_1pp_count": int(sum(diff >= -0.010 for diff in fold_top_diffs)),
        "fold_top10_improve_count": int(sum(diff > 0 for diff in fold_top_diffs)),
        "fold_top10_decline_count": int(sum(diff < 0 for diff in fold_top_diffs)),
        "pr_auc_diff": boot["pr_auc_diff"]["point"],
        "pr_auc_diff_ci95_low": boot["pr_auc_diff"]["ci95_low"],
        "pr_auc_diff_ci95_high": boot["pr_auc_diff"]["ci95_high"],
        "top10_success_rate_diff": boot["top10_success_rate_diff"]["point"],
        "top10_success_rate_diff_ci95_low": boot["top10_success_rate_diff"]["ci95_low"],
        "top10_success_rate_diff_ci95_high": boot["top10_success_rate_diff"]["ci95_high"],
        "top10_net_return_mean_diff": boot["top10_net_return_mean_diff"]["point"],
        "top10_net_return_mean_diff_ci95_low": boot["top10_net_return_mean_diff"]["ci95_low"],
        "top10_net_return_mean_diff_ci95_high": boot["top10_net_return_mean_diff"]["ci95_high"],
        "top10_net_return_median_diff": boot["top10_net_return_median_diff"]["point"],
        "top10_net_return_median_diff_ci95_low": boot["top10_net_return_median_diff"]["ci95_low"],
        "top10_net_return_median_diff_ci95_high": boot["top10_net_return_median_diff"]["ci95_high"],
        "worst_fold_auc_diff": float(min(fold_auc_diffs)),
        "long_auc_diff": side_diffs.get("long"),
        "short_auc_diff": side_diffs.get("short"),
        "year_auc_diffs_json": json.dumps(year_auc_diffs, sort_keys=True),
        "year_top10_success_rate_diffs_json": json.dumps(year_top_diffs, sort_keys=True),
        "non_overlap_auc_diff": float(roc_auc_score(non_overlap[TARGET], non_overlap[cand_col]) - roc_auc_score(non_overlap[TARGET], non_overlap[base_col])) if non_overlap[TARGET].nunique() >= 2 else None,
        "non_overlap_top10_success_rate_diff": fold_relative_stats_for_score(non_overlap.assign(fold="non_overlap"), cand_col)["top_success_rate"] - fold_relative_stats_for_score(non_overlap.assign(fold="non_overlap"), base_col)["top_success_rate"],
        "asset_balanced_auc_diff": boot["asset_balanced_auc_diff"]["point"],
        "asset_balanced_auc_diff_ci95_low": boot["asset_balanced_auc_diff"]["ci95_low"],
        "asset_balanced_auc_diff_ci95_high": boot["asset_balanced_auc_diff"]["ci95_high"],
        "asset_group_auc_diffs_json": json.dumps(group_diffs, sort_keys=True),
        "asset_group_top10_success_rate_diffs_json": json.dumps(group_top_diffs, sort_keys=True),
        "asset_group_direction_flip": bool(any(v < 0 for v in group_diffs.values()) and any(v > 0 for v in group_diffs.values())),
        "train_validation_auc_gap_delta": train_validation_gap(candidate, metric_df) - train_validation_gap(REFERENCE_CANDIDATE, metric_df),
        "coefficient_redistribution_json": json.dumps(json_ready(coef_redistribution), ensure_ascii=False, sort_keys=True),
        "bootstrap_draw_hash": boot["same_draw_hash"],
    }


def train_validation_gap(candidate: str, metric_df: pd.DataFrame) -> float:
    rows = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["split"].eq("validation")) & (metric_df["probability_type"].eq("raw")) & (metric_df["row_type"].eq("metric"))]
    return float(rows["train_val_auc_gap"].mean())


def coefficient_redistribution(coef_df: pd.DataFrame, candidate: str) -> dict[str, Any]:
    full = coef_df.loc[coef_df["candidate"].eq(REFERENCE_CANDIDATE)]
    cand = coef_df.loc[coef_df["candidate"].eq(candidate)]
    out: dict[str, Any] = {}
    for group in FACTOR_GROUPS:
        full_sum = float(full.loc[full["factor_group"].eq(group), "coef"].abs().sum())
        cand_sum = float(cand.loc[cand["factor_group"].eq(group), "coef"].abs().sum())
        out[group] = {"full_abs_coef_sum": full_sum, "candidate_abs_coef_sum": cand_sum, "delta": cand_sum - full_sum}
    return out


def decide_factor_role(row: dict[str, Any]) -> str:
    q = row["top10_success_rate_bh_q"]
    side_opposite = (row["long_auc_diff"] > 0.005 and row["short_auc_diff"] < -0.005) or (row["short_auc_diff"] > 0.005 and row["long_auc_diff"] < -0.005)
    required = (
        row["top10_success_rate_diff"] < 0
        and row["top10_success_rate_diff_ci95_high"] is not None
        and row["top10_success_rate_diff_ci95_high"] < 0
        and q is not None
        and q < 0.10
        and row["fold_top10_decline_count"] >= 2
        and not (row["top10_net_return_mean_diff_ci95_low"] is not None and row["top10_net_return_mean_diff_ci95_low"] > 0.002)
        and not side_opposite
    )
    harmful = (
        row["top10_success_rate_diff"] > 0
        and row["top10_success_rate_diff_ci95_low"] is not None
        and row["top10_success_rate_diff_ci95_low"] > 0
        and q is not None
        and q < 0.10
        and row["fold_top10_improve_count"] >= 2
        and row["macro_auc_diff_ci95_low"] is not None
        and row["macro_auc_diff_ci95_low"] >= -0.003
        and row["top10_net_return_mean_diff_ci95_low"] is not None
        and row["top10_net_return_mean_diff_ci95_low"] >= -0.002
    )
    removable = (
        row["macro_auc_diff_ci95_low"] is not None
        and row["macro_auc_diff_ci95_low"] >= -0.003
        and row["top10_success_rate_diff_ci95_low"] is not None
        and row["top10_success_rate_diff_ci95_low"] >= -0.010
        and row["top10_net_return_mean_diff_ci95_low"] is not None
        and row["top10_net_return_mean_diff_ci95_low"] >= -0.002
        and row["worst_fold_auc_diff"] >= -0.005
        and row["long_auc_diff"] >= -0.010
        and row["short_auc_diff"] >= -0.010
        and row["fold_top10_not_down_more_than_1pp_count"] >= 2
    )
    if required:
        return "REQUIRED_DEVELOPMENT_EVIDENCE"
    if harmful:
        return "HARMFUL_OR_NOISY_DEVELOPMENT_EVIDENCE"
    if removable:
        return "REMOVABLE_NONINFERIOR"
    return "INCONCLUSIVE_FACTOR_ROLE"


def decide_compression(row: dict[str, Any]) -> tuple[str, dict[str, bool]]:
    year_top = json.loads(row["year_top10_success_rate_diffs_json"])
    checks = {
        "macro_auc_ci_low": row["macro_auc_diff_ci95_low"] is not None and row["macro_auc_diff_ci95_low"] >= -0.003,
        "top10_success_ci_low": row["top10_success_rate_diff_ci95_low"] is not None and row["top10_success_rate_diff_ci95_low"] >= -0.010,
        "top10_net_mean_ci_low": row["top10_net_return_mean_diff_ci95_low"] is not None and row["top10_net_return_mean_diff_ci95_low"] >= -0.002,
        "worst_fold_auc": row["worst_fold_auc_diff"] >= -0.005,
        "long_short_auc": row["long_auc_diff"] >= -0.010 and row["short_auc_diff"] >= -0.010,
        "non_overlap_auc": row["non_overlap_auc_diff"] is not None and row["non_overlap_auc_diff"] >= -0.005,
        "two_of_three_years_top10_not_below_b0": sum(float(v) >= 0 for v in year_top.values()) >= 2,
        "train_validation_gap": row["train_validation_auc_gap_delta"] <= 0.010,
        "asset_holdout_not_obviously_worse": row.get("asset_holdout_macro_auc_diff", 0.0) >= -0.005 and row.get("asset_holdout_worst_unit_auc_diff", 0.0) >= -0.010,
    }
    if all(checks.values()):
        return "COMPRESSED_CANDIDATE_NONINFERIOR_DEVELOPMENT_ONLY", checks
    return "COMPRESSED_CANDIDATE_NOT_NONINFERIOR", checks


def b0_unstable(oof: pd.DataFrame) -> bool:
    col = f"p_{REFERENCE_CANDIDATE.lower()}_raw"
    for _, group in oof.groupby("side", sort=True):
        if group[TARGET].nunique() >= 2 and roc_auc_score(group[TARGET], group[col]) < 0.50:
            return True
    for _, group in oof.groupby("event_year", sort=True):
        if group[TARGET].nunique() >= 2 and roc_auc_score(group[TARGET], group[col]) < 0.50:
            return True
    return False


def run_asset_holdout(frame: pd.DataFrame, factor_spec: dict[str, Any]) -> pd.DataFrame:
    p2_order = factor_spec["p2_original_field_order"]
    rows: list[dict[str, Any]] = []
    for fold, start, end in FOLDS:
        base_train, base_valid = fold_split(frame, start, end)
        for held_group in range(5):
            train = base_train.loc[base_train["asset_group"].ne(held_group)].copy()
            valid = base_valid.loc[base_valid["asset_group"].eq(held_group)].copy()
            if train.empty or valid.empty:
                continue
            train_assets = set(train["asset"])
            valid_assets = set(valid["asset"])
            if train_assets & valid_assets:
                raise RuntimeError("DATA_BLOCK_NOT_READY: target asset group leaked into asset-holdout training")
            for candidate in HOLDOUT_CANDIDATES:
                features = candidate_features_from_order(p2_order, candidate)
                _, p_valid, _ = fit_logit(train, valid, features)
                metrics = metric_values(valid, p_valid)
                metrics.update(
                    {
                        "candidate": candidate,
                        "feature_count": len(features),
                        "fold": fold,
                        "held_asset_group": held_group,
                        "train_n": int(len(train)),
                        "validation_n": int(len(valid)),
                        "train_asset_group_excludes_target": True,
                        "train_key_hash": row_key_hash(train),
                        "validation_key_hash": row_key_hash(valid),
                    }
                )
                rows.append(metrics)
    return pd.DataFrame(rows)


def update_compression_holdout_checks(comparison_df: pd.DataFrame, holdout_df: pd.DataFrame) -> pd.DataFrame:
    base = holdout_df.loc[holdout_df["candidate"].eq(REFERENCE_CANDIDATE)].sort_values(["fold", "held_asset_group"])
    out = comparison_df.copy()
    for candidate in COMPRESSED_CANDIDATES:
        cand = holdout_df.loc[holdout_df["candidate"].eq(candidate)].sort_values(["fold", "held_asset_group"])
        merged = cand.merge(base[["fold", "held_asset_group", "roc_auc"]], on=["fold", "held_asset_group"], suffixes=("_candidate", "_base"))
        diffs = merged["roc_auc_candidate"] - merged["roc_auc_base"]
        mask = out["candidate"].eq(candidate)
        out.loc[mask, "asset_holdout_macro_auc_diff"] = float(diffs.mean())
        out.loc[mask, "asset_holdout_worst_unit_auc_diff"] = float(diffs.min())
        out.loc[mask, "asset_holdout_direction_flip"] = bool((diffs > 0).any() and (diffs < 0).any())
        row = out.loc[mask].iloc[0].to_dict()
        decision, checks = decide_compression(row)
        out.loc[mask, "decision"] = decision
        out.loc[mask, "compression_gate_checks_json"] = json.dumps(json_ready(checks), ensure_ascii=False, sort_keys=True)
    return out


def build_decile_metrics(oof: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for candidate in ALL_CANDIDATES:
        raw_col = f"p_{candidate.lower()}_raw"
        for scope_type, scope, frame in [("OOF", "fold_relative_all", oof), ("OOF", "legacy_pooled_raw_diagnostic", oof)]:
            if scope == "fold_relative_all":
                frames = []
                for fold, group in frame.groupby("fold", sort=True):
                    _, dec = percentile_and_decile(group[raw_col].to_numpy())
                    g = group.copy()
                    g["_decile"] = dec
                    frames.append(g)
                tmp = pd.concat(frames, ignore_index=True)
            else:
                _, dec = percentile_and_decile(frame[raw_col].to_numpy())
                tmp = frame.copy()
                tmp["_decile"] = dec
            base = float(tmp[TARGET].mean())
            for decile in range(1, 11):
                group = tmp.loc[tmp["_decile"].eq(decile)]
                rows.append(
                    {
                        "candidate": candidate,
                        "scope_type": scope_type,
                        "scope": scope,
                        "decile": decile,
                        "n": int(len(group)),
                        "success_rate": float(group[TARGET].mean()) if len(group) else None,
                        "uplift": float(group[TARGET].mean() - base) if len(group) else None,
                        "net_return_mean": float(group[NET_RETURN].mean()) if len(group) else None,
                        "net_return_median": float(group[NET_RETURN].median()) if len(group) else None,
                    }
                )
        for fold, frame in oof.groupby("fold", sort=True):
            _, dec = percentile_and_decile(frame[raw_col].to_numpy())
            base = float(frame[TARGET].mean())
            for d in range(1, 11):
                group = frame.loc[dec == d]
                rows.append({"candidate": candidate, "scope_type": "fold", "scope": str(fold), "decile": d, "n": int(len(group)), "success_rate": float(group[TARGET].mean()) if len(group) else None, "uplift": float(group[TARGET].mean() - base) if len(group) else None, "net_return_mean": float(group[NET_RETURN].mean()) if len(group) else None, "net_return_median": float(group[NET_RETURN].median()) if len(group) else None})
    return pd.DataFrame(rows)


def build_only_group_metrics(metric_df: pd.DataFrame, oof: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for candidate in ONLY_CANDIDATES:
        raw_col = f"p_{candidate.lower()}_raw"
        vals = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["split"].eq("validation")) & (metric_df["probability_type"].eq("raw")) & (metric_df["row_type"].eq("metric"))]
        row = {
            "candidate": candidate,
            "factor_group": ONLY_CANDIDATES[candidate],
            "feature_count": int(vals["feature_count"].iloc[0]),
            "macro_auc": float(vals["roc_auc"].mean()),
            "worst_fold_auc": float(vals["roc_auc"].min()),
            "macro_pr_auc": float(vals["pr_auc"].mean()),
            "fold_relative_top10_success_rate": fold_relative_top_stats(oof, raw_col)["success_rate"],
            "fold_relative_top10_net_return_mean": fold_relative_top_stats(oof, raw_col)["net_return_mean"],
            "long_auc": stratum_auc(oof, raw_col, "side", "long"),
            "short_auc": stratum_auc(oof, raw_col, "side", "short"),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def stratum_auc(oof: pd.DataFrame, score_col: str, column: str, value: str) -> float | None:
    group = oof.loc[oof[column].astype(str).eq(value)]
    return float(roc_auc_score(group[TARGET], group[score_col])) if len(group) and group[TARGET].nunique() >= 2 else None


def coefficient_stability(frame: pd.DataFrame, coef_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate, cand_group in coef_df.groupby("candidate", sort=True):
        for base_feature, group in cand_group.groupby("base_feature", sort=True):
            signs = [int(np.sign(v)) for v in group.sort_values("fold")["coef"].tolist()]
            rows.append(
                {
                    "candidate": candidate,
                    "base_feature": base_feature,
                    "factor_group": feature_group_for(base_feature),
                    "fold_coefs_json": json.dumps({row.fold: float(row.coef) for row in group.itertuples()}, sort_keys=True),
                    "same_nonzero_sign": bool(0 not in signs and len(set(signs)) == 1),
                    "abs_coef_median": float(group["coef"].abs().median()),
                    "abs_coef_max": float(group["coef"].abs().max()),
                }
            )
    corr_summary: dict[str, Any] = {}
    for group, features in FACTOR_GROUPS.items():
        numeric_features = [f for f in features if f != "t1_volatility_state_p0r"]
        corr = frame[numeric_features].apply(pd.to_numeric, errors="coerce").corr(method="spearman").abs()
        high_pairs = []
        vals = []
        for i, left in enumerate(numeric_features):
            for right in numeric_features[i + 1 :]:
                value = corr.loc[left, right]
                if pd.notna(value):
                    vals.append(float(value))
                    if value >= 0.8:
                        high_pairs.append({"left": left, "right": right, "abs_spearman": float(value)})
        corr_summary[group] = {
            "numeric_feature_count": len(numeric_features),
            "median_abs_spearman": float(np.median(vals)) if vals else None,
            "max_abs_spearman": float(np.max(vals)) if vals else None,
            "high_corr_pair_count_abs_ge_0_8": len(high_pairs),
            "high_corr_pairs_top20": sorted(high_pairs, key=lambda x: x["abs_spearman"], reverse=True)[:20],
        }
    return pd.DataFrame(rows), corr_summary


def build_strata_summary(oof: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for candidate in [REFERENCE_CANDIDATE, "M_EVENT_25", "M_EVENT_VOL_36"]:
        col = f"p_{candidate.lower()}_raw"
        out[candidate] = {}
        for kind in ["side", "year", "asset_group"]:
            labels = stratum_labels(oof, kind)
            tmp = oof.copy()
            tmp["_stratum"] = labels
            out[candidate][kind] = {}
            for value, group in tmp.groupby("_stratum", observed=True):
                if len(group) < 20 or group[TARGET].nunique() < 2:
                    continue
                top = fold_relative_stats_for_score(group.assign(fold=str(value)), col)
                out[candidate][kind][str(value)] = {
                    "n": int(len(group)),
                    "success_rate": float(group[TARGET].mean()),
                    "auc": float(roc_auc_score(group[TARGET], group[col])),
                    "top10_success_rate": top["top_success_rate"],
                    "top10_net_return_mean": top["top_net_return_mean"],
                    "top10_net_return_median": top["top_net_return_median"],
                }
    return out


def final_refit_metrics(frame: pd.DataFrame, factor_spec: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    p2_order = factor_spec["p2_original_field_order"]
    for candidate in [REFERENCE_CANDIDATE, "M_EVENT_25", "M_EVENT_VOL_36"]:
        features = candidate_features_from_order(p2_order, candidate)
        p_train, _, _ = fit_logit(frame, frame, features)
        out[candidate] = {
            "train_rows": int(len(frame)),
            "train_max_ts": frame["ts"].max(),
            "train_max_label_end": frame[LABEL_END].max(),
            "feature_count": len(features),
            "train_metrics_raw": metric_values(frame, p_train),
        }
    return out


def rebuild_global_verdict(comparison_df: pd.DataFrame, oof: pd.DataFrame) -> dict[str, Any]:
    compression_pass = comparison_df.loc[comparison_df["comparison_family"].eq("compressed_candidate") & comparison_df["decision"].eq("COMPRESSED_CANDIDATE_NONINFERIOR_DEVELOPMENT_ONLY"), "candidate"].tolist()
    factor_decisions = dict(zip(comparison_df.loc[comparison_df["comparison_family"].eq("deletion_factor_role"), "removed_group"], comparison_df.loc[comparison_df["comparison_family"].eq("deletion_factor_role"), "decision"]))
    if compression_pass:
        verdict = "COMPRESSED_CORE_CANDIDATE_FROZEN"
        frozen = "M_EVENT_25" if "M_EVENT_25" in compression_pass else "M_EVENT_VOL_36"
    elif b0_unstable(oof):
        verdict = "NO_STABLE_FACTOR_STRUCTURE"
        frozen = REFERENCE_CANDIDATE
    elif any(v == "REMOVABLE_NONINFERIOR" for v in factor_decisions.values()):
        verdict = "PARTIAL_REDUNDANCY_IDENTIFIED_NO_LOCKED_COMPRESSION"
        frozen = REFERENCE_CANDIDATE
    else:
        verdict = "FULL_B0_REMAINS_REFERENCE"
        frozen = REFERENCE_CANDIDATE
    return {"global_verdict": verdict, "frozen_candidate_for_future_oos": frozen, "factor_decisions": factor_decisions}


def fmt(value: Any, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "NA"
    return f"{float(value):.{digits}f}"


def pct(value: Any) -> str:
    if value is None:
        return "NA"
    return f"{100 * float(value):.2f}%"


def write_reports(summary: dict[str, Any], metric_df: pd.DataFrame, comparison_df: pd.DataFrame, only_df: pd.DataFrame, holdout_df: pd.DataFrame, decile_df: pd.DataFrame, coef_summary_df: pd.DataFrame) -> None:
    candidate_summary = summary["development"]["candidate_summary"]
    b0 = candidate_summary[REFERENCE_CANDIDATE]
    lines = [
        "# BIN-1D-MA7-CTP P4：MA7核心因子消融、模型压缩与高分穿越稳定性审计",
        "",
        f"> {summary['generated_at_utc']}。状态：`{STATUS}`。",
        "> `2022-2024 IS REUSED DEVELOPMENT HISTORY, NOT NEW BLIND OOS`。",
        "> P4 不是策略版本，不生成仓位、权益曲线、live spec、runner handoff 或 live-ready 产物。",
        "",
        "## 1. 全局裁决",
        "",
        f"**{summary['decision']['global_verdict']}** / `{STATUS}`；未来新 OOS 候选：`{summary['decision']['frozen_candidate_for_future_oos']}`。",
        f"- B0 fold-relative Top10 成功率 `{pct(b0['fold_relative_top10']['success_rate'])}`，uplift `{fmt(b0['fold_relative_top10']['uplift_vs_all_oof'])}`，净收益均值/中位数 `{fmt(b0['fold_relative_top10']['net_return_mean'])}` / `{fmt(b0['fold_relative_top10']['net_return_median'])}`。",
        f"- B0 Macro AUC `{fmt(b0['macro_auc'])}`，OOF raw AUC `{fmt(b0['oof_raw']['roc_auc'])}`，20 日 non-overlap AUC `{fmt(summary['non_overlap']['R_FULL_B0_69']['auc'])}`。",
        f"- HYPE/2025+/TradFi 隔离：`{summary['hype_isolation']['event_rows']}/{summary['input_integrity']['post_2025_event_rows_read']}/{summary['tradfi_audit']['strict_sample_known_tradfi_events']}`。",
        "",
        "## 2. 数据与隔离审计",
        "",
        "| Item | Value |",
        "| --- | ---: |",
        f"| 原始 pre-2025 MA7 事件 | {summary['raw_event_audit_without_labels']['n']} |",
        f"| 严格样本 | {summary['strict_event_audit']['n']} |",
        f"| 资产 | {summary['strict_event_audit']['assets']} |",
        f"| long / short | {summary['strict_event_audit']['long']} / {summary['strict_event_audit']['short']} |",
        f"| 正例率 | {pct(summary['strict_event_audit']['positive_rate'])} |",
        f"| 最早 / 最晚事件 | {summary['strict_event_audit']['min_ts']} / {summary['strict_event_audit']['max_ts']} |",
        f"| 最大 label_end_ts_20d | {summary['strict_event_audit']['max_label_end_ts_20d']} |",
        f"| 非穿越 / 重复 asset+ts / 空标签 / 不完整20日路径 | {summary['strict_event_audit']['non_cross']} / {summary['strict_event_audit']['duplicate_asset_ts']} / {summary['strict_event_audit']['null_target']} / {summary['strict_event_audit']['incomplete_20d_future_path']} |",
        f"| feature_known_at < / == / > entry_ts | {summary['strict_event_audit']['feature_known_at_lt_entry_ts']} / {summary['strict_event_audit']['feature_known_at_eq_entry_ts']} / {summary['strict_event_audit']['feature_known_at_gt_entry_ts']} |",
        f"| HYPE / 已知 TradFi 严格事件 | {summary['strict_event_audit']['hype']} / {summary['strict_event_audit']['known_tradfi_events']} |",
        "",
        "## 3. 69个特征到六组的映射",
        "",
        "| Group | Count | Fields |",
        "| --- | ---: | --- |",
    ]
    for group, item in summary["factor_group_spec"]["factor_groups"].items():
        lines.append(f"| `{group}` | {item['field_count']} | {', '.join(f'`{x}`' for x in item['fields'])} |")
    lines.extend(["", "## 4. 候选模型及特征数量", "", "| Candidate | Role | Feature count |", "| --- | --- | ---: |"])
    for candidate, item in summary["factor_group_spec"]["candidate_models"].items():
        lines.append(f"| `{candidate}` | {item['role']} | {item['feature_count']} |")
    lines.extend(["", "## 5. 每个模型D1/D2/D3训练期和验证期指标", "", "| Candidate | Fold | Train n | Train AUC | Train Top10 | Val n | Val AUC | Val PR-AUC | Val Top10 | Val Top10净均值 | AUC gap | Uplift gap |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for candidate in ALL_CANDIDATES:
        for fold in ["D1", "D2", "D3"]:
            tr = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["fold"].eq(fold)) & (metric_df["split"].eq("training")) & (metric_df["probability_type"].eq("raw"))].iloc[0]
            va = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["fold"].eq(fold)) & (metric_df["split"].eq("validation")) & (metric_df["probability_type"].eq("raw"))].iloc[0]
            lines.append(f"| `{candidate}` | {fold} | {int(tr.eval_n)} | {fmt(tr.roc_auc)} | {pct(tr.top10_success_rate)} | {int(va.eval_n)} | {fmt(va.roc_auc)} | {fmt(va.pr_auc)} | {pct(va.top10_success_rate)} | {fmt(va.top10_net_return_mean)} | {fmt(va.train_val_auc_gap)} | {fmt(va.train_val_top_uplift_gap)} |")
    lines.extend(["", "## 6. B0复现对账", "", "| Metric | P4 B0 | P3R B0 reference |", "| --- | ---: | ---: |"])
    p3r_b0 = summary["p3r_b0_reference"]
    lines.extend(
        [
            f"| Macro AUC | {fmt(b0['macro_auc'])} | {fmt(p3r_b0['macro_auc'])} |",
            f"| Worst fold AUC | {fmt(b0['worst_fold_auc'])} | {fmt(p3r_b0['worst_fold_auc'])} |",
            f"| OOF raw AUC | {fmt(b0['oof_raw']['roc_auc'])} | {fmt(p3r_b0['oof_raw_auc'])} |",
            f"| legacy pooled-raw Top10 | {pct(b0['legacy_pooled_raw_top10']['success_rate'])} | {pct(p3r_b0['legacy_top10_success_rate'])} |",
        ]
    )
    lines.extend(["", "## 7. 六个删除式消融结果", "", comparison_markdown(comparison_df.loc[comparison_df["comparison_family"].eq("deletion_factor_role")])])
    lines.extend(["", "## 8. 六个单组模型结果", "", "| Candidate | Group | Feature count | Macro AUC | Worst fold AUC | Top10成功率 | Top10净均值 | Long AUC | Short AUC |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for row in only_df.itertuples():
        lines.append(f"| `{row.candidate}` | `{row.factor_group}` | {row.feature_count} | {fmt(row.macro_auc)} | {fmt(row.worst_fold_auc)} | {pct(row.fold_relative_top10_success_rate)} | {fmt(row.fold_relative_top10_net_return_mean)} | {fmt(row.long_auc)} | {fmt(row.short_auc)} |")
    lines.extend(["", "## 9. 两个压缩模型结果", "", comparison_markdown(comparison_df.loc[comparison_df["comparison_family"].eq("compressed_candidate")])])
    lines.extend(["", "## 10. fold-relative Top 10%结果", "", "| Candidate | Top10 n | 成功率 | Uplift | 净收益均值 | 净收益中位数 | 最差fold | fold std |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for candidate, item in candidate_summary.items():
        top = item["fold_relative_top10"]
        lines.append(f"| `{candidate}` | {top['n']} | {pct(top['success_rate'])} | {fmt(top['uplift_vs_all_oof'])} | {fmt(top['net_return_mean'])} | {fmt(top['net_return_median'])} | {pct(top['worst_fold_success_rate'])} | {fmt(top['fold_success_rate_std'])} |")
    lines.extend(["", "## 11. legacy pooled-raw Top 10%对账", "", "| Candidate | Top10 n | 成功率 | Uplift | 净收益均值 | 净收益中位数 | Bottom10 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for candidate, item in candidate_summary.items():
        top = item["legacy_pooled_raw_top10"]
        lines.append(f"| `{candidate}` | {top['n']} | {pct(top['success_rate'])} | {fmt(top['uplift_vs_all_oof'])} | {fmt(top['net_return_mean'])} | {fmt(top['net_return_median'])} | {pct(top['bottom_success_rate'])} |")
    lines.extend(["", "## 12. 20日non-overlap结果", "", "| Candidate | n | AUC | Top10成功率 | Top10净均值 |", "| --- | ---: | ---: | ---: | ---: |"])
    for candidate, item in summary["non_overlap"].items():
        lines.append(f"| `{candidate}` | {item['n']} | {fmt(item['auc'])} | {pct(item['top10_success_rate'])} | {fmt(item['top10_net_return_mean'])} |")
    lines.extend(["", "## 13. long/short分层", "", strata_table(summary["strata"], "side")])
    lines.extend(["", "## 14. 年份分层", "", strata_table(summary["strata"], "year")])
    lines.extend(["", "## 15. 资产五组分层", "", strata_table(summary["strata"], "asset_group")])
    lines.extend(["", "## 16. 15单元时间×资产holdout", "", holdout_table(holdout_df)])
    lines.extend(["", "## 17. 系数稳定性与相关性", "", "| Group | high | same-sign coef ratio | median | max | high-corr pairs |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for group, corr in summary["coefficient_correlation"].items():
        group_coefs = coef_summary_df.loc[(coef_summary_df["candidate"].eq(REFERENCE_CANDIDATE)) & (coef_summary_df["factor_group"].eq(group))]
        lines.append(f"| `{group}` | {corr['numeric_feature_count']} | {fmt(group_coefs['same_nonzero_sign'].mean() if len(group_coefs) else None)} | {fmt(group_coefs['abs_coef_median'].median() if len(group_coefs) else None)} | {fmt(group_coefs['abs_coef_max'].max() if len(group_coefs) else None)} | {corr['high_corr_pair_count_abs_ge_0_8']} |")
    lines.extend(["", "## 18. 训练-验证差距", "", "| Candidate | Avg AUC gap | Avg Top10 uplift gap | Overfit folds |", "| --- | ---: | ---: | --- |"])
    for candidate, item in candidate_summary.items():
        lines.append(f"| `{candidate}` | {fmt(item['train_validation_auc_gap_mean'])} | {fmt(item['train_validation_top_uplift_gap_mean'])} | {', '.join(item['overfit_warning_folds']) or ''} |")
    lines.extend(["", "## 19. bootstrap置信区间与BH校正", "", comparison_markdown(comparison_df)])
    lines.extend(["", "## 20. 因子角色裁决", "", "| Group | Decision |", "| --- | --- |"])
    for group, decision in summary["decision"]["factor_decisions"].items():
        lines.append(f"| `{group}` | `{decision}` |")
    lines.extend(["", "## 21. 压缩模型裁决", "", "| Candidate | Decision | Gate checks |", "| --- | --- | --- |"])
    for row in comparison_df.loc[comparison_df["comparison_family"].eq("compressed_candidate")].itertuples():
        lines.append(f"| `{row.candidate}` | `{row.decision}` | `{row.compression_gate_checks_json}` |")
    lines.extend(["", "## 22. 为什么本轮不是策略", "", "- P4 只给 MA7 穿越事件打概率分，不产生持仓、仓位、组合调度、权益曲线、年化收益或 Sharpe。", "- 2022-2024 已经被 P2/P3R 多次查看，只能视为开发期 walk-forward 证据。", "- 即使压缩模型通过，也只是供未来全新 OOS 验证的候选，不是 promotion、dry-run 或 live-ready。", "", "## 23. 后续真正新OOS要求", "", "- 需要等待 2026-06-30 后此前未参与特征设计、候选冻结或模型选择的新 donor 数据。", "- 新 OOS 必须先复用本 P4 锁定的候选、因子组、Top10 fold 内排名、校准和非劣门槛；不能用 2024 单年或本次结果再调结构。"])
    atomic_write_text(REPORT_PATH, "\n".join(lines) + "\n")

    audit_lines = [
        "# BIN-1D-MA7-CTP P4 建模审计",
        "",
        f"状态：`{STATUS}`。裁决：`{summary['decision']['global_verdict']}`。",
        "",
        "## 冻结顺序",
        "",
        f"- P4 合同 SHA256：`{summary['contract_lock']['contract_sha256']}`。",
        f"- factor group spec SHA256：`{summary['contract_lock']['factor_group_spec_sha256']}`。",
        f"- contract lock 状态：`{summary['contract_lock']['status']}`；`labels_read=false` 审计行数 `{summary['contract_lock']['event_filter_audit_without_labels']['n']}`。",
        "",
        "## 数据与隔离",
        "",
        f"- 严格样本 `{summary['strict_event_audit']['n']}`；HYPE/2025+/TradFi `{summary['strict_event_audit']['hype']}/{summary['input_integrity']['post_2025_event_rows_read']}/{summary['strict_event_audit']['known_tradfi_events']}`。",
        f"- 时间门禁 `< / == / >` 为 `{summary['strict_event_audit']['feature_known_at_lt_entry_ts']}/{summary['strict_event_audit']['feature_known_at_eq_entry_ts']}/{summary['strict_event_audit']['feature_known_at_gt_entry_ts']}`。",
        "- 所有候选使用同一 D1/D2/D3 训练/验证行；asset holdout 训练排除目标资产组。",
        "",
        "## 模型与校准",
        "",
        "- 所有候选为 pooled Logistic Regression，训练折拟合中位数、one-hot 和 StandardScaler；没有 long/short 独立头。",
        "- D1 校准保持 raw；D2 只用 D1 OOF；D3 只用 D1-D2 OOF；raw 与 forward-calibrated 概率分列保存。",
        f"- paired bootstrap 使用 fold 内 28 日 UTC 日期块，同 draw hash：`{summary['stability']['bootstrap']['paired_draw_counts_sha256']}`。",
        "",
        "## 禁止产物",
        "",
        "- 未生成 HYPE reveal、2025+ 预测、策略仓位、账户权益、Sharpe、live spec、runner handoff 或交易路径 HTML。",
    ]
    atomic_write_text(AUDIT_PATH, "\n".join(audit_lines) + "\n")


def comparison_markdown(df: pd.DataFrame) -> str:
    lines = [
        "| Candidate | Decision | Macro AUC diff 95% CI | Top10 diff 95% CI | q | Net mean diff 95% CI | Worst fold | Long | Short | Non-overlap | Asset-holdout macro |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in df.itertuples():
        q = getattr(row, "top10_success_rate_bh_q", None)
        holdout = getattr(row, "asset_holdout_macro_auc_diff", None)
        lines.append(
            f"| `{row.candidate}` | `{row.decision}` | {fmt(row.macro_auc_diff)} [{fmt(row.macro_auc_diff_ci95_low)}, {fmt(row.macro_auc_diff_ci95_high)}] | "
            f"{fmt(row.top10_success_rate_diff)} [{fmt(row.top10_success_rate_diff_ci95_low)}, {fmt(row.top10_success_rate_diff_ci95_high)}] | {fmt(q)} | "
            f"{fmt(row.top10_net_return_mean_diff)} [{fmt(row.top10_net_return_mean_diff_ci95_low)}, {fmt(row.top10_net_return_mean_diff_ci95_high)}] | "
            f"{fmt(row.worst_fold_auc_diff)} | {fmt(row.long_auc_diff)} | {fmt(row.short_auc_diff)} | {fmt(row.non_overlap_auc_diff)} | {fmt(holdout)} |"
        )
    return "\n".join(lines)


def strata_table(strata: dict[str, Any], kind: str) -> str:
    lines = ["| Candidate | Stratum | n | AUC | Top10成功率 | Top10净均值 |", "| --- | --- | ---: | ---: | ---: | ---: |"]
    for candidate, by_kind in strata.items():
        for value, item in by_kind[kind].items():
            lines.append(f"| `{candidate}` | `{value}` | {item['n']} | {fmt(item['auc'])} | {pct(item['top10_success_rate'])} | {fmt(item['top10_net_return_mean'])} |")
    return "\n".join(lines)


def holdout_table(holdout_df: pd.DataFrame) -> str:
    base = holdout_df.loc[holdout_df["candidate"].eq(REFERENCE_CANDIDATE)]
    lines = ["| Candidate | 15-unit Macro AUC | Worst unit AUC | Top10成功率 | 资产组方向翻转 |", "| --- | ---: | ---: | ---: | --- |"]
    for candidate, group in holdout_df.groupby("candidate", sort=True):
        top_rates = [row.top10_success_rate for row in group.itertuples() if row.top10_success_rate is not None]
        if candidate == REFERENCE_CANDIDATE:
            flip = False
        else:
            merged = group.merge(base[["fold", "held_asset_group", "roc_auc"]], on=["fold", "held_asset_group"], suffixes=("_candidate", "_base"))
            diffs = merged["roc_auc_candidate"] - merged["roc_auc_base"]
            flip = bool((diffs > 0).any() and (diffs < 0).any())
        lines.append(f"| `{candidate}` | {fmt(group['roc_auc'].mean())} | {fmt(group['roc_auc'].min())} | {pct(np.mean(top_rates) if top_rates else None)} | `{flip}` |")
    return "\n".join(lines)


def build_manifest(paths: Iterable[Path], summary: dict[str, Any]) -> None:
    artifacts = []
    for path in paths:
        if path.exists():
            artifacts.append({"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    atomic_write_json(
        MANIFEST_PATH,
        {
            "family": "Binance-1D-MA7-Cross-Trend-Probability",
            "alias": "BIN-1D-MA7-CTP",
            "experiment": "P4 Core Factor Ablation + Compressed Tail-Ranking Audit",
            "generated_at_utc": datetime.now(UTC),
            "status": STATUS,
            "decision": summary["decision"]["global_verdict"],
            "holdout_read": False,
            "hype_asset_excluded": HYPE_ASSET,
            "hype_reveal_executed": False,
            "post_2025_event_rows_read": 0,
            "post_2025_predictions_written": 0,
            "no_strategy_no_portfolio_no_live_artifact": True,
            "input_lineage": summary["input_integrity"],
            "artifacts": artifacts,
        },
    )


def main() -> None:
    args = parse_args()
    if not args.run:
        raise SystemExit("Pass --run to execute P4.")
    ensure_output_policy(args.force)
    factor_spec = write_factor_group_spec()
    input_audit = validate_inputs(factor_spec)
    raw_event_audit = count_events_without_labels()
    contract_lock = {
        "status": "FROZEN_BEFORE_P4_LABEL_READ",
        "generated_at_utc": datetime.now(UTC),
        "contract_sha256": sha256_file(SPEC_PATH),
        "factor_group_spec_sha256": sha256_file(FACTOR_GROUP_SPEC_PATH),
        "factor_group_payload_sha256": factor_spec["payload_sha256"],
        "p2_feature_spec_sha256": input_audit["p2_feature_spec_sha256"],
        "p3r_feature_spec_sha256": input_audit["p3r_feature_spec_sha256"],
        "p2_summary_sha256": input_audit["p2_summary_sha256"],
        "p3r_summary_sha256": input_audit["p3r_summary_sha256"],
        "candidate_set_frozen": list(ALL_CANDIDATES),
        "noninferiority_thresholds_frozen": {
            "macro_auc_ci_low": -0.003,
            "top10_success_ci_low": -0.010,
            "top10_net_mean_ci_low": -0.002,
            "worst_fold_auc": -0.005,
            "side_auc": -0.010,
            "non_overlap_auc_compression": -0.005,
            "train_validation_gap_delta": 0.010,
        },
        "event_filter_audit_without_labels": raw_event_audit,
    }
    atomic_write_json(CONTRACT_LOCK_PATH, contract_lock)
    print("P4 contract lock written; loading labels after lock.", flush=True)

    frame, strict_audit = load_strict_event_panel(factor_spec)
    metric_df, oof, coef_df, development = run_development(frame, factor_spec)
    comparison_df, stability = summarize_comparisons(oof, metric_df, coef_df)
    holdout_df = run_asset_holdout(frame, factor_spec)
    comparison_df = update_compression_holdout_checks(comparison_df, holdout_df)
    verdict_update = rebuild_global_verdict(comparison_df, oof)
    stability["factor_decisions"] = verdict_update["factor_decisions"]
    stability["compression_decisions"] = {
        row.candidate: {
            "decision": row.decision,
            "checks": json.loads(row.compression_gate_checks_json),
        }
        for row in comparison_df.loc[
            comparison_df["comparison_family"].eq("compressed_candidate")
        ].itertuples()
    }
    stability["global_verdict"] = verdict_update["global_verdict"]
    stability["frozen_candidate_for_future_oos"] = verdict_update["frozen_candidate_for_future_oos"]

    decile_df = build_decile_metrics(oof)
    only_df = build_only_group_metrics(metric_df, oof)
    coef_summary_df, corr_summary = coefficient_stability(frame, coef_df)
    non_overlap = {}
    non_overlap_frame = non_overlap_sample(oof)
    for candidate in ALL_CANDIDATES:
        col = f"p_{candidate.lower()}_raw"
        top = fold_relative_stats_for_score(non_overlap_frame.assign(fold="non_overlap"), col)
        non_overlap[candidate] = {
            "n": int(len(non_overlap_frame)),
            "auc": float(roc_auc_score(non_overlap_frame[TARGET], non_overlap_frame[col])) if non_overlap_frame[TARGET].nunique() >= 2 else None,
            "top10_success_rate": top["top_success_rate"],
            "top10_net_return_mean": top["top_net_return_mean"],
            "top10_net_return_median": top["top_net_return_median"],
        }
    strata = build_strata_summary(oof)
    final_metrics = final_refit_metrics(frame, factor_spec)
    p3r_summary = load_json(P3R_SUMMARY_PATH)
    p3r_b0 = p3r_summary["development"]["candidate_summary"]["B0_P2_F1_LOGIT"]

    summary: dict[str, Any] = {
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "alias": "BIN-1D-MA7-CTP",
        "experiment": "P4 Core Factor Ablation + Compressed Tail-Ranking Audit",
        "generated_at_utc": datetime.now(UTC),
        "status": STATUS,
        "objective_ma7_cross_only": True,
        "development_history_warning": "2022-2024 IS REUSED DEVELOPMENT HISTORY, NOT NEW BLIND OOS",
        "one_pooled_model_only": True,
        "independent_long_short_heads_trained": 0,
        "no_strategy_no_portfolio_no_live_artifact": True,
        "input_integrity": input_audit,
        "contract_lock": contract_lock,
        "factor_group_spec": factor_spec,
        "raw_event_audit_without_labels": raw_event_audit,
        "strict_event_audit": strict_audit,
        "tradfi_audit": {"strict_sample_known_tradfi_events": strict_audit["known_tradfi_events"], "known_base_symbols": sorted(TRADFI_BASE_SYMBOLS)},
        "hype_isolation": {"asset": HYPE_ASSET, "input_rows": input_audit["panel_hype_rows"], "event_rows": strict_audit["hype"], "oof_rows": int(oof["asset"].eq(HYPE_ASSET).sum()), "model_card_rows": 0, "hype_reveal_executed": False},
        "hyper_preservation": {"asset": HYPER_ASSET, "input_rows": input_audit["panel_hyper_rows"], "event_rows": strict_audit["hyper"], "oof_rows": int(oof["asset"].eq(HYPER_ASSET).sum())},
        "development": development,
        "comparisons": comparison_df.to_dict(orient="records"),
        "only_group_metrics": only_df.to_dict(orient="records"),
        "asset_holdout": {
            "unit_count": int(len(holdout_df[["fold", "held_asset_group"]].drop_duplicates())),
            "model_metrics": holdout_df.to_dict(orient="records"),
        },
        "stability": stability,
        "non_overlap": non_overlap,
        "strata": strata,
        "coefficient_correlation": corr_summary,
        "final_refit_pre_2025": final_metrics,
        "p3r_b0_reference": {
            "macro_auc": p3r_b0["macro_auc"],
            "worst_fold_auc": p3r_b0["worst_fold_auc"],
            "oof_raw_auc": p3r_b0["oof_raw"]["roc_auc"],
            "legacy_top10_success_rate": p3r_b0["decile_raw"]["top_success_rate"],
        },
        "decision": {
            "global_verdict": stability["global_verdict"],
            "frozen_candidate_for_future_oos": stability["frozen_candidate_for_future_oos"],
            "factor_decisions": stability["factor_decisions"],
            "compression_decisions": {
                row.candidate: row.decision
                for row in comparison_df.loc[comparison_df["comparison_family"].eq("compressed_candidate")].itertuples()
            },
            "training_executed": True,
            "status": STATUS,
            "not_live_ready": True,
            "no_2025_plus_historical_test": True,
        },
    }
    model_card = {
        "family": summary["family"],
        "alias": summary["alias"],
        "experiment": summary["experiment"],
        "model_role": "pooled direction-aligned MA7-cross core factor ablation and compressed tail-ranking audit",
        "candidates": {candidate: candidate_features_from_order(factor_spec["p2_original_field_order"], candidate) for candidate in ALL_CANDIDATES},
        "factor_group_spec_sha256": sha256_file(FACTOR_GROUP_SPEC_PATH),
        "contract_sha256": sha256_file(SPEC_PATH),
        "seed": SEED,
        "status": STATUS,
        "global_verdict": summary["decision"]["global_verdict"],
        "frozen_candidate_for_future_oos": summary["decision"]["frozen_candidate_for_future_oos"],
        "calibration": {candidate: development["candidate_summary"][candidate]["calibration"] for candidate in ALL_CANDIDATES},
        "hype_rows": 0,
        "hype_reveal_executed": False,
        "post_2025_event_rows_read": 0,
        "post_2025_predictions_written": 0,
        "known_tradfi_strict_sample_rows": 0,
        "not_live_ready": True,
        "prohibited_uses": ["position sizing", "account backtest", "live trading", "long/short head deployment", "continuation or exit modeling", "HYPE reveal", "2025+ prediction"],
    }

    atomic_write_parquet(FOLD_METRICS_PATH, metric_df)
    atomic_write_parquet(OOF_PREDICTIONS_PATH, oof)
    atomic_write_parquet(ABLATION_COMPARISONS_PATH, comparison_df)
    atomic_write_parquet(ONLY_GROUP_METRICS_PATH, only_df)
    atomic_write_parquet(ASSET_HOLDOUT_METRICS_PATH, holdout_df)
    atomic_write_parquet(DECILE_METRICS_PATH, decile_df)
    atomic_write_parquet(COEFFICIENT_STABILITY_PATH, coef_summary_df)
    atomic_write_json(MODEL_CARD_PATH, model_card)
    atomic_write_json(SUMMARY_PATH, summary)
    write_reports(summary, metric_df, comparison_df, only_df, holdout_df, decile_df, coef_summary_df)
    build_manifest(
        [
            SPEC_PATH,
            FACTOR_GROUP_SPEC_PATH,
            SCRIPT_PATH,
            TEST_PATH,
            CONTRACT_LOCK_PATH,
            FOLD_METRICS_PATH,
            OOF_PREDICTIONS_PATH,
            ABLATION_COMPARISONS_PATH,
            ONLY_GROUP_METRICS_PATH,
            ASSET_HOLDOUT_METRICS_PATH,
            DECILE_METRICS_PATH,
            COEFFICIENT_STABILITY_PATH,
            MODEL_CARD_PATH,
            SUMMARY_PATH,
            REPORT_PATH,
            AUDIT_PATH,
        ],
        summary,
    )
    print(f"P4 complete: {summary['decision']['global_verdict']} frozen={summary['decision']['frozen_candidate_for_future_oos']}", flush=True)


if __name__ == "__main__":
    main()
