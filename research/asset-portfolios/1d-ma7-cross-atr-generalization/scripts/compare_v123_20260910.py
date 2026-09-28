"""Saved-account comparison only: reuse V1/V3, consume newly completed V2.

Never imports a replay engine or opens the data lake. Every consumed source is
checked against its producer's preserved manifest before analysis is written.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from common import BASE, sha, write_json

OLD = BASE / 'artifacts/results_20260909'
NEW = BASE / 'artifacts/results_v2_20260910'
OUT = BASE / 'artifacts/comparison_v123_20260910'
VERSIONS = {'V1': (OLD, 'F0', '复用2026-09-09'), 'V2': (NEW, 'V2', '本次补跑2026-09-10'), 'V3': (OLD, 'H4_D0', '复用2026-09-09')}
LABELS = {'V1': '固定1.5ATR倍数', 'V2': '盈利且MA止损停滞时收紧', 'V3': '高低价4天未刷新后每天收紧'}
SCENARIOS = ['slippage_10bp', 'carry_5bp_day']
COHORTS = ['main_full', 'partial', 'short']
OLD_MANIFEST_SHA = '880d7201b4c23695265d80d2704e0ec03245dfdb8a274b50873f82fbfb50a13d'
INPUT_MANIFEST_SHA = 'a2390b002883506a8f39522a31e708e76346e21be6a0a598e753b4a5b5e4891c'


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean(v) for v in value]
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    return value


class Source:
    def __init__(self, directory, pinned=None):
        self.directory = directory
        manifest = directory / 'artifact_checksums.json'
        self.manifest_sha = sha(manifest)
        if pinned:
            assert self.manifest_sha == pinned, 'Original manifest changed'
        self.hashes = json.loads(manifest.read_text())
        self.checked = {}

    def path(self, relative):
        assert relative in self.hashes, f'Unregistered source: {relative}'
        path = self.directory / relative
        if relative not in self.checked:
            value = sha(path)
            assert value == self.hashes[relative], f'Source changed: {path}'
            self.checked[relative] = value
        return path

    def csv(self, relative):
        path = self.path(relative)
        try:
            return pd.read_csv(path)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()

    def obj(self, relative):
        return json.loads(self.path(relative).read_text())


def quality(item):
    item['historically_profitable'] = bool(item['return_pct'] > 0)
    item['risk_count_pass'] = bool(item['trade_days'] >= 180 and item['trades'] >= 10 and
                                   item['return_pct'] > 0 and item['max_drawdown_pct'] >= -30 and not item['bankrupt'])
    item['stable_candidate'] = bool(item['risk_count_pass'] and
        item['early60_return_pct'] > 0 and item['late40_return_pct'] > 0 and
        item['early60_trades'] >= 3 and item['late40_trades'] >= 3 and
        item['slippage_10bp_return_pct'] > 0 and item['carry_5bp_day_return_pct'] > 0)


def summarize_cohorts(ranking):
    rows = []
    for cohort in COHORTS:
        for version in VERSIONS:
            p = ranking[(ranking.cohort == cohort) & (ranking.version == version)]
            n = len(p)
            r = dict(cohort=cohort, version=version, case_id=VERSIONS[version][1], coins=n,
                     positive_coins=int((p.return_pct > 0).sum()), negative_coins=int((p.return_pct < 0).sum()),
                     flat_coins=int((p.return_pct == 0).sum()), positive_pct=float((p.return_pct > 0).mean()*100),
                     median_return_pct=float(p.return_pct.median()), median_max_drawdown_pct=float(p.max_drawdown_pct.median()),
                     worst_max_drawdown_pct=float(p.max_drawdown_pct.min()), median_trades=float(p.trades.median()),
                     all_trades=int(p.trades.sum()), winning_trades=int(p.winning_trades.sum()), losing_trades=int(p.losing_trades.sum()),
                     flat_trades=int(p.flat_trades.sum()), risk_count_pass_coins=int(p.risk_count_pass.sum()),
                     stable_candidate_coins=int(p.stable_candidate.sum()), bankrupt_coins=int(p.bankrupt.sum()),
                     data_boundary_coins=int(p.boundary_end_due_to_data.sum()),
                     median_slippage_10bp_return_pct=float(p.slippage_10bp_return_pct.median()),
                     median_carry_5bp_day_return_pct=float(p.carry_5bp_day_return_pct.median()),
                     beats_buy_hold_return_coins=int(p.beats_buy_hold_return.sum()))
            h = p[p.slug == 'HYPE']
            if len(h):
                r.update(hype_return_pct=float(h.iloc[0].return_pct), hype_return_rank_desc=int((p.return_pct > h.iloc[0].return_pct).sum()+1))
            rows.append(r)
    return rows


def paired(ranking):
    rows = []
    # Differences are paired by symbol; drawdown change uses signed source values:
    # a positive drawdown change is a reduction in loss from peak.
    for cohort in COHORTS:
        p = ranking[ranking.cohort == cohort]
        for newer, older in [('V2', 'V1'), ('V3', 'V2'), ('V3', 'V1')]:
            a = p[p.version == newer].set_index('symbol').sort_index()
            b = p[p.version == older].set_index('symbol').sort_index()
            assert a.index.equals(b.index)
            rdelta, ddelta = a.return_pct-b.return_pct, a.max_drawdown_pct-b.max_drawdown_pct
            eps = 1e-9
            rows.append(dict(cohort=cohort, comparison=f'{newer}-{older}', newer_version=newer, older_version=older,
                coins=len(a), return_up_coins=int((rdelta > eps).sum()), return_down_coins=int((rdelta < -eps).sum()),
                return_same_coins=int((rdelta.abs() <= eps).sum()),
                drawdown_improved_coins=int((ddelta > eps).sum()), drawdown_worse_coins=int((ddelta < -eps).sum()),
                drawdown_same_coins=int((ddelta.abs() <= eps).sum()),
                return_up_drawdown_not_worse_coins=int(((rdelta > eps) & (ddelta >= -eps)).sum()),
                both_strictly_improved_coins=int(((rdelta > eps) & (ddelta > eps)).sum()),
                return_down_drawdown_worse_coins=int(((rdelta < -eps) & (ddelta < -eps)).sum()),
                median_paired_return_change_pp=float(rdelta.median()),
                median_paired_drawdown_reduction_pp=float(ddelta.median()),
                median_paired_trade_count_change=float((a.trades-b.trades).median()),
                older_nonpositive_newer_positive_coins=int(((b.return_pct <= 0) & (a.return_pct > 0)).sum()),
                older_positive_newer_nonpositive_coins=int(((b.return_pct > 0) & (a.return_pct <= 0)).sum()),
                both_positive_coins=int(((b.return_pct > 0) & (a.return_pct > 0)).sum()),
                both_nonpositive_coins=int(((b.return_pct <= 0) & (a.return_pct <= 0)).sum()),
                newer_winning_trades=int(a.winning_trades.sum()), newer_losing_trades=int(a.losing_trades.sum()),
                newer_flat_trades=int(a.flat_trades.sum()), older_winning_trades=int(b.winning_trades.sum()),
                older_losing_trades=int(b.losing_trades.sum()), older_flat_trades=int(b.flat_trades.sum())))
    return rows


def main():
    assert not OUT.exists(), 'Preserve existing comparison output'
    assert sha(BASE/'artifacts/inputs_20260909/checksums.json') == INPUT_MANIFEST_SHA
    sources = {OLD: Source(OLD, OLD_MANIFEST_SHA), NEW: Source(NEW, '52b52f4e752cce01f7e31bb6b504190bfe3deb801e89eba0f7ea104dcf6afd97')}
    old, new = sources[OLD], sources[NEW]
    for source in sources.values():
        c = source.obj('completion.json')
        assert c['complete'] and c['coins_completed'] == 611 and c['coins_failed'] == 0
        source.obj('run_manifest.json')
    scope = old.csv('scope.csv')
    v2_scope = new.csv('scope.csv')
    assert len(scope) == 652 and scope.symbol.is_unique
    for field in ['symbol', 'cohort', 'trade_days', 'trade_start', 'end', 'boundary_end_due_to_data']:
        pd.testing.assert_series_equal(scope.sort_values('symbol')[field].reset_index(drop=True),
                                       v2_scope.sort_values('symbol')[field].reset_index(drop=True), check_names=False)
    scope_by = scope.set_index('symbol')
    summary = {path: source.csv('summary.csv') for path, source in sources.items()}
    stress = {path: source.csv('stress.csv') for path, source in sources.items()}
    assert set(summary[NEW].case_id) == {'V2'} and set(stress[NEW].case_id) == {'V2'}
    assert len(summary[NEW]) == 1689 and len(stress[NEW]) == 1222
    hold = old.csv('buy_hold.csv').query("window=='full'").set_index('symbol')
    base = summary[OLD].query("window=='full' and case_id=='F0'").set_index('symbol')
    v3 = summary[OLD].query("window=='full' and case_id=='H4_D0'").set_index('symbol')
    assert len(base) == len(v3) == len(hold) == 611
    rows = []
    for version, (path, cid, origin) in VERSIONS.items():
        g = summary[path].query('case_id==@cid').set_index(['symbol', 'window'])
        s = stress[path].query('case_id==@cid').set_index(['symbol', 'scenario'])
        assert g.index.is_unique and s.index.is_unique
        full = g.xs('full', level='window')
        assert full.index.sort_values().equals(base.index.sort_values())
        for symbol, row in full.iterrows():
            item = dict(row)
            item.update(symbol=symbol, window='full', version=version, version_label=LABELS[version],
                        source_case_id=cid, source_origin=origin, source_results_path=str(path.relative_to(BASE)),
                        boundary_end_due_to_data=bool(scope_by.loc[symbol].boundary_end_due_to_data),
                        fixed_return_pct=base.loc[symbol].return_pct,
                        fixed_drawdown_pct=base.loc[symbol].max_drawdown_pct,
                        baseline_return_pct=v3.loc[symbol].return_pct,
                        baseline_drawdown_pct=v3.loc[symbol].max_drawdown_pct,
                        buy_hold_return_pct=hold.loc[symbol].return_pct,
                        buy_hold_drawdown_pct=hold.loc[symbol].max_drawdown_pct,
                        vs_fixed_return_pp=row.return_pct-base.loc[symbol].return_pct,
                        vs_fixed_drawdown_reduction_pp=row.max_drawdown_pct-base.loc[symbol].max_drawdown_pct,
                        vs_baseline_return_pp=row.return_pct-v3.loc[symbol].return_pct,
                        vs_baseline_drawdown_reduction_pp=row.max_drawdown_pct-v3.loc[symbol].max_drawdown_pct)
            for period in ['early60', 'late40']:
                part = g.loc[(symbol, period)] if (symbol, period) in g.index else None
                for field in ['return_pct', 'max_drawdown_pct', 'trades']:
                    item[period+'_'+field] = part[field] if part is not None else np.nan
                item[period+'_start'] = part['start'] if part is not None else None
                item[period+'_end_exclusive'] = part['end_exclusive'] if part is not None else None
            for scenario in SCENARIOS:
                part = s.loc[(symbol, scenario)]
                for field in ['return_pct', 'max_drawdown_pct', 'trades', 'bankrupt']:
                    item[scenario+'_'+field] = part[field]
            quality(item)
            item['beats_fixed_both'] = bool(item['vs_fixed_return_pp'] > 0 and item['vs_fixed_drawdown_reduction_pp'] >= 0)
            item['beats_baseline_both'] = bool(item['vs_baseline_return_pp'] > 0 and item['vs_baseline_drawdown_reduction_pp'] >= 0)
            item['beats_buy_hold_return'] = bool(row.return_pct > item['buy_hold_return_pct'])
            relative = f'runs/{row.slug}/{cid}/full/trades.csv'
            trades = sources[path].csv(relative)
            assert len(trades) == int(row.trades)
            pnl = trades.net_pnl if len(trades) else pd.Series(dtype=float)
            assert np.isclose(10000+pnl.sum(), row.ending_equity, atol=1e-6, rtol=0)
            item.update(winning_trades=int((pnl > 0).sum()), losing_trades=int((pnl < 0).sum()), flat_trades=int((pnl == 0).sum()),
                        trades_csv_path='../'+path.name+'/'+relative)
            rows.append(item)
    ranking = pd.DataFrame(rows).sort_values(['cohort', 'version', 'return_pct'], ascending=[True, True, False])
    assert len(ranking) == 1833
    # Previous result summaries and candidate rules must reproduce exactly, without replay.
    prior_dir = BASE/'artifacts/analysis_20260909'
    prior_hashes = json.loads((prior_dir/'artifact_checksums.json').read_text())
    assert sha(prior_dir/'ranking.csv') == prior_hashes['ranking.csv']
    prior = pd.read_csv(prior_dir/'ranking.csv').query("case_id in ['F0','H4_D0']").sort_values(['symbol','case_id']).reset_index(drop=True)
    derived = ranking[ranking.version.isin(['V1','V3'])].sort_values(['symbol','case_id']).reset_index(drop=True)
    pd.testing.assert_frame_equal(prior, derived[prior.columns], check_dtype=False, check_exact=False, rtol=1e-12, atol=1e-12)
    cohort_rows, pair_rows = summarize_cohorts(ranking), paired(ranking)
    comparable = ranking.set_index(['symbol','version'])
    comparison, html_rows = [], []
    for r in scope.to_dict('records'):
        symbol = r['symbol']
        excluded = r['status'] != 'REPLAY_COMPLETED'
        reason = '未找到足够连续、日K与小时K同时有效且满足29日预热的交易窗口' if excluded else ''
        item = dict(r, exclusion_reason=reason)
        detail = dict(symbol=symbol, slug=r['slug'], cohort=r['cohort'], days=int(r['trade_days']),
                      start=str(r['trade_start'])[:10] if not excluded else None,
                      end=(pd.Timestamp(r['end'])-pd.Timedelta(days=1)).strftime('%Y-%m-%d') if not excluded else None,
                      dataEndedEarly=bool(r['boundary_end_due_to_data']) if not excluded else False,
                      excluded=excluded, reason=reason, dailyStatus=r['daily_status'], hourlyStatus=r['hourly_status'], versions={})
        for version in VERSIONS:
            if not excluded:
                v = comparable.loc[(symbol,version)].to_dict()
                for field in ['return_pct','max_drawdown_pct','trades','win_rate_pct','risk_count_pass','stable_candidate','bankrupt',
                              'early60_return_pct','late40_return_pct','slippage_10bp_return_pct','carry_5bp_day_return_pct',
                              'winning_trades','losing_trades','flat_trades','source_origin','source_case_id']:
                    item[version+'_'+field] = v[field]
                v['path_url'] = (f'../html_20260909_v2/coins/{r["slug"]}.html#{VERSIONS[version][1]}' if version != 'V2' else v['trades_csv_path'])
                assert (OUT/v['path_url'].split('#')[0]).resolve().exists()
                detail['versions'][version] = v
            else:
                for field in ['return_pct','max_drawdown_pct','trades','risk_count_pass','stable_candidate','bankrupt']:
                    item[version+'_'+field] = None
        comparison.append(item)
        html_rows.append(detail)
    candidates = ranking[ranking.risk_count_pass].copy()
    candidates['candidate_level'] = np.where(candidates.stable_candidate, 'stable', 'risk_count_only')
    summary_out = dict(family_id='BIN-1D-MA7-CAR-GEN', round='V1-V2-V3-comparison-20260910',
        observed_contracts=874, candidate_coins=652, excluded_non_coin_or_unknown=222, completed_coins=611,
        excluded_price_coins=41, execution_failed_coins=0, cohort_counts=scope.cohort.value_counts().to_dict(),
        versions={v: {'source_case_id': a[1], 'source': a[2], 'label': LABELS[v]} for v,a in VERSIONS.items()},
        reused_versions=['V1','V3'], newly_replayed_versions=['V2'], cohorts=cohort_rows, paired_comparisons=pair_rows,
        all_full_period_trades=int(ranking.trades.sum()), source_summary_rows={'V1':1689,'V2':1689,'V3':1689},
        source_stress_rows={'V1':1222,'V2':1222,'V3':1222},
        price_diagnostic_only=True, funding_window_verified=False, independent_single_coin_accounts=True,
        comparison_note='Each symbol is a separate 10000 USDT account. Cohorts have different histories and remain separate; no summary is a tradable portfolio.',
        drawdown_note='CSV uses negative source drawdowns. HTML displays positive drawdown magnitudes. Positive paired drawdown reduction means less drawdown.',
        stable_candidate_definition='At least 180 days and 10 trades; positive return, max drawdown <=30%, not bankrupt; each independent early/late account >=3 trades and positive; both uniform cost stresses positive.',
        verification=dict(previous_V1_V3_ranking_identical=True, previous_ranking_rows_checked=len(prior),
                          previous_ranking_columns_checked=len(prior.columns), full_trade_ledgers_checked=1833))
    OUT.mkdir(parents=True)
    ranking.to_csv(OUT/'ranking.csv', index=False)
    pd.DataFrame(comparison).to_csv(OUT/'comparison.csv', index=False)
    pd.DataFrame(cohort_rows).to_csv(OUT/'cohort_summary.csv', index=False)
    pd.DataFrame(pair_rows).to_csv(OUT/'paired_comparisons.csv', index=False)
    candidates.to_csv(OUT/'candidates.csv', index=False)
    scope[scope.status!='REPLAY_COMPLETED'].assign(exclusion_reason='未找到足够连续、日K与小时K同时有效且满足29日预热的交易窗口').to_csv(OUT/'excluded.csv', index=False)
    for name, obj in [('cohort_summary.json',cohort_rows),('paired_comparisons.json',pair_rows),('summary.json',summary_out)]:
        write_json(OUT/name, clean(obj))
    data = clean(dict(summary=summary_out, rows=html_rows, versionLabels=LABELS))
    template_path=BASE/'scripts/v123_comparison_template.html'
    template=template_path.read_text()
    assert template.count('__FROZEN_DATA__') == 1
    assert not re.search(r'<(?:script|link|iframe|img)\b[^>]+\b(?:src|href)\s*=', template, re.I)
    script=re.findall(r'<script>(.*?)</script>', template, re.S)
    assert len(script)==1 and not re.search(r'\b(?:fetch|XMLHttpRequest|WebSocket|EventSource)\b', script[0])
    subprocess.run(['node','--check','-'],input=script[0],text=True,check=True,capture_output=True)
    encoded=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/')
    (OUT/'index.html').write_text(template.replace('__FROZEN_DATA__',encoded))
    source_manifest = dict(input_manifest_sha256=INPUT_MANIFEST_SHA,
        contract_sha256=sha(BASE/'specs/contract-v1-v3-comparison-20260910.md'),
        comparison_script_sha256=sha(Path(__file__)),template_sha256=sha(template_path),
        prior_ranking_sha256=sha(prior_dir/'ranking.csv'),
        sources={str(p.relative_to(BASE)):{'artifact_checksums_sha256':s.manifest_sha,'consumed_files':s.checked} for p,s in sources.items()},
        replay_performed_by_this_script=False, reused_versions=['V1','V3'], newly_replayed_versions=['V2'])
    write_json(OUT/'source_manifest.json',source_manifest)
    write_json(OUT/'artifact_checksums.json',{str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()})
    print(pd.DataFrame(cohort_rows)[['cohort','version','coins','positive_coins','median_return_pct','median_max_drawdown_pct','stable_candidate_coins']].to_string(index=False))


if __name__=='__main__':
    main()
