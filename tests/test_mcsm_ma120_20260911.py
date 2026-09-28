"""MA120 causal timing, partial cash and original-account parity checks."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

DIRECTORY = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts"
sys.path.insert(0, str(DIRECTORY))
from mcsm_baseline_accounting_20260908 import AccountingError, LinearPerpAccount  # noqa: E402
from mcsm_ma120_accounting_20260911 import PartialCashAccount  # noqa: E402
from research_mcsm_ma120_20260911 import choose_entries, choose_exits, features  # noqa: E402


def sample():
    month = pd.Timestamp("2021-01-01T00:00Z")
    days = pd.date_range(month - pd.Timedelta(days=125), month + pd.Timedelta(days=31))
    d = pd.DataFrame({"symbol": "S", "ts": days, "open": 101., "close": 100.,
                      "eligible": True, "research_segment_id": 1})
    h = pd.DataFrame({"symbol": ["S"], "month": month, "entry_ts": month + pd.Timedelta(minutes=15),
                      "exit_ts": month + pd.offsets.MonthBegin(1) + pd.Timedelta(minutes=15), "weight": .1})
    return month, h, d


def test_120_complete_closes_not_current_month_close():
    month, h, d = sample()
    d.loc[d.ts.eq(month), "close"] = 10000.
    f = features(d, {"S"})
    e = choose_entries(h, f).iloc[0]
    assert e.admitted and e.ma120_known_at_0000 == 100.
    assert not f.iloc[118].valid120 and f.iloc[119].valid120


def test_open_at_ma_no_entry():
    month, h, d = sample()
    d.loc[d.ts.eq(month), "open"] = 100.
    assert not choose_entries(h, features(d, {"S"})).admitted.any()


def test_exit_first_close_below_next_0015_no_reentry():
    month, h, d = sample()
    d.loc[d.ts.eq(month + pd.Timedelta(days=2)), "close"] = 90.
    f = features(d, {"S"})
    signals, exits = choose_exits(h, choose_entries(h, f), f)
    assert len(exits) == 1 and len(signals) == 3
    assert exits.exit_ts.iloc[0] == month + pd.Timedelta(days=3, minutes=15)


def test_equal_ma_does_not_exit():
    _, h, d = sample()
    f = features(d, {"S"})
    assert choose_exits(h, choose_entries(h, f), f)[1].empty


@pytest.mark.parametrize("bad", ["missing", "ineligible", "identity"])
def test_broken_120_history_not_entered(bad):
    month, h, d = sample()
    idx = d.index[d.ts.eq(month - pd.Timedelta(days=20))][0]
    if bad == "missing":
        d = d.drop(index=idx)
    elif bad == "ineligible":
        d.loc[idx, "eligible"] = False
    else:
        d.loc[d.index >= idx, "research_segment_id"] = 2
    assert not choose_entries(h, features(d, {"S"})).admitted.any()


def test_known_identity_restart_cannot_bridge():
    month = pd.Timestamp("2026-01-01T00:00Z")
    days = pd.date_range(month - pd.Timedelta(days=125), month)
    d = pd.DataFrame({"symbol": "LIT/USDT:USDT", "ts": days, "open": 101., "close": 100.,
                      "eligible": True, "research_segment_id": 1})
    f = features(d, {"LIT/USDT:USDT"})
    assert not f.iloc[-2].valid120
    assert f.iloc[-2].reason == "IDENTITY_RESTART_120_DAYS_NOT_READY"


def test_unknown_held_indicator_fails_not_silently_kept():
    month, h, d = sample()
    d.loc[d.ts.eq(month + pd.Timedelta(days=2)), "eligible"] = False
    f = features(d, {"S"})
    with pytest.raises(ValueError, match="unknown held"):
        choose_exits(h, choose_entries(h, f), f)


def test_arrow_same_ma_and_entries():
    _, h, d = sample()
    f = features(d, {"S"})
    a = features(d.convert_dtypes(dtype_backend="pyarrow"), {"S"})
    assert np.allclose(a.ma120.astype(float), f.ma120, equal_nan=True)
    assert choose_entries(h, a).admitted.equals(choose_entries(h, f).admitted)


def test_partial_cash_keeps_ten_percent_not_renormalized():
    a = PartialCashAccount(100000.)
    row = a.rebalance("2021-01-01T00:15Z", {"S": .1, "T": .1}, {"S": 100., "T": 50.})
    post = 100000. / (1 + .2 * .0014)
    assert row["equity"] == pytest.approx(post)
    assert row["gross_notional"] == pytest.approx(.2 * post)
    assert a.positions["S"].quantity == pytest.approx(.1 * post / 100.)
    assert a.positions["T"].quantity == pytest.approx(.1 * post / 50.)


def test_exit_does_not_resize_others_and_flat_month_costs_zero():
    a = PartialCashAccount(100000.)
    a.rebalance("2021-01-01T00:15Z", {"S": .1, "T": .1}, {"S": 100., "T": 50.})
    q = a.positions["T"].quantity
    a.terminal_close("2021-01-02T00:15Z", "S", 90., "test", settlement_fee_rate=.001, settlement_slippage_rate=.0004)
    assert a.positions["T"].quantity == q
    a.rebalance("2021-02-01T00:15Z", {}, {"T": 50.})
    row = a.rebalance("2021-03-01T00:15Z", {}, {})
    assert row["event_fees"] == 0 and row["event_slippage"] == 0


def test_full_cash_adapter_preserves_original_account():
    a, b = PartialCashAccount(), LinearPerpAccount()
    for t, weights, prices in [("2021-01-01T00:15Z", {"S": .5, "T": .5}, {"S": 100., "T": 50.}),
                               ("2021-02-01T00:15Z", {"S": 1.}, {"S": 150., "T": 45.}),
                               ("2021-03-01T00:15Z", {}, {"S": 120.})]:
        assert a.rebalance(t, weights, prices) == b.rebalance(t, weights, prices)


@pytest.mark.parametrize("weights", [{"S": 1.1}, {"S": 0.}, {"S": float("nan")}, {"S": -.1}])
def test_invalid_weights_atomic(weights):
    a = PartialCashAccount()
    before = a.snapshot()
    with pytest.raises(AccountingError):
        a.rebalance("2021-01-01T00:15Z", weights, {"S": 100.})
    assert a.snapshot() == before and not a.ledger
