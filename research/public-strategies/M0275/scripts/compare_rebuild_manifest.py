#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare new rebuild to frozen light manifest (not --expected-manifest format)."""
import argparse,hashlib,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--snapshot',required=True);p.add_argument('--output',required=True);a=p.parse_args();base=pathlib.Path(a.snapshot)
    light=json.loads((ROOT/'specs/input-manifest-inherited.json').read_text());actual=json.loads((base/'manifest.json').read_text())
    for key in ['timeframe','schema','builder_sha256']:assert light[key]==actual[key],key
    assert actual['builder_sha256']==sha(ROOT/'scripts/rebuild_official_bars.py')
    assert len(actual['archives'])==len(light['archives'])==25
    for x,y in zip(actual['archives'],light['archives']):
        for kind in ['zip','checksum','csv']:
            assert x[kind]['bytes']==y[kind]['bytes'] and x[kind]['sha256']==y[kind]['sha256']
            raw=base/x[kind]['path'];assert raw.stat().st_size==x[kind]['bytes'] and sha(raw)==x[kind]['sha256']
    for key in ['sha256','bytes','rows']:assert actual['canonical_csv'][key]==light['canonical_csv'][key]
    assert sha(base/actual['canonical_csv']['path'])==light['canonical_csv']['sha256']
    result={'status':'PASS_LIGHT_MANIFEST_AND_BUILDER_MATCH','snapshot_manifest_sha256':sha(base/'manifest.json'),'light_manifest_sha256':sha(ROOT/'specs/input-manifest-inherited.json'),'builder_sha256':actual['builder_sha256'],'source_objects_checked':75,'canonical_sha256':light['canonical_csv']['sha256'],'trusted':False}
    with open(a.output,'x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
