"""Four strategy cases; root-gated historical CLI, no benchmark runner."""
if not __debug__:
    raise RuntimeError('M3710 rejects Python -O before gates/input/engine')
import argparse
import json
from pathlib import Path
from dependencies import FAMILY, adapter, engine
from gates import protocol, check_gate, disk_reserve
from signals import features, COLUMNS


def write_results(input_view, out, spec, *, synthetic_only=False):
    """InputView came from the pinned adapter. Full features precede any projection."""
    disk_reserve(out)
    a = adapter()
    e = engine()
    assert type(input_view) is a.InputView and not out.exists()
    assert input_view.profile.name == 'warmup100'
    aligned = a.align_features(input_view, features(input_view.full_rows), required_ready_fields=('sma20',))
    assert len(aligned.full_features)==831 and len(aligned.view_features)==762
    out.mkdir(parents=True)
    e.csvout(out/'features-full.csv', [dict(x) for x in aligned.full_features], COLUMNS)
    e.csvout(out/'features-view.csv', [dict(x) for x in aligned.view_features], COLUMNS)
    with (out/'accounting-input.csv').open('xb') as h:h.write(input_view.view_bytes)
    e.dump(out/'index-map.json', dict(profile='warmup100', canonical_rows=831, warmup=100, offset=69,
        kernel_input_index_namespace='view', signal_due_trip_namespace='eval',
        rows=[a.map_index('warmup100',i,'canonical') for i in range(831)]))
    summaries=[]
    for case in spec['cases']:
        result=e.simulate(input_view.view_rows,aligned.view_features,case)
        summaries.append(result['summary'])
        for name,cols in [('nav',e.NAV),('fills',e.FILL),('pending',e.EVENT),('decisions',e.DEC),('monthly',e.MONTH),('roundtrips',e.TRIP)]:
            e.csvout(out/f"{case['name']}-{name}.csv",result[name],cols)
        e.dump(out/f"{case['name']}-summary.json",result['summary'])
        mapping=dict(fills=[dict(fill_id=x['fill_id'],at=a.map_index('warmup100',x['eval_index'],'eval'),
            intent=a.map_pending('warmup100',x['signal_index'],x['due_index'],case['delay_bars'])) for x in result['fills']],
            events=[dict(event_id=x['event_id'],at=a.map_index('warmup100',x['eval_index'],'eval'),
            intent=a.map_pending('warmup100',x['signal_index'],x['due_index'],case['delay_bars'])) for x in result['pending']],
            trips=[a.map_roundtrip('warmup100',x['entry_index'],x['exit_index']) for x in result['roundtrips']],
            terminal=None if result['summary']['terminal_pending'] is None else
                a.map_pending('warmup100',result['summary']['terminal_pending']['signal_index'],
                    result['summary']['terminal_pending']['due_index'],case['delay_bars']))
        e.dump(out/f"{case['name']}-index-map.json",mapping)
    e.dump(out/'summary.json',dict(id='M3710',classification='HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED',
        execution_class='ADAPTED_EXECUTION_PROXY',strict_reproductions=0,trusted=False,OOS=False,
        strategy_configurations=4,new_controls=0,synthetic_only=synthetic_only,cases=summaries,
        full_feature_rows=831,accounting_rows=762,evaluation_rows=731,
        control_remote_commit=spec['benchmark']['original_remote_core_commit']))
    manifest=[dict(path=p.name,bytes=p.stat().st_size,sha256=e.sha(p)) for p in sorted(out.iterdir())]
    e.dump(out/'manifest.json',manifest)
    return dict(status='COMPLETE',payloads=len(manifest),strategy_configurations=4,new_controls=0,synthetic_only=synthetic_only)


def run(input_path,out,gate_path):
    disk_reserve(out)
    check_gate(gate_path)  # before engine import and before reading historical input
    e=engine();e.environment(FAMILY/'specs/environment-lock.json')
    iv=adapter().load_input(input_path.read_bytes(),'warmup100')
    return write_results(iv,out,protocol())

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ['input','output','root-gate']:p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();print(json.dumps(run(args.input,args.output,args.root_gate)))
