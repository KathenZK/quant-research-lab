"""Pinned definitions for the two separate V3 opportunity experiments."""
from dataclasses import replace
from pathlib import Path
import importlib.util
import json
import sys
from common import ROOT, BASE, sha, write_json

R = BASE / 'artifacts/v3_opportunity_20260913'
PIN = BASE / 'specs/v3-opportunity-engine-pin-20260913.json'
NAMES = {'V3': '原V3', 'E_STATE': '候选按价格状态失效', 'TP_PROTECT': '空单止盈改跟踪保护'}

def engine():
    pin = json.loads(PIN.read_text())
    path = ROOT / pin['engine_path']
    assert sha(path) == pin['engine_sha256']
    name = 'ma7_opportunity_frozen_v6'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]

def config(arm):
    e = engine()
    base = e.Config(reverse=False, progress_days=4, fee=.001, slip=.0004)
    if arm == 'V3': return base
    if arm == 'E_STATE': return replace(base, entry_wait_policy='until_invalid', entry_wait_days=0)
    if arm == 'TP_PROTECT': return replace(base, short_exit='accel1_rsi30_protect')
    raise ValueError(arm)

def verify_preconditions():
    for path, digest in json.loads((R/'before_results.json').read_text())['pins'].items():
        assert sha(ROOT/path) == digest, path
    assert json.loads((R/'inputs/completion.json').read_text())['complete']
    assert json.loads((R/'diagnostics/completion.json').read_text())['complete']
    engine()
