"""Hash-pinned shared v1 only; no copied account engine or other strategy import."""
import hashlib
import importlib.util
import json
from pathlib import Path

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]

def load(name):
    assert name in ('engine', 'verify_account')
    pin = json.loads((FAMILY / 'specs/kernel-pin.json').read_text())
    base = ROOT / pin['root']
    for rel, item in pin['files'].items():
        data = (base / rel).read_bytes()
        assert len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256'], rel
    path = base / pin['version'] / (name + '.py')
    spec = importlib.util.spec_from_file_location('M1347_catalog_daily_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
