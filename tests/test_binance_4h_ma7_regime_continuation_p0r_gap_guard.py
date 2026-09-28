from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "research/asset-portfolios/4h-ma7-regime-continuation/scripts"
P0_PATH = SCRIPT_DIR / "research_binance_4h_ma7_regime_continuation_p0.py"
GG_PATH = SCRIPT_DIR / "binance_4h_ma7_rc_gap_guard.py"
CLI_PATH = SCRIPT_DIR / "research_binance_4h_ma7_regime_continuation_p0r_gap_guard.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


P0 = load_module("binance_4h_ma7_rc_p0_for_gap_tests", P0_PATH)
GG = load_module("binance_4h_ma7_rc_gap_guard", GG_PATH)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hourly_frame(
    *,
    periods: int = 160,
    start: str = "2024-01-01T00:00:00Z",
    symbol: str = "TEST/USDT:USDT",
    close: np.ndarray | None = None,
) -> pd.DataFrame:
    ts = pd.date_range(start, periods=periods, freq="1h", tz="UTC")
    if close is None:
        close = 100.0 + np.arange(periods) * 0.1
    close = np.asarray(close, dtype=float)
    return pd.DataFrame(
        {
            "ts": ts,
            "exchange": "binance",
            "symbol": symbol,
            "market_type": "perp",
            "base_asset": symbol.split("/")[0],
            "quote_asset": "USDT",
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
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


def fourh_from_hourly(hourly: pd.DataFrame, phase: int = 0) -> pd.DataFrame:
    bars, _ = P0.aggregate_4h(hourly, phase)
    return P0.add_indicators(bars)


def attach_pool(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    out["in_trading_pool"] = True
    out["eligible"] = True
    out["event_day"] = (out["ts"] + pd.Timedelta(hours=4)).dt.normalize()
    out["atr_quintile"] = pd.Series([3] * len(out), dtype="Int64")
    return out


def long_event_row(
    *,
    ts: pd.Timestamp,
    symbol: str = "TEST/USDT:USDT",
    phase: int = 0,
    entry_price: float = 100.0,
    atr_scale: float = 10.0,
    side: int = 1,
) -> pd.DataFrame:
    direction = "long" if side == 1 else "short"
    return pd.DataFrame(
        {
            "symbol": [symbol],
            "base_asset": [symbol.split("/")[0]],
            "quote_asset": ["USDT"],
            "ts": [pd.Timestamp(ts)],
            "phase_hour": [phase],
            "block_id": [1],
            "ma_period": [7],
            "direction": [direction],
            "side": [side],
            "signal_ts": [pd.Timestamp(ts) + pd.Timedelta(hours=4)],
            "entry_ts": [pd.Timestamp(ts) + pd.Timedelta(hours=4)],
            "entry_price": [entry_price],
            "atr_scale": [atr_scale],
            "cross_event": [True],
            "in_trading_pool": [True],
            "atr_quintile": pd.Series([3], dtype="Int64"),
        }
    )


def test_frozen_gap_guard_hashes_and_parents_unchanged() -> None:
    cli = load_module("binance_4h_ma7_rc_p0r_gap_guard_cli", CLI_PATH)
    config = cli.validate_frozen_config()
    assert config["study_id"] == "BIN-4H-MA7-RC-P0R-GAP-GUARD"
    assert sha256_file(cli.CONFIG_PATH) == cli.EXPECTED_CONFIG_SHA256
    parent = cli.parent_hash_check(config)
    assert parent["unchanged"] is True
    assert all(row["unchanged"] for row in parent["files"])


def test_continuous_sample_matches_legacy_enrich_outcomes() -> None:
    hourly = hourly_frame(periods=4 * 50)
    fourh = attach_pool(fourh_from_hourly(hourly))
    event = long_event_row(ts=fourh.iloc[8]["ts"], entry_price=float(fourh.iloc[9]["open"]))
    hourly_maps = P0.hourly_maps(hourly)
    fourh_maps = P0.panel_maps(fourh)
    old = P0.enrich_outcomes(event, hourly_maps, fourh_maps, {})
    new = GG.enrich_outcomes_gap_aware(event, hourly_maps, fourh_maps, {})
    for col in (
        "first_hit_label",
        "ma7_recross_bars",
        "same_side_survival_bars",
        "gross_return_1",
        "gross_return_3",
        "mfe_1",
        "mae_1",
        "mfe_3",
    ):
        left = old.iloc[0][col]
        right = new.iloc[0][col]
        if pd.isna(left) and pd.isna(right):
            continue
        assert left == pytest.approx(right)
    assert bool(new.iloc[0]["first_hit_valid"]) is True
    assert bool(new.iloc[0]["gross_1_valid"]) is True
    assert bool(new.iloc[0]["recross_complete"]) is True


def test_indicator_lookback_gap_does_not_span_and_requires_rewarm() -> None:
    hourly = hourly_frame(periods=4 * 30)
    fourh = fourh_from_hourly(hourly)
    dropped = fourh.drop(index=fourh.index[8]).reset_index(drop=True)
    gapped = P0.add_indicators(dropped)
    assert gapped.iloc[8]["block_id"] != gapped.iloc[7]["block_id"]
    assert pd.isna(gapped.iloc[8]["sma7"])
    first_ready = gapped.iloc[8:]["sma7"].first_valid_index()
    assert first_ready is not None
    ready_pos = int(gapped.index.get_loc(first_ready))
    assert ready_pos - 8 == 6
    expected = gapped["close"].iloc[ready_pos - 6 : ready_pos + 1].mean()
    assert gapped.iloc[ready_pos]["sma7"] == pytest.approx(expected)
    pre_gap_tail = gapped["close"].iloc[1:8].mean()
    assert gapped.iloc[ready_pos]["sma7"] != pytest.approx(pre_gap_tail)


def test_missing_next_entry_bar_does_not_roll_forward() -> None:
    hourly = hourly_frame(periods=4 * 20)
    fourh = attach_pool(fourh_from_hourly(hourly))
    fourh = fourh.copy()
    fourh["sma7"] = 10.0
    fourh["atr_scale"] = 1.0
    close = np.array([10.0] * 6 + [9.0, 12.0] + [12.0] * (len(fourh) - 8), dtype=float)
    fourh["close"] = close
    signal_ts = fourh.iloc[7]["ts"]
    without_entry = fourh.drop(index=fourh.index[8]).reset_index(drop=True)
    without_entry = GG.assign_contiguous_blocks(without_entry, pd.Timedelta(hours=4))
    events = P0.build_event_candidates(without_entry, 7)
    assert events.empty or not bool((events["ts"] == signal_ts).any())

    forced = long_event_row(ts=signal_ts, entry_price=100.0)
    later_open = float(fourh.iloc[9]["open"])
    out = GG.enrich_outcomes_gap_aware(
        forced, P0.hourly_maps(hourly), P0.panel_maps(without_entry), {}
    )
    assert bool(out.iloc[0]["entry_bar_missing"]) is True
    assert out.iloc[0]["first_hit_reason"] == "entry_bar_missing"
    assert out.iloc[0]["gross_1_reason"] == "entry_bar_missing"
    rolled = 1.0 * (later_open / 100.0 - 1.0)
    if np.isfinite(out.iloc[0]["gross_return_1"]):
        assert out.iloc[0]["gross_return_1"] != pytest.approx(rolled)


def test_mid_window_gap_does_not_continue_duration_across_hole() -> None:
    fourh_ts = pd.date_range("2024-01-01T00:00:00Z", periods=20, freq="4h", tz="UTC")
    fourh_ts = fourh_ts.delete(5)
    fourh = pd.DataFrame(
        {
            "symbol": "TEST/USDT:USDT",
            "phase_hour": 0,
            "ts": fourh_ts,
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "sma7": 100.0,
        }
    )
    recross = GG.recross_survival_on_grid(
        signal_bar_ns=GG.utc_ns(fourh_ts[3]),
        side=1,
        fourh_ts=GG.series_utc_ns(fourh["ts"]),
        close=fourh["close"].to_numpy(dtype=float),
        sma7=fourh["sma7"].to_numpy(dtype=float),
    )
    assert recross["exclusive_reason"] == "internal_gap"
    assert recross["recross_complete"] is False
    assert not np.isfinite(recross["same_side_survival_bars"])
    assert recross["observed_same_side_bars_before_interrupt"] == 1


def test_short_horizon_valid_when_long_horizon_is_not() -> None:
    hourly = hourly_frame(periods=4 * 8)
    fourh = attach_pool(fourh_from_hourly(hourly))
    event = long_event_row(ts=fourh.iloc[1]["ts"], entry_price=float(fourh.iloc[2]["open"]))
    out = GG.enrich_outcomes_gap_aware(event, P0.hourly_maps(hourly), P0.panel_maps(fourh), {})
    assert bool(out.iloc[0]["gross_1_valid"]) is True
    assert bool(out.iloc[0]["mfe_1_valid"]) is True
    assert bool(out.iloc[0]["gross_30_valid"]) is False
    assert out.iloc[0]["gross_30_reason"] == "right_censor_cutoff"
    assert bool(out.iloc[0]["mfe_30_valid"]) is False
    assert bool(out.iloc[0]["first_hit_valid"]) is False


def test_right_censor_is_not_treated_as_completed_observation() -> None:
    fourh_ts = pd.date_range("2024-01-01T00:00:00Z", periods=8, freq="4h", tz="UTC")
    fourh = pd.DataFrame(
        {
            "symbol": "TEST/USDT:USDT",
            "phase_hour": 0,
            "ts": fourh_ts,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 101.0,
            "sma7": 100.0,
        }
    )
    recross = GG.recross_survival_on_grid(
        signal_bar_ns=GG.utc_ns(fourh_ts[1]),
        side=1,
        fourh_ts=GG.series_utc_ns(fourh["ts"]),
        close=fourh["close"].to_numpy(dtype=float),
        sma7=fourh["sma7"].to_numpy(dtype=float),
    )
    assert recross["exclusive_reason"] == "right_censor_cutoff"
    assert recross["recross_complete"] is False
    assert recross["internal_gap"] is False
    assert not np.isfinite(recross["same_side_survival_bars"])
    assert recross["observed_same_side_bars_before_interrupt"] == 6


def test_missing_1h_path_invalidates_path_metrics_only() -> None:
    hourly = hourly_frame(periods=4 * 40)
    fourh = attach_pool(fourh_from_hourly(hourly))
    event = long_event_row(ts=fourh.iloc[8]["ts"], entry_price=float(fourh.iloc[9]["open"]))
    gapped_hourly = hourly.drop(index=hourly.index[40:44]).reset_index(drop=True)
    out = GG.enrich_outcomes_gap_aware(
        event, P0.hourly_maps(gapped_hourly), P0.panel_maps(fourh), {}
    )
    assert bool(out.iloc[0]["gross_1_valid"]) is True
    assert bool(out.iloc[0]["recross_complete"]) is True
    assert bool(out.iloc[0]["first_hit_valid"]) is False
    assert out.iloc[0]["first_hit_label"] == "incomplete_future"
    assert out.iloc[0]["first_hit_reason"] in {"internal_gap", "path_1h_missing"}
    assert bool(out.iloc[0]["mfe_30_valid"]) is False


def test_recross_after_gap_is_not_pre_gap_trend_end() -> None:
    fourh_ts = list(pd.date_range("2024-01-01T00:00:00Z", periods=5, freq="4h", tz="UTC"))
    fourh_ts.extend(pd.date_range("2024-01-03T00:00:00Z", periods=10, freq="4h", tz="UTC"))
    close = [101.0] * 5 + [99.0] * 10
    fourh = pd.DataFrame(
        {
            "symbol": "TEST/USDT:USDT",
            "phase_hour": 0,
            "ts": pd.to_datetime(fourh_ts, utc=True),
            "open": 100.0,
            "high": 102.0,
            "low": 98.0,
            "close": close,
            "sma7": 100.0,
        }
    )
    recross = GG.recross_survival_on_grid(
        signal_bar_ns=GG.utc_ns(fourh["ts"].iloc[3]),
        side=1,
        fourh_ts=GG.series_utc_ns(fourh["ts"]),
        close=fourh["close"].to_numpy(dtype=float),
        sma7=fourh["sma7"].to_numpy(dtype=float),
    )
    assert recross["exclusive_reason"] == "internal_gap"
    assert recross["recross_complete"] is False
    assert recross["recross_observed_before_interrupt"] is False
    assert np.isfinite(recross["recross_after_gap_bars"])
    assert not np.isfinite(recross["ma7_recross_bars"])


def test_symbols_and_phases_do_not_join() -> None:
    ts = pd.date_range("2024-01-01T00:00:00Z", periods=12, freq="4h", tz="UTC")
    a = pd.DataFrame(
        {
            "symbol": ["A/USDT:USDT"] * 6,
            "phase_hour": [0] * 6,
            "ts": ts[:6],
            "open": 100.0,
            "close": 101.0,
            "sma7": 100.0,
        }
    )
    phase1 = a.copy()
    phase1["phase_hour"] = 1
    phase1["ts"] = ts[:6] + pd.Timedelta(hours=1)
    recross_a = GG.recross_survival_on_grid(
        signal_bar_ns=GG.utc_ns(a["ts"].iloc[1]),
        side=1,
        fourh_ts=GG.series_utc_ns(a["ts"]),
        close=a["close"].to_numpy(dtype=float),
        sma7=a["sma7"].to_numpy(dtype=float),
    )
    recross_phase = GG.recross_survival_on_grid(
        signal_bar_ns=GG.utc_ns(a["ts"].iloc[1]),
        side=1,
        fourh_ts=GG.series_utc_ns(phase1["ts"]),
        close=phase1["close"].to_numpy(dtype=float),
        sma7=phase1["sma7"].to_numpy(dtype=float),
    )
    assert recross_a["exclusive_reason"] == "right_censor_cutoff"
    assert recross_phase["observed_same_side_bars_before_interrupt"] == 0
    classified = GG.classify_windows_for_inventory(
        pd.concat(
            [
                long_event_row(ts=a["ts"].iloc[1], symbol="A/USDT:USDT", entry_price=100.0),
                long_event_row(
                    ts=phase1["ts"].iloc[1],
                    symbol="A/USDT:USDT",
                    phase=1,
                    entry_price=100.0,
                ),
            ],
            ignore_index=True,
        ),
        {
            ("A/USDT:USDT", 0): a.set_index("ts"),
            ("A/USDT:USDT", 1): phase1.set_index("ts"),
        },
        {},
        sample_kind="events",
    )
    assert set(classified["recross_reason"]) == {"right_censor_cutoff"}


def test_incomplete_samples_are_not_failures_in_denominators() -> None:
    events = pd.DataFrame(
        {
            "phase_hour": [0, 0, 0],
            "ma_period": [7, 7, 7],
            "direction": ["long", "long", "long"],
            "first_hit_label": ["favorable_first", "incomplete_future", "adverse_first"],
            "first_hit_valid": [True, False, True],
            "first_hit_reason": ["complete", "internal_gap", "complete"],
            "symbol": ["A", "A", "A"],
        }
    )
    controls = pd.DataFrame(
        {
            "direction": ["long", "long"],
            "first_hit_label": ["adverse_first", "incomplete_future"],
            "first_hit_valid": [True, False],
            "control_stratum_has_event": [True, True],
            "control_weight": [1.0, 1.0],
            "symbol": ["A", "A"],
        }
    )
    naive = float(events["first_hit_label"].eq("favorable_first").mean())
    guarded = GG.first_hit_success_rate(events)
    assert naive == pytest.approx(1.0 / 3.0)
    assert guarded == pytest.approx(0.5)
    summary = GG.summarize_guarded_first_hit(events, controls)
    row = summary.loc[summary["direction"].eq("long")].iloc[0]
    assert int(row["candidates"]) == 3
    assert int(row["valid"]) == 2
    assert int(row["interrupted"]) == 1
    assert row["event_favorable_rate"] == pytest.approx(0.5)
    assert row["control_favorable_rate"] == pytest.approx(0.0)


def test_funding_missing_is_separate_from_price_gap() -> None:
    hourly = hourly_frame(periods=4 * 12, start="2024-01-01T00:00:00Z")
    fourh = attach_pool(fourh_from_hourly(hourly))
    event = long_event_row(ts=fourh.iloc[2]["ts"], entry_price=float(fourh.iloc[3]["open"]))
    out = GG.enrich_outcomes_gap_aware(event, P0.hourly_maps(hourly), P0.panel_maps(fourh), {})
    assert bool(out.iloc[0]["gross_3_valid"]) is True
    assert bool(out.iloc[0]["net_3_valid"]) is False
    assert out.iloc[0]["net_3_reason"] == "funding_missing"
    assert out.iloc[0]["gross_3_reason"] == "complete"
    assert bool(out.iloc[0]["funding_complete_3"]) is False
    gapped_4h = fourh.drop(index=fourh.index[5]).reset_index(drop=True)
    gapped_4h = GG.assign_contiguous_blocks(gapped_4h, pd.Timedelta(hours=4))
    out_gap = GG.enrich_outcomes_gap_aware(
        event, P0.hourly_maps(hourly), P0.panel_maps(gapped_4h), {}
    )
    assert out_gap.iloc[0]["gross_3_reason"] == "internal_gap"
    assert out_gap.iloc[0]["net_3_reason"] == "internal_gap"
    assert out_gap.iloc[0]["net_3_reason"] != "funding_missing"


def test_duplicate_and_unaligned_grids_are_rejected() -> None:
    hourly = hourly_frame(periods=8)
    dup = pd.concat([hourly, hourly.iloc[[0]]], ignore_index=True)
    with pytest.raises(RuntimeError, match="duplicate"):
        GG.validate_time_grid(dup, step=pd.Timedelta(hours=1), name="1h")
    shifted = hourly.copy()
    shifted.loc[3, "ts"] = shifted.loc[3, "ts"] + pd.Timedelta(minutes=15)
    with pytest.raises(RuntimeError, match="hour grid|integer multiple"):
        GG.validate_time_grid(shifted, step=pd.Timedelta(hours=1), name="1h")
    fourh = fourh_from_hourly(hourly_frame(periods=16))
    broken = fourh.copy()
    broken.loc[2, "ts"] = broken.loc[2, "ts"] + pd.Timedelta(hours=1)
    with pytest.raises(RuntimeError, match="aligned to phase|integer multiple"):
        GG.validate_time_grid(broken, step=pd.Timedelta(hours=4), name="4h", phase_hour=0)


def test_nan_sma_is_not_treated_as_no_recross() -> None:
    ts = pd.date_range("2024-01-01T00:00:00Z", periods=12, freq="4h", tz="UTC")
    sma = np.array([100.0] * 3 + [np.nan] * 9)
    recross = GG.recross_survival_on_grid(
        signal_bar_ns=GG.utc_ns(ts[1]),
        side=1,
        fourh_ts=GG.series_utc_ns(ts),
        close=np.full(12, 101.0),
        sma7=sma,
    )
    assert recross["exclusive_reason"] == "indicator_undefined"
    assert recross["recross_complete"] is False
    assert not np.isfinite(recross["same_side_survival_bars"])


def test_inventory_checksum_and_endpoint_only_gross_are_diagnostic() -> None:
    hourly = hourly_frame(periods=4 * 12)
    fourh = attach_pool(fourh_from_hourly(hourly))
    gapped = fourh.drop(index=fourh.index[6]).reset_index(drop=True)
    event = long_event_row(ts=fourh.iloc[3]["ts"], entry_price=float(fourh.iloc[4]["open"]))
    out = GG.enrich_outcomes_gap_aware(event, P0.hourly_maps(hourly), P0.panel_maps(gapped), {})
    assert not np.isfinite(out.iloc[0]["gross_return_3"])
    assert np.isfinite(out.iloc[0]["gross_return_3_endpoints_only"])
    classified = GG.classify_windows_for_inventory(
        event, P0.panel_maps(gapped), P0.hourly_maps(hourly), sample_kind="events"
    )
    tables = GG.build_inventory_tables(classified)
    metric = tables["by_metric"]
    assert bool(metric["checksum_ok"].all())
    gross3 = metric.loc[metric["metric"].eq("gross_return_3")].iloc[0]
    assert int(gross3["candidates"]) == 1
    assert int(gross3["internal_gap"]) == 1
    assert int(gross3["valid"]) == 0
