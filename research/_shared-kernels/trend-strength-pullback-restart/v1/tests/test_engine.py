"""仅合成行情；直接公式、顺序边界、前缀不变性与证据拒绝测试。"""
import importlib.util
import hashlib
import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


SPEC = importlib.util.spec_from_file_location("tspr_engine_test", Path(__file__).parents[1] / "engine.py")
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)


def frame(close=None, n=180, break_at=None, missing_row=False):
    if close is None:
        rng = np.random.default_rng(92271)
        close = 100 * np.exp(np.cumsum(rng.normal(.003, .022, n)))
    close = np.asarray(close, dtype=float)
    n = len(close)
    opening = close * (1 + .002 * np.sin(np.arange(n)))
    result = pd.DataFrame({
        "symbol": "SYNTH/USDT:USDT", "ts": pd.date_range("2020-01-01", periods=n, tz="UTC"),
        "open": opening, "high": np.maximum(opening, close) * 1.012,
        "low": np.minimum(opening, close) * .987, "close": close, "volume": 100.,
        "eligible": True, "research_segment_id": "SYNTH#1",
    })
    if break_at is not None:
        result.loc[break_at:, "research_segment_id"] = "SYNTH#2"
        if missing_row:
            result.loc[break_at, "eligible"] = False
            result.loc[break_at, "research_segment_id"] = None
    result["research_window_valid"] = (
        result.eligible & result.groupby("research_segment_id").cumcount().ge(59))
    return result


def build(f):
    return engine.build_panel(f, f.ts.iloc[-1] + engine.DAY)


def crafted(kind="restart"):
    c = np.linspace(70, 130, 160) + .3 * np.sin(np.arange(160))
    t, s = 80, 74
    c[s-6:s] = 100
    c[s] = 112
    c[s+1:t+1] = [94, 101, 93, 92, 91, 110]
    if kind == "bounce":
        c[s+2] = 115
    elif kind == "equal_today":
        c[t-1] = 90
        c[t] = c[t-6:t].mean()
    elif kind == "false_first_adverse":
        c[s-6:s] = [1, 118, 118, 118, 118, 118]
        c[s] = 100
        c[s+1:t+1] = [101, 99, 95, 93, 90, 120]
    elif kind == "no_u":
        c[s+1:t+1] = [113, 114, 115, 116, 117, 118]
    return frame(c), t, s


def direct_state(c, t, d):
    s = t - 6
    def z(j):
        return d * (c[j] - np.mean(c[j-6:j+1]))
    candidates = [j for j in range(s+1, t) if z(j) < 0]
    u = candidates[0] if candidates else None
    p = bool(z(s) > 0 and u is not None
             and d*c[u] < max(d*c[j] for j in range(s, u))
             and all(z(j) <= 0 for j in range(u+1, t))
             and z(t-1) < 0 and d*(c[t-1]-c[s]) < 0)
    return p, z(t) > 0 and z(t-1) < 0, u


def test_strength_matches_twenty_sample_returns_at_s_and_frozen_bins():
    f = frame()
    p = build(f)
    c = f.close.to_numpy()
    for t in (59, 80, 125, 179):
        s = t-6
        r = np.array([np.log(c[j]/c[j-1]) for j in range(s-19, s+1)])
        x = np.log(c[s]/c[s-20]) / (np.std(r, ddof=1)*np.sqrt(20))
        assert p.at[t, "strength_LONG"] == pytest.approx(x, rel=1e-13)
        assert p.at[t, "strength_SHORT"] == -p.at[t, "strength_LONG"]
        assert p.at[t, "anchor_time"] == f.at[s, "ts"]
        assert p.at[t, "anchor_index"] == s
    values = np.array([-1, 0, 1e-12, 1, np.nextafter(1., 2.), 2, np.nextafter(2., 3.), np.nan, np.inf])
    np.testing.assert_array_equal(engine.strength_bins(values, np.ones(len(values), bool)), [0, 0, 1, 1, 2, 2, 3, 0, 0])


def test_strict_restart_allows_equal_ma_day_inside_pullback():
    f, t, s = crafted()
    p = build(f)
    assert f.at[s+2, "close"] == p.at[s+2, "sma7"] == 101
    assert p.at[t, "P_LONG"] and p.at[t, "M_LONG"]
    assert all(p.at[t, f"{condition}_LONG"] for condition in engine.P_CONDITIONS)
    assert p.at[t, "pullback_index_LONG"] == s+1
    assert p.at[t, "pullback_time_LONG"] == f.at[s+1, "ts"]
    assert p.at[t, "prior_extreme_at_u_LONG"] == 112
    assert p.at[t, "cell_LONG"] == 3


def test_reentry_after_an_intermediate_favorable_close_is_not_first_restart():
    f, t, _ = crafted("bounce")
    p = build(f)
    assert p.at[t, "M_LONG"]
    assert not p.at[t, "p4_no_favorable_after_u_LONG"]
    assert not p.at[t, "P_LONG"]


def test_first_adverse_cannot_be_rechosen_to_make_actual_pullback_pass():
    f, t, s = crafted("false_first_adverse")
    p = build(f)
    assert p.at[t, "p1_anchor_favorable_LONG"]
    assert p.at[t, "pullback_index_LONG"] == s+1
    assert f.at[s+1, "close"] > f.at[s, "close"]
    assert not p.at[t, "p3_actual_pullback_LONG"]
    assert not p.at[t, "P_LONG"]


def test_current_equal_ma_is_not_strict_cross_and_missing_u_retains_observation():
    f, t, _ = crafted("equal_today")
    p = build(f)
    # This construction has an exactly representable mean of 97.
    assert f.at[t, "close"] == p.at[t, "sma7"]
    assert p.at[t, "P_LONG"] and not p.at[t, "M_LONG"]
    no_u, t, _ = crafted("no_u")
    q = build(no_u)
    assert q.at[t, "feature_valid"] and q.at[t, "ALL_LONG"]
    assert not q.at[t, "P_LONG"] and q.at[t, "pullback_index_LONG"] == -1
    assert pd.isna(q.at[t, "pullback_time_LONG"])


def test_vectorized_states_equal_independent_sequential_oracle_both_directions():
    f = frame(n=420)
    p = build(f)
    c = f.close.to_numpy()
    observed = set()
    for t in range(59, len(f)):
        for side, d in engine.SIDES:
            expected_p, expected_m, u = direct_state(c, t, d)
            assert p.at[t, f"P_{side}"] == expected_p
            assert p.at[t, f"M_{side}"] == expected_m
            assert p.at[t, f"pullback_index_{side}"] == (-1 if u is None else u)
            if p.at[t, f"ALL_{side}"]:
                observed.add(p.at[t, f"cell_{side}"])
    assert observed == {0, 1, 2, 3}


def test_geometry_retained_outside_positive_strength_domain():
    f, t, _ = crafted()
    p = build(f)
    assert p.at[t, "feature_valid"] and p.at[t, "strength_SHORT"] < 0
    assert p.at[t, "strength_bin_SHORT"] == 0 and p.at[t, "cell_SHORT"] == -1
    expected_p, expected_m, _ = direct_state(f.close.to_numpy(), t, -1)
    assert p.at[t, "P_SHORT"] == expected_p and p.at[t, "M_SHORT"] == expected_m
    assert not p.at[t, "ALL_SHORT"]


def test_mirrored_price_geometry_produces_a_short_restart_in_negative_trend():
    f, t, s = crafted()
    mirrored = frame(300 - f.close.to_numpy())
    p = build(mirrored)
    assert p.at[t, "strength_SHORT"] > 0 and p.at[t, "ALL_SHORT"]
    assert p.at[t, "P_SHORT"] and p.at[t, "M_SHORT"]
    assert p.at[t, "pullback_index_SHORT"] == s+1
    assert p.at[t, "prior_extreme_at_u_SHORT"] == 188


def test_constant_prices_invalid_sigma_and_zero_strength_is_counted_separately():
    p = build(frame(np.full(100, 100.)))
    assert p.official_past60.any() and not p.feature_valid.any()
    assert not p[list(engine.GROUPS)].to_numpy().any()
    c = np.tile([100., 101.], 70)
    q = build(frame(c))
    assert q.feature_valid.iloc[59:].all()
    assert q.strength_zero.iloc[59:].all()
    assert not q[list(engine.GROUPS)].to_numpy().any()


def test_q_labels_use_next_open_and_previous_atr_and_late_is_terminal_difference():
    f = frame()
    p = build(f)
    t = 80
    a = engine.wilder_atr(f.high.to_numpy(), f.low.to_numpy(), f.close.to_numpy())[t-1]
    assert p.at[t, "atr14_lag"] == a
    for horizon in engine.HORIZONS:
        direct = (f.at[t+horizon, "close"] - f.at[t+1, "open"]) / a
        assert p.at[t, f"q{horizon}"] == direct
        assert p.at[t, f"ret{horizon}"] == f.at[t+horizon, "close"] / f.at[t+1, "open"] - 1
    assert p.at[t, "l20"] == pytest.approx((f.at[t+20, "close"]-f.at[t+5, "close"])/a)
    changed = f.copy()
    changed.loc[t, "high"] *= 10
    changed.loc[t, "low"] /= 10
    q = build(changed)
    assert q.at[t, "atr14"] != p.at[t, "atr14"]
    assert q.at[t, "atr14_lag"] == p.at[t, "atr14_lag"]
    assert q.at[t, "q20"] == p.at[t, "q20"]


def test_extremes_offsets_and_giveback_use_full_future_twenty_bars():
    f = frame()
    t = 80
    f.loc[t+7, "high"] = f.high.max()*3
    f.loc[t+13, "low"] = f.low.min()/3
    p = build(f)
    a, entry = p.at[t, "atr14_lag"], f.at[t+1, "open"]
    assert p.at[t, "peak20_long_day"] == 7 and p.at[t, "peak20_short_day"] == 13
    assert p.at[t, "adverse20_long_day"] == 13 and p.at[t, "adverse20_short_day"] == 7
    assert p.at[t, "mfe20_long"] == (f.at[t+7, "high"]-entry)/a
    assert p.at[t, "mae20_long"] == (entry-f.at[t+13, "low"])/a
    assert p.at[t, "giveback20_long"] == p.at[t, "mfe20_long"] - p.at[t, "q20"]
    assert p.at[t, "giveback20_short"] == p.at[t, "mfe20_short"] + p.at[t, "q20"]


@pytest.mark.parametrize("missing_row", [False, True])
def test_segment_boundary_resets_past_and_labels_without_losing_prior_signals(missing_row):
    f = frame(n=240, break_at=90, missing_row=missing_row)
    p = build(f)
    t = 80
    assert p.at[t, "feature_valid"] and not p.at[t, "valid20"]
    assert p.at[t, "known_interruption20"] and p.at[t, "censored20"]
    assert not p.at[t, "administrative_unmatured20"]
    assert pd.isna(p.at[t, "q20"])
    start = 91 if missing_row else 90
    assert not p.feature_valid.iloc[start:start+59].any()
    assert p.at[start+59, "feature_valid"]
    expected = engine.wilder_atr(f.high.iloc[start:].to_numpy(), f.low.iloc[start:].to_numpy(), f.close.iloc[start:].to_numpy())
    assert p.at[start+14, "atr14_lag"] == expected[13]
    assert p.administrative_unmatured20.iloc[-20:].all()
    assert not p.censored20.iloc[-20:].any()


def test_all_past_state_columns_are_prefix_invariant_while_labels_mature_later():
    f = frame(n=210)
    full = build(f)
    prefix_frame = f.iloc[:135].copy()
    prefix = build(prefix_frame)
    columns = ["feature_valid", "atr14_lag", "sigma20_anchor", "log_return20_anchor", "anchor_time", "anchor_index", *engine.GROUPS]
    for side, _ in engine.SIDES:
        columns += [f"{name}_{side}" for name in ("strength", "strength_bin", "P", "M", "cell", "pullback_time", "pullback_index", *engine.P_CONDITIONS)]
    pd.testing.assert_frame_equal(full.loc[:134, columns], prefix[columns])
    assert full.at[130, "valid20"] and not prefix.at[130, "valid20"]
    assert prefix.at[134, "ALL_LONG"] or prefix.at[134, "ALL_SHORT"]


def test_known_interruption_takes_precedence_over_administrative_immaturity():
    p = build(frame(n=100, break_at=90))
    assert p.at[80, "signal_time"] + 20*engine.DAY > p.ts.iloc[-1] + engine.DAY
    assert p.at[80, "known_interruption20"] and p.at[80, "censored20"]
    assert not p.at[80, "administrative_unmatured20"]


def test_direction_view_multiplies_labels_once_and_never_drops_censored_events():
    f = frame(n=180)
    p = build(f)
    short = engine.direction_events(p, "SHORT")
    assert len(short) == p.ALL_SHORT.sum()
    np.testing.assert_allclose(short.q20, -p.loc[short.index, "q20"], equal_nan=True)
    assert (short.direction == -1).all()
    assert short.valid20.sum() <= len(short)
    with pytest.raises(ValueError, match="unsigned"):
        engine.direction_events(short, "SHORT")
    for side, _ in engine.SIDES:
        assert (p[f"HIGH_PM_{side}"] <= p[f"HIGH_P_{side}"]).all()
        assert (p[f"HIGH_P_{side}"] <= p[f"HIGH_{side}"]).all()
        assert (p[f"HIGH_{side}"] <= p[f"ALL_{side}"]).all()


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_event_probe_matches_explicit_entry_exit_cashflows(side):
    f, t, _ = crafted()
    if side == "SHORT":
        f = frame(300 - f.close.to_numpy())
    f.loc[t+1, "open"] = 100
    f.loc[t+20, "close"] = 110
    f["high"] = f[["open", "close"]].max(axis=1) * 1.012
    f["low"] = f[["open", "close"]].min(axis=1) * .987
    p = build(f)
    probe = engine.event_probe(p, f"ALL_{side}")
    if side == "LONG":
        expected = (109.956 - 100.04 - .10004 - .109956) / 100.04
    else:
        expected = (99.96 - 110.044 - .09996 - .110044) / 99.96
    assert probe.at[t, "return_after_fee_slippage"] == pytest.approx(expected, abs=1e-15)
    assert probe.valid20.all() and not probe.funding_verified.any()


@pytest.mark.parametrize("problem", ["duplicate", "naive", "mask", "segment_reuse", "price"])
def test_invalid_verified_frame_is_rejected_without_fallback(problem):
    f = frame()
    if problem == "duplicate":
        f.loc[70, "ts"] = f.at[69, "ts"]
    elif problem == "naive":
        f["ts"] = f.ts.dt.tz_localize(None)
    elif problem == "mask":
        f.loc[10, "research_window_valid"] = True
    elif problem == "segment_reuse":
        f.loc[80, "eligible"] = False
        f.loc[80, "research_segment_id"] = None
    else:
        f.loc[70, "close"] = 0
    with pytest.raises(ValueError):
        engine.build_panel(f, pd.Timestamp("2021-01-01", tz="UTC"))


def test_closed_bar_cutoff_rejected():
    f = frame()
    with pytest.raises(ValueError, match="unclosed"):
        engine.build_panel(f, f.ts.iloc[-1])


def make_saved_input(tmp_path):
    family = tmp_path / "synthetic-consumer"
    root = family / "artifacts/p0-inputs"
    mask_path = Path(inspect.getfile(engine.complete_window_mask)).resolve()
    source = mask_path.parents[3]
    root.mkdir(parents=True)
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return engine.sha(path)
    request = {"symbols": ["SYNTH/USDT:USDT"], "timeframe": "1d", "mode": "price_diagnostic",
               "gap_policy": "contiguous_segments", "backward_bars": 60, "forward_bars": 0,
               "start": "2020-01-01T00:00:00Z", "end": "2020-07-01T00:00:00Z"}
    pins = {}
    for path, value in (("specs/input-request.json", request),
                        ("specs/source-pins.json", {"formal_lab": str(source), "files": {"src/strategy_lab/data/research_inputs.py": engine.sha(mask_path)}}),
                        ("specs/input-contract.md", "synthetic input contract"),
                        ("specs/observed-universe.json", request["symbols"]),
                        ("scripts/audit_inputs.py", "synthetic test-only reader")):
        pins[path] = save(family / path, value)
    save(root / "started.json", {"family_files_sha256": pins})
    f = frame(n=150)
    path = root / "returned-frames/test.pkl.gz"
    path.parent.mkdir()
    f.to_pickle(path, compression="gzip")
    entry = {"stage": "research", "backward_bars": 60, "forward_bars": 0,
             "path": "returned-frames/test.pkl.gz", "sha256": engine.sha(path),
             "dataframe_hash": hashlib.sha256(pd.util.hash_pandas_object(f, index=True).values.tobytes()).hexdigest(),
             "rows": len(f), "columns": list(f.columns), "request_path": "requests/test.json",
             "request_sha256": save(root / "requests/test.json", request),
             "startup_report_path": "startup-reports/test.json"}
    entry["startup_report_sha256"] = save(root / entry["startup_report_path"], {"request": request, "status": "PRICE_DIAGNOSTIC_INPUTS_VERIFIED"})
    manifest_sha = save(root / "frame-manifest.json", {request["symbols"][0]: entry})
    save(root / "summary.json", {"status": "PRICE_INPUTS_READY_WITH_RECORDED_EXCLUSIONS",
         "source_pins_unchanged": True, "changed_family_files": [], "frames": 1,
         "old_family_frames_read": False, "data_lake_written": False, "signals_computed": False,
         "labels_computed": False, "frame_manifest_sha256": manifest_sha})
    return root, f


def test_saved_frames_bound_to_own_family_request_and_bytes(tmp_path):
    root, f = make_saved_input(tmp_path)
    [(symbol, loaded)] = list(engine.load_verified_frames(root))
    assert symbol == "SYNTH/USDT:USDT"
    pd.testing.assert_frame_equal(loaded, f)
    saved = root / "returned-frames/test.pkl.gz"
    saved.write_bytes(saved.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="changed"):
        list(engine.load_verified_frames(root))


def test_saved_frames_reject_foreign_contract_even_if_price_hash_is_valid(tmp_path):
    root, _ = make_saved_input(tmp_path)
    (root.parent.parent / "scripts/audit_inputs.py").write_text("another family's reader")
    with pytest.raises(ValueError, match="changed"):
        list(engine.load_verified_frames(root))


def test_cached_mask_from_another_checkout_is_rejected(tmp_path, monkeypatch):
    root, _ = make_saved_input(tmp_path)
    monkeypatch.setattr(engine.inspect, "getfile", lambda function: str(tmp_path / "foreign/research_inputs.py"))
    with pytest.raises(ValueError, match="loaded complete_window_mask"):
        list(engine.load_verified_frames(root))
