from pathlib import Path
import json
import pandas as pd
import numpy as np
D=Path(__file__).resolve().parents[1]/'artifacts/hype_other'; cutoff=pd.Timestamp('2026-08-15T00:00Z')
checks=[]
for case in ['ar_v4','mmtf_1h_v3','mmtf_15m_v3','keltner_v3']:
 full=pd.read_csv(D/case/'trades.csv'); prefix=pd.read_csv(D/(case+'_prefix0815')/'trades.csv')
 for f in (full,prefix):
  for c in ['entry_ts','exit_ts']:f[c]=pd.to_datetime(f[c],utc=True)
 cols=['entry_ts','exit_ts','exit_reason']+[c for c in ['entry_price','exit_price','entry_fill','exit_fill'] if c in full]
 a=full.loc[(full.exit_ts<cutoff)&(~full.exit_reason.str.contains('terminal|window_end')),cols].reset_index(drop=True)
 b=prefix.loc[(prefix.exit_ts<cutoff)&(~prefix.exit_reason.str.contains('terminal|window_end')),cols].reset_index(drop=True)
 pd.testing.assert_frame_equal(a,b,rtol=1e-12,atol=1e-12)
 summary=json.loads((D/case/'summary.json').read_text()); metrics=summary['metrics']; ending=metrics.get('ending_equity',metrics.get('final_equity',1+metrics.get('return_pct',0)/100))
 curve=pd.read_csv(D/case/'equity.csv'); assert abs(curve.equity.iloc[-1]-ending)<1e-12
 checks.append({'case':case,'closed_prefix_trades':len(a),'prefix_exact':True,'terminal_equity_matches_original':True})
(D/'verification.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks,indent=2))
