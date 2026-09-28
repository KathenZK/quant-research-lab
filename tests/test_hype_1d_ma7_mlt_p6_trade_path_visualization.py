from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import pytest

pytestmark = pytest.mark.local_data

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "research/hype/1d-ma7-machine-learning-trend/artifacts"
STEM = "hype_1d_ma7_mlt_p6_v7_anchor_three_head_lifecycle_2026-08-28"
HTML = ARTIFACT_DIR / f"{STEM}_v7_1_training_trade_paths.html"
MANIFEST = ARTIFACT_DIR / f"{STEM}_v7_1_training_trade_paths_manifest.json"


def _require_retained_artifacts(*paths: Path) -> None:
    missing = [path for path in paths if not path.exists()]
    if missing:
        pytest.skip(
            "retained trade-path artifacts unavailable: "
            + ", ".join(path.name for path in missing)
        )


def assert_hashed(path: Path) -> None:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    assert sidecar.exists()
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest()
        == sidecar.read_text(encoding="utf-8").split()[0]
    )


def test_p6_v7_training_manifest_has_complete_paths() -> None:
    _require_retained_artifacts(HTML, MANIFEST)
    assert_hashed(HTML)
    assert_hashed(MANIFEST)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["holdout_read"] is False
    assert manifest["candles"] == 365
    assert manifest["ma7_points"] == 359
    assert manifest["full_probability_points"] == {
        "entry": 186,
        "survival": 356,
        "reversal": 85,
    }
    assert manifest["confirmation_probability_points"] == {
        "entry": 49,
        "survival": 80,
        "reversal": 16,
    }
    assert manifest["equity_points"] == {
        "P6_FULL": 366,
        "V7_FULL": 366,
        "P6_IC": 81,
        "V7_IC": 81,
    }
    assert manifest["trades_by_strategy"] == {
        "P6_FULL": 25,
        "V7_FULL": 17,
        "P6_IC": 5,
        "V7_IC": 2,
    }
    assert manifest["episodes"] == 23
    assert manifest["new_captures"] == 5
    assert manifest["line_render_count"] == 49
    assert manifest["external_dependencies"] == 0
    assert manifest["window"]["days"] == 365
    assert manifest["window"]["confirmationDays"] == 80


def test_p6_v7_training_html_is_interactive_and_auditable() -> None:
    _require_retained_artifacts(HTML)
    html = HTML.read_text(encoding="utf-8")
    assert "__PAYLOAD__" not in html
    assert "http://" not in html
    assert "https://" not in html
    for token in (
        "setPointerCapture",
        "releasePointerCapture",
        "ondblclick=reset",
        "focusIc",
        "nextExtra",
        "nextIcLoss",
        "完整365日",
        "最后80日内部确认",
        "MA7",
        "后81日冻结窗口没有读取",
        "ctx.lineTo(x2,y2)",
    ):
        assert token in html
    match = re.search(r"const DATA=(.*),DAY=86400000", html)
    assert match is not None
    payload = json.loads(match.group(1))
    assert len(payload["candles"]) == 365
    assert len(payload["trades"]) == 49
    assert len(payload["episodes"]) == 23
    ids = [row["id"] for row in payload["trades"]]
    assert len(ids) == len(set(ids))
    assert all(row["entryT"] <= row["exitT"] for row in payload["trades"])
    assert all("entry" in row and "exit" in row for row in payload["trades"])
    assert sum(row["strategy"] == "P6_FULL" for row in payload["trades"]) == 25
    assert sum(row["strategy"] == "V7_FULL" for row in payload["trades"]) == 17
    assert sum(row["strategy"] == "P6_IC" for row in payload["trades"]) == 5
    assert sum(row["strategy"] == "V7_IC" for row in payload["trades"]) == 2
    assert sum(row["classification"] == "P6_NEW_CAPTURE" for row in payload["episodes"]) == 5
    assert payload["metrics"]["P6_FULL"]["trades"] == 25
    assert payload["metrics"]["V7_FULL"]["trades"] == 17
    assert payload["metrics"]["P6_IC"]["trades"] == 5
    assert payload["metrics"]["V7_IC"]["trades"] == 2
    assert payload["status"].startswith("DEVELOPMENT_FAILED_HOLDOUT_LOCKED")
    assert payload["window"]["days"] == 365
    assert payload["window"]["confirmationDays"] == 80
