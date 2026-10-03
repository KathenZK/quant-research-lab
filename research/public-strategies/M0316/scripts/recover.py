#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Execute a fresh process against an independently rebuilt pinned input; compare bytes."""
import argparse,pathlib,subprocess,sys,json,os,hashlib
p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--original',required=True);p.add_argument('--output',required=True);p.add_argument('--receipt',required=True);a=p.parse_args();R=pathlib.Path(__file__).resolve().parents[1];out=pathlib.Path(a.output)
cmd=[sys.executable,str(R/'scripts/run_replay.py'),'--input',a.input,'--output',a.output];env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}
r=subprocess.run(cmd,env=env,capture_output=True,text=True);assert r.returncode==0,r.stderr
orig=pathlib.Path(a.original);files=[]
for f in sorted(orig.iterdir()):
    if f.name=='summary.json':continue
    assert (out/f.name).read_bytes()==f.read_bytes(),f.name;files.append(f.name)
x=json.loads((orig/'summary.json').read_text());y=json.loads((out/'summary.json').read_text());x.pop('peak_rss_kib');y.pop('peak_rss_kib');assert x==y
receipt={'status':'PASS_LOCAL_RECOVERY','independent_data_snapshot_input':a.input,'fresh_subprocess':True,'command':cmd,'returncode':r.returncode,'matched_files':files,'summary_matches_excluding_peak_rss':True,'offsite_restore':False}
with open(a.receipt,'x') as f:json.dump(receipt,f,indent=2);f.write('\n')
print(json.dumps(receipt,indent=2))
