"""Event-clock adapter for one frozen MA120 rule. Baseline sources remain unchanged."""
from __future__ import annotations

import pandas as pd

from mcsm_ma120_accounting_20260911 import PartialCashAccount
from research_mcsm_single_asset_exit_20260910 import (
    AccountingError, DAY, END, INITIAL, SCENARIOS, START, choose_funding_mark,
    clip_funding, compact_row, finite_positive, performance, validate_holdings, voluntary_close,
)


def replay_ma(holdings, execution, daily_prices, funding, terminals, exits, exit_prices, scenario, slippage=.0004, admitted=None):
    """Complete self-financed path; only single-name exit events differ from baseline."""
    if scenario not in SCENARIOS:
        raise ValueError("not a frozen scenario")
    h = validate_holdings(holdings, terminals)
    admitted = set(zip(h.month, h.symbol)) if admitted is None else admitted
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
    targets = {month + pd.Timedelta(minutes=15): group.loc[[(month, s) in admitted for s in group.symbol]].set_index("symbol").weight.to_dict()
               for month, group in h.groupby("month")}
    targets[END] = {}
    cash_slots = h.loc[[(m, s) not in admitted for m, s in zip(h.month, h.symbol)], ["month", "symbol", "entry_ts"]].rename(columns={"entry_ts": "exit_ts"})
    cutoffs = pd.concat([exits[["month", "symbol", "exit_ts"]], cash_slots], ignore_index=True)
    booked, omitted = clip_funding(h, funding, cutoffs)
    events = [(ts, 5, "rebalance", target) for ts, target in targets.items()]
    events += [(ts, 0, "daily", None) for ts in pd.date_range(START.floor("D") + DAY, END.floor("D"), freq="D", tz="UTC")]
    events += [(row["exit_ts"], 4, "voluntary_exit", row) for row in exits.to_dict("records")]
    events += [(ts, 3, "exit_boundary_mark", None) for ts in sorted(exit_prices.ts.unique())]
    events += [(row["ts"], 2, "terminal", row) for row in terminals if START < row["ts"] <= END]
    if scenario != "price_only":
        events += [(row["ts"], 1, "funding", row) for row in booked.to_dict("records")]
    events.sort(key=lambda item: (item[0], item[1], str((item[3] or {}).get("symbol", ""))))
    account = PartialCashAccount(INITIAL, slippage_rate=slippage)
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
    metrics.update(scenario=scenario, status="HISTORICAL_MA120_DIAGNOSTIC_NOT_VERIFIED_NET",
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

