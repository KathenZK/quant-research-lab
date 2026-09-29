"""Independent restoration from captured code and raw trusted input, not new selection."""

import argparse
import importlib.util
import json
from pathlib import Path
import pandas as pd
from strategy_lab.knowledge.market_contract import sha
from strategy_lab.knowledge.market_dataset import read_market_dataset
from strategy_lab.factor_study.pipeline import write, ref, digest
from strategy_lab.research.trials import TrialRegistry


def module(path):
    spec = importlib.util.spec_from_file_location("frozen_local_research", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--campaign", type=Path, required=True)
    a = p.parse_args()
    root = a.campaign.resolve()
    records = []
    seen = set()
    for directory in ["strategies", "confirmation-repair-v1"]:
        base = root / directory
        plan = json.loads((base / "plan.json").read_text())
        code = base / "code"
        if (
            digest({k: v for k, v in plan.items() if k != "plan_sha256"})
            != plan["plan_sha256"]
        ):
            raise ValueError("Frozen plan changed")
        for rel, expected in plan["code_files"].items():
            if sha(code / rel) != expected:
                raise ValueError("Captured code changed: " + rel)
        bars, _, manifest, _, _ = read_market_dataset(
            plan["config"]["acquisition_contract"],
            plan["config"]["manifest"],
            formal=True,
        )
        assert manifest["dataset_sha256"] == plan["dataset_sha256"]
        signals = module(code / "src/strategy_lab/discovery/signals.py")
        for path in sorted((base / "runs").glob("*/result.json")):
            result = json.loads(path.read_text())
            t = result["trial"]
            if t["attempt_id"] in seen or result["status"] != "SUCCESS":
                continue
            seen.add(t["attempt_id"])
            engine = module(
                code / "research/_shared-kernels/quantgraph-market/v2/engine.py"
            )
            enter, leave, _ = signals.signal_arrays(
                bars, t["record_id"], modification=t["modification"]
            )
            engine.signals = lambda *_: (enter, leave)
            config = {
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
            account, fills, trades = engine.replay(bars, config)
            for name, actual in [
                ("account", account),
                ("fills", fills),
                ("trades", trades),
            ]:
                old = pd.read_parquet(path.parent / (name + ".parquet"))
                # Parquet normalizes a zero-column RangeIndex into an empty
                # string index. There are no values or column names to compare.
                if actual.shape == old.shape == (0, 0):
                    continue
                pd.testing.assert_frame_equal(actual, old, check_exact=True)
            entry = {
                "attempt_id": t["attempt_id"],
                "trial_id": t["trial_id"],
                "source_result": ref(path),
                "status": "EXACT_ACCOUNT_FILL_TRADE_PARITY",
                "new_configuration": False,
            }
            reg = TrialRegistry(root / "trials.jsonl")
            reg.record(
                t["attempt_id"],
                event_id="independent-restoration-v1",
                state="completed",
                results_observed="OBSERVED",
                affects_selection="YES",
                reason="Recomputed same registered configuration from captured code and trusted native bytes; exact parity; no new selection or holdout",
                result_refs=entry,
            )
            records.append(entry)
    target = root / "independent-restoration.json"
    if not target.exists():
        write(
            target,
            {
                "restored": len(records),
                "new_configuration_trials": 0,
                "records": records,
            },
        )
    print(
        {"restored": len(records), "exact_parity": True, "new_configuration_trials": 0}
    )


if __name__ == "__main__":
    main()
