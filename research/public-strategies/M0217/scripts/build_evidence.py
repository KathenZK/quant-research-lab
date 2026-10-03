"""Create local frozen lightweight lineage and full private Graph detail once."""
import csv
import hashlib
import json
import platform
import sys
from pathlib import Path

FAMILY = Path(__file__).resolve().parents[1]
ART = FAMILY / "artifacts/20261003-first-replay"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, data):
    with (ART / name).open("x") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")


def main():
    spec_path = FAMILY / "specs/M0217-first-replay.json"
    config = json.loads(spec_path.read_text())
    summary = json.loads((ART / "results/summary.json").read_text())
    write("input-reference.json", dict(input_sha256=config["input_sha256"], dataset_id="binance.spot.BTCUSDT.1d.M0216.20261003", source_manifest="../../../1d-m0216-sma-cross/artifacts/20261003-first-replay/input-manifest.json", rows=762, warmup_rows=31, evaluation_rows=731, gaps=0, duplicates=0, pit_proven=False, tradability_proven=False, profile=config["data_profile"]))
    write("source-audit.json", dict(source_url=config["source_url"], access_method="web open", readable_lines=0, verified_tweet_content=False, catalog_confirmation="Coordinator supplied legally read stable ID M0217 and rule; this worker did not materialize master CSV", interpretation_assumptions=config["assumptions"]))
    write("environment.json", dict(python=sys.version, platform=platform.platform(), dependencies="stdlib plus strategy_lab.research.exposure for preregistration; repository uv.lock", frozen_input_hash=config["input_sha256"]))
    manifest = {str(p.relative_to(FAMILY)): sha(p) for p in sorted(FAMILY.glob("scripts/*.py"))}
    manifest.update({str(p.relative_to(FAMILY)): sha(p) for p in sorted((ART / "results").glob("*"))})
    manifest.update({str(spec_path.relative_to(FAMILY)): sha(spec_path), "artifacts/20261003-first-replay/validation.json": sha(ART / "validation.json")})
    write("result-manifest.json", dict(record_id="M0217", files=manifest, input_sha256=config["input_sha256"], protocol_sha256=sha(spec_path), overwrite_policy="frozen: never overwrite", strategy_configurations=3, benchmarks=1, strict_reproductions=0))
    full = dict(summary["base"]["full"], sharpe=summary["base"]["full"]["sharpe_zero_cash"], start="2023-01-01", end="2024-12-31")
    reason = "原帖正文不可读；昨日振幅、当天退出和BTCUSDT实例均为显式假设，日线不能证明真实触价成交。"
    record = dict(id="M0217", name="日线波动突破0.8倍振幅持有1日", status="tested_hypothesis_only", reason="完成假设回测与独立校验；交易成本敏感，未晋级。", tested_variants=1, families=[config["family"]], audit=dict(source_verification_status="unreadable", source_rule_attribution_status="catalog_anchored_hypothesis"), implementations=[dict(variant_id=config["variant_id"], family=config["family"], origin_run_id="M0217-20261003-first-replay", fidelity_class="HYPOTHESIS")], related_results=[dict(origin_run_id="M0217-20261003-first-replay", variant_id=config["variant_id"], fidelity_class="HYPOTHESIS", protocol_sha256=sha(spec_path), manifest_sha256=sha(ART / "result-manifest.json"))])
    write("graph-record.json", record)
    with (ART / "results/base-nav.csv").open() as f:
        curve = [dict(date=r["date"], equity=float(r["equity"]), drawdown=float(r["drawdown"])) for r in csv.DictReader(f)]
    with (ART / "results/buy_hold-nav.csv").open() as f:
        benchmark_curve = [dict(date=r["date"], equity=float(r["equity"]), drawdown=float(r["drawdown"])) for r in csv.DictReader(f)]
    write("graph-detail.json", dict(run_id="M0217-20261003-first-replay", origin_run_id="M0217-20261003-first-replay", id="M0217", variant_id=config["variant_id"], name=record["name"], family=config["family"], fidelity_class="HYPOTHESIS", fidelity_reason=reason, spec=config, metrics=dict(full, periods=dict(full=full)), benchmark=dict(name="BTCUSDT 95% buy-and-hold", metrics=summary["buy_hold"]["full"]), cost_sensitivity={k:summary[k]["full"] for k in ("base", "fee0", "fee20")}, equity_curve=curve, benchmark_curve=benchmark_curve, limitations=config["assumptions"]+["Historical archive revisions/PIT feed availability unproven", "2023–2024 already exposed; no untouched OOS claim", "Costs of 20bps per side reverse performance; not promoted or live-ready"], lineage=dict(input_sha256=config["input_sha256"], protocol_sha256=sha(spec_path), manifest_sha256=sha(ART / "result-manifest.json"), license="CC BY-NC-SA 4.0", attribution="Binance Vision"), curve_meta=dict(observations=731, total_observations=731, returned_points=731, sampling="none", benchmark_curve_available=True)))


if __name__ == "__main__":
    main()
