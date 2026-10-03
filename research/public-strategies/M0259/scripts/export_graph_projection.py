#!/usr/bin/env python3
"""Create UNPUBLISHED light result/Graph artifacts only after actual validation.
Shape follows M0216 at Lab commit797a8e7d1dda2a1009ab03baac0bf770dab8a806.
Does not upload, bind a definition, import into Graph, or claim page rendering.
GPL-3.0-or-later; authored 2026-10-03.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

TERMS='https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(p,v):
    with open(p,'x') as f:f.write(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def curve(p):
    with open(p,newline='') as f:
        return [{'date':r['ts'][:10],'equity':float(r['equity']),'drawdown':float(r['drawdown'])} for r in csv.DictReader(f)]

def main():
    ap=argparse.ArgumentParser()
    for x in ['results','validation','original-class','causality','rebuild','freeze','out','private-detail']:ap.add_argument('--'+x,required=True)
    a=ap.parse_args();root=Path(__file__).resolve().parents[1];res=Path(a.results);out=Path(a.out)
    val=read(a.validation);original=read(a.original_class);causal=read(a.causality);rebuild=read(a.rebuild);freeze=read(a.freeze)
    if not (val['status']=='PASS' and original['status']=='PASS' and causal['status']=='PASS' and rebuild['status']=='VERIFIED'):
        raise SystemExit('Missing actual validation / causality / rebuild pass')
    s=read(res/'summary.json');spec=read(root/'specs/M0259-first-replay.json')
    current_spec_sha=sha(root/'specs/M0259-first-replay.json')
    frozen_spec_sha=freeze['code_and_spec_sha256']['specs/M0259-first-replay.json']
    if current_spec_sha!=s['protocol_sha256'] or current_spec_sha!=frozen_spec_sha:
        raise SystemExit('Protocol drift: current spec, computed-result protocol and frozen spec must match')
    private_detail=Path(a.private_detail).resolve()
    if private_detail.is_relative_to(out.resolve()):raise SystemExit('Full private detail must be outside public artifact directory')
    if private_detail.exists():raise SystemExit('Refusing to overwrite private detail')
    if s['input_sha256']!=freeze['input_sha256'] or val['input_sha256']!=freeze['input_sha256'] or original['input_sha256']!=freeze['input_sha256']:
        raise SystemExit('Input lineage mismatch')
    if s['freeze_sha256']!=sha(a.freeze) or rebuild['frozen_sha256']!=sha(a.freeze):raise SystemExit('Freeze lineage mismatch')
    out.mkdir(parents=True,exist_ok=False)
    retained=['summary.json','curve_meta.json','base_equity_daily.csv','base_trades.csv','base_fills.csv','base_ambiguities.json','buyhold_equity_daily.csv']
    for name in retained:shutil.copyfile(res/name,out/name)
    for name,p in [('validation.json',a.validation),('original-class-validation.json',a.original_class),('causality.json',a.causality),('rebuild-receipt.json',a.rebuild),('freeze.json',a.freeze)]:shutil.copyfile(p,out/name)
    result_manifest={'id':'M0259','files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file()},
                     'rights':{'data_and_derivatives_license':'CC BY-NC-SA 4.0','additional_terms':TERMS,'attribution':'Binance Vision / Binance official public market data'},
                     'full_hourly_outputs':'privately retained; deterministic replay.py generates identical files; daily curve is a labeled sample'}
    write(out/'result-manifest.json',result_manifest)
    lineage={'origin_run_id':s['run_id'],'variant_id':s['variant_id'],'fidelity_class':'HYPOTHESIS',
             'protocol_sha256':s['protocol_sha256'],'manifest_sha256':sha(out/'result-manifest.json'),
             'freeze_sha256':sha(a.freeze),'input_sha256':s['input_sha256']}
    audit={'source_verification_status':'readable_hash_verified','source_rule_attribution_status':'public_source_anchored_hypothesis',
           'data_status':'DIAGNOSTIC_ONLY','signal_ledger_validation':'PASS','original_class_signal_validation':'PASS','future_perturbation':'PASS','local_rebuild':'VERIFIED',
           'oos_claim':False,'promoted':False,'live_ready':False,'graph_definition_bound':False,'graph_page_verified':False}
    record={'id':'M0259','name':'BbandRsi','status':'tested_hypothesis_only',
            'reason':'BTCUSDT现货1h探索性历史执行诊断；独立账本和本地恢复通过，不是严格复现、纯净样本外或晋升结论。',
            'tested_variants':1,'families':[spec['family']],'audit':audit,
            'implementations':[{'family':spec['family'],**lineage}],'related_results':[lineage]}
    base_curve=curve(out/'base_equity_daily.csv');benchmark=curve(out/'buyhold_equity_daily.csv')
    def period(name):return {'full':s['cases'][name]['metrics']}
    detail={'id':'M0259','run_id':s['run_id'],'origin_run_id':s['run_id'],'variant_id':s['variant_id'],
            'name':'BbandRsi','family':spec['family'],'fidelity_class':'HYPOTHESIS',
            'fidelity_reason':'Signals anchored to exact source and indicator semantics; BTCUSDT selection and independent execution are declared hypotheses.',
            'spec':{'source_url':'https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/berlinguyinca/BbandRsi.py','assumptions':spec['limitations'],'params':spec},
            'audit':audit,'lineage':{**lineage,'projection_revision':'M0259-graph-display-v1','license':'CC BY-NC-SA 4.0','attribution':'Binance Vision','additional_terms':TERMS},
            'limitations':spec['limitations']+['Graph input compatibility is not actual import, definition binding or page verification.'],
            'metrics':{'periods':period('base'),'same_instrument_benchmark':period('buyhold'),'additional_native_bar_lag':period('delay2'),
                       'cost_sensitivity':{k:period(k) for k in ['fee0','fee20']}},
            'curve':base_curve,'benchmark_curve':benchmark,
            'curve_meta':{'observations':len(base_curve),'total_observations':s['cases']['base']['metrics']['observations'],
                          'returned_points':len(base_curve),'sampling':'UTC last hourly close of each day, no initial cash point in sampled array',
                          'benchmark_curve_available':True,'date_semantics':'trading UTC day label; valuation is next UTC midnight',
                          'metrics_frequency':'hourly full-curve max drawdown; daily close-return Sharpe sqrt365',
                          'drawdown_semantics':'each sampled point retains drawdown from full hourly running peak; reported maximum is from unsampled hourly curve',
                          'initial_equity':100000.,'unit':'USDT','terminal':'unliquidated raw close marking'}}
    write(out/'graph-record.json',record);write(private_detail,detail)
    write(out/'publication-manifest.json',{'state':'GENERATED_NOT_PUBLISHED_OR_IMPORTED','files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file()},'self_excluded':True,'full_graph_detail_excluded':'private destination provided separately; never included in public files'})
    print('Graph-shaped artifacts generated, not imported or deployed')
if __name__=='__main__':main()
