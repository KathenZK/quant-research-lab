"""交付文件、冻结身份及研究收据核验；不重跑统计或策略实验。"""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import json
import re
from urllib.parse import unquote

FAMILY=Path(__file__).resolve().parents[1]
ROOT=FAMILY.parents[2]
LAB=Path('/Users/ZK/OpenCode/quant-strategy-lab')
REL=FAMILY.relative_to(ROOT)


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(path.read_text())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-sync',action='store_true')
    args=parser.parse_args()
    if args.check_sync:
        manifest=load(FAMILY/'artifacts/sync-manifest.json')
        assert load(LAB/REL/'artifacts/sync-manifest.json')==manifest
        owned={str(p.relative_to(FAMILY)) for p in FAMILY.rglob('*')
               if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts
               and p.name!='.DS_Store' and str(p.relative_to(FAMILY))!='artifacts/sync-manifest.json'}
        assert owned==set(manifest['files']), 'owned file set changed after sync'
        checked=0
        for name,digest in manifest['files'].items():
            assert sha(FAMILY/name)==digest, f'local changed after sync: {name}'
            assert sha(LAB/REL/name)==digest, f'formal Lab differs: {name}'
            checked+=1
        print(json.dumps({'status':'PASS','synchronized_owned_files':checked,'destination':str(LAB/REL)}))
        return
    target=FAMILY/'artifacts/delivery-verification.json'
    if target.exists():
        raise FileExistsError(target)
    checked={}

    def check(path,digest):
        path=path.resolve()
        assert path.is_relative_to(FAMILY), path
        actual=sha(path)
        assert actual==digest, f'hash mismatch: {path}'
        checked[str(path.relative_to(FAMILY))]=actual

    p0=FAMILY/'artifacts/p0-inputs'
    p0s=load(p0/'summary.json')
    assert p0s['source_pins_unchanged'] and not p0s['changed_family_files']
    check(p0/'frame-manifest.json',p0s['frame_manifest_sha256'])
    check(p0/'coverage.csv',p0s['coverage_sha256'])
    check(p0/'segments.csv',p0s['segments_sha256'])
    for name,digest in load(p0/'started.json')['family_files_sha256'].items():
        check(FAMILY/name,digest)
    shared_pins=load(p0/'started.json')['verified_src_files']
    for name,digest in shared_pins.items():
        assert sha(LAB/name)==digest, f'shared reader source changed: {name}'
    bundle_pin=load(p0/'started.json')['bundle_pin']
    assert sha(LAB/bundle_pin['bundle_path'])==bundle_pin['bundle_sha256']
    for symbol,entry in load(p0/'frame-manifest.json').items():
        check(p0/entry['path'],entry['sha256'])
        for key in ('request','startup_report'):
            check(p0/entry[key+'_path'],entry[key+'_sha256'])
    p1=FAMILY/'artifacts/p1-research'
    for name,digest in load(p1/'summary.json')['files'].items():
        check(p1/name,digest)
    for name,digest in load(p1/'panel-manifest.json')['pins'].items():
        check(FAMILY/name,digest)
    for run in ('p1-statistics','p1-statistics-exact-parity-r1','p1-statistics-exact-r1'):
        base=FAMILY/'artifacts'/run
        report=load(base/'report.json')
        for name,digest in report['artifact_sha256'].items():
            check(base/name,digest)
        receipt=load(base/'execution-receipt.json')
        check(base/'report.json',receipt['report_sha256'])
        for name,digest in receipt['pins'].items():
            check(FAMILY/name,digest)
    exact=load(FAMILY/'artifacts/p1-statistics-exact-r1/report.json')
    parity=load(FAMILY/'artifacts/p1-statistics-exact-parity-r1/report.json')
    assert parity['status']=='PASS' and parity['replicates_per_block']==2048
    assert parity['maximum_absolute_error']<=1e-10
    assert exact['status']=='COMPLETED'
    assert exact['bootstrap_reps']==1_000_000 and exact['metric_family_size']==46
    assert sorted(b['block_days'] for b in exact['blocks'])==[60,120]
    assert all(b['processed']==1_000_000 for b in exact['blocks'])
    p2=FAMILY/'artifacts/p2-capture'
    done=load(p2/'completed.json')
    assert done['output_contract_checks_passed'] and not done['changed_files']
    check(p2/'artifact-manifest.json',done['artifact_manifest_sha256'])
    for name,entry in load(p2/'artifact-manifest.json')['files'].items():
        check(p2/name,entry['sha256'])
    for name,digest in load(p2/'started.json')['pinned_files'].items():
        check(FAMILY/name,digest)
    tests=load(FAMILY/'artifacts/validation-tests.json')
    assert tests['pytest']['passed']==80 and tests['pytest']['failed']==0
    for name,digest in tests['pins'].items():
        check(FAMILY/'scripts'/name,digest)
    capture_audit_path=FAMILY/'artifacts/p2-independent-audit.json'
    capture_audit=load(capture_audit_path)
    assert capture_audit['file_hashes']['checked']==31 and not capture_audit['file_hashes']['failed']
    assert capture_audit['full_ledger']['trade_rows']==225998
    assert capture_audit['full_ledger']['checks'] and all(c['failures']==0 for c in capture_audit['full_ledger']['checks'].values())
    assert capture_audit['equity_sample_checks']['rows']==7673
    checked[str(capture_audit_path.relative_to(FAMILY))]=sha(capture_audit_path)
    rebuild=load(FAMILY/'artifacts/reconstruction-audit.json')
    assert rebuild['status']=='PASS' and rebuild['all_panel_rows']==597968
    assert rebuild['all_columns_exact'] and rebuild['all_symbols']==648
    assert rebuild['prefix_cases'] and all(p['signals_unchanged'] and p['mature_labels_unchanged'] for p in rebuild['prefix_cases'])
    check(p1/'panel.pkl.gz',rebuild['panel_sha256'])
    check(FAMILY/'scripts/verify_reconstruction.py',rebuild['script_sha256'])
    figure=FAMILY/'artifacts/path-illustration'
    figure_receipt=load(figure/'receipt.json')
    check(p1/'panel.pkl.gz',figure_receipt['panel_sha256'])
    check(FAMILY/'scripts/render_path_diagnostic.py',figure_receipt['script_sha256'])
    for name,digest in figure_receipt['files'].items():
        check(figure/name,digest)
    decision=load(FAMILY/'artifacts/decision-summary.json')
    assert decision['historical_candidate']==exact['selected_historical_candidate']
    check(FAMILY/'diagnostics/research-report-20260908.md',decision['report_sha256'])
    required=['README.md','binance-1d-mtcs-core-ledger.md','decision-log.md','scripts/README.md',
              'diagnostics/p2-independent-audit.md','diagnostics/p1-economic-interpretation.md',
              'diagnostics/statistics-approximation-audit.md','diagnostics/validation-and-delivery.md',
              'diagnostics/data-scope-and-funding.md','diagnostics/literature-boundary.md']
    for name in required:
        assert (FAMILY/name).is_file(), name
    links=0
    external_formal=[]
    for doc in FAMILY.rglob('*.md'):
        for href in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',doc.read_text()):
            href=href.strip('<>').split('#')[0]
            if not href or re.match(r'^[a-zA-Z]+://',href):
                continue
            dest=(doc.parent/unquote(href)).resolve()
            if dest==target:
                continue
            if not dest.exists() and dest.is_relative_to(ROOT) and not dest.is_relative_to(FAMILY):
                formal=LAB/dest.relative_to(ROOT)
                assert formal.exists(), f'broken link {doc}: {href}'
                external_formal.append(str(formal))
            else:
                assert dest.exists(), f'broken link {doc}: {href}'
            links+=1
    receipt={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'PASS',
             'checked_hash_files':len(checked),'checked_local_links':links,
             'formal_shared_links':sorted(set(external_formal)),
             'complete_exact_replicates_per_block':1_000_000,'necessary_tests_passed':80,
             'shared_reader_source_pins_unchanged':True,'shared_reader_files':len(shared_pins),
             'history_only':True,'fullcost_verified':False,'live_ready':False,
             'global_checks_scope':'this family verified; pre-existing repository consumer errors and frozen style warnings separately disclosed',
             'script_sha256':sha(Path(__file__)),'checked_files':checked}
    target.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='checked_files'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
