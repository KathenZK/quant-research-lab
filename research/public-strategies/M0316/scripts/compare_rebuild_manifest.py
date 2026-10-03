#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline read-only comparison of a full snapshot to the pinned LIGHT manifest.
The light manifest is intentionally NOT builder --expected-manifest format.
No builder/engine import, network request, or return computation is performed.
"""
import argparse,ast,csv,datetime,hashlib,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def inside(base,rel):
    p=(base/rel).resolve();assert p.is_relative_to(base.resolve()),'manifest path escapes snapshot';assert p.is_file();return p
def compare(snapshot,light_path,builder_path):
    base=pathlib.Path(snapshot);lp=pathlib.Path(light_path);bp=pathlib.Path(builder_path)
    light=json.loads(lp.read_text());actual=json.loads((base/'manifest.json').read_text())
    assignments={node.targets[0].id:node.value for node in ast.parse(bp.read_text()).body if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name)}
    protocol=ast.literal_eval(assignments['VERSION']);schema=ast.literal_eval(assignments['NATIVE'])+ast.literal_eval(assignments['ADDED'])
    assert actual['protocol']==protocol
    assert light['timeframe']==actual['timeframe']=='4h'
    assert light['schema']==actual['schema']==schema
    assert light['builder_sha256']==actual['builder_sha256']==sha(bp)
    for key in ['start_utc','end_exclusive_utc','identity']:assert actual[key]==light[key],key
    assert actual['trusted'] is False and light['trusted'] is False
    assert light['start_utc']=='2022-12-01T00:00:00Z' and light['end_exclusive_utc']=='2025-01-01T00:00:00Z'
    expected_months=['2022-12']+[f'{y}-{m:02}' for y in [2023,2024] for m in range(1,13)]
    assert [a['month'] for a in light['archives']]==expected_months
    assert [a['month'] for a in actual['archives']]==expected_months
    assert len(set(expected_months))==len(actual['archives'])==len(light['archives'])==25
    objects=[]
    for old,new in zip(light['archives'],actual['archives']):
        assert old['month']==new['month']
        for kind in ['zip','checksum','csv']:
            for key in ['bytes','sha256']:assert old[kind][key]==new[kind][key],(old['month'],kind,key)
            file=inside(base,new[kind]['path']);assert file.stat().st_size==old[kind]['bytes'];assert sha(file)==old[kind]['sha256']
            objects.append({'month':old['month'],'kind':kind,'path':new[kind]['path'],'bytes':file.stat().st_size,'sha256':sha(file)})
    for key in ['sha256','bytes','rows']:assert actual['canonical_csv'][key]==light['canonical_csv'][key]
    can=inside(base,actual['canonical_csv']['path']);assert sha(can)==light['canonical_csv']['sha256'];assert can.stat().st_size==light['canonical_csv']['bytes']==1298564
    with can.open(newline='') as f:
        reader=csv.reader(f);assert next(reader)==schema;rows=sum(1 for _ in reader)
    assert rows==light['canonical_csv']['rows']==4572
    return {'status':'PASS_OFFLINE_LIGHT_MANIFEST_AND_FROZEN_BUILDER','id':'M0316','snapshot_manifest_sha256':sha(base/'manifest.json'),'light_manifest_sha256':sha(lp),'light_has_protocol':'protocol' in light,'full_protocol_verified_against_builder_AST':protocol,'builder_sha256':sha(bp),'source_objects_checked':len(objects),'objects':objects,'canonical':{'sha256':sha(can),'bytes':can.stat().st_size,'rows':rows},'timeframe':'4h','schema_verified':True,'scope_identity_verified':True,'trusted':False,'new_market_requests':0,'returns_computed':False,'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'comparison_script_sha256':sha(__file__)}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',required=True);p.add_argument('--light-manifest',default=str(ROOT/'specs/input-manifest-inherited.json'));p.add_argument('--builder',default=str(ROOT/'scripts/rebuild_official_bars.py'));p.add_argument('--output',required=True);a=p.parse_args();result=compare(a.snapshot,a.light_manifest,a.builder)
    with open(a.output,'x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='objects'},indent=2))
