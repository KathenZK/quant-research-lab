"""Independent event-ledger accounting and native source/risk semantic probes."""
import argparse
from datetime import timedelta
import json
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import pandas as pd
from freqtrade.enums import ExitCheckTuple, ExitType, TradingMode
from freqtrade.optimize.backtesting import Backtesting
from freqtrade.persistence import LocalTrade

from run_replay import (INITIAL, PAIR, dump, load_input, load_source, make_config,
                        offline_exchange, sha, verify_framework)


def source_checks(source, bars):
    cls = load_source(source)
    strategy = cls({"runmode": "backtest"})
    before = [strategy.buy_pr1.value, strategy.buy_vol1.value]
    strategy.ft_load_hyper_params()
    assert before == ["CDL2CROWS", 0]
    assert [strategy.buy_pr1.value, strategy.buy_vol1.value] == ["CDLHIGHWAVE", -100]
    probes = []
    for index in [pd.RangeIndex(3), pd.date_range("2023-01-01", periods=3)]:
        for preexisting in [False, True]:
            frame = pd.DataFrame({"close": [1., 2., 3.]}, index=index)
            if preexisting:
                frame["exit_long"] = 0
            returned = strategy.populate_exit_trend(frame, {})
            assert len(returned) == 3 and not returned.exit_long.eq(1).any()
            probes.append({"index": type(index).__name__, "preexisting_zero_column": preexisting,
                           "exit_ones": 0, "nan_count": int(returned.exit_long.isna().sum())})
    full = strategy.populate_indicators(bars.copy(), {})
    full = strategy.populate_entry_trend(full, {})
    full = strategy.populate_exit_trend(full, {})
    assert not full.exit_long.eq(1).any()
    assert full.enter_long.eq(1).equals(full.CDLHIGHWAVE.eq(-100))
    for cutoff in [31, 101, 201, 501, len(bars) - 1]:
        partial = strategy.populate_indicators(bars.iloc[:cutoff].copy(), {})
        partial = strategy.populate_entry_trend(partial, {})
        for column in list(strategy.prs) + ["enter_long"]:
            pd.testing.assert_series_equal(full[column].iloc[:cutoff], partial[column])
    return {"parameter_default_before_load": before,
            "parameter_after_native_load": [strategy.buy_pr1.value, strategy.buy_vol1.value],
            "empty_tuple_probes": probes, "causal_prefixes_checked": 5,
            "all_pattern_columns_checked": len(strategy.prs),
            "rows": len(full), "entry_signals": int(full.enter_long.eq(1).sum()),
            "exit_signals": 0}, full


def risk_checks(source):
    with TemporaryDirectory(prefix="m0288-risk-") as directory:
        temp = Path(directory)
        for name in ["strategy", "user_data", "data"]:
            (temp / name).mkdir()
        (temp / "strategy/PatternRecognition.py").write_bytes(Path(source).read_bytes())
        config = make_config(temp, 0)
        with patch.object(socket.socket, "connect", side_effect=RuntimeError("OFFLINE_TEST")):
            exchange = offline_exchange(config)
            try:
                backtest = Backtesting(config, exchange=exchange)
                backtest._set_strategy(backtest.strategylist[0])
                strategy = backtest.strategy
                now = pd.Timestamp("2023-01-01", tz="UTC").to_pydatetime()

                def trade():
                    return LocalTrade(pair=PAIR, open_rate=100., amount=1., stake_amount=100.,
                                      open_date=now, fee_open=0., fee_close=0., is_short=False,
                                      leverage=1., trading_mode=TradingMode.SPOT,
                                      price_precision=.01, precision_mode_price=4)

                def exits(t, low, high, minute=0):
                    return strategy.should_exit(t, 100., now + timedelta(minutes=minute),
                                                enter=False, exit_=False, low=low, high=high)

                checks = {}
                t = trade()
                assert exits(t, 100, 108.3) == []
                assert np.isclose(t.stop_loss, 71.2)
                checks["no_trailing_before_offset"] = t.stop_loss
                t = trade()
                r = exits(t, 99, 110)
                assert [x.exit_type for x in r] == [ExitType.TRAILING_STOP_LOSS]
                assert np.isclose(t.stop_loss, 106.48)
                row = (now, 100., 110., 99., 109., 0, 0, 0, 0, None, None)
                close = backtest._get_close_rate_for_stoploss(
                    row, t, ExitCheckTuple(exit_type=ExitType.TRAILING_STOP_LOSS), 0)
                assert np.isclose(close, 105.2)
                checks["same_entry_bar_trailing_pessimistic_fill"] = close
                strategy.ft_stoploss_adjust(107., t, now + timedelta(days=1), .07, 0,
                                            low=107., high=108.)
                assert np.isclose(t.stop_loss, 106.48)
                checks["trailing_ratchet_never_lowers"] = t.stop_loss
                t = trade()
                r = exits(t, 70, 250)
                assert [x.exit_type for x in r] == [ExitType.STOP_LOSS, ExitType.ROI]
                checks["fixed_stop_precedes_roi_when_both_touched"] = [x.exit_type.value for x in r]
                t = trade()
                r = exits(t, 99, 200)
                assert [x.exit_type for x in r] == [ExitType.ROI, ExitType.TRAILING_STOP_LOSS]
                checks["roi_precedes_trailing_when_both_touched"] = [x.exit_type.value for x in r]
                expected = [(0, .936), (5270, .936), (5271, .332), (18146, .332),
                            (18147, .086), (48151, .086), (48152, 0)]
                t = trade()
                for minute, roi in expected:
                    _, actual = strategy.min_roi_reached_entry(t, minute, now)
                    assert actual == roi
                checks["roi_schedule_boundaries"] = expected
                return checks
            finally:
                exchange.close()
                Backtesting.cleanup()


def independent_ledger(run, bars, signals):
    """Rebuild balances with chronological debits/credits; no replay NAV function."""
    summary = json.loads((run / "summary.json").read_text())
    by_date = bars.set_index("date")
    result = {}
    for name in ["base", "fee0", "fee20", "delay2"]:
        trades = pd.read_csv(run / f"{name}-trades.csv")
        nav = pd.read_csv(run / f"{name}-daily-nav.csv")
        event_map = {}
        max_profit_error = 0.
        lag = summary["cases"][name]["signal_delay_bars"]
        for i, t in trades.iterrows():
            opened, closed = pd.Timestamp(t.open_date), pd.Timestamp(t.close_date)
            assert closed >= opened and opened >= pd.Timestamp("2023-01-02", tz="UTC")
            signal_date = opened - timedelta(days=lag)
            signal = signals.loc[signals.date == signal_date, "enter_long"]
            assert len(signal) == 1 and signal.iloc[0] == 1
            assert np.isclose(t.open_rate, by_date.loc[opened, "open"], atol=.011)
            expected = t.amount * (t.close_rate * (1 - t.fee_close) - t.open_rate * (1 + t.fee_open))
            error = abs(expected - t.profit_abs)
            assert error < 2e-7
            max_profit_error = max(max_profit_error, error)
            event_map.setdefault(opened, []).append((i * 2, "BUY", t))
            event_map.setdefault(closed, []).append((i * 2 + 1, "SELL", t))
        cash, quantity = INITIAL, 0.
        curve = []
        max_cash_error = max_nav_error = 0.
        for row in nav.itertuples():
            date = pd.Timestamp(row.date)
            for _, side, t in sorted(event_map.get(date, [])):
                if side == "BUY":
                    assert abs(quantity) < 1e-10
                    cash -= t.amount * t.open_rate * (1 + t.fee_open)
                    quantity += t.amount
                else:
                    assert np.isclose(quantity, t.amount)
                    cash += t.amount * t.close_rate * (1 - t.fee_close)
                    quantity -= t.amount
            eq = cash + quantity * by_date.loc[date, "close"]
            max_cash_error = max(max_cash_error, abs(cash-row.cash))
            max_nav_error = max(max_nav_error, abs(eq-row.equity))
            assert abs(eq - row.equity) < 2e-6
            assert abs(cash-row.cash) < 2e-6 and abs(quantity-row.quantity) < 1e-8
            curve.append(eq)
        assert abs(quantity) < 1e-10
        equity = np.array([INITIAL] + curve)
        returns = equity[1:] / equity[:-1] - 1
        independent = {"return": equity[-1] / INITIAL - 1,
                       "max_drawdown": (equity / np.maximum.accumulate(equity) - 1).min(),
                       "daily_sharpe": returns.mean() / returns.std(ddof=1) * np.sqrt(365)}
        for key, value in independent.items():
            assert abs(value - summary["cases"][name][key]) < 1e-9
        result[name] = {"round_trips_checked": len(trades), "days_checked": len(nav),
                        "max_per_trade_profit_error": max_profit_error,
                        "max_cash_error": max_cash_error, "max_nav_error": max_nav_error,
                        "all_entries_have_correct_prior_signal": True}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    verify_framework()
    bars = load_input(args.input)
    source, signals = source_checks(args.source, bars)
    risk = risk_checks(args.source)
    ledger = independent_ledger(args.run, bars, signals)
    # Fail closed on both source and data changes; no intentional bad file survives.
    with TemporaryDirectory(prefix="m0288-refusal-") as directory:
        bad = Path(directory) / "tampered"
        bad.write_bytes(b"invalid source and data")
        for load in [load_source, load_input]:
            try:
                load(bad)
            except ValueError:
                pass
            else:
                raise AssertionError("Hash gate failed open")
    dump(args.out, {"status": "PASS_DIAGNOSTIC_NOT_STRICT", "source_checks": source,
                    "native_risk_checks": risk, "independent_ledger": ledger,
                    "hash_gate_tamper_rejections": 2,
                    "summary_sha256": sha(args.run / "summary.json"),
                    "limitation": "Independent accounting and boundary fixtures, not a second complete trade engine or proof of intraday path"})
    print("PASS source lifecycle, causal signals, native risk boundaries, independent ledger")


if __name__ == "__main__":
    main()
