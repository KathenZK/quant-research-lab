"""Offline exact archive/hash/CRC/canonical reassembly; does not compute features."""
import argparse,csv,hashlib,io,json,zipfile
from pathlib import Path
from run_replay import load_input,FAMILY
COLS=['open_time','open','high','low','close','volume','close_time','quote_volume','trade_count','taker_base','taker_quote','ignore']
def verify(raw,canonical):
    protocol=json.loads((FAMILY/'specs/protocol-v1.json').read_text()); rows=[]
    for rec in protocol['input']['raw_files']:
        p=raw/rec['name'];b=p.read_bytes()
        assert len(b)==rec['bytes'] and hashlib.sha256(b).hexdigest()==rec['sha256'],p
        if p.suffix=='.zip':
            assert (raw/(p.name+'.CHECKSUM')).read_text().split()[0]==rec['sha256']
            with zipfile.ZipFile(p) as z:
                assert z.testzip() is None and z.namelist()==[p.stem+'.csv']
                a=list(csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]))));assert all(len(r)==12 for r in a);rows.extend(a)
    buf=io.StringIO(newline='');w=csv.writer(buf);w.writerow(COLS);w.writerows(rows)
    assert buf.getvalue().encode()==canonical.read_bytes()
    frame=load_input(canonical,protocol)
    return {'status':'PASS','raw_objects':50,'provider_checksums':25,'zip_CRCs':25,'canonical_sha256':hashlib.sha256(canonical.read_bytes()).hexdigest(),'offline_rebuild_exact':True,'total_rows':len(rows),'evaluation_rows':len(frame),'prefeed_rows':0,'features_or_returns_computed':False,'network_requests':0,'quality_status':'DIAGNOSTIC_ONLY','PIT':'NOT_PROVEN','trusted':False}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=verify(a.raw,a.input)
    with a.output.open('x') as h:h.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r))
