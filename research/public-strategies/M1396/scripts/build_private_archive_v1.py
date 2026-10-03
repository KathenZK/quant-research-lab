"""Build and verify a private local snapshot; no upload, deletion or network."""
import hashlib,json,zipfile
from pathlib import Path
FAMILY=Path(__file__).resolve().parents[1];ROOT=FAMILY.parents[2];ART=FAMILY/'artifacts/20261003-catalog-v1'

def digest(data):return hashlib.sha256(data).hexdigest()
def main():
    ident=FAMILY.name;dest=ART/'private-archive-v1';dest.mkdir(exist_ok=False)
    payloads={}
    for p in FAMILY.rglob('*'):
        if not p.is_file() or any(x in p.parts for x in ['__pycache__','private-fresh-restore','private-archive-v1','private-history-causality']):continue
        if p.name.endswith('.lock') or p.name.startswith('publication-'):continue
        payloads['family/'+str(p.relative_to(FAMILY))]=p
    pin=json.loads((FAMILY/'specs/kernel-pin.json').read_text())
    for name in list(pin['files'])+['manifest.json']:
        p=ROOT/pin['path']/name;payloads['shared-kernel/'+name]=p
    inputroot=Path('/workspace/quant-recovery/M0216-remote-restore')
    payloads['inputs/input.csv']=inputroot/'input-staging/input.csv'
    spec=json.loads((FAMILY/'specs/protocol-v1.json').read_text())
    for rec in spec['input']['raw_files']:
        p=inputroot/'raw'/rec['name'];assert p.stat().st_size==rec['bytes'] and digest(p.read_bytes())==rec['sha256'];payloads['inputs/raw/'+p.name]=p
    gate=json.loads((ART/'private-root-gate.json').read_text())
    for rec in gate['control']['files']:
        p=Path(rec['local_path']);assert p.stat().st_size==rec['bytes'] and digest(p.read_bytes())==rec['sha256'];payloads['control/'+p.name]=p
    private=Path('/workspace/quant-recovery/catalog-hypothesis-M1396-M1463-preflight-20261003-v1/private')
    for suffix in ['-identity.json','-original-record.json']:
        p=private/(ident+suffix);payloads['private-original/'+p.name]=p
    manifest=dict(schema='private-research-snapshot/v1',id=ident,files=[dict(path=k,bytes=p.stat().st_size,sha256=digest(p.read_bytes())) for k,p in sorted(payloads.items())],remote_backup=False,contains_private_original_fields=True)
    manifestbytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    archive=dest/(ident+'-20261003-v1.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name,p in sorted(payloads.items()):z.write(p,name)
        z.writestr('MANIFEST.json',manifestbytes)
    (dest/'manifest.json').write_bytes(manifestbytes)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and z.read('MANIFEST.json')==manifestbytes
        assert set(z.namelist())==set(payloads)|{'MANIFEST.json'}
        for rec in manifest['files']:
            b=z.read(rec['path']);assert len(b)==rec['bytes'] and digest(b)==rec['sha256']
    safe=dict(status='LOCAL_PRIVATE_ARCHIVE_VERIFIED',id=ident,archive_bytes=archive.stat().st_size,archive_sha256=digest(archive.read_bytes()),standalone_manifest_sha256=digest(manifestbytes),payloads=len(payloads),manifest_members=1,crc_and_all_payload_hashes_verified=True,canonical_input_sha256=spec['input']['sha256'],control_files=7,new_control_runs=0,remote_Library_saved=False,Library_backup_id=None,remote_private_backup_gap='Existing Library uploadHTTP401; no current upload or blind retry; localZIP is not durable backup',public_scope='Only this safe receipt, never ZIP or private manifest contents')
    with (ART/'private-archive.safe.json').open('x') as f:json.dump(safe,f,indent=2);f.write('\n')
    print(json.dumps(safe))
if __name__=='__main__':main()
