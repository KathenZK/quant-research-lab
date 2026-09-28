#!/usr/bin/env python3
"""旧 Top10 资金费逐项复现与新版源事件对账；不是新的净收益回测。

旧缓存仅经原冻结 loader 做历史复现；新版仅做治理源值审计，不授予净收益资格。
官方月档为有界证据副本，不写入或升级数据湖。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
FAMILY = Path(__file__).resolve().parents[1]
OLD_STEM = "binance-1d-mcsm-long10-diagnostic-2026-08-18"
OUT = FAMILY / "artifacts/funding-source-20260908"
VARIANT = "adv10m_top10_long_only"
PIN = {
    "bundle_id": "binance.v3.research_inputs.v2",
    "bundle_path": "research/platform/data-lake-governance/specs/binance-v3-research-input-bundle-v2.json",
    "bundle_sha256": "d2a729d03be71d67aa9c5522fb242bbf010b6c64400233c27d9cb2406f567008",
}
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research/asset-portfolios/1d-monthly-cs-momentum-ls3/scripts"))
import research_binance_1d_mcsm_ls3 as legacy
from strategy_lab.data.funding_v2 import load_funding_v2
from strategy_lab.data.research_bundle import read_bundle_contract


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_current_funding():
    bundle, selected = read_bundle_contract(ROOT, pin=PIN)
    component = bundle["components"]["funding"]
    data = load_funding_v2(ROOT / "data" / component["root"],
                           expected_manifest_sha256=component["manifest_sha256"])
    return data, selected, component


def load_legacy_reproduction():
    """不调用 ensure_daily_cache，绝不触发重建；原三脚本必须仍与旧摘要哈希一致。"""
    summary_path = FAMILY / "artifacts" / f"{OLD_STEM}-summary.json"
    summary = json.loads(summary_path.read_text())
    paths = {
        "script_sha256": FAMILY / "scripts/research_binance_1d_mcsm_long10.py",
        "engine_sha256": ROOT / "research/asset-portfolios/1d-monthly-cs-momentum-ls3/scripts/research_binance_1d_mcsm_extensions.py",
        "baseline_engine_sha256": Path(legacy.__file__),
    }
    for field, path in paths.items():
        assert sha(path) == summary[field], f"frozen engine changed: {field}"
    source_files = [summary_path, *paths.values(), legacy.CACHE_MARKER,
                    *sorted(legacy.FUNDING_CACHE.glob("month=*.parquet")),
                    *sorted(legacy.OHLCV_CACHE.glob("month=*.parquet")),
                    legacy.FUNDING_OVERLAY, legacy.OHLCV_OVERLAY]
    source_files += [FAMILY / "artifacts" / f"{OLD_STEM}-{s}.csv" for s in ("holdings", "daily-paths")]
    manifest = [{"path": str(p.relative_to(ROOT)), "sha256": sha(p), "bytes": p.stat().st_size}
                for p in source_files]
    ohlcv, funding, _ = legacy.load_panel()
    holdings = pd.read_csv(FAMILY / "artifacts" / f"{OLD_STEM}-holdings.csv")
    holdings = holdings[holdings.variant.eq(VARIANT) & holdings.status.eq("traded")].copy()
    holdings["rebalance"] = pd.to_datetime(holdings.rebalance)
    holdings = holdings.assign(sym_key=holdings.longs.str.split(",")).explode("sym_key")
    holdings["weight"] = 1.0 / holdings.n_longs
    daily = pd.read_csv(FAMILY / "artifacts" / f"{OLD_STEM}-daily-paths.csv")
    daily = daily[daily.variant.eq(VARIANT)].copy()
    daily["day"] = pd.to_datetime(daily.day)
    return ohlcv, funding, holdings, daily, manifest


def fixed_quantity_funding(quantity: float, events: pd.DataFrame) -> float:
    """仅为账户代数函数：调用方仍须独立证明日历、身份、持仓窗口。"""
    if (events.empty or not np.isfinite(quantity) or not np.isfinite(events.mark_price).all()
            or events.mark_price.le(0).any() or not np.isfinite(events.funding_rate).all()):
        raise ValueError("mark prices absent; no fixed-quantity funding amount")
    return float((-quantity * events.mark_price * events.funding_rate).sum())


def fetch_official(symbol: str, events: pd.DataFrame, receipt_dir: Path) -> dict:
    """只取固定三币 June 月档及 CHECKSUM，403/418/429 立即停止不换路由。"""
    name = f"{symbol}USDT-fundingRate-2026-06.zip"
    url = f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{symbol}USDT/{name}"
    receipt_dir.mkdir(exist_ok=True)
    receipt = {"symbol": symbol, "url": url, "audited_at": pd.Timestamp.now("UTC").isoformat(),
               "source_files_reused": (receipt_dir / name).exists(),
               "usage": "bounded source evidence, not published/trusted research data"}
    for suffix in (".CHECKSUM", ""):
        path = receipt_dir / f"{name}{suffix}"
        if path.exists():
            payload = path.read_bytes()
        else:
            try:
                with urllib.request.urlopen(url + suffix, timeout=25) as response:
                    payload = response.read()
                path.write_bytes(payload)
            except urllib.error.HTTPError as exc:
                receipt["http_error"] = exc.code
                receipt["status"] = "OFFICIAL_FETCH_FAILED"
                if exc.code in {403, 418, 429}:
                    raise RuntimeError(f"official endpoint refused {exc.code}; stop") from exc
                return receipt
            time.sleep(2)
    zip_path = receipt_dir / name
    expected = (receipt_dir / f"{name}.CHECKSUM").read_text().split()[0]
    assert sha(zip_path) == expected, "official CHECKSUM mismatch"
    with zipfile.ZipFile(zip_path) as z:
        assert z.testzip() is None
        names = z.namelist()
        assert len(names) == 1
        raw = pd.read_csv(io.BytesIO(z.read(names[0])))
    raw["ts"] = pd.to_datetime(raw.calc_time, unit="ms", utc=True)
    assert not raw.ts.duplicated().any()
    assert raw.ts.ge(pd.Timestamp("2026-06-01", tz="UTC")).all()
    assert raw.ts.lt(pd.Timestamp("2026-07-01", tz="UTC")).all()
    native = events[events.symbol.eq(f"{symbol}/USDT:USDT")
                    & events.ts.ge(pd.Timestamp("2026-06-01", tz="UTC"))
                    & events.ts.lt(pd.Timestamp("2026-07-01", tz="UTC"))].copy()
    paired = raw.merge(native[["ts", "funding_rate"]], on="ts", how="outer", indicator=True)
    paired["rate_error"] = paired.last_funding_rate - paired.funding_rate
    paired.to_csv(receipt_dir / f"{symbol}-official-event-parity.csv", index=False)
    # Complete official month and unique hour permit a diagnostic mapping only.
    # Preserve BOTH timestamps; never mutate the frozen published snapshot.
    raw["event_hour"] = raw.ts.dt.floor("h")
    native["event_hour"] = native.ts.dt.floor("h")
    assert not raw.event_hour.duplicated().any() and not native.event_hour.duplicated().any()
    mapped = raw.merge(native[["event_hour", "ts", "funding_rate"]], on="event_hour",
                       how="outer", suffixes=("_official", "_snapshot"), indicator=True, validate="one_to_one")
    mapped["offset_milliseconds"] = (mapped.ts_official - mapped.ts_snapshot).dt.total_seconds() * 1000
    mapped["rate_error"] = mapped.last_funding_rate - mapped.funding_rate
    mapped["mapping_verified"] = (mapped._merge.eq("both") & mapped.offset_milliseconds.abs().le(2000)
                                    & mapped.rate_error.abs().le(1e-12))
    mapped.to_csv(receipt_dir / f"{symbol}-official-hour-mapping.csv", index=False)
    receipt.update(status="CHECKSUM_CRC_AND_EVENT_PARITY_AUDITED", archive_sha256=expected,
                   rows=len(raw), native_rows=len(native), outer_unmatched=int(paired._merge.ne("both").sum()),
                   max_rate_error=float(paired.rate_error.abs().max()),
                   exact_timestamp_matches=int(paired._merge.eq("both").sum()),
                   official_evidence_hour_mapping_pass=bool(mapped.mapping_verified.all()),
                   mapped_timestamp_changes=int(mapped.offset_milliseconds.ne(0).sum()),
                   max_timestamp_offset_milliseconds=float(mapped.offset_milliseconds.abs().max()),
                   mapped_max_abs_rate_error=float(mapped.rate_error.abs().max()),
                   funding_rate_sum=float(raw.last_funding_rate.sum()),
                   min_rate=float(raw.last_funding_rate.min()),
                   negative_2pct_events=int(raw.last_funding_rate.eq(-0.02).sum()),
                   intervals=raw.funding_interval_hours.value_counts().sort_index().to_dict(),
                   interval_switches=int(raw.funding_interval_hours.diff().fillna(0).ne(0).sum()),
                   original_columns=[c for c in raw.columns if c not in {"ts", "event_hour"}])
    return receipt


def price_bridge(ohlcv: pd.DataFrame, holdings: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """同旧名单/旧月初 open/月末 close 的代数桥；不修复原成交和缺口。"""
    indexed = ohlcv.set_index(["sym_key", "day"])
    rows = []
    for month, h in holdings.groupby("rebalance"):
        end = min(month + pd.offsets.MonthEnd(), daily.day.max())
        month_daily = daily[daily.day.between(month, end)]
        returns, bad = [], []
        same_basket_daily = pd.Series(0.0, index=month_daily.day)
        missing_inner = []
        for item in h.itertuples():
            a = (item.sym_key, month)
            b = (item.sym_key, end)
            if a not in indexed.index or b not in indexed.index:
                bad.append(item.sym_key)
            else:
                returns.append(item.weight * (indexed.loc[b, "close"] / indexed.loc[a, "open"] - 1.0))
            prices = ohlcv[ohlcv.sym_key.eq(item.sym_key)].set_index("day").reindex(month_daily.day)
            item_returns = prices.close / prices.close.shift(1) - 1
            item_returns.iloc[0] = prices.close.iloc[0] / prices.open.iloc[0] - 1
            missing_inner.extend([f"{item.sym_key}:{v.date()}" for v in item_returns.index[item_returns.isna()]])
            # Exact legacy convention retained only for explanatory algebra.
            same_basket_daily += item.weight * item_returns.fillna(0)
        fixed = sum(returns) if not bad else np.nan
        rows.append({"month": str(month.date()), "holdings": h.longs.iloc[0],
                     "legacy_daily_price_compound": float((1 + month_daily.price_pnl).prod() - 1),
                     "same_basket_daily_weight_price_compound": float((1 + same_basket_daily).prod() - 1),
                     "fixed_unit_open_to_last_close_price": fixed,
                     "missing_endpoints": ",".join(bad),
                     "missing_internal_price_return_count": len(missing_inner),
                     "continuous_account_valid": False,
                     "note": "same old observed marks; daily path may include prior holdings overnight; no funding/cost/entry repair"})
    result = pd.DataFrame(rows)
    result["price_bridge_difference"] = result.fixed_unit_open_to_last_close_price - result.legacy_daily_price_compound
    result["pure_reweighting_difference"] = result.fixed_unit_open_to_last_close_price - result.same_basket_daily_weight_price_compound
    result["old_engine_prior_basket_overnight_effect"] = result.legacy_daily_price_compound - result.same_basket_daily_weight_price_compound
    return result


def run(fetch: bool, refresh: bool):
    assert not OUT.exists() or refresh, f"refuse overwriting evidence: {OUT}"
    OUT.mkdir(parents=True, exist_ok=refresh)
    ohlcv, funding, holdings, daily, manifest = load_legacy_reproduction()
    days = pd.DataFrame({"day": pd.date_range(daily.day.min(), daily.day.max())})
    days["rebalance"] = days.day.dt.to_period("M").dt.to_timestamp()
    held_days = holdings[["rebalance", "sym_key", "weight"]].merge(days, on="rebalance")
    joined = held_days.merge(funding, on=["day", "sym_key"], how="left", validate="one_to_one")
    joined["legacy_zero_filled_missing_rate"] = joined.funding_rate.isna()
    joined["legacy_funding_contribution"] = -joined.weight * joined.funding_rate.fillna(0)
    rebuilt = joined.groupby("day").legacy_funding_contribution.sum()
    daily["funding_rebuilt"] = daily.day.map(rebuilt)
    daily["funding_reproduction_error"] = daily.funding_rebuilt - daily.funding_pnl
    assert daily.funding_reproduction_error.abs().max() <= 1e-12
    current, pin, component = load_current_funding()
    events = current.events.copy()
    events["day"] = events.ts.dt.tz_localize(None).dt.floor("D")
    events["rebalance"] = events.day.dt.to_period("M").dt.to_timestamp()
    events["sym_key"] = events.symbol.str.replace("/USDT:USDT", "", regex=False)
    held_events = events.merge(holdings[["rebalance", "sym_key", "weight"]],
                               on=["rebalance", "sym_key"], validate="many_to_one")
    held_events["nominal_rate_contribution_not_cash"] = -held_events.weight * held_events.funding_rate
    current_daily = held_events.groupby(["day", "sym_key"]).agg(
        native_rate_sum=("funding_rate", "sum"), native_events=("ts", "count"),
        marked_events=("mark_price", "count"), archive_evidenced_events=("archive_evidence_sha256", lambda x: x.str.len().eq(64).sum()))
    parity = joined.merge(current_daily, on=["day", "sym_key"], how="left", validate="one_to_one")
    parity["native_minus_legacy_rate"] = parity.native_rate_sum - parity.funding_rate
    parity["parity_status"] = np.select([
        parity.funding_rate.isna(), parity.native_rate_sum.isna(), parity.native_minus_legacy_rate.abs().gt(1e-12)],
        ["LEGACY_RATE_MISSING", "NATIVE_EVENT_MISSING", "VALUE_DIFFERENCE"], default="SAME_RATE_SUM_NOT_COVERAGE_PROOF")
    bymonth = parity.groupby(["rebalance", "sym_key"]).agg(
        legacy_funding=("legacy_funding_contribution", "sum"), native_rate_sum=("native_rate_sum", "sum"),
        held_days=("day", "count"), missing_legacy_days=("legacy_zero_filled_missing_rate", "sum"),
        native_events=("native_events", "sum"), marked_events=("marked_events", "sum"),
        archive_evidenced_events=("archive_evidenced_events", "sum"),
        max_abs_rate_error=("native_minus_legacy_rate", lambda x: x.abs().max())).reset_index()
    bymonth["calendar_full_month_covered"] = False
    for i, row in bymonth.iterrows():
        a = row.rebalance.tz_localize("UTC")
        b = a + pd.offsets.MonthBegin(1)
        s = current.segments
        bymonth.loc[i, "calendar_full_month_covered"] = bool((s.symbol.eq(row.sym_key + "/USDT:USDT") & s.start.le(a) & s.end.ge(b)).any())
    periods = {}
    for name, a, b in [("original_full", "2020-03-01", "2026-06-30"),
                        ("2021aug_2026may", "2021-08-01", "2026-05-31"),
                        ("2026june", "2026-06-01", "2026-06-30")]:
        g = parity[parity.day.between(a, b)]
        contributions = g.groupby("sym_key").legacy_funding_contribution.sum().sort_values(ascending=False)
        months = g.groupby("rebalance").legacy_funding_contribution.sum().sort_values(ascending=False)
        d = daily[daily.day.between(a, b)]
        e = held_events[held_events.day.between(a, b)]
        periods[name] = {"legacy_funding_arithmetic_sum": float(g.legacy_funding_contribution.sum()),
            "top_assets": contributions.head(15).to_dict(), "top_months": {str(k.date()): v for k, v in months.head(12).items()},
            "positive_asset_total": float(contributions.clip(lower=0).sum()),
            "top3_share_of_net": float(contributions.head(3).sum()/contributions.sum()),
            "top3_share_of_positive_asset_contributions": float(contributions.head(3).sum()/contributions.clip(lower=0).sum()),
            "legacy_price_compound_INVALID": float((1+d.price_pnl).prod()-1),
            "legacy_net_compound_INVALID": float((1+d.net_return).prod()-1),
            "held_days": len(g), "legacy_missing_rate_days": int(g.legacy_zero_filled_missing_rate.sum()),
            "native_events": len(e), "native_marked_events": int(e.mark_price.notna().sum()),
            "native_archive_evidenced_events": int(e.archive_evidence_sha256.str.len().eq(64).sum()),
            "rate_sum_mismatch_days": int(g.native_minus_legacy_rate.abs().gt(1e-12).sum())}
    receipts = [fetch_official(s, current.events, OUT / "source-evidence") for s in ["HOME", "LAB", "H"]] if fetch else []
    largest = held_events.nlargest(100, "nominal_rate_contribution_not_cash")
    june = held_events[held_events.day.between("2026-06-01", "2026-06-30")]
    source_evidence = pd.concat([largest, june]).drop_duplicates("event_id")
    daily.to_csv(OUT / "legacy-daily-parity.csv", index=False)
    parity.to_csv(OUT / "held-day-funding-parity.csv", index=False)
    bymonth.to_csv(OUT / "asset-month-funding.csv", index=False)
    source_evidence.to_csv(OUT / "june-and-top-event-evidence.csv", index=False)
    bridge = price_bridge(ohlcv, holdings, daily)
    bridge.to_csv(OUT / "legacy-price-accounting-bridge.csv", index=False)
    summary = {"status": "FUNDING_RATE_SOURCE_AUDIT_ONLY_NOT_NET_VALID", "purpose": "governance_audit_and_frozen_reproduction",
        "generated_at": pd.Timestamp.now("UTC").isoformat(), "script_sha256": sha(Path(__file__)),
        "variant": VARIANT, "bundle_pin": pin, "funding_component": component, "legacy_inputs": manifest,
        "old_cache_original_lineage": "LINEAGE_INCOMPLETE; current content fingerprint only, not a manufactured historic input manifest",
        "legacy_funding_reproduction_max_abs_error": float(daily.funding_reproduction_error.abs().max()),
        "current_source_status": current.manifest["status"], "current_event_parity_counts": parity.parity_status.value_counts().to_dict(),
        "asset_months": len(bymonth), "full_calendar_asset_months": int(bymonth.calendar_full_month_covered.sum()),
        "price_bridge": {"months": len(bridge),
            "months_with_all_old_endpoints": int(bridge.fixed_unit_open_to_last_close_price.notna().sum()),
            "months_without_internal_price_return_missing": int(bridge.missing_internal_price_return_count.eq(0).sum()),
            "median_absolute_pure_reweighting_difference": float(bridge.pure_reweighting_difference.abs().median()),
            "largest_absolute_pure_reweighting_difference": float(bridge.pure_reweighting_difference.abs().max()),
            "continuous_account_valid": False},
        "periods": periods, "official_june_archives": receipts,
        "formula": "fixed quantity: -sum(q_i * event_mark_price_i,t * funding_rate_i,t); legacy: -sum(0.1 * daily_rate_sum_i)",
        "funding_window_verified": False, "pit_identity_proven": False, "fixed_quantity_cash_return_computed": False,
        "strategy_approved": False, "data_lake_written": False,
        "limitations": ["Legacy source results remain PERFORMANCE_INVALIDATED", "Same inherited rate sums are not independent corroboration",
                        "Original month-boundary funding assigned to new basket including 00:00; entry at 00:15 would not own that settlement",
                        "Absent marks cannot be replaced by trade close without explicitly labeled proxy", "No net account or calendar proof from arithmetic rate contributions",
                        "Price bridge retains old endpoint/zero-volume/missing-bar defects and is not corrected executable price performance"]}
    (OUT / "summary.json").write_text(json.dumps(legacy.sanitize(summary), indent=2, ensure_ascii=False, allow_nan=False)+"\n")
    print(json.dumps({k: summary[k] for k in ["status", "legacy_funding_reproduction_max_abs_error", "current_event_parity_counts", "asset_months", "full_calendar_asset_months", "periods", "official_june_archives"]}, indent=2, default=str))


def self_test():
    e = pd.DataFrame({"mark_price": [100., 200.], "funding_rate": [-0.01, -0.01]})
    assert abs(fixed_quantity_funding(0.001, e) - 0.003) < 1e-12
    e.loc[0, "mark_price"] = np.nan
    try:
        fixed_quantity_funding(0.001, e)
    except ValueError:
        pass
    else:
        raise AssertionError("must reject missing marks")
    e.loc[0, "mark_price"] = np.inf
    try:
        fixed_quantity_funding(0.001, e)
    except ValueError:
        pass
    else:
        raise AssertionError("must reject nonfinite marks")
    dates = pd.to_datetime(["2021-04-01", "2021-04-02"])
    prices = pd.DataFrame({"day": list(dates)*2, "sym_key": ["A", "A", "B", "B"],
                           "open": [100., 200., 100., 100.], "close": [200., 100., 100., 100.]})
    h = pd.DataFrame({"rebalance": [dates[0]]*2, "sym_key": ["A", "B"], "weight": [.5, .5], "longs": ["A,B"]*2})
    d = pd.DataFrame({"day": dates, "price_pnl": [.5, -.25]})
    bridge = price_bridge(prices, h, d).iloc[0]
    assert abs(bridge.same_basket_daily_weight_price_compound - .125) < 1e-12
    assert abs(bridge.fixed_unit_open_to_last_close_price) < 1e-12
    print("self-test passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-official", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--refresh-own-audit", action="store_true")
    args = parser.parse_args()
    self_test() if args.self_test else run(args.fetch_official, args.refresh_own_audit)
