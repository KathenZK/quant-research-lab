"""Verify frozen own code and reproduce outputs in a new directory; no downloads."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
F=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--expected',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
    freeze=json.loads((F/'specs/C0-v1.json').read_text())
    for x in freeze['frozen_files']:
        assert hashlib.sha256((F/x['path']).read_bytes()).hexdigest()==x['sha256'],x['path']
    subprocess.run([sys.executable,str(F/'scripts/run_replay.py'),'--input',str(a.input),'--output',str(a.output)],check=True)
    expected=json.loads((a.expected/'RESULT-MANIFEST.json').read_text())
    for x in expected:
        b=(a.output/x['path']).read_bytes();assert len(b)==x['bytes'] and hashlib.sha256(b).hexdigest()==x['sha256'],x['path']
    assert (a.output/'RESULT-MANIFEST.json').read_bytes()==(a.expected/'RESULT-MANIFEST.json').read_bytes()
    r={'status':'PASS','regenerated_payload_files':len(expected),'manifest_exact':True,'fresh_output':str(a.output),'network_requests':0,'scope':'own adapted experiment only; original forum source/project omitted; requires locked Python runtime preinstalled'}
    with a.receipt.open('x') as h:h.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r))
