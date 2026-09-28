import json
import numpy as np
import pandas as pd
import pytest
from strategy_lab.discovery import campaign
from strategy_lab.discovery.signals import signal_arrays
from strategy_lab.research.trials import TrialRegistry


def sample():
    rng = np.random.default_rng(71)
    c = 100 + np.cumsum(rng.normal(0, 1, 300))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame(
        {
            "ts": pd.date_range("2020-01-01", periods=len(c), tz="UTC"),
            "open": o,
            "high": np.maximum(o, c) + 1,
            "low": np.minimum(o, c) - 1,
            "close": c,
            "volume": 1.0,
        }
    )


@pytest.mark.parametrize(
    "rid,old_name,params",
    [
        ("EV3-M0234-BTC-EUR", "PRICE_SMA", [50]),
        ("EV3-M0233-BTC-EUR", "ZSCORE_REVERSION", [20, 1.5]),
        ("EV3-M0256-BTC-EUR", "EMA_CROSSOVER", [8, 21]),
    ],
)
def test_existing_three_sources_match_frozen_signal_implementation(
    rid, old_name, params
):
    bars = sample()
    engine = campaign.load_module(campaign.ENGINE)
    actual = signal_arrays(bars, rid)
    expected = engine.signals(bars, old_name, params)
    for a, b in zip(actual, expected):
        np.testing.assert_array_equal(a, b)


def test_registered_signal_account_timing_and_roundtrip_cash_identity():
    bars = sample()
    enter, leave, _ = signal_arrays(bars, "M5676")
    engine = campaign.load_module(campaign.ENGINE)
    engine.signals = lambda *_: (enter, leave)
    c = dict(
        signal="REGISTERED",
        parameters=[],
        minutes=1440,
        initial_cash=10000,
        evaluation_start="2020-01-01T00:00:00Z",
        fee_bps=10,
        slippage_bps=5,
    )
    a, f, t = engine.replay(bars, c)
    first = np.flatnonzero(enter)[0] + 1
    assert f.iloc[0].ts == str(bars.ts.iloc[first])
    assert f.iloc[0].price == pytest.approx(bars.open.iloc[first] * 1.0005)
    assert a.equity.iloc[-1] == pytest.approx(10000 + t.pnl.sum())
    assert a.fee.sum() == pytest.approx(f.fee.sum())
    changed = bars.copy()
    changed.loc[240:, ["open", "high", "low", "close"]] *= 2
    b, _, _ = engine.replay(changed, c)
    np.testing.assert_allclose(a.equity[:240], b.equity[:240])


def test_budget_includes_failed_attempt_and_code_revision(tmp_path):
    plan = {
        "config": {},
        "campaign_id": "test",
        "strategy_trial_cap": 1,
        "dataset_sha256": "a" * 64,
        "evaluation_start": "2020-01-01",
        "split": "2021-01-01",
        "end": "2022-01-01",
        "code_files": {"code": "b" * 64},
        "objective": "test scope",
        "decision_method": "retain every attempt",
    }
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    reg = TrialRegistry(tmp_path / "trials.jsonl")
    reg.register_campaign(
        "test",
        selection_goal="test",
        scope_definition="test",
        history_reason="synthetic test",
    )
    t = {
        "trial_id": "same",
        "record_id": "INTERNAL_BUY_HOLD",
        "parent_experiment_id": None,
    }
    campaign.register_trials(tmp_path, plan, [t], [])
    reg.record(
        t["attempt_id"],
        event_id="start",
        state="started",
        results_observed="UNOBSERVED",
        affects_selection="NO",
        reason="test",
    )
    reg.record(
        t["attempt_id"],
        event_id="failure",
        state="failed",
        results_observed="OBSERVED",
        affects_selection="YES",
        reason="test",
    )
    plan["code_files"]["code"] = "c" * 64
    with pytest.raises(ValueError, match="budget exhausted"):
        campaign.register_trials(
            tmp_path,
            plan,
            [
                {
                    "trial_id": "same",
                    "record_id": "INTERNAL_BUY_HOLD",
                    "parent_experiment_id": None,
                }
            ],
            [],
        )
    assert reg.snapshot(["test"])["raw_attempts"] == 1


def test_component_checkpoint_rejects_mutated_plan_and_artifact(tmp_path):
    from strategy_lab.discovery.component import validate_retained_result
    from strategy_lab.factor_study.pipeline import ref

    plan = tmp_path / "plan.json"
    artifact = tmp_path / "account.parquet"
    plan.write_text('{"frozen": true}')
    artifact.write_bytes(b"retained table bytes")
    result = {"plan": ref(plan), "artifacts": [ref(artifact)]}
    validate_retained_result(result, plan)
    artifact.write_bytes(b"changed outcome")
    with pytest.raises(ValueError, match="artifact changed"):
        validate_retained_result(result, plan)
    plan.write_text('{"frozen": false}')
    with pytest.raises(ValueError, match="plan changed"):
        validate_retained_result(result, plan)
