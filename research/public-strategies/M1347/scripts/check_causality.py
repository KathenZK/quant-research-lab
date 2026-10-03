"""After release, verify feature prefixes and price independence; no account rerun."""
import argparse
import copy
import json
from pathlib import Path
from kernel_loader import FAMILY, load
from oracle import verify_features
from signals import features
from run_replay import check_gate

engine = load('engine')

def check(input_path, gate_path):
    engine.environment(FAMILY / 'specs/environment-lock.json')
    check_gate(gate_path)
    spec = json.loads((FAMILY / 'specs/protocol-v1.json').read_text())
    rows = engine.load_input(input_path, spec)
    full = features(rows)
    verify_features(rows, full)
    cuts = [31, 32, 34, 58, 59, 60, 61, 64, 86, 90, 91, 365, 397, 455, 759, 761]
    for cut in cuts:
        assert features(rows[:cut]) == full[:cut]
        mutated = copy.deepcopy(rows)
        for row in mutated[cut:]:
            for key in ['open', 'high', 'low', 'close']: row[key] = '100'
        after = features(mutated)
        assert after[:cut] == full[:cut]
        assert [(r['raw_entry'], r['raw_exit']) for r in after] == [(r['raw_entry'], r['raw_exit']) for r in full]
    return dict(status='PASS', prefix_cases=len(cuts), future_mutations=len(cuts),
                price_independent_calendar=True, account_engine_reruns=0, new_controls=0,
                limit='Feature causality only; synthetic suite and independent result audit cover account chronology')

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for arg in ['input', 'root-gate', 'output']: p.add_argument('--' + arg, type=Path, required=True)
    a = p.parse_args()
    r = check(a.input, a.root_gate)
    engine.dump(a.output, r)
    print(json.dumps(r))
