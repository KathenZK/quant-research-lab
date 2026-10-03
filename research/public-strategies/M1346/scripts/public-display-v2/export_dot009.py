"""Fixed approved Git light objects -> private display candidates. No strategy execution."""
import argparse,calendar,json,shutil
from copy import deepcopy
from pathlib import Path
import common_public_display as common
import frozen_export as prior
PIN='08e6ab4a49a808f53f06e509f06cb2c453f007d5'
LOCK='4379e8c4897b9ae8d3eeaaf3a467549a71abd79600026b2da463a7f682b3d9f1'
PROFILE='DAILY_SAMPLED_APPROVED_DETAIL_V1'
KIND='PUBLIC_DERIVED_DISPLAY_MANIFEST'
FIDELITY='HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED'
EXECUTION='ADAPTED_EXECUTION_PROXY'
CONTRACTS={'M1346':'CATALOG_CLOSE25_LEVEL_FULLCASH_REUSED_CONTROL_V1','M1349':'CATALOG_ROC25_NEG10_HOLD25_FULLCASH_REUSED_CONTROL_V1','M1270':'CATALOG_UTC_SUNDAY_MONDAY_RAW_CANCEL_FULLCASH_REUSED_CONTROL_V1'}
SPECIAL={'M1346':[],'M1349':['holding_counter','source_warning'],'M1270':['calendar_execution']}
require,sha,encode=common.require,common.sha,common.encode

def load(repo,rid):
    require(rid in CONTRACTS,'Unapproved ID')
    for name,digest in [('common_public_display.py','f5a8536676f1575f55adcf3b286ba92c198a01c070399250fbf933f8937c9c13'),('frozen_export.py','266c93afa0829b0e504b2e008e1ed0ae1b43a4b5fd2869ffaeb047e41fba3128')]:
        require(sha(Path(__file__).with_name(name).read_bytes())==digest,'Helper changed')
    lock=Path(__file__).with_name('selected-public-source-lock.json').read_bytes();require(sha(lock)==LOCK,'Source lock changed')
    refs=json.loads(lock)['records'][rid];common.PIN=PIN;data={}
    for role,ref in refs.items():
        p=common.safe_path(ref['path']);require('private-output' not in p and '/expected/' not in p,'Private inventory prohibited')
        raw=common.git_bytes(repo,p);require(len(raw)==ref['bytes'] and sha(raw)==ref['sha256'],'Source bytes mismatch')
        require(ref['url']==f'https://github.com/KathenZK/quant-research-lab/blob/{PIN}/{p}','Source URL mismatch');data[role]=raw
    return data,refs

def same(a,b,label):
    require(type(a) is type(b) and a==b,label)

def match(view,case):
    for k in ['total_return','cagr','max_drawdown','sharpe_zero_cash','observations','final_equity']:same(view[k],case[k],'Metric/type mismatch '+k)
    same(view['sharpe'],case['sharpe_zero_cash'],'Sharpe/null mismatch')
    require(view['start']=='2023-01-01' and view['end']=='2024-12-31' and view['annualization']==365,'Wrong period')

def validate(rid,data):
    v={k:json.loads(b) for k,b in data.items()};s,d,r,w,c,cat,ctl,proj,stats,cfg=[v[k] for k in ['summary','original_detail','original_record','rules','C0','catalog','control_reference','control_projection','statistics','cases']]
    require(s['id']==d['id']==r['id']==w['id']==cat['fields']['id']==rid,'ID mismatch')
    require(len(cat['fields'])==11 and r['audit']==cat['fields'],'Catalog11 mismatch')
    require(s['classification']==c['classification']==FIDELITY and s['execution_class']==c['execution_class']==EXECUTION,'Fidelity mismatch')
    require(d['fidelity_class']=='HYPOTHESIS' and d['audit']['original_runtime_equivalence'] is False and d['audit']['trusted'] is False,'Quality promotion')
    require(s['strategy_configurations']==4 and s['new_controls']==c['new_controls']==s['strict_reproductions']==0,'Trial count mismatch')
    require(s['C0_sha256']==d['lineage']['C0_sha256']==sha(data['C0']) and rid in c['strategy_ids'],'C0 mismatch')
    pins={x['path']:x for x in c['pins']}
    for role,path in [('rules',f'frozen/{rid}-root-frozen-rules.json'),('catalog',f'frozen/{rid}-catalog-original-fields.json'),('control_reference','frozen/buyhold-reference-v1.json'),('control_projection','frozen/reused-buyhold-projection-v1.json'),('statistics','frozen/statistics-v1.json'),('cases','frozen/cases-v1.json')]:
        require(pins[path]['sha256']==sha(data[role]) and pins[path]['bytes']==len(data[role]),'Selected C0 pin mismatch')
    require(s['input_sha256']==c['input_sha256']==w['input']['sha256']=='48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5','Input mismatch')
    require(w['capital']['fraction']=='1' and w['capital']['entry_fee_inclusive'] is True and w['capital']['initial_cash']=='100000','Fullcash changed')
    require(sha(data['control_reference'])=='ea4fb4687cffe69b7ee877312e19ec49b263bf5d21705d0dcfa2e791c24be00a','Control pin mismatch')
    require(ctl['id']=='M1258' and ctl['allocation']=='100% fee-inclusive' and ctl['fee_bps_each_side']==8 and ctl['slippage_bps_each_side']==2 and ctl['bars']==731,'Control wrong')
    require(s['benchmark_reuse']==proj and proj['reference_sha256']==sha(data['control_reference']) and proj['new_controls']==0,'Control projection mismatch')
    cases={x['case']:x for x in s['cases']};require(len(s['cases'])==len(cases)==4 and set(cases)=={'base','fee0','fee20','delay2'},'Case set wrong')
    require(set(d['metrics']['cost_sensitivity'])=={'fee0','fee20'},'Cost keys changed')
    for name,fee,lag in [('base',8,1),('fee0',0,1),('fee20',20,1),('delay2',8,2)]:
        x=cases[name];require(x['fee_bps']==fee and x['slippage_bps']==2 and x['delay_bars']==lag and x['observations']==731,'Cost/lag/count wrong')
        p=d['metrics']['periods'] if name=='base' else d['metrics']['additional_native_bar_lag'] if name=='delay2' else d['metrics']['cost_sensitivity'][name]
        require(set(p)=={'2023-2024'},'Missing/unexpected period');match(p['2023-2024'],x)
    match(d['metrics']['same_instrument_benchmark']['2023-2024'],proj['metrics'])
    dates=['2023-01-01']+[f'{y}-{m:02d}-{calendar.monthrange(y,m)[1]}' for y in [2023,2024] for m in range(1,13)]
    require(d['curve']==v['curve'] and [p['date'] for p in v['curve']]==dates,'Curve changed')
    require(d['curve_meta']['point_count']==25 and d['curve_meta']['source_observations']==731 and d['curve_meta']['normalized_to_initial']==100000,'Curve metadata wrong')
    require(v['curve'][0]['equity']==1.0,'Initial point rescaled')
    require(abs(v['curve'][-1]['equity']-cases['base']['final_equity']/100000)<1e-12,'Curve rescaled')
    if rid=='M1270':
        x=cases['delay2'];require(x['fills']==0 and x['final_equity']==100000.0 and x['total_return']==0.0 and x['sharpe_zero_cash'] is None,'Lag2 allcash changed')
    if rid=='M1349':require(s['execution_policy']=={'max_completed_closes':25},'Holding timer mismatch')
    return v,cases

def project(rid,data,refs):
    lock=Path(__file__).with_name('selected-public-source-lock.json').read_bytes()
    require(sha(lock)==LOCK and refs==json.loads(lock)['records'][rid],'Source roles/hash mismatch')
    require(set(data)==set(refs),'Role set mismatch')
    for role,body in data.items():
        require(sha(body)==refs[role]['sha256'] and len(body)==refs[role]['bytes'],'Selected bytes mismatch')
    v,cases=validate(rid,data);s=v['summary'];w=v['rules'];d=deepcopy(v['original_detail']);r=deepcopy(v['original_record'])
    rules={k:deepcopy(w[k]) for k in ['indicator','entry','exit','capital','execution','cold_start','cost_cases','valuation','statistics','stop_or_roi','known_halt']+SPECIAL[rid]}
    d.update(projection_profile=PROFILE,source_contract=CONTRACTS[rid],research_fidelity=FIDELITY,execution_class=EXECUTION,implementation_fidelity=EXECUTION,manifest_kind=KIND,projection_status='STAGED_NOT_IMPORTED')
    m=d['metrics'];m['cost_sensitivity']={str(fee):deepcopy(m['cost_sensitivity'][name]) for name,fee in [('fee0',0),('fee20',20)]}
    for p in [m['periods'],m['same_instrument_benchmark'],m['additional_native_bar_lag'],*m['cost_sensitivity'].values()]:
        require(set(p)=={'2023-2024'} and isinstance(p['2023-2024'],dict),'Missing/null period cannot alias');p['full']=deepcopy(p['2023-2024'])
    m.update(source_period_aliases={'2023-2024':'full'},source_cost_key_aliases={'fee0':'0','fee20':'20'},additional_lag_unit='day')
    d['curve_meta'].update(returned_points=25,observations=731,total_observations=731,equity_unit='initial_capital_multiple',drawdown_unit='fraction',denominator=100000,first_point_rebased=False,full_daily_curve_published=False,interpolation_claim=False,private_daily_nav_used=False)
    d['spec']['params']={'rules':rules,'metric_conventions':w['statistics']}
    d['limitations'] += ['Only25 original normalized samples;731 counts metric observations. No interpolation or metric recalculation.', 'One actual M1258 base8bps+2bps control reused across cases; no fee0/20 matched-cost controls exist in this projection.','Projection runs0 strategies/controls. No active entity/revision bound; not Site activation.']
    r.update(fidelity_class='HYPOTHESIS',research_fidelity=FIDELITY,execution_class=EXECUTION,projection_profile=PROFILE,source_contract=CONTRACTS[rid],manifest_kind=KIND,status='tested_hypothesis_only',projection_status='STAGED_NOT_IMPORTED',definition_revision_bound=False,catalog_fields=deepcopy(v['catalog']['fields']),rules=rules,results=deepcopy(cases),configuration_runs=4,strategy_configurations=4,new_control_runs=0,control_configurations=0,reused_control_configurations=1,benchmark_reference={'kind':'REUSED_ACCEPTED_M1258_BASE_CONTROL','id':'M1258','reference_sha256':sha(data['control_reference']),'projection':deepcopy(v['control_projection']),'matched_cost_controls_available':False},monthly=None,monthly_status='STRATEGY_MONTHLY_VALUES_NOT_IN_SELECTED_PUBLIC_SUMMARY',limitations=deepcopy(d['limitations']),economic_basis={'hypothesis':w['economic_hypothesis'],'author_verified':False})
    curve=encode(v['curve']);manifest={'schema_version':'quantgraph-public-derived-display-manifest/v2','manifest_kind':KIND,'projection_profile':PROFILE,'source_contract':CONTRACTS[rid],'id':rid,'origin_run_id':d['origin_run_id'],'variant_id':d['variant_id'],'origin_lab_commit':PIN,'original_private_result_manifest':False,'original_results_modified':False,'source_artifacts':refs,'source_lock_sha256':LOCK,'source_lock_kind':'SELECTED_APPROVED_GIT_SOURCE_LOCK_NOT_PUBLICATION_MANIFEST','files':{**refs,'base-nav-sampled.json':{'bytes':len(curve),'sha256':sha(curve)}},'excluded_from_self_hash':['public-display-manifest.json','graph-record.json','graph-detail.json'],'curve_contract':deepcopy(d['curve_meta'])}
    mr=encode(manifest);old=deepcopy(d['lineage']);d['lineage']={'manifest_kind':KIND,'manifest_sha256':sha(mr),'source_display_manifest_sha256':sha(mr),'C0_sha256':sha(data['C0']),'protocol_sha256':sha(data['rules']),'protocol_hash_role':'FROZEN_RULE_CONTRACT_NOT_INVENTED_PROTOCOL_FILE','lab_commit':PIN,'source_artifacts':refs,'source_lineage':old,'definition_revision_bound':False}
    binding={k:d[k] for k in ['origin_run_id','variant_id','fidelity_class','execution_class']};binding.update(protocol_sha256=sha(data['rules']),manifest_sha256=sha(mr));rr=dict(binding,manifest_kind=KIND)
    r.update(source_artifacts=refs,related_results=[rr],implementations=[dict(rr,family=d['family'])]);d.update(transport_binding=binding,lab_counts={'strategy_ids':1,'strategy_configurations':4,'new_control_configurations':0,'reused_control_configurations':1,'strict_reproductions':0},projection_activity={'new_strategy_trials':0,'new_controls':0})
    out={'graph-record.json':encode(r),'graph-detail.json':encode(d),'base-nav-sampled.json':curve,'public-display-manifest.json':mr}
    for raw in out.values():prior.screen(raw)
    return out

def export(repo,output):
    require(not output.exists(),'Immutable output exists');files={};sources={}
    for rid in CONTRACTS:
        data,refs=load(repo,rid);sources[rid]=refs
        for name,body in project(rid,data,refs).items():files[f'research/public-strategies/{rid}/artifacts/20261003-public-display-prep/{name}']=body
    delivery={'schema_version':'dot009-public-display-preparation/v1','source_commit':PIN,'source_lock_sha256':LOCK,'status':'STAGED_NOT_PUBLISHED_PENDING_INDEPENDENT_REVIEW','source_artifacts':sources,'original_strategy_configurations':12,'new_strategy_trials':0,'new_controls':0,'unique_reused_control_ids':['M1258'],'files':{p:{'bytes':len(b),'sha256':sha(b)} for p,b in sorted(files.items())}}
    files['DELIVERY-MANIFEST.json']=encode(delivery);require(shutil.disk_usage(output.parent).free>5*1024**3+sum(map(len,files.values())),'5GiB reserve required');output.mkdir(mode=0o700)
    for p,b in files.items():
        f=output/p;f.parent.mkdir(parents=True,exist_ok=True)
        with f.open('xb') as stream:stream.write(b)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--lab-repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();export(a.lab_repo,a.output)
