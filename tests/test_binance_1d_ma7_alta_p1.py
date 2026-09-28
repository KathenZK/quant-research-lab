from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

import pytest



ROOT = Path(__file__).resolve().parents[1]
P1_SCRIPT = ROOT / (
    "research/asset-portfolios/1d-ma7-asset-local-temporal-audit/"
    "scripts/research_binance_1d_ma7_alta_p1.py"
)
SUMMARY_PATH = ROOT / (
    "research/asset-portfolios/1d-ma7-asset-local-temporal-audit/"
    "artifacts/p1_temporal_audit_2026-08-10/p1_summary.json"
)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


alta = load_module(P1_SCRIPT, "alta_p1_test_module")


def passing_take_summary() -> dict:
    return {
        "selected_events": 250,
        "side_counts": {"long": 125, "short": 125},
        "main": {"mean": 0.001, "profit_factor": 1.20},
        "positive_asset_count": 12,
        "positive_compound_asset_count": 12,
        "per_asset": {asset: {"selected": 8} for asset in alta.ASSETS},
        "cluster_bootstrap": {"positive_probability": 0.90},
        "variants": {
            name: {"mean": 0.001, "profit_factor": 1.10}
            for name in ("z_4bps", "z_funding_off")
        },
    }


def passing_local_summary() -> dict:
    return {
        "selected_events": 100,
        "assets_with_at_least_5": 15,
        "main": {"mean": 0.001, "profit_factor": 1.20},
        "positive_asset_count": 12,
        "cluster_bootstrap": {"positive_probability": 0.90},
        "variants": {
            name: {"mean": 0.001, "profit_factor": 1.10}
            for name in ("z_4bps", "z_funding_off")
        },
    }


def test_contract_is_asset_local_fixed_and_hype_locked() -> None:
    assert len(alta.ASSETS) == 21
    assert "HYPE" not in alta.ASSETS
    assert alta.ALPHA == 1000.0
    assert alta.QUANTILE == 0.80
    assert alta.T0 == pd.Timestamp("2025-05-31T00:00:00Z")
    assert alta.T1 == pd.Timestamp("2026-08-01T00:00:00Z")
    assert alta.TRAIN_PURGE_END == alta.T0 - pd.Timedelta(days=5)


def test_local_threshold_uses_only_purged_asset_history(monkeypatch) -> None:
    monkeypatch.setattr(alta, "ASSETS", ("AAA",))
    monkeypatch.setattr(alta.tfml, "PRICE_FEATURES", ("prediction",))
    monkeypatch.setattr(
        alta.tfml,
        "fit_model",
        lambda frame, features, alpha: object(),
    )
    monkeypatch.setattr(
        alta.tfml,
        "predict_utility",
        lambda model, frame, features: frame["prediction"].to_numpy(
            dtype="float64"
        ),
    )

    rows = []
    for index in range(100):
        timestamp = pd.Timestamp("2025-01-01T00:00:00Z") + pd.Timedelta(
            days=index
        )
        rows.append(
            {
                "asset": "AAA",
                "signal_ts": timestamp,
                "exit_ts": timestamp + pd.Timedelta(days=1),
                "event_id": f"train-{index}",
                "root_id": f"train-{index}",
                "prediction": float(index),
            }
        )
    rows.extend(
        [
            {
                "asset": "AAA",
                "signal_ts": alta.T0 - pd.Timedelta(days=2),
                "exit_ts": alta.T0 - pd.Timedelta(days=1),
                "event_id": "purged",
                "root_id": "purged",
                "prediction": 10_000.0,
            },
            {
                "asset": "AAA",
                "signal_ts": alta.T0,
                "exit_ts": alta.T0 + pd.Timedelta(days=5),
                "event_id": "test-low",
                "root_id": "test-low",
                "prediction": 79.1,
            },
            {
                "asset": "AAA",
                "signal_ts": alta.T0 + pd.Timedelta(days=1),
                "exit_ts": alta.T0 + pd.Timedelta(days=6),
                "event_id": "test-high",
                "root_id": "test-high",
                "prediction": 79.3,
            },
            {
                "asset": "AAA",
                "signal_ts": alta.T1,
                "exit_ts": alta.T1 + pd.Timedelta(days=5),
                "event_id": "future",
                "root_id": "future",
                "prediction": 20_000.0,
            },
        ]
    )

    take_all, local, model_report = alta.build_policies(pd.DataFrame(rows))

    assert set(take_all["event_id"]) == {"test-low", "test-high"}
    assert set(local["event_id"]) == {"test-low", "test-high"}
    assert np.isclose(model_report["AAA"]["threshold"], 79.2)
    assert local.set_index("event_id")["selected"].to_dict() == {
        "test-low": False,
        "test-high": True,
    }


def test_local_gate_cannot_bypass_failed_substrate_gate() -> None:
    capacity = {"p0_capacity_pass": True}
    take = passing_take_summary()
    local = passing_local_summary()
    delta = {"positive_probability": 0.90}

    assert alta.apply_gate(capacity, take, local, delta)["p1_pass"]

    take["main"]["mean"] = -0.001
    gate = alta.apply_gate(capacity, take, local, delta)
    assert not gate["take_all"]["pass"]
    assert not gate["local_q80_ridge1000"]["checks"]["take_all_gate"]
    assert not gate["local_q80_ridge1000"]["pass"]
    assert not gate["p1_pass"]


@pytest.mark.local_data
def test_retained_terminal_result_and_hype_lock() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))

    assert summary["status"] == "DEVELOPMENT_HARD_GATE_FAILED"
    assert not summary["development_gate"]["p1_pass"]
    assert summary["take_all"]["selected_events"] == 1341
    assert summary["take_all"]["main"]["mean"] < 0.0
    assert summary["take_all"]["cluster_bootstrap"]["quantiles"]["97.5%"] < 0.0
    assert summary["local_q80_ridge1000"]["main"]["mean"] < 0.0
    assert summary["hype_rows"] == 0
    assert summary["hype_files"] == 0
    assert summary["hype_requests"] == 0
