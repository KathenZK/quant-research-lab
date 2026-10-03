"""Artificial gate fixtures; sentinel proves no input read or account import on rejection."""
if not __debug__:
    raise RuntimeError('M3710 rejects Python -O')
import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
import gates
import run_replay


def check(destination):
    assert not destination.exists();destination.mkdir(parents=True)
    family=destination/'fake-family';family.mkdir()
    paths=sorted(gates.REQUIRED_C0_PATHS)
    files=[]
    for rel in paths:
        p=family/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'ARTIFICIAL_GATE_PAYLOAD\n')
        files.append(dict(path=rel,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    c0=dict(id='M3710',status='FROZEN_PRE_HISTORY',files=files)
    c0path=family/'specs/C0-v1.json'
    review=destination/'fake-independent.json';review.write_text('{"synthetic":true}\n')
    gate=dict(status='ROOT_APPROVED_HISTORY_AFTER_INDEPENDENT_QA',id='M3710',
        C0_sha256='',authorized_strategy_configurations=4,new_controls=0,control_independently_accepted=True,
        control_reference_sha256=gates.sha(family/'specs/control-reference.json'),
        control_remote_acceptance_sha256=gates.sha(family/'specs/control-remote-acceptance.safe.json'),
        adapter_pin_sha256=gates.sha(family/'specs/adapter-pin.json'),source_commit='a'*40,
        independent_code_review=dict(status='PASS',local_path=str(review),sha256=gates.sha(review)))
    gatepath=destination/'root-gate-artificial.json';tests=[];reads=[];imports=[]
    class NeverHistorical:
        def read_bytes(self):reads.append('price');raise AssertionError('PRICE_READ_BEFORE_GATE_FAILURE')
    def no_engine():imports.append('engine');raise AssertionError('ENGINE_IMPORT_BEFORE_GATE_FAILURE')
    def save(c,g):
        c0path.write_text(json.dumps(c));g=copy.deepcopy(g)
        g['C0_sha256']=gates.sha(c0path);gatepath.write_text(json.dumps(g));return g
    def rejected(label,c=None,g=None,low_disk=False):
        save(c0 if c is None else c,gate if g is None else g)
        before=(len(reads),len(imports));out=destination/('output-'+str(len(tests)))
        patches=[patch.object(gates,'FAMILY',family),patch.object(run_replay,'engine',no_engine)]
        if low_disk:patches.append(patch.object(gates.shutil,'disk_usage',return_value=type('D',(),{'free':gates.RESERVE_BYTES+gates.OUTPUT_ALLOWANCE_BYTES-1})()))
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:stack.enter_context(p)
            try:run_replay.run(NeverHistorical(),out,gatepath)
            except (AssertionError,ValueError,KeyError,RuntimeError,FileNotFoundError):pass
            else:raise AssertionError('Gate accepted '+label)
        assert before==(len(reads),len(imports)),label
        assert not out.exists(),label
        tests.append(label)
    for label,mut in [
        ('missing required file',lambda c:c['files'].pop()),
        ('duplicate path',lambda c:c['files'].append(copy.deepcopy(c['files'][0]))),
        ('extra path',lambda c:c['files'].append(dict(path='extra.txt',bytes=1,sha256='a'*64))),
        ('bytes bool',lambda c:c['files'][0].__setitem__('bytes',True)),
        ('bytes float',lambda c:c['files'][0].__setitem__('bytes',22.0)),
        ('bytes zero',lambda c:c['files'][0].__setitem__('bytes',0)),
        ('sha invalid',lambda c:c['files'][0].__setitem__('sha256','z'*64)),
        ('sha uppercase',lambda c:c['files'][0].__setitem__('sha256','A'*64)),
        ('sha wrong bytes',lambda c:c['files'][0].__setitem__('sha256','a'*64)),
        ('absolute path',lambda c:c['files'][0].__setitem__('path','/tmp/README.md')),
        ('parent traversal',lambda c:c['files'][0].__setitem__('path','../README.md')),
        ('dot path',lambda c:c['files'][0].__setitem__('path','./README.md')),
        ('backslash path',lambda c:c['files'][0].__setitem__('path','scripts\\signals.py')),
        ('duplicate slash',lambda c:c['files'][0].__setitem__('path','scripts//signals.py')),
        ('draft status',lambda c:c.__setitem__('status','PRE_C0_DRAFT'))]:
        changed=copy.deepcopy(c0);mut(changed);rejected(label,c=changed)
    for key,value in [('authorized_strategy_configurations',4.0),('new_controls',False),
                      ('control_independently_accepted',1),('id','M3711'),
                      ('adapter_pin_sha256','a'*64),('source_commit','z'*40),
                      ('status','APPROVED')]:
        changed=copy.deepcopy(gate);changed[key]=value;rejected('gate '+key+' '+str(value),g=changed)
    rejected('disk below5GiB plus256MiB reserve',low_disk=True)
    save(c0,gate)
    with patch.object(gates,'FAMILY',family):
        gates.verify_c0();gates.check_gate(gatepath)
    tests.append('positive artificial C0/gate shape valid without engine or input')
    for module in ['run_replay.py','verify_replay.py','check_causality.py','rebuild_input.py','restore_run.py']:
        proc=subprocess.run([sys.executable,'-O',str(Path(__file__).parent/module),'--help'],capture_output=True,text=True)
        assert proc.returncode!=0 and 'rejects Python -O' in proc.stderr,module
        tests.append('Python -O rejected before import/input '+module)
    return dict(id='M3710',status='PASS',checks=len(tests),tests=tests,input_read_attempts=len(reads),
        engine_import_attempts=len(imports),synthetic_only=True,historical_features=0,historical_runs=0,new_controls=0)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--fixture-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=check(a.fixture_dir)
    with a.output.open('x') as h:json.dump(r,h,indent=2);h.write('\n')
    print(json.dumps(dict(status=r['status'],checks=r['checks'],input_read_attempts=r['input_read_attempts'])))
