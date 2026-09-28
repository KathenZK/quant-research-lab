from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    ROOT
    / "research/asset-portfolios/4h-ma7-regime-continuation/scripts"
    / "research_binance_4h_ma7_regime_continuation_p0.py"
)
SPEC = importlib.util.spec_from_file_location("binance_4h_ma7_rc_p0", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hourly_frame(
    *,
    periods: int = 160,
    start: str = "2024-01-01T00:00:00Z",
    symbol: str = "TEST/USDT:USDT",
) -> pd.DataFrame:
    ts = pd.date_range(start, periods=periods, freq="1h", tz="UTC")
    close = 100.0 + np.arange(periods) * 0.1
    return pd.DataFrame(
        {
            "ts": ts,
            "exchange": "binance",
            "symbol": symbol,
            "market_type": "perp",
            "base_asset": "TEST",
            "quote_asset": "USDT",
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close + 0.05,
            "volume": 1.0,
            "quote_volume": 2_000_000.0,
            "trade_count": 1,
            "vwap": close,
            "is_closed": True,
            "source": "unit",
            "taker_buy_volume": 0.5,
            "taker_buy_quote_volume": 1_000_000.0,
        }
    )


@pytest.mark.local_data
def test_frozen_config_and_manifest_hashes_match() -> None:
    config = MODULE.validate_frozen_config()
    assert config["study_id"] == "BIN-4H-MA7-RC-P0"
    assert sha256_file(MODULE.CONFIG_PATH) == MODULE.EXPECTED_CONFIG_SHA256
    assert (
        sha256_file(ROOT / config["data"]["dataset_manifest"])
        == MODULE.EXPECTED_MANIFEST_SHA256
    )


def test_1h_to_4h_ohlcv_aggregation_and_phase_from_real_1h() -> None:
    frame = hourly_frame(periods=8)
    bars, audit = MODULE.aggregate_4h(frame, 0)
    assert len(bars) == 2
    assert bars.iloc[0]["open"] == pytest.approx(frame.iloc[0]["open"])
    assert bars.iloc[0]["high"] == pytest.approx(frame.iloc[:4]["high"].max())
    assert bars.iloc[0]["low"] == pytest.approx(frame.iloc[:4]["low"].min())
    assert bars.iloc[0]["close"] == pytest.approx(frame.iloc[3]["close"])
    assert bars.iloc[0]["quote_volume"] == pytest.approx(8_000_000.0)
    assert bars.iloc[0]["bars_1h"] == 4
    assert audit["incomplete_or_illegal_4h_groups"] == 0

    shifted, _ = MODULE.aggregate_4h(frame, 1)
    assert shifted.iloc[0]["ts"] == pd.Timestamp("2024-01-01T01:00:00Z")


def test_missing_duplicate_illegal_and_unclosed_1h_do_not_enter_4h() -> None:
    missing = hourly_frame(periods=8).drop(index=2)
    bars, audit = MODULE.aggregate_4h(missing, 0)
    assert len(bars) == 1
    assert audit["incomplete_or_illegal_4h_groups"] == 1

    duplicate = pd.concat([hourly_frame(periods=4), hourly_frame(periods=1)], ignore_index=True)
    bars, audit = MODULE.aggregate_4h(duplicate, 0)
    assert len(bars) == 0
    assert audit["incomplete_or_illegal_4h_groups"] == 1

    illegal = hourly_frame(periods=4)
    illegal.loc[0, "high"] = illegal.loc[0, "low"] - 1.0
    bars, _ = MODULE.aggregate_4h(illegal, 0)
    assert bars.empty

    open_bar = hourly_frame(periods=4)
    open_bar.loc[0, "is_closed"] = False
    bars, _ = MODULE.aggregate_4h(open_bar, 0)
    assert bars.empty


def test_sma_periods_atr20_and_atr_scale_have_no_future_information() -> None:
    bars, _ = MODULE.aggregate_4h(hourly_frame(periods=200), 0)
    enriched = MODULE.add_indicators(bars)
    row = enriched.iloc[41]
    assert row["sma5"] == pytest.approx(enriched["close"].iloc[37:42].mean())
    assert row["sma7"] == pytest.approx(enriched["close"].iloc[35:42].mean())
    assert row["sma10"] == pytest.approx(enriched["close"].iloc[32:42].mean())
    assert row["sma42"] == pytest.approx(enriched["close"].iloc[:42].mean())
    assert row["atr20"] == pytest.approx(enriched["tr"].iloc[22:42].mean())
    assert enriched.iloc[42]["atr_scale"] == pytest.approx(enriched.iloc[41]["atr20"])

    shocked = bars.copy()
    shocked.loc[42, "high"] += 50.0
    enriched_shocked = MODULE.add_indicators(shocked)
    assert enriched_shocked.iloc[42]["atr_scale"] == pytest.approx(enriched.iloc[42]["atr_scale"])


def test_strict_cross_and_next_4h_open_entry_timing() -> None:
    ts = pd.date_range("2024-01-01", periods=12, freq="4h", tz="UTC")
    close = [10, 10, 10, 10, 10, 10, 9, 12, 8, 8, 8, 8]
    panel = pd.DataFrame(
        {
            "symbol": ["TEST/USDT:USDT"] * 12,
            "base_asset": ["TEST"] * 12,
            "quote_asset": ["USDT"] * 12,
            "ts": ts,
            "phase_hour": [0] * 12,
            "open": np.arange(100, 112, dtype=float),
            "high": np.array(close, dtype=float) + 1,
            "low": np.array(close, dtype=float) - 1,
            "close": close,
            "volume": 1.0,
            "quote_volume": 1.0,
            "trade_count": 1,
            "bars_1h": 4,
            "first_1h_ts": ts,
            "last_1h_ts": ts + pd.Timedelta(hours=3),
            "all_closed": True,
        }
    )
    panel = MODULE.add_indicators(panel)
    for period in MODULE.MA_PERIODS:
        panel[f"sma{period}"] = 10.0
    panel["atr_scale"] = 1.0
    panel["atr_quintile"] = pd.Series([3] * 12, dtype="Int64")
    panel["in_trading_pool"] = True
    panel["eligible"] = True
    panel["event_day"] = panel["ts"].dt.normalize()
    events = MODULE.build_event_candidates(panel, 7)
    long_event = events.loc[events["direction"].eq("long")].iloc[0]
    assert long_event["ts"] == ts[7]
    assert long_event["signal_ts"] == ts[7] + pd.Timedelta(hours=4)
    assert long_event["entry_ts"] == ts[8]
    assert long_event["entry_price"] == pytest.approx(108.0)
    assert (events.loc[events["direction"].eq("short"), "ts"] == ts[8]).any()


def test_first_hit_uses_atr_scale_mirrors_sides_and_adverse_wins_same_1h() -> None:
    event = pd.DataFrame(
        {
            "symbol": ["TEST/USDT:USDT", "TEST/USDT:USDT"],
            "base_asset": ["TEST", "TEST"],
            "quote_asset": ["USDT", "USDT"],
            "ts": pd.to_datetime(["2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"], utc=True),
            "phase_hour": [0, 0],
            "block_id": [1, 1],
            "ma_period": [7, 7],
            "direction": ["long", "short"],
            "side": [1, -1],
            "signal_ts": pd.to_datetime(["2024-01-01T04:00:00Z", "2024-01-01T04:00:00Z"], utc=True),
            "entry_ts": pd.to_datetime(["2024-01-01T04:00:00Z", "2024-01-01T04:00:00Z"], utc=True),
            "entry_price": [100.0, 100.0],
            "atr_scale": [2.0, 2.0],
            "cross_event": [True, True],
            "in_trading_pool": [True, True],
            "atr_quintile": pd.Series([3, 3], dtype="Int64"),
        }
    )
    hourly = hourly_frame(periods=121, start="2024-01-01T04:00:00Z")
    hourly["open"] = 100.0
    hourly["close"] = 100.0
    hourly["high"] = 104.1
    hourly["low"] = 95.9
    fourh, _ = MODULE.aggregate_4h(hourly, 0)
    fourh = MODULE.add_indicators(fourh)
    hourly_by_symbol = MODULE.hourly_maps(hourly)
    fourh_by_symbol = MODULE.panel_maps(fourh)
    out = MODULE.enrich_outcomes(event, hourly_by_symbol, fourh_by_symbol, {})
    assert out.iloc[0]["first_hit_label"] == "adverse_first"
    assert bool(out.iloc[0]["same_1h_dual_hit_adverse_first"]) is True
    assert out.iloc[1]["first_hit_label"] == "adverse_first"
    assert bool(out.iloc[1]["same_1h_dual_hit_adverse_first"]) is True


def test_incomplete_future_excluded_from_first_hit_stats() -> None:
    events = pd.DataFrame(
        {
            "phase_hour": [0, 0],
            "ma_period": [7, 7],
            "direction": ["long", "long"],
            "first_hit_label": ["favorable_first", "incomplete_future"],
            "same_1h_dual_hit_adverse_first": [False, False],
            "symbol": ["A", "A"],
            "utc_week": ["2024-W01", "2024-W01"],
        }
    )
    controls = pd.DataFrame(
        {
            "direction": ["long"],
            "first_hit_label": ["adverse_first"],
            "control_stratum_has_event": [True],
            "control_weight": [1.0],
            "symbol": ["A"],
            "utc_week": ["2024-W01"],
        }
    )
    result = MODULE.build_first_hit_stats(events, controls, np.random.default_rng(1))
    assert result.loc[result["direction"].eq("long"), "event_count"].iloc[0] == 1
    assert result.loc[result["direction"].eq("long"), "incomplete_future_events"].iloc[0] == 1


def test_mfe_mae_direction_and_fixed_horizon_index() -> None:
    row = pd.Series({"side": -1, "entry_price": 100.0})
    path = pd.DataFrame({"high": [103.0, 102.0], "low": [99.0, 95.0]})
    mfe, mae = MODULE._directional_high_low(row, path)
    assert mfe.max() == pytest.approx(0.05)
    assert mae.min() == pytest.approx(-0.03)


def test_ma7_recross_survival_time() -> None:
    event = pd.DataFrame(
        {
            "symbol": ["TEST/USDT:USDT"],
            "base_asset": ["TEST"],
            "quote_asset": ["USDT"],
            "ts": pd.to_datetime(["2024-01-01T00:00:00Z"], utc=True),
            "phase_hour": [0],
            "block_id": [1],
            "ma_period": [7],
            "direction": ["long"],
            "side": [1],
            "signal_ts": pd.to_datetime(["2024-01-01T04:00:00Z"], utc=True),
            "entry_ts": pd.to_datetime(["2024-01-01T04:00:00Z"], utc=True),
            "entry_price": [100.0],
            "atr_scale": [10.0],
            "cross_event": [True],
            "in_trading_pool": [True],
            "atr_quintile": pd.Series([3], dtype="Int64"),
        }
    )
    hourly = hourly_frame(periods=121, start="2024-01-01T04:00:00Z")
    fourh_ts = pd.date_range("2024-01-01T00:00:00Z", periods=35, freq="4h", tz="UTC")
    fourh = pd.DataFrame(
        {
            "symbol": "TEST/USDT:USDT",
            "phase_hour": 0,
            "ts": fourh_ts,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": [101.0, 101.0, 101.0, 99.0, *([99.0] * 31)],
            "sma7": 100.0,
        }
    )
    out = MODULE.enrich_outcomes(event, MODULE.hourly_maps(hourly), MODULE.panel_maps(fourh), {})
    assert out.iloc[0]["ma7_recross_bars"] == 3
    assert out.iloc[0]["same_side_survival_bars"] == 2


def test_pit_membership_and_stratified_non_cross_weights_are_causal() -> None:
    bars, _ = MODULE.aggregate_4h(hourly_frame(periods=6 * 4 * 35), 0)
    bars.loc[bars["ts"].dt.normalize() < pd.Timestamp("2024-01-31T00:00:00Z"), "quote_volume"] = 1.0
    eligibility, _ = MODULE.build_universe(bars)
    day31 = eligibility.loc[eligibility["day"].eq(pd.Timestamp("2024-01-31T00:00:00Z"))].iloc[0]
    assert not bool(day31["eligible"])

    events = pd.DataFrame(
        {
            "symbol": ["A", "A"],
            "calendar_year": [2024, 2024],
            "direction": ["long", "long"],
            "atr_quintile": pd.Series([1, 1], dtype="Int64"),
        }
    )
    controls = pd.DataFrame(
        {
            "symbol": ["A", "A", "A", "B"],
            "calendar_year": [2024, 2024, 2024, 2024],
            "direction": ["long", "long", "long", "long"],
            "atr_quintile": pd.Series([1, 1, 1, 1], dtype="Int64"),
        }
    )
    weighted = MODULE.apply_control_weights(events, controls)
    assert weighted.loc[weighted["symbol"].eq("A"), "control_weight"].iloc[0] == pytest.approx(2 / 3)
    assert weighted.loc[weighted["symbol"].eq("B"), "control_weight"].iloc[0] == 0


def test_fee_slippage_and_funding_direction() -> None:
    entry = pd.Timestamp("2024-01-01T00:00:00Z")
    exit_ = pd.Timestamp("2024-01-01T08:00:00Z")
    lookup = {
        "TEST/USDT:USDT": MODULE.FundingLookup(
            timestamps=np.array([], dtype="datetime64[ns]"),
            rates=np.array([]),
            by_second={
                pd.Timestamp("2024-01-01T08:00:00Z"): 0.001,
            },
        )
    }
    long_cost, complete, expected, missing = MODULE.funding_cost_for_window(
        lookup, "TEST/USDT:USDT", entry, exit_, 1
    )
    short_cost, _, _, _ = MODULE.funding_cost_for_window(
        lookup, "TEST/USDT:USDT", entry, exit_, -1
    )
    assert complete is True
    assert expected == 1
    assert missing == 0
    assert long_cost == pytest.approx(0.001)
    assert short_cost == pytest.approx(-0.001)
    assert MODULE.ROUND_TRIP_4BPS == pytest.approx(0.0028)
    assert MODULE.ROUND_TRIP_8BPS == pytest.approx(0.0036)


def test_cutoff_and_reproducible_bh() -> None:
    config = MODULE.load_json(MODULE.CONFIG_PATH)
    assert config["data"]["cutoff_exclusive_utc"] == "2026-08-24T08:00:00Z"
    q = MODULE.benjamini_hochberg(pd.Series([0.01, 0.04, 0.03, 0.20]))
    assert q.tolist() == pytest.approx([0.04, 0.0533333333, 0.0533333333, 0.20])
    assert MODULE.SEED == 20260902
