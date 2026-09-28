"""固定30日Top10：两种规则、完整持仓审计和条件性价格预算。"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/p0-20260907"
STEP = pd.Timedelta(hours=4)
HOLD = pd.Timedelta(days=30)
FEE = 0.001


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dump(p, obj):
    p.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        + "\n"
    )


def load_inputs():
    manifest = json.loads((OUT / "input-manifest.json").read_text())
    for n, h in manifest["artifacts"].items():
        assert sha(OUT / n) == h, n
    for n, h in manifest["prefit"].items():
        assert sha(FAMILY / n) == h, n
    return (
        pd.read_parquet(OUT / "daily-features.parquet"),
        pd.read_parquet(OUT / "market-states.parquet"),
        pd.read_parquet(OUT / "four-hour-prices.parquet"),
    )


def matrix(f):
    symbols = sorted(f.symbol.unique())
    dates = pd.date_range(f.ts.min(), f.ts.max(), freq="4h", tz="UTC")
    ss, tt = pd.Index(symbols).get_indexer(f.symbol), dates.get_indexer(f.ts)
    assert not f.duplicated(["symbol", "ts"]).any()
    shape = (len(dates), len(symbols))
    m = {c: np.full(shape, np.nan) for c in ["open", "high", "low", "close"]}
    for c in m:
        m[c][tt, ss] = f[c].to_numpy(dtype=float)
    m["eligible"] = np.zeros(shape, dtype=bool)
    m["eligible"][tt, ss] = f.eligible.fillna(False).to_numpy(bool)
    m["segment"] = np.full(shape, -1, dtype=np.int32)
    ids, _ = pd.factorize(f.research_segment_id)
    m["segment"][tt, ss] = ids
    m.update(symbols=symbols, dates=dates)
    return m


def can_enter(m, i, s):
    return (
        i > 0
        and m["eligible"][i, s]
        and m["segment"][i, s] >= 0
        and m["segment"][i, s] == m["segment"][i - 1, s]
        and np.isfinite(m["open"][i, s])
        and m["open"][i, s] > 0
    )


def plan(d, market, m, variant):
    """Calendar decisions use only completed daily history and today's executable open."""
    market = market.set_index("signal_time")
    groups = {
        t: g.sort_values(["momentum_rank", "symbol"])
        for t, g in d[d.pool & d.momentum_rank.le(10)].groupby("signal_time")
    }
    lookup = {s: i for i, s in enumerate(m["symbols"])}
    active, due = False, None
    actions, decisions = {}, []
    for i, t in enumerate(m["dates"]):
        if t.hour != 4 or t < pd.Timestamp("2020-01-01T00:00:00Z"):
            continue
        signal = t.floor("D")
        if active and t < due:
            continue
        if variant == "always_top10" and due is not None and t < due:
            continue
        state = market.loc[signal] if signal in market.index else None
        known = state is not None and bool(state.state_valid)
        allowed = known and (variant == "always_top10" or bool(state.bull))
        if (
            not allowed
            and not active
            and not (variant == "always_top10" and due is not None)
        ):
            continue
        candidates = groups.get(signal, pd.DataFrame()) if allowed else pd.DataFrame()
        selected = [lookup[s] for s in candidates.symbol] if len(candidates) else []
        filled = [s for s in selected if can_enter(m, i, s)]
        actions[i] = filled
        decisions.append(
            {
                "variant": variant,
                "signal_time": signal,
                "execution_time": t,
                "bull": bool(state.bull) if known else None,
                "state_known": known,
                "selected": [m["symbols"][s] for s in selected],
                "filled": [m["symbols"][s] for s in filled],
                "cancelled": [m["symbols"][s] for s in selected if s not in filled],
                "action": "buy_or_rotate" if filled else "exit_to_cash",
            }
        )
        active = bool(filled)
        due = t + HOLD if active or variant == "always_top10" else None
    return actions, decisions


def leg_factor(entry, exit_, bps):
    slip = bps / 10000
    return exit_ / entry * (1 - slip) / (1 + slip) * (1 - FEE) / (1 + FEE)


def rounds(m, actions, variant, bps):
    """Independent round labels retain gaps; they never repair the account path."""
    rows, legs = [], []
    for i, selected in actions.items():
        if not selected:
            continue
        j = i + 180
        complete = j < len(m["dates"])
        valid = complete
        factors = []
        for s in selected:
            path = slice(i, min(j + 1, len(m["dates"])))
            ok = (
                complete
                and m["eligible"][path, s].all()
                and np.all(m["segment"][path, s] == m["segment"][i, s])
            )
            valid &= ok
            factor = leg_factor(m["open"][i, s], m["open"][j, s], bps) if ok else np.nan
            factors.append(factor)
            legs.append(
                {
                    "variant": variant,
                    "bps": bps,
                    "entry_time": m["dates"][i],
                    "symbol": m["symbols"][s],
                    "valid": bool(ok),
                    "return_ex_funding": factor - 1,
                    "mae": float(m["low"][i:j, s].min() / m["open"][i, s] - 1)
                    if ok
                    else np.nan,
                }
            )
        rows.append(
            {
                "variant": variant,
                "bps": bps,
                "entry_time": m["dates"][i],
                "scheduled_exit": m["dates"][i] + HOLD,
                "filled": len(selected),
                "valid": bool(valid),
                "status": "complete"
                if valid
                else ("holding_gap" if complete else "right_censor"),
                "return_ex_funding": float(sum((x - 1) * 0.1 for x in factors))
                if valid
                else np.nan,
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(legs)


def simulate(m, actions, variant, bps, initial=100000.0):
    cash, positions = initial, {}
    tx, hist, cycles = [], [], []
    invalid = None
    cycle = None
    begin = min(actions) if actions else len(m["dates"])
    slip = bps / 10000
    for i in range(begin, len(m["dates"])):
        t = m["dates"][i]
        bad = [s for s in positions if not can_enter(m, i, s)]
        if bad:
            invalid = {
                "time": str(t),
                "symbols": [m["symbols"][s] for s in bad],
                "reason": "HELD_PRICE_OR_IDENTITY_GAP",
            }
            break
        if i in actions:
            for s, p in list(positions.items()):
                exit_fill = m["open"][i, s] * (1 - slip)
                proceeds = p["qty"] * exit_fill * (1 - FEE)
                cash += proceeds
                tx.append(
                    {
                        **p,
                        "exit_time": t,
                        "exit_raw": m["open"][i, s],
                        "exit_fill": exit_fill,
                        "pnl_ex_funding": proceeds - p["spent"],
                        "return_ex_funding": proceeds / p["spent"] - 1,
                        "status": "closed",
                    }
                )
            positions = {}
            if cycle is not None:
                cycles.append(
                    {
                        **cycle,
                        "exit_time": t,
                        "budget_end": cash,
                        "return_ex_funding": cash / cycle["budget_start"] - 1,
                    }
                )
                cycle = None
            selected = actions[i]
            budget = cash
            if selected:
                cycle = {
                    "variant": variant,
                    "bps": bps,
                    "entry_time": t,
                    "budget_start": budget,
                    "positions": len(selected),
                }
            for s in selected:
                assert can_enter(m, i, s)
                fill = m["open"][i, s] * (1 + slip)
                spent = budget * 0.1
                qty = spent / ((1 + FEE) * fill)
                cash -= spent
                positions[s] = {
                    "variant": variant,
                    "bps": bps,
                    "symbol": m["symbols"][s],
                    "entry_time": t,
                    "entry_raw": m["open"][i, s],
                    "entry_fill": fill,
                    "qty": qty,
                    "spent": spent,
                    "budget_start": budget,
                    "signal_time": t - STEP,
                }
            assert cash >= -1e-6
        marked = cash + sum(
            p["qty"] * m["close"][i, s] * (1 - slip) * (1 - FEE)
            for s, p in positions.items()
        )
        nominal = sum(p["qty"] * m["close"][i, s] for s, p in positions.items())
        hist.append(
            {
                "time": t + STEP,
                "budget_mark_ex_funding": marked,
                "cash": cash,
                "positions": len(positions),
                "exposure": nominal / (cash + nominal)
                if cash + nominal > 0
                else np.nan,
            }
        )
    for s, p in positions.items():
        mark = m["close"][i - 1 if invalid else i, s]
        mark_time = m["dates"][i] if invalid else m["dates"][i] + STEP
        tx.append(
            {
                **p,
                "status": "censored",
                "mark_time": mark_time,
                "mark_raw": mark,
                "mark_pnl_ex_funding": p["qty"] * mark * (1 - slip) * (1 - FEE)
                - p["spent"],
                "reason": "path_invalid" if invalid else "right_censor",
            }
        )
    h = pd.DataFrame(hist)
    trades = pd.DataFrame(tx)
    closed = trades[trades.status.eq("closed")] if len(trades) else trades
    if len(h):
        wealth = np.r_[initial, h.budget_mark_ex_funding.to_numpy()]
        peak = np.maximum.accumulate(wealth)
        dd = wealth / peak - 1
        trough = int(np.argmin(dd))
        peak_i = int(np.argmax(wealth[: trough + 1]))
        recovery = np.flatnonzero(wealth[trough + 1 :] >= wealth[peak_i])
        ts = [m["dates"][begin], *h.time.tolist()]
        drawdown = {
            "mdd_pct": float(dd.min() * 100),
            "peak": str(ts[peak_i]),
            "trough": str(ts[trough]),
            "recovery": str(ts[trough + 1 + recovery[0]]) if len(recovery) else None,
        }
        recon = (
            initial
            + (closed.pnl_ex_funding.sum() if len(closed) else 0)
            + (
                trades.loc[trades.status.eq("censored"), "mark_pnl_ex_funding"].sum()
                if "mark_pnl_ex_funding" in trades
                else 0
            )
        )
        assert np.isclose(recon, h.budget_mark_ex_funding.iloc[-1], rtol=0, atol=1e-5)
    else:
        drawdown = None
    result = {
        "variant": variant,
        "bps": bps,
        "path_valid": invalid is None,
        "invalid": invalid,
        "start": str(m["dates"][begin]) if len(actions) else None,
        "observed_end": str(h.time.iloc[-1]) if len(h) else None,
        "closed_trades": len(closed),
        "open_trades": len(trades) - len(closed),
        "closed_rounds": len(cycles),
        "full_price_contribution_pct": float(
            (h.budget_mark_ex_funding.iloc[-1] / initial - 1) * 100
        )
        if len(h) and invalid is None
        else None,
        "valid_prefix_price_contribution_pct": float(
            (h.budget_mark_ex_funding.iloc[-1] / initial - 1) * 100
        )
        if len(h)
        else None,
        "drawdown": drawdown,
        "mean_exposure_pct": float(h.exposure.mean() * 100) if len(h) else None,
        "scope": "conditional price budget ex funding; no perpetual net NAV",
    }
    return result, h, trades, pd.DataFrame(cycles)


def summaries(paths):
    yearly, recent = [], []
    for variant, bps, h in paths:
        if h.empty:
            continue
        prior = 100000.0
        for y, g in h.groupby(h.time.dt.year):
            end = float(g.budget_mark_ex_funding.iloc[-1])
            yearly.append(
                {
                    "variant": variant,
                    "bps": bps,
                    "year": int(y),
                    "price_budget_change_pct": (end / prior - 1) * 100,
                    "mean_exposure_pct": g.exposure.mean() * 100,
                    "last_mark": g.time.iloc[-1],
                }
            )
            prior = end
        cutoff = pd.Timestamp("2026-09-05T12:00:00Z")
        for label, delta in [
            ("1d", pd.Timedelta(days=1)),
            ("7d", pd.Timedelta(days=7)),
            ("1m", pd.DateOffset(months=1)),
            ("3m", pd.DateOffset(months=3)),
            ("6m", pd.DateOffset(months=6)),
            ("1y", pd.DateOffset(years=1)),
        ]:
            a = cutoff - delta
            before = h[h.time.le(a)]
            within = h[h.time.gt(a) & h.time.le(cutoff)]
            complete = bool(len(before) and len(within) and h.time.iloc[-1] == cutoff)
            recent.append(
                {
                    "variant": variant,
                    "bps": bps,
                    "slice": label,
                    "complete": complete,
                    "cutoff": cutoff,
                    "price_budget_change_pct": (
                        within.budget_mark_ex_funding.iloc[-1]
                        / before.budget_mark_ex_funding.iloc[-1]
                        - 1
                    )
                    * 100
                    if complete
                    else np.nan,
                }
            )
    pd.DataFrame(yearly).to_csv(OUT / "yearly.csv", index=False)
    pd.DataFrame(recent).to_csv(OUT / "recent.csv", index=False)


def main():
    d, market, f = load_inputs()
    m = matrix(f)
    results, paths, allrounds, alllegs, decisions = [], [], [], [], []
    for variant in ["bull_top10", "always_top10"]:
        actions, dec = plan(d, market, m, variant)
        decisions.extend(dec)
        for bps in [4, 8]:
            result, h, tx, cycles = simulate(m, actions, variant, bps)
            round_rows, leg_rows = rounds(m, actions, variant, bps)
            allrounds.append(round_rows)
            alllegs.append(leg_rows)
            results.append(result)
            paths.append((variant, bps, h))
            h.to_parquet(OUT / f"budget-path-{variant}-{bps}bp.parquet", index=False)
            tx.to_parquet(OUT / f"trades-{variant}-{bps}bp.parquet", index=False)
            cycles.to_csv(OUT / f"cycles-{variant}-{bps}bp.csv", index=False)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    dump(OUT / "summary.json", results)
    dump(OUT / "decisions.json", decisions)
    pd.concat(allrounds, ignore_index=True).to_csv(
        OUT / "round-labels.csv", index=False
    )
    pd.concat(alllegs, ignore_index=True).to_parquet(
        OUT / "leg-labels.parquet", index=False
    )
    summaries(paths)
    (OUT / "provenance/replay_p0.py.txt").write_bytes(Path(__file__).read_bytes())
    dump(
        OUT / "result-manifest.json",
        {
            "source_sha256": sha(Path(__file__)),
            "artifacts": {
                str(p.relative_to(OUT)): sha(p)
                for p in OUT.rglob("*")
                if p.is_file() and p.name != "result-manifest.json"
            },
        },
    )


if __name__ == "__main__":
    main()
