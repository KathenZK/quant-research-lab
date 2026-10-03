"""Existing Graph projection shape with explicit ADAPTED classification; no import/deploy."""

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read(p):
    return json.loads(Path(p).read_text())


def write(p, obj):
    with Path(p).open("x") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")


def rows(p):
    with Path(p).open() as f:
        return list(csv.DictReader(f))


def export(results, recovery, output, private):
    results, out, private = map(Path, [results, output, private])
    private.mkdir(parents=True, exist_ok=False)
    sp = ROOT / "specs/M0311-first-replay.json"
    s = read(sp)
    summary = read(results / "summary.json")
    restored = read(recovery)
    checks = [
        "original-source-validation.json",
        "independent-validation.json",
        "small-balance-validation.json",
        "execution-time-validation.json",
        "causality-validation.json",
        "additional-prefix-validation.json",
    ]
    for name in checks:
        assert read(out / name)["status"] == "PASS"
    assert restored["status"] == "PASS" and restored["all_result_files_byte_identical"]
    assert summary["protocol_sha256"] == restored["protocol_sha256"] == sha(sp)
    manifest = {
        "id": "M0311",
        "origin_run_id": s["run_id"],
        "protocol_sha256": sha(sp),
        "input_sha256": s["input"]["sha256"],
        "source_manifest_sha256": sha(ROOT / "specs/source-manifest.json"),
        "files": {
            p.name: {"bytes": p.stat().st_size, "sha256": sha(p)}
            for p in sorted(results.iterdir())
            if p.is_file()
        },
        "checks": {n: sha(out / n) for n in checks},
        "recovery_sha256": sha(recovery),
        "public_boundary": "No raw OHLCV/full5mNAV/signals/source text. Summary,dailycurves and clearly labeled first20+last20 trade samples only.",
    }
    write(out / "result-manifest.json", manifest)
    shutil.copyfile(recovery, out / "local-recovery.json")
    light = out / "results"
    light.mkdir(exist_ok=False)
    shutil.copyfile(results / "summary.json", light / "summary.json")
    tradeinfo = {}
    for case in s["cases"]:
        n = case["name"]
        source = results / f"{n}-trades.csv"
        full = rows(source)
        sample = full if len(full) <= 40 else full[:20] + full[-20:]
        target = light / f"{n}-trades-sample.csv"
        with target.open("x", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(full[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(sample)
        tradeinfo[n] = {
            "full_rows": len(full),
            "sample_rows": len(sample),
            "selection": "all if<=40 else first20+last20; not representative statistical sampling",
            "full_sha256": sha(source),
            "sample_sha256": sha(target),
        }
    write(out / "trade-sample-manifest.json", tradeinfo)
    curves = {}
    for name in ["base", "buyhold"]:
        full = rows(results / f"{name}-nav.csv")
        daily = rows(results / f"{name}-daily-nav.csv")
        peak = 100000.0
        dd = {}
        for row in full:
            eq = float(row["equity"])
            peak = max(peak, eq)
            dd[row["bar_index"]] = eq / peak - 1
        curves[name] = [
            {
                "date": r["date"],
                "equity": float(r["equity"]),
                "nav": float(r["nav"]),
                "drawdown": dd[r["bar_index"]],
            }
            for r in daily
        ]
        with (out / f"{name}-nav-light.csv").open("x", newline="") as f:
            w = csv.DictWriter(
                f, fieldnames=["date", "equity", "nav", "drawdown"], lineterminator="\n"
            )
            w.writeheader()
            w.writerows(curves[name])
    lineage = {
        "origin_run_id": s["run_id"],
        "variant_id": s["variant_id"],
        "fidelity_class": "ADAPTED",
        "execution_class": "ADAPTED_EXECUTION_PROXY",
        "protocol_sha256": sha(sp),
        "manifest_sha256": sha(out / "result-manifest.json"),
    }
    audit = {
        "source_verification_status": "pinned_source_and_CMF_original_arrays_identical",
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
        "remote_backup_verified": False,
    }
    limits = [
        "ADAPTED_EXECUTION_PROXY: original GTC limit entry/exit/stop replaced with nextopen/marketstyle full fills",
        "CMF21 original NaN/sign rules and strict ROI>1% preserved; exit_profit_onlyFalse",
        "Availability-selected2024 already exposed, no OOS or original author runtime claim",
        "Fractional dust trading continues below real minimum notionals; near-zero balances are theoretical proxy outputs",
        "No original limit queue/timeout/fill validation; no execution guarantee",
        "Only derived light curves and explicitly sampled fills public; full logs private",
    ]
    attr = {
        "provider": "Binance",
        "license": "CC BY-NC-SA-4.0 plus Binance Dataset Terms",
        "terms_url": "https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md",
        "changes": "CMF21, declared adapted OHLC accounting, metrics,daily sampling",
    }
    record = {
        "id": "M0311",
        "name": "TechnicalExampleStrategy：BTC现货5m CMF21执行代理",
        "status": "tested_adapted_only",
        "reason": "原CMF信号与strict ROI核对通过；原limit订单改为明示成交代理。全部预定配置显著亏损，不晋升。",
        "tested_variants": 1,
        "strategy_configurations": 4,
        "control_configurations": 1,
        "families": [s["family"]],
        "audit": audit,
        "implementations": [dict(lineage, family=s["family"])],
        "related_results": [lineage],
        "data_attribution": attr,
        "limitations": limits,
    }
    write(out / "graph-record.json", record)

    def period(case):
        m = dict(summary["results"][case]["metrics"])
        m["max_drawdown"] = -m["max_drawdown"]
        m["start"] = "2024-01-01"
        m["end"] = "2024-12-31"
        return {"full": m}

    detail = {
        "id": "M0311",
        "run_id": s["run_id"],
        **lineage,
        "name": record["name"],
        "family": s["family"],
        "audit": audit,
        "lineage": lineage,
        "fidelity_reason": limits[0],
        "spec": {
            "source_url": read(ROOT / "specs/source-manifest.json")["files"][0]["url"],
            "params": s,
        },
        "limitations": limits,
        "metrics": {
            "periods": period("base"),
            "same_instrument_benchmark": period("buyhold"),
            "additional_native_bar_lag": period("delay2"),
            "cost_sensitivity": {n: period(n) for n in ["fee0", "fee20"]},
        },
        "curve": curves["base"],
        "curve_meta": {
            "rows": 366,
            "source_observations": 105408,
            "initial_equity": 100000,
            "sampling": "UTC daily last native5m close",
            "max_drawdown_sign": "negative",
            "max_drawdown_source": "all105408 native bar-close states plus initial capital",
            "sharpe_frequency": "UTCdaily,sqrt365,ddof1",
            "sampled_curve_sha256": sha(out / "base-nav-light.csv"),
            "full_curve_sha256": sha(results / "base-nav.csv"),
        },
        "data_attribution": attr,
    }
    write(private / "graph-detail.private.json", detail)
    write(
        out / "graph-projection-receipt.json",
        {
            "id": "M0311",
            "status": "PREPARED_NOT_IMPORTED",
            "private_detail_sha256": sha(private / "graph-detail.private.json"),
            "private_detail_bytes": (private / "graph-detail.private.json")
            .stat()
            .st_size,
            "definition_bound": False,
            "deployed": False,
        },
    )
    return {
        "id": "M0311",
        "status": "PASS",
        "full_result_files": len(manifest["files"]),
        "public_trade_samples": sum(x["sample_rows"] for x in tradeinfo.values()),
        "deployed": False,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--results", required=True)
    p.add_argument("--recovery", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--private-output", required=True)
    a = p.parse_args()
    print(
        json.dumps(export(a.results, a.recovery, a.output, a.private_output), indent=2)
    )
