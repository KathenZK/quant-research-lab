"""Batch startup retains the original exact validators and fails closed."""
import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest

_PATH = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/startup_batch.py"
_SPEC = importlib.util.spec_from_file_location("ma7_gen_startup_batch", _PATH)
module = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = module
_SPEC.loader.exec_module(module)


@pytest.fixture
def context():
    pin = {"bundle_id": "binance.v3.research_inputs.v2", "bundle_path": "bundle.json", "bundle_sha256": "a"*64}
    bundle = {"observed_asset_classes": {"A": "COIN", "B": "COIN", "C": "COIN"},
              "components": {"1d": {"start_utc": "2025-01-01T00:00:00Z", "last_bar_close_utc": "2025-02-01T00:00:00Z"}}}
    c = module.BatchStartupContext(Path("/tmp"), Path("/tmp/data"), bundle, pin, {},
            ("A", "B"), "2025-01-01T00:00:00Z", "2025-02-01T00:00:00Z", {}, "2025-02-02")
    c.catalog_receipts["1d"] = {"scope_token_sha256": "b"*64}
    return c


def request(context, symbols=None, **changes):
    return {"schema_version": 1, **context.pin, "mode": "price_diagnostic", "timeframe": "1d",
            "symbols": symbols or ["A"], "start": context.start, "end": context.end,
            "gap_policy": "contiguous_segments", "asset_policy": "crypto_only",
            "backward_bars": 29, "forward_bars": 0, **changes}


def raw(symbol):
    return pd.DataFrame({"symbol": symbol, "ts": pd.date_range("2025-01-01", periods=31, tz="UTC"),
        "timeframe": "1d", "is_closed": True, "open": 10.0, "high": 11.0, "low": 9.0,
        "close": 10.5, "volume": 0.0 if symbol == "B" else 1.0,
        "quote_volume": 10.0, "trade_count": 1})


def install_reads(monkeypatch):
    monkeypatch.setattr(module, "_scope_token", lambda _context, _request: object())
    monkeypatch.setattr(module, "read_verified_ohlcv", lambda _, symbol, **__: raw(symbol))


def test_passed_frame_is_exact_original_validator_output(context, monkeypatch):
    install_reads(monkeypatch)
    req = request(context)
    expected, stats = module.validate_price_frame(raw("A"), req, "A", [])
    result = module.require_research_startup_batch(req, context=context)
    pd.testing.assert_frame_equal(expected, result.prices["A"], check_exact=True)
    assert result.report["symbols"]["A"] == stats
    assert result.report["symbol_status"]["A"]["status"] == "PRICE_DIAGNOSTIC_INPUTS_VERIFIED"


def test_one_bad_window_does_not_approve_or_drop_its_normal_peer(context, monkeypatch):
    install_reads(monkeypatch)
    result = module.require_research_startup_batch(request(context, ["A", "B"]), context=context)
    assert set(result.prices) == {"A"}
    assert result.failures == {"B": "B: no complete eligible feature/label window"}
    assert not result.report["all_requested_symbols_verified"]
    assert result.report["status"] == "PRICE_DIAGNOSTIC_BATCH_EVALUATED"


def test_unexpected_reader_error_is_fatal(context, monkeypatch):
    install_reads(monkeypatch)

    def fail(*_args, **_kwargs):
        raise ValueError("parquet changed")

    monkeypatch.setattr(module, "read_verified_ohlcv", fail)
    with pytest.raises(ValueError, match="parquet changed"):
        module.require_research_startup_batch(request(context), context=context)


@pytest.mark.parametrize("changes", [
    {"bundle_sha256": "c"*64},
    {"start": "2025-01-02T00:00:00Z"},
    {"symbols": ["C"]},
    {"backward_bars": 1},
    {"gap_policy": "reject"},
])
def test_context_cannot_be_reused_with_changed_pin_or_scope(context, changes):
    with pytest.raises(ValueError):
        module.require_research_startup_batch(request(context, **changes), context=context)
