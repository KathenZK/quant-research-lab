"""Append-only v2 private snapshot after display-only correction; retain v1; no upload or replay."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]

def digest(data): return hashlib.sha256(data).hexdigest()
def encoded(value): return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()

def build(runtime, raw, control, original_record, independent_review, destination):
    assert not destination.exists(); destination.mkdir(parents=True)
    payloads = {}
    def add(name, p):
        assert name not in payloads and not p.is_symlink()
        payloads[name] = p.read_bytes()
    c0 = json.loads((FAMILY / 'specs/C0-v1.json').read_text())
    for item in c0['files']:
        data = (FAMILY / item['path']).read_bytes()
        assert len(data) == item['bytes'] and digest(data) == item['sha256']
    for p in sorted(FAMILY.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts: continue
        assert not p.name.startswith('publication-manifest') and p.name != 'private-archive-v2.safe.json', 'Build once before final archive/publication descriptors'
        add('repo/' + str(p.relative_to(ROOT)), p)
    public_core = [dict(path=k[5:], bytes=len(v), sha256=digest(v)) for k, v in sorted(payloads.items())]
    payloads['PUBLIC-CORE-INVENTORY.json'] = encoded(dict(files=public_core,
        note='Exact public core at package creation. Later archive-safe receipt and final publication inventory are outer descriptors, intentionally nonrecursive.'))
    pin = json.loads((FAMILY / 'specs/kernel-pin.json').read_text())
    for rel, item in pin['files'].items():
        p = ROOT / pin['root'] / rel; data = p.read_bytes()
        assert len(data) == item['bytes'] and digest(data) == item['sha256']
        add('repo/' + pin['root'] + '/' + rel, p)
    spec = json.loads((FAMILY / 'specs/protocol-v1.json').read_text())
    add('inputs/input.csv', runtime / 'input.csv')
    assert digest(payloads['inputs/input.csv']) == spec['input']['sha256']
    for item in spec['input']['raw_files']:
        p = raw / item['name']; data = p.read_bytes()
        assert len(data) == item['bytes'] and digest(data) == item['sha256']
        add('inputs/raw/' + item['name'], p)
    reference = json.loads((FAMILY / 'specs/control-reference.json').read_text())
    for item in reference['files']:
        p = control / item['path']; data = p.read_bytes()
        assert len(data) == item['bytes'] and digest(data) == item['sha256']
        add('existing-control/' + item['path'], p)
    for p in sorted((runtime / 'results').iterdir()): add('results/' + p.name, p)
    expected = json.loads((runtime / 'results/manifest.json').read_text())
    for item in expected:
        data = payloads['results/' + item['path']]
        assert len(data) == item['bytes'] and digest(data) == item['sha256']
    for p in sorted(runtime.iterdir()):
        if p.is_file() and p.name != 'input.csv': add('execution/' + p.name, p)
    add('verification/fresh-restore-receipt.json', runtime / 'fresh-restore/restoration-receipt.json')
    add('verification/independent-actual-ledger.private.json', independent_review)
    add('private-catalog/M1347-original-record.json', original_record)
    assert digest(payloads['private-catalog/M1347-original-record.json']) == spec['source_original_binding']['record_sha256']
    payloads['PACKAGE-README.md'] = ('''# M1347 私有恢复包

完整输入只存 inputs/input.csv 一份，50 原档只存 inputs/raw 一组；四配置完整账本在 results。
repo 内保存原 28 个 C0 对象、固定共享 v1、当前结果文档及便携恢复入口。existing-control 为已验 M1258 七文件，只读引用，禁止当成新增控制。
private-catalog 含完整用户目录原记录及内部批注，仅限私有保存；不公开。原作者网页/实现未获取，不能声称恢复作者原程序。
恢复需要预装 repo 下 environment-lock 指定的运行环境。先使用 python RESTORE_PACKAGE.py 检验全部成员；有明确恢复授权时再 python RESTORE_PACKAGE.py --replay，调用原冻结代码，输出到全新 restored-core，按原公开 hash manifest 校验，不修改参考输出。
原 root 放行保存在 execution，便携版本只重映射独立审查回执位置；两者的原 C0/四配置权限不变。
外层最终 publication inventory 与 ZIP 自身安全回执为非递归描述，不在本包核心文件中。独立 manifest 随包单独保存。本地 ZIP 不代表 Library 或其他远端成功备份。
''').encode()
    payloads['RESTORE_PACKAGE.py'] = b'''import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--replay',action='store_true');a=p.parse_args();root=Path(__file__).resolve().parent
manifest=json.loads((root/'MANIFEST.json').read_text())
for item in manifest['files']:
 rel=Path(item['path']);assert not rel.is_absolute() and '..' not in rel.parts
 f=root/rel;assert not f.is_symlink();data=f.read_bytes();assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'],item['path']
print(json.dumps({'status':'PASS','verified_members':len(manifest['files']),'new_research_configurations':0}))
if a.replay:
 env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
 script=root/'repo/research/public-strategies/M1347/scripts/restore_core_v1.py'
 subprocess.run([sys.executable,str(script),'--input',str(root/'inputs/input.csv'),'--fresh',str(root/'restored-core'),'--receipt',str(root/'restored-core-receipt.json')],env=env,check=True)
'''
    manifest = dict(schema='M1347-private-recovery/v2', id='M1347',
        original_source_commit='5ccadf192dfc6381721058d28887cd9bc435a20c',
        C0_sha256=digest((FAMILY / 'specs/C0-v1.json').read_bytes()),
        files=[dict(path=k, bytes=len(v), sha256=digest(v)) for k, v in sorted(payloads.items())],
        logical_mapping=dict(canonical='inputs/input.csv', raw='inputs/raw', full_reference='results',
                             frozen_code='repo/research/public-strategies/M1347', kernel='repo/' + pin['root'],
                             existing_control='existing-control', private_original='private-catalog'),
        original_webpage_or_runtime_included=False, exact_environment_preinstalled_required=True,
        remote_private_backup_verified=False)
    manifest_bytes = encoded(manifest)
    archive = destination / 'M1347-private-recovery-v2.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(payloads.items()): z.writestr(name, data)
        z.writestr('MANIFEST.json', manifest_bytes)
    (destination / 'PRIVATE-CONTENTS-v2.json').write_bytes(manifest_bytes)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and len(z.namelist()) == len(payloads) + 1
        assert set(z.namelist()) == set(payloads) | {'MANIFEST.json'}
        assert z.read('MANIFEST.json') == manifest_bytes
        for item in manifest['files']:
            data = z.read(item['path']); assert len(data) == item['bytes'] and digest(data) == item['sha256']
    safe = dict(prior_archive_sha256=json.loads((FAMILY / 'artifacts/20261003-catalog-v1/private-archive.safe.json').read_text())['archive_sha256'], display_projection_version=2, status='LOCAL_PRIVATE_ARCHIVE_CRC_AND_ALL_HASHES_PASS', id='M1347',
        archive_name=archive.name, archive_bytes=archive.stat().st_size, archive_sha256=digest(archive.read_bytes()),
        standalone_manifest_name='PRIVATE-CONTENTS-v2.json', standalone_manifest_bytes=len(manifest_bytes),
        standalone_manifest_sha256=digest(manifest_bytes), payloads=len(payloads), manifest_members=1,
        raw_objects=50, canonical_copies=1, full_result_files=31, existing_control_files=7,
        public_core_objects=len(public_core), original_28_C0_objects_unchanged=True,
        new_research_configurations=0, new_controls=0, Library_saved=False, Library_backup_id=None,
        private_remote_gap='Known Library HTTP401; no retry; local archive is not remote backup',
        public_manifest_and_archive_receipt='Outer nonrecursive descriptors intentionally not inside snapshot')
    (FAMILY / 'artifacts/20261003-catalog-v1/private-archive-v2.safe.json').write_bytes(encoded(safe))
    print(json.dumps(safe))

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for arg in ['runtime', 'raw', 'control', 'original-record', 'independent-review', 'destination']:
        p.add_argument('--' + arg, type=Path, required=True)
    a = p.parse_args(); build(a.runtime, a.raw, a.control, a.original_record, a.independent_review, a.destination)
