#!/usr/bin/env python3
"""Offline batch009 wrapper; requires lawfully held original snapshot and sources.
No downloads, installation, strategy edits, or fallback input acceptance.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

TOPIC = Path(__file__).resolve().parents[1]
REPO = TOPIC.parents[2]
EXPECT = TOPIC / 'specs/expectations.json'
RUNNER = '''import runpy,socket,sys
from unittest.mock import patch
from pathlib import Path
p=sys.argv[1];sys.argv=sys.argv[1:];sys.path.insert(0,str(Path(p).parent))
with patch.object(socket.socket,'connect',side_effect=RuntimeError('OFFLINE_ONLY')),patch.object(socket.socket,'connect_ex',side_effect=RuntimeError('OFFLINE_ONLY')):
 runpy.run_path(p,run_name='__main__')
'''

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def filecheck(path, expected):
    require(path.is_file(), 'MISSING_FILE: ' + path.name)
    if 'bytes' in expected:
        require(path.stat().st_size == expected['bytes'], 'BYTE_MISMATCH: ' + path.name)
    require(sha(path) == expected['sha256'], 'HASH_MISMATCH: ' + path.name)

def preflight(snapshot, sources, expected):
    # Reject wrong inputs before loading any external source or numerical dependency.
    filecheck(snapshot / 'manifest.json', {'sha256': expected['snapshot_manifest_sha256']})
    for item in expected['source_objects']:
        filecheck(snapshot / item['name'], item)
    item = expected['canonical_csv']
    filecheck(snapshot / item['name'], item)
    for name, item in expected['sources'].items():
        filecheck(sources / name, item)
    for name, digest in expected['code_files'].items():
        filecheck(REPO / name, {'sha256': digest})
    for item in expected['ids'].values():
        filecheck(REPO / item['prior_recovery_receipt'], {'sha256': item['prior_recovery_sha256']})
    deps = expected['dependencies']
    require(platform.python_version() == deps['python'], 'DEPENDENCY_BLOCKED: exact Python ' + deps['python'])
    for name in ['numpy', 'pandas', 'TA-Lib', 'freqtrade', 'technical', 'ft-pandas-ta']:
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            raise RuntimeError('DEPENDENCY_BLOCKED: ' + name) from None
        require(version == deps[name], 'DEPENDENCY_BLOCKED: ' + name + '==' + deps[name])
    import talib
    require(talib.__ta_version__.decode().split()[0] == deps['ta_library'], 'DEPENDENCY_BLOCKED: native TA-Lib')
    require(talib.get_compatibility() == deps['talib_compatibility'], 'DEPENDENCY_BLOCKED: TA compatibility')
    require(talib.get_unstable_period('EMA') == deps['ema_unstable_period'], 'DEPENDENCY_BLOCKED: EMA unstable')

def execute(script, args, target, label):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    with (target / (label + '.log')).open('x') as log:
        subprocess.run([sys.executable, '-c', RUNNER, str(script)] + [str(a) for a in args], env=env, stdout=log, stderr=subprocess.STDOUT, check=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot', type=Path, required=True, help='Existing original fb84 snapshot; never downloaded')
    p.add_argument('--sources', type=Path, required=True, help='Existing local union of the 14 pinned files in expectations.json')
    p.add_argument('--output', type=Path, required=True, help='New private directory; must not exist')
    p.add_argument('--preflight-only', action='store_true', help='Hash/dependency checks only; no input reconstruction or replay')
    a = p.parse_args()
    require(not sys.flags.optimize, 'OPTIMIZED_PYTHON_FORBIDDEN: frozen validators use assert')
    expected = json.loads(EXPECT.read_text())
    snapshot, sources, target = a.snapshot.resolve(), a.sources.resolve(), a.output.resolve()
    require(not target.exists(), 'OUTPUT_EXISTS')
    require(target.parent.is_dir(), 'OUTPUT_PARENT_MISSING')
    require(not target.is_relative_to(REPO), 'OUTPUT_MUST_BE_OUTSIDE_GIT_CHECKOUT')
    require(shutil.disk_usage(target.parent).free > 6 * 1024**3, 'DISK_BLOCKED: >6GiB free required, preserving >5GiB')
    preflight(snapshot, sources, expected)
    if a.preflight_only:
        print(json.dumps({'status': 'PREFLIGHT_PASS', 'historical_replays': 0, 'network_requests': 0}))
        return
    target.mkdir()
    # Existing verifier writes to snapshot.parent; isolated copy prevents input mutation.
    for name in ['manifest.json', expected['canonical_csv']['name']] + [x['name'] for x in expected['source_objects']]:
        dst = target / 'snapshot' / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(snapshot / name, dst)
    m311 = REPO / 'research/public-strategies/M0311/scripts'
    execute(m311 / 'audit_input.py', [target / 'snapshot'], target, 'input-qa')
    rebuilt = target / 'independent-rebuilt-native12.csv'
    filecheck(rebuilt, expected['canonical_csv'])
    checks = {}
    for rid, item in expected['ids'].items():
        require(shutil.disk_usage(target).free > 5 * 1024**3 + 256 * 1024**2, 'DISK_BLOCKED: keep >5GiB; preserved partial output')
        result = target / rid / 'results'
        result.parent.mkdir()
        scripts = REPO / 'research/public-strategies' / rid / 'scripts'
        if rid == 'M0311':
            execute(scripts / 'compare_original.py', ['--input', rebuilt, '--sources', sources, '--output', result.parent / 'source-qa.json'], target, rid + '-source')
            execute(scripts / 'run_replay.py', ['--input', rebuilt, '--output', result], target, rid + '-replay')
            execute(scripts / 'validate_independent.py', ['--input', rebuilt, '--results', result, '--output', result.parent / 'oracle.json'], target, rid + '-oracle')
        else:
            execute(scripts / 'run.py', ['run', '--input', rebuilt, '--sources', sources, '--output', result], target, rid + '-replay')
            execute(scripts / 'run.py', ['oracle', '--input', rebuilt, '--results', result, '--output', result.parent / 'oracle.json'], target, rid + '-oracle')
        actual_names = {f.name for f in result.iterdir()}
        require(actual_names == set(item['result_files']), 'RESULT_MEMBERS_MISMATCH: ' + rid)
        for name, fingerprint in item['result_files'].items():
            filecheck(result / name, fingerprint)
        checks[rid] = {'status': 'BYTE_IDENTICAL', 'result_files': len(actual_names)}
    receipt = {'status': 'PASS', 'ids': checks, 'input_qa_runs': 1, 'result_file_count': 88, 'restored_strategy_configurations': 24, 'restored_controls': 1, 'new_experiments': 0, 'network_requests': 0, 'remote_backup_verified': False, 'quality_status': 'DIAGNOSTIC_ONLY', 'PIT': 'UNKNOWN', 'expectations_sha256': sha(EXPECT), 'wrapper_sha256': sha(__file__)}
    with (target / 'recovery-receipt.json').open('x') as f:
        json.dump(receipt, f, indent=2)
        f.write('\n')
    print(json.dumps(receipt, indent=2))

if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit('BLOCKED: ' + str(exc))
