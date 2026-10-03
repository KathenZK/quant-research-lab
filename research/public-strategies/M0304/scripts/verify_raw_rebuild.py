"""Independent offline source-byte to canonical reconstruction; stdlib only."""
from pathlib import Path
import argparse,csv,hashlib,io,json,zipfile
from decimal import Decimal
from datetime import datetime,timezone

HEAD=['open_time','open','high','low','close','volume','close_time','quote_volume','trade_count','taker_buy_base_volume','taker_buy_quote_volume','ignore','ts','exchange','market_type','timeframe','symbol','native_symbol','source','bar_close_ts','source_archive']
def stamp(value):
    sec,msec=divmod(int(value),1000)
    return datetime.fromtimestamp(sec,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')+f'.{msec:03d}Z'
def verify(root):
    manifest=json.loads((root/'manifest.json').read_text())
    output=io.StringIO(newline='');writer=csv.writer(output,lineterminator='\n');writer.writerow(HEAD)
    start=1701388800000;end=1735689600000;count=0;evalrows=0;zero=0;archives=[]
    for month in ['2023-12']+[f'2024-{m:02d}' for m in range(1,13)]:
        directory=root/'archives'/month;filename=f'BTCUSDT-5m-{month}.zip';archivepath=directory/filename
        zipped=archivepath.read_bytes();actual=hashlib.sha256(zipped).hexdigest();checksum=(directory/(filename+'.CHECKSUM')).read_text().split();assert checksum==[actual,filename]
        with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
            assert archive.testzip() is None and archive.namelist()==[filename[:-4]+'.csv']
            raw=archive.read(archive.namelist()[0])
        assert raw==(directory/(filename[:-4]+'.csv')).read_bytes()
        rows=list(csv.reader(io.StringIO(raw.decode(),newline='')))
        for row in rows:
            assert len(row)==12 and all(v and v.strip()==v for v in row)
            assert int(row[0])==start+300000*count and int(row[6])==int(row[0])+299999
            vals=[Decimal(row[j]) for j in [1,2,3,4,5,7,9,10]];assert all(v.is_finite() for v in vals)
            op,hi,lo,cl,vol,quote,taker,takerquote=vals
            assert 0<lo<=op<=hi and lo<=cl<=hi
            assert vol>=0 and quote>=0 and 0<=taker<=vol and 0<=takerquote<=quote
            assert lo*vol-Decimal(1).scaleb(quote.as_tuple().exponent)<=quote<=hi*vol+Decimal(1).scaleb(quote.as_tuple().exponent)
            assert lo*taker-Decimal(1).scaleb(takerquote.as_tuple().exponent)<=takerquote<=hi*taker+Decimal(1).scaleb(takerquote.as_tuple().exponent)
            assert row[8].isdigit() and (vol==0)==(int(row[8])==0)
            zero+=int(vol==0);count+=1;evalrows+=int(int(row[0])>=1704067200000)
            writer.writerow(row+[stamp(row[0]),'binance','spot','5m','BTC/USDT','BTCUSDT','binance_vision',stamp(row[6]),filename])
        archives.append({'month':month,'zip_sha256':actual,'rows':len(rows)})
    assert start+count*300000==end and count==114336 and evalrows==105408 and zero==0
    payload=output.getvalue().encode();expected=root/manifest['canonical_csv']['path'];assert payload==expected.read_bytes()
    rebuilt=root.parent/'independent-rebuilt-native12.csv'
    with rebuilt.open('xb') as f:f.write(payload)
    result={'status':'PASS_DIAGNOSTIC_ONLY','verified_at':datetime.now(timezone.utc).isoformat(),'input_rows':count,'evaluation_rows':evalrows,'zero_volume_rows':zero,'native_fields_byte_for_field_equal':True,'canonical_bytes_equal':True,'canonical_sha256':hashlib.sha256(payload).hexdigest(),'canonical_bytes':len(payload),'13_official_SHA_and_ZIP_CRC':'PASS','independent_grid_OHLCV_native_quantity_checks':'PASS','archives':archives,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'network_GETs':0,'strategy_runs':0,'PIT':False,'finality':False,'remote_recovery':False}
    with (root.parent/'independent-rebuild.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('snapshot',type=Path);verify(p.parse_args().snapshot)
