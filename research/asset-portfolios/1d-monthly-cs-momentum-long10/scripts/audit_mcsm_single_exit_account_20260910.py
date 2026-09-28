"""Independent endpoint cash reconstruction, without candidate account arithmetic."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from audit_mcsm_funding_account_bridge_20260910 import terminals_from_raw
from verify_mcsm_baseline_20260908 import load_verified_returned_daily

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
ROUND = FAMILY / "artifacts/mechanism-round-20260910"
BASE = FAMILY / "artifacts/baseline-estimate-20260909"
NATIVE_SHA = "fc57b942e14ab29007256326404c698f379d24988a0da274fe4434b0d9c70990"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def post_cost(pre, old, weights, cost):
    names = set(old) | set(weights)
    low, high = 0., pre
    for _ in range(100):
        mid = (low + high) / 2
        turnover = math.fsum(abs(weights.get(s, 0.) * mid - old.get(s, 0.)) for s in names)
        if mid + cost * turnover > pre:
            high = mid
        else:
            low = mid
    return (low + high) / 2


def check_complete_results(results):
    expected = {(s, p, c) for s in ("price_only", "estimated_center")
                for p in ("baseline", "single_exit") for c in (.0004, .0008)}
    actual = [(r["scenario"], r["strategy"], r["slippage_rate"]) for r in results]
    if len(actual) != 8 or set(actual) != expected:
        raise ValueError("not exactly eight unique prescribed accounts")


def check_complete_nav(nav, extra):
    begin = pd.Timestamp("2020-03-01T00:15Z")
    end = pd.Timestamp("2026-07-01T00:15Z")
    expected = set(pd.date_range(begin, end, freq="MS"))
    expected |= set(pd.date_range(begin.floor("D") + pd.Timedelta(days=1), end.floor("D"), freq="D"))
    expected |= set(extra.index.get_level_values(0))
    if set(nav.ts) != expected or not nav.ts.is_monotonic_increasing:
        raise ValueError("missing, extra or disordered valuation clock")
    if not np.isfinite(nav.equity.to_numpy(float)).all() or not nav.equity.gt(0).all():
        raise ValueError("invalid NAV equity")


def reconstruct(h, execution, daily, funding, terminals, exits, extra, nav, slip, funded):
    """Sum fixed quantities times endpoints and signed funding; inspect all NAV clocks."""
    # Scalar pandas MultiIndex lookup repeatedly rebuilds hash tables for the
    # retained Arrow-backed indexes. Cache exact tuple keys, not new prices.
    execution = execution.to_dict()
    daily_close = daily["close"].to_dict()
    extra = extra.to_dict()
    pre, old_q, fund_total, fee_total, slip_total, price_total = 100000., {}, 0., 0., 0., 0.
    peak_error, tested = 0., 0
    independent_equities = [100000.]
    snapshots = nav.sort_values("ts", kind="stable").groupby("ts", sort=True).tail(1).set_index("ts")
    fgroups = {s: g.sort_values("ts") for s, g in funding.groupby("symbol")}
    months = list(h.groupby("month", sort=True))
    expected_months, last_start, previous = [], 100000., None
    for number in range(len(months) + 1):
        final = number == len(months)
        month = months[-1][0] + pd.offsets.MonthBegin(1) if final else months[number][0]
        ts = month + pd.Timedelta(minutes=15)
        group = h.iloc[:0] if final else months[number][1]
        w = dict(zip(group.symbol, group.weight))
        entry = {s: float(execution[(ts, s)]) for s in set(w) | set(old_q)}
        old = {s: old_q[s] * entry[s] for s in old_q}
        post = post_cost(pre, old, w, .001 + slip)
        q = {s: w[s] * post / entry[s] for s in w}
        turnover = math.fsum(abs(q.get(s, 0.) - old_q.get(s, 0.)) * entry[s] for s in set(q) | set(old_q))
        fee_total += .001 * turnover
        slip_total += slip * turnover
        peak_error = max(peak_error, abs(post - float(snapshots.loc[ts, "equity"])))
        independent_equities.append(post)
        tested += 1
        if previous is not None:
            expected_months.append({"month": previous, "account_return": post / last_start - 1})
        last_start, previous = (100000. if number == 0 else post), month
        if final:
            break
        leg = []
        for r in group.itertuples():
            early = exits.get((month, r.symbol))
            end = early if early is not None else r.exit_ts
            terminal = early is None and bool(r.terminal)
            endprice = (float(extra[(end, r.symbol)]) if early is not None else
                        terminals[(r.symbol, end)]["estimated_center"] if terminal else
                        float(execution[(end, r.symbol)]))
            fee = .001 * q[r.symbol] * endprice if early is not None or terminal else 0.
            slippage = slip * q[r.symbol] * endprice if early is not None else 0.
            ev = fgroups.get(r.symbol, funding.iloc[:0])
            ev = ev.loc[ev.ts.gt(r.entry_ts) & ev.ts.le(end)]
            cash = -q[r.symbol] * ev.mark_center.to_numpy(float) * ev.funding_rate.to_numpy(float)
            if not funded:
                cash = np.zeros(len(ev))
            leg.append((r, end, endprice, early is not None or terminal, fee, slippage, ev.ts, cash))
        nxt = month + pd.offsets.MonthBegin(1) + pd.Timedelta(minutes=15)
        for clock, row in snapshots.loc[(snapshots.index > ts) & (snapshots.index < nxt)].iterrows():
            is_daily = row.sample_kind == "daily"
            value = post
            for r, end, endprice, closes, fee, slippage, event_times, cash in leg:
                closed = closes and (end < clock if is_daily else end <= clock)
                if closed:
                    price = endprice
                elif is_daily:
                    price = float(daily_close[(clock - pd.Timedelta(days=1), r.symbol)])
                else:
                    price = float(extra[(clock, r.symbol)])
                value += q[r.symbol] * (price - entry[r.symbol])
                take = event_times.lt(clock) if is_daily else event_times.le(clock)
                value += math.fsum(cash[take.to_numpy()])
                if closed:
                    value -= fee + slippage
            if not math.isfinite(value):
                raise ValueError("nonfinite independently reconstructed NAV")
            same_time = nav.loc[nav.ts.eq(clock)]
            just_closed = sorted((r.symbol, fee + slippage) for r, end, _, closes, fee, slippage, *_ in leg
                                 if closes and end == clock and (month, r.symbol) in exits)
            values = [value + math.fsum(cost for _, cost in just_closed)]
            for _, cost in just_closed:
                values.append(values[-1] - cost)
            if len(values) != len(same_time):
                raise ValueError("missing or extra synchronous pre/post-exit NAV event")
            actual_values = same_time.equity.to_numpy(float)
            if not np.isfinite(actual_values).all():
                raise ValueError("nonfinite reported NAV")
            peak_error = max(peak_error, float(np.max(np.abs(np.array(values) - actual_values))))
            independent_equities.extend(values)
            tested += 1
        month_pnl = math.fsum(q[r.symbol] * (p - entry[r.symbol]) for r, _, p, *_ in leg)
        month_fund = math.fsum(math.fsum(item[-1]) for item in leg)
        month_fee = math.fsum(item[4] for item in leg)
        month_slip = math.fsum(item[5] for item in leg)
        price_total += month_pnl
        fund_total += month_fund
        fee_total += month_fee
        slip_total += month_slip
        pre = post + month_pnl + month_fund - month_fee - month_slip
        old_q = {r.symbol: q[r.symbol] for r, _, _, closes, *_ in leg if not closes}
    eq = np.array(independent_equities)
    return {"final_equity": post, "funding_pnl_usdt": fund_total, "fees_usdt": fee_total,
            "slippage_usdt": slip_total, "price_pnl": price_total,
            "max_nav_absolute_error_usdt": peak_error, "nav_clocks_tested": tested,
            "nav_rows_tested": len(eq) - 1, "mdd_recomputed": float((eq / np.maximum.accumulate(eq) - 1).min()),
            "monthly": pd.DataFrame(expected_months)}


def main():
    output = ROUND / "independent-audit" / "account-summary.json"
    if output.exists():
        raise FileExistsError(output)
    source = json.loads((BASE / "accounts/started.json").read_text())
    for key, path in source["paths"].items():
        if sha(ROOT / path) != source["sha256"][key]:
            raise ValueError(f"original input changed: {key}")
    candidate = ROUND / "single-exit"
    receipt = json.loads((candidate / "summary.json").read_text())
    check_complete_results(receipt["results"])
    for path, digest in receipt["source_sha256"].items():
        if sha(candidate / path) != digest:
            raise ValueError(f"candidate output hash changed: {path}")
    funding_path = FAMILY / "artifacts/funding-recheck-20260910/native-replay/native-priority-events.parquet"
    if sha(funding_path) != NATIVE_SHA:
        raise ValueError("native funding changed")
    h = pd.read_parquet(ROOT / source["paths"]["holdings"])
    execution = pd.read_parquet(ROOT / source["paths"]["execution"]).set_index(["ts", "symbol"]).price
    funding = pd.read_parquet(funding_path)
    if not np.isfinite(funding[["funding_rate", "mark_center"]].to_numpy(float)).all() or not funding.mark_center.gt(0).all():
        raise ValueError("invalid funding event")
    daily = load_verified_returned_daily().set_index(["ts", "symbol"])
    terminals, terminal_pins = terminals_from_raw()
    exits = pd.read_parquet(candidate / "exit-plan.parquet")
    independent = pd.read_parquet(ROUND / "independent-audit/independent-exit-targets.parquet")
    cols = ["month", "symbol", "exit_ts"]
    if set(map(tuple, exits[cols].values)) != set(map(tuple, independent[cols].values)):
        raise ValueError("independent signal mismatch")
    extra = pd.read_parquet(candidate / "execution-prices.parquet").set_index(["ts", "symbol"]).price
    results = []
    for metrics in receipt["results"]:
        scenario, strategy, slip = metrics["scenario"], metrics["strategy"], metrics["slippage_rate"]
        folder = candidate / f"{scenario}-{strategy}-{int(slip * 10000)}bp"
        nav = pd.read_parquet(folder / "nav.parquet")
        check_complete_nav(nav, extra)
        exit_map = exits.set_index(["month", "symbol"]).exit_ts.to_dict() if strategy == "single_exit" else {}
        found = reconstruct(h, execution, daily, funding, terminals, exit_map, extra, nav, slip, scenario != "price_only")
        monthly = pd.read_parquet(folder / "monthly.parquet")
        found_month = found.pop("monthly")
        if not found_month.month.equals(monthly.month):
            raise ValueError("monthly calendar differs")
        if not np.isfinite(np.c_[found_month.account_return.to_numpy(float), monthly.account_return.to_numpy(float)]).all():
            raise ValueError("nonfinite monthly return")
        found["max_monthly_return_error"] = float(np.max(np.abs(found_month.account_return - monthly.account_return)))
        found["differences"] = {k: found[k] - metrics[k] for k in ("final_equity", "funding_pnl_usdt", "fees_usdt", "slippage_usdt")}
        found["differences"]["price_pnl_usdt"] = found["price_pnl"] - metrics["price_pnl_usdt"]
        found["differences"]["mdd"] = found["mdd_recomputed"] - metrics["max_drawdown_daily_and_rebalance"]
        if not np.isfinite(list(found["differences"].values()) + [found["max_nav_absolute_error_usdt"], found["max_monthly_return_error"]]).all():
            raise ValueError("nonfinite audit difference")
        if (any(abs(v) > 1e-4 for v in found["differences"].values()) or found["max_nav_absolute_error_usdt"] > 1e-4
                or found["max_monthly_return_error"] > 1e-10 or abs(found["differences"]["mdd"]) > 1e-10):
            raise ValueError(f"account arithmetic mismatch: {found}")
        found.update(scenario=scenario, strategy=strategy, slippage_rate=slip, matches=True)
        results.append(found)
        print(json.dumps(found), flush=True)
    result = {"status": "PASS_INDEPENDENT_8_ACCOUNT_CASH_AND_ALL_DISTINCT_NAV_CLOCKS", "exit_targets_exact": len(exits),
              "results": results, "script_sha256": sha(Path(__file__)), "terminal_pins": terminal_pins,
              "candidate_summary_sha256": sha(candidate / "summary.json"), "funding_sha256": NATIVE_SHA}
    with output.open("x") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")


if __name__ == "__main__":
    main()
