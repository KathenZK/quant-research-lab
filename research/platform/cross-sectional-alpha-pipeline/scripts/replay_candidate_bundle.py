"""Run with python -I from an independently restored bundle, no repository imports."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

import numpy as np
import pandas as pd


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    root = Path(__file__).resolve().parent
    # Verify all bytes before importing executable evidence or parsing inputs.
    manifest = json.loads((root / "manifest.json").read_text())
    for row in manifest["files"]:
        p = root / row["path"]
        if not p.resolve().is_relative_to(root) or hashlib.sha256(p.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"changed evidence {row['path']}")
    engine = load("restored_frozen_engine", root / "code/engine.py")
    oracle = load("independent_account_oracle", root / "code/accounting.py")
    config = json.loads((root / "config.json").read_text())
    raw = pd.read_parquet(root / "input/joint_daily.parquet")
    raw = raw.loc[raw.joint_segment_id.eq(config["segment_id"])].rename(columns={"ts": "timestamp"}).reset_index(drop=True)
    hourly = pd.read_parquet(root / "input/hourly.parquet")
    hourly = hourly.loc[hourly.ts.ge(pd.Timestamp(config["input_start"])) & hourly.ts.lt(pd.Timestamp(config["end"]))]
    hourly = hourly.rename(columns={"ts": "timestamp"}).reset_index(drop=True)
    for frame, freq in [(raw, "D"), (hourly, "h")]:
        frame["timestamp"] = pd.to_datetime(frame.timestamp, utc=True).dt.as_unit("ns")
        expected = pd.date_range(config["input_start"], config["end"], freq=freq, inclusive="left").as_unit("ns")
        pd.testing.assert_index_equal(pd.DatetimeIndex(frame.timestamp), expected, exact=True, check_names=False)
        assert frame[["eligible", "observed_valid", "is_closed"]].all().all()
    assert raw.joint_eligible.all() and raw.hour_rows.eq(24).all() and raw.eligible_hours.eq(24).all()
    daily = engine.enrich_features(engine.features(raw))
    indicators = ["ma", "ma30", "prev_ma30", "ma30_ready", "atr", "rsi", "slope", "cross",
                  "accel1", "accel2", "ma_step", "prev_ma_step", "ma_step_change", "sm_delta",
                  "sm_previous_delta", "sm_previous_atr", "sm_previous_atr2"]
    original_features = pd.read_parquet(root / "reference/daily_features.parquet")
    pd.testing.assert_frame_equal(daily[indicators], original_features[indicators], check_exact=True)
    daily["ready"] = (daily[["eligible", "observed_valid", "is_closed", "joint_eligible"]].all(axis=1)
                      & np.isfinite(daily[["ma", "atr", "rsi", "slope"]]).all(axis=1) & daily.atr.gt(0))
    start = daily.loc[daily.ready, "timestamp"].iloc[0] + pd.Timedelta(days=1)
    assert start == pd.Timestamp(config["start"])
    prefix_lengths = [14, 15, 18, 29, 90]
    for n in prefix_lengths:
        prefix = engine.enrich_features(engine.features(raw.iloc[:n]))
        pd.testing.assert_frame_equal(prefix[indicators], daily.iloc[:n][indicators], check_exact=True)
    events = []
    result = engine.simulate(
        hourly, daily, engine.Config(**config["parameters"]), start, pd.Timestamp(config["end"]), None, 0., entry_events=events)
    summary, trades, equity, stops = result[:4]
    for name, frame in [("trades.csv", trades), ("stops.csv", stops)]:
        assert (root / "reference" / name).read_text() == frame.to_csv(index=False), name
    event_frame = pd.DataFrame(events).reindex(columns=list(dict.fromkeys(engine.ENTRY_EVENT_COLUMNS + engine.CANDIDATE_EVENT_COLUMNS)))
    assert (root / "reference/entry_events.csv").read_text() == event_frame.to_csv(index=False)
    pd.testing.assert_frame_equal(pd.read_parquet(root / "reference/equity.parquet"), equity, check_exact=True)
    original_summary = json.loads((root / "reference/summary.json").read_text())
    serial_summary = json.loads(json.dumps(summary, default=str))
    assert all(original_summary[k] == value for k, value in serial_summary.items())
    # Independent cash algebra uses quantities and actual fills, not kernel PnL.
    account = oracle.LinearAccount(10000, 1)
    reconciliation = []
    for row in trades.to_dict("records"):
        before = account.cash
        for leg, sign in [("entry", 1), ("exit", -1)]:
            price = float(row[leg + "_price"])
            account.apply({"id": f"{row['trade_id']}:{leg}", "ts": str(row[leg + "_time"]),
                           "kind": "fill", "symbol": "HYPE/USDT:USDT",
                           "quantity": float(row["side"] * row["qty"] * sign), "price": price,
                           "fee_rate": config["parameters"]["fee"], "marks": {"HYPE/USDT:USDT": price}})
        assert abs(account.cash - row["end_equity"]) < 1e-8
        assert abs(account.cash - before - row["net_pnl"]) < 1e-8
        reconciliation.append({"trade_id": row["trade_id"], "reference_end_equity": row["end_equity"],
                               "independent_end_equity": account.cash, "absolute_error": abs(account.cash-row["end_equity"])})
    assert abs(account.fees - original_summary["fee_total"]) < 1e-8
    assert abs(account.cash - original_summary["ending_equity"]) < 1e-8
    report = {"status": "EXACT_RESTORE_AND_INDEPENDENT_CASH_RECONCILIATION_PASS",
              "execution_root": str(root), "python": sys.version, "numpy": np.__version__, "pandas": pd.__version__,
              "feature_rows": len(daily), "hourly_rows": len(hourly), "indicator_columns": indicators,
              "prefix_checks": prefix_lengths, "trades": len(trades), "stop_rows": len(stops),
              "decision_rows": len(event_frame), "equity_rows": len(equity),
              "csv_byte_exact": ["trades", "stops", "entry_events"], "equity_values_exact": True,
              "engine_summary_fields_exact": len(serial_summary), "independent_max_cash_error": max(r["absolute_error"] for r in reconciliation),
              "ending_equity": account.cash, "fees": account.fees,
              "price_only_diagnostic": True, "funding_window_verified": False,
              "prospective_observation": False, "reconciliation": reconciliation}
    output = Path(sys.argv[1]).resolve()
    with output.open("x") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(json.dumps({k: v for k, v in report.items() if k != "reconciliation"}, indent=2))


if __name__ == "__main__":
    main()
