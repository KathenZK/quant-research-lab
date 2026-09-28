import os
"""Read-only startup verification; writes only this new family's returned-frame snapshot."""
import sys,json,hashlib,time
from pathlib import Path
SRC=Path('/Users/ZK/OpenCode/quant-strategy-lab')
sys.path.insert(0,str(SRC/'src'))
from strategy_lab.data.research_bundle import require_research_startup,read_bundle_contract,validate_request
import pandas as pd
F=Path(__file__).resolve().parents[1]
A=Path(os.environ.get('TPSA_R0_OUTPUT',str(F/'artifacts')))
request=json.loads((F/'specs/price-request.json').read_text())
start=time.time()
print('Start exact 599-symbol price diagnostic scope via require_research_startup',flush=True)
try:
    inputs=require_research_startup(request,project_root=SRC,data_root=SRC/'data')
except Exception as exc:
    (A/'price_startup_failure.json').write_text(json.dumps({'type':type(exc).__name__,'message':str(exc),'request':request},indent=2))
    raise
(A/'price_startup_report.json').write_text(json.dumps(inputs.report,indent=2))
pd.concat(list(inputs.prices.values()),ignore_index=True).to_parquet(A/'verified_price_frames.parquet',index=False)
bundle,_=read_bundle_contract(SRC,pin={k:request[k] for k in ['bundle_path','bundle_id','bundle_sha256']})
net={**request,'mode':'net_research','asset_policy':'crypto_only','symbols':[s for s in request['symbols'] if bundle['observed_asset_classes'][s]=='COIN']}
(A/'net-request-blocked.json').write_text(json.dumps(net,indent=2))
try:
    validate_request(net,bundle)
except Exception as exc:
    (A/'net_startup_blocker.json').write_text(json.dumps({'status':'NET_RESEARCH_BLOCKED_BEFORE_PRICE_LOAD','message':str(exc),'coin_symbols':len(net['symbols']),'unclassified_symbols':sorted(set(request['symbols'])-set(net['symbols'])),'identity_review_exists':False,'no_net_account_published':True},indent=2))
print('Prices saved',time.time()-start,flush=True)
