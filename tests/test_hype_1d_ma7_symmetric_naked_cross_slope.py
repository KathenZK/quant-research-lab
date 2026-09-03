from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

pytestmark = pytest.mark.local_data

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "research/hype/1d-ma7-asymmetric-body-trend/scripts"
    / "research_hype_1d_ma7_symmetric_naked_cross_slope.py"
)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RESEARCH = load_module(SCRIPT_PATH, "hype_snc02_research_test")


@pytest.fixture(scope="module")
def context():
    adapter = load_module(RESEARCH.ADAPTER_PATH, "hype_snc02_adapter_test")
    frozen = adapter.load_context()
    original = frozen.original_harness
    original.HOURLY_CUTOFF = pd.Timestamp("2100-01-01T00:00:00Z")
    original.FUNDING_CUTOFF = pd.Timestamp("2100-01-01T00:00:00Z")
    market = original.load_market(0)
    return SimpleNamespace(
        market=market,
        book=market.book,
        features=market.features,
        engine=frozen.engine,
    )


def test_august_08_is_exact_symmetric_long_signal(context) -> None:
    index = next(
        i
        for i, ts in enumerate(context.book.ts)
        if pd.Timestamp(ts) == pd.Timestamp("2026-08-08T00:00:00Z")
    )
    signal = RESEARCH.qualified_signal(context, index)
    assert signal is not None
    assert signal.target_side == 1
    assert signal.close == pytest.approx(55.114)
    assert signal.previous_close < signal.previous_ma7
    assert signal.close > signal.ma7
    assert signal.slope_atr == pytest.approx(0.1589024656338677)


def test_extended_naked_path_catches_august_trend_but_fails_mdd(context) -> None:
    risk = load_module(RESEARCH.RISK_PATH, "hype_snc02_risk_test")
    metrics, raw, _, _ = RESEARCH.run_backtest(
        context,
        risk,
        start=0,
        right=context.book.count,
    )
    assert metrics["net_return_pct"] == pytest.approx(32.55515373766722)
    assert metrics["chronological_1h_mdd_pct"] == pytest.approx(-50.7945477791502)
    assert metrics["closed_trades"] == 25
    assert metrics["ledger_parity"] == {
        "terminal_equity": True,
        "turnover": True,
        "cost": True,
        "funding": True,
        "trade_count": True,
    }
    latest = raw.trades[-1]
    assert latest["side"] == "long"
    assert latest["entry_ts"] == "2026-08-09T00:00:00+00:00"
    assert latest["entry_price"] == pytest.approx(55.113)
    assert latest["exit_reason"] == "terminal_flatten"
    assert latest["gross_return_pct"] == pytest.approx(26.6252971168327)
