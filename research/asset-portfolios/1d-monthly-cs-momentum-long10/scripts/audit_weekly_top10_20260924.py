"""Independent direct-window ranking, raw terminal index, and complete cash checks."""
from __future__ import annotations

import csv
from decimal import Decimal
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

from audit_mcsm_funding_account_bridge_20260910 import terminals_from_raw
from audit_mcsm_weekly_account_20260911 import (
    calendar_months, compare_numeric, independent_leg_cash, independent_replay,
)
from research_binance_1d_mcsm_lifecycle_20260908 import EXCLUDED
from complete_weekly_top10_20260924 import OUT, PRIOR, validate_prior
from research_weekly_top10_20260924 import END, FAMILY, ROOT, START, load_inputs
from research_mcsm_weekly_20260911 import pin, save, sha

DAY_NS = 86_400_000_000_000


def direct_ranking(daily, endpoints, holdings):
    """No candidate rolling features or rank function: exact past rows only."""
    dates = sorted(holdings.loc[holdings.strategy.eq("W7"), "decision_ts"].unique())
    pools = {d: [] for d in dates}
    prior = {(s, t): bool(e) and bool(v) for s, t, e, v in zip(
        endpoints.symbol, endpoints.ts, endpoints.eligible, endpoints.research_window_valid)}
    for symbol, raw in daily.groupby("symbol", sort=True):
        if symbol.split("/")[0] in EXCLUDED:
            continue
        g = raw.sort_values("ts")
        time = g.ts.to_numpy(dtype="datetime64[ns]").astype(np.int64)
        close = g.close.to_numpy(float)
        volume = g.quote_volume.to_numpy(float)
        valid = g.eligible.to_numpy(bool) & np.isfinite(close) & (close > 0)
        segments = g.research_segment_id.to_numpy()
        boundaries = {"LIT/USDT:USDT": pd.Timestamp("2025-12-23T17:30Z"),
                      "AERGO/USDT:USDT": pd.Timestamp("2025-04-16T11:00Z")}
        for day in dates:
            end = int(day.value) - DAY_NS
            j = int(np.searchsorted(time, end))
            if j >= len(time) or time[j] != end or j < 30:
                continue
            window = slice(j - 30, j + 1)
            if (not valid[window].all() or not np.array_equal(time[window], np.arange(end - 30 * DAY_NS, end + 1, DAY_NS))
                    or not (segments[window] == segments[j]).all()):
                continue
            boundary = boundaries.get(symbol)
            if boundary is not None and end - 30 * DAY_NS < boundary.value < day.value:
                continue
            adv = float(np.mean(volume[j - 29:j + 1]))
            if not np.isfinite(adv) or adv < 10_000_000 or not prior.get((symbol, day), False):
                continue
            score = close[j] / close[j - 7] - 1
            pools[day].append((float(score), symbol))
    for day, pool in pools.items():
        expected = [s for _, s in sorted(pool, key=lambda row: (-row[0], row[1]))[:10]]
        actual = holdings.loc[holdings.strategy.eq("W7") & holdings.decision_ts.eq(day), "symbol"].tolist()
        if len(expected) != 10 or expected != actual:
            raise ValueError(f"weekly direct ranking differs: {day}, {expected}, {actual}")
    return {"weekly_decisions": len(dates), "weekly_slots": len(dates) * 10,
            "every_nomination_matches_independent_past_rows": True}


def raw_terminal_values():
    old, source_pins = terminals_from_raw()
    result = {k: {"center": v["estimated_center"], "low": v["estimated_adverse"], "high": v["estimated_favorable"]}
              for k, v in old.items()}
    events = []
    for directory in [PRIOR, OUT]:
        record = json.loads((directory / "terminal-evidence/summary.json").read_text())
        events.extend(record["events"])
    for event in events:
        source = FAMILY / event["source_path"]
        pin(source, event["source_sha256"])
        if source.suffix == ".zip":
            with zipfile.ZipFile(source) as z:
                rows = list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())))
            checksum = source.with_name(source.name + ".CHECKSUM")
            assert checksum.read_text().split()[0] == sha(source)
        else:
            rows = json.loads(source.read_text())
        end = pd.Timestamp(event["ts"])
        minutes = 30 if event["symbol"] == "MEMEFI/USDT:USDT" else 60
        assert event["minute_count"] == minutes
        target = list(range(int((end - pd.Timedelta(minutes=minutes)).timestamp() * 1000), int(end.timestamp() * 1000), 60000))
        selected = [r for r in rows if str(r[0]).isdigit() and int(r[0]) in set(target)]
        assert [int(r[0]) for r in selected] == target
        assert all(int(r[6]) == int(r[0]) + 59999 for r in selected)
        ohlc = [[Decimal(str(v)) for v in r[1:5]] for r in selected]
        assert all(all(v.is_finite() and v > 0 for v in r) and r[2] == min(r) and r[1] == max(r) for r in ohlc)
        center = float(sum(sum(r) for r in ohlc) / Decimal(minutes * 4))
        low, high = float(sum(r[2] for r in ohlc) / Decimal(minutes)), float(sum(r[1] for r in ohlc) / Decimal(minutes))
        for kind, value in [("center", center), ("low", low), ("high", high)]:
            assert np.isclose(event[kind], value, rtol=1e-13, atol=1e-13)
        result[(event["symbol"], end)] = {"center": center, "low": low, "high": high}
        source_pins[str(source.relative_to(ROOT))] = sha(source)
    return result, source_pins


def main():
    validate_prior()
    summary = json.loads((OUT / "summary.json").read_text())
    for name, digest in summary["files_sha256"].items():
        pin(OUT / name, digest)
    plan = json.loads((OUT / "plan.json").read_text())
    h = pd.read_parquet(OUT / "holding-windows.parquet")
    prior_h = pd.read_parquet(PRIOR / "holding-windows.parquet")
    fixed = ["strategy", "decision_ts", "entry_ts", "scheduled_exit_ts", "symbol", "weight"]
    pd.testing.assert_frame_equal(h[fixed], prior_h[fixed])
    base, daily, endpoints, _, _, _ = load_inputs()
    ranking = direct_ranking(daily, endpoints, h)
    months = h.loc[h.strategy.eq("B0")]
    original = base.loc[base.entry_ts.ge(START)]
    assert list(zip(months.entry_ts, months.symbol)) == list(zip(original.entry_ts, original.symbol))
    terminals, terminal_pins = raw_terminal_values()
    for r in h.itertuples(index=False):
        relevant = [t for (s, t) in terminals if s == r.symbol and r.entry_ts < t <= r.scheduled_exit_ts]
        cutoff = min([r.scheduled_exit_ts, *relevant])
        assert cutoff == r.exit_ts and bool(r.terminal) == bool(relevant)
    print(json.dumps(ranking), flush=True)
    results = []
    prescribed = {(v, scenario, slip) for v in ["B0", "W7"] for scenario in ["center", "low", "high"]
                  for slip in ([.0004, .0008] if scenario == "center" else [.0004])}
    assert len(summary["accounts"]) == 8
    assert {(r["strategy"], r["terminal_scenario"], r["slippage_rate"]) for r in summary["accounts"]} == prescribed
    for metric in summary["accounts"]:
        strategy, scenario, slip = metric["strategy"], metric["terminal_scenario"], metric["slippage_rate"]
        label = f"{strategy}-{scenario}-{round(slip * 10000)}bp"
        folder = OUT / label
        values = {k: v[scenario] for k, v in terminals.items()}
        held = h.loc[h.strategy.eq(strategy)]
        found = independent_replay(held, endpoints, daily, values, plan["common_grid"], slip, start=START, end=END)
        if found["failure"] is not None:
            assert metric["total_return"] is None
            results.append({"account": label, "status": "CONFIRMED_BLOCKED", "failure": found["failure"]})
            continue
        assert metric["status"] == "CONDITIONAL_TERMINAL_ESTIMATE_PRICE_ONLY_NOT_VERIFIED_NET" and not found["remaining_positions"]
        original_nav = pd.read_parquet(folder / "nav.parquet")
        nav = found["nav"]
        assert original_nav.ts.tolist() == nav.ts.tolist()
        assert original_nav.sample_kind.tolist() == nav.sample_kind.tolist()
        errors = compare_numeric(original_nav, nav, ["ts"], ["equity", "price_pnl", "fees", "slippage", "gross_notional"], label)
        errors["trades"] = compare_numeric(pd.read_parquet(folder / "trades.parquet"), found["trades"], ["ts", "symbol"],
                                           ["old_quantity", "new_quantity", "reference_price", "traded_notional", "fee", "slippage"], label)
        legs = independent_leg_cash(held, found["trades"], endpoints, values)
        errors["legs"] = compare_numeric(pd.read_parquet(folder / "leg-price-pnl.parquet"), legs, ["entry_ts", "symbol"],
                                         ["account_entry_quantity", "entry_reference_price", "exit_reference_price", "period_price_pnl_usdt"], label)
        monthly = calendar_months(nav, start=START, end=END)
        errors["monthly"] = compare_numeric(pd.read_parquet(folder / "monthly.parquet"), monthly, ["month"],
                                            ["start_equity", "end_equity", "pnl_usdt", "return", "fees_usdt", "slippage_usdt"], label)
        assert len(monthly) == 73
        e = np.r_[100000., nav.equity.to_numpy(float)]
        mdd = float((e / np.maximum.accumulate(e) - 1).min())
        assert np.isclose(mdd, metric["max_drawdown_common_grid"], rtol=1e-11, atol=1e-12)
        assert np.isclose(e[-1], metric["final_equity"], rtol=1e-11, atol=1e-6)
        assert np.isclose((1 + monthly["return"]).prod(), e[-1] / 100000., rtol=1e-11)
        for year in metric["yearly"]:
            y = monthly.loc[monthly.month.dt.year.eq(year["year"])]
            assert np.isclose(year["return"], y.end_equity.iloc[-1] / y.start_equity.iloc[0] - 1, rtol=1e-11, atol=1e-12)
            assert np.isclose(year["pnl_usdt"], y.pnl_usdt.sum(), rtol=1e-11, atol=1e-6)
        periods = pd.read_parquet(folder / "periods.parquet")
        assert np.isclose((1 + periods["return"]).prod(), e[-1] / 100000., rtol=1e-11)
        assert len(periods) == (73 if strategy == "B0" else 318)
        assert metric["funding_computed"] is False and metric["funding_pnl_usdt"] is None
        if len(found["terminals"]):
            errors["terminals"] = compare_numeric(pd.read_parquet(folder / "terminals.parquet"), found["terminals"], ["ts", "symbol"],
                                                  ["quantity", "settlement_price", "fee"], label)
        result = {"account": label, "status": "PASS_INDEPENDENT_CASH_AND_REPORTING", "nav_rows": len(nav),
                  "trades": len(found["trades"]), "legs": len(legs), "months": len(monthly), "periods": len(periods),
                  "final_equity": float(e[-1]), "max_drawdown": mdd, "max_absolute_errors": errors}
        results.append(result)
        print(json.dumps({k: v for k, v in result.items() if k != "max_absolute_errors"}), flush=True)
    save(OUT / "independent-audit.json", {"status": "ALL_8_SCENARIOS_INDEPENDENTLY_CHECKED", "ranking": ranking,
                                         "results": results, "terminal_raw_pins": terminal_pins,
                                         "summary_sha256": sha(OUT / "summary.json"), "audit_script_sha256": sha(Path(__file__))})


if __name__ == "__main__":
    main()
