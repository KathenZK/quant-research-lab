"""Real adapter/wrapper with artificial OHLCV only; optional real byte/schema QA."""
import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from kernel_loader import FAMILY, load
from signals import features
from oracle import verify_features
import run_replay as runner


def check(out, real_input=None):
    a = runner.adapter()
    engine = load('engine')
    p = a.PROFILES['warmup100']
    rows = []
    for i in range(831):
        t = a.EVAL_START+(i-100)*a.DAY
        price = str(100+(i*7)%19)
        rows.append(dict(zip(a.COLS, [str(t), price, price, price, price, '100',
                    str(t+a.DAY-1), '10000', '5', '20', '2000', '0'])))
    body = a._serialize(rows)
    view = a._serialize(rows[69:])
    synthetic_profile = replace(p, size=len(body), sha256=hashlib.sha256(body).hexdigest(),
                                view_size=len(view), view_sha256=hashlib.sha256(view).hexdigest())
    iv = a._validate_input(body, synthetic_profile)
    f = features(iv.full_rows)
    expected = verify_features(iv.full_rows, f)
    fv = a.align_features(iv, f, required_ready_fields=('ema20',))
    assert [dict(x) for x in fv.view_features] == f[69:]
    assert fv.view_features[31]['canonical_feature_index'] == 100
    assert features(iv.view_rows)[31]['ema20'] != f[100]['ema20']  # reseeding is not equivalent
    for i in range(831):
        m = a.map_index('warmup100', i, namespace='canonical')
        assert m == dict(canonical_index=i, view_index=i-69 if i>=69 else None, eval_index=i-100 if i>=100 else None)
    rejected = 0
    def reject(call):
        nonlocal rejected
        try:
            call()
        except (ValueError, AssertionError, TypeError):
            rejected += 1
        else:
            raise AssertionError('invalid integration input accepted')
    for key, value in [('canonical_feature_index', 99), ('open_time', True), ('close_time', 0),
                       ('close', '0'), ('ready', False), ('raw_entry', True), ('ema20', 'NaN')]:
        changed = [dict(x) for x in f]
        changed[100][key] = value
        reject(lambda changed=changed: a.align_features(iv, changed, required_ready_fields=('ema20',)))
    reject(lambda: a.align_features(iv, f[69:], required_ready_fields=('ema20',)))
    for profile in ['warmup100', 'warmup735', 'invalid', True]:
        reject(lambda profile=profile: a.load_input(body, profile))
    out.mkdir(parents=True)
    source = out/'artificial.csv'
    source.write_bytes(body)
    # Only bypass identity/root authorization for labelled artificial fixture; actual adapter alignment and runner account/serializer are exercised.
    with patch.object(runner, 'check_gate', return_value={'SYNTHETIC_NOT_AUTHORIZATION': True}), patch.object(runner, 'adapter', return_value=a), patch.object(a, 'load_input', return_value=iv):
        result = runner.run(source, out/'results', out/'NOT_A_REAL_GATE')
    spec = json.loads((FAMILY/'specs/protocol-v1.json').read_text())
    qa = load('verify_account').verify_account(iv.view_rows, out/'results', spec, expected[69:])
    assert (out/'results/accounting-view.csv').read_bytes() == view
    real = None
    if real_input is not None:
        raw = real_input.read_bytes()
        ri = a.load_input(raw, 'warmup100')  # NO features or account for market data.
        assert len(ri.full_rows)==831 and len(ri.view_rows)==762
        real = dict(status='PASS', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                    view_sha256=hashlib.sha256(ri.view_bytes).hexdigest(), real_features=0)
        reject(lambda: a.load_input(raw+b' ', 'warmup100'))
        reject(lambda: a.load_input(raw, 'warmup735'))
    return dict(status='PASS', synthetic_wrapper=result, independent_account=qa, rejected=rejected,
                mapping_rows=831, full_features=831, real_input_schema_only=real,
                historical_features=0, historical_runs=0, new_controls=0)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--real-input-schema-only',type=Path)
    args=parser.parse_args()
    r=check(args.output,args.real_input_schema_only)
    load('engine').dump(args.output/'receipt.json',r)
    print(json.dumps(r))
