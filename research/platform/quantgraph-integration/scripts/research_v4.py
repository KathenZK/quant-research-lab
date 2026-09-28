"""One frozen template family; formal admission precedes all account computation."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from strategy_lab.knowledge.market_dataset import read_market_dataset  # noqa: E402
from strategy_lab.knowledge.market_contract import sha, check_contract_binding  # noqa: E402
from strategy_lab.knowledge.candidates import digest  # noqa: E402
from strategy_lab.knowledge.results import market_evidence_v4  # noqa: E402
import research_v3 as historical  # noqa: E402
from strategy_lab.research.integrity import assess_research_integrity, adjudicate_research  # noqa: E402
from strategy_lab.research.trials import TrialRegistry  # noqa: E402
from strategy_lab.research.exposure import read_ledger  # noqa: E402

ENGINE_PATH = ROOT / "research/_shared-kernels/quantgraph-market/v2/engine.py"
ENGINE_HASH = "3c86e382f6b7716593059db568403aae0089496312ba4ba77cfa4b8de17dcdd9"


def current_engine():
    if sha(ENGINE_PATH) != ENGINE_HASH:
        raise ValueError("Frozen v2 engine changed")
    spec = importlib.util.spec_from_file_location("qg_market_v2", ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def robustness(surface, baseline):
    grid = [r["parameters"] for r in surface]
    base_index = grid.index(baseline)
    neighbors = [
        i for i, p in enumerate(grid) if sum(a != b for a, b in zip(p, baseline)) == 1
    ]
    out = dict(
        adjacency="one parameter axis differs; fixed predeclared grid",
        baseline_index=base_index,
        neighbor_indices=neighbors,
    )
    for window in ("in_sample", "oos"):
        base = surface[base_index][window].get("sharpe")
        scores = [surface[i][window].get("sharpe") for i in neighbors]
        if base is None or any(x is None for x in scores) or not neighbors:
            out[window] = dict(
                status="NOT_APPLICABLE",
                reason="Undefined Sharpe or no predeclared neighbors",
            )
        else:
            deltas = [x - base for x in scores]
            tolerance = 0.1 * max(abs(base), 1e-12)
            out[window] = dict(
                status="COMPUTED",
                local_sensitivity=deltas,
                plateau_neighbor_count=sum(abs(x) <= tolerance for x in deltas),
                neighbor_count=len(neighbors),
                absolute_sharpe_tolerance=tolerance,
                interpretation="Descriptive proximity to frozen baseline; not parameter selection",
            )
    return out


def adjudicate(result, assessment=None):
    return adjudicate_research(result, assessment)


def run(contract_path, manifest_path, output, candidate=None, private_diagnostic=False, *, integrity_context=None):
    bars, contract, manifest, rights, coverage = read_market_dataset(
        contract_path, manifest_path, formal=not private_diagnostic
    )
    contract_pin, manifest_pin = sha(contract_path), sha(manifest_path)
    if not private_diagnostic:
        from strategy_lab.knowledge.market_contract import validate_candidate_binding

        if candidate is None:
            raise ValueError(
                "Explicit ELIGIBLE V4 candidate required before formal computation"
            )
        validate_candidate_binding(
            candidate,
            contract,
            manifest,
            contract_sha256=contract_pin,
            manifest_sha256=manifest_pin,
        )
    config = contract["engine_config"]
    historical.engine = current_engine()
    ctx = dict(integrity_context or {})
    ctx.update(dataset_fingerprint=manifest['dataset_sha256'],
               hypothesis_family_id=contract['experiment_family_id'], identity=contract['strategy_variant_id'])
    registry_path = ctx.get('registry_path', output.parent / 'trial-registry.jsonl')
    registry = TrialRegistry(registry_path)
    if ctx.get('holdout_id'):
        registry.use_holdout(ctx['holdout_id'], use_id=ctx['holdout_use_id'],
                             dataset_fingerprint=manifest['dataset_sha256'], reason='Before V4 result computation/reveal')
    result = historical.study(bars, config, output, trial_context=ctx)
    for name in ("deflated_sharpe", "pbo"):
        if result[name]["status"] in {"NOT_COMPUTABLE", "NOT_COMPUTED"}:
            result[name]["status"] = "NOT_APPLICABLE"
    dsr = result["deflated_sharpe"]
    dsr.update(
        sharpe_units="PER_BAR",
        annualization_periods=365 * 1440 / config["minutes"],
        skew_definition="population standardized third moment",
        kurtosis_definition="Pearson, not excess",
        nominal_trial_count=contract["trial_count"],
        prior_exposed_trials=contract["prior_trial_count"],
        expected_max_sharpe=dsr.get("benchmark_sr"),
        limitation="Conditional fixed-family diagnostic; IID approximation; not a correction for all prior research or reused holdout",
    )
    result["pbo"].update(
        method="CSCV_FIXED_RETURNS",
        tie_policy="midrank; equal weighting of all tied IS winners",
        sample_requirements=">=2 trials; 8 equal blocks; >=2 bars/block; nonzero variance in every split",
        limitation_status="LIMITATION",
        purged=False,
        embargoed=False,
    )
    result["robustness"]["local_sensitivity"] = robustness(
        result["robustness"]["surface"], config["parameters"]
    )
    result["exposure_definition"] = "POST_OPEN_POSITION_PROXY_WITH_INTRABAR_BOUNDS"
    result["trade_window_policy"] = (
        "Trade counts and win rates are assigned by exit timestamp using whole-trade PnL; "
        "period return/risk metrics use only that window's daily account returns. "
        "Positions and prior-bar signals carry across the IS/OOS boundary."
    )
    base_account = output / (
        "account-" + str(config["parameter_grid"].index(config["parameters"])) + ".csv"
    )
    import pandas as pd

    account = pd.read_csv(base_account)
    account["ts"] = pd.to_datetime(account["ts"], utc=True)
    baseline_index = config["parameter_grid"].index(config["parameters"])
    trades = pd.read_csv(output / f"trades-{baseline_index}.csv")
    exits = (
        pd.to_datetime(trades.exit_ts, utc=True)
        if len(trades)
        else pd.Series([], dtype="datetime64[ns, UTC]")
    )
    sequential = []
    cursor, end = pd.Timestamp(contract["oos_start"]), pd.Timestamp(contract["oos_end"])
    while cursor < end:
        stop = min(cursor + pd.DateOffset(months=6), end)
        a = account[(account.ts >= cursor) & (account.ts < stop)]
        t = trades[(exits >= cursor) & (exits < stop)]
        sequential.append(
            dict(
                start=cursor.isoformat(),
                end_exclusive=stop.isoformat(),
                metrics=historical.summarize(a, t, 365 * 1440 / config["minutes"]),
            )
        )
        cursor = stop
    result["chronological_oos_slices"] = dict(
        status="COMPUTED",
        method="LOCKED_BASELINE_SIX_MONTH_SLICES",
        slices=sequential,
        state_policy="Carry account and prior closed-bar signal across boundaries; trades assigned by exit timestamp",
        purpose="Descriptive temporal stability only; no refitting or parameter selection",
    )
    result["walk_forward"] = dict(
        status="NOT_APPLICABLE",
        reason="Frozen rule has no fitted estimator or rolling selection protocol; chronological OOS slices are reported separately",
    )
    result["exposure_duration_bounds"] = dict(
        lower=float(account.exposure_duration_lower.mean()),
        upper=float(account.exposure_duration_upper.mean()),
        actual_time_observed=False,
    )
    check_contract_binding(contract_path, manifest)
    if sha(contract_path) != contract_pin or sha(manifest_path) != manifest_pin:
        raise ValueError("Contract or manifest changed during computation")
    # Rehash data and rights after computation before labeling any result formal.
    read_market_dataset(contract_path, manifest_path, formal=not private_diagnostic)
    # Record all modules determining validation, execution and statistics.
    modules = [
        Path(__file__),
        Path(historical.__file__),
        ENGINE_PATH,
        historical.METRICS_PATH,
        ROOT / "src/strategy_lab/knowledge/market_contract.py",
        ROOT / "src/strategy_lab/knowledge/market_dataset.py",
        ROOT / "src/strategy_lab/knowledge/market_core.py",
        ROOT / "src/strategy_lab/data/market_coverage.py",
    ]
    modules += [ROOT / 'src/strategy_lab/research' / name for name in
                ('integrity.py', 'trials.py', 'statistics.py', 'exposure.py', 'accounting.py')]
    code_manifest = {str(p.relative_to(ROOT)): sha(p) for p in modules}
    exposure_records = []
    for ledger in ctx.get('exposure_ledgers', []):
        exposure_records.extend(read_ledger(Path(ledger)))
    assessment = assess_research_integrity(
        study_kind=ctx.get('study_kind', 'HISTORICAL_REPLICATION' if contract.get('holdout_status') == 'RETROSPECTIVE_PREVIOUSLY_OBSERVED' else 'EXPLORATORY_ANALYSIS'),
        contract=contract, selection_scope=result['trial_registry'],
        statistical_methods={'dsr': result['deflated_sharpe'], 'pbo': result['pbo']},
        holdout_evidence=registry.holdout_evidence(ctx['holdout_id']) if ctx.get('holdout_id') else None,
        exposure_records=exposure_records, dataset_fingerprint=manifest['dataset_sha256'])
    report = dict(
        schema_version="market-study-v4",
        evidence_kind="PRIVATE_DIAGNOSTIC_PROBE"
        if private_diagnostic
        else "REAL_MARKET_BACKTEST",
        formal_market_backtest_count=0 if private_diagnostic else 1,
        contract_sha256=sha(contract_path),
        dataset_manifest_sha256=sha(manifest_path),
        dataset_sha256=manifest["dataset_sha256"],
        rights_id=rights["rights_id"],
        rights_sha256=manifest["rights_sha256"],
        code_sha256=digest(code_manifest),
        code_manifest=code_manifest,
        config_sha256=digest(config),
        strategy_concept_id=contract["strategy_concept_id"],
        strategy_template_id=contract["strategy_template_id"],
        strategy_variant_id=contract["strategy_variant_id"],
        experiment_family_id=contract["experiment_family_id"],
        coverage=coverage,
        real_market_data=True,
        results=result,
        integrity_assessment=assessment,
        promotion_allowed=False,
        research_status="EXPLORE_UNTRUSTED"
        if private_diagnostic
        else adjudicate(result, assessment),
    )
    historical.write_json(output / "research-result.json", report)
    if not private_diagnostic:
        envelope = market_evidence_v4(
            candidate_rows=[candidate],
            contract_path=contract_path,
            manifest_path=manifest_path,
            artifact_uri=str(output / "research-result.json"),
            artifact_sha256=sha(output / "research-result.json"),
            code_sha256=report["code_sha256"],
            results=result,
            research_status=report["research_status"],
        )
        historical.write_json(output / "research-evidence.json", envelope)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--contract", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--candidate", type=Path)
    p.add_argument("--private-diagnostic", action="store_true")
    p.add_argument("--integrity-context", type=Path, help="Optional explicit registry/campaign/protocol sidecar")
    a = p.parse_args()
    r = run(
        a.contract,
        a.manifest,
        a.output,
        json.loads(a.candidate.read_text()) if a.candidate else None,
        a.private_diagnostic,
        integrity_context=json.loads(a.integrity_context.read_text()) if a.integrity_context else None,
    )
    print(
        json.dumps(
            {
                k: r[k]
                for k in (
                    "evidence_kind",
                    "formal_market_backtest_count",
                    "research_status",
                )
            }
        )
    )
