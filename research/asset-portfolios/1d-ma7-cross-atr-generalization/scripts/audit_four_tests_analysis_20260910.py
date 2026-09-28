"""Independent saved-ledger analysis audit; no simulator/analysis-module imports.

Reads only this family's frozen result artifacts. Reconstructs all post-exit
windows and aggregation denominators, then separately checks new comparisons.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import traceback

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
OLD = BASE / 'artifacts/results_20260909'
NEW = BASE / 'artifacts/results_four_tests_20260910'
ANALYSIS = BASE / 'artifacts/analysis_four_tests_20260910'
EXIT = ANALYSIS / 'exit_diagnostics'
OUTPUT = BASE / 'artifacts/delivery_four_tests_20260910/analysis_independent_check.json'
OLD_MANIFEST_SHA = '880d7201b4c23695265d80d2704e0ec03245dfdb8a274b50873f82fbfb50a13d'
NEW_MANIFEST_SHA = 'd076298e421654e200d9ae380a08b7130886e9550cec31f1af8f62e5fd1cad6e'
COHORTS = ['main_full', 'partial', 'short']
CASES = ['V3', 'A_LONG', 'A_SHORT', 'A_SHORT_NO_TP', 'B_MA30_READY', 'B_MA30',
         'C_RISK005', 'C_SMALL', 'D_RESET', 'D_NO_TP', 'V1']
PAIRS = [('A_LONG', 'V3'), ('A_SHORT', 'V3'), ('A_SHORT_NO_TP', 'A_SHORT'),
         ('B_MA30', 'B_MA30_READY'), ('B_MA30_READY', 'V3'), ('C_RISK005', 'V3'),
         ('C_SMALL', 'V3'), ('C_RISK005', 'C_SMALL'), ('D_RESET', 'V3'),
         ('D_NO_TP', 'V3'), ('V3', 'V1')]
HOUR = pd.Timedelta(hours=1)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def obj(p):
    return json.loads(p.read_text())


def csv(p, **kwargs):
    try:
        return pd.read_csv(p, **kwargs)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def finite_json(x):
    if isinstance(x, dict):
        return {str(k): finite_json(v) for k, v in x.items()}
    if isinstance(x, (tuple, list)):
        return [finite_json(v) for v in x]
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if np.isfinite(x) else None
    return x


def compare(expected, actual, keys, name, columns=None):
    """Exact identifiers/counts/booleans, numeric tolerance for CSV round trips."""
    assert not expected.duplicated(keys).any(), (name, 'expected duplicates')
    assert not actual.duplicated(keys).any(), (name, 'actual duplicates')
    a = expected.set_index(keys).sort_index()
    b = actual.set_index(keys).sort_index()
    assert a.index.equals(b.index), (name, 'missing/extra identities', len(a), len(b))
    for col in columns or a.columns:
        assert col in b, (name, 'missing column', col)
        av, bv = a[col], b[col]
        if pd.api.types.is_numeric_dtype(av) and not pd.api.types.is_bool_dtype(av):
            left = pd.to_numeric(av).to_numpy(dtype=float)
            right = pd.to_numeric(bv).to_numpy(dtype=float)
            ok = np.isclose(left, right, rtol=1e-11, atol=1e-9, equal_nan=True)
            assert ok.all(), (name, col, a.index[np.flatnonzero(~ok)[0]],
                              left[np.flatnonzero(~ok)[0]], right[np.flatnonzero(~ok)[0]])
        elif 'time' in col or col in {'arm_day', 'followup_start', 'followup_end_exclusive', 'selected_data_end_exclusive'}:
            left = pd.to_datetime(av, utc=True, format='mixed')
            right = pd.to_datetime(bv, utc=True, format='mixed')
            assert ((left == right) | (left.isna() & right.isna())).all(), (name, col)
        else:
            assert av.fillna('').astype(str).equals(bv.fillna('').astype(str)), (name, col)
    return {'rows': len(a), 'columns_checked': len(columns or a.columns), 'status': 'PASS'}


def scope():
    s = csv(OLD / 'scope.csv')
    assert len(s) == 652 and s.symbol.is_unique
    eligible = s[s.status == 'REPLAY_COMPLETED'].copy()
    assert len(eligible) == 611
    days = (pd.to_datetime(eligible.end, utc=True) - pd.to_datetime(eligible.trade_start, utc=True)).dt.total_seconds() / 86400
    assert np.array_equal(days.to_numpy(), eligible.trade_days.to_numpy())
    main = (eligible.trade_start.str.startswith('2025-06-29') & eligible.end.str.startswith('2026-09-05') & days.eq(433))
    expected = np.where(main, 'main_full', np.where(days >= 180, 'partial', 'short'))
    assert np.array_equal(expected, eligible.cohort.to_numpy())
    assert eligible.cohort.value_counts().to_dict() == {'main_full': 346, 'partial': 193, 'short': 72}
    return s, eligible


def exit_source_integrity():
    """Match already verified consumed-source hashes to the immutable manifest."""
    assert digest(OLD / 'artifact_checksums.json') == OLD_MANIFEST_SHA
    manifest = obj(OLD / 'artifact_checksums.json')
    record = obj(EXIT / 'source_manifest.json')
    assert record['source']['artifact_checksums_sha256'] == OLD_MANIFEST_SHA
    consumed = record['source']['consumed_files']
    for name, sha in consumed.items():
        assert manifest[name] == sha, name
    hashes = obj(EXIT / 'artifact_checksums.json')
    for name, sha in hashes.items():
        assert digest(EXIT / name) == sha, name
    return {'source_files_previously_verified_and_matched': len(consumed),
            'source_integrity_method': 'Match Source consumed hashes to pinned manifest; do not rescan all original files.',
            'exit_artifacts_rehashed': len(hashes), 'exit_artifact_hashes': hashes,
            'old_manifest_sha256': OLD_MANIFEST_SHA}


def audit_exits():
    integrity = exit_source_integrity()
    _, eligible = scope()
    totals = {'all_v3_trades': 0, 'terminal_exits_excluded': 0,
              'eligible_exit_events': 0, 'armed_then_new_extreme_exits': 0}
    records = []
    source_names = set(obj(EXIT / 'source_manifest.json')['source']['consumed_files'])
    for n, market in enumerate(eligible.itertuples()):
        tr_rel = f'runs/{market.slug}/H4_D0/full/trades.csv'
        st_rel = f'runs/{market.slug}/H4_D0/full/stops.csv'
        h_rel = f'market/{market.slug}/hourly.parquet'
        assert {tr_rel, st_rel, h_rel} <= source_names
        trades, stops = csv(OLD / tr_rel), csv(OLD / st_rel)
        hourly = pd.read_parquet(OLD / h_rel, columns=['timestamp', 'open', 'high', 'low', 'close', 'eligible', 'is_closed'])
        times = pd.DatetimeIndex(pd.to_datetime(hourly.timestamp, utc=True))
        assert times.is_unique and times.is_monotonic_increasing
        assert (times[1:] - times[:-1] == HOUR).all()
        start, end = pd.Timestamp(market.input_start), pd.Timestamp(market.end)
        assert times[0] == start and times[-1] + HOUR == end
        assert hourly.eligible.all() and hourly.is_closed.all()
        if len(stops):
            stops['timestamp'] = pd.to_datetime(stops.timestamp, utc=True)
            resumed = set(stops.loc[stops.old_armed & stops.new_extreme & stops.full_holding_day, 'trade_id'].astype(int))
        else:
            resumed = set()
        for trade in trades.to_dict('records'):
            totals['all_v3_trades'] += 1
            if trade['exit_reason'] == 'sample_end':
                totals['terminal_exits_excluded'] += 1
                continue
            assert trade['exit_reason'] in {'stop_gap', 'stop_intrahour', 'accel1_rsi30'}
            totals['eligible_exit_events'] += 1
            did_resume = int(trade['trade_id']) in resumed
            totals['armed_then_new_extreme_exits'] += int(did_resume)
            exit_at = pd.Timestamp(trade['exit_time'])
            first = pd.Timestamp(trade['exit_interval_end']) if pd.notna(trade.get('exit_interval_end')) else exit_at
            assert first >= exit_at and first == first.floor('h')
            updates = stops[stops.trade_id == trade['trade_id']]
            assert (updates.timestamp <= exit_at).all()
            price = float(trade['exit_reference'])
            assert price > 0
            side = int(trade['side'])
            for horizon in (5, 10, 20):
                last = first + pd.Timedelta(days=horizon)
                left, right = times.searchsorted(first), times.searchsorted(last)
                post = hourly.iloc[left:right]
                is_complete = (first >= start and last <= end and right - left == 24 * horizon
                               and len(post) > 0 and times[left] == first and times[right - 1] + HOUR == last)
                values = {k: trade[k] for k in ['trade_id', 'side', 'exit_reason', 'exit_time', 'exit_interval_end',
                          'exit_reference', 'entry_time', 'entry_price', 'net_pnl', 'arm_day', 'armed']}
                values.update(symbol=market.symbol, slug=market.slug, cohort=market.cohort,
                              exit_kind='stop' if trade['exit_reason'].startswith('stop') else 'short_rsi_tp',
                              armed_then_new_extreme=did_resume, horizon_days=horizon,
                              followup_start=first.isoformat(), followup_end_exclusive=last.isoformat(),
                              selected_data_end_exclusive=end.isoformat(), available_hours=right-left,
                              required_hours=24*horizon, censored=not is_complete,
                              censor_reason='' if is_complete else ('FROZEN_SEGMENT_END_BEFORE_FULL_FOLLOWUP' if last > end else 'INCOMPLETE_FUTURE_HOURLY_WINDOW'),
                              directional_end_return_pct=np.nan, favorable_excursion_pct=np.nan,
                              adverse_excursion_pct=np.nan, followup_end_close=np.nan)
                if is_complete:
                    close = float(post.close.iloc[-1])
                    low, high = float(post.low.min()), float(post.high.max())
                    signed_low = side * (low-price)/price * 100
                    signed_high = side * (high-price)/price * 100
                    values.update(followup_end_close=close, directional_end_return_pct=side*(close-price)/price*100,
                                  favorable_excursion_pct=max(0., signed_low, signed_high),
                                  adverse_excursion_pct=max(0., -signed_low, -signed_high))
                records.append(values)
        if n % 100 == 99:
            print(f'exit audit {n+1}/611 coins', flush=True)
    expected = pd.DataFrame(records)
    assert len(expected) == 26781 and totals['eligible_exit_events'] == 8927
    event_check = compare(expected, csv(EXIT/'exit_events.csv'), ['symbol', 'trade_id', 'horizon_days'], 'exit events')
    expected_groups, expected_coins = aggregate_exits_independent(expected)
    group_check = compare(expected_groups, csv(EXIT/'exit_summary.csv'), ['cohort', 'exit_group', 'side', 'horizon_days'], 'exit groups')
    coin_check = compare(expected_coins, csv(EXIT/'exit_coin_summary.csv'), ['cohort', 'exit_group', 'side', 'horizon_days', 'symbol'], 'exit coin groups')
    summary = obj(EXIT/'summary.json')
    assert totals == summary['totals'], (totals, summary['totals'])
    compare(expected_groups, pd.DataFrame(summary['groups']), ['cohort', 'exit_group', 'side', 'horizon_days'], 'exit JSON groups')
    return {'status': 'PASS', 'totals': totals, 'cohorts': eligible.cohort.value_counts().to_dict(),
            'events_check': event_check, 'group_check': group_check, 'coin_group_check': coin_check, **integrity}


def aggregate_exits_independent(events):
    med_fields = ['directional_end_return_pct', 'favorable_excursion_pct', 'adverse_excursion_pct']
    expanded = []
    for group in ['stop_all', 'stop_armed_then_refreshed', 'short_rsi_tp']:
        mask = events.exit_kind == ('short_rsi_tp' if group == 'short_rsi_tp' else 'stop')
        if group == 'stop_armed_then_refreshed':
            mask &= events.armed_then_new_extreme
        p = events[mask].copy()
        p['exit_group'] = group
        p['side_group'] = np.where(p.side == 1, 'long', 'short')
        all_sides = p.copy()
        all_sides['side_group'] = 'all'
        expanded.extend([p, all_sides])
    expanded = pd.concat(expanded, ignore_index=True)
    grouping = ['cohort', 'exit_group', 'side_group', 'horizon_days']
    by_group = {key: value for key, value in expanded.groupby(grouping)}
    groups, coins = [], []
    for key in itertools.product(COHORTS, ['stop_all', 'stop_armed_then_refreshed', 'short_rsi_tp'], ['all', 'long', 'short'], [5, 10, 20]):
        selected = by_group.get(key, expanded.iloc[:0])
        good = selected[selected.censored == False]
        row = dict(zip(['cohort', 'exit_group', 'side', 'horizon_days'], key))
        row.update(events_total=len(selected), events_complete=len(good), events_censored=len(selected)-len(good),
                   coins_total=selected.symbol.nunique(), coins_with_complete_events=good.symbol.nunique())
        directional = good.directional_end_return_pct
        for label, mask in [('positive', directional>0), ('negative', directional<0), ('flat', directional==0)]:
            row[f'continuation_{label}_events'] = int(mask.sum())
        row['continuation_positive_pct'] = np.nan if not len(good) else row['continuation_positive_events'] / len(good)*100
        for field in med_fields:
            row['event_median_'+field] = good[field].median()
            row['coin_median_'+field] = good.groupby('symbol')[field].median().median()
        row['event_q25_directional_end_return_pct'] = directional.quantile(.25)
        row['event_q75_directional_end_return_pct'] = directional.quantile(.75)
        groups.append(row)
        for symbol, p in selected.groupby('symbol'):
            valid = p[p.censored == False]
            coin = {k: row[k] for k in ['cohort', 'exit_group', 'side', 'horizon_days']}
            coin.update(symbol=symbol, events_total=len(p), events_complete=len(valid), events_censored=len(p)-len(valid),
                        continuation_positive_events=int((valid.directional_end_return_pct>0).sum()))
            for field in med_fields:
                coin['median_'+field] = valid[field].median()
            coins.append(coin)
    return pd.DataFrame(groups), pd.DataFrame(coins)


def reconstructed_trade_risk(trades, fee, slip):
    q = trades.copy()
    if q.empty:
        return q
    closing_fill = q.initial_stop * (1-q.side*slip)
    cash_loss_per_unit = q.side*q.entry_price-q.side*closing_fill + fee*q.entry_price+fee*closing_fill
    budget = q.qty*cash_loss_per_unit
    q['initial_planned_risk_rebuilt'] = budget
    q['initial_planned_risk_pct_rebuilt'] = budget/q.entry_equity*100
    q['initial_notional_equity_pct'] = q.qty*q.entry_price/q.entry_equity*100
    q['actual_trade_return_pct'] = q.net_pnl/q.entry_equity*100
    q['net_pnl_in_initial_r'] = q.net_pnl/budget.where(budget>0)
    q['initial_stop_nonpositive'] = q.initial_stop<=0
    q['actual_loss_exceeds_half_percent'] = q.actual_trade_return_pct < -.500000001
    q['loss_exceeds_half_percent_before_carry'] = (q.net_pnl+q.carry_paid)/q.entry_equity*100 < -.500000001
    q['carry_pushes_over_half_percent'] = q.actual_loss_exceeds_half_percent & ~q.loss_exceeds_half_percent_before_carry
    q['gap_exit_on_excess'] = q.actual_loss_exceeds_half_percent & q.exit_reason.eq('stop_gap')
    q['execution_worse_than_initial_stop'] = q.side*(q.exit_price-closing_fill) < -1e-10
    return q


def audit_comparison():
    original_scope, eligible = scope()
    record = obj(ANALYSIS/'source_manifest.json')
    consumed_counts = {}
    for directory, key in [(OLD, 'old_source'), (NEW, 'new_source')]:
        manifest_sha = digest(directory/'artifact_checksums.json')
        assert manifest_sha == (OLD_MANIFEST_SHA if directory == OLD else NEW_MANIFEST_SHA)
        assert record[key]['artifact_checksums_sha256'] == manifest_sha
        all_hashes = obj(directory/'artifact_checksums.json')
        for relative, sha in record[key]['consumed_files'].items():
            assert all_hashes[relative] == sha
        consumed_counts[key] = len(record[key]['consumed_files'])
    analysis_hashes = obj(ANALYSIS/'artifact_checksums.json')
    needed = ['ranking.csv', 'cohort_summary.csv', 'paired_comparisons.csv', 'coin_paired_comparisons.csv',
              'candidates.csv', 'summary.json', 'risk_trade_events.csv', 'risk_summary.csv', 'risk_summary.json', 'source_manifest.json']
    data_hashes = {}
    for relative in needed:
        data_hashes[relative] = digest(ANALYSIS/relative)
        assert data_hashes[relative] == analysis_hashes[relative]
    for relative in ['summary.csv', 'stress.csv', 'scope.csv']:
        for directory, key in [(OLD, 'old_source'), (NEW, 'new_source')]:
            assert relative in record[key]['consumed_files']
    s_old, s_new = csv(OLD/'summary.csv'), csv(NEW/'summary.csv')
    stress_old, stress_new = csv(OLD/'stress.csv'), csv(NEW/'stress.csv')
    assert len(s_new)==15201 and len(stress_new)==10998
    assert set(s_new.case_id)==set(CASES)-{'V1','V3'}
    assert set(stress_new.case_id)==set(CASES)-{'V1','V3'}
    compare(original_scope, csv(NEW/'scope.csv'), ['symbol'], 'source scopes',
            ['cohort','trade_days','trade_start','end','boundary_end_due_to_data'])
    expected, risk_frames = [], []
    risk_keep = ['trade_id','side','entry_time','exit_time','exit_reason','entry_equity','entry_price','exit_price','initial_stop','qty','net_pnl','carry_paid',
                 'initial_planned_risk_rebuilt','initial_planned_risk_pct_rebuilt','initial_notional_equity_pct','actual_trade_return_pct','net_pnl_in_initial_r',
                 'initial_stop_nonpositive','actual_loss_exceeds_half_percent','loss_exceeds_half_percent_before_carry','carry_pushes_over_half_percent',
                 'gap_exit_on_excess','execution_worse_than_initial_stop']
    trade_rows_checked = 0
    for case in CASES:
        directory, source_key, cid = (OLD,'old_source','H4_D0' if case=='V3' else 'F0') if case in {'V1','V3'} else (NEW,'new_source',case)
        summary = s_old if directory==OLD else s_new
        stresses = stress_old if directory==OLD else stress_new
        windows = summary[summary.case_id==cid].set_index(['symbol','window'])
        scenario_rows = stresses[stresses.case_id==cid].set_index(['symbol','scenario'])
        assert windows.index.is_unique and scenario_rows.index.is_unique
        full = windows.xs('full',level='window')
        assert len(full)==611 and set(full.index)==set(eligible.symbol)
        for symbol, src in full.iterrows():
            item = src.to_dict()
            item.update(symbol=symbol, case_id=case, zero_trades=src.trades==0)
            for period in ['early60','late40']:
                p = windows.loc[(symbol,period)] if (symbol,period) in windows.index else None
                for field in ['return_pct','max_drawdown_pct','trades','exposure_pct']:
                    item[period+'_'+field] = p[field] if p is not None else np.nan
            for scenario in ['slippage_10bp','carry_5bp_day']:
                p = scenario_rows.loc[(symbol,scenario)]
                for field in ['return_pct','max_drawdown_pct','trades','bankrupt','exposure_pct']:
                    item[scenario+'_'+field] = p[field]
            tr_path = f'runs/{src.slug}/{cid}/full/trades.csv'
            assert tr_path in record[source_key]['consumed_files']
            tr = reconstructed_trade_risk(csv(directory/tr_path), float(src.fee), float(src.slip))
            assert len(tr)==src.trades
            trade_rows_checked += len(tr)
            pnl = tr.net_pnl if len(tr) else pd.Series(dtype=float)
            assert np.isclose(10000+pnl.sum(),src.ending_equity,rtol=0,atol=1e-6)
            item.update(winning_trades=int((pnl>0).sum()), losing_trades=int((pnl<0).sum()), flat_trades=int((pnl==0).sum()))
            for direction, number in [('long',1),('short',-1)]:
                directional = tr.loc[tr.side==number] if len(tr) else tr
                item[direction+'_trade_return_median_pct'] = (directional.return_on_entry_equity*100).median() if len(directional) else np.nan
                assert src[direction+'_trades']==len(directional)
            mappings = {'initial_stop_distance_median_pct':'initial_stop_risk_pct',
                        'initial_notional_equity_median_pct':'initial_notional_equity_pct',
                        'initial_planned_risk_median_pct':'initial_planned_risk_pct_rebuilt',
                        'net_pnl_initial_r_median':'net_pnl_in_initial_r'}
            for out, field in mappings.items():
                item[out] = tr[field].median() if len(tr) else np.nan
            item['loss_exceeds_half_percent_trades'] = int(tr.actual_loss_exceeds_half_percent.sum()) if len(tr) else 0
            item['initial_stop_nonpositive_trades'] = int(tr.initial_stop_nonpositive.sum()) if len(tr) else 0
            item['risk_count_pass'] = bool(src.trade_days>=180 and src.trades>=10 and src.return_pct>0 and src.max_drawdown_pct>=-30 and not src.bankrupt)
            item['stable_candidate'] = bool(item['risk_count_pass'] and item['early60_return_pct']>0 and item['late40_return_pct']>0
                and item['early60_trades']>=3 and item['late40_trades']>=3 and item['slippage_10bp_return_pct']>0 and item['carry_5bp_day_return_pct']>0)
            expected.append(item)
            if case in {'V3','C_RISK005','C_SMALL'}:
                for scenario in ['full','slippage_10bp','carry_5bp_day']:
                    p = src if scenario=='full' else scenario_rows.loc[(symbol,scenario)]
                    if scenario=='full':
                        risk = tr
                    else:
                        risk_path = f'sensitivity/{src.slug}/{cid}/{scenario}/trades.csv'
                        assert risk_path in record[source_key]['consumed_files']
                        risk = reconstructed_trade_risk(csv(directory/risk_path),float(p.fee),float(p.slip))
                    if not len(risk):
                        continue
                    if case=='C_RISK005':
                        assert (risk.initial_planned_risk_pct_rebuilt<=.500000001).all()
                        assert (risk.initial_notional_equity_pct<=100.000000001).all()
                    frame = risk[risk_keep].copy()
                    frame['symbol'], frame['slug'], frame['cohort'] = symbol, src.slug, src.cohort
                    frame['case_id'], frame['scenario'] = case, scenario
                    risk_frames.append(frame)
        print(f'comparison audit {case}: 611 coins',flush=True)
    expected = pd.DataFrame(expected)
    actual = csv(ANALYSIS/'ranking.csv')
    ignored = {'label','window'}
    columns = [col for col in expected.columns if col not in ignored|{'symbol','case_id'}]
    # Source-row metadata that is renamed for display is not a financial claim.
    rank_check = compare(expected, actual, ['symbol','case_id'], 'ranking', columns)
    cohorts = independent_cohorts(expected)
    pair_groups, pair_coins = independent_pairs(expected)
    cohort_check = compare(cohorts,csv(ANALYSIS/'cohort_summary.csv'),['cohort','case_id'],'cohort summary')
    paired_check = compare(pair_groups,csv(ANALYSIS/'paired_comparisons.csv'),['cohort','comparison'],'paired groups')
    paired_coins_check = compare(pair_coins,csv(ANALYSIS/'coin_paired_comparisons.csv'),['cohort','symbol','comparison'],'paired coins')
    candidates = expected[expected.risk_count_pass]
    candidate_check = compare(candidates,csv(ANALYSIS/'candidates.csv'),['symbol','case_id'],'candidates',
                              ['cohort','return_pct','max_drawdown_pct','trades','risk_count_pass','stable_candidate'])
    risk_events = pd.concat(risk_frames,ignore_index=True)
    risk_event_check = compare(risk_events,csv(ANALYSIS/'risk_trade_events.csv'),['case_id','symbol','scenario','trade_id'],'risk trades')
    risk_groups = independent_risk_groups(risk_events)
    risk_group_check = compare(risk_groups,csv(ANALYSIS/'risk_summary.csv'),['cohort','case_id','scenario','exit_reason'],'risk groups')
    summary = obj(ANALYSIS/'summary.json')
    compare(cohorts,pd.DataFrame(summary['cohorts']),['cohort','case_id'],'JSON cohorts')
    compare(pair_groups,pd.DataFrame(summary['paired_comparisons']),['cohort','comparison'],'JSON pairs')
    compare(risk_groups,pd.DataFrame(obj(ANALYSIS/'risk_summary.json')['groups']),['cohort','case_id','scenario','exit_reason'],'JSON risk groups')
    assert summary['candidate_coins']==652 and summary['completed_coins']==611 and summary['excluded_price_coins']==41
    assert summary['full_account_count']==len(expected)==6721
    assert summary['all_full_period_trades']==trade_rows_checked
    return {'status':'PASS','ranking':rank_check,'cohorts':cohort_check,'paired_groups':paired_check,
            'paired_coins':paired_coins_check,'candidates':candidate_check,'risk_events':risk_event_check,
            'risk_groups':risk_group_check,'full_trade_rows_recomputed':trade_rows_checked,
            'source_consumed_hashes_matched':consumed_counts,'analysis_data_sha256':data_hashes,
            'html_sha256_observed':digest(ANALYSIS/'index.html'),'browser_visual_qa_performed':False}


def independent_cohorts(rank):
    rows=[]
    median_map={'median_return_pct':'return_pct','median_max_drawdown_pct':'max_drawdown_pct',
                'median_exposure_pct':'exposure_pct','median_trades':'trades',
                'median_long_trade_return_pct':'long_trade_return_median_pct','median_short_trade_return_pct':'short_trade_return_median_pct',
                'median_initial_stop_distance_pct':'initial_stop_distance_median_pct','median_initial_notional_equity_pct':'initial_notional_equity_median_pct',
                'median_initial_planned_risk_pct':'initial_planned_risk_median_pct','median_net_pnl_initial_r':'net_pnl_initial_r_median'}
    summed=['winning_trades','losing_trades','flat_trades','long_trades','short_trades','loss_exceeds_half_percent_trades','initial_stop_nonpositive_trades']
    entries=['flat_ready_crosses','flat_not_ready_crosses','entry_attempts','entry_fills','slope_rejected','direction_rejected',
             'ma30_not_ready_rejected','ma30_direction_rejected','invalid_stop_rejected','nonpositive_equity_rejected','invalid_unit_risk_rejected']
    for (cohort,case),p in rank.groupby(['cohort','case_id']):
        r={'cohort':cohort,'case_id':case,'coins':len(p),'positive_coins':int((p.return_pct>0).sum()),
           'negative_coins':int((p.return_pct<0).sum()),'flat_coins':int((p.return_pct==0).sum()),
           'zero_trade_coins':int((p.trades==0).sum()),'positive_pct':float((p.return_pct>0).mean()*100),
           'worst_max_drawdown_pct':float(p.max_drawdown_pct.min()),'all_trades':int(p.trades.sum()),
           'risk_count_pass_coins':int(p.risk_count_pass.sum()),'stable_candidate_coins':int(p.stable_candidate.sum()),
           'bankrupt_coins':int(p.bankrupt.sum()),'both_subperiods_positive_coins':int(((p.early60_return_pct>0)&(p.late40_return_pct>0)).sum())}
        for out,field in median_map.items():r[out]=p[field].median()
        for field in summed:r[field]=int(p[field].sum())
        for field in entries:r['all_'+field]=p[field].sum() if p[field].notna().any() else np.nan
        for scenario in ['slippage_10bp','carry_5bp_day','early60','late40']:
            r['median_'+scenario+'_return_pct']=p[scenario+'_return_pct'].median()
        rows.append(r)
    assert len(rows)==33
    return pd.DataFrame(rows)


def independent_pairs(rank):
    groups,coins=[],[]
    indexed=rank.set_index(['case_id','cohort','symbol']).sort_index()
    epsilon=1e-9
    for new_case,old_case in PAIRS:
        for cohort in COHORTS:
            a,b=indexed.loc[(new_case,cohort)],indexed.loc[(old_case,cohort)]
            assert a.index.equals(b.index)
            return_delta=a.return_pct-b.return_pct
            # Signed drawdowns are negative, so a larger value is a reduction.
            dd_delta=a.max_drawdown_pct-b.max_drawdown_pct
            row={'cohort':cohort,'comparison':new_case+'-'+old_case,'newer_case':new_case,'older_case':old_case,'coins':len(a),
                 'return_up_coins':int((return_delta>epsilon).sum()),'return_down_coins':int((return_delta< -epsilon).sum()),
                 'return_same_coins':int((return_delta.abs()<=epsilon).sum()),'drawdown_improved_coins':int((dd_delta>epsilon).sum()),
                 'drawdown_worse_coins':int((dd_delta< -epsilon).sum()),'drawdown_same_coins':int((dd_delta.abs()<=epsilon).sum()),
                 'return_up_drawdown_not_worse_coins':int(((return_delta>epsilon)&(dd_delta>=-epsilon)).sum()),
                 'both_strictly_improved_coins':int(((return_delta>epsilon)&(dd_delta>epsilon)).sum()),
                 'median_paired_return_change_pp':return_delta.median(),'median_paired_drawdown_reduction_pp':dd_delta.median(),
                 'median_paired_exposure_change_pp':(a.exposure_pct-b.exposure_pct).median(),
                 'median_paired_trade_count_change':(a.trades-b.trades).median(),
                 'older_nonpositive_newer_positive_coins':int(((b.return_pct<=0)&(a.return_pct>0)).sum()),
                 'older_positive_newer_nonpositive_coins':int(((b.return_pct>0)&(a.return_pct<=0)).sum()),
                 'both_positive_coins':int(((b.return_pct>0)&(a.return_pct>0)).sum()),
                 'both_nonpositive_coins':int(((b.return_pct<=0)&(a.return_pct<=0)).sum())}
            groups.append(row)
            for symbol in a.index:
                coins.append(dict(cohort=cohort,symbol=symbol,comparison=row['comparison'],newer_case=new_case,older_case=old_case,
                                  return_change_pp=return_delta.loc[symbol],drawdown_reduction_pp=dd_delta.loc[symbol],
                                  exposure_change_pp=a.loc[symbol,'exposure_pct']-b.loc[symbol,'exposure_pct'],
                                  trade_count_change=int(a.loc[symbol,'trades']-b.loc[symbol,'trades'])))
    assert len(groups)==33 and len(coins)==6721
    return pd.DataFrame(groups),pd.DataFrame(coins)


def independent_risk_groups(events):
    rows=[]
    for (cohort,case,scenario),part in events.groupby(['cohort','case_id','scenario']):
        for label in ['ALL_EXITS']+sorted(set(part.exit_reason)):
            p=part if label=='ALL_EXITS' else part[part.exit_reason==label]
            breach=p.actual_loss_exceeds_half_percent
            r=dict(cohort=cohort,case_id=case,scenario=scenario,exit_reason=label,trades=len(p),coins=p.symbol.nunique(),
                   planned_risk_median_pct=p.initial_planned_risk_pct_rebuilt.median(),notional_equity_median_pct=p.initial_notional_equity_pct.median(),
                   planned_risk_coin_median_pct=p.groupby('symbol').initial_planned_risk_pct_rebuilt.median().median(),
                   notional_equity_coin_median_pct=p.groupby('symbol').initial_notional_equity_pct.median().median(),
                   net_pnl_initial_r_median=p.net_pnl_in_initial_r.median(),net_pnl_initial_r_coin_median=p.groupby('symbol').net_pnl_in_initial_r.median().median(),
                   initial_stop_nonpositive_trades=int(p.initial_stop_nonpositive.sum()),initial_stop_nonpositive_coins=p[p.initial_stop_nonpositive].symbol.nunique(),
                   loss_exceeds_half_percent_trades=int(breach.sum()),loss_exceeds_half_percent_pct=breach.mean()*100,
                   loss_exceeds_half_percent_coins=p[breach].symbol.nunique(),max_actual_loss_pct=max(0.,-p.actual_trade_return_pct.min()),
                   breach_before_carry_trades=int(p.loss_exceeds_half_percent_before_carry.sum()),
                   carry_pushes_over_half_percent_trades=int(p.carry_pushes_over_half_percent.sum()),
                   gap_exit_on_excess_trades=int(p.gap_exit_on_excess.sum()),
                   execution_worse_than_initial_stop_on_excess_trades=int((breach&p.execution_worse_than_initial_stop).sum()))
            rows.append(r)
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exits-only', action='store_true')
    parser.add_argument('--reuse-exits', action='store_true')
    args = parser.parse_args()
    report = {'status': 'IN_PROGRESS', 'audit_script_sha256': digest(Path(__file__)),
              'strategy_backtest_performed': False, 'browser_visual_qa_performed': False}
    try:
        if args.reuse_exits:
            prior = obj(OUTPUT)
            assert prior['exits']['status'] == 'PASS'
            for name, sha in prior['exits']['exit_artifact_hashes'].items():
                assert digest(EXIT/name) == sha, name
            report['exits'] = prior['exits']
            report['exit_check_reused_from_prior_pass'] = True
        else:
            report['exits'] = audit_exits()
        if args.exits_only:
            report['status'] = 'EXIT_AUDIT_PASS_COMPARISON_PENDING'
        else:
            report['comparison'] = audit_comparison()
            report['status'] = 'PASS'
    except Exception:
        report['status'] = 'FAIL'
        report['failure'] = traceback.format_exc()
        raise
    finally:
        report['completed_at_utc'] = pd.Timestamp.now(tz='UTC').isoformat()
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(finite_json(report), ensure_ascii=False, indent=2, allow_nan=False)+'\n')
        print(json.dumps({k: v for k, v in report.items() if k in ['status', 'failure']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
