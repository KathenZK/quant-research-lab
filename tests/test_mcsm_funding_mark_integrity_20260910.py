import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pandas as pd
import pytest

PATH = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_funding_mark_integrity_20260910.py"
SPEC = importlib.util.spec_from_file_location("independent_mark_integrity", PATH)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
MS = 1583020800000


def row(ms=MS):
    return [ms, "1.1", "1.3", "1.0", "1.2", 0, ms + 59999, 0, 0, 0, 0, 0]


def test_minute_fields_independently_decoded():
    actual, counts = AUDIT.parse_minute_source(json.dumps([row()]).encode(), False, [MS], "BTC/USDT:USDT", "2020-03")
    assert actual[MS] == (1.1, 1.3, 1.0, 1.2)
    assert counts["used_minutes"] == 1


def test_zip_member_and_header():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("BTCUSDT-1m-2020-03.csv", "open_time,open,high,low,close,volume,close_time,q,n,t1,t2,i\n" + ",".join(map(str, row())) + "\n")
    actual, _ = AUDIT.parse_minute_source(stream.getvalue(), True, [MS], "BTC/USDT:USDT", "2020-03")
    assert actual[MS][0] == 1.1
    with pytest.raises(ValueError, match="archive member"):
        AUDIT.parse_minute_source(stream.getvalue(), True, [MS], "ETH/USDT:USDT", "2020-03")


@pytest.mark.parametrize("mutate", [lambda r: r.__setitem__(0, MS * 1000), lambda r: r.__setitem__(6, MS + 60000), lambda r: r.__setitem__(2, .9), lambda r: r.__setitem__(1, 0)])
def test_bad_unit_close_or_ohlc_rejected(mutate):
    raw = row()
    mutate(raw)
    with pytest.raises(ValueError):
        AUDIT.parse_minute_source(json.dumps([raw]).encode(), False, [MS], "BTC/USDT:USDT", "2020-03")


def test_missing_and_duplicate_minutes_rejected():
    with pytest.raises(ValueError, match="absent"):
        AUDIT.parse_minute_source(json.dumps([row()]).encode(), False, [MS + 60000], "BTC/USDT:USDT", "2020-03")
    with pytest.raises(ValueError, match="duplicate"):
        AUDIT.parse_minute_source(json.dumps([row(), row()]).encode(), False, [MS], "BTC/USDT:USDT", "2020-03")


def test_url_does_not_drop_thousand_prefix():
    correct = "https://fapi.binance.com/fapi/v1/markPriceKlines?symbol=1000SHIBUSDT&interval=1m"
    AUDIT.validate_source_url(correct, "1000SHIB/USDT:USDT", "2025-01", False)
    with pytest.raises(ValueError, match="symbol"):
        AUDIT.validate_source_url(correct, "SHIB/USDT:USDT", "2025-01", False)


def test_trade_klines_not_accepted_as_mark():
    with pytest.raises(ValueError, match="official USD-M mark"):
        AUDIT.validate_source_url("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1m", "BTC/USDT:USDT", "2020-03", False)


def test_native_rate_type_and_millisecond_preserved():
    event = SimpleNamespace(ts=pd.Timestamp(MS + 1, unit="ms", tz="UTC"), symbol="MU/USDT:USDT", funding_rate=-.02, source_rate_type="Special")
    raw = [{"symbol": "MUUSDT", "fundingTime": MS + 1, "fundingRate": "-.02", "rateType": "Special", "markPrice": "1000"}]
    assert AUDIT.native_match(raw, event) == 1000
    raw[0]["rateType"] = "Regular"
    with pytest.raises(ValueError, match="uniquely"):
        AUDIT.native_match(raw, event)
