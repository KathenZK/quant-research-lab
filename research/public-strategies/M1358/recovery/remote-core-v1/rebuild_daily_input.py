"""Rebuild exact M1358 canonical bytes from already lawfully held archives. No downloads."""
import argparse,csv,hashlib,io,json,zipfile
from pathlib import Path
COLS=['open_time','open','high','low','close','volume','close_time','quote_volume','trade_count','taker_base','taker_quote','ignore']
def rebuild(protocol_path,raw,output,reference=None):
    protocol=json.loads(protocol_path.read_text());spec=protocol['input'];allrows=[];raw_files=spec['raw_files']
    assert len(raw_files)==50
    for f in raw_files:
        p=raw/f['name'];b=p.read_bytes()
        assert len(b)==f['bytes'] and hashlib.sha256(b).hexdigest()==f['sha256'],f['name']
        if p.suffix=='.zip':
            assert (raw/(p.name+'.CHECKSUM')).read_text().split()[0]==f['sha256']
            with zipfile.ZipFile(p) as z:
                assert z.testzip() is None and z.namelist()==[p.stem+'.csv']
                rows=list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())))
                assert all(len(row)==12 for row in rows);allrows.extend(rows)
    buf=io.StringIO(newline='');w=csv.writer(buf);w.writerow(COLS);w.writerows(allrows);data=buf.getvalue().encode()
    assert len(allrows)==762 and len(data)==spec['bytes']==128196 and hashlib.sha256(data).hexdigest()==spec['sha256']
    if reference is not None:assert data==reference.read_bytes()
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as f:f.write(data)
    return {'status':'PASS','canonical_bytes':len(data),'canonical_sha256':hashlib.sha256(data).hexdigest(),'rows':762,'raw_objects':50,'provider_checksums':25,'ZIP_CRCs':25,'existing_canonical_byte_comparison':reference is not None,'input_source':'explicit lawful local raw archive cache, not Git','network_requests':0,'trusted':False,'quality_status':'DIAGNOSTIC_ONLY','PIT':'NOT_PROVEN'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--protocol',type=Path,required=True);p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reference',type=Path);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
    r=rebuild(a.protocol,a.raw,a.output,a.reference)
    with a.receipt.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps(r))
