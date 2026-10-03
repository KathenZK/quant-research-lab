"""Independent Fraction features and pinned independent Decimal account oracle."""
if not __debug__:
    raise RuntimeError('M3710 rejects Python -O')
import argparse
import csv
import json
from pathlib import Path
from dependencies import FAMILY, adapter, account_verifier, engine
from gates import protocol, check_gate, disk_reserve
from oracle import verify_features


def read_csv(path):
    with path.open(newline='') as f:return list(csv.DictReader(f))


def position(index,namespace='eval'):
    c=index+(100 if namespace=='eval' else 0)
    return dict(canonical_index=c,view_index=c-69 if c>=69 else None,eval_index=c-100 if c>=100 else None)


def intent_mapping(signal,due,lag):
    assert 0<=signal<731 and due==signal+lag
    return dict(signal=position(signal),due_eval_ordinal=due,due_view_ordinal=due+31,
                due_canonical_ordinal=due+100,due_in_window=due<731)


def verify_view(iv,out,spec):
    actual=read_csv(out/'features-full.csv')
    expected=verify_features(iv.full_rows,actual)
    assert read_csv(out/'features-view.csv')==actual[69:]
    assert (out/'accounting-input.csv').read_bytes()==iv.view_bytes
    saved=json.loads((out/'index-map.json').read_text())
    assert saved==dict(profile='warmup100',canonical_rows=831,warmup=100,offset=69,
        kernel_input_index_namespace='view',signal_due_trip_namespace='eval',
        rows=[position(i,'canonical') for i in range(831)])
    account=account_verifier().verify_account(iv.view_rows,out,spec,expected[69:])
    for case in spec['cases']:
        name=case['name'];lag=case['delay_bars']
        fills=read_csv(out/f'{name}-fills.csv');events=read_csv(out/f'{name}-pending.csv')
        trips=read_csv(out/f'{name}-roundtrips.csv')
        summary=json.loads((out/f'{name}-summary.json').read_text())
        want=dict(fills=[dict(fill_id=int(x['fill_id']),at=position(int(x['eval_index'])),
            intent=intent_mapping(int(x['signal_index']),int(x['due_index']),lag)) for x in fills],
            events=[dict(event_id=int(x['event_id']),at=position(int(x['eval_index'])),
            intent=intent_mapping(int(x['signal_index']),int(x['due_index']),lag)) for x in events],
            trips=[dict(entry=position(int(x['entry_index'])),exit=position(int(x['exit_index'])),
            holding_bars=int(x['exit_index'])-int(x['entry_index'])) for x in trips],
            terminal=None if summary['terminal_pending'] is None else intent_mapping(
                summary['terminal_pending']['signal_index'],summary['terminal_pending']['due_index'],lag))
        assert json.loads((out/f'{name}-index-map.json').read_text())==want
    manifest=json.loads((out/'manifest.json').read_text())
    assert len(manifest)==37 and {p.name for p in out.iterdir()}=={x['path'] for x in manifest}|{'manifest.json'}
    for x in manifest:
        assert (out/x['path']).stat().st_size==x['bytes'] and engine().sha(out/x['path'])==x['sha256']
    top=json.loads((out/'summary.json').read_text())
    assert top['id']=='M3710' and top['full_feature_rows']==831 and top['accounting_rows']==762
    assert top['trusted'] is False and top['OOS'] is False and top['evaluation_rows']==731
    account.update(id='M3710',canonical_features=831,view_features=762,independent_index_mapping='PASS',
        full_feature_oracle='Fraction with independent50-digit half-even per-operation rounding; exact numeric equality, no epsilon',
        account_comparison='Pinned independent Decimal50 verifier exact serialized all financial fields; stronger than zero-tolerance numerical equality on these accepted records',
        new_historical_engine_runs=0)
    return account


def verify(input_path,out,gate_path,receipt_path):
    disk_reserve(receipt_path)
    check_gate(gate_path)
    e=engine();e.environment(FAMILY/'specs/environment-lock.json')
    iv=adapter().load_input(input_path.read_bytes(),'warmup100')
    return verify_view(iv,out,protocol())

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ['input','results','root-gate','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();receipt=verify(a.input,a.results,a.root_gate,a.output);engine().dump(a.output,receipt)
    print(json.dumps(receipt))
