"""Read only the manifest-pinned original funding v2 source receipts, no network."""
from __future__ import annotations

from collections import defaultdict
import gzip
import importlib.util
import io
import json
from pathlib import Path
import zipfile

import pandas as pd

SCRIPT = Path(__file__).with_name("audit_mcsm_all_funding_sources_20260910.py")
SPEC = importlib.util.spec_from_file_location("mcsm_original_source_audit", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
ROOT = audit.ROOT
GOV = ROOT / "research/platform/data-lake-governance/artifacts/binance_funding_v3_inputs_v2_20260907"
INDEX = GOV / "input_receipts.json"
MANIFEST = ROOT / "data/derived/datasets/binance_perp_funding_v3_inputs_v2/_MANIFEST.json"
OUT = audit.OUT.parent / "retained-sources"


def month_ms(value):
    ts = pd.Timestamp(value + "-01", tz="UTC")
    return audit.utc_ms(ts), audit.utc_ms(ts + pd.offsets.MonthBegin(1))


def main():
    started, checks = audit.verify_frozen_inputs()
    manifest = json.loads(MANIFEST.read_text())
    if audit.sha(MANIFEST) != "398cc19eac88d0e8c55258c118f6cae2481c6b2d1a5e6253778344b9f25a1076":
        raise ValueError("Original v2 manifest changed")
    if audit.sha(INDEX) != manifest["input_receipts_sha256"]:
        raise ValueError("Original source receipt index changed")
    jobs = json.loads((audit.OUT / "plan.json").read_text())["jobs"]
    jobs_by_symbol = defaultdict(list)
    for job in jobs:
        jobs_by_symbol[job["symbol"]].append(job)
    receipts = []
    source_files = {}
    for ref in json.loads(INDEX.read_text())["receipts"]:
        path = ROOT / ref["path"]
        if audit.sha(path) != ref["sha256"]:
            raise ValueError("Manifest-pinned receipt changed")
        r = json.loads(path.read_text())
        if "pages" in r:
            candidates = jobs if path.parent.name == "global_receipts" else jobs_by_symbol.get(r.get("symbol"), [])
            overlaps = [j for j in candidates if r["start_ms"] <= j["holding_end_ms"] and r["end_ms"] > j["holding_start_ms"]]
            if overlaps:
                receipts.append({"path": ref["path"], "sha256": ref["sha256"], "kind": "API", "windows": [j["window_id"] for j in overlaps]})
        elif r.get("status") == "CHECKSUM_AND_CRC_PASS":
            if not "2020-03" <= r["month"] <= "2026-07":
                continue
            start, end = month_ms(r["month"])
            overlaps = [j for j in jobs_by_symbol.get(r["symbol"], []) if start <= j["holding_end_ms"] and end > j["holding_start_ms"]]
            if overlaps:
                receipts.append({"path": ref["path"], "sha256": ref["sha256"], "kind": "ARCHIVE", "windows": [j["window_id"] for j in overlaps]})
    plan_path = OUT / "plan.json"
    if plan_path.exists():
        previous_plan = json.loads(plan_path.read_text())
        if previous_plan["source_receipts"] != receipts or previous_plan["frozen_input_sha256"] != started["sha256"]:
            raise ValueError("Retained source request changed")
        if previous_plan["script_sha256"] != audit.sha(Path(__file__)) and not (OUT / "serialization-fix.json").exists():
            audit.save_new(OUT / "serialization-fix.json", {"reason": "Original mixed native string/API and float/archive fundingRate requires explicit numeric dtype for Parquet serialization only",
                                                            "previous_script_sha256": previous_plan["script_sha256"],
                                                            "fixed_script_sha256": audit.sha(Path(__file__)),
                                                            "selection_and_comparison_logic_changed": False})
    else:
        audit.save_new(plan_path, {"frozen_at": audit.stamp(), "status": "LOCAL_RETAINED_ORIGINAL_SOURCES_ONLY_NOT_FRESH_QUERY",
                               "manifest_sha256": audit.sha(MANIFEST), "index_sha256": audit.sha(INDEX),
                               "frozen_input_sha256": started["sha256"], "source_receipts": receipts,
                               "script_sha256": audit.sha(Path(__file__)), "network_requests": 0})
    observations = []
    by_window = defaultdict(list)
    for ref in receipts:
        r = json.loads((ROOT / ref["path"]).read_text())
        rows = []
        if ref["kind"] == "API":
            if r.get("full_pagination") is not True:
                raise ValueError("Retained API does not document complete pagination")
            seen = {}
            for page in r["pages"]:
                path = ROOT / page["path"]
                if audit.sha(path) != page["sha256"]:
                    raise ValueError("Original API page hash changed")
                source_files[page["path"]] = page["sha256"]
                raw = gzip.decompress(path.read_bytes())
                if page.get("raw_sha256") and audit.hashlib.sha256(raw).hexdigest() != page["raw_sha256"]:
                    raise ValueError("Original decompressed API page hash changed")
                data = json.loads(raw)
                if not isinstance(data, list):
                    raise ValueError("API page is not an array")
                for row in data:
                    ts = row["fundingTime"]
                    if not r["start_ms"] <= ts <= r["end_ms"]:
                        raise ValueError("Original native API row outside receipt range")
                    if "symbol" in r and Path(ref["path"]).parent.name != "global_receipts" and row["symbol"] != r["symbol"].split("/")[0] + "USDT":
                        raise ValueError("Original native API symbol mismatch")
                    key = (row["symbol"], ts, audit.api_type(row))
                    value = (float(row["fundingRate"]), audit.positive_mark(row.get("markPrice")))
                    if key in seen:
                        if seen[key] != value:
                            raise ValueError("Page overlap has conflicting exact native event values")
                        continue  # Exact native key/value pagination overlap, never time-proximity deduplication.
                    seen[key] = value
                    rows.append({**row, "source_path": page["path"], "source_sha256": page["sha256"]})
        else:
            slug = "binance_funding_v3_inputs_v2_20260907" if Path(ref["path"]).parent.parent == GOV.relative_to(ROOT) else "binance_funding_v3_inputs_20260907"
            name = f"{r['code']}-fundingRate-{r['month']}.zip"
            path = ROOT / "data/raw/_archives" / slug / name
            if audit.sha(path) != r["sha256"] or path.with_suffix(".zip.CHECKSUM").read_text().split()[0] != r["sha256"]:
                raise ValueError("Retained archive checksum changed")
            source_files[str(path.relative_to(ROOT))] = r["sha256"]
            with zipfile.ZipFile(path) as archive:
                if archive.testzip() is not None or archive.namelist() != [name[:-4] + ".csv"]:
                    raise ValueError("Retained archive CRC/member identity failed")
                frame = pd.read_csv(io.BytesIO(archive.read(archive.namelist()[0])))
            ts = pd.to_datetime(frame.calc_time, unit="ms", utc=True)
            if not ts.dt.strftime("%Y-%m").eq(r["month"]).all() or ts.duplicated().any():
                raise ValueError("Archive times invalid")
            rows = [{"symbol": r["code"], "fundingTime": int(x.calc_time), "fundingRate": float(x.last_funding_rate),
                     "rateType": "Unspecified", "markPrice": None, "source_path": str(path.relative_to(ROOT)),
                     "source_sha256": r["sha256"]} for x in frame.itertuples()]
        source_counts = defaultdict(int)
        for row in rows:
            source_counts[(row["symbol"], row["fundingTime"] // 3_600_000)] += 1
        for window_id in ref["windows"]:
            job = jobs[window_id]
            held = [x for x in rows if x["symbol"] == job["api_symbol"] and job["holding_start_ms"] < x["fundingTime"] <= job["holding_end_ms"]]
            for row in held:
                hour_ms = row["fundingTime"] // 3_600_000 * 3_600_000
                full_hour = ref["kind"] == "ARCHIVE" or (r["start_ms"] <= hour_ms and r["end_ms"] >= hour_ms + 3_600_000 - 1)
                item = {**row, "window_id": window_id, "holding_month": job["holding_month"],
                        "source_receipt_path": ref["path"], "source_receipt_sha256": ref["sha256"],
                        "source_kind": ref["kind"], "unique_hour_within_source": full_hour and source_counts[(row["symbol"], hour_ms // 3_600_000)] == 1}
                by_window[window_id].append(item)
                observations.append(item)
    frozen = pd.read_parquet(ROOT / started["paths"]["funding"])
    result = []
    for job in jobs:
        frame = frozen[frozen.symbol.eq(job["symbol"]) & frozen.holding_start.eq(pd.Timestamp(job["holding_start_ms"], unit="ms", tz="UTC"))]
        index = defaultdict(list)
        for item in by_window[job["window_id"]]:
            index[item["fundingTime"] // 3_600_000].append(item)
        for fr in frame.itertuples():
            ts = audit.utc_ms(fr.ts)
            hits = index[ts // 3_600_000]
            compatible, conflicts = [], []
            for nr in hits:
                exact = nr["fundingTime"] == ts and (fr.source_rate_type == "Unspecified" or audit.api_type(nr) in (fr.source_rate_type, "Unspecified"))
                unique = nr["unique_hour_within_source"] and abs(nr["fundingTime"] - ts) < 2000
                if exact or unique:
                    types_compatible = fr.source_rate_type == "Unspecified" or audit.api_type(nr) in (fr.source_rate_type, "Unspecified")
                    if abs(float(nr["fundingRate"]) - fr.funding_rate) <= 1e-12 and types_compatible:
                        compatible.append(nr)
                    else:
                        conflicts.append(nr)
            native_marks = [nr for nr in compatible if audit.positive_mark(nr.get("markPrice")) is not None and nr["source_kind"] == "API"]
            chosen = native_marks[0] if native_marks else compatible[0] if compatible else None
            result.append({"original_event_id": fr.event_id, "symbol": fr.symbol, "holding_month": job["holding_month"],
                           "frozen_ts": fr.ts, "frozen_rate": fr.funding_rate, "model_rate_type": fr.rate_type,
                           "frozen_rate_type": fr.source_rate_type,
                           "mapping_status": "RETAINED_RATE_OR_TYPE_CONFLICT" if conflicts else "RETAINED_SOURCE_MATCH" if compatible else "NO_RETAINED_SOURCE_MATCH",
                           "compatible_source_observations": len(compatible), "conflicting_source_observations": len(conflicts),
                           "native_ts": pd.Timestamp(chosen["fundingTime"], unit="ms", tz="UTC") if chosen else pd.NaT,
                           "native_rate": float(chosen["fundingRate"]) if chosen else None,
                           "native_rate_type": audit.api_type(chosen) if chosen else None,
                           "native_mark": audit.positive_mark(chosen.get("markPrice")) if chosen else None,
                           "source_path": chosen["source_path"] if chosen else None,
                           "source_sha256": chosen["source_sha256"] if chosen else None,
                           "source_kind": chosen["source_kind"] if chosen else None,
                           "native_mark_sources_conflict": len({audit.positive_mark(nr.get("markPrice")) for nr in native_marks}) > 1})
    comparison = pd.DataFrame(result)
    comparison_path = OUT / "retained-event-comparison.parquet"
    if comparison_path.exists():
        pd.testing.assert_frame_equal(pd.read_parquet(comparison_path), comparison)
    else:
        comparison.to_parquet(comparison_path, index=False)
    observation_frame = pd.DataFrame(observations)
    observation_frame["fundingRate"] = pd.to_numeric(observation_frame.fundingRate, errors="raise")
    observation_frame["markPrice"] = observation_frame.markPrice.map(audit.positive_mark)
    observation_path = OUT / "held-original-source-observations.parquet"
    if observation_path.exists():
        raise FileExistsError(observation_path)
    observation_frame.to_parquet(observation_path, index=False)
    fresh = pd.read_parquet(audit.OUT / "native-event-comparison.parquet")
    combined_match = set(fresh.loc[fresh.mapping_status.str.startswith("MATCH_"), "original_event_id"]) | set(comparison.loc[comparison.mapping_status.eq("RETAINED_SOURCE_MATCH"), "original_event_id"])
    audit.save_new(OUT / "summary.json", {"status": "RETAINED_SOURCE_AUDIT_NOT_FRESH_FULL_API_VERIFICATION",
                                          "plan_sha256": audit.sha(plan_path), "network_requests": 0,
                                          "matched_receipts": len(receipts), "raw_files_verified": len(source_files),
                                          "held_source_observations_including_receipt_overlap": len(observations),
                                          "frozen_events": len(frozen), "mapping_counts": comparison.mapping_status.value_counts().to_dict(),
                                          "native_marks_available": int(comparison.native_mark.notna().sum()),
                                          "native_mark_sources_conflict_events": int(comparison.native_mark_sources_conflict.sum()),
                                          "union_matched_with_fresh_and_four_exact_prior_queries": len(combined_match),
                                          "union_unmatched_events": len(frozen) - len(combined_match),
                                          "calendar_complete_proven": False, "absence_not_inferred_from_missing_retained_sources": True,
                                          "raw_source_hashes": source_files,
                                          "output_sha256": {p.name: audit.sha(p) for p in OUT.glob("*.parquet")}})
    if audit.verify_frozen_inputs()[1] != checks:
        raise ValueError("Frozen inputs changed during retained source audit")
    print(json.dumps({"receipts": len(receipts), "observations": len(observations),
                      "mapping_counts": comparison.mapping_status.value_counts().to_dict(),
                      "union_matched": len(combined_match)}), flush=True)


if __name__ == "__main__":
    main()
