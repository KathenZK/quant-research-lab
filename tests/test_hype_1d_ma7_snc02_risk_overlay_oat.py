from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import pytest



ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "research/hype/1d-ma7-asymmetric-body-trend/scripts/"
    "research_hype_1d_ma7_snc02_risk_overlay_oat.py"
)
ARTIFACT = (
    ROOT
    / "research/hype/1d-ma7-asymmetric-body-trend/artifacts/"
    "hype_1d_ma7_snc02_risk_overlay_oat_2026-08-20.json"
)


def load_module():
    spec = importlib.util.spec_from_file_location("snc02_risk_oat_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_artifact() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_stop_fill_uses_adverse_gap_and_intrahour_stop() -> None:
    module = load_module()
    assert module.stop_fill(1, 90.0, 85.0, 88.0, 80.0) == 85.0
    assert module.stop_fill(1, 90.0, 95.0, 98.0, 89.0) == 90.0
    assert module.stop_fill(-1, 110.0, 115.0, 120.0, 112.0) == 115.0
    assert module.stop_fill(-1, 110.0, 105.0, 111.0, 100.0) == 110.0
    assert module.stop_fill(1, 90.0, 95.0, 98.0, 91.0) is None


def test_cost_aware_breakeven_formula() -> None:
    module = load_module()
    cost = 0.0014
    entry = 100.0
    long_price = module.breakeven_price(entry, 1, cost)
    short_price = module.breakeven_price(entry, -1, cost)
    assert math.isclose(long_price * (1.0 - cost), entry * (1.0 + cost))
    assert math.isclose(short_price * (1.0 + cost), entry * (1.0 - cost))


@pytest.mark.local_data
def test_locked_artifact_control_parity_and_verdict() -> None:
    payload = load_artifact()
    expected = {"CTRL_SNC02", "FF3", "MA05", "HS25", "BE20", "PT25_A3"}
    assert set(payload["primary_extended"]) == expected
    assert all(payload["control_parity"][window].values() for window in payload["control_parity"])
    control = payload["primary_extended"]["CTRL_SNC02"]
    assert math.isclose(control["net_return_pct"], 32.55515373766722, abs_tol=2e-10)
    assert math.isclose(
        control["chronological_1h_mdd_pct"],
        -50.7945477791502,
        abs_tol=2e-10,
    )
    assert not any(
        payload["verdict"][arm]["mdd20_pass"]
        for arm in expected
        if arm != "CTRL_SNC02"
    )
    ma05 = payload["primary_extended"]["MA05"]
    assert ma05["net_return_pct"] > control["net_return_pct"]
    assert ma05["chronological_1h_mdd_pct"] > control["chronological_1h_mdd_pct"]
    assert payload["stress"]["MA05"]["lag_1d"]["net_return_pct"] > 0.0


@pytest.mark.local_data
def test_latest_august_trade_is_preserved_except_fail_fast() -> None:
    payload = load_artifact()
    for arm in ("CTRL_SNC02", "MA05", "HS25", "BE20", "PT25_A3"):
        trade = payload["verdict"][arm]["latest_august_long"]
        assert trade["entry_ts"] == "2026-08-09T00:00:00+00:00"
        assert trade["exit_reason"] == "terminal_flatten"
        assert math.isclose(trade["exit_price"], 69.787)
    fail_fast = payload["verdict"]["FF3"]["latest_august_long"]
    assert fail_fast["exit_ts"] == "2026-08-12T00:00:00+00:00"
    assert fail_fast["net_return_pct"] < 0.0


@pytest.mark.local_data
def test_artifact_sha256_sidecar() -> None:
    digest = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    sidecar = Path(f"{ARTIFACT}.sha256").read_text(encoding="utf-8").split()[0]
    assert digest == sidecar
