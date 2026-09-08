"""P1资金约束的价格贡献诊断；不计未知funding，不发布永续净绩效。"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/p1-20260907"
STEP = pd.Timedelta(hours=4)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dump(p, obj):
    p.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        + "\n"
    )


def build_matrix(frame):
    f = frame.copy()
    symbols = sorted(f.symbol.unique())
    dates = pd.date_range(f.ts.min(), f.ts.max(), freq="4h", tz="UTC")
    ss = pd.Index(symbols).get_indexer(f.symbol)
    tt = dates.get_indexer(f.ts)
    shape = (len(dates), len(symbols))
    cols = ["open", "low", "close", "stop_band", "rsi14", "daily_mom30"]
    m = {c: np.full(shape, np.nan) for c in cols}
    for c in cols:
        m[c][tt, ss] = f[c].to_numpy(dtype=float)
    for c in ["eligible", "feature_valid", "admission", "atr_down"]:
        m[c] = np.zeros(shape, dtype=bool)
        m[c][tt, ss] = f[c].fillna(False).to_numpy(dtype=bool)
    m["segment"] = np.full(shape, -1, dtype=np.int32)
    ids, _ = pd.factorize(f.research_segment_id)
    m["segment"][tt, ss] = ids
    m["dates"] = dates
    m["symbols"] = symbols
    return m


def requests_at_close(variant, eligible, rsi, atr_down, held, used, armed):
    """All arguments describe the now-completed bar; no future availability filter."""
    recovered = np.isfinite(rsi) & (rsi > 30)
    used[recovered] = False
    flat = ~held
    if variant == "direct":
        return np.flatnonzero(eligible & flat)
    if variant == "rsi14_reclaim":
        candidates = eligible & flat & recovered & armed
        armed[recovered] = False
        armed[eligible & flat & (rsi <= 30)] = True
        return np.flatnonzero(candidates)
    candidates = eligible & flat & (rsi <= 30) & ~used
    if variant == "rsi14_atr_pullback":
        candidates &= atr_down
    return np.flatnonzero(candidates)


def simulate(m, variant, bps, initial=100000.0):
    dates = m["dates"]
    symbols = m["symbols"]
    ns = len(symbols)
    fee = 0.001
    slip = bps / 10000
    cash = initial
    positions = {}
    used = np.zeros(ns, dtype=bool)
    armed = np.zeros(ns, dtype=bool)
    pending = np.array([], dtype=int)
    trades = []
    marks = []
    counters = {
        k: 0
        for k in [
            "requests",
            "filled",
            "held_skip",
            "invalid_entry_stop",
            "missing_next_bar",
            "max_positions",
            "risk_or_cash",
            "intrabar_exits",
            "open_exits",
        ]
    }
    invalid = None
    begin = pd.Timestamp("2020-01-01T00:00:00Z")
    last_i = None

    def close_position(s, i, raw_price, reason, at_open):
        nonlocal cash
        p = positions.pop(s)
        fill = raw_price * (1 - slip)
        proceeds = p["qty"] * fill * (1 - fee)
        cash += proceeds
        p.update(
            status="closed",
            reason=reason,
            exit_bar_open=dates[i],
            exit_time_upper_bound=dates[i] if at_open else dates[i] + STEP,
            exit_raw=float(raw_price),
            exit_fill=float(fill),
            proceeds=float(proceeds),
            pnl_ex_funding=float(proceeds - p["spent"]),
            return_ex_funding=float(
                (proceeds - p["spent"]) / (p["qty"] * p["entry_fill"])
            ),
        )
        trades.append(p)

    for i, t in enumerate(dates):
        if t < begin:
            continue
        last_i = i
        op = m["open"][i]
        close = m["close"][i]
        seg = m["segment"][i]
        continuous = (
            (i > 0) & m["eligible"][i] & (seg >= 0) & (seg == m["segment"][i - 1])
        )
        # A live holding cannot be wished away before its last observed bar.
        broken = [s for s in positions if not continuous[s] or not np.isfinite(op[s])]
        if broken:
            invalid = {
                "time": str(t),
                "symbols": [symbols[s] for s in broken],
                "reason": "HOLDING_PRICE_OR_IDENTITY_GAP",
            }
            break
        reset = ~continuous
        used[reset] = False
        armed[reset] = False
        for s in list(positions):
            p = positions[s]
            if p["pending_exit"]:
                close_position(s, i, op[s], "new_stop_marketable_next_open", True)
                counters["open_exits"] += 1
            elif op[s] <= p["stop"]:
                close_position(s, i, op[s], "gap_through_stop", True)
                counters["open_exits"] += 1
        # All pending orders came from the preceding close. Intrabar exits happen later.
        for s in sorted(
            pending, key=lambda s: (-m["daily_mom30"][i - 1, s], symbols[s])
        ):
            if s in positions:
                counters["held_skip"] += 1
                continue
            if not continuous[s] or not np.isfinite(op[s]):
                counters["missing_next_bar"] += 1
                continue
            band = m["stop_band"][i - 1, s]
            if (
                not np.isfinite(band)
                or band <= 0
                or band >= op[s]
                or band >= m["close"][i - 1, s]
            ):
                counters["invalid_entry_stop"] += 1
                continue
            if len(positions) >= 5:
                counters["max_positions"] += 1
                continue
            equity = cash + sum(p["qty"] * op[k] for k, p in positions.items())
            risk = sum(
                p["qty"] * max(0, op[k] - p["stop"] * (1 - slip) * (1 - fee))
                for k, p in positions.items()
            )
            fill = op[s] * (1 + slip)
            loss_per_unit = fill * (1 + fee) - band * (1 - slip) * (1 - fee)
            budget = min(0.005 * equity, 0.02 * equity - risk)
            qty = min(
                budget / loss_per_unit, 0.2 * equity / fill, cash / (fill * (1 + fee))
            )
            if budget <= 0 or not np.isfinite(qty) or qty <= 0 or equity <= 0:
                counters["risk_or_cash"] += 1
                continue
            spent = qty * fill * (1 + fee)
            cash -= spent
            if cash < -1e-7:
                raise AssertionError("Negative cash")
            positions[s] = {
                "variant": variant,
                "slippage_bps": bps,
                "symbol": symbols[s],
                "signal_bar_open": dates[i - 1],
                "entry_time": t,
                "entry_year": t.year,
                "entry_raw": float(op[s]),
                "entry_fill": float(fill),
                "qty": float(qty),
                "spent": float(spent),
                "initial_stop": float(band),
                "stop": float(band),
                "pending_exit": False,
                "initial_budget_equity": float(equity),
                "entry_risk": float(qty * loss_per_unit),
                "risk_before": float(risk),
                "notional": float(qty * fill),
                "cash_after_entry": float(cash),
            }
            counters["filled"] += 1
            if variant != "direct":
                used[s] = True
        for s in list(positions):
            p = positions[s]
            if m["low"][i, s] <= p["stop"]:
                close_position(s, i, p["stop"], "intrabar_stop", False)
                counters["intrabar_exits"] += 1
            else:
                band = m["stop_band"][i, s]
                if not np.isfinite(band):
                    raise AssertionError("Undefined stop while holding")
                p["stop"] = float(max(p["stop"], band))
                p["pending_exit"] = p["stop"] >= close[s]
        equity = cash + sum(p["qty"] * close[s] for s, p in positions.items())
        liquidation = cash + sum(
            p["qty"] * close[s] * (1 - slip) * (1 - fee) for s, p in positions.items()
        )
        exposure = sum(p["qty"] * close[s] for s, p in positions.items())
        marks.append(
            {
                "bar_close": t + STEP,
                "budget_mark_value_ex_funding": equity,
                "hypothetical_liquidation_value_ex_funding": liquidation,
                "cash_ex_funding": cash,
                "position_count": len(positions),
                "exposure_fraction": exposure / equity if equity > 0 else np.nan,
            }
        )
        held = np.zeros(ns, dtype=bool)
        held[list(positions)] = True
        admission = m["admission"][i] & m["eligible"][i]
        pending = requests_at_close(
            variant, admission, m["rsi14"][i], m["atr_down"][i], held, used, armed
        )
        counters["requests"] += len(pending)
    for s, p in positions.items():
        if invalid:
            p.update(status="censored", reason="path_stopped_for_holding_gap")
        else:
            mark = m["close"][last_i, s]
            liquidation = p["qty"] * mark * (1 - slip) * (1 - fee)
            p.update(
                status="censored",
                reason="right_censor_cutoff",
                mark_time=dates[last_i] + STEP,
                mark_raw=float(mark),
                mark_gross_return=float(mark / p["entry_raw"] - 1),
                mark_pnl_ex_funding=float(liquidation - p["spent"]),
            )
        trades.append(p)
    for t in trades:
        t.pop("pending_exit", None)
        t.pop("stop", None)
    tx = pd.DataFrame(trades)
    hist = pd.DataFrame(marks)
    closed = tx[tx.status.eq("closed")] if len(tx) else tx
    gain = closed.pnl_ex_funding if len(closed) else pd.Series(dtype=float)
    summary = {
        "variant": variant,
        "slippage_bps": bps,
        "path_valid": invalid is None,
        "invalid": invalid,
        "closed": len(closed),
        "open_or_censored": len(tx) - len(closed),
        "traded_symbols": int(tx.symbol.nunique()) if len(tx) else 0,
        "mean_trade_return_ex_funding_pct": float(closed.return_ex_funding.mean() * 100)
        if len(closed)
        else None,
        "median_trade_return_ex_funding_pct": float(
            closed.return_ex_funding.median() * 100
        )
        if len(closed)
        else None,
        "trade_win_pct": float((gain > 0).mean() * 100) if len(gain) else None,
        "realized_price_pnl_ex_funding": float(gain.sum()),
        "price_contribution_pct_initial_budget": float(
            (hist.hypothetical_liquidation_value_ex_funding.iloc[-1] / initial - 1)
            * 100
        )
        if len(hist) and invalid is None
        else None,
        "mean_exposure_pct": float(hist.exposure_fraction.mean() * 100)
        if len(hist)
        else None,
        "max_positions_seen": int(hist.position_count.max()) if len(hist) else 0,
        "counters": counters,
        "not_net_performance": True,
    }
    return tx, hist, summary


def main():
    manifest = json.loads((OUT / "input-manifest.json").read_text())
    for name, h in manifest["artifacts"].items():
        if sha(OUT / name) != h:
            raise ValueError("P1 input artifact changed")
    for name, h in manifest["prefit"].items():
        if sha(FAMILY / name) != h:
            raise ValueError("P1 config changed")
    frame = pd.read_parquet(OUT / "four-hour-features.parquet")
    matrix = build_matrix(frame)
    del frame
    config = json.loads((FAMILY / "specs/p1-config.json").read_text())
    records = []
    summaries = []
    for bps in [4, 8]:
        for variant in config["entry_variants"]:
            tx, hist, summary = simulate(matrix, variant, bps)
            tx.to_parquet(OUT / f"p1-trades-{variant}-{bps}bp.parquet", index=False)
            hist.to_parquet(
                OUT / f"p1-budget-path-{variant}-{bps}bp.parquet", index=False
            )
            records.append(tx)
            summaries.append(summary)
            print(
                variant,
                bps,
                "closed",
                summary["closed"],
                "valid",
                summary["path_valid"],
                "price contribution",
                summary["price_contribution_pct_initial_budget"],
                flush=True,
            )
    trades = pd.concat(records, ignore_index=True)
    trades.to_csv(OUT / "p1-entry-trades.csv", index=False)
    dump(OUT / "p1-entry-summary.json", summaries)
    pd.DataFrame(
        [
            {k: v for k, v in s.items() if k not in ["invalid", "counters"]}
            for s in summaries
        ]
    ).to_csv(OUT / "p1-entry-summary.csv", index=False)
    cut = matrix["dates"][-1] + STEP
    recent = []
    for label, days in [
        ("1d", 1),
        ("7d", 7),
        ("1m", 30),
        ("3m", 90),
        ("6m", 180),
        ("1y", 365),
    ]:
        for (variant, bps), g in trades[
            trades.entry_time.ge(cut - pd.Timedelta(days=days))
        ].groupby(["variant", "slippage_bps"]):
            v = g[g.status.eq("closed")]
            recent.append(
                {
                    "window": label,
                    "variant": variant,
                    "slippage_bps": bps,
                    "entries": len(g),
                    "closed": len(v),
                    "censored": len(g) - len(v),
                    "mean_ex_funding_pct": v.return_ex_funding.mean() * 100,
                    "closed_pnl_ex_funding": v.pnl_ex_funding.sum(),
                }
            )
    pd.DataFrame(recent).to_csv(OUT / "p1-recent-entry-cohorts.csv", index=False)
    closed = trades[trades.status.eq("closed")]
    for keys, name in [
        (["variant", "slippage_bps", "entry_year"], "year"),
        (["variant", "slippage_bps", "symbol"], "symbol"),
    ]:
        closed.groupby(keys).agg(
            trades=("symbol", "size"),
            mean_return=("return_ex_funding", "mean"),
            pnl_ex_funding=("pnl_ex_funding", "sum"),
        ).reset_index().to_csv(OUT / f"p1-entry-by-{name}.csv", index=False)
    (OUT / "provenance/replay_p1_entries.py.txt").write_bytes(
        Path(__file__).read_bytes()
    )


if __name__ == "__main__":
    main()
