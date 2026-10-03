"""Root-gated historical feature causality only; never rerun an account."""
if not __debug__:
    raise RuntimeError('M3710 rejects Python -O')
import argparse
from pathlib import Path
from dependencies import FAMILY, adapter, engine
from gates import check_gate, disk_reserve
from signals import features
from oracle import verify_features


def check(input_path,gate_path,receipt_path):
    disk_reserve(receipt_path)
    check_gate(gate_path)
    engine().environment(FAMILY/'specs/environment-lock.json')
    iv=adapter().load_input(input_path.read_bytes(),'warmup100')
    rows=[dict(x) for x in iv.full_rows];full=features(rows);verify_features(rows,full)
    cuts=[1,18,19,20,21,68,69,70,99,100,101,102,400,729,830,831]
    for cut in cuts:
        assert features(rows[:cut])==full[:cut]
        changed=[dict(x) for x in rows]
        for r in changed[cut:]:r['close']='999999.999'
        assert features(changed)[:cut]==full[:cut]
    return dict(id='M3710',status='PASS',prefix_cases=len(cuts),future_cases=len(cuts),
        full_canonical_features_preserved=True,account_reruns=0,new_controls=0,
        limitation='Feature causality; execution chronology is checked separately by independent account verification.')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ['input','root-gate','output']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();receipt=check(a.input,a.root_gate,a.output);engine().dump(a.output,receipt)
