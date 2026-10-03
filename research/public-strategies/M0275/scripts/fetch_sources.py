#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Retrieve pinned strategy/reference source into a new private directory.
Never bypasses HTTP/security errors; never stores full source in public artifacts.
"""
import argparse,hashlib,json,pathlib,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--target',required=True);p.add_argument('--references',action='store_true');a=p.parse_args();out=pathlib.Path(a.target);out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((ROOT/'specs/source-manifest.json').read_text());items=[manifest['strategy_source']]
    if a.references:items.extend(x for x in manifest['reference_only_sources'] if x['filename'].endswith('.py'))
    receipts=[]
    for item in items:
        dst=out/item['filename'];partial=dst.with_suffix(dst.suffix+'.partial')
        with urllib.request.urlopen(item['url'],timeout=60) as r:
            body=r.read();receipt={'url':item['url'],'status':r.status,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
        partial.write_bytes(body)
        if len(body)!=item['bytes'] or receipt['sha256']!=item['sha256']:raise ValueError('Pinned source differs; .partial retained, no substitution')
        partial.rename(dst);receipts.append(receipt)
    (out/'receipt.json').write_text(json.dumps(receipts,indent=2)+'\n');print(json.dumps(receipts,indent=2))
if __name__=='__main__':main()
