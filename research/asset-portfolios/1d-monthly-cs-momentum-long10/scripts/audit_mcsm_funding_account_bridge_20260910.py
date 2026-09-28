"""Independent interval-endpoint accounting; no account-kernel arithmetic.

Each holding month's price P&L is quantity * (exit - entry). Funding is a
separate signed cash sum. Thus interim funding marks cannot create price P&L.
Original frozen files are verified; no market network requests or new selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from verify_mcsm_baseline_20260908 import load_verified_returned_daily

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
BASE = FAMILY / "artifacts/baseline-estimate-20260909"
INITIAL, FEE, SLIP = 100_000.0, .001, .0004
SCENARIOS = ("price_only", "estimated_center", "estimated_adverse", "estimated_favorable")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def solve_post_cost(pre, old_values, weights):
    """Monotone bisection, independent of both previous analytical solvers."""
    if not math.isfinite(pre) or pre <= 0:
        raise ValueError("nonpositive opening capital")
    names = sorted(set(old_values) | set(weights))
    if any(v < 0 or not math.isfinite(v) for v in (*old_values.values(), *weights.values())):
        raise ValueError("long-only finite values required")
    if sum(weights.values()) > 1 + 1e-12:
        raise ValueError("weights exceed one")
    low, high = 0.0, pre
    for _ in range(90):
        mid = (low + high) / 2
        cost = (FEE + SLIP) * math.fsum(abs(weights.get(s, 0) * mid - old_values.get(s, 0)) for s in names)
        if mid + cost > pre:
            high = mid
        else:
            low = mid
    result = (low + high) / 2
    if result <= 0:
        raise ValueError("cost exhausted capital")
    return result


def event_mark(frame, scenario):
    rate = frame.funding_rate.to_numpy(float)
    low, center, high = (frame[k].to_numpy(float) for k in ("mark_low", "mark_center", "mark_high"))
    if not np.isfinite(np.c_[rate, low, center, high]).all() or not ((low > 0) & (low <= center) & (center <= high)).all():
        raise ValueError("invalid funding rate/mark")
    if scenario in ("price_only", "estimated_center"):
        return center
    if scenario == "estimated_adverse":
        return np.where(rate >= 0, high, low)
    if scenario == "estimated_favorable":
        return np.where(rate >= 0, low, high)
    raise ValueError("unknown scenario")


def funding_cash(quantity, mark, rate):
    return -np.asarray(quantity) * np.asarray(mark) * np.asarray(rate)


def prepare_windows(holdings, funding):
    if holdings.duplicated(["month", "symbol"]).any() or funding.duplicated(["ts", "symbol", "rate_type"]).any():
        raise ValueError("duplicate holding or funding identity")
    if not holdings.groupby("month").size().eq(10).all() or not holdings.weight.eq(.1).all():
        raise ValueError("changed Top10 equal-weight contract")
    assigned = np.zeros(len(funding), dtype=int)
    windows = {}
    for row in holdings.itertuples():
        positions = np.flatnonzero((funding.symbol.eq(row.symbol) & funding.ts.gt(row.entry_ts) & funding.ts.le(row.exit_ts)).to_numpy())
        assigned[positions] += 1
        windows[(row.month, row.symbol)] = positions
    if not (assigned == 1).all():
        raise ValueError("funding outside actual (entry,exit] or overlapping holding windows")
    return windows


def terminals_from_raw():
    directory = FAMILY / "artifacts/baseline-verification-20260908/terminal-evidence"
    path = directory / "final-review.json"
    if sha(path) != "f735e3f11941ff01d7a65cc2db1a1e6dde2265d098ace0599ee47e694f354af6":
        raise ValueError("terminal review hash mismatch")
    values, checked = {}, {str(path.relative_to(ROOT)): sha(path)}
    for row in json.loads(path.read_text())["events"]:
        source = directory / f"{row['symbol']}-index-1m.json"
        meta_path = source.with_name(source.name + ".meta.json")
        meta = json.loads(meta_path.read_text())
        if sha(source) != meta.get("sha256", meta.get("content_sha256")) or not row["index_1m_complete_window"]:
            raise ValueError("terminal source not frozen or incomplete")
        raw = np.array([[float(v) for v in record[1:5]] for record in json.loads(source.read_text())])
        values[(row["symbol"][:-4] + "/USDT:USDT", pd.Timestamp(row["terminal_utc"]))] = {
            "price_only": float(raw.mean()), "estimated_center": float(raw.mean()),
            "estimated_adverse": float(raw[:, 2].mean()), "estimated_favorable": float(raw[:, 1].mean()),
        }
        checked[str(source.relative_to(ROOT))] = sha(source)
    return values, checked


def reconstruct(holdings, execution, daily, funding, windows, terminals, scenario):
    """Aggregate each fixed-quantity interval directly; record no interim marks."""
    execution = execution.set_index(["ts", "symbol"])
    rate = funding.funding_rate.to_numpy(float)
    marks = event_mark(funding, scenario)
    quantities = np.zeros(len(funding))
    months = list(holdings.groupby("month", sort=True))
    pre, old_q, price_total, fund_total, fees, slip = INITIAL, {}, 0., 0., 0., 0.
    nav, month_rows, trades, leg_rows = [], [], [], []
    previous_month, previous_start, previous_details = None, INITIAL, None
    for index in range(len(months) + 1):
        final = index == len(months)
        month = months[-1][0] + pd.offsets.MonthBegin(1) if final else months[index][0]
        ts = month + pd.Timedelta(minutes=15)
        group = holdings.iloc[:0] if final else months[index][1]
        weights = dict(zip(group.symbol, group.weight))
        prices = {s: float(execution.loc[(ts, s), "price"]) for s in set(weights) | set(old_q)}
        old_values = {s: q * prices[s] for s, q in old_q.items()}
        post = solve_post_cost(pre, old_values, weights)
        q = {s: w * post / prices[s] for s, w in weights.items()}
        for symbol in sorted(set(q) | set(old_q)):
            delta = q.get(symbol, 0.) - old_q.get(symbol, 0.)
            notional = abs(delta) * prices[symbol]
            fee, slippage = FEE * notional, SLIP * notional
            fees += fee
            slip += slippage
            trades.append({"ts": ts, "symbol": symbol, "old_quantity": old_q.get(symbol, 0.),
                           "new_quantity": q.get(symbol, 0.), "delta_quantity": delta,
                           "reference_price": prices[symbol], "traded_notional": notional,
                           "fee": fee, "slippage": slippage})
        if previous_month is not None:
            month_rows.append({"month": previous_month, "account_start_equity": previous_start,
                               "account_end_equity": post, "account_return": post / previous_start - 1,
                               **previous_details})
        previous_month, previous_start = month, INITIAL if index == 0 else post
        nav.append({"ts": ts, "equity": post, "price_pnl": price_total, "funding_pnl": fund_total,
                    "fees": fees, "slippage": slip, "gross_notional": math.fsum(q[s] * prices[s] for s in q)})
        if final:
            break
        month_price = month_fund = terminal_fee = 0.
        fund_parts, legs = [], []
        for row in group.itertuples():
            if not math.isclose(prices[row.symbol], row.entry_price, rel_tol=1e-13):
                raise ValueError("holding entry differs from actual execution reference")
            pos = windows[(month, row.symbol)]
            quantities[pos] = q[row.symbol]
            cash = funding_cash(q[row.symbol], marks[pos], rate[pos])
            if scenario == "price_only":
                cash = np.zeros_like(cash)
            exit_price = terminals[(row.symbol, row.exit_ts)][scenario] if row.terminal else float(execution.loc[(row.exit_ts, row.symbol), "price"])
            pnl = q[row.symbol] * (exit_price - prices[row.symbol])
            terminal_cost = FEE * q[row.symbol] * exit_price if row.terminal else 0.
            month_price += pnl
            month_fund += math.fsum(cash)
            terminal_fee += terminal_cost
            event_times = funding.iloc[pos].ts
            fund_parts.append(pd.DataFrame({"ts": event_times.to_numpy(), "cash": cash}))
            legs.append((row, exit_price, terminal_cost))
            leg_rows.append({"month": month, "symbol": row.symbol, "quantity": q[row.symbol],
                             "entry_price": prices[row.symbol], "exit_price": exit_price,
                             "price_pnl": pnl, "funding_cash": math.fsum(cash),
                             "funding_yield_on_leg_entry_notional": math.fsum(cash) / (q[row.symbol] * prices[row.symbol]),
                             "funding_yield_on_month_open_capital": math.fsum(cash) / post,
                             "terminal_fee": terminal_cost, "event_count": len(pos)})
        cash_events = pd.concat(fund_parts).sort_values("ts")
        next_month = month + pd.offsets.MonthBegin(1)
        for daily_ts in pd.date_range(month + pd.Timedelta(days=1), next_month, freq="D"):
            daily_price, daily_terminal_fee, gross = 0., 0., 0.
            for row, exit_price, terminal_cost in legs:
                if row.terminal and row.exit_ts < daily_ts:
                    observed = exit_price
                    daily_terminal_fee += terminal_cost
                else:
                    source = daily.loc[(daily_ts - pd.Timedelta(days=1), row.symbol)]
                    if not isinstance(source.eligible, (bool, np.bool_)) or not source.eligible:
                        raise ValueError("ineligible daily mark")
                    observed = float(source.close)
                    gross += q[row.symbol] * observed
                daily_price += q[row.symbol] * (observed - prices[row.symbol])
            # The original synchronous close is before funding at the same instant.
            daily_fund = math.fsum(cash_events.loc[cash_events.ts.lt(daily_ts), "cash"])
            equity = post + daily_price + daily_fund - daily_terminal_fee
            nav.append({"ts": daily_ts, "equity": equity, "price_pnl": price_total + daily_price,
                        "funding_pnl": fund_total + daily_fund, "fees": fees + daily_terminal_fee,
                        "slippage": slip, "gross_notional": gross})
        price_total += month_price
        fund_total += month_fund
        fees += terminal_fee
        pre = post + month_price + month_fund - terminal_fee
        old_q = {row.symbol: q[row.symbol] for row in group.itertuples() if not row.terminal}
        previous_details = {"opening_post_cost_capital": post, "closing_pre_rebalance_capital": pre,
                            "interval_price_pnl": month_price, "interval_funding_cash": month_fund,
                            "interval_terminal_fee": terminal_fee,
                            "funding_yield_on_opening_post_cost_capital": month_fund / post,
                            "price_factor_before_next_rebalance": 1 + month_price / post - terminal_fee / post,
                            "full_factor_before_next_rebalance": pre / post}
    return {"nav": pd.DataFrame(nav), "monthly": pd.DataFrame(month_rows), "trades": pd.DataFrame(trades),
            "legs": pd.DataFrame(leg_rows), "quantities": quantities,
            "cash": funding_cash(quantities, marks, rate) if scenario != "price_only" else np.zeros(len(rate)),
            "marks": marks, "final_equity": post}


def compare(actual, expected, keys, fields):
    left = actual.sort_values(keys).reset_index(drop=True)
    right = expected.sort_values(keys).reset_index(drop=True)
    if not left[keys].equals(right[keys]):
        raise ValueError(f"identity/row-count mismatch {keys}")
    errors = {}
    for field in fields:
        difference = left[field].to_numpy(float) - right[field].to_numpy(float)
        errors[field] = float(np.abs(difference).max())
        if not np.allclose(left[field], right[field], rtol=1e-10, atol=1e-6):
            raise ValueError((field, errors[field]))
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=FAMILY / "artifacts/funding-recheck-20260910/accounting")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    run = BASE / "accounts"
    started = json.loads((run / "started.json").read_text())
    summary = json.loads((run / "summary.json").read_text())
    checked = {}
    for role, path in started["paths"].items():
        digest = sha(path)
        if digest != started["sha256"][role]:
            raise ValueError(f"frozen input changed: {role}")
        checked[str(path)] = digest
    for path, digest in summary["output_sha256"].items():
        if sha(run / path) != digest:
            raise ValueError(f"frozen account output changed: {path}")
        checked[str((run / path).relative_to(ROOT))] = digest
    holdings, execution, funding = (pd.read_parquet(started["paths"][k]) for k in ("holdings", "execution", "funding"))
    windows = prepare_windows(holdings, funding)
    terminals, terminal_hashes = terminals_from_raw()
    checked.update(terminal_hashes)
    daily = load_verified_returned_daily().set_index(["ts", "symbol"]).sort_index()
    reports, results = {}, {}
    for scenario in SCENARIOS:
        result = reconstruct(holdings, execution, daily, funding, windows, terminals, scenario)
        results[scenario] = result
        errors = {}
        for table, keys, fields in (
            ("nav", ["ts"], ["equity", "price_pnl", "funding_pnl", "fees", "slippage", "gross_notional"]),
            ("monthly", ["month"], ["account_start_equity", "account_end_equity", "account_return"]),
            ("trades", ["ts", "symbol"], ["old_quantity", "new_quantity", "delta_quantity", "reference_price", "traded_notional", "fee", "slippage"]),
        ):
            errors[table] = compare(result[table], pd.read_parquet(run / scenario / f"{table}.parquet"), keys, fields)
        if scenario != "price_only":
            event_check = funding[["ts", "symbol", "rate_type"]].copy()
            event_check["quantity"], event_check["estimate_mark"], event_check["rate"], event_check["funding_cash"] = result["quantities"], result["marks"], funding.funding_rate, result["cash"]
            errors["funding"] = compare(event_check, pd.read_parquet(run / scenario / "funding.parquet"), ["ts", "symbol", "rate_type"], ["quantity", "estimate_mark", "rate", "funding_cash"])
        compounded = INITIAL * float(np.prod(1 + result["monthly"].account_return))
        if not math.isclose(compounded, result["final_equity"], rel_tol=1e-10, abs_tol=1e-6):
            raise ValueError("monthly independent compounding failed")
        cash = result["cash"]
        nav = result["nav"]
        values = np.r_[INITIAL, nav.equity]
        reports[scenario] = {"final_equity": result["final_equity"], "total_return": result["final_equity"] / INITIAL - 1,
                             "mdd_daily_rebalance": float((values / np.maximum.accumulate(values) - 1).min()),
                             "monthly_compounded_final": compounded, "comparison_max_absolute_errors": errors,
                             "funding_received": math.fsum(cash[cash > 0]), "funding_paid": -math.fsum(cash[cash < 0]),
                             "funding_net": math.fsum(cash), "price_pnl": float(nav.price_pnl.iloc[-1]),
                             "fees": float(nav.fees.iloc[-1]), "slippage": float(nav.slippage.iloc[-1])}
        print(scenario, reports[scenario]["final_equity"], "independent interval account MATCH", flush=True)
    direct = funding_cash(results["price_only"]["quantities"], funding.mark_center.to_numpy(float), funding.funding_rate.to_numpy(float))
    cash_frame = funding[["ts", "symbol"]].copy()
    cash_frame["center_cash"] = results["estimated_center"]["cash"]
    cash_frame["same_price_only_quantities_cash_not_reinvested"] = direct
    cash_frame["year"] = cash_frame.ts.dt.year
    monthly_bridge = results["estimated_center"]["monthly"].merge(results["price_only"]["monthly"], on="month", suffixes=("_funded", "_price_only"))
    monthly_bridge["funded_to_price_return_factor"] = (1 + monthly_bridge.account_return_funded) / (1 + monthly_bridge.account_return_price_only)
    leg_bridge = results["estimated_center"]["legs"].merge(results["price_only"]["legs"][["month", "symbol", "quantity"]], on=["month", "symbol"], suffixes=("_funded", "_price_only"))
    direct_windows = []
    for row in holdings.itertuples():
        positions = windows[(row.month, row.symbol)]
        direct_windows.append({"month": row.month, "symbol": row.symbol, "direct_cash_price_only_q": math.fsum(direct[positions])})
    leg_bridge = leg_bridge.merge(pd.DataFrame(direct_windows), on=["month", "symbol"])
    yearly = []
    previous = {s: INITIAL for s in ("price_only", "estimated_center")}
    for year in range(2020, 2027):
        record = {"year": year}
        cutoff = min(pd.Timestamp(f"{year + 1}-01-01", tz="UTC"), pd.Timestamp(summary["end"]))
        for scenario in previous:
            value = float(results[scenario]["nav"].loc[results[scenario]["nav"].ts.le(cutoff), "equity"].iloc[-1])
            record[f"{scenario}_start"] = previous[scenario]
            record[f"{scenario}_end"] = value
            record[f"{scenario}_return"] = value / previous[scenario] - 1
            previous[scenario] = value
        yearly.append(record)
    yearly = pd.DataFrame(yearly).merge(cash_frame.groupby("year")[["center_cash", "same_price_only_quantities_cash_not_reinvested"]].sum().reset_index(), on="year")
    center, price = reports["estimated_center"], reports["price_only"]
    ranked = leg_bridge.sort_values("funding_cash", ascending=False)
    concentration = {f"top_{count}_holding_windows_cash": float(ranked.head(count).funding_cash.sum()) for count in (1, 5, 10, 20)}
    summary_out = {
        "status": "INDEPENDENT_INTERVAL_ACCOUNT_RECONSTRUCTED_ESTIMATE_NOT_VERIFIED_NET",
        "method": "Direct fixed-quantity entry-to-exit P&L, separate signed funding sum, independent bisection net-trade cost; no intermediate price marks and no prior account arithmetic.",
        "holdings": len(holdings), "months": len(monthly_bridge), "funding_events": len(funding),
        "negative_rate_events": int(funding.funding_rate.lt(0).sum()), "positive_rate_events": int(funding.funding_rate.gt(0).sum()),
        "zero_rate_events": int(funding.funding_rate.eq(0).sum()), "duplicate_native_keys": 0,
        "all_events_assigned_once_to_actual_open_interval": True,
        "scenarios": reports,
        "same_price_only_quantities_direct_funding": {"received": math.fsum(direct[direct > 0]), "paid": -math.fsum(direct[direct < 0]), "net": math.fsum(direct),
            "price_account_final_plus_non_reinvested_cash": price["final_equity"] + math.fsum(direct),
            "description": "Accounting decomposition only: funding does not change price-only position quantities or future target capital; not a self-financing new strategy."},
        "final_equity_difference_bridge": {"funded_minus_price_final": center["final_equity"] - price["final_equity"],
            "funding_cash_in_funded_path": center["funding_net"], "price_pnl_difference_due_to_changed_future_quantities": center["price_pnl"] - price["price_pnl"],
            "fee_and_slippage_saving": price["fees"] + price["slippage"] - center["fees"] - center["slippage"]},
        "compounded_monthly_relative_factors": float(np.prod(monthly_bridge.funded_to_price_return_factor)),
        "final_equity_ratio": center["final_equity"] / price["final_equity"],
        "concentration": concentration,
        "calendar_cash_year_note": "Cash years are actual UTC event years; Jan 1 00:00 funding occurs after daily close and is in the new year, unlike holding-month labels.",
        "limitations": ["No independent event source or complete historical calendar proof within this arithmetic-only audit.", "Original minute-mark and terminal estimates remain estimates.", "No margin liquidation, historical contract qualification, capacity or actual fill certification."],
        "checked_sha256": checked, "script_sha256": sha(__file__),
    }
    args.output.mkdir(parents=True)
    for name, frame in (("monthly-bridge", monthly_bridge), ("yearly-bridge", yearly), ("holding-window-bridge", leg_bridge), ("top-20-funding-windows", ranked.head(20))):
        frame.to_csv(args.output / f"{name}.csv", index=False)
    (args.output / "summary.json").write_text(json.dumps(summary_out, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
