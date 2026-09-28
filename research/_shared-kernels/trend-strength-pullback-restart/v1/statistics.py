"""TSPR v1 完整比率统计；只消费调用方标签，不读取行情或重建价格路径。

输入为 wide symbol × ts 面板，q20/l20 未乘方向。prepare 返回 Prepared，
totals 形状为 (asset, direction, cell, [n,sumQ,sumLate])；estimate 同时接受
带任意批次前缀的 totals。run 默认执行冻结的 24 维联合推断。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import fcntl
import hashlib
import json
import math
import os
import time

import numpy as np
import pandas as pd


DIRECTIONS = ("LONG", "SHORT")
CONTRASTS = ("STRENGTH", "RESTART", "PATH", "SYNERGY", "STRENGTH_MODERATION", "HIGH_PM")
LABELS = ("Q20", "Late")
METRICS = tuple(f"{d}.{c}.{y}" for d in DIRECTIONS for c in CONTRASTS for y in LABELS)
SEED = 20260909
BLOCKS = (60, 120)
STAGES = (50000, 100000, 200000)
# 每方向仅七格：HIGH 的四格、LOW 全日、LOW10、LOW11。
CELL_NAMES = ("HIGH00", "HIGH01", "HIGH10", "HIGH11", "LOW_ALL", "LOW10", "LOW11")


@dataclass
class Prepared:
    daily: np.ndarray  # date × (仅有观察的 asset/direction/cell × 3)
    active_cells: np.ndarray
    totals: np.ndarray
    dates: pd.DatetimeIndex
    symbols: tuple[str, ...]
    events: pd.DataFrame  # 全部事前 x>0 机会，保留未完整标签
    fingerprint: str
    input_rows: int
    reference_data: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None

    def expand(self, packed: np.ndarray) -> np.ndarray:
        values = np.asarray(packed, dtype=np.float64)
        if values.shape[-1] != len(self.active_cells) * 3:
            raise ValueError("packed column count does not match preparation")
        result = np.zeros(values.shape[:-1] + (len(self.symbols) * 14, 3), dtype=np.float64)
        result[..., self.active_cells, :] = values.reshape(values.shape[:-1] + (-1, 3))
        return result.reshape(values.shape[:-1] + (len(self.symbols), 2, 7, 3))


def _boolean(frame: pd.DataFrame, name: str) -> np.ndarray:
    if not pd.api.types.is_bool_dtype(frame[name].dtype) or frame[name].isna().any():
        raise ValueError(f"{name} must be nonmissing boolean")
    return frame[name].to_numpy(dtype=bool)


def prepare(panel: pd.DataFrame) -> Prepared:
    """验证已生成标签并压缩；不使用未来完整性改变事前机会全集。"""
    if not isinstance(panel, pd.DataFrame) or panel.empty:
        raise ValueError("panel must be a nonempty DataFrame")
    required = {"symbol", "ts", "feature_valid", "valid20", "q20", "l20"}
    required |= {f"{v}_{d}" for d in DIRECTIONS for v in ("strength", "strength_bin", "P", "M")}
    missing = required - set(panel)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    frame = panel[list(sorted(required))].copy()
    if frame.symbol.isna().any() or not frame.symbol.map(lambda x: isinstance(x, str) and bool(x)).all():
        raise ValueError("symbol must contain nonempty strings")
    if pd.api.types.is_numeric_dtype(frame.ts.dtype):
        raise ValueError("numeric ts must be resolved upstream")
    frame["ts"] = pd.to_datetime(frame.ts, utc=True, errors="raise")
    if frame.ts.isna().any() or not frame.ts.eq(frame.ts.dt.normalize()).all():
        raise ValueError("ts must identify UTC daily bar opens")
    if frame.duplicated(["symbol", "ts"]).any():
        raise ValueError("duplicate symbol × ts observations")
    feature = _boolean(frame, "feature_valid")
    complete = _boolean(frame, "valid20")
    for y in ("q20", "l20"):
        frame[y] = pd.to_numeric(frame[y], errors="raise").astype(float)
        if not np.isfinite(frame.loc[feature & complete, y]).all():
            raise ValueError(f"complete eligible {y} must be finite")
    if "q5" in panel:
        q5 = pd.to_numeric(panel.q5, errors="raise").to_numpy(dtype=float)
        valid = feature & complete
        if not np.isfinite(q5[valid]).all() or not np.allclose(
            frame.l20.to_numpy()[valid], frame.q20.to_numpy()[valid] - q5[valid], rtol=1e-12, atol=1e-10
        ):
            raise ValueError("l20 must equal q20 minus q5 on complete eligible rows")
    for d in DIRECTIONS:
        x = pd.to_numeric(frame[f"strength_{d}"], errors="raise").to_numpy(dtype=float)
        if not np.isfinite(x[feature]).all():
            raise ValueError(f"eligible strength_{d} must be finite")
        bins = pd.to_numeric(frame[f"strength_bin_{d}"], errors="raise").to_numpy(dtype=float)
        expected = np.where(x > 2, 3, np.where(x > 1, 2, np.where(x > 0, 1, 0)))
        if not np.isin(bins, (0, 1, 2, 3)).all() or not np.array_equal(bins[feature], expected[feature]):
            raise ValueError(f"strength_bin_{d} does not match frozen boundaries")
        frame[f"strength_{d}"] = x
        frame[f"strength_bin_{d}"] = bins.astype(np.int8)
        p, m = _boolean(frame, f"P_{d}"), _boolean(frame, f"M_{d}")
        if f"cell_{d}" in panel:
            expected_cell = np.where(feature & (x > 0), 2 * p.astype(int) + m.astype(int), -1)
            actual = pd.to_numeric(panel[f"cell_{d}"], errors="raise").to_numpy()
            if not np.array_equal(actual, expected_cell):
                raise ValueError(f"cell_{d} is inconsistent with eligibility/P/M")
    if not np.allclose(frame.loc[feature, "strength_LONG"], -frame.loc[feature, "strength_SHORT"], rtol=1e-12, atol=1e-12):
        raise ValueError("directional strengths must be opposites")
    status_column = next((c for c in ("label20_status", "label_status20", "status20", "label_status_20", "future_status20") if c in panel), None)
    frame["label_status20"] = panel[status_column].astype(str).to_numpy() if status_column else np.where(complete, "COMPLETE", "UNOBSERVED_UNCLASSIFIED")
    frame = frame.sort_values(["symbol", "ts"], kind="stable").reset_index(drop=True)
    digest = hashlib.sha256(pd.util.hash_pandas_object(frame, index=False).values.tobytes()).hexdigest()
    pieces = []
    for di, (d, sign) in enumerate(zip(DIRECTIONS, (1, -1))):
        mask = frame.feature_valid & frame[f"strength_{d}"].gt(0)
        part = frame.loc[mask, ["symbol", "ts", "valid20", "label_status20"]].copy()
        part["direction_index"] = di
        part["direction"] = d
        part["strength"] = frame.loc[mask, f"strength_{d}"].to_numpy()
        part["strength_bin"] = frame.loc[mask, f"strength_bin_{d}"].to_numpy()
        part["P"] = frame.loc[mask, f"P_{d}"].to_numpy()
        part["M"] = frame.loc[mask, f"M_{d}"].to_numpy()
        part["cell"] = 2 * part.P.astype(np.int8) + part.M.astype(np.int8)
        part["Q20"] = sign * frame.loc[mask, "q20"].to_numpy()
        part["Late"] = sign * frame.loc[mask, "l20"].to_numpy()
        pieces.append(part)
    events = pd.concat(pieces, ignore_index=True)
    eligible_frame = frame.loc[frame.feature_valid]
    if eligible_frame.empty:
        raise ValueError("no feature-valid observations")
    # 包括边缘全 x=0 日期，不能由状态覆盖率缩短共同日历。
    dates = pd.date_range(eligible_frame.ts.min(), eligible_frame.ts.max(), freq="D", tz="UTC")
    symbols = tuple(sorted(eligible_frame.symbol.unique()))
    events["asset_index"] = pd.Categorical(events.symbol, categories=symbols).codes
    events["date_index"] = ((events.ts - dates[0]) / pd.Timedelta(days=1)).astype(int)
    observed = events.loc[events.valid20]
    packed_rows: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    for bin_value, source_cells, destination in ((3, None, None), (1, None, 4), (1, 2, 5), (1, 3, 6)):
        part = observed.loc[observed.strength_bin.eq(bin_value)]
        if source_cells is not None:
            part = part.loc[part.cell.eq(source_cells)]
        slot = part.cell.to_numpy() if destination is None else np.full(len(part), destination)
        ids = (part.asset_index.to_numpy() * 2 + part.direction_index.to_numpy()) * 7 + slot
        values = np.column_stack((np.ones(len(part)), part.Q20, part.Late))
        packed_rows.append((part.date_index.to_numpy(), ids.astype(int), values))
    all_ids = np.concatenate([p[1] for p in packed_rows])
    active = np.unique(all_ids)
    # 没有任何完整样本时保留空 packed，原点将如实无支持。
    daily = np.zeros((len(dates), len(active), 3), dtype=np.float64)
    for days, ids, values in packed_rows:
        if len(ids):
            np.add.at(daily, (days, np.searchsorted(active, ids)), values)
    result = Prepared(daily.reshape(len(dates), -1), active, np.empty(0), dates, symbols, events, digest, len(frame))
    result.totals = result.expand(result.daily.sum(axis=0))
    return result


def _contrast(cells: np.ndarray, coefficients: tuple[int, ...]) -> np.ndarray:
    counts = cells[..., 0]
    valid = np.all(counts > 0, axis=-1)
    inverse = np.divide(1.0, counts, out=np.zeros_like(counts), where=counts > 0)
    weights = np.divide(1.0, inverse.sum(axis=-1), out=np.zeros_like(valid, dtype=float), where=valid)
    means = np.divide(cells[..., 1:], counts[..., None], out=np.zeros_like(cells[..., 1:]), where=counts[..., None] > 0)
    differences = np.sum(means * np.asarray(coefficients)[..., None], axis=-2)
    denominator = weights.sum(axis=-1)
    numerator = np.sum(weights[..., None] * differences, axis=-2)
    return np.divide(numerator, denominator[..., None], out=np.full_like(numerator, np.nan), where=denominator[..., None] > 0)


def estimate(totals: np.ndarray) -> np.ndarray:
    """精确重新计算格内均值、调和权重与比率；返回 (...,24)。"""
    values = np.asarray(totals, dtype=float)
    if values.ndim < 4 or values.shape[-3:] != (2, 7, 3):
        raise ValueError("totals must end in (asset,2,7,3)")
    if not np.isfinite(values).all() or (values[..., 0] < 0).any():
        raise ValueError("totals must be finite with nonnegative counts")
    outputs = []
    for di in range(2):
        v = values[..., di, :, :]
        outputs.append(_contrast(np.stack((v[..., :4, :].sum(axis=-2), v[..., 4, :]), axis=-2), (1, -1)))
        outputs.append(_contrast(v[..., [3, 2], :], (1, -1)))
        outputs.append(_contrast(v[..., [3, 1], :], (1, -1)))
        outputs.append(_contrast(v[..., [3, 2, 1, 0], :], (1, -1, -1, 1)))
        outputs.append(_contrast(v[..., [3, 2, 6, 5], :], (1, -1, -1, 1)))
        raw = v[..., 3, :].sum(axis=-2)
        outputs.append(np.divide(raw[..., 1:], raw[..., :1], out=np.full_like(raw[..., 1:], np.nan), where=raw[..., :1] > 0))
    return np.concatenate(outputs, axis=-1)


def _arm_definitions(contrast: str) -> tuple[list[tuple[int, int | None]], tuple[int, ...]]:
    definitions = {
        "STRENGTH": ([(3, None), (1, None)], (1, -1)),
        "RESTART": ([(3, 3), (3, 2)], (1, -1)),
        "PATH": ([(3, 3), (3, 1)], (1, -1)),
        "SYNERGY": ([(3, 3), (3, 2), (3, 1), (3, 0)], (1, -1, -1, 1)),
        "STRENGTH_MODERATION": ([(3, 3), (3, 2), (1, 3), (1, 2)], (1, -1, -1, 1)),
        "HIGH_PM": ([(3, 3)], (1,)),
    }
    return definitions[contrast]


def reference_estimate(prepared: Prepared, date_weights: np.ndarray | None = None, *, quarter: bool = False, fine_strength: bool = False) -> np.ndarray:
    """独立从原观察行按格累加；用于对拍与描述性匹配，不使用 packed。"""
    events = prepared.events
    if date_weights is None:
        day_w = np.ones(len(prepared.dates))
    else:
        day_w = np.asarray(date_weights, dtype=float)
        if day_w.shape != (len(prepared.dates),) or not np.isfinite(day_w).all() or (day_w < 0).any():
            raise ValueError("date_weights must be finite nonnegative calendar weights")
    if not quarter and not fine_strength:
        # 独立布局保留全部三档四格，每条原观察只出现一次；不使用七格压缩。
        if prepared.reference_data is None:
            raw = events.loc[events.valid20]
            codes = ((raw.asset_index.to_numpy() * 2 + raw.direction_index.to_numpy()) * 3 + raw.strength_bin.to_numpy() - 1) * 4 + raw.cell.to_numpy()
            prepared.reference_data = (codes.astype(np.int64), raw.date_index.to_numpy(dtype=np.int64), raw[list(LABELS)].to_numpy(dtype=float))
        codes, days, outcomes = prepared.reference_data
        weights = day_w[days]
        cell_count = len(prepared.symbols) * 24
        cube = np.column_stack((np.bincount(codes, weights=weights, minlength=cell_count), *(np.bincount(codes, weights=weights * outcomes[:, j], minlength=cell_count) for j in range(2)))).reshape(len(prepared.symbols), 2, 3, 4, 3)
        answer = []
        for di in range(2):
            for contrast in CONTRASTS:
                arms, coefficients = _arm_definitions(contrast)
                arm_values = [cube[:, di, b - 1].sum(axis=1) if c is None else cube[:, di, b - 1, c] for b, c in arms]
                if contrast == "HIGH_PM":
                    total = arm_values[0].sum(axis=0)
                    answer.extend(total[1:] / total[0] if total[0] > 0 else (np.nan, np.nan))
                    continue
                count_matrix = np.column_stack([v[:, 0] for v in arm_values])
                supported = np.min(count_matrix, axis=1) > 0
                n = count_matrix[supported]
                if not len(n):
                    answer.extend((np.nan, np.nan))
                    continue
                overlap = 1 / np.sum(1 / n, axis=1)
                difference = sum(a * v[supported, 1:] / n[:, j, None] for j, (a, v) in enumerate(zip(coefficients, arm_values)))
                answer.extend(np.sum(overlap[:, None] * difference, axis=0) / np.sum(overlap))
        return np.asarray(answer)
    complete = events.loc[events.valid20].copy()
    complete["row_weight"] = day_w[complete.date_index.to_numpy()]
    result = []
    for d in DIRECTIONS:
        part = complete.loc[complete.direction.eq(d)].copy()
        strata = part.symbol.astype(str)
        if quarter:
            strata = strata + "/" + part.ts.dt.year.astype(str) + "Q" + part.ts.dt.quarter.astype(str)
        if fine_strength:
            fine = part.strength.map(lambda x: str(math.floor(x * 4) if x <= np.finfo(float).max / 4 else int(x) * 4)).astype(str)
            strata = strata + "/F" + fine
        codes, levels = pd.factorize(strata, sort=True)
        k = len(levels)
        for contrast in CONTRASTS:
            if fine_strength and contrast not in ("RESTART", "PATH"):
                result.extend((np.nan, np.nan))
                continue
            arms, coefficients = _arm_definitions(contrast)
            counts, sums = [], []
            for strength_bin, cell in arms:
                mask = part.strength_bin.eq(strength_bin).to_numpy()
                if cell is not None:
                    mask = mask & part.cell.eq(cell).to_numpy()
                c = codes[mask]
                w = part.row_weight.to_numpy()[mask]
                counts.append(np.bincount(c, weights=w, minlength=k))
                sums.append(np.column_stack([np.bincount(c, weights=w * part[y].to_numpy()[mask], minlength=k) for y in LABELS]))
            if contrast == "HIGH_PM":
                denom = counts[0].sum()
                result.extend(sums[0].sum(axis=0) / denom if denom > 0 else (np.nan, np.nan))
                continue
            numerator = np.zeros(2)
            denominator = 0.0
            for i in range(k):
                n = [c[i] for c in counts]
                if min(n) <= 0:
                    continue
                w = 1.0 / sum(1.0 / value for value in n)
                difference = sum(a * s[i] / count for a, s, count in zip(coefficients, sums, n))
                numerator += w * difference
                denominator += w
            result.extend(numerator / denominator if denominator > 0 else (np.nan, np.nan))
    return np.asarray(result)


def circular_block_sums(daily: np.ndarray, block_length: int) -> np.ndarray:
    """每个合法起点的循环连续块充分统计，支持块长大于日历长度。"""
    values = np.asarray(daily, dtype=float)
    if values.ndim != 2 or not len(values) or block_length < 1:
        raise ValueError("nonempty daily matrix and positive block required")
    cycles, remainder = divmod(block_length, len(values))
    result = np.broadcast_to(values.sum(axis=0) * cycles, values.shape).copy()
    if remainder:
        extended = np.concatenate((values, values[:remainder]), axis=0)
        cumulative = np.concatenate((np.zeros((1, values.shape[1])), np.cumsum(extended, axis=0)), axis=0)
        result += cumulative[np.arange(len(values)) + remainder] - cumulative[np.arange(len(values))]
    return result


def draw_starts(rng: np.random.Generator, count: int, calendar_length: int, block_length: int) -> np.ndarray:
    return rng.integers(0, calendar_length, size=(count, math.ceil(calendar_length / block_length)), dtype=np.int64)


def weights_from_starts(starts: np.ndarray, calendar_length: int, block_length: int) -> np.ndarray:
    starts = np.asarray(starts, dtype=np.int64)
    expected = math.ceil(calendar_length / block_length)
    if starts.ndim != 2 or starts.shape[1] != expected or (starts < 0).any() or (starts >= calendar_length).any():
        raise ValueError("invalid circular block starts")
    offsets = np.arange(block_length)
    indexes = ((starts[..., None] + offsets) % calendar_length).reshape(len(starts), -1)[:, :calendar_length]
    weights = np.zeros((len(starts), calendar_length), dtype=np.int64)
    np.add.at(weights, (np.arange(len(starts))[:, None], indexes), 1)
    return weights


def bootstrap_estimates(prepared: Prepared, starts: np.ndarray, block_length: int, blocks: np.ndarray | None = None) -> np.ndarray:
    """完整块计数 DGEMM，最后块按实际剩余天数截断。"""
    starts = np.asarray(starts)
    t = len(prepared.dates)
    full, remainder = divmod(t, block_length)
    if starts.shape != (len(starts), full + bool(remainder)):
        raise ValueError("start matrix does not match exact calendar length")
    block_values = circular_block_sums(prepared.daily, block_length) if blocks is None else blocks
    start_counts = np.zeros((len(starts), t), dtype=float)
    if full:
        np.add.at(start_counts, (np.arange(len(starts))[:, None], starts[:, :full]), 1.0)
    packed = start_counts @ block_values
    if remainder:
        # 尾块只需本批起点对应的日行，避免再常驻一份大块矩阵。
        for offset in range(remainder):
            packed += prepared.daily[(starts[:, -1] + offset) % t]
    return estimate(prepared.expand(packed))


def audit_reference(prepared: Prepared, *, seed: int = SEED, block_lengths: tuple[int, ...] = BLOCKS, replicates: int = 256) -> dict[str, Any]:
    point, direct = estimate(prepared.totals), reference_estimate(prepared)
    finite_match = np.array_equal(np.isfinite(point), np.isfinite(direct))
    point_error = float(np.max(np.abs(point[np.isfinite(point)] - direct[np.isfinite(point)]))) if np.isfinite(point).any() and finite_match else (0.0 if finite_match else math.inf)
    details = []
    for block in block_lengths:
        rng = np.random.default_rng(np.random.SeedSequence([seed, block]))
        starts = draw_starts(rng, replicates, len(prepared.dates), block)
        computed = bootstrap_estimates(prepared, starts, block)
        weights = weights_from_starts(starts, len(prepared.dates), block)
        max_error, matches = 0.0, True
        for b, day_weights in enumerate(weights):
            reference = reference_estimate(prepared, day_weights)
            mask = np.isfinite(reference)
            matches &= np.array_equal(mask, np.isfinite(computed[b]))
            if mask.any():
                max_error = max(max_error, float(np.max(np.abs(reference[mask] - computed[b, mask]))))
        details.append({"block": block, "replicates": replicates, "finite_mask_match": bool(matches), "max_absolute_error": max_error, "passed": bool(matches and max_error <= 1e-10)})
    return {"point_max_absolute_error": point_error, "point_finite_mask_match": bool(finite_match), "blocks": details, "passed": bool(finite_match and point_error <= 1e-10 and all(r["passed"] for r in details))}


def simultaneous_intervals(point: np.ndarray, replicates: np.ndarray) -> dict[str, Any]:
    point, values = np.asarray(point, dtype=float), np.asarray(replicates, dtype=float)
    if point.shape != (24,) or values.ndim != 2 or values.shape[1] != 24 or len(values) < 2:
        raise ValueError("expected 24 estimates and at least two full replicates")
    reasons = [""] * 24
    valid = np.isfinite(point) & np.isfinite(values).all(axis=0)
    sd = np.full(24, np.nan)
    sd[valid] = np.std(values[:, valid], axis=0, ddof=1)
    for j in range(24):
        if not np.isfinite(point[j]):
            reasons[j] = "POINT_NO_SUPPORT"
        elif not np.isfinite(values[:, j]).all():
            reasons[j] = "REPLICATE_NO_SUPPORT_OR_NONFINITE"
        elif not np.isfinite(sd[j]) or sd[j] <= 0:
            reasons[j] = "ZERO_OR_NONFINITE_SD"
    valid &= np.isfinite(sd) & (sd > 0)
    lower, upper = np.full(24, -np.inf), np.full(24, np.inf)
    critical = np.nan
    if valid.any():
        max_error = np.max(np.abs(values[:, valid] - point[valid]) / sd[valid], axis=1)
        critical = float(np.quantile(max_error, 0.95, method="linear"))
        lower[valid] = point[valid] - critical * sd[valid]
        upper[valid] = point[valid] + critical * sd[valid]
    return {"lower": lower, "upper": upper, "sd": sd, "critical": critical, "reliable": valid, "reasons": reasons, "estimable_dimensions": int(valid.sum()), "registered_dimensions": 24}


def monte_carlo_check(point: np.ndarray, replicates: np.ndarray) -> tuple[dict[str, Any], pd.DataFrame]:
    if len(replicates) % 5:
        raise ValueError("replicate count must divide into five equal fixed batches")
    full = simultaneous_intervals(point, replicates)
    rows, passed = [], True
    for batch_id, subset in enumerate(np.split(replicates, 5), 1):
        part = simultaneous_intervals(point, subset)
        for j, name in enumerate(METRICS):
            applicable = bool(full["reliable"][j])
            difference = max(abs(part["lower"][j] - full["lower"][j]), abs(part["upper"][j] - full["upper"][j])) if applicable else np.nan
            ratio = difference / full["sd"][j] if applicable else np.nan
            good = bool(part["reliable"][j] and ratio <= 0.25) if applicable else True
            passed &= good
            rows.append({"batch": batch_id, "metric": name, "applicable": applicable, "batch_critical": part["critical"], "full_critical": full["critical"], "batch_sd": part["sd"][j], "full_sd": full["sd"][j], "batch_lower": part["lower"][j], "batch_upper": part["upper"][j], "full_lower": full["lower"][j], "full_upper": full["upper"][j], "max_endpoint_difference": difference, "difference_in_full_sd": ratio, "passed": good})
    return {"passed": bool(passed), "threshold_full_sd": 0.25, "batches": 5, "replicates": len(replicates)}, pd.DataFrame(rows)


def _weighted_x(values: np.ndarray, weights: np.ndarray) -> dict[str, float]:
    mask = np.isfinite(values) & (weights > 0)
    x, w = np.asarray(values)[mask], np.asarray(weights)[mask]
    if not len(x):
        return {key: np.nan for key in ("x_mean", "x_sd", "x_min", "x_p10", "x_p25", "x_p50", "x_p75", "x_p90", "x_max")}
    order = np.argsort(x, kind="stable")
    x, w = x[order], w[order]
    w = w / w.sum()
    mean = float(np.sum(x * w))
    quantiles = np.interp((0.1, 0.25, 0.5, 0.75, 0.9), np.cumsum(w), x)
    return {"x_mean": mean, "x_sd": float(np.sqrt(np.sum(w * (x - mean) ** 2))), "x_min": float(x[0]), **dict(zip(("x_p10", "x_p25", "x_p50", "x_p75", "x_p90"), map(float, quantiles))), "x_max": float(x[-1])}


def _sensitivity_support(prepared: Prepared, direction: str, contrast: str, *, quarter: bool, fine: bool) -> dict[str, Any]:
    part = prepared.events.loc[prepared.events.valid20 & prepared.events.direction.eq(direction)].copy()
    strata = part.symbol.astype(str)
    if quarter:
        strata = strata + "/" + part.ts.dt.year.astype(str) + "Q" + part.ts.dt.quarter.astype(str)
    if fine:
        strata = strata + "/F" + part.strength.map(lambda x: str(math.floor(x * 4) if x <= np.finfo(float).max / 4 else int(x) * 4)).astype(str)
    codes, levels = pd.factorize(strata, sort=True)
    arms, _ = _arm_definitions(contrast)
    counts = []
    for strength_bin, cell in arms:
        mask = part.strength_bin.eq(strength_bin)
        if cell is not None:
            mask &= part.cell.eq(cell)
        counts.append(np.bincount(codes[mask.to_numpy()], minlength=len(levels)))
    ns = np.stack(counts, axis=1)
    supported = (ns > 0).all(axis=1)
    any_arm = ns.sum(axis=1) > 0
    pm_mask = (part.strength_bin.eq(3) & part.cell.eq(3)).to_numpy()
    pm_total = int(pm_mask.sum())
    pm_kept = int(supported[codes[pm_mask]].sum())
    return {"support_strata": int(supported.sum()), "strata_with_any_arm": int(any_arm.sum()), "complete_high_pm_events": pm_total, "high_pm_events_in_support": pm_kept, "high_pm_complete_support_fraction": pm_kept / pm_total if pm_total else np.nan, "complete_events_by_arm": json.dumps(ns.sum(axis=0).tolist()), "support_events_by_arm": json.dumps(ns[supported].sum(axis=0).tolist())}


def descriptions(prepared: Prepared) -> dict[str, pd.DataFrame]:
    events = prepared.events
    matrix = []
    for d in DIRECTIONS:
        for strength_bin in (1, 2, 3):
            for cell in range(4):
                part = events.loc[events.direction.eq(d) & events.strength_bin.eq(strength_bin) & events.cell.eq(cell)]
                observed = part.loc[part.valid20]
                row = {"direction": d, "strength_bin": strength_bin, "cell": cell, "opportunities": len(part), "complete20": len(observed), "unobserved20": len(part) - len(observed), "symbols": part.symbol.nunique(), "Q20": observed.Q20.mean(), "Late": observed.Late.mean(), "x_all_mean": part.strength.mean(), "x_complete_mean": observed.strength.mean()}
                matrix.append(row)
    statuses = events.groupby(["direction", "strength_bin", "cell", "label_status20"], observed=True).size().rename("count").reset_index()
    support_rows = []
    for d in DIRECTIONS:
        part = events.loc[events.direction.eq(d)]
        for contrast in CONTRASTS:
            arms, _ = _arm_definitions(contrast)
            selected, observed, counts = [], [], []
            for strength_bin, cell in arms:
                mask = part.strength_bin.eq(strength_bin)
                if cell is not None:
                    mask &= part.cell.eq(cell)
                a = part.loc[mask]
                b = a.loc[a.valid20]
                selected.append(a)
                observed.append(b)
                counts.append(np.bincount(b.asset_index, minlength=len(prepared.symbols)).astype(float))
            ns = np.stack(counts, axis=1)
            if contrast == "HIGH_PM":
                weights = ns[:, 0]
            else:
                valid = (ns > 0).all(axis=1)
                inverses = np.divide(1.0, ns, out=np.zeros_like(ns), where=ns > 0).sum(axis=1)
                weights = np.divide(1.0, inverses, out=np.zeros_like(inverses), where=valid)
            normalized = weights / weights.sum() if weights.sum() else weights
            for arm_index, ((strength_bin, cell), a, b, n) in enumerate(zip(arms, selected, observed, counts)):
                entered = weights[b.asset_index.to_numpy()] > 0
                per_event = np.divide(weights, n, out=np.zeros_like(weights), where=n > 0)[b.asset_index.to_numpy()]
                stats = _weighted_x(b.strength.to_numpy(), per_event)
                row = {"direction": d, "contrast": contrast, "arm": arm_index, "strength_bin": strength_bin, "cell": "ALL" if cell is None else cell, "opportunities": len(a), "complete20": len(b), "unobserved20": len(a) - len(b), "support_events": int(entered.sum()), "support_fraction_complete": float(entered.mean()) if len(b) else np.nan, "support_fraction_all_opportunities": float(entered.sum() / len(a)) if len(a) else np.nan, "support_symbols": int((weights > 0).sum()), "total_harmonic_weight": float(weights.sum()), "largest_symbol_weight": float(normalized.max()) if len(normalized) else np.nan, "effective_weighted_symbols": float(1.0 / np.sum(normalized ** 2)) if weights.sum() else 0.0, "estimand": "ALL_HIGH_PM_EVENTS" if contrast == "HIGH_PM" else "HARMONIC_OVERLAP_POPULATION", **stats}
                support_rows.append(row)
    sensitivity = []
    for label, values in (("SYMBOL_QUARTER", reference_estimate(prepared, quarter=True)), ("SYMBOL_FINE_STRENGTH_0.25", reference_estimate(prepared, fine_strength=True))):
        support_cache = {}
        for j, metric in enumerate(METRICS):
            if label.endswith("0.25") and metric.split(".")[1] not in ("RESTART", "PATH"):
                continue
            d, contrast, _ = metric.split(".")
            key = (d, contrast)
            if key not in support_cache:
                support_cache[key] = _sensitivity_support(prepared, d, contrast, quarter=label == "SYMBOL_QUARTER", fine=label.endswith("0.25"))
            sensitivity.append({"sensitivity": label, "metric": metric, "estimate": values[j], "inference": "DESCRIPTIVE_ONLY", **support_cache[key]})
    total_screen = []
    for d in DIRECTIONS:
        part = events.loc[events.direction.eq(d) & events.valid20]
        for strength_bin in (1, 2, 3):
            a = part.loc[part.strength_bin.eq(strength_bin)]
            pm = a.loc[a.cell.eq(3)]
            counts = pm.groupby("symbol").size()
            for y in LABELS:
                ordinary = a.groupby("symbol")[y].mean()
                control = float((counts * ordinary.reindex(counts.index)).sum() / counts.sum()) if counts.sum() else np.nan
                total_screen.append({"direction": d, "strength_bin": strength_bin, "label": y, "PM_mean": pm[y].mean(), "same_symbol_all_day_control": control, "PM_minus_all_days": pm[y].mean() - control, "inference": "DESCRIPTIVE_ONLY"})
    return {"state_matrix": pd.DataFrame(matrix), "label_status_counts": statuses, "support_and_strength_balance": pd.DataFrame(support_rows), "descriptive_sensitivities": pd.DataFrame(sensitivity), "descriptive_total_screening": pd.DataFrame(total_screen)}


def decisions(point: np.ndarray, lower: np.ndarray, upper: np.ndarray, reliable: np.ndarray, *, precision_ok: bool) -> dict[str, Any]:
    rows, candidates = [], []
    for di, direction in enumerate(DIRECTIONS):
        statuses = {}
        for ci, contrast in enumerate(CONTRASTS):
            indexes = [di * 12 + ci * 2, di * 12 + ci * 2 + 1]
            if not precision_ok:
                status = "NUMERICAL_PRECISION_INSUFFICIENT"
            elif not np.asarray(reliable)[indexes].all():
                status = "INFERENCE_UNRELIABLE"
            elif (lower[indexes] > 0).all():
                status = "POSITIVE_ASSOCIATION"
            elif (upper[indexes] <= 0).any():
                status = "RULE_NOT_SUPPORTED"
            else:
                status = "INSUFFICIENT_EVIDENCE"
            statuses[contrast] = status
            rows.append({"direction": direction, "contrast": contrast, "status": status})
        indexes = [di * 12 + 10, di * 12 + 11]
        necessary = ("RESTART", "PATH", "HIGH_PM")
        if not precision_ok:
            candidate = "NUMERICAL_PRECISION_INSUFFICIENT"
        elif any(statuses[k] == "INFERENCE_UNRELIABLE" for k in necessary):
            candidate = "INFERENCE_UNRELIABLE"
        elif lower[indexes[0]] > 0.25 and lower[indexes[1]] > 0 and all(statuses[k] == "POSITIVE_ASSOCIATION" for k in ("RESTART", "PATH")):
            candidate = "HISTORICAL_PRICE_CANDIDATE"
        elif upper[indexes[0]] <= 0.25 or upper[indexes[1]] <= 0 or any(statuses[k] == "RULE_NOT_SUPPORTED" for k in ("RESTART", "PATH")):
            candidate = "RULE_NOT_SUPPORTED"
        else:
            candidate = "INSUFFICIENT_EVIDENCE"
        candidates.append({"direction": direction, "status": candidate, "identity": "ITERATIVE_REUSED_DIAGNOSTIC", "SYNERGY_or_STRENGTH_MODERATION_required": False})
    return {"associations": rows, "candidates": candidates}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, (np.integer, np.bool_)):
        return value.item()
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return "NaN" if np.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if isinstance(value, np.floating):
        return float(value)
    return value


def _write_json(path: Path, value: Any, *, replace: bool = False) -> None:
    if path.exists() and not replace:
        raise FileExistsError(path)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as handle:
        json.dump(_jsonable(value), handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _retain_table(path: Path, table: pd.DataFrame) -> None:
    """派生小表原子落盘；恢复时核对既有字节，拒绝不完整/不同内容。"""
    content = table.to_csv(index=False).encode("utf-8")
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"retained table differs from recomputation: {path.name}")
        return
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def run(panel: pd.DataFrame, output_dir: Path, *, bootstrap_stages: tuple[int, ...] = STAGES, seed: int = SEED, block_lengths: tuple[int, ...] = BLOCKS, batch_size: int = 256, checkpoint_every: int = 2048, reference_reps: int = 256, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """冻结默认值；非默认模拟规模用于合成测试，产物显式标为 TEST_CONFIGURATION。

    不覆盖既有结果。中断后以相同输入/源码/配置恢复；完整复制及起点分片
    一经写入即保留，checkpoint 只是可原子更新的进度索引。
    """
    out = Path(output_dir)
    stages = tuple(bootstrap_stages)
    if not stages or any(isinstance(n, bool) or not isinstance(n, int) or n < 10 or n % 5 for n in stages) or list(stages) != sorted(set(stages)):
        raise ValueError("stages must be increasing unique positive counts divisible by five")
    if not block_lengths or len(set(block_lengths)) != len(block_lengths) or any(b < 1 for b in block_lengths):
        raise ValueError("block lengths must be distinct positive integers")
    if batch_size < 1 or checkpoint_every < 1 or reference_reps < 1:
        raise ValueError("batch/checkpoint/reference sizes must be positive")
    prepared = prepare(panel)
    out.mkdir(parents=True, exist_ok=True)
    emit = progress or (lambda message: print(message, flush=True))
    lock_handle = (out / ".run.lock").open("a+")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_handle.close()
        raise RuntimeError("another statistics process owns this output directory")
    try:
        config = {"fingerprint": prepared.fingerprint, "source_sha256": _sha(Path(__file__)), "seed": seed, "blocks": list(block_lengths), "stages": list(stages), "reference_reps": reference_reps, "metrics": list(METRICS), "calendar_length": len(prepared.dates), "active_cells": prepared.active_cells.tolist(), "symbols": list(prepared.symbols), "configuration_identity": "FROZEN_CONFIGURATION" if stages == STAGES and tuple(block_lengths) == BLOCKS and seed == SEED and reference_reps == 256 else "TEST_CONFIGURATION"}
        identity_path = out / "identity.json"
        if identity_path.exists():
            if json.loads(identity_path.read_text()) != config:
                raise ValueError("input/source/configuration differs from retained run")
        else:
            unexpected = [p for p in out.iterdir() if p.name != ".run.lock"]
            if unexpected:
                raise FileExistsError("nonempty output without matching identity")
            _write_json(identity_path, config)
        if (out / "report.json").exists():
            report = json.loads((out / "report.json").read_text())
            for relative, sha in report["artifact_sha256"].items():
                if _sha(out / relative) != sha:
                    raise ValueError(f"retained artifact hash mismatch: {relative}")
            return report
        point = estimate(prepared.totals)
        audit_path = out / "direct_reference_audit.json"
        if audit_path.exists():
            audit = json.loads(audit_path.read_text())
        else:
            emit(f"独立对拍：原点及每块 {reference_reps} 组原观察日期复制")
            audit = audit_reference(prepared, seed=seed, block_lengths=tuple(block_lengths), replicates=reference_reps)
            _write_json(audit_path, audit)
        if not audit["passed"]:
            raise RuntimeError("direct reference audit failed; retained evidence, no inference")
        _retain_table(out / "point_statistics.csv", pd.DataFrame({"metric": METRICS, "estimate": point}))
        daily_path = out / "daily_sufficient_statistics.npy"
        if not daily_path.exists():
            temporary = daily_path.with_suffix(".tmp")
            with temporary.open("wb") as handle:
                np.save(handle, prepared.daily, allow_pickle=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, daily_path)
        else:
            retained = np.load(daily_path, mmap_mode="r", allow_pickle=False)
            if retained.shape != prepared.daily.shape or not np.array_equal(retained, prepared.daily):
                raise ValueError("retained daily statistics differ from preparation")
            del retained
        calendar_data = {"dates": [d.isoformat() for d in prepared.dates], "columns": CELL_NAMES, "fields": ["n", "sumQ20", "sumLate"], "active_cells": prepared.active_cells, "shape_full_totals": prepared.totals.shape}
        if not (out / "calendar.json").exists():
            _write_json(out / "calendar.json", calendar_data)
        elif json.loads((out / "calendar.json").read_text()) != _jsonable(calendar_data):
            raise ValueError("retained calendar metadata differs")
        for name, table in descriptions(prepared).items():
            _retain_table(out / f"{name}.csv", table)
        finals, interval_rows = [], []
        for block in block_lengths:
            folder = out / f"block-{block}"
            folder.mkdir(exist_ok=True)
            checkpoint_path = folder / "checkpoint.json"
            rng = np.random.default_rng(np.random.SeedSequence([seed, block]))
            replay_rng = np.random.default_rng(np.random.SeedSequence([seed, block]))
            records, completed = [], 0
            if checkpoint_path.exists():
                checkpoint = json.loads(checkpoint_path.read_text())
                records, completed = checkpoint["shards"], checkpoint["completed"]
                rng.bit_generator.state = checkpoint["rng_state"]
            all_values = np.empty((stages[-1], 24))
            verified = 0
            for record in records:
                if record["start"] != verified or _sha(folder / record["file"]) != record["sha256"]:
                    raise ValueError("checkpoint shard sequence/hash mismatch")
                with np.load(folder / record["file"], allow_pickle=False) as shard:
                    values, starts = shard["replicates"], shard["starts"]
                    if values.shape != (record["end"] - verified, 24) or starts.shape != (len(values), math.ceil(len(prepared.dates) / block)):
                        raise ValueError("checkpoint shard shape mismatch")
                    expected_starts = draw_starts(replay_rng, len(values), len(prepared.dates), block)
                    if not np.array_equal(starts, expected_starts):
                        raise ValueError("retained starts do not match frozen RNG prefix")
                    all_values[verified:record["end"]] = values
                verified = record["end"]
            if verified != completed:
                raise ValueError("checkpoint progress does not match retained shards")
            if records and replay_rng.bit_generator.state != rng.bit_generator.state:
                raise ValueError("checkpoint RNG state does not follow retained starts")
            orphaned = set(folder.glob("replicates-*.npz")) - {folder / r["file"] for r in records}
            if orphaned:
                raise RuntimeError("unindexed completed shard exists; preserve and audit before recovery")
            block_values = circular_block_sums(prepared.daily, block)
            chosen = None
            for target in stages:
                if completed > target:
                    # 已有较晚阶段表示先前阶段没有通过；保留它的原始诊断。
                    continue
                while completed < target:
                    chunk_start = completed
                    chunk_end = min(target, completed + checkpoint_every)
                    saved_starts = []
                    started_at = time.monotonic()
                    while completed < chunk_end:
                        count = min(batch_size, chunk_end - completed)
                        starts = draw_starts(rng, count, len(prepared.dates), block)
                        values = bootstrap_estimates(prepared, starts, block, block_values)
                        all_values[completed:completed + count] = values
                        saved_starts.append(starts)
                        completed += count
                        emit(f"{block} 日块：{completed:,}/{target:,} 完整复制")
                    destination = folder / f"replicates-{chunk_start:06d}-{chunk_end:06d}.npz"
                    if destination.exists():
                        raise FileExistsError(destination)
                    temporary = destination.with_suffix(".tmp")
                    with temporary.open("wb") as handle:
                        np.savez(handle, replicates=all_values[chunk_start:chunk_end], starts=np.concatenate(saved_starts))
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary, destination)
                    records.append({"file": destination.name, "start": chunk_start, "end": chunk_end, "sha256": _sha(destination), "seconds": time.monotonic() - started_at})
                    _write_json(checkpoint_path, {"completed": completed, "rng_state": rng.bit_generator.state, "shards": records}, replace=True)
                stage_values = all_values[:target]
                intervals = simultaneous_intervals(point, stage_values)
                mc, mc_rows = monte_carlo_check(point, stage_values)
                stage_path = folder / f"stage-{target:06d}.json"
                stage_data = {"block": block, "replicates": target, "intervals": intervals, "mc": mc}
                if stage_path.exists():
                    if json.loads(stage_path.read_text()) != _jsonable(stage_data):
                        raise ValueError("recomputed retained stage differs")
                else:
                    _write_json(stage_path, stage_data)
                _retain_table(folder / f"mc-{target:06d}.csv", mc_rows)
                chosen = {"block": block, "replicates": target, "intervals": intervals, "mc": mc}
                emit(f"{block} 日块：{target:,} 次精度检查 {'PASS' if mc['passed'] else '需要固定续算'}")
                if mc["passed"]:
                    break
            if chosen is None:
                raise RuntimeError("checkpoint exceeds configured stages")
            finals.append(chosen)
            del block_values, all_values
            for j, metric in enumerate(METRICS):
                interval_rows.append({"block": block, "metric": metric, "estimate": point[j], "lower": chosen["intervals"]["lower"][j], "upper": chosen["intervals"]["upper"][j], "sd": chosen["intervals"]["sd"][j], "critical": chosen["intervals"]["critical"], "reliable": chosen["intervals"]["reliable"][j], "reason": chosen["intervals"]["reasons"][j], "mc_passed": chosen["mc"]["passed"]})
        lower = np.min(np.stack([r["intervals"]["lower"] for r in finals]), axis=0)
        upper = np.max(np.stack([r["intervals"]["upper"] for r in finals]), axis=0)
        reliable = np.all(np.stack([r["intervals"]["reliable"] for r in finals]), axis=0)
        precision_ok = all(r["mc"]["passed"] for r in finals)
        for j, metric in enumerate(METRICS):
            interval_rows.append({"block": "envelope", "metric": metric, "estimate": point[j], "lower": lower[j], "upper": upper[j], "reliable": reliable[j], "mc_passed": precision_ok})
        interval_frame = pd.DataFrame(interval_rows)
        interval_path = out / "intervals.csv"
        _retain_table(interval_path, interval_frame)
        judgement = decisions(point, lower, upper, reliable, precision_ok=precision_ok)
        if not (out / "decisions.json").exists():
            _write_json(out / "decisions.json", judgement)
        elif json.loads((out / "decisions.json").read_text()) != _jsonable(judgement):
            raise ValueError("retained decisions differ from recomputation")
        artifact_hashes = {str(p.relative_to(out)): _sha(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name not in (".run.lock", "report.json") and not p.name.endswith(".tmp")}
        report = {"identity": "ITERATIVE_REUSED_DIAGNOSTIC", "configuration_identity": config["configuration_identity"], "input_rows": prepared.input_rows, "opportunities": len(prepared.events), "complete20": int(prepared.events.valid20.sum()), "symbols": len(prepared.symbols), "calendar_length": len(prepared.dates), "registered_dimensions": 24, "envelope_reliable_dimensions": int(reliable.sum()), "precision_passed": precision_ok, "blocks": [{"block": r["block"], "replicates": r["replicates"], "critical": r["intervals"]["critical"], "estimable_dimensions": r["intervals"]["estimable_dimensions"], "mc": r["mc"]} for r in finals], "decisions": judgement, "artifact_sha256": artifact_hashes}
        _write_json(out / "report.json", report)
        return _jsonable(report)
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()
