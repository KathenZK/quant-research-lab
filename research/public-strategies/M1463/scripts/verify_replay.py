"""Family independent features, pinned independent account verifier; never replay."""
import argparse,json,hashlib
from pathlib import Path
from kernel_loader import FAMILY,load
from oracle import verify_features
qa=load('verify_account')
def verify(input_path,out):
    spec=json.loads((FAMILY/'specs/protocol-v1.json').read_text())
    assert hashlib.sha256(input_path.read_bytes()).hexdigest()==spec['input']['sha256']
    rows=qa.read(input_path);actual=qa.read(out/'features.csv');expected=verify_features(rows,actual)
    return qa.verify_account(rows,out,spec,expected)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=verify(a.input,a.results)
    with a.output.open('x') as h:json.dump(r,h,indent=2);h.write('\n')
    print(json.dumps(r))
