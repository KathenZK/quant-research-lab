#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic light projection. Never publish native OHLCV/full features/4h NAV."""
import argparse,datetime,hashlib,json,pathlib,shutil
import pandas as pd
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def write(p,x):
    with p.open('x') as f:json.dump(x,f,indent=2,ensure_ascii=False);f.write('\n')
def export(work):
    work=pathlib.Path(work);out=ROOT/'artifacts/results';out.mkdir(exist_ok=False)
    assert json.loads((ROOT/'artifacts/independent-real-result-audit.json').read_text())['status']=='PASS_INDEPENDENT_DECIMAL_ALL_CASE_EXECUTION_AND_METRICS'
    summary=json.loads((work/'summary.json').read_text());spec=json.loads((ROOT/'specs/protocol.json').read_text())
    shutil.copyfile(work/'summary.json',out/'summary.json')
    metrics=[];annual=[];curves={};details={}
    for name,result in summary['results'].items():
        metrics.append({'case':name,**result['case'],**result['metrics']});d=pd.read_csv(work/f'{name}-daily-nav.csv');t=pd.read_csv(work/f'{name}-trades.csv');last=100000
        for yr,g in d.groupby(d.date.str[:4]):
            end=float(g.iloc[-1].equity);annual.append({'case':name,'year':yr,'marked_return':end/last-1});last=end
        monthly=d.groupby(d.date.str[:7]).tail(1)
        curves[name]=dict(zip(monthly.timestamp_utc,monthly.nav))
        details[name]={'exit_reason_counts':t[t.side=='SELL'].reason.value_counts().to_dict(),'first_entry_utc':t.iloc[0].execution_time_utc,'last_event_side':t.iloc[-1].side,'last_event_bar_open_utc':t.iloc[-1].bar_open_utc,'roi_boundary_candidate_bars':result['metrics']['roi_boundary_candidate_bars']}
    pd.DataFrame(metrics).drop(columns='name',errors='ignore').to_csv(out/'metrics.csv',index=False,float_format='%.17g')
    pd.DataFrame(annual).to_csv(out/'calendar-year-attribution.csv',index=False,float_format='%.17g')
    curve=pd.DataFrame(curves);curve.index.name='timestamp_utc';curve.loc[spec['evaluation']['start']]=1.;curve.sort_index().to_csv(out/'month-end-nav-light.csv',float_format='%.17g')
    # 201 base fill events: compact derived execution ledger, not raw historical candles.
    shutil.copyfile(work/'base-trades.csv',out/'base-trades.csv')
    write(out/'trade-diagnostics.json',details)
    result_manifest={'origin_run_id':spec['run_id'],'variant_id':spec['variant_id'],'fidelity_class':'HYPOTHESIS','protocol_sha256':sha(ROOT/'specs/protocol.json'),'light_files':{str(p.relative_to(ROOT)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(out.iterdir())},'private_full_outputs':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(work.iterdir())},'projection':'month-end normalized NAV plus initial point; max drawdown/Sharpe computed before sampling over all 4h/day observations; base fill ledger only','raw_or_full_candles_included':False}
    write(ROOT/'artifacts/result-manifest.json',result_manifest)
    record={'id':'M0317','name':'mabStra：BTC现货4h源码默认阈值诊断','status':'tested_hypothesis_only','reason':'固定SMA7/14/28及Decimal4默认参数，保留矛盾卖出区间；原ROI分钟阶梯、4h开盘观察和market执行代理。4386根买入条件全真、卖出恒假，净收益/回撤/日Sharpe落后同仓位买持；非作者优化复原，未晋升。','tested_variants':1,'families':[spec['family']],
      'audit':{'source_verification_status':'pinned_source_sha256_verified','source_rule_attribution_status':'original_AST_default_signals_and_fixed_risk_preserved_market_execution_proxy_declared','independent_validation':'PASS_INDEPENDENT_DECIMAL_ALL_CASE_EXECUTION_AND_METRICS','causality_validation':'PASS','local_recovery':'PASS_LOCAL_RECOVERY','data_quality_status':'DIAGNOSTIC_ONLY','trusted_input':False,'strict_core_finality':'NOT_ESTABLISHED','strict_replication':False,'oos_claim':False,'promotion':False,'definition_bound':False,'deployed':False},
      'implementations':[{'origin_run_id':spec['run_id'],'variant_id':spec['variant_id'],'fidelity_class':'HYPOTHESIS','protocol_sha256':sha(ROOT/'specs/protocol.json'),'manifest_sha256':sha(ROOT/'artifacts/result-manifest.json'),'family':spec['family']}],
      'related_results':[{'origin_run_id':spec['run_id'],'variant_id':spec['variant_id'],'fidelity_class':'HYPOTHESIS','protocol_sha256':sha(ROOT/'specs/protocol.json'),'manifest_sha256':sha(ROOT/'artifacts/result-manifest.json')}],
      'data_attribution':{'provider':'Binance','license':'CC BY-NC-SA-4.0 with Binance additional terms','terms_url':'https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md','changes':'native archive canonicalization, SMA ratio indicators, assumed fills/costs/risk accounting, metrics and month-end normalization'}}
    write(ROOT/'artifacts/graph-record.json',record)
    write(ROOT/'artifacts/C2-validation-receipt.json',{'id':'M0317','checkpoint':'C2','status':'PASS_DECLARED_HYPOTHESIS_ONLY','completed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'protocol_sha256':sha(ROOT/'specs/protocol.json'),'summary_sha256':sha(out/'summary.json'),'independent_decision_oracle':'artifacts/independent-real-result-audit.json','execution_prefixes':'55 exact case-prefix comparisons','local_recovery':'22 output files; only peak RSS permitted to differ','strict_reproductions':0,'C3':'PENDING_PARENT_REMOTE_SAVE_AND_READBACK','global_counts_or_indexes_modified':False})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work',required=True);a=p.parse_args();export(a.work)
