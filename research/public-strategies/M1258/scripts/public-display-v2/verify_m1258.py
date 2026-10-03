"""Candidate-only derivation tests. No engine/importer/privateNAV/market execution."""
import argparse,json,subprocess
from copy import deepcopy
from pathlib import Path
import export_m1258 as e

def inventory(root):return {str(p.relative_to(root)):dict(bytes=p.stat().st_size,sha256=e.sha(p.read_bytes())) for p in sorted(root.rglob('*')) if p.is_file()}
def verify(repo,first,rebuild,receipt):
    require=e.require;checks=[]
    def rejected(call,label):
        try:call()
        except (ValueError,KeyError,TypeError):checks.append(label)
        else:raise AssertionError('Guard failed: '+label)
    e.export(repo,rebuild)
    one,two=inventory(first),inventory(rebuild);assert one==two and len(one)==5
    data,refs,allfiles=e.load_sources(repo);d=json.loads(data['original_detail']);s=json.loads(data['summary']);p=json.loads(data['protocol']);rules=json.loads(data['rules'])
    output=first/e.DEST
    rec=json.loads((output/'graph-record.json').read_bytes());detail=json.loads((output/'graph-detail.json').read_bytes());manifest=json.loads((output/'public-display-manifest.json').read_bytes());curve=json.loads((output/'base-nav-sampled.json').read_bytes())
    assert detail['curve']==d['curve']==curve and len(curve)==25
    assert detail['curve_meta']['total_observations']==731 and detail['curve_meta']['returned_points']==25 and detail['curve_meta']['private_daily_nav_used'] is False
    assert detail['curve_meta']['first_point_rebased'] is False and detail['curve_meta']['equity_unit']=='initial_capital_multiple'
    assert detail['metrics']['periods']==d['metrics']['periods'] and detail['metrics']['additional_native_bar_lag']==d['metrics']['additional_native_bar_lag'] and detail['metrics']['same_instrument_benchmark']==d['metrics']['same_instrument_benchmark']
    for case,key in [('fee0','0'),('fee20','20')]:assert detail['metrics']['cost_sensitivity'][key]==d['metrics']['cost_sensitivity'][case]
    assert rec['results']==s['cases'] and rec['monthly']==s['monthly'] and rec['benchmark_reference']['result']==s['cases']['buyhold']
    assert rec['research_fidelity']==detail['research_fidelity']==s['classification']=='HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED'
    assert rec['fidelity_class']==detail['fidelity_class']=='HYPOTHESIS'
    assert rec['control_configurations']==rec['new_control_runs']==detail['lab_counts']['new_control_configurations']==1
    assert rec['strategy_configurations']==detail['lab_counts']['strategy_configurations']==4
    assert detail['projection_activity']=={'new_controls':0,'new_strategy_trials':0}
    assert rec['rules']['capital']==rules['capital']==rules['benchmark']['allocation']
    assert rec['rules']['capital']['fraction']=='1' and rec['rules']['capital']['entry_fee_inclusive'] is True
    assert rec['benchmark_reference']['result']['win_rate'] is None
    assert manifest['schema_version']==e.SCHEMA and manifest['projection_profile']==rec['projection_profile']==detail['projection_profile']==e.PROFILE
    assert manifest['manifest_kind']==e.KIND and manifest['original_private_result_manifest'] is False
    assert detail['lineage']['manifest_sha256']==e.sha((output/'public-display-manifest.json').read_bytes())
    binding=detail['transport_binding'];assert len(binding)==6 and all(isinstance(v,str) for v in binding.values())
    for k,v in binding.items():assert rec['related_results'][0][k]==rec['implementations'][0][k]==v
    assert binding['origin_run_id']==detail['origin_run_id']==detail['run_id'] and binding['variant_id']==detail['variant_id']
    assert binding['protocol_sha256']==e.sha(data['protocol']) and binding['manifest_sha256']==detail['lineage']['manifest_sha256']
    assert manifest['files']['base-nav-sampled.json']==dict(bytes=(output/'base-nav-sampled.json').stat().st_size,sha256=e.sha((output/'base-nav-sampled.json').read_bytes()))
    assert set(manifest['files'])==set(refs)|{'base-nav-sampled.json'}
    assert 'private-output-manifest.json' not in json.dumps(manifest['files'])
    for name in one:
        body=(first/name).read_bytes();e.prior.screen(body)
    delivery=json.loads((first/'DELIVERY-MANIFEST.json').read_bytes())
    assert len(delivery['files'])==4 and delivery['generated_files_including_delivery']==5
    for name,pin in delivery['files'].items():assert pin==one[name]
    assert len(allfiles)==37 and sum(x['bytes'] for x in allfiles)==157863
    assert delivery['source_files']==allfiles
    for f in allfiles:
        raw=e.common.git_bytes(repo,f['path']);assert len(raw)==f['bytes'] and e.sha(raw)==f['sha256']
    # Mutation guards change in-memory fixtures only. Actual approved files stay immutable.
    def mutate(role,edit):
        changed=deepcopy(data);newrefs=deepcopy(refs);obj=json.loads(changed[role]);edit(obj);changed[role]=e.encode(obj)
        newrefs[role]['bytes']=len(changed[role]);newrefs[role]['sha256']=e.sha(changed[role])
        return changed,newrefs
    for label,role,edit in [
        ('curve_double_division','original_detail',lambda x:[p.update(equity=p['equity']/100000) for p in x['curve']]),
        ('invented_26th_point','original_detail',lambda x:x['curve'].append(deepcopy(x['curve'][-1]))),
        ('731_display_points_claim','original_detail',lambda x:x['curve_meta'].update(returned_points=731)),
        ('absolute_units_label','original_detail',lambda x:x['curve_meta'].update(equity_unit='USDT')),
        ('wrong_fee0_cost','summary',lambda x:x['cases']['fee0'].update(fee_bps=8)),
        ('wrong_daily_delay','summary',lambda x:x['cases']['delay2'].update(delay_bars=1)),
        ('null_control_winrate_to_zero','summary',lambda x:x['cases']['buyhold'].update(win_rate=0)),
        ('wrong_C0_binding','original_detail',lambda x:x['lineage'].update(C0_sha256='0'*64)),
        ('private_Library_field','original_detail',lambda x:x['limitations'].append('libfile_privateexample')),
        ('wrong_actual_control_count','summary',lambda x:x.update(new_controls=0)),
        ('research_fidelity_promoted','summary',lambda x:x.update(classification='STRICT')),
    ]:
        bad,bref=mutate(role,edit);rejected(lambda:e.project(bad,bref),label)
    # Direct finish guards verify the transport layer independently of source pin gates.
    bad=deepcopy(detail);bad['projection_profile']='NATIVE_5M_RULE_CARD_V2';rejected(lambda:e.finish(deepcopy(rec),bad,refs,e.encode(curve)),'profile_mismatch')
    bad=deepcopy(detail);bad['origin_run_id']=0;rejected(lambda:e.finish(deepcopy(rec),bad,refs,e.encode(curve)),'sixfield_nonstring_transport')
    old=e.PUB_PIN
    try:
        e.PUB_PIN=(old[0],'0'*64);rejected(lambda:e.load_sources(repo),'publication_hash_mismatch')
    finally:e.PUB_PIN=old
    bad=deepcopy(refs);bad['rules']['sha256']='0'*64;rejected(lambda:e.project(data,bad),'selected_source_hash_mismatch')
    rejected(lambda:e.export(repo,first),'immutable_output_collision')
    rejected(lambda:e.same(None,0,'null'),'null_zero_distinction')
    rejected(lambda:e.same(0,None,'zero'),'zero_null_distinction')
    for value in ['https://example.org/x?sig=secret','/workspace/private-file','Bearer secret001']:
        rejected(lambda:e.prior.screen(e.encode({'x':value})),'privacy_screen_'+value.split('/')[0])
    result=dict(status='PASS_CANDIDATE_SELF_CHECK_NOT_INDEPENDENT_APPROVAL',source_commit=e.PIN,original_publication_manifest_sha256=e.PUB_PIN[1],source_objects_checked=37,source_bytes=157863,original_C0_payloads_unchanged=19,actual_fresh_builds=2,byte_identical_files=5,candidate_files=4,outer_delivery_manifests=1,curve_points=25,metric_observations=731,original_strategy_configurations=4,original_new_controls=1,new_executions=0,new_controls=0,guard_count=len(checks),guard_checks=checks,sixfield_transport_exact=True,Graph_fidelity='HYPOTHESIS',research_fidelity='HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED',fullcash_fee_inclusive_preserved=True,null_preserved=True,private_NAV_read=False,market_requests=0,repository_writes=0,Site_operations=0,files=one)
    require(not receipt.exists(),'Receipt must be new');receipt.write_bytes(e.encode(result));print(json.dumps({k:result[k] for k in ['status','source_objects_checked','actual_fresh_builds','byte_identical_files','curve_points','metric_observations','guard_count','new_executions','new_controls']}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--lab-repo',type=Path,required=True);p.add_argument('--first',type=Path,required=True);p.add_argument('--rebuild',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args();verify(a.lab_repo,a.first,a.rebuild,a.receipt)
