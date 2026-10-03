"""Fresh-process recovery against an independent original reference directory.
Reference never substitutes for generated output. No network, private data copying beyond this ID.
"""
if not __debug__:
    raise RuntimeError('M3710 rejects Python -O')
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from dependencies import FAMILY, ROOT, sha
from gates import verify_c0, check_gate, disk_reserve


def restore(input_path,reference,destination,gate_path,receipt_path):
    disk_reserve(destination)
    gate=check_gate(gate_path);c0=verify_c0()
    assert not destination.exists() and reference.is_dir()
    expected_path=reference/'manifest.json';expected_bytes=expected_path.read_bytes()
    expected=json.loads(expected_bytes)
    assert len(expected)==37 and len({x['path'] for x in expected})==37
    for x in expected:
        assert Path(x['path']).name==x['path']
        assert (reference/x['path']).stat().st_size==x['bytes'] and sha(reference/x['path'])==x['sha256']
    destination.mkdir(parents=True)
    family=destination/FAMILY.relative_to(ROOT)
    for x in c0['files']:
        p=family/x['path'];p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(FAMILY/x['path'],p)
    shutil.copyfile(FAMILY/'specs/C0-v1.json',family/'specs/C0-v1.json')
    for pin_name in ['kernel-pin.json','adapter-pin.json']:
        pin=json.loads((FAMILY/'specs'/pin_name).read_text())
        for rel,x in pin['files'].items():
            src=ROOT/pin['root']/rel
            assert src.stat().st_size==x['bytes'] and sha(src)==x['sha256']
            dst=destination/pin['root']/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    private=destination/'private';private.mkdir()
    shutil.copyfile(input_path,private/'input.csv')
    r=gate['independent_code_review'];shutil.copyfile(r['local_path'],private/'independent-code-review.safe.json')
    r['local_path']=str(private/'independent-code-review.safe.json')
    (private/'root-release.json').write_text(json.dumps(gate,indent=2)+'\n')
    env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    scripts=family/'scripts';results=private/'results'
    subprocess.run([sys.executable,str(scripts/'run_replay.py'),'--input',str(private/'input.csv'),
        '--output',str(results),'--root-gate',str(private/'root-release.json')],env=env,check=True)
    assert (results/'manifest.json').read_bytes()==expected_bytes
    assert {p.name for p in results.iterdir()}=={x['path'] for x in expected}|{'manifest.json'}
    for x in expected:
        assert (results/x['path']).read_bytes()==(reference/x['path']).read_bytes(),x['path']
    subprocess.run([sys.executable,str(scripts/'verify_replay.py'),'--input',str(private/'input.csv'),
        '--results',str(results),'--root-gate',str(private/'root-release.json'),
        '--output',str(private/'account-qa.json')],env=env,check=True)
    report=dict(id='M3710',status='PASS_FRESH_PROCESS_BYTE_EXACT',payloads=37,files=38,
        expected_manifest_sha256=sha(expected_path),input_sha256=sha(private/'input.csv'),
        new_research_trials=0,new_controls=0,scope='Local independently retained reference recovery; not remote publication or Library backup')
    with receipt_path.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ['input','reference','fresh','root-gate','receipt']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();print(json.dumps(restore(a.input,a.reference,a.fresh,a.root_gate,a.receipt)))
