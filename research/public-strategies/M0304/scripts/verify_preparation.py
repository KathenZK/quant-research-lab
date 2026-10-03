#!/usr/bin/env python3
"""Offline verification/recovery of the blocked preparation package, not market data."""
import argparse, hashlib, json, os, subprocess, sys, platform, importlib.metadata as md
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
 a.output_dir.mkdir(parents=True,exist_ok=False)
 manifest=json.loads((root/'publication-manifest.json').read_text())
 listed={item['path'] for item in manifest['files']}
 actual={f.relative_to(root).as_posix() for f in root.rglob('*') if f.is_file() and f.name!='publication-manifest.json'}
 assert len(listed)==len(manifest['files']), 'duplicate manifest entries'
 assert actual==listed, f'file set mismatch missing={listed-actual}, extra={actual-listed}'
 assert not any(f.is_symlink() for f in root.rglob('*')), 'symlinks disallowed'
 frozen=json.loads((root/'specs/environment.json').read_text())
 assert platform.python_version()==frozen['python'], 'python version mismatch'
 for package,version in frozen['packages'].items(): assert md.version(package)==version, package
 for item in manifest['files']:
  f=root/item['path'];assert f.resolve().is_relative_to(root.resolve()), 'path traversal'
  assert f.is_file(),str(f)
  assert len(f.read_bytes())==item['bytes'],str(f)
  assert hashlib.sha256(f.read_bytes()).hexdigest()==item['sha256'],str(f)
 env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
 subprocess.run([sys.executable,str(root/'scripts/formula_probe.py'),'--output',str(a.output_dir/'synthetic-formula-validation.json')],check=True,env=env)
 receipt={'status':'PREPARATION_RECOVERY_PASS_NOT_RAW_DATA_OR_STRATEGY_RECOVERY','files_verified':len(manifest['files']),'network_requests':0,'historical_runs':0,'original_third_party_code_executed':False}
 (a.output_dir/'recovery-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
if __name__=='__main__':main()
