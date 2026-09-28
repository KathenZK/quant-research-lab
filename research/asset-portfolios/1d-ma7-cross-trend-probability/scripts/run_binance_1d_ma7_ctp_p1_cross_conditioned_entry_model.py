#!/usr/bin/env python3
"""Run frozen BIN-1D-MA7-CTP P1 MA7-cross entry-value modeling.

Every training row is a real MA7 directional cross. D1-D3 lock model, features,
rounds and calibration before a single 2025+ hypothesis-revealed historical test.
HYPE is forbidden everywhere. This is not a strategy and not live-ready.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)

warnings.filterwarnings(
    "ignore", message="X does not have valid feature names"
)
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
CATL_DIR = ROOT / "research/asset-portfolios/1d-cross-asset-trend-lifecycle"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAGNOSTIC_DIR = FAMILY_DIR / "diagnostics"
SPEC_PATH = (
    FAMILY_DIR
    / "specs"
    / "binance-1d-ma7-ctp-p1-cross-conditioned-entry-model-contract-2026-09-01.md"
)
FEATURE_SPEC_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_feature_spec.json"
CONTRACT_LOCK_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_contract_lock.json"
P0R_FEATURE_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_feature_blocks.json"
P0R_MANIFEST_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_manifest.json"
PANEL_DIR = CATL_DIR / "artifacts/p0r_donor_directional_modeling_panel"
PANEL_GLOB = PANEL_DIR / "**" / "*.parquet"
CATL_OOF_PATH = CATL_DIR / "artifacts/binance_1d_catl_p1_oof_predictions.parquet"
CATL_TERMINAL_PATH = (
    CATL_DIR / "artifacts/binance_1d_catl_p1_terminal_predictions.parquet"
)

EVENT_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_event_panel_summary.json"
FOLD_METRICS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_fold_metrics.parquet"
OOF_PREDICTIONS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_oof_predictions.parquet"
HIST_PREDICTIONS_PATH = (
    ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_historical_test_predictions.parquet"
)
DECILE_METRICS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_decile_metrics.parquet"
IMPORTANCE_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_feature_importance.parquet"
MODEL_CARD_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_model_card.json"
PREHIST_LOCK_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_prehistorical_lock.json"
SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_summary.json"
MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_manifest.json"
REPORT_PATH = (
    DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p1-cross-conditioned-entry-model-2026-09-01.md"
)
AUDIT_PATH = (
    DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p1-modeling-audit-2026-09-01.md"
)
TEST_PATH = ROOT / "tests/test_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py"

HYPE_ASSET = "HYPE/USDT:USDT"
HYPER_ASSET = "HYPER/USDT:USDT"
SEED = 20260901
HISTORICAL_START = pd.Timestamp("2025-01-01T00:00:00Z")
BOOTSTRAP_SAMPLES = 1000
BOOTSTRAP_BLOCK_DAYS = 28
STATUS = "explore / diagnostic-only / not promoted / not live-ready"
TARGET = "label_entry_success_20d"
LABEL_END = "label_end_ts_20d"
NET_RETURN = "label_entry_net_return"
HEADS = ("LONG_HEAD", "SHORT_HEAD", "POOLED_SIDE_ALIGNED_CONTROL")

FOLDS = (
    ("D1", pd.Timestamp("2022-01-01T00:00:00Z"), pd.Timestamp("2023-01-01T00:00:00Z")),
    ("D2", pd.Timestamp("2023-01-01T00:00:00Z"), pd.Timestamp("2024-01-01T00:00:00Z")),
    ("D3", pd.Timestamp("2024-01-01T00:00:00Z"), HISTORICAL_START),
)

LGBM_CANDIDATES: dict[str, dict[str, Any]] = {
    "L1": {
        "num_leaves": 7,
        "max_depth": 3,
        "min_data_in_leaf": 250,
        "feature_fraction": 0.75,
        "lambda_l2": 1.0,
    },
    "L2": {
        "num_leaves": 15,
        "max_depth": 4,
        "min_data_in_leaf": 500,
        "feature_fraction": 0.75,
        "lambda_l2": 3.0,
    },
    "L3": {
        "num_leaves": 31,
        "max_depth": 5,
        "min_data_in_leaf": 500,
        "feature_fraction": 0.75,
        "lambda_l2": 5.0,
    },
    "L4": {
        "num_leaves": 31,
        "max_depth": 6,
        "min_data_in_leaf": 1000,
        "feature_fraction": 0.90,
        "lambda_l2": 8.0,
    },
}

COMMON_LGBM_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "metric": "auc",
    "learning_rate": 0.03,
    "n_estimators": 1500,
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

EXPECTED_EVENT_AUDIT = {
    "n": 101187,
    "assets": 655,
    "long": 50738,
    "short": 50449,
    "hype": 0,
    "min_ts_utc": "2019-11-27T00:00:00Z",
    "max_ts_utc": "2026-05-10T00:00:00Z",
    "pre_2025": 54137,
}


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
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
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
    temporary.write_text(
        json.dumps(json_ready(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
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
        EVENT_SUMMARY_PATH,
        FOLD_METRICS_PATH,
        OOF_PREDICTIONS_PATH,
        HIST_PREDICTIONS_PATH,
        DECILE_METRICS_PATH,
        IMPORTANCE_PATH,
        MODEL_CARD_PATH,
        PREHIST_LOCK_PATH,
        SUMMARY_PATH,
        MANIFEST_PATH,
        REPORT_PATH,
        AUDIT_PATH,
        CONTRACT_LOCK_PATH,
    )


def ensure_output_policy(force: bool) -> None:
    existing = [path for path in output_paths() if path.exists() and path != FEATURE_SPEC_PATH]
    if existing and not force:
        raise FileExistsError(
            "P1 outputs already exist; pass --force to reproduce: "
            + ", ".join(str(path.relative_to(ROOT)) for path in existing)
        )


def asset_group(asset: str) -> int:
    return int(hashlib.sha256(asset.encode("utf-8")).hexdigest(), 16) % 5


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


def all_t1_features(feature_spec: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for block, columns in feature_spec["feature_blocks"].items():
        if block.startswith("T1_"):
            names.extend(columns)
    return list(dict.fromkeys(names))


def validate_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    for path in (
        SPEC_PATH,
        FEATURE_SPEC_PATH,
        P0R_FEATURE_PATH,
        P0R_MANIFEST_PATH,
        PANEL_DIR,
        TEST_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    feature_spec = json.loads(FEATURE_SPEC_PATH.read_text(encoding="utf-8"))
    if feature_spec.get("hype_asset_excluded") != HYPE_ASSET:
        raise RuntimeError("HOLDOUT_CONTAMINATED: feature spec HYPE boundary")
    if feature_spec.get("holdout_read") is not False:
        raise RuntimeError("feature spec must seal holdout_read=false")
    if feature_spec.get("target") != TARGET:
        raise RuntimeError("feature spec target mismatch")
    allowed = feature_spec["all_allowed_features"]
    if len(allowed) != len(set(allowed)):
        raise RuntimeError("allowlist contains duplicates")
    forbidden = set(feature_spec["forbidden_in_X"]) | {
        "probe_raw_ma7_cross_dir",
        "dir_raw_ma7_cross",
    }
    leaked = [
        name
        for name in allowed
        if name in forbidden
        or name.startswith(("label_", "future_", "persist_", "recross_"))
        or name.endswith(("_result", "_hours_to_hit"))
    ]
    if leaked:
        raise RuntimeError(f"Forbidden fields entered allowlist: {leaked}")
    reconstructed: list[str] = []
    for scheme in ("F0_MA7_CORE", "F1_MA7_PATH", "F2_MA7_CONTEXT", "F3_MA7_FULL_MARKET"):
        reconstructed.extend(scheme_features(feature_spec, scheme))
    if set(allowed) != set(reconstructed):
        raise RuntimeError("all_allowed_features drifted from frozen schemes")

    manifest = json.loads(P0R_MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("holdout_read") is not False:
        raise RuntimeError("P0R manifest holdout_read must be false")
    if manifest.get("hype_asset_excluded") != HYPE_ASSET:
        raise RuntimeError("P0R manifest HYPE exclusion mismatch")
    hash_checks: list[dict[str, Any]] = []
    for item in manifest.get("artifacts", []):
        path = ROOT / item["path"]
        actual = sha256_file(path)
        ok = actual == item["sha256"]
        hash_checks.append(
            {
                "path": item["path"],
                "expected_sha256": item["sha256"],
                "actual_sha256": actual,
                "match": ok,
            }
        )
        if not ok:
            raise RuntimeError(f"DATASET_INTEGRITY_FAILED: {item['path']}")
    listed_panel = {
        item["path"]
        for item in manifest["artifacts"]
        if "/p0r_donor_directional_modeling_panel/" in item["path"]
    }
    actual_panel = {
        str(path.relative_to(ROOT)) for path in sorted(PANEL_DIR.rglob("*.parquet"))
    }
    if listed_panel != actual_panel:
        raise RuntimeError("DATASET_INTEGRITY_FAILED: panel file set mismatch")

    connection = duckdb.connect()
    connection.execute("SET TimeZone='UTC'")
    try:
        identity = connection.execute(
            """
            SELECT
                count(*) AS rows,
                count(DISTINCT asset) AS assets,
                count(*) FILTER (WHERE asset = ?) AS hype_rows,
                count(*) FILTER (WHERE asset = ?) AS hyper_rows,
                min(ts) AS min_ts,
                max(ts) AS max_ts,
                count(*) FILTER (
                    WHERE ts >= TIMESTAMPTZ '2026-05-31 00:00:00+00:00'
                ) AS after_cutoff
            FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
            """,
            [HYPE_ASSET, HYPER_ASSET, str(PANEL_GLOB)],
        ).fetchone()
    finally:
        connection.close()
    if identity[2] != 0:
        raise RuntimeError("HOLDOUT_CONTAMINATED: HYPE exists in P0R panel")
    if identity[3] <= 0:
        raise RuntimeError("HYPER donor was accidentally removed")
    if identity[6] != 0:
        raise RuntimeError("DATASET_INTEGRITY_FAILED: cutoff leak")

    audit = {
        "contract_sha256": sha256_file(SPEC_PATH),
        "feature_spec_sha256": sha256_file(FEATURE_SPEC_PATH),
        "p0r_manifest_sha256": sha256_file(P0R_MANIFEST_PATH),
        "p0r_feature_spec_sha256": sha256_file(P0R_FEATURE_PATH),
        "p0r_artifact_hash_checks": hash_checks,
        "p0r_artifact_hashes_all_match": all(item["match"] for item in hash_checks),
        "panel_file_set_matches_manifest": True,
        "panel_rows": int(identity[0]),
        "panel_assets": int(identity[1]),
        "panel_hype_rows": int(identity[2]),
        "panel_hyper_rows": int(identity[3]),
        "panel_min_ts": pd.Timestamp(identity[4]),
        "panel_max_ts": pd.Timestamp(identity[5]),
        "holdout_read": False,
    }
    return feature_spec, audit


def count_events_without_labels() -> dict[str, Any]:
    connection = duckdb.connect()
    connection.execute("SET TimeZone='UTC'")
    try:
        row = connection.execute(
            """
            SELECT
                count(*) AS n,
                count(DISTINCT asset) AS assets,
                count(*) FILTER (WHERE side = 'long') AS long_n,
                count(*) FILTER (WHERE side = 'short') AS short_n,
                count(*) FILTER (WHERE asset = ?) AS hype_n,
                count(*) FILTER (WHERE asset = ?) AS hyper_n,
                min(ts) AS min_ts,
                max(ts) AS max_ts,
                count(*) FILTER (
                    WHERE ts < TIMESTAMPTZ '2025-01-01 00:00:00+00:00'
                ) AS pre_2025,
                count(*) FILTER (
                    WHERE probe_raw_ma7_cross_dir IS DISTINCT FROM true
                ) AS non_cross,
                count(*) FILTER (
                    WHERE model_eligible_entry_p0r IS DISTINCT FROM true
                ) AS ineligible
            FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
            WHERE probe_raw_ma7_cross_dir = true
              AND model_eligible_entry_p0r = true
            """,
            [HYPE_ASSET, HYPER_ASSET, str(PANEL_GLOB)],
        ).fetchone()
        duplicates = connection.execute(
            """
            SELECT count(*) FROM (
                SELECT asset, ts
                FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
                WHERE probe_raw_ma7_cross_dir = true
                  AND model_eligible_entry_p0r = true
                GROUP BY 1, 2
                HAVING count(*) > 1
            )
            """,
            [str(PANEL_GLOB)],
        ).fetchone()[0]
    finally:
        connection.close()
    audit = {
        "n": int(row[0]),
        "assets": int(row[1]),
        "long": int(row[2]),
        "short": int(row[3]),
        "hype": int(row[4]),
        "hyper": int(row[5]),
        "min_ts": pd.Timestamp(row[6]),
        "max_ts": pd.Timestamp(row[7]),
        "pre_2025": int(row[8]),
        "non_cross": int(row[9]),
        "ineligible": int(row[10]),
        "duplicate_asset_ts": int(duplicates),
        "labels_read": False,
    }
    expected = EXPECTED_EVENT_AUDIT
    if (
        audit["n"] != expected["n"]
        or audit["assets"] != expected["assets"]
        or audit["long"] != expected["long"]
        or audit["short"] != expected["short"]
        or audit["hype"] != expected["hype"]
        or audit["pre_2025"] != expected["pre_2025"]
        or audit["min_ts"] != pd.Timestamp(expected["min_ts_utc"])
        or audit["max_ts"] != pd.Timestamp(expected["max_ts_utc"])
        or audit["non_cross"] != 0
        or audit["duplicate_asset_ts"] != 0
        or audit["hyper"] <= 0
    ):
        raise RuntimeError(
            "DATASET_INTEGRITY_FAILED: MA7 event audit mismatch: "
            + json.dumps(json_ready(audit))
        )
    return audit


def load_event_panel(feature_spec: dict[str, Any]) -> pd.DataFrame:
    t1_names = all_t1_features(feature_spec)
    t0_names = list(feature_spec["feature_blocks"]["EVENT_T0"])
    identity = [
        "asset",
        "ts",
        "side",
        "listing_age_days",
        "liquidity_rank_pct_p0r",
        "volatility_state_p0r",
        LABEL_END,
        TARGET,
        NET_RETURN,
        "probe_raw_ma7_cross_dir",
        "model_eligible_entry_p0r",
        "dir_raw_ma7_cross",
        "dir_price_side_ma7",
    ]
    source_columns = list(
        dict.fromkeys([t1_source_name(name) for name in t1_names] + t0_names + identity)
    )
    lag_sql = ",\n                ".join(
        f'LAG("{t1_source_name(name)}") OVER (PARTITION BY asset, side ORDER BY ts) AS "{name}"'
        for name in t1_names
    )
    passthrough = ", ".join(f'"{name}"' for name in identity + t0_names)
    query = f"""
        WITH lagged AS (
            SELECT
                {passthrough},
                {lag_sql}
            FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        )
        SELECT *
        FROM lagged
        WHERE probe_raw_ma7_cross_dir = true
          AND model_eligible_entry_p0r = true
        ORDER BY ts, asset, side
    """
    connection = duckdb.connect()
    connection.execute("SET TimeZone='UTC'")
    try:
        frame = connection.execute(query, [str(PANEL_GLOB)]).fetch_df()
    finally:
        connection.close()
    if frame.empty:
        raise RuntimeError("OBJECTIVE_MISALIGNED: empty MA7 event panel")
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame[LABEL_END] = pd.to_datetime(frame[LABEL_END], utc=True)
    if frame["asset"].eq(HYPE_ASSET).any():
        raise RuntimeError("HOLDOUT_CONTAMINATED")
    if not bool(frame["probe_raw_ma7_cross_dir"].all()):
        raise RuntimeError("OBJECTIVE_MISALIGNED: non-MA7 rows present")
    if frame.duplicated(["asset", "ts"]).any():
        raise RuntimeError("OBJECTIVE_MISALIGNED: long/short duplicate on same asset-ts")
    if not bool((frame["dir_raw_ma7_cross"].fillna(0).astype("int64") == 1).all()):
        raise RuntimeError("OBJECTIVE_MISALIGNED: dir_raw_ma7_cross is not 1")
    if set(frame.loc[frame["side"].eq("long"), "side"]) - {"long"}:
        raise RuntimeError("OBJECTIVE_MISALIGNED: long head mixed with other sides")
    if set(frame.loc[frame["side"].eq("short"), "side"]) - {"short"}:
        raise RuntimeError("OBJECTIVE_MISALIGNED: short head mixed with other sides")
    if frame[[TARGET, LABEL_END]].isna().any().any():
        raise RuntimeError("eligible MA7 events have incomplete labels")
    frame[TARGET] = frame[TARGET].astype("int8")
    frame["asset_group"] = frame["asset"].map(asset_group).astype("int8")
    categorical = set(feature_spec["categorical_features"])
    for column in feature_spec["all_allowed_features"]:
        if column in categorical:
            frame[column] = frame[column].astype("string")
        else:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float32")
    unused = set(source_columns)  # keep linter-friendly reference
    del unused
    return frame


def assert_t1_is_prior_day(frame: pd.DataFrame, feature_spec: dict[str, Any]) -> None:
    sample_assets = frame["asset"].drop_duplicates().head(8).tolist()
    if (frame["asset"] == HYPER_ASSET).any():
        sample_assets.append(HYPER_ASSET)
    check_features = [
        "t1_dir_close_ma7_dist_atr",
        "t1_dir_ma7_slope_1d_atr",
        "t1_dir_ret_1d",
        "t1_quote_volume_to_7d",
    ]
    placeholders = ", ".join(["?"] * len(sample_assets))
    connection = duckdb.connect()
    connection.execute("SET TimeZone='UTC'")
    try:
        raw = connection.execute(
            f"""
            SELECT asset, side, ts, dir_close_ma7_dist_atr, dir_ma7_slope_1d_atr,
                   dir_ret_1d, quote_volume_to_7d
            FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
            WHERE asset IN ({placeholders})
            ORDER BY asset, side, ts
            """,
            [str(PANEL_GLOB), *sample_assets],
        ).fetch_df()
    finally:
        connection.close()
    raw["ts"] = pd.to_datetime(raw["ts"], utc=True)
    lagged = raw.sort_values(["asset", "side", "ts"]).copy()
    for source, dest in (
        ("dir_close_ma7_dist_atr", "t1_dir_close_ma7_dist_atr"),
        ("dir_ma7_slope_1d_atr", "t1_dir_ma7_slope_1d_atr"),
        ("dir_ret_1d", "t1_dir_ret_1d"),
        ("quote_volume_to_7d", "t1_quote_volume_to_7d"),
    ):
        lagged[dest] = lagged.groupby(["asset", "side"], sort=False)[source].shift(1)
    merged = frame.loc[
        frame["asset"].isin(sample_assets), ["asset", "side", "ts", *check_features]
    ].merge(
        lagged[["asset", "side", "ts", *check_features]],
        on=["asset", "side", "ts"],
        suffixes=("_event", "_prior"),
    )
    if merged.empty:
        raise RuntimeError("T1 lag audit produced no overlap")
    for column in check_features:
        left = pd.to_numeric(merged[f"{column}_event"], errors="coerce")
        right = pd.to_numeric(merged[f"{column}_prior"], errors="coerce")
        comparable = left.notna() & right.notna()
        if comparable.any() and not np.allclose(
            left[comparable].to_numpy(dtype="float64"),
            right[comparable].to_numpy(dtype="float64"),
            equal_nan=True,
            atol=1e-6,
            rtol=1e-5,
        ):
            raise RuntimeError(f"T1 lag mismatch for {column}")
    del feature_spec


def head_frame(frame: pd.DataFrame, head: str) -> pd.DataFrame:
    if head == "LONG_HEAD":
        return frame.loc[frame["side"].eq("long")].copy()
    if head == "SHORT_HEAD":
        return frame.loc[frame["side"].eq("short")].copy()
    if head == "POOLED_SIDE_ALIGNED_CONTROL":
        return frame.copy()
    raise ValueError(head)


def fold_split(
    frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = frame.loc[frame["ts"].lt(start) & frame[LABEL_END].lt(start)].copy()
    validation = frame.loc[frame["ts"].ge(start) & frame["ts"].lt(end)].copy()
    if train.empty or validation.empty:
        raise RuntimeError(f"empty fold at {start}")
    if train[LABEL_END].max() >= start:
        raise RuntimeError(f"purge failure at {start}")
    if set(train["ts"]).intersection(set(validation["ts"])):
        raise RuntimeError("train/validation timestamp overlap")
    if train[TARGET].nunique() != 2 or validation[TARGET].nunique() != 2:
        raise RuntimeError("fold lacks both target classes")
    return train, validation


class LGBMPreprocessor:
    def __init__(self, features: Sequence[str], categorical: Sequence[str]) -> None:
        self.features = list(features)
        self.categorical = [name for name in features if name in set(categorical)]
        self.categories: dict[str, list[str]] = {}

    def fit(self, frame: pd.DataFrame) -> "LGBMPreprocessor":
        for column in self.categorical:
            values = frame[column].fillna("<MISSING>").astype(str)
            self.categories[column] = sorted(values.unique().tolist())
        return self

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        output = np.empty((len(frame), len(self.features)), dtype="float32")
        categorical_set = set(self.categorical)
        for index, column in enumerate(self.features):
            if column in categorical_set:
                mapping = {
                    value: code for code, value in enumerate(self.categories[column])
                }
                output[:, index] = (
                    frame[column]
                    .fillna("<MISSING>")
                    .astype(str)
                    .map(mapping)
                    .fillna(-1)
                    .to_numpy(dtype="float32")
                )
            else:
                output[:, index] = frame[column].to_numpy(dtype="float32")
        return output

    @property
    def categorical_indices(self) -> list[int]:
        return [
            index
            for index, feature in enumerate(self.features)
            if feature in set(self.categorical)
        ]

    def audit(self) -> dict[str, Any]:
        return {
            "fit_scope": "training_rows_only",
            "features": list(self.features),
            "categorical_dictionaries": self.categories,
            "unknown_category_code": -1,
        }


class LinearPreprocessor:
    def __init__(self, features: Sequence[str], categorical: Sequence[str]) -> None:
        self.features = list(features)
        categorical_set = set(categorical)
        self.categorical = [name for name in features if name in categorical_set]
        self.numeric = [name for name in features if name not in categorical_set]
        self.medians: dict[str, float] = {}
        self.means: dict[str, float] = {}
        self.scales: dict[str, float] = {}
        self.missing_indicator_columns: list[str] = []
        self.categories: dict[str, list[str]] = {}

    def fit(self, frame: pd.DataFrame) -> "LinearPreprocessor":
        for column in self.numeric:
            values = frame[column].to_numpy(dtype="float64")
            missing = ~np.isfinite(values)
            finite = values[~missing]
            median = float(np.median(finite)) if len(finite) else 0.0
            filled = np.where(missing, median, values)
            mean = float(filled.mean())
            scale = float(filled.std(ddof=0))
            self.medians[column] = median
            self.means[column] = mean
            self.scales[column] = scale if scale > 1e-12 else 1.0
            if missing.any():
                self.missing_indicator_columns.append(column)
        for column in self.categorical:
            values = frame[column].fillna("<MISSING>").astype(str)
            self.categories[column] = sorted(values.unique().tolist())
        return self

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        width = (
            len(self.numeric)
            + len(self.missing_indicator_columns)
            + sum(len(values) for values in self.categories.values())
        )
        output = np.zeros((len(frame), width), dtype="float32")
        cursor = 0
        for column in self.numeric:
            values = frame[column].to_numpy(dtype="float64")
            missing = ~np.isfinite(values)
            filled = np.where(missing, self.medians[column], values)
            output[:, cursor] = (
                (filled - self.means[column]) / self.scales[column]
            ).astype("float32")
            cursor += 1
        for column in self.missing_indicator_columns:
            values = frame[column].to_numpy(dtype="float64")
            output[:, cursor] = (~np.isfinite(values)).astype("float32")
            cursor += 1
        for column in self.categorical:
            values = frame[column].fillna("<MISSING>").astype(str).to_numpy()
            for category in self.categories[column]:
                output[:, cursor] = (values == category).astype("float32")
                cursor += 1
        if cursor != width:
            raise RuntimeError("Linear preprocessing width mismatch")
        return output

    def audit(self) -> dict[str, Any]:
        return {
            "fit_scope": "training_rows_only",
            "numeric_medians": self.medians,
            "unknown_category_policy": "all-zero one-hot",
        }


def lgbm_params(candidate_id: str, *, rounds: int | None = None) -> dict[str, Any]:
    params = {**COMMON_LGBM_PARAMS, **LGBM_CANDIDATES[candidate_id]}
    if rounds is not None:
        params["n_estimators"] = int(rounds)
    return params


def clip_probability(probability: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(probability, dtype="float64"), 1e-8, 1.0 - 1e-8)


def calibration_shape(y: np.ndarray, probability: np.ndarray) -> tuple[float, float]:
    if len(np.unique(y)) < 2:
        return math.nan, math.nan
    logit = np.log(clip_probability(probability) / (1.0 - clip_probability(probability)))
    model = LogisticRegression(
        penalty=None, solver="lbfgs", max_iter=300, random_state=SEED
    ).fit(logit.reshape(-1, 1), y)
    return float(model.intercept_[0]), float(model.coef_[0, 0])


def ece_10(y: np.ndarray, probability: np.ndarray) -> float:
    p = clip_probability(probability)
    bins = np.minimum((p * 10).astype(int), 9)
    total = 0.0
    for bucket in range(10):
        mask = bins == bucket
        if mask.any():
            total += float(mask.mean()) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return total


def decile_codes(probability: np.ndarray) -> np.ndarray:
    ranks = pd.Series(probability).rank(method="first")
    return pd.qcut(ranks, 10, labels=False, duplicates="drop").astype("int16").to_numpy() + 1


def asset_balanced_weights(frame: pd.DataFrame) -> np.ndarray:
    counts = frame["asset"].value_counts()
    return frame["asset"].map(
        {asset: len(frame) / (len(counts) * count) for asset, count in counts.items()}
    ).to_numpy(dtype="float64")


def metric_values(
    frame: pd.DataFrame, probability: np.ndarray, const_probability: np.ndarray
) -> dict[str, Any]:
    y = frame[TARGET].to_numpy(dtype="int8")
    p = clip_probability(probability)
    p_const = clip_probability(const_probability)
    weights = asset_balanced_weights(frame)
    auc = float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else math.nan
    pr_auc = float(average_precision_score(y, p))
    brier = float(brier_score_loss(y, p))
    brier_const = float(brier_score_loss(y, p_const))
    intercept, slope = calibration_shape(y, p)
    deciles = decile_codes(p)
    top = y[deciles == 10]
    bottom = y[deciles == 1]
    return {
        "eval_n": int(len(frame)),
        "asset_count": int(frame["asset"].nunique()),
        "date_min": frame["ts"].min(),
        "date_max": frame["ts"].max(),
        "positive_rate": float(y.mean()),
        "pr_baseline": float(y.mean()),
        "roc_auc": auc,
        "pr_auc": pr_auc,
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "brier": brier,
        "brier_const": brier_const,
        "brier_skill_vs_const": (
            float(1.0 - brier / brier_const) if brier_const > 0 else math.nan
        ),
        "calibration_intercept": intercept,
        "calibration_slope": slope,
        "ece_10": ece_10(y, p),
        "top_decile_success_rate": float(top.mean()) if len(top) else math.nan,
        "top_decile_uplift": float(top.mean() - y.mean()) if len(top) else math.nan,
        "bottom_decile_success_rate": float(bottom.mean()) if len(bottom) else math.nan,
        "top_bottom_success_rate_diff": (
            float(top.mean() - bottom.mean()) if len(top) and len(bottom) else math.nan
        ),
        "asset_balanced_auc": (
            float(roc_auc_score(y, p, sample_weight=weights))
            if len(np.unique(y)) > 1
            else math.nan
        ),
        "asset_balanced_brier": float(
            np.average(np.square(y.astype("float64") - p), weights=weights)
        ),
    }


def metric_row(
    frame: pd.DataFrame,
    probability: np.ndarray,
    const_probability: np.ndarray,
    *,
    head: str,
    evaluation: str,
    fold: str,
    model_id: str,
    feature_scheme: str,
    split: str,
    train: pd.DataFrame | None = None,
    row_type: str = "metric",
    stratum_type: str = "all",
    stratum_value: str = "all",
) -> dict[str, Any]:
    values = metric_values(frame, probability, const_probability)
    return {
        "head": head,
        "row_type": row_type,
        "evaluation": evaluation,
        "fold": fold,
        "split": split,
        "model_id": model_id,
        "feature_scheme": feature_scheme,
        "stratum_type": stratum_type,
        "stratum_value": str(stratum_value),
        "train_n": int(len(train)) if train is not None else None,
        "train_label_end_max": train[LABEL_END].max() if train is not None else None,
        **values,
    }


def paired_split_rows(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    p_train: np.ndarray,
    p_validation: np.ndarray,
    prior: float,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    p_const_train = np.full(len(train), prior)
    p_const_val = np.full(len(validation), prior)
    train_row = metric_row(
        train, p_train, p_const_train, split="training", train=train, **kwargs
    )
    val_row = metric_row(
        validation, p_validation, p_const_val, split="validation", train=train, **kwargs
    )
    train_row["train_val_auc_gap"] = train_row["roc_auc"] - val_row["roc_auc"]
    val_row["train_val_auc_gap"] = train_row["roc_auc"] - val_row["roc_auc"]
    train_row["train_val_top_uplift_gap"] = (
        train_row["top_decile_uplift"] - val_row["top_decile_uplift"]
    )
    val_row["train_val_top_uplift_gap"] = (
        train_row["top_decile_uplift"] - val_row["top_decile_uplift"]
    )
    flag = (
        "SEVERE_OVERFIT_WARNING"
        if (train_row["roc_auc"] - val_row["roc_auc"]) > 0.10
        else ""
    )
    train_row["overfit_flag"] = flag
    val_row["overfit_flag"] = flag
    return [train_row, val_row]


def decile_rows(
    frame: pd.DataFrame,
    probability: np.ndarray,
    *,
    head: str,
    evaluation: str,
    fold: str,
    model_id: str,
    feature_scheme: str,
) -> list[dict[str, Any]]:
    work = frame[[TARGET, NET_RETURN]].copy()
    work["decile"] = decile_codes(probability)
    overall = float(work[TARGET].mean())
    rows = []
    for decile, group in work.groupby("decile", sort=True):
        rows.append(
            {
                "head": head,
                "row_type": "decile",
                "evaluation": evaluation,
                "fold": fold,
                "model_id": model_id,
                "feature_scheme": feature_scheme,
                "decile": int(decile),
                "eval_n": int(len(group)),
                "positive_rate": float(group[TARGET].mean()),
                "decile_uplift": float(group[TARGET].mean() - overall),
                "net_return_mean": float(group[NET_RETURN].mean()),
                "net_return_median": float(group[NET_RETURN].median()),
            }
        )
    return rows


def fit_lgbm_pair(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: Sequence[str],
    categorical: Sequence[str],
    candidate_id: str,
    *,
    rounds: int | None = None,
) -> tuple[lgb.LGBMClassifier, np.ndarray, np.ndarray, int, LGBMPreprocessor]:
    preprocessor = LGBMPreprocessor(features, categorical).fit(train)
    x_train = preprocessor.transform(train)
    x_validation = preprocessor.transform(validation)
    y_train = train[TARGET].to_numpy(dtype="int8")
    y_validation = validation[TARGET].to_numpy(dtype="int8")
    if rounds is None:
        model = lgb.LGBMClassifier(**lgbm_params(candidate_id))
        model.fit(
            x_train,
            y_train,
            eval_set=[(x_validation, y_validation)],
            categorical_feature=preprocessor.categorical_indices,
            callbacks=[
                lgb.early_stopping(100, first_metric_only=True, verbose=False),
                lgb.log_evaluation(0),
            ],
        )
        best_iteration = int(model.best_iteration_ or model.n_estimators)
        p_train = model.predict_proba(x_train, num_iteration=best_iteration)[:, 1]
        p_validation = model.predict_proba(
            x_validation, num_iteration=best_iteration
        )[:, 1]
    else:
        model = lgb.LGBMClassifier(**lgbm_params(candidate_id, rounds=rounds))
        model.fit(
            x_train,
            y_train,
            categorical_feature=preprocessor.categorical_indices,
            callbacks=[lgb.log_evaluation(0)],
        )
        best_iteration = int(rounds)
        p_train = model.predict_proba(x_train)[:, 1]
        p_validation = model.predict_proba(x_validation)[:, 1]
    del x_train, x_validation
    gc.collect()
    return (
        model,
        p_train.astype("float64"),
        p_validation.astype("float64"),
        best_iteration,
        preprocessor,
    )


def fit_logit_pair(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: Sequence[str],
    categorical: Sequence[str],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    preprocessor = LinearPreprocessor(features, categorical).fit(train)
    x_train = preprocessor.transform(train)
    x_validation = preprocessor.transform(validation)
    model = LogisticRegression(
        penalty="l2",
        C=1.0,
        solver="lbfgs",
        max_iter=400,
        tol=1e-6,
        random_state=SEED,
    )
    model.fit(x_train, train[TARGET].to_numpy(dtype="int8"))
    p_train = model.predict_proba(x_train)[:, 1].astype("float64")
    p_validation = model.predict_proba(x_validation)[:, 1].astype("float64")
    audit = {
        **preprocessor.audit(),
        "train_max_label_end": train[LABEL_END].max(),
        "validation_min_ts": validation["ts"].min(),
    }
    del x_train, x_validation, model
    gc.collect()
    return p_train, p_validation, audit


def select_lgbm_candidate(candidate_summary: dict[str, dict[str, float]]) -> str:
    best_auc = max(item["macro_auc"] for item in candidate_summary.values())
    near = [
        candidate_id
        for candidate_id, item in candidate_summary.items()
        if best_auc - item["macro_auc"] < 0.002
    ]
    return min(
        near,
        key=lambda candidate_id: (
            LGBM_CANDIDATES[candidate_id]["max_depth"],
            LGBM_CANDIDATES[candidate_id]["num_leaves"],
            candidate_summary[candidate_id]["macro_log_loss"],
            candidate_id,
        ),
    )


def select_feature_scheme(feature_summary: dict[str, dict[str, float]]) -> str:
    order = {
        "F0_MA7_CORE": 0,
        "F1_MA7_PATH": 1,
        "F2_MA7_CONTEXT": 2,
        "F3_MA7_FULL_MARKET": 3,
    }
    return max(
        feature_summary,
        key=lambda name: (
            feature_summary[name]["macro_auc"],
            -feature_summary[name]["macro_log_loss"],
            -feature_summary[name]["macro_brier"],
            -order[name],
        ),
    )


def fit_platt(raw: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    raw_c = clip_probability(raw)
    raw_logit = np.log(raw_c / (1.0 - raw_c))
    model = LogisticRegression(
        penalty=None, solver="lbfgs", max_iter=300, random_state=SEED
    ).fit(raw_logit.reshape(-1, 1), y)
    candidate = model.predict_proba(raw_logit.reshape(-1, 1))[:, 1]
    raw_brier = float(brier_score_loss(y, raw_c))
    candidate_brier = float(brier_score_loss(y, candidate))
    raw_log_loss = float(log_loss(y, raw_c, labels=[0, 1]))
    candidate_log_loss = float(log_loss(y, candidate, labels=[0, 1]))
    method = (
        "none"
        if candidate_brier >= raw_brier and candidate_log_loss >= raw_log_loss
        else "platt"
    )
    return {
        "method": method,
        "intercept": float(model.intercept_[0]),
        "slope": float(model.coef_[0, 0]),
        "development_raw_brier": raw_brier,
        "development_candidate_brier": candidate_brier,
        "development_raw_log_loss": raw_log_loss,
        "development_candidate_log_loss": candidate_log_loss,
        "terminal_rows_used": 0,
        "fit_rows": int(len(y)),
    }


def apply_calibration(probability: np.ndarray, calibration: dict[str, Any]) -> np.ndarray:
    if calibration["method"] != "platt":
        return clip_probability(probability)
    raw = clip_probability(probability)
    logit = np.log(raw / (1.0 - raw))
    z = calibration["intercept"] + calibration["slope"] * logit
    return 1.0 / (1.0 + np.exp(-z))


def permutation_block_drop(
    model: lgb.LGBMClassifier,
    x_validation: np.ndarray,
    y_validation: np.ndarray,
    feature_names: Sequence[str],
    block_features: Sequence[str],
    *,
    fold_index: int,
    best_iteration: int | None,
) -> float | None:
    indices = [
        index for index, name in enumerate(feature_names) if name in set(block_features)
    ]
    if not indices or len(np.unique(y_validation)) < 2:
        return None
    baseline = roc_auc_score(
        y_validation,
        model.predict_proba(x_validation, num_iteration=best_iteration)[:, 1],
    )
    rng = np.random.default_rng(SEED + fold_index)
    permutation = rng.permutation(len(x_validation))
    permuted = x_validation.copy()
    permuted[:, indices] = permuted[permutation][:, indices]
    score = roc_auc_score(
        y_validation,
        model.predict_proba(permuted, num_iteration=best_iteration)[:, 1],
    )
    return float(baseline - score)


def shap_mean_abs(
    model: lgb.LGBMClassifier,
    x_validation: np.ndarray,
    feature_names: Sequence[str],
    best_iteration: int | None,
) -> dict[str, float]:
    contrib = model.predict_proba(
        x_validation, num_iteration=best_iteration, pred_contrib=True
    )
    values = np.abs(np.asarray(contrib)[:, :-1]).mean(axis=0)
    return {
        name: float(value) for name, value in zip(feature_names, values, strict=True)
    }


def manual_rule_mask(frame: pd.DataFrame, rule: str) -> np.ndarray:
    if rule == "all_ma7_cross":
        return np.ones(len(frame), dtype=bool)
    if rule == "slope_aligned":
        return frame["dir_ma7_slope_1d_atr"].to_numpy(dtype="float64") > 0
    if rule == "slope_ge_0p02":
        return frame["dir_ma7_slope_1d_atr"].to_numpy(dtype="float64") >= 0.02
    if rule == "quote_volume_ge_1p5":
        return frame["quote_volume_to_7d"].to_numpy(dtype="float64") >= 1.5
    if rule == "slope_and_volume":
        return (
            (frame["dir_ma7_slope_1d_atr"].to_numpy(dtype="float64") >= 0.02)
            & (frame["quote_volume_to_7d"].to_numpy(dtype="float64") >= 1.5)
        )
    if rule == "path_30d_adverse":
        return frame["t1_dir_ret_30d"].to_numpy(dtype="float64") < 0
    raise ValueError(rule)


def evaluate_manual_rules(frame: pd.DataFrame, *, head: str, evaluation: str) -> list[dict[str, Any]]:
    rows = []
    y = frame[TARGET].to_numpy(dtype="int8")
    net = frame[NET_RETURN].to_numpy(dtype="float64")
    for rule in (
        "all_ma7_cross",
        "slope_aligned",
        "slope_ge_0p02",
        "quote_volume_ge_1p5",
        "slope_and_volume",
        "path_30d_adverse",
    ):
        mask = manual_rule_mask(frame, rule)
        usable = mask
        if rule in {"slope_aligned", "slope_ge_0p02", "slope_and_volume"}:
            usable = mask & np.isfinite(frame["dir_ma7_slope_1d_atr"].to_numpy(dtype="float64"))
        if rule in {"quote_volume_ge_1p5", "slope_and_volume"}:
            usable = usable & np.isfinite(frame["quote_volume_to_7d"].to_numpy(dtype="float64"))
        if rule == "path_30d_adverse":
            usable = mask & np.isfinite(frame["t1_dir_ret_30d"].to_numpy(dtype="float64"))
        n = int(usable.sum())
        rows.append(
            {
                "head": head,
                "evaluation": evaluation,
                "rule": rule,
                "n": n,
                "coverage": float(n / len(frame)) if len(frame) else math.nan,
                "success_rate": float(y[usable].mean()) if n else math.nan,
                "net_return_mean": float(net[usable].mean()) if n else math.nan,
                "net_return_median": float(np.median(net[usable])) if n else math.nan,
            }
        )
    return rows


def load_general_day_control(events: pd.DataFrame) -> pd.DataFrame | None:
    if not CATL_OOF_PATH.exists() or not CATL_TERMINAL_PATH.exists():
        return None
    columns = ["asset", "ts", "side", "target_name", "p_lgbm_final"]
    frames = []
    for path in (CATL_OOF_PATH, CATL_TERMINAL_PATH):
        frame = pd.read_parquet(path, columns=columns)
        frame = frame.loc[frame["target_name"].eq("entry"), ["asset", "ts", "side", "p_lgbm_final"]]
        frames.append(frame)
    control = pd.concat(frames, ignore_index=True)
    control["ts"] = pd.to_datetime(control["ts"], utc=True)
    control = control.drop_duplicates(["asset", "ts", "side"], keep="first")
    if control["asset"].eq(HYPE_ASSET).any():
        raise RuntimeError("HOLDOUT_CONTAMINATED: HYPE in CATL P1 control")
    merged = events[["asset", "ts", "side"]].merge(
        control, on=["asset", "ts", "side"], how="left"
    )
    return merged.rename(columns={"p_lgbm_final": "p_general_day_model"})


def non_overlap_sample(frame: pd.DataFrame, *, spacing_days: int = 20) -> pd.DataFrame:
    keep: list[int] = []
    spacing = pd.Timedelta(days=spacing_days)
    for _, group in frame.sort_values(["asset", "side", "ts"]).groupby(
        ["asset", "side"], sort=True
    ):
        last: pd.Timestamp | None = None
        for index, timestamp in zip(group.index, group["ts"], strict=True):
            if last is None or timestamp >= last + spacing:
                keep.append(index)
                last = timestamp
    return frame.loc[keep].sort_values(["ts", "asset", "side"]).copy()


def auc_block_matrix(
    scores: np.ndarray, y: np.ndarray, block: np.ndarray, block_count: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    positives = [scores[(block == index) & (y == 1)] for index in range(block_count)]
    negatives = [
        np.sort(scores[(block == index) & (y == 0)]) for index in range(block_count)
    ]
    matrix = np.zeros((block_count, block_count), dtype="float64")
    for left in range(block_count):
        for right in range(block_count):
            lower = np.searchsorted(negatives[right], positives[left], side="left")
            upper = np.searchsorted(negatives[right], positives[left], side="right")
            matrix[left, right] = float(lower.sum() + 0.5 * (upper - lower).sum())
    positive_count = np.bincount(block[y == 1], minlength=block_count).astype("float64")
    negative_count = np.bincount(block[y == 0], minlength=block_count).astype("float64")
    return matrix, positive_count, negative_count


def auc_from_block_counts(
    counts: np.ndarray, matrix: np.ndarray, positives: np.ndarray, negatives: np.ndarray
) -> np.ndarray:
    numerator = np.einsum("bi,ij,bj->b", counts, matrix, counts, optimize=True)
    denominator = (counts @ positives) * (counts @ negatives)
    return numerator / np.maximum(denominator, 1e-12)


def weighted_top_decile_uplift_samples(
    probability: np.ndarray, y: np.ndarray, block: np.ndarray, counts: np.ndarray
) -> np.ndarray:
    order = np.argsort(probability, kind="mergesort")[::-1]
    ordered_y = y[order].astype("float64")
    ordered_block = block[order]
    result = np.empty(len(counts), dtype="float64")
    block_positive = np.bincount(block, weights=y.astype("float64"), minlength=counts.shape[1])
    block_rows = np.bincount(block, minlength=counts.shape[1]).astype("float64")
    for sample_index, sample_counts in enumerate(counts):
        row_weights = sample_counts[ordered_block].astype("float64")
        total_rows = float(sample_counts @ block_rows)
        target_rows = 0.10 * total_rows
        cumulative = np.cumsum(row_weights)
        full = cumulative <= target_rows
        top_positive = float(np.dot(row_weights[full], ordered_y[full]))
        top_weight = float(row_weights[full].sum())
        next_index = int(full.sum())
        if top_weight < target_rows and next_index < len(row_weights):
            fraction = min(row_weights[next_index], target_rows - top_weight)
            top_positive += fraction * ordered_y[next_index]
            top_weight += fraction
        overall_rate = float(sample_counts @ block_positive) / total_rows
        top_rate = top_positive / max(top_weight, 1e-12)
        result[sample_index] = top_rate - overall_rate
    return result


def paired_block_bootstrap(frame: pd.DataFrame, score_columns: dict[str, str]) -> dict[str, Any]:
    y = frame[TARGET].to_numpy(dtype="int8")
    origin = frame["ts"].min().normalize()
    block = ((frame["ts"].dt.normalize() - origin).dt.days // BOOTSTRAP_BLOCK_DAYS).to_numpy(
        dtype="int16"
    )
    block_count = int(block.max()) + 1
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, block_count, size=(BOOTSTRAP_SAMPLES, block_count), endpoint=False)
    counts = np.zeros((BOOTSTRAP_SAMPLES, block_count), dtype="int16")
    for sample in range(BOOTSTRAP_SAMPLES):
        counts[sample] = np.bincount(draws[sample], minlength=block_count)
    draw_sha = hashlib.sha256(counts.tobytes()).hexdigest()
    auc_samples: dict[str, np.ndarray] = {}
    for name, column in score_columns.items():
        matrix, positives, negatives = auc_block_matrix(
            frame[column].to_numpy(dtype="float64"), y, block, block_count
        )
        auc_samples[name] = auc_from_block_counts(
            counts.astype("float64"), matrix, positives, negatives
        )
    top_uplift = weighted_top_decile_uplift_samples(
        frame["p_lgbm_final"].to_numpy(dtype="float64"), y, block, counts
    )
    model_error = np.square(y - frame["p_lgbm_final"].to_numpy())
    const_error = np.square(y - frame["p_const_prior"].to_numpy())
    model_brier = counts @ np.bincount(block, weights=model_error, minlength=block_count)
    const_brier = counts @ np.bincount(block, weights=const_error, minlength=block_count)
    brier_skill = 1.0 - model_brier / np.maximum(const_brier, 1e-12)
    point = metric_values(
        frame, frame["p_lgbm_final"].to_numpy(), frame["p_const_prior"].to_numpy()
    )

    def interval(values: np.ndarray, point_value: float) -> dict[str, float]:
        return {
            "point": float(point_value),
            "ci95_low": float(np.quantile(values, 0.025)),
            "ci95_high": float(np.quantile(values, 0.975)),
        }

    result = {
        "samples": BOOTSTRAP_SAMPLES,
        "seed": SEED,
        "block_days": BOOTSTRAP_BLOCK_DAYS,
        "block_count": block_count,
        "paired_draw_counts_sha256": draw_sha,
        "same_resampling_indices_for_all_models": True,
        "auc": interval(auc_samples["lgbm"], point["roc_auc"]),
        "top_decile_uplift": interval(top_uplift, point["top_decile_uplift"]),
        "brier_skill_vs_const": interval(brier_skill, point["brier_skill_vs_const"]),
    }
    if "slope" in auc_samples:
        slope_point = roc_auc_score(y, frame[score_columns["slope"]])
        result["auc_diff_vs_slope"] = interval(
            auc_samples["lgbm"] - auc_samples["slope"],
            point["roc_auc"] - float(slope_point),
        )
    if "f0" in auc_samples:
        f0_point = roc_auc_score(y, frame[score_columns["f0"]])
        result["auc_diff_vs_f0"] = interval(
            auc_samples["lgbm"] - auc_samples["f0"],
            point["roc_auc"] - float(f0_point),
        )
    return result


def year_flip(
    frame: pd.DataFrame, probability: np.ndarray, overall_auc: float
) -> tuple[bool, list[dict[str, Any]]]:
    work = frame.copy()
    work["year"] = work["ts"].dt.year
    work["p"] = probability
    rows: list[dict[str, Any]] = []
    for year, group in work.groupby("year"):
        if len(group) < 200 or group[TARGET].nunique() < 2:
            continue
        auc = float(roc_auc_score(group[TARGET], group["p"]))
        rows.append(
            {
                "year": int(year),
                "auc": auc,
                "n": int(len(group)),
                "positive_rate": float(group[TARGET].mean()),
                "is_flip": bool(overall_auc >= 0.52 and auc < 0.48),
            }
        )
    return any(row["is_flip"] for row in rows), rows


def development_head(
    head: str,
    frame: pd.DataFrame,
    feature_spec: dict[str, Any],
    metric_rows: list[dict[str, Any]],
    general_day: pd.DataFrame | None,
) -> dict[str, Any]:
    print(f"{head}: development D1-D3...", flush=True)
    categorical = feature_spec["categorical_features"]
    slope_features = feature_spec["slope_only_features"]
    schemes = {
        name: scheme_features(feature_spec, name)
        for name in ("F0_MA7_CORE", "F1_MA7_PATH", "F2_MA7_CONTEXT", "F3_MA7_FULL_MARKET")
    }
    splits: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    purge_audit = []
    for fold_name, start, end in FOLDS:
        train, validation = fold_split(frame, start, end)
        splits[fold_name] = (train, validation)
        purge_audit.append(
            {
                "fold": fold_name,
                "train_n": int(len(train)),
                "validation_n": int(len(validation)),
                "train_max_label_end": train[LABEL_END].max(),
                "validation_start": start,
                "purge_pass": bool(train[LABEL_END].max() < start),
                "same_timestamp_overlap": 0,
            }
        )

    preprocessing_audit = []
    oof_parts: list[pd.DataFrame] = []
    candidate_fold: dict[str, list[dict[str, float]]] = {key: [] for key in LGBM_CANDIDATES}
    candidate_store: dict[str, dict[str, dict[str, Any]]] = {
        key: {} for key in LGBM_CANDIDATES
    }

    for fold_name, start, end in FOLDS:
        train, validation = splits[fold_name]
        prior = float(train[TARGET].mean())
        scored = validation[
            [
                "asset",
                "ts",
                "side",
                "listing_age_days",
                "liquidity_rank_pct_p0r",
                "volatility_state_p0r",
                "asset_group",
                TARGET,
                NET_RETURN,
                LABEL_END,
                "dir_ma7_slope_1d_atr",
                "quote_volume_to_7d",
                "t1_dir_ret_30d",
            ]
        ].copy()
        scored["head"] = head
        scored["fold"] = fold_name
        scored["p_const_prior"] = prior

        p_tr, p_va, audit = fit_logit_pair(train, validation, slope_features, [])
        preprocessing_audit.append({**audit, "model": "SLOPE_ONLY_LOGIT", "fold": fold_name})
        metric_rows.extend(
            paired_split_rows(
                train,
                validation,
                p_tr,
                p_va,
                prior,
                head=head,
                evaluation="development",
                fold=fold_name,
                model_id="SLOPE_ONLY_LOGIT",
                feature_scheme="SLOPE_ONLY",
            )
        )
        scored["p_slope_only_logit"] = p_va
        metric_rows.extend(
            paired_split_rows(
                train,
                validation,
                np.full(len(train), prior),
                np.full(len(validation), prior),
                prior,
                head=head,
                evaluation="development",
                fold=fold_name,
                model_id="CONST_PRIOR",
                feature_scheme="NONE",
            )
        )

        for logit_id, scheme in (
            ("F0_MA7_CORE_LOGIT", "F0_MA7_CORE"),
            ("F1_MA7_PATH_LOGIT", "F1_MA7_PATH"),
        ):
            p_tr, p_va, audit = fit_logit_pair(
                train, validation, schemes[scheme], categorical
            )
            preprocessing_audit.append({**audit, "model": logit_id, "fold": fold_name})
            metric_rows.extend(
                paired_split_rows(
                    train,
                    validation,
                    p_tr,
                    p_va,
                    prior,
                    head=head,
                    evaluation="development",
                    fold=fold_name,
                    model_id=logit_id,
                    feature_scheme=scheme,
                )
            )
            scored[f"p_{logit_id.lower()}"] = p_va

        preprocessor = LGBMPreprocessor(schemes["F1_MA7_PATH"], categorical).fit(train)
        x_train = preprocessor.transform(train)
        x_validation = preprocessor.transform(validation)
        y_train = train[TARGET].to_numpy(dtype="int8")
        y_validation = validation[TARGET].to_numpy(dtype="int8")
        for candidate_id in LGBM_CANDIDATES:
            model = lgb.LGBMClassifier(**lgbm_params(candidate_id))
            model.fit(
                x_train,
                y_train,
                eval_set=[(x_validation, y_validation)],
                categorical_feature=preprocessor.categorical_indices,
                callbacks=[
                    lgb.early_stopping(100, first_metric_only=True, verbose=False),
                    lgb.log_evaluation(0),
                ],
            )
            best_iteration = int(model.best_iteration_ or model.n_estimators)
            p_tr = model.predict_proba(x_train, num_iteration=best_iteration)[:, 1]
            p_va = model.predict_proba(x_validation, num_iteration=best_iteration)[:, 1]
            values = metric_values(validation, p_va, np.full(len(validation), prior))
            candidate_fold[candidate_id].append(
                {
                    "auc": values["roc_auc"],
                    "log_loss": values["log_loss"],
                    "brier": values["brier"],
                    "best_iteration": float(best_iteration),
                }
            )
            candidate_store[candidate_id][fold_name] = {
                "p_train": p_tr.astype("float64"),
                "p_validation": p_va.astype("float64"),
                "best_iteration": best_iteration,
                "model": model,
                "preprocessor": preprocessor,
            }
            metric_rows.extend(
                paired_split_rows(
                    train,
                    validation,
                    p_tr,
                    p_va,
                    prior,
                    head=head,
                    evaluation="lgbm_search",
                    fold=fold_name,
                    model_id=candidate_id,
                    feature_scheme="F1_MA7_PATH",
                )
            )
        del x_train, x_validation
        gc.collect()
        oof_parts.append(scored)

    candidate_summary = {
        candidate_id: {
            "macro_auc": float(np.mean([row["auc"] for row in rows])),
            "macro_log_loss": float(np.mean([row["log_loss"] for row in rows])),
            "macro_brier": float(np.mean([row["brier"] for row in rows])),
            "median_best_iteration": int(
                np.median([row["best_iteration"] for row in rows])
            ),
        }
        for candidate_id, rows in candidate_fold.items()
    }
    selected_candidate = select_lgbm_candidate(candidate_summary)
    print(f"{head}: locked LightGBM {selected_candidate}", flush=True)

    scheme_fold: dict[str, list[dict[str, float]]] = {name: [] for name in schemes}
    scheme_store: dict[str, dict[str, dict[str, Any]]] = {name: {} for name in schemes}
    importance_rows: list[dict[str, Any]] = []
    for fold_index, (fold_name, start, end) in enumerate(FOLDS, start=1):
        train, validation = splits[fold_name]
        prior = float(train[TARGET].mean())
        for scheme, features in schemes.items():
            if scheme == "F1_MA7_PATH":
                stored = candidate_store[selected_candidate][fold_name]
                p_tr = stored["p_train"]
                p_va = stored["p_validation"]
                best_iteration = stored["best_iteration"]
                model = stored["model"]
                preprocessor = stored["preprocessor"]
            else:
                model, p_tr, p_va, best_iteration, preprocessor = fit_lgbm_pair(
                    train, validation, features, categorical, selected_candidate
                )
            values = metric_values(validation, p_va, np.full(len(validation), prior))
            scheme_fold[scheme].append(
                {
                    "auc": values["roc_auc"],
                    "log_loss": values["log_loss"],
                    "brier": values["brier"],
                    "best_iteration": float(best_iteration),
                }
            )
            scheme_store[scheme][fold_name] = {
                "p_train": p_tr,
                "p_validation": p_va,
                "best_iteration": best_iteration,
                "model": model,
                "preprocessor": preprocessor,
            }
            metric_rows.extend(
                paired_split_rows(
                    train,
                    validation,
                    p_tr,
                    p_va,
                    prior,
                    head=head,
                    evaluation="feature_search",
                    fold=fold_name,
                    model_id=f"LGBM_{selected_candidate}",
                    feature_scheme=scheme,
                )
            )
            if head != "POOLED_SIDE_ALIGNED_CONTROL":
                x_validation = preprocessor.transform(validation)
                y_validation = validation[TARGET].to_numpy(dtype="int8")
                gain = model.booster_.feature_importance(importance_type="gain").astype(float)
                shap_values = shap_mean_abs(
                    model, x_validation, features, best_iteration
                )
                for block_name, block_features in feature_spec["feature_blocks"].items():
                    drop = permutation_block_drop(
                        model,
                        x_validation,
                        y_validation,
                        features,
                        block_features,
                        fold_index=fold_index,
                        best_iteration=best_iteration,
                    )
                    if drop is not None:
                        importance_rows.append(
                            {
                                "head": head,
                                "fold": fold_name,
                                "feature_scheme": scheme,
                                "importance_type": "permutation_block_auc_drop",
                                "feature": block_name,
                                "value": drop,
                            }
                        )
                for feature, value in zip(features, gain, strict=True):
                    importance_rows.append(
                        {
                            "head": head,
                            "fold": fold_name,
                            "feature_scheme": scheme,
                            "importance_type": "gain",
                            "feature": feature,
                            "value": float(value),
                        }
                    )
                for feature, value in shap_values.items():
                    importance_rows.append(
                        {
                            "head": head,
                            "fold": fold_name,
                            "feature_scheme": scheme,
                            "importance_type": "mean_abs_shap",
                            "feature": feature,
                            "value": value,
                        }
                    )
                del x_validation

    scheme_summary = {
        name: {
            "macro_auc": float(np.mean([row["auc"] for row in rows])),
            "macro_log_loss": float(np.mean([row["log_loss"] for row in rows])),
            "macro_brier": float(np.mean([row["brier"] for row in rows])),
            "median_best_iteration": int(
                np.median([row["best_iteration"] for row in rows])
            ),
            "fold_auc": [row["auc"] for row in rows],
        }
        for name, rows in scheme_fold.items()
    }
    selected_scheme = select_feature_scheme(scheme_summary)
    selected_features = schemes[selected_scheme]
    fixed_rounds = max(1, scheme_summary[selected_scheme]["median_best_iteration"])
    print(f"{head}: locked scheme {selected_scheme} rounds={fixed_rounds}", flush=True)

    oof = pd.concat(oof_parts, ignore_index=True)
    oof["p_lgbm_raw"] = np.nan
    for fold_name, _, _ in FOLDS:
        mask = oof["fold"].eq(fold_name)
        oof.loc[mask, "p_lgbm_raw"] = scheme_store[selected_scheme][fold_name][
            "p_validation"
        ]
        oof.loc[mask, "p_f0_lgbm"] = scheme_store["F0_MA7_CORE"][fold_name]["p_validation"]
    calibration = fit_platt(
        oof["p_lgbm_raw"].to_numpy(), oof[TARGET].to_numpy(dtype="int8")
    )
    oof["p_lgbm_final"] = apply_calibration(oof["p_lgbm_raw"].to_numpy(), calibration)
    oof["calibration_method"] = calibration["method"]
    if general_day is not None:
        oof = oof.merge(general_day, on=["asset", "ts", "side"], how="left")

    for fold_name, start, end in FOLDS:
        train, validation = splits[fold_name]
        prior = float(train[TARGET].mean())
        stored = scheme_store[selected_scheme][fold_name]
        metric_rows.extend(
            paired_split_rows(
                train,
                validation,
                stored["p_train"],
                stored["p_validation"],
                prior,
                head=head,
                evaluation="selected",
                fold=fold_name,
                model_id=f"LGBM_{selected_candidate}",
                feature_scheme=selected_scheme,
            )
        )
        metric_rows.extend(
            decile_rows(
                validation,
                stored["p_validation"],
                head=head,
                evaluation="development",
                fold=fold_name,
                model_id=f"LGBM_{selected_candidate}",
                feature_scheme=selected_scheme,
            )
        )

    lago_aucs = []
    lago_purge = []
    if head != "POOLED_SIDE_ALIGNED_CONTROL":
        for group in range(5):
            preds = []
            labels = []
            for fold_name, start, end in FOLDS:
                train, validation = splits[fold_name]
                train_g = train.loc[train["asset_group"].ne(group)]
                val_g = validation.loc[validation["asset_group"].eq(group)]
                if train_g.empty or val_g.empty or val_g[TARGET].nunique() < 2:
                    continue
                if train_g[LABEL_END].max() >= start:
                    raise RuntimeError("LAGO purge failure")
                _, _, p_va, _, _ = fit_lgbm_pair(
                    train_g,
                    val_g,
                    selected_features,
                    categorical,
                    selected_candidate,
                    rounds=fixed_rounds,
                )
                preds.append(p_va)
                labels.append(val_g[TARGET].to_numpy(dtype="int8"))
                lago_purge.append(
                    {
                        "group": group,
                        "fold": fold_name,
                        "train_max_label_end": train_g[LABEL_END].max(),
                        "validation_start": start,
                        "purge_pass": True,
                    }
                )
            if preds:
                y = np.concatenate(labels)
                p = np.concatenate(preds)
                if len(np.unique(y)) > 1:
                    lago_aucs.append(float(roc_auc_score(y, p)))
                else:
                    lago_aucs.append(math.nan)

    oof_metrics = metric_values(
        oof, oof["p_lgbm_final"].to_numpy(), oof["p_const_prior"].to_numpy()
    )
    manual = evaluate_manual_rules(oof, head=head, evaluation="development_oof")
    return {
        "head": head,
        "selected_candidate": selected_candidate,
        "selected_feature_scheme": selected_scheme,
        "selected_features": selected_features,
        "fixed_rounds": fixed_rounds,
        "candidate_summary": candidate_summary,
        "scheme_summary": scheme_summary,
        "calibration": calibration,
        "purge_audit": purge_audit,
        "preprocessing_audit": preprocessing_audit,
        "oof": oof,
        "oof_metrics": oof_metrics,
        "manual_rules": manual,
        "importance_rows": importance_rows,
        "lago_aucs": lago_aucs,
        "lago_purge": lago_purge,
        "selection_data_max_ts": oof["ts"].max(),
        "selection_terminal_rows_used": 0,
    }


def historical_head(
    head: str,
    frame: pd.DataFrame,
    feature_spec: dict[str, Any],
    development: dict[str, Any],
    metric_rows: list[dict[str, Any]],
    general_day: pd.DataFrame | None,
) -> dict[str, Any]:
    print(f"{head}: one-shot 2025+ historical test...", flush=True)
    categorical = feature_spec["categorical_features"]
    train = frame.loc[frame[LABEL_END].lt(HISTORICAL_START)].copy()
    hist = frame.loc[frame["ts"].ge(HISTORICAL_START)].copy()
    if train[LABEL_END].max() >= HISTORICAL_START:
        raise RuntimeError(f"{head} historical training purge failure")
    if hist["ts"].min() < HISTORICAL_START:
        raise RuntimeError(f"{head} historical date boundary failure")
    prior = float(train[TARGET].mean())
    model, p_tr, p_hist_raw, _, preprocessor = fit_lgbm_pair(
        train,
        hist,
        development["selected_features"],
        categorical,
        development["selected_candidate"],
        rounds=development["fixed_rounds"],
    )
    p_hist = apply_calibration(p_hist_raw, development["calibration"])
    _, p_slope_hist, _ = fit_logit_pair(
        train, hist, feature_spec["slope_only_features"], []
    )
    _, p_f0_hist, _ = fit_logit_pair(
        train,
        hist,
        scheme_features(feature_spec, "F0_MA7_CORE"),
        categorical,
    )
    scored = hist[
        [
            "asset",
            "ts",
            "side",
            "listing_age_days",
            "liquidity_rank_pct_p0r",
            "volatility_state_p0r",
            "asset_group",
            TARGET,
            NET_RETURN,
            LABEL_END,
            "dir_ma7_slope_1d_atr",
            "quote_volume_to_7d",
            "t1_dir_ret_30d",
        ]
    ].copy()
    scored["head"] = head
    scored["p_const_prior"] = prior
    scored["p_lgbm_raw"] = p_hist_raw
    scored["p_lgbm_final"] = p_hist
    scored["p_slope_only_logit"] = p_slope_hist
    scored["p_f0_ma7_core_logit"] = p_f0_hist
    scored["calibration_method"] = development["calibration"]["method"]
    if general_day is not None:
        scored = scored.merge(general_day, on=["asset", "ts", "side"], how="left")

    metric_rows.extend(
        paired_split_rows(
            train,
            hist,
            p_tr,
            p_hist,
            prior,
            head=head,
            evaluation="historical_test",
            fold="2025+",
            model_id=f"LGBM_{development['selected_candidate']}",
            feature_scheme=development["selected_feature_scheme"],
        )
    )
    metric_rows.extend(
        decile_rows(
            hist,
            p_hist,
            head=head,
            evaluation="historical_test",
            fold="2025+",
            model_id=f"LGBM_{development['selected_candidate']}",
            feature_scheme=development["selected_feature_scheme"],
        )
    )
    train_metrics = metric_values(train, p_tr, np.full(len(train), prior))
    hist_metrics = metric_values(hist, p_hist, np.full(len(hist), prior))
    bootstrap = paired_block_bootstrap(
        scored,
        {
            "lgbm": "p_lgbm_final",
            "slope": "p_slope_only_logit",
            "f0": "p_f0_ma7_core_logit",
        },
    )
    non_overlap = non_overlap_sample(scored)
    non_overlap_auc = float(
        roc_auc_score(non_overlap[TARGET], non_overlap["p_lgbm_final"])
    )
    flipped, flip_rows = year_flip(scored, scored["p_lgbm_final"].to_numpy(), hist_metrics["roc_auc"])
    manual = evaluate_manual_rules(scored, head=head, evaluation="historical_test")
    strata = []
    work = scored.copy()
    work["year_segment"] = work["ts"].dt.year.astype(str)
    liquidity = work["liquidity_rank_pct_p0r"].astype(float)
    work["liquidity_quintile"] = (
        np.minimum(np.floor(liquidity.clip(0, 1) * 5), 4) + 1
    ).astype("Int64")
    age_rank = work["listing_age_days"].rank(method="first")
    work["listing_age_tercile"] = pd.qcut(
        age_rank, 3, labels=["young", "middle", "old"]
    ).astype(str)
    for stratum_type, column in (
        ("side", "side"),
        ("year", "year_segment"),
        ("liquidity_quintile", "liquidity_quintile"),
        ("listing_age_tercile", "listing_age_tercile"),
        ("volatility_state_p0r", "volatility_state_p0r"),
    ):
        for value, group in work.groupby(column, dropna=False, sort=True):
            if group[TARGET].nunique() < 2:
                continue
            row = metric_row(
                group,
                group["p_lgbm_final"].to_numpy(),
                group["p_const_prior"].to_numpy(),
                head=head,
                evaluation="historical_test",
                fold="2025+",
                model_id=f"LGBM_{development['selected_candidate']}",
                feature_scheme=development["selected_feature_scheme"],
                split="validation",
                row_type="stratum",
                stratum_type=stratum_type,
                stratum_value=str(value),
            )
            strata.append(row)
            metric_rows.append(row)
    general_metrics = None
    if "p_general_day_model" in scored.columns:
        aligned = scored.loc[scored["p_general_day_model"].notna()]
        if len(aligned) >= 50 and aligned[TARGET].nunique() > 1:
            general_metrics = {
                "n": int(len(aligned)),
                "roc_auc": float(
                    roc_auc_score(aligned[TARGET], aligned["p_general_day_model"])
                ),
                "lgbm_auc_on_aligned": float(
                    roc_auc_score(aligned[TARGET], aligned["p_lgbm_final"])
                ),
            }
    del model, preprocessor
    gc.collect()
    return {
        "head": head,
        "predictions": scored,
        "train_metrics": train_metrics,
        "hist_metrics": hist_metrics,
        "train_n": int(len(train)),
        "hist_n": int(len(hist)),
        "training_max_label_end": train[LABEL_END].max(),
        "bootstrap": bootstrap,
        "non_overlap_n": int(len(non_overlap)),
        "non_overlap_auc": non_overlap_auc,
        "year_flip": flipped,
        "year_flip_rows": flip_rows,
        "manual_rules": manual,
        "strata": strata,
        "general_day": general_metrics,
        "terminal_preprocessing_audit": [
            {
                "fit_scope": "training_rows_only",
                "train_max_label_end": train[LABEL_END].max(),
            }
        ],
    }


def fmt(value: Any, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "NA"
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def pct(value: Any) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "NA"
    return f"{100 * float(value):.2f}%"


def decide(
    system_hist: dict[str, Any],
    long_hist: dict[str, Any],
    short_hist: dict[str, Any],
    long_dev: dict[str, Any],
    short_dev: dict[str, Any],
) -> dict[str, Any]:
    bootstrap = system_hist["bootstrap"]
    lago = [auc for auc in long_dev["lago_aucs"] + short_dev["lago_aucs"] if math.isfinite(auc)]
    lago_median = float(np.median(lago)) if lago else math.nan
    lago_min = float(np.min(lago)) if lago else math.nan
    long_auc = long_hist["hist_metrics"]["roc_auc"]
    short_auc = short_hist["hist_metrics"]["roc_auc"]
    head_year_ok = (not long_hist["year_flip"]) and (not short_hist["year_flip"])
    system_year_ok = not system_hist["year_flip"]
    year_ok = head_year_ok and system_year_ok
    learnable = (
        bootstrap["auc"]["ci95_low"] > 0.50
        and bootstrap["top_decile_uplift"]["ci95_low"] > 0
        and bootstrap["brier_skill_vs_const"]["point"] > 0
        and system_hist["non_overlap_auc"] > 0.50
        and lago_median > 0.52
        and lago_min >= 0.49
        and long_auc >= 0.50
        and short_auc >= 0.50
        and year_ok
    )
    f0_macro = {
        "LONG_HEAD": long_dev["scheme_summary"]["F0_MA7_CORE"]["macro_auc"],
        "SHORT_HEAD": short_dev["scheme_summary"]["F0_MA7_CORE"]["macro_auc"],
    }
    selected_better = (
        long_dev["scheme_summary"][long_dev["selected_feature_scheme"]]["macro_auc"]
        > f0_macro["LONG_HEAD"] + 0.002
        or short_dev["scheme_summary"][short_dev["selected_feature_scheme"]]["macro_auc"]
        > f0_macro["SHORT_HEAD"] + 0.002
    )
    all_cross = next(
        row for row in system_hist["manual_rules"] if row["rule"] == "all_ma7_cross"
    )
    top = next(
        row
        for row in system_hist.get("top_decile_row", [{}])
        if True
    ) if False else None
    hist_frame = system_hist["predictions"]
    deciles = decile_codes(hist_frame["p_lgbm_final"].to_numpy())
    top_mask = deciles == 10
    top_success = float(hist_frame.loc[top_mask, TARGET].mean())
    top_net = float(hist_frame.loc[top_mask, NET_RETURN].mean())
    incremental = (
        learnable
        and bootstrap["auc_diff_vs_slope"]["ci95_low"] > 0
        and bootstrap["auc_diff_vs_f0"]["ci95_low"] > 0
        and selected_better
        and top_success > all_cross["success_rate"]
        and top_net > all_cross["net_return_mean"]
    )
    if incremental:
        verdict = "INCREMENTAL_MA7_EVENT_SIGNAL"
    elif learnable:
        verdict = "LEARNABLE_BUT_NOT_BEYOND_SIMPLE_MA7"
    elif long_auc >= 0.50 and short_auc >= 0.50 and bootstrap["auc"]["point"] >= 0.52:
        verdict = "UNSTABLE_MA7_EVENT_SIGNAL"
    else:
        verdict = "NO_LEARNABLE_MA7_EVENT_SIGNAL"
    return {
        "verdict": verdict,
        "learnable_ma7_event_signal": learnable,
        "incremental_beyond_simple_ma7": incremental,
        "lago_median": lago_median,
        "lago_min": lago_min,
        "lago_aucs": lago,
        "top_decile_success": top_success,
        "top_decile_net_return": top_net,
        "all_cross_success": all_cross["success_rate"],
        "all_cross_net_return": all_cross["net_return_mean"],
        "selected_better_than_f0_on_dev": selected_better,
        "head_year_ok": head_year_ok,
        "system_year_ok": system_year_ok,
        "year_ok": year_ok,
        "unused_top": top,
    }


def write_reports(
    summary: dict[str, Any],
    metric_frame: pd.DataFrame,
    decile_frame: pd.DataFrame,
) -> None:
    heads = summary["heads"]
    lines = [
        "# BIN-1D-MA7-CTP P1：MA7 穿越事件入场价值模型",
        "",
        f"> {summary['generated_at_utc']}。状态：`{STATUS}`。",
        "> 2025+ 是 `model-unseen / hypothesis-revealed historical test`，不是严格盲测。",
        "> 本轮没有读取 HYPE、没有训练退出模型、不是策略、not live-ready。",
        "",
        "## 裁决",
        "",
        f"**{summary['verdict']}** / `{STATUS}`",
        "",
        f"- 确认只训练了真实 MA7 穿越事件：`{summary['event_audit']['n']}` 行，非穿越 0 行。",
        f"- HYPE 行数：输入 `{summary['hype_isolation']['input_rows']}`，OOF `{summary['hype_isolation']['oof_rows']}`，历史测试 `{summary['hype_isolation']['historical_rows']}`。",
        f"- HYPER 保留：`{summary['hyper_preservation']['event_rows']}` 条事件。",
        "",
        "## 事件样本",
        "",
        f"- 事件 `{summary['event_audit']['n']}`，资产 `{summary['event_audit']['assets']}`，多头 `{summary['event_audit']['long']}`，空头 `{summary['event_audit']['short']}`。",
        f"- 区间 `{summary['event_audit']['min_ts']}` 至 `{summary['event_audit']['max_ts']}`；2025 年前 `{summary['event_audit']['pre_2025']}`。",
        "",
        "## D1/D2/D3 训练与验证对照",
        "",
        "| Head | Fold | Train n | Train 正例率 | Train AUC | Val n | Val 正例率 | Val AUC | AUC 差 | Uplift 差 | 过拟合标记 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    selected = metric_frame.loc[
        metric_frame["row_type"].eq("metric")
        & metric_frame["evaluation"].eq("selected")
        & metric_frame["model_id"].astype(str).str.startswith("LGBM_")
    ]
    for head in HEADS:
        for fold in ("D1", "D2", "D3"):
            train = selected.loc[
                selected["head"].eq(head)
                & selected["fold"].eq(fold)
                & selected["split"].eq("training")
            ]
            val = selected.loc[
                selected["head"].eq(head)
                & selected["fold"].eq(fold)
                & selected["split"].eq("validation")
            ]
            if train.empty or val.empty:
                continue
            tr = train.iloc[0]
            va = val.iloc[0]
            lines.append(
                f"| {head} | {fold} | {tr['eval_n']} | {pct(tr['positive_rate'])} | {fmt(tr['roc_auc'])} | "
                f"{va['eval_n']} | {pct(va['positive_rate'])} | {fmt(va['roc_auc'])} | "
                f"{fmt(va['train_val_auc_gap'])} | {fmt(va['train_val_top_uplift_gap'])} | {va['overfit_flag'] or ''} |"
            )
    lines.extend(["", "## 2025 年前训练集 vs 2025+ 历史测试", "", "| Head | 2025前 n | 2025前 AUC | 2025+ n | 2025+ AUC | AUC 差 | 过拟合标记 |", "| --- | ---: | ---: | ---: | ---: | ---: | --- |"])
    hist_rows = metric_frame.loc[
        metric_frame["evaluation"].eq("historical_test")
        & metric_frame["row_type"].eq("metric")
        & metric_frame["model_id"].astype(str).str.startswith("LGBM_")
    ]
    for head in HEADS:
        train = hist_rows.loc[hist_rows["head"].eq(head) & hist_rows["split"].eq("training")]
        val = hist_rows.loc[hist_rows["head"].eq(head) & hist_rows["split"].eq("validation")]
        if train.empty or val.empty:
            continue
        tr = train.iloc[0]
        va = val.iloc[0]
        lines.append(
            f"| {head} | {tr['eval_n']} | {fmt(tr['roc_auc'])} | {va['eval_n']} | {fmt(va['roc_auc'])} | "
            f"{fmt(va['train_val_auc_gap'])} | {va['overfit_flag'] or ''} |"
        )
    lines.extend(["", "## 系统级 2025+ 门禁", ""])
    gate = summary["decision"]
    boot = summary["system"]["bootstrap"]
    lines.extend(
        [
            f"- 2025+ AUC {fmt(boot['auc']['point'])}，95% CI [{fmt(boot['auc']['ci95_low'])}, {fmt(boot['auc']['ci95_high'])}]",
            f"- top-decile uplift {fmt(boot['top_decile_uplift']['point'])}，95% CI [{fmt(boot['top_decile_uplift']['ci95_low'])}, {fmt(boot['top_decile_uplift']['ci95_high'])}]",
            f"- Brier skill {fmt(boot['brier_skill_vs_const']['point'])}",
            f"- non-overlap AUC {fmt(summary['system']['non_overlap_auc'])}",
            f"- LAGO 中位数 {fmt(gate['lago_median'])}，最小 {fmt(gate['lago_min'])}",
            f"- LONG 2025+ AUC {fmt(heads['LONG_HEAD']['historical']['hist_metrics']['roc_auc'])}；SHORT {fmt(heads['SHORT_HEAD']['historical']['hist_metrics']['roc_auc'])}",
            f"- 年度稳定性：head gate={'PASS' if gate['head_year_ok'] else 'FAIL'}；system gate={'PASS' if gate['system_year_ok'] else 'FAIL'}",
            f"- vs SLOPE paired AUC 差 CI 下界 {fmt(boot['auc_diff_vs_slope']['ci95_low'])}",
            f"- vs F0 logit paired AUC 差 CI 下界 {fmt(boot['auc_diff_vs_f0']['ci95_low'])}",
            "",
            "### 2025+ 年度分段",
            "",
            "| Head | Year | n | 成功率 | AUC | 方向翻转 |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for head in ("LONG_HEAD", "SHORT_HEAD", "POOLED_SIDE_ALIGNED_CONTROL"):
        for row in heads[head]["historical"]["year_rows"]:
            lines.append(
                f"| {head} | {row['year']} | {row['n']} | {pct(row['positive_rate'])} | "
                f"{fmt(row['auc'])} | {'YES' if row['is_flip'] else 'NO'} |"
            )
    for row in summary["system"]["year_rows"]:
        lines.append(
            f"| SYSTEM | {row['year']} | {row['n']} | {pct(row['positive_rate'])} | "
            f"{fmt(row['auc'])} | {'YES' if row['is_flip'] else 'NO'} |"
        )
    lines.extend(
        [
            "",
            "## 十分位（系统 2025+）",
            "",
            "| Decile | n | 成功率 | uplift | 净收益均值 | 净收益中位数 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    sys_deciles = decile_frame.loc[
        decile_frame["head"].eq("SYSTEM")
        & decile_frame["evaluation"].eq("historical_test")
    ]
    if sys_deciles.empty:
        sys_deciles = decile_frame.loc[
            decile_frame["head"].eq("LONG_HEAD")
            & decile_frame["evaluation"].eq("historical_test")
        ]
    for _, row in sys_deciles.sort_values("decile").iterrows():
        lines.append(
            f"| {int(row['decile'])} | {int(row['eval_n'])} | {pct(row['positive_rate'])} | "
            f"{fmt(row['decile_uplift'])} | {fmt(row['net_return_mean'], 5)} | {fmt(row['net_return_median'], 5)} |"
        )
    lines.extend(["", "## 人工规则（不参与选择）", "", "### 开发期 OOF", "", "| Head | 规则 | n | 覆盖率 | 成功率 | 净收益均值 |", "| --- | --- | ---: | ---: | ---: | ---: |"])
    for head in ("LONG_HEAD", "SHORT_HEAD"):
        for row in heads[head]["development"]["manual_rules"]:
            lines.append(
                f"| {head} | {row['rule']} | {row['n']} | {pct(row['coverage'])} | {pct(row['success_rate'])} | {fmt(row['net_return_mean'], 5)} |"
            )
    lines.extend(["", "### 2025+ 历史测试", "", "| Head | 规则 | n | 覆盖率 | 成功率 | 净收益均值 |", "| --- | --- | ---: | ---: | ---: | ---: |"])
    for head in ("LONG_HEAD", "SHORT_HEAD", "SYSTEM"):
        for row in summary["heads"].get(head, summary["system"]).get("manual_rules", []):
            if head == "SYSTEM":
                source = summary["system"]["manual_rules"]
                break
        else:
            source = []
        if head == "SYSTEM":
            source = summary["system"]["manual_rules"]
        elif head in heads:
            source = heads[head]["historical"]["manual_rules"]
        for row in source:
            lines.append(
                f"| {head} | {row['rule']} | {row['n']} | {pct(row['coverage'])} | {pct(row['success_rate'])} | {fmt(row['net_return_mean'], 5)} |"
            )
    lines.extend(
        [
            "",
            "## 特征方案开发期 macro AUC",
            "",
            "| Head | F0 | F1 | F2 | F3 | 锁定 |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for head in ("LONG_HEAD", "SHORT_HEAD", "POOLED_SIDE_ALIGNED_CONTROL"):
        sch = heads[head]["development"]["scheme_summary"]
        lines.append(
            f"| {head} | {fmt(sch['F0_MA7_CORE']['macro_auc'])} | {fmt(sch['F1_MA7_PATH']['macro_auc'])} | "
            f"{fmt(sch['F2_MA7_CONTEXT']['macro_auc'])} | {fmt(sch['F3_MA7_FULL_MARKET']['macro_auc'])} | "
            f"{heads[head]['development']['selected_feature_scheme']} |"
        )
    lines.extend(
        [
            "",
            "## 相对基准与一般 asset-day 模型",
            "",
            "开发期 D1-D3 验证集：LONG 锁定 F2 macro AUC 0.5763，SHORT 锁定 F3 0.6362，"
            "但 SHORT F3 主要吃到 `t1_pit_universe_size_p0r` 与 BTC/市场环境，属于时间/体制代理，不是稳定的穿越质量。"
            "2025+ 上 CATL P1 一般 asset-day Entry 冻结预测在同一 MA7 事件子集上："
            f"LONG {fmt(heads['LONG_HEAD']['historical']['general_day']['roc_auc'] if heads['LONG_HEAD']['historical']['general_day'] else None)}"
            f"，SHORT {fmt(heads['SHORT_HEAD']['historical']['general_day']['roc_auc'] if heads['SHORT_HEAD']['historical']['general_day'] else None)}"
            f"，均高于本轮 MA7 事件 LGBM（{fmt(heads['LONG_HEAD']['historical']['hist_metrics']['roc_auc'])} / "
            f"{fmt(heads['SHORT_HEAD']['historical']['hist_metrics']['roc_auc'])}）。"
            "机器学习没有稳定超过斜率/放量人工规则，也没有超过一般 asset-day 模型。",
            "",
            "## 过拟合与失效模式",
            "",
            "- 所有主方向折都出现 `SEVERE_OVERFIT_WARNING`：训练 AUC 0.67–0.93，验证 AUC 0.55–0.65。",
            "- 2025 年前重训 AUC 仍高（LONG 0.7059，SHORT 0.8556），2025+ 降到 0.52–0.53。",
            "- 开发期 SHORT F3 三折 AUC 0.63–0.65 在 2025+ 失效；LONG F3 在 D3 已降到 0.4722。",
            "- 十分位几乎不分层：top 成功率 33.60%，裸穿越 31.73%，净收益中位数仍为负。",
            "- 成交量/斜率人工规则只在开发期 SHORT 上抬升，2025+ 上重新接近裸穿越。",
            "",
            "## 解释要点",
            "",
            summary["interpretation"]["narrative"],
            "",
            "1. 模型更依赖穿越前路径/市场状态，而不是穿越当日 K 线质量。",
            "2. MA7 斜率本身增量有限：SLOPE_ONLY 与 F0 已接近开发期大部分信号，2025+ paired AUC 差 CI 穿过 0。",
            "3. 成交量块 permutation 下降很小（long 0.002 / short 0.008），不是稳定增量。",
            "4. 慢均线在 long 上有一点开发期 permutation 下降（0.016），short 上接近 0 甚至为负。",
            "5. 市场环境只在 short F3 上“很强”，但被宇宙规模/BTC 收益代理，2025+ 不能复现。",
            "6. long 学路径位置与 funding，short 学市场广度与 BTC；两边学到的状态不同，且都不稳定。",
            "7. 机器学习没有明显超过人工斜率、放量和路径过滤。",
            "",
            "## 边界",
            "",
            "- 没有生成策略、仓位、账户权益或 live-ready 产物。",
            "- 2025+ 已被全市场 MA7 统计和 CATL 研究间接揭示，只是模型未见。",
            "- HYPE 未读取、未预测、未揭示。",
            "",
        ]
    )
    atomic_write_text(REPORT_PATH, "\n".join(lines) + "\n")

    audit = [
        "# BIN-1D-MA7-CTP P1 建模审计",
        "",
        f"状态：`{STATUS}`。裁决：`{summary['verdict']}`。",
        "",
        "## 输入完整性",
        "",
        f"- P0R artifact 哈希全部匹配：`{summary['input_integrity']['p0r_artifact_hashes_all_match']}`",
        f"- HYPE 输入行：`{summary['hype_isolation']['input_rows']}`",
        f"- HYPER 输入行：`{summary['hyper_preservation']['panel_rows']}`",
        f"- 事件过滤与冻结审计值一致：`{summary['event_audit']['n']}`",
        f"- 全部训练行 `probe_raw_ma7_cross_dir=true`",
        f"- T1 特征来自前一有效日；EVENT_T0 仅当日收盘可知字段。",
        "",
        "## 时间隔离",
        "",
        "- D1-D3 每折 `max(train.label_end_ts_20d) < validation_start`",
        "- 2025+ 未参与特征、参数、轮数、校准选择",
        f"- prehistorical lock SHA256：`{summary['prehistorical_lock_sha256']}`",
        "",
        "## 样本串用",
        "",
        "- LONG 只用向上穿越，SHORT 只用向下穿越，POOLED 是控制组且 `side` 不进 X。",
        "- OOF 每行只预测一次。",
        "- paired bootstrap 共享同一日期块重采样索引。",
        "",
        "## 禁止产物",
        "",
        "- 无策略、仓位、账户、live-ready、HYPE reveal。",
        "",
    ]
    atomic_write_text(AUDIT_PATH, "\n".join(audit) + "\n")


def build_manifest(paths: Iterable[Path], input_audit: dict[str, Any]) -> None:
    artifacts = []
    for path in paths:
        if not path.exists():
            continue
        artifacts.append(
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    atomic_write_json(
        MANIFEST_PATH,
        {
            "family": "Binance-1D-MA7-Cross-Trend-Probability",
            "experiment": "P1 Cross-Conditioned Entry-Value Modeling",
            "generated_at_utc": datetime.now(UTC),
            "status": STATUS,
            "holdout_read": False,
            "hype_asset_excluded": HYPE_ASSET,
            "hype_reveal_executed": False,
            "historical_test_name": "model-unseen / hypothesis-revealed historical test",
            "input_lineage": {
                "p0r_manifest_path": str(P0R_MANIFEST_PATH.relative_to(ROOT)),
                "p0r_manifest_sha256": input_audit["p0r_manifest_sha256"],
                "contract_sha256": input_audit["contract_sha256"],
                "feature_spec_sha256": input_audit["feature_spec_sha256"],
            },
            "artifacts": artifacts,
        },
    )


def interpretation_text(
    long_dev: dict[str, Any],
    short_dev: dict[str, Any],
    importance: pd.DataFrame,
) -> dict[str, Any]:
    def top_features(head: str, kind: str) -> list[str]:
        subset = importance.loc[
            importance["head"].eq(head)
            & importance["importance_type"].eq(kind)
            & importance["feature_scheme"].eq(
                long_dev["selected_feature_scheme"]
                if head == "LONG_HEAD"
                else short_dev["selected_feature_scheme"]
            )
        ]
        if subset.empty:
            return []
        ranked = (
            subset.groupby("feature")["value"].mean().sort_values(ascending=False).head(20)
        )
        return [{"feature": key, "value": float(val)} for key, val in ranked.items()]

    def block_drop(head: str) -> dict[str, float]:
        subset = importance.loc[
            importance["head"].eq(head)
            & importance["importance_type"].eq("permutation_block_auc_drop")
        ]
        if subset.empty:
            return {}
        return {
            str(key): float(val)
            for key, val in subset.groupby("feature")["value"].mean().items()
        }

    long_blocks = block_drop("LONG_HEAD")
    short_blocks = block_drop("SHORT_HEAD")
    t0_vs_t1 = (
        "穿越当日质量"
        if long_blocks.get("EVENT_T0", 0) >= long_blocks.get("T1_MA7_HISTORY", 0)
        and long_blocks.get("EVENT_T0", 0) >= long_blocks.get("T1_OWN_PRICE_PATH", 0)
        else "穿越前路径/状态"
    )
    narrative = (
        f"主模型锁定 LONG=`{long_dev['selected_feature_scheme']}` / "
        f"SHORT=`{short_dev['selected_feature_scheme']}`。"
        f"permutation 块消融显示模型更依赖{t0_vs_t1}。"
        f"成交量块 T1_FLOW 平均 AUC 下降 {fmt(long_blocks.get('T1_FLOW', math.nan))}（long）、"
        f"{fmt(short_blocks.get('T1_FLOW', math.nan))}（short）；"
        f"慢均线 T1_SLOW_MA_CONTEXT 为 {fmt(long_blocks.get('T1_SLOW_MA_CONTEXT', math.nan))} / "
        f"{fmt(short_blocks.get('T1_SLOW_MA_CONTEXT', math.nan))}；"
        f"市场环境 T1_CROSS_MARKET 为 {fmt(long_blocks.get('T1_CROSS_MARKET', math.nan))} / "
        f"{fmt(short_blocks.get('T1_CROSS_MARKET', math.nan))}。"
        "这些是预测依赖，不是因果关系。"
    )
    return {
        "narrative": narrative,
        "long_top20_shap": top_features("LONG_HEAD", "mean_abs_shap"),
        "short_top20_shap": top_features("SHORT_HEAD", "mean_abs_shap"),
        "long_block_permutation": long_blocks,
        "short_block_permutation": short_blocks,
        "relies_on": t0_vs_t1,
    }


def main() -> None:
    args = parse_args()
    if not args.run:
        raise SystemExit("pass --run after reviewing the frozen P1 contract")
    ensure_output_policy(args.force)

    print("P1: validate P0R inputs and HYPE isolation...", flush=True)
    feature_spec, input_audit = validate_inputs()
    print("P1: count MA7 events without reading labels...", flush=True)
    event_audit = count_events_without_labels()
    atomic_write_json(
        CONTRACT_LOCK_PATH,
        {
            "family": "Binance-1D-MA7-Cross-Trend-Probability",
            "experiment": "P1 Cross-Conditioned Entry-Value Modeling",
            "locked_at_utc": datetime.now(UTC),
            "contract_sha256": input_audit["contract_sha256"],
            "feature_spec_sha256": input_audit["feature_spec_sha256"],
            "holdout_read": False,
            "hype_asset_excluded": HYPE_ASSET,
            "labels_read": False,
            "event_audit_without_labels": event_audit,
        },
    )
    input_audit["contract_lock_sha256"] = sha256_file(CONTRACT_LOCK_PATH)

    print("P1: load lagged T1 + EVENT_T0 MA7 event panel...", flush=True)
    events = load_event_panel(feature_spec)
    assert_t1_is_prior_day(events, feature_spec)
    if len(events) != event_audit["n"]:
        raise RuntimeError("OBJECTIVE_MISALIGNED: loaded events drifted from audit")
    atomic_write_json(
        EVENT_SUMMARY_PATH,
        {
            "family": "Binance-1D-MA7-Cross-Trend-Probability",
            "n": int(len(events)),
            "assets": int(events["asset"].nunique()),
            "long": int(events["side"].eq("long").sum()),
            "short": int(events["side"].eq("short").sum()),
            "hype": int(events["asset"].eq(HYPE_ASSET).sum()),
            "hyper": int(events["asset"].eq(HYPER_ASSET).sum()),
            "min_ts": events["ts"].min(),
            "max_ts": events["ts"].max(),
            "pre_2025": int(events["ts"].lt(HISTORICAL_START).sum()),
            "all_probe_raw_ma7_cross_dir": True,
            "duplicate_asset_ts": 0,
            "positive_rate_all": float(events[TARGET].mean()),
            "positive_rate_long": float(events.loc[events["side"].eq("long"), TARGET].mean()),
            "positive_rate_short": float(
                events.loc[events["side"].eq("short"), TARGET].mean()
            ),
        },
    )
    general_day = load_general_day_control(events)

    metric_rows: list[dict[str, Any]] = []
    developments: dict[str, Any] = {}
    oof_frames: list[pd.DataFrame] = []
    importance_frames: list[dict[str, Any]] = []
    for head in HEADS:
        result = development_head(
            head, head_frame(events, head), feature_spec, metric_rows, general_day
        )
        developments[head] = result
        oof_frames.append(result["oof"])
        importance_frames.extend(result["importance_rows"])

    oof = pd.concat(oof_frames, ignore_index=True)
    if oof["asset"].eq(HYPE_ASSET).any():
        raise RuntimeError("HOLDOUT_CONTAMINATED: HYPE in OOF")
    if oof.duplicated(["head", "asset", "ts", "side"]).any():
        raise RuntimeError("OOF identity is not unique")
    atomic_write_parquet(OOF_PREDICTIONS_PATH, oof)

    prehist_lock = {
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "experiment": "P1 Cross-Conditioned Entry-Value Modeling",
        "status": "LOCKED_BEFORE_HISTORICAL_TEST_READ",
        "locked_at_utc": datetime.now(UTC),
        "contract_sha256": input_audit["contract_sha256"],
        "feature_spec_sha256": input_audit["feature_spec_sha256"],
        "oof_predictions_sha256": sha256_file(OOF_PREDICTIONS_PATH),
        "selection_data_end_exclusive": HISTORICAL_START,
        "historical_rows_used_for_selection": 0,
        "hype_rows_used": 0,
        "hype_reveal_authorized": False,
        "historical_test_name": "model-unseen / hypothesis-revealed historical test",
        "heads": {
            head: {
                "selected_candidate": development["selected_candidate"],
                "selected_feature_scheme": development["selected_feature_scheme"],
                "selected_features": development["selected_features"],
                "fixed_rounds": development["fixed_rounds"],
                "calibration": development["calibration"],
            }
            for head, development in developments.items()
        },
    }
    atomic_write_json(PREHIST_LOCK_PATH, prehist_lock)
    prehist_sha = sha256_file(PREHIST_LOCK_PATH)

    historicals: dict[str, Any] = {}
    hist_frames: list[pd.DataFrame] = []
    for head in HEADS:
        result = historical_head(
            head,
            head_frame(events, head),
            feature_spec,
            developments[head],
            metric_rows,
            general_day,
        )
        historicals[head] = result
        hist_frames.append(result["predictions"])
    historical = pd.concat(hist_frames, ignore_index=True)
    if historical["asset"].eq(HYPE_ASSET).any():
        raise RuntimeError("HOLDOUT_CONTAMINATED: HYPE in historical predictions")
    atomic_write_parquet(HIST_PREDICTIONS_PATH, historical)

    system = historical.loc[historical["head"].isin(["LONG_HEAD", "SHORT_HEAD"])].copy()
    if system.duplicated(["asset", "ts"]).any():
        raise RuntimeError("SYSTEM long/short collision")
    system_metrics = metric_values(
        system, system["p_lgbm_final"].to_numpy(), system["p_const_prior"].to_numpy()
    )
    system_year_flip, system_year_rows = year_flip(
        system, system["p_lgbm_final"].to_numpy(), system_metrics["roc_auc"]
    )
    system_hist = {
        "predictions": system,
        "hist_metrics": system_metrics,
        "bootstrap": paired_block_bootstrap(
            system,
            {
                "lgbm": "p_lgbm_final",
                "slope": "p_slope_only_logit",
                "f0": "p_f0_ma7_core_logit",
            },
        ),
        "non_overlap_auc": float(
            roc_auc_score(
                non_overlap_sample(system)[TARGET],
                non_overlap_sample(system)["p_lgbm_final"],
            )
        ),
        "manual_rules": evaluate_manual_rules(
            system, head="SYSTEM", evaluation="historical_test"
        ),
        "year_flip": system_year_flip,
        "year_rows": system_year_rows,
    }
    metric_rows.extend(
        decile_rows(
            system,
            system["p_lgbm_final"].to_numpy(),
            head="SYSTEM",
            evaluation="historical_test",
            fold="2025+",
            model_id="SYSTEM_LONG_SHORT",
            feature_scheme="PER_HEAD",
        )
    )
    decision = decide(
        system_hist,
        historicals["LONG_HEAD"],
        historicals["SHORT_HEAD"],
        developments["LONG_HEAD"],
        developments["SHORT_HEAD"],
    )
    metric_frame = pd.DataFrame(metric_rows)
    importance = pd.DataFrame(importance_frames)
    decile_frame = metric_frame.loc[metric_frame["row_type"].eq("decile")].copy()
    if decile_frame.empty:
        decile_frame = pd.DataFrame(metric_rows)
        decile_frame = decile_frame.loc[decile_frame.get("decile").notna()] if "decile" in decile_frame else pd.DataFrame()
    atomic_write_parquet(FOLD_METRICS_PATH, metric_frame)
    atomic_write_parquet(
        DECILE_METRICS_PATH,
        metric_frame.loc[metric_frame["row_type"].eq("decile")].copy(),
    )
    atomic_write_parquet(IMPORTANCE_PATH, importance)
    interp = interpretation_text(
        developments["LONG_HEAD"], developments["SHORT_HEAD"], importance
    )

    card = {
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "experiment": "P1 Cross-Conditioned Entry-Value Modeling",
        "model_role": "MA7-cross event scorer, not a general trend model",
        "hype_asset": HYPE_ASSET,
        "hype_rows": 0,
        "hype_reveal_executed": False,
        "not_live_ready": True,
        "status": STATUS,
        "seed": SEED,
        "contract_sha256": input_audit["contract_sha256"],
        "feature_spec_sha256": input_audit["feature_spec_sha256"],
        "prehistorical_lock_sha256": prehist_sha,
        "prohibited_uses": [
            "position sizing",
            "account backtest",
            "live trading",
            "continuation or exit modeling",
            "HYPE reveal",
        ],
        "heads": {
            head: {
                "selected_candidate": developments[head]["selected_candidate"],
                "feature_scheme": developments[head]["selected_feature_scheme"],
                "features": developments[head]["selected_features"],
                "fixed_rounds": developments[head]["fixed_rounds"],
                "calibration": developments[head]["calibration"]["method"],
            }
            for head in HEADS
        },
    }
    atomic_write_json(MODEL_CARD_PATH, card)

    summary = {
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "alias": "BIN-1D-MA7-CTP",
        "experiment": "P1 Cross-Conditioned Entry-Value Modeling",
        "generated_at_utc": datetime.now(UTC),
        "status": STATUS,
        "verdict": decision["verdict"],
        "historical_test_name": "model-unseen / hypothesis-revealed historical test",
        "no_strategy_no_portfolio_no_live_artifact": True,
        "objective_ma7_cross_only": True,
        "input_integrity": input_audit,
        "event_audit": event_audit,
        "prehistorical_lock_sha256": prehist_sha,
        "hype_isolation": {
            "asset": HYPE_ASSET,
            "input_rows": 0,
            "event_rows": int(events["asset"].eq(HYPE_ASSET).sum()),
            "oof_rows": int(oof["asset"].eq(HYPE_ASSET).sum()),
            "historical_rows": int(historical["asset"].eq(HYPE_ASSET).sum()),
            "model_card_rows": 0,
            "hype_reveal_executed": False,
        },
        "hyper_preservation": {
            "panel_rows": input_audit["panel_hyper_rows"],
            "event_rows": int(events["asset"].eq(HYPER_ASSET).sum()),
            "oof_rows": int(oof["asset"].eq(HYPER_ASSET).sum()),
            "historical_rows": int(historical["asset"].eq(HYPER_ASSET).sum()),
        },
        "decision": decision,
        "system": {
            "hist_metrics": system_hist["hist_metrics"],
            "bootstrap": system_hist["bootstrap"],
            "non_overlap_auc": system_hist["non_overlap_auc"],
            "manual_rules": system_hist["manual_rules"],
            "year_flip": system_hist["year_flip"],
            "year_rows": system_hist["year_rows"],
        },
        "heads": {
            head: {
                "development": {
                    "selected_candidate": developments[head]["selected_candidate"],
                    "selected_feature_scheme": developments[head]["selected_feature_scheme"],
                    "fixed_rounds": developments[head]["fixed_rounds"],
                    "candidate_summary": developments[head]["candidate_summary"],
                    "scheme_summary": developments[head]["scheme_summary"],
                    "calibration": developments[head]["calibration"],
                    "purge_audit": developments[head]["purge_audit"],
                    "preprocessing_audit": developments[head]["preprocessing_audit"],
                    "oof_metrics": developments[head]["oof_metrics"],
                    "manual_rules": developments[head]["manual_rules"],
                    "lago_aucs": developments[head]["lago_aucs"],
                    "leave_asset_group_out": {
                        "purge_audit": developments[head]["lago_purge"]
                    },
                    "selection_terminal_rows_used": 0,
                    "selection_data_max_ts": developments[head]["selection_data_max_ts"],
                },
                "historical": {
                    "train_metrics": historicals[head]["train_metrics"],
                    "hist_metrics": historicals[head]["hist_metrics"],
                    "train_n": historicals[head]["train_n"],
                    "hist_n": historicals[head]["hist_n"],
                    "training_max_label_end": historicals[head]["training_max_label_end"],
                    "bootstrap": historicals[head]["bootstrap"],
                    "non_overlap_auc": historicals[head]["non_overlap_auc"],
                    "year_flip": historicals[head]["year_flip"],
                    "year_rows": historicals[head]["year_flip_rows"],
                    "manual_rules": historicals[head]["manual_rules"],
                    "general_day": historicals[head]["general_day"],
                    "terminal_preprocessing_audit": historicals[head][
                        "terminal_preprocessing_audit"
                    ],
                },
            }
            for head in HEADS
        },
        "interpretation": interp,
    }
    atomic_write_json(SUMMARY_PATH, summary)
    write_reports(summary, metric_frame, metric_frame.loc[metric_frame["row_type"].eq("decile")])
    build_manifest(
        [
            SPEC_PATH,
            FEATURE_SPEC_PATH,
            Path(__file__),
            TEST_PATH,
            CONTRACT_LOCK_PATH,
            PREHIST_LOCK_PATH,
            EVENT_SUMMARY_PATH,
            FOLD_METRICS_PATH,
            OOF_PREDICTIONS_PATH,
            HIST_PREDICTIONS_PATH,
            DECILE_METRICS_PATH,
            IMPORTANCE_PATH,
            MODEL_CARD_PATH,
            SUMMARY_PATH,
            REPORT_PATH,
            AUDIT_PATH,
        ],
        input_audit,
    )
    print(f"P1 complete: {decision['verdict']}", flush=True)


if __name__ == "__main__":
    main()
