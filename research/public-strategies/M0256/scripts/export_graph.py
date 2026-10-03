#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Create requested Graph-compatible JSON after validation/rebuild. No import,
registration, definition binding, deployment or remote writes are performed.
"""
import argparse,csv,hashlib,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(pathlib.Path(p).read_text())
def write(p,x):pathlib.Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def export(results,independent,causality,recovery,output):
    results=pathlib.Path(results);out=pathlib.Path(output);out.mkdir(parents=True,exist_ok=False)
    specpath=ROOT/'specs/M0256-first-replay.json';spec=read(specpath);summary=read(results/'summary.json');validation=read(independent);future=read(causality);restored=read(recovery)
    assert validation['status']==future['status']==restored['status']=='PASS'
    assert summary['protocol_sha256']==sha(specpath)==restored['protocol_sha256']
    assert summary['input_sha256']==spec['input']['sha256']==restored['input_sha256']
    files={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(results.glob('*')) if p.is_file()}
    manifest={'id':'M0256','origin_run_id':spec['run_id'],'protocol_sha256':sha(specpath),'input_sha256':spec['input']['sha256'],'source_manifest_sha256':sha(ROOT/'specs/source-manifest.json'),'files':files,'checks':{'independent':sha(independent),'causality':sha(causality),'local_recovery':sha(recovery)}}
    write(out/'result-manifest.json',manifest);mh=sha(out/'result-manifest.json')
    lineage={'origin_run_id':spec['run_id'],'variant_id':spec['variant_id'],'fidelity_class':'HYPOTHESIS','protocol_sha256':sha(specpath),'manifest_sha256':mh}
    audit={'source_verification_status':'pinned_source_sha256_verified','source_rule_attribution_status':'original_source_signals_and_risk_preserved_execution_assumptions_declared','independent_validation':'PASS','causality_validation':'PASS','local_recovery':'PASS','data_quality_status':'DIAGNOSTIC_ONLY','trusted_input':False,'strict_core_finality':'NOT_ESTABLISHED','strict_replication':False,'oos_claim':False,'promotion':False,'definition_bound':False,'deployed':False}
    license={'provider':'Binance','license':'CC BY-NC-SA-4.0 with Binance additional terms','terms_url':'https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md','changes':'EMA calculation, assumed execution/accounting, metrics and daily sampling'}
    record={'id':'M0256','name':'AverageStrategy：BTC现货4h EMA8/21','status':'tested_hypothesis_only','reason':'单标的假设实例回测与独立校验；保留ROI50%/stop−20%，非原框架严格复现，历史窗口已曝光。','tested_variants':1,'families':[spec['family']],'audit':audit,'implementations':[dict(lineage,family=spec['family'])],'related_results':[lineage],'data_attribution':license}
    write(out/'graph-record.json',record)
    with (results/'base-nav-light.csv').open() as f:daily=list(csv.DictReader(f))
    with (results/'base-nav.csv').open() as f:full=list(csv.DictReader(f))
    def period(name):
        m=dict(summary['results'][name]['metrics']);m['max_drawdown']=-m['max_drawdown'];m['start']='2023-01-01';m['end']='2024-12-31';return {'full':m}
    peak=float(spec['execution']['initial_cash']);drawdowns={}
    for row in full:
        value=float(row['equity']);peak=max(peak,value);drawdowns[row['bar_index']]=value/peak-1
    m=period('base')['full']
    detail={'id':'M0256','run_id':spec['run_id'],'origin_run_id':spec['run_id'],'variant_id':spec['variant_id'],'fidelity_class':'HYPOTHESIS','name':record['name'],'family':spec['family'],'fidelity_reason':'Pinned-source EMA8/21 and ROI/stop preserved; BTC instance, OHLC execution and resumption proxies are declared hypotheses.','spec':{'source_url':'https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/berlinguyinca/AverageStrategy.py','assumptions':['Independent execution port, not Freqtrade engine','DIAGNOSTIC_ONLY input; strict finality/PIT/tradability not established','Known interruption timing handled only to the granularity proved by retained evidence'],'params':spec},'audit':audit,'lineage':lineage,
       'limitations':['HYPOTHESIS; no historical author asset-universe proof','Retrospective archive; not clean OOS; prior searches unknown','4h OHLC cannot determine intrabar stop/ROI order; stop-first assumption','Full fractional fills, no historical trading-limit/order-book proof','Graph compatibility is not definition binding, ingestion or deployment'],
       'metrics':{'periods':{'full':m},'same_instrument_benchmark':period('buyhold'),'additional_native_bar_lag':period('delay2'),'cost_sensitivity':{k:period(k) for k in ('fee0','fee20')}},'curve':[{'date':r['date'],'equity':float(r['equity']),'drawdown':drawdowns[r['bar_index']]} for r in daily],
       'curve_meta':{'observations':len(full),'total_observations':len(full),'returned_points':len(daily),'sampling':'UTC daily last native 4h bar; no interpolation','benchmark_curve_available':False,'frequency':'1d UTC end-of-day sampled from 4h ledger','rows':len(daily),'source_observations':len(full),'initial_equity':spec['execution']['initial_cash'],'initial_timestamp':spec['evaluation']['start'],'max_drawdown_sign':'negative','max_drawdown_source':'all unsampled 4h bar-close equity plus initial capital, not recomputed from daily curve','sharpe_frequency':'daily returns sqrt365, initial capital included, ddof1, risk_free0','timestamp_convention':'close boundary; 2025-01-01T00Z is end of 2024-12-31','period_end_exclusive':spec['evaluation']['end_exclusive'],'sampled_curve_sha256':sha(results/'base-nav-light.csv'),'full_curve_sha256':sha(results/'base-nav.csv')},'data_attribution':license}
    write(out/'graph-detail.private.json',detail)
    assert detail['metrics']['periods']['full']['max_drawdown']<=0 and len(detail['curve'])==spec['evaluation']['expected_rows']//6
    return {'status':'FILES_GENERATED_NOT_IMPORTED','record':str(out/'graph-record.json'),'detail_private':str(out/'graph-detail.private.json'),'manifest_sha256':mh,'definition_bound':False,'deployed':False}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',required=True);p.add_argument('--independent',required=True);p.add_argument('--causality',required=True);p.add_argument('--recovery',required=True);p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(export(a.results,a.independent,a.causality,a.recovery,a.output),indent=2))
