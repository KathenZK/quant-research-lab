#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Retrieve immutable public software references. Not a market-data downloader.
An existing file is never replaced: mismatching bytes fail closed.
"""
import argparse,hashlib,json,pathlib,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
def fetch(out):
    manifest=json.loads((ROOT/'specs/source-manifest.json').read_text());out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True);items=[]
    for item in manifest['files']:
        p=out/item['filename']
        if p.exists():b=p.read_bytes();status='EXISTING_VERIFIED'
        else:
            with urllib.request.urlopen(item['raw_url'],timeout=60) as response:b=response.read()
            status='FETCHED_VERIFIED'
        if hashlib.sha256(b).hexdigest()!=item['sha256'] or len(b)!=item['bytes']:raise ValueError('MISMATCH '+item['filename'])
        if not p.exists():p.write_bytes(b)
        items.append({'file':item['filename'],'status':status,'sha256':item['sha256']})
    return items
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default=str(ROOT/'sources'));a=p.parse_args();print(json.dumps(fetch(a.output),indent=2))
