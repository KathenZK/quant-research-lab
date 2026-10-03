#!/usr/bin/env python3
"""Materialize exact public source bytes to a NEW private directory.
No market-data download. Source code permissions do not authorize market data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads((root/'sources/manifest.json').read_text())
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    receipts=[]
    for item in manifest['retrieval_files']:
        try:
            with urllib.request.urlopen(item['url'],timeout=60) as res:b=res.read()
        except Exception as e:
            raise SystemExit('UNAVAILABLE: '+item['url']+' '+str(e))
        h=hashlib.sha256(b).hexdigest()
        if h!=item['sha256']:raise SystemExit('MISMATCH: '+item['url']+' '+h)
        (out/item['filename']).write_bytes(b)
        receipts.append({'filename':item['filename'],'sha256':h,'bytes':len(b),'status':'VERIFIED'})
    (out/'source-retrieval-receipt.json').write_text(json.dumps(receipts,indent=2)+'\n')
    print('VERIFIED',len(receipts),'fixed source files')
if __name__=='__main__':main()
