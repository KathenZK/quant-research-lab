"""事后只读核验器：不调用统计内核，不改变任何冻结计算或候选定义。"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from family_common import FAMILY, load_panel, save_json, sha, verify_lock


CONTRASTS = {
    "STRENGTH": ([(3, None), (1, None)], [1, -1]),
    "RESTART": ([(3, 3), (3, 2)], [1, -1]),
    "PATH": ([(3, 3), (3, 1)], [1, -1]),
    "SYNERGY": ([(3, 3), (3, 2), (3, 1), (3, 0)], [1, -1, -1, 1]),
    "STRENGTH_MODERATION": ([(3, 3), (3, 2), (1, 3), (1, 2)], [1, -1, -1, 1]),
    "HIGH_PM": ([(3, 3)], [1]),
}


def same(a, b):
    left, right = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if not np.array_equal(np.isfinite(left), np.isfinite(right)):
        raise AssertionError("finite masks differ")
    if not np.array_equal(np.isnan(left), np.isnan(right)) or not np.array_equal(np.isposinf(left), np.isposinf(right)) or not np.array_equal(np.isneginf(left), np.isneginf(right)):
        raise AssertionError("nonfinite identities differ")
    mask = np.isfinite(left)
    error = float(np.max(np.abs(left[mask] - right[mask]))) if mask.any() else 0.0
    if error > 1e-10:
        raise AssertionError(f"absolute error {error} exceeds 1e-10")
    return error


def original_rows(panel, granularity):
    answer, coverage = {}, {}
    for side, sign in (("LONG", 1), ("SHORT", -1)):
        mask = panel.feature_valid & panel.valid20 & panel[f"strength_{side}"].gt(0)
        part = panel.loc[mask, ["symbol", "ts", "q20", "l20"]].copy()
        part["x"] = panel.loc[mask, f"strength_{side}"].to_numpy()
        part["bin"] = np.where(part.x > 2, 3, np.where(part.x > 1, 2, 1))
        part["cell"] = 2 * panel.loc[mask, f"P_{side}"].to_numpy(dtype=int) + panel.loc[mask, f"M_{side}"].to_numpy(dtype=int)
        part["q20"] *= sign
        part["l20"] *= sign
        if granularity == "quarter":
            keys = list(zip(part.symbol, part.ts.dt.year, part.ts.dt.quarter))
        elif granularity == "fine":
            keys = list(zip(part.symbol, part.x.map(lambda x: math.floor(x * 4))))
        else:
            keys = list(part.symbol)
        part["stratum"] = pd.factorize(pd.Series(keys, dtype=object), sort=True)[0]
        for name, (arms, coefficients) in CONTRASTS.items():
            if granularity == "fine" and name not in ("RESTART", "PATH"):
                continue
            tables = []
            for b, c in arms:
                chosen = part.loc[part.bin.eq(b)]
                if c is not None:
                    chosen = chosen.loc[chosen.cell.eq(c)]
                tables.append(chosen.groupby("stratum").agg(n=("q20", "size"), q=("q20", "sum"), late=("l20", "sum")))
            support = set.intersection(*(set(t.index) for t in tables))
            num, den = np.zeros(2), 0.0
            if name == "HIGH_PM":
                total = tables[0].sum(axis=0)
                value = total[["q", "late"]].to_numpy() / total.n if total.n else np.array([np.nan, np.nan])
            else:
                for stratum in sorted(support):
                    cells = [table.loc[stratum] for table in tables]
                    w = 1.0 / sum(1.0 / c.n for c in cells)
                    num += w * sum(coef * c[["q", "late"]].to_numpy() / c.n for coef, c in zip(coefficients, cells))
                    den += w
                value = num / den if den else np.array([np.nan, np.nan])
            pm = part.loc[part.bin.eq(3) & part.cell.eq(3)]
            covered = int(pm.stratum.isin(support).sum())
            for y, v in zip(("Q20", "Late"), value):
                metric = f"{side}.{name}.{y}"
                answer[metric] = float(v)
                coverage[metric] = {"support_strata": len(support), "high_pm_complete_support_fraction": covered / len(pm) if len(pm) else np.nan}
    return answer, coverage


def confidence(point, values):
    valid = np.isfinite(point) & np.isfinite(values).all(axis=0)
    sd = np.full(len(point), np.nan)
    sd[valid] = values[:, valid].std(axis=0, ddof=1)
    valid &= np.isfinite(sd) & (sd > 0)
    lo, hi = np.full(len(point), -np.inf), np.full(len(point), np.inf)
    critical = np.nan
    if valid.any():
        statistic = np.abs((values[:, valid] - point[valid]) / sd[valid]).max(axis=1)
        critical = np.quantile(statistic, 0.95, method="linear")
        lo[valid] = point[valid] - critical * sd[valid]
        hi[valid] = point[valid] + critical * sd[valid]
    return lo, hi, sd, valid, critical


def main():
    lock = verify_lock()
    directory = FAMILY / "artifacts/p1-statistics"
    report = json.loads((directory / "report.json").read_text())
    for relative, digest in report["artifact_sha256"].items():
        if sha(directory / relative) != digest:
            raise AssertionError(f"retained hash mismatch: {relative}")
    panel, panel_identity = load_panel()
    point_table = pd.read_csv(directory / "point_statistics.csv")
    metrics, point = point_table.metric.tolist(), point_table.estimate.to_numpy()
    reference, _ = original_rows(panel, "symbol")
    point_error = same([reference[m] for m in metrics], point)
    sensitivity = pd.read_csv(directory / "descriptive_sensitivities.csv")
    sensitivity_errors = {}
    for label, granularity in (("SYMBOL_QUARTER", "quarter"), ("SYMBOL_FINE_STRENGTH_0.25", "fine")):
        estimated, coverage = original_rows(panel, granularity)
        subset = sensitivity.loc[sensitivity.sensitivity.eq(label)]
        error = same([estimated[m] for m in subset.metric], subset.estimate)
        for row in subset.itertuples():
            if row.support_strata != coverage[row.metric]["support_strata"]:
                raise AssertionError("descriptive support strata differ")
            same([row.high_pm_complete_support_fraction], [coverage[row.metric]["high_pm_complete_support_fraction"]])
        sensitivity_errors[label] = error
    del panel
    intervals = pd.read_csv(directory / "intervals.csv")
    t = json.loads((directory / "identity.json").read_text())["calendar_length"]
    reconstructed, blocks = [], []
    for block in (60, 120):
        folder = directory / f"block-{block}"
        checkpoint = json.loads((folder / "checkpoint.json").read_text())
        rng = np.random.default_rng(np.random.SeedSequence([20260909, block]))
        arrays, count = [], 0
        for shard in checkpoint["shards"]:
            if shard["start"] != count:
                raise AssertionError("replicate sequence is not contiguous")
            with np.load(folder / shard["file"], allow_pickle=False) as retained:
                values, starts = retained["replicates"], retained["starts"]
                expected = rng.integers(0, t, size=(len(values), math.ceil(t / block)), dtype=np.int64)
                if not np.array_equal(expected, starts):
                    raise AssertionError("frozen RNG prefix differs")
                arrays.append(values.copy())
                count += len(values)
        if count != checkpoint["completed"] or rng.bit_generator.state != checkpoint["rng_state"]:
            raise AssertionError("checkpoint identity differs")
        values = np.concatenate(arrays)
        stage_rows = []
        prior_passed = False
        for stage_file in sorted(folder.glob("stage-*.json")):
            stage = json.loads(stage_file.read_text())
            n = stage["replicates"]
            if prior_passed:
                raise AssertionError("continued after precision gate already passed")
            lo, hi, sd, valid, critical = confidence(point, values[:n])
            max_ratio = 0.0
            reconstructed_mc = []
            for k, subset in enumerate(np.split(values[:n], 5), 1):
                sublo, subhi, _, subvalid, _ = confidence(point, subset)
                if valid.any():
                    ratio = np.maximum(np.abs(sublo[valid] - lo[valid]), np.abs(subhi[valid] - hi[valid])) / sd[valid]
                    max_ratio = max(max_ratio, float(np.max(ratio)))
                    if not subvalid[valid].all():
                        max_ratio = np.inf
                    reconstructed_mc.extend((k, metrics[j], float(r)) for j, r in zip(np.flatnonzero(valid), ratio))
            mc_passed = max_ratio <= 0.25
            if mc_passed != stage["mc"]["passed"]:
                raise AssertionError("MC precision decision differs")
            retained_mc = pd.read_csv(folder / f"mc-{n:06d}.csv").set_index(["batch", "metric"])
            for k, metric, ratio in reconstructed_mc:
                same([ratio], [retained_mc.loc[(k, metric), "difference_in_full_sd"]])
            stage_rows.append({"replicates": n, "mc_passed": mc_passed, "max_endpoint_difference_in_full_sd": max_ratio})
            prior_passed = mc_passed
        if count not in (50000, 100000, 200000) or not stage_rows or stage_rows[-1]["replicates"] != count:
            raise AssertionError("replicate count/stages violate contract")
        saved = intervals.loc[intervals.block.eq(str(block))].set_index("metric").loc[metrics]
        errors = [same(saved.lower, lo), same(saved.upper, hi), same(saved.sd, sd), same(saved.critical, np.full(24, critical))]
        reconstructed.append((lo, hi, valid, prior_passed))
        blocks.append({"block": block, "replicates": count, "estimable_dimensions": int(valid.sum()), "critical": float(critical), "interval_max_error": max(errors), "stages": stage_rows})
    lower = np.minimum(reconstructed[0][0], reconstructed[1][0])
    upper = np.maximum(reconstructed[0][1], reconstructed[1][1])
    reliable = reconstructed[0][2] & reconstructed[1][2]
    precise = all(r[3] for r in reconstructed)
    saved = intervals.loc[intervals.block.eq("envelope")].set_index("metric").loc[metrics]
    envelope_error = max(same(saved.lower, lower), same(saved.upper, upper))
    official = json.loads((directory / "decisions.json").read_text())
    statuses = {}
    for row in official["associations"]:
        indices = [metrics.index(f"{row['direction']}.{row['contrast']}.{y}") for y in ("Q20", "Late")]
        decision = "NUMERICAL_PRECISION_INSUFFICIENT" if not precise else "INFERENCE_UNRELIABLE" if not reliable[indices].all() else "POSITIVE_ASSOCIATION" if (lower[indices] > 0).all() else "RULE_NOT_SUPPORTED" if (upper[indices] <= 0).any() else "INSUFFICIENT_EVIDENCE"
        if decision != row["status"]:
            raise AssertionError("association verdict differs")
        statuses[(row["direction"], row["contrast"])] = decision
    for row in official["candidates"]:
        d = row["direction"]
        q, late = [metrics.index(f"{d}.HIGH_PM.{y}") for y in ("Q20", "Late")]
        state = [statuses[(d, c)] for c in ("RESTART", "PATH", "HIGH_PM")]
        decision = "NUMERICAL_PRECISION_INSUFFICIENT" if not precise else "INFERENCE_UNRELIABLE" if "INFERENCE_UNRELIABLE" in state else "HISTORICAL_PRICE_CANDIDATE" if lower[q] > 0.25 and lower[late] > 0 and state[:2] == ["POSITIVE_ASSOCIATION"] * 2 else "RULE_NOT_SUPPORTED" if upper[q] <= 0.25 or upper[late] <= 0 or "RULE_NOT_SUPPORTED" in state[:2] else "INSUFFICIENT_EVIDENCE"
        if decision != row["status"]:
            raise AssertionError("candidate verdict differs")
    verify_lock()
    receipt = {"status": "PASS", "role": "Independent readback; no frozen kernel import or economic selection", "script_sha256": sha(__file__), "computation_lock_sha256": lock["computation_lock_sha256"], **panel_identity, "report_sha256": sha(directory / "report.json"), "retained_artifact_hashes_verified": len(report["artifact_sha256"]), "original_rows_point_max_error": point_error, "descriptive_sensitivity_max_errors": sensitivity_errors, "blocks": blocks, "envelope_max_error": envelope_error, "all_verdicts_reproduced": True}
    save_json(FAMILY / "artifacts/statistics-independent-audit.json", receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
