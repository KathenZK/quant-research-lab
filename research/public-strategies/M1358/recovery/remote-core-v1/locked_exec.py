import argparse,importlib.metadata,json,runpy,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--family',type=Path,required=True);p.add_argument('script',type=Path);p.add_argument('args',nargs=argparse.REMAINDER);a=p.parse_args()
assert getattr(sys,'_m1358_offline_guard',False),'offline guard not active'
lock=json.loads((a.family/'specs/environment-lock.json').read_text());assert sys.version==lock['python']
for k,v in lock['packages'].items():assert importlib.metadata.version(k)==v,(k,v)
sys.path.insert(0,str(a.script.parent));sys.argv=[str(a.script),*a.args];runpy.run_path(str(a.script),run_name='__main__')
