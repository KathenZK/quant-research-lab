"""Four catalog-hypothesis cases; hard root-control gate before historical features."""
import argparse,json
from pathlib import Path
from kernel_loader import FAMILY,load
from signals import features
engine=load('engine')

def check_gate(gate_path):
    gate=json.loads(gate_path.read_text());spec=json.loads((FAMILY/'specs/protocol-v1.json').read_text())
    assert gate['status']=='ROOT_APPROVED_HISTORY_AFTER_INDEPENDENT_QA'
    assert gate['id']==spec['id'] and gate['C0_sha256']==engine.sha(FAMILY/'specs/C0-v1.json')
    c0=json.loads((FAMILY/'specs/C0-v1.json').read_text())
    for item in c0['files']:
        p=FAMILY/item['path'];assert p.stat().st_size==item['bytes'] and engine.sha(p)==item['sha256'],item['path']
    assert gate['control_independently_accepted'] is True
    control=gate['control'];assert len(control['remote_commit'])==40
    assert control['identity']==dict(id='M1258',case='buyhold',input_sha256=spec['input']['sha256'],initial_cash='100000',fraction='1',entry_fee_inclusive=True,fee_bps=8,slippage_bps=2,evaluation_start_ms=spec['evaluation_start_ms'],evaluation_end_ms=spec['evaluation_end_ms'],observations=731,Decimal_precision=50)
    for item in control['files']:
        p=Path(item['local_path']);assert p.stat().st_size==item['bytes'] and engine.sha(p)==item['sha256']
    assert len(control['files'])>=2
    return gate

def run(input_path,out,gate_path):
    engine.environment(FAMILY/'specs/environment-lock.json');gate=check_gate(gate_path)
    protocol=json.loads((FAMILY/'specs/protocol-v1.json').read_text());rows=engine.load_input(input_path,protocol)
    assert not out.exists();out.mkdir(parents=True)
    feat=features(rows);engine.csvout(out/'features.csv',feat,list(feat[0]));summaries=[]
    for case in protocol['cases']:
        result=engine.simulate(rows,feat,case);summaries.append(result['summary'])
        for name,columns in [('nav',engine.NAV),('fills',engine.FILL),('pending',engine.EVENT),('decisions',engine.DEC),('monthly',engine.MONTH),('roundtrips',engine.TRIP)]:engine.csvout(out/f"{case['name']}-{name}.csv",result[name],columns)
        engine.dump(out/f"{case['name']}-summary.json",result['summary'])
    engine.dump(out/'summary.json',dict(id=protocol['id'],classification='HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED',execution_class='ADAPTED_EXECUTION_PROXY',strict_reproductions=0,strategy_configurations=4,new_controls=0,native_nav_equals_daily_nav='*-nav.csv;1d no aggregation',cases=summaries,control_remote_commit=gate['control']['remote_commit']))
    manifest=[dict(path=p.name,bytes=p.stat().st_size,sha256=engine.sha(p)) for p in sorted(out.iterdir())]
    engine.dump(out/'manifest.json',manifest)
    return dict(status='COMPLETE',payloads=len(manifest),strategy_configurations=4,new_controls=0)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--root-gate',type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.input,a.output,a.root_gate)))
