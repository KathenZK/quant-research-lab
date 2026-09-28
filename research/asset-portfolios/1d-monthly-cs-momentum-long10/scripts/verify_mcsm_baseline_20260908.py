#!/usr/bin/env python3
"""只验证 Top10 原始固定数量基线；遇到最早净账缺口即停止。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from strategy_lab.data.research_bundle import require_research_startup
from research_binance_1d_mcsm_lifecycle_20260908 import make_panels, select_month
from mcsm_baseline_accounting_20260908 import AccountingError, LinearPerpAccount

ROOT = Path(__file__).resolve().parents[4]
FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/baseline-verification-20260908"
INPUT = FAMILY / "artifacts/lifecycle-inputs-20260908"
SPEC = FAMILY / "specs/binance-1d-mcsm-baseline-verification-20260908.md"
FRAME_SHA = "3565255edeafcdc5dd3083191b820d2302f993e4ac89679bd812e43601e7049a"
SIGNAL_CODE_SHA = "faf1e764c2babd586cb96b997aeb771cf2d24e3689bb19678ad5e86089d2157b"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        handle.write("\n")


def load_verified_returned_daily() -> pd.DataFrame:
    """只读已固定返回帧及其完整证据链，不把 startup 当原始湖读取许可证。"""
    summary = json.loads((INPUT / "summary.json").read_text())
    if (summary["status"] != "PRICE_DIAGNOSTIC_INPUTS_VERIFIED"
            or not summary["all_requested_symbols_passed"] or summary["returned_symbols"] != 874):
        raise ValueError("incomplete prior returned input")
    if sha(INPUT / "daily-returned-frames.parquet") != FRAME_SHA or summary["parquet_sha256"] != FRAME_SHA:
        raise ValueError("returned frame hash changed")
    for path, digest in summary["source_sha256"].items():
        if sha(ROOT / path) != digest:
            raise ValueError(f"changed prior input source: {path}")
    for receipt in summary["startup_receipts"]:
        for role in ("request", "report"):
            if sha(INPUT / receipt[f"{role}_path"]) != receipt[f"{role}_sha256"]:
                raise ValueError("changed prior input receipt")
    signal_path = FAMILY / "scripts/research_binance_1d_mcsm_lifecycle_20260908.py"
    if sha(signal_path) != SIGNAL_CODE_SHA:
        raise ValueError("frozen calendar selector changed")
    return pd.read_parquet(INPUT / "daily-returned-frames.parquet")


def prepare_plan() -> None:
    p = make_panels(load_verified_returned_daily())
    selections, needs, ranked = [], [], []
    for month in pd.date_range("2020-03-01", "2026-06-01", freq="MS", tz="UTC"):
        pool = select_month(p, month)
        entry = month + pd.Timedelta(minutes=15)
        end = month + pd.offsets.MonthBegin(1) + pd.Timedelta(minutes=15)
        for rank, row in pool.iterrows():
            ranked.append({"month": month, "entry": entry, "symbol": row.symbol,
                           "observed_rank": rank + 1, "formation_return": row.signal,
                           "adv30": row.adv30, "identity_approved": False})
            if rank < 10:
                selections.append({"month": month, "entry": entry, "symbol": row.symbol,
                                   "observed_rank": rank + 1, "initial_target_weight": .1,
                                   "nomination_only_not_approved_order": True})
                needs.append({"symbol": row.symbol, "start": entry, "end": end,
                              "needs": "identity;entry;held marks;funding calendar;native funding mark;terminal"})
    directory = OUT / "plan"
    directory.mkdir(parents=True, exist_ok=False)
    tables = {"ranked-candidates": pd.DataFrame(ranked), "observed-top10-nominations": pd.DataFrame(selections),
              "required-holding-windows": pd.DataFrame(needs)}
    for name, table in tables.items():
        table.to_csv(directory / f"{name}.csv", index=False)
    first = tables["observed-top10-nominations"]
    first = first[first.month.eq(pd.Timestamp("2020-03-01", tz="UTC"))]
    original = json.loads((INPUT / "summary.json").read_text())["request"]
    request = dict(original, timeframe="15m", symbols=sorted(first.symbol.tolist()),
                   start="2020-02-29T23:45:00Z", end="2020-04-01T00:30:00Z")
    save(directory / "first-month-price-request.json", request)
    save(directory / "summary.json", {
        "status": "ORDER_NOMINATIONS_AND_REQUIRED_WINDOWS_ONLY", "months": 76,
        "nominations": len(tables["observed-top10-nominations"]),
        "first_month_symbols": first.symbol.tolist(), "initial_cash_usdt": 100_000,
        "contract_sha256": sha(SPEC), "script_sha256": sha(Path(__file__)),
        "daily_returned_frame_sha256": FRAME_SHA, "selector_code_sha256": SIGNAL_CODE_SHA,
        "price_request_sha256": sha(directory / "first-month-price-request.json"),
        "net_calculated": False, "identity_approved": False,
        "notes": "All calendar nominations are frozen before cash-return calculation; official historical eligibility still required.",
        "evidence_sha256": {f.name: sha(f) for f in directory.glob("*.csv")},
    })
    print(first.to_string(index=False), flush=True)


def load_first_month_prices() -> None:
    request = json.loads((OUT / "plan/first-month-price-request.json").read_text())
    inputs = require_research_startup(request, project_root=ROOT)
    save(OUT / "first-month-price-startup.json", inputs.report)
    frame = pd.concat(inputs.prices.values(), ignore_index=True)
    path = OUT / "first-month-returned-15m.parquet"
    if path.exists():
        raise FileExistsError(path)
    frame.to_parquet(path, index=False, compression="zstd")
    save(OUT / "first-month-price-receipt.json", {
        "parquet_sha256": sha(path), "rows": len(frame), "symbols": frame.symbol.nunique(),
        "startup_report_sha256": sha(OUT / "first-month-price-startup.json"),
        "request_sha256": sha(OUT / "plan/first-month-price-request.json"),
        "status": inputs.report["status"], "net_verified": False,
    })
    print({"status": inputs.report["status"], "rows": len(frame), "symbols": frame.symbol.nunique()}, flush=True)


def recheck_ada_formation() -> None:
    request_path = FAMILY / "specs/baseline-ada-formation-request-20260908.json"
    request = json.loads(request_path.read_text())
    inputs = require_research_startup(request, project_root=ROOT)
    directory = OUT / "formation-recheck"
    directory.mkdir(parents=True, exist_ok=False)
    save(directory / "ada-startup-report.json", inputs.report)
    frame = inputs.prices["ADA/USDT:USDT"].copy()
    frame.to_parquet(directory / "ada-returned-15m.parquet", index=False, compression="zstd")
    frame["day"] = frame.ts.dt.floor("D")
    daily = frame.groupby("day").agg(bars=("ts", "size"), quote_volume=("quote_volume", "sum"))
    a = pd.Timestamp("2020-01-31T23:45:00Z")
    b = pd.Timestamp("2020-02-29T23:45:00Z")
    indexed = frame.set_index("ts")
    begin, end = indexed.loc[a], indexed.loc[b]
    continuous = bool(pd.notna(begin.research_segment_id) and begin.research_segment_id == end.research_segment_id)
    formation = float(end.close / begin.close - 1)
    adv = float(daily.loc["2020-01-31":"2020-02-29", "quote_volume"].mean())
    summary = {
        "status": "ORIGINAL_PARTIAL_ENDPOINT_RECHECK_NOT_PERFORMANCE",
        "initial_daily_plan_status": "REJECTED_AS_ORIGINAL_BASELINE_PARITY",
        "reason": "Complete 1d resampling excludes ADA partial listing day whereas original endpoint required >=48 of 96 bars.",
        "jan31_observed_15m_bars": int(daily.loc["2020-01-31", "bars"]),
        "feb29_observed_15m_bars": int(daily.loc["2020-02-29", "bars"]),
        "formation_endpoint_path_one_segment": continuous,
        "formation_return": formation, "adv30": adv,
        "original_endpoint_and_adv_eligible": bool(continuous and daily.loc["2020-01-31", "bars"] >= 48 and adv >= 10_000_000),
        "entry_open_0015": float(indexed.loc[pd.Timestamp("2020-03-01T00:15:00Z"), "open"]),
        "request_sha256": sha(request_path), "startup_report_sha256": sha(directory / "ada-startup-report.json"),
        "returned_frame_sha256": sha(directory / "ada-returned-15m.parquet"),
        "net_calculated": False,
    }
    save(directory / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def baseline_gate_closeout() -> None:
    """实际源值缺失必须挡住第一笔资金现金流，不输出续算/跳月净值。"""
    directory = OUT / "accounting-gate"
    directory.mkdir(parents=True, exist_ok=False)
    price_receipt = json.loads((OUT / "first-month-price-receipt.json").read_text())
    price_path = OUT / "first-month-returned-15m.parquet"
    ada_receipt = json.loads((OUT / "formation-recheck/summary.json").read_text())
    ada_path = OUT / "formation-recheck/ada-returned-15m.parquet"
    if sha(price_path) != price_receipt["parquet_sha256"] or sha(ada_path) != ada_receipt["returned_frame_sha256"]:
        raise ValueError("verified returned price frame changed")
    if not ada_receipt["original_endpoint_and_adv_eligible"]:
        raise ValueError("ADA original qualification not established")
    audit = json.loads((FAMILY / "artifacts/funding-source-20260908/summary.json").read_text())
    old_path = FAMILY / "artifacts/binance-1d-mcsm-long10-diagnostic-2026-08-18-holdings.csv"
    expected = next(r["sha256"] for r in audit["legacy_inputs"] if r["path"] == str(old_path.relative_to(ROOT)))
    if sha(old_path) != expected:
        raise ValueError("original frozen order nominations changed")
    old = pd.read_csv(old_path)
    row = old.loc[old.variant.eq("adv10m_top10_long_only") & old.rebalance.eq("2020-03-01")].iloc[0]
    names = [s + "/USDT:USDT" for s in row.longs.split(",")]
    if len(names) != 10 or len(set(names)) != 10:
        raise ValueError("original March Top10 identity mismatch")
    bars = pd.concat([pd.read_parquet(price_path), pd.read_parquet(ada_path)], ignore_index=True)
    entry = pd.Timestamp("2020-03-01T00:15:00Z")
    prior = bars.loc[bars.ts.eq(entry-pd.Timedelta(minutes=15))].set_index("symbol").loc[names]
    at_entry = bars.loc[bars.ts.eq(entry)].set_index("symbol").loc[names]
    if not prior.research_window_valid.all() or not at_entry.open.gt(0).all():
        raise ValueError("missing prior closed activity or reference entry")
    prices = at_entry.open.to_dict()
    account = LinearPerpAccount(initial_cash=100_000)
    entry_row = account.rebalance(entry.to_pydatetime(), {s: .1 for s in names}, prices)
    save(directory / "reference-entry-accounting.json", {
        "status": "REFERENCE_PRICE_ENTRY_ACCOUNTING_ONLY_NOT_VERIFIED_FILLS", "symbols": names,
        "source": str(old_path.relative_to(ROOT)), "source_sha256": expected,
        "prior_completed_bar_used_for_activity": True, "entry_bar_future_volume_used_for_selection": False,
        "ledger": entry_row, "identity_and_execution_approved": False,
    })
    probe = json.loads((OUT / "funding-evidence/probe-summary.json").read_text())
    receipt = next(r for r in probe["results"] if r["symbol"] == "BTCUSDT" and r["start_utc"] == "2020-03-01")
    raw = ROOT / receipt["raw_path"]
    if sha(raw) != receipt["raw_sha256"]:
        raise ValueError("official funding raw response changed")
    native = json.loads(raw.read_text())
    after_entry = sorted((r for r in native if pd.Timestamp(r["fundingTime"], unit="ms", tz="UTC") > entry),
                         key=lambda r: r["fundingTime"])
    first = after_entry[0]
    timestamp = pd.Timestamp(first["fundingTime"], unit="ms", tz="UTC")
    before = account.snapshot()
    try:
        account.funding(timestamp.to_pydatetime(), "BTC/USDT:USDT", float(first["fundingRate"]), first.get("markPrice"))
    except AccountingError as exc:
        error = str(exc)
    else:
        raise AssertionError("Expected actual missing native mark to halt baseline verification")
    if account.snapshot() != before:
        raise AssertionError("failed event changed cash/positions")
    save(directory / "first-held-funding-rejection.json", {
        "status": "ACTUAL_SOURCE_MISSING_MARK_REJECTED", "event_time_utc": timestamp.isoformat(),
        "symbol": "BTC/USDT:USDT", "is_original_first_month_holding": "BTC/USDT:USDT" in names,
        "native_event": first, "raw_source_path": str(raw.relative_to(ROOT)), "raw_source_sha256": sha(raw),
        "native_mark_is_empty": first.get("markPrice") in (None, ""), "error": error,
        "account_unchanged": True, "funding_not_zero_filled": True,
        "note": "Confirmed first post-entry BTC funding timestamp; this is an input/accounting gate demonstration, not approved trade or portfolio NAV.",
    })
    # Real identity review has not been completed; do not manufacture accepted evidence.
    req = json.loads((OUT / "plan/first-month-price-request.json").read_text())
    req.update(mode="net_research", asset_policy="crypto_only", symbols=sorted(names))
    save(directory / "net-request-not-approved.json", req)
    try:
        require_research_startup(req, project_root=ROOT)
    except ValueError as exc:
        net_gate_error = str(exc)
    else:
        raise AssertionError("net startup unexpectedly approved missing identity review")
    save(OUT / "summary.json", {
        "status": "BASELINE_NOT_VERIFIED", "requested_months": 76, "net_account_months_reconstructed": 0,
        "net_profit_usdt": None, "total_net_return": None, "alpha_tested": False,
        "original_march_symbols": names, "initial_1d_only_plan_rejected": True,
        "ada_partial_endpoint_recovered": True,
        "first_confirmed_held_funding_gap": {"symbol": "BTC/USDT:USDT", "time": timestamp.isoformat(),
                                              "missing": "native settlement markPrice"},
        "funding_gap_origin": "Official HTTP200 fundingRate response contains empty markPrice, not just an unfetched local field",
        "net_startup_status": "REJECTED", "net_startup_error": net_gate_error,
        "remaining_requirements": ["full 76-month original-signal and historical-identity reconstruction",
                                   "exact native funding marks and complete settlement evidence for all actual holding windows",
                                   "BNX/VIDT actual terminal settlement price and applicable fees",
                                   "full continuous price/funding/fee/slippage account, margin and execution limitations"],
        "no_missing_months_compounded": True, "no_mark_proxy_used": True, "no_funding_zero_fill": True,
        "script_sha256": sha(Path(__file__)), "contract_sha256": sha(SPEC),
        "accounting_kernel_sha256": sha(FAMILY / "scripts/mcsm_baseline_accounting_20260908.py"),
        "evidence_sha256": {str(p.relative_to(OUT)): sha(p) for p in sorted(directory.glob("*.json"))},
    })
    print(json.dumps({"status": "BASELINE_NOT_VERIFIED", "earliest_confirmed_gap": timestamp.isoformat(),
                      "missing": "BTC native settlement markPrice", "net_return": None,
                      "accounting_rejection": error, "net_startup_rejection": net_gate_error}, ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "first-month-prices", "ada-formation-recheck", "closeout"))
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare_plan()
    elif args.phase == "first-month-prices":
        load_first_month_prices()
    elif args.phase == "ada-formation-recheck":
        recheck_ada_formation()
    else:
        baseline_gate_closeout()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
