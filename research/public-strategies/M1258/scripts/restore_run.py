"""One clean-directory offline restore, exact C0 pins, full deterministic output comparison."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
FAMILY=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def restore(input_path,expected_manifest,fresh,receipt):
    assert not fresh.exists();fresh.mkdir(parents=True)
    c0=json.loads((FAMILY/'specs/C0-v1.json').read_text());family=fresh/'M1258'
    for rec in c0['files']:
        src=FAMILY/rec['path'];assert src.stat().st_size==rec['bytes'] and sha(src)==rec['sha256']
        dst=family/rec['path'];dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    shutil.copyfile(FAMILY/'specs/C0-v1.json',family/'specs/C0-v1.json')
    canonical=fresh/'input.csv';shutil.copyfile(input_path,canonical)
    assert sha(canonical)==c0['canonical_sha256']
    out=fresh/'results';env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    commands=[[sys.executable,str(family/'scripts/run_replay.py'),'--input',str(canonical),'--output',str(out)],[sys.executable,str(family/'scripts/verify_replay.py'),'--input',str(canonical),'--results',str(out),'--output',str(fresh/'oracle.json')]]
    for args in commands:subprocess.run(args,check=True,env=env,capture_output=True,text=True)
    expected=json.loads(expected_manifest.read_text());actual=json.loads((out/'manifest.json').read_text());assert actual==expected
    for rec in expected:assert sha(out/rec['path'])==rec['sha256']
    assert (out/'manifest.json').read_bytes()==expected_manifest.read_bytes()
    result=dict(status='PASS',fresh_directory=str(fresh),payloads=len(expected),payloads_exact=len(expected),manifest_exact=True,frozen_code_files=len(c0['files']),canonical_sha256=sha(canonical),restore_strategy_configurations=4,restore_control_configurations=1,new_trials=0,new_controls=0,requires_preinstalled_frozen_environment=True,network_requests=0)
    with receipt.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--expected-manifest',type=Path,required=True);p.add_argument('--fresh',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args();print(json.dumps(restore(a.input,a.expected_manifest,a.fresh,a.receipt)))
