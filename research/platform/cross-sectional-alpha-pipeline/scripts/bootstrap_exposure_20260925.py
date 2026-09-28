"""Register documented historical exposures, without inventing trial counts."""
import json
from pathlib import Path

from strategy_lab.research.evidence import sha256
from strategy_lab.research.exposure import append_record, read_ledger, overlaps

ROOT = Path(__file__).resolve().parents[4]
TOPIC = ROOT / "research/platform/cross-sectional-alpha-pipeline"
OUT = TOPIC / "artifacts/implementation-20260925"
LEDGER = TOPIC / "artifacts/research-exposure-ledger.jsonl"


def main():
    source = ROOT / "research/asset-portfolios/multi-legacy-post-registration-audit/artifacts/repository_ranking_20260911/results.json"
    manifest = source.with_name("archive_manifest.json")
    expected = json.loads(manifest.read_text())["files"][str(source.relative_to(ROOT))]["sha256"]
    if sha256(source) != expected:
        raise ValueError("historical exposure source no longer matches its archive")
    rows = json.loads(source.read_text())
    existing = {r["data"]["id"]: r["data"] for r in read_ledger(LEDGER)}
    def append(data):
        if data["id"] in existing:
            if existing[data["id"]] != data:
                raise ValueError("existing exposure changed; append an explicit correction")
        else:
            append_record(LEDGER, data)
    for row in rows:
        append({"kind": "exposure", "id": "historical-20260911-" + row["id"], "family": row["family_path"],
                "candidate": row["name"], "window_start": row["start"], "window_end": row["end"],
                "evidence_class": "historical_replay", "trial_count": None,
                "trial_count_unknown_reason": "source contains one retained scenario; all preceding manual/model/parameter selections are not enumerated",
                "recorded_scenarios": 1, "source_registered_version": row.get("registered"),
                "selection_reason": "bulk import of ALL 117 retained audit scenarios without return filtering; no new performance experiment",
                "artifacts": {str(source.relative_to(ROOT)): expected, str(manifest.relative_to(ROOT)): sha256(manifest)},
                "observed_at_original": "2026-09-11 archive; exact first exposure time unknown",
                "source_limitations": row.get("limitation", ""), "return_was_seen": row.get("return_value") is not None})
    # Two explicitly documented development/reused-holdout windows extend beyond
    # the post-registration audit. Registration today does not reset their status.
    manual = [
        ("cslgbm-reused-2026q2", "research/asset-portfolios/1h-cross-sectional-lightgbm-selector",
         "2026-04-01T00:00:00Z", "2026-07-01T00:00:00Z", "decision-log.md",
         "2026-07-17 OOS revealed; 2026-07-18 formula correction. Same quarter is reused holdout; original model artifacts deleted."),
        ("keltner-v3-development", "research/hype/30m-keltner-trend-breakout",
         "2025-05-30T10:30:00Z", "2026-07-13T06:06:00Z", "specs/hype-30m-keltner-trend-breakout-v3-spec.md",
         "Frozen research sample stated in V3 spec; this is development exposure, not untouched OOS."),
    ]
    for id, family, start, end, suffix, note in manual:
        path = ROOT / family / suffix
        append({"kind": "exposure", "id": id, "family": family, "window_start": start, "window_end": end,
                "evidence_class": "development", "trial_count": None,
                "trial_count_unknown_reason": "full search/selection history not reconstructible from this retained document",
                "selection_reason": note, "artifacts": {str(path.relative_to(ROOT)): sha256(path)}})
    receipt = OUT / "backup-receipt-r3.json"
    replay = OUT / "candidate-restore-result.json"
    append({"kind": "exposure", "id": "hype-ma7-car-v3-recovery-20260925",
            "family": "research/asset-portfolios/1d-ma7-cross-atr-generalization",
            "window_start": "2025-06-15T00:00:00Z", "window_end": "2026-09-05T00:00:00Z",
            "evidence_class": "historical_replay", "trial_count": None,
            "trial_count_unknown_reason": "one preselected restoration; historical strategy selection count remains unknown",
            "new_strategy_variants": 0, "selection_reason": "predeclared frozen V3 restoration; infrastructure development retries do not create new alpha variants",
            "artifacts": {str(receipt.relative_to(ROOT)): sha256(receipt), str(replay.relative_to(ROOT)): sha256(replay)}})
    records = read_ledger(LEDGER)
    overlap = overlaps(records, start="2026-04-01T00:00:00Z", end="2026-07-01T00:00:00Z")
    result = {"records": len(records), "families": len({r["data"]["family"] for r in records}),
              "historical_audit_scenarios": len(rows), "historical_audit_families": len({r["family_path"] for r in rows}),
              "chain_verified": True, "last_sha256": records[-1]["sha256"], "file_sha256": sha256(LEDGER),
              "known_total_strategy_trial_counts": 0, "coverage": "seed inventory, not exhaustive history",
              "reused_2026q2_record_count": len(overlap), "reused_2026q2_families": sorted({r["data"]["family"] for r in overlap}),
              "dsr_pbo_computed": False, "independent_oos_claim": False}
    with (OUT / "exposure-bootstrap-summary.json").open("x") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
