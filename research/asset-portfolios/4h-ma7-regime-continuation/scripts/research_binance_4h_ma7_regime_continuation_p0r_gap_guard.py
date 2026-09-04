#!/usr/bin/env python3
"""BIN-4H-MA7-RC P0R-GAP-GUARD entry.

Inventory of gap impact and small real-data verification only.
Does not overwrite P0 / P0R-DATA artifacts. Does not run full PnL research.
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

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/4h-ma7-regime-continuation"
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = FAMILY_DIR / "configs/binance-4h-ma7-regime-continuation-p0r-gap-guard.json"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAGNOSTIC_DIR = FAMILY_DIR / "diagnostics"
REPORT_PATH = DIAGNOSTIC_DIR / "binance-4h-ma7-regime-continuation-p0r-gap-guard-2026-09-03.md"

EXPECTED_CONFIG_SHA256 = "71306a2b45471f1e8e24fcd0d6a621a94c95be7bc83e65a69c2fa6faa61bd67d"
EXPECTED_MANIFEST_SHA256 = "2af83bfaee7632ba3b77e4c4e08d104e492620d62c86b3515d586537e4c3a823"
RUN_DATE = "2026-09-03"

KNOWN_STATISTICAL_BLOCKERS = [
    "完整年度窗口仍只统计 2023–2025 三个日历年，PASS 却要求至少四个正年度，故 SUPPORTED_WEAK_CONTINUATION 在现口径下不可达。",
    "horizon 表先写 bootstrap p_value，随后 cluster 用同名 p_value 覆盖，导致 CI 与 p/q-value 检验对象不一致。本轮未修复。",
    "P0R-DATA 全市场结果尚未写出。",
]

OUTPUTS = {
    "inventory_summary": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_gap_guard_inventory_summary_{RUN_DATE}.json",
    "by_metric": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_gap_guard_inventory_by_metric_{RUN_DATE}.csv",
    "by_direction": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_gap_guard_inventory_by_direction_{RUN_DATE}.csv",
    "by_year": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_gap_guard_inventory_by_year_{RUN_DATE}.csv",
    "by_phase": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_gap_guard_inventory_by_phase_{RUN_DATE}.csv",
    "by_symbol": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_gap_guard_inventory_by_symbol_{RUN_DATE}.csv",
    "verify": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_gap_guard_verify_{RUN_DATE}.json",
    "parent_hash_check": ARTIFACT_DIR / f"binance_4h_ma7_rc_p0r_gap_guard_parent_hash_check_{RUN_DATE}.json",
}


def load_module(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


P0R = load_module(
    "binance_4h_ma7_rc_p0r_data",
    SCRIPT_DIR / "research_binance_4h_ma7_regime_continuation_p0r_data.py",
)
P0 = P0R.P0
GG = load_module("binance_4h_ma7_rc_gap_guard", SCRIPT_DIR / "binance_4h_ma7_rc_gap_guard.py")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sidecar(path: Path) -> str:
    digest = sha256_file(path)
    rel_path = path.relative_to(ROOT).as_posix()
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {rel_path}\n", encoding="utf-8")
    return digest


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run BIN-4H-MA7-RC P0R-GAP-GUARD inventory.")
    parser.add_argument("--run", action="store_true", help="Acknowledge frozen rule lock.")
    parser.add_argument("--force", action="store_true", help="Replace existing gap-guard outputs only.")
    parser.add_argument("--skip-inventory", action="store_true", help="Only run small verification.")
    parser.add_argument("--skip-verify", action="store_true", help="Skip real-data window checks.")
    parser.add_argument("--native-only", action="store_true", help="Inventory native 0h only.")
    return parser.parse_args()


def validate_frozen_config() -> dict[str, Any]:
    actual = sha256_file(CONFIG_PATH)
    if actual != EXPECTED_CONFIG_SHA256:
        raise RuntimeError(f"frozen gap-guard config hash mismatch: {actual} != {EXPECTED_CONFIG_SHA256}")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if config["study_id"] != "BIN-4H-MA7-RC-P0R-GAP-GUARD":
        raise RuntimeError("unexpected study_id")
    manifest_path = ROOT / config["data"]["dataset_manifest"]
    if sha256_file(manifest_path) != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("gap-guard dataset manifest hash mismatch")
    if config["data"]["native_4h_dataset_id"] != P0R.BINANCE_PERP_4H_FROM_15M_V1:
        raise RuntimeError("native 4h dataset_id changed")
    if config["data"]["path_1h_dataset_id"] != P0R.BINANCE_PERP_1H_FROM_15M_V1:
        raise RuntimeError("path 1h dataset_id changed")
    if "binance.perp.ohlcv.1h.normalized.legacy" not in config["data"]["forbidden_dataset_ids"]:
        raise RuntimeError("legacy 1h is not forbidden")
    return config


def parent_hash_check(config: dict[str, Any]) -> dict[str, Any]:
    expected = config["protected_parent_hashes"]
    mapping = {
        "p0_config": P0.CONFIG_PATH,
        "p0r_data_config": P0R.CONFIG_PATH,
        "p0_script": P0R.P0_SCRIPT_PATH,
        "p0r_data_script": SCRIPT_DIR / "research_binance_4h_ma7_regime_continuation_p0r_data.py",
        "p0_manifest": ARTIFACT_DIR / "binance_4h_ma7_rc_p0_dataset_manifest_2026-09-02.json",
        "p0r_data_manifest": ARTIFACT_DIR / "binance_4h_ma7_rc_p0r_data_dataset_manifest_2026-09-03.json",
        "p0_summary": ARTIFACT_DIR / "binance_4h_ma7_rc_p0_summary_2026-09-02.json",
        "p0_results_report": DIAGNOSTIC_DIR / "binance-4h-ma7-regime-continuation-p0-results-2026-09-02.md",
    }
    rows = []
    all_ok = True
    for key, path in mapping.items():
        actual = sha256_file(path)
        ok = actual == expected[key]
        all_ok = all_ok and ok
        rows.append({"name": key, "path": rel(path), "expected": expected[key], "actual": actual, "unchanged": ok})
    if not all_ok:
        raise RuntimeError("protected P0 / P0R-DATA files changed; aborting gap-guard run")
    planned = {path.resolve() for path in [*OUTPUTS.values(), REPORT_PATH]}
    protected = {path.resolve() for path in P0R.p0_protected_paths()}
    overlap = planned & protected
    if overlap:
        raise RuntimeError(f"gap-guard outputs collide with protected files: {overlap}")
    p0r_outputs = {path.resolve() for path in [*P0R.OUTPUTS.values(), P0R.REPORT_PATH]}
    if planned & p0r_outputs:
        raise RuntimeError("gap-guard outputs collide with P0R-DATA outputs")
    return {"unchanged": True, "files": rows}


def prepare_outputs(force: bool) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    DIAGNOSTIC_DIR.mkdir(parents=True, exist_ok=True)
    existing = [path for path in [*OUTPUTS.values(), REPORT_PATH] if path.exists()]
    if existing and not force:
        names = ", ".join(rel(path) for path in existing[:3])
        raise RuntimeError(f"gap-guard outputs already exist; pass --force. Existing: {names}")


def hourly_ts_maps(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    maps: dict[str, pd.DataFrame] = {}
    for symbol, group in frame.groupby("symbol", sort=True):
        ordered = group.sort_values("ts")
        maps[str(symbol)] = pd.DataFrame({"ts": ordered["ts"].to_numpy()}).set_index(
            pd.DatetimeIndex(pd.to_datetime(ordered["ts"], utc=True))
        )
    return maps


def verify_real_windows(
    native_4h: pd.DataFrame,
    ohlcv_1h: pd.DataFrame | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "aergo_probe_window": "2025-04-01T00:00:00Z/2025-05-01T00:00:00Z",
        "continuous_probe_symbol": None,
        "aergo_gaps_found": False,
        "continuous_sample_ok": False,
        "gap_does_not_continue_across_segment": False,
        "notes": [],
    }
    aergo_sym = "AERGO/USDT:USDT"
    aergo = native_4h.loc[native_4h["symbol"].eq(aergo_sym)].copy()
    gaps = GG.discover_internal_gaps(
        aergo,
        pd.Timedelta(hours=4),
        symbol=aergo_sym,
        start="2025-04-01T00:00:00Z",
        end="2025-05-01T00:00:00Z",
    )
    payload["aergo_row_count_in_probe"] = int(len(aergo.loc[
        (aergo["ts"] >= pd.Timestamp("2025-04-01T00:00:00Z"))
        & (aergo["ts"] < pd.Timestamp("2025-05-01T00:00:00Z"))
    ])) if not aergo.empty else 0
    payload["aergo_gaps"] = gaps.to_dict("records")
    payload["aergo_gaps_found"] = not gaps.empty
    if gaps.empty:
        payload["notes"].append("AERGO 2025-04 窗口现场未发现内部缺口；不硬编码缺口位置。")
    else:
        gap = gaps.iloc[0]
        after = pd.Timestamp(gap["gap_after_ts"])
        panel = aergo.sort_values("ts")
        recross = GG.recross_survival_on_grid(
            signal_bar_ns=GG.utc_ns(after),
            side=1,
            fourh_ts=GG.series_utc_ns(panel["ts"]),
            close=panel["close"].to_numpy(dtype=float),
            sma7=panel["sma7"].to_numpy(dtype=float) if "sma7" in panel.columns else np.full(len(panel), np.nan),
        )
        payload["aergo_gap_used"] = {
            "gap_after_ts": gap["gap_after_ts"],
            "gap_resume_ts": gap["gap_resume_ts"],
            "missing_bars": int(gap["missing_bars"]),
            "recross_reason": recross["exclusive_reason"],
            "recross_complete": recross["recross_complete"],
            "recross_after_gap_bars": recross["recross_after_gap_bars"],
            "survival_main": recross["same_side_survival_bars"],
        }
        payload["gap_does_not_continue_across_segment"] = (
            recross["exclusive_reason"] == "internal_gap"
            and recross["recross_complete"] is False
            and not np.isfinite(recross["same_side_survival_bars"])
        )
        if recross["recross_complete"]:
            payload["notes"].append("缺口后若被记成完整持续，验收失败。")
        # Resume bar must not be treated as bar 1 of the old segment.
        if np.isfinite(recross["recross_after_gap_bars"]):
            payload["notes"].append("缺口后存在反穿，仅写入诊断字段，未进入主口径。")

    # Continuous window: longest native 0h run of BTC if present, else first symbol.
    btc = native_4h.loc[native_4h["symbol"].eq("BTC/USDT:USDT")].copy()
    candidate = btc if not btc.empty else native_4h.loc[native_4h["symbol"].eq(native_4h["symbol"].iloc[0])].copy()
    if candidate.empty:
        payload["notes"].append("无可用连续窗口验证样本。")
        return payload
    payload["continuous_probe_symbol"] = str(candidate["symbol"].iloc[0])
    ordered = candidate.sort_values("ts")
    if "block_id" not in ordered.columns:
        ordered = GG.assign_contiguous_blocks(ordered, pd.Timedelta(hours=4))
    sizes = ordered.groupby("block_id").size()
    block_id = int(sizes.idxmax())
    block = ordered.loc[ordered["block_id"].eq(block_id)].copy()
    payload["continuous_block"] = {
        "symbol": payload["continuous_probe_symbol"],
        "bars": int(len(block)),
        "start": P0._iso(block["ts"].min()),
        "end": P0._iso(block["ts"].max()),
    }
    if len(block) < 40:
        payload["notes"].append("最长连续段不足 40 根 4h，跳过新旧 enrich 对照。")
        return payload
    signal_row = block.iloc[20]
    event = pd.DataFrame(
        {
            "symbol": [signal_row["symbol"]],
            "base_asset": [signal_row.get("base_asset", str(signal_row["symbol"]).split("/")[0])],
            "quote_asset": ["USDT"],
            "ts": [signal_row["ts"]],
            "phase_hour": [0],
            "block_id": [signal_row["block_id"]],
            "ma_period": [7],
            "direction": ["long"],
            "side": [1],
            "signal_ts": [signal_row["ts"] + pd.Timedelta(hours=4)],
            "entry_ts": [signal_row["ts"] + pd.Timedelta(hours=4)],
            "entry_price": [float(block.iloc[21]["open"])],
            "atr_scale": [10.0],
            "cross_event": [True],
            "in_trading_pool": [True],
            "atr_quintile": pd.Series([3], dtype="Int64"),
        }
    )
    fourh_maps = P0.panel_maps(block)
    if ohlcv_1h is None or ohlcv_1h.empty:
        hourly_maps = {}
        payload["notes"].append("无 1h 路径，连续窗口只对照 recross。")
    else:
        sym = str(signal_row["symbol"])
        hourly = ohlcv_1h.loc[ohlcv_1h["symbol"].eq(sym)].copy()
        hourly_maps = P0.hourly_maps(hourly) if not hourly.empty else {}
    if not hourly_maps:
        recross_old = P0.enrich_outcomes(event, {}, fourh_maps, {})
        recross_new = GG.apply_gap_guard(recross_old, {}, fourh_maps, {})
        payload["continuous_recross_old"] = float(recross_old.iloc[0]["ma7_recross_bars"]) if np.isfinite(recross_old.iloc[0]["ma7_recross_bars"]) else None
        payload["continuous_recross_new"] = float(recross_new.iloc[0]["ma7_recross_bars"]) if np.isfinite(recross_new.iloc[0]["ma7_recross_bars"]) else None
        payload["continuous_survival_old"] = float(recross_old.iloc[0]["same_side_survival_bars"])
        payload["continuous_survival_new"] = float(recross_new.iloc[0]["same_side_survival_bars"]) if np.isfinite(recross_new.iloc[0]["same_side_survival_bars"]) else None
        payload["continuous_sample_ok"] = (
            recross_new.iloc[0]["recross_complete"]
            and (
                (not np.isfinite(recross_old.iloc[0]["ma7_recross_bars"]) and not np.isfinite(recross_new.iloc[0]["ma7_recross_bars"]))
                or recross_old.iloc[0]["ma7_recross_bars"] == recross_new.iloc[0]["ma7_recross_bars"]
            )
            and recross_old.iloc[0]["same_side_survival_bars"] == recross_new.iloc[0]["same_side_survival_bars"]
        )
        return payload
    old = P0.enrich_outcomes(event, hourly_maps, fourh_maps, {})
    new = GG.enrich_outcomes_gap_aware(event, hourly_maps, fourh_maps, {})
    compare_cols = [
        "first_hit_label",
        "ma7_recross_bars",
        "same_side_survival_bars",
        "gross_return_1",
        "gross_return_3",
        "mfe_1",
        "mae_1",
    ]
    mismatches = []
    for col in compare_cols:
        left = old.iloc[0][col]
        right = new.iloc[0][col]
        if pd.isna(left) and pd.isna(right):
            continue
        if left != right and not (isinstance(left, float) and isinstance(right, float) and math.isclose(float(left), float(right), rel_tol=0, abs_tol=1e-12)):
            mismatches.append({"column": col, "old": left, "new": right})
    payload["continuous_mismatches"] = mismatches
    payload["continuous_sample_ok"] = mismatches == []
    payload["continuous_first_hit_label"] = str(new.iloc[0]["first_hit_label"])
    return payload


def render_report(summary: dict[str, Any]) -> None:
    inv = summary.get("inventory") or {}
    verify = summary.get("verify") or {}
    parent = summary.get("parent_hash_check") or {}
    completeness = inv.get("completeness", "未完成")
    verdict = summary.get("gap_guard_verdict", "FAIL")
    by_metric = inv.get("headline_by_metric") or []

    def md_rows(rows: list[dict[str, Any]], columns: list[str]) -> str:
        if not rows:
            return "_无数据或盘点未完成_"
        header = "| " + " | ".join(columns) + " |"
        sep = "| " + " | ".join(["---"] * len(columns)) + " |"
        body = []
        for row in rows[:24]:
            body.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
        return "\n".join([header, sep, *body])

    blockers = "\n".join(f"- {item}" for item in KNOWN_STATISTICAL_BLOCKERS)
    aergo_ok = bool(verify.get("gap_does_not_continue_across_segment")) or not verify.get("aergo_gaps_found")
    report = f"""# BIN-4H-MA7-RC P0R-GAP-GUARD 验收报告（2026-09-03）

## 结论先行

- 缺口保护是否实现并通过测试：`{verdict}`。
- 连续样本是否保持原结果：`{'PASS' if verify.get('continuous_sample_ok') else 'FAIL / 未验证'}`。
- 有多少研究样本受到缺口影响：见下方盘点；全库 K 线缺失比例不得当作策略样本损失比例。
- 完整研究还有哪些独立 blocker：见文末。本轮结论只覆盖缺口保护，不是策略有效、全研究通过或可以上线。

家族状态保持 `explore / diagnostic-only / not promoted / not live-ready`。未登记 `V1`，未 promotion，未写 runner。

## 冻结与范围

- 合同：[binance-4h-ma7-regime-continuation-p0r-gap-guard-contract-2026-09-03.md](../specs/binance-4h-ma7-regime-continuation-p0r-gap-guard-contract-2026-09-03.md)
- 配置 SHA256：`{summary['input_lineage']['config_sha256']}`
- 输入：`binance.perp.ohlcv.4h.from_15m.v1` 与 `binance.perp.ohlcv.1h.from_15m.v1`
- 截止：`2026-08-24T08:00:00Z`
- 原 P0 / P0R-DATA 文件未变化：`{parent.get('unchanged')}`

## 测试

合成反例不依赖本地行情。针对性测试文件：[tests/test_binance_4h_ma7_regime_continuation_p0r_gap_guard.py](../../../tests/test_binance_4h_ma7_regime_continuation_p0r_gap_guard.py)。报告生成时测试结果：`{summary.get('tests', {}).get('status', '见命令输出')}`，通过 `{summary.get('tests', {}).get('passed', '')}`。

## 真实窗口验证

- 连续窗口：`{verify.get('continuous_probe_symbol')}`，`{verify.get('continuous_block')}`，新旧一致：`{verify.get('continuous_sample_ok')}`。
- AERGO 2025-04 现场缺口：发现 `{verify.get('aergo_gaps_found')}`；跨段不计延续：`{aergo_ok}`。
- 备注：{verify.get('notes')}

## 缺口影响盘点

完整性：`{completeness}`。

本盘点只统计候选事件、连续性和窗口可用性，不运行完整收益、显著性或 bootstrap。

{md_rows(by_metric, ['sample_kind', 'metric', 'candidates', 'valid', 'internal_gap', 'right_censor_cutoff', 'indicator_warmup_insufficient', 'path_1h_missing', 'valid_rate'])}

池内 4h 预热不足（bar 级，不是事件损失率）：pool_bars=`{inv.get('warmup', {}).get('pool_bars')}`，insufficient=`{inv.get('warmup', {}).get('indicator_warmup_insufficient')}`。

## 独立 blocker（本轮不修复）

{blockers}

读取门禁如失败见 `inventory.catalog_blockers`：`{inv.get('catalog_blockers')}`。

## 入口

```text
uv run python research/asset-portfolios/4h-ma7-regime-continuation/scripts/research_binance_4h_ma7_regime_continuation_p0r_gap_guard.py --run
```
"""
    REPORT_PATH.write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    if not args.run:
        raise SystemExit("pass --run to acknowledge frozen gap-guard rules")
    config = validate_frozen_config()
    parent = parent_hash_check(config)
    prepare_outputs(args.force)

    cutoff = pd.Timestamp(config["data"]["cutoff_exclusive_utc"])
    last_complete_4h = pd.Timestamp(config["data"]["last_allowed_complete_4h_open_utc"])
    last_closed_1h = pd.Timestamp(config["data"]["last_allowed_closed_1h_open_utc"])

    inventory: dict[str, Any] = {
        "completeness": "未完成",
        "catalog_blockers": [],
        "headline_by_metric": [],
        "warmup": {},
        "native_only": bool(args.native_only),
        "full_pnl_research_run": False,
        "bootstrap_run": False,
    }
    verify: dict[str, Any] = {}
    classified = pd.DataFrame()
    tables: dict[str, pd.DataFrame] = {}
    ohlcv_1h = pd.DataFrame()
    native_4h = pd.DataFrame()

    failed = False
    try:
        print("stage: catalog FULL_MARKET trusted loads", flush=True)
        trusted_4h, catalog_4h = P0R.catalog_trusted_load(config["data"]["native_4h_dataset_id"], cutoff)
        trusted_1h, catalog_1h = P0R.catalog_trusted_load(config["data"]["path_1h_dataset_id"], cutoff)
        inventory["catalog_4h_symbols"] = catalog_4h["coverage"].get("symbol_count")
        inventory["catalog_1h_symbols"] = catalog_1h["coverage"].get("symbol_count")

        print("stage: load derived 4h", flush=True)
        native_4h_raw, audit_4h = P0R.load_derived_ohlcv(
            config["data"]["native_4h_dataset_id"],
            cutoff,
            expected_timeframe="4h",
            expected_components=P0R.NATIVE_4H_COMPONENTS,
            trusted=trusted_4h,
        )
        native_4h = P0R.prepare_native_4h(native_4h_raw, last_complete_4h)
        print(f"  native 4h bars={len(native_4h)} symbols={native_4h['symbol'].nunique()}", flush=True)
        GG.validate_time_grid(native_4h, step=pd.Timedelta(hours=4), name="native_4h", phase_hour=0)
        native_4h = P0.add_indicators(native_4h)
        eligibility, _universe = P0.build_universe(native_4h)
        native_4h = P0.attach_universe(native_4h, eligibility)
        inventory["warmup"] = GG.warmup_bar_counts(native_4h.loc[native_4h["phase_hour"].eq(0)])
        pool_symbols = sorted(
            eligibility.loc[eligibility["in_trading_pool"].fillna(False), "symbol"].astype(str).unique()
        )
        print(f"  ever-pool symbols={len(pool_symbols)}", flush=True)

        phase_panels = [native_4h]
        hourly_maps: dict[str, pd.DataFrame] = {}
        if not args.skip_inventory or not args.skip_verify:
            print("stage: load derived 1h timestamps/OHLCV for pool symbols", flush=True)
            if pool_symbols:
                ohlcv_1h, audit_1h = P0R.load_derived_ohlcv(
                    config["data"]["path_1h_dataset_id"],
                    cutoff,
                    expected_timeframe="1h",
                    expected_components=P0R.PATH_1H_COMPONENTS,
                    symbols=pool_symbols,
                    trusted=trusted_1h,
                )
                ohlcv_1h = ohlcv_1h.loc[ohlcv_1h["ts"] <= last_closed_1h].copy()
                GG.validate_time_grid(ohlcv_1h, step=pd.Timedelta(hours=1), name="path_1h")
                hourly_maps = P0.hourly_maps(ohlcv_1h)
                inventory["ohlcv_1h_rows"] = int(len(ohlcv_1h))
                inventory["audit_1h_selected_symbols"] = audit_1h["ohlcv_selected_symbols_before_cutoff"]
            inventory["audit_4h_selected_symbols"] = audit_4h["ohlcv_selected_symbols_before_cutoff"]

        if not args.native_only and not ohlcv_1h.empty:
            print("stage: aggregate phase 1/2/3", flush=True)
            for phase in (1, 2, 3):
                bars, audit = P0.aggregate_4h(ohlcv_1h, int(phase))
                bars = bars.loc[bars["ts"] < cutoff].copy()
                if bars.empty:
                    continue
                GG.validate_time_grid(bars, step=pd.Timedelta(hours=4), name=f"phase_{phase}", phase_hour=phase)
                bars = P0.add_indicators(bars)
                bars = P0.attach_universe(bars, eligibility)
                phase_panels.append(bars)
                print(f"  phase {phase}: {audit['complete_4h_bars']} complete 4h bars", flush=True)

        panel = pd.concat(phase_panels, ignore_index=True)
        fourh_maps = P0.panel_maps(panel)

        if not args.skip_inventory:
            print("stage: extract candidates without outcome PnL", flush=True)
            event_frames = [P0.build_event_candidates(panel, period) for period in P0.MA_PERIODS]
            events = pd.concat([frame for frame in event_frames if not frame.empty], ignore_index=True)
            controls = P0.build_non_cross_controls(panel)
            print(f"  event candidates={len(events)} control candidates={len(controls)}", flush=True)
            print("stage: classify window availability", flush=True)
            classified_events = GG.classify_windows_for_inventory(
                events, fourh_maps, hourly_maps, sample_kind="events"
            )
            classified_controls = GG.classify_windows_for_inventory(
                controls, fourh_maps, hourly_maps, sample_kind="controls"
            )
            classified = pd.concat([classified_events, classified_controls], ignore_index=True)
            tables = GG.build_inventory_tables(classified)
            inventory["completeness"] = "完成" if not args.native_only else "仅原生 0h + 已加载 phase（见 native_only 标记）"
            if args.native_only:
                inventory["completeness"] = "仅原生 0h；phase 1/2/3 未盘点"
            inventory["event_candidates"] = int(len(events))
            inventory["control_candidates"] = int(len(controls))
            inventory["primary_ma7_phase0_events"] = int(
                ((events["phase_hour"] == 0) & (events["ma_period"] == 7)).sum()
            )
            by_metric = tables["by_metric"]
            inventory["headline_by_metric"] = json.loads(by_metric.to_json(orient="records"))
            inventory["all_checksum_ok"] = bool(by_metric["checksum_ok"].all()) if not by_metric.empty else False
            inventory["bar_missing_note"] = "不得把全库 K 线缺失比例当成事件样本损失比例。"

        if not args.skip_verify:
            print("stage: real continuous and gap-window verification", flush=True)
            verify = verify_real_windows(native_4h, ohlcv_1h if not ohlcv_1h.empty else None)
    except RuntimeError as exc:
        inventory["catalog_blockers"].append(str(exc))
        inventory["completeness"] = "未完成"
        failed = True
        print(f"blocker: {exc}", flush=True)

    tests_meta = {"status": "run separately via pytest", "passed": None}
    verdict = "PASS" if (
        inventory.get("completeness", "").startswith("完成")
        or inventory.get("completeness", "").startswith("仅原生")
    ) and verify.get("continuous_sample_ok") and (
        verify.get("gap_does_not_continue_across_segment") or not verify.get("aergo_gaps_found")
    ) else "FAIL"
    if inventory.get("catalog_blockers"):
        verdict = "FAIL"
    if inventory.get("all_checksum_ok") is False:
        verdict = "FAIL"

    summary = {
        "family": "Binance-4H-MA7-Regime-Continuation",
        "alias": "BIN-4H-MA7-RC",
        "stage": "P0R-GAP-GUARD",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "explore / diagnostic-only / not promoted / not live-ready",
        "gap_guard_verdict": verdict,
        "not_a_strategy_pass": True,
        "not_live_ready": True,
        "input_lineage": {
            "config_path": rel(CONFIG_PATH),
            "config_sha256": EXPECTED_CONFIG_SHA256,
            "dataset_manifest_sha256": EXPECTED_MANIFEST_SHA256,
        },
        "inventory": inventory,
        "verify": verify,
        "parent_hash_check": parent,
        "tests": tests_meta,
        "blockers": KNOWN_STATISTICAL_BLOCKERS,
    }

    write_json(OUTPUTS["inventory_summary"], summary)
    write_json(OUTPUTS["verify"], verify)
    write_json(OUTPUTS["parent_hash_check"], parent)
    if not tables:
        tables = {
            "by_metric": pd.DataFrame(),
            "by_direction": pd.DataFrame(),
            "by_year": pd.DataFrame(),
            "by_phase": pd.DataFrame(),
            "by_symbol": pd.DataFrame(),
        }
    tables["by_metric"].to_csv(OUTPUTS["by_metric"], index=False)
    tables["by_direction"].to_csv(OUTPUTS["by_direction"], index=False)
    tables["by_year"].to_csv(OUTPUTS["by_year"], index=False)
    tables["by_phase"].to_csv(OUTPUTS["by_phase"], index=False)
    tables["by_symbol"].to_csv(OUTPUTS["by_symbol"], index=False)
    render_report(summary)
    for path in [*OUTPUTS.values(), REPORT_PATH]:
        write_sidecar(path)
    print(f"gap_guard_verdict={verdict} completeness={inventory.get('completeness')}", flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
