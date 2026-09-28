import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from strategy_lab.discovery.signals import METHODS, signal_arrays, smooth, rsi

FIX = Path(__file__).parent / "fixtures/discovery/indicators.json"


def bars():
    f = pd.DataFrame(json.loads(FIX.read_text())["input"])
    f["volume"] = 1.0
    f["ts"] = pd.date_range("2020-01-01", periods=len(f), tz="UTC")
    return f


@pytest.mark.parametrize("record", METHODS)
def test_every_registered_method_is_prefix_invariant(record):
    f = bars()
    a = signal_arrays(f, record)
    prefix = signal_arrays(f.iloc[:400], record)
    for x, y in zip(a, prefix):
        np.testing.assert_allclose(np.asarray(x)[:400], y, equal_nan=True)
    assert not (a[0] & a[1]).any()


@pytest.mark.parametrize(
    "record",
    [r for r, v in METHODS.items() if v[1] in json.loads(FIX.read_text())["expected"]],
)
def test_trusted_talib_numeric_parity(record):
    expected = json.loads(FIX.read_text())["expected"][METHODS[record][1]]
    np.testing.assert_allclose(
        signal_arrays(bars(), record)[2],
        np.array(expected, dtype=float),
        rtol=1e-9,
        atol=1e-9,
        equal_nan=True,
    )


def test_hand_seed_and_flat_rsi_boundary():
    np.testing.assert_allclose(smooth(pd.Series([1.0, 2, 3, 4]), 3).iloc[2:], [2, 3])
    assert rsi(pd.Series(np.ones(25)), 14).iloc[-1] == 0
    assert rsi(pd.Series(np.arange(25.0)), 14).iloc[-1] == 100


def test_monthly_never_uses_incomplete_month_and_rejects_unknown():
    f = bars()
    a, b, _ = signal_arrays(f, "M4692")
    assert not (a | b)[~f.ts.dt.is_month_end].any()
    with pytest.raises(ValueError):
        signal_arrays(f, '__import__("os")')


def test_rolling_cmo_and_ulcer_manual_oracles():
    f = bars()
    c = f.close
    for record in ("M5732", "M5714"):
        value = signal_arrays(f, record)[2].iloc[-1]
        if record == "M5732":
            d = np.diff(c.to_numpy()[-15:])
            expected = 100 * d.sum() / np.abs(d).sum()
        else:
            dd = [
                100 * (c.iloc[i] / max(c.iloc[i - 13 : i + 1]) - 1)
                for i in range(len(c) - 14, len(c))
            ]
            expected = np.sqrt(np.mean(np.square(dd)))
        assert value == pytest.approx(expected)
