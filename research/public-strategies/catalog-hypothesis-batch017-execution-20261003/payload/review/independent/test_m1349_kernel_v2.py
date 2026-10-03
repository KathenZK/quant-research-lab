"""Independent M1349 synthetic lifecycle/account/causality tests, no history."""
import copy,hashlib,importlib.util,json,sys,unittest
from decimal import Decimal as D, localcontext, ROUND_HALF_EVEN
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_kernel_v2 as qa
kernel=qa.load('mandatory_exit_v2','kernel/v2/engine.py')
POLICY={'max_completed_closes':25}
COUNT={'synthetic_engine_calls':0,'lifecycle_rows':0,'prefix_checks':0,'future_checks':0}
def features(r):
    return qa.actual_features('M1349',r)
def audit_lifecycle(result):
    buys={f['eval_index']:f for f in result['fills'] if f['side']=='BUY'};sells={f['eval_index']:f for f in result['fills'] if f['side']=='SELL'};last_buy=None
    for j,(n,d) in enumerate(zip(result['nav'],result['decisions'])):
        assert not(j in buys and j in sells)
        if j in sells:last_buy=None
        if j in buys:last_buy=j
        held=j-last_buy+1 if last_buy is not None else 0
        trigger=last_buy+24 if held>=25 else ''
        assert n['held_completed_bars']==d['held_completed_bars']==held
        assert n['mandatory_exit_latched']==d['mandatory_exit_latched']==int(held>=25)
        assert n['mandatory_exit_trigger_index']==d['mandatory_exit_trigger_index']==trigger
        assert d['raw_exit']==0
        assert d['effective_exit']==int(held>=25)
        assert d['effective_entry']==(0 if held>=25 else d['raw_entry'])
        assert d['exit_reason']==('time25' if held>=25 else '')
        if held>=25:
            assert n['pending_side']=='SELL' and n['pending_signal_index']==trigger
            assert n['pending_due_index']==trigger+result['summary']['delay_bars']
        if j in buys:assert held==1
        if j in sells:assert held==0
        COUNT['lifecycle_rows']+=1
    assert result['summary']['terminal_held_completed_bars']==result['nav'][-1]['held_completed_bars']
    assert result['summary']['terminal_mandatory_exit_latched']==bool(result['nav'][-1]['mandatory_exit_latched'])
    assert result['summary']['terminal_mandatory_exit_trigger_index']==(None if result['nav'][-1]['mandatory_exit_trigger_index']=='' else result['nav'][-1]['mandatory_exit_trigger_index'])
    for t in result['roundtrips']:assert t['holding_bars']==24+result['summary']['delay_bars']

def run(r,case):
    result=kernel.simulate(r,features(r),case,execution_policy=POLICY);COUNT['synthetic_engine_calls']+=1
    qa.audit_account(result,r,case,31);audit_lifecycle(result);return result

def persistent(n=130):
    r=qa.rows(n)
    with localcontext() as c:
        c.prec=50;c.rounding=ROUND_HALF_EVEN
        for i,b in enumerate(r):b['close']=str(D(100)*(D('0.99')**i));b['low']=str(D(b['close'])/2)
    return r

class Checks(unittest.TestCase):
    def test_01_exact_v2_and_v1_pins(self):
        manifest=json.loads((ROOT/'kernel/v2/manifest.json').read_text())
        self.assertEqual(hashlib.sha256((ROOT/'kernel/v2/engine.py').read_bytes()).hexdigest(),'2b3354dc5c210c66749c5b1e595831abb2adc3f6fff6b9b5f06d22e9fcb39219')
        for f in manifest['files']:
            p=ROOT/'kernel/v2'/f['path'];self.assertEqual(p.stat().st_size,f['bytes']);self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),f['sha256'])
        for name,expected in manifest['unchanged_v1'].items():self.assertEqual(hashlib.sha256((ROOT/'kernel/v1'/name).read_bytes()).hexdigest(),expected)
    def test_02_equal_constant_all_cases(self):
        r=qa.rows()
        for case in qa.CASES:
            a=run(r,case);self.assertEqual(a['fills'],[]);self.assertEqual(len(a['nav']),731);self.assertEqual(len(a['monthly']),24);self.assertTrue(all(D(n['equity'])==100000 for n in a['nav']))
    def test_03_persistent_oversold_exit_all_cases(self):
        r=persistent()
        for case in qa.CASES:
            a=run(r,case);lag=case['delay_bars'];e=lag;trigger=e+24;sale=trigger+lag
            self.assertEqual(a['fills'][0]['eval_index'],e);self.assertEqual(a['fills'][1]['eval_index'],sale)
            self.assertEqual(a['nav'][e]['held_completed_bars'],1);self.assertEqual(a['nav'][trigger]['held_completed_bars'],25)
            self.assertTrue(a['decisions'][trigger]['raw_entry']);self.assertEqual(a['decisions'][trigger]['effective_entry'],0)
            self.assertEqual(a['nav'][trigger]['pending_signal_index'],trigger);self.assertEqual(a['nav'][trigger]['pending_due_index'],sale)
            self.assertEqual(a['summary']['cancelled_intents'],0)
            if lag==2:
                self.assertEqual(a['nav'][trigger+1]['held_completed_bars'],26);self.assertEqual(a['nav'][trigger+1]['pending_signal_index'],trigger);self.assertEqual(a['nav'][trigger+1]['pending_due_index'],sale)
            self.assertEqual(a['nav'][sale]['held_completed_bars'],0);self.assertEqual(a['nav'][sale]['mandatory_exit_latched'],0)
            self.assertGreater(a['fills'][2]['eval_index'],sale)
    def test_04_recovery_retains_pending_buy_no_early_exit(self):
        r=qa.rows(95);r[31]['close']='80'
        for case in qa.CASES:
            a=run(r,case);lag=case['delay_bars']
            self.assertEqual([(f['side'],f['eval_index']) for f in a['fills']],[('BUY',lag),('SELL',lag+24+lag)])
            self.assertEqual(a['summary']['cancelled_intents'],0)
            self.assertFalse(a['decisions'][1]['raw_entry'] or a['decisions'][1]['raw_exit'])
    def test_05_terminal_exit_pending_latched(self):
        for case in qa.CASES:
            lag=case['delay_bars'];e=lag;trigger=e+24;sale=trigger+lag
            for end in range(trigger+1,sale+1):
                a=run(persistent(31+end),case);self.assertEqual(len(a['fills']),1);self.assertEqual(a['summary']['terminal_pending'],dict(side='SELL',signal_index=trigger,due_index=sale));self.assertTrue(a['summary']['terminal_mandatory_exit_latched']);self.assertEqual(a['summary']['terminal_held_completed_bars'],end-e)
                self.assertGreater(D(a['summary']['final_quantity']),0);self.assertEqual(D(a['summary']['final_cash']),0)
    def test_06_threshold_level_and_no_warmup(self):
        r=qa.rows(62)
        for i in range(25,31):r[i]['close']='80'
        a=run(r,qa.CASES[0]);self.assertEqual(a['fills'],[])
        for value,expected in [('90',False),('89.9999999999999999999999999999999999999999',True),('90.0000000000000000000000000000000000000001',False)]:
            r=qa.rows(80);r[31]['close']=value;a=run(r,qa.CASES[0]);self.assertEqual(bool(a['decisions'][0]['raw_entry']),expected)
    def test_07_lifecycle_rejects_corruption(self):
        a=run(persistent(),qa.CASES[3]);bad=copy.deepcopy(a);bad['nav'][2]['held_completed_bars']=0
        with self.assertRaises(AssertionError):audit_lifecycle(bad)
    def test_08_prefix_future_and_determinism(self):
        r=persistent(135)
        for case in qa.CASES:
            full=run(r,case);again=run(copy.deepcopy(r),case);self.assertEqual(json.dumps(full,sort_keys=True),json.dumps(again,sort_keys=True))
            for cut in [33,56,57,58,59,60,89,134]:
                limit=cut-31;a=run(r[:cut],case)
                for key in ['nav','decisions']:self.assertEqual(a[key],full[key][:limit])
                for key in ['fills','pending']:self.assertEqual(a[key],[x for x in full[key] if x['eval_index']<limit])
                self.assertEqual(a['roundtrips'],[x for x in full['roundtrips'] if x['exit_index']<limit]);COUNT['prefix_checks']+=1
                future=copy.deepcopy(r)
                for b in future[cut:]:b.update(open='999999',high='9999999',low='0.001',close='999888')
                a=run(future,case)
                for key in ['nav','decisions']:self.assertEqual(a[key][:limit],full[key][:limit])
                for key in ['fills','pending']:self.assertEqual([x for x in a[key] if x['eval_index']<limit],[x for x in full[key] if x['eval_index']<limit])
                COUNT['future_checks']+=1
    def test_09_raw_feature_future_independent(self):
        r=persistent(130);f=qa.own_flags('M1349',r)
        for i,x in enumerate(features(r)):self.assertEqual((x['raw_entry'],x['raw_exit']),(f[i]['raw_entry'],0))
    def test_10_policy_schema_and_fields(self):
        self.assertEqual(kernel.output_columns('nav',POLICY),kernel.NAV+kernel.POLICY_NAV)
        self.assertEqual(kernel.output_columns('decisions',POLICY),kernel.DEC+kernel.POLICY_DEC)
        for bad in [True,{'max_completed_closes':True},{'max_completed_closes':0},{'max_completed_closes':25,'extra':1}]:
            with self.assertRaises(ValueError):kernel.policy_limit(bad)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    report=dict(schema='M1349-independent-kernel-v2-synthetic/v1',status='PASS' if result.wasSuccessful() else 'FAIL',tests_run=result.testsRun,counts=COUNT,account_counts=qa.COUNTS,errors=[(str(a),b) for a,b in result.errors],failures=[(str(a),b) for a,b in result.failures],historical_strategy_runs=0,new_controls=0,policy=POLICY,source_signal='independent Decimal50 ROC25 level strictly below -0.10; raw_exit zero; actual kernel owns lifecycle',pins={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'kernel/v2/engine.py',ROOT/'kernel/v2/verify_account.py',ROOT/'kernel/v2/manifest.json',ROOT/'source/daily_three_signals.py',Path(__file__)]})
    dest=ROOT/'review/independent/M1349-synthetic-kernel-v2-v1.json'
    with dest.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(report));raise SystemExit(not result.wasSuccessful())
