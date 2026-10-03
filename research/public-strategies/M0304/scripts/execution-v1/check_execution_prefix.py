#!/usr/bin/env python3
"""Synthetic stateful execution causality stress; no market data."""
import copy,json,resource
from pathlib import Path
import numpy as np
import pandas as pd
from formula_probe import synthetic
from replay_engine import replay,write,ms,BAR_MS
R=Path(__file__).resolve().parent
resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
spec=json.loads((R/'planned-protocol.json').read_text());n=2400;d=synthetic(2026100304,n);d['open_time']=ms('2024-01-01T00:00Z')+np.arange(n)*BAR_MS
rng=np.random.default_rng(304);d['enter_long']=rng.random(n)<.15;d['exit_long']=rng.random(n)<.15
spec['input_expected_only']['evaluation_end_exclusive']=pd.Timestamp(int(d.open_time.iloc[-1])+BAR_MS,unit='ms',tz='UTC').isoformat();case={'name':'base','fee_bps_per_side':8,'delay_bars':1};full=replay(d,spec,case);checks=[]
for end in [81,750,1800]:
    ps=copy.deepcopy(spec);ps['input_expected_only']['evaluation_end_exclusive']=pd.Timestamp(int(d.open_time.iloc[end]),unit='ms',tz='UTC').isoformat()
    prefix=replay(d.iloc[:end],ps,case)
    pd.testing.assert_frame_equal(full[0].iloc[:end],prefix[0],check_exact=True)
    pd.testing.assert_frame_equal(full[2].loc[full[2].bar_index<end].reset_index(drop=True),prefix[2],check_exact=True)
    changed=d.copy();changed.loc[end:,['open','high','low','close']]*=3.1;changed.loc[end:,['enter_long','exit_long']]=~changed.loc[end:,['enter_long','exit_long']]
    altered=replay(changed,spec,case);pd.testing.assert_frame_equal(full[0].iloc[:end],altered[0].iloc[:end],check_exact=True)
    pd.testing.assert_frame_equal(full[2].loc[full[2].bar_index<end].reset_index(drop=True),altered[2].loc[altered[2].bar_index<end].reset_index(drop=True),check_exact=True);checks.append(end)
write(R/'synthetic-execution-prefix.json',{'status':'PASS_SYNTHETIC_STATEFUL_EXECUTION_PREFIX','rows':n,'seed_price':2026100304,'seed_signals':304,'synthetic_fills':len(full[2]),'exact_prefixes_and_future_perturbations':checks,'compared':'all cash/quantity/equity/nav bar marks and complete trade rows; terminal order reason excluded because horizon changes','historical_runs':0,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
d.to_csv(R/'synthetic-stress-input.csv',index=False,float_format='%.17g');full[0].to_csv(R/'synthetic-stress-nav.csv',index=False,float_format='%.17g');full[2].to_csv(R/'synthetic-stress-trades.csv',index=False,float_format='%.17g');write(R/'synthetic-stress-events.json',full[4]);write(R/'synthetic-stress-spec.json',spec)
print('PASS synthetic stateful prefixes',len(full[2]),'fills')
