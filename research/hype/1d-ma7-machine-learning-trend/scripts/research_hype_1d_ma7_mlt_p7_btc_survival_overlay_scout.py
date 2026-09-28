"""SCOUT: frozen P7 survival overlay on BTCUSDT exact V7.1.

BTC was in the P7 training pool. Full-fit overlay on the donor window is
in-sample for the survival head. The post-2026-05-31 BTC days were not in
the frozen donor labels. Leave-one-out (no BTC in fit) is the cleaner
ranking check. This is not a P7 contract stage, not a new version, and
not live-ready.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/hype/1d-ma7-machine-learning-trend"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
P4_SCRIPT = FAMILY_DIR / "scripts/run_hype_1d_ma7_mlt_p4_v7_1_behavior_clone_residual.py"
P5_SCRIPT = FAMILY_DIR / "scripts/run_hype_1d_ma7_mlt_p5_opportunity_repair_lifecycle.py"
P6_SCRIPT = FAMILY_DIR / "scripts/run_hype_1d_ma7_mlt_p6_v7_anchor_three_head_lifecycle.py"
P7_SCRIPT = FAMILY_DIR / "scripts/run_hype_1d_ma7_mlt_p7_cross_asset_survival_overlay.py"

RUN_DATE = "2026-08-31"
STEM = f"hype_1d_ma7_mlt_p7_btc_survival_overlay_scout_{RUN_DATE}"
DONOR_ROWS = (
    ARTIFACT_DIR
    / "hype_1d_ma7_mlt_p7_cross_asset_survival_overlay_2026-08-28_donor_survival_rows.csv"
)
TRAIN_TERMINAL = pd.Timestamp("2026-05-31T00:00:00Z")
TRAIN_LAST_FEATURE_DAY = pd.Timestamp("2026-05-30T00:00:00Z")
LAKE_TERMINAL = pd.Timestamp("2026-08-28T00:00:00Z")
COST_NOTE = "Binance USD-M: fee 0.001 + 4 bps adverse slippage per fill; actual funding"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256(path)}  {path.name}\n", encoding="utf-8"
    )


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    skip = {"per_trade_returns"}
    return {key: sanitize(value) for key, value in metrics.items() if key not in skip}


def slim_trades(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keep = (
        "side",
        "entry_ts",
        "exit_ts",
        "exit_reason",
        "net_return",
        "source",
        "entry_price",
        "exit_price",
    )
    rows = []
    for trade in trades:
        row = {key: trade.get(key) for key in keep if key in trade}
        reason = str(trade.get("exit_reason", ""))
        row["extended"] = "p7_dynamic_survival" in reason
        rows.append(row)
    return rows


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def attach_btc(frozen: Any, donor: Any) -> Any:
    return replace(
        frozen,
        market=donor.market,
        short_config=replace(frozen.short_config, cooldown_days=3),
    )


def day_index(context: Any, day: pd.Timestamp) -> int:
    stamps = pd.DatetimeIndex(pd.to_datetime(context.book.ts, utc=True))
    matches = [i for i, ts in enumerate(stamps) if ts == day]
    if len(matches) != 1:
        raise RuntimeError(f"expected one bar at {day.isoformat()}, got {matches}")
    return matches[0]


def price_path_pct(context: Any, left: int, right: int) -> float:
    open0 = float(context.book.open[left])
    close1 = float(context.book.close[right - 1])
    return (close1 / open0 - 1.0) * 100.0


def run_window(
    *,
    p4: Any,
    p5: Any,
    p6: Any,
    p7: Any,
    diag: Any,
    v6: Any,
    engine: Any,
    context: Any,
    model: Any,
    features: list[str],
    left: int,
    right: int,
) -> dict[str, Any]:
    frame, episodes, _ = p6.build_frame(p5, p4, engine, context)
    teacher = p4.run_teacher(diag, v6, engine, context, left, right)
    bundle = p7.overlay_bundle(
        p4,
        p5,
        p6,
        v6,
        context,
        frame,
        episodes,
        list(teacher.result.raw.trades),
        model,
        features,
        left,
        right,
    )
    if int(bundle["metrics"]["trades"]) != int(bundle["teacher_metrics"]["trades"]):
        raise RuntimeError("BTC overlay changed V7.1 trade count")
    start = pd.Timestamp(context.book.ts[left])
    last = pd.Timestamp(context.book.ts[right - 1])
    decisions = bundle["decisions"]
    extended_rows = []
    if not decisions.empty:
        for row in decisions.to_dict("records"):
            if not bool(row.get("extended")):
                continue
            extended_rows.append(
                {
                    "entry_ts": row.get("entry_ts"),
                    "v7_1_exit_ts": row.get("teacher_exit_ts") or row.get("v7_1_exit_ts"),
                    "p7_exit_ts": row.get("p7_exit_ts") or row.get("exit_ts"),
                    "exit_reason": row.get("p7_exit_reason") or row.get("exit_reason"),
                    "entry_probability": row.get("entry_probability"),
                }
            )
    return {
        "window": {
            "left": left,
            "right": right,
            "days": right - left,
            "start": start.isoformat(),
            "last_feature_day": last.isoformat(),
            "terminal": pd.Timestamp(context.book.terminal_ts).isoformat()
            if right == context.book.count
            else pd.Timestamp(context.book.ts[right]).isoformat(),
        },
        "p7": compact_metrics(bundle["metrics"]),
        "v7_1": compact_metrics(bundle["teacher_metrics"]),
        "head_metrics": sanitize(bundle["head_metrics"]),
        "extended_trades": int(bundle["extended_trades"]),
        "p7_capture": sanitize(bundle["capture"]),
        "v7_1_capture": sanitize(bundle["teacher_capture"]),
        "price_path_pct": price_path_pct(context, left, right),
        "trades": slim_trades(bundle["trades"]),
        "v7_1_trades": slim_trades(bundle["teacher_trades"]),
        "extended_detail": extended_rows,
    }


def main() -> None:
    if not DONOR_ROWS.exists():
        raise RuntimeError(f"missing frozen donor rows: {DONOR_ROWS}")
    p4 = load_module(P4_SCRIPT, "hype_p7_btc_scout_p4")
    p5 = load_module(P5_SCRIPT, "hype_p7_btc_scout_p5")
    p6 = load_module(P6_SCRIPT, "hype_p7_btc_scout_p6")
    p7 = load_module(P7_SCRIPT, "hype_p7_btc_scout_p7")
    diag = p4.load_module(p4.DIAGNOSTIC, "hype_p7_btc_scout_diag")
    v6 = diag.load_module(diag.V6_ABLATION_PATH, "hype_p7_btc_scout_v6")
    engine = diag.load_module(diag.ENGINE_PATH, "hype_p7_btc_scout_engine")
    adapter = diag.load_module(diag.ADAPTER_PATH, "hype_p7_btc_scout_adapter")
    frozen = adapter.load_context()
    original = frozen.original_harness
    orig_engine, base, search = original.modules()
    parent = base.load_parent()
    features = p7.survival_features(p5, p6)
    donor_pool = pd.read_csv(DONOR_ROWS)
    p7.assert_donor_pool(donor_pool)
    full_fit = p7.complete_rows_by_ts(donor_pool)
    loo_fit = full_fit.loc[full_fit["asset"].astype(str) != "BTCUSDT"].copy()
    if loo_fit.empty or loo_fit["asset"].nunique() != 3:
        raise RuntimeError("leave-one-out donor pool drifted")
    frozen_model = p7.fit_model(full_fit, features)
    loo_model = p7.fit_model(loo_fit, features)

    log("loading BTC donor context through P7 train terminal")
    train_donor = p7.load_donor_context(
        original,
        orig_engine,
        base,
        search,
        parent,
        "BTCUSDT",
        p7.DONOR_SPECS["BTCUSDT"],
        TRAIN_TERMINAL,
    )
    train_ctx = attach_btc(frozen, train_donor)
    if pd.Timestamp(train_ctx.book.ts[-1]) != TRAIN_LAST_FEATURE_DAY:
        raise RuntimeError("BTC train last feature day drifted")

    log("loading BTC donor context through last complete lake day")
    lake_donor = p7.load_donor_context(
        original,
        orig_engine,
        base,
        search,
        parent,
        "BTCUSDT",
        p7.DONOR_SPECS["BTCUSDT"],
        LAKE_TERMINAL,
    )
    lake_ctx = attach_btc(frozen, lake_donor)
    train_left = 0
    train_right = int(train_ctx.book.count)
    val_left = day_index(lake_ctx, TRAIN_TERMINAL)
    lake_right = int(lake_ctx.book.count)
    if pd.Timestamp(lake_ctx.book.ts[val_left - 1]) != TRAIN_LAST_FEATURE_DAY:
        raise RuntimeError("BTC validation boundary drifted")

    log("running frozen P7 overlay on BTC train window")
    donor_window = run_window(
        p4=p4,
        p5=p5,
        p6=p6,
        p7=p7,
        diag=diag,
        v6=v6,
        engine=engine,
        context=train_ctx,
        model=frozen_model,
        features=features,
        left=train_left,
        right=train_right,
    )
    log("running leave-one-out overlay on BTC train window")
    loo_window = run_window(
        p4=p4,
        p5=p5,
        p6=p6,
        p7=p7,
        diag=diag,
        v6=v6,
        engine=engine,
        context=train_ctx,
        model=loo_model,
        features=features,
        left=train_left,
        right=train_right,
    )
    log("running frozen P7 overlay on BTC post-train window")
    post_window = run_window(
        p4=p4,
        p5=p5,
        p6=p6,
        p7=p7,
        diag=diag,
        v6=v6,
        engine=engine,
        context=lake_ctx,
        model=frozen_model,
        features=features,
        left=val_left,
        right=lake_right,
    )
    log("running frozen P7 overlay on BTC continuous full sample")
    full_window = run_window(
        p4=p4,
        p5=p5,
        p6=p6,
        p7=p7,
        diag=diag,
        v6=v6,
        engine=engine,
        context=lake_ctx,
        model=frozen_model,
        features=features,
        left=0,
        right=lake_right,
    )
    log("running recent slices on BTC full sample")
    lake_frame, _, _ = p6.build_frame(p5, p4, engine, lake_ctx)
    slices = p7.recent_slices(
        p4,
        p6,
        diag,
        v6,
        engine,
        lake_ctx,
        frozen_model,
        features,
        lake_frame,
        0,
        lake_right,
    )
    slice_out = {
        label: {
            "available_days": item["available_days"],
            "p7": compact_metrics(item["p7"]),
            "v7_1": compact_metrics(item["v7_1"]),
        }
        for label, item in slices.items()
    }

    summary = {
        "family": "HYPE-1D-MA7-Machine-Learning-Trend",
        "experiment": "P7_BTC_SURVIVAL_OVERLAY_SCOUT",
        "run_date": RUN_DATE,
        "status": "diagnostic-only / not promoted / not live-ready",
        "note": (
            "Frozen P7 ExtraTrees applied to BTCUSDT exact V7.1. "
            "BTC was in the donor training pool. Not P7 --stage validate."
        ),
        "cost_model": COST_NOTE,
        "btc_in_training_pool": True,
        "windows": {
            "donor_train_in_sample_for_btc": {
                **{k: v for k, v in donor_window.items() if k not in {"trades", "v7_1_trades"}},
                "contamination": "BTC labels were in the frozen full fit",
            },
            "donor_train_leave_one_out": {
                **{k: v for k, v in loo_window.items() if k not in {"trades", "v7_1_trades"}},
                "contamination": "fit on ETH/BNB/SOL only; BTC overlay is asset-OOS",
            },
            "post_train_isolated": {
                **{k: v for k, v in post_window.items() if k not in {"trades", "v7_1_trades"}},
                "contamination": "time-OOS vs frozen donor cutoff; BTC still seen in earlier labels",
            },
            "continuous_full": {
                **{k: v for k, v in full_window.items() if k not in {"trades", "v7_1_trades"}},
                "contamination": "mixes in-sample donor window and time-OOS tail",
            },
        },
        "recent_slices_flat_start": slice_out,
        "sources": {
            "donor_survival_rows": {
                "path": str(DONOR_ROWS.relative_to(ROOT)),
                "sha256": sha256(DONOR_ROWS),
            },
            "btc_klines": train_donor.market.audit["klines"],
            "btc_klines_sha256": train_donor.market.audit["klines_sha256"],
            "script": str(Path(__file__).relative_to(ROOT)),
        },
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = ARTIFACT_DIR / f"{STEM}_summary.json"
    summary_path.write_text(
        json.dumps(sanitize(summary), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    write_sidecar(summary_path)
    for name, payload in {
        f"{STEM}_donor_train_p7_trades.csv": donor_window["trades"],
        f"{STEM}_donor_train_v7_1_trades.csv": donor_window["v7_1_trades"],
        f"{STEM}_loo_train_p7_trades.csv": loo_window["trades"],
        f"{STEM}_post_train_p7_trades.csv": post_window["trades"],
        f"{STEM}_post_train_v7_1_trades.csv": post_window["v7_1_trades"],
        f"{STEM}_full_p7_trades.csv": full_window["trades"],
        f"{STEM}_full_v7_1_trades.csv": full_window["v7_1_trades"],
    }.items():
        path = ARTIFACT_DIR / name
        pd.DataFrame(payload).to_csv(path, index=False)
        write_sidecar(path)
    print(json.dumps(sanitize(summary["windows"]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
