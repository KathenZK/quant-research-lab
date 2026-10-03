#!/usr/bin/env python3
"""Reconstruct private third-party source; never write it into the public package."""
import argparse,pathlib,urllib.request,json,hashlib
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=False)
R=pathlib.Path(__file__).resolve().parents[1];s=json.loads((R/'specs/source-manifest.json').read_text());sources=[('hlhb.py',s['strategy_source']),('freqtrade-interface.py',s['reference_framework'])]
for name,item in sources:
    body=urllib.request.urlopen(item['url'],timeout=30).read();assert hashlib.sha256(body).hexdigest()==item['sha256'];assert len(body)==item['bytes'];(out/name).write_bytes(body)
print('Verified pinned source files only; no market-data requests')
