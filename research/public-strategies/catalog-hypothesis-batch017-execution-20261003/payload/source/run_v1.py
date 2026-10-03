"""Batch017 thin v1 consumer for M1346 and M1270. No benchmark generation."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from daily_three_signals import build_features

ACTIVE_IDS = ('M1346', 'M1270')
KERNEL_PINS = {
    'engine.py':'5b92fea2db2a5da7c4ecd90356adaf8cb533dcedd7378992d2b8e8e324d43782',
    'verify_account.py':'338aa731bed5c6e2b46897ab2de190082fa29d96d252a686999610efce2d5dbe',
    'manifest.json':'9109be9de3b72ab09c0075fe0603a93c216cbbba238265ebb9194ce0bbe2a2b4',
}
FEATURE = ['index','open_time','bar_date','signal_available_ms','weekday','ready','close','lag25_close','roc25','raw_entry','price_or_calendar_exit','raw_exit']
AUDIT = ['eval_index','input_index','effective_time','ready','raw_entry','raw_exit','held','pending_before_side','pending_before_signal_index','pending_before_due_index','pending_after_side','pending_after_signal_index','pending_after_due_index','close_events','reason']
FILL_EXTRA = ['signal_effective_time','signal_available_time','entry_or_exit_reason']

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load_kernel(directory):
    for name,expected in KERNEL_PINS.items():
        assert sha(directory/name)==expected,('KERNEL_PIN_MISMATCH',name)
    spec=importlib.util.spec_from_file_location('batch017_pinned_daily_v1',directory/'engine.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def features(strategy_id, rows):
    if strategy_id not in ACTIVE_IDS:raise ValueError('M1349 remains gated for holding-timer kernel v2')
    result=[]
    for item in build_features(strategy_id,rows):
        item=dict(item)
        item['raw_exit']=int(item['price_or_calendar_exit'])
        for key in ['raw_entry','price_or_calendar_exit','ready']:item[key]=int(item[key])
        result.append(item)
    return result

def serial(row):
    return {k:('' if v is None else str(v) if not isinstance(v,(str,int)) else v) for k,v in row.items()}

def supplemental(strategy_id, rows, feat, result, kernel):
    audits=[]
    for j,decision in enumerate(result['decisions']):
        previous=None
        if j>0:
            n=result['nav'][j-1]
            if n['pending_side']:previous={'side':n['pending_side'],'signal_index':n['pending_signal_index'],'due_index':n['pending_due_index']}
        if previous is not None and previous['due_index']<=j:previous=None
        current=result['nav'][j]
        es=[e for e in result['pending'] if e['eval_index']==j and e['phase']=='CLOSE']
        audits.append(dict(eval_index=j,input_index=j+31,effective_time=decision['effective_time'],ready=feat[j+31]['ready'],raw_entry=decision['raw_entry'],raw_exit=decision['raw_exit'],held=decision['held'],pending_before_side='' if previous is None else previous['side'],pending_before_signal_index='' if previous is None else previous['signal_index'],pending_before_due_index='' if previous is None else previous['due_index'],pending_after_side=current['pending_side'],pending_after_signal_index=current['pending_signal_index'],pending_after_due_index=current['pending_due_index'],close_events=';'.join(e['event'] for e in es),reason='raw_opposite' if any(e['event']=='CANCELLED_OPPOSITE' for e in es) else 'retained_earliest' if any(e['event']=='RETAINED_EARLIEST' for e in es) else 'calendar_sunday' if strategy_id=='M1270' and decision['raw_entry'] else 'calendar_monday' if strategy_id=='M1270' and decision['raw_exit'] else 'momentum25_up' if decision['raw_entry'] else 'momentum25_down' if decision['raw_exit'] else 'no_event'))
    fills=[]
    for f in result['fills']:
        signal_ms=int(rows[31+f['signal_index']]['open_time'])+86400000
        fills.append(dict(**f,signal_effective_time=kernel.iso(signal_ms),signal_available_time=kernel.iso(signal_ms),entry_or_exit_reason=('calendar_sunday' if f['side']=='BUY' else 'calendar_monday') if strategy_id=='M1270' else ('momentum25_up' if f['side']=='BUY' else 'momentum25_down')))
    return audits,fills

def produce(strategy_id, rows, rules, out, kernel):
    out.mkdir(parents=True,exist_ok=False)
    feat=features(strategy_id,rows)
    kernel.csvout(out/'features.csv',[serial(x) for x in feat],FEATURE)
    summaries=[]
    for case in rules['cost_cases']:
        result=kernel.simulate(rows,feat,case)
        for key,columns in [('nav',kernel.NAV),('fills',kernel.FILL),('pending',kernel.EVENT),('decisions',kernel.DEC),('monthly',kernel.MONTH),('roundtrips',kernel.TRIP)]:
            kernel.csvout(out/f"{case['name']}-{key}.csv",result[key],columns)
        kernel.csvout(out/f"{case['name']}-daily-nav.csv",result['nav'],kernel.NAV)
        audits,enriched=supplemental(strategy_id,rows,feat,result,kernel)
        kernel.csvout(out/f"{case['name']}-intent-audit.csv",audits,AUDIT)
        kernel.csvout(out/f"{case['name']}-fills-complete.csv",enriched,kernel.FILL+FILL_EXTRA)
        kernel.dump(out/f"{case['name']}-summary.json",result['summary'])
        summaries.append(result['summary'])
    top=dict(id=strategy_id,classification='HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED',execution_class='ADAPTED_EXECUTION_PROXY',quality_status='DIAGNOSTIC_ONLY',trusted=False,window_OOS=False,strict_reproductions=0,strategy_configurations=4,new_controls=0,cases=summaries)
    kernel.dump(out/'summary.json',top)
    kernel.dump(out/'manifest.json',[dict(path=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(out.iterdir())])
    return top

def check_c0(bundle, c0_path):
    c0=json.loads(c0_path.read_bytes())
    assert c0['status']=='FROZEN_BEFORE_HISTORICAL_RETURNS'
    assert c0['strategy_ids']==list(ACTIVE_IDS) and c0['strategy_configurations']==8 and c0['new_controls']==0
    for item in c0['pins']:
        p=bundle/item['path'];assert p.stat().st_size==item['bytes'] and sha(p)==item['sha256'],item['path']
    gate=json.loads((bundle/'review/independent/prehistory-executable-v1.json').read_bytes())
    assert gate['status']=='PASS' and gate['historical_strategy_runs']==0
    return c0

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--c0',type=Path,required=True)
    args=parser.parse_args();bundle=args.bundle.resolve()
    check_c0(bundle,args.c0)
    kernel=load_kernel(bundle/'kernel/v1');kernel.environment(bundle/'frozen/runtime-v1.json')
    rows=kernel.load_input(args.input,dict(input=dict(bytes=128196,sha256='48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5'),evaluation_start_ms=1672531200000,evaluation_end_ms=1735689600000))
    assert not args.output.exists()
    for strategy_id in ACTIVE_IDS:
        rules=json.loads((bundle/f'frozen/{strategy_id}-root-frozen-rules.json').read_bytes())
        produce(strategy_id,rows,rules,args.output/strategy_id,kernel)
    print(json.dumps(dict(status='COMPLETED',strategy_ids=list(ACTIVE_IDS),strategy_configurations=8,new_controls=0,strict_reproductions=0)))

if __name__=='__main__':main()
