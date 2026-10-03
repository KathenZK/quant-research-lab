"""Verify immutable dependency bytes before importing; never silently fall back."""
if not __debug__:
    raise RuntimeError('M3710 rejects Python -O before gates, inputs or engine import')
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
_CACHE = {}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def pinned_module(pin_name, module_name):
    pin = json.loads((FAMILY / 'specs' / pin_name).read_text())
    base = ROOT / pin['root']
    for relative, record in pin['files'].items():
        data = (base / relative).read_bytes()
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Dependency bytes changed: ' + relative)
    key = (pin_name, module_name)
    if key in _CACHE:
        return _CACHE[key]
    path = base / pin['version'] / (module_name + '.py')
    name = 'M3710_' + pin_name.replace('.', '_') + '_' + module_name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    _CACHE[key] = module
    return module

def engine():
    return pinned_module('kernel-pin.json', 'engine')

def account_verifier():
    return pinned_module('kernel-pin.json', 'verify_account')


def adapter():
    return pinned_module('adapter-pin.json', 'adapter')
