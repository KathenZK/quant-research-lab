"""Read-only verification of the frozen delivery; all new outputs go to /tmp."""
from pathlib import Path
import contextlib
import hashlib
import importlib.util
import io
import json
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
ROOT = Path('/Users/ZK/.codex/worktrees/5f41/quant-strategy-lab')
TOPIC = ROOT / 'research/platform/small-account-three-line-validation'
OUT = Path('/tmp/three-line-review-20260909')
OUT.mkdir(exist_ok=True)

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def load(path):
    return json.loads(path.read_text())

def verify(base, path, groups=('files',)):
    data = load(path)
    entries = ([{'path': p, 'sha256': s} for p, s in data.items()]
               if 'files' not in data else [e for g in groups for e in data.get(g, [])])
    errors = []
    for entry in entries:
        p = base / entry['path']
        if not p.is_file() or sha(p) != entry['sha256']:
            errors.append(entry['path'])
        elif 'bytes' in entry and p.stat().st_size != entry['bytes']:
            errors.append(entry['path'] + ': byte size mismatch')
    return {'manifest': str(path), 'sha256': sha(path), 'files_checked': len(entries), 'errors': errors}

checks = []
for family, name in [
    ('1d-small-account-slow-trend', 'hashes.json'),
    ('1d-tpsa-long-account', 'artifact_manifest.json'),
    ('8h-btceth-small-account-carry', 'input_manifest.json'),
    ('8h-btceth-small-account-carry', 'output_manifest.json'),
]:
    base = ROOT / 'research/asset-portfolios' / family
    checks.append(verify(base, base / 'artifacts' / name))
checks.append(verify(ROOT, TOPIC / 'artifacts/final-delivery-manifest.json',
                     ('files', 'shared_files', 'family_manifest_pins')))
context = []
for e in load(TOPIC / 'artifacts/context-source-manifest.json')['sources']:
    p = Path(e['path'])
    context.append({'path': str(p), 'unchanged': p.is_file() and sha(p) == e['sha256']})

audits = []
for name in ['independent_math_oracles', 'audit_a_ledgers', 'audit_b_ledgers', 'audit_c_ledgers']:
    source = TOPIC / 'scripts' / (name + '.py')
    spec = importlib.util.spec_from_file_location('review_' + name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        if name == 'independent_math_oracles':
            result = module.check_oracles()
            (OUT / (name + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        else:
            module.OUT = OUT / (name + '.json')
            module.audit()
    (OUT / (name + '.log')).write_text(captured.getvalue())
    audits.append({'script': str(source), 'sha256': sha(source), 'status': 'PASS',
                   'output': name + '.json'})

result = {'review_utc': datetime.now(timezone.utc).isoformat(),
          'frozen_root': str(ROOT), 'manifest_checks': checks,
          'context_source_checks': context, 'retained_accountant_reruns': audits,
          'scope': 'Retained hashes and independent accountant scripts rerun; no strategy-engine or model-training rerun and no new market data. Frozen worktree is unchanged.'}
(OUT / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'manifest_counts': [c['files_checked'] for c in checks],
                  'manifest_errors': [c for c in checks if c['errors']],
                  'context_unchanged': sum(c['unchanged'] for c in context),
                  'context_total': len(context), 'audits': audits}, ensure_ascii=False, indent=2))
assert not any(c['errors'] for c in checks)
