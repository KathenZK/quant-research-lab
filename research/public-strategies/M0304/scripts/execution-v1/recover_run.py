#!/usr/bin/env python3
"""Re-run the frozen implementation on independently rebuilt input and compare outputs.
Requires the original approved C0 gate. Repeated frozen recovery is not a new search.
"""
import argparse,json
from pathlib import Path
from replay_engine import run,read,sha,write
p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--source-run',required=True);p.add_argument('--output',required=True);p.add_argument('--spec',required=True);p.add_argument('--gate',required=True);p.add_argument('--receipt',required=True);a=p.parse_args()
result=run(a.input,a.output,a.spec,a.gate);source=Path(a.source_run);dest=Path(a.output)
expected={f.name for f in source.iterdir() if f.is_file()};actual={f.name for f in dest.iterdir() if f.is_file()};assert actual==expected
compared=[]
for name in sorted(expected):
    if name=='summary.json':
        left,right=read(source/name),read(dest/name);left.pop('peak_rss_kib',None);right.pop('peak_rss_kib',None);assert left==right
    else:assert sha(source/name)==sha(dest/name),name
    compared.append(name)
write(a.receipt,{'status':'PASS_FROZEN_HISTORICAL_RECOVERY','record_id':'M0304','input_sha256':sha(a.input),'protocol_sha256':sha(a.spec),'output_files_compared':compared,'byte_identical_except_summary_peak_rss':True,'new_configs_or_searches':0,'recovered_strategy_configs':4,'recovered_controls':1,'network_requests':0,'limits':'Frozen implementation repeatability is not independent validation of engine logic or original runtime equivalence.'})
print('PASS frozen recovery all files')
