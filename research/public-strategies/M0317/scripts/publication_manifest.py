#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lock a small public-only file allowlist after evidence assembly. Refuses overwrite."""
import datetime,hashlib,json,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
 spec=json.loads((ROOT/'specs/protocol.json').read_text())
 for rel,h in spec['frozen_file_hashes'].items():assert sha(ROOT/rel)==h,rel
 assert json.loads((ROOT/'artifacts/local-recovery.json').read_text())['status']=='PASS_LOCAL_RECOVERY'
 assert json.loads((ROOT/'artifacts/independent-real-result-audit.json').read_text())['status']=='PASS_INDEPENDENT_DECIMAL_ALL_CASE_EXECUTION_AND_METRICS'
 for p in ROOT.rglob('*.md'):
  for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
   if '://' in target or target.startswith('#') or target=='publication-manifest.json':continue
   assert (p.parent/target.split('#')[0]).exists(),(p,target)
 files={}
 for p in sorted(ROOT.rglob('*')):
  if not p.is_file() or p.name=='publication-manifest.json':continue
  rel=str(p.relative_to(ROOT));assert not any(x in rel.lower() for x in ['__pycache__','private-graph','graph-detail','-nav.csv','signals.csv','source.py'])
  assert p.stat().st_size<150000,rel
  if p.suffix=='.json':json.loads(p.read_text(),parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
  files[rel]={'bytes':p.stat().st_size,'sha256':sha(p)}
 obj={'id':'M0317','origin_run_id':spec['run_id'],'variant_id':spec['variant_id'],'status':'COMPLETED_DIAGNOSTIC_REPLAY_VALIDATED_AND_LOCALLY_REBUILT','created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'self_excluded':True,'public_allowlist':files,'manifest_itself_public_candidate':True,'fidelity_class':'HYPOTHESIS','data_quality_status':'DIAGNOSTIC_ONLY','strict_reproductions':0,'protocol_sha256':sha(ROOT/'specs/protocol.json'),'raw_market_data':False,'full_third_party_source':False,'large_nav_or_features':False,'private_graph_detail':False,'software_license':'GPL-3.0-or-later scripts; original GPLv3 repository attribution retained','data_derivative_license':'Binance CC BY-NC-SA4.0 plus pinned additional terms; personal nonproduction scope','excluded_private_material':['work-M0317/sources','work-M0317/first-run','work-M0317/recovery-run','work-M0317/private-graph','shared raw market snapshots'],'C3':'PENDING_PARENT_REMOTE_SAVE_AND_READBACK','global_manifest_or_counts_modified':False}
 with (ROOT/'publication-manifest.json').open('x') as f:json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
 print(json.dumps({'status':'PUBLIC_CANDIDATE_LOCKED_FOR_FINAL_QA','files':len(files),'bytes':sum(x['bytes'] for x in files.values()),'manifest_sha256':sha(ROOT/'publication-manifest.json'),'no_more_experiments':True}))
if __name__=='__main__':main()
