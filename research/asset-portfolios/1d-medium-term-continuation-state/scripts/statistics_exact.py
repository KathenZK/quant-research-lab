"""BIN-1D-MTCS 完整比率bootstrap精度修复；原信号、估计量及区间均不变。

压缩充分统计不是线性化：每一复制重新计算所有分母、资产权重和对照均值。
保存不可覆盖的复制分块，只有拥有明确身份的检查点元数据允许原子更新。
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Callable

import numpy as np
import pandas as pd

_SPEC = importlib.util.spec_from_file_location("_mtcs_frozen_statistics_for_exact", Path(__file__).with_name("statistics.py"))
base = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = base
_SPEC.loader.exec_module(base)

REFERENCE_REPS = 2048
PARITY_ATOL = 1e-10
DEFAULT_BATCH = 256
DEFAULT_CHECKPOINT = 4096


def file_sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value) -> bytes:
    return (json.dumps(base._clean(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _atomic_bytes(path: Path, value: bytes, immutable: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists():
        if path.read_bytes() != value:
            raise FileExistsError(f"Immutable artifact differs: {path}")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".pending-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _json(path: Path, value, immutable=True) -> None:
    _atomic_bytes(path, _json_bytes(value), immutable=immutable)


def _array(path: Path, values: np.ndarray) -> str:
    buffer = io.BytesIO()
    np.save(buffer, values, allow_pickle=False)
    data = buffer.getvalue()
    _atomic_bytes(path, data)
    return sha256(data).hexdigest()


def _csv(path: Path, frame: pd.DataFrame) -> None:
    _atomic_bytes(path, frame.to_csv(index=False).encode())


@contextmanager
def _lock(directory: Path):
    import fcntl
    with (directory / "run.lock").open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another process owns this exact run") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def pack_daily(prepared) -> np.ndarray:
    """每币15字段+全组20字段，保留原46估计量所需全部信息。"""
    source = prepared.sufficient
    days, assets = source.shape[:2]
    packed = np.empty((days, 15 * assets + 20), dtype=np.float64)
    offset = 0
    packed[:, offset:offset + 10 * assets] = source[:, :, 1:, 0].reshape(days, 10 * assets)
    offset += 10 * assets
    packed[:, offset:offset + 3 * assets] = source[:, :, 0, :].reshape(days, 3 * assets)
    offset += 3 * assets
    packed[:, offset:offset + 2 * assets] = source[:, :, [3, 4], 1].reshape(days, 2 * assets)
    offset += 2 * assets
    packed[:, offset:] = source[:, :, 1:, 1:].sum(axis=1).reshape(days, 20)
    return packed


def estimate_packed(totals: np.ndarray, assets: int) -> tuple[np.ndarray, np.ndarray]:
    """完整非线性估计；压缩前后代数等价，不采用IF或固定对照。"""
    one = totals.ndim == 1
    if one:
        totals = totals[None]
    if totals.ndim != 2 or totals.shape[1] != 15 * assets + 20:
        raise ValueError("wrong packed sufficient-statistics shape")
    b = len(totals)
    offset = 10 * assets
    selected_counts = totals[:, :offset].reshape(b, assets, 10)
    control = totals[:, offset:offset + 3 * assets].reshape(b, assets, 3)
    offset += 3 * assets
    mq = totals[:, offset:offset + 2 * assets].reshape(b, assets, 2)
    selected_sums = totals[:, offset + 2 * assets:].reshape(b, 10, 2)
    counts = selected_counts.sum(axis=1)
    nc = control[:, :, 0]
    mean_cq = np.divide(control[:, :, 1], nc, out=np.zeros_like(nc), where=nc > 0)
    mean_cl = np.divide(control[:, :, 2], nc, out=np.zeros_like(nc), where=nc > 0)
    out = np.full((b, len(base.METRICS)), np.nan)
    for ui, unit in enumerate(base.UNITS):
        ns = selected_counts[:, :, ui]
        n = counts[:, ui]
        if ((ns > 0) & (nc <= 0)).any():
            raise ValueError("positive selected weight with zero all-day control")
        direction = 1.0 if unit.endswith("LONG") else -1.0
        for yi, ci in ((0, mean_cq), (1, mean_cl)):
            mu = np.divide(selected_sums[:, ui, yi], n, out=np.full_like(n, np.nan), where=n > 0)
            mc = np.divide((ns * ci).sum(axis=1), n, out=np.full_like(n, np.nan), where=n > 0)
            out[:, 4 * ui + 2 * yi] = direction * mu
            out[:, 4 * ui + 2 * yi + 1] = direction * (mu - mc)
        if unit.startswith("S"):
            side_index = 0 if direction == 1 else 1
            nm = selected_counts[:, :, 2 + side_index]
            if ((ns > 0) & (nm <= 0)).any():
                raise ValueError("positive selected weight with zero MA7 control")
            mi = np.divide(mq[:, :, side_index], nm, out=np.zeros_like(nm), where=nm > 0)
            mm = np.divide((ns * mi).sum(axis=1), n, out=np.full_like(n, np.nan), where=n > 0)
            out[:, base.METRIC_INDEX[(unit, "DeltaFilter")]] = out[:, 4 * ui] - direction * mm
    return (out[0], counts[0]) if one else (out, counts)


def exact_batch(starts: np.ndarray, full: np.ndarray | None, tail: np.ndarray | None,
                days: int, block: int) -> np.ndarray:
    """完整块起点计数×充分统计的DGEMM；最后一个尾块按原长度截断。"""
    complete, remainder = divmod(days, block)
    if complete:
        weights = np.zeros((len(starts), days), dtype=np.float64)
        np.add.at(weights, (np.arange(len(starts))[:, None], starts[:, :complete]), 1.0)
        totals = weights @ full
    else:
        totals = np.zeros((len(starts), tail.shape[1]), dtype=np.float64)
    if remainder:
        totals += tail[starts[:, complete]]
    return totals


def reference_values(prepared, block: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """调用原完整逐资产算法重现原2048组起点，IF值不参与参考。"""
    days = len(prepared.dates)
    starts = base.draw_starts(seed, block, days, REFERENCE_REPS)
    complete, remainder = divmod(days, block)
    full = base.circular_block_sums(prepared.sufficient, block) if complete else None
    tail = base.circular_block_sums(prepared.sufficient, remainder) if remainder else None
    values = np.empty((REFERENCE_REPS, 46), dtype=np.float64)
    counts = np.empty((REFERENCE_REPS, 10), dtype=np.float64)
    width = int(np.prod(prepared.sufficient.shape[1:]))
    batch = max(1, min(16, 32_000_000 // max(1, starts.shape[1] * width * 8)))
    for begin in range(0, REFERENCE_REPS, batch):
        end = min(begin + batch, REFERENCE_REPS)
        totals = base._sum_draws(full, tail, starts[begin:end], days, block)
        values[begin:end], counts[begin:end] = base.estimate(totals)
    return values, counts


def _validate_shards(directory: Path, checkpoint: dict) -> None:
    expected_begin = 0
    for shard in checkpoint["shards"]:
        if shard["begin"] != expected_begin or shard["end"] <= shard["begin"]:
            raise ValueError("checkpoint shard ranges are inconsistent")
        path = directory / shard["path"]
        if file_sha(path) != shard["sha256"]:
            raise ValueError(f"checkpoint shard hash mismatch: {path}")
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        if array.shape != (shard["end"] - shard["begin"], 46) or array.dtype != np.float64:
            raise ValueError("checkpoint shard shape/dtype mismatch")
        expected_begin = shard["end"]
    if checkpoint["processed"] != expected_begin:
        raise ValueError("checkpoint progress differs from committed shards")


def _reference_parity(points, errors, reference, begin, current_max):
    end = min(begin + len(errors), len(reference))
    if begin >= end:
        return current_max
    actual = points + errors[:end - begin]
    wanted = reference[begin:end]
    if not np.array_equal(np.isfinite(actual), np.isfinite(wanted)):
        raise ValueError("full-bootstrap reference finite-mask mismatch")
    difference = np.abs(np.where(np.isfinite(wanted), actual - wanted, 0.0))
    maximum = np.maximum(current_max, difference.max(axis=0))
    if (maximum > PARITY_ATOL).any():
        raise ValueError(f"FULL_REFERENCE_PARITY_FAILED max_error={maximum.max():.12g}")
    return maximum


def validate_parity(panel: pd.DataFrame, output_dir: Path, seed: int = 20260908,
                    batch_reps: int = DEFAULT_BATCH, external_pins: dict | None = None) -> dict:
    """单独的2048完整复制验收；无百万次重算、置信区间或经济裁决。"""
    prepared = base.prepare(panel)
    if len(prepared.dates) == 0 or batch_reps < 1:
        raise ValueError("no observable labels or invalid batch size")
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("parity output must be new or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    packed = pack_daily(prepared)
    points, _ = base.estimate(prepared.sufficient.sum(axis=0))
    packed_points, _ = estimate_packed(packed.sum(axis=0), len(prepared.assets))
    if not np.allclose(points, packed_points, atol=PARITY_ATOL, rtol=0, equal_nan=True):
        raise ValueError("packed point parity failed")
    rows = []
    for block in base.BLOCK_LENGTHS:
        reference, reference_counts = reference_values(prepared, block, seed)
        starts = base.draw_starts(seed, block, len(packed), REFERENCE_REPS)
        complete, remainder = divmod(len(packed), block)
        full = base.circular_block_sums(packed, block) if complete else None
        tail = base.circular_block_sums(packed, remainder) if remainder else None
        maximum = np.zeros(46)
        for begin in range(0, REFERENCE_REPS, batch_reps):
            end = min(begin + batch_reps, REFERENCE_REPS)
            totals = exact_batch(starts[begin:end], full, tail, len(packed), block)
            values, counts = estimate_packed(totals, len(prepared.assets))
            if not np.array_equal(counts, reference_counts[begin:end]):
                raise ValueError("full bootstrap selected counts differ")
            maximum = _reference_parity(points, values - points, reference, begin, maximum)
        for mi, (unit, metric) in enumerate(base.METRICS):
            rows.append({"block_days": block, "unit": unit, "metric": metric,
                         "checked_replicates": REFERENCE_REPS, "maximum_absolute_error": maximum[mi],
                         "absolute_tolerance": PARITY_ATOL, "passed": maximum[mi] <= PARITY_ATOL})
    _csv(output_dir / "reference-parity.csv", pd.DataFrame(rows))
    result = {"status": "PASS", "mode": "PARITY_ONLY_NO_INFERENCE", "seed": seed,
              "replicates_per_block": REFERENCE_REPS, "metrics": 46,
              "maximum_absolute_error": max(r["maximum_absolute_error"] for r in rows),
              "input_sha256": prepared.input_sha256, "external_pins": external_pins or {},
              "source_sha256": file_sha(Path(__file__)), "original_source_sha256": file_sha(Path(base.__file__)),
              "artifact_sha256": {"reference-parity.csv": file_sha(output_dir / "reference-parity.csv")}}
    _json(output_dir / "report.json", result)
    return base._clean(result)


def analyze(panel: pd.DataFrame, output_dir: Path, bootstrap_reps: int = 1_000_000,
            seed: int = 20260908, *, batch_reps: int = DEFAULT_BATCH,
            checkpoint_reps: int = DEFAULT_CHECKPOINT, external_pins: dict | None = None,
            baseline_dir: Path | None = None, progress_callback: Callable | None = None) -> dict:
    for name, value, minimum in (("bootstrap_reps", bootstrap_reps, 4), ("batch_reps", batch_reps, 1),
                                 ("checkpoint_reps", checkpoint_reps, 1), ("seed", seed, 0)):
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise ValueError(f"invalid {name}")
    prepared = base.prepare(panel)
    if len(prepared.dates) == 0:
        raise ValueError("no observable labels; exact bootstrap is undefined")
    points, event_counts = base.estimate(prepared.sufficient.sum(axis=0))
    packed = pack_daily(prepared)
    packed_points, packed_counts = estimate_packed(packed.sum(axis=0), len(prepared.assets))
    if not np.allclose(points, packed_points, atol=PARITY_ATOL, rtol=0, equal_nan=True):
        raise ValueError("packed point estimates differ from original estimator")
    if not np.array_equal(event_counts, packed_counts):
        raise ValueError("packed event counts differ")
    baseline_dir = Path(baseline_dir) if baseline_dir is not None else None
    baseline_hashes = {}
    if baseline_dir is not None:
        baseline_report = json.loads((baseline_dir / "report.json").read_text())
        if baseline_report["source_sha256"] != file_sha(Path(base.__file__)):
            raise ValueError("original statistics source differs from completed P1")
        if baseline_report["input_sha256"] != prepared.input_sha256:
            raise ValueError("original P1 statistical cohort differs")
        original_points = pd.read_csv(baseline_dir / "point-statistics.csv").set_index(["unit", "metric"])
        wanted = np.array([original_points.loc[pair, "point"] for pair in base.METRICS])
        if not np.allclose(points, wanted, atol=PARITY_ATOL, rtol=0, equal_nan=True):
            raise ValueError("real point estimates differ from P1")
        baseline_hashes = {name: file_sha(baseline_dir / name) for name in
                           ("report.json", "point-statistics.csv", "approximation-audit.csv")}
    contract = {
        "schema": "MTCS_EXACT_BOOTSTRAP_V1", "input_sha256": prepared.input_sha256,
        "source_sha256": file_sha(Path(__file__)), "original_source_sha256": file_sha(Path(base.__file__)),
        "external_pins": external_pins or {}, "baseline_hashes": baseline_hashes,
        "bootstrap_reps": bootstrap_reps, "seed": seed, "batch_reps": batch_reps,
        "checkpoint_reps": checkpoint_reps, "blocks": list(base.BLOCK_LENGTHS),
        "metric_family_size": 46, "single_tail_probability": base.TAIL_PROBABILITY,
        "interval_method": "FULL_RATIO_CIRCULAR_BLOCK_BASIC_BONFERRONI_ENVELOPE",
        "random_stream": "PCG64(SeedSequence([seed, block_days]))",
        "reference_replicates": REFERENCE_REPS, "reference_absolute_tolerance": PARITY_ATOL,
        "days": len(prepared.dates), "assets": len(prepared.assets), "packed_fields": packed.shape[1],
        "numpy_version": np.__version__, "pandas_version": pd.__version__,
    }
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()) and not (output_dir / "run-contract.json").exists():
        raise FileExistsError("nonempty output has no matching resumable contract")
    output_dir.mkdir(parents=True, exist_ok=True)
    with _lock(output_dir):
        contract_path = output_dir / "run-contract.json"
        if contract_path.exists() and json.loads(contract_path.read_text()) != base._clean(contract):
            raise ValueError("resume input/source/config contract differs")
        _json(contract_path, contract)
        if (output_dir / "report.json").exists():
            finished = json.loads((output_dir / "report.json").read_text())
            for name, digest in finished["artifact_sha256"].items():
                if file_sha(output_dir / name) != digest:
                    raise ValueError(f"completed artifact changed: {name}")
            return finished

        def emit(event):
            event = {**event, "elapsed_seconds": time.perf_counter() - started}
            with (output_dir / "progress.jsonl").open("a") as stream:
                stream.write(json.dumps(base._clean(event), ensure_ascii=False) + "\n")
                stream.flush()
            if progress_callback is not None:
                progress_callback(event)
            else:
                print(json.dumps(base._clean(event), ensure_ascii=False), flush=True)

        started = time.perf_counter()
        references = {}
        for block in base.BLOCK_LENGTHS:
            ref_path = output_dir / "reference" / f"b{block}-values.npy"
            count_path = output_dir / "reference" / f"b{block}-counts.npy"
            meta_path = output_dir / "reference" / f"b{block}-manifest.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                if file_sha(ref_path) != meta["values_sha256"] or file_sha(count_path) != meta["counts_sha256"]:
                    raise ValueError("reference array changed")
                values = np.load(ref_path, allow_pickle=False)
                counts = np.load(count_path, allow_pickle=False)
            else:
                emit({"stage": "REFERENCE_START", "block_days": block, "replicates": REFERENCE_REPS})
                values, counts = reference_values(prepared, block, seed)
                meta = {"block_days": block, "values_sha256": _array(ref_path, values),
                        "counts_sha256": _array(count_path, counts), "replicates": REFERENCE_REPS}
                if baseline_dir is not None:
                    prior = pd.read_csv(baseline_dir / "approximation-audit.csv").set_index(["block_days", "unit", "metric"])
                    checks = []
                    for mi, (unit, metric) in enumerate(base.METRICS):
                        actual_sd = float(np.std(values[np.isfinite(values[:, mi]), mi], ddof=1))
                        old_sd = float(prior.loc[(block, unit, metric), "exact_bootstrap_sd"])
                        if not np.isclose(actual_sd, old_sd, atol=PARITY_ATOL, rtol=0, equal_nan=True):
                            raise ValueError("recreated reference differs from original 2048 full audit")
                        checks.append(abs(actual_sd - old_sd))
                    meta["maximum_original_audit_sd_error"] = float(np.nanmax(checks))
                _json(meta_path, meta)
            references[block] = values
            emit({"stage": "REFERENCE_READY", "block_days": block, "replicates": REFERENCE_REPS})
        dates, assets, coverage = prepared.dates, prepared.assets, prepared.coverage
        point_rows = []
        for mi, (unit, metric) in enumerate(base.METRICS):
            ui = base.UNITS.index(unit)
            asset_n = prepared.sufficient[:, :, ui + 1, 0].sum(axis=0)
            point_rows.append({"unit": unit, "metric": metric, "point": points[mi],
                               "events": int(event_counts[ui]), "assets": int((asset_n > 0).sum())})
        _csv(output_dir / "point-statistics.csv", pd.DataFrame(point_rows))
        del prepared  # 此后只保留较小的精确压缩统计，不再持有完整日×币×11×3数组。
        interval_rows, mc_rows, parity_rows, block_reports = [], [], [], []
        reasons = {u: [] for u in base.UNITS}
        bounds = []
        for ui, unit in enumerate(base.UNITS):
            if event_counts[ui] == 0:
                reasons[unit].append("NO_OBSERVED_EVENTS")
            if bootstrap_reps * base.TAIL_PROBABILITY < base.MIN_EXPECTED_TAIL_COUNT:
                reasons[unit].append("MC_TAIL_PRECISION_INSUFFICIENT")
        for block in base.BLOCK_LENGTHS:
            days = len(dates)
            checkpoint_path = output_dir / f"checkpoint-b{block}.json"
            rng = np.random.default_rng(np.random.SeedSequence([seed, block]))
            if checkpoint_path.exists():
                cp = json.loads(checkpoint_path.read_text())
                _validate_shards(output_dir, cp)
                rng.bit_generator.state = cp["rng_state"]
            else:
                cp = {"block_days": block, "processed": 0, "shards": [], "rng_state": rng.bit_generator.state,
                      "zero_selected_replicates": [0] * 10, "reference_maximum_absolute_error": [0.0] * 46}
            complete, remainder = divmod(days, block)
            full = base.circular_block_sums(packed, block) if complete else None
            tail = base.circular_block_sums(packed, remainder) if remainder else None
            while cp["processed"] < bootstrap_reps:
                begin = cp["processed"]
                end = min(begin + checkpoint_reps, bootstrap_reps)
                errors = np.empty((end - begin, 46), dtype=np.float64)
                zero = np.array(cp["zero_selected_replicates"], dtype=np.int64)
                maximum = np.array(cp["reference_maximum_absolute_error"], dtype=float)
                for batch_begin in range(begin, end, batch_reps):
                    batch_end = min(batch_begin + batch_reps, end)
                    starts = rng.integers(0, days, size=(batch_end - batch_begin, (days + block - 1) // block), dtype=np.int64)
                    totals = exact_batch(starts, full, tail, days, block)
                    values, counts = estimate_packed(totals, len(assets))
                    e = values - points
                    errors[batch_begin - begin:batch_end - begin] = e
                    zero += (counts <= 0).sum(axis=0)
                    maximum = _reference_parity(points, e, references[block], batch_begin, maximum)
                    emit({"stage": "BATCH", "block_days": block, "processed": batch_end,
                          "total": bootstrap_reps, "committed": begin})
                relative = f"shards/b{block}/{begin:09d}-{end:09d}.npy"
                digest = _array(output_dir / relative, errors)
                cp["shards"].append({"begin": begin, "end": end, "path": relative, "sha256": digest})
                cp.update(processed=end, rng_state=rng.bit_generator.state,
                          zero_selected_replicates=zero.tolist(), reference_maximum_absolute_error=maximum.tolist())
                _json(checkpoint_path, cp, immutable=False)
                emit({"stage": "CHECKPOINT", "block_days": block, "processed": end, "total": bootstrap_reps})
            del full, tail
            # 合并文件是显式可重建的临时工作区，原始复制分块始终保留。
            with tempfile.TemporaryDirectory(dir=output_dir, prefix=".quantile-work-") as temporary:
                mapped = np.lib.format.open_memmap(Path(temporary) / "errors.npy", mode="w+", dtype=np.float64,
                                                   shape=(bootstrap_reps, 46))
                for shard in cp["shards"]:
                    mapped[shard["begin"]:shard["end"]] = np.load(output_dir / shard["path"], allow_pickle=False)
                mapped.flush()
                lower, upper = base.basic_intervals(points, mapped)
                half = bootstrap_reps // 2
                low1, high1 = base.basic_intervals(points, mapped[:half])
                low2, high2 = base.basic_intervals(points, mapped[half:])
                sd = np.std(mapped, axis=0, ddof=1)
                for mi, (unit, metric) in enumerate(base.METRICS):
                    mc_rows.append({"block_days": block, "unit": unit, "metric": metric,
                                    "bootstrap_sd": sd[mi], "lower_half1": low1[mi], "lower_half2": low2[mi],
                                    "upper_half1": high1[mi], "upper_half2": high2[mi],
                                    "lower_half_absolute_difference": abs(low1[mi] - low2[mi]),
                                    "upper_half_absolute_difference": abs(high1[mi] - high2[mi]),
                                    "expected_single_tail_count_full": bootstrap_reps * base.TAIL_PROBABILITY,
                                    "expected_single_tail_count_half": half * base.TAIL_PROBABILITY})
                sample_hash = sha256(memoryview(mapped)).hexdigest()
                del mapped
            if days <= block:
                for unit in base.UNITS:
                    reasons[unit].append(f"B{block}:INSUFFICIENT_CALENDAR_SPAN")
            if bootstrap_reps < REFERENCE_REPS:
                for unit in base.UNITS:
                    reasons[unit].append("INCOMPLETE_2048_REFERENCE_PARITY")
            for ui, unit in enumerate(base.UNITS):
                if cp["zero_selected_replicates"][ui]:
                    reasons[unit].append(f"B{block}:ZERO_SELECTED_DENOMINATOR_REPLICATE")
            for mi, (unit, metric) in enumerate(base.METRICS):
                parity_rows.append({"block_days": block, "unit": unit, "metric": metric,
                                    "checked_replicates": min(bootstrap_reps, REFERENCE_REPS),
                                    "maximum_absolute_error": cp["reference_maximum_absolute_error"][mi],
                                    "absolute_tolerance": PARITY_ATOL,
                                    "passed": bootstrap_reps >= REFERENCE_REPS and cp["reference_maximum_absolute_error"][mi] <= PARITY_ATOL})
            bounds.append((lower, upper))
            block_reports.append({"block_days": block, "processed": cp["processed"],
                                  "zero_selected_replicates": dict(zip(base.UNITS, cp["zero_selected_replicates"])),
                                  "error_samples_sha256": sample_hash,
                                  "reference_maximum_absolute_error": max(cp["reference_maximum_absolute_error"]),
                                  "calendar_length_over_block": days / block,
                                  "checkpoint_path": checkpoint_path.name})
            for mi, (unit, metric) in enumerate(base.METRICS):
                interval_rows.append({"block_days": str(block), "unit": unit, "metric": metric,
                                      "point": points[mi], "lower": lower[mi], "upper": upper[mi],
                                      "threshold": 0.0 if metric in ("L20", "DeltaLate") else 0.25})
            emit({"stage": "BLOCK_COMPLETE", "block_days": block, "processed": bootstrap_reps})
        env_lower = np.minimum(bounds[0][0], bounds[1][0])
        env_upper = np.maximum(bounds[0][1], bounds[1][1])
        for mi, (unit, metric) in enumerate(base.METRICS):
            if not np.isfinite([points[mi], env_lower[mi], env_upper[mi]]).all():
                reasons[unit].append(f"{metric}:NONFINITE_ESTIMATE_OR_INTERVAL")
            interval_rows.append({"block_days": "envelope", "unit": unit, "metric": metric,
                                  "point": points[mi], "lower": env_lower[mi], "upper": env_upper[mi],
                                  "threshold": 0.0 if metric in ("L20", "DeltaLate") else 0.25})
        intervals = pd.DataFrame(interval_rows)
        intervals["unit_reliable"] = intervals.unit.map(lambda u: not [x for x in reasons[u] if "DeltaFilter:" not in x])
        intervals["all_unit_metrics_reliable"] = intervals.unit.map(lambda u: not reasons[u])
        decisions = base._unit_decisions(intervals, reasons)
        _csv(output_dir / "intervals.csv", intervals)
        _csv(output_dir / "reference-parity.csv", pd.DataFrame(parity_rows))
        _csv(output_dir / "monte-carlo-half-audit.csv", pd.DataFrame(mc_rows))
        _csv(output_dir / "unit-decisions.csv", pd.DataFrame([
            {**r, **{key: ";".join(r[key]) for key in ("reasons", "all_metric_reasons", "filter_reasons")}}
            for r in decisions]))
        candidates = [r for r in decisions if r["status"] == "HISTORICAL_CANDIDATE"]
        candidates.sort(key=lambda r: (-r["delta20_lower"], {"U": 0, "M": 1, "S": 2}[r["unit"][0]], base.UNITS.index(r["unit"])))
        emit({"stage": "COMPLETED", "replicates_per_block": bootstrap_reps})
        artifact_paths = [p for p in output_dir.rglob("*") if p.is_file() and p.name != "run.lock" and not p.name.startswith(".pending-")]
        report = {
            "status": "COMPLETED", "inference_status": "FULL_NONLINEAR_COMPUTED",
            "all_reliable": all(r["all_metrics_reliable"] for r in decisions),
            "all_primary_reliable": all(r["primary_reliable"] for r in decisions),
            "history_status": "ITERATIVE_REUSED_DIAGNOSTIC", "input_sha256": contract["input_sha256"],
            "source_sha256": contract["source_sha256"], "original_source_sha256": contract["original_source_sha256"],
            "seed": seed, "bootstrap_reps": bootstrap_reps, "metric_family_size": 46,
            "single_tail_probability": base.TAIL_PROBABILITY,
            "interval_method": contract["interval_method"], "blocks": block_reports,
            "approximation_gate": "NOT_APPLICABLE_FULL_NONLINEAR_RECOMPUTATION",
            "original_if_failure_preserved": True, "coverage": coverage,
            "units": decisions, "selected_historical_candidate": candidates[0]["unit"] if candidates else None,
            "limitations": ["精确指原估计量的逐复制计算，不是bootstrap有限样本覆盖率保证。",
                            "本结果只对应完整观测标签队列；删失、观测库存/PIT、非平稳和有限独立行情仍限制外推。",
                            "原IF精度失败保留；没有新时间确认或全成本交易认证。"],
            "artifact_sha256": {str(p.relative_to(output_dir)): file_sha(p) for p in sorted(artifact_paths)},
        }
        _json(output_dir / "report.json", report)
        return base._clean(report)
