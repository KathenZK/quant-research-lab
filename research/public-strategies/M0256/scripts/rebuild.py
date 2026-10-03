#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Copy frozen code, references and exact input to a fresh local directory;
replay independently and compare every deterministic research output byte.
This does not prove remote/Git/Library recovery or source availability forever.
"""
import argparse,datetime,hashlib,json,pathlib,shutil,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def rebuild(input_path,reference,output):
    out=pathlib.Path(output);out.mkdir(parents=True,exist_ok=False);copy=out/'M0256'
    for folder in ('scripts','specs','sources'):shutil.copytree(ROOT/folder,copy/folder,ignore=shutil.ignore_patterns('__pycache__'))
    local_input=out/'input.csv';shutil.copyfile(input_path,local_input)
    spec=json.loads((copy/'specs/M0256-first-replay.json').read_text());assert sha(local_input)==spec['input']['sha256']
    result=out/'results'
    with (out/'replay.stdout.json').open('w') as log:subprocess.run([sys.executable,str(copy/'scripts/run_replay.py'),'--input',str(local_input),'--output',str(result)],check=True,stdout=log)
    expected=['signals.csv','summary.json','base-nav-light.csv']+[f'{case["name"]}-{suffix}.csv' for case in spec['cases'] for suffix in ('nav','daily-nav','trades')]
    checks=[]
    for name in expected:
        a=sha(pathlib.Path(reference)/name);b=sha(result/name);assert a==b,('RESULT_MISMATCH',name,a,b);checks.append({'file':name,'sha256':b,'bytes':(result/name).stat().st_size})
    subprocess.run([sys.executable,str(copy/'scripts/validate_independent.py'),'--input',str(local_input),'--results',str(result),'--output',str(out/'independent-validation.json')],check=True,stdout=subprocess.DEVNULL)
    receipt={'status':'PASS','recovered_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z'),'mode':'fresh-directory local copied-code+copied-input replay','input_sha256':sha(local_input),'protocol_sha256':sha(copy/'specs/M0256-first-replay.json'),'deterministic_files':checks,'independent_ledger_after_restore':'PASS','remote_retrieval_verified':False,'limitation':'No claim of remote/off-machine recovery or future source availability. Official URL removal returns UNAVAILABLE; changed bytes return MISMATCH.'}
    (out/'recovery-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--reference-results',required=True);p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(rebuild(a.input,a.reference_results,a.output),indent=2))
