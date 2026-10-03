#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
import datetime,json,pathlib,hashlib
R=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=R/'specs/protocol.json';s=json.loads(p.read_text());assert s['frozen_at_utc'] is None
review=json.loads((R/'artifacts/independent-C1-static-review.json').read_text());assert review['status'].startswith('PASS'),review
s['frozen_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();files=[*sorted((R/'scripts').glob('*.py')),*sorted((R/'specs').glob('*')),*sorted((R/'artifacts').glob('C0-*.json')),R/'artifacts/independent-C1-static-review.json'];s['frozen_file_hashes']={str(f.relative_to(R)):sha(f) for f in files if f!=p and f.is_file()};p.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
receipt={'id':'M0316','checkpoint':'C1','status':'FROZEN_BEFORE_FIRST_RETURNS','frozen_at_utc':s['frozen_at_utc'],'protocol_sha256':sha(p),'engine_sha256':sha(R/'scripts/run_replay.py'),'source_qa':'PASS','independent_static_review':review['status'],'returns_seen_before_freeze':False,'cases':s['cases'],'strict_reproductions':0}
with (R/'artifacts/C1-freeze-receipt.json').open('x') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps(receipt,indent=2))
