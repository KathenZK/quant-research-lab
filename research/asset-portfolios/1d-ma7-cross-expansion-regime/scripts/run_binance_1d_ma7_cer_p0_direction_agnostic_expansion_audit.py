#!/usr/bin/env python3
"""Run BIN-1D-MA7-CER P0 direction-agnostic expansion event audit.

Independent family. Does not train models, invent a composite score, or
treat MA7 cross direction as a prediction target.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import warnings

import duckdb
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


warnings.filterwarnings(
    "ignore",
    message="no explicit representation of timezones available for np.datetime64",
)


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-expansion-regime"
OLD_FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
CATL_DIR = ROOT / "research/asset-portfolios/1d-cross-asset-trend-lifecycle"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAGNOSTIC_DIR = FAMILY_DIR / "diagnostics"
SPEC_DIR = FAMILY_DIR / "specs"

PANEL_DIR = CATL_DIR / "artifacts/p0r_donor_directional_modeling_panel"
PANEL_GLOB = PANEL_DIR / "**/*.parquet"
DAILY_PANEL_DIR = CATL_DIR / "artifacts/p0_asset_day_feature_panel"
P0R_FEATURE_BLOCKS_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_feature_blocks.json"
P0R_MANIFEST_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_manifest.json"
P0R_SUMMARY_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_summary.json"

P5_VALIDATION_PATH = OLD_FAMILY_DIR / "artifacts/binance_1d_ma7_ctp_p5_validation_2025_plus_predictions.parquet"
P5_OOF_PATH = OLD_FAMILY_DIR / "artifacts/binance_1d_ma7_ctp_p5_pre2025_oof_predictions.parquet"
P5_DATA_AUDIT_PATH = OLD_FAMILY_DIR / "artifacts/binance_1d_ma7_ctp_p5_data_audit.json"
P5_SUMMARY_PATH = OLD_FAMILY_DIR / "artifacts/binance_1d_ma7_ctp_p5_summary.json"

CONTRACT_PATH = SPEC_DIR / "binance-1d-ma7-cer-p0-direction-agnostic-expansion-audit-contract-2026-09-04.md"
SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_cer_p0_direction_agnostic_expansion_audit.py"

PREFIX = "binance_1d_ma7_cer_p0_"
RESEARCH_ID = "BIN-1D-MA7-CER-P0-2026-09-04"
SCHEMA_VERSION = "cer.p0.v1"
STATUS = "explore / diagnostic-only / not promoted / not live-ready"
LOCK_STATUS = "FROZEN_BEFORE_P0_EXPANSION_OUTPUT_READ"
CANONICAL_UNIVERSE_VERSION = "CATL-P0R-donor-panel-hype-sealed"
CANONICAL_EVENT_VERSION = "P5-P7A-ma7-cross-identity-direction-as-metadata-only"
PRIMARY_HORIZON = 5
HORIZONS = (1, 3, 5, 10, 20)
VOL_HORIZONS = (3, 5, 10, 20)
EFF_HORIZONS = (3, 5, 10, 20)
EVENT_TIME_WINDOW = 20
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_BLOCK_DAYS = 28
BOOTSTRAP_SEED = 20260901
MC_N = 500
MC_SEED_START = 2026090400
MC_SEED_END = 2026090899
CUTOFF = pd.Timestamp("2025-01-01T00:00:00Z")
EXPECTED_2025_PLUS = 46892
EXPECTED_2025 = 32111
EXPECTED_2026 = 14781
HYPE_ASSET = "HYPE/USDT:USDT"
HYPE_SLUG = "hype_usdt_usdt"
HYPER_ASSET = "HYPER/USDT:USDT"
BULL_BREADTH = 0.60
BEAR_BREADTH = 0.40
LIQ_CUTS = (1.0 / 3.0, 2.0 / 3.0)
DOMINANCE_EPS = 1e-12
MATERIAL_ABS_ATR = 0.20
MATERIAL_REL = 0.10
MC_EXCURSION_TOL = 0.02
MC_RATIO_TOL = 0.01

KNOWN_TRADFI_BASE_SYMBOLS = {
    "AAPL", "AMZN", "COIN", "CRCL", "GOOGL", "HOOD", "META", "MSFT", "MSTR",
    "NVDA", "PLTR", "TSLA", "SPX", "SPY", "QQQ", "TSM", "UBER", "XAU", "XAG",
    "XPD", "XPT",
}

BH_METRICS = (
    "max_abs_excursion",
    "future_range",
    "vol_expansion_ratio",
    "path_efficiency",
    "abs_terminal",
)

VERDICT_CANDIDATES = (
    "DATA_OR_REPRODUCTION_FAILURE",
    "NO_EXPANSION_EDGE",
    "CROSS_IS_LAGGING_EXPANSION_MARKER",
    "WEAK_EXPANSION_MARKER",
    "EXPANSION_EVENT_SUPPORTED",
)

CONFIG_PATH = ARTIFACT_DIR / f"{PREFIX}config.json"
CONTRACT_LOCK_PATH = ARTIFACT_DIR / f"{PREFIX}contract_lock.json"
INPUT_INVENTORY_PATH = ARTIFACT_DIR / f"{PREFIX}input_inventory.json"
DATA_AUDIT_PATH = ARTIFACT_DIR / f"{PREFIX}data_audit.json"
EVENT_PARITY_PATH = ARTIFACT_DIR / f"{PREFIX}event_parity.json"
OUTCOMES_PATH = ARTIFACT_DIR / f"{PREFIX}outcomes.parquet"
PLACEBO_OUTCOMES_PATH = ARTIFACT_DIR / f"{PREFIX}placebo_outcomes.parquet"
MAIN_EFFECTS_PATH = ARTIFACT_DIR / f"{PREFIX}main_effects.csv"
YEAR_BREAKDOWN_PATH = ARTIFACT_DIR / f"{PREFIX}year_breakdown.csv"
EVENT_TIME_PATH = ARTIFACT_DIR / f"{PREFIX}event_time_study.parquet"
BOOTSTRAP_PATH = ARTIFACT_DIR / f"{PREFIX}bootstrap.parquet"
SUMMARY_PATH = ARTIFACT_DIR / f"{PREFIX}summary.json"
MANIFEST_PATH = ARTIFACT_DIR / f"{PREFIX}manifest.json"
REPORT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-cer-p0-direction-agnostic-expansion-audit-2026-09-04.md"
IMPL_AUDIT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-cer-p0-implementation-audit-2026-09-04.md"

CHARTS = {
    "excursion": ARTIFACT_DIR / f"{PREFIX}chart_01_max_abs_excursion.svg",
    "range": ARTIFACT_DIR / f"{PREFIX}chart_02_future_range.svg",
    "vol": ARTIFACT_DIR / f"{PREFIX}chart_03_realized_vol_expansion.svg",
    "efficiency": ARTIFACT_DIR / f"{PREFIX}chart_04_path_efficiency.svg",
    "terminal": ARTIFACT_DIR / f"{PREFIX}chart_05_terminal_displacement.svg",
    "et_vol": ARTIFACT_DIR / f"{PREFIX}chart_06_event_time_volatility.svg",
    "et_range": ARTIFACT_DIR / f"{PREFIX}chart_07_event_time_range.svg",
    "prepost": ARTIFACT_DIR / f"{PREFIX}chart_08_prepost_expansion_ratio.svg",
    "yearly": ARTIFACT_DIR / f"{PREFIX}chart_09_yearly_effect.svg",
    "updown": ARTIFACT_DIR / f"{PREFIX}chart_10_up_down_cross.svg",
}

FILES_READ: list[str] = []
BANNED_OUTCOME_SUBSTRINGS = (
    "label_entry_success",
    "directional_success",
    "equity",
    "sharpe",
    "cagr",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(json_ready(payload), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


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


def event_identity_hash(frame: pd.DataFrame, side_col: str = "cross_side") -> str:
    keys = frame[["asset", "ts", side_col]].copy()
    ts = pd.to_datetime(keys["ts"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    lines = sorted(
        f"{a}|{t}|{s}"
        for a, t, s in zip(keys["asset"].astype(str), ts, keys[side_col].astype(str))
    )
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def calendar_block_id(ts: pd.Series, *, origin: pd.Timestamp | None = None) -> pd.Series:
    times = pd.to_datetime(ts, utc=True)
    if origin is None:
        start = times.min()
    else:
        start = pd.to_datetime(origin, utc=True)
    if pd.isna(start):
        raise RuntimeError("calendar block origin is missing")
    start = _utc_normalize(start)
    return ((times.dt.normalize() - start).dt.days // BOOTSTRAP_BLOCK_DAYS).astype(int)


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


def finite_mean(values: np.ndarray) -> float:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    return float(np.mean(x)) if len(x) else float("nan")


def finite_median(values: np.ndarray) -> float:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    return float(np.median(x)) if len(x) else float("nan")


def finite_quantile(values: np.ndarray, q: float) -> float:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    return float(np.quantile(x, q)) if len(x) else float("nan")


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    mask = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not mask.any():
        return float("nan")
    return float(np.average(v[mask], weights=w[mask]))


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    mask = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not mask.any():
        return float("nan")
    v = v[mask]
    w = w[mask]
    order = np.argsort(v)
    v = v[order]
    cw = np.cumsum(w[order])
    cutoff = q * cw[-1]
    idx = int(np.searchsorted(cw, cutoff, side="left"))
    idx = min(max(idx, 0), len(v) - 1)
    return float(v[idx])


def liq_bucket(rank: float) -> str:
    if not np.isfinite(rank):
        return "unknown"
    if rank <= LIQ_CUTS[0]:
        return "low"
    if rank <= LIQ_CUTS[1]:
        return "mid"
    return "high"


def market_state(breadth: float, btc_above: float) -> str:
    if not np.isfinite(breadth) or not np.isfinite(btc_above):
        return "UNKNOWN"
    if breadth >= BULL_BREADTH and btc_above > 0:
        return "BULL"
    if breadth <= BEAR_BREADTH and btc_above < 1:
        return "BEAR"
    return "MIXED"


def fmt(value: float | None, digits: int = 4) -> str:
    if value is None or not np.isfinite(value):
        return "NA"
    return f"{float(value):.{digits}f}"


def fmt_ci(lo: float, hi: float, digits: int = 4) -> str:
    if not np.isfinite(lo) or not np.isfinite(hi):
        return "[NA, NA]"
    return f"[{lo:.{digits}f}, {hi:.{digits}f}]"


def build_config(*, generated_at: str) -> dict[str, Any]:
    return {
        "research_id": RESEARCH_ID,
        "schema_version": SCHEMA_VERSION,
        "experiment": "P0 Direction-Agnostic Expansion Event Audit",
        "status": STATUS,
        "lock_status": LOCK_STATUS,
        "family": "Binance-1D-MA7-Cross-Expansion-Regime",
        "alias": "BIN-1D-MA7-CER",
        "not_ctp_p8": True,
        "direction_agnostic": True,
        "primary_horizon_days": PRIMARY_HORIZON,
        "secondary_horizons_days": [h for h in HORIZONS if h != PRIMARY_HORIZON],
        "outcomes": list(BH_METRICS) + ["dominance"],
        "primary_baseline": "DATE_MATCHED_NON_CROSS",
        "placebo_groups": [
            "DATE_MATCHED_NON_CROSS",
            "SAME_ASSET_RANDOM_NON_CROSS_DATE",
            "DATE_AND_VOL_MATCHED_NON_CROSS",
            "DATE_LIQUIDITY_VOL_MATCHED_NON_CROSS",
        ],
        "bootstrap": {"n": BOOTSTRAP_SAMPLES, "block_days": BOOTSTRAP_BLOCK_DAYS, "seed": BOOTSTRAP_SEED},
        "monte_carlo": {"n": MC_N, "seed_start": MC_SEED_START, "seed_end": MC_SEED_END},
        "bh_family": list(BH_METRICS),
        "material_abs_atr": MATERIAL_ABS_ATR,
        "material_relative": MATERIAL_REL,
        "canonical_universe_version": CANONICAL_UNIVERSE_VERSION,
        "canonical_event_version": CANONICAL_EVENT_VERSION,
        "hype_asset": HYPE_ASSET,
        "hyper_asset": HYPER_ASSET,
        "no_ml": True,
        "no_equity_curve": True,
        "no_composite_score": True,
        "no_directional_success_label": True,
        "verdict_candidates": list(VERDICT_CANDIDATES),
        "generated_at": generated_at,
        "realized_vol_definition": "sqrt(sum(log(close_t/close_t-1)^2)) over complete UTC days; pre uses returns ending at T0",
        "atr_anchor": "event-day P0R atr_anchor only",
        "entry_ref": "next UTC day open from P0R",
    }


def list_p0r_files() -> list[Path]:
    files = sorted(PANEL_DIR.rglob("*.parquet"))
    if not files:
        raise RuntimeError("P0R donor panel is empty")
    for path in files:
        note_read(path)
    return files


def list_daily_files(slugs: set[str]) -> list[Path]:
    files: list[Path] = []
    if HYPE_SLUG in slugs:
        raise RuntimeError("HYPE slug leaked into allowed daily partitions")
    for slug in sorted(slugs):
        if slug == HYPE_SLUG:
            continue
        part = DAILY_PANEL_DIR / f"asset_slug_partition={slug}"
        if not part.exists():
            continue
        files.extend(sorted(part.rglob("*.parquet")))
    for path in files:
        note_read(path)
    if not files:
        raise RuntimeError("no daily feature-panel files for allowed slugs")
    return files


def freeze_inputs(config: dict[str, Any], daily_files: list[Path], p0r_files: list[Path]) -> tuple[dict[str, Any], dict[str, Any]]:
    static = [
        CONTRACT_PATH, SCRIPT_PATH, P0R_FEATURE_BLOCKS_PATH, P0R_MANIFEST_PATH, P0R_SUMMARY_PATH,
        P5_VALIDATION_PATH, P5_OOF_PATH, P5_DATA_AUDIT_PATH, P5_SUMMARY_PATH,
    ]
    for path in static:
        note_read(path)
    inputs: dict[str, Any] = {"research_id": RESEARCH_ID, "schema_version": SCHEMA_VERSION, "files": []}
    hashed: dict[str, str] = {}
    all_paths = [*static, *p0r_files, *daily_files]
    for i, path in enumerate(all_paths, start=1):
        if i == 1 or i % 500 == 0 or i == len(all_paths):
            print(f"hashing inputs {i}/{len(all_paths)}", flush=True)
        digest = sha256_file(path)
        hashed[rel(path)] = digest
        inputs["files"].append({"path": rel(path), "sha256": digest, "bytes": path.stat().st_size})
    if any("_p7_" in Path(item["path"]).name and "_p7a_" not in Path(item["path"]).name for item in inputs["files"]):
        raise RuntimeError("P7 artifacts must not be inputs")
    if any(HYPE_SLUG in item["path"].lower() and "hyper_usdt_usdt" not in item["path"].lower() for item in inputs["files"]):
        raise RuntimeError("HYPE partition leaked into input inventory")
    inputs["n_files"] = len(inputs["files"])
    inputs["input_set_sha256"] = canonical_sha256(hashed)
    lock = {
        "research_id": RESEARCH_ID,
        "schema_version": SCHEMA_VERSION,
        "status": LOCK_STATUS,
        "contract_sha256": hashed[rel(CONTRACT_PATH)],
        "config_sha256": canonical_sha256(config),
        "script_sha256": hashed[rel(SCRIPT_PATH)],
        "input_inventory_sha256": canonical_sha256(inputs),
        "canonical_event_version": CANONICAL_EVENT_VERSION,
        "canonical_universe_version": CANONICAL_UNIVERSE_VERSION,
        "primary_horizon_days": PRIMARY_HORIZON,
    }
    atomic_write_json(CONFIG_PATH, config)
    atomic_write_json(INPUT_INVENTORY_PATH, inputs)
    atomic_write_json(CONTRACT_LOCK_PATH, lock)
    return inputs, lock


def load_p0r_panel() -> pd.DataFrame:
    cols = [
        "asset", "asset_slug", "side", "ts", "feature_known_at", "entry_ts", "entry_ref", "atr_anchor",
        "model_eligible_entry_p0r", "probe_raw_ma7_cross_dir", "future_path_complete_20d",
        "future_path_complete_5d", "volatility_state_p0r", "liquidity_rank_pct_p0r", "atr14_pct",
        "dir_market_breadth_ma30_p0r", "dir_btc_price_side_ma30",
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
    for col in ["ts", "feature_known_at", "entry_ts"]:
        df[col] = pd.to_datetime(df[col], utc=True)
    if (df["asset"] == HYPE_ASSET).any():
        raise RuntimeError("HYPE rows leaked into P0R load")
    df["side"] = df["side"].astype(str).str.lower()
    df["base_symbol"] = df["asset"].map(base_symbol)
    df["is_known_tradfi"] = df["base_symbol"].isin(KNOWN_TRADFI_BASE_SYMBOLS)
    df["event_year"] = df["ts"].dt.year.astype(int)
    return df


def build_eligible_days(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
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
    out = pd.DataFrame({
        "asset": merged["asset"],
        "asset_slug": merged["asset_slug"],
        "ts": merged["ts"],
        "event_year": merged["event_year_long"],
        "feature_known_at": merged["feature_known_at_long"],
        "entry_ts": merged["entry_ts_long"],
        "entry_ref": merged["entry_ref_long"],
        "atr_anchor": merged["atr_anchor_long"],
        "atr14_pct": merged["atr14_pct_long"],
        "future_path_complete_5d": merged["future_path_complete_5d_long"].astype(bool),
        "future_path_complete_20d": merged["future_path_complete_20d_long"].astype(bool),
        "volatility_state_p0r": merged["volatility_state_p0r_long"].astype(str),
        "liquidity_rank_pct_p0r": merged["liquidity_rank_pct_p0r_long"].astype(float),
        "is_cross": merged["probe_raw_ma7_cross_dir_long"] | merged["probe_raw_ma7_cross_dir_short"],
        "cross_side": np.where(
            merged["probe_raw_ma7_cross_dir_long"],
            "up",
            np.where(merged["probe_raw_ma7_cross_dir_short"], "down", ""),
        ),
        "hyper": merged["asset"].eq(HYPER_ASSET),
    })
    out["liq_bucket"] = out["liquidity_rank_pct_p0r"].map(liq_bucket)
    out["date"] = out["ts"].dt.normalize()
    audit = {
        "eligible_directional_rows": int(len(eligible)),
        "dual_side_asset_days": int(len(out)),
        "entry_ref_mismatch": entry_mismatch,
        "atr_mismatch": atr_mismatch,
        "entry_ts_mismatch": entry_ts_mismatch,
        "hype_rows": int((out["asset"] == HYPE_ASSET).sum()),
        "hyper_rows": int(out["hyper"].sum()),
        "cross_asset_days": int(out["is_cross"].sum()),
        "non_cross_asset_days": int((~out["is_cross"]).sum()),
    }
    if audit["hype_rows"] != 0:
        raise RuntimeError("HYPE rows in eligible days")
    if audit["hyper_rows"] <= 0:
        raise RuntimeError("HYPER missing from eligible days")
    if entry_mismatch or atr_mismatch or entry_ts_mismatch:
        raise RuntimeError("long/short identity mismatch on entry/ATR")
    return out, audit


def attach_official_identity(days: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
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
    p5_val_main["cross_side"] = np.where(p5_val_main["side"].eq("long"), "up", np.where(p5_val_main["side"].eq("short"), "down", ""))

    def key(frame: pd.DataFrame) -> pd.Series:
        return (
            frame["asset"].astype(str)
            + "|"
            + pd.to_datetime(frame["ts"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S%z")
            + "|"
            + frame["cross_side"].astype(str)
        )

    val_keys = set(key(p5_val_main))
    out = days.copy()
    out["event_key"] = key(out)
    out["in_p5_val"] = out["is_cross"] & out["event_key"].isin(val_keys)
    out["official_real"] = out["is_cross"] & ((out["ts"] < CUTOFF) | out["in_p5_val"])
    plus = out.loc[out["official_real"] & (out["ts"] >= CUTOFF)]
    unofficial_extra = out.loc[out["is_cross"] & (out["ts"] >= CUTOFF) & ~out["in_p5_val"]]
    plus_keys = set(key(plus))
    extra = plus_keys - val_keys
    missing = val_keys - plus_keys
    parity = {
        "p5_validation_main": int(len(p5_val_main)),
        "identity_extra_vs_p5_val": int(len(extra)),
        "identity_missing_vs_p5_val": int(len(missing)),
        "unofficial_2025_plus_probe_not_in_p5": int(len(unofficial_extra)),
        "real_2025_plus": int(len(plus)),
        "real_2025": int(((plus["event_year"] == 2025)).sum()),
        "real_2026": int(((plus["event_year"] == 2026)).sum()),
        "canonical_event_id_hash_2025_plus": event_identity_hash(plus),
        "p5_event_id_hash": event_identity_hash(p5_val_main),
        "hype_rows": int((out["asset"] == HYPE_ASSET).sum()),
        "hyper_rows": int(out["hyper"].sum()),
        "official_n": int(out["official_real"].sum()),
        "official_hyper_n": int(out.loc[out["official_real"], "hyper"].sum()),
    }
    parity["anchors_ok"] = (
        parity["real_2025_plus"] == EXPECTED_2025_PLUS
        and parity["real_2025"] == EXPECTED_2025
        and parity["real_2026"] == EXPECTED_2026
        and parity["identity_extra_vs_p5_val"] == 0
        and parity["identity_missing_vs_p5_val"] == 0
        and parity["canonical_event_id_hash_2025_plus"] == parity["p5_event_id_hash"]
        and parity["hype_rows"] == 0
        and parity["hyper_rows"] > 0
    )
    parity["reproduction_failure"] = not parity["anchors_ok"]
    return out, parity


def load_daily_ohlc(files: list[Path], slugs: set[str]) -> pd.DataFrame:
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    df = con.execute(
        """
        SELECT
            asset, asset_slug, ts, open, high, low, close, quote_volume,
            atr14, market_breadth_above_ma30, btc_above_ma30, complete_day
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        WHERE asset <> ?
          AND complete_day = true
        """,
        [[str(p) for p in files], HYPE_ASSET],
    ).fetchdf()
    con.close()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    if (df["asset"] == HYPE_ASSET).any():
        raise RuntimeError("HYPE rows in daily OHLC")
    if df["asset_slug"].eq(HYPE_SLUG).any():
        raise RuntimeError("HYPE slug in daily OHLC")
    extra = set(df["asset_slug"].unique()) - slugs
    if extra:
        raise RuntimeError(f"unexpected daily slugs: {sorted(extra)[:5]}")
    return df.sort_values(["asset", "ts"]).reset_index(drop=True)


def _window_stat(arr: np.ndarray, start_offset: int, length: int, how: str) -> np.ndarray:
    n = len(arr)
    out = np.full(n, np.nan)
    if length <= 0 or n < length:
        return out
    i_min = max(0, -start_offset)
    i_max = n - start_offset - length
    if i_max < i_min:
        return out
    view = sliding_window_view(arr, length)
    idx = np.arange(i_min, i_max + 1)
    src = idx + start_offset
    if how == "max":
        out[idx] = view[src].max(axis=1)
    elif how == "min":
        out[idx] = view[src].min(axis=1)
    elif how == "sum":
        out[idx] = view[src].sum(axis=1)
    elif how == "first":
        out[idx] = view[src][:, 0]
    elif how == "last":
        out[idx] = view[src][:, -1]
    else:
        raise ValueError(how)
    return out


def _utc_normalize(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.normalize()


def _daynum(ts: np.ndarray | pd.Series) -> np.ndarray:
    idx = pd.DatetimeIndex(pd.to_datetime(ts, utc=True))
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    delta = idx.normalize() - pd.Timestamp("1970-01-01", tz="UTC")
    return np.asarray(delta / pd.Timedelta(days=1), dtype=np.int64)


def _calendar_ok_from_days(days: np.ndarray, offset: int) -> np.ndarray:
    n = len(days)
    out = np.zeros(n, dtype=bool)
    if offset == 0:
        out[:] = True
        return out
    if offset > 0:
        span = n - offset
        if span > 0:
            out[:span] = (days[offset:] - days[:span]) == offset
        return out
    k = -offset
    span = n - k
    if span > 0:
        out[k:] = (days[k:] - days[:span]) == k
    return out


def _calendar_ok(ts: np.ndarray | pd.Series, offset: int) -> np.ndarray:
    return _calendar_ok_from_days(_daynum(ts), offset)


def compute_asset_features(daily: pd.DataFrame) -> tuple[pd.DataFrame, dict[tuple[int, int], np.ndarray]]:
    """Return per-day feature frame plus event-time arrays keyed by (offset, metric_id)."""
    g = daily.sort_values("ts")
    n = len(g)
    ts = pd.to_datetime(g["ts"], utc=True)
    days = _daynum(ts)
    high = g["high"].to_numpy(dtype=float)
    low = g["low"].to_numpy(dtype=float)
    close = g["close"].to_numpy(dtype=float)
    opn = g["open"].to_numpy(dtype=float)
    qvol = g["quote_volume"].to_numpy(dtype=float)
    breadth = g["market_breadth_above_ma30"].to_numpy(dtype=float)
    btc_above = g["btc_above_ma30"].to_numpy(dtype=float)
    logret = np.full(n, np.nan)
    pos = (close[1:] > 0) & (close[:-1] > 0)
    logret[1:][pos] = np.log(close[1:][pos] / close[:-1][pos])
    abs_logret = np.abs(logret)
    abs_simple = np.full(n, np.nan)
    abs_simple[1:] = np.abs(close[1:] / close[:-1] - 1.0)
    close_absdiff = np.full(n, np.nan)
    close_absdiff[1:] = np.abs(close[1:] - close[:-1])
    day_range = high - low

    feat = pd.DataFrame({
        "asset": g["asset"].to_numpy(),
        "ts": ts,
        "open": opn,
        "high": high,
        "low": low,
        "close": close,
        "quote_volume": qvol,
        "market_breadth_above_ma30": breadth,
        "btc_above_ma30": btc_above,
        "t0_day_range": day_range,
        "t0_abs_logret": abs_logret,
        "t0_abs_simple": abs_simple,
    })

    for h in HORIZONS:
        ok = _calendar_ok_from_days(days, h)
        fut_max_high = _window_stat(high, 1, h, "max")
        fut_min_low = _window_stat(low, 1, h, "min")
        fut_last_close = _window_stat(close, 1, h, "last")
        fut_first_close = _window_stat(close, 1, h, "first")
        path_sum = _window_stat(close_absdiff, 1, h, "sum")
        feat[f"ok_{h}d"] = ok
        feat[f"fut_max_high_{h}d"] = np.where(ok, fut_max_high, np.nan)
        feat[f"fut_min_low_{h}d"] = np.where(ok, fut_min_low, np.nan)
        feat[f"fut_close_{h}d"] = np.where(ok, fut_last_close, np.nan)
        feat[f"fut_first_close_{h}d"] = np.where(ok, fut_first_close, np.nan)
        feat[f"path_sum_{h}d"] = np.where(ok, path_sum, np.nan)
        if h in VOL_HORIZONS:
            sq = np.nan_to_num(logret ** 2, nan=0.0)
            fut_rv = np.sqrt(np.maximum(_window_stat(sq, 1, h, "sum"), 0.0))
            pre_ok = _calendar_ok_from_days(days, -h)
            pre_rv = np.sqrt(np.maximum(_window_stat(sq, -(h - 1), h, "sum"), 0.0))
            feat[f"future_rv_{h}d"] = np.where(ok, fut_rv, np.nan)
            feat[f"pre_rv_{h}d"] = np.where(pre_ok, pre_rv, np.nan)
        pre_len = h
        pre_off = -(h - 1) if h > 0 else 0
        pre_ok_range = _calendar_ok_from_days(days, -(h - 1)) if h > 1 else np.ones(n, dtype=bool)
        if h >= 1:
            pre_max = _window_stat(high, pre_off, pre_len, "max")
            pre_min = _window_stat(low, pre_off, pre_len, "min")
            feat[f"pre_max_high_{h}d"] = np.where(pre_ok_range, pre_max, np.nan)
            feat[f"pre_min_low_{h}d"] = np.where(pre_ok_range, pre_min, np.nan)

    # T-3..T0 is 4 days (offset -3, length 4)
    pre3_ok = _calendar_ok_from_days(days, -3)
    feat["pre_tminus3_max"] = np.where(pre3_ok, _window_stat(high, -3, 4, "max"), np.nan)
    feat["pre_tminus3_min"] = np.where(pre3_ok, _window_stat(low, -3, 4, "min"), np.nan)

    et: dict[tuple[int, int], np.ndarray] = {}
    for k in range(-EVENT_TIME_WINDOW, EVENT_TIME_WINDOW + 1):
        ok = _calendar_ok_from_days(days, k)
        j = np.arange(n) + k
        valid = (j >= 0) & (j < n) & ok
        rng = np.full(n, np.nan)
        alr = np.full(n, np.nan)
        asr = np.full(n, np.nan)
        qv = np.full(n, np.nan)
        rng[valid] = day_range[j[valid]]
        alr[valid] = abs_logret[j[valid]]
        asr[valid] = abs_simple[j[valid]]
        qv[valid] = qvol[j[valid]]
        et[(k, 0)] = rng
        et[(k, 1)] = alr
        et[(k, 2)] = asr
        et[(k, 3)] = qv
    return feat, et


def _accumulate_event_time(
    dates: np.ndarray,
    official: np.ndarray,
    placebo: np.ndarray,
    atr: np.ndarray,
    pos: np.ndarray,
    et: dict[tuple[int, int], np.ndarray],
    acc: dict[tuple[Any, int, int], np.ndarray],
) -> None:
    n_days = len(next(iter(et.values())))
    for k in range(-EVENT_TIME_WINDOW, EVENT_TIME_WINDOW + 1):
        # et[(k, *)] is already indexed at T0; do not add k again.
        valid = (pos >= 0) & (pos < n_days)
        rng = np.full(len(pos), np.nan)
        alr = np.full(len(pos), np.nan)
        asr = np.full(len(pos), np.nan)
        qv = np.full(len(pos), np.nan)
        rng[valid] = et[(k, 0)][pos[valid]]
        alr[valid] = et[(k, 1)][pos[valid]]
        asr[valid] = et[(k, 2)][pos[valid]]
        qv[valid] = et[(k, 3)][pos[valid]]
        atr_ok = valid & np.isfinite(atr) & (atr > 0) & np.isfinite(rng)
        groups = np.where(official, 1, np.where(placebo, 0, -1))
        keep = atr_ok & (groups >= 0)
        if not keep.any():
            continue
        range_atr = rng[keep] / atr[keep]
        tmp = pd.DataFrame({
            "date": pd.to_datetime(dates[keep], utc=True).normalize(),
            "grp": groups[keep],
            "range_atr": range_atr,
            "abs_logret": alr[keep],
            "abs_simple": asr[keep],
            "quote_volume": qv[keep],
        })
        g = tmp.groupby(["date", "grp"], sort=False)
        for (date, grp), sub in g:
            key = (_utc_normalize(date), int(k), int(grp))
            bucket = acc[key]
            bucket[0] += float(len(sub))
            bucket[1] += float(np.nansum(sub["range_atr"].to_numpy(dtype=float)))
            bucket[2] += float(np.nansum(sub["abs_logret"].to_numpy(dtype=float)))
            bucket[3] += float(np.nansum(sub["abs_simple"].to_numpy(dtype=float)))
            bucket[4] += float(np.nansum(sub["quote_volume"].to_numpy(dtype=float)))


def attach_outcomes(days: pd.DataFrame, daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    feat_frames = []
    et_acc: dict[tuple[Any, int, int], np.ndarray] = defaultdict(lambda: np.zeros(5, dtype=float))
    assets = sorted(days["asset"].unique())
    daily_assets = set(daily["asset"].unique())
    missing_assets = [a for a in assets if a not in daily_assets]
    days = days.sort_values(["asset", "ts"]).reset_index(drop=True)
    for i, asset in enumerate(assets, start=1):
        if i == 1 or i % 50 == 0 or i == len(assets):
            print(f"outcomes asset {i}/{len(assets)} {asset}", flush=True)
        dsub = daily.loc[daily["asset"].eq(asset)]
        if dsub.empty:
            continue
        feat, et = compute_asset_features(dsub)
        ev = days.loc[days["asset"].eq(asset)].copy()
        merged = ev[["asset", "ts"]].merge(feat, on=["asset", "ts"], how="left")
        feat_frames.append(merged)
        feat_ns = pd.to_datetime(feat["ts"], utc=True).astype("int64").to_numpy()
        ev_ns = pd.to_datetime(ev["ts"], utc=True).astype("int64").to_numpy()
        pos = np.searchsorted(feat_ns, ev_ns)
        pos = np.clip(pos, 0, max(len(feat_ns) - 1, 0))
        match = (len(feat_ns) > 0) & (feat_ns[pos] == ev_ns)
        pos = np.where(match, pos, -1)
        _accumulate_event_time(
            pd.to_datetime(ev["date"], utc=True).to_numpy(),
            ev["official_real"].to_numpy(dtype=bool),
            (~ev["is_cross"]).to_numpy(dtype=bool),
            ev["atr_anchor"].to_numpy(dtype=float),
            pos.astype(int),
            et,
            et_acc,
        )

    print("concat features", flush=True)
    feat_all = pd.concat(feat_frames, ignore_index=True) if feat_frames else pd.DataFrame()
    print(f"concat rows={len(feat_all)}", flush=True)
    out = days.merge(feat_all, on=["asset", "ts"], how="left", suffixes=("", "_feat"))
    atr = out["atr_anchor"].to_numpy(dtype=float)
    ref = out["entry_ref"].to_numpy(dtype=float)
    t0_close = out["close"].to_numpy(dtype=float) if "close" in out.columns else np.full(len(out), np.nan)
    atr_ok = np.isfinite(atr) & (atr > 0) & np.isfinite(ref) & (ref > 0)

    for h in HORIZONS:
        max_h = out[f"fut_max_high_{h}d"].to_numpy(dtype=float)
        min_l = out[f"fut_min_low_{h}d"].to_numpy(dtype=float)
        last_c = out[f"fut_close_{h}d"].to_numpy(dtype=float)
        first_c = out[f"fut_first_close_{h}d"].to_numpy(dtype=float)
        path = out[f"path_sum_{h}d"].to_numpy(dtype=float)
        ok = out[f"ok_{h}d"].fillna(False).to_numpy(dtype=bool) & atr_ok
        mfe_up = (max_h - ref) / atr
        mfe_dn = (ref - min_l) / atr
        out[f"mfe_up_{h}d"] = np.where(ok, mfe_up, np.nan)
        out[f"mfe_down_{h}d"] = np.where(ok, mfe_dn, np.nan)
        out[f"max_abs_excursion_{h}d"] = np.where(ok, np.maximum(mfe_up, mfe_dn), np.nan)
        out[f"future_range_{h}d"] = np.where(ok, (max_h - min_l) / atr, np.nan)
        out[f"abs_terminal_{h}d"] = np.where(ok, np.abs(last_c - ref) / atr, np.nan)
        a = np.maximum(mfe_up, mfe_dn)
        b = np.minimum(mfe_up, mfe_dn)
        denom = a + b
        out[f"dominance_{h}d"] = np.where(ok & (denom > DOMINANCE_EPS), a / denom, np.nan)
        if h in EFF_HORIZONS:
            first_leg = np.abs(first_c - ref)
            path_from_entry = path - np.abs(first_c - t0_close) + first_leg
            out[f"path_efficiency_{h}d"] = np.where(
                ok & (path_from_entry > 0) & np.isfinite(path_from_entry),
                np.abs(last_c - ref) / path_from_entry,
                np.nan,
            )
        if h in VOL_HORIZONS:
            fut_rv = out[f"future_rv_{h}d"].to_numpy(dtype=float)
            pre_rv = out[f"pre_rv_{h}d"].to_numpy(dtype=float)
            out[f"vol_expansion_ratio_{h}d"] = np.where(ok & np.isfinite(pre_rv) & (pre_rv > 0), fut_rv / pre_rv, np.nan)
        pre_max = out[f"pre_max_high_{h}d"].to_numpy(dtype=float)
        pre_min = out[f"pre_min_low_{h}d"].to_numpy(dtype=float)
        out[f"pre_range_{h}d"] = np.where(atr_ok & np.isfinite(pre_max) & np.isfinite(pre_min), (pre_max - pre_min) / atr, np.nan)
        if h in VOL_HORIZONS:
            out[f"post_pre_range_ratio_{h}d"] = np.where(
                (out[f"pre_range_{h}d"] > 0) & np.isfinite(out[f"future_range_{h}d"]),
                out[f"future_range_{h}d"] / out[f"pre_range_{h}d"],
                np.nan,
            )
            out[f"post_pre_vol_ratio_{h}d"] = out[f"vol_expansion_ratio_{h}d"]

    out["pre_tminus3_to_t0_range"] = np.where(
        atr_ok & np.isfinite(out["pre_tminus3_max"]) & np.isfinite(out["pre_tminus3_min"]),
        (out["pre_tminus3_max"] - out["pre_tminus3_min"]) / atr,
        np.nan,
    )
    out["t0_day_range_atr"] = np.where(atr_ok, out["t0_day_range"] / atr, np.nan)
    out["market_state"] = [
        market_state(b, t)
        for b, t in zip(
            out["market_breadth_above_ma30"].to_numpy(dtype=float),
            out["btc_above_ma30"].to_numpy(dtype=float),
        )
    ]

    et_rows = []
    for (date, k, is_cross), bucket in et_acc.items():
        n = bucket[0]
        if n <= 0:
            continue
        et_rows.append({
            "date": _utc_normalize(date),
            "offset": int(k),
            "is_cross": bool(is_cross),
            "n": float(n),
            "mean_range_atr": bucket[1] / n,
            "mean_abs_logret": bucket[2] / n,
            "mean_abs_simple": bucket[3] / n,
            "mean_quote_volume": bucket[4] / n,
        })
    et_df = pd.DataFrame(et_rows)
    audit = {
        "missing_daily_assets": missing_assets[:20],
        "n_missing_daily_assets": len(missing_assets),
        "outcome_rows": int(len(out)),
        "event_time_rows": int(len(et_df)),
        "hype_rows": int((out["asset"] == HYPE_ASSET).sum()),
        "hyper_rows": int(out["hyper"].sum()),
        "entry_ref_vs_future_defined": int(out["ok_5d"].fillna(False).sum()) if "ok_5d" in out else 0,
    }
    return out, et_df, audit


def _metric_col(metric: str, horizon: int) -> str:
    return f"{metric}_{horizon}d"


def date_matched_stats(frame: pd.DataFrame, col: str) -> pd.DataFrame:
    part = frame.loc[frame[col].notna(), ["date", "official_real", "is_cross", col]].copy()
    if part.empty:
        return pd.DataFrame(columns=[
            "date", "n_cross", "n_non", "cross_mean", "cross_median", "non_mean", "non_median",
            "cross_sum", "cross_sq_sum", "delta_mean", "delta_median",
        ])
    cross = part.loc[part["official_real"]]
    non = part.loc[~part["is_cross"]]
    cg = cross.groupby("date")[col].agg(cross_mean="mean", cross_median="median", n_cross="size", cross_sum="sum")
    ng = non.groupby("date")[col].agg(non_mean="mean", non_median="median", n_non="size")
    out = cg.join(ng, how="left").reset_index()
    out["date"] = pd.to_datetime(out["date"], utc=True)
    out["n_non"] = out["n_non"].fillna(0).astype(int)
    out["n_cross"] = out["n_cross"].astype(int)
    out["delta_mean"] = out["cross_mean"] - out["non_mean"]
    out["delta_median"] = out["cross_median"] - out["non_median"]
    out["cross_sq_sum"] = 0.0
    return out


def summarize_date_stats(stats: pd.DataFrame) -> dict[str, float]:
    if stats.empty:
        return {
            "n_cross": 0,
            "n_dates": 0,
            "cross_mean": float("nan"),
            "cross_median": float("nan"),
            "non_mean": float("nan"),
            "non_median": float("nan"),
            "delta_mean": float("nan"),
            "delta_median": float("nan"),
            "paired_effect_size": float("nan"),
            "relative_mean": float("nan"),
            "relative_median": float("nan"),
        }
    usable = stats.loc[(stats["n_cross"] > 0) & (stats["n_non"] > 0)].copy()
    if usable.empty:
        usable = stats.loc[stats["n_cross"] > 0].copy()
    w = usable["n_cross"].astype(float).to_numpy()
    out = {
        "n_cross": int(np.nansum(w)),
        "n_dates": int((usable["n_cross"] > 0).sum()),
        "cross_mean": weighted_mean(usable["cross_mean"].to_numpy(dtype=float), w),
        "cross_median": weighted_mean(usable["cross_median"].to_numpy(dtype=float), w),
        "non_mean": weighted_mean(usable["non_mean"].to_numpy(dtype=float), w),
        "non_median": weighted_mean(usable["non_median"].to_numpy(dtype=float), w),
        "delta_mean": weighted_mean(usable["delta_mean"].to_numpy(dtype=float), w),
        "delta_median": weighted_mean(usable["delta_median"].to_numpy(dtype=float), w),
    }
    deltas = usable.loc[usable["delta_mean"].notna(), "delta_mean"].to_numpy(dtype=float)
    out["paired_effect_size"] = float(np.mean(deltas) / np.std(deltas, ddof=1)) if len(deltas) > 1 and np.std(deltas, ddof=1) > 0 else float("nan")
    if out["non_mean"] and np.isfinite(out["non_mean"]) and out["non_mean"] != 0:
        out["relative_mean"] = out["delta_mean"] / out["non_mean"]
    else:
        out["relative_mean"] = float("nan")
    if out["non_median"] and np.isfinite(out["non_median"]) and out["non_median"] != 0:
        out["relative_median"] = out["delta_median"] / out["non_median"]
    else:
        out["relative_median"] = float("nan")
    return out


def vol_matched_delta(frame: pd.DataFrame, col: str) -> dict[str, float]:
    cross = frame.loc[frame["official_real"] & frame[col].notna()]
    non = frame.loc[~frame["is_cross"] & frame[col].notna()]
    if cross.empty:
        return {"delta_mean": float("nan"), "n_cross": 0, "coverage": 0.0}
    parts = []
    weights = []
    covered = 0
    for (d, bucket), cg in cross.groupby(["date", "volatility_state_p0r"]):
        pool = non.loc[(non["date"] == d) & (non["volatility_state_p0r"] == bucket), col]
        if pool.empty:
            continue
        parts.append(finite_mean(cg[col].to_numpy(dtype=float)) - finite_mean(pool.to_numpy(dtype=float)))
        weights.append(len(cg))
        covered += len(cg)
    w = np.asarray(weights, dtype=float)
    return {
        "delta_mean": weighted_mean(np.asarray(parts, dtype=float), w) if len(parts) else float("nan"),
        "n_cross": int(covered),
        "coverage": float(covered / max(len(cross), 1)),
    }


def liq_vol_matched_delta(frame: pd.DataFrame, col: str) -> dict[str, float]:
    cross = frame.loc[frame["official_real"] & frame[col].notna()]
    non = frame.loc[~frame["is_cross"] & frame[col].notna()]
    if cross.empty:
        return {"delta_mean": float("nan"), "n_cross": 0, "coverage": 0.0}
    parts = []
    weights = []
    covered = 0
    for (d, vb, lb), cg in cross.groupby(["date", "volatility_state_p0r", "liq_bucket"]):
        pool = non.loc[
            (non["date"] == d) & (non["volatility_state_p0r"] == vb) & (non["liq_bucket"] == lb),
            col,
        ]
        if pool.empty:
            continue
        parts.append(finite_mean(cg[col].to_numpy(dtype=float)) - finite_mean(pool.to_numpy(dtype=float)))
        weights.append(len(cg))
        covered += len(cg)
    w = np.asarray(weights, dtype=float)
    return {
        "delta_mean": weighted_mean(np.asarray(parts, dtype=float), w) if len(parts) else float("nan"),
        "n_cross": int(covered),
        "coverage": float(covered / max(len(cross), 1)),
    }


def same_asset_exact(frame: pd.DataFrame, col: str) -> dict[str, float]:
    cross = frame.loc[frame["official_real"] & frame[col].notna()]
    non = frame.loc[~frame["is_cross"] & frame[col].notna()]
    asset_mean = non.groupby("asset")[col].mean()
    mapped = cross["asset"].map(asset_mean)
    mask = cross[col].notna() & mapped.notna()
    if not mask.any():
        return {"cross_mean": float("nan"), "placebo_mean": float("nan"), "delta_mean": float("nan"), "n": 0}
    c = cross.loc[mask, col].to_numpy(dtype=float)
    p = mapped.loc[mask].to_numpy(dtype=float)
    return {
        "cross_mean": float(np.mean(c)),
        "placebo_mean": float(np.mean(p)),
        "delta_mean": float(np.mean(c - p)),
        "n": int(mask.sum()),
    }


def pooled_percentiles(frame: pd.DataFrame, col: str) -> dict[str, float]:
    cross = frame.loc[frame["official_real"], col].to_numpy(dtype=float)
    non = frame.loc[~frame["is_cross"] & frame[col].notna()].copy()
    n_cross = frame.loc[frame["official_real"]].groupby("date").size()
    n_non = non.groupby("date").size()
    w = non["date"].map(lambda d: (n_cross.get(d, 0) / n_non.get(d, np.nan)) if d in n_non.index else np.nan)
    out = {}
    for name, q in [("p75", 0.75), ("p90", 0.90), ("p95", 0.95), ("p99", 0.99)]:
        out[f"cross_{name}"] = finite_quantile(cross, q)
        out[f"non_{name}"] = weighted_quantile(non[col].to_numpy(dtype=float), w.to_numpy(dtype=float), q)
    out["cross_mean"] = finite_mean(cross)
    out["cross_median"] = finite_median(cross)
    return out


def run_block_bootstrap(stats_map: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, Any]]:
    primary = stats_map["max_abs_excursion"]
    work_index = primary.loc[primary["n_cross"] > 0, ["date"]].copy()
    work_index["date"] = pd.to_datetime(work_index["date"], utc=True)
    if work_index.empty:
        raise RuntimeError("no official Cross dates available for bootstrap")
    work_index["block"] = calendar_block_id(work_index["date"], origin=work_index["date"].min())
    blocks = work_index["block"].drop_duplicates().to_numpy()
    by_block = {int(b): work_index.loc[work_index["block"].eq(b), "date"].to_numpy() for b in blocks}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    records = []
    for i in range(BOOTSTRAP_SAMPLES):
        sampled_blocks = rng.choice(blocks, size=len(blocks), replace=True)
        dates = np.concatenate([by_block[int(b)] for b in sampled_blocks])
        rec: dict[str, Any] = {"replicate": i}
        for metric, stats in stats_map.items():
            sample = stats.set_index("date").reindex(dates).reset_index()
            s = summarize_date_stats(sample)
            rec[f"{metric}_delta_mean"] = s["delta_mean"]
            rec[f"{metric}_delta_median"] = s["delta_median"]
            rec[f"{metric}_cross_mean"] = s["cross_mean"]
            rec[f"{metric}_non_mean"] = s["non_mean"]
            rec[f"{metric}_cross_median"] = s["cross_median"]
            rec[f"{metric}_non_median"] = s["non_median"]
        records.append(rec)
    boot = pd.DataFrame(records)

    def summarize(col: str) -> dict[str, float]:
        x = boot[col].to_numpy(dtype=float)
        finite = x[np.isfinite(x)]
        return {
            "bootstrap_mean": float(np.mean(finite)) if len(finite) else float("nan"),
            "p2.5": float(np.percentile(finite, 2.5)) if len(finite) else float("nan"),
            "p97.5": float(np.percentile(finite, 97.5)) if len(finite) else float("nan"),
            "effective_replicates": int(len(finite)),
            "non_finite_replicates": int(len(x) - len(finite)),
            "p_two_sided": bootstrap_two_sided_p(finite),
        }

    summary = {
        "n": BOOTSTRAP_SAMPLES,
        "seed": BOOTSTRAP_SEED,
        "block_days": BOOTSTRAP_BLOCK_DAYS,
        "n_blocks": int(len(blocks)),
        "metrics": {},
    }
    for metric in stats_map:
        summary["metrics"][metric] = {
            "delta_mean": summarize(f"{metric}_delta_mean"),
            "delta_median": summarize(f"{metric}_delta_median"),
        }
    return boot, summary


def year_breakdown(frame: pd.DataFrame, col: str) -> pd.DataFrame:
    rows = []
    for period, mask in [
        ("full", pd.Series(True, index=frame.index)),
        ("pre_2022", frame["event_year"] < 2022),
        ("pre_2025", frame["ts"] < CUTOFF),
        ("2022", frame["event_year"].eq(2022)),
        ("2023", frame["event_year"].eq(2023)),
        ("2024", frame["event_year"].eq(2024)),
        ("2025", frame["event_year"].eq(2025)),
        ("2026", frame["event_year"].eq(2026)),
    ]:
        sub = frame.loc[mask]
        stats = date_matched_stats(sub, col)
        s = summarize_date_stats(stats) if len(stats) else {}
        rows.append({"period": period, "metric": col, **s})
    return pd.DataFrame(rows)


def choose_verdict(
    parity: dict[str, Any],
    primary: dict[str, dict[str, Any]],
    boot: dict[str, Any],
    year_exc: pd.DataFrame,
    vol_matched: dict[str, float],
    lagging: dict[str, Any],
) -> str:
    if parity.get("reproduction_failure"):
        return "DATA_OR_REPRODUCTION_FAILURE"
    n_pos = 0
    n_neg = 0
    material_hits = 0
    for metric in BH_METRICS:
        ci = boot["metrics"][metric]["delta_mean"]
        lo, hi = ci["p2.5"], ci["p97.5"]
        point = primary[metric]["delta_mean"]
        if np.isfinite(lo) and np.isfinite(hi):
            if lo > 0:
                n_pos += 1
            elif hi < 0:
                n_neg += 1
        if metric == "max_abs_excursion":
            med = primary[metric]["delta_median"]
            rel = primary[metric].get("relative_median", float("nan"))
            if (np.isfinite(med) and abs(med) >= MATERIAL_ABS_ATR) and (np.isfinite(rel) and abs(rel) >= MATERIAL_REL):
                material_hits += 1
        elif np.isfinite(primary[metric].get("relative_mean", float("nan"))) and abs(primary[metric]["relative_mean"]) >= MATERIAL_REL:
            if np.isfinite(lo) and lo > 0:
                material_hits += 1
    years = year_exc.loc[year_exc["period"].isin(["2022", "2023", "2024", "2025", "2026"])]
    year_pos = int((years["delta_mean"] > 0).sum()) if len(years) else 0
    year_ok = year_pos >= 3
    future_supported = n_pos >= 3
    future_absent = n_pos <= 1
    pre_up = bool(lagging.get("pre_elevated"))
    post_flat = bool(lagging.get("post_flat"))
    vol_ok = bool(vol_matched.get("still_positive"))
    if future_absent and pre_up and post_flat:
        return "CROSS_IS_LAGGING_EXPANSION_MARKER"
    if not future_supported:
        return "NO_EXPANSION_EDGE"
    if future_supported and vol_ok and year_ok and material_hits >= 2 and n_pos >= 4 and not post_flat:
        return "EXPANSION_EVENT_SUPPORTED"
    return "WEAK_EXPANSION_MARKER"


def event_time_curves(et: pd.DataFrame) -> pd.DataFrame:
    if et.empty:
        return et
    et = et.copy()
    et["date"] = pd.to_datetime(et["date"], utc=True)
    n_cross_date = et.loc[et["is_cross"]].groupby("date")["n"].max()
    rows = []
    for offset, grp in et.groupby("offset"):
        cross = grp.loc[grp["is_cross"]].set_index("date")
        non = grp.loc[~grp["is_cross"]].set_index("date")
        dates = sorted(set(cross.index) & set(n_cross_date.index))
        w = n_cross_date.reindex(dates).astype(float).to_numpy()
        def wmean(frame: pd.DataFrame, col: str) -> float:
            if frame.empty:
                return float("nan")
            aligned = frame.reindex(dates)
            return weighted_mean(aligned[col].to_numpy(dtype=float), w)
        rows.append({
            "offset": int(offset),
            "cross_range": wmean(cross, "mean_range_atr"),
            "non_range": wmean(non, "mean_range_atr"),
            "cross_abs_logret": wmean(cross, "mean_abs_logret"),
            "non_abs_logret": wmean(non, "mean_abs_logret"),
            "cross_abs_simple": wmean(cross, "mean_abs_simple"),
            "non_abs_simple": wmean(non, "mean_abs_simple"),
            "cross_quote_volume": wmean(cross, "mean_quote_volume"),
            "non_quote_volume": wmean(non, "mean_quote_volume"),
            "n_dates": int(len(dates)),
        })
    curves = pd.DataFrame(rows).sort_values("offset")
    curves["delta_range"] = curves["cross_range"] - curves["non_range"]
    curves["delta_abs_logret"] = curves["cross_abs_logret"] - curves["non_abs_logret"]
    return curves


def same_asset_mc(frame: pd.DataFrame, col: str) -> dict[str, float]:
    cross = frame.loc[frame["official_real"] & frame[col].notna()]
    non = frame.loc[~frame["is_cross"] & frame[col].notna()]
    pools = {a: g[col].to_numpy(dtype=float) for a, g in non.groupby("asset")}
    counts = cross.groupby("asset").size().to_dict()
    exact = same_asset_exact(frame, col)
    means = []
    for seed in range(MC_SEED_START, MC_SEED_END + 1):
        rng = np.random.default_rng(seed)
        total = 0.0
        n = 0
        for asset, n_evt in counts.items():
            pool = pools.get(asset)
            if pool is None or len(pool) == 0:
                continue
            draw = rng.choice(pool, size=int(n_evt), replace=True)
            total += float(np.sum(draw))
            n += int(n_evt)
        means.append(total / n if n else float("nan"))
    mc_mean = float(np.nanmean(means)) if means else float("nan")
    return {
        "exact_placebo": exact["placebo_mean"],
        "mc_mean": mc_mean,
        "abs_diff": abs(mc_mean - exact["placebo_mean"]) if np.isfinite(mc_mean) and np.isfinite(exact["placebo_mean"]) else float("nan"),
        "n": MC_N,
    }


def svg_escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def y_limits(values: list[float], *, include_zero: bool, nonnegative: bool) -> tuple[float, float]:
    finite = [v for v in values if np.isfinite(v)]
    if not finite:
        return (0.0, 1.0)
    ymin = min(finite)
    ymax = max(finite)
    pad = max(0.05 * (ymax - ymin if ymax > ymin else 1.0), 1e-6)
    if nonnegative:
        return 0.0, max(ymax + pad, 1e-6)
    lo = ymin - pad
    hi = ymax + pad
    if include_zero:
        lo = min(lo, 0.0)
        hi = max(hi, 0.0)
    return lo, hi


def write_svg(path: Path, width: int, height: int, body: str, title: str) -> None:
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="{width / 2:.1f}" y="28" text-anchor="middle" font-size="16" font-family="sans-serif">{svg_escape(title)}</text>
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


def svg_hist(series: list[tuple[str, np.ndarray, str]], *, xlabel: str, title: str, path: Path, nonnegative: bool) -> None:
    width, height = 920, 540
    left, right, top, bottom = 70, 880, 50, 430
    arrays = [arr[np.isfinite(arr)] for _, arr, _ in series]
    if not any(len(a) for a in arrays):
        write_svg(path, width, height, "", title)
        return
    all_x = np.concatenate([a for a in arrays if len(a)])
    lo = float(np.quantile(all_x, 0.01))
    hi = float(np.quantile(all_x, 0.99))
    if nonnegative:
        lo = min(0.0, lo) if lo < 0 else 0.0
    if hi <= lo:
        hi = lo + 1.0
    bins = np.linspace(lo, hi, 36)
    dens = []
    for arr in arrays:
        hist, _ = np.histogram(arr, bins=bins, density=True)
        dens.append(hist)
    ymax = max(float(np.max(d)) if len(d) else 0.0 for d in dens)
    ymin = 0.0
    parts = [
        f'<text x="18" y="240" transform="rotate(-90 18 240)" font-size="12" font-family="sans-serif">density</text>',
        f'<text x="{(left + right) / 2:.1f}" y="510" text-anchor="middle" font-size="12" font-family="sans-serif">{svg_escape(xlabel)}</text>',
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#333" />',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#333" />',
    ]
    for (_, _, color), hist in zip(series, dens):
        for i, c in enumerate(hist):
            x0, _ = chart_coords(left, right, top, bottom, bins[0], bins[-1], ymin, ymax, bins[i], 0)
            x1, _ = chart_coords(left, right, top, bottom, bins[0], bins[-1], ymin, ymax, bins[i + 1], 0)
            _, y = chart_coords(left, right, top, bottom, bins[0], bins[-1], ymin, ymax, bins[i], float(c))
            parts.append(
                f'<rect x="{x0:.1f}" y="{y:.1f}" width="{max(x1 - x0, 1):.1f}" height="{bottom - y:.1f}" fill="{color}" fill-opacity="0.45" />'
            )
    for j, (name, _, color) in enumerate(series):
        parts.append(f'<rect x="{70 + j * 280}" y="500" width="12" height="12" fill="{color}" />')
        parts.append(f'<text x="{88 + j * 280}" y="511" font-size="12" font-family="sans-serif">{svg_escape(name)}</text>')
    write_svg(path, width, height, "\n".join(parts), title)


def svg_lines(xs: list[float], series: list[tuple[str, list[float], str]], *, xlabel: str, ylabel: str, title: str, path: Path, nonnegative: bool, vline: float | None = None) -> None:
    width, height = 920, 540
    left, right, top, bottom = 70, 880, 50, 430
    all_vals = [v for _, vals, _ in series for v in vals if np.isfinite(v)]
    ymin, ymax = y_limits(all_vals, include_zero=True, nonnegative=nonnegative)
    xmin, xmax = min(xs), max(xs)
    parts = [
        f'<text x="18" y="240" transform="rotate(-90 18 240)" font-size="12" font-family="sans-serif">{svg_escape(ylabel)}</text>',
        f'<text x="{(left + right) / 2:.1f}" y="510" text-anchor="middle" font-size="12" font-family="sans-serif">{svg_escape(xlabel)}</text>',
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#333" />',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#333" />',
    ]
    if ymin < 0 < ymax:
        _, z = chart_coords(left, right, top, bottom, xmin, xmax, ymin, ymax, xmin, 0)
        parts.append(f'<line x1="{left}" y1="{z:.1f}" x2="{right}" y2="{z:.1f}" stroke="#444" />')
    if vline is not None:
        px, _ = chart_coords(left, right, top, bottom, xmin, xmax, ymin, ymax, vline, ymin)
        parts.append(f'<line x1="{px:.1f}" y1="{top}" x2="{px:.1f}" y2="{bottom}" stroke="#444" />')
    for name, vals, color in series:
        pts = []
        for x, yv in zip(xs, vals):
            if not np.isfinite(yv):
                continue
            px, py = chart_coords(left, right, top, bottom, xmin, xmax, ymin, ymax, x, yv)
            pts.append(f"{px:.1f},{py:.1f}")
        if pts:
            parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{" ".join(pts)}" />')
    step = max(1, len(xs) // 10)
    for i, x in enumerate(xs):
        if i % step != 0 and i not in (0, len(xs) - 1):
            continue
        px, _ = chart_coords(left, right, top, bottom, xmin, xmax, ymin, ymax, x, ymin)
        parts.append(f'<text x="{px:.1f}" y="{bottom + 20}" text-anchor="middle" font-size="11" font-family="sans-serif">{x:g}</text>')
    for j, (name, _, color) in enumerate(series):
        parts.append(f'<rect x="{70 + j * 280}" y="500" width="12" height="12" fill="{color}" />')
        parts.append(f'<text x="{88 + j * 280}" y="511" font-size="12" font-family="sans-serif">{svg_escape(name)}</text>')
    write_svg(path, width, height, "\n".join(parts), title)


def svg_grouped_bars(categories: list[str], series: list[tuple[str, list[float], str]], *, ylabel: str, title: str, path: Path, nonnegative: bool, hline: float | None = None) -> None:
    width, height = 920, 540
    left, right, top, bottom = 70, 880, 50, 430
    all_vals = [v for _, vals, _ in series for v in vals if np.isfinite(v)]
    if hline is not None:
        all_vals.append(hline)
    ymin, ymax = y_limits(all_vals, include_zero=True, nonnegative=nonnegative)
    n = max(len(categories), 1)
    group_w = (right - left) / n
    bar_w = group_w / (len(series) + 1.5)
    parts = [f'<text x="18" y="240" transform="rotate(-90 18 240)" font-size="12" font-family="sans-serif">{svg_escape(ylabel)}</text>']
    parts.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#333" />')
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#333" />')
    if ymin < 0 < ymax:
        _, z = chart_coords(left, right, top, bottom, 0, 1, ymin, ymax, 0, 0)
        parts.append(f'<line x1="{left}" y1="{z:.1f}" x2="{right}" y2="{z:.1f}" stroke="#444" />')
    if hline is not None:
        _, hy = chart_coords(left, right, top, bottom, 0, 1, ymin, ymax, 0, hline)
        parts.append(f'<line x1="{left}" y1="{hy:.1f}" x2="{right}" y2="{hy:.1f}" stroke="#444" stroke-dasharray="6 4" />')
    for i, cat in enumerate(categories):
        gx = left + i * group_w
        for j, (_, vals, color) in enumerate(series):
            value = vals[i] if i < len(vals) else float("nan")
            if not np.isfinite(value):
                continue
            x0 = gx + (j + 0.5) * bar_w
            _, y = chart_coords(left, right, top, bottom, 0, 1, ymin, ymax, 0, value)
            base = chart_coords(left, right, top, bottom, 0, 1, ymin, ymax, 0, 0)[1]
            y0 = min(y, base)
            parts.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{bar_w:.1f}" height="{abs(base - y):.1f}" fill="{color}" />')
        parts.append(f'<text x="{gx + group_w / 2:.1f}" y="{bottom + 22}" text-anchor="middle" font-size="12" font-family="sans-serif">{svg_escape(cat)}</text>')
    for j, (name, _, color) in enumerate(series):
        parts.append(f'<rect x="{70 + j * 180}" y="500" width="12" height="12" fill="{color}" />')
        parts.append(f'<text x="{88 + j * 180}" y="511" font-size="12" font-family="sans-serif">{svg_escape(name)}</text>')
    write_svg(path, width, height, "\n".join(parts), title)


def svg_bars(items: list[tuple[str, float, str]], *, ylabel: str, title: str, path: Path, nonnegative: bool) -> None:
    width, height = 860, 520
    left, right, top, bottom = 70, 820, 50, 430
    vals = [v for _, v, _ in items]
    ymin, ymax = y_limits(vals, include_zero=True, nonnegative=nonnegative)
    n = max(len(items), 1)
    gap = 20
    bar_w = max(20.0, (right - left - gap * (n + 1)) / n)
    parts = [f'<text x="18" y="240" transform="rotate(-90 18 240)" font-size="12" font-family="sans-serif">{svg_escape(ylabel)}</text>']
    parts.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#333" />')
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#333" />')
    _, z = chart_coords(left, right, top, bottom, 0, 1, ymin, ymax, 0, 0)
    if ymin < 0 < ymax:
        parts.append(f'<line x1="{left}" y1="{z:.1f}" x2="{right}" y2="{z:.1f}" stroke="#444" />')
    for i, (label, value, color) in enumerate(items):
        x0 = left + gap + i * (bar_w + gap)
        _, y = chart_coords(left, right, top, bottom, 0, 1, ymin, ymax, 0, value)
        y0 = min(y, z)
        parts.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{bar_w:.1f}" height="{abs(z - y):.1f}" fill="{color}" />')
        parts.append(f'<text x="{x0 + bar_w / 2:.1f}" y="{bottom + 24}" text-anchor="middle" font-size="11" font-family="sans-serif">{svg_escape(label)}</text>')
    write_svg(path, width, height, "\n".join(parts), title)


def draw_charts(frame: pd.DataFrame, curves: pd.DataFrame, year_df: pd.DataFrame, extra: dict[str, Any]) -> None:
    h = PRIMARY_HORIZON
    cross = frame.loc[frame["official_real"]]
    non = frame.loc[~frame["is_cross"]]

    def hist_pair(path: Path, col: str, title: str) -> None:
        c = cross[col].to_numpy(dtype=float)
        n = non[col].to_numpy(dtype=float)
        finite = np.concatenate([c[np.isfinite(c)], n[np.isfinite(n)]]) if (np.isfinite(c).any() or np.isfinite(n).any()) else np.array([0.0])
        svg_hist(
            [("Cross", c, "#1f4e79"), ("Date-matched non-cross pool", n, "#b35c1e")],
            xlabel=col,
            title=title,
            path=path,
            nonnegative=bool(len(finite) and float(np.min(finite)) >= 0),
        )

    hist_pair(CHARTS["excursion"], f"max_abs_excursion_{h}d", "5D max abs excursion")
    hist_pair(CHARTS["range"], f"future_range_{h}d", "5D future range")
    hist_pair(CHARTS["vol"], f"vol_expansion_ratio_{h}d", "5D realized-vol expansion ratio")
    hist_pair(CHARTS["efficiency"], f"path_efficiency_{h}d", "5D path efficiency")
    hist_pair(CHARTS["terminal"], f"abs_terminal_{h}d", "5D absolute terminal move")

    xs = curves["offset"].astype(float).tolist() if not curves.empty else [-20.0, 0.0, 20.0]
    svg_lines(
        xs,
        [
            ("Cross", curves["cross_abs_logret"].astype(float).tolist() if not curves.empty else [0.0, 0.0, 0.0], "#1f4e79"),
            ("Date-matched non-cross", curves["non_abs_logret"].astype(float).tolist() if not curves.empty else [0.0, 0.0, 0.0], "#b35c1e"),
        ],
        xlabel="offset (days from T0)",
        ylabel="|log return|",
        title="Event-time |log return|",
        path=CHARTS["et_vol"],
        nonnegative=True,
        vline=0.0,
    )
    svg_lines(
        xs,
        [
            ("Cross", curves["cross_range"].astype(float).tolist() if not curves.empty else [0.0, 0.0, 0.0], "#1f4e79"),
            ("Date-matched non-cross", curves["non_range"].astype(float).tolist() if not curves.empty else [0.0, 0.0, 0.0], "#b35c1e"),
        ],
        xlabel="offset (days from T0)",
        ylabel="range / ATR14",
        title="Event-time ATR-normalized daily range",
        path=CHARTS["et_range"],
        nonnegative=True,
        vline=0.0,
    )
    svg_grouped_bars(
        ["range post/pre", "vol post/pre"],
        [
            ("Cross", [
                float(extra["post_pre_range"]["cross_mean"]),
                float(extra["post_pre_vol"]["cross_mean"]),
            ], "#1f4e79"),
            ("Non-cross", [
                float(extra["post_pre_range"]["non_mean"]),
                float(extra["post_pre_vol"]["non_mean"]),
            ], "#b35c1e"),
        ],
        ylabel="post/pre ratio",
        title="5D post/pre expansion ratio",
        path=CHARTS["prepost"],
        nonnegative=True,
        hline=1.0,
    )
    ysub = year_df.loc[year_df["period"].isin(["2022", "2023", "2024", "2025", "2026"])]
    svg_bars(
        [(str(p), float(v), "#1f4e79") for p, v in zip(ysub["period"], ysub["delta_mean"])],
        ylabel="Cross − date-matched non-cross",
        title="5D max abs excursion Δ mean by year",
        path=CHARTS["yearly"],
        nonnegative=False,
    )
    up = cross.loc[cross["cross_side"].eq("up"), f"max_abs_excursion_{h}d"]
    down = cross.loc[cross["cross_side"].eq("down"), f"max_abs_excursion_{h}d"]
    svg_bars(
        [
            ("up-cross", finite_mean(up.to_numpy(dtype=float)), "#2a9d8f"),
            ("down-cross", finite_mean(down.to_numpy(dtype=float)), "#e76f51"),
        ],
        ylabel="mean max abs excursion",
        title="5D max abs excursion by Cross direction (descriptive only)",
        path=CHARTS["updown"],
        nonnegative=True,
    )


def write_reports(summary: dict[str, Any], lock: dict[str, Any], config: dict[str, Any]) -> None:
    p = summary["primary_5d"]
    boot = summary["bootstrap"]["metrics"]
    mx = p["max_abs_excursion"]
    fr = p["future_range"]
    vr = p["vol_expansion_ratio"]
    pe = p["path_efficiency"]
    lines = [
        "# BIN-1D-MA7-CER P0 无方向价格扩张事件审计",
        "",
        f"5D median max excursion: Cross = {fmt(mx['cross_median'])}; Non-cross = {fmt(mx['non_median'])}; Difference = {fmt(mx['delta_median'])}; 95% CI = {fmt_ci(boot['max_abs_excursion']['delta_median']['p2.5'], boot['max_abs_excursion']['delta_median']['p97.5'])}",
        f"5D future range: Cross = {fmt(fr['cross_mean'])}; Non-cross = {fmt(fr['non_mean'])}; Difference = {fmt(fr['delta_mean'])}; 95% CI = {fmt_ci(boot['future_range']['delta_mean']['p2.5'], boot['future_range']['delta_mean']['p97.5'])}",
        f"5D realized-vol expansion ratio: Cross = {fmt(vr['cross_mean'])}; Non-cross = {fmt(vr['non_mean'])}; Difference = {fmt(vr['delta_mean'])}; 95% CI = {fmt_ci(boot['vol_expansion_ratio']['delta_mean']['p2.5'], boot['vol_expansion_ratio']['delta_mean']['p97.5'])}",
        f"5D path efficiency: Cross = {fmt(pe['cross_mean'])}; Non-cross = {fmt(pe['non_mean'])}; Difference = {fmt(pe['delta_mean'])}; 95% CI = {fmt_ci(boot['path_efficiency']['delta_mean']['p2.5'], boot['path_efficiency']['delta_mean']['p97.5'])}",
        "",
        summary["lagging_answer"],
        "",
        f"全局裁决：`{summary['verdict']}`",
    ]
    lines.append("")
    lines.append(f"- 状态：`{STATUS}`")
    lines.append(f"- `research_id`：`{RESEARCH_ID}`")
    lines.append(f"- 合同锁：`{LOCK_STATUS}`")
    lines.append(f"- data/event parity：`{summary['parity']['anchors_ok']}`")
    lines.append(f"- 官方 Cross N：{summary['parity']['official_n']}")
    lines.append(
        f"- 2025+ 未纳入官方样本的额外 probe：{summary['parity'].get('unofficial_2025_plus_probe_not_in_p5', 'NA')}（不进入主分析）"
    )
    tm = p["abs_terminal"]
    lines.append(
        f"- 5D abs terminal: Cross = {fmt(tm['cross_mean'])}; Non-cross = {fmt(tm['non_mean'])}; Difference = {fmt(tm['delta_mean'])}; 95% CI = {fmt_ci(boot['abs_terminal']['delta_mean']['p2.5'], boot['abs_terminal']['delta_mean']['p97.5'])}"
    )
    lines.append("")
    lines.append("## 主 5D outcome（相对 DATE_MATCHED_NON_CROSS）")
    lines.append("")
    lines.append("| Metric | Cross mean | Non-cross mean | Δ mean | Δ median | 95% CI (Δ mean) | BH q |")
    lines.append("| --- | ---: | ---: | ---: | ---: | --- | ---: |")
    for metric in BH_METRICS:
        item = p[metric]
        ci = boot[metric]["delta_mean"]
        q = summary["bh"][metric]["q"]
        lines.append(
            f"| {metric} | {fmt(item['cross_mean'])} | {fmt(item['non_mean'])} | {fmt(item['delta_mean'])} | {fmt(item['delta_median'])} | {fmt_ci(ci['p2.5'], ci['p97.5'])} | {fmt(q, 4)} |"
        )
    lines.append("")
    lines.append("## Pre vs post")
    lines.append("")
    lg = summary["lagging"]
    lines.append(f"- T-3→T0 range Δ mean = {fmt(lg['pre_delta'])}")
    lines.append(f"- T0 day range Δ mean = {fmt(lg['t0_delta'])}")
    lines.append(f"- T+1→T+5 range Δ mean = {fmt(lg['post_delta'])}")
    lines.append(f"- 5D post/pre range ratio Cross = {fmt(lg['cross_post_pre_range'])} vs non-cross {fmt(lg['non_post_pre_range'])}")
    lines.append(f"- 5D post/pre vol ratio Cross = {fmt(lg['cross_post_pre_vol'])} vs non-cross {fmt(lg['non_post_pre_vol'])}")
    lines.append("")
    lines.append("## Event-time")
    lines.append("")
    lines.append(summary["event_time_finding"])
    lines.append("")
    lines.append("## 年份")
    lines.append("")
    lines.append("| Period | N | Δ mean excursion | Δ mean range |")
    lines.append("| --- | ---: | ---: | ---: |")
    for row in summary["year_rows"]:
        lines.append(f"| {row['period']} | {row.get('n_cross', 'NA')} | {fmt(row.get('delta_mean'))} | {fmt(row.get('range_delta_mean'))} |")
    lines.append("")
    lines.append("## Up / down Cross（描述性）")
    lines.append("")
    ud = summary["up_down"]
    lines.append(f"- up-cross 5D max abs excursion mean = {fmt(ud['up_exc'])} (N={ud['up_n']})")
    lines.append(f"- down-cross 5D max abs excursion mean = {fmt(ud['down_exc'])} (N={ud['down_n']})")
    lines.append("不得解释为方向预测。")
    lines.append("")
    lines.append("## 其他 placebo")
    lines.append("")
    lines.append(f"- same-asset exact Δ mean excursion = {fmt(summary['placebo_b']['delta_mean'])}")
    lines.append(f"- vol-matched Δ mean excursion = {fmt(summary['placebo_c']['delta_mean'])} (coverage {fmt(summary['placebo_c']['coverage'])})")
    lines.append(f"- liq+vol matched Δ mean excursion = {fmt(summary['placebo_d']['delta_mean'])} (coverage {fmt(summary['placebo_d']['coverage'])})")
    lines.append("")
    lines.append("## Horizon 敏感性（次要，不得替代 5D）")
    lines.append("")
    lines.append("| Horizon | Δ mean excursion | Δ mean range | Δ mean vol ratio | Δ mean efficiency | Δ mean terminal |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for hz in ("1", "3", "5", "10", "20"):
        s = summary["sensitivity"].get(hz, {})
        lines.append(
            f"| {hz}D | {fmt(s.get('max_abs_excursion', {}).get('delta_mean'))} | {fmt(s.get('future_range', {}).get('delta_mean'))} | {fmt(s.get('vol_expansion_ratio', {}).get('delta_mean'))} | {fmt(s.get('path_efficiency', {}).get('delta_mean'))} | {fmt(s.get('abs_terminal', {}).get('delta_mean'))} |"
        )
    lines.append("")
    lines.append("## 市场状态（描述性，不寻优）")
    lines.append("")
    lines.append("| State | N | Δ mean excursion |")
    lines.append("| --- | ---: | ---: |")
    for row in summary["regime"]:
        lines.append(f"| {row['market_state']} | {row.get('n_cross', 'NA')} | {fmt(row.get('delta_mean'))} |")
    lines.append("")
    lines.append("## 可以确认 / 不能确认")
    lines.append("")
    lines.append(f"- 可以确认：{summary['can_confirm']}")
    lines.append(f"- 不能确认：{summary['cannot_confirm']}")
    lines.append(f"- P1：{summary['p1_route']}")
    lines.append("")
    lines.append("## 图表")
    lines.append("")
    for key, path in CHARTS.items():
        lines.append(f"- [{path.name}](../artifacts/{path.name})")
    lines.append("")
    lines.append("本轮未修改旧 `BIN-1D-MA7-CTP` 产物或 verdict。")
    atomic_write_text(REPORT_PATH, "\n".join(lines) + "\n")

    impl = [
        "# BIN-1D-MA7-CER P0 实现审计",
        "",
        f"- 状态：`{STATUS}`",
        f"- 全局裁决：`{summary['verdict']}`",
        f"- 合同锁：`{LOCK_STATUS}`",
        f"- config sha256：`{summary['config_sha256']}`",
        f"- contract sha256：`{lock['contract_sha256']}`",
        f"- manifest sha256：`{summary['manifest_sha256']}`",
        "",
        "## 输入隔离",
        "",
        f"- HYPE 原始分区读取：`{summary['isolation']['hype_raw_partition_read']}`",
        f"- HYPE 行数：`{summary['parity']['hype_rows']}`",
        f"- HYPER 行数：`{summary['parity']['hyper_rows']}`",
        f"- files_read 含 `hype_usdt_usdt`：`{summary['isolation']['hype_slug_in_files_read']}`",
        f"- 未读取 P7 产物：`{summary['isolation']['p7_input_files'] == 0}`",
        "",
        "## 冻结口径",
        "",
        "- 主 outcome 无方向；未使用 P0R 方向 first-hit 成功标签。",
        "- ATR 锚点只来自事件日 `atr_anchor`。",
        "- 主 horizon 固定 5D。",
        "- 无 ML、无权益曲线、无综合 Expansion Score。",
        "- 图表为手写 SVG，不依赖 matplotlib。",
        "- Event-time 数组按 T0 索引，不再二次加 offset。",
        "- 日期匹配只对同时存在 Cross 与 non-cross 的日期加权。",
        "",
        f"运行命令：`{sys.executable} {rel(SCRIPT_PATH)}`",
        "",
    ]
    atomic_write_text(IMPL_AUDIT_PATH, "\n".join(impl))


def build_manifest(paths: list[Path], config_hash: str, lock_hash: str) -> dict[str, Any]:
    files = []
    for path in paths:
        if path == MANIFEST_PATH or not path.exists():
            continue
        files.append({"path": rel(path), "sha256": sha256_file(path), "bytes": path.stat().st_size})
    payload = {
        "research_id": RESEARCH_ID,
        "schema_version": SCHEMA_VERSION,
        "config_sha256": config_hash,
        "contract_lock_sha256": lock_hash,
        "files": files,
        "status": STATUS,
    }
    payload["manifest_sha256"] = canonical_sha256(payload)
    atomic_write_json(MANIFEST_PATH, payload)
    return payload


def assert_no_banned_columns(frame: pd.DataFrame) -> None:
    for col in frame.columns:
        text = str(col).lower()
        for banned in BANNED_OUTCOME_SUBSTRINGS:
            if banned in text:
                raise RuntimeError(f"banned column present: {col}")


def main() -> int:
    generated_at = datetime.now(UTC).isoformat()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    DIAGNOSTIC_DIR.mkdir(parents=True, exist_ok=True)
    config = build_config(generated_at=generated_at)
    print("loading P0R", flush=True)
    raw = load_p0r_panel()
    days, univ_audit = build_eligible_days(raw)
    slugs = set(days["asset_slug"].astype(str))
    slugs.discard(HYPE_SLUG)
    p0r_files = list_p0r_files()
    print("listing daily files", flush=True)
    daily_files = list_daily_files(slugs)
    inputs, lock = freeze_inputs(config, daily_files, p0r_files)
    days, parity = attach_official_identity(days)
    print("loading daily OHLC", flush=True)
    daily = load_daily_ohlc(daily_files, slugs)
    print("computing outcomes", flush=True)
    frame, et_df, outcome_audit = attach_outcomes(days, daily)
    print(
        "post_attach",
        "rows", len(frame),
        "official", int(frame["official_real"].sum()),
        "is_cross", int(frame["is_cross"].sum()),
        "close_notna", int(frame["close"].notna().sum()) if "close" in frame.columns else -1,
        "exc5_notna", int(frame["max_abs_excursion_5d"].notna().sum()) if "max_abs_excursion_5d" in frame.columns else -1,
        "ok5", int(frame["ok_5d"].fillna(False).astype(bool).sum()) if "ok_5d" in frame.columns else -1,
        "official_dtype", str(frame["official_real"].dtype),
        flush=True,
    )
    assert_no_banned_columns(frame)
    if int((frame["asset"] == HYPE_ASSET).sum()) != 0:
        raise RuntimeError("HYPE rows in outcomes")

    # join check: entry_ref vs next-day open
    nxt = daily[["asset", "ts", "open"]].rename(columns={"ts": "entry_ts", "open": "entry_open"})
    chk = frame.merge(nxt, on=["asset", "entry_ts"], how="left")
    finite = chk["entry_ref"].notna() & chk["entry_open"].notna()
    entry_mismatch = int((~np.isclose(chk.loc[finite, "entry_ref"], chk.loc[finite, "entry_open"], rtol=0, atol=1e-8)).sum()) if finite.any() else 0
    atr_daily = daily[["asset", "ts", "atr14"]]
    atr_chk = frame.merge(atr_daily, on=["asset", "ts"], how="left")
    atr_finite = atr_chk["atr_anchor"].notna() & atr_chk["atr14"].notna()
    atr_mismatch = int((~np.isclose(atr_chk.loc[atr_finite, "atr_anchor"], atr_chk.loc[atr_finite, "atr14"], rtol=0, atol=1e-8)).sum()) if atr_finite.any() else 0

    h = PRIMARY_HORIZON
    primary_cols = {m: _metric_col(m, h) for m in BH_METRICS}
    stats_map = {m: date_matched_stats(frame, primary_cols[m]) for m in BH_METRICS}
    print(
        "date_stats",
        {m: (len(stats_map[m]), int(stats_map[m]["n_cross"].sum()) if len(stats_map[m]) else 0) for m in BH_METRICS},
        flush=True,
    )
    primary = {m: summarize_date_stats(stats_map[m]) for m in BH_METRICS}
    extra_stats = {
        "pre_tminus3_to_t0_range": date_matched_stats(frame, "pre_tminus3_to_t0_range"),
        "t0_day_range_atr": date_matched_stats(frame, "t0_day_range_atr"),
        "post_pre_range": date_matched_stats(frame, f"post_pre_range_ratio_{h}d"),
        "post_pre_vol": date_matched_stats(frame, f"post_pre_vol_ratio_{h}d"),
    }
    extra = {k: summarize_date_stats(v) for k, v in extra_stats.items()}

    print("bootstrap", flush=True)
    boot_df, boot_summary = run_block_bootstrap(stats_map)
    pvals = [boot_summary["metrics"][m]["delta_mean"]["p_two_sided"] for m in BH_METRICS]
    qvals = benjamini_hochberg(pvals)
    bh = {m: {"p": pvals[i], "q": qvals[i]} for i, m in enumerate(BH_METRICS)}

    year_exc = year_breakdown(frame, primary_cols["max_abs_excursion"])
    year_rng = year_breakdown(frame, primary_cols["future_range"])
    year_rows = []
    for _, row in year_exc.iterrows():
        r = year_rng.loc[year_rng["period"].eq(row["period"])].iloc[0]
        year_rows.append({
            "period": row["period"],
            "n_cross": row.get("n_cross"),
            "delta_mean": row.get("delta_mean"),
            "range_delta_mean": r.get("delta_mean"),
        })

    placebo_b = same_asset_exact(frame, primary_cols["max_abs_excursion"])
    placebo_c = vol_matched_delta(frame, primary_cols["max_abs_excursion"])
    placebo_d = liq_vol_matched_delta(frame, primary_cols["max_abs_excursion"])
    vol_still = False
    vc = boot_summary["metrics"]["max_abs_excursion"]["delta_mean"]
    if np.isfinite(placebo_c["delta_mean"]) and placebo_c["delta_mean"] > 0 and vc["p2.5"] > 0:
        vol_still = True
    elif np.isfinite(placebo_c["delta_mean"]) and placebo_c["delta_mean"] > 0:
        vol_still = True

    post_ci = boot_summary["metrics"]["future_range"]["delta_mean"]
    pre_stats = extra["pre_tminus3_to_t0_range"]
    t0_stats = extra["t0_day_range_atr"]
    post_stats = primary["future_range"]
    lagging = {
        "pre_delta": pre_stats["delta_mean"],
        "t0_delta": t0_stats["delta_mean"],
        "post_delta": post_stats["delta_mean"],
        "cross_post_pre_range": extra["post_pre_range"]["cross_mean"],
        "non_post_pre_range": extra["post_pre_range"]["non_mean"],
        "cross_post_pre_vol": extra["post_pre_vol"]["cross_mean"],
        "non_post_pre_vol": extra["post_pre_vol"]["non_mean"],
        "pre_elevated": bool(
            (np.isfinite(pre_stats["delta_mean"]) and pre_stats["delta_mean"] >= MATERIAL_ABS_ATR)
            or (np.isfinite(t0_stats["delta_mean"]) and t0_stats["delta_mean"] >= MATERIAL_ABS_ATR)
        ),
        "t0_positive": bool(np.isfinite(t0_stats["delta_mean"]) and t0_stats["delta_mean"] > 0),
        "post_flat": bool(np.isfinite(post_ci["p2.5"]) and post_ci["p2.5"] <= 0 <= post_ci["p97.5"]),
    }

    curves = event_time_curves(et_df)
    pre_et = curves.loc[curves["offset"].between(-3, 0), "delta_range"].mean() if not curves.empty else float("nan")
    post_et = curves.loc[curves["offset"].between(1, 5), "delta_range"].mean() if not curves.empty else float("nan")
    if np.isfinite(pre_et) and np.isfinite(post_et) and pre_et > post_et and lagging["post_flat"]:
        et_finding = f"事件时间显示 Cross 前/当日 range 增量（T-3..T0 Δ≈{fmt(pre_et)}）大于 Cross 后 T+1..T+5（Δ≈{fmt(post_et)}），更接近 lagging marker。"
        lagging_answer = "MA7 Cross 更接近已经发生行情后的 lagging marker，而不是可靠的未来 expansion predictor。"
    elif np.isfinite(post_et) and post_et > 0 and (not np.isfinite(pre_et) or post_et >= pre_et):
        et_finding = f"事件时间显示 T+1..T+5 range 增量（Δ≈{fmt(post_et)}）不小于 T-3..T0（Δ≈{fmt(pre_et)}）。"
        lagging_answer = "MA7 Cross 在 5D 未来窗口上仍有 expansion 增量，不完全只是 T0 之前行情的确认。"
    else:
        et_finding = f"事件时间 T-3..T0 Δ range≈{fmt(pre_et)}，T+1..T+5 Δ range≈{fmt(post_et)}。"
        lagging_answer = "需要结合主 5D outcome 与 lagging 对照一起判断；单一曲线不能单独改写预注册裁决。"

    up = frame.loc[frame["official_real"] & frame["cross_side"].eq("up")]
    down = frame.loc[frame["official_real"] & frame["cross_side"].eq("down")]
    up_down = {
        "up_n": int(len(up)),
        "down_n": int(len(down)),
        "up_exc": finite_mean(up[primary_cols["max_abs_excursion"]].to_numpy(dtype=float)),
        "down_exc": finite_mean(down[primary_cols["max_abs_excursion"]].to_numpy(dtype=float)),
    }

    print("same-asset MC", flush=True)
    mc_b = same_asset_mc(frame, primary_cols["max_abs_excursion"])

    # sensitivity horizons
    sensitivity = {}
    for hz in HORIZONS:
        sensitivity[str(hz)] = {}
        for metric in BH_METRICS:
            col = _metric_col(metric, hz) if metric != "vol_expansion_ratio" or hz in VOL_HORIZONS else None
            if metric in ("vol_expansion_ratio", "path_efficiency") and hz == 1:
                continue
            col = _metric_col(metric, hz)
            if col not in frame.columns:
                continue
            sensitivity[str(hz)][metric] = summarize_date_stats(date_matched_stats(frame, col))

    regime_rows = []
    for state in ["BULL", "BEAR", "MIXED"]:
        sub = frame.loc[frame["market_state"].eq(state)]
        if sub.empty:
            continue
        s = summarize_date_stats(date_matched_stats(sub, primary_cols["max_abs_excursion"]))
        regime_rows.append({"market_state": state, **s})

    verdict = choose_verdict(
        parity,
        primary,
        boot_summary,
        year_exc,
        {"still_positive": vol_still},
        lagging,
    )
    parity["entry_ref_mismatch"] = entry_mismatch
    parity["atr_mismatch"] = atr_mismatch
    if entry_mismatch:
        verdict = "DATA_OR_REPRODUCTION_FAILURE"
        parity["reproduction_failure"] = True
        parity["anchors_ok"] = False

    pct = pooled_percentiles(frame, primary_cols["max_abs_excursion"])

    hype_read = any(HYPE_SLUG in p.lower() and "hyper_usdt_usdt" not in p.lower() for p in FILES_READ)
    isolation = {
        "hype_raw_partition_read": hype_read,
        "hype_slug_in_files_read": hype_read,
        "files_read": FILES_READ,
        "p7_input_files": int(sum("_p7_" in Path(p).name and "_p7a_" not in Path(p).name for p in FILES_READ)),
    }

    p1_route = {
        "EXPANSION_EVENT_SUPPORTED": "可以进入 P1，但仍不得立刻做方向预测。",
        "WEAK_EXPANSION_MARKER": "仅当 effect size 被判断为有意义时才考虑 P1；默认不进入方向模型。",
        "NO_EXPANSION_EDGE": "STOP。不要进入 P1，并停止整条 MA7 研究路线。",
        "CROSS_IS_LAGGING_EXPANSION_MARKER": "STOP 或仅保留 descriptive use。不要进入 P1 方向/扩张模型。",
        "DATA_OR_REPRODUCTION_FAILURE": "先修复数据/identity，不得解释机制。",
    }[verdict]

    can_confirm = "在预注册 5D、日期匹配 placebo 和 28 日块 bootstrap 下，MA7 Cross 与同日 non-cross 的无方向 expansion 对比。"
    cannot_confirm = "不能确认可交易策略、方向预测、最优阈值、live-ready，或把 Cross 当天已经走完的行情当成未来预测。"
    if verdict == "NO_EXPANSION_EDGE":
        can_confirm = "官方 MA7 Cross identity 可复现；相对同日 non-cross，5D 预注册无方向 expansion 均值增量的 95% 块 bootstrap CI 覆盖 0，且 median 增量远小于 0.20 ATR 物质性门槛。"
        cannot_confirm = "不能确认任何交易策略、方向预测、ML 价值，或把 T0 当日略高的 range 解释成未来扩张。"
    elif verdict == "CROSS_IS_LAGGING_EXPANSION_MARKER":
        can_confirm = "未来窗口相对 placebo 无稳定增量，而 Cross 前/当日 range 已达到物质性扩张门槛。"
        cannot_confirm = "不能把 Cross 当作未来 expansion predictor，也不能据此做方向或交易策略。"

    summary = {
        "research_id": RESEARCH_ID,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "verdict": verdict,
        "lock_status": LOCK_STATUS,
        "primary_horizon_days": PRIMARY_HORIZON,
        "parity": {k: v for k, v in parity.items() if k not in {"p5_keys", "p5_val_main"}},
        "universe_audit": univ_audit,
        "outcome_audit": outcome_audit,
        "primary_5d": primary,
        "percentiles_5d_excursion": pct,
        "bootstrap": boot_summary,
        "bh": bh,
        "lagging": lagging,
        "lagging_answer": lagging_answer,
        "event_time_finding": et_finding,
        "event_time_pre_delta": pre_et,
        "event_time_post_delta": post_et,
        "year_rows": year_rows,
        "up_down": up_down,
        "placebo_b": placebo_b,
        "placebo_c": placebo_c,
        "placebo_d": placebo_d,
        "placebo_b_mc": mc_b,
        "sensitivity": sensitivity,
        "regime": regime_rows,
        "isolation": isolation,
        "no_ml": True,
        "no_equity_curve": True,
        "no_composite_score": True,
        "no_directional_success_label": True,
        "p1_route": p1_route,
        "can_confirm": can_confirm,
        "cannot_confirm": cannot_confirm,
        "entry_ref_mismatch": entry_mismatch,
        "atr_mismatch": atr_mismatch,
        "config_sha256": lock["config_sha256"],
    }

    print("writing artifacts", flush=True)
    cross_out = frame.loc[frame["official_real"]].copy()
    placebo_out = frame.loc[~frame["is_cross"]].copy()
    keep_cols = [
        "asset", "ts", "date", "entry_ts", "entry_ref", "atr_anchor", "official_real", "is_cross",
        "cross_side", "volatility_state_p0r", "liq_bucket", "market_state", "event_year", "hyper",
    ]
    for hz in HORIZONS:
        keep_cols.extend([
            f"max_abs_excursion_{hz}d", f"future_range_{hz}d", f"abs_terminal_{hz}d", f"dominance_{hz}d",
        ])
        if hz in VOL_HORIZONS:
            keep_cols.extend([
                f"vol_expansion_ratio_{hz}d",
                f"path_efficiency_{hz}d",
                f"post_pre_range_ratio_{hz}d",
                f"post_pre_vol_ratio_{hz}d",
            ])
    keep_cols.extend(["pre_tminus3_to_t0_range", "t0_day_range_atr"])
    keep_cols = [c for c in keep_cols if c in frame.columns]
    atomic_write_parquet(OUTCOMES_PATH, cross_out[keep_cols])
    atomic_write_parquet(PLACEBO_OUTCOMES_PATH, placebo_out[keep_cols])

    effect_rows = []
    for metric in BH_METRICS:
        item = primary[metric]
        ci = boot_summary["metrics"][metric]["delta_mean"]
        effect_rows.append({
            "metric": metric,
            "horizon": PRIMARY_HORIZON,
            "placebo": "DATE_MATCHED_NON_CROSS",
            **item,
            "ci_low": ci["p2.5"],
            "ci_high": ci["p97.5"],
            "p": bh[metric]["p"],
            "q": bh[metric]["q"],
        })
    atomic_write_csv(MAIN_EFFECTS_PATH, pd.DataFrame(effect_rows))
    atomic_write_csv(YEAR_BREAKDOWN_PATH, year_exc)
    atomic_write_parquet(EVENT_TIME_PATH, et_df)
    atomic_write_parquet(BOOTSTRAP_PATH, boot_df)
    parity_path_payload = {k: v for k, v in parity.items() if k not in {"p5_keys", "p5_val_main"}}
    atomic_write_json(EVENT_PARITY_PATH, parity_path_payload)
    atomic_write_json(DATA_AUDIT_PATH, {
        "universe": univ_audit,
        "outcome": outcome_audit,
        "entry_ref_mismatch": entry_mismatch,
        "atr_mismatch": atr_mismatch,
        "hype_rows": int((frame["asset"] == HYPE_ASSET).sum()),
        "hyper_rows": int(frame["hyper"].sum()),
        "files_read": FILES_READ,
    })

    print("charts", flush=True)
    draw_charts(frame, curves, year_exc, extra)

    manifest_files = [
        CONFIG_PATH, CONTRACT_LOCK_PATH, INPUT_INVENTORY_PATH, DATA_AUDIT_PATH, EVENT_PARITY_PATH,
        OUTCOMES_PATH, PLACEBO_OUTCOMES_PATH, MAIN_EFFECTS_PATH, YEAR_BREAKDOWN_PATH, EVENT_TIME_PATH,
        BOOTSTRAP_PATH, SUMMARY_PATH, REPORT_PATH, IMPL_AUDIT_PATH, CONTRACT_PATH, SCRIPT_PATH,
        *CHARTS.values(),
    ]
    # summary/manifest written after hashes of other files; write summary first without manifest hash then update
    atomic_write_json(SUMMARY_PATH, summary)
    manifest = build_manifest(manifest_files, lock["config_sha256"], canonical_sha256(lock))
    summary["manifest_sha256"] = manifest["manifest_sha256"]
    atomic_write_json(SUMMARY_PATH, summary)
    manifest = build_manifest(manifest_files, lock["config_sha256"], canonical_sha256(lock))
    summary["manifest_sha256"] = manifest["manifest_sha256"]
    atomic_write_json(SUMMARY_PATH, summary)
    write_reports(summary, lock, config)
    # refresh manifest after reports
    manifest = build_manifest(
        [p for p in manifest_files if p != MANIFEST_PATH],
        lock["config_sha256"],
        canonical_sha256(lock),
    )
    print(json.dumps({"verdict": verdict, "official_n": parity["official_n"], "anchors_ok": parity["anchors_ok"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
