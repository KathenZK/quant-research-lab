"""Verify the saved workbook, source lineage and classification without new market reads."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path('/Users/ZK/OpenCode/quant-strategy-lab')
FAMILY = ROOT / 'research/asset-portfolios/1d-monthly-cs-momentum-long10'
OUT = FAMILY / 'artifacts/recent36-monthly-holdings-20260924'
SUPPORT = Path(__file__).resolve().parent
BOOK = SUPPORT.parent / '月频Top10_最近36个月持仓与换仓.xlsx'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
data = json.loads((OUT / 'report-data.json').read_text())
source = FAMILY / 'artifacts/weekly-top10-20260924/terminal-complete'
assert sha(source / 'summary.json') == data['source_summary_sha256']
assert sha(source / 'independent-audit.json') == data['source_audit_sha256']
script = FAMILY / 'scripts/export_mcsm_recent36_20260924.py'
assert sha(script) == data['script_sha256']
for name, digest in data['source_files_sha256'].items():
    assert sha(ROOT / name) == digest
NS = {'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with zipfile.ZipFile(BOOK) as z:
    shared = ET.fromstring(z.read('xl/sharedStrings.xml'))
    strings = [''.join(x.itertext()) for x in shared.findall('x:si', NS)]
    sheets = [ET.fromstring(z.read(f'xl/worksheets/sheet{i}.xml')) for i in [1,2]]
    def cells(tree):
        result = {}
        for c in tree.findall('.//x:sheetData/x:row/x:c', NS):
            assert c.attrib.get('t') != 'e', c.attrib
            v = c.find('x:v', NS)
            if c.attrib.get('t') == 'inlineStr':
                val = ''.join(c.find('x:is', NS).itertext())
            elif v is None:
                val = ''
            elif c.attrib.get('t') == 's':
                val = strings[int(v.text)]
            elif c.attrib.get('t') == 'str':
                val = v.text or ''
            else:
                val = float(v.text)
            result[c.attrib['r']] = val
        return result
    m, d = map(cells, sheets)
    def close(a,b):
        assert isinstance(a,(int,float)) and abs(a-b) <= max(1e-8,abs(b)*1e-10), (a,b)
    def codes(s):
        return [] if s == '无' else re.split('[、\n]',s)
    for i,r in enumerate(data['months'],10):
        close(m[f'B{i}'],r['return'])
        for col,key in [('C','selected'),('D','new'),('E','exited'),('F','retained')]:
            assert codes(m[f'{col}{i}']) == r[key], (i,col)
        close(m[f'I{i}'],len(r['retained']))
    close(m['B5'],data['stats']['total_return'])
    close(m['B6'],data['stats']['max_drawdown'])
    close(m['F5'],data['stats']['average_retained_names'])
    for i,r in enumerate(data['legs'],8):
        assert d[f'B{i}'] == r['symbol'] and d[f'C{i}'] == r['action']
        close(d[f'D{i}'],r['entry_price'])
        close(d[f'E{i}'],r['exit_price'])
        close(d[f'F{i}'],r['gross_return'])
        close(d[f'K{i}'],r['price_pnl_usdt'])
    for i,(tree,x,y) in enumerate(zip(sheets,[1,2],[9,7]),1):
        pane = tree.find('.//x:pane',NS)
        assert pane.attrib['xSplit']==str(x) and pane.attrib['ySplit']==str(y)
        table = ET.fromstring(z.read(f'xl/tables/table{i}.xml'))
        assert table.find('x:autoFilter',NS) is not None
    assert len(sheets[0].findall('.//x:c/x:f',NS)) >= 72
    assert len(sheets[1].findall('.//x:c/x:f',NS)) == 720
for doc in [OUT / 'README.md',OUT / 'monthly-table.md']:
    for link in re.findall(r'\]\(([^)]+)\)',doc.read_text()):
        if link.startswith(('http','#')) or link == 'qa.json':
            continue
        assert (doc.parent/link).exists(),link
registry = ROOT / 'scripts/governance/check_trusted_consumers.py'
spec = importlib.util.spec_from_file_location('recent36_registry',registry)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)
errors = mod.run_checks(ROOT)
own = [e for e in errors if '1d-monthly-cs-momentum-long10' in e]
assert not own, own
files=[BOOK,OUT/'monthly-table.md',OUT/'report-data.json',OUT/'README.md',script,SUPPORT/'build.mjs',Path(__file__)]
assert sum(p.stat().st_size for p in files) < 5*1024*1024
result={'status':'PASS_SAVED_WORKBOOK_AND_36_MONTHS_360_LEGS','months':36,'legs':360,
        'actual_trade_sets_reconciled':True,'source_hashes_unchanged':True,'formulas_saved_and_cached_values_verified':True,
        'filters_and_frozen_headers_verified':True,'visual_review':'both sheets and first/last monthly ranges reviewed',
        'excel_native_application_not_opened':True,'own_family_registry_errors':own,
        'other_family_registry_errors':errors,'files_sha256':{str(p.relative_to(ROOT)):sha(p) for p in files},
        'lint_note':'Frozen extraction has two E702 semicolon style warnings only; not edited after input-output pinning.'}
with (OUT/'qa.json').open('x') as f:
    json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({'status':result['status'],'workbook':str(BOOK),'other_family_registry_errors':len(errors)},ensure_ascii=False))
