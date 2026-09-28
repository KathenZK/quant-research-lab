"""Verify this completed comparison's links/acceptances and archive file hashes."""
from pathlib import Path
import ast
import hashlib
import json
import re

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
A = FAMILY / 'artifacts/iteration_comparison_20260911'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    docs = [FAMILY / name for name in (
        'README.md', 'decision-log.md', 'scripts/README.md',
        'specs/iteration-comparison-20260911.md',
        'diagnostics/iteration-comparison-20260911.md',
        'diagnostics/correction-mmtf-rvol-20260911.md')]
    scripts = [p for p in (FAMILY / 'scripts').glob('*.py')
               if 'iteration' in p.name or p.name in (
                   'compare_cc_versions.py', 'compare_ema_versions.py',
                   'compare_ar_mmtf_versions.py')]
    for p in scripts:
        ast.parse(p.read_text(), filename=str(p))
    links = []
    for p in docs + sorted(A.rglob('*.md')):
        for dest in re.findall(r'\]\(([^)]+)\)', p.read_text()):
            if dest.startswith(('https:', 'http:', '#', 'mailto:')):
                continue
            dest = dest.split('#', 1)[0]
            target = (p.parent / dest).resolve()
            assert target.exists(), (p, dest)
            links.append({'from': str(p.relative_to(ROOT)), 'to': str(target)})
    acceptances = []
    for name in ('acceptance_ema_independent.json', 'acceptance_ar_mmtf_independent.json',
                 'acceptance_cc_independent.json', 'acceptance_aggregate.json'):
        p = A / name
        obj = json.loads(p.read_text())
        assert str(obj['status']).startswith('PASS'), (name, obj['status'])
        acceptances.append({'path': str(p.relative_to(ROOT)),
                            'sha256': sha(p), 'status': obj['status']})
    verification = {'status': 'PASS', 'scope': 'This comparison only; not repository-wide acceptance',
                    'python_scripts_parsed': len(scripts), 'local_links_checked': len(links),
                    'acceptances': acceptances, 'links': links,
                    'figures_visually_inspected': ['paired_returns.png', 'cc_versions_windows.png'],
                    'limitations': 'Passing checks does not establish complete funding or live execution.'}
    (A / 'archive_verification.json').write_text(json.dumps(verification, ensure_ascii=False, indent=2) + '\n')
    output = A / 'archive_sha256.json'
    paths = set(docs + scripts)
    paths.update(p for p in A.rglob('*') if p.is_file() and p != output and '__pycache__' not in p.parts)
    rows = [{'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size, 'sha256': sha(p)}
            for p in sorted(paths)]
    output.write_text(json.dumps({'scope': 'iteration_comparison_20260911',
                                 'historical_20260910_artifacts_not_overwritten': True,
                                 'files': rows}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'PASS', 'archived_files': len(rows),
                      'local_links_checked': len(links), 'archive_sha256': sha(output)}))


if __name__ == '__main__':
    main()
