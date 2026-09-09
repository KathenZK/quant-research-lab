"""TSPR v1：锚点趋势强度、严格顺序回撤、首次重穿与完整路径标签。

只消费调用家族已留证的 P0 返回帧；不读取行情湖、不引用其他家族代码。
wide panel 的 qH/retH/l20 不带方向符号；direction_events 明确乘一次方向。
"""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_lab.data.research_inputs import complete_window_mask

DAY = pd.Timedelta(days=1)
HORIZONS = (1, 5, 10, 20, 40)
SIDES = (("LONG", 1), ("SHORT", -1))
GROUPS = tuple(f"{group}_{side}" for group in ("ALL", "HIGH", "HIGH_P", "HIGH_PM")
               for side, _ in SIDES)
P_CONDITIONS = ("p1_anchor_favorable", "p2_has_adverse", "p3_actual_pullback",
                "p4_no_favorable_after_u", "p4_prev_adverse", "p5_net_pullback")
PANEL_SCHEMA = {
    "unit": "one symbol / UTC daily bar open ts; signal_time = ts + one day",
    "feature_valid": "official past60 AND positive finite ATR14[t-1] AND sigma20[t-6] AND finite strength",
    "strength_LONG/SHORT": "d * log(C[s]/C[s-20]) / (sample_std20(log returns at s) * sqrt(20)); s=t-6",
    "strength_bin_LONG/SHORT": "int8: 0=outside positive eligible domain, 1=(0,1], 2=(1,2], 3=(2,infinity)",
    "P_LONG/SHORT,M_LONG/SHORT": "bool; past-only conditions, gated by feature_valid but not strength sign",
    "cell_LONG/SHORT": "int8: -1=outside domain, otherwise 2*P+M: 0=00, 1=01, 2=10, 3=11",
    "anchor_time,pullback_time_LONG/SHORT": "UTC bar opens; pullback is earliest strict adverse day u, even when another P condition fails",
    "anchor_index,pullback_index_LONG/SHORT": "zero-based original frame row position, -1 when unavailable",
    "atr14_lag": "Wilder ATR14[t-1], sole label scale; atr14 is today's value for audit only",
    "qH,retH,l20": "UNSIGNED BY DIRECTION: (C[t+H]-O[t+1])/A, C[t+H]/O[t+1]-1, q20-q5",
    "validH": "feature_valid AND official complete_window_mask(backward=60, forward=H)",
    "mfe20_long/short,mae20_long/short": "direction-specific favorable/adverse future price extremes in ATR units",
    "giveback20_long/short": "direction-specific MFE20 minus direction-specific Q20",
    "labelH_status": "PAST_INELIGIBLE / COMPLETE_CONTIGUOUS / ADMINISTRATIVE_UNMATURED / CENSORED_GAP_OR_IDENTITY_BOUNDARY",
    "capture_groups": list(GROUPS),
}


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _verified_path(root: Path, relative: str, digest: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or sha(path) != digest:
        raise ValueError(f"saved evidence changed or escaped its owner: {relative}")
    return path


def load_verified_frames(input_dir: Path):
    """回放调用家族自己的 P0，先验请求/回执/源码/内容哈希；不寻找替代输入。

    input_dir 必须为该消费家族 artifacts/p0-inputs。其 started.json 将本次
    audit_inputs.py、输入合同、请求和来源 pins 绑定至当前家族，禁止旧家族帧回退。
    """
    root = Path(input_dir).resolve()
    if root.name != "p0-inputs" or root.parent.name != "artifacts":
        raise ValueError("expected the consumer family's artifacts/p0-inputs")
    family = root.parent.parent
    def read(path):
        return json.loads(path.read_text(encoding="utf-8"))

    summary = read(root / "summary.json")
    if (summary.get("status") != "PRICE_INPUTS_READY_WITH_RECORDED_EXCLUSIONS"
            or not summary.get("source_pins_unchanged") or summary.get("changed_family_files")):
        raise ValueError("P0 did not complete with unchanged sources and contracts")
    for flag in ("old_family_frames_read", "data_lake_written", "signals_computed", "labels_computed"):
        if summary.get(flag) is not False:
            raise ValueError(f"P0 ownership/purpose assertion failed: {flag}")
    started = read(root / "started.json")
    required_pins = {"specs/input-request.json", "specs/source-pins.json", "specs/input-contract.md",
                     "specs/observed-universe.json", "scripts/audit_inputs.py"}
    if not required_pins.issubset(started["family_files_sha256"]):
        raise ValueError("P0 does not bind this consumer's input contract and reader")
    for relative, digest in started["family_files_sha256"].items():
        _verified_path(family, relative, digest)
    source_pins = read(family / "specs/source-pins.json")
    source_root = Path(source_pins["formal_lab"]).resolve()
    mask_source = "src/strategy_lab/data/research_inputs.py"
    if (mask_source not in source_pins["files"]
            or Path(inspect.getfile(complete_window_mask)).resolve() != source_root / mask_source):
        raise ValueError("loaded complete_window_mask is not from the explicitly pinned source root")
    for relative, digest in source_pins["files"].items():
        _verified_path(source_root, relative, digest)
    expected = read(family / "specs/input-request.json")
    if (expected.get("backward_bars") != 60 or expected.get("forward_bars") != 0
            or expected.get("timeframe") != "1d" or expected.get("mode") != "price_diagnostic"
            or expected.get("gap_policy") != "contiguous_segments"):
        raise ValueError("P0 must be a past-only daily price-diagnostic request")
    manifest_path = _verified_path(root, "frame-manifest.json", summary["frame_manifest_sha256"])
    manifest = read(manifest_path)
    if len(manifest) != summary["frames"] or not set(manifest).issubset(expected["symbols"]):
        raise ValueError("P0 saved universe differs from its own frozen request")
    for symbol, entry in sorted(manifest.items()):
        if (entry.get("stage") != "research" or entry.get("backward_bars") != 60
                or entry.get("forward_bars") != 0):
            raise ValueError(f"{symbol}: not a second-stage past60 returned frame")
        path = _verified_path(root, entry["path"], entry["sha256"])
        if path.parent != root / "returned-frames":
            raise ValueError(f"{symbol}: frame is not in this P0 returned-frames directory")
        request = read(_verified_path(root, entry["request_path"], entry["request_sha256"]))
        receipt = read(_verified_path(root, entry["startup_report_path"], entry["startup_report_sha256"]))
        if receipt.get("request") != request or receipt.get("status") != "PRICE_DIAGNOSTIC_INPUTS_VERIFIED":
            raise ValueError(f"{symbol}: receipt/request mismatch")
        if (symbol not in request["symbols"] or not set(request["symbols"]).issubset(expected["symbols"])
                or {k: v for k, v in request.items() if k != "symbols"}
                != {k: v for k, v in expected.items() if k != "symbols"}):
            raise ValueError(f"{symbol}: receipt belongs to another input request")
        frame = pd.read_pickle(path, compression="gzip")
        digest = hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).values.tobytes()).hexdigest()
        if (digest != entry["dataframe_hash"] or len(frame) != entry["rows"]
                or list(frame.columns) != entry["columns"] or not frame.symbol.eq(symbol).all()):
            raise ValueError(f"{symbol}: returned dataframe content/identity mismatch")
        if (not frame.ts.ge(pd.Timestamp(expected["start"])).all()
                or not (frame.ts + DAY).le(pd.Timestamp(expected["end"])).all()):
            raise ValueError(f"{symbol}: returned frame exceeds its frozen time range")
        yield symbol, frame


def wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """段首 TR=H-L；首 period 根 TR 均值播种，之后 Wilder 递推。"""
    n = len(close)
    result = np.full(n, np.nan)
    if not n:
        return result
    previous = np.r_[close[0], close[:-1]]
    tr = np.maximum(high - low, np.maximum(np.abs(high - previous), np.abs(low - previous)))
    if n >= period:
        result[period - 1] = tr[:period].mean()
        for i in range(period, n):
            result[i] = ((period - 1) * result[i - 1] + tr[i]) / period
    return result


def strength_bins(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """固定边界；不增加近零容差、截顶或按样本校准。"""
    x = np.asarray(values, dtype=float)
    active = np.asarray(valid, dtype=bool) & np.isfinite(x) & (x > 0)
    out = np.zeros(len(x), dtype=np.int8)
    out[active & (x <= 1)] = 1
    out[active & (x > 1) & (x <= 2)] = 2
    out[active & (x > 2)] = 3
    return out


def _validate_frame(frame: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[pd.DataFrame, pd.Timestamp, np.ndarray]:
    required = {"symbol", "ts", "open", "high", "low", "close", "volume", "eligible",
                "research_segment_id", "research_window_valid"}
    if not required.issubset(frame.columns) or frame.empty:
        raise ValueError("nonempty verified frame with OHLCV, identity and window columns required")
    f = frame.reset_index(drop=True).copy()
    if f.symbol.isna().any() or f.symbol.nunique() != 1:
        raise ValueError("exactly one nonmissing symbol required")
    cutoff = pd.Timestamp(cutoff)
    if not isinstance(f.ts.dtype, pd.DatetimeTZDtype) or cutoff.tz is None:
        raise ValueError("timestamps and cutoff must be timezone-aware")
    f["ts"] = f.ts.dt.tz_convert("UTC")
    cutoff = cutoff.tz_convert("UTC")
    if (f.ts.isna().any() or not f.ts.is_monotonic_increasing or f.ts.duplicated().any()
            or not f.ts.eq(f.ts.dt.normalize()).all() or (f.ts + DAY > cutoff).any()):
        raise ValueError("unordered, duplicate, non-daily or unclosed timestamps")
    for column in ("eligible", "research_window_valid"):
        if not pd.api.types.is_bool_dtype(f[column]) or f[column].isna().any():
            raise ValueError(f"{column} must be a nonmissing boolean mask")
    if (f.loc[f.eligible, "research_segment_id"].isna().any()
            or f.loc[~f.eligible, "research_segment_id"].notna().any()):
        raise ValueError("segment identity must exist exactly on eligible rows")
    for _, g in f.loc[f.eligible].groupby("research_segment_id", sort=False):
        if (not g.ts.diff().iloc[1:].eq(DAY).all() or not np.all(np.diff(g.index) == 1)):
            raise ValueError("eligible segment must be contiguous in time and original row position")
        prices = g[["open", "high", "low", "close"]].to_numpy(float)
        if not np.isfinite(prices).all() or (prices <= 0).any():
            raise ValueError("eligible OHLC must be finite and strictly positive")
        o, h, low, c = prices.T
        if (h < np.maximum(o, c)).any() or (low > np.minimum(o, c)).any() or (h < low).any():
            raise ValueError("eligible OHLC bounds are inconsistent")
    official = complete_window_mask(f, backward=60, forward=0).to_numpy(bool)
    if not np.array_equal(official, f.research_window_valid.to_numpy(bool)):
        raise ValueError("past60 mask differs from the verified returned frame")
    return f, cutoff, official


def build_panel(frame: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """生成全部原始日线行；事前信号永不依赖未来完整性。"""
    f, cutoff, official = _validate_frame(frame, cutoff)
    n = len(f)
    data = {name: f[name].to_numpy(copy=True) for name in
            ("symbol", "open", "high", "low", "close", "volume", "eligible", "research_segment_id")}
    data["ts"] = f.ts
    data["signal_time"] = f.ts + DAY
    data["official_past60"] = official
    float_columns = ["atr14", "atr14_lag", "sma7", "sma7_prev", "sma7_anchor", "anchor_close",
                     "sigma20_anchor", "log_return20_anchor", "entry_open", "exit_close20",
                     "high20_price", "low20_price", "l20"]
    time_columns = ["anchor_time"]
    for side, _ in SIDES:
        lower = side.lower()
        float_columns += [f"strength_{side}", f"prior_extreme_at_u_{side}", f"z_anchor_{side}",
                          f"z_prev_{side}", f"z_current_{side}", f"net_pullback_delta_{side}",
                          f"mfe20_{lower}", f"mae20_{lower}", f"peak20_{lower}_day",
                          f"adverse20_{lower}_day", f"giveback20_{lower}", f"mfe20_return_{lower}",
                          f"mae20_return_{lower}", f"giveback20_return_{lower}"]
        time_columns.append(f"pullback_time_{side}")
        data[f"pullback_index_{side}"] = np.full(n, -1, dtype=np.int64)
        data[f"pullback_age_{side}"] = np.full(n, -1, dtype=np.int8)
        for name in (*P_CONDITIONS, "P", "M"):
            data[f"{name}_{side}"] = np.zeros(n, dtype=bool)
    for name in float_columns:
        data[name] = np.full(n, np.nan)
    for name in time_columns:
        data[name] = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")
    data["anchor_index"] = np.full(n, -1, dtype=np.int64)
    data["segment_bar_index"] = np.full(n, -1, dtype=np.int64)
    for horizon in HORIZONS:
        data[f"q{horizon}"] = np.full(n, np.nan)
        data[f"ret{horizon}"] = np.full(n, np.nan)
        data[f"valid{horizon}"] = complete_window_mask(f, backward=60, forward=horizon).to_numpy(bool)
    for _, g in f.loc[f.eligible].groupby("research_segment_id", sort=False):
        idx = g.index.to_numpy()
        count = len(g)
        c, h, low, o = (g[column].to_numpy(float) for column in ("close", "high", "low", "open"))
        dates = g.ts.dt.tz_localize(None).to_numpy(dtype="datetime64[ns]")
        atr = wilder_atr(h, low, c)
        lag = np.r_[np.nan, atr[:-1]]
        ma = np.full(count, np.nan)
        if count >= 7:
            ma[6:] = np.lib.stride_tricks.sliding_window_view(c, 7).mean(axis=1)
        data["segment_bar_index"][idx] = np.arange(count)
        data["atr14"][idx], data["atr14_lag"][idx] = atr, lag
        data["sma7"][idx], data["sma7_prev"][idx] = ma, np.r_[np.nan, ma[:-1]]
        sigma = np.full(count, np.nan)
        numerator = np.full(count, np.nan)
        if count >= 21:
            returns = np.log(c[1:] / c[:-1])
            sigma[20:] = np.lib.stride_tricks.sliding_window_view(returns, 20).std(axis=1, ddof=1)
            numerator[20:] = np.log(c[20:] / c[:-20])
        sigma_anchor, numerator_anchor = np.full(count, np.nan), np.full(count, np.nan)
        if count > 6:
            positions = np.arange(6, count)
            anchors = positions - 6
            sigma_anchor[positions], numerator_anchor[positions] = sigma[anchors], numerator[anchors]
            target = idx[positions]
            data["anchor_index"][target], data["anchor_time"][target] = idx[anchors], dates[anchors]
            data["anchor_close"][target], data["sma7_anchor"][target] = c[anchors], ma[anchors]
        data["sigma20_anchor"][idx], data["log_return20_anchor"][idx] = sigma_anchor, numerator_anchor
        strength = np.full(count, np.nan)
        valid_sigma = np.isfinite(sigma_anchor) & (sigma_anchor > 0) & np.isfinite(numerator_anchor)
        strength[valid_sigma] = numerator_anchor[valid_sigma] / (sigma_anchor[valid_sigma] * np.sqrt(20.0))
        past = official[idx] & np.isfinite(lag) & (lag > 0) & np.isfinite(strength)
        delta = c - ma
        previous_delta = np.r_[np.nan, delta[:-1]]
        for side, direction in SIDES:
            data[f"strength_{side}"][idx] = direction * strength
            data[f"z_current_{side}"][idx] = direction * delta
            data[f"z_prev_{side}"][idx] = direction * previous_delta
            data[f"M_{side}"][idx] = past & (direction * delta > 0) & (direction * previous_delta < 0)
            if count <= 6:
                continue
            positions = np.arange(6, count)
            anchors = positions - 6
            target = idx[positions]
            window = anchors[:, None] + np.arange(1, 6)
            z = direction * delta[window]
            adverse = z < 0
            has_u = adverse.any(axis=1)
            first = adverse.argmax(axis=1)
            u = anchors + first + 1
            prior = anchors[:, None] + np.arange(5)
            allowed = np.arange(5)[None, :] <= first[:, None]
            extreme = np.where(allowed, direction * c[prior], -np.inf).max(axis=1)
            after = np.arange(5)[None, :] > first[:, None]
            conditions = (
                direction * delta[anchors] > 0,
                has_u,
                has_u & (direction * c[u] < extreme),
                has_u & ~((z > 0) & after).any(axis=1),
                z[:, -1] < 0,
                direction * (c[positions - 1] - c[anchors]) < 0,
            )
            for name, values in zip(P_CONDITIONS, conditions):
                data[f"{name}_{side}"][target] = values
            data[f"P_{side}"][target] = past[positions] & np.logical_and.reduce(conditions)
            data[f"z_anchor_{side}"][target] = direction * delta[anchors]
            data[f"net_pullback_delta_{side}"][target] = direction * (c[positions - 1] - c[anchors])
            found = target[has_u]
            data[f"pullback_index_{side}"][found] = idx[u[has_u]]
            data[f"pullback_time_{side}"][found] = dates[u[has_u]]
            data[f"pullback_age_{side}"][found] = positions[has_u] - u[has_u]
            data[f"prior_extreme_at_u_{side}"][found] = direction * extreme[has_u]
        if count > 1:
            data["entry_open"][idx[:-1]] = o[1:]
        for horizon in HORIZONS:
            if count <= horizon:
                continue
            positions = idx[:-horizon]
            mask = data[f"valid{horizon}"][positions] & past[:-horizon]
            target = positions[mask]
            entry, exit_price, scale = o[1:count-horizon+1][mask], c[horizon:][mask], lag[:-horizon][mask]
            data[f"q{horizon}"][target] = (exit_price - entry) / scale
            data[f"ret{horizon}"][target] = exit_price / entry - 1
            if horizon != 20:
                continue
            highs = np.lib.stride_tricks.sliding_window_view(h[1:], 20)[mask]
            lows = np.lib.stride_tricks.sliding_window_view(low[1:], 20)[mask]
            max_price, min_price = highs.max(axis=1), lows.min(axis=1)
            data["exit_close20"][target] = exit_price
            data["high20_price"][target], data["low20_price"][target] = max_price, min_price
            for side, direction in SIDES:
                lower = side.lower()
                favorable = max_price - entry if direction == 1 else entry - min_price
                adverse_move = entry - min_price if direction == 1 else max_price - entry
                data[f"mfe20_{lower}"][target] = favorable / scale
                data[f"mae20_{lower}"][target] = adverse_move / scale
                data[f"mfe20_return_{lower}"][target] = favorable / entry
                data[f"mae20_return_{lower}"][target] = adverse_move / entry
                data[f"peak20_{lower}_day"][target] = (highs.argmax(axis=1) if direction == 1 else lows.argmin(axis=1)) + 1
                data[f"adverse20_{lower}_day"][target] = (lows.argmin(axis=1) if direction == 1 else highs.argmax(axis=1)) + 1
                data[f"giveback20_{lower}"][target] = favorable / scale - direction * data["q20"][target]
                data[f"giveback20_return_{lower}"][target] = favorable / entry - direction * data["ret20"][target]
    feature = (official & np.isfinite(data["atr14_lag"]) & (data["atr14_lag"] > 0)
               & np.isfinite(data["strength_LONG"]))
    data["feature_valid"] = feature
    data["strength_zero"] = feature & (data["strength_LONG"] == 0)
    data["feature_status"] = np.select(
        [~official, ~np.isfinite(data["atr14_lag"]) | (data["atr14_lag"] <= 0), ~np.isfinite(data["strength_LONG"])],
        ["PAST_WINDOW_INCOMPLETE", "INVALID_LAG_ATR", "INVALID_ANCHOR_STRENGTH"], default="DEFINED")
    for side, _ in SIDES:
        bins = strength_bins(data[f"strength_{side}"], feature)
        domain = bins > 0
        data[f"strength_bin_{side}"] = bins
        data[f"cell_{side}"] = np.where(domain, 2 * data[f"P_{side}"].astype(np.int8)
                                                + data[f"M_{side}"].astype(np.int8), -1).astype(np.int8)
        data[f"ALL_{side}"] = domain
        data[f"HIGH_{side}"] = bins == 3
        data[f"HIGH_P_{side}"] = (bins == 3) & data[f"P_{side}"]
        data[f"HIGH_PM_{side}"] = data[f"HIGH_P_{side}"] & data[f"M_{side}"]
    segment_end = f.groupby("research_segment_id", sort=False).ts.transform("max") + DAY
    for horizon in HORIZONS:
        valid = data[f"valid{horizon}"] & feature
        if not np.isfinite(data[f"q{horizon}"][valid]).all():
            raise ValueError(f"nonfinite label in complete {horizon}-day window")
        data[f"valid{horizon}"] = valid
        expected_end = f.ts + (horizon + 1) * DAY
        interrupted = feature & (segment_end < expected_end).to_numpy(bool) & (segment_end < cutoff).to_numpy(bool)
        immature = feature & ~interrupted & (expected_end > cutoff).to_numpy(bool)
        censored = feature & ~valid & ~immature
        data[f"known_interruption{horizon}"] = interrupted
        data[f"administrative_unmatured{horizon}"] = immature
        data[f"censored{horizon}"] = censored
        data[f"label{horizon}_status"] = np.select(
            [~feature, valid, immature], ["PAST_INELIGIBLE", "COMPLETE_CONTIGUOUS", "ADMINISTRATIVE_UNMATURED"],
            default="CENSORED_GAP_OR_IDENTITY_BOUNDARY")
    data["l20"] = data["q20"] - data["q5"]
    panel = pd.DataFrame(data)
    for name in time_columns:
        panel[name] = pd.to_datetime(panel[name], utc=True)
    if panel.loc[~panel.feature_valid, list(GROUPS)].to_numpy().any():
        raise ValueError("signal escaped past-only eligibility")
    panel.attrs["schema"] = PANEL_SCHEMA
    panel.attrs["kernel"] = "trend-strength-pullback-restart/v1"
    return panel


def direction_events(panel: pd.DataFrame, direction: str | int, *, eligible_only: bool = True) -> pd.DataFrame:
    """方向整洁视图；qH、retH、l20 在此乘一次 d，wide 原列留在调用方。

    默认保留全部事前 x>0 观察，包括未来截尾；不会按 valid20 筛选。
    """
    if isinstance(direction, (bool, np.bool_)) or direction not in ("LONG", "SHORT", 1, -1):
        raise ValueError("direction must be LONG/SHORT or +1/-1")
    if "labels_direction_applied" in panel.attrs:
        raise ValueError("direction_events requires the original unsigned wide panel")
    side, d = ("LONG", 1) if direction in ("LONG", 1) else ("SHORT", -1)
    rows = panel.loc[panel[f"ALL_{side}"]].copy() if eligible_only else panel.copy()
    rows["direction"], rows["side"] = d, side
    for name in ("strength", "strength_bin", "P", "M", "cell", "pullback_time", "pullback_index", "pullback_age", *P_CONDITIONS):
        rows[name] = rows[f"{name}_{side}"]
    for name in ["l20", *(f"q{h}" for h in HORIZONS), *(f"ret{h}" for h in HORIZONS)]:
        rows[name] = d * rows[name]
    for name in ("mfe20", "mae20", "giveback20", "mfe20_return", "mae20_return", "giveback20_return"):
        rows[name] = rows[f"{name}_{side.lower()}"]
    rows.attrs["labels_direction_applied"] = d
    return rows


def event_probe(panel: pd.DataFrame, group: str, slippage: float = .0004, fee: float = .001) -> pd.DataFrame:
    """完整20日事件的固定入场名义额成本探针；不是不重叠账户或含资金费净收益。"""
    if group not in GROUPS:
        raise ValueError("unknown fixed group")
    if "labels_direction_applied" in panel.attrs:
        raise ValueError("event_probe requires the original unsigned wide panel")
    if not all(np.isfinite(x) and 0 <= x < 1 for x in (slippage, fee)):
        raise ValueError("fee/slippage must be finite and in [0,1)")
    d = 1 if group.endswith("LONG") else -1
    rows = panel.loc[panel[group] & panel.valid20].copy()
    entry = rows.entry_open * (1 + d * slippage)
    exit_price = rows.exit_close20 * (1 - d * slippage)
    rows["direction"], rows["group"] = d, group
    rows["gross_return"] = d * rows.ret20
    rows["return_after_fee_slippage"] = d * (exit_price - entry) / entry - fee * (1 + exit_price / entry)
    rows["fees_fraction_entry_notional"] = fee * (1 + exit_price / entry)
    rows["funding_verified"] = False
    return rows
