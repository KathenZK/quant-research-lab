"""Render P7/V7.1 paths: 365-day train plus lake-end validation."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import UTC, datetime
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
SLICE_SCRIPT = FAMILY_DIR / "scripts/audit_hype_1d_ma7_mlt_p4_recent_slices.py"
STEM = "hype_1d_ma7_mlt_p7_cross_asset_survival_overlay_2026-08-28"

SUMMARY = ARTIFACT_DIR / f"{STEM}_development_summary.json"
DEVELOPMENT_MANIFEST = ARTIFACT_DIR / f"{STEM}_development_manifest.json"
DONOR_ROWS = ARTIFACT_DIR / f"{STEM}_donor_survival_rows.csv"
LAKE_SUMMARY = ARTIFACT_DIR / f"{STEM}_lake_validation_summary.json"
LAKE_CONTINUOUS_P7 = ARTIFACT_DIR / f"{STEM}_lake_continuous_trades.csv"
LAKE_CONTINUOUS_V7 = ARTIFACT_DIR / f"{STEM}_lake_continuous_v7_1_trades.csv"
LAKE_VALIDATION_P7 = ARTIFACT_DIR / f"{STEM}_lake_validation_trades.csv"
LAKE_VALIDATION_V7 = ARTIFACT_DIR / f"{STEM}_lake_validation_v7_1_trades.csv"
LAKE_SCORES = ARTIFACT_DIR / f"{STEM}_lake_continuous_scores.csv"

OUTPUT_PATH = ARTIFACT_DIR / f"{STEM}_v7_1_training_trade_paths.html"
MANIFEST_PATH = ARTIFACT_DIR / f"{STEM}_v7_1_training_trade_paths_manifest.json"

TRAIN_DAYS = 365
DEVELOPMENT_DAYS = 285
TRAIN_LAST_DAY = pd.Timestamp("2026-05-30T00:00:00Z")
VAL_START = pd.Timestamp("2026-05-31T00:00:00Z")
LAKE_CUTOFF = pd.Timestamp("2100-01-01T00:00:00Z")
STRATEGIES = {
    "P7_FULL": {
        "label": "P7 连续覆盖",
        "code": "P7-C",
        "color": "#e6a15c",
        "dash": [9, 5],
        "group": "full",
    },
    "V7_FULL": {
        "label": "exact V7.1 连续",
        "code": "V7-C",
        "color": "#69b7c9",
        "dash": [],
        "group": "full",
    },
    "P7_VAL": {
        "label": "P7 验证窗（空仓重开）",
        "code": "P7-V",
        "color": "#c58ad9",
        "dash": [3, 4],
        "group": "validation",
    },
    "V7_VAL": {
        "label": "V7.1 验证窗（空仓重开）",
        "code": "V7-V",
        "color": "#9ccdd7",
        "dash": [2, 4],
        "group": "validation",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


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


def verify_sidecar(path: Path) -> None:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.exists():
        raise RuntimeError(f"missing sidecar: {sidecar}")
    if sidecar.read_text(encoding="utf-8").split()[0] != sha256(path):
        raise RuntimeError(f"source artifact hash mismatch: {path}")


def timestamp_ms(value: Any) -> int:
    return int(pd.Timestamp(value).timestamp() * 1_000)


def finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def load_trades(path: Path) -> list[dict[str, Any]]:
    return pd.read_csv(path).to_dict("records")


def daily_equity(
    slice_audit: Any,
    p4: Any,
    v6: Any,
    context: Any,
    trades: list[dict[str, Any]],
    start_index: int,
) -> list[dict[str, Any]]:
    observations, _, terminal_equity = slice_audit.equity_observations(
        p4, v6, context, trades
    )
    last_at_timestamp: dict[pd.Timestamp, float] = {}
    for ts, value in observations:
        last_at_timestamp[pd.Timestamp(ts)] = float(value)
    timestamps = [pd.Timestamp(ts) for ts in context.book.ts[start_index:]]
    timestamps.append(pd.Timestamp(context.book.terminal_ts))
    rows = [{"t": timestamp_ms(ts), "v": last_at_timestamp[ts]} for ts in timestamps]
    if not math.isclose(rows[-1]["v"], terminal_equity, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("daily equity terminal parity failed")
    return rows


def trade_rows(
    strategy: str,
    segment: str,
    trades: list[dict[str, Any]],
    returns: list[float],
) -> list[dict[str, Any]]:
    if len(trades) != len(returns):
        raise RuntimeError(f"{strategy} trade return parity failed")
    rows: list[dict[str, Any]] = []
    for order, (trade, net_return) in enumerate(zip(trades, returns, strict=True), start=1):
        source = str(trade.get("source", ""))
        if source == "nan" or source == "":
            source = "V7.1 core"
        exit_reason = str(trade["exit_reason"])
        extended = "p7_dynamic_survival" in exit_reason
        rows.append(
            {
                "id": f"{STRATEGIES[strategy]['code']}-{order:02d}",
                "strategy": strategy,
                "strategyLabel": STRATEGIES[strategy]["label"],
                "segment": segment,
                "side": str(trade["side"]),
                "entryT": timestamp_ms(trade["entry_ts"]),
                "exitT": timestamp_ms(trade["exit_ts"]),
                "entry": float(trade["entry_price"]),
                "exit": float(trade["exit_price"]),
                "barsHeld": int(trade.get("bars_held", 0)),
                "netReturnPct": float(net_return) * 100.0,
                "exitReason": exit_reason,
                "entryProbability": finite_or_none(trade.get("entry_probability")),
                "source": source,
                "extended": extended,
            }
        )
    return rows


def episode_rows_from_frames(p7_frame: pd.DataFrame, v7_frame: pd.DataFrame) -> list[dict[str, Any]]:
    p7_frame = p7_frame.copy()
    v7_frame = v7_frame.copy()
    p7_frame["strategy"] = "P7_TRANSFER"
    v7_frame["strategy"] = "V7.1"
    frame = pd.concat([p7_frame, v7_frame], ignore_index=True)
    rows: list[dict[str, Any]] = []
    for episode_id, group in frame.groupby("episode_id", sort=False):
        lookup = group.set_index("strategy")
        if "P7_TRANSFER" not in lookup.index or "V7.1" not in lookup.index:
            raise RuntimeError(f"episode strategy pair missing: {episode_id}")
        p7 = lookup.loc["P7_TRANSFER"]
        v7 = lookup.loc["V7.1"]
        p7_capture = float(p7["capture_ratio"])
        v7_capture = float(v7["capture_ratio"])
        if p7_capture > 0 and v7_capture == 0:
            classification = "P7_NEW_CAPTURE"
        elif p7_capture > v7_capture:
            classification = "P7_MORE"
        elif p7_capture < v7_capture:
            classification = "V7_MORE"
        else:
            classification = "SAME"
        rows.append(
            {
                "id": str(episode_id),
                "side": int(p7["side"]),
                "startT": timestamp_ms(p7["start_ts"]),
                "endT": timestamp_ms(p7["end_ts"]) + 86_400_000,
                "durationDays": int(p7["duration_days"]),
                "p7Days": int(p7["covered_days"]),
                "v7Days": int(v7["covered_days"]),
                "p7Capture": p7_capture,
                "v7Capture": v7_capture,
                "classification": classification,
            }
        )
    return rows


def score_lookup_frame(frame: pd.DataFrame) -> dict[int, float]:
    return {
        int(row["index"]): float(row["probability"])
        for row in frame.to_dict("records")
        if math.isfinite(float(row["probability"]))
    }


def write_retained(path: Path, payload: Any) -> None:
    if isinstance(payload, pd.DataFrame):
        payload.to_csv(path, index=False)
    else:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256(path)}  {path.name}\n", encoding="utf-8"
    )


def load_lake_context(p4: Any) -> tuple[Any, Any, Any, Any]:
    diag = p4.load_module(p4.DIAGNOSTIC, "hype_p7_path_diag")
    v6 = diag.load_module(diag.V6_ABLATION_PATH, "hype_p7_path_v6")
    engine = diag.load_module(diag.ENGINE_PATH, "hype_p7_path_engine")
    adapter = diag.load_module(diag.ADAPTER_PATH, "hype_p7_path_adapter")
    frozen = adapter.load_context()
    original = frozen.original_harness
    original.HOURLY_CUTOFF = LAKE_CUTOFF
    original.FUNDING_CUTOFF = LAKE_CUTOFF
    context = replace(
        frozen,
        market=original.load_market(0),
        short_config=replace(frozen.short_config, cooldown_days=3),
    )
    if context.book.count <= TRAIN_DAYS:
        raise RuntimeError("lake context did not extend past the 365-day training window")
    if pd.Timestamp(context.book.ts[TRAIN_DAYS - 1]) != TRAIN_LAST_DAY:
        raise RuntimeError("training last feature day drift")
    if pd.Timestamp(context.book.ts[TRAIN_DAYS]) != VAL_START:
        raise RuntimeError("validation start drift")
    return diag, v6, engine, context


def build_payload() -> tuple[dict[str, Any], dict[str, Any]]:
    sources = (SUMMARY, DEVELOPMENT_MANIFEST, DONOR_ROWS)
    for path in sources:
        verify_sidecar(path)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    frozen = json.loads(DEVELOPMENT_MANIFEST.read_text(encoding="utf-8"))
    if frozen["holdout_permitted"] is not False:
        raise RuntimeError("P7 contract validate remains locked; this chart is a visualization overlay")

    p4 = load_module(P4_SCRIPT, "hype_p7_trade_path_p4")
    p5 = load_module(P5_SCRIPT, "hype_p7_trade_path_p5")
    p6 = load_module(P6_SCRIPT, "hype_p7_trade_path_p6")
    p7 = load_module(P7_SCRIPT, "hype_p7_trade_path_p7")
    slice_audit = load_module(SLICE_SCRIPT, "hype_p7_trade_path_slices")
    diag, v6, engine, context = load_lake_context(p4)
    right = int(context.book.count)
    features = p7.survival_features(p5, p6)
    donor_pool = pd.read_csv(DONOR_ROWS)
    model = p7.fit_model(p7.complete_rows_by_ts(donor_pool), features)
    frame, episodes, _ = p6.build_frame(p5, p4, engine, context)
    teacher_full = p4.run_teacher(diag, v6, engine, context, 0, right)
    teacher_val = p4.run_teacher(diag, v6, engine, context, TRAIN_DAYS, right)
    continuous = p7.overlay_bundle(
        p4,
        p5,
        p6,
        v6,
        context,
        frame,
        episodes,
        list(teacher_full.result.raw.trades),
        model,
        features,
        0,
        right,
    )
    isolated = p7.overlay_bundle(
        p4,
        p5,
        p6,
        v6,
        context,
        frame,
        episodes,
        list(teacher_val.result.raw.trades),
        model,
        features,
        TRAIN_DAYS,
        right,
    )
    if int(continuous["metrics"]["trades"]) != int(continuous["teacher_metrics"]["trades"]):
        raise RuntimeError("continuous overlay changed V7.1 trade count")
    if int(isolated["metrics"]["trades"]) != int(isolated["teacher_metrics"]["trades"]):
        raise RuntimeError("validation overlay changed V7.1 trade count")

    val_start = pd.Timestamp(context.book.ts[TRAIN_DAYS])
    continuous_val_entries = [
        trade
        for trade in continuous["teacher_trades"]
        if pd.Timestamp(trade["entry_ts"]) >= val_start
    ]
    lake_summary = {
        "family": "HYPE-1D-MA7-Machine-Learning-Trend",
        "experiment": "P7_CROSS_ASSET_SURVIVAL_OVERLAY",
        "note": "user-requested lake validation visualization; not P7 contract --stage validate",
        "p7_gate_still": "DEVELOPMENT_FAILED_HOLDOUT_LOCKED",
        "holdout_permitted": False,
        "visualization_read": True,
        "window": {
            "train_days": TRAIN_DAYS,
            "train_last_feature_day": pd.Timestamp(context.book.ts[TRAIN_DAYS - 1]).isoformat(),
            "validation_start": val_start.isoformat(),
            "validation_last_feature_day": pd.Timestamp(context.book.ts[-1]).isoformat(),
            "terminal": pd.Timestamp(context.book.terminal_ts).isoformat(),
            "days": right,
            "validation_days": right - TRAIN_DAYS,
            "hourly_end": str(context.market.audit.get("hourly_end")),
            "funding_end": str(context.market.audit.get("funding_end")),
        },
        "continuous": {
            "p7": continuous["metrics"],
            "v7_1": continuous["teacher_metrics"],
            "extended_trades": continuous["extended_trades"],
            "validation_entries": len(continuous_val_entries),
        },
        "isolated_validation_window": {
            "p7": isolated["metrics"],
            "v7_1": isolated["teacher_metrics"],
            "extended_trades": isolated["extended_trades"],
            "trades": int(isolated["metrics"]["trades"]),
        },
    }
    write_retained(LAKE_SUMMARY, p7.sanitize(lake_summary))
    write_retained(LAKE_CONTINUOUS_P7, pd.DataFrame(continuous["trades"]))
    write_retained(LAKE_CONTINUOUS_V7, pd.DataFrame(continuous["teacher_trades"]))
    write_retained(LAKE_VALIDATION_P7, pd.DataFrame(isolated["trades"]))
    write_retained(LAKE_VALIDATION_V7, pd.DataFrame(isolated["teacher_trades"]))
    write_retained(LAKE_SCORES, continuous["scores"])

    trade_sets = {
        "P7_FULL": continuous["trades"],
        "V7_FULL": continuous["teacher_trades"],
        "P7_VAL": isolated["trades"],
        "V7_VAL": isolated["teacher_trades"],
    }
    replays = {
        "P7_FULL": continuous["metrics"],
        "V7_FULL": continuous["teacher_metrics"],
        "P7_VAL": isolated["metrics"],
        "V7_VAL": isolated["teacher_metrics"],
    }
    scores = score_lookup_frame(continuous["scores"])
    candles: list[dict[str, Any]] = []
    for row in frame.to_dict("records"):
        index = int(row["index"])
        candles.append(
            {
                "t": timestamp_ms(row["ts"]),
                "o": float(row["open"]),
                "h": float(row["high"]),
                "l": float(row["low"]),
                "c": float(row["close"]),
                "ma7": finite_or_none(row["ma7"]),
                "slopeAtr": finite_or_none(row["slope1_atr"]),
                "rootSide": int(row["root_side"]),
                "fullSurvival": finite_or_none(scores.get(index)),
            }
        )

    trades: list[dict[str, Any]] = []
    for strategy in STRATEGIES:
        trades.extend(
            trade_rows(
                strategy,
                STRATEGIES[strategy]["group"],
                trade_sets[strategy],
                replays[strategy]["per_trade_returns"],
            )
        )
    episode_table = episode_rows_from_frames(
        continuous["capture_rows"], continuous["teacher_capture_rows"]
    )
    equity = {
        "P7_FULL": daily_equity(slice_audit, p4, v6, context, trade_sets["P7_FULL"], 0),
        "V7_FULL": daily_equity(slice_audit, p4, v6, context, trade_sets["V7_FULL"], 0),
        "P7_VAL": daily_equity(
            slice_audit, p4, v6, context, trade_sets["P7_VAL"], TRAIN_DAYS
        ),
        "V7_VAL": daily_equity(
            slice_audit, p4, v6, context, trade_sets["V7_VAL"], TRAIN_DAYS
        ),
    }

    capture = {
        "P7_FULL": continuous["capture"],
        "V7_FULL": continuous["teacher_capture"],
        "P7_VAL": isolated["capture"],
        "V7_VAL": isolated["teacher_capture"],
    }
    metrics: dict[str, Any] = {}
    for strategy in STRATEGIES:
        metrics[strategy] = {
            **{
                key: replays[strategy][key]
                for key in (
                    "net_return_pct",
                    "chronological_1h_mdd_pct",
                    "trades",
                    "win_rate",
                    "profit_factor",
                    "cost_pct_initial",
                    "exposure_days",
                )
            },
            **capture[strategy],
        }
        count = int(metrics[strategy]["trades"])
        metrics[strategy]["average_hold_days"] = (
            float(metrics[strategy]["exposure_days"]) / count if count else 0.0
        )

    payload = {
        "title": "前365日是训练，365日之后到湖末日才是验证",
        "subtitle": "HYPEUSDT · 1D · 训练 2025-05-31→2026-05-30 · 验证 2026-05-31→数据湖最后完整日",
        "status": (
            "P7 合同仍是 DEVELOPMENT_FAILED_HOLDOUT_LOCKED；本图按要求展开验证期，不改阈值、不重训"
        ),
        "generatedAt": datetime.now(UTC).isoformat(),
        "window": {
            "start": pd.Timestamp(context.book.ts[0]).isoformat(),
            "trainLastDay": pd.Timestamp(context.book.ts[TRAIN_DAYS - 1]).isoformat(),
            "valStart": val_start.isoformat(),
            "valBoundaryT": timestamp_ms(val_start),
            "developmentBoundary": pd.Timestamp(context.book.ts[DEVELOPMENT_DAYS]).isoformat(),
            "developmentBoundaryT": timestamp_ms(context.book.ts[DEVELOPMENT_DAYS]),
            "lastDay": pd.Timestamp(context.book.ts[-1]).isoformat(),
            "terminal": pd.Timestamp(context.book.terminal_ts).isoformat(),
            "terminalT": timestamp_ms(context.book.terminal_ts),
            "days": right,
            "trainDays": TRAIN_DAYS,
            "validationDays": right - TRAIN_DAYS,
            "developmentDays": DEVELOPMENT_DAYS,
            "continuousValidationEntries": len(continuous_val_entries),
            "isolatedValidationTrades": int(isolated["metrics"]["trades"]),
        },
        "strategies": STRATEGIES,
        "metrics": metrics,
        "oof": {
            "auc": summary["oof"]["auc"],
            "rows": summary["oof"]["rows"],
            "byAsset": {
                asset: {"auc": values["auc"], "rows": values["rows"]}
                for asset, values in summary["oof"]["by_asset"].items()
            },
        },
        "candles": candles,
        "equity": equity,
        "trades": trades,
        "episodes": episode_table,
    }
    manifest = {
        "schema": "hype-1d-ma7-mlt-p7-v7-1-train-validation-trade-path-v2",
        "generated_at": payload["generatedAt"],
        "renderer": Path(__file__).name,
        "holdout_read": True,
        "visualization_only": True,
        "p7_contract_validate_ran": False,
        "sources": {path.name: sha256(path) for path in sources},
        "window": payload["window"],
        "candles": len(candles),
        "ma7_points": sum(row["ma7"] is not None for row in candles),
        "full_probability_points": {
            "survival": sum(row["fullSurvival"] is not None for row in candles)
        },
        "equity_points": {key: len(value) for key, value in equity.items()},
        "trades_by_strategy": {
            key: sum(row["strategy"] == key for row in trades) for key in STRATEGIES
        },
        "extended_trades": sum(
            row["extended"] for row in trades if row["strategy"] == "P7_FULL"
        ),
        "episodes": len(episode_table),
        "new_captures": sum(row["classification"] == "P7_NEW_CAPTURE" for row in episode_table),
        "line_render_count": len(trades),
        "external_dependencies": 0,
        "retained": {
            path.name: sha256(path)
            for path in (
                LAKE_SUMMARY,
                LAKE_CONTINUOUS_P7,
                LAKE_CONTINUOUS_V7,
                LAKE_VALIDATION_P7,
                LAKE_VALIDATION_V7,
                LAKE_SCORES,
            )
        },
    }
    return p7.sanitize(payload), p7.sanitize(manifest)


HTML_TEMPLATE = r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>P7 vs V7.1 训练+验证交易路径</title><style>
:root{color-scheme:dark;--bg:#0b0f12;--panel:#11171b;--panel2:#151d22;--line:#2a353b;--grid:#202a30;--text:#e8edef;--muted:#89979e;--up:#72b29b;--down:#c87878;--ma:#d7b869;--v7:#69b7c9;--p6:#e6a15c;--ic:#c58ad9;--accent:#d7b869}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--text);font:13px/1.48 Geist,Satoshi,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.shell{max-width:1880px;margin:auto;padding:24px}.hero{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(360px,.85fr);gap:42px;align-items:end;padding:20px 0 24px;border-bottom:1px solid var(--line)}.eyebrow{color:var(--accent);font:600 11px/1.2 "Geist Mono",ui-monospace,monospace;letter-spacing:.16em}.hero h1{max-width:980px;margin:11px 0 10px;font-size:clamp(30px,4vw,58px);line-height:.98;letter-spacing:-.045em;font-weight:620}.subtitle,.status,.note{color:var(--muted)}.verdict{border-left:2px solid var(--down);padding:6px 0 6px 18px}.verdict b{display:block;font-size:18px;margin-bottom:6px}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--line);margin:28px 0 18px}.metric-group{background:var(--panel);padding:17px 18px}.metric-group h2{font-size:14px;margin:0 0 13px}.metric-grid{display:grid;grid-template-columns:1.1fr repeat(4,1fr)}.metric-grid>div{border-left:1px solid var(--line);padding:4px 12px}.metric-grid>div:first-child{border-left:0}.metric-grid span{display:block;color:var(--muted);font-size:11px}.metric-grid b{display:block;margin-top:6px;font:550 16px "Geist Mono",monospace}.p6c{color:var(--p6)}.v7c{color:var(--v7)}.icc{color:var(--ic)}.positive{color:var(--up)}.negative{color:var(--down)}.diagnosis{display:grid;grid-template-columns:1.25fr .75fr;gap:1px;background:var(--line);margin-bottom:18px}.diagnosis>div{background:var(--panel);padding:18px 20px}.diagnosis h2{font-size:15px;margin:0 0 9px}.diagnosis p{margin:0;color:#c5ced2}.equation{font:500 14px/1.65 "Geist Mono",monospace;color:var(--accent)}.toolbar{position:sticky;top:0;z-index:3;display:flex;flex-wrap:wrap;align-items:center;gap:8px 15px;padding:10px 12px;border:1px solid var(--line);background:rgba(17,23,27,.94);backdrop-filter:blur(14px)}button{color:var(--text);border:1px solid #394850;background:#172127;padding:7px 11px;cursor:pointer;font:12px "Geist Mono",monospace}button:hover{border-color:#64757e}label{color:var(--muted);user-select:none;font:12px "Geist Mono",monospace}input{vertical-align:-2px}.chart{border:1px solid var(--line);border-top:0;background:var(--panel);overflow:hidden}canvas{width:100%;display:block}#priceChart{height:610px;cursor:crosshair}#probChart{height:220px;border-top:1px solid var(--line)}#equityFull{height:230px;border-top:1px solid var(--line)}#equityIc{height:190px;border-top:1px solid var(--line)}.chart-note{padding:10px 12px;border:1px solid var(--line);border-top:0;color:var(--muted);font:11px "Geist Mono",monospace}.sections{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);gap:18px;margin-top:24px}.table-wrap{max-height:680px;overflow:auto;border:1px solid var(--line);background:var(--panel)}.table-head{position:sticky;top:0;z-index:2;padding:14px 16px;background:var(--panel2);border-bottom:1px solid var(--line)}.table-head h2{font-size:14px;margin:0}.table-head p{color:var(--muted);font-size:11px;margin:4px 0 0}table{width:100%;border-collapse:collapse;min-width:900px;font:11px "Geist Mono",monospace}th,td{padding:9px 10px;border-bottom:1px solid var(--grid);text-align:right;white-space:nowrap}th{color:var(--muted);background:var(--panel2);position:sticky;top:64px;z-index:1;font-weight:500}th:nth-child(-n+4),td:nth-child(-n+4),th:last-child,td:last-child{text-align:left}tbody tr{cursor:pointer}tbody tr:hover,tbody tr.active{background:#1b272d}tbody tr.new{background:rgba(215,184,105,.07)}.badge{padding:2px 6px;border:1px solid #6f6040;color:#e3c67d}.tooltip{position:fixed;z-index:8;display:none;pointer-events:none;max-width:600px;padding:11px 13px;border:1px solid #4b5c64;background:rgba(11,15,18,.97);white-space:pre-line;font:11px/1.55 "Geist Mono",monospace}@media(max-width:1100px){.shell{padding:12px}.hero,.metrics,.diagnosis,.sections{grid-template-columns:1fr}.metric-grid{grid-template-columns:1fr 1fr}.metric-grid>div{border-left:0;border-top:1px solid var(--line);padding:9px}#priceChart{height:500px}}@media(max-width:720px){.hero h1{font-size:34px}.toolbar{position:static}}
</style></head><body><main class="shell"><section class="hero"><div><div class="eyebrow">HYPE · MA7 CROSS-ASSET SURVIVAL OVERLAY</div><h1 id="title"></h1><div id="subtitle" class="subtitle"></div><div id="status" class="status"></div></div><div class="verdict"><b>结论：前365日是训练，365日之后到湖末日才是验证</b><span class="note">橙/蓝是连续回放（训练接验证，状态不断开）。紫线是官方验证窗：从 2026-05-31 空仓重开，与 P4/P5 同一口径。P7 合同门禁仍然失败；本图只展开验证期，不改阈值。</span></div></section><section id="metrics" class="metrics"></section><section class="diagnosis"><div><h2>看图重点</h2><p id="diagnosisText"></p></div><div><h2>供体日历 OOF AUC</h2><div id="equation" class="equation"></div></div></section>
<div class="toolbar"><button id="reset">完整样本</button><button id="focusTrain">训练365日</button><button id="focusVal">验证期</button><button id="focusDev">训练期末80日</button><button id="focusLast">最后一根K</button><button id="focusValTrade">下一笔验证期交易</button><button id="focusExtra">下一笔P7延长</button><button id="zoomIn">放大</button><button id="zoomOut">缩小</button><label><input id="showMa" type="checkbox" checked> MA7</label><label><input id="showTrends" type="checkbox" checked> 稳定趋势区间</label><label><input id="showLabels" type="checkbox" checked> 交易编号</label><label><input class="strategy-toggle" data-strategy="P7_FULL" type="checkbox" checked><span class="p6c"> P7连续</span></label><label><input class="strategy-toggle" data-strategy="V7_FULL" type="checkbox" checked><span class="v7c"> V7.1连续</span></label><label><input class="strategy-toggle" data-strategy="P7_VAL" type="checkbox"><span class="icc"> P7验证窗空仓重开</span></label><label><input class="strategy-toggle" data-strategy="V7_VAL" type="checkbox"> V7.1验证窗空仓重开</label></div>
<div class="chart"><canvas id="priceChart"></canvas><canvas id="probChart"></canvas><canvas id="equityFull"></canvas><canvas id="equityIc"></canvas></div><div class="chart-note">默认打开验证期（2026-05-31 → 数据湖最后完整日）。亮竖线是训练/验证边界；淡竖线只是训练期内 285/80 拆分，不是验证。金虚线标出湖内最后一根闭合日K。橙虚线 P7 连续覆盖 · 蓝实线 exact V7.1 连续 · 勾选紫色可看官方空仓重开验证窗（少 6 月 5 日那笔）。滚轮缩放，拖动平移，双击或「完整样本」看训练+验证。<br>连续回放验证段入场 4 笔；官方空仓重开验证窗 3 笔。P7 合同仍未过门禁，本图不改阈值、不重训。</div>
<section class="sections"><div class="table-wrap"><div class="table-head"><h2>连续全样本的趋势覆盖</h2><p>点击聚焦；黄色行表示 P7 比 V7.1 多覆盖几天。</p></div><table><thead><tr><th>趋势</th><th>方向</th><th>分类</th><th>区间</th><th>天数</th><th>P7覆盖</th><th>V7覆盖</th><th>覆盖差</th></tr></thead><tbody id="episodeRows"></tbody></table></div><div class="table-wrap"><div class="table-head"><h2>全部交易路径</h2><p>连续回放 + 官方验证窗空仓重开；黄色行是被 survival 延长的退出。</p></div><table><thead><tr><th>口径</th><th>策略</th><th>交易</th><th>方向</th><th>入场</th><th>退出</th><th>持有</th><th>净收益</th><th>来源/退出</th></tr></thead><tbody id="tradeRows"></tbody></table></div></section></main><div id="tooltip" class="tooltip"></div><script>
const DATA=__PAYLOAD__,DAY=86400000,C={bg:'#11171b',bg2:'#0e1417',grid:'#202a30',muted:'#89979e',up:'#72b29b',down:'#c87878',ma:'#d7b869',v7:'#69b7c9',p6:'#e6a15c',ic:'#c58ad9',survival:'#78b59b'};
const $=id=>document.getElementById(id),candles=DATA.candles,trades=DATA.trades,episodes=DATA.episodes,equity=DATA.equity,priceCanvas=$('priceChart'),probCanvas=$('probChart'),equityFull=$('equityFull'),equityIc=$('equityIc'),tooltip=$('tooltip');const PAD=5*DAY,domainMin=candles[0].t-DAY,domainMax=DATA.window.terminalT+PAD,valT=DATA.window.valBoundaryT,devT=DATA.window.developmentBoundaryT;let viewStart=valT-2*DAY,viewEnd=domainMax,hoverT=null,activeId=null,dragging=false,dragX=0,dragStart=0,extraIndex=0,valIndex=0;
function activeStrategies(){return new Set([...document.querySelectorAll('.strategy-toggle:checked')].map(x=>x.dataset.strategy))}function signed(v,d=2){return(v>=0?'+':'')+Number(v).toFixed(d)}function fmt(v,d=3){return v==null?'—':Number(v).toFixed(d)}function pct(v,d=1){return fmt(v*100,d)+'%'}function day(t){return new Date(t).toISOString().slice(0,10)}function clamp(v,a,b){return Math.max(a,Math.min(b,v))}function setup(c){const r=c.getBoundingClientRect(),d=devicePixelRatio||1;c.width=Math.round(r.width*d);c.height=Math.round(r.height*d);const x=c.getContext('2d');x.setTransform(d,0,0,d,0,0);return{ctx:x,w:r.width,h:r.height}}function xs(t,l,w){return l+(t-viewStart)/(viewEnd-viewStart)*w}function visCandles(){return candles.filter(p=>p.t>=viewStart-DAY&&p.t<=viewEnd+DAY)}function visTrades(){const a=activeStrategies();return trades.filter(p=>a.has(p.strategy)&&p.exitT>=viewStart&&p.entryT<=viewEnd)}function visEpisodes(){return episodes.filter(p=>p.endT>=viewStart&&p.startT<=viewEnd)}
function ticks(lo,hi,n){const span=Math.max(1e-9,hi-lo),raw=span/n,p=10**Math.floor(Math.log10(raw)),q=raw/p,s=(q<1.5?1:q<3?2:q<7?5:10)*p,o=[];for(let v=Math.ceil(lo/s)*s;v<=hi+s*.1;v+=s)o.push(v);return o}function axes(ctx,m,pw,ph,lo,hi,y){ctx.font='11px "Geist Mono",monospace';for(const v of ticks(lo,hi,5)){const yy=y(v);ctx.strokeStyle=C.grid;ctx.beginPath();ctx.moveTo(m.l,yy);ctx.lineTo(m.l+pw,yy);ctx.stroke();ctx.fillStyle=C.muted;ctx.textAlign='right';ctx.fillText(v.toFixed(Math.abs(v)<10?2:1),m.l-8,yy+4)}for(let i=0;i<=8;i++){const z=viewStart+(viewEnd-viewStart)*i/8,x=xs(z,m.l,pw);ctx.strokeStyle=C.grid;ctx.beginPath();ctx.moveTo(x,m.t);ctx.lineTo(x,m.t+ph);ctx.stroke();ctx.fillStyle=C.muted;ctx.textAlign=i===0?'left':i===8?'right':'center';ctx.fillText(day(z),x,m.t+ph+18)}}function boundary(ctx,m,pw,ph,label){function mark(t,color,dash,text,yOff){if(t<viewStart||t>viewEnd)return;const x=xs(t,m.l,pw);ctx.strokeStyle=color;ctx.globalAlpha=.85;ctx.setLineDash(dash);ctx.beginPath();ctx.moveTo(x,m.t);ctx.lineTo(x,m.t+ph);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1;if(label&&text){ctx.fillStyle=color;ctx.textAlign='center';ctx.fillText(text,x,m.t+yOff)}}mark(devT,'#6b7a82',[2,4],label?'训练期内 285/80 拆分':'',13);mark(valT,'#d5dde0',[6,5],label?'训练365日 ← | → 验证期':'',28)}function crosshair(ctx,m,pw,ph){if(hoverT==null)return;const x=xs(hoverT,m.l,pw);ctx.strokeStyle=C.muted;ctx.globalAlpha=.5;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(x,m.t);ctx.lineTo(x,m.t+ph);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1}function line(ctx,vals,key,color,y,l,w,dash=[],width=1.8,offset=DAY/2){ctx.strokeStyle=color;ctx.lineWidth=width;ctx.setLineDash(dash);ctx.beginPath();let on=false;for(const p of vals){if(p[key]==null){on=false;continue}const x=xs(p.t+offset,l,w),yy=y(p[key]);on?ctx.lineTo(x,yy):(ctx.moveTo(x,yy),on=true)}ctx.stroke();ctx.setLineDash([])}function marker(ctx,x,y,side,entry,color,size){ctx.fillStyle=color;ctx.strokeStyle=C.bg2;ctx.lineWidth=1.2;ctx.beginPath();if(entry){if(side==='long'){ctx.moveTo(x,y-size);ctx.lineTo(x-size,y+size);ctx.lineTo(x+size,y+size)}else{ctx.moveTo(x,y+size);ctx.lineTo(x-size,y-size);ctx.lineTo(x+size,y-size)}ctx.closePath()}else ctx.arc(x,y,size-1,0,Math.PI*2);ctx.fill();ctx.stroke()}
function shadeEpisodes(ctx,m,pw,ph){if(!$('showTrends').checked)return;for(const e of visEpisodes()){const x1=xs(Math.max(e.startT,viewStart),m.l,pw),x2=xs(Math.min(e.endT,viewEnd),m.l,pw);ctx.fillStyle=e.side>0?'rgba(114,178,155,.075)':'rgba(200,120,120,.075)';ctx.fillRect(x1,m.t,Math.max(1,x2-x1),ph);if(e.classification==='P7_MORE'||e.classification==='P7_NEW_CAPTURE'){ctx.strokeStyle='rgba(215,184,105,.7)';ctx.setLineDash([3,4]);ctx.strokeRect(x1+.5,m.t+.5,Math.max(1,x2-x1-1),ph-1);ctx.setLineDash([])}}}
function markLastBar(ctx,m,pw,ph){const last=candles[candles.length-1];if(last.t<viewStart-DAY||last.t>viewEnd+DAY)return;const x=xs(last.t+DAY/2,m.l,pw);ctx.strokeStyle='#d7b869';ctx.globalAlpha=.9;ctx.setLineDash([2,3]);ctx.beginPath();ctx.moveTo(x,m.t);ctx.lineTo(x,m.t+ph);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1;ctx.fillStyle='#d7b869';ctx.font='10px "Geist Mono",monospace';ctx.textAlign=x>m.l+pw-130?'right':'left';ctx.fillText('最后一根K '+day(last.t),x+(x>m.l+pw-130?-8:8),m.t+ph-8)}
function drawPrice(){const{ctx,w,h}=setup(priceCanvas),m={l:72,r:48,t:24,b:34},pw=w-m.l-m.r,ph=h-m.t-m.b,vis=visCandles(),vtr=visTrades();ctx.fillStyle=C.bg;ctx.fillRect(0,0,w,h);if(!vis.length)return;let lo=Math.min(...vis.map(p=>p.l),...vtr.map(t=>Math.min(t.entry,t.exit))),hi=Math.max(...vis.map(p=>p.h),...vtr.map(t=>Math.max(t.entry,t.exit))),pad=(hi-lo)*.07||1;lo-=pad;hi+=pad;const y=v=>m.t+(hi-v)/(hi-lo)*ph;axes(ctx,m,pw,ph,lo,hi,y);shadeEpisodes(ctx,m,pw,ph);const bw=clamp(pw/Math.max(1,(viewEnd-viewStart)/DAY)*.62,1,13);for(const p of vis){const x=xs(p.t+DAY/2,m.l,pw),col=p.c>=p.o?C.up:C.down;ctx.strokeStyle=col;ctx.beginPath();ctx.moveTo(x,y(p.h));ctx.lineTo(x,y(p.l));ctx.stroke();ctx.fillStyle=col;ctx.fillRect(x-bw/2,y(Math.max(p.o,p.c)),bw,Math.max(1,y(Math.min(p.o,p.c))-y(Math.max(p.o,p.c))))}if($('showMa').checked)line(ctx,vis,'ma7',C.ma,y,m.l,pw,[],1.7);for(const t of vtr.sort((a,b)=>a.strategy.includes('V7')?-1:1)){const cfg=DATA.strategies[t.strategy],hot=t.id===activeId,x1=xs(t.entryT,m.l,pw),x2=xs(t.exitT,m.l,pw),y1=y(t.entry),y2=y(t.exit);ctx.strokeStyle=cfg.color;ctx.globalAlpha=hot?1:cfg.group==='validation'?.98:.76;ctx.lineWidth=hot?4:cfg.group==='validation'?3.1:t.strategy==='V7_FULL'?2.8:2.25;ctx.setLineDash(cfg.dash);ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1;marker(ctx,x1,y1,t.side,true,cfg.color,hot?9:7);marker(ctx,x2,y2,t.side,false,cfg.color,hot?9:7);if($('showLabels').checked||hot){ctx.fillStyle=cfg.color;ctx.textAlign='center';ctx.font='10px "Geist Mono",monospace';ctx.fillText(t.id,x2,y2+(cfg.group==='confirmation'?18:-11))}}markLastBar(ctx,m,pw,ph);boundary(ctx,m,pw,ph,true);crosshair(ctx,m,pw,ph);ctx.fillStyle=C.muted;ctx.textAlign='left';ctx.fillText('PRICE · HYPEUSDT 1D · MA7 · 交易路径',m.l,15)}
function drawProbability(){const{ctx,w,h}=setup(probCanvas),m={l:72,r:48,t:18,b:28},pw=w-m.l-m.r,ph=h-m.t-m.b,vis=visCandles();ctx.fillStyle=C.bg2;ctx.fillRect(0,0,w,h);const y=v=>m.t+(1-v)*ph;for(const v of[0,.35,.5,.6,1]){const yy=y(v);ctx.strokeStyle=[.35,.6].includes(v)?'rgba(215,184,105,.28)':C.grid;ctx.setLineDash([.35,.6].includes(v)?[4,4]:[]);ctx.beginPath();ctx.moveTo(m.l,yy);ctx.lineTo(m.l+pw,yy);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=C.muted;ctx.textAlign='right';ctx.fillText(v.toFixed(2),m.l-8,yy+4)}shadeEpisodes(ctx,m,pw,ph);line(ctx,vis,'fullSurvival',C.survival,y,m.l,pw,[],2.0);boundary(ctx,m,pw,ph,false);crosshair(ctx,m,pw,ph);ctx.fillStyle=C.muted;ctx.textAlign='left';ctx.fillText('SURVIVAL_3D · START .60 · DEATH .35 · 冻结供体模型打到训练+验证全样本',m.l,13)}
function drawEquity(canvas,keys,title){const{ctx,w,h}=setup(canvas),m={l:72,r:48,t:20,b:34},pw=w-m.l-m.r,ph=h-m.t-m.b,a=activeStrategies(),series=keys.filter(k=>a.has(k)).map(k=>({k,v:equity[k].filter(p=>p.t>=viewStart-DAY&&p.t<=viewEnd+DAY)})).filter(s=>s.v.length);ctx.fillStyle=C.bg2;ctx.fillRect(0,0,w,h);if(!series.length){ctx.fillStyle=C.muted;ctx.fillText(title+' · 请启用对应策略',m.l,15);return}let lo=Math.min(...series.flatMap(s=>s.v.map(p=>p.v))),hi=Math.max(...series.flatMap(s=>s.v.map(p=>p.v))),pad=(hi-lo)*.08||.02;lo=Math.max(0,lo-pad);hi+=pad;const y=v=>m.t+(hi-v)/(hi-lo)*ph;axes(ctx,m,pw,ph,lo,hi,y);for(const s of series){const cfg=DATA.strategies[s.k];ctx.strokeStyle=cfg.color;ctx.lineWidth=2.6;ctx.setLineDash(cfg.dash);ctx.beginPath();s.v.forEach((p,i)=>{const x=xs(p.t,m.l,pw);i?ctx.lineTo(x,y(p.v)):ctx.moveTo(x,y(p.v))});ctx.stroke();ctx.setLineDash([])}boundary(ctx,m,pw,ph,false);crosshair(ctx,m,pw,ph);ctx.fillStyle=C.muted;ctx.textAlign='left';ctx.fillText(title,m.l,13)}function draw(){drawPrice();drawProbability();drawEquity(equityFull,['P7_FULL','V7_FULL'],'EQUITY · 连续全样本（训练接验证）');drawEquity(equityIc,['P7_VAL','V7_VAL'],'EQUITY · 官方验证窗空仓重开（独立从1开始）');for(const r of document.querySelectorAll('tbody tr'))r.classList.toggle('active',r.dataset.id===activeId)}
function reset(){viewStart=domainMin;viewEnd=domainMax;activeId=null;draw()}function setView(a,b){viewStart=Math.max(domainMin,a);viewEnd=Math.min(domainMax,Math.max(viewStart+8*DAY,b))}function focusRange(a,b){setView(a,b);activeId=null;draw()}function zoom(f,a=(viewStart+viewEnd)/2){const cur=viewEnd-viewStart,next=clamp(cur*f,8*DAY,domainMax-domainMin),q=(a-viewStart)/cur;viewStart=a-next*q;viewEnd=viewStart+next;if(viewStart<domainMin){viewEnd+=domainMin-viewStart;viewStart=domainMin}if(viewEnd>domainMax){viewStart-=viewEnd-domainMax;viewEnd=domainMax}draw()}function focusItem(item,aKey,bKey){const a=item[aKey],b=item[bKey],pad=8*DAY;let start=Math.min(a,b)-pad,end=Math.max(a,b)+pad;if(end>=valT)end=Math.max(end,DATA.window.terminalT+2*DAY);if(end-start<36*DAY){const extra=(36*DAY-(end-start))/2;start-=extra;end+=extra}setView(start,end);activeId=item.id;draw();priceCanvas.scrollIntoView({behavior:'smooth',block:'center'})}function enableVal(){for(const x of document.querySelectorAll('.strategy-toggle')){if(String(x.dataset.strategy).endsWith('_VAL'))x.checked=true}}function focusValView(){focusRange(valT-2*DAY,domainMax);priceCanvas.scrollIntoView({behavior:'smooth',block:'center'})}function focusLastBar(){focusRange(candles[candles.length-1].t-36*DAY,domainMax);priceCanvas.scrollIntoView({behavior:'smooth',block:'center'})}function nextExtra(){const x=trades.filter(t=>t.strategy==='P7_FULL'&&t.extended);if(x.length)focusItem(x[extraIndex++%x.length],'entryT','exitT')}function nextValTrade(){const x=trades.filter(t=>t.strategy==='P7_FULL'&&t.entryT>=valT);if(x.length)focusItem(x[valIndex++%x.length],'entryT','exitT')}
function metricGroup(title,a,b,cls){const x=DATA.metrics[a],y=DATA.metrics[b];return`<div class="metric-group"><h2>${title}</h2><div class="metric-grid"><div><span>策略</span><b class="${cls}">${DATA.strategies[a].label}</b><span>${DATA.strategies[b].label}</span></div><div><span>收益 · MDD</span><b>${signed(x.net_return_pct)}% · ${signed(x.chronological_1h_mdd_pct)}%</b><span>${signed(y.net_return_pct)}% · ${signed(y.chronological_1h_mdd_pct)}%</span></div><div><span>交易 · 胜率</span><b>${x.trades} · ${pct(x.win_rate)}</b><span>${y.trades} · ${pct(y.win_rate)}</span></div><div><span>按天趋势覆盖</span><b>${pct(x.duration_weighted_capture)}</b><span>${pct(y.duration_weighted_capture)}</span></div><div><span>平均持有 · 成本</span><b>${fmt(x.average_hold_days,1)}d · ${fmt(x.cost_pct_initial,2)}%</b><span>${fmt(y.average_hold_days,1)}d · ${fmt(y.cost_pct_initial,2)}%</span></div></div></div>`}function renderMetrics(){$('metrics').innerHTML=metricGroup('连续全样本：训练接验证，状态不断开','P7_FULL','V7_FULL','p6c')+metricGroup('官方验证窗：从365日边界空仓重开','P7_VAL','V7_VAL','icc');$('diagnosisText').textContent='前365日是训练，2026-05-31起到数据湖最后完整日才是验证。连续回放验证段开了4笔（含6月5日short）；官方空仓重开验证窗只有3笔。P7只延长了7月12日那笔max_hold，验证窗净收益仍低于V7.1。训练期内那两笔被拉长的short止盈仍然在图左侧。';const o=DATA.oof;$('equation').innerHTML=`合并 ${o.auc.toFixed(3)} · ${o.rows}行<br>ETH ${o.byAsset.ETHUSDT.auc.toFixed(3)}<br>BTC ${o.byAsset.BTCUSDT.auc.toFixed(3)}<br>BNB ${o.byAsset.BNBUSDT.auc.toFixed(3)}<br>SOL ${o.byAsset.SOLUSDT.auc.toFixed(3)}`}
function renderEpisodes(){const body=$('episodeRows');body.innerHTML=episodes.map(e=>{const label=e.classification==='P7_NEW_CAPTURE'?'<span class="badge">P7新识别</span>':e.classification==='P7_MORE'?'<span class="badge">P7更久</span>':e.classification==='V7_MORE'?'V7更多':'相同';return`<tr data-id="${e.id}" class="${e.classification==='P7_MORE'||e.classification==='P7_NEW_CAPTURE'?'new':''}"><td>${e.id}</td><td>${e.side>0?'多头':'空头'}</td><td>${label}</td><td>${day(e.startT)} → ${day(e.endT-DAY)}</td><td>${e.durationDays}</td><td class="p6c">${e.p7Days} · ${pct(e.p7Capture)}</td><td class="v7c">${e.v7Days} · ${pct(e.v7Capture)}</td><td class="${e.p7Capture>=e.v7Capture?'positive':'negative'}">${signed((e.p7Capture-e.v7Capture)*100,1)}pp</td></tr>`}).join('');for(const r of body.querySelectorAll('tr'))r.onclick=()=>focusItem(episodes.find(e=>e.id===r.dataset.id),'startT','endT')}
function renderTrades(){const body=$('tradeRows');body.innerHTML=trades.sort((a,b)=>a.entryT-b.entryT||a.strategy.localeCompare(b.strategy)).map(t=>`<tr data-id="${t.id}" class="${t.extended?'new':''}"><td>${t.segment==='full'?'连续回放':'验证窗空仓重开'}</td><td style="color:${DATA.strategies[t.strategy].color}">${t.strategyLabel}</td><td>${t.id}</td><td>${t.side==='long'?'做多':'做空'}</td><td>${day(t.entryT)} · ${fmt(t.entry)}</td><td>${day(t.exitT)} · ${fmt(t.exit)}</td><td>${t.barsHeld}d</td><td class="${t.netReturnPct>=0?'positive':'negative'}">${signed(t.netReturnPct)}%</td><td>${t.extended?'P7延长 · ':''}${t.exitReason}</td></tr>`).join('');for(const r of body.querySelectorAll('tr'))r.onclick=()=>focusItem(trades.find(t=>t.id===r.dataset.id),'entryT','exitT')}
function pointerMove(e){if(dragging){const r=priceCanvas.getBoundingClientRect(),span=viewEnd-viewStart,shift=-(e.clientX-dragX)/Math.max(1,r.width-120)*span;viewStart=clamp(dragStart+shift,domainMin,domainMax-span);viewEnd=viewStart+span;draw();return}const r=priceCanvas.getBoundingClientRect(),q=clamp((e.clientX-r.left-72)/Math.max(1,r.width-120),0,1);hoverT=viewStart+q*(viewEnd-viewStart);const c=candles.reduce((a,b)=>Math.abs(b.t+DAY/2-hoverT)<Math.abs(a.t+DAY/2-hoverT)?b:a,candles[0]),near=trades.filter(t=>activeStrategies().has(t.strategy)&&Math.min(Math.abs(t.entryT-hoverT),Math.abs(t.exitT-hoverT))<DAY*.7),ep=episodes.find(x=>x.startT<=c.t&&x.endT>c.t);let s=`${day(c.t)} UTC\nO ${fmt(c.o)} H ${fmt(c.h)} L ${fmt(c.l)} C ${fmt(c.c)}\nMA7 ${fmt(c.ma7)} · slope/ATR ${signed(c.slopeAtr,4)}\n完整拟合 SURVIVAL ${fmt(c.fullSurvival,3)}`;if(ep)s+=`\n${ep.id} ${ep.side>0?'稳定多头':'稳定空头'} · P7 ${pct(ep.p7Capture)} / V7 ${pct(ep.v7Capture)}`;for(const t of near)s+=`\n${t.id} ${t.strategyLabel} ${t.side==='long'?'多':'空'} · ${signed(t.netReturnPct)}%${t.extended?' · 延长':''}`;tooltip.textContent=s;tooltip.style.display='block';tooltip.style.left=Math.min(innerWidth-620,e.clientX+15)+'px';tooltip.style.top=Math.min(innerHeight-250,e.clientY+15)+'px';draw()}
$('title').textContent=DATA.title;$('subtitle').textContent=DATA.subtitle;$('status').textContent=`${DATA.status} · ${DATA.window.start.slice(0,10)} → ${DATA.window.terminal.slice(0,10)}`;$('reset').onclick=reset;$('focusTrain').onclick=()=>focusRange(domainMin,valT);$('focusVal').onclick=focusValView;$('focusDev').onclick=()=>focusRange(devT-2*DAY,valT);$('focusLast').onclick=focusLastBar;$('focusExtra').onclick=nextExtra;$('focusValTrade').onclick=nextValTrade;$('zoomIn').onclick=()=>zoom(.65);$('zoomOut').onclick=()=>zoom(1.55);$('showMa').onchange=draw;$('showTrends').onchange=draw;$('showLabels').onchange=draw;for(const x of document.querySelectorAll('.strategy-toggle'))x.onchange=draw;priceCanvas.onwheel=e=>{e.preventDefault();const r=priceCanvas.getBoundingClientRect(),q=clamp((e.clientX-r.left-72)/Math.max(1,r.width-120),0,1);zoom(e.deltaY>0?1.2:.82,viewStart+q*(viewEnd-viewStart))};priceCanvas.onpointerdown=e=>{dragging=true;dragX=e.clientX;dragStart=viewStart;priceCanvas.setPointerCapture(e.pointerId)};priceCanvas.onpointerup=e=>{dragging=false;if(priceCanvas.hasPointerCapture(e.pointerId))priceCanvas.releasePointerCapture(e.pointerId)};priceCanvas.onpointermove=pointerMove;priceCanvas.onpointerleave=()=>{if(!dragging){hoverT=null;tooltip.style.display='none';draw()}};priceCanvas.ondblclick=reset;window.onresize=draw;renderMetrics();renderEpisodes();renderTrades();draw();
</script></body></html>'''


def main() -> None:
    args = parse_args()
    outputs = (
        OUTPUT_PATH,
        MANIFEST_PATH,
        OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".sha256"),
        MANIFEST_PATH.with_suffix(MANIFEST_PATH.suffix + ".sha256"),
    )
    if any(path.exists() for path in outputs) and not args.force:
        raise RuntimeError(f"comparison artifact exists: {OUTPUT_PATH.name}; use --force")
    payload, manifest = build_payload()
    html = HTML_TEMPLATE.replace(
        "__PAYLOAD__",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
    )
    required = (
        "setPointerCapture",
        "releasePointerCapture",
        "ondblclick=reset",
        "focusVal",
        "focusLast",
        "nextExtra",
        "nextValTrade",
        "完整样本",
        "训练365日",
        "验证期",
        "最后一根K",
        "markLastBar",
        "valBoundaryT",
        "MA7",
        "空仓重开",
    )
    for token in required:
        if token not in html:
            raise RuntimeError(f"required comparison interaction missing: {token}")
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    manifest.update(
        {
            "html": OUTPUT_PATH.name,
            "html_sha256": sha256(OUTPUT_PATH),
            "html_bytes": OUTPUT_PATH.stat().st_size,
            "renderer_sha256": sha256(Path(__file__).resolve()),
        }
    )
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    for path in (OUTPUT_PATH, MANIFEST_PATH):
        path.with_suffix(path.suffix + ".sha256").write_text(
            f"{sha256(path)}  {path.name}\n", encoding="utf-8"
        )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
