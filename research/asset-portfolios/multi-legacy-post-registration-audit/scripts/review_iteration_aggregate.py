"""Independent read-only acceptance of the 2026-09-11 aggregate.

Verifies membership against predeclared cases, fixed early/final endpoints,
summary arithmetic, and every referenced result curve. Never runs a strategy.
Only aggregate data, source results/plans, and referenced CSVs are hashed; the
human report and README can be edited independently without stale acceptance.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[4]
BASE=Path(__file__).resolve().parents[1]/'artifacts/iteration_comparison_20260911'
OUT=BASE/'acceptance_aggregate.json'
START=pd.Timestamp('2026-07-23T00:00:00Z')
END=pd.Timestamp('2026-09-05T15:00:00Z')


def read(name):return json.loads((BASE/name).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def path(x):
    p=Path(x)
    return p if p.is_absolute() else ROOT/p
def near(a,b,tol=1e-10):
    assert np.allclose(np.asarray(a,float),np.asarray(b,float),rtol=1e-11,atol=tol,equal_nan=True),(a,b)
def sign(x):return 0 if abs(x)<=1e-12 else 1 if x>0 else -1
def key(r):return tuple(r[k] for k in ('group','family','version','scenario','window'))


def main():
    checks=[];warnings=[];files=set()
    names=['all_results.json','paired_results.json','coverage_final.json','aggregate_counts.json','scope.json',
           'ema/cases_plan.json','ar_mmtf/cases_plan.json','cc/cases_plan.json',
           'ema/results.json','ar_mmtf/results.json','cc/results.json']
    for n in names:files.add(BASE/n)
    allrows,pairs,coverage,counts,scope=[read(n) for n in names[:5]]
    ep,ap,cp=read('ema/cases_plan.json'),read('ar_mmtf/cases_plan.json'),read('cc/cases_plan.json')['plan']
    emap={'unit':'equal_1x_base','original_sizing':'original_size_base','unit_slip8bps':'equal_1x_stress'}
    amap={'fixed_1x':'equal_1x_base','original_sizing':'original_size_base','fixed_1x_slippage_8bps':'equal_1x_stress'}
    cmap={'fixed1x':'equal_1x_base','original_size':'original_size_base','fixed1x_slip8bps':'equal_1x_stress','long_fixed1x':'equal_1x_base'}
    expected=set()
    for c in ep['cases']:
        for s in ep['scenarios']:expected.add(('ema',c['family'],c['version'],emap[s['name']],'common'))
    for c in ap['cases']:
        for s in ap['scenarios']:expected.add(('ar_mmtf',c['family'],c['version'],amap[s],'common'))
    for c in cp['cases']:expected.add(('cc','HYPE-CC',c['config']['version'],cmap[c['scenario']],c['window']))
    actual=[key(r) for r in allrows]
    assert len(actual)==len(set(actual))==len(expected)==101
    assert set(actual)==expected
    assert Counter(r['window'] for r in allrows)=={'common':96,'long':5}
    assert Counter(r['group'] for r in allrows)=={'ema':27,'ar_mmtf':54,'cc':20}
    assert len({r['equity_path'] for r in allrows})==101
    for r in allrows:
        assert pd.Timestamp(r['end'])==END
        assert pd.Timestamp(r['start'])==(START if r['window']=='common' else pd.Timestamp('2026-06-08T03:45:00Z'))
        assert r['window']=='common' or r['group']=='cc'
    checks.append(dict(check='all_predeclared_cases_present_exactly_once',status='PASS',rows=101,common=96,cc_long=5,group_counts=dict(Counter(r['group'] for r in allrows))))

    # Prove each normalized aggregate row came from its own unselected group result.
    source_index={}
    for r in read('ema/results.json'):
        source_index[('ema',r['family'],r['version'],emap[r['scenario']],'common')]=(r['return_pct']/100,r['return_excluding_funding_pct']/100,r['max_drawdown_pct']/100,r['trades'],r['equity_path'])
    for r in read('ar_mmtf/results.json'):
        source_index[('ar_mmtf',r['family'],r['version'],amap[r['scenario']],'common')]=(r['return'],r['return_excluding_funding'],r['max_drawdown'],r['trades'],r['equity_path'])
    ccrows=read('cc/results.json')
    for r in ccrows:
        if r['funding_mode']!='observed_funding_estimate':continue
        ex=next(x for x in ccrows if x['case_id']==r['case_id'] and x['funding_mode']=='funding_excluded')
        source_index[('cc','HYPE-CC',r['version'],cmap[r['scenario']],r['window'])]=(r['return_pct']/100,ex['return_pct']/100,-r['max_drawdown_pct']/100,r['trades'],r['equity_path'])
    assert set(source_index)==expected
    for r in allrows:
        s=source_index[key(r)]
        near([r['return'],r['return_ex_funding'],r['drawdown']],s[:3])
        assert r['trades']==s[3] and path(r['equity_path'])==path(s[4])
    checks.append(dict(check='all_101_rows_match_group_source_results_and_units',status='PASS'))

    expected_pairs={'EMA-X':('V1','V18'),'EMA-TB':('V35','V41'),'MII':('V1','V1.4A'),'ENS':('V35+MII1.3','V2'),'HYPE-CC':('V10','V35')}
    for family in {c['family'] for c in ap['cases']}:
        early=next(c['version'] for c in ap['cases'] if c['family']==family and c['role']=='early')
        final=next(c['version'] for c in ap['cases'] if c['family']==family and c['role']=='latest')
        expected_pairs[family]=(early,final)
    assert len(pairs)==len({p['family'] for p in pairs})==14
    assert {p['family'] for p in pairs}==set(expected_pairs)
    for p in pairs:
        assert (p['early_version'],p['final_version'])==expected_pairs[p['family']]
        for role in ['early','final']:
            candidates=[r for r in allrows if r['family']==p['family'] and r['version']==p[f'{role}_version'] and r['scenario']=='equal_1x_base' and r['window']=='common']
            assert len(candidates)==1
            r=candidates[0]
            near(p[f'{role}_return'],r['return'])
            near(p[f'{role}_return_ex_funding'],r['return_ex_funding'])
            near(p[f'{role}_drawdown'],r['drawdown'])
            assert p[f'{role}_trades']==r['trades']
        near(p['increment'],p['final_return']-p['early_return'])
        near(p['increment_ex_funding'],p['final_return_ex_funding']-p['early_return_ex_funding'])
    checks.append(dict(check='fourteen_fixed_endpoints_match_predeclared_plans',status='PASS',endpoints=expected_pairs))

    final_by_family={r['family']:r for r in coverage['rows']}
    assert len(final_by_family)==len(scope['rows'])==len(coverage['rows'])==17
    assert set(final_by_family)=={r['family'] for r in scope['rows']}
    seen=[]
    for s in scope['rows']:
        r=final_by_family[s['family']]
        if s['status']=='PLANNED_VERSION_COMPARISON':
            assert r['status']=='REPLAYED_VERSION_COMPARISON'
            p=next(p for p in pairs if p['family']==r['pair']['family'])
            assert p==r['pair']
            seen.append(p['family'])
        else:
            assert r==s
    assert len(seen)==len(set(seen))==14 and set(seen)==set(expected_pairs)
    computed={'families':14,'result_rows':101,
              'final_higher':sum(sign(p['increment'])==1 for p in pairs),
              'final_lower':sum(sign(p['increment'])==-1 for p in pairs),
              'equal':sum(sign(p['increment'])==0 for p in pairs),
              'final_positive':sum(sign(p['final_return'])==1 for p in pairs),
              'early_positive':sum(sign(p['early_return'])==1 for p in pairs),
              'funding_changes_increment_sign':[p['family'] for p in pairs if sign(p['increment'])!=sign(p['increment_ex_funding'])]}
    assert counts==computed
    assert (computed['final_higher'],computed['final_lower'],computed['equal'])==(7,6,1)
    assert computed['funding_changes_increment_sign']==[]
    checks.append(dict(check='scope_coverage_counts_and_funding_excluded_direction',status='PASS',counts=computed,unpaired=3))

    max_return_error=max_dd_error=0.
    for r in allrows:
        eqpath,trpath,mopath=[path(r[k]) for k in ['equity_path','trades_path','monthly_path']]
        assert eqpath.is_file() and trpath.is_file() and mopath.is_file()
        files.update([eqpath,trpath,mopath])
        cv=pd.read_csv(eqpath)
        try:trades=pd.read_csv(trpath)
        except pd.errors.EmptyDataError:
            assert r['trades']==0
            trades=pd.DataFrame()
        assert len(trades)==r['trades']
        column='equity_funding_estimate' if r['group']=='ema' else 'equity'
        initial=10000. if r['group']=='cc' else 1.
        eq=cv[column].astype(float)
        assert np.isfinite(eq).all() and (eq>0).all()
        timecol='valuation_ts' if r['group']=='ema' else 'ts'
        times=pd.to_datetime(cv[timecol],utc=True)
        assert times.is_unique and times.is_monotonic_increasing and times.iloc[-1]==END
        ret=eq.iloc[-1]/initial-1
        dd=(eq/eq.cummax().clip(lower=initial)-1).min()
        near(ret,r['return']);near(dd,r['drawdown'])
        near(cv.drawdown,eq/eq.cummax().clip(lower=initial)-1)
        max_return_error=max(max_return_error,abs(ret-r['return']))
        max_dd_error=max(max_dd_error,abs(dd-r['drawdown']))
        if r['group']=='cc':
            ex=next(x for x in ccrows if x['version']==r['version'] and cmap[x['scenario']]==r['scenario'] and x['window']==r['window'] and x['funding_mode']=='funding_excluded')
            ex_path=path(ex['equity_path']);files.add(ex_path)
            nofund=pd.read_csv(ex_path).equity.iloc[-1]/initial-1
        else:nofund=cv.equity_excluding_funding.iloc[-1]-1
        near(nofund,r['return_ex_funding'])
        checks.append(dict(check='artifact_count_terminal_return_closing_drawdown',group=r['group'],family=r['family'],version=r['version'],scenario=r['scenario'],window=r['window'],status='PASS',rows=len(cv),trades=len(trades)))
    warnings=[
        'Aggregate acceptance verifies completeness, fixed endpoints, accounting summaries and sampled closing-equity drawdown. It is not an additional historical strategy parity or live-execution acceptance.',
        'EMA-X early endpoint remains a reconstructed bare-cross diagnostic without a unique full historical V1 spec; EMA-TB primary V35 is the earliest retained complete causal engine, while V2P stays supplemental.',
        'Funding remains observed-event estimates with differing documented family execution assumptions; removing estimated funding does not change any early/final incremental-return sign.',
        'CC V10 is the earliest complete written specification; V18/V21 are retained intermediate results, not substituted into the fixed early/final success counts.'
    ]
    files.add(Path(__file__))
    result=dict(status='PASS',reviewer='compare_cc_versions independent aggregate reviewer',checked_utc=pd.Timestamp.now(tz='UTC').isoformat(),
                counts=computed,common_rows=96,long_cc_rows=5,check_count=len(checks),checks=checks,warnings=warnings,errors=[],
                maximum_absolute_return_error=max_return_error,maximum_absolute_closing_drawdown_error=max_dd_error,
                hash_scope='Only aggregate data, frozen scope/plans, group results, referenced CSVs and this acceptance script. Human reports/READMEs excluded.',
                checked_files_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(files)})
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(checks),'hashes':len(files),'rows':len(allrows),'pairs':len(pairs),'sha256':sha(OUT)},ensure_ascii=False))


if __name__=='__main__':main()
