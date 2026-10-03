#!/usr/bin/env python3
"""Create a finite exact public file allowlist. Refuses any existing manifest."""
import hashlib,json
from pathlib import Path
r=Path(__file__).resolve().parents[1]
p=r/'publication-manifest.json'
assert not p.exists(), 'preserve existing manifest; create versioned output instead'
files=[]
for f in sorted(r.rglob('*')):
 if not f.is_file():continue
 assert not f.is_symlink(), 'symlink not allowed'
 assert f.suffix in {'.md','.json','.py','.txt'}, f
 assert '__pycache__' not in f.parts and not any(x in f.name for x in ['.private.','.csv','.zip','.parquet']), f
 b=f.read_bytes(); files.append({'path':f.relative_to(r).as_posix(),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
out={'schema':'exact-publication-manifest/v1','record_id':'M0304','state':'BLOCKED_SOURCE_INPUT_PREPARATION_ONLY','files':files,'file_count_excluding_manifest':len(files),'bytes_excluding_manifest':sum(f['bytes'] for f in files),'self_excluded':True,'raw_market_data_included':False,'full_third_party_source_included':False,'historical_runs':0,'strict_reproductions':0,'private_graph_included':False}
with p.open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({'files_including_manifest':len(files)+1,'bytes_including_manifest':sum(f['bytes'] for f in files)+p.stat().st_size,'manifest_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))
