"""BIN-1D-MTCS 固定46指标的相关时间块推断；只消费调用方的panel。

不读取数据湖，不计算/拼接OHLCV，不改变信号。区间只描述完整观测标签队列，
删失、PIT与经济可用性的外部验收不能由本模块替代。
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


UNITS = (
    "U_LONG", "U_SHORT", "M_LONG", "M_SHORT", "S1_LONG", "S1_SHORT",
    "S2_LONG", "S2_SHORT", "S3_LONG", "S3_SHORT",
)
BASE_METRICS = ("Q20", "Delta20", "L20", "DeltaLate")
METRICS = tuple((u, m) for u in UNITS for m in BASE_METRICS) + tuple(
    (u, "DeltaFilter") for u in UNITS if u.startswith("S")
)
METRIC_IDS = tuple(f"{u}:{m}" for u, m in METRICS)
METRIC_INDEX = {pair: i for i, pair in enumerate(METRICS)}
ALPHA = 0.05
TAIL_PROBABILITY = ALPHA / (2 * len(METRICS))
AUDIT_REPLICATES = 2048
RMSE_SD_LIMIT = 0.10
BIAS_SD_LIMIT = 0.05
MIN_EXPECTED_TAIL_COUNT = 100
BLOCK_LENGTHS = (60, 120)


@dataclass
class Prepared:
    # 日×币×(全日,10单元)×(计数,未乘方向Q和,未乘方向L和)
    sufficient: np.ndarray
    dates: pd.DatetimeIndex
    assets: tuple[str, ...]
    input_sha256: str
    coverage: dict[str, Any]


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return _clean(value.tolist())
    if isinstance(value, (np.integer, np.bool_)):
        return value.item()
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(_clean(value), ensure_ascii=False, indent=2) + "\n")


def prepare(panel: pd.DataFrame) -> Prepared:
    """校验调用方输入；只使用feature_valid & valid20的价格标签。"""
    required = ["symbol", "signal_time", "feature_valid", "valid20", "q20", "l20", *UNITS]
    missing = sorted(set(required) - set(panel.columns))
    if missing:
        raise ValueError(f"Missing panel columns: {missing}")
    frame = panel.loc[:, required].copy()
    if frame["symbol"].isna().any() or not frame["symbol"].map(
        lambda x: isinstance(x, str) and bool(x.strip())
    ).all():
        raise ValueError("symbol must be a nonempty string")
    raw_times = pd.to_datetime(frame["signal_time"], errors="raise")
    if not isinstance(raw_times.dtype, pd.DatetimeTZDtype):
        raise ValueError("signal_time must be timezone-aware UTC")
    times = raw_times.dt.tz_convert("UTC")
    if times.isna().any() or not times.eq(times.dt.floor("D")).all():
        raise ValueError("signal_time must be complete UTC daily-close timestamps")
    frame["signal_time"] = times
    if frame.duplicated(["symbol", "signal_time"]).any():
        raise ValueError("duplicate symbol/signal_time")
    for col in ("feature_valid", "valid20", *UNITS):
        if not pd.api.types.is_bool_dtype(frame[col].dtype) or frame[col].isna().any():
            raise ValueError(f"{col} must be a non-null boolean")
        frame[col] = frame[col].astype(bool)
    if frame.loc[~frame["feature_valid"], list(UNITS)].to_numpy().any():
        raise ValueError("signals outside feature_valid are forbidden")
    for prefix in ("U", "M", "S1", "S2", "S3"):
        if (frame[f"{prefix}_LONG"] & frame[f"{prefix}_SHORT"]).any():
            raise ValueError(f"overlapping directions: {prefix}")
    for side in ("LONG", "SHORT"):
        states = frame[[f"S{k}_{side}" for k in (1, 2, 3)]].sum(axis=1)
        if not states.eq(frame[f"M_{side}"].astype(int)).all():
            raise ValueError(f"S1/S2/S3 must partition M_{side}")
    observed = frame["feature_valid"] & frame["valid20"]
    for col in ("q20", "l20"):
        frame[col] = pd.to_numeric(frame[col], errors="raise").astype(float)
        if not np.isfinite(frame.loc[observed, col]).all():
            raise ValueError(f"nonfinite {col} in observed cohort")
    frame = frame.sort_values(["signal_time", "symbol"], kind="stable").reset_index(drop=True)
    observed = frame["feature_valid"] & frame["valid20"]
    input_hash = sha256(pd.util.hash_pandas_object(frame, index=False).to_numpy().tobytes()).hexdigest()
    observed_frame = frame.loc[observed]
    assets = tuple(sorted(observed_frame["symbol"].unique()))
    if observed_frame.empty:
        dates = pd.DatetimeIndex([], tz="UTC")
    else:
        dates = pd.date_range(observed_frame["signal_time"].min(), observed_frame["signal_time"].max(), freq="D")
    sufficient = np.zeros((len(dates), len(assets), len(UNITS) + 1, 3), dtype=np.float64)
    if len(dates):
        ti = dates.get_indexer(observed_frame["signal_time"])
        ai = pd.Index(assets).get_indexer(observed_frame["symbol"])
        values = np.column_stack((np.ones(len(observed_frame)), observed_frame["q20"], observed_frame["l20"]))
        sufficient[ti, ai, 0, :] = values
        for gi, unit in enumerate(UNITS, 1):
            selected = observed_frame[unit].to_numpy()
            sufficient[ti[selected], ai[selected], gi, :] = values[selected]
    coverage = {
        "rows": len(frame), "feature_valid_rows": int(frame["feature_valid"].sum()),
        "observed_rows": int(observed.sum()),
        "feature_valid_without_valid20": int((frame["feature_valid"] & ~frame["valid20"]).sum()),
        "calendar_days": len(dates), "observed_assets": len(assets),
        "calendar_start": str(dates[0]) if len(dates) else None,
        "calendar_end": str(dates[-1]) if len(dates) else None,
        "units": {u: {"signals": int(frame[u].sum()), "observed_signals": int((frame[u] & observed).sum()),
                       "unobserved_signals": int((frame[u] & ~observed).sum())} for u in UNITS},
        "claim_scope": "COMPLETE_OBSERVED_20D_LABEL_COHORT_ONLY",
        "censoring_note": "valid20缺失不能补零；本接口不把未知原因推断成行政未成熟或随机缺失。",
    }
    return Prepared(sufficient, dates, assets, input_hash, coverage)


def estimate(totals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """从币×组充分统计量精确重算；支持复制×币×组输入。"""
    one = totals.ndim == 3
    if one:
        totals = totals[None, ...]
    if totals.ndim != 4 or totals.shape[2:] != (11, 3):
        raise ValueError("totals must have (..., assets, 11, 3) shape")
    out = np.full((len(totals), len(METRICS)), np.nan)
    event_counts = np.zeros((len(totals), len(UNITS)))
    for ui, unit in enumerate(UNITS):
        side = 1.0 if unit.endswith("LONG") else -1.0
        selected = totals[:, :, ui + 1, :]
        ns = selected[:, :, 0]
        n = ns.sum(axis=1)
        event_counts[:, ui] = n
        for label, offset in ((1, 0), (2, 2)):
            sums = side * selected[:, :, label].sum(axis=1)
            mu_s = np.divide(sums, n, out=np.full_like(n, np.nan), where=n > 0)
            control = totals[:, :, 0, :]
            nc = control[:, :, 0]
            if ((ns > 0) & (nc <= 0)).any():
                raise ValueError("positive selected weight with zero all-day control")
            mu_i = np.divide(side * control[:, :, label], nc, out=np.zeros_like(nc), where=nc > 0)
            mu_c = np.divide((ns * mu_i).sum(axis=1), n, out=np.full_like(n, np.nan), where=n > 0)
            out[:, 4 * ui + offset] = mu_s
            out[:, 4 * ui + offset + 1] = mu_s - mu_c
        if unit.startswith("S"):
            ci = UNITS.index("M_" + unit.split("_")[1]) + 1
            control = totals[:, :, ci, :]
            nc = control[:, :, 0]
            if ((ns > 0) & (nc <= 0)).any():
                raise ValueError("positive selected weight with zero MA7 control")
            mu_i = np.divide(side * control[:, :, 1], nc, out=np.zeros_like(nc), where=nc > 0)
            mu_c = np.divide((ns * mu_i).sum(axis=1), n, out=np.full_like(n, np.nan), where=n > 0)
            out[:, METRIC_INDEX[(unit, "DeltaFilter")]] = out[:, 4 * ui] - mu_c
    return (out[0], event_counts[0]) if one else (out, event_counts)


def influence(prepared: Prepared) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """精确估计器对日期权重的一阶导数；每列之和为0。"""
    daily = prepared.sufficient
    totals = daily.sum(axis=0)
    points, counts = estimate(totals)
    psi = np.zeros((len(daily), len(METRICS)), dtype=np.float64)
    for ui, unit in enumerate(UNITS):
        n = counts[ui]
        if n == 0:
            continue
        gi = ui + 1
        side = 1.0 if unit.endswith("LONG") else -1.0
        ns = totals[:, gi, 0]
        ns_t = daily[:, :, gi, 0]

        def mean_influence(label: int, mu: float) -> np.ndarray:
            return (side * daily[:, :, gi, label] - mu * ns_t).sum(axis=1) / n

        def control_influence(ci: int, label: int) -> np.ndarray:
            nc = totals[:, ci, 0]
            mu_i = np.divide(side * totals[:, ci, label], nc, out=np.zeros_like(nc), where=nc > 0)
            mu_c = float((ns * mu_i).sum() / n)
            weight = np.divide(ns, nc, out=np.zeros_like(nc), where=nc > 0)
            changing_mix = (ns_t * (mu_i - mu_c)).sum(axis=1)
            changing_means = (weight * (side * daily[:, :, ci, label] - mu_i * daily[:, :, ci, 0])).sum(axis=1)
            return (changing_mix + changing_means) / n

        for label, offset in ((1, 0), (2, 2)):
            ps = mean_influence(label, points[4 * ui + offset])
            psi[:, 4 * ui + offset] = ps
            psi[:, 4 * ui + offset + 1] = ps - control_influence(0, label)
        if unit.startswith("S"):
            ci = UNITS.index("M_" + unit.split("_")[1]) + 1
            psi[:, METRIC_INDEX[(unit, "DeltaFilter")]] = psi[:, 4 * ui] - control_influence(ci, 1)
    return points, psi, counts


def circular_block_sums(daily: np.ndarray, length: int) -> np.ndarray:
    """为每个真实日历起点计算循环连续块；不是重新生成价格路径。"""
    n = len(daily)
    if n == 0 or not 1 <= length <= n:
        raise ValueError("block length must be within the observed calendar")
    prefix = np.empty((n + 1,) + daily.shape[1:], dtype=np.float64)
    prefix[0] = 0.0
    np.cumsum(daily, axis=0, out=prefix[1:])
    result = np.empty_like(daily, dtype=np.float64)
    ordinary = n - length + 1
    np.subtract(prefix[length:], prefix[:ordinary], out=result[:ordinary])
    if length > 1:
        np.subtract(prefix[-1], prefix[ordinary:n], out=result[ordinary:])
        result[ordinary:] += prefix[1:length]
    return result


def draw_starts(seed: int, block: int, days: int, reps: int) -> np.ndarray:
    rng = np.random.default_rng(np.random.SeedSequence([int(seed), int(block)]))
    return rng.integers(0, days, size=(reps, (days + block - 1) // block), dtype=np.int64)


def _sum_draws(full: np.ndarray | None, tail: np.ndarray | None, starts: np.ndarray,
               days: int, block: int) -> np.ndarray:
    complete, remainder = divmod(days, block)
    shape = (len(starts),) + ((full if full is not None else tail).shape[1:])
    values = np.zeros(shape, dtype=np.float64)
    if complete:
        values += full[starts[:, :complete]].sum(axis=1)
    if remainder:
        values += tail[starts[:, complete]]
    return values


def resampled_totals(daily: np.ndarray, starts: np.ndarray, block: int) -> np.ndarray:
    """小型合成测试/对拍用精确充分统计量复制。"""
    days = len(daily)
    complete, remainder = divmod(days, block)
    full = circular_block_sums(daily, block) if complete else None
    tail = circular_block_sums(daily, remainder) if remainder else None
    return _sum_draws(full, tail, starts, days, block)


def _approximation_audit(prepared: Prepared, points: np.ndarray, psi: np.ndarray,
                         block: int, seed: int) -> tuple[list[dict], np.ndarray]:
    days = len(psi)
    starts = draw_starts(seed, block, days, AUDIT_REPLICATES)
    complete, remainder = divmod(days, block)
    full = circular_block_sums(prepared.sufficient, block) if complete else None
    tail = circular_block_sums(prepared.sufficient, remainder) if remainder else None
    pfull = circular_block_sums(psi, block) if complete else None
    ptail = circular_block_sums(psi, remainder) if remainder else None
    exact = np.full((AUDIT_REPLICATES, len(METRICS)), np.nan)
    linear = np.full_like(exact, np.nan)
    zero_reps = np.zeros(len(UNITS), dtype=int)
    # 完整统计量gather以小批次处理，避免reps×blocks×assets展开占用内存。
    width = max(1, int(np.prod(prepared.sufficient.shape[1:])))
    batch = max(1, min(16, 32_000_000 // max(1, starts.shape[1] * width * 8)))
    for begin in range(0, AUDIT_REPLICATES, batch):
        end = min(begin + batch, AUDIT_REPLICATES)
        totals = _sum_draws(full, tail, starts[begin:end], days, block)
        exact[begin:end], counts = estimate(totals)
        zero_reps += (counts <= 0).sum(axis=0)
        linear[begin:end] = points + _sum_draws(pfull, ptail, starts[begin:end], days, block) - psi.sum(axis=0)
    rows = []
    for mi, (unit, metric) in enumerate(METRICS):
        valid = np.isfinite(exact[:, mi]) & np.isfinite(linear[:, mi])
        x, y = exact[valid, mi], linear[valid, mi]
        sd = float(np.std(x, ddof=1)) if len(x) > 1 else np.nan
        error = y - x
        rmse = float(np.sqrt(np.mean(error ** 2))) if len(error) else np.nan
        bias = float(np.mean(error)) if len(error) else np.nan
        max_error = float(np.max(np.abs(error))) if len(error) else np.nan
        numerical = 128 * np.finfo(float).eps * max(1.0, float(np.max(np.abs(x))) if len(x) else 1.0)
        if np.isfinite(sd) and sd <= numerical:
            passed = bool(valid.all() and max_error <= numerical)
            rmse_ratio = 0.0 if passed else np.inf
            bias_ratio = 0.0 if passed else np.inf
        else:
            rmse_ratio = rmse / sd
            bias_ratio = abs(bias) / sd
            passed = bool(valid.all() and rmse_ratio <= RMSE_SD_LIMIT and bias_ratio <= BIAS_SD_LIMIT)
        rows.append({"block_days": block, "unit": unit, "metric": metric,
                     "audit_replicates": AUDIT_REPLICATES, "finite_replicates": int(valid.sum()),
                     "zero_selected_denominator_replicates": int(zero_reps[UNITS.index(unit)]),
                     "exact_bootstrap_sd": sd, "linear_minus_exact_rmse": rmse,
                     "linear_minus_exact_bias": bias, "maximum_absolute_error": max_error,
                     "rmse_over_sd": rmse_ratio, "absolute_bias_over_sd": bias_ratio,
                     "passed": passed})
    return rows, zero_reps


def _bootstrap_errors(psi: np.ndarray, daily_counts: np.ndarray, block: int,
                      seed: int, reps: int) -> tuple[np.ndarray, np.ndarray]:
    days = len(psi)
    # 与2048次精确对拍共享相同随机流的前2048次（若reps>=2048）。
    rng = np.random.default_rng(np.random.SeedSequence([int(seed), int(block)]))
    complete, remainder = divmod(days, block)
    combined = np.column_stack((psi, daily_counts))
    full = circular_block_sums(combined, block) if complete else None
    tail = circular_block_sums(combined, remainder) if remainder else None
    errors = np.empty((reps, len(METRICS)), dtype=np.float64)
    zero_reps = np.zeros(len(UNITS), dtype=np.int64)
    center = psi.sum(axis=0)
    blocks_per_rep = (days + block - 1) // block
    batch = max(1, min(4096, 64_000_000 // max(1, blocks_per_rep * combined.shape[1] * 8)))
    for begin in range(0, reps, batch):
        end = min(reps, begin + batch)
        starts = rng.integers(0, days, size=(end - begin, blocks_per_rep), dtype=np.int64)
        sums = _sum_draws(full, tail, starts, days, block)
        errors[begin:end] = sums[:, :len(METRICS)] - center
        zero_reps += (sums[:, len(METRICS):] <= 0).sum(axis=0)
    return errors, zero_reps


def basic_intervals(points: np.ndarray, errors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    quantiles = np.quantile(errors, [TAIL_PROBABILITY, 1 - TAIL_PROBABILITY], axis=0, method="linear")
    return points - quantiles[1], points - quantiles[0]


def _unit_decisions(intervals: pd.DataFrame, reliability: dict[str, list[str]]) -> list[dict]:
    env = intervals[intervals["block_days"].eq("envelope")].set_index(["unit", "metric"])
    rows = []
    for unit in UNITS:
        all_reasons = sorted(set(reliability[unit]))
        # 可选筛选差值的近似失败，不否定S组自身四项识别指标。
        reasons = [r for r in all_reasons if "DeltaFilter:" not in r]
        filter_reasons = all_reasons if unit.startswith("S") else []
        primary = [env.loc[(unit, m)] for m in BASE_METRICS]
        reliable = not reasons
        passed = reliable and all(r["lower"] > r["threshold"] for r in primary)
        failed = reliable and any(
            r["upper"] <= 0 if r["threshold"] == 0 else r["upper"] < r["threshold"] for r in primary
        )
        status = "HISTORICAL_CANDIDATE" if passed else "RULE_NOT_SUPPORTED" if failed else "INSUFFICIENT_EVIDENCE"
        if not reliable:
            status = "INFERENCE_UNRELIABLE"
        filter_status = "NOT_APPLICABLE"
        if unit.startswith("S"):
            r = env.loc[(unit, "DeltaFilter")]
            if filter_reasons:
                filter_status = "INFERENCE_UNRELIABLE"
            elif passed and r["lower"] > 0.25:
                filter_status = "HISTORICAL_FILTER_CANDIDATE"
            elif r["upper"] < 0.25:
                filter_status = "FILTER_INCREMENT_NOT_SUPPORTED"
            else:
                filter_status = "INSUFFICIENT_EVIDENCE"
        rows.append({"unit": unit, "reliable": reliable, "primary_reliable": reliable,
                     "all_metrics_reliable": not all_reasons,
                     "filter_reliable": not filter_reasons if unit.startswith("S") else None,
                     "reasons": reasons, "all_metric_reasons": all_reasons,
                     "filter_reasons": filter_reasons, "status": status,
                     "filter_status": filter_status, "delta20_lower": env.loc[(unit, "Delta20"), "lower"]})
    return rows


def analyze(panel: pd.DataFrame, output_dir: Path, bootstrap_reps: int = 1_000_000,
            seed: int = 20260908) -> dict:
    """固定实验推断与审计输出；无数据湖/模型/价格读取副作用。"""
    if not isinstance(bootstrap_reps, int) or isinstance(bootstrap_reps, bool) or bootstrap_reps < 4:
        raise ValueError("bootstrap_reps must be an integer >=4")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    prepared = prepare(panel)  # 输出前校验；拒绝伪造/重复/不一致输入。
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("output_dir must be empty; prior inference is immutable")
    output_dir.mkdir(parents=True, exist_ok=True)
    points, psi, counts = influence(prepared)
    daily_counts = prepared.sufficient[:, :, 1:, 0].sum(axis=1)
    reliability = {u: [] for u in UNITS}
    for ui, unit in enumerate(UNITS):
        if counts[ui] == 0:
            reliability[unit].append("NO_OBSERVED_EVENTS")
        if bootstrap_reps * TAIL_PROBABILITY < MIN_EXPECTED_TAIL_COUNT:
            reliability[unit].append("MC_TAIL_PRECISION_INSUFFICIENT")
    _write_json(output_dir / "started.json", {"input_sha256": prepared.input_sha256,
                "bootstrap_reps": bootstrap_reps, "seed": seed, "coverage": prepared.coverage})
    threshold = np.array([0.25 if m in ("Q20", "Delta20", "DeltaFilter") else 0.0 for _, m in METRICS])
    point_rows = []
    for mi, (unit, metric) in enumerate(METRICS):
        ui = UNITS.index(unit)
        asset_counts = prepared.sufficient[:, :, ui + 1, 0].sum(axis=0)
        active_days = np.flatnonzero(daily_counts[:, ui] > 0)
        point_rows.append({"unit": unit, "metric": metric, "point": points[mi],
                           "threshold": threshold[mi], "events": int(counts[ui]),
                           "assets": int((asset_counts > 0).sum()),
                           "first_event_date": str(prepared.dates[active_days[0]]) if len(active_days) else None,
                           "last_event_date": str(prepared.dates[active_days[-1]]) if len(active_days) else None,
                           "event_calendar_span_days": int(active_days[-1] - active_days[0] + 1) if len(active_days) else 0,
                           "active_nonoverlapping_60d_blocks": len(np.unique(active_days // 60)),
                           "active_nonoverlapping_120d_blocks": len(np.unique(active_days // 120))})
    pd.DataFrame(point_rows).to_csv(output_dir / "point-statistics.csv", index=False)
    influence_frame = pd.DataFrame(psi, columns=METRIC_IDS)
    influence_frame.insert(0, "signal_time", prepared.dates)
    influence_frame.to_csv(output_dir / "daily-influence.csv.gz", index=False,
                           compression={"method": "gzip", "mtime": 0})
    count_frame = pd.DataFrame(daily_counts, columns=UNITS)
    count_frame.insert(0, "signal_time", prepared.dates)
    count_frame.to_csv(output_dir / "daily-selection-counts.csv.gz", index=False,
                       compression={"method": "gzip", "mtime": 0})
    interval_rows, audit_rows, mc_rows, block_details = [], [], [], []
    bounds = []
    for block in BLOCK_LENGTHS:
        if len(prepared.dates) <= block:
            lower, upper = np.full(len(METRICS), np.nan), np.full(len(METRICS), np.nan)
            for unit in UNITS:
                reliability[unit].append(f"B{block}:INSUFFICIENT_CALENDAR_SPAN")
            for unit, metric in METRICS:
                audit_rows.append({"block_days": block, "unit": unit, "metric": metric,
                                   "audit_replicates": 0, "finite_replicates": 0,
                                   "zero_selected_denominator_replicates": 0,
                                   "exact_bootstrap_sd": np.nan, "linear_minus_exact_rmse": np.nan,
                                   "linear_minus_exact_bias": np.nan, "maximum_absolute_error": np.nan,
                                   "rmse_over_sd": np.nan, "absolute_bias_over_sd": np.nan,
                                   "passed": False, "reason": "INSUFFICIENT_CALENDAR_SPAN"})
                mc_rows.append({"block_days": block, "unit": unit, "metric": metric,
                                "status": "INSUFFICIENT_CALENDAR_SPAN", "bootstrap_sd": np.nan,
                                "lower_half1": np.nan, "lower_half2": np.nan,
                                "upper_half1": np.nan, "upper_half2": np.nan,
                                "lower_half_absolute_difference": np.nan,
                                "upper_half_absolute_difference": np.nan,
                                "expected_tail_count_full": bootstrap_reps * TAIL_PROBABILITY,
                                "expected_tail_count_half_min": (bootstrap_reps // 2) * TAIL_PROBABILITY})
            block_details.append({"block_days": block, "status": "INSUFFICIENT_CALENDAR_SPAN"})
        else:
            audit, audit_zeros = _approximation_audit(prepared, points, psi, block, seed)
            audit_rows.extend(audit)
            for row in audit:
                if not row["passed"]:
                    reliability[row["unit"]].append(f"B{block}:{row['metric']}:LINEARIZATION_AUDIT_FAILED")
            errors, main_zeros = _bootstrap_errors(psi, daily_counts, block, seed, bootstrap_reps)
            lower, upper = basic_intervals(points, errors)
            half = len(errors) // 2
            low1, high1 = basic_intervals(points, errors[:half])
            low2, high2 = basic_intervals(points, errors[half:])
            sd = np.std(errors, axis=0, ddof=1)
            for mi, (unit, metric) in enumerate(METRICS):
                mc_rows.append({"block_days": block, "unit": unit, "metric": metric,
                                "status": "COMPUTED", "bootstrap_sd": sd[mi], "lower_half1": low1[mi], "lower_half2": low2[mi],
                                "upper_half1": high1[mi], "upper_half2": high2[mi],
                                "lower_half_absolute_difference": abs(low1[mi] - low2[mi]),
                                "upper_half_absolute_difference": abs(high1[mi] - high2[mi]),
                                "expected_tail_count_full": bootstrap_reps * TAIL_PROBABILITY,
                                "expected_tail_count_half_min": half * TAIL_PROBABILITY})
            for ui, unit in enumerate(UNITS):
                if audit_zeros[ui] or main_zeros[ui]:
                    reliability[unit].append(f"B{block}:ZERO_SELECTED_DENOMINATOR_REPLICATE")
            block_details.append({"block_days": block, "status": "COMPUTED",
                                  "zero_replicates_full_audit": dict(zip(UNITS, audit_zeros.tolist())),
                                  "zero_replicates_main": dict(zip(UNITS, main_zeros.tolist())),
                                  "calendar_length_over_block": len(psi) / block,
                                  "error_samples_sha256": sha256(memoryview(errors)).hexdigest(),
                                  "first_2048_error_samples_sha256": sha256(memoryview(errors[:2048])).hexdigest()})
            del errors
        bounds.append((lower, upper))
        for mi, (unit, metric) in enumerate(METRICS):
            interval_rows.append({"block_days": str(block), "unit": unit, "metric": metric,
                                  "point": points[mi], "lower": lower[mi], "upper": upper[mi],
                                  "threshold": threshold[mi]})
    # 普通min/max保留NaN，不能用nanmin忽略失败设定后择取较窄区间。
    env_lower = np.minimum(bounds[0][0], bounds[1][0])
    env_upper = np.maximum(bounds[0][1], bounds[1][1])
    for mi, (unit, metric) in enumerate(METRICS):
        if not np.isfinite([points[mi], env_lower[mi], env_upper[mi]]).all():
            reliability[unit].append(f"{metric}:NONFINITE_ESTIMATE_OR_INTERVAL")
        interval_rows.append({"block_days": "envelope", "unit": unit, "metric": metric,
                              "point": points[mi], "lower": env_lower[mi], "upper": env_upper[mi],
                              "threshold": threshold[mi]})
    intervals = pd.DataFrame(interval_rows)
    intervals["unit_reliable"] = intervals["unit"].map(
        lambda u: not [r for r in reliability[u] if "DeltaFilter:" not in r])
    intervals["all_unit_metrics_reliable"] = intervals["unit"].map(lambda u: not reliability[u])
    intervals.to_csv(output_dir / "intervals.csv", index=False)
    pd.DataFrame(audit_rows).to_csv(output_dir / "approximation-audit.csv", index=False)
    pd.DataFrame(mc_rows).to_csv(output_dir / "monte-carlo-half-audit.csv", index=False)
    decisions = _unit_decisions(intervals, reliability)
    pd.DataFrame([{**row, **{k: ";".join(row[k]) for k in ("reasons", "all_metric_reasons", "filter_reasons")}}
                  for row in decisions]).to_csv(
        output_dir / "unit-decisions.csv", index=False)
    candidates = [r for r in decisions if r["status"] == "HISTORICAL_CANDIDATE"]
    candidates.sort(key=lambda r: (-r["delta20_lower"], {"U": 0, "M": 1, "S": 2}[r["unit"][0]], UNITS.index(r["unit"])))
    report = {
        "status": "COMPLETED", "all_reliable": all(row["all_metrics_reliable"] for row in decisions),
        "all_primary_reliable": all(row["primary_reliable"] for row in decisions),
        "inference_status": "RELIABLE_APPROXIMATION" if all(row["all_metrics_reliable"] for row in decisions) else "SOME_UNITS_INFERENCE_UNRELIABLE",
        "history_status": "ITERATIVE_REUSED_DIAGNOSTIC", "input_sha256": prepared.input_sha256,
        "source_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "seed": seed, "bootstrap_reps": bootstrap_reps, "metric_family_size": len(METRICS),
        "numpy_version": np.__version__, "pandas_version": pd.__version__,
        "family_alpha": ALPHA, "single_tail_probability": TAIL_PROBABILITY,
        "interval_method": "LINEARIZED_CIRCULAR_MOVING_BLOCK_BASIC_BONFERRONI_ENVELOPE",
        "quantile_method": "numpy.linear", "blocks": block_details,
        "resampling_rng": "numpy.PCG64(SeedSequence([seed, block_days]))",
        "audit_replicates": AUDIT_REPLICATES, "rmse_sd_limit": RMSE_SD_LIMIT,
        "absolute_bias_sd_limit": BIAS_SD_LIMIT, "minimum_expected_single_tail_count": MIN_EXPECTED_TAIL_COUNT,
        "daily_influence_zero_sum_max_abs": float(np.max(np.abs(psi.sum(axis=0)))) if len(psi) else 0.0,
        "coverage": prepared.coverage, "units": decisions,
        "selected_historical_candidate": candidates[0]["unit"] if candidates else None,
        "limitations": ["一阶近似核对不证明有限样本覆盖率；相关时间信息不足不能由更多复制或更多币弥补。",
                        "区间针对完整观测标签队列；删失、历史PIT、单币外推与完整交易成本仍需调用方独立验收。",
                        "只选择历史候选；本模块不宣布新增时间确认、全成本可用或晋升。"],
        "artifact_sha256": {p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(output_dir.iterdir()) if p.is_file()},
    }
    _write_json(output_dir / "report.json", report)
    return _clean(report)
