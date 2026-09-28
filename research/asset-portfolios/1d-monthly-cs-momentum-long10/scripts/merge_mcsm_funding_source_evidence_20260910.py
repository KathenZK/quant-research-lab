"""Fuse independently retained API evidence without hiding unmatched original events."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd

SCRIPT = Path(__file__).with_name("audit_mcsm_all_funding_sources_20260910.py")
SPEC = importlib.util.spec_from_file_location("mcsm_source_merge", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
OUT = audit.OUT.parent / "combined-sources"


def merge_candidate(frame, row, kind):
    key = row["original_event_id"]
    if key not in frame.index:
        raise ValueError("Additional source event is outside frozen holding events")
    old = frame.loc[key]
    if old.symbol != row["symbol"] or abs(old.frozen_rate - row["native_rate"]) > 1e-12:
        raise ValueError("API candidate source identity/rate conflict")
    if row["native_rate_type"] != old.model_rate_type:
        raise ValueError("API candidate source type differs from booked account type")
    delta = int((pd.Timestamp(row["native_ts"]) - old.frozen_ts).total_seconds() * 1000)
    if abs(delta) >= 2000:
        raise ValueError("API candidate exceeds frozen event time mapping tolerance")
    if old.mapping_status.startswith("MATCH_"):
        if old.native_ts != row["native_ts"] or abs(old.native_rate - row["native_rate"]) > 1e-12 or old.native_rate_type != row["native_rate_type"]:
            raise ValueError("Independent official sources disagree on event identity/rate/type")
        if pd.notna(old.native_mark) and pd.notna(row["native_mark"]) and abs(old.native_mark - row["native_mark"]) > 1e-10 * max(1.0, abs(old.native_mark)):
            raise ValueError("Independent official sources disagree on native mark")
        if pd.notna(old.native_mark) or pd.isna(row["native_mark"]):
            return
    elif old.mapping_status != "SOURCE_QUERY_INCOMPLETE":
        raise ValueError("Never overlay or hide an existing official source conflict")
    for column in ["native_ts", "native_rate", "native_rate_type", "native_mark", "source_path", "source_sha256"]:
        frame.at[key, column] = row[column]
    frame.at[key, "mapping_status"] = "MATCH_EXACT_NATIVE_KEY" if delta == 0 else "MATCH_OFFICIAL_UNIQUE_HOUR"
    frame.at[key, "timestamp_delta_ms"] = delta
    frame.at[key, "source_retrieval_kind"] = kind


def main():
    started, checks = audit.verify_frozen_inputs()
    files = {"fresh_summary": audit.OUT / "summary.json", "fresh_comparison": audit.OUT / "native-event-comparison.parquet",
             "retained_summary": audit.OUT.parent / "retained-sources/summary.json",
             "retained_comparison": audit.OUT.parent / "retained-sources/retained-event-comparison.parquet",
             "marks_summary": audit.OUT.parent / "marks/native-retained-summary.json",
             "marks_comparison": audit.OUT.parent / "marks/native-retained-mappings.parquet"}
    summaries = {name: json.loads(path.read_text()) for name, path in files.items() if name.endswith("summary")}
    for summary_name, table_name in [("fresh_summary", "fresh_comparison"), ("retained_summary", "retained_comparison"), ("marks_summary", "marks_comparison")]:
        if summaries[summary_name]["output_sha256"][files[table_name].name] != audit.sha(files[table_name]):
            raise ValueError("Independent source result hash changed")
    if summaries["marks_summary"]["raw_conflicts"] or summaries["marks_summary"]["ambiguous_matches"]:
        raise ValueError("Retained native source audit has conflicts")
    plan_path = OUT / "plan.json"
    audit.save_new(plan_path, {"frozen_at": audit.stamp(), "inputs": {k: {"path": str(p.relative_to(audit.ROOT)), "sha256": audit.sha(p)} for k, p in files.items()},
                               "frozen_account_input_sha256": started["sha256"], "script_sha256": audit.sha(Path(__file__)),
                               "rules": "Keep every original event; fail on any disagreement; only typed API sources eligible; archive-only rates remain separate corroboration; no network"})
    frame = pd.read_parquet(files["fresh_comparison"])
    if len(frame) != 97421 or frame.original_event_id.isna().any() or frame.original_event_id.duplicated().any():
        raise ValueError("Expected a complete unique outer comparison with all original events")
    if not frame.mapping_status.isin(["MATCH_EXACT_NATIVE_KEY", "MATCH_OFFICIAL_UNIQUE_HOUR", "SOURCE_QUERY_INCOMPLETE"]).all():
        raise ValueError("Existing source differences cannot be silently overlaid")
    frame["source_retrieval_kind"] = "UNQUERIED_OR_REFUSED"
    matched = frame.mapping_status.str.startswith("MATCH_")
    frame.loc[matched, "source_retrieval_kind"] = frame.loc[matched, "source_path"].map(
        lambda path: "FRESH_API_20260910" if "/funding-recheck-20260910/" in path else "RETAINED_EXACT_REQUEST_20260909")
    frame = frame.set_index("original_event_id", drop=False)
    retained = pd.read_parquet(files["retained_comparison"])
    if retained.mapping_status.str.contains("CONFLICT").any() or retained.native_mark_sources_conflict.any():
        raise ValueError("Manifest-pinned original sources have conflicts")
    for row in retained[retained.mapping_status.eq("RETAINED_SOURCE_MATCH") & retained.source_kind.eq("API")].to_dict("records"):
        merge_candidate(frame, row, "RETAINED_V2_MANIFEST_API")
    marks = pd.read_parquet(files["marks_comparison"])
    for row in marks.to_dict("records"):
        if row["match_status"] != "UNIQUE_EXACT_NATIVE_MS_RATE_TYPE":
            raise ValueError("Additional native source mapping was not independently exact")
        row["source_sha256"] = row["source_file_sha256"]
        merge_candidate(frame, row, "RETAINED_BASELINE_NATIVE_API")
    raw_hashes = {}
    for row in frame[frame.source_path.notna()][["source_path", "source_sha256"]].drop_duplicates().itertuples(index=False):
        if row.source_path in raw_hashes and raw_hashes[row.source_path] != row.source_sha256:
            raise ValueError("Source path has inconsistent hashes")
        if audit.sha(audit.ROOT / row.source_path) != row.source_sha256:
            raise ValueError("Merged original source bytes changed")
        raw_hashes[row.source_path] = row.source_sha256
    frame = frame.reset_index(drop=True)
    output = OUT / "native-event-comparison.parquet"
    frame.to_parquet(output, index=False)
    matched = frame.mapping_status.str.startswith("MATCH_")
    archive = retained.mapping_status.eq("RETAINED_SOURCE_MATCH") & retained.source_kind.eq("ARCHIVE")
    corroborated = set(frame.loc[matched, "original_event_id"]) | set(retained.loc[archive, "original_event_id"])
    summary = {"status": "PARTIAL_OFFICIAL_API_EVIDENCE_WITH_EXPLICIT_UNCOVERED_EVENTS_NOT_FULL_CALENDAR_PROOF",
               "plan_sha256": audit.sha(plan_path), "original_events": len(frame),
               "matched_api_events": int(matched.sum()), "uncovered_api_events": int((~matched).sum()),
               "native_mark_events": int((matched & frame.native_mark.notna()).sum()),
               "rate_corroborated_api_or_retained_archive_events": len(corroborated),
               "source_retrieval_kind_counts": frame.source_retrieval_kind.value_counts().to_dict(),
               "mapping_counts": frame.mapping_status.value_counts().to_dict(),
               "native_rate_type_counts": frame.native_rate_type.dropna().value_counts().to_dict(),
               "complete_fresh_query_windows": 134, "exact_prior_complete_query_windows": 4,
               "global_fresh_api_query_failed_after_http403": True, "all_760_windows_verified": False,
               "retained_sources_do_not_prove_full_calendar": True, "network_requests": 0,
               "raw_source_hashes": raw_hashes,
               "output_sha256": {output.name: audit.sha(output)}}
    audit.save_new(OUT / "summary.json", summary)
    if audit.verify_frozen_inputs()[1] != checks:
        raise ValueError("Original account files changed during merge")
    print(json.dumps({k: v for k, v in summary.items() if k != "raw_source_hashes"}), flush=True)


if __name__ == "__main__":
    main()
