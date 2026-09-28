"""Render existing frozen backtest ledgers on daily candles; never simulate."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from run_study import BASE, INPUT, load_inputs

RESULTS = BASE / "artifacts/results_20260909"
OUTPUT = BASE / "artifacts/trade_paths_20260909"
TEMPLATE = Path(__file__).with_name("trade_path_template.html")
ARMS = {"primary": "完整方案 · 允许反手", "no_reverse_accel1": "对照方案 · 关闭反手"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ms(value):
    return int(pd.Timestamp(value).value // 1_000_000)


def finite(value):
    return float(value) if pd.notna(value) and np.isfinite(value) else None


def load_chart_data():
    _, daily, _ = load_inputs()
    original = json.loads((RESULTS / "artifact_checksums.json").read_text())
    manifest = json.loads((RESULTS / "run_manifest.json").read_text())
    for key, path in {"engine_sha256": BASE / "scripts/engine.py",
                      "run_script_sha256": BASE / "scripts/run_study.py",
                      "contract_sha256": BASE / "specs/contract-20260909.md"}.items():
        if sha(path) != manifest[key]:
            raise ValueError(f"Frozen source changed: {key}")
    records = [[ms(r.timestamp), r.open, r.high, r.low, r.close, finite(r.ma), finite(r.atr),
                finite(r.rsi), finite(r.slope), int(r.cross), bool(r.accel1)] for r in daily.itertuples()]
    data = {"candles": records, "start": ms(manifest["start"]), "end": ms(manifest["end"]), "arms": {}}
    audit = {"input_checksums_sha256": sha(INPUT / "checksums.json"),
             "parent_manifest_sha256": sha(RESULTS / "run_manifest.json"),
             "parent_artifact_checksums_sha256": sha(RESULTS / "artifact_checksums.json"),
             "source_files": {}, "candles": len(records), "arms": {},
             "no_backtest_rerun": True, "funding_window_verified": False,
             "timestamp_semantics": "UTC; candle center at noon; daily indicators at close; intrahour exit glyph centered in its recorded one-hour uncertainty interval"}
    for name, label in ARMS.items():
        files = {kind: RESULTS / f"{name}_{kind}.{ext}" for kind, ext in
                 [("trades", "csv"), ("stops", "csv"), ("equity", "parquet"), ("summary", "json")]}
        for path in files.values():
            assert sha(path) == original[path.name], f"Original result changed: {path.name}"
            audit["source_files"][path.name] = sha(path)
        trades = pd.read_csv(files["trades"])
        stops = pd.read_csv(files["stops"])
        curve = pd.read_parquet(files["equity"])
        summary = json.loads(files["summary"].read_text())
        chart_trades = []
        for t in trades.itertuples():
            stop_rows = stops[stops.trade_id == t.trade_id].copy()
            stop_rows["timestamp"] = pd.to_datetime(stop_rows.timestamp, utc=True)
            stop_rows = stop_rows.sort_values("timestamp", kind="stable")
            assert len(stop_rows)
            assert ms(stop_rows.iloc[0].timestamp) == ms(t.entry_time)
            assert all(t.side * stop_rows.new_stop.diff().dropna() >= -1e-10)
            assert abs(float(stop_rows.iloc[-1].new_stop) - t.stop) < 1e-9
            assert all(ms(v) <= ms(t.exit_time) for v in stop_rows.timestamp)
            a, b = ms(t.exit_time), ms(t.exit_interval_end)
            assert b - a == (3_600_000 if t.exit_reason == "stop_intrahour" else 0)
            chart_trades.append({
                "id": int(t.trade_id), "side": int(t.side), "entry": ms(t.entry_time),
                "exit": a, "exitEnd": b, "exitPlot": (a + b) // 2,
                "entryPrice": t.entry_price, "exitPrice": t.exit_price,
                "entryReference": t.entry_reference, "exitReference": t.exit_reference,
                "entryReason": t.entry_reason, "exitReason": t.exit_reason,
                "signal": ms(t.signal_day), "cross": ms(t.cross_day),
                "tpSignal": ms(t.tp_signal_day) if pd.notna(t.tp_signal_day) else None,
                "tpRsi": finite(t.tp_signal_rsi), "qty": t.qty,
                "pnl": t.net_pnl, "returnPct": t.return_on_entry_equity * 100,
                "fees": t.entry_fee + t.exit_fee,
                "stops": [[ms(r.timestamp), r.new_stop] for r in stop_rows.itertuples()],
            })
        assert len(chart_trades) == summary["trades"]
        assert abs(sum(t["pnl"] for t in chart_trades) - (summary["ending_equity"] - 10000)) < 1e-7
        # Same-timestamp rows retain the last state, without a fictitious time shift.
        line = curve.groupby("timestamp", sort=True).equity.last()
        chart_equity = [[ms(ts), float(value)] for ts, value in line.items()]
        assert abs(chart_equity[-1][1] - summary["ending_equity"]) < 1e-7
        data["arms"][name] = {"label": label, "summary": summary, "trades": chart_trades, "equity": chart_equity}
        audit["arms"][name] = {"trades": len(chart_trades), "long": summary["long_trades"],
                              "short": summary["short_trades"], "stop_rows": len(stops),
                              "exit_reasons": trades.exit_reason.value_counts().to_dict(),
                              "entry_markers": len(chart_trades), "exit_markers": len(chart_trades),
                              "reconciled_pnl": float(trades.net_pnl.sum()),
                              "monotone_stop_verified": True, "exit_hour_intervals_verified": True}
    return data, audit


def main():
    data, audit = load_chart_data()
    OUTPUT.mkdir(exist_ok=True)
    html_path = OUTPUT / "hype-ma7-trade-paths.html"
    content = TEMPLATE.read_text()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    assert content.count("__FROZEN_DATA__") == 1
    html_path.write_text(content.replace("__FROZEN_DATA__", payload))
    audit.update({"renderer_sha256": sha(Path(__file__)), "template_sha256": sha(TEMPLATE),
                  "html_sha256": sha(html_path), "html_bytes": html_path.stat().st_size,
                  "created_at_utc": str(pd.Timestamp.now(tz="UTC"))})
    (OUTPUT / "chart_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(html_path), "audit": audit["arms"], "bytes": audit["html_bytes"]}, indent=2))


if __name__ == "__main__":
    main()
