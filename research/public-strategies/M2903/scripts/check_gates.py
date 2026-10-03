"""Synthetic gate probes only: temporary text files, no market input or account."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import gates
import run_replay


def check():
    passed = []
    def reject(name, call):
        try:
            call()
        except (ValueError, RuntimeError, AssertionError, FileNotFoundError):
            passed.append(name)
        else:
            raise AssertionError('accepted: ' + name)
    with tempfile.TemporaryDirectory(prefix='m2903-gates-') as tmp:
        base = Path(tmp)
        (base / 'file').write_bytes(b'x')
        item = dict(path='file', bytes=1, sha256=hashlib.sha256(b'x').hexdigest())
        gates.verify_files(base, [item], {'file'})
        passed.append('valid exact fixture pin')
        for name in ['/tmp/file', '../file', './file', 'x/../file', 'x//file', 'x\\file', '']:
            reject('relative path ' + repr(name), lambda name=name: gates.relative_file(base, name))
        (base / 'link').symlink_to(base / 'file')
        reject('symlink', lambda: gates.relative_file(base, 'link'))
        for label, items in [('missing', []), ('duplicate', [item, item]),
                             ('unexpected', [dict(item, path='other')]),
                             ('boolean size', [dict(item, bytes=True)]),
                             ('wrong hash', [dict(item, sha256='0'*64)]),
                             ('wrong size', [dict(item, bytes=2)])]:
            reject(label, lambda items=items: gates.verify_files(base, items, {'file'}))
        # Duplicate despite correct length must also fail.
        reject('duplicate correctcount', lambda: gates.verify_files(base, [item, item], {'file', 'other'}))
        (base / 'duplicate.json').write_text('{"files":[],"files":[]}')
        reject('duplicate JSON keys', lambda: gates.read_json(base / 'duplicate.json'))
        gates.release_counts(dict(authorized_strategy_configurations=4, new_controls=0))
        for a, b in [(True, 0), (4.0, 0), ('4', 0), (4, False), (4, 0.0), (4, '0'), (3, 0), (4, 1)]:
            reject('counts ' + repr((a, b)), lambda a=a, b=b: gates.release_counts(dict(authorized_strategy_configurations=a, new_controls=b)))
        output = base / 'not-created'
        needed = gates.RESERVE_BYTES + gates.OUTPUT_BUDGET_BYTES
        with patch.object(gates.shutil, 'disk_usage', return_value=SimpleNamespace(free=needed)):
            assert gates.disk_budget(output) == needed
            passed.append('exact reserve plus budget accepted')
        with patch.object(gates.shutil, 'disk_usage', return_value=SimpleNamespace(free=needed-1)):
            reject('one byte below combined budget', lambda: gates.disk_budget(output))
            with patch.object(run_replay, 'load', side_effect=AssertionError('ENGINE SHOULD NOT LOAD')) as loader:
                reject('run lowdisk before engine or input', lambda: run_replay.run(base/'NO_INPUT', output, base/'NO_GATE'))
                loader.assert_not_called()
                assert not output.exists()
        reject('existing output', lambda: gates.disk_budget(base/'file'))
        # Normal invocation cannot progress without real frozen C0; nonexistent input is not read.
        with patch.object(run_replay, 'adapter', side_effect=AssertionError('ADAPTER SHOULD NOT LOAD')) as adapter:
            reject('missing C0 before adapter/input', lambda: run_replay.check_gate(base/'NO_GATE'))
            adapter.assert_not_called()
        proc = subprocess.run([sys.executable, '-O', str(Path(run_replay.__file__)), '--input', str(base/'NO_INPUT'),
                               '--output', str(output), '--root-gate', str(base/'NO_GATE')], capture_output=True, text=True)
        assert proc.returncode != 0 and 'Python -O is prohibited' in proc.stderr
        assert 'FileNotFoundError' not in proc.stderr and not output.exists()
        passed.append('actual Python -O subprocess rejects before missing gates/input')
    return dict(status='PASS', synthetic_only=True, checks=len(passed), checks_passed=passed,
                historical_features=0, historical_runs=0, new_controls=0,
                limitations='Adapter/input/runtime negative integration awaits exact reviewed adapter; no claim of final C0 acceptance.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = check()
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps(result))
