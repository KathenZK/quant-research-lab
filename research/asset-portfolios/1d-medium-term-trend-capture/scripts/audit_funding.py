"""MTTC资金费覆盖与现金额敏感性；观察身份不冒充net_research或完整净收益。"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
REPO = FAMILY.parents[2]
LAB = Path("/Users/ZK/OpenCode/quant-strategy-lab")
FUNDING_ROOT = LAB / "data/derived/datasets/binance_perp_funding_v3_inputs_v2"
FUNDING_MANIFEST_SHA256 = "398cc19eac88d0e8c55258c118f6cae2481c6b2d1a5e6253778344b9f25a1076"
sys.path.insert(0, str(LAB / "src"))
from strategy_lab.data.funding_v2 import load_funding_v2  # noqa: E402


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


def load_coverage():
    """通过原冻结读取器核验全部费率事件与覆盖文件；无下载或旧缓存回退。"""
    return load_funding_v2(FUNDING_ROOT, expected_manifest_sha256=FUNDING_MANIFEST_SHA256)


def utc(value, field):
    result = pd.Timestamp(value)
    if pd.isna(result) or result.tzinfo is None:
        raise ValueError(f"{field} requires a nonmissing timezone-aware timestamp")
    return result.tz_convert("UTC")


def unknown(status, **details):
    return {"funding_status": status, "calendar_event_set_verified": False,
            "all_mark_prices_real": False, "funding_real_cash": np.nan,
            "funding_with_daily_close_proxy_cash": np.nan,
            "events": np.nan, "real_mark_events": 0, "proxy_mark_events": 0,
            "unknown_mark_events": 0, "coverage_segment_id": None,
            "identity_status": "OBSERVED_CODE_IDENTITY_NOT_HISTORICAL_PIT",
            "net_research_gate_passed": False, "event_rows": [], **details}


def verified_events_for_window(data, symbol, start, end):
    """只验证结算覆盖，不提供伪造身份材料去调用净收益资格门禁。"""
    start, end = utc(start, "entry_ts"), utc(end, "exit_ts")
    if start >= end:
        raise ValueError("Funding holding interval must have positive duration")
    if end > utc(data.manifest["cutoff_utc"], "funding cutoff"):
        return None, "UNKNOWN_AFTER_FROZEN_FUNDING_CUTOFF", None
    segments = data.segments
    hit = segments.loc[segments.symbol.eq(symbol) & segments.start.le(start) & segments.end.ge(end)]
    if len(hit) != 1:
        return None, "UNKNOWN_CALENDAR_FULL_WINDOW_UNPROVEN", None
    segment_id = hit.segment_id.iloc[0]
    source = data.events_by_symbol.get(symbol, data.events.iloc[:0]) if hasattr(data, "events_by_symbol") else data.events.loc[data.events.symbol.eq(symbol)]
    expected_source = data.expected_by_segment.get(segment_id, data.expected.iloc[:0]) if hasattr(data, "expected_by_segment") else data.expected.loc[data.expected.segment_id.eq(segment_id)]
    actual = source.loc[source.ts.gt(start) & source.ts.le(end)].copy()
    expected = expected_source.loc[expected_source.ts.gt(start) & expected_source.ts.le(end)]
    if (actual.event_id.duplicated().any() or expected.event_id.duplicated().any()
            or not actual.event_unambiguous.fillna(False).all()
            or set(actual.event_id) != set(expected.event_id)):
        return None, "UNKNOWN_MISSING_EXTRA_OR_AMBIGUOUS_EVENT", segment_id
    joined = actual.merge(expected, on="event_id", suffixes=("_actual", "_expected"), validate="one_to_one")
    if (not joined.ts_actual.eq(joined.ts_expected).all()
            or not joined.rate_type_actual.eq(joined.rate_type_expected).all()
            or not np.isfinite(actual.funding_rate).all()
            or not np.allclose(joined.funding_rate_actual, joined.funding_rate_expected, rtol=0, atol=1e-12)):
        return None, "UNKNOWN_EVENT_ID_TIME_TYPE_OR_RATE_MISMATCH", segment_id
    return actual.sort_values("ts"), "CALENDAR_EVENT_SET_VERIFIED_OBSERVED_IDENTITY_ONLY", segment_id


def funding_for_position(data, *, symbol, entry_ts, exit_ts, qty, bars, research_segment_id=None):
    """固定多头数量的(entry,exit]现金额；缺mark仅用事件UTC日前一日已闭合close。"""
    if not np.isfinite(qty) or qty <= 0:
        raise ValueError("MTTC funding requires positive finite long quantity")
    events, status, segment_id = verified_events_for_window(data, symbol, entry_ts, exit_ts)
    if events is None:
        return unknown(status, coverage_segment_id=segment_id)
    if bars.duplicated("ts").any() or not bars.ts.is_monotonic_increasing:
        raise ValueError("Proxy bars must be unique and ordered; never sort away input errors")
    if not isinstance(bars.ts.dtype, pd.DatetimeTZDtype):
        raise ValueError("Proxy bars must have explicit timezone-aware timestamps")
    if "symbol" in bars and not bars.symbol.eq(symbol).all():
        raise ValueError("Proxy bars contain a different symbol")
    lookup = bars.set_index("ts")
    output, real_n, proxy_n, missing_n = [], 0, 0, 0
    real_cash, mixed_cash = 0.0, 0.0
    for event in events.itertuples(index=False):
        mark = float(event.mark_price)
        proxy_ts = pd.NaT
        method = "ACTUAL_FUNDING_MARK_PRICE"
        if np.isfinite(mark) and mark > 0:
            real_n += 1
        else:
            method = "UNKNOWN_MARK_AND_DAILY_PROXY"
            proxy_ts = event.ts.floor("D") - pd.Timedelta(days=1)
            mark = np.nan
            if proxy_ts in lookup.index:
                row = lookup.loc[proxy_ts]
                same_segment = research_segment_id is None or str(row.research_segment_id) == str(research_segment_id)
                valid = bool(row.get("eligible", False)) and same_segment
                if valid and np.isfinite(row.close) and row.close > 0:
                    mark = float(row.close)
                    method = "PREVIOUS_UTC_DAY_CLOSED_TRADE_PRICE_PROXY"
            if np.isfinite(mark):
                proxy_n += 1
            else:
                missing_n += 1
        cash = -float(qty) * mark * float(event.funding_rate)
        if method == "ACTUAL_FUNDING_MARK_PRICE":
            real_cash += cash
        if np.isfinite(cash):
            mixed_cash += cash
        output.append({"symbol": symbol, "event_id": event.event_id, "event_ts": event.ts,
                       "rate_type": event.rate_type, "funding_rate": event.funding_rate,
                       "quantity_before_event": float(qty), "native_mark_price": event.mark_price,
                       "cashflow_price": mark, "price_method": method,
                       "proxy_bar_open_ts": proxy_ts,
                       "proxy_close_known_ts": proxy_ts + pd.Timedelta(days=1),
                       "funding_cash": cash, "coverage_segment_id": segment_id})
    all_real = real_n == len(events)
    return unknown("VERIFIED_RATE_AND_ACTUAL_MARK_CASH_OBSERVED_IDENTITY_ONLY" if all_real
                   else "VERIFIED_RATE_DAILY_CLOSE_PROXY_SENSITIVITY" if missing_n == 0
                   else "UNKNOWN_MARK_AND_DAILY_PROXY", calendar_event_set_verified=True,
                   all_mark_prices_real=all_real,
                   funding_real_cash=real_cash if all_real else np.nan,
                   funding_with_daily_close_proxy_cash=mixed_cash if missing_n == 0 else np.nan,
                   events=len(events), real_mark_events=real_n, proxy_mark_events=proxy_n,
                   unknown_mark_events=missing_n, coverage_segment_id=segment_id, event_rows=output)


def no_position_funding():
    """正常取消/到期而从未持仓时的0是结构性无结算义务，不是未知费用补零。"""
    return unknown("NO_POSITION_NO_FUNDING_DUE", calendar_event_set_verified=True,
                   all_mark_prices_real=True, funding_real_cash=0.0, events=0,
                   funding_with_daily_close_proxy_cash=0.0)


def audit_common_opportunities(summary, prices, data):
    """三臂共同正常结束先由价格账决定；费用未知行保留，不更改原机会母集。"""
    required = {"origin_id", "symbol", "policy", "cost_id", "normal_complete", "entered",
                "entry_ts", "exit_ts", "qty", "return", "complete_window_60", "budget"}
    if not required.issubset(summary.columns):
        raise ValueError(f"Opportunity summary missing: {sorted(required-set(summary.columns))}")
    if summary.duplicated(["origin_id", "policy", "cost_id"]).any():
        raise ValueError("Duplicate origin/policy/cost opportunity")
    for col in ("normal_complete", "entered", "complete_window_60"):
        if not pd.api.types.is_bool_dtype(summary[col].dtype) or summary[col].isna().any():
            raise ValueError(f"{col} must be explicit nonmissing boolean")
    s = summary.loc[summary.cost_id.isin(["base", "slippage_stress"])].copy()
    if not hasattr(data, "events_by_symbol"):
        data = SimpleNamespace(manifest=data.manifest, segments=data.segments, events=data.events,
                               expected=data.expected,
                               events_by_symbol={k: v for k, v in data.events.groupby("symbol", sort=False)},
                               expected_by_segment={k: v for k, v in data.expected.groupby("segment_id", sort=False)})
    rows, event_rows, paired_rows, denominators = [], [], [], []
    if not np.equal(summary.budget.to_numpy(float), 1.0).all():
        raise ValueError("Funding opportunity audit requires frozen unit budgets of 1")
    for (origin, cost), group in s.groupby(["origin_id", "cost_id"], sort=False):
        if set(group.policy) != {"A", "B", "C"} or len(group) != 3 or group.symbol.nunique() != 1:
            raise ValueError("Every origin/cost must contain exactly A/B/C for one symbol")
        if group.complete_window_60.nunique() != 1:
            raise ValueError("Common 60-day source completeness differs between arms")
        normal = bool(group.normal_complete.all())
        complete_window = bool(group.complete_window_60.all())
        common = normal and complete_window
        denominators.append({"origin_id": origin, "cost_id": cost, "symbol": group.symbol.iloc[0],
                             "all_three_price_normal_complete": normal,
                             "complete_window_60": complete_window, "primary_price_pair": common})
        if not common:
            continue
        arm_results = {}
        for row in group.to_dict("records"):
            if not np.isfinite(row["return"]):
                raise ValueError("Normal completed opportunity must have finite price return")
            if not row["entered"]:
                if row["return"] != 0:
                    raise ValueError("Normal no-position opportunity cannot have nonzero price return")
                result = no_position_funding()
            else:
                bars = prices[row["symbol"]]
                # origin may precede entry; the entry's segment proves the proxy cannot bridge a gap.
                hit = bars.loc[bars.ts.eq(utc(row["entry_ts"], "entry_ts"))]
                if len(hit) != 1 or not bool(hit.eligible.iloc[0]):
                    raise ValueError("Entered opportunity does not match one eligible source daily open")
                result = funding_for_position(data, symbol=row["symbol"], entry_ts=row["entry_ts"],
                            exit_ts=row["exit_ts"], qty=float(row["qty"]), bars=bars,
                            research_segment_id=hit.research_segment_id.iloc[0])
            meta = {"origin_id": origin, "cost_id": cost, "policy": row["policy"], "symbol": row["symbol"]}
            event_rows.extend({**meta, **event} for event in result.pop("event_rows"))
            # 配对机会账初始预算固定为1；不是10000 USDT账户的资金费再投资重跑。
            result.update(price_return=float(row["return"]),
                          return_after_real_funding=float(row["return"]) + result["funding_real_cash"],
                          return_after_funding_daily_close_proxy=float(row["return"]) + result["funding_with_daily_close_proxy_cash"])
            rows.append({**meta, **result})
            arm_results[row["policy"]] = result
        paired = {"origin_id": origin, "cost_id": cost, "symbol": group.symbol.iloc[0],
                  "all_three_rate_covered": all(r["calendar_event_set_verified"] for r in arm_results.values()),
                  "all_three_actual_marks": all(r["all_mark_prices_real"] for r in arm_results.values()),
                  "all_three_proxy_cash_available": all(np.isfinite(r["funding_with_daily_close_proxy_cash"]) for r in arm_results.values())}
        if "origin_ts" in group:
            paired["origin_ts"] = group.origin_ts.iloc[0]
        for scope, column in (("price", "price_return"), ("real_funding", "return_after_real_funding"),
                              ("funding_daily_close_proxy", "return_after_funding_daily_close_proxy")):
            for policy in ("A", "B", "C"):
                paired[f"{scope}_{policy}"] = arm_results[policy][column]
            paired[f"{scope}_B_minus_A"] = paired[f"{scope}_B"] - paired[f"{scope}_A"]
            paired[f"{scope}_C_minus_B"] = paired[f"{scope}_C"] - paired[f"{scope}_B"]
        paired_rows.append(paired)
    return {"opportunities": pd.DataFrame(rows), "events": pd.DataFrame(event_rows),
            "paired": pd.DataFrame(paired_rows), "denominators": pd.DataFrame(denominators)}


def contained(root, relative):
    relative = Path(relative)
    path = (root / relative).resolve()
    if relative.is_absolute() or ".." in relative.parts or not path.is_relative_to(root.resolve()):
        raise ValueError(f"Evidence path escapes its declared root: {relative}")
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def pin_file(pins, path, expected):
    path = Path(path).resolve()
    if sha(path) != expected:
        raise ValueError(f"Retained input changed: {path}")
    if str(path) in pins and pins[str(path)] != expected:
        raise ValueError(f"Conflicting input pins: {path}")
    pins[str(path)] = expected


def load_retained_inputs(research_run):
    """新家族计算锁→价格完成回执→本次P0返回帧，逐文件验证后消费。"""
    pins = {}
    lock_path = FAMILY / "specs/computation-lock.json"
    lock = read_json(lock_path)
    if not lock.get("files") or str(Path(__file__).relative_to(REPO)) not in lock["files"]:
        raise ValueError("Computation lock must contain the funding audit before results")
    for name, expected in lock["files"].items():
        pin_file(pins, contained(REPO, name), expected)
    pin_file(pins, lock_path, sha(lock_path))
    run = FAMILY / "artifacts" / research_run
    completed_path = run / "completed.json"
    complete = read_json(completed_path)
    if complete.get("lock_reverified", {}).get("sha256") != sha(lock_path):
        raise ValueError("Research completion is not bound to this computation lock")
    for name, expected in complete["files"].items():
        pin_file(pins, contained(run, name), expected)
    pin_file(pins, completed_path, sha(completed_path))
    if "opportunities.parquet" not in complete["files"]:
        raise ValueError("Research receipt omits the opportunity source")
    root = FAMILY / "artifacts/p0-inputs"
    p0_summary = read_json(root / "summary.json")
    if (p0_summary.get("status") != "PRICE_INPUTS_READY_WITH_RECORDED_EXCLUSIONS"
            or p0_summary.get("startup_failed_symbols") != 0
            or not p0_summary.get("source_pins_unchanged") or p0_summary.get("changed_family_files")):
        raise ValueError("P0 did not successfully complete with immutable input pins")
    for name, field in (("frame-manifest.json", "frame_manifest_sha256"), ("coverage.csv", "coverage_sha256"),
                        ("segments.csv", "segments_sha256")):
        pin_file(pins, root / name, p0_summary[field])
    pin_file(pins, root / "summary.json", sha(root / "summary.json"))
    started = read_json(root / "started.json")
    pin_file(pins, root / "started.json", sha(root / "started.json"))
    for name, expected in started["family_files_sha256"].items():
        pin_file(pins, contained(FAMILY, name), expected)
    source_pins = read_json(FAMILY / "specs/source-pins.json")["files"]
    for name, expected in source_pins.items():
        pin_file(pins, contained(LAB, name), expected)
    frames = {}
    for symbol, item in read_json(root / "frame-manifest.json").items():
        path = contained(root, item["path"])
        pin_file(pins, path, item["sha256"])
        for field in ("request", "startup_report"):
            pin_file(pins, contained(root, item[field + "_path"]), item[field + "_sha256"])
        request = read_json(contained(root, item["request_path"]))
        report = read_json(contained(root, item["startup_report_path"]))
        if (request != report.get("request") or report.get("status") != "PRICE_DIAGNOSTIC_INPUTS_VERIFIED"
                or request.get("backward_bars") != 60 or request.get("forward_bars") != 0
                or request.get("mode") != "price_diagnostic" or symbol not in request["symbols"]):
            raise ValueError(f"P0 request/return provenance is invalid: {symbol}")
        frame = pd.read_pickle(path, compression="gzip")
        digest = hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).values.tobytes()).hexdigest()
        if digest != item["dataframe_hash"] or len(frame) != item["rows"] or not frame.symbol.eq(symbol).all():
            raise ValueError(f"P0 returned frame contents changed: {symbol}")
        frames[symbol] = frame
    opportunities = pd.read_parquet(run / "opportunities.parquet")
    return opportunities, frames, pins, run


def finite_or_none(value):
    return float(value) if np.isfinite(value) else None


def save_json(path, content):
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2, default=str, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-run", default="research-20260909")
    args = parser.parse_args()
    if not args.research_run or Path(args.research_run).name != args.research_run or args.research_run in (".", ".."):
        raise ValueError("Research run must be a single retained directory name")
    out = FAMILY / "artifacts/funding"
    if out.exists():
        raise FileExistsError("Funding evidence already exists; do not overwrite the frozen run")
    began = time.time()
    opportunities, frames, pins, run = load_retained_inputs(args.research_run)
    pin_file(pins, FUNDING_ROOT / "_MANIFEST.json", FUNDING_MANIFEST_SHA256)
    data = load_coverage()
    save_json(out / "started.json", {"utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "funding cashflow sensitivity on the frozen price opportunity paths",
        "research_run": args.research_run, "input_pins": pins,
        "funding_dataset_id": data.manifest["dataset_id"], "funding_manifest_sha256": FUNDING_MANIFEST_SHA256,
        "funding_parquet_fingerprint": data.manifest["parquet_inventory_fingerprint"],
        "identity_status": "OBSERVED_CODE_IDENTITY_NOT_HISTORICAL_PIT", "net_research_gate_passed": False,
        "time_convention": "(entry_ts,exit_ts]; native milliseconds retained; same-time funding before open orders",
        "proxy_policy": "actual funding mark first; missing mark uses eligible preceding UTC day's close in the same price segment",
        "costs": ["base", "slippage_stress"], "returns_read_only_after_source_lock": True})
    result = audit_common_opportunities(opportunities, frames, data)
    for name, frame in result.items():
        frame.to_csv(out / (f"{name}.csv.gz" if name == "events" else f"{name}.csv"), index=False)
    data.segments.to_csv(out / "verified-calendar-segments.csv", index=False)
    paired, denominators, fees = result["paired"], result["denominators"], result["opportunities"]
    summaries = []
    for cost in ("base", "slippage_stress"):
        p = paired.loc[paired.cost_id.eq(cost)].copy()
        source = pd.read_parquet(run / f"paired-{cost}.parquet")
        if set(p.origin_id) != set(source.origin_id):
            raise ValueError("Funding audit changed the primary price paired-origin population")
        price = p.set_index("origin_id")
        base = source.set_index("origin_id").reindex(price.index)
        if not np.allclose(price[["price_A", "price_B", "price_C"]], base[["A", "B", "C"]], rtol=1e-12, atol=1e-12):
            raise ValueError("Funding audit's pre-funding paired returns differ from research")
        den = denominators.loc[denominators.cost_id.eq(cost)]
        coverage = {"cost_id": cost, "original_origins": len(den),
                    "primary_price_pair_origins": len(p), "common_rate_covered": int(p.all_three_rate_covered.sum()),
                    "common_actual_mark_cash": int(p.all_three_actual_marks.sum()),
                    "common_real_or_proxy_cash": int(p.all_three_proxy_cash_available.sum()),
                    "unknown_calendar_origins": int((~p.all_three_rate_covered).sum()),
                    "calendar_known_but_price_unknown_origins": int((p.all_three_rate_covered & ~p.all_three_proxy_cash_available).sum())}
        for label, flag, prefix in (("actual_marks", "all_three_actual_marks", "real_funding"),
                                    ("real_or_daily_proxy", "all_three_proxy_cash_available", "funding_daily_close_proxy")):
            sample = p.loc[p[flag]]
            table = sample[["origin_id", "symbol", "origin_ts"]].copy()
            for policy in ("A", "B", "C"):
                table[policy] = sample[f"{prefix}_{policy}"].to_numpy(float)
            table["B_minus_A"] = table.B - table.A
            table["C_minus_B"] = table.C - table.B
            table.to_csv(out / f"paired-{label}-{cost}.csv", index=False)
            coverage[label] = {"n": len(table), "symbols": int(table.symbol.nunique()),
                "points": {column: finite_or_none(table[column].mean()) for column in ("A", "B", "C", "B_minus_A", "C_minus_B")},
                "price_only_same_origins": {column: finite_or_none(sample[f"price_{column}"].mean()) for column in ("A", "B", "C", "B_minus_A", "C_minus_B")}}
        summaries.append(coverage)
    for path, digest in pins.items():
        if sha(path) != digest:
            raise ValueError(f"Input changed during funding audit: {path}")
    summary = {"status": "OBSERVED_IDENTITY_FUNDING_CASH_SENSITIVITY_COMPLETE",
        "seconds": time.time() - began, "cost_summaries": summaries,
        "funding_status_counts": {str(k): int(v) for k, v in fees.funding_status.value_counts().items()},
        "opportunity_rows": len(fees), "attributed_event_rows": len(result["events"]),
        "event_rows_can_repeat_across_origins_and_costs": True,
        "fullcost_verified": False, "net_research_gate_passed": False,
        "unknown_funding_filled_with_zero": False, "old_family_price_frames_read": False,
        "account_funding_reinvestment_replayed": False,
        "scope": "主价格配对母集内的单位预算机会现金额附表；真实mark与日线代理分列；不是全历史账户资金费净收益",
        "limitations": ["历史身份仍是观测代码声明，不是PIT认证", "只在完整结算片段内验证持仓窗口", "代理成交收盘价不是结算mark价", "费用共同样本是价格主样本的覆盖子集，不能外推全历史", "资金费未回流改变账户分配、数量或后续再投资"]}
    save_json(out / "summary.json", summary)
    save_json(out / "artifact-manifest.json", {"files": {p.name: sha(p) for p in out.iterdir() if p.is_file()},
                                               "input_pins_unchanged": True})
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
