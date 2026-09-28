from pathlib import Path
import json,io,contextlib
import pandas as pd
from hype_other_replay import write,OUT
for p in OUT.glob('*/summary.json'):
 s=json.loads(p.read_text());case=p.parent.name
 try:t=pd.read_csv(p.parent/'trades.csv')
 except pd.errors.EmptyDataError:t=pd.DataFrame()
 curve=pd.read_csv(p.parent/'equity.csv')
 if case.startswith('pktsc'):
  s['replication_type']='SPEC_RULE_CAUSAL_CORRECTION_NOT_EXACT_CODE_REPRODUCTION'
  s['source_test_future_label_filter_removed']=True
 with contextlib.redirect_stdout(io.StringIO()):write(case,s,t,curve)
print('all summary clocks and monthly valuation boundaries refreshed')
