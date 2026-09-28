"""Frozen v5 plus two mutually exclusive V3 opportunity experiments.

Default bounded waiting preserves every v5 account calculation and table.
The state-valid entry candidate and legacy-short-TP protection are isolated
controls; neither adds MA30 management or changes the V3 progress ratchet.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Config:
    slope: float = 0.05
    reverse: bool = True
    short_exit: str = "accel1_rsi30"
    fee: float = 0.0005
    slip: float = 0.0003
    delay_hours: int = 0
    entry_mode: str = "original"
    tighten_mode: str = "fixed"
    profit_trigger_atr: float = 0.0
    progress_days: int = 0
    progress_source: str = "high_low"
    stop_anchor: str = "ma"
    exit_opposite_cross: bool = False
    initial_stop_cap_pct: float | None = None
    entry_wait_days: int = 0
    direction_mode: str = "both"
    trend_filter: str = "none"
    risk_fraction: float | None = None
    notional_fraction: float = 1.0
    progress_policy: str = "permanent"
    exit_state_policy: str = "v3"
    admission_routing: bool = False
    ma30_mode: str = "none"
    entry_wait_policy: str = "bounded"

    def __post_init__(self):
        if self.entry_wait_policy not in {"bounded", "until_invalid"}:
            raise ValueError("Unknown entry wait policy")
        opportunity_entry = self.entry_wait_policy == "until_invalid"
        opportunity_exit = self.short_exit == "accel1_rsi30_protect"
        if opportunity_entry and opportunity_exit:
            raise ValueError("Opportunity entry and short protection must be tested separately")
        if (opportunity_entry or opportunity_exit) and (
                self.reverse or self.progress_days != 4
                or self.progress_source != "high_low" or self.progress_policy != "permanent"
                or self.stop_anchor != "ma" or self.delay_hours != 0
                or self.entry_mode != "original" or self.entry_wait_days != 0
                or self.exit_state_policy != "v3" or self.ma30_mode != "none"
                or self.admission_routing or self.exit_opposite_cross
                or self.initial_stop_cap_pct is not None or self.trend_filter != "none"
                or self.direction_mode != "both" or self.risk_fraction is not None
                or self.notional_fraction != 1.0 or self.tighten_mode != "fixed"
                or self.profit_trigger_atr != 0):
            raise ValueError("Opportunity experiments require the original V3 execution controls")
        if opportunity_entry and self.short_exit != "accel1_rsi30":
            raise ValueError("Opportunity entry preserves V3 short take profit")
        if self.ma30_mode not in {"none", "defense", "extend", "both"}:
            raise ValueError("Unknown MA30 management mode")
        if self.ma30_mode != "none" and not self.admission_routing:
            raise ValueError("MA30 management requires fixed daily admission routing")
        if not isinstance(self.admission_routing, (bool, np.bool_)):
            raise ValueError("admission_routing must be boolean")
        if self.admission_routing and (
                self.reverse or self.progress_days != 4
                or self.progress_source != "high_low" or self.progress_policy != "permanent"
                or self.stop_anchor != "ma" or self.delay_hours != 0
                or self.entry_mode != "original" or self.entry_wait_days != 0
                or self.exit_state_policy != "v3" or self.short_exit != "accel1_rsi30"
                or self.exit_opposite_cross):
            raise ValueError("Admission routing requires the original V3 entry and execution controls")
        if self.exit_state_policy not in {"v3", "defense", "trend", "extension"}:
            raise ValueError("Unknown exit state policy")
        if self.exit_state_policy != "v3" and (self.progress_days != 4 or self.reverse
                or self.progress_source != "high_low" or self.progress_policy != "permanent"
                or self.stop_anchor != "ma" or self.delay_hours != 0):
            raise ValueError("State policies require the frozen V3 execution controls")
        if self.exit_state_policy == "extension" and self.short_exit != "none":
            raise ValueError("Extension replaces the old short hard take profit")
        if self.direction_mode not in {"both", "long", "short"}:
            raise ValueError(f"Unknown direction mode: {self.direction_mode}")
        if self.trend_filter not in {"none", "ma30_ready", "ma30_direction"}:
            raise ValueError(f"Unknown trend filter: {self.trend_filter}")
        if (self.risk_fraction is not None
                and (not np.isfinite(self.risk_fraction) or not 0 < self.risk_fraction <= 1)):
            raise ValueError("risk_fraction must lie in (0, 1]")
        if not np.isfinite(self.notional_fraction) or not 0 < self.notional_fraction <= 1:
            raise ValueError("notional_fraction must lie in (0, 1]")
        if self.progress_policy not in {"permanent", "reset_on_new_extreme"}:
            raise ValueError(f"Unknown progress policy: {self.progress_policy}")
        if (not isinstance(self.entry_wait_days, (int, np.integer))
                or isinstance(self.entry_wait_days, bool) or self.entry_wait_days < 0):
            raise ValueError("entry_wait_days must be a nonnegative integer")
        if self.entry_wait_days and self.entry_mode != "original":
            raise ValueError("Deferred entry requires original entry_mode")
        if self.entry_mode not in {"original", "opposite_slowdown", "absolute_slowdown", "no_slope"}:
            raise ValueError(f"Unknown entry mode: {self.entry_mode}")
        if self.tighten_mode not in {"fixed", "stall_only", "armed_daily"}:
            raise ValueError(f"Unknown tightening mode: {self.tighten_mode}")
        if not np.isfinite(self.profit_trigger_atr) or self.profit_trigger_atr < 0:
            raise ValueError("profit_trigger_atr must be finite and nonnegative")
        if (not isinstance(self.progress_days, (int, np.integer))
                or isinstance(self.progress_days, bool) or self.progress_days < 0):
            raise ValueError("progress_days must be a nonnegative integer")
        if self.progress_source not in {"high_low", "close"}:
            raise ValueError(f"Unknown progress source: {self.progress_source}")
        if self.stop_anchor not in {"ma", "extreme"}:
            raise ValueError(f"Unknown stop anchor: {self.stop_anchor}")
        if self.stop_anchor == "extreme" and self.progress_days == 0:
            raise ValueError("Extreme protection requires progress_days > 0")
        if (self.initial_stop_cap_pct is not None
                and (not np.isfinite(self.initial_stop_cap_pct)
                     or not 0 < self.initial_stop_cap_pct < 1)):
            raise ValueError("initial_stop_cap_pct must lie strictly between 0 and 1")

    @property
    def name(self):
        cap = "none" if self.initial_stop_cap_pct is None else f"{self.initial_stop_cap_pct:g}"
        name = (f"s{self.slope:g}_rev{int(self.reverse)}_{self.short_exit}"
                f"_{self.entry_mode}_{self.tighten_mode}_p{self.profit_trigger_atr:g}"
                f"_n{self.progress_days}_{self.stop_anchor}_x{int(self.exit_opposite_cross)}_cap{cap}"
                f"_source{self.progress_source}_wait{self.entry_wait_days}")
        if self.exit_state_policy != "v3":
            name += "_state_" + self.exit_state_policy
        if self.admission_routing:
            name += "_admission_routing"
        if self.ma30_mode != "none":
            name += "_ma30_" + self.ma30_mode
        if self.entry_wait_policy != "bounded":
            name += "_wait_policy_" + self.entry_wait_policy
        # Keep the historical name byte-for-byte when new controls are off.
        if (self.direction_mode == "both" and self.trend_filter == "none"
                and self.risk_fraction is None and self.notional_fraction == 1
                and self.progress_policy == "permanent"):
            return name
        risk = "none" if self.risk_fraction is None else f"{self.risk_fraction:g}"
        return (name + f"_dir{self.direction_mode}_trend{self.trend_filter}"
                f"_risk{risk}_notional{self.notional_fraction:g}_progress{self.progress_policy}")


def wilder(values, period):
    a = np.asarray(values, dtype=float)
    out = np.full(len(a), np.nan)
    seed = []
    last = np.nan
    for i, value in enumerate(a):
        if not np.isfinite(value):
            seed, last = [], np.nan
            continue
        if not np.isfinite(last):
            seed.append(value)
            if len(seed) == period:
                last = float(np.mean(seed))
        else:
            last = ((period - 1) * last + value) / period
        out[i] = last
    return out


def features(daily):
    d = daily.copy().reset_index(drop=True)
    d["timestamp"] = pd.to_datetime(d.timestamp, utc=True)
    if d.timestamp.duplicated().any() or not d.timestamp.diff().dropna().eq(pd.Timedelta(days=1)).all():
        raise ValueError("Daily gaps/duplicates must not be bridged")
    if "research_segment_id" in d and d.research_segment_id.nunique() != 1:
        raise ValueError("This experiment requires one continuous segment")
    close = d.close
    delta = close.diff()
    tr = pd.concat([d.high - d.low, (d.high - close.shift()).abs(), (d.low - close.shift()).abs()], axis=1).max(axis=1)
    tr.iloc[0] = np.nan
    d["ma"] = close.rolling(7).mean()
    d["ma30"] = close.rolling(30).mean()
    d["prev_ma30"] = d.ma30.shift()
    d["ma30_ready"] = d[["ma30", "prev_ma30"]].notna().all(axis=1)
    d["atr"] = wilder(tr, 14)
    up = wilder(delta.clip(lower=0), 6)
    down = wilder((-delta).clip(lower=0), 6)
    with np.errstate(divide="ignore", invalid="ignore"):
        rsi = 100 - 100 / (1 + up / down)
    rsi[(up == 0) & (down == 0)] = 50
    rsi[(up > 0) & (down == 0)] = 100
    d["rsi"] = rsi
    d["slope"] = d.ma.diff() / d.atr
    d["cross"] = np.select([(close.shift() <= d.ma.shift()) & (close > d.ma), (close.shift() >= d.ma.shift()) & (close < d.ma)], [1, -1], 0)
    drop = -delta
    d["accel1"] = (drop >= d.atr.shift()) & (drop > drop.shift().clip(lower=0))
    two = drop + drop.shift()
    d["accel2"] = (drop > 0) & (drop.shift() > 0) & (two >= 1.5 * d.atr.shift(2)) & (two > (drop.shift(2) + drop.shift(3)).clip(lower=0))
    d["ready"] = (np.arange(len(d)) >= 28) & d[["ma", "atr", "rsi", "slope"]].notna().all(axis=1)
    if "research_window_valid" in d:
        d["ready"] &= d.research_window_valid.astype(bool)
    return d


def enrich_features(daily_features):
    """Add causal MA dollar steps without recalculating the frozen R1 indicators."""
    d = daily_features.copy().reset_index(drop=True)
    d["ma_step"] = d.ma.diff()
    d["prev_ma_step"] = d.ma_step.shift()
    d["ma_step_change"] = d.ma_step - d.prev_ma_step
    # v1 frozen feature frames have no MA30 columns. Add only the new causal
    # values, retaining all original indicators and the original ready flag.
    if "ma30" not in d:
        d["ma30"] = d.close.rolling(30).mean()
    if "prev_ma30" not in d:
        d["prev_ma30"] = d.ma30.shift()
    d["ma30_ready"] = d[["ma30", "prev_ma30"]].notna().all(axis=1)
    d["sm_delta"] = d.close.diff()
    d["sm_previous_delta"] = d.sm_delta.shift()
    d["sm_previous_atr"] = d.atr.shift()
    d["sm_previous_atr2"] = d.atr.shift(2)
    return d


def exit_state_step(p, row, policy):
    """Closed, wholly held daily bar only; no future or unheld extrema.

    The caller updates V3's cumulative extreme/counter first, then applies
    this transition before choosing this day's single multiplier decrement.
    """
    side, atr = p["side"], float(row.atr)
    closes = p.setdefault("_sm_closes", [p["entry_reference"]])
    closes.append(float(row.close))
    closes[:] = closes[-4:]
    p["sm_held_days"] = p.get("sm_held_days", 0) + 1
    ready = p["sm_held_days"] >= 3
    diffs = np.diff(closes)
    distance = float(np.abs(diffs).sum()) if ready else float("nan")
    eff = (float(side * diffs.sum() / distance) if distance > 0 else 0.0) if ready else float("nan")
    speed3 = float(side * diffs.sum() / atr) if ready else float("nan")
    retrace = float(side * (p["extreme_price"] - row.close) / atr)
    net_move = float(side * (row.close - p["entry_price"]))
    ma_dist = float(side * (row.close - row.ma) / atr)
    speed1 = float(side * row.sm_delta / row.sm_previous_atr)
    speed0 = float(side * row.sm_previous_delta / row.sm_previous_atr2)
    failed = ma_dist <= 0 and net_move <= 0
    pulled_back = retrace >= 1.25
    chopped = ready and eff <= .2 and p["no_new_extreme_days"] >= 3 and net_move <= 0
    defense = bool(failed or pulled_back or chopped)
    healthy = bool(ready and eff >= .6 and speed3 >= .5 and ma_dist > 0 and retrace <= .75)
    extreme_rsi = bool(row.rsi >= 80 if side == 1 else row.rsi <= 20)
    acceleration = bool((speed1 >= 1 and speed1 > max(speed0, 0))
                        or (ready and speed3 >= 2 and eff >= .6))
    extended = bool(ma_dist >= 2 or extreme_rsi)
    watch = p.get("sm_watch", "NORMAL")
    transition = "unchanged"
    observed_extreme = float(row.high if side == 1 else row.low)
    if policy == "extension":
        if watch == "NORMAL" and acceleration and extended:
            watch, transition = "WATCH", "watch_started"
            p["sm_watch_start"] = row.timestamp
            p["sm_watch_atr"] = atr
            p["sm_watch_extreme"] = observed_extreme
            p["sm_peak_speed"] = max(float(side * row.sm_delta / atr), 0.)
        elif watch in {"WATCH", "PROTECT"}:
            p["sm_watch_extreme"] = (max if side == 1 else min)(p["sm_watch_extreme"], observed_extreme)
            fixed_speed = float(side * row.sm_delta / p["sm_watch_atr"])
            p["sm_peak_speed"] = max(p["sm_peak_speed"], fixed_speed)
            watch_retrace = side * (p["sm_watch_extreme"] - row.close) / p["sm_watch_atr"]
            if watch == "WATCH":
                if fixed_speed <= .5 * p["sm_peak_speed"] and watch_retrace >= .75:
                    watch, transition = "PROTECT", "exhaustion_protect"
                    p["sm_protect_day"] = row.timestamp
                elif ma_dist < 2 and not extreme_rsi:
                    watch, transition = "NORMAL", "watch_cleared"
                    for key in ("sm_watch_start", "sm_watch_atr", "sm_watch_extreme", "sm_peak_speed"):
                        p[key] = None
        p["sm_watch"] = watch
    protect = watch == "PROTECT"
    state = ("PROTECT" if protect else "DEFENSE" if defense else "WATCH" if watch == "WATCH"
             else "HEALTHY" if healthy else "PROBE" if not ready else "ORDINARY")
    p["sm_state"] = state
    p["sm_defense_days"] = p.get("sm_defense_days", 0) + int(defense)
    p["sm_healthy_days"] = p.get("sm_healthy_days", 0) + int(healthy)
    p["sm_protect_days"] = p.get("sm_protect_days", 0) + int(protect)
    defensive_stop = float(row.close - side * .5 * atr) if defense else None
    protection_stop = (float(p["sm_watch_extreme"] - side * p["sm_watch_atr"]) if protect else None)
    return {"sm_state": state, "sm_transition": transition, "sm_held_days": p["sm_held_days"],
            "sm_ready3": ready, "sm_flat3": bool(ready and distance == 0),
            "sm_efficiency3": eff, "sm_speed3": speed3, "sm_speed1": speed1,
            "sm_speed0": speed0, "sm_retrace_atr": retrace, "sm_ma_distance": ma_dist,
            "sm_failed_cross": bool(failed), "sm_large_retrace": bool(pulled_back),
            "sm_chopped": bool(chopped), "sm_defense": defense, "sm_healthy": healthy,
            "sm_acceleration": acceleration, "sm_extended": extended,
            "sm_watch": watch, "sm_protect": protect,
            "sm_watch_start": p.get("sm_watch_start"), "sm_watch_atr": p.get("sm_watch_atr"),
            "sm_watch_extreme": p.get("sm_watch_extreme"), "sm_peak_speed": p.get("sm_peak_speed"),
            "sm_defensive_stop": defensive_stop, "sm_protection_stop": protection_stop}


def ma30_exit_state_step(p, row, mode, profit_eligible):
    """MA30 overlay evaluated once after a fully held daily bar closes.

    The v4 helper supplies the unchanged causal path measurements. Its generic
    defense/health recommendations and counters are replaced, not combined,
    with this experiment's explicitly gated MA30 recommendations.
    """
    z = exit_state_step(p, row, "v3")
    s, a = p["side"], float(row.atr)
    q = s * (float(row.ma30) - float(row.prev_ma30)) / a
    x = s * (float(row.close) - float(row.ma30)) / a
    if not np.isfinite(q) or not np.isfinite(x):
        raise ValueError("MA30 management needs finite closed MA30 state")
    conflict, aligned = q <= -.05, q >= .05 and x > 0
    weak_path = (z["sm_ready3"] and z["sm_efficiency3"] <= .2
                 and s * (row.close - p["entry_price"]) <= 0)
    pressure = z["sm_ma_distance"] <= 0 or z["sm_retrace_atr"] >= .75 or weak_path
    defensive = bool(mode in {"defense", "both"} and conflict and pressure)
    allow_extension = mode in {"extend", "both"}
    healthy = bool(allow_extension and aligned and profit_eligible and z["sm_healthy"])
    watch = p.get("sm_watch", "NORMAL")
    transition = "unchanged"
    observed = float(row.high if s == 1 else row.low)
    if allow_extension:
        if watch == "NORMAL" and aligned and profit_eligible and z["sm_acceleration"] and z["sm_extended"]:
            watch, transition = "WATCH", "watch_started"
            p["sm_watch_start"], p["sm_watch_atr"] = row.timestamp, a
            p["sm_watch_extreme"] = observed
            p["sm_peak_speed"] = max(float(s * row.sm_delta / a), 0.)
        elif watch in {"WATCH", "PROTECT"}:
            p["sm_watch_extreme"] = (max if s == 1 else min)(p["sm_watch_extreme"], observed)
            velocity = s * row.sm_delta / p["sm_watch_atr"]
            p["sm_peak_speed"] = max(p["sm_peak_speed"], velocity)
            draw = s * (p["sm_watch_extreme"] - row.close) / p["sm_watch_atr"]
            if watch == "WATCH":
                if velocity <= .5 * p["sm_peak_speed"] and draw >= .75:
                    watch, transition = "PROTECT", "exhaustion_protect"
                    p["sm_protect_day"] = row.timestamp
                elif not aligned or (z["sm_ma_distance"] < 2 and not (row.rsi >= 80 if s == 1 else row.rsi <= 20)):
                    transition = "watch_alignment_lost" if not aligned else "watch_cleared"
                    watch = "NORMAL"
                    for key in ("sm_watch_start", "sm_watch_atr", "sm_watch_extreme", "sm_peak_speed"):
                        p[key] = None
    protect = watch == "PROTECT"
    suppress = bool(allow_extension and profit_eligible and (healthy or (watch == "WATCH" and aligned)))
    # A triggered permanent protection state takes priority over healthy pause.
    if protect:
        suppress = False
    state = ("PROTECT" if protect else "DEFENSE" if defensive else "WATCH" if watch == "WATCH"
             else "HEALTHY" if healthy else "PROBE" if not z["sm_ready3"] else "ORDINARY")
    for name, flag in (("defense", defensive), ("healthy", healthy), ("protect", protect)):
        p["sm_" + name + "_days"] += int(flag) - int(z["sm_" + name])
    p["sm_watch"], p["sm_state"], p["m30_suppress_short_tp"] = watch, state, suppress
    z.update(sm_state=state, sm_transition=transition, sm_defense=defensive,
             sm_healthy=healthy, sm_protect=protect, sm_watch=watch,
             sm_watch_start=p.get("sm_watch_start"), sm_watch_atr=p.get("sm_watch_atr"),
             sm_watch_extreme=p.get("sm_watch_extreme"), sm_peak_speed=p.get("sm_peak_speed"),
             sm_defensive_stop=float(row.close - s * .5 * a) if defensive else None,
             sm_protection_stop=float(p["sm_watch_extreme"] - s * p["sm_watch_atr"]) if protect else None,
             m30_q=float(q), m30_x=float(x), m30_conflict=bool(conflict),
             m30_aligned=bool(aligned), m30_pressure=bool(pressure),
             m30_profit_eligible=bool(profit_eligible), m30_suppress_short_tp=suppress,
             m30_short_tp_actually_suppressed=False)
    return z


def entry_qualification(row, side, config=Config()):
    """Return the first qualifying reason; crossing/position rules are external."""
    if side not in (-1, 1) or not bool(row.ready):
        return None
    if side * row.slope > config.slope:
        return "original"
    if config.entry_mode == "no_slope":
        return "no_slope"
    if config.entry_mode == "opposite_slowdown":
        if side * row.prev_ma_step < 0 and side * (row.ma_step - row.prev_ma_step) > 0:
            return "opposite_slowdown"
    elif config.entry_mode == "absolute_slowdown":
        if abs(row.ma_step) < abs(row.prev_ma_step):
            return "absolute_slowdown"
    return None


ENTRY_EVENT_COLUMNS = [
    "timestamp", "signal_day", "side", "cross", "entry_reason", "cross_day",
    "stage", "reason", "status", "entry_filter", "direction_mode", "entry_slope",
    "entry_close", "entry_ma", "entry_ma30", "entry_prev_ma30", "trade_id",
    "attempt_before_equity", "entry_price", "initial_stop", "initial_stop_fill",
    "initial_stop_unit_risk", "qty_cap", "qty", "initial_planned_risk",
    "initial_planned_risk_pct", "risk_fraction", "notional_fraction",
    "initial_stop_price_nonpositive",
    "admission_allowed", "admission_rule_id", "admission_signal_day",
    "exit_route", "route_short_exit",
]

# Only the new candidate policy emits these fields; legacy dictionaries and
# account tables remain unchanged when both opportunity controls are disabled.
CANDIDATE_EVENT_COLUMNS = [
    "candidate_wait_policy", "candidate_cross_close", "candidate_age_days",
    "candidate_correct_side", "candidate_slope_met", "candidate_breaks_cross_close",
]


def validate_admission_routes(daily_features):
    """Fail closed on a malformed externally supplied decision table.

    This validates every row, including warmup and rejected directions. It
    never computes a rule from future outcomes, coerces strings/numbers into
    booleans, or substitutes an admission or route for missing data.
    """
    routes = {"v3", "defense", "trend", "extension"}
    for direction in ("long", "short"):
        for stem in ("admit", "route", "rule_id"):
            column = f"{stem}_{direction}"
            if column not in daily_features:
                raise ValueError("Missing admission-routing column: " + column)
            values = daily_features[column]
            if stem == "admit":
                valid = values.map(lambda value: isinstance(value, (bool, np.bool_)))
            elif stem == "route":
                valid = values.map(lambda value: isinstance(value, str) and value in routes)
            else:
                valid = values.map(lambda value: isinstance(value, str) and bool(value.strip()))
            if not valid.all():
                raise ValueError("Invalid admission-routing value in " + column)


def simulate(hourly, daily_features, config=Config(), start=None, end=None, funding=None,
             carry_daily=0.0, entry_events=None, fixed_episode=None):
    """Funding=None explicitly means price-only diagnostic, never verified net."""
    if fixed_episode is not None:
        for key in ("entry_equity", "qty"):
            if not np.isfinite(float(fixed_episode[key])) or float(fixed_episode[key]) <= 0:
                raise ValueError("Fixed episode requires finite positive " + key)
        if int(fixed_episode["side"]) not in (-1, 1):
            raise ValueError("Fixed episode requires a valid direction")
    h = hourly.copy()
    h["timestamp"] = pd.to_datetime(h.timestamp, utc=True)
    d = enrich_features(daily_features)
    d["timestamp"] = pd.to_datetime(d.timestamp, utc=True)
    if config.admission_routing:
        validate_admission_routes(d)
        if config.ma30_mode != "none" and not (d.route_long.eq("v3").all() and d.route_short.eq("v3").all()):
            raise ValueError("MA30 management only overlays V3 routes")
    first_start = d.loc[d.ready, "timestamp"].iloc[0] + pd.Timedelta(days=1)
    start = first_start if start is None else max(pd.Timestamp(start), first_start)
    end = h.timestamp.iloc[-1] + pd.Timedelta(hours=1) if end is None else pd.Timestamp(end)
    h = h[(h.timestamp >= start) & (h.timestamp < end)].reset_index(drop=True)
    if h.empty or not h.timestamp.diff().dropna().eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Missing/empty hourly execution grid")
    if h.timestamp.iloc[0] != start or h.timestamp.iloc[-1] + pd.Timedelta(hours=1) != end:
        raise ValueError("Incomplete requested execution window")
    day_map = {t: i for i, t in enumerate(d.timestamp)}
    daily_rows = list(d.itertuples(index=False))
    signal_indices = (h.timestamp.dt.floor("D") - pd.Timedelta(days=1)).map(day_map)
    if signal_indices.isna().any():
        raise ValueError("Missing preceding closed daily bar")
    signal_indices = signal_indices.astype(int).to_numpy()
    fund = []
    if funding is not None:
        f = funding.copy()
        f["timestamp"] = pd.to_datetime(f.timestamp, utc=True)
        f = f[(f.timestamp >= start) & (f.timestamp <= end)].sort_values("timestamp")
        fund = f.to_dict("records")
    fidx = 0
    initial_equity = 10000.0 if fixed_episode is None else float(fixed_episode["entry_equity"])
    cash, position = initial_equity, None
    trades, marks, stops, funding_log = [], [], [], []
    pending_reverse, pending_day, pending_entry = None, None, None
    peak, adverse_mdd, exposure_hours = initial_equity, 0.0, 0
    trade_id = 0
    entry_counts = {key: 0 for key in (
        "flat_ready_crosses", "flat_not_ready_crosses", "entry_attempts", "entry_fills",
        "slope_rejected", "direction_rejected", "ma30_not_ready_rejected",
        "ma30_direction_rejected", "invalid_stop_rejected", "nonpositive_equity_rejected",
        "invalid_unit_risk_rejected", "wait_candidates_created",
    )}
    if config.admission_routing:
        entry_counts["admission_rejected"] = 0
    if config.entry_wait_policy == "until_invalid":
        entry_counts.update(wait_candidates_confirmed=0, wait_candidates_cancelled=0,
                            wait_candidate_observations=0, wait_candidates_unresolved=0)

    def routing_details(row, side):
        if not config.admission_routing:
            return {}
        direction = "long" if side == 1 else "short"
        route = getattr(row, "route_" + direction)
        return {"admission_allowed": bool(getattr(row, "admit_" + direction)),
                "admission_rule_id": getattr(row, "rule_id_" + direction),
                "admission_signal_day": row.timestamp,
                "exit_route": route,
                "route_short_exit": "none" if route == "extension" else "accel1_rsi30"}

    def position_routing_details(p):
        if not config.admission_routing:
            return {}
        return {key: p[key] for key in (
            "admission_allowed", "admission_rule_id", "admission_signal_day",
            "exit_route", "route_short_exit")}

    def entry_event(timestamp, row, side, reason, cross_time, stage, outcome, status, details=None):
        if entry_events is not None:
            entry_events.append({
                "timestamp": timestamp, "signal_day": row.timestamp, "side": side,
                "cross": int(row.cross), "entry_reason": reason, "cross_day": cross_time,
                "stage": stage, "reason": outcome, "status": status,
                "entry_filter": config.trend_filter, "direction_mode": config.direction_mode,
                "entry_slope": float(row.slope), "entry_close": float(row.close),
                "entry_ma": float(row.ma), "entry_ma30": float(row.ma30),
                "entry_prev_ma30": float(row.prev_ma30),
                "trade_id": trade_id if status == "filled" else None,
                "attempt_before_equity": cash,
                "risk_fraction": config.risk_fraction, "notional_fraction": config.notional_fraction,
                **routing_details(row, side),
                **(details or {}),
            })

    def entry_filter_rejection(row, side):
        if ((config.direction_mode == "long" and side != 1)
                or (config.direction_mode == "short" and side != -1)):
            return "direction_rejected"
        if config.trend_filter != "none":
            if not bool(row.ma30_ready):
                return "ma30_not_ready_rejected"
            if (config.trend_filter == "ma30_direction"
                    and not (side * (row.close - row.ma30) > 0
                             and side * (row.ma30 - row.prev_ma30) > 0)):
                return "ma30_direction_rejected"
        return None

    def candidate_event(timestamp, row, intent, outcome, status):
        if config.entry_wait_policy != "until_invalid":
            return
        side = intent["side"]
        entry_event(timestamp, row, side, "delayed_cross", intent["cross_time"],
                    "candidate", outcome, status, {
                        "candidate_wait_policy": config.entry_wait_policy,
                        "candidate_cross_close": intent["cross_close"],
                        "candidate_age_days": int((row.timestamp - intent["cross_time"]).days),
                        "candidate_correct_side": bool(side * (row.close - row.ma) > 0),
                        "candidate_slope_met": bool(side * row.slope > config.slope),
                        "candidate_breaks_cross_close": bool(side * (row.close - intent["cross_close"]) > 0),
                    })
        entry_counts["wait_candidate_observations"] += 1
        if status == "cancelled":
            entry_counts["wait_candidates_cancelled"] += 1
        elif status == "confirmed":
            entry_counts["wait_candidates_confirmed"] += 1
        elif status == "unresolved":
            entry_counts["wait_candidates_unresolved"] += 1

    def short_protect_snapshot(p):
        if config.short_exit != "accel1_rsi30_protect":
            return {}
        return {key: p.get(key) for key in (
            "tp_protect_active", "tp_protect_signal_day", "tp_protect_event_atr",
            "tp_protect_extreme_low", "tp_protect_candidate", "tp_protect_trigger_rsi",
            "tp_protect_trigger_close", "tp_protect_eligible_signal_count",
            "tp_protect_suppressed_count")}

    def short_protect_step(p, row, full_holding_day):
        if config.short_exit != "accel1_rsi30_protect":
            return {}
        triggered = False
        eligible_signal = False
        if p["side"] == -1 and full_holding_day:
            # Exactly the legacy short trigger, including costs already charged
            # at this boundary. Activation is evaluated before today's gap stop;
            # the newly known line is never applied to yesterday's hourly bars.
            expected_fill = signal_close = float(row.close)
            expected_fill *= 1 + config.slip
            expected_profit = (p["qty"] * (p["entry_price"] - expected_fill)
                               - p["entry_fee"] - p["qty"] * expected_fill * config.fee
                               - p["funding_paid"] - p["carry_paid"])
            eligible_signal = bool(row.rsi <= 30 and expected_profit > 0 and row.accel1)
            if eligible_signal:
                p["tp_protect_eligible_signal_count"] += 1
                if not p["tp_protect_active"]:
                    triggered = True
                    p.update(tp_protect_active=True, tp_protect_signal_day=row.timestamp,
                             tp_protect_event_atr=float(row.atr),
                             tp_protect_extreme_low=float(row.low),
                             tp_protect_trigger_rsi=float(row.rsi),
                             tp_protect_trigger_close=signal_close)
            if p["tp_protect_active"]:
                p["tp_protect_extreme_low"] = min(p["tp_protect_extreme_low"], float(row.low))
                p["tp_protect_candidate"] = p["tp_protect_extreme_low"] + p["tp_protect_event_atr"]
        return {**short_protect_snapshot(p), "tp_protect_triggered_this_day": triggered,
                "tp_protect_eligible_signal": eligible_signal,
                "tp_protect_actually_suppressed": False}

    def equity(price):
        return cash if position is None else cash + position["side"] * position["qty"] * (price - position["entry_price"])

    def mark(timestamp, price, kind):
        nonlocal peak
        value = equity(price)
        peak = max(peak, value)
        marks.append({"timestamp": timestamp, "equity": value, "side": 0 if position is None else position["side"], "price": price, "kind": kind})

    def close_position(timestamp, price, reason, interval_end=None):
        nonlocal cash, position
        p = position
        fill = price * (1 - p["side"] * config.slip)
        pnl = p["side"] * p["qty"] * (fill - p["entry_price"])
        fee = p["qty"] * fill * config.fee
        cash += pnl - fee
        trades.append({**{k: v for k, v in p.items() if not k.startswith("_sm_")}, "exit_time": timestamp, "exit_interval_end": interval_end or timestamp,
                       "exit_price": fill, "exit_reference": price, "exit_reason": reason,
                       "gross_pnl": pnl, "exit_fee": fee, "net_pnl": pnl - p["entry_fee"] - fee - p["funding_paid"] - p["carry_paid"],
                       "end_equity": cash, "return_on_entry_equity": (cash - p["entry_equity"]) / p["entry_equity"]})
        position = None
        mark(timestamp, price, "exit")

    def open_position(timestamp, price, side, j, reason, cross_time):
        nonlocal position, cash, trade_id, pending_entry
        pending_entry = None  # An attempted fill consumes its signal, even if invalid.
        row = daily_rows[j]
        entry_counts["entry_attempts"] += 1
        rejection = entry_filter_rejection(row, side)
        if rejection is not None:
            entry_counts[rejection] += 1
            entry_event(timestamp, row, side, reason, cross_time, "filter", rejection, "rejected")
            return
        route_details = routing_details(row, side)
        if config.admission_routing and not route_details["admission_allowed"]:
            entry_counts["admission_rejected"] += 1
            entry_event(timestamp, row, side, reason, cross_time,
                        "admission", "admission_rejected", "rejected")
            return
        stop = float(row.ma - side * 1.5 * row.atr)
        if not np.isfinite(stop) or side * (price - stop) <= 0:
            entry_counts["invalid_stop_rejected"] += 1
            entry_event(timestamp, row, side, reason, cross_time,
                        "fill", "invalid_stop_rejected", "rejected", {"initial_stop": stop})
            return
        if cash <= 0:
            entry_counts["nonpositive_equity_rejected"] += 1
            entry_event(timestamp, row, side, reason, cross_time,
                        "fill", "nonpositive_equity_rejected", "rejected")
            return
        fill = price * (1 + side * config.slip)
        uncapped_stop = stop
        if config.initial_stop_cap_pct is not None:
            capped_stop = fill * (1 - side * config.initial_stop_cap_pct)
            stop = max(stop, capped_stop) if side == 1 else min(stop, capped_stop)
            if side * (price - stop) <= 0:
                entry_counts["invalid_stop_rejected"] += 1
                entry_event(timestamp, row, side, reason, cross_time,
                            "fill", "invalid_stop_rejected", "rejected", {"initial_stop": stop})
                return
        before = cash
        qty_cap = before * config.notional_fraction / (fill * (1 + config.fee))
        stop_fill = stop * (1 - side * config.slip)
        unit_risk = side * (fill - stop_fill) + config.fee * (fill + stop_fill)
        if config.risk_fraction is None:
            qty = qty_cap
        else:
            if not np.isfinite(unit_risk) or unit_risk <= 0:
                entry_counts["invalid_unit_risk_rejected"] += 1
                entry_event(timestamp, row, side, reason, cross_time,
                            "sizing", "invalid_unit_risk_rejected", "rejected",
                            {"entry_price": fill, "initial_stop": stop,
                             "initial_stop_fill": stop_fill, "initial_stop_unit_risk": unit_risk})
                return
            qty = min(before * config.risk_fraction / unit_risk, qty_cap)
        planned_risk = qty * unit_risk
        if fixed_episode is not None:
            if (timestamp != pd.Timestamp(fixed_episode["entry_time"])
                    or side != int(fixed_episode["side"])):
                raise ValueError("Fixed episode must start at its original eligible V3 crossing")
            qty = float(fixed_episode["qty"])
            planned_risk = qty * unit_risk
        entry_details = {
            "attempt_before_equity": before, "entry_price": fill, "initial_stop": stop,
            "initial_stop_fill": stop_fill, "initial_stop_unit_risk": unit_risk,
            "qty_cap": qty_cap, "qty": qty, "initial_planned_risk": planned_risk,
            "initial_planned_risk_pct": planned_risk / before * 100,
            "initial_stop_price_nonpositive": stop <= 0,
        }
        fee = qty * fill * config.fee
        cash -= fee
        trade_id += 1
        entry_counts["entry_fills"] += 1
        entry_event(timestamp, row, side, reason, cross_time,
                    "fill", "filled", "filled", entry_details)
        position = {"trade_id": trade_id, "side": side, "qty": qty, "entry_time": timestamp,
                    **route_details,
                    "entry_price": fill, "entry_reference": price, "entry_fee": fee, "entry_equity": before,
                    "entry_reason": reason, "signal_day": row.timestamp, "cross_day": cross_time,
                    "entry_wait_days_used": int((row.timestamp - cross_time).days) if reason == "delayed_cross" else 0,
                    "stop": stop, "funding_paid": 0.0, "carry_paid": 0.0,
                    "entry_slope": float(row.slope), "entry_rsi": float(row.rsi),
                    "entry_ma30": float(row.ma30), "entry_prev_ma30": float(row.prev_ma30),
                    "entry_filter": config.trend_filter, "direction_mode": config.direction_mode,
                    "risk_fraction": config.risk_fraction, "notional_fraction": config.notional_fraction,
                    "initial_stop_fill": stop_fill, "initial_stop_unit_risk": unit_risk,
                    "qty_cap": qty_cap, "initial_planned_risk": planned_risk,
                    "initial_planned_risk_pct": planned_risk / before * 100,
                    "initial_stop_price_nonpositive": stop <= 0,
                    "qualification": entry_qualification(row, side, config),
                    "entry_ma_step": float(row.ma_step), "entry_prev_ma_step": float(row.prev_ma_step),
                    "entry_atr": float(row.atr), "initial_stop_mult": 1.5,
                    "stop_mult": 1.5, "armed": False, "tightening_days": 0,
                    "stop_floor_reached": False,
                    "initialized": False, "extreme_price": None, "extreme_day": None,
                    "progress_source": config.progress_source,
                    "no_new_extreme_days": 0, "arm_day": None, "anchor_decisive_days": 0,
                    "progress_policy": config.progress_policy,
                    "first_arm_day": None, "ever_armed": False, "arm_count": 0, "reset_count": 0,
                    "anchor_candidate": None,
                    "uncapped_initial_stop": uncapped_stop, "initial_stop": stop,
                    "cap_applied": stop != uncapped_stop,
                    "initial_stop_risk_price": side * (fill - stop),
                    "initial_stop_risk_pct": side * (fill - stop) / fill * 100}
        if config.short_exit == "accel1_rsi30_protect":
            position.update(tp_protect_active=False, tp_protect_signal_day=None,
                            tp_protect_event_atr=None, tp_protect_extreme_low=None,
                            tp_protect_candidate=None, tp_protect_trigger_rsi=None,
                            tp_protect_trigger_close=None, tp_protect_eligible_signal_count=0,
                            tp_protect_suppressed_count=0)
        stops.append({"timestamp": timestamp, "trade_id": trade_id, "side": side,
                      **route_details,
                      "old_stop": stop, "new_stop": stop, "signal_day": row.timestamp,
                      "old_mult": 1.5, "new_mult": 1.5, "old_armed": False, "new_armed": False,
                      "natural_candidate": uncapped_stop, "stalled": False, "profit_eligible": False,
                      "expected_profit_at_close": None, "favorable_move_atr": None,
                      "tightening_trigger": "entry", "tightened": False,
                      "initialized": False, "extreme_price": None, "extreme_day": None,
                      "progress_source": config.progress_source,
                      "no_new_extreme_days": 0, "arm_day": None,
                      "progress_policy": config.progress_policy, "armed_reset": False,
                      "first_arm_day": None, "ever_armed": False, "arm_count": 0, "reset_count": 0,
                      "full_holding_day": False, "new_extreme": False,
                      "anchor_candidate": None, "anchor_decisive": False,
                      "uncapped_initial_stop": uncapped_stop, "initial_stop": stop,
                      "cap_applied": stop != uncapped_stop,
                      "initial_stop_risk_price": side * (fill - stop),
                      "initial_stop_risk_pct": side * (fill - stop) / fill * 100,
                      **short_protect_snapshot(position)})
        mark(timestamp, price, "entry")

    def reverse_intent(j, p):
        if not config.reverse or j < 0:
            return None
        row = daily_rows[j]
        side = -p["side"]
        # A bar that closes exactly at entry was known before entry, so exclude it.
        history = d.iloc[max(0, j - 4):j + 1]
        history = history[(history.timestamp + pd.Timedelta(days=1) > p["entry_time"]) & (history.cross != 0)]
        if history.empty or int(history.iloc[-1].cross) != side:
            return None
        if entry_qualification(row, side, config) is None or side * (row.close - row.ma) <= 0:
            return None
        return {"side": side, "cross_time": history.iloc[-1].timestamp}

    def close_profit_snapshot(row):
        """Use closed-day price and costs carried into the next day's boundary."""
        p = position
        fill = float(row.close) * (1 - p["side"] * config.slip)
        expected_profit = (p["side"] * p["qty"] * (fill - p["entry_price"])
                           - p["entry_fee"] - p["qty"] * fill * config.fee
                           - p["funding_paid"] - p["carry_paid"])
        favorable_move = p["side"] * (float(row.close) - p["entry_price"])
        eligible = (expected_profit > 0
                    and favorable_move >= config.profit_trigger_atr * p["entry_atr"])
        return {"expected_profit_at_close": expected_profit,
                "favorable_move_atr": favorable_move / p["entry_atr"],
                "profit_eligible": bool(eligible)}

    def update_stop(timestamp, row, profit_snapshot):
        p = position
        policy = p["exit_route"] if config.admission_routing else config.exit_state_policy
        side, old_stop, old_mult, old_armed = p["side"], p["stop"], p["stop_mult"], p["armed"]
        natural = float(row.ma - side * old_mult * row.atr)
        stalled = side * (natural - old_stop) <= 1e-12 * max(1.0, abs(old_stop))
        eligible = profit_snapshot["profit_eligible"]
        trigger = "fixed"
        should_tighten = False
        full_holding_day = bool(row.timestamp >= p["entry_time"])
        new_extreme = False
        armed_reset = False
        if config.progress_days > 0:
            # The daily bar must be wholly held; an entry at 01:00 cannot use
            # that day's high/low, which may have occurred before the fill.
            # Close progress keeps this same full-day convention for comparison.
            if not full_holding_day:
                trigger = "partial_entry_day"
            elif not p["initialized"]:
                p["initialized"] = True
                p["extreme_price"] = float(row.close if config.progress_source == "close"
                                           else row.high if side == 1 else row.low)
                p["extreme_day"] = row.timestamp
                p["no_new_extreme_days"] = 0
                new_extreme = True
                trigger = "extreme_initialize"
            else:
                observed_extreme = float(row.close if config.progress_source == "close"
                                         else row.high if side == 1 else row.low)
                new_extreme = side * (observed_extreme - p["extreme_price"]) > 0
                if new_extreme:
                    p["extreme_price"] = observed_extreme
                    p["extreme_day"] = row.timestamp
                    p["no_new_extreme_days"] = 0
                    if config.progress_policy == "reset_on_new_extreme":
                        armed_reset = bool(p["armed"])
                        p["armed"] = False
                        p["arm_day"] = None
                        p["reset_count"] += int(armed_reset)
                else:
                    p["no_new_extreme_days"] += 1
                if not p["armed"] and p["no_new_extreme_days"] >= config.progress_days:
                    p["armed"] = True
                    p["arm_day"] = row.timestamp
                if old_mult <= 0.5:
                    trigger = "at_floor"
                elif p["armed"]:
                    trigger = "progress_armed_daily" if old_armed else "no_new_extreme"
                    should_tighten = True
                else:
                    trigger = "progress_reset" if armed_reset else "progress_observed"
        elif config.tighten_mode != "fixed":
            if old_mult <= 0.5:
                trigger = "at_floor"
            elif config.tighten_mode == "armed_daily" and old_armed:
                trigger, should_tighten = "armed_daily", True
            elif eligible and stalled:
                trigger, should_tighten = "stall_profit", True
                if config.tighten_mode == "armed_daily":
                    p["armed"] = True
            elif not eligible:
                trigger = "not_profitable"
            else:
                trigger = "not_stalled"
        if p["armed"] and not old_armed:
            p["arm_count"] += 1
            p["ever_armed"] = True
            if p["first_arm_day"] is None:
                p["first_arm_day"] = row.timestamp
        state_snapshot = {}
        if (policy != "v3" or config.ma30_mode != "none") and full_holding_day:
            state_snapshot = (ma30_exit_state_step(p, row, config.ma30_mode, eligible)
                              if config.ma30_mode != "none" else exit_state_step(p, row, policy))
            if state_snapshot["sm_protect"] or state_snapshot["sm_defense"]:
                should_tighten = old_mult > .5
                trigger = "state_protect" if state_snapshot["sm_protect"] else "state_defense"
            elif (policy in {"trend", "extension"} or config.ma30_mode in {"extend", "both"}) and state_snapshot["sm_healthy"]:
                should_tighten = False
                trigger = "healthy_pause"
        if should_tighten:
            p["stop_mult"] = max(0.5, round(old_mult - 0.2, 10))
            p["tightening_days"] += 1
            if p["stop_mult"] == 0.5:
                p["stop_floor_reached"] = True
        # Keep R1's original arithmetic and max/min ordering for fixed mode.
        proposed = float(row.ma - side * p["stop_mult"] * row.atr)
        p["stop"] = max(old_stop, proposed) if side == 1 else min(old_stop, proposed)
        anchor_candidate, anchor_decisive = None, False
        if config.stop_anchor == "extreme" and p["armed"] and p["initialized"]:
            anchor_candidate = float(p["extreme_price"] - side * p["stop_mult"] * row.atr)
            anchor_decisive = side * (anchor_candidate - p["stop"]) > 0
            if anchor_decisive:
                p["stop"] = anchor_candidate
                p["anchor_decisive_days"] += 1
        p["anchor_candidate"] = anchor_candidate
        for key in ("sm_defensive_stop", "sm_protection_stop"):
            candidate = state_snapshot.get(key)
            if candidate is not None:
                p["stop"] = (max if side == 1 else min)(p["stop"], candidate)
        protect_snapshot = short_protect_step(p, row, full_holding_day)
        if p.get("tp_protect_active", False):
            # Normal V3 progress/multiplier updates above remain in force.
            p["stop"] = min(p["stop"], p["tp_protect_candidate"])
        stops.append({"timestamp": timestamp, "trade_id": p["trade_id"], "side": side,
                      **position_routing_details(p),
                      "old_stop": old_stop, "new_stop": p["stop"], "signal_day": row.timestamp,
                      "old_mult": old_mult, "new_mult": p["stop_mult"],
                      "old_armed": old_armed, "new_armed": p["armed"],
                      "natural_candidate": natural, "stalled": bool(stalled),
                      **profit_snapshot, "tightening_trigger": trigger,
                      "tightened": should_tighten,
                      "initialized": p["initialized"], "extreme_price": p["extreme_price"],
                      "progress_source": config.progress_source,
                      "extreme_day": p["extreme_day"],
                      "no_new_extreme_days": p["no_new_extreme_days"], "arm_day": p["arm_day"],
                      "progress_policy": config.progress_policy, "armed_reset": armed_reset,
                      "first_arm_day": p["first_arm_day"], "ever_armed": p["ever_armed"],
                      "arm_count": p["arm_count"], "reset_count": p["reset_count"],
                      "full_holding_day": full_holding_day, "new_extreme": bool(new_extreme),
                      "anchor_candidate": anchor_candidate, "anchor_decisive": bool(anchor_decisive),
                      "uncapped_initial_stop": p["uncapped_initial_stop"],
                      "initial_stop": p["initial_stop"], "cap_applied": p["cap_applied"],
                      "initial_stop_risk_price": p["initial_stop_risk_price"],
                      "initial_stop_risk_pct": p["initial_stop_risk_pct"],
                      **state_snapshot, **protect_snapshot})

    def charge_event(event, price, timestamp):
        nonlocal cash
        if position is None:
            return
        official_mark = event.get("mark_price", np.nan)
        proxy = not (official_mark is not None and np.isfinite(float(official_mark)) and float(official_mark) > 0)
        used = price if proxy else float(official_mark)
        cost = position["side"] * position["qty"] * used * float(event["funding_rate"])
        cash -= cost
        position["funding_paid"] += cost
        funding_log.append({"timestamp": event["timestamp"], "trade_id": position["trade_id"], "rate": event["funding_rate"], "mark_price_used": used, "mark_proxy": proxy, "cost": cost, "accounted_at_hour": timestamp})

    for bar, j in zip(h.itertuples(index=False), signal_indices):
        t = bar.timestamp
        row = daily_rows[j]
        if position is not None:
            if pending_entry is not None:
                candidate_event(t, row, pending_entry, "position_held", "cancelled")
            pending_entry = None
        # Freeze the closed-day profitability decision before boundary funding.
        profit_snapshot = close_profit_snapshot(row) if t.hour == 0 and position is not None else None
        # Events precisely at an hour belong to the position carried into that hour.
        while fidx < len(fund) and fund[fidx]["timestamp"] <= t:
            charge_event(fund[fidx], bar.open, t)
            fidx += 1
        mark(t, bar.open, "open")
        if t.hour == 0:
            if position is not None:
                update_stop(t, row, profit_snapshot)
            pending_day = {"at": t + pd.Timedelta(hours=config.delay_hours), "j": j}

        # A gap through an existing stop always takes precedence at the open.
        stopped_this_hour = False
        if position is not None and position["side"] * (bar.open - position["stop"]) <= 0:
            intent = reverse_intent(j, position)
            close_position(t, bar.open, "stop_gap")
            pending_reverse = None if intent is None else {**intent, "at": t + pd.Timedelta(hours=1)}
            stopped_this_hour = True
            pending_day = None

        if not stopped_this_hour and pending_reverse is not None and pending_reverse["at"] <= t:
            intent = pending_reverse
            pending_reverse = None
            # Recheck the latest fully closed day if the hour crossed midnight.
            if (position is None and entry_qualification(row, intent["side"], config) is not None
                    and intent["side"] * (row.close - row.ma) > 0):
                open_position(t, bar.open, intent["side"], j, "stop_reversal", intent["cross_time"])
            pending_day = None

        if not stopped_this_hour and pending_day is not None and pending_day["at"] <= t:
            signal = daily_rows[pending_day["j"]]
            signal_j = pending_day["j"]
            pending_day = None
            # Gap stops above have priority. This closed-bar exit precedes RSI
            # and consumes the signal without reopening or requesting reversal.
            if (position is not None and config.exit_opposite_cross
                    and int(signal.cross) == -position["side"]):
                position["opposite_cross_signal_day"] = signal.timestamp
                close_position(t, bar.open, "opposite_cross")
                stopped_this_hour = True
                pending_reverse = None
            short_exit = (position["route_short_exit"] if config.admission_routing
                          and position is not None else config.short_exit)
            if position is not None and position["side"] == -1 and short_exit != "none":
                expected_fill = signal.close * (1 + config.slip)
                expected_profit = position["qty"] * (position["entry_price"] - expected_fill) - position["entry_fee"] - position["qty"] * expected_fill * config.fee - position["funding_paid"] - position["carry_paid"]
                accelerated = (short_exit == "rsi30" or
                               (short_exit in {"accel1_rsi30", "accel1_rsi30_protect"} and signal.accel1) or
                               (short_exit == "accel2_rsi30" and signal.accel2))
                if signal.rsi <= 30 and expected_profit > 0 and accelerated:
                    if short_exit == "accel1_rsi30_protect":
                        # update_stop activated the completed-day protection
                        # before checking the open. This count records only
                        # legacy TP calls actually reached after gap priority.
                        if not position.get("tp_protect_active", False):
                            raise ValueError("Short TP protection needs a wholly held signal day")
                        position["tp_protect_suppressed_count"] += 1
                        stops[-1]["tp_protect_suppressed_count"] = position["tp_protect_suppressed_count"]
                        stops[-1]["tp_protect_actually_suppressed"] = True
                    elif config.ma30_mode != "none" and position.get("m30_suppress_short_tp", False):
                        position["m30_short_tp_suppressed_count"] = position.get("m30_short_tp_suppressed_count", 0) + 1
                        stops[-1]["m30_short_tp_actually_suppressed"] = True
                    else:
                        position["tp_signal_day"] = signal.timestamp
                        position["tp_signal_rsi"] = float(signal.rsi)
                        close_position(t, bar.open, short_exit)
                        stopped_this_hour = True  # Prevent using the same daily cross to reopen.
            if position is None and not stopped_this_hour:
                if not signal.ready:
                    if pending_entry is not None:
                        candidate_event(t, signal, pending_entry, "not_ready", "cancelled")
                    pending_entry = None
                    if int(signal.cross):
                        entry_counts["flat_not_ready_crosses"] += 1
                        entry_event(t, signal, int(signal.cross), "daily_cross", signal.timestamp,
                                    "ready", "not_ready", "rejected")
                else:
                    side = int(signal.cross)
                    if side:
                        entry_counts["flat_ready_crosses"] += 1
                        # Every fresh cross supersedes an older intent. Only
                        # a flat, ready cross rejected for slope can wait.
                        if pending_entry is not None:
                            candidate_event(t, signal, pending_entry, "fresh_cross_supersedes", "cancelled")
                        pending_entry = None
                        if entry_qualification(signal, side, config) is not None:
                            open_position(t, bar.open, side, signal_j, "daily_cross", signal.timestamp)
                        elif ((config.entry_wait_days > 0 or config.entry_wait_policy == "until_invalid")
                              and np.isfinite(signal.slope)
                              and side * (signal.close - signal.ma) > 0):
                            entry_counts["slope_rejected"] += 1
                            entry_counts["wait_candidates_created"] += 1
                            entry_event(t, signal, side, "daily_cross", signal.timestamp,
                                        "slope", "slope_rejected", "waiting")
                            pending_entry = {"side": side, "cross_j": signal_j,
                                             "cross_time": signal.timestamp,
                                             "cross_close": float(signal.close)}
                            candidate_event(t, signal, pending_entry, "created", "pending")
                        else:
                            entry_counts["slope_rejected"] += 1
                            entry_event(t, signal, side, "daily_cross", signal.timestamp,
                                        "slope", "slope_rejected", "rejected")
                    elif pending_entry is not None:
                        intent = pending_entry
                        wait_days = signal_j - intent["cross_j"]
                        intended_side = intent["side"]
                        if ((config.entry_wait_policy == "bounded" and wait_days > config.entry_wait_days)
                                or intended_side * (signal.close - signal.ma) <= 0):
                            candidate_event(t, signal, intent, "ma_side_invalid", "cancelled")
                            pending_entry = None
                        elif (wait_days > 0
                              and intended_side * signal.slope > config.slope
                              and intended_side * (signal.close - intent["cross_close"]) > 0):
                            # Consume before attempting the next-open fill;
                            # invalid initial stop/gap must never retry it.
                            candidate_event(t, signal, intent, "confirmed", "confirmed")
                            pending_entry = None
                            open_position(t, bar.open, intended_side, signal_j,
                                          "delayed_cross", intent["cross_time"])
                        else:
                            candidate_event(t, signal, intent, "conditions_pending", "pending")

        if fixed_episode is not None and trades:
            end = pd.Timestamp(trades[-1]["exit_interval_end"])
            break
        # Native millisecond events inside the stop hour are charged to its opening
        # position before stop detection: explicit scheduling estimate, not a bound.
        while fidx < len(fund) and fund[fidx]["timestamp"] < t + pd.Timedelta(hours=1):
            charge_event(fund[fidx], bar.open, t)
            fidx += 1
        if position is not None:
            exposure_hours += 1
            if carry_daily:
                paid = position["qty"] * bar.open * carry_daily / 24
                cash -= paid
                position["carry_paid"] += paid
            side, stop = position["side"], position["stop"]
            hit = (bar.low <= stop) if side == 1 else (bar.high >= stop)
            adverse = max(bar.low, stop) if side == 1 else min(bar.high, stop)
            # Includes estimated liquidation transaction cost at the adverse price.
            adverse_equity = equity(adverse) - position["qty"] * adverse * (config.fee + config.slip)
            adverse_mdd = min(adverse_mdd, adverse_equity / peak - 1)
            if hit:
                intent = reverse_intent(j, position)
                close_position(t, stop, "stop_intrahour", t + pd.Timedelta(hours=1))
                pending_reverse = None if intent is None else {**intent, "at": t + pd.Timedelta(hours=1)}
                pending_day = None
        mark(t + pd.Timedelta(hours=1), bar.close, "hour_close")
        if fixed_episode is not None and trades:
            end = pd.Timestamp(trades[-1]["exit_interval_end"])
            break
    if pending_entry is not None:
        candidate_event(end, daily_rows[int(signal_indices[-1])], pending_entry,
                        "sample_end_unresolved", "unresolved")
    while fidx < len(fund) and fund[fidx]["timestamp"] <= end:
        charge_event(fund[fidx], float(h.iloc[-1].close), end)
        fidx += 1
    if position is not None:
        close_position(end, float(h.iloc[-1].close), "sample_end")
    curve = pd.DataFrame(marks)
    tr = pd.DataFrame(trades)
    eq = curve.equity.to_numpy()
    mdd = float(np.min(eq / np.maximum.accumulate(np.r_[initial_equity, eq])[1:] - 1))
    trade_pnl = tr.net_pnl if len(tr) else pd.Series(dtype=float)
    wins, losses = trade_pnl[trade_pnl > 0].sum(), -trade_pnl[trade_pnl < 0].sum()
    gain = cash / initial_equity - 1
    days = (end - start).total_seconds() / 86400
    summary = {"name": config.name, **asdict(config), "start": str(start), "end_exclusive": str(end),
               "return_pct": gain * 100, "ending_equity": cash, "max_drawdown_pct": mdd * 100,
               "adverse_hour_check_pct": min(adverse_mdd, mdd) * 100,
               "annualized_return_pct": (None if fixed_episode is not None else
                   ((cash / initial_equity) ** (365 / days) - 1) * 100 if cash > 0 else -100),
               "trades": len(tr), "win_rate_pct": float((trade_pnl > 0).mean() * 100) if len(tr) else 0,
               "profit_factor": float(wins / losses) if losses else None,
               "exposure_pct": exposure_hours / (days * 24 if fixed_episode is not None else len(h)) * 100,
               "fee_total": float(tr.entry_fee.sum() + tr.exit_fee.sum()) if len(tr) else 0,
               "funding_paid": float(tr.funding_paid.sum()) if len(tr) else 0,
               "carry_paid": float(tr.carry_paid.sum()) if len(tr) else 0,
               "reversal_entries": int((tr.entry_reason == "stop_reversal").sum()) if len(tr) else 0,
               "short_tp_exits": int(tr.exit_reason.isin(["rsi30", "accel1_rsi30", "accel2_rsi30"]).sum()) if len(tr) else 0,
               "price_only_diagnostic": funding is None, "funding_window_verified": False,
               "funding_price_proxy_events": sum(x["mark_proxy"] for x in funding_log),
               "funding_events_charged": len(funding_log), "bankrupt": cash <= 0}
    for qualification in ("original", "opposite_slowdown", "absolute_slowdown", "no_slope"):
        summary["qualification_" + qualification + "_entries"] = (
            int((tr.qualification == qualification).sum()) if len(tr) else 0)
    summary["delayed_entries"] = int((tr.entry_reason == "delayed_cross").sum()) if len(tr) else 0
    summary["tightened_trades"] = int((tr.tightening_days > 0).sum()) if len(tr) else 0
    summary["tightening_days"] = int(tr.tightening_days.sum()) if len(tr) else 0
    summary["floor_trades"] = int(tr.stop_floor_reached.sum()) if len(tr) else 0
    summary["armed_trades"] = int(tr.armed.sum()) if len(tr) else 0
    summary["opposite_cross_exits"] = int((tr.exit_reason == "opposite_cross").sum()) if len(tr) else 0
    summary["extreme_anchor_decisive_days"] = int(tr.anchor_decisive_days.sum()) if len(tr) else 0
    summary["extreme_anchor_trades"] = int((tr.anchor_decisive_days > 0).sum()) if len(tr) else 0
    summary["progress_armed_trades"] = int(tr.arm_day.notna().sum()) if len(tr) else 0
    summary["initial_cap_trades"] = int(tr.cap_applied.sum()) if len(tr) else 0
    summary["ever_armed_trades"] = int(tr.ever_armed.sum()) if len(tr) else 0
    summary["arm_count"] = int(tr.arm_count.sum()) if len(tr) else 0
    summary["reset_count"] = int(tr.reset_count.sum()) if len(tr) else 0
    summary["initial_stop_nonpositive_trades"] = int(tr.initial_stop_price_nonpositive.sum()) if len(tr) else 0
    summary.update(entry_counts)
    if config.short_exit == "accel1_rsi30_protect":
        summary["short_protection_activated_trades"] = int(tr.tp_protect_active.sum()) if len(tr) else 0
        summary["short_protection_eligible_signals"] = int(tr.tp_protect_eligible_signal_count.sum()) if len(tr) else 0
        summary["short_protection_suppressed_tp_calls"] = int(tr.tp_protect_suppressed_count.sum()) if len(tr) else 0
    for side, label in [(1, "long"), (-1, "short")]:
        subset = tr[tr.side == side] if len(tr) else tr
        summary[label + "_trades"] = len(subset)
        summary[label + "_pnl"] = float(subset.net_pnl.sum()) if len(subset) else 0
        summary[label + "_wins"] = int((subset.net_pnl > 0).sum()) if len(subset) else 0
    assert math.isclose(initial_equity + float(tr.net_pnl.sum() if len(tr) else 0), cash, abs_tol=1e-7), "Account reconciliation failed"
    for item in stops:
        assert item["side"] * (item["new_stop"] - item["old_stop"]) >= -1e-12, "Stop widened"
        assert 0.5 <= item["new_mult"] <= item["old_mult"] <= 1.5, "ATR multiple widened or crossed floor"
    assert summary["tightening_days"] == sum(item["tightened"] for item in stops), "Tightening log mismatch"
    assert summary["extreme_anchor_decisive_days"] == sum(item["anchor_decisive"] for item in stops), "Extreme anchor log mismatch"
    return summary, tr, curve, pd.DataFrame(stops), pd.DataFrame(funding_log)
