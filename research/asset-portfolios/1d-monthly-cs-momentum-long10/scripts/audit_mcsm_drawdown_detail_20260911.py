"""Independent literal OLS, UTC endpoint checks and descriptive rebuy detail."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from verify_mcsm_baseline_20260908 import load_verified_returned_daily

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
OUT = FAMILY / "artifacts/drawdown-frequency-round-20260911/drawdown"
DAY = pd.Timedelta(days=1)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    with path.open("x") as handle:
        json.dump(obj, handle, indent=2, ensure_ascii=False, default=str, allow_nan=False)
        handle.write("\n")


def main():
    receipt = json.loads((OUT / "summary.json").read_text())
    for name, digest in receipt["files_sha256"].items():
        if sha(OUT / name) != digest:
            raise ValueError(f"drawdown output changed: {name}")
    save(OUT / "independent-detail-audit-started.json", {"script_sha256": sha(Path(__file__)),
                                                       "drawdown_summary_sha256": sha(OUT / "summary.json"),
                                                       "audit_sample_rule": "Each account/year first, minimum and maximum complete-day price cash row; auditing already known outputs, not strategy selection."})
    daily = load_verified_returned_daily()
    records = {(r.symbol, r.ts): (float(r.close), bool(r.eligible), str(r.research_segment_id), float(r.quote_volume))
               for r in daily.itertuples(index=False)}

    def ret(symbol, day):
        now, old = records.get((symbol, day)), records.get((symbol, day - DAY))
        if now is None or old is None or not now[1] or not old[1] or now[2] != old[2]:
            return None
        return now[0] / old[0] - 1

    def market_ret(day):
        btc, eth = ret("BTC/USDT:USDT", day), ret("ETH/USDT:USDT", day)
        return (btc + eth) / 2 if btc is not None and eth is not None else None

    legs = pd.read_parquet(OUT / "holding-legs.parquet")
    qmap = legs.set_index(["account", "month", "symbol"]).initial_quantity.to_dict()
    checked = []
    for path in sorted(OUT.glob("*-daily-attribution.parquet")):
        account = path.name.removesuffix("-daily-attribution.parquet")
        days = pd.read_parquet(path)
        valid = days.loc[days.beta_available].copy()
        samples = []
        for _, group in valid.groupby(valid.start_ts.dt.year):
            samples.extend([group.index[0], group.price_pnl.idxmin(), group.price_pnl.idxmax()])
        for row in valid.loc[sorted(set(samples))].itertuples(index=False):
            day, symbol = row.start_ts, row.symbol
            segment = records[(symbol, day)][2]
            xs, ys = [], []
            for lag in range(1, 61):
                target = day - lag * DAY
                present = records.get((symbol, target))
                if present is None or present[2] != segment:
                    break
                rr, mm = ret(symbol, target), market_ret(target)
                if rr is not None and mm is not None:
                    ys.append(rr)
                    xs.append(mm)
            if len(xs) < 45:
                raise ValueError("audited beta uses insufficient history")
            design = np.column_stack([np.ones(len(xs)), xs])
            intercept, beta = np.linalg.lstsq(design, np.array(ys), rcond=None)[0]
            q = qmap[(account, row.month, symbol)]
            prior, close = records[(symbol, day-DAY)][0], records[(symbol, day)][0]
            price = q * (close - prior)
            model = q * prior * beta * market_ret(day)
            errors = {"beta_error": beta - row.beta, "price_cash_error": price - row.price_pnl,
                      "market_cash_error": model - row.market_related_price_pnl,
                      "residual_cash_error": price - model - row.residual_price_pnl}
            if abs(errors["beta_error"]) > 1e-9 or max(abs(v) for k, v in errors.items() if k != "beta_error") > 1e-5:
                raise ValueError(f"independent OLS or cash mismatch {account} {symbol} {day}: {errors}")
            if len(xs) != int(row.beta_prior_observations):
                raise ValueError("independent OLS observation count differs")
            checked.append({"account": account, "symbol": symbol, "day": day, "prior_pairs": len(xs),
                            "ols_intercept_kept_in_residual": intercept, "independent_beta": beta, **errors})
    pd.DataFrame(checked).to_parquet(OUT / "independent-ols-samples.parquet", index=False)
    clocks = []
    for window in json.loads((OUT / "window-summary.json").read_text()):
        reference = window["market_references"]
        start, end = pd.Timestamp(reference["reference_start_utc"]), pd.Timestamp(reference["reference_end_utc"])
        if start < pd.Timestamp(window["start_ts"]) or end > pd.Timestamp(window["end_ts"]):
            raise ValueError("market reference crosses account boundary")
        for symbol, field in [("BTC/USDT:USDT", "btc_return"), ("ETH/USDT:USDT", "eth_return")]:
            # Bar open-day D closes at D+1 00:00. Reference start therefore
            # uses close(start-DAY), end uses close(end-DAY), never close(start).
            value = records[(symbol, end-DAY)][0] / records[(symbol, start-DAY)][0] - 1
            error = value - reference[field]
            if abs(error) > 1e-11:
                raise ValueError("BTC/ETH reference is shifted one day")
            clocks.append({"account": window["account"], "window": window["window"], "symbol": symbol,
                           "reference_start": start, "reference_end": end,
                           "first_price_bar_open": start-DAY, "last_price_bar_open": end-DAY,
                           "endpoint_return": value, "difference": error})
    pd.DataFrame(clocks).to_parquet(OUT / "independent-market-clock-checks.parquet", index=False)
    # The same 12 selections occur in both quantity paths. Keep amounts apart.
    rebuys = []
    for account, group in legs.groupby("account", sort=True):
        if "single_exit" not in account:
            continue
        prior = group.set_index(["month", "symbol"])
        for leg in group.itertuples(index=False):
            key = (leg.month - pd.offsets.MonthBegin(1), leg.symbol)
            if key not in prior.index or not bool(prior.loc[key, "early_exit"]):
                continue
            old = prior.loc[key]
            rebuys.append({"account": account, "symbol": leg.symbol, "prior_month": key[0],
                           "prior_early_exit_ts": old.actual_exit_ts, "prior_exit_price": old.exit_price,
                           "rebuy_month": leg.month, "rebuy_ts": leg.entry_ts, "rebuy_price": leg.entry_price,
                           "new_exit_ts": leg.actual_exit_ts, "new_exit_price": leg.exit_price,
                           "new_price_pnl": leg.price_pnl, "new_funding_pnl": leg.funding_pnl,
                           "new_direct_exit_fees": leg.direct_exit_fees, "new_direct_exit_slippage": leg.direct_exit_slippage,
                           "new_net_before_month_boundary_costs": leg.net_before_separate_month_boundary_costs})
    rebuy_frame = pd.DataFrame(rebuys)
    rebuy_frame.to_parquet(OUT / "rebought-after-prior-exit.parquet", index=False)
    months = pd.read_parquet(OUT / "monthly-details.parquet")
    worst = pd.concat([g.nsmallest(5, "return") for _, g in months.groupby("account")], ignore_index=True)
    worst.to_parquet(OUT / "worst-five-months.parquet", index=False)
    # Expose exact broad-market missing labels for every requested reference
    # date. Membership is derived only from 31 closes before the target date.
    market = pd.read_parquet(OUT / "market-daily-reference.parquet")
    window_dates = set()
    for w in json.loads((OUT / "window-summary.json").read_text()):
        ref = w["market_references"]
        window_dates |= set(pd.date_range(ref["reference_start_utc"], pd.Timestamp(ref["reference_end_utc"])-DAY, freq="D"))
    unknown_days = market.loc[market.ts.isin(window_dates) & market.broad_return.isna(), "ts"]
    classes = json.loads((ROOT / "research/platform/data-lake-governance/specs/binance-v3-research-input-bundle-v2.json").read_text())["observed_asset_classes"]
    gaps = []
    for day in unknown_days:
        selected, missing = [], []
        for symbol in sorted(s for s, c in classes.items() if c == "COIN"):
            prior = [records.get((symbol, day - n*DAY)) for n in range(1, 32)]
            if any(x is None or not x[1] for x in prior) or len({x[2] for x in prior}) != 1:
                continue
            if np.mean([x[3] for x in prior[:30]]) < 1e7:
                continue
            selected.append(symbol)
            if ret(symbol, day) is None:
                missing.append(symbol)
        if len(selected) >= 5 and not missing:
            raise ValueError("broad benchmark reported unavailable without an independent missing label")
        gaps.append({"day": day, "prior_selected_count": len(selected), "missing_symbols": missing,
                     "reason": "LESS_THAN_FIVE_PRIOR_MEMBERS" if len(selected) < 5 else "MISSING_OR_INVALID_SELECTED_RETURN"})
    save(OUT / "broad-market-unavailable-days.json", gaps)
    result = {"status": "INDEPENDENT_LITERAL_OLS_CASH_CLOCK_AND_BROAD_GAP_CHECK_PASS", "ols_samples": len(checked),
              "max_beta_error": max(abs(x["beta_error"]) for x in checked),
              "max_cash_error": max(abs(x[k]) for x in checked for k in ["price_cash_error", "market_cash_error", "residual_cash_error"]),
              "market_endpoint_checks": len(clocks), "broad_unavailable_unique_days_checked": len(gaps),
              "rebuys": [{"account": account, "count": len(g),
                           **{c: float(g[c].sum()) for c in ["new_price_pnl", "new_funding_pnl", "new_direct_exit_fees", "new_direct_exit_slippage", "new_net_before_month_boundary_costs"]},
                           "positive_price_legs": int(g.new_price_pnl.gt(0).sum()),
                           "positive_direct_net_legs": int(g.new_net_before_month_boundary_costs.gt(0).sum())}
                          for account, g in rebuy_frame.groupby("account")],
              "yearly_reporting_bridge": "Original older summary yearly used Jan1 00:00 NAV. Current month-summed yearly uses Jan1 00:15 after monthly rebalance, matching original monthly.parquet. Same account, different explicit boundary.",
              "files_sha256": {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.glob('*')) if p.is_file()}}
    save(OUT / "independent-detail-audit.json", result)
    print(json.dumps(result, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
