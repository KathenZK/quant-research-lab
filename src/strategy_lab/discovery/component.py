"""Development-only public-factor-to-position ablation, reusing frozen engine."""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
from strategy_lab.data.factors.engine import compute_factor_bundle
from strategy_lab.factor_study.factors import registry, validate_definition
from strategy_lab.factor_study.pipeline import digest, ref, write
from strategy_lab.knowledge.market_dataset import read_market_dataset
from strategy_lab.knowledge.results import evidence_envelope
from strategy_lab.knowledge.market_contract import sha
from strategy_lab.research.accounting import digest as trial_digest
from strategy_lab.research.trials import TrialRegistry
from .campaign import load_module, ENGINE, ROOT, code_files, _summary
from .capabilities import metadata


def run(config, output, *, registry_path, campaign_id="discovery-20260928-v1"):
    """Six configurations: MA5 public definition and MA50 matched original control.

    Selected for known structural redundancy, NOT the largest observed IC. Only
    development bars are consumed; no second validation-based evolution round.
    """
    from quantgraph import FactorDB
    from quantgraph.factor_study import definition_identity
    from quantgraph.graph.ingestion_store import SQLiteIngestionRepository

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    db = FactorDB(config["graph_root"])
    v = next(
        x
        for x in db.search_factors(source="qlib", limit=1000)
        if "Alpha158:MA5" in x["source_native_ids"]
    )
    validate_definition(v)
    identity = definition_identity(v)
    source = json.loads(Path(config["source_catalog"]).read_text())
    parent = next(
        x["variant"]
        for x in source
        if x["variant"]["source_native_id"] == "EV3-M0234-BTC-EUR"
    )
    bars, _, manifest, _, _ = read_market_dataset(
        config["acquisition_contract"], config["manifest"], formal=True
    )
    bars = bars[bars.ts < pd.Timestamp("2025-01-01T00:00:00Z")].reset_index(drop=True)
    plan_path = output / "plan.json"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
        if digest({k: v for k, v in plan.items() if k != "sha256"}) != plan["sha256"]:
            raise ValueError("Component plan changed")
        if plan["input_manifest"] != ref(config["manifest"]):
            raise ValueError("Component input changed")
        if plan["code_files"] != code_files():
            raise ValueError("Component plan code changed")
    else:
        plan = {
            "schema_version": "factor-component-ablation/v1",
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "campaign_id": campaign_id,
            "identity": identity,
            "parent_strategy": parent["strategy_variant_id"],
            "parent_definition_revision": parent["spec_sha256"],
            "code_files": code_files(),
            "input_manifest": ref(config["manifest"]),
            "dataset_sha256": manifest["dataset_sha256"],
            "dataset_version": manifest["dataset_version"],
            "evaluation_start": "2023-08-01T00:00:00Z",
            "end": "2025-01-01T00:00:00Z",
            "validation_consumed": False,
            "selection_basis": "MA5 already overlaps price-relative/range definitions; inspect a simple component before adding complexity. Not selected by maximum IC.",
            "hypothesis": "Shortening an otherwise identical close/SMA long-cash rule from50to5 bars increases turnover and cost drag without robust incremental information",
            "comparison": "MA5 <1 long vs full-window50barSMA long; same next-open engine, terminal close and0/15/30bp total per-side scenarios",
            "budget": 6,
            "study_kind": "EXPLORATORY_ANALYSIS",
            "prior_results_observed": True,
            "research_status": "EXPLORATORY_RETROSPECTIVE",
            "promotion_allowed": False,
        }
        plan["sha256"] = digest(plan)
        write(plan_path, plan)
        for relative in plan["code_files"]:
            target = output / "code" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
    reg = TrialRegistry(registry_path)
    specs = []
    for name in ("qlib_MA5", "parent_MA50"):
        for cost, fee, slip in [("net", 10, 5), ("gross", 0, 0), ("stress", 20, 10)]:
            tid = "factor-component-dev-" + name + "-" + cost
            spec = {
                "hypothesis_family_id": "factor_component_ma",
                "selection_campaign_id": campaign_id,
                "identity": identity,
                "parameters": {"name": name, "fee_bps": fee, "slippage_bps": slip},
                "label_horizon": "development_daily_account",
                "objective": plan["hypothesis"],
                "selection_rule": "Retain all6; development only; no winner promotion",
                "dataset_fingerprint": manifest["dataset_sha256"],
                "sample_fingerprint": digest([plan["evaluation_start"], plan["end"]]),
                "code_hash": digest(plan["code_files"]),
                "config_hash": digest([name, fee, slip, plan["sha256"]]),
                "parent_experiment_id": "EV3-M0234-BTC-EUR--" + cost,
            }
            scope = reg.snapshot([campaign_id])
            expected = "attempt-" + trial_digest({"experiment_id": tid, "spec": spec})
            if (
                expected not in {x["attempt_id"] for x in scope["attempts"]}
                and scope["raw_attempts"] >= 200
            ):
                raise ValueError("Strategy budget exhausted")
            specs.append((tid, reg.plan(tid, spec), name, fee, slip))
    results = []
    repo = SQLiteIngestionRepository(config["journal"])
    for tid, attempt, name, fee, slip in specs:
        folder = output / tid
        folder.mkdir(exist_ok=True)
        result_path = folder / "result.json"
        if result_path.exists():
            result = json.loads(result_path.read_text())
            validate_retained_result(result, plan_path)
            events = next(
                x
                for x in reg.snapshot([campaign_id])["attempts"]
                if x["attempt_id"] == attempt
            )["events"]
            retained_refs = [
                x["data"]["result_refs"]
                for x in events
                if x["data"].get("result_refs", {}).get("uri")
                == str(result_path.resolve())
            ]
            if not retained_refs or retained_refs[-1] != ref(result_path):
                raise ValueError("Component result changed or unregistered")
        else:
            reg.record(
                attempt,
                event_id="started",
                state="started",
                results_observed="UNOBSERVED",
                affects_selection="NO",
                reason="Predeclared development-only component ablation",
            )
            try:
                if name == "qlib_MA5":
                    factor = compute_factor_bundle(bars, registry(["MA5"]))[
                        "MA5"
                    ].reset_index(drop=True)
                    valid = bars.close.rolling(5).count() >= 5
                    enter = (factor < 1) & valid
                    leave = (factor >= 1) & valid
                else:
                    line = bars.close.rolling(50).mean()
                    enter = bars.close > line
                    leave = bars.close <= line
                engine = load_module(ENGINE)
                engine.signals = lambda *_: (enter.to_numpy(), leave.to_numpy())
                contract = {
                    "signal": "REGISTERED_MA_COMPONENT",
                    "parameters": [],
                    "minutes": 1440,
                    "initial_cash": 10000.0,
                    "evaluation_start": plan["evaluation_start"],
                    "fee_bps": fee,
                    "slippage_bps": slip,
                }
                account, fills, trades = engine.replay(bars, contract)
                assert np.isclose(
                    account.equity.iloc[-1], 10000 + trades.pnl.sum(), rtol=1e-10
                )
                artifacts = []
                for n, frame in [
                    ("account", account),
                    ("fills", fills),
                    ("trades", trades),
                ]:
                    path = folder / (n + ".parquet")
                    frame.to_parquet(path, index=False)
                    artifacts.append(ref(path))
                result = {
                    "trial_id": tid,
                    "attempt_id": attempt,
                    "name": name,
                    "fee_bps": fee,
                    "slippage_bps": slip,
                    "status": "SUCCESS",
                    "metrics": _summary(account, trades),
                    "artifacts": artifacts,
                    "plan": ref(plan_path),
                    "definition": identity,
                    "promotion_allowed": False,
                }
            except Exception as exc:
                result = {
                    "trial_id": tid,
                    "attempt_id": attempt,
                    "name": name,
                    "fee_bps": fee,
                    "slippage_bps": slip,
                    "status": "FAILED",
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                    "metrics": {},
                    "artifacts": [],
                    "plan": ref(plan_path),
                    "definition": identity,
                    "promotion_allowed": False,
                }
            write(result_path, result)
            reg.record(
                attempt,
                event_id="result",
                state="completed" if result["status"] == "SUCCESS" else "failed",
                results_observed="OBSERVED",
                affects_selection="YES",
                reason="Retain all development-only comparisons",
                result_refs=ref(result_path),
            )
        envelope = evidence_envelope(
            family_id=campaign_id,
            source_strategy_ids=[parent["strategy_variant_id"]],
            contract=plan,
            trial_count=6,
            artifact_uri=str(result_path.resolve()),
            artifact_sha256=ref(result_path)["sha256"],
            results={
                "in_sample": result["metrics"],
                "oos": {
                    "status": "NOT_APPLICABLE",
                    "reason": "Development-only ablation; no further validation inspection",
                },
                "costs": {"fee_bps": fee, "slippage_bps": slip},
            },
            evidence_kind="ATTRIBUTION_ABLATION",
        )
        sref = {
            "entity_type": "StrategyVariant",
            "entity_id": parent["strategy_variant_id"],
            "definition_revision": parent["spec_sha256"],
        }
        fref = {
            "entity_type": "FactorVariant",
            "entity_id": identity["factor_variant_id"],
            "definition_revision": identity["definition_revision"],
        }
        envelope["study_metadata"] = metadata(
            "STRATEGY_EVOLUTION",
            [sref],
            config,
            [
                "Development-only ablation; no new source strategy or independent economic discovery",
                "Bit2Me numerical derivatives restricted",
            ],
            {
                "execution_status": result["status"],
                "factor_mapping": identity,
                "relationships": [
                    {
                        "relation": "USES_FACTOR",
                        "from": sref,
                        "to": fref,
                        "evidence": "Actual registered QlibMA5 factor values determine next-open positions",
                    }
                ]
                if name == "qlib_MA5"
                else [],
            },
            [sref, fref],
        )
        envelope["research_run_id"] = "qgrun-" + digest(envelope)[:32]
        target = folder / "graph-envelope.json"
        if target.exists() and json.loads(target.read_text()) != envelope:
            raise ValueError(
                "Component envelope changed; new metadata revision required"
            )
        if not target.exists():
            write(target, envelope)
        receipt = repo.put_evidence(envelope, "B-factor-component")
        assert envelope in repo.evidence_for(parent["strategy_variant_id"])
        if not (folder / "writeback.json").exists():
            write(folder / "writeback.json", receipt)
        results.append(result)
    return results


def validate_retained_result(result, plan_path):
    """A checkpoint cannot silently reuse changed plan or numerical artifacts."""
    if result["plan"] != ref(plan_path):
        raise ValueError("Component result plan changed")
    for item in result["artifacts"]:
        if sha(item["uri"]) != item["sha256"]:
            raise ValueError("Component artifact changed")
