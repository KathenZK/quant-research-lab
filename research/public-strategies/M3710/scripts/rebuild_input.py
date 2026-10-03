"""Offline raw archive recipe; exact manifest and shared input validator, no features."""
if not __debug__:
    raise RuntimeError('M3710 rejects Python -O')
import argparse
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path
from dependencies import FAMILY, adapter
from gates import disk_reserve


def rebuild(raw,output):
    disk_reserve(output)
    manifest_path=FAMILY/'specs/input-manifest.json'
    spec=json.loads((FAMILY/'specs/protocol-v1.json').read_text())
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest()==spec['input']['manifest_sha256']
    manifest=json.loads(manifest_path.read_text());assert len(manifest['objects'])==56
    rows=[];cols=adapter().COLS
    for x in manifest['objects']:
        p=raw/x['name'];b=p.read_bytes()
        assert len(b)==x['bytes'] and hashlib.sha256(b).hexdigest()==x['sha256']
        if p.suffix=='.zip':
            ch=(raw/(p.name+'.CHECKSUM')).read_text().split()
            assert len(ch)==2 and ch[0]==x['sha256'] and ch[1].lstrip('*')==p.name
            with zipfile.ZipFile(io.BytesIO(b)) as z:
                assert z.namelist()==[p.stem+'.csv'] and z.testzip() is None
                month=list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode(),newline='')))
                assert all(len(r)==12 and all(r) for r in month);rows.extend(month)
    assert len(rows)==853
    selected=[r for r in rows if 1663891200000<=int(r[0])<1735689600000]
    assert len(selected)==831 and rows[22:]==selected
    buffer=io.StringIO(newline='');writer=csv.writer(buffer);writer.writerow(cols);writer.writerows(selected)
    data=buffer.getvalue().encode();adapter().load_input(data,'warmup100')
    with output.open('xb') as f:f.write(data)
    return dict(status='PASS_DATA_ONLY',bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
        raw_objects=56,CRC_checks=28,provider_checksums=28,rows=831,warmup=100,evaluation=731,
        quality='DIAGNOSTIC_ONLY',trusted=False,PIT=False,features_computed=False,network_calls=0)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ['raw','output','receipt']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();result=rebuild(a.raw,a.output)
    with a.receipt.open('x') as h:json.dump(result,h,indent=2);h.write('\n')
