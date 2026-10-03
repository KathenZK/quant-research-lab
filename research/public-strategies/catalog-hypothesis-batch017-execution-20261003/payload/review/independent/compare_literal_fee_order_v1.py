"""Audit the retained synthetic wrapper outputs using the literal frozen sell order."""
import csv,json,hashlib
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p):
    with p.open(newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    mismatch=[];counts={'fill_decimal_fields':0,'nav_decimal_fields':0,'representation_only_mismatches':0,'numerical_mismatches':0};per=[]
    with localcontext() as c:
        c.prec=50;c.rounding=ROUND_HALF_EVEN
        for sid in ['M1346','M1270']:
            cases=json.loads((ROOT/f'frozen/{sid}-root-frozen-rules.json').read_text())['cost_cases'];out=ROOT/f'review/independent/synthetic-wrapper-v1/{sid}/replica1'
            for case in cases:
                name=case['name'];cash=D(100000);qty=D(0);fees=[];case_representations=0;fills=read(out/f'{name}-fills.csv');nav=read(out/f'{name}-nav.csv')
                def compare(field,actual,expected,index,kind):
                    nonlocal case_representations
                    assert D(actual)==D(expected),(sid,name,index,field,actual,expected)
                    if actual!=expected:
                        counts['representation_only_mismatches']+=1;case_representations+=1
                        if len(mismatch)<12:mismatch.append(dict(id=sid,case=name,eval_index=index,field=field,kernel=actual,literal=expected,numerically_equal=True,kind=kind))
                for j,n in enumerate(nav):
                    for f in (x for x in fills if int(x['eval_index'])==j):
                        cb,qb=cash,qty;fee=D(case['fee_bps_each_side']);slip=D(case['slippage_bps_each_side'])
                        if f['side']=='BUY':
                            price=D(f['raw_open'])*(1+slip/10000);principal=cash/(1+fee/10000);commission=cash-principal;qty=principal/price;cash=D(0)
                        else:
                            price=D(f['raw_open'])*(1-slip/10000);principal=qty*price;commission=principal*fee/10000;cash=cash+principal-commission;qty=D(0)
                        for k,v in dict(fill_price=price,notional=principal,fee=commission,cash_before=cb,quantity_before=qb,cash_after=cash,quantity_after=qty).items():compare(k,f[k],str(v),j,'fill');counts['fill_decimal_fields']+=1
                        fees.append(commission)
                    for k,v in dict(cash=cash,quantity=qty,equity=cash+qty*D(n['raw_close'])).items():compare(k,n[k],str(v),j,'nav');counts['nav_decimal_fields']+=1
                summary=json.loads((out/f'{name}-summary.json').read_text());compare('total_fees',summary['total_fees'],str(sum(fees,D(0))),None,'summary')
                per.append(dict(id=sid,case=name,representation_only_differences=case_representations,numerical_differences=0))
    result=dict(schema='batch017-literal-fee-order-difference-audit/v1',status='REPRESENTATION_ONLY_CONFIRMED_NOT_GATE_RELEASE',counts=counts,cases=per,examples=mismatch,historical_strategy_runs=0,new_controls=0,script_sha256=sha(Path(__file__)),scope='Full previously generated invented 731-day synthetic wrapper outputs for all eight compatible cases; no target kernel altered; literal raw*bps/10000 arithmetic independently reconstructed')
    p=ROOT/'review/independent/literal-fee-order-difference-v1.json'
    with p.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(result))
if __name__=='__main__':main()
