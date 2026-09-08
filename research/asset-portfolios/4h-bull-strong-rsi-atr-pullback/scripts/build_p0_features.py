"""P0：只消费组合启动返回帧，生成同家族可校验的指标快照。"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd
from strategy_lab.data.research_bundle import require_research_startup
from strategy_lab.data.research_inputs import complete_window_mask

ROOT = Path(__file__).resolve().parents[4]
FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/p0-20260907"
STEP = pd.Timedelta(hours=4)


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dump(p, obj):
    p.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        + "\n"
    )


def wilder(x, n):
    """Arithmetic seed over n observations, then Wilder recurrence; initial NaNs only."""
    a = np.asarray(x, dtype=float)
    out = np.full(len(a), np.nan)
    valid = np.flatnonzero(np.isfinite(a))
    if len(valid) < n:
        return out
    first = valid[0]
    if not np.isfinite(a[first:]).all():
        raise ValueError("RMA input must be contiguous after initial NaNs")
    i = first + n - 1
    out[i] = a[first : i + 1].mean()
    for j in range(i + 1, len(a)):
        out[j] = (out[j - 1] * (n - 1) + a[j]) / n
    return out


def features(frame):
    # The startup mask is a mandatory prerequisite; longer lookbacks are checked separately.
    keep = [
        "symbol",
        "ts",
        "open",
        "high",
        "low",
        "close",
        "quote_volume",
        "eligible",
        "research_window_valid",
        "research_segment_id",
    ]
    f = frame[keep].copy()
    for col in [
        "ma7",
        "atr14",
        "atr_down",
        "natr_down",
        "rsi14",
        "rsi6",
        "mom30_lag1d",
        "adv7",
        "bull",
    ]:
        f[col] = np.nan
    for _, group in f.groupby("research_segment_id", sort=False):
        ix = group.index
        close = group.close.reset_index(drop=True)
        prev = close.shift()
        tr = pd.concat(
            [
                (group.high - group.low).reset_index(drop=True),
                (group.high.reset_index(drop=True) - prev).abs(),
                (group.low.reset_index(drop=True) - prev).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = pd.Series(wilder(tr, 14))
        f.loc[ix, "ma7"] = close.rolling(7).mean().values
        f.loc[ix, "atr14"] = atr.values
        f.loc[ix, "atr_down"] = (atr < atr.shift(6)).values.astype(float)
        natr = atr / close
        f.loc[ix, "natr_down"] = (natr < natr.shift(6)).values.astype(float)
        delta = close.diff()
        for n in [6, 14]:
            up, down = wilder(delta.clip(lower=0), n), wilder(-delta.clip(upper=0), n)
            den = up + down
            rsi = np.divide(100 * up, den, out=np.full(len(den), 50.0), where=den > 0)
            rsi[~np.isfinite(den)] = np.nan
            f.loc[ix, f"rsi{n}"] = rsi
        f.loc[ix, "mom30_lag1d"] = (close.shift(6) / close.shift(186) - 1).values
        f.loc[ix, "adv7"] = (
            group.quote_volume.reset_index(drop=True).rolling(42).mean() * 6
        ).values
        ma = close.rolling(360).mean()
        bull = (close > ma) & (ma > ma.shift(30)) & (close > close.shift(180))
        f.loc[ix, "bull"] = bull.values.astype(float)
    f["feature_valid"] = (
        complete_window_mask(frame, backward=187, forward=0).values
        & f.research_window_valid
    )
    f["stop_band"] = f.ma7 - 2 * f.atr14
    return f


def load_inputs(request):
    return require_research_startup(request, project_root=ROOT)


def main():
    OUT.mkdir(exist_ok=False)
    request = json.loads((FAMILY / "specs/startup-price-p0.json").read_text())
    for rel, h in json.loads(
        (FAMILY / "specs/p0-prefit-hashes.json").read_text()
    ).items():
        if digest(FAMILY / rel) != h:
            raise ValueError("Prefit contract changed")
    print(
        "Starting full bundle integrity + exact-window price checks for",
        len(request["symbols"]),
        "symbols",
        flush=True,
    )
    t = time.time()
    try:
        inputs = load_inputs(request)
    except Exception as exc:
        dump(
            OUT / "startup-rejected.json",
            {"status": "RESEARCH_STARTUP_REJECTED", "error": str(exc)},
        )
        raise
    dump(OUT / "startup-report.json", inputs.report)
    print("Startup passed in", round(time.time() - t, 1), "seconds", flush=True)
    boundary_path = (
        ROOT
        / "research/platform/data-lake-governance/specs/binance-15m-history-v3-boundaries-2026-09-06.json"
    )
    boundaries = json.loads(boundary_path.read_text())["boundaries"]
    cols = []
    audit = []
    for k, (symbol, frame) in enumerate(inputs.prices.items()):
        f = frame.copy()
        # Additional known identity boundaries may tighten, never widen the startup eligibility.
        if symbol == "LIT/USDT:USDT":
            old = f.ts.lt(pd.Timestamp("2025-12-23T17:30:00Z"))
            f.loc[old, ["eligible", "research_window_valid"]] = False
            f.loc[old, "research_segment_id"] = pd.NA
        for b in boundaries:
            if b["symbol"] == symbol:
                after = f.ts.ge(pd.Timestamp(b["launch_utc"]))
                f.loc[after & f.eligible, "research_segment_id"] = (
                    f.loc[after & f.eligible, "research_segment_id"] + "@new_identity"
                )
        f["research_window_valid"] &= complete_window_mask(f, backward=1, forward=0)
        z = features(f)
        cols.append(z)
        audit.append(
            {
                "symbol": symbol,
                "rows": len(z),
                "eligible_rows": int(z.eligible.sum()),
                "feature_rows": int(z.feature_valid.sum()),
                "first": str(z.ts.min()),
                "last_close": str(z.ts.max() + STEP),
                "segments": int(z.research_segment_id.nunique()),
            }
        )
        if k % 100 == 0:
            print("Features", k + 1, "/", len(inputs.prices), flush=True)
    panel = pd.concat(cols, ignore_index=True)
    btc = panel[panel.symbol.eq("BTC/USDT:USDT")].set_index("ts")
    panel["bull"] = panel.ts.map(btc.bull).fillna(0).astype(bool)
    panel["liquid"] = False
    panel["strong"] = False
    eligible = panel.feature_valid & panel.adv7.ge(10_000_000)
    ranked = panel[eligible].sort_values(
        ["ts", "adv7", "symbol"], ascending=[True, False, True]
    )
    liquid = ranked.groupby("ts", sort=False).head(100)
    panel.loc[liquid.index, "liquid"] = True
    ranks = liquid.sort_values(
        ["ts", "mom30_lag1d", "symbol"], ascending=[True, False, True]
    )
    pos = ranks.groupby("ts", sort=False).cumcount() + 1
    count = ranks.groupby("ts", sort=False).symbol.transform("size")
    strong = ranks[(pos <= np.ceil(count * 0.2)) & ranks.mom30_lag1d.gt(0)]
    panel.loc[strong.index, "strong"] = True
    panel["atr_down"] = panel.atr_down.fillna(0).astype(bool)
    panel["natr_down"] = panel.natr_down.fillna(0).astype(bool)
    panel.to_parquet(OUT / "features.parquet", index=False)
    pd.DataFrame(audit).to_csv(OUT / "data-coverage.csv", index=False)
    prov = OUT / "provenance"
    prov.mkdir()
    sources = [
        Path(__file__),
        ROOT / "src/strategy_lab/data/research_bundle.py",
        ROOT / "src/strategy_lab/data/catalog.py",
        ROOT / "src/strategy_lab/data/research_inputs.py",
        ROOT / "src/strategy_lab/data/funding_v2.py",
        boundary_path,
    ]
    for p in sources:
        (prov / p.name).write_bytes(p.read_bytes())
    dump(
        OUT / "features-manifest.json",
        {
            "status": "SAME_FAMILY_VERIFIED_FEATURE_ARTIFACT",
            "rows": len(panel),
            "symbols": panel.symbol.nunique(),
            "features_sha256": digest(OUT / "features.parquet"),
            "startup_report_sha256": digest(OUT / "startup-report.json"),
            "source_hashes": {str(p.relative_to(ROOT)): digest(p) for p in sources},
            "prefit": json.loads((FAMILY / "specs/p0-prefit-hashes.json").read_text()),
            "data_dataset_id": "binance.perp.ohlcv.4h.from_15m.v2",
            "net_return_permitted": False,
        },
    )
    print(
        "Features ready:",
        len(panel),
        "rows, seconds",
        round(time.time() - t, 1),
        flush=True,
    )


if __name__ == "__main__":
    sys.exit(main())
