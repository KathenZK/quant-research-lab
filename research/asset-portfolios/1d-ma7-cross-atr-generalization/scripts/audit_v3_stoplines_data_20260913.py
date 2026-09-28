"""Independent read-only checks of the stop-line presentation repair.

Compares original HTML payloads and frozen CSVs; does not import the renderer
or strategy engine. No market data are downloaded or recalculated.
"""
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
R = ROOT / 'research/asset-portfolios/1d-ma7-cross-atr-generalization/artifacts/v3_opportunity_20260913'
OUT = R / 'ui_stoplines_audit'
FIELDS = ['trade_id', 'timestamp', 'signal_day', 'old_mult', 'new_mult',
          'tightened', 'no_new_extreme_days', 'new_armed', 'old_stop', 'new_stop',
          'extreme_price', 'tp_protect_active', 'tp_protect_candidate',
          'expected_profit_at_close', 'full_holding_day']
BOOL = {'tightened', 'new_armed', 'tp_protect_active', 'full_holding_day'}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def payload(p):
    s = p.read_text()
    return json.JSONDecoder().raw_decode(s.split('const DATA=', 1)[1])[0]


def value(s, field):
    if s in (None, '', 'nan', 'NaN'):
        return None
    if field in BOOL:
        assert str(s).lower() in ('true', 'false'), (field, s)
        return str(s).lower() == 'true'
    if field in ('timestamp', 'signal_day'):
        return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp() * 1000)
    return float(s)


def equal(a, b, context):
    if a is None or b is None or isinstance(a, bool) or isinstance(b, bool):
        assert a == b, (context, a, b)
    else:
        assert math.isclose(float(a), float(b), rel_tol=2e-13, abs_tol=1e-12), (context, a, b)


def main():
    counts = Counter()
    sources = json.loads((R / 'inputs/sources.json').read_text())
    original_manifest = json.loads((R / 'html/artifact_checksums.json').read_text())
    for rel, expected in original_manifest.items():
        assert sha(R / 'html' / rel) == expected, ('old HTML changed', rel)
    for oldfile in sorted((R / 'html/coins').glob('*.html')):
        newfile = R / 'html_stoplines/coins' / oldfile.name
        old, new = payload(oldfile), payload(newfile)
        for k, v in old.items():
            if k != 'segments':
                assert new[k] == v, (oldfile.stem, k)
        assert set(old['segments']) == set(new['segments'])
        for key, oldseg in old['segments'].items():
            seg = new['segments'][key]
            for k, v in oldseg.items():
                assert seg[k] == v, (key, 'original field changed', k)
            for arm in old['names']:
                details = seg['stopDetails'][arm]
                stoprows = seg['stops'][arm]
                assert len(details) == len(stoprows), (key, arm, 'length')
                src = ROOT / sources[key]['baseline_dir'] if arm == 'V3' else R / 'accounts' / arm / 'runs' / key / arm / 'full'
                with (src / 'stops.csv').open(newline='') as fh:
                    csvrows = list(csv.DictReader(fh))
                assert len(csvrows) == len(details), (key, arm, 'CSV length')
                trades = {t[0]: t for t in seg['trades'][arm]}
                previous = {}
                for i, (p, s, raw) in enumerate(zip(details, stoprows, csvrows)):
                    for j, field in enumerate(FIELDS):
                        # Original V3 has no protection field; its explicit UI state is off.
                        expected = False if field == 'tp_protect_active' and field not in raw else value(raw.get(field), field)
                        equal(p[j], expected, (key, arm, i, field))
                    assert p[0] == s[0] and p[1] == s[1]
                    equal(p[9], s[2], (key, arm, i, 'displayed stop'))
                    t = trades[p[0]]
                    assert t[1] <= p[1] <= t[2], (key, arm, i, 'outside holding')
                    assert p[1] == p[2] + 86400000, (key, arm, i, 'not next-day effective')
                    assert .5 - 1e-12 <= p[4] <= 1.5 + 1e-12
                    if p[0] in previous:
                        prev = previous[p[0]]
                        assert p[1] >= prev[1]
                        assert p[4] <= prev[4] + 1e-12, (key, arm, i, 'ATR widened')
                        assert t[3] * (p[9] - prev[9]) >= -1e-9 * max(1, abs(p[9])), (key, arm, i, 'stop widened')
                    previous[p[0]] = p
                    counts['stop_records'] += 1
                    counts['ATR_reductions'] += bool(p[5])
                counts['accounts'] += 1
                counts['trades'] += len(trades)
            counts['segments'] += 1
        counts['coin_pages'] += 1
    assert counts['coin_pages'] == 680 and counts['segments'] == 975
    OUT.mkdir(exist_ok=True)
    result = {'complete': True, 'method': 'Independent original-payload and frozen-CSV comparison',
              'counts': dict(counts), 'all_original_html_checksums_unchanged': True,
              'all_original_embedded_data_unchanged': True,
              'effective_next_day_and_holding_boundaries_verified': True,
              'stop_and_multiplier_one_way_verified': True,
              'script_sha256': sha(Path(__file__))}
    (OUT / 'data.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
