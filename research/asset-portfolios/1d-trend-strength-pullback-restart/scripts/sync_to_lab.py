"""仅同步本任务拥有的独立家族/共享版本；冲突先停止，不覆盖并行工作。"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import shutil
import tempfile

from family_common import FAMILY, KERNEL, REPO, save_json, sha, verify_lock

LAB = Path('/Users/ZK/OpenCode/quant-strategy-lab')


def main():
    verify_lock()
    receipt_path = FAMILY / 'artifacts/delivery-sync.json'
    if receipt_path.exists():
        raise FileExistsError('Delivery receipt already exists; inspect it rather than overwrite')
    base = FAMILY.relative_to(REPO)
    startup = json.loads((FAMILY / 'artifacts/startup-sync-receipt.json').read_text())['files']
    previous = {str(base / relative): expected for relative, expected in startup.items()}
    inventory = []
    roots = (FAMILY, KERNEL.parent)
    for source_root in roots:
        for path in sorted(source_root.rglob('*')):
            if path.is_symlink():
                raise ValueError(f'Unexpected owned symlink: {path}')
            if not path.is_file() or '__pycache__' in path.parts or '.pytest_cache' in path.parts:
                continue
            if path.name.endswith(('.pyc', '.lock')) or path == receipt_path:
                continue
            relative = str(path.relative_to(REPO))
            destination = LAB / relative
            digest = sha(path)
            current = sha(destination) if destination.exists() else None
            if current is not None and current != digest and previous.get(relative) != current:
                raise RuntimeError(f'Unowned destination change; synchronization stopped: {destination}')
            inventory.append((path, destination, relative, digest, current))
    copied = unchanged = 0
    for source, destination, relative, digest, previous_digest in inventory:
        if sha(source) != digest:
            raise RuntimeError(f'Source changed during delivery: {relative}')
        if previous_digest == digest:
            unchanged += 1
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.tspr-sync-', delete=False) as stream:
            temp = Path(stream.name)
        try:
            shutil.copy2(source, temp)
            if sha(temp) != digest:
                raise RuntimeError('Copy digest differs')
            observed = sha(destination) if destination.exists() else None
            if observed != previous_digest:
                raise RuntimeError(f'Destination changed during delivery: {relative}')
            os.replace(temp, destination)
            copied += 1
        finally:
            temp.unlink(missing_ok=True)
    mismatches = [relative for source, destination, relative, digest, _ in inventory
                  if sha(source) != digest or sha(destination) != digest]
    if mismatches:
        raise RuntimeError(f'Final delivery comparison failed: {mismatches[:5]}')
    result = {'status': 'PASS', 'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'owned_files': len(inventory), 'copied': copied, 'unchanged': unchanged,
              'destination': str(LAB), 'files': {r: h for _, _, r, h, _ in inventory},
              'root_indexes': 'exact additive family/kernel rows handled separately; never wholesale copied'}
    save_json(receipt_path, result)
    dest = LAB / receipt_path.relative_to(REPO)
    if dest.exists():
        raise FileExistsError(dest)
    shutil.copy2(receipt_path, dest)
    if sha(dest) != sha(receipt_path):
        raise RuntimeError('Delivery receipt mismatch')
    print({'status': 'PASS', 'owned_files': len(inventory), 'copied': copied, 'unchanged': unchanged})


if __name__ == '__main__':
    main()
