"""Artificial-only prefix/future account checks; never accepts market input."""
import argparse
import json
from pathlib import Path
from check_synthetic import bars
from kernel_loader import FAMILY, load
from signals import features


def check():
    engine = load('engine')
    spec = json.loads((FAMILY / 'specs/protocol-v1.json').read_text())
    rows = bars([str(100 + (i * 7) % 19) for i in range(180)])
    counts = 0
    for case in spec['cases']:
        full = engine.simulate(rows, features(rows), case, start=100)
        for cut in [101, 102, 105, 121, 149, 179]:
            prefix = engine.simulate(rows[:cut], features(rows[:cut]), case, start=100)
            changed = [dict(row) for row in rows]
            for row in changed[cut:]:
                for key in ['open', 'high', 'low', 'close']:
                    row[key] = '1000000'
            future = engine.simulate(changed, features(changed), case, start=100)
            for field in ['nav', 'decisions']:
                assert prefix[field] == full[field][:cut - 100] == future[field][:cut - 100]
            for field in ['fills', 'pending']:
                target = [x for x in full[field] if x['eval_index'] < cut - 100]
                assert prefix[field] == target == [x for x in future[field] if x['eval_index'] < cut - 100]
            counts += 1
    return dict(status='PASS', synthetic_only=True, account_prefix_future_pairs=counts,
                historical_features=0, historical_runs=0, new_controls=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = check()
    load('engine').dump(args.output, result)
    print(json.dumps(result))
