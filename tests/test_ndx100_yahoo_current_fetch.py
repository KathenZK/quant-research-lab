from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = ROOT / "research/us-indexes/1d-nasdaq100-ma7-regime-continuation"
SCRIPT_PATH = FAMILY_DIR / "scripts/fetch_yahoo_current_ndx100_daily.py"
SPEC = importlib.util.spec_from_file_location("ndx100_yahoo_fetch", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.local_data
def test_current_snapshot_is_explicitly_survivorship_biased() -> None:
    config = MODULE.load_config()
    universe = MODULE.current_universe()
    assert config["study_id"] == "NDX100-1D-MA7-RC-Y0"
    assert config["universe"]["survivorship_bias"] is True
    assert config["research_contract"]["may_replace_historical_point_in_time_p0"] is False
    assert universe["terminal_snapshot_session"].unique().tolist() == ["2026-08-21"]
    assert len(universe) == 102
    assert universe["ticker"].nunique() == 102


def test_parse_chart_reconstructs_split_only_prices_without_adj_close() -> None:
    before = int(pd.Timestamp("2020-08-28", tz="UTC").timestamp())
    split_day = int(pd.Timestamp("2020-08-31", tz="UTC").timestamp())
    payload = {
        "chart": {
            "error": None,
            "result": [
                {
                    "meta": {
                        "symbol": "TEST",
                        "exchangeTimezoneName": "UTC",
                        "fullExchangeName": "NasdaqGS",
                    },
                    "timestamp": [before, split_day],
                    "indicators": {
                        "quote": [
                            {
                                "open": [400.0, 100.0],
                                "high": [404.0, 101.0],
                                "low": [396.0, 99.0],
                                "close": [400.0, 100.0],
                                "volume": [10.0, 40.0],
                            }
                        ],
                        "adjclose": [{"adjclose": [95.0, 100.0]}],
                    },
                    "events": {
                        "splits": {
                            str(split_day): {
                                "date": split_day,
                                "numerator": 4.0,
                                "denominator": 1.0,
                                "splitRatio": "4:1",
                            }
                        },
                        "dividends": {
                            "ignored": {"date": before, "amount": 1.0}
                        },
                    },
                }
            ],
        }
    }
    frame, audit = MODULE.parse_chart("TEST", payload)
    assert frame["close"].tolist() == pytest.approx([100.0, 100.0])
    assert frame["volume"].tolist() == pytest.approx([40.0, 40.0])
    assert frame["yahoo_adj_close"].tolist() == pytest.approx([95.0, 100.0])
    assert audit["split_event_count"] == 1
    assert audit["dividend_event_count"] == 1


@pytest.mark.local_data
def test_completed_yahoo_audit_has_no_hard_price_blocker() -> None:
    audit_path = FAMILY_DIR / "artifacts/ndx100_1d_ma7_rc_y0_yahoo_price_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["universe_security_count"] == 102
    assert audit["usable_ticker_count_including_qqq"] == 103
    assert audit["request_failures"] == []
    assert audit["blockers_for_full_current_universe_study"] == []
