"""Restrict hover stop labels to the selected holding interval; preserve payloads."""
from pathlib import Path
import hashlib
import json
import shutil


def main():
    root = Path('research/asset-portfolios/1d-ma7-cross-atr-generalization/artifacts/ma30_states_20260911')
    pages = root / 'html'
    backup = root / 'html_before_hover_fix'
    assert not backup.exists()
    shutil.copytree(pages, backup)
    old = "let line=chosen?stops.filter(s=>s[0]===chosen[0]&&s[1]<=b[0]).at(-1):null;"
    new = "let line=chosen&&b[0]>=chosen[1]&&b[0]<=chosen[2]?stops.filter(s=>s[0]===chosen[0]&&s[1]<=b[0]).at(-1):null;"
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    checks = []
    for p in [pages / 'coin.js', *sorted((pages / 'coins').glob('*.html'))]:
        before = p.read_text()
        assert before.count(old) == 1, p
        after = before.replace(old, new)
        if p.suffix == '.html':
            # All prices, fills, stops, returns and table values stay identical.
            before_data = before.split('const DATA=', 1)[1].split(';\n', 1)[0]
            after_data = after.split('const DATA=', 1)[1].split(';\n', 1)[0]
            assert before_data == after_data
        checks.append({'path': str(p.relative_to(pages)), 'before': sha(p)})
        p.write_text(after)
        checks[-1]['after'] = sha(p)
    receipt = {'change': 'Hover stop label shown only during the selected trade holding interval',
               'data_payloads_unchanged': True, 'pages_checked': 680, 'files': checks,
               'source_script_sha256': sha(Path(__file__))}
    (root / 'html_hover_fix.json').write_text(json.dumps(receipt, indent=2) + '\n')
    manifest = {str(p.relative_to(pages)): sha(p) for p in pages.rglob('*')
                if p.is_file() and p.name != 'artifact_checksums.json'}
    (pages / 'artifact_checksums.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
