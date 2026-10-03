import json, argparse
from pathlib import Path
from copy import deepcopy
import export_dot009 as e

def run(repo,first,rebuild,receipt):
    e.require(not receipt.exists(),'Receipt exists');e.export(repo,rebuild)
    def fs(p):return {str(f.relative_to(p)):f.read_bytes() for f in p.rglob('*') if f.is_file()}
    a,b=fs(first),fs(rebuild);assert a==b and len(a)==13
    checks=[]
    def reject(fn,label):
        try:fn()
        except (ValueError,TypeError,KeyError,IndexError):checks.append(label)
        else:raise AssertionError(label)
    for rid in e.CONTRACTS:
        data,refs=e.load(repo,rid);o=e.project(rid,data,refs);d=json.loads(o['graph-detail.json']);r=json.loads(o['graph-record.json']);old=json.loads(data['original_detail'])
        assert d['curve']==old['curve'] and len(d['curve'])==25 and len(r['catalog_fields'])==11
        m=d['metrics']
        for periods in [m['periods'],m['same_instrument_benchmark'],m['additional_native_bar_lag'],*m['cost_sensitivity'].values()]:
            assert periods['full']==periods['2023-2024'] and periods['full']['observations']==731
        assert set(m['cost_sensitivity'])=={'0','20'}
        if rid=='M1270':assert m['additional_native_bar_lag']['full']['sharpe'] is None
        for label,role,edit in [
            ('identity','summary',lambda x:x.update(id='M9999')),
            ('new_control','summary',lambda x:x.update(new_controls=1)),
            ('promote','summary',lambda x:x.update(classification='STRICT')),
            ('curve_rescale','curve',lambda x:[p.update(equity=p['equity']/100000) for p in x]),
            ('curve731','original_detail',lambda x:x['curve_meta'].update(point_count=731)),
            ('period_missing','original_detail',lambda x:x['metrics']['periods'].pop('2023-2024')),
            ('period_null','original_detail',lambda x:x['metrics']['periods'].update({'2023-2024':None})),
            ('sharpe_type','original_detail',lambda x:x['metrics']['additional_native_bar_lag']['2023-2024'].update(sharpe=False)),
            ('fee','summary',lambda x:x['cases'][1].update(fee_bps=8)),
            ('slippage','summary',lambda x:x['cases'][0].update(slippage_bps=0)),
            ('catalogdrop','catalog',lambda x:x['fields'].pop('规则')),
            ('capital95','rules',lambda x:x['capital'].update(fraction='0.95')),
        ]:
            bad=deepcopy(data);x=json.loads(bad[role]);edit(x);bad[role]=e.encode(x);reject(lambda:e.validate(rid,bad),rid+':'+label)
        bad=deepcopy(refs);bad['summary']['sha256']='0'*64;reject(lambda:e.project(rid,data,bad),rid+':rolehash')
        bad=deepcopy(refs);bad['summary']['path']='../private';reject(lambda:e.project(rid,data,bad),rid+':rolepath')
    reject(lambda:e.export(repo,first),'immutableoutput')
    for path in ['../outside','/workspace/private','a/../b']:
        reject(lambda:e.common.safe_path(path),'path'+path)
    for word in ['libfile_fake','/workspace/private','Bearer privatefixture']:
        reject(lambda:e.prior.screen(e.encode({'x':word})),'privacyfixture')
    delivery=json.loads(a['DELIVERY-MANIFEST.json']);assert len(delivery['files'])==12
    for p,x in delivery['files'].items():assert x=={'bytes':len(a[p]),'sha256':e.sha(a[p])}
    receipt.write_bytes(e.encode({'status':'PASS_SELF_CHECK_NOT_INDEPENDENT','fresh_files_byte_equal':13,'candidate_files':12,'candidate_bytes':sum(len(v) for k,v in a.items() if k!='DELIVERY-MANIFEST.json'),'guard_count':len(checks),'guards':checks,'source_roles':33,'unique_selected_source_paths':len({x['path'] for rs in delivery['source_artifacts'].values() for x in rs.values()}),'original_strategy_configurations':12,'new_strategy_trials':0,'new_controls':0,'unique_reused_controls':['M1258'],'points_per_id':25,'observations_per_id':731,'private_outputs_read':False,'files':{p:{'bytes':len(v),'sha256':e.sha(v)} for p,v in a.items()}}))
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ['lab-repo','first','rebuild','receipt']:p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();run(a.lab_repo,a.first,a.rebuild,a.receipt)
