"""Pinned M0288 native Freqtrade diagnostic; all replay sockets are disabled.

Strategy source remains external, exact hash required. No live trading or exchange
requests. Static precision metadata is an explicit diagnostic assumption.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import socket
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import pandas as pd
from freqtrade.enums import CandleType, RunMode, TradingMode
from freqtrade.optimize.backtesting import Backtesting
from freqtrade.resolvers import ExchangeResolver

FAMILY = Path(__file__).resolve().parents[1]
SOURCE_SHA = "cce61e4af8ed3cb8e78a5d9713aba7891ec08d1bdb1da9911c3f550424db795d"
INPUT_SHA = "48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5"
PAIR = "BTC/USDT"
INITIAL = 100000.0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    with Path(path).open("x") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def load_source(path):
    if sha(path) != SOURCE_SHA:
        raise ValueError("Original strategy SHA256 mismatch")
    module_spec = importlib.util.spec_from_file_location("m0288_original", path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module.PatternRecognition


def load_input(path):
    if sha(path) != INPUT_SHA:
        raise ValueError("Input SHA256 mismatch")
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame.open_time, unit="ms", utc=True)
    expected = pd.date_range("2022-12-01", "2024-12-31", freq="D", tz="UTC")
    if list(frame.date) != list(expected):
        raise ValueError("Missing/duplicate/out-of-order/out-of-scope bar")
    if not (frame.close_time - frame.open_time).eq(86399999).all():
        raise ValueError("Non-closed native daily candle")
    cols = ["open", "high", "low", "close", "volume"]
    if not np.isfinite(frame[cols]).all().all() or not (frame[cols] > 0).all().all():
        raise ValueError("Invalid numeric data")
    if not (frame.high >= frame[["open", "low", "close"]].max(axis=1)).all():
        raise ValueError("Invalid high")
    if not (frame.low <= frame[["open", "high", "close"]].min(axis=1)).all():
        raise ValueError("Invalid low")
    return frame[["date"] + cols].copy()


def metrics(nav):
    eq = np.r_[INITIAL, nav.equity.to_numpy()]
    returns = eq[1:] / eq[:-1] - 1
    sd = np.std(returns, ddof=1)
    return {
        "return": float(eq[-1] / INITIAL - 1),
        "annualized_return": float((eq[-1] / INITIAL) ** (365 / len(nav)) - 1),
        "max_drawdown": float(np.min(eq / np.maximum.accumulate(eq) - 1)),
        "daily_sharpe": float(np.mean(returns) / sd * np.sqrt(365)) if sd else None,
        "final_equity": float(eq[-1]),
        "days": len(nav),
    }


def make_config(temp, fee):
    return {
        "strategy": "PatternRecognition", "strategy_path": str(temp / "strategy"),
        "timeframe": "1d", "runmode": RunMode.BACKTEST,
        "trading_mode": TradingMode.SPOT, "candle_type_def": CandleType.SPOT,
        "dry_run": True, "dry_run_wallet": INITIAL, "stake_currency": "USDT",
        "stake_amount": "unlimited", "tradable_balance_ratio": .95,
        "max_open_trades": 1, "fee": fee,
        "user_data_dir": temp / "user_data", "datadir": temp / "data",
        "dataformat_ohlcv": "feather", "timerange": "20230101-20250101",
        "exchange": {"name": "binance", "pair_whitelist": [PAIR],
                     "pair_blacklist": [], "enable_ws": False},
        "pairlists": [{"method": "StaticPairList"}],
        "entry_pricing": {"price_side": "other", "use_order_book": False},
        "exit_pricing": {"price_side": "other", "use_order_book": False},
        "order_types": {"entry": "market", "exit": "market", "stoploss": "market",
                        "stoploss_on_exchange": False},
        "order_time_in_force": {"entry": "GTC", "exit": "GTC"},
        "unfilledtimeout": {"entry": 10, "exit": 10, "unit": "minutes"},
    }


def offline_exchange(config):
    exchange = ExchangeResolver.load_exchange(config, validate=False)
    # This is a model fixture, not recovered historical exchange metadata.
    market = {
        "symbol": PAIR, "id": "BTCUSDT", "base": "BTC", "quote": "USDT",
        "active": True, "spot": True, "type": "spot", "contract": False,
        "precision": {"amount": 1e-8, "price": .01},
        "limits": {"amount": {"min": 0, "max": None},
                   "cost": {"min": 0, "max": None}},
        "maker": config["fee"], "taker": config["fee"],
    }
    exchange._markets = {PAIR: market}
    exchange._api.set_markets(exchange._markets)
    exchange._api_async.set_markets(exchange._markets)
    return exchange


def reconstruct_nav(bars, trades):
    """End-of-candle marked NAV. Native intrabar exits use native event dates."""
    rows = []
    for bar in bars.itertuples():
        closed = trades[trades.close_date <= bar.date]
        opened = trades[(trades.open_date <= bar.date) & (trades.close_date > bar.date)]
        if len(opened) > 1:
            raise ValueError("Position stacking not permitted")
        cash = INITIAL + float(closed.profit_abs.sum())
        amount = 0.0
        for trade in opened.itertuples():
            cash -= trade.amount * trade.open_rate * (1 + trade.fee_open)
            amount += trade.amount
        equity = cash + amount * bar.close
        rows.append({"date": bar.date.isoformat(), "cash": cash, "quantity": amount,
                     "equity": equity})
    return pd.DataFrame(rows)


def run_case(bars, source, fee, delay):
    with TemporaryDirectory(prefix="m0288-native-") as directory:
        temp = Path(directory)
        for name in ["strategy", "user_data", "data"]:
            (temp / name).mkdir()
        (temp / "strategy/PatternRecognition.py").write_bytes(Path(source).read_bytes())
        config = make_config(temp, fee)
        with patch.object(socket.socket, "connect", side_effect=RuntimeError("OFFLINE_REPLAY")):
            exchange = offline_exchange(config)
            try:
                backtest = Backtesting(config, exchange=exchange)
                backtest._set_strategy(backtest.strategylist[0])
                strategy = backtest.strategy
                if (strategy.buy_pr1.value, strategy.buy_vol1.value) != ("CDLHIGHWAVE", -100):
                    raise ValueError("Native parameter lifecycle differs")
                if delay > 1:
                    # Sensitivity is explicit: original signal generation + additional lag.
                    original = strategy.populate_entry_trend

                    def delayed(frame, metadata):
                        result = original(frame, metadata)
                        result["enter_long"] = result.enter_long.shift(delay - 1)
                        result.loc[result.date < pd.Timestamp("2023-01-02", tz="UTC"),
                                   "enter_long"] = 0
                        return result

                    strategy.populate_entry_trend = delayed
                processed = strategy.advise_all_indicators({PAIR: bars.copy()})
                result = backtest.backtest(
                    processed=processed, start_date=pd.Timestamp("2023-01-01", tz="UTC"),
                    end_date=pd.Timestamp("2024-12-31", tz="UTC"))
                trades = result["results"].copy()
                for col in ["open_date", "close_date"]:
                    trades[col] = pd.to_datetime(trades[col], utc=True)
                evaluation = bars[bars.date >= pd.Timestamp("2023-01-01", tz="UTC")]
                nav = reconstruct_nav(evaluation, trades)
                if not np.isclose(nav.equity.iloc[-1], result["final_balance"], atol=1e-6):
                    raise ValueError("Trade-ledger final NAV differs from native wallet")
                out = metrics(nav)
                out.update({"round_trips": len(trades), "fills": len(trades) * 2,
                            "native_final_balance": result["final_balance"],
                            "exit_reasons": trades.exit_reason.value_counts().to_dict(),
                            "rejected_signals": result["rejected_signals"],
                            "fee_bps": fee * 10000, "signal_delay_bars": delay})
                return trades, nav, out
            finally:
                exchange.close()
                Backtesting.cleanup()


def benchmark(bars):
    evaluation = bars[bars.date >= pd.Timestamp("2023-01-01", tz="UTC")]
    fee = .0008
    amount = INITIAL * .95 / (evaluation.open.iloc[0] * (1 + fee))
    cash = INITIAL * .05
    rows = [{"date": b.date.isoformat(), "cash": cash, "quantity": amount,
             "equity": cash + amount * b.close} for b in evaluation.itertuples()]
    rows[-1] = {"date": rows[-1]["date"], "cash": cash + amount * evaluation.close.iloc[-1] * (1-fee),
                "quantity": 0.0, "equity": cash + amount * evaluation.close.iloc[-1] * (1-fee)}
    nav = pd.DataFrame(rows)
    result = metrics(nav)
    result.update({"round_trips": 1, "fills": 2, "fee_bps": 8,
                   "terminal": "final daily close, differs from native force_exit at final open"})
    return nav, result


def verify_framework():
    manifest = json.loads((FAMILY / "specs/framework-source-manifest.json").read_text())
    import freqtrade
    root = Path(freqtrade.__file__).parent.parent
    checks = {}
    for item in manifest["files"]:
        if not item["path"].startswith("freqtrade/"):
            continue
        digest = sha(root / item["path"])
        if digest != item["sha256"]:
            raise ValueError(f"Installed framework differs: {item['path']}")
        checks[item["path"]] = digest
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError("Refuse to overwrite frozen output")
    args.out.mkdir(parents=True)
    load_source(args.source)
    checked = verify_framework()
    bars = load_input(args.input)
    spec = json.loads((FAMILY / "specs/M0288-first-replay.json").read_text())
    summary = {"record_id": "M0288", "run_id": spec["run_id"], "fidelity_class": "HYPOTHESIS",
               "strict_reproductions": 0, "strategy_configurations": 4, "benchmark_runs": 1,
               "cases": {}, "data_quality": "DIAGNOSTIC_ONLY", "input_sha256": INPUT_SHA,
               "source_sha256": SOURCE_SHA, "framework_checked": checked,
               "spec_sha256": sha(FAMILY / "specs/M0288-first-replay.json")}
    columns = ["pair", "open_date", "close_date", "open_rate", "close_rate", "amount",
               "stake_amount", "fee_open", "fee_close", "profit_abs", "profit_ratio",
               "trade_duration", "exit_reason", "is_open"]
    for case in spec["cases"]:
        trades, nav, result = run_case(bars, args.source, case["fee_bps"] / 10000,
                                       case["signal_delay_bars"])
        trades[columns].to_csv(args.out / f"{case['name']}-trades.csv", index=False)
        nav.to_csv(args.out / f"{case['name']}-daily-nav.csv", index=False)
        summary["cases"][case["name"]] = result
    nav, result = benchmark(bars)
    nav.to_csv(args.out / "buyhold-daily-nav.csv", index=False)
    summary["cases"]["buyhold"] = result
    dump(args.out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
