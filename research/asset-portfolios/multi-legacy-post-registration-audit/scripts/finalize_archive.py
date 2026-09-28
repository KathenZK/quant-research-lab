"""Join coverage records and verify this audit's deliverable links and hashes."""
from pathlib import Path
import collections,hashlib,json,re
import pandas as pd

ROOT=Path(__file__).resolve().parents[4]
FAMILY=Path(__file__).resolve().parents[1]
A=FAMILY/'artifacts'

def read(p):return json.loads(p.read_text())
def save(p,d):p.write_text(json.dumps(d,indent=2,ensure_ascii=False,default=str)+'\n')

def main():
    coverage=[]
    legacy=read(A/'hype_legacy/registrations.json')
    iterable=legacy.values() if isinstance(legacy,dict) else legacy
    for row in iterable:
        if not isinstance(row,dict):continue
        coverage.append({'group':'hype_legacy','status':'REPLAYED_WITH_DECLARED_LIMITATIONS',**row})
    hi=read(A/'hype_other/inventory.json')
    for row in hi['rows']:coverage.append({'group':'hype_other',**row})
    oi=read(A/'other_assets/scope_inventory.json')
    for row in oi.get('registered_single_asset_replayed',[]):
        coverage.append({'group':'other_assets','family':f"{row['asset']}-1H-Adaptive-Regime",'status':'REPLAYED',**row})
    if oi.get('registered_six_asset_replayed'):
        coverage.append({'group':'other_assets',**oi['registered_six_asset_replayed']})
    for name in oi.get('unregistered_unique_frozen_observations_replayed',[]):
        coverage.append({'group':'other_assets','family':name,'status':'REPLAYED_UNREGISTERED_FROZEN_OBSERVATION'})
    for row in oi.get('unreplayed',[]):coverage.append({'group':'other_assets',**row})
    for asset,registration in oi.get('registered',{}).items():
        coverage.append({'group':'other_assets','family':f'{asset}-1H-Adaptive-Regime','registration':registration,'status':'REPLAYED'})
    for row in oi.get('other_families',[]):coverage.append({'group':'other_assets',**row})
    coverage.append({'group':'ensemble','family':'Binance-1H-Adaptive-Regime-Multi-Asset-Ensemble','version':'V1','status':'REPLAYED_SPEC_CANDIDATE_BLOCKING','start':'2026-07-08T00:00:00Z'})
    save(A/'coverage_inventory.json',{'as_of':'2026-09-10','scope':'HYPE/BTC/ETH/SOL/BNB/TRX early intraday families prioritized at 15m/30m/1h; ancillary SOL4h explicitly listed','rows':coverage,'statuses':dict(collections.Counter(x.get('status','NOT_SPECIFIED') for x in coverage))})
    errors=[]
    for p in FAMILY.rglob('*.md'):
        if 'artifacts/inputs/marks/' in str(p):continue
        for link in re.findall(r'\]\(([^)]+)\)',p.read_text()):
            if '://' in link or link.startswith('#'):continue
            target=link.split('#')[0].strip('<>')
            if target and not (p.parent/target).exists():errors.append({'source':str(p.relative_to(ROOT)),'missing':target})
    prices=read(A/'inputs/manifest.json')
    for name,meta in prices['files'].items():
        if hashlib.sha256((A/'inputs'/name).read_bytes()).hexdigest()!=meta['sha256']:errors.append({'input_hash_mismatch':name})
    rows=read(A/'all_results.json')
    for row in rows:
        if not (-1<=float(row['return']) and float(row['drawdown'])<=0):errors.append({'invalid_metric':row['name']})
    save(A/'archive_checks.json',{'status':'PASS' if not errors else 'FAIL','errors':errors,'checked_input_files':len(prices['files']),'result_rows':len(rows),'covered_inventory_rows':len(coverage)})
    pinned={}
    for p in FAMILY.rglob('*'):
        if not p.is_file() or '__pycache__' in str(p) or p.suffix not in ('.py','.md','.json','.csv','.parquet','.png','.svg'):continue
        if p.name in ('archive_sha256.json',):continue
        pinned[str(p.relative_to(FAMILY))]=hashlib.sha256(p.read_bytes()).hexdigest()
    save(A/'archive_sha256.json',{'algorithm':'sha256','files':pinned})
    print(json.dumps({'errors':errors,'result_rows':len(rows),'inventory_rows':len(coverage),'archive_files':len(pinned)},ensure_ascii=False))

if __name__=='__main__':main()
