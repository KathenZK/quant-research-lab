"""Restore pinned public source bytes for offline QA; never overwrite evidence."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ART = Path(__file__).resolve().parents[1] / 'artifacts/20261003-first-replay'
manifest = json.loads((ART/'source-manifest.json').read_text())
target = ART/'private-source'
target.mkdir(exist_ok=True)
for name, record in manifest['files'].items():
    path = target/name.replace('/','__')
    if path.exists():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
        continue
    with urlopen(record['url'],timeout=30) as response:
        content = response.read()
    if hashlib.sha256(content).hexdigest() != record['sha256']:
        raise ValueError('Pinned source changed: '+name)
    with path.open('xb') as f:
        f.write(content)
print('Pinned public source bytes hash-verified')
