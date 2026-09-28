"""One frozen single-name exit ablation; observed funding is not verified net.

The unmodified September 9 inputs and account kernel remain immutable. All
additional execution prices come from require_research_startup returned frames.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_lab.data.research_bundle import require_research_startup
from mcsm_baseline_accounting_20260908 import AccountingError, LinearPerpAccount
from run_mcsm_baseline_estimate_20260909 import (
    END, INITIAL, KERNEL_SHA, START, choose_funding_mark, compact_row,
    finite_positive, load_terminals, performance, validate_holdings,
)
from verify_mcsm_baseline_20260908 import load_verified_returned_daily

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
BASE = FAMILY / "artifacts/baseline-estimate-20260909"
OUT = FAMILY / "artifacts/mechanism-round-20260910/single-exit"
DAY = pd.Timedelta(days=1)
SCENARIOS = ("price_only", "estimated_center")
NATIVE = FAMILY / "artifacts/funding-recheck-20260910/native-replay"
NATIVE_SHA = "fc57b942e14ab29007256326404c698f379d24988a0da274fe4434b0d9c70990"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        handle.write("\n")


def daily_features(daily, symbols):
    """Complete contiguous 21-close and 8-close windows; never fill missing bars."""
    selected = daily.loc[daily.symbol.isin(symbols)].copy()
    selected["ts"] = pd.to_datetime(selected.ts, utc=True)
    if selected.duplicated(["symbol", "ts"]).any():
        raise ValueError("duplicate daily feature row")
    parts = []
    for symbol, group in selected.groupby("symbol", sort=True):
        group = group.sort_values("ts").reset_index(drop=True)
        valid = group.eligible.eq(True) & np.isfinite(group.close) & group.close.gt(0)
        segment_run = group.research_segment_id.ne(group.research_segment_id.shift()).fillna(True).astype("int64").cumsum()
        for length in (8, 21):
            contiguous = group.ts.sub(group.ts.shift(length - 1)).eq((length - 1) * DAY)
            same_segment = segment_run.eq(segment_run.shift(length - 1))
            group[f"valid_{length}"] = contiguous & same_segment & valid.rolling(length).sum().eq(length)
        group["previous_20_low"] = group.close.shift(1).rolling(20, min_periods=20).min().where(group.valid_21)
        group["return_7d"] = group.close.div(group.close.shift(7)).sub(1).where(group.valid_8)
        parts.append(group[["symbol", "ts", "close", "previous_20_low", "return_7d", "valid_21", "valid_8"]])
    if not parts:
        raise ValueError("no daily feature frames")
    return pd.concat(parts, ignore_index=True).set_index(["symbol", "ts"]).sort_index()


def make_exit_signals(holdings, features):
    """20-close breakdown AND relative weakness, confirmed two held UTC days.

    All nine fixed month-start peers must have eligible seven-day returns. An
    unknown own/peer feature is retained as unknown and resets confirmation.
    No rule is evaluated before the month begins or after the first exit.
    """
    signals, exits = [], []
    for month, basket in holdings.groupby("month", sort=True):
        names = basket.symbol.tolist()
        if len(names) != 10 or len(set(names)) != 10:
            raise ValueError("fixed ten-name peer denominator required")
        for holding in basket.itertuples(index=False):
            streak = 0
            end_day = (holding.exit_ts - pd.Timedelta(minutes=15)).floor("D")
            for day in pd.date_range(month, end_day - DAY, freq="D", tz="UTC"):
                decision_ts = day + DAY
                execution_ts = decision_ts + pd.Timedelta(minutes=15)
                if execution_ts >= holding.exit_ts:
                    break
                own_key = (holding.symbol, day)
                own = features.loc[own_key] if own_key in features.index else None
                peer_returns = [float(features.loc[(s, day), "return_7d"])
                                for s in names if s != holding.symbol and (s, day) in features.index
                                and np.isfinite(features.loc[(s, day), "return_7d"])]
                own_valid = own is not None and bool(own.valid_21) and np.isfinite(own.return_7d)
                valid = own_valid and len(peer_returns) == 9
                peer_median = float(np.median(peer_returns)) if len(peer_returns) == 9 else np.nan
                condition = bool(valid and own.close < own.previous_20_low and own.return_7d < peer_median)
                streak = streak + 1 if condition else 0
                row = {"month": month, "symbol": holding.symbol, "day": day,
                       "decision_ts": decision_ts, "candidate_execution_ts": execution_ts,
                       "own_feature_valid": own_valid, "peer_valid_count": len(peer_returns),
                       "feature_status": "KNOWN" if valid else "UNKNOWN_RESET_CONFIRMATION",
                       "close": float(own.close) if own is not None else np.nan,
                       "previous_20_low": float(own.previous_20_low) if own is not None else np.nan,
                       "return_7d": float(own.return_7d) if own is not None else np.nan,
                       "peer_median_return_7d": peer_median, "condition": condition,
                       "confirmation_days": streak, "triggered": streak >= 2}
                signals.append(row)
                if streak >= 2:
                    exits.append({"month": month, "symbol": holding.symbol,
                                  "signal_day": day, "decision_ts": decision_ts,
                                  "exit_ts": execution_ts, "original_exit_ts": holding.exit_ts})
                    break
    columns = ["month", "symbol", "signal_day", "decision_ts", "exit_ts", "original_exit_ts"]
    return pd.DataFrame(signals), pd.DataFrame(exits, columns=columns)


def execution_requests(exits, template, holdings):
    """Freeze all requests before observing any additional execution price."""
    plans = []
    if exits.empty:
        return plans
    required = []
    exit_keys = set(zip(exits.symbol, exits.exit_ts))
    for ts in sorted(exits.exit_ts.unique()):
        held = holdings.loc[holdings.entry_ts.lt(ts) & holdings.exit_ts.ge(ts)]
        for holding in held.itertuples(index=False):
            required.append({"symbol": holding.symbol, "exit_ts": ts,
                             "ordinary_exit_required": (holding.symbol, ts) in exit_keys})
    needs = pd.DataFrame(required, columns=["symbol", "exit_ts", "ordinary_exit_required"])
    for year, group in needs.groupby(needs.exit_ts.dt.year, sort=True):
        names = sorted(group.symbol.unique())
        for offset in range(0, len(names), 32):
            batch = group.loc[group.symbol.isin(names[offset:offset + 32])]
            request = {key: template[key] for key in ("schema_version", "bundle_id", "bundle_path", "bundle_sha256")}
            request.update(mode="price_diagnostic", timeframe="15m", symbols=names[offset:offset + 32],
                           start=(batch.exit_ts.min() - pd.Timedelta(minutes=15)).isoformat(),
                           end=(batch.exit_ts.max() + pd.Timedelta(minutes=15)).isoformat(),
                           gap_policy="contiguous_segments", asset_policy="observed_mixed_diagnostic",
                           backward_bars=1, forward_bars=0)
            plans.append({"label": f"{year}-{offset:03d}", "request": request,
                          "required": batch.to_dict("records")})
    return plans


def load_exit_execution(plans, output):
    """Consume only actual startup-returned frames; no second raw lake read."""
    rows, receipts = [], []
    for plan in plans:
        label, request = plan["label"], plan["request"]
        request_path = output / "execution-requests" / f"{label}.json"
        if not request_path.exists() or json.loads(request_path.read_text()) != request:
            raise ValueError("execution request was not frozen before price lookup")
        start = time.monotonic()
        print(f"EXIT_EXECUTION_STARTUP {label} symbols={len(request['symbols'])}", flush=True)
        returned = require_research_startup(request, project_root=ROOT)
        if returned.report["status"] != "PRICE_DIAGNOSTIC_INPUTS_VERIFIED":
            raise ValueError("wrong exit execution startup status")
        report_path = output / "execution-reports" / f"{label}.json"
        save(report_path, returned.report)
        for need in plan["required"]:
            symbol, ts = need["symbol"], pd.Timestamp(need["exit_ts"])
            frame = returned.prices[symbol]
            selected = frame.loc[frame.ts.eq(ts)]
            if len(selected) != 1:
                raise ValueError(f"boundary has no returned open: {symbol} {ts}")
            prior = frame.loc[frame.ts.eq(ts - pd.Timedelta(minutes=15))]
            if need["ordinary_exit_required"] and (len(prior) != 1 or not bool(prior.eligible.iloc[0])
                                                   or not bool(prior.research_window_valid.iloc[0])):
                raise ValueError(f"exit lacks prior closed active bar: {symbol} {ts}")
            bar = selected.iloc[0]
            rows.append({"symbol": symbol, "ts": ts, "price": finite_positive(float(bar.open), "exit open"),
                         "reference": "NEXT_DAY_0015_15M_OPEN", "ordinary_exit_required": need["ordinary_exit_required"],
                         "current_bar_future_activity_not_used": True,
                         "request_path": str(request_path.relative_to(ROOT)),
                         "request_sha256": sha(request_path), "report_path": str(report_path.relative_to(ROOT)),
                         "report_sha256": sha(report_path)})
        receipts.append({"year": label, "request_sha256": sha(request_path), "report_sha256": sha(report_path),
                         "returned_rows": sum(len(frame) for frame in returned.prices.values()),
                         "required_exit_prices": len(plan["required"]), "elapsed_seconds": time.monotonic() - start})
        del returned
        print(f"EXIT_EXECUTION_READY {label} n={len(plan['required'])}", flush=True)
    columns = ["symbol", "ts", "price", "reference", "ordinary_exit_required", "current_bar_future_activity_not_used",
               "request_path", "request_sha256", "report_path", "report_sha256"]
    return pd.DataFrame(rows, columns=columns), receipts


def voluntary_close(account, ts, symbol, price, evidence):
    """Reuse immutable atomic close math, with ordinary sell cost, not settlement cost.

    The kernel method is named terminal_close; the new ledger explicitly calls
    these ordinary voluntary exits. No other position is resized or remarked.
    """
    return account.terminal_close(ts, symbol, price, evidence, settlement_fee_rate=account.fee_rate,
                                  settlement_slippage_rate=account.slippage_rate)


def clip_funding(holdings, funding, exits):
    """Keep (entry, actual exit], documenting every intentionally omitted event."""
    remaining = funding.copy()
    remaining["ts"] = pd.to_datetime(remaining.ts, utc=True)
    if remaining.duplicated(["ts", "symbol", "rate_type"]).any():
        raise ValueError("duplicate funding source identity")
    assigned = np.zeros(len(remaining), dtype=np.int8)
    included = np.zeros(len(remaining), dtype=bool)
    early = exits.set_index(["month", "symbol"]).exit_ts.to_dict() if len(exits) else {}
    for holding in holdings.itertuples(index=False):
        original = remaining.symbol.eq(holding.symbol) & remaining.ts.gt(holding.entry_ts) & remaining.ts.le(holding.exit_ts)
        assigned += original.to_numpy(np.int8)
        cutoff = early.get((holding.month, holding.symbol), holding.exit_ts)
        included |= (original & remaining.ts.le(cutoff)).to_numpy()
    if not (assigned == 1).all():
        raise ValueError("funding event not assigned exactly once to original frozen holding")
    remaining["actual_position_booked"] = included
    return remaining.loc[included].copy(), remaining.loc[~included].copy()


def replay_exit(holdings, execution, daily_prices, funding, terminals, exits, exit_prices, scenario, slippage=.0004):
    """Complete self-financed path; only single-name exit events differ from baseline."""
    if scenario not in SCENARIOS:
        raise ValueError("not a frozen scenario")
    h = validate_holdings(holdings, terminals)
    execution = execution.copy()
    execution["ts"] = pd.to_datetime(execution.ts, utc=True)
    if execution.duplicated(["ts", "symbol"]).any() or exit_prices.duplicated(["ts", "symbol"]).any():
        raise ValueError("duplicate execution observation")
    monthly_prices = {ts: group.set_index("symbol").price.to_dict() for ts, group in execution.groupby("ts")}
    exit_map = exit_prices.set_index(["ts", "symbol"]).price.to_dict()
    for row in exits.itertuples(index=False):
        if (row.exit_ts, row.symbol) not in exit_map:
            raise ValueError("missing requested early exit price")
    daily_prices = daily_prices.copy()
    daily_prices["ts"] = pd.to_datetime(daily_prices.ts, utc=True)
    daily_prices = daily_prices.set_index(["ts", "symbol"]).sort_index()
    targets = {month + pd.Timedelta(minutes=15): group.set_index("symbol").weight.to_dict()
               for month, group in h.groupby("month")}
    targets[END] = {}
    booked, omitted = clip_funding(h, funding, exits)
    events = [(ts, 5, "rebalance", target) for ts, target in targets.items()]
    events += [(ts, 0, "daily", None) for ts in pd.date_range(START.floor("D") + DAY, END.floor("D"), freq="D", tz="UTC")]
    events += [(row["exit_ts"], 4, "voluntary_exit", row) for row in exits.to_dict("records")]
    events += [(ts, 3, "exit_boundary_mark", None) for ts in sorted(exit_prices.ts.unique())]
    events += [(row["ts"], 2, "terminal", row) for row in terminals if START < row["ts"] <= END]
    if scenario != "price_only":
        events += [(row["ts"], 1, "funding", row) for row in booked.to_dict("records")]
    events.sort(key=lambda item: (item[0], item[1], str((item[3] or {}).get("symbol", ""))))
    account = LinearPerpAccount(INITIAL, slippage_rate=slippage)
    daily_rows, nav_rows, fund_rows, terminal_rows, trades, months, exit_rows = [], [], [], [], [], [], []
    previous_equity, previous_month = INITIAL, None
    for ts, _, kind, payload in events:
        if kind == "rebalance":
            required = set(account.positions) | set(payload)
            marks = {s: p for s, p in monthly_prices.get(ts, {}).items() if s in required}
            row = account.rebalance(ts, payload, marks)
            trades += [{"ts": ts, "kind": "monthly_rebalance", **trade} for trade in row["details"]["trades"]]
            if previous_month is not None:
                months.append({"month": previous_month, "account_start_equity": previous_equity,
                               "account_end_equity": row["equity"], "account_return": row["equity"] / previous_equity - 1})
            previous_equity = INITIAL if ts == START else row["equity"]
            previous_month = ts.floor("D")
        elif kind == "daily":
            marks = {}
            for symbol in account.positions:
                if (ts - DAY, symbol) not in daily_prices.index:
                    raise AccountingError(f"missing daily mark {symbol} {ts - DAY}")
                source = daily_prices.loc[(ts - DAY, symbol)]
                if not bool(source.eligible):
                    raise AccountingError(f"ineligible daily mark {symbol} {ts - DAY}")
                marks[symbol] = finite_positive(float(source.close), "daily mark")
            row = account.mark(ts, marks)
            daily_rows.append({"ts": ts, **compact_row(row), "held_slots": len(account.positions)})
        elif kind == "exit_boundary_mark":
            marks = {symbol: exit_map[(ts, symbol)] for symbol in account.positions}
            row = account.mark(ts, marks)
        elif kind == "funding":
            mark = choose_funding_mark(payload, scenario)
            row = account.funding(ts, payload["symbol"], float(payload["funding_rate"]), mark,
                                  rate_type=payload["rate_type"])
            fund_rows.append({"ts": ts, "symbol": payload["symbol"], "rate_type": payload["rate_type"],
                              "quantity": row["details"]["quantity"], "funding_cash": row["event_funding_pnl"]})
        elif kind == "voluntary_exit":
            symbol = payload["symbol"]
            if symbol not in account.positions:
                raise AccountingError("scheduled early exit without actual held position")
            row = voluntary_close(account, ts, symbol, exit_map[(ts, symbol)],
                                  "GOVERNED_RETURNED_NEXT_DAY_0015_OPEN:execution-prices.parquet")
            exit_rows.append({"ts": ts, "month": payload["month"], "kind": kind, **row["details"],
                              "account_equity_mixed_marks": row["equity"], "not_synchronous_nav": True})
        else:
            if payload["symbol"] not in account.positions:
                continue
            row = account.terminal_close(ts, payload["symbol"], payload["center"],
                                         f"ESTIMATED:{payload['source_path']} sha256={payload['source_sha256']}",
                                         settlement_fee_rate=.001, settlement_slippage_rate=0)
            terminal_rows.append({"ts": ts, **row["details"], "source_quality": payload["source_quality"]})
        if kind in ("daily", "rebalance", "exit_boundary_mark", "voluntary_exit"):
            nav_rows.append({"ts": ts, "sample_kind": kind, **compact_row(row),
                             "gross_to_equity": row["gross_notional"] / row["equity"]})
        account.ledger[-1] = compact_row(account.ledger[-1])
    if account.positions or len(months) != 76:
        raise AccountingError("incomplete single-exit account")
    if scenario != "price_only" and len(fund_rows) != len(booked):
        raise AccountingError("booked funding count mismatch")
    nav, daily, monthly = pd.DataFrame(nav_rows), pd.DataFrame(daily_rows), pd.DataFrame(months)
    metrics = performance(nav, daily, monthly, account.snapshot())
    metrics.update(scenario=scenario, status="HISTORICAL_SINGLE_RULE_DIAGNOSTIC_NOT_VERIFIED_NET",
                   early_exit_count=len(exit_rows), original_observed_funding_events=len(funding),
                   observed_events_inside_actual_position=len(booked), observed_events_after_early_exit=len(omitted),
                   funding_events_booked=len(fund_rows), terminal_events=len(terminal_rows),
                   full_account_closed=True, calendar_verified=False, pit_verified=False,
                   margin_liquidation_simulated=False, slippage_rate=slippage,
                   max_drawdown_sampling="daily, monthly and all common candidate-exit 0015 opens; post-exit costs included",
                   mean_daily_gross_to_equity=float(daily.gross_notional.div(daily.equity).mean()),
                   mean_daily_held_slots=float(daily.held_slots.mean()))
    return {"metrics": metrics, "nav": nav, "daily": daily, "monthly": monthly,
            "trades": pd.DataFrame(trades), "funding": pd.DataFrame(fund_rows),
            "terminals": pd.DataFrame(terminal_rows), "early-exits": pd.DataFrame(exit_rows)}


def load_frozen_inputs():
    started = json.loads((BASE / "accounts/started.json").read_text())
    paths = {key: ROOT / path for key, path in started["paths"].items()}
    for key, path in paths.items():
        if sha(path) != started["sha256"][key]:
            raise ValueError(f"frozen baseline changed: {key}")
    if sha(Path(__file__).with_name("mcsm_baseline_accounting_20260908.py")) != KERNEL_SHA:
        raise ValueError("immutable account kernel changed")
    for key, digest in json.loads((BASE / "accounts/summary.json").read_text())["output_sha256"].items():
        if sha(BASE / "accounts" / key) != digest:
            raise ValueError(f"frozen baseline output changed: {key}")
    holdings = pd.read_parquet(paths["holdings"])
    for column in ("month", "entry_ts", "exit_ts"):
        holdings[column] = pd.to_datetime(holdings[column], utc=True)
    native_path = NATIVE / "native-priority-events.parquet"
    if sha(native_path) != NATIVE_SHA:
        raise ValueError("frozen native-priority funding input changed")
    started = {**started, "this_round_funding_path": str(native_path.relative_to(ROOT)), "this_round_funding_sha256": NATIVE_SHA}
    return holdings, pd.read_parquet(paths["execution"]), load_verified_returned_daily(), pd.read_parquet(native_path), load_terminals(), started


def leg_diagnostics(holdings, execution, funding, terminals, exits, exit_prices, baseline, candidate, scenario, slippage):
    """Normalize each fixed monthly leg to one entry-USDT; separate from account P&L."""
    prices = execution.set_index(["ts", "symbol"]).price.to_dict()
    terminal_prices = {(row["ts"], row["symbol"]): row["center"] for row in terminals}
    earlier = exits.set_index(["month", "symbol"]).exit_ts.to_dict() if len(exits) else {}
    early_prices = exit_prices.set_index(["ts", "symbol"]).price.to_dict()
    quantities = baseline["trades"].set_index(["ts", "symbol"]).new_quantity.to_dict()
    fund = funding.copy()
    fund["ts"] = pd.to_datetime(fund.ts, utc=True)
    rows = []
    for holding in holdings.itertuples(index=False):
        entry = prices[(holding.entry_ts, holding.symbol)]
        old_end = terminal_prices.get((holding.exit_ts, holding.symbol), prices.get((holding.exit_ts, holding.symbol)))
        if old_end is None:
            raise ValueError("original leg exit not available")
        early_ts = earlier.get((holding.month, holding.symbol), holding.exit_ts)
        new_end = early_prices[(early_ts, holding.symbol)] if early_ts < holding.exit_ts else old_end
        held_events = fund.loc[fund.symbol.eq(holding.symbol) & fund.ts.gt(holding.entry_ts) & fund.ts.le(holding.exit_ts)]
        cash = -held_events.mark_center * held_events.funding_rate / entry
        old_funding = float(cash.sum()) if scenario != "price_only" else 0.
        new_funding = float(cash.loc[held_events.ts.le(early_ts)].sum()) if scenario != "price_only" else 0.
        old_terminal = (holding.exit_ts, holding.symbol) in terminal_prices
        old_cost = .001 + slippage + (old_end / entry) * (.001 + (0 if old_terminal else slippage))
        new_cost = .001 + slippage + (new_end / entry) * (.001 + (0 if old_terminal and early_ts == holding.exit_ts else slippage))
        old_price, new_price = old_end / entry - 1, new_end / entry - 1
        old_net, new_net = old_price + old_funding - old_cost, new_price + new_funding - new_cost
        nominal = quantities[(holding.entry_ts, holding.symbol)] * entry
        rows.append({"month": holding.month, "symbol": holding.symbol, "early_exit": early_ts < holding.exit_ts,
                     "original_exit_ts": holding.exit_ts, "actual_exit_ts": early_ts, "entry_price": entry,
                     "original_exit_price": old_end, "actual_exit_price": new_end,
                     "original_price_return": old_price, "candidate_price_return": new_price,
                     "original_funding_per_entry_usdt": old_funding, "candidate_funding_per_entry_usdt": new_funding,
                     "original_roundtrip_cost_per_entry_usdt": old_cost, "candidate_roundtrip_cost_per_entry_usdt": new_cost,
                     "original_standalone_net_return": old_net, "candidate_standalone_net_return": new_net,
                     "net_return_difference": new_net - old_net,
                     "baseline_month_entry_nominal": nominal,
                     "fixed_baseline_quantity_price_pnl_change": nominal * (new_price - old_price),
                     "fixed_baseline_quantity_funding_change": nominal * (new_funding - old_funding),
                     "fixed_baseline_quantity_roundtrip_cost_change": nominal * (new_cost - old_cost)})
    frame = pd.DataFrame(rows)
    positive = frame.original_standalone_net_return.gt(0)
    top_count = max(1, int(np.ceil(len(frame) * .1)))
    winners = frame.loc[positive].sort_values(["original_standalone_net_return", "symbol", "month"], ascending=[False, True, True])
    top = winners.head(top_count)
    price_change = frame.fixed_baseline_quantity_price_pnl_change
    fund_change = frame.fixed_baseline_quantity_funding_change
    summary = {"normalization": "one entry USDT per month-leg, full roundtrip costs; not monthly net-turnover account PnL",
               "positive_original_legs": int(positive.sum()), "top_winner_count": len(top),
               "positive_legs_profit_retention": float(frame.loc[positive, "candidate_standalone_net_return"].sum()
                                                      / frame.loc[positive, "original_standalone_net_return"].sum()),
               "top_10pct_legs_profit_retention": float(top.candidate_standalone_net_return.sum() / top.original_standalone_net_return.sum()),
               "early_exit_improved_legs": int((frame.early_exit & frame.net_return_difference.gt(0)).sum()),
               "early_exit_worsened_legs": int((frame.early_exit & frame.net_return_difference.lt(0)).sum()),
               "fixed_baseline_q_avoided_price_loss_usdt": float(price_change.clip(lower=0).sum()),
               "fixed_baseline_q_foregone_price_gain_usdt": float(-price_change.clip(upper=0).sum()),
               "fixed_baseline_q_avoided_funding_payments_usdt": float(fund_change.clip(lower=0).sum()),
               "fixed_baseline_q_foregone_funding_income_usdt": float(-fund_change.clip(upper=0).sum()),
               "fixed_baseline_q_funding_change_usdt": float(fund_change.sum()),
               "actual_account_funding_change_usdt": candidate["metrics"]["funding_pnl_usdt"] - baseline["metrics"]["funding_pnl_usdt"],
               "actual_account_final_equity_change_usdt": candidate["metrics"]["final_equity"] - baseline["metrics"]["final_equity"],
               "direct_bridge_not_self_financing_third_strategy": True}
    return frame, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    if sha(args.contract) != args.contract_sha256:
        raise ValueError("frozen round contract mismatch")
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    holdings, execution, daily, funding, terminals, started = load_frozen_inputs()
    save(args.output / "started.json", {"contract_path": str(args.contract), "contract_sha256": args.contract_sha256,
                                        "script_sha256": sha(Path(__file__)), "original_inputs": started,
                                        "no_parameter_search": True, "unseen_oos": False})
    features = daily_features(daily, set(holdings.symbol))
    signals, exits = make_exit_signals(holdings, features)
    signals.to_parquet(args.output / "signal-days.parquet", index=False)
    exits.to_parquet(args.output / "exit-plan.parquet", index=False)
    exits.to_csv(args.output / "exit-plan.csv", index=False)
    template = json.loads((FAMILY / "artifacts/lifecycle-inputs-20260908/summary.json").read_text())["request"]
    plans = execution_requests(exits, template, holdings)
    for plan in plans:
        save(args.output / "execution-requests" / f"{plan['label']}.json", plan["request"])
    save(args.output / "execution-plan-frozen.json", {"plans": plans,
                                                     "signals_sha256": sha(args.output / "signal-days.parquet"),
                                                     "exits_sha256": sha(args.output / "exit-plan.parquet"),
                                                     "all_requests_frozen_before_new_execution_prices": True})
    print(f"EXIT_PLAN_FROZEN exits={len(exits)} signal_days={len(signals)}", flush=True)
    exit_prices, receipts = load_exit_execution(plans, args.output)
    exit_prices.to_parquet(args.output / "execution-prices.parquet", index=False)
    save(args.output / "execution-summary.json", {"receipts": receipts, "prices_sha256": sha(args.output / "execution-prices.parquet")})
    metrics, reproductions, explanations = [], [], []
    no_exits = exits.iloc[:0].copy()
    no_prices = exit_prices.iloc[:0].copy()
    for scenario in SCENARIOS:
        print(f"REPRODUCE_BASELINE {scenario}", flush=True)
        baseline = replay_exit(holdings, execution, daily, funding, terminals, no_exits, no_prices, scenario)
        expected = (json.loads((BASE / "accounts" / scenario / "summary.json").read_text()) if scenario == "price_only"
                    else json.loads((NATIVE / "summary.json").read_text())["metrics"])
        for field in ("final_equity", "total_return", "max_drawdown_daily_and_rebalance", "funding_pnl_usdt", "fees_usdt", "slippage_usdt"):
            if not np.isclose(baseline["metrics"][field], expected[field], rtol=1e-10, atol=1e-6):
                raise ValueError(f"baseline reproduction failed: {scenario} {field}")
        reproductions.append({"scenario": scenario, "final_equity": baseline["metrics"]["final_equity"], "matches": True})
        for slip in (.0004, .0008):
            print(f"COMMON_GRID_BASELINE {scenario} slip={slip}", flush=True)
            comparator = replay_exit(holdings, execution, daily, funding, terminals, no_exits, exit_prices, scenario, slip)
            print(f"REPLAY_SINGLE_EXIT {scenario} slip={slip}", flush=True)
            candidate = replay_exit(holdings, execution, daily, funding, terminals, exits, exit_prices, scenario, slip)
            for strategy, result in (("baseline", comparator), ("single_exit", candidate)):
                directory = args.output / f"{scenario}-{strategy}-{int(slip * 10000)}bp"
                directory.mkdir()
                result["metrics"]["strategy"] = strategy
                for key in ("nav", "monthly", "trades", "terminals", "early-exits"):
                    result[key].to_parquet(directory / f"{key}.parquet", index=False)
                result["monthly"].to_csv(directory / "monthly.csv", index=False)
                save(directory / "summary.json", result["metrics"])
                metrics.append(result["metrics"])
                print(json.dumps(result["metrics"], default=str), flush=True)
            legs, explanation = leg_diagnostics(holdings, execution, funding, terminals, exits, exit_prices,
                                                comparator, candidate, scenario, slip)
            legs.to_parquet(args.output / f"leg-bridge-{scenario}-{int(slip * 10000)}bp.parquet", index=False)
            explanation.update(scenario=scenario, slippage_rate=slip)
            explanations.append(explanation)
    save(args.output / "summary.json", {"status": "HISTORICAL_SINGLE_RULE_DIAGNOSTIC_NOT_VERIFIED_NET",
                                        "results": metrics, "baseline_reproductions": reproductions, "leg_explanations": explanations,
                                        "signal_days": len(signals), "unknown_signal_days": int(signals.feature_status.ne("KNOWN").sum()),
                                        "early_exits": len(exits), "unique_exit_symbols": int(exits.symbol.nunique()),
                                        "source_sha256": {str(path.relative_to(args.output)): sha(path)
                                                          for path in sorted(args.output.rglob("*")) if path.is_file()}})


if __name__ == "__main__":
    main()
