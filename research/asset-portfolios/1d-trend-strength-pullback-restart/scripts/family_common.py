"""本家族不可覆盖证据与冻结身份入口；不读取市场数据。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

FAMILY = Path(__file__).resolve().parents[1]
REPO = FAMILY.parents[2]
KERNEL = REPO / 'research/_shared-kernels/trend-strength-pullback-restart/v1'
SOURCE_LAB = Path('/Users/ZK/OpenCode/quant-strategy-lab')
sys.path.insert(0, str(SOURCE_LAB / 'src'))
sys.path.insert(0, str(KERNEL))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f'Retained evidence exists: {path}')
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str,
                               allow_nan=False) + '\n')


def verify_lock():
    path = FAMILY / 'specs/computation-lock.json'
    lock = json.loads(path.read_text())
    for relative, expected in lock['files'].items():
        target = (REPO / relative).resolve()
        if not target.is_relative_to(REPO.resolve()) or sha(target) != expected:
            raise ValueError(f'Frozen computation changed: {relative}')
    manifest = lock['kernel_manifest']
    mpath = REPO / manifest['path']
    if sha(mpath) != manifest['sha256']:
        raise ValueError('Frozen kernel manifest changed')
    entries = json.loads(mpath.read_text())['files']
    actual = {str(p.relative_to(KERNEL)) for p in KERNEL.rglob('*.py')}
    if actual != set(entries):
        raise ValueError('Frozen kernel Python inventory changed')
    for relative, expected in entries.items():
        if sha(KERNEL / relative) != expected:
            raise ValueError(f'Frozen kernel content changed: {relative}')
    return {'computation_lock_sha256': sha(path), 'files': lock['files'],
            'kernel_manifest': manifest}


def load_panel(run_id='p1-research'):
    import pandas as pd
    directory = FAMILY / 'artifacts' / run_id
    manifest = json.loads((directory / 'panel-manifest.json').read_text())
    path = directory / manifest['path']
    if sha(path) != manifest['sha256']:
        raise ValueError('Retained panel hash mismatch')
    frame = pd.read_pickle(path, compression='gzip')
    if len(frame) != manifest['rows'] or frame.symbol.nunique() != manifest['symbols']:
        raise ValueError('Retained panel dimensions mismatch')
    return frame, {'panel_manifest_sha256': sha(directory / 'panel-manifest.json'),
                   'panel_sha256': manifest['sha256']}
