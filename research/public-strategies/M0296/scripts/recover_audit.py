#!/usr/bin/env python3
"""Verify every packaged byte then rerun only our own offline AST/synthetic auditor.
No network, third-party import/exec, market data, orders or historical replay.
"""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();root=a.package_root.resolve();out=a.out.resolve()
 if sys.version_info[:2]!=(3,12):raise SystemExit('AST fingerprint schema requires Python3.12; no package installation is performed')
 m=json.loads((root/'PRIVATE_MANIFEST.json').read_text()); checked=[]
 for item in m['files']:
  f=root/item['path']
  if not f.resolve().is_relative_to(root):raise SystemExit('Unsafe manifest path')
  if not f.is_file() or f.stat().st_size!=item['bytes'] or sha(f)!=item['sha256']:raise SystemExit('Integrity failure: '+item['path'])
  checked.append(item['path'])
 pub=root/'public/research/public-strategies'
 for id in ['M0296','M0299','M0312','M0314']:
  pm=json.loads((pub/id/'publication-manifest.json').read_text())
  for x in pm['files']:
   f=pub/id/x['path']
   if sha(f)!=x['sha256'] or f.stat().st_size!=x['bytes']:raise SystemExit('Public manifest mismatch: '+str(f))
 result=out.with_suffix('.audit.json');out.parent.mkdir(parents=True,exist_ok=True)
 env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
 subprocess.run([sys.executable,str(pub/'M0296/scripts/audit_batch.py'),'--evidence-root',str(root/'private/source-evidence'),'--out',str(result)],check=True,env=env)
 expected=root/'private/frozen-results/audit-batch-result-v1.json'
 if result.read_bytes()!=expected.read_bytes():raise SystemExit('Recomputed audit differs from frozen result')
 receipt={'schema':'source-rule-audit-clean-recovery/v1','pass':True,'verified_package_files':len(checked),'private_manifest_sha256':sha(root/'PRIVATE_MANIFEST.json'),'recomputed_audit_sha256':sha(result),'frozen_audit_sha256':sha(expected),'byte_identical_audit_result':True,'historical_runs':0,'market_requests':0,'native_engine_runs':0,'third_party_code_executed':False,'python':sys.version.split()[0],'scope':'Recover source bytes and our own AST/synthetic audit; not original runtime or trading reproduction'}
 out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt))
if __name__=='__main__':main()
