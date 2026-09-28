"""资金费核算合成边界；不读取真实费率、价格或策略结果。"""
from types import SimpleNamespace
import json

import numpy as np
import pandas as pd
import pytest

import audit_funding as funding_module
from audit_funding import audit_common_opportunities, funding_for_position, no_position_funding


def fixture():
    dates = pd.date_range("2026-01-01", periods=5, freq="D", tz="UTC")
    bars = pd.DataFrame({"symbol": "SYNTH", "ts": dates, "close": [90., 100., 110., 120., 130.],
                         "eligible": True, "research_segment_id": "S1"})
    times = ["2026-01-02T00:00:00Z", "2026-01-02T08:00:00.001Z", "2026-01-03T00:00:00Z"]
    events = pd.DataFrame({"symbol": "SYNTH", "event_id": ["E0", "E1", "E2"],
                           "ts": pd.to_datetime(times, utc=True, format="ISO8601"), "rate_type": "Regular",
                           "funding_rate": [0.1, .01, -.02], "mark_price": [100., 105., 110.],
                           "event_unambiguous": True})
    expected = events[["symbol", "event_id", "ts", "rate_type", "funding_rate"]].assign(segment_id="F1")
    segments = pd.DataFrame({"symbol": ["SYNTH"], "segment_id": ["F1"], "start": [dates[0]], "end": [dates[4]]})
    data = SimpleNamespace(events=events, expected=expected, segments=segments,
                           manifest={"cutoff_utc": "2026-01-06T00:00:00Z"})
    return data, bars


def calculate(data, bars, **kwargs):
    return funding_for_position(data, symbol="SYNTH", entry_ts="2026-01-02T00:00:00Z",
                                exit_ts="2026-01-03T00:00:00Z", qty=2,
                                bars=bars, research_segment_id="S1", **kwargs)


def test_native_milliseconds_entry_excluded_exit_included_and_negative_rate_credit():
    data, bars = fixture()
    r = calculate(data, bars)
    assert r["events"] == 2
    assert r["all_mark_prices_real"]
    assert r["funding_real_cash"] == pytest.approx(-2 * 105 * .01 + 2 * 110 * .02)
    assert r["event_rows"][0]["event_ts"].microsecond == 1000
    assert not r["net_research_gate_passed"]


def test_missing_mark_uses_preceding_utc_day_not_same_day_or_last_available_day():
    data, bars = fixture()
    data.events.loc[1, "mark_price"] = np.nan
    r = calculate(data, bars)
    assert np.isnan(r["funding_real_cash"])
    assert r["funding_with_daily_close_proxy_cash"] == pytest.approx(-2 * 90 * .01 + 2 * 110 * .02)
    first = r["event_rows"][0]
    assert first["proxy_bar_open_ts"] == pd.Timestamp("2026-01-01", tz="UTC")
    assert first["proxy_close_known_ts"] < first["event_ts"]
    assert r["real_mark_events"] == r["proxy_mark_events"] == 1


@pytest.mark.parametrize("kind", ["absent", "ineligible", "other_segment", "nonpositive"])
def test_bad_daily_proxy_never_forward_filled_or_crosses_segment(kind):
    data, bars = fixture()
    data.events.loc[1, "mark_price"] = np.nan
    if kind == "absent":
        bars = bars.iloc[1:]
    elif kind == "ineligible":
        bars.loc[0, "eligible"] = False
    elif kind == "other_segment":
        bars.loc[0, "research_segment_id"] = "OLD"
    else:
        bars.loc[0, "close"] = 0
    r = calculate(data, bars)
    assert r["calendar_event_set_verified"]
    assert np.isnan(r["funding_with_daily_close_proxy_cash"])
    assert r["unknown_mark_events"] == 1


@pytest.mark.parametrize("kind", ["missing", "extra", "rate_change", "timestamp_change", "type_change", "ambiguous", "cross_segment", "none", "cutoff"])
def test_missing_or_unproven_funding_is_unknown_never_zero(kind):
    data, bars = fixture()
    if kind == "missing":
        data.events = data.events.drop(1)
    elif kind == "extra":
        data.events = pd.concat([data.events, data.events.iloc[[1]].assign(event_id="EXTRA")], ignore_index=True)
    elif kind == "rate_change":
        data.events.loc[1, "funding_rate"] += .001
    elif kind == "timestamp_change":
        data.events.loc[1, "ts"] += pd.Timedelta(milliseconds=1)
    elif kind == "type_change":
        data.events.loc[1, "rate_type"] = "Special"
    elif kind == "ambiguous":
        data.events.loc[1, "event_unambiguous"] = False
    elif kind == "cross_segment":
        data.segments.loc[0, "end"] = pd.Timestamp("2026-01-02T16:00Z")
    elif kind == "none":
        data.events = data.events.iloc[:0]
        data.segments = data.segments.iloc[:0]
    else:
        data.manifest["cutoff_utc"] = "2026-01-02T20:00:00Z"
    r = calculate(data, bars)
    assert r["funding_status"].startswith("UNKNOWN")
    assert not r["calendar_event_set_verified"]
    assert np.isnan(r["funding_real_cash"]) and np.isnan(r["funding_with_daily_close_proxy_cash"])


def test_proven_window_with_no_scheduled_events_is_legitimate_zero():
    data, bars = fixture()
    r = funding_for_position(data, symbol="SYNTH", entry_ts="2026-01-02T09:00Z",
                             exit_ts="2026-01-02T10:00Z", qty=2, bars=bars)
    assert r["calendar_event_set_verified"] and r["events"] == 0
    assert r["funding_real_cash"] == 0
    assert no_position_funding()["funding_real_cash"] == 0


def opportunities():
    return pd.DataFrame([{"origin_id": "O1", "symbol": "SYNTH", "policy": p, "cost_id": "base",
                          "origin_ts": pd.Timestamp("2026-01-01", tz="UTC"),
                          "normal_complete": True, "entered": p != "C", "entry_ts": "2026-01-02T00:00Z",
                          "exit_ts": "2026-01-03T00:00Z", "qty": .001, "return": .05 if p != "C" else 0,
                          "complete_window_60": True, "budget": 1.0}
                         for p in ("A", "B", "C")])


def test_common_origin_pair_keeps_c_no_trade_zero_and_marks_unknown_without_deleting_origin():
    data, bars = fixture()
    s = opportunities()
    result = audit_common_opportunities(s, {"SYNTH": bars}, data)
    row = result["paired"].iloc[0]
    assert row.all_three_actual_marks and row.real_funding_C == 0
    assert row.real_funding_C_minus_B < 0
    data.events.loc[1, "mark_price"] = np.nan
    result = audit_common_opportunities(s, {"SYNTH": bars}, data)
    row = result["paired"].iloc[0]
    assert not row.all_three_actual_marks and row.all_three_proxy_cash_available
    assert len(result["opportunities"]) == 3
    data.segments = data.segments.iloc[:0]
    result = audit_common_opportunities(s, {"SYNTH": bars}, data)
    row = result["paired"].iloc[0]
    assert len(result["paired"]) == 1 and not row.all_three_rate_covered
    assert np.isnan(row.real_funding_B_minus_A)


def test_incomplete_three_arm_price_path_remains_in_denominator_not_fee_pair():
    data, bars = fixture()
    s = opportunities()
    s.loc[0, "normal_complete"] = False
    s.loc[0, "return"] = np.nan
    result = audit_common_opportunities(s, {"SYNTH": bars}, data)
    assert len(result["denominators"]) == 1
    assert not result["denominators"].all_three_price_normal_complete.any()
    assert result["paired"].empty


def test_early_normal_exit_does_not_promote_incomplete_common_60day_price_window():
    data, bars = fixture()
    s = opportunities()
    s["complete_window_60"] = False
    result = audit_common_opportunities(s, {"SYNTH": bars}, data)
    assert result["denominators"].all_three_price_normal_complete.all()
    assert not result["denominators"].primary_price_pair.any()
    assert result["paired"].empty


@pytest.mark.parametrize("kind", ["naive", "negative_qty", "duplicate_bars"])
def test_invalid_inputs_raise_instead_of_becoming_unknown(kind):
    data, bars = fixture()
    args = {"symbol": "SYNTH", "entry_ts": "2026-01-02T00:00Z", "exit_ts": "2026-01-03T00:00Z", "qty": 1, "bars": bars}
    if kind == "naive":
        args["entry_ts"] = "2026-01-02"
    elif kind == "negative_qty":
        args["qty"] = -1
    else:
        args["bars"] = pd.concat([bars.iloc[[0]], bars], ignore_index=True)
    with pytest.raises(ValueError):
        funding_for_position(data, **args)


@pytest.mark.parametrize("change_source_during_audit", [False, True])
def test_synthetic_end_to_end_delivery_and_source_change_rejection(tmp_path, monkeypatch, change_source_during_audit):
    data, bars = fixture()
    data.events.loc[1, "mark_price"] = np.nan
    data.manifest.update(dataset_id="SYNTHETIC_FUNDING", parquet_inventory_fingerprint="synthetic")
    family = tmp_path / "family"
    run = family / "artifacts/synthetic-research"
    run.mkdir(parents=True)
    summary = pd.concat([opportunities(), opportunities().assign(cost_id="slippage_stress")], ignore_index=True)
    for cost in ("base", "slippage_stress"):
        row = {"origin_id": "O1", "symbol": "SYNTH", "origin_ts": pd.Timestamp("2026-01-01", tz="UTC"), "A": .05, "B": .05, "C": 0.}
        pd.DataFrame([row]).to_parquet(run / f"paired-{cost}.parquet", index=False)
    source = run / "source-pin.txt"
    source.write_text("synthetic immutable input")
    pins = {str(source): funding_module.sha(source)}
    funding_root = tmp_path / "synthetic-funding"
    funding_root.mkdir()
    manifest = funding_root / "_MANIFEST.json"
    manifest.write_text(json.dumps({"synthetic": True}))
    monkeypatch.setattr(funding_module, "FAMILY", family)
    monkeypatch.setattr(funding_module, "FUNDING_ROOT", funding_root)
    monkeypatch.setattr(funding_module, "FUNDING_MANIFEST_SHA256", funding_module.sha(manifest))
    monkeypatch.setattr(funding_module, "load_retained_inputs", lambda _: (summary, {"SYNTH": bars}, pins, run))
    monkeypatch.setattr(funding_module, "load_coverage", lambda: data)
    monkeypatch.setattr("sys.argv", ["audit_funding.py", "--research-run", "synthetic-research"])
    if change_source_during_audit:
        original = funding_module.audit_common_opportunities

        def mutate(*args):
            result = original(*args)
            source.write_text("changed mid audit")
            return result

        monkeypatch.setattr(funding_module, "audit_common_opportunities", mutate)
        with pytest.raises(ValueError, match="Input changed during funding audit"):
            funding_module.main()
        assert not (family / "artifacts/funding/summary.json").exists()
    else:
        assert funding_module.main() == 0
        out = family / "artifacts/funding"
        final = json.loads((out / "summary.json").read_text())
        assert final["cost_summaries"][0]["common_actual_mark_cash"] == 0
        assert final["cost_summaries"][0]["common_real_or_proxy_cash"] == 1
        assert final["attributed_event_rows"] == 8
        assert not final["fullcost_verified"] and not final["unknown_funding_filled_with_zero"]
        proxy = pd.read_csv(out / "paired-real_or_daily_proxy-base.csv")
        assert proxy.A.iloc[0] == pytest.approx(.05 - .001 * 90 * .01 + .001 * 110 * .02)
        assert proxy.C.iloc[0] == 0
        with pytest.raises(FileExistsError):
            funding_module.main()
