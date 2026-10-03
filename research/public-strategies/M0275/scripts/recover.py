#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Recover once to a new directory from a separately captured canonical input."""
import argparse,datetime,hashlib,json,os,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--reference',required=True);p.add_argument('--target',required=True);p.add_argument('--receipt',required=True);a=p.parse_args()
    assert not pathlib.Path(a.target).exists(); env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}
    command=[sys.executable,str(ROOT/'scripts/run_replay.py'),'--input',a.input,'--output',a.target,'--spec',str(ROOT/'specs/protocol.json')]
    before=datetime.datetime.now(datetime.timezone.utc).isoformat();r=subprocess.run(command,env=env,capture_output=True,text=True,check=True)
    files={};ref=pathlib.Path(a.reference);target=pathlib.Path(a.target)
    assert sorted(p.name for p in ref.iterdir())==sorted(p.name for p in target.iterdir())
    for f in sorted(ref.iterdir()):
        if f.name=='summary.json':
            x=json.loads(f.read_text());y=json.loads((target/f.name).read_text());x.pop('peak_rss_kib');y.pop('peak_rss_kib');assert x==y
        else:assert sha(f)==sha(target/f.name),f.name
        files[f.name]={'reference_sha256':sha(f),'recovered_sha256':sha(target/f.name),'financial_content_equal':True}
    rec={'status':'PASS_LOCAL_RECOVERY','started_at_utc':before,'finished_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':command,'input_sha256':sha(a.input),'protocol_sha256':sha(ROOT/'specs/protocol.json'),'input_is_existing_independently_network_rebuilt_snapshot':True,'new_network_recapture_for_M0275':False,'no_reference_results_used_by_replay_process':True,'summary_difference_allowed':['peak_rss_kib'],'files':files,'offsite_backup':False}
    with open(a.receipt,'x') as f:json.dump(rec,f,indent=2);f.write('\n')
    print(json.dumps({'status':rec['status'],'files':len(files),'receipt':a.receipt}))
if __name__=='__main__':main()
