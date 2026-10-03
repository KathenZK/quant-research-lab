"""Fail closed before historical bytes, features or account calls."""
if not __debug__:
    raise RuntimeError('M3710 rejects Python -O before input/gates/import')
import json
import re
import shutil
from pathlib import Path
from dependencies import FAMILY, sha

RESERVE_BYTES = 5 * 1024**3
OUTPUT_ALLOWANCE_BYTES = 256 * 1024**2
REQUIRED_C0_PATHS = frozenset('''
README.md M3710.md M3710-core-ledger.md decision-log.md scripts/README.md
scripts/dependencies.py scripts/signals.py scripts/oracle.py scripts/gates.py
scripts/run_replay.py scripts/verify_replay.py scripts/check_causality.py
scripts/rebuild_input.py scripts/restore_run.py scripts/check_indicator_synthetic.py
scripts/check_synthetic.py scripts/check_gates.py
specs/root-rules-v1.json specs/protocol-v1.json specs/contract-pin.json
specs/source-review.safe.json specs/kernel-pin.json specs/adapter-pin.json
specs/adapter-independent-review.safe.json specs/adapter-remote-acceptance.safe.json
specs/environment-lock.json specs/input-manifest.json specs/control-reference.json
specs/control-remote-acceptance.safe.json specs/exposure-v1.json
artifacts/20261003-prehistory-v1/indicator-synthetic.safe.json
artifacts/20261003-prehistory-v1/synthetic-suite.safe.json
artifacts/20261003-prehistory-v1/gate-negative.safe.json
'''.split())

def disk_reserve(output):
    parent = Path(output).absolute().parent
    while not parent.exists():
        parent = parent.parent
    free = shutil.disk_usage(parent).free
    if free < RESERVE_BYTES + OUTPUT_ALLOWANCE_BYTES:
        raise RuntimeError('DISK_RESERVE: require 5GiB plus256MiB output allowance')
    return free


def protocol():
    return json.loads((FAMILY / 'specs/protocol-v1.json').read_text())


def verify_c0():
    path = FAMILY / 'specs/C0-v1.json'
    c0 = json.loads(path.read_text())
    assert c0['id'] == 'M3710' and c0['status'] == 'FROZEN_PRE_HISTORY'
    assert type(c0['files']) is list
    for item in c0['files']:
        assert type(item) is dict and set(item)=={'path','bytes','sha256'}
        assert type(item['path']) is str and item['path']
        assert type(item['bytes']) is int and item['bytes']>0
        assert type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}',item['sha256'])
        relative = Path(item['path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        assert relative.as_posix()==item['path'] and '\\' not in item['path']
    paths = [x['path'] for x in c0['files']]
    assert len(paths) == len(set(paths)) and set(paths)==REQUIRED_C0_PATHS
    for item in c0['files']:
        relative = Path(item['path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        p = FAMILY / relative
        assert p.stat().st_size == item['bytes'] and sha(p) == item['sha256'], item['path']
    return c0


def check_gate(path):
    gate = json.loads(Path(path).read_text())
    verify_c0()
    assert gate['status'] == 'ROOT_APPROVED_HISTORY_AFTER_INDEPENDENT_QA'
    assert gate['id'] == 'M3710' and gate['C0_sha256'] == sha(FAMILY / 'specs/C0-v1.json')
    for name, value in [('authorized_strategy_configurations',4),('new_controls',0)]:
        assert type(gate[name]) is int and gate[name] == value
    assert gate['control_independently_accepted'] is True
    assert gate['control_reference_sha256'] == sha(FAMILY / 'specs/control-reference.json')
    assert gate['control_remote_acceptance_sha256'] == sha(FAMILY / 'specs/control-remote-acceptance.safe.json')
    assert gate['adapter_pin_sha256'] == sha(FAMILY / 'specs/adapter-pin.json')
    receipt = gate['independent_code_review']
    assert receipt['status'] == 'PASS' and sha(receipt['local_path']) == receipt['sha256']
    assert type(gate['source_commit']) is str and re.fullmatch('[0-9a-f]{40}',gate['source_commit'])
    return gate
