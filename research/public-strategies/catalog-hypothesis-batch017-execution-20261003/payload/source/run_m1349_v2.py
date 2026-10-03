"""M1349 thin ROC feature consumer; immutable v2 owns actual holding lifecycle."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from daily_three_signals import build_features

POLICY={'max_completed_closes':25}
PINS={'engine.py':'2b3354dc5c210c66749c5b1e595831abb2adc3f6fff6b9b5f06d22e9fcb39219','verify_account.py':'191961bece1b80c02d074894a8f48fde8c3f6360b5ab564cc69484fae3b14712','manifest.json':'0f5d96e56c1dfe396320d5d80932d09218291379495045a31b0564c1ef16bb5a'}
FEATURE=['index','open_time','bar_date','signal_available_ms','weekday','ready','close','lag25_close','roc25','raw_entry','price_or_calendar_exit','raw_exit']
AUDIT=['eval_index','input_index','effective_time','ready','raw_entry','raw_exit','effective_entry','effective_exit','held','held_completed_bars','mandatory_exit_latched','mandatory_exit_trigger_index','pending_before_side','pending_before_signal_index','pending_before_due_index','pending_after_side','pending_after_signal_index','pending_after_due_index','close_events','reason']
FILL_EXTRA=['signal_effective_time','signal_available_time','entry_or_exit_reason']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load_kernel(directory):
    for name,expected in PINS.items():assert sha(directory/name)==expected,('KERNEL_PIN_MISMATCH',name)
    for x in json.loads((directory/'manifest.json').read_bytes())['files']:
        p=directory/x['path'];assert p.stat().st_size==x['bytes'] and sha(p)==x['sha256']
    s=importlib.util.spec_from_file_location('batch017_pinned_daily_v2',directory/'engine.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def features(rows):
    result=[]
    for f in build_features('M1349',rows):
        f=dict(f,raw_exit=0)
        for k in ['raw_entry','price_or_calendar_exit','ready']:f[k]=int(f[k])
        assert f['price_or_calendar_exit']==0
        result.append(f)
    return result
def serial(row):return {k:('' if v is None else str(v) if not isinstance(v,(str,int)) else v) for k,v in row.items()}
def supplemental(rows,feat,result,kernel):
    audits=[]
    for j,d in enumerate(result['decisions']):
        before=None
        if j>0:
            p=result['nav'][j-1]
            if p['pending_side'] and p['pending_due_index']>j:before=dict(side=p['pending_side'],signal_index=p['pending_signal_index'],due_index=p['pending_due_index'])
        after=result['nav'][j];events=[x for x in result['pending'] if x['eval_index']==j and x['phase']=='CLOSE']
        audits.append(dict(eval_index=j,input_index=j+31,effective_time=d['effective_time'],ready=feat[j+31]['ready'],raw_entry=d['raw_entry'],raw_exit=d['raw_exit'],effective_entry=d['effective_entry'],effective_exit=d['effective_exit'],held=d['held'],held_completed_bars=d['held_completed_bars'],mandatory_exit_latched=d['mandatory_exit_latched'],mandatory_exit_trigger_index=d['mandatory_exit_trigger_index'],pending_before_side='' if before is None else before['side'],pending_before_signal_index='' if before is None else before['signal_index'],pending_before_due_index='' if before is None else before['due_index'],pending_after_side=after['pending_side'],pending_after_signal_index=after['pending_signal_index'],pending_after_due_index=after['pending_due_index'],close_events=';'.join(x['event'] for x in events),reason='time25' if d['mandatory_exit_latched'] else 'roc25_below_minus10' if d['raw_entry'] else 'no_event'))
    fills=[]
    for f in result['fills']:
        ms=int(rows[31+f['signal_index']]['open_time'])+86400000
        fills.append(dict(**f,signal_effective_time=kernel.iso(ms),signal_available_time=kernel.iso(ms),entry_or_exit_reason='roc25_below_minus10' if f['side']=='BUY' else 'time25'))
    return audits,fills
def produce(rows,rules,out,kernel):
    out.mkdir(parents=True,exist_ok=False);feat=features(rows)
    kernel.csvout(out/'features.csv',[serial(x) for x in feat],FEATURE);summaries=[]
    for case in rules['cost_cases']:
        result=kernel.simulate(rows,feat,case,execution_policy=POLICY)
        for kind in ['nav','fills','pending','decisions','monthly','roundtrips']:
            kernel.csvout(out/f"{case['name']}-{kind}.csv",result[kind],kernel.output_columns(kind,execution_policy=POLICY))
        kernel.csvout(out/f"{case['name']}-daily-nav.csv",result['nav'],kernel.output_columns('nav',execution_policy=POLICY))
        audits,fills=supplemental(rows,feat,result,kernel)
        kernel.csvout(out/f"{case['name']}-intent-audit.csv",audits,AUDIT)
        kernel.csvout(out/f"{case['name']}-fills-complete.csv",fills,kernel.FILL+FILL_EXTRA)
        kernel.dump(out/f"{case['name']}-summary.json",result['summary']);summaries.append(result['summary'])
    top=dict(id='M1349',classification='HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED',execution_class='ADAPTED_EXECUTION_PROXY',quality_status='DIAGNOSTIC_ONLY',trusted=False,window_OOS=False,strict_reproductions=0,strategy_configurations=4,new_controls=0,execution_policy=POLICY,cases=summaries)
    kernel.dump(out/'summary.json',top);kernel.dump(out/'manifest.json',[dict(path=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(out.iterdir())]);return top
def check_c0(bundle,path):
    c=json.loads(path.read_bytes());assert c['status']=='FROZEN_BEFORE_HISTORICAL_RETURNS' and c['strategy_ids']==['M1349'] and c['strategy_configurations']==4 and c['new_controls']==0
    for pin in c['pins']:
        f=bundle/pin['path'];assert f.stat().st_size==pin['bytes'] and sha(f)==pin['sha256'],pin['path']
    q=json.loads((bundle/'review/independent/prehistory-m1349-v2.json').read_bytes());assert q['status']=='PASS' and q['M1349_historical_runs']==0
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--c0',type=Path,required=True);a=p.parse_args();root=a.bundle.resolve()
    check_c0(root,a.c0);kernel=load_kernel(root/'kernel/v2');kernel.environment(root/'frozen/runtime-v1.json')
    rows=kernel.load_input(a.input,dict(input=dict(bytes=128196,sha256='48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5'),evaluation_start_ms=1672531200000,evaluation_end_ms=1735689600000))
    rules=json.loads((root/'frozen/M1349-root-frozen-rules.json').read_bytes());produce(rows,rules,a.output/'M1349',kernel)
    print(json.dumps(dict(status='COMPLETED',strategy_ids=['M1349'],strategy_configurations=4,new_controls=0,strict_reproductions=0)))
if __name__=='__main__':main()
