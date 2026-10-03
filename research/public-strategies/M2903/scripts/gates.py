"""Fail-closed local file pins and disk budget; no market input access."""
import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath

RESERVE_BYTES = 5 * 1024**3
OUTPUT_BUDGET_BYTES = 64 * 1024**2
C0_REQUIRED = frozenset({
    'scripts/signals.py', 'scripts/oracle.py', 'scripts/kernel_loader.py',
    'scripts/gates.py', 'scripts/run_replay.py', 'scripts/check_synthetic.py',
    'scripts/check_causality.py', 'scripts/check_gates.py', 'scripts/check_release_metadata.py', 'scripts/check_integration.py',
    'specs/protocol-v1.json', 'specs/root-frozen-rules.json',
    'specs/kernel-pin.json', 'specs/adapter-pin.json', 'specs/environment-lock.json',
    'specs/exposure-v1.json', 'specs/control-reference.json',
    'specs/control-remote-acceptance.safe.json',
})


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def relative_file(base, name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('pin path must be normalized relative POSIX')
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(x in ('', '.', '..') for x in name.split('/')):
        raise ValueError('unsafe pin path')
    base = Path(base).resolve()
    path = base
    for part in pure.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('symlink pin prohibited')
    if not path.is_file() or not path.resolve().is_relative_to(base):
        raise ValueError('pin missing or outside family')
    return path


def verify_files(base, items, required):
    if type(items) is not list or len(items) != len(required):
        raise ValueError('pin count mismatch')
    names = [item['path'] for item in items]
    if len(set(names)) != len(names) or set(names) != set(required):
        raise ValueError('duplicate/missing/unexpected pin paths')
    for item in items:
        path = relative_file(base, item['path'])
        if type(item['bytes']) is not int or item['bytes'] < 0:
            raise ValueError('pin byte count must be integer')
        if not isinstance(item['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', item['sha256']):
            raise ValueError('invalid SHA256')
        data = path.read_bytes()
        if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('pin byte/hash mismatch: ' + item['path'])


def release_counts(gate):
    if type(gate.get('authorized_strategy_configurations')) is not int or gate['authorized_strategy_configurations'] != 4:
        raise ValueError('release must authorize integer four cases')
    if type(gate.get('new_controls')) is not int or gate['new_controls'] != 0:
        raise ValueError('release must authorize integer zero new controls')


def disk_budget(output):
    path = Path(output)
    if path.exists() or path.is_symlink():
        raise ValueError('output already exists')
    parent = path.parent
    while not parent.exists():
        parent = parent.parent
    free = shutil.disk_usage(parent).free
    if free < RESERVE_BYTES + OUTPUT_BUDGET_BYTES:
        raise RuntimeError('need >=5GiB reserve plus64MiB declared output budget')
    return free


def hex_digest(value, length):
    if type(value) is not str or re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is None:
        raise ValueError('digest/commit must be lowercase hexadecimal string')
    return value


def review_file(value):
    # Review receipts are explicitly local, unlike C0 family-relative pins.
    if type(value) is not str or not value or '\x00' in value or '\\' in value:
        raise ValueError('review path must be an explicit local string')
    path = Path(value)
    if any(part in ('.', '..') for part in value.split('/')):
        raise ValueError('review path traversal prohibited')
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise ValueError('review path symlink prohibited')
    if not path.is_file():
        raise ValueError('review receipt missing')
    return path
