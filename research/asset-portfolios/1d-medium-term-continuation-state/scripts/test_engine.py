"""仅用合成日线独立检验 MTCS 信号、路径标签和缺口处理。"""

import numpy as np
import pandas as pd
import pytest

from engine import DAY, GROUPS, build_panel, event_probe, wilder_atr
from strategy_lab.data.research_inputs import (
    IdentityWindow,
    complete_window_mask,
    segment_research_bars,
)


def raw_bars(close):
    close = np.asarray(close, dtype=float)
    return pd.DataFrame({
        "symbol": "SYNTH/USDT:USDT",
        "ts": pd.date_range("2020-01-01", periods=len(close), freq="D", tz="UTC"),
        "timeframe": "1d", "is_closed": True,
        "open": close, "high": close + 1, "low": close - 1, "close": close,
        "volume": 100.0, "quote_volume": 10000.0, "trade_count": 10,
    })


def verified(frame, **kwargs):
    arguments = {"identity_policy": "observed_diagnostic"}
    arguments.update(kwargs)
    segmented = segment_research_bars(frame, "1d", **arguments)
    segmented["research_window_valid"] = complete_window_mask(segmented, backward=60, forward=0)
    return segmented


def panel(frame, cutoff=None):
    if cutoff is None:
        cutoff = frame.ts.max() + DAY
    return build_panel(verified(frame), cutoff)


def test_wilder_atr_initialization_gap_true_range_and_recursion_hand_calculation():
    # 第1根 high-low=2；第2根上涨跳空 TR=11；其余 TR=2。
    close = np.array([100.0] + [110.0] * 15)
    high, low = close + 1, close - 1
    atr = wilder_atr(high, low, close)
    seed = (2 + 11 + 12 * 2) / 14
    assert np.isnan(atr[:13]).all()
    assert atr[13] == pytest.approx(seed)
    assert atr[14] == pytest.approx((13 * seed + 2) / 14)
    assert atr[15] == pytest.approx((13 * atr[14] + 2) / 14)


def test_next_open_to_20th_close_and_late_identity_are_exact():
    raw = raw_bars(np.full(105, 100.0))
    t = 60
    raw.loc[t + 1, ["open", "high", "low", "close"]] = [120, 124, 119, 123]
    raw.loc[t + 5, ["open", "high", "low", "close"]] = [125, 126, 124, 125]
    raw.loc[t + 20, ["open", "high", "low", "close"]] = [140, 141, 139, 140]
    raw.loc[t + 21, ["open", "high", "low", "close"]] = [500, 501, 499, 500]
    result = panel(raw)
    row = result.iloc[t]
    assert row.atr14 == 2
    assert row.signal_time == raw.iloc[t + 1].ts
    assert row.entry_open == 120
    assert row.exit_close20 == 140
    assert row.q1 == pytest.approx(1.5)
    assert row.q5 == pytest.approx(2.5)
    assert row.q20 == pytest.approx(10)
    assert row.l20 == pytest.approx(7.5)
    assert row.ret20 == pytest.approx(140 / 120 - 1)
    assert row.q20 == pytest.approx(row.q5 + row.l20)
    assert row.peak20_long_day == 20
    assert row.mfe20_long == pytest.approx((141 - 120) / 2)
    mature = result.loc[result.valid20]
    np.testing.assert_allclose(mature.q20, mature.q5 + mature.l20, rtol=1e-13, atol=1e-13)


@pytest.mark.parametrize("direction", [1, -1])
def test_strict_ma_cross_rejects_both_current_and_previous_equalities(direction):
    close = np.full(85, 100.0)
    close[58:62] = [101, 99, 100, 101]
    if direction == -1:
        close = 200 - close
    result = panel(raw_bars(close))
    side = "LONG" if direction == 1 else "SHORT"
    other = "SHORT" if direction == 1 else "LONG"
    assert result.iloc[59][f"M_{other}"]
    assert result.iloc[60].close == result.iloc[60].sma7
    assert not result.iloc[60][f"M_{side}"]
    assert direction * (result.iloc[61].close - result.iloc[61].sma7) > 0
    assert not result.iloc[61][f"M_{side}"]


def test_states_are_mutually_exclusive_exhaustive_and_use_prior_bar_values():
    rng = np.random.default_rng(713)
    close = 1000 + np.cumsum(rng.normal(0, 2, 1000))
    result = panel(raw_bars(close))
    for side, direction in [("LONG", 1), ("SHORT", -1)]:
        counts = result[[f"S{k}_{side}" for k in (1, 2, 3)]].sum(axis=1)
        np.testing.assert_array_equal(counts, result[f"M_{side}"].astype(int))
        for k in (1, 2, 3):
            assert result[f"S{k}_{side}"].any()
        for t in np.flatnonzero(result[f"M_{side}"].to_numpy()):
            delta20 = direction * (close[t - 1] - close[t - 21])
            delta5 = direction * (close[t - 1] - close[t - 6])
            expected = 2 if delta20 <= 0 else 1 if delta5 > 0 else 3
            assert result.iloc[t][f"S{expected}_{side}"]
            assert result.iloc[t].prior20_delta == pytest.approx(close[t - 1] - close[t - 21])
            assert result.iloc[t].prior5_delta == pytest.approx(close[t - 1] - close[t - 6])


def test_momentum_is_current_20_day_direction_and_zero_has_no_signal():
    close = np.full(90, 100.0)
    close[60], close[61] = 101, 99
    result = panel(raw_bars(close))
    assert result.iloc[60].U_LONG
    assert result.iloc[61].U_SHORT
    assert result.iloc[62].momentum20_delta == 0
    assert not result.iloc[62].U_LONG
    assert not result.iloc[62].U_SHORT
    assert not result.iloc[:59][list(GROUPS)].to_numpy().any()
    assert result.iloc[59].feature_valid


@pytest.mark.parametrize("direction", [1, -1])
@pytest.mark.parametrize("state", [2, 3])
def test_state_zero_boundaries_have_the_frozen_assignment(direction, state):
    close = np.full(90, 100.0)
    close[59], close[60] = 99, 102
    if state == 2:
        close[39] = 99  # prior20 == 0 belongs to startup candidate.
    else:
        close[39], close[54] = 90, 99  # prior20 > 0, prior5 == 0.
    if direction == -1:
        close = 200 - close
    side = "LONG" if direction == 1 else "SHORT"
    result = panel(raw_bars(close))
    row = result.iloc[60]
    assert row[f"M_{side}"]
    assert row[f"S{state}_{side}"]
    assert row.prior20_delta == 0 if state == 2 else row.prior5_delta == 0


def test_future_prefix_preserves_features_signals_and_all_mature_labels():
    rng = np.random.default_rng(2718)
    raw = raw_bars(1000 + np.cumsum(rng.normal(0, 3, 190)))
    full = panel(raw)
    causal = ["atr14", "sma7", "prior20_delta", "prior5_delta", "momentum20_delta", "feature_valid", *GROUPS]
    for length in (60, 61, 73, 93, 140, 189):
        prefix = panel(raw.iloc[:length])
        pd.testing.assert_frame_equal(prefix[causal], full.iloc[:length][causal].reset_index(drop=True))
        for horizon in (1, 5, 10, 20, 40):
            mature_stop = max(0, length - horizon)
            cols = [f"q{horizon}", f"ret{horizon}", f"valid{horizon}"]
            pd.testing.assert_frame_equal(prefix.iloc[:mature_stop][cols], full.iloc[:mature_stop][cols])


@pytest.mark.parametrize("interruption", ["dropbar", "zero_volume", "zero_trade_count"])
def test_interruption_blocks_labels_and_requires_new_60_bar_warmup(interruption):
    raw = raw_bars(100 + np.arange(165) / 10)
    interruption_ts = raw.iloc[80].ts
    restart_ts = raw.iloc[81].ts
    ready_ts = raw.iloc[140].ts
    # 段后价格跳到另一量级，ATR重置不能继承跨缺口价格跳跃。
    raw.loc[81:, ["open", "high", "low", "close"]] += 1000
    if interruption == "dropbar":
        raw = raw.drop(index=80).reset_index(drop=True)
    elif interruption == "zero_volume":
        raw.loc[80, "volume"] = 0
    else:
        raw.loc[80, "trade_count"] = 0
    result = panel(raw).set_index("ts")
    assert result.iloc[59].valid20
    assert result.iloc[60].feature_valid
    assert result.iloc[60].U_LONG
    assert result.iloc[60].censored20
    assert np.isnan(result.iloc[60].q20)
    assert not result.loc[restart_ts:ready_ts - DAY].feature_valid.any()
    assert not result.loc[restart_ts:ready_ts - DAY, list(GROUPS)].to_numpy().any()
    assert result.loc[ready_ts].feature_valid
    assert np.isnan(result.loc[restart_ts].atr14)
    assert result.loc[restart_ts + 13 * DAY].atr14 == pytest.approx(2)
    if interruption != "dropbar":
        assert not result.loc[interruption_ts].eligible


def test_administrative_immaturity_and_known_gap_have_distinct_priority():
    raw = raw_bars(100 + np.arange(100) / 10)
    full = panel(raw)
    assert full.iloc[79].valid20
    assert full.iloc[80].label20_status == "ADMINISTRATIVE_UNMATURED"
    assert full.iloc[80].administrative_unmatured20
    assert not full.iloc[80].censored20
    raw.loc[90, "volume"] = 0
    gap = panel(raw)
    assert gap.iloc[80].U_LONG == full.iloc[80].U_LONG
    assert gap.iloc[80].known_interruption20
    assert gap.iloc[80].censored20
    assert not gap.iloc[80].administrative_unmatured20
    assert gap.iloc[80].label20_status == "CENSORED_GAP_OR_IDENTITY_BOUNDARY"


def test_symbol_ending_before_global_cutoff_is_censored_not_admin_immature():
    raw = raw_bars(100 + np.arange(90) / 10)
    global_cutoff = raw.iloc[0].ts + 100 * DAY
    result = panel(raw, cutoff=global_cutoff)
    assert result.iloc[80].known_interruption20
    assert result.iloc[80].censored20
    assert not result.iloc[80].administrative_unmatured20


def test_identity_boundary_resets_features_and_future_window_without_missing_day():
    raw = raw_bars(100 + np.arange(165) / 10)
    windows = [
        IdentityWindow("SYNTH/USDT:USDT", str(raw.iloc[0].ts), str(raw.iloc[80].ts), "synthetic identity A"),
        IdentityWindow("SYNTH/USDT:USDT", str(raw.iloc[80].ts), str(raw.iloc[-1].ts + DAY), "synthetic identity B"),
    ]
    frame = verified(raw, identity_policy="require_verified", identity_windows=windows)
    result = build_panel(frame, raw.iloc[-1].ts + DAY)
    assert result.iloc[59].valid20
    assert result.iloc[60].censored20
    assert not result.iloc[80:139].feature_valid.any()
    assert result.iloc[139].feature_valid


@pytest.mark.parametrize("direction", [1, -1])
def test_event_probe_is_linear_with_adverse_fills_and_actual_notional_fees(direction):
    group = "M_LONG" if direction == 1 else "M_SHORT"
    probe_input = pd.DataFrame({group: [True], "valid20": [True], "entry_open": [100.0],
                                "exit_close20": [120.0], "ret20": [0.2]})
    result = event_probe(probe_input, group).iloc[0]
    entry = 100 * (1 + direction * 0.0004)
    exit_price = 120 * (1 - direction * 0.0004)
    quantity_for_unit_entry_notional = 1 / entry
    paid_fees = 0.001 + quantity_for_unit_entry_notional * exit_price * 0.001
    expected = direction * quantity_for_unit_entry_notional * (exit_price - entry) - paid_fees
    assert result.gross_return == pytest.approx(direction * 0.2)
    assert result.return_after_fee_slippage == pytest.approx(expected)
    assert result.fees_fraction_entry_notional == pytest.approx(paid_fees)
    assert not result.funding_verified


@pytest.mark.parametrize("bad_case", ["unordered", "duplicate", "past_mask", "unclosed_cutoff"])
def test_engine_rejects_corrupted_input_without_sorting_or_repair(bad_case):
    raw = raw_bars(100 + np.arange(100) / 10)
    frame = verified(raw)
    cutoff = raw.iloc[-1].ts + DAY
    if bad_case == "unordered":
        frame = frame.iloc[::-1].reset_index(drop=True)
    elif bad_case == "duplicate":
        frame.loc[61, "ts"] = frame.loc[60, "ts"]
    elif bad_case == "past_mask":
        frame.loc[60, "research_window_valid"] = False
    else:
        cutoff -= pd.Timedelta(hours=1)
    with pytest.raises(ValueError):
        build_panel(frame, cutoff)
