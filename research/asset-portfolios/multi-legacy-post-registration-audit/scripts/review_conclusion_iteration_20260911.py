"""Read saved September 11 evidence; never import or rerun a strategy engine.

The historical hash snapshot was collected before authorized correction-document
edits. This new review preserves all historical results and acceptance files.
"""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
FAMILY = Path(__file__).resolve().parents[1]
OLD = FAMILY / "artifacts/iteration_comparison_20260911"
OUT = FAMILY / "artifacts/conclusion_review_20260911"
TOL = 1e-9  # Fraction of initial account equity, not percentage points.
ERRORS = []
CHECKS = collections.Counter()
READ_HASHES = {}
MONTH_SENSITIVITY = []

# Fixed independently from the pre-result plans; no return-based endpoint choice.
ENDPOINTS = {
    "EMA-X": ("V1", "V18"), "EMA-TB": ("V35", "V41"),
    "MII": ("V1", "V1.4A"), "ENS": ("V35+MII1.3", "V2"),
    "BNB_1h_AR": ("V1", "V3"), "BTC_1h_AR": ("V1", "V4"),
    "ETH_1h_AR": ("V1", "V4"), "HYPE_15m_MMTF": ("V1", "V3"),
    "HYPE_1h_AR": ("V1", "V4"), "HYPE_1h_MMTF": ("V1", "V3"),
    "HYPE_30m_Keltner": ("V2.1", "V3"), "SOL_1h_AR": ("V1", "V3"),
    "TRX_1h_AR": ("V1", "V3"), "HYPE-CC": ("V10", "V35"),
}
SCENARIOS = ("equal_1x_base", "original_size_base", "equal_1x_stress")


def path(p):
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def sha(p):
    p = path(p)
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    READ_HASHES[str(p.relative_to(ROOT))] = h
    return h


def read_json(p):
    p = path(p)
    sha(p)
    return json.loads(p.read_text())


def read_csv(p):
    p = path(p)
    sha(p)
    return pd.read_csv(p)


def check(kind, passed, identity, **detail):
    CHECKS[kind] += 1
    if not bool(passed):
        ERRORS.append({"check": kind, "identity": identity, **detail})


def near(kind, actual, expected, identity, scale=1):
    actual, expected = float(actual), float(expected)
    delta = abs(actual - expected)
    check(kind, np.isfinite(actual) and np.isfinite(expected) and delta <= TOL * scale,
          identity, actual=actual, expected=expected, absolute_error=delta)
    return delta


def monthly_values(times, values, initial):
    ends = {}
    for timestamp, value in zip(times, values):
        ends[str(timestamp)[:7]] = float(value)
    previous = float(initial)
    returns = {}
    for month, value in ends.items():
        returns[month] = value / previous - 1
        previous = value
    return returns


def saved_account(group, raw, identity):
    eq = read_csv(raw["equity_path"])
    trades = read_csv(raw["trades_path"])
    months = read_csv(raw["monthly_path"])
    timecol = "valuation_ts" if group == "ema" else "ts"
    eqcol = "equity_funding_estimate" if group == "ema" else "equity"
    initial = 10000.0 if group == "cc" else 1.0
    values = eq[eqcol].to_numpy(dtype=float)
    timestamps = pd.to_datetime(eq[timecol], utc=True)
    check("equity_finite_positive", np.isfinite(values).all() and (values > 0).all(), identity)
    check("valuation_time_nondecreasing", timestamps.is_monotonic_increasing, identity)
    check("last_valuation_equals_end", timestamps.iloc[-1] == pd.Timestamp(raw["end"]), identity)
    peak = np.maximum.accumulate(np.r_[initial, values])[1:]
    dd = values / peak - 1
    ret = values[-1] / initial - 1
    near("saved_drawdown_series", np.max(np.abs(dd - eq["drawdown"].to_numpy())), 0, identity)
    if "return" in eq:
        # This CSV column is the per-valuation change, not cumulative return.
        incremental = values / np.r_[initial, values[:-1]] - 1
        near("saved_incremental_return_series", np.max(np.abs(incremental - eq["return"].to_numpy())), 0, identity)
    ret_expected = raw["return_pct"] / 100 if group in ("ema", "cc") else raw["return"]
    dd_expected = (-1 if group == "cc" else 1) * raw["max_drawdown_pct"] / 100 if group in ("ema", "cc") else raw["max_drawdown"]
    near("raw_terminal_return", ret, ret_expected, identity)
    near("raw_closing_drawdown", dd.min(), dd_expected, identity)
    check("raw_trade_count", len(trades) == raw["trades"], identity, actual=len(trades), expected=raw["trades"])
    terminal = trades["exit_reason"].astype(str).str.startswith("terminal") if len(trades) else pd.Series([], dtype=bool)
    terminal_count = int(terminal.sum())
    check("raw_terminal_count", terminal_count == raw.get("terminal_closes", raw.get("terminal_trades", 0)), identity,
          actual=terminal_count, expected=raw.get("terminal_closes", raw.get("terminal_trades", 0)))
    # All original writers assign a closing bar to its opening month. EMA/AR
    # express this as close timestamp - 1ns; CC explicitly uses bar_open.
    # Keep the direct close-calendar calculation separately as sensitivity.
    month_calendar = monthly_values(timestamps, values, initial)
    month_times = timestamps - pd.Timedelta(nanoseconds=1)
    month_actual = monthly_values(month_times, values, initial)
    month_col = "return" if group == "ar_mmtf" else "return_pct"
    month_saved = {str(r["month"]): float(r[month_col]) / (1 if month_col == "return" else 100) for r in months.to_dict("records")}
    check("monthly_keys", list(month_actual) == list(month_saved), identity, actual=list(month_actual), expected=list(month_saved))
    for m, v in month_actual.items():
        if m in month_saved:
            near("monthly_return", v, month_saved[m], f"{identity}:{m}")
            calendar_delta = month_calendar[m] - month_saved[m]
            if abs(calendar_delta) > TOL:
                MONTH_SENSITIVITY.append({"group": group, "identity": identity, "month": m,
                    "funding_mode": raw.get("funding_mode", "observed_funding_estimate"),
                    "saved_bar_month_return": month_saved[m], "close_timestamp_calendar_return": month_calendar[m],
                    "difference_percentage_points": calendar_delta * 100})
    near("monthly_compounding", np.prod([1 + v for v in month_actual.values()]) - 1, ret, identity)

    fees = terminal_fees = 0.0
    if len(trades):
        qty = trades["quantity"].to_numpy()
        entryfill = trades["entry_fill" if group != "ar_mmtf" else "entry_price"].to_numpy()
        exitfill = trades["exit_fill" if group != "ar_mmtf" else "exit_price"].to_numpy()
        near("entry_fee_from_fill", np.max(np.abs(trades["entry_fee"] - abs(qty * entryfill) * .001)), 0, identity, initial)
        near("exit_fee_from_fill", np.max(np.abs(trades["exit_fee"] - abs(qty * exitfill) * .001)), 0, identity, initial)
        fees = float((trades["entry_fee"] + trades["exit_fee"]).sum())
        terminal_fees = float(trades.loc[terminal, "exit_fee"].sum())
        check("terminal_exit_fee_present", not terminal_count or (trades.loc[terminal, "exit_fee"] > 0).all(), identity)
        if group == "ar_mmtf":
            net = trades["price_pnl_after_slippage"] - trades["entry_fee"] - trades["exit_fee"] + trades["funding_estimate"]
            fee_expected = raw["cost_totals"]["entry_fee"] + raw["cost_totals"]["exit_fee"]
        else:
            net = trades["net_pnl"]
            fee_expected = raw["fee_quote"] if group == "cc" else raw["fees_initial_equity_pct"] / 100
            fundingcol = "funding_pnl" if group == "cc" else "observed_funding_estimate"
            direction = trades["direction"]
            independent_net = qty * direction * (exitfill - entryfill) - trades["entry_fee"] - trades["exit_fee"] + trades[fundingcol]
            near("trade_net_from_actual_fills", np.max(np.abs(net - independent_net)), 0, identity, initial)
        near("fee_total_matches_raw", fees, fee_expected, identity, initial)
        near("ledger_cash_terminal", initial + net.sum(), values[-1], identity, initial)
        near("last_trade_exit_equity", trades.iloc[-1]["exit_equity"], values[-1], identity, initial)
    else:
        near("flat_account_terminal", values[-1], initial, identity)
    result = {"initial_equity": initial, "equity_rows": len(eq), "trade_rows": len(trades),
              "first_valuation": str(timestamps.iloc[0]), "last_valuation": str(timestamps.iloc[-1]),
              "terminal_equity": float(values[-1]), "return": float(ret), "drawdown": float(dd.min()),
              "terminal_closes": terminal_count, "fees_initial_equity_fraction": fees / initial,
              "terminal_exit_fees_initial_equity_fraction": terminal_fees / initial,
              "monthly_return": month_actual}
    excol = "equity_excluding_funding"
    if excol in eq:
        ex = eq[excol].to_numpy()
        result["return_ex_funding"] = float(ex[-1] / initial - 1)
        result["drawdown_ex_funding"] = float((ex / np.maximum.accumulate(np.r_[initial, ex])[1:] - 1).min())
        result["monthly_return_ex_funding"] = monthly_values(month_times, ex, initial)
        exexpected = raw["return_excluding_funding_pct"] / 100 if group == "ema" else raw["return_excluding_funding"]
        near("raw_excluded_funding_terminal", result["return_ex_funding"], exexpected, identity)
        if "return_excluding_funding" in months:
            ex_calendar = monthly_values(timestamps, ex, initial)
            for row in months.to_dict("records"):
                near("monthly_excluded_funding", result["monthly_return_ex_funding"][row["month"]], row["return_excluding_funding"], f"{identity}:{row['month']}")
                calendar_delta = ex_calendar[row["month"]] - row["return_excluding_funding"]
                if abs(calendar_delta) > TOL:
                    MONTH_SENSITIVITY.append({"group": group, "identity": identity, "month": row["month"],
                        "funding_mode": "funding_excluded", "saved_bar_month_return": row["return_excluding_funding"],
                        "close_timestamp_calendar_return": ex_calendar[row["month"]], "difference_percentage_points": calendar_delta * 100})
        if group == "ar_mmtf" and len(trades):
            # With nonoverlapping positions the no-funding account compounds the
            # per-trade gross return; subtracting total funding from final equity
            # would incorrectly retain funding-driven future position sizes.
            near("excluded_funding_trade_compounding", np.prod(1 + trades["return_excluding_funding"]) - 1,
                 result["return_ex_funding"], identity)
    return result


def sign(x):
    return 1 if x > TOL else -1 if x < -TOL else 0


def main():
    OUT.mkdir(exist_ok=True)
    baseline = read_json(OUT / "archive_698_before_correction.json")
    manifest = read_json(OLD / "archive_sha256.json")
    check("historical_archive_manifest_identity", sha(OLD / "archive_sha256.json") == baseline["manifest_sha256"], "archive")
    check("historical_archive_snapshot_698_match", baseline["entries"] == baseline["matched"] == len(manifest["files"]) == 698 and not baseline["mismatches"], "archive")
    all_rows = read_json(OLD / "all_results.json")
    saved_pairs = read_json(OLD / "paired_results.json")
    saved_counts = read_json(OLD / "aggregate_counts.json")
    raw_groups = {g: read_json(OLD / g / "results.json") for g in ("ema", "ar_mmtf", "cc")}
    by_path = {g: {str(path(r["equity_path"])): r for r in rows} for g, rows in raw_groups.items()}
    plans = {g: read_json(OLD / g / "cases_plan.json") for g in raw_groups}
    plan_versions = {(r["family"], r["version"]) for g in ("ema", "ar_mmtf") for r in plans[g]["cases"]}
    plan_versions |= {("HYPE-CC", r["config"]["version"]) for r in plans["cc"]["plan"]["cases"]}
    for family, endpoints in ENDPOINTS.items():
        for version in endpoints:
            check("fixed_endpoint_in_original_plan", (family, version) in plan_versions, f"{family}:{version}")
    counts_by_group = dict(collections.Counter(r["group"] for r in all_rows))
    windows = dict(collections.Counter(r["window"] for r in all_rows))
    check("101_rows_and_group_counts", len(all_rows) == 101 and counts_by_group == {"ema": 27, "ar_mmtf": 54, "cc": 20}, "all_results", actual=counts_by_group)
    check("common_and_long_counts", windows == {"common": 96, "long": 5}, "all_results", actual=windows)
    identities = [(r["family"], r["version"], r["scenario"], r["window"]) for r in all_rows]
    check("unique_normalized_results", len(identities) == len(set(identities)), "all_results")
    reviewed = []
    cc_extra = []
    max_return_error = max_dd_error = max_ex_error = 0.0
    for r in all_rows:
        identity = "|".join(str(r[k]) for k in ("family", "version", "scenario", "window"))
        before_errors = len(ERRORS)
        try:
            raw = by_path[r["group"]][str(path(r["equity_path"]))]
            calc = saved_account(r["group"], raw, identity)
            if r["group"] == "cc":
                siblings = [x for x in raw_groups["cc"] if x["case_id"] == raw["case_id"] and x["funding_mode"] == "funding_excluded"]
                check("unique_cc_no_funding_sibling", len(siblings) == 1, identity)
                extra = saved_account("cc", siblings[0], identity + "|funding_excluded")
                cc_extra.append({"identity": identity, "equity_path": siblings[0]["equity_path"], **extra})
                calc["return_ex_funding"] = extra["return"]
                calc["drawdown_ex_funding"] = extra["drawdown"]
                calc["monthly_return_ex_funding"] = extra["monthly_return"]
            max_return_error = max(max_return_error, near("normalized_return", calc["return"], r["return"], identity))
            max_dd_error = max(max_dd_error, near("normalized_drawdown", calc["drawdown"], r["drawdown"], identity))
            max_ex_error = max(max_ex_error, near("normalized_excluded_funding_return", calc["return_ex_funding"], r["return_ex_funding"], identity))
            check("normalized_trade_count", calc["trade_rows"] == r["trades"], identity)
            check("normalized_terminal_count", calc["terminal_closes"] == r["terminal_closes"], identity)
            reviewed.append({**r, "calculated": calc, "status": "PASS" if len(ERRORS) == before_errors else "FAIL"})
        except Exception as exc:
            ERRORS.append({"check": "read_and_recompute_exception", "identity": identity, "error": repr(exc)})
            reviewed.append({**r, "status": "ERROR"})

    calculated_index = {(r["family"], r["version"], r["scenario"], r["window"]): r for r in reviewed if "calculated" in r}
    paired_index = {p["family"]: p for p in saved_pairs}
    check("14_fixed_pair_families", len(saved_pairs) == 14 and set(paired_index) == set(ENDPOINTS), "pairs")
    pairs = []
    for family, (early, final) in ENDPOINTS.items():
        try:
            a = calculated_index[(family, early, "equal_1x_base", "common")]
            b = calculated_index[(family, final, "equal_1x_base", "common")]
            p = paired_index[family]
            check("fixed_pair_identity", (p["early_version"], p["final_version"]) == (early, final), family)
            actual = {"early_return": a["calculated"]["return"], "final_return": b["calculated"]["return"],
                      "early_return_ex_funding": a["calculated"]["return_ex_funding"], "final_return_ex_funding": b["calculated"]["return_ex_funding"],
                      "early_drawdown": a["calculated"]["drawdown"], "final_drawdown": b["calculated"]["drawdown"],
                      "early_trades": a["calculated"]["trade_rows"], "final_trades": b["calculated"]["trade_rows"]}
            actual["increment"] = actual["final_return"] - actual["early_return"]
            actual["increment_ex_funding"] = actual["final_return_ex_funding"] - actual["early_return_ex_funding"]
            for k, value in actual.items():
                near("paired_value", value, p[k], f"{family}:{k}")
            pairs.append({"family": family, "early_version": early, "final_version": final, **actual,
                          "increment_sign": sign(actual["increment"]), "increment_ex_funding_sign": sign(actual["increment_ex_funding"])})
        except Exception as exc:
            ERRORS.append({"check": "pair_recompute_exception", "identity": family, "error": repr(exc)})
    counts = {"families": len(pairs), "result_rows": len(all_rows),
              "final_higher": sum(p["increment_sign"] > 0 for p in pairs),
              "final_lower": sum(p["increment_sign"] < 0 for p in pairs),
              "equal": sum(p["increment_sign"] == 0 for p in pairs),
              "final_positive": sum(p["final_return"] > TOL for p in pairs),
              "early_positive": sum(p["early_return"] > TOL for p in pairs),
              "funding_changes_increment_sign": [p["family"] for p in pairs if p["increment_sign"] != p["increment_ex_funding_sign"]]}
    check("aggregate_counts_recomputed", counts == saved_counts, "counts", actual=counts, expected=saved_counts)
    check("7_higher_6_lower_1_equal", (counts["final_higher"], counts["final_lower"], counts["equal"]) == (7, 6, 1), "counts")
    rankings = {}
    for scenario in SCENARIOS:
        chosen = [calculated_index[(family, versions[1], scenario, "common")] for family, versions in ENDPOINTS.items()
                  if (family, versions[1], scenario, "common") in calculated_index]
        check("ranking_14_final_versions", len(chosen) == 14 and all(r["role"] == "final" for r in chosen), scenario)
        for funding in ("return", "return_ex_funding"):
            ranked = sorted(chosen, key=lambda x: (-x["calculated"][funding], x["family"]))
            output = []
            for i, r in enumerate(ranked):
                c = r["calculated"]
                rank = 1 + sum(x["calculated"][funding] > c[funding] + TOL for x in ranked)
                output.append({"rank": rank, "family": r["family"], "name": r["name"], "version": r["version"],
                               "return": c[funding], "return_pct": c[funding] * 100,
                               "drawdown": c["drawdown" if funding == "return" else "drawdown_ex_funding"],
                               "trades": c["trade_rows"]})
            rankings[f"{scenario}__{'observed_funding_estimate' if funding == 'return' else 'funding_excluded'}"] = output

    # Read what previous independent checks actually claimed, preserving their
    # declarations rather than interpreting PASS as a comprehensive endorsement.
    audit_scopes = {}
    coverage = {
        "ema": {"normalized_rows": 27, "previous_checks": "Independent features/spec mapping plus saved ledgers, fees, funding estimates, months and four predefined endpoints; nine saved prefix reports inspected, not rerun.",
                "not_covered": ["Complete independent cold strategy replay", "Historical training-sample returns/original-code parity", "Complete funding or exact intrabar execution", "Statistical overfitting attribution", "Cross-family research priority language"]},
        "ar_mmtf": {"normalized_rows": 54, "previous_checks": "Original spec/source parameters, 15m RVOL96 and 1h RVOL48, TRX V3 delay, saved V2/V1 equivalence evidence, 366 saved ledger rows, costs, months and closing equity.",
                    "not_covered": ["Complete independent replay of all 54 scenarios", "Original Keltner complete 1m input identity", "An observed forced terminal-close example: all 54 accounts end flat", "Complete funding or exact intrabar execution", "Statistical overfitting attribution", "Cross-family research priority language"]},
        "cc": {"normalized_rows": 20, "previous_checks": "Five source specs and independently calculated input features; 40 saved funding-branch runs, 1706 trades and 3679 funding rows reconstructed, including quantity/equity/months.",
               "not_covered": ["Complete independent cold scenario replay", "Equivalence to original close-fill/implicit-rebalance engines", "Complete funding/native marks or exact intrabar execution", "Statistical overfitting attribution", "Cross-family research priority language"]},
    }
    for g in ("ema", "ar_mmtf", "cc"):
        p = OLD / f"acceptance_{g}_independent.json"
        d = read_json(p)
        audit_scopes[g] = {"path": str(p.relative_to(ROOT)), "sha256": sha(p), "historical_status": d["status"],
                           "declared_scope": d["scope"], "declared_limitations": d.get("limitations", d.get("warnings", [])),
                           "recorded_top_level_checks": len(d.get("checks", [])), **coverage[g]}
    aggregate = read_json(OLD / "acceptance_aggregate.json")
    audit_scopes["aggregate"] = {"historical_status": aggregate["status"], "recorded_checks": aggregate["check_count"],
                                  "coverage": "101 normalized summary identities, fixed 14 endpoints, saved final equity/closing drawdown/trade counts; a packaging/arithmetic check, not another full strategy replay.",
                                  "declared_limitations": aggregate["warnings"]}

    monthly_summary = {}
    for group in ("ema", "ar_mmtf", "cc"):
        affected = [r for r in MONTH_SENSITIVITY if r["group"] == group]
        monthly_summary[group] = {"differing_month_cells": len(affected),
            "affected_saved_accounts": len({r["identity"] for r in affected}),
            "maximum_absolute_difference_percentage_points": max([abs(r["difference_percentage_points"]) for r in affected], default=0),
            "families": sorted({r["identity"].split("|")[0] for r in affected})}
    monthly_sources = {
        "ema": {"path": str((FAMILY / "scripts/compare_ema_versions.py").relative_to(ROOT)), "line": 251, "definition": "ret.index minus 1 nanosecond"},
        "ar_mmtf": {"path": str((FAMILY / "scripts/compare_ar_mmtf_versions.py").relative_to(ROOT)), "line": 346, "definition": "curve.ts minus 1 nanosecond"},
        "cc": {"path": str((FAMILY / "scripts/compare_cc_versions.py").relative_to(ROOT)), "line": 435, "definition": "bar_open calendar month"}}
    for item in monthly_sources.values():
        item["sha256"] = sha(item["path"])

    # Re-check all read historical artifacts against the archive. Documentation
    # deliberately edited after the timestamped 698/698 snapshot is not read here.
    archive_index = {x["path"]: x["sha256"] for x in manifest["files"]}
    checked_historical = 0
    for p, h in list(READ_HASHES.items()):
        if p in archive_index:
            checked_historical += 1
            check("current_read_artifact_matches_historical_archive", h == archive_index[p], p,
                  actual_sha256=h, expected_sha256=archive_index[p])
    result = {"status": "PASS_WITH_DECLARED_SCOPE_LIMITS" if not ERRORS else "FAIL",
              "checked_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "review_kind": "New read-only saved-artifact numeric and conclusion-table review; zero strategy reruns; old acceptance files preserved.",
              "units": "Returns and drawdowns are fractions of initial equity; drawdowns negative; ranking return_pct is percentage. Equality tolerance 1e-9 fraction.",
              "historical_archive_before_authorized_corrections": baseline,
              "historical_artifacts_read_and_rehashed_now": checked_historical,
              "row_coverage": {"normalized_rows": len(reviewed), "groups": counts_by_group, "windows": windows,
                               "additional_cc_no_funding_accounts": len(cc_extra), "unique_saved_accounts_recomputed": len(reviewed) + len(cc_extra),
                               "equity_rows": sum(x["calculated"]["equity_rows"] for x in reviewed if "calculated" in x) + sum(x["equity_rows"] for x in cc_extra),
                               "trade_rows": sum(x["calculated"]["trade_rows"] for x in reviewed if "calculated" in x) + sum(x["trade_rows"] for x in cc_extra)},
              "maximum_absolute_error": {"return": max_return_error, "drawdown": max_dd_error, "return_ex_funding": max_ex_error},
              "counts_from_csv": counts, "fixed_primary_pairs_from_csv": pairs, "final_version_rankings_from_csv": rankings,
              "monthly_boundary_convention_review": {"status": "RECONCILED_TO_ORIGINAL_WRITERS_NOT_A_TOTAL_ACCOUNT_ERROR",
                  "actual_convention": "All three groups assign the month's last closed bar to that bar's opening month. Close timestamp exactly at next month's 00:00 belongs to preceding bar month.",
                  "reviewer_initial_schema_corrections": ["CSV return is per-valuation return, not cumulative return.", "Direct valuation timestamp calendar month differs from the original writers' closed-bar month assignment. Both calculations retained below; original artifacts unchanged."],
                  "sources": monthly_sources, "summary_by_group": monthly_summary,
                  "sensitivity_definition": "Alternative close-timestamp calendar month minus saved bar-opening month; percentage points. Funding modes separately counted when a separate saved monthly CSV/column exists.",
                  "terminal_return_unchanged": True, "differences": MONTH_SENSITIVITY},
              "previous_independent_acceptance_scopes": audit_scopes,
              "limits_of_this_review": ["Recomputes saved CSV arithmetic; does not generate signals or search/replay strategies.",
                                       "Profit ranking uses only 14 predefined final versions in the common July23 to September5 15:00 UTC window; it excludes early/milestone versions and the five CC long-window rows.",
                                       "Basis fee is 0.1% per fill, slippage 0.04% per fill; stress slippage 0.08%. Entry 1x is actual traded notional, not equal stop-loss risk.",
                                       "All funding-inclusive results are incomplete observed-event estimates with differing family event/notional assumptions, not verified complete net profit.",
                                       "Drawdown is sampled closing equity, not maximum intrabar loss or liquidation evidence.",
                                       "Numeric/spec acceptance did not audit narrative research priority and does not prove or disprove overfitting."],
              "checks_by_kind": dict(CHECKS), "error_count": len(ERRORS), "errors": ERRORS,
              "rows": reviewed, "additional_cc_funding_excluded_accounts": cc_extra,
              "read_artifacts_sha256": READ_HASHES, "review_script_sha256": sha(Path(__file__))}
    dest = OUT / "numeric_iteration_independent.json"
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "error_count": len(ERRORS), "errors": ERRORS[:20],
                      "coverage": result["row_coverage"], "counts": counts,
                      "top_three_each_ranking": {k: v[:3] for k, v in rankings.items()}, "output": str(dest)}, ensure_ascii=False, indent=2))
    return int(bool(ERRORS))


if __name__ == "__main__":
    raise SystemExit(main())
