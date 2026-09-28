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


def adjudicate(result):
    oos = result["oos"]
    if oos.get("observations", 0) < 3 or oos.get("closed_trades", 0) < 30:
        return "INCONCLUSIVE"
    dsr, pbo = result["deflated_sharpe"], result["pbo"]
    if (
        oos["total_return"] <= 0
        or (oos["sharpe"] is not None and oos["sharpe"] <= 0)
        or oos["max_drawdown"] > 0.3
    ):
        return "RESEARCH_FAILED"
    if dsr["status"] != "COMPUTED" or pbo["status"] != "COMPUTED":
        return "INCONCLUSIVE"
    return (
        "RESEARCH_PASSED"
        if dsr["value"] >= 0.95 and pbo["value"] <= 0.1
        else "RESEARCH_FAILED"
    )


def run(contract_path, manifest_path, output, candidate=None, private_diagnostic=False):
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
    result = historical.study(bars, config, output)
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
        method="CSCV",
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
    base_account = output / (
        "account-" + str(config["parameter_grid"].index(config["parameters"])) + ".csv"
    )
    import pandas as pd

    account = pd.read_csv(base_account)
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
        ROOT / "src/strategy_lab/data/market_coverage.py",
    ]
    code_manifest = {str(p.relative_to(ROOT)): sha(p) for p in modules}
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
        promotion_allowed=False,
        research_status="EXPLORE_UNTRUSTED"
        if private_diagnostic
        else adjudicate(result),
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
    a = p.parse_args()
    r = run(
        a.contract,
        a.manifest,
        a.output,
        json.loads(a.candidate.read_text()) if a.candidate else None,
        a.private_diagnostic,
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
