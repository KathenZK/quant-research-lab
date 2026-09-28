"""回放已验指纹的同家族特征；收益口径明确排除未验证 funding。"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/p0-20260907"
STEP = pd.Timedelta(hours=4)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dump(p, obj):
    p.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        + "\n"
    )


def cost_return(open_price, exit_price, bps=4, fee=0.001):
    ratio = exit_price * (1 - bps / 10000) / (open_price * (1 + bps / 10000))
    return ratio - 1 - fee * (1 + ratio)


def signal_mask(g, v, named):
    signal = g.feature_valid & g.liquid
    if v.get("named"):
        # Named observation retains the same liquidity floor but no cross-sectional strength.
        signal &= g.symbol.isin(named)
    if v["bull"]:
        signal &= g.bull
    if v["strong"]:
        signal &= g.strong
    if v["rsi_period"]:
        signal &= g[f"rsi{v['rsi_period']}"] <= v["rsi_threshold"]
    if v["atr"]:
        signal &= g.natr_down if v.get("atr_measure") == "natr" else g.atr_down
    return np.array(signal.fillna(False), dtype=bool, copy=True)


def replay_symbol(g, v, config):
    g = g.reset_index(drop=True)
    ts = list(g.ts)
    op = g.open.to_numpy()
    lo = g.low.to_numpy()
    cl = g.close.to_numpy()
    seg = g.research_segment_id.fillna("").to_numpy()
    valid = g.eligible.to_numpy()
    bands = g.stop_band.to_numpy()
    sig = signal_mask(g, v, config["named_symbols"])
    start = pd.Timestamp(config["evaluation_start"])
    cutoff = pd.Timestamp(config["data_end"])
    trades = []
    pos = None
    counters = {
        "signals": 0,
        "entry_invalid_stop": 0,
        "entry_missing_or_boundary": 0,
        "signal_while_held": 0,
        "entries": 0,
    }
    for i in range(len(g)):
        # A missing/invalid next bar cannot be converted into a clairvoyant previous-close exit.
        continuous = (
            i > 0
            and valid[i]
            and valid[i - 1]
            and seg[i] == seg[i - 1]
            and ts[i] - ts[i - 1] == STEP
        )
        if pos is not None and not continuous:
            pos.update(
                status="censored",
                reason="price_gap_or_identity_boundary",
                last_valuation_time=ts[i - 1] + STEP,
                last_mark_gross=cl[i - 1] / pos["entry_open"] - 1,
            )
            trades.append(pos)
            pos = None
        # Signal is from previous fully closed bar; a position exiting this open does not
        # accept a signal generated while it was still held.
        if pos is None and i > 0 and sig[i - 1] and ts[i] >= start:
            if not continuous:
                counters["entry_missing_or_boundary"] += 1
            elif (
                not np.isfinite(bands[i - 1])
                or bands[i - 1] <= 0
                or bands[i - 1] >= op[i]
            ):
                counters["entry_invalid_stop"] += 1
            else:
                pos = {
                    "variant": v["id"],
                    "symbol": g.symbol.iloc[0],
                    "signal_time": ts[i - 1] + STEP,
                    "signal_bar_open": ts[i - 1],
                    "entry_time": ts[i],
                    "entry_open": float(op[i]),
                    "initial_stop": float(bands[i - 1]),
                    "stop": float(bands[i - 1]),
                    "pending_exit": False,
                    "entry_i": i,
                    "rsi_entry": float(g[f"rsi{v['rsi_period'] or 14}"].iloc[i - 1]),
                    "atr_entry": float(g.atr14.iloc[i - 1]),
                    "momentum_entry": float(g.mom30_lag1d.iloc[i - 1]),
                    "adv7_entry": float(g.adv7.iloc[i - 1]),
                }
                counters["entries"] += 1
        if pos is not None:
            price = None
            reason = None
            is_open = False
            if pos["pending_exit"]:
                price = op[i]
                reason = "new_stop_marketable_next_open"
                is_open = True
            elif op[i] <= pos["stop"]:
                price = op[i]
                reason = "gap_through_stop"
                is_open = True
            elif lo[i] <= pos["stop"]:
                price = pos["stop"]
                reason = "intrabar_stop"
            if price is not None:
                pos.update(
                    status="closed",
                    reason=reason,
                    exit_bar_open=ts[i],
                    exit_time_upper_bound=ts[i] if is_open else ts[i] + STEP,
                    exit_price_before_slip=float(price),
                    gross_return=float(price / pos["entry_open"] - 1),
                    cost_adjusted_ex_funding_4bps=float(
                        cost_return(pos["entry_open"], price, 4)
                    ),
                    cost_adjusted_ex_funding_8bps=float(
                        cost_return(pos["entry_open"], price, 8)
                    ),
                    held_bars=i - pos["entry_i"] + 1,
                )
                trades.append(pos)
                pos = None
            elif valid[i] and np.isfinite(bands[i]):
                pos["stop"] = float(
                    max(pos["stop"], bands[i]) if v["exit"] == "ratchet" else bands[i]
                )
                pos["pending_exit"] = pos["stop"] >= cl[i]
        if sig[i] and ts[i] + STEP >= start:
            counters["signals"] += 1
            if pos is not None:
                counters["signal_while_held"] += 1
                # Mark this signal as consumed by an existing position for the next open.
                sig[i] = False
    if pos is not None:
        reason = (
            "right_censor_cutoff"
            if ts[-1] + STEP == cutoff
            else "symbol_history_end_unknown"
        )
        pos.update(
            status="censored",
            reason=reason,
            last_valuation_time=ts[-1] + STEP,
            last_mark_gross=cl[-1] / pos["entry_open"] - 1,
        )
        trades.append(pos)
    # A signal on the last bar has no next bar available, independent of its prospective stop.
    if len(g) and sig[-1] and ts[-1] + STEP >= start:
        counters["entry_missing_or_boundary"] += 1
    for t in trades:
        t["entry_year"] = pd.Timestamp(t["entry_time"]).year
        t["entry_month"] = pd.Timestamp(t["entry_time"]).strftime("%Y-%m")
        for field in ["stop", "pending_exit", "entry_i"]:
            t.pop(field, None)
    return trades, counters


def statistics(group):
    closed = group[group.status.eq("closed")]
    result = {
        "trades_total": len(group),
        "closed": len(closed),
        "censored": len(group) - len(closed),
        "symbols": group.symbol.nunique(),
    }
    for field, label in [
        ("gross_return", "gross"),
        ("cost_adjusted_ex_funding_4bps", "cost4_ex_funding"),
        ("cost_adjusted_ex_funding_8bps", "cost8_ex_funding"),
    ]:
        a = closed[field].dropna().to_numpy(dtype=float)
        neg = -a[a < 0].sum()
        pos = a[a > 0].sum()
        result.update(
            {
                label + "_mean_pct": 100 * a.mean() if len(a) else None,
                label + "_median_pct": 100 * np.median(a) if len(a) else None,
                label + "_win_pct": 100 * (a > 0).mean() if len(a) else None,
                label + "_pf": pos / neg if neg > 0 else None,
            }
        )
    return result


def grouped_stats(trades, keys):
    rows = []
    for key, g in trades.groupby(keys, sort=True):
        if not isinstance(key, tuple):
            key = (key,)
        rows.append(dict(zip(keys, key)) | statistics(g))
    return pd.DataFrame(rows)


def forward_events(panel, config):
    rows = []
    variants = {v["id"]: v for v in config["variants"]}
    btc = panel[panel.symbol.eq("BTC/USDT:USDT")].set_index("ts").open
    for sym, g in panel.groupby("symbol", sort=False):
        g = g.reset_index(drop=True)
        seg = g.research_segment_id.fillna("")
        start = pd.Timestamp(config["evaluation_start"])
        base = signal_mask(g, variants["without_atr"], config["named_symbols"])
        for i in np.flatnonzero(base):
            j = i + 1
            if (
                j >= len(g)
                or g.ts.iloc[j] < start
                or g.ts.iloc[j] - g.ts.iloc[i] != STEP
                or not seg.iloc[i]
                or seg.iloc[i] != seg.iloc[j]
            ):
                continue
            for h in config["forward_horizons_bars"]:
                k = j + h
                complete = (
                    k < len(g)
                    and seg.iloc[k] == seg.iloc[i]
                    and g.ts.iloc[k] - g.ts.iloc[i] == STEP * (h + 1)
                )
                r = {
                    "symbol": sym,
                    "entry_time": g.ts.iloc[j],
                    "entry_year": g.ts.iloc[j].year,
                    "entry_month": str(g.ts.iloc[j])[:7],
                    "horizon_days": h // 6,
                    "atr_declining": bool(g.atr_down.iloc[i]),
                    "valid": complete,
                }
                if complete:
                    ret = g.open.iloc[k] / g.open.iloc[j] - 1
                    bt0 = btc.get(g.ts.iloc[j], np.nan)
                    bt1 = btc.get(g.ts.iloc[k], np.nan)
                    r.update(
                        gross_return=float(ret), btc_excess=float(ret - (bt1 / bt0 - 1))
                    )
                rows.append(r)
    return pd.DataFrame(rows)


def block_interval(trades):
    primary = trades[trades.variant.eq("primary") & trades.status.eq("closed")].copy()
    if len(primary) < 2:
        return {"method": "entry_month_cluster_bootstrap", "ci95_mean_pct": None}
    # Resample whole entry-month blocks to retain contemporaneous cross-coin clustering.
    agg = primary.groupby("entry_month").cost_adjusted_ex_funding_4bps.agg(
        ["sum", "count"]
    )
    rng = np.random.default_rng(9072026)
    ix = rng.integers(0, len(agg), (2000, len(agg)))
    samples = agg["sum"].to_numpy()[ix].sum(axis=1) / agg["count"].to_numpy()[ix].sum(
        axis=1
    )
    return {
        "method": "entry_month_cluster_bootstrap_2000_seed9072026",
        "months": len(agg),
        "ci95_mean_pct": (np.quantile(samples, [0.025, 0.975]) * 100).tolist(),
        "interpretation": "exploratory; sparse blocks and cross-month dependence limit inference",
    }


def main():
    manifest = json.loads((OUT / "features-manifest.json").read_text())
    assert sha(OUT / "features.parquet") == manifest["features_sha256"]
    assert sha(OUT / "startup-report.json") == manifest["startup_report_sha256"]
    for rel, h in manifest["prefit"].items():
        assert sha(FAMILY / rel) == h, "Frozen contract changed"
    # This is a hash-pinned feature artifact from the startup-returned frames in this family.
    panel = pd.read_parquet(OUT / "features.parquet")
    config = json.loads((FAMILY / "specs/p0-config.json").read_text())
    config["data_end"] = json.loads(
        (FAMILY / "specs/startup-price-p0.json").read_text()
    )["end"]
    rows = []
    counts = []
    groups = list(panel.groupby("symbol", sort=False))
    for v in config["variants"]:
        for sym, g in groups:
            if v.get("named") and sym not in config["named_symbols"]:
                continue
            tr, c = replay_symbol(g, v, config)
            rows.extend(tr)
            counts.append(dict(variant=v["id"], symbol=sym, **c))
        print("Replayed", v["id"], "cumulative trades", len(rows), flush=True)
    trades = pd.DataFrame(rows)
    trades["trade_id"] = [f"P0-{i:07d}" for i in range(len(trades))]
    trades.to_parquet(OUT / "trades.parquet", index=False)
    trades.to_csv(OUT / "trades.csv", index=False)
    pd.DataFrame(counts).to_csv(OUT / "signal-counts.csv", index=False)
    for keys, name in [
        (["variant"], "summary"),
        (["variant", "symbol"], "by-symbol"),
        (["variant", "entry_year"], "by-year"),
    ]:
        grouped_stats(trades, keys).to_csv(OUT / f"{name}.csv", index=False)
    cutoff = pd.Timestamp(config["data_end"])
    slices = []
    for label, days in [
        ("1d", 1),
        ("7d", 7),
        ("1m", 30),
        ("3m", 90),
        ("6m", 180),
        ("1y", 365),
    ]:
        left = cutoff - pd.Timedelta(days=days)
        for v in config["variants"]:
            all_v = trades[trades.variant.eq(v["id"])]
            g = all_v[all_v.entry_time.ge(left) & all_v.entry_time.lt(cutoff)]
            s = dict(
                variant=v["id"],
                window=label,
                start=str(left),
                end=str(cutoff),
                **statistics(g),
            )
            # Existing trades carried into the slice are separately counted, not silently lost.
            s["carried_in"] = int(
                (
                    all_v.entry_time.lt(left)
                    & (
                        all_v.exit_time_upper_bound.isna()
                        | all_v.exit_time_upper_bound.ge(left)
                    )
                ).sum()
            )
            slices.append(s)
    pd.DataFrame(slices).to_csv(OUT / "recent-entry-cohorts.csv", index=False)
    events = forward_events(panel, config)
    events.to_parquet(OUT / "forward-events.parquet", index=False)
    labels = []
    for keys, g in events.groupby(["horizon_days", "entry_year", "atr_declining"]):
        val = g[g.valid]
        labels.append(
            dict(zip(["horizon_days", "entry_year", "atr_declining"], keys))
            | {
                "events": len(g),
                "valid": len(val),
                "gross_mean_pct": float(val.gross_return.mean() * 100)
                if len(val)
                else None,
                "gross_median_pct": float(val.gross_return.median() * 100)
                if len(val)
                else None,
                "btc_excess_mean_pct": float(val.btc_excess.mean() * 100)
                if len(val)
                else None,
            }
        )
    pd.DataFrame(labels).to_csv(OUT / "forward-label-summary.csv", index=False)
    dump(OUT / "bootstrap.json", block_interval(trades))
    dump(
        OUT / "result-manifest.json",
        {
            "result_label": "PRICE_DIAGNOSTIC_ONLY_NOT_NET_PERFORMANCE",
            "config_sha256": sha(FAMILY / "specs/p0-config.json"),
            "feature_manifest_sha256": sha(OUT / "features-manifest.json"),
            "replay_script_sha256": sha(Path(__file__)),
            "funding_verified": False,
            "pit_proven": False,
            "artifacts": {
                name: sha(OUT / name)
                for name in (
                    "trades.parquet",
                    "trades.csv",
                    "signal-counts.csv",
                    "summary.csv",
                    "by-symbol.csv",
                    "by-year.csv",
                    "recent-entry-cohorts.csv",
                    "forward-events.parquet",
                    "forward-label-summary.csv",
                    "bootstrap.json",
                    "startup-report.json",
                    "features-manifest.json",
                )
            },
        },
    )
    (OUT / "provenance/replay_p0.py.txt").write_bytes(Path(__file__).read_bytes())
    print(grouped_stats(trades, ["variant"]).to_string(index=False), flush=True)


if __name__ == "__main__":
    sys.exit(main())
