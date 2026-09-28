"""Validate unresolved family windows and retain exact outcome; never relax gaps."""
from pathlib import Path
import sys,json,hashlib
from strategy_lab.data.research_bundle import require_research_startup

ROOT=Path(__file__).resolve().parents[4];FAMILY=Path(__file__).resolve().parents[1]
def load(request):return require_research_startup(request,project_root=ROOT,data_root=ROOT/'data')
def run(key):
    request_path=FAMILY/f'specs/repository-{key}-input-request-20260911.json';request=json.loads(request_path.read_text());out=FAMILY/'artifacts/repository_ranking_20260911/input_probes';out.mkdir(exist_ok=True)
    record={'request':str(request_path.relative_to(ROOT)),'request_sha256':hashlib.sha256(request_path.read_bytes()).hexdigest()}
    try:
        result=load(request);record.update(status='INPUTS_RETURNED',report=result.report,files={})
        for symbol,frame in result.prices.items():
            p=out/(key+'_'+symbol.split('/')[0]+'.parquet');frame.to_parquet(p,index=False);record['files'][symbol]={'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    except Exception as exc:record.update(status='INPUT_CHECK_FAILED',error_type=type(exc).__name__,error=str(exc))
    (out/(key+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2,default=str));print(key,record['status'],record.get('error',''))
if __name__=='__main__':run(sys.argv[1])
