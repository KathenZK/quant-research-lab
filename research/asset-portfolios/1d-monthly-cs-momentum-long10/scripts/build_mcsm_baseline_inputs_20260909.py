"""原月度 Top10 的独立 explore 输入/名单复原；不计算账户收益。"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

LAB = Path(__file__).resolve().parents[4]
FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "src"))

from strategy_lab.data.catalog import DatasetScope, load_trusted_research_dataset, read_verified_ohlcv, require_passing_trusted
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.research_bundle import read_bundle_contract, validate_price_frame, verify_bundle_files
from strategy_lab.data.research_inputs import segment_research_bars, complete_window_mask

OUT = FAMILY / "artifacts/baseline-estimate-20260909/inputs"
OLD = FAMILY / "artifacts/lifecycle-inputs-20260908"
TERMINALS = FAMILY / "artifacts/baseline-verification-20260908/terminal-evidence/final-review.json"
FRAME_SHA = "3565255edeafcdc5dd3083191b820d2302f993e4ac89679bd812e43601e7049a"
TERMINAL_SHA = "f735e3f11941ff01d7a65cc2db1a1e6dde2265d098ace0599ee47e694f354af6"
PIN = {"bundle_path": "research/platform/data-lake-governance/specs/binance-v3-research-input-bundle-v2.json",
       "bundle_id": "binance.v3.research_inputs.v2",
       "bundle_sha256": "d2a729d03be71d67aa9c5522fb242bbf010b6c64400233c27d9cb2406f567008"}
START = pd.Timestamp("2020-01-01T00:00:00Z")
END = pd.Timestamp("2026-07-01T00:30:00Z")
MONTHS = pd.date_range("2020-03-01", "2026-06-01", freq="MS", tz="UTC")
EXCLUDED = {"USDC", "BUSD", "TUSD", "USDP", "FDUSD", "DAI", "SUSD", "EUR", "AEUR",
            "GBP", "AUD", "BRL", "USD1", "USDE", "XUSD", "BFUSD", "BLUEBIRD", "DOTECO", "FOOTBALL"}
COLS = ["ts", "symbol", "open", "high", "low", "close", "volume", "quote_volume", "trade_count",
        "is_closed", "observed_valid", "identity_verified", "eligible", "research_segment_id", "research_window_valid"]


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, default=str, allow_nan=False)
        handle.write("\n")


def load_returned_daily() -> tuple[pd.DataFrame, dict]:
    summary = json.loads((OLD / "summary.json").read_text())
    if sha(OLD / "daily-returned-frames.parquet") != FRAME_SHA or summary["parquet_sha256"] != FRAME_SHA:
        raise ValueError("Same-family returned daily projection changed")
    if summary["returned_symbols"] != 874 or not summary["all_requested_symbols_passed"]:
        raise ValueError("Prior returned symbol coverage incomplete")
    for relative, digest in summary["source_sha256"].items():
        if sha(LAB / relative) != digest:
            raise ValueError(f"Prior source pin changed: {relative}")
    for receipt in summary["startup_receipts"]:
        for role in ("request", "report"):
            if sha(OLD / receipt[f"{role}_path"]) != receipt[f"{role}_sha256"]:
                raise ValueError("Prior startup receipt changed")
    return pd.read_parquet(OLD / "daily-returned-frames.parquet"), summary


def load_terminals() -> tuple[dict, dict]:
    if sha(TERMINALS) != TERMINAL_SHA:
        raise ValueError("Reviewed terminal evidence changed")
    document = json.loads(TERMINALS.read_text())
    events = {}
    for event in document["events"]:
        cms = FAMILY / event["official_cms_path"]
        if sha(cms) != event["official_cms_sha256"]:
            raise ValueError("Official terminal announcement content changed")
        symbol = event["symbol"][:-4] + "/USDT:USDT"
        events[symbol] = event
    return events, document


def request(symbols: list[str], start: pd.Timestamp, end: pd.Timestamp) -> dict:
    if not START <= start < end <= END:
        raise ValueError("Scoped request escapes globally audited frozen range")
    return {"schema_version": 1, **PIN, "mode": "price_diagnostic", "timeframe": "15m",
            "symbols": sorted(symbols), "start": start.isoformat(), "end": end.isoformat(),
            "gap_policy": "contiguous_segments", "asset_policy": "observed_mixed_diagnostic",
            "backward_bars": 1, "forward_bars": 0}


def supplement_plan(daily: pd.DataFrame) -> pd.DataFrame:
    records = []
    for symbol, group in daily.groupby("symbol", sort=True):
        times = pd.DatetimeIndex(group.ts.sort_values())
        first_prior, last_next = times[0] - pd.Timedelta(days=1), times[-1] + pd.Timedelta(days=1)
        for day, reason in ((first_prior, "BEFORE_FIRST_FULL_DAY_MONTHEND"), (last_next, "AFTER_LAST_FULL_DAY_MONTHEND")):
            if day.is_month_end and START <= day < END - pd.Timedelta(days=1):
                records.append({"symbol": symbol, "day": day, "reason": reason})
        missing = pd.date_range(times[0], times[-1], freq="D").difference(times)
        for day in missing:
            if START <= day < END - pd.Timedelta(days=1):
                records.append({"symbol": symbol, "day": day, "reason": "INTERNAL_INCOMPLETE_DAY"})
    return pd.DataFrame(records).drop_duplicates(["symbol", "day"]).sort_values(["day", "symbol"])


def scoped_read(loaded, req: dict, label: str) -> tuple[pd.DataFrame, dict]:
    a, b = pd.Timestamp(req["start"]), pd.Timestamp(req["end"])
    if not START <= a < b <= END:
        raise ValueError("Subrequest outside same validated dataset extent")
    req_path = OUT / "requests" / f"{label}.json"
    save(req_path, req)
    # Sole supplemental lake reader: the exact files returned by this run's strict catalog audit.
    raw = read_verified_ohlcv(loaded, start=a, end=b)
    raw = raw.loc[raw.symbol.isin(req["symbols"])].copy()
    reports, pieces = {}, []
    for symbol in req["symbols"]:
        part = raw.loc[raw.symbol.eq(symbol)].copy()
        try:
            frame, stats = validate_price_frame(part, req, symbol, [])
            status = "SCOPED_FRAME_PRICE_WINDOW_VALID"
        except ValueError as exc:
            if not str(exc).startswith(f"{symbol}:"):
                raise
            # An all-zero/empty prior bar is evidence of unavailable activity, not a deletion.
            if part.empty:
                reports[symbol] = {"status": "EXPLICIT_EMPTY_SUBWINDOW", "error": str(exc), "rows": 0}
                continue
            frame = segment_research_bars(part, "15m", identity_policy="observed_diagnostic")
            frame["research_window_valid"] = complete_window_mask(frame, backward=1, forward=0)
            if frame.research_window_valid.any():
                raise
            stats = {"rows": len(frame), "complete_windows": 0, "error": str(exc)}
            status = "EXPLICIT_NO_ELIGIBLE_WINDOW_RETAINED_NOT_APPROVED"
        if not frame.ts.ge(a).all() or not (frame.ts + pd.Timedelta(minutes=15)).le(b).all():
            raise ValueError("Returned supplemental rows escaped exact request")
        pieces.append(frame[COLS])
        reports[symbol] = {"status": status, **stats}
    result = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame(columns=COLS)
    result = result.sort_values(["symbol", "ts"], kind="stable").reset_index(drop=True)
    dest = OUT / "returned-scoped-15m" / f"{label}.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(dest, index=False, compression="zstd")
    receipt = {"status": "EXPLORATORY_SCOPED_EQUIVALENT_AUDIT", "request": req,
               "request_path": str(req_path.relative_to(OUT)), "request_sha256": sha(req_path),
               "frame_path": str(dest.relative_to(OUT)), "frame_sha256": sha(dest),
               "symbol_results": reports, "rows": len(result),
               "startup_api_pass_claimed": False, "net_inputs_verified": False,
               "global_catalog_receipt": "catalog-receipt.json"}
    save(OUT / "receipts" / f"{label}.json", receipt)
    return result, receipt


def aggregate_partial(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    f = frame.sort_values(["symbol", "ts"]).copy()
    f["day"] = f.ts.dt.floor("D")
    result = f.groupby(["symbol", "day"]).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
        volume=("volume", "sum"), quote_volume=("quote_volume", "sum"), trade_count=("trade_count", "sum"),
        bars_15m=("ts", "size"), first_15m_ts=("ts", "first"), last_15m_ts=("ts", "last"),
        all_closed=("is_closed", "all"), observed_valid_bars=("observed_valid", "sum"),
    ).reset_index().rename(columns={"day": "ts"})
    result["actual_2345_close_present"] = result.last_15m_ts.eq(result.ts + pd.Timedelta(hours=23, minutes=45))
    result["source_role"] = "EXPLICIT_GOVERNED_15M_PARTIAL_AGGREGATE_ORIGINAL_RULE"
    return result


def rankings(daily: pd.DataFrame, supplements: pd.DataFrame) -> pd.DataFrame:
    base = daily[["ts", "symbol", "open", "high", "low", "close", "volume", "quote_volume", "trade_count"]].copy()
    base["bars_15m"] = 96
    base["actual_2345_close_present"] = True
    base["source_role"] = "VERIFIED_COMPLETE_1D_RETURNED_PROJECTION"
    if not supplements.empty:
        base = pd.concat([base, supplements], ignore_index=True)
    if base.duplicated(["symbol", "ts"]).any():
        raise ValueError("Supplement attempted to replace existing complete day")
    days = pd.date_range("2020-01-01", "2026-07-01", freq="D", tz="UTC")
    close = base.pivot(index="ts", columns="symbol", values="close").reindex(days)
    quote = base.pivot(index="ts", columns="symbol", values="quote_volume").reindex(days)
    counts = base.pivot(index="ts", columns="symbol", values="bars_15m").reindex(days)
    adv = quote.rolling(30, min_periods=30).mean()
    candidates = []
    for month in MONTHS:
        end = month - pd.Timedelta(days=1)
        begin = month - pd.offsets.MonthBegin(1) - pd.Timedelta(days=1)
        formed = close.loc[end] / close.loc[begin] - 1
        coverage = counts.loc[month - pd.offsets.MonthBegin(1):end].ge(1).sum() / end.day
        pool = pd.DataFrame({"formation_return": formed, "adv30": adv.loc[end],
                             "coverage": coverage, "formation_begin_bars": counts.loc[begin],
                             "formation_end_bars": counts.loc[end]})
        excluded = pd.Series([symbol.split("/")[0] in EXCLUDED for symbol in pool.index], index=pool.index)
        pool = pool.loc[~excluded & pool.formation_return.notna() & pool.adv30.ge(10_000_000)
                        & pool.coverage.ge(.8) & pool.formation_begin_bars.ge(48) & pool.formation_end_bars.ge(48)]
        pool = pool.reset_index().sort_values(["formation_return", "adv30", "symbol"], ascending=[False, False, True])
        pool["month"], pool["formation_start_day"], pool["formation_end_day"] = month, begin, end
        pool["rank"] = np.arange(1, len(pool) + 1)
        candidates.append(pool)
    pd.concat([base.loc[base.ts.ge(START) & base.ts.lt(END)]]).to_parquet(
        OUT / "daily-original-buckets.parquet", index=False, compression="zstd")
    return pd.concat(candidates, ignore_index=True)


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f"Refusing to overwrite this run: {OUT}")
    started = time.monotonic()
    daily, daily_receipt = load_returned_daily()
    terminals, terminal_document = load_terminals()
    bundle, _ = read_bundle_contract(LAB, pin=PIN)
    plan = supplement_plan(daily)
    OUT.mkdir(parents=True)
    plan.to_csv(OUT / "partial-day-supplement-plan.csv", index=False)
    global_request = request(sorted(bundle["observed_asset_classes"]), START, END)
    save(OUT / "global-scoped-audit-request.json", global_request)
    save(OUT / "frozen-input-plan.json", {
        "status": "EXPLORATORY_SCOPED_EQUIVALENT_AUDIT_PLANNED", "strategy_net_status": "UNTRUSTED_ESTIMATE_ONLY",
        "created_utc": datetime.now(timezone.utc).isoformat(), "bundle_pin": PIN,
        "source_sha256": sha(Path(__file__)), "daily_projection_sha256": FRAME_SHA,
        "daily_summary_sha256": sha(OLD / "summary.json"), "daily_receipt": daily_receipt,
        "terminal_review_sha256": TERMINAL_SHA,
        "partial_plan_sha256": sha(OUT / "partial-day-supplement-plan.csv"),
        "global_request_sha256": sha(OUT / "global-scoped-audit-request.json"),
        "months": [m.isoformat() for m in MONTHS],
        "formation_rule": "previous complete calendar month endpoints; >=48 15m/day, coverage>=.8, calendar ADV30 with 30 observations>=10m",
        "ranking": "formation descending, ADV descending, symbol ascending",
        "entry_rule": "00:15 open; activity exclusively prior 00:00 closed bar; official restrictions already effective excluded; no future-survival reselection",
        "partial_scope_reason": "An initial partial non-month-end cannot qualify next-month endpoints; interior missing days all included. Endpoints before first full or after last full day explicitly checked when month-end.",
        "scope_constraints": "one full pinned bundle/catalog audit, then bounded requests against exactly same verified files; not require_research_startup PASS",
        "net_inputs_verified": False, "pit_universe_proven": False,
    })
    print(f"FROZEN partial-days={len(plan)} distinct-days={plan.day.nunique()} symbols={plan.symbol.nunique()}", flush=True)
    verified = verify_bundle_files(bundle, data_root=LAB / "data")
    lake = LAB / "data"
    layout = DataLakeLayout(root_dir=lake, raw_dir=lake / "raw", normalized_dir=lake / "normalized",
                           features_dir=lake / "features", cache_dir=lake / "cache", derived_dir=lake / "derived")
    loaded = require_passing_trusted(load_trusted_research_dataset(
        "binance.perp.ohlcv.15m.history.v3", layout=layout, requested_scope=DatasetScope.FULL_MARKET,
        start=START, end=END, gap_policy="contiguous_segments", max_materialize_rows=0))
    if loaded.manifest["parquet_inventory_fingerprint"] != bundle["components"]["15m"]["parquet_inventory_fingerprint"]:
        raise ValueError("Catalog contents differ from pinned bundle")
    save(OUT / "catalog-receipt.json", {"status": "EXPLORATORY_SCOPED_EQUIVALENT_AUDIT",
         "verified_components": verified, "audit": loaded.audit, "coverage": loaded.coverage,
         "verified_identity": loaded.verified_identity, "manifest": loaded.manifest,
         "verified_file_count": len(loaded.verified_parquet_files),
         "global_request_sha256": sha(OUT / "global-scoped-audit-request.json"),
         "startup_api_pass_claimed": False, "net_inputs_verified": False})
    print(f"CATALOG_PASS elapsed={time.monotonic()-started:.1f}s", flush=True)
    parts, receipts = [], []
    for i, (day, group) in enumerate(plan.groupby("day", sort=True)):
        req = request(group.symbol.tolist(), day, day + pd.Timedelta(days=1))
        frame, receipt = scoped_read(loaded, req, f"partial-{day:%Y%m%d}")
        parts.append(aggregate_partial(frame))
        receipts.append(receipt)
        print(f"PARTIAL {i+1}/{plan.day.nunique()} {day.date()} rows={len(frame)}", flush=True)
    supplements = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    supplements.to_parquet(OUT / "partial-original-buckets.parquet", index=False, compression="zstd")
    ranked = rankings(daily, supplements)
    ranked.to_parquet(OUT / "ranked-candidates.parquet", index=False, compression="zstd")
    ranked.to_csv(OUT / "ranked-candidates.csv", index=False)
    save(OUT / "ranking-freeze.json", {"status": "FULL_FORMATION_RANKING_FROZEN_BEFORE_ENTRY_CHECKS_AND_RETURNS",
         "months": 76, "rows": len(ranked), "sha256": sha(OUT / "ranked-candidates.parquet"),
         "partial_buckets": len(supplements), "new_performance_computed": False})
    print(f"RANKING_FROZEN rows={len(ranked)} elapsed={time.monotonic()-started:.1f}s", flush=True)
    holdings, decisions, execution = [], [], []
    previous = []
    for i, month in enumerate(list(MONTHS) + [pd.Timestamp("2026-07-01T00:00:00Z")]):
        pool = ranked.loc[ranked.month.eq(month)]
        # All formation-qualified candidates are requested before using observed activity.
        symbols = sorted(set(pool.symbol) | set(previous))
        req = request(symbols, month, month + pd.Timedelta(minutes=30))
        frame, receipt = scoped_read(loaded, req, f"execution-{month:%Y%m}")
        receipts.append(receipt)
        prior = frame.loc[frame.ts.eq(month)].set_index("symbol")
        entry = frame.loc[frame.ts.eq(month + pd.Timedelta(minutes=15))].set_index("symbol")
        selected = []
        for row in pool.itertuples(index=False):
            event = terminals.get(row.symbol)
            restriction = event is not None and pd.Timestamp(event["new_orders_stop_utc"]) <= month + pd.Timedelta(minutes=15)
            activity = row.symbol in prior.index and bool(prior.loc[row.symbol, "research_window_valid"])
            open_ok = row.symbol in entry.index and np.isfinite(entry.loc[row.symbol, "open"]) and entry.loc[row.symbol, "open"] > 0
            eligible = not restriction and activity and open_ok
            chosen = eligible and len(selected) < 10
            why = "SELECTED" if chosen else "BELOW_FIRST_TEN_ELIGIBLE" if eligible else "OFFICIAL_RESTRICTION_EFFECTIVE" if restriction else "PRIOR_ACTIVITY_UNAVAILABLE" if not activity else "MISSING_REFERENCE_OPEN"
            decisions.append({"month": month, "symbol": row.symbol, "rank": row.rank,
                              "reason": why, "prior_activity_valid": activity, "entry_open_available": open_ok,
                              "future_entry_bar_activity_used": False})
            if chosen:
                selected.append(row.symbol)
                planned_exit = month + pd.offsets.MonthBegin(1) + pd.Timedelta(minutes=15)
                terminal = event is not None and month + pd.Timedelta(minutes=15) < pd.Timestamp(event["terminal_utc"]) < planned_exit
                holdings.append({"month": month, "symbol": row.symbol, "weight": .1,
                    "entry_ts": month + pd.Timedelta(minutes=15), "entry_price": float(entry.loc[row.symbol, "open"]),
                    "exit_ts": pd.Timestamp(event["terminal_utc"]) if terminal else planned_exit,
                    "exit_price": None, "terminal": terminal, "terminal_status": "OFFICIAL_TERMINAL_PRICE_ESTIMATE_NEEDED" if terminal else "NEXT_MONTH_REFERENCE_PENDING",
                    "formation_return": row.formation_return, "adv30": row.adv30, "rank": row.rank,
                    "formation_start_day": row.formation_start_day, "formation_end_day": row.formation_end_day,
                    "coverage": row.coverage, "formation_begin_bars": row.formation_begin_bars,
                    "formation_end_bars": row.formation_end_bars,
                    "entry_prior_activity_valid": activity, "identity_proven": False})
        for symbol in sorted(set(previous) | set(selected)):
            event = terminals.get(symbol)
            closed = event is not None and pd.Timestamp(event["terminal_utc"]) <= month
            execution.append({"ts": month + pd.Timedelta(minutes=15), "symbol": symbol,
                 "price": float(entry.loc[symbol, "open"]) if symbol in entry.index else None,
                 "prior_activity_valid": bool(prior.loc[symbol, "research_window_valid"]) if symbol in prior.index else False,
                 "already_terminal": closed, "selected_new": symbol in selected, "held_old": symbol in previous})
        if not pool.empty and len(selected) != 10:
            raise ValueError(f"Original frozen formation/entry rules produced {len(selected)} legs at {month}")
        previous = selected
        print(f"EXECUTION {i+1}/77 {month:%Y-%m} selected={len(selected)}", flush=True)
    h = pd.DataFrame(holdings)
    e = pd.DataFrame(execution)
    lookup = e.set_index(["ts", "symbol"]).price
    for idx, row in h.iterrows():
        if not row.terminal:
            price = lookup.get((row.exit_ts, row.symbol), np.nan)
            h.loc[idx, "exit_price"] = price
            h.loc[idx, "terminal_status"] = "NEXT_MONTH_0015_REFERENCE" if pd.notna(price) else "MISSING_EXIT_REFERENCE_ESTIMATE_REQUIRED"
    h.to_parquet(OUT / "holdings.parquet", index=False, compression="zstd")
    h.to_csv(OUT / "holdings.csv", index=False)
    records = json.loads(h.to_json(orient="records", date_format="iso"))
    save(OUT / "holdings.json", records)
    e.to_parquet(OUT / "monthly_execution_prices.parquet", index=False, compression="zstd")
    pd.DataFrame(decisions).to_csv(OUT / "selection-decisions.csv", index=False)
    save(OUT / "summary.json", {"status": "EXPLORE_UNTRUSTED_BASELINE_INPUTS_RECONSTRUCTED",
         "months": 76, "holdings": len(h), "unique_symbols": h.symbol.nunique(),
         "terminal_holdings": json.loads(h.loc[h.terminal].to_json(orient="records", date_format="iso")),
         "missing_nonterminal_exit_prices": int(h.loc[~h.terminal].exit_price.isna().sum()),
         "entry_activity_uses_only_prior_closed_bar": True, "selection_uses_future_survival": False,
         "daily_source_sha256": FRAME_SHA, "source_script_sha256": sha(Path(__file__)),
         "source_status": "EXPLORATORY_SCOPED_EQUIVALENT_AUDIT", "new_performance_computed": False,
         "net_inputs_verified": False, "pit_universe_proven": False, "tradability_proven": False,
         "receipts": len(receipts), "catalog_receipt_sha256": sha(OUT / "catalog-receipt.json"),
         "files": {p.name: sha(p) for p in OUT.iterdir() if p.is_file()},
         "elapsed_seconds": time.monotonic() - started})
    print(f"HOLDINGS_READY {OUT/'holdings.parquet'} rows={len(h)} elapsed={time.monotonic()-started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
