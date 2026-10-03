"""Read-only frozen source, fresh outputs, independent remote hash references.
The old restore_run CLI requires unavailable full prior payloads. This driver uses
its source/input copy and original run+verify commands, then compares remote hashes.
It never invokes the abandoned self-reference adapter or imports old results.
"""
from pathlib import Path
import datetime as dt,fcntl,hashlib,json,os,resource,shutil,subprocess,sys,time
Q=Path(os.environ['RECOVERY_ROOT']).resolve();CORE=Q/'core';IDS=['M1396','M1463']
PY=Path(os.environ['PINNED_PYTHON'])
HELPER=CORE/'research/public-strategies/M1358/recovery/remote-core-v1'
CONTROL=Path(os.environ['CONTROL_CACHE'])
RAW=Path(os.environ['RAW_CACHE'])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,r):
 with p.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
def ref(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(HELPER/'offline-guard'),M1358_OFFLINE_AUDIT_LOG=str(Q/'offline-processes.jsonl'))
stages=[]
def run(stage,family,script,args):
 cmd=[str(PY),str(HELPER/'locked_exec.py'),'--family',str(family),str(script),*map(str,args)]
 before=resource.getrusage(resource.RUSAGE_CHILDREN);start=dt.datetime.now(dt.timezone.utc).isoformat();wall=time.perf_counter()
 with (Q/(stage+'.log')).open('x') as f:r=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT)
 after=resource.getrusage(resource.RUSAGE_CHILDREN);out=dict(stage=stage,command=cmd,start_utc=start,end_utc=dt.datetime.now(dt.timezone.utc).isoformat(),wall_seconds=time.perf_counter()-wall,child_cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,max_child_rss_kib=after.ru_maxrss,returncode=r.returncode);stages.append(out);dump(Q/(stage+'-execution.json'),out);assert r.returncode==0,stage
with (Q/'review.lock').open('r+') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);free_start=shutil.disk_usage(Q).free;assert free_start>5*1024**3
 source=json.loads((Q/'source-materialization.private.json').read_text())
 for x in source['objects']:
  p=CORE/x['path'];assert p.stat().st_size==x['bytes'] and sha(p)==x['sha256']
 family={i:CORE/f'research/public-strategies/{i}' for i in IDS};protocols={i:json.loads((family[i]/'specs/protocol-v1.json').read_text()) for i in IDS}
 assert protocols['M1396']['input']==protocols['M1463']['input']
 prior=Path(os.environ['CONTROL_RECOVERY_RECEIPT']);assert sha(prior)=='448e6996f1562999bb47e455fdac460f77fda0d688391a160139510f61c22131'
 control_records=[]
 for i in IDS:
  f=family[i];pubauth=f/'recovery/control-release-v1/prehistory-authorization.safe.json';auth=json.loads(pubauth.read_text());release=json.loads((f/'recovery/control-release-v1/release.json').read_text());cref=json.loads((f/'recovery/control-release-v1/control-reference.json').read_text())
  assert auth['status']=='ROOT_APPROVED_HISTORY_AFTER_INDEPENDENT_QA' and auth['id']==i
  assert auth['C0_sha256']==sha(f/'specs/C0-v1.json') and auth['control_independently_accepted'] is True
  assert auth['control']['remote_commit']==release['remote_public_core_commit']=='2a2e33e0de2b4897d6ccb460e72dcb5e73aa4153'
  assert auth['control']['files']==cref['files'] and len(cref['files'])==7
  for x in auth['control']['files']:
   p=CONTROL/x['path'];assert p.stat().st_size==x['bytes'] and sha(p)==x['sha256'];x['local_path']=str(p)
  (Q/i).mkdir();dump(Q/i/'root-gate.local.json',auth);control_records.append(dict(id=i,authorization_sha256=sha(pubauth),control_reference_sha256=sha(f/'recovery/control-release-v1/control-reference.json'),control_files=7,provenance_receipt=ref(prior),local_path_only_added=True))
 dump(Q/'control-reuse.private.json',dict(status='PASS',records=control_records,new_controls=0,control_replayed=False))
 run('input-rebuild',family['M1396'],family['M1396']/'scripts/rebuild_input.py',['--raw',RAW,'--output',Q/'input.csv','--receipt',Q/'input-rebuild.json'])
 all_results={}
 for i in IDS:
  original=family[i];root=Q/i/'fresh';root.mkdir();copy=root/f'research/public-strategies/{i}';c0=json.loads((original/'specs/C0-v1.json').read_text())
  for x in c0['files']:
   src=original/x['path'];assert src.stat().st_size==x['bytes'] and sha(src)==x['sha256'];dst=copy/x['path'];dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
  shutil.copyfile(original/'specs/C0-v1.json',copy/'specs/C0-v1.json')
  pin=json.loads((original/'specs/kernel-pin.json').read_text());base=root/pin['path'];base.mkdir(parents=True)
  for name in [*pin['files'],'manifest.json']:shutil.copyfile(CORE/pin['path']/name,base/name)
  private=root/'private';private.mkdir();shutil.copyfile(Q/'input.csv',private/'input.csv');shutil.copyfile(Q/i/'root-gate.local.json',private/'root-gate.json')
  expected_path=original/'artifacts/20261003-catalog-v1/private-output-manifest.json';expected=json.loads(expected_path.read_text());assert len(expected)==30
  expected_copy=Q/i/'expected-manifest.json';shutil.copyfile(expected_path,expected_copy)
  run(i+'-run',copy,copy/'scripts/run_replay.py',['--input',private/'input.csv','--output',private/'results','--root-gate',private/'root-gate.json'])
  run(i+'-verify',copy,copy/'scripts/verify_replay.py',['--input',private/'input.csv','--results',private/'results','--output',private/'validation.json'])
  out=private/'results';assert {p.name for p in out.iterdir()}=={x['path'] for x in expected}|{'manifest.json'}
  hashes=[]
  for x in expected:
   p=out/x['path'];assert p.stat().st_size==x['bytes'] and sha(p)==x['sha256'],(i,x['path']);hashes.append(x)
  assert (out/'manifest.json').read_bytes()==expected_path.read_bytes()
  oracle=json.loads((private/'validation.json').read_text());assert oracle['status']=='PASS'
  for x in c0['files']:assert sha(copy/x['path'])==x['sha256']
  assert sha(copy/'specs/C0-v1.json')==sha(original/'specs/C0-v1.json')
  all_results[i]=dict(status='REMOTE_HASH_REFERENCE_REBUILD_PASS',payloads_size_sha256_exact=30,manifest_byte_exact=True,total_output_files=31,expected_only_remote=True,expected_manifest=ref(expected_copy),C0_sha256=sha(original/'specs/C0-v1.json'),copied_frozen_files=len(c0['files'])+1,oracle=oracle,oracle_receipt=ref(private/'validation.json'),engine_executions=1,restore_cli_invoked=False,original_run_and_verify_invoked=True,full_original_results_available=False,new_trials=0,new_controls=0,strict_reproductions=0,checks=hashes)
  dump(Q/i/'recovery.private.json',all_results[i])
 for x in source['objects']:assert sha(CORE/x['path'])==x['sha256']
 guards=[json.loads(x) for x in (Q/'offline-processes.jsonl').read_text().splitlines()];assert len(guards)==5 and all(x['event']=='GUARD_ACTIVE' for x in guards)
 free_end=shutil.disk_usage(Q).free;assert free_end>5*1024**3
 result=dict(status='REMOTE_HASH_REFERENCE_REBUILD_PASS',finished_utc=dt.datetime.now(dt.timezone.utc).isoformat(),source_commit=source['commit'],publication_union=96,publication_union_bytes=source['publication_union_bytes'],support_files=4,IDs=all_results,original_restore_CLI_limitation='Requires full prior financial payloads. Not called; source/input copy and original run_replay+verify commands reproduced by external driver; references are exclusively fixed remote size/SHA, not old result bytes.',abandoned_adapter_used=False,control_reused_files=7,control_replayed=False,engine_executions=2,configuration_recoveries=8,new_strategy_trials=0,new_controls=0,strict_reproductions=0,offline_processes=5,network_attempts_during_replay=0,environment_lock_asserted=True,source_C0_unchanged=True,stages=stages,free_disk_before=free_start,free_disk_after=free_end)
 dump(Q/'coordinator-comparison.private.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ['IDs','stages']}))
