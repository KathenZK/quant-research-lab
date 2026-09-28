"""Frozen, bounded campaigns using the existing trusted reader, journal and engine."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import time
import numpy as np
import pandas as pd
from strategy_lab.factor_study.pipeline import write, digest, ref
from strategy_lab.knowledge.market_contract import sha
from strategy_lab.knowledge.market_dataset import read_market_dataset
from strategy_lab.knowledge.results import evidence_envelope
from strategy_lab.research.trials import TrialRegistry
from strategy_lab.research.integrity import assess_research_integrity
from .signals import METHODS, signal_arrays

ROOT = Path(__file__).resolve().parents[3]
ENGINE = "research/_shared-kernels/quantgraph-market/v2/engine.py"
ENGINE_SHA = "3c86e382f6b7716593059db568403aae0089496312ba4ba77cfa4b8de17dcdd9"
METRICS = "research/_shared-kernels/quantgraph-diagnostics/v2/metrics.py"


def load_module(relative):
    spec = importlib.util.spec_from_file_location(
        "discovery_private_module", ROOT / relative
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def code_files():
    files = list((ROOT / "src/strategy_lab/discovery").glob("*.py")) + [
        ROOT / "src/strategy_lab/discovery/strategy-mappings.json"
    ]
    files += [
        ROOT / p
        for p in [
            ENGINE,
            METRICS,
            "src/strategy_lab/research/trials.py",
            "src/strategy_lab/research/exposure.py",
            "src/strategy_lab/research/integrity.py",
            "src/strategy_lab/research/accounting.py",
            "src/strategy_lab/knowledge/market_dataset.py",
            "src/strategy_lab/knowledge/market_core.py",
            "src/strategy_lab/knowledge/market_contract.py",
            "src/strategy_lab/data/factors/base.py",
            "src/strategy_lab/data/factors/engine.py",
            "src/strategy_lab/factor_study/factors.py",
        ]
    ]
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(files)}


def registry(output):
    output = Path(output)
    plan = json.loads((output / "plan.json").read_text())
    return TrialRegistry(
        plan["config"].get("registry_path", str(output / "trials.jsonl"))
    )


def triage(catalog, factor_variants):
    """Complete inventory, never sorts by predictive performance."""
    rows = []
    seen = set()
    for row in catalog:
        v = row["variant"]
        rid = v["source_native_id"]
        template = v["strategy_template_id"]
        parsed = v.get("rule_ast") is not None
        if rid in METHODS:
            status = "SELECTED_INDEPENDENT_IMPLEMENTATION"
            reason = (
                "Registered reviewed signal; explicit market/cash/execution transfer"
            )
        elif template in seen and template is not None:
            status = "DUPLICATE_TEMPLATE"
            reason = "Parameter/asset variant of an earlier structural template"
        elif not parsed:
            status = "SOURCE_OR_RULE_REVIEW"
            reason = "No complete parsed rule; knowledge queue, not forbidden to learn"
        else:
            status = "DATA_OR_IMPLEMENTATION_QUEUE"
            reason = "Multi-asset/total-return inputs or unreviewed operator semantics needed"
        if template:
            seen.add(template)
        rows.append(
            {
                "entity_type": "StrategyVariant",
                "entity_id": v["strategy_variant_id"],
                "record_id": rid,
                "concept_id": v["strategy_concept_id"],
                "template_id": template,
                "definition_revision": v["spec_sha256"],
                "source_url": v["source_url"],
                "source_record_hash": v["source_sha256"],
                "status": status,
                "reason": reason,
                "priority_score": int(parsed) * 3
                + int(bool(v["source_url"]))
                + int(rid in METHODS) * 4,
                "source_equivalence": "NOT_ESTABLISHED",
                "rights": v["rights_status"],
            }
        )
    from strategy_lab.factor_study.factors import FORMULAS

    for v in factor_variants:
        chosen = any("Alpha158:" + n in v["source_native_ids"] for n in FORMULAS)
        rows.append(
            {
                "entity_type": "FactorVariant",
                "entity_id": v["factor_variant_id"],
                "concept_id": v["canonical_factor_id"],
                "source_url": v["source_url"],
                "status": "SELECTED_PUBLIC_DEFINITION"
                if chosen
                else "DATA_OR_SEMANTIC_REVIEW",
                "reason": "Pinned Qlib OHLC formula and registered semantics"
                if chosen
                else "Not in frozen OHLC implementation set; no return-based exclusion",
                "priority_score": 8 if chosen else 1,
                "rights": v["commercial_use"],
            }
        )
    rule_refs = {}
    for source in catalog:
        for link in source.get("factor_links", []):
            rule_refs[link["factor_variant_id"]] = link
    for fid, link in sorted(rule_refs.items()):
        rows.append(
            {
                "entity_type": "RuleFactorReference",
                "entity_id": fid,
                "concept_id": link["factor_id"],
                "source_url": link["source"],
                "status": "RULE_REFERENCE_ONLY",
                "priority_score": 1,
                "reason": "Collected strategy indicator reference; not a semantically verified public FactorDefinition mapping",
                "rights": "REVIEW_REQUIRED",
            }
        )
    return rows


def freeze(
    catalog_path, factor_variants, cfg, output, *, campaign_id="discovery-20260928-v1"
):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    catalog = json.loads(Path(catalog_path).read_text())
    byid = {r["variant"]["source_native_id"]: r for r in catalog}
    record_ids = cfg.get("record_ids", list(METHODS))
    if (
        not record_ids
        or len(set(record_ids)) != len(record_ids)
        or set(record_ids) - set(METHODS)
    ):
        raise ValueError("Unapproved strategy set")
    selected = [byid[k] for k in record_ids]
    mappings = json.loads(
        Path(__file__).with_name("strategy-mappings.json").read_text()
    )
    for row in selected:
        v = row["variant"]
        expected = mappings[v["source_native_id"]]
        if any(
            v[k] != expected[k]
            for k in ("source_sha256", "spec_sha256", "strategy_variant_id")
        ):
            raise ValueError("Strategy source changed; mapping needs semantic review")
    assert len({r["variant"]["strategy_template_id"] for r in selected}) == len(
        record_ids
    )
    bars, _, manifest, rights, coverage = read_market_dataset(
        cfg["acquisition_contract"], cfg["manifest"], formal=True
    )
    if (
        manifest["provider"] != "bit2me"
        or manifest["symbols"] != ["BTC/EUR"]
        or manifest["frequency"] != "1d"
    ):
        raise ValueError("Only reviewed daily BTC/EUR profile in this campaign")
    inventory = triage(catalog, factor_variants)
    write(output / "triage.json", inventory)
    write(output / "selected-sources.json", selected)
    plan = {
        "schema_version": "lab-discovery-campaign/v1",
        "campaign_id": campaign_id,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "config": cfg,
        "input": {
            "manifest": ref(cfg["manifest"]),
            "acquisition_contract": ref(cfg["acquisition_contract"]),
        },
        "record_ids": record_ids,
        "dataset_sha256": manifest["dataset_sha256"],
        "dataset_version": manifest["dataset_version"],
        "rights": rights,
        "coverage": coverage,
        "code_files": code_files(),
        "catalog_sha256": sha(catalog_path),
        "selection": ref(output / "selected-sources.json"),
        "evaluation_start": "2023-08-01T00:00:00Z",
        "split": "2025-01-01T00:00:00Z",
        "end": "2026-09-27T00:00:00Z",
        "strategy_trial_cap": 200,
        "evolution_round_cap": 2,
        "objective": "Identify interpretable mechanisms and failure modes beyond simple directional exposure after costs; do not maximize past Sharpe",
        "decision_method": "Development paired comparisons and stability; validation reported once after evolution is locked. Continuing research needs positive exposure-matched incremental mean with block CI excluding zero, consistent development subperiod signs and adequate activity. No RESEARCH_PASSED.",
        "risk_constraints": "Unlevered long/cash only, no shorts/funding/borrowing. Report all drawdowns; no universal Sharpe cutoff. No live/paper execution.",
        "assumptions": {
            "market_transfer": "Source assets replaced with BTC/EUR; safe leg replaced by EUR cash yielding zero. No claim of source-exact returns.",
            "execution": "Current closed bar signals at next open; all-equity sizing net of costs; final close liquidation; whole account carries across split",
            "costs": "Research scenario 10bp fee +5bp slippage each side, not verified personal fee tier; 0/0 diagnostic and20/10 stress",
            "calendar": "Crypto UTC 24/7; monthly decisions only after actual month-end close; logarithmic return volatility annualized365 ddof1 rather than equity252",
            "adjustment": "UNADJUSTED spot; no equity dividend/corporate-action or survivorship claim",
            "indicators": "SMA-seeded EMA, Wilder RSI/ATR; CMO unsmoothed rolling sums; Bollinger population std ddof0; most recent Aroon ties; full windows; no fills",
            "channel": "100 daily closes including current bar, >= comparison at month-end; source unspecified boundary is declared research assumption",
        },
        "holdout_status": "RETROSPECTIVE_PREVIOUSLY_OBSERVED",
        "prior_trial_history": "UNKNOWN; existing BTC and Bit2Me/factor results previously observed",
        "resource_estimate": {
            "rows": len(bars),
            "initial_strategy_configs": 3 * (len(record_ids) + 1),
            "max_workers": 4,
            "default_workers": 1,
            "expected_minutes": 10,
            "expected_output_mb": 80,
            "paid_services": False,
        },
        "public_policy": "Business status/design default PUBLIC; Bit2Me numerical derivatives/market attachments RESTRICTED by specific reviewed terms, not an alpha secrecy policy",
    }
    plan["plan_sha256"] = digest(plan)
    write(output / "plan.json", plan)
    for relative in plan["code_files"]:
        target = output / "code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    reg = registry(output)
    reg.register_campaign(
        campaign_id,
        selection_goal=plan["objective"],
        scope_definition="All 20 templates x3cost scenarios,3buyhold controls,and at most2evolution rounds. Factor labels separately registered and linked in final inventory.",
        history_completeness="UNKNOWN",
        history_reason=plan["prior_trial_history"],
    )
    trials = []
    for rid in [*record_ids, "INTERNAL_BUY_HOLD"]:
        for cost, fee, slip in [("net", 10, 5), ("gross", 0, 0), ("stress", 20, 10)]:
            trials.append(
                {
                    "trial_id": rid + "--" + cost,
                    "record_id": rid,
                    "cost": cost,
                    "fee_bps": fee,
                    "slippage_bps": slip,
                    "modification": None,
                    "parent_experiment_id": None,
                    "round": 0,
                }
            )
    register_trials(output, plan, trials, selected)
    write(output / "round-0.json", trials)
    return plan


def register_trials(output, plan, trials, selected):
    reg = registry(output)
    byid = {r["variant"]["source_native_id"]: r["variant"] for r in selected}
    for t in trials:
        v = byid.get(t["record_id"])
        identity = (
            {
                k: v[k]
                for k in (
                    "source_native_id",
                    "strategy_concept_id",
                    "strategy_template_id",
                    "strategy_variant_id",
                    "spec_sha256",
                    "source_sha256",
                )
            }
            if v
            else {"id": "INTERNAL_BASELINE_BUY_HOLD"}
        )
        spec = {
            "hypothesis_family_id": METHODS[t["record_id"]][0]
            if v
            else "internal_buy_hold",
            "selection_campaign_id": plan["campaign_id"],
            "identity": identity,
            "parameters": t,
            "label_horizon": "daily_account_returns",
            "objective": plan["objective"],
            "selection_rule": plan["decision_method"],
            "dataset_fingerprint": plan["dataset_sha256"],
            "sample_fingerprint": digest(
                [plan["evaluation_start"], plan["split"], plan["end"]]
            ),
            "code_hash": digest(plan["code_files"]),
            "config_hash": digest([plan["config"], t]),
            "parent_experiment_id": t["parent_experiment_id"],
        }
        from strategy_lab.research.accounting import digest as trial_digest

        expected = "attempt-" + trial_digest(
            {"experiment_id": t["trial_id"], "spec": spec}
        )
        latest = reg.snapshot([plan["campaign_id"]])
        if (
            expected not in {a["attempt_id"] for a in latest["attempts"]}
            and latest["raw_attempts"] >= plan["strategy_trial_cap"]
        ):
            raise ValueError(
                "Trial budget exhausted (code revisions and failures included)"
            )
        t["attempt_id"] = reg.plan(t["trial_id"], spec)


def verify(plan):
    if (
        digest({k: v for k, v in plan.items() if k != "plan_sha256"})
        != plan["plan_sha256"]
    ):
        raise ValueError("Plan changed")
    if code_files() != plan["code_files"]:
        raise ValueError(
            "Frozen code changed; use preserved code or new registered revision"
        )
    if sha(ROOT / ENGINE) != ENGINE_SHA:
        raise ValueError("Existing frozen engine changed")
    for item in plan["input"].values():
        if sha(item["uri"]) != item["sha256"]:
            raise ValueError("Pinned input changed")


def _summary(a, t):
    if len(a) < 3:
        return {"status": "INSUFFICIENT_SAMPLE", "observations": len(a)}
    value = load_module(METRICS).performance(a.return_net.to_numpy(), 365)
    value.update(
        turnover=float(a.turnover.sum()),
        exposure=float(a.exposure.mean()),
        fees=float(a.fee.sum()),
        slippage_cost=float(a.slippage_cost.sum()),
        closed_trades=len(t),
        win_rate=float((t.pnl > 0).mean()) if len(t) else None,
    )
    return value


def run_one(output, plan, t, bars):
    output = Path(output)
    folder = output / "runs" / t["trial_id"]
    result_path = folder / "result.json"
    reg = registry(output)
    if result_path.exists():
        result = json.loads(result_path.read_text())
        for item in result.get("artifacts", []):
            if sha(item["uri"]) != item["sha256"]:
                raise ValueError("Completed artifact changed")
        return result
    folder.mkdir(parents=True, exist_ok=True)
    reg.record(
        t["attempt_id"],
        event_id="started",
        state="started",
        results_observed="UNOBSERVED",
        affects_selection="NO",
        reason="Frozen configuration starts before account computation",
    )
    try:
        e, leave, value = signal_arrays(
            bars, t["record_id"], modification=t["modification"]
        )
        engine = load_module(ENGINE)
        engine.signals = lambda *_: (e, leave)
        contract = {
            "signal": "REGISTERED_DISCOVERY",
            "parameters": [],
            "minutes": 1440,
            "initial_cash": 10000.0,
            "evaluation_start": plan["evaluation_start"],
            "fee_bps": t["fee_bps"],
            "slippage_bps": t["slippage_bps"],
            "stop_loss_fraction": 0.2
            if t["record_id"] == "EV3-M0256-BTC-EUR"
            else None,
            "take_profit_fraction": 0.5
            if t["record_id"] == "EV3-M0256-BTC-EUR"
            else None,
        }
        account, fills, trades = engine.replay(bars, contract)
        if not trades.empty and not np.isclose(
            account.equity.iloc[-1], 10000 + trades.pnl.sum(), rtol=1e-10
        ):
            raise ValueError("Account trade cash identity failed")
        sections = {}
        for name, start, end in [
            ("development", plan["evaluation_start"], plan["split"]),
            ("validation", plan["split"], plan["end"]),
            ("dev_2023", plan["evaluation_start"], "2024-01-01T00:00:00Z"),
            ("dev_2024", "2024-01-01T00:00:00Z", plan["split"]),
        ]:
            a = account[
                (account.ts >= pd.Timestamp(start)) & (account.ts < pd.Timestamp(end))
            ]
            if trades.empty:
                tr = trades
            else:
                exits = pd.to_datetime(trades.exit_ts, utc=True)
                tr = trades[
                    (exits >= pd.Timestamp(start)) & (exits < pd.Timestamp(end))
                ]
            sections[name] = _summary(a, tr)
        artifacts = []
        for name, frame in [
            ("account", account),
            ("fills", fills),
            ("trades", trades),
            (
                "signals",
                pd.DataFrame(
                    {"ts": bars.ts, "enter": e, "leave": leave, "diagnostic": value}
                ),
            ),
        ]:
            path = folder / (name + ".parquet")
            frame.to_parquet(path, index=False)
            artifacts.append(ref(path))
        result = {
            "trial": t,
            "status": "SUCCESS",
            "metrics": sections,
            "artifacts": artifacts,
            "computation": "VERIFIED_ACCOUNT_IDENTITIES_AND_REGISTERED_SIGNAL",
            "reproduction": "EXPLICIT_RESEARCH_IMPLEMENTATION; SOURCE_EXACT_RETURN_REPRODUCTION_NOT_CLAIMED",
            "research_status": "EXPLORATORY_RETROSPECTIVE",
            "promotion_allowed": False,
            "plan_sha256": plan["plan_sha256"],
        }
    except Exception as exc:
        result = {
            "trial": t,
            "status": "FAILED",
            "error": type(exc).__name__,
            "reason": str(exc),
            "artifacts": [],
            "plan_sha256": plan["plan_sha256"],
            "promotion_allowed": False,
        }
    write(result_path, result)
    reg.record(
        t["attempt_id"],
        event_id="result",
        state="completed" if result["status"] == "SUCCESS" else "failed",
        results_observed="OBSERVED",
        affects_selection="YES",
        reason="Retain every successful or failed configuration, including gross/stress and controls",
        result_refs=ref(result_path),
    )
    return result


def run(output, *, round_number=0, workers=1):
    output = Path(output)
    plan = json.loads((output / "plan.json").read_text())
    verify(plan)
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError("workers must be1..4")
    trials = json.loads((output / f"round-{round_number}.json").read_text())
    bars, _, manifest, _, _ = read_market_dataset(
        plan["config"]["acquisition_contract"], plan["config"]["manifest"], formal=True
    )
    if manifest["dataset_sha256"] != plan["dataset_sha256"]:
        raise ValueError("Data changed")
    begin = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda t: run_one(output, plan, t, bars), trials))
    summary = {
        "round": round_number,
        "completed": len(results),
        "failed": sum(r["status"] == "FAILED" for r in results),
        "elapsed_seconds": time.monotonic() - begin,
        "results": [
            ref(output / "runs" / t["trial_id"] / "result.json") for t in trials
        ],
    }
    target = output / f"round-{round_number}-complete.json"
    if not target.exists():
        write(target, summary)
    return summary


def writeback(output, graph_journal):
    from quantgraph.graph.ingestion_store import SQLiteIngestionRepository

    output = Path(output)
    plan = json.loads((output / "plan.json").read_text())
    verify(plan)
    reg = registry(output)
    scope = reg.snapshot([plan["campaign_id"]])
    assessment = assess_research_integrity(
        study_kind="EXPLORATORY_ANALYSIS",
        contract={
            "frozen_at": plan["frozen_at"],
            "oos_start": plan["split"],
            "oos_end": plan["end"],
            "holdout_status": plan["holdout_status"],
        },
        selection_scope=scope,
        dataset_fingerprint=plan["dataset_sha256"],
        statistical_methods={
            n: {
                "status": "NOT_APPLICABLE",
                "decision_use": "NONE",
                "reason": "No confirmatory selection; prior campaign trial history unknown and historical validation observed",
            }
            for n in ("dsr", "pbo")
        },
    )
    p = output / "integrity-assessment.json"
    if not p.exists():
        write(p, assessment)
    selected = json.loads((output / "selected-sources.json").read_text())
    byid = {r["variant"]["source_native_id"]: r for r in selected}
    repo = SQLiteIngestionRepository(graph_journal)
    receipts = []
    for result_path in sorted((output / "runs").glob("*/result.json")):
        result = json.loads(result_path.read_text())
        t = result["trial"]
        row = byid.get(t["record_id"])
        if row is None:
            continue
        v = row["variant"]
        sections = {
            "in_sample": result.get("metrics", {}).get(
                "development", {"status": "FAILED", "reason": result.get("reason")}
            ),
            "oos": result.get("metrics", {}).get("validation", {"status": "FAILED"}),
            "costs": {"fee_bps": t["fee_bps"], "slippage_bps": t["slippage_bps"]},
            "stability": {
                "study_kind": "EXPLORATORY_ANALYSIS",
                "source_exact_reproduction": False,
                "integrity": assessment,
                "full_result": ref(result_path),
            },
        }
        envelope = evidence_envelope(
            family_id=plan["campaign_id"],
            source_strategy_ids=[v["strategy_variant_id"]],
            contract={
                "plan_sha256": plan["plan_sha256"],
                "source_identity": {
                    k: v[k]
                    for k in (
                        "strategy_concept_id",
                        "strategy_template_id",
                        "strategy_variant_id",
                        "spec_sha256",
                        "source_sha256",
                    )
                },
                "trial": t,
            },
            trial_count=len(scope["attempts"]),
            artifact_uri=str(result_path.resolve()),
            artifact_sha256=sha(result_path),
            results=sections,
            evidence_kind="ATTRIBUTION_ABLATION" if t["round"] else "LAB_REPRODUCED",
        )
        path = result_path.parent / "graph-envelope.json"
        if path.exists():
            envelope = json.loads(path.read_text())
        else:
            write(path, envelope)
        receipt = repo.put_evidence(envelope, "discovery-private-study")
        if envelope not in repo.evidence_for(v["strategy_variant_id"]):
            raise ValueError("Graph readback mismatch")
        receipts.append(receipt)
    target = output / "graph-readback.json"
    if not target.exists():
        write(target, receipts)
    return receipts


def freeze_evolution(output):
    """One narrowly specified round selected only from development cost/turnover."""
    output = Path(output)
    plan = json.loads((output / "plan.json").read_text())
    verify(plan)
    target = output / "round-1.json"
    if target.exists():
        return json.loads(target.read_text())
    choices = []
    for rid in plan["record_ids"]:
        if rid in {"M4692", "M4815", "M5242", "M5749", "EV3-M0256-BTC-EUR"}:
            continue
        base = json.loads(
            (output / "runs" / (rid + "--net") / "result.json").read_text()
        )
        gross = json.loads(
            (output / "runs" / (rid + "--gross") / "result.json").read_text()
        )
        if base["status"] != "SUCCESS" or gross["status"] != "SUCCESS":
            continue
        dev = base["metrics"]["development"]
        drag = gross["metrics"]["development"]["total_return"] - dev["total_return"]
        if drag > 0 and dev["turnover"] > 0:
            choices.append((dev["turnover"], rid, drag))
    chosen = sorted(choices, key=lambda x: (-x[0], x[1]))[:2]
    trials = []
    hypotheses = []
    for turnover, rid, drag in chosen:
        hypotheses.append(
            {
                "parent_record_id": rid,
                "reason": "Development cost drag and high turnover; selected by turnover, not maximum return",
                "observed_development_turnover": turnover,
                "observed_development_gross_minus_net_return": drag,
                "change": "Require two consecutive daily closed-bar conditions for entry AND exit; all other rules fixed",
                "prediction": "At least20% lower development turnover and lower cost drag; net excess mean against fixed exposure control should not deteriorate",
                "ablation": "Same parent, unchanged costs, original one-close rule already retained; gross/net/stress isolate cost mechanism",
                "budget": 3,
                "comparison_baseline": rid + "--net",
                "no_validation_inspection_for_selection": True,
            }
        )
        for cost, fee, slip in [("net", 10, 5), ("gross", 0, 0), ("stress", 20, 10)]:
            trials.append(
                {
                    "trial_id": rid + "--confirm2--" + cost,
                    "record_id": rid,
                    "cost": cost,
                    "fee_bps": fee,
                    "slippage_bps": slip,
                    "modification": "two_close_confirmation",
                    "parent_experiment_id": rid + "--" + cost,
                    "round": 1,
                }
            )
    selected = json.loads((output / "selected-sources.json").read_text())
    register_trials(output, plan, trials, selected)
    write(
        output / "evolution-hypotheses.json",
        {
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "plan_sha256": plan["plan_sha256"],
            "round": 1,
            "hypotheses": hypotheses,
            "no_second_round_reason": "At most two rounds, not a requirement to keep searching. One mechanism change plus ablation suffices; no validation-guided retries.",
        },
    )
    write(target, trials)
    return trials


def mean_block_ci(x, *, seed=928, replications=500, block=20):
    x = np.asarray(x, dtype=float)
    if len(x) < 30 or not np.isfinite(x).all():
        return {"status": "INSUFFICIENT_SAMPLE", "ci95": None}
    rng = np.random.default_rng(seed)
    means = []
    n = len(x)
    for _ in range(replications):
        idx = (
            rng.integers(0, n, size=int(np.ceil(n / block)))[:, None] + np.arange(block)
        ) % n
        means.append(x[idx.ravel()[:n]].mean())
    return {
        "status": "COMPUTED",
        "mean_daily": float(x.mean()),
        "ci95": np.quantile(means, [0.025, 0.975]).tolist(),
        "n": n,
        "method": "circular moving-block paired bootstrap; block20;500replications;descriptive, no multiple-selection adjustment",
    }


def report(output):
    output = Path(output)
    plan = json.loads((output / "plan.json").read_text())
    verify(plan)
    reference = pd.read_parquet(
        output / "runs/INTERNAL_BUY_HOLD--gross/account.parquet"
    )
    rows = []
    matrix = {}
    for path in sorted((output / "runs").glob("*/result.json")):
        r = json.loads(path.read_text())
        t = r["trial"]
        if (
            t["cost"] != "net"
            or t["record_id"] == "INTERNAL_BUY_HOLD"
            or r["status"] != "SUCCESS"
        ):
            continue
        a = pd.read_parquet(path.parent / "account.parquet")
        dev = a.ts < pd.Timestamp(plan["split"])
        weight = float(a.loc[dev, "exposure"].mean())
        paired = {}
        for label, mask in [("development", dev), ("validation", ~dev)]:
            paired[label] = mean_block_ci(
                a.loc[mask, "return_net"].to_numpy()
                - weight * reference.loc[mask, "return_net"].to_numpy()
            )
        rid = t["record_id"]
        gross = json.loads(
            (
                path.parent.parent
                / (t["trial_id"].rsplit("--", 1)[0] + "--gross")
                / "result.json"
            ).read_text()
        )
        stress = json.loads(
            (
                path.parent.parent
                / (t["trial_id"].rsplit("--", 1)[0] + "--stress")
                / "result.json"
            ).read_text()
        )
        dev_ci = paired["development"]["ci95"]
        val_ci = paired["validation"]["ci95"]
        support = bool(dev_ci and val_ci and dev_ci[0] > 0 and val_ci[0] > 0)
        subperiod_means = {}
        for label, start, end in [
            ("dev_2023", plan["evaluation_start"], "2024-01-01T00:00:00Z"),
            ("dev_2024", "2024-01-01T00:00:00Z", plan["split"]),
        ]:
            mask = (a.ts >= pd.Timestamp(start)) & (a.ts < pd.Timestamp(end))
            subperiod_means[label] = float(
                (
                    a.loc[mask, "return_net"]
                    - weight * reference.loc[mask, "return_net"]
                ).mean()
            )
        support &= all(v > 0 for v in subperiod_means.values())
        support &= r["metrics"]["validation"]["closed_trades"] >= 10
        category = (
            "FURTHER_RESEARCH_SUPPORTED_EXPLORATORY"
            if support
            else "NO_INCREMENTAL_EVIDENCE_OR_INCONCLUSIVE"
        )
        item = {
            "trial_id": t["trial_id"],
            "family": METHODS[rid][0],
            "metrics": r["metrics"],
            "paired_incremental": paired,
            "development_subperiod_incremental_mean": subperiod_means,
            "activity_limit": "Fewer than10 closed validation trades means sparse episode evidence; descriptive returns still retained",
            "development_fitted_exposure_weight": weight,
            "matched_control_scope": "Analytic constant exposure-scaled buy-hold price-return control; not a separately tradable portfolio or causal attribution",
            "cost_drag": {
                k: gross["metrics"][k]["total_return"] - r["metrics"][k]["total_return"]
                for k in ("development", "validation")
            },
            "double_cost_returns": {
                k: stress["metrics"][k]["total_return"]
                for k in ("development", "validation")
            },
            "classification": category,
            "historical_validation": "RETROSPECTIVE_ONLY",
            "future_independent_validation_required": True,
            "parameter_sensitivity": "NOT_TESTED; three costs are execution scenarios, not parameter search",
            "source_exact_reproduction": False,
            "result": ref(path),
        }
        if t["round"]:
            parent = json.loads(
                (
                    output / "runs" / t["parent_experiment_id"] / "result.json"
                ).read_text()
            )
            parent_gross = json.loads(
                (output / "runs" / (rid + "--gross") / "result.json").read_text()
            )
            pdev = parent["metrics"]["development"]
            d = r["metrics"]["development"]
            parent_drag = (
                parent_gross["metrics"]["development"]["total_return"]
                - pdev["total_return"]
            )
            item["evolution_comparison"] = {
                "parent": t["parent_experiment_id"],
                "development_turnover_reduction": 1 - d["turnover"] / pdev["turnover"],
                "turnover_prediction_supported": d["turnover"]
                <= 0.8 * pdev["turnover"],
                "cost_drag_prediction_supported": item["cost_drag"]["development"]
                < parent_drag,
                "development_net_return_delta": d["total_return"]
                - pdev["total_return"],
                "validation_net_return_delta": r["metrics"]["validation"][
                    "total_return"
                ]
                - parent["metrics"]["validation"]["total_return"],
                "interpretation": "Paired observational ablation on same historical path, not causal market evidence",
            }
        rows.append(item)
        matrix[t["trial_id"]] = a.return_net.to_numpy()
    redundancy = []
    corr = pd.DataFrame(matrix).corr()
    for i, left in enumerate(corr.columns):
        for right in corr.columns[i + 1 :]:
            v = corr.loc[left, right]
            if np.isfinite(v):
                redundancy.append(
                    {
                        "left": left,
                        "right": right,
                        "pearson_daily_account_return": float(v),
                    }
                )
    result = {
        "campaign_id": plan["campaign_id"],
        "strategy_templates": len(plan["record_ids"]),
        "computational_method_groups": len({METHODS[r][0] for r in plan["record_ids"]}),
        "economic_method_groups": len(
            {
                METHODS[r][0]
                if METHODS[r][0]
                in {"mean_reversion", "volatility_state", "drawdown_state"}
                else "trend_directional_state"
                for r in plan["record_ids"]
            }
        ),
        "rows": rows,
        "redundancy": redundancy,
        "promoted": 0,
        "limitations": [
            "Single spot market transfer, no source-exact author performance replication",
            "Previously observed retrospective data; no independent holdout",
            "Known source metadata is not copyright/commercial clearance",
            "Numerical derivatives restricted by Bit2Me terms; public business status and plan are separate",
            "No parameter robustness or cross-market confirmation claimed",
            "Block confidence intervals describe temporal sampling conditional on inspected methods; no selection correction",
        ],
    }
    target = output / "comparison.json"
    if not target.exists():
        write(target, result)
    lines = [
        "# 公开方法发现与失败学习（内部数值研究）",
        "",
        "所有结论为 EXPLORATORY_RETROSPECTIVE。源方法、研究实现假设与计算正确性分别记录。",
        "",
        "| 模板/版本 | 开发净收益 | 后段净收益 | 后段最大回撤 | 开发/后段成本侵蚀 | 后段匹配暴露增量均值95%区间 | 结论 |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for r in rows:
        d, v = r["metrics"]["development"], r["metrics"]["validation"]
        lines.append(
            f"| {r['trial_id']} | {d['total_return']:.3%} | {v['total_return']:.3%} | {v['max_drawdown']:.3%} | {r['cost_drag']} | {r['paired_incremental']['validation']['ci95']} | {r['classification']} |"
        )
    lines += ["", "## 演化与否定结果", ""]
    for r in rows:
        if "evolution_comparison" in r:
            lines.append(
                "- "
                + r["trial_id"]
                + "："
                + json.dumps(r["evolution_comparison"], ensure_ascii=False)
            )
    lines += ["", "## 限制", ""] + ["- " + s for s in result["limitations"]]
    p = output / "report.md"
    if not p.exists():
        p.write_text("\n".join(lines) + "\n")
    return result
