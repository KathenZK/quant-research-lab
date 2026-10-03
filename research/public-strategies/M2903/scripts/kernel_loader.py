import sys
if not __debug__:
    raise RuntimeError("Python -O is prohibited")
"""Hash-pinned shared v1 only; no copied account engine or other strategy import."""
import hashlib
import importlib.util
from gates import read_json, verify_files
from pathlib import Path

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]

def load(name):
    assert name in ('engine', 'verify_account')
    pin = read_json(FAMILY / 'specs/kernel-pin.json')
    assert pin['root'] == 'research/_shared-kernels/catalog-daily-cash' and pin['version'] == 'v1'
    base = ROOT / pin['root']
    verify_files(base, [dict(path=k, **v) for k, v in pin['files'].items()],
                 {'README.md', 'v1/engine.py', 'v1/verify_account.py', 'v1/manifest.json'})
    path = base / pin['version'] / (name + '.py')
    spec = importlib.util.spec_from_file_location('M2903_catalog_daily_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
