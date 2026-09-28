"""Independent source-to-analysis and all-page data checks; offline JS only."""
from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

import numpy as np
import pandas as pd

from v3_opportunity_inputs_20260913 import ROOT, BASE, R, load_sources, table, sha, write_json

OUT = R/'delivery_audit'
ARMS = ['V3', 'E_STATE', 'TP_PROTECT']
EVENTS = ['crosses', 'natural_exits', 'stagnation4', 'short_tp']


def manifest(directory):
    m = json.loads((directory/'artifact_checksums.json').read_text())
    for rel, digest in m.items():
        assert sha(directory/rel) == digest, directory/rel
    return m


def data_from_page(path):
    source = path.read_text()
    start = source.index('<script>const DATA=') + len('<script>const DATA=')
    end = source.index(';\nconst $=', start)
    data = json.loads(source[start:end])
    assert len(re.findall(r'<script(?:\s|>)', source)) == 1
    assert not re.search(r'<(?:script|link|img)[^>]+(?:src|href)=["\']https?://', source)
    return data, source


def equal_value(actual, expected):
    if expected is None or expected is pd.NaT or (not isinstance(expected, (str, list, dict)) and pd.isna(expected)):
        assert actual is None, (actual, expected)
    elif isinstance(expected, (pd.Timestamp, np.datetime64)):
        assert actual == pd.Timestamp(expected).value // 1_000_000
    elif isinstance(expected, (bool, np.bool_)):
        assert actual is bool(expected), (actual, expected)
    elif isinstance(expected, (int, float, np.number)):
        assert np.isclose(actual, expected, rtol=2e-13, atol=1e-12), (actual, expected)
    else:
        assert actual == expected, (actual, expected)


def assert_rows(actual, frame, columns):
    assert len(actual) == len(frame), (len(actual), len(frame), columns)
    if not len(frame):
        return  # Original empty segment files may have no columns at all.
    data=np.asarray(actual,dtype=object)
    assert data.shape==(len(frame),len(columns))
    for i,column in enumerate(columns):
        s=frame[column]
        if pd.api.types.is_datetime64_any_dtype(s):
            expected=pd.DatetimeIndex(s).as_unit('ns').asi8.astype(float)/1e6
            expected[s.isna()]=np.nan
            assert np.allclose(np.asarray(data[:,i],dtype=float),expected,rtol=0,atol=0,equal_nan=True),column
        elif pd.api.types.is_numeric_dtype(s):
            assert np.allclose(np.asarray(data[:,i],dtype=float),s.to_numpy(float),rtol=2e-13,atol=1e-12,equal_nan=True),column
        else:
            for value,original in zip(data[:,i],s):
                equal_value(value,original)


def period_checks():
    out = R/'analysis'
    a = table(out/'period_accounts.csv'); s = table(out/'period_summary.csv')
    blocks = [table(R/'inputs/baseline_blocks.csv')]
    segments = [table(R/'inputs/baseline_summary.csv')]
    for arm in ARMS[1:]:
        blocks.append(table(R/'accounts'/arm/'blocks.csv'))
        segments.append(table(R/'accounts'/arm/'summary.csv'))
    b = pd.concat(blocks, ignore_index=True); source_s = pd.concat(segments, ignore_index=True)
    assert len(source_s) == 2925
    key = ['run_key', 'case_id', 'block', 'status']
    wanted = b[b.status.ne('NO_OVERLAP')].copy()
    actual = a[a.block.ne('full_segment')].copy()
    assert not wanted.duplicated(key).any() and not actual.duplicated(key).any()
    merged = actual.merge(wanted, on=key, how='outer', suffixes=('_shown', '_source'), indicator=True)
    assert merged._merge.eq('both').all()
    for field in ['return_pct', 'max_drawdown_pct']:
        assert np.allclose(merged[field+'_shown'], merged[field+'_source'], rtol=1e-13, atol=1e-12, equal_nan=True)
    for field in ['actual_start', 'actual_end']:
        assert pd.to_datetime(merged[field+'_shown'], utc=True).equals(pd.to_datetime(merged[field+'_source'], utc=True))
    full = a[a.block.eq('full_segment')].merge(source_s, on=['run_key', 'case_id'], suffixes=('_shown', '_source'))
    assert len(full) == 2925
    for field in ['return_pct', 'max_drawdown_pct']:
        assert np.allclose(full[field+'_shown'], full[field+'_source'], rtol=1e-13, atol=1e-12, equal_nan=True)
    controls = a[a.case_id.eq('V3')].set_index(['run_key', 'block', 'status'])
    for row in a.itertuples(index=False):
        base = controls.loc[(row.run_key, row.block, row.status)]
        assert np.isclose(row.return_change_pp, row.return_pct-base.return_pct, rtol=1e-12, atol=1e-11, equal_nan=True)
        assert np.isclose(row.drawdown_reduction_pp, abs(base.max_drawdown_pct)-abs(row.max_drawdown_pct), rtol=1e-12, atol=1e-11, equal_nan=True)
    groups = a.groupby(['block', 'status', 'case_id'])
    for row in s.itertuples(index=False):
        g = groups.get_group((row.block, row.status, row.case_id))
        assert row.coins == g.slug.nunique() and row.segments == len(g)
        assert row.profitable == ((g.return_pct>1e-10)&g.participating_trades.gt(0)).sum()
        assert row.losing == (g.return_pct < -1e-10).sum()
        assert row.zero_trades == g.participating_trades.eq(0).sum()
        assert row.improved == g.return_change_pp.gt(1e-10).sum()
        assert row.worsened == g.return_change_pp.lt(-1e-10).sum()
        assert row.trades == g.closed_trades.sum()
        for shown, field, absolute in [('median_return_pct','return_pct',False),
             ('median_drawdown_pct','max_drawdown_pct',True), ('median_payoff','payoff_ratio',False),
             ('median_unit_payoff','unit_payoff_ratio',False), ('median_delta_pp','return_change_pp',False)]:
            value = getattr(row, shown)
            if row.status != 'COMPLETE':
                assert pd.isna(value)
            else:
                assert not g.slug.duplicated().any()
                vals = g[field].abs() if absolute else g[field]
                expected = vals.median()
                assert (pd.isna(value) and pd.isna(expected)) or np.isclose(value, expected, rtol=1e-12, atol=1e-12)
    return {'period_rows':len(a), 'period_summary_rows':len(s), 'full_segment_accounts':len(full),
            'source_blocks_equal':True, 'summary_recomputed':True, 'partial_medians_not_reported':True}


def entry_change_checks(sources):
    expected = []
    for key, info in sources.items():
        old = table(ROOT/info['baseline_dir']/'trades.csv')
        new = table(R/'accounts/E_STATE/runs'/key/'E_STATE/full/trades.csv')
        maps = []
        for t in [old,new]:
            maps.append({(pd.Timestamp(row['cross_day']),int(row['side'])):row for row in t.to_dict('records')})
            assert len(maps[-1]) == len(t)
        a,b = maps
        for signal in set(a)|set(b):
            x,y=a.get(signal),b.get(signal)
            relation = ('same_entry' if x and y and pd.Timestamp(x['entry_time'])==pd.Timestamp(y['entry_time'])
                        else 'shifted_entry' if x and y else 'new_cross_entry' if y else 'baseline_cross_missed')
            expected.append({'run_key':key,'cross_day':signal[0],'side':signal[1],'relationship':relation,
                             'baseline_return':x['return_on_entry_equity'] if x else np.nan,
                             'new_return':y['return_on_entry_equity'] if y else np.nan})
    want=pd.DataFrame(expected)
    got=table(R/'accounts/E_STATE/entry_comparison.csv')
    key=['run_key','cross_day','side']
    merged=want.merge(got,on=key,how='outer',suffixes=('_want','_shown'),indicator=True,validate='one_to_one')
    assert merged._merge.eq('both').all()
    assert merged.relationship_want.eq(merged.relationship_shown).all()
    for name in ['baseline_return','new_return']:
        assert np.allclose(merged[name+'_want'],merged[name+'_shown'],rtol=1e-13,atol=1e-13,equal_nan=True)
    same=want[want.relationship.eq('same_entry')]
    return {'relationship_counts':want.relationship.value_counts().to_dict(),
            'original_entries':int(want.baseline_return.notna().sum()),
            'new_entries':int(want.new_return.notna().sum()),
            'same_entry_max_abs_unit_return_difference':float((same.new_return-same.baseline_return).abs().max()),
            'independently_reconstructed_from_original_and_new_trade_logs':True,
            'not_fixed_original_quantity_or_equity_comparison':True}


def html_checks(sources):
    h = R/'html'; scope = table(R/'inputs/universe_scope.csv')
    wanted = set(scope.slug)
    pages = list((h/'coins').glob('*.html'))
    assert len(pages) == 680 and {p.stem for p in pages} == wanted
    main, text = data_from_page(h/'index.html')
    for name, file in [('accounts','period_accounts.csv'), ('sums','period_summary.csv'),
                       ('groups','opportunity_groups.csv')]:
        frame = table(R/'analysis'/file)
        # JSON date strings preserve the builder's ISO representation; all
        # numeric values and ordering are checked independently below.
        assert len(main[name]) == len(frame)
        for shown, original in zip(main[name], frame.to_dict('records')):
            assert set(shown) == set(original)
            for field, value in original.items():
                if isinstance(value, pd.Timestamp):
                    assert pd.Timestamp(shown[field]) == value
                else:
                    equal_value(shown[field], value)
    assert {r['slug'] for r in main['scope']} == wanted
    assert len(main['pairs']) == len(table(R/'pairs/summary.csv'))
    counts = dict(pages=681, segments=0, bars=0, crosses=0, events=0, candidates=0,
                  trades={arm:0 for arm in ARMS}, stops={arm:0 for arm in ARMS})
    issues = []
    for path in [h/'index.html', *pages]:
        data, page_text = (main,text) if path.name == 'index.html' else data_from_page(path)
        for link in re.findall(r'href=["\']([^"\']+)["\']', page_text.split('<script>')[0]):
            if link.startswith(('#','http:','https:','javascript:')):
                continue
            target = (path.parent/unquote(link.split('#')[0])).resolve()
            if not target.exists():
                issues.append({'page':str(path.relative_to(ROOT)), 'missing_link':link})
        if path.name == 'index.html':
            continue
        expected_keys = {key for key,s in sources.items() if s['slug'] == path.stem}
        assert set(data['segments']) == expected_keys
        for key, seg in data['segments'].items():
            info = sources[key]
            assert sha(ROOT/info['daily_source']) == info['daily_sha256']
            daily = pd.read_parquet(ROOT/info['daily_source'])
            assert_rows(seg['bars'], daily, ['timestamp','open','high','low','close','ma','ma30'])
            counts['segments'] += 1; counts['bars'] += len(seg['bars'])
            for arm in ARMS:
                directory = ROOT/info['baseline_dir'] if arm == 'V3' else R/'accounts'/arm/'runs'/key/arm/'full'
                if arm == 'V3':
                    for name in ['trades.csv','stops.csv','entry_events.csv']:
                        assert sha(directory/name) == info['baseline_sha256'][name]
                t, s, e = [table(directory/name) for name in ['trades.csv','stops.csv','entry_events.csv']]
                cols = ['trade_id','entry_time','exit_time','side','entry_price','exit_price','net_pnl','return_on_entry_equity','exit_reason']
                if len(t): assert_rows(seg['trades'][arm], t, cols)
                else: assert not seg['trades'][arm]
                if len(s):
                    s['state'] = 'V3原止损'
                    if 'tp_protect_active' in s:
                        s.loc[s.tp_protect_active.fillna(False).astype(bool), 'state'] = '空单保护已启动'
                    assert_rows(seg['stops'][arm], s, ['trade_id','timestamp','new_stop','state'])
                else: assert not seg['stops'][arm]
                counts['trades'][arm] += len(t); counts['stops'][arm] += len(s)
                if arm == 'E_STATE' and len(e):
                    q = e[e.stage.eq('candidate')]
                    assert_rows(seg['candidates'][arm], q, ['timestamp','cross_day','side','status','reason','candidate_age_days'])
                    counts['candidates'] += len(q)
                else:
                    assert not seg['candidates'][arm]
            dc = {name:pd.read_parquet(R/'diagnostics/segments'/key/(name+'.parquet')) for name in EVENTS}
            q = dc['crosses']
            assert_rows(seg['crosses'], q, ['event_time','side','entry_disposition','slope_direction','actual_trade_id',
                        'f20_complete','f20_hypothetical_net_return','f20_mfe_atr','f20_mae_atr','f20_first_2atr'])
            counts['crosses'] += len(q)
            q = pd.concat([dc[n] for n in EVENTS if n != 'crosses'], ignore_index=True)
            if len(q):
                assert_rows(seg['events'], q, ['event_time','event_type','actual_trade_id','actual_unit_return',
                            'f20_complete','f20_directional_close_pct','f20_mfe_atr','f20_mae_atr',
                            'f20_old_extreme_recovered','f20_recovery_first_day'])
            else: assert not seg['events']
            counts['events'] += len(q)
        if len(counts['trades']) and counts['segments'] % 100 == 0:
            print('Checked HTML segments',counts['segments'],flush=True)
    assert counts['segments'] == 975 and counts['trades']['V3'] == 22028
    counts['unresolved_local_links'] = issues
    counts['empty_coin_pages'] = scope.loc[scope.segments_with_trading_window.eq(0),'slug'].tolist()
    counts['all_displayed_prices_returns_and_states_equal_saved_sources'] = True
    return counts


def main():
    assert json.loads((R/'analysis/completion.json').read_text())['complete']
    assert json.loads((R/'html/completion.json').read_text())['complete']
    assert not (OUT/'completion.json').exists(), 'Never overwrite completed audit'
    OUT.mkdir(parents=True,exist_ok=True)
    files = [Path(__file__), Path(__file__).with_name('audit_v3_opportunity_dom_20260913.js'),
             Path(__file__).with_name('build_v3_opportunity_report_20260913.py'),
             Path(__file__).with_name('build_v3_opportunity_html_20260913.py'),
             Path(__file__).with_name('build_ma30_report_20260911.py')]
    pins = {str(p.relative_to(ROOT)):sha(p) for p in files}
    write_json(OUT/'started.json',{'utc':str(pd.Timestamp.now(tz='UTC')),'pins':pins,
                                 'browser_used':False,'offline_dom_canvas_only':True})
    for folder in [R/'inputs',R/'diagnostics',R/'analysis',R/'html',R/'pairs',
                   R/'accounts/E_STATE',R/'accounts/TP_PROTECT']:
        manifest(folder)
    sources=load_sources()
    write_json(OUT/'period_checks.json',period_checks())
    write_json(OUT/'entry_change_checks.json',entry_change_checks(sources))
    write_json(OUT/'html_data_checks.json',html_checks(sources))
    subprocess.run(['node',str(Path(__file__).with_name('audit_v3_opportunity_dom_20260913.js')),
                    str(R/'html'),str(OUT/'dom_checks.json')],check=True)
    links = json.loads((OUT/'html_data_checks.json').read_text())['unresolved_local_links']
    write_json(OUT/'completion.json',{'complete':not links,'data_and_period_checks_passed':True,
               'offline_interactions_passed':True,'browser_render_verified':False,
               'unresolved_local_links':links,'source_pins':pins})
    write_json(OUT/'artifact_checksums.json',{str(p.relative_to(OUT)):sha(p)
               for p in OUT.rglob('*') if p.is_file() and p.name!='artifact_checksums.json'})
    assert not links, links
    print('Delivery audit passed; no real browser rendering claimed.',flush=True)


if __name__ == '__main__':main()
