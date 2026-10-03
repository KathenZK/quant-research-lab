#!/usr/bin/env python3
"""Offline source-rule audit. Standard library only; NEVER imports/executes third-party files.
All numeric cases are invented scalar/short-array fixtures, not market histories.
"""
import argparse, ast, hashlib, json, math, statistics, sys
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path

IDS = {'M0296': ('SMACrossover', '453440d7b934c494934a1c56b3826d94638594f79ad4e4c7faaff36b96d33fae'),
       'M0299': ('SimpleBollinger', '746cc0f8644a7fae12089f597448b573d4d482a3855c870d18b4a7bfeb0a5255'),
       'M0312': ('TradingView_RSI', '86a0532e427cfe3b4f3ff9fa94c7d007ffb544c96db7fa20613b7ebf724d2769'),
       'M0314': ('TurtleRules', '35e4c3cd69010ca81402277693cb6f7deaf52a284153f20f25d4cf605701408a')}
D = Decimal

def sha(data): return hashlib.sha256(data).hexdigest()
def canonical(obj): return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
def safe(v):
    if isinstance(v,float) and not math.isfinite(v): return 'NaN' if math.isnan(v) else str(v)
    if isinstance(v,Decimal): return str(v)
    if isinstance(v,(list,tuple)): return [safe(x) for x in v]
    if isinstance(v,dict): return {k:safe(x) for k,x in v.items()}
    return v

def ast_fingerprint(path):
    raw=path.read_bytes(); tree=ast.parse(raw)
    methods=[]
    for cl in [n for n in tree.body if isinstance(n,ast.ClassDef)]:
        for m in cl.body:
            if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef)):
                methods.append({'class':cl.name,'method':m.name,'lines':[m.lineno,m.end_lineno],
                                'ast_sha256':sha(ast.dump(m,include_attributes=False).encode())})
    return {'bytes':len(raw),'sha256':sha(raw),'python_ast_sha256':sha(ast.dump(tree,include_attributes=False).encode()),
            'ast_schema':'CPython3.12 ast.dump(include_attributes=False); includes literal docstrings; excludes comments/location',
            'methods':methods},tree

def qty(balance, price, fee=0, precision=3):
    adjusted=balance*(1-3*fee) if fee else balance
    return math.floor(adjusted/price*10**precision)/10**precision

def qty_decimal(balance, price, fee='0', precision=3):
    b,p,f=map(lambda x:D(str(x)),(balance,price,fee)); return (b*(1-3*f)/p).quantize(D(10)**-precision,rounding=ROUND_FLOOR)

def crossed(prior,current,level,direction):
    return (prior<=level and current>level) if direction=='above' else (prior>=level and current<level)

def cloud(candles):
    if len(candles)<80:return (math.nan,)*4
    c=candles[-80:]; earlier=c[:-25]
    def middle(seq,n):return (max(x[0] for x in seq[-n:])+min(x[1] for x in seq[-n:]))/2
    return (middle(c,9),middle(c,26),(middle(earlier,9)+middle(earlier,26))/2,middle(earlier,52))

def cloud_index_oracle(candles):
    if len(candles)<80:return (math.nan,)*4
    t=len(candles)-1
    def center(end,n):
        ids=range(end-n+1,end+1)
        return (max(D(str(candles[i][0])) for i in ids)+min(D(str(candles[i][1])) for i in ids))/2
    return tuple(float(v) for v in [center(t,9),center(t,26),(center(t-25,9)+center(t-25,26))/2,center(t-25,52)])

def turtle_signal(high,low,upper,lower,exit_mode=False):
    if high>=upper:return 'exit_short' if exit_mode else 'entry_long'
    if low<=lower:return 'exit_long' if exit_mode else 'entry_short'
    return None

class Cases:
    def __init__(self):self.items=[]
    def add(self,id,name,observed,expected,basis='self-authored scalar/array model; no native engine execution'):
        equal = observed==expected
        self.items.append({'id':id,'case':name,'observed':safe(observed),'expected':safe(expected),'pass':bool(equal),'basis':basis})
        if not equal:raise AssertionError((id,name,observed,expected))

def synthetic():
    t=Cases()
    # SMA relation is a state, not an event. Independent arithmetic oracle uses Decimal.
    t.add('M0296','strict_long_relation',51>50,True)
    t.add('M0296','strict_short_relation',49<50,True)
    t.add('M0296','equality_neither_direction',(50>50,50<50),(False,False))
    t.add('M0296','unchanged_above_still_eligible_flat',(51>50,crossed(51,52,50,'above')),(True,False))
    c=[float(i) for i in range(1,202)]
    f,s=sum(c[-50:])/50,sum(c[-200:])/200
    fd,sd=sum(D(str(v)) for v in c[-50:])/50,sum(D(str(v)) for v in c[-200:])/200
    t.add('M0296','sma50_200_decimal_oracle',(f,s),(float(fd),float(sd)))
    t.add('M0296','reverse_state_exit_long_and_short',(49<50,51>50),(True,True))
    t.add('M0296','undefined_sma_no_entry',math.nan>1,False)
    t.add('M0296','fee_and_floor_budget',qty(10000,100,.001),float(qty_decimal(10000,100,'.001')))
    # BB population variance and shifted historical Ichimoku spans.
    x=[float(i) for i in range(1,21)]; mean=statistics.mean(x); sd=statistics.pstdev(x)
    xd=list(map(lambda v:D(str(v)),x)); md=sum(xd)/20; vard=sum((v-md)**2 for v in xd)/20
    t.add('M0299','bb20_population_variance',round(sd*sd,10),float(vard))
    t.add('M0299','bb_default_two_std',round(mean+2*sd,10),round(float(md+2*vard.sqrt()),10))
    t.add('M0299','hl2_uses_high_low_not_open_close',(120+80)/2,100)
    t.add('M0299','upper_and_both_cloud_filter',111>110 and 111>105 and 111>108,True)
    t.add('M0299','cloud_one_span_blocks',111>110 and 111>105 and 111>112,False)
    t.add('M0299','upper_equality_not_entry',110>110,False)
    t.add('M0299','middle_equality_not_exit',100<100,False)
    t.add('M0299','middle_strict_exit',99<100,True)
    candles=[(float(i+2),float(i)) for i in range(80)]
    t.add('M0299','cloud_80_ramp_exact_indices',cloud(candles),(76.0,67.5,46.75,29.5))
    t.add('M0299','cloud_79_is_nan',all(math.isnan(v) for v in cloud(candles[:79])),True)
    for n in [80,81,100,200]:
        a=[(float((i*17)%71+10),float((i*17)%71+2)) for i in range(n)]
        t.add('M0299',f'cloud_index_decimal_oracle_n{n}',cloud(a),cloud_index_oracle(a))
    changed=candles.copy();changed[-1]=(10000.,-10000.)
    t.add('M0299','last25_do_not_affect_shifted_spans',cloud(changed)[2:],cloud(candles)[2:])
    enlarged=candles+[(999999.,-999999.)]*15
    t.add('M0299','decision_prefix_ignores_future_suffix',cloud(enlarged[:80]),cloud(candles))
    # RSI boundary semantics and strict margin gate. These are RSI-input fixtures, not a price-history replay.
    for name,prior,current,level,direction,expected in [
        ('enter_equal_prior_allowed',35,36,35,'above',True),('enter_equal_current_not_allowed',34,35,35,'above',False),
        ('above_state_not_cross',36,37,35,'above',False),('exit75_equal_prior_allowed',75,74,75,'below',True),
        ('exit75_equal_current_not_allowed',76,75,75,'below',False),('emergency_cross10',10,9,10,'below',True),
        ('already_below10_not_new_cross',9,8,10,'below',False)]:t.add('M0312',name,crossed(prior,current,level,direction),expected)
    t.add('M0312','default5_outside_declared10_30',10<=5<=30,False)
    t.add('M0312','literal_default_injection_not_clipped',{'rsi':5}['rsi'],5)
    for name,b,p,f,expected in [('zero_fee_equal_margin_blocks',10000,100,0,False),('fee_buffer_makes_margin_strict',10000,100,.001,True),('floor_remainder_makes_margin_strict',100,3,0,True)]:
        q=qty(b,p,f)
        t.add('M0312',name,b>q*p,expected)
        t.add('M0312',name+'_decimal_qty',q,float(qty_decimal(b,p,f)))
    t.add('M0312','precision3_not_leverage',qty(100,3),33.333)
    t.add('M0312','insufficient_margin_blocks',50>qty(100,3)*3,False)
    t.add('M0312','tiny_balance_zero_qty',qty(.01,100000),0)
    t.add('M0312','price_brackets_5pct_10pct',(100*.95,100*1.1),(95.0,110.00000000000001))
    # Reference intrabar sorter for two pre-existing orders strictly either side of open.
    t.add('M0312','reference_green_or_doji_both_hit_first','stop' if 100<=101 else 'profit','stop')
    t.add('M0312','reference_red_both_hit_first','profit' if 100>99 else 'stop','profit')
    # Turtle branch ordering, risk, counters, callback dependency. No historical orders are produced.
    t.add('M0314','upper_equality_enters',turtle_signal(110,100,110,90),'entry_long')
    t.add('M0314','lower_equality_enters',turtle_signal(100,90,110,90),'entry_short')
    t.add('M0314','both_bounds_prioritize_long',turtle_signal(110,90,110,90),'entry_long')
    t.add('M0314','both_exit_bounds_prioritize_exit_short',turtle_signal(110,90,110,90,True),'exit_short')
    t.add('M0314','both_bounds_suppress_long_exit_branch',turtle_signal(110,90,110,90,True)=='exit_long',False)
    highs=[100]*19+[110];lows=[90]*19+[80]
    t.add('M0314','donchian_includes_current_bar',(max(highs[-20:]),min(lows[-20:])),(110,80))
    t.add('M0314','repeated_extreme_equal_can_signal',turtle_signal(100,95,100,90),'entry_long')
    unit=(.01*10000)/10
    t.add('M0314','one_atr_unit_quantity',unit,10.0)
    t.add('M0314','two_atr_initial_loss_fraction',unit*2*10/10000,.02)
    entries=[100,105,110,115];stop=115-20
    t.add('M0314','constant_atr_four_units_risk_example',sum((e-stop)*unit for e in entries)/10000,.05)
    t.add('M0314','half_atr_equality_no_add',105>100+.5*10,False)
    t.add('M0314','half_atr_strict_add',105.01>100+.5*10,True)
    t.add('M0314','no_add_when_counter4',4<4,False)
    t.add('M0314','increased_atr_can_widen_stop',110-2*20 < 105-2*5,True)
    t.add('M0314','before_forces_s1',dict(system_type='S1',entry_dc_period=20,exit_dc_period=10),{'system_type':'S1','entry_dc_period':20,'exit_dc_period':10})
    # hypothetical direct callback invocation demonstrates function state transition only, not reachability.
    profitable=True;first=not profitable;profitable=False;second=not profitable
    t.add('M0314','legacy_filter_consumes_flag_once_if_invoked',(first,second),(False,True))
    level=0;level+=1;filter_pass=False
    t.add('M0314','submission_side_effect_before_rejected_filter',(level,filter_pass),(1,False))
    modern_dispatch={'opening_position':'on_open_position','closing_position':'on_close_position','increased_position':'on_increased_position','reduced_position':'on_reduced_position'}
    t.add('M0314','reference_dispatch_has_no_old_profit_callback','on_take_profit' in modern_dispatch.values(),False)
    t.add('M0314','reference_dispatch_has_no_old_stop_callback','on_stop_loss' in modern_dispatch.values(),False)
    t.add('M0314','positive_liquidate_tp_alone_not_callback',('take_profit','on_close_position'),('take_profit','on_close_position'))
    return t.items

def source_checks(evidence):
    output={}; common=[]
    def check(label,condition):
        common.append({'check':label,'pass':bool(condition)})
        if not condition: raise AssertionError(label)
    for id,(name,expected) in IDS.items():
        fp,tree=ast_fingerprint(evidence/'example-strategies'/name/'__init__.py')
        check(id+'_exact_source_sha',fp['sha256']==expected)
        cl=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==name)
        methods={n.name:n for n in cl.body if isinstance(n,ast.FunctionDef)}
        fp['called_function_names']=sorted(set(ast.unparse(n.func) for n in ast.walk(cl) if isinstance(n,ast.Call)))
        fp['defined_methods']=list(methods);output[id]=fp
        if id=='M0296':
            check('sma_signal_has_no_crossed_call',all('crossed' not in ast.unparse(methods[x]) for x in ['should_long','should_short']))
            check('sma_fast50_slow200', 'ta.sma(self.candles, 50)' in ast.unparse(methods['fast_sma']) and 'ta.sma(self.candles, 200)' in ast.unparse(methods['slow_sma']))
        elif id=='M0299':
            check('bb_hl2_and_default_cloud', "source_type='hl2'" in ast.unparse(methods['bb']) and 'ta.ichimoku_cloud(self.candles)' in ast.unparse(methods['ichimoku']))
            check('bb_cancel_true',isinstance(methods['should_cancel_entry'].body[0],ast.Return) and methods['should_cancel_entry'].body[0].value.value is True)
        elif id=='M0312':
            hp_return=methods['hyperparameters'].body[0].value
            hp=[]
            for dic in hp_return.elts:
                hp.append({ast.literal_eval(k): (v.id if isinstance(v,ast.Name) else ast.literal_eval(v)) for k,v in zip(dic.keys,dic.values)})
            fp['hyperparameters']=hp
            check('rsi_default5_outside10_30',hp[0]=={'name':'rsi','type':'int','min':10,'max':30,'default':5})
            calls=[n for n in ast.walk(cl) if isinstance(n,ast.Call) and ast.unparse(n.func)=='utils.size_to_qty']
            check('rsi_third_positional_literal3',len(calls)==2 and all(n.args[2].value==3 for n in calls))
            check('rsi_strict_margin_gt','self.available_margin > qty * self.price' in ast.unparse(methods['should_long']))
        else:
            text=ast.unparse(cl)
            check('turtle_no_direct_take_profit_assignment',not any(isinstance(n,ast.Attribute) and isinstance(n.ctx,ast.Store) and n.attr=='take_profit' for n in ast.walk(cl)))
            check('turtle_legacy_callbacks_defined',all(n in methods for n in ['on_take_profit','on_stop_loss']))
            check('turtle_forced_s1_before',"self.vars['system_type'] = 'S1'" in ast.unparse(methods['before']))
            check('turtle_entry_priority_high_first',ast.unparse(methods['entry_signal']).index('self.high >= upperband')<ast.unparse(methods['entry_signal']).index('self.low <= lowerband'))
            check('turtle_exit_priority_high_first',ast.unparse(methods['exit_signal']).index('self.high >= upperband')<ast.unparse(methods['exit_signal']).index('self.low <= lowerband'))
    util=(evidence/'jesse-reference/jesse/utils.py').read_text();strategy=(evidence/'jesse-reference/jesse/strategies/Strategy.py').read_text()
    st=ast.parse(strategy);cl=next(n for n in st.body if isinstance(n,ast.ClassDef) and n.name=='Strategy');funcs={n.name:n for n in cl.body if isinstance(n,ast.FunctionDef)}
    check('reference_size_arg3_precision', 'def size_to_qty(position_size: float, entry_price: float, precision: int = 3, fee_rate: float = 0)' in util)
    check('reference_fee_buffer_x3','position_size *= 1 - fee_rate * 3' in util)
    check('reference_init_injects_default_literal',"self.hp[dna['name']] = dna['default']" in strategy)
    check('reference_liquidate_positive_sets_takeprofit','self.take_profit' in ast.unparse(funcs['liquidate']))
    calls=[ast.unparse(n.func) for n in ast.walk(funcs['_on_updated_position']) if isinstance(n,ast.Call)]
    check('reference_updated_dispatch_has_no_legacy_callbacks',not any('on_take_profit' in x or 'on_stop_loss' in x for x in calls))
    check('reference_close_calls_new_callback','self.on_close_position(order, closed_trade)' in ast.unparse(funcs['_on_close_position']))
    check('reference_spot_rejects_short','should_short cannot be True if the exchange type is "spot".' in strategy)
    check('reference_spot_rejects_brackets_in_go_long','Setting self.take_profit in the go_long() method is not supported for spot trading' in strategy and 'Setting self.stop_loss in the go_long() method is not supported for spot trading' in strategy)
    check('reference_filters_after_go_long',ast.unparse(funcs['_execute_long']).index('self.go_long()')<ast.unparse(funcs['_execute_long']).index('self._execute_filters()'))
    check('reference_reset_not_turtle_custom_fields','current_pyramiding_levels' not in ast.unparse(funcs['_reset']))
    ich=(evidence/'jesse-reference/jesse/indicators/ichimoku_cloud.py').read_text()
    rust=(evidence/'jesse-rust-reference/src/trend.rs').read_text()
    check('reference_cloud_python_80_guard','candles.shape[0] < 80' in ich and 'candles[-80:]' in ich)
    check('reference_cloud_rust_displacement_minus1','..-((displacement as isize) - 1)' in rust)
    check('reference_rust_dependency_pin','jesse-rust==1.3.0' in (evidence/'jesse-reference/requirements.txt').read_text())
    check('reference_rust_cargo_version','version = "1.3.0"' in (evidence/'jesse-rust-reference/Cargo.toml').read_text())
    return {'source_fingerprints':output,'checks':common,'source_check_count':len(common),'passed':all(x['pass'] for x in common)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence-root',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--ids',nargs='+',choices=IDS,default=list(IDS));p.add_argument('--synthetic-only',action='store_true')
    args=p.parse_args()
    results=synthetic(); selected=[x for x in results if x['id'] in args.ids]
    report={'schema':'public-source-rule-audit/offline-v1','stage':'SOURCE_RULE_DEDUP_AUDIT_ONLY','third_party_code_executed':False,'market_data_requests':0,'historical_runs':0,'native_engine_runs':0,'synthetic_case_count':len(selected),'cases':selected,'pass':all(x['pass'] for x in selected),'limitation':'Self-authored mathematical/branch fixtures. Not native indicator equality, an original-runtime reproduction, or full execution-engine validation.'}
    if not args.synthetic_only:
        if not args.evidence_root:p.error('--evidence-root required unless --synthetic-only')
        report['source_audit']=source_checks(args.evidence_root)
    dump(args.out,report)
    print(json.dumps({'pass':report['pass'],'synthetic_cases':len(selected),'source_checks':report.get('source_audit',{}).get('source_check_count',0),'historical_runs':0,'native_engine_runs':0,'output':str(args.out)}))
if __name__=='__main__':main()
