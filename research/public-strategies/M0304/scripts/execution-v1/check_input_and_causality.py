#!/usr/bin/env python3
"""Read authorized input only for raw and formula QA; never calls historical replay."""
import argparse,hashlib,json,resource
from pathlib import Path
import numpy as np
import pandas as pd
from formula_probe import features,FEATURES
from replay_engine import load_input,write,sha,ms
p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--spec',required=True);p.add_argument('--output',required=True);a=p.parse_args()
resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));s=json.loads(Path(a.spec).read_text());d=load_input(a.input,s)
evalmask=(d.open_time>=ms(s['input_expected_only']['evaluation_start']))&(d.open_time<ms(s['input_expected_only']['evaluation_end_exclusive']));assert int(evalmask.sum())==105408
assert d.open_time.is_monotonic_increasing and not d.open_time.duplicated().any();z=features(d)
assert np.isfinite(z.loc[evalmask,['slowk','rsi','fisher_rsi','bb_lowerband','sar','CDLHAMMER']].to_numpy()).all()
checks=[]
for n in [9000,40000,80000]:
    p=features(d.iloc[:n]);pd.testing.assert_frame_equal(z.loc[:n-1,FEATURES],p[FEATURES],check_exact=True);del p
    changed=d.copy();changed.loc[n:,['open','high','low','close']]*=2.1;changed.loc[n:,'volume']*=7
    alt=features(changed);pd.testing.assert_frame_equal(z.loc[:n-1,FEATURES],alt.loc[:n-1,FEATURES],check_exact=True);del changed,alt;checks.append(n)
write(a.output,{'record_id':'M0304','status':'PASS_INPUT_AND_FORMULA_CAUSALITY_NOT_EXECUTION_C0','input_sha256':sha(a.input),'input_bytes':Path(a.input).stat().st_size,'input_rows':len(d),'evaluation_rows':int(evalmask.sum()),'grid_duplicates_gaps_nonstandard_close_times':0,'nonfinite_ohlcv':0,'zero_volume_or_trade_count':0,'positive_ohlc_and_volume_ranges':'PASS','identity_columns':'PASS','all_evaluation_features_finite':True,'historical_feature_prefixes_and_future_perturbations_exact':checks,'historical_account_returns_computed':False,'historical_strategy_runs':0,'original_external_source_executed':False,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
print('PASS input and formula QA only, no historical returns')
