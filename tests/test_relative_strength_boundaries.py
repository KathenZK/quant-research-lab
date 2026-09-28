import numpy as np
import pandas as pd
import pytest

from strategy_lab.data.factors.cross_sectional import RelativeStrengthFactor
from strategy_lab.data.factors.engine import compute_factor_frame


def panel():
    return pd.DataFrame({
        "symbol": ["A", "A", "B", "B"],
        "ts": pd.to_datetime(["2026-01-01", "2026-01-02"] * 2, utc=True),
        "close": [100., 110., 1000., 1000.], "benchmark_close": [100.] * 4,
    })


def test_two_symbol_hand_example_and_engine_boundary():
    p = panel()
    out = compute_factor_frame(p, RelativeStrengthFactor(1))
    assert out.relative_strength_1.iloc[1] == pytest.approx(.1)
    assert pd.isna(out.relative_strength_1.iloc[2])
    assert out.relative_strength_1.iloc[3] == 0
    changed = p.copy()
    changed.loc[changed.symbol.eq("A"), "close"] *= 17
    pd.testing.assert_series_equal(RelativeStrengthFactor(1).compute(p).iloc[2:],
                                   RelativeStrengthFactor(1).compute(changed).iloc[2:])


def test_segment_exchange_and_market_boundaries():
    p = panel().assign(symbol="A", research_segment_id=[0, 0, 1, 1])
    assert pd.isna(RelativeStrengthFactor(1).compute(p).iloc[2])
    for column in ["exchange", "market_type", "timeframe"]:
        p = panel().assign(symbol="A")
        p[column] = ["first", "first", "second", "second"]
        assert pd.isna(RelativeStrengthFactor(1).compute(p).iloc[2])


def test_future_perturbation_and_missing_prices_do_not_backfill():
    p = pd.DataFrame({"close": [100., 110., np.nan, 121.], "benchmark_close": [100.] * 4})
    initial = RelativeStrengthFactor(1).compute(p)
    p.loc[3, "close"] = 10000
    pd.testing.assert_series_equal(initial.iloc[:3], RelativeStrengthFactor(1).compute(p).iloc[:3])
    assert pd.isna(initial.iloc[2]) and pd.isna(initial.iloc[3])


def test_duplicate_rejected_and_direct_unsorted_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        RelativeStrengthFactor(1).compute(pd.concat([panel(), panel().iloc[:1]]))
    with pytest.raises(ValueError, match="chronological"):
        RelativeStrengthFactor(1).compute(panel().iloc[[1, 0, 2, 3]])


def test_original_nonunique_index_is_preserved():
    p = panel().set_axis([0, 1, 0, 1])
    r = RelativeStrengthFactor(1).compute(p)
    assert list(r.index) == [0, 1, 0, 1]
    assert pd.isna(r.iloc[2])


@pytest.mark.parametrize("periods", [0, -1, True, 1.5])
def test_invalid_periods_rejected(periods):
    with pytest.raises(ValueError, match="positive integer"):
        RelativeStrengthFactor(periods).compute(panel())


def test_missing_identity_rejected():
    p = panel()
    p.loc[2, "symbol"] = None
    with pytest.raises(ValueError, match="identity"):
        RelativeStrengthFactor(1).compute(p)
