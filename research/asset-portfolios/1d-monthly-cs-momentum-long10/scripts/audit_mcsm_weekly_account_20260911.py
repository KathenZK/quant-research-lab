"""Independent weekly/monthly cash replay without either strategy account engine."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from audit_mcsm_funding_account_bridge_20260910 import terminals_from_raw
from verify_mcsm_baseline_20260908 import load_verified_returned_daily

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
SOURCE = FAMILY / "artifacts/drawdown-frequency-round-20260911/weekly"
OUT = SOURCE.parent / "independent-audit"
BASE = FAMILY / "artifacts/baseline-estimate-20260909"
START = pd.Timestamp("2020-04-01T00:15Z")
END = pd.Timestamp("2026-07-01T00:15Z")
DAY = pd.Timedelta(days=1)
MIN15 = pd.Timedelta(minutes=15)
INITIAL = 100000.
CONTRACT_SHA = "aa38d87cf3cb374d4f587faf3660586950986bfa2a25813e851d65c28862d2d4"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin(path, digest):
    if sha(path) != digest:
        raise ValueError(f"changed fixed input: {path}")


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        handle.write("\n")


class MissingInput(Exception):
    def __init__(self, code, ts, symbol, reference_ts=None):
        self.code, self.ts, self.symbol = code, pd.Timestamp(ts), symbol
        self.reference_ts = self.ts if reference_ts is None else pd.Timestamp(reference_ts)
        super().__init__(f"{code} {symbol} {self.reference_ts}")

    def as_dict(self):
        return {"code": self.code, "event_ts": self.ts, "symbol": self.symbol,
                "reference_ts": self.reference_ts, "message": str(self)}


def solve_postcost(pre, quantities, prices, weights, cost):
    """Solve the self-financing equation independently of any imported account."""
    if not np.isfinite(pre) or pre <= 0:
        raise ValueError("nonpositive or invalid pre-trade equity")
    union = set(quantities) | set(weights)
    nominal = {s: quantities.get(s, 0.) * prices[s] for s in union}
    if weights and (any(w <= 0 for w in weights.values()) or not math.isclose(sum(weights.values()), 1., abs_tol=1e-12)):
        raise ValueError("invalid target weights")
    lo, hi = 0., pre
    for _ in range(100):
        value = (lo + hi) / 2
        lhs = value + cost * math.fsum(abs(weights.get(s, 0.) * value - nominal[s]) for s in union)
        if lhs > pre:
            hi = value
        else:
            lo = value
    post = (lo + hi) / 2
    new = {s: w * post / prices[s] for s, w in weights.items()}
    turnover = math.fsum(abs(new.get(s, 0.) - quantities.get(s, 0.)) * prices[s] for s in union)
    if abs(post + turnover * cost - pre) > max(1e-7, pre * 1e-12):
        raise ValueError("self-financing equation does not reconcile")
    return post, new, turnover


def verify_schedule(holdings, grid, start=START, end=END):
    """Missing whole decisions cannot disappear behind a plausible NAV series."""
    if set(holdings.strategy) != {"B0", "M28", "W28", "W7"}:
        raise ValueError("missing or extra strategy in fixed holdings")
    month_dates = set(pd.date_range(start.floor("D"), end.floor("D")-DAY, freq="MS", tz="UTC") + MIN15)
    monday_dates = {start} | set(pd.date_range(start.floor("D"), end.floor("D")-DAY, freq="W-MON", tz="UTC") + MIN15)
    expected_grid = month_dates | monday_dates | {end}
    if len(grid) != len(set(map(pd.Timestamp, grid))) or set(map(pd.Timestamp, grid)) != expected_grid:
        raise ValueError("common valuation grid is incomplete or duplicated")
    for strategy, h in holdings.groupby("strategy", sort=True):
        expected = month_dates if strategy in {"B0", "M28"} else monday_dates
        if set(h.entry_ts) != expected or not h.groupby("entry_ts").size().eq(10).all():
            raise ValueError(f"missing decision or missing slot: {strategy}")
        if h.duplicated(["entry_ts", "symbol"]).any() or not np.allclose(h.weight, .1, rtol=0, atol=1e-15):
            raise ValueError(f"invalid same-decision weights: {strategy}")
        dates = sorted(expected) + [end]
        next_exit = dict(zip(dates[:-1], dates[1:]))
        if any(r.scheduled_exit_ts != next_exit[r.entry_ts] for r in h.itertuples(index=False)):
            raise ValueError(f"scheduled holding window changed: {strategy}")


def load_saved_endpoints(plan):
    """Read only pinned returned projections; no API calls or raw lake readers."""
    parts, hashes = [], {}
    catalog_path = BASE / "inputs/catalog-receipt.json"
    pin(catalog_path, "f410516d008d2779fbc49f061cd2b9ba03c55abb5fb30cb18445aff9a9ab2f97")
    catalog = json.loads(catalog_path.read_text())
    pin(BASE / "inputs/global-scoped-audit-request.json", catalog["global_request_sha256"])
    if catalog["audit"]["row_quality"] != "PASS":
        raise ValueError("old returned projection lacks passing catalog receipt")
    for frozen in plan["old_receipts"]:
        path = ROOT / frozen["path"]
        pin(path, frozen["sha256"])
        receipt = json.loads(path.read_text())
        for kind in ["request", "frame"]:
            target = BASE / "inputs" / receipt[f"{kind}_path"]
            pin(target, receipt[f"{kind}_sha256"])
            hashes[str(target.relative_to(ROOT))] = sha(target)
        parts.append(pd.read_parquet(BASE / "inputs" / receipt["frame_path"]))
        hashes[str(path.relative_to(ROOT))] = sha(path)
    qualification = json.loads((SOURCE / "qualification-plan.json").read_text())
    for folder, requests in [(SOURCE / "qualification", qualification["requests"]), (SOURCE, plan["requests"])]:
        for item in requests:
            label = item["label"]
            rpath = folder / "receipts" / f"{label}.json"
            receipt = json.loads(rpath.read_text())
            request_path = folder / "requests" / f"{label}.json"
            report_path = folder / "reports" / f"{label}.json"
            frame_path = folder / "returned-targets" / f"{label}.parquet"
            for target, digest in [(request_path, receipt["request_sha256"]),
                                   (report_path, receipt["report_sha256"]), (frame_path, receipt["frame_sha256"])]:
                pin(target, digest)
                hashes[str(target.relative_to(ROOT))] = digest
            if json.loads(request_path.read_text()) != item["request"]:
                raise ValueError("saved request differs from fixed target plan")
            report = json.loads(report_path.read_text())
            if report["status"] != "PRICE_DIAGNOSTIC_INPUTS_VERIFIED":
                raise ValueError("saved projection lacks passing startup report")
            frame = pd.read_parquet(frame_path)
            target_keys = {(s, pd.Timestamp(t)) for s, t in item["target_keys"]}
            keys = set(zip(frame.symbol, frame.ts))
            if len(frame) != receipt["rows"] or not keys.issubset(target_keys):
                raise ValueError("unexpected saved projection rows")
            parts.append(frame)
            hashes[str(rpath.relative_to(ROOT))] = sha(rpath)
    endpoints = pd.concat(parts, ignore_index=True)
    if endpoints.duplicated(["symbol", "ts"]).any():
        raise ValueError("duplicate saved endpoint key")
    return endpoints, hashes


def required_price(kind, ts, symbol, prices, closes, trade_required):
    if kind == "daily":
        key = (ts-DAY, symbol)
        if key not in closes:
            raise MissingInput("DAILY_MARK_MISSING", ts, symbol, ts-DAY)
        value, valid = closes[key]
        if not valid or not np.isfinite(value) or value <= 0:
            raise MissingInput("DAILY_MARK_INELIGIBLE", ts, symbol, ts-DAY)
        return value
    if (ts, symbol) not in prices:
        raise MissingInput("EXECUTION_OPEN_MISSING", ts, symbol)
    value, _ = prices[(ts, symbol)]
    if not np.isfinite(value) or value <= 0:
        raise MissingInput("EXECUTION_OPEN_INVALID", ts, symbol)
    if trade_required:
        if (ts-MIN15, symbol) not in prices:
            raise MissingInput("PRIOR_ACTIVITY_MISSING", ts, symbol)
        if not prices[(ts-MIN15, symbol)][1]:
            raise MissingInput("PRIOR_ACTIVITY_INELIGIBLE", ts, symbol)
    return value


def independent_replay(holdings, endpoints, daily, terminal_values, grid, slip, start=START, end=END):
    """Mark current fixed quantity, settle terminal, and solve new target equity."""
    prices = {(r.ts, r.symbol): (float(r.open) if pd.notna(r.open) else np.nan,
                                bool(r.eligible) and bool(r.research_window_valid)) for r in endpoints.itertuples(index=False)}
    closes = {(r.ts, r.symbol): (float(r.close), bool(r.eligible)) for r in daily.itertuples(index=False)}
    targets = {ts: dict(zip(g.symbol, g.weight)) for ts, g in holdings.groupby("entry_ts")}
    targets[end] = {}
    timeline = [(t, 0, "daily", None) for t in pd.date_range(start.floor("D") + DAY, end.floor("D"), freq="D")]
    timeline += [(t, 1, "terminal", (s, price)) for (s, t), price in terminal_values.items() if start < t < end]
    timeline += [(pd.Timestamp(t), 2, "boundary", None) for t in grid]
    timeline.sort(key=lambda x: (x[0], x[1]))
    eq, price_cash, fees, slippage = INITIAL, 0., 0., 0.
    q, last = {}, {}
    nav_rows, trades, terminal_rows = [], [], []
    failure = None
    for ts, _, kind, payload in timeline:
        try:
            if kind == "terminal":
                symbol, price = payload
                if symbol not in q:
                    continue
                pnl = q[symbol] * (price - last[symbol])
                fee = q[symbol] * price * .001
                price_cash += pnl
                fees += fee
                eq += pnl - fee
                terminal_rows.append({"ts": ts, "symbol": symbol, "quantity": q[symbol], "settlement_price": price, "fee": fee})
                del q[symbol], last[symbol]
                continue
            values = {}
            needed = set(q) | set(targets.get(ts, {})) if kind == "boundary" else set(q)
            missing_same_event = []
            for symbol in sorted(needed):
                try:
                    values[symbol] = required_price(kind, ts, symbol, prices, closes, ts in targets)
                except MissingInput as exc:
                    missing_same_event.append(exc.as_dict())
            if missing_same_event:
                failure = {**missing_same_event[0], "same_event_failures": missing_same_event}
                break
            delta = math.fsum(q[s] * (values[s] - last[s]) for s in q)
            eq += delta
            price_cash += delta
            last = {s: values[s] for s in q}
            if kind == "boundary" and ts in targets:
                pre = eq
                post, new, turnover = solve_postcost(pre, q, values, targets[ts], .001+slip)
                for symbol in sorted(set(q) | set(new)):
                    notional = abs(new.get(symbol, 0.) - q.get(symbol, 0.)) * values[symbol]
                    trades.append({"ts": ts, "symbol": symbol, "old_quantity": q.get(symbol, 0.),
                                   "new_quantity": new.get(symbol, 0.), "reference_price": values[symbol],
                                   "traded_notional": notional, "fee": notional*.001, "slippage": notional*slip})
                fees += turnover*.001
                slippage += turnover*slip
                eq = post
                q = new
                last = {s: values[s] for s in q}
            if abs(INITIAL + price_cash - fees - slippage - eq) > max(1e-6, eq*1e-11):
                raise ValueError("independent event cash identity failed")
            nav_rows.append({"ts": ts, "sample_kind": kind, "equity": eq, "price_pnl": price_cash,
                             "fees": fees, "slippage": slippage,
                             "gross_notional": math.fsum(q[s]*last[s] for s in q)})
        except MissingInput as exc:
            failure = exc.as_dict()
            break
    return {"nav": pd.DataFrame(nav_rows), "trades": pd.DataFrame(trades), "terminals": pd.DataFrame(terminal_rows),
            "failure": failure, "remaining_positions": q}


def compare_numeric(expected, found, keys, fields, description):
    if expected.duplicated(keys).any() or found.duplicated(keys).any():
        raise ValueError(f"duplicate key in {description}")
    a = expected.set_index(keys).sort_index()
    b = found.set_index(keys).sort_index()
    if not a.index.equals(b.index):
        raise ValueError(f"different exact keys in {description}")
    errors = {}
    for field in fields:
        av, bv = a[field].to_numpy(float), b[field].to_numpy(float)
        if not np.isfinite(av).all() or not np.isfinite(bv).all():
            raise ValueError(f"nonfinite {description} {field}")
        errors[field] = float(np.abs(av-bv).max()) if len(av) else 0.
        if not np.allclose(av, bv, rtol=1e-10, atol=1e-6):
            raise ValueError(f"independent mismatch {description} {field}: {errors[field]}")
    return errors


def calendar_months(nav, start=START, end=END):
    rows, prior = [], INITIAL
    cumulative = {"price_pnl": 0., "fees": 0., "slippage": 0.}
    for month in pd.date_range(start.floor("D"), end.floor("D")-DAY, freq="MS", tz="UTC"):
        cutoff = min(month+pd.offsets.MonthBegin(1), end)
        if cutoff == end.floor("D"):
            cutoff = end
        value = nav.loc[nav.ts.eq(cutoff)]
        if len(value) != 1:
            raise ValueError("calendar month missing exact end NAV")
        equity = float(value.equity.iloc[0])
        changes = {field + "_usdt": float(value[field].iloc[0]) - previous for field, previous in cumulative.items()}
        rows.append({"month": month, "start_equity": prior, "end_equity": equity,
                     "pnl_usdt": equity-prior, "return": equity/prior-1, **changes})
        prior = equity
        cumulative = {field: float(value[field].iloc[0]) for field in cumulative}
    return pd.DataFrame(rows)


def independent_leg_cash(holdings, trades, endpoints, terminal_values):
    quantities = trades.set_index(["ts", "symbol"]).new_quantity.to_dict()
    opens = endpoints.set_index(["ts", "symbol"]).open.to_dict()
    rows = []
    for leg in holdings.itertuples(index=False):
        q = quantities[(leg.entry_ts, leg.symbol)]
        begin = float(opens[(leg.entry_ts, leg.symbol)])
        finish = (float(terminal_values[(leg.symbol, leg.exit_ts)]) if leg.terminal else
                  float(opens[(leg.exit_ts, leg.symbol)]))
        rows.append({"entry_ts": leg.entry_ts, "symbol": leg.symbol, "account_entry_quantity": q,
                     "entry_reference_price": begin, "exit_reference_price": finish,
                     "period_price_pnl_usdt": q*(finish-begin)})
    return pd.DataFrame(rows)


def main():
    summary_path = SOURCE / "summary.json"
    published = json.loads(summary_path.read_text())
    if published["contract_sha256"] != CONTRACT_SHA:
        raise ValueError("weekly study contract changed")
    pin(FAMILY / "specs/binance-1d-mcsm-drawdown-frequency-round-20260911.md", CONTRACT_SHA)
    pin(FAMILY / "scripts/research_mcsm_weekly_20260911.py", published["execution_script_sha256"])
    expected_keys = {(s, slip) for s in ["B0", "M28", "W28", "W7"] for slip in [.0004, .0008]}
    if len(published["accounts"]) != 8 or {(x["strategy"], x["slippage_rate"]) for x in published["accounts"]} != expected_keys:
        raise ValueError("not exactly eight predefined weekly comparison accounts")
    frozen = json.loads((SOURCE / "nomination-freeze.json").read_text())
    plan = json.loads((SOURCE / "execution-plan.json").read_text())
    pin(SOURCE / "nomination-freeze.json", plan["nomination_freeze_sha256"])
    pin(SOURCE / "holding-windows.parquet", plan["holding_windows_sha256"])
    pin(SOURCE / "target-keys.parquet", plan["target_keys_sha256"])
    if frozen["contract_sha256"] != CONTRACT_SHA:
        raise ValueError("nominations used another contract")
    endpoints, pins = load_saved_endpoints(plan)
    holdings = pd.read_parquet(SOURCE / "holding-windows.parquet")
    verify_schedule(holdings, plan["common_grid"])
    daily = load_verified_returned_daily()
    terminal_raw, terminal_pins = terminals_from_raw()
    terminal_values = {key: value["estimated_center"] for key, value in terminal_raw.items()}
    for leg in holdings.itertuples(index=False):
        possible = [t for symbol, t in terminal_values if symbol == leg.symbol and leg.entry_ts < t <= leg.scheduled_exit_ts]
        expected_exit = min(possible) if possible else leg.scheduled_exit_ts
        if leg.exit_ts != expected_exit or bool(leg.terminal) != bool(possible):
            raise ValueError("holding exit differs from fixed terminal/scheduled event")
    pins[str(summary_path.relative_to(ROOT))] = sha(summary_path)
    for metric in published["accounts"]:
        folder = SOURCE / f"{metric['strategy']}-{round(metric['slippage_rate']*10000)}bp"
        for path in folder.glob('*'):
            if path.is_file():
                pins[str(path.relative_to(ROOT))] = sha(path)
    save(OUT / "weekly-started.json", {"script_sha256": sha(Path(__file__)), "contract_sha256": CONTRACT_SHA,
                                       "input_sha256": pins, "terminal_raw_pins": terminal_pins,
                                       "does_not_import_weekly_or_account_engine": True})
    results = []
    for metric in published["accounts"]:
        strategy, slip = metric["strategy"], metric["slippage_rate"]
        label = f"{strategy}-{round(slip*10000)}bp"
        folder = SOURCE / label
        found = independent_replay(holdings.loc[holdings.strategy.eq(strategy)], endpoints, daily, terminal_values, plan["common_grid"], slip)
        nav = found["nav"]
        nav.to_parquet(OUT / f"weekly-{label}-independent-nav.parquet", index=False)
        if found["failure"] is not None:
            if metric["status"] != "ACCOUNT_REPLAY_BLOCKED_MISSING_INPUT_NO_SKIP":
                raise ValueError("published full account despite an independently missing input")
            failure = found["failure"]
            matches = [item for item in failure.get("same_event_failures", [failure]) if item["message"] == metric["reason"]]
            if not matches:
                raise ValueError(f"earliest failure does not match: {failure} vs {metric['reason']}")
            result = {"account": label, "status": "CONFIRMED_FIRST_MISSING_INPUT_NO_FULL_RETURN", "failure": failure,
                      "published_failure_in_same_earliest_event_set": matches[0],
                      "completed_nav_rows_before_failure": len(nav), "full_period_return": None,
                      "remaining_positions_at_failure": len(found["remaining_positions"])}
            save(OUT / f"weekly-{label}-failure-check.json", result)
            results.append(result)
            continue
        if metric["status"] != "COMPLETE_PRICE_DIAGNOSTIC_NOT_FUNDING_NET" or found["remaining_positions"]:
            raise ValueError("independent complete/published status or final clearing differs")
        original_nav = pd.read_parquet(folder / "nav.parquet")
        if not original_nav.funding_pnl.eq(0).all() or metric["funding_computed"] or metric["funding_pnl_usdt"] is not None:
            raise ValueError("price-only account contains a hidden funding assumption")
        if original_nav.ts.tolist() != nav.ts.tolist() or original_nav.sample_kind.tolist() != nav.sample_kind.tolist():
            raise ValueError("NAV clocks/order differs")
        errors = compare_numeric(original_nav, nav, ["ts"], ["equity", "price_pnl", "fees", "slippage", "gross_notional"], label+" NAV")
        trade_errors = compare_numeric(pd.read_parquet(folder / "trades.parquet"), found["trades"], ["ts", "symbol"],
                                       ["old_quantity", "new_quantity", "reference_price", "traded_notional", "fee", "slippage"], label+" trades")
        legs = independent_leg_cash(holdings.loc[holdings.strategy.eq(strategy)], found["trades"], endpoints, terminal_values)
        leg_errors = compare_numeric(pd.read_parquet(folder / "leg-price-pnl.parquet"), legs, ["entry_ts", "symbol"],
                                     ["account_entry_quantity", "entry_reference_price", "exit_reference_price", "period_price_pnl_usdt"], label+" legs")
        if not np.isclose(legs.period_price_pnl_usdt.sum(), nav.price_pnl.iloc[-1], rtol=1e-10, atol=1e-6):
            raise ValueError("holding-period cash does not sum to account price PnL")
        reported_terminals = pd.read_parquet(folder / "terminals.parquet")
        if len(reported_terminals) != len(found["terminals"]):
            raise ValueError("terminal count differs")
        terminal_errors = (compare_numeric(reported_terminals, found["terminals"], ["ts", "symbol"],
                                           ["quantity", "settlement_price", "fee"], label+" terminals")
                           if len(found["terminals"]) else {})
        months = calendar_months(nav)
        month_errors = compare_numeric(pd.read_parquet(folder / "monthly.parquet"), months, ["month"],
                                       ["start_equity", "end_equity", "pnl_usdt", "return", "price_pnl_usdt", "fees_usdt", "slippage_usdt"], label+" months")
        months.to_parquet(OUT / f"weekly-{label}-independent-monthly.parquet", index=False)
        e = np.r_[INITIAL, nav.equity.to_numpy(float)]
        mdd = float((e/np.maximum.accumulate(e)-1).min())
        final = float(e[-1])
        metrics = {"final_equity": final, "total_return": final/INITIAL-1,
                   "cagr_365_25": (final/INITIAL)**(365.25*86400/(END-START).total_seconds())-1,
                   "max_drawdown_common_grid": mdd, "price_pnl_usdt": float(nav.price_pnl.iloc[-1]),
                   "fees_usdt": float(nav.fees.iloc[-1]), "slippage_usdt": float(nav.slippage.iloc[-1])}
        for field, value in metrics.items():
            if not np.isclose(value, metric[field], rtol=1e-10, atol=1e-6):
                raise ValueError(f"metric mismatch {label} {field}")
        years = []
        for year, g in months.groupby(months.month.dt.year):
            years.append({"year": int(year), "start_equity": float(g.start_equity.iloc[0]),
                          "end_equity": float(g.end_equity.iloc[-1]), "return": float(g.end_equity.iloc[-1]/g.start_equity.iloc[0]-1),
                          "pnl_usdt": float(g.pnl_usdt.sum()), "months": len(g),
                          **{field: float(g[field].sum()) for field in ["price_pnl_usdt", "fees_usdt", "slippage_usdt"]}})
        year_errors = compare_numeric(pd.DataFrame(metric["yearly"]), pd.DataFrame(years), ["year"],
                                      ["start_equity", "end_equity", "return", "pnl_usdt", "months", "price_pnl_usdt", "fees_usdt", "slippage_usdt"], label+" years")
        result = {"account": label, "status": "INDEPENDENT_PRICE_ACCOUNT_ALL_NAV_TRADES_MONTHS_YEARS_PASS", "nav_rows": len(nav),
                  "trades": len(found["trades"]), "monthly_rows": len(months), "terminal_closes": len(found["terminals"]),
                  "nav_max_abs_errors": errors, "trade_max_abs_errors": trade_errors, "month_max_abs_errors": month_errors,
                  "year_max_abs_errors": year_errors, "terminal_max_abs_errors": terminal_errors,
                  "holding_leg_rows": len(legs), "leg_max_abs_errors": leg_errors,
                  **metrics, "funding_not_computed": True}
        save(OUT / f"weekly-{label}-account-check.json", result)
        results.append(result)
        print(json.dumps(result), flush=True)
    for path, digest in pins.items():
        pin(ROOT / path, digest)
    size = sum(p.stat().st_size for p in OUT.glob('weekly-*') if p.is_file())
    if size > 5*1024**2:
        raise ValueError("weekly independent audit output exceeds 5MiB budget")
    save(OUT / "weekly-summary.json", {"status": "ALL_EIGHT_PRESCRIBED_PRICE_ACCOUNTS_OR_FIRST_FAILURE_INDEPENDENTLY_ADJUDICATED",
                                       "results": results, "all_source_hashes_unchanged": True,
                                       "budget_bytes_before_summary": size, "contract_sha256": CONTRACT_SHA,
                                       "script_sha256": sha(Path(__file__)),
                                       "output_sha256": {p.name: sha(p) for p in sorted(OUT.glob('weekly-*')) if p.is_file()}})


if __name__ == "__main__":
    main()
