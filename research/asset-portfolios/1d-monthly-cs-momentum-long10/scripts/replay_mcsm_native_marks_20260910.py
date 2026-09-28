"""Only replace uniquely matched event marks; preserve the original estimated run."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from run_mcsm_baseline_estimate_20260909 import load_terminals, run_scenario
from verify_mcsm_baseline_20260908 import load_verified_returned_daily

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
OLD = FAMILY / "artifacts/baseline-estimate-20260909"
NEW = FAMILY / "artifacts/funding-recheck-20260910"
MATCH_STATUSES = {"MATCH_EXACT_NATIVE_KEY", "MATCH_OFFICIAL_UNIQUE_HOUR"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        handle.write("\n")


def native_overlay(funding, comparison):
    """Source matching is external; validate every replacement again locally."""
    if funding.event_id.isna().any() or funding.event_id.duplicated().any():
        raise ValueError("original event IDs must be unique and present")
    c = comparison.copy()
    if "native_mark" not in c:
        raise ValueError("comparison itself must supply native_mark")
    if c.original_event_id.isna().any() or c.original_event_id.duplicated().any():
        raise ValueError("comparison must contain exactly one row per original event")
    if set(c.original_event_id) != set(funding.event_id):
        raise ValueError("comparison omitted or invented an original event")
    if not c.mapping_status.isin(MATCH_STATUSES | {"SOURCE_QUERY_INCOMPLETE"}).all():
        raise ValueError("known source conflict or unsupported mapping status")
    joined = funding.merge(c, left_on="event_id", right_on="original_event_id", how="left",
                           suffixes=("", "_checked"), validate="one_to_one")
    mark_column = "native_mark_checked" if "native_mark_checked" in joined else "native_mark"
    native = pd.to_numeric(joined[mark_column], errors="coerce")
    matched = joined.mapping_status.isin(MATCH_STATUSES)
    usable = matched & np.isfinite(native) & native.gt(0)
    rate = pd.to_numeric(joined.native_rate, errors="coerce")
    if not np.isfinite(rate[matched]).all():
        raise ValueError("matched source has no valid native rate")
    if not np.allclose(rate[matched], joined.loc[matched, "funding_rate"], rtol=0, atol=1e-12):
        raise ValueError("official rate differs; mark-only overlay is prohibited")
    if not joined.loc[matched, "native_rate_type"].eq(joined.loc[matched, "rate_type"]).all():
        raise ValueError("official funding type differs")
    if "symbol_checked" in joined and not joined.symbol.eq(joined.symbol_checked).all():
        raise ValueError("comparison symbol differs from original event")
    if "ts" in funding:
        checked_time_column = "frozen_ts_checked" if "frozen_ts_checked" in joined else "frozen_ts"
        frozen_time = pd.to_datetime(joined[checked_time_column], utc=True)
        if not frozen_time.eq(pd.to_datetime(joined.ts, utc=True)).all():
            raise ValueError("comparison points to a different original timestamp")
        native_time = pd.to_datetime(joined.native_ts, utc=True)
        offsets = (native_time - frozen_time).dt.total_seconds().abs()
        if native_time[matched].isna().any() or not offsets[matched].le(2).all():
            raise ValueError("native timestamp is outside the agreed mapping tolerance")
        if not native_time[matched].dt.floor("h").eq(frozen_time[matched].dt.floor("h")).all():
            raise ValueError("native timestamp crosses an original event hour")
        if {"holding_start", "holding_end"}.issubset(funding.columns):
            entered = pd.to_datetime(joined.holding_start, utc=True)
            exited = pd.to_datetime(joined.holding_end, utc=True)
            if not (native_time[matched].gt(entered[matched]) & native_time[matched].le(exited[matched])).all():
                raise ValueError("native timestamp crosses the actual holding window")
    if usable.any() and (joined.loc[usable, "source_path"].isna().any()
                         or not joined.loc[usable, "source_path"].astype(str).str.len().gt(0).all()
                         or not joined.loc[usable, "source_sha256"].astype(str).str.fullmatch(r"[0-9a-f]{64}").all()):
        raise ValueError("native mark replacement lacks raw source provenance")
    out = funding.copy().set_index("event_id")
    replacements = joined.loc[usable].copy()
    replacements["replacement"] = native[usable]
    replacement_marks = replacements.set_index("event_id").replacement
    for column in ("mark_center", "mark_low", "mark_high"):
        out.loc[replacement_marks.index, column] = replacement_marks
    out.loc[replacement_marks.index, "mark_source"] = "RECHECKED_OFFICIAL_NATIVE_SETTLEMENT_MARK"
    replaced = replacements.set_index("event_id")
    provenance = {"mark_raw_path": "source_path", "mark_raw_sha256": "source_sha256"}
    for target, source in provenance.items():
        if target in out:
            out.loc[replaced.index, target] = replaced[source]
    if "mark_quality" in out:
        out.loc[replaced.index, "mark_quality"] = "RECHECKED_OFFICIAL_NATIVE_MARK_PARTIAL_SOURCE_AUDIT"
    out = out.reset_index().reindex(columns=funding.columns)
    immutable_columns = [x for x in funding if x not in (
        "mark_center", "mark_low", "mark_high", "mark_source", "mark_raw_path", "mark_raw_sha256", "mark_quality")]
    pd.testing.assert_frame_equal(out[immutable_columns].reset_index(drop=True),
                                  funding[immutable_columns].reset_index(drop=True))
    return out, {
        "original_events": len(funding), "independently_matched_source_events": int(matched.sum()),
        "usable_native_mark_events": int(usable.sum()), "retained_original_mark_events": int((~usable).sum()),
        "mark_only_change": True, "old_timestamps_rates_types_and_selection_unchanged": True,
        "comparison_status_counts": c.mapping_status.value_counts().to_dict(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, default=NEW / "sources/native-event-comparison.parquet")
    parser.add_argument("--output", type=Path, default=NEW / "native-replay")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    run = OLD / "accounts"
    started = json.loads((run / "started.json").read_text())
    kernel = FAMILY / "scripts/mcsm_baseline_accounting_20260908.py"
    if sha(kernel) != started["kernel_sha256"]:
        raise ValueError("original accounting kernel changed")
    for key, path in started["paths"].items():
        if sha(path) != started["sha256"][key]:
            raise ValueError(f"original input/code changed: {key}")
    old_summary = json.loads((run / "summary.json").read_text())
    for name, digest in old_summary["output_sha256"].items():
        if sha(run / name) != digest:
            raise ValueError(f"original account output changed: {name}")
    source_summary_path = args.comparison.parent / "summary.json"
    source_summary = json.loads(source_summary_path.read_text())
    if source_summary.get("output_sha256", {}).get(args.comparison.name) != sha(args.comparison):
        raise ValueError("comparison does not match source summary published hash")
    for key in ("missing_from_api", "extra_api_events", "rate_conflicts", "type_conflicts"):
        if source_summary.get(key, 0):
            raise ValueError(f"known source issue prevents mark-only replay: {key}")
    funding = pd.read_parquet(started["paths"]["funding"])
    comparison = pd.read_parquet(args.comparison)
    changed, coverage = native_overlay(funding, comparison)
    usable = comparison.mapping_status.isin(MATCH_STATUSES) & pd.to_numeric(comparison.native_mark, errors="coerce").gt(0)
    for row in comparison.loc[usable, ["source_path", "source_sha256"]].drop_duplicates().itertuples(index=False):
        raw_path = Path(row.source_path)
        if not raw_path.is_absolute():
            raw_path = ROOT / raw_path
        if sha(raw_path) != row.source_sha256:
            raise ValueError(f"replacement raw source hash differs: {raw_path}")
    args.output.mkdir(parents=True)
    changed_path = args.output / "native-priority-events.parquet"
    changed.to_parquet(changed_path, index=False)
    pins = {"original_summary": run / "summary.json", "original_started": run / "started.json",
            "comparison": args.comparison, "source_summary": source_summary_path,
            "new_input": changed_path, "script": Path(__file__),
            "recheck_plan": FAMILY / "specs/binance-1d-mcsm-funding-recheck-20260910.md",
            "accounting_kernel": kernel}
    pins.update({f"original_input_{key}": Path(value) for key, value in started["paths"].items()})
    hashes = {key: sha(path) for key, path in pins.items()}
    save(args.output / "started.json", {
        "status": "NATIVE_PRIORITY_DIAGNOSTIC_INPUT_FROZEN_BEFORE_REPLAY", "paths": pins,
        "sha256": hashes, "coverage": coverage, "source_summary_status": source_summary.get("status"),
        "does_not_fix_missing_or_extra_events": True,
    })
    holdings = pd.read_parquet(started["paths"]["holdings"])
    execution = pd.read_parquet(started["paths"]["execution"])
    result = run_scenario(holdings, execution, load_verified_returned_daily(), changed, load_terminals(), "estimated_center")
    old_center = next(x for x in old_summary["results"] if x["scenario"] == "estimated_center")
    cash = pd.read_parquet(run / "estimated_center/funding.parquet")
    signed = cash.merge(changed[["symbol", "ts", "rate_type", "mark_center"]],
                        on=["symbol", "ts", "rate_type"], validate="one_to_one")
    direct = -signed.quantity * signed.rate * signed.mark_center - signed.funding_cash
    for table in ("nav", "monthly", "terminals"):
        result[table].to_parquet(args.output / f"{table}.parquet", index=False)
    result["monthly"].to_csv(args.output / "monthly.csv", index=False)
    if any(sha(pins[key]) != value for key, value in hashes.items()):
        raise ValueError("input/source changed during native priority replay")
    save(args.output / "summary.json", {
        "status": "NATIVE_PRIORITY_MARK_SENSITIVITY_NOT_FULL_VERIFIED_NET",
        "metrics": result["metrics"], "coverage": coverage,
        "original_final_equity": old_center["final_equity"],
        "new_minus_original_final_equity": result["metrics"]["final_equity"] - old_center["final_equity"],
        "direct_mark_cash_change_at_original_quantities": float(direct.sum()),
        "rate_selection_time_and_cost_changes": False,
        "missing_or_extra_source_events_not_silently_fixed": True,
        "full_calendar_pit_margin_fills_verified": False,
        "input_sha256": hashes,
    })
    print(json.dumps(result["metrics"], default=str, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
