#!/usr/bin/env python3
"""Run BIN-1D-MA7-CTP P6 market-regime x side conditional ranking audit."""

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

SPEC_PATH = FAMILY_DIR / "specs/binance-1d-ma7-ctp-p6-market-regime-side-conditional-ranking-contract-2026-09-03.md"
SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p6_market_regime_side_conditional_ranking.py"
TEST_PATH = ROOT / "tests/test_binance_1d_ma7_ctp_p6_market_regime_side_conditional_ranking.py"
P5_SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py"
P4_FACTOR_GROUP_SPEC_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p4_factor_group_spec.json"
P5_MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_manifest.json"
P5_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_summary.json"
P5_ACCEPTANCE_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p5-independent-acceptance-audit-2026-09-02.md"
P5_OOF_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_pre2025_oof_predictions.parquet"
P5_VALIDATION_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_validation_2025_plus_predictions.parquet"
P0R_PANEL_DIR = CATL_DIR / "artifacts/p0r_donor_directional_modeling_panel"
P0R_PANEL_GLOB = P0R_PANEL_DIR / "**/*.parquet"
P0R_MANIFEST_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_manifest.json"
P0_MANIFEST_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0_manifest.json"
DATA_LAKE_SPEC_PATH = ROOT / "docs/data-lake-spec.md"

PREFIX = "binance_1d_ma7_ctp_p6_"
CONFIG_PATH = ARTIFACT_DIR / f"{PREFIX}config.json"
CONTRACT_LOCK_PATH = ARTIFACT_DIR / f"{PREFIX}contract_lock.json"
EXPOSURE_LEDGER_PATH = ARTIFACT_DIR / f"{PREFIX}exposure_ledger.json"
DATA_AUDIT_PATH = ARTIFACT_DIR / f"{PREFIX}data_audit.json"
B0_REPRODUCTION_PATH = ARTIFACT_DIR / f"{PREFIX}b0_reproduction_audit.json"
FOLD_STAGE_METRICS_PATH = ARTIFACT_DIR / f"{PREFIX}fold_stage_metrics.parquet"
PREDICTIONS_PATH = ARTIFACT_DIR / f"{PREFIX}predictions.parquet"
MARKET_STATE_METRICS_PATH = ARTIFACT_DIR / f"{PREFIX}market_state_metrics.parquet"
SELECTION_METRICS_PATH = ARTIFACT_DIR / f"{PREFIX}selection_metrics.parquet"
PAIRED_STATS_PATH = ARTIFACT_DIR / f"{PREFIX}paired_bootstrap_stats.parquet"
CONCENTRATION_PATH = ARTIFACT_DIR / f"{PREFIX}concentration_diagnostics.json"
SUMMARY_PATH = ARTIFACT_DIR / f"{PREFIX}summary.json"
MANIFEST_PATH = ARTIFACT_DIR / f"{PREFIX}manifest.json"
REPORT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p6-market-regime-side-conditional-ranking-2026-09-03.md"
PROSPECTIVE_PROTOCOL_PATH = FAMILY_DIR / "specs/binance-1d-ma7-ctp-p6-prospective-oos-confirmation-protocol-2026-09-03.md"

HYPE_ASSET = "HYPE/USDT:USDT"
HYPER_ASSET = "HYPER/USDT:USDT"
TARGET = "label_entry_success_20d"
LABEL_END = "label_end_ts_20d"
NET_RETURN = "label_entry_net_return"
SEED = 20260901
CUTOFF = pd.Timestamp("2025-01-01T00:00:00Z")
P0_CUTOFF = pd.Timestamp("2026-05-31T00:00:00Z")
STATUS = "explore / diagnostic-only / not promoted / not live-ready"
LOCK_STATUS = "FROZEN_BEFORE_P6_LABEL_METRIC_AND_2025_VALIDATION_REUSE"
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_BLOCK_DAYS = 28
MIN_SAME_DAY_EVENTS = 20
SAME_DAY_TOP_PCT = 0.05
PROB_EPS = 1e-6
GRID_LEVELS = ["MIXED_LONG", "BULL_LONG", "BEAR_LONG", "MIXED_SHORT", "BULL_SHORT", "BEAR_SHORT"]
REFERENCE_GRID = "MIXED_LONG"
MODEL_NAMES = ["R_B0_69", "M0_MARKET_ONLY", "M1_B0_X_SIDE_X_REGIME"]
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


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


P5 = load_module(P5_SCRIPT_PATH, "binance_1d_ma7_ctp_p5_for_p6")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(json.dumps(json_ready(payload), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


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


def output_paths() -> list[Path]:
    return [
        CONFIG_PATH,
        CONTRACT_LOCK_PATH,
        EXPOSURE_LEDGER_PATH,
        DATA_AUDIT_PATH,
        B0_REPRODUCTION_PATH,
        FOLD_STAGE_METRICS_PATH,
        PREDICTIONS_PATH,
        MARKET_STATE_METRICS_PATH,
        SELECTION_METRICS_PATH,
        PAIRED_STATS_PATH,
        CONCENTRATION_PATH,
        SUMMARY_PATH,
        REPORT_PATH,
        PROSPECTIVE_PROTOCOL_PATH,
        MANIFEST_PATH,
    ]


def ensure_output_policy(force: bool) -> None:
    existing = [path for path in output_paths() if path.exists()]
    if existing and not force:
        rel = ", ".join(str(path.relative_to(ROOT)) for path in existing[:5])
        raise RuntimeError(f"P6 outputs already exist; rerun with --force to replace P6-only files: {rel}")


def build_config() -> dict[str, Any]:
    p4_spec = load_json(P4_FACTOR_GROUP_SPEC_PATH)
    b0_features = p4_spec["p2_original_field_order"]
    config = {
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "alias": "BIN-1D-MA7-CTP",
        "experiment": "P6 Market-Regime x Side Conditional Ranking Value Audit",
        "created_utc": datetime.now(UTC).isoformat(),
        "status": STATUS,
        "lock_status": LOCK_STATUS,
        "seed": SEED,
        "event_contract": {
            "market": "Binance USD-M USDT perpetuals",
            "bar": "complete UTC 1d",
            "event": "strict SMA7 directional crossover at daily close",
            "feature_known_at": "ts + 1 day == entry_ts",
            "entry": "next UTC open",
            "atr_period": 14,
            "success_barrier_atr": 2.0,
            "failure_barrier_atr": -1.0,
            "horizon_days": 20,
            "same_hour_double_touch": "adverse first",
            "fee_per_fill": 0.001,
            "slippage_per_fill": 0.0004,
            "leverage": 1.0,
        },
        "market_state": {
            "main_thresholds": {"bull_breadth_gte": 0.60, "bear_breadth_lte": 0.40},
            "robustness_thresholds_registered_only": [{"bull": 0.65, "bear": 0.35}, {"bull": 0.55, "bear": 0.45}],
            "unknown_policy": "BTC or breadth missing -> UNKNOWN; not filled to MIXED",
            "restore_formula": {
                "raw_breadth_long": "dir_market_breadth_ma30_p0r",
                "raw_breadth_short": "1 - dir_market_breadth_ma30_p0r",
                "raw_btc_side_long": "dir_btc_price_side_ma30",
                "raw_btc_side_short": "-dir_btc_price_side_ma30",
            },
        },
        "models": {
            "R_B0_69": {"type": "validated_p5_b0_reference", "feature_count": len(b0_features)},
            "M0_MARKET_ONLY": {"features": "five dummies over six side x regime grids", "model": "L2 LogisticRegression C=1"},
            "M1_B0_X_SIDE_X_REGIME": {
                "features": "standardized B0 logit + five grid dummies + five interactions",
                "model": "L2 LogisticRegression C=1",
                "first_layer_score": "time-forward out-of-sample B0 raw probability",
            },
        },
        "selection_protocols": {
            "annual_global": [0.01, 0.05, 0.10],
            "within_regime": [0.01, 0.05, 0.10],
            "same_day_same_side": {"top_pct": SAME_DAY_TOP_PCT, "min_events": MIN_SAME_DAY_EVENTS},
            "frozen_threshold": {"train_source": "pre-2025 forward OOF raw scores", "quantile": 0.95},
        },
        "bootstrap": {"samples": BOOTSTRAP_SAMPLES, "block_days": BOOTSTRAP_BLOCK_DAYS, "seed": SEED, "full_resample_recompute": True},
        "known_tradfi_base_symbols": sorted(KNOWN_TRADFI_BASE_SYMBOLS),
        "forbidden_outputs": ["strategy", "position", "equity", "annualized_return", "sharpe", "live_spec", "runner_handoff", "trade_path_html", "hype_reveal"],
    }
    if len(b0_features) != 69:
        raise RuntimeError("B0 feature count is not 69")
    return config


def write_lock(config: dict[str, Any]) -> None:
    atomic_write_json(CONFIG_PATH, config)
    lock = {
        "family": config["family"],
        "alias": config["alias"],
        "experiment": "P6",
        "status": LOCK_STATUS,
        "created_utc": datetime.now(UTC).isoformat(),
        "frozen_before": ["p6_label_rate", "p6_auc", "p6_top_metrics", "2025_plus_validation_reuse_metrics"],
        "labels_or_2025_metrics_read_before_lock": False,
        "contract": {"path": str(SPEC_PATH.relative_to(ROOT)), "sha256": sha256_file(SPEC_PATH)},
        "config": {"path": str(CONFIG_PATH.relative_to(ROOT)), "sha256": sha256_file(CONFIG_PATH)},
        "script": {"path": str(SCRIPT_PATH.relative_to(ROOT)), "sha256": sha256_file(SCRIPT_PATH)},
        "p5_manifest": {"path": str(P5_MANIFEST_PATH.relative_to(ROOT)), "sha256": sha256_file(P5_MANIFEST_PATH)},
    }
    atomic_write_json(CONTRACT_LOCK_PATH, lock)


def verify_p5_manifest() -> dict[str, Any]:
    manifest = load_json(P5_MANIFEST_PATH)
    mismatches = []
    critical = {
        str(P5_OOF_PATH.relative_to(ROOT)),
        str(P5_VALIDATION_PATH.relative_to(ROOT)),
        str(P5_SUMMARY_PATH.relative_to(ROOT)),
        str(P5_ACCEPTANCE_PATH.relative_to(ROOT)),
        str(P5_SCRIPT_PATH.relative_to(ROOT)),
        str(P4_FACTOR_GROUP_SPEC_PATH.relative_to(ROOT)),
    }
    critical_mismatches = []
    for item in manifest["artifacts"]:
        path = ROOT / item["path"]
        if not path.exists():
            row = {"path": item["path"], "issue": "missing"}
            mismatches.append(row)
            if item["path"] in critical:
                critical_mismatches.append(row)
        elif sha256_file(path) != item["sha256"]:
            row = {"path": item["path"], "issue": "sha256_mismatch", "expected": item["sha256"], "actual": sha256_file(path)}
            mismatches.append(row)
            if item["path"] in critical:
                critical_mismatches.append(row)
    if critical_mismatches:
        raise RuntimeError(f"P5 critical scientific artifact verification failed: {critical_mismatches[:3]}")
    return {
        "p5_manifest_path": str(P5_MANIFEST_PATH.relative_to(ROOT)),
        "p5_manifest_sha256": sha256_file(P5_MANIFEST_PATH),
        "verified_artifacts": len(manifest["artifacts"]),
        "mismatches": mismatches,
        "all_manifest_entries_match": not mismatches,
        "critical_scientific_artifacts_match": not critical_mismatches,
        "critical_artifacts": sorted(critical),
        "p5_summary_verdict": load_json(P5_SUMMARY_PATH)["adjudication"]["global_verdict"],
        "p5_acceptance_sha256": sha256_file(P5_ACCEPTANCE_PATH),
    }


def load_market_event_fields() -> pd.DataFrame:
    cols = [
        "asset",
        "asset_slug",
        "side",
        "ts",
        "feature_known_at",
        "entry_ts",
        LABEL_END,
        TARGET,
        NET_RETURN,
        "model_eligible_entry_p0r",
        "probe_raw_ma7_cross_dir",
        "future_path_complete_20d",
        "dir_raw_ma7_cross",
        "dir_market_breadth_ma30_p0r",
        "dir_btc_price_side_ma30",
        "pit_universe_size_p0r",
    ]
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    quoted = ", ".join(f'"{c}"' for c in cols)
    df = con.execute(
        f"""
        SELECT {quoted}
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        WHERE asset <> ?
        """,
        [str(P0R_PANEL_GLOB), HYPE_ASSET],
    ).fetchdf()
    for col in ["ts", "feature_known_at", "entry_ts", LABEL_END]:
        df[col] = pd.to_datetime(df[col], utc=True)
    df = df[(df["probe_raw_ma7_cross_dir"]) & (df["model_eligible_entry_p0r"]) & (df["future_path_complete_20d"])].copy()
    df["base_symbol"] = df["asset"].map(base_symbol)
    df["is_known_tradfi"] = df["base_symbol"].isin(KNOWN_TRADFI_BASE_SYMBOLS)
    df["event_year"] = df["ts"].dt.year.astype(int)
    df["side_upper"] = df["side"].str.upper()
    return df


def restore_market_state(events: pd.DataFrame, bull: float = 0.60, bear: float = 0.40) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = events.copy()
    if "side_upper" not in out.columns:
        out["side_upper"] = out["side"].str.upper()
    is_long = out["side"].eq("long")
    out["raw_market_breadth_ma30"] = np.where(is_long, out["dir_market_breadth_ma30_p0r"], 1.0 - out["dir_market_breadth_ma30_p0r"])
    out["raw_btc_price_side_ma30"] = np.where(is_long, out["dir_btc_price_side_ma30"], -out["dir_btc_price_side_ma30"])
    missing = out["raw_market_breadth_ma30"].isna() | out["raw_btc_price_side_ma30"].isna()
    out["market_state"] = "MIXED"
    out.loc[missing, "market_state"] = "UNKNOWN"
    out.loc[(~missing) & (out["raw_market_breadth_ma30"] >= bull) & (out["raw_btc_price_side_ma30"] > 0), "market_state"] = "BULL"
    out.loc[(~missing) & (out["raw_market_breadth_ma30"] <= bear) & (out["raw_btc_price_side_ma30"] < 0), "market_state"] = "BEAR"
    out["six_grid"] = out["market_state"] + "_" + out["side_upper"]
    per_day = out.groupby(["ts", "side"], as_index=False).agg(
        breadth=("raw_market_breadth_ma30", "mean"),
        btc_side=("raw_btc_price_side_ma30", "mean"),
        state=("market_state", lambda x: sorted(set(x))[0] if len(set(x)) == 1 else "MULTI"),
    )
    pivot = per_day.pivot(index="ts", columns="side", values=["breadth", "btc_side", "state"])
    comparable = pivot.dropna()
    breadth_diff = (comparable[("breadth", "long")] - comparable[("breadth", "short")]).abs() if len(comparable) else pd.Series(dtype=float)
    btc_diff = (comparable[("btc_side", "long")] - comparable[("btc_side", "short")]).abs() if len(comparable) else pd.Series(dtype=float)
    state_match = comparable[("state", "long")].eq(comparable[("state", "short")]) if len(comparable) else pd.Series(dtype=bool)
    audit = {
        "rows": int(len(out)),
        "unknown_rows": int(out["market_state"].eq("UNKNOWN").sum()),
        "state_counts": out["six_grid"].value_counts().sort_index().to_dict(),
        "long_short_comparable_days": int(len(comparable)),
        "max_long_short_restored_breadth_abs_diff": float(breadth_diff.max()) if len(breadth_diff) else None,
        "max_long_short_restored_btc_side_abs_diff": float(btc_diff.max()) if len(btc_diff) else None,
        "long_short_state_mismatch_days": int((~state_match).sum()) if len(state_match) else 0,
    }
    if audit["long_short_state_mismatch_days"] != 0 or (audit["max_long_short_restored_breadth_abs_diff"] or 0) > 1e-10:
        raise RuntimeError("market state restoration mismatch between same-day long and short rows")
    return out, audit


def load_base_events_and_predictions(config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    feature_spec = P5.build_feature_spec()
    development_base, validation_base, strict_audit = P5.prepare_event_panel(feature_spec)
    market = load_market_event_fields()
    market_cols = [
        "asset",
        "side",
        "ts",
        "raw_market_breadth_ma30",
        "raw_btc_price_side_ma30",
        "market_state",
        "six_grid",
        "pit_universe_size_p0r",
    ]
    market, market_audit = restore_market_state(market)
    development = development_base.merge(market[market_cols], on=["asset", "side", "ts"], how="left", validate="one_to_one")
    validation = validation_base.merge(market[market_cols], on=["asset", "side", "ts"], how="left", validate="one_to_one")

    oof = pd.read_parquet(P5_OOF_PATH)
    val_pred = pd.read_parquet(P5_VALIDATION_PATH)
    for frame in [oof, val_pred]:
        for col in ["ts", "feature_known_at", "entry_ts", LABEL_END]:
            frame[col] = pd.to_datetime(frame[col], utc=True)
    oof_key = oof[["asset", "side", "ts", "R_B0_69_raw_probability"]].rename(columns={"R_B0_69_raw_probability": "b0_raw_probability"})
    val_key = val_pred[["asset", "side", "ts", "R_B0_69_raw_probability", "validation_role", "asset_generalization"]].rename(
        columns={"R_B0_69_raw_probability": "b0_raw_probability"}
    )
    development_oof = development.merge(oof_key, on=["asset", "side", "ts"], how="inner", validate="one_to_one")
    validation_scored = validation.merge(val_key, on=["asset", "side", "ts"], how="inner", validate="one_to_one")
    validation_main = validation_scored[validation_scored["validation_role"].eq("main_crypto_validation")].copy()
    data_audit = {
        "strict_sample": strict_audit,
        "market_state_restoration": market_audit,
        "development_oof_rows_with_b0": int(len(development_oof)),
        "validation_rows_with_b0_total": int(len(validation_scored)),
        "validation_rows_main_crypto": int(len(validation_main)),
        "validation_known_tradfi_rows": int(validation_scored["is_known_tradfi"].sum()),
        "hype_rows": int((development["asset"].eq(HYPE_ASSET)).sum() + (validation_scored["asset"].eq(HYPE_ASSET)).sum()),
        "hyper_present": bool(development["asset"].eq(HYPER_ASSET).any() or validation_scored["asset"].eq(HYPER_ASSET).any()),
        "b0_feature_count": config["models"]["R_B0_69"]["feature_count"],
    }
    if data_audit["hype_rows"] != 0:
        raise RuntimeError("HYPE rows entered P6")
    return development, validation, data_audit


def logit_probability(p: pd.Series | np.ndarray) -> np.ndarray:
    arr = np.clip(np.asarray(p, dtype=float), PROB_EPS, 1.0 - PROB_EPS)
    return np.log(arr / (1.0 - arr))


def six_grid_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    grid = pd.Categorical(frame["six_grid"], categories=GRID_LEVELS)
    dummies = pd.get_dummies(grid, prefix="grid", dtype=float)
    ref_col = f"grid_{REFERENCE_GRID}"
    if ref_col in dummies:
        dummies = dummies.drop(columns=[ref_col])
    expected = [f"grid_{level}" for level in GRID_LEVELS if level != REFERENCE_GRID]
    for col in expected:
        if col not in dummies:
            dummies[col] = 0.0
    return dummies[expected].reset_index(drop=True)


def fit_m0(train: pd.DataFrame, valid: pd.DataFrame) -> tuple[np.ndarray, dict[str, Any]]:
    x_train = six_grid_matrix(train)
    x_valid = six_grid_matrix(valid)
    model = LogisticRegression(penalty="l2", C=1.0, solver="lbfgs", max_iter=1000, random_state=SEED)
    model.fit(x_train, train[TARGET].astype(int))
    return np.clip(model.predict_proba(x_valid)[:, 1], PROB_EPS, 1.0 - PROB_EPS), {"model": model, "features": x_train.columns.tolist()}


def m1_matrix(frame: pd.DataFrame, scaler: StandardScaler | None = None, fit: bool = False) -> tuple[pd.DataFrame, StandardScaler]:
    b0_logit = logit_probability(frame["b0_raw_probability"])
    if scaler is None:
        scaler = StandardScaler()
    z = scaler.fit_transform(b0_logit.reshape(-1, 1))[:, 0] if fit else scaler.transform(b0_logit.reshape(-1, 1))[:, 0]
    grid = six_grid_matrix(frame)
    x = grid.copy()
    x.insert(0, "b0_logit_z", z)
    for col in grid.columns:
        x[f"b0_logit_z_x_{col}"] = z * grid[col].to_numpy()
    return x, scaler


def fit_m1(train: pd.DataFrame, valid: pd.DataFrame) -> tuple[np.ndarray, dict[str, Any]]:
    x_train, scaler = m1_matrix(train, fit=True)
    x_valid, _ = m1_matrix(valid, scaler=scaler, fit=False)
    model = LogisticRegression(penalty="l2", C=1.0, solver="lbfgs", max_iter=1000, random_state=SEED)
    model.fit(x_train, train[TARGET].astype(int))
    return np.clip(model.predict_proba(x_valid)[:, 1], PROB_EPS, 1.0 - PROB_EPS), {
        "model": model,
        "scaler": scaler,
        "features": x_train.columns.tolist(),
        "coef": dict(zip(x_train.columns, model.coef_[0], strict=True)),
    }


def fold_split(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = frame[frame[LABEL_END] < start].copy()
    valid = frame[(frame["ts"] >= start) & (frame["ts"] < end) & (frame[LABEL_END] < CUTOFF)].copy()
    return train, valid


def generate_inner_b0_oof(train_frame: pd.DataFrame, b0_features: list[str], outer_start: pd.Timestamp) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    rows = []
    stage = []
    years = sorted(train_frame["ts"].dt.year.unique().tolist())
    for year in years:
        start = pd.Timestamp(f"{year}-01-01T00:00:00Z")
        end = pd.Timestamp(f"{year + 1}-01-01T00:00:00Z")
        fit = train_frame[train_frame[LABEL_END] < start].copy()
        valid = train_frame[(train_frame["ts"] >= start) & (train_frame["ts"] < end) & (train_frame[LABEL_END] < outer_start)].copy()
        if len(fit) < 1000 or len(valid) == 0 or fit[TARGET].nunique() < 2:
            stage.append({"inner_year": year, "used": False, "fit_rows": int(len(fit)), "valid_rows": int(len(valid)), "reason": "warmup_or_single_class"})
            continue
        _, valid_raw, _ = P5.fit_logit(fit, valid, b0_features)
        part = valid.copy()
        part["b0_raw_probability"] = valid_raw
        part["inner_year"] = year
        rows.append(part)
        stage.append(
            {
                "inner_year": year,
                "used": True,
                "fit_rows": int(len(fit)),
                "valid_rows": int(len(valid)),
                "fit_max_label_end": fit[LABEL_END].max(),
                "valid_min_ts": valid["ts"].min(),
            }
        )
    if not rows:
        return pd.DataFrame(), stage
    return pd.concat(rows, ignore_index=True), stage


def add_model_predictions(development: pd.DataFrame, validation: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    b0_features = load_json(P4_FACTOR_GROUP_SPEC_PATH)["p2_original_field_order"]
    p5_oof = pd.read_parquet(P5_OOF_PATH)
    p5_val = pd.read_parquet(P5_VALIDATION_PATH)
    for frame in [p5_oof, p5_val]:
        for col in ["ts", LABEL_END]:
            if col in frame:
                frame[col] = pd.to_datetime(frame[col], utc=True)
    base_cols = [
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
        "market_state",
        "six_grid",
        "raw_market_breadth_ma30",
        "raw_btc_price_side_ma30",
    ]
    oof_key = p5_oof[["asset", "side", "ts", "fold", "R_B0_69_raw_probability"]].rename(columns={"R_B0_69_raw_probability": "b0_raw_probability"})
    dev_pred = development.merge(oof_key, on=["asset", "side", "ts"], how="inner", validate="one_to_one")
    dev_pred = dev_pred[base_cols + ["fold", "b0_raw_probability"]].copy()
    dev_pred["period"] = "development_oof"
    dev_pred["R_B0_69_score"] = dev_pred["b0_raw_probability"]
    stage_rows: list[dict[str, Any]] = []
    for fold_name, start, end in P5.FOLDS:
        train, valid = fold_split(development, start, end)
        valid_idx = dev_pred["fold"].eq(fold_name)
        m0_pred, _ = fit_m0(train, dev_pred.loc[valid_idx])
        dev_pred.loc[valid_idx, "M0_MARKET_ONLY_score"] = m0_pred
        inner, stages = generate_inner_b0_oof(train, b0_features, start)
        for row in stages:
            stage_rows.append({"outer_fold": fold_name, **row})
        if len(inner) >= 1000 and inner[TARGET].nunique() >= 2:
            m1_pred, _ = fit_m1(inner, dev_pred.loc[valid_idx])
            dev_pred.loc[valid_idx, "M1_B0_X_SIDE_X_REGIME_score"] = m1_pred
            stage_rows.append(
                {
                    "outer_fold": fold_name,
                    "stage": "m1_train",
                    "used": True,
                    "fit_rows": int(len(inner)),
                    "fit_max_label_end": inner[LABEL_END].max(),
                    "valid_rows": int(valid_idx.sum()),
                }
            )
        else:
            dev_pred.loc[valid_idx, "M1_B0_X_SIDE_X_REGIME_score"] = np.nan
            stage_rows.append(
                {"outer_fold": fold_name, "stage": "m1_train", "used": False, "fit_rows": int(len(inner)), "reason": "insufficient_inner_oof"}
            )

    val_key = p5_val[["asset", "side", "ts", "R_B0_69_raw_probability", "validation_role", "asset_generalization"]].rename(
        columns={"R_B0_69_raw_probability": "b0_raw_probability"}
    )
    val_pred = validation.merge(val_key, on=["asset", "side", "ts"], how="inner", validate="one_to_one")
    val_pred = val_pred[val_pred["validation_role"].eq("main_crypto_validation")].copy()
    val_pred = val_pred[base_cols + ["b0_raw_probability", "validation_role", "asset_generalization"]].copy()
    val_pred["fold"] = np.where(val_pred["event_year"].eq(2025), "V2025", "V2026")
    val_pred["period"] = "validation_2025_plus"
    val_pred["R_B0_69_score"] = val_pred["b0_raw_probability"]
    m0_val, _ = fit_m0(development, val_pred)
    val_pred["M0_MARKET_ONLY_score"] = m0_val
    m1_train = dev_pred.dropna(subset=["M1_B0_X_SIDE_X_REGIME_score"]).copy()
    # The final M1 fit uses the first-layer B0 OOF score itself, not the previous M1 prediction.
    m1_val, m1_bundle = fit_m1(dev_pred, val_pred)
    val_pred["M1_B0_X_SIDE_X_REGIME_score"] = m1_val
    stage_rows.append(
        {
            "outer_fold": "V2025_PLUS",
            "stage": "final_m1_train",
            "used": True,
            "fit_rows": int(len(dev_pred)),
            "fit_max_label_end": dev_pred[LABEL_END].max(),
            "valid_rows": int(len(val_pred)),
            "feature_count": len(m1_bundle["features"]),
        }
    )
    stage_df = pd.DataFrame(stage_rows)
    predictions = pd.concat([dev_pred, val_pred], ignore_index=True)
    predictions["event_month"] = predictions["ts"].dt.strftime("%Y-%m")
    predictions["block28"] = ((predictions["ts"] - predictions["ts"].min()).dt.days // BOOTSTRAP_BLOCK_DAYS).astype(int)
    return predictions, stage_df


def basic_metrics(frame: pd.DataFrame, score_col: str) -> dict[str, Any]:
    valid = frame.dropna(subset=[score_col]).copy()
    if len(valid) == 0:
        return {"n": 0}
    y = valid[TARGET].astype(int).to_numpy()
    p = np.clip(valid[score_col].astype(float).to_numpy(), PROB_EPS, 1.0 - PROB_EPS)
    out = {
        "n": int(len(valid)),
        "assets": int(valid["asset"].nunique()),
        "event_days": int(valid["ts"].nunique()),
        "block28_count": int(valid["block28"].nunique()) if "block28" in valid else None,
        "positive_rate": float(y.mean()),
        "auc": float(roc_auc_score(y, p)) if len(np.unique(y)) >= 2 else None,
        "pr_auc": float(average_precision_score(y, p)) if len(np.unique(y)) >= 2 else None,
        "brier": float(brier_score_loss(y, p)),
        "logloss": float(log_loss(y, p, labels=[0, 1])),
    }
    for pct in [0.01, 0.05, 0.10]:
        top_n = max(1, int(math.ceil(len(valid) * pct)))
        out[f"top{int(pct*100)}_n"] = int(top_n)
        if valid[score_col].nunique(dropna=False) <= 1:
            out[f"top{int(pct*100)}_success_rate"] = float(y.mean())
            out[f"top{int(pct*100)}_uplift"] = 0.0
            out[f"top{int(pct*100)}_net_mean"] = float(valid[NET_RETURN].mean())
            out[f"top{int(pct*100)}_net_median"] = float(valid[NET_RETURN].median())
            out[f"top{int(pct*100)}_net_p05"] = float(valid[NET_RETURN].quantile(0.05))
        else:
            top = top_mask(valid, score_col, pct=pct, group_cols=None)
            out[f"top{int(pct*100)}_success_rate"] = float(valid.loc[top, TARGET].mean()) if top.any() else None
            out[f"top{int(pct*100)}_uplift"] = None if not top.any() else float(valid.loc[top, TARGET].mean() - y.mean())
            out[f"top{int(pct*100)}_net_mean"] = float(valid.loc[top, NET_RETURN].mean()) if top.any() else None
            out[f"top{int(pct*100)}_net_median"] = float(valid.loc[top, NET_RETURN].median()) if top.any() else None
            out[f"top{int(pct*100)}_net_p05"] = float(valid.loc[top, NET_RETURN].quantile(0.05)) if top.any() else None
    return out


def top_mask(frame: pd.DataFrame, score_col: str, *, pct: float, group_cols: list[str] | None) -> np.ndarray:
    df = frame.reset_index(drop=True).copy()
    mask = np.zeros(len(df), dtype=bool)
    if not group_cols:
        n = max(1, int(math.ceil(len(df) * pct)))
        ranked = df.sort_values([score_col, "asset", "ts", "side"], ascending=[False, True, True, True], kind="mergesort")
        mask[ranked.index[:n].to_numpy()] = True
        return mask
    by: str | list[str] = group_cols[0] if len(group_cols) == 1 else group_cols
    for _, idx in df.groupby(by, sort=True).groups.items():
        sub = df.loc[idx]
        n = max(1, int(math.ceil(len(sub) * pct)))
        ranked = sub.sort_values([score_col, "asset", "ts", "side"], ascending=[False, True, True, True], kind="mergesort")
        mask[ranked.index[:n].to_numpy()] = True
    return mask


def bottom_mask(frame: pd.DataFrame, score_col: str, *, pct: float, group_cols: list[str] | None) -> np.ndarray:
    df = frame.reset_index(drop=True).copy()
    mask = np.zeros(len(df), dtype=bool)
    by: Any = group_cols[0] if group_cols and len(group_cols) == 1 else group_cols
    groups = [(None, df.index)] if not group_cols else df.groupby(by, sort=True).groups.items()
    for _, idx in groups:
        sub = df.loc[idx]
        n = max(1, int(math.ceil(len(sub) * pct)))
        ranked = sub.sort_values([score_col, "asset", "ts", "side"], ascending=[True, True, True, True], kind="mergesort")
        mask[ranked.index[:n].to_numpy()] = True
    return mask


def build_metric_tables(predictions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    selection_rows = []
    scopes = [
        ("development_oof", predictions["period"].eq("development_oof")),
        ("validation_2025_plus", predictions["period"].eq("validation_2025_plus")),
        ("validation_2025", predictions["period"].eq("validation_2025_plus") & predictions["event_year"].eq(2025)),
        ("validation_2026", predictions["period"].eq("validation_2025_plus") & predictions["event_year"].eq(2026)),
    ]
    for scope, mask in scopes:
        frame = predictions[mask].copy()
        for model in MODEL_NAMES:
            score = f"{model}_score"
            if score in frame:
                rows.append({"scope": scope, "model": model, **basic_metrics(frame, score)})
        for side, sub in frame.groupby("side", sort=True):
            for model in MODEL_NAMES:
                rows.append({"scope": f"{scope}:side:{side}", "model": model, **basic_metrics(sub, f"{model}_score")})
        for grid, sub in frame.groupby("six_grid", sort=True):
            for model in MODEL_NAMES:
                rows.append({"scope": f"{scope}:grid:{grid}", "model": model, **basic_metrics(sub, f"{model}_score")})
        if "asset_generalization" in frame:
            for group, sub in frame.groupby("asset_generalization", sort=True):
                for model in MODEL_NAMES:
                    rows.append({"scope": f"{scope}:asset:{group}", "model": model, **basic_metrics(sub, f"{model}_score")})

    for period, frame in predictions.groupby("period", sort=True):
        for model in MODEL_NAMES:
            score = f"{model}_score"
            valid = frame.dropna(subset=[score]).copy()
            for pct in [0.01, 0.05, 0.10]:
                selected = top_mask(valid, score, pct=pct, group_cols=["event_year"])
                for grid, sub in valid.loc[selected].groupby("six_grid", sort=True):
                    selection_rows.append(
                        {
                            "period": period,
                            "protocol": "annual_global_then_grid",
                            "model": model,
                            "pct": pct,
                            "six_grid": grid,
                            "n": int(len(sub)),
                            "success_rate": float(sub[TARGET].mean()) if len(sub) else None,
                            "net_mean": float(sub[NET_RETURN].mean()) if len(sub) else None,
                        }
                    )
                selected = top_mask(valid, score, pct=pct, group_cols=["event_year", "side", "market_state"])
                bottom = bottom_mask(valid, score, pct=0.05, group_cols=["event_year", "side", "market_state"])
                for grid, sub in valid.groupby("six_grid", sort=True):
                    top_sub = valid.loc[selected & valid["six_grid"].eq(grid)]
                    bot_sub = valid.loc[bottom & valid["six_grid"].eq(grid)]
                    if sub[score].nunique(dropna=False) <= 1:
                        top_success_rate = float(sub[TARGET].mean())
                        top_uplift = 0.0
                        top_net_mean = float(sub[NET_RETURN].mean())
                        bottom5_success_rate = float(sub[TARGET].mean())
                    else:
                        top_success_rate = float(top_sub[TARGET].mean()) if len(top_sub) else None
                        top_uplift = float(top_sub[TARGET].mean() - sub[TARGET].mean()) if len(top_sub) and len(sub) else None
                        top_net_mean = float(top_sub[NET_RETURN].mean()) if len(top_sub) else None
                        bottom5_success_rate = float(bot_sub[TARGET].mean()) if len(bot_sub) else None
                    selection_rows.append(
                        {
                            "period": period,
                            "protocol": "within_year_side_regime",
                            "model": model,
                            "pct": pct,
                            "six_grid": grid,
                            "n": int(len(sub)),
                            "base_success_rate": float(sub[TARGET].mean()) if len(sub) else None,
                            "top_n": int(len(top_sub)),
                            "top_success_rate": top_success_rate,
                            "top_uplift": top_uplift,
                            "top_net_mean": top_net_mean,
                            "bottom5_success_rate": bottom5_success_rate,
                        }
                    )
    return pd.DataFrame(rows), pd.DataFrame(selection_rows)


def same_day_top5(frame: pd.DataFrame, score_col: str) -> dict[str, Any]:
    valid = frame.dropna(subset=[score_col]).reset_index(drop=True).copy()
    total_selected = 0
    selected_success_sum = 0.0
    selected_net_sum = 0.0
    expected_success_weighted = 0.0
    expected_net_weighted = 0.0
    aucs = []
    eligible_groups = 0
    ineligible_groups = 0
    grid_parts: dict[str, list[dict[str, float]]] = {}
    for (ts, side), g in valid.groupby(["ts", "side"], sort=True):
        if len(g) < MIN_SAME_DAY_EVENTS:
            ineligible_groups += 1
            continue
        eligible_groups += 1
        k = int(math.ceil(SAME_DAY_TOP_PCT * len(g)))
        all_tied = g[score_col].nunique(dropna=False) <= 1
        total_selected += k
        group_expected_success = float(g[TARGET].mean()) * k
        group_expected_net = float(g[NET_RETURN].mean()) * k
        expected_success_weighted += group_expected_success
        expected_net_weighted += group_expected_net
        if all_tied:
            selected_success_sum += group_expected_success
            selected_net_sum += group_expected_net
            grid = str(g["six_grid"].iloc[0])
            grid_parts.setdefault(grid, []).append(
                {
                    "selected_n": float(k),
                    "success_sum": group_expected_success,
                    "net_sum": group_expected_net,
                    "expected_success_sum": group_expected_success,
                    "expected_net_sum": group_expected_net,
                }
            )
            continue
        ranked = g.sort_values([score_col, "asset", "ts", "side"], ascending=[False, True, True, True], kind="mergesort")
        sel = ranked.iloc[:k]
        selected_success_sum += float(sel[TARGET].sum())
        selected_net_sum += float(sel[NET_RETURN].sum())
        if g[TARGET].nunique() >= 2:
            aucs.append(float(roc_auc_score(g[TARGET].astype(int), g[score_col].astype(float))))
        for grid, sg in sel.groupby("six_grid", sort=True):
            grid_parts.setdefault(grid, []).append(
                {
                    "selected_n": float(len(sg)),
                    "success_sum": float(sg[TARGET].sum()),
                    "net_sum": float(sg[NET_RETURN].sum()),
                    "expected_success_sum": float(g[TARGET].mean()) * len(sg),
                    "expected_net_sum": float(g[NET_RETURN].mean()) * len(sg),
                }
            )
    selected_success = selected_success_sum / total_selected if total_selected else None
    selected_net_mean = selected_net_sum / total_selected if total_selected else None
    expected_success = expected_success_weighted / total_selected if total_selected else None
    expected_net = expected_net_weighted / total_selected if total_selected else None
    grid_summary = {}
    for grid, rows in grid_parts.items():
        n = sum(r["selected_n"] for r in rows)
        grid_summary[grid] = {
            "selected_n": int(n),
            "selected_success_rate": sum(r["success_sum"] for r in rows) / n if n else None,
            "expected_success_rate": sum(r["expected_success_sum"] for r in rows) / n if n else None,
            "selected_net_mean": sum(r["net_sum"] for r in rows) / n if n else None,
            "expected_net_mean": sum(r["expected_net_sum"] for r in rows) / n if n else None,
        }
    return {
        "eligible_day_side_groups": eligible_groups,
        "ineligible_day_side_groups": ineligible_groups,
        "selected_n": int(total_selected),
        "selected_success_rate": selected_success,
        "expected_success_rate": expected_success,
        "success_delta_vs_same_day_random": None if selected_success is None or expected_success is None else selected_success - expected_success,
        "selected_net_mean": selected_net_mean,
        "expected_net_mean": expected_net,
        "net_delta_vs_same_day_random": None if selected_net_mean is None or expected_net is None else selected_net_mean - expected_net,
        "same_day_cross_sectional_auc_mean": float(np.mean(aucs)) if aucs else None,
        "same_day_cross_sectional_auc_n": int(len(aucs)),
        "grid_summary": grid_summary,
    }


def frozen_threshold_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    dev = predictions[predictions["period"].eq("development_oof")].copy()
    val = predictions[predictions["period"].eq("validation_2025_plus")].copy()
    for model in MODEL_NAMES:
        score = f"{model}_score"
        train = dev.dropna(subset=[score])
        if len(train) == 0:
            continue
        threshold = float(train[score].quantile(0.95))
        for scope, frame in [("development_oof", dev), ("validation_2025_plus", val), ("validation_2025", val[val["event_year"].eq(2025)]), ("validation_2026", val[val["event_year"].eq(2026)])]:
            f = frame.dropna(subset=[score]).copy()
            selected = f[score] >= threshold
            rows.append(
                {
                    "protocol": "frozen_pre2025_oof_95pct_threshold",
                    "scope": scope,
                    "model": model,
                    "threshold": threshold,
                    "n": int(len(f)),
                    "selected_n": int(selected.sum()),
                    "coverage": float(selected.mean()) if len(f) else None,
                    "success_rate": float(f.loc[selected, TARGET].mean()) if selected.any() else None,
                    "net_mean": float(f.loc[selected, NET_RETURN].mean()) if selected.any() else None,
                }
            )
    return pd.DataFrame(rows)


def build_selection_and_same_day_metrics(predictions: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows = []
    same_day_summary = {}
    for period, frame in predictions.groupby("period", sort=True):
        for model in MODEL_NAMES:
            score = f"{model}_score"
            result = same_day_top5(frame, score)
            same_day_summary[f"{period}:{model}"] = result
            rows.append({"period": period, "protocol": "same_day_same_side_top5", "model": model, **{k: v for k, v in result.items() if k != "grid_summary"}})
    frozen = frozen_threshold_metrics(predictions)
    if len(frozen):
        rows.extend(frozen.to_dict("records"))
    return pd.DataFrame(rows), same_day_summary


def make_block_draw_indices(frame: pd.DataFrame) -> tuple[list[np.ndarray], str]:
    df = frame.reset_index(drop=True).copy()
    block_ids = ((df["ts"] - df["ts"].min()).dt.days // BOOTSTRAP_BLOCK_DAYS).astype(int)
    blocks = sorted(block_ids.unique().tolist())
    groups = {int(block): df.index[block_ids.eq(block)].to_numpy() for block in blocks}
    rng = np.random.default_rng(SEED)
    draws = []
    draw_blocks = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sampled_blocks = rng.choice(blocks, size=len(blocks), replace=True)
        draw_blocks.append([int(x) for x in sampled_blocks])
        draws.append(np.concatenate([groups[int(block)] for block in sampled_blocks]))
    return draws, canonical_sha256({"blocks": blocks, "draws": draw_blocks})


def same_day_contributions(frame: pd.DataFrame, score_col: str, baseline_score_col: str | None = None) -> pd.DataFrame:
    rows = []
    valid = frame.dropna(subset=[score_col]).reset_index(drop=True).copy()
    for (ts, side), g in valid.groupby(["ts", "side"], sort=True):
        if len(g) < MIN_SAME_DAY_EVENTS:
            continue
        k = int(math.ceil(SAME_DAY_TOP_PCT * len(g)))
        if g[score_col].nunique(dropna=False) <= 1:
            selected_success_sum = float(g[TARGET].mean()) * k
            selected_net_sum = float(g[NET_RETURN].mean()) * k
        else:
            selected = g.sort_values([score_col, "asset", "ts", "side"], ascending=[False, True, True, True], kind="mergesort").iloc[:k]
            selected_success_sum = float(selected[TARGET].sum())
            selected_net_sum = float(selected[NET_RETURN].sum())
        if baseline_score_col is None:
            baseline_success_sum = float(g[TARGET].mean()) * k
            baseline_net_sum = float(g[NET_RETURN].mean()) * k
        elif g[baseline_score_col].nunique(dropna=False) <= 1:
            baseline_success_sum = float(g[TARGET].mean()) * k
            baseline_net_sum = float(g[NET_RETURN].mean()) * k
        else:
            base_selected = g.sort_values([baseline_score_col, "asset", "ts", "side"], ascending=[False, True, True, True], kind="mergesort").iloc[:k]
            baseline_success_sum = float(base_selected[TARGET].sum())
            baseline_net_sum = float(base_selected[NET_RETURN].sum())
        rows.append(
            {
                "ts": ts,
                "side": side,
                "block28": int(g["block28"].iloc[0]),
                "selected_n": k,
                "success_diff_sum": selected_success_sum - baseline_success_sum,
                "net_diff_sum": selected_net_sum - baseline_net_sum,
            }
        )
    return pd.DataFrame(rows)


def paired_bootstrap(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for period, frame in predictions.groupby("period", sort=True):
        frame = frame.reset_index(drop=True).copy()
        rng = np.random.default_rng(SEED)
        blocks = sorted(frame["block28"].unique().tolist())
        draw_blocks = [[int(x) for x in rng.choice(blocks, size=len(blocks), replace=True)] for _ in range(BOOTSTRAP_SAMPLES)]
        draw_hash = canonical_sha256({"blocks": [int(x) for x in blocks], "draws": draw_blocks})
        comparisons = [
            ("R_B0_69", "MARKET_RANDOM_EXPECTATION"),
            ("M1_B0_X_SIDE_X_REGIME", "MARKET_RANDOM_EXPECTATION"),
            ("M1_B0_X_SIDE_X_REGIME", "R_B0_69"),
        ]
        for model, baseline in comparisons:
            score = f"{model}_score"
            if frame[score].isna().all():
                continue
            point = same_day_top5(frame, score)
            if baseline == "R_B0_69":
                base_point = same_day_top5(frame, "R_B0_69_score")
                point_success_diff = point["selected_success_rate"] - base_point["selected_success_rate"]
                point_net_diff = point["selected_net_mean"] - base_point["selected_net_mean"]
                contrib = same_day_contributions(frame, score, baseline_score_col="R_B0_69_score")
            else:
                point_success_diff = point["success_delta_vs_same_day_random"]
                point_net_diff = point["net_delta_vs_same_day_random"]
                contrib = same_day_contributions(frame, score, baseline_score_col=None)
            if len(contrib) == 0:
                continue
            block_contrib = contrib.groupby("block28", as_index=True)[["selected_n", "success_diff_sum", "net_diff_sum"]].sum()
            success_diffs = []
            net_diffs = []
            for sampled_blocks in draw_blocks:
                summed = block_contrib.loc[sampled_blocks].sum()
                denom = float(summed["selected_n"])
                if denom > 0:
                    success_diffs.append(float(summed["success_diff_sum"] / denom))
                    net_diffs.append(float(summed["net_diff_sum"] / denom))
            s = np.asarray(success_diffs, dtype=float)
            n = np.asarray(net_diffs, dtype=float)
            rows.append(
                {
                    "period": period,
                    "model": model,
                    "baseline": baseline,
                    "metric_family": "same_day_same_side_top5",
                    "bootstrap_samples": BOOTSTRAP_SAMPLES,
                    "block_days": BOOTSTRAP_BLOCK_DAYS,
                    "draw_hash": draw_hash,
                    "success_diff": point_success_diff,
                    "success_diff_ci_low": float(np.quantile(s, 0.025)) if len(s) else None,
                    "success_diff_ci_high": float(np.quantile(s, 0.975)) if len(s) else None,
                    "net_mean_diff": point_net_diff,
                    "net_mean_diff_ci_low": float(np.quantile(n, 0.025)) if len(n) else None,
                    "net_mean_diff_ci_high": float(np.quantile(n, 0.975)) if len(n) else None,
                    "auc_diff": None,
                    "auc_diff_ci_low": None,
                    "auc_diff_ci_high": None,
                    "two_sided_sign_p_success": float(2 * min((s <= 0).mean(), (s >= 0).mean())) if len(s) else None,
                    "null_hypothesis": "paired block-resampled same-day Top5 additive numerator/denominator difference equals zero under fixed predictions",
                }
            )
    pvals = {
        f"{row['period']}:{row['model']}:{row['baseline']}": row["two_sided_sign_p_success"]
        for row in rows
        if row["two_sided_sign_p_success"] is not None
    }
    qvals = bh_q_values(pvals)
    for row in rows:
        row["bh_q_success"] = qvals.get(f"{row['period']}:{row['model']}:{row['baseline']}")
    return pd.DataFrame(rows)


def bh_q_values(p_values: dict[str, float | None]) -> dict[str, float | None]:
    valid = sorted(((k, p) for k, p in p_values.items() if p is not None), key=lambda item: item[1])
    q = {k: None for k in p_values}
    m = len(valid)
    prev = 1.0
    for rank_from_end, (key, p) in enumerate(reversed(valid), start=1):
        rank = m - rank_from_end + 1
        value = min(prev, p * m / rank)
        q[key] = float(min(value, 1.0))
        prev = value
    return q


def concentration_diagnostics(predictions: pd.DataFrame) -> dict[str, Any]:
    out = {}
    for period, frame in predictions.groupby("period", sort=True):
        for model in ["R_B0_69", "M1_B0_X_SIDE_X_REGIME"]:
            score = f"{model}_score"
            valid = frame.dropna(subset=[score]).copy()
            selected_parts = []
            for _, g in valid.groupby(["ts", "side"], sort=True):
                if len(g) < MIN_SAME_DAY_EVENTS:
                    continue
                k = int(math.ceil(SAME_DAY_TOP_PCT * len(g)))
                selected_parts.append(g.sort_values([score, "asset"], ascending=[False, True], kind="mergesort").iloc[:k])
            if not selected_parts:
                continue
            sel = pd.concat(selected_parts, ignore_index=True)
            out[f"{period}:{model}"] = {
                "selected_n": int(len(sel)),
                "top_asset_share": float(sel["asset"].value_counts(normalize=True).iloc[0]),
                "top_asset": str(sel["asset"].value_counts().index[0]),
                "top_month_share": float(sel["event_month"].value_counts(normalize=True).iloc[0]),
                "top_month": str(sel["event_month"].value_counts().index[0]),
                "btc_eth_removed_success_rate": float(sel[~sel["base_symbol"].isin(["BTC", "ETH"])][TARGET].mean()),
                "remove_top_asset_success_rate": float(sel[sel["asset"] != sel["asset"].value_counts().index[0]][TARGET].mean()),
                "remove_top_month_success_rate": float(sel[sel["event_month"] != sel["event_month"].value_counts().index[0]][TARGET].mean()),
            }
    return out


def exposure_ledger(data_audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "created_utc": datetime.now(UTC).isoformat(),
        "verdict": "NO_CONFIRMED_FRESH_OOS_AVAILABLE",
        "trained_history": {
            "pre_2025_strict_events": data_audit["strict_sample"]["strict_rows"],
            "date_range": [data_audit["strict_sample"]["strict_min_ts"], data_audit["strict_sample"]["strict_max_ts"]],
            "max_label_end": data_audit["strict_sample"]["strict_max_label_end"],
        },
        "predicted_or_reused_history": {
            "iterative_reused_validation_2025_plus": True,
            "p1_observed_2025_plus": True,
            "p5_observed_and_repaired_2025_plus": True,
            "p6_uses_2025_plus_for_frozen_candidate_comparison_only": True,
            "validation_main_crypto_rows": data_audit["validation_rows_main_crypto"],
        },
        "fresh_oos": {
            "available_now": False,
            "reason": "P0R/P5 validated event panel ends before the P0 cutoff and 2025+ has already been observed/reused; no separately confirmed unexposed labeled window is available in this task.",
            "required_before_use": "dataset_id + trusted load audit + overlap migration parity + frozen prospective protocol",
        },
        "data_lake_boundary": {
            "canonical_new_ohlcv_dataset_id": "binance.perp.ohlcv.1d.from_15m.v1",
            "new_data_steps": ["query", "select_version", "validate", "read", "fix_input"],
            "legacy_family_cache_not_allowed_for_new_oos": True,
        },
    }


def non_overlap_metrics(predictions: pd.DataFrame) -> dict[str, Any]:
    out = {}
    for period, frame in predictions.groupby("period", sort=True):
        sample = P5.non_overlap_sample(frame)
        out[period] = {"n": int(len(sample)), "base_success_rate": float(sample[TARGET].mean()) if len(sample) else None}
        for model in MODEL_NAMES:
            score = f"{model}_score"
            if score in sample and sample[score].notna().any() and sample[TARGET].nunique() >= 2:
                out[period][f"{model}_auc"] = float(roc_auc_score(sample[TARGET], sample[score]))
    return out


def adjudicate(selection_metrics: pd.DataFrame, paired: pd.DataFrame, concentration: dict[str, Any], exposure: dict[str, Any]) -> dict[str, Any]:
    val_m1 = selection_metrics[
        (selection_metrics["period"].eq("validation_2025_plus"))
        & (selection_metrics["protocol"].eq("same_day_same_side_top5"))
        & (selection_metrics["model"].eq("M1_B0_X_SIDE_X_REGIME"))
    ]
    val_b0 = selection_metrics[
        (selection_metrics["period"].eq("validation_2025_plus"))
        & (selection_metrics["protocol"].eq("same_day_same_side_top5"))
        & (selection_metrics["model"].eq("R_B0_69"))
    ]
    m1_delta = float(val_m1["success_delta_vs_same_day_random"].iloc[0]) if len(val_m1) else None
    m1_net_delta = float(val_m1["net_delta_vs_same_day_random"].iloc[0]) if len(val_m1) else None
    b0_delta = float(val_b0["success_delta_vs_same_day_random"].iloc[0]) if len(val_b0) else None
    p_m1 = paired[
        (paired["period"].eq("validation_2025_plus"))
        & (paired["model"].eq("M1_B0_X_SIDE_X_REGIME"))
        & (paired["baseline"].eq("MARKET_RANDOM_EXPECTATION"))
    ]
    ci_low = float(p_m1["success_diff_ci_low"].iloc[0]) if len(p_m1) and pd.notna(p_m1["success_diff_ci_low"].iloc[0]) else None
    q = float(p_m1["bh_q_success"].iloc[0]) if len(p_m1) and pd.notna(p_m1["bh_q_success"].iloc[0]) else None
    if m1_delta is None:
        verdict = "DATA_OR_IMPLEMENTATION_AUDIT_FAILED"
    elif m1_delta >= 0.05 and (m1_net_delta or -1.0) > 0 and ci_low is not None and ci_low > 0 and q is not None and q <= 0.05:
        verdict = "LOCAL_CONDITIONAL_VALUE_NEEDS_FRESH_OOS" if not exposure["fresh_oos"]["available_now"] else "FRESH_OOS_CONFIRMED_CONDITIONAL_VALUE"
    elif (b0_delta or 0) <= 0.01 and m1_delta <= 0.01:
        verdict = "MARKET_OR_SIDE_VALUE_ONLY"
    else:
        verdict = "NO_STABLE_EXTRA_COIN_SELECTION_VALUE"
    fresh_oos_status = "PENDING_FRESH_OOS" if not exposure["fresh_oos"]["available_now"] else "FRESH_OOS_CONSUMED"
    return {
        "verdict": verdict,
        "fresh_oos_status": fresh_oos_status,
        "same_day_top5_research_budget_gate": {
            "target_success_delta": 0.05,
            "m1_validation_success_delta": m1_delta,
            "m1_validation_net_delta": m1_net_delta,
            "m1_success_diff_ci_low": ci_low,
            "m1_bh_q_success": q,
        },
    }


def fmt(x: Any, digits: int = 4) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)) or pd.isna(x):
        return "NA"
    return f"{float(x):.{digits}f}"


def write_reports(summary: dict[str, Any], market_metrics: pd.DataFrame, selection_metrics: pd.DataFrame, paired: pd.DataFrame) -> None:
    def metric(scope: str, model: str, col: str) -> Any:
        rows = market_metrics[(market_metrics["scope"].eq(scope)) & (market_metrics["model"].eq(model))]
        return rows[col].iloc[0] if len(rows) and col in rows else None

    def same(period: str, model: str, col: str) -> Any:
        rows = selection_metrics[
            (selection_metrics["period"].eq(period))
            & (selection_metrics["protocol"].eq("same_day_same_side_top5"))
            & (selection_metrics["model"].eq(model))
        ]
        return rows[col].iloc[0] if len(rows) and col in rows else None

    lines = [
        "# BIN-1D-MA7-CTP P6 市场环境 × 多空方向的条件排序价值审计",
        "",
        f"- 状态：`{STATUS}`",
        f"- 实验裁决：`{summary['adjudication']['verdict']}`；新 OOS：`{summary['adjudication']['fresh_oos_status']}`",
        "- P6 受已经观察到的 2025+ 启发；2025+ 是 `ITERATIVE_REUSED_VALIDATION_2025_PLUS`，不是首次盲测。",
        "",
        "## 大白话结论",
        "",
        f"- 市场环境与方向能解释裸成功率的表面差异：六格基础成功率见指标表，最高/最低格差异来自市场时段和方向，不等于选币能力。",
        f"- 同一天同方向选币主检验：B0 在 2025+ 的 Top5 相对同日同方向随机基准成功率增量为 {fmt(same('validation_2025_plus', 'R_B0_69', 'success_delta_vs_same_day_random'))}，M1 为 {fmt(same('validation_2025_plus', 'M1_B0_X_SIDE_X_REGIME', 'success_delta_vs_same_day_random'))}；M1 事件标签净收益增量为 {fmt(same('validation_2025_plus', 'M1_B0_X_SIDE_X_REGIME', 'net_delta_vs_same_day_random'))}。",
        "- 已成立：2025+ 不是新盲测，HYPE 仍为 0，市场状态还原 long/short 一致，M1 使用前向 B0 样本外分数训练。",
        "- 仍是线索：任何局部六格或方向优势必须看 paired bootstrap、多重比较和集中度，不能说成全市场选币模型有效。",
        f"- 继续/停止：当前裁决为 `{summary['adjudication']['verdict']}`；若未达到 +5pp 且净收益增量为正的研究预算门槛，应停止或只保留局部观察，不继续扩特征。",
        "- 真正新 OOS：本轮没有合格未揭示标签窗口；若未来继续，必须先走数据湖 canonical dataset 与迁移对账，再按 prospective 协议一次性确认。",
        "",
        "## 核心数字",
        "",
        "| Scope | Model | AUC | PR-AUC | Top5 success | Top5 uplift |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for scope in ["development_oof", "validation_2025_plus", "validation_2025", "validation_2026"]:
        for model in MODEL_NAMES:
            lines.append(
                f"| `{scope}` | `{model}` | {fmt(metric(scope, model, 'auc'))} | {fmt(metric(scope, model, 'pr_auc'))} | "
                f"{fmt(metric(scope, model, 'top5_success_rate'))} | {fmt(metric(scope, model, 'top5_uplift'))} |"
            )
    lines.extend(
        [
            "",
            "## 证据",
            "",
            "- [config](../artifacts/binance_1d_ma7_ctp_p6_config.json)",
            "- [exposure ledger](../artifacts/binance_1d_ma7_ctp_p6_exposure_ledger.json)",
            "- [data audit](../artifacts/binance_1d_ma7_ctp_p6_data_audit.json)",
            "- [B0 reproduction audit](../artifacts/binance_1d_ma7_ctp_p6_b0_reproduction_audit.json)",
            "- [predictions](../artifacts/binance_1d_ma7_ctp_p6_predictions.parquet)",
            "- [market state metrics](../artifacts/binance_1d_ma7_ctp_p6_market_state_metrics.parquet)",
            "- [selection metrics](../artifacts/binance_1d_ma7_ctp_p6_selection_metrics.parquet)",
            "- [paired bootstrap stats](../artifacts/binance_1d_ma7_ctp_p6_paired_bootstrap_stats.parquet)",
            "- [summary](../artifacts/binance_1d_ma7_ctp_p6_summary.json)",
            "- [prospective protocol](../specs/binance-1d-ma7-ctp-p6-prospective-oos-confirmation-protocol-2026-09-03.md)",
        ]
    )
    atomic_write_text(REPORT_PATH, "\n".join(lines) + "\n")
    protocol = f"""# BIN-1D-MA7-CTP P6 Prospective OOS Confirmation Protocol

- 状态：`prospective / frozen-after-historical-audit / not active`
- 触发条件：只有 P6 历史审计达到同日同方向 Top5 相对基准 +5pp、事件标签净收益增量为正、集中度可接受、且用户明确授权时，才消耗新 OOS。
- 当前结论：`{summary['adjudication']['fresh_oos_status']}`；本轮没有读取合格未揭示标签窗口。

未来若执行：

1. 使用数据湖 canonical `binance.perp.ohlcv.1d.from_15m.v1` 与必要 `1h/15m` 路径，先完成第 16 节查询、选版本、验证、读取、固定输入。
2. 在读取新标签前冻结唯一待确认对象、适用六格/方向、B0/M1 分数来源、阈值、同日 Top5 指标、paired bootstrap、最小日期块和样本量。
3. 先完成 P0R/P5 重叠窗口迁移对账：事件键、OHLCV、B0 69 字段、ATR、小时 first-hit、funding、B0 预测。
4. 禁止看新结果边跑边改规则，禁止反复查看显著性后择时停止。

本协议不是定时任务，不授权 runner，不登记策略版本。
"""
    atomic_write_text(PROSPECTIVE_PROTOCOL_PATH, protocol)


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
            "experiment": "P6",
            "created_utc": datetime.now(UTC).isoformat(),
            "artifacts": artifacts,
            "manifest_excludes_self": True,
            "manifest_sha256_canonical_payload": canonical_sha256(artifacts),
        },
    )


def run(force: bool) -> dict[str, Any]:
    ensure_output_policy(force)
    config = build_config()
    write_lock(config)
    p5_audit = verify_p5_manifest()
    development, validation_main, data_audit = load_base_events_and_predictions(config)
    predictions, stage_df = add_model_predictions(development, validation_main, config)
    market_metrics, selection_breakdown = build_metric_tables(predictions)
    selection_metrics, same_day_summary = build_selection_and_same_day_metrics(predictions)
    paired = paired_bootstrap(predictions)
    concentration = concentration_diagnostics(predictions)
    exposure = exposure_ledger(data_audit)
    data_audit["p5_manifest_verification"] = p5_audit
    data_audit["prediction_rows"] = {
        "development_oof": int(predictions["period"].eq("development_oof").sum()),
        "validation_2025_plus": int(predictions["period"].eq("validation_2025_plus").sum()),
    }
    b0_reproduction = {
        "p4_b0_feature_count": config["models"]["R_B0_69"]["feature_count"],
        "p5_oof_prediction_file_sha256": sha256_file(P5_OOF_PATH),
        "p5_validation_prediction_file_sha256": sha256_file(P5_VALIDATION_PATH),
        "b0_oof_rows_reused": int(predictions["period"].eq("development_oof").sum()),
        "b0_validation_rows_reused": int(predictions["period"].eq("validation_2025_plus").sum()),
        "manifest_verified": True,
        "self_fit_probability_claimed_identical": False,
    }
    non_overlap = non_overlap_metrics(predictions)
    summary = {
        "family": config["family"],
        "alias": config["alias"],
        "experiment": config["experiment"],
        "created_utc": datetime.now(UTC).isoformat(),
        "status": STATUS,
        "data_roles": {
            "development": "strict pre-2025",
            "validation": "ITERATIVE_REUSED_VALIDATION_2025_PLUS",
            "fresh_oos": "not available / not consumed",
        },
        "adjudication": adjudicate(selection_metrics, paired, concentration, exposure),
        "same_day_summary": same_day_summary,
        "concentration": concentration,
        "non_overlap": non_overlap,
        "hype_isolation": {"hype_rows": data_audit["hype_rows"], "hyper_present": data_audit["hyper_present"]},
        "p5_manifest_verification": p5_audit,
    }
    atomic_write_json(EXPOSURE_LEDGER_PATH, exposure)
    atomic_write_json(DATA_AUDIT_PATH, data_audit)
    atomic_write_json(B0_REPRODUCTION_PATH, b0_reproduction)
    atomic_write_parquet(FOLD_STAGE_METRICS_PATH, stage_df)
    atomic_write_parquet(PREDICTIONS_PATH, predictions)
    atomic_write_parquet(MARKET_STATE_METRICS_PATH, pd.concat([market_metrics, selection_breakdown], ignore_index=True, sort=False))
    atomic_write_parquet(SELECTION_METRICS_PATH, selection_metrics)
    atomic_write_parquet(PAIRED_STATS_PATH, paired)
    atomic_write_json(CONCENTRATION_PATH, concentration)
    atomic_write_json(SUMMARY_PATH, summary)
    write_reports(summary, market_metrics, selection_metrics, paired)
    build_manifest([SPEC_PATH, SCRIPT_PATH, TEST_PATH, P4_FACTOR_GROUP_SPEC_PATH, P5_MANIFEST_PATH, P5_SUMMARY_PATH, P5_ACCEPTANCE_PATH, P0R_MANIFEST_PATH, P0_MANIFEST_PATH, DATA_LAKE_SPEC_PATH] + output_paths())
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="replace P6-only outputs")
    args = parser.parse_args()
    summary = run(force=args.force)
    print(json.dumps(json_ready({"verdict": summary["adjudication"]["verdict"], "fresh_oos": summary["adjudication"]["fresh_oos_status"], "summary": str(SUMMARY_PATH)}), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
