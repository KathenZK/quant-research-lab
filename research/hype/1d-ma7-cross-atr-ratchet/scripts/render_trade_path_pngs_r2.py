"""Render R2 original-entry/stall-only overviews from the verified saved payload."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

import render_trade_path_pngs as renderer

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "artifacts/r2_trade_paths_20260909"
ARMS = ("original_stall_rev1", "original_stall_rev0")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    audit_path = OUT / "chart_audit.json"
    audit = json.loads(audit_path.read_text())
    payload_path = OUT / "payload.json"
    html_path = OUT / "hype-ma7-r2-trade-paths.html"
    assert sha(payload_path) == audit["payload_sha256"]
    assert sha(html_path) == audit["html_sha256"]
    data = json.loads(payload_path.read_text())
    for arm in ARMS:
        summary = data["arms"][arm]["summary"]
        assert summary["entry_mode"] == "original"
        assert summary["tighten_mode"] == "stall_only" and summary["profit_trigger_atr"] == 0
        assert summary["return_pct"] > 0  # The retained R1 renderer prefixes '+' in its subtitle.
    renderer.OUT = OUT
    images = {arm: renderer.render(data, arm) for arm in ARMS}
    receipt = {
        "chart_audit_sha256": sha(audit_path), "payload_sha256": sha(payload_path),
        "chart_html_sha256": sha(html_path), "renderer_wrapper_sha256": sha(Path(__file__)),
        "r1_renderer_sha256": sha(Path(renderer.__file__)),
        "matplotlib_version": matplotlib.__version__, "no_backtest_rerun": True,
        "outputs": {path.name: sha(path) for path in images.values()},
    }
    (OUT / "static_chart_audit.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({arm: str(path) for arm, path in images.items()}, indent=2))


if __name__ == "__main__":
    main()
