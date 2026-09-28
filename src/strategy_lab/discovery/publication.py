"""Compatible append-only Graph evidence enrichment; no Graph service or grant API."""

import json
from pathlib import Path
from strategy_lab.factor_study.pipeline import digest, write
from .capabilities import metadata


def publish(output, *, graph_root, journal):
    """Keep old envelopes; add typed provenance and actual derived source entities.

    Existing result bytes and run IDs are never overwritten. Enrichment revisions
    link their original run ID and are NOT additional market experiments.
    """
    from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
    from quantgraph.models.ingestion import IngestBatch

    output = Path(output)
    plan = json.loads((output / "plan.json").read_text())
    selected = json.loads((output / "selected-sources.json").read_text())
    byid = {r["variant"]["source_native_id"]: r for r in selected}
    results = [
        (p, json.loads(p.read_text()))
        for p in sorted((output / "runs").glob("*/result.json"))
    ]
    parents = sorted(
        {r["trial"]["record_id"] for _, r in results if r["trial"]["round"]}
    )
    records = []
    for rid in parents:
        parent = byid[rid]["variant"]
        records.append(
            {
                "record_id": "B-DISC-C2-" + rid + "-v1",
                "source_url": "https://github.com/KathenZK/quant-research-lab/blob/0012fba/src/strategy_lab/discovery/signals.py",
                "name": "Lab independent two-close confirmation hypothesis: " + rid,
                "author": "Quant Research Lab independent research hypothesis",
                "raw_market": "BTC/EUR spot, unlevered long/cash, daily UTC",
                "raw_rule": "Independent research hypothesis, not attributed to the source author. Apply the parent condition only after two consecutive closed bars for both entry and exit. Next open, same costs and position rules as frozen parent. Parent definition SHA256: "
                + parent["spec_sha256"],
                "collected_at": plan["frozen_at"],
                "metadata": {
                    "provenance_type": "SOURCE_DERIVED",
                    "parent_record_id": rid,
                    "parent_strategy_variant_id": parent["strategy_variant_id"],
                    "parent_definition_revision": parent["spec_sha256"],
                    "hypothesis": "Cost/turnover reduction may improve net incremental information; empirical result retained separately",
                    "origin": "SELF_OWNED_RESEARCH_HYPOTHESIS",
                    "source_attribution": parent["source_url"],
                },
                "strategy_parameters": {
                    "entry_confirmation_closed_bars": 2,
                    "exit_confirmation_closed_bars": 2,
                },
            }
        )
    repo = SQLiteIngestionRepository(journal)
    derived = {}
    if records:
        batch = {
            "batch_id": "B-discovery-derived-" + digest(records)[:20],
            "collector_version": "lab-discovery-v1",
            "records": records,
        }
        value = IngestBatch.model_validate(batch)
        receipt = repo.ingest(
            value, json.dumps(batch, ensure_ascii=False).encode(), "B-owned-hypothesis"
        )
        target = output / "derived-record-batch.json"
        if not target.exists():
            write(target, batch)
            write(output / "derived-ingestion-receipt.json", receipt)
        # B- IDs sort before the original M... entries; still use complete paging.
        for offset in range(0, repo.ingest_stats()["semantic_records"], 1000):
            for row in repo.variants(1000, offset):
                v = row["variant"]
                if v["source_native_id"].startswith("B-DISC-C2-"):
                    derived[v["source_native_id"]] = v
    receipts = []
    for path, r in results:
        t = r["trial"]
        row = byid.get(t["record_id"])
        if row is None:
            continue
        envelope = json.loads((path.parent / "graph-envelope.json").read_text())
        source = row["variant"]
        source_ref = {
            "entity_type": "StrategyVariant",
            "entity_id": source["strategy_variant_id"],
            "definition_revision": source["spec_sha256"],
        }
        relations = []
        lineage = []
        if t["round"]:
            d = derived["B-DISC-C2-" + t["record_id"] + "-v1"]
            derived_ref = {
                "entity_type": "StrategyVariant",
                "entity_id": d["strategy_variant_id"],
                "definition_revision": d["spec_sha256"],
            }
            lineage = [derived_ref, source_ref]
            relations.append(
                {
                    "relation": "DERIVED_FROM",
                    "from": derived_ref,
                    "to": source_ref,
                    "evidence": "Frozen one-component change; source is not claimed author of derived hypothesis",
                }
            )
        else:
            derived_ref = source_ref
        for link in row.get("factor_links", []):
            relations.append(
                {
                    "relation": "USES_FACTOR",
                    "from": derived_ref,
                    "to": {
                        "entity_type": "FactorVariant",
                        "entity_id": link["factor_variant_id"],
                        "definition_revision": digest(link["evidence"]),
                    },
                    "role": "signal",
                    "evidence": "Explicit source rule indicator reference; not causal return attribution",
                }
            )
        md = metadata(
            "STRATEGY_EVOLUTION" if t["round"] else "STRATEGY_REPLICATION",
            [source_ref],
            plan["config"],
            [
                "Independent research implementation on BTC/EUR; not source-exact author performance",
                "Retrospective history and incomplete prior search inventory",
                "Market data and derived numerical artifacts restricted by reviewed Bit2Me terms",
            ],
            {
                "execution_status": r["status"],
                "source_record_id": source["source_native_id"],
                "source_snapshot_sha256": source["source_sha256"],
                "source_concept_id": source["strategy_concept_id"],
                "source_template_id": source["strategy_template_id"],
                "implementation_code_sha256": digest(plan["code_files"]),
                "trial": t,
                "relationships": relations,
                "evidence_revision_of": envelope["research_run_id"],
            },
            lineage,
        )
        md["public_summary"]["sample"] = {
            "start": plan["evaluation_start"],
            "end": plan["end"],
            "rows": sum(
                r.get("metrics", {}).get(s, {}).get("observations", 0)
                for s in ("development", "validation")
            ),
            "frequency": "1d",
            "symbols": ["BTC/EUR"],
            "dataset_version": plan["dataset_version"],
            "real_market_data": True,
        }
        if t["round"]:
            md["public_summary"]["evolution"] = {
                "parent_experiment_id": t["parent_experiment_id"],
                "reason": "Development turnover and cost erosion prompted a predeclared mechanism test",
                "change": "Two consecutive closed-bar conditions, unchanged other components",
                "outcome": r["status"],
                "research_origin": "SELF_OWNED_HYPOTHESIS",
                "numerical_hypothesis_result": "Available in authorized internal evidence; source license restriction, not alpha secrecy",
            }
        enriched = {**envelope, "study_metadata": md}
        enriched["research_run_id"] = "qgrun-" + digest(enriched)[:32]
        # TESTED_BY endpoint is the actual immutable evidence revision, not a fake source entity.
        enriched["study_metadata"]["provenance"]["relationships"].append(
            {
                "relation": "TESTED_BY",
                "from": derived_ref,
                "to": {
                    "entity_type": "ResearchEvidence",
                    "entity_id": enriched["research_run_id"],
                },
                "evidence": "Actual completed or failed account experiment; computation status retained",
            }
        )
        target = path.parent / "graph-enriched-envelope.json"
        if target.exists():
            old = json.loads(target.read_text())
            if old != enriched:
                raise ValueError("Changed enrichment requires a new revision output")
        else:
            write(target, enriched)
        receipt = repo.put_evidence(enriched, "B-evidence-enrichment")
        if enriched not in repo.evidence_for(source["strategy_variant_id"]):
            raise ValueError("Enriched result did not read back")
        receipts.append(receipt)
    target = output / "graph-enriched-readback.json"
    if not target.exists():
        write(target, receipts)
    return receipts
