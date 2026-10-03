"""Authorized posthistory isolated byte-exact restoration; no network."""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
from kernel_loader import FAMILY,ROOT,load
engine=load('engine')

def restore(input_path,gate,reference,destination):
    from run_replay import check_gate
    check_gate(gate)
    assert not destination.exists();destination.mkdir(parents=True)
    rel=FAMILY.relative_to(ROOT);copy=destination/rel
    c0=json.loads((FAMILY/'specs/C0-v1.json').read_text())
    for item in c0['files']:
        src=FAMILY/item['path'];dst=copy/item['path'];dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(src.read_bytes())
    (copy/'specs/C0-v1.json').write_bytes((FAMILY/'specs/C0-v1.json').read_bytes())
    pin=json.loads((FAMILY/'specs/kernel-pin.json').read_text());base=destination/pin['path'];base.mkdir(parents=True)
    for name in list(pin['files'])+['manifest.json']:(base/name).write_bytes((ROOT/pin['path']/name).read_bytes())
    private=destination/'private';private.mkdir();shutil.copyfile(input_path,private/'input.csv');shutil.copyfile(gate,private/'root-gate.json')
    env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    subprocess.run([sys.executable,str(copy/'scripts/run_replay.py'),'--input',str(private/'input.csv'),'--output',str(private/'results'),'--root-gate',str(private/'root-gate.json')],env=env,check=True,capture_output=True,text=True)
    subprocess.run([sys.executable,str(copy/'scripts/verify_replay.py'),'--input',str(private/'input.csv'),'--results',str(private/'results'),'--output',str(private/'validation.json')],env=env,check=True,capture_output=True,text=True)
    manifest=json.loads((reference/'manifest.json').read_text());assert {p.name for p in (private/'results').iterdir()}=={p.name for p in reference.iterdir()}
    for name in [x['path'] for x in manifest]+['manifest.json']:assert (private/'results'/name).read_bytes()==(reference/name).read_bytes(),name
    receipt=dict(status='PASS',compared_files=len(manifest)+1,scope='Fresh local source+input reconstruction, not Library snapshot or remote recovery',strategy_configurations_research_count=0,new_controls=0)
    engine.dump(destination/'restoration-receipt.json',receipt);return receipt
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--root-gate',type=Path,required=True);p.add_argument('--results',type=Path,required=True);p.add_argument('--destination',type=Path,required=True);a=p.parse_args();print(json.dumps(restore(a.input,a.root_gate,a.results,a.destination)))
