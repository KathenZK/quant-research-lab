"""Four continuous fixed-rule accounts; explicit estimated inputs, never verified net.

The frozen accounting kernel remains immutable. This adapter labels every
funding/terminal proxy before calling its arithmetic and never treats a returned
price frame or an observed event inventory as historical PIT/calendar approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from mcsm_baseline_accounting_20260908 import AccountingError, LinearPerpAccount
from verify_mcsm_baseline_20260908 import load_verified_returned_daily

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
OUT = FAMILY / "artifacts/baseline-estimate-20260909"
START = pd.Timestamp("2020-03-01T00:15:00Z")
END = pd.Timestamp("2026-07-01T00:15:00Z")
INITIAL = 100_000.0
KERNEL_SHA = "0445d4e7afa76576558dfd122983dab2c12e523718383f01d45bfc0e2779972c"
TERMINAL_SHA = "f735e3f11941ff01d7a65cc2db1a1e6dde2265d098ace0599ee47e694f354af6"
SCENARIOS = ("price_only", "estimated_center", "estimated_adverse", "estimated_favorable")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_new(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as file:
        json.dump(obj, file, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        file.write("\n")


def finite_positive(value, label):
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{label}: missing/nonpositive estimate input")
    return float(value)


def choose_funding_mark(row, scenario):
    """For a long, a positive rate is a payment; a negative rate is income."""
    center = finite_positive(float(row["mark_center"]), "mark_center")
    lo = finite_positive(float(row["mark_low"]), "mark_low")
    hi = finite_positive(float(row["mark_high"]), "mark_high")
    if not lo <= center <= hi:
        raise ValueError("funding proxy center outside its stated interval")
    rate = float(row["funding_rate"])
    if not np.isfinite(rate):
        raise ValueError("missing funding rate cannot be zero-filled")
    if scenario == "estimated_center":
        return center
    if scenario == "estimated_adverse":
        return hi if rate >= 0 else lo
    if scenario == "estimated_favorable":
        return lo if rate >= 0 else hi
    raise ValueError("price_only must not book funding")


def load_terminals():
    directory = FAMILY / "artifacts/baseline-verification-20260908/terminal-evidence"
    review_path = directory / "final-review.json"
    if sha(review_path) != TERMINAL_SHA:
        raise ValueError("frozen terminal review changed")
    result = []
    for event in json.loads(review_path.read_text())["events"]:
        symbol = event["symbol"]
        path = directory / f"{symbol}-index-1m.json"
        meta = json.loads(path.with_name(path.name + ".meta.json").read_text())
        digest = meta.get("sha256", meta.get("content_sha256"))
        if digest is None or sha(path) != digest:
            raise ValueError(f"terminal index source hash changed: {symbol}")
        raw = json.loads(path.read_text())
        values = np.asarray([[float(x) for x in row[1:5]] for row in raw])
        lo, hi = values[:, 2].mean(), values[:, 1].mean()
        center = values.mean()
        if not (np.isclose(lo, event["index_1m_envelope_mean_low"], atol=1e-12)
                and np.isclose(hi, event["index_1m_envelope_mean_high"], atol=1e-12)
                and event["index_1m_complete_window"]):
            raise ValueError("terminal envelope/grid disagreement")
        result.append({"symbol": symbol[:-4] + "/USDT:USDT",
                       "ts": pd.Timestamp(event["terminal_utc"]),
                       "center": float(center), "low": float(lo), "high": float(hi),
                       "source_path": str(path.relative_to(FAMILY)), "source_sha256": digest,
                       "source_quality": "CONDITIONAL_INDEX_MINUTE_PROXY_NOT_EXACT_SETTLEMENT"})
    return result


def compact_row(row):
    """Keep all cash deltas but avoid copying 10-position snapshots per funding event."""
    return {key: value for key, value in row.items() if key not in ("positions", "details")}


def performance(nav, daily, monthly, final):
    equities = np.r_[INITIAL, nav.equity.to_numpy(float)]
    dd = equities / np.maximum.accumulate(equities) - 1
    trough_pos = int(np.argmin(dd))
    peak_pos = int(np.argmax(equities[:trough_pos + 1]))
    sample_times = [START] + nav.ts.tolist()
    duration = (END - START).total_seconds() / (365.25 * 86400)
    close_series = daily.set_index("ts").equity
    rets = close_series.pct_change().dropna()
    yearly = []
    previous = INITIAL
    # Include final clearing 00:15 in the last (2026 H1) period.
    for year in range(2020, 2027):
        cutoff = min(pd.Timestamp(f"{year + 1}-01-01", tz="UTC"), END)
        values = nav.loc[nav.ts.le(cutoff)]
        equity = float(values.equity.iloc[-1])
        yearly.append({"year": year, "period_start_equity": previous,
                       "period_end_equity": equity, "return": equity / previous - 1,
                       "partial_year": year in (2020, 2026)})
        previous = equity
    return {
        "initial_equity": INITIAL, "final_equity": float(final["equity"]),
        "net_profit_model_usdt": float(final["equity"] - INITIAL),
        "total_return": float(final["equity"] / INITIAL - 1),
        "cagr_365_25": float((final["equity"] / INITIAL) ** (1 / duration) - 1),
        "max_drawdown_daily_and_rebalance": float(dd.min()),
        "drawdown_peak_time": sample_times[peak_pos],
        "drawdown_peak_equity": float(equities[peak_pos]),
        "drawdown_trough_time": sample_times[trough_pos],
        "drawdown_trough_equity": float(equities[trough_pos]),
        "max_drawdown_sampling": "complete daily closes plus rebalance boundaries; not intraday",
        "daily_sharpe_365_zero_rf": float(rets.mean() / rets.std(ddof=1) * np.sqrt(365)) if rets.std(ddof=1) else None,
        "daily_annualized_volatility_365": float(rets.std(ddof=1) * np.sqrt(365)),
        "monthly_win_rate": float(monthly.account_return.gt(0).mean()),
        "monthly_returns": len(monthly), "max_gross_to_equity_sampled": float(nav.gross_to_equity.max()),
        "price_pnl_usdt": float(final["price_pnl"]), "funding_pnl_usdt": float(final["funding_pnl"]),
        "fees_usdt": float(final["fees"]), "slippage_usdt": float(final["slippage"]),
        "cash_attribution_error": float(final["equity"] - INITIAL - final["price_pnl"]
                                        - final["funding_pnl"] + final["fees"] + final["slippage"]),
        "yearly": yearly,
    }


def validate_holdings(holdings, terminals=()):
    h = holdings.copy()
    for col in ("month", "entry_ts", "exit_ts"):
        h[col] = pd.to_datetime(h[col], utc=True)
    expected = pd.date_range("2020-03-01", "2026-06-01", freq="MS", tz="UTC")
    if not h.groupby("month").size().reindex(expected).eq(10).all() or len(h) != 760:
        raise ValueError("exactly ten original-rule names are required in every one of 76 months")
    if h.duplicated(["month", "symbol"]).any() or not np.allclose(h.weight, .1):
        raise ValueError("duplicate or non-10-percent holding")
    if not h.entry_ts.eq(h.month + pd.Timedelta(minutes=15)).all():
        raise ValueError("entry time changed")
    if not h.exit_ts.gt(h.entry_ts).all():
        raise ValueError("nonpositive holding interval")
    expected_exits = h.month + pd.offsets.MonthBegin(1) + pd.Timedelta(minutes=15)
    terminal_keys = {(event["symbol"], pd.Timestamp(event["ts"])) for event in terminals}
    for row, expected_exit in zip(h.itertuples(index=False), expected_exits):
        if row.exit_ts == expected_exit:
            continue
        if not (row.exit_ts < expected_exit and (row.symbol, row.exit_ts) in terminal_keys):
            raise ValueError("exit must be next calendar month or hash-verified official terminal")
    return h


def run_scenario(holdings, execution, daily_prices, funding, terminals, scenario):
    """Replay one self-financed path; input completeness failures never skip months."""
    if scenario not in SCENARIOS:
        raise ValueError("unknown scenario")
    h = validate_holdings(holdings, terminals)
    execution = execution.copy()
    execution["ts"] = pd.to_datetime(execution.ts, utc=True)
    if execution.duplicated(["ts", "symbol"]).any():
        raise ValueError("duplicate monthly execution mark")
    execution_map = {ts: group.set_index("symbol").price.to_dict() for ts, group in execution.groupby("ts")}
    daily_prices = daily_prices.copy()
    daily_prices["ts"] = pd.to_datetime(daily_prices.ts, utc=True)
    daily_prices = daily_prices.set_index(["ts", "symbol"]).sort_index()
    if daily_prices.index.duplicated().any():
        raise ValueError("duplicate daily valuation source")
    targets = {month + pd.Timedelta(minutes=15): group.set_index("symbol").weight.to_dict()
               for month, group in h.groupby("month")}
    targets[END] = {}
    events = [(ts, 3, "rebalance", target) for ts, target in targets.items()]
    events += [(ts, 0, "daily", None) for ts in pd.date_range("2020-03-02", "2026-07-01", freq="D", tz="UTC")]
    events += [(event["ts"], 2, "terminal", event) for event in terminals if START < event["ts"] <= END]
    if scenario != "price_only":
        funding = funding.copy()
        funding["ts"] = pd.to_datetime(funding.ts, utc=True)
        if funding.duplicated(["ts", "symbol", "rate_type"]).any():
            raise ValueError("duplicate native funding identity")
        if not funding.ts.gt(START).all() or not funding.ts.le(END).all():
            raise ValueError("funding source not clipped to declared account interval")
        events += [(row["ts"], 1, "funding", row) for row in funding.to_dict("records")]
    events.sort(key=lambda item: (item[0], item[1], str((item[3] or {}).get("symbol", ""))))
    account = LinearPerpAccount(INITIAL)
    daily_rows, nav_rows, fund_rows, terminal_rows, trade_rows, month_rows = [], [], [], [], [], []
    prev_rebalance_equity = INITIAL
    previous_month = None
    booked_keys = []
    for ts, _, kind, payload in events:
        if kind == "rebalance":
            required_symbols = set(account.positions) | set(payload)
            observed = {symbol: price for symbol, price in execution_map.get(ts, {}).items()
                        if symbol in required_symbols}
            row = account.rebalance(ts, payload, observed)
            for trade in row["details"]["trades"]:
                trade_rows.append({"ts": ts, **trade})
            if previous_month is not None:
                month_rows.append({"month": previous_month, "account_start_equity": prev_rebalance_equity,
                                   "account_end_equity": row["equity"],
                                   "account_return": row["equity"] / prev_rebalance_equity - 1})
            prev_rebalance_equity = row["equity"]
            if ts == START:
                # Attribute the original entry cost to the first holding month.
                prev_rebalance_equity = INITIAL
            previous_month = ts.floor("D")
        elif kind == "daily":
            values = {}
            day = ts - pd.Timedelta(days=1)
            for symbol in account.positions:
                try:
                    source = daily_prices.loc[(day, symbol)]
                except KeyError as exc:
                    raise AccountingError(f"missing daily mark {symbol} {day}") from exc
                if not isinstance(source["eligible"], (bool, np.bool_)) or not source["eligible"]:
                    raise AccountingError(f"ineligible daily mark {symbol} {day}")
                values[symbol] = finite_positive(float(source["close"]), f"daily {symbol} {day}")
            row = account.mark(ts, values)
            daily_rows.append({"ts": ts, **compact_row(row)})
        elif kind == "funding":
            symbol = payload["symbol"]
            if symbol not in account.positions:
                raise AccountingError(f"funding supplied outside actual position {symbol} {ts}")
            mark = choose_funding_mark(payload, scenario)
            row = account.funding(ts, symbol, float(payload["funding_rate"]), mark,
                                  rate_type=payload["rate_type"])
            fund_rows.append({"ts": ts, "symbol": symbol, "rate_type": payload["rate_type"],
                              "rate": float(payload["funding_rate"]), "estimate_mark": mark,
                              "quantity": row["details"]["quantity"],
                              "funding_cash": row["event_funding_pnl"],
                              "source_quality": payload.get("mark_source", payload.get("mark_quality", "UNSPECIFIED_ESTIMATE"))})
            booked_keys.append((ts, symbol, payload["rate_type"]))
        else:
            if payload["symbol"] not in account.positions:
                continue
            field = {"estimated_adverse": "low", "estimated_favorable": "high"}.get(scenario, "center")
            price = payload[field]
            row = account.terminal_close(ts, payload["symbol"], price,
                                         f"ESTIMATED:{payload['source_path']} sha256={payload['source_sha256']}",
                                         settlement_fee_rate=.001, settlement_slippage_rate=0)
            terminal_rows.append({"ts": ts, **row["details"], "source_quality": payload["source_quality"],
                                  "account_equity_mixed_marks": row["equity"],
                                  "gross_notional_mixed_marks": row["gross_notional"],
                                  "all_marks_at_event_time": row["all_marks_at_event_time"],
                                  "not_a_synchronous_nav_observation": True})
        if kind in ("daily", "rebalance"):
            nav_rows.append({"ts": ts, "sample_kind": kind, **compact_row(row),
                             "gross_to_equity": row["gross_notional"] / row["equity"]})
        # No algorithm reads old ledger snapshots. Preserve every numeric event
        # delta while full executed trades and funding identities are kept above.
        account.ledger[-1] = compact_row(account.ledger[-1])
    if account.positions:
        raise AccountingError("final liquidation left positions")
    if len(month_rows) != 76:
        raise AccountingError("incomplete monthly account")
    if scenario != "price_only" and len(booked_keys) != len(funding):
        raise AccountingError("an observed funding event was silently skipped")
    nav, daily, months = pd.DataFrame(nav_rows), pd.DataFrame(daily_rows), pd.DataFrame(month_rows)
    final = account.snapshot()
    metrics = performance(nav, daily, months, final)
    metrics.update(scenario=scenario, status="EXPLORATORY_ESTIMATED_ACCOUNT_NOT_VERIFIED_NET",
                   calendar_verified=False, pit_verified=False, margin_liquidation_simulated=False,
                   funding_events_booked=len(booked_keys), terminal_events=len(terminal_rows),
                   monthly_entry_count=76, full_account_closed=True,
                   terminal_fees_usdt=float(sum(r["fee"] for r in terminal_rows)))
    return {"metrics": metrics, "nav": nav, "daily": daily, "monthly": months,
            "trades": pd.DataFrame(trade_rows), "funding": pd.DataFrame(fund_rows),
            "terminals": pd.DataFrame(terminal_rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdings", type=Path, default=OUT / "inputs/holdings.parquet")
    parser.add_argument("--execution", type=Path, default=OUT / "inputs/monthly_execution_prices.parquet")
    parser.add_argument("--funding", type=Path, default=OUT / "funding/estimated-funding-events.parquet")
    parser.add_argument("--output", type=Path, default=OUT / "accounts")
    parser.add_argument("--price-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if sha(Path(__file__).with_name("mcsm_baseline_accounting_20260908.py")) != KERNEL_SHA:
        raise ValueError("frozen accounting kernel changed")
    input_summary_path = args.holdings.parent / "summary.json"
    input_summary = json.loads(input_summary_path.read_text())
    if (input_summary["holdings"] != 760 or input_summary["months"] != 76
            or input_summary["missing_nonterminal_exit_prices"] != 0):
        raise ValueError("incomplete 76-month input receipt")
    for name, digest in input_summary["files"].items():
        if sha(args.holdings.parent / name) != digest:
            raise ValueError(f"input projection/receipt hash mismatch: {name}")
    paths = {"holdings": args.holdings, "execution": args.execution,
             "input_summary": input_summary_path,
             "script": Path(__file__), "contract": FAMILY / "specs/binance-1d-mcsm-baseline-estimate-20260909.md"}
    if not args.price_only:
        paths["funding"] = args.funding
        funding_summary_path = args.funding.parent / "summary.json"
        funding_summary = json.loads(funding_summary_path.read_text())
        if (not funding_summary["all_observed_event_marks_usable"]
                or funding_summary["events_sha256"] != sha(args.funding)):
            raise ValueError("observed funding projection incomplete or changed")
        plan_reference = Path(funding_summary.get("plan_path", "plan-v2.json"))
        funding_plan_path = (args.funding.parent / plan_reference if len(plan_reference.parts) == 1
                             else ROOT / plan_reference)
        if not funding_plan_path.resolve().is_relative_to(args.funding.parent.resolve()):
            raise ValueError("funding plan must remain inside this estimate evidence directory")
        funding_plan = json.loads(funding_plan_path.read_text())
        if (sha(funding_plan_path) != funding_summary["plan_sha256"]
                or funding_plan["holdings_sha256"] != sha(args.holdings)):
            raise ValueError("funding built from different holdings or plan changed")
        paths["funding_summary"] = funding_summary_path
        paths["funding_plan"] = funding_plan_path
    frozen_hashes = {key: sha(path) for key, path in paths.items()}
    save_new(args.output / "started.json", {"status": "ESTIMATE_INPUTS_FROZEN_BEFORE_ACCOUNT_OUTPUT",
                                           "paths": paths, "sha256": frozen_hashes,
                                           "kernel_sha256": KERNEL_SHA, "no_verified_net_claim": True})
    holdings, execution = pd.read_parquet(args.holdings), pd.read_parquet(args.execution)
    daily = load_verified_returned_daily()
    funding = pd.DataFrame() if args.price_only else pd.read_parquet(args.funding)
    terminals = load_terminals()
    metrics = []
    for scenario in (("price_only",) if args.price_only else SCENARIOS):
        print(f"ACCOUNT_START {scenario}", flush=True)
        result = run_scenario(holdings, execution, daily, funding, terminals, scenario)
        directory = args.output / scenario
        directory.mkdir()
        for kind in ("nav", "daily", "monthly", "trades", "funding", "terminals"):
            result[kind].to_parquet(directory / f"{kind}.parquet", index=False)
            if kind in ("monthly", "terminals"):
                result[kind].to_csv(directory / f"{kind}.csv", index=False)
        save_new(directory / "summary.json", result["metrics"])
        metrics.append(result["metrics"])
        print(json.dumps(result["metrics"], ensure_ascii=False, default=str, allow_nan=False), flush=True)
    if any(sha(paths[key]) != value for key, value in frozen_hashes.items()):
        raise ValueError("input or source mutated during execution")
    save_new(args.output / "summary.json", {
        "status": "EXPLORATORY_ESTIMATED_ACCOUNT_NOT_VERIFIED_NET", "results": metrics,
        "initial_equity": INITIAL, "start": START, "end": END,
        "input_sha256": frozen_hashes, "input_files_unchanged": True,
        "kernel_sha256": KERNEL_SHA, "no_missing_months_compounded_away": True,
        "output_sha256": {str(path.relative_to(args.output)): sha(path)
                          for path in sorted(args.output.rglob("*")) if path.is_file()},
    })


if __name__ == "__main__":
    main()
