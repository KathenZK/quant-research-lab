"""Render every frozen R3 trade from saved ledgers; no simulation or indicators."""
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
RESULTS = BASE / "artifacts/r3_price_progress_20260909"
OUTPUT = BASE / "artifacts/r3_trade_paths_20260909"
TEMPLATE = Path(__file__).with_name("trade_path_template_r3.html")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ms(value):
    return None if pd.isna(value) else int(pd.Timestamp(value).value // 1_000_000)


def finite(value):
    return float(value) if pd.notna(value) and np.isfinite(value) else None


def rules(config):
    text = "日收盘穿越MA7，且顺交易方向的MA7斜率严格超过0.05ATR/日，次日开盘入场。关闭反手。"
    n = config["progress_days"]
    if n:
        text += (f"只用完整持仓日的日K最高/最低价：首日初始化，随后连续{n}个完成日未刷新持仓最高/最低价，"
                 "收盘启动；不要求浮盈。启动当日倍数减0.2，此后每天继续减到0.5；新极值仍更新，但不会撤销启动。")
        text += ("止损仍以MA7±倍数×ATR14计算。" if config["stop_anchor"] == "ma" else
                 "启动前以MA7计算止损；启动后同时加入持仓最高价−倍数×ATR14（多）或最低价＋倍数×ATR14（空），取更近者。")
    elif config["tighten_mode"] == "fixed":
        text += "MA7两侧的ATR倍数固定1.5，止损候选无法推进时保持旧线。"
    else:
        text += "沿用R2：只有当前MA止损候选无法继续推进，且收盘预估扣费用后仍盈利，当天倍数才减0.2，最低0.5。"
    if config["exit_opposite_cross"]:
        text += "持仓出现反向收盘穿越MA7，次日退出，无需斜率或浮盈，不用该次穿越重开。"
    if config["initial_stop_cap_pct"] is not None:
        text += "初始止损增加距含滑点入场价10%的保护，仅取更近者；费用和跳空后亏损可能超过10%。"
    return text + "实际止损只能收窄，日线更新次日00:00生效；若开盘已越过止损，按开盘退出。空单仍保留加速下跌、RSI6≤30且预估盈利时退出。"


def load_chart_data():
    original = json.loads((RESULTS / "artifact_checksums.json").read_text())

    def verified(relative):
        path = RESULTS / relative
        assert relative in original, f"Missing checksum: {relative}"
        assert sha(path) == original[relative], f"Frozen R3 result changed: {relative}"
        return path

    manifest = json.loads(verified("run_manifest.json").read_text())
    source_checks = {
        "engine_sha256": BASE / "scripts/engine_r3.py",
        "run_script_sha256": BASE / "scripts/run_r3.py",
        "contract_sha256": BASE / "specs/r3-price-progress-20260909.md",
        "input_checksums_sha256": INPUT / "checksums.json",
    }
    for key, path in source_checks.items():
        assert sha(path) == manifest[key], f"Frozen source changed: {key}"
    input_manifest = json.loads((INPUT / "checksums.json").read_text())
    for relative, checksum in input_manifest.items():
        assert sha(INPUT / relative) == checksum, f"Frozen input changed: {relative}"
    daily_path = verified("daily_features.csv")
    daily = pd.read_csv(daily_path)
    raw = pd.read_parquet(INPUT / "daily.parquet").rename(columns={"ts": "timestamp"})
    assert len(daily) == len(raw)
    assert pd.to_datetime(daily.timestamp, utc=True).equals(pd.to_datetime(raw.timestamp, utc=True))
    for column in ("open", "high", "low", "close"):
        np.testing.assert_allclose(daily[column], raw[column], rtol=1e-14, atol=1e-14)
    candles = [[ms(r.timestamp), r.open, r.high, r.low, r.close, finite(r.ma), finite(r.atr),
                finite(r.rsi), finite(r.slope), int(r.cross), bool(r.accel1)] for r in daily.itertuples()]
    start, end = manifest["windows"]["full"]
    assert len(manifest["cases"]) == 14 and manifest["primary_case"] == "P2_extreme"
    data = {"candles": candles, "start": ms(start), "end": ms(end),
            "defaultArm": manifest["primary_case"], "arms": {}}
    audit = {"parent_manifest_sha256": sha(RESULTS / "run_manifest.json"),
             "parent_artifact_checksums_sha256": sha(RESULTS / "artifact_checksums.json"),
             "frozen_sources_verified": {k: sha(v) for k, v in source_checks.items()},
             "input_files_verified": input_manifest, "source_files": {"daily_features.csv": sha(daily_path)},
             "candles": len(candles), "arms": {}, "default_arm": data["defaultArm"],
             "no_backtest_rerun": True, "no_indicator_recalculation": True,
             "daily_ohlc_matches_frozen_inputs": True, "all_declared_cases_included": True,
             "funding_window_verified": False, "browser_qa_performed": False,
             "extreme_source": "closed daily high/low wholly held by this position; never close or hourly high/low",
             "timestamp_semantics": "UTC; candle center noon; indicators at daily close; stops at effective time; intrahour exits centered within recorded uncertainty interval"}
    baseline = pd.read_csv(verified("runs/B0_r2_stall/full/trades.csv"))
    baseline_ids = {(int(t.side), ms(t.entry_time)): int(t.trade_id) for t in baseline.itertuples()}
    for case in manifest["cases"]:
        name, label, config = case["case_id"], case["label"], case["config"]
        files = {kind: verified(f"runs/{name}/full/{kind}.{ext}") for kind, ext in
                 [("trades", "csv"), ("stops", "csv"), ("equity", "parquet"), ("summary", "json")]}
        audit["source_files"].update({str(p.relative_to(RESULTS)): sha(p) for p in files.values()})
        trades, stops = pd.read_csv(files["trades"]), pd.read_csv(files["stops"])
        curve, summary = pd.read_parquet(files["equity"]), json.loads(files["summary"].read_text())
        for key, value in config.items():
            assert summary[key] == value, f"Case configuration mismatch: {name}/{key}"
        assert not summary["reverse"] and summary["fee"] == .0005 and summary["slip"] == .0003
        assert summary["price_only_diagnostic"] and summary["entry_mode"] == "original"
        chart_trades = []
        for t in trades.to_dict("records"):
            rows = stops[stops.trade_id == t["trade_id"]].sort_values("timestamp", kind="stable")
            assert len(rows) and ms(rows.iloc[0].timestamp) == ms(t["entry_time"])
            assert all(t["side"] * rows.new_stop.diff().dropna() >= -1e-10)
            assert abs(rows.iloc[-1].new_stop - t["stop"]) < 1e-9
            assert all(rows.new_mult <= rows.old_mult) and all(rows.new_mult >= .5)
            assert rows.iloc[-1].new_mult == t["stop_mult"]
            assert int(rows.tightened.sum()) == t["tightening_days"]
            a, b = ms(t["exit_time"]), ms(t["exit_interval_end"])
            assert b - a == (3_600_000 if t["exit_reason"] == "stop_intrahour" else 0)
            assert all(ms(v) <= a for v in rows.timestamp)
            progress = [{"ts": ms(r.timestamp), "signal": ms(r.signal_day), "stop": r.new_stop,
                         "oldStop": r.old_stop, "oldMult": r.old_mult, "mult": r.new_mult,
                         "tightened": bool(r.tightened), "trigger": r.tightening_trigger,
                         "initialized": bool(r.initialized), "extreme": finite(r.extreme_price),
                         "extremeDay": ms(r.extreme_day), "days": int(r.no_new_extreme_days),
                         "armed": bool(r.new_armed), "armDay": ms(r.arm_day),
                         "fullDay": bool(r.full_holding_day), "newExtreme": bool(r.new_extreme),
                         "anchor": finite(r.anchor_candidate), "anchorDecisive": bool(r.anchor_decisive),
                         "maCandidate": finite(r.natural_candidate), "stalled": bool(r.stalled),
                         "profitable": bool(r.profit_eligible)} for r in rows.itertuples()]
            chart_trades.append({
                "id": int(t["trade_id"]), "side": int(t["side"]), "entry": ms(t["entry_time"]),
                "exit": a, "exitEnd": b, "exitPlot": (a + b) // 2,
                "entryPrice": t["entry_price"], "exitPrice": t["exit_price"],
                "entryReference": t["entry_reference"], "exitReference": t["exit_reference"],
                "entryReason": t["entry_reason"], "exitReason": t["exit_reason"],
                "qualification": t["qualification"], "entryAtr": t["entry_atr"],
                "initialMult": t["initial_stop_mult"], "finalMult": t["stop_mult"],
                "tighteningDays": int(t["tightening_days"]), "armed": bool(t["armed"]),
                "armDay": ms(t["arm_day"]), "extreme": finite(t["extreme_price"]),
                "extremeDay": ms(t["extreme_day"]), "staleDays": int(t["no_new_extreme_days"]),
                "initialRiskPct": t["initial_stop_risk_pct"], "capApplied": bool(t["cap_applied"]),
                "baselineId": baseline_ids.get((int(t["side"]), ms(t["entry_time"]))),
                "signal": ms(t["signal_day"]), "cross": ms(t["cross_day"]),
                "oppositeSignal": ms(t.get("opposite_cross_signal_day")),
                "tpSignal": ms(t.get("tp_signal_day")), "tpRsi": finite(t.get("tp_signal_rsi")),
                "qty": t["qty"], "pnl": t["net_pnl"], "returnPct": t["return_on_entry_equity"] * 100,
                "fees": t["entry_fee"] + t["exit_fee"],
                "stops": [[ms(r.timestamp), r.new_stop] for r in rows.itertuples()],
                "stopAudit": [[p["ts"], p["oldMult"], p["mult"], p["tightened"], p["trigger"], p["stalled"], p["profitable"]] for p in progress],
                "progress": progress,
            })
        assert len(chart_trades) == summary["trades"]
        assert abs(sum(t["pnl"] for t in chart_trades) - (summary["ending_equity"] - 10000)) < 1e-7
        assert sum(t["tighteningDays"] for t in chart_trades) == summary["tightening_days"]
        line = curve.groupby("timestamp", sort=True).equity.last()
        chart_equity = [[ms(ts), float(value)] for ts, value in line.items()]
        assert abs(chart_equity[-1][1] - summary["ending_equity"]) < 1e-7
        data["arms"][name] = {"label": label, "rules": rules(config), "summary": summary,
                              "trades": chart_trades, "equity": chart_equity}
        audit["arms"][name] = {"trades": len(chart_trades), "stop_rows": len(stops),
                               "long": summary["long_trades"], "short": summary["short_trades"],
                               "return_pct": summary["return_pct"], "max_drawdown_pct": summary["max_drawdown_pct"],
                               "exit_reasons": trades.exit_reason.value_counts().to_dict(),
                               "tightening_days": summary["tightening_days"],
                               "same_entry_baseline_matches": sum(t["baselineId"] is not None for t in chart_trades),
                               "all_trades_and_stop_rows_included": True, "monotone_stop_verified": True,
                               "multiplier_ledger_verified": True, "exit_hour_intervals_verified": True}
    return data, audit


def main():
    data, audit = load_chart_data()
    OUTPUT.mkdir(exist_ok=True)
    html_path, payload_path = OUTPUT / "hype-ma7-r3-trade-paths.html", OUTPUT / "payload.json"
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
    print(json.dumps({"output": str(html_path), "arms": audit["arms"], "bytes": audit["html_bytes"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
