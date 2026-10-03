"""Verify exact inspected source class, without executing its imports or app code."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
ART = FAMILY / 'artifacts/20261003-first-replay'
manifest = json.loads((ART/'source-manifest.json').read_text())
source = ART/'private-source/strategies__mean_reversion.py'
assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest['files']['strategies/mean_reversion.py']['sha256']
tree = ast.parse(source.read_text())
classes = [n for n in tree.body if isinstance(n,ast.ClassDef) and n.name in ('Strategy','MeanReversionStrategy')]
assert [n.name for n in classes] == ['Strategy','MeanReversionStrategy']
namespace = {'pd':pd}
exec(compile(ast.Module(body=classes,type_ignores=[]),str(source),'exec'),namespace)
s = importlib.util.spec_from_file_location('m0233_run',FAMILY/'scripts/run_replay.py')
module = importlib.util.module_from_spec(s)
s.loader.exec_module(module)
rows = module.load(FAMILY.parent/'M0216/artifacts/20261003-first-replay/input.csv')
config = json.loads((FAMILY/'specs/M0233-first-replay.json').read_text())
actual = module.signals(rows,config)
frame = pd.DataFrame({'price':[r['close'] for r in rows]})
upstream = namespace['MeanReversionStrategy'](window=20,z_entry=1.5,z_exit=.5).generate_signals(frame)
assert upstream['position'].tolist() == [r['source_position'] for r in actual]
assert upstream['position'].clip(lower=0).tolist() == [r['long_target'] for r in actual]
result = dict(status='PASS',source_commit=manifest['commit'],source_sha256=manifest['files']['strategies/mean_reversion.py']['sha256'],method='Execute only inspected Strategy and MeanReversionStrategy class AST from hash-verified source; no upstream imports, engine, downloader or application execution',source_signal_rows=762,long_target_rows=762,short_source_rows=int((upstream['position'] == -1).sum()),classification='ADAPTATION: signal mapping verified, execution and capital differ',license='MIT Copyright (c) 2025 Alqama-svg')
with (ART/'source-validation.json').open('x') as f:
    json.dump(result,f,indent=2)
    f.write('\n')
print(json.dumps(result))
