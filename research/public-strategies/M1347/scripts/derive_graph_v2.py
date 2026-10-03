"""Pure public-to-public schema projection; preserve v1, no NAV expansion or replay."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p, x):
    with p.open('x') as f: json.dump(x, f, ensure_ascii=False, indent=2, allow_nan=False); f.write('\n')

def build(source, output):
    assert not output.exists(); output.mkdir(parents=True)
    detail = json.loads((source / 'graph-detail.json').read_text())
    record = json.loads((source / 'graph-record.json').read_text())
    curve = json.loads((source / 'base-nav-sampled.json').read_text())
    original_metrics = copy.deepcopy(detail['metrics'])
    assert detail['id'] == record['id'] == 'M1347' and len(curve) == 25
    assert detail['curve'] == curve and detail['curve_meta']['equity_unit'] == 'initial_capital_multiple'
    assert detail['curve_meta']['observations'] == 731 and detail['curve_meta']['returned_points'] == 25
    assert detail['metrics']['periods']['full'] == detail['metrics']['periods']['2023-2024']
    for name in ['same_instrument_benchmark', 'additional_native_bar_lag']:
        detail['metrics'][name]['full'] = copy.deepcopy(detail['metrics'][name]['2023-2024'])
    assert set(detail['metrics']['cost_sensitivity']) == {'fee0', 'fee20'}
    detail['metrics']['cost_sensitivity'] = {new: dict(copy.deepcopy(original_metrics['cost_sensitivity'][old]),
        full=copy.deepcopy(original_metrics['cost_sensitivity'][old]['2023-2024'])) for old, new in [('fee0', '0'), ('fee20', '20')]}
    detail['display_projection'] = dict(version=2, period_aliases={'full': '2023-2024'}, fee_labels_bps=['0', '20'],
        retained_slippage_bps_each_side=2, v1_detail_sha256=sha(source / 'graph-detail.json'),
        summary_sha256=sha(source / 'summary.json'), new_strategy_configurations=0, new_controls=0,
        explanation='Default full-period consumer and numeric bps labels; all values, nulls and25sourcepoints unchanged')
    record['display_projection'] = copy.deepcopy(detail['display_projection'])
    assert detail['curve'] == curve
    assert detail['spec']['assumptions'] and all(isinstance(x, str) for x in detail['spec']['assumptions'])
    for name in ['same_instrument_benchmark', 'additional_native_bar_lag']:
        assert detail['metrics'][name]['full'] == original_metrics[name]['2023-2024']
    for old, new in [('fee0', '0'), ('fee20', '20')]:
        assert detail['metrics']['cost_sensitivity'][new]['full'] == original_metrics['cost_sensitivity'][old]['2023-2024']
    dump(output / 'graph-detail.json', detail); dump(output / 'graph-record.json', record)
    with (output / 'base-nav-sampled.json').open('xb') as f: f.write((source / 'base-nav-sampled.json').read_bytes())
    dump(output / 'public-display-manifest.json', dict(schema='M1347-public-graph-projection/v2',
        manifest_kind='PUBLIC_DERIVED_GRAPH_PROJECTION', id='M1347', source_scope='Only previously generated publicv1 fields; no private NAV read',
        files=[dict(path=p.name, bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(output.iterdir())],
        source_files=[dict(path=p.name, bytes=p.stat().st_size, sha256=sha(p)) for p in [source / 'graph-detail.json',
                      source / 'graph-record.json', source / 'base-nav-sampled.json', source / 'summary.json']],
        script_sha256=sha(Path(__file__)), returned_points=25, metrics_observations=731, normalization_operations=0,
        original_research_counts=dict(strategy_configurations=4, new_controls=0),
        this_projection_counts=dict(strategy_configurations=0, new_controls=0),
        null_policy='Preserve every null/zero value; no fill or conversion',
        fixed_original_source_C0_and_results_unchanged=True))

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--source', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); build(a.source, a.output)
