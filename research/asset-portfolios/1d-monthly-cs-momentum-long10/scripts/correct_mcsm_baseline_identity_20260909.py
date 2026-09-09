"""Fix two confirmed identity inputs using frozen ranks, preserving original artifacts."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
LAB = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(FAMILY / "scripts"))

import build_mcsm_baseline_inputs_20260909 as base  # noqa: E402

OLD = FAMILY / "artifacts/baseline-estimate-20260909/inputs"
OUT = OLD.parent / "inputs-identity-corrected"


def verified_saved_execution(month: pd.Timestamp, receipts: list) -> pd.DataFrame:
    path = OLD / "receipts" / f"execution-{month:%Y%m}.json"
    receipt = json.loads(path.read_text())
    for role in ("request", "frame"):
        assert base.sha(OLD / receipt[f"{role}_path"]) == receipt[f"{role}_sha256"]
    assert receipt["status"] == "EXPLORATORY_SCOPED_EQUIVALENT_AUDIT"
    receipts.append({"receipt_path": str(path.relative_to(FAMILY)), "receipt_sha256": base.sha(path),
                     "frame_path": receipt["frame_path"], "frame_sha256": receipt["frame_sha256"]})
    return pd.read_parquet(OLD / receipt["frame_path"])


def main() -> None:
    plan_path = OUT / "identity-correction.json"
    plan = json.loads(plan_path.read_text())
    old_summary = json.loads((OLD / "summary.json").read_text())
    for filename, expected in old_summary["files"].items():
        assert base.sha(OLD / filename) == expected, filename
    assert base.sha(OLD / "holdings.parquet") == plan["parent_holdings_sha256"]
    assert base.sha(OLD / "ranked-candidates.parquet") == plan["parent_ranked_candidates_sha256"]
    catalog = json.loads((OLD / "catalog-receipt.json").read_text())
    assert base.sha(OLD / "catalog-receipt.json") == old_summary["catalog_receipt_sha256"]
    assert catalog["status"] == "EXPLORATORY_SCOPED_EQUIVALENT_AUDIT"
    identity_path = OLD / "selection-appendix/identity-sources/summary.json"
    identity = json.loads(identity_path.read_text())
    for source in identity["sources"]:
        assert base.sha(FAMILY / source["cms_path"]) == source["cms_sha256"]
    original = pd.read_parquet(OLD / "holdings.parquet")
    h = original.copy()
    ranked = pd.read_parquet(OLD / "ranked-candidates.parquet")
    decisions = pd.read_csv(OLD / "selection-decisions.csv")
    receipts = []
    replacements = []
    formation_requests = []
    for change in plan["corrections"]:
        month = pd.Timestamp(change["month"])
        symbol = change["replacement_symbol"]
        old_symbol = change["excluded_symbol"]
        candidate = ranked.loc[ranked.month.eq(month) & ranked.symbol.eq(symbol)].iloc[0]
        assert candidate["rank"] == change["replacement_original_rank"]
        decision = decisions.loc[pd.to_datetime(decisions.month, utc=True).eq(month) & decisions.symbol.eq(symbol)].iloc[0]
        assert decision.reason == "BELOW_FIRST_TEN_ELIGIBLE" and bool(decision.prior_activity_valid) and bool(decision.entry_open_available)
        entry_frame = verified_saved_execution(month, receipts)
        exit_month = month + pd.offsets.MonthBegin(1)
        exit_frame = verified_saved_execution(exit_month, receipts)
        def reference(frame, time):
            prior = frame.loc[frame.symbol.eq(symbol) & frame.ts.eq(time)].iloc[0]
            current = frame.loc[frame.symbol.eq(symbol) & frame.ts.eq(time + pd.Timedelta(minutes=15))].iloc[0]
            assert bool(prior.research_window_valid) and bool(prior.eligible) and current.open > 0
            return float(current.open)
        entry, exit_price = reference(entry_frame, month), reference(exit_frame, exit_month)
        indices = h.index[h.month.eq(month) & h.symbol.eq(old_symbol)]
        assert len(indices) == 1 and not ((h.month == month) & (h.symbol == symbol)).any()
        idx = indices[0]
        for column in candidate.index:
            h.loc[idx, column] = candidate[column]
        h.loc[idx, "entry_price"] = entry
        h.loc[idx, "exit_price"] = exit_price
        h.loc[idx, "entry_prior_activity_valid"] = True
        h.loc[idx, "identity_proven"] = False
        assert not h.loc[idx, "terminal"]
        replacements.append({"month": month, "symbol": symbol, "entry_ts": h.loc[idx, "entry_ts"],
                             "exit_ts": h.loc[idx, "exit_ts"], "entry_price": entry, "exit_price": exit_price,
                             "rank": int(candidate["rank"]), "replaced": old_symbol})
        formation_requests.append(base.request([symbol], candidate.formation_start_day + pd.Timedelta(hours=23, minutes=45), month))
    removed_keys = {(pd.Timestamp(c["month"]), c["excluded_symbol"]) for c in plan["corrections"]}
    unchanged = original.loc[[tuple(row) not in removed_keys for row in original[["month", "symbol"]].itertuples(index=False, name=None)]]
    actual_unchanged = h.loc[unchanged.index]
    pd.testing.assert_frame_equal(unchanged, actual_unchanged)
    assert len(unchanged) == 758 and len(h) == 760 and h.groupby("month").size().eq(10).all()
    base.save(OUT / "formation-requests-frozen.json", {"requests": formation_requests, "plan_sha256": base.sha(plan_path)})
    base.save(OUT / "parent-input-receipts.json", {"receipts": receipts, "parent_summary_sha256": base.sha(OLD / "summary.json"),
              "parent_catalog_sha256": base.sha(OLD / "catalog-receipt.json"), "identity_evidence_sha256": base.sha(identity_path)})
    old_exec = pd.read_parquet(OLD / "monthly_execution_prices.parquet")
    lookup = old_exec.set_index(["ts", "symbol"])
    execution = []
    previous = set()
    for month in list(sorted(h.month.unique())) + [pd.Timestamp("2026-07-01", tz="UTC")]:
        current = set(h.loc[h.month.eq(month), "symbol"])
        time = month + pd.Timedelta(minutes=15)
        absent = sorted((previous | current) - set(lookup.loc[time].index))
        frame = verified_saved_execution(month, receipts) if absent else None
        for symbol in sorted(previous | current):
            if (time, symbol) in lookup.index:
                row = lookup.loc[(time, symbol)].to_dict()
            else:
                prior = frame.loc[frame.symbol.eq(symbol) & frame.ts.eq(month)].iloc[0]
                now = frame.loc[frame.symbol.eq(symbol) & frame.ts.eq(time)].iloc[0]
                assert prior.research_window_valid and now.open > 0
                row = {"price": float(now.open), "prior_activity_valid": True, "already_terminal": False}
            row.update({"ts": time, "symbol": symbol, "selected_new": symbol in current, "held_old": symbol in previous})
            execution.append(row)
        previous = current
    e = pd.DataFrame(execution)[old_exec.columns]
    assert not e.duplicated(["ts", "symbol"]).any()
    assert e.loc[e.ts.eq(pd.Timestamp("2025-05-01T00:15Z")) & e.symbol.eq("LAYER/USDT:USDT"), ["selected_new", "held_old"]].all().all()
    h.to_parquet(OUT / "holdings.parquet", index=False, compression="zstd")
    e.to_parquet(OUT / "monthly_execution_prices.parquet", index=False, compression="zstd")
    e.to_parquet(OUT / "execution.parquet", index=False, compression="zstd")
    base.save(OUT / "replacements.json", json.loads(pd.DataFrame(replacements).to_json(orient="records", date_format="iso")))
    print("HOLDINGS_READY " + str(OUT / "holdings.parquet") + " SHA256 " + base.sha(OUT / "holdings.parquet"), flush=True)
    # New requests were frozen before this supplemental lake access. Full strict audit once,
    # followed only by two bounded reads against its verified file list.
    bundle, _ = base.read_bundle_contract(LAB, pin=base.PIN)
    verified = base.verify_bundle_files(bundle, data_root=LAB / "data")
    lake = LAB / "data"
    layout = base.DataLakeLayout(root_dir=lake, raw_dir=lake / "raw", normalized_dir=lake / "normalized",
                                features_dir=lake / "features", cache_dir=lake / "cache", derived_dir=lake / "derived")
    audit_start = pd.Timestamp(formation_requests[0]["start"])
    audit_end = pd.Timestamp(formation_requests[-1]["end"])
    loaded = base.require_passing_trusted(base.load_trusted_research_dataset(
        "binance.perp.ohlcv.15m.history.v3", layout=layout, requested_scope=base.DatasetScope.FULL_MARKET,
        start=audit_start, end=audit_end, gap_policy="contiguous_segments", max_materialize_rows=0))
    base.save(OUT / "catalog-receipt.json", {"status": "EXPLORATORY_SCOPED_EQUIVALENT_AUDIT",
              "start": audit_start, "end": audit_end, "verified_components": verified,
              "audit": loaded.audit, "coverage": loaded.coverage, "startup_api_pass_claimed": False})
    formation_qa = []
    base.OUT = OUT
    for req in formation_requests:
        a, b = pd.Timestamp(req["start"]), pd.Timestamp(req["end"])
        assert audit_start <= a < b <= audit_end
        symbol = req["symbols"][0]
        frame, receipt = base.scoped_read(loaded, req, "formation-" + symbol.split("/")[0])
        expected = pd.date_range(a, b, freq="15min", inclusive="left")
        missing = expected.difference(frame.ts)
        qa = {"symbol": symbol, "formation_end": b, "rows": len(frame), "expected_rows": len(expected),
              "missing_bars": len(missing), "ineligible_bars": int((~frame.eligible).sum()),
              "segments": int(frame.research_segment_id.nunique()), "frame_sha256": receipt["frame_sha256"]}
        assert len(frame) == len(expected) and len(missing) == 0 and frame.eligible.all() and qa["segments"] == 1, qa
        formation_qa.append(qa)
    base.save(OUT / "formation-qa.json", {"status": "TWO_REPLACEMENT_FORMATIONS_SINGLE_COMPLETE_ELIGIBLE_SEGMENT", "checks": formation_qa,
              "full_pit_identity_certification": False, "scope": "No observed interruption, inactive endpoint, or relaunch boundary within these two formation intervals; full-market identity certification remains unavailable."})
    base.save(OUT / "summary.json", {"status": "EXPLORE_UNTRUSTED_BASELINE_IDENTITY_INPUTS_CORRECTED", "months": 76,
              "holdings": 760, "unique_symbols": int(h.symbol.nunique()), "other_asset_months_unchanged": 758,
              "missing_nonterminal_exit_prices": int(h.loc[~h.terminal].exit_price.isna().sum()),
              "terminal_holdings": json.loads(h.loc[h.terminal].to_json(orient="records", date_format="iso")),
              "daily_source_sha256": old_summary["daily_source_sha256"], "source_status": "EXPLORATORY_SCOPED_EQUIVALENT_AUDIT",
              "source_script_sha256": base.sha(Path(__file__)), "catalog_receipt_sha256": base.sha(OUT / "catalog-receipt.json"),
              "entry_activity_uses_only_prior_closed_bar": True, "selection_uses_future_survival": False,
              "net_inputs_verified": False, "pit_universe_proven": False, "tradability_proven": False,
              "new_performance_computed": False, "replacement_formations_complete": True,
              "files": {**{p.name: base.sha(p) for p in OUT.iterdir() if p.is_file()},
                        "../inputs/daily-original-buckets.parquet": old_summary["files"]["daily-original-buckets.parquet"],
                        "../inputs/summary.json": base.sha(OLD / "summary.json")}})
    assert base.sha(OLD / "holdings.parquet") == plan["parent_holdings_sha256"]
    print("IDENTITY_CORRECTED_INPUTS_COMPLETE " + base.sha(OUT / "summary.json"), flush=True)


if __name__ == "__main__":
    main()
