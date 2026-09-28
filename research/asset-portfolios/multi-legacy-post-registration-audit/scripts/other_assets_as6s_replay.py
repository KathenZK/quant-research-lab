"""Replay recovered AS6S V6 route parameters through original Lab mark engine."""
from __future__ import annotations
from dataclasses import asdict
import hashlib
import json
import re
import sys
import numpy as np
import pandas as pd
import audit_common as common
import other_assets_replay as ar

START = pd.Timestamp("2026-07-16T00:00:00Z")
END = ar.END
OUT = ar.OUT / "AS6S_V6"
SOURCE = ar.ROOT / "research/asset-portfolios/15m-asset-specific-six-strategy-selector/scripts"
sys.path.insert(0, str(SOURCE))
import as6s_engine as features_engine
import replay_binance_as6s_v6_mark_price_account as mark_engine
import combine_binance_as6s_v6_microtuned_account as account
from combine_hybrid_asset_specific_account import strict_metrics


def plain(value):
    return {k:v for k,v in value.items() if not k.startswith("_")}


def snake(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def load_mark(asset):
    folder = ar.FAMILY / "artifacts/inputs/marks"
    manifest = json.loads((folder / "manifest.json").read_text())
    row = next(row for row in manifest["assets"] if row["asset"] == asset)
    path = folder / f"{asset}_15m.parquet"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
    frame = pd.read_parquet(path)
    frame["ts"] = frame.ts.astype("datetime64[ns, UTC]")
    assert pd.DatetimeIndex(frame.ts).equals(pd.date_range(START, END, freq="15min", inclusive="left"))
    return frame


def add_sentinel(frame, freq):
    last = frame.iloc[-1:].copy()
    last["ts"] = END
    for col in ("open", "high", "low", "close"):
        last[col] = frame.close.iloc[-1]
    return pd.concat([frame, last], ignore_index=True)


def recovery_configs(route):
    configs = []
    legacy = {row["name"]: plain(row) for row in route["legacy"]["legs"]}
    for sleeve in route["sleeves"]:
        audit = {"symbol": sleeve["asset"].upper() + "USDT", "quality": sleeve["quality"], "exposure": sleeve["exposure"]}
        if sleeve["frontier"] is not None:
            config = plain(sleeve["frontier"])
            config["threshold_long"] = config.pop("threshold")
            config["side_mode"] = config["side_mode"].lower()
            config["config_id"] = sleeve["id"].split(":")[-1]
            config["symbol"] = audit["symbol"]
            config["mechanism"] = "trend_state" if sleeve["mechanism"] == "Trend" else sleeve["mechanism"].lower()
            kind = "frontier"
        elif sleeve["clean_rsi"] is not None:
            config = plain(sleeve["clean_rsi"])
            config.pop("max_atr_pct96")  # Python original clean.Config has no such field.
            config.update(h1_confirm=False, rsi14_band=False)
            kind = "clean"
        else:
            config = legacy[sleeve["legacy_leg"]].copy()
            config.pop("asset")
            config.pop("sleeve_priority")
            config["style"] = snake(config["style"])
            config["side_mode"] = config["side_mode"].lower()
            config["exit_kind"] = config["exit_kind"].lower()
            # Fixed sizing means these original Python dataclass slots are inert.
            config.update(roc_threshold_bps=0., sizing_kind="fixed", risk_fraction=.01, max_leverage=1.)
            audit["mechanism"] = config["style"]
            kind = "legacy"
        configs.append((sleeve["id"], kind, audit, config))
    return configs


def equity_rows(trades, frames, funding, start, end, scale=.75):
    balance, cursor = 1., 0
    rows = [{"ts": start, "equity": 1., "closed_balance": 1.}]
    for ts in pd.date_range(start, end, freq="15min", inclusive="left"):
        while cursor < len(trades) and trades[cursor].exit_ts <= ts:
            balance *= 1. + scale * trades[cursor].exposure * trades[cursor].net_return_1x
            cursor += 1
        marked = balance
        if cursor < len(trades):
            trade = trades[cursor]
            if trade.entry_ts <= ts < trade.exit_ts:
                price = float(frames[trade.symbol].loc[ts, "close"])
                rates = funding[trade.symbol]
                accrued = rates.loc[(rates.ts >= trade.entry_ts) & (rates.ts < ts + pd.Timedelta(minutes=15)), "funding_rate"].sum()
                marked = balance * (1. + scale * trade.exposure * (trade.side * (price / trade.entry_price - 1.) - .001 - trade.side * accrued))
        rows.append({"ts": ts + pd.Timedelta(minutes=15), "equity": marked, "closed_balance": balance})
    while cursor < len(trades):
        balance *= 1. + scale * trades[cursor].exposure * trades[cursor].net_return_1x
        cursor += 1
    rows[-1].update(equity=balance, closed_balance=balance)
    curve = pd.DataFrame(rows)
    curve["drawdown"] = curve.equity / curve.equity.cummax() - 1.
    monthly, prev = [], 1.
    for month, group in curve.iloc[1:].groupby((curve.ts.iloc[1:] - pd.Timedelta(nanoseconds=1)).dt.strftime("%Y-%m")):
        value = float(group.equity.iloc[-1])
        monthly.append({"month": month, "return": value / prev - 1., "ending_equity": value})
        prev = value
    return curve, pd.DataFrame(monthly)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # Subnanosecond accounting boundary permits explicit end liquidation while
    # actual entry events are still filtered to the requested [START,END).
    mark_engine.REUSED_END = END + pd.Timedelta(nanoseconds=1)
    account.REUSED_END = END + pd.Timedelta(nanoseconds=1)
    account.RESEARCH_START = START
    recovery = json.loads((ar.OUT / "as6s_recovery.json").read_text())
    for name, expected in recovery["source_pins"].items():
        assert hashlib.sha256(ar.Path(name).read_bytes()).hexdigest() == expected
    raw_by_symbol, frames, marks, funding, h1, engines, prefixes = {}, {}, {}, {}, {}, {}, {}
    clean_context = None
    for asset in ["BTC", "ETH", "SOL", "BNB", "TRX", "HYPE"]:
        symbol = asset + "USDT"
        raw = common.load_prices(asset, "15m").reset_index(drop=True)
        raw_by_symbol[symbol] = raw
        featured = features_engine.add_features(raw)
        featured = featured.loc[(featured.ts >= START) & (featured.ts < END)].reset_index(drop=True)
        frames[symbol] = add_sentinel(featured, "15min")
        marks[symbol] = add_sentinel(load_mark(asset), "15min")
        funding[symbol] = common.load_funding(asset)
        engine = ar.load_module(ar.ENGINE_PATH, f"audit_as6s_{asset}_legacy")
        engines[symbol] = engine
        hour_raw = common.load_prices(asset, "1h").reset_index(drop=True)
        hour_featured = engine.add_features(hour_raw, funding[symbol])
        hour_featured = hour_featured.loc[(hour_featured.ts >= START) & (hour_featured.ts < END)].reset_index(drop=True)
        h1[symbol] = add_sentinel(hour_featured, "1h")
        prefixes[symbol] = engine.funding_prefix(funding[symbol])
        if asset == "HYPE":
            clean = mark_engine.clean
            cf = clean.evolution.add_rsi_features(clean.evolution.add_features(raw[["ts", "open", "high", "low", "close", "volume"]], []))
            cf = cf[(cf.ts >= START) & (cf.ts < END)].reset_index(drop=True)
            # The Rust copy preserves max .028; original Python disabled it.
            # Verify it is inactive on this particular evaluation interval.
            assert (cf.atr_pct96 <= .028).all(), "Clean RSI maximum ATR drift affects this interval"
            cf = add_sentinel(cf, "15min")
            ft, fp = features_engine.funding_arrays(funding[symbol])
            clean_context = {"features": cf, "market": clean.mii.build_market_arrays(cf),
                "mark_open": marks[symbol].open.to_numpy(), "mark_high": marks[symbol].high.to_numpy(), "mark_low": marks[symbol].low.to_numpy(),
                "funding_times": ft, "funding_prefix": fp}
    results = []
    for route_name, route in recovery["routes"].items():
        print(f"Preparing frozen {route_name}", flush=True)
        options, sleeves = {}, []
        recovered = recovery_configs(route)
        ar.write_json(OUT / f"{route_name}_python_configs.json", [{"sleeve":s, "kind":k, "audit":a, "config":c} for s,k,a,c in recovered])
        for sleeve, kind, audit, config in recovered:
            symbol = audit["symbol"]
            if kind == "frontier":
                universe = mark_engine.frontier_universe(sleeve, audit, config, frames[symbol], marks[symbol], funding[symbol])
            elif kind == "clean":
                universe = mark_engine.clean_universe(sleeve, audit, config, frames[symbol], marks[symbol], funding[symbol], prepared_context=clean_context)
            else:
                engine = engines[symbol]
                cfg = engine.StrategyConfig(**config)
                universe = mark_engine.legacy_universe(sleeve, audit, config, engine, cfg, h1[symbol], frames[symbol], marks[symbol], prefixes[symbol])
            universe = {scenario: [t for t in trades if START <= t.entry_ts < END and t.exit_ts <= END] for scenario,trades in universe.items()}
            options[sleeve] = [{"option_id":"frozen", "config":config, "universe":universe}]
            sleeves.append(sleeve)
            print(f"  {sleeve}: {len(universe['base'])} opportunities", flush=True)
        routed = account.route_scenarios(tuple(0 for _ in sleeves), tuple(sleeves), options, mode=route_name, frames=frames, funding=funding)
        for scenario, trades in routed.items():
            metrics = strict_metrics(trades, START, END + pd.Timedelta(nanoseconds=1), .75)
            curve, monthly = equity_rows(trades, {k:v.set_index("ts") for k,v in frames.items()}, funding, START, END)
            assert abs(metrics["total_return"] - float(curve.equity.iloc[-1] - 1.)) < 1e-10
            assert all(a.exit_ts < b.entry_ts for a,b in zip(trades,trades[1:])) or route_name == "strong_breakout_preemptive"
            prefix = f"{route_name}_{scenario}"
            pd.DataFrame([asdict(t) for t in trades]).to_csv(OUT / f"{prefix}_trades.csv", index=False)
            curve.to_csv(OUT / f"{prefix}_equity.csv", index=False)
            monthly.to_csv(OUT / f"{prefix}_monthly.csv", index=False)
            result = {"family":"Binance-15M-AS6S", "version":"V6", "route":route_name, "scenario":scenario,
                "start":START, "end":END, "status":"RECOVERED_RUNNER_COPY_OBSERVED_FUNDING_ESTIMATE",
                "return":metrics["total_return"], "trades":metrics["trades"], "win_rate":metrics["win_rate"],
                "legacy_mae_drawdown":metrics["max_dd"], "close_marked_max_drawdown":float(curve.drawdown.min()),
                "preemptions":metrics["preemptions"], "by_sleeve":metrics["by_sleeve"], "maximum_allocation":max((.75*t.exposure for t in trades), default=0.),
                "terminal_liquidations":sum(t.exit_ts == END for t in trades)}
            results.append(result)
            print(json.dumps(result, default=str), flush=True)
    limitations = ["Original Lab freeze JSON deleted; recovered read-only runner copy has recorded July15 parity evidence, not rerun historical parity", "Original Python mark-trigger, trade-basis fill, stop-first and original funding-rate allocation preserved", "Clean RSI Rust max ATR .028 differs from disabled Python ceiling; verified all evaluation ATR values below .028", "Start flat; signal features prewarmed; first evaluation bar closes before first new order", "Funding event coverage and historical mark-notional cashflow not fully verified", "User requested partial post-registration reveal; this interval is no longer blind"]
    ar.write_json(OUT / "results.json", {"results":results, "limitations":limitations})
    source_pins = {}
    for module in list(sys.modules.values()):
        file = getattr(module,"__file__",None)
        if file:
            path = ar.Path(file).resolve()
            if path.is_relative_to(ar.ROOT / "research") and path.exists():
                source_pins[str(path.relative_to(ar.ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    ar.write_json(OUT / "source_pins.json", source_pins)


if __name__ == "__main__":
    main()
