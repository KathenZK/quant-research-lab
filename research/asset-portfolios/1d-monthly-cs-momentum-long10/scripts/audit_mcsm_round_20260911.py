"""Independent new-round checks; never imports the candidate exit or account maths."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from audit_mcsm_single_exit_account_20260910 import check_complete_nav, reconstruct
from audit_mcsm_funding_account_bridge_20260910 import terminals_from_raw
from verify_mcsm_baseline_20260908 import load_verified_returned_daily

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
ROUND = FAMILY / "artifacts/drawdown-frequency-round-20260911"
OLD = FAMILY / "artifacts/mechanism-round-20260910"
BASE = FAMILY / "artifacts/baseline-estimate-20260909"
CONTRACT_SHA = "aa38d87cf3cb374d4f587faf3660586950986bfa2a25813e851d65c28862d2d4"
NATIVE_SHA = "fc57b942e14ab29007256326404c698f379d24988a0da274fe4434b0d9c70990"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, default=str, allow_nan=False)
        stream.write("\n")


def verify_hashes(mapping, base):
    for path, expected in mapping.items():
        if sha(base / path) != expected:
            raise ValueError(f"changed evidence: {path}")


def independent_plan(holdings, original, daily, rule):
    """Use exact calendar-day closes, not the candidate feature table or ranking."""
    if rule not in ("x5", "x10"):
        raise ValueError("unknown rule")
    closes = daily.set_index(["ts", "symbol"]).close.to_dict()
    answer = {}
    for month, basket in holdings.groupby("month", sort=True):
        month_exits = original.loc[original.month.eq(month)]
        if month_exits.empty:
            continue
        first = month_exits.exit_ts.min()
        day = first.floor("D") - pd.Timedelta(days=1)
        ranks = sorted((float(closes[(day, symbol)]) /
                        float(closes[(day - pd.Timedelta(days=7), symbol)]) - 1, symbol)
                       for symbol in basket.symbol)
        extra = {symbol for _, symbol in ranks[:5]} if rule == "x5" else set(basket.symbol)
        for row in month_exits.itertuples():
            answer[(month, row.symbol)] = row.exit_ts
        for row in basket.itertuples():
            if row.symbol in extra and first < row.exit_ts:
                answer[(month, row.symbol)] = min(first, answer.get((month, row.symbol), first))
    return answer


def audit_breadth():
    candidate = ROUND / "broader-exit"
    receipt = json.loads((candidate / "summary.json").read_text())
    verify_hashes(receipt["source_sha256"], candidate)
    started = json.loads((candidate / "started.json").read_text())
    if started["contract_sha256"] != CONTRACT_SHA or sha(Path(started["contract_path"])) != CONTRACT_SHA:
        raise ValueError("contract mismatch")
    verify_hashes(json.loads((OLD / "completion.json").read_text())["files_sha256"], ROOT)
    verify_hashes(json.loads((OLD / "single-exit/summary.json").read_text())["source_sha256"], OLD / "single-exit")
    source = json.loads((BASE / "accounts/started.json").read_text())
    for key, relative in source["paths"].items():
        if sha(ROOT / relative) != source["sha256"][key]:
            raise ValueError(f"original input mismatch: {key}")
    funding_path = FAMILY / "artifacts/funding-recheck-20260910/native-replay/native-priority-events.parquet"
    if sha(funding_path) != NATIVE_SHA:
        raise ValueError("funding mismatch")
    holdings = pd.read_parquet(ROOT / source["paths"]["holdings"])
    execution = pd.read_parquet(ROOT / source["paths"]["execution"]).set_index(["ts", "symbol"]).price
    daily = load_verified_returned_daily()
    funding = pd.read_parquet(funding_path)
    terminals, terminal_pins = terminals_from_raw()
    original = pd.read_parquet(OLD / "independent-audit/independent-exit-targets.parquet")
    extra = pd.read_parquet(OLD / "single-exit/execution-prices.parquet").set_index(["ts", "symbol"]).price
    mappings = {}
    for rule in ("x5", "x10"):
        independent = independent_plan(holdings, original, daily, rule)
        actual = pd.read_parquet(candidate / f"{rule}-exit-plan.parquet")
        if actual.duplicated(["month", "symbol"]).any():
            raise ValueError("duplicate plan")
        if independent != actual.set_index(["month", "symbol"]).exit_ts.to_dict():
            raise ValueError(f"independent signal mismatch: {rule}")
        mappings[rule] = independent
    expected = {(s, r, c) for s in ("price_only", "estimated_center")
                for r in ("x5", "x10") for c in (.0004, .0008)}
    actual = [(m["scenario"], m["strategy"], m["slippage_rate"]) for m in receipt["results"]]
    if len(actual) != 8 or set(actual) != expected:
        raise ValueError("missing or unexpected account")
    results = []
    for metrics in receipt["results"]:
        scenario, strategy, slip = metrics["scenario"], metrics["strategy"], metrics["slippage_rate"]
        folder = candidate / f"{scenario}-{strategy}-{round(slip * 10000)}bp"
        nav = pd.read_parquet(folder / "nav.parquet")
        check_complete_nav(nav, extra)
        found = reconstruct(holdings, execution, daily.set_index(["ts", "symbol"]), funding,
                            terminals, mappings[strategy], extra, nav, slip, scenario != "price_only")
        months = pd.read_parquet(folder / "monthly.parquet")
        independent_months = found.pop("monthly")
        if not independent_months.month.equals(months.month):
            raise ValueError("month sequence mismatch")
        found["max_monthly_return_error"] = float(np.max(np.abs(independent_months.account_return - months.account_return)))
        found["differences"] = {key: found[key] - metrics[key]
                                for key in ("final_equity", "funding_pnl_usdt", "fees_usdt", "slippage_usdt")}
        found["differences"]["price_pnl"] = found["price_pnl"] - metrics["price_pnl_usdt"]
        found["differences"]["mdd"] = found["mdd_recomputed"] - metrics["max_drawdown_daily_and_rebalance"]
        errors = [*found["differences"].values(), found["max_nav_absolute_error_usdt"], found["max_monthly_return_error"]]
        if not np.isfinite(errors).all() or max(abs(v) for v in errors) > 1e-4:
            raise ValueError(f"independent cash mismatch: {found}")
        if found["max_monthly_return_error"] > 1e-10 or abs(found["differences"]["mdd"]) > 1e-10:
            raise ValueError("independent return/MDD mismatch")
        years = pd.read_parquet(folder / "yearly.parquet")
        for year in years.itertuples():
            m = months.loc[months.month.dt.year.eq(year.year)]
            if not np.isclose(np.prod(1 + m.account_return) - 1, year.account_return, atol=1e-10, rtol=0):
                raise ValueError("annual compound return mismatch")
            if not np.isclose(m.pnl_usdt.sum(), year.pnl_usdt, atol=1e-4, rtol=0):
                raise ValueError("annual cash mismatch")
        found.update(scenario=scenario, strategy=strategy, slippage_rate=slip, matches=True)
        results.append(found)
        print(json.dumps(found), flush=True)
    summary = {"status": "PASS_INDEPENDENT_8_BREADTH_ACCOUNTS_AND_DAILY_CLOSE_RULES",
               "contract_sha256": CONTRACT_SHA, "script_sha256": sha(Path(__file__)),
               "candidate_summary_sha256": sha(candidate / "summary.json"), "terminal_pins": terminal_pins,
               "signal_counts": {rule: len(plan) for rule, plan in mappings.items()}, "results": results}
    save(ROUND / "independent-audit/breadth-summary.json", summary)


def audit_drawdown():
    folder = ROUND / "drawdown"
    summary = json.loads((folder / "summary.json").read_text())
    verify_hashes(summary["files_sha256"], folder)
    monthly = pd.read_parquet(folder / "monthly-details.parquet")
    yearly = pd.read_parquet(folder / "yearly-details.parquet")
    windows = json.loads((folder / "window-summary.json").read_text())
    market = load_verified_returned_daily().set_index(["ts", "symbol"]).close.to_dict()
    checks, max_error = [], 0.
    for record in summary["accounts"]:
        account = record["account"]
        nav = pd.read_parquet(OLD / "single-exit" / account / "nav.parquet").sort_values("ts", kind="stable")
        values = np.r_[100000., nav.equity.to_numpy(float)]
        dd = values / np.maximum.accumulate(values) - 1
        trough = int(np.argmin(dd))
        peak = int(np.argmax(values[:trough + 1]))
        if abs(float(dd.min()) - record["max_drawdown"]) > 1e-12:
            raise ValueError("drawdown mismatch")
        if nav.iloc[trough - 1].ts != pd.Timestamp(record["trough_ts"]) or nav.iloc[peak - 1].ts != pd.Timestamp(record["peak_ts"]):
            raise ValueError("peak/trough time mismatch")
        months = monthly.loc[monthly.account.eq(account)]
        previous = {"equity": 100000., "price_pnl": 0., "funding_pnl": 0., "fees": 0., "slippage": 0.}
        for row in months.itertuples():
            end = row.month + pd.offsets.MonthBegin(1) + pd.Timedelta(minutes=15)
            observed = nav.loc[nav.ts.eq(end)].iloc[-1]
            error = abs(row.start_equity - previous["equity"])
            error = max(error, abs(row.end_equity - observed.equity),
                        abs(row.pnl - (observed.equity - previous["equity"])))
            for field in ("price_pnl", "funding_pnl", "fees", "slippage"):
                error = max(error, abs(getattr(row, field) - (observed[field] - previous[field])))
            max_error = max(max_error, error)
            previous = observed
        for _, row in yearly.loc[yearly.account.eq(account)].iterrows():
            m = months.loc[months.month.dt.year.eq(row.year)]
            if abs(float(np.prod(1 + m["return"]) - 1) - row["return"]) > 1e-10:
                raise ValueError("year return mismatch")
        checks.append({"account": account, "monthly_rows": len(months), "max_drawdown_exact": True})
    reference_checks = []
    for window in windows:
        ref = window["market_references"]
        a, b = pd.Timestamp(ref["reference_start_utc"]), pd.Timestamp(ref["reference_end_utc"])
        for symbol, field in (("BTC/USDT:USDT", "btc_return"), ("ETH/USDT:USDT", "eth_return")):
            direct = market[(b - pd.Timedelta(days=1), symbol)] / market[(a - pd.Timedelta(days=1), symbol)] - 1
            if ref[field] is None or abs(float(direct) - ref[field]) > 1e-10:
                raise ValueError("market window endpoint return mismatch")
            reference_checks.append({"account": window["account"], "window": window["window"],
                                     "symbol": symbol, "reference_start": a, "reference_end": b,
                                     "direct_endpoint_return": float(direct)})
    if max_error > 1e-4:
        raise ValueError(f"drawdown/monthly cash mismatch: {max_error}")
    save(ROUND / "independent-audit/drawdown-summary.json", {
        "status": "PASS_NAV_DRAWDOWNS_304_MONTH_CASH_28_YEARS_24_MARKET_ENDPOINTS",
        "checks": checks, "max_monthly_cash_error_usdt": max_error,
        "reference_checks": reference_checks, "candidate_summary_sha256": sha(folder / "summary.json"),
        "contract_sha256": CONTRACT_SHA, "script_sha256": sha(Path(__file__))})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("breadth", "drawdown"), required=True)
    args = parser.parse_args()
    if args.phase == "breadth":
        audit_breadth()
    else:
        audit_drawdown()


if __name__ == "__main__":
    main()
