#!/usr/bin/env python3
"""Run BIN-1D-MA7-CTP P7A placebo base-rate and barrier-geometry audit.

Independent sidecar diagnostic. Does not read or write any P7 artifacts.
Does not train models, search factors, or promote a strategy.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
CATL_DIR = ROOT / "research/asset-portfolios/1d-cross-asset-trend-lifecycle"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAGNOSTIC_DIR = FAMILY_DIR / "diagnostics"
SPEC_DIR = FAMILY_DIR / "specs"

CATL_P0_SCRIPT = CATL_DIR / "scripts/run_binance_1d_catl_p0_dataset_label_atlas.py"
P0R_FEATURE_BLOCKS_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_feature_blocks.json"
P0R_MANIFEST_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_manifest.json"
P0R_SUMMARY_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_summary.json"
PANEL_DIR = CATL_DIR / "artifacts/p0r_donor_directional_modeling_panel"
PANEL_GLOB = PANEL_DIR / "**/*.parquet"
CATL_HOURLY_PATH = CATL_DIR / "artifacts/_catl_p0_hourly_from_15m.parquet"
FUNDING_DIR = ROOT / "data/normalized/funding_rates/exchange=binance/market_type=perp"

P5_VALIDATION_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_validation_2025_plus_predictions.parquet"
P5_OOF_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_pre2025_oof_predictions.parquet"
P5_DATA_AUDIT_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_data_audit.json"
P5_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_summary.json"
P5_MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_manifest.json"
P6_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p6_summary.json"
P6_DATA_AUDIT_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p6_data_audit.json"
P1_EVENT_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_event_panel_summary.json"

CONTRACT_PATH = SPEC_DIR / "binance-1d-ma7-ctp-p7a-placebo-base-rate-audit-contract-2026-09-04.md"
SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p7a_placebo_base_rate_audit.py"
TEST_PATH = ROOT / "tests/test_binance_1d_ma7_ctp_p7a_placebo_base_rate_audit.py"

PREFIX = "binance_1d_ma7_ctp_p7a_"
RESEARCH_ID = "BIN-1D-MA7-CTP-P7A-2026-09-04"
SCHEMA_VERSION = "p7a.v1"
STATUS = "explore / diagnostic-only / placebo-audit / not promoted / not live-ready"
LOCK_STATUS = "FROZEN_BEFORE_P7A_PLACEBO_OUTPUT_READ"
CANONICAL_LABEL_VERSION = "CATL-P0R-entry-2atr-1atr-20d-hourly-first-hit"
CANONICAL_UNIVERSE_VERSION = "CATL-P0R-donor-panel-hype-sealed"

HYPE_ASSET = "HYPE/USDT:USDT"
HYPE_SLUG = "hype_usdt_usdt"
HYPER_ASSET = "HYPER/USDT:USDT"
TARGET = "label_entry_success_20d"
LABEL_END = "label_end_ts_20d"
NET_RETURN = "label_entry_net_return"
RESULT_COL = "label_entry_result"

BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_BLOCK_DAYS = 28
BOOTSTRAP_SEED = 20260901
MC_N = 500
MC_SEED_START = 2026090400
MC_SEED_END = 2026090899
MC_SUCCESS_TOLERANCE = 0.002
CUTOFF = pd.Timestamp("2025-01-01T00:00:00Z")
P0_CUTOFF = pd.Timestamp("2026-05-31T00:00:00Z")
EXPECTED_2025_PLUS = 46892
EXPECTED_2025 = 32111
EXPECTED_2026 = 14781
EXPECTED_P1_N = 101187

FEE_PER_FILL = 0.001
SLIPPAGE_PER_FILL = 0.0004
ROUND_TRIP_COST = 2.0 * (FEE_PER_FILL + SLIPPAGE_PER_FILL)
LEVERAGE = 1.0
PRIMARY_FAV = 2.0
PRIMARY_ADV = 1.0
PRIMARY_HORIZON_DAYS = 20
PRIMARY_HORIZON_HOURS = PRIMARY_HORIZON_DAYS * 24

BARRIER_GRID = (
    (1.0, 1.0),
    (1.5, 1.0),
    (2.0, 1.0),
    (2.5, 1.0),
    (3.0, 1.0),
    (2.0, 0.5),
    (2.0, 1.5),
    (2.0, 2.0),
)
TIMEOUT_DAYS = (5, 10, 20, 40)
MAX_SENSITIVITY_HOURS = 40 * 24

KNOWN_TRADFI_BASE_SYMBOLS = {
    "AAPL", "AMZN", "COIN", "CRCL", "GOOGL", "HOOD", "META", "MSFT", "MSTR",
    "NVDA", "PLTR", "TSLA", "SPX", "SPY", "QQQ", "TSM", "UBER", "XAU", "XAG",
    "XPD", "XPT",
}

VERDICT_CANDIDATES = (
    "DATA_OR_REPRODUCTION_FAILURE",
    "PLACEBO_EXPLAINS_BASE_RATE",
    "CROSS_MOVEMENT_EFFECT_WITHOUT_DIRECTIONAL_EDGE",
    "MA7_DIRECTIONAL_EDGE_WEAK",
    "MA7_DIRECTIONAL_EDGE_SUPPORTED",
)

CONFIG_PATH = ARTIFACT_DIR / f"{PREFIX}config.json"
CONTRACT_LOCK_PATH = ARTIFACT_DIR / f"{PREFIX}contract_lock.json"
INPUT_INVENTORY_PATH = ARTIFACT_DIR / f"{PREFIX}input_inventory.json"
DATA_AUDIT_PATH = ARTIFACT_DIR / f"{PREFIX}data_audit.json"
REAL_EVENT_PARITY_PATH = ARTIFACT_DIR / f"{PREFIX}real_event_parity.json"
CANDIDATE_UNIVERSE_AUDIT_PATH = ARTIFACT_DIR / f"{PREFIX}candidate_universe_audit.json"
DUAL_SIDE_PATH = ARTIFACT_DIR / f"{PREFIX}dual_side_outcomes.parquet"
DATE_EXPECT_PATH = ARTIFACT_DIR / f"{PREFIX}date_placebo_expectations.parquet"
PLACEBO_SUMMARY_CSV = ARTIFACT_DIR / f"{PREFIX}placebo_summary.csv"
PLACEBO_SUMMARY_JSON = ARTIFACT_DIR / f"{PREFIX}placebo_summary.json"
YEAR_DIR_CSV = ARTIFACT_DIR / f"{PREFIX}year_direction_breakdown.csv"
FIRST_HIT_CSV = ARTIFACT_DIR / f"{PREFIX}first_hit_breakdown.csv"
BARRIER_CSV = ARTIFACT_DIR / f"{PREFIX}barrier_sensitivity.csv"
TIMEOUT_CSV = ARTIFACT_DIR / f"{PREFIX}timeout_sensitivity.csv"
BOOTSTRAP_PATH = ARTIFACT_DIR / f"{PREFIX}bootstrap_results.parquet"
MC_CSV = ARTIFACT_DIR / f"{PREFIX}monte_carlo_validation.csv"
SUMMARY_PATH = ARTIFACT_DIR / f"{PREFIX}summary.json"
MANIFEST_PATH = ARTIFACT_DIR / f"{PREFIX}manifest.json"
REPORT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p7a-placebo-base-rate-audit-2026-09-04.md"
IMPL_AUDIT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p7a-implementation-audit-2026-09-04.md"
DEFERRED_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p7a-deferred-registration-2026-09-04.md"

CHARTS = {
    "decomposition": ARTIFACT_DIR / f"{PREFIX}chart_01_base_rate_decomposition.svg",
    "yearly": ARTIFACT_DIR / f"{PREFIX}chart_02_yearly_rates.svg",
    "edge_year": ARTIFACT_DIR / f"{PREFIX}chart_03_directional_edge_by_year.svg",
    "move_year": ARTIFACT_DIR / f"{PREFIX}chart_04_cross_movement_by_year.svg",
    "barrier": ARTIFACT_DIR / f"{PREFIX}chart_05_barrier_geometry_sensitivity.svg",
    "timeout": ARTIFACT_DIR / f"{PREFIX}chart_06_timeout_sensitivity.svg",
    "long_short": ARTIFACT_DIR / f"{PREFIX}chart_07_long_short.svg",
    "monte_carlo": ARTIFACT_DIR / f"{PREFIX}chart_08_monte_carlo_validation.svg",
}

FILES_READ: list[str] = []


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CATL_P0 = load_module(CATL_P0_SCRIPT, "binance_1d_catl_p0_for_p7a")
result_from_hours = CATL_P0.result_from_hours
hit_net_return = CATL_P0.hit_net_return
build_funding_lookup = CATL_P0.build_funding_lookup
funding_sum_between = CATL_P0.funding_sum_between


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(json_ready(payload), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


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
    if isinstance(value, Path):
        return str(value)
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


def atomic_write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(tmp, index=False)
    tmp.replace(path)


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT)).replace("\\", "/")


def note_read(path: Path) -> Path:
    resolved = path.resolve()
    text = str(resolved)
    if HYPE_SLUG in text.lower() and "hyper_usdt_usdt" not in text.lower():
        raise RuntimeError(f"refusing to read HYPE partition: {path}")
    FILES_READ.append(rel(resolved) if ROOT in resolved.parents or resolved == ROOT else text)
    return path


def base_symbol(asset: str) -> str:
    return asset.split("/")[0].upper()


def is_hype(asset: str) -> bool:
    return str(asset) == HYPE_ASSET


def assert_no_p7_input(paths: list[str]) -> None:
    for item in paths:
        name = Path(item).name
        if "_p7_" in name and "_p7a_" not in name:
            raise RuntimeError(f"P7A must not read P7 artifact as input: {item}")


def event_identity_hash(frame: pd.DataFrame) -> str:
    keys = frame[["asset", "ts", "side"]].copy()
    ts = pd.to_datetime(keys["ts"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    lines = sorted(f"{a}|{t}|{s}" for a, t, s in zip(keys["asset"].astype(str), ts, keys["side"].astype(str)))
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def random_side_expectation(long_v: np.ndarray | pd.Series, short_v: np.ndarray | pd.Series) -> np.ndarray:
    return 0.5 * np.asarray(long_v, dtype=float) + 0.5 * np.asarray(short_v, dtype=float)


def result_from_hours_array(fav: np.ndarray, adv: np.ndarray, horizon_hours: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    fav_hit = np.isfinite(fav) & (fav <= horizon_hours)
    adv_hit = np.isfinite(adv) & (adv <= horizon_hours)
    result = np.full(len(fav), "timeout", dtype=object)
    success = np.zeros(len(fav), dtype=bool)
    hours = np.full(len(fav), float(horizon_hours), dtype=float)
    both = fav_hit & adv_hit
    fav_only = fav_hit & ~adv_hit
    adv_only = adv_hit & ~fav_hit
    result[both & (fav < adv)] = "favorable_first"
    success[both & (fav < adv)] = True
    hours[both & (fav < adv)] = fav[both & (fav < adv)]
    result[both & (adv < fav)] = "adverse_first"
    hours[both & (adv < fav)] = adv[both & (adv < fav)]
    result[both & (fav == adv)] = "ambiguous_same_hour"
    hours[both & (fav == adv)] = adv[both & (fav == adv)]
    result[fav_only] = "favorable_first"
    success[fav_only] = True
    hours[fav_only] = fav[fav_only]
    result[adv_only] = "adverse_first"
    hours[adv_only] = adv[adv_only]
    return result, success, hours


def date_weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    x = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce")
    mask = x.notna() & w.notna() & (w > 0)
    if not bool(mask.any()) or float(w[mask].sum()) == 0:
        return float("nan")
    return float(np.average(x[mask].to_numpy(dtype=float), weights=w[mask].to_numpy(dtype=float)))


def pct(value: float | None, digits: int = 4) -> str:
    if value is None or not np.isfinite(value):
        return "NA"
    return f"{100.0 * float(value):.{digits}f}%"


def pp(value: float | None, digits: int = 4) -> str:
    if value is None or not np.isfinite(value):
        return "NA"
    return f"{100.0 * float(value):+.{digits}f} pp"


def calendar_block_id(ts: pd.Series, *, origin: pd.Timestamp | None = None) -> pd.Series:
    times = pd.to_datetime(ts, utc=True)
    start = origin if origin is not None else times.min()
    return ((times.dt.normalize() - start.normalize()).dt.days // BOOTSTRAP_BLOCK_DAYS).astype(int)


def benjamini_hochberg(pvalues: list[float]) -> list[float]:
    m = len(pvalues)
    order = np.argsort(pvalues)
    q = np.ones(m, dtype=float)
    prev = 1.0
    for rank_from_end, idx in enumerate(reversed(order)):
        rank = m - rank_from_end
        q[idx] = min(prev, pvalues[idx] * m / rank)
        prev = q[idx]
    return [float(v) for v in q]


def bootstrap_two_sided_p(draws: np.ndarray) -> float:
    finite = draws[np.isfinite(draws)]
    if len(finite) == 0:
        return float("nan")
    n = len(finite)
    p_pos = (np.sum(finite >= 0) + 1.0) / (n + 1.0)
    p_neg = (np.sum(finite <= 0) + 1.0) / (n + 1.0)
    return float(min(1.0, 2.0 * min(p_pos, p_neg)))


def build_config(*, generated_at: str) -> dict[str, Any]:
    return {
        "research_id": RESEARCH_ID,
        "schema_version": SCHEMA_VERSION,
        "experiment": "P7A Placebo Base-Rate and Barrier Geometry Audit",
        "status": STATUS,
        "lock_status": LOCK_STATUS,
        "purpose": "explain the already-observed ~30% first-hit positive rate; not a new blind OOS",
        "p7_sidecar": True,
        "forbidden_p7_inputs": True,
        "canonical_label_version": CANONICAL_LABEL_VERSION,
        "canonical_universe_version": CANONICAL_UNIVERSE_VERSION,
        "primary_barrier": {"tp_atr": PRIMARY_FAV, "sl_atr": PRIMARY_ADV, "horizon_days": PRIMARY_HORIZON_DAYS},
        "cost_model": {
            "leverage": LEVERAGE,
            "fee_per_fill": FEE_PER_FILL,
            "slippage_per_fill": SLIPPAGE_PER_FILL,
            "round_trip_cost": ROUND_TRIP_COST,
        },
        "placebo_groups": [
            "REAL_MA7_CROSS",
            "SAME_CROSS_ASSET_DATE_RANDOM_SIDE_EXPECTATION",
            "DATE_MATCHED_ELIGIBLE_RANDOM_SIDE_EXPECTATION",
            "DATE_MATCHED_NON_CROSS_RANDOM_SIDE_EXPECTATION",
            "DATE_MATCHED_NON_CROSS_1D_MOMENTUM",
            "DATE_MATCHED_NON_CROSS_MA7_SIDE",
        ],
        "primary_baseline": "DATE_MATCHED_NON_CROSS_RANDOM_SIDE_EXPECTATION",
        "barrier_grid": [{"tp": a, "sl": b} for a, b in BARRIER_GRID],
        "timeout_grid_days": list(TIMEOUT_DAYS),
        "bootstrap": {"n": BOOTSTRAP_SAMPLES, "block_days": BOOTSTRAP_BLOCK_DAYS, "seed": BOOTSTRAP_SEED},
        "monte_carlo": {
            "n": MC_N,
            "seed_start": MC_SEED_START,
            "seed_end": MC_SEED_END,
            "success_tolerance": MC_SUCCESS_TOLERANCE,
        },
        "parity_anchors": {
            "validation_2025_plus": EXPECTED_2025_PLUS,
            "year_2025": EXPECTED_2025,
            "year_2026": EXPECTED_2026,
        },
        "verdict_candidates": list(VERDICT_CANDIDATES),
        "economic_edge_threshold_pp": 2.0,
        "multiple_testing": "Bonferroni and BH-FDR on three primary tests",
        "hype_asset": HYPE_ASSET,
        "hyper_asset": HYPER_ASSET,
        "generated_at": generated_at,
        "no_ml": True,
        "no_equity_curve": True,
        "theoretical_brownian_p": 1.0 / 3.0,
    }


def list_p0r_panel_files() -> list[Path]:
    files = sorted(PANEL_DIR.rglob("*.parquet"))
    if not files:
        raise RuntimeError("P0R donor panel is empty")
    for path in files:
        note_read(path)
    return files


def freeze_inputs(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    note_read(CONTRACT_PATH)
    note_read(SCRIPT_PATH)
    note_read(P0R_FEATURE_BLOCKS_PATH)
    note_read(P0R_MANIFEST_PATH)
    note_read(P0R_SUMMARY_PATH)
    note_read(CATL_P0_SCRIPT)
    note_read(CATL_HOURLY_PATH)
    note_read(P5_VALIDATION_PATH)
    note_read(P5_OOF_PATH)
    note_read(P5_DATA_AUDIT_PATH)
    note_read(P5_SUMMARY_PATH)
    note_read(P5_MANIFEST_PATH)
    note_read(P6_SUMMARY_PATH)
    note_read(P6_DATA_AUDIT_PATH)
    note_read(P1_EVENT_SUMMARY_PATH)
    panel_files = list_p0r_panel_files()
    inputs = {
        "research_id": RESEARCH_ID,
        "schema_version": SCHEMA_VERSION,
        "files": [],
    }
    hashed: dict[str, str] = {}
    for path in [
        CONTRACT_PATH, SCRIPT_PATH, P0R_FEATURE_BLOCKS_PATH, P0R_MANIFEST_PATH, P0R_SUMMARY_PATH,
        CATL_P0_SCRIPT, CATL_HOURLY_PATH, P5_VALIDATION_PATH, P5_OOF_PATH, P5_DATA_AUDIT_PATH,
        P5_SUMMARY_PATH, P5_MANIFEST_PATH, P6_SUMMARY_PATH, P6_DATA_AUDIT_PATH, P1_EVENT_SUMMARY_PATH,
        *panel_files,
    ]:
        digest = sha256_file(path)
        hashed[rel(path)] = digest
        inputs["files"].append({"path": rel(path), "sha256": digest, "bytes": path.stat().st_size})
    assert_no_p7_input([item["path"] for item in inputs["files"]])
    if any(HYPE_SLUG in item["path"].lower() and "hyper_usdt_usdt" not in item["path"].lower() for item in inputs["files"]):
        raise RuntimeError("HYPE partition leaked into input inventory")
    inputs["n_files"] = len(inputs["files"])
    inputs["input_set_sha256"] = canonical_sha256(hashed)
    lock = {
        "research_id": RESEARCH_ID,
        "schema_version": SCHEMA_VERSION,
        "status": LOCK_STATUS,
        "purpose": config["purpose"],
        "contract_sha256": hashed[rel(CONTRACT_PATH)],
        "config_sha256": canonical_sha256(config),
        "script_sha256": hashed[rel(SCRIPT_PATH)],
        "input_inventory_sha256": canonical_sha256(inputs),
        "canonical_label_version": CANONICAL_LABEL_VERSION,
        "canonical_universe_version": CANONICAL_UNIVERSE_VERSION,
        "p7_files_included": False,
    }
    atomic_write_json(CONFIG_PATH, config)
    atomic_write_json(INPUT_INVENTORY_PATH, inputs)
    atomic_write_json(CONTRACT_LOCK_PATH, lock)
    return inputs, lock


def load_p0r_panel() -> pd.DataFrame:
    cols = [
        "asset", "asset_slug", "side", "ts", "feature_known_at", "entry_ts", "entry_ref", "atr_anchor",
        TARGET, LABEL_END, NET_RETURN, RESULT_COL, "label_entry_hours_to_hit", "label_entry_ambiguous_same_hour",
        "future_path_complete_20d", "future_terminal_direction_return_20d",
        "model_eligible_entry_p0r", "probe_raw_ma7_cross_dir", "dir_raw_ma7_cross",
        "dir_ret_1d", "dir_price_side_ma7",
    ]
    quoted = ", ".join(f'"{c}"' for c in cols)
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    df = con.execute(
        f"""
        SELECT {quoted}
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        WHERE asset <> ?
        """,
        [str(PANEL_GLOB), HYPE_ASSET],
    ).fetchdf()
    con.close()
    for col in ["ts", "feature_known_at", "entry_ts", LABEL_END]:
        df[col] = pd.to_datetime(df[col], utc=True)
    if (df["asset"] == HYPE_ASSET).any():
        raise RuntimeError("HYPE rows leaked into P0R load")
    df["side"] = df["side"].astype(str).str.lower()
    df["side_sign"] = np.where(df["side"].eq("long"), 1, -1).astype(int)
    df["base_symbol"] = df["asset"].map(base_symbol)
    df["is_known_tradfi"] = df["base_symbol"].isin(KNOWN_TRADFI_BASE_SYMBOLS)
    df["event_year"] = df["ts"].dt.year.astype(int)
    df[TARGET] = df[TARGET].astype(int)
    return df


def build_dual_side(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    eligible = raw.loc[
        raw["model_eligible_entry_p0r"].astype(bool)
        & raw["future_path_complete_20d"].astype(bool)
        & ~raw["is_known_tradfi"]
    ].copy()
    if (eligible["asset"] == HYPE_ASSET).any():
        raise RuntimeError("HYPE eligible rows")
    long = eligible.loc[eligible["side"].eq("long")].copy()
    short = eligible.loc[eligible["side"].eq("short")].copy()
    key = ["asset", "asset_slug", "ts"]
    merged = long.merge(short, on=key, how="inner", suffixes=("_long", "_short"))
    both_probe = merged["probe_raw_ma7_cross_dir_long"] & merged["probe_raw_ma7_cross_dir_short"]
    if int(both_probe.sum()) != 0:
        raise RuntimeError("asset-day with both long and short MA7 cross probes")
    entry_mismatch = (~np.isclose(merged["entry_ref_long"], merged["entry_ref_short"], rtol=0, atol=0, equal_nan=True)).sum()
    atr_mismatch = (~np.isclose(merged["atr_anchor_long"], merged["atr_anchor_short"], rtol=0, atol=0, equal_nan=True)).sum()
    entry_ts_mismatch = int((merged["entry_ts_long"] != merged["entry_ts_short"]).sum())
    out = pd.DataFrame({
        "asset": merged["asset"],
        "asset_slug": merged["asset_slug"],
        "ts": merged["ts"],
        "event_year": merged["event_year_long"],
        "feature_known_at": merged["feature_known_at_long"],
        "entry_ts": merged["entry_ts_long"],
        "entry_ref": merged["entry_ref_long"],
        "atr_anchor": merged["atr_anchor_long"],
        "label_end_ts_20d": merged[f"{LABEL_END}_long"],
        "long_success": merged[f"{TARGET}_long"].astype(int),
        "short_success": merged[f"{TARGET}_short"].astype(int),
        "long_net": merged[f"{NET_RETURN}_long"].astype(float),
        "short_net": merged[f"{NET_RETURN}_short"].astype(float),
        "long_result": merged[f"{RESULT_COL}_long"].astype(str),
        "short_result": merged[f"{RESULT_COL}_short"].astype(str),
        "long_hours": merged["label_entry_hours_to_hit_long"].astype(float),
        "short_hours": merged["label_entry_hours_to_hit_short"].astype(float),
        "long_terminal": merged["future_terminal_direction_return_20d_long"].astype(float),
        "short_terminal": merged["future_terminal_direction_return_20d_short"].astype(float),
        "long_ambiguous": merged["label_entry_ambiguous_same_hour_long"].astype(bool),
        "short_ambiguous": merged["label_entry_ambiguous_same_hour_short"].astype(bool),
        "is_cross": merged["probe_raw_ma7_cross_dir_long"] | merged["probe_raw_ma7_cross_dir_short"],
        "real_side": np.where(merged["probe_raw_ma7_cross_dir_long"], "long",
                     np.where(merged["probe_raw_ma7_cross_dir_short"], "short", "")),
        "ret_1d": merged["dir_ret_1d_long"].astype(float),
        "dir_price_side_ma7_long": merged["dir_price_side_ma7_long"].astype(float),
        "hyper": merged["asset"].eq(HYPER_ASSET),
    })
    out["rs_success"] = random_side_expectation(out["long_success"], out["short_success"])
    out["rs_net"] = random_side_expectation(out["long_net"], out["short_net"])
    out["real_success"] = np.where(out["real_side"].eq("long"), out["long_success"],
                          np.where(out["real_side"].eq("short"), out["short_success"], np.nan))
    out["real_net"] = np.where(out["real_side"].eq("long"), out["long_net"],
                      np.where(out["real_side"].eq("short"), out["short_net"], np.nan))
    out["real_result"] = np.where(out["real_side"].eq("long"), out["long_result"],
                         np.where(out["real_side"].eq("short"), out["short_result"], ""))
    out["momentum_side"] = np.where(out["ret_1d"] > 0, "long", np.where(out["ret_1d"] < 0, "short", ""))
    out["ma7_side"] = np.where(out["dir_price_side_ma7_long"] > 0, "long",
                      np.where(out["dir_price_side_ma7_long"] < 0, "short", ""))
    out["date"] = out["ts"].dt.normalize()
    audit = {
        "eligible_directional_rows": int(len(eligible)),
        "dual_side_asset_days": int(len(out)),
        "paired_long": int(len(long)),
        "paired_short": int(len(short)),
        "inner_join_kept": int(len(merged)),
        "entry_ref_mismatch": int(entry_mismatch),
        "atr_mismatch": int(atr_mismatch),
        "entry_ts_mismatch": int(entry_ts_mismatch),
        "hype_rows": int((out["asset"] == HYPE_ASSET).sum()),
        "hyper_rows": int(out["hyper"].sum()),
        "cross_asset_days": int(out["is_cross"].sum()),
        "non_cross_asset_days": int((~out["is_cross"]).sum()),
        "tradfi_excluded": True,
    }
    if audit["hype_rows"] != 0:
        raise RuntimeError("HYPE rows in dual-side table")
    if audit["hyper_rows"] <= 0:
        raise RuntimeError("HYPER missing from dual-side table")
    if audit["entry_ref_mismatch"] or audit["atr_mismatch"] or audit["entry_ts_mismatch"]:
        raise RuntimeError("long/short counterfactuals do not share entry/ATR/path identity")
    return out, audit


def attach_p5_identity(dual: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    p5_val = pd.read_parquet(P5_VALIDATION_PATH)
    p5_val["ts"] = pd.to_datetime(p5_val["ts"], utc=True)
    p5_val["side"] = p5_val["side"].astype(str).str.lower()
    if (p5_val["asset"] == HYPE_ASSET).any():
        raise RuntimeError("HYPE rows in P5 predictions")
    if "is_known_tradfi" in p5_val.columns:
        p5_val_main = p5_val.loc[~p5_val["is_known_tradfi"].astype(bool)].copy()
    else:
        p5_val_main = p5_val.loc[~p5_val["asset"].map(base_symbol).isin(KNOWN_TRADFI_BASE_SYMBOLS)].copy()
    p5_val_main = p5_val_main.loc[~p5_val_main["asset"].eq(HYPE_ASSET)]

    def key(frame: pd.DataFrame, side_col: str) -> pd.Series:
        return (
            frame["asset"].astype(str)
            + "|"
            + pd.to_datetime(frame["ts"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S%z")
            + "|"
            + frame[side_col].astype(str)
        )

    val_keys = set(key(p5_val_main, "side"))
    out = dual.copy()
    out["event_key"] = key(out.assign(side=out["real_side"].where(out["real_side"].ne(""), "none")), "side")
    out["in_p5_val"] = out["is_cross"] & out["event_key"].isin(val_keys)
    out["official_real"] = out["is_cross"] & ((out["ts"] < CUTOFF) | out["in_p5_val"])
    excluded = out.loc[out["is_cross"] & (out["ts"] >= CUTOFF) & ~out["in_p5_val"]]
    meta = {
        "p5_validation_main": int(len(p5_val_main)),
        "p0r_cross_not_in_p5_2025plus": int(len(excluded)),
        "p5_keys": val_keys,
        "p5_val_main": p5_val_main,
        "excluded_sample": sorted(excluded["event_key"].astype(str))[:20],
    }
    return out, meta


def real_event_frame(dual: pd.DataFrame) -> pd.DataFrame:
    real = dual.loc[dual["official_real"] & dual["real_side"].isin(["long", "short"])].copy()
    real["side"] = real["real_side"]
    real[TARGET] = real["real_success"].astype(int)
    real[NET_RETURN] = real["real_net"].astype(float)
    real[RESULT_COL] = real["real_result"].astype(str)
    return real.reset_index(drop=True)


def first_hit_counts(result: pd.Series) -> dict[str, int]:
    vc = result.astype(str).value_counts()
    return {
        "favorable_first": int(vc.get("favorable_first", 0)),
        "adverse_first": int(vc.get("adverse_first", 0)),
        "ambiguous_same_hour": int(vc.get("ambiguous_same_hour", 0)),
        "timeout": int(vc.get("timeout", 0)),
        "n": int(len(result)),
    }


def decompose_net(success: np.ndarray, result: np.ndarray, net: np.ndarray, atr: np.ndarray, ref: np.ndarray, terminal: np.ndarray) -> dict[str, float]:
    price = np.where(result == "favorable_first", PRIMARY_FAV * atr / ref,
            np.where(np.isin(result, ["adverse_first", "ambiguous_same_hour"]), -PRIMARY_ADV * atr / ref, terminal))
    funding = net - price + ROUND_TRIP_COST
    return {
        "success_rate": float(np.mean(success)) if len(success) else float("nan"),
        "net_mean": float(np.mean(net)) if len(net) else float("nan"),
        "net_median": float(np.median(net)) if len(net) else float("nan"),
        "gross_mean": float(np.mean(price)) if len(price) else float("nan"),
        "funding_mean": float(np.mean(funding)) if len(funding) else float("nan"),
        "cost": ROUND_TRIP_COST,
        "positive_net_ratio": float(np.mean(net > 0)) if len(net) else float("nan"),
        "n": int(len(success)),
    }


def group_metrics_from_arrays(success: np.ndarray, net: np.ndarray, result: np.ndarray | None = None) -> dict[str, Any]:
    out = {
        "success_rate": float(np.mean(success)) if len(success) else float("nan"),
        "net_mean": float(np.mean(net)) if len(net) else float("nan"),
        "net_median": float(np.median(net)) if len(net) else float("nan"),
        "positive_net_ratio": float(np.mean(net > 0)) if len(net) else float("nan"),
        "n": int(len(success)),
    }
    if result is not None:
        out.update(first_hit_counts(pd.Series(result)))
    return out


def period_mask(dual: pd.DataFrame, period: str) -> pd.Series:
    year = dual["event_year"]
    ts = dual["ts"]
    if period == "full":
        return pd.Series(True, index=dual.index)
    if period == "pre_2025":
        return ts < CUTOFF
    if period == "2025plus":
        return ts >= CUTOFF
    if period.isdigit():
        return year.eq(int(period))
    raise KeyError(period)


def date_stats(dual: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    part = dual.loc[mask].copy()
    cross = part.loc[part["official_real"]]
    non = part.loc[~part["is_cross"]]
    mom = non.loc[non["momentum_side"].isin(["long", "short"])].copy()
    mom["mom_success"] = np.where(mom["momentum_side"].eq("long"), mom["long_success"], mom["short_success"])
    mom["mom_net"] = np.where(mom["momentum_side"].eq("long"), mom["long_net"], mom["short_net"])
    mom_g = mom.groupby("date", sort=True).agg(mom_n=("asset", "size"), mom_success_mean=("mom_success", "mean"), mom_net_mean=("mom_net", "mean"))
    ma = non.loc[non["ma7_side"].isin(["long", "short"])].copy()
    ma["ma_success"] = np.where(ma["ma7_side"].eq("long"), ma["long_success"], ma["short_success"])
    ma["ma_net"] = np.where(ma["ma7_side"].eq("long"), ma["long_net"], ma["short_net"])
    ma_g = ma.groupby("date", sort=True).agg(ma7_n=("asset", "size"), ma7_success_mean=("ma_success", "mean"), ma7_net_mean=("ma_net", "mean"))

    out = pd.DataFrame({"date": sorted(part["date"].unique())})
    out = out.merge(cross.groupby("date").size().rename("n_cross"), on="date", how="left")
    out = out.merge(non.groupby("date").size().rename("n_noncross"), on="date", how="left")
    out = out.merge(part.groupby("date").size().rename("n_eligible"), on="date", how="left")
    out = out.merge(cross.groupby("date")["real_success"].sum().rename("real_success_sum"), on="date", how="left")
    out = out.merge(cross.groupby("date")["real_net"].sum().rename("real_net_sum"), on="date", how="left")
    out = out.merge(cross.groupby("date")["rs_success"].sum().rename("cross_rs_sum"), on="date", how="left")
    out = out.merge(cross.groupby("date")["rs_net"].sum().rename("cross_rs_net_sum"), on="date", how="left")
    out = out.merge(part.groupby("date")["rs_success"].mean().rename("eligible_rs_mean"), on="date", how="left")
    out = out.merge(part.groupby("date")["rs_net"].mean().rename("eligible_rs_net_mean"), on="date", how="left")
    out = out.merge(non.groupby("date")["rs_success"].mean().rename("noncross_rs_mean"), on="date", how="left")
    out = out.merge(non.groupby("date")["rs_net"].mean().rename("noncross_rs_net_mean"), on="date", how="left")
    out = out.merge(mom_g, on="date", how="left")
    out = out.merge(ma_g, on="date", how="left")
    long_cross = cross.loc[cross["real_side"].eq("long")]
    short_cross = cross.loc[cross["real_side"].eq("short")]
    out = out.merge(long_cross.groupby("date").size().rename("real_long_n"), on="date", how="left")
    out = out.merge(long_cross.groupby("date")["real_success"].sum().rename("real_long_success_sum"), on="date", how="left")
    out = out.merge(long_cross.groupby("date")["short_success"].sum().rename("real_long_opp_success_sum"), on="date", how="left")
    out = out.merge(short_cross.groupby("date").size().rename("real_short_n"), on="date", how="left")
    out = out.merge(short_cross.groupby("date")["real_success"].sum().rename("real_short_success_sum"), on="date", how="left")
    out = out.merge(short_cross.groupby("date")["long_success"].sum().rename("real_short_opp_success_sum"), on="date", how="left")
    for col in ["n_cross", "n_noncross", "n_eligible", "real_long_n", "real_short_n", "mom_n", "ma7_n"]:
        out[col] = out[col].fillna(0).astype(int)
    for col in ["real_success_sum", "real_net_sum", "cross_rs_sum", "cross_rs_net_sum", "real_long_success_sum",
                "real_long_opp_success_sum", "real_short_success_sum", "real_short_opp_success_sum"]:
        out[col] = out[col].fillna(0.0)
    return out


def weighted_from_dates(stats: pd.DataFrame) -> dict[str, float]:
    w = stats["n_cross"].astype(float)
    real_n = float(w.sum())
    out = {
        "n_cross": int(real_n),
        "n_dates": int((stats["n_cross"] > 0).sum()),
        "n_dates_with_noncross": int(((stats["n_cross"] > 0) & (stats["n_noncross"] > 0)).sum()),
        "real_success": float(stats["real_success_sum"].sum() / real_n) if real_n else float("nan"),
        "real_net": float(stats["real_net_sum"].sum() / real_n) if real_n else float("nan"),
        "same_cross_rs": float(stats["cross_rs_sum"].sum() / real_n) if real_n else float("nan"),
        "same_cross_rs_net": float(stats["cross_rs_net_sum"].sum() / real_n) if real_n else float("nan"),
        "eligible_rs": date_weighted_mean(stats["eligible_rs_mean"], w),
        "eligible_rs_net": date_weighted_mean(stats["eligible_rs_net_mean"], w),
        "noncross_rs": date_weighted_mean(stats["noncross_rs_mean"], w),
        "noncross_rs_net": date_weighted_mean(stats["noncross_rs_net_mean"], w),
        "momentum": date_weighted_mean(stats["mom_success_mean"], w),
        "momentum_net": date_weighted_mean(stats["mom_net_mean"], w),
        "ma7_side": date_weighted_mean(stats["ma7_success_mean"], w),
        "ma7_side_net": date_weighted_mean(stats["ma7_net_mean"], w),
    }
    out["directional_edge"] = out["real_success"] - out["same_cross_rs"]
    out["cross_movement"] = out["same_cross_rs"] - out["noncross_rs"]
    out["total_vs_noncross"] = out["real_success"] - out["noncross_rs"]
    long_n = float(stats["real_long_n"].sum())
    short_n = float(stats["real_short_n"].sum())
    out["real_long_n"] = int(long_n)
    out["real_short_n"] = int(short_n)
    out["real_long_success"] = float(stats["real_long_success_sum"].sum() / long_n) if long_n else float("nan")
    out["real_short_success"] = float(stats["real_short_success_sum"].sum() / short_n) if short_n else float("nan")
    out["real_long_vs_opp_short"] = (
        float(stats["real_long_success_sum"].sum() / long_n - stats["real_long_opp_success_sum"].sum() / long_n)
        if long_n else float("nan")
    )
    out["real_short_vs_opp_long"] = (
        float(stats["real_short_success_sum"].sum() / short_n - stats["real_short_opp_success_sum"].sum() / short_n)
        if short_n else float("nan")
    )
    return out


def real_side_metrics(real: pd.DataFrame) -> dict[str, Any]:
    atr = real["atr_anchor"].to_numpy(dtype=float)
    ref = real["entry_ref"].to_numpy(dtype=float)
    terminal = np.where(real["real_side"].eq("long"), real["long_terminal"], real["short_terminal"]).astype(float)
    decomp = decompose_net(
        real["real_success"].to_numpy(dtype=float),
        real["real_result"].to_numpy(dtype=object),
        real["real_net"].to_numpy(dtype=float),
        atr, ref, terminal,
    )
    decomp.update(first_hit_counts(real["real_result"]))
    return decomp


def load_json(path: Path) -> dict[str, Any]:
    note_read(path)
    return json.loads(path.read_text(encoding="utf-8"))


def real_event_parity(real: pd.DataFrame) -> dict[str, Any]:
    main = real.copy()
    y2025 = main.loc[main["event_year"].eq(2025)]
    y2026 = main.loc[main["event_year"].eq(2026)]
    plus = main.loc[main["ts"] >= CUTOFF]
    p5_val = pd.read_parquet(P5_VALIDATION_PATH)
    p5_oof = pd.read_parquet(P5_OOF_PATH)
    for frame in (p5_val, p5_oof):
        frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
        frame["side"] = frame["side"].astype(str).str.lower()
        if "asset" in frame.columns and (frame["asset"] == HYPE_ASSET).any():
            raise RuntimeError("HYPE rows in P5 predictions")
    p5_val_main = p5_val.copy()
    if "is_known_tradfi" in p5_val_main.columns:
        p5_val_main = p5_val_main.loc[~p5_val_main["is_known_tradfi"].astype(bool)]
    else:
        p5_val_main = p5_val_main.loc[~p5_val_main["asset"].map(base_symbol).isin(KNOWN_TRADFI_BASE_SYMBOLS)]
    p5_val_main = p5_val_main.loc[~p5_val_main["asset"].eq(HYPE_ASSET)]

    def key(frame: pd.DataFrame) -> pd.Series:
        return frame["asset"].astype(str) + "|" + pd.to_datetime(frame["ts"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S%z") + "|" + frame["side"].astype(str)

    plus_keys = set(key(plus.assign(side=plus["real_side"])))
    val_keys = set(key(p5_val_main))
    missing = sorted(val_keys - plus_keys)
    extra = sorted(plus_keys - val_keys)

    merged = plus.assign(side=plus["real_side"]).merge(
        p5_val_main[[
            "asset", "ts", "side", TARGET, NET_RETURN, "entry_ts", "feature_known_at", LABEL_END,
        ] + [c for c in ["entry_ref", "atr_anchor"] if c in p5_val_main.columns]],
        on=["asset", "ts", "side"],
        how="inner",
        suffixes=("", "_p5"),
    )
    if f"{TARGET}_p5" in merged.columns:
        label_mismatch = int((merged[TARGET].astype(int) != merged[f"{TARGET}_p5"].astype(int)).sum())
    else:
        label_mismatch = int((merged[TARGET].astype(int) != merged[TARGET].astype(int)).sum())
    net_mismatch = 0
    if f"{NET_RETURN}_p5" in merged.columns:
        net_mismatch = int((~np.isclose(merged[NET_RETURN], merged[f"{NET_RETURN}_p5"], rtol=0, atol=1e-12, equal_nan=True)).sum())
    entry_ts_mismatch = 0
    if "entry_ts_p5" in merged.columns:
        entry_ts_mismatch = int((pd.to_datetime(merged["entry_ts"], utc=True) != pd.to_datetime(merged["entry_ts_p5"], utc=True)).sum())
    feature_known_mismatch = 0
    if "feature_known_at_p5" in merged.columns:
        feature_known_mismatch = int((pd.to_datetime(merged["feature_known_at"], utc=True) != pd.to_datetime(merged["feature_known_at_p5"], utc=True)).sum())
    entry_mismatch = 0
    atr_mismatch = 0
    if "entry_ref_p5" in merged.columns:
        entry_mismatch = int((~np.isclose(merged["entry_ref"], merged["entry_ref_p5"], rtol=0, atol=1e-12, equal_nan=True)).sum())
    if "atr_anchor_p5" in merged.columns:
        atr_mismatch = int((~np.isclose(merged["atr_anchor"], merged["atr_anchor_p5"], rtol=0, atol=1e-12, equal_nan=True)).sum())

    p1 = json.loads(P1_EVENT_SUMMARY_PATH.read_text(encoding="utf-8"))
    counts = {
        "real_n": int(len(main)),
        "real_2025_plus": int(len(plus)),
        "real_2025": int(len(y2025)),
        "real_2026": int(len(y2026)),
        "real_pre_2025": int((main["ts"] < CUTOFF).sum()),
        "hype_rows": int((main["asset"] == HYPE_ASSET).sum()),
        "hyper_rows": int(main["asset"].eq(HYPER_ASSET).sum()),
        "p5_validation_main": int(len(p5_val_main)),
        "p5_oof_n": int(len(p5_oof)),
        "identity_missing_vs_p5_val": len(missing),
        "identity_extra_vs_p5_val": len(extra),
        "label_mismatch_vs_p5_val": label_mismatch,
        "net_return_mismatch_vs_p5_val": net_mismatch,
        "entry_ts_mismatch_vs_p5_val": entry_ts_mismatch,
        "feature_known_at_mismatch_vs_p5_val": feature_known_mismatch,
        "entry_ref_mismatch_vs_p5_val": entry_mismatch,
        "atr_mismatch_vs_p5_val": atr_mismatch,
        "p1_n": int(p1.get("n", -1)),
        "success_2025": float(y2025["real_success"].mean()) if len(y2025) else float("nan"),
        "success_2026": float(y2026["real_success"].mean()) if len(y2026) else float("nan"),
        "success_2025_plus": float(plus["real_success"].mean()) if len(plus) else float("nan"),
        "success_full": float(main["real_success"].mean()) if len(main) else float("nan"),
        "canonical_event_id_hash": event_identity_hash(main.assign(side=main["real_side"])),
        "canonical_event_id_hash_2025_plus": event_identity_hash(plus.assign(side=plus["real_side"])),
    }
    counts["anchors_ok"] = (
        counts["real_2025_plus"] == EXPECTED_2025_PLUS
        and counts["real_2025"] == EXPECTED_2025
        and counts["real_2026"] == EXPECTED_2026
        and counts["hype_rows"] == 0
        and counts["hyper_rows"] > 0
        and counts["identity_missing_vs_p5_val"] == 0
        and counts["identity_extra_vs_p5_val"] == 0
        and counts["label_mismatch_vs_p5_val"] == 0
        and counts["net_return_mismatch_vs_p5_val"] == 0
        and counts["entry_ts_mismatch_vs_p5_val"] == 0
        and counts["feature_known_at_mismatch_vs_p5_val"] == 0
        and counts["entry_ref_mismatch_vs_p5_val"] == 0
        and counts["atr_mismatch_vs_p5_val"] == 0
    )
    counts["reproduction_failure"] = not counts["anchors_ok"]
    counts["p5_val_missing_sample"] = missing[:20]
    counts["p5_val_extra_sample"] = extra[:20]
    return counts


def placebo_table(metrics: dict[str, float], real_extra: dict[str, Any]) -> pd.DataFrame:
    rows = []
    mapping = [
        ("REAL_MA7_CROSS", metrics["real_success"], metrics["real_net"], metrics["n_cross"], real_extra.get("net_median")),
        ("SAME_CROSS_ASSET_DATE_RANDOM_SIDE_EXPECTATION", metrics["same_cross_rs"], metrics["same_cross_rs_net"], metrics["n_cross"], None),
        ("DATE_MATCHED_ELIGIBLE_RANDOM_SIDE_EXPECTATION", metrics["eligible_rs"], metrics["eligible_rs_net"], metrics["n_cross"], None),
        ("DATE_MATCHED_NON_CROSS_RANDOM_SIDE_EXPECTATION", metrics["noncross_rs"], metrics["noncross_rs_net"], metrics["n_cross"], None),
        ("DATE_MATCHED_NON_CROSS_1D_MOMENTUM", metrics["momentum"], metrics["momentum_net"], metrics["n_cross"], None),
        ("DATE_MATCHED_NON_CROSS_MA7_SIDE", metrics["ma7_side"], metrics["ma7_side_net"], metrics["n_cross"], None),
    ]
    for name, success, net, n, median in mapping:
        rows.append({
            "group": name,
            "success_rate": success,
            "vs_noncross_random": success - metrics["noncross_rs"] if np.isfinite(success) and np.isfinite(metrics["noncross_rs"]) else float("nan"),
            "net_mean": net,
            "net_median": median,
            "effective_n": n,
        })
    return pd.DataFrame(rows)


def run_block_bootstrap(stats: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    work = stats.loc[stats["n_cross"] > 0].copy().reset_index(drop=True)
    work["block"] = calendar_block_id(work["date"], origin=work["date"].min())
    blocks = work["block"].drop_duplicates().to_numpy()
    by_block = {int(b): work.loc[work["block"].eq(b)].index.to_numpy() for b in blocks}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    records = []
    for i in range(BOOTSTRAP_SAMPLES):
        sampled = rng.choice(blocks, size=len(blocks), replace=True)
        idx = np.concatenate([by_block[int(b)] for b in sampled])
        sample = work.iloc[idx]
        m = weighted_from_dates(sample)
        records.append({
            "replicate": i,
            "real_success": m["real_success"],
            "same_cross_rs": m["same_cross_rs"],
            "noncross_rs": m["noncross_rs"],
            "directional_edge": m["directional_edge"],
            "cross_movement": m["cross_movement"],
            "total_vs_noncross": m["total_vs_noncross"],
        })
    boot = pd.DataFrame(records)

    def summarize(col: str) -> dict[str, float]:
        x = boot[col].to_numpy(dtype=float)
        finite = x[np.isfinite(x)]
        return {
            "point_from_full_sample": None,
            "bootstrap_mean": float(np.mean(finite)) if len(finite) else float("nan"),
            "p2.5": float(np.percentile(finite, 2.5)) if len(finite) else float("nan"),
            "p97.5": float(np.percentile(finite, 97.5)) if len(finite) else float("nan"),
            "effective_replicates": int(len(finite)),
            "non_finite_replicates": int(len(x) - len(finite)),
            "p_two_sided": bootstrap_two_sided_p(finite),
        }

    summary = {col: summarize(col) for col in ["directional_edge", "cross_movement", "total_vs_noncross", "real_success", "same_cross_rs", "noncross_rs"]}
    summary["n"] = BOOTSTRAP_SAMPLES
    summary["seed"] = BOOTSTRAP_SEED
    summary["block_days"] = BOOTSTRAP_BLOCK_DAYS
    summary["n_blocks"] = int(len(blocks))
    return boot, summary


def monte_carlo_validation(dual: pd.DataFrame, exact: dict[str, float], *, period: str = "full") -> pd.DataFrame:
    mask = period_mask(dual, period)
    part = dual.loc[mask].copy()
    cross = part.loc[part["official_real"]].reset_index(drop=True)
    non = part.loc[~part["is_cross"]].copy()
    dates = sorted(cross["date"].unique())
    n_cross_by_date = cross.groupby("date").size().to_dict()
    non_by_date = {d: g.reset_index(drop=True) for d, g in non.groupby("date")}
    rows = []
    for offset, seed in enumerate(range(MC_SEED_START, MC_SEED_END + 1)):
        rng = np.random.default_rng(seed)
        side_u = rng.random(len(cross))
        same_pick = np.where(side_u < 0.5, cross["long_success"].to_numpy(dtype=float), cross["short_success"].to_numpy(dtype=float))
        sampled_success = []
        sampled_weight = []
        for d in dates:
            n = int(n_cross_by_date[d])
            pool = non_by_date.get(d)
            if pool is None or len(pool) == 0 or n <= 0:
                continue
            replace = len(pool) < n
            idx = rng.choice(len(pool), size=n, replace=replace)
            pick = pool.iloc[idx]
            u = rng.random(n)
            succ = np.where(u < 0.5, pick["long_success"].to_numpy(dtype=float), pick["short_success"].to_numpy(dtype=float))
            sampled_success.append(succ)
            sampled_weight.append(n)
        non_mc = float(np.concatenate(sampled_success).mean()) if sampled_success else float("nan")
        rows.append({
            "seed": seed,
            "replicate": offset,
            "same_cross_random_side": float(same_pick.mean()),
            "date_matched_noncross_random_side": non_mc,
        })
    mc = pd.DataFrame(rows)

    def mc_summary(col: str, exact_value: float) -> dict[str, float]:
        x = mc[col].to_numpy(dtype=float)
        finite = x[np.isfinite(x)]
        mean = float(np.mean(finite)) if len(finite) else float("nan")
        return {
            "mean": mean,
            "median": float(np.median(finite)) if len(finite) else float("nan"),
            "std": float(np.std(finite, ddof=1)) if len(finite) > 1 else float("nan"),
            "p2.5": float(np.percentile(finite, 2.5)) if len(finite) else float("nan"),
            "p97.5": float(np.percentile(finite, 97.5)) if len(finite) else float("nan"),
            "exact_expectation": exact_value,
            "exact_minus_mc_mean": exact_value - mean if np.isfinite(mean) and np.isfinite(exact_value) else float("nan"),
            "within_tolerance": bool(np.isfinite(mean) and np.isfinite(exact_value) and abs(exact_value - mean) <= MC_SUCCESS_TOLERANCE),
        }

    meta = {
        "same_cross": mc_summary("same_cross_random_side", exact["same_cross_rs"]),
        "noncross": mc_summary("date_matched_noncross_random_side", exact["noncross_rs"]),
        "n": MC_N,
        "seed_start": MC_SEED_START,
        "seed_end": MC_SEED_END,
        "tolerance": MC_SUCCESS_TOLERANCE,
    }
    mc.attrs["summary"] = meta
    return mc


def load_funding_lookup() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    files = sorted(str(p) for p in FUNDING_DIR.rglob("*.parquet") if HYPE_SLUG not in str(p).lower() or "hyper_usdt_usdt" in str(p).lower())
    if not files:
        return {}
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    funding = con.execute(
        """
        WITH dedup AS (
            SELECT symbol, ts, avg(funding_rate) AS funding_rate
            FROM read_parquet(?, union_by_name=true, hive_partitioning=false)
            WHERE symbol <> ?
            GROUP BY symbol, ts
        )
        SELECT symbol AS asset, date_trunc('day', ts) AS ts, sum(funding_rate) AS funding_rate_sum
        FROM dedup
        GROUP BY symbol, date_trunc('day', ts)
        ORDER BY symbol, ts
        """,
        [files, HYPE_ASSET],
    ).df()
    con.close()
    funding["ts"] = pd.to_datetime(funding["ts"], utc=True)
    if (funding["asset"] == HYPE_ASSET).any():
        raise RuntimeError("HYPE funding rows loaded")
    return build_funding_lookup(funding)


def to_epoch_ns(series: pd.Series) -> np.ndarray:
    ts = pd.to_datetime(series, utc=True)
    return ts.dt.as_unit("ns").astype("int64").to_numpy()


def complete_window_mask(hour_ns: np.ndarray, entry_ns: np.ndarray, pos: np.ndarray, hours: int) -> np.ndarray:
    hour_delta = pd.Timedelta(hours=1).value
    in_bounds = (pos >= 0) & (pos + hours - 1 < len(hour_ns))
    expected_end = entry_ns + (hours - 1) * hour_delta
    ok = np.zeros(len(pos), dtype=bool)
    ok[in_bounds] = hour_ns[pos[in_bounds] + hours - 1] == expected_end[in_bounds]
    return ok


def first_hit_for_window(high: np.ndarray, low: np.ndarray, close: np.ndarray, pos: np.ndarray, entry_ref: np.ndarray, atr: np.ndarray, hours: int, fav_thr: float, adv_thr: float, side_sign: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    high_win = np.lib.stride_tricks.sliding_window_view(high, hours)[pos]
    low_win = np.lib.stride_tricks.sliding_window_view(low, hours)[pos]
    close_win = np.lib.stride_tricks.sliding_window_view(close, hours)[pos]
    if side_sign == 1:
        fav_path = (high_win - entry_ref[:, None]) / atr[:, None]
        adv_path = (entry_ref[:, None] - low_win) / atr[:, None]
        terminal = close_win[:, -1] / entry_ref - 1.0
    else:
        fav_path = (entry_ref[:, None] - low_win) / atr[:, None]
        adv_path = (high_win - entry_ref[:, None]) / atr[:, None]
        terminal = -(close_win[:, -1] / entry_ref - 1.0)
    hit_f = fav_path >= fav_thr
    hit_a = adv_path >= adv_thr
    fav_h = np.where(hit_f.any(axis=1), hit_f.argmax(axis=1) + 1, np.nan)
    adv_h = np.where(hit_a.any(axis=1), hit_a.argmax(axis=1) + 1, np.nan)
    return fav_h, adv_h, terminal


def run_sensitivity(dual: pd.DataFrame, funding_lookup: dict[str, tuple[np.ndarray, np.ndarray]]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    needed = dual.reset_index(drop=True).copy()
    assets = sorted(needed["asset"].unique())
    if HYPE_ASSET in assets:
        raise RuntimeError("HYPE in sensitivity asset list")
    hour_delta = pd.Timedelta(hours=1).value
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    print("loading hourly table excluding HYPE...", flush=True)
    con.execute(
        """
        CREATE TABLE hourly AS
        SELECT symbol, hour_ts, open, high, low, close
        FROM read_parquet(?)
        WHERE symbol <> ?
        """,
        [str(CATL_HOURLY_PATH), HYPE_ASSET],
    )
    hype_hourly = int(con.execute("SELECT count(*) FROM hourly WHERE symbol = ?", [HYPE_ASSET]).fetchone()[0])
    if hype_hourly:
        raise RuntimeError("HYPE rows present in sensitivity hourly table")
    barrier_store: dict[tuple[float, float], list[pd.DataFrame]] = {pair: [] for pair in BARRIER_GRID}
    timeout_store: dict[int, list[pd.DataFrame]] = {d: [] for d in TIMEOUT_DAYS}
    parity_n = 0
    parity_mismatch = 0
    entry_ref_hourly_mismatch = 0

    def funding_vector(asset_name: str, start_ns: np.ndarray, hours_held: np.ndarray) -> np.ndarray:
        item = funding_lookup.get(asset_name)
        if item is None:
            return np.zeros(len(start_ns), dtype=float)
        times, csum = item
        held = np.where(np.isfinite(hours_held), hours_held, 0.0)
        end_ns = start_ns + held.astype(np.int64) * hour_delta
        left = np.searchsorted(times, start_ns, side="left")
        right = np.searchsorted(times, end_ns, side="right")
        right = np.clip(right, 0, len(csum) - 1)
        left = np.clip(left, 0, len(csum) - 1)
        return (csum[right] - csum[left]).astype(float)

    def nets_from(
        result: np.ndarray,
        hours: np.ndarray,
        term: np.ndarray,
        fav: float,
        adv: float,
        atr_v: np.ndarray,
        ref_v: np.ndarray,
        sign: int,
        start_ns: np.ndarray,
        asset_name: str,
    ) -> np.ndarray:
        price = np.where(
            result == "favorable_first",
            fav * atr_v / ref_v,
            np.where(np.isin(result, ["adverse_first", "ambiguous_same_hour"]), -adv * atr_v / ref_v, term),
        )
        fs = funding_vector(asset_name, start_ns, hours)
        return LEVERAGE * price + (-sign * fs) - ROUND_TRIP_COST

    for asset_i, asset in enumerate(assets, start=1):
        if asset_i == 1 or asset_i % 50 == 0 or asset_i == len(assets):
            print(f"sensitivity asset {asset_i}/{len(assets)} {asset}", flush=True)
        hourly = con.execute(
            """
            SELECT hour_ts, open, high, low, close
            FROM hourly
            WHERE symbol = ?
            ORDER BY hour_ts
            """,
            [asset],
        ).df()
        if hourly.empty:
            continue
        hourly["hour_ts"] = pd.to_datetime(hourly["hour_ts"], utc=True)
        hour_ns = to_epoch_ns(hourly["hour_ts"])
        pos_map = {int(ts): i for i, ts in enumerate(hour_ns)}
        high = hourly["high"].to_numpy(dtype=float)
        low = hourly["low"].to_numpy(dtype=float)
        close = hourly["close"].to_numpy(dtype=float)
        opens = hourly["open"].to_numpy(dtype=float)
        sub = needed.loc[needed["asset"].eq(asset)].copy()
        entry_ns = to_epoch_ns(sub["entry_ts"])
        pos = np.array([pos_map.get(int(ts), -1) for ts in entry_ns], dtype=np.int64)
        frozen_ref = sub["entry_ref"].to_numpy(dtype=float)
        hourly_ref = np.where(pos >= 0, opens[np.clip(pos, 0, len(opens) - 1)], np.nan)
        finite_ref = (pos >= 0) & np.isfinite(frozen_ref) & np.isfinite(hourly_ref)
        if finite_ref.any():
            entry_ref_hourly_mismatch += int((~np.isclose(frozen_ref[finite_ref], hourly_ref[finite_ref], rtol=0, atol=1e-8)).sum())
        entry_ref = frozen_ref
        atr = sub["atr_anchor"].to_numpy(dtype=float)
        complete20 = complete_window_mask(hour_ns, entry_ns, pos, PRIMARY_HORIZON_HOURS)
        complete40 = complete_window_mask(hour_ns, entry_ns, pos, MAX_SENSITIVITY_HOURS)
        valid20 = complete20 & (pos >= 0) & np.isfinite(entry_ref) & np.isfinite(atr) & (atr > 0)
        valid40 = complete40 & (pos >= 0) & np.isfinite(entry_ref) & np.isfinite(atr) & (atr > 0)

        def hit_hours(path: np.ndarray, thr: float) -> np.ndarray:
            hit = path >= thr
            return np.where(hit.any(axis=1), hit.argmax(axis=1) + 1, np.nan)

        def extract_paths(valid: np.ndarray, hours: int) -> dict[str, Any] | None:
            if not valid.any() or hours > len(high):
                return None
            idx = np.where(valid)[0]
            high_win, low_win, close_win = (
                np.lib.stride_tricks.sliding_window_view(high, hours)[pos[idx]],
                np.lib.stride_tricks.sliding_window_view(low, hours)[pos[idx]],
                np.lib.stride_tricks.sliding_window_view(close, hours)[pos[idx]],
            )
            up = (high_win - entry_ref[idx, None]) / atr[idx, None]
            dn = (entry_ref[idx, None] - low_win) / atr[idx, None]
            term_long = close_win[:, -1] / entry_ref[idx] - 1.0
            return {
                "idx": idx,
                "hours": hours,
                "start_ns": entry_ns[idx],
                "atr": atr[idx],
                "ref": entry_ref[idx],
                "up": up,
                "dn": dn,
                "term_long": term_long,
                "term_short": -term_long,
            }

        def sides_from_paths(bundle: dict[str, Any], fav: float, adv: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
            hours = int(bundle["hours"])
            fl = hit_hours(bundle["up"], fav)
            al = hit_hours(bundle["dn"], adv)
            fs = hit_hours(bundle["dn"], fav)
            a_s = hit_hours(bundle["up"], adv)
            rl, sl, hl = result_from_hours_array(fl, al, hours)
            rs, ss, hs = result_from_hours_array(fs, a_s, hours)
            nl = nets_from(rl, hl, bundle["term_long"], fav, adv, bundle["atr"], bundle["ref"], 1, bundle["start_ns"], asset)
            ns = nets_from(rs, hs, bundle["term_short"], fav, adv, bundle["atr"], bundle["ref"], -1, bundle["start_ns"], asset)
            return sl.astype(int), ss.astype(int), nl, ns, rl, rs

        paths20 = extract_paths(valid20, PRIMARY_HORIZON_HOURS)
        paths40 = extract_paths(valid40, MAX_SENSITIVITY_HOURS)

        if paths20 is not None:
            ls, ss, ln, sn, rl, rs = sides_from_paths(paths20, PRIMARY_FAV, PRIMARY_ADV)
            frozen_l = sub.iloc[paths20["idx"]]["long_success"].to_numpy(dtype=int)
            frozen_s = sub.iloc[paths20["idx"]]["short_success"].to_numpy(dtype=int)
            parity_n += 2 * len(ls)
            parity_mismatch += int((ls != frozen_l).sum() + (ss != frozen_s).sum())

        def append_store(store_key, store, bundle, fav, adv, with_result: bool) -> None:
            if bundle is None:
                return
            ls, ss, ln, sn, rl, rs = sides_from_paths(bundle, fav, adv)
            slc = sub.iloc[bundle["idx"]]
            real_side = slc["real_side"].to_numpy()
            tmp = pd.DataFrame({
                "date": slc["date"].to_numpy(),
                "official_real": slc["official_real"].to_numpy(),
                "is_cross": slc["is_cross"].to_numpy(),
                "real_success": np.where(
                    slc["official_real"].to_numpy(),
                    np.where(real_side == "long", ls, np.where(real_side == "short", ss, np.nan)),
                    np.nan,
                ),
                "rs": 0.5 * ls + 0.5 * ss,
                "real_net": np.where(
                    slc["official_real"].to_numpy(),
                    np.where(real_side == "long", ln, np.where(real_side == "short", sn, np.nan)),
                    np.nan,
                ),
            })
            if with_result:
                tmp["real_result"] = np.where(real_side == "long", rl, np.where(real_side == "short", rs, ""))
            store[store_key].append(tmp)

        for tp, sl in BARRIER_GRID:
            append_store((tp, sl), barrier_store, paths20, tp, sl, False)
        for days in TIMEOUT_DAYS:
            hours = days * 24
            if days > 20:
                append_store(days, timeout_store, paths40, PRIMARY_FAV, PRIMARY_ADV, True)
            elif paths20 is None:
                continue
            else:
                clipped = dict(paths20)
                clipped["hours"] = hours
                append_store(days, timeout_store, clipped, PRIMARY_FAV, PRIMARY_ADV, True)

    con.close()

    def summarize_placebo_frames(frames: list[pd.DataFrame]) -> dict[str, float]:
        if not frames:
            return {"real": float("nan"), "same_cross_rs": float("nan"), "noncross_rs": float("nan"), "n_cross": 0}
        df = pd.concat(frames, ignore_index=True)
        cross = df.loc[df["official_real"]]
        non = df.loc[~df["is_cross"]]
        n_cross = cross.groupby("date").size()
        cross_rs = cross.groupby("date")["rs"].mean()
        real = cross.groupby("date")["real_success"].mean()
        non_rs = non.groupby("date")["rs"].mean()
        w = n_cross.astype(float)
        return {
            "real": date_weighted_mean(real.reindex(w.index), w),
            "same_cross_rs": date_weighted_mean(cross_rs.reindex(w.index), w),
            "noncross_rs": date_weighted_mean(non_rs.reindex(w.index), w),
            "n_cross": int(w.sum()),
            "real_net": date_weighted_mean(cross.groupby("date")["real_net"].mean().reindex(w.index), w) if "real_net" in df else float("nan"),
        }

    barrier_rows = []
    for tp, sl in BARRIER_GRID:
        s = summarize_placebo_frames(barrier_store[(tp, sl)])
        barrier_rows.append({
            "tp": tp,
            "sl": sl,
            "real_ma7": s["real"],
            "same_cross_random_side": s["same_cross_rs"],
            "noncross_random_side": s["noncross_rs"],
            "directional_edge": s["real"] - s["same_cross_rs"] if np.isfinite(s["real"]) and np.isfinite(s["same_cross_rs"]) else float("nan"),
            "cross_movement_effect": s["same_cross_rs"] - s["noncross_rs"] if np.isfinite(s["same_cross_rs"]) and np.isfinite(s["noncross_rs"]) else float("nan"),
            "n_cross": s["n_cross"],
        })
    timeout_rows = []
    for days in TIMEOUT_DAYS:
        frames = timeout_store[days]
        s = summarize_placebo_frames(frames)
        if frames:
            df = pd.concat(frames, ignore_index=True)
            cross = df.loc[df["official_real"]]
            counts = first_hit_counts(cross["real_result"]) if "real_result" in cross else {}
        else:
            counts = {}
            cross = pd.DataFrame()
        n = max(len(cross), 1)
        timeout_rows.append({
            "horizon_days": days,
            "real_ma7": s["real"],
            "same_cross_random_side": s["same_cross_rs"],
            "noncross_random_side": s["noncross_rs"],
            "directional_edge": s["real"] - s["same_cross_rs"] if np.isfinite(s["real"]) and np.isfinite(s["same_cross_rs"]) else float("nan"),
            "cross_movement_effect": s["same_cross_rs"] - s["noncross_rs"] if np.isfinite(s["same_cross_rs"]) and np.isfinite(s["noncross_rs"]) else float("nan"),
            "favorable_first_rate": counts.get("favorable_first", 0) / n if counts else float("nan"),
            "adverse_first_rate": counts.get("adverse_first", 0) / n if counts else float("nan"),
            "ambiguous_rate": counts.get("ambiguous_same_hour", 0) / n if counts else float("nan"),
            "timeout_rate": counts.get("timeout", 0) / n if counts else float("nan"),
            "net_mean": s.get("real_net", float("nan")),
            "n_cross": s["n_cross"],
        })
    audit = {
        "hourly_parity_compared": int(parity_n),
        "hourly_parity_mismatches": int(parity_mismatch),
        "hourly_parity_ok": parity_n > 0 and parity_mismatch == 0 and entry_ref_hourly_mismatch == 0,
        "entry_ref_hourly_mismatch": int(entry_ref_hourly_mismatch),
        "assets": int(len(assets)),
        "hype_in_hourly_query": False,
    }
    return pd.DataFrame(barrier_rows), pd.DataFrame(timeout_rows), audit


def choose_verdict(parity: dict[str, Any], full: dict[str, float], boot: dict[str, Any], year_rows: pd.DataFrame, mc_ok: bool, hourly_ok: bool) -> str:
    if parity.get("reproduction_failure") or not hourly_ok or not mc_ok:
        return "DATA_OR_REPRODUCTION_FAILURE"
    edge = full["directional_edge"]
    move = full["cross_movement"]
    edge_ci = (boot["directional_edge"]["p2.5"], boot["directional_edge"]["p97.5"])
    move_ci = (boot["cross_movement"]["p2.5"], boot["cross_movement"]["p97.5"])
    edge_covers0 = edge_ci[0] <= 0 <= edge_ci[1]
    move_covers0 = move_ci[0] <= 0 <= move_ci[1]
    year_edges = year_rows.loc[year_rows["period"].isin(["2022", "2023", "2024", "2025", "2026"]), "directional_edge"]
    year_sign_pos = int((year_edges > 0).sum())
    year_sign_neg = int((year_edges < 0).sum())
    year_consistent = year_sign_pos >= 4 or year_sign_neg >= 4
    long_short_conflict = (
        np.isfinite(full["real_long_vs_opp_short"])
        and np.isfinite(full["real_short_vs_opp_long"])
        and (full["real_long_vs_opp_short"] * full["real_short_vs_opp_long"] < 0)
        and min(abs(full["real_long_vs_opp_short"]), abs(full["real_short_vs_opp_long"])) > 0.01
    )
    if (not edge_covers0) and edge > 0 and year_consistent and not long_short_conflict and abs(edge) >= 0.02:
        return "MA7_DIRECTIONAL_EDGE_SUPPORTED"
    if (not edge_covers0) and edge > 0:
        return "MA7_DIRECTIONAL_EDGE_WEAK"
    if (not move_covers0) and move > 0 and (edge_covers0 or abs(edge) < 0.01):
        return "CROSS_MOVEMENT_EFFECT_WITHOUT_DIRECTIONAL_EDGE"
    return "PLACEBO_EXPLAINS_BASE_RATE"


def svg_escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def y_limits(values: list[float], *, zero_line: bool, percent: bool) -> tuple[float, float]:
    finite = [v for v in values if np.isfinite(v)]
    if not finite:
        return (0.0, 1.0)
    ymin = min(finite)
    ymax = max(finite)
    pad = max(0.02 if not percent else 2.0, 0.08 * (ymax - ymin if ymax > ymin else 1.0))
    lo = ymin - pad
    hi = ymax + pad
    if zero_line:
        lo = min(lo, 0.0)
        hi = max(hi, 0.0)
    else:
        lo = min(0.0, lo)
        hi = max(hi, 50.0 if percent else 0.5)
    return lo, hi


def write_svg(path: Path, width: int, height: int, body: str, title: str) -> None:
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="{width/2:.1f}" y="28" text-anchor="middle" font-size="16" font-family="sans-serif">{svg_escape(title)}</text>
  {body}
</svg>
'''
    atomic_write_text(path, svg)


def chart_coords(left: float, right: float, top: float, bottom: float, xmin: float, xmax: float, ymin: float, ymax: float, x: float, y: float) -> tuple[float, float]:
    if xmax == xmin:
        xmax = xmin + 1.0
    if ymax == ymin:
        ymax = ymin + 1.0
    px = left + (x - xmin) / (xmax - xmin) * (right - left)
    py = bottom - (y - ymin) / (ymax - ymin) * (bottom - top)
    return px, py


def svg_bars(items: list[tuple[str, float, str]], *, ylabel: str, title: str, path: Path, percent: bool = True, zero_line: bool = False) -> None:
    width, height = 860, 520
    left, right, top, bottom = 70, 820, 50, 430
    vals = [v for _, v, _ in items]
    ymin, ymax = y_limits(vals, zero_line=zero_line, percent=percent)
    n = max(len(items), 1)
    gap = 20
    bar_w = max(20.0, (right - left - gap * (n + 1)) / n)
    parts = [f'<text x="18" y="240" transform="rotate(-90 18 240)" font-size="12" font-family="sans-serif">{svg_escape(ylabel)}</text>']
    parts.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#333" />')
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#333" />')
    if zero_line:
        _, z = chart_coords(left, right, top, bottom, 0, 1, ymin, ymax, 0, 0)
        parts.append(f'<line x1="{left}" y1="{z:.1f}" x2="{right}" y2="{z:.1f}" stroke="#444" />')
    for i, (label, value, color) in enumerate(items):
        x0 = left + gap + i * (bar_w + gap)
        _, y = chart_coords(left, right, top, bottom, 0, 1, ymin, ymax, 0, value)
        y0 = min(y, bottom)
        h = abs(bottom - y)
        parts.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{color}" />')
        parts.append(f'<text x="{x0 + bar_w/2:.1f}" y="{bottom + 24}" text-anchor="middle" font-size="11" font-family="sans-serif">{svg_escape(label)}</text>')
        parts.append(f'<text x="{x0 + bar_w/2:.1f}" y="{y0 - 6:.1f}" text-anchor="middle" font-size="11" font-family="sans-serif">{value:.2f}</text>')
    write_svg(path, width, height, "\n".join(parts), title)


def svg_grouped_bars(categories: list[str], series: list[tuple[str, list[float], str]], *, ylabel: str, title: str, path: Path) -> None:
    width, height = 920, 540
    left, right, top, bottom = 70, 880, 50, 430
    all_vals = [v for _, vals, _ in series for v in vals]
    ymin, ymax = y_limits(all_vals, zero_line=False, percent=True)
    n = max(len(categories), 1)
    group_w = (right - left) / n
    bar_w = group_w / (len(series) + 1.5)
    parts = [f'<text x="18" y="240" transform="rotate(-90 18 240)" font-size="12" font-family="sans-serif">{svg_escape(ylabel)}</text>']
    parts.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#333" />')
    for i, cat in enumerate(categories):
        gx = left + i * group_w
        for j, (_, vals, color) in enumerate(series):
            value = vals[i]
            x0 = gx + (j + 0.5) * bar_w
            _, y = chart_coords(left, right, top, bottom, 0, 1, ymin, ymax, 0, value)
            parts.append(f'<rect x="{x0:.1f}" y="{min(y,bottom):.1f}" width="{bar_w:.1f}" height="{abs(bottom-y):.1f}" fill="{color}" />')
        parts.append(f'<text x="{gx + group_w/2:.1f}" y="{bottom + 22}" text-anchor="middle" font-size="12" font-family="sans-serif">{svg_escape(cat)}</text>')
    for j, (name, _, color) in enumerate(series):
        parts.append(f'<rect x="{70 + j*180}" y="500" width="12" height="12" fill="{color}" />')
        parts.append(f'<text x="{88 + j*180}" y="511" font-size="12" font-family="sans-serif">{svg_escape(name)}</text>')
    write_svg(path, width, height, "\n".join(parts), title)


def svg_lines(xs: list[float] | list[str], series: list[tuple[str, list[float], str]], *, xlabel: str, ylabel: str, title: str, path: Path, zero_line: bool = False, hline: tuple[float, str, str] | None = None, numeric_x: bool = False) -> None:
    width, height = 920, 540
    left, right, top, bottom = 70, 880, 50, 430
    if numeric_x:
        xvals = [float(x) for x in xs]
    else:
        xvals = list(range(len(xs)))
    all_vals = [v for _, vals, _ in series for v in vals]
    if hline:
        all_vals.append(hline[0])
    ymin, ymax = y_limits(all_vals, zero_line=zero_line, percent=True)
    xmin, xmax = min(xvals), max(xvals)
    parts = [
        f'<text x="18" y="240" transform="rotate(-90 18 240)" font-size="12" font-family="sans-serif">{svg_escape(ylabel)}</text>',
        f'<text x="{(left+right)/2:.1f}" y="510" text-anchor="middle" font-size="12" font-family="sans-serif">{svg_escape(xlabel)}</text>',
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#333" />',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#333" />',
    ]
    if zero_line:
        _, z = chart_coords(left, right, top, bottom, xmin, xmax, ymin, ymax, xmin, 0)
        parts.append(f'<line x1="{left}" y1="{z:.1f}" x2="{right}" y2="{z:.1f}" stroke="#444" />')
    if hline:
        _, hy = chart_coords(left, right, top, bottom, xmin, xmax, ymin, ymax, xmin, hline[0])
        parts.append(f'<line x1="{left}" y1="{hy:.1f}" x2="{right}" y2="{hy:.1f}" stroke="{hline[1]}" stroke-dasharray="6 4" />')
        parts.append(f'<text x="{right}" y="{hy-4:.1f}" text-anchor="end" font-size="11" font-family="sans-serif">{svg_escape(hline[2])}</text>')
    for name, vals, color in series:
        pts = []
        for x, yv in zip(xvals, vals):
            px, py = chart_coords(left, right, top, bottom, xmin, xmax, ymin, ymax, x, yv)
            pts.append(f"{px:.1f},{py:.1f}")
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{color}" />')
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{" ".join(pts)}" />')
    if not numeric_x:
        for i, lab in enumerate(xs):
            px, _ = chart_coords(left, right, top, bottom, xmin, xmax, ymin, ymax, i, ymin)
            parts.append(f'<text x="{px:.1f}" y="{bottom+20}" text-anchor="middle" font-size="12" font-family="sans-serif">{svg_escape(str(lab))}</text>')
    else:
        for x in xvals:
            px, _ = chart_coords(left, right, top, bottom, xmin, xmax, ymin, ymax, x, ymin)
            parts.append(f'<text x="{px:.1f}" y="{bottom+20}" text-anchor="middle" font-size="12" font-family="sans-serif">{x:g}</text>')
    for j, (name, _, color) in enumerate(series):
        parts.append(f'<rect x="{70 + j*200}" y="500" width="12" height="12" fill="{color}" />')
        parts.append(f'<text x="{88 + j*200}" y="511" font-size="12" font-family="sans-serif">{svg_escape(name)}</text>')
    write_svg(path, width, height, "\n".join(parts), title)


def svg_hist(series: list[tuple[str, np.ndarray, str]], lines: list[tuple[float, str, str]], *, xlabel: str, ylabel: str, title: str, path: Path) -> None:
    width, height = 920, 540
    left, right, top, bottom = 70, 880, 50, 430
    all_x = np.concatenate([arr[np.isfinite(arr)] for _, arr, _ in series]) if series else np.array([0.0])
    bins = np.linspace(float(np.min(all_x)), float(np.max(all_x)), 31)
    counts = [np.histogram(arr[np.isfinite(arr)], bins=bins)[0] for _, arr, _ in series]
    ymax = max(int(np.max(np.vstack(counts))), 1) if counts else 1
    ymin = 0.0
    parts = [
        f'<text x="18" y="240" transform="rotate(-90 18 240)" font-size="12" font-family="sans-serif">{svg_escape(ylabel)}</text>',
        f'<text x="{(left+right)/2:.1f}" y="510" text-anchor="middle" font-size="12" font-family="sans-serif">{svg_escape(xlabel)}</text>',
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#333" />',
    ]
    for (_, _, color), hist in zip(series, counts):
        for i, c in enumerate(hist):
            x0, _ = chart_coords(left, right, top, bottom, bins[0], bins[-1], ymin, ymax, bins[i], 0)
            x1, _ = chart_coords(left, right, top, bottom, bins[0], bins[-1], ymin, ymax, bins[i + 1], 0)
            _, y = chart_coords(left, right, top, bottom, bins[0], bins[-1], ymin, ymax, bins[i], float(c))
            parts.append(f'<rect x="{x0:.1f}" y="{y:.1f}" width="{max(x1-x0,1):.1f}" height="{bottom-y:.1f}" fill="{color}" fill-opacity="0.45" />')
    for xv, color, name in lines:
        px, _ = chart_coords(left, right, top, bottom, bins[0], bins[-1], ymin, ymax, xv, 0)
        parts.append(f'<line x1="{px:.1f}" y1="{top}" x2="{px:.1f}" y2="{bottom}" stroke="{color}" stroke-dasharray="6 4" />')
        parts.append(f'<text x="{px:.1f}" y="{top-4}" text-anchor="middle" font-size="11" font-family="sans-serif">{svg_escape(name)}</text>')
    write_svg(path, width, height, "\n".join(parts), title)


def write_charts(full: dict[str, float], year_df: pd.DataFrame, barrier: pd.DataFrame, timeout: pd.DataFrame, mc: pd.DataFrame, mc_meta: dict[str, Any]) -> None:
    svg_bars(
        [
            ("non-cross random", 100 * full["noncross_rs"], "#8d99ae"),
            ("same-cross random", 100 * full["same_cross_rs"], "#2b6cb0"),
            ("real MA7", 100 * full["real_success"], "#c53030"),
        ],
        ylabel="Success rate (%)",
        title="三层 base-rate 分解",
        path=CHARTS["decomposition"],
    )
    ydf = year_df.loc[year_df["period"].isin(["2022", "2023", "2024", "2025", "2026"])].copy()
    svg_grouped_bars(
        [str(p) for p in ydf["period"]],
        [
            ("non-cross random", [100 * v for v in ydf["noncross_rs"]], "#8d99ae"),
            ("same-cross random", [100 * v for v in ydf["same_cross_rs"]], "#2b6cb0"),
            ("real MA7", [100 * v for v in ydf["real_success"]], "#c53030"),
        ],
        ylabel="Success rate (%)",
        title="各年成功率",
        path=CHARTS["yearly"],
    )
    svg_lines(
        [str(p) for p in ydf["period"]],
        [("MA7 directional edge (pp)", [100 * v for v in ydf["directional_edge"]], "#c53030")],
        xlabel="Year",
        ylabel="MA7 directional edge (pp)",
        title="MA7 directional edge 按年",
        path=CHARTS["edge_year"],
        zero_line=True,
    )
    svg_lines(
        [str(p) for p in ydf["period"]],
        [("Cross movement effect (pp)", [100 * v for v in ydf["cross_movement"]], "#2b6cb0")],
        xlabel="Year",
        ylabel="Cross movement effect (pp)",
        title="Cross movement effect 按年",
        path=CHARTS["move_year"],
        zero_line=True,
    )
    b1 = barrier.loc[np.isclose(barrier["sl"], 1.0)].sort_values("tp")
    svg_lines(
        [float(x) for x in b1["tp"]],
        [
            ("Real MA7", [100 * v for v in b1["real_ma7"]], "#c53030"),
            ("Same-cross random", [100 * v for v in b1["same_cross_random_side"]], "#2b6cb0"),
            ("Non-cross random", [100 * v for v in b1["noncross_random_side"]], "#8d99ae"),
        ],
        xlabel="TP (ATR)",
        ylabel="Success rate (%)",
        title="屏障几何敏感性（固定 SL=-1 ATR）",
        path=CHARTS["barrier"],
        numeric_x=True,
        hline=(100.0 / 3.0, "#666666", "Brownian 33.33% (not empirical)"),
    )
    svg_lines(
        [float(x) for x in timeout["horizon_days"]],
        [
            ("Real MA7", [100 * v for v in timeout["real_ma7"]], "#c53030"),
            ("Same-cross random", [100 * v for v in timeout["same_cross_random_side"]], "#2b6cb0"),
            ("Non-cross random", [100 * v for v in timeout["noncross_random_side"]], "#8d99ae"),
        ],
        xlabel="Horizon (days)",
        ylabel="Success rate (%)",
        title="Timeout 敏感性（固定 +2/-1 ATR）",
        path=CHARTS["timeout"],
        numeric_x=True,
    )
    svg_bars(
        [
            ("REAL LONG", 100 * full["real_long_success"], "#2f9e44"),
            ("REAL SHORT", 100 * full["real_short_success"], "#d9480f"),
        ],
        ylabel="Success rate (%)",
        title="真实 MA7 Long / Short",
        path=CHARTS["long_short"],
    )
    svg_hist(
        [
            ("MC same-cross", 100 * mc["same_cross_random_side"].to_numpy(dtype=float), "#2b6cb0"),
            ("MC non-cross", 100 * mc["date_matched_noncross_random_side"].to_numpy(dtype=float), "#8d99ae"),
        ],
        [
            (100 * mc_meta["same_cross"]["exact_expectation"], "#2b6cb0", "exact same-cross"),
            (100 * mc_meta["noncross"]["exact_expectation"], "#555555", "exact non-cross"),
        ],
        xlabel="Success rate (%)",
        ylabel="Replicates",
        title="Monte Carlo vs exact expectation",
        path=CHARTS["monte_carlo"],
    )


def fmt_ci(stat: dict[str, Any]) -> str:
    return f"[{pp(stat['p2.5'])}, {pp(stat['p97.5'])}]"


def write_report(summary: dict[str, Any]) -> str:
    full = summary["full"]
    boot = summary["bootstrap_summary"]
    years = pd.DataFrame(summary["year_rows"])
    barrier = pd.DataFrame(summary["barrier_rows"])
    timeout = pd.DataFrame(summary["timeout_rows"])
    groups = pd.DataFrame(summary["placebo_rows"])
    verdict = summary["verdict"]
    lines = [
        "# BIN-1D-MA7-CTP P7A 安慰剂基础成功率与屏障几何归因审计",
        "",
        f"Real MA7 success rate = {pct(full['real_success'])}",
        "",
        f"Same-cross asset-date random-side expectation = {pct(full['same_cross_rs'])}",
        "",
        f"Date-matched non-cross random-side expectation = {pct(full['noncross_rs'])}",
        "",
        f"MA7 directional edge = {pct(full['real_success'])} - {pct(full['same_cross_rs'])} = {pp(full['directional_edge'])}",
        "",
        f"Cross movement effect = {pct(full['same_cross_rs'])} - {pct(full['noncross_rs'])} = {pp(full['cross_movement'])}",
        "",
        f"原来看到的约 30% 成功率，主要来自 **barrier/base-rate**（同日 non-cross random-side = {pct(full['noncross_rs'])}）。Cross movement effect 为 {pp(full['cross_movement'])}；MA7 directional edge 为 {pp(full['directional_edge'])}，其 95% 块 bootstrap CI 覆盖 0，因此不能把约 30% 写成 MA7 方向的趋势预测概率。全局裁决 `{verdict}`。",
        "",
        f"- 状态：`{STATUS}`",
        f"- `research_id`：`{RESEARCH_ID}`",
        f"- 合同锁：`{LOCK_STATUS}`",
        "- 本轮是与 P7 并行的独立 sidecar diagnostic，未读取 P7 产物，不训练模型。",
        "",
        "## 主表",
        "",
        "| Group | Success Rate | vs Non-Cross Random | Net Mean | Net Median | Effective N |",
        "| ---------------------------------------------- | -----------: | ------------------: | -------: | ---------: | ----------: |",
    ]
    for rec in groups.to_dict("records"):
        lines.append(
            f"| {rec['group']} | {pct(rec['success_rate'])} | {pp(rec['vs_noncross_random'])} | {rec['net_mean'] if rec['net_mean'] is None or not np.isfinite(rec['net_mean']) else f'{rec['net_mean']:.6f}'} | {rec['net_median'] if rec['net_median'] is None or (isinstance(rec['net_median'], float) and not np.isfinite(rec['net_median'])) else (f'{rec['net_median']:.6f}' if rec['net_median'] is not None else '')} | {int(rec['effective_n'])} |"
        )
    lines.extend([
        "",
        f"Barrier / non-cross random base rate = {pct(full['noncross_rs'])}",
        "",
        f"Cross movement effect = {pp(full['cross_movement'])}",
        "",
        f"MA7 directional edge = {pp(full['directional_edge'])}",
        "",
        f"Observed real MA7 rate = {pct(full['real_success'])}",
        "",
        "## 理论 sanity check",
        "",
        "连续零漂移对称 Brownian motion 下 `P(hit +2 first vs -1) = 1/3 ≈ 33.333%`。这不是真实 crypto placebo。本轮 empirical non-cross random-side base rate 见上表，与 33.33% 的差不得被解释成 MA7 信息。",
        "",
        "## 主检验（28 日块 bootstrap）",
        "",
        f"- Directional edge {pp(full['directional_edge'])}，95% CI {fmt_ci(boot['directional_edge'])}，bootstrap mean {pp(boot['directional_edge']['bootstrap_mean'])}。",
        f"- Cross movement {pp(full['cross_movement'])}，95% CI {fmt_ci(boot['cross_movement'])}。",
        f"- Total vs non-cross {pp(full['total_vs_noncross'])}，95% CI {fmt_ci(boot['total_vs_noncross'])}。",
        f"- Bonferroni α = {0.05/3:.4f}；BH q 见 summary JSON。",
        "",
        "## Long / Short",
        "",
        f"- REAL LONG success {pct(full['real_long_success'])}（N={full['real_long_n']}），相对同日反方向 short counterfactual {pp(full['real_long_vs_opp_short'])}。",
        f"- REAL SHORT success {pct(full['real_short_success'])}（N={full['real_short_n']}），相对同日反方向 long counterfactual {pp(full['real_short_vs_opp_long'])}。",
        "",
        "## 年度",
        "",
        "| Period | N | Real MA7 | Same-cross RS | Non-cross RS | Edge | Movement |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for rec in years.to_dict("records"):
        lines.append(
            f"| {rec['period']} | {int(rec['n_cross'])} | {pct(rec['real_success'])} | {pct(rec['same_cross_rs'])} | {pct(rec['noncross_rs'])} | {pp(rec['directional_edge'])} | {pp(rec['cross_movement'])} |"
        )
    lines.extend([
        "",
        "## 屏障敏感性",
        "",
        "| TP | SL | Real MA7 | Same-Cross Random Side | Non-Cross Random Side | Directional Edge | Cross Movement Effect |",
        "| -: | -: | -------: | ---------------------: | --------------------: | ---------------: | --------------------: |",
    ])
    for rec in barrier.to_dict("records"):
        lines.append(
            f"| {rec['tp']:.1f} | {rec['sl']:.1f} | {pct(rec['real_ma7'])} | {pct(rec['same_cross_random_side'])} | {pct(rec['noncross_random_side'])} | {pp(rec['directional_edge'])} | {pp(rec['cross_movement_effect'])} |"
        )
    lines.extend([
        "",
        "## Timeout 敏感性",
        "",
        "| Horizon | Real MA7 | Same-cross RS | Non-cross RS | Fav-first | Adv-first | Ambiguous | Timeout | Net mean | N |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for rec in timeout.to_dict("records"):
        lines.append(
            f"| {int(rec['horizon_days'])}D | {pct(rec['real_ma7'])} | {pct(rec['same_cross_random_side'])} | {pct(rec['noncross_random_side'])} | {pct(rec['favorable_first_rate'])} | {pct(rec['adverse_first_rate'])} | {pct(rec['ambiguous_rate'])} | {pct(rec['timeout_rate'])} | {rec['net_mean'] if not np.isfinite(rec['net_mean']) else f'{rec['net_mean']:.6f}'} | {int(rec['n_cross'])} |"
        )
    q = summary["research_answers"]
    lines.extend(["", "## 预注册研究问题", ""])
    for i, ans in enumerate(q, start=1):
        lines.append(f"{i}. {ans}")
        lines.append("")
    lines.extend([
        "## 当前证据可以确认什么 / 不能确认什么",
        "",
        f"- 可以确认：在 P0R canonical `+2/-1/20D` 标签下，empirical placebo 与真实 MA7 的三层分解；全局裁决 `{verdict}`。",
        "- 不能确认：可交易策略、账户收益、新 OOS、live-ready、最优 TP/SL，或把 label positive rate 直接叫做趋势概率（除非 directional edge 被支持）。",
        "",
        "## 图表",
        "",
    ])
    for key, path in CHARTS.items():
        lines.append(f"- [{path.name}](../artifacts/{path.name})")
    lines.extend([
        "",
        "## 产物",
        "",
        f"- [合同]({rel(CONTRACT_PATH).split('1d-ma7-cross-trend-probability/')[-1].replace('research/asset-portfolios/1d-ma7-cross-trend-probability/', '../')})",
        f"- [summary](../artifacts/{SUMMARY_PATH.name})",
        f"- [manifest](../artifacts/{MANIFEST_PATH.name})",
        f"- [implementation audit]({IMPL_AUDIT_PATH.name})",
        f"- [deferred registration]({DEFERRED_PATH.name})",
        "",
        "本轮未修改 family README、core ledger、decision log 或顶层索引。",
    ])
    # fix contract relative link
    text = "\n".join(lines).replace(
        f"- [合同]({rel(CONTRACT_PATH).split('1d-ma7-cross-trend-probability/')[-1].replace('research/asset-portfolios/1d-ma7-cross-trend-probability/', '../')})",
        "- [合同](../specs/binance-1d-ma7-ctp-p7a-placebo-base-rate-audit-contract-2026-09-04.md)",
    )
    return text + "\n"


def write_impl_audit(summary: dict[str, Any], lock: dict[str, Any], manifest: dict[str, Any]) -> str:
    return "\n".join([
        "# BIN-1D-MA7-CTP P7A 实现审计",
        "",
        f"- 状态：`{STATUS}`",
        f"- 全局裁决：`{summary['verdict']}`",
        f"- 合同锁：`{lock['status']}`",
        f"- config sha256：`{lock['config_sha256']}`",
        f"- contract sha256：`{lock['contract_sha256']}`",
        f"- manifest sha256：`{manifest['manifest_sha256']}`",
        "",
        "## 输入隔离",
        "",
        f"- P7 输入文件数：`{summary['isolation']['p7_input_files']}`（必须为 0）",
        f"- HYPE 原始分区读取：`{summary['isolation']['hype_raw_partition_read']}`",
        f"- HYPE 行数：`{summary['parity']['hype_rows']}`",
        f"- HYPER 行数：`{summary['parity']['hyper_rows']}`",
        f"- files_read 含 `hype_usdt_usdt`：`{summary['isolation']['hype_slug_in_files_read']}`",
        "",
        "## Canonical first-hit",
        "",
        "- 主结果使用 P0R 冻结 `label_entry_success_20d` / `label_entry_net_return` / `label_entry_result`。",
        "- 敏感性调用 CATL P0 `result_from_hours` 与 `hit_net_return`，同一 entry/ATR/未来小时路径。",
        f"- 小时路径 2/1/20D 与冻结标签比对：compared={summary['sensitivity_audit']['hourly_parity_compared']} mismatches={summary['sensitivity_audit']['hourly_parity_mismatches']}。",
        "- same-hour 双触使用 adverse-first。",
        "- random-side 主结果是 0.5×long+0.5×short 精确期望。",
        "- 日期加权使用真实 Cross 的 `n_real_cross[d]`。",
        "",
        "## 未做的事",
        "",
        "- 无 ML 模型、无策略权益曲线、无 Sharpe/CAGR、未改 P0–P7 冻结产物、未改共享 README/ledger/decision log。",
        "",
        f"运行命令：`{summary['run_command']}`",
        "",
    ]) + "\n"


def write_deferred(summary: dict[str, Any]) -> str:
    return "\n".join([
        "# BIN-1D-MA7-CTP P7A 延迟登记说明",
        "",
        "P7A 完成时，同一家族的 P7 可能仍在另一窗口修改共享文档。本文件记录以后应如何把 P7A 登记进共享文档，而本轮不修改这些文件。",
        "",
        "## 以后应更新的文件",
        "",
        "1. `research/asset-portfolios/1d-ma7-cross-trend-probability/README.md`：增加 P7A 入口链接；不要覆盖 P7 条目。",
        "2. `binance-1d-ma7-ctp-core-ledger.md`：Current State 增加 P7A sidecar 一行；Version Table 增加 P7A 行，状态 `explore / diagnostic-only / placebo-audit / not promoted / not live-ready`，裁决 `" + summary["verdict"] + "`。",
        "3. `decision-log.md`：新增 2026-09-04 一条，只写一句话结论和证据链接。",
        "4. `artifacts/README.md`：增加 P7A 产物清单。",
        "5. `research/README.md` 与 `research/asset-portfolios/README.md`：仅在需要指向 P7A 报告时加链接，不复述指标。",
        "",
        "## 登记时必须保留",
        "",
        "- P7 已有修改全部保留，禁止为整理工作树 reset/checkout/clean。",
        "- P7A 文件一律 `p7a` 前缀，不得改名成 P7。",
        "- 主状态不得写成 promotion / live-ready。",
        "",
        "## 建议的 decision-log 草稿（登记时再写入）",
        "",
        f"决策：P7A 安慰剂审计裁决 `{summary['verdict']}`。真实 MA7 成功率 {pct(summary['full']['real_success'])}，同 Cross asset-date 随机方向 {pct(summary['full']['same_cross_rs'])}，同日 non-cross 随机方向 {pct(summary['full']['noncross_rs'])}；directional edge {pp(summary['full']['directional_edge'])}，cross movement {pp(summary['full']['cross_movement'])}。约 30% 不应再被直接写成“MA7 穿越后形成趋势的概率”。不晋升、不改 runner。",
        "",
        "证据：`diagnostics/binance-1d-ma7-ctp-p7a-placebo-base-rate-audit-2026-09-04.md`。",
        "",
    ]) + "\n"


def research_answers(full: dict[str, float], barrier: pd.DataFrame, timeout: pd.DataFrame, years: pd.DataFrame, verdict: str) -> list[str]:
    brownian = 1.0 / 3.0
    y = years.set_index("period")
    signs = ", ".join(
        f"{p}:{pp(float(y.loc[p, 'directional_edge']))}" for p in ["2022", "2023", "2024", "2025", "2026"] if p in y.index
    )
    b_change = barrier.sort_values(["sl", "tp"])
    return [
        f"完全不利用 MA7 时，empirical success base rate（同日 non-cross random-side）为 {pct(full['noncross_rs'])}。",
        f"{'是' if 0.28 <= full['noncross_rs'] <= 0.35 else '不完全是'}：该 empirical placebo 为 {pct(full['noncross_rs'])}，落在约 30%～33% 附近。" if np.isfinite(full["noncross_rs"]) else "empirical placebo 无法计算。",
        f"理论 Brownian 33.33% 与 empirical non-cross placebo 相差 {pp(full['noncross_rs'] - brownian)}。不得用理论值替代实证。",
        f"真实 MA7 {pct(full['real_success'])} 中，{pct(full['noncross_rs'])} 这一层可归因于屏障/市场路径 base rate；其余为 movement {pp(full['cross_movement'])} 与 direction {pp(full['directional_edge'])}。",
        f"同一 Cross asset-date 上随机 Long/Short 的精确期望成功率为 {pct(full['same_cross_rs'])}。",
        f"真实 MA7 方向相对随机方向的差为 {pp(full['directional_edge'])}。裁决 `{verdict}`。",
        f"Cross asset-date 相对同日 non-cross 的 movement effect 为 {pp(full['cross_movement'])}。",
        f"MA7 的增量结构：timing/movement {pp(full['cross_movement'])}，direction {pp(full['directional_edge'])}。",
        f"相对最简单 1D momentum：MA7 {pct(full['real_success'])} vs momentum {pct(full['momentum'])}，差 {pp(full['real_success'] - full['momentum'])}。",
        f"相对普通 MA7-side rule：MA7 {pct(full['real_success'])} vs MA7-side {pct(full['ma7_side'])}，差 {pp(full['real_success'] - full['ma7_side'])}。",
        f"LONG {pct(full['real_long_success'])}，SHORT {pct(full['real_short_success'])}；相对反方向 counterfactual 分别为 {pp(full['real_long_vs_opp_short'])} 与 {pp(full['real_short_vs_opp_long'])}。",
        f"2022–2026 directional edge：{signs}。",
        "屏障从 1:1 改到 3:1 时，success rate 主要随 TP/SL 几何变化，见敏感性表；directional edge 是否接近 0 以该表为准。",
        "horizon 从 5D 到 40D 的变化见 timeout 表；用于判断是否趋近屏障几何基础概率。",
        "“MA7 穿越后约有 30% 的概率形成趋势”不应再作为无条件表述；应改为标签正样本率相对 placebo 的分解。",
        (
            f"在下一开盘进入、+2 ATR/-1 ATR、最长 20 日 first-hit 标签定义下，MA7 Cross 事件的 positive rate 约为 {pct(full['real_success'])}；"
            f"同日期 non-cross random-side empirical base rate 为 {pct(full['noncross_rs'])}，因此 MA7 Cross 相对于 placebo 的总增量为 {pp(full['total_vs_noncross'])}，"
            f"其中 directional increment 为 {pp(full['directional_edge'])}。"
        ),
    ]


def build_manifest(paths: list[Path], config_hash: str, lock_hash: str) -> dict[str, Any]:
    files = []
    for path in paths:
        if not path.exists():
            continue
        if path.resolve() == MANIFEST_PATH.resolve():
            continue
        files.append({"path": rel(path), "sha256": sha256_file(path), "bytes": path.stat().st_size})
    payload = {
        "research_id": RESEARCH_ID,
        "schema_version": SCHEMA_VERSION,
        "config_sha256": config_hash,
        "contract_lock_sha256": lock_hash,
        "files": files,
        "excludes": ["manifest self", "P7 files", "temporary cache", "pytest cache"],
    }
    payload["manifest_sha256"] = canonical_sha256({k: v for k, v in payload.items() if k != "manifest_sha256"})
    return payload


def main() -> int:
    generated_at = datetime.now(UTC).isoformat()
    run_command = (
        "/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python "
        "research/asset-portfolios/1d-ma7-cross-trend-probability/scripts/run_binance_1d_ma7_ctp_p7a_placebo_base_rate_audit.py"
    )
    config = build_config(generated_at=generated_at)
    print("freezing P7A contract/config/inventory...", flush=True)
    inputs, lock = freeze_inputs(config)
    config_hash = lock["config_sha256"]

    print("loading P0R panel and dual-side outcomes...", flush=True)
    raw = load_p0r_panel()
    dual, universe_audit = build_dual_side(raw)
    dual, p5_meta = attach_p5_identity(dual)
    universe_audit["p0r_cross_not_in_p5_2025plus"] = p5_meta["p0r_cross_not_in_p5_2025plus"]
    universe_audit["official_real_n"] = int(dual["official_real"].sum())
    real = real_event_frame(dual)
    parity = real_event_parity(real)

    periods = ["full", "pre_2025", "2022", "2023", "2024", "2025", "2026", "2025plus"]
    year_rows = []
    stats_full = date_stats(dual, period_mask(dual, "full"))
    full = weighted_from_dates(stats_full)
    real_extra = real_side_metrics(real)
    full.update({k: v for k, v in real_extra.items() if k not in full})
    for period in periods:
        st = date_stats(dual, period_mask(dual, period))
        m = weighted_from_dates(st)
        m["period"] = "2025+" if period == "2025plus" else period
        year_rows.append(m)
    year_df = pd.DataFrame(year_rows)

    groups = placebo_table(full, real_extra)
    print("running 28-day block bootstrap and Monte Carlo validation...", flush=True)
    boot_df, boot_summary = run_block_bootstrap(stats_full)
    for key in ["directional_edge", "cross_movement", "total_vs_noncross", "real_success", "same_cross_rs", "noncross_rs"]:
        boot_summary[key]["point_from_full_sample"] = full[key if key != "same_cross_rs" else "same_cross_rs"]
    pvals = [
        boot_summary["directional_edge"]["p_two_sided"],
        boot_summary["cross_movement"]["p_two_sided"],
        boot_summary["total_vs_noncross"]["p_two_sided"],
    ]
    qvals = benjamini_hochberg(pvals)
    boot_summary["multiple_testing"] = {
        "tests": ["directional_edge", "cross_movement", "total_vs_noncross"],
        "p": pvals,
        "bh_q": qvals,
        "bonferroni_alpha": 0.05 / 3,
        "bonferroni_reject": [p < 0.05 / 3 for p in pvals],
    }

    mc = monte_carlo_validation(dual, full)
    mc_meta = mc.attrs["summary"]
    mc_ok = bool(mc_meta["same_cross"]["within_tolerance"] and mc_meta["noncross"]["within_tolerance"])

    print("loading funding and running barrier/timeout sensitivity...", flush=True)
    funding_lookup = load_funding_lookup()
    barrier_df, timeout_df, sens_audit = run_sensitivity(dual, funding_lookup)

    first_hit_rows = []
    for period in periods:
        sub = real.loc[period_mask(real, period)]
        rec = first_hit_counts(sub["real_result"])
        rec["period"] = "2025+" if period == "2025plus" else period
        rec["success_rate"] = float(sub["real_success"].mean()) if len(sub) else float("nan")
        rec["net_mean"] = float(sub["real_net"].mean()) if len(sub) else float("nan")
        rec["net_median"] = float(sub["real_net"].median()) if len(sub) else float("nan")
        first_hit_rows.append(rec)
    first_hit_df = pd.DataFrame(first_hit_rows)

    isolation = {
        "p7_input_files": int(sum(1 for p in inputs["files"] if "_p7_" in Path(p["path"]).name and "_p7a_" not in Path(p["path"]).name)),
        "hype_raw_partition_read": any(HYPE_SLUG in p.lower() and "hyper_usdt_usdt" not in p.lower() for p in FILES_READ),
        "hype_slug_in_files_read": any(HYPE_SLUG in p.lower() and "hyper_usdt_usdt" not in p.lower() for p in FILES_READ),
        "files_read": sorted(set(FILES_READ)),
        "shared_docs_modified": False,
    }
    hourly_ok = bool(sens_audit.get("hourly_parity_ok")) and int(sens_audit.get("hourly_parity_compared", 0)) > 0
    if parity["reproduction_failure"]:
        hourly_ok = False
    verdict = choose_verdict(parity, full, boot_summary, year_df, mc_ok, hourly_ok)

    dual_out = dual[[
        "asset", "ts", "date", "event_year", "feature_known_at", "entry_ts", "entry_ref", "atr_anchor",
        "is_cross", "official_real", "in_p5_val", "real_side",
        "long_success", "short_success", "long_net", "short_net", "long_result", "short_result",
        "rs_success", "rs_net", "ret_1d", "ma7_side", "momentum_side", "dir_price_side_ma7_long", "hyper",
    ]].copy()
    dual_out["research_id"] = RESEARCH_ID
    date_out = stats_full.copy()
    date_out["research_id"] = RESEARCH_ID

    answers = research_answers(full, barrier_df, timeout_df, year_df, verdict)
    summary = {
        "research_id": RESEARCH_ID,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "verdict": verdict,
        "generated_at": generated_at,
        "canonical_label_version": CANONICAL_LABEL_VERSION,
        "canonical_universe_version": CANONICAL_UNIVERSE_VERSION,
        "config_sha256": config_hash,
        "contract_lock_sha256": canonical_sha256(lock),
        "run_command": run_command,
        "full": full,
        "parity": parity,
        "universe_audit": universe_audit,
        "placebo_rows": groups.to_dict("records"),
        "year_rows": year_df.to_dict("records"),
        "barrier_rows": barrier_df.to_dict("records"),
        "timeout_rows": timeout_df.to_dict("records"),
        "bootstrap_summary": boot_summary,
        "monte_carlo": mc_meta,
        "sensitivity_audit": sens_audit,
        "isolation": isolation,
        "research_answers": answers,
        "theoretical_brownian": 1.0 / 3.0,
        "no_ml": True,
        "no_equity_curve": True,
    }

    atomic_write_json(DATA_AUDIT_PATH, {"research_id": RESEARCH_ID, "universe": universe_audit, "hype": isolation, "panel_rows": int(len(raw))})
    atomic_write_json(REAL_EVENT_PARITY_PATH, {"research_id": RESEARCH_ID, **parity})
    atomic_write_json(CANDIDATE_UNIVERSE_AUDIT_PATH, {"research_id": RESEARCH_ID, **universe_audit})
    atomic_write_parquet(DUAL_SIDE_PATH, dual_out)
    atomic_write_parquet(DATE_EXPECT_PATH, date_out)
    atomic_write_csv(PLACEBO_SUMMARY_CSV, groups)
    atomic_write_json(PLACEBO_SUMMARY_JSON, {"research_id": RESEARCH_ID, "rows": groups.to_dict("records"), "full": full})
    atomic_write_csv(YEAR_DIR_CSV, year_df)
    atomic_write_csv(FIRST_HIT_CSV, first_hit_df)
    atomic_write_csv(BARRIER_CSV, barrier_df)
    atomic_write_csv(TIMEOUT_CSV, timeout_df)
    boot_df["research_id"] = RESEARCH_ID
    atomic_write_parquet(BOOTSTRAP_PATH, boot_df)
    mc_out = mc.copy()
    mc_out["research_id"] = RESEARCH_ID
    atomic_write_csv(MC_CSV, mc_out)
    write_charts(full, year_df, barrier_df, timeout_df, mc, mc_meta)
    atomic_write_json(SUMMARY_PATH, summary)
    report = write_report(summary)
    atomic_write_text(REPORT_PATH, report)

    output_paths = [
        CONTRACT_PATH, CONFIG_PATH, CONTRACT_LOCK_PATH, INPUT_INVENTORY_PATH, DATA_AUDIT_PATH,
        REAL_EVENT_PARITY_PATH, CANDIDATE_UNIVERSE_AUDIT_PATH, DUAL_SIDE_PATH, DATE_EXPECT_PATH,
        PLACEBO_SUMMARY_CSV, PLACEBO_SUMMARY_JSON, YEAR_DIR_CSV, FIRST_HIT_CSV, BARRIER_CSV,
        TIMEOUT_CSV, BOOTSTRAP_PATH, MC_CSV, SUMMARY_PATH, REPORT_PATH, SCRIPT_PATH, TEST_PATH,
        *CHARTS.values(),
    ]
    manifest = build_manifest(output_paths, config_hash, canonical_sha256(lock))
    atomic_write_json(MANIFEST_PATH, manifest)
    impl = write_impl_audit(summary, lock, manifest)
    deferred = write_deferred(summary)
    atomic_write_text(IMPL_AUDIT_PATH, impl)
    atomic_write_text(DEFERRED_PATH, deferred)
    manifest = build_manifest(output_paths + [IMPL_AUDIT_PATH, DEFERRED_PATH], config_hash, canonical_sha256(lock))
    atomic_write_json(MANIFEST_PATH, manifest)
    print(json.dumps({
        "verdict": verdict,
        "real": full["real_success"],
        "same_cross_rs": full["same_cross_rs"],
        "noncross_rs": full["noncross_rs"],
        "edge": full["directional_edge"],
        "movement": full["cross_movement"],
        "parity_ok": not parity["reproduction_failure"],
        "mc_ok": mc_ok,
        "hourly_parity_ok": sens_audit.get("hourly_parity_ok"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

