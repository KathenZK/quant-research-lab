"""Post-release offline fresh-directory byte recovery; no new research or controls."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from kernel_loader import FAMILY, ROOT, load

engine = load('engine')

def restore(input_path, gate_path, reference, destination):
    from run_replay import check_gate
    gate = check_gate(gate_path)
    assert not destination.exists()
    destination.mkdir(parents=True)
    copy = destination / FAMILY.relative_to(ROOT)
    c0 = json.loads((FAMILY / 'specs/C0-v1.json').read_text())
    for rel in [x['path'] for x in c0['files']] + ['specs/C0-v1.json']:
        dst = copy / rel; dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((FAMILY / rel).read_bytes())
    pin = json.loads((FAMILY / 'specs/kernel-pin.json').read_text())
    for rel in pin['files']:
        dst = destination / pin['root'] / rel; dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((ROOT / pin['root'] / rel).read_bytes())
    private = destination / 'private'; private.mkdir()
    shutil.copyfile(input_path, private / 'input.csv')
    receipt = gate['independent_code_review']
    shutil.copyfile(receipt['local_path'], private / 'independent-code-review.json')
    gate['independent_code_review']['local_path'] = str(private / 'independent-code-review.json')
    engine.dump(private / 'root-gate.json', gate)
    env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
    subprocess.run([sys.executable, str(copy / 'scripts/run_replay.py'), '--input', str(private / 'input.csv'),
                    '--output', str(private / 'results'), '--root-gate', str(private / 'root-gate.json')], env=env, check=True, capture_output=True, text=True)
    subprocess.run([sys.executable, str(copy / 'scripts/verify_replay.py'), '--input', str(private / 'input.csv'),
                    '--results', str(private / 'results'), '--output', str(private / 'validation.json')], env=env, check=True, capture_output=True, text=True)
    names = [x['path'] for x in json.loads((reference / 'manifest.json').read_text())] + ['manifest.json']
    assert set(names) == {x.name for x in (private / 'results').iterdir()}
    for name in names:
        assert (private / 'results' / name).read_bytes() == (reference / name).read_bytes(), name
    report = dict(status='PASS', compared_files=len(names), new_research_configurations=0, new_controls=0,
                  scope='Local fresh source/input byte recovery; separately report remote/Library status')
    engine.dump(destination / 'restoration-receipt.json', report)
    return report

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for arg in ['input', 'root-gate', 'results', 'destination']: p.add_argument('--' + arg, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(restore(a.input, a.root_gate, a.results, a.destination)))
