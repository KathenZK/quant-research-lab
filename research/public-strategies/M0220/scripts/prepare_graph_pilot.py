"""Prepare retained M0220 evidence for the existing Graph importer, offline.

This is a preparation bundle, not an import manifest or a research execution.
Missing source/corpus bindings remain explicit; no runtime is initialized.
"""
import argparse
import csv
from datetime import date, timedelta
import gzip
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import sqlite3

RUN = 'M0220-20261003-first-replay'
ART = 'artifacts/20261003-first-replay/'
SPEC = 'specs/M0220-first-replay.json'
SOURCE = 'artifacts/20261003-source-preflight/source-provenance.json'
REQUIRED = {SPEC, SOURCE, ART + 'graph-detail-local.json', ART + 'graph-record.json',
            ART + 'results/summary.json', ART + 'results/base-nav.csv',
            ART + 'results/base-trades.csv', ART + 'input-reference.json',
            ART + 'independent-validation.json', ART + 'causality-validation.json'}


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def regular(root, name):
    if not isinstance(name, str) or '\\' in name:
        raise ValueError('Unsafe relative evidence path')
    parts = name.split('/')
    if PurePosixPath(name).is_absolute() or any(x in {'', '.', '..'} for x in parts):
        raise ValueError('Unsafe relative evidence path')
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Evidence symlinks are not allowed')
    if not path.is_file():
        raise ValueError('Missing retained evidence: ' + name)
    return path.read_bytes()


def verify_origin(family, expected_manifest):
    family = Path(family)
    if family.is_symlink():
        raise ValueError('Evidence root cannot be a symlink')
    raw = regular(family, ART + 'result-manifest.json')
    if digest(raw) != expected_manifest:
        raise ValueError('Externally pinned manifest mismatch')
    manifest = json.loads(raw)
    refs = manifest.get('files', {})
    if not REQUIRED <= refs.keys() or len(refs) > 100:
        raise ValueError('Required retained evidence is absent')
    blobs = {}
    for name, expected in refs.items():
        blob = regular(family, name)
        if digest(blob) != expected:
            raise ValueError('Retained artifact digest mismatch: ' + name)
        blobs[name] = blob
    blobs[ART + 'result-manifest.json'] = raw
    return manifest, blobs


def read_binding(catalog, expected_sha256):
    """Read an operator-pinned, consistent existing Catalog copy; never create one."""
    path = Path(catalog)
    if path.is_symlink() or not path.is_file():
        raise ValueError('An existing regular private Catalog copy is required')
    wal = path.with_name(path.name + '-wal')
    if wal.exists() and wal.stat().st_size:
        raise ValueError('Use a consistent Catalog backup without a pending WAL')
    before = path.read_bytes()
    if digest(before) != expected_sha256:
        raise ValueError('Catalog snapshot pin mismatch')
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as con:
        con.row_factory = sqlite3.Row
        if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('Catalog integrity check failed')
        release = con.execute('SELECT version,manifest_sha256 FROM research_universes ORDER BY sequence DESC LIMIT 1').fetchone()
        if not release:
            raise ValueError('Existing research universe is required')
        rows = con.execute('''SELECT u.*,c.definition_revision AS current_revision,
            c.private_payload,c.payload AS catalog_payload FROM research_universe_records u
            JOIN catalog_items c ON c.entity_id=u.entity_id AND c.active=1
            WHERE u.version=? AND u.record_id=?''', (release['version'], 'M0220')).fetchall()
        if len(rows) != 1:
            raise ValueError('Exactly one active M0220 definition binding is required')
        row = dict(rows[0])
        original = json.loads(row['private_payload']).get('raw_record', {})
        rule = original.get('规则')
        if (not isinstance(rule, str) or not rule or digest(rule.encode()) != row['definition_sha256']
                or row['definition_revision'] != row['current_revision']):
            raise ValueError('Original rule or current definition revision mismatch')
        declaration = json.loads(row['payload'])
        if declaration.get('definition_text') != rule:
            raise ValueError('Universe and Catalog original rule differ')
        if any(declaration.get('raw_record', {}).get(k) != original.get(k)
               for k in ['规则', '市场', 'source_url']):
            raise ValueError('Universe and Catalog source fields differ')
        if not original.get('名称') or not original.get('source_url'):
            raise ValueError('Original source name and URL are required')
    if path.read_bytes() != before:
        raise ValueError('Catalog copy changed while reading')
    return dict(record_id='M0220', entity_id=row['entity_id'],
                definition_revision=row['definition_revision'], definition_sha256=row['definition_sha256'],
                original_record=original, universe_version=release['version'],
                universe_manifest_sha256=release['manifest_sha256'], catalog_snapshot_sha256=expected_sha256,
                scope='Existing Catalog/worklist binding only; not full source-corpus recovery')


def project(blobs):
    def get(name):
        return json.loads(blobs[name])
    spec, detail, record = get(SPEC), get(ART + 'graph-detail-local.json'), get(ART + 'graph-record.json')
    summary, ref = get(ART + 'results/summary.json'), get(ART + 'input-reference.json')
    if (spec['record_id'] != 'M0220' or spec['fidelity'] != 'HYPOTHESIS'
            or detail['id'] != 'M0220' or record['id'] != 'M0220'
            or detail['run_id'] != RUN or detail['origin_run_id'] != RUN
            or detail['variant_id'] != spec['variant_id'] or detail['fidelity_class'] != 'HYPOTHESIS'
            or detail['family'] != spec['family'] or not detail.get('fidelity_reason')):
        raise ValueError('Retained identity or fidelity mismatch')
    if spec['symbol'] != 'BTCUSDT' or spec['market_type'] != 'spot' or ref['input_sha256'] != spec['input_sha256']:
        raise ValueError('Input market identity mismatch')
    source = get(SOURCE)
    if source['url'] != spec['source_url'] or source['source_sha256'] != spec['source_sha256']:
        raise ValueError('Source evidence does not bind the frozen specification')
    retained = detail['metrics']
    displayed = dict(base=retained['periods']['full'],
                     fee0=retained['cost_sensitivity']['fee0']['full'],
                     fee20=retained['cost_sensitivity']['fee20']['full'],
                     lag2=retained['additional_native_bar_lag']['full'],
                     buyhold=retained['same_instrument_benchmark']['full'])
    for case, presentation in displayed.items():
        original = dict(presentation)
        original['sharpe_zero_cash'] = original.pop('sharpe')
        if original != summary[case]['metrics']:
            raise ValueError('Display metrics diverge from original retained result')
    rows = list(csv.DictReader(io.StringIO(blobs[ART + 'results/base-nav.csv'].decode(), newline='')))
    metric = summary['base']['metrics']
    if len(rows) != metric['observations'] or not rows:
        raise ValueError('Retained NAV observation count mismatch')
    previous, prior_date = float(spec['initial_cash']), None
    if not math.isfinite(previous) or previous <= 0:
        raise ValueError('Explicit positive original capital is required')
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['date', spec['variant_id']])
    compounded = 1.0
    for row in rows:
        day, equity = date.fromisoformat(row['date']), float(row['equity'])
        if prior_date is not None and day != prior_date + timedelta(days=1):
            raise ValueError('Retained daily NAV has a gap or duplicate')
        if not math.isfinite(equity) or equity <= 0:
            raise ValueError('Invalid retained capital')
        ret = equity / previous - 1
        writer.writerow([row['date'], repr(ret)])
        compounded *= 1 + ret
        previous, prior_date = equity, day
    if (rows[0]['date'] != metric['start'] or rows[-1]['date'] != metric['end']
            or not math.isclose(compounded - 1, metric['total_return'], rel_tol=1e-7, abs_tol=1e-8)):
        raise ValueError('Retained NAV and original metric period disagree')
    common = dict(id='M0220', variant_id=spec['variant_id'], family=spec['family'],
                  origin_run_id=RUN, assets=['BTCUSDT'], cash_asset='USDT',
                  fidelity_class='HYPOTHESIS', fidelity_reason=detail['fidelity_reason'])
    projected_spec = dict(common, original_spec=spec, assumptions=spec['assumptions'],
                          cash_unit='USDT', virtual_cash=True)
    spec_blob = encoded([projected_spec])
    projected_metric = dict(common, run_id=RUN, name=detail['name'],
        protocol_sha256=digest(blobs[SPEC]), implementation_specs_sha256=digest(spec_blob),
        **detail['metrics'])
    deep = dict(variant_id=spec['variant_id'], origin_run_id=RUN,
                scope='RETAINED_VALIDATION_AND_NATIVE_LAG; NO_NEW_EXECUTION',
                additional_native_bar_lag=detail['metrics']['additional_native_bar_lag'],
                retained_independent_validation=get(ART + 'independent-validation.json'),
                retained_causality_validation=get(ART + 'causality-validation.json'))
    return {'implemented_specs.json': spec_blob, 'strategy_metrics.json': encoded([projected_metric]),
            'daily_returns.csv.gz': gzip.compress(output.getvalue().encode(), mtime=0),
            'deep_validation.json': encoded([deep])}, dict(observations=len(rows),
            first_day_preserves_initial_capital_costs=True, native_cash='USDT', new_trials=0)


def prepare(family, expected_manifest, output, *, catalog=None, expected_catalog=None):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('Use a new immutable preparation directory')
    if bool(catalog) != bool(expected_catalog):
        raise ValueError('Catalog path and external snapshot pin must be supplied together')
    manifest, blobs = verify_origin(family, expected_manifest)
    projections, checks = project(blobs)
    binding = read_binding(catalog, expected_catalog) if catalog else None
    files = {'origin/' + k: v for k, v in blobs.items()}
    files.update({'projection-draft/' + k: v for k, v in projections.items()})
    if binding:
        files['catalog-binding.json'] = encoded(binding)
    receipt = dict(schema_version='lab-graph-pilot-preparation/v1', record_id='M0220',
        origin_run_id=RUN, origin_manifest_sha256=expected_manifest,
        origin_created_at=manifest['created_at'], original_files=len(blobs),
        projection_only=True, native_import_ready=False, imported=False, deployed=False,
        definition_binding='VERIFIED_EXISTING_CATALOG' if binding else 'MISSING_PRIVATE_CATALOG',
        checks=checks, missing_native_artifacts=['run_manifest.json', 'run_summary.json',
            'all_record_coverage.csv', 'record_audit.jsonl', 'source_verification.json'],
        blockers=['No source-corpus scope digest is invented',
            'Finalize through existing Graph v3 contract to retain virtual USDT and origin bytes',
            'Original producer has no native Graph run_manifest; drafts are generated projections',
            'Site baseline/CAS state and release authorization remain separate'],
        publication='PRIVATE_LOCAL_PREPARATION_ONLY; NO_LICENSE_CLEARANCE_CLAIM',
        files={k: dict(sha256=digest(v), bytes=len(v)) for k, v in sorted(files.items())})
    # Validation and any read-only binding finish before the first write.
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, blob in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open('xb') as stream:
            stream.write(blob)
    with (output / 'preparation-receipt.json').open('xb') as stream:
        stream.write(encoded(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family', type=Path, required=True)
    parser.add_argument('--expected-manifest-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--expected-catalog-sha256')
    args = parser.parse_args()
    receipt = prepare(args.family, args.expected_manifest_sha256, args.output,
                      catalog=args.catalog, expected_catalog=args.expected_catalog_sha256)
    print(json.dumps({k: receipt[k] for k in ['record_id', 'native_import_ready', 'definition_binding', 'checks']}))


if __name__ == '__main__':
    main()
