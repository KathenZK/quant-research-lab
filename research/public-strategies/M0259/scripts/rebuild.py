#!/usr/bin/env python3
"""Re-run identical frozen input/code into fresh output and compare content hashes.
Input and qtpylib materialization are explicit caller steps, independent of location.
This script never downloads market data or accepts legal terms.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser()
    for x in ['input','qtpylib','freeze','reference','out','receipt']:p.add_argument('--'+x,required=True)
    a=p.parse_args();scripts=Path(__file__).resolve().parent
    subprocess.run([sys.executable,str(scripts/'replay.py'),'--input',a.input,'--qtpylib',a.qtpylib,'--freeze',a.freeze,'--out',a.out],check=True)
    reference=Path(a.reference);out=Path(a.out)
    names=sorted(p.name for p in reference.iterdir() if p.is_file() and p.name not in ['validation.json','causality.json'])
    got=sorted(p.name for p in out.iterdir() if p.is_file())
    assert names==got,('File set mismatch',names,got)
    matches=[]
    for name in names:
        h=sha(reference/name);g=sha(out/name)
        assert h==g,('MISMATCH',name,h,g)
        matches.append({'file':name,'sha256':h,'bytes':(out/name).stat().st_size})
    # Also re-run the independent validator in the new destination.
    subprocess.run([sys.executable,str(scripts/'validate_independent.py'),'--input',a.input,'--results',a.out,'--out',str(out/'validation.json')],check=True)
    result={'status':'VERIFIED','scope':'actual replay into distinct fresh output directory using frozen code/spec/input; byte-for-byte baseline and all sensitivity results; independent ledger rerun',
            'frozen_sha256':sha(a.freeze),'input_sha256':sha(a.input),'matched_files':matches,
            'source_results_location':str(reference.resolve()),'fresh_results_location':str(out.resolve()),
            'limits':'local bytes restored; fresh online market-data retrieval is a separate rights-sensitive operation; public source availability never guaranteed'}
    with open(a.receipt,'x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print('VERIFIED',len(matches),'result files restored')
if __name__=='__main__':main()
