#!/usr/bin/env python3
"""Run frozen donor-only BIN-1D-CATL P1 walk-forward modeling.

The program has a hard two-stage boundary. It completes all D1-D3 model,
feature, round-count and calibration choices, writes a pre-terminal lock, and
only then reads the 2025+ donor terminal labels. HYPE is forbidden everywhere.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
from dataclasses import dataclass
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


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-cross-asset-trend-lifecycle"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAGNOSTIC_DIR = FAMILY_DIR / "diagnostics"
SPEC_PATH = (
    FAMILY_DIR
    / "specs"
    / "binance-1d-catl-p1-donor-walk-forward-modeling-contract-2026-08-31.md"
)
CONTRACT_LOCK_PATH = ARTIFACT_DIR / "binance_1d_catl_p1_contract_lock.json"
P0R_FEATURE_PATH = ARTIFACT_DIR / "binance_1d_catl_p0r_feature_blocks.json"
P0R_MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_catl_p0r_manifest.json"
PANEL_DIR = ARTIFACT_DIR / "p0r_donor_directional_modeling_panel"
PANEL_GLOB = PANEL_DIR / "**" / "*.parquet"

SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_catl_p1_summary.json"
FOLD_METRICS_PATH = ARTIFACT_DIR / "binance_1d_catl_p1_fold_metrics.parquet"
TERMINAL_PREDICTIONS_PATH = (
    ARTIFACT_DIR / "binance_1d_catl_p1_terminal_predictions.parquet"
)
OOF_PREDICTIONS_PATH = ARTIFACT_DIR / "binance_1d_catl_p1_oof_predictions.parquet"
MODEL_CARD_PATH = ARTIFACT_DIR / "binance_1d_catl_p1_model_card.json"
PRETERMINAL_LOCK_PATH = ARTIFACT_DIR / "binance_1d_catl_p1_preterminal_lock.json"
MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_catl_p1_manifest.json"
ENTRY_REPORT_PATH = (
    DIAGNOSTIC_DIR / "binance-1d-catl-p1-entry-model-2026-08-31.md"
)
CONTINUATION_REPORT_PATH = (
    DIAGNOSTIC_DIR / "binance-1d-catl-p1-continuation-model-2026-08-31.md"
)
AUDIT_REPORT_PATH = (
    DIAGNOSTIC_DIR / "binance-1d-catl-p1-modeling-audit-2026-08-31.md"
)
TEST_PATH = ROOT / "tests/test_binance_1d_catl_p1_donor_walk_forward_modeling.py"

HYPE_ASSET = "HYPE/USDT:USDT"
HYPER_ASSET = "HYPER/USDT:USDT"
SEED = 20260831
TERMINAL_START = pd.Timestamp("2025-01-01T00:00:00Z")
BOOTSTRAP_SAMPLES = 1000
BOOTSTRAP_BLOCK_DAYS = 28
STATUS = "explore / diagnostic-only / not promoted / not live-ready"

FOLDS = (
    (
        "D1",
        pd.Timestamp("2022-01-01T00:00:00Z"),
        pd.Timestamp("2023-01-01T00:00:00Z"),
    ),
    (
        "D2",
        pd.Timestamp("2023-01-01T00:00:00Z"),
        pd.Timestamp("2024-01-01T00:00:00Z"),
    ),
    (
        "D3",
        pd.Timestamp("2024-01-01T00:00:00Z"),
        TERMINAL_START,
    ),
)

LGBM_CANDIDATES: dict[str, dict[str, Any]] = {
    "L1": {
        "num_leaves": 15,
        "max_depth": 4,
        "min_data_in_leaf": 1000,
        "feature_fraction": 0.75,
        "lambda_l2": 1.0,
    },
    "L2": {
        "num_leaves": 31,
        "max_depth": 6,
        "min_data_in_leaf": 1000,
        "feature_fraction": 0.75,
        "lambda_l2": 3.0,
    },
    "L3": {
        "num_leaves": 31,
        "max_depth": 6,
        "min_data_in_leaf": 3000,
        "feature_fraction": 0.75,
        "lambda_l2": 5.0,
    },
    "L4": {
        "num_leaves": 63,
        "max_depth": 8,
        "min_data_in_leaf": 3000,
        "feature_fraction": 0.90,
        "lambda_l2": 8.0,
    },
}

COMMON_LGBM_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "metric": "auc",
    "learning_rate": 0.03,
    "n_estimators": 2000,
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


@dataclass(frozen=True, slots=True)
class TargetSpec:
    name: str
    eligibility: str
    target: str
    label_end: str
    net_return: str
    non_overlap_days: int
    question: str


TARGETS = (
    TargetSpec(
        name="entry",
        eligibility="model_eligible_entry_p0r",
        target="label_entry_success_20d",
        label_end="label_end_ts_20d",
        net_return="label_entry_net_return",
        non_overlap_days=20,
        question="下一 UTC open 起 20 日内先到 +2 ATR 而非 -1 ATR",
    ),
    TargetSpec(
        name="continuation",
        eligibility="model_eligible_continue_p0r",
        target="label_continue_success_5d",
        label_end="label_end_ts_5d",
        net_return="label_continue_net_return",
        non_overlap_days=5,
        question="下一 UTC open 起 5 日内先到 +1 ATR 而非 -0.75 ATR",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        help="Required acknowledgement of the frozen donor terminal evaluation.",
    )
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


def ensure_output_policy(force: bool) -> None:
    outputs = (
        SUMMARY_PATH,
        FOLD_METRICS_PATH,
        TERMINAL_PREDICTIONS_PATH,
        OOF_PREDICTIONS_PATH,
        MODEL_CARD_PATH,
        PRETERMINAL_LOCK_PATH,
        MANIFEST_PATH,
        ENTRY_REPORT_PATH,
        CONTINUATION_REPORT_PATH,
        AUDIT_REPORT_PATH,
    )
    existing = [path for path in outputs if path.exists()]
    if existing and not force:
        raise FileExistsError(
            "P1 outputs already exist; pass --force to reproduce: "
            + ", ".join(str(path.relative_to(ROOT)) for path in existing)
        )


def validate_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    required = (
        SPEC_PATH,
        CONTRACT_LOCK_PATH,
        P0R_FEATURE_PATH,
        P0R_MANIFEST_PATH,
        PANEL_DIR,
        TEST_PATH,
    )
    for path in required:
        if not path.exists():
            raise FileNotFoundError(path)

    contract_lock = json.loads(CONTRACT_LOCK_PATH.read_text(encoding="utf-8"))
    actual_contract_sha = sha256_file(SPEC_PATH)
    if actual_contract_sha != contract_lock["contract_sha256"]:
        raise RuntimeError(
            "Frozen P1 contract hash mismatch: "
            f"{actual_contract_sha} != {contract_lock['contract_sha256']}"
        )
    if contract_lock.get("hype_asset_excluded") != HYPE_ASSET:
        raise RuntimeError("P1 contract lock has the wrong HYPE boundary")
    if contract_lock.get("holdout_read") is not False:
        raise RuntimeError("P1 contract lock does not seal HYPE")

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
            raise RuntimeError(f"P0R artifact hash mismatch: {item['path']}")
    lineage = manifest.get("input_lineage", {})
    p0_manifest_path = ROOT / lineage["p0_manifest_path"]
    p0_manifest_actual = sha256_file(p0_manifest_path)
    if p0_manifest_actual != lineage["p0_manifest_sha256"]:
        raise RuntimeError("P0 manifest lineage hash mismatch")

    listed_panel = {
        item["path"]
        for item in manifest["artifacts"]
        if "/p0r_donor_directional_modeling_panel/" in item["path"]
    }
    actual_panel = {
        str(path.relative_to(ROOT)) for path in sorted(PANEL_DIR.rglob("*.parquet"))
    }
    if listed_panel != actual_panel:
        raise RuntimeError("P0R panel file set differs from its manifest")

    feature_spec = json.loads(P0R_FEATURE_PATH.read_text(encoding="utf-8"))
    if feature_spec.get("hype_asset_excluded") != HYPE_ASSET:
        raise RuntimeError("P0R feature spec HYPE exclusion mismatch")
    allowed = feature_spec["all_allowed_features"]
    if len(allowed) != len(set(allowed)):
        raise RuntimeError("P0R feature allowlist contains duplicates")
    forbidden_exact = {
        "asset",
        "asset_slug",
        "side",
        "side_sign",
        "ts",
        "feature_known_at",
        "entry_ts",
        "entry_ref",
        "atr_anchor",
    }
    leaked = [
        name
        for name in allowed
        if name in forbidden_exact
        or name.startswith(("label_", "future_"))
        or name.endswith(("_result", "_hours_to_hit"))
    ]
    if leaked:
        raise RuntimeError(f"Forbidden fields entered allowlist: {leaked}")

    connection = duckdb.connect()
    try:
        columns = {
            row[0]
            for row in connection.execute(
                """
                DESCRIBE SELECT * FROM read_parquet(
                    ?, union_by_name=true, hive_partitioning=true
                )
                """,
                [str(PANEL_GLOB)],
            ).fetchall()
        }
        if not set(allowed).issubset(columns):
            raise RuntimeError(
                f"Allowlist columns missing from panel: {sorted(set(allowed) - columns)}"
            )
        identity = connection.execute(
            """
            SELECT
                count(*) AS rows,
                count(DISTINCT asset) AS assets,
                count(*) FILTER (WHERE asset = ?) AS hype_rows,
                count(*) FILTER (WHERE asset = ?) AS hyper_rows,
                min(ts) AS min_ts,
                max(ts) AS max_ts
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

    audit = {
        "contract_sha256": actual_contract_sha,
        "contract_lock_sha256": sha256_file(CONTRACT_LOCK_PATH),
        "p0r_manifest_sha256": sha256_file(P0R_MANIFEST_PATH),
        "p0r_feature_spec_sha256": sha256_file(P0R_FEATURE_PATH),
        "p0_manifest_lineage_sha256": p0_manifest_actual,
        "p0r_artifact_hash_checks": hash_checks,
        "p0r_artifact_hashes_all_match": all(
            item["match"] for item in hash_checks
        ),
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


def build_feature_sets(feature_spec: dict[str, Any]) -> dict[str, list[str]]:
    blocks = feature_spec["feature_blocks"]
    full = list(feature_spec["all_allowed_features"])
    sets = {
        "G": list(blocks["ma_geometry"]),
        "GPV": [
            *blocks["ma_geometry"],
            *blocks["price_path"],
            *blocks["volatility_and_candle"],
        ],
        "FULL": full,
        "FULL_NO_EVENT": [
            name for name in full if name not in set(blocks["event_probes"])
        ],
        "FULL_NO_CROSS_MARKET": [
            name for name in full if name not in set(blocks["cross_market"])
        ],
    }
    if any(len(names) != len(set(names)) for names in sets.values()):
        raise RuntimeError("Feature scheme contains duplicate columns")
    return sets


def ma_probe_features(feature_spec: dict[str, Any]) -> list[str]:
    allowed = set(feature_spec["all_allowed_features"])
    candidates = [
        "dir_close_ma7_dist_atr",
        "dir_close_ma30_dist_atr",
        *[
            f"dir_ma{period}_slope_{days}d_atr"
            for period in (7, 30)
            for days in (1, 3, 5)
        ],
        "dir_ma7_slope_change_3d",
        "dir_ma30_slope_change_3d",
        "dir_ma7_slope_accel_5d",
        "dir_ma30_slope_accel_5d",
        "dir_raw_ma7_cross",
        "dir_raw_ma30_cross",
        "dir_price_side_ma7",
        "dir_price_side_ma30",
        "days_since_ma7_cross",
        "days_since_ma30_cross",
        "ma7_cross_count_7d",
        "ma30_cross_count_7d",
        "ma7_cross_count_14d",
        "ma30_cross_count_14d",
        "fast_slow_ma_direction_aligned",
        "ma7_cross_with_ma30_opposite_slope",
        "dir_price_ma7_ma30_joint_state",
        "large_cross_degree_atr",
        "probe_raw_ma7_cross_dir",
        "probe_raw_ma30_cross_dir",
        "probe_20d_range_breakout_dir",
        "probe_same_side_ma7_no_cross",
        "probe_same_side_ma30_no_cross",
        "probe_ma7_ma30_direction_aligned",
        "probe_ma7_cross_ma30_opposite",
    ]
    result = [name for name in candidates if name in allowed]
    if len(result) != len(candidates):
        raise RuntimeError(
            f"MA probe columns missing from allowlist: {set(candidates) - allowed}"
        )
    return result


def load_target_frame(
    spec: TargetSpec,
    feature_spec: dict[str, Any],
    *,
    stage: str,
) -> pd.DataFrame:
    if stage not in {"development", "terminal"}:
        raise ValueError(stage)
    comparator = "<" if stage == "development" else ">="
    identity_columns = [
        "asset",
        "ts",
        "side",
        "listing_age_days",
        "liquidity_rank_pct_p0r",
        "volatility_state_p0r",
        spec.label_end,
        spec.target,
        spec.net_return,
    ]
    columns = list(dict.fromkeys([*identity_columns, *feature_spec["all_allowed_features"]]))
    select_sql = ", ".join(f'"{name}"' for name in columns)
    query = f"""
        SELECT {select_sql}
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        WHERE "{spec.eligibility}"
          AND ts {comparator} TIMESTAMPTZ '2025-01-01 00:00:00+00:00'
        ORDER BY ts, asset, side
    """
    connection = duckdb.connect()
    connection.execute("SET TimeZone='UTC'")
    try:
        frame = connection.execute(query, [str(PANEL_GLOB)]).fetch_df()
    finally:
        connection.close()
    if frame.empty:
        raise RuntimeError(f"{spec.name} {stage} frame is empty")
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame[spec.label_end] = pd.to_datetime(frame[spec.label_end], utc=True)
    if frame["asset"].eq(HYPE_ASSET).any():
        raise RuntimeError("HOLDOUT_CONTAMINATED")
    if frame[[spec.target, spec.label_end]].isna().any().any():
        raise RuntimeError(f"{spec.name} eligible rows have incomplete targets")
    if frame.duplicated(["asset", "ts", "side"]).any():
        raise RuntimeError(f"{spec.name} contains duplicate asset-day-side rows")
    frame[spec.target] = frame[spec.target].astype("int8")
    frame["asset_group"] = frame["asset"].map(asset_group).astype("int8")
    categorical = set(feature_spec["categorical_features"])
    for column in feature_spec["all_allowed_features"]:
        if column in categorical:
            frame[column] = frame[column].astype("string")
        else:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(
                "float32"
            )
    return frame


def asset_group(asset: str) -> int:
    return int(hashlib.sha256(asset.encode("utf-8")).hexdigest(), 16) % 5


def fold_split(
    frame: pd.DataFrame,
    spec: TargetSpec,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = frame.loc[
        frame["ts"].lt(start) & frame[spec.label_end].lt(start)
    ].copy()
    validation = frame.loc[frame["ts"].ge(start) & frame["ts"].lt(end)].copy()
    if train.empty or validation.empty:
        raise RuntimeError(f"{spec.name} empty fold at {start}")
    if train[spec.label_end].max() >= start:
        raise RuntimeError(f"{spec.name} purge failure at {start}")
    if set(train["ts"]).intersection(set(validation["ts"])):
        raise RuntimeError(f"{spec.name} train/validation timestamp overlap")
    if train[spec.target].nunique() != 2 or validation[spec.target].nunique() != 2:
        raise RuntimeError(f"{spec.name} fold lacks both target classes")
    return train, validation


class LGBMPreprocessor:
    """One-column-per-feature encoder with train-only categorical dictionaries."""

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
            "numeric_missing_handling": "LightGBM native missing; no validation fit",
            "unknown_category_code": -1,
        }


class LinearPreprocessor:
    """Train-only median, missing indicator, scaling and categorical one-hot."""

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
            "numeric_means": self.means,
            "numeric_scales": self.scales,
            "missing_indicator_columns": self.missing_indicator_columns,
            "categorical_dictionaries": self.categories,
            "unknown_category_policy": "all-zero one-hot",
        }


def lgbm_params(candidate_id: str, *, rounds: int | None = None) -> dict[str, Any]:
    params = {**COMMON_LGBM_PARAMS, **LGBM_CANDIDATES[candidate_id]}
    if rounds is not None:
        params["n_estimators"] = int(rounds)
    return params


def fit_lgbm_matrices(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_validation: np.ndarray,
    y_validation: np.ndarray,
    categorical_indices: Sequence[int],
    candidate_id: str,
) -> tuple[lgb.LGBMClassifier, np.ndarray, int]:
    model = lgb.LGBMClassifier(**lgbm_params(candidate_id))
    model.fit(
        x_train,
        y_train,
        eval_set=[(x_validation, y_validation)],
        categorical_feature=list(categorical_indices),
        callbacks=[
            lgb.early_stopping(100, first_metric_only=True, verbose=False),
            lgb.log_evaluation(0),
        ],
    )
    probability = model.predict_proba(
        x_validation, num_iteration=model.best_iteration_
    )[:, 1]
    best_iteration = int(model.best_iteration_ or model.n_estimators)
    return model, probability.astype("float64"), best_iteration


def fit_lgbm_fixed(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    spec: TargetSpec,
    features: Sequence[str],
    categorical: Sequence[str],
    candidate_id: str,
    rounds: int,
) -> tuple[lgb.LGBMClassifier, np.ndarray, LGBMPreprocessor]:
    preprocessor = LGBMPreprocessor(features, categorical).fit(train)
    x_train = preprocessor.transform(train)
    x_validation = preprocessor.transform(validation)
    model = lgb.LGBMClassifier(**lgbm_params(candidate_id, rounds=rounds))
    model.fit(
        x_train,
        train[spec.target].to_numpy(dtype="int8"),
        categorical_feature=preprocessor.categorical_indices,
        callbacks=[lgb.log_evaluation(0)],
    )
    probability = model.predict_proba(x_validation)[:, 1].astype("float64")
    del x_train, x_validation
    gc.collect()
    return model, probability, preprocessor


def fit_logit(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    spec: TargetSpec,
    features: Sequence[str],
    categorical: Sequence[str],
) -> tuple[np.ndarray, dict[str, Any]]:
    preprocessor = LinearPreprocessor(features, categorical).fit(train)
    x_train = preprocessor.transform(train)
    x_validation = preprocessor.transform(validation)
    model = LogisticRegression(
        penalty="l2",
        C=1.0,
        solver="lbfgs",
        max_iter=300,
        tol=1e-6,
        random_state=SEED,
    )
    model.fit(x_train, train[spec.target].to_numpy(dtype="int8"))
    probability = model.predict_proba(x_validation)[:, 1].astype("float64")
    audit = {
        **preprocessor.audit(),
        "model": "LogisticRegression",
        "penalty": "l2",
        "C": 1.0,
        "solver": "lbfgs",
        "iterations": int(model.n_iter_[0]),
        "train_rows": int(len(train)),
        "validation_rows": int(len(validation)),
        "train_max_ts": train["ts"].max(),
        "train_max_label_end": train[spec.label_end].max(),
        "validation_min_ts": validation["ts"].min(),
    }
    del x_train, x_validation, model
    gc.collect()
    return probability, audit


def clip_probability(probability: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(probability, dtype="float64"), 1e-8, 1.0 - 1e-8)


def calibration_shape(y: np.ndarray, probability: np.ndarray) -> tuple[float, float]:
    if len(np.unique(y)) < 2:
        return math.nan, math.nan
    logit = np.log(clip_probability(probability) / (1.0 - clip_probability(probability)))
    model = LogisticRegression(
        penalty=None,
        solver="lbfgs",
        max_iter=300,
        random_state=SEED,
    ).fit(logit.reshape(-1, 1), y)
    return float(model.intercept_[0]), float(model.coef_[0, 0])


def ece_10(y: np.ndarray, probability: np.ndarray) -> float:
    p = clip_probability(probability)
    bins = np.minimum((p * 10).astype(int), 9)
    total = 0.0
    for bucket in range(10):
        mask = bins == bucket
        if mask.any():
            total += float(mask.mean()) * abs(
                float(y[mask].mean()) - float(p[mask].mean())
            )
    return total


def decile_codes(probability: np.ndarray) -> np.ndarray:
    ranks = pd.Series(probability).rank(method="first")
    return (
        pd.qcut(ranks, 10, labels=False, duplicates="drop")
        .astype("int16")
        .to_numpy()
        + 1
    )


def asset_balanced_weights(frame: pd.DataFrame) -> np.ndarray:
    counts = frame["asset"].value_counts()
    return frame["asset"].map(
        {asset: len(frame) / (len(counts) * count) for asset, count in counts.items()}
    ).to_numpy(dtype="float64")


def metric_values(
    frame: pd.DataFrame,
    spec: TargetSpec,
    probability: np.ndarray,
    const_probability: np.ndarray,
) -> dict[str, Any]:
    y = frame[spec.target].to_numpy(dtype="int8")
    p = clip_probability(probability)
    p_const = clip_probability(const_probability)
    weights = asset_balanced_weights(frame)
    auc = float(roc_auc_score(y, p))
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
        "top_decile_success_rate": float(top.mean()),
        "top_decile_uplift": float(top.mean() - y.mean()),
        "bottom_decile_success_rate": float(bottom.mean()),
        "top_bottom_success_rate_diff": float(top.mean() - bottom.mean()),
        "asset_balanced_auc": float(roc_auc_score(y, p, sample_weight=weights)),
        "asset_balanced_brier": float(
            np.average(np.square(y.astype("float64") - p), weights=weights)
        ),
    }


def metric_row(
    frame: pd.DataFrame,
    spec: TargetSpec,
    probability: np.ndarray,
    const_probability: np.ndarray,
    *,
    evaluation: str,
    fold: str,
    model_id: str,
    feature_scheme: str,
    calibration: str,
    train: pd.DataFrame | None = None,
    row_type: str = "metric",
    stratum_type: str = "all",
    stratum_value: str = "all",
) -> dict[str, Any]:
    result = {
        "target_name": spec.name,
        "row_type": row_type,
        "evaluation": evaluation,
        "fold": fold,
        "model_id": model_id,
        "feature_scheme": feature_scheme,
        "calibration": calibration,
        "stratum_type": stratum_type,
        "stratum_value": str(stratum_value),
        "train_n": int(len(train)) if train is not None else None,
        "train_date_min": train["ts"].min() if train is not None else None,
        "train_date_max": train["ts"].max() if train is not None else None,
        "train_label_end_max": (
            train[spec.label_end].max() if train is not None else None
        ),
        **metric_values(frame, spec, probability, const_probability),
    }
    return result


def decile_rows(
    frame: pd.DataFrame,
    spec: TargetSpec,
    probability: np.ndarray,
    *,
    evaluation: str,
    fold: str,
    model_id: str,
    feature_scheme: str,
    calibration: str,
) -> list[dict[str, Any]]:
    work = frame[[spec.target, spec.net_return]].copy()
    work["decile"] = decile_codes(probability)
    overall = float(work[spec.target].mean())
    rows = []
    for decile, group in work.groupby("decile", sort=True):
        rows.append(
            {
                "target_name": spec.name,
                "row_type": "decile",
                "evaluation": evaluation,
                "fold": fold,
                "model_id": model_id,
                "feature_scheme": feature_scheme,
                "calibration": calibration,
                "stratum_type": "probability_decile",
                "stratum_value": str(int(decile)),
                "decile": int(decile),
                "eval_n": int(len(group)),
                "positive_rate": float(group[spec.target].mean()),
                "decile_uplift": float(group[spec.target].mean() - overall),
                "net_return_mean": float(group[spec.net_return].mean()),
                "net_return_median": float(group[spec.net_return].median()),
            }
        )
    return rows


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
    order = {name: index for index, name in enumerate(feature_summary)}
    return max(
        feature_summary,
        key=lambda name: (
            feature_summary[name]["macro_auc"],
            -feature_summary[name]["macro_log_loss"],
            -order[name],
        ),
    )


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
    if not indices:
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
    del permuted
    return float(baseline - score)


def aggregate_feature_importance(
    fold_importance: list[dict[str, float]],
    feature_spec: dict[str, Any],
) -> dict[str, Any]:
    all_features = feature_spec["all_allowed_features"]
    feature_values = {
        feature: float(
            np.mean([fold.get(feature, 0.0) for fold in fold_importance])
        )
        for feature in all_features
        if any(feature in fold for fold in fold_importance)
    }
    total = sum(feature_values.values())
    if total > 0:
        feature_values = {key: value / total for key, value in feature_values.items()}
    block_by_feature = {
        feature: block
        for block, features in feature_spec["feature_blocks"].items()
        for feature in features
    }
    blocks: dict[str, float] = {}
    for feature, value in feature_values.items():
        block = block_by_feature[feature]
        blocks[block] = blocks.get(block, 0.0) + value
    return {
        "importance_type": "mean LightGBM split gain share",
        "top_features": [
            {"feature": feature, "gain_share": value}
            for feature, value in sorted(
                feature_values.items(), key=lambda item: -item[1]
            )[:20]
        ],
        "feature_blocks": [
            {"feature_block": block, "gain_share": value}
            for block, value in sorted(blocks.items(), key=lambda item: -item[1])
        ],
        "causality_warning": "Feature importance is predictive dependence, not causality.",
    }


def fit_platt(oof: pd.DataFrame, spec: TargetSpec) -> dict[str, Any]:
    y = oof[spec.target].to_numpy(dtype="int8")
    raw = clip_probability(oof["p_lgbm_raw"].to_numpy())
    raw_logit = np.log(raw / (1.0 - raw))
    model = LogisticRegression(
        penalty=None,
        solver="lbfgs",
        max_iter=300,
        random_state=SEED,
    ).fit(raw_logit.reshape(-1, 1), y)
    candidate = model.predict_proba(raw_logit.reshape(-1, 1))[:, 1]
    raw_brier = float(brier_score_loss(y, raw))
    candidate_brier = float(brier_score_loss(y, candidate))
    raw_log_loss = float(log_loss(y, raw, labels=[0, 1]))
    candidate_log_loss = float(log_loss(y, candidate, labels=[0, 1]))
    both_no_improvement = (
        candidate_brier >= raw_brier and candidate_log_loss >= raw_log_loss
    )
    method = "none" if both_no_improvement else "platt"
    return {
        "method": method,
        "candidate_method": "platt",
        "intercept": float(model.intercept_[0]),
        "slope": float(model.coef_[0, 0]),
        "development_raw_brier": raw_brier,
        "development_candidate_brier": candidate_brier,
        "development_raw_log_loss": raw_log_loss,
        "development_candidate_log_loss": candidate_log_loss,
        "selection_rule": (
            "none only if Platt improves neither development OOF Brier nor log loss"
        ),
        "fit_rows": int(len(oof)),
        "fit_min_ts": oof["ts"].min(),
        "fit_max_ts": oof["ts"].max(),
        "terminal_rows_used": 0,
    }


def apply_calibration(probability: np.ndarray, calibration: dict[str, Any]) -> np.ndarray:
    raw = clip_probability(probability)
    if calibration["method"] == "none":
        return raw
    logits = np.log(raw / (1.0 - raw))
    value = calibration["intercept"] + calibration["slope"] * logits
    return 1.0 / (1.0 + np.exp(-value))


def leave_asset_group_out(
    frame: pd.DataFrame,
    spec: TargetSpec,
    feature_spec: dict[str, Any],
    features: Sequence[str],
    candidate_id: str,
    rounds: int,
    metric_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    predictions: list[pd.DataFrame] = []
    purge_rows: list[dict[str, Any]] = []
    for group in range(5):
        for fold_name, start, end in FOLDS:
            base_train, base_validation = fold_split(frame, spec, start, end)
            train = base_train.loc[base_train["asset_group"].ne(group)].copy()
            validation = base_validation.loc[
                base_validation["asset_group"].eq(group)
            ].copy()
            if train.empty or validation.empty:
                raise RuntimeError(
                    f"{spec.name} leave-group {group} {fold_name} is empty"
                )
            model, probability, preprocessor = fit_lgbm_fixed(
                train,
                validation,
                spec,
                features,
                feature_spec["categorical_features"],
                candidate_id,
                rounds,
            )
            prior = float(train[spec.target].mean())
            scored = validation[
                ["asset", "ts", "side", spec.target, spec.net_return]
            ].copy()
            scored["fold"] = fold_name
            scored["asset_group"] = group
            scored["p_lgbm"] = probability
            scored["p_const_prior"] = prior
            predictions.append(scored)
            purge_rows.append(
                {
                    "asset_group": group,
                    "fold": fold_name,
                    "train_n": int(len(train)),
                    "validation_n": int(len(validation)),
                    "train_max_label_end": train[spec.label_end].max(),
                    "validation_start": start,
                    "purge_pass": bool(train[spec.label_end].max() < start),
                    "preprocessing_fit_scope": preprocessor.audit()["fit_scope"],
                }
            )
            del model, preprocessor, base_train, base_validation, train, validation
            gc.collect()
    combined = pd.concat(predictions, ignore_index=True)
    groups: list[dict[str, Any]] = []
    for group, group_frame in combined.groupby("asset_group", sort=True):
        p = group_frame["p_lgbm"].to_numpy()
        p_const = group_frame["p_const_prior"].to_numpy()
        values = metric_values(group_frame, spec, p, p_const)
        groups.append({"asset_group": int(group), **values})
        metric_rows.append(
            {
                "target_name": spec.name,
                "row_type": "leave_asset_group_out",
                "evaluation": "development",
                "fold": "D1-D3",
                "model_id": f"LGBM_{candidate_id}",
                "feature_scheme": "selected",
                "calibration": "raw",
                "stratum_type": "asset_group",
                "stratum_value": str(int(group)),
                **values,
            }
        )
    aucs = [item["roc_auc"] for item in groups]
    uplifts = [item["top_decile_uplift"] for item in groups]
    return {
        "assignment": "int(sha256(asset).hexdigest(), 16) % 5",
        "fixed_rounds": rounds,
        "groups": groups,
        "median_auc": float(np.median(aucs)),
        "minimum_auc": float(np.min(aucs)),
        "median_top_decile_uplift": float(np.median(uplifts)),
        "hype_rows": 0,
        "purge_audit": purge_rows,
    }


def development_target(
    spec: TargetSpec,
    feature_spec: dict[str, Any],
    metric_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    print(f"P1 {spec.name}: load development-only rows...", flush=True)
    frame = load_target_frame(spec, feature_spec, stage="development")
    feature_sets = build_feature_sets(feature_spec)
    categorical = feature_spec["categorical_features"]
    cross_market = feature_spec["feature_blocks"]["cross_market"]
    splits: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    purge_audit: list[dict[str, Any]] = []
    for fold_name, start, end in FOLDS:
        train, validation = fold_split(frame, spec, start, end)
        splits[fold_name] = (train, validation)
        purge_audit.append(
            {
                "fold": fold_name,
                "train_n": int(len(train)),
                "validation_n": int(len(validation)),
                "train_max_ts": train["ts"].max(),
                "train_max_label_end": train[spec.label_end].max(),
                "validation_start": start,
                "validation_end_exclusive": end,
                "purge_pass": bool(train[spec.label_end].max() < start),
                "same_timestamp_overlap": 0,
            }
        )

    print(f"P1 {spec.name}: compare L1-L4 on FULL...", flush=True)
    candidate_artifacts: dict[str, dict[str, dict[str, Any]]] = {
        candidate_id: {} for candidate_id in LGBM_CANDIDATES
    }
    candidate_fold_values: dict[str, list[dict[str, float]]] = {
        candidate_id: [] for candidate_id in LGBM_CANDIDATES
    }
    for fold_index, (fold_name, _, _) in enumerate(FOLDS, start=1):
        train, validation = splits[fold_name]
        preprocessor = LGBMPreprocessor(
            feature_sets["FULL"], categorical
        ).fit(train)
        x_train = preprocessor.transform(train)
        x_validation = preprocessor.transform(validation)
        y_train = train[spec.target].to_numpy(dtype="int8")
        y_validation = validation[spec.target].to_numpy(dtype="int8")
        prior = float(y_train.mean())
        p_const = np.full(len(validation), prior)
        for candidate_id in LGBM_CANDIDATES:
            model, probability, best_iteration = fit_lgbm_matrices(
                x_train,
                y_train,
                x_validation,
                y_validation,
                preprocessor.categorical_indices,
                candidate_id,
            )
            values = metric_values(validation, spec, probability, p_const)
            importance = dict(
                zip(
                    feature_sets["FULL"],
                    model.booster_.feature_importance(importance_type="gain").astype(
                        float
                    ),
                    strict=True,
                )
            )
            perm_drop = permutation_block_drop(
                model,
                x_validation,
                y_validation,
                feature_sets["FULL"],
                cross_market,
                fold_index=fold_index,
                best_iteration=best_iteration,
            )
            candidate_artifacts[candidate_id][fold_name] = {
                "probability": probability,
                "best_iteration": best_iteration,
                "importance": importance,
                "cross_market_permutation_auc_drop": perm_drop,
                "preprocessing_audit": preprocessor.audit(),
            }
            candidate_fold_values[candidate_id].append(values)
            metric_rows.append(
                {
                    "target_name": spec.name,
                    "row_type": "parameter_search",
                    "evaluation": "development",
                    "fold": fold_name,
                    "model_id": f"LGBM_{candidate_id}",
                    "feature_scheme": "FULL",
                    "calibration": "raw",
                    "train_n": int(len(train)),
                    "best_iteration": best_iteration,
                    **values,
                }
            )
            del model
        del x_train, x_validation, y_train, y_validation, preprocessor
        gc.collect()
    candidate_summary = {
        candidate_id: {
            "macro_auc": float(
                np.mean([row["roc_auc"] for row in fold_values])
            ),
            "macro_log_loss": float(
                np.mean([row["log_loss"] for row in fold_values])
            ),
            "best_iterations": [
                candidate_artifacts[candidate_id][fold_name]["best_iteration"]
                for fold_name, _, _ in FOLDS
            ],
        }
        for candidate_id, fold_values in candidate_fold_values.items()
    }
    selected_candidate = select_lgbm_candidate(candidate_summary)

    print(
        f"P1 {spec.name}: compare frozen feature schemes with {selected_candidate}...",
        flush=True,
    )
    scheme_artifacts: dict[str, dict[str, dict[str, Any]]] = {
        "FULL": candidate_artifacts[selected_candidate]
    }
    scheme_fold_values: dict[str, list[dict[str, float]]] = {
        "FULL": candidate_fold_values[selected_candidate]
    }
    for scheme, features in feature_sets.items():
        if scheme == "FULL":
            continue
        scheme_artifacts[scheme] = {}
        scheme_fold_values[scheme] = []
        for fold_index, (fold_name, _, _) in enumerate(FOLDS, start=1):
            train, validation = splits[fold_name]
            preprocessor = LGBMPreprocessor(features, categorical).fit(train)
            x_train = preprocessor.transform(train)
            x_validation = preprocessor.transform(validation)
            y_train = train[spec.target].to_numpy(dtype="int8")
            y_validation = validation[spec.target].to_numpy(dtype="int8")
            model, probability, best_iteration = fit_lgbm_matrices(
                x_train,
                y_train,
                x_validation,
                y_validation,
                preprocessor.categorical_indices,
                selected_candidate,
            )
            prior = float(y_train.mean())
            values = metric_values(
                validation, spec, probability, np.full(len(validation), prior)
            )
            importance = dict(
                zip(
                    features,
                    model.booster_.feature_importance(importance_type="gain").astype(
                        float
                    ),
                    strict=True,
                )
            )
            perm_drop = permutation_block_drop(
                model,
                x_validation,
                y_validation,
                features,
                cross_market,
                fold_index=fold_index,
                best_iteration=best_iteration,
            )
            scheme_artifacts[scheme][fold_name] = {
                "probability": probability,
                "best_iteration": best_iteration,
                "importance": importance,
                "cross_market_permutation_auc_drop": perm_drop,
                "preprocessing_audit": preprocessor.audit(),
            }
            scheme_fold_values[scheme].append(values)
            metric_rows.append(
                {
                    "target_name": spec.name,
                    "row_type": "feature_search",
                    "evaluation": "development",
                    "fold": fold_name,
                    "model_id": f"LGBM_{selected_candidate}",
                    "feature_scheme": scheme,
                    "calibration": "raw",
                    "train_n": int(len(train)),
                    "best_iteration": best_iteration,
                    **values,
                }
            )
            del model, preprocessor, x_train, x_validation, y_train, y_validation
            gc.collect()
    feature_summary = {
        scheme: {
            "macro_auc": float(np.mean([row["roc_auc"] for row in values])),
            "macro_log_loss": float(
                np.mean([row["log_loss"] for row in values])
            ),
            "best_iterations": [
                scheme_artifacts[scheme][fold_name]["best_iteration"]
                for fold_name, _, _ in FOLDS
            ],
        }
        for scheme, values in scheme_fold_values.items()
    }
    selected_scheme = select_feature_scheme(feature_summary)
    selected_features = feature_sets[selected_scheme]
    selected_rounds = int(
        np.median(feature_summary[selected_scheme]["best_iterations"])
    )

    print(f"P1 {spec.name}: fit frozen logistic baselines...", flush=True)
    baseline_features = {
        "MA_PROBE_LOGIT": ma_probe_features(feature_spec),
        "G_ONLY_LOGIT": feature_sets["G"],
        "FULL_LOGIT": feature_sets["FULL"],
    }
    oof_frames: list[pd.DataFrame] = []
    preprocessing_audit: list[dict[str, Any]] = []
    selected_importance: list[dict[str, float]] = []
    selected_permutation: list[dict[str, Any]] = []
    for fold_index, (fold_name, _, _) in enumerate(FOLDS, start=1):
        train, validation = splits[fold_name]
        prior = float(train[spec.target].mean())
        selected = scheme_artifacts[selected_scheme][fold_name]
        scored = validation[
            [
                "asset",
                "ts",
                "side",
                "listing_age_days",
                "liquidity_rank_pct_p0r",
                "volatility_state_p0r",
                "asset_group",
                spec.target,
                spec.net_return,
            ]
        ].copy()
        scored["fold"] = fold_name
        scored["p_const_prior"] = prior
        scored["p_lgbm_raw"] = selected["probability"]
        selected_importance.append(selected["importance"])
        selected_permutation.append(
            {
                "fold": fold_name,
                "auc_drop": selected["cross_market_permutation_auc_drop"],
            }
        )
        preprocessing_audit.append(
            {
                "fold": fold_name,
                "model_id": f"LGBM_{selected_candidate}",
                "feature_scheme": selected_scheme,
                "train_n": int(len(train)),
                "validation_n": int(len(validation)),
                "train_max_label_end": train[spec.label_end].max(),
                "validation_start": validation["ts"].min(),
                **selected["preprocessing_audit"],
            }
        )
        for model_id, features in baseline_features.items():
            probability, audit = fit_logit(
                train, validation, spec, features, categorical
            )
            column = {
                "MA_PROBE_LOGIT": "p_ma_probe_logit",
                "G_ONLY_LOGIT": "p_g_only_logit",
                "FULL_LOGIT": "p_full_logit",
            }[model_id]
            scored[column] = probability
            preprocessing_audit.append(
                {
                    "fold": fold_name,
                    "model_id": model_id,
                    "feature_scheme": (
                        "MA_PROBE"
                        if model_id == "MA_PROBE_LOGIT"
                        else "G"
                        if model_id == "G_ONLY_LOGIT"
                        else "FULL"
                    ),
                    **audit,
                }
            )
            metric_rows.append(
                metric_row(
                    validation,
                    spec,
                    probability,
                    np.full(len(validation), prior),
                    evaluation="development",
                    fold=fold_name,
                    model_id=model_id,
                    feature_scheme=(
                        "MA_PROBE"
                        if model_id == "MA_PROBE_LOGIT"
                        else "G"
                        if model_id == "G_ONLY_LOGIT"
                        else "FULL"
                    ),
                    calibration="raw",
                    train=train,
                )
            )
        metric_rows.append(
            metric_row(
                validation,
                spec,
                np.full(len(validation), prior),
                np.full(len(validation), prior),
                evaluation="development",
                fold=fold_name,
                model_id="CONST_PRIOR",
                feature_scheme="NONE",
                calibration="raw",
                train=train,
            )
        )
        oof_frames.append(scored)
    oof = pd.concat(oof_frames, ignore_index=True)
    if oof.duplicated(["asset", "ts", "side"]).any():
        raise RuntimeError(f"{spec.name} OOF row was predicted more than once")
    if oof["ts"].min() < FOLDS[0][1] or oof["ts"].max() >= TERMINAL_START:
        raise RuntimeError(f"{spec.name} OOF contains non-development dates")
    calibration = fit_platt(oof, spec)
    oof["p_lgbm_final"] = apply_calibration(
        oof["p_lgbm_raw"].to_numpy(), calibration
    )
    oof["calibration_method"] = calibration["method"]
    oof["target_name"] = spec.name

    raw_fold_rows = []
    final_fold_rows = []
    for fold_name, _, _ in FOLDS:
        fold_frame = oof.loc[oof["fold"].eq(fold_name)].copy()
        p_const = fold_frame["p_const_prior"].to_numpy()
        raw_row = metric_row(
            fold_frame,
            spec,
            fold_frame["p_lgbm_raw"].to_numpy(),
            p_const,
            evaluation="development",
            fold=fold_name,
            model_id=f"LGBM_{selected_candidate}",
            feature_scheme=selected_scheme,
            calibration="raw",
            row_type="raw_metric",
        )
        metric_rows.append(raw_row)
        raw_fold_rows.append(raw_row)
        row = metric_row(
            fold_frame,
            spec,
            fold_frame["p_lgbm_final"].to_numpy(),
            p_const,
            evaluation="development",
            fold=fold_name,
            model_id=f"LGBM_{selected_candidate}",
            feature_scheme=selected_scheme,
            calibration=calibration["method"],
        )
        row["paired_auc_diff_vs_ma_probe"] = (
            row["roc_auc"]
            - roc_auc_score(
                fold_frame[spec.target], fold_frame["p_ma_probe_logit"]
            )
        )
        row["paired_auc_diff_vs_g_only"] = (
            row["roc_auc"]
            - roc_auc_score(
                fold_frame[spec.target], fold_frame["p_g_only_logit"]
            )
        )
        metric_rows.append(row)
        final_fold_rows.append(row)
        metric_rows.extend(
            decile_rows(
                fold_frame,
                spec,
                fold_frame["p_lgbm_final"].to_numpy(),
                evaluation="development",
                fold=fold_name,
                model_id=f"LGBM_{selected_candidate}",
                feature_scheme=selected_scheme,
                calibration=calibration["method"],
            )
        )
    macro_fields = (
        "roc_auc",
        "pr_auc",
        "log_loss",
        "brier",
        "brier_skill_vs_const",
        "calibration_intercept",
        "calibration_slope",
        "ece_10",
        "top_decile_uplift",
        "top_bottom_success_rate_diff",
        "asset_balanced_auc",
        "asset_balanced_brier",
        "paired_auc_diff_vs_ma_probe",
        "paired_auc_diff_vs_g_only",
    )
    raw_macro_fields = tuple(
        field
        for field in macro_fields
        if not field.startswith("paired_auc_diff")
    )
    raw_macro = {
        field: float(np.mean([row[field] for row in raw_fold_rows]))
        for field in raw_macro_fields
    }
    raw_macro.update(
        {
            "target_name": spec.name,
            "row_type": "raw_macro",
            "evaluation": "development",
            "fold": "D1-D3_MACRO",
            "model_id": f"LGBM_{selected_candidate}",
            "feature_scheme": selected_scheme,
            "calibration": "raw",
            "eval_n": int(len(oof)),
            "asset_count": int(oof["asset"].nunique()),
            "date_min": oof["ts"].min(),
            "date_max": oof["ts"].max(),
            "positive_rate": float(oof[spec.target].mean()),
        }
    )
    metric_rows.append(raw_macro)
    macro = {
        field: float(np.mean([row[field] for row in final_fold_rows]))
        for field in macro_fields
    }
    macro.update(
        {
            "target_name": spec.name,
            "row_type": "macro",
            "evaluation": "development",
            "fold": "D1-D3_MACRO",
            "model_id": f"LGBM_{selected_candidate}",
            "feature_scheme": selected_scheme,
            "calibration": calibration["method"],
            "eval_n": int(len(oof)),
            "asset_count": int(oof["asset"].nunique()),
            "date_min": oof["ts"].min(),
            "date_max": oof["ts"].max(),
            "positive_rate": float(oof[spec.target].mean()),
        }
    )
    metric_rows.append(macro)

    print(f"P1 {spec.name}: deterministic leave-asset-group-out...", flush=True)
    leave_group = leave_asset_group_out(
        frame,
        spec,
        feature_spec,
        selected_features,
        selected_candidate,
        selected_rounds,
        metric_rows,
    )
    importance = aggregate_feature_importance(
        selected_importance, feature_spec
    )
    for item in importance["feature_blocks"]:
        metric_rows.append(
            {
                "target_name": spec.name,
                "row_type": "feature_block_importance",
                "evaluation": "development",
                "fold": "D1-D3",
                "model_id": f"LGBM_{selected_candidate}",
                "feature_scheme": selected_scheme,
                "calibration": "raw",
                "stratum_type": "feature_block",
                "stratum_value": item["feature_block"],
                "point_estimate": item["gain_share"],
            }
        )
    for item in selected_permutation:
        metric_rows.append(
            {
                "target_name": spec.name,
                "row_type": "cross_market_block_permutation",
                "evaluation": "development",
                "fold": item["fold"],
                "model_id": f"LGBM_{selected_candidate}",
                "feature_scheme": selected_scheme,
                "calibration": "raw",
                "stratum_type": "feature_block",
                "stratum_value": "cross_market",
                "point_estimate": item["auc_drop"],
            }
        )

    development = {
        "sample_rows_pre2025": int(len(frame)),
        "sample_assets_pre2025": int(frame["asset"].nunique()),
        "selected_candidate": selected_candidate,
        "candidate_selection": candidate_summary,
        "selected_feature_scheme": selected_scheme,
        "feature_selection": feature_summary,
        "selected_features": selected_features,
        "selected_feature_count": len(selected_features),
        "fixed_terminal_rounds": selected_rounds,
        "calibration": calibration,
        "raw_macro": raw_macro,
        "raw_folds": raw_fold_rows,
        "macro": macro,
        "folds": final_fold_rows,
        "purge_audit": purge_audit,
        "preprocessing_audit": preprocessing_audit,
        "leave_asset_group_out": leave_group,
        "cross_market_permutation": selected_permutation,
        "feature_importance": importance,
        "ma_probe_features": baseline_features["MA_PROBE_LOGIT"],
        "selection_data_max_ts": oof["ts"].max(),
        "selection_terminal_rows_used": 0,
        "hype_rows": 0,
        "hyper_rows": int(frame["asset"].eq(HYPER_ASSET).sum()),
    }
    del frame, splits
    gc.collect()
    return {"target": spec, "oof": oof, "development": development}


def auc_block_matrix(
    scores: np.ndarray, y: np.ndarray, block: np.ndarray, block_count: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    positive_count = np.bincount(block[y == 1], minlength=block_count).astype(
        "float64"
    )
    negative_count = np.bincount(block[y == 0], minlength=block_count).astype(
        "float64"
    )
    matrix = np.zeros((block_count, block_count), dtype="float64")
    positives = [scores[(block == index) & (y == 1)] for index in range(block_count)]
    negatives = [
        np.sort(scores[(block == index) & (y == 0)])
        for index in range(block_count)
    ]
    for left in range(block_count):
        for right in range(block_count):
            lower = np.searchsorted(negatives[right], positives[left], side="left")
            upper = np.searchsorted(negatives[right], positives[left], side="right")
            matrix[left, right] = float(
                lower.sum() + 0.5 * (upper - lower).sum()
            )
    return matrix, positive_count, negative_count


def auc_from_block_counts(
    counts: np.ndarray,
    matrix: np.ndarray,
    positives: np.ndarray,
    negatives: np.ndarray,
) -> np.ndarray:
    numerator = np.einsum("bi,ij,bj->b", counts, matrix, counts, optimize=True)
    denominator = (counts @ positives) * (counts @ negatives)
    return numerator / denominator


def weighted_top_decile_uplift_samples(
    probability: np.ndarray,
    y: np.ndarray,
    block: np.ndarray,
    counts: np.ndarray,
) -> np.ndarray:
    order = np.argsort(probability, kind="mergesort")[::-1]
    ordered_y = y[order].astype("float64")
    ordered_block = block[order]
    result = np.empty(len(counts), dtype="float64")
    block_positive = np.bincount(
        block, weights=y.astype("float64"), minlength=counts.shape[1]
    )
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
        top_rate = top_positive / top_weight
        result[sample_index] = top_rate - overall_rate
    return result


def paired_block_bootstrap(
    terminal: pd.DataFrame, spec: TargetSpec
) -> dict[str, Any]:
    y = terminal[spec.target].to_numpy(dtype="int8")
    origin = terminal["ts"].min().normalize()
    block = (
        (terminal["ts"].dt.normalize() - origin).dt.days
        // BOOTSTRAP_BLOCK_DAYS
    ).to_numpy(dtype="int16")
    block_count = int(block.max()) + 1
    rng = np.random.default_rng(SEED)
    draws = rng.integers(
        0, block_count, size=(BOOTSTRAP_SAMPLES, block_count), endpoint=False
    )
    counts = np.zeros((BOOTSTRAP_SAMPLES, block_count), dtype="int16")
    for sample in range(BOOTSTRAP_SAMPLES):
        counts[sample] = np.bincount(draws[sample], minlength=block_count)
    draw_sha = hashlib.sha256(counts.tobytes()).hexdigest()

    auc_samples: dict[str, np.ndarray] = {}
    score_columns = {
        "lgbm": "p_lgbm_final",
        "ma_probe": "p_ma_probe_logit",
        "g_only": "p_g_only_logit",
    }
    for name, column in score_columns.items():
        matrix, positives, negatives = auc_block_matrix(
            terminal[column].to_numpy(dtype="float64"),
            y,
            block,
            block_count,
        )
        auc_samples[name] = auc_from_block_counts(
            counts.astype("float64"), matrix, positives, negatives
        )
    top_uplift = weighted_top_decile_uplift_samples(
        terminal["p_lgbm_final"].to_numpy(dtype="float64"),
        y,
        block,
        counts,
    )
    model_error = np.square(y - terminal["p_lgbm_final"].to_numpy())
    const_error = np.square(y - terminal["p_const_prior"].to_numpy())
    model_block_error = np.bincount(
        block, weights=model_error, minlength=block_count
    )
    const_block_error = np.bincount(
        block, weights=const_error, minlength=block_count
    )
    model_brier = counts @ model_block_error
    const_brier = counts @ const_block_error
    brier_skill = 1.0 - model_brier / const_brier

    def interval(values: np.ndarray, point: float) -> dict[str, float]:
        return {
            "point": float(point),
            "ci95_low": float(np.quantile(values, 0.025)),
            "ci95_high": float(np.quantile(values, 0.975)),
        }

    point = metric_values(
        terminal,
        spec,
        terminal["p_lgbm_final"].to_numpy(),
        terminal["p_const_prior"].to_numpy(),
    )
    auc_ma_diff = auc_samples["lgbm"] - auc_samples["ma_probe"]
    auc_g_diff = auc_samples["lgbm"] - auc_samples["g_only"]
    return {
        "samples": BOOTSTRAP_SAMPLES,
        "seed": SEED,
        "block_days": BOOTSTRAP_BLOCK_DAYS,
        "block_origin": origin,
        "block_count": block_count,
        "paired_draw_counts_sha256": draw_sha,
        "same_resampling_indices_for_all_models": True,
        "auc": interval(auc_samples["lgbm"], point["roc_auc"]),
        "auc_diff_vs_ma_probe": interval(
            auc_ma_diff,
            point["roc_auc"]
            - roc_auc_score(y, terminal["p_ma_probe_logit"]),
        ),
        "auc_diff_vs_g_only": interval(
            auc_g_diff,
            point["roc_auc"]
            - roc_auc_score(y, terminal["p_g_only_logit"]),
        ),
        "top_decile_uplift": interval(
            top_uplift, point["top_decile_uplift"]
        ),
        "brier_skill_vs_const": interval(
            brier_skill, point["brier_skill_vs_const"]
        ),
    }


def non_overlap_sample(
    frame: pd.DataFrame, *, spacing_days: int
) -> pd.DataFrame:
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


def terminal_strata(
    terminal: pd.DataFrame,
    spec: TargetSpec,
    *,
    model_id: str,
    feature_scheme: str,
    calibration: str,
) -> list[dict[str, Any]]:
    work = terminal.copy()
    work["year_segment"] = work["ts"].dt.year.astype(str)
    liquidity = work["liquidity_rank_pct_p0r"].astype(float)
    work["liquidity_quintile"] = (
        np.minimum(np.floor(liquidity.clip(0, 1) * 5), 4) + 1
    ).astype("Int64")
    age_rank = work["listing_age_days"].rank(method="first")
    work["listing_age_tercile"] = (
        pd.qcut(age_rank, 3, labels=["young", "middle", "old"]).astype(str)
    )
    rows: list[dict[str, Any]] = []
    for stratum_type, column in (
        ("side", "side"),
        ("year", "year_segment"),
        ("liquidity_quintile", "liquidity_quintile"),
        ("listing_age_tercile", "listing_age_tercile"),
        ("volatility_state_p0r", "volatility_state_p0r"),
    ):
        for value, group in work.groupby(column, dropna=False, sort=True):
            if group[spec.target].nunique() < 2:
                continue
            rows.append(
                metric_row(
                    group,
                    spec,
                    group["p_lgbm_final"].to_numpy(),
                    group["p_const_prior"].to_numpy(),
                    evaluation="terminal",
                    fold="2025+",
                    model_id=model_id,
                    feature_scheme=feature_scheme,
                    calibration=calibration,
                    row_type="stratum",
                    stratum_type=stratum_type,
                    stratum_value=str(value),
                )
            )
    return rows


def terminal_target(
    dev_result: dict[str, Any],
    feature_spec: dict[str, Any],
    metric_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    spec: TargetSpec = dev_result["target"]
    development = dev_result["development"]
    selected_features = development["selected_features"]
    candidate_id = development["selected_candidate"]
    scheme = development["selected_feature_scheme"]
    rounds = development["fixed_terminal_rounds"]
    calibration = development["calibration"]
    categorical = feature_spec["categorical_features"]

    print(f"P1 {spec.name}: pre-terminal lock exists; read 2025+ once...", flush=True)
    pre2025 = load_target_frame(spec, feature_spec, stage="development")
    train = pre2025.loc[pre2025[spec.label_end].lt(TERMINAL_START)].copy()
    terminal = load_target_frame(spec, feature_spec, stage="terminal")
    if train[spec.label_end].max() >= TERMINAL_START:
        raise RuntimeError(f"{spec.name} terminal training purge failure")
    if terminal["ts"].min() < TERMINAL_START:
        raise RuntimeError(f"{spec.name} terminal date boundary failure")

    print(f"P1 {spec.name}: fixed-round terminal refit and prediction...", flush=True)
    model, raw_probability, lgbm_preprocessor = fit_lgbm_fixed(
        train,
        terminal,
        spec,
        selected_features,
        categorical,
        candidate_id,
        rounds,
    )
    final_probability = apply_calibration(raw_probability, calibration)
    prior = float(train[spec.target].mean())
    scored = terminal[
        [
            "asset",
            "ts",
            "side",
            "listing_age_days",
            "liquidity_rank_pct_p0r",
            "volatility_state_p0r",
            "asset_group",
            spec.target,
            spec.net_return,
        ]
    ].copy()
    scored["target_name"] = spec.name
    scored["p_const_prior"] = prior
    scored["p_lgbm_raw"] = raw_probability
    scored["p_lgbm_final"] = final_probability
    scored["calibration_method"] = calibration["method"]

    baseline_features = {
        "MA_PROBE_LOGIT": ma_probe_features(feature_spec),
        "G_ONLY_LOGIT": build_feature_sets(feature_spec)["G"],
        "FULL_LOGIT": build_feature_sets(feature_spec)["FULL"],
    }
    terminal_preprocessing: list[dict[str, Any]] = [
        {
            "model_id": f"LGBM_{candidate_id}",
            "fit_scope": "pre-2025 rows with label_end < 2025-01-01 only",
            "train_n": int(len(train)),
            "train_max_label_end": train[spec.label_end].max(),
            "terminal_n": int(len(terminal)),
            **lgbm_preprocessor.audit(),
        }
    ]
    for model_id, features in baseline_features.items():
        probability, audit = fit_logit(
            train, terminal, spec, features, categorical
        )
        column = {
            "MA_PROBE_LOGIT": "p_ma_probe_logit",
            "G_ONLY_LOGIT": "p_g_only_logit",
            "FULL_LOGIT": "p_full_logit",
        }[model_id]
        scored[column] = probability
        terminal_preprocessing.append(
            {
                "model_id": model_id,
                "fit_scope": "pre-2025 rows with label_end < 2025-01-01 only",
                **audit,
            }
        )
        metric_rows.append(
            metric_row(
                terminal,
                spec,
                probability,
                np.full(len(terminal), prior),
                evaluation="terminal",
                fold="2025+",
                model_id=model_id,
                feature_scheme=(
                    "MA_PROBE"
                    if model_id == "MA_PROBE_LOGIT"
                    else "G"
                    if model_id == "G_ONLY_LOGIT"
                    else "FULL"
                ),
                calibration="raw",
                train=train,
            )
        )
    metric_rows.append(
        metric_row(
            terminal,
            spec,
            np.full(len(terminal), prior),
            np.full(len(terminal), prior),
            evaluation="terminal",
            fold="2025+",
            model_id="CONST_PRIOR",
            feature_scheme="NONE",
            calibration="raw",
            train=train,
        )
    )
    final_model_id = f"LGBM_{candidate_id}"
    overall = metric_row(
        scored,
        spec,
        scored["p_lgbm_final"].to_numpy(),
        scored["p_const_prior"].to_numpy(),
        evaluation="terminal",
        fold="2025+",
        model_id=final_model_id,
        feature_scheme=scheme,
        calibration=calibration["method"],
        train=train,
    )
    raw_overall = metric_row(
        scored,
        spec,
        scored["p_lgbm_raw"].to_numpy(),
        scored["p_const_prior"].to_numpy(),
        evaluation="terminal",
        fold="2025+",
        model_id=final_model_id,
        feature_scheme=scheme,
        calibration="raw",
        train=train,
        row_type="raw_metric",
    )
    metric_rows.append(raw_overall)
    overall["paired_auc_diff_vs_ma_probe"] = (
        overall["roc_auc"]
        - roc_auc_score(scored[spec.target], scored["p_ma_probe_logit"])
    )
    overall["paired_auc_diff_vs_g_only"] = (
        overall["roc_auc"]
        - roc_auc_score(scored[spec.target], scored["p_g_only_logit"])
    )
    metric_rows.append(overall)
    terminal_deciles = decile_rows(
        scored,
        spec,
        scored["p_lgbm_final"].to_numpy(),
        evaluation="terminal",
        fold="2025+",
        model_id=final_model_id,
        feature_scheme=scheme,
        calibration=calibration["method"],
    )
    metric_rows.extend(terminal_deciles)
    strata = terminal_strata(
        scored,
        spec,
        model_id=final_model_id,
        feature_scheme=scheme,
        calibration=calibration["method"],
    )
    metric_rows.extend(strata)

    bootstrap = paired_block_bootstrap(scored, spec)
    for metric_name in (
        "auc",
        "auc_diff_vs_ma_probe",
        "auc_diff_vs_g_only",
        "top_decile_uplift",
        "brier_skill_vs_const",
    ):
        metric_rows.append(
            {
                "target_name": spec.name,
                "row_type": "bootstrap_ci",
                "evaluation": "terminal",
                "fold": "2025+",
                "model_id": final_model_id,
                "feature_scheme": scheme,
                "calibration": calibration["method"],
                "stratum_type": "metric",
                "stratum_value": metric_name,
                "point_estimate": bootstrap[metric_name]["point"],
                "ci95_low": bootstrap[metric_name]["ci95_low"],
                "ci95_high": bootstrap[metric_name]["ci95_high"],
                "bootstrap_samples": BOOTSTRAP_SAMPLES,
                "bootstrap_block_days": BOOTSTRAP_BLOCK_DAYS,
                "bootstrap_draw_sha256": bootstrap[
                    "paired_draw_counts_sha256"
                ],
            }
        )

    non_overlap = non_overlap_sample(
        scored, spacing_days=spec.non_overlap_days
    )
    non_overlap_values = metric_values(
        non_overlap,
        spec,
        non_overlap["p_lgbm_final"].to_numpy(),
        non_overlap["p_const_prior"].to_numpy(),
    )
    metric_rows.append(
        {
            "target_name": spec.name,
            "row_type": "non_overlap",
            "evaluation": "terminal",
            "fold": "2025+",
            "model_id": final_model_id,
            "feature_scheme": scheme,
            "calibration": calibration["method"],
            "stratum_type": "spacing_days",
            "stratum_value": str(spec.non_overlap_days),
            **non_overlap_values,
        }
    )

    by_side = {
        str(row["stratum_value"]): row
        for row in strata
        if row["stratum_type"] == "side"
    }
    by_year = {
        str(row["stratum_value"]): row
        for row in strata
        if row["stratum_type"] == "year"
    }
    leave_group = development["leave_asset_group_out"]
    no_cross_auc = development["feature_selection"][
        "FULL_NO_CROSS_MARKET"
    ]["macro_auc"]
    selected_auc = development["feature_selection"][scheme]["macro_auc"]
    cross_market_auc_advantage = selected_auc - no_cross_auc
    permutation_values = [
        item["auc_drop"]
        for item in development["cross_market_permutation"]
        if item["auc_drop"] is not None
    ]
    cross_market_increment = bool(
        cross_market_auc_advantage >= 0.002
        or (
            len(permutation_values) == 3
            and all(value > 0 for value in permutation_values)
        )
    )
    learnable_checks = {
        "terminal_auc_ci_low_gt_050": bootstrap["auc"]["ci95_low"] > 0.50,
        "terminal_top_decile_uplift_ci_low_gt_0": bootstrap[
            "top_decile_uplift"
        ]["ci95_low"]
        > 0.0,
        "terminal_brier_skill_gt_0": overall["brier_skill_vs_const"] > 0.0,
        "non_overlap_auc_gt_050": non_overlap_values["roc_auc"] > 0.50,
        "leave_group_median_auc_gt_052": leave_group["median_auc"] > 0.52,
        "leave_group_min_auc_ge_049": leave_group["minimum_auc"] >= 0.49,
        "long_terminal_auc_ge_050": by_side["long"]["roc_auc"] >= 0.50,
        "short_terminal_auc_ge_050": by_side["short"]["roc_auc"] >= 0.50,
        "year_2025_auc_ge_049": by_year["2025"]["roc_auc"] >= 0.49,
        "year_2026_auc_ge_049": by_year["2026"]["roc_auc"] >= 0.49,
    }
    learnable_pass = all(learnable_checks.values())
    incremental_checks = {
        "auc_diff_vs_g_ci_low_gt_0": bootstrap["auc_diff_vs_g_only"][
            "ci95_low"
        ]
        > 0.0,
        "auc_diff_vs_ma_probe_ci_low_gt_0": bootstrap[
            "auc_diff_vs_ma_probe"
        ]["ci95_low"]
        > 0.0,
        "cross_market_increment_on_development": cross_market_increment,
    }
    incremental_pass = learnable_pass and all(incremental_checks.values())
    if incremental_pass:
        verdict = "INCREMENTAL_CROSS_ASSET_SIGNAL"
    elif learnable_pass:
        verdict = "LEARNABLE_BUT_NOT_INCREMENTAL_BEYOND_MA"
    elif overall["roc_auc"] > 0.50 and overall["top_decile_uplift"] > 0.0:
        verdict = "UNSTABLE_DONOR_SIGNAL"
    else:
        verdict = "NO_LEARNABLE_DONOR_SIGNAL"

    terminal_importance = dict(
        zip(
            selected_features,
            model.booster_.feature_importance(importance_type="gain").astype(float),
            strict=True,
        )
    )
    result = {
        "sample": {
            "training_n": int(len(train)),
            "training_assets": int(train["asset"].nunique()),
            "training_max_ts": train["ts"].max(),
            "training_max_label_end": train[spec.label_end].max(),
            "terminal_n": int(len(scored)),
            "terminal_assets": int(scored["asset"].nunique()),
            "terminal_min_ts": scored["ts"].min(),
            "terminal_max_ts": scored["ts"].max(),
            "terminal_positive_rate": float(scored[spec.target].mean()),
        },
        "raw_overall": raw_overall,
        "overall": overall,
        "deciles": terminal_deciles,
        "bootstrap": bootstrap,
        "non_overlap": {
            "spacing_days": spec.non_overlap_days,
            **non_overlap_values,
        },
        "strata": strata,
        "by_side": by_side,
        "by_year": by_year,
        "terminal_preprocessing_audit": terminal_preprocessing,
        "terminal_model_feature_importance": aggregate_feature_importance(
            [terminal_importance], feature_spec
        ),
        "cross_market_increment": {
            "selected_scheme_macro_auc": selected_auc,
            "full_no_cross_market_macro_auc": no_cross_auc,
            "auc_advantage": cross_market_auc_advantage,
            "development_permutation_auc_drops": permutation_values,
            "pass": cross_market_increment,
        },
        "learnable_checks": learnable_checks,
        "learnable_pass": learnable_pass,
        "incremental_checks": incremental_checks,
        "incremental_pass": incremental_pass,
        "verdict": verdict,
        "status": STATUS,
        "hype_rows": int(scored["asset"].eq(HYPE_ASSET).sum()),
        "hyper_rows": int(scored["asset"].eq(HYPER_ASSET).sum()),
    }
    del pre2025, train, terminal, model, lgbm_preprocessor
    gc.collect()
    return {"predictions": scored, "terminal": result}


def report_metric_table(rows: Sequence[dict[str, Any]]) -> list[str]:
    lines = [
        "| Fold | n / 资产 | UTC 范围 | 正例率 | ROC-AUC | PR-AUC | Log loss | Brier skill | Top uplift |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['fold']} | {int(row['eval_n']):,} / {int(row['asset_count'])} | "
            f"{pd.Timestamp(row['date_min']).date()}–{pd.Timestamp(row['date_max']).date()} | "
            f"{row['positive_rate']:.2%} | {row['roc_auc']:.4f} | "
            f"{row['pr_auc']:.4f} | {row['log_loss']:.4f} | "
            f"{row['brier_skill_vs_const']:.2%} | "
            f"{row['top_decile_uplift']:.2%} |"
        )
    return lines


def report_strata_table(
    strata: Sequence[dict[str, Any]], stratum_type: str
) -> list[str]:
    rows = [row for row in strata if row["stratum_type"] == stratum_type]
    lines = [
        "| 分层 | n | 正例率 | ROC-AUC | Brier | Top uplift |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['stratum_value']} | {int(row['eval_n']):,} | "
            f"{row['positive_rate']:.2%} | {row['roc_auc']:.4f} | "
            f"{row['brier']:.4f} | {row['top_decile_uplift']:.2%} |"
        )
    return lines


def report_decile_table(deciles: Sequence[dict[str, Any]]) -> list[str]:
    lines = [
        "| 十分位 | n | 成功率 | 相对总体 uplift | 净收益均值 | 净收益中位数 |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in deciles:
        lines.append(
            f"| {int(row['decile'])} | {int(row['eval_n']):,} | "
            f"{row['positive_rate']:.2%} | {row['decile_uplift']:.2%} | "
            f"{row['net_return_mean']:.2%} | {row['net_return_median']:.2%} |"
        )
    return lines


def write_target_report(
    spec: TargetSpec, development: dict[str, Any], terminal: dict[str, Any]
) -> None:
    path = ENTRY_REPORT_PATH if spec.name == "entry" else CONTINUATION_REPORT_PATH
    bootstrap = terminal["bootstrap"]
    side = terminal["by_side"]
    year = terminal["by_year"]
    groups = development["leave_asset_group_out"]
    blocks = development["feature_importance"]["feature_blocks"][:4]
    lines = [
        f"# BIN-1D-CATL-P1 {spec.name.title()} donor-only 模型",
        "",
        "## 裁决",
        "",
        f"`{terminal['verdict']} / {STATUS}`",
        "",
        f"问题：{spec.question}。本轮只评价 donor 概率排序，不构造交易规则。",
        "",
        "## D1-D3 开发期 walk-forward",
        "",
        f"- LightGBM 参数：`{development['selected_candidate']}`；特征方案：`{development['selected_feature_scheme']}`（{development['selected_feature_count']} 个字段）。",
        f"- terminal 固定轮数：开发三折最佳轮数中位数 `{development['fixed_terminal_rounds']}`。",
        f"- 概率校准：`{development['calibration']['method']}`；校准器只拟合 D1-D3 OOF，terminal 标签使用量为 `0`。",
        "",
        *report_metric_table(development["folds"]),
        "",
        f"三折 raw/calibrated macro ROC-AUC `{development['raw_macro']['roc_auc']:.4f}` / `{development['macro']['roc_auc']:.4f}`，"
        f"log loss `{development['raw_macro']['log_loss']:.4f}` / `{development['macro']['log_loss']:.4f}`，"
        f"Brier `{development['raw_macro']['brier']:.4f}` / `{development['macro']['brier']:.4f}`。"
        f"校准后 Brier skill `{development['macro']['brier_skill_vs_const']:.2%}`。",
        "",
        "## 2025+ donor terminal OOS",
        "",
        f"- n=`{terminal['sample']['terminal_n']:,}`，资产 `{terminal['sample']['terminal_assets']}`，正例率 `{terminal['sample']['terminal_positive_rate']:.2%}`。",
        f"- ROC-AUC `{terminal['overall']['roc_auc']:.4f}`，28d block-bootstrap 95% CI `[{bootstrap['auc']['ci95_low']:.4f}, {bootstrap['auc']['ci95_high']:.4f}]`。",
        f"- PR-AUC `{terminal['overall']['pr_auc']:.4f}`（正例率基线 `{terminal['overall']['pr_baseline']:.4f}`），log loss `{terminal['overall']['log_loss']:.4f}`，Brier `{terminal['overall']['brier']:.4f}`，Brier skill `{terminal['overall']['brier_skill_vs_const']:.2%}`。",
        f"- Top-decile uplift `{terminal['overall']['top_decile_uplift']:.2%}`，95% CI `[{bootstrap['top_decile_uplift']['ci95_low']:.2%}, {bootstrap['top_decile_uplift']['ci95_high']:.2%}]`；top-bottom 差 `{terminal['overall']['top_bottom_success_rate_diff']:.2%}`。",
        f"- 校准 intercept/slope `{terminal['overall']['calibration_intercept']:.3f}/{terminal['overall']['calibration_slope']:.3f}`，ECE10 `{terminal['overall']['ece_10']:.3%}`。",
        f"- raw/calibrated terminal log loss `{terminal['raw_overall']['log_loss']:.4f}` / `{terminal['overall']['log_loss']:.4f}`，Brier `{terminal['raw_overall']['brier']:.4f}` / `{terminal['overall']['brier']:.4f}`。",
        f"- 每资产倒数加权 AUC/Brier `{terminal['overall']['asset_balanced_auc']:.4f}` / `{terminal['overall']['asset_balanced_brier']:.4f}`。",
        "",
        "### Terminal 概率十分位与经济排序诊断",
        "",
        *report_decile_table(terminal["deciles"]),
        "",
        "净收益只用于同一标签定义下的排序诊断；这些重叠 landmark 不得累加或年化。",
        "",
        "## 相对 MA baseline 的增量",
        "",
        f"- 相对 `MA_PROBE_LOGIT` AUC 差 `{terminal['overall']['paired_auc_diff_vs_ma_probe']:.4f}`，95% CI `[{bootstrap['auc_diff_vs_ma_probe']['ci95_low']:.4f}, {bootstrap['auc_diff_vs_ma_probe']['ci95_high']:.4f}]`。",
        f"- 相对 `G_ONLY_LOGIT` AUC 差 `{terminal['overall']['paired_auc_diff_vs_g_only']:.4f}`，95% CI `[{bootstrap['auc_diff_vs_g_only']['ci95_low']:.4f}, {bootstrap['auc_diff_vs_g_only']['ci95_high']:.4f}]`。",
        f"- cross-market 开发期增量门：`{terminal['cross_market_increment']['pass']}`；锁定方案相对 `FULL_NO_CROSS_MARKET` macro AUC 差 `{terminal['cross_market_increment']['auc_advantage']:.4f}`。",
        "",
        "## 稳定性",
        "",
        f"- long/short terminal AUC：`{side['long']['roc_auc']:.4f}` / `{side['short']['roc_auc']:.4f}`。",
        f"- 2025/2026 AUC：`{year['2025']['roc_auc']:.4f}` / `{year['2026']['roc_auc']:.4f}`。",
        f"- non-overlap（间隔 {spec.non_overlap_days} 日）AUC：`{terminal['non_overlap']['roc_auc']:.4f}`，n=`{terminal['non_overlap']['eval_n']:,}`。",
        f"- leave-asset-group-out 五组 AUC 中位数/最小值：`{groups['median_auc']:.4f}` / `{groups['minimum_auc']:.4f}`。",
        "",
        "### 流动性五分位",
        "",
        *report_strata_table(terminal["strata"], "liquidity_quintile"),
        "",
        "### 上市年龄三分位",
        "",
        *report_strata_table(terminal["strata"], "listing_age_tercile"),
        "",
        "### 因果波动状态",
        "",
        *report_strata_table(terminal["strata"], "volatility_state_p0r"),
        "",
        "## 模型依赖的 feature blocks",
        "",
    ]
    for item in blocks:
        lines.append(
            f"- `{item['feature_block']}`：开发折平均 gain share `{item['gain_share']:.2%}`。"
        )
    lines.extend(
        [
            "",
            "这些重要性只表示模型的预测依赖，不是因果证据。",
            "",
            "## HYPE 隔离与研究边界",
            "",
            "- 输入、OOF、terminal 输出中的 `HYPE/USDT:USDT` 均为 `0` 行；`HYPER/USDT:USDT` 保留。",
            "- HYPE K 线、funding、标签、表现、路径和预测均未读取或生成。",
            "- 事件标签高度重叠，经济字段只是排序诊断；没有仓位、组合约束、成交状态机或账户回测，因此不是交易策略，也不支持 promotion/live-ready。",
            "",
            "## 证据",
            "",
            "- [P1 summary](../artifacts/binance_1d_catl_p1_summary.json)",
            "- [逐折与分层指标](../artifacts/binance_1d_catl_p1_fold_metrics.parquet)",
            "- [开发 OOF 预测](../artifacts/binance_1d_catl_p1_oof_predictions.parquet)",
            "- [terminal 预测](../artifacts/binance_1d_catl_p1_terminal_predictions.parquet)",
            "- [模型卡](../artifacts/binance_1d_catl_p1_model_card.json)",
        ]
    )
    atomic_write_text(path, "\n".join(lines) + "\n")


def write_audit_report(
    input_audit: dict[str, Any],
    developments: dict[str, Any],
    terminals: dict[str, Any],
    preterminal_sha: str,
) -> None:
    lines = [
        "# BIN-1D-CATL-P1 建模审计",
        "",
        "## 审计结论",
        "",
        f"`PASS / {STATUS}`",
        "",
        "P1 严格使用 P0R donor-only panel。所有模型/特征/轮数/校准选择在读取 2025+ donor terminal 标签前锁定；HYPE 全资产仍封存。",
        "",
        "## 输入完整性",
        "",
        f"- P1 contract SHA256：`{input_audit['contract_sha256']}`。",
        f"- P0R manifest SHA256：`{input_audit['p0r_manifest_sha256']}`。",
        f"- P0R feature spec SHA256：`{input_audit['p0r_feature_spec_sha256']}`。",
        f"- P0R manifest 的 `{len(input_audit['p0r_artifact_hash_checks'])}` 个 artifact 哈希全部匹配，panel 文件集合无额外分区。",
        f"- donor panel：`{input_audit['panel_rows']:,}` 行、`{input_audit['panel_assets']}` 资产；HYPE `{input_audit['panel_hype_rows']}` 行；HYPER `{input_audit['panel_hyper_rows']:,}` 行。",
        "",
        "## 时间与 terminal lock",
        "",
        f"- Pre-terminal lock SHA256：`{preterminal_sha}`。",
        "- D1/D2/D3 validation 固定为 2022/2023/2024；每折训练都执行目标专属 `label_end_ts < validation_start_ts` 精确 purge。",
        "- Entry 与 continuation 均在 joint pre-terminal lock 落盘后才调用 terminal loader。",
        "- terminal 重训只用 `label_end_ts < 2025-01-01`；2025+ 不参与模型、特征、参数、轮数或校准选择。",
        "",
        "## 预处理与特征边界",
        "",
        "- X 严格由 P0R `all_allowed_features` 派生；资产、方向、时间、价格、资格、标签、future、result、收益、MFE/MAE 均不进入 X。",
        "- LightGBM 类别字典逐折只在训练集拟合；数值缺失走 LightGBM 原生 missing。",
        "- Logistic baseline 的中位数、缺失指示、均值/标准差和 one-hot 字典逐折只在训练集拟合，未知类别为全零 one-hot。",
        "- 同一 asset-day 的 long/short 由 UTC 日期边界共同切分；OOF 主键唯一。",
        "",
        "## Bootstrap 与稳定性",
        "",
    ]
    for name in ("entry", "continuation"):
        bootstrap = terminals[name]["bootstrap"]
        group = developments[name]["leave_asset_group_out"]
        lines.extend(
            [
                f"- `{name}`：28d paired bootstrap `{bootstrap['samples']}` 次，共享 draw SHA `{bootstrap['paired_draw_counts_sha256']}`；leave-group AUC median/min `{group['median_auc']:.4f}/{group['minimum_auc']:.4f}`。",
            ]
        )
    lines.extend(
        [
            "",
            "## HYPE fail-closed 证明",
            "",
            "- 精确禁止对象为 `HYPE/USDT:USDT`；输入检查、开发 loader、terminal loader、OOF、terminal predictions、summary/model card 均断言 0 行。",
            "- `HYPER/USDT:USDT` 使用精确字符串区分并保留。",
            "- 本轮没有 HYPE reveal，也没有 HYPE prediction artifact。",
            "",
            "## 非策略证明",
            "",
            "- 输出没有仓位、杠杆、组合回测、交易阈值、订单、权益曲线、runner、live spec、dry-run 或 live-ready artifact。",
            "- 标签净收益只在概率十分位内报告均值/中位数，未累加或年化。",
            "",
            "## 精确复现",
            "",
            "```bash",
            "cd /Users/ZK/OpenCode/quant-strategy-lab",
            "uv run --extra ml python research/asset-portfolios/1d-cross-asset-trend-lifecycle/scripts/run_binance_1d_catl_p1_donor_walk_forward_modeling.py --run --force",
            "uv run --extra ml pytest -q tests/test_binance_1d_catl_p1_donor_walk_forward_modeling.py tests/test_binance_1d_catl_p0_dataset_label_atlas.py tests/test_binance_1d_catl_p0r_modeling_input_repair.py",
            "```",
        ]
    )
    atomic_write_text(AUDIT_REPORT_PATH, "\n".join(lines) + "\n")


def build_manifest(paths: Iterable[Path], input_audit: dict[str, Any]) -> None:
    artifacts = []
    for path in paths:
        artifacts.append(
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    payload = {
        "family": "Binance-1D-Cross-Asset-Trend-Lifecycle",
        "experiment": "P1 Donor-Only Walk-Forward Entry/Continuation Modeling",
        "generated_at_utc": datetime.now(UTC),
        "status": STATUS,
        "holdout_read": False,
        "hype_asset_excluded": HYPE_ASSET,
        "hype_reveal_executed": False,
        "input_lineage": {
            "p0r_manifest_path": str(P0R_MANIFEST_PATH.relative_to(ROOT)),
            "p0r_manifest_sha256": input_audit["p0r_manifest_sha256"],
            "p0r_feature_spec_sha256": input_audit["p0r_feature_spec_sha256"],
            "contract_sha256": input_audit["contract_sha256"],
        },
        "artifacts": artifacts,
    }
    atomic_write_json(MANIFEST_PATH, payload)


def main() -> None:
    args = parse_args()
    if not args.run:
        raise SystemExit("pass --run after reviewing the frozen P1 contract")
    ensure_output_policy(args.force)
    feature_spec, input_audit = validate_inputs()
    metric_rows: list[dict[str, Any]] = []

    developments: dict[str, Any] = {}
    dev_results: dict[str, Any] = {}
    oof_frames: list[pd.DataFrame] = []
    for spec in TARGETS:
        result = development_target(spec, feature_spec, metric_rows)
        dev_results[spec.name] = result
        developments[spec.name] = result["development"]
        oof_frames.append(result["oof"])
    oof = pd.concat(oof_frames, ignore_index=True)
    if oof["asset"].eq(HYPE_ASSET).any():
        raise RuntimeError("HOLDOUT_CONTAMINATED: HYPE in OOF")
    if oof.duplicated(["target_name", "asset", "ts", "side"]).any():
        raise RuntimeError("OOF prediction identity is not unique")
    atomic_write_parquet(OOF_PREDICTIONS_PATH, oof)

    preterminal_lock = {
        "family": "Binance-1D-Cross-Asset-Trend-Lifecycle",
        "experiment": "P1 Donor-Only Walk-Forward Entry/Continuation Modeling",
        "locked_at_utc": datetime.now(UTC),
        "contract_sha256": input_audit["contract_sha256"],
        "feature_spec_sha256": input_audit["p0r_feature_spec_sha256"],
        "oof_predictions_sha256": sha256_file(OOF_PREDICTIONS_PATH),
        "selection_data_end_exclusive": TERMINAL_START,
        "terminal_rows_used_for_selection": 0,
        "hype_rows_used": 0,
        "hype_reveal_authorized": False,
        "evaluation_rules": {
            "terminal_start": TERMINAL_START,
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "bootstrap_block_days": BOOTSTRAP_BLOCK_DAYS,
            "non_overlap_entry_days": 20,
            "non_overlap_continuation_days": 5,
            "decision_gate": "contract section 11",
        },
        "targets": {
            name: {
                "selected_candidate": development["selected_candidate"],
                "selected_feature_scheme": development[
                    "selected_feature_scheme"
                ],
                "selected_features": development["selected_features"],
                "fixed_terminal_rounds": development["fixed_terminal_rounds"],
                "calibration": development["calibration"],
                "leave_asset_group_out": development[
                    "leave_asset_group_out"
                ],
            }
            for name, development in developments.items()
        },
        "status": "LOCKED_BEFORE_DONOR_TERMINAL_READ",
    }
    atomic_write_json(PRETERMINAL_LOCK_PATH, preterminal_lock)
    preterminal_sha = sha256_file(PRETERMINAL_LOCK_PATH)

    terminals: dict[str, Any] = {}
    terminal_frames: list[pd.DataFrame] = []
    for spec in TARGETS:
        result = terminal_target(
            dev_results[spec.name], feature_spec, metric_rows
        )
        terminals[spec.name] = result["terminal"]
        terminal_frames.append(result["predictions"])
    terminal_predictions = pd.concat(terminal_frames, ignore_index=True)
    if terminal_predictions["asset"].eq(HYPE_ASSET).any():
        raise RuntimeError("HOLDOUT_CONTAMINATED: HYPE in terminal predictions")
    if terminal_predictions.duplicated(
        ["target_name", "asset", "ts", "side"]
    ).any():
        raise RuntimeError("Terminal prediction identity is not unique")
    atomic_write_parquet(TERMINAL_PREDICTIONS_PATH, terminal_predictions)

    fold_metrics = pd.DataFrame(metric_rows)
    atomic_write_parquet(FOLD_METRICS_PATH, fold_metrics)
    summary = {
        "family": "Binance-1D-Cross-Asset-Trend-Lifecycle",
        "alias": "BIN-1D-CATL",
        "experiment": "P1 Donor-Only Walk-Forward Entry/Continuation Modeling",
        "evidence_revision": {
            "id": "P1R1",
            "reason": (
                "Complete raw/calibrated, decile and terminal stratum reporting; "
                "the frozen contract, model selection, parameters, calibration "
                "rule and decision gates are unchanged."
            ),
        },
        "generated_at_utc": datetime.now(UTC),
        "status": STATUS,
        "contract_sha256": input_audit["contract_sha256"],
        "preterminal_lock_sha256": preterminal_sha,
        "input_integrity": input_audit,
        "targets": {
            spec.name: {
                "question": spec.question,
                "development": developments[spec.name],
                "terminal": terminals[spec.name],
            }
            for spec in TARGETS
        },
        "hype_isolation": {
            "forbidden_asset": HYPE_ASSET,
            "input_rows": input_audit["panel_hype_rows"],
            "oof_rows": int(oof["asset"].eq(HYPE_ASSET).sum()),
            "terminal_prediction_rows": int(
                terminal_predictions["asset"].eq(HYPE_ASSET).sum()
            ),
            "model_card_rows": 0,
            "hype_reveal_executed": False,
            "holdout_read": False,
        },
        "hyper_preservation": {
            "asset": HYPER_ASSET,
            "input_rows": input_audit["panel_hyper_rows"],
            "oof_rows": int(oof["asset"].eq(HYPER_ASSET).sum()),
            "terminal_prediction_rows": int(
                terminal_predictions["asset"].eq(HYPER_ASSET).sum()
            ),
        },
        "no_strategy_no_portfolio_no_live_artifact": True,
        "reproduction_command": (
            "uv run --extra ml python "
            "research/asset-portfolios/1d-cross-asset-trend-lifecycle/scripts/"
            "run_binance_1d_catl_p1_donor_walk_forward_modeling.py --run --force"
        ),
        "test_command": (
            "uv run --extra ml pytest -q "
            "tests/test_binance_1d_catl_p1_donor_walk_forward_modeling.py "
            "tests/test_binance_1d_catl_p0_dataset_label_atlas.py "
            "tests/test_binance_1d_catl_p0r_modeling_input_repair.py"
        ),
    }
    atomic_write_json(SUMMARY_PATH, summary)

    model_card = {
        "family": summary["family"],
        "experiment": summary["experiment"],
        "model_role": "donor-only probability-ranking diagnostic",
        "donor_only": True,
        "hype_asset": HYPE_ASSET,
        "hype_rows": 0,
        "hype_reveal_executed": False,
        "training_cutoff_rule": "label_end_ts < 2025-01-01T00:00:00Z",
        "not_live_ready": True,
        "status": STATUS,
        "seed": SEED,
        "contract_sha256": input_audit["contract_sha256"],
        "feature_spec_sha256": input_audit["p0r_feature_spec_sha256"],
        "preterminal_lock_sha256": preterminal_sha,
        "software": {
            "python": ".".join(map(str, os.sys.version_info[:3])),
            "lightgbm": lgb.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "targets": {
            spec.name: {
                "target": spec.target,
                "eligibility": spec.eligibility,
                "label_end": spec.label_end,
                "selected_candidate": developments[spec.name][
                    "selected_candidate"
                ],
                "lgbm_params": lgbm_params(
                    developments[spec.name]["selected_candidate"],
                    rounds=developments[spec.name]["fixed_terminal_rounds"],
                ),
                "feature_scheme": developments[spec.name][
                    "selected_feature_scheme"
                ],
                "features": developments[spec.name]["selected_features"],
                "feature_count": developments[spec.name][
                    "selected_feature_count"
                ],
                "calibration": developments[spec.name]["calibration"],
                "verdict": terminals[spec.name]["verdict"],
                "feature_importance": developments[spec.name][
                    "feature_importance"
                ],
            }
            for spec in TARGETS
        },
        "prohibited_uses": [
            "HYPE inference before an independently authorized P2 reveal",
            "position sizing",
            "portfolio backtest",
            "runner handoff",
            "dry-run or live trading",
        ],
    }
    atomic_write_json(MODEL_CARD_PATH, model_card)

    for spec in TARGETS:
        write_target_report(
            spec, developments[spec.name], terminals[spec.name]
        )
    write_audit_report(
        input_audit, developments, terminals, preterminal_sha
    )
    manifest_paths = (
        SPEC_PATH,
        CONTRACT_LOCK_PATH,
        PRETERMINAL_LOCK_PATH,
        Path(__file__),
        TEST_PATH,
        ENTRY_REPORT_PATH,
        CONTINUATION_REPORT_PATH,
        AUDIT_REPORT_PATH,
        SUMMARY_PATH,
        FOLD_METRICS_PATH,
        TERMINAL_PREDICTIONS_PATH,
        OOF_PREDICTIONS_PATH,
        MODEL_CARD_PATH,
    )
    build_manifest(manifest_paths, input_audit)
    print(
        json.dumps(
            {
                "entry_verdict": terminals["entry"]["verdict"],
                "continuation_verdict": terminals["continuation"]["verdict"],
                "summary": str(SUMMARY_PATH.relative_to(ROOT)),
                "manifest": str(MANIFEST_PATH.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
