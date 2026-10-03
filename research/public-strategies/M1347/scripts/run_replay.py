"""Four cases only. Actual input/feature replay requires independently reviewed root release."""
import argparse
import json
from pathlib import Path
from kernel_loader import FAMILY, load
from signals import features

engine = load('engine')

def verify_c0():
    c0 = json.loads((FAMILY / 'specs/C0-v1.json').read_text())
    for item in c0['files']:
        p = FAMILY / item['path']
        assert p.stat().st_size == item['bytes'] and engine.sha(p) == item['sha256'], item['path']
    return c0

def check_gate(gate_path):
    gate = json.loads(Path(gate_path).read_text())
    verify_c0()
    assert gate['status'] == 'ROOT_APPROVED_HISTORY_AFTER_INDEPENDENT_QA'
    assert gate['id'] == 'M1347' and gate['C0_sha256'] == engine.sha(FAMILY / 'specs/C0-v1.json')
    assert gate['authorized_strategy_configurations'] == 4 and gate['new_controls'] == 0
    assert gate['control_independently_accepted'] is True
    assert gate['control_reference_sha256'] == engine.sha(FAMILY / 'specs/control-reference.json')
    assert gate['control_remote_acceptance_sha256'] == engine.sha(FAMILY / 'specs/control-remote-acceptance.safe.json')
    receipt = gate['independent_code_review']
    assert engine.sha(receipt['local_path']) == receipt['sha256']
    assert receipt['status'] == 'PASS' and len(gate['source_commit']) == 40
    return gate

def write_results(rows, out, protocol, control_remote_commit):
    """Shared serializer for authorized replay and clearly labelled artificial-only QA."""
    assert not out.exists()
    out.mkdir(parents=True)
    feat = features(rows)
    engine.csvout(out / 'features.csv', feat, list(feat[0]))
    summaries = []
    for case in protocol['cases']:
        result = engine.simulate(rows, feat, case)
        summaries.append(result['summary'])
        for name, columns in [('nav', engine.NAV), ('fills', engine.FILL), ('pending', engine.EVENT),
                              ('decisions', engine.DEC), ('monthly', engine.MONTH), ('roundtrips', engine.TRIP)]:
            engine.csvout(out / f"{case['name']}-{name}.csv", result[name], columns)
        engine.dump(out / f"{case['name']}-summary.json", result['summary'])
    engine.dump(out / 'summary.json', dict(id='M1347', classification='HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED',
        execution_class='ADAPTED_EXECUTION_PROXY', strict_reproductions=0, strategy_configurations=4,
        new_controls=0, native_nav_equals_daily_nav='*-nav.csv;1d no aggregation', cases=summaries,
        control_remote_commit=control_remote_commit))
    manifest = [dict(path=p.name, bytes=p.stat().st_size, sha256=engine.sha(p)) for p in sorted(out.iterdir())]
    engine.dump(out / 'manifest.json', manifest)
    return dict(status='COMPLETE', payloads=len(manifest), strategy_configurations=4, new_controls=0)

def run(input_path, out, gate_path):
    engine.environment(FAMILY / 'specs/environment-lock.json')
    check_gate(gate_path)
    protocol = json.loads((FAMILY / 'specs/protocol-v1.json').read_text())
    rows = engine.load_input(input_path, protocol)
    return write_results(rows, out, protocol, protocol['benchmark']['original_remote_core_commit'])

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--root-gate', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(run(a.input, a.output, a.root_gate)))
