"""Complete the unchanged weekly account after two further official terminal events."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

import collect_weekly_terminals_20260924 as collector
import research_weekly_top10_20260924 as original
from audit_baseline_terminals_20260908 import text_nodes
from research_mcsm_weekly_20260911 import apply_known_terminals, pin, replay_price, save, sha

FAMILY, ROOT, START, END = original.FAMILY, original.ROOT, original.START, original.END
PRIOR = original.OUT
OUT = PRIOR / "terminal-complete"
EVIDENCE = OUT / "terminal-evidence"
SPEC = FAMILY / "specs/binance-1d-mcsm-weekly-top10-terminal-amendment-20260924.md"
EVENTS = [
    {"symbol": "COCOSUSDT", "terminal": "2023-05-25T09:00Z", "minutes": 60,
     "article": "45852dc155b641bc9e1c23bc41d8ded6"},
    {"symbol": "MEMEFIUSDT", "terminal": "2025-08-11T09:00Z", "minutes": 30,
     "article": "21e399dcea734230a3c181daf5407b64"},
]


def validate_prior():
    pin(Path(original.__file__), "3f1094f4451ff7026a4fded2ffde8c795fb38934aaf99c8e6bf9c9f2d0c2623e")
    pin(Path(collector.__file__), "68d47eef60f4c864cbd2138925547f2de421592a6635d1a356710e8c5ee18dfd")
    pin(PRIOR / "summary.json", "c41fe6e6542429a45d1a42dfad37165f6380003c61071dd8cb8b6fafa72e56cf")
    prior = json.loads((PRIOR / "summary.json").read_text())
    for name, digest in prior["files_sha256"].items():
        pin(PRIOR / name, digest)
    plan = json.loads((PRIOR / "plan.json").read_text())
    pin(original.SPEC, plan["contract_sha256"])
    return plan


def collect():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    collector.OUT = EVIDENCE  # Redirect only new HTTP evidence; frozen implementation is unchanged.
    planfile = EVIDENCE / "request-plan.json"
    if not planfile.exists():
        save(planfile, {"spec_sha256": sha(SPEC), "script_sha256": sha(Path(__file__)), "events": EVENTS,
                        "prior_summary_sha256": sha(PRIOR / "summary.json"), "no_full_weekly_return_available": True})
    plan = json.loads(planfile.read_text())
    pin(SPEC, plan["spec_sha256"])
    pin(Path(__file__), plan["script_sha256"])
    records = []
    for event in EVENTS:
        symbol, terminal = event["symbol"], pd.Timestamp(event["terminal"])
        url = "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode=" + event["article"]
        announcement, meta = collector.fetch(symbol + "-announcement.json", url)
        assert meta["status"] == 200
        payload = json.loads(announcement.read_text())
        assert payload["code"] == "000000"
        body = payload["data"]["body"]
        try:
            tree = json.loads(body)
        except json.JSONDecodeError:
            tree = json.loads(body.replace('\\"', '"'))
        words = text_nodes(tree)
        assert terminal.strftime("%Y-%m-%d %H:%M") in words and "automatic settlement" in words.lower()
        assert pd.Timestamp(payload["data"]["publishDate"], unit="ms", tz="UTC") < terminal
        name = f"{symbol}-1m-{terminal:%Y-%m-%d}.zip"
        url = f"https://data.binance.vision/data/futures/um/daily/indexPriceKlines/{symbol}/1m/{name}"
        source, meta = collector.fetch(name, url)
        if meta["status"] != 200:
            raise ValueError(f"official archive unavailable: {meta['status']}; no zero fill")
        check, meta = collector.fetch(name + ".CHECKSUM", url + ".CHECKSUM")
        assert meta["status"] == 200 and check.read_text().split()[0] == sha(source)
        with zipfile.ZipFile(source) as z:
            assert len(z.namelist()) == 1
            rows = list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())))
        hour, _ = collector.validate_minutes(rows, terminal)
        window = hour[-event["minutes"]:]
        values = np.array([[float(v) for v in r[1:5]] for r in window])
        target = EVIDENCE / (symbol + "-terminal-minute-window.json")
        save(target, window)
        item = {"symbol": symbol[:-4] + "/USDT:USDT", "ts": terminal,
                "center": float(values.mean()), "low": float(values[:, 2].mean()), "high": float(values[:, 1].mean()),
                "minute_count": len(window), "source_quality": "CONDITIONAL_INDEX_PROXY_NOT_EXACT_SETTLEMENT"}
        for kind, path in [("source", source), ("announcement", announcement), ("window", target)]:
            item[kind + "_path"], item[kind + "_sha256"] = str(path.relative_to(FAMILY)), sha(path)
        records.append(item)
        print(json.dumps(item, default=str), flush=True)
    save(EVIDENCE / "summary.json", {"events": records, "exact_settlement_verified": False,
                                     "files_sha256": {str(p.relative_to(EVIDENCE)): sha(p)
                                                      for p in EVIDENCE.iterdir() if p.is_file()}})


def new_terms():
    summary = json.loads((EVIDENCE / "summary.json").read_text())
    for name, digest in summary["files_sha256"].items():
        pin(EVIDENCE / name, digest)
    return [{**r, "ts": pd.Timestamp(r["ts"])} for r in summary["events"]]


def verify_daily_coverage(h, daily):
    valid = {(r.ts, r.symbol): bool(r.eligible) and np.isfinite(r.close) and r.close > 0
             for r in daily.itertuples(index=False)}
    checked = 0
    for r in h.itertuples(index=False):
        for t in pd.date_range(r.entry_ts.floor("D") + original.DAY, r.exit_ts.floor("D"), freq="D"):
            if not valid.get((t - original.DAY, r.symbol), False):
                raise ValueError(f"unresolved daily price: {r.symbol} {t - original.DAY}")
            checked += 1
    return checked


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=["collect", "prepare", "execute"])
    args = p.parse_args()
    prior_plan = validate_prior()
    if args.phase == "collect":
        collect()
        return
    _, daily, endpoints, old_terms, _, hashes = original.load_inputs()
    terms = old_terms + original.load_new_terminals() + new_terms()
    h = pd.read_parquet(PRIOR / "holding-windows.parquet")
    h = apply_known_terminals(h, terms)
    original.validate_schedule(h)
    checks = verify_daily_coverage(h, daily)
    if args.phase == "prepare":
        h.to_parquet(OUT / "holding-windows.parquet", index=False)
        save(OUT / "plan.json", {"spec_sha256": sha(SPEC), "script_sha256": sha(Path(__file__)),
                                 "holdings_sha256": sha(OUT / "holding-windows.parquet"),
                                 "extra_terminal_sha256": sha(EVIDENCE / "summary.json"),
                                 "daily_marks_checked": checks, "start": START, "end": END,
                                 "common_grid": prior_plan["common_grid"], "scenarios": prior_plan["scenarios"],
                                 "retained_endpoint_hashes": hashes, "only_terminal_exits_changed": True})
        print(f"PLAN_READY daily_checks={checks}", flush=True)
        return
    plan = json.loads((OUT / "plan.json").read_text())
    for path, digest in [(SPEC, plan["spec_sha256"]), (Path(__file__), plan["script_sha256"]),
                         (OUT / "holding-windows.parquet", plan["holdings_sha256"]),
                         (EVIDENCE / "summary.json", plan["extra_terminal_sha256"])]:
        pin(path, digest)
    for name, digest in plan["retained_endpoint_hashes"].items():
        pin(ROOT / name, digest)
    grid = [pd.Timestamp(t) for t in plan["common_grid"]]
    results = []
    for sc in plan["scenarios"]:
        selected_terms = original.choose_terminals(terms, sc["terminal"])
        for strategy, held in h.groupby("strategy", sort=True):
            label = f"{strategy}-{sc['terminal']}-{round(sc['slip'] * 10000)}bp"
            print(f"REPLAY {label}", flush=True)
            directory = OUT / label
            directory.mkdir()
            result = replay_price(held, endpoints, daily, selected_terms, grid, sc["slip"], start=START, end=END)
            result["leg-price-pnl"] = original.leg_cash(held, result, endpoints, selected_terms)
            metrics = result.pop("metrics")
            nav = result["nav"].set_index("ts")
            turnovers = [float(g.traded_notional.sum()) / float(nav.loc[ts].equity)
                         for ts, g in result["trades"].groupby("ts")]
            metrics.update(strategy=strategy, terminal_scenario=sc["terminal"],
                           status="CONDITIONAL_TERMINAL_ESTIMATE_PRICE_ONLY_NOT_VERIFIED_NET",
                           traded_notional_usdt=float(result["trades"].traded_notional.sum()),
                           turnover_sum_equity_units=float(sum(turnovers)),
                           mean_rebalance_turnover_equity=float(np.mean(turnovers)),
                           weekly_or_monthly_win_rate=float(result["periods"]["return"].gt(0).mean()))
            if strategy == "B0":
                previous = json.loads((PRIOR / label / "summary.json").read_text())
                for key in ["final_equity", "fees_usdt", "slippage_usdt", "max_drawdown_common_grid"]:
                    assert np.isclose(previous[key], metrics[key], rtol=1e-12, atol=1e-7)
            for name, frame in result.items():
                frame.to_parquet(directory / f"{name}.parquet", index=False)
            save(directory / "summary.json", metrics)
            results.append(metrics)
            print(json.dumps({k: metrics[k] for k in ["strategy", "total_return", "cagr_365_25",
                                                     "max_drawdown_common_grid", "terminal_closes"]}), flush=True)
    save(OUT / "summary.json", {"status": "COMPUTED_PENDING_INDEPENDENT_AUDIT", "accounts": results,
                                "funding_included": False, "exact_terminal_settlement_verified": False,
                                "prior_failed_summary_sha256": sha(PRIOR / "summary.json"),
                                "files_sha256": {str(p.relative_to(OUT)): sha(p)
                                                 for p in sorted(OUT.rglob("*")) if p.is_file()}})


if __name__ == "__main__":
    main()
