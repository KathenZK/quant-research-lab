"""Actual check_gate against artificial C0 pins; never an execution release."""
import argparse
import copy
import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import gates
import run_replay as runner


def check():
    observed = []
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='m2903-metadata-') as tmp:
        base = Path(tmp)
        items = []
        for name in sorted(gates.C0_REQUIRED):
            path = base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'ARTIFICIAL PIN FIXTURE NOT AUTHORIZATION\n')
            items.append(dict(path=name, bytes=path.stat().st_size, sha256=sha(path)))
        c0 = base / 'specs/C0-v1.json'
        c0.write_text(json.dumps(dict(id='M2903', status='FROZEN_PREHISTORY_C0', files=items)))
        review = base / 'review.txt'
        review.write_text('ARTIFICIAL REVIEW NOT AN ACCEPTANCE\n')
        gate = dict(id='M2903', status='ROOT_APPROVED_HISTORY_AFTER_INDEPENDENT_QA',
                    C0_sha256=sha(c0), authorized_strategy_configurations=4, new_controls=0,
                    control_independently_accepted=True,
                    control_reference_sha256=sha(base/'specs/control-reference.json'),
                    control_remote_acceptance_sha256=sha(base/'specs/control-remote-acceptance.safe.json'),
                    independent_code_review=dict(status='PASS', local_path=str(review), sha256=sha(review)),
                    source_commit='9d2836c0385aa35353016629b66ecc2a1595ad94')
        def probe(label, data, accepted=False):
            file = base / 'artificial-release.json'
            file.write_text(json.dumps(data))
            try:
                runner.check_gate(file)
                actual = True
            except (ValueError, AssertionError, TypeError, KeyError, FileNotFoundError):
                actual = False
            assert actual is accepted, label
            observed.append(dict(case=label, result='ACCEPTED_FIXTURE' if actual else 'REJECTED'))
        with patch.object(runner, 'FAMILY', base):
            probe('valid fixture only', gate, True)
            for value in [[0]*40, 'z'*40, 'A'*40, 'a'*39, 40, True, None]:
                changed = copy.deepcopy(gate)
                changed['source_commit'] = value
                probe('source_commit '+repr(value), changed)
            for key in ['C0_sha256', 'control_reference_sha256', 'control_remote_acceptance_sha256']:
                for value in [[0]*64, 'z'*64, 'A'*64, True]:
                    changed = copy.deepcopy(gate)
                    changed[key] = value
                    probe(key+' '+repr(value), changed)
            for key, values in [('sha256', [[0]*64, 'z'*64, True]),
                                ('local_path', [True, [], '../review.txt', str(base/'absent'), 'bad\x00path']),
                                ('status', [True, ['PASS']])]:
                for value in values:
                    changed = copy.deepcopy(gate)
                    changed['independent_code_review'][key] = value
                    probe('review '+key+' '+repr(value), changed)
    return dict(status='PASS', checks=len(observed), observations=observed,
                synthetic_only=True, historical_features=0, historical_runs=0,
                actual_function='run_replay.check_gate', authorization_issued=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = check()
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps(dict(status=result['status'], checks=result['checks'])))
