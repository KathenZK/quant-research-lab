"""Verify remote public files, then construct a fresh private recovery bundle."""
import argparse,hashlib,json,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--repository',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
manifest=json.loads((Path(__file__).parent/'recovery-materialization.json').read_bytes());assert not a.output.exists()
for item in manifest['files']:
 src=a.repository/item['repository_path'];b=src.read_bytes();assert len(b)==item['bytes'] and hashlib.sha256(b).hexdigest()==item['sha256'],item['repository_path']
for item in manifest['files']:
 src=a.repository/item['repository_path'];dst=a.output/item['bundle_path'];dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
print('Verified and materialized',len(manifest['files']),'public core files; input raw cache remains external')
