from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd

import pytest



ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "research/hype/1d-ma7-machine-learning-trend/scripts/"
    "run_hype_1d_ma7_mlt_p5_opportunity_repair_lifecycle.py"
)


def load_subject():
    spec = importlib.util.spec_from_file_location("hype_p5_test_subject", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_policy_can_directly_reverse() -> None:
    subject = load_subject()
    result = subject.self_test()
    assert result == {"status": "PASS", "trades": 2, "direct_reversals": 1}


def test_feature_blocks_are_cumulative() -> None:
    subject = load_subject()
    b1 = subject.FEATURE_BLOCKS["B1_ROOT_PATH"]
    b2 = subject.FEATURE_BLOCKS["B2_PRETREND_STRUCTURE"]
    b3 = subject.FEATURE_BLOCKS["B3_PARTICIPATION_FUNDING"]
    assert b2[: len(b1)] == b1
    assert b3[: len(b2)] == b2
    assert len(set(b3)) == len(b3)


@pytest.mark.local_data
def test_development_loader_is_physically_train_only() -> None:
    subject = load_subject()
    p4 = subject.load_module(subject.P4_SCRIPT, "hype_p5_test_p4")
    _, _, _, _, context = p4.load_dependencies(train_only=True)
    assert context.book.count == subject.TRAIN_DAYS
    assert str(context.book.terminal_ts) == "2026-05-31 00:00:00+00:00"
    assert pd.Timestamp(context.market.audit["hourly_end"]) <= pd.Timestamp(
        context.book.terminal_ts
    )
    assert pd.Timestamp(context.market.audit["funding_end"]) <= pd.Timestamp(
        context.book.terminal_ts
    )


def test_validation_requires_hashed_passing_manifest(tmp_path, monkeypatch) -> None:
    subject = load_subject()
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(subject, "MANIFEST_PATH", missing)
    try:
        subject.validate()
    except RuntimeError as exc:
        assert "develop first" in str(exc)
    else:
        raise AssertionError("validation unexpectedly bypassed manifest gate")
