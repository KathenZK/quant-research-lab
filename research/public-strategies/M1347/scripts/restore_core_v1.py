"""Restore frozen results from core code + exact input + public expected hashes.
No network or benchmark execution. Root runs this only after actual remote core retrieval.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from kernel_loader import FAMILY, ROOT, load

engine = load('engine')

def restore(input_path, destination, receipt_path):
    assert not destination.exists()
    destination.mkdir(parents=True)
    family_copy = destination / FAMILY.relative_to(ROOT)
    c0 = json.loads((FAMILY / 'specs/C0-v1.json').read_text())
    for item in c0['files']:
        src = FAMILY / item['path']
        assert src.stat().st_size == item['bytes'] and engine.sha(src) == item['sha256']
        dst = family_copy / item['path']; dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dst)
    shutil.copyfile(FAMILY / 'specs/C0-v1.json', family_copy / 'specs/C0-v1.json')
    pin = json.loads((FAMILY / 'specs/kernel-pin.json').read_text())
    for rel, item in pin['files'].items():
        src = ROOT / pin['root'] / rel
        assert src.stat().st_size == item['bytes'] and engine.sha(src) == item['sha256']
        dst = destination / pin['root'] / rel; dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dst)
    gate = json.loads((FAMILY / 'recovery/root-release.portable.json').read_text())
    review = FAMILY / gate['independent_code_review']['local_path']
    assert engine.sha(review) == gate['independent_code_review']['sha256']
    private = destination / 'private'; private.mkdir()
    shutil.copyfile(review, private / 'independent-code-review.safe.json')
    gate['independent_code_review']['local_path'] = str(private / 'independent-code-review.safe.json')
    engine.dump(private / 'root-release.json', gate)
    shutil.copyfile(input_path, private / 'input.csv')
    env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
    subprocess.run([sys.executable, str(family_copy / 'scripts/run_replay.py'), '--input', str(private / 'input.csv'),
                    '--output', str(private / 'results'), '--root-gate', str(private / 'root-release.json')], env=env, check=True)
    expected_path = FAMILY / 'artifacts/20261003-catalog-v1/private-output-manifest.json'
    expected = json.loads(expected_path.read_text())
    actual_manifest = private / 'results/manifest.json'
    assert actual_manifest.read_bytes() == expected_path.read_bytes(), 'Actual manifest differs from independently retained expected manifest'
    assert {p.name for p in (private / 'results').iterdir()} == {x['path'] for x in expected} | {'manifest.json'}
    for item in expected:
        p = private / 'results' / item['path']
        assert p.stat().st_size == item['bytes'] and engine.sha(p) == item['sha256'], item['path']
    subprocess.run([sys.executable, str(family_copy / 'scripts/verify_replay.py'), '--input', str(private / 'input.csv'),
                    '--results', str(private / 'results'), '--output', str(private / 'account-validation.json')], env=env, check=True)
    report = dict(status='PASS', payloads=len(expected), compared_files=len(expected) + 1,
                  expected_manifest_sha256=engine.sha(expected_path), input_sha256=engine.sha(private / 'input.csv'),
                  strategy_research_configurations_added=0, new_controls=0, network_requests=0,
                  scope='Frozen core recovery only; remote origin must be independently established by caller; not full private Library backup')
    engine.dump(receipt_path, report)
    return report

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for arg in ['input', 'fresh', 'receipt']: p.add_argument('--' + arg, type=Path, required=True)
    a = p.parse_args(); print(json.dumps(restore(a.input, a.fresh, a.receipt)))
