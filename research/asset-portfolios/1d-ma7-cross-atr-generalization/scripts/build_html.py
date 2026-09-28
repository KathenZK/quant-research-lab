"""Saved-result-only local HTML; no simulation, network, or indicator recalculation."""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
import pandas as pd


BASE = Path(__file__).resolve().parents[1]
CASES = ("F0", "H4_D0", "H4_D2", "H4_D3")
LABELS = {"F0": "固定1.5ATR", "H4_D0": "高低价4天后收紧", "H4_D2": "收紧＋穿越后最多等待2天", "H4_D3": "收紧＋穿越后最多等待3天"}
COHORT_LABELS = {"main_full": "完整433天", "partial_long": "其它至少180天", "short": "不足180天，仅描述"}


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ms(value):
    return None if value is None or pd.isna(value) else int(pd.Timestamp(value).value // 1_000_000)


def finite(value):
    return float(value) if value is not None and pd.notna(value) and np.isfinite(float(value)) else None


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.floating, float)):
        return finite(value)
    return value


def dumps(value):
    return json.dumps(clean(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def read_csv(path):
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def alias(row, *names, default=None):
    for name in names:
        value = row.get(name)
        if value is not None and not pd.isna(value):
            return value
    return default


def rules(config):
    wait = int(config.get("entry_wait_days", 0))
    text = "日收盘穿越MA7，且方向斜率严格超过0.05ATR/日，次日开盘入场。"
    if wait:
        text += (f"空仓时若穿越日斜率不足，最多等后续{wait}个完整日；首次同时满足仍在MA同侧、斜率过线、"
                 "收盘越过原穿越日收盘价，就在下一日开仓。回到或等于MA、反向穿越、过期就取消；不复用持仓期间的穿越。")
    if config.get("progress_days", 0):
        text += ("多单看完整持仓日最高价，空单看最低价；首日初始化，连续4天不刷新后启动，"
                 "ATR倍数从1.5每天减0.2至0.5，再次刷新不会取消启动。")
    else:
        text += "ATR倍数固定1.5，不启用高低价停滞收紧。"
    return text + "止损始终围绕MA7±倍数×ATR14计算，实际线只收窄，次日生效；开盘越过止损按开盘退出。空单保留加速下跌＋RSI6≤30且预计扣费用后盈利时退出；关闭反手。"


class SavedResults:
    def __init__(self, directory):
        self.directory = directory
        path = directory / "artifact_checksums.json"
        self.checksums = json.loads(path.read_text())
        if "files" in self.checksums:
            self.checksums = self.checksums["files"]
        self.checked = {}
        self.manifest = json.loads(self.verified("run_manifest.json").read_text())

    def verified(self, relative):
        relative = str(relative)
        assert relative in self.checksums, f"Result not pinned: {relative}"
        path = self.directory / relative
        if relative not in self.checked:
            expected = self.checksums[relative]
            if isinstance(expected, dict):
                expected = expected["sha256"]
            value = sha(path)
            assert value == expected, f"Saved result changed: {relative}"
            self.checked[relative] = value
        return path

    def csv(self, relative):
        return read_csv(self.verified(relative))

    def optional_json(self, relative):
        if relative not in self.checksums:
            return None
        return json.loads(self.verified(relative).read_text())


def assert_account(summary, trades, stops, curve):
    assert len(trades) == int(summary["trades"])
    net = float(trades.net_pnl.sum()) if len(trades) else 0.0
    assert abs(10000.0 + net - summary["ending_equity"]) < 1e-6
    assert abs(float(curve.equity.iloc[-1]) - summary["ending_equity"]) < 1e-6
    assert len(stops) == 0 if len(trades) == 0 else len(stops) >= len(trades)


def chart_trade(record, rows, daily_index):
    t = record
    rows = rows.sort_values("timestamp", kind="stable")
    assert len(rows) and ms(rows.iloc[0].timestamp) == ms(t["entry_time"])
    assert (t["side"] * (rows.new_stop - rows.old_stop) >= -1e-10).all()
    assert (rows.new_mult <= rows.old_mult).all() and (rows.new_mult >= .5).all()
    assert abs(float(rows.iloc[-1].new_stop) - t["stop"]) < 1e-9
    assert int(rows.tightened.sum()) == t["tightening_days"]
    exit_at, exit_end = ms(t["exit_time"]), ms(t["exit_interval_end"])
    assert exit_end - exit_at == (3_600_000 if t["exit_reason"] == "stop_intrahour" else 0)
    assert all(ms(value) <= exit_at for value in rows.timestamp)
    progress = []
    for r in rows.itertuples():
        signal = daily_index[ms(r.signal_day)]
        progress.append({
            "ts": ms(r.timestamp), "signal": ms(r.signal_day), "stop": r.new_stop,
            "oldStop": r.old_stop, "oldMult": r.old_mult, "mult": r.new_mult,
            "tightened": bool(r.tightened), "trigger": r.tightening_trigger,
            "initialized": bool(r.initialized), "extreme": finite(r.extreme_price),
            "extremeDay": ms(r.extreme_day), "days": int(r.no_new_extreme_days),
            "armed": bool(r.new_armed), "armDay": ms(r.arm_day),
            "fullDay": bool(r.full_holding_day), "newExtreme": bool(r.new_extreme),
            "anchor": finite(r.anchor_candidate), "anchorDecisive": bool(r.anchor_decisive),
            "maCandidate": finite(r.natural_candidate),
            "finalMaCandidate": float(signal.ma - r.side * r.new_mult * signal.atr),
            "stalled": bool(r.stalled), "profitable": bool(r.profit_eligible),
        })
    return {
        "id": int(t["trade_id"]), "side": int(t["side"]), "entry": ms(t["entry_time"]),
        "exit": exit_at, "exitEnd": exit_end, "exitPlot": (exit_at + exit_end) // 2,
        "entryPrice": t["entry_price"], "exitPrice": t["exit_price"],
        "entryReason": t["entry_reason"], "exitReason": t["exit_reason"],
        "entryAtr": t["entry_atr"], "initialMult": t["initial_stop_mult"], "finalMult": t["stop_mult"],
        "tighteningDays": int(t["tightening_days"]), "armDay": ms(t["arm_day"]),
        "extreme": finite(t["extreme_price"]), "extremeDay": ms(t["extreme_day"]),
        "staleDays": int(t["no_new_extreme_days"]), "initialRiskPct": t["initial_stop_risk_pct"],
        "capApplied": bool(t["cap_applied"]), "signal": ms(t["signal_day"]), "cross": ms(t["cross_day"]),
        "waitDays": int(t.get("entry_wait_days_used", 0)),
        "tpSignal": ms(t.get("tp_signal_day")), "tpRsi": finite(t.get("tp_signal_rsi")),
        "oppositeSignal": None, "pnl": t["net_pnl"], "returnPct": t["return_on_entry_equity"] * 100,
        "fees": t["entry_fee"] + t["exit_fee"],
        "stops": [[p["ts"], p["stop"]] for p in progress],
        "stopAudit": [[p["ts"], p["oldMult"], p["mult"], p["tightened"], p["trigger"], p["stalled"], p["profitable"]] for p in progress],
        "progress": progress,
    }


def index_rows(frame):
    result = {}
    for row in frame.to_dict("records"):
        identifier = str(alias(row, "slug", "symbol", "market"))
        case = str(alias(row, "case_id", "case"))
        window = str(alias(row, "window", "scenario", "stress"))
        key = (identifier, case, window)
        assert key not in result, f"Duplicate summary key: {key}"
        result[key] = row
    return result


def lookup(index, slug, symbol, case, window):
    return index.get((slug, case, window), index.get((symbol, case, window)))


def compact_summary(full, early, late, slip, carry, days):
    item = {"returnPct": float(full["return_pct"]), "drawdownPct": abs(float(full["max_drawdown_pct"])),
            "trades": int(full["trades"]), "delayed": int(full.get("delayed_entries", 0)),
            "bankrupt": bool(full.get("bankrupt", False)), "endingEquity": float(full["ending_equity"]),
            "early": finite(early.get("return_pct")) if early else None,
            "late": finite(late.get("return_pct")) if late else None,
            "slippage": finite(slip.get("return_pct")) if slip else None,
            "carry": finite(carry.get("return_pct")) if carry else None}
    item["risk"] = bool(days >= 180 and item["trades"] >= 10 and item["returnPct"] > 0 and item["drawdownPct"] <= 30 and not item["bankrupt"])
    item["stable"] = bool(item["risk"] and early and late and int(early["trades"]) >= 3 and int(late["trades"]) >= 3
                          and all(item[key] is not None and item[key] > 0 for key in ("early", "late", "slippage", "carry")))
    return item


@lru_cache(maxsize=2)
def checked_template(path):
    template = path.read_text()
    assert template.count("__FROZEN_DATA__") == 1
    assert not re.search(r'<(?:script|link|iframe|img)\b[^>]+\b(?:src|href)\s*=', template, re.I)
    script = re.findall(r"<script>(.*?)</script>", template, re.S)
    assert len(script) == 1
    assert not re.search(r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource)\b", script[0])
    node = shutil.which("node") or "/Users/ZK/.nvm/versions/node/v22.17.1/bin/node"
    subprocess.run([node, "--check", "-"], input=script[0], text=True, check=True, capture_output=True)
    return template


def render_template(path, data):
    return checked_template(path).replace("__FROZEN_DATA__", dumps(data).replace("</", "<\\/"))


def build(results_dir, output_dir, analysis_dir=None):
    if output_dir.exists():
        raise FileExistsError("Use a new output directory; preserve previous HTML revisions")
    results = SavedResults(results_dir)
    scope = results.csv("scope.csv")
    summary_index = index_rows(results.csv("summary.csv"))
    stress_index = index_rows(results.csv("stress.csv"))
    configured = results.manifest.get("cases", [])
    if isinstance(configured, dict):
        configured = [{"case_id": key, "config": value} for key, value in configured.items()]
    assert set(c["case_id"] for c in configured) == set(CASES)
    config_by_id = {c["case_id"]: c for c in configured}
    output_dir.mkdir(parents=True, exist_ok=True)
    coins_dir = output_dir / "coins"
    coins_dir.mkdir(exist_ok=True)
    market = {"cases": [{"case_id": case, "label": LABELS[case]} for case in CASES], "rows": [],
              "marketSummary": results.optional_json("market_summary.json")}
    analysis_checks, ranking_index = {}, {}
    if analysis_dir is not None:
        analysis_hashes = json.loads((analysis_dir / "artifact_checksums.json").read_text())
        for name in ("market_summary.json", "ranking.csv", "source_manifest.json"):
            assert sha(analysis_dir / name) == analysis_hashes[name], f"Saved analysis changed: {name}"
            analysis_checks[name] = analysis_hashes[name]
        market["marketSummary"] = json.loads((analysis_dir / "market_summary.json").read_text())
        ranking_index = index_rows(read_csv(analysis_dir / "ranking.csv"))
        source_manifest = json.loads((analysis_dir / "source_manifest.json").read_text())
        assert source_manifest["result_checksums_sha256"] == sha(results_dir / "artifact_checksums.json")
    audit = {"source_manifest_sha256": sha(results_dir / "run_manifest.json"), "coins": {},
             "no_simulation": True, "no_indicator_recalculation": True, "browser_qa_performed": False,
             "equity_chart_sampling": "last saved account record per UTC calendar day; drawdown is unchanged hourly summary",
             "all_declared_cases_included": True, "templates": {}, "outputs": {}, "analysis_files": analysis_checks}
    for name in ("market_template.html", "coin_template.html"):
        audit["templates"][name] = sha(Path(__file__).with_name(name))
    for source in scope.to_dict("records"):
        symbol = str(alias(source, "symbol", "market", "coin"))
        slug = str(alias(source, "slug", default=symbol.replace("/", "_").replace(":", "_")))
        assert re.fullmatch(r"[\w.-]+", slug) and slug not in {".", ".."}, f"Unsafe coin filename: {slug}"
        full_rows = {case: lookup(summary_index, slug, symbol, case, "full") for case in CASES}
        has_page = any(full_rows.values())
        item = {"symbol": symbol, "slug": slug, "status": str(alias(source, "status", default="")),
                "reason": str(alias(source, "reason", "exclusion_reason", "error", default="")),
                "hasPage": has_page, "cases": {}, "cohort": "excluded", "days": 0, "start": None, "end": None,
                "improvement": None, "delay2": None, "delay3": None, "dataEndedEarly": False}
        if not item["reason"]:
            item["reason"] = {"NO_USABLE_TRADING_WINDOW": "没有通过检查且完成预热的连续交易区间",
                              "EXECUTION_FAILED": "账户回测执行失败，详见失败记录"}.get(item["status"], "")
        if not has_page:
            market["rows"].append(item)
            continue
        assert all(full_rows.values()), f"Missing full case: {symbol}"
        base_summary_path = results.verified(f"runs/{slug}/H4_D0/full/summary.json")
        base_summary = json.loads(base_summary_path.read_text())
        start, end = pd.Timestamp(base_summary["start"]), pd.Timestamp(base_summary["end_exclusive"])
        days = int((end - start).total_seconds() / 86400)
        cohort = "main_full" if start == pd.Timestamp("2025-06-29", tz="UTC") and end == pd.Timestamp("2026-09-05", tz="UTC") else "partial_long" if days >= 180 else "short"
        item.update(cohort=cohort, days=days, start=str(start.date()), end=str((end - pd.Timedelta(days=1)).date()))
        daily = results.csv(f"market/{slug}/daily_features.csv")
        metadata = json.loads(results.verified(f"market/{slug}/metadata.json").read_text())
        item["dataEndedEarly"] = bool(metadata["boundary_end_due_to_data"])
        assert len(daily) and not pd.to_datetime(daily.timestamp, utc=True).duplicated().any()
        assert pd.to_datetime(daily.timestamp, utc=True).diff().dropna().eq(pd.Timedelta(days=1)).all()
        daily_index = {ms(r.timestamp): r for r in daily.itertuples()}
        candles = [[ms(r.timestamp), r.open, r.high, r.low, r.close, finite(r.ma), finite(r.atr),
                    finite(r.rsi), finite(r.slope), int(r.cross), bool(r.accel1)] for r in daily.itertuples()]
        chart = {"symbol": symbol, "slug": slug, "cohortLabel": COHORT_LABELS[cohort], "start": ms(start),
                 "end": ms(end), "candles": candles, "defaultArm": "H4_D0", "arms": {}, "comparison": [], "buyHold": None,
                 "dataEndedEarly": item["dataEndedEarly"]}
        coin_audit = {"candles": len(candles), "data_ended_early": item["dataEndedEarly"], "cases": {}}
        for case in CASES:
            run_dir = f"runs/{slug}/{case}/full"
            summary = json.loads(results.verified(f"{run_dir}/summary.json").read_text())
            trades, stops = results.csv(f"{run_dir}/trades.csv"), results.csv(f"{run_dir}/stops.csv")
            curve = pd.read_parquet(results.verified(f"{run_dir}/equity.parquet"))
            assert_account(summary, trades, stops, curve)
            assert summary["start"] == base_summary["start"] and summary["end_exclusive"] == base_summary["end_exclusive"]
            assert not summary["reverse"] and summary["fee"] == .0005 and summary["slip"] == .0003
            assert summary["price_only_diagnostic"] and summary["progress_source"] == "high_low"
            config = config_by_id[case].get("config", summary)
            for key, value in config.items():
                assert summary[key] == value, f"Frozen config mismatch: {symbol}/{case}/{key}"
            chart_trades = [chart_trade(t, stops[stops.trade_id == t["trade_id"]], daily_index) for t in trades.to_dict("records")]
            assert sum(len(t["progress"]) for t in chart_trades) == len(stops)
            curve["timestamp"] = pd.to_datetime(curve.timestamp, utc=True)
            curve = curve.groupby("timestamp", sort=True, as_index=False).last()
            sampled = curve.groupby(curve.timestamp.dt.floor("D"), sort=True).tail(1)
            equity = [[ms(r.timestamp), float(r.equity)] for r in sampled.itertuples()]
            if equity[0][0] > ms(start):
                equity.insert(0, [ms(start), 10000.0])
            assert abs(equity[-1][1] - summary["ending_equity"]) < 1e-6
            chart["arms"][case] = {"label": LABELS[case], "rules": rules(config), "summary": summary,
                                    "trades": chart_trades, "equity": equity}
            for field in ("return_pct", "max_drawdown_pct", "trades", "ending_equity"):
                assert np.isclose(float(full_rows[case][field]), float(summary[field]), rtol=1e-12, atol=1e-8)
            early = lookup(summary_index, slug, symbol, case, "early60")
            late = lookup(summary_index, slug, symbol, case, "late40")
            slip = lookup(stress_index, slug, symbol, case, "slippage_10bp")
            carry = lookup(stress_index, slug, symbol, case, "carry_5bp_day")
            assert slip is not None and carry is not None, f"Missing all-coin stress: {symbol}/{case}"
            item["cases"][case] = compact_summary(summary, early, late, slip, carry, days)
            if ranking_index:
                ranked = lookup(ranking_index, slug, symbol, case, "full")
                assert ranked is not None, f"Missing independently saved ranking: {symbol}/{case}"
                assert bool(ranked["risk_count_pass"]) == item["cases"][case]["risk"]
                assert bool(ranked["stable_candidate"]) == item["cases"][case]["stable"]
                assert bool(ranked["bankrupt"]) == item["cases"][case]["bankrupt"]
                assert abs(float(ranked["return_pct"]) - item["cases"][case]["returnPct"]) < 1e-8
                item["cases"][case]["buyHoldReturn"] = finite(ranked["buy_hold_return_pct"])
                item["cases"][case]["buyHoldDrawdown"] = abs(float(ranked["buy_hold_drawdown_pct"]))
                chart["buyHold"] = {"returnPct": item["cases"][case]["buyHoldReturn"],
                                     "drawdownPct": item["cases"][case]["buyHoldDrawdown"]}
            chart["comparison"].append({"case": case, "label": LABELS[case], **item["cases"][case]})
            coin_audit["cases"][case] = {"trades": len(chart_trades), "stop_rows": len(stops),
                                         "delayed_entries": summary["delayed_entries"], "daily_equity_points": len(equity),
                                         "bankrupt": bool(summary["bankrupt"]),
                                         "all_trades_included": True, "all_stop_rows_included": True}
        for case in CASES:
            item["cases"][case]["vsFixed"] = item["cases"][case]["returnPct"] - item["cases"]["F0"]["returnPct"]
        item["improvement"] = item["cases"]["H4_D0"]["returnPct"] - item["cases"]["F0"]["returnPct"]
        for n in (2, 3):
            item[f"delay{n}"] = item["cases"][f"H4_D{n}"]["returnPct"] - item["cases"]["H4_D0"]["returnPct"]
        path = coins_dir / f"{slug}.html"
        path.write_text(render_template(Path(__file__).with_name("coin_template.html"), chart))
        audit["outputs"][str(path.relative_to(output_dir))] = sha(path)
        audit["coins"][symbol] = coin_audit
        market["rows"].append(item)
        if len(audit["coins"]) % 100 == 0:
            print(f"Built {len(audit['coins'])} coin HTML pages", flush=True)
    assert len(market["rows"]) == len(scope) and len({r["slug"] for r in market["rows"]}) == len(scope)
    if market["marketSummary"]:
        aggregate = market["marketSummary"]
        assert aggregate["candidate_coins"] == len(market["rows"])
        assert aggregate["completed_coins"] == sum(r["hasPage"] for r in market["rows"])
        for group in aggregate["cohorts"]:
            cohort = "partial_long" if group["cohort"] == "partial" else group["cohort"]
            part = [r["cases"][group["case_id"]] for r in market["rows"] if r["cohort"] == cohort]
            assert group["coins"] == len(part)
            assert group["positive_coins"] == sum(r["returnPct"] > 0 for r in part)
            assert group["risk_count_pass_coins"] == sum(r["risk"] for r in part)
            assert group["stable_candidate_coins"] == sum(r["stable"] for r in part)
            assert np.isclose(group["median_return_pct"], np.median([r["returnPct"] for r in part]), atol=1e-8)
            assert np.isclose(abs(group["median_max_drawdown_pct"]), np.median([r["drawdownPct"] for r in part]), atol=1e-8)
        audit["independent_cohort_summaries_verified"] = True
    for row in market["rows"]:
        assert (coins_dir / f"{row['slug']}.html").exists() == row["hasPage"]
    market_path = output_dir / "market_payload.json"
    market_path.write_text(dumps(market) + "\n")
    index_path = output_dir / "index.html"
    index_path.write_text(render_template(Path(__file__).with_name("market_template.html"), market))
    audit["outputs"]["index.html"] = sha(index_path)
    audit["outputs"]["market_payload.json"] = sha(market_path)
    audit["source_files"] = results.checked
    audit["scope_rows"] = len(scope)
    audit["coin_pages"] = len(audit["coins"])
    audit["total_trades_included"] = sum(a["trades"] for c in audit["coins"].values() for a in c["cases"].values())
    audit["total_stop_rows_included"] = sum(a["stop_rows"] for c in audit["coins"].values() for a in c["cases"].values())
    audit["data_ended_early_coin_pages"] = sum(c["data_ended_early"] for c in audit["coins"].values())
    audit["bankrupt_coin_case_views"] = sum(a["bankrupt"] for c in audit["coins"].values() for a in c["cases"].values())
    audit["builder_sha256"] = sha(Path(__file__))
    (output_dir / "chart_audit.json").write_text(json.dumps(clean(audit), ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: audit[key] for key in ("scope_rows", "coin_pages", "total_trades_included", "total_stop_rows_included")}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=BASE / "artifacts/results_20260909")
    parser.add_argument("--output", type=Path, default=BASE / "artifacts/html_20260909_v2")
    parser.add_argument("--analysis", type=Path, default=BASE / "artifacts/analysis_20260909")
    args = parser.parse_args()
    build(args.results, args.output, args.analysis)


if __name__ == "__main__":
    main()
