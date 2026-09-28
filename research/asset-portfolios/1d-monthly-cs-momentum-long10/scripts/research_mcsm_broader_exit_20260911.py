"""Two precommitted breadth exits, reusing frozen monthly Top10 inputs.

No entry, funding signal, market hedge, or parameter search is introduced.
Funding remains an observed, partially proxy-valued diagnostic, not verified net.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_lab.data.research_bundle import require_research_startup
from research_mcsm_single_asset_exit_20260910 import (
    DAY, FAMILY, INITIAL, ROOT, SCENARIOS, daily_features, leg_diagnostics,
    load_frozen_inputs, replay_exit, save, sha,
)

OLD = FAMILY / "artifacts/mechanism-round-20260910/single-exit"
COMPLETION = FAMILY / "artifacts/mechanism-round-20260910/completion.json"
OUT = FAMILY / "artifacts/drawdown-frequency-round-20260911/broader-exit"
RULES = ("x5", "x10")


def broaden_exit_plan(holdings, original_exits, features, rule):
    """At each month's first original exit, add bottom-five or all-ten exits.

    X5 takes the union, not a quota: an original trigger outside the bottom
    five still exits. Later original exits remain, deduplicated by earliest
    timestamp. All rankings are strictly from the already-closed signal day.
    """
    if rule not in RULES:
        raise ValueError("unknown frozen breadth rule")
    if original_exits.duplicated(["month", "symbol"]).any():
        raise ValueError("duplicate original monthly exit")
    original = original_exits.set_index(["month", "symbol"]).to_dict("index")
    plan, decisions = [], []
    for month, basket in holdings.groupby("month", sort=True):
        names = sorted(basket.symbol)
        if len(names) != 10 or len(set(names)) != 10:
            raise ValueError("ten fixed monthly names required")
        month_exits = original_exits.loc[original_exits.month.eq(month)]
        first = month_exits.exit_ts.min() if len(month_exits) else None
        added = set()
        if first is not None:
            signal_day = first.floor("D") - DAY
            ranking = []
            for symbol in names:
                key = (symbol, signal_day)
                value = features.loc[key, "return_7d"] if key in features.index else np.nan
                if not np.isfinite(value):
                    raise ValueError("first trigger must have all ten valid 7-day returns")
                ranking.append((float(value), symbol))
            ranking.sort()
            added = {symbol for _, symbol in ranking[:5]} if rule == "x5" else set(names)
            first_original = set(month_exits.loc[month_exits.exit_ts.eq(first), "symbol"])
            decisions.append({"month": month, "rule": rule, "first_exit_ts": first,
                              "signal_day": signal_day, "bottom_five": [s for _, s in ranking[:5]],
                              "first_original_symbols": sorted(first_original),
                              "first_union_symbols": sorted(first_original | added),
                              "first_union_count": len(first_original | added),
                              "ranking": [{"symbol": s, "return_7d": r} for r, s in ranking]})
        for holding in basket.itertuples(index=False):
            old = original.get((month, holding.symbol))
            exit_ts = old["exit_ts"] if old else None
            reason = "ORIGINAL_SINGLE_EXIT" if old else None
            if holding.symbol in added:
                if first >= holding.exit_ts:
                    # Existing terminal exits cannot be sold again.
                    if first > holding.exit_ts:
                        decisions[-1].setdefault("already_terminal_symbols", []).append(holding.symbol)
                elif exit_ts is None or first < exit_ts:
                    exit_ts, reason = first, f"FIRST_TRIGGER_{rule.upper()}"
            if exit_ts is not None:
                if not holding.entry_ts < exit_ts < holding.exit_ts:
                    raise ValueError("voluntary exit must be strictly inside original holding")
                plan.append({"month": month, "symbol": holding.symbol, "rule": rule,
                             "signal_day": exit_ts.floor("D") - DAY,
                             "decision_ts": exit_ts - pd.Timedelta(minutes=15),
                             "exit_ts": exit_ts, "original_exit_ts": holding.exit_ts,
                             "reason": reason})
    columns = ["month", "symbol", "rule", "signal_day", "decision_ts", "exit_ts", "original_exit_ts", "reason"]
    result = pd.DataFrame(plan, columns=columns).sort_values(["month", "exit_ts", "symbol"]).reset_index(drop=True)
    if result.duplicated(["month", "symbol"]).any():
        raise ValueError("breadth plan would sell one holding twice")
    return result, decisions


def prior_bar_proven_by_report(report, symbol, exit_ts):
    """Only a complete eligible internal grid proves an unretained prior bar.

    Missing rows before listing or after the last returned row are acceptable
    only when the reported internal first-to-last grid is exactly complete.
    Any ineligible row or unexplained internal gap requires targeted evidence.
    """
    if report.get("status") != "PRICE_DIAGNOSTIC_INPUTS_VERIFIED":
        return False
    if report.get("request", {}).get("backward_bars") != 1 or report.get("request", {}).get("forward_bars") != 0:
        return False
    item = report.get("symbols", {}).get(symbol)
    if not item or item.get("ineligible_rows") != 0 or item.get("eligible_segments") != 1:
        return False
    first = pd.Timestamp(item["first_open_utc"])
    last = pd.Timestamp(item["last_open_utc"])
    prior = exit_ts - pd.Timedelta(minutes=15)
    expected = (last - first) / pd.Timedelta(minutes=15) + 1
    return bool(first <= prior <= last and expected == item["rows"]
                and item.get("complete_windows") == item["rows"])


def extra_activity_requests(required, old_prices, reports):
    """Freeze missing prior-activity requests without examining new outcomes."""
    lookup = old_prices.set_index(["ts", "symbol"])
    proofs, missing = [], []
    for row in required.itertuples(index=False):
        key = (row.exit_ts, row.symbol)
        if key not in lookup.index:
            raise ValueError("expanded exit is absent from old common execution grid")
        price_row = lookup.loc[key]
        if bool(price_row.ordinary_exit_required):
            evidence = "OLD_EXPLICIT_PRIOR_ACTIVITY_CHECK"
        elif prior_bar_proven_by_report(reports[price_row.report_path], row.symbol, row.exit_ts):
            evidence = "OLD_REPORT_COMPLETE_ELIGIBLE_INTERNAL_GRID"
        else:
            evidence = "TARGETED_STARTUP_REQUIRED"
            missing.append({"symbol": row.symbol, "ts": row.exit_ts})
        proofs.append({"symbol": row.symbol, "exit_ts": row.exit_ts, "prior_activity_evidence": evidence,
                       "old_report_path": price_row.report_path, "old_report_sha256": price_row.report_sha256})
    template = next(iter(reports.values()))["request"]
    requests = []
    if missing:
        frame = pd.DataFrame(missing).drop_duplicates().sort_values(["ts", "symbol"])
        for year, group in frame.groupby(frame.ts.dt.year, sort=True):
            names = sorted(group.symbol.unique())
            for offset in range(0, len(names), 32):
                subset = group.loc[group.symbol.isin(names[offset:offset + 32])]
                request = {k: template[k] for k in ("schema_version", "bundle_id", "bundle_path", "bundle_sha256")}
                request.update(mode="price_diagnostic", timeframe="15m", symbols=names[offset:offset + 32],
                               start=(subset.ts.min() - pd.Timedelta(minutes=15)).isoformat(),
                               end=(subset.ts.max() + pd.Timedelta(minutes=15)).isoformat(),
                               gap_policy="contiguous_segments", asset_policy="observed_mixed_diagnostic",
                               backward_bars=1, forward_bars=0)
                requests.append({"label": f"{year}-{offset:03d}", "request": request,
                                 "targets": subset.to_dict("records")})
    return pd.DataFrame(proofs), requests


def load_additional_prior_activity(plans, old_prices, output):
    """Read only startup-returned frames and keep the two target bars as proof."""
    rows = []
    old_map = old_prices.set_index(["ts", "symbol"]).price.to_dict()
    for plan in plans:
        path = output / "activity-requests" / f"{plan['label']}.json"
        if json.loads(path.read_text()) != plan["request"]:
            raise ValueError("activity request was not fixed before execution lookup")
        print(f"ACTIVITY_STARTUP {plan['label']} targets={len(plan['targets'])}", flush=True)
        result = require_research_startup(plan["request"], project_root=ROOT)
        if result.report["status"] != "PRICE_DIAGNOSTIC_INPUTS_VERIFIED":
            raise ValueError("activity startup did not verify price inputs")
        save(output / "activity-reports" / f"{plan['label']}.json", result.report)
        for target in plan["targets"]:
            symbol, ts = target["symbol"], pd.Timestamp(target["ts"])
            bars = result.prices[symbol]
            prior = bars.loc[bars.ts.eq(ts - pd.Timedelta(minutes=15))]
            current = bars.loc[bars.ts.eq(ts)]
            if len(prior) != 1 or not bool(prior.eligible.iloc[0]) or not bool(prior.research_window_valid.iloc[0]):
                raise ValueError(f"new ordinary exit has no valid prior active bar: {symbol} {ts}")
            if len(current) != 1 or not np.isclose(float(current.open.iloc[0]), old_map[(ts, symbol)], rtol=0, atol=0):
                raise ValueError("target returned open differs from frozen old common-grid price")
            for role, frame in (("prior_closed_activity", prior), ("current_open_only", current)):
                row = frame.iloc[0]
                rows.append({"symbol": symbol, "ts": row.ts, "target_exit_ts": ts, "role": role,
                             "open": float(row.open), "eligible": bool(row.eligible),
                             "research_window_valid": bool(row.research_window_valid),
                             "request_path": str(path.relative_to(ROOT)), "request_sha256": sha(path)})
        del result
    return pd.DataFrame(rows)


def load_prior_round():
    """Validate the old completion, immutable engine and returned-frame chain."""
    completion = json.loads(COMPLETION.read_text())
    for relative, digest in completion["files_sha256"].items():
        if sha(ROOT / relative) != digest:
            raise ValueError(f"previous-round frozen evidence changed: {relative}")
    summary = json.loads((OLD / "summary.json").read_text())
    for relative, digest in summary["source_sha256"].items():
        if sha(OLD / relative) != digest:
            raise ValueError(f"previous single-exit source/output changed: {relative}")
    prices = pd.read_parquet(OLD / "execution-prices.parquet")
    exits = pd.read_parquet(OLD / "exit-plan.parquet")
    reports = {}
    for row in prices.itertuples(index=False):
        if row.report_path not in reports:
            if sha(ROOT / row.report_path) != row.report_sha256 or sha(ROOT / row.request_path) != row.request_sha256:
                raise ValueError("old returned execution request/report chain changed")
            reports[row.report_path] = json.loads((ROOT / row.report_path).read_text())
    if prices.duplicated(["ts", "symbol"]).any():
        raise ValueError("duplicate old common execution price")
    return prices, exits, reports, summary


def monthly_leg_cash_bridge(holdings, execution, funding, terminals, exits, exit_prices, result, scenario):
    """Reconcile every monthly account P&L without pretending netting is roundtrip.

    Month-end rebalancing costs belong to the ending month, matching the frozen
    monthly account. Costs for next-month entrants not in the current basket
    are explicitly separate overhead, never arbitrarily assigned to old legs.
    The first month additionally bears initial entry costs. Later entry costs
    are displayed per leg but already belong to the preceding account month.
    """
    prices = execution.set_index(["ts", "symbol"]).price.to_dict()
    early_prices = exit_prices.set_index(["ts", "symbol"]).price.to_dict()
    terminal_prices = {(row["ts"], row["symbol"]): row["center"] for row in terminals}
    cutoff = exits.set_index(["month", "symbol"]).exit_ts.to_dict()
    trades = result["trades"].copy()
    trades["ts"] = pd.to_datetime(trades.ts, utc=True)
    trade_map = trades.set_index(["ts", "symbol"]).to_dict("index")
    early = result["early-exits"]
    early_map = early.set_index(["month", "symbol"]).to_dict("index") if len(early) else {}
    terminal_frame = result["terminals"]
    terminal_map = terminal_frame.set_index(["ts", "symbol"]).to_dict("index") if len(terminal_frame) else {}
    funding = funding.copy()
    funding["ts"] = pd.to_datetime(funding.ts, utc=True)
    fund_by_symbol = {s: g for s, g in funding.groupby("symbol", sort=False)}
    first_month = holdings.month.min()
    records, overhead = [], []
    for month, basket in holdings.groupby("month", sort=True):
        names = set(basket.symbol)
        boundary = month + pd.offsets.MonthBegin(1) + pd.Timedelta(minutes=15)
        next_trades = trades.loc[trades.ts.eq(boundary)]
        other = next_trades.loc[~next_trades.symbol.isin(names)]
        overhead.append({"month": month, "next_month_new_names_charged_to_ending_month": sorted(other.symbol),
                         "next_month_new_names_fee": float(other.fee.sum()),
                         "next_month_new_names_slippage": float(other.slippage.sum())})
        for holding in basket.itertuples(index=False):
            key = (holding.entry_ts, holding.symbol)
            trade = trade_map[key]
            quantity = float(trade["new_quantity"])
            entry_price = float(prices[key])
            end = cutoff.get((month, holding.symbol), holding.exit_ts)
            is_early = end < holding.exit_ts
            is_terminal = not is_early and (end, holding.symbol) in terminal_prices
            end_price = (early_prices[(end, holding.symbol)] if is_early else
                         terminal_prices[(end, holding.symbol)] if is_terminal else prices[(end, holding.symbol)])
            source = fund_by_symbol.get(holding.symbol)
            if scenario == "price_only":
                cash, count = 0., 0
            else:
                if source is None:
                    raise ValueError("funded leg has no original observed event data")
                actual_events = source.loc[source.ts.gt(holding.entry_ts) & source.ts.le(end)]
                cash = float((-quantity * actual_events.mark_center * actual_events.funding_rate).sum())
                count = len(actual_events)
            closing = early_map.get((month, holding.symbol), terminal_map.get((end, holding.symbol), {}))
            boundary_trade = trade_map.get((boundary, holding.symbol), {})
            initial_fee = float(trade["fee"]) if month == first_month else 0.
            initial_slip = float(trade["slippage"]) if month == first_month else 0.
            direct_fee = float(closing.get("fee", 0.))
            direct_slip = float(closing.get("slippage", 0.))
            end_fee = float(boundary_trade.get("fee", 0.))
            end_slip = float(boundary_trade.get("slippage", 0.))
            attributed_fee = initial_fee + direct_fee + end_fee
            attributed_slip = initial_slip + direct_slip + end_slip
            price_pnl = quantity * (end_price - entry_price)
            records.append({"month": month, "symbol": holding.symbol, "entry_ts": holding.entry_ts,
                            "entry_price": entry_price, "quantity": quantity,
                            "initial_notional_usdt": quantity * entry_price,
                            "actual_exit_ts": end, "original_exit_ts": holding.exit_ts,
                            "exit_kind": "EARLY_EXIT" if is_early else "TERMINAL_ESTIMATE" if is_terminal else "MONTHLY_ROTATION",
                            "exit_price": end_price, "price_pnl_usdt": price_pnl,
                            "funding_pnl_usdt": cash, "observed_funding_events_booked": count,
                            "entry_boundary_fee_paid": float(trade["fee"]),
                            "entry_boundary_slippage_paid": float(trade["slippage"]),
                            "entry_cost_belongs_to_previous_month_except_initial": month != first_month,
                            "early_or_terminal_fee": direct_fee, "early_or_terminal_slippage": direct_slip,
                            "ending_boundary_same_symbol_fee": end_fee,
                            "ending_boundary_same_symbol_slippage": end_slip,
                            "monthly_attributed_fee": attributed_fee,
                            "monthly_attributed_slippage": attributed_slip,
                            "monthly_net_leg_pnl_before_new_name_overhead": price_pnl + cash - attributed_fee - attributed_slip})
    legs = pd.DataFrame(records)
    monthly = result["monthly"].copy().merge(pd.DataFrame(overhead), on="month", validate="one_to_one")
    grouped = legs.groupby("month", sort=True).agg(
        price_pnl_usdt=("price_pnl_usdt", "sum"), funding_pnl_usdt=("funding_pnl_usdt", "sum"),
        attributed_leg_fee=("monthly_attributed_fee", "sum"),
        attributed_leg_slippage=("monthly_attributed_slippage", "sum"),
        leg_net_before_overhead=("monthly_net_leg_pnl_before_new_name_overhead", "sum"),
        initial_gross_notional_usdt=("initial_notional_usdt", "sum"),
        early_exit_count=("exit_kind", lambda v: int(v.eq("EARLY_EXIT").sum())),
        holdings=("symbol", lambda v: ", ".join(s.split("/")[0] for s in v)))
    monthly = monthly.merge(grouped, on="month", validate="one_to_one")
    monthly["fee_usdt"] = monthly.attributed_leg_fee + monthly.next_month_new_names_fee
    monthly["slippage_usdt"] = monthly.attributed_leg_slippage + monthly.next_month_new_names_slippage
    monthly["pnl_usdt"] = monthly.account_end_equity - monthly.account_start_equity
    monthly["reconstructed_pnl_usdt"] = monthly.price_pnl_usdt + monthly.funding_pnl_usdt - monthly.fee_usdt - monthly.slippage_usdt
    monthly["cash_identity_error_usdt"] = monthly.reconstructed_pnl_usdt - monthly.pnl_usdt
    if not np.allclose(monthly.reconstructed_pnl_usdt, monthly.pnl_usdt, rtol=1e-10, atol=1e-6):
        raise ValueError("monthly actual-quantity leg cash bridge failed")
    for field, metric in (("price_pnl_usdt", "price_pnl_usdt"), ("funding_pnl_usdt", "funding_pnl_usdt"),
                          ("fee_usdt", "fees_usdt"), ("slippage_usdt", "slippage_usdt")):
        if not np.isclose(monthly[field].sum(), result["metrics"][metric], rtol=1e-10, atol=1e-6):
            raise ValueError(f"full-account ledger component mismatch: {field}")
    yearly = []
    for year, group in monthly.groupby(monthly.month.dt.year, sort=True):
        yearly.append({"year": int(year), "months": len(group), "first_month": group.month.min(),
                       "last_month": group.month.max(), "start_equity_usdt": float(group.account_start_equity.iloc[0]),
                       "end_equity_usdt": float(group.account_end_equity.iloc[-1]),
                       "account_return": float(group.account_end_equity.iloc[-1] / group.account_start_equity.iloc[0] - 1),
                       **{field: float(group[field].sum()) for field in
                          ("pnl_usdt", "price_pnl_usdt", "funding_pnl_usdt", "fee_usdt", "slippage_usdt")},
                       "early_exit_count": int(group.early_exit_count.sum()),
                       "winning_months": int(group.account_return.gt(0).sum()),
                       "worst_month_return": float(group.account_return.min()),
                       "best_month_return": float(group.account_return.max())})
    return legs, monthly, pd.DataFrame(yearly)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    if sha(args.contract) != args.contract_sha256:
        raise ValueError("round contract mismatch")
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    prices, original_exits, reports, prior_summary = load_prior_round()
    holdings, execution, daily, funding, terminals, input_started = load_frozen_inputs()
    save(args.output / "started.json", {"contract_path": str(args.contract), "contract_sha256": args.contract_sha256,
                                        "script_sha256": sha(Path(__file__)), "prior_completion_sha256": sha(COMPLETION),
                                        "prior_single_exit_summary_sha256": sha(OLD / "summary.json"),
                                        "original_inputs": input_started, "no_parameter_search": True,
                                        "unseen_oos": False, "native_funding_not_verified_net": True})
    features = daily_features(daily, set(holdings.symbol))
    plans = {}
    for rule in RULES:
        plan, decisions = broaden_exit_plan(holdings, original_exits, features, rule)
        plans[rule] = plan
        plan.to_parquet(args.output / f"{rule}-exit-plan.parquet", index=False)
        plan.to_csv(args.output / f"{rule}-exit-plan.csv", index=False)
        save(args.output / f"{rule}-first-trigger-decisions.json", decisions)
    union = pd.concat(list(plans.values()), ignore_index=True).drop_duplicates(["symbol", "exit_ts"])
    proofs, requests = extra_activity_requests(union, prices, reports)
    proofs.to_parquet(args.output / "prior-activity-proof-plan.parquet", index=False)
    for plan in requests:
        save(args.output / "activity-requests" / f"{plan['label']}.json", plan["request"])
    save(args.output / "all-plans-frozen.json", {
        "status": "SIGNALS_AND_ACTIVITY_REQUESTS_FROZEN_BEFORE_NEW_EXECUTION_READ_OR_ACCOUNT_RETURNS",
        "plans": requests, "target_counts": {r: len(p) for r, p in plans.items()},
        "unique_targets": len(union), "proof_status_counts": proofs.prior_activity_evidence.value_counts().to_dict(),
        "frozen_files_sha256": {str(p.relative_to(args.output)): sha(p) for p in sorted(args.output.rglob("*")) if p.is_file()},
    })
    print(f"BREADTH_PLANS_FROZEN counts={ {r: len(p) for r,p in plans.items()} } prior_requests={len(requests)}", flush=True)
    activity = load_additional_prior_activity(requests, prices, args.output)
    activity.to_parquet(args.output / "additional-prior-activity.parquet", index=False)
    save(args.output / "execution-ready.json", {"all_plans_frozen_sha256": sha(args.output / "all-plans-frozen.json"),
                                                "new_activity_rows": len(activity),
                                                "all_ordinary_exit_prior_activity_verified": True,
                                                "old_common_grid_prices_sha256": sha(OLD / "execution-prices.parquet"),
                                                "new_price_rows_replace_old": False})
    reproductions = []
    for scenario in SCENARIOS:
        print(f"REPRODUCE_ORIGINAL_SINGLE_EXIT {scenario} 4bp", flush=True)
        reproduced = replay_exit(holdings, execution, daily, funding, terminals, original_exits, prices, scenario, .0004)
        expected = json.loads((OLD / f"{scenario}-single_exit-4bp/summary.json").read_text())
        fields = ("final_equity", "total_return", "max_drawdown_daily_and_rebalance", "funding_pnl_usdt", "fees_usdt", "slippage_usdt")
        errors = {f: float(reproduced["metrics"][f] - expected[f]) for f in fields}
        if not all(np.isclose(reproduced["metrics"][f], expected[f], rtol=1e-10, atol=1e-6) for f in fields):
            raise ValueError("original single-exit reproduction failed")
        reproductions.append({"scenario": scenario, "matches": True, "errors": errors})
    save(args.output / "original-single-exit-reproduction.json", reproductions)
    metrics, explanations, bridge_checks = [], [], []
    for scenario in SCENARIOS:
        for slip in (.0004, .0008):
            bp = int(slip * 10000)
            old_dir = OLD / f"{scenario}-baseline-{bp}bp"
            baseline = {"trades": pd.read_parquet(old_dir / "trades.parquet"),
                        "metrics": json.loads((old_dir / "summary.json").read_text())}
            for rule in RULES:
                print(f"REPLAY_BREADTH {scenario} {rule} {bp}bp", flush=True)
                result = replay_exit(holdings, execution, daily, funding, terminals, plans[rule], prices, scenario, slip)
                result["metrics"].update(strategy=rule, status="HISTORICAL_FIXED_BREADTH_EXIT_DIAGNOSTIC_NOT_VERIFIED_NET")
                directory = args.output / f"{scenario}-{rule}-{bp}bp"
                directory.mkdir()
                for key in ("nav", "trades", "terminals", "early-exits"):
                    result[key].to_parquet(directory / f"{key}.parquet", index=False)
                legs, monthly, yearly = monthly_leg_cash_bridge(holdings, execution, funding, terminals, plans[rule], prices, result, scenario)
                for key, frame in (("holding-legs", legs), ("monthly", monthly), ("yearly", yearly)):
                    frame.to_parquet(directory / f"{key}.parquet", index=False)
                    frame.to_csv(directory / f"{key}.csv", index=False)
                save(directory / "summary.json", result["metrics"])
                normalized, explanation = leg_diagnostics(holdings, execution, funding, terminals, plans[rule], prices,
                                                          baseline, result, scenario, slip)
                normalized.to_parquet(directory / "normalized-leg-bridge.parquet", index=False)
                explanation.update(scenario=scenario, slippage_rate=slip, strategy=rule)
                explanations.append(explanation)
                checks = {"scenario": scenario, "strategy": rule, "slippage_rate": slip,
                          "holding_legs": len(legs), "months": len(monthly), "years": len(yearly),
                          "max_monthly_cash_identity_error_usdt": float(monthly.cash_identity_error_usdt.abs().max()),
                          "early_exit_count_distribution": monthly.early_exit_count.value_counts().sort_index().to_dict(),
                          "full_account_cash_identity_error_usdt": float(INITIAL + monthly.pnl_usdt.sum() - result["metrics"]["final_equity"])}
                bridge_checks.append(checks)
                metrics.append(result["metrics"])
                print(json.dumps({"scenario": scenario, "rule": rule, "slip": slip,
                                  "return": result["metrics"]["total_return"], "final": result["metrics"]["final_equity"]}), flush=True)
    save(args.output / "summary.json", {"status": "EIGHT_FIXED_BREADTH_EXIT_ACCOUNTS_COMPLETE_NOT_LIVE_READY",
                                        "results": metrics, "leg_explanations": explanations,
                                        "account_bridge_checks": bridge_checks,
                                        "prior_comparator_results": prior_summary["results"],
                                        "original_single_exit_reproductions": reproductions,
                                        "no_new_entry_or_ranking_rules": True,
                                        "old_common_exit_timestamps": int(prices.ts.nunique()),
                                        "all_nav_accounts_use_same_common_grid": True,
                                        "source_sha256": {str(p.relative_to(args.output)): sha(p)
                                                          for p in sorted(args.output.rglob("*")) if p.is_file()}})
    size = sum(p.stat().st_size for p in args.output.rglob("*") if p.is_file())
    if size > 15 * 1024 ** 2:
        raise ValueError("broader-exit local artifact budget exceeded")
    print(f"BREADTH_COMPLETE accounts={len(metrics)} bytes={size}", flush=True)


if __name__ == "__main__":
    main()
