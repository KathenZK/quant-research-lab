"""Performance-blind market input preparation through the frozen startup API.

No returns are computed. Every market frame is an exact startup return, with a
separate joint daily/hourly eligibility projection for downstream replay.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Iterator

import numpy as np
import pandas as pd

LAB = Path(__file__).resolve().parents[4]
FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "src"))

from strategy_lab.data.research_bundle import read_bundle_contract  # noqa: E402
from startup_batch import create_startup_context, require_research_startup_batch  # noqa: E402


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        handle.write("\n")


def load_inputs(request: dict, context):
    """Same original validators using this run's strict fixed-scope context."""
    return require_research_startup_batch(request, context=context)


def load_batch(request: dict, out: Path, label: str, context) -> Iterator[tuple]:
    request_path = out / "requests" / f"{label}.json"
    save_json(request_path, request)
    receipt = {"request_path": str(request_path.relative_to(out)),
               "request_sha256": sha(request_path)}
    result = load_inputs(request, context)
    if set(result.prices) | set(result.failures) != set(request["symbols"]):
        raise ValueError("Batch result omitted or added requested symbols")
    report_path = out / "startup_reports" / f"{label}.json"
    save_json(report_path, result.report)
    receipt.update(startup_report_path=str(report_path.relative_to(out)),
                   startup_report_sha256=sha(report_path))
    for symbol in request["symbols"]:
        if symbol in result.failures:
            error = result.failures[symbol]
            save_json(out / "failures" / f"{label}_{symbol.split('/')[0]}.json",
                      {**receipt, "symbol": symbol, "error": error,
                       "fallback_used": False, "data_returned": False})
            print(f"NO_USABLE_WINDOW {label} {symbol}", flush=True)
            yield symbol, None, receipt, error
        else:
            yield symbol, result.prices[symbol], receipt, None


def joint_daily_projection(daily: pd.DataFrame, hourly: pd.DataFrame,
                           warmup_days: int) -> tuple[pd.DataFrame, dict]:
    """Keep all daily rows; one bad/missing hour invalidates that entire day."""
    d = daily.copy().reset_index(drop=True)
    h = hourly.copy().reset_index(drop=True)
    if d.ts.duplicated().any() or h.ts.duplicated().any():
        raise ValueError("Duplicate input timestamp")
    h["day"] = h.ts.dt.floor("D")
    hour_days = h.groupby("day", sort=True).agg(
        rows=("ts", "size"), eligible_hours=("eligible", "sum"),
        first_hour=("ts", "min"), last_hour=("ts", "max"),
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"),
        quote_volume=("quote_volume", "sum"), trade_count=("trade_count", "sum"),
    )
    aligned = hour_days.reindex(pd.DatetimeIndex(d.ts))
    aligned.index = d.index
    all_hours = (aligned.rows.eq(24) & aligned.eligible_hours.eq(24)
                 & aligned.first_hour.eq(d.ts)
                 & aligned.last_hour.eq(d.ts + pd.Timedelta(hours=23)))
    d["startup_daily_segment_id"] = d.research_segment_id
    d["startup_daily_window_valid"] = d.research_window_valid
    d["joint_eligible"] = d.eligible & all_hours
    d["hour_rows"] = aligned.rows.fillna(0).astype(int)
    d["eligible_hours"] = aligned.eligible_hours.fillna(0).astype(int)
    # The OHLC check uses only days with 24 represented hours; zero activity is
    # retained for eligibility diagnostics, never filled into market prices.
    comparable = aligned.rows.eq(24)
    differences = {}
    for column in ("open", "high", "low", "close", "volume", "quote_volume", "trade_count"):
        left = d.loc[comparable, column].to_numpy(float)
        right = aligned.loc[comparable, column].to_numpy(float)
        differences[column] = float(np.max(np.abs(left - right))) if len(left) else 0.0
        if not np.allclose(left, right, rtol=1e-12, atol=1e-9):
            raise ValueError(f"Hourly/daily aggregation mismatch: {column}")
    continuous = (d.ts.diff().eq(pd.Timedelta(days=1))
                  & d.startup_daily_segment_id.eq(d.startup_daily_segment_id.shift())
                  & d.joint_eligible.shift(fill_value=False) & d.joint_eligible)
    ids = (~continuous).cumsum()
    d["joint_segment_id"] = (d.symbol.astype("string") + "#joint" + ids.astype("string")).where(d.joint_eligible)
    d["research_segment_id"] = d.joint_segment_id
    d["research_window_valid"] = d.joint_eligible & (
        d.groupby("joint_segment_id", sort=False).cumcount() + 1 >= warmup_days)
    return d, {"daily_rows": len(d), "hourly_rows": len(h),
               "daily_ineligible_rows": int((~d.eligible).sum()),
               "hourly_ineligible_rows": int((~h.eligible).sum()),
               "joint_eligible_days": int(d.joint_eligible.sum()),
               "daily_valid_but_hourly_incomplete_days": int((d.eligible & ~all_hours).sum()),
               "joint_segments": int(d.joint_segment_id.nunique()),
               "joint_complete_feature_windows": int(d.research_window_valid.sum()),
               "aggregation_max_abs_differences": differences}


def segment_rows(d: pd.DataFrame, window: dict, warmup_days: int) -> list[dict]:
    result = []
    main_start, main_end = pd.Timestamp(window["trade_start"]), pd.Timestamp(window["end"])
    for segment_id, g in d.loc[d.joint_eligible].groupby("joint_segment_id", sort=False):
        start, end = g.ts.iloc[0], g.ts.iloc[-1] + pd.Timedelta(days=1)
        first_trade = max(main_start, start + pd.Timedelta(days=warmup_days))
        end = min(end, main_end)
        result.append({"window_id": window["window_id"], "symbol": g.symbol.iloc[0],
                       "segment_id": segment_id, "input_start": start, "end": end,
                       "first_trade_open": first_trade, "trade_start": first_trade,
                       "trade_days": max(0, int((end - first_trade) / pd.Timedelta(days=1))),
                       "trading_days": max(0, int((end - first_trade) / pd.Timedelta(days=1))),
                       "input_days": len(g), "boundary_end_due_to_data": end < main_end,
                       "full_window_contiguous": start <= pd.Timestamp(window["input_start"])
                       and end == main_end})
    return result


def save_frame(out: Path, frame: pd.DataFrame, relative: str, receipt: dict) -> dict:
    path = out / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    frame.to_parquet(path, index=False, compression="zstd")
    return {"path": relative, "sha256": sha(path), "rows": len(frame), **receipt}


def prepare(plan_path: Path, out: Path) -> None:
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite retained inputs: {out}")
    plan = json.loads(plan_path.read_text())
    source_pins = dict(plan["source_pins"])
    for relative, digest in source_pins.items():
        if sha(LAB / relative) != digest:
            raise ValueError(f"Pinned source changed: {relative}")
    contract = LAB / plan["contract_path"]
    contract_sha = sha(contract)
    if plan["contract_sha256"] != contract_sha:
        raise ValueError("Research contract changed before input preparation")
    bundle, pin = read_bundle_contract(LAB, pin=plan["bundle_pin"])
    observed = bundle["observed_asset_classes"]
    symbols = sorted(symbol for symbol, asset_class in observed.items() if asset_class == "COIN")
    if plan["symbols"] != symbols:
        raise ValueError("Requested coins differ from the entire frozen COIN universe")
    warmup = plan["warmup_days"]
    batch_size = plan["batch_size"]
    if warmup != 29 or not 1 <= batch_size <= 652:
        raise ValueError("Unexpected warmup or invalid batch size")
    supplement = LAB / plan["input_loading_supplement_path"]
    if sha(supplement) != plan["input_loading_supplement_sha256"]:
        raise ValueError("Input loading supplement changed")
    source_pins[str((FAMILY / "scripts/startup_batch.py").relative_to(LAB))] = sha(FAMILY / "scripts/startup_batch.py")
    parity_path = FAMILY / "artifacts/startup_batch_parity_20260909.json"
    parity = json.loads(parity_path.read_text())
    if (parity["status"] != "PASS" or parity["compared_frames"] != 6
            or parity["source_sha256"]["startup_batch.py"] != sha(FAMILY / "scripts/startup_batch.py")):
        raise ValueError("Current batch startup lacks successful original-API frame parity")
    out.mkdir(parents=True)
    save_json(out / "started.json", {"created_utc": datetime.now(timezone.utc).isoformat(),
              "plan_path": str(plan_path.relative_to(LAB)), "plan_sha256": sha(plan_path),
              "script_sha256": sha(Path(__file__)), "contract_path": str(contract.relative_to(LAB)),
              "contract_sha256": contract_sha, "parity_report_sha256": sha(parity_path),
              "candidate_results_computed": False})
    save_json(out / "frozen_plan.json", plan)
    save_json(out / "source_pins.json", source_pins)
    pd.DataFrame([{"symbol": s, "observed_class": c, "included": c == "COIN",
                   "reason": "OBSERVED_COIN" if c == "COIN" else "NON_COIN_OR_UNKNOWN"}
                  for s, c in sorted(observed.items())]).to_csv(out / "universe.csv", index=False)
    all_scope, all_segments, manifest = [], [], {}
    begin = time.monotonic()
    for window in plan["windows"]:
        window_id = window["window_id"]
        daily_frames, frame_status = {}, {}
        context = create_startup_context(project_root=LAB, data_root=LAB / "data", pin=pin,
            symbols=symbols, start=window["input_start"], end=window["end"])
        save_json(out / f"startup_context_{window_id}_initial.json", context.receipt())
        for tf, backward in (("1d", warmup), ("1h", 1)):
            for offset in range(0, len(symbols), batch_size):
                requested = symbols[offset:offset + batch_size]
                request = {"schema_version": 1, **pin, "mode": "price_diagnostic",
                           "timeframe": tf, "symbols": requested,
                           "start": window["input_start"], "end": window["end"],
                           "gap_policy": "contiguous_segments", "asset_policy": "crypto_only",
                           "backward_bars": backward, "forward_bars": 0}
                print(f"STARTUP {window_id} {tf} {offset}/{len(symbols)}", flush=True)
                for symbol, frame, receipt, error in load_batch(request, out, f"{window_id}_{tf}_{offset:04d}", context):
                    key = f"{window_id}/{symbol}"
                    coin = symbol.split("/")[0]
                    frame_status.setdefault(symbol, {})[tf] = error or "PRICE_DIAGNOSTIC_INPUTS_VERIFIED"
                    manifest.setdefault(key, {})
                    if frame is not None:
                        relative = f"returned/{window_id}/{tf}/{coin}.parquet"
                        manifest[key][tf] = save_frame(out, frame, relative, receipt)
                    if tf == "1d":
                        if frame is not None:
                            daily_frames[symbol] = frame
                        continue
                    row = {"window_id": window_id, "symbol": symbol,
                           "daily_status": frame_status[symbol].get("1d"),
                           "hourly_status": frame_status[symbol][tf]}
                    if frame is None or symbol not in daily_frames:
                        no_window = any("no complete eligible feature/label window" in str(value)
                                        for value in (row["daily_status"], row["hourly_status"]))
                        all_scope.append({**row, "status": "NO_USABLE_WINDOW" if no_window else "STARTUP_FAILED",
                                          "trade_days": 0, "trading_days": 0,
                                          "max_segment_trade_days": 0, "cohort": "NO_USABLE_WINDOW",
                                          "selected_segment_id": None, "full_window_contiguous": False})
                        continue
                    joint, stats = joint_daily_projection(daily_frames.pop(symbol), frame, warmup)
                    joint_path = f"joint/{window_id}/{coin}.parquet"
                    manifest[key]["joint_daily"] = save_frame(out, joint, joint_path,
                        {"source_daily_sha256": manifest[key]["1d"]["sha256"],
                         "source_hourly_sha256": manifest[key]["1h"]["sha256"]})
                    segments = segment_rows(joint, window, warmup)
                    selected = sorted(segments, key=lambda r: (-r["trade_days"], r["input_start"]))[0] if segments else None
                    selected = selected if selected and selected["trade_days"] >= 1 else None
                    for segment in segments:
                        segment["selected"] = bool(selected and segment["segment_id"] == selected["segment_id"])
                    all_segments.extend(segments)
                    full_window = any(r["full_window_contiguous"] for r in segments)
                    cohort = ("FULL_433D" if full_window else "PARTIAL_GE180D"
                              if selected and selected["trade_days"] >= 180 else "SHORT_LT180D"
                              if selected else "NO_USABLE_WINDOW")
                    all_scope.append({**row, **{k: v for k, v in stats.items() if k != "aggregation_max_abs_differences"},
                                      "status": "JOINT_PRICE_WINDOWS_VERIFIED" if selected else "NO_USABLE_WINDOW",
                                      "cohort": cohort,
                                      "trade_days": sum(r["trade_days"] for r in segments),
                                      "trading_days": selected["trade_days"] if selected else 0,
                                      "selected_segment_id": selected["segment_id"] if selected else None,
                                      "selected_input_start": selected["input_start"] if selected else None,
                                      "selected_trade_start": selected["trade_start"] if selected else None,
                                      "selected_end": selected["end"] if selected else None,
                                      "boundary_end_due_to_data": selected["boundary_end_due_to_data"] if selected else None,
                                      "max_segment_trade_days": max((r["trade_days"] for r in segments), default=0),
                                      "full_window_contiguous": full_window,
                                      "aggregation_max_abs_difference": max(stats["aggregation_max_abs_differences"].values())})
        save_json(out / f"startup_context_{window_id}.json", context.receipt())
        save_json(out / f"frames_manifest_{window_id}.json", {k: v for k, v in manifest.items() if k.startswith(window_id + "/")})
        pd.DataFrame([r for r in all_scope if r["window_id"] == window_id]).to_csv(out / f"scope_{window_id}.csv", index=False)
        print(f"WINDOW_COMPLETE {window_id} seconds={time.monotonic()-begin:.1f}", flush=True)
    pd.DataFrame(all_scope).to_csv(out / "scope.csv", index=False)
    pd.DataFrame(all_segments).to_csv(out / "segments.csv", index=False)
    pd.DataFrame([r for r in all_segments if r["selected"]]).to_csv(out / "selected_segments.csv", index=False)
    save_json(out / "frames_manifest.json", manifest)
    save_json(out / "summary.json", {
        "completed_utc": datetime.now(timezone.utc).isoformat(), "seconds": time.monotonic() - begin,
        "observed_contracts": len(observed), "included_coins": len(symbols),
        "excluded_non_coin_or_unknown": len(observed) - len(symbols),
        "symbol_window_rows": len(all_scope),
        "startup_failed_symbol_windows": sum(r["status"] == "STARTUP_FAILED" for r in all_scope),
        "no_usable_symbol_windows": sum(r["status"] == "NO_USABLE_WINDOW" for r in all_scope),
        "cohorts": pd.Series([r["cohort"] for r in all_scope]).value_counts().to_dict(),
        "candidate_results_computed": False, "funding_window_verified": False,
        "historical_identity_verified": False, "pit_universe_proven": False})
    for relative, digest in source_pins.items():
        if sha(LAB / relative) != digest:
            raise ValueError(f"Pinned source changed during preparation: {relative}")
    if sha(contract) != contract_sha:
        raise ValueError("Contract changed during preparation")
    if sha(supplement) != plan["input_loading_supplement_sha256"]:
        raise ValueError("Input loading supplement changed during preparation")
    save_json(out / "checksums.json", {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=FAMILY / "specs/input-plan-v3-20260909.json")
    parser.add_argument("--output", type=Path, default=FAMILY / "artifacts/inputs_20260909")
    args = parser.parse_args()
    prepare(args.config.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
