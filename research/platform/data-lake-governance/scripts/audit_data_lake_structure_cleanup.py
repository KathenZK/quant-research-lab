"""只读库存、已发布内容指纹和清理依赖盘点；仅向治理 artifacts 写报告。"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import heapq
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import zipfile

from strategy_lab.data.manifest import inventory_fingerprint, parquet_inventory, sha256_file, utc_now_iso, write_canonical_json

ROOT=Path(__file__).resolve().parents[4]
LAKE=ROOT/'data'
ART=ROOT/'research/platform/data-lake-governance/artifacts/data_lake_structure_cleanup_audit_20260907'


def inventory():
    layers=defaultdict(lambda:{'files':0,'logical_bytes':0,'allocated_bytes':0})
    groups=defaultdict(lambda:{'files':0,'logical_bytes':0,'allocated_bytes':0})
    largest=[]
    symlinks=[]
    empty=[]
    for directory,dirs,files in os.walk(LAKE,followlinks=False):
        if not dirs and not files:
            empty.append(str(Path(directory).relative_to(ROOT)))
        for name in files:
            p=Path(directory)/name
            st=p.lstat()
            if stat.S_ISLNK(st.st_mode):
                symlinks.append(str(p.relative_to(ROOT)))
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            parts=p.relative_to(LAKE).parts
            stop=next((i for i,x in enumerate(parts) if x.startswith(('date=','month=','year='))),len(parts)-1)
            group='/'.join(parts[:stop])
            if parts[0]=='features':
                group='/'.join(parts[:2])
            for target in [layers[parts[0]],groups[group]]:
                target['files']+=1
                target['logical_bytes']+=st.st_size
                target['allocated_bytes']+=st.st_blocks*512
            item=(st.st_size,str(p.relative_to(ROOT)))
            if len(largest)<30:
                heapq.heappush(largest,item)
            elif item>largest[0]:
                heapq.heapreplace(largest,item)
    return {'layers':dict(layers),'groups':dict(sorted(groups.items())),
        'largest_files':[{'logical_bytes':n,'path':p} for n,p in sorted(largest,reverse=True)],
        'symlinks':symlinks,'empty_leaf_directories':empty,
        'allocated_note':'sum of regular-file st_blocks, excludes directory metadata; APFS clones/snapshots may affect actual reclaim'}


def published():
    records=[]
    for p in sorted((LAKE/'derived/datasets').glob('*/_MANIFEST.json')):
        m=json.loads(p.read_text())
        actual=inventory_fingerprint(parquet_inventory(p.parent))
        record={'root':str(p.parent.relative_to(ROOT)),'manifest_sha256':sha256_file(p),
            **{k:m.get(k) for k in ['dataset_id','rows','symbol_count','symbols','start_utc','end_utc',
                'cutoff_exclusive_utc','cutoff_utc','status','row_quality','quality_status','bytes','file_count',
                'input_dataset_id','input_manifest_sha256','input_snapshot_fingerprint',
                'internal_missing_bars','full_historical_funding_calendar_verified',
                'verified_segments','verified_segment_symbols','ambiguous_rows']},
            'actual_parquet_fingerprint':actual,'content_fingerprint_matches':actual==m['parquet_inventory_fingerprint']}
        records.append(record)
        print(record['dataset_id'],record['content_fingerprint_matches'],flush=True)
    return records


def zip_comparison():
    p=LAKE/'normalized/ohlcv/exchange=binance/market_type=perp.zip'
    counts=defaultdict(int)
    details=[]
    with zipfile.ZipFile(p) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            rel=PurePosixPath(info.filename)
            if rel.is_absolute() or '..' in rel.parts:
                counts['unsafe_member_path']+=1
                continue
            if rel.parts[0]=='__MACOSX' or rel.name=='.DS_Store':
                counts['macos_metadata']+=1
                continue
            target=p.parent/str(rel)
            if not target.is_file():
                label='missing_local_counterpart'
            elif target.stat().st_size!=info.file_size:
                label='different_size'
            else:
                with z.open(info) as stream:
                    digest=hashlib.file_digest(stream,'sha256').hexdigest()
                label='exact_content_duplicate' if digest==sha256_file(target) else 'different_content'
            counts[label]+=1
            if label!='exact_content_duplicate' and len(details)<20:
                details.append({'member':info.filename,'label':label})
    return {'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha256_file(p),
        'members':dict(counts),'nonduplicate_examples':details,
        'policy':'No extraction or deletion. Exact match does not prove the backup is unnecessary.'}


def dependencies():
    candidates=[p.name for p in (LAKE/'cache').iterdir() if p.is_dir()]
    candidates += [p.name for p in (LAKE/'derived/_staging').iterdir()]
    candidates += ['market_type=perp.zip']
    paths=subprocess.run(['rg','--files','research','docs','src','scripts','-g','*.py','-g','*.md','-g','*.json',
        '-g','!**/artifacts/**'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.splitlines()
    hits={c:[] for c in candidates}
    for filename in paths:
        p=ROOT/filename
        if p.stat().st_size>2_000_000:
            continue
        content=p.read_text(errors='replace')
        for candidate in candidates:
            if candidate in content and p!=Path(__file__):
                hits[candidate].append(filename)
    return {'scan_scope':'literal mentions in research/docs/src/scripts Python Markdown JSON; artifacts excluded; dynamic dependencies not proven absent',
        'candidates':hits}


def main():
    ART.mkdir(parents=True,exist_ok=True)
    data=inventory()
    data['checked_at']=utc_now_iso()
    data['disk_free_bytes']=shutil.disk_usage(ROOT).free
    write_canonical_json(ART/'file_inventory_summary.json',data)
    records=published()
    write_canonical_json(ART/'published_content_check.json',{'checked_at':utc_now_iso(),'datasets':records,
        'all_fingerprints_match':all(r['content_fingerprint_matches'] for r in records),
        'method':'strict content hash compared with published manifest; not a new remote audit or full SQL revalidation'})
    write_canonical_json(ART/'legacy_zip_comparison.json',zip_comparison())
    write_canonical_json(ART/'cleanup_dependencies.json',dependencies())
    usage=subprocess.run(['du','-k','-d','2','data'],cwd=ROOT,capture_output=True,text=True,check=True)
    write_canonical_json(ART/'allocated_usage.json',{'method':'du -k -d 2 data','stdout':usage.stdout,'checked_at':utc_now_iso()})
    opened=subprocess.run(['lsof','-nP','+D',str(LAKE/'derived/_staging')],capture_output=True,text=True,timeout=30)
    write_canonical_json(ART/'staging_open_files.json',{'checked_at':utc_now_iso(),'returncode':opened.returncode,
        'stdout':opened.stdout,'stderr':opened.stderr,'caveat':'point-in-time check, not a deletion lock'})
    print('Read-only structure audit complete; no lake files changed',flush=True)


if __name__=='__main__':
    main()
