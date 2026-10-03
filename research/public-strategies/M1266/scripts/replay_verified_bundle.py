"""Restore frozen outputs using these exact code bytes and an authorized private bundle.

This is a restore diagnostic, not a new experiment or a way around the original
release gate. Private source, raw data, C0 and release are supplied locally;
none are fetched, embedded, or transmitted. Original runner checks all C0 pins.
"""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path

C0_SHA='adcf2862aaa7af28b19ced8432c62c23e314fd4ba6e3ec1e687cfd679c08a0f7'
RELEASE_SHA='debb6431803fc180c5fa31e7572b4c248d37c62be01b1886c30145885efd5225'
CODE_PINS={'m1266_engine_v1.py':'8fc21d238aa4c49fbd6c0a79ecfbd97fedc7d60b37e6df160aaf91eec40d05f5','run_m1266_v1.py':'8d1f52b13e11e40f9fbb73715ca67242753192484be9d0c9549e2640f54cc2f7'}

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def require(value,message):
 if not value:raise ValueError(message)
def safe_relative(text):
 p=Path(text);require(not p.is_absolute() and '..' not in p.parts and p.parts,'unsafe path');return p

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--private-preparation',type=Path,required=True);p.add_argument('--release',type=Path,required=True);p.add_argument('--workspace',type=Path,required=True);a=p.parse_args()
 require(sys.flags.optimize==0,'optimization forbidden')
 source=a.private_preparation.resolve();here=Path(__file__).resolve().parent
 c0file=source/'frozen/C0-v1.json';require(digest(c0file)==C0_SHA,'C0 mismatch');require(digest(a.release)==RELEASE_SHA,'release mismatch')
 c0=json.loads(c0file.read_bytes());require(len(c0['pins'])==132,'C0 pin count')
 for name,expected in CODE_PINS.items():require(digest(here/name)==expected,'remote code mismatch:'+name)
 for item in c0['pins']:
  path=source/safe_relative(item['path']);require(path.stat().st_size==item['bytes'] and digest(path)==item['sha256'],'private pin mismatch:'+item['path'])
 require(shutil.disk_usage(a.workspace.parent).free>5*1024**3+128*1024**2,'disk reserve')
 a.workspace.mkdir(parents=True,exist_ok=False);bundle=a.workspace/'bundle';bundle.mkdir()
 for item in c0['pins']:
  rel=safe_relative(item['path']);dst=bundle/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/rel,dst)
 shutil.copyfile(c0file,bundle/'frozen/C0-v1.json')
 # Replace staged execution copies with the verified bytes beside this recipe.
 # Hash equality preserves C0; the original source bundle is never modified.
 for name in CODE_PINS:shutil.copyfile(here/name,bundle/'scripts'/name)
 result=a.workspace/'results'
 argv=[sys.executable,str(here/'run_m1266_v1.py'),'--bundle',str(bundle),'--c0',str(bundle/'frozen/C0-v1.json'),'--release',str(a.release.resolve()),'--input',str(bundle/'input/input.csv'),'--output',str(result)]
 completed=subprocess.run(argv,capture_output=True,text=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
 (a.workspace/'runner.stdout').write_text(completed.stdout);(a.workspace/'runner.stderr').write_text(completed.stderr);require(completed.returncode==0,'original runner rejected or failed')
 expected=json.loads((here/'expected-result-hashes-v1.json').read_bytes())
 verified=[]
 require(sorted(p.name for p in result.iterdir())==sorted(x['path'] for x in expected),'output set differs')
 for item in expected:
  path=result/safe_relative(item['path']);require(path.stat().st_size==item['bytes'] and digest(path)==item['sha256'],'result mismatch:'+item['path']);verified.append(item)
 report=dict(status='PASS_FROZEN_RESTORE_NOT_NEW_TRIAL',C0_sha256=C0_SHA,release_sha256=RELEASE_SHA,code_pins=CODE_PINS,verified_outputs=verified,original_runner_used=True,all132_C0_pins_verified=True,additional_strategy_trials=0,additional_controls=0)
 (a.workspace/'restore-report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
