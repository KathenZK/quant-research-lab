"""Independent direct-window signals and endpoint cash audit for MA120."""
from __future__ import annotations

import math
import json
from pathlib import Path

import numpy as np
import pandas as pd

from audit_mcsm_single_exit_account_20260910 import reconstruct, check_complete_nav
from audit_mcsm_funding_account_bridge_20260910 import terminals_from_raw
from research_mcsm_single_asset_exit_20260910 import FAMILY, load_frozen_inputs, save, sha

OUT = FAMILY / "artifacts/ma120-round-20260911"
DAY = pd.Timedelta(days=1)


def exact_ma(group, day):
    """Select 120 exact calendar rows and directly sum; no rolling feature reuse."""
    window = group.loc[group.ts.ge(day - 119 * DAY) & group.ts.le(day)].sort_values("ts")
    if len(window) != 120 or list(window.ts) != list(pd.date_range(day - 119 * DAY, day)):
        return None
    if (not window.eligible.eq(True).all() or not np.isfinite(window.close.to_numpy(float)).all()
            or not window.close.gt(0).all() or window.research_segment_id.nunique(dropna=False) != 1):
        return None
    for name, at in [("LIT/USDT:USDT", "2025-12-23T17:30Z"), ("AERGO/USDT:USDT", "2025-04-16T11:00Z")]:
        if group.symbol.iloc[0] == name and day - 119 * DAY < pd.Timestamp(at) < day + DAY:
            return None
    return math.fsum(window.close.to_numpy(float)) / 120


def audit_signals(h, daily, entries, exits):
    groups = {s: g for s, g in daily.loc[daily.symbol.isin(h.symbol)].groupby("symbol")}
    ent = entries.set_index(["month", "symbol"])
    expected = []
    tested = 0
    for r in h.itertuples(index=False):
        g = groups[r.symbol]
        ma = exact_ma(g, r.month - DAY)
        opening = float(g.loc[g.ts.eq(r.month), "open"].iloc[0])
        admitted = ma is not None and opening > ma
        e = ent.loc[(r.month, r.symbol)]
        assert bool(e.admitted) == admitted
        assert bool(e.ma120_valid) == (ma is not None)
        assert e.month_0000_open == opening
        if ma is not None:
            assert np.isclose(e.ma120_known_at_0000, ma, rtol=1e-13, atol=1e-13)
        if not admitted:
            continue
        for day in pd.date_range(r.month, r.exit_ts.floor("D")):
            execution = day + DAY + pd.Timedelta(minutes=15)
            if execution >= r.exit_ts:
                break
            ma = exact_ma(g, day)
            if ma is None:
                raise ValueError("independent held indicator unknown")
            tested += 1
            close = float(g.loc[g.ts.eq(day), "close"].iloc[0])
            if close < ma:
                expected.append((r.month, r.symbol, day, execution))
                break
    actual = list(map(tuple, exits[["month", "symbol", "signal_day", "exit_ts"]].values))
    assert set(expected) == set(actual) and len(expected) == len(actual)
    return {"monthly_slots_checked": len(h), "daily_conditions_checked": tested,
            "entry_decisions_exact": True, "exit_targets_exact": len(expected), "independent_direct_means": True}


def main():
    summary = json.loads((OUT / "summary.json").read_text())
    for name, digest in summary["source_sha256"].items():
        if sha(OUT / name) != digest:
            raise ValueError(f"changed candidate output: {name}")
    h, execution, daily, funding, _, _ = load_frozen_inputs()
    entries = pd.read_parquet(OUT / "entry-decisions.parquet")
    exits = pd.read_parquet(OUT / "exit-plan.parquet")
    extra = pd.read_parquet(OUT / "execution-prices.parquet").set_index(["ts", "symbol"]).price
    signals = audit_signals(h, daily, entries, exits)
    print(json.dumps(signals), flush=True)
    execution = execution.set_index(["ts", "symbol"]).price
    daily = daily.set_index(["ts", "symbol"])
    terminals, pins = terminals_from_raw()
    expected = {(s, v, c) for s in ["price_only", "estimated_center"] for v in ["baseline", "ma120"] for c in [.0004, .0008]}
    assert {(r["scenario"], r["strategy"], r["slippage_rate"]) for r in summary["results"]} == expected
    assert len(summary["results"]) == 8
    rows = []
    for metrics in summary["results"]:
        s, v, slip = metrics["scenario"], metrics["strategy"], metrics["slippage_rate"]
        path = OUT / f"{s}-{v}-{int(slip * 10000)}bp"
        nav = pd.read_parquet(path / "nav.parquet")
        check_complete_nav(nav, extra)
        candidate_h = h.copy()
        if v == "ma120":
            weights = entries.set_index(["month", "symbol"]).target_weight.to_dict()
            candidate_h["weight"] = [weights[(m, name)] for m, name in zip(h.month, h.symbol)]
        mapping = exits.set_index(["month", "symbol"]).exit_ts.to_dict() if v == "ma120" else {}
        found = reconstruct(candidate_h, execution, daily, funding, terminals, mapping, extra, nav, slip, s != "price_only")
        months = pd.read_parquet(path / "monthly.parquet")
        independently_months = found.pop("monthly")
        assert months.month.equals(independently_months.month)
        found["max_monthly_return_error"] = float(np.max(np.abs(months.account_return - independently_months.account_return)))
        differences = {k: found[k] - metrics[k] for k in ["final_equity", "funding_pnl_usdt", "fees_usdt", "slippage_usdt"]}
        differences["price_pnl"] = found["price_pnl"] - metrics["price_pnl_usdt"]
        differences["mdd"] = found["mdd_recomputed"] - metrics["max_drawdown_daily_and_rebalance"]
        assert np.isfinite(list(differences.values())).all()
        assert max(abs(x) for x in differences.values()) < 1e-4
        assert found["max_nav_absolute_error_usdt"] < 1e-4
        assert found["max_monthly_return_error"] < 1e-10 and abs(differences["mdd"]) < 1e-10
        assert np.isclose(np.prod(1 + months.account_return), 1 + metrics["total_return"], rtol=1e-11)
        years = pd.read_parquet(path / "yearly.parquet")
        assert np.isclose(np.prod(1 + years["return"]), 1 + metrics["total_return"], rtol=1e-11)
        for y in years.itertuples(index=False):
            g = months.loc[months.month.dt.year.eq(y.year)]
            assert y.start_equity == g.account_start_equity.iloc[0] and y.end_equity == g.account_end_equity.iloc[-1]
        if v == "ma120":
            legs = pd.read_parquet(OUT / f"legs-{s}-{int(slip * 10000)}bp.parquet")
            assert np.isclose(legs.actual_price_pnl.sum(), metrics["price_pnl_usdt"], atol=1e-6)
            assert np.isclose(legs.actual_funding_pnl.sum(), metrics["funding_pnl_usdt"], atol=1e-6)
            assert legs.loc[~legs.admitted, "quantity"].eq(0).all()
        found.update(strategy=v, scenario=s, slippage_rate=slip, differences=differences, matches=True)
        rows.append(found)
        print(json.dumps(found), flush=True)
    save(OUT / "independent-audit.json", {"status": "PASS_ALL_8_ACCOUNTS_AND_DIRECT_MA120_SIGNALS",
                                         "signals": signals, "results": rows, "terminal_pins": pins,
                                         "summary_sha256": sha(OUT / "summary.json"),
                                         "script_sha256": sha(Path(__file__)),
                                         "cash_auditor_sha256": sha(Path(__file__).with_name("audit_mcsm_single_exit_account_20260910.py"))})


if __name__ == "__main__":
    main()
