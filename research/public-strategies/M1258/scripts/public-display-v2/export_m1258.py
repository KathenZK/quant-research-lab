"""M1258-only, approved public detail -> display v2. Offline; no private NAV reads."""
import argparse,calendar,json,math,shutil
from copy import deepcopy
from pathlib import Path
import common_public_display as common
import frozen_export as prior
PIN='2a2e33e0de2b4897d6ccb460e72dcb5e73aa4153'
RID='M1258';PROFILE='DAILY_SAMPLED_APPROVED_DETAIL_V1'
SCHEMA='quantgraph-public-derived-display-manifest/v2';KIND='PUBLIC_DERIVED_DISPLAY_MANIFEST'
PUB_PIN=(6826,'a6a38fc7270c56741c756dcd1219d534e51bf1fe89ac5f59067da0c44a360d81')
PREFIX='research/public-strategies/M1258/'
BASE='artifacts/20261003-catalog-v1/'
DEST=PREFIX+'artifacts/20261003-public-display-prep/'
ROLES=dict(summary=BASE+'summary.json',original_detail=BASE+'graph-detail.json',original_record=BASE+'graph-record.json',protocol='specs/protocol-v1.json',C0='specs/C0-v1.json',rules='source/root-frozen-rules.json',source_card='source/sourcecard.safe.json',catalog_fields='source/catalog-original-fields.json')
require,sha,encode=common.require,common.sha,common.encode
common.PIN=PIN

def code_gate():
    for name,expected in [('common_public_display.py','f5a8536676f1575f55adcf3b286ba92c198a01c070399250fbf933f8937c9c13'),('frozen_export.py','266c93afa0829b0e504b2e008e1ed0ae1b43a4b5fd2869ffaeb047e41fba3128')]:
        require(sha(Path(__file__).with_name(name).read_bytes())==expected,'Frozen helper altered')

def load_sources(repo):
    code_gate();common.PIN=PIN
    raw=common.git_bytes(repo,PREFIX+'publication-manifest.json')
    require((len(raw),sha(raw))==PUB_PIN,'Publication pin mismatch')
    pub=json.loads(raw);require(pub['id']==RID and pub['payload_count']==36,'Publication identity/count mismatch')
    data={'publication_manifest':raw};refs={'publication_manifest':common.source_ref(PREFIX+'publication-manifest.json',raw)}
    inventory=[refs['publication_manifest']];allowed={}
    for item in pub['files']:
        rel=common.safe_path(item['path']);require(rel not in allowed,'Duplicate source path')
        body=common.git_bytes(repo,PREFIX+rel)
        require(len(body)==item['bytes'] and sha(body)==item['sha256'],'Public source bytes mismatch')
        allowed[rel]=body;inventory.append(common.source_ref(PREFIX+rel,body))
    require(len(inventory)==37 and sum(x['bytes'] for x in inventory)==157863,'Exact37 public inventory mismatch')
    # Verify all original frozen payloads against their approved public bytes.
    c0=json.loads(allowed[ROLES['C0']])
    require(len(c0['files'])==19,'C0 count mismatch')
    for item in c0['files']:
        body=allowed[common.safe_path(item['path'])]
        require((len(body),sha(body))==(item['bytes'],item['sha256']),'Original C0 payload changed')
    for role,rel in ROLES.items():
        require(rel in allowed,'Selected source outside publication allowlist')
        data[role]=allowed[rel];refs[role]=common.source_ref(PREFIX+rel,allowed[rel])
    # private-output-manifest is verified as an opaque public object above only.
    # Do not parse its contents, dereference paths or use private result payloads.
    return data,refs,inventory

def same(a,b,message):
    if a is None or b is None:require(a is None and b is None,message+' (null changed)')
    else:require(type(a)==type(b) and a==b,message)

def metric_match(view,case):
    for key in ['total_return','cagr','max_drawdown','sharpe_zero_cash','observations','final_equity']:
        same(view[key],case[key],'Source metric changed: '+key)
    same(view['sharpe'],case['sharpe_zero_cash'],'Sharpe alias changed')
    require(view['annualization']==365 and view['start']=='2023-01-01' and view['end']=='2024-12-31','Window/annualization changed')

def project(data,refs):
    for role,body in data.items():
        require(role in refs and (len(body),sha(body))==(refs[role]['bytes'],refs[role]['sha256']),'Selected source reference mismatch')
    s,p,c,d,r,rules,source,catalog=[json.loads(data[k]) for k in ['summary','protocol','C0','original_detail','original_record','rules','source_card','catalog_fields']]
    require(s['id']==p['id']==c['id']==d['id']==r['id']==rules['id']==source['id']==catalog['fields']['id']==RID,'ID mismatch')
    require(len(catalog['fields'])==11,'Original11fields mismatch')
    fidelity='HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED'
    require(s['classification']==p['classification']==source['fidelity']==fidelity,'Research hypothesis changed')
    require(d['fidelity_class']==r['implementations'][0]['fidelity_class']=='HYPOTHESIS','Graph fidelity changed')
    require(s['execution']==p['execution']=='ADAPTED_EXECUTION_PROXY' and source['source_verified'] is False,'Execution/source boundary changed')
    require(s['strict_reproductions']==p['strict_reproductions']==c['strict_reproductions']==0,'Strict classification changed')
    require(s['source_commit']==d['lineage']['source_commit']=='783cf6ed8962aa782667f0b193d93b187716dcbc','Execution source commit mismatch')
    require(s['C0_sha256']==d['lineage']['C0_sha256']==sha(data['C0']),'C0 pin mismatch')
    require(p['source_rules']['sha256']==sha(data['rules']),'Root rules pin mismatch')
    frozen={x['path']:x for x in c['files']}
    for role in ['protocol','rules','source_card','catalog_fields']:
        require(frozen[ROLES[role]]['sha256']==sha(data[role]),'C0 selected rule binding mismatch')
    require(p['input']['sha256']==s['input_sha256']==d['lineage']['input_sha256']==c['canonical_sha256']=='48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5','Input pin mismatch')
    require(s['strategy_configurations']==c['planned_strategy_configurations']==r['configuration_runs']==4,'Strategy count mismatch')
    require(s['new_controls']==c['planned_new_controls']==r['new_control_runs']==1,'Actual new fullcash control count mismatch')
    require(set(s['cases'])=={'base','fee0','fee20','delay2','buyhold'},'Unexpected configuration')
    capital=rules['capital']
    require(capital['fraction']=='1' and capital['entry_fee_inclusive'] is True and capital['initial_cash']=='100000','Fullcash allocation altered')
    require(capital['Decimal_precision']==50 and capital['rounding']=='ROUND_HALF_EVEN','Decimal arithmetic altered')
    require(capital==rules['benchmark']['allocation'],'Benchmark allocation not matching strategy')
    require(p['initial_cash']=='100000' and d['metrics']['capital_state']['initial_cash_usdt']==100000,'Unit denominator changed')
    require(rules['benchmark']['fee_bps']==8 and rules['benchmark']['slippage_bps']==2 and rules['benchmark']['new_control_configurations']==1,'Control cost/count mismatch')
    for name,fee,lag in [('base',8,1),('fee0',0,1),('fee20',20,1),('delay2',8,2)]:
        case=s['cases'][name];cfg=dict(name=name,fee_bps_each_side=fee,slippage_bps_each_side=2,delay_bars=lag)
        require(cfg in p['cases'] and cfg in rules['cost_cases'],'Unfrozen cost configuration')
        require(case['kind']=='STRATEGY' and case['fee_bps']==fee and case['slippage_bps']==2 and case['delay_bars']==lag,'Cost/delay result mismatch')
        view=d['metrics']['periods'] if name=='base' else d['metrics']['additional_native_bar_lag'] if name=='delay2' else d['metrics']['cost_sensitivity'][name]
        metric_match(view['2023-2024'],case)
    benchmark=s['cases']['buyhold'];bc=p['benchmark']
    require(benchmark['kind']=='CONTROL' and benchmark['fee_bps']==bc['fee_bps_each_side']==8 and benchmark['slippage_bps']==bc['slippage_bps_each_side']==2 and benchmark['delay_bars']==bc['delay_bars']==0,'Actual buyhold parameters changed')
    require(benchmark['fills']==1 and benchmark['closed_roundtrips']==0 and benchmark['win_rate'] is None,'Control null/trade state changed')
    metric_match(d['metrics']['same_instrument_benchmark']['2023-2024'],benchmark)
    dates=['2023-01-01']+[f'{y}-{m:02d}-{calendar.monthrange(y,m)[1]}' for y in [2023,2024] for m in range(1,13)]
    require([x['date'] for x in d['curve']]==dates and len(d['curve'])==25,'Exactly25 approved points required')
    require(d['curve_meta']['observations']==d['curve_meta']['total_observations']==s['cases']['base']['observations']==731 and d['curve_meta']['returned_points']==25,'Sample/full observation count mismatch')
    require(d['curve_meta']['equity_unit']=='initial_capital_multiple' and d['curve_meta']['drawdown_unit']=='fraction','Curve unit mismatch')
    require(d['curve'][0]['equity']==1.0 and math.isclose(d['curve'][-1]['equity'],s['cases']['base']['final_equity']/100000,abs_tol=1e-14),'NAV rescaled/rebased')
    for x in d['curve']:
        require(type(x['equity']) in [float,int] and math.isfinite(x['equity']) and x['equity']>=0,'Invalid NAV')
        require(type(x['drawdown']) in [float,int] and math.isfinite(x['drawdown']) and -1<=x['drawdown']<=0,'Invalid source drawdown')
    detail=deepcopy(d)
    detail.update(projection_profile=PROFILE,research_fidelity=fidelity,execution_class='ADAPTED_EXECUTION_PROXY',implementation_fidelity='ADAPTED_EXECUTION_PROXY')
    detail['metrics']['cost_sensitivity']={str(fee):deepcopy(d['metrics']['cost_sensitivity'][name]) for name,fee in [('fee0',0),('fee20',20)]}
    detail['metrics']['source_cost_key_aliases']={'fee0':'0','fee20':'20'}
    detail['curve_meta'].update(full_daily_curve_published=False,interpolation_claim=False,private_daily_nav_used=False,first_point_rebased=False,denominator=100000,source_drawdown_basis='Original approved samples retain drawdown against full daily peaks; never recomputed from25points')
    detail['spec']['params'].update(capital=deepcopy(capital),RSI5=rules['RSI5'],entry=rules['entry'],exit=rules['exit'],metric_conventions=deepcopy(p['statistics']))
    detail['limitations'] += ['Only the original25 public points are retained;731 is the original metrics observation count, not display point count.',
        'OriginalGraph HYPOTHESIS and research HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED stay separate from ADAPTED_EXECUTION_PROXY.',
        'Original run executed4 strategy configurations plus1 new100%fee-inclusive buyhold; this display preparation executes0new trials or controls.',
        'Original private-output inventory is not a display manifest and never authorizes reading privateNAV or ledgers.']
    record=deepcopy(r)
    record.update(projection_profile=PROFILE,status='tested_hypothesis_only',source_status=r['status'],fidelity_class='HYPOTHESIS',research_fidelity=fidelity,execution_class='ADAPTED_EXECUTION_PROXY',results=deepcopy(s['cases']),monthly=deepcopy(s['monthly']),benchmark_reference=dict(kind='ACTUAL_ORIGINAL_NEW_CONTROL',name='buyhold',new_controls_at_original_run=1,allocation=deepcopy(capital),configuration=deepcopy(bc),result=deepcopy(benchmark),evidence_role='summary'),benchmark_curve=[],source=deepcopy(source),catalog_fields=deepcopy(catalog['fields']),rules={k:deepcopy(rules[k]) for k in ['RSI5','entry','exit','capital','cold_start','stop_or_roi','known_halt']},metric_conventions=deepcopy(p['statistics']),economic_basis=dict(paper=None,hypothesis=None,status='NOT_ESTABLISHED_IN_SELECTED_SOURCE_CARD'),limitations=deepcopy(detail['limitations']))
    record['rules']['raw_cross_cancellation']=rules['execution']['raw_M1258']
    record['rules']['same_side_pending']='Retain original earliest due; no postponement. Opposite raw cross cancels before holding-eligible scheduling.'
    record['rules']['cost_cases']=deepcopy(rules['cost_cases'])
    return finish(record,detail,refs,encode(d['curve']))

def finish(record,detail,refs,curve):
    require(record['projection_profile']==detail['projection_profile']==PROFILE,'Display profile mismatch')
    manifest=dict(schema_version=SCHEMA,manifest_kind=KIND,projection_profile=PROFILE,id=RID,origin_run_id=detail['run_id'],variant_id=detail['variant_id'],origin_lab_commit=PIN,original_private_result_manifest=False,original_results_modified=False,source_artifacts=refs,files={**refs,'base-nav-sampled.json':dict(bytes=len(curve),sha256=sha(curve))},curve_contract=deepcopy(detail['curve_meta']),excluded_from_self_hash=['public-display-manifest.json','graph-record.json','graph-detail.json'],exclusion_reason='Record/detail bind this manifest; outerdelivery binds all4 candidate files without cycles',status='STAGED_NOT_PUBLISHED')
    manifest_raw=encode(manifest)
    oldlineage=deepcopy(detail['lineage'])
    detail['lineage']=dict(manifest_kind=KIND,source_display_manifest_sha256=sha(manifest_raw),manifest_sha256=sha(manifest_raw),lab_commit=PIN,protocol_sha256=refs['protocol']['sha256'],C0_sha256=refs['C0']['sha256'],source_artifacts=refs,definition_revision_bound=False,new_execution_trials=0,new_control_trials=0,source_lineage=oldlineage)
    binding={k:detail[k] for k in ['origin_run_id','variant_id','fidelity_class','execution_class']}
    binding.update(protocol_sha256=detail['lineage']['protocol_sha256'],manifest_sha256=detail['lineage']['manifest_sha256'])
    require(len(binding)==6 and all(isinstance(v,str) and v for v in binding.values()),'Six-field transport type mismatch')
    reference=dict(binding,manifest_kind=KIND)
    record.update(manifest_kind=KIND,related_results=[reference],implementations=[dict(reference,family=detail['family'])],projection_status='STAGED_NOT_IMPORTED',definition_revision_bound=False,control_configurations=1,reused_control_configurations=0,strategy_configurations=4,tested_variants=1,source_artifacts=refs)
    detail.update(manifest_kind=KIND,projection_status='STAGED_NOT_IMPORTED',transport_binding=binding,lab_counts=dict(strategy_ids=1,strategy_configurations=4,new_control_configurations=1,reused_control_configurations=0,strict_reproductions=0),projection_activity=dict(new_strategy_trials=0,new_controls=0))
    output={'graph-record.json':encode(record),'graph-detail.json':encode(detail),'base-nav-sampled.json':curve,'public-display-manifest.json':manifest_raw}
    for body in output.values():prior.screen(body)
    return output

def export(repo,output):
    require(not output.exists(),'Immutable output directory already exists')
    data,refs,inventory=load_sources(repo);files={DEST+name:body for name,body in project(data,refs).items()}
    delivery=dict(schema_version='M1258-public-display-preparation/v1',source_commit=PIN,original_publication_manifest_sha256=PUB_PIN[1],projection_profile=PROFILE,status='STAGED_NOT_IMPORTED',ids=[RID],records=1,original_strategy_configurations=4,original_new_control_configurations=1,new_executions=0,new_controls=0,private_daily_nav_used=False,default_graph_inventory_changed=False,site_operations=0,source_files=inventory,generated_candidates=4,generated_files_including_delivery=5,files={name:dict(bytes=len(body),sha256=sha(body)) for name,body in sorted(files.items())})
    files['DELIVERY-MANIFEST.json']=encode(delivery)
    require(shutil.disk_usage(output.parent).free>5*1024**3+sum(map(len,files.values())),'5GiB reserve required')
    output.mkdir(mode=0o700)
    for name,body in files.items():
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as h:h.write(body)
    return delivery
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--lab-repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=export(a.lab_repo,a.output);print(json.dumps({k:r[k] for k in ['status','source_commit','records','original_strategy_configurations','original_new_control_configurations','new_executions','new_controls','generated_files_including_delivery']}))
