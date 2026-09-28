"""Fixed, observational entry-funding mechanism test; never verified net returns.

Pre-entry features use only settled timestamps strictly before UTC month start.
The next month is attached only after these features are computed. No filtering
or parameter selection is allowed from the future holding-period funding cash.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from strategy_lab.data.funding_v2 import load_funding_v2  # noqa: E402

BASE = FAMILY / "artifacts/baseline-estimate-20260909"
NATIVE = FAMILY / "artifacts/funding-recheck-20260910/native-replay"
OUT = FAMILY / "artifacts/mechanism-round-20260910/funding-signal"
FUND_ROOT = ROOT / "data/derived/datasets/binance_perp_funding_v3_inputs_v2"
FUND_MANIFEST_SHA = "398cc19eac88d0e8c55258c118f6cae2481c6b2d1a5e6253778344b9f25a1076"
PINS = {
    "bundle_integrity_receipt": (FAMILY / "artifacts/mechanism-round-20260910/bundle-check.json",
                                 "5da453375fd8d7066868077e28b4c38ebf36d739d43d819e62379bdb04d87746"),
    "holdings": (BASE / "inputs-identity-corrected/holdings.parquet",
                 "2765cc3fade0b8c571871c5e2bfff88ad6e5bc65198a5fff35e261afa6df61e4"),
    "future_funding": (NATIVE / "native-priority-events.parquet",
                       "fc57b942e14ab29007256326404c698f379d24988a0da274fe4434b0d9c70990"),
    "native_started": (NATIVE / "started.json",
                       "a03207ccf77d38b227c955df9636b9ec3a6ee58900ebd877c03d298adb5418fa"),
    "terminal_estimates": (NATIVE / "terminals.parquet",
                           "33bc5e945d39f64f169105475d0cf5b057f0465f1e2a78b1d704c5daf7687ac2"),
    "original_center_funding_cash": (BASE / "accounts/estimated_center/funding.parquet",
                                     "21351409b2f5a8857258120c8b736f5da46a440e5a3cb3c9b5a67026b19f5e49"),
    "funding_manifest": (FUND_ROOT / "_MANIFEST.json", FUND_MANIFEST_SHA),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, default=str, allow_nan=False)
        handle.write("\n")


def sign_label(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "UNKNOWN"
    return "NEGATIVE" if value < 0 else "POSITIVE" if value > 0 else "ZERO"


def calendar_check(snapshot, symbol: str, start: pd.Timestamp, end: pd.Timestamp,
                   actual: pd.DataFrame) -> tuple[bool, str]:
    """Check retained interval/event evidence without inventing identity approval.

    Exact (start,end] bounds are supplied by the caller. This checks only the
    event calendar in the old publication; it does not re-authenticate deleted
    upstream originals, historical asset identity, or point-in-time publication.
    """
    segments = snapshot.segments
    hit = segments[segments.symbol.eq(symbol) & segments.start.le(start)
                   & segments.end.ge(end)]
    if len(hit) != 1:
        return False, "NO_SINGLE_PUBLISHED_CALENDAR_SEGMENT"
    expected = snapshot.expected
    expected = expected[expected.segment_id.eq(hit.segment_id.iloc[0])
                        & expected.ts.gt(start) & expected.ts.le(end)]
    if (actual.event_id.duplicated().any() or not actual.event_unambiguous.all()
            or set(actual.event_id) != set(expected.event_id)):
        return False, "PUBLISHED_CALENDAR_EVENT_SET_MISMATCH"
    joined = actual.merge(expected, on="event_id", suffixes=("_actual", "_expected"),
                          validate="one_to_one")
    if (not joined.ts_actual.eq(joined.ts_expected).all()
            or not joined.rate_type_actual.eq(joined.rate_type_expected).all()
            or not np.allclose(joined.funding_rate_actual, joined.funding_rate_expected,
                               rtol=0, atol=1e-12)):
        return False, "PUBLISHED_CALENDAR_VALUE_MISMATCH"
    return True, "PUBLISHED_CALENDAR_MATCH_NOT_PIT_OR_RAW_REVERIFICATION"


def pre_entry_feature(events: pd.DataFrame, month: pd.Timestamp) -> dict:
    """Conservative cutoff precedes the 00:15 trade by at least 15 minutes."""
    month = pd.Timestamp(month)
    if month.tzinfo is None:
        raise ValueError("explicit UTC month required")
    month = month.tz_convert("UTC")
    if month != month.normalize() or month.day != 1:
        raise ValueError("signal must be UTC first-of-month 00:00")
    begin = month - pd.Timedelta(hours=72)
    selected = events[events.ts.ge(begin) & events.ts.lt(month)].sort_values("ts")
    if selected.event_id.duplicated().any():
        raise ValueError("duplicate pre-entry funding event")
    if not np.isfinite(selected.funding_rate).all():
        raise ValueError("nonfinite funding must not become zero")
    base = {"signal_cutoff_exclusive": month, "pre_window_start_inclusive": begin,
            "pre_observed_events": len(selected),
            "pre_ambiguous_events": int((~selected.event_unambiguous).sum()),
            "pre_negative_observed_events": int(selected.funding_rate.lt(0).sum()),
            "pre_special_events": int(selected.rate_type.eq("Special").sum()),
            "pre_unspecified_events": int(selected.rate_type.eq("Unspecified").sum()),
            "pre_last_ts": selected.ts.max() if len(selected) else pd.NaT,
            "pre_last_age_hours": (month - selected.ts.max()).total_seconds() / 3600
            if len(selected) else np.nan}
    regular = selected[selected.rate_type.isin(["Regular", "Unspecified"])]
    # Unknown source type is explicitly an observed diagnostic, not certification.
    usable = len(regular) > 0 and selected.event_unambiguous.all()
    value = float(regular.funding_rate.sum()) if usable else None
    latest_time = regular.ts.max() if usable else pd.NaT
    latest = regular[regular.ts.eq(latest_time)] if usable else regular.iloc[:0]
    last_rate = float(latest.funding_rate.iloc[0]) if len(latest) == 1 else None
    return {**base, "pre72_rate_sum": value, "pre72_sign": sign_label(value),
            "latest_rate": last_rate, "latest_sign": sign_label(last_rate),
            "pre_observation_status": "OBSERVED_ONLY" if usable else "UNKNOWN"}


def unit_forward_return(holding: dict, events: pd.DataFrame) -> dict:
    """Per unit initial reference notional, not a self-financed account return."""
    entry = float(holding["entry_price"])
    exit_price = float(holding["exit_price"])
    if not np.isfinite([entry, exit_price]).all() or min(entry, exit_price) <= 0:
        raise ValueError("missing entry/exit price")
    if not len(events):
        raise ValueError("unobserved future funding is UNKNOWN, not zero")
    if (events.event_id.duplicated().any() or not events.symbol.eq(holding["symbol"]).all()
            or not events.ts.gt(holding["entry_ts"]).all()
            or not events.ts.le(holding["exit_ts"]).all()):
        raise ValueError("future funding holding identity/bounds differ")
    if (not np.isfinite(events[["funding_rate", "mark_center"]].to_numpy()).all()
            or not events.mark_center.gt(0).all()):
        raise ValueError("unknown rate/mark cannot be estimated as zero")
    cash = -events.mark_center / entry * events.funding_rate
    receipts = cash.clip(lower=0)
    neg_events = events[events.funding_rate.lt(0)]
    first_neg = neg_events.ts.min() if len(neg_events) else pd.NaT
    ratio = exit_price / entry
    # Standalone open+close costs: same-side reference notional convention as the
    # original account. Consecutive same-name month trades are not netted here.
    cost = .0014 + (.001 if holding.get("terminal", False) else .0014) * ratio
    return {
        "price_return": ratio - 1, "funding_return_estimate": float(cash.sum()),
        "gross_total_return_estimate": ratio - 1 + float(cash.sum()),
        "standalone_roundtrip_cost": cost,
        "standalone_cost_total_return_estimate": ratio - 1 + float(cash.sum()) - cost,
        "funding_received_per_initial_notional": float(receipts.sum()),
        "funding_paid_per_initial_notional": float(-cash.clip(upper=0).sum()),
        "future_observed_events": len(events),
        "future_negative_events": len(neg_events),
        "first_future_negative_ts": first_neg,
        "first_future_negative_after_days": (first_neg - holding["entry_ts"]).total_seconds() / 86400
        if len(neg_events) else np.nan,
        "funding_first_7d_estimate": float(cash[events.ts.le(holding["entry_ts"]
                                                                  + pd.Timedelta(days=7))].sum()),
        "receipts_at_mark_ge_2x_entry": float(receipts[events.mark_center.ge(2 * entry)].sum()),
    }


def group_metrics(frame: pd.DataFrame) -> dict:
    result = {"legs": len(frame), "months": int(frame.month.nunique())}
    for name in ("price_return", "funding_return_estimate", "gross_total_return_estimate",
                 "standalone_cost_total_return_estimate"):
        values = frame[name]
        result[f"{name}_mean"] = float(values.mean()) if len(frame) else None
        result[f"{name}_median"] = float(values.median()) if len(frame) else None
        result[f"{name}_positive_share"] = float(values.gt(0).mean()) if len(frame) else None
        monthly = frame.groupby("month")[name].mean()
        result[f"{name}_equal_month_mean"] = float(monthly.mean()) if len(monthly) else None
    return result


def paired_months(frame: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows = []
    for month, group in frame.groupby("month"):
        negative = group[group[group_col].eq("NEGATIVE")]
        rest = group[group[group_col].isin(["ZERO", "POSITIVE"])]
        if not len(negative) or not len(rest):
            continue
        row = {"month": month, "negative_legs": len(negative), "nonnegative_legs": len(rest)}
        for name in ("price_return", "funding_return_estimate", "gross_total_return_estimate",
                     "standalone_cost_total_return_estimate"):
            row[f"{name}_negative_minus_nonnegative"] = float(negative[name].mean() - rest[name].mean())
        rows.append(row)
    if not len(frame):
        return pd.DataFrame()
    calendar = pd.date_range(frame.month.min(), frame.month.max(), freq="MS", tz="UTC")
    columns = [f"{name}_negative_minus_nonnegative" for name in (
        "price_return", "funding_return_estimate", "gross_total_return_estimate",
        "standalone_cost_total_return_estimate")]
    result = pd.DataFrame(rows, columns=["month", "negative_legs", "nonnegative_legs", *columns])
    return result.set_index("month").reindex(calendar).rename_axis("month").reset_index()


def paired_summary(paired: pd.DataFrame, seed: int = 20260910, repetitions: int = 2000) -> dict:
    result = {"calendar_months": len(paired),
              "paired_months": int(paired.negative_legs.notna().sum()) if len(paired) else 0,
              "bootstrap": "3 calendar month noncircular moving blocks, gaps retained; diagnostic, not OOS",
              "seed": seed, "repetitions": repetitions}
    if not len(paired):
        return result
    rng = np.random.default_rng(seed)
    block_length = min(3, len(paired))
    blocks = int(np.ceil(len(paired) / block_length))
    starts = rng.integers(0, len(paired) - block_length + 1, size=(repetitions, blocks))
    indices = (starts[:, :, None] + np.arange(block_length)[None, None, :]).reshape(repetitions, -1)
    indices = indices[:, :len(paired)]
    for column in paired.columns:
        if not column.endswith("_negative_minus_nonnegative"):
            continue
        values = paired[column].to_numpy(float)
        valid = values[np.isfinite(values)]
        if not len(valid):
            result[column] = {"mean": None, "median": None, "bootstrap_95_percentile": None}
            continue
        sample = values[indices]
        counts = np.isfinite(sample).sum(axis=1)
        sampled = np.nansum(sample, axis=1)[counts > 0] / counts[counts > 0]
        result[column] = {"mean": float(valid.mean()), "median": float(np.median(valid)),
                          "positive_month_share": float((valid > 0).mean()),
                          "bootstrap_empty_samples": int((counts == 0).sum()),
                          "bootstrap_95_percentile": np.quantile(sampled, [.025, .975]).tolist()}
    return result


def period_groups(legs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    period_sets = [("all", legs)]
    period_sets += [(str(year), group) for year, group in legs.groupby(legs.month.dt.year)]
    period_sets += [("entry_through_2025_09", legs[legs.month.lt("2025-10-01")]),
                    ("entry_from_2025_10", legs[legs.month.ge("2025-10-01")])]
    for period, frame in period_sets:
        for signal in ("pre72_sign", "latest_sign"):
            for value in ("NEGATIVE", "ZERO", "POSITIVE", "UNKNOWN"):
                group = frame[frame[signal].eq(value)]
                rows.append({"period": period, "signal": signal, "group": value, **group_metrics(group)})
            rest = frame[frame[signal].isin(["ZERO", "POSITIVE"])]
            rows.append({"period": period, "signal": signal, "group": "NONNEGATIVE", **group_metrics(rest)})
    return pd.DataFrame(rows)


def run(contract: Path, contract_sha: str, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite retained output: {output}")
    if sha(contract) != contract_sha:
        raise ValueError("root's frozen contract differs")
    for name, (path, digest) in PINS.items():
        if digest and sha(path) != digest:
            raise ValueError(f"frozen input changed: {name}")
    native_started = json.loads(PINS["native_started"][0].read_text())
    if native_started["sha256"]["new_input"] != PINS["future_funding"][1]:
        raise ValueError("native-priority artifact does not match prior replay receipt")
    bundle_check = json.loads(PINS["bundle_integrity_receipt"][0].read_text())
    if (bundle_check["status"] != "BUNDLE_INTEGRITY_PASS_NOT_RESEARCH_READY"
            or bundle_check["funding_window_verified"] is not False
            or bundle_check["verified_components"]["funding"]["manifest_sha256"] != FUND_MANIFEST_SHA):
        raise ValueError("full bundle integrity receipt does not bind the unapproved funding snapshot")
    inputs = {name: {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}
              for name, (path, _) in PINS.items()}
    inputs["contract"] = {"path": str(contract.relative_to(ROOT)), "sha256": contract_sha}
    inputs["script"] = {"path": str(Path(__file__).relative_to(ROOT)), "sha256": sha(Path(__file__))}
    save_new(output / "started.json", {"started_utc": datetime.now(timezone.utc).isoformat(),
                                       "status": "PRECOMMITTED_OBSERVED_FUNDING_MECHANISM_DIAGNOSTIC",
                                       "inputs": inputs, "no_network": True,
                                       "funding_window_verified": False})
    snapshot = load_funding_v2(FUND_ROOT, expected_manifest_sha256=FUND_MANIFEST_SHA)
    holdings = pd.read_parquet(PINS["holdings"][0]).reset_index(drop=True)
    if len(holdings) != 760 or holdings.duplicated(["month", "symbol"]).any():
        raise ValueError("original 760 holdings changed")
    terminals = pd.read_parquet(PINS["terminal_estimates"][0])
    if len(terminals) != int(holdings.terminal.sum()) or len(terminals) != 2:
        raise ValueError("terminal estimate inventory changed")
    for terminal in terminals.itertuples(index=False):
        hit = holdings.symbol.eq(terminal.symbol) & holdings.exit_ts.eq(terminal.ts) & holdings.terminal
        if int(hit.sum()) != 1 or holdings.loc[hit, "exit_price"].notna().any():
            raise ValueError("terminal estimate does not replace one declared missing proxy")
        holdings.loc[hit, "exit_price"] = terminal.settlement_price
        holdings.loc[hit, "terminal_status"] = terminal.source_quality
    by_symbol = {symbol: group for symbol, group in snapshot.events.groupby("symbol", sort=False)}
    pre_rows, pre_events = [], []
    for holding in holdings.to_dict("records"):
        symbol = holding["symbol"]
        if symbol not in by_symbol:
            events = snapshot.events.iloc[:0]
        else:
            events = by_symbol[symbol]
        feature = pre_entry_feature(events, holding["month"])
        observed = events[events.ts.ge(feature["pre_window_start_inclusive"])
                          & events.ts.lt(feature["signal_cutoff_exclusive"])].copy()
        calendar, reason = calendar_check(snapshot, symbol,
            feature["pre_window_start_inclusive"] - pd.Timedelta(nanoseconds=1),
            feature["signal_cutoff_exclusive"] - pd.Timedelta(nanoseconds=1), observed)
        feature.update({"month": holding["month"], "symbol": symbol,
                        "pre_published_calendar_match": calendar, "pre_calendar_reason": reason})
        pre_rows.append(feature)
        observed["holding_month"] = holding["month"]
        pre_events.append(observed[["holding_month", "symbol", "ts", "event_id", "funding_rate",
                                    "rate_type", "event_unambiguous", "source"]])
    signals = pd.DataFrame(pre_rows)
    signals.to_parquet(output / "pre-entry-signals.parquet", index=False)
    pd.concat(pre_events, ignore_index=True).to_parquet(output / "pre-entry-observed-events.parquet", index=False)
    # Features are written and hashed before reading future cash or computing outcomes.
    save_new(output / "pre-entry-features-complete.json", {
        "rows": len(signals), "signals_sha256": sha(output / "pre-entry-signals.parquet"),
        "observations_sha256": sha(output / "pre-entry-observed-events.parquet"),
        "future_outcomes_used": False, "pre_calendar_match_legs": int(signals.pre_published_calendar_match.sum()),
        "signal_cutoff": "strictly before month-start 00:00 UTC; trade at 00:15",
    })
    del snapshot, by_symbol, pre_events
    future = pd.read_parquet(PINS["future_funding"][0])
    center_cash = pd.read_parquet(PINS["original_center_funding_cash"][0])
    cash_bridge = center_cash.merge(future[["ts", "symbol", "rate_type", "holding_start"]],
                                    on=["ts", "symbol", "rate_type"], validate="one_to_one")
    if len(cash_bridge) != len(future) or len(cash_bridge) != len(center_cash):
        raise ValueError("original account cash mapping incomplete")
    center_groups = {(symbol, start): group for (symbol, start), group in
                     cash_bridge.groupby(["symbol", "holding_start"], sort=False)}
    future_groups = {(symbol, start): group for (symbol, start), group in
                     future.groupby(["symbol", "holding_start"], sort=False)}
    rows, assigned = [], []
    for holding in holdings.to_dict("records"):
        key = (holding["symbol"], holding["entry_ts"])
        if key not in future_groups:
            raise ValueError(f"missing full future funding inventory for {key}")
        events = future_groups[key]
        outcome = unit_forward_return(holding, events)
        old_cash = center_groups[key]
        outcome["original_center_funding_cash_usdt"] = float(old_cash.funding_cash.sum())
        outcome["original_center_funding_received_usdt"] = float(old_cash.funding_cash.clip(lower=0).sum())
        outcome["original_center_received_at_mark_ge_2x_entry_usdt"] = float(
            old_cash.loc[old_cash.estimate_mark.ge(2 * holding["entry_price"]), "funding_cash"].clip(lower=0).sum())
        rows.append({**holding, **outcome, "asset_class_observed": ",".join(sorted(events.asset_class.unique()))})
        assigned.extend(events.event_id.tolist())
    if len(assigned) != len(set(assigned)) or set(assigned) != set(future.event_id):
        raise ValueError("future funding event assignment not complete one-to-one")
    legs = pd.DataFrame(rows).merge(signals, on=["month", "symbol"], validate="one_to_one")
    legs["negative_timing"] = np.select(
        [legs.latest_sign.eq("UNKNOWN"), legs.latest_sign.eq("NEGATIVE"), legs.future_negative_events.eq(0)],
        ["LATEST_SIGNAL_UNKNOWN", "LATEST_PRE_ENTRY_NEGATIVE", "LATEST_NONNEGATIVE_AND_NO_FUTURE_NEGATIVE"],
        default="LATEST_NONNEGATIVE_WITH_FUTURE_NEGATIVE")
    legs.to_parquet(output / "holding-leg-results.parquet", index=False)
    legs.to_csv(output / "holding-leg-results.csv", index=False)
    grouped = period_groups(legs)
    grouped.to_csv(output / "group-results.csv", index=False)
    paired = paired_months(legs, "pre72_sign")
    paired.to_csv(output / "paired-month-differences.csv", index=False)
    # The ten largest original-center account cash contributors are retrospective labels,
    # explicitly not usable for selection and never removed from the main test.
    excluded = legs.nlargest(10, "original_center_funding_cash_usdt")
    remaining = legs.drop(index=excluded.index)
    excluded.to_csv(output / "retrospective-top10-original-account-funding-legs.csv", index=False)
    period_groups(remaining).to_csv(output / "top10-excluded-sensitivity.csv", index=False)
    timing = []
    for label, group in legs.groupby("negative_timing"):
        timing.append({"timing": label, **group_metrics(group),
                       "unit_funding_sum": float(group.funding_return_estimate.sum()),
                       "unit_receipts_sum": float(group.funding_received_per_initial_notional.sum()),
                       "unit_receipts_at_mark_ge_2x_entry": float(group.receipts_at_mark_ge_2x_entry.sum()),
                       "original_center_funding_cash_usdt": float(group.original_center_funding_cash_usdt.sum()),
                       "original_center_funding_received_usdt": float(group.original_center_funding_received_usdt.sum()),
                       "original_center_received_at_mark_ge_2x_entry_usdt": float(
                           group.original_center_received_at_mark_ge_2x_entry_usdt.sum())})
    summary = {
        "status": "OBSERVED_ENTRY_FUNDING_MECHANISM_DIAGNOSTIC_NOT_OOS_OR_VERIFIED_NET",
        "scope": {"holding_legs": len(legs), "months": int(legs.month.nunique()),
                  "start_utc": holdings.entry_ts.min(), "end_utc": holdings.exit_ts.max(),
                  "future_observed_events": len(future), "fully_assigned_events": len(assigned)},
        "coverage": {"pre_observed_only_or_unknown": legs.pre_observation_status.value_counts().to_dict(),
                     "pre_published_calendar_match_legs": int(legs.pre_published_calendar_match.sum()),
                     "pre_calendar_not_proven_legs": int((~legs.pre_published_calendar_match).sum()),
                     "pre_unspecified_type_legs": int(legs.pre_unspecified_events.gt(0).sum()),
                     "pre_special_event_legs": int(legs.pre_special_events.gt(0).sum()),
                     "pre_ambiguous_legs": int(legs.pre_ambiguous_events.gt(0).sum())},
        "overall": group_metrics(legs),
        "pre72_group_counts": legs.pre72_sign.value_counts().to_dict(),
        "latest_group_counts": legs.latest_sign.value_counts().to_dict(),
        "paired_months": paired_summary(paired),
        "paired_by_era": {label: paired_summary(paired_months(group, "pre72_sign")) for label, group in
                          [("entry_through_2025_09", legs[legs.month.lt("2025-10-01")]),
                           ("entry_from_2025_10", legs[legs.month.ge("2025-10-01")])]},
        "top10_excluded_sensitivity": {"retrospective_original_center_account_cash_ranking": True,
                                       "legs_removed": len(excluded),
                                       "overall": group_metrics(remaining),
                                       "paired_months": paired_summary(paired_months(remaining, "pre72_sign"))},
        "negative_timing": timing,
        "calendar_matching_subset": group_metrics(legs[legs.pre_published_calendar_match]),
        "not_a_trading_strategy_or_account_replay": True,
        "limitations": [
            "All 76 months are revealed history; no OOS or prospective validity claim.",
            "Pre-entry rates are settled-event observations, not historically archived exchange screen predictions.",
            "Most pre72 windows lack an independent complete settlement calendar; unknown is not zero.",
            "Unspecified event type is treated as regular only for the explicitly labeled observed feature.",
            "Future cash inherits the partial-source/native-mark-priority estimate and terminal proxy assumptions.",
            "Each leg uses one unit initial reference notional; means/sums are not cumulative account returns.",
            "Standalone roundtrip costs do not net consecutive same-name month transitions.",
            "Three-calendar-month moving block bootstrap is descriptive, not independent OOS evidence.",
            "Through September 2025 versus October onward is not causal identification of a formula change.",
            "Top-ten exclusion is a retrospective sensitivity, not a tradable exclusion rule.",
        ],
        "inputs": inputs,
    }
    for name, item in inputs.items():
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError(f"input changed during run: {name}")
    summary["outputs"] = {path.name: {"sha256": sha(path), "bytes": path.stat().st_size}
                          for path in sorted(output.iterdir()) if path.is_file()}
    save_new(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    result = run(args.contract.resolve(), args.contract_sha256, args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, default=str, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
