"""One user-prescribed Top10/MA120 rule, with preserved historical comparators."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research_mcsm_single_asset_exit_20260910 import (
    BASE, DAY, FAMILY, NATIVE, ROOT, SCENARIOS, load_frozen_inputs, replay_exit, save, sha,
)
from research_mcsm_weekly_20260911 import build_requests, load_execution, load_old_endpoints
from replay_mcsm_ma120_20260911 import replay_ma

OUT = FAMILY / "artifacts/ma120-round-20260911"
SPEC = FAMILY / "specs/binance-1d-mcsm-ma120-round-20260911.md"
WEEKLY = FAMILY / "artifacts/drawdown-frequency-round-20260911/weekly"
MIN15 = pd.Timedelta(minutes=15)
IDENTITY = {"LIT/USDT:USDT": pd.Timestamp("2025-12-23T17:30Z"),
            "AERGO/USDT:USDT": pd.Timestamp("2025-04-16T11:00Z")}


def pin(path, expected):
    if sha(path) != expected:
        raise ValueError(f"changed pinned source: {path}")


def features(daily, symbols):
    parts = []
    for symbol, group in daily.loc[daily.symbol.isin(symbols)].groupby("symbol", sort=True):
        g = group.sort_values("ts").reset_index(drop=True).copy()
        g["ts"] = pd.to_datetime(g.ts, utc=True)
        if g.ts.duplicated().any():
            raise ValueError("duplicate feature day")
        valid = g.eligible.eq(True) & np.isfinite(g.close) & g.close.gt(0)
        runs = g.research_segment_id.ne(g.research_segment_id.shift()).fillna(True).astype(int).cumsum()
        enough = g.index.to_series().ge(119)
        contiguous = g.ts.sub(g.ts.shift(119)).eq(119 * DAY)
        same_segment = runs.eq(runs.shift(119))
        g["valid120"] = enough & contiguous & same_segment & valid.rolling(120).sum().eq(120)
        g["reason"] = np.where(enough, "GAP_OR_INELIGIBLE_SEGMENT", "LESS_THAN_120_OBSERVED_DAYS")
        boundary = IDENTITY.get(symbol)
        if boundary is not None:
            crossed = (g.ts - 119 * DAY).lt(boundary) & (g.ts + DAY).gt(boundary)
            g.loc[crossed, "valid120"] = False
            g.loc[crossed, "reason"] = "IDENTITY_RESTART_120_DAYS_NOT_READY"
        g.loc[g.valid120, "reason"] = "KNOWN"
        g["ma120"] = g.close.rolling(120, min_periods=120).mean().where(g.valid120)
        parts.append(g[["symbol", "ts", "open", "close", "ma120", "valid120", "reason"]])
    return pd.concat(parts, ignore_index=True).set_index(["symbol", "ts"]).sort_index()


def choose_entries(holdings, feat):
    rows = []
    for r in holdings.itertuples(index=False):
        prior = feat.loc[(r.symbol, r.month - DAY)] if (r.symbol, r.month - DAY) in feat.index else None
        opening = float(feat.loc[(r.symbol, r.month), "open"])
        if not np.isfinite(opening) or opening <= 0:
            raise ValueError(f"missing month-opening price: {r.symbol} {r.month}")
        known = prior is not None and bool(prior.valid120)
        ma = float(prior.ma120) if known else np.nan
        admitted = bool(known and opening > ma)
        reason = ("BUY_ABOVE_MA120" if admitted else "AT_OR_BELOW_MA120") if known else (
            str(prior.reason) if prior is not None else "NO_PREVIOUS_COMPLETE_DAY")
        rows.append({"month": r.month, "symbol": r.symbol, "entry_ts": r.entry_ts,
                     "month_0000_open": opening, "ma120_known_at_0000": ma,
                     "ma120_valid": known, "admitted": admitted, "entry_reason": reason,
                     "target_weight": .1 if admitted else 0.})
    return pd.DataFrame(rows)


def choose_exits(holdings, entries, feat):
    admitted = set(map(tuple, entries.loc[entries.admitted, ["month", "symbol"]].values))
    checks, exits = [], []
    for r in holdings.itertuples(index=False):
        if (r.month, r.symbol) not in admitted:
            continue
        for day in pd.date_range(r.month, r.exit_ts.floor("D"), freq="D"):
            execution = day + DAY + MIN15
            if execution >= r.exit_ts:
                break
            f = feat.loc[(r.symbol, day)] if (r.symbol, day) in feat.index else None
            if f is None or not bool(f.valid120):
                raise ValueError(f"unknown held MA120 day: {r.symbol} {day}")
            trigger = bool(f.close < f.ma120)
            checks.append({"month": r.month, "symbol": r.symbol, "day": day,
                           "decision_ts": day + DAY, "exit_ts": execution,
                           "close": float(f.close), "ma120": float(f.ma120), "trigger": trigger})
            if trigger:
                exits.append({"month": r.month, "symbol": r.symbol, "signal_day": day,
                              "decision_ts": day + DAY, "exit_ts": execution,
                              "original_exit_ts": r.exit_ts})
                break
    columns = ["month", "symbol", "signal_day", "decision_ts", "exit_ts", "original_exit_ts"]
    return pd.DataFrame(checks), pd.DataFrame(exits, columns=columns)


def load_cache():
    """Hash-pinned family projections only, with the original receipt chain."""
    path = WEEKLY / "postrun-integrity.json"
    pin(path, "7c1b3cc76843e9f542cedc6883ee1c22acb2709d09ead67de556fc85ceeb452b")
    audit = json.loads(path.read_text())
    pin(WEEKLY / "summary.json", audit["summary_sha256"])
    pin(Path(__file__).with_name("research_mcsm_weekly_20260911.py"), audit["execution_script_sha256"])
    started = json.loads((WEEKLY / "execution-started.json").read_text())
    pin(WEEKLY / "execution-plan.json", started["execution_plan_sha256"])
    plan = json.loads((WEEKLY / "execution-plan.json").read_text())
    old, sources = load_old_endpoints(plan["old_receipts"])
    pieces = [old]
    # The pinned postrun audit records hashes of every receipt, which in turn
    # records exact request/report/frame hashes. Qualification slices lack open
    # prices and are deliberately not admitted as executable price references.
    receipt_pins = next(value for key, value in audit.items()
                        if isinstance(value, list) and value and isinstance(value[0], dict)
                        and "path" in value[0] and "sha256" in value[0])
    for item in receipt_pins:
        if item["path"].startswith("qualification/"):
            continue
        receipt_path = WEEKLY / item["path"]
        pin(receipt_path, item["sha256"])
        receipt = json.loads(receipt_path.read_text())
        label = receipt["label"]
        for role, subdir, ext in (("request", "requests", "json"), ("report", "reports", "json"),
                                 ("frame", "returned-targets", "parquet")):
            pin(WEEKLY / subdir / f"{label}.{ext}", receipt[f"{role}_sha256"])
        if json.loads((WEEKLY / "reports" / f"{label}.json").read_text())["status"] != "PRICE_DIAGNOSTIC_INPUTS_VERIFIED":
            raise ValueError("unverified cached report")
        pieces.append(pd.read_parquet(WEEKLY / "returned-targets" / f"{label}.parquet"))
    result = pd.concat(pieces, ignore_index=True)
    if result.duplicated(["symbol", "ts"]).any():
        raise ValueError("duplicate cached price")
    return result, sources


def required_targets(holdings, exits):
    rows = []
    for ts in sorted(exits.exit_ts.unique()):
        held = holdings.loc[holdings.entry_ts.lt(ts) & holdings.exit_ts.ge(ts)]
        for r in held.itertuples(index=False):
            rows.extend([{"symbol": r.symbol, "ts": ts}, {"symbol": r.symbol, "ts": ts - MIN15}])
    return pd.DataFrame(rows, columns=["symbol", "ts"]).drop_duplicates().sort_values(["ts", "symbol"])


def executable_prices(holdings, entries, exits, endpoints):
    indexed = endpoints.set_index(["symbol", "ts"])
    rows = []
    exit_keys = set(zip(exits.symbol, exits.exit_ts))
    for ts in sorted(exits.exit_ts.unique()):
        held = holdings.loc[holdings.entry_ts.lt(ts) & holdings.exit_ts.ge(ts)]
        for r in held.itertuples(index=False):
            if (r.symbol, ts) not in indexed.index:
                raise ValueError(f"no common valuation price: {r.symbol} {ts}")
            f = indexed.loc[(r.symbol, ts)]
            p = float(f.open)
            if not np.isfinite(p) or p <= 0:
                raise ValueError("invalid executable price")
            if (r.symbol, ts) in exit_keys:
                prior = indexed.loc[(r.symbol, ts - MIN15)]
                if not bool(prior.eligible) or not bool(prior.research_window_valid):
                    raise ValueError("early exit lacks closed prior activity")
            rows.append({"symbol": r.symbol, "ts": ts, "price": p,
                         "source_receipt": f.source_receipt})
    # Original monthly active-bar proof is retained; independently ensure each
    # admitted name has its required previous closed 15m bar in the projection.
    for r in entries.loc[entries.admitted].itertuples(index=False):
        prior = indexed.loc[(r.symbol, r.entry_ts - MIN15)]
        if not bool(prior.eligible) or not bool(prior.research_window_valid):
            raise ValueError("entry lacks original closed prior activity")
    return pd.DataFrame(rows, columns=["symbol", "ts", "price", "source_receipt"])


def annual(monthly):
    rows = []
    for year, g in monthly.groupby(monthly.month.dt.year, sort=True):
        a, b = float(g.account_start_equity.iloc[0]), float(g.account_end_equity.iloc[-1])
        rows.append({"year": int(year), "months": len(g), "start_equity": a, "end_equity": b,
                     "pnl_usdt": b - a, "return": b / a - 1})
    return pd.DataFrame(rows)


def leg_bridge(h, entries, execution, funding, terminals, exits, extra, result, baseline, scenario, slip):
    prices = execution.set_index(["ts", "symbol"]).price.to_dict()
    ends = {(r["ts"], r["symbol"]): r["center"] for r in terminals}
    early = exits.set_index(["month", "symbol"]).exit_ts.to_dict()
    xp = extra.set_index(["ts", "symbol"]).price.to_dict()
    ent = entries.set_index(["month", "symbol"])
    qs = result["trades"].set_index(["ts", "symbol"]).new_quantity.to_dict()
    bqs = baseline["trades"].set_index(["ts", "symbol"]).new_quantity.to_dict()
    fg = {s: g for s, g in funding.groupby("symbol")}
    rows = []
    for r in h.itertuples(index=False):
        e = ent.loc[(r.month, r.symbol)]
        bought = bool(e.admitted)
        start = prices[(r.entry_ts, r.symbol)]
        terminal = (r.exit_ts, r.symbol) in ends
        old_end = ends.get((r.exit_ts, r.symbol), prices.get((r.exit_ts, r.symbol)))
        cutoff = early.get((r.month, r.symbol), r.exit_ts) if bought else r.entry_ts
        end = xp[(cutoff, r.symbol)] if bought and cutoff < r.exit_ts else old_end if bought else start
        events = fg[r.symbol].loc[fg[r.symbol].ts.gt(r.entry_ts) & fg[r.symbol].ts.le(r.exit_ts)]
        cash = -events.mark_center * events.funding_rate / start if scenario != "price_only" else events.mark_center * 0.
        original_f = float(cash.sum())
        actual_f = float(cash.loc[events.ts.le(cutoff)].sum()) if bought else 0.
        original_cost = .001 + slip + old_end / start * (.001 + (0 if terminal else slip))
        actual_cost = (.001 + slip + end / start * (.001 + (0 if terminal and cutoff == r.exit_ts else slip))) if bought else 0.
        original_price = old_end / start - 1
        actual_price = end / start - 1 if bought else 0.
        q = qs.get((r.entry_ts, r.symbol), 0.) if bought else 0.
        old_net, new_net = original_price + original_f - original_cost, actual_price + actual_f - actual_cost
        rows.append({"month": r.month, "symbol": r.symbol, "admitted": bought, "reason": e.entry_reason,
                     "entry_ts": r.entry_ts, "actual_exit_ts": cutoff if bought else pd.NaT,
                     "early_exit": bought and cutoff < r.exit_ts, "entry_price": start,
                     "exit_price": end if bought else np.nan, "quantity": q,
                     "entry_notional": q * start, "actual_price_pnl": q * (end - start),
                     "actual_funding_pnl": q * start * actual_f,
                     "original_price_return": original_price, "candidate_price_return": actual_price,
                     "original_net_return": old_net, "candidate_net_return": new_net,
                     "net_return_difference": new_net - old_net,
                     "fixed_baseline_q_net_difference": bqs[(r.entry_ts, r.symbol)] * start * (new_net - old_net)})
    legs = pd.DataFrame(rows)
    winners = legs.loc[legs.original_net_return.gt(0)]
    top = winners.sort_values(["original_net_return", "symbol", "month"], ascending=[False, True, True]).head(76)
    losers = legs.loc[legs.original_net_return.lt(0)]
    diff = legs.fixed_baseline_q_net_difference
    explanation = {"normalization": "equal one-USDT entry slots, full roundtrip cost; not compounded account PnL",
                   "original_winning_legs": len(winners), "top_winners": len(top),
                   "winning_profit_retention": float(winners.candidate_net_return.sum() / winners.original_net_return.sum()),
                   "top76_profit_retention": float(top.candidate_net_return.sum() / top.original_net_return.sum()),
                   "top76_entered": int(top.admitted.sum()), "top76_early_exit": int(top.early_exit.sum()),
                   "original_losing_leg_loss": float(-losers.original_net_return.sum()),
                   "candidate_return_on_original_losers": float(losers.candidate_net_return.sum()),
                   "improved_legs": int(legs.net_return_difference.gt(0).sum()),
                   "worsened_legs": int(legs.net_return_difference.lt(0).sum()),
                   "fixed_baseline_q_avoided_loss_usdt": float(diff.clip(lower=0).sum()),
                   "fixed_baseline_q_missed_profit_usdt": float(-diff.clip(upper=0).sum())}
    return legs, explanation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "execute"])
    args = parser.parse_args()
    h, execution, daily, funding, terminals, original = load_frozen_inputs()
    if args.phase == "prepare":
        if OUT.exists():
            raise FileExistsError(OUT)
        OUT.mkdir()
        save(OUT / "started.json", {"contract_sha256": sha(SPEC), "source": original,
                                    "scripts": {p.name: sha(p) for p in [Path(__file__), Path(__file__).with_name("replay_mcsm_ma120_20260911.py"),
                                                                       Path(__file__).with_name("mcsm_ma120_accounting_20260911.py")]}})
        feat = features(daily, set(h.symbol))
        entries = choose_entries(h, feat)
        checks, exits = choose_exits(h, entries, feat)
        entries.to_parquet(OUT / "entry-decisions.parquet", index=False)
        checks.to_parquet(OUT / "signal-days.parquet", index=False)
        exits.to_parquet(OUT / "exit-plan.parquet", index=False)
        needs = required_targets(h, exits)
        old, sources = load_cache()
        requests = build_requests(needs, old)
        for item in requests:
            save(OUT / "execution/requests" / f"{item['label']}.json", item["request"])
        save(OUT / "plan.json", {"requests": requests, "old_monthly_receipts": sources,
                                  "contract_sha256": sha(SPEC), "source_sha256": {
                                      name: sha(OUT / name) for name in ["started.json", "entry-decisions.parquet", "signal-days.parquet", "exit-plan.parquet"]},
                                  "required_targets": len(needs), "entry_counts": entries.entry_reason.value_counts().to_dict(),
                                  "exits": len(exits), "new_requests": len(requests), "frozen_before_new_execution_prices": True})
        print(json.dumps({"phase": "PLAN_FROZEN", "entries": int(entries.admitted.sum()), "exits": len(exits),
                          "reasons": entries.entry_reason.value_counts().to_dict(), "new_requests": len(requests)}), flush=True)
        return
    plan = json.loads((OUT / "plan.json").read_text())
    pin(SPEC, plan["contract_sha256"])
    for name, digest in plan["source_sha256"].items():
        pin(OUT / name, digest)
    started = json.loads((OUT / "started.json").read_text())
    for name, digest in started["scripts"].items():
        pin(Path(__file__).with_name(name), digest)
    entries = pd.read_parquet(OUT / "entry-decisions.parquet")
    exits = pd.read_parquet(OUT / "exit-plan.parquet")
    old, _ = load_cache()
    endpoints, receipts = load_execution(plan["requests"], OUT / "execution", old)
    extra = executable_prices(h, entries, exits, endpoints)
    extra.to_parquet(OUT / "execution-prices.parquet", index=False)
    save(OUT / "execution-summary.json", {"receipts": receipts, "execution_sha256": sha(OUT / "execution-prices.parquet"),
                                         "prior_bar_checks": int(entries.admitted.sum()) + len(exits)})
    no_exits, no_extra = exits.iloc[:0], extra.iloc[:0]
    admitted = set(map(tuple, entries.loc[entries.admitted, ["month", "symbol"]].values))
    results, explanations, reproductions = [], [], []
    for scenario in SCENARIOS:
        expected = (json.loads((BASE / f"accounts/{scenario}/summary.json").read_text()) if scenario == "price_only" else
                    json.loads((NATIVE / "summary.json").read_text())["metrics"])
        exact = replay_ma(h, execution, daily, funding, terminals, no_exits, no_extra, scenario)
        for field in ["final_equity", "total_return", "max_drawdown_daily_and_rebalance", "funding_pnl_usdt", "fees_usdt", "slippage_usdt"]:
            if not np.isclose(exact["metrics"][field], expected[field], rtol=1e-10, atol=1e-6):
                raise ValueError(f"original baseline reproduction failed: {scenario} {field}")
        reproductions.append({"scenario": scenario, "matches": True, "final_equity": exact["metrics"]["final_equity"]})
        for slip in [.0004, .0008]:
            print(f"REPLAY {scenario} slip={slip}", flush=True)
            baseline = replay_exit(h, execution, daily, funding, terminals, no_exits, extra, scenario, slip)
            candidate = replay_ma(h, execution, daily, funding, terminals, exits, extra, scenario, slip, admitted)
            for strategy, result in [("baseline", baseline), ("ma120", candidate)]:
                folder = OUT / f"{scenario}-{strategy}-{int(slip * 10000)}bp"
                folder.mkdir()
                yearly = annual(result["monthly"])
                result["metrics"].update(strategy=strategy, yearly=yearly.to_dict("records"))
                result["monthly"]["pnl_usdt"] = result["monthly"].account_end_equity - result["monthly"].account_start_equity
                for key in ["nav", "daily", "monthly", "trades", "funding", "terminals", "early-exits"]:
                    result[key].to_parquet(folder / f"{key}.parquet", index=False)
                yearly.to_parquet(folder / "yearly.parquet", index=False)
                save(folder / "summary.json", result["metrics"])
                results.append(result["metrics"])
                print(json.dumps({k: result["metrics"][k] for k in ["strategy", "scenario", "total_return", "cagr_365_25", "max_drawdown_daily_and_rebalance"]}), flush=True)
            legs, explanation = leg_bridge(h, entries, execution, funding, terminals, exits, extra, candidate, baseline, scenario, slip)
            legs.to_parquet(OUT / f"legs-{scenario}-{int(slip * 10000)}bp.parquet", index=False)
            explanation.update(scenario=scenario, slippage_rate=slip)
            explanations.append(explanation)
    save(OUT / "summary.json", {"status": "COMPUTED_PENDING_INDEPENDENT_AUDIT", "results": results,
                                "baseline_reproductions": reproductions, "leg_explanations": explanations,
                                "entry_counts": plan["entry_counts"], "early_exits": len(exits),
                                "source_sha256": {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob("*")) if p.is_file()}})


if __name__ == "__main__":
    main()
