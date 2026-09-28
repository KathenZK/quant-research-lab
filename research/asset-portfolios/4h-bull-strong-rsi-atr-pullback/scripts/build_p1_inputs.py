"""P1严格启动日线和4H请求，再生成仅属于本家族的因果指标输入。"""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import numpy as np
import pandas as pd
from strategy_lab.data.research_bundle import require_research_startup
from strategy_lab.data.research_inputs import complete_window_mask

ROOT = Path(__file__).resolve().parents[4]
FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/p1-20260907"
DAY = pd.Timedelta(days=1)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        + "\n"
    )


def check_pins():
    for name in ["p1-prefit-hashes.json", "p1-parent-protection.json"]:
        for relative, digest in json.loads(
            (FAMILY / "specs" / name).read_text()
        ).items():
            if sha(FAMILY / relative) != digest:
                raise ValueError(f"Frozen source changed: {relative}")


def load_inputs(request):
    return require_research_startup(request, project_root=ROOT)


def apply_boundaries(frame, boundaries):
    f = frame.copy()
    symbol = f.symbol.iloc[0]
    if symbol == "LIT/USDT:USDT":
        old = f.ts.lt(pd.Timestamp("2025-12-23T17:30:00Z"))
        f.loc[old, ["eligible", "research_window_valid"]] = False
        f.loc[old, "research_segment_id"] = pd.NA
    for b in boundaries:
        if b["symbol"] == symbol:
            mask = f.ts.ge(pd.Timestamp(b["launch_utc"])) & f.eligible
            f.loc[mask, "research_segment_id"] = (
                f.loc[mask, "research_segment_id"] + "@identity"
            )
    return f


def daily_features(frame):
    cols = [
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
    f = frame[cols].copy()
    for col in ["ma50", "ma100", "ma50_lag5", "mom30", "median_quote20"]:
        f[col] = np.nan
    for _, g in f.groupby("research_segment_id", sort=False):
        idx = g.index
        c = g.close.reset_index(drop=True)
        ma50 = c.rolling(50).mean()
        f.loc[idx, "ma50"] = ma50.values
        f.loc[idx, "ma100"] = c.rolling(100).mean().values
        f.loc[idx, "ma50_lag5"] = ma50.shift(5).values
        f.loc[idx, "mom30"] = (c / c.shift(30) - 1).values
        f.loc[idx, "median_quote20"] = g.quote_volume.rolling(20).median().values
    f["feature_valid"] = f.research_window_valid & complete_window_mask(
        frame, backward=60, forward=0
    )
    f["available_at"] = f.ts + DAY
    return f


def market_and_strength(daily):
    d = daily.copy()
    d["pool"] = False
    d["strong"] = False
    eligible = d.feature_valid & d.median_quote20.ge(10_000_000)
    liquid = (
        d[eligible]
        .sort_values(["ts", "median_quote20", "symbol"], ascending=[True, False, True])
        .groupby("ts", sort=False)
        .head(100)
    )
    d.loc[liquid.index, "pool"] = True
    ranked = liquid.sort_values(
        ["ts", "mom30", "symbol"], ascending=[True, False, True]
    )
    rank = ranked.groupby("ts", sort=False).cumcount() + 1
    n = ranked.groupby("ts", sort=False).symbol.transform("size")
    chosen = ranked[(rank <= np.ceil(n * 0.2)) & ranked.mom30.gt(0)]
    d.loc[chosen.index, "strong"] = True
    d["above_ma50"] = d.close > d.ma50
    market = (
        d[d.pool]
        .groupby("ts")
        .agg(pool_size=("symbol", "size"), breadth=("above_ma50", "mean"))
    )
    btc = d[d.symbol.eq("BTC/USDT:USDT")].set_index("ts")
    market = market.join(btc[["close", "ma100", "ma50", "ma50_lag5"]])
    market["state_valid"] = market.pool_size.ge(20) & market[
        ["close", "ma100", "ma50", "ma50_lag5"]
    ].notna().all(axis=1)
    market["btc_up"] = (market.close > market.ma100) & (market.ma50 > market.ma50_lag5)
    market["broad"] = market.breadth > 0.6
    market["bull"] = market.state_valid & market.btc_up & market.broad
    market["state"] = np.select(
        [
            ~market.state_valid,
            market.btc_up & market.broad,
            market.btc_up & ~market.broad,
            ~market.btc_up & market.broad,
        ],
        ["UNKNOWN", "BTC_UP_BROAD", "BTC_UP_NARROW", "BTC_DOWN_BROAD"],
        default="BTC_DOWN_NARROW",
    )
    market["available_at"] = market.index + DAY
    for name in [
        "state_valid",
        "btc_up",
        "broad",
        "bull",
        "state",
        "breadth",
        "pool_size",
    ]:
        d[name] = d.ts.map(market[name])
    for col in ["state_valid", "btc_up", "broad", "bull"]:
        d[col] = d[col].fillna(False).astype(bool)
    d["state"] = d.state.fillna("UNKNOWN")
    d["strong_last5_count"] = d.groupby(
        "research_segment_id", sort=False
    ).strong.transform(lambda x: x.rolling(5).sum())
    return d, market.reset_index()


def attach_daily(four, daily):
    f = four.copy()
    f["signal_time"] = f.ts + pd.Timedelta(hours=4)
    f["daily_available_key"] = f.signal_time.dt.floor("D")
    fields = [
        "symbol",
        "available_at",
        "pool",
        "strong",
        "bull",
        "state",
        "mom30",
        "median_quote20",
    ]
    right = daily[fields].rename(
        columns={
            "available_at": "daily_available_key",
            "mom30": "daily_mom30",
            "median_quote20": "daily_liquidity",
        }
    )
    f = f.drop(columns=["bull"], errors="ignore").merge(
        right, on=["symbol", "daily_available_key"], how="left", validate="many_to_one"
    )
    for c in ["pool", "strong", "bull"]:
        f[c] = f[c].fillna(False).astype(bool)
    f["state"] = f.state.fillna("UNKNOWN")
    f["admission"] = f.feature_valid & f.pool & f.strong & f.bull
    return f


def main():
    check_pins()
    OUT.mkdir(exist_ok=False)
    start = time.time()
    boundary_path = (
        ROOT
        / "research/platform/data-lake-governance/specs/binance-15m-history-v3-boundaries-2026-09-06.json"
    )
    boundaries = json.loads(boundary_path.read_text())["boundaries"]
    config = json.loads((FAMILY / "specs/p1-config.json").read_text())
    p0 = FAMILY / config["frozen_p0_indicator_source"]["path"]
    if sha(p0) != config["frozen_p0_indicator_source"]["sha256"]:
        raise ValueError("P0 indicator source changed")
    spec = importlib.util.spec_from_file_location("p0_features", p0)
    indicator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(indicator)
    requests = {
        tf: json.loads((FAMILY / f"specs/p1-startup-{tf}.json").read_text())
        for tf in ["1d", "4h"]
    }
    print("Verifying both new P1 requests: 652 symbols, daily + 4h", flush=True)
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = {tf: ex.submit(load_inputs, req) for tf, req in requests.items()}
        try:
            daily_inputs = futures["1d"].result()
            dump(OUT / "startup-1d.json", daily_inputs.report)
            daily = pd.concat(
                [
                    daily_features(apply_boundaries(f, boundaries))
                    for f in daily_inputs.prices.values()
                ],
                ignore_index=True,
            )
            daily, market = market_and_strength(daily)
            daily.to_parquet(OUT / "daily-features.parquet", index=False)
            market.to_csv(OUT / "daily-market-state.csv", index=False)
            print(
                "Daily price/state inputs ready, seconds",
                round(time.time() - start, 1),
                flush=True,
            )
            del daily_inputs
            four_inputs = futures["4h"].result()
            dump(OUT / "startup-4h.json", four_inputs.report)
        except Exception as e:
            dump(
                OUT / "startup-rejected.json",
                {"error": str(e), "status": "RESEARCH_STARTUP_REJECTED"},
            )
            raise
    four_frames = []
    for symbol, frame in four_inputs.prices.items():
        frame = apply_boundaries(frame, boundaries)
        f = indicator.features(frame)
        f["feature_valid"] = frame.research_window_valid & complete_window_mask(
            frame, backward=20, forward=0
        )
        f["atr_down"] = f.atr_down.fillna(0).astype(bool)
        f["natr_down"] = f.natr_down.fillna(0).astype(bool)
        four_frames.append(attach_daily(f, daily[daily.symbol.eq(symbol)]))
    four = pd.concat(four_frames, ignore_index=True)
    four.to_parquet(OUT / "four-hour-features.parquet", index=False)
    sources = [
        Path(__file__),
        p0,
        boundary_path,
        ROOT / "src/strategy_lab/data/research_bundle.py",
        ROOT / "src/strategy_lab/data/research_inputs.py",
        ROOT / "src/strategy_lab/data/catalog.py",
    ]
    prov = OUT / "provenance"
    prov.mkdir()
    for p in sources:
        (prov / (p.name + ".txt")).write_bytes(p.read_bytes())
    dump(
        OUT / "input-manifest.json",
        {
            "status": "P1_SAME_FAMILY_VERIFIED_FEATURE_INPUTS",
            "daily_rows": len(daily),
            "four_hour_rows": len(four),
            "artifacts": {p.name: sha(p) for p in OUT.iterdir() if p.is_file()},
            "prefit": json.loads((FAMILY / "specs/p1-prefit-hashes.json").read_text()),
            "source_hashes": {str(p.relative_to(ROOT)): sha(p) for p in sources},
            "funding_verified": False,
            "pit_verified": False,
        },
    )
    check_pins()
    print(
        "P1 inputs complete; elapsed",
        round(time.time() - start, 1),
        "seconds",
        flush=True,
    )


if __name__ == "__main__":
    main()
