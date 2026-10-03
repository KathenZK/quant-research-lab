#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Private daily Graph projection of already-validated ledgers; no new replay."""
import argparse,csv,hashlib,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(pathlib.Path(p).read_text())
def write(p,x):
    with pathlib.Path(p).open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def export(work,target):
    work=pathlib.Path(work);out=pathlib.Path(target);out.mkdir(parents=True,exist_ok=False)
    spec=read(ROOT/'specs/protocol.json');summary=read(work/'summary.json');record=read(ROOT/'artifacts/graph-record.json')
    assert summary['protocol_sha256']==sha(ROOT/'specs/protocol.json')
    assert read(ROOT/'artifacts/independent-real-result-audit.json')['status']=='PASS_INDEPENDENT_DECIMAL_ALL_CASE_EXECUTION_AND_METRICS'
    assert read(ROOT/'artifacts/local-recovery.json')['status']=='PASS_LOCAL_RECOVERY'
    curves={};files={}
    for name in ['base','buyhold']:
        full=list(csv.DictReader((work/f'{name}-nav.csv').open()));daily=list(csv.DictReader((work/f'{name}-daily-nav.csv').open()))
        peak=float(spec['execution']['initial_cash']);drawdowns={}
        for row in full:
            value=float(row['equity']);peak=max(peak,value);drawdowns[row['bar_index']]=value/peak-1
        curves[name]=[{'date':r['date'],'timestamp_utc':r['timestamp_utc'],'equity':float(r['equity']),'drawdown':drawdowns[r['bar_index']]} for r in daily]
        assert len(full)==4386 and len(daily)==731 and all(-1<=x['drawdown']<=0 for x in curves[name])
        assert abs(min(drawdowns.values())+summary['results'][name]['metrics']['max_drawdown'])<1e-12
        for suffix in ['nav','daily-nav']:
            p=work/f'{name}-{suffix}.csv';files[p.name]={'sha256':sha(p),'bytes':p.stat().st_size}
    def metrics(name):
        m=dict(summary['results'][name]['metrics']);m['max_drawdown']=-m['max_drawdown'];m['sharpe']=m['sharpe_daily'];m['start']='2023-01-01';m['end']='2024-12-31';return {'full':m}
    lineage=dict(record['related_results'][0]);lineage['input_sha256']=summary['input_sha256']
    detail={'id':'M0317','run_id':spec['run_id'],'origin_run_id':spec['run_id'],'variant_id':spec['variant_id'],'fidelity_class':'HYPOTHESIS','name':record['name'],'family':spec['family'],
      'fidelity_reason':'Source-default Decimal4 and SMA7/14/28 preserved, sell interval remains impossible. Native-minute ROI uses observed4h opening tiers; explicit market-order proxy is not inherited limit execution. No author optimized-performance recovery.',
      'spec':{'source_url':'https://github.com/freqtrade/freqtrade-strategies/blob/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/mabStra.py','params':spec,'assumptions':['No full Freqtrade engine; author warns hyperopt required; no saved optimized params; no tuning','Original ROI minute keys, new tier deferred to next observable effective open','Halt nominal12 bar entry modeled14; no tick proof']},
      'audit':record['audit'],'lineage':lineage,'limitations':['DIAGNOSTIC_ONLY; strict finality/PIT/tradability unproven','Retrospective exposed window; unknown prior search count; no OOS/promotion/live-ready claim','Monthly public curve and private daily curves are projections; risk metrics use full4h ledger','Graph compatibility does not mean import/binding/deployment'],
      'metrics':{'periods':metrics('base'),'same_instrument_benchmark':metrics('buyhold'),'additional_native_bar_lag':metrics('delay2'),'cost_sensitivity':{k:metrics(k) for k in ['fee0','fee20']}},
      'curve':curves['base'],'benchmark_curve':curves['buyhold'],
      'curve_meta':{'observations':4386,'total_observations':4386,'source_observations':4386,'returned_points':731,'rows':731,'benchmark_curve_available':True,'benchmark_returned_points':731,'sampling':'UTC daily last native4h close; no interpolation','frequency':'1d UTC end-of-day sampled from4h ledger','initial_equity':100000,'initial_timestamp':spec['evaluation']['start'],'max_drawdown_sign':'negative','max_drawdown_source':'all unsampled4h closes plus initial capital; not recomputed from sampled daily curve','daily_drawdown_source':'daily close divided by maximum of all4h closes up to that time plus initial capital, minus1','sharpe_frequency':'daily returns sqrt365, initial capital included, ddof1, risk_free0','timestamp_convention':'close boundary;2025-01-01T00Z denotes2024-12-31 end','period_end_exclusive':spec['evaluation']['end_exclusive'],'source_hashes':files},
      'data_attribution':record['data_attribution'],'distribution':'PRIVATE_LIBRARY_ONLY_EXCLUDE_PUBLIC_GIT'}
    write(out/'graph-detail.private.json',detail)
    manifest={'id':'M0317','origin_run_id':spec['run_id'],'variant_id':spec['variant_id'],'fidelity_class':'HYPOTHESIS','protocol_sha256':sha(ROOT/'specs/protocol.json'),'input_sha256':summary['input_sha256'],'public_result_manifest_sha256':sha(ROOT/'artifacts/result-manifest.json'),'source_ledgers':files,'private_allowlist':{'graph-detail.private.json':{'bytes':(out/'graph-detail.private.json').stat().st_size,'sha256':sha(out/'graph-detail.private.json')}},'self_excluded':True,'public_upload':False,'new_returns_computed':False,'no_raw_candles_or_features':True}
    write(out/'private-manifest.json',manifest);print(json.dumps({'status':'PRIVATE_PROJECTION_CREATED_NOT_IMPORTED','detail_sha256':sha(out/'graph-detail.private.json'),'manifest_sha256':sha(out/'private-manifest.json'),'detail_bytes':(out/'graph-detail.private.json').stat().st_size,'rows_per_curve':731},indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work',required=True);p.add_argument('--output',required=True);a=p.parse_args();export(a.work,a.output)
