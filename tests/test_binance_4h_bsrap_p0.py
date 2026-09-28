"""Economic execution and causal-window checks for the independent P0 diagnostic."""

import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

BASE = (
    Path(__file__).resolve().parents[1]
    / "research/asset-portfolios/4h-bull-strong-rsi-atr-pullback/scripts"
)


def module(name):
    spec = importlib.util.spec_from_file_location(name, BASE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


r = module("replay_p0")
b = module("build_p0_features")
VAR = {
    "id": "test",
    "rsi_period": 14,
    "rsi_threshold": 30,
    "bull": True,
    "strong": True,
    "atr": True,
    "exit": "ratchet",
}
CONFIG = {
    "named_symbols": [],
    "evaluation_start": "2026-01-01T00:00:00Z",
    "data_end": "2026-01-02T00:00:00Z",
}


def frame(n=6):
    return pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=n, freq="4h", tz="UTC"),
            "symbol": "BTC/USDT:USDT",
            "open": 100.0,
            "high": 110.0,
            "low": 99.0,
            "close": 105.0,
            "research_segment_id": "seg",
            "eligible": True,
            "feature_valid": True,
            "liquid": True,
            "bull": True,
            "strong": True,
            "atr_down": True,
            "natr_down": True,
            "rsi14": [20.0] + [50.0] * (n - 1),
            "stop_band": 90.0,
            "atr14": 5.0,
            "mom30_lag1d": 0.2,
            "adv7": 1e9,
        }
    )


def test_next_open_and_entry_bar_stop_both_cost_sides():
    f = frame()
    f.loc[1, ["open", "low"]] = [102.0, 89.0]
    trades, _ = r.replay_symbol(f, VAR, CONFIG)
    assert len(trades) == 1
    t = trades[0]
    assert t["entry_time"] == f.ts.iloc[1]
    assert t["exit_price_before_slip"] == 90
    assert t["gross_return"] == pytest.approx(90 / 102 - 1)
    expected = 90 * 0.9996 / (102 * 1.0004)
    assert t["cost_adjusted_ex_funding_4bps"] == pytest.approx(
        expected - 1 - 0.001 * (1 + expected)
    )


def test_stop_does_not_see_same_bar_new_band():
    f = frame()
    f.loc[1, ["low", "close", "stop_band"]] = [92.0, 110.0, 100.0]
    f.loc[2, ["open", "low"]] = [108.0, 99.0]
    trades, _ = r.replay_symbol(f, VAR, CONFIG)
    assert trades[0]["exit_bar_open"] == f.ts.iloc[2]
    assert trades[0]["exit_price_before_slip"] == 100.0


def test_ratchet_never_moves_down_and_raw_band_control_differs():
    f = frame()
    f.loc[1, "stop_band"] = 98.0
    f.loc[2, "stop_band"] = 80.0
    f.loc[3, "low"] = 95.0
    ratchet, _ = r.replay_symbol(f, VAR, CONFIG)
    raw, _ = r.replay_symbol(f, VAR | {"exit": "raw_band"}, CONFIG)
    assert ratchet[0]["exit_price_before_slip"] == 98.0
    assert raw[0]["status"] == "censored"


def test_gap_through_stop_uses_worse_open_not_stale_line():
    f = frame()
    f.loc[2, ["open", "low", "close"]] = [80.0, 75.0, 82.0]
    trades, _ = r.replay_symbol(f, VAR, CONFIG)
    assert trades[0]["exit_price_before_slip"] == 80.0
    assert trades[0]["reason"] == "gap_through_stop"


def test_stop_already_above_next_open_rejects_entry():
    f = frame()
    f.loc[1, ["open", "low"]] = [85.0, 80.0]
    trades, c = r.replay_symbol(f, VAR, CONFIG)
    assert not trades and c["entry_invalid_stop"] == 1


def test_missing_price_censors_holding_instead_of_fabricating_exit():
    f = frame().drop(index=2).reset_index(drop=True)
    trades, _ = r.replay_symbol(f, VAR, CONFIG)
    assert trades[0]["status"] == "censored"
    assert trades[0]["reason"] == "price_gap_or_identity_boundary"
    assert "gross_return" not in trades[0]


def test_no_entry_signal_carried_across_gap():
    f = frame().drop(index=1).reset_index(drop=True)
    trades, c = r.replay_symbol(f, VAR, CONFIG)
    assert not trades and c["entry_missing_or_boundary"] == 1


def test_market_bull_off_and_rsi_recovery_do_not_exit():
    f = frame()
    f.loc[1:, "bull"] = False
    trades, _ = r.replay_symbol(f, VAR, CONFIG)
    assert trades[0]["status"] == "censored"
    assert trades[0]["reason"] == "right_censor_cutoff"


def test_new_stop_above_close_exits_only_next_open():
    f = frame()
    f.loc[1, ["close", "stop_band"]] = [105.0, 106.0]
    f.loc[2, ["open", "low"]] = [104.0, 103.0]
    trades, _ = r.replay_symbol(f, VAR, CONFIG)
    assert trades[0]["exit_bar_open"] == f.ts.iloc[2]
    assert trades[0]["exit_price_before_slip"] == 104.0
    assert trades[0]["reason"] == "new_stop_marketable_next_open"


def test_features_prefix_invariant_and_reset_requires_new_warmup():
    n = 500
    x = 100 + np.arange(n) * 0.1 + np.sin(np.arange(n))
    f = pd.DataFrame(
        {
            "symbol": "BTC/USDT:USDT",
            "ts": pd.date_range("2026-01-01", periods=n, freq="4h", tz="UTC"),
            "open": x,
            "high": x + 1,
            "low": x - 1,
            "close": x,
            "quote_volume": 1e8,
            "eligible": True,
            "research_window_valid": True,
            "research_segment_id": "a",
        }
    )
    full = b.features(f)
    prefix = b.features(f.iloc[:300])
    pd.testing.assert_frame_equal(full.iloc[:300], prefix)
    f.loc[250:, "research_segment_id"] = "b"
    split = b.features(f)
    assert split.atr14.iloc[250:263].isna().all()
    assert not split.feature_valid.iloc[250:436].any()
    assert split.feature_valid.iloc[436]


def test_wilder_arithmetic_seed_and_flat_rsi_convention():
    assert b.wilder([np.nan, 1, 2, 3, 6], 3)[3:].tolist() == [2.0, 10 / 3]
    with pytest.raises(ValueError, match="contiguous"):
        b.wilder([1, 2, np.nan, 3, 4], 3)
