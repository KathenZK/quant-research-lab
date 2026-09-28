"""Verify legacy market fields after the isolated engine extension."""
from io import StringIO
import json
import pandas as pd
from pandas.testing import assert_frame_equal
from v3_opportunity_study_20260913 import *
from v3_opportunity_inputs_20260913 import load_sources,load_segment,table

def main():
    sources=load_sources();keys=['HYPE__seg001',next(k for k,v in sources.items() if v['slug']=='BTC'),next(k for k,v in sources.items() if v['slug']=='ETH')];checks=[]
    for key in keys:
        d,h,m,t,s=load_segment(key);events=[]
        res=engine().simulate(h,d,config('V3'),pd.Timestamp(m['trade_start']),pd.Timestamp(m['end']),entry_events=events)
        for expected,actual,label in [(t,res[1],'trades'),(s,res[3],'stops'),(pd.read_parquet(ROOT/m['baseline_dir']/'equity.parquet'),res[2],'equity'),(table(ROOT/m['baseline_dir']/'entry_events.csv'),pd.DataFrame(events),'entry_events')]:
            # Compare the old serialized representation; CSV nulls are NaN.
            if label!='equity':actual=pd.read_csv(StringIO(actual.to_csv(index=False)),float_precision='round_trip')
            for c in expected.columns:
                if pd.api.types.is_datetime64_any_dtype(expected[c]):
                    actual[c]=pd.to_datetime(actual[c],utc=True).dt.as_unit('ns')
                    expected[c]=pd.to_datetime(expected[c],utc=True).dt.as_unit('ns')
            assert_frame_equal(expected,actual[expected.columns],check_dtype=False,check_exact=False,rtol=1e-12,atol=1e-10)
        old=json.loads((ROOT/m['baseline_dir']/'summary.json').read_text())
        for c in ['return_pct','max_drawdown_pct','trades','ending_equity','fee_total']:assert abs(old[c]-res[0][c])<1e-10
        checks.append({'run_key':key,'trades':len(t),'old_fields_match':True});print(key,len(t),'PASS',flush=True)
    write_json(R/'baseline_compatibility.json',{'complete':True,'checks':checks,'engine_pin':json.loads(PIN.read_text()),'rtol':1e-12,'atol':1e-10,'source_sha256':sha(Path(__file__))})

if __name__=='__main__':main()
