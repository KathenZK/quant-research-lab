"""从冻结 v1、完整官方原文与显式事件裁决发布配套资金费率 v2。"""
from __future__ import annotations

import argparse
import gzip
import io
import json
from pathlib import Path
import tempfile
import zipfile

import duckdb
import numpy as np
import pandas as pd

from strategy_lab.data.funding_v2 import (
    DATASET_ID, adjudicate_event_hour, archive_interval_segments, load_funding_v2,
)
from strategy_lab.data.manifest import inventory_fingerprint, parquet_inventory, sha256_file, utc_now_iso, write_canonical_json
from strategy_lab.data.research_inputs import load_verified_funding_snapshot

ROOT=Path(__file__).resolve().parents[4]
FAMILY=ROOT/'research/platform/data-lake-governance'
ART=FAMILY/'artifacts/binance_funding_v3_inputs_v2_20260907'
OLD=FAMILY/'artifacts/binance_v3_research_inputs_v1_20260907'
BASE=ROOT/'data/derived/datasets/binance_perp_funding_v3_inputs_v1'
OUT=ROOT/'data/derived/datasets/binance_perp_funding_v3_inputs_v2'
CUTOFF=pd.Timestamp('2026-09-05T15:45:00Z')
SPEC=FAMILY/'specs/binance-funding-v3-inputs-v2-2026-09-07.md'
COLS=['symbol','ts','funding_rate','mark_price','source','rate_type','raw_receipt_sha256']


def connect():
    c=duckdb.connect()
    c.execute("SET TimeZone='UTC'")
    c.execute('SET threads=2')
    c.execute("SET memory_limit='2GB'")
    return c


def write_event_partitions(events, stage):
    """逐月写出，避免同时开启数千个日分区的压缩缓冲区。"""
    for month, frame in events.groupby(events.ts.dt.strftime('%Y-%m'), sort=True):
        target=stage/'events'/f'month={month}'
        target.mkdir(parents=True)
        frame.sort_values(['symbol','ts','rate_type']).to_parquet(
            target/'data.parquet',index=False,compression='zstd')


def read_evidence():
    old_index=json.loads((OLD/'funding/published_input_receipts.json').read_text())
    refs=[]
    for r in old_index['receipts']:
        p=ROOT/r['path']
        if sha256_file(p)!=r['sha256']:
            raise ValueError('frozen v1 evidence changed')
        refs.append(p)
    refs+=sorted((ART/'receipts').glob('*.json'))
    refs+=sorted((ART/'archive_receipts').glob('*.json'))
    refs+=sorted((ART/'global_receipts').glob('*.json'))
    refs+=sorted((ART/'adjudication_evidence/receipts').glob('*.json'))
    code_map={s.split('/')[0]+'USDT':s for s in pd.read_csv(OLD/'identity_inventory.csv').symbol}
    global_outside={}
    native=[]
    inputs=[]
    api_scopes=[]
    archive_scopes=[]
    for path in refs:
        r=json.loads(path.read_text())
        inputs.append({'path':str(path.relative_to(ROOT)),'sha256':sha256_file(path)})
        if path.parent.name in ('receipts','global_receipts'):
            if not r.get('full_pagination'):
                raise ValueError('incomplete API receipt')
            global_query=path.parent.name=='global_receipts'
            api_scopes.append({'symbol':'ALL_USDM' if global_query else r['symbol'],
                               **{k:r[k] for k in ['start_ms','end_ms','job_id']}})
            for page in r['pages']:
                p=ROOT/page['path']
                if sha256_file(p)!=page['sha256']:
                    raise ValueError('API raw changed')
                data=json.loads(gzip.decompress(p.read_bytes()))
                previous=page.get('cursor',r['start_ms'])
                for x in data:
                    ts=pd.Timestamp(x['fundingTime'],unit='ms',tz='UTC')
                    if ((not global_query and x['symbol']!=r['symbol'].split('/')[0]+'USDT')
                        or not r['start_ms']<=x['fundingTime']<=r['end_ms']):
                        raise ValueError('API native identity/range mismatch')
                    # Page overlap is intentional in v2, but each page is monotonic.
                    if x['fundingTime']<previous:
                        raise ValueError('API page cursor mismatch')
                    previous=x['fundingTime']
                    symbol=code_map.get(x['symbol']) if global_query else r['symbol']
                    if symbol is None:
                        global_outside[x['symbol']]=global_outside.get(x['symbol'],0)+1
                        continue
                    h=ts.floor('h')
                    full=(r['start_ms']<=int(h.value//1_000_000)
                          and r['end_ms']>=int((h+pd.Timedelta(hours=1)).value//1_000_000)-1)
                    native.append({'symbol':symbol,'ts':ts,'funding_rate':float(x['fundingRate']),
                        'mark_price':float(x.get('markPrice') or 'nan'),'source':'binance_futures_funding_rate_api',
                        'rate_type':x.get('rateType','Unspecified'),'raw_receipt_sha256':page['sha256'],
                        'authority_kind':'API' if full else 'API_PARTIAL_HOUR',
                        'archive_interval_hours':np.nan,'receipt_path':str(path.relative_to(ROOT))})
        elif r['status']=='CHECKSUM_AND_CRC_PASS':
            slug=('binance_funding_v3_inputs_v2_20260907' if path.parent.parent==ART
                  else 'binance_funding_v3_inputs_20260907')
            name=f'{r["code"]}-fundingRate-{r["month"]}.zip'
            p=ROOT/'data/raw/_archives'/slug/name
            if sha256_file(p)!=r['sha256'] or p.with_suffix('.zip.CHECKSUM').read_text().split()[0]!=r['sha256']:
                raise ValueError('archive SHA256/CHECKSUM changed')
            with zipfile.ZipFile(p) as z:
                if z.testzip() is not None or z.namelist()!=[name[:-4]+'.csv']:
                    raise ValueError('archive CRC/member identity invalid')
                f=pd.read_csv(io.BytesIO(z.read(z.namelist()[0])))
            ts=pd.to_datetime(f.calc_time,unit='ms',utc=True)
            if (not ts.is_monotonic_increasing or ts.duplicated().any()
                or not ts.dt.strftime('%Y-%m').eq(r['month']).all()
                or not np.isfinite(f[['last_funding_rate','funding_interval_hours']].to_numpy()).all()
                or not f.funding_interval_hours.gt(0).all()):
                raise ValueError('archive schema/time/value invalid')
            archive_scopes.append({'symbol':r['symbol'],'month':r['month'],'rows':len(f),
                'sha256':r['sha256'],'path':str(p.relative_to(ROOT))})
            for t,v,hours in zip(ts,f.last_funding_rate,f.funding_interval_hours):
                native.append({'symbol':r['symbol'],'ts':t,'funding_rate':float(v),'mark_price':np.nan,
                    'source':'binance_vision_funding_monthly','rate_type':'Unspecified',
                    'raw_receipt_sha256':r['sha256'],'authority_kind':'ARCHIVE',
                    'archive_interval_hours':float(hours),'receipt_path':str(path.relative_to(ROOT))})
    result=pd.DataFrame(native)
    result['ts']=pd.to_datetime(result.ts,utc=True)
    result['rate_type']=result.rate_type.where(result.rate_type.isin(['Regular','Special']),'Unspecified')
    if not np.isfinite(result.funding_rate).all():
        raise ValueError('nonfinite incoming funding')
    write_canonical_json(ART/'global_outside_scope.json',{'native_codes_and_page_overlap_rows':global_outside,
        'policy':'raw retained; no conversion into V3 USDT contracts'})
    return result,inputs,api_scopes,archive_scopes


def reconcile(base,native,classes):
    b=base[COLS].copy()
    b['rate_type']=b.rate_type.where(b.rate_type.isin(['Regular','Special']),'Unspecified')
    b['authority_kind']='LEGACY'
    b['archive_interval_hours']=np.nan
    b['receipt_path']=''
    both=pd.concat([b,native],ignore_index=True)
    both['ts']=pd.to_datetime(both.ts,utc=True)
    both=both[both.symbol.isin(classes)&both.ts.le(CUTOFF)].copy()
    c=connect()
    c.register('input_rows',both)
    conflict=c.execute('SELECT symbol,ts,rate_type,min(funding_rate) AS lo,max(funding_rate) AS hi FROM input_rows GROUP BY 1,2,3 HAVING hi-lo>1e-12').df()
    conflict.to_csv(ART/'exact_type_conflicts.csv',index=False)
    if len(conflict):
        raise ValueError('exact funding event conflicts need adjudication')
    observed=c.execute("""SELECT * FROM input_rows QUALIFY row_number() OVER(PARTITION BY symbol,ts,rate_type
        ORDER BY CASE authority_kind WHEN 'API' THEN 0 WHEN 'API_PARTIAL_HOUR' THEN 1 WHEN 'ARCHIVE' THEN 2 ELSE 3 END,raw_receipt_sha256)=1""").df()
    c.close()
    observed['hour']=observed.ts.dt.floor('h')
    sizes=observed.groupby(['symbol','hour']).ts.transform('size')
    candidates=observed[sizes.gt(1)]
    candidate_keys=candidates[['symbol','hour']].drop_duplicates()
    native=native[native.symbol.isin(classes)&native.ts.le(CUTOFF)].copy()
    native['hour']=native.ts.dt.floor('h')
    api=native[native.authority_kind.eq('API')].drop_duplicates(['symbol','ts','rate_type'])
    archive=native[native.authority_kind.eq('ARCHIVE')].drop_duplicates(['symbol','ts','rate_type'])
    authorities={k:g.copy() for k,g in archive.merge(candidate_keys,on=['symbol','hour']).groupby(['symbol','hour'],sort=False)}
    authorities.update({k:g.copy() for k,g in api.merge(candidate_keys,on=['symbol','hour']).groupby(['symbol','hour'],sort=False)})
    untouched=observed[sizes.eq(1)].copy()
    untouched['event_unambiguous']=True
    untouched['resolution']='SINGLE_OBSERVED_EVENT'
    changed=[]
    mappings=[]
    groups=[]
    for i,(key,g) in enumerate(candidates.groupby(['symbol','hour'],sort=False),1):
        a=authorities.get(key)
        f,links,status=adjudicate_event_hour(g,a)
        f['resolution']=status
        changed.append(f)
        mappings.extend(links)
        groups.append({'symbol':key[0],'hour':key[1],'observed_keys':len(g),'published_events':len(f),
            'status':status,'unambiguous':bool(f.event_unambiguous.all()),
            'authority':a.authority_kind.iloc[0] if a is not None else 'NONE'})
        if i%2000==0:
            print(f'funding adjudicated {i} event hours',flush=True)
    out=pd.concat([untouched,*changed],ignore_index=True)
    out['asset_class']=out.symbol.map(classes)
    out['hour']=out.ts.dt.floor('h')
    # Attach independently retained native frequency metadata, not observed deltas.
    an=archive.groupby(['symbol','hour']).ts.transform('size')
    only=archive[an.eq(1)][['symbol','hour','ts','funding_rate','archive_interval_hours','raw_receipt_sha256']].rename(columns={
        'ts':'archive_ts','funding_rate':'archive_rate','archive_interval_hours':'native_interval',
        'raw_receipt_sha256':'archive_evidence_sha256'})
    out=out.merge(only,on=['symbol','hour'],how='left',validate='many_to_one')
    match=(out.ts-out.archive_ts).abs().le(pd.Timedelta(seconds=2)) & (out.funding_rate-out.archive_rate).abs().le(1e-12)
    out['archive_interval_hours']=out.native_interval.where(match)
    out['archive_evidence_sha256']=out.archive_evidence_sha256.where(match,'').fillna('')
    out=out[COLS+['event_unambiguous','resolution','asset_class','archive_interval_hours','archive_evidence_sha256']].copy()
    out=out.sort_values(['symbol','ts','rate_type']).reset_index(drop=True)
    c=connect()
    c.register('out',out)
    out=c.execute("SELECT *,sha256(symbol||'|'||epoch_ms(ts)::VARCHAR||'|'||rate_type) AS event_id FROM out").df()
    c.close()
    out['ts']=pd.to_datetime(out.ts,utc=True)
    if out.event_id.duplicated().any():
        raise ValueError('published event identity duplicate')
    pd.DataFrame(mappings).to_csv(ART/'event_mapping.csv',index=False)
    pd.DataFrame(groups).to_csv(ART/'hour_adjudication.csv',index=False)
    stats={'observed_exact_type_keys':len(observed),'candidate_hours':len(groups),
        'resolved_candidate_hours':sum(r['unambiguous'] for r in groups),
        'unresolved_candidate_hours':sum(not r['unambiguous'] for r in groups),
        'representation_keys_removed':len(observed)-len(out),'mapping_rows':len(mappings)}
    return out,stats


def value_lineage_audit(base,native,events,classes):
    """独立集合对账：没有凭空事件，每个旧键保留或有已验证的映射。"""
    c=connect()
    b=base[base.symbol.isin(classes)][['symbol','ts','funding_rate']].copy()
    n=native[native.symbol.isin(classes)&native.ts.le(CUTOFF)][['symbol','ts','funding_rate']].drop_duplicates()
    e=events[['symbol','ts','funding_rate']]
    c.register('legacy_rows',b)
    c.register('native_rows',n)
    c.register('published_rows',e)
    links=pd.read_csv(ART/'event_mapping.csv')
    for col in ['old_ts','canonical_ts']:
        links[col]=pd.to_datetime(links[col],utc=True,format='mixed')
    c.register('event_links',links)
    unexplained=c.execute('''SELECT count(*) FROM published_rows p
        WHERE NOT EXISTS(SELECT 1 FROM legacy_rows b WHERE b.symbol=p.symbol AND b.ts=p.ts AND abs(b.funding_rate-p.funding_rate)<=1e-12)
        AND NOT EXISTS(SELECT 1 FROM native_rows n WHERE n.symbol=p.symbol AND n.ts=p.ts AND abs(n.funding_rate-p.funding_rate)<=1e-12)''').fetchone()[0]
    lost=c.execute('''SELECT b.* FROM legacy_rows b
        WHERE NOT EXISTS(SELECT 1 FROM published_rows p WHERE b.symbol=p.symbol AND b.ts=p.ts AND abs(b.funding_rate-p.funding_rate)<=1e-12)
        AND NOT EXISTS(SELECT 1 FROM event_links l JOIN published_rows p ON p.symbol=l.symbol AND p.ts=l.canonical_ts AND abs(p.funding_rate-l.funding_rate)<=1e-12
            WHERE l.symbol=b.symbol AND l.old_ts=b.ts AND abs(l.funding_rate-b.funding_rate)<=1e-12)''').df()
    lost.to_csv(ART/'unexplained_legacy_loss.csv',index=False)
    result={'published_rows_without_legacy_or_native_value':unexplained,'unexplained_legacy_key_loss':len(lost),
        'checked_legacy_price_scope_rows':len(b),'checked_native_rows':len(n),'checked_output_rows':len(e)}
    write_canonical_json(ART/'value_lineage_audit.json',result)
    c.close()
    if unexplained or len(lost):
        raise ValueError('independent funding value/legacy preservation audit failed')


def independent_global_parity():
    """直接重读两套独立请求原文，不复用发布表或裁决函数。"""
    global_events={}
    def raw_events(receipt):
        result={}
        for p in receipt['pages']:
            path=ROOT/p['path']
            if sha256_file(path)!=p['sha256']:
                raise ValueError('raw parity evidence changed')
            for r in json.loads(gzip.decompress(path.read_bytes())):
                key=(r['symbol'],r['fundingTime'],r.get('rateType','Unspecified'))
                value=float(r['fundingRate'])
                if key in result and abs(result[key]-value)>1e-12:
                    raise ValueError('raw pagination overlap conflict')
                result[key]=value
        return result
    for p in sorted((ART/'global_receipts').glob('*.json')):
        global_events.update(raw_events(json.loads(p.read_text())))
    checks=[]
    special=[]
    for p in sorted((ART/'adjudication_evidence/receipts').glob('*.json')):
        r=json.loads(p.read_text())
        observed=raw_events(r)
        if r['kind']=='global_tail_independent_check':
            code=r['symbol'].split('/')[0]+'USDT'
            expected={k:v for k,v in global_events.items() if k[0]==code}
            if observed.keys()!=expected.keys() or any(abs(v-expected[k])>1e-12 for k,v in observed.items()):
                raise ValueError('global funding pagination differs from independent symbol query')
            checks.append({'symbol':r['symbol'],'event_count':len(observed),'parity':'PASS',
                           'absence_proven':False,'receipt_sha256':sha256_file(p)})
        else:
            special.append({'symbol':r['symbol'],'start_ms':r['start_ms'],'event_count':len(observed),
                'native_types':sorted({k[2] for k in observed}),'receipt_sha256':sha256_file(p)})
    write_canonical_json(ART/'global_parity.json',{'global_unique_events':len(global_events),
        'global_native_codes':len({k[0] for k in global_events}),'symbol_checks':checks,
        'note':'An empty matching query is not proof of historical absence'})
    write_canonical_json(ART/'stock_event_types.json',{'checks':special})


def retrieval_scope_coverage(plan,api_scopes,archive_scopes):
    """区分未执行逐币查询和已被其他官方查询/归档覆盖的检索范围。"""
    spans={}
    for r in archive_scopes:
        a=pd.Timestamp(r['month']+'-01',tz='UTC')
        b=a+pd.offsets.MonthBegin(1)
        spans.setdefault(r['symbol'],[]).append((int(a.value//1_000_000),int(b.value//1_000_000)-1))
    global_spans=[]
    for r in api_scopes:
        if r['symbol']=='ALL_USDM':
            global_spans.append((r['start_ms'],r['end_ms']))
        else:
            spans.setdefault(r['symbol'],[]).append((r['start_ms'],r['end_ms']))
    rows=[]
    for j in plan['jobs']:
        cursor=j['start_ms']
        gaps=[]
        for a,b in sorted(spans.get(j['symbol'],[])+global_spans):
            if b<cursor or a>j['end_ms']:
                continue
            if a>cursor:
                gaps.append((cursor,min(a-1,j['end_ms'])))
            cursor=max(cursor,b+1)
            if cursor>j['end_ms']:
                break
        if cursor<=j['end_ms']:
            gaps.append((cursor,j['end_ms']))
        rows.append({**j,'retrieval_scope_covered':not gaps,'uncovered_ranges_json':json.dumps(gaps),
            'net_calendar_proven':False,'absence_proven':False})
    pd.DataFrame(rows).to_csv(ART/'query_evidence_coverage.csv',index=False)
    return {'original_jobs':len(rows),'retrieval_scope_covered_jobs':sum(r['retrieval_scope_covered'] for r in rows),
        'retrieval_scope_uncovered_jobs':sum(not r['retrieval_scope_covered'] for r in rows),
        'note':'Retrieval range coverage is not independent funding-calendar or historical-absence proof'}


def protection():
    records=[]
    for slug in ['binance_perp_15m_history_v3','binance_perp_1h_from_15m_v2',
                 'binance_perp_4h_from_15m_v2','binance_perp_1d_from_15m_v2',
                 'binance_perp_funding_v3_inputs_v1']:
        root=ROOT/'data/derived/datasets'/slug
        m=json.loads((root/'_MANIFEST.json').read_text())
        actual=inventory_fingerprint(parquet_inventory(root))
        if actual!=m['parquet_inventory_fingerprint']:
            raise ValueError(f'protected dataset changed: {slug}')
        records.append({'dataset_id':m['dataset_id'],'manifest_sha256':sha256_file(root/'_MANIFEST.json'),
                        'fingerprint':actual,'unchanged':True})
    bundle=json.loads((OLD/'research_input_bundle.json').read_text())
    if sha256_file(ROOT/'src/strategy_lab/data/research_inputs.py')!=bundle['reader_sha256']:
        raise ValueError('frozen v1 reader changed')
    return records


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--allow-partial',action='store_true')
    parser.add_argument('--analyze-only',action='store_true')
    args=parser.parse_args()
    if OUT.exists():
        raise FileExistsError('v2 already published; never overwrite')
    plan=json.loads((ART/'plan.json').read_text())
    if sha256_file(SPEC)!=plan['contract_sha256'] or sha256_file(BASE/'_MANIFEST.json')!=plan['parent_manifest_sha256']:
        raise ValueError('frozen contract/input changed')
    done={p.stem for p in (ART/'receipts').glob('*.json')}
    pending=[j for j in plan['jobs'] if j['job_id'] not in done]
    if pending and not args.allow_partial:
        raise ValueError('uncompleted query jobs; explicit partial publication required')
    classes=pd.read_csv(OLD/'identity_inventory.csv').set_index('symbol').snapshot_underlying_type.to_dict()
    base=load_verified_funding_snapshot(BASE)
    base[~base.symbol.isin(classes)].groupby('symbol').size().rename('rows').to_csv(ART/'outside_v3_scope.csv')
    print('verifying native funding receipts',flush=True)
    native,inputs,api_scopes,archive_scopes=read_evidence()
    independent_global_parity()
    retrieval=retrieval_scope_coverage(plan,api_scopes,archive_scopes)
    events,stats=reconcile(base,native,classes)
    value_lineage_audit(base,native,events,classes)
    segments,expected=archive_interval_segments(events)
    symbol_rows=events.groupby('symbol').agg(rows=('ts','size'),first_ts=('ts','min'),last_ts=('ts','max'),
        ambiguous_rows=('event_unambiguous',lambda s:int((~s).sum())),special_events=('rate_type',lambda s:int(s.eq('Special').sum()))).reset_index()
    symbol_rows=symbol_rows.merge(pd.DataFrame({'symbol':list(classes),'asset_class':list(classes.values())}),how='right',on='symbol')
    symbol_rows.to_csv(ART/'symbol_inventory.csv',index=False)
    segments.to_csv(ART/'verified_segments.csv',index=False)
    events[~events.event_unambiguous].to_csv(ART/'unresolved_events.csv',index=False)
    events[events.rate_type.eq('Special')].to_csv(ART/'special_events.csv',index=False)
    pd.DataFrame(pending).to_csv(ART/'pending_queries.csv',index=False)
    pd.DataFrame(api_scopes).to_csv(ART/'api_query_scopes.csv',index=False)
    pd.DataFrame(archive_scopes).to_csv(ART/'archive_scopes.csv',index=False)
    summary={'dataset_id':DATASET_ID,'rows':len(events),'symbols':events.symbol.nunique(),
        'price_scope_symbols':len(classes),'price_symbols_without_events':sorted(set(classes)-set(events.symbol)),
        'start_utc':events.ts.min().isoformat(),'end_utc':events.ts.max().isoformat(),'cutoff_utc':CUTOFF.isoformat(),
        'pending_query_jobs':len(pending),'completed_v2_queries':len(plan['jobs'])-len(pending),
        'pending_coin_queries':sum(j['asset_class']=='COIN' for j in pending),
        'verified_archive_months':len(archive_scopes),'verified_segments':len(segments),
        'completed_global_query_days':sum(r['symbol']=='ALL_USDM' for r in api_scopes),
        'verified_expected_events':len(expected),'verified_segment_symbols':segments.symbol.nunique(),
        'ambiguous_rows':int((~events.event_unambiguous).sum()),'special_events':int(events.rate_type.eq('Special').sum()),
        'adjudication':stats,'row_quality':'PASS','status':'PARTIAL_COVERAGE',
        'full_historical_funding_calendar_verified':False,'full_pit_identity_verified':False,
        'scope_policy':'V3 observed symbols only; outside-scope v1 records retained in old immutable snapshot',
        'net_policy':'require_funding_v2_window plus independent identity evidence; no zero fill',
        'calendar_policy':'native archive intervals; no API-only frequency extrapolation, no edge/frequency-change bridging'}
    summary['retrieval_coverage']=retrieval
    write_canonical_json(ART/'analysis.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    if args.analyze_only:
        return
    protected=protection()
    write_canonical_json(ART/'protected_inputs.json',{'datasets':protected,'legacy_reader_unchanged':True})
    index={'receipts':inputs,'parent_funding_manifest_sha256':sha256_file(BASE/'_MANIFEST.json'),
           'native_rows_before_overlap_dedup':len(native),'frozen_at':utc_now_iso()}
    write_canonical_json(ART/'input_receipts.json',index)
    stage=Path(tempfile.mkdtemp(prefix='funding_v2_',dir=ROOT/'data/derived/_staging'))
    write_event_partitions(events,stage)
    (stage/'coverage').mkdir()
    segments.to_parquet(stage/'coverage/segments.parquet',index=False)
    expected.to_parquet(stage/'coverage/expected_events.parquet',index=False)
    inv=parquet_inventory(stage)
    summary.update(parquet_inventory_fingerprint=inventory_fingerprint(inv),file_count=len(inv),bytes=sum(r['size'] for r in inv),
        input_manifest_sha256=sha256_file(BASE/'_MANIFEST.json'),contract_sha256=sha256_file(SPEC),
        builder_sha256=sha256_file(Path(__file__)),reader_sha256=sha256_file(ROOT/'src/strategy_lab/data/funding_v2.py'),
        input_receipts_sha256=sha256_file(ART/'input_receipts.json'),generated_at=utc_now_iso(),
        event_partitioning='UTC month; bounded single-partition writer')
    summary.update(event_mapping_sha256=sha256_file(ART/'event_mapping.csv'),
        hour_adjudication_sha256=sha256_file(ART/'hour_adjudication.csv'),
        value_lineage_audit_sha256=sha256_file(ART/'value_lineage_audit.json'))
    summary.update(global_parity_sha256=sha256_file(ART/'global_parity.json'),
        stock_event_types_sha256=sha256_file(ART/'stock_event_types.json'),
        query_evidence_coverage_sha256=sha256_file(ART/'query_evidence_coverage.csv'))
    if (ART/'global_plan.json').exists():
        summary['global_plan_sha256']=sha256_file(ART/'global_plan.json')
    write_canonical_json(stage/'_MANIFEST.json',summary)
    # Verify the complete staged artifact through the independent public reader before rename.
    loaded=load_funding_v2(stage,expected_manifest_sha256=sha256_file(stage/'_MANIFEST.json'))
    if len(loaded.events)!=len(events):
        raise ValueError('staging readback mismatch')
    del loaded,events,base,native
    stage.rename(OUT)
    published=load_funding_v2(OUT,expected_manifest_sha256=sha256_file(OUT/'_MANIFEST.json'))
    write_canonical_json(ART/'acceptance.json',{**summary,'manifest_sha256':sha256_file(OUT/'_MANIFEST.json'),
        'published_readback':'PASS','published_rows':len(published.events),'protected_inputs_unchanged':True})
    print('funding v2 published and strictly verified; explicit coverage limits remain',flush=True)


if __name__=='__main__':
    main()
