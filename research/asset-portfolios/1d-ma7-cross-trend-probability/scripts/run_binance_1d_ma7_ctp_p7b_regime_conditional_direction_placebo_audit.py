#!/usr/bin/env python3
"""Run BIN-1D-MA7-CTP P7B regime-conditional cross-direction placebo audit.

Independent sidecar after P7A. Does not train models, read P7 B0 reconstruction,
or promote a strategy. Contract is frozen before six-grid outcomes are computed.
"""

from __future__ import annotations

import argparse
import hashlib
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
PANEL_DIR = CATL_DIR / "artifacts/p0r_donor_directional_modeling_panel"
PANEL_GLOB = PANEL_DIR / "**/*.parquet"

P0R_FEATURE_BLOCKS_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_feature_blocks.json"
P0R_MANIFEST_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_manifest.json"
P0R_SUMMARY_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_summary.json"
P5_VALIDATION_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_validation_2025_plus_predictions.parquet"
P5_OOF_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_pre2025_oof_predictions.parquet"
P5_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_summary.json"
P5_MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_manifest.json"
P6_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p6_summary.json"
P6_DATA_AUDIT_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p6_data_audit.json"
P6_PREDICTIONS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p6_predictions.parquet"
P6_CONFIG_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p6_config.json"
P1_EVENT_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p1_event_panel_summary.json"
P7A_DUAL_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_dual_side_outcomes.parquet"
P7A_PARITY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_real_event_parity.json"
P7A_UNIVERSE_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_candidate_universe_audit.json"
P7A_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_summary.json"
P7A_MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_manifest.json"

CONTRACT_PATH = SPEC_DIR / "binance-1d-ma7-ctp-p7b-regime-conditional-direction-placebo-audit-2026-09-04.md"
SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p7b_regime_conditional_direction_placebo_audit.py"
TEST_PATH = ROOT / "tests/test_binance_1d_ma7_ctp_p7b_regime_conditional_direction_placebo_audit.py"

PREFIX = "binance_1d_ma7_ctp_p7b_"
RESEARCH_ID = "BIN-1D-MA7-CTP-P7B-2026-09-04"
SCHEMA_VERSION = "p7b.v1"
STATUS = "explore / diagnostic-only / placebo-audit / not promoted / not live-ready"
LOCK_STATUS = "FROZEN_BEFORE_P7B_REGIME_OUTCOME_READ"
CANONICAL_LABEL_VERSION = "CATL-P0R-entry-2atr-1atr-20d-hourly-first-hit"
CANONICAL_UNIVERSE_VERSION = "CATL-P0R-donor-panel-hype-sealed"
P6_REGIME_VERSION = "P6-frozen-BULL>=0.60-BEAR<=0.40-btc-sma30"

HYPE_ASSET = "HYPE/USDT:USDT"
HYPE_SLUG = "hype_usdt_usdt"
HYPER_ASSET = "HYPER/USDT:USDT"
BTC_ASSET = "BTC/USDT:USDT"
ETH_ASSET = "ETH/USDT:USDT"
TARGET = "label_entry_success_20d"
LABEL_END = "label_end_ts_20d"
NET_RETURN = "label_entry_net_return"
RESULT_COL = "label_entry_result"

BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_BLOCK_DAYS = 28
BOOTSTRAP_SEED = 20260901
CUTOFF = pd.Timestamp("2025-01-01T00:00:00Z")
EXPECTED_2025_PLUS = 46892
EXPECTED_2025 = 32111
EXPECTED_2026 = 14781
EXPECTED_P7A_OFFICIAL = 101029
EXPECTED_P7A_EVENT_HASH = "fe219526ac66de871cecae9907df01e0e1bfb90ca7ec5db899a542bb50794a6c"
EXPECTED_P7A_EVENT_HASH_2025_PLUS = "f9743f3a1ed7c0afc0c54c0899b8496439ae785315cf44a6b0209acb856a1a84"
EXPECTED_P7A_DUAL_SHA256 = "d0bed3c2e16bced53ef25358d3bef83a05c051aa6bfaf4b40260f58c89c298c8"

FEE_PER_FILL = 0.001
SLIPPAGE_PER_FILL = 0.0004
ROUND_TRIP_COST = 2.0 * (FEE_PER_FILL + SLIPPAGE_PER_FILL)
PRIMARY_FAV = 2.0
PRIMARY_ADV = 1.0
PRIMARY_HORIZON_DAYS = 20
BULL_BREADTH = 0.60
BEAR_BREADTH = 0.40
STRONG_BULL_BREADTH = 0.70
STRONG_BEAR_BREADTH = 0.30
VOL_LIQ_EDGES = (0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0)
BREADTH_BIN_EDGES = (0.0, 0.20, 0.40, 0.60, 0.80, 1.00)
BREADTH_BIN_LABELS = ("0-20%", "20-40%", "40-60%", "60-80%", "80-100%")

SIX_GRID = ("BULL_UP", "BULL_DOWN", "BEAR_UP", "BEAR_DOWN", "MIXED_UP", "MIXED_DOWN")
CELL_REGIME = {
    "BULL_UP": "BULL", "BULL_DOWN": "BULL",
    "BEAR_UP": "BEAR", "BEAR_DOWN": "BEAR",
    "MIXED_UP": "MIXED", "MIXED_DOWN": "MIXED",
}
CELL_SIDE = {
    "BULL_UP": "long", "BULL_DOWN": "short",
    "BEAR_UP": "long", "BEAR_DOWN": "short",
    "MIXED_UP": "long", "MIXED_DOWN": "short",
}
CELL_DIRECTION = {
    "BULL_UP": "UP", "BULL_DOWN": "DOWN",
    "BEAR_UP": "UP", "BEAR_DOWN": "DOWN",
    "MIXED_UP": "UP", "MIXED_DOWN": "DOWN",
}
ALIGNED_CELLS = ("BULL_UP", "BEAR_DOWN")
COUNTER_CELLS = ("BULL_DOWN", "BEAR_UP")
PERIODS = ("full", "pre_2022", "2022", "2023", "2024", "2025", "2026", "2025plus")

KNOWN_TRADFI_BASE_SYMBOLS = {
    "AAPL", "AMZN", "COIN", "CRCL", "GOOGL", "HOOD", "META", "MSFT", "MSTR",
    "NVDA", "PLTR", "TSLA", "SPX", "SPY", "QQQ", "TSM", "UBER", "XAU", "XAG",
    "XPD", "XPT",
}

VERDICT_CANDIDATES = (
    "DATA_OR_REPRODUCTION_FAILURE",
    "NO_REGIME_CONDITIONAL_DIRECTIONAL_EDGE",
    "REGIME_DRIFT_EXPLAINS_APPARENT_EDGE",
    "BULL_ONLY_CONDITIONAL_EDGE",
    "BEAR_ONLY_CONDITIONAL_EDGE",
    "REGIME_ALIGNED_DIRECTIONAL_EDGE_SUPPORTED",
    "REGIME_EFFECT_TEMPORALLY_UNSTABLE",
)

CONFIG_PATH = ARTIFACT_DIR / f"{PREFIX}config.json"
CONTRACT_LOCK_PATH = ARTIFACT_DIR / f"{PREFIX}contract_lock.json"
INPUT_INVENTORY_PATH = ARTIFACT_DIR / f"{PREFIX}input_inventory.json"
DATA_AUDIT_PATH = ARTIFACT_DIR / f"{PREFIX}data_audit.json"
EVENT_REGIME_PARITY_PATH = ARTIFACT_DIR / f"{PREFIX}event_regime_parity.json"
SIX_GRID_CSV = ARTIFACT_DIR / f"{PREFIX}six_grid_summary.csv"
DRIFT_CSV = ARTIFACT_DIR / f"{PREFIX}regime_drift_decomposition.csv"
INCREMENTAL_CSV = ARTIFACT_DIR / f"{PREFIX}incremental_edges.csv"
YEAR_CSV = ARTIFACT_DIR / f"{PREFIX}year_breakdown.csv"
BREADTH_CSV = ARTIFACT_DIR / f"{PREFIX}breadth_bins.csv"
MATCH_CSV = ARTIFACT_DIR / f"{PREFIX}matching_robustness.csv"
LOO_PATH = ARTIFACT_DIR / f"{PREFIX}leave_one_out.parquet"
BOOTSTRAP_PATH = ARTIFACT_DIR / f"{PREFIX}bootstrap.parquet"
SUMMARY_PATH = ARTIFACT_DIR / f"{PREFIX}summary.json"
MANIFEST_PATH = ARTIFACT_DIR / f"{PREFIX}manifest.json"
REPORT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p7b-regime-conditional-direction-placebo-audit-2026-09-04.md"
IMPL_AUDIT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p7b-implementation-audit-2026-09-04.md"
DEFERRED_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p7b-deferred-registration-2026-09-04.md"

CHARTS = {
    "real_vs_random": ARTIFACT_DIR / f"{PREFIX}chart_01_six_grid_real_vs_random.svg",
    "dir_edge": ARTIFACT_DIR / f"{PREFIX}chart_02_six_grid_directional_edge.svg",
    "regime_drift": ARTIFACT_DIR / f"{PREFIX}chart_03_six_grid_regime_drift.svg",
    "incremental": ARTIFACT_DIR / f"{PREFIX}chart_04_six_grid_incremental_edge.svg",
    "bull_up_decomp": ARTIFACT_DIR / f"{PREFIX}chart_05_bull_up_decomposition.svg",
    "bear_down_decomp": ARTIFACT_DIR / f"{PREFIX}chart_06_bear_down_decomposition.svg",
    "year_bull_up": ARTIFACT_DIR / f"{PREFIX}chart_07_yearly_bull_up_edge.svg",
    "year_bear_down": ARTIFACT_DIR / f"{PREFIX}chart_08_yearly_bear_down_edge.svg",
    "aligned_counter": ARTIFACT_DIR / f"{PREFIX}chart_09_aligned_vs_counter.svg",
    "breadth": ARTIFACT_DIR / f"{PREFIX}chart_10_breadth_bins.svg",
    "loo_month": ARTIFACT_DIR / f"{PREFIX}chart_11_leave_one_month_out.svg",
    "matched": ARTIFACT_DIR / f"{PREFIX}chart_12_vol_liq_matched.svg",
}

FILES_READ: list[str] = []
P7_BANNED_NAME_MARKERS = ("_p7_summary", "_p7_model_reconstruction", "_p7_frozen_coefficients", "_p7_feature_")


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
    return str(asset).split("/")[0].upper()


def assert_no_p7_input(paths: list[str]) -> None:
    for item in paths:
        name = Path(item).name
        if "_p7_" in name and "_p7a_" not in name and "_p7b_" not in name:
            raise RuntimeError(f"P7B must not read P7 artifact as input: {item}")
        if any(marker in name for marker in P7_BANNED_NAME_MARKERS):
            raise RuntimeError(f"P7B must not read P7 reconstruction artifact: {item}")


def event_identity_hash(frame: pd.DataFrame) -> str:
    keys = frame[["asset", "ts", "side"]].copy()
    ts = pd.to_datetime(keys["ts"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    lines = sorted(f"{a}|{t}|{s}" for a, t, s in zip(keys["asset"].astype(str), ts, keys["side"].astype(str)))
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def random_side_expectation(long_v: np.ndarray | pd.Series, short_v: np.ndarray | pd.Series) -> np.ndarray:
    return 0.5 * np.asarray(long_v, dtype=float) + 0.5 * np.asarray(short_v, dtype=float)


def incremental_edge(cross_directional_edge: float, regime_directional_drift: float) -> float:
    """MA7 increment is directional edge minus regime drift. Drift must not be credited to MA7."""
    if not np.isfinite(cross_directional_edge) or not np.isfinite(regime_directional_drift):
        return float("nan")
    return float(cross_directional_edge - regime_directional_drift)


def date_weighted_mean(values: pd.Series | np.ndarray, weights: pd.Series | np.ndarray) -> float:
    x = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    mask = np.isfinite(x) & np.isfinite(w) & (w > 0)
    if not bool(mask.any()) or float(w[mask].sum()) == 0:
        return float("nan")
    return float(np.average(x[mask], weights=w[mask]))


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
    finite_idx = [i for i, p in enumerate(pvalues) if p is not None and np.isfinite(p)]
    q = [float("nan")] * len(pvalues)
    if not finite_idx:
        return q
    m = len(finite_idx)
    ordered = sorted(finite_idx, key=lambda i: pvalues[i])
    prev = 1.0
    assigned = [float("nan")] * m
    for rank_from_end, pos in enumerate(reversed(range(m))):
        idx = ordered[pos]
        rank = pos + 1
        assigned[pos] = min(prev, pvalues[idx] * m / rank)
        prev = assigned[pos]
    for pos, idx in enumerate(ordered):
        q[idx] = float(assigned[pos])
    return q


def bootstrap_two_sided_p(draws: np.ndarray) -> float:
    finite = np.asarray(draws, dtype=float)
    finite = finite[np.isfinite(finite)]
    if len(finite) == 0:
        return float("nan")
    n = len(finite)
    p_pos = (np.sum(finite >= 0) + 1.0) / (n + 1.0)
    p_neg = (np.sum(finite <= 0) + 1.0) / (n + 1.0)
    return float(min(1.0, 2.0 * min(p_pos, p_neg)))


def restore_market_state_fields(
    breadth_dir: np.ndarray,
    btc_dir: np.ndarray,
    is_long: np.ndarray,
    *,
    bull: float = BULL_BREADTH,
    bear: float = BEAR_BREADTH,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    raw_breadth = np.where(is_long, breadth_dir, 1.0 - breadth_dir)
    raw_btc = np.where(is_long, btc_dir, -btc_dir)
    missing = ~np.isfinite(raw_breadth) | ~np.isfinite(raw_btc)
    state = np.full(len(raw_breadth), "MIXED", dtype=object)
    state[missing] = "UNKNOWN"
    state[(~missing) & (raw_breadth >= bull) & (raw_btc > 0)] = "BULL"
    state[(~missing) & (raw_breadth <= bear) & (raw_btc < 0)] = "BEAR"
    return raw_breadth.astype(float), raw_btc.astype(float), state


def tertile_bucket(pct_rank: np.ndarray) -> np.ndarray:
    out = np.zeros(len(pct_rank), dtype=int)
    finite = np.isfinite(pct_rank)
    out[finite] = 1
    out[finite & (pct_rank > VOL_LIQ_EDGES[1])] = 2
    out[finite & (pct_rank > VOL_LIQ_EDGES[2])] = 3
    return out


def breadth_bin_label(raw_breadth: np.ndarray) -> np.ndarray:
    labels = np.full(len(raw_breadth), "", dtype=object)
    finite = np.isfinite(raw_breadth)
    edges = BREADTH_BIN_EDGES
    names = BREADTH_BIN_LABELS
    for i, name in enumerate(names):
        lo, hi = edges[i], edges[i + 1]
        if i == 0:
            mask = finite & (raw_breadth >= lo) & (raw_breadth <= hi if i == len(names) - 1 else raw_breadth < hi)
        elif i == len(names) - 1:
            mask = finite & (raw_breadth >= lo) & (raw_breadth <= hi)
        else:
            mask = finite & (raw_breadth >= lo) & (raw_breadth < hi)
        labels[mask] = name
    return labels


def cell_name(regime: str, side: str) -> str:
    direction = "UP" if side == "long" else "DOWN"
    return f"{regime}_{direction}"


def build_config(*, generated_at: str) -> dict[str, Any]:
    return {
        "research_id": RESEARCH_ID,
        "schema_version": SCHEMA_VERSION,
        "experiment": "P7B Regime-Conditional Cross Direction Placebo Audit",
        "status": STATUS,
        "lock_status": LOCK_STATUS,
        "purpose": (
            "targeted diagnostic after pooled P7A and partial P6 six-grid observation; "
            "not a new blind OOS; split REGIME_DIRECTIONAL_DRIFT from REGIME_CONDITIONAL_MA7_INCREMENT"
        ),
        "targeted_not_blind": True,
        "p7a_sidecar": True,
        "forbidden_p7_inputs": True,
        "forbidden_b0": True,
        "forbidden_ml": True,
        "canonical_label_version": CANONICAL_LABEL_VERSION,
        "canonical_universe_version": CANONICAL_UNIVERSE_VERSION,
        "p6_regime_version": P6_REGIME_VERSION,
        "primary_barrier": {"tp_atr": PRIMARY_FAV, "sl_atr": PRIMARY_ADV, "horizon_days": PRIMARY_HORIZON_DAYS},
        "cost_model": {
            "leverage": 1.0,
            "fee_per_fill": FEE_PER_FILL,
            "slippage_per_fill": SLIPPAGE_PER_FILL,
            "round_trip_cost": ROUND_TRIP_COST,
        },
        "six_grid": list(SIX_GRID),
        "bull_breadth_gte": BULL_BREADTH,
        "bear_breadth_lte": BEAR_BREADTH,
        "strong_bull_breadth_gte": STRONG_BULL_BREADTH,
        "strong_bear_breadth_lte": STRONG_BEAR_BREADTH,
        "primary_hypotheses": ["H1_BULL_UP_INCREMENTAL>0", "H2_BEAR_DOWN_INCREMENTAL>0", "H3_REGIME_ALIGNMENT_EFFECT>0"],
        "date_matching": "weight non-cross same-date metrics by n_cell_cross[d]",
        "vol_liq_matching": {
            "vol_metric": "atr_to_entry_p0r",
            "liq_metric": "liquidity_rank_pct_p0r",
            "same_day_percentile": True,
            "tertile_edges": list(VOL_LIQ_EDGES),
            "frozen_before_outcome_read": True,
        },
        "breadth_bins": list(BREADTH_BIN_LABELS),
        "bootstrap": {"n": BOOTSTRAP_SAMPLES, "block_days": BOOTSTRAP_BLOCK_DAYS, "seed": BOOTSTRAP_SEED},
        "bh_primary_family": [
            "BULL_UP_INCREMENTAL_EDGE",
            "BEAR_DOWN_INCREMENTAL_EDGE",
            "REGIME_ALIGNMENT_EFFECT",
        ],
        "bh_secondary_family": [f"{cell}_INCREMENTAL_EDGE" for cell in SIX_GRID],
        "periods": list(PERIODS),
        "2025plus_role": "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS",
        "parity_anchors": {
            "validation_2025_plus": EXPECTED_2025_PLUS,
            "year_2025": EXPECTED_2025,
            "year_2026": EXPECTED_2026,
            "p7a_official_n": EXPECTED_P7A_OFFICIAL,
            "p7a_event_hash": EXPECTED_P7A_EVENT_HASH,
            "p7a_event_hash_2025_plus": EXPECTED_P7A_EVENT_HASH_2025_PLUS,
            "p7a_dual_sha256": EXPECTED_P7A_DUAL_SHA256,
        },
        "verdict_candidates": list(VERDICT_CANDIDATES),
        "hype_asset": HYPE_ASSET,
        "hyper_asset": HYPER_ASSET,
        "generated_at": generated_at,
        "no_ml": True,
        "no_equity_curve": True,
        "no_b0": True,
        "interpretation_rule": (
            "BULL_UP real-vs-random is not MA7 information unless BULL_UP_INCREMENTAL_EDGE > 0 "
            "after subtracting Bull non-cross long drift"
        ),
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
    note_read(P5_VALIDATION_PATH)
    note_read(P5_OOF_PATH)
    note_read(P5_SUMMARY_PATH)
    note_read(P5_MANIFEST_PATH)
    note_read(P6_SUMMARY_PATH)
    note_read(P6_DATA_AUDIT_PATH)
    note_read(P6_CONFIG_PATH)
    note_read(P6_PREDICTIONS_PATH)
    note_read(P1_EVENT_SUMMARY_PATH)
    note_read(P7A_DUAL_PATH)
    note_read(P7A_PARITY_PATH)
    note_read(P7A_UNIVERSE_PATH)
    note_read(P7A_SUMMARY_PATH)
    note_read(P7A_MANIFEST_PATH)
    panel_files = list_p0r_panel_files()
    hashed: dict[str, str] = {}
    files: list[dict[str, Any]] = []
    for path in [
        CONTRACT_PATH, SCRIPT_PATH, P0R_FEATURE_BLOCKS_PATH, P0R_MANIFEST_PATH, P0R_SUMMARY_PATH,
        P5_VALIDATION_PATH, P5_OOF_PATH, P5_SUMMARY_PATH, P5_MANIFEST_PATH, P6_SUMMARY_PATH,
        P6_DATA_AUDIT_PATH, P6_CONFIG_PATH, P6_PREDICTIONS_PATH, P1_EVENT_SUMMARY_PATH,
        P7A_DUAL_PATH, P7A_PARITY_PATH, P7A_UNIVERSE_PATH, P7A_SUMMARY_PATH, P7A_MANIFEST_PATH,
        *panel_files,
    ]:
        digest = sha256_file(path)
        hashed[rel(path)] = digest
        files.append({"path": rel(path), "sha256": digest, "bytes": path.stat().st_size})
    assert_no_p7_input([item["path"] for item in files])
    if any(HYPE_SLUG in item["path"].lower() and "hyper_usdt_usdt" not in item["path"].lower() for item in files):
        raise RuntimeError("HYPE partition leaked into input inventory")
    dual_hash = hashed[rel(P7A_DUAL_PATH)]
    if dual_hash != EXPECTED_P7A_DUAL_SHA256:
        raise RuntimeError(f"P7A dual-side hash mismatch: {dual_hash}")
    inputs = {
        "research_id": RESEARCH_ID,
        "schema_version": SCHEMA_VERSION,
        "files": files,
        "n_files": len(files),
        "input_set_sha256": canonical_sha256(hashed),
        "p7a_dual_sha256": dual_hash,
        "p7_files_included": False,
        "b0_score_files_used_as_features": False,
    }
    lock = {
        "research_id": RESEARCH_ID,
        "schema_version": SCHEMA_VERSION,
        "status": LOCK_STATUS,
        "purpose": config["purpose"],
        "targeted_not_blind": True,
        "contract_sha256": hashed[rel(CONTRACT_PATH)],
        "config_sha256": canonical_sha256(config),
        "script_sha256": hashed[rel(SCRIPT_PATH)],
        "input_inventory_sha256": canonical_sha256(inputs),
        "canonical_label_version": CANONICAL_LABEL_VERSION,
        "canonical_universe_version": CANONICAL_UNIVERSE_VERSION,
        "p6_regime_version": P6_REGIME_VERSION,
        "six_grid": list(SIX_GRID),
        "bull_breadth_gte": BULL_BREADTH,
        "bear_breadth_lte": BEAR_BREADTH,
        "primary_hypotheses": config["primary_hypotheses"],
        "p7_files_included": False,
        "p7a_dual_sha256": dual_hash,
    }
    atomic_write_json(CONFIG_PATH, config)
    atomic_write_json(INPUT_INVENTORY_PATH, inputs)
    atomic_write_json(CONTRACT_LOCK_PATH, lock)
    return inputs, lock


def load_p0r_panel() -> pd.DataFrame:
    cols = [
        "asset", "asset_slug", "side", "ts", "feature_known_at", "entry_ts", "entry_ref", "atr_anchor",
        TARGET, LABEL_END, NET_RETURN, RESULT_COL, "future_path_complete_20d",
        "future_terminal_direction_return_20d", "model_eligible_entry_p0r", "probe_raw_ma7_cross_dir",
        "dir_market_breadth_ma30_p0r", "dir_btc_price_side_ma30", "atr_to_entry_p0r",
        "liquidity_rank_pct_p0r", "atr14_pct",
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
    df["base_symbol"] = df["asset"].map(base_symbol)
    df["is_known_tradfi"] = df["base_symbol"].isin(KNOWN_TRADFI_BASE_SYMBOLS)
    df["event_year"] = df["ts"].dt.year.astype(int)
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
    entry_mismatch = int((~np.isclose(merged["entry_ref_long"], merged["entry_ref_short"], rtol=0, atol=0, equal_nan=True)).sum())
    atr_mismatch = int((~np.isclose(merged["atr_anchor_long"], merged["atr_anchor_short"], rtol=0, atol=0, equal_nan=True)).sum())
    entry_ts_mismatch = int((merged["entry_ts_long"] != merged["entry_ts_short"]).sum())
    known_ok = int((merged["feature_known_at_long"] != merged["entry_ts_long"]).sum())
    timing_ok = int((merged["feature_known_at_long"] != (merged["ts"] + pd.Timedelta(days=1))).sum())
    out = pd.DataFrame({
        "asset": merged["asset"],
        "asset_slug": merged["asset_slug"],
        "ts": merged["ts"],
        "event_year": merged["event_year_long"],
        "feature_known_at": merged["feature_known_at_long"],
        "entry_ts": merged["entry_ts_long"],
        "entry_ref": merged["entry_ref_long"],
        "atr_anchor": merged["atr_anchor_long"],
        "atr_to_entry": merged["atr_to_entry_p0r_long"].astype(float),
        "liquidity_rank_pct": merged["liquidity_rank_pct_p0r_long"].astype(float),
        "dir_breadth_long": merged["dir_market_breadth_ma30_p0r_long"].astype(float),
        "dir_breadth_short": merged["dir_market_breadth_ma30_p0r_short"].astype(float),
        "dir_btc_long": merged["dir_btc_price_side_ma30_long"].astype(float),
        "dir_btc_short": merged["dir_btc_price_side_ma30_short"].astype(float),
        "long_success": merged[f"{TARGET}_long"].astype(int),
        "short_success": merged[f"{TARGET}_short"].astype(int),
        "long_net": merged[f"{NET_RETURN}_long"].astype(float),
        "short_net": merged[f"{NET_RETURN}_short"].astype(float),
        "long_result": merged[f"{RESULT_COL}_long"].astype(str),
        "short_result": merged[f"{RESULT_COL}_short"].astype(str),
        "long_terminal": merged["future_terminal_direction_return_20d_long"].astype(float),
        "short_terminal": merged["future_terminal_direction_return_20d_short"].astype(float),
        "is_cross": merged["probe_raw_ma7_cross_dir_long"] | merged["probe_raw_ma7_cross_dir_short"],
        "real_side": np.where(merged["probe_raw_ma7_cross_dir_long"], "long",
                     np.where(merged["probe_raw_ma7_cross_dir_short"], "short", "")),
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
    out["opp_success"] = np.where(out["real_side"].eq("long"), out["short_success"],
                         np.where(out["real_side"].eq("short"), out["long_success"], np.nan))
    out["date"] = out["ts"].dt.normalize()
    raw_b, raw_btc, state = restore_market_state_fields(
        out["dir_breadth_long"].to_numpy(dtype=float),
        out["dir_btc_long"].to_numpy(dtype=float),
        np.ones(len(out), dtype=bool),
    )
    raw_b_s, raw_btc_s, state_s = restore_market_state_fields(
        out["dir_breadth_short"].to_numpy(dtype=float),
        out["dir_btc_short"].to_numpy(dtype=float),
        np.zeros(len(out), dtype=bool),
    )
    out["raw_breadth"] = raw_b
    out["raw_btc_side"] = raw_btc
    out["market_state"] = state
    out["market_state_from_short"] = state_s
    out["raw_breadth_from_short"] = raw_b_s
    out["raw_btc_from_short"] = raw_btc_s
    audit = {
        "eligible_directional_rows": int(len(eligible)),
        "dual_side_asset_days": int(len(out)),
        "entry_ref_mismatch": entry_mismatch,
        "atr_mismatch": atr_mismatch,
        "entry_ts_mismatch": entry_ts_mismatch,
        "feature_known_at_ne_entry_ts": known_ok,
        "feature_known_at_ne_ts_plus_1d": timing_ok,
        "hype_rows": int((out["asset"] == HYPE_ASSET).sum()),
        "hyper_rows": int(out["hyper"].sum()),
        "cross_asset_days": int(out["is_cross"].sum()),
        "non_cross_asset_days": int((~out["is_cross"]).sum()),
        "long_short_state_mismatch_rows": int((out["market_state"] != out["market_state_from_short"]).sum()),
        "max_long_short_breadth_abs_diff": float(np.nanmax(np.abs(raw_b - raw_b_s))) if len(out) else None,
        "max_long_short_btc_abs_diff": float(np.nanmax(np.abs(raw_btc - raw_btc_s))) if len(out) else None,
    }
    if audit["hype_rows"] != 0:
        raise RuntimeError("HYPE rows in dual-side table")
    if audit["hyper_rows"] <= 0:
        raise RuntimeError("HYPER missing from dual-side table")
    if audit["entry_ref_mismatch"] or audit["atr_mismatch"] or audit["entry_ts_mismatch"]:
        raise RuntimeError("long/short counterfactuals do not share entry/ATR/path identity")
    if audit["feature_known_at_ne_entry_ts"] or audit["feature_known_at_ne_ts_plus_1d"]:
        raise RuntimeError("regime/feature timing is not event-day close -> next UTC open")
    if audit["long_short_state_mismatch_rows"] != 0:
        raise RuntimeError("long/short restored market_state mismatch")
    if (audit["max_long_short_breadth_abs_diff"] or 0) > 1e-8:
        raise RuntimeError("long/short restored raw_breadth mismatch")
    return out, audit


def attach_p5_identity(dual: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    p5_val = pd.read_parquet(P5_VALIDATION_PATH)
    p5_val["ts"] = pd.to_datetime(p5_val["ts"], utc=True)
    p5_val["side"] = p5_val["side"].astype(str).str.lower()
    if (p5_val["asset"] == HYPE_ASSET).any():
        raise RuntimeError("HYPE rows in P5 predictions")
    p5_val_main = p5_val.loc[~p5_val["is_known_tradfi"].astype(bool) & ~p5_val["asset"].eq(HYPE_ASSET)].copy()

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
    return out, {
        "p5_validation_main": int(len(p5_val_main)),
        "p0r_cross_not_in_p5_2025plus": int(len(excluded)),
    }


def parity_p7a_dual(dual: pd.DataFrame) -> dict[str, Any]:
    p7a = pd.read_parquet(P7A_DUAL_PATH)
    p7a["ts"] = pd.to_datetime(p7a["ts"], utc=True)
    merged = dual.merge(
        p7a[["asset", "ts", "official_real", "is_cross", "real_side", "long_success", "short_success", "long_net", "short_net"]],
        on=["asset", "ts"],
        how="outer",
        suffixes=("", "_p7a"),
        indicator=True,
    )
    both = merged["_merge"].eq("both")
    success_mismatch = int((
        both
        & (
            (merged["long_success"] != merged["long_success_p7a"])
            | (merged["short_success"] != merged["short_success_p7a"])
        )
    ).sum())
    net_mismatch = int((
        both
        & (
            ~np.isclose(merged["long_net"], merged["long_net_p7a"], rtol=0, atol=1e-12, equal_nan=True)
            | ~np.isclose(merged["short_net"], merged["short_net_p7a"], rtol=0, atol=1e-12, equal_nan=True)
        )
    ).sum())
    official_mismatch = int((both & (merged["official_real"] != merged["official_real_p7a"])).sum())
    side_mismatch = int((both & (merged["real_side"].astype(str) != merged["real_side_p7a"].astype(str))).sum())
    return {
        "p7a_rows": int(len(p7a)),
        "rebuild_rows": int(len(dual)),
        "both_rows": int(both.sum()),
        "left_only": int(merged["_merge"].eq("left_only").sum()),
        "right_only": int(merged["_merge"].eq("right_only").sum()),
        "success_mismatch": success_mismatch,
        "net_mismatch": net_mismatch,
        "official_mismatch": official_mismatch,
        "real_side_mismatch": side_mismatch,
        "ok": (
            int(both.sum()) == int(len(p7a)) == int(len(dual))
            and success_mismatch == 0
            and net_mismatch == 0
            and official_mismatch == 0
            and side_mismatch == 0
            and int(merged["_merge"].eq("left_only").sum()) == 0
            and int(merged["_merge"].eq("right_only").sum()) == 0
        ),
    }


def real_event_parity(real: pd.DataFrame) -> dict[str, Any]:
    main = real.copy()
    y2025 = main.loc[main["event_year"].eq(2025)]
    y2026 = main.loc[main["event_year"].eq(2026)]
    plus = main.loc[main["ts"] >= CUTOFF]
    p5_val = pd.read_parquet(P5_VALIDATION_PATH)
    p5_val["ts"] = pd.to_datetime(p5_val["ts"], utc=True)
    p5_val["side"] = p5_val["side"].astype(str).str.lower()
    p5_val_main = p5_val.loc[~p5_val["is_known_tradfi"].astype(bool) & ~p5_val["asset"].eq(HYPE_ASSET)]

    def key(frame: pd.DataFrame) -> pd.Series:
        return frame["asset"].astype(str) + "|" + pd.to_datetime(frame["ts"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S%z") + "|" + frame["side"].astype(str)

    plus_keys = set(key(plus.assign(side=plus["real_side"])))
    val_keys = set(key(p5_val_main))
    missing = sorted(val_keys - plus_keys)
    extra = sorted(plus_keys - val_keys)
    counts = {
        "real_n": int(len(main)),
        "real_2025_plus": int(len(plus)),
        "real_2025": int(len(y2025)),
        "real_2026": int(len(y2026)),
        "real_pre_2025": int((main["ts"] < CUTOFF).sum()),
        "hype_rows": int((main["asset"] == HYPE_ASSET).sum()),
        "hyper_rows": int(main["asset"].eq(HYPER_ASSET).sum()),
        "identity_missing_vs_p5_val": len(missing),
        "identity_extra_vs_p5_val": len(extra),
        "canonical_event_id_hash": event_identity_hash(main.assign(side=main["real_side"])),
        "canonical_event_id_hash_2025_plus": event_identity_hash(plus.assign(side=plus["real_side"])),
        "success_full": float(main["real_success"].mean()) if len(main) else float("nan"),
        "success_2025": float(y2025["real_success"].mean()) if len(y2025) else float("nan"),
        "success_2026": float(y2026["real_success"].mean()) if len(y2026) else float("nan"),
    }
    counts["anchors_ok"] = (
        counts["real_n"] == EXPECTED_P7A_OFFICIAL
        and counts["real_2025_plus"] == EXPECTED_2025_PLUS
        and counts["real_2025"] == EXPECTED_2025
        and counts["real_2026"] == EXPECTED_2026
        and counts["hype_rows"] == 0
        and counts["hyper_rows"] > 0
        and counts["identity_missing_vs_p5_val"] == 0
        and counts["identity_extra_vs_p5_val"] == 0
        and counts["canonical_event_id_hash"] == EXPECTED_P7A_EVENT_HASH
        and counts["canonical_event_id_hash_2025_plus"] == EXPECTED_P7A_EVENT_HASH_2025_PLUS
    )
    counts["reproduction_failure"] = not counts["anchors_ok"]
    return counts


def parity_p6_regime(real: pd.DataFrame) -> dict[str, Any]:
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    p6 = con.execute(
        """
        SELECT asset, side, ts, market_state, six_grid, raw_market_breadth_ma30, raw_btc_price_side_ma30
        FROM read_parquet(?)
        WHERE asset <> ?
        """,
        [str(P6_PREDICTIONS_PATH), HYPE_ASSET],
    ).fetchdf()
    con.close()
    p6["ts"] = pd.to_datetime(p6["ts"], utc=True)
    p6["side"] = p6["side"].astype(str).str.lower()
    work = real.assign(side=real["real_side"]).copy()
    merged = work.merge(
        p6,
        on=["asset", "ts", "side"],
        how="inner",
        suffixes=("", "_p6"),
    )
    state_mismatch = int((merged["market_state"] != merged["market_state_p6"]).sum()) if "market_state_p6" in merged.columns else int((merged["market_state"] != merged["market_state"]).sum())
    if "market_state_p6" in merged.columns:
        state_mismatch = int((merged["market_state"].astype(str) != merged["market_state_p6"].astype(str)).sum())
        six_ours = merged["market_state"].astype(str) + "_" + merged["real_side"].str.upper()
        six_mismatch = int((six_ours != merged["six_grid"].astype(str)).sum())
        breadth_mismatch = int((~np.isclose(
            merged["raw_breadth"], merged["raw_market_breadth_ma30"], rtol=0, atol=1e-10, equal_nan=True,
        )).sum())
        btc_mismatch = int((~np.isclose(
            merged["raw_btc_side"], merged["raw_btc_price_side_ma30"], rtol=0, atol=1e-10, equal_nan=True,
        )).sum())
    else:
        six_mismatch = 0
        breadth_mismatch = 0
        btc_mismatch = 0
    date_conflict = (
        real.groupby("date")["market_state"].nunique()
    )
    unknown_n = int(real["market_state"].eq("UNKNOWN").sum())
    audit = {
        "p6_overlap_rows": int(len(merged)),
        "p6_pred_rows": int(len(p6)),
        "state_mismatch": state_mismatch,
        "six_grid_mismatch": six_mismatch,
        "breadth_mismatch": breadth_mismatch,
        "btc_mismatch": btc_mismatch,
        "unknown_official_rows": unknown_n,
        "dates_with_multiple_states": int((date_conflict > 1).sum()),
        "bull_threshold": BULL_BREADTH,
        "bear_threshold": BEAR_BREADTH,
        "ok": (
            len(merged) > 0
            and state_mismatch == 0
            and six_mismatch == 0
            and breadth_mismatch == 0
            and btc_mismatch == 0
            and unknown_n == 0
            and int((date_conflict > 1).sum()) == 0
        ),
    }
    return audit


def attach_vol_liq(dual: pd.DataFrame) -> pd.DataFrame:
    out = dual.copy()
    out["vol_pct"] = out.groupby("date")["atr_to_entry"].rank(pct=True, method="average")
    out["liq_pct"] = out.groupby("date")["liquidity_rank_pct"].rank(pct=True, method="average")
    out["vol_bucket"] = tertile_bucket(out["vol_pct"].to_numpy(dtype=float))
    out["liq_bucket"] = tertile_bucket(out["liq_pct"].to_numpy(dtype=float))
    out["breadth_bin"] = breadth_bin_label(out["raw_breadth"].to_numpy(dtype=float))
    out["month"] = out["date"].dt.strftime("%Y-%m")
    origin = out["date"].min()
    out["block28"] = calendar_block_id(out["date"], origin=origin)
    out["cell"] = np.where(
        out["official_real"] & out["market_state"].isin(["BULL", "BEAR", "MIXED"]) & out["real_side"].isin(["long", "short"]),
        out["market_state"] + "_" + np.where(out["real_side"].eq("long"), "UP", "DOWN"),
        "",
    )
    strong_b, _, strong_state = restore_market_state_fields(
        out["dir_breadth_long"].to_numpy(dtype=float),
        out["dir_btc_long"].to_numpy(dtype=float),
        np.ones(len(out), dtype=bool),
        bull=STRONG_BULL_BREADTH,
        bear=STRONG_BEAR_BREADTH,
    )
    out["strong_state"] = strong_state
    out["strong_breadth"] = strong_b
    return out


def funding_array(result: np.ndarray, net: np.ndarray, atr: np.ndarray, ref: np.ndarray, terminal: np.ndarray) -> np.ndarray:
    atr = np.asarray(atr, dtype=float)
    ref = np.asarray(ref, dtype=float)
    terminal = np.asarray(terminal, dtype=float)
    net = np.asarray(net, dtype=float)
    result = np.asarray(result, dtype=object)
    with np.errstate(divide="ignore", invalid="ignore"):
        fav = PRIMARY_FAV * atr / ref
        adv = -PRIMARY_ADV * atr / ref
    price = np.where(result == "favorable_first", fav,
            np.where(np.isin(result, ["adverse_first", "ambiguous_same_hour"]), adv, terminal))
    return net - price + ROUND_TRIP_COST


def add_event_economics(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["real_funding"] = funding_array(
        out["real_result"].to_numpy(dtype=object),
        out["real_net"].to_numpy(dtype=float),
        out["atr_anchor"].to_numpy(dtype=float),
        out["entry_ref"].to_numpy(dtype=float),
        np.where(out["real_side"].eq("long"), out["long_terminal"], out["short_terminal"]).astype(float),
    )
    out["long_funding"] = funding_array(out["long_result"], out["long_net"], out["atr_anchor"], out["entry_ref"], out["long_terminal"])
    out["short_funding"] = funding_array(out["short_result"], out["short_net"], out["atr_anchor"], out["entry_ref"], out["short_terminal"])
    out["rs_funding"] = 0.5 * out["long_funding"] + 0.5 * out["short_funding"]
    return out


def _safe_avg(values: np.ndarray, weights: np.ndarray) -> float:
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not bool(mask.any()) or float(weights[mask].sum()) == 0:
        return float("nan")
    return float(np.average(values[mask], weights=weights[mask]))


def cell_metrics_from_events(cross: pd.DataFrame, noncross: pd.DataFrame, cell: str) -> dict[str, Any]:
    regime = CELL_REGIME[cell]
    side = CELL_SIDE[cell]
    c = cross.loc[cross["cell"].eq(cell)].copy()
    n = int(len(c))
    empty = {
        "cell": cell, "regime": regime, "cross": CELL_DIRECTION[cell], "n": 0,
        "unique_dates": 0, "unique_assets": 0, "month_count": 0, "block_count": 0,
        "real_success": float("nan"), "random_success": float("nan"), "opp_success": float("nan"),
        "directional_edge": float("nan"), "noncross_same_success": float("nan"),
        "noncross_random_success": float("nan"), "regime_drift": float("nan"),
        "incremental_edge": float("nan"), "coverage_n": 0, "coverage_dates": 0,
        "dates_missing_noncross": 0, "real_net_mean": float("nan"), "real_net_median": float("nan"),
        "real_positive_net": float("nan"), "random_net_mean": float("nan"),
        "noncross_same_net_mean": float("nan"), "favorable_first": float("nan"),
        "adverse_first": float("nan"), "timeout": float("nan"), "funding_mean": float("nan"),
        "ci_width": float("nan"),
    }
    if n == 0:
        return empty
    same_col = "long_success" if side == "long" else "short_success"
    same_net = "long_net" if side == "long" else "short_net"
    n_by_date = c.groupby("date").size().rename("n_cell")
    non_date = noncross.groupby("date").agg(
        n_non=("asset", "size"),
        same_success=(same_col, "mean"),
        rs_success=("rs_success", "mean"),
        same_net=(same_net, "mean"),
        rs_net=("rs_net", "mean"),
    )
    joined = n_by_date.to_frame().join(non_date, how="left")
    missing = joined["n_non"].isna() | (joined["n_non"] <= 0)
    valid = joined.loc[~missing]
    if len(valid):
        c_used = c.loc[c["date"].isin(valid.index)]
    else:
        c_used = c.iloc[0:0]
    real = float(c_used["real_success"].mean()) if len(c_used) else float("nan")
    rs = float(c_used["rs_success"].mean()) if len(c_used) else float("nan")
    opp = float(c_used["opp_success"].mean()) if len(c_used) else float("nan")
    non_same = date_weighted_mean(valid["same_success"], valid["n_cell"]) if len(valid) else float("nan")
    non_rs = date_weighted_mean(valid["rs_success"], valid["n_cell"]) if len(valid) else float("nan")
    drift = (non_same - non_rs) if np.isfinite(non_same) and np.isfinite(non_rs) else float("nan")
    dir_edge = real - rs if np.isfinite(real) and np.isfinite(rs) else float("nan")
    inc = incremental_edge(dir_edge, drift)
    real_cov, rs_cov, dir_edge_cov = real, rs, dir_edge
    fav = float((c["real_result"] == "favorable_first").mean())
    adv = float((c["real_result"] == "adverse_first").mean())
    timeout = float((c["real_result"] == "timeout").mean())
    return {
        "cell": cell,
        "regime": regime,
        "cross": CELL_DIRECTION[cell],
        "n": n,
        "unique_dates": int(c["date"].nunique()),
        "unique_assets": int(c["asset"].nunique()),
        "month_count": int(c["month"].nunique()),
        "block_count": int(c["block28"].nunique()),
        "real_success": real,
        "random_success": rs,
        "opp_success": opp,
        "directional_edge": dir_edge,
        "directional_edge_covered": dir_edge_cov,
        "noncross_same_success": non_same,
        "noncross_random_success": non_rs,
        "regime_drift": drift,
        "incremental_edge": inc,
        "coverage_n": int(valid["n_cell"].sum()) if len(valid) else 0,
        "coverage_dates": int(len(valid)),
        "dates_missing_noncross": int(missing.sum()),
        "real_net_mean": float(c["real_net"].mean()),
        "real_net_median": float(c["real_net"].median()),
        "real_positive_net": float((c["real_net"] > 0).mean()),
        "random_net_mean": float(c["rs_net"].mean()),
        "noncross_same_net_mean": date_weighted_mean(valid["same_net"], valid["n_cell"]) if len(valid) else float("nan"),
        "favorable_first": fav,
        "adverse_first": adv,
        "timeout": timeout,
        "funding_mean": float(c["real_funding"].mean()) if "real_funding" in c.columns else float("nan"),
        "real_covered": real_cov,
        "random_covered": rs_cov,
        "n_noncross_weighted": float(valid["n_non"].sum()) if len(valid) else 0.0,
    }


def alignment_from_cells(cells: dict[str, dict[str, Any]]) -> dict[str, Any]:
    def weighted(names: tuple[str, ...], field: str) -> float:
        ns = np.array([
            cells[name].get("coverage_n", cells[name].get("n", 0)) or 0
            for name in names
        ], dtype=float)
        vs = np.array([cells[name].get(field, float("nan")) for name in names], dtype=float)
        return date_weighted_mean(vs, ns)

    aligned_inc = weighted(ALIGNED_CELLS, "incremental_edge")
    counter_inc = weighted(COUNTER_CELLS, "incremental_edge")
    return {
        "aligned_incremental_edge": aligned_inc,
        "counter_incremental_edge": counter_inc,
        "regime_alignment_effect": (
            aligned_inc - counter_inc if np.isfinite(aligned_inc) and np.isfinite(counter_inc) else float("nan")
        ),
        "aligned_n": int(sum(cells[name].get("coverage_n", cells[name].get("n", 0)) or 0 for name in ALIGNED_CELLS)),
        "counter_n": int(sum(cells[name].get("coverage_n", cells[name].get("n", 0)) or 0 for name in COUNTER_CELLS)),
        "aligned_directional_edge": weighted(ALIGNED_CELLS, "directional_edge"),
        "counter_directional_edge": weighted(COUNTER_CELLS, "directional_edge"),
    }


def compute_six_grid(cross: pd.DataFrame, noncross: pd.DataFrame) -> dict[str, dict[str, Any]]:
    return {cell: cell_metrics_from_events(cross, noncross, cell) for cell in SIX_GRID}


def build_date_pack(cross: pd.DataFrame, noncross: pd.DataFrame) -> dict[str, Any]:
    dates = pd.Index(sorted(set(cross["date"]).union(set(noncross["date"]))))
    non_date = noncross.groupby("date").agg(
        n_non=("asset", "size"),
        long_success=("long_success", "mean"),
        short_success=("short_success", "mean"),
        rs_success=("rs_success", "mean"),
    ).reindex(dates)
    pack: dict[str, Any] = {
        "dates": dates.to_numpy(),
        "n_non": non_date["n_non"].fillna(0).to_numpy(dtype=float),
        "non_long": non_date["long_success"].to_numpy(dtype=float),
        "non_short": non_date["short_success"].to_numpy(dtype=float),
        "non_rs": non_date["rs_success"].to_numpy(dtype=float),
        "block": calendar_block_id(pd.Series(dates), origin=pd.Timestamp(dates.min())).to_numpy(dtype=int),
        "year": pd.DatetimeIndex(dates).year.to_numpy(dtype=int),
        "month": pd.DatetimeIndex(dates).strftime("%Y-%m").to_numpy(),
    }
    for cell in SIX_GRID:
        c = cross.loc[cross["cell"].eq(cell)]
        g = c.groupby("date").agg(
            n=("asset", "size"),
            real_sum=("real_success", "sum"),
            rs_sum=("rs_success", "sum"),
        ).reindex(dates).fillna(0)
        pack[f"{cell}_n"] = g["n"].to_numpy(dtype=float)
        pack[f"{cell}_real"] = g["real_sum"].to_numpy(dtype=float)
        pack[f"{cell}_rs"] = g["rs_sum"].to_numpy(dtype=float)
    return pack


def metrics_from_pack(pack: dict[str, Any], idx: np.ndarray | None = None) -> dict[str, Any]:
    if idx is None:
        idx = np.arange(len(pack["dates"]))
    n_non = pack["n_non"][idx]
    non_long = pack["non_long"][idx]
    non_short = pack["non_short"][idx]
    non_rs = pack["non_rs"][idx]
    out: dict[str, Any] = {}
    for cell in SIX_GRID:
        n = pack[f"{cell}_n"][idx]
        real_sum = pack[f"{cell}_real"][idx]
        rs_sum = pack[f"{cell}_rs"][idx]
        side = CELL_SIDE[cell]
        non_same = non_long if side == "long" else non_short
        valid = (n > 0) & (n_non > 0) & np.isfinite(non_same) & np.isfinite(non_rs)
        w = n[valid]
        if float(w.sum()) == 0:
            out[cell] = {"n": 0.0, "directional_edge": float("nan"), "regime_drift": float("nan"), "incremental_edge": float("nan")}
            continue
        real = float(real_sum[valid].sum() / w.sum())
        rs = float(rs_sum[valid].sum() / w.sum())
        ns = _safe_avg(non_same[valid], w)
        nr = _safe_avg(non_rs[valid], w)
        drift = ns - nr
        dir_edge = real - rs
        out[cell] = {
            "n": float(w.sum()),
            "real_success": real,
            "random_success": rs,
            "directional_edge": dir_edge,
            "noncross_same_success": ns,
            "noncross_random_success": nr,
            "regime_drift": drift,
            "incremental_edge": incremental_edge(dir_edge, drift),
        }
    aligned = alignment_from_cells(out)
    out["ALIGNED"] = aligned
    return out


def run_block_bootstrap(pack: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    blocks = np.unique(pack["block"])
    by_block = {int(b): np.where(pack["block"] == b)[0] for b in blocks}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    records = []
    keys = [f"{cell}_incremental_edge" for cell in SIX_GRID] + [
        "BULL_UP_INCREMENTAL_EDGE", "BEAR_DOWN_INCREMENTAL_EDGE", "REGIME_ALIGNMENT_EFFECT",
        "BULL_UP_DIRECTIONAL_EDGE", "BEAR_DOWN_DIRECTIONAL_EDGE",
        "BULL_UP_REGIME_DRIFT", "BEAR_DOWN_REGIME_DRIFT",
    ]
    for i in range(BOOTSTRAP_SAMPLES):
        sampled = rng.choice(blocks, size=len(blocks), replace=True)
        idx = np.concatenate([by_block[int(b)] for b in sampled])
        m = metrics_from_pack(pack, idx)
        rec = {"replicate": i}
        for cell in SIX_GRID:
            rec[f"{cell}_incremental_edge"] = m[cell]["incremental_edge"]
            rec[f"{cell}_directional_edge"] = m[cell]["directional_edge"]
            rec[f"{cell}_regime_drift"] = m[cell]["regime_drift"]
        rec["BULL_UP_INCREMENTAL_EDGE"] = m["BULL_UP"]["incremental_edge"]
        rec["BEAR_DOWN_INCREMENTAL_EDGE"] = m["BEAR_DOWN"]["incremental_edge"]
        rec["REGIME_ALIGNMENT_EFFECT"] = m["ALIGNED"]["regime_alignment_effect"]
        rec["aligned_incremental_edge"] = m["ALIGNED"]["aligned_incremental_edge"]
        rec["counter_incremental_edge"] = m["ALIGNED"]["counter_incremental_edge"]
        rec["BULL_UP_DIRECTIONAL_EDGE"] = m["BULL_UP"]["directional_edge"]
        rec["BEAR_DOWN_DIRECTIONAL_EDGE"] = m["BEAR_DOWN"]["directional_edge"]
        rec["BULL_UP_REGIME_DRIFT"] = m["BULL_UP"]["regime_drift"]
        rec["BEAR_DOWN_REGIME_DRIFT"] = m["BEAR_DOWN"]["regime_drift"]
        records.append(rec)
    boot = pd.DataFrame.from_records(records)

    def summarize(col: str, point: float | None = None) -> dict[str, float]:
        x = boot[col].to_numpy(dtype=float) if col in boot.columns else np.array([], dtype=float)
        finite = x[np.isfinite(x)]
        return {
            "point_from_full_sample": point,
            "bootstrap_mean": float(np.mean(finite)) if len(finite) else float("nan"),
            "p2.5": float(np.percentile(finite, 2.5)) if len(finite) else float("nan"),
            "p97.5": float(np.percentile(finite, 97.5)) if len(finite) else float("nan"),
            "effective_replicates": int(len(finite)),
            "non_finite_replicates": int(len(x) - len(finite)),
            "p_two_sided": bootstrap_two_sided_p(finite),
            "ci_width": float(np.percentile(finite, 97.5) - np.percentile(finite, 2.5)) if len(finite) else float("nan"),
        }

    summary = {
        "n": BOOTSTRAP_SAMPLES,
        "seed": BOOTSTRAP_SEED,
        "block_days": BOOTSTRAP_BLOCK_DAYS,
        "n_blocks": int(len(blocks)),
        "stats": {},
    }
    for col in [
        "BULL_UP_INCREMENTAL_EDGE", "BEAR_DOWN_INCREMENTAL_EDGE", "REGIME_ALIGNMENT_EFFECT",
        "aligned_incremental_edge", "counter_incremental_edge",
        "BULL_UP_DIRECTIONAL_EDGE", "BEAR_DOWN_DIRECTIONAL_EDGE",
        "BULL_UP_REGIME_DRIFT", "BEAR_DOWN_REGIME_DRIFT",
        *[f"{cell}_incremental_edge" for cell in SIX_GRID],
        *[f"{cell}_directional_edge" for cell in SIX_GRID],
    ]:
        summary["stats"][col] = summarize(col)
    return boot, summary


def period_frames(cross: pd.DataFrame, noncross: pd.DataFrame, period: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    if period == "full":
        return cross, noncross
    if period == "pre_2022":
        mask_c = cross["event_year"] < 2022
        mask_n = noncross["event_year"] < 2022
    elif period == "2025plus":
        mask_c = cross["ts"] >= CUTOFF
        mask_n = noncross["ts"] >= CUTOFF
    elif period.isdigit():
        mask_c = cross["event_year"].eq(int(period))
        mask_n = noncross["event_year"].eq(int(period))
    else:
        raise KeyError(period)
    return cross.loc[mask_c], noncross.loc[mask_n]


def matched_cell_metrics(cross: pd.DataFrame, noncross: pd.DataFrame, cell: str) -> dict[str, Any]:
    regime = CELL_REGIME[cell]
    side = CELL_SIDE[cell]
    c = cross.loc[cross["cell"].eq(cell)].copy()
    same = "long_success" if side == "long" else "short_success"
    non = noncross.copy()
    key = ["date", "vol_bucket", "liq_bucket"]
    g = non.groupby(key).agg(
        n_non=("asset", "size"),
        same_success=(same, "mean"),
        rs_success=("rs_success", "mean"),
    )
    m = c.merge(g.reset_index(), on=key, how="left", suffixes=("", "_non"))
    ok = m["n_non"].fillna(0) > 0
    if int(ok.sum()) == 0:
        return {"cell": cell, "n": int(len(c)), "matched_n": 0, "match_rate": 0.0, "incremental_edge": float("nan"),
                "directional_edge": float("nan"), "regime_drift": float("nan")}
    sub = m.loc[ok]
    dir_edge = float(sub["real_success"].mean() - sub["rs_success"].mean())
    drift = float((sub["same_success"] - sub["rs_success_non"]).mean()) if "rs_success_non" in sub.columns else float("nan")
    if "rs_success_non" in sub.columns:
        drift = float((sub["same_success"] - sub["rs_success_non"]).mean())
        inc = incremental_edge(dir_edge, drift)
    else:
        inc = float("nan")
    return {
        "cell": cell,
        "n": int(len(c)),
        "matched_n": int(ok.sum()),
        "match_rate": float(ok.mean()),
        "directional_edge": dir_edge,
        "regime_drift": drift,
        "incremental_edge": inc,
    }


def matched_alignment(matched: dict[str, dict[str, Any]]) -> dict[str, Any]:
    def wmean(names: tuple[str, ...]) -> float:
        ns = np.array([matched[n]["matched_n"] for n in names], dtype=float)
        vs = np.array([matched[n]["incremental_edge"] for n in names], dtype=float)
        return date_weighted_mean(vs, ns)
    a = wmean(ALIGNED_CELLS)
    c = wmean(COUNTER_CELLS)
    return {
        "aligned_incremental_edge": a,
        "counter_incremental_edge": c,
        "regime_alignment_effect": a - c if np.isfinite(a) and np.isfinite(c) else float("nan"),
    }


def breadth_diagnostics(cross: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label in BREADTH_BIN_LABELS:
        for direction, side in (("UP", "long"), ("DOWN", "short")):
            sub = cross.loc[cross["breadth_bin"].eq(label) & cross["real_side"].eq(side)]
            real = float(sub["real_success"].mean()) if len(sub) else float("nan")
            rs = float(sub["rs_success"].mean()) if len(sub) else float("nan")
            rows.append({
                "breadth_bin": label,
                "cross": direction,
                "n": int(len(sub)),
                "real_success": real,
                "random_success": rs,
                "directional_edge": real - rs if np.isfinite(real) and np.isfinite(rs) else float("nan"),
            })
    return pd.DataFrame(rows)


def leave_one_out(cross: pd.DataFrame, noncross: pd.DataFrame) -> pd.DataFrame:
    rows = []
    pack = build_date_pack(cross, noncross)
    full = metrics_from_pack(pack)
    months = sorted(set(pack["month"].tolist()))
    for month in months:
        idx = np.where(pack["month"] != month)[0]
        m = metrics_from_pack(pack, idx)
        rows.append({
            "kind": "leave_one_month_out",
            "dropped": month,
            "BULL_UP_INCREMENTAL_EDGE": m["BULL_UP"]["incremental_edge"],
            "BEAR_DOWN_INCREMENTAL_EDGE": m["BEAR_DOWN"]["incremental_edge"],
            "REGIME_ALIGNMENT_EFFECT": m["ALIGNED"]["regime_alignment_effect"],
            "aligned_incremental_edge": m["ALIGNED"]["aligned_incremental_edge"],
        })
    blocks = sorted(set(int(b) for b in pack["block"].tolist()))
    for block in blocks:
        idx = np.where(pack["block"] != block)[0]
        m = metrics_from_pack(pack, idx)
        rows.append({
            "kind": "leave_one_28D_block_out",
            "dropped": str(block),
            "BULL_UP_INCREMENTAL_EDGE": m["BULL_UP"]["incremental_edge"],
            "BEAR_DOWN_INCREMENTAL_EDGE": m["BEAR_DOWN"]["incremental_edge"],
            "REGIME_ALIGNMENT_EFFECT": m["ALIGNED"]["regime_alignment_effect"],
            "aligned_incremental_edge": m["ALIGNED"]["aligned_incremental_edge"],
        })
    # asset LOO on event incrementals with date drift held from full sample (cross concentration)
    drift_by_date_side = {}
    six = compute_six_grid(cross, noncross)
    non_date = noncross.groupby("date").agg(long_s=("long_success", "mean"), short_s=("short_success", "mean"), rs=("rs_success", "mean"))
    c = cross.copy()
    c = c.merge(non_date, on="date", how="left")
    c["date_drift"] = np.where(
        c["real_side"].eq("long"), c["long_s"] - c["rs"],
        np.where(c["real_side"].eq("short"), c["short_s"] - c["rs"], np.nan),
    )
    c["event_inc"] = (c["real_success"] - c["rs_success"]) - c["date_drift"]
    for cell, sub_name in (("BULL_UP", "BULL_UP"), ("BEAR_DOWN", "BEAR_DOWN")):
        sub = c.loc[c["cell"].eq(cell)]
        for asset, g in sub.groupby("asset"):
            rest = sub.loc[sub["asset"] != asset, "event_inc"]
            rows.append({
                "kind": "leave_one_asset_out",
                "dropped": str(asset),
                "cell": cell,
                "BULL_UP_INCREMENTAL_EDGE": float(rest.mean()) if cell == "BULL_UP" and len(rest) else (full["BULL_UP"]["incremental_edge"] if cell != "BULL_UP" else float("nan")),
                "BEAR_DOWN_INCREMENTAL_EDGE": float(rest.mean()) if cell == "BEAR_DOWN" and len(rest) else (full["BEAR_DOWN"]["incremental_edge"] if cell != "BEAR_DOWN" else float("nan")),
                "REGIME_ALIGNMENT_EFFECT": float("nan"),
                "aligned_incremental_edge": float("nan"),
                "dropped_n": int(len(g)),
            })
    aligned = c.loc[c["cell"].isin(ALIGNED_CELLS)]
    for asset, g in aligned.groupby("asset"):
        rest = aligned.loc[aligned["asset"] != asset]
        if len(rest) == 0:
            continue
        # event-weighted aligned incremental approximation
        rows.append({
            "kind": "leave_one_asset_out",
            "dropped": str(asset),
            "cell": "ALIGNED",
            "BULL_UP_INCREMENTAL_EDGE": float("nan"),
            "BEAR_DOWN_INCREMENTAL_EDGE": float("nan"),
            "REGIME_ALIGNMENT_EFFECT": float("nan"),
            "aligned_incremental_edge": float(rest["event_inc"].mean()),
            "dropped_n": int(len(g)),
        })
    excl = compute_six_grid(
        cross.loc[~cross["asset"].isin([BTC_ASSET, ETH_ASSET])],
        noncross.loc[~noncross["asset"].isin([BTC_ASSET, ETH_ASSET])],
    )
    al = alignment_from_cells(excl)
    rows.append({
        "kind": "exclude_btc_eth",
        "dropped": "BTC/ETH",
        "BULL_UP_INCREMENTAL_EDGE": excl["BULL_UP"]["incremental_edge"],
        "BEAR_DOWN_INCREMENTAL_EDGE": excl["BEAR_DOWN"]["incremental_edge"],
        "REGIME_ALIGNMENT_EFFECT": al["regime_alignment_effect"],
        "aligned_incremental_edge": al["aligned_incremental_edge"],
    })
    return pd.DataFrame(rows)


def ci_supports_positive(stat: dict[str, Any]) -> bool:
    return bool(np.isfinite(stat.get("p2.5", np.nan)) and stat["p2.5"] > 0)


def year_sign_majority(year_df: pd.DataFrame, column: str, pooled: float) -> dict[str, Any]:
    years = year_df.loc[year_df["period"].isin(["2022", "2023", "2024", "2025", "2026"])].copy()
    vals = years[column].to_numpy(dtype=float)
    finite = vals[np.isfinite(vals)]
    if len(finite) == 0 or not np.isfinite(pooled) or pooled == 0:
        same = 0
    else:
        same = int(np.sum(np.sign(finite) == np.sign(pooled)))
    return {
        "n_years": int(len(finite)),
        "same_sign": same,
        "majority_same_sign": same > (len(finite) / 2.0) if len(finite) else False,
        "flip_count": int(len(finite) - same),
        "values": {str(p): float(v) if np.isfinite(v) else None for p, v in zip(years["period"], years[column])},
    }


def choose_verdict(
    *,
    identity_ok: bool,
    p7a_ok: bool,
    regime_ok: bool,
    baseline_ok: bool,
    cells: dict[str, dict[str, Any]],
    aligned: dict[str, Any],
    boot: dict[str, Any],
    primary_q: dict[str, float],
    year_df: pd.DataFrame,
    matched: dict[str, Any],
    loo: pd.DataFrame,
) -> str:
    if not (identity_ok and p7a_ok and regime_ok and baseline_ok):
        return "DATA_OR_REPRODUCTION_FAILURE"
    stats = boot["stats"]
    bull_inc = cells["BULL_UP"]["incremental_edge"]
    bear_inc = cells["BEAR_DOWN"]["incremental_edge"]
    align = aligned["regime_alignment_effect"]
    bull_ci = ci_supports_positive(stats["BULL_UP_INCREMENTAL_EDGE"])
    bear_ci = ci_supports_positive(stats["BEAR_DOWN_INCREMENTAL_EDGE"])
    align_ci = ci_supports_positive(stats["REGIME_ALIGNMENT_EFFECT"])
    bull_q = primary_q.get("BULL_UP_INCREMENTAL_EDGE", 1.0)
    bear_q = primary_q.get("BEAR_DOWN_INCREMENTAL_EDGE", 1.0)
    align_q = primary_q.get("REGIME_ALIGNMENT_EFFECT", 1.0)
    bull_sig = bull_ci and np.isfinite(bull_q) and bull_q < 0.05 and bull_inc > 0
    bear_sig = bear_ci and np.isfinite(bear_q) and bear_q < 0.05 and bear_inc > 0
    align_sig = align_ci and np.isfinite(align_q) and align_q < 0.05 and align > 0
    y_bull = year_sign_majority(year_df, "BULL_UP_INCREMENTAL_EDGE", bull_inc)
    y_bear = year_sign_majority(year_df, "BEAR_DOWN_INCREMENTAL_EDGE", bear_inc)
    y_align = year_sign_majority(year_df, "REGIME_ALIGNMENT_EFFECT", align)
    matched_bull = matched["cells"]["BULL_UP"]["incremental_edge"]
    matched_bear = matched["cells"]["BEAR_DOWN"]["incremental_edge"]
    matched_align = matched["alignment"]["regime_alignment_effect"]
    matched_ok = (
        np.isfinite(matched_bull) and matched_bull > 0
        and np.isfinite(matched_bear) and matched_bear > 0
        and np.isfinite(matched_align) and matched_align > 0
    )
    month_loo = loo.loc[loo["kind"].eq("leave_one_month_out")]
    block_loo = loo.loc[loo["kind"].eq("leave_one_28D_block_out")]

    def loo_keeps_sign(frame: pd.DataFrame, col: str, pooled: float) -> bool:
        if not np.isfinite(pooled) or pooled == 0 or frame.empty:
            return False
        vals = frame[col].to_numpy(dtype=float)
        finite = vals[np.isfinite(vals)]
        if len(finite) == 0:
            return False
        return bool(np.all(np.sign(finite) == np.sign(pooled)))

    not_single_month = loo_keeps_sign(month_loo, "BULL_UP_INCREMENTAL_EDGE", bull_inc) and loo_keeps_sign(month_loo, "BEAR_DOWN_INCREMENTAL_EDGE", bear_inc) and loo_keeps_sign(month_loo, "REGIME_ALIGNMENT_EFFECT", align)
    not_single_block = loo_keeps_sign(block_loo, "BULL_UP_INCREMENTAL_EDGE", bull_inc) and loo_keeps_sign(block_loo, "BEAR_DOWN_INCREMENTAL_EDGE", bear_inc) and loo_keeps_sign(block_loo, "REGIME_ALIGNMENT_EFFECT", align)
    if (
        bull_sig and bear_sig and align_sig
        and y_bull["majority_same_sign"] and y_bear["majority_same_sign"] and y_align["majority_same_sign"]
        and matched_ok and not_single_month and not_single_block
    ):
        return "REGIME_ALIGNED_DIRECTIONAL_EDGE_SUPPORTED"
    pooled_looks = bull_sig or bear_sig or align_sig
    year_unstable = (
        (np.isfinite(bull_inc) and bull_inc > 0 and not y_bull["majority_same_sign"])
        or (np.isfinite(bear_inc) and bear_inc > 0 and not y_bear["majority_same_sign"])
        or (np.isfinite(align) and align > 0 and not y_align["majority_same_sign"])
    )
    concentrated = pooled_looks and (not not_single_month or not not_single_block)
    if pooled_looks and (year_unstable or concentrated):
        if bull_sig and (not bear_sig) and y_bull["majority_same_sign"] and np.isfinite(matched_bull) and matched_bull > 0:
            return "BULL_ONLY_CONDITIONAL_EDGE"
        if bear_sig and (not bull_sig) and y_bear["majority_same_sign"] and np.isfinite(matched_bear) and matched_bear > 0:
            return "BEAR_ONLY_CONDITIONAL_EDGE"
        return "REGIME_EFFECT_TEMPORALLY_UNSTABLE"
    if bull_sig and (not bear_sig) and y_bull["majority_same_sign"] and np.isfinite(matched_bull) and matched_bull > 0:
        return "BULL_ONLY_CONDITIONAL_EDGE"
    if bear_sig and (not bull_sig) and y_bear["majority_same_sign"] and np.isfinite(matched_bear) and matched_bear > 0:
        return "BEAR_ONLY_CONDITIONAL_EDGE"
    bull_dir = cells["BULL_UP"]["directional_edge"]
    bear_dir = cells["BEAR_DOWN"]["directional_edge"]
    dir_looks = (
        (np.isfinite(bull_dir) and abs(bull_dir) >= 0.02)
        or (np.isfinite(bear_dir) and abs(bear_dir) >= 0.02)
        or ci_supports_positive(stats["BULL_UP_DIRECTIONAL_EDGE"])
        or ci_supports_positive(stats["BEAR_DOWN_DIRECTIONAL_EDGE"])
    )
    inc_near_zero = (not bull_sig) and (not bear_sig) and (not align_sig)
    if dir_looks and inc_near_zero:
        return "REGIME_DRIFT_EXPLAINS_APPARENT_EDGE"
    return "NO_REGIME_CONDITIONAL_DIRECTIONAL_EDGE"


def svg_escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def y_limits(values: list[float], *, zero_line: bool) -> tuple[float, float]:
    finite = [v for v in values if np.isfinite(v)]
    if not finite:
        return (-1.0, 1.0)
    ymin = min(finite)
    ymax = max(finite)
    pad = max(0.5, 0.08 * (ymax - ymin if ymax > ymin else 1.0))
    lo, hi = ymin - pad, ymax + pad
    if zero_line:
        lo = min(lo, 0.0)
        hi = max(hi, 0.0)
    return lo, hi


def write_svg(path: Path, width: int, height: int, body: str, title: str) -> None:
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="{width/2:.1f}" y="28" text-anchor="middle" font-size="15" font-family="sans-serif">{svg_escape(title)}</text>
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


def svg_grouped_bars(categories: list[str], series: list[tuple[str, list[float], str]], *, ylabel: str, title: str, path: Path, zero_line: bool = True) -> None:
    width, height = 980, 540
    left, right, top, bottom = 70, 940, 50, 420
    all_vals = [v for _, vals, _ in series for v in vals]
    ymin, ymax = y_limits(all_vals, zero_line=zero_line)
    n = max(len(categories), 1)
    group_w = (right - left) / n
    bar_w = group_w / (len(series) + 1.5)
    parts = [f'<text x="18" y="240" transform="rotate(-90 18 240)" font-size="12" font-family="sans-serif">{svg_escape(ylabel)}</text>']
    parts.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#333" />')
    _, z = chart_coords(left, right, top, bottom, 0, 1, ymin, ymax, 0, 0)
    parts.append(f'<line x1="{left}" y1="{z:.1f}" x2="{right}" y2="{z:.1f}" stroke="#666" stroke-dasharray="4 4" />')
    for i, cat in enumerate(categories):
        gx = left + i * group_w
        for j, (_name, vals, color) in enumerate(series):
            value = vals[i] if i < len(vals) and np.isfinite(vals[i]) else 0.0
            x0 = gx + (j + 0.4) * bar_w
            _, y = chart_coords(left, right, top, bottom, 0, 1, ymin, ymax, 0, value)
            y0 = min(y, z)
            h = abs(z - y)
            parts.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{color}" />')
        parts.append(f'<text x="{gx + group_w/2:.1f}" y="{bottom + 22}" text-anchor="middle" font-size="10" font-family="sans-serif">{svg_escape(cat)}</text>')
    legend_x = 80
    for name, _vals, color in series:
        parts.append(f'<rect x="{legend_x}" y="500" width="12" height="12" fill="{color}" />')
        parts.append(f'<text x="{legend_x + 18}" y="511" font-size="11" font-family="sans-serif">{svg_escape(name)}</text>')
        legend_x += 180
    write_svg(path, width, height, "\n".join(parts), title)


def svg_bars(items: list[tuple[str, float, str]], *, ylabel: str, title: str, path: Path) -> None:
    width, height = 920, 520
    left, right, top, bottom = 70, 880, 50, 420
    vals = [v for _, v, _ in items]
    ymin, ymax = y_limits(vals, zero_line=True)
    n = max(len(items), 1)
    gap = 16
    bar_w = max(18.0, (right - left - gap * (n + 1)) / n)
    parts = [f'<text x="18" y="240" transform="rotate(-90 18 240)" font-size="12" font-family="sans-serif">{svg_escape(ylabel)}</text>']
    parts.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#333" />')
    _, z = chart_coords(left, right, top, bottom, 0, 1, ymin, ymax, 0, 0)
    parts.append(f'<line x1="{left}" y1="{z:.1f}" x2="{right}" y2="{z:.1f}" stroke="#666" stroke-dasharray="4 4" />')
    for i, (label, value, color) in enumerate(items):
        x0 = left + gap + i * (bar_w + gap)
        v = value if np.isfinite(value) else 0.0
        _, y = chart_coords(left, right, top, bottom, 0, 1, ymin, ymax, 0, v)
        y0 = min(y, z)
        h = abs(z - y)
        parts.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{color}" />')
        parts.append(f'<text x="{x0 + bar_w/2:.1f}" y="{bottom + 22}" text-anchor="middle" font-size="10" font-family="sans-serif">{svg_escape(label)}</text>')
        parts.append(f'<text x="{x0 + bar_w/2:.1f}" y="{y0 - 6:.1f}" text-anchor="middle" font-size="10" font-family="sans-serif">{v:.2f}</text>')
    write_svg(path, width, height, "\n".join(parts), title)


def write_charts(cells: dict[str, dict[str, Any]], aligned: dict[str, Any], year_df: pd.DataFrame, breadth: pd.DataFrame, loo: pd.DataFrame, matched: dict[str, Any]) -> None:
    cats = list(SIX_GRID)
    real = [100.0 * cells[c]["real_success"] for c in cats]
    rs = [100.0 * cells[c]["random_success"] for c in cats]
    svg_grouped_bars(cats, [("Real", real, "#1f77b4"), ("Same-cross random", rs, "#ff7f0e")], ylabel="Success %", title="P7B six-grid real vs same-cross random", path=CHARTS["real_vs_random"])
    svg_bars([(c, 100.0 * cells[c]["directional_edge"], "#2ca02c") for c in cats], ylabel="pp", title="P7B six-grid cross directional edge", path=CHARTS["dir_edge"])
    svg_bars([(c, 100.0 * cells[c]["regime_drift"], "#9467bd") for c in cats], ylabel="pp", title="P7B six-grid regime directional drift", path=CHARTS["regime_drift"])
    svg_bars([(c, 100.0 * cells[c]["incremental_edge"], "#d62728") for c in cats], ylabel="pp", title="P7B six-grid incremental MA7 edge", path=CHARTS["incremental"])
    bu = cells["BULL_UP"]
    svg_bars([
        ("Real long", 100.0 * bu["real_success"], "#1f77b4"),
        ("Random", 100.0 * bu["random_success"], "#ff7f0e"),
        ("Non-cross long", 100.0 * bu["noncross_same_success"], "#8c564b"),
        ("Non-cross random", 100.0 * bu["noncross_random_success"], "#7f7f7f"),
    ], ylabel="Success %", title="P7B BULL_UP decomposition", path=CHARTS["bull_up_decomp"])
    bd = cells["BEAR_DOWN"]
    svg_bars([
        ("Real short", 100.0 * bd["real_success"], "#1f77b4"),
        ("Random", 100.0 * bd["random_success"], "#ff7f0e"),
        ("Non-cross short", 100.0 * bd["noncross_same_success"], "#8c564b"),
        ("Non-cross random", 100.0 * bd["noncross_random_success"], "#7f7f7f"),
    ], ylabel="Success %", title="P7B BEAR_DOWN decomposition", path=CHARTS["bear_down_decomp"])
    years = [p for p in ["pre_2022", "2022", "2023", "2024", "2025", "2026", "2025+"] if p in set(year_df["period"])]
    ymap = year_df.set_index("period")
    svg_bars([(p, 100.0 * float(ymap.loc[p, "BULL_UP_INCREMENTAL_EDGE"]), "#1f77b4") for p in years], ylabel="pp", title="P7B yearly BULL_UP incremental edge", path=CHARTS["year_bull_up"])
    svg_bars([(p, 100.0 * float(ymap.loc[p, "BEAR_DOWN_INCREMENTAL_EDGE"]), "#d62728") for p in years], ylabel="pp", title="P7B yearly BEAR_DOWN incremental edge", path=CHARTS["year_bear_down"])
    svg_bars([
        ("Aligned inc", 100.0 * aligned["aligned_incremental_edge"], "#2ca02c"),
        ("Counter inc", 100.0 * aligned["counter_incremental_edge"], "#d62728"),
        ("Alignment effect", 100.0 * aligned["regime_alignment_effect"], "#9467bd"),
    ], ylabel="pp", title="P7B aligned vs counter-regime incremental edge", path=CHARTS["aligned_counter"])
    up = breadth.loc[breadth["cross"].eq("UP")]
    down = breadth.loc[breadth["cross"].eq("DOWN")]
    bins = list(BREADTH_BIN_LABELS)
    svg_grouped_bars(
        bins,
        [
            ("UP edge", [100.0 * float(up.loc[up["breadth_bin"].eq(b), "directional_edge"].mean()) if len(up.loc[up["breadth_bin"].eq(b)]) else 0.0 for b in bins], "#1f77b4"),
            ("DOWN edge", [100.0 * float(down.loc[down["breadth_bin"].eq(b), "directional_edge"].mean()) if len(down.loc[down["breadth_bin"].eq(b)]) else 0.0 for b in bins], "#d62728"),
        ],
        ylabel="pp",
        title="P7B breadth bins x up/down cross directional edge",
        path=CHARTS["breadth"],
    )
    month_loo = loo.loc[loo["kind"].eq("leave_one_month_out")].copy()
    if len(month_loo):
        svg_grouped_bars(
            month_loo["dropped"].astype(str).tolist()[:: max(1, len(month_loo)//12)],
            [
                ("BULL_UP", (100.0 * month_loo["BULL_UP_INCREMENTAL_EDGE"]).tolist()[:: max(1, len(month_loo)//12)], "#1f77b4"),
                ("BEAR_DOWN", (100.0 * month_loo["BEAR_DOWN_INCREMENTAL_EDGE"]).tolist()[:: max(1, len(month_loo)//12)], "#d62728"),
            ],
            ylabel="pp",
            title="P7B leave-one-month-out incremental edges",
            path=CHARTS["loo_month"],
        )
    else:
        svg_bars([("none", 0.0, "#cccccc")], ylabel="pp", title="P7B leave-one-month-out incremental edges", path=CHARTS["loo_month"])
    svg_bars([
        ("BULL_UP date", 100.0 * cells["BULL_UP"]["incremental_edge"], "#1f77b4"),
        ("BULL_UP matched", 100.0 * matched["cells"]["BULL_UP"]["incremental_edge"], "#5fa8d3"),
        ("BEAR_DOWN date", 100.0 * cells["BEAR_DOWN"]["incremental_edge"], "#d62728"),
        ("BEAR_DOWN matched", 100.0 * matched["cells"]["BEAR_DOWN"]["incremental_edge"], "#e07a7a"),
        ("Align date", 100.0 * aligned["regime_alignment_effect"], "#9467bd"),
        ("Align matched", 100.0 * matched["alignment"]["regime_alignment_effect"], "#c5b0d5"),
    ], ylabel="pp", title="P7B vol/liquidity matched robustness", path=CHARTS["matched"])


def fmt_ci(stat: dict[str, Any]) -> str:
    if not np.isfinite(stat.get("p2.5", np.nan)):
        return "NA"
    return f"[{pp(stat['p2.5'])}, {pp(stat['p97.5'])}]"


def write_report(summary: dict[str, Any]) -> str:
    cells = {row["cell"]: row for row in summary["six_grid"]}
    bu = cells["BULL_UP"]
    bd = cells["BEAR_DOWN"]
    aligned = summary["alignment"]
    boot = summary["bootstrap"]["stats"]
    q = summary["bh_primary"]
    verdict = summary["verdict"]
    one_liner = {
        "DATA_OR_REPRODUCTION_FAILURE": "数据或复现门禁失败，停止机制解释。",
        "NO_REGIME_CONDITIONAL_DIRECTIONAL_EDGE": "分市场状态也无法挽救 MA7 方向假设。",
        "REGIME_DRIFT_EXPLAINS_APPARENT_EDGE": "表面上的格子差异主要来自市场本身的方向漂移，不是 MA7 增量。",
        "BULL_ONLY_CONDITIONAL_EDGE": "仅牛市 Up Cross 可能含有条件信息，不能推导熊市规则。",
        "BEAR_ONLY_CONDITIONAL_EDGE": "仅熊市 Down Cross 可能含有条件信息，不能推导牛市规则。",
        "REGIME_ALIGNED_DIRECTIONAL_EDGE_SUPPORTED": "MA7 方向信息可能依赖市场状态，但不是可交易策略。",
        "REGIME_EFFECT_TEMPORALLY_UNSTABLE": "历史上存在状态条件点估计，但稳定性不足。",
    }.get(verdict, verdict)
    lines = [
        "# BIN-1D-MA7-CTP P7B 市场状态条件下 MA7 穿越方向安慰剂审计",
        "",
        f"BULL_UP: Real success = {pct(bu['real_success'])}",
        f"Same-cross random = {pct(bu['random_success'])}",
        f"Cross directional edge = {pp(bu['directional_edge'])}",
        "",
        f"Bull non-cross long = {pct(bu['noncross_same_success'])}",
        f"Bull non-cross random = {pct(bu['noncross_random_success'])}",
        f"Bull regime directional drift = {pp(bu['regime_drift'])}",
        "",
        f"BULL_UP incremental MA7 edge = {pp(bu['directional_edge'])} - {pp(bu['regime_drift'])} = {pp(bu['incremental_edge'])}",
        f"95% CI = {fmt_ci(boot['BULL_UP_INCREMENTAL_EDGE'])}",
        "",
        f"BEAR_DOWN: Real success = {pct(bd['real_success'])}",
        f"Same-cross random = {pct(bd['random_success'])}",
        f"Cross directional edge = {pp(bd['directional_edge'])}",
        "",
        f"Bear non-cross short = {pct(bd['noncross_same_success'])}",
        f"Bear non-cross random = {pct(bd['noncross_random_success'])}",
        f"Bear regime directional drift = {pp(bd['regime_drift'])}",
        "",
        f"BEAR_DOWN incremental MA7 edge = {pp(bd['directional_edge'])} - {pp(bd['regime_drift'])} = {pp(bd['incremental_edge'])}",
        f"95% CI = {fmt_ci(boot['BEAR_DOWN_INCREMENTAL_EDGE'])}",
        "",
        f"REGIME_ALIGNMENT_EFFECT = {pp(aligned['regime_alignment_effect'])}",
        f"95% CI = {fmt_ci(boot['REGIME_ALIGNMENT_EFFECT'])}",
        "",
        f"一句话：{one_liner}",
        "",
        f"- 状态：`{STATUS}`",
        f"- `research_id`：`{RESEARCH_ID}`",
        f"- 合同锁：`{LOCK_STATUS}`",
        f"- 全局裁决：`{verdict}`",
        "- 本轮是已经观察过总体 P7A 与部分 P6 六格历史后的 targeted diagnostic，不是新盲测。",
        "- 禁止把 Bull 本身的 Long drift 或 Bear 本身的 Short drift 算成 MA7 增量。",
        "",
        "## 六格完整结果",
        "",
        "| Regime | Cross | N | Real | Same-Cross Random | Direction Edge | Non-Cross Same-Side | Regime Drift | Incremental MA7 Edge |",
        "| ------ | ----- | -: | ---: | ----------------: | -------------: | ------------------: | -----------: | -------------------: |",
    ]
    for cell in SIX_GRID:
        r = cells[cell]
        lines.append(
            f"| {r['regime']} | {r['cross']} | {r['n']} | {pct(r['real_success'])} | {pct(r['random_success'])} | {pp(r['directional_edge'])} | {pct(r['noncross_same_success'])} | {pp(r['regime_drift'])} | {pp(r['incremental_edge'])} |"
        )
    lines += [
        "",
        "## 主检验",
        "",
        f"- BULL_UP incremental {pp(bu['incremental_edge'])}，p={boot['BULL_UP_INCREMENTAL_EDGE']['p_two_sided']:.4f}，BH q={q['BULL_UP_INCREMENTAL_EDGE']:.4f}，CI {fmt_ci(boot['BULL_UP_INCREMENTAL_EDGE'])}。",
        f"- BEAR_DOWN incremental {pp(bd['incremental_edge'])}，p={boot['BEAR_DOWN_INCREMENTAL_EDGE']['p_two_sided']:.4f}，BH q={q['BEAR_DOWN_INCREMENTAL_EDGE']:.4f}，CI {fmt_ci(boot['BEAR_DOWN_INCREMENTAL_EDGE'])}。",
        f"- REGIME_ALIGNMENT_EFFECT {pp(aligned['regime_alignment_effect'])}，p={boot['REGIME_ALIGNMENT_EFFECT']['p_two_sided']:.4f}，BH q={q['REGIME_ALIGNMENT_EFFECT']:.4f}，CI {fmt_ci(boot['REGIME_ALIGNMENT_EFFECT'])}。",
        f"- BEAR_DOWN N={bd['n']}，dates={bd['unique_dates']}，CI width={pp(boot['BEAR_DOWN_INCREMENTAL_EDGE']['ci_width'])}；BULL_UP N={bu['n']}，dates={bu['unique_dates']}，CI width={pp(boot['BULL_UP_INCREMENTAL_EDGE']['ci_width'])}。",
        "",
        "## 年份",
        "",
        "| Period | BULL_UP inc | BEAR_DOWN inc | Alignment |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in summary["year_rows"]:
        tag = " `ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS`" if row["period"] in {"2025+", "2025plus", "2025"} or str(row["period"]).startswith("2025") else ""
        if row["period"] in {"2025+", "2026"} or str(row["period"]) == "2025plus":
            tag = " `ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS`"
        lines.append(f"| {row['period']}{tag} | {pp(row['BULL_UP_INCREMENTAL_EDGE'])} | {pp(row['BEAR_DOWN_INCREMENTAL_EDGE'])} | {pp(row['REGIME_ALIGNMENT_EFFECT'])} |")
    mx_up = cells["MIXED_UP"]
    mx_dn = cells["MIXED_DOWN"]
    lines += [
        "",
        "## Mixed 与反趋势 Cross",
        "",
        f"- MIXED_UP incremental {pp(mx_up['incremental_edge'])}（N={mx_up['n']}）。",
        f"- MIXED_DOWN incremental {pp(mx_dn['incremental_edge'])}（N={mx_dn['n']}）。",
        f"- 反趋势 BULL_DOWN incremental {pp(cells['BULL_DOWN']['incremental_edge'])}；BEAR_UP incremental {pp(cells['BEAR_UP']['incremental_edge'])}。",
        "",
        "## Vol/liquidity matched",
        "",
        f"- BULL_UP matched incremental {pp(summary['matched']['cells']['BULL_UP']['incremental_edge'])}，match rate {pct(summary['matched']['cells']['BULL_UP']['match_rate'])}。",
        f"- BEAR_DOWN matched incremental {pp(summary['matched']['cells']['BEAR_DOWN']['incremental_edge'])}，match rate {pct(summary['matched']['cells']['BEAR_DOWN']['match_rate'])}。",
        f"- Alignment matched {pp(summary['matched']['alignment']['regime_alignment_effect'])}。",
        "",
        "## 当前证据可以确认什么 / 不能确认什么",
        "",
        f"- 可以确认：在 P6 冻结 BULL/BEAR/MIXED 与 P7A canonical 标签下，六格 directional edge、regime drift 与 incremental MA7 edge 的分解；全局裁决 `{verdict}`。",
        "- 不能确认：可交易策略、账户收益、新 OOS、live-ready，或把 Bull/Bear 本身的同侧漂移写成 MA7 预测价值。",
        "",
        "## 图表",
        "",
    ]
    for key, path in CHARTS.items():
        lines.append(f"- [{path.name}](../artifacts/{path.name})")
    lines += [
        "",
        "## 产物",
        "",
        f"- [合同](../specs/{CONTRACT_PATH.name})",
        f"- [summary](../artifacts/{SUMMARY_PATH.name})",
        f"- [manifest](../artifacts/{MANIFEST_PATH.name})",
        "- [implementation audit](binance-1d-ma7-ctp-p7b-implementation-audit-2026-09-04.md)",
        "- [deferred registration](binance-1d-ma7-ctp-p7b-deferred-registration-2026-09-04.md)",
        "",
        "本轮未修改 family README、core ledger、decision log 或顶层索引。",
        "",
    ]
    return "\n".join(lines) + "\n"


def write_impl_audit(summary: dict[str, Any], lock: dict[str, Any], manifest: dict[str, Any]) -> str:
    iso = summary["isolation"]
    return "\n".join([
        "# BIN-1D-MA7-CTP P7B 实现审计",
        "",
        f"- 状态：`{STATUS}`",
        f"- 全局裁决：`{summary['verdict']}`",
        f"- 合同锁：`{LOCK_STATUS}`",
        f"- config sha256：`{summary['config_sha256']}`",
        f"- contract sha256：`{lock['contract_sha256']}`",
        f"- manifest sha256：`{manifest['manifest_sha256']}`",
        "",
        "## 输入隔离",
        "",
        f"- P7 输入文件数：`{iso['p7_input_files']}`（必须为 0）",
        f"- B0 分数未作为研究输入：`{iso['no_b0_input']}`",
        f"- HYPE 原始分区读取：`{iso['hype_raw_partition_read']}`",
        f"- HYPE 行数：`{summary['parity']['hype_rows']}`",
        f"- HYPER 行数：`{summary['parity']['hyper_rows']}`",
        f"- P7A dual-side 复现：`{summary['p7a_dual_parity']['ok']}`",
        f"- P6 regime parity：`{summary['regime_parity']['ok']}`",
        "",
        "## 未做的事",
        "",
        "- 无 ML 模型、无 B0 训练/打分、无策略权益曲线、无 Sharpe/CAGR、未改 P0–P7A 冻结产物、未改共享 README/ledger/decision log。",
        "",
        f"运行命令：`{summary['run_command']}`",
        "",
    ]) + "\n"


def write_deferred(summary: dict[str, Any]) -> str:
    return "\n".join([
        "# BIN-1D-MA7-CTP P7B 延迟登记说明",
        "",
        "P7B 完成时，同一家族的 P7 / P7A 或其他窗口可能仍在修改共享文档。本文件记录以后应如何把 P7B 登记进共享文档，而本轮不修改这些文件。",
        "",
        "## 以后应更新的文件",
        "",
        "1. `research/asset-portfolios/1d-ma7-cross-trend-probability/README.md`：增加 P7B 入口链接；不要覆盖 P7 / P7A 条目。",
        "2. `binance-1d-ma7-ctp-core-ledger.md`：Current State 增加 P7B sidecar 一行；Version Table 增加 P7B 行，状态 `explore / diagnostic-only / placebo-audit / not promoted / not live-ready`。",
        "3. `decision-log.md`：新增 2026-09-04 一条，只写一句话结论和证据链接。",
        "4. `artifacts/README.md`：增加 P7B 产物清单。",
        "5. `research/README.md` 与 `research/asset-portfolios/README.md`：仅在需要指向 P7B 报告时加链接，不复述指标。",
        "",
        "## 建议的 decision-log 草稿（登记时再写入）",
        "",
        f"决策：P7B 市场状态条件方向安慰剂审计裁决 `{summary['verdict']}`。BULL_UP incremental {pp(summary['six_grid'][0]['incremental_edge'] if False else [r for r in summary['six_grid'] if r['cell']=='BULL_UP'][0]['incremental_edge'])}，BEAR_DOWN incremental {pp([r for r in summary['six_grid'] if r['cell']=='BEAR_DOWN'][0]['incremental_edge'])}，alignment {pp(summary['alignment']['regime_alignment_effect'])}。不晋升、不改 runner。",
        "",
        "证据：`diagnostics/binance-1d-ma7-ctp-p7b-regime-conditional-direction-placebo-audit-2026-09-04.md`。",
        "",
    ]) + "\n"


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    generated_at = datetime.now(UTC).isoformat()
    run_command = (
        "/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python "
        "research/asset-portfolios/1d-ma7-cross-trend-probability/scripts/run_binance_1d_ma7_ctp_p7b_regime_conditional_direction_placebo_audit.py"
    )
    if SUMMARY_PATH.exists() and not args.force:
        print("P7B outputs exist; pass --force to overwrite", flush=True)
    config = build_config(generated_at=generated_at)
    print("freezing P7B contract/config/inventory before six-grid outcome read...", flush=True)
    inputs, lock = freeze_inputs(config)
    config_hash = lock["config_sha256"]

    print("loading P0R panel, restoring P7A dual-side, attaching P6 regime...", flush=True)
    raw = load_p0r_panel()
    dual, universe_audit = build_dual_side(raw)
    dual, p5_meta = attach_p5_identity(dual)
    universe_audit.update(p5_meta)
    p7a_parity = parity_p7a_dual(dual)
    dual = attach_vol_liq(dual)
    dual = add_event_economics(dual)
    real = dual.loc[dual["official_real"] & dual["real_side"].isin(["long", "short"])].copy()
    noncross = dual.loc[~dual["is_cross"]].copy()
    identity = real_event_parity(real)
    regime_parity = parity_p6_regime(real)

    print("computing six-grid date-matched incremental edges...", flush=True)
    cells = compute_six_grid(real, noncross)
    aligned = alignment_from_cells(cells)
    baseline_ok = all(cells[c]["coverage_n"] > 0 for c in SIX_GRID)
    pack = build_date_pack(real, noncross)
    boot_df, boot_summary = run_block_bootstrap(pack)
    point_map = {
        "BULL_UP_INCREMENTAL_EDGE": cells["BULL_UP"]["incremental_edge"],
        "BEAR_DOWN_INCREMENTAL_EDGE": cells["BEAR_DOWN"]["incremental_edge"],
        "REGIME_ALIGNMENT_EFFECT": aligned["regime_alignment_effect"],
        "aligned_incremental_edge": aligned["aligned_incremental_edge"],
        "counter_incremental_edge": aligned["counter_incremental_edge"],
        "BULL_UP_DIRECTIONAL_EDGE": cells["BULL_UP"]["directional_edge"],
        "BEAR_DOWN_DIRECTIONAL_EDGE": cells["BEAR_DOWN"]["directional_edge"],
        "BULL_UP_REGIME_DRIFT": cells["BULL_UP"]["regime_drift"],
        "BEAR_DOWN_REGIME_DRIFT": cells["BEAR_DOWN"]["regime_drift"],
    }
    for cell in SIX_GRID:
        point_map[f"{cell}_incremental_edge"] = cells[cell]["incremental_edge"]
        point_map[f"{cell}_directional_edge"] = cells[cell]["directional_edge"]
    for key, point in point_map.items():
        if key in boot_summary["stats"]:
            boot_summary["stats"][key]["point_from_full_sample"] = point

    primary_names = ["BULL_UP_INCREMENTAL_EDGE", "BEAR_DOWN_INCREMENTAL_EDGE", "REGIME_ALIGNMENT_EFFECT"]
    primary_p = [boot_summary["stats"][n]["p_two_sided"] for n in primary_names]
    primary_q = benjamini_hochberg(primary_p)
    bh_primary = dict(zip(primary_names, primary_q))
    secondary_names = [f"{cell}_incremental_edge" for cell in SIX_GRID]
    secondary_p = [boot_summary["stats"][n]["p_two_sided"] for n in secondary_names]
    secondary_q = benjamini_hochberg(secondary_p)
    bh_secondary = dict(zip(secondary_names, secondary_q))
    boot_summary["bh_primary"] = bh_primary
    boot_summary["bh_secondary"] = bh_secondary

    year_rows = []
    for period in PERIODS:
        c_p, n_p = period_frames(real, noncross, period)
        cell_p = compute_six_grid(c_p, n_p)
        al_p = alignment_from_cells(cell_p)
        rec = {
            "period": "2025+" if period == "2025plus" else period,
            "role": "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS" if period in {"2025", "2026", "2025plus"} else "historical",
            "BULL_UP_INCREMENTAL_EDGE": cell_p["BULL_UP"]["incremental_edge"],
            "BEAR_DOWN_INCREMENTAL_EDGE": cell_p["BEAR_DOWN"]["incremental_edge"],
            "REGIME_ALIGNMENT_EFFECT": al_p["regime_alignment_effect"],
            "BULL_UP_n": cell_p["BULL_UP"]["n"],
            "BEAR_DOWN_n": cell_p["BEAR_DOWN"]["n"],
        }
        year_rows.append(rec)
    year_df = pd.DataFrame(year_rows)

    matched_cells = {cell: matched_cell_metrics(real, noncross, cell) for cell in SIX_GRID}
    matched = {"cells": matched_cells, "alignment": matched_alignment(matched_cells)}
    breadth = breadth_diagnostics(real)
    print("running leave-one-out / concentration...", flush=True)
    loo = leave_one_out(real, noncross)

    strong_cross = real.copy()
    strong_cross["cell"] = np.where(
        strong_cross["strong_state"].eq("BULL") & strong_cross["real_side"].eq("long"), "BULL_UP",
        np.where(strong_cross["strong_state"].eq("BEAR") & strong_cross["real_side"].eq("short"), "BEAR_DOWN",
        np.where(strong_cross["strong_state"].eq("BULL") & strong_cross["real_side"].eq("short"), "BULL_DOWN",
        np.where(strong_cross["strong_state"].eq("BEAR") & strong_cross["real_side"].eq("long"), "BEAR_UP",
        np.where(strong_cross["strong_state"].eq("MIXED") & strong_cross["real_side"].eq("long"), "MIXED_UP",
        np.where(strong_cross["strong_state"].eq("MIXED") & strong_cross["real_side"].eq("short"), "MIXED_DOWN", "")))))
    )
    strong_non = noncross.copy()
    strong_cells = compute_six_grid(strong_cross.loc[strong_cross["cell"].ne("")], strong_non)
    strong_al = alignment_from_cells(strong_cells)

    identity_ok = not identity["reproduction_failure"]
    p7a_ok = bool(p7a_parity["ok"])
    regime_ok = bool(regime_parity["ok"])
    verdict = choose_verdict(
        identity_ok=identity_ok,
        p7a_ok=p7a_ok,
        regime_ok=regime_ok,
        baseline_ok=baseline_ok,
        cells=cells,
        aligned=aligned,
        boot=boot_summary,
        primary_q=bh_primary,
        year_df=year_df,
        matched=matched,
        loo=loo,
    )
    isolation = {
        "p7_input_files": int(sum(1 for p in inputs["files"] if "_p7_" in Path(p["path"]).name and "_p7a_" not in Path(p["path"]).name and "_p7b_" not in Path(p["path"]).name)),
        "hype_raw_partition_read": any(HYPE_SLUG in p.lower() and "hyper_usdt_usdt" not in p.lower() for p in FILES_READ),
        "hype_slug_in_files_read": any(HYPE_SLUG in p.lower() and "hyper_usdt_usdt" not in p.lower() for p in FILES_READ),
        "files_read": sorted(set(FILES_READ)),
        "no_b0_input": True,
        "no_ml": True,
        "shared_docs_modified": False,
    }
    six_rows = [cells[c] for c in SIX_GRID]
    drift_rows = [{
        "cell": c,
        "cross_directional_edge": cells[c]["directional_edge"],
        "regime_drift": cells[c]["regime_drift"],
        "incremental_edge": cells[c]["incremental_edge"],
        "formula": "incremental = (real - random) - (noncross_same - noncross_random)",
        "bull_drift_not_ma7": c.startswith("BULL"),
        "bear_drift_not_ma7": c.startswith("BEAR"),
    } for c in SIX_GRID]
    inc_rows = [{
        "cell": c,
        "incremental_edge": cells[c]["incremental_edge"],
        "p_two_sided": boot_summary["stats"][f"{c}_incremental_edge"]["p_two_sided"],
        "bh_q": bh_secondary[f"{c}_incremental_edge"],
        "ci_low": boot_summary["stats"][f"{c}_incremental_edge"]["p2.5"],
        "ci_high": boot_summary["stats"][f"{c}_incremental_edge"]["p97.5"],
        "family": "secondary",
    } for c in SIX_GRID]
    match_rows = [matched_cells[c] for c in SIX_GRID]

    summary = {
        "research_id": RESEARCH_ID,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "verdict": verdict,
        "generated_at": generated_at,
        "canonical_label_version": CANONICAL_LABEL_VERSION,
        "config_sha256": config_hash,
        "contract_lock_sha256": canonical_sha256(lock),
        "run_command": run_command,
        "parity": identity,
        "p7a_dual_parity": p7a_parity,
        "regime_parity": regime_parity,
        "universe_audit": universe_audit,
        "six_grid": six_rows,
        "alignment": aligned,
        "year_rows": year_df.to_dict("records"),
        "bootstrap": boot_summary,
        "bh_primary": bh_primary,
        "bh_secondary": bh_secondary,
        "matched": {
            "cells": {k: v for k, v in matched_cells.items()},
            "alignment": matched["alignment"],
        },
        "secondary_regime_strength": {
            "label": "SECONDARY_REGIME_STRENGTH_SENSITIVITY",
            "strong_bull_up_incremental": strong_cells["BULL_UP"]["incremental_edge"],
            "strong_bear_down_incremental": strong_cells["BEAR_DOWN"]["incremental_edge"],
            "strong_alignment": strong_al["regime_alignment_effect"],
            "strong_bull_up_n": strong_cells["BULL_UP"]["n"],
            "strong_bear_down_n": strong_cells["BEAR_DOWN"]["n"],
        },
        "breadth_rows": breadth.to_dict("records"),
        "isolation": isolation,
        "no_ml": True,
        "no_equity_curve": True,
        "no_b0": True,
        "interpretation_rule": config["interpretation_rule"],
        "2025plus_role": "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS",
    }

    atomic_write_json(DATA_AUDIT_PATH, {
        "research_id": RESEARCH_ID,
        "universe": universe_audit,
        "hype": isolation,
        "panel_rows": int(len(raw)),
        "official_n": int(len(real)),
        "noncross_n": int(len(noncross)),
        "unknown_official": int(real["market_state"].eq("UNKNOWN").sum()),
    })
    atomic_write_json(EVENT_REGIME_PARITY_PATH, {
        "research_id": RESEARCH_ID,
        "identity": identity,
        "p7a_dual": p7a_parity,
        "p6_regime": regime_parity,
        "timing": {
            "feature_known_at_equals_entry_ts": True,
            "no_future_regime": True,
            "bull_threshold": BULL_BREADTH,
            "bear_threshold": BEAR_BREADTH,
        },
    })
    atomic_write_csv(SIX_GRID_CSV, pd.DataFrame(six_rows))
    atomic_write_csv(DRIFT_CSV, pd.DataFrame(drift_rows))
    atomic_write_csv(INCREMENTAL_CSV, pd.DataFrame(inc_rows))
    atomic_write_csv(YEAR_CSV, year_df)
    atomic_write_csv(BREADTH_CSV, breadth)
    atomic_write_csv(MATCH_CSV, pd.DataFrame(match_rows))
    loo = loo.copy()
    loo["research_id"] = RESEARCH_ID
    atomic_write_parquet(LOO_PATH, loo)
    boot_df["research_id"] = RESEARCH_ID
    atomic_write_parquet(BOOTSTRAP_PATH, boot_df)
    write_charts(cells, aligned, year_df, breadth, loo, {"cells": matched_cells, "alignment": matched["alignment"]})
    atomic_write_json(SUMMARY_PATH, summary)
    report = write_report(summary)
    atomic_write_text(REPORT_PATH, report)

    output_paths = [
        CONTRACT_PATH, CONFIG_PATH, CONTRACT_LOCK_PATH, INPUT_INVENTORY_PATH, DATA_AUDIT_PATH,
        EVENT_REGIME_PARITY_PATH, SIX_GRID_CSV, DRIFT_CSV, INCREMENTAL_CSV, YEAR_CSV, BREADTH_CSV,
        MATCH_CSV, LOO_PATH, BOOTSTRAP_PATH, SUMMARY_PATH, REPORT_PATH, SCRIPT_PATH, TEST_PATH,
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
        "bull_up_inc": cells["BULL_UP"]["incremental_edge"],
        "bear_down_inc": cells["BEAR_DOWN"]["incremental_edge"],
        "alignment": aligned["regime_alignment_effect"],
        "identity_ok": identity_ok,
        "p7a_ok": p7a_ok,
        "regime_ok": regime_ok,
        "hype_rows": identity["hype_rows"],
        "hyper_rows": identity["hyper_rows"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
