"""Literal weekly rule, terminal-window rejection, and independent selection checks."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts"
sys.path.insert(0, str(SCRIPTS))
from collect_weekly_terminals_20260924 import validate_minutes  # noqa: E402
from research_weekly_top10_20260924 import START, END, choose_terminals, validate_schedule  # noqa: E402
from research_mcsm_weekly_20260911 import decision_dates, feature_table, nominate, qualify_ranked, apply_known_terminals  # noqa: E402
from audit_weekly_top10_20260924 import direct_ranking  # noqa: E402
from complete_weekly_top10_20260924 import verify_daily_coverage  # noqa: E402


def minutes():
    end = pd.Timestamp("2021-12-19T02:00Z")
    start_ms = int((end - pd.Timedelta(hours=1)).timestamp() * 1000)
    rows = [[t, "10", "12", "8", "11", "0", t + 59999] for t in range(start_ms, start_ms + 3600000, 60000)]
    return end, rows


def test_sixty_minute_complete_index_window():
    end, rows = minutes()
    used, prices = validate_minutes(rows, end)
    assert len(used) == 60 and prices == {"center": 10.25, "low": 8., "high": 12.}


@pytest.mark.parametrize("fault", ["missing", "duplicate", "negative", "ohlc", "nan", "unclosed", "order"])
def test_terminal_input_fails_closed(fault):
    end, rows = minutes()
    if fault == "missing":
        rows.pop(4)
    elif fault == "duplicate":
        rows[4] = rows[3].copy()
    elif fault == "negative":
        rows[4][3] = "-1"
    elif fault == "ohlc":
        rows[4][3] = "30"
    elif fault == "nan":
        rows[4][1] = "nan"
    elif fault == "unclosed":
        rows[4][6] += 1
    else:
        rows[4], rows[5] = rows[5], rows[4]
    with pytest.raises(ValueError):
        validate_minutes(rows, end)


def test_monday_calendar_has_no_initial_stub():
    dates = decision_dates("W7", start=START, end=END)
    assert len(dates) == 318 and all(d.dayofweek == 0 for d in dates)
    assert dates[0] == START.floor("D") and dates[-1] == pd.Timestamp("2026-06-29T00:00Z")


def ranked_sample():
    day = pd.Timestamp("2020-06-01T00:00Z")
    frames = []
    for i in range(12):
        time = pd.date_range(day - pd.Timedelta(days=40), day + pd.Timedelta(days=7))
        close = np.ones(len(time)) * 100.
        close[time >= day - pd.Timedelta(days=7)] = 101. + i
        close[time >= day] = 0.1  # unknown future collapses must not affect selection
        frames.append(pd.DataFrame({"symbol": f"S{i:02}/USDT:USDT", "ts": time, "close": close,
                                    "quote_volume": 20_000_000., "eligible": True, "research_segment_id": 1}))
    daily = pd.concat(frames, ignore_index=True)
    endpoints = pd.DataFrame({"symbol": daily.symbol.unique(), "ts": day, "eligible": True, "research_window_valid": True})
    return day, daily, endpoints


def test_past_week_rank_not_future_and_independent_matches():
    day, daily, endpoints = ranked_sample()
    features = feature_table(daily)
    ranked, _ = nominate(features, "W7", start=day + pd.Timedelta(minutes=15), end=day + pd.Timedelta(days=7, minutes=15), all_candidates=True)
    selected, _ = qualify_ranked(ranked, endpoints)
    assert selected.symbol.tolist() == [f"S{i:02}/USDT:USDT" for i in range(11, 1, -1)]
    assert selected.formation_return.iloc[0] == pytest.approx(.12)
    check = direct_ranking(daily, endpoints, selected)
    assert check["weekly_slots"] == 10


def test_inactive_prior_name_is_not_bought():
    day, daily, endpoints = ranked_sample()
    endpoints.loc[endpoints.symbol.eq("S11/USDT:USDT"), "eligible"] = False
    ranked, _ = nominate(feature_table(daily), "W7", start=day + pd.Timedelta(minutes=15),
                         end=day + pd.Timedelta(days=7, minutes=15), all_candidates=True)
    selected, _ = qualify_ranked(ranked, endpoints)
    assert selected.symbol.tolist() == [f"S{i:02}/USDT:USDT" for i in range(10, 0, -1)]
    assert direct_ranking(daily, endpoints, selected)["weekly_slots"] == 10


def test_terminal_keeps_leg_and_clips_to_true_date_no_successor():
    entry = pd.Timestamp("2021-12-13T00:15Z")
    terminal = pd.Timestamp("2021-12-19T02:00Z")
    h = pd.DataFrame({"symbol": ["BZRX/USDT:USDT"], "entry_ts": entry,
                      "scheduled_exit_ts": pd.Timestamp("2021-12-20T00:15Z")})
    got = apply_known_terminals(h, [{"symbol": "BZRX/USDT:USDT", "ts": terminal}])
    assert got.symbol.tolist() == ["BZRX/USDT:USDT"] and got.exit_ts.iloc[0] == terminal
    assert bool(got.terminal.iloc[0])


def test_terminal_sensitivity_does_not_mutate_sources():
    original = [{"center": 10., "low": 9., "high": 11.}]
    assert choose_terminals(original, "low")[0]["center"] == 9.
    assert choose_terminals(original, "high")[0]["center"] == 11.
    assert original[0]["center"] == 10.
    with pytest.raises(ValueError):
        choose_terminals(original, "best")


def test_missing_whole_week_is_detected():
    rows = []
    for strategy in ["B0", "W7"]:
        dates = pd.date_range(START.floor("D"), END.floor("D") - pd.Timedelta(days=1), freq="MS" if strategy == "B0" else "W-MON")
        for i, d in enumerate(dates):
            end = dates[i+1] + pd.Timedelta(minutes=15) if i+1 < len(dates) else END
            for j in range(10):
                rows.append({"strategy": strategy, "symbol": f"S{j}", "weight": .1,
                             "entry_ts": d + pd.Timedelta(minutes=15), "scheduled_exit_ts": end})
    frame = pd.DataFrame(rows)
    validate_schedule(frame)
    broken = frame.loc[~(frame.strategy.eq("W7") & frame.entry_ts.eq(START + pd.Timedelta(days=7)))]
    with pytest.raises(ValueError, match="incomplete"):
        validate_schedule(broken)


def test_official_terminal_does_not_require_post_terminal_zero_volume_marks():
    entry = pd.Timestamp("2025-08-11T00:15Z")
    terminal = pd.Timestamp("2025-08-11T09:00Z")
    h = pd.DataFrame({"symbol": ["MEMEFI/USDT:USDT"], "entry_ts": entry,
                      "scheduled_exit_ts": pd.Timestamp("2025-08-18T00:15Z")})
    daily = pd.DataFrame({"ts": [entry.floor("D")], "symbol": ["MEMEFI/USDT:USDT"], "close": [1.], "eligible": [True]})
    clipped = apply_known_terminals(h, [{"symbol": "MEMEFI/USDT:USDT", "ts": terminal}])
    assert verify_daily_coverage(clipped, daily) == 0
    with pytest.raises(ValueError, match="unresolved daily price"):
        verify_daily_coverage(apply_known_terminals(h, []), daily)


def test_invalid_pre_terminal_mark_still_rejected():
    h = pd.DataFrame({"symbol": ["X/USDT:USDT"], "entry_ts": pd.Timestamp("2023-05-22T00:15Z"),
                      "exit_ts": pd.Timestamp("2023-05-25T09:00Z")})
    daily = pd.DataFrame({"ts": pd.date_range("2023-05-22", periods=3, tz="UTC"), "symbol": "X/USDT:USDT",
                          "close": 1., "eligible": [True, False, True]})
    with pytest.raises(ValueError, match="unresolved daily price"):
        verify_daily_coverage(h, daily)
