"""Synthetic contract tests only; no market fetch, strategy run or live runtime."""
import csv
import gzip
import importlib.util
import io
import json
from pathlib import Path
import sqlite3

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'research/public-strategies/M0220/scripts/prepare_graph_pilot.py'
_spec = importlib.util.spec_from_file_location('m0220_graph_pilot', SCRIPT)
pilot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pilot)


@pytest.fixture
def origin(tmp_path):
    root = tmp_path / 'synthetic-family'
    metrics = dict(start='2024-01-01', end='2024-01-02', observations=2,
                   total_return=.089, max_drawdown=-.01, sharpe_zero_cash=1.0)
    display = dict(metrics)
    display['sharpe'] = display.pop('sharpe_zero_cash')
    spec = dict(record_id='M0220', variant_id='M0220-SYNTHETIC', family='synthetic',
                fidelity='HYPOTHESIS', symbol='BTCUSDT', market_type='spot', initial_cash=100,
                input_sha256='a' * 64, source_url='https://example.test/source',
                source_sha256='b' * 64, assumptions=['SYNTHETIC fixture'])
    detail = dict(id='M0220', name='SYNTHETIC ONLY', family='synthetic', variant_id=spec['variant_id'],
                  run_id=pilot.RUN, origin_run_id=pilot.RUN, fidelity_class='HYPOTHESIS',
                  fidelity_reason='SYNTHETIC fixture', metrics=dict(periods={'full': display},
                    additional_native_bar_lag={'full': display}, same_instrument_benchmark={'full': display},
                    cost_sensitivity={'fee0': {'full': display}, 'fee20': {'full': display}}))
    blobs = {pilot.SPEC: pilot.encoded(spec), pilot.SOURCE: pilot.encoded(dict(url=spec['source_url'], source_sha256=spec['source_sha256'])),
             pilot.ART + 'graph-detail-local.json': pilot.encoded(detail),
             pilot.ART + 'graph-record.json': pilot.encoded(dict(id='M0220')),
             pilot.ART + 'results/summary.json': pilot.encoded({c: {'metrics': metrics} for c in ['base', 'fee0', 'fee20', 'lag2', 'buyhold']}),
             pilot.ART + 'results/base-nav.csv': b'date,equity\n2024-01-01,99\n2024-01-02,108.9\n',
             pilot.ART + 'results/base-trades.csv': b'date,side\n2024-01-01,BUY\n',
             pilot.ART + 'input-reference.json': pilot.encoded(dict(input_sha256='a' * 64)),
             pilot.ART + 'independent-validation.json': b'{"status":"SYNTHETIC"}',
             pilot.ART + 'causality-validation.json': b'{"status":"SYNTHETIC"}',
             'scripts/inert.py': b'raise RuntimeError("Retained code must never execute")\n'}
    for name, blob in blobs.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)
    manifest = dict(created_at='2026-10-03T07:18:44+00:00', files={n: pilot.digest(v) for n, v in blobs.items()})
    raw = pilot.encoded(manifest)
    (root / pilot.ART / 'result-manifest.json').write_bytes(raw)
    return root, pilot.digest(raw), blobs


def test_prepare_preserves_origin_and_first_day_cost_without_import(origin, tmp_path):
    root, pin, blobs = origin
    out = tmp_path / 'private-preparation'
    receipt = pilot.prepare(root, pin, out)
    assert receipt['native_import_ready'] is False
    assert receipt['definition_binding'] == 'MISSING_PRIVATE_CATALOG'
    assert receipt['checks']['new_trials'] == 0
    assert not (out / 'manifest.json').exists()
    assert not list(out.rglob('*.sqlite'))
    for name, raw in blobs.items():
        assert (out / 'origin' / name).read_bytes() == raw
    returns = list(csv.DictReader(io.StringIO(gzip.decompress((out / 'projection-draft/daily_returns.csv.gz').read_bytes()).decode())))
    assert float(returns[0]['M0220-SYNTHETIC']) == pytest.approx(-.01)
    assert float(returns[1]['M0220-SYNTHETIC']) == pytest.approx(.10)
    specs = json.loads((out / 'projection-draft/implemented_specs.json').read_bytes())
    assert specs[0]['cash_asset'] == 'USDT'
    assert specs[0]['fidelity_class'] == 'HYPOTHESIS'
    with pytest.raises(ValueError, match='immutable'):
        pilot.prepare(root, pin, out)


@pytest.mark.parametrize('case', ['manifest', 'artifact', 'absent', 'symlink'])
def test_evidence_corruption_stops_before_output(origin, tmp_path, case):
    root, pin, _ = origin
    path = root / pilot.ART / 'results/base-nav.csv'
    if case == 'manifest':
        pin = '0' * 64
    elif case == 'artifact':
        path.write_bytes(path.read_bytes() + b'\n')
    elif case == 'absent':
        path.unlink()
    else:
        target = tmp_path / 'outside.csv'
        path.rename(target)
        path.symlink_to(target)
    out = tmp_path / 'must-not-exist'
    with pytest.raises(ValueError):
        pilot.prepare(root, pin, out)
    assert not out.exists()


def test_manifest_traversal_is_rejected(origin, tmp_path):
    root, _, _ = origin
    p = root / pilot.ART / 'result-manifest.json'
    manifest = json.loads(p.read_bytes())
    manifest['files']['../../escape'] = '0' * 64
    p.write_bytes(pilot.encoded(manifest))
    with pytest.raises(ValueError, match='relative'):
        pilot.prepare(root, pilot.digest(p.read_bytes()), tmp_path / 'blocked')


@pytest.mark.parametrize('mutation', ['duplicate', 'missing_day', 'metric', 'fidelity'])
def test_semantic_conflicts_rejected_even_when_re_pinned(origin, mutation):
    _, _, raw = origin
    blobs = dict(raw)
    if mutation in {'duplicate', 'missing_day'}:
        day = b'2024-01-01' if mutation == 'duplicate' else b'2024-01-03'
        key = pilot.ART + 'results/base-nav.csv'
        blobs[key] = blobs[key].replace(b'2024-01-02', day)
    else:
        key = pilot.ART + 'graph-detail-local.json'
        detail = json.loads(blobs[key])
        if mutation == 'metric':
            detail['metrics']['periods']['full']['total_return'] = 100
        else:
            detail['fidelity_class'] = 'STANDARDIZED'
        blobs[key] = pilot.encoded(detail)
    with pytest.raises(ValueError):
        pilot.project(blobs)


@pytest.fixture
def catalog(tmp_path):
    """Explicit synthetic schema fixture, never passed off as a private restore."""
    path = tmp_path / 'SYNTHETIC-CATALOG.sqlite'
    original = {'规则': 'SYNTHETIC RULE', '市场': 'SYNTHETIC', 'source_url': 'https://example.test', '名称': 'SYNTHETIC'}
    payload = {'definition_text': original['规则'], 'raw_record': original}
    with sqlite3.connect(path) as con:
        con.executescript('''CREATE TABLE research_universes(sequence INTEGER,version TEXT,manifest_sha256 TEXT);
            CREATE TABLE research_universe_records(version TEXT,record_id TEXT,entity_id TEXT,definition_revision TEXT,definition_sha256 TEXT,payload TEXT);
            CREATE TABLE catalog_items(entity_id TEXT,active INTEGER,definition_revision TEXT,private_payload TEXT,payload TEXT);''')
        con.execute('INSERT INTO research_universes VALUES(1,?,?)', ('synthetic-v1', 'c' * 64))
        con.execute('INSERT INTO research_universe_records VALUES(?,?,?,?,?,?)', ('synthetic-v1', 'M0220', 'synthetic-entity', 'r1', pilot.digest(original['规则'].encode()), json.dumps(payload)))
        con.execute('INSERT INTO catalog_items VALUES(?,?,?,?,?)', ('synthetic-entity', 1, 'r1', json.dumps({'raw_record': original}), '{}'))
    return path


def test_binding_reads_existing_pinned_definition_without_mutation(catalog):
    before = catalog.read_bytes()
    result = pilot.read_binding(catalog, pilot.digest(before))
    assert result['definition_revision'] == 'r1'
    assert result['original_record']['规则'] == 'SYNTHETIC RULE'
    assert catalog.read_bytes() == before


def test_optional_binding_preserves_database_and_still_does_not_claim_import(origin, catalog, tmp_path):
    root, pin, _ = origin
    before = catalog.read_bytes()
    out = tmp_path / 'synthetic-preparation-with-binding'
    receipt = pilot.prepare(root, pin, out, catalog=catalog, expected_catalog=pilot.digest(before))
    assert receipt['definition_binding'] == 'VERIFIED_EXISTING_CATALOG'
    assert receipt['native_import_ready'] is False
    assert (out / 'catalog-binding.json').is_file()
    assert catalog.read_bytes() == before


def test_missing_catalog_never_creates_runtime_or_output(origin, tmp_path):
    root, pin, _ = origin
    missing, output = tmp_path / 'missing/catalog.sqlite', tmp_path / 'blocked-preparation'
    with pytest.raises(ValueError, match='existing regular'):
        pilot.prepare(root, pin, output, catalog=missing, expected_catalog='0' * 64)
    assert not missing.parent.exists()
    assert not output.exists()


@pytest.mark.parametrize('case', ['missing', 'pin', 'wal', 'revision', 'rule'])
def test_binding_rejects_absence_inconsistent_backup_or_definition(catalog, case):
    pin = pilot.digest(catalog.read_bytes())
    if case == 'missing':
        catalog = catalog.with_name('does-not-exist.sqlite')
    elif case == 'pin':
        pin = '0' * 64
    elif case == 'wal':
        catalog.with_name(catalog.name + '-wal').write_bytes(b'pending')
    else:
        with sqlite3.connect(catalog) as con:
            if case == 'revision':
                con.execute("UPDATE catalog_items SET definition_revision='r2'")
            else:
                con.execute("UPDATE research_universe_records SET definition_sha256=?", ('0' * 64,))
        pin = pilot.digest(catalog.read_bytes())
    with pytest.raises(ValueError):
        pilot.read_binding(catalog, pin)
    if case == 'missing':
        assert not catalog.exists()
