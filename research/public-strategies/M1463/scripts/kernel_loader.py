"""Load immutable research shared kernel by exact file hashes, no family import."""
import hashlib,importlib.util,json
from pathlib import Path
FAMILY=Path(__file__).resolve().parents[1]
ROOT=FAMILY.parents[2]
def load(name):
    pin=json.loads((FAMILY/'specs/kernel-pin.json').read_text());base=ROOT/pin['path']
    assert hashlib.sha256((base/'manifest.json').read_bytes()).hexdigest()==pin['manifest_sha256']
    for filename,expected in pin['files'].items():assert hashlib.sha256((base/filename).read_bytes()).hexdigest()==expected,filename
    spec=importlib.util.spec_from_file_location('catalog_daily_'+name,base/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
