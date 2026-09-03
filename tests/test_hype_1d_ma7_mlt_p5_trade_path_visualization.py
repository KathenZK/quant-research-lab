from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import pytest

pytestmark = pytest.mark.local_data

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "research/hype/1d-ma7-machine-learning-trend/artifacts"
STEM = "hype_1d_ma7_mlt_p5_opportunity_repair_lifecycle_2026-08-28"
HTML = ARTIFACT_DIR / f"{STEM}_v7_1_comparison_trade_paths.html"
MANIFEST = ARTIFACT_DIR / f"{STEM}_v7_1_comparison_trade_paths_manifest.json"


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


def test_p5_v7_comparison_manifest_has_complete_paths() -> None:
    _require_retained_artifacts(HTML, MANIFEST)
    assert_hashed(HTML)
    assert_hashed(MANIFEST)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["candles"] == 446
    assert manifest["ma7_points"] == 440
    assert manifest["probability_points"] == 446
    assert manifest["equity_points"] == {"P5": 447, "V7_1": 447}
    assert manifest["trades_by_strategy"] == {"P5": 39, "V7_1": 20}
    assert manifest["trades_by_segment"] == {"training": 46, "validation": 13}
    assert manifest["episodes"] == 30
    assert manifest["new_captures"] == 8
    assert manifest["line_render_count"] == 59
    assert manifest["external_dependencies"] == 0


def test_p5_v7_comparison_html_is_interactive_and_auditable() -> None:
    _require_retained_artifacts(HTML)
    html = HTML.read_text(encoding="utf-8")
    for token in (
        "setPointerCapture",
        "releasePointerCapture",
        "ondblclick=reset",
        "focusValidation",
        "nextNew",
        "nextLoss",
        "showTrends",
        "p5Smooth",
        "0.55入场 / 0.45退出",
        "稳定趋势区间",
        "完整446日",
        "MA7",
        "P5 虚线",
        "V7.1 实线",
    ):
        assert token in html
    match = re.search(r"const DATA=(.*),DAY=86400000", html)
    assert match is not None
    payload = json.loads(match.group(1))
    assert len(payload["candles"]) == 446
    assert len(payload["trades"]) == 59
    assert len(payload["episodes"]) == 30
    assert sum(row["strategy"] == "P5" for row in payload["trades"]) == 39
    assert sum(row["strategy"] == "V7_1" for row in payload["trades"]) == 20
    assert sum(row["classification"] == "P5_NEW_CAPTURE" for row in payload["episodes"]) == 8
    assert payload["metrics"]["P5"]["training"]["trades"] == 29
    assert payload["metrics"]["P5"]["validation"]["trades"] == 10
    assert payload["metrics"]["V7_1"]["training"]["trades"] == 17
    assert payload["metrics"]["V7_1"]["validation"]["trades"] == 3
    assert payload["insights"]["training"]["extraEpisodes"] == 5
    assert payload["insights"]["validation"]["extraEpisodes"] == 2
