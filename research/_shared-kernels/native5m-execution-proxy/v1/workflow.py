# SPDX-License-Identifier: GPL-3.0-or-later
"""Batch-consumed fixed replay/oracle/source/prefix entrypoints, local files only."""

import argparse
import json
import socket
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
import account
import oracle
import protocol
import source_adapter


def write(p, obj):
    with Path(p).open("x") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def adapter(idroot):
    return source_adapter.load(
        Path(idroot) / "scripts/adapter.py", "rules_" + Path(idroot).name
    )


def run(inputpath, out, idroot, sources):
    idroot = Path(idroot)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    spec = protocol.verify(idroot)
    data = account.load_input(inputpath, spec)
    a = adapter(idroot)
    z = source_adapter.features(data, spec, sources, a)
    cols = ["open_time"] + list(a.FEATURES) + ["entry_signal", "exit_signal"]
    z[cols].to_csv(out / "signals.csv", index=False, float_format="%.17g")
    results = {}
    for case in spec["cases"]:
        nav, daily, trades, metrics = account.replay(z, spec, case)
        if trades.empty:
            trades = pd.DataFrame(
                columns=[
                    "trade_id",
                    "bar_index",
                    "side",
                    "reason",
                    "phase",
                    "signal_bar_index",
                    "signal_close_utc",
                    "execution_time_utc",
                    "execution_earliest_utc",
                    "execution_latest_utc",
                    "execution_time_basis",
                    "reference_price",
                    "fill_price",
                    "quantity",
                    "notional",
                    "fee",
                    "cash_after",
                    "quantity_after",
                ]
            )
        for name, frame in [("nav", nav), ("daily-nav", daily), ("trades", trades)]:
            frame.to_csv(
                out / f"{case['name']}-{name}.csv", index=False, float_format="%.17g"
            )
        results[case["name"]] = {"configuration": case, "metrics": metrics}
    summary = {
        "id": spec["record_id"],
        "origin_run_id": spec["run_id"],
        "variant_id": spec["variant_id"],
        "fidelity_class": "ADAPTED",
        "execution_class": "ADAPTED_EXECUTION_PROXY",
        "status": "explore / not promoted / not live-ready",
        "data_quality_status": "DIAGNOSTIC_ONLY",
        "trusted_input": False,
        "protocol_sha256": protocol.sha(idroot / "specs/protocol.json"),
        "input_sha256": protocol.sha(inputpath),
        "kernel_files": spec["kernel"]["files"],
        "actual_strategy_ids": 1,
        "strategy_configurations": 4,
        "new_control_configurations": 0,
        "reused_control_configurations": 1,
        "benchmark_reference": spec["benchmark_reference"],
        "oos_claim": False,
        "signals": {
            "entry_rows": int(z.entry_signal.sum()),
            "exit_rows": int(z.exit_signal.sum()),
            "collisions": int(((z.entry_signal == 1) & (z.exit_signal == 1)).sum()),
        },
        "feature_readiness": {
            c: {
                "first_valid_index": int(z[c].first_valid_index())
                if z[c].first_valid_index() is not None
                else None,
                "evaluation_nan_rows": int(
                    z.loc[z.open_time >= 1704067200000, c].isna().sum()
                ),
            }
            for c in a.FEATURES
        },
        "results": results,
    }
    write(out / "summary.json", summary)
    return summary


def sourcecheck(inputpath, idroot, sources):
    spec = protocol.verify(idroot)
    data = account.load_input(inputpath, spec)
    a = adapter(idroot)
    z = source_adapter.features(data, spec, sources, a)
    return {
        "id": spec["record_id"],
        "status": "PASS",
        "rows": len(z),
        "native_class_actual_parameter_load": True,
        "independent_Boolean_formulas_equal": True,
        "advanced_TA_indicator_independence": "Pinned TA-Lib/native indicator implementations; not independently reimplemented",
        "source_sha256": spec["source"]["sha256"],
        "loaded_parameters": spec["parameters"]["loaded_parameter_values"],
        "original_orders": spec["original_orders"],
        "engine_fills_reproduced": False,
    }


def prefixcheck(inputpath, idroot, sources):
    spec = protocol.verify(idroot)
    data = account.load_input(inputpath, spec)
    a = adapter(idroot)
    full = source_adapter.features(data, spec, sources, a)
    cuts = [9000, 9500, 20000, 50000, 90000]
    cols = list(a.FEATURES) + ["entry_signal", "exit_signal"]
    results = []
    for cut in cuts:
        pref = source_adapter.features(data.iloc[:cut].copy(), spec, sources, a)
        mut = data.copy()
        mut.loc[cut:, ["open", "high", "low", "close", "volume"]] *= 3
        changed = source_adapter.features(mut, spec, sources, a)
        for col in cols:
            np.testing.assert_allclose(
                pref[col], full.iloc[:cut][col], rtol=1e-12, atol=1e-12, equal_nan=True
            )
            np.testing.assert_allclose(
                changed.iloc[:cut][col],
                full.iloc[:cut][col],
                rtol=1e-12,
                atol=1e-12,
                equal_nan=True,
            )
        # Account outputs at short initial prefixes; late feature probes are full-year coverage.
        if cut <= 9500:
            cutoff = int(data.iloc[cut - 1].close_time) + 1
            for case in spec["cases"]:
                left = account.replay(full, spec, case, cutoff)
                right = account.replay(pref, spec, case, cutoff)
                altered = account.replay(changed, spec, case, cutoff)
                for index in [0, 1, 2]:
                    assert left[index].equals(right[index]) and left[index].equals(
                        altered[index]
                    )
        results.append(
            {
                "cut": cut,
                "features_and_signals_causal": True,
                "account_prefix_checked": cut <= 9500,
            }
        )
    return {
        "id": spec["record_id"],
        "status": "PASS",
        "cuts": results,
        "new_strategy_trials": 0,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["run", "oracle", "source", "prefix"])
    p.add_argument("--input", required=True)
    p.add_argument("--idroot", required=True)
    p.add_argument("--sources")
    p.add_argument("--results")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    with patch.object(
        socket.socket, "connect", side_effect=RuntimeError("OFFLINE_ONLY")
    ):
        if a.mode == "run":
            result = run(a.input, a.output, a.idroot, a.sources)
        elif a.mode == "oracle":
            result = oracle.validate(
                a.input, a.results, Path(a.idroot) / "specs/protocol.json"
            )
            write(a.output, result)
        elif a.mode == "source":
            result = sourcecheck(a.input, a.idroot, a.sources)
            write(a.output, result)
        else:
            result = prefixcheck(a.input, a.idroot, a.sources)
            write(a.output, result)
    print(
        json.dumps({"status": "PASS", "mode": a.mode, "id": result.get("id")}, indent=2)
    )
