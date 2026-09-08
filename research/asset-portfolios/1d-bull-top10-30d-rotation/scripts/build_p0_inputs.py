"""独立启动日线及4H输入，构建简单Top10轮动的历史状态。"""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import pandas as pd
from strategy_lab.data.research_bundle import require_research_startup
from strategy_lab.data.research_inputs import complete_window_mask

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
OUT = FAMILY / "artifacts/p0-20260907"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dump(p, obj):
    p.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        + "\n"
    )


def check_pins():
    for n, h in json.loads(
        (FAMILY / "specs/p0-prefit-hashes.json").read_text()
    ).items():
        assert sha(FAMILY / n) == h, n
    for n, h in json.loads(
        (FAMILY / "specs/parent-protection.json").read_text()
    ).items():
        assert sha(ROOT / n) == h, n


def load_inputs(request):
    return require_research_startup(request, project_root=ROOT)


def boundaries(f, known):
    f = f.copy()
    symbol = f.symbol.iloc[0]
    if symbol == "LIT/USDT:USDT":
        old = f.ts.lt(pd.Timestamp("2025-12-23T17:30:00Z"))
        f.loc[old, ["eligible", "research_window_valid"]] = False
        f.loc[old, "research_segment_id"] = pd.NA
    for x in known:
        if x["symbol"] == symbol:
            mask = f.ts.ge(pd.Timestamp(x["launch_utc"])) & f.eligible
            f.loc[mask, "research_segment_id"] = (
                f.loc[mask, "research_segment_id"] + "@identity"
            )
    return f


def daily_features(f):
    f = f.copy()
    for c in ["ma50", "ma100", "ma50_lag5", "mom30", "liquidity"]:
        f[c] = np.nan
    for _, g in f.groupby("research_segment_id", sort=False):
        c = g.close
        f.loc[g.index, "ma50"] = c.rolling(50).mean()
        f.loc[g.index, "ma100"] = c.rolling(100).mean()
        f.loc[g.index, "ma50_lag5"] = c.rolling(50).mean().shift(5)
        f.loc[g.index, "mom30"] = c / c.shift(30) - 1
        f.loc[g.index, "liquidity"] = g.quote_volume.rolling(20).median()
    f["formation_valid"] = f.research_window_valid & complete_window_mask(
        f, backward=60, forward=0
    )
    f["signal_time"] = f.ts + pd.Timedelta(days=1)
    return f


def states(d):
    d = d.copy()
    d["pool"] = False
    liquid = (
        d[d.formation_valid & d.liquidity.ge(10_000_000)]
        .sort_values(
            ["signal_time", "liquidity", "symbol"], ascending=[True, False, True]
        )
        .groupby("signal_time", sort=False)
        .head(100)
    )
    d.loc[liquid.index, "pool"] = True
    ranked = liquid.sort_values(
        ["signal_time", "mom30", "symbol"], ascending=[True, False, True]
    )
    d["momentum_rank"] = np.nan
    d.loc[ranked.index, "momentum_rank"] = (
        ranked.groupby("signal_time", sort=False).cumcount() + 1
    )
    liquid = liquid.assign(above=liquid.close.gt(liquid.ma50))
    market = liquid.groupby("signal_time").agg(
        pool_size=("symbol", "size"), breadth=("above", "mean")
    )
    btc = d[d.symbol.eq("BTC/USDT:USDT")].set_index("signal_time")
    market = market.join(btc[["close", "ma100", "ma50", "ma50_lag5"]])
    market["state_valid"] = market.pool_size.ge(20) & market[
        ["close", "ma100", "ma50", "ma50_lag5"]
    ].notna().all(axis=1)
    market["bull"] = (
        market.state_valid
        & market.close.gt(market.ma100)
        & market.ma50.gt(market.ma50_lag5)
        & market.breadth.gt(0.6)
    )
    market = market.reset_index()
    return d, market


def main():
    check_pins()
    OUT.mkdir(exist_ok=False)
    (OUT / "provenance").mkdir()
    boundary_path = (
        ROOT
        / "research/platform/data-lake-governance/specs/binance-15m-history-v3-boundaries-2026-09-06.json"
    )
    known = json.loads(boundary_path.read_text())["boundaries"]
    t0 = time.monotonic()
    requests = {
        tf: json.loads((FAMILY / f"specs/p0-startup-{tf}.json").read_text())
        for tf in ["1d", "4h"]
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = {tf: pool.submit(load_inputs, req) for tf, req in requests.items()}
        for tf in ["1d", "4h"]:
            inp = tasks[tf].result()
            dump(OUT / f"startup-{tf}.json", inp.report)
            frames = [boundaries(f, known) for f in inp.prices.values()]
            if tf == "1d":
                d, market = states(
                    pd.concat([daily_features(f) for f in frames], ignore_index=True)
                )
                d.to_parquet(OUT / "daily-features.parquet", index=False)
                market.to_parquet(OUT / "market-states.parquet", index=False)
                market.to_csv(OUT / "market-states.csv", index=False)
            else:
                columns = [
                    "symbol",
                    "ts",
                    "open",
                    "high",
                    "low",
                    "close",
                    "eligible",
                    "research_segment_id",
                ]
                pd.concat([f[columns] for f in frames], ignore_index=True).to_parquet(
                    OUT / "four-hour-prices.parquet", index=False
                )
            print(f"{tf} inputs done, {time.monotonic() - t0:.1f}s", flush=True)
            del inp, frames
    sources = [
        Path(__file__),
        boundary_path,
        ROOT / "src/strategy_lab/data/research_bundle.py",
        ROOT / "src/strategy_lab/data/research_inputs.py",
    ]
    for p in sources:
        (OUT / "provenance" / (p.name + ".txt")).write_bytes(p.read_bytes())
    dump(
        OUT / "input-manifest.json",
        {
            "status": "PRICE_DIAGNOSTIC_INPUTS_VERIFIED",
            "funding_verified": False,
            "pit_verified": False,
            "artifacts": {p.name: sha(p) for p in OUT.iterdir() if p.is_file()},
            "sources": {str(p.relative_to(ROOT)): sha(p) for p in sources},
            "prefit": json.loads((FAMILY / "specs/p0-prefit-hashes.json").read_text()),
        },
    )
    check_pins()
    print("Inputs complete", flush=True)


if __name__ == "__main__":
    main()
