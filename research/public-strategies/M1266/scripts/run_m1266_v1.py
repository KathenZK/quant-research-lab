"""Historical M1266 entrypoint, unavailable until exact-C0 coordinator release.

No implicit execution, acquisitions, parameter search, network, or global writes.
Outputs always go to a new private directory. Replays use the same frozen gate.
"""
import argparse
import decimal
import _decimal
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import platform
import shutil
import sys

INPUT_SHA = 'a21612759ddd7e849f4a5e5b3ac62f74b003c84bf9e0e77d45ab8670b59eb550'
CONTRACT_SHA = 'f80970af5a90c335db55b507a8112ef2ec50c3c48d59a9d057f363120070260e'
RULES_SHA = 'bc553ebdd3aa2a0bc8d55a3b878ce2354e52b200bd69728915cf6bdb8b1b9491'

def sha(body):
    return hashlib.sha256(body).hexdigest()


def require(condition, message):
    if not condition:
        raise PermissionError(message)


def check_gate(root, c0_path, release_path):
    """Validate receipt first, before importing engine or parsing any prices.

    Explicit exceptions deliberately survive Python -O. Engine invariants use
    assert, therefore optimization is forbidden before any other gate read.
    """
    require(sys.flags.optimize == 0, 'PYTHON_OPTIMIZATION_FORBIDDEN')
    if not release_path.is_file():
        raise PermissionError('EXACT_C0_COORDINATOR_RELEASE_REQUIRED')
    cb = c0_path.read_bytes()
    c0 = json.loads(cb)
    release = json.loads(release_path.read_bytes())
    require(c0['status'] == 'FROZEN_BEFORE_HISTORICAL_FEATURES_AND_RETURNS', 'C0_STATUS')
    require(c0['historical_strategy_runs'] == c0['historical_new_control_runs'] == 0, 'C0_COUNTS')
    require(release['status'] == 'RELEASED_BY_COORDINATOR', 'RELEASE_STATUS')
    require(release['strategy_ids'] == ['M1266'], 'RELEASE_IDS')
    require(release['C0_sha256'] == sha(cb), 'RELEASE_C0_HASH')
    require(release['planned_strategy_configurations'] == 4, 'RELEASE_STRATEGY_COUNT')
    require(release['planned_new_controls'] == 1, 'RELEASE_CONTROL_COUNT')
    require(bool(release['coordinator_evidence']), 'RELEASE_COORDINATOR_EVIDENCE_REQUIRED')
    for pin in c0['pins']:
        path = root / pin['path']
        body = path.read_bytes()
        require(len(body) == pin['bytes'] and sha(body) == pin['sha256'], 'PIN_MISMATCH:' + pin['path'])
    runtime = json.loads((root / 'frozen/runtime-v1.json').read_bytes())
    require(sys.flags.optimize == runtime['optimize'] == 0, 'RUNTIME_OPTIMIZATION')
    require(decimal.__libmpdec_version__ == runtime['libmpdec_version'], 'LIBMPDEC_VERSION')
    require(sha(Path(decimal.__file__).read_bytes()) == runtime['decimal_module_sha256'], 'DECIMAL_MODULE_HASH')
    require(_decimal.__spec__.origin == runtime['decimal_c_extension_origin'], 'DECIMAL_EXTENSION_ORIGIN')
    require(sys.version == runtime['python_version'], 'PYTHON_VERSION')
    require(platform.python_implementation() == runtime['python_implementation'], 'PYTHON_IMPLEMENTATION')
    require(sha(Path(sys.executable).read_bytes()) == runtime['python_executable_sha256'], 'PYTHON_EXECUTABLE_HASH')
    require(shutil.disk_usage(root).free >= 5 * 1024**3, 'DISK_RESERVE')
    require(sha((root/'frozen/catalog-fixedqty-batch019-output-contract-20261003.json').read_bytes()) == CONTRACT_SHA, 'CONTRACT_HASH')
    require(sha((root/'frozen/M1266-root-frozen-rules.json').read_bytes()) == RULES_SHA, 'RULES_HASH')
    return c0


def load_input(path):
    body = path.read_bytes()
    require(len(body) == 139983 and sha(body) == INPUT_SHA, 'INPUT_BYTES_HASH')
    rows = list(csv.DictReader(io.StringIO(body.decode(), newline='')))
    require(len(rows) == 831, 'INPUT_ROWS')
    require([int(r['open_time']) for r in rows] == list(range(1663891200000, 1735689600000, 86400000)), 'INPUT_GRID')
    require(int(rows[100]['open_time']) == 1672531200000, 'EVALUATION_BOUNDARY')
    return rows


def produce(root, rows, output):
    spec = importlib.util.spec_from_file_location('m1266_pinned_engine', root/'scripts/m1266_engine_v1.py')
    engine = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = engine
    spec.loader.exec_module(engine)
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for case in engine.CASES:
        value = engine.run(rows, case)
        (output/(case.name+'.json')).write_bytes(engine.canonical_bytes(value))
        results.append(dict(case=case.name, metrics=value['metrics']))
    control = engine.run(rows, engine.CASES[0], control=True)
    (output/'buyhold-base.json').write_bytes(engine.canonical_bytes(control))
    (output/'summary.json').write_bytes(engine.canonical_bytes(dict(
        id='M1266', classification='ADAPTED_SOURCE_CORRECTED_VARIANT',
        execution_class='HYPOTHESIS_EXECUTION_PROXY', trusted=False,
        OOS=False, strict_reproductions=0, strategy_configurations=4,
        new_controls=1, cases=results, benchmark=control['metrics'],
        fee_control_limitation='Only base8fee2slip control; fee0/fee20/delay2 do not have independently matched controls.')))
    files=[dict(path=p.name, bytes=p.stat().st_size, sha256=sha(p.read_bytes()))
           for p in sorted(output.iterdir())]
    (output/'manifest.json').write_bytes(engine.canonical_bytes(files))
    return dict(strategy_configurations=4, new_controls=1, strict_reproductions=0)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--c0', type=Path, required=True)
    p.add_argument('--release', type=Path, required=True)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a=p.parse_args()
    root=a.bundle.resolve()
    check_gate(root,a.c0,a.release)
    rows=load_input(a.input)
    result=produce(root,rows,a.output)
    print(json.dumps(dict(status='COMPLETED',**result)))

if __name__=='__main__':
    main()
