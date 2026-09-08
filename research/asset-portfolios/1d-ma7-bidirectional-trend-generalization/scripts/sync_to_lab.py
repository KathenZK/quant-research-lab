"""按上次 SHA 仅同步本家族拥有文件；未知冲突停止，不碰其他任务文件。"""
from pathlib import Path
import datetime as dt
import hashlib
import json
import shutil

FAMILY = Path(__file__).resolve().parents[1]
LAB = Path('/Users/ZK/OpenCode/quant-strategy-lab')
REL = Path('research/asset-portfolios') / FAMILY.name
MANIFEST = 'artifacts/sync-manifest.json'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    dest = LAB / REL
    previous = json.loads((dest / MANIFEST).read_text())
    files = {str(p.relative_to(FAMILY)): p for p in FAMILY.rglob('*')
             if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts
             and p.name != '.DS_Store' and str(p.relative_to(FAMILY)) != MANIFEST}
    changes = []
    for rel, source in files.items():
        target = dest / rel
        if target.exists() and sha(target) != sha(source):
            assert previous['files'].get(rel) == sha(target), f'UNKNOWN CONFLICT: {target}'
        if not target.exists() or sha(target) != sha(source):
            changes.append(rel)
    for rel in changes:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(files[rel], target)
    manifest = {'updated_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                'source': str(FAMILY), 'destination': str(dest),
                'files': {rel: sha(p) for rel,p in sorted(files.items())},
                'changed_files_this_sync': changes,
                'previous_manifest_sha256': sha(dest / MANIFEST),
                'policy': 'own family only; unknown destination changes fail closed; no deletions'}
    for p in [FAMILY / MANIFEST, dest / MANIFEST]:
        p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'synced': len(changes), 'owned_files': len(files), 'destination': str(dest)}))

if __name__ == '__main__':
    main()
