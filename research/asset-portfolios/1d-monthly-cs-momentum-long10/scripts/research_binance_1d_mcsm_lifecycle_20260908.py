#!/usr/bin/env python3
"""固定月度篮子的日级状态诊断；不输出资金净值或账户绩效。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
SPEC = FAMILY / "specs/binance-1d-mcsm-lifecycle-funding-round-20260908.md"
INPUT_DIR = FAMILY / "artifacts/lifecycle-inputs-20260908"
START = pd.Timestamp("2020-08-01", tz="UTC")
LAST = pd.Timestamp("2026-06-01", tz="UTC")
COST = 0.0014
EXCLUDED = {
    "USDC", "BUSD", "TUSD", "USDP", "FDUSD", "DAI", "SUSD", "EUR", "AEUR",
    "GBP", "AUD", "BRL", "USD1", "USDE", "XUSD", "BFUSD", "BLUEBIRD", "DOTECO", "FOOTBALL",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path: Path, value) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False) + "\n")


def finite(value):
    return float(value) if pd.notna(value) and np.isfinite(value) else None


def after_cost(value):
    """独立月全开全平的价格扣成交成本，不是资金净收益。"""
    return value - 1.0 - COST * (1.0 + value)


def state_name(breadth: float, leader: float) -> str:
    if not np.isfinite(breadth) or not np.isfinite(leader):
        return "unavailable"
    return ("market_strong" if breadth > 0.5 else "market_weak") + "__" + (
        "leader_strong" if leader > 0 else "leader_weak")


def make_panels(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    f = frame.copy()
    f["ts"] = pd.to_datetime(f.ts, utc=True)
    # 数据治理读取范围更长，研究明确不使用 July 2 之后的行情。
    f = f.loc[f.ts.le(pd.Timestamp("2026-07-02", tz="UTC"))].copy()
    if f.duplicated(["ts", "symbol"]).any():
        raise ValueError("duplicate input keys")
    if not f.research_window_valid.equals(f.eligible):
        raise ValueError("backward=1, forward=0 input mask mismatch")
    f["adv30"] = f.groupby("research_segment_id").quote_volume.transform(
        lambda s: s.rolling(30, min_periods=30).mean())
    # 无效行不删除后拼接；保留网格并让窗口失效。
    for key in ("open", "close", "adv30"):
        f[key] = f[key].where(f.eligible)
    grid = pd.date_range(f.ts.min(), f.ts.max(), freq="D")
    return {key: f.pivot(index="ts", columns="symbol", values=key).reindex(grid)
            for key in ("open", "close", "adv30", "research_segment_id")}


def select_month(p: dict, month: pd.Timestamp) -> pd.DataFrame:
    end = month - pd.Timedelta(days=1)
    start = month - pd.DateOffset(months=1) - pd.Timedelta(days=1)
    close, seg = p["close"], p["research_segment_id"]
    same = seg.loc[start].notna() & seg.loc[start].eq(seg.loc[end])
    signal = (close.loc[end] / close.loc[start] - 1).where(same)
    adv = p["adv30"].loc[end]
    excluded = pd.Series([s.split("/")[0] in EXCLUDED for s in signal.index], index=signal.index)
    pool = pd.DataFrame({"signal": signal, "adv30": adv}).loc[
        signal.notna() & adv.ge(10_000_000) & ~excluded].reset_index()
    return pool.sort_values(["signal", "adv30", "symbol"], ascending=[False, False, True]).reset_index(drop=True)


def basket_paths(p: dict, symbols: list[str], signal_end, entry, end) -> dict:
    days = pd.date_range(signal_end, end, freq="D")
    empty = pd.Series(np.nan, index=days)
    if not symbols:
        return {"open": empty, "close": empty, "prices": pd.DataFrame(index=days), "q": None, "bad": ["empty"]}
    segments = p["research_segment_id"].reindex(index=days, columns=symbols)
    same = segments.eq(p["research_segment_id"].loc[signal_end, symbols], axis=1)
    opens = p["open"].reindex(index=days, columns=symbols).where(same)
    closes = p["close"].reindex(index=days, columns=symbols).where(same)
    bad = opens.loc[entry].index[opens.loc[entry].isna()].tolist()
    if bad:
        return {"open": empty, "close": empty, "prices": closes, "q": None, "bad": bad}
    q = 1.0 / len(symbols) / opens.loc[entry]
    return {"open": opens.mul(q).sum(axis=1, min_count=len(symbols)),
            "close": closes.mul(q).sum(axis=1, min_count=len(symbols)),
            "prices": closes, "q": q, "bad": []}


def path_return(path: pd.Series, start, end) -> float:
    window = path.loc[start:end]
    expected = (end - start).days + 1
    if len(window) != expected or window.isna().any() or not window.gt(0).all():
        return float("nan")
    return float(window.iloc[-1] / window.iloc[0] - 1)


def known_state(top: dict, market: dict, decision) -> tuple[float, float, float, float]:
    stop = decision - pd.Timedelta(days=1)
    start = stop - pd.Timedelta(days=7)
    rtop = path_return(top["close"], start, stop)
    rmarket = path_return(market["close"], start, stop)
    prices = market["prices"].loc[start:stop]
    if len(prices) != 8 or prices.empty or prices.isna().any().any():
        breadth = float("nan")
    else:
        breadth = float((prices.iloc[-1] / prices.iloc[0] - 1).gt(0).mean())
    return breadth, rtop - rmarket, rtop, rmarket


def calculate(p: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    monthly, daily, landmarks, holdings, blockers = [], [], [], [], []
    for month in pd.date_range(START, LAST, freq="MS"):
        pool = select_month(p, month)
        top_symbols = pool.symbol.iloc[:10].tolist()
        market_symbols = pool.symbol.tolist()
        entry = month + pd.Timedelta(days=1)
        end = month + pd.offsets.MonthBegin(1) + pd.Timedelta(days=1)
        signal_end = month - pd.Timedelta(days=1)
        row = {"month": month, "entry": entry, "exit": end, "market_count": len(pool),
               "symbols": "|".join(top_symbols), "top_entry_valid": False, "baseline_valid": False,
               "market_baseline_valid": False, "first_trigger": None, "trigger_exit": None,
               "baseline_gross": np.nan, "baseline_price_cost": np.nan, "market_gross": np.nan,
               "candidate_price_cost": np.nan, "delta_price_cost": np.nan,
               "market_delta_price_cost": np.nan, "delta_excess_price_cost": np.nan,
               "trigger_prior_peak": np.nan, "trigger_known_pnl": np.nan,
               "giveback_before_signal": np.nan, "established_before_trigger": None,
               "trigger_to_fill_return": np.nan, "avoided_loss": 0., "missed_upside": 0.,
               "unknown_state_days": 0, "first_day_price_opportunity": np.nan}
        if len(top_symbols) < 10:
            blockers.append({"month": month, "role": "selection", "reason": "fewer_than_10"})
            monthly.append(row)
            continue
        top = basket_paths(p, top_symbols, signal_end, entry, end)
        market = basket_paths(p, market_symbols, signal_end, entry, end)
        row["top_entry_valid"] = top["q"] is not None
        first_open = p["open"].loc[month, top_symbols]
        next_open = p["open"].loc[entry, top_symbols]
        if first_open.notna().all() and next_open.notna().all():
            row["first_day_price_opportunity"] = float((next_open / first_open - 1).mean())
        for rank, item in pool.iterrows():
            holdings.append({"month": month, "symbol": item.symbol, "rank": rank + 1,
                             "is_top10": rank < 10, "signal": item.signal, "adv30": item.adv30,
                             "entry": entry, "entry_price_observed": p["open"].loc[entry, item.symbol],
                             "q_top": top["q"].get(item.symbol, np.nan) if top["q"] is not None else np.nan})
        for role, basket in (("top10", top), ("market", market)):
            missing = basket["open"].loc[entry:end].isna()
            if missing.any():
                bad_day = missing.index[missing][0]
                syms = top_symbols if role == "top10" else market_symbols
                seg = p["research_segment_id"]
                bad_names = [s for s in syms if pd.isna(p["open"].at[bad_day, s])
                             or pd.isna(seg.at[bad_day, s])
                             or seg.at[bad_day, s] != seg.at[signal_end, s]]
                blockers.append({"month": month, "role": role, "reason": "entry_or_held_path_gap",
                                 "first_bad_day": bad_day, "symbols": "|".join(bad_names or basket["bad"])})
        base_ret = path_return(top["open"], entry, end)
        market_ret = path_return(market["open"], entry, end)
        row.update(baseline_gross=base_ret, baseline_valid=bool(np.isfinite(base_ret)),
                   baseline_price_cost=after_cost(1 + base_ret), market_gross=market_ret,
                   market_baseline_valid=bool(np.isfinite(market_ret)))
        first_event = None
        for decision in pd.date_range(entry + pd.Timedelta(days=7), end - pd.Timedelta(days=2), freq="D"):
            breadth, excess, rt, rm = known_state(top, market, decision)
            state = state_name(breadth, excess)
            fill = decision + pd.Timedelta(days=1)
            age = (decision - entry).days
            prior = top["close"].loc[entry:decision - pd.Timedelta(days=1)]
            prior_peak = max(0., float(prior.max() - 1)) if not prior.empty and prior.notna().all() else np.nan
            known_pnl = float(prior.iloc[-1] - 1) if not prior.empty and pd.notna(prior.iloc[-1]) else np.nan
            event = {"month": month, "decision": decision, "fill": fill, "age_days": age,
                     "breadth7": breadth, "leader7_excess": excess, "top7": rt, "market7": rm,
                     "state": state, "known_pnl": known_pnl, "prior_peak_pnl": prior_peak}
            daily.append(event)
            row["unknown_state_days"] += state == "unavailable"
            if first_event is None and state == "market_weak__leader_weak":
                first_event = event
            if age in (7, 14, 21):
                future_end = fill + pd.Timedelta(days=7)
                lr = {**event, "label_end": future_end, "within_holding_month": future_end <= end,
                      "future_top7": np.nan, "future_market7": np.nan, "future_excess7": np.nan}
                if future_end <= end:
                    lr["future_top7"] = path_return(top["open"], fill, future_end)
                    lr["future_market7"] = path_return(market["open"], fill, future_end)
                    lr["future_excess7"] = lr["future_top7"] - lr["future_market7"]
                lr["valid"] = bool(state != "unavailable" and np.isfinite(lr["future_excess7"]))
                landmarks.append(lr)
        if first_event is None:
            # Unknown state does not mean weak and never fabricates a sell signal.
            row["candidate_price_cost"] = row["baseline_price_cost"]
            row["market_delta_price_cost"] = 0. if np.isfinite(market_ret) else np.nan
        else:
            fill = first_event["fill"]
            stop_ret = path_return(top["open"], entry, fill)
            market_stop_ret = path_return(market["open"], entry, fill)
            row["market_delta_price_cost"] = after_cost(1 + market_stop_ret) - after_cost(1 + market_ret)
            row.update(first_trigger=first_event["decision"], trigger_exit=fill,
                       candidate_price_cost=after_cost(1 + stop_ret),
                       trigger_prior_peak=first_event["prior_peak_pnl"],
                       trigger_known_pnl=first_event["known_pnl"],
                       established_before_trigger=first_event["prior_peak_pnl"] > 0,
                       giveback_before_signal=first_event["prior_peak_pnl"] - first_event["known_pnl"])
            known_value = first_event["known_pnl"] + 1
            if np.isfinite(stop_ret) and np.isfinite(known_value):
                row["trigger_to_fill_return"] = (1 + stop_ret) / known_value - 1
        row["delta_price_cost"] = row["candidate_price_cost"] - row["baseline_price_cost"]
        row["delta_excess_price_cost"] = row["delta_price_cost"] - row["market_delta_price_cost"]
        if first_event is not None and np.isfinite(row["delta_price_cost"]):
            row["avoided_loss"] = max(row["delta_price_cost"], 0)
            row["missed_upside"] = max(-row["delta_price_cost"], 0)
        monthly.append(row)
    return tuple(pd.DataFrame(x) for x in (monthly, daily, landmarks, holdings, blockers))


def block_ci(series: pd.Series, draws: int = 2000) -> dict:
    """完整日历轴上 3 个月 circular blocks；缺失保留，不冒充独立日。"""
    calendar = pd.date_range(START, LAST, freq="MS")
    values = series.reindex(calendar).to_numpy(dtype=float)
    rng = np.random.default_rng(20260908)
    samples = []
    for _ in range(draws):
        starts = rng.integers(0, len(values), size=int(np.ceil(len(values) / 3)))
        indices = np.concatenate([(s + np.arange(3)) % len(values) for s in starts])[:len(values)]
        observed = values[indices]
        if np.isfinite(observed).any():
            samples.append(float(np.nanmean(observed)))
    return {"mean": finite(np.nanmean(values)) if np.isfinite(values).any() else None,
            "p05": finite(np.quantile(samples, .05)) if samples else None,
            "p95": finite(np.quantile(samples, .95)) if samples else None,
            "months": int(np.isfinite(values).sum()), "draws": draws, "block_months": 3}


def summarize(monthly, landmarks) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    states = []
    valid = landmarks.loc[landmarks.valid].copy()
    for state, group in valid.groupby("state"):
        row = {"state": state, "observations": len(group), "months": group.month.nunique(),
               "mean_absolute": group.future_top7.mean(), "median_absolute": group.future_top7.median(),
               "mean_excess": group.future_excess7.mean(), "median_excess": group.future_excess7.median(),
               "absolute_win_rate": group.future_top7.gt(0).mean(), "excess_win_rate": group.future_excess7.gt(0).mean()}
        for col, label in (("future_top7", "absolute"), ("future_excess7", "excess")):
            ci = block_ci(group.groupby("month")[col].mean())
            row.update({f"month_weighted_{label}_{key}": value for key, value in ci.items()})
        states.append(row)
    pairs = monthly.loc[monthly.baseline_valid & monthly.candidate_price_cost.notna()].copy()
    triggered = pairs.loc[pairs.first_trigger.notna()]
    beta_pairs = pairs.loc[pairs.delta_excess_price_cost.notna()]
    base, candidate = pairs.baseline_price_cost, pairs.candidate_price_cost
    tail = pairs.nlargest(max(1, int(np.ceil(len(pairs) * .1))), "baseline_price_cost")
    tail_sum = tail.baseline_price_cost.clip(lower=0).sum()
    pos_sum = base.clip(lower=0).sum()
    yearly = []
    for year, group in pairs.groupby(pairs.month.dt.year):
        yearly.append({"year": year, "months": len(group), "triggers": int(group.first_trigger.notna().sum()),
                       "baseline_mean": group.baseline_price_cost.mean(),
                       "candidate_mean": group.candidate_price_cost.mean(),
                       "delta_mean": group.delta_price_cost.mean(),
                       "leave_year_out_delta_mean": pairs.loc[pairs.month.dt.year.ne(year), "delta_price_cost"].mean()})
    best = pairs.baseline_price_cost.idxmax() if len(pairs) else None
    largest_improvement = pairs.delta_price_cost.idxmax() if len(pairs) else None
    phase = {}
    for label, g in triggered.groupby("established_before_trigger"):
        phase["previously_profitable" if label else "never_profitable"] = {
            "months": len(g), "delta_mean": finite(g.delta_price_cost.mean()),
            "avoided_loss_sum": finite(g.avoided_loss.sum()), "missed_upside_sum": finite(g.missed_upside.sum()),
            "mean_known_pnl": finite(g.trigger_known_pnl.mean()),
            "mean_prior_peak": finite(g.trigger_prior_peak.mean()),
            "mean_giveback_already_happened": finite(g.giveback_before_signal.mean())}
    summary = {
        "status": "PRICE_MECHANISM_DIAGNOSTIC_NOT_NET_PERFORMANCE",
        "months_requested": len(monthly), "baseline_price_complete_months": int(monthly.baseline_valid.sum()),
        "market_price_complete_months": int(monthly.market_baseline_valid.sum()),
        "paired_months": len(pairs), "triggered_paired_months": len(triggered),
        "landmarks_total": len(landmarks), "landmarks_valid": len(valid),
        "baseline_mean_price_cost": finite(base.mean()), "candidate_mean_price_cost": finite(candidate.mean()),
        "paired_delta_ci": block_ci(pairs.set_index("month").delta_price_cost),
        "triggered_delta_ci": block_ci(triggered.set_index("month").delta_price_cost),
        "market_control_paired_months": len(beta_pairs),
        "market_control_triggered_months": int(beta_pairs.first_trigger.notna().sum()),
        "excess_delta_ci": block_ci(beta_pairs.set_index("month").delta_excess_price_cost),
        "market_delta_ci": block_ci(beta_pairs.set_index("month").market_delta_price_cost),
        "avoided_loss_sum": finite(triggered.avoided_loss.sum()),
        "missed_upside_sum": finite(triggered.missed_upside.sum()),
        "positive_month_pnl_retention": finite(candidate.loc[base.gt(0)].clip(lower=0).sum() / pos_sum) if pos_sum else None,
        "all_positive_pnl_ratio": finite(candidate.clip(lower=0).sum() / pos_sum) if pos_sum else None,
        "right_tail_months": [d.isoformat() for d in tail.month],
        "right_tail_price_pnl_retention": finite(tail.candidate_price_cost.clip(lower=0).sum() / tail_sum) if tail_sum else None,
        "drop_best_baseline_month_delta_mean": finite(pairs.drop(index=best).delta_price_cost.mean()) if best is not None else None,
        "drop_largest_improvement_month_delta_mean": finite(pairs.drop(index=largest_improvement).delta_price_cost.mean()) if largest_improvement is not None else None,
        "best_baseline_month": str(pairs.loc[best, "month"]) if best is not None else None,
        "largest_improvement_month": str(pairs.loc[largest_improvement, "month"]) if largest_improvement is not None else None,
        "entry_first_day_mean_price_opportunity": finite(monthly.first_day_price_opportunity.mean()),
        "entry_first_day_median_price_opportunity": finite(monthly.first_day_price_opportunity.median()),
        "phase_groups": phase,
        "funding_window_verified": False, "net_performance_valid": False,
        "pit_universe_proven": False, "tradability_proven": False, "strategy_approved": False,
        "oos_status": "REUSED_HISTORY_DIAGNOSTIC", "account_equity_compounded": False,
    }
    return summary, pd.DataFrame(states), pd.DataFrame(yearly)


def self_test() -> None:
    assert state_name(.5, 0) == "market_weak__leader_weak"
    assert state_name(float("nan"), 1) == "unavailable"
    dates = pd.date_range("2025-01-01", periods=4, tz="UTC")
    assert np.isclose(path_return(pd.Series([1, 2, 3, 4], index=dates), dates[0], dates[-1]), 3)
    assert np.isnan(path_return(pd.Series([1, np.nan, 3, 4], index=dates), dates[0], dates[-1]))
    assert np.isclose(after_cost(2), 1 - 3 * COST)
    # 1/2 资金各买一币，价格分化后不把权重调回 1/2。
    units = np.array([.5, .5]) / np.array([10., 10.])
    prices = np.array([[10., 10.], [20., 5.], [40., 2.5]])
    nav = prices @ units
    fixed_weight = np.prod(1 + (prices[1:] / prices[:-1] - 1).mean(axis=1))
    assert np.isclose(nav[-1], 2.125) and np.isclose(fixed_weight, 1.5625)
    print("SELF_TEST_PASS", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--run-id", default="lifecycle-diagnostic-20260908")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if Path(args.run_id).name != args.run_id or args.run_id in (".", ".."):
        raise ValueError("run-id must be one safe basename")
    out = FAMILY / "artifacts" / args.run_id
    if out.exists():
        raise FileExistsError(out)
    input_summary = json.loads((INPUT_DIR / "summary.json").read_text())
    frame_path = INPUT_DIR / "daily-returned-frames.parquet"
    expected = input_summary["parquet_sha256"]
    if sha(frame_path) != expected:
        raise ValueError("returned frame content changed")
    if (input_summary["status"] != "PRICE_DIAGNOSTIC_INPUTS_VERIFIED"
            or not input_summary["all_requested_symbols_passed"]
            or input_summary["returned_symbols"] != 874
            or input_summary["rejected_symbols"]):
        raise ValueError("input audit contains unresolved startup failures")
    if sha(ROOT / input_summary["request_path"]) != input_summary["request_sha256"]:
        raise ValueError("frozen request changed")
    for relative, digest in input_summary["source_sha256"].items():
        if sha(ROOT / relative) != digest:
            raise ValueError(f"input producer/source changed: {relative}")
    for receipt in input_summary["startup_receipts"]:
        if receipt["status"] != "PRICE_DIAGNOSTIC_INPUTS_VERIFIED":
            raise ValueError("failed startup receipt")
        for role in ("request", "report"):
            if sha(INPUT_DIR / receipt[f"{role}_path"]) != receipt[f"{role}_sha256"]:
                raise ValueError(f"changed startup {role}")
    out.mkdir(parents=True)
    started = {"started_utc": datetime.now(timezone.utc).isoformat(), "script_sha256": sha(Path(__file__)),
               "contract_sha256": sha(SPEC), "input_frame_sha256": expected,
               "input_summary_sha256": sha(INPUT_DIR / "summary.json")}
    save_json(out / "started.json", started)
    frame = pd.read_parquet(frame_path)
    panels = make_panels(frame)
    monthly, daily, landmarks, holdings, blockers = calculate(panels)
    summary, states, yearly = summarize(monthly, landmarks)
    for name, result in (("monthly", monthly), ("daily-states", daily), ("landmarks", landmarks),
                         ("holdings", holdings), ("blockers", blockers), ("state-summary", states), ("yearly", yearly)):
        result.to_csv(out / f"{name}.csv", index=False)
    summary.update(started, finished_utc=datetime.now(timezone.utc).isoformat(),
                   script_unchanged=sha(Path(__file__)) == started["script_sha256"],
                   contract_unchanged=sha(SPEC) == started["contract_sha256"],
                   evidence_sha256={f.name: sha(f) for f in sorted(out.glob("*.csv"))})
    save_json(out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
