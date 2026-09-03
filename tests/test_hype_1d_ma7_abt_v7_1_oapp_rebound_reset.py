from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd

import pytest



SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "research/hype/1d-ma7-asymmetric-body-trend/scripts"
    / "diagnose_hype_1d_ma7_abt_v7_1_oapp_rebound_reset.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("hype_v7_1_oapp_rr_diagnostic", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


DIAGNOSTIC = load_module()


def test_rebound_reset_requires_two_non_rising_eligible_closes() -> None:
    count = DIAGNOSTIC.OAPPConfirmationPolicy.rebound_count(
        active=True,
        prior_count=0,
        previous_close=57.474,
        close=56.497,
    )
    assert count == 1
    count = DIAGNOSTIC.OAPPConfirmationPolicy.rebound_count(
        active=True,
        prior_count=count,
        previous_close=56.497,
        close=56.895,
    )
    assert count == 1
    count = DIAGNOSTIC.OAPPConfirmationPolicy.rebound_count(
        active=True,
        prior_count=count,
        previous_close=56.895,
        close=56.700,
    )
    assert count == 2
    assert (
        DIAGNOSTIC.OAPPConfirmationPolicy.rebound_count(
            active=False,
            prior_count=count,
            previous_close=56.700,
            close=57.000,
        )
        == 0
    )


@pytest.mark.local_data
def test_rr_incident_switch_prevents_august_16_exit_but_is_terminal_censored() -> None:
    v6 = DIAGNOSTIC.load_module(DIAGNOSTIC.V6_ABLATION_PATH, "rr_test_v6")
    engine = DIAGNOSTIC.load_module(DIAGNOSTIC.ENGINE_PATH, "rr_test_engine")
    adapter = DIAGNOSTIC.load_module(DIAGNOSTIC.ADAPTER_PATH, "rr_test_adapter")
    _, context = DIAGNOSTIC.extended_context(adapter)
    incident_index = next(
        index
        for index, ts in enumerate(context.book.ts)
        if pd.Timestamp(ts) == DIAGNOSTIC.INCIDENT_ENTRY_TS
    )
    _, result, policy = DIAGNOSTIC.run_arm(
        v6,
        engine,
        context,
        "RR",
        window=(0, context.book.count),
        switch_index=incident_index,
        retain=True,
    )
    incident = next(
        trade
        for trade in result.raw.trades
        if pd.Timestamp(trade["entry_ts"]) == DIAGNOSTIC.INCIDENT_ENTRY_TS
    )
    assert pd.Timestamp(incident["exit_ts"]) == pd.Timestamp("2026-08-20T00:00:00Z")
    assert incident["exit_reason"] == "terminal_flatten"
    august_14 = next(row for row in policy.events if row["ts"].startswith("2026-08-14"))
    august_15 = next(row for row in policy.events if row["ts"].startswith("2026-08-15"))
    assert august_14["new_count"] == 1
    assert august_15["close"] > august_15["previous_close"]
    assert august_15["new_count"] == 1
    assert august_15["reason"] is None
