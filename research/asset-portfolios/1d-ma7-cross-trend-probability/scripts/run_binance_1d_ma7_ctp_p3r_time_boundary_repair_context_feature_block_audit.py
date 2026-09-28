#!/usr/bin/env python3
"""Run BIN-1D-MA7-CTP P3R time-boundary repair context audit.

P3R is the P3 audit repair. It keeps P3 samples, labels, candidate blocks,
logistic model settings, and decision thresholds unchanged, but replaces the
incorrect `feature_known_at < entry_ts` gate with the P0/P0R contract:
`feature_known_at == entry_ts == ts + 1 day`.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import duckdb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
CATL_DIR = ROOT / "research/asset-portfolios/1d-cross-asset-trend-lifecycle"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAGNOSTIC_DIR = FAMILY_DIR / "diagnostics"

P3_SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p3_context_feature_block_audit.py"
ORIGINAL_P3_FEATURE_SPEC_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_feature_spec.json"
P3_SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3_summary.json"

SPEC_PATH = FAMILY_DIR / "specs/binance-1d-ma7-ctp-p3r-time-boundary-repair-context-feature-block-audit-contract-2026-09-02.md"
FEATURE_SPEC_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_feature_spec.json"
CONTRACT_LOCK_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_contract_lock.json"
FOLD_METRICS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_fold_metrics.parquet"
OOF_PREDICTIONS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_oof_predictions.parquet"
INCREMENTAL_COMPARISONS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_incremental_comparisons.parquet"
DECILE_METRICS_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_decile_metrics.parquet"
MODEL_CARD_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_model_card.json"
SUMMARY_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_summary.json"
MANIFEST_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p3r_manifest.json"
REPORT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p3r-context-feature-block-audit-2026-09-02.md"
AUDIT_PATH = DIAGNOSTIC_DIR / "binance-1d-ma7-ctp-p3r-modeling-audit-2026-09-02.md"
TEST_PATH = ROOT / "tests/test_binance_1d_ma7_ctp_p3r_time_boundary_repair.py"

P0R_MANIFEST_PATH = CATL_DIR / "artifacts/binance_1d_catl_p0r_manifest.json"
P2_FEATURE_SPEC_PATH = ARTIFACT_DIR / "binance_1d_ma7_ctp_p2_feature_spec.json"
PANEL_DIR = CATL_DIR / "artifacts/p0r_donor_directional_modeling_panel"
PANEL_GLOB = PANEL_DIR / "**/*.parquet"

EXPECTED_P0R_MANIFEST_SHA = "033e12bf77c5d67f4871845e3fc2650dfa26a09ca8f74983f379d84e388f93ef"
EXPECTED_P2_FEATURE_SPEC_SHA = "ac4feb1270bb2d0b1da4d1523a84763ada808ec02b409559a603608cceec2c68"
EXPECTED_ORIGINAL_P3_FEATURE_SPEC_SHA = "0862eed0a974684ba16a962ebe146cdefbbc6af7cd6e7532f69c8a4554b61f8b"

HYPE_ASSET = "HYPE/USDT:USDT"
HYPER_ASSET = "HYPER/USDT:USDT"
SEED = 20260901
CUTOFF = pd.Timestamp("2025-01-01T00:00:00Z")
STATUS = "explore / diagnostic-only / not promoted / not live-ready"
TARGET = "label_entry_success_20d"
LABEL_END = "label_end_ts_20d"
NET_RETURN = "label_entry_net_return"
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_BLOCK_DAYS = 28
EXPECTED_STRICT_ROWS = 52563
EXPECTED_STRICT_ASSETS = 338
EXPECTED_STRICT_LONG = 26237
EXPECTED_STRICT_SHORT = 26326
EXPECTED_STRICT_MIN_TS = pd.Timestamp("2019-11-27T00:00:00Z")
EXPECTED_STRICT_MAX_TS = pd.Timestamp("2024-12-10T00:00:00Z")
EXPECTED_MAX_LABEL_END = pd.Timestamp("2024-12-31T00:00:00Z")
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


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


P3 = load_module(P3_SCRIPT_PATH, "binance_1d_ma7_ctp_p3_reference")

P3.SPEC_PATH = SPEC_PATH
P3.FEATURE_SPEC_PATH = FEATURE_SPEC_PATH
P3.CONTRACT_LOCK_PATH = CONTRACT_LOCK_PATH
P3.FOLD_METRICS_PATH = FOLD_METRICS_PATH
P3.OOF_PREDICTIONS_PATH = OOF_PREDICTIONS_PATH
P3.INCREMENTAL_COMPARISONS_PATH = INCREMENTAL_COMPARISONS_PATH
P3.SUMMARY_PATH = SUMMARY_PATH
P3.MANIFEST_PATH = MANIFEST_PATH
P3.MODEL_CARD_PATH = MODEL_CARD_PATH
P3.REPORT_PATH = REPORT_PATH
P3.AUDIT_PATH = AUDIT_PATH
P3.TEST_PATH = TEST_PATH
P3.BOOTSTRAP_SAMPLES = BOOTSTRAP_SAMPLES
P3.forward_oof_calibration = P3.P2.forward_oof_calibration


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="execute P3R")
    parser.add_argument("--force", action="store_true", help="overwrite P3R outputs")
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
        rel = ", ".join(str(path.relative_to(ROOT)) for path in existing)
        raise FileExistsError(f"P3R outputs already exist; pass --force to reproduce: {rel}")


def assert_hashes() -> dict[str, str]:
    hashes = {
        "p0r_manifest_sha256": sha256_file(P0R_MANIFEST_PATH),
        "p2_feature_spec_sha256": sha256_file(P2_FEATURE_SPEC_PATH),
        "original_p3_feature_spec_sha256": sha256_file(ORIGINAL_P3_FEATURE_SPEC_PATH),
    }
    if hashes["p0r_manifest_sha256"] != EXPECTED_P0R_MANIFEST_SHA:
        raise RuntimeError("DATA_BLOCK_NOT_READY: P0R manifest SHA mismatch")
    if hashes["p2_feature_spec_sha256"] != EXPECTED_P2_FEATURE_SPEC_SHA:
        raise RuntimeError("DATA_BLOCK_NOT_READY: P2 feature spec SHA mismatch")
    if hashes["original_p3_feature_spec_sha256"] != EXPECTED_ORIGINAL_P3_FEATURE_SPEC_SHA:
        raise RuntimeError("DATA_BLOCK_NOT_READY: original P3 feature spec SHA mismatch")
    return hashes


def assert_feature_arrays_identical_to_p3(p3r_spec: dict[str, Any], p3_spec: dict[str, Any]) -> dict[str, Any]:
    keys = ["feature_blocks", "candidate_feature_blocks", "categorical_features", "derived_features"]
    checks = {key: p3r_spec[key] == p3_spec[key] for key in keys}
    if not all(checks.values()):
        raise RuntimeError(f"DATA_BLOCK_NOT_READY: P3R feature arrays differ from original P3: {checks}")
    return checks


def validate_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    hashes = assert_hashes()
    feature_spec, p2_feature_spec, input_audit = P3.validate_inputs()
    p3_spec = load_json(ORIGINAL_P3_FEATURE_SPEC_PATH)
    feature_array_checks = assert_feature_arrays_identical_to_p3(feature_spec, p3_spec)
    if input_audit["p0r_manifest_sha256"] != EXPECTED_P0R_MANIFEST_SHA:
        raise RuntimeError("DATA_BLOCK_NOT_READY: P0R manifest hash mismatch after P3 validation")
    input_audit.update(hashes)
    input_audit["original_p3_feature_arrays_identical"] = feature_array_checks
    return feature_spec, p2_feature_spec, input_audit, p3_spec


def source_columns_for_features(feature_spec: dict[str, Any]) -> list[str]:
    return P3.source_columns_for_features(feature_spec)


def t1_source_name(feature: str) -> str:
    return P3.t1_source_name(feature)


def validate_p3r_time_boundary(frame: pd.DataFrame) -> dict[str, Any]:
    time_gate = {
        "feature_known_at_lt_entry_ts": int((frame["feature_known_at"] < frame["entry_ts"]).sum()),
        "feature_known_at_eq_entry_ts": int((frame["feature_known_at"] == frame["entry_ts"]).sum()),
        "feature_known_at_gt_entry_ts": int((frame["feature_known_at"] > frame["entry_ts"]).sum()),
        "entry_ts_eq_ts_plus_1d": int((frame["entry_ts"] == frame["ts"] + pd.Timedelta(days=1)).sum()),
        "feature_known_at_eq_ts_plus_1d": int((frame["feature_known_at"] == frame["ts"] + pd.Timedelta(days=1)).sum()),
    }
    if time_gate["feature_known_at_lt_entry_ts"] != 0 or time_gate["feature_known_at_gt_entry_ts"] != 0:
        raise RuntimeError("DATA_BLOCK_NOT_READY: feature_known_at must equal entry_ts in P3R")
    if time_gate["entry_ts_eq_ts_plus_1d"] != len(frame) or time_gate["feature_known_at_eq_ts_plus_1d"] != len(frame):
        raise RuntimeError("DATA_BLOCK_NOT_READY: entry_ts/feature_known_at must equal ts + 1 day")
    return time_gate


def load_strict_event_panel(feature_spec: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
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
    events["asset_group"] = events["asset"].map(P3.asset_group).astype("int8")
    events["event_year"] = events["ts"].dt.year.astype("int16")

    tradfi_mask = events["asset"].astype(str).str.split("/", n=1).str[0].isin(TRADFI_BASE_SYMBOLS)
    tradfi_counts = events.loc[tradfi_mask, "asset"].value_counts().sort_index().astype(int).to_dict()
    time_gate = validate_p3r_time_boundary(events)

    if len(events) != EXPECTED_STRICT_ROWS:
        raise RuntimeError(f"DATA_BLOCK_NOT_READY: expected strict rows {EXPECTED_STRICT_ROWS}, got {len(events)}")
    if events["asset"].nunique() != EXPECTED_STRICT_ASSETS:
        raise RuntimeError(f"DATA_BLOCK_NOT_READY: expected strict assets {EXPECTED_STRICT_ASSETS}, got {events['asset'].nunique()}")
    if int(events["side"].eq("long").sum()) != EXPECTED_STRICT_LONG or int(events["side"].eq("short").sum()) != EXPECTED_STRICT_SHORT:
        raise RuntimeError("DATA_BLOCK_NOT_READY: strict long/short count mismatch")
    if events["ts"].min() != EXPECTED_STRICT_MIN_TS or events["ts"].max() != EXPECTED_STRICT_MAX_TS:
        raise RuntimeError("DATA_BLOCK_NOT_READY: strict date range mismatch")
    if events[LABEL_END].max() != EXPECTED_MAX_LABEL_END:
        raise RuntimeError("DATA_BLOCK_NOT_READY: strict label end max mismatch")
    if events["asset"].eq(HYPE_ASSET).any():
        raise RuntimeError("HOLDOUT_CONTAMINATED")
    if events["ts"].ge(CUTOFF).any() or events[LABEL_END].ge(CUTOFF).any():
        raise RuntimeError("DATA_BLOCK_NOT_READY: 2025+ row entered P3R strict sample")
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
    if tradfi_counts:
        raise RuntimeError(f"DATA_BLOCK_NOT_READY: known TradFi symbols entered strict sample: {tradfi_counts}")

    P3.assert_t1_is_prior_valid_day(raw, events, feature_spec)
    audit = {
        "tradfi_known_symbol_event_counts": tradfi_counts,
        "tradfi_known_symbol_events": int(tradfi_mask.sum()),
        "time_boundary_repair": time_gate,
        "time_boundary_contract_pass": True,
        "t1_prior_valid_day_audit_pass": True,
        "ordinary_feature_known_no_later_than_signal_close": True,
    }
    return events.reset_index(drop=True), audit


def decile_rows(oof: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for candidate in P3.CANDIDATES:
        for probability_type, suffix in [("raw", "raw"), ("forward_calibrated", "calibrated_forward")]:
            probability_col = f"p_{candidate.lower()}_{suffix}"
            scopes: list[tuple[str, str, pd.DataFrame]] = [("OOF", "all", oof)]
            scopes.extend((str(year), "year", group) for year, group in oof.groupby("event_year", sort=True))
            scopes.extend((str(fold), "fold", group) for fold, group in oof.groupby("fold", sort=True))
            for scope, scope_type, frame in scopes:
                y = frame[TARGET].astype(int).to_numpy()
                base = float(np.mean(y))
                dec = P3.P2.decile_codes(frame[probability_col].to_numpy())
                for code in range(1, 11):
                    mask = dec == code
                    group = frame.loc[mask]
                    yy = y[mask]
                    rows.append(
                        {
                            "candidate": candidate,
                            "probability_type": probability_type,
                            "scope_type": scope_type,
                            "scope": scope,
                            "decile": code,
                            "n": int(mask.sum()),
                            "success_rate": float(np.mean(yy)) if len(yy) else None,
                            "uplift": float(np.mean(yy) - base) if len(yy) else None,
                            "net_return_mean": float(group[NET_RETURN].mean()) if len(group) else None,
                            "net_return_median": float(group[NET_RETURN].median()) if len(group) else None,
                        }
                    )
    return pd.DataFrame(rows)


def stratum_incremental_deltas(oof: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base_col = "p_b0_p2_f1_logit_raw"
    for kind in ["side", "year", "asset_group", "volatility_state", "liquidity_quintile", "listing_age", "pit_universe_size"]:
        labels = P3.stratum_label(oof, kind)
        tmp = oof.copy()
        tmp["_stratum"] = labels
        for value, group in tmp.groupby("_stratum", observed=True):
            if len(group) < 20 or group[TARGET].nunique() < 2:
                continue
            base_auc = float(roc_auc_score(group[TARGET], group[base_col]))
            for candidate in P3.INCREMENTAL_CANDIDATES:
                cand_col = f"p_{candidate.lower()}_raw"
                rows.append(
                    {
                        "candidate": candidate,
                        "stratum_type": kind,
                        "stratum_value": str(value),
                        "n": int(len(group)),
                        "baseline_auc": base_auc,
                        "candidate_auc": float(roc_auc_score(group[TARGET], group[cand_col])),
                        "auc_diff": float(roc_auc_score(group[TARGET], group[cand_col]) - base_auc),
                    }
                )
    return rows


def build_model_card(feature_spec: dict[str, Any], input_audit: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "alias": "BIN-1D-MA7-CTP",
        "experiment": "P3R Time-Boundary Repair + Independent Context Feature Block Audit",
        "model_role": "pooled direction-aligned MA7-cross context block audit",
        "candidates": {candidate: P3.candidate_features(feature_spec, candidate) for candidate in P3.CANDIDATES},
        "feature_spec_sha256": sha256_file(FEATURE_SPEC_PATH),
        "original_p3_feature_spec_sha256": input_audit["original_p3_feature_spec_sha256"],
        "contract_sha256": sha256_file(SPEC_PATH),
        "seed": SEED,
        "calibration": {candidate: summary["development"]["candidate_summary"][candidate]["calibration"] for candidate in P3.CANDIDATES},
        "status": STATUS,
        "hype_rows": 0,
        "hype_reveal_executed": False,
        "post_2025_event_rows_read": 0,
        "post_2025_predictions_written": 0,
        "known_tradfi_strict_sample_rows": 0,
        "not_live_ready": True,
        "prohibited_uses": [
            "position sizing",
            "account backtest",
            "live trading",
            "long/short head deployment",
            "continuation or exit modeling",
            "HYPE reveal",
            "2025+ prediction",
        ],
    }


def fmt(value: Any, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "NA"
    return f"{float(value):.{digits}f}"


def pct(value: Any) -> str:
    if value is None:
        return "NA"
    return f"{100 * float(value):.2f}%"


def write_reports(summary: dict[str, Any], metric_df: pd.DataFrame, comparison_df: pd.DataFrame, decile_df: pd.DataFrame) -> None:
    candidate_summary = summary["development"]["candidate_summary"]
    lines = [
        "# BIN-1D-MA7-CTP P3R：时间边界修复后的独立上下文块审计",
        "",
        f"> {summary['generated_at_utc']}。状态：`{STATUS}`。",
        "> P3R 是 P3 的审计修复版，只修复 `feature_known_at == entry_ts == ts+1d` 时间边界；没有改样本、标签、特征块、模型候选或裁决门槛。",
        "> 本轮不读取 HYPE，不读取或预测 2025+ 事件，不生成策略、仓位、账户权益或 live-ready 产物。",
        "",
        "## 裁决",
        "",
        f"**{summary['decision']['global_verdict']}** / `{STATUS}`",
        "",
        f"- 训练已完成：`{summary['decision']['training_executed']}`；严格样本 `{summary['strict_event_audit']['n']}` 行，资产 `{summary['strict_event_audit']['assets']}`，long/short `{summary['strict_event_audit']['long']}/{summary['strict_event_audit']['short']}`。",
        f"- P3 原记录仍为 `{summary['p3_historical_record']['decision']}`；P3R 是时间门禁修复，不是 P4 或结果后调参。",
        f"- HYPE 输入/严格事件/OOF/模型卡：`{summary['hype_isolation']['input_rows']}/{summary['hype_isolation']['event_rows']}/{summary['hype_isolation']['oof_rows']}/{summary['hype_isolation']['model_card_rows']}`；HYPER 输入 `{summary['hyper_preservation']['input_rows']}`。",
        f"- 2025+ 事件读取/预测写出：`{summary['input_integrity']['post_2025_event_rows_read']}/{summary['input_integrity']['post_2025_prediction_rows_written']}`；严格样本 TradFi 事件 `{summary['tradfi_audit']['strict_sample_known_tradfi_events']}`。",
        "",
        "## 数据与时点审计",
        "",
        f"- 原始 pre-2025 MA7 事件 `{summary['raw_event_audit_without_labels']['n']}`；严格样本日期 `{summary['strict_event_audit']['min_ts']}` 至 `{summary['strict_event_audit']['max_ts']}`，最大标签结束 `{summary['strict_event_audit']['max_label_end_ts_20d']}`。",
        f"- `feature_known_at < entry_ts` `{summary['strict_event_audit']['feature_known_at_lt_entry_ts']}`，`==` `{summary['strict_event_audit']['feature_known_at_eq_entry_ts']}`，`>` `{summary['strict_event_audit']['feature_known_at_gt_entry_ts']}`；`entry_ts == ts+1d` `{summary['strict_event_audit']['entry_ts_eq_ts_plus_1d']}`。",
        f"- B0-B4 feature arrays 与原 P3 逐字段一致：`{all(summary['feature_spec_consistency'].values())}`。",
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
            "| Candidate | Fold | Train n | Train AUC | Train PR-AUC | Train Brier | Val n | Val AUC | Val PR-AUC | Val forward Brier | Val forward logloss | AUC 差 | Uplift 差 | 标记 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for candidate in P3.CANDIDATES:
        for fold in ["D1", "D2", "D3"]:
            tr = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["fold"].eq(fold)) & (metric_df["split"].eq("training")) & (metric_df["probability_type"].eq("raw"))].iloc[0]
            va_raw = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["fold"].eq(fold)) & (metric_df["split"].eq("validation")) & (metric_df["probability_type"].eq("raw"))].iloc[0]
            va_cal = metric_df.loc[(metric_df["candidate"].eq(candidate)) & (metric_df["fold"].eq(fold)) & (metric_df["split"].eq("validation")) & (metric_df["probability_type"].eq("forward_calibrated"))].iloc[0]
            lines.append(
                f"| {candidate} | {fold} | {int(tr.eval_n)} | {fmt(tr.roc_auc)} | {fmt(tr.pr_auc)} | {fmt(tr.brier)} | "
                f"{int(va_raw.eval_n)} | {fmt(va_raw.roc_auc)} | {fmt(va_raw.pr_auc)} | {fmt(va_cal.brier)} | {fmt(va_cal.log_loss)} | "
                f"{fmt(va_raw.train_val_auc_gap)} | {fmt(va_raw.train_val_top_uplift_gap)} | {va_raw.overfit_flag or ''} |"
            )
    lines.extend(
        [
            "",
            "## 单块增量裁决",
            "",
            "| Block | Decision | AUC diff | 95% CI | p | q | Folds improved | Worst fold delta | Non-overlap diff | Long diff | Short diff | Top10 success diff | Top10 net diff |",
            "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in comparison_df.itertuples():
        lines.append(
            f"| {row.candidate} | `{row.decision}` | {fmt(row.auc_diff)} | [{fmt(row.auc_diff_ci95_low)}, {fmt(row.auc_diff_ci95_high)}] | {fmt(row.auc_diff_p)} | {fmt(row.auc_diff_bh_q)} | "
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
            f"- 最高 20% - 最低 20% 成功率差：`{fmt(liq['q5_minus_q1_success_rate']['point'])}`，95% CI `[{fmt(liq['q5_minus_q1_success_rate']['ci95_low'])}, {fmt(liq['q5_minus_q1_success_rate']['ci95_high'])}]`；净收益均值差 `{fmt(liq['q5_minus_q1_net_return_mean']['point'])}`。",
            f"- `liquidity_rank_pct_p0r` 三折系数同号：`{liq['liquidity_rank_coef_same_sign']}`；系数：{', '.join(f'{k}={fmt(v)}' for k, v in liq['liquidity_rank_coef_by_fold'].items())}。",
            "",
            "| Liquidity quintile | n | 成功率 | 净收益均值 | B0 AUC | B1 AUC | B1-B0 AUC |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for value, item in liq["quintiles"].items():
        lines.append(f"| {value} | {item['n']} | {pct(item['success_rate'])} | {fmt(item['net_return_mean'])} | {fmt(item['b0_auc'])} | {fmt(item['b1_auc'])} | {fmt(item['b1_minus_b0_auc'])} |")
    lines.extend(["", "## Top/Bottom 十分位（OOF raw）", "", "| Candidate | Top10 n | Top10 成功率 | Top10 uplift | Top10 净收益均值 | Bottom10 成功率 |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for candidate in P3.CANDIDATES:
        item = candidate_summary[candidate]["decile_raw"]
        lines.append(f"| {candidate} | {item['top_n']} | {pct(item['top_success_rate'])} | {fmt(item['top_uplift'])} | {fmt(item['top_net_return_mean'])} | {pct(item['bottom_success_rate'])} |")
    lines.extend(
        [
            "",
            "## 前向校准与边界",
            "",
            f"- D1 保持 raw；D2/D3 只用更早 OOF。B0 D2-D3 raw/calibrated Brier：`{fmt(candidate_summary['B0_P2_F1_LOGIT']['calibration']['forward_validation']['raw']['brier'])}` / `{fmt(candidate_summary['B0_P2_F1_LOGIT']['calibration']['forward_validation']['forward_calibrated']['brier'])}`。",
            "- 2025+ 是本家族已揭示历史段，不是严格盲测；P3R 按合同没有读取或预测 2025+。",
            "- 本轮没有 HYPE reveal，没有退出/持仓/反手模型，没有策略、账户回测、仓位或 live-ready 产物。",
        ]
    )
    atomic_write_text(REPORT_PATH, "\n".join(lines) + "\n")

    audit_lines = [
        "# BIN-1D-MA7-CTP P3R 建模审计",
        "",
        f"状态：`{STATUS}`。裁决：`{summary['decision']['global_verdict']}`。",
        "",
        "## 机械修复记录",
        "",
        "- 原 P3 合同要求 `feature_known_at < entry_ts`，严格样本全部为等于关系，故 P3 训练前停止。",
        "- P3R 只修复为 `feature_known_at == entry_ts == ts + 1 day`；没有修改标签、样本、特征、模型候选或裁决门槛。",
        "- 前向校准调用 P2 修复后的逻辑：只有更早 OOF 可参与当前 fold 校准，且若前向 Brier/LogLoss 未改善则冻结 raw。",
        "",
        "## 输入完整性",
        "",
        f"- P0R manifest SHA256：`{summary['input_integrity']['p0r_manifest_sha256']}`；artifact 哈希全部匹配：`{summary['input_integrity']['p0r_artifact_hashes_all_match']}`。",
        f"- P2 feature spec SHA256：`{summary['input_integrity']['p2_feature_spec_sha256']}`；原 P3 feature spec SHA256：`{summary['input_integrity']['original_p3_feature_spec_sha256']}`。",
        f"- B0 精确复用 P2 F1：`{summary['b0_exactly_reuses_p2_f1']}`；P3R feature arrays 与原 P3 一致：`{summary['feature_spec_consistency']}`。",
        "",
        "## 隔离与样本",
        "",
        f"- HYPE 输入/事件/OOF/模型卡：`{summary['hype_isolation']['input_rows']}/{summary['hype_isolation']['event_rows']}/{summary['hype_isolation']['oof_rows']}/{summary['hype_isolation']['model_card_rows']}`。",
        f"- 2025+ 事件读取/预测写出：`{summary['input_integrity']['post_2025_event_rows_read']}/{summary['input_integrity']['post_2025_prediction_rows_written']}`。",
        f"- 已知 TradFi 严格样本事件：`{summary['tradfi_audit']['strict_sample_known_tradfi_events']}`；底层 post-2025 可用行只记录为 `{summary['input_integrity']['post_2025_rows_available_but_not_modeled']}`，不进入建模。",
        "",
        "## 模型与审计",
        "",
        "- 所有候选使用同一严格样本行；只训练 pooled Logistic Regression，不训练 long/short heads，不训练 LightGBM。",
        "- 数值中位数、类别 one-hot 与 StandardScaler 均只在训练折拟合；D1-D3 purge 全部通过。",
        f"- 28 日 paired bootstrap 使用同一重采样索引，draw hash：`{summary['stability']['bootstrap']['paired_draw_counts_sha256']}`。",
        "",
        "## 禁止产物",
        "",
        "- 无 HYPE、无 2025+ 预测、无策略、无仓位、无权益曲线、无 live spec、无 live-ready。",
    ]
    atomic_write_text(AUDIT_PATH, "\n".join(audit_lines) + "\n")


def build_manifest(paths: Iterable[Path], input_audit: dict[str, Any], decision: str) -> None:
    artifacts = []
    for path in paths:
        if path.exists():
            artifacts.append({"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    atomic_write_json(
        MANIFEST_PATH,
        {
            "family": "Binance-1D-MA7-Cross-Trend-Probability",
            "alias": "BIN-1D-MA7-CTP",
            "experiment": "P3R Time-Boundary Repair + Independent Context Feature Block Audit",
            "generated_at_utc": datetime.now(UTC),
            "status": STATUS,
            "decision": decision,
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
                "original_p3_feature_spec_path": str(ORIGINAL_P3_FEATURE_SPEC_PATH.relative_to(ROOT)),
                "original_p3_feature_spec_sha256": input_audit["original_p3_feature_spec_sha256"],
                "contract_sha256": sha256_file(SPEC_PATH),
                "feature_spec_sha256": sha256_file(FEATURE_SPEC_PATH),
            },
            "artifacts": artifacts,
        },
    )


def main() -> None:
    args = parse_args()
    if not args.run:
        raise SystemExit("Pass --run to execute P3R.")
    ensure_output_policy(args.force)
    feature_spec, p2_feature_spec, input_audit, _ = validate_inputs()
    raw_event_audit = P3.count_events_without_labels()
    atomic_write_json(
        CONTRACT_LOCK_PATH,
        {
            "status": "FROZEN_BEFORE_P3R_LABEL_READ",
            "generated_at_utc": datetime.now(UTC),
            "contract_sha256": sha256_file(SPEC_PATH),
            "feature_spec_sha256": sha256_file(FEATURE_SPEC_PATH),
            "p0r_manifest_sha256": input_audit["p0r_manifest_sha256"],
            "p2_feature_spec_sha256": input_audit["p2_feature_spec_sha256"],
            "original_p3_feature_spec_sha256": input_audit["original_p3_feature_spec_sha256"],
            "event_filter_audit_without_labels": raw_event_audit,
            "time_boundary_repair_only": True,
        },
    )
    print("P3R contract lock written; loading labels after lock.", flush=True)

    frame, strict_extra = load_strict_event_panel(feature_spec)
    metric_df, oof, coef_df, development = P3.run_development(frame, feature_spec)
    comparison_df, stability = P3.summarize_incremental(oof, metric_df, coef_df)
    stratum_metric_df = pd.DataFrame(P3.stratum_rows(oof))
    if not stratum_metric_df.empty:
        metric_df = pd.concat([metric_df, stratum_metric_df], ignore_index=True)
    decile_df = decile_rows(oof)
    final_metrics = P3.final_refit_metrics(frame, feature_spec)
    top10_by_year = P3.build_top10_by_year(oof)
    forward_probability = P3.build_forward_probability_reports(oof)

    strict_audit = {
        "n": int(len(frame)),
        "assets": int(frame["asset"].nunique()),
        "long": int(frame["side"].eq("long").sum()),
        "short": int(frame["side"].eq("short").sum()),
        "hype": int(frame["asset"].eq(HYPE_ASSET).sum()),
        "hyper": int(frame["asset"].eq(HYPER_ASSET).sum()),
        "min_ts": frame["ts"].min(),
        "max_ts": frame["ts"].max(),
        "max_label_end_ts_20d": frame[LABEL_END].max(),
        "non_cross": int((~frame["probe_raw_ma7_cross_dir"]).sum()),
        "duplicate_asset_ts": int(frame.duplicated(["asset", "ts"]).sum()),
        "duplicate_asset_ts_side": int(frame.duplicated(["asset", "ts", "side"]).sum()),
        "null_target": int(frame[TARGET].isna().sum()),
        "incomplete_20d_future_path": int((~frame["future_path_complete_20d"]).sum()),
        "feature_known_at_lt_entry_ts": strict_extra["time_boundary_repair"]["feature_known_at_lt_entry_ts"],
        "feature_known_at_eq_entry_ts": strict_extra["time_boundary_repair"]["feature_known_at_eq_entry_ts"],
        "feature_known_at_gt_entry_ts": strict_extra["time_boundary_repair"]["feature_known_at_gt_entry_ts"],
        "entry_ts_eq_ts_plus_1d": strict_extra["time_boundary_repair"]["entry_ts_eq_ts_plus_1d"],
        "feature_known_at_eq_ts_plus_1d": strict_extra["time_boundary_repair"]["feature_known_at_eq_ts_plus_1d"],
        "positive_rate": float(frame[TARGET].mean()),
    }
    p3_summary = load_json(P3_SUMMARY_PATH)
    summary: dict[str, Any] = {
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "alias": "BIN-1D-MA7-CTP",
        "experiment": "P3R Time-Boundary Repair + Independent Context Feature Block Audit",
        "generated_at_utc": datetime.now(UTC),
        "status": STATUS,
        "objective_ma7_cross_only": True,
        "time_boundary_repair_only": True,
        "one_pooled_model_only": True,
        "independent_long_short_heads_trained": 0,
        "no_strategy_no_portfolio_no_live_artifact": True,
        "p3_historical_record": {
            "decision": p3_summary["decision"]["global_verdict"],
            "training_executed": p3_summary["decision"]["training_executed"],
            "feature_known_at_eq_entry_ts": p3_summary["strict_event_audit"]["feature_known_at_eq_entry_ts"],
        },
        "input_integrity": input_audit,
        "raw_event_audit_without_labels": raw_event_audit,
        "strict_event_audit": strict_audit,
        "tradfi_audit": {
            "known_base_symbols": sorted(TRADFI_BASE_SYMBOLS),
            "strict_sample_known_tradfi_events": strict_extra["tradfi_known_symbol_events"],
            "strict_sample_counts_by_asset": strict_extra["tradfi_known_symbol_event_counts"],
            "performed_after_strict_sample_formation": True,
        },
        "time_boundary_audit": strict_extra["time_boundary_repair"],
        "feature_spec_consistency": input_audit["original_p3_feature_arrays_identical"],
        "b0_exactly_reuses_p2_f1": feature_spec["feature_blocks"]["B0_P2_F1"] == P3.scheme_features(p2_feature_spec, "F1_MA7_PATH"),
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
        "stratum_incremental_deltas": stratum_incremental_deltas(oof),
        "liquidity_special": stability["liquidity_special"],
        "top10_by_validation_year_raw": top10_by_year,
        "forward_probability_reports": forward_probability,
        "final_refit_pre_2025": final_metrics,
        "decision": {
            "global_verdict": stability["global_verdict"],
            "block_decisions": stability["block_decisions"],
            "training_executed": True,
            "status": STATUS,
            "not_live_ready": True,
            "no_2025_plus_historical_test": True,
        },
    }
    model_card = build_model_card(feature_spec, input_audit, summary)

    atomic_write_parquet(FOLD_METRICS_PATH, metric_df)
    atomic_write_parquet(OOF_PREDICTIONS_PATH, oof)
    atomic_write_parquet(INCREMENTAL_COMPARISONS_PATH, comparison_df)
    atomic_write_parquet(DECILE_METRICS_PATH, decile_df)
    atomic_write_json(SUMMARY_PATH, summary)
    atomic_write_json(MODEL_CARD_PATH, model_card)
    write_reports(summary, metric_df, comparison_df, decile_df)
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
            DECILE_METRICS_PATH,
            SUMMARY_PATH,
            MODEL_CARD_PATH,
            REPORT_PATH,
            AUDIT_PATH,
        ],
        input_audit,
        summary["decision"]["global_verdict"],
    )
    print(f"P3R complete: {summary['decision']['global_verdict']}", flush=True)


if __name__ == "__main__":
    main()
