"""Build an unpublished Graph detail from retained light evidence, no raw prices."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

FAMILY = Path(__file__).resolve().parents[1]


def project():
    base = FAMILY / "artifacts/20261003-first-replay"
    summary = json.loads((base / "results/summary.json").read_text())
    spec = json.loads((FAMILY / "specs/M0216-first-replay.json").read_text())
    record = json.loads((base / "graph-record.json").read_text())
    manifest = json.loads((base / "result-manifest.json").read_text())
    for relative, expected in manifest["files"].items():
        path = FAMILY / relative
        if relative.endswith(("results/summary.json", "results/base-nav.csv")):
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError("Retained light evidence changed")

    def periods(case):
        values = {"full": summary[case]["metrics"], **summary[case]["periods"]}
        return {
            key: {
                **value,
                "sharpe": value["sharpe_zero_cash"],
                "start": "2023-01-01" if key == "full" else key + "-01-01",
                "end": "2024-12-31" if key == "full" else key + "-12-31",
            }
            for key, value in values.items()
        }

    rows = list(csv.DictReader((base / "results/base-nav.csv").open()))
    result = record["related_results"][0]
    return dict(
        id="M0216",
        name=record["name"],
        family=spec["family"],
        run_id=result["origin_run_id"],
        origin_run_id=result["origin_run_id"],
        variant_id=result["variant_id"],
        fidelity_class="HYPOTHESIS",
        fidelity_reason="Source-anchored daily signal and risk-gate hypothesis; not strict reproduction.",
        metrics=dict(
            periods=periods("base"),
            same_instrument_benchmark=periods("buyhold"),
            additional_native_bar_lag=periods("lag2"),
            cost_sensitivity={k: periods(k) for k in ["fee0", "fee20"]},
        ),
        spec=dict(
            source_url=spec["source_url"], assumptions=spec["limitations"], params=spec
        ),
        audit=record["audit"],
        curve=[
            dict(
                date=r["date"], equity=float(r["equity"]), drawdown=float(r["drawdown"])
            )
            for r in rows
        ],
        lineage={
            **result,
            "projection_revision": "graph-display-v2",
            "license": "CC BY-NC-SA 4.0",
            "attribution": "Binance Vision",
        },
        limitations=spec["limitations"]
        + ["Permanent halt retains BTC; baseline trails buy-and-hold."],
        curve_meta=dict(
            observations=len(rows),
            total_observations=len(rows),
            returned_points=len(rows),
            sampling="none",
            benchmark_curve_available=False,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.output.open("x") as handle:
        json.dump(project(), handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
