#!/usr/bin/env python3
"""Finalize an exact public execution-package allowlist, without private evidence."""
import argparse,hashlib,json
from pathlib import Path
r=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
files=[]
for f in sorted(r.rglob('*')):
 if not f.is_file():continue
 assert not f.is_symlink() and '__pycache__' not in f.parts
 assert f.suffix in {'.md','.json','.py','.txt'} and '.private.' not in f.name,f
 if f.resolve()==a.output.resolve():continue
 b=f.read_bytes();files.append({'path':f.relative_to(r).as_posix(),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
x={'schema':'exact-publication-manifest/v1','record_id':'M0304','state':'DIAGNOSTIC_EXECUTED_AND_INDEPENDENTLY_AUDITED','origin_run_id':'M0304-20261003-calendar2024-v1','fidelity_class':'HYPOTHESIS','files':files,'file_count_excluding_manifest':len(files),'bytes_excluding_manifest':sum(i['bytes'] for i in files),'self_excluded':True,'raw_market_data_included':False,'full_third_party_source_included':False,'private_graph_included':False,'strategy_configs':4,'same_window_controls':1,'searches':0,'strict_reproductions':0}
with a.output.open('x') as f:json.dump(x,f,indent=2);f.write('\n')
print(json.dumps({'files_including_manifest':len(files)+1,'bytes_including_manifest':sum(i['bytes'] for i in files)+a.output.stat().st_size,'manifest_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()}))
