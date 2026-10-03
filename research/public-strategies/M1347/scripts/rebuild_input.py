"""Offline normalization derived from M1358 remote-core rebuild, no strategy import."""
import argparse,csv,hashlib,io,json,zipfile
from pathlib import Path
from kernel_loader import load,FAMILY
load_input=load('engine').load_input
COLS=['open_time','open','high','low','close','volume','close_time','quote_volume','trade_count','taker_base','taker_quote','ignore']
def rebuild(raw,canonical,output=None):
    protocol=json.loads((FAMILY/'specs/protocol-v1.json').read_text());s=protocol['input'];rows=[]
    assert len(s['raw_files'])==50
    for rec in s['raw_files']:
        p=raw/rec['name'];b=p.read_bytes();assert len(b)==rec['bytes'] and hashlib.sha256(b).hexdigest()==rec['sha256'],p.name
        if p.suffix=='.zip':
            assert (raw/(p.name+'.CHECKSUM')).read_text().split()[0]==rec['sha256']
            with zipfile.ZipFile(p) as z:
                assert z.testzip() is None and z.namelist()==[p.stem+'.csv']
                a=list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())));assert all(len(x)==12 for x in a);rows.extend(a)
    b=io.StringIO(newline='');w=csv.writer(b);w.writerow(COLS);w.writerows(rows);data=b.getvalue().encode()
    assert len(data)==s['bytes'] and hashlib.sha256(data).hexdigest()==s['sha256']
    if canonical is not None:assert data==canonical.read_bytes();load_input(canonical,protocol)
    if output is not None:
        with output.open('xb') as h:h.write(data)
        load_input(output,protocol)
    return dict(status='PASS',raw_objects=50,ZIP_CRCs=25,provider_checksums=25,canonical_sha256=s['sha256'],canonical_bytes=len(data),rows=len(rows),warmup_rows=31,evaluation_rows=731,offline_rebuild_exact=True,features_or_returns_computed=False,network_requests=0,quality_status='DIAGNOSTIC_ONLY',trusted=False,PIT='NOT_PROVEN')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--reference',type=Path);p.add_argument('--output',type=Path);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args();r=rebuild(a.raw,a.reference,a.output)
    with a.receipt.open('x') as h:h.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r))
