"""One entrypoint; requires a fresh output directory and never rewrites frozen artifacts."""
import argparse,os,json,hashlib,subprocess,sys
from pathlib import Path
F=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--plot-python',type=Path,default=Path('/Users/ZK/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'));args=p.parse_args()
out=args.output_dir.resolve()
if out.exists() and any(out.iterdir()):raise SystemExit('Use an empty output directory; frozen evidence is never overwritten.')
out.mkdir(parents=True,exist_ok=True)
for item in json.loads((F/'artifacts/source_manifest.json').read_text()):
    path=Path(item['path']);got=hashlib.sha256(path.read_bytes()).hexdigest()
    if got!=item['sha256']:raise SystemExit(f'Pinned source changed: {path}')
os.environ['TPSA_R0_OUTPUT']=str(out)
for filename in ['load_prices.py','model_and_source_audit.py','audit_source_execution.py','run_account.py','account_acceptance.py','render_trade_paths.py']:
    subprocess.run([sys.executable,str(F/'scripts'/filename)],check=True)
subprocess.run([str(args.plot_python),str(F/'scripts/plot_account.py')],check=True)
manifest=[{'path':str(x.relative_to(out)),'sha256':hashlib.sha256(x.read_bytes()).hexdigest(),'bytes':x.stat().st_size} for x in sorted(out.rglob('*')) if x.is_file()]
(out/'reproduction_manifest.json').write_text(json.dumps(manifest,indent=2))
print('Reproduced frozen R0 evidence to',out)
