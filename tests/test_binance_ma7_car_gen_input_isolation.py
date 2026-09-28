"""Input batching may isolate only an explicitly named unavailable window."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

_PATH = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/prepare_inputs_v2.py"
_SPEC = importlib.util.spec_from_file_location("ma7_gen_prepare_inputs_v2", _PATH)
module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(module)


def test_isolate_named_missing_window_then_require_fresh_complete_success(monkeypatch, tmp_path):
    request = {"symbols": ["A", "B", "C"], "start": "2025-01-01", "end": "2026-01-01"}
    calls = []

    def fake_load(current):
        calls.append(current)
        if "B" in current["symbols"]:
            raise ValueError("B: no complete eligible feature/label window")
        return SimpleNamespace(prices={s: pd.DataFrame({"x": [s]}) for s in current["symbols"]}, report={"ok": True})

    monkeypatch.setattr(module, "load_inputs", fake_load)
    rows = list(module.load_batch(request, tmp_path, "test"))
    assert [x[0] for x in rows] == ["B", "A", "C"]
    assert rows[0][1] is None
    assert [call["symbols"] for call in calls] == [["A", "B", "C"], ["A", "C"]]
    assert all(call["start"] == request["start"] and call["end"] == request["end"] for call in calls)


@pytest.mark.parametrize("error", ["bundle: parquet content changed", "A: invalid aggregation", "A: empty or mixed-symbol frame"])
def test_all_other_errors_remain_fatal(monkeypatch, tmp_path, error):
    def fake_load(_):
        raise ValueError(error)

    monkeypatch.setattr(module, "load_inputs", fake_load)
    with pytest.raises(ValueError, match=error):
        list(module.load_batch({"symbols": ["A", "B"]}, tmp_path, "test"))
