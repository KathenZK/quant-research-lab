"""最终只读验收：固定输入、被解释结果、计算源码、正文链接与当前源码。"""
from pathlib import Path
import json
import re
from urllib.parse import unquote, urlparse
from run_research import FAMILY, INPUT, sha, save


def main():
    lab=Path('/Users/ZK/OpenCode/quant-strategy-lab');art=FAMILY/'artifacts'
    out=art/'delivery-20260908.json'
    errors=[];checked=0
    pins=json.loads((FAMILY/'specs/source-pins-20260908.json').read_text())
    for p,h in pins['files'].items():
        checked+=1
        if sha(lab/p)!=h:
            if p=='scripts/governance/check_trusted_consumers.py':
                # Only the three explicitly owned registrations may explain this startup pin change.
                import hashlib
                text=(lab/p).read_text()
                blocks=re.findall(r'    ConsumerSpec\(\n        "research/asset-portfolios/1d-ma7-bidirectional-trend-generalization/.*?    \),\n',text,re.S)
                assert len(blocks)==3
                for block in blocks:text=text.replace(block,'',1)
                if hashlib.sha256(text.encode()).hexdigest()!=h:errors.append('unexplained registry change')
            else:errors.append('source pin drift: '+p)
    frames=json.loads((INPUT/'frame-manifest.json').read_text())
    for symbol,entry in frames.items():
        if sha(INPUT/entry['path'])!=entry['sha256']:errors.append('input frame changed: '+symbol)
    assert len(frames)==874
    expected={
        'p1-development-20260908-r1':'f1d3a55779850cb25912051284b2e724a0e8473c71ad74285f3ce27a02bcda0f',
        'p1-evaluation-20260908-r1':'0b9daaafe44dac5a83c73b6f1a49c7f8a0460e6b21cf54adcb694e0818c656f4',
        'p2-applicability-20260908-r2':'40589a2dde6ff203d45bbacbd0defcd2429e641b16a40b51a4bcd1f598d8988a'}
    for d,h in expected.items():
        if sha(art/d/'results.csv')!=h:errors.append('result changed: '+d)
        assert (art/d/'completed.json').exists() and not (art/d/'INVALIDATED.json').exists()
    lock=json.loads((art/'p1-development-20260908-r1/selection-lock.json').read_text())
    assert sha(FAMILY/'specs/research-contract-p1-20260908.md')==lock['contract_sha256']
    snap=art/'source-snapshots/20260908-computation'
    evaluation=json.loads((art/'p1-evaluation-20260908-r1/started.json').read_text())
    computational={
        'engine.py':evaluation['source_sha256']['engine.py'],
        'run_research.py':evaluation['source_sha256']['run_research.py'],
        'run_applicability.py':json.loads((art/'p2-applicability-20260908-r2/started.json').read_text())['script_sha256'],
        'statistical_review.py':json.loads((art/'p3-statistics-20260908-r1/completed.json').read_text())['source_sha256']}
    for name,h in computational.items():
        if sha(snap/(name+'.txt'))!=h:errors.append('computational snapshot mismatch: '+name)
    assert sha(FAMILY/'scripts/engine.py')==computational['engine.py']
    html=art/'p4-trade-paths-20260908/MA7多空趋势_交易路径.html'
    assert sha(html)==json.loads((html.parent/'verification.json').read_text())['html_sha256']
    if not out.exists():save(out,{'status':'CHECK_IN_PROGRESS'})
    links=0
    for md in FAMILY.rglob('*.md'):
        for raw in re.findall(r'\[[^\]]*\]\(([^)]+)\)',md.read_text()):
            raw=raw.strip('<>');u=urlparse(raw)
            if u.scheme or not u.path:continue
            target=(md.parent/unquote(u.path)).resolve();links+=1
            if not target.exists():errors.append(f'broken link {md.relative_to(FAMILY)} -> {raw}')
    consumer=json.loads((art/'consumer-check-final.json').read_text())
    assert consumer['own_errors']==[] and consumer['same_as_preexisting_six']
    record={'status':'PASS' if not errors else 'FAIL','errors':errors,'fixed_source_pins_checked':checked,
        'input_frame_file_hashes_checked':len(frames),'primary_result_hashes':expected,
        'registry_pin_delta':'three owned consumer registrations; removing only those exactly reconstructs startup pin',
        'original_computation_source_hashes':computational,'engine_unchanged_since_accepted_evaluation':True,
        'contract_hash_unchanged':True,'local_links_checked':links,'HTML_hash_unchanged':True,
        'current_script_sha256':{p.name:sha(p) for p in sorted((FAMILY/'scripts').glob('*.py'))},
        'current_document_sha256':{str(p.relative_to(FAMILY)):sha(p) for p in sorted(FAMILY.rglob('*.md'))},
        'repo_consumer_gate':'FAIL_PREEXISTING_SIX','artifact_budget_gate':'C_EXTERNALIZE_AND_D_PROHIBITED_NEW_GIT_LOCAL_ONLY',
        'visual_browser_QA':'BLOCKED_LOCAL_FILE_URL_POLICY','no_full_cost_or_live_readiness_claim':True,
        'formal_destination':'/Users/ZK/OpenCode/quant-strategy-lab/research/asset-portfolios/1d-ma7-bidirectional-trend-generalization',
        'sync_manifest_is_separate':'artifacts/sync-manifest.json'}
    save(out,record)
    print(json.dumps({'status':record['status'],'errors':errors,'source_pins':checked,'frames':len(frames),'local_links':links}))
    assert not errors


if __name__=='__main__':main()
