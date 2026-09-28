from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

pytestmark = pytest.mark.local_data

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "research/hype/1d-ma7-asymmetric-body-trend/scripts"
    / "diagnose_hype_1d_ma7_abt_v7_1_oapp_zero_profit_floor.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("hype_v7_1_oapp_zpf_diagnostic", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


DIAGNOSTIC = load_module()


def test_zero_profit_floor_fails_canonical_return_and_drawdown_gates() -> None:
    base = DIAGNOSTIC.load_module(
        DIAGNOSTIC.BASE_DIAGNOSTIC_PATH, "zpf_test_base"
    )
    v6 = base.load_module(base.V6_ABLATION_PATH, "zpf_test_v6")
    engine = base.load_module(base.ENGINE_PATH, "zpf_test_engine")
    adapter = base.load_module(base.ADAPTER_PATH, "zpf_test_adapter")
    context, _ = base.extended_context(adapter)
    metrics, result, policy = DIAGNOSTIC.run_zpf(
        base,
        v6,
        engine,
        context,
        window=(0, base.CANONICAL_RIGHT),
        retain=True,
    )
    assert metrics["net_return_pct"] == pytest.approx(469.3711549463612)
    assert metrics["chronological_1h_mdd_pct"] == pytest.approx(-25.069266605985163)
    assert metrics["handoff_accept"] == 0
    assert metrics["long_trail_exit"] == 1
    exits = [row for row in policy.events if row["exit"]]
    assert len(exits) == 1
    assert exits[0]["gross_profit_fraction"] == pytest.approx(-0.02143955903089345)
    assert len(result.raw.trades) == 21
