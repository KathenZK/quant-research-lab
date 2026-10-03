"""Independent synthetic-only tests of exact coordinator v1 and daily adapters.
No file below input/ is opened and no historical prices enter this program.
"""
import copy, datetime as dt, hashlib, importlib.util, json, math, statistics, unittest
from decimal import Decimal as D, localcontext, ROUND_HALF_EVEN
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
engine=load('target_engine','kernel/v1/engine.py');signals=load('target_signals','source/daily_three_signals.py')
CASES=json.loads((ROOT/'frozen/M1346-root-frozen-rules.json').read_text())['cost_cases']
COUNTS={'simulations':0,'nav_rows_audited':0,'fills_audited':0,'prefix_comparisons':0,'future_comparisons':0,'signal_rows_compared':0}
def rows(n=762,start='2022-12-01'):
    stamp=int(dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc).timestamp())*1000
    return [dict(open_time=str(stamp+i*86400000),open='100',high='200',low='1',close='100',volume='1',close_time=str(stamp+(i+1)*86400000-1),quote_volume='100',trade_count='1',taker_base='0.5',taker_quote='50',ignore='0') for i in range(n)]
def own_flags(sid,r):
    result=[]
    with localcontext() as c:
        c.prec=50;c.rounding=ROUND_HALF_EVEN
        for i,row in enumerate(r):
            stamp=dt.datetime.fromtimestamp(int(row['open_time'])/1000,dt.timezone.utc)
            close=D(row['close']);lag=D(r[i-25]['close']) if i>=25 and sid!='M1270' else None
            ready=(sid=='M1270' or i>=25);roc=close/lag-1 if lag is not None and sid=='M1349' else None
            entry=(close>lag if sid=='M1346' and ready else roc<D('-0.10') if sid=='M1349' and ready else stamp.weekday()==6 if sid=='M1270' else False)
            exit_=(close<lag if sid=='M1346' and ready else stamp.weekday()==0 if sid=='M1270' else False)
            result.append(dict(raw_entry=int(entry),raw_exit=int(exit_),ready=ready,roc25=roc))
    return result

def actual_features(sid,r):
    own=own_flags(sid,r);feat=signals.build_features(sid,r)
    for i,(a,b) in enumerate(zip(feat,own)):
        assert (a['raw_entry'],a['price_or_calendar_exit'],a['ready'],a['roc25'])==(bool(b['raw_entry']),bool(b['raw_exit']),b['ready'],b['roc25']),(sid,i)
        assert a['signal_available_ms']==int(r[i]['open_time'])+86400000
    COUNTS['signal_rows_compared']+=len(r)
    return [dict(raw_entry=int(f['raw_entry']),raw_exit=int(f['price_or_calendar_exit'])) for f in feat]

def run(sid,r,case,start=31):
    assert sid in ['M1346','M1270'],'M1349 execution not authorized against v1'
    result=engine.simulate(r,actual_features(sid,r),case,start=start);COUNTS['simulations']+=1
    audit_account(result,r,case,start)
    return result

def audit_account(result,r,case,start):
    """Reconcile persisted fills and NAV; never generate signals, orders or queues."""
    fills=result['fills'];nav=result['nav'];summary=result['summary'];cash=D(100000);qty=D(0);commissions=[];entry=None;closed=[];fpos=0
    with localcontext() as c:
        c.prec=50;c.rounding=ROUND_HALF_EVEN
        for j,bar in enumerate(r[start:]):
            matching=[f for f in fills if f['eval_index']==j];assert len(matching)<=1
            for f in matching:
                assert f['fill_id']==fpos;fpos+=1
                assert f['input_index']==start+j and f['phase']=='OPEN'
                assert f['due_index']==f['signal_index']+case['delay_bars'] and f['due_index']<=j
                assert f['signal_index']<j and f['effective_time']==engine.iso(int(bar['open_time']))
                cb,qb=cash,qty;raw=D(bar['open']);fee=D(case['fee_bps_each_side']);slip=D(case['slippage_bps_each_side'])
                if f['side']=='BUY':
                    assert qty==0 and cash>0
                    price=raw*(1+slip/10000);principal=cash/(1+fee/10000);commission=cash-principal;qty=principal/price;cash=D(0);entry=(j,cb)
                else:
                    assert f['side']=='SELL' and qty>0 and entry
                    price=raw*(1-slip/10000);principal=qty*price;commission=principal*(fee/10000);cash=cash+principal-commission;qty=D(0);closed.append((entry[0],j,cash-entry[1],cash/entry[1]-1));entry=None
                for k,value in dict(raw_open=bar['open'],fill_price=str(price),notional=str(principal),fee=str(commission),cash_before=str(cb),quantity_before=str(qb),cash_after=str(cash),quantity_after=str(qty)).items():assert f[k]==value,(k,f[k],value)
                commissions.append(commission);assert cash>=0 and qty>=0;COUNTS['fills_audited']+=1
            n=nav[j];assert n['input_index']==start+j and n['eval_index']==j
            assert n['cash']==str(cash) and n['quantity']==str(qty) and n['raw_close']==bar['close'] and n['equity']==str(cash+qty*D(bar['close']))
            assert n['mark_time']==engine.iso(int(bar['open_time'])+86400000);COUNTS['nav_rows_audited']+=1
        assert fpos==len(fills) and len(nav)==len(r)-start
        assert summary['total_fees']==str(sum(commissions,D(0))) and summary['final_cash']==str(cash) and summary['final_quantity']==str(qty)
        assert summary['closed_roundtrips']==len(closed)
        for a,b in zip(result['roundtrips'],closed):
            assert (a['entry_index'],a['exit_index'],D(a['net_pnl']),D(a['net_return']))==b
            assert a['holding_bars']==b[1]-b[0]
        assert summary['win_rate']==(sum(x[2]>0 for x in closed)/len(closed) if closed else None)
        assert summary['exposure_fraction']==sum(D(n['quantity'])>0 for n in nav)/len(nav)
        groups={}
        for n in nav:groups.setdefault(n['open_time'][:7],[]).append(n)
        previous=D(100000)
        assert len(result['monthly'])==len(groups)
        for m,(month,g) in zip(result['monthly'],groups.items()):
            assert m['month']==month and m['days']==len(g) and m['days_long']==sum(D(n['quantity'])>0 for n in g)
            assert m['end_equity']==g[-1]['equity'] and m['return']==str(D(g[-1]['equity'])/previous-1)
            mf=[f for f in fills if f['effective_time'].startswith(month)]
            assert m['buy_fills']==sum(f['side']=='BUY' for f in mf) and m['sell_fills']==sum(f['side']=='SELL' for f in mf)
            previous=D(g[-1]['equity'])
    values=[float(n['equity']) for n in nav];ret=[v/p-1 for p,v in zip([100000.]+values[:-1],values)];peak=100000.;dd=0.
    for v in values:peak=max(peak,v);dd=min(dd,v/peak-1)
    sd=statistics.stdev(ret) if len(ret)>1 else 0
    expected=dict(total_return=values[-1]/100000.-1,cagr=(values[-1]/100000.)**(365/len(values))-1,max_drawdown=dd,sharpe_zero_cash=statistics.mean(ret)/sd*math.sqrt(365) if sd>0 else None,final_equity=values[-1])
    for k,v in expected.items():
        if v is None:assert summary[k] is None
        elif v==0:assert summary[k]==0
        else:assert math.isclose(summary[k],v,rel_tol=1e-12,abs_tol=0),(k,summary[k],v)

class IndependentTests(unittest.TestCase):
    def test_01_target_pins(self):
        manifest=json.loads((ROOT/'kernel/v1/manifest.json').read_text())
        for name,sha in manifest['files'].items():self.assertEqual(hashlib.sha256((ROOT/'kernel/v1'/name).read_bytes()).hexdigest(),sha)
        self.assertEqual(manifest['files']['engine.py'],'5b92fea2db2a5da7c4ecd90356adaf8cb533dcedd7378992d2b8e8e324d43782')
    def test_02_manual_decimal_vectors(self):
        vectors=json.loads((ROOT/'review/independent/manual-account-vectors-v1.json').read_text())['vectors']
        with localcontext() as c:
            c.prec=50;c.rounding=ROUND_HALF_EVEN
            for case,expected in zip(CASES,vectors):
                cash,qty,b=engine.fill_order(D(100000),D(0),'100','BUY',case['fee_bps_each_side'],2)
                for k,v in [('fill_price','buy_fill'),('notional','buy_notional'),('fee','buy_fee'),('quantity_after','quantity'),('cash_after','cash_after_buy')]:self.assertEqual(b[k],expected[v])
                self.assertEqual(str(qty*D(105)),expected['close_equity_at_105'])
                cash,qty,s=engine.fill_order(cash,qty,'110','SELL',case['fee_bps_each_side'],2)
                for k,v in [('fill_price','sell_fill'),('notional','sell_notional'),('fee','sell_fee'),('cash_after','cash_after_sell')]:self.assertEqual(s[k],expected[v])
                self.assertEqual(qty,0)
    def test_03_constant_momentum_all_cases(self):
        r=rows()
        for case in CASES:
            x=run('M1346',r,case)
            self.assertEqual(len(x['nav']),731);self.assertEqual(len(x['monthly']),24);self.assertEqual(x['fills'],[])
            self.assertTrue(all(D(n['equity'])==100000 for n in x['nav']))
            self.assertEqual(x['summary']['exposure_fraction'],0);self.assertIsNone(x['summary']['sharpe_zero_cash']);self.assertIsNone(x['summary']['win_rate'])
    def test_04_boundary_and_ready_all_signals(self):
        r=rows(80)
        for sid in ['M1346','M1349']:
            f=actual_features(sid,r);self.assertTrue(all(not x['raw_entry'] and not x['raw_exit'] for x in f))
        for value,entry,exit_ in [('100',False,False),('100.0000000000000000000000000000000000000001',True,False),('99.9999999999999999999999999999999999999999',False,True)]:
            r[25]['close']=value;f=actual_features('M1346',r);self.assertEqual((f[25]['raw_entry'],f[25]['raw_exit']),(entry,exit_))
        for value,entry in [('90',False),('90.0000000000000000000000000000000000000001',False),('89.9999999999999999999999999999999999999999',True)]:
            r[25]['close']=value;f=actual_features('M1349',r);self.assertEqual(f[25]['raw_entry'],entry)
    def test_05_flat_pending_cancel_before_gating(self):
        r=rows(42);r[31]['close']='101';r[32]['close']='99'
        x=run('M1346',r,CASES[3]);self.assertEqual(x['fills'],[])
        cancel=[e for e in x['pending'] if e['event']=='CANCELLED_OPPOSITE'];self.assertEqual([(e['eval_index'],e['side'],e['held']) for e in cancel],[(1,'BUY',0)])
    def test_06_equal_neutral_and_repeated_due(self):
        for second in ['100','102']:
            r=rows(42);r[31]['close']='101';r[32]['close']=second;r[34]['close']='99'
            x=run('M1346',r,CASES[3]);self.assertEqual([(f['side'],f['eval_index'],f['signal_index'],f['due_index']) for f in x['fills']],[('BUY',2,0,2),('SELL',5,3,5)])
    def test_07_pending_sell_cancel_while_long(self):
        r=rows(42);r[31]['close']='101';r[34]['close']='99';r[35]['close']='101'
        x=run('M1346',r,CASES[3]);self.assertEqual([f['side'] for f in x['fills']],['BUY']);self.assertGreater(D(x['summary']['final_quantity']),0)
        cancel=[e for e in x['pending'] if e['event']=='CANCELLED_OPPOSITE'];self.assertEqual([(e['side'],e['eval_index'],e['held']) for e in cancel],[('SELL',4,1)])
    def test_08_exit_priority_simultaneous(self):
        pending={'side':'BUY','signal_index':0,'due_index':2}
        p,events=engine.reconcile(pending,True,True,False,1,2);self.assertIsNone(p);self.assertEqual(events[0]['event'],'CANCELLED_OPPOSITE')
        pending={'side':'SELL','signal_index':0,'due_index':2}
        p,events=engine.reconcile(pending,True,True,True,1,2);self.assertEqual(p,pending);self.assertEqual(events[0]['event'],'RETAINED_EARLIEST')
    def test_09_no_warmup_orders_or_terminal_sale(self):
        r=rows(35)
        for i in range(25,35):r[i]['close']='101'
        x=run('M1346',r,CASES[0]);self.assertEqual(x['fills'][0]['eval_index'],1);self.assertEqual(len(x['fills']),1);self.assertGreater(D(x['summary']['final_quantity']),0)
        r=rows(34);r[-1]['close']='101';x=run('M1346',r,CASES[3]);self.assertEqual(x['fills'],[]);self.assertEqual(x['summary']['terminal_pending'],{'side':'BUY','signal_index':2,'due_index':4})
    def test_10_calendar_731_all_cases(self):
        r=rows()
        for case in CASES:
            x=run('M1270',r,case);self.assertEqual(len(x['monthly']),24)
            if case['name']=='delay2':
                self.assertEqual(x['fills'],[]);self.assertEqual(x['summary']['cancelled_intents'],105);self.assertEqual(x['summary']['queued_intents'],105)
                self.assertEqual(x['summary']['exposure_fraction'],0);self.assertEqual(x['summary']['final_equity'],100000);self.assertTrue(all(m['buy_fills']==m['sell_fills']==m['days_long']==0 and D(m['return'])==0 for m in x['monthly']))
            else:
                self.assertEqual(len(x['fills']),210);self.assertEqual(len(x['roundtrips']),105);self.assertEqual(sum(m['days_long'] for m in x['monthly']),105)
                self.assertEqual(x['summary']['exposure_fraction'],105/731)
                for f in x['fills']:
                    weekday=dt.datetime.fromtimestamp(int(r[f['input_index']]['open_time'])/1000,dt.timezone.utc).weekday();self.assertEqual(weekday,0 if f['side']=='BUY' else 1)
                self.assertEqual(x['fills'][0]['effective_time'],'2023-01-02T00:00:00Z');self.assertEqual(x['fills'][-1]['effective_time'],'2024-12-31T00:00:00Z')
    def test_11_calendar_year_month_leap_boundaries(self):
        r=rows(100,start='2023-11-30');x=run('M1270',r,CASES[0]);self.assertEqual(x['decisions'][0]['raw_entry'],1)
        self.assertEqual(x['fills'][0]['effective_time'],'2024-01-01T00:00:00Z');self.assertEqual(x['monthly'][0]['month'],'2023-12');self.assertEqual(x['monthly'][0]['buy_fills'],0)
        leap=next(n for n in x['nav'] if n['open_time'].startswith('2024-02-29'));self.assertEqual(D(leap['quantity']),0)
    def test_12_prefix_future_and_determinism(self):
        r=rows(180)
        for i,bar in enumerate(r):bar['open']=str(95+(i*7)%70);bar['close']=str(80+(i*13)%90)
        for sid in ['M1346','M1270']:
            for case in CASES:
                full=run(sid,r,case)
                again=run(sid,copy.deepcopy(r),case);self.assertEqual(json.dumps(full,sort_keys=True),json.dumps(again,sort_keys=True))
                for cut in [34,56,62,91,124,179]:
                    prefix=run(sid,r[:cut],case);limit=cut-31
                    for key in ['nav','decisions']:self.assertEqual(prefix[key],full[key][:limit])
                    for key in ['fills','pending']:self.assertEqual(prefix[key],[v for v in full[key] if v['eval_index']<limit])
                    COUNTS['prefix_comparisons']+=1
                    future=copy.deepcopy(r)
                    for bar in future[cut:]:bar.update(open='999999',high='99999999',low='0.01',close='999888',volume='234')
                    changed=run(sid,future,case)
                    for key in ['nav','decisions']:self.assertEqual(changed[key][:limit],full[key][:limit])
                    for key in ['fills','pending']:self.assertEqual([v for v in changed[key] if v['eval_index']<limit],[v for v in full[key] if v['eval_index']<limit])
                    COUNTS['future_comparisons']+=1
    def test_13_open_fill_cannot_see_current_close(self):
        r=rows(80);r[31]['close']='101';changed=copy.deepcopy(r);changed[32].update(high='99999',low='0.01',close='250')
        a=run('M1346',r,CASES[0]);b=run('M1346',changed,CASES[0]);self.assertEqual(a['fills'][0],b['fills'][0]);self.assertNotEqual(a['nav'][1]['equity'],b['nav'][1]['equity'])
    def test_14_M1349_signal_only_counter_latch(self):
        r=rows(80);r[50]['close']='80'
        for held in [0,1,24,25,26,30]:
            f=signals.events_at_close('M1349',r,50,held_completed_bars=held);self.assertTrue(f['raw_entry']);self.assertEqual(f['raw_exit'],held>=25)
        f=signals.events_at_close('M1349',r,50,held_completed_bars=26,mandatory_exit_latched=True);self.assertTrue(f['mandatory_exit'] and f['raw_exit']);self.assertEqual(f['exit_reason'],'time25')
        r[50]['close']='120';f=signals.events_at_close('M1349',r,50,held_completed_bars=24);self.assertFalse(f['raw_entry'] or f['raw_exit'])
        self.assertTrue(signals.events_at_close('M1349',r,50,held_completed_bars=26,mandatory_exit_latched=True)['raw_exit'])
        for cut in [1,25,26,31,50,79]:
            self.assertEqual(signals.build_features('M1349',r[:cut]),signals.build_features('M1349',r)[:cut]);COUNTS['prefix_comparisons']+=1
            future=copy.deepcopy(r)
            for b in future[cut:]:b['close']='99999999'
            self.assertEqual(signals.build_features('M1349',future)[:cut],signals.build_features('M1349',r)[:cut]);COUNTS['future_comparisons']+=1

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(IndependentTests);result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'schema':'batch017-independent-synthetic-v2','status':'PASS' if result.wasSuccessful() else 'FAIL','tests_run':result.testsRun,'errors':[(str(a),b) for a,b in result.errors],'failures':[(str(a),b) for a,b in result.failures],'counts':COUNTS,'scope':'M1346/M1270 engine v1 full synthetic QA; M1349 feature/event boundaries only; literal frozen sell-fee serialization reconciliation pending','historical_strategy_runs':0,'new_controls':0,'evidence_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['kernel/v1/engine.py','kernel/v1/manifest.json','source/daily_three_signals.py','review/independent/test_kernel_v2.py']}}
    dest=ROOT/'review/independent/synthetic-independent-v2.json'
    with dest.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(report));raise SystemExit(not result.wasSuccessful())
