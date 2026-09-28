"""Validate the documentation inventory, without running strategy code or backtests."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[4]
TOPIC = ROOT / 'research/platform/research-program-review'
OUT = TOPIC / 'artifacts/strategy-chronology-20260925'
REPORT = TOPIC / 'diagnostics/strategy-project-chronology-and-research-review-2026-09-25.md'


def fingerprint(path: Path) -> dict:
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    families = json.loads((OUT / 'inventory.json').read_text())
    manifest = json.loads((OUT / 'source-manifest.json').read_text())
    report = REPORT.read_text()
    standalone = '<!-- SELF_CONTAINED_EDITION_20260925 -->' in report
    errors = []
    prose = []
    fence = None
    details = []
    table_columns = None
    table_count = 0
    table_mismatches = []
    for number, line in enumerate(report.splitlines(), 1):
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            if fence is None:
                fence = (marker[1], number)
            elif marker[1][0] == fence[0][0] and len(marker[1]) >= len(fence[0]):
                fence = None
            table_columns = None
            continue
        if fence:
            continue
        prose.append(line)
        if '<details>' in line:
            details.append(number)
        if '</details>' in line:
            if details:
                details.pop()
            else:
                errors.append({'extra_details_close': number})
        if line.startswith('|'):
            columns = len(re.findall(r'(?<!\\)\|', line))
            if table_columns is None:
                table_columns = columns
                table_count += 1
            elif columns != table_columns:
                table_mismatches.append(number)
        else:
            table_columns = None
    if fence:
        errors.append({'unclosed_fence': fence})
    if details:
        errors.append({'unclosed_details': details})
    if table_mismatches:
        errors.append({'table_column_mismatch_lines': table_mismatches})
    text = '\n'.join(prose)
    anchors = re.findall(r'<a id="([^"]+)">', text)
    duplicates = [k for k, count in Counter(anchors).items() if count > 1]
    if duplicates:
        errors.append({'duplicate_anchors': duplicates})
    local = []
    external = []
    broken = []
    bad_anchors = []
    targets = re.findall(r'!?\[[^\]\n]*\]\(((?:[^()\n]|\([^()\n]*\))*)\)', text)
    targets += re.findall(r'^\s{0,3}\[[^\]]+\]:\s*(\S+)', text, re.M)
    targets += re.findall(r'<[^>]+(?:src|href)=["\']([^"\']+)', text, re.I)
    anchor_set = set(anchors)
    internal_count = 0
    for target in targets:
        target = target.strip().strip('<>').split(' "')[0]
        if re.match(r'^(https?://|mailto:|data:)', target):
            external.append(target)
        elif target.startswith('#'):
            internal_count += 1
            if unquote(target[1:]) not in anchor_set:
                bad_anchors.append(target)
        else:
            relative = unquote(target.partition('#')[0])
            path = (REPORT.parent / relative).resolve()
            local.append(str(path))
            if not path.exists():
                broken.append(target)
    if broken or bad_anchors:
        errors.append({'broken_local_links': broken, 'missing_report_anchors': bad_anchors})
    if standalone and local:
        errors.append({'standalone_has_filesystem_dependencies': sorted(set(local))})
    if standalone and re.search(r'/Users/[^\s`"<>]+', report):
        errors.append({'standalone_has_personal_absolute_paths': True})

    expected_paths = set()
    for asset in (ROOT / 'research').iterdir():
        if not asset.is_dir() or asset.name.startswith('_') or asset.name in {'platform', 'industry'}:
            continue
        for folder in asset.iterdir():
            if folder.is_dir() and folder.name not in {'artifacts', 'diagnostics', 'legacy-canvas', 'scripts', 'specs', 'notes'}:
                expected_paths.add(str(folder))
    expected_paths.add(str(ROOT / 'research/mu'))
    main_paths = {f['absolute_path'] for f in families if not f['external_worktree']}
    if main_paths != expected_paths:
        errors.append({'missing_main_directories': sorted(expected_paths - main_paths), 'unexpected_main_directories': sorted(main_paths - expected_paths)})
    family_ids = re.findall(r'^### (F\d{3}) ·', text, re.M)
    public_ids = re.findall(r'^### PUBLIC100-([A-E]\d+) ·', text, re.M)
    expected_public = {f'{prefix}{n}' for prefix, count in [('A', 60), ('B', 5), ('C', 10), ('D', 10), ('E', 15)] for n in range(1, count + 1)}
    if family_ids != [f['id'] for f in families] or len(set(family_ids)) != 139:
        errors.append({'family_card_coverage_failure': family_ids})
    if set(public_ids) != expected_public or len(public_ids) != 100:
        errors.append({'public100_card_coverage_failure': public_ids})
    dates = [f['first_evidence']['date'] for f in families]
    if dates != sorted(dates) or any(not ('2026-04-20' <= date <= '2026-09-25') for date in dates):
        errors.append({'date_order_or_scope_failure': dates})
    historical_count = len(re.findall(r'^### H-\S+ ·', text, re.M))
    archive_count = len(re.findall(r'^### A-H\d+ ·', text, re.M))
    if (historical_count, archive_count) != (12, 29):
        errors.append({'historical_counts_failure': [historical_count, archive_count]})
    for item in manifest['sources']:
        path = Path(item['path'])
        if not path.exists() or fingerprint(path) != item:
            errors.append({'source_missing_or_changed': str(path)})
    spec_count = sum(len(f['specs']) for f in families)
    for family in families:
        for source in [family['primary'], family['first_evidence']['source'], *family['specs'], *family['docs']]:
            if not Path(source).exists():
                errors.append({'inventory_source_missing': source})
    # These three generated table types previously had blank lines between data rows.
    if re.search(r'\|\n\n\|F\d{3}\|', report):
        errors.append({'broken_family_index_table': True})

    embedded = None
    if standalone:
        embedded = json.loads((OUT/'self-contained-manifest.json').read_text())
        if embedded['report'] != {k: fingerprint(REPORT)[k] for k in ['bytes', 'sha256']}:
            errors.append({'standalone_report_fingerprint_mismatch': True})
        for item in embedded['sources']:
            if item['id'] not in anchor_set:
                errors.append({'embedded_source_missing_from_report': item['id']})
            if item.get('sha256') and not item.get('generated_metadata'):
                path = Path(item['source_path'])
                if not path.exists() or fingerprint(path)['sha256'] != item['sha256']:
                    errors.append({'embedded_source_changed': str(path)})
        expected_spec_paths = {str(Path(s).resolve()) for family in families for s in family['specs']}
        embedded_by_path = {item['source_path']: item for item in embedded['sources']}
        for path in expected_spec_paths:
            if path not in embedded_by_path:
                errors.append({'spec_not_embedded': path})
            elif embedded_by_path[path]['inclusion'] != '全文':
                errors.append({'spec_not_included_in_full': path, 'inclusion': embedded_by_path[path]['inclusion']})

    result = {
        'as_of': '2026-09-25',
        'status': 'PASS' if not errors else 'FAIL',
        'scope': 'Document coverage, source fingerprints and Markdown structure only; no strategy/data/backtest/live validation.',
        'standalone_edition': standalone,
        'counts': {
            'main_families_or_topics': len(main_paths),
            'external_unique_families': sum(f['external_worktree'] for f in families),
            'family_cards': len(family_ids),
            'public100_cards': len(public_ids),
            'historical_prototypes': historical_count,
            'archive_documents': archive_count,
            'spec_files': spec_count,
            'fingerprinted_sources': len(manifest['sources']),
            'local_link_occurrences': len(local),
            'internal_link_occurrences': internal_count,
            'embedded_source_entries': embedded['embedded_entries'] if embedded else 0,
            'external_link_occurrences_not_rechecked': len(external),
            'tables': table_count,
            'inherited_missing_references_rendered_as_text': len(manifest['missing_inherited_references']),
        },
        'limitations': [
            'External URLs were not fetched; the standalone edition requires zero filesystem links and valid internal anchors.',
            'Historical source results and their data, rule implementations, costs and performance were not recomputed.',
            'Creation dates remain evidence dates; manual interpretation and documented family-origin overrides are part of the compilation.',
            'Sources include pre-existing uncommitted files and three unmerged worktree families; regeneration requires their continued availability.',
        ],
        'artifacts': [fingerprint(path) for path in [REPORT, OUT / 'inventory.json', OUT / 'source-manifest.json', Path(__file__), TOPIC / 'scripts/build_strategy_chronology_20260925.py']],
        'errors': errors,
    }
    (OUT / 'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': result['status'], **result['counts'], 'errors': errors}, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
