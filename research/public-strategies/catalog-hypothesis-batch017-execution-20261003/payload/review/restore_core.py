"""QA-only recovery of C0-pinned code; verifies every reproduced output hash.

Original C0 stays byte-for-byte intact. Its non-executable historical review
logs may be private, so this recovery verifies the complete operational subset
explicitly, plus fresh independent data/account QA, rather than pretending to
rerun the original prehistory admission. No new configurations or controls.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,p):
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main():
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--expected',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--ids',nargs='+',choices=['M1346','M1270','M1349'],required=True);a=p.parse_args();root=a.bundle.resolve()
    assert not a.output.exists() and not a.receipt.exists();sys.path.insert(0,str(root/'source'))
    records=[]
    for sid in a.ids:
        version='v2' if sid=='M1349' else 'v1';module_name='run_m1349_v2.py' if sid=='M1349' else 'run_v1.py'
        c0_path=root/f'frozen/C0-{version}.json';c0=json.loads(c0_path.read_bytes());pinmap={x['path']:x for x in c0['pins']}
        required=[f'source/{module_name}','source/daily_three_signals.py','frozen/runtime-v1.json',f'frozen/{sid}-root-frozen-rules.json']
        required.extend(f'kernel/{version}/'+f for f in ['engine.py','verify_account.py','manifest.json'])
        if version=='v2':required.extend('kernel/v2/'+x['path'] for x in json.loads((root/'kernel/v2/manifest.json').read_bytes())['files'])
        for rel in set(required):
            expected=pinmap[rel];f=root/rel;assert f.stat().st_size==expected['bytes'] and sha(f)==expected['sha256'],rel
        runner=load('consumer_'+sid,root/'source'/module_name);kernel=runner.load_kernel(root/f'kernel/{version}');kernel.environment(root/'frozen/runtime-v1.json')
        rows=kernel.load_input(a.input,dict(input=dict(bytes=128196,sha256=c0['input_sha256']),evaluation_start_ms=1672531200000,evaluation_end_ms=1735689600000));rules=json.loads((root/f'frozen/{sid}-root-frozen-rules.json').read_bytes())
        out=a.output/sid
        if sid=='M1349':runner.produce(rows,rules,out,kernel)
        else:runner.produce(sid,rows,rules,out,kernel)
        expected_path=a.expected/sid/'manifest.json';assert (out/'manifest.json').read_bytes()==expected_path.read_bytes()
        files=json.loads(expected_path.read_bytes())
        for item in files:
            f=out/item['path'];assert f.stat().st_size==item['bytes'] and sha(f)==item['sha256'],(sid,item['path'])
        records.append(dict(id=sid,C0_sha256=sha(c0_path),kernel_version=version,payloads=len(files),manifest_byte_exact=True,all_payloads_byte_exact=True,output_manifest_sha256=sha(out/'manifest.json')))
    a.receipt.write_text(json.dumps(dict(status='PASS',records=records,engine_QA_replay_configurations=4*len(a.ids),new_strategy_configurations=0,new_controls=0,strict_reproductions=0),indent=2)+'\n');print(a.receipt.read_text())
if __name__=='__main__':main()
