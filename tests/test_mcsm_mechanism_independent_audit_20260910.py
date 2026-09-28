import importlib.util
from pathlib import Path

import pandas as pd

PATH = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_mechanism_round_20260910.py"
SPEC = importlib.util.spec_from_file_location("mechanism_independent", PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def fixture():
    dates = pd.date_range("2025-01-01", "2025-02-15", tz="UTC")
    records = []
    names = [f"COIN{i}" for i in range(10)]
    for name in names:
        for i, date in enumerate(dates):
            close = 100.0 if name != "COIN0" or date < pd.Timestamp("2025-02-01", tz="UTC") else 100 - (i - 30)
            records.append({"symbol": name, "ts": date, "close": close,
                            "eligible": True, "research_segment_id": 1})
    holdings = pd.DataFrame({"month": [pd.Timestamp("2025-02-01", tz="UTC")] * 10, "symbol": names,
                             "entry_ts": [pd.Timestamp("2025-02-01T00:15Z")] * 10,
                             "exit_ts": [pd.Timestamp("2025-03-01T00:15Z")] * 10})
    return pd.DataFrame(records), holdings


def test_requires_two_closed_days_and_fifteen_minute_execution_delay():
    prices, holdings = fixture()
    target = MOD.independent_targets(prices, holdings)
    assert len(target) == 1
    assert target.iloc[0].exit_ts == pd.Timestamp("2025-02-03T00:15Z")


def test_any_missing_peer_resets_confirmation_not_smaller_median():
    prices, holdings = fixture()
    bad = prices.symbol.eq("COIN9") & prices.ts.eq(pd.Timestamp("2025-02-02", tz="UTC"))
    prices.loc[bad, "eligible"] = False
    target = MOD.independent_targets(prices, holdings)
    assert target.iloc[0].exit_ts == pd.Timestamp("2025-02-12T00:15Z")


def test_future_prices_do_not_change_an_earlier_exit():
    prices, holdings = fixture()
    first = MOD.independent_targets(prices, holdings)
    prices.loc[prices.ts.ge(pd.Timestamp("2025-02-03", tz="UTC")), "close"] = 10000
    second = MOD.independent_targets(prices, holdings)
    pd.testing.assert_frame_equal(first, second)


def test_segment_break_prevents_twenty_day_structure_signal():
    prices, holdings = fixture()
    prices.loc[prices.ts.ge(pd.Timestamp("2025-01-25", tz="UTC")), "research_segment_id"] = 2
    target = MOD.independent_targets(prices, holdings)
    assert target.iloc[0].exit_ts == pd.Timestamp("2025-02-16T00:15Z")


def test_month_end_is_not_an_extra_early_exit():
    prices, holdings = fixture()
    holdings["exit_ts"] = pd.Timestamp("2025-02-03T00:15Z")
    assert MOD.independent_targets(prices, holdings).empty
