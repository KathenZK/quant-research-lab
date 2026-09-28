"""P1：独立检验市场状态和强势筛选的前瞻价格分布。"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/p1-20260907"
DAY = pd.Timedelta(days=1)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dump(p, obj):
    p.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        + "\n"
    )


def cost(r, bps=4):
    z = (1 + r) * (1 - bps / 10000) / (1 + bps / 10000)
    return z - 1 - 0.001 * (1 + z)


def load_verified_inputs():
    m = json.loads((OUT / "input-manifest.json").read_text())
    for name, h in m["artifacts"].items():
        if sha(OUT / name) != h:
            raise ValueError(f"Changed P1 input: {name}")
    for name, h in m["prefit"].items():
        if sha(FAMILY / name) != h:
            raise ValueError(f"Changed frozen P1 contract: {name}")
    return pd.read_parquet(OUT / "daily-features.parquet")


def label_frame(g, h, cutoff):
    g = g.reset_index(drop=True)
    seg = g.research_segment_id.fillna("")
    nxt = g.ts.shift(-1)
    target = g.ts.shift(-h - 1)
    valid = (
        seg.ne("")
        & seg.eq(seg.shift(-h - 1))
        & (nxt - g.ts).eq(DAY)
        & (target - g.ts).eq(DAY * (h + 1))
    )
    en = g.open.shift(-1)
    ex = g.open.shift(-h - 1)
    ret = (ex / en - 1).where(valid)
    result = g[
        [
            "symbol",
            "available_at",
            "pool",
            "strong",
            "state",
            "bull",
            "state_valid",
            "mom30",
            "strong_last5_count",
        ]
    ].copy()
    result["horizon_days"] = h
    result["valid"] = valid
    result["reason"] = np.select(
        [valid, (g.available_at + DAY * (h + 1)) > cutoff],
        ["complete", "right_censor_cutoff"],
        default="gap_or_identity_or_symbol_end",
    )
    result["gross_return"] = ret
    result["cost4_ex_funding"] = cost(ret, 4)
    result["cost8_ex_funding"] = cost(ret, 8)
    result["mae"] = (g.low.rolling(h).min().shift(-h) / en - 1).where(valid)
    result["mfe"] = (g.high.rolling(h).max().shift(-h) / en - 1).where(valid)
    result["entry_year"] = result.available_at.dt.year
    return result


def make_events(daily):
    cutoff = pd.Timestamp(
        json.loads((FAMILY / "specs/p1-startup-1d.json").read_text())["end"]
    )
    output = []
    btc = daily[daily.symbol.eq("BTC/USDT:USDT")].copy()
    benchmarks = {
        h: label_frame(btc, h, cutoff).set_index("available_at").gross_return
        for h in [3, 7, 14]
    }
    for _, g in daily.groupby("symbol", sort=False):
        for h in [3, 7, 14]:
            z = label_frame(g, h, cutoff)
            keep = (
                z.pool
                & z.state_valid
                & z.available_at.ge(pd.Timestamp("2020-01-01T00:00:00Z"))
            )
            z = z[keep].copy()
            z["btc_excess"] = z.gross_return - z.available_at.map(benchmarks[h])
            output.append(z)
    return pd.concat(output, ignore_index=True)


def daily_comparisons(events):
    rows = []
    for (h, t), g in events.groupby(["horizon_days", "available_at"], sort=True):
        val = g[g.valid]
        strong = val[val.strong]
        rest = val[~val.strong]
        row = {
            "horizon_days": h,
            "available_at": t,
            "entry_year": t.year,
            "state": g.state.iloc[0],
            "bull": bool(g.bull.iloc[0]),
            "candidates": len(g),
            "valid": len(val),
            "strong_valid": len(strong),
            "rest_valid": len(rest),
            "invalid": len(g) - len(val),
        }
        for name, subset in [("all", val), ("strong", strong), ("rest", rest)]:
            for col in [
                "gross_return",
                "cost4_ex_funding",
                "cost8_ex_funding",
                "mae",
                "mfe",
                "btc_excess",
            ]:
                row[name + "_" + col] = subset[col].mean() if len(subset) else np.nan
            row[name + "_median"] = (
                subset.cost4_ex_funding.median() if len(subset) else np.nan
            )
            row[name + "_win_rate"] = (
                subset.cost4_ex_funding.gt(0).mean() if len(subset) else np.nan
            )
        row["paired_valid"] = len(strong) >= 3 and len(rest) >= 3
        row["strong_minus_all"] = (
            row["strong_cost4_ex_funding"] - row["all_cost4_ex_funding"]
            if row["paired_valid"]
            else np.nan
        )
        row["strong_minus_rest"] = (
            row["strong_cost4_ex_funding"] - row["rest_cost4_ex_funding"]
            if row["paired_valid"]
            else np.nan
        )
        rows.append(row)
    return pd.DataFrame(rows)


def interval(frame, market=False):
    f = frame.copy()
    f["month"] = f.available_at.dt.strftime("%Y-%m")
    if market:
        f["a"] = f.all_cost4_ex_funding.where(f.bull)
        f["b"] = f.all_cost4_ex_funding
    else:
        f["a"] = f.strong_minus_all
        f["b"] = 0.0
    agg = f.groupby("month").agg(
        sa=("a", "sum"), na=("a", "count"), sb=("b", "sum"), nb=("b", "count")
    )
    if len(agg) < 12:
        return {"months": len(agg), "ci95_pp": None}
    ix = np.random.default_rng(20260907).integers(0, len(agg), (2000, len(agg)))
    na = agg.na.to_numpy()[ix].sum(axis=1)
    nb = agg.nb.to_numpy()[ix].sum(axis=1)
    good = (na > 0) & (nb > 0)
    z = (
        agg.sa.to_numpy()[ix].sum(axis=1)[good] / na[good]
        - agg.sb.to_numpy()[ix].sum(axis=1)[good] / nb[good]
    ) * 100
    return {
        "months": len(agg),
        "ci95_pp": np.quantile(z, [0.025, 0.975]).tolist(),
        "bootstrap_valid_draws": int(good.sum()),
    }


def state_stats(d):
    rows = []
    for (h, state), g in d.groupby(["horizon_days", "state"]):
        v = g[g.valid.gt(0)]
        rows.append(
            {
                "horizon_days": h,
                "state": state,
                "decision_days": len(g),
                "valid_days": len(v),
                "candidate_coin_days": int(g.candidates.sum()),
                "incomplete_coin_days": int(g.invalid.sum()),
                "gross_mean_pct": v.all_gross_return.mean() * 100,
                "cost4_mean_pct": v.all_cost4_ex_funding.mean() * 100,
                "median_daily_basket_pct": v.all_cost4_ex_funding.median() * 100,
                "positive_basket_day_pct": v.all_cost4_ex_funding.gt(0).mean() * 100,
                "mean_mae_pct": v.all_mae.mean() * 100,
            }
        )
    return pd.DataFrame(rows)


def evaluate(d):
    market = []
    selector = []
    yearly = []
    for h, g in d.groupby("horizon_days"):
        v = g[g.valid.gt(0)]
        b = v[v.bull]
        p = b[b.paired_valid]
        mean = v.all_cost4_ex_funding.mean()
        market.append(
            {
                "horizon_days": h,
                "all_days": len(v),
                "bull_days": len(b),
                "bull_time_pct": len(b) / len(v) * 100,
                "all_mean_pct": mean * 100,
                "bull_mean_pct": b.all_cost4_ex_funding.mean() * 100,
                "nonbull_mean_pct": v[~v.bull].all_cost4_ex_funding.mean() * 100,
                "bull_increment_pp": (b.all_cost4_ex_funding.mean() - mean) * 100,
                "positive_opportunity_retention_pct": b.all_gross_return.clip(
                    lower=0
                ).sum()
                / v.all_gross_return.clip(lower=0).sum()
                * 100,
                "upside_capture_per_time": (
                    b.all_gross_return.clip(lower=0).sum()
                    / v.all_gross_return.clip(lower=0).sum()
                )
                / (len(b) / len(v)),
                "interval": interval(v, market=True),
            }
        )
        selector.append(
            {
                "horizon_days": h,
                "paired_days": len(p),
                "strong_mean_pct": p.strong_cost4_ex_funding.mean() * 100,
                "pool_mean_pct": p.all_cost4_ex_funding.mean() * 100,
                "rest_mean_pct": p.rest_cost4_ex_funding.mean() * 100,
                "strong_minus_pool_pp": p.strong_minus_all.mean() * 100,
                "strong_minus_rest_pp": p.strong_minus_rest.mean() * 100,
                "interval": interval(p),
            }
        )
        for year, w in v.groupby("entry_year"):
            bb = w[w.bull]
            pp = bb[bb.paired_valid]
            yearly.append(
                {
                    "horizon_days": h,
                    "entry_year": year,
                    "all_days": len(w),
                    "bull_days": len(bb),
                    "paired_days": len(pp),
                    "market_all_mean_pct": w.all_cost4_ex_funding.mean() * 100,
                    "market_bull_mean_pct": bb.all_cost4_ex_funding.mean() * 100,
                    "market_increment_pp": (
                        bb.all_cost4_ex_funding.mean() - w.all_cost4_ex_funding.mean()
                    )
                    * 100,
                    "strong_mean_pct": pp.strong_cost4_ex_funding.mean() * 100,
                    "strong_increment_pp": pp.strong_minus_all.mean() * 100,
                }
            )
    y = pd.DataFrame(yearly)
    mp = next(x for x in market if x["horizon_days"] == 7)
    sp = next(x for x in selector if x["horizon_days"] == 7)
    yp = y[y.horizon_days.eq(7)]
    gates = {
        "market": {
            "min_100_days": mp["bull_days"] >= 100,
            "min_3_years": int(yp.bull_days.gt(0).sum()) >= 3,
            "positive_mean_7d": bool(mp["bull_mean_pct"] > 0),
            "positive_increment_7d": bool(mp["bull_increment_pp"] > 0),
            "positive_increment_3_years": int(yp.market_increment_pp.gt(0).sum()) >= 3,
            "secondary_3d_14d_positive": all(
                x["bull_increment_pp"] > 0 for x in market if x["horizon_days"] != 7
            ),
        },
        "strength": {
            "min_100_days": sp["paired_days"] >= 100,
            "min_3_years": int(yp.paired_days.gt(0).sum()) >= 3,
            "positive_mean_7d": bool(sp["strong_mean_pct"] > 0),
            "positive_increment_7d": bool(sp["strong_minus_pool_pp"] > 0),
            "positive_increment_3_years": int(yp.strong_increment_pp.gt(0).sum()) >= 3,
            "secondary_3d_14d_positive": all(
                x["strong_minus_pool_pp"] > 0
                for x in selector
                if x["horizon_days"] != 7
            ),
        },
    }
    return market, selector, y, gates


def main():
    daily = load_verified_inputs()
    events = make_events(daily)
    events.to_parquet(OUT / "p1-events.parquet", index=False)
    d = daily_comparisons(events)
    d.to_parquet(OUT / "p1-day-comparisons.parquet", index=False)
    state_stats(d).to_csv(OUT / "p1-state-summary.csv", index=False)
    market, selector, y, gates = evaluate(d)
    pd.DataFrame(
        [{k: v for k, v in row.items() if k != "interval"} for row in market]
    ).to_csv(OUT / "p1-market-effect.csv", index=False)
    pd.DataFrame(
        [{k: v for k, v in row.items() if k != "interval"} for row in selector]
    ).to_csv(OUT / "p1-strength-effect.csv", index=False)
    y.to_csv(OUT / "p1-by-year.csv", index=False)
    dump(
        OUT / "p1-state-inference.json",
        {
            "market": market,
            "strength": selector,
            "screens": gates,
            "screen_pass": {k: all(v.values()) for k, v in gates.items()},
            "net_performance": False,
            "fresh_oos": False,
        },
    )
    # Disjoint 14-day decision anchors are a descriptive overlap sensitivity, not selection.
    nonoverlap = d[
        (d.available_at - pd.Timestamp("2020-01-01T00:00:00Z")).dt.days.mod(14).eq(0)
    ]
    nm, ns, ny, ng = evaluate(nonoverlap)
    dump(OUT / "p1-nonoverlap-sensitivity.json", {"market": nm, "strength": ns})
    cut = pd.Timestamp(
        json.loads((FAMILY / "specs/p1-startup-1d.json").read_text())["end"]
    )
    recent = []
    for label, days in [
        ("1d", 1),
        ("7d", 7),
        ("1m", 30),
        ("3m", 90),
        ("6m", 180),
        ("1y", 365),
    ]:
        for (h, state), g in d[d.available_at.ge(cut - DAY * days)].groupby(
            ["horizon_days", "state"]
        ):
            v = g[g.valid.gt(0)]
            recent.append(
                {
                    "window": label,
                    "horizon_days": h,
                    "state": state,
                    "decision_days": len(g),
                    "valid_days": len(v),
                    "incomplete_coin_days": int(g.invalid.sum()),
                    "cost4_mean_pct": v.all_cost4_ex_funding.mean() * 100,
                }
            )
    pd.DataFrame(recent).to_csv(OUT / "p1-recent-state-cohorts.csv", index=False)
    events.groupby(["horizon_days", "state", "reason"]).size().rename(
        "events"
    ).reset_index().to_csv(OUT / "p1-validity-counts.csv", index=False)
    (OUT / "provenance/research_p1_states.py.txt").write_bytes(
        Path(__file__).read_bytes()
    )
    print(
        pd.DataFrame(
            [{k: v for k, v in x.items() if k != "interval"} for x in market]
        ).to_string(index=False),
        flush=True,
    )
    print(
        pd.DataFrame(
            [{k: v for k, v in x.items() if k != "interval"} for x in selector]
        ).to_string(index=False),
        flush=True,
    )


if __name__ == "__main__":
    main()
