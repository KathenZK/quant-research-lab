#!/usr/bin/env python3
"""Read-only source fingerprint and AST check. Never imports or executes the source."""
import argparse,ast,hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('source_file',type=Path);a=p.parse_args()
b=a.source_file.read_bytes();s=json.loads((root/'specs/source-manifest.json').read_text())['items'][0]
assert len(b)==s['bytes'] and hashlib.sha256(b).hexdigest()==s['sha256']
t=ast.parse(b);cl=next(n for n in t.body if isinstance(n,ast.ClassDef) and n.name=='Strategy002')
attrs={}
for n in cl.body:
 if isinstance(n,ast.Assign):
  for target in n.targets:
   if isinstance(target,ast.Name):attrs[target.id]=ast.literal_eval(n.value)
 elif isinstance(n,ast.AnnAssign):attrs[n.target.id]=ast.literal_eval(n.value)
assert attrs==json.loads((root/'specs/source-ast-attributes.json').read_text())
assert {n.name for n in cl.body if isinstance(n,ast.FunctionDef)}=={'informative_pairs','populate_indicators','populate_entry_trend','populate_exit_trend'}
print(json.dumps({'status':'SOURCE_HASH_BYTES_AST_PASS','original_code_executed':False,'historical_runs':0}))
