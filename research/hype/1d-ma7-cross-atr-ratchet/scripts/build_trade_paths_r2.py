"""Render eight R2 ledger paths on the frozen daily candles; never simulate."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
INPUT = BASE / "artifacts/inputs_20260909"
RESULTS = BASE / "artifacts/r2_slowdown_tightening_20260909"
OUTPUT = BASE / "artifacts/r2_trade_paths_20260909"
TEMPLATE = Path(__file__).with_name("trade_path_template_r2.html")
DEFAULT_ARM = "original_stall_rev1"
ARMS = {
    "original_stall_rev1": ("original", "stall_only", True, "只改止损 · 允许反手"),
    "original_stall_rev0": ("original", "stall_only", False, "只改止损 · 关闭反手"),
    "original_fixed_rev1": ("original", "fixed", True, "原始规则 · 允许反手"),
    "original_fixed_rev0": ("original", "fixed", False, "原始规则 · 关闭反手"),
    "slowdown_stall_rev1": ("opposite_slowdown", "stall_only", True, "减速入场＋停滞收紧 · 允许反手"),
    "slowdown_stall_rev0": ("opposite_slowdown", "stall_only", False, "减速入场＋停滞收紧 · 关闭反手"),
    "slowdown_daily_rev1": ("opposite_slowdown", "armed_daily", True, "减速入场＋启动后每天收紧 · 允许反手"),
    "slowdown_daily_rev0": ("opposite_slowdown", "armed_daily", False, "减速入场＋启动后每天收紧 · 关闭反手"),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ms(value):
    return int(pd.Timestamp(value).value // 1_000_000)


def finite(value):
    return float(value) if pd.notna(value) and np.isfinite(value) else None


def load_chart_data():
    original = json.loads((RESULTS / "artifact_checksums.json").read_text())

    def verified(relative):
        path = RESULTS / relative
        assert relative in original, f"Result missing from checksum manifest: {relative}"
        assert sha(path) == original[relative], f"Frozen R2 result changed: {relative}"
        return path

    manifest = json.loads(verified("run_manifest.json").read_text())
    source_checks = {
        "engine_sha256": BASE / "scripts/engine_r2.py",
        "run_script_sha256": BASE / "scripts/run_r2.py",
        "contract_sha256": BASE / "specs/r2-slowdown-tightening-20260909.md",
        "r1_engine_sha256": BASE / "scripts/engine.py",
        "r1_run_manifest_sha256": BASE / "artifacts/results_20260909/run_manifest.json",
        "input_checksums_sha256": INPUT / "checksums.json",
    }
    for key, path in source_checks.items():
        assert sha(path) == manifest[key], f"Frozen input or source changed: {key}"
    input_manifest = json.loads((INPUT / "checksums.json").read_text())
    for relative, checksum in input_manifest.items():
        assert sha(INPUT / relative) == checksum, f"Frozen input changed: {relative}"

    daily_path = verified("daily_features.csv")
    daily = pd.read_csv(daily_path)
    raw_daily = pd.read_parquet(INPUT / "daily.parquet").rename(columns={"ts": "timestamp"})
    assert len(daily) == len(raw_daily)
    assert (pd.to_datetime(daily.timestamp, utc=True).to_numpy()
            == pd.to_datetime(raw_daily.timestamp, utc=True).to_numpy()).all()
    for column in ("open", "high", "low", "close"):
        np.testing.assert_allclose(daily[column], raw_daily[column], rtol=1e-14, atol=1e-14)
    records = [[ms(r.timestamp), r.open, r.high, r.low, r.close, finite(r.ma), finite(r.atr),
                finite(r.rsi), finite(r.slope), int(r.cross), bool(r.accel1),
                finite(r.ma_step), finite(r.prev_ma_step)] for r in daily.itertuples()]
    start, end = manifest["windows"]["full"]
    data = {"candles": records, "start": ms(start), "end": ms(end),
            "defaultArm": DEFAULT_ARM, "arms": {}}
    audit = {
        "input_checksums_sha256": sha(INPUT / "checksums.json"),
        "input_files_verified": input_manifest,
        "parent_manifest_sha256": sha(RESULTS / "run_manifest.json"),
        "parent_artifact_checksums_sha256": sha(RESULTS / "artifact_checksums.json"),
        "frozen_sources_verified": {key: sha(path) for key, path in source_checks.items()},
        "source_files": {"daily_features.csv": sha(daily_path)}, "candles": len(records),
        "arms": {}, "default_arm": DEFAULT_ARM, "no_backtest_rerun": True,
        "no_indicator_recalculation": True, "daily_ohlc_matches_frozen_inputs": True,
        "funding_window_verified": False, "browser_qa_performed": False,
        "timestamp_semantics": "UTC; candle center at noon; daily indicators at close; intrahour exit glyph centered in its recorded one-hour uncertainty interval",
    }
    for name, (entry_mode, tighten_mode, reverse, label) in ARMS.items():
        run = f"s0.05_rev{int(reverse)}_accel1_rsi30_{entry_mode}_{tighten_mode}_p0"
        relative = f"runs/{run}/full"
        files = {kind: verified(f"{relative}/{kind}.{ext}") for kind, ext in
                 [("trades", "csv"), ("stops", "csv"), ("equity", "parquet"), ("summary", "json")]}
        audit["source_files"].update({str(path.relative_to(RESULTS)): sha(path) for path in files.values()})
        trades = pd.read_csv(files["trades"])
        stops = pd.read_csv(files["stops"])
        curve = pd.read_parquet(files["equity"])
        summary = json.loads(files["summary"].read_text())
        assert summary["entry_mode"] == entry_mode and summary["tighten_mode"] == tighten_mode
        assert summary["reverse"] == reverse and summary["profit_trigger_atr"] == 0
        assert summary["fee"] == .0005 and summary["slip"] == .0003 and summary["delay_hours"] == 0
        assert summary["price_only_diagnostic"] and summary["short_exit"] == "accel1_rsi30"
        chart_trades = []
        for t in trades.itertuples():
            stop_rows = stops[stops.trade_id == t.trade_id].copy()
            stop_rows["timestamp"] = pd.to_datetime(stop_rows.timestamp, utc=True)
            stop_rows = stop_rows.sort_values("timestamp", kind="stable")
            assert len(stop_rows) and ms(stop_rows.iloc[0].timestamp) == ms(t.entry_time)
            assert all(t.side * stop_rows.new_stop.diff().dropna() >= -1e-10)
            assert abs(float(stop_rows.iloc[-1].new_stop) - t.stop) < 1e-9
            assert all(ms(v) <= ms(t.exit_time) for v in stop_rows.timestamp)
            assert stop_rows.iloc[0].new_mult == 1.5
            assert all(stop_rows.new_mult <= stop_rows.old_mult)
            assert all(stop_rows.new_mult >= .5)
            assert stop_rows.iloc[-1].new_mult == t.stop_mult
            assert int(stop_rows.tightened.sum()) == t.tightening_days
            a, b = ms(t.exit_time), ms(t.exit_interval_end)
            assert b - a == (3_600_000 if t.exit_reason == "stop_intrahour" else 0)
            chart_trades.append({
                "id": int(t.trade_id), "side": int(t.side), "entry": ms(t.entry_time),
                "exit": a, "exitEnd": b, "exitPlot": (a + b) // 2,
                "entryPrice": t.entry_price, "exitPrice": t.exit_price,
                "entryReference": t.entry_reference, "exitReference": t.exit_reference,
                "entryReason": t.entry_reason, "exitReason": t.exit_reason,
                "qualification": t.qualification, "entryAtr": t.entry_atr,
                "initialMult": t.initial_stop_mult, "finalMult": t.stop_mult,
                "tighteningDays": int(t.tightening_days), "armed": bool(t.armed),
                "entrySlope": t.entry_slope, "entryMaStep": t.entry_ma_step,
                "entryPrevMaStep": t.entry_prev_ma_step,
                "signal": ms(t.signal_day), "cross": ms(t.cross_day),
                "tpSignal": ms(t.tp_signal_day) if pd.notna(t.tp_signal_day) else None,
                "tpRsi": finite(t.tp_signal_rsi), "qty": t.qty,
                "pnl": t.net_pnl, "returnPct": t.return_on_entry_equity * 100,
                "fees": t.entry_fee + t.exit_fee,
                "stops": [[ms(r.timestamp), r.new_stop] for r in stop_rows.itertuples()],
                "stopAudit": [[ms(r.timestamp), r.old_mult, r.new_mult, bool(r.tightened),
                               r.tightening_trigger, bool(r.stalled), bool(r.profit_eligible)]
                              for r in stop_rows.itertuples()],
            })
        assert len(chart_trades) == summary["trades"]
        assert abs(sum(t["pnl"] for t in chart_trades) - (summary["ending_equity"] - 10000)) < 1e-7
        assert sum(t["tighteningDays"] for t in chart_trades) == summary["tightening_days"]
        assert sum(t["tighteningDays"] > 0 for t in chart_trades) == summary["tightened_trades"]
        line = curve.groupby("timestamp", sort=True).equity.last()
        chart_equity = [[ms(ts), float(value)] for ts, value in line.items()]
        assert abs(chart_equity[-1][1] - summary["ending_equity"]) < 1e-7
        data["arms"][name] = {"label": label, "summary": summary, "trades": chart_trades, "equity": chart_equity}
        audit["arms"][name] = {
            "trades": len(chart_trades), "long": summary["long_trades"], "short": summary["short_trades"],
            "stop_rows": len(stops), "exit_reasons": trades.exit_reason.value_counts().to_dict(),
            "entry_qualifications": trades.qualification.value_counts().to_dict(),
            "tightened_trades": summary["tightened_trades"], "tightening_days": summary["tightening_days"],
            "entry_markers": len(chart_trades), "exit_markers": len(chart_trades),
            "reconciled_pnl": float(trades.net_pnl.sum()), "return_pct": summary["return_pct"],
            "max_drawdown_pct": summary["max_drawdown_pct"], "monotone_stop_verified": True,
            "multiplier_ledger_verified": True, "exit_hour_intervals_verified": True,
        }
    return data, audit


def main():
    data, audit = load_chart_data()
    OUTPUT.mkdir(exist_ok=True)
    html_path = OUTPUT / "hype-ma7-r2-trade-paths.html"
    payload_path = OUTPUT / "payload.json"
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    payload_path.write_text(payload + "\n")
    content = TEMPLATE.read_text()
    assert content.count("__FROZEN_DATA__") == 1
    scripts = re.findall(r"<script>(.*?)</script>", content, re.S)
    assert len(scripts) == 1
    subprocess.run(["node", "--check", "-"], input=scripts[0], text=True, check=True, capture_output=True)
    assert not re.search(r"<(?:script|link|iframe|img)\b[^>]+\b(?:src|href)\s*=", content, re.I)
    assert not re.search(r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource)\b", scripts[0])
    html_path.write_text(content.replace("__FROZEN_DATA__", payload.replace("</", "<\\/")))
    audit.update({"renderer_sha256": sha(Path(__file__)), "template_sha256": sha(TEMPLATE),
                  "payload_sha256": sha(payload_path), "html_sha256": sha(html_path),
                  "javascript_syntax_verified": True, "external_resource_tags": 0,
                  "html_bytes": html_path.stat().st_size, "created_at_utc": str(pd.Timestamp.now(tz="UTC"))})
    (OUTPUT / "chart_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(html_path), "payload": str(payload_path),
                      "arms": audit["arms"], "bytes": audit["html_bytes"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
