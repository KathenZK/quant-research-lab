"""Pinned paths and transparent shared-engine loading for this research family."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parents[1]
INPUT = BASE / "artifacts/inputs_20260909"
RESULTS = BASE / "artifacts/results_20260909"
CONTRACT = BASE / "specs/contract-p1-20260909.md"
ENGINE_PATH = ROOT / "research/_shared-kernels/ma7-cross-atr-ratchet/v1/engine.py"
ENGINE_SHA256 = "54f559748b557c81ec21ca53e4f30e09264547e5d0e8cb658716e33cf2f8d72b"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str, allow_nan=False) + "\n")


def load_engine():
    assert sha(ENGINE_PATH) == ENGINE_SHA256, "Pinned shared engine changed"
    name = "ma7_car_generalization_shared_v1"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ENGINE_PATH)
    engine = importlib.util.module_from_spec(spec)
    sys.modules[name] = engine
    spec.loader.exec_module(engine)
    return engine


def cases():
    engine = load_engine()
    base = engine.Config(reverse=False, progress_source="high_low", progress_days=4)
    return [
        ("F0", "固定1.5ATR原止损", replace(base, progress_days=0)),
        ("H4_D0", "4日未刷新后收紧·仅当日穿越", base),
        ("H4_D2", "4日未刷新后收紧·穿越可等2日", replace(base, entry_wait_days=2)),
        ("H4_D3", "4日未刷新后收紧·穿越可等3日", replace(base, entry_wait_days=3)),
    ]
