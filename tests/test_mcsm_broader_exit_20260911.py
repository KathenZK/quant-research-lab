"""Pre-outcome tests for the two frozen breadth exit rules."""
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

DIRECTORY = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts"
sys.path.insert(0, str(DIRECTORY))
SPEC = importlib.util.spec_from_file_location("mcsm_broader_exit_0911", DIRECTORY / "research_mcsm_broader_exit_20260911.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def setup_plan():
    month = pd.Timestamp("2020-03-01", tz="UTC")
    first = pd.Timestamp("2020-03-10T00:15Z")
    holdings = pd.DataFrame({"month": month, "symbol": [f"S{i}" for i in range(10)],
                             "entry_ts": month + pd.Timedelta(minutes=15),
                             "exit_ts": pd.Timestamp("2020-04-01T00:15Z"), "weight": .1})
    features = pd.DataFrame({"symbol": holdings.symbol, "ts": first.floor("D") - MOD.DAY,
                             "return_7d": np.arange(10) * .1}).set_index(["symbol", "ts"])
    exits = pd.DataFrame({"month": [month, month], "symbol": ["S0", "S8"],
                          "exit_ts": [first, first + MOD.DAY]})
    return holdings, features, exits


def test_x5_sells_bottom_five_once_and_retains_later_original_exit():
    holdings, features, exits = setup_plan()
    plan, decisions = MOD.broaden_exit_plan(holdings, exits, features, "x5")
    assert len(plan) == 6
    first = exits.exit_ts.min()
    assert set(plan.loc[plan.exit_ts.eq(first), "symbol"]) == {"S0", "S1", "S2", "S3", "S4"}
    assert plan.loc[plan.symbol.eq("S8"), "exit_ts"].iloc[0] == first + MOD.DAY
    assert decisions[0]["first_union_count"] == 5


def test_x5_is_union_not_five_name_quota():
    holdings, features, exits = setup_plan()
    exits.loc[exits.symbol.eq("S0"), "symbol"] = "S9"
    plan, decisions = MOD.broaden_exit_plan(holdings, exits, features, "x5")
    assert len(plan) == 7
    assert decisions[0]["first_union_count"] == 6


def test_x10_exits_all_at_first_trigger_without_double_sell():
    holdings, features, exits = setup_plan()
    plan, decisions = MOD.broaden_exit_plan(holdings, exits, features, "x10")
    assert len(plan) == 10
    assert plan.exit_ts.nunique() == 1
    assert not plan.duplicated(["month", "symbol"]).any()
    assert decisions[0]["first_union_count"] == 10


def test_no_trigger_keeps_original_monthly_positions():
    holdings, features, exits = setup_plan()
    plan, decisions = MOD.broaden_exit_plan(holdings, exits.iloc[:0], features, "x10")
    assert plan.empty and not decisions


def test_tied_returns_use_symbol_order_not_future_profit():
    holdings, features, exits = setup_plan()
    features["return_7d"] = 0.
    _, decisions = MOD.broaden_exit_plan(holdings, exits, features, "x5")
    assert decisions[0]["bottom_five"] == ["S0", "S1", "S2", "S3", "S4"]


def test_missing_peer_return_blocks_ranking_no_smaller_denominator():
    holdings, features, exits = setup_plan()
    features.iloc[3, 0] = np.nan
    with pytest.raises(ValueError, match="all ten"):
        MOD.broaden_exit_plan(holdings, exits, features, "x5")


def test_future_feature_changes_do_not_change_closed_day_ranking():
    holdings, features, exits = setup_plan()
    first, _ = MOD.broaden_exit_plan(holdings, exits, features, "x5")
    for symbol in holdings.symbol:
        features.loc[(symbol, pd.Timestamp("2020-03-10", tz="UTC")), "return_7d"] = 1e8
    second, _ = MOD.broaden_exit_plan(holdings, exits, features, "x5")
    pd.testing.assert_frame_equal(first, second)


def sample_report():
    return {"status": "PRICE_DIAGNOSTIC_INPUTS_VERIFIED", "request": {"backward_bars": 1, "forward_bars": 0}, "symbols": {"S0": {
        "first_open_utc": "2020-03-10T00:00Z", "last_open_utc": "2020-03-10T00:15Z",
        "ineligible_rows": 0, "eligible_segments": 1, "rows": 2, "complete_windows": 2}}}


def test_report_proves_complete_internal_grid_without_current_future_activity_use():
    assert MOD.prior_bar_proven_by_report(sample_report(), "S0", pd.Timestamp("2020-03-10T00:15Z"))


@pytest.mark.parametrize("change", [{"ineligible_rows": 1}, {"rows": 1}, {"eligible_segments": 2}, {"complete_windows": 1}])
def test_report_does_not_silently_certify_unknown_prior_bar(change):
    report = sample_report()
    report["symbols"]["S0"].update(change)
    assert not MOD.prior_bar_proven_by_report(report, "S0", pd.Timestamp("2020-03-10T00:15Z"))


def test_report_rejects_prior_outside_returned_range():
    assert not MOD.prior_bar_proven_by_report(sample_report(), "S0", pd.Timestamp("2020-03-10T00:00Z"))


def test_report_requires_single_bar_backward_window():
    report = sample_report()
    report["request"]["backward_bars"] = 2
    assert not MOD.prior_bar_proven_by_report(report, "S0", pd.Timestamp("2020-03-10T00:15Z"))


def synthetic_full_account():
    months = pd.date_range("2020-03-01", "2026-06-01", freq="MS", tz="UTC")
    all_names = [f"S{i}" for i in range(11)]
    rows = []
    for i, month in enumerate(months):
        names = all_names[:10] if i % 2 == 0 else all_names[:9] + ["S10"]
        rows += [{"month": month, "symbol": s, "entry_ts": month + pd.Timedelta(minutes=15),
                  "exit_ts": month + pd.offsets.MonthBegin(1) + pd.Timedelta(minutes=15), "weight": .1} for s in names]
    holdings = pd.DataFrame(rows)
    ts = pd.date_range("2020-03-01T00:15Z", "2026-07-01T00:15Z", freq="MS")
    execution = pd.DataFrame([{"ts": t, "symbol": s, "price": 100.} for t in ts for s in all_names])
    daily = pd.DataFrame([{"ts": t, "symbol": s, "close": 100., "eligible": True}
                          for t in pd.date_range("2020-03-01", "2026-06-30", tz="UTC") for s in all_names])
    funding = pd.DataFrame({"symbol": pd.Series([], dtype="str"), "ts": pd.Series([], dtype="datetime64[ns, UTC]"),
                            "rate_type": pd.Series([], dtype="str")})
    first_exit = pd.Timestamp("2020-03-10T00:15Z")
    exits = pd.DataFrame({"month": [months[0]], "symbol": ["S0"], "exit_ts": [first_exit],
                          "original_exit_ts": [pd.Timestamp("2020-04-01T00:15Z")]})
    exit_prices = pd.DataFrame({"symbol": all_names, "ts": first_exit, "price": 100.})
    return holdings, execution, daily, funding, exits, exit_prices


def test_actual_quantity_monthly_cash_bridge_includes_new_names_and_initial_cost():
    holdings, execution, daily, funding, exits, prices = synthetic_full_account()
    result = MOD.replay_exit(holdings, execution, daily, funding, [], exits, prices, "price_only")
    legs, monthly, yearly = MOD.monthly_leg_cash_bridge(holdings, execution, funding, [], exits, prices, result, "price_only")
    assert len(legs) == 760 and len(monthly) == 76 and len(yearly) == 7
    assert monthly.cash_identity_error_usdt.abs().max() < 1e-6
    assert monthly.next_month_new_names_fee.iloc[0] > 0
    assert monthly.next_month_new_names_charged_to_ending_month.iloc[0] == ["S10"]
    assert monthly.fee_usdt.sum() == pytest.approx(result["metrics"]["fees_usdt"])
    assert monthly.slippage_usdt.sum() == pytest.approx(result["metrics"]["slippage_usdt"])
    assert len(legs.loc[legs.exit_kind.eq("EARLY_EXIT")]) == 1
    assert legs.loc[legs.month.eq(holdings.month.iloc[0]), "quantity"].nunique() == 1
    assert yearly.pnl_usdt.sum() == pytest.approx(result["metrics"]["final_equity"] - MOD.INITIAL)
