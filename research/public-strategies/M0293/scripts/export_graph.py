#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Light Graph-compatible records and result hashes; never imports or deploys."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, obj):
    with Path(path).open("x") as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def export(results, recovery, output, private_output):
    results, out, private = Path(results), Path(output), Path(private_output)
    out.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, exist_ok=False)
    specpath = ROOT / "specs/M0293-first-replay.json"
    spec = read(specpath)
    summary = read(results / "summary.json")
    restored = read(recovery)
    checks = [
        "original-source-validation.json",
        "execution-time-validation.json",
        "independent-validation.json",
        "causality-validation.json",
    ]
    for filename in checks:
        assert read(out / filename)["status"] == "PASS"
    assert restored["status"] == "PASS" and restored["all_result_files_byte_identical"]
    assert summary["protocol_sha256"] == sha(specpath) == restored["protocol_sha256"]
    assert (
        summary["input_sha256"] == spec["input"]["sha256"] == restored["input_sha256"]
    )
    manifest = {
        "id": "M0293",
        "origin_run_id": spec["run_id"],
        "protocol_sha256": sha(specpath),
        "input_sha256": spec["input"]["sha256"],
        "source_manifest_sha256": sha(ROOT / "specs/source-manifest.json"),
        "files": {
            p.name: {"sha256": sha(p), "bytes": p.stat().st_size}
            for p in sorted(results.iterdir())
            if p.is_file()
        },
        "checks": {name: sha(out / name) for name in checks},
        "recovery_sha256": sha(recovery),
        "replay_code_sha256": sha(ROOT / "scripts/run_replay.py"),
        "public_boundary": "No raw market data/full 4h curves/signals or third-party source text; lightweight summary, trades, daily base projection and fingerprints only.",
    }
    write(out / "result-manifest.json", manifest)
    shutil.copyfile(recovery, out / "local-recovery.json")
    light = out / "results"
    light.mkdir(exist_ok=False)
    for filename in ["summary.json"] + [
        f"{case['name']}-trades.csv" for case in spec["cases"]
    ]:
        shutil.copyfile(results / filename, light / filename)
    with (results / "base-nav.csv").open() as stream:
        full = list(csv.DictReader(stream))
    with (results / "base-daily-nav.csv").open() as stream:
        daily = list(csv.DictReader(stream))
    peak = spec["execution"]["initial_cash"]
    dd = {}
    for row in full:
        equity = float(row["equity"])
        peak = max(peak, equity)
        dd[row["bar_index"]] = equity / peak - 1
    curve = [
        {
            "date": row["date"],
            "equity": float(row["equity"]),
            "nav": float(row["nav"]),
            "drawdown": dd[row["bar_index"]],
        }
        for row in daily
    ]
    with (out / "base-nav-light.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["date", "equity", "nav", "drawdown"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(curve)
    lineage = {
        "origin_run_id": spec["run_id"],
        "variant_id": spec["variant_id"],
        "fidelity_class": "HYPOTHESIS",
        "protocol_sha256": sha(specpath),
        "manifest_sha256": sha(out / "result-manifest.json"),
    }
    audit = {
        "source_verification_status": "pinned_source_bytes_verified_original_class_signal_arrays_identical",
        "independent_validation": "PASS",
        "causality_validation": "PASS",
        "local_recovery": "PASS",
        "strict_replication": False,
        "data_quality_status": "DIAGNOSTIC_ONLY",
        "trusted_input": False,
        "strict_core_finality": "NOT_ESTABLISHED",
        "pit_proven": False,
        "oos_claim": False,
        "promotion": False,
        "definition_bound": False,
        "deployed": False,
    }
    attribution = {
        "provider": "Binance",
        "license": "CC BY-NC-SA-4.0 plus Binance Dataset Terms",
        "terms_url": "https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md",
        "changes": "EMA8/21 and closed48h SMA50 calculation, declared OHLC execution/accounting, metrics and daily sampling",
    }

    def period(case):
        metric = dict(summary["results"][case]["metrics"])
        metric["max_drawdown"] = -metric["max_drawdown"]
        metric["start"] = "2023-01-01"
        metric["end"] = "2024-12-31"
        return {"full": metric}

    record = {
        "id": "M0293",
        "name": "ReinforcedAverageStrategy：BTC现货4h EMA交叉与48h SMA过滤",
        "status": "tested_hypothesis_only",
        "reason": "原始信号和48h闭合合并核对通过；SMA50预热不足如实保留；常量ROI50%、止损20%，非原框架严格复现。",
        "tested_variants": 1,
        "strategy_configurations": 4,
        "control_configurations": 1,
        "families": [spec["family"]],
        "audit": audit,
        "implementations": [dict(lineage, family=spec["family"])],
        "related_results": [lineage],
        "data_attribution": attribution,
    }
    write(out / "graph-record.json", record)
    detail = {
        "id": "M0293",
        "run_id": spec["run_id"],
        **lineage,
        "name": record["name"],
        "family": spec["family"],
        "audit": audit,
        "lineage": lineage,
        "fidelity_reason": "Original class EMA signals and closed48h SMA50 preserved; researcher-selected BTCUSDT instance, limited-history initialization and declared OHLC execution.",
        "spec": {
            "source_url": read(ROOT / "specs/source-manifest.json")["files"][0]["url"],
            "params": spec,
        },
        "limitations": [
            "HYPOTHESIS; DIAGNOSTIC_ONLY untrusted retrospective archives; no strict/PIT/OOS claim",
            "Only31 days preload;48h SMA50 unavailable for first413 evaluation bars; retain original NaN filter without shifting evaluation",
            "ROI fixed50% and stop20%; no trailing despite inactive positive/offset fields",
            "Resampled48h SMA value becomes usable only on final constituent4h close; merge offset44h, forward fill only",
            "Full fractional fills with assumed fees/slip; no order book/lot constraints",
            "Prepared file is not live definition binding, import or deployment",
        ],
        "metrics": {
            "periods": period("base"),
            "same_instrument_benchmark": period("buyhold"),
            "additional_native_bar_lag": period("delay2"),
            "cost_sensitivity": {k: period(k) for k in ("fee0", "fee20")},
        },
        "curve": curve,
        "curve_meta": {
            "rows": len(curve),
            "source_observations": len(full),
            "initial_equity": 100000,
            "sampling": "UTC daily last native4h bar, no interpolation",
            "max_drawdown_sign": "negative",
            "max_drawdown_source": "all4386 bar-close states plus initial equity, not daily-only",
            "sharpe_frequency": "UTC daily returns, sqrt365,ddof1,initialcapital included",
            "sampled_curve_sha256": sha(out / "base-nav-light.csv"),
            "full_curve_sha256": sha(results / "base-nav.csv"),
        },
        "data_attribution": attribution,
    }
    write(private / "graph-detail.private.json", detail)
    write(
        out / "graph-projection-receipt.json",
        {
            "status": "PREPARED_NOT_IMPORTED",
            "id": "M0293",
            "private_detail_sha256": sha(private / "graph-detail.private.json"),
            "private_detail_bytes": (private / "graph-detail.private.json")
            .stat()
            .st_size,
            "definition_bound": False,
            "deployed": False,
        },
    )
    return {
        "status": "PASS",
        "full_result_hashes": len(manifest["files"]),
        "public_base_curve_points": len(curve),
        "id": "M0293",
        "deployed": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--recovery", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--private-output", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            export(args.results, args.recovery, args.output, args.private_output),
            indent=2,
        )
    )
