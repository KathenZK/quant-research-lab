"""Bind completed research, checks and source/document snapshots; no market replay."""
from pathlib import Path
import hashlib
import json
import platform
import re
import shutil
import sys
import numpy as np
import pandas as pd


def main():
    base = Path('research/asset-portfolios/1d-ma7-cross-atr-generalization')
    root = base / 'artifacts/ma30_states_20260911'
    dest = root / 'delivery'
    assert not dest.exists()
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    read = lambda p: json.loads(Path(p).read_text())
    write = lambda p, x: Path(p).write_text(json.dumps(x, ensure_ascii=False, indent=2) + '\n')
    checks = {
        'accounts': root / 'audit/accounts.json',
        'same_entry': root / 'pair_audit/final.json',
        'summary': root / 'summary_audit/final.json',
        'html': root / 'html_audit/final.json',
    }
    for p in checks.values():
        assert read(p)['status'] == 'PASS', p
    for name in ['before_results.json', 'results/started.json', 'pairs/started.json']:
        for p, h in read(root / name)['pins'].items():
            assert sha(p) == h, p
    pin = read(base / 'specs/ma30-states-engine-pin-20260911.json')
    for kind in ['engine', 'contract', 'tests']:
        assert sha(pin[kind + '_path']) == pin[kind + '_sha256']
    assert read(root / 'governance/scope.json')['own_ma30_family_errors'] == 0
    assert read(root / 'governance/scope.json')['registry_sha256'] == sha('scripts/governance/check_trusted_consumers.py')
    assert read(checks['same_entry'])['pairs_manifest_sha256'] == sha(root / 'pairs/artifact_checksums.json')
    assert read(checks['summary'])['analysis_manifest_sha256'] == sha(root / 'analysis/artifact_checksums.json')
    assert read(checks['html'])['html_manifest_sha256'] == sha(root / 'html/artifact_checksums.json')
    for p, h in read(root / 'html/artifact_checksums.json').items():
        assert sha(root / 'html' / p) == h, p
    report = base / 'diagnostics/ma30-states-results-20260911.md'
    report_links = []
    for target in re.findall(r'\]\(([^)]+)\)', report.read_text()):
        if '://' in target or target.startswith('#'):
            continue
        p = (report.parent / target.split('#')[0]).resolve()
        assert p.exists(), p
        report_links.append(str(p))
    write(root / 'report_links_check.json', {'status': 'PASS', 'report_sha256': sha(report),
          'local_links': len(report_links), 'paths': report_links,
          'engine_and_original_inputs_unchanged': True})
    dest.mkdir()
    snapshot_paths = {report, base / 'README.md', base / 'bin-1d-ma7-car-gen-core-ledger.md',
                      base / 'decision-log.md', root / 'README.md', Path(__file__),
                      Path('research/README.md'), Path('research/asset-portfolios/README.md'),
                      Path('research/_shared-kernels/README.md'),
                      Path('research/_shared-kernels/ma7-cross-atr-ratchet/README.md'),
                      Path('scripts/governance/check_trusted_consumers.py'),
                      Path('tests/test_ma7_car_ma30_states.py')}
    # The older local helpers imported by this round are captured for reproducibility too.
    snapshot_paths.update((base / 'scripts').glob('*.py'))
    snapshot_paths.update((base / 'scripts').glob('*ma30*.mjs'))
    snapshot_paths.update((base / 'specs').glob('*ma30*'))
    for v in ['v1', 'v2', 'v3', 'v4', 'v5']:
        snapshot_paths.update(Path('research/_shared-kernels/ma7-cross-atr-ratchet', v).glob('*.py'))
        snapshot_paths.update(Path('research/_shared-kernels/ma7-cross-atr-ratchet', v).glob('*.json'))
        snapshot_paths.update(Path('research/_shared-kernels/ma7-cross-atr-ratchet', v).glob('*.md'))
    snapshot_paths = {p.resolve().relative_to(Path.cwd().resolve()) for p in snapshot_paths}
    snapshots = []
    for p in sorted(snapshot_paths):
        if not p.is_file():
            continue
        target = dest / 'snapshots' / p
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        assert sha(p) == sha(target)
        snapshots.append({'source': str(p), 'snapshot': str(target), 'sha256': sha(p)})
    write(dest / 'snapshots.json', snapshots)
    write(dest / 'runtime.json', {'python': sys.version, 'platform': platform.platform(),
                                'numpy': np.__version__, 'pandas': pd.__version__})
    sources = [root / n for n in ['before_results.json', 'preimages/manifest.json',
               'results/artifact_checksums.json', 'results/started.json', 'results/completion.json',
               'pairs/artifact_checksums.json', 'pairs/started.json', 'pairs/completion.json',
               'analysis/artifact_checksums.json', 'analysis/inputs.json',
               'html/artifact_checksums.json', 'html_hover_fix.json', 'report_links_check.json',
               'pair_audit_roundoff_note.json', 'governance/scope.json', 'governance/trusted_consumers.log',
               'html_before_hover_fix/artifact_checksums.json', 'html_audit_parser_attempt/final.json',
               'html_audit_count_attempt/final.json', 'summary_audit/artifact_checksums.json']]
    sources += list(checks.values())
    sources += [report, base / 'specs/ma30-states-engine-pin-20260911.json']
    source_pins = {str(p): sha(p) for p in sources}
    write(dest / 'evidence_pins.json', source_pins)
    final = {
        'complete': True, 'research_status': 'completed_historical_mechanism_comparison',
        'official_strategy_versions_unchanged': ['V1', 'V2', 'V3'],
        'new_strategy_version_assigned': False, 'engine_version': 'v5',
        'candidate_codes': 680, 'stock_codes_included': 0, 'replayed_coins': 660,
        'continuous_segments': 954, 'new_accounts': 8586, 'reused_baseline_accounts': 954,
        'fee_each_side': .001, 'slippage_each_side': .0004,
        'same_original_entries': 16226, 'new_fixed_entry_replays': 2460,
        'reused_equivalent_exit_labels': 78670,
        'account_audit_counts': read(checks['accounts'])['totals'],
        'audit_status': {k: read(v)['status'] for k, v in checks.items()},
        'browser_render_verified': False, 'own_governance_errors': 0,
        'unrelated_repository_governance_errors': read(root / 'governance/scope.json')['repository_errors'],
        'universal_profit_achieved': False, 'full_cycle_validated': False,
        'full_funding_verified': False, 'official_price_conflict_resolved': False,
        'future_blind_validation': False, 'live_ready': False,
        'html': str(root / 'html/index.html'), 'report': str(report),
        'evidence_pins_sha256': sha(dest / 'evidence_pins.json'),
        'snapshots_manifest_sha256': sha(dest / 'snapshots.json'),
        'source_script_sha256': sha(Path(__file__)),
    }
    write(root / 'completion.json', final)
    write(dest / 'artifact_checksums.json', {str(p.relative_to(dest)): sha(p)
          for p in dest.rglob('*') if p.is_file() and p.name != 'artifact_checksums.json'})
    print(json.dumps({'complete': True, 'snapshots': len(snapshots), 'checks': final['audit_status'],
                      'universal_profit_achieved': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
