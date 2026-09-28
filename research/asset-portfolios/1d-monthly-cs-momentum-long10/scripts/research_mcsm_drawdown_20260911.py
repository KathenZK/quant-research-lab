"""Cash-first drawdown attribution of frozen Top10 accounts; no trading claim.

Full-day rolling-beta attribution is a statistical description, not a causal
decomposition or executable hedge. Boundary price cash stays explicitly separate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research_mcsm_single_asset_exit_20260910 import load_frozen_inputs

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
OLD = FAMILY / "artifacts/mechanism-round-20260910/single-exit"
OUT = FAMILY / "artifacts/drawdown-frequency-round-20260911/drawdown"
BUNDLE = ROOT / "research/platform/data-lake-governance/specs/binance-v3-research-input-bundle-v2.json"
BUNDLE_SHA = "d2a729d03be71d67aa9c5522fb242bbf010b6c64400233c27d9cb2406f567008"
DAY = pd.Timedelta(days=1)
MIN15 = pd.Timedelta(minutes=15)
INITIAL = 100000.


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        handle.write("\n")


def complete_returns(frame):
    """Observed valid, immediately adjacent closes in the same identity segment."""
    p = frame.sort_values("ts").copy()
    valid = p.eligible.fillna(False).astype(bool) & np.isfinite(p.close) & p.close.gt(0)
    consecutive = p.ts.diff().eq(DAY) & p.research_segment_id.eq(p.research_segment_id.shift())
    p["daily_return"] = p.close.div(p.close.shift()).sub(1).where(valid & valid.shift(fill_value=False) & consecutive)
    p["valid_close"] = valid
    return p


def market_features(daily, classes):
    """Only prior-closed eligibility; any missing selected label invalidates day."""
    pieces = [complete_returns(g) for _, g in daily.groupby("symbol", sort=True)]
    p = pd.concat(pieces, ignore_index=True)
    benchmark = p.loc[p.symbol.isin(["BTC/USDT:USDT", "ETH/USDT:USDT"])].pivot(index="ts", columns="symbol", values="daily_return")
    benchmark.columns = ["btc_return" if x.startswith("BTC/") else "eth_return" for x in benchmark.columns]
    benchmark["market_factor"] = benchmark[["btc_return", "eth_return"]].mean(axis=1, skipna=False)
    pool_parts = []
    for symbol, g in p.groupby("symbol", sort=True):
        if classes.get(symbol) != "COIN":
            continue
        g = g.sort_values("ts").copy()
        runs = (g.research_segment_id.ne(g.research_segment_id.shift()) | g.ts.diff().ne(DAY)).fillna(True).astype("int64").cumsum()
        contiguous = g.ts.sub(g.ts.shift(30)).eq(30 * DAY) & runs.eq(runs.shift(30))
        prior_ready = contiguous & g.valid_close.rolling(31, min_periods=31).sum().eq(31)
        adv = g.quote_volume.rolling(30, min_periods=30).mean()
        # Move the prior selection to the next *calendar* date, then left-join
        # the label. Shifting row positions would silently drop a coin whose
        # entire target bar is absent, and could reuse a pre-gap membership.
        chosen = g[["ts", "symbol"]].copy()
        chosen["ts"] = chosen.ts + DAY
        chosen["prior_pool_eligible"] = (prior_ready & adv.ge(1e7)).to_numpy()
        chosen = chosen.merge(g[["ts", "symbol", "daily_return"]], on=["ts", "symbol"], how="left", validate="one_to_one")
        pool_parts.append(chosen)
    all_pool = pd.concat(pool_parts, ignore_index=True)
    selected = all_pool.loc[all_pool.prior_pool_eligible]
    broad = selected.groupby("ts").daily_return.agg(pool_count="size", valid_count="count", broad_return="mean")
    broad["broad_return"] = broad.broad_return.where(broad.valid_count.eq(broad.pool_count) & broad.pool_count.ge(5))
    market = benchmark.join(broad, how="outer").sort_index()
    betas = []
    for symbol, g in p.groupby("symbol", sort=True):
        g = g.sort_values("ts").copy().set_index("ts")
        g["market_factor"] = market.market_factor.reindex(g.index)
        # Segment changes or calendar holes reset history, including unavailable
        # price spans. The 60-bar rolling window never reaches an earlier run.
        runs = (g.research_segment_id.ne(g.research_segment_id.shift()) | g.index.to_series().diff().ne(DAY)).fillna(True).astype("int64").cumsum()
        for _, segment in g.groupby(runs, sort=False):
            y, x = segment.daily_return, segment.market_factor
            pair = np.isfinite(y) & np.isfinite(x)
            xx, yy = x.where(pair), y.where(pair)
            count = pair.rolling(60, min_periods=1).sum().shift(1)
            beta = yy.rolling(60, min_periods=45).cov(xx).div(xx.rolling(60, min_periods=45).var()).shift(1)
            beta = beta.where(count.ge(45) & np.isfinite(beta))
            b = segment[["symbol", "close", "daily_return", "market_factor"]].copy()
            b["previous_close"] = segment.close.shift(1)
            b["beta_asof_previous_closed_day"] = beta
            b["beta_prior_observations"] = count
            betas.append(b.reset_index())
    return market, pd.concat(betas, ignore_index=True), all_pool


def drawdown_episode(nav):
    """Use the existing ordered pre/post-event NAV rows, not a resampled series."""
    nav = nav.sort_values(["ts", "event_id"], kind="stable").reset_index(drop=True)
    eq = nav.equity.to_numpy(float)
    peak = np.maximum.accumulate(np.r_[INITIAL, eq])[1:]
    dd = eq / peak - 1
    trough_i = int(np.argmin(dd))
    prior = eq[:trough_i + 1]
    peak_i = int(np.argmax(prior))
    after = np.flatnonzero(eq[trough_i + 1:] >= eq[peak_i])
    recovery_i = trough_i + 1 + int(after[0]) if len(after) else None
    below = eq < peak
    spans, begin = [], None
    for i, underwater in enumerate(below):
        if underwater and begin is None:
            begin = max(0, i - 1)
        if begin is not None and (not underwater or i == len(eq) - 1):
            spans.append((nav.ts.iloc[i] - nav.ts.iloc[begin]).total_seconds() / 86400)
            begin = None
    return nav, {"peak_index": peak_i, "trough_index": trough_i, "recovery_index": recovery_i,
                 "peak_ts": nav.ts.iloc[peak_i], "trough_ts": nav.ts.iloc[trough_i],
                 "recovery_ts": nav.ts.iloc[recovery_i] if recovery_i is not None else None,
                 "peak_equity": float(eq[peak_i]), "trough_equity": float(eq[trough_i]),
                 "max_drawdown": float(dd[trough_i]),
                 "peak_to_trough_days": (nav.ts.iloc[trough_i] - nav.ts.iloc[peak_i]).total_seconds() / 86400,
                 "peak_to_recovery_or_end_days": (nav.ts.iloc[recovery_i if recovery_i is not None else -1] - nav.ts.iloc[peak_i]).total_seconds() / 86400,
                 "recovered_by_end": recovery_i is not None, "longest_underwater_days": max(spans, default=0.)}


def build_legs(holdings, trades, funding, terminals, exits, execution, extra, funded):
    qmap = trades.set_index(["ts", "symbol"]).new_quantity.to_dict()
    prices = execution.set_index(["ts", "symbol"]).price.to_dict()
    extra_prices = extra.set_index(["ts", "symbol"]).price.to_dict()
    terminal_map = {(x["ts"], x["symbol"]): x["center"] for x in terminals}
    exit_map = exits.set_index(["month", "symbol"]).exit_ts.to_dict() if len(exits) else {}
    fg = {s: g.sort_values("ts") for s, g in funding.groupby("symbol", sort=False)}
    out = []
    for h in holdings.itertuples(index=False):
        early = exit_map.get((h.month, h.symbol))
        actual_exit = early if early is not None else h.exit_ts
        terminal = early is None and bool(h.terminal)
        q = float(qmap[(h.entry_ts, h.symbol)])
        start_price = float(prices[(h.entry_ts, h.symbol)])
        end_price = (float(extra_prices[(actual_exit, h.symbol)]) if early is not None else
                     float(terminal_map[(actual_exit, h.symbol)]) if terminal else float(prices[(actual_exit, h.symbol)]))
        ev = fg.get(h.symbol, funding.iloc[:0])
        ev = ev.loc[ev.ts.gt(h.entry_ts) & ev.ts.le(actual_exit)]
        cash = float((-q * ev.mark_center * ev.funding_rate).sum()) if funded else 0.
        direct_fee = q * end_price * .001 if early is not None or terminal else 0.
        direct_slip = q * end_price * .0004 if early is not None else 0.
        out.append({"month": h.month, "symbol": h.symbol, "entry_ts": h.entry_ts,
                    "original_exit_ts": h.exit_ts, "actual_exit_ts": actual_exit,
                    "exit_reason": "early_exit" if early is not None else "conditional_terminal" if terminal else "monthly_boundary",
                    "initial_quantity": q, "entry_price": start_price, "exit_price": end_price,
                    "initial_notional": q * start_price, "price_pnl": q * (end_price - start_price),
                    "funding_pnl": cash, "observed_funding_events": len(ev) if funded else 0,
                    "direct_exit_fees": direct_fee, "direct_exit_slippage": direct_slip,
                    "net_before_separate_month_boundary_costs": q * (end_price - start_price) + cash - direct_fee - direct_slip,
                    "early_exit": early is not None})
    return pd.DataFrame(out)


def monthly_details(legs, trades, monthly):
    costs = trades[["ts", "symbol", "old_quantity", "new_quantity", "fee", "slippage"]].copy()
    costs["attributed_month"] = (costs.ts - MIN15).dt.tz_localize(None).dt.to_period("M").dt.to_timestamp().dt.tz_localize("UTC") - pd.offsets.MonthBegin(1)
    first = legs.month.min()
    costs.loc[costs.attributed_month.lt(first), "attributed_month"] = first
    membership = set(zip(legs.month, legs.symbol))
    costs["held_in_attributed_month"] = [(m, s) in membership for m, s in zip(costs.attributed_month, costs.symbol)]
    rows = []
    for m in monthly.itertuples(index=False):
        g = legs.loc[legs.month.eq(m.month)]
        c = costs.loc[costs.attributed_month.eq(m.month)]
        fee = float(g.direct_exit_fees.sum() + c.fee.sum())
        slip = float(g.direct_exit_slippage.sum() + c.slippage.sum())
        price, fund = float(g.price_pnl.sum()), float(g.funding_pnl.sum())
        pnl = m.account_end_equity - m.account_start_equity
        error = price + fund - fee - slip - pnl
        if abs(error) > 1e-5:
            raise ValueError(f"monthly cash does not reconcile {m.month}: {error}")
        previous = legs.loc[legs.month.eq(m.month - pd.offsets.MonthBegin(1))]
        early_previous = set(previous.loc[previous.early_exit, "symbol"])
        rows.append({"month": m.month, "holdings": g.symbol.tolist(), "holdings_text": ", ".join(s.split('/')[0] for s in g.symbol),
                     "start_equity": m.account_start_equity, "end_equity": m.account_end_equity,
                     "return": m.account_return, "pnl": pnl, "price_pnl": price, "funding_pnl": fund,
                     "fees": fee, "slippage": slip, "reconciliation_error": error,
                     "price_losing_coins": int(g.price_pnl.lt(0).sum()),
                     "direct_net_losing_coins": int(g.net_before_separate_month_boundary_costs.lt(0).sum()),
                     "early_exits": int(g.early_exit.sum()),
                     "same_coins_from_previous_month": len(set(g.symbol) & set(previous.symbol)),
                     "rebought_after_prior_month_early_exit": len(set(g.symbol) & early_previous),
                     "rebought_symbols": sorted(set(g.symbol) & early_previous)})
    return pd.DataFrame(rows), costs


def daily_attribution(legs, features):
    indexed = features.set_index(["symbol", "ts"])
    rows = []
    for leg in legs.itertuples(index=False):
        # Every retained interval starts at 00:00 strictly after 00:15 entry and
        # ends no later than actual exit. Partial first/last days stay outside.
        start_day = leg.entry_ts.floor("D") + DAY
        end_day = leg.actual_exit_ts.floor("D") - DAY
        for day in pd.date_range(start_day, end_day, freq="D", tz="UTC"):
            key = (leg.symbol, day)
            if key not in indexed.index:
                continue
            x = indexed.loc[key]
            valid_price = np.isfinite(x.daily_return) and np.isfinite(x.previous_close)
            valid_beta = valid_price and np.isfinite(x.beta_asof_previous_closed_day) and np.isfinite(x.market_factor)
            price = leg.initial_quantity * x.previous_close * x.daily_return if valid_price else np.nan
            market_cash = leg.initial_quantity * x.previous_close * x.beta_asof_previous_closed_day * x.market_factor if valid_beta else np.nan
            rows.append({"month": leg.month, "symbol": leg.symbol, "start_ts": day, "end_ts": day + DAY,
                         "price_pnl": price, "beta": x.beta_asof_previous_closed_day,
                         "beta_prior_observations": x.beta_prior_observations,
                         "market_factor": x.market_factor, "market_related_price_pnl": market_cash,
                         "residual_price_pnl": price - market_cash if valid_beta else np.nan,
                         "beta_available": valid_beta, "price_available": valid_price})
    return pd.DataFrame(rows)


def market_window(market, start, end):
    # Benchmarks are explicitly adjacent complete UTC-day reference windows;
    # strategy 00:15 boundaries are not silently relabelled as 00:00 benchmarks.
    begin_day = start.ceil("D")
    last_end = end.floor("D")
    frame = market.loc[(market.index >= begin_day) & (market.index < last_end)]
    expected = pd.date_range(begin_day, last_end - DAY, freq="D", tz="UTC")
    result = {"reference_start_utc": begin_day, "reference_end_utc": last_end, "expected_days": len(expected)}
    for col in ["btc_return", "eth_return", "market_factor", "broad_return"]:
        s = frame[col].reindex(expected)
        count = int(s.notna().sum())
        result[col] = float((1 + s).prod() - 1) if count == len(expected) and count else None
        result[col + "_valid_days"] = count
    if len(frame):
        result["broad_min_pool"] = int(frame.pool_count.min()) if frame.pool_count.notna().any() else None
        result["broad_max_pool"] = int(frame.pool_count.max()) if frame.pool_count.notna().any() else None
    return result


def value_at(symbol, when, daily_map, execution_map, extra_map):
    if when == when.floor("D"):
        key = (when - DAY, symbol)
        return float(daily_map[key])
    key = (when, symbol)
    if key in execution_map:
        return float(execution_map[key])
    if key in extra_map:
        return float(extra_map[key])
    raise ValueError(f"no precise window valuation {symbol} {when}")


def window_leg_cash(legs, funding, start_row, end_row, daily_map, execution_map, extra_map, funded):
    start, end = start_row.ts, end_row.ts
    fg = {s: g for s, g in funding.groupby("symbol", sort=False)}
    rows = []
    for leg in legs.itertuples(index=False):
        a, b = max(start, leg.entry_ts), min(end, leg.actual_exit_ts)
        if b <= a:
            continue
        pa = leg.entry_price if a == leg.entry_ts else value_at(leg.symbol, a, daily_map, execution_map, extra_map)
        pb = leg.exit_price if b == leg.actual_exit_ts else value_at(leg.symbol, b, daily_map, execution_map, extra_map)
        ev = fg.get(leg.symbol, funding.iloc[:0])
        mask = ev.ts.gt(leg.entry_ts) & ev.ts.le(leg.actual_exit_ts)
        mask &= ev.ts.ge(start) if start_row.sample_kind == "daily" else ev.ts.gt(start)
        mask &= ev.ts.lt(end) if end_row.sample_kind == "daily" else ev.ts.le(end)
        cash = float((-leg.initial_quantity * ev.loc[mask, "mark_center"] * ev.loc[mask, "funding_rate"]).sum()) if funded else 0.
        rows.append({"month": leg.month, "symbol": leg.symbol, "start_ts": a, "end_ts": b,
                     "price_pnl": leg.initial_quantity * (pb - pa), "funding_pnl": cash})
    return pd.DataFrame(rows)


def window_summary(name, start_row, end_row, legs, funding, attributed, market, maps, funded):
    cash = {col: float(end_row[col] - start_row[col]) for col in ["price_pnl", "funding_pnl", "fees", "slippage"]}
    delta = float(end_row.equity - start_row.equity)
    error = cash["price_pnl"] + cash["funding_pnl"] - cash["fees"] - cash["slippage"] - delta
    sliced = window_leg_cash(legs, funding, start_row, end_row, *maps, funded)
    price_error = float(sliced.price_pnl.sum()) - cash["price_pnl"]
    funding_error = float(sliced.funding_pnl.sum()) - cash["funding_pnl"]
    if max(abs(error), abs(price_error), abs(funding_error)) > 1e-5:
        raise ValueError(f"window cash mismatch {name}: {error, price_error, funding_error}")
    days = attributed.loc[attributed.start_ts.ge(start_row.ts) & attributed.end_ts.le(end_row.ts)]
    good = days.loc[days.beta_available]
    valid_price = days.loc[days.price_available]
    modeled_price = float(good.price_pnl.sum())
    model_market = float(good.market_related_price_pnl.sum())
    full_day_price = float(valid_price.price_pnl.sum())
    summary = {"window": name, "start_ts": start_row.ts, "end_ts": end_row.ts,
               "start_equity": float(start_row.equity), "end_equity": float(end_row.equity),
               "return": float(end_row.equity / start_row.equity - 1), "equity_change": delta,
               **cash, "cash_reconciliation_error": error, "leg_price_reconciliation_error": price_error,
               "leg_funding_reconciliation_error": funding_error,
               "full_day_price_pnl": full_day_price, "beta_modeled_price_pnl": modeled_price,
               "market_related_price_pnl": model_market,
               "modeled_residual_price_pnl": float(good.residual_price_pnl.sum()),
               "complete_day_beta_unavailable_price_pnl": full_day_price - modeled_price,
               "boundary_or_unavailable_day_price_pnl": cash["price_pnl"] - full_day_price,
               "full_holding_days": len(days), "beta_available_holding_days": len(good),
               "beta_available_gross_absolute_daily_price_pnl_share": float(good.price_pnl.abs().sum() / valid_price.price_pnl.abs().sum()) if valid_price.price_pnl.abs().sum() else None,
               "negative_leg_segments": int(sliced.price_pnl.lt(0).sum()), "leg_segments": len(sliced),
               "market_references": market_window(market, start_row.ts, end_row.ts),
               "attribution_is_statistical_not_causal": True}
    return summary, sliced


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    if sha(args.contract) != args.contract_sha256 or sha(BUNDLE) != BUNDLE_SHA:
        raise ValueError("frozen contract or bundle differs")
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    prior = json.loads((OLD / "summary.json").read_text())
    for path, digest in prior["source_sha256"].items():
        if sha(OLD / path) != digest:
            raise ValueError(f"frozen previous account file changed: {path}")
    holdings, execution, daily, funding, terminals, pins = load_frozen_inputs()
    save(args.output / "started.json", {"contract_path": str(args.contract), "contract_sha256": args.contract_sha256,
                                        "script_sha256": sha(Path(__file__)), "prior_summary_sha256": sha(OLD / "summary.json"),
                                        "original_inputs": pins, "no_live_operations": True,
                                        "no_new_strategy_parameter_search": True})
    market, features, pool = market_features(daily, json.loads(BUNDLE.read_text())["observed_asset_classes"])
    market.reset_index().to_parquet(args.output / "market-daily-reference.parquet", index=False)
    # Save only per-day selected membership digest/count, not another full matrix.
    pool_rows = []
    for day, g in pool.loc[pool.prior_pool_eligible].groupby("ts", sort=True):
        names = "\n".join(sorted(g.symbol))
        pool_rows.append({"ts": day, "pool_count": len(g), "members_sha256": hashlib.sha256(names.encode()).hexdigest(),
                          "labels_available": int(g.daily_return.notna().sum())})
    pd.DataFrame(pool_rows).to_parquet(args.output / "broad-pool-membership-digests.parquet", index=False)
    exits_all = pd.read_parquet(OLD / "exit-plan.parquet")
    extra = pd.read_parquet(OLD / "execution-prices.parquet")
    maps = (daily.set_index(["ts", "symbol"]).close.to_dict(), execution.set_index(["ts", "symbol"]).price.to_dict(),
            extra.set_index(["ts", "symbol"]).price.to_dict())
    summaries, all_months, all_legs, all_years, all_windows, all_costs, all_windowlegs = [], [], [], [], [], [], []
    for scenario in ["price_only", "estimated_center"]:
        for strategy in ["baseline", "single_exit"]:
            account = f"{scenario}-{strategy}-4bp"
            folder = OLD / account
            trades = pd.read_parquet(folder / "trades.parquet")
            monthly = pd.read_parquet(folder / "monthly.parquet")
            nav, dd = drawdown_episode(pd.read_parquet(folder / "nav.parquet"))
            exits = exits_all if strategy == "single_exit" else exits_all.iloc[:0]
            legs = build_legs(holdings, trades, funding, terminals, exits, execution, extra, scenario != "price_only")
            months, costs = monthly_details(legs, trades, monthly)
            attributed = daily_attribution(legs, features)
            # Holding-day decomposition is small and gives a complete audit trail.
            attributed.to_parquet(args.output / f"{account}-daily-attribution.parquet", index=False)
            windows = [("maximum_drawdown", nav.iloc[dd["peak_index"]], nav.iloc[dd["trough_index"]])]
            for year in [2022, 2025]:
                a, b = pd.Timestamp(f"{year}-01-01T00:15Z"), pd.Timestamp(f"{year+1}-01-01T00:15Z")
                windows.append((str(year), nav.loc[nav.ts.eq(a)].iloc[-1], nav.loc[nav.ts.eq(b)].iloc[-1]))
            for name, a, b in windows:
                summary, wl = window_summary(name, a, b, legs, funding, attributed, market, maps, scenario != "price_only")
                summary["account"] = account
                all_windows.append(summary)
                wl["account"], wl["window"] = account, name
                all_windowlegs.append(wl)
            for frame in [months, legs, costs]:
                frame["account"] = account
            all_months.append(months)
            all_legs.append(legs)
            all_costs.append(costs)
            for year, g in months.groupby(months.month.dt.year, sort=True):
                all_years.append({"account": account, "year": int(year), "months": len(g),
                                  "start_equity": float(g.start_equity.iloc[0]), "end_equity": float(g.end_equity.iloc[-1]),
                                  "return": float(g.end_equity.iloc[-1] / g.start_equity.iloc[0] - 1),
                                  **{c: float(g[c].sum()) for c in ["pnl", "price_pnl", "funding_pnl", "fees", "slippage"]},
                                  "losing_months": int(g['return'].lt(0).sum()), "early_exits": int(g.early_exits.sum()),
                                  "average_price_losing_coins": float(g.price_losing_coins.mean())})
            summaries.append({"account": account, **dd, "months_reconciled": len(months), "legs": len(legs),
                              "max_month_cash_error": float(months.reconciliation_error.abs().max()),
                              "total_rebought_after_prior_early_exit": int(months.rebought_after_prior_month_early_exit.sum()),
                              "months_with_early_exits": int(months.early_exits.gt(0).sum()),
                              "months_with_multiple_early_exits": int(months.early_exits.gt(1).sum()),
                              "max_early_exits_in_a_month": int(months.early_exits.max()),
                              "mean_early_exits_per_month": float(months.early_exits.mean())})
            print(json.dumps({"account_complete": account, "max_drawdown": dd["max_drawdown"], "monthly_cash_error": summaries[-1]["max_month_cash_error"]}), flush=True)
    for name, data in [("monthly-details", pd.concat(all_months)), ("holding-legs", pd.concat(all_legs)),
                       ("monthly-boundary-costs", pd.concat(all_costs)), ("yearly-details", pd.DataFrame(all_years)),
                       ("window-leg-cash", pd.concat(all_windowlegs))]:
        data.to_parquet(args.output / f"{name}.parquet", index=False)
    save(args.output / "window-summary.json", all_windows)
    save(args.output / "summary.json", {"status": "FOUR_FROZEN_ACCOUNTS_CASH_RECONCILED_MODEL_ATTRIBUTION_NOT_CAUSAL",
                                        "accounts": summaries, "funding_not_verified_net": True,
                                        "market_reference_clock_differs_from_0015_by_explicit_boundary_exclusion": True,
                                        "broad_market_any_missing_selected_price_invalidates_day": True,
                                        "daily_model": "prior 60 within-segment days, >=45 pairs, beta known before day; BTC ETH equal-weight factor",
                                        "month_cost_assignment": "Original post-rebalance to next-post-rebalance monthly NAV; next-month entry fees are separate boundary cost rows, first month includes first entry fee.",
                                        "files_sha256": {str(p.relative_to(args.output)): sha(p) for p in sorted(args.output.glob('*')) if p.is_file()}})
    size = sum(p.stat().st_size for p in args.output.rglob('*') if p.is_file())
    if size > 15 * 1024**2:
        raise ValueError(f"drawdown output budget exceeded {size}")


if __name__ == "__main__":
    main()
