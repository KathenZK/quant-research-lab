"""Independent cash-and-unit reconstruction of three estimated funding accounts.

This imports only the independent analytic cost solver and frozen returned-frame
reader. It never calls the primary runner or accounting kernel. All results stay
conditional estimates; observed-event reconciliation is not a calendar audit.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from audit_mcsm_price_only_replica_20260909 import (
    ARTIFACTS, FAMILY, FEE, INITIAL, SLIP, sha, solve_piecewise,
)
from verify_mcsm_baseline_20260908 import load_verified_returned_daily

SCENARIOS = ("estimated_center", "estimated_adverse", "estimated_favorable")


def mark_for_event(event, scenario):
    """Independent signed-payment choice, not the main runner's helper."""
    rate = float(event["funding_rate"])
    center, low, high = (float(event[key]) for key in ("mark_center", "mark_low", "mark_high"))
    if not all(math.isfinite(x) for x in (rate, center, low, high)) or not 0 < low <= center <= high:
        raise ValueError("invalid or missing funding estimate")
    if scenario == "estimated_center":
        return center
    endpoints = (low, high) if rate < 0 else (high, low)
    if scenario not in SCENARIOS:
        raise ValueError("unknown estimate scenario")
    return endpoints[0 if scenario == "estimated_adverse" else 1]


def reconstruct(holdings, execution, daily_prices, funding, terminals, scenario, start, end):
    """Reconstruct one path using units plus cash reserve, including funding cash.

    Reserve may be negative after funding payments: this is a mathematical perp
    replica, not a spot-cash feasibility or margin simulation. Each scenario has
    its own evolving capital and hence its own subsequent rebalance quantities.
    """
    if scenario not in SCENARIOS:
        raise ValueError("unknown estimate scenario")
    prices = {ts: group.set_index("symbol").price.to_dict() for ts, group in execution.groupby("ts")}
    targets = {ts: group.set_index("symbol").weight.to_dict() for ts, group in holdings.groupby("entry_ts")}
    targets[end] = {}
    if funding.duplicated(["ts", "symbol", "rate_type"]).any():
        raise ValueError("duplicate funding event identity")
    if not funding.ts.gt(start).all() or not funding.ts.le(end).all():
        raise ValueError("funding outside the declared account interval")
    events = [(ts, 3, "trade", weights) for ts, weights in targets.items()]
    events += [(ts, 0, "close", None) for ts in pd.date_range(start.floor("D") + pd.Timedelta(days=1), end.floor("D"), freq="D")]
    events += [(item["ts"], 2, "terminal", item) for item in terminals if start < item["ts"] <= end]
    events += [(item["ts"], 1, "funding", item) for item in funding.to_dict("records")]
    events.sort(key=lambda event: (event[0], event[1], str((event[3] or {}).get("symbol", ""))))
    q, last_price = {}, {}
    reserve = INITIAL
    price_pnl = funding_pnl = fees = slippage = 0.0
    nav_rows, monthly_rows, trade_rows, funding_rows, terminal_rows = [], [], [], [], []
    previous_month, previous_month_start = None, INITIAL

    def mark(observed):
        nonlocal price_pnl
        for symbol, price in observed.items():
            if symbol not in q:
                raise ValueError("mark for an unheld contract")
            value = float(price)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"missing/invalid held mark {symbol}")
            price_pnl += q[symbol] * (value - last_price[symbol])
            last_price[symbol] = value

    for ts, _, kind, payload in events:
        if kind == "funding":
            symbol, rate_type = payload["symbol"], payload["rate_type"]
            if symbol not in q or rate_type not in ("Regular", "Special"):
                raise ValueError("unheld funding contract or unknown rate type")
            price = mark_for_event(payload, scenario)
            mark({symbol: price})
            cash = -q[symbol] * price * float(payload["funding_rate"])
            reserve += cash
            funding_pnl += cash
            funding_rows.append({
                "ts": ts, "symbol": symbol, "rate_type": rate_type,
                "source_type": payload.get("source_type"),
                "quantity": q[symbol], "rate": float(payload["funding_rate"]),
                "estimate_mark": price, "funding_cash": cash,
                "source_quality": payload.get("mark_source", payload.get("mark_quality", "UNSPECIFIED_ESTIMATE")),
            })
        elif kind == "terminal":
            symbol = payload["symbol"]
            if symbol not in q:
                continue
            field = {"estimated_center": "center", "estimated_adverse": "low", "estimated_favorable": "high"}[scenario]
            price = float(payload[field])
            mark({symbol: price})
            quantity = q.pop(symbol)
            last_price.pop(symbol)
            fee = quantity * price * FEE
            fees += fee
            reserve += quantity * price - fee
            terminal_rows.append({"ts": ts, "symbol": symbol, "quantity": quantity,
                                  "settlement_price": price, "fee": fee, "slippage": 0.0})
        elif kind == "close":
            observed = {}
            for symbol in q:
                record = daily_prices.loc[(ts - pd.Timedelta(days=1), symbol)]
                if not isinstance(record.eligible, (bool, np.bool_)) or not record.eligible:
                    raise ValueError("missing or ineligible daily mark")
                observed[symbol] = float(record.close)
            mark(observed)
        else:
            observed = {s: prices[ts][s] for s in set(q) | set(payload)}
            mark({s: observed[s] for s in q})
            old_value = {s: quantity * observed[s] for s, quantity in q.items()}
            pre = reserve + math.fsum(old_value.values())
            if pre <= 0 or not math.isfinite(pre):
                raise ValueError("nonpositive pre-rebalance equity")
            post = solve_piecewise(pre, old_value, payload)
            new_q = {s: weight * post / observed[s] for s, weight in payload.items()}
            for symbol in sorted(set(q) | set(new_q)):
                delta = new_q.get(symbol, 0) - q.get(symbol, 0)
                notional = abs(delta) * observed[symbol]
                fee, slip = notional * FEE, notional * SLIP
                reserve -= delta * observed[symbol] + fee + slip
                fees += fee
                slippage += slip
                trade_rows.append({"ts": ts, "symbol": symbol, "new_quantity": new_q.get(symbol, 0),
                                   "delta_quantity": delta, "traded_notional": notional, "fee": fee, "slippage": slip})
            q = new_q
            last_price = {s: observed[s] for s in q}
            equity = reserve + math.fsum(q[s] * last_price[s] for s in q)
            if previous_month is not None:
                monthly_rows.append({"month": previous_month, "account_start_equity": previous_month_start,
                                     "account_end_equity": equity, "account_return": equity / previous_month_start - 1})
            previous_month, previous_month_start = ts.floor("D"), equity if ts != start else INITIAL
        gross = math.fsum(q[s] * last_price[s] for s in q)
        equity = reserve + gross
        if not math.isfinite(equity) or equity <= 0:
            raise ValueError(f"nonpositive estimated equity at {ts} {kind}")
        if kind in ("close", "trade"):
            nav_rows.append({"ts": ts, "equity": equity, "gross_notional": gross,
                             "replica_reserve_cash": reserve, "price_pnl": price_pnl,
                             "funding_pnl": funding_pnl, "fees": fees, "slippage": slippage,
                             "gross_to_equity": gross / equity})
    if q or len(funding_rows) != len(funding):
        raise ValueError("incomplete final liquidation or observed funding accounting")
    return {"nav": pd.DataFrame(nav_rows), "monthly": pd.DataFrame(monthly_rows),
            "trades": pd.DataFrame(trade_rows), "funding": pd.DataFrame(funding_rows),
            "terminals": pd.DataFrame(terminal_rows),
            "final": {"equity": equity, "price_pnl": price_pnl, "funding_pnl": funding_pnl,
                      "fees": fees, "slippage": slippage}}


def terminal_inputs():
    directory = FAMILY / "artifacts/baseline-verification-20260908/terminal-evidence"
    review = directory / "final-review.json"
    if sha(review) != "f735e3f11941ff01d7a65cc2db1a1e6dde2265d098ace0599ee47e694f354af6":
        raise ValueError("terminal review mutated")
    result, checked = [], {str(review): sha(review)}
    for item in json.loads(review.read_text())["events"]:
        path = directory / f"{item['symbol']}-index-1m.json"
        meta = json.loads(path.with_name(path.name + ".meta.json").read_text())
        if sha(path) != meta.get("sha256", meta.get("content_sha256")):
            raise ValueError("terminal raw index changed")
        candles = np.asarray([[float(x) for x in row[1:5]] for row in json.loads(path.read_text())])
        if not item["index_1m_complete_window"]:
            raise ValueError("terminal window not complete")
        result.append({"symbol": item["symbol"][:-4] + "/USDT:USDT", "ts": pd.Timestamp(item["terminal_utc"]),
                       "center": float(candles.mean()), "low": float(candles[:, 2].mean()),
                       "high": float(candles[:, 1].mean())})
        checked[str(path)] = sha(path)
    return result, checked


def compare_tables(result, directory):
    errors = {}
    fields = {
        "nav": ("equity", "gross_notional", "price_pnl", "funding_pnl", "fees", "slippage", "gross_to_equity"),
        "monthly": ("account_start_equity", "account_end_equity", "account_return"),
        "trades": ("new_quantity", "delta_quantity", "traded_notional", "fee", "slippage"),
        "funding": ("quantity", "rate", "estimate_mark", "funding_cash"),
        "terminals": ("quantity", "settlement_price", "fee", "slippage"),
    }
    for name, columns in fields.items():
        actual = result[name]
        expected = pd.read_parquet(directory / f"{name}.parquet")
        identity = ["month"] if name == "monthly" else ["ts"]
        if name in ("trades", "funding", "terminals"):
            identity.append("symbol")
        if name == "funding":
            identity.append("rate_type")
        if not actual[identity].equals(expected[identity]):
            raise ValueError(f"event identities/order differ for {name}")
        for column in columns:
            diff = actual[column].to_numpy() - expected[column].to_numpy()
            scale = np.maximum(1, np.abs(expected[column].to_numpy()))
            errors[f"{name}.{column}"] = {"max_absolute": float(np.max(np.abs(diff))),
                                          "max_relative": float(np.max(np.abs(diff) / scale))}
            if not np.allclose(actual[column], expected[column], rtol=1e-10, atol=1e-6):
                raise ValueError((name, column, errors[f"{name}.{column}"]))
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=ARTIFACTS / "accounts")
    parser.add_argument("--output", type=Path, default=ARTIFACTS / "independent-funded-audit")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    retained = json.loads((args.run / "summary.json").read_text())
    started = json.loads((args.run / "started.json").read_text())
    checked = {}
    for role, source in started["paths"].items():
        if role == "script":
            continue  # Audit frozen outputs even if the working runner later evolves.
        path = Path(source)
        if sha(path) != started["sha256"][role]:
            raise ValueError(f"changed frozen input {role}")
        checked[str(path)] = sha(path)
    for relative, digest in retained["output_sha256"].items():
        if sha(args.run / relative) != digest:
            raise ValueError(f"changed target output {relative}")
    holdings = pd.read_parquet(started["paths"]["holdings"])
    execution = pd.read_parquet(started["paths"]["execution"])
    funding = pd.read_parquet(started["paths"]["funding"])
    daily = load_verified_returned_daily().set_index(["ts", "symbol"]).sort_index()
    terminals, terminal_hashes = terminal_inputs()
    checked.update(terminal_hashes)
    start, end = pd.Timestamp(retained["start"]), pd.Timestamp(retained["end"])
    reports, results = [], {}
    for scenario in SCENARIOS:
        print(f"INDEPENDENT_ACCOUNT_START {scenario}", flush=True)
        result = reconstruct(holdings, execution, daily, funding, terminals, scenario, start, end)
        errors = compare_tables(result, args.run / scenario)
        final = result["final"]
        path = np.r_[INITIAL, result["nav"].equity.to_numpy()]
        dd = path / np.maximum.accumulate(path) - 1
        cash_sum = float(result["funding"].funding_cash.sum())
        target_summary = json.loads((args.run / scenario / "summary.json").read_text())
        if not np.isclose(final["equity"], target_summary["final_equity"], rtol=1e-10, atol=1e-6):
            raise ValueError("final equity mismatch")
        if len(result["monthly"]) != 76:
            raise ValueError("missing month in independent account")
        report = {
            "scenario": scenario, "status": "INDEPENDENT_ESTIMATED_FUNDED_REPLICA_MATCH_NOT_VERIFIED_NET",
            "comparisons": errors, "final": final,
            "total_return": float(final["equity"] / INITIAL - 1),
            "daily_and_rebalance_mdd": float(dd.min()),
            "max_daily_and_rebalance_gross_to_equity": float(result["nav"].gross_to_equity.max()),
            "nav_samples": len(result["nav"]), "months": len(result["monthly"]),
            "funding_events": len(result["funding"]), "terminal_events": len(result["terminals"]),
            "funding_cash_independent_sum": cash_sum,
            "funding_cash_sum_error": cash_sum - final["funding_pnl"],
            "final_identity_error": final["equity"] - INITIAL - final["price_pnl"] - final["funding_pnl"] + final["fees"] + final["slippage"],
            "monthly_chain_error": float(np.prod(1 + result["monthly"].account_return) - final["equity"] / INITIAL),
            "funding_source_quality_counts": result["funding"].source_quality.value_counts().to_dict(),
            "funding_cash_by_source_quality": result["funding"].groupby("source_quality").funding_cash.sum().to_dict(),
        }
        reports.append(report)
        results[scenario] = result
        print(json.dumps(report, ensure_ascii=False, allow_nan=False), flush=True)
    if any(sha(path) != digest for path, digest in checked.items()):
        raise ValueError("input changed during independent audit")
    args.output.mkdir(parents=True)
    for scenario, result in results.items():
        folder = args.output / scenario
        folder.mkdir()
        for table in ("nav", "monthly", "trades", "funding", "terminals"):
            result[table].to_parquet(folder / f"{table}.parquet", index=False)
    summary = {
        "status": "INDEPENDENT_THREE_ESTIMATED_FUNDED_ACCOUNTS_RECONSTRUCTED_NOT_VERIFIED_NET",
        "method": "Independent units-plus-reserve-cash replica; direct event funding cash; analytic piecewise turnover-cost root; separate capital per scenario; no primary runner/kernel arithmetic.",
        "source_run": str(args.run), "source_run_summary_sha256": sha(args.run / "summary.json"),
        "frozen_input_and_terminal_hashes_checked": checked,
        "source_runner_at_start_sha256": started["sha256"]["script"],
        "audit_script_sha256": sha(Path(__file__)),
        "independent_cost_solver_path": str(Path(__file__).with_name("audit_mcsm_price_only_replica_20260909.py")),
        "independent_cost_solver_sha256": sha(Path(__file__).with_name("audit_mcsm_price_only_replica_20260909.py")),
        "comparison_tolerance": {"rtol": 1e-10, "atol": 1e-6},
        "results": reports,
        "limitations": "Reconstructs only the stated observed-event estimates and terminal proxies. No funding calendar, PIT, fills, portfolio margin, liquidation, or true-net certification. Endpoint scenarios are not global mathematical bounds or confidence intervals.",
    }
    with (args.output / "summary.json").open("x") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(f"INDEPENDENT_FUNDED_AUDIT_COMPLETE {args.output}", flush=True)


if __name__ == "__main__":
    main()
