"""冻结月度 Top10 与事前流动性/波动匹配对照的价格诊断。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment


FAMILY = Path(__file__).resolve().parents[1]
LAB = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(LAB / "src"))
sys.path.insert(0, str(FAMILY / "scripts"))

from strategy_lab.data.research_bundle import require_research_startup  # noqa: E402
from build_mcsm_baseline_inputs_20260909 import load_returned_daily  # noqa: E402
from run_mcsm_baseline_estimate_20260909 import load_terminals  # noqa: E402

OUT = FAMILY / "artifacts/mechanism-round-20260910/selection"
BASE = FAMILY / "artifacts/baseline-estimate-20260909"
SPEC = FAMILY / "specs/binance-1d-mcsm-mechanism-round-20260910.md"
SPEC_SHA = "9df5e3fcf02c88e68d00467a04a4e9fd2f20eb33001cf07effb589d5bd7f5956"
MONTHS = pd.date_range("2020-03-01", "2026-06-01", freq="MS", tz="UTC")
BUNDLE_PATH = LAB / "research/platform/data-lake-governance/specs/binance-v3-research-input-bundle-v2.json"
BUNDLE_SHA = "d2a729d03be71d67aa9c5522fb242bbf010b6c64400233c27d9cb2406f567008"
KNOWN_IDENTITY = {(pd.Timestamp("2025-05-01", tz="UTC"), "AERGO/USDT:USDT"),
                  (pd.Timestamp("2026-01-01", tz="UTC"), "LIT/USDT:USDT")}


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        handle.write("\n")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prior_volatility(frame: pd.DataFrame) -> pd.DataFrame:
    """30 个已闭合日收益；31 日价格须连续且位于同一有效段。"""
    out = frame.sort_values(["symbol", "ts"], kind="stable").copy()
    if out.duplicated(["symbol", "ts"]).any():
        raise ValueError("Duplicate daily input")
    groups = out.groupby(["symbol", "research_segment_id"], sort=False)
    out["daily_return"] = groups.close.pct_change(fill_method=None)
    out["vol30"] = out.groupby(["symbol", "research_segment_id"], sort=False).daily_return.transform(
        lambda values: values.rolling(30, min_periods=30).std(ddof=1)
    )
    out["valid31"] = groups.research_window_valid.transform(
        lambda values: values.astype(int).rolling(31, min_periods=31).sum().eq(31)
    )
    start = groups.ts.shift(30)
    out["valid31"] &= out.ts.sub(start).eq(pd.Timedelta(days=30))
    out.loc[~out.valid31, "vol30"] = np.nan
    return out[["symbol", "ts", "vol30", "valid31"]]


def optimal_pairs(pool: pd.DataFrame, top_symbols: list[str]) -> pd.DataFrame:
    """log特征横截面z分数等权平方距离；同类无放回，不接收未来表现。"""
    required = {"symbol", "adv30", "vol30"}
    if required - set(pool.columns):
        raise ValueError("Missing matching feature")
    if pool.symbol.duplicated().any() or len(set(top_symbols)) != len(top_symbols):
        raise ValueError("Duplicate matching symbol")
    p = pool.sort_values("symbol", kind="stable").copy()
    if not np.isfinite(p[["adv30", "vol30"]].to_numpy()).all():
        raise ValueError("Missing matching input")
    if p[["adv30", "vol30"]].le(0).any().any():
        raise ValueError("Nonpositive matching input")
    if not set(top_symbols).issubset(set(p.symbol)):
        raise ValueError("Selected symbol lacks valid pre-entry feature")
    if "asset_class" not in p:
        p["asset_class"] = "COIN"
    for column in ("adv30", "vol30"):
        logged = np.log(p[column])
        std = float(logged.std(ddof=0))
        p[f"{column}_z"] = (logged - logged.mean()) / std if std > 0 else 0.0
    columns = ["adv30_z", "vol30_z"]
    records = []
    for category in sorted(p.loc[p.symbol.isin(top_symbols), "asset_class"].unique()):
        top = p.loc[p.symbol.isin(top_symbols) & p.asset_class.eq(category)].reset_index(drop=True)
        control = p.loc[~p.symbol.isin(top_symbols) & p.asset_class.eq(category)].reset_index(drop=True)
        if len(control) < len(top):
            raise ValueError(f"Insufficient distinct controls in {category}: {len(control)} < {len(top)}")
        difference = top[columns].to_numpy()[:, None, :] - control[columns].to_numpy()[None, :, :]
        distance = .5 * np.square(difference).sum(axis=2)
        # Sorted symbols plus stable lexicographic refinement resolve equal optima.
        rows, cols = lexicographic_assignment(distance)
        for i, j in zip(rows, cols, strict=True):
            a, b = top.iloc[i], control.iloc[j]
            records.append({
                "top_symbol": a.symbol, "control_symbol": b.symbol, "asset_class": category,
                "matching_distance": float(distance[i, j]),
                **{f"top_{name}": float(a[name]) for name in ("adv30", "vol30", *columns)},
                **{f"control_{name}": float(b[name]) for name in ("adv30", "vol30", *columns)},
            })
    return pd.DataFrame(records).sort_values("top_symbol", kind="stable").reset_index(drop=True)


def lexicographic_assignment(distance: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    remaining = list(range(distance.shape[1]))
    choices = []
    for i in range(distance.shape[0]):
        sub = distance[i:, remaining]
        a, b = linear_sum_assignment(sub)
        optimum = float(sub[a, b].sum())
        chosen = None
        for j in remaining:
            later = [c for c in remaining if c != j]
            tail = distance[i + 1:, later]
            if tail.shape[0]:
                r, c = linear_sum_assignment(tail)
                value = float(distance[i, j] + tail[r, c].sum())
            else:
                value = float(distance[i, j])
            if np.isclose(value, optimum, rtol=1e-12, atol=1e-12):
                chosen = j
                break
        if chosen is None:
            raise ValueError("Cannot resolve deterministic optimal assignment")
        choices.append(chosen)
        remaining.remove(chosen)
    return np.arange(distance.shape[0]), np.asarray(choices)


def frozen_sources() -> dict[str, str]:
    started = json.loads((BASE / "accounts/started.json").read_text())
    result = {}
    for key, digest in started["sha256"].items():
        path = Path(started["paths"][key])
        path = path if path.is_absolute() else LAB / path
        if sha(path) != digest:
            raise ValueError(f"Original account input changed: {path}")
        result[str(path.relative_to(LAB))] = digest
    if sha(SPEC) != SPEC_SHA or sha(BUNDLE_PATH) != BUNDLE_SHA:
        raise ValueError("Round contract or bundle changed")
    summary = json.loads((BASE / "inputs/summary.json").read_text())
    for name in ("ranked-candidates.parquet", "selection-decisions.csv"):
        path = BASE / "inputs" / name
        digest = summary["files"][name]
        if sha(path) != digest:
            raise ValueError(f"Original candidate source changed: {name}")
        result[str(path.relative_to(LAB))] = digest
    for path in (SPEC, BUNDLE_PATH, BASE / "inputs/summary.json",
                 BASE / "accounts/started.json", Path(__file__)):
        result[str(path.relative_to(LAB))] = sha(path)
    return result


def prepare_matches(daily: pd.DataFrame, holdings: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    candidates = pd.read_parquet(BASE / "inputs/ranked-candidates.parquet")
    decisions = pd.read_csv(BASE / "inputs/selection-decisions.csv")
    decisions["month"] = pd.to_datetime(decisions.month, utc=True)
    pool = candidates.merge(decisions[["month", "symbol", "reason"]], on=["month", "symbol"], validate="one_to_one")
    pool["entry_eligible"] = pool.reason.isin(["SELECTED", "BELOW_FIRST_TEN_ELIGIBLE"])
    pool["known_identity_error"] = [(m, s) in KNOWN_IDENTITY for m, s in zip(pool.month, pool.symbol, strict=True)]
    feature = prior_volatility(daily).rename(columns={"ts": "formation_end_day"})
    pool = pool.merge(feature, on=["symbol", "formation_end_day"], how="left", validate="many_to_one")
    classes = json.loads(BUNDLE_PATH.read_text())["observed_asset_classes"]
    pool["asset_class"] = pool.symbol.map(classes)
    pool["matching_feature_valid"] = pool.entry_eligible & ~pool.known_identity_error & pool.vol30.gt(0) & pool.vol30.notna()
    records, coverage = [], []
    for month in MONTHS:
        p = pool.loc[pool.month.eq(month) & pool.matching_feature_valid].copy()
        names = sorted(holdings.loc[holdings.month.eq(month), "symbol"])
        missing = sorted(set(names) - set(p.symbol))
        report = {"month": month, "original_candidates": int(pool.month.eq(month).sum()),
                  "valid_feature_candidates": len(p), "valid_controls": int((~p.symbol.isin(names)).sum()),
                  "top_missing_features": ";".join(missing), "status": "MATCH_UNAVAILABLE", "reason": ""}
        if missing:
            report["reason"] = "TOP10_PREENTRY_FEATURE_UNAVAILABLE"
        else:
            try:
                paired = optimal_pairs(p, names)
            except ValueError as exc:
                if not str(exc).startswith("Insufficient distinct controls"):
                    raise
                report["reason"] = str(exc)
            else:
                paired.insert(0, "month", month)
                records.append(paired)
                report["status"] = "MATCH_AVAILABLE"
        coverage.append(report)
    return pd.concat(records, ignore_index=True), pd.DataFrame(coverage), pool


def load_saved_endpoints() -> pd.DataFrame:
    parts = []
    for month in list(MONTHS) + [pd.Timestamp("2026-07-01", tz="UTC")]:
        receipt_path = BASE / f"inputs/receipts/execution-{month:%Y%m}.json"
        receipt = json.loads(receipt_path.read_text())
        for role in ("request", "frame"):
            if sha(BASE / "inputs" / receipt[f"{role}_path"]) != receipt[f"{role}_sha256"]:
                raise ValueError("Original endpoint source changed")
        f = pd.read_parquet(BASE / "inputs" / receipt["frame_path"])
        f["source_reference"] = str(receipt_path.relative_to(FAMILY))
        parts.append(f)
    result = pd.concat(parts, ignore_index=True)
    if result.duplicated(["symbol", "ts"]).any():
        raise ValueError("Duplicate original endpoints")
    return result


def required_endpoints(pairs: pd.DataFrame) -> pd.DataFrame:
    records = []
    for row in pairs.itertuples(index=False):
        for symbol in (row.top_symbol, row.control_symbol):
            for day in (row.month, row.month + pd.offsets.MonthBegin(1)):
                for minute in (0, 15):
                    records.append({"symbol": symbol, "ts": day + pd.Timedelta(minutes=minute)})
    return pd.DataFrame(records).drop_duplicates().sort_values(["ts", "symbol"]).reset_index(drop=True)


def load_new_endpoint_request(request: dict):
    """唯一新湖读取：只消费本次统一入口返回的帧与mask。"""
    return require_research_startup(request, project_root=LAB, data_root=LAB / "data")


def supplement_endpoints(needs: pd.DataFrame, old: pd.DataFrame) -> pd.DataFrame:
    present = set(zip(old.symbol, old.ts, strict=True))
    missing = needs.loc[[(s, t) not in present for s, t in zip(needs.symbol, needs.ts, strict=True)]].copy()
    missing.to_csv(OUT / "missing-endpoint-plan.csv", index=False)
    if missing.empty:
        save(OUT / "endpoint-plan.json", {"requests": [], "missing_rows": 0})
        return old
    missing["year"] = missing.ts.dt.year
    requests = []
    for year, group in missing.groupby("year", sort=True):
        symbols = sorted(group.symbol.unique())
        for offset in range(0, len(symbols), 32):
            batch = symbols[offset:offset + 32]
            target = group.loc[group.symbol.isin(batch)]
            label = f"{year}-{offset:03d}"
            request = {"schema_version": 1, "bundle_path": str(BUNDLE_PATH.relative_to(LAB)),
                       "bundle_id": "binance.v3.research_inputs.v2", "bundle_sha256": BUNDLE_SHA,
                       "mode": "price_diagnostic", "timeframe": "15m", "symbols": batch,
                       "start": target.ts.min().floor("D").isoformat(),
                       "end": (target.ts.max().floor("D") + pd.Timedelta(minutes=30)).isoformat(),
                       "gap_policy": "contiguous_segments", "asset_policy": "observed_mixed_diagnostic",
                       "backward_bars": 1, "forward_bars": 0}
            path = OUT / "requests" / f"{label}.json"
            save(path, request)
            requests.append({"label": label, "request": request, "request_sha256": sha(path),
                             "target_keys": [(s, t.isoformat()) for s, t in zip(target.symbol, target.ts, strict=True)]})
    save(OUT / "endpoint-plan.json", {"requests": requests, "missing_rows": len(missing)})
    print(f"FROZEN_ENDPOINT_REQUESTS n={len(requests)} missing_rows={len(missing)}", flush=True)
    pieces, receipts = [old], []
    for item in requests:
        label = item["label"]
        print(f"ENDPOINT_STARTUP {label} symbols={len(item['request']['symbols'])}", flush=True)
        inputs = load_new_endpoint_request(item["request"])
        save(OUT / "startup-reports" / f"{label}.json", inputs.report)
        if inputs.report["status"] != "PRICE_DIAGNOSTIC_INPUTS_VERIFIED":
            raise ValueError("Unexpected startup mode")
        keys = {(s, pd.Timestamp(t)) for s, t in item["target_keys"]}
        selected = []
        for symbol, frame in inputs.prices.items():
            mask = [(symbol, ts) in keys for ts in frame.ts]
            part = frame.loc[mask, ["symbol", "ts", "open", "research_window_valid"]].copy()
            part["source_reference"] = f"startup-reports/{label}.json"
            selected.append(part)
        compact = pd.concat(selected, ignore_index=True)
        path = OUT / "new-endpoints" / f"{label}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        compact.to_parquet(path, index=False, compression="zstd")
        receipts.append({"label": label, "frame_sha256": sha(path), "rows": len(compact),
                         "request_sha256": item["request_sha256"],
                         "report_sha256": sha(OUT / "startup-reports" / f"{label}.json")})
        pieces.append(compact)
        del inputs
        print(f"ENDPOINT_DONE {label} rows={len(compact)}", flush=True)
    save(OUT / "endpoint-receipts.json", receipts)
    result = pd.concat(pieces, ignore_index=True)
    if result.duplicated(["symbol", "ts"]).any():
        raise ValueError("New endpoints duplicate existing rows")
    return result


def leg_label(symbol: str, month: pd.Timestamp, endpoints: pd.DataFrame, terminals: list[dict]) -> dict:
    entry = month + pd.Timedelta(minutes=15)
    end = month + pd.offsets.MonthBegin(1) + pd.Timedelta(minutes=15)
    termination = [t for t in terminals if t["symbol"] == symbol and entry < t["ts"] < end]
    result = {"entry_ts": entry, "exit_ts": end, "entry_price": np.nan, "exit_price": np.nan,
              "terminal_proxy": bool(termination), "status": "LABEL_UNAVAILABLE", "reason": ""}
    for timestamp, role in ((entry, "entry"), (end, "exit")):
        if role == "exit" and termination:
            result["exit_price"] = termination[0]["center"]
            result["exit_ts"] = termination[0]["ts"]
            continue
        prior_key = (symbol, timestamp - pd.Timedelta(minutes=15))
        key = (symbol, timestamp)
        if prior_key not in endpoints.index or key not in endpoints.index:
            result["reason"] = f"{role.upper()}_ENDPOINT_MISSING"
            return result
        if not bool(endpoints.loc[prior_key, "research_window_valid"]):
            result["reason"] = f"{role.upper()}_PRIOR_ACTIVITY_UNAVAILABLE"
            return result
        price = float(endpoints.loc[key, "open"])
        if not np.isfinite(price) or price <= 0:
            result["reason"] = f"{role.upper()}_OPEN_UNAVAILABLE"
            return result
        result[f"{role}_price"] = price
    result["status"] = "LABEL_AVAILABLE"
    result["gross_price_return"] = result["exit_price"] / result["entry_price"] - 1
    result["net_price_return"] = net_roundtrip_return(result["entry_price"], result["exit_price"])
    return result


def net_roundtrip_return(entry: float, exit_price: float, cost: float = .0014) -> float:
    return float(exit_price / entry * (1 - cost) / (1 + cost) - 1)


def bootstrap_calendar(values: np.ndarray) -> dict:
    rng = np.random.default_rng(20260910)
    samples = []
    for _ in range(2000):
        starts = rng.integers(0, len(values) - 2, size=int(np.ceil(len(values) / 3)))
        indices = np.concatenate([np.arange(start, start + 3) for start in starts])[:len(values)]
        sample = values[indices]
        if np.isfinite(sample).any():
            samples.append(float(np.nanmean(sample)))
    return {"iterations": 2000, "block_months": 3, "seed": 20260910,
            "retained_missing_calendar_slots": True,
            "descriptive_mean_difference_interval_95": np.quantile(samples, [.025, .975]).tolist()}


def stats(frame: pd.DataFrame) -> dict:
    good = frame.loc[frame.status.eq("COMPARABLE")]
    if good.empty:
        return {"months": 0}
    return {"months": len(good), "top_mean_monthly_return": float(good.top_return.mean()),
            "control_mean_monthly_return": float(good.control_return.mean()),
            "mean_difference": float(good.difference.mean()), "median_difference": float(good.difference.median()),
            "top_beats_control_fraction": float(good.difference.gt(0).mean()),
            "top_positive_month_fraction": float(good.top_return.gt(0).mean()),
            "control_positive_month_fraction": float(good.control_return.gt(0).mean())}


def run() -> dict:
    if OUT.exists():
        raise FileExistsError(OUT)
    pins = frozen_sources()
    daily, daily_receipt = load_returned_daily()
    h = pd.read_parquet(BASE / "inputs-identity-corrected/holdings.parquet")
    save(OUT / "started.json", {"utc": datetime.now(timezone.utc).isoformat(), "pins": pins,
                                "daily_receipt_sha256": sha(FAMILY / "artifacts/lifecycle-inputs-20260908/summary.json"),
                                "status": "METHOD_FROZEN_BEFORE_NEW_COMPARISON_RETURNS"})
    pairs, coverage, features = prepare_matches(daily, h)
    pairs.to_csv(OUT / "matched-pairs-frozen.csv", index=False)
    coverage.to_csv(OUT / "match-coverage-frozen.csv", index=False)
    features.to_parquet(OUT / "preentry-candidate-features.parquet", index=False, compression="zstd")
    save(OUT / "matching-freeze.json", {"utc": datetime.now(timezone.utc).isoformat(),
         "pairs_sha256": sha(OUT / "matched-pairs-frozen.csv"), "coverage_sha256": sha(OUT / "match-coverage-frozen.csv"),
         "features_sha256": sha(OUT / "preentry-candidate-features.parquet"), "pair_count": len(pairs),
         "no_future_labels_computed": True, "full_candidate_rows": len(features),
         "daily_input_sha256": daily_receipt["parquet_sha256"]})
    print(f"MATCHES_FROZEN pairs={len(pairs)} months={pairs.month.nunique()}", flush=True)
    endpoints = supplement_endpoints(required_endpoints(pairs), load_saved_endpoints())
    endpoints = endpoints.set_index(["symbol", "ts"]).sort_index()
    terminals = load_terminals()
    labels = []
    for row in pairs.itertuples(index=False):
        for role, symbol in (("top", row.top_symbol), ("control", row.control_symbol)):
            result = leg_label(symbol, row.month, endpoints, terminals)
            labels.append({"month": row.month, "top_symbol": row.top_symbol, "role": role,
                           "symbol": symbol, **result})
    labels = pd.DataFrame(labels)
    labels.to_csv(OUT / "all-leg-labels.csv", index=False)
    monthly = coverage.copy()
    monthly["top_return"] = monthly["control_return"] = monthly["difference"] = np.nan
    for i, row in monthly.iterrows():
        if row.status != "MATCH_AVAILABLE":
            continue
        part = labels.loc[labels.month.eq(row.month)]
        if len(part) != 20 or not part.status.eq("LABEL_AVAILABLE").all():
            monthly.loc[i, "status"] = "LABEL_UNAVAILABLE"
            monthly.loc[i, "reason"] = ";".join(part.loc[part.status.ne("LABEL_AVAILABLE"), "symbol"])
            continue
        top = float(part.loc[part.role.eq("top"), "net_price_return"].mean())
        control = float(part.loc[part.role.eq("control"), "net_price_return"].mean())
        monthly.loc[i, ["status", "top_return", "control_return", "difference"]] = ["COMPARABLE", top, control, top - control]
    monthly.to_csv(OUT / "monthly-comparison.csv", index=False)
    year_rows, leave_rows = [], []
    for year in range(2020, 2027):
        year_rows.append({"year": year, **stats(monthly.loc[monthly.month.dt.year.eq(year)])})
        leave_rows.append({"excluded_year": year, **stats(monthly.loc[~monthly.month.dt.year.eq(year)])})
    pd.DataFrame(year_rows).to_csv(OUT / "yearly-comparison.csv", index=False)
    pd.DataFrame(leave_rows).to_csv(OUT / "leave-one-year-out.csv", index=False)
    pair_labels = labels.pivot(index=["month", "top_symbol"], columns="role", values="net_price_return").reset_index()
    pair_labels["difference"] = pair_labels.top - pair_labels.control
    pair_labels.to_csv(OUT / "paired-label-differences.csv", index=False)
    summary = {"status": "REVEALED_HISTORY_MATCHED_PRICE_DIAGNOSTIC_COMPLETE",
        "period_start": MONTHS[0] + pd.Timedelta(minutes=15),
        "period_end": pd.Timestamp("2026-07-01T00:15:00Z"), "calendar_months": 76,
        "cost_per_side": .0014, "funding_included": False, "account_replay": False,
        "matched_months": int(pairs.month.nunique()), "matched_pairs": len(pairs),
        "match_unavailable_months": int(monthly.status.eq("MATCH_UNAVAILABLE").sum()),
        "label_unavailable_months": int(monthly.status.eq("LABEL_UNAVAILABLE").sum()),
        "unavailable_legs": int(labels.status.ne("LABEL_AVAILABLE").sum()),
        "terminal_proxy_legs": int(labels.terminal_proxy.sum()), "results": stats(monthly),
        "yearly": year_rows, "leave_one_year_out": leave_rows,
        "bootstrap": bootstrap_calendar(monthly.difference.to_numpy()),
        "matching_quality": {"mean_squared_distance": float(pairs.matching_distance.mean()),
            "max_squared_distance": float(pairs.matching_distance.max()),
            "mean_top_adv30": float(pairs.top_adv30.mean()), "mean_control_adv30": float(pairs.control_adv30.mean()),
            "mean_top_vol30": float(pairs.top_vol30.mean()), "mean_control_vol30": float(pairs.control_vol30.mean()),
            "mean_abs_adv_z_gap": float((pairs.top_adv30_z - pairs.control_adv30_z).abs().mean()),
            "mean_abs_vol_z_gap": float((pairs.top_vol30_z - pairs.control_vol30_z).abs().mean())},
        "no_skipped_month_cagr_or_drawdown": True,
        "net_inputs_verified": False, "pit_universe_proven": False, "tradability_proven": False,
        "limitations": ["Original observed universe is not fully historical PIT-certified",
             "Same ADV and volatility do not control all market beta or other risk",
             "Missing match or future label months retained; no reselection and no zero return fill",
             "Round-trip diagnostic differs from original same-name monthly net trading",
             "Terminal prices remain original conditional index estimates"],
        "source_pins_unchanged": frozen_sources() == pins}
    summary["files_sha256"] = {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob("*")) if p.is_file()}
    save(OUT / "summary.json", summary)
    print(json.dumps(summary, indent=2, default=str), flush=True)
    return summary


if __name__ == "__main__":
    run()
