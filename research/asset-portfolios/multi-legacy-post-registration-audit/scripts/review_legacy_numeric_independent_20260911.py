"""Read archived summaries/ledgers only; does not execute any strategy engine."""
from pathlib import Path
import json
import math
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
FAMILY = Path(__file__).resolve().parents[1]
A = FAMILY / "artifacts"
OUT = A / "conclusion_review_20260911"
TOL = 2e-10


def read(path):
    return json.loads(Path(path).read_text())


def path(value):
    p = Path(value)
    return p if p.is_absolute() else ROOT / p


def csv(p):
    try:
        return pd.read_csv(p)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def same(a, b):
    return abs(float(a) - float(b)) <= TOL


def main():
    rows = read(A / "all_results.json")
    table = pd.read_csv(A / "all_results.csv").set_index("name")
    inventory = read(A / "coverage_inventory.json")["rows"]
    legacy = read(A / "hype_legacy/summary.json")
    others = read(A / "other_assets/results.json")
    extra = read(A / "other_assets/supplemental_results.json")
    as6s = read(A / "other_assets/AS6S_V6/results.json")["results"]
    report = (FAMILY / "diagnostics/report-20260910.md").read_text()
    checks, issues = [], []
    for r in rows:
        ep = path(r["equity_path"])
        tp = ep.with_name(ep.name.replace("equity", "trades"))
        mp = ep.with_name(ep.name.replace("equity", "monthly"))
        ef, tf, mf = csv(ep), csv(tp), csv(mp)
        source_file = path(r["source"])
        source = read(source_file)
        expected = {}
        conservative = None
        if "hype_legacy" in str(source_file):
            source = next(x for x in legacy if path(x["equity_file"]) == ep)
            expected = dict(return_value=source["return_pct"] / 100,
                            drawdown=source["max_drawdown_pct"] / 100,
                            trades=source["natural_closed_trades"] + source.get("terminal_marks", 0))
        elif source_file == A / "other_assets/results.json":
            source = next(x for x in others if x["asset"] == ep.parent.name and x["scenario"] == "base")
            conservative = source["legacy_engine_conservative_mae_drawdown"]
            expected = dict(return_value=source["return"], drawdown=min(source["close_marked_max_drawdown"], conservative), trades=source["trade_count"])
        elif "hype_other" in str(source_file):
            metrics = source.get("metrics", {})
            conservative = metrics.get("max_dd") if ep.parent.name == "ar_v4" else None
            expected = dict(return_value=source["curve_return"], drawdown=min(source["curve_close_drawdown"], conservative if conservative is not None else 0),
                            trades=metrics.get("trades", metrics.get("campaigns", metrics.get("directional_entries", len(tf)))))
        elif "AS6S_V6" in str(source_file):
            source = next(x for x in as6s if x["scenario"] == "base" and ep.name == x["route"] + "_base_equity.csv")
            conservative = source["legacy_mae_drawdown"]
            expected = dict(return_value=source["return"], drawdown=min(source["close_marked_max_drawdown"], conservative), trades=source["trades"])
        elif "ensemble" in str(source_file):
            expected = dict(return_value=source["return"], drawdown=source["max_drawdown"], trades=source["trades"])
        else:
            source = next(x for x in extra if path(x["equity_path"]) == ep and x.get("scenario", "base") == "base")
            expected = dict(return_value=source["return"], drawdown=source["drawdown"], trades=source["trades"])

        tc = "ts" if "ts" in ef else ef.columns[0]
        ec = next(c for c in ("equity", "net_equity", "equity_net") if c in ef)
        values = pd.to_numeric(ef[ec]).to_numpy()
        raw_times = pd.to_datetime(ef[tc], utc=True)
        times = raw_times.copy()
        semantics = r.get("equity_timestamp_semantics", {})
        end = pd.Timestamp(source.get("end", source.get("end_exclusive", r.get("end", "2026-09-05T15:00:00Z")))).tz_convert("UTC")
        if semantics.get("label") == "bar_open":
            delta = pd.Timedelta(minutes=semantics["bar_duration_minutes"])
            times = times.map(lambda t: min(t + delta, end))
        series = pd.Series(values, index=times).sort_index()
        series = series[~series.index.duplicated(keep="last")]
        start = pd.Timestamp(r["start"])
        series = series[series.index >= start]
        close_dd = float(np.min(values / np.maximum.accumulate(np.maximum(values, 1.0)) - 1))
        inferred_dd = min(close_dd, conservative) if conservative is not None else close_dd
        cut = start + pd.Timedelta(days=30)
        first = series[series.index <= cut]
        first30 = float(first.iloc[-1] - 1)
        after30 = float(series.iloc[-1] / first.iloc[-1] - 1) if series.index[-1] > cut else None
        aug = series[series.index <= pd.Timestamp("2026-09-01T00:00:00Z")]
        jul = series[series.index <= pd.Timestamp("2026-08-01T00:00:00Z")]
        august = float(aug.iloc[-1] / (jul.iloc[-1] if len(jul) else 1) - 1)

        actual_count = len(tf)
        count_unit = "closed_trade_or_campaign_rows"
        if "mhef_1h" in str(ep):
            signs = np.sign(tf["position"].to_numpy())
            actual_count = int(np.sum((signs != 0) & (signs != np.r_[0, signs[:-1]])))
            count_unit = "directional_entries; CSV rows are rebalance fills"
        # Five supplementary paths are serialized at the first interval's end.
        # The exporter explicitly shifts BTC timestamps and uses frame.ts[1:]
        # for SOL RS4. This is not a later replay start.
        first_offset_minutes = float((raw_times.iloc[0] - start).total_seconds() / 60)
        allowed_offset = 0
        if source_file.name == "frozen_contract.json" and "SOL_1H" not in str(source_file):
            allowed_offset = {"15m": 15, "30m": 30, "4h": 240}.get(r.get("timeframe"), 0)
        flags = {
            "json_csv_equal": all(same(table.loc[r["name"], k], r[k]) for k in ("return", "drawdown", "trades", "first30_return", "august_return")),
            "summary_equal": same(expected["return_value"], r["return"]) and same(expected["drawdown"], r["drawdown"]) and expected["trades"] == r["trades"],
            "summary_start_equal": pd.Timestamp(source["start"]) == start,
            "equity_return_equal": same(values[-1] - 1, r["return"]),
            "drawdown_equal_under_declared_measure": same(inferred_dd, r["drawdown"]),
            "trade_count_equal_under_declared_unit": actual_count == r["trades"],
            "first30_equal": same(first30, r["first30_return"]),
            "after30_equal": (after30 is None and r["after30_return"] is None) or (after30 is not None and r["after30_return"] is not None and same(after30, r["after30_return"])),
            "august_equal": same(august, r["august_return"]),
            "curve_start_matches_exporter_time_semantics": first_offset_minutes == allowed_offset,
            "curve_ends_on_declared_end": series.index[-1] == end,
            "report_rounded_row_present": f"| {r['name']} | {str(r['start'])[:10]} | {100*r['return']:+.2f}% | {abs(100*r['drawdown']):.2f}% |" in report,
        }
        monthly_values = pd.to_numeric(mf["return"]).to_numpy() / (100 if "hype_legacy" in str(ep) else 1)
        flags["monthly_compound_equals_final"] = same(np.prod(1 + monthly_values) - 1, r["return"])
        monthly_errors = []
        monthly_labels = mf["month"] if "month" in mf else pd.to_datetime(mf.iloc[:, 0], utc=True).dt.strftime("%Y-%m")
        previous = 1.0
        for label, actual in zip(monthly_labels, monthly_values):
            boundary = (pd.Timestamp(str(label) + "-01", tz="UTC") + pd.offsets.MonthBegin(1))
            before = series[series.index <= boundary]
            value = float(before.iloc[-1])
            monthly_errors.append(abs(value / previous - 1 - actual))
            previous = value
        flags["monthly_boundaries_match_curve"] = max(monthly_errors, default=0) <= TOL
        for key in ("entry_ts", "signal_ts"):
            if key in tf and len(tf):
                flags[key + "_not_before_start"] = bool((pd.to_datetime(tf[key], utc=True) >= start).all())
        if "exit_ts" in tf and len(tf):
            flags["exit_not_after_end"] = bool((pd.to_datetime(tf["exit_ts"], utc=True) <= end).all())
        # These serialized single-position account returns have an unambiguous product.
        if "equity_ret" in tf:
            flags["trade_account_return_compound"] = same(np.prod(1 + tf["equity_ret"].to_numpy()) - 1, r["return"])
        inv = next((x for x in inventory if ep.parent.name in x.get("cases", [])), None)
        if inv and inv.get("replay_from_next_utc_day"):
            flags["inventory_date_start_equal"] = start == pd.Timestamp(inv["freeze_date"], tz="UTC") + pd.Timedelta(days=1)
        if "registration" in source:
            registration = pd.Timestamp(source["registration"])
            registration = registration.tz_localize("UTC") if registration.tzinfo is None else registration
            expected_start = registration + pd.Timedelta(days=1) if len(source["registration"]) == 10 else registration.ceil("15min")
            flags["registration_start_equal"] = start == expected_start
        flags = {key: bool(value) for key, value in flags.items()}
        failures = [key for key, passed in flags.items() if not passed]
        check = dict(name=r["name"], family=r["family"], primary=r["primary"], registered=r["registered"], return_value=r["return"],
                     drawdown=r["drawdown"], curve_close_drawdown=close_dd, source_conservative_drawdown=conservative,
                     trades=r["trades"], raw_trade_csv_rows=len(tf), count_unit=count_unit,
                     start=str(start), end=str(end), first_curve_offset_minutes=first_offset_minutes, equity_path=str(ep.relative_to(ROOT)), trades_path=str(tp.relative_to(ROOT)),
                     monthly_path=str(mp.relative_to(ROOT)), source_path=str(source_file.relative_to(ROOT)), checks=flags, failures=failures)
        checks.append(check)
        issues.extend(dict(name=r["name"], check=f) for f in failures)
    mainrows = [r for r in rows if r["primary"]]
    ranked = sorted(rows, key=lambda r: r["return"], reverse=True)
    result = dict(scope="Archived numeric correspondence only; no strategy rerun and no full original-implementation or data-completeness acceptance.",
                  status="NUMERIC_CORRESPONDENCE_ISSUES" if issues else "NUMERIC_CORRESPONDENCE_CHECKS_PASS_WITH_KNOWN_RULE_AND_INTERPRETATION_LIMITATIONS",
                  counts=dict(rows=len(rows), families=len(set(r["family"] for r in rows)), primary=len(mainrows), registered_flag=sum(r["registered"] for r in rows),
                              primary_positive=sum(r["return"] > TOL for r in mainrows), primary_negative=sum(r["return"] < -TOL for r in mainrows), primary_zero=sum(abs(r["return"]) <= TOL for r in mainrows)),
                  top_raw_cumulative_returns=[dict(rank=i+1, name=r["name"], return_value=r["return"], drawdown=r["drawdown"], start=r["start"], trades=r["trades"], primary=r["primary"]) for i,r in enumerate(ranked[:5])],
                  issues=issues, rows=checks,
                  material_findings=[
                      "Keltner V3 is rank 1 by raw cumulative return among both primary 16 and all 45 rows; windows/costs/size differ, so this is not a fair cross-strategy ranking.",
                      "Original primary main table has 16 rows; 18 rows carry registered=true because two AS6S routes are in the appendix. Main-table title implying complete registered coverage is imprecise.",
                      "The recommendation prioritizing MII/MHEF was an interpretation without a predeclared common selection objective, not an established superiority result.",
                      "Known 15m MMTF RVOL48-vs-spec96 defect means parameter identity was not preserved even though old arithmetic agrees. Corrected original-model return is -0.14153566672164397, versus -0.1421911958492844 archived.",
                      "Known CC old entry/early-exit timing ambiguity remains; arithmetic correspondence does not establish exact source-rule reproduction.",
                      "Eight AR/AS6S rows use source conservative intratrade MAE drawdown as well as curve drawdown; other rows predominantly use close-marked equity. Drawdowns are not one uniform measure.",
                      "Two MHEF rows count 20 directional entries each but their CSVs contain 1264 and 196 rebalance fills, respectively. Forty-five rows are not forty-five independent strategies.",
                      "Old acceptance explicitly covered aggregate/source-artifact arithmetic and presentation; it cannot justify universal original-engine correctness or causal overfitting claims."
                  ],
                  not_checked=["All 45 original engines' signal/feature/exit/sizing implementation", "Independent full funding settlement ledger", "Market data continuity and historical instrument identity", "Every original registration timestamp or complete git lineage", "All strategies' cash-flow reconstruction from fills"])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "numeric_legacy_independent.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(dict(status=result["status"], counts=result["counts"], issues=issues), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
