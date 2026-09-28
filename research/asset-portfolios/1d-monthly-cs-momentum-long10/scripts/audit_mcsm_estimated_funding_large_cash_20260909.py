"""事后大额资金费现金专项原文复核；不改变已冻结账户或研究参数。"""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "research/asset-portfolios/1d-monthly-cs-momentum-long10"
RUN = FAMILY / "artifacts/baseline-estimate-20260909"
OUT = RUN / "large-funding-cash-source-audit"
spec = importlib.util.spec_from_file_location("funding_sources", Path(__file__).with_name("build_mcsm_baseline_estimated_funding_20260909.py"))
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)
source.OUT = OUT


def main():
    cash_path = RUN / "accounts/estimated_center/funding.parquet"
    funding_path = RUN / "funding-identity-corrected/estimated-funding-events.parquet"
    holdings_path = RUN / "inputs-identity-corrected/holdings.parquet"
    cash, funding = pd.read_parquet(cash_path), pd.read_parquet(funding_path)
    all_rows = cash.merge(funding, on=["symbol", "ts", "rate_type"], validate="one_to_one")
    all_rows["month"] = all_rows.holding_start.dt.strftime("%Y-%m")
    cash_error = (-all_rows.quantity * all_rows.estimate_mark * all_rows.rate - all_rows.funding_cash).abs().max()
    assert cash_error < 1e-7
    windows = [("RIVER", "2026-01"), ("AIA", "2025-11"), ("MYX", "2025-09"), ("PIPPIN", "2025-12")]
    plan_path = OUT / "plan.json"
    jobs = []
    for symbol, month in windows:
        code = symbol + "USDT"
        start = pd.Timestamp(month + "-01", tz="UTC") + pd.Timedelta(minutes=15)
        end = start + pd.offsets.MonthBegin(1)
        url = f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{code}/{code}-fundingRate-{month}.zip"
        api = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={code}&startTime={start.value // 10**6}&endTime={end.value // 10**6}&limit=1000"
        jobs.append({"symbol": symbol, "month": month, "zip_url": url, "checksum_url": url + ".CHECKSUM", "api_url": api})
    if not plan_path.exists():
        source.save_new(plan_path, {"status": "POSTHOC_LARGE_CASH_SOURCE_AUDIT_ONLY", "jobs": jobs, "maximum_requests": 12,
                                   "source_selection": "Four largest additional proxy-heavy cash contributors; existing LAB HOME H native evidence reused",
                                   "cash_sha256": source.sha(cash_path), "funding_sha256": source.sha(funding_path),
                                   "holdings_sha256": source.sha(holdings_path), "script_sha256": source.sha(Path(__file__)),
                                   "do_not_mutate_estimate": True, "no_rate_limit_retry": True})
    else:
        assert json.loads(plan_path.read_text())["jobs"] == jobs
    results = []
    for job in jobs:
        symbol, month = job["symbol"], job["month"]
        blob, zip_receipt = source.request_saved(job["zip_url"], f"{symbol}-{month}-funding-zip")
        check, check_receipt = source.request_saved(job["checksum_url"], f"{symbol}-{month}-funding-checksum")
        assert zip_receipt["http_status"] == check_receipt["http_status"] == 200
        assert check.decode().split()[0] == zip_receipt["raw_sha256"]
        with zipfile.ZipFile(io.BytesIO(blob)) as zipped:
            assert zipped.testzip() is None
            official = pd.read_csv(io.BytesIO(zipped.read(zipped.namelist()[0])))
        official["hour"] = official.calc_time // 3_600_000
        assert official.hour.is_unique
        api_blob, api_receipt = source.request_saved(job["api_url"], f"{symbol}-{month}-funding-api")
        assert api_receipt["http_status"] == 200
        api = pd.DataFrame(json.loads(api_blob))
        assert 0 < len(api) < 1000
        api["hour"] = api.fundingTime.astype("int64") // 3_600_000
        assert api.hour.is_unique
        selected = all_rows[all_rows.symbol.eq(symbol + "/USDT:USDT") & all_rows.month.eq(month)].copy()
        selected["hour"] = selected.ts.dt.as_unit("ns").astype("int64") // 3_600_000_000_000
        assert selected.hour.is_unique
        checked = selected.merge(api, on="hour", suffixes=("", "_api"), validate="one_to_one", how="outer", indicator=True)
        assert checked._merge.eq("both").all()
        rate_diff = (checked.fundingRate.astype(float) - checked.rate).abs()
        assert rate_diff.max() <= 1e-12
        native_ms = checked.fundingTime.astype("int64")
        frozen_ms = checked.frozen_ts.dt.as_unit("ns").astype("int64") // 1_000_000
        assert (native_ms - frozen_ms).abs().max() < 2000
        archive_comparison = checked.merge(official, on="hour", how="inner", validate="one_to_one")
        assert (archive_comparison.last_funding_rate - archive_comparison.rate).abs().max() <= 1e-12
        assert archive_comparison.fundingTime.eq(archive_comparison.calc_time).all()
        api_marks = pd.to_numeric(checked.markPrice, errors="coerce")
        usable = api_marks.gt(0) & np.isfinite(api_marks)
        native_cash = -checked.quantity * api_marks * checked.rate
        ratio = api_marks[usable] / checked.estimate_mark[usable]
        bounds = api_marks[usable].between(checked.mark_low[usable], checked.mark_high[usable])
        results.append({"symbol": symbol, "holding_month": month, "cash_model_usdt": float(selected.funding_cash.sum()),
                        "observed_events": len(selected), "api_events": len(api), "calendar_month_archive_events": len(official),
                        "calendar_month_overlap_rate_rows": len(archive_comparison), "api_source_rate_sum": float(checked.fundingRate.astype(float).sum()),
                        "api_source_rate_min": float(checked.fundingRate.astype(float).min()), "source_rate_max_abs_error": float(rate_diff.max()),
                        "native_time_max_abs_delta_ms": int((native_ms - frozen_ms).abs().max()),
                        "native_type_counts": checked.rateType.value_counts().to_dict() if "rateType" in checked else {"UNSPECIFIED_API": len(checked)},
                        "unique_hour_only_one_event": True, "api_native_marks_available": int(usable.sum()),
                        "native_to_proxy_mark_min_ratio": float(ratio.min()) if usable.any() else None,
                        "native_to_proxy_mark_max_ratio": float(ratio.max()) if usable.any() else None,
                        "native_mark_outside_conditional_minute_bounds": int((~bounds).sum()),
                        "native_cash_minus_frozen_proxy_cash_for_usable_marks": float((native_cash[usable] - checked.funding_cash[usable]).sum()) if usable.any() else None,
                        "not_replacing_frozen_model_inputs": True,
                        "zip_receipt": zip_receipt, "checksum_receipt": check_receipt, "api_receipt": api_receipt})
        print(json.dumps({k: v for k, v in results[-1].items() if not k.endswith("receipt")}), flush=True)
    final = {"status": "PASS_BOUNDED_LARGE_CASH_SOURCE_CHECK_NOT_FULL_CALENDAR_CERTIFICATION",
             "plan_sha256": source.sha(plan_path), "cash_formula_all_events_max_abs_error": float(cash_error),
             "cash_formula": "-held_coin_quantity * mark_USDT_per_coin * signed_fractional_rate",
             "funding_rate_percent_rescaling": False, "extra_contract_multiplier_applied": False,
             "source_script_sha256": source.sha(Path(__file__)), "results": results}
    source.save_new(OUT / "summary.json", final)


if __name__ == "__main__":
    main()
