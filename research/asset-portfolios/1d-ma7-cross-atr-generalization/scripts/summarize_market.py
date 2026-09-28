"""Account-level comparisons on every declared market, with explicit cohorts."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from common import BASE, RESULTS, sha, write_json

OUTPUT = BASE / "artifacts/analysis_20260909"


def summarize():
    if OUTPUT.exists():
        raise FileExistsError("Preserve existing market analysis")
    hashes = json.loads((RESULTS / "artifact_checksums.json").read_text())
    for file in ["summary.csv", "stress.csv", "buy_hold.csv", "scope.csv", "completion.json"]:
        assert sha(RESULTS / file) == hashes[file], "Result changed: " + file
    completion = json.loads((RESULTS / "completion.json").read_text())
    assert completion["complete"] and completion["coins_failed"] == 0
    scope = pd.read_csv(RESULTS / "scope.csv")
    g = pd.read_csv(RESULTS / "summary.csv")
    s = pd.read_csv(RESULTS / "stress.csv")
    bh = pd.read_csv(RESULTS / "buy_hold.csv")
    full = g[g.window == "full"].copy()
    reference = full[full.case_id == "F0"].set_index("symbol")
    baseline = full[full.case_id == "H4_D0"].set_index("symbol")
    hold = bh[bh.window == "full"].set_index("symbol")
    detail = []
    for row in full.to_dict("records"):
        symbol, cid = row["symbol"], row["case_id"]
        item = dict(row)
        item.update(fixed_return_pct=reference.loc[symbol].return_pct,
                    fixed_drawdown_pct=reference.loc[symbol].max_drawdown_pct,
                    baseline_return_pct=baseline.loc[symbol].return_pct,
                    baseline_drawdown_pct=baseline.loc[symbol].max_drawdown_pct,
                    buy_hold_return_pct=hold.loc[symbol].return_pct,
                    buy_hold_drawdown_pct=hold.loc[symbol].max_drawdown_pct,
                    vs_fixed_return_pp=row["return_pct"] - reference.loc[symbol].return_pct,
                    vs_fixed_drawdown_reduction_pp=row["max_drawdown_pct"] - reference.loc[symbol].max_drawdown_pct,
                    vs_baseline_return_pp=row["return_pct"] - baseline.loc[symbol].return_pct,
                    vs_baseline_drawdown_reduction_pp=row["max_drawdown_pct"] - baseline.loc[symbol].max_drawdown_pct)
        for period in ["early60", "late40"]:
            part = g[(g.symbol == symbol) & (g.case_id == cid) & (g.window == period)]
            for field in ["return_pct", "max_drawdown_pct", "trades"]:
                item[period + "_" + field] = part.iloc[0][field] if len(part) else np.nan
        for scenario in ["slippage_10bp", "carry_5bp_day"]:
            part = s[(s.symbol == symbol) & (s.case_id == cid) & (s.scenario == scenario)]
            assert len(part) == 1
            item[scenario + "_return_pct"] = part.iloc[0].return_pct
            item[scenario + "_max_drawdown_pct"] = part.iloc[0].max_drawdown_pct
        item["historically_profitable"] = row["return_pct"] > 0
        item["risk_count_pass"] = bool(row["trade_days"] >= 180 and row["trades"] >= 10
                                      and row["return_pct"] > 0 and row["max_drawdown_pct"] >= -30 and not row["bankrupt"])
        item["stable_candidate"] = bool(item["risk_count_pass"]
                                        and item["early60_return_pct"] > 0 and item["late40_return_pct"] > 0
                                        and item["early60_trades"] >= 3 and item["late40_trades"] >= 3
                                        and item["slippage_10bp_return_pct"] > 0 and item["carry_5bp_day_return_pct"] > 0)
        item["beats_fixed_both"] = bool(item["vs_fixed_return_pp"] > 0 and item["vs_fixed_drawdown_reduction_pp"] >= 0)
        item["beats_baseline_both"] = bool(item["vs_baseline_return_pp"] > 0 and item["vs_baseline_drawdown_reduction_pp"] >= 0)
        item["beats_buy_hold_return"] = bool(row["return_pct"] > item["buy_hold_return_pct"])
        detail.append(item)
    ranking = pd.DataFrame(detail).sort_values(["cohort", "case_id", "return_pct"], ascending=[True, True, False])
    group_rows = []
    for (cohort, case), part in ranking.groupby(["cohort", "case_id"], sort=True):
        n = len(part)
        row = {"cohort": cohort, "case_id": case, "coins": n,
               "positive_coins": int(part.historically_profitable.sum()),
               "negative_coins": int((part.return_pct < 0).sum()), "flat_coins": int((part.return_pct == 0).sum()),
               "positive_pct": float(part.historically_profitable.mean()*100),
               "median_return_pct": float(part.return_pct.median()),
               "median_max_drawdown_pct": float(part.max_drawdown_pct.median()),
               "worst_max_drawdown_pct": float(part.max_drawdown_pct.min()),
               "median_trades": float(part.trades.median()), "all_trades": int(part.trades.sum()),
               "delayed_entries": int(part.delayed_entries.sum()),
               "risk_count_pass_coins": int(part.risk_count_pass.sum()), "risk_count_pass_pct": float(part.risk_count_pass.mean()*100),
               "stable_candidate_coins": int(part.stable_candidate.sum()), "stable_candidate_pct": float(part.stable_candidate.mean()*100),
               "beats_fixed_both_coins": int(part.beats_fixed_both.sum()),
               "beats_buy_hold_return_coins": int(part.beats_buy_hold_return.sum()),
               "beats_baseline_both_coins": int(part.beats_baseline_both.sum()),
               "median_vs_fixed_return_pp": float(part.vs_fixed_return_pp.median()),
               "median_vs_baseline_return_pp": float(part.vs_baseline_return_pp.median()),
               "vs_baseline_return_up_coins": int((part.vs_baseline_return_pp > 1e-9).sum()),
               "vs_baseline_return_down_coins": int((part.vs_baseline_return_pp < -1e-9).sum()),
               "vs_baseline_return_same_coins": int((part.vs_baseline_return_pp.abs() <= 1e-9).sum()),
               "median_slippage_10bp_return_pct": float(part.slippage_10bp_return_pct.median()),
               "median_carry_5bp_day_return_pct": float(part.carry_5bp_day_return_pct.median()),
               "bankrupt_coins": int(part.bankrupt.sum())}
        hype = part[part.symbol == "HYPE/USDT:USDT"]
        if len(hype):
            value = float(hype.iloc[0].return_pct)
            row["hype_return_pct"] = value
            row["hype_return_rank_desc"] = int((part.return_pct > value).sum()+1)
            row["hype_return_percentile"] = float((part.return_pct <= value).mean()*100)
        group_rows.append(row)
    OUTPUT.mkdir(parents=True)
    ranking.to_csv(OUTPUT / "ranking.csv", index=False)
    pd.DataFrame(group_rows).to_csv(OUTPUT / "cohort_summary.csv", index=False)
    qualified = ranking[ranking.stable_candidate]
    qualified.to_csv(OUTPUT / "all_stable_candidates.csv", index=False)
    risk = ranking[ranking.risk_count_pass]
    risk.to_csv(OUTPUT / "all_risk_count_candidates.csv", index=False)
    excluded = scope[scope.status != "REPLAY_COMPLETED"]
    excluded.to_csv(OUTPUT / "excluded.csv", index=False)
    main = ranking[(ranking.cohort == "main_full") & (ranking.case_id == "H4_D0")]
    assert len(main) == int((scope.cohort == "main_full").sum())
    summary = {"family_id": "BIN-1D-MA7-CAR-GEN", "observed_contracts": 874, "candidate_coins": 652,
               "excluded_non_coin_or_unknown": 222, "completed_coins": completion["coins_completed"],
               "excluded_price_coins": completion["price_excluded"], "execution_failed_coins": 0,
               "cohort_counts": {str(k): int(v) for k,v in scope.cohort.value_counts().items()},
               "primary_case": "H4_D0", "primary_entry_extension": "H4_D3", "cohorts": group_rows,
               "comparison_note": "Each symbol is a separate account; full-period cohort has identical 433 days, partial/short histories are separately grouped. No averages are a tradable portfolio.",
               "funding_window_verified": False, "all_window_results": completion["strategy_window_runs"],
               "all_stress_results": completion["stress_runs"], "all_full_period_trades": int(full.trades.sum()),
               "price_diagnostic_only": True}
    write_json(OUTPUT / "market_summary.json", summary)
    write_json(OUTPUT / "source_manifest.json", {"result_checksums_sha256": sha(RESULTS / "artifact_checksums.json"),
                                                "summary_script_sha256": sha(Path(__file__)), "filters_predeclared": True})
    write_json(OUTPUT / "artifact_checksums.json", {str(p.relative_to(OUTPUT)): sha(p) for p in sorted(OUTPUT.iterdir()) if p.is_file()})
    print(pd.DataFrame(group_rows)[["cohort", "case_id", "coins", "positive_coins", "median_return_pct", "median_max_drawdown_pct", "risk_count_pass_coins", "stable_candidate_coins"]].to_string(index=False))


if __name__ == "__main__":
    summarize()
