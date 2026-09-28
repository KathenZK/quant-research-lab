"""Precommitted frequency comparison; only price diagnostics, never zero-filled funding."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_lab.data.funding_v2 import load_funding_v2
from strategy_lab.data.research_bundle import require_research_startup
from mcsm_baseline_accounting_20260908 import LinearPerpAccount
from research_binance_1d_mcsm_lifecycle_20260908 import EXCLUDED
from run_mcsm_baseline_estimate_20260909 import compact_row, load_terminals
from verify_mcsm_baseline_20260908 import FRAME_SHA, load_verified_returned_daily

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
OUT = FAMILY / "artifacts/drawdown-frequency-round-20260911/weekly"
BASE = FAMILY / "artifacts/baseline-estimate-20260909"
START = pd.Timestamp("2020-04-01T00:15:00Z")
END = pd.Timestamp("2026-07-01T00:15:00Z")
DAY = pd.Timedelta(days=1)
MIN15 = pd.Timedelta(minutes=15)
INITIAL = 100_000.
BUNDLE_PATH = "research/platform/data-lake-governance/specs/binance-v3-research-input-bundle-v2.json"
BUNDLE_SHA = "d2a729d03be71d67aa9c5522fb242bbf010b6c64400233c27d9cb2406f567008"
FUND_SHA = "398cc19eac88d0e8c55258c118f6cae2481c6b2d1a5e6253778344b9f25a1076"
HOLD_SHA = "2765cc3fade0b8c571871c5e2bfff88ad6e5bc65198a5fff35e261afa6df61e4"
NATIVE_SHA = "fc57b942e14ab29007256326404c698f379d24988a0da274fe4434b0d9c70990"
KERNEL_SHA = "0445d4e7afa76576558dfd122983dab2c12e523718383f01d45bfc0e2779972c"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        handle.write("\n")


def pin(path, expected):
    if sha(path) != expected:
        raise ValueError(f"frozen input changed: {path}")


def feature_table(daily):
    """At decision 00:00, all 31 bars ending yesterday must be complete and one segment."""
    rows = []
    for symbol, group in daily.sort_values(["symbol", "ts"]).groupby("symbol", sort=True):
        g = group.copy()
        if g.ts.duplicated().any():
            raise ValueError("duplicate daily symbol timestamp")
        valid = g.eligible.eq(True) & np.isfinite(g.close) & g.close.gt(0)
        segment_run = g.research_segment_id.ne(g.research_segment_id.shift()).fillna(True).astype("int64").cumsum()
        g["valid31"] = (valid.rolling(31).sum().eq(31)
                        & g.ts.sub(g.ts.shift(30)).eq(30 * DAY)
                        & segment_run.eq(segment_run.shift(30)))
        g["adv30"] = g.quote_volume.rolling(30, min_periods=30).mean()
        for days in (7, 28):
            g[f"return_{days}"] = g.close.div(g.close.shift(days)).sub(1).where(g.valid31)
        g["decision_ts"] = g.ts + DAY
        g["feature_start_day"] = g.ts - 30 * DAY
        # Known source-confirmed re-launches cannot be crossed even if a provider
        # accidentally leaves a continuous observed identifier.
        for name, launch in (("LIT/USDT:USDT", "2025-12-23T17:30:00Z"),
                             ("AERGO/USDT:USDT", "2025-04-16T11:00:00Z")):
            if symbol == name:
                boundary = pd.Timestamp(launch)
                g.loc[g.feature_start_day.lt(boundary) & g.decision_ts.gt(boundary), "valid31"] = False
        g["qualified"] = (g.valid31 & g.adv30.ge(10_000_000)
                          & (symbol.split("/")[0] not in EXCLUDED))
        rows.append(g[["symbol", "decision_ts", "feature_start_day", "valid31", "adv30",
                       "return_7", "return_28", "qualified"]])
    return pd.concat(rows, ignore_index=True)


def decision_dates(strategy, start=START, end=END):
    if strategy == "M28":
        return pd.date_range(start.floor("D"), end.floor("D") - DAY, freq="MS", tz="UTC")
    if strategy not in {"W28", "W7"}:
        raise ValueError("unknown frequency strategy")
    mondays = pd.date_range(start.floor("D"), end.floor("D") - DAY, freq="W-MON", tz="UTC")
    return pd.DatetimeIndex(sorted(set([start.floor("D"), *mondays])))


def nominate(features, strategy, start=START, end=END, all_candidates=False):
    dates = decision_dates(strategy, start, end)
    scores = "return_7" if strategy == "W7" else "return_28"
    selections, counts = [], []
    for i, day in enumerate(dates):
        pool = features.loc[features.decision_ts.eq(day) & features.qualified].copy()
        pool = pool.loc[np.isfinite(pool[scores])].sort_values(
            [scores, "symbol"], ascending=[False, True])
        counts.append({"strategy": strategy, "decision_ts": day, "qualified_count": len(pool),
                       "status": "TEN_AVAILABLE" if len(pool) >= 10 else "INSUFFICIENT_PREENTRY_NAMES"})
        if len(pool) < 10:
            continue
        chosen = pool if all_candidates else pool.head(10)
        for rank, row in enumerate(chosen.itertuples(index=False), 1):
            selections.append({"strategy": strategy, "decision_ts": day, "entry_ts": day + MIN15,
                               "scheduled_exit_ts": dates[i + 1] + MIN15 if i + 1 < len(dates) else end,
                               "symbol": row.symbol, "rank": rank, "weight": .1,
                               "formation_return": getattr(row, scores), "adv30": row.adv30,
                               "feature_start_day": row.feature_start_day})
    return pd.DataFrame(selections), pd.DataFrame(counts)


def qualify_ranked(ranked, endpoints):
    """The prior bar is closed at execution; no execution-bar values enter selection."""
    prior = {(t, s): bool(e) and bool(v) for t, s, e, v in zip(
        endpoints.ts, endpoints.symbol, endpoints.eligible, endpoints.research_window_valid, strict=True)}
    decisions, selected = [], []
    for (strategy, ts), group in ranked.groupby(["strategy", "decision_ts"], sort=True):
        qualified = []
        for row in group.sort_values("rank").itertuples(index=False):
            key = (ts, row.symbol)
            exists = key in prior
            valid = exists and prior[key]
            decisions.append({"strategy": strategy, "decision_ts": ts, "symbol": row.symbol,
                              "rank": row.rank, "prior_exists": exists, "prior_activity_valid": valid})
            if valid:
                qualified.append(row._asdict())
        if len(qualified) < 10:
            raise ValueError(f"PREENTRY_INSUFFICIENT_ACTIVE {strategy} {ts}: {len(qualified)}")
        selected += qualified[:10]
    return pd.DataFrame(selected), pd.DataFrame(decisions)


def validate_nominations(holdings, start=START, end=END):
    """Missing scheduled decisions cannot masquerade as successful long holds."""
    if set(holdings.strategy) != {"B0", "M28", "W28", "W7"}:
        raise ValueError("INCOMPLETE_DECISION_SCHEDULE_STRATEGY_SET")
    for strategy, h in holdings.groupby("strategy", sort=True):
        expected = (pd.date_range(start.floor("D"), end.floor("D") - DAY, freq="MS", tz="UTC")
                    if strategy == "B0" else decision_dates(strategy, start, end)) + MIN15
        counts = h.groupby("entry_ts").size()
        if set(counts.index) != set(expected) or not counts.eq(10).all():
            raise ValueError(f"INCOMPLETE_DECISION_SCHEDULE {strategy}")
        if h.duplicated(["entry_ts", "symbol"]).any() or not np.allclose(h.weight, .1):
            raise ValueError(f"INVALID_TOP10_WEIGHTS_OR_DUPLICATES {strategy}")


def load_old_endpoints(expected_receipts=None):
    frames, sources = [], []
    catalog_path = BASE / "inputs/catalog-receipt.json"
    pin(catalog_path, "f410516d008d2779fbc49f061cd2b9ba03c55abb5fb30cb18445aff9a9ab2f97")
    catalog = json.loads(catalog_path.read_text())
    pin(BASE / "inputs/global-scoped-audit-request.json", catalog["global_request_sha256"])
    if catalog["audit"]["row_quality"] != "PASS" or catalog["audit"]["gap_policy"] != "contiguous_segments":
        raise ValueError("old scoped audit not qualified")
    bundle = json.loads((ROOT / BUNDLE_PATH).read_text())
    pin(ROOT / BUNDLE_PATH, BUNDLE_SHA)
    for key, value in catalog["verified_components"].items():
        if value["manifest_sha256"] != bundle["components"][key]["manifest_sha256"]:
            raise ValueError("old scoped audit bundle mismatch")
    expected = {x["path"]: x["sha256"] for x in (expected_receipts or [])}
    for day in pd.date_range("2020-03-01", "2026-07-01", freq="MS", tz="UTC"):
        receipt_path = BASE / f"inputs/receipts/execution-{day:%Y%m}.json"
        if expected_receipts is not None:
            name = str(receipt_path.relative_to(ROOT))
            if name not in expected:
                raise ValueError("frozen old endpoint receipt missing")
            pin(receipt_path, expected[name])
        receipt = json.loads(receipt_path.read_text())
        if receipt["global_catalog_receipt"] != "catalog-receipt.json":
            raise ValueError("old endpoint catalog lineage changed")
        for role in ("request", "frame"):
            pin(BASE / "inputs" / receipt[f"{role}_path"], receipt[f"{role}_sha256"])
        f = pd.read_parquet(BASE / "inputs" / receipt["frame_path"])
        f["source_receipt"] = str(receipt_path.relative_to(ROOT))
        frames.append(f)
        sources.append({"path": str(receipt_path.relative_to(ROOT)), "sha256": sha(receipt_path), **receipt})
    result = pd.concat(frames, ignore_index=True)
    if result.duplicated(["symbol", "ts"]).any():
        raise ValueError("duplicate historical endpoint")
    return result, sources


def apply_known_terminals(holdings, terminals):
    h = holdings.copy()
    h["exit_ts"] = h.scheduled_exit_ts
    h["terminal"] = False
    for term in terminals:
        hit = h.symbol.eq(term["symbol"]) & h.entry_ts.lt(term["ts"]) & h.exit_ts.ge(term["ts"])
        h.loc[hit, "exit_ts"] = term["ts"]
        h.loc[hit, "terminal"] = True
    return h


def target_keys(holdings, common_grid):
    rows = []
    for strategy, h in holdings.groupby("strategy", sort=True):
        trade_times = set(h.entry_ts) | {END}
        for ts in common_grid:
            existing = set(h.loc[h.entry_ts.lt(ts) & h.exit_ts.ge(ts), "symbol"])
            incoming = set(h.loc[h.entry_ts.eq(ts), "symbol"])
            for symbol in sorted(existing | incoming):
                for minute_offset in (0, -15):
                    rows.append({"symbol": symbol, "ts": ts + pd.Timedelta(minutes=minute_offset),
                                 "trade_required": ts in trade_times})
    return pd.DataFrame(rows).groupby(["symbol", "ts"], as_index=False).trade_required.max().sort_values(["ts", "symbol"])


def build_requests(needs, old):
    known = set(zip(old.symbol, old.ts, strict=True))
    missing = needs.loc[[(s, t) not in known for s, t in zip(needs.symbol, needs.ts, strict=True)]]
    requests = []
    for year, group in missing.groupby(missing.ts.dt.year, sort=True):
        names = sorted(group.symbol.unique())
        for offset in range(0, len(names), 32):
            chosen = names[offset:offset + 32]
            targets = group.loc[group.symbol.isin(chosen)]
            request = {"schema_version": 1, "bundle_path": BUNDLE_PATH,
                       "bundle_id": "binance.v3.research_inputs.v2", "bundle_sha256": BUNDLE_SHA,
                       "mode": "price_diagnostic", "timeframe": "15m", "symbols": chosen,
                       "start": targets.ts.min().isoformat(), "end": (targets.ts.max() + MIN15).isoformat(),
                       "gap_policy": "contiguous_segments", "asset_policy": "observed_mixed_diagnostic",
                       "backward_bars": 1, "forward_bars": 0}
            requests.append({"label": f"{year}-{offset:03d}", "request": request,
                             "target_keys": [(s, t.isoformat()) for s, t in zip(targets.symbol, targets.ts, strict=True)]})
    return requests


def load_execution(requests, output, old):
    """Consume only frames returned by the actual frozen startup calls."""
    pieces, receipts = [old], []

    def one(item):
        label = item["label"]
        request_path = output / "requests" / f"{label}.json"
        if json.loads(request_path.read_text()) != item["request"]:
            raise ValueError("request not frozen")
        report_path = output / "reports" / f"{label}.json"
        frame_path = output / "returned-targets" / f"{label}.parquet"
        receipt_path = output / "receipts" / f"{label}.json"
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            pin(report_path, receipt["report_sha256"])
            pin(frame_path, receipt["frame_sha256"])
            pin(request_path, receipt["request_sha256"])
            return pd.read_parquet(frame_path), receipt
        print(f"WEEKLY_STARTUP {label} symbols={len(item['request']['symbols'])}", flush=True)
        returned = require_research_startup(item["request"], project_root=ROOT, data_root=ROOT / "data")
        if returned.report["status"] != "PRICE_DIAGNOSTIC_INPUTS_VERIFIED":
            raise ValueError("unexpected startup status")
        targets = {}
        for symbol, ts in item["target_keys"]:
            targets.setdefault(symbol, set()).add(pd.Timestamp(ts))
        f = pd.concat([returned.prices[s].loc[returned.prices[s].ts.isin(times)]
                       for s, times in targets.items()], ignore_index=True)
        if output.name == "qualification":
            f = f[["symbol", "ts", "eligible", "research_window_valid"]].copy()
        f["source_receipt"] = str(receipt_path.relative_to(ROOT))
        save(report_path, returned.report)
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        if frame_path.exists():
            raise FileExistsError(frame_path)
        f.to_parquet(frame_path, index=False)
        receipt = {"label": label, "rows": len(f), "target_count": len(item["target_keys"]),
                   "request_sha256": sha(request_path), "report_sha256": sha(report_path),
                   "frame_sha256": sha(frame_path), "returned_rows": sum(len(x) for x in returned.prices.values())}
        save(receipt_path, receipt)
        del returned
        print(f"WEEKLY_TARGETS_READY {label} found={len(f)}/{len(item['target_keys'])}", flush=True)
        return f, receipt

    with ThreadPoolExecutor(max_workers=2) as executor:
        for frame, receipt in executor.map(one, requests):
            pieces.append(frame)
            receipts.append(receipt)
    result = pd.concat(pieces, ignore_index=True)
    if result.duplicated(["symbol", "ts"]).any():
        raise ValueError("duplicate old/new execution reference")
    return result, receipts


def monthly_summary(nav, holdings, start=START, end=END):
    rows, previous = [], INITIAL
    previous_cash = {"price_pnl": 0., "fees": 0., "slippage": 0.}
    for month in pd.date_range(start.floor("D"), end.floor("D") - DAY, freq="MS", tz="UTC"):
        next_month = month + pd.offsets.MonthBegin(1)
        cutoff = end if next_month == end.floor("D") else next_month
        begin = start if month == start.floor("D") else month
        after = nav.loc[nav.ts.eq(cutoff)]
        if after.empty:
            raise ValueError("missing exact calendar-month valuation")
        last = after.iloc[-1]
        held = holdings.loc[holdings.entry_ts.lt(cutoff) & holdings.exit_ts.gt(begin)]
        initial_names = holdings.loc[holdings.entry_ts.le(begin) & holdings.exit_ts.gt(begin), "symbol"]
        changes = {name: float(last[name]) - previous_cash[name] if name in last.index else np.nan
                   for name in previous_cash}
        rows.append({"month": month, "start_equity": previous, "end_equity": float(last.equity),
                     "pnl_usdt": float(last.equity - previous), "return": float(last.equity / previous - 1),
                     "price_pnl_usdt": changes["price_pnl"], "funding_pnl_usdt": None,
                     "fees_usdt": changes["fees"], "slippage_usdt": changes["slippage"],
                     "account_pnl_identity_error": float(last.equity - previous) - changes["price_pnl"]
                     + changes["fees"] + changes["slippage"],
                     "held_symbols_during_month": ", ".join(sorted(held.symbol.unique())),
                     "month_start_symbols": ", ".join(sorted(initial_names.unique())),
                     "distinct_held_names": held.symbol.nunique(),
                     "rebalances_in_month": holdings.loc[holdings.entry_ts.ge(begin)
                                                           & holdings.entry_ts.lt(cutoff), "entry_ts"].nunique(),
                     "period_start": begin, "period_end": cutoff,
                     "valuation_rule": "calendar 00:00 daily-close marks; initial/final actual 00:15; not realized-only PnL"})
        previous = float(last.equity)
        previous_cash = {name: float(last[name]) if name in last.index else np.nan for name in previous_cash}
    return pd.DataFrame(rows)


def replay_price(holdings, endpoints, daily, terminals, common_grid, slippage, start=START, end=END):
    """One-times fixed-quantity linear-perp price account using immutable arithmetic."""
    account = LinearPerpAccount(INITIAL, fee_rate=.001, slippage_rate=slippage)
    prices = {(t, s): (float(o) if pd.notna(o) else np.nan, bool(e) and bool(v))
              for t, s, o, e, v in zip(endpoints.ts, endpoints.symbol, endpoints.open,
                                      endpoints.eligible, endpoints.research_window_valid, strict=True)}
    marks = {(t, s): (float(c), bool(e)) for t, s, c, e in zip(
        daily.ts, daily.symbol, daily.close, daily.eligible, strict=True)}
    targets = {ts: dict(zip(g.symbol, g.weight, strict=True)) for ts, g in holdings.groupby("entry_ts")}
    targets[end] = {}
    events = [(ts, 0, "daily", None) for ts in pd.date_range(start.floor("D") + DAY, end.floor("D"), freq="D")]
    events += [(t["ts"], 1, "terminal", t) for t in terminals if start < t["ts"] < end]
    events += [(ts, 2, "boundary", None) for ts in common_grid]
    events.sort(key=lambda r: (r[0], r[1]))
    nav, trade_rows, terminal_rows, period_rows = [], [], [], []
    previous_period, previous_equity, previous_turnover = None, INITIAL, None
    for ts, _, kind, payload in events:
        if kind == "daily":
            values = {}
            for symbol in account.positions:
                if (ts - DAY, symbol) not in marks:
                    raise ValueError(f"DAILY_MARK_MISSING {symbol} {ts - DAY}")
                close, eligible = marks[(ts - DAY, symbol)]
                if not eligible or not np.isfinite(close) or close <= 0:
                    raise ValueError(f"DAILY_MARK_INELIGIBLE {symbol} {ts - DAY}")
                values[symbol] = close
            row = account.mark(ts, values)
        elif kind == "terminal":
            if payload["symbol"] not in account.positions:
                continue
            row = account.terminal_close(ts, payload["symbol"], payload["center"],
                                         f"CONDITIONAL:{payload['source_path']}:{payload['source_sha256']}",
                                         settlement_fee_rate=.001, settlement_slippage_rate=0.)
            terminal_rows.append({"ts": ts, **row["details"]})
            account.ledger[-1] = compact_row(account.ledger[-1])
            continue  # Other marks not synchronous; not a NAV point.
        else:
            required = set(account.positions) | set(targets.get(ts, {}))
            values = {}
            for symbol in required:
                if (ts, symbol) not in prices:
                    raise ValueError(f"EXECUTION_OPEN_MISSING {symbol} {ts}")
                current_open, _ = prices[(ts, symbol)]
                if not np.isfinite(current_open) or current_open <= 0:
                    raise ValueError(f"EXECUTION_OPEN_INVALID {symbol} {ts}")
                if ts in targets:
                    if (ts - MIN15, symbol) not in prices:
                        raise ValueError(f"PRIOR_ACTIVITY_MISSING {symbol} {ts}")
                    _, prior_active = prices[(ts - MIN15, symbol)]
                    if not prior_active:
                        raise ValueError(f"PRIOR_ACTIVITY_INELIGIBLE {symbol} {ts}")
                values[symbol] = current_open
            if ts in targets:
                row = account.rebalance(ts, targets[ts], values)
                trade_rows += [{"ts": ts, **trade} for trade in row["details"]["trades"]]
                if previous_period is not None:
                    period_rows.append({"entry_ts": previous_period, "exit_ts": ts,
                                        "start_equity": previous_equity, "end_equity": row["equity"],
                                        "pnl_usdt": row["equity"] - previous_equity,
                                        "return": row["equity"] / previous_equity - 1,
                                        "selected_symbols": ", ".join(sorted(targets[previous_period])),
                                        "entry_traded_notional_usdt": previous_turnover,
                                        "exit_boundary_traded_notional_usdt": row["details"]["traded_notional"],
                                        "holding_days": (ts - previous_period).total_seconds() / 86400,
                                        "short_week": (ts - previous_period) < 7 * DAY})
                previous_period, previous_equity = ts, INITIAL if ts == start else row["equity"]
                previous_turnover = row["details"]["traded_notional"]
            else:
                row = account.mark(ts, values)
        nav.append({"ts": ts, "sample_kind": kind, **compact_row(row)})
        account.ledger[-1] = compact_row(account.ledger[-1])
    if account.positions:
        raise ValueError("uncleared final positions")
    nav = pd.DataFrame(nav)
    months = monthly_summary(nav, holdings, start, end)
    final = account.snapshot()
    equity = np.r_[INITIAL, nav.equity.to_numpy(float)]
    dd = equity / np.maximum.accumulate(equity) - 1
    trough = int(np.argmin(dd))
    peak = int(np.argmax(equity[:trough + 1]))
    times = [start, *nav.ts.tolist()]
    years = []
    for year, group in months.groupby(months.month.dt.year, sort=True):
        years.append({"year": int(year), "start_equity": float(group.start_equity.iloc[0]),
                      "end_equity": float(group.end_equity.iloc[-1]),
                      "return": float(group.end_equity.iloc[-1] / group.start_equity.iloc[0] - 1),
                      "pnl_usdt": float(group.pnl_usdt.sum()), "price_pnl_usdt": float(group.price_pnl_usdt.sum()),
                      "fees_usdt": float(group.fees_usdt.sum()), "slippage_usdt": float(group.slippage_usdt.sum()),
                      "funding_pnl_usdt": None, "months": len(group)})
    metrics = {"status": "COMPLETE_PRICE_DIAGNOSTIC_NOT_FUNDING_NET", "start": start, "end": end,
               "initial_equity": INITIAL, "final_equity": final["equity"],
               "total_return": final["equity"] / INITIAL - 1,
               "cagr_365_25": (final["equity"] / INITIAL) ** (365.25 * 86400 / (end - start).total_seconds()) - 1,
               "max_drawdown_common_grid": float(dd.min()), "drawdown_peak": times[peak], "drawdown_trough": times[trough],
               "fees_usdt": final["fees"], "slippage_usdt": final["slippage"], "price_pnl_usdt": final["price_pnl"],
               "funding_computed": False, "funding_pnl_usdt": None, "fee_rate": .001, "slippage_rate": slippage,
               "rebalances": len(targets) - 1, "monthly_records": len(months), "terminal_closes": len(terminal_rows),
               "cash_identity_error": final["equity"] - INITIAL - final["price_pnl"] + final["fees"] + final["slippage"],
               "yearly": years}
    return {"metrics": metrics, "nav": nav, "monthly": months, "periods": pd.DataFrame(period_rows),
            "trades": pd.DataFrame(trade_rows), "terminals": pd.DataFrame(terminal_rows)}


def priced_windows(holdings, endpoints, terminals):
    opens = {(ts, s): float(p) for ts, s, p in zip(endpoints.ts, endpoints.symbol, endpoints.open, strict=True)
             if pd.notna(p) and np.isfinite(p) and p > 0}
    terminal_map = {(t["ts"], t["symbol"]): t["center"] for t in terminals}
    rows = []
    for h in holdings.to_dict("records"):
        begin = opens.get((h["entry_ts"], h["symbol"]), np.nan)
        end = terminal_map.get((h["exit_ts"], h["symbol"]), opens.get((h["exit_ts"], h["symbol"]), np.nan))
        valid = np.isfinite(begin) and np.isfinite(end)
        rows.append({**h, "entry_reference_price": begin, "exit_reference_price": end,
                     "gross_price_return": end / begin - 1 if valid else np.nan,
                     "endpoint_status": "BOTH_REFERENCE_PRICES_AVAILABLE" if valid else "LABEL_UNAVAILABLE",
                     "is_funding_net_return": False})
    return pd.DataFrame(rows)


def baseline_adapter_recheck(endpoints, daily, terminals, output):
    """Reproduce the original 76-month B0 only; S1 is not this adapter's event model."""
    original_path = BASE / "inputs-identity-corrected/holdings.parquet"
    pin(original_path, HOLD_SHA)
    h = pd.read_parquet(original_path)
    h["scheduled_exit_ts"] = h.month + pd.offsets.MonthBegin(1) + MIN15
    start = pd.Timestamp("2020-03-01T00:15:00Z")
    grid = list(pd.date_range(start.floor("D"), END.floor("D"), freq="MS", tz="UTC") + MIN15)
    reproduced = replay_price(h, endpoints, daily, terminals, grid, .0004, start=start)
    old_path = BASE / "accounts/price_only/nav.parquet"
    original = pd.read_parquet(old_path)
    got = reproduced["nav"]
    if len(got) != len(original) or got.ts.tolist() != original.ts.tolist():
        raise ValueError("B0 adapter observation timestamps differ")
    errors = {}
    for name in ("equity", "price_pnl", "funding_pnl", "fees", "slippage"):
        errors[name] = float(np.max(np.abs(got[name].to_numpy(float) - original[name].to_numpy(float))))
        if not np.allclose(got[name].to_numpy(float), original[name].to_numpy(float), rtol=1e-10, atol=1e-6):
            raise ValueError(f"B0 adapter numerical disagreement: {name}")
    summary = {"status": "PASS_ORIGINAL_B0_76_MONTH_PRICE_ADAPTER", "nav_rows": len(got),
               "max_abs_errors": errors, "source_nav_sha256": sha(old_path),
               "final_equity": reproduced["metrics"]["final_equity"],
               "total_return": reproduced["metrics"]["total_return"],
               "S1_reproduced_by_this_adapter": False,
               "S1_note": "This frequency adapter has no discretionary single-exit event and does not claim S1 reproduction.",
               "monthly_reporting_changed_to_calendar_not_claimed_identical": True}
    save(output / "b0-original-adapter-recheck.json", summary)
    return summary


def funding_availability_flags(events, native):
    """The old native_mark column is legacy: use the reviewed source and center."""
    native_proven = native.mark_source.eq("RECHECKED_OFFICIAL_NATIVE_SETTLEMENT_MARK") & native.mark_center.gt(0)
    native_ids = set(native.loc[native_proven, "event_id"])
    flags = events.copy()
    flags["old_monthly_estimate_available"] = flags.event_id.isin(set(native.event_id))
    flags["native_settlement_mark_available"] = flags.event_id.isin(native_ids) | flags.mark_price.gt(0)
    return flags, int(native_proven.sum())


def funding_coverage(holdings, output):
    """Count observed events and proved calendar spans, not a funding net account."""
    data = load_funding_v2(ROOT / "data/derived/datasets/binance_perp_funding_v3_inputs_v2",
                           expected_manifest_sha256=FUND_SHA)
    native_path = FAMILY / "artifacts/funding-recheck-20260910/native-replay/native-priority-events.parquet"
    pin(native_path, NATIVE_SHA)
    native = pd.read_parquet(native_path)
    events, native_count = funding_availability_flags(data.events, native)
    if native_count != 3695:
        raise ValueError("frozen rechecked native-mark count changed")
    grouped = {s: g.sort_values("ts") for s, g in events.groupby("symbol", sort=False)}
    rows = []
    for h in holdings.itertuples(index=False):
        g = grouped.get(h.symbol)
        if g is None:
            event_count = old_count = marks = 0
        else:
            left, right = g.ts.searchsorted(h.entry_ts, side="right"), g.ts.searchsorted(h.exit_ts, side="right")
            selected = g.iloc[left:right]
            event_count = len(selected)
            old_count = int(selected.old_monthly_estimate_available.sum())
            marks = int(selected.native_settlement_mark_available.sum())
        spans = data.segments.loc[data.segments.symbol.eq(h.symbol)
                                 & data.segments.start.le(h.entry_ts) & data.segments.end.ge(h.exit_ts)]
        # Matching a span is still not an accepted identity review or net gate.
        rows.append({"strategy": h.strategy, "symbol": h.symbol, "entry_ts": h.entry_ts, "exit_ts": h.exit_ts,
                     "observed_events": event_count, "events_with_old_monthly_estimate": old_count,
                     "events_with_known_native_mark": marks, "calendar_span_contains_window": len(spans) == 1,
                     "exact_funding_net_computed": False})
    table = pd.DataFrame(rows)
    table.to_csv(output / "funding-window-coverage.csv", index=False)
    summary = {"status": "OBSERVED_EVENT_COVERAGE_ONLY_NOT_NET_APPROVAL", "manifest_sha256": FUND_SHA,
               "old_native_priority_sha256": NATIVE_SHA, "no_network": True,
               "native_priority_source_confirmed_mark_events": native_count,
               "legacy_native_mark_column_not_used": True,
               "no_missing_rate_or_mark_zero_fill": True, "no_new_mark_trade_price_proxy": True,
               "scope": "native mark count from pinned old replay and funding snapshot only; not an exhaustive raw-file rescan",
               "strategies": table.groupby("strategy").agg(windows=("symbol", "size"),
                    observed_events=("observed_events", "sum"), old_estimate_events=("events_with_old_monthly_estimate", "sum"),
                    native_mark_events=("events_with_known_native_mark", "sum"),
                    calendar_contained_windows=("calendar_span_contains_window", "sum")).reset_index().to_dict("records")}
    save(output / "funding-coverage-summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--phase", choices=("plan", "qualify", "execute"), required=True)
    args = parser.parse_args()
    pin(args.contract, args.contract_sha256)
    pin(FAMILY / "scripts/mcsm_baseline_accounting_20260908.py", KERNEL_SHA)
    output = args.output
    if args.phase == "plan":
        if output.exists() and any(not p.name.startswith("implementation-failure-") for p in output.iterdir()):
            raise FileExistsError(output)
        output.mkdir(parents=True, exist_ok=True)
        daily = load_verified_returned_daily()
        features = feature_table(daily)
        pieces, counts = [], []
        for strategy in ("M28", "W28", "W7"):
            h, c = nominate(features, strategy, all_candidates=True)
            pieces.append(h)
            counts.append(c)
        base_path = BASE / "inputs-identity-corrected/holdings.parquet"
        pin(base_path, HOLD_SHA)
        base = pd.read_parquet(base_path)
        base = base.loc[base.entry_ts.ge(START)].copy()
        base["strategy"] = "B0"
        base["decision_ts"] = base.entry_ts - MIN15
        base["scheduled_exit_ts"] = base.month + pd.offsets.MonthBegin(1) + MIN15
        base["feature_start_day"] = pd.NaT
        base[pieces[0].columns].to_parquet(output / "b0-nominations.parquet", index=False)
        ranked = pd.concat(pieces, ignore_index=True)
        ranked.to_parquet(output / "ranked-candidates.parquet", index=False)
        count_table = pd.concat(counts, ignore_index=True)
        count_table.to_csv(output / "preentry-counts.csv", index=False)
        if not count_table.status.eq("TEN_AVAILABLE").all():
            raise ValueError("PREENTRY_QUALIFIED_POOL_INSUFFICIENT_NO_SILENT_SKIPPED_PERIOD")
        save(output / "nomination-freeze.json", {"created_at": pd.Timestamp.now(tz="UTC"),
             "contract_path": str(args.contract), "contract_sha256": args.contract_sha256,
             "script_sha256": sha(Path(__file__)), "daily_sha256": FRAME_SHA, "kernel_sha256": KERNEL_SHA,
             "ranked_candidates_sha256": sha(output / "ranked-candidates.parquet"),
             "b0_nominations_sha256": sha(output / "b0-nominations.parquet"),
             "preentry_counts_sha256": sha(output / "preentry-counts.csv"), "future_prices_read": False,
             "start": START, "end": END, "unseen_oos": False})
        needs = ranked[["symbol", "decision_ts"]].rename(columns={"decision_ts": "ts"}).drop_duplicates()
        needs["trade_required"] = True
        old, receipts = load_old_endpoints()
        requests = build_requests(needs, old)
        for item in requests:
            save(output / "qualification" / "requests" / f"{item['label']}.json", item["request"])
        save(output / "qualification-plan.json", {"requests": requests, "old_receipts": receipts,
             "nomination_freeze_sha256": sha(output / "nomination-freeze.json"), "prior_target_keys": len(needs),
             "future_returns_computed": False})
        print({"status": "PAST_QUALIFICATION_REQUESTS_FROZEN", "requests": len(requests),
               "prior_target_keys": len(needs), "candidate_strategy_rows": len(ranked)}, flush=True)
        return
    frozen = json.loads((output / "nomination-freeze.json").read_text())
    if frozen["contract_sha256"] != args.contract_sha256:
        raise ValueError("contract differs from frozen plan")
    pin(output / "ranked-candidates.parquet", frozen["ranked_candidates_sha256"])
    pin(output / "b0-nominations.parquet", frozen["b0_nominations_sha256"])
    if args.phase == "qualify":
        qualification_plan = json.loads((output / "qualification-plan.json").read_text())
        pin(output / "nomination-freeze.json", qualification_plan["nomination_freeze_sha256"])
        old, old_receipts = load_old_endpoints(qualification_plan["old_receipts"])
        endpoints, receipts = load_execution(qualification_plan["requests"], output / "qualification", old)
        ranked = pd.read_parquet(output / "ranked-candidates.parquet")
        selected, decisions = qualify_ranked(ranked, endpoints)
        decisions.to_parquet(output / "prior-activity-decisions.parquet", index=False)
        nominations = pd.concat([selected, pd.read_parquet(output / "b0-nominations.parquet")], ignore_index=True)
        validate_nominations(nominations)
        nominations.to_parquet(output / "nominations.parquet", index=False)
        save(output / "qualified-nomination-freeze.json", {"created_at": pd.Timestamp.now(tz="UTC"),
             "nominations_sha256": sha(output / "nominations.parquet"),
             "prior_activity_decisions_sha256": sha(output / "prior-activity-decisions.parquet"),
             "qualification_plan_sha256": sha(output / "qualification-plan.json"),
             "receipts": receipts, "future_holding_labels_examined": False})
        holdings = apply_known_terminals(nominations, load_terminals())
        holdings.to_parquet(output / "holding-windows.parquet", index=False)
        holdings.to_csv(output / "holding-windows.csv", index=False)
        grid = sorted(set(holdings.entry_ts) | set(pd.date_range(START.floor("D"), END.floor("D"), freq="MS", tz="UTC") + MIN15) | {END})
        needs = target_keys(holdings, grid)
        needs.to_parquet(output / "target-keys.parquet", index=False)
        requests = build_requests(needs, endpoints)
        for item in requests:
            save(output / "requests" / f"{item['label']}.json", item["request"])
        save(output / "execution-plan.json", {"requests": requests, "common_grid": grid,
             "old_receipts": old_receipts, "holding_windows_sha256": sha(output / "holding-windows.parquet"),
             "target_keys_sha256": sha(output / "target-keys.parquet"),
             "nomination_freeze_sha256": sha(output / "nomination-freeze.json"),
             "new_requests": len(requests), "target_keys": len(needs), "future_returns_computed": False})
        print({"status": "PLANS_FROZEN_NO_NEW_RETURNS", "requests": len(requests), "target_keys": len(needs)}, flush=True)
        return
    selected_freeze = json.loads((output / "qualified-nomination-freeze.json").read_text())
    pin(output / "nominations.parquet", selected_freeze["nominations_sha256"])
    plan = json.loads((output / "execution-plan.json").read_text())
    pin(output / "holding-windows.parquet", plan["holding_windows_sha256"])
    pin(output / "nomination-freeze.json", plan["nomination_freeze_sha256"])
    holdings = pd.read_parquet(output / "holding-windows.parquet")
    validate_nominations(holdings)
    old, _ = load_old_endpoints(plan["old_receipts"])
    execution_started = output / "execution-started.json"
    if not execution_started.exists():
        save(execution_started, {"created_at": pd.Timestamp.now(tz="UTC"),
             "script_sha256": sha(Path(__file__)), "contract_sha256": args.contract_sha256,
             "execution_plan_sha256": sha(output / "execution-plan.json"),
             "qualified_nominations_sha256": sha(output / "qualified-nomination-freeze.json"),
             "new_frequency_returns_computed": False, "pandas_version": pd.__version__,
             "numpy_version": np.__version__})
    execution_pin = json.loads(execution_started.read_text())
    pin(Path(__file__), execution_pin["script_sha256"])
    pin(output / "execution-plan.json", execution_pin["execution_plan_sha256"])
    if not (output / "implementation-guard-qa.json").exists():
        save(output / "implementation-guard-qa.json", {
            "status": "PASS_BEFORE_NEW_ACCOUNT_RETURNS", "complete_decision_schedules": True,
            "strategy_leg_counts": holdings.groupby("strategy").size().to_dict(),
            "old_endpoint_receipts_matched_prefrozen_hashes": len(plan["old_receipts"]),
            "catalog_receipt_sha256": sha(BASE / "inputs/catalog-receipt.json"),
            "script_sha256": sha(Path(__file__)), "changes": [
                "Fail closed on missing strategy or predetermined decision, non-ten baskets or invalid weights.",
                "Pin old receipt bytes to prequalification plan and bind global catalog lineage.",
                "Use tuple-key indices as a value-preserving representation optimization."],
            "strategy_rules_changed": False})
    qualification_plan = json.loads((output / "qualification-plan.json").read_text())
    prior, _ = load_execution(qualification_plan["requests"], output / "qualification", old)
    endpoints, receipts = load_execution(plan["requests"], output, prior)
    if not (output / "endpoint-summary.json").exists():
        save(output / "endpoint-summary.json", {"receipts": receipts, "endpoint_rows": len(endpoints)})
    daily = load_verified_returned_daily()
    terminals = load_terminals()
    priced = priced_windows(holdings, endpoints, terminals)
    if not (output / "priced-holding-windows.parquet").exists():
        priced.to_parquet(output / "priced-holding-windows.parquet", index=False)
    if not (output / "b0-original-adapter-recheck.json").exists():
        baseline_adapter_recheck(endpoints, daily, terminals, output)
    grid = [pd.Timestamp(t) for t in plan["common_grid"]]
    results = []
    for strategy, h in holdings.groupby("strategy", sort=True):
        for slippage in (.0004, .0008):
            label = f"{strategy}-{round(slippage * 10000)}bp"
            directory = output / label
            if directory.exists():
                result = json.loads((directory / "summary.json").read_text())
                results.append(result)
                continue
            directory.mkdir()
            try:
                result = replay_price(h, endpoints, daily, terminals, grid, slippage)
            except (ValueError, KeyError) as exc:
                summary = {"strategy": strategy, "slippage_rate": slippage,
                           "status": "ACCOUNT_REPLAY_BLOCKED_MISSING_INPUT_NO_SKIP", "reason": str(exc),
                           "total_return": None, "max_drawdown_common_grid": None}
                save(directory / "summary.json", summary)
            else:
                summary = {"strategy": strategy, **result.pop("metrics")}
                leg_prices = priced.loc[priced.strategy.eq(strategy)].copy()
                quantities = result["trades"].set_index(["ts", "symbol"]).new_quantity.to_dict()
                leg_prices["account_entry_quantity"] = [quantities[(ts, s)] for ts, s in zip(
                    leg_prices.entry_ts, leg_prices.symbol, strict=True)]
                leg_prices["period_price_pnl_usdt"] = (leg_prices.exit_reference_price - leg_prices.entry_reference_price) * leg_prices.account_entry_quantity
                result["leg-price-pnl"] = leg_prices
                for name, frame in result.items():
                    frame.to_parquet(directory / f"{name}.parquet", index=False)
                    if name in ("monthly", "periods"):
                        frame.to_csv(directory / f"{name}.csv", index=False)
                save(directory / "summary.json", summary)
            results.append(summary)
            print({"strategy": label, **summary}, flush=True)
    if not (output / "funding-coverage-summary.json").exists():
        funding_coverage(holdings, output)
    pin(Path(__file__), execution_pin["script_sha256"])
    save(output / "summary.json", {"status": "PRICE_FREQUENCY_ROUND_COMPLETED_WITH_EXPLICIT_COVERAGE", "accounts": results,
         "contract_sha256": args.contract_sha256, "plan_script_sha256": frozen["script_sha256"],
         "execution_script_sha256": sha(Path(__file__)), "nomination_freeze_sha256": sha(output / "nomination-freeze.json"),
         "common_grid_points": len(grid), "no_funding_net_claim": True, "no_network": True,
         "funding_coverage_sha256": sha(output / "funding-coverage-summary.json")})


if __name__ == "__main__":
    main()
