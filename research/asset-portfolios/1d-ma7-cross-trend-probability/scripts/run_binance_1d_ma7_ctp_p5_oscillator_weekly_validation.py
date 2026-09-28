#!/usr/bin/env python3
"""Run BIN-1D-MA7-CTP P5 oscillator/weekly validation audit."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
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

SPEC_PATH = FAMILY_DIR / "specs/binance-1d-ma7-ctp-p5-oscillator-weekly-validation-contract-2026-09-02.md"
SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py"
TEST_PATH = ROOT / "tests/test_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py"
P4_SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py"
P4_FACTOR_GROUP_SPEC_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p4_factor_group_spec.json"
P4_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p4_summary.json"
P4_MODEL_CARD_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p4_model_card.json"
P0R_FEATURE_BLOCKS_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_feature_blocks.json"
P0R_MANIFEST_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_manifest.json"
P0_MANIFEST_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0_manifest.json"
PANEL_DIR = CATL_DIR / "artifacts/p0r_donor_directional_modeling_panel"
PANEL_GLOB = PANEL_DIR / "**/*.parquet"
P0_ASSET_DAY_DIR = CATL_DIR / "artifacts/p0_asset_day_feature_panel"

PREFIX = "binance_1d_ma7_ctp_p5_"
FEATURE_SPEC_PATH = ARTIFACT_DIR / f"{PREFIX}feature_spec.json"
CONTRACT_LOCK_PATH = ARTIFACT_DIR / f"{PREFIX}contract_lock.json"
DATA_AUDIT_PATH = ARTIFACT_DIR / f"{PREFIX}data_audit.json"
FOLD_METRICS_PATH = ARTIFACT_DIR / f"{PREFIX}fold_metrics.parquet"
OOF_PREDICTIONS_PATH = ARTIFACT_DIR / f"{PREFIX}pre2025_oof_predictions.parquet"
VALIDATION_PREDICTIONS_PATH = ARTIFACT_DIR / f"{PREFIX}validation_2025_plus_predictions.parquet"
PAIRED_COMPARISONS_PATH = ARTIFACT_DIR / f"{PREFIX}paired_comparisons.parquet"
STRATA_PATH = ARTIFACT_DIR / f"{PREFIX}strata.parquet"
CALIBRATION_PATH = ARTIFACT_DIR / f"{PREFIX}calibration.json"
MODEL_CARD_PATH = ARTIFACT_DIR / f"{PREFIX}model_card.json"
SUMMARY_PATH = ARTIFACT_DIR / f"{PREFIX}summary.json"
MANIFEST_PATH = ARTIFACT_DIR / f"{PREFIX}manifest.json"
REPORT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p5-oscillator-weekly-validation-2026-09-02.md"
MODELING_AUDIT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p5-modeling-audit-2026-09-02.md"
WEEKLY_AUDIT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p5-weekly-causality-audit-2026-09-02.md"
INDEPENDENT_ACCEPTANCE_AUDIT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p5-independent-acceptance-audit-2026-09-02.md"

HYPE_ASSET = "HYPE/USDT:USDT"
HYPER_ASSET = "HYPER/USDT:USDT"
SEED = 20260901
CUTOFF = pd.Timestamp("2025-01-01T00:00:00Z")
P0_CUTOFF = pd.Timestamp("2026-05-31T00:00:00Z")
TARGET = "label_entry_success_20d"
LABEL_END = "label_end_ts_20d"
NET_RETURN = "label_entry_net_return"
STATUS = "explore / diagnostic-only / not promoted / not live-ready"
LOCK_STATUS = "FROZEN_BEFORE_P5_LABEL_AND_2025_VALIDATION_READ"
HEAD = "POOLED_DIRECTION_ALIGNED_LOGIT"
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_BLOCK_DAYS = 28

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

KNOWN_TRADFI_BASE_SYMBOLS = {
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

G7_RSI6 = [
    "dir_rsi6_centered",
    "dir_rsi6_delta_1d",
    "dir_rsi6_delta_3d",
    "dir_rsi6_recovery_from_5d_adverse_extreme",
    "dir_rsi6_cross_50",
    "t1_dir_rsi6_centered",
    "t1_dir_rsi6_delta_1d",
    "t1_dir_rsi6_delta_3d",
    "t1_dir_rsi6_recovery_from_5d_adverse_extreme",
    "t1_dir_rsi6_cross_50",
]

G8_WEEKLY = [
    "dir_w_ret_1w",
    "dir_w_ret_4w",
    "dir_w_ret_12w",
    "dir_w_close_sma4_dist_watr6",
    "dir_w_close_sma13_dist_watr6",
    "dir_w_sma4_slope_1w_watr6",
    "dir_w_sma13_slope_1w_watr6",
    "dir_w_ma4_ma13_alignment",
    "w_atr6_pct",
    "w_path_efficiency_12w",
    "weekly_history_13w_complete",
]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


P4 = load_module(P4_SCRIPT_PATH, "binance_1d_ma7_ctp_p4")
P2 = P4.P2


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(json.dumps(json_ready(payload), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        if not np.isfinite(value):
            return None
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(json_ready(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def atomic_write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(tmp, index=False)
    tmp.replace(path)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def base_symbol(asset: str) -> str:
    return asset.split("/")[0].upper()


def candidate_definitions() -> dict[str, list[str]]:
    p4_spec = load_json(P4_FACTOR_GROUP_SPEC_PATH)
    b0 = list(p4_spec["p2_original_field_order"])
    g3 = set(p4_spec["factor_groups"]["G3_VOLATILITY_STATE"]["fields"])
    no_g3 = [feature for feature in b0 if feature not in g3]
    return {
        "R_B0_69": b0,
        "C_NO_G3_58": no_g3,
        "C_B0_PLUS_RSI_79": b0 + G7_RSI6,
        "C_B0_PLUS_WEEKLY_80": b0 + G8_WEEKLY,
        "C_B0_PLUS_RSI_WEEKLY_90": b0 + G7_RSI6 + G8_WEEKLY,
        "C_NO_G3_PLUS_RSI_WEEKLY_79": no_g3 + G7_RSI6 + G8_WEEKLY,
    }


def build_feature_spec() -> dict[str, Any]:
    p4_spec = load_json(P4_FACTOR_GROUP_SPEC_PATH)
    b0 = list(p4_spec["p2_original_field_order"])
    g3 = list(p4_spec["factor_groups"]["G3_VOLATILITY_STATE"]["fields"])
    candidates = candidate_definitions()
    expected_counts = {
        "R_B0_69": 69,
        "C_NO_G3_58": 58,
        "C_B0_PLUS_RSI_79": 79,
        "C_B0_PLUS_WEEKLY_80": 80,
        "C_B0_PLUS_RSI_WEEKLY_90": 90,
        "C_NO_G3_PLUS_RSI_WEEKLY_79": 79,
    }
    checks: dict[str, Any] = {}
    all_features: list[str] = []
    for candidate, fields in candidates.items():
        duplicates = sorted({f for f in fields if fields.count(f) > 1})
        checks[candidate] = {
            "count": len(fields),
            "expected_count": expected_counts[candidate],
            "count_ok": len(fields) == expected_counts[candidate],
            "duplicates": duplicates,
            "field_order_sha256": canonical_sha256(fields),
        }
        all_features.extend(fields)
    feature_spec = {
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "alias": "BIN-1D-MA7-CTP",
        "experiment": "P5 Oscillator + Completed-Weekly-Regime Increment and 2025+ Validation Audit",
        "created_utc": datetime.now(UTC).isoformat(),
        "status": STATUS,
        "contract_lock_status": LOCK_STATUS,
        "base_reference": {
            "p4_factor_group_spec": str(P4_FACTOR_GROUP_SPEC_PATH.relative_to(ROOT)),
            "p4_b0_feature_count": len(b0),
            "p4_b0_field_order_sha256": canonical_sha256(b0),
        },
        "feature_blocks": {
            "B0_P4_FULL": b0,
            "G3_VOLATILITY_STATE_REMOVED_FOR_C_NO_G3": g3,
            "G7_RSI6_OSCILLATOR": G7_RSI6,
            "G8_COMPLETED_WEEKLY_REGIME": G8_WEEKLY,
        },
        "candidates": {name: {"features": fields, "count": len(fields)} for name, fields in candidates.items()},
        "checks": {
            "candidate_checks": checks,
            "all_expected_counts_ok": all(row["count_ok"] and not row["duplicates"] for row in checks.values()),
            "hype_asset_forbidden": HYPE_ASSET,
            "hyper_asset_retained": HYPER_ASSET,
            "forbidden_outputs": ["strategy", "equity_curve", "sharpe", "live_spec", "runner_handoff", "trade_path_html", "hype_predictions"],
        },
        "numeric_new_features": G7_RSI6 + G8_WEEKLY,
        "known_tradfi_base_symbols": sorted(KNOWN_TRADFI_BASE_SYMBOLS),
        "all_feature_union_count": len(dict.fromkeys(all_features)),
    }
    if not feature_spec["checks"]["all_expected_counts_ok"]:
        raise RuntimeError("candidate feature spec count/order check failed")
    return feature_spec


def write_contract_lock(feature_spec: dict[str, Any], *, force: bool) -> None:
    if CONTRACT_LOCK_PATH.exists() and not force:
        existing = load_json(CONTRACT_LOCK_PATH)
        if existing.get("status") != LOCK_STATUS:
            raise RuntimeError("existing P5 contract lock has unexpected status")
        return
    atomic_write_json(FEATURE_SPEC_PATH, feature_spec)
    lock = {
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "alias": "BIN-1D-MA7-CTP",
        "experiment": "P5",
        "status": LOCK_STATUS,
        "created_utc": datetime.now(UTC).isoformat(),
        "frozen_before": ["p5_label_rate", "p5_auc", "p5_top10", "2025_plus_validation_label_read", "2025_plus_validation_metric_read"],
        "contract": {"path": str(SPEC_PATH.relative_to(ROOT)), "sha256": sha256_file(SPEC_PATH)},
        "feature_spec": {"path": str(FEATURE_SPEC_PATH.relative_to(ROOT)), "sha256": sha256_file(FEATURE_SPEC_PATH)},
        "script": {"path": str(SCRIPT_PATH.relative_to(ROOT)), "sha256": sha256_file(SCRIPT_PATH)},
        "p4_factor_group_spec": {
            "path": str(P4_FACTOR_GROUP_SPEC_PATH.relative_to(ROOT)),
            "sha256": sha256_file(P4_FACTOR_GROUP_SPEC_PATH),
        },
        "labels_or_2025_validation_read_before_lock": False,
    }
    atomic_write_json(CONTRACT_LOCK_PATH, lock)


def read_donor_asset_slugs() -> pd.DataFrame:
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    query = """
        SELECT DISTINCT asset, asset_slug
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        WHERE asset <> ?
        ORDER BY asset
    """
    assets = con.execute(query, [str(PANEL_GLOB), HYPE_ASSET]).fetchdf()
    if (assets["asset"] == HYPE_ASSET).any():
        raise RuntimeError("HYPE donor asset leaked into allowlist")
    if not (assets["asset"] == HYPER_ASSET).any():
        raise RuntimeError("HYPER/USDT:USDT is missing from donor allowlist")
    return assets


def p0_asset_day_paths_for_donor_slugs(donor_slugs: Iterable[str]) -> list[str]:
    paths: list[str] = []
    forbidden_slug = "hype_usdt_usdt"
    for slug in sorted(set(donor_slugs)):
        if str(slug).lower() == forbidden_slug:
            raise RuntimeError("refusing to read HYPE asset-day partition")
        partition = P0_ASSET_DAY_DIR / f"asset_slug_partition={slug}"
        if not partition.exists():
            continue
        paths.extend(str(path) for path in sorted(partition.glob("year=*/part-*.parquet")))
    if not paths:
        raise RuntimeError("no non-HYPE P0 asset-day paths found")
    if any("hype_usdt_usdt" in path.lower() for path in paths):
        raise RuntimeError("HYPE path was included in P0 asset-day read list")
    return paths


def load_p0r_panel(source_cols: list[str]) -> pd.DataFrame:
    base_cols = [
        "asset",
        "asset_slug",
        "side",
        "ts",
        "feature_known_at",
        "entry_ts",
        "entry_ref",
        "atr_anchor",
        TARGET,
        LABEL_END,
        NET_RETURN,
        "model_eligible_entry_p0r",
        "probe_raw_ma7_cross_dir",
        "dir_raw_ma7_cross",
        "future_path_complete_20d",
        "volatility_state_p0r",
    ]
    cols = list(dict.fromkeys(base_cols + source_cols))
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    quoted = ", ".join(f'"{c}"' for c in cols)
    query = f"""
        SELECT {quoted}
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        WHERE asset <> ?
    """
    df = con.execute(query, [str(PANEL_GLOB), HYPE_ASSET]).fetchdf()
    for col in ["ts", "feature_known_at", "entry_ts", LABEL_END]:
        df[col] = pd.to_datetime(df[col], utc=True)
    df["side_sign"] = np.where(df["side"].astype(str).str.lower() == "long", 1.0, -1.0)
    df["base_symbol"] = df["asset"].map(base_symbol)
    df["is_known_tradfi"] = df["base_symbol"].isin(KNOWN_TRADFI_BASE_SYMBOLS)
    df["event_year"] = df["ts"].dt.year.astype(int)
    return df


def prepare_event_panel(feature_spec: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    b0 = feature_spec["feature_blocks"]["B0_P4_FULL"]
    source_cols = P4.source_columns_for_features(b0)
    raw = load_p0r_panel(source_cols)
    if (raw["asset"] == HYPE_ASSET).any():
        raise RuntimeError("HYPE rows in P5 source panel")

    raw = raw.sort_values(["asset", "side", "ts"]).copy()
    for feature in b0:
        if feature.startswith("t1_") and feature not in raw.columns:
            raw[feature] = raw.groupby(["asset", "side"], sort=False)[P4.t1_source_name(feature)].shift(1)
    events = raw[(raw["probe_raw_ma7_cross_dir"]) & (raw["model_eligible_entry_p0r"])].copy()
    P4.assert_t1_is_prior_valid_day(raw, events)

    development = events[(events["ts"] < CUTOFF) & (events[LABEL_END] < CUTOFF)].copy()
    validation = events[(events["ts"] >= CUTOFF) & (events[LABEL_END] < P0_CUTOFF)].copy()
    main_validation = validation[~validation["is_known_tradfi"]].copy()

    strict_audit = {
        "strict_rows": int(len(development)),
        "strict_assets": int(development["asset"].nunique()),
        "strict_long": int((development["side"] == "long").sum()),
        "strict_short": int((development["side"] == "short").sum()),
        "strict_min_ts": development["ts"].min(),
        "strict_max_ts": development["ts"].max(),
        "strict_max_label_end": development[LABEL_END].max(),
        "strict_hype_rows": int((development["asset"] == HYPE_ASSET).sum()),
        "strict_known_tradfi_rows": int(development["is_known_tradfi"].sum()),
        "validation_rows_total": int(len(validation)),
        "validation_rows_main_crypto": int(len(main_validation)),
        "validation_known_tradfi_rows": int(validation["is_known_tradfi"].sum()),
        "validation_known_tradfi_assets": sorted(validation.loc[validation["is_known_tradfi"], "asset"].unique().tolist()),
        "validation_hype_rows": int((validation["asset"] == HYPE_ASSET).sum()),
        "strict_incomplete_20d_future_path": int((~development["future_path_complete_20d"].astype(bool)).sum()),
        "validation_incomplete_20d_future_path": int((~validation["future_path_complete_20d"].astype(bool)).sum()),
        "strict_non_directional_cross": int((development["dir_raw_ma7_cross"] != 1).sum()),
        "validation_year_counts_total": {str(k): int(v) for k, v in validation["event_year"].value_counts().sort_index().items()},
        "validation_year_counts_main_crypto": {str(k): int(v) for k, v in main_validation["event_year"].value_counts().sort_index().items()},
    }
    expected = {
        "strict_rows": EXPECTED_STRICT_ROWS,
        "strict_assets": EXPECTED_STRICT_ASSETS,
        "strict_long": EXPECTED_STRICT_LONG,
        "strict_short": EXPECTED_STRICT_SHORT,
        "strict_min_ts": EXPECTED_STRICT_MIN_TS,
        "strict_max_ts": EXPECTED_STRICT_MAX_TS,
        "strict_max_label_end": EXPECTED_MAX_LABEL_END,
        "strict_hype_rows": 0,
        "strict_known_tradfi_rows": 0,
    }
    mismatches = []
    for key, expected_value in expected.items():
        actual = strict_audit[key]
        if isinstance(expected_value, pd.Timestamp):
            ok = pd.Timestamp(actual) == expected_value
        else:
            ok = actual == expected_value
        if not ok:
            mismatches.append({"field": key, "actual": actual, "expected": expected_value})
    strict_audit["p4_strict_sample_reproduced"] = not mismatches
    strict_audit["mismatches"] = mismatches
    if mismatches:
        raise RuntimeError(f"P5 strict pre-2025 sample does not reproduce P4: {mismatches}")
    return development, validation, strict_audit


def load_price_panel(donor_assets: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    paths = p0_asset_day_paths_for_donor_slugs(donor_assets["asset_slug"].tolist())
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    cols = "asset, asset_slug, base_asset, ts, feature_known_at, open, high, low, close, complete_day"
    query = f"SELECT {cols} FROM read_parquet(?, union_by_name=true, hive_partitioning=true)"
    prices = con.execute(query, [paths]).fetchdf()
    for col in ["ts", "feature_known_at"]:
        prices[col] = pd.to_datetime(prices[col], utc=True)
    if (prices["asset"] == HYPE_ASSET).any():
        raise RuntimeError("HYPE rows were read into P5 price panel")
    if not (prices["asset"] == HYPER_ASSET).any():
        raise RuntimeError("HYPER rows missing from P5 price panel")
    prices = prices.sort_values(["asset", "ts"]).reset_index(drop=True)
    audit = {
        "donor_allowlist_assets": int(donor_assets["asset"].nunique()),
        "donor_allowlist_asset_slugs": int(donor_assets["asset_slug"].nunique()),
        "p0_asset_day_files_read": int(len(paths)),
        "hype_raw_file_read": False,
        "hype_rows_read": int((prices["asset"] == HYPE_ASSET).sum()),
        "hyper_rows_read": int((prices["asset"] == HYPER_ASSET).sum()),
        "min_ts": prices["ts"].min(),
        "max_ts": prices["ts"].max(),
    }
    return prices, audit


def wilder_rsi(close: pd.Series, period: int = 6) -> pd.Series:
    values = close.astype(float).to_numpy()
    out = np.full(len(values), np.nan, dtype=float)
    if len(values) <= period:
        return pd.Series(out, index=close.index, dtype=float)
    delta = np.diff(values)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = float(np.nanmean(gain[:period]))
    avg_loss = float(np.nanmean(loss[:period]))

    def rsi_from_avg(g: float, l: float) -> float:
        if l == 0 and g == 0:
            return 50.0
        if l == 0:
            return 100.0
        rs = g / l
        return 100.0 - (100.0 / (1.0 + rs))

    out[period] = rsi_from_avg(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        avg_gain = ((avg_gain * (period - 1)) + float(gain[i - 1])) / period
        avg_loss = ((avg_loss * (period - 1)) + float(loss[i - 1])) / period
        out[i] = rsi_from_avg(avg_gain, avg_loss)
    return pd.Series(out, index=close.index, dtype=float)


def build_rsi_daily(prices: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for _, g in prices.sort_values(["asset", "ts"]).groupby("asset", sort=False):
        x = g[["asset", "ts"]].copy()
        rsi = wilder_rsi(g["close"], 6)
        x["rsi6"] = rsi.to_numpy()
        x["rsi6_lag1"] = x["rsi6"].shift(1)
        x["rsi6_lag3"] = x["rsi6"].shift(3)
        x["rsi6_centered_raw"] = (x["rsi6"] - 50.0) / 50.0
        x["rsi6_delta_1d_raw"] = (x["rsi6"] - x["rsi6_lag1"]) / 100.0
        x["rsi6_delta_3d_raw"] = (x["rsi6"] - x["rsi6_lag3"]) / 100.0
        roll_min = x["rsi6"].rolling(5, min_periods=1).min()
        roll_max = x["rsi6"].rolling(5, min_periods=1).max()
        x["rsi6_recovery_long_raw"] = (x["rsi6"] - roll_min) / 100.0
        x["rsi6_recovery_short_raw"] = (roll_max - x["rsi6"]) / 100.0
        x["rsi6_cross_long_raw"] = ((x["rsi6"] > 50.0) & (x["rsi6_lag1"] <= 50.0)).astype(float)
        x["rsi6_cross_short_raw"] = ((x["rsi6"] < 50.0) & (x["rsi6_lag1"] >= 50.0)).astype(float)
        for col in [
            "rsi6_centered_raw",
            "rsi6_delta_1d_raw",
            "rsi6_delta_3d_raw",
            "rsi6_recovery_long_raw",
            "rsi6_recovery_short_raw",
            "rsi6_cross_long_raw",
            "rsi6_cross_short_raw",
        ]:
            x[f"t1_{col}"] = x[col].shift(1)
        rows.append(x)
    return pd.concat(rows, ignore_index=True)


def add_rsi_features(events: pd.DataFrame, rsi_daily: pd.DataFrame) -> pd.DataFrame:
    out = events.merge(rsi_daily, on=["asset", "ts"], how="left", validate="many_to_one")
    sign = out["side_sign"].astype(float)
    is_long = out["side"].astype(str).str.lower() == "long"
    out["dir_rsi6_centered"] = sign * out["rsi6_centered_raw"]
    out["dir_rsi6_delta_1d"] = sign * out["rsi6_delta_1d_raw"]
    out["dir_rsi6_delta_3d"] = sign * out["rsi6_delta_3d_raw"]
    out["dir_rsi6_recovery_from_5d_adverse_extreme"] = np.where(
        is_long, out["rsi6_recovery_long_raw"], out["rsi6_recovery_short_raw"]
    )
    out["dir_rsi6_cross_50"] = np.where(is_long, out["rsi6_cross_long_raw"], out["rsi6_cross_short_raw"])
    out["t1_dir_rsi6_centered"] = sign * out["t1_rsi6_centered_raw"]
    out["t1_dir_rsi6_delta_1d"] = sign * out["t1_rsi6_delta_1d_raw"]
    out["t1_dir_rsi6_delta_3d"] = sign * out["t1_rsi6_delta_3d_raw"]
    out["t1_dir_rsi6_recovery_from_5d_adverse_extreme"] = np.where(
        is_long, out["t1_rsi6_recovery_long_raw"], out["t1_rsi6_recovery_short_raw"]
    )
    out["t1_dir_rsi6_cross_50"] = np.where(is_long, out["t1_rsi6_cross_long_raw"], out["t1_rsi6_cross_short_raw"])
    return out.drop(
        columns=[
            "rsi6",
            "rsi6_lag1",
            "rsi6_lag3",
            "rsi6_centered_raw",
            "rsi6_delta_1d_raw",
            "rsi6_delta_3d_raw",
            "rsi6_recovery_long_raw",
            "rsi6_recovery_short_raw",
            "rsi6_cross_long_raw",
            "rsi6_cross_short_raw",
            "t1_rsi6_centered_raw",
            "t1_rsi6_delta_1d_raw",
            "t1_rsi6_delta_3d_raw",
            "t1_rsi6_recovery_long_raw",
            "t1_rsi6_recovery_short_raw",
            "t1_rsi6_cross_long_raw",
            "t1_rsi6_cross_short_raw",
        ]
    )


def build_weekly_features(prices: pd.DataFrame) -> pd.DataFrame:
    daily = prices[prices["complete_day"].astype(bool)].copy()
    daily["week_start"] = daily["ts"] - pd.to_timedelta(daily["ts"].dt.weekday, unit="D")
    weekly = (
        daily.sort_values(["asset", "ts"])
        .groupby(["asset", "week_start"], as_index=False)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            day_count=("ts", "count"),
            first_day=("ts", "min"),
            last_day=("ts", "max"),
            all_complete=("complete_day", "all"),
        )
    )
    weekly["week_end_day"] = weekly["week_start"] + pd.Timedelta(days=6)
    weekly = weekly[
        (weekly["day_count"] == 7)
        & (weekly["all_complete"])
        & (weekly["first_day"] == weekly["week_start"])
        & (weekly["last_day"] == weekly["week_end_day"])
    ].copy()
    rows: list[pd.DataFrame] = []
    for _, g in weekly.sort_values(["asset", "week_start"]).groupby("asset", sort=False):
        x = g[["asset", "week_start", "open", "high", "low", "close"]].copy()
        prev_close = x["close"].shift(1)
        tr = pd.concat(
            [(x["high"] - x["low"]).abs(), (x["high"] - prev_close).abs(), (x["low"] - prev_close).abs()], axis=1
        ).max(axis=1)
        x["watr6"] = tr.rolling(6, min_periods=6).mean()
        x["w_ret_1w_raw"] = x["close"].pct_change(1)
        x["w_ret_4w_raw"] = x["close"].pct_change(4)
        x["w_ret_12w_raw"] = x["close"].pct_change(12)
        x["sma4"] = x["close"].rolling(4, min_periods=4).mean()
        x["sma13"] = x["close"].rolling(13, min_periods=13).mean()
        x["w_close_sma4_dist_watr6_raw"] = (x["close"] - x["sma4"]) / x["watr6"]
        x["w_close_sma13_dist_watr6_raw"] = (x["close"] - x["sma13"]) / x["watr6"]
        x["w_sma4_slope_1w_watr6_raw"] = (x["sma4"] - x["sma4"].shift(1)) / x["watr6"]
        x["w_sma13_slope_1w_watr6_raw"] = (x["sma13"] - x["sma13"].shift(1)) / x["watr6"]
        x["w_ma4_ma13_alignment_raw"] = np.sign(x["sma4"] - x["sma13"])
        x["w_atr6_pct"] = x["watr6"] / x["close"]
        denom = x["close"].diff().abs().rolling(12, min_periods=12).sum()
        x["w_path_efficiency_12w"] = (x["close"] - x["close"].shift(12)).abs() / denom
        x["weekly_history_13w_complete"] = (
            (x["week_start"] - x["week_start"].shift(12) == pd.Timedelta(days=84)).fillna(False).astype(float)
        )
        rows.append(x)
    features = pd.concat(rows, ignore_index=True)
    features["weekly_feature_known_at"] = features["week_start"] + pd.Timedelta(days=7)
    keep = [
        "asset",
        "week_start",
        "weekly_feature_known_at",
        "w_ret_1w_raw",
        "w_ret_4w_raw",
        "w_ret_12w_raw",
        "w_close_sma4_dist_watr6_raw",
        "w_close_sma13_dist_watr6_raw",
        "w_sma4_slope_1w_watr6_raw",
        "w_sma13_slope_1w_watr6_raw",
        "w_ma4_ma13_alignment_raw",
        "w_atr6_pct",
        "w_path_efficiency_12w",
        "weekly_history_13w_complete",
    ]
    return features[keep].sort_values(["asset", "weekly_feature_known_at"]).reset_index(drop=True)


def add_weekly_features(events: pd.DataFrame, weekly: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    left = events.sort_values(["feature_known_at", "asset"]).reset_index(drop=True)
    right = weekly.sort_values(["weekly_feature_known_at", "asset"]).reset_index(drop=True)
    joined = pd.merge_asof(
        left,
        right,
        by="asset",
        left_on="feature_known_at",
        right_on="weekly_feature_known_at",
        direction="backward",
        allow_exact_matches=True,
    )
    leak_mask = joined["weekly_feature_known_at"].notna() & (joined["weekly_feature_known_at"] > joined["feature_known_at"])
    if leak_mask.any():
        raise RuntimeError("WEEKLY_LOOKAHEAD_CONTAMINATION")
    sign = joined["side_sign"].astype(float)
    joined["dir_w_ret_1w"] = sign * joined["w_ret_1w_raw"]
    joined["dir_w_ret_4w"] = sign * joined["w_ret_4w_raw"]
    joined["dir_w_ret_12w"] = sign * joined["w_ret_12w_raw"]
    joined["dir_w_close_sma4_dist_watr6"] = sign * joined["w_close_sma4_dist_watr6_raw"]
    joined["dir_w_close_sma13_dist_watr6"] = sign * joined["w_close_sma13_dist_watr6_raw"]
    joined["dir_w_sma4_slope_1w_watr6"] = sign * joined["w_sma4_slope_1w_watr6_raw"]
    joined["dir_w_sma13_slope_1w_watr6"] = sign * joined["w_sma13_slope_1w_watr6_raw"]
    joined["dir_w_ma4_ma13_alignment"] = sign * joined["w_ma4_ma13_alignment_raw"]
    joined["weekly_history_13w_complete"] = joined["weekly_history_13w_complete"].fillna(0.0)
    audit = {
        "events": int(len(joined)),
        "weekly_rows": int(len(weekly)),
        "weekly_feature_known_at_missing_rows": int(joined["weekly_feature_known_at"].isna().sum()),
        "weekly_feature_known_at_lt_feature_known_at": int(
            (joined["weekly_feature_known_at"].notna() & (joined["weekly_feature_known_at"] < joined["feature_known_at"])).sum()
        ),
        "weekly_feature_known_at_eq_feature_known_at": int(
            (joined["weekly_feature_known_at"].notna() & (joined["weekly_feature_known_at"] == joined["feature_known_at"])).sum()
        ),
        "weekly_feature_known_at_gt_feature_known_at": int(leak_mask.sum()),
        "verdict": "PASS_NO_WEEKLY_LOOKAHEAD",
    }
    drop_cols = [
        "w_ret_1w_raw",
        "w_ret_4w_raw",
        "w_ret_12w_raw",
        "w_close_sma4_dist_watr6_raw",
        "w_close_sma13_dist_watr6_raw",
        "w_sma4_slope_1w_watr6_raw",
        "w_sma13_slope_1w_watr6_raw",
        "w_ma4_ma13_alignment_raw",
    ]
    return joined.drop(columns=drop_cols), audit


def add_new_features(events: pd.DataFrame, rsi_daily: pd.DataFrame, weekly: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    with_rsi = add_rsi_features(events, rsi_daily)
    with_weekly, weekly_audit = add_weekly_features(with_rsi, weekly)
    missing = {
        feature: float(with_weekly[feature].isna().mean()) if feature in with_weekly else 1.0
        for feature in G7_RSI6 + G8_WEEKLY
    }
    return with_weekly, {"new_feature_missing_rate": missing, "weekly_causality": weekly_audit}


def fold_split(df: pd.DataFrame, fold: tuple[str, pd.Timestamp, pd.Timestamp]) -> tuple[pd.DataFrame, pd.DataFrame]:
    name, start, end = fold
    train = df[df[LABEL_END] < start].copy()
    valid = df[(df["ts"] >= start) & (df["ts"] < end) & (df[LABEL_END] < CUTOFF)].copy()
    train["fold"] = name
    valid["fold"] = name
    return train, valid


def clip_probability(probability: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(probability, dtype=float), 1e-6, 1.0 - 1e-6)


def top_mask_by_group(frame: pd.DataFrame, probability: np.ndarray, group_cols: list[str] | None = None, q: float = 0.90) -> np.ndarray:
    df = frame.reset_index(drop=True).copy()
    df["_p"] = probability
    mask = np.zeros(len(df), dtype=bool)
    if not group_cols:
        cutoff = df["_p"].quantile(q)
        return (df["_p"] >= cutoff).to_numpy()
    by: str | list[str] = group_cols[0] if len(group_cols) == 1 else group_cols
    for _, idx in df.groupby(by, sort=False).groups.items():
        vals = df.loc[idx, "_p"]
        cutoff = vals.quantile(q)
        mask[np.asarray(idx, dtype=int)] = vals >= cutoff
    return mask


def bottom_mask_by_group(frame: pd.DataFrame, probability: np.ndarray, group_cols: list[str] | None = None, q: float = 0.10) -> np.ndarray:
    df = frame.reset_index(drop=True).copy()
    df["_p"] = probability
    mask = np.zeros(len(df), dtype=bool)
    if not group_cols:
        cutoff = df["_p"].quantile(q)
        return (df["_p"] <= cutoff).to_numpy()
    by: str | list[str] = group_cols[0] if len(group_cols) == 1 else group_cols
    for _, idx in df.groupby(by, sort=False).groups.items():
        vals = df.loc[idx, "_p"]
        cutoff = vals.quantile(q)
        mask[np.asarray(idx, dtype=int)] = vals <= cutoff
    return mask


def ece_10(y: np.ndarray, p: np.ndarray) -> float | None:
    if len(y) == 0:
        return None
    bins = np.linspace(0.0, 1.0, 11)
    total = 0.0
    for i in range(10):
        if i == 9:
            mask = (p >= bins[i]) & (p <= bins[i + 1])
        else:
            mask = (p >= bins[i]) & (p < bins[i + 1])
        if mask.any():
            total += float(mask.mean()) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return total


def metric_values(
    frame: pd.DataFrame,
    probability: np.ndarray,
    *,
    top_group_cols: list[str] | None = None,
    threshold: float | None = None,
) -> dict[str, Any]:
    if len(frame) == 0:
        return {
            "n": 0,
            "positive_rate": None,
            "roc_auc": None,
            "pr_auc": None,
            "brier": None,
            "brier_skill": None,
            "logloss": None,
            "ece10": None,
            "top10_success_rate": None,
            "top10_n": 0,
            "top10_uplift": None,
            "top10_net_mean": None,
            "top10_net_median": None,
            "bottom10_success_rate": None,
            "top_bottom_success_diff": None,
        }
    y = frame[TARGET].astype(int).to_numpy()
    p = clip_probability(probability)
    base_rate = float(y.mean())
    auc = float(roc_auc_score(y, p)) if len(np.unique(y)) >= 2 else None
    pr_auc = float(average_precision_score(y, p)) if len(np.unique(y)) >= 2 else None
    brier = float(brier_score_loss(y, p))
    const_brier = float(brier_score_loss(y, np.full(len(y), base_rate)))
    brier_skill = None if const_brier == 0 else 1.0 - brier / const_brier
    ll = float(log_loss(y, p, labels=[0, 1]))
    if threshold is None:
        top = top_mask_by_group(frame, p, top_group_cols)
    else:
        top = p >= threshold
    bottom = bottom_mask_by_group(frame, p, top_group_cols)
    top_y = y[top]
    bottom_y = y[bottom]
    net = frame[NET_RETURN].astype(float).to_numpy() if NET_RETURN in frame else np.full(len(frame), np.nan)
    top_rate = float(top_y.mean()) if len(top_y) else None
    bottom_rate = float(bottom_y.mean()) if len(bottom_y) else None
    return {
        "n": int(len(frame)),
        "positive_rate": base_rate,
        "roc_auc": auc,
        "pr_auc": pr_auc,
        "brier": brier,
        "brier_skill": brier_skill,
        "logloss": ll,
        "ece10": ece_10(y, p),
        "top10_success_rate": top_rate,
        "top10_n": int(top.sum()),
        "top10_coverage": float(top.mean()),
        "top10_uplift": None if top_rate is None else top_rate - base_rate,
        "top10_net_mean": float(np.nanmean(net[top])) if top.any() else None,
        "top10_net_median": float(np.nanmedian(net[top])) if top.any() else None,
        "bottom10_success_rate": bottom_rate,
        "bottom10_n": int(bottom.sum()),
        "top_bottom_success_diff": None if top_rate is None or bottom_rate is None else top_rate - bottom_rate,
    }


def fit_logit(train: pd.DataFrame, valid: pd.DataFrame, features: list[str]) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    categorical = ["t1_volatility_state_p0r"] if "t1_volatility_state_p0r" in features else []
    prep = P2.TabularPreprocessor(features, categorical).fit(train)
    x_train = prep.transform(train)
    x_valid = prep.transform(valid)
    scaler = StandardScaler()
    x_train_s = scaler.fit_transform(x_train)
    x_valid_s = scaler.transform(x_valid)
    model = LogisticRegression(penalty="l2", solver="lbfgs", max_iter=1000, random_state=SEED)
    model.fit(x_train_s, train[TARGET].astype(int).to_numpy())
    return (
        clip_probability(model.predict_proba(x_train_s)[:, 1]),
        clip_probability(model.predict_proba(x_valid_s)[:, 1]),
        {
            "preprocessor": prep,
            "scaler": scaler,
            "model": model,
            "encoded_feature_count": int(x_train_s.shape[1]),
            "coef_abs_sum": float(np.abs(model.coef_[0]).sum()),
        },
    )


def apply_fitted(bundle: dict[str, Any], frame: pd.DataFrame) -> np.ndarray:
    x = bundle["preprocessor"].transform(frame)
    x_s = bundle["scaler"].transform(x)
    return clip_probability(bundle["model"].predict_proba(x_s)[:, 1])


def asset_balanced_auc(frame: pd.DataFrame, probability: np.ndarray) -> float | None:
    if len(frame) == 0 or frame[TARGET].nunique() < 2:
        return None
    return float(roc_auc_score(frame[TARGET].astype(int), probability, sample_weight=P4.asset_balanced_weights(frame)))


def non_overlap_sample(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, g in frame.sort_values(["asset", "ts"]).groupby("asset", sort=False):
        last_end = pd.Timestamp.min.tz_localize("UTC")
        for idx, row in g.iterrows():
            if row["ts"] >= last_end:
                rows.append(idx)
                last_end = row[LABEL_END]
    return frame.loc[rows].copy()


def stratum_auc(frame: pd.DataFrame, probability: np.ndarray, mask: pd.Series | np.ndarray) -> float | None:
    sub = frame.loc[np.asarray(mask)].copy()
    if len(sub) == 0 or sub[TARGET].nunique() < 2:
        return None
    return float(roc_auc_score(sub[TARGET].astype(int), probability[np.asarray(mask)]))


def leave_asset_group_out_auc(frame: pd.DataFrame, probability: np.ndarray, groups: int = 5) -> dict[str, float | None]:
    df = frame[["asset", TARGET]].copy()
    df["_p"] = probability
    asset_order = sorted(df["asset"].unique())
    bucket = {asset: i % groups for i, asset in enumerate(asset_order)}
    out: dict[str, float | None] = {}
    for i in range(groups):
        sub = df[df["asset"].map(bucket) == i]
        if len(sub) and sub[TARGET].nunique() >= 2:
            out[f"asset_group_{i}"] = float(roc_auc_score(sub[TARGET].astype(int), sub["_p"]))
        else:
            out[f"asset_group_{i}"] = None
    return out


def run_development(development: pd.DataFrame, candidates: dict[str, list[str]]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    fold_rows: list[dict[str, Any]] = []
    oof_parts: list[pd.DataFrame] = []
    bundles: dict[str, list[dict[str, Any]]] = {candidate: [] for candidate in candidates}

    for fold in FOLDS:
        fold_name, _, _ = fold
        train, valid = fold_split(development, fold)
        pred_part = valid[["asset", "side", "ts", "feature_known_at", "entry_ts", LABEL_END, TARGET, NET_RETURN, "base_symbol"]].copy()
        pred_part["fold"] = fold_name
        for candidate, features in candidates.items():
            train_raw, valid_raw, bundle = fit_logit(train, valid, features)
            bundles[candidate].append(bundle)
            pred_part[f"{candidate}_raw_probability"] = valid_raw
            train_metrics = metric_values(train, train_raw)
            valid_metrics = metric_values(valid, valid_raw, top_group_cols=None)
            top_gap = None
            if train_metrics["top10_uplift"] is not None and valid_metrics["top10_uplift"] is not None:
                top_gap = train_metrics["top10_uplift"] - valid_metrics["top10_uplift"]
            row = {
                "period": "development",
                "fold": fold_name,
                "candidate": candidate,
                "train_n": train_metrics["n"],
                "train_positive_rate": train_metrics["positive_rate"],
                "train_roc_auc": train_metrics["roc_auc"],
                "train_pr_auc": train_metrics["pr_auc"],
                "train_brier": train_metrics["brier"],
                "train_logloss": train_metrics["logloss"],
                "train_top10_success_rate": train_metrics["top10_success_rate"],
                "train_top10_uplift": train_metrics["top10_uplift"],
                "train_top10_net_mean": train_metrics["top10_net_mean"],
                "train_top10_net_median": train_metrics["top10_net_median"],
                "validation_n": valid_metrics["n"],
                "validation_positive_rate": valid_metrics["positive_rate"],
                "validation_roc_auc": valid_metrics["roc_auc"],
                "validation_pr_auc": valid_metrics["pr_auc"],
                "validation_brier": valid_metrics["brier"],
                "validation_brier_skill": valid_metrics["brier_skill"],
                "validation_logloss": valid_metrics["logloss"],
                "validation_ece10": valid_metrics["ece10"],
                "validation_top10_success_rate": valid_metrics["top10_success_rate"],
                "validation_top10_uplift": valid_metrics["top10_uplift"],
                "validation_top10_net_mean": valid_metrics["top10_net_mean"],
                "validation_top10_net_median": valid_metrics["top10_net_median"],
                "validation_bottom10_success_rate": valid_metrics["bottom10_success_rate"],
                "validation_top_bottom_success_diff": valid_metrics["top_bottom_success_diff"],
                "train_validation_auc_gap": None
                if train_metrics["roc_auc"] is None or valid_metrics["roc_auc"] is None
                else train_metrics["roc_auc"] - valid_metrics["roc_auc"],
                "train_validation_top10_uplift_gap": top_gap,
                "encoded_feature_count": bundle["encoded_feature_count"],
            }
            fold_rows.append(row)
        oof_parts.append(pred_part)

    oof = pd.concat(oof_parts, ignore_index=True)
    forward_calibration_audits: dict[str, list[dict[str, Any]]] = {}
    fold_order = [fold_name for fold_name, _, _ in FOLDS]
    for candidate in candidates:
        oof[f"{candidate}_calibrated_probability"] = np.nan
        forward_calibration_audits[candidate] = []
        for fold_index, (fold_name, fold_start, _) in enumerate(FOLDS):
            valid_mask = oof["fold"] == fold_name
            prior_folds = fold_order[:fold_index]
            prior = oof[oof["fold"].isin(prior_folds) & oof[LABEL_END].lt(fold_start)].copy()
            if len(prior) == 0 or prior[TARGET].nunique() < 2:
                oof.loc[valid_mask, f"{candidate}_calibrated_probability"] = oof.loc[
                    valid_mask, f"{candidate}_raw_probability"
                ]
                forward_calibration_audits[candidate].append(
                    {
                        "evaluation_fold": fold_name,
                        "evaluation_start": fold_start,
                        "calibration_train_folds": prior_folds,
                        "calibration_train_rows": int(len(prior)),
                        "calibration_train_label_end_max": None,
                        "method": "raw_no_prior_completed_oof",
                        "temporal_isolation_pass": True,
                    }
                )
                continue
            cal = P2.fit_platt(prior[f"{candidate}_raw_probability"].to_numpy(), prior[TARGET].astype(int).to_numpy())
            oof.loc[valid_mask, f"{candidate}_calibrated_probability"] = P2.apply_calibration(
                oof.loc[valid_mask, f"{candidate}_raw_probability"].to_numpy(), cal
            )
            max_label_end = prior[LABEL_END].max()
            forward_calibration_audits[candidate].append(
                {
                    "evaluation_fold": fold_name,
                    "evaluation_start": fold_start,
                    "calibration_train_folds": prior_folds,
                    "calibration_train_rows": int(len(prior)),
                    "calibration_train_label_end_max": max_label_end,
                    "method": cal["method"],
                    "temporal_isolation_pass": bool(max_label_end < fold_start),
                }
            )

    for candidate in candidates:
        for fold_name, _, _ in FOLDS:
            mask = oof["fold"] == fold_name
            metrics = metric_values(oof.loc[mask], oof.loc[mask, f"{candidate}_calibrated_probability"].to_numpy())
            fold_rows.append(
                {
                    "period": "development_calibrated_oof",
                    "fold": fold_name,
                    "candidate": candidate,
                    "validation_n": metrics["n"],
                    "validation_positive_rate": metrics["positive_rate"],
                    "validation_roc_auc": metrics["roc_auc"],
                    "validation_pr_auc": metrics["pr_auc"],
                    "validation_brier": metrics["brier"],
                    "validation_brier_skill": metrics["brier_skill"],
                    "validation_logloss": metrics["logloss"],
                    "validation_ece10": metrics["ece10"],
                    "validation_top10_success_rate": metrics["top10_success_rate"],
                    "validation_top10_uplift": metrics["top10_uplift"],
                    "validation_top10_net_mean": metrics["top10_net_mean"],
                    "validation_top10_net_median": metrics["top10_net_median"],
                }
            )

    aggregate: dict[str, Any] = {}
    no = non_overlap_sample(oof)
    for candidate in candidates:
        raw = oof[f"{candidate}_raw_probability"].to_numpy()
        cal = oof[f"{candidate}_calibrated_probability"].to_numpy()
        fold_aucs = [
            metric_values(oof[oof["fold"] == fold_name], oof.loc[oof["fold"] == fold_name, f"{candidate}_raw_probability"].to_numpy())[
                "roc_auc"
            ]
            for fold_name, _, _ in FOLDS
        ]
        fold_top = [
            metric_values(oof[oof["fold"] == fold_name], oof.loc[oof["fold"] == fold_name, f"{candidate}_raw_probability"].to_numpy())[
                "top10_success_rate"
            ]
            for fold_name, _, _ in FOLDS
        ]
        aggregate[candidate] = {
            "macro_auc": float(np.mean([x for x in fold_aucs if x is not None])),
            "worst_fold_auc": float(np.min([x for x in fold_aucs if x is not None])),
            "top10_success_mean_3y": float(np.mean([x for x in fold_top if x is not None])),
            "top10_success_worst_3y": float(np.min([x for x in fold_top if x is not None])),
            "top10_success_std_3y": float(np.std([x for x in fold_top if x is not None], ddof=0)),
            "oof_raw": metric_values(oof, raw, top_group_cols=["fold"]),
            "oof_calibrated": metric_values(oof, cal, top_group_cols=["fold"]),
            "long_auc": stratum_auc(oof, raw, oof["side"] == "long"),
            "short_auc": stratum_auc(oof, raw, oof["side"] == "short"),
            "non_overlap_auc": float(roc_auc_score(no[TARGET].astype(int), no.loc[:, f"{candidate}_raw_probability"]))
            if len(no) and no[TARGET].nunique() >= 2
            else None,
            "asset_balanced_auc": asset_balanced_auc(oof, raw),
            "leave_asset_group_out_auc": leave_asset_group_out_auc(oof, raw),
            "forward_calibration_audit": forward_calibration_audits[candidate],
        }
    return pd.DataFrame(fold_rows), oof, aggregate


def fit_final_validation(
    development: pd.DataFrame,
    validation: pd.DataFrame,
    oof: pd.DataFrame,
    candidates: dict[str, list[str]],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    pred = validation[
        [
            "asset",
            "side",
            "ts",
            "feature_known_at",
            "entry_ts",
            LABEL_END,
            TARGET,
            NET_RETURN,
            "base_symbol",
            "is_known_tradfi",
            "event_year",
        ]
    ].copy()
    seen_assets = set(development["asset"].unique())
    pred["asset_generalization"] = np.where(pred["asset"].isin(seen_assets), "seen_asset", "new_asset")
    pred["validation_role"] = np.where(pred["is_known_tradfi"], "unsupported_tradfi_diagnostic", "main_crypto_validation")

    calibration: dict[str, Any] = {}
    for candidate, features in candidates.items():
        train_raw, valid_raw, bundle = fit_logit(development, validation, features)
        cal = P2.fit_platt(oof[f"{candidate}_raw_probability"].to_numpy(), oof[TARGET].astype(int).to_numpy())
        oof_final_cal = P2.apply_calibration(oof[f"{candidate}_raw_probability"].to_numpy(), cal)
        valid_cal = P2.apply_calibration(valid_raw, cal)
        threshold = float(np.quantile(oof_final_cal, 0.90))
        raw_threshold = float(np.quantile(oof[f"{candidate}_raw_probability"].to_numpy(), 0.90))
        selected_by_raw = valid_raw >= raw_threshold
        selected_by_calibrated = valid_cal >= threshold
        if not np.array_equal(selected_by_raw, selected_by_calibrated):
            raise RuntimeError(f"frozen raw/calibrated decision mismatch for {candidate}")
        pred[f"{candidate}_raw_probability"] = valid_raw
        pred[f"{candidate}_calibrated_probability"] = valid_cal
        pred[f"{candidate}_frozen_threshold_selected"] = selected_by_raw
        calibration[candidate] = {
            "platt_fitted_on": "pre_2025_D1_D2_D3_OOF_only",
            "threshold_fitted_on": "pre_2025_D1_D2_D3_OOF_only",
            "threshold_probability_space": "final_all_oof_platt_calibrator_with_raw_score_decision_parity",
            "frozen_calibrated_probability_threshold_90pct": threshold,
            "frozen_raw_probability_threshold_90pct": raw_threshold,
            "platt_parameters": cal,
            "oof_threshold_rows": int(len(oof)),
            "validation_raw_calibrated_selection_parity": True,
            "validation_used_for_fit": False,
            "train_rows": int(len(development)),
            "validation_rows_predicted": int(len(validation)),
            "encoded_feature_count": bundle["encoded_feature_count"],
            "train_raw_metrics": metric_values(development, train_raw),
        }
    return pred, calibration


def build_strata(
    oof: pd.DataFrame,
    validation_pred: pd.DataFrame,
    candidates: dict[str, list[str]],
    calibration: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    main_val = validation_pred[validation_pred["validation_role"] == "main_crypto_validation"].copy()
    for candidate in candidates:
        dev_raw = oof[f"{candidate}_raw_probability"].to_numpy()
        rows.append({"period": "development", "scope": "pooled_fold_relative", "candidate": candidate, **metric_values(oof, dev_raw, top_group_cols=["fold"])})
        for side in ["long", "short"]:
            sub = oof[oof["side"] == side]
            rows.append({"period": "development", "scope": f"side:{side}", "candidate": candidate, **metric_values(sub, sub[f"{candidate}_raw_probability"].to_numpy())})
        no = non_overlap_sample(oof)
        rows.append({"period": "development", "scope": "non_overlap_20d", "candidate": candidate, **metric_values(no, no[f"{candidate}_raw_probability"].to_numpy())})

        val_raw = main_val[f"{candidate}_raw_probability"].to_numpy()
        val_cal = main_val[f"{candidate}_calibrated_probability"].to_numpy()
        rows.append({"period": "validation_2025_plus", "scope": "pooled_validation_top10", "candidate": candidate, **metric_values(main_val, val_raw)})
        rows.append(
            {
                "period": "validation_2025_plus",
                "scope": "year_relative_top10",
                "candidate": candidate,
                **metric_values(main_val, val_raw, top_group_cols=["event_year"]),
            }
        )
        rows.append(
            {
                "period": "validation_2025_plus",
                "scope": "frozen_threshold_selection",
                "candidate": candidate,
                **metric_values(main_val, val_cal, threshold=calibration[candidate]["frozen_calibrated_probability_threshold_90pct"]),
            }
        )
        for year, sub in main_val.groupby("event_year", sort=True):
            rows.append({"period": "validation_2025_plus", "scope": f"year:{year}", "candidate": candidate, **metric_values(sub, sub[f"{candidate}_raw_probability"].to_numpy())})
            rows.append(
                {
                    "period": "validation_2025_plus",
                    "scope": f"year:{year}:frozen_threshold",
                    "candidate": candidate,
                    **metric_values(
                        sub,
                        sub[f"{candidate}_calibrated_probability"].to_numpy(),
                        threshold=calibration[candidate]["frozen_calibrated_probability_threshold_90pct"],
                    ),
                }
            )
        for side in ["long", "short"]:
            sub = main_val[main_val["side"] == side]
            rows.append({"period": "validation_2025_plus", "scope": f"side:{side}", "candidate": candidate, **metric_values(sub, sub[f"{candidate}_raw_probability"].to_numpy())})
        for asset_group in ["seen_asset", "new_asset"]:
            sub = main_val[main_val["asset_generalization"] == asset_group]
            rows.append({"period": "validation_2025_plus", "scope": asset_group, "candidate": candidate, **metric_values(sub, sub[f"{candidate}_raw_probability"].to_numpy())})
        no_val = non_overlap_sample(main_val)
        rows.append({"period": "validation_2025_plus", "scope": "non_overlap_20d", "candidate": candidate, **metric_values(no_val, no_val[f"{candidate}_raw_probability"].to_numpy())})
        main_val["_month"] = main_val["ts"].dt.to_period("M").astype(str)
        for month, sub in main_val.groupby("_month", sort=True):
            rows.append({"period": "validation_2025_plus", "scope": f"month:{month}", "candidate": candidate, **metric_values(sub, sub[f"{candidate}_raw_probability"].to_numpy())})
        main_val["_block28"] = ((main_val["ts"] - CUTOFF).dt.days // BOOTSTRAP_BLOCK_DAYS).astype(int)
        for block, sub in main_val.groupby("_block28", sort=True):
            rows.append({"period": "validation_2025_plus", "scope": f"block28:{block}", "candidate": candidate, **metric_values(sub, sub[f"{candidate}_raw_probability"].to_numpy())})

    daily = (
        main_val.groupby("ts")
        .agg(
            event_count=("asset", "size"),
            r_b0_selected=("R_B0_69_frozen_threshold_selected", "sum"),
            no_g3_selected=("C_NO_G3_58_frozen_threshold_selected", "sum"),
        )
        .reset_index()
    )
    daily_summary = {
        "daily_event_count": daily["event_count"].describe(percentiles=[0.1, 0.5, 0.9]).to_dict(),
        "daily_r_b0_frozen_selection_count": daily["r_b0_selected"].describe(percentiles=[0.1, 0.5, 0.9]).to_dict(),
        "daily_c_no_g3_frozen_selection_count": daily["no_g3_selected"].describe(percentiles=[0.1, 0.5, 0.9]).to_dict(),
    }
    return pd.DataFrame(rows), daily_summary


def make_block_draws(frame: pd.DataFrame, *, period_col: str | None = None) -> tuple[dict[str, list[np.ndarray]], str]:
    df = frame.copy()
    if period_col is None:
        df["_period"] = "all"
        period_col = "_period"
    rng = np.random.default_rng(SEED)
    draws: dict[str, list[np.ndarray]] = {}
    for period, g in df.groupby(period_col, sort=True):
        block_ids = ((g["ts"] - g["ts"].min()).dt.days // BOOTSTRAP_BLOCK_DAYS).astype(int)
        blocks = sorted(block_ids.unique())
        index_by_block = {block: g.index[block_ids.to_numpy() == block].to_numpy() for block in blocks}
        period_draws: list[np.ndarray] = []
        for _ in range(BOOTSTRAP_SAMPLES):
            sampled_blocks = rng.choice(blocks, size=len(blocks), replace=True)
            period_draws.append(np.concatenate([index_by_block[int(block)] for block in sampled_blocks]))
        draws[str(period)] = period_draws
    digest_payload = {k: [draw[:10].tolist() + [int(len(draw))] for draw in v[:10]] for k, v in draws.items()}
    return draws, canonical_sha256(digest_payload)


def _score_metric(frame: pd.DataFrame, probability: np.ndarray, metric: str, *, top_group_cols: list[str] | None = None) -> float | None:
    if len(frame) == 0:
        return None
    if metric == "roc_auc":
        if frame[TARGET].nunique() < 2:
            return None
        return float(roc_auc_score(frame[TARGET].astype(int), probability))
    if metric == "pr_auc":
        if frame[TARGET].nunique() < 2:
            return None
        return float(average_precision_score(frame[TARGET].astype(int), probability))
    if metric == "top10_success":
        top = top_mask_by_group(frame, probability, top_group_cols)
        return float(frame.loc[top, TARGET].astype(int).mean()) if top.any() else None
    if metric == "top10_net_mean":
        top = top_mask_by_group(frame, probability, top_group_cols)
        return float(frame.loc[top, NET_RETURN].astype(float).mean()) if top.any() else None
    if metric == "asset_balanced_auc":
        return asset_balanced_auc(frame, probability)
    if metric == "non_overlap_auc":
        temp = frame.reset_index(drop=True).copy()
        temp["_p_metric"] = probability
        if "_non_overlap_flag" in temp:
            no = temp[temp["_non_overlap_flag"]].copy()
        else:
            no = non_overlap_sample(temp)
        if len(no) == 0 or no[TARGET].nunique() < 2:
            return None
        return float(roc_auc_score(no[TARGET].astype(int), no["_p_metric"]))
    if metric == "long_auc":
        mask = frame["side"] == "long"
        return stratum_auc(frame, probability, mask)
    if metric == "short_auc":
        mask = frame["side"] == "short"
        return stratum_auc(frame, probability, mask)
    raise ValueError(metric)


def paired_comparisons(
    frame: pd.DataFrame,
    candidates: dict[str, list[str]],
    *,
    period: str,
    probability_suffix: str,
    top_group_cols: list[str] | None,
    period_col_for_draws: str | None = None,
) -> tuple[pd.DataFrame, str]:
    frame = frame.reset_index(drop=True).copy()
    frame["_non_overlap_flag"] = False
    frame.loc[non_overlap_sample(frame).index, "_non_overlap_flag"] = True
    metrics = [
        "roc_auc",
        "pr_auc",
        "top10_success",
        "top10_net_mean",
        "asset_balanced_auc",
        "non_overlap_auc",
        "long_auc",
        "short_auc",
    ]
    draws_by_period, draw_hash = make_block_draws(frame, period_col=period_col_for_draws)
    period_keys = sorted(draws_by_period)
    sampled_indices_by_draw = [
        np.concatenate([draws_by_period[key][draw_index] for key in period_keys])
        for draw_index in range(BOOTSTRAP_SAMPLES)
    ]
    rows: list[dict[str, Any]] = []
    p_values: dict[str, float | None] = {}
    base_col = f"R_B0_69_{probability_suffix}"
    challengers = [c for c in candidates if c != "R_B0_69"]
    points: dict[str, dict[str, float | None]] = {}
    distributions: dict[str, dict[str, list[float]]] = {
        challenger: {metric: [] for metric in metrics} for challenger in challengers
    }
    base_probability = frame[base_col].to_numpy()
    base_point_scores = {
        metric: _score_metric(frame, base_probability, metric, top_group_cols=top_group_cols)
        for metric in metrics
    }
    for challenger in challengers:
        ch_col = f"{challenger}_{probability_suffix}"
        points[challenger] = {}
        for metric in metrics:
            c = _score_metric(frame, frame[ch_col].to_numpy(), metric, top_group_cols=top_group_cols)
            b = base_point_scores[metric]
            points[challenger][metric] = None if b is None or c is None else c - b

    for sampled_indices in sampled_indices_by_draw:
        sample = frame.loc[sampled_indices].reset_index(drop=True)
        base_p = sample[base_col].to_numpy()
        base_scores = {
            metric: _score_metric(sample, base_p, metric, top_group_cols=top_group_cols)
            for metric in metrics
        }
        for challenger in challengers:
            ch_p = sample[f"{challenger}_{probability_suffix}"].to_numpy()
            for metric in metrics:
                c = _score_metric(sample, ch_p, metric, top_group_cols=top_group_cols)
                b = base_scores[metric]
                if b is not None and c is not None and math.isfinite(c - b):
                    distributions[challenger][metric].append(float(c - b))

    for challenger in challengers:
        row: dict[str, Any] = {
            "period": period,
            "candidate": challenger,
            "baseline": "R_B0_69",
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "block_days": BOOTSTRAP_BLOCK_DAYS,
            "draw_hash": draw_hash,
            "bootstrap_method_note": "shared 28d block resampling; every nonlinear metric recomputed on each full resampled paired-event draw",
            "bootstrap_period_stratification": period_col_for_draws or "none",
        }
        for metric in metrics:
            vals = np.asarray(distributions[challenger][metric], dtype=float)
            diff = points[challenger][metric]
            row[f"{metric}_diff"] = diff
            row[f"{metric}_diff_ci_low"] = float(np.quantile(vals, 0.025)) if len(vals) else None
            row[f"{metric}_diff_ci_high"] = float(np.quantile(vals, 0.975)) if len(vals) else None
            if metric == "roc_auc":
                if len(vals) and diff is not None:
                    p_values[challenger] = float(2.0 * min((vals <= 0).mean(), (vals >= 0).mean()))
                else:
                    p_values[challenger] = None
        rows.append(row)
    q_values = P4.bh_q_values(p_values)
    for row in rows:
        row["auc_diff_p_value_two_sided_bootstrap"] = p_values.get(row["candidate"])
        row["auc_diff_bh_q_value"] = q_values.get(row["candidate"])
    return pd.DataFrame(rows), draw_hash


def adjudicate(
    development_aggregate: dict[str, Any],
    strata: pd.DataFrame,
    comparisons: pd.DataFrame,
    data_audit: dict[str, Any],
) -> dict[str, Any]:
    if data_audit["strict_sample"]["strict_hype_rows"] or data_audit["strict_sample"]["validation_hype_rows"]:
        return {"global_verdict": "HOLDOUT_CONTAMINATED", "candidate_verdicts": {}}
    if data_audit["new_features"]["weekly_causality"]["weekly_feature_known_at_gt_feature_known_at"] != 0:
        return {"global_verdict": "WEEKLY_LOOKAHEAD_CONTAMINATION", "candidate_verdicts": {}}
    if not data_audit["strict_sample"]["p4_strict_sample_reproduced"]:
        return {"global_verdict": "DATA_BLOCK_NOT_READY", "candidate_verdicts": {}}

    def val_row(candidate: str, scope: str) -> pd.Series | None:
        rows = strata[(strata["period"] == "validation_2025_plus") & (strata["candidate"] == candidate) & (strata["scope"] == scope)]
        return rows.iloc[0] if len(rows) else None

    def comp_row(candidate: str, period: str) -> pd.Series | None:
        rows = comparisons[(comparisons["period"] == period) & (comparisons["candidate"] == candidate)]
        return rows.iloc[0] if len(rows) else None

    verdicts: dict[str, str] = {"R_B0_69": "NO_NEW_INCREMENT_B0_REMAINS_REFERENCE"}
    for candidate in [c for c in development_aggregate if c != "R_B0_69"]:
        dev = comp_row(candidate, "development_oof")
        val = comp_row(candidate, "validation_2025_plus")
        y2025 = val_row(candidate, "year:2025")
        y2026 = val_row(candidate, "year:2026")
        b2025 = val_row("R_B0_69", "year:2025")
        b2026 = val_row("R_B0_69", "year:2026")
        long_row = val_row(candidate, "side:long")
        short_row = val_row(candidate, "side:short")
        no_row = val_row(candidate, "non_overlap_20d")
        seen_row = val_row(candidate, "seen_asset")
        new_row = val_row(candidate, "new_asset")
        b_long = val_row("R_B0_69", "side:long")
        b_short = val_row("R_B0_69", "side:short")
        b_no = val_row("R_B0_69", "non_overlap_20d")

        confirmed = False
        if dev is not None and val is not None and y2025 is not None and y2026 is not None:
            macro_gap = development_aggregate[candidate]["macro_auc"] - development_aggregate["R_B0_69"]["macro_auc"]
            long_gap = None if long_row is None or b_long is None else long_row["roc_auc"] - b_long["roc_auc"]
            short_gap = None if short_row is None or b_short is None else short_row["roc_auc"] - b_short["roc_auc"]
            no_gap = None if no_row is None or b_no is None else no_row["roc_auc"] - b_no["roc_auc"]
            seen_ok = seen_row is None or seen_row["roc_auc"] is None or seen_row["roc_auc"] >= 0.49
            new_ok = new_row is None or new_row["roc_auc"] is None or new_row["roc_auc"] >= 0.49
            confirmed = (
                macro_gap >= -0.003
                and val["auc_diff_bh_q_value"] is not None
                and val["auc_diff_bh_q_value"] <= 0.05
                and val["roc_auc_diff_ci_low"] is not None
                and val["roc_auc_diff_ci_low"] > 0
                and val["top10_success_diff_ci_low"] is not None
                and val["top10_success_diff_ci_low"] >= 0
                and y2025["roc_auc"] is not None
                and y2026["roc_auc"] is not None
                and y2025["roc_auc"] > 0.50
                and y2026["roc_auc"] > 0.50
                and long_gap is not None
                and short_gap is not None
                and long_gap >= -0.01
                and short_gap >= -0.01
                and no_gap is not None
                and no_gap >= -0.005
                and seen_ok
                and new_ok
            )
        tail = False
        if val is not None and y2025 is not None and y2026 is not None and b2025 is not None and b2026 is not None:
            long_gap = None if long_row is None or b_long is None else long_row["roc_auc"] - b_long["roc_auc"]
            short_gap = None if short_row is None or b_short is None else short_row["roc_auc"] - b_short["roc_auc"]
            no_gap = None if no_row is None or b_no is None else no_row["roc_auc"] - b_no["roc_auc"]
            tail = (
                val["top10_success_diff_ci_low"] is not None
                and val["top10_success_diff_ci_low"] > 0
                and val["top10_net_mean_diff_ci_low"] is not None
                and val["top10_net_mean_diff_ci_low"] >= -0.002
                and val["roc_auc_diff_ci_low"] is not None
                and val["roc_auc_diff_ci_low"] >= -0.005
                and y2025["top10_success_rate"] is not None
                and b2025["top10_success_rate"] is not None
                and y2026["top10_success_rate"] is not None
                and b2026["top10_success_rate"] is not None
                and y2025["top10_success_rate"] >= b2025["top10_success_rate"]
                and y2026["top10_success_rate"] >= b2026["top10_success_rate"]
                and long_gap is not None
                and short_gap is not None
                and long_gap >= -0.01
                and short_gap >= -0.01
                and no_gap is not None
                and no_gap >= -0.005
            )
        if confirmed:
            verdicts[candidate] = "VALIDATION_CONFIRMED_INCREMENT"
        elif tail:
            verdicts[candidate] = "TAIL_SPECIALIST_VALIDATED"
        elif dev is not None and val is not None and (dev["roc_auc_diff"] or 0) > 0 and (val["roc_auc_diff"] or 0) <= 0:
            verdicts[candidate] = "DEVELOPMENT_ONLY_NOT_REPLICATED"
        else:
            verdicts[candidate] = "NO_NEW_INCREMENT_B0_REMAINS_REFERENCE"
    if any(v == "VALIDATION_CONFIRMED_INCREMENT" for v in verdicts.values()):
        global_verdict = "VALIDATION_CONFIRMED_INCREMENT"
    elif any(v == "TAIL_SPECIALIST_VALIDATED" for v in verdicts.values()):
        global_verdict = "TAIL_SPECIALIST_VALIDATED"
    else:
        global_verdict = "NO_NEW_INCREMENT_B0_REMAINS_REFERENCE"
    return {"global_verdict": global_verdict, "candidate_verdicts": verdicts}


def fmt(x: Any, digits: int = 4) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "NA"
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    return f"{float(x):.{digits}f}"


def row_lookup(strata: pd.DataFrame, period: str, scope: str, candidate: str) -> dict[str, Any]:
    rows = strata[(strata["period"] == period) & (strata["scope"] == scope) & (strata["candidate"] == candidate)]
    return rows.iloc[0].to_dict() if len(rows) else {}


def comparison_lookup(comparisons: pd.DataFrame, period: str, candidate: str) -> dict[str, Any]:
    rows = comparisons[(comparisons["period"] == period) & (comparisons["candidate"] == candidate)]
    return rows.iloc[0].to_dict() if len(rows) else {}


def candidate_table(strata: pd.DataFrame, comparisons: pd.DataFrame, verdicts: dict[str, str]) -> str:
    lines = [
        "| Candidate | Dev Macro AUC/Top10 | 2025+ AUC/Top10 | 2025 | 2026 | vs B0 AUC CI | vs B0 Top10 CI | Verdict |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for candidate in candidate_definitions():
        dev = row_lookup(strata, "development", "pooled_fold_relative", candidate)
        val = row_lookup(strata, "validation_2025_plus", "year_relative_top10", candidate)
        y2025 = row_lookup(strata, "validation_2025_plus", "year:2025", candidate)
        y2026 = row_lookup(strata, "validation_2025_plus", "year:2026", candidate)
        comp = comparison_lookup(comparisons, "validation_2025_plus", candidate)
        auc_ci = "ref" if candidate == "R_B0_69" else f"{fmt(comp.get('roc_auc_diff_ci_low'))}/{fmt(comp.get('roc_auc_diff_ci_high'))}"
        top_ci = (
            "ref"
            if candidate == "R_B0_69"
            else f"{fmt(comp.get('top10_success_diff_ci_low'))}/{fmt(comp.get('top10_success_diff_ci_high'))}"
        )
        lines.append(
            f"| `{candidate}` | {fmt(dev.get('roc_auc'))}/{fmt(dev.get('top10_success_rate'))} | "
            f"{fmt(val.get('roc_auc'))}/{fmt(val.get('top10_success_rate'))} | "
            f"{fmt(y2025.get('roc_auc'))}/{fmt(y2025.get('top10_success_rate'))} | "
            f"{fmt(y2026.get('roc_auc'))}/{fmt(y2026.get('top10_success_rate'))} | "
            f"{auc_ci} | {top_ci} | `{verdicts.get(candidate, 'NA')}` |"
        )
    return "\n".join(lines)


def write_reports(summary: dict[str, Any], strata: pd.DataFrame, comparisons: pd.DataFrame, data_audit: dict[str, Any]) -> None:
    verdicts = summary["adjudication"]["candidate_verdicts"]
    table = candidate_table(strata, comparisons, verdicts)
    strict = data_audit["strict_sample"]
    weekly = data_audit["new_features"]["weekly_causality"]
    validation_reuse = summary["validation_reuse_history"]
    g3 = comparison_lookup(comparisons, "validation_2025_plus", "C_NO_G3_58")
    rsi = comparison_lookup(comparisons, "validation_2025_plus", "C_B0_PLUS_RSI_79")
    weekly_comp = comparison_lookup(comparisons, "validation_2025_plus", "C_B0_PLUS_WEEKLY_80")
    main = f"""# BIN-1D-MA7-CTP P5 RSI6、完整周线趋势增量与2025+验证审计

- 状态：`{STATUS}`
- 全局裁决：`{summary['adjudication']['global_verdict']}`
- 研究问题：严格 MA7 方向穿越后，从下一 UTC 日 open 开始，未来 20 日是否先触及顺向 `+2 ATR` 而非逆向 `-1 ATR`。
- 2025+ 数据角色：`ITERATIVE_REUSED_VALIDATION_2025_PLUS`；P1 已观察过，不是最终盲测；P5 仅用于预注册候选的迭代验证，不参与训练、校准或阈值拟合。

## 数据切分

- 开发集复现 P4 严格样本：{strict['strict_rows']} 事件，{strict['strict_assets']} 资产，long/short {strict['strict_long']}/{strict['strict_short']}，日期 {strict['strict_min_ts']} 至 {strict['strict_max_ts']}，最大标签结束 {strict['strict_max_label_end']}。
- HYPE：开发集 {strict['strict_hype_rows']} 行，2025+ 验证 {strict['validation_hype_rows']} 行；HYPE 原始 price 分区未读取。
- 2025+ 总事件 {strict['validation_rows_total']}，其中主加密验证 {strict['validation_rows_main_crypto']}，known TradFi 排除 {strict['validation_known_tradfi_rows']}。
- 2025+ 分年主加密事件：{strict['validation_year_counts_main_crypto']}。

## 候选表现

{table}

## 主要增量结论

- `C_NO_G3_58` 验证期 AUC diff CI：{fmt(g3.get('roc_auc_diff_ci_low'))} 至 {fmt(g3.get('roc_auc_diff_ci_high'))}；Top10 success diff CI：{fmt(g3.get('top10_success_diff_ci_low'))} 至 {fmt(g3.get('top10_success_diff_ci_high'))}。G3 删除假设裁决：`{verdicts.get('C_NO_G3_58')}`。
- `G7_RSI6_OSCILLATOR` 单独增量候选 `C_B0_PLUS_RSI_79` 验证期 AUC diff CI：{fmt(rsi.get('roc_auc_diff_ci_low'))} 至 {fmt(rsi.get('roc_auc_diff_ci_high'))}；Top10 diff CI：{fmt(rsi.get('top10_success_diff_ci_low'))} 至 {fmt(rsi.get('top10_success_diff_ci_high'))}。
- `G8_COMPLETED_WEEKLY_REGIME` 单独增量候选 `C_B0_PLUS_WEEKLY_80` 验证期 AUC diff CI：{fmt(weekly_comp.get('roc_auc_diff_ci_low'))} 至 {fmt(weekly_comp.get('roc_auc_diff_ci_high'))}；Top10 diff CI：{fmt(weekly_comp.get('top10_success_diff_ci_low'))} 至 {fmt(weekly_comp.get('top10_success_diff_ci_high'))}。
- 本轮仍只评估弱排序器；未生成策略、权益曲线、Sharpe、live spec、runner handoff、交易路径 HTML 或 HYPE reveal。

## 证据文件

- [feature spec](../artifacts/binance_1d_ma7_ctp_p5_feature_spec.json)
- [data audit](../artifacts/binance_1d_ma7_ctp_p5_data_audit.json)
- [fold metrics](../artifacts/binance_1d_ma7_ctp_p5_fold_metrics.parquet)
- [pre-2025 OOF predictions](../artifacts/binance_1d_ma7_ctp_p5_pre2025_oof_predictions.parquet)
- [2025+ validation predictions](../artifacts/binance_1d_ma7_ctp_p5_validation_2025_plus_predictions.parquet)
- [paired comparisons](../artifacts/binance_1d_ma7_ctp_p5_paired_comparisons.parquet)
- [strata](../artifacts/binance_1d_ma7_ctp_p5_strata.parquet)
- [summary](../artifacts/binance_1d_ma7_ctp_p5_summary.json)

## 下一步

若本轮未出现可复现的线性增量，应停止在同一线性候选空间继续微调；若存在稳定尾部改善但整体 AUC 仍弱，可把结论限定为非线性建模候选输入，而不是 promotion 或策略登记。
"""
    modeling = f"""# BIN-1D-MA7-CTP P5 Modeling Audit

- 裁决：`{summary['adjudication']['global_verdict']}`
- 模型：pooled direction-aligned `LogisticRegression(penalty="l2", solver="lbfgs", max_iter=1000, random_state=20260901)`。
- 候选：六个预注册候选；无 LightGBM/XGBoost/RandomForest/ExtraTrees/神经网络、L1/ElasticNet、自动特征选择、超参搜索、多空独立模型或临时交互项。
- 训练/预处理隔离：D1-D3 使用训练折拟合填充、编码、Scaler 与模型；2025+ 没有参与训练、预处理、校准或阈值拟合。
- 最终外层验证：模型用全部严格 pre-2025 重训；Platt 校准器和 frozen threshold 仅来自 pre-2025 OOF。
- Bootstrap：开发期与 2025+ 分开使用 28 日 UTC 日期块、{BOOTSTRAP_SAMPLES} 次、固定种子 `{SEED}`；同一 period 内所有挑战者共享 draws，每次在完整重采样事件集上重新计算非线性指标。
- 2025+ 验证复用历史：{validation_reuse}
- Known TradFi：主统计排除，单独标记 `unsupported_tradfi_diagnostic`；排除事件 {strict['validation_known_tradfi_rows']}。
- HYPE：原始 price 分区读取为 `false`，OOF/验证/指标均为 0 行；`HYPER/USDT:USDT` 保留。
"""
    weekly_report = f"""# BIN-1D-MA7-CTP P5 Weekly Causality Audit

- 裁决：`{weekly['verdict']}`
- 周期定义：UTC Monday 00:00 至下一 Monday 00:00，仅 7 个完整日 K 组成的闭合周可用。
- As-of 规则：日线事件使用最近一个 `weekly_feature_known_at <= feature_known_at` 的完整闭合周。
- 事件行：{weekly['events']}
- 周线特征行：{weekly['weekly_rows']}
- `weekly_feature_known_at < feature_known_at`：{weekly['weekly_feature_known_at_lt_feature_known_at']}
- `weekly_feature_known_at == feature_known_at`：{weekly['weekly_feature_known_at_eq_feature_known_at']}
- `weekly_feature_known_at > feature_known_at`：{weekly['weekly_feature_known_at_gt_feature_known_at']}
- 缺失周线 known-at 行：{weekly['weekly_feature_known_at_missing_rows']}
- 缺失处理：数值特征不删除 MA7 事件，由训练折中位数填充；`weekly_history_13w_complete` 保留 0/1 完整性标记。
"""
    atomic_write_text(REPORT_PATH, main)
    atomic_write_text(MODELING_AUDIT_PATH, modeling)
    atomic_write_text(WEEKLY_AUDIT_PATH, weekly_report)


def build_manifest(paths: Iterable[Path]) -> None:
    artifacts = []
    for path in paths:
        if path.exists() and path != MANIFEST_PATH:
            artifacts.append({"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    atomic_write_json(
        MANIFEST_PATH,
        {
            "family": "Binance-1D-MA7-Cross-Trend-Probability",
            "alias": "BIN-1D-MA7-CTP",
            "experiment": "P5",
            "created_utc": datetime.now(UTC).isoformat(),
            "artifacts": artifacts,
            "manifest_sha256_canonical_payload": canonical_sha256(artifacts),
        },
    )


def output_paths() -> list[Path]:
    return [
        FEATURE_SPEC_PATH,
        CONTRACT_LOCK_PATH,
        DATA_AUDIT_PATH,
        FOLD_METRICS_PATH,
        OOF_PREDICTIONS_PATH,
        VALIDATION_PREDICTIONS_PATH,
        PAIRED_COMPARISONS_PATH,
        STRATA_PATH,
        CALIBRATION_PATH,
        MODEL_CARD_PATH,
        SUMMARY_PATH,
        REPORT_PATH,
        MODELING_AUDIT_PATH,
        WEEKLY_AUDIT_PATH,
        MANIFEST_PATH,
    ]


def ensure_output_policy(force: bool) -> None:
    existing = [path for path in output_paths() if path.exists()]
    if existing and not force:
        rel = ", ".join(str(path.relative_to(ROOT)) for path in existing[:5])
        raise RuntimeError(f"P5 outputs already exist; rerun with --force to replace P5-only files: {rel}")


def run(force: bool) -> dict[str, Any]:
    ensure_output_policy(force)
    feature_spec = build_feature_spec()
    write_contract_lock(feature_spec, force=True)

    candidates = {name: spec["features"] for name, spec in feature_spec["candidates"].items()}
    donor_assets = read_donor_asset_slugs()
    development_base, validation_base, strict_audit = prepare_event_panel(feature_spec)
    prices, price_audit = load_price_panel(donor_assets)
    rsi_daily = build_rsi_daily(prices)
    weekly = build_weekly_features(prices)
    all_events = pd.concat([development_base, validation_base], ignore_index=True)
    all_featured, feature_audit = add_new_features(all_events, rsi_daily, weekly)
    development = all_featured[all_featured["ts"] < CUTOFF].copy()
    validation = all_featured[all_featured["ts"] >= CUTOFF].copy()
    validation_main = validation[~validation["is_known_tradfi"]].copy()

    seen_assets = set(development["asset"].unique())
    strict_audit["validation_seen_asset_rows_main_crypto"] = int(validation_main["asset"].isin(seen_assets).sum())
    strict_audit["validation_new_asset_rows_main_crypto"] = int((~validation_main["asset"].isin(seen_assets)).sum())

    fold_metrics, oof, development_aggregate = run_development(development, candidates)
    validation_pred, calibration = fit_final_validation(development, validation, oof, candidates)
    strata, daily_summary = build_strata(oof, validation_pred, candidates, calibration)

    dev_comp, dev_draw_hash = paired_comparisons(
        oof,
        candidates,
        period="development_oof",
        probability_suffix="raw_probability",
        top_group_cols=["fold"],
        period_col_for_draws="fold",
    )
    val_main = validation_pred[validation_pred["validation_role"] == "main_crypto_validation"].copy()
    val_comp, val_draw_hash = paired_comparisons(
        val_main,
        candidates,
        period="validation_2025_plus",
        probability_suffix="raw_probability",
        top_group_cols=["event_year"],
        period_col_for_draws=None,
    )
    comparisons = pd.concat([dev_comp, val_comp], ignore_index=True)

    data_audit = {
        "contract_lock_status": LOCK_STATUS,
        "strict_sample": strict_audit,
        "price_panel": price_audit,
        "new_features": feature_audit,
        "feature_missing_rate_development": {
            feature: float(development[feature].isna().mean()) for feature in G7_RSI6 + G8_WEEKLY
        },
        "feature_missing_rate_validation_main_crypto": {
            feature: float(validation_main[feature].isna().mean()) if len(validation_main) else None
            for feature in G7_RSI6 + G8_WEEKLY
        },
        "tradfi_policy": {
            "known_tradfi_base_symbols": sorted(KNOWN_TRADFI_BASE_SYMBOLS),
            "excluded_from_main_training_and_validation_statistics": True,
        },
    }
    adjudication = adjudicate(development_aggregate, strata, comparisons, data_audit)
    summary = {
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "alias": "BIN-1D-MA7-CTP",
        "experiment": "P5 Oscillator + Completed-Weekly-Regime Increment and 2025+ Validation Audit",
        "status": STATUS,
        "created_utc": datetime.now(UTC).isoformat(),
        "validation_reuse_history": [
            "P1 已读取/观察 2025+ donor terminal history；P5 将其正式标记为 ITERATIVE_REUSED_VALIDATION_2025_PLUS。",
            "P5 不使用 2025+ 训练模型、预处理器、校准器或阈值，只用于六个预注册候选的迭代验证比较。",
        ],
        "candidate_feature_counts": {candidate: len(features) for candidate, features in candidates.items()},
        "development_aggregate": development_aggregate,
        "daily_validation_distribution": daily_summary,
        "bootstrap_draw_hashes": {"development_oof": dev_draw_hash, "validation_2025_plus": val_draw_hash},
        "adjudication": adjudication,
        "hype_isolation": {
            "hype_asset": HYPE_ASSET,
            "hype_raw_file_read": False,
            "hype_rows_read": strict_audit["strict_hype_rows"] + strict_audit["validation_hype_rows"],
            "hyper_retained": price_audit["hyper_rows_read"] > 0,
        },
        "next_step_policy": "若无线性验证增量，停止同一线性空间微调；若仅尾部改善，最多进入非线性建模候选输入，不进入 promotion。",
    }

    atomic_write_json(DATA_AUDIT_PATH, data_audit)
    atomic_write_parquet(FOLD_METRICS_PATH, fold_metrics)
    atomic_write_parquet(OOF_PREDICTIONS_PATH, oof)
    atomic_write_parquet(VALIDATION_PREDICTIONS_PATH, validation_pred)
    atomic_write_parquet(PAIRED_COMPARISONS_PATH, comparisons)
    atomic_write_parquet(STRATA_PATH, strata)
    atomic_write_json(CALIBRATION_PATH, calibration)
    atomic_write_json(
        MODEL_CARD_PATH,
        {
            "family": summary["family"],
            "alias": summary["alias"],
            "experiment": "P5",
            "status": STATUS,
            "head": HEAD,
            "model": "LogisticRegression(penalty='l2', solver='lbfgs', max_iter=1000, random_state=20260901)",
            "preprocessing": "train-fold median imputation, train-fold one-hot, train-fold StandardScaler",
            "candidate_feature_counts": summary["candidate_feature_counts"],
            "training_scope": "strict pre-2025 for final validation models",
            "calibration_scope": "pre-2025 D1-D3 OOF only",
            "validation_scope": "ITERATIVE_REUSED_VALIDATION_2025_PLUS, main crypto excludes known TradFi",
            "forbidden_outputs": ["strategy", "equity_curve", "sharpe", "live_spec", "runner_handoff", "trade_path_html", "hype_reveal"],
        },
    )
    atomic_write_json(SUMMARY_PATH, summary)
    write_reports(summary, strata, comparisons, data_audit)
    build_manifest(
        [
            SPEC_PATH,
            SCRIPT_PATH,
            TEST_PATH,
            P4_FACTOR_GROUP_SPEC_PATH,
            P4_SUMMARY_PATH,
            P4_MODEL_CARD_PATH,
            P0R_FEATURE_BLOCKS_PATH,
            P0R_MANIFEST_PATH,
            P0_MANIFEST_PATH,
            INDEPENDENT_ACCEPTANCE_AUDIT_PATH,
        ]
        + output_paths()
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="replace P5-only outputs")
    args = parser.parse_args()
    summary = run(force=args.force)
    print(json.dumps(json_ready({"verdict": summary["adjudication"]["global_verdict"], "summary": str(SUMMARY_PATH)}), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
