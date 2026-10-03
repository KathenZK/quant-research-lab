"""Export light frozen evidence and unbound Graph-shaped records; never deploy."""
import argparse
import json
from pathlib import Path
import shutil

import pandas as pd

from run_replay import FAMILY, INITIAL, dump, sha

TERMS = ("https://github.com/binance/binance-public-data/blob/"
         "f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md")
VARIANT = "M0288-BTCUSDT-1D-CDLHIGHWAVE-20261003"


def read(path):
    return json.loads(Path(path).read_text())


def curve(path):
    frame = pd.read_csv(path)
    peak = frame.equity.cummax().clip(lower=INITIAL)
    frame["drawdown"] = frame.equity / peak - 1
    return frame[["date", "equity", "drawdown"]]


def export(results, validation, recovery, out, private_detail):
    out, private_detail = Path(out), Path(private_detail)
    if private_detail.resolve().is_relative_to(out.resolve()):
        raise ValueError("Keep full unbound detail outside public evidence directory")
    if out.exists() or private_detail.exists():
        raise FileExistsError("Refuse to overwrite frozen publication")
    results = Path(results)
    v, r, summary = read(validation), read(recovery), read(results / "summary.json")
    spec = read(FAMILY / "specs/M0288-first-replay.json")
    assert v["status"] == "PASS_DIAGNOSTIC_NOT_STRICT" and r["status"] == "PASS"
    assert v["summary_sha256"] == sha(results / "summary.json")
    assert summary["spec_sha256"] == sha(FAMILY / "specs/M0288-first-replay.json")
    assert summary["input_sha256"] == spec["input"]["sha256"]
    assert r["files_byte_identical"] == 10
    for item in r["rows"]:
        assert sha(results / item["path"]) == item["sha256"]
    out.mkdir(parents=True)
    for name in ["summary.json", "base-trades.csv", "fee0-trades.csv",
                 "fee20-trades.csv", "delay2-trades.csv"]:
        shutil.copyfile(results / name, out / name)
    for name, original in [("independent-validation.json", validation),
                           ("recovery-validation.json", recovery)]:
        shutil.copyfile(original, out / name)
    curves = {}
    for name in ["base", "buyhold"]:
        light = curve(results / f"{name}-daily-nav.csv")
        light.to_csv(out / f"{name}-daily-nav-light.csv", index=False)
        curves[name] = light.to_dict(orient="records")
    attribution = {"provider": "Binance Vision", "license": "CC BY-NC-SA 4.0",
                   "additional_terms": TERMS,
                   "changes": "Native Freqtrade simulated trades, USDT daily NAV and derived metrics"}
    files = {p.name: {"sha256": sha(p), "bytes": p.stat().st_size}
             for p in sorted(out.iterdir()) if p.is_file()}
    manifest = {"record_id": "M0288", "origin_run_id": spec["run_id"],
                "files": files, "input_sha256": summary["input_sha256"],
                "protocol_sha256": summary["spec_sha256"],
                "private_full_results": r["rows"], "data_attribution": attribution,
                "state": "LOCAL_VALIDATED_AWAITING_COORDINATOR_REMOTE_SAVE"}
    dump(out / "result-manifest.json", manifest)
    lineage = {"origin_run_id": spec["run_id"], "variant_id": VARIANT,
               "fidelity_class": "HYPOTHESIS", "protocol_sha256": summary["spec_sha256"],
               "manifest_sha256": sha(out / "result-manifest.json")}
    audit = {"source_verification_status": "pinned_source_sha256_verified",
             "source_rule_attribution_status": "unchanged_source_native_reference_engine_hypothesis",
             "independent_validation": "PASS", "causality_validation": "PASS",
             "local_recovery": "PASS", "data_quality_status": "DIAGNOSTIC_ONLY",
             "trusted_input": False, "strict_replication": False, "oos_claim": False,
             "promotion": False, "definition_bound": False, "deployed": False}
    record = {"id": "M0288", "name": "PatternRecognition：日线 CDLHIGHWAVE=-100",
              "status": "tested_hypothesis_only", "tested_variants": 1,
              "tested_configurations": 4, "families": ["PUBLIC-M0288-PATTERN"],
              "reason": "原源码和原生参考引擎可执行；BTC单标的诊断明显落后买持、对执行延迟敏感。",
              "audit": audit, "implementations": [dict(lineage, family="PUBLIC-M0288-PATTERN")],
              "related_results": [lineage], "data_attribution": attribution}
    dump(out / "graph-record.json", record)

    def period(name):
        m = dict(summary["cases"][name])
        m.update({"start": "2023-01-01", "end": "2024-12-31"})
        return {"full": m}

    detail = {"id": "M0288", "run_id": spec["run_id"], **lineage,
              "name": record["name"], "family": "PUBLIC-M0288-PATTERN",
              "fidelity_reason": "Exact author class and native Freqtrade2026.9 reference engine; author runtime/universe unknown, offline precision fixture and daily OHLC fill assumptions.",
              "spec": {"source_url": read(FAMILY / "specs/source-preflight-checkpoint.json")["source_url"],
                       "params": spec}, "audit": audit, "lineage": lineage,
              "limitations": ["Original author runtime and asset universe unknown",
                              "DIAGNOSTIC_ONLY retrospective spot1d archive, PIT/tradability unproven",
                              "No original hyperopt sample or clean out-of-sample claim",
                              "Native daily OHLC trailing/ROI ordering is a model, not intraday reconstruction",
                              "No spread/slippage/orderbook model; fee stress changes actual exits",
                              "Native final-open force_exit differs from benchmark final-close liquidation",
                              "Native95% stake excludes entry fee; benchmark95% inclusive cash budget",
                              "Unbound Graph projection; no active database import or deployment"],
              "metrics": {"periods": period("base"), "same_instrument_benchmark": period("buyhold"),
                          "additional_native_bar_lag": period("delay2"),
                          "cost_sensitivity": {k: period(k) for k in ["fee0", "fee20"]}},
              "curve": curves["base"], "benchmark_curve": curves["buyhold"],
              "curve_meta": {"observations": 731, "total_observations": 731, "returned_points": 731,
                             "sampling": "none; every UTC daily close", "benchmark_curve_available": True,
                             "initial_equity": INITIAL, "unit": "USDT", "max_drawdown_sign": "negative",
                             "date_semantics": "UTC bar-open day label; mark after daily bar, no intraday NAV claim",
                             "metrics_frequency": "daily returns sqrt365 ddof1; initial equity included"},
              "data_attribution": attribution}
    dump(private_detail, detail)
    return {"status": "FILES_GENERATED_NOT_IMPORTED", "definition_bound": False,
            "deployed": False, "public_files": len(list(out.iterdir())),
            "private_detail_sha256": sha(private_detail)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["results", "validation", "recovery", "out", "private-detail"]:
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    print(json.dumps(export(a.results, a.validation, a.recovery, a.out, a.private_detail), indent=2))


if __name__ == "__main__":
    main()
