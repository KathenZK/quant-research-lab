"""Independent spot-cash replica audit of the estimated price-only perp account.

Consumes hash-verified frozen returned price frames and retained source evidence.
No accounting-kernel or estimated-runner arithmetic is called. For a 1x long-only
linear perp without funding, fixed units can be independently represented as
spot units plus reserve cash. This identity does not simulate actual spot trading
or verify the original perpetual strategy's funding, tradability, or liquidation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from verify_mcsm_baseline_20260908 import load_verified_returned_daily

FAMILY = Path(__file__).resolve().parents[1]
ARTIFACTS = FAMILY / "artifacts/baseline-estimate-20260909"
INITIAL, FEE, SLIP = 100_000.0, .001, .0004


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def solve_piecewise(pre_equity, old_value, weights):
    """Analytic root on turnover's linear segments, not the kernel bisection."""
    symbols = sorted(set(old_value) | set(weights))
    knots = sorted({0.0, *(old_value.get(s, 0) / w for s, w in weights.items())})
    knots.append(float("inf"))
    for low, high in zip(knots[:-1], knots[1:]):
        probe = (low + high) / 2 if np.isfinite(high) else low + max(1, pre_equity)
        signs = {s: 1 if weights.get(s, 0) * probe >= old_value.get(s, 0) else -1 for s in symbols}
        slope = sum(signs[s] * weights.get(s, 0) for s in symbols)
        intercept = sum(-signs[s] * old_value.get(s, 0) for s in symbols)
        root = (pre_equity - (FEE + SLIP) * intercept) / (1 + (FEE + SLIP) * slope)
        if low - 1e-8 <= root <= high + 1e-8 and root > 0:
            return root
    raise ValueError("independent analytic cost equation has no positive root")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=ARTIFACTS / "price-only-first-run")
    parser.add_argument("--output", type=Path, default=ARTIFACTS / "independent-price-only-audit")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    retained = json.loads((args.run / "summary.json").read_text())
    started = json.loads((args.run / "started.json").read_text())
    checked = {}
    for role in ("holdings", "execution", "input_summary", "contract"):
        path = Path(started["paths"][role])
        assert sha(path) == started["sha256"][role], f"changed {role} input"
        checked[str(path)] = sha(path)
    for relative, digest in retained["output_sha256"].items():
        assert sha(args.run / relative) == digest, f"changed target artifact {relative}"
    holdings = pd.read_parquet(started["paths"]["holdings"])
    executions = pd.read_parquet(started["paths"]["execution"])
    daily = load_verified_returned_daily().set_index(["ts", "symbol"]).sort_index()
    target_nav = pd.read_parquet(args.run / "price_only/nav.parquet")
    target_monthly = pd.read_parquet(args.run / "price_only/monthly.parquet")
    target_trades = pd.read_parquet(args.run / "price_only/trades.parquet")
    target_summary = retained["results"][0]
    assert target_summary["scenario"] == "price_only"
    start, end = pd.Timestamp(retained["start"]), pd.Timestamp(retained["end"])
    prices = {ts: group.set_index("symbol").price.to_dict() for ts, group in executions.groupby("ts")}
    targets = {ts: group.set_index("symbol").weight.to_dict() for ts, group in holdings.groupby("entry_ts")}
    targets[end] = {}
    events = [(ts, 2, "trade", weights) for ts, weights in targets.items()]
    events += [(ts, 0, "close", None) for ts in pd.date_range(start.floor("D") + pd.Timedelta(days=1), end.floor("D"), freq="D")]
    terminal_dir = FAMILY / "artifacts/baseline-verification-20260908/terminal-evidence"
    review_path = terminal_dir / "final-review.json"
    assert sha(review_path) == "f735e3f11941ff01d7a65cc2db1a1e6dde2265d098ace0599ee47e694f354af6"
    terminals = {}
    for event in json.loads(review_path.read_text())["events"]:
        raw_path = terminal_dir / f"{event['symbol']}-index-1m.json"
        meta = json.loads(raw_path.with_name(raw_path.name + ".meta.json").read_text())
        assert sha(raw_path) == meta.get("sha256", meta.get("content_sha256"))
        raw = json.loads(raw_path.read_text())
        ts = pd.Timestamp(event["terminal_utc"])
        symbol = event["symbol"][:-4] + "/USDT:USDT"
        settlement = float(np.mean([[float(x) for x in candle[1:5]] for candle in raw]))
        terminals[symbol] = settlement
        events.append((ts, 1, "terminal", {"symbol": symbol, "price": settlement}))
        checked[str(raw_path)] = sha(raw_path)
    events.sort(key=lambda event: (event[0], event[1]))
    q, last_price = {}, {}
    reserve, cumulative_price, cumulative_fee, cumulative_slip = INITIAL, 0.0, 0.0, 0.0
    nav_rows, monthly_rows, trade_rows = [], [], []
    previous_month, previous_month_start = None, INITIAL

    def mark(observed):
        nonlocal cumulative_price
        for symbol, quantity in q.items():
            value = float(observed[symbol])
            assert np.isfinite(value) and value > 0
            cumulative_price += quantity * (value - last_price[symbol])
            last_price[symbol] = value

    for ts, _, kind, payload in events:
        if kind == "terminal":
            symbol, settlement = payload["symbol"], payload["price"]
            if symbol not in q:
                continue
            quantity = q.pop(symbol)
            cumulative_price += quantity * (settlement - last_price.pop(symbol))
            cost = quantity * settlement * FEE
            cumulative_fee += cost
            reserve += quantity * settlement - cost
            continue
        if kind == "close":
            observed = {}
            for symbol in q:
                record = daily.loc[(ts - pd.Timedelta(days=1), symbol)]
                assert isinstance(record.eligible, (bool, np.bool_)) and record.eligible
                observed[symbol] = float(record.close)
            mark(observed)
        else:
            observed = prices[ts]
            mark(observed)
            old_values = {symbol: quantity * observed[symbol] for symbol, quantity in q.items()}
            pre = reserve + sum(old_values.values())
            post = solve_piecewise(pre, old_values, payload)
            new_q = {symbol: weight * post / observed[symbol] for symbol, weight in payload.items()}
            for symbol in sorted(set(q) | set(new_q)):
                delta = new_q.get(symbol, 0) - q.get(symbol, 0)
                notional = abs(delta) * observed[symbol]
                fee, slip = notional * FEE, notional * SLIP
                reserve -= delta * observed[symbol] + fee + slip
                cumulative_fee += fee
                cumulative_slip += slip
                trade_rows.append({"ts": ts, "symbol": symbol, "new_quantity": new_q.get(symbol, 0),
                                   "delta_quantity": delta, "traded_notional": notional, "fee": fee, "slippage": slip})
            q = new_q
            last_price = {symbol: observed[symbol] for symbol in q}
            equity = reserve + sum(q[s] * last_price[s] for s in q)
            if previous_month is not None:
                monthly_rows.append({"month": previous_month, "account_start_equity": previous_month_start,
                                     "account_end_equity": equity, "account_return": equity / previous_month_start - 1})
            previous_month, previous_month_start = ts.floor("D"), equity if ts != start else INITIAL
        gross = sum(q[s] * last_price[s] for s in q)
        equity = reserve + gross
        nav_rows.append({"ts": ts, "equity": equity, "gross_notional": gross, "replica_reserve_cash": reserve,
                         "price_pnl": cumulative_price, "fees": cumulative_fee, "slippage": cumulative_slip})
    assert not q
    independent = pd.DataFrame(nav_rows)
    monthly = pd.DataFrame(monthly_rows)
    trades = pd.DataFrame(trade_rows)
    assert independent.ts.tolist() == target_nav.ts.tolist()
    assert monthly.month.tolist() == target_monthly.month.tolist()
    assert trades[["ts", "symbol"]].equals(target_trades[["ts", "symbol"]])
    errors = {}
    for table_name, actual, expected, cols in (
        ("nav", independent, target_nav, ("equity", "gross_notional", "price_pnl", "fees", "slippage")),
        ("monthly", monthly, target_monthly, ("account_start_equity", "account_end_equity", "account_return")),
        ("trades", trades, target_trades, ("new_quantity", "delta_quantity", "traded_notional", "fee", "slippage")),
    ):
        for col in cols:
            diff = actual[col].to_numpy() - expected[col].to_numpy()
            scale = np.maximum(1, np.abs(expected[col].to_numpy()))
            errors[f"{table_name}.{col}"] = {"max_absolute": float(np.max(np.abs(diff))),
                                                 "max_relative": float(np.max(np.abs(diff) / scale))}
            assert np.allclose(actual[col], expected[col], rtol=1e-10, atol=1e-6), (table_name, col, errors[f"{table_name}.{col}"])
    path = np.r_[INITIAL, independent.equity.to_numpy()]
    dd = path / np.maximum.accumulate(path) - 1
    contributions = holdings[["month", "symbol", "entry_price", "exit_price", "terminal", "formation_return"]].copy()
    for symbol, terminal_price in terminals.items():
        contributions.loc[contributions.symbol.eq(symbol) & contributions.terminal, "exit_price"] = terminal_price
    contributions["asset_holding_price_return"] = contributions.exit_price / contributions.entry_price - 1
    contributions["initial_equal_weight_return_contribution"] = contributions.asset_holding_price_return * .1
    large_2021 = contributions.loc[contributions.month.dt.year.eq(2021)].nlargest(20, "initial_equal_weight_return_contribution")
    summary = {
        "status": "INDEPENDENT_PRICE_ONLY_REPLICA_MATCH_ESTIMATE_NOT_VERIFIED_NET",
        "method": "Independent fixed-unit spot-plus-reserve-cash representation; analytic piecewise cost solver; no kernel or run_scenario arithmetic called.",
        "source_run": str(args.run), "source_run_summary_sha256": sha(args.run / "summary.json"),
        "frozen_input_and_terminal_hashes_checked": checked,
        "daily_returned_frame_verified_by_frozen_reader": True,
        "source_runner_at_start_sha256": started["sha256"]["script"],
        "audit_script_sha256": sha(Path(__file__)),
        "comparison_tolerance": {"rtol": 1e-10, "atol": 1e-6},
        "comparisons": errors,
        "nav_samples": len(independent), "months": len(monthly), "trade_rows": len(trades),
        "independent_final_equity": float(equity), "independent_total_return": float(equity / INITIAL - 1),
        "independent_daily_and_rebalance_mdd": float(dd.min()),
        "independent_price_pnl": cumulative_price, "independent_fees": cumulative_fee,
        "independent_slippage": cumulative_slip,
        "final_identity_error": float(equity - INITIAL - cumulative_price + cumulative_fee + cumulative_slip),
        "monthly_chain_error": float(np.prod(1 + monthly.account_return) - equity / INITIAL),
        "largest_2021_asset_month_contributions": json.loads(large_2021.to_json(orient="records", date_format="iso")),
        "limitations": "Price-only counterfactual with the same terminal proxies; this does not verify funding completeness, PIT, fills, margin, or profitability of actual perpetual execution.",
    }
    args.output.mkdir(parents=True)
    independent.to_csv(args.output / "independent-nav.csv", index=False)
    monthly.to_csv(args.output / "independent-monthly.csv", index=False)
    contributions.to_csv(args.output / "asset-month-price-contributions.csv", index=False)
    with (args.output / "summary.json").open("x") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
