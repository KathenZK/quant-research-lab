"""手算与因果前缀测试；全部输入为合成行情，不读取研究数据。"""

import numpy as np
import pandas as pd
import pytest

from capture import run_hold20_account


def bars(prices):
    values = np.asarray(prices, dtype=float)
    return pd.DataFrame({"ts": pd.date_range("2020-01-01", periods=len(values), freq="D", tz="UTC"),
                         "open": values, "high": values, "low": values, "close": values,
                         "symbol": "SYNTH", "research_segment_id": 1})


def signals(n, *indices):
    selected = np.zeros(n, dtype=bool)
    selected[list(indices)] = True
    return selected


@pytest.mark.parametrize("direction, expected", [(1, 1.2), (-1, 0.8)])
def test_linear_long_and_short_hand_calculation(direction, expected):
    frame = bars([50] + [100] * 19 + [120])
    result = run_hold20_account(frame, signals(21, 0), direction, fee=0, slippage=0)
    trade = result["trades"].iloc[0]
    assert trade.entry_fill_price == 100
    assert trade.quantity == 0.01
    assert trade.exit_index == 20
    assert trade.holding_bars_observed == 20
    assert trade.completed
    assert result["summary"]["final_equity_after_fee_slippage"] == pytest.approx(expected)


@pytest.mark.parametrize("direction", [1, -1])
def test_actual_fill_notional_fees_and_every_daily_mark(direction):
    frame = bars([50, 100, 120])
    fee, slip = 0.001, 0.0004
    entry = 100 * (1 + direction * slip)
    quantity = 1 / (entry * (1 + fee))
    entry_fee = quantity * entry * fee
    exit_fill = 120 * (1 - direction * slip)
    exit_fee = quantity * exit_fill * fee
    expected_entry_nav = 1 - entry_fee + direction * quantity * (100 - entry)
    expected_exit_nav = 1 - entry_fee + direction * quantity * (exit_fill - entry) - exit_fee
    result = run_hold20_account(frame, signals(3, 0), direction, horizon=2)
    equity, trade = result["equity"], result["trades"].iloc[0]
    assert trade.entry_notional + trade.entry_fee == pytest.approx(1)
    assert trade.entry_notional <= 1
    assert trade.exit_fee == pytest.approx(exit_fee)
    assert trade.exit_notional == pytest.approx(quantity * exit_fill)
    assert equity.iloc[1].equity_after_fee_slippage == pytest.approx(expected_entry_nav)
    assert equity.iloc[2].equity_after_fee_slippage == pytest.approx(expected_exit_nav)
    assert equity.fee_paid.sum() == pytest.approx(entry_fee + exit_fee)
    assert result["summary"]["total_fees"] == pytest.approx(entry_fee + exit_fee)
    assert trade.pnl_after_fee_slippage == pytest.approx(trade.price_pnl - trade.total_fees)


def test_fixed_quantity_does_not_rebalance_short_after_price_changes():
    result = run_hold20_account(bars([100, 100, 150, 100]), signals(4, 0), -1,
                               fee=0, slippage=0, horizon=3)
    assert result["equity"].equity_after_fee_slippage.tolist() == pytest.approx([1, 1, 0.5, 1])
    assert result["trades"].iloc[0].quantity == 0.01


def test_20th_bar_exit_and_same_close_new_signal_do_not_overlap():
    result = run_hold20_account(bars([100] * 42), np.ones(42, dtype=bool), 1,
                               fee=0, slippage=0)
    trades = result["trades"]
    assert trades.entry_index.tolist() == [1, 21, 41]
    assert trades.iloc[:2].exit_index.tolist() == [20, 40]
    assert trades.holding_bars_observed.tolist() == [20, 20, 1]
    assert result["summary"]["ignored_signals_while_open"] == 39
    assert result["summary"]["completed_trades"] == 2
    assert result["summary"]["censored_open_trades"] == 1


def test_signal_without_next_bar_is_pending_not_rejected_using_future():
    result = run_hold20_account(bars([100]), signals(1, 0), 1)
    assert result["trades"].empty
    assert result["summary"]["pending_signals_at_segment_end"] == 1
    assert result["equity"].iloc[0].signal_action == "QUEUED_NEXT_OPEN"


def test_immature_entry_is_taken_and_censored_without_fake_exit_cost():
    result = run_hold20_account(bars([100, 100, 110]), signals(3, 0), 1)
    trade = result["trades"].iloc[0]
    assert trade.status == "OPEN_CENSORED_SEGMENT_END"
    assert not trade.completed
    assert trade.holding_bars_observed == 2
    assert pd.isna(trade.exit_ts)
    assert trade.exit_fee == 0
    assert trade.exit_slippage_cost == 0
    assert trade.total_fees == trade.entry_fee
    assert result["equity"].iloc[-1].quantity > 0
    assert result["summary"]["completed_trades"] == 0


@pytest.mark.parametrize("direction", [1, -1])
def test_future_prefix_does_not_change_entry_fees_positions_or_nav(direction):
    frame = bars(100 + np.sin(np.arange(75) / 3) * 10 + np.arange(75) / 4)
    selected = np.arange(75) % 3 == 0
    full = run_hold20_account(frame, selected, direction)
    for length in [1, 2, 8, 20, 21, 22, 39, 61, 74]:
        prefix = run_hold20_account(frame.iloc[:length], selected[:length], direction)
        pd.testing.assert_frame_equal(prefix["equity"], full["equity"].iloc[:length].reset_index(drop=True))
        prefix_completed = prefix["trades"].loc[lambda t: t.completed.astype(bool)].reset_index(drop=True)
        full_completed = full["trades"].loc[lambda t: t.completed.astype(bool) & (t.exit_index < length)].reset_index(drop=True)
        pd.testing.assert_frame_equal(prefix_completed, full_completed, check_dtype=False)


def test_short_nonpositive_nav_is_not_clipped_or_fictitiously_liquidated():
    result = run_hold20_account(bars([100, 100, 250, 90, 80]), np.ones(5, dtype=bool), -1,
                               fee=0, slippage=0, horizon=4)
    trade = result["trades"].iloc[0]
    assert not trade.completed
    assert trade.status == "OPEN_HALTED_NONPOSITIVE_CLOSE_NAV"
    assert trade.exit_fee == 0
    assert pd.isna(trade.exit_fill_price)
    assert trade.pnl_after_fee_slippage == pytest.approx(-1.5)
    assert result["summary"]["final_equity_after_fee_slippage"] == pytest.approx(-0.5)
    assert result["summary"]["max_drawdown_after_fee_slippage"] == pytest.approx(1.5)
    assert result["summary"]["halt_index"] == 2
    assert result["summary"]["entered_trades"] == 1
    assert result["summary"]["ignored_signals_after_halt"] == 3
    assert result["equity"].iloc[3].equity_state == "HALTED_FROZEN_FAILURE_SNAPSHOT_NOT_CURRENT_MTM"
    assert np.isnan(result["equity"].iloc[3].mark_price)
    assert np.isnan(result["equity"].iloc[3].daily_return_after_fee_slippage)


def test_intraday_insolvency_is_flagged_even_when_close_recovers():
    frame = bars([100, 100, 110, 100])
    frame.loc[2, "high"] = 220
    result = run_hold20_account(frame, signals(4, 0), -1, fee=0, slippage=0, horizon=3)
    assert result["summary"]["intraday_insolvency_breach"]
    assert not result["summary"]["halted"]
    assert result["summary"]["completed_trades"] == 1
    assert result["trades"].iloc[0].min_intraday_nav == pytest.approx(-0.2)
    assert "INTRADAY_INSOLVENCY_BOUNDARY_BREACHED" in result["summary"]["execution_blockers"]
    assert not result["summary"]["executable_certification"]


def test_nonpositive_exit_after_fee_is_completed_then_halted():
    result = run_hold20_account(bars([100, 100, 197]), signals(3, 0), -1,
                               fee=0.02, slippage=0, horizon=2)
    assert result["equity"].iloc[-1].min_intraday_equity_after_entry_fee > 0
    assert result["summary"]["final_equity_after_fee_slippage"] < 0
    assert result["summary"]["halted"]
    assert result["trades"].iloc[0].completed
    assert result["trades"].iloc[0].exit_fee > 0


def test_account_reconciles_all_trade_pnl_and_signal_dispositions():
    frame = bars(100 + np.arange(67))
    result = run_hold20_account(frame, np.ones(67, dtype=bool), 1)
    summary, trades = result["summary"], result["trades"]
    assert summary["final_equity_after_fee_slippage"] == pytest.approx(1 + trades.pnl_after_fee_slippage.sum())
    assert summary["total_fees"] == pytest.approx(trades.total_fees.sum())
    assert summary["selected_signals"] == (summary["entered_trades"] + summary["pending_signals_at_segment_end"]
                                           + summary["ignored_signals_while_open"] + summary["ignored_signals_after_halt"])


def test_empty_and_no_signal_preserve_cash_without_costs():
    for frame in [bars([]), bars([100, 150, 50])]:
        result = run_hold20_account(frame, np.zeros(len(frame), dtype=bool), -1)
        assert result["trades"].empty
        assert result["summary"]["final_equity_after_fee_slippage"] == 1
        assert result["summary"]["total_fees"] == 0


@pytest.mark.parametrize("bad_case", ["gap", "duplicate", "unordered", "ohlc", "nan", "mixed_symbol", "mixed_segment", "intraday", "integer_signals"])
def test_rejects_invalid_or_mixed_segment_input(bad_case):
    frame = bars([100, 110, 120])
    selected = signals(3, 0)
    if bad_case == "gap":
        frame.loc[2, "ts"] += pd.Timedelta(days=1)
    elif bad_case == "duplicate":
        frame.loc[2, "ts"] = frame.loc[1, "ts"]
    elif bad_case == "unordered":
        frame = frame.iloc[::-1]
    elif bad_case == "ohlc":
        frame.loc[1, "high"] = 100
    elif bad_case == "nan":
        frame.loc[1, "close"] = np.nan
    elif bad_case == "mixed_symbol":
        frame.loc[1, "symbol"] = "OTHER"
    elif bad_case == "mixed_segment":
        frame.loc[1, "research_segment_id"] = 2
    elif bad_case == "intraday":
        frame["ts"] += pd.Timedelta(hours=1)
    elif bad_case == "integer_signals":
        selected = selected.astype(int)
    with pytest.raises(ValueError):
        run_hold20_account(frame, selected, 1)
