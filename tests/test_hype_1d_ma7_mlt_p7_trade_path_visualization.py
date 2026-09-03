from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import pytest

pytestmark = pytest.mark.local_data

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "research/hype/1d-ma7-machine-learning-trend/artifacts"
STEM = "hype_1d_ma7_mlt_p7_cross_asset_survival_overlay_2026-08-28"
HTML = ARTIFACT_DIR / f"{STEM}_v7_1_training_trade_paths.html"
MANIFEST = ARTIFACT_DIR / f"{STEM}_v7_1_training_trade_paths_manifest.json"
LAKE_SUMMARY = ARTIFACT_DIR / f"{STEM}_lake_validation_summary.json"


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


def test_p7_v7_training_manifest_has_complete_paths() -> None:
    _require_retained_artifacts(HTML, MANIFEST, LAKE_SUMMARY)
    assert_hashed(HTML)
    assert_hashed(MANIFEST)
    assert_hashed(LAKE_SUMMARY)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["holdout_read"] is True
    assert manifest["visualization_only"] is True
    assert manifest["p7_contract_validate_ran"] is False
    assert manifest["candles"] == 454
    assert manifest["window"]["trainDays"] == 365
    assert manifest["window"]["validationDays"] == 89
    assert manifest["window"]["lastDay"].startswith("2026-08-27")
    assert manifest["window"]["terminal"].startswith("2026-08-28")
    assert manifest["window"]["continuousValidationEntries"] == 4
    assert manifest["window"]["isolatedValidationTrades"] == 3
    assert manifest["trades_by_strategy"] == {
        "P7_FULL": 21,
        "V7_FULL": 21,
        "P7_VAL": 3,
        "V7_VAL": 3,
    }
    assert manifest["extended_trades"] == 3
    assert manifest["line_render_count"] == 48
    assert manifest["external_dependencies"] == 0
    assert manifest["equity_points"] == {
        "P7_FULL": 455,
        "V7_FULL": 455,
        "P7_VAL": 90,
        "V7_VAL": 90,
    }


def test_p7_v7_training_html_is_interactive_and_auditable() -> None:
    _require_retained_artifacts(HTML)
    html = HTML.read_text(encoding="utf-8")
    assert "__PAYLOAD__" not in html
    assert "http://" not in html
    assert "https://" not in html
    for token in (
        "setPointerCapture",
        "releasePointerCapture",
        "ondblclick=reset",
        "focusVal",
        "focusLast",
        "nextExtra",
        "nextValTrade",
        "完整样本",
        "训练365日",
        "验证期",
        "最后一根K",
        "MA7",
        "空仓重开",
        "ctx.lineTo(x2,y2)",
        "valT-2*DAY",
        "valBoundaryT",
    ):
        assert token in html
    match = re.search(r"const DATA=(.*),DAY=86400000", html)
    assert match is not None
    payload = json.loads(match.group(1))
    assert payload["window"]["trainLastDay"].startswith("2026-05-30")
    assert payload["window"]["valStart"].startswith("2026-05-31")
    assert payload["window"]["lastDay"].startswith("2026-08-27")
    assert payload["window"]["terminal"].startswith("2026-08-28")
    assert payload["candles"][-1]["t"] == payload["window"]["terminalT"] - 86_400_000
    assert len(payload["candles"]) == 454
    assert len(payload["trades"]) == 48
    ids = [row["id"] for row in payload["trades"]]
    assert len(ids) == len(set(ids))
    assert all(row["entryT"] <= row["exitT"] for row in payload["trades"])
    assert all("entry" in row and "exit" in row for row in payload["trades"])
    assert sum(row["strategy"] == "P7_FULL" for row in payload["trades"]) == 21
    assert sum(row["strategy"] == "V7_FULL" for row in payload["trades"]) == 21
    assert sum(row["strategy"] == "P7_VAL" for row in payload["trades"]) == 3
    assert sum(row["strategy"] == "V7_VAL" for row in payload["trades"]) == 3
    assert sum(row["extended"] for row in payload["trades"] if row["strategy"] == "P7_FULL") == 3
    val_entries = [
        row
        for row in payload["trades"]
        if row["strategy"] == "V7_FULL" and row["entryT"] >= payload["window"]["valBoundaryT"]
    ]
    assert len(val_entries) == 4
    assert payload["metrics"]["P7_FULL"]["trades"] == 21
    assert payload["metrics"]["V7_FULL"]["trades"] == 21
    assert payload["metrics"]["P7_VAL"]["trades"] == 3
    assert payload["metrics"]["V7_VAL"]["trades"] == 3
    assert "DEVELOPMENT_FAILED_HOLDOUT_LOCKED" in payload["status"]
    assert payload["window"]["days"] == 454
    assert payload["window"]["validationDays"] == 89
