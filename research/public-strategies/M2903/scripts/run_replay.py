"""Four frozen cases only; exact C0/root release before historical input or features."""
import sys

if not __debug__:
    raise RuntimeError('Python -O is prohibited before loading gates or inputs')

import argparse
import importlib.util
import json
from pathlib import Path
from kernel_loader import FAMILY, ROOT, load
from signals import features
from gates import C0_REQUIRED, read_json, verify_files, release_counts, disk_budget, hex_digest, review_file


def adapter():
    engine = load('engine')
    pin = read_json(FAMILY / 'specs/adapter-pin.json')
    assert pin['status'] == 'INDEPENDENTLY_VERIFIED_REMOTE_PINNED'
    assert pin['root'] == 'research/_shared-kernels/catalog-daily-input-view'
    base = ROOT / pin['root']
    hex_digest(pin['remote_commit'], 40)
    assert pin['remote_commit'] == '43becf3c521eeb884dfc239883ee5cb5106d3646'
    assert pin['independent_review']['path'] == 'reviews/v1-independent-20261003.json'
    assert engine.sha(base / pin['independent_review']['path']) == hex_digest(pin['independent_review']['sha256'], 64)
    verify_files(base, [dict(path=k, **v) for k, v in pin['files'].items()],
                 {'v1/adapter.py', 'v1/manifest.json'})
    spec = importlib.util.spec_from_file_location('m2903_input_view', base / 'v1/adapter.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_gate(path):
    engine = load('engine')
    c0path = FAMILY / 'specs/C0-v1.json'
    c0 = read_json(c0path)
    assert c0['status'] == 'FROZEN_PREHISTORY_C0' and c0['id'] == 'M2903'
    verify_files(FAMILY, c0['files'], C0_REQUIRED)
    gate = read_json(path)
    assert gate['status'] == 'ROOT_APPROVED_HISTORY_AFTER_INDEPENDENT_QA'
    assert gate['id'] == 'M2903'
    assert hex_digest(gate['C0_sha256'], 64) == engine.sha(c0path)
    release_counts(gate)
    assert gate['control_independently_accepted'] is True
    for key, name in [('control_reference_sha256', 'control-reference.json'),
                      ('control_remote_acceptance_sha256', 'control-remote-acceptance.safe.json')]:
        assert hex_digest(gate[key], 64) == engine.sha(FAMILY / 'specs' / name)
    receipt = gate['independent_code_review']
    assert type(receipt) is dict and receipt['status'] == 'PASS'
    assert engine.sha(review_file(receipt['local_path'])) == hex_digest(receipt['sha256'], 64)
    hex_digest(gate['source_commit'], 40)
    return gate


def run(input_path, out, gate_path):
    disk_budget(out)  # Before gates, input reads, feature calculations or mkdir.
    engine = load('engine')
    engine.environment(FAMILY / 'specs/environment-lock.json')
    check_gate(gate_path)
    view_adapter = adapter()
    protocol = json.loads((FAMILY / 'specs/protocol-v1.json').read_text())
    assert not out.exists()
    iv = view_adapter.load_input(Path(input_path).read_bytes(), 'warmup100')
    full_features = features(iv.full_rows)
    fv = view_adapter.align_features(iv, full_features, required_ready_fields=('ema20',))
    disk_budget(out)  # Recheck after validation/calculation, before first output write.
    out.mkdir(parents=True)
    (out / 'accounting-view.csv').write_bytes(iv.view_bytes)
    engine.csvout(out / 'canonical-features.csv', full_features, list(full_features[0]))
    mapping = [view_adapter.map_index('warmup100', i, namespace='canonical') for i in range(len(iv.full_rows))]
    engine.csvout(out / 'index-mapping.csv', mapping, list(mapping[0]))
    summaries = []
    for case in protocol['cases']:
        result = engine.simulate(iv.view_rows, fv.view_features, case, start=31)
        summaries.append(result['summary'])
        for name, columns in [('nav', engine.NAV), ('fills', engine.FILL), ('pending', engine.EVENT),
                              ('decisions', engine.DEC), ('monthly', engine.MONTH), ('roundtrips', engine.TRIP)]:
            engine.csvout(out / f"{case['name']}-{name}.csv", result[name], columns)
        engine.dump(out / f"{case['name']}-summary.json", result['summary'])
    engine.dump(out / 'summary.json', dict(id='M2903', cases=summaries,
        classification='HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED', execution_class='ADAPTED_EXECUTION_PROXY',
        strict_reproductions=0, strategy_configurations=4, new_controls=0,
        control_reference_sha256=engine.sha(FAMILY / 'specs/control-reference.json'),
        full_input_sha256=protocol['input']['sha256'], accounting_view_sha256=protocol['input_adapter']['view_sha256'],
        kernel_input_index_namespace='accounting_view', signal_due_trip_index_namespace='evaluation',
        canonical_feature_index_namespace='full831', canonical_offset=69))
    engine.dump(out / 'manifest.json', [dict(path=p.name, bytes=p.stat().st_size, sha256=engine.sha(p)) for p in sorted(out.iterdir())])
    return dict(status='COMPLETE', strategy_configurations=4, new_controls=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--root-gate', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.input, args.output, args.root_gate)))
