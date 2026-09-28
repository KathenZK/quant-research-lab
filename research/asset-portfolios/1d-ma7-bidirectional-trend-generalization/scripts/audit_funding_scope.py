"""只读审计完整资金窗口资格；不输出策略净收益或放宽 startup 身份门禁。"""
from pathlib import Path
import json
import sys
import argparse
import pandas as pd

FAMILY=Path(__file__).resolve().parents[1]
LAB=Path('/Users/ZK/OpenCode/quant-strategy-lab')
sys.path.insert(0,str(LAB/'src'))
from strategy_lab.data.research_bundle import require_research_startup
from strategy_lab.data.funding_v2 import load_funding_v2

def load_coverage():
    return load_funding_v2(LAB/'data/derived/datasets/binance_perp_funding_v3_inputs_v2',
        expected_manifest_sha256='398cc19eac88d0e8c55258c118f6cae2481c6b2d1a5e6253778344b9f25a1076')

def attempt_net_startup(request):
    return require_research_startup(request,project_root=LAB,data_root=LAB/'data')

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',default='funding-scope-20260908');args=p.parse_args()
    out=FAMILY/'artifacts'/args.run_id;assert not out.exists();out.mkdir()
    data=load_coverage();s=data.segments.copy();s['start']=pd.to_datetime(s.start,utc=True);s['end']=pd.to_datetime(s.end,utc=True)
    s.to_csv(out/'verified-calendar-segments.csv',index=False)
    universe=json.loads((FAMILY/'specs/observed-universe-20260908.json').read_text());rows=[]
    for symbol,cls in universe.items():
        g=s[s.symbol.eq(symbol)]
        rows.append({'symbol':symbol,'asset_class':cls,'calendar_segments':len(g),
            'main_639_calendar_covered':bool(((g.start<=pd.Timestamp('2024-12-05',tz='UTC'))&(g.end>=pd.Timestamp('2026-09-05',tz='UTC'))).any()),
            'latest_calendar_end':str(g.end.max()) if len(g) else None,
            'events':int(data.events.symbol.eq(symbol).sum()),
            'special_events':int((data.events.symbol.eq(symbol)&data.events.rate_type.eq('Special')).sum()),
            'identity_review':'NO_INDEPENDENT_FULL_HISTORICAL_REVIEW',
            'net_result_status':'UNVERIFIED_NOT_ZERO'})
    pd.DataFrame(rows).to_csv(out/'symbol-funding-status.csv',index=False)
    request=json.loads((FAMILY/'specs/input-request-20260908.json').read_text())
    request.update(mode='net_research',symbols=['BTC/USDT:USDT'],asset_policy='crypto_only',start='2024-12-05T00:00:00Z')
    try:
        attempt_net_startup(request)
        raise AssertionError('net startup must reject absent identity review')
    except ValueError as exc:error=str(exc)
    report={'dataset_id':data.manifest['dataset_id'],'status':data.manifest['status'],'rows':len(data.events),
        'calendar_segments':len(s),'symbols_with_some_calendar':s.symbol.nunique(),
        'main_symbols_with_full_calendar':sum(r['main_639_calendar_covered'] for r in rows),
        'net_startup_rejection':error,'missing_funding_filled':False,
        'identity_evidence_fabricated':False,'candidate_funding_return_computed':False,
        'main_blocker':'2026-09-05 main end exceeds every full-window archive calendar proof; standalone coverage does not grant identity certification'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
