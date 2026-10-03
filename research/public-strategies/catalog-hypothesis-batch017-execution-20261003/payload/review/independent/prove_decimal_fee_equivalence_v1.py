"""Synthetic exact Decimal50 numerical audit; no target engine or historical data."""
from decimal import Decimal as D, localcontext, ROUND_HALF_EVEN
from pathlib import Path
import hashlib,json,random
ROOT=Path(__file__).resolve().parents[2]
def main():
    rng=random.Random(1701346)
    coefficient=['0','1','5','9','10','25','99','100','1'+'0'*49,'9'*50,'5'*50,'1'+'0'*47+'25','9'*48+'95','1'+'0'*47+'05','8'*49+'5','2'+'5'*49]
    coefficient += [''.join([str(rng.randint(1,9))]+[str(rng.randint(0,9)) for _ in range(49)]) for _ in range(200)]
    powers=[-500,-100,-50,-20,-10,-4,-3,-2,-1,0,1,2,3,4,10,20,50,100,500]
    counts={str(b):dict(comparisons=0,lexical_differences=0,numerical_differences=0) for b in [0,8,20]};examples=[]
    with localcontext() as c:
        c.prec=50;c.rounding=ROUND_HALF_EVEN
        for digits in coefficient:
            for exponent in powers:
                notional=D(digits).scaleb(exponent)
                for bps in [0,8,20]:
                    literal=notional*D(bps)/D(10000)
                    factor_first=notional*(D(bps)/D(10000))
                    assert literal.is_finite() and factor_first.is_finite()
                    assert literal==factor_first,(notional,bps,literal,factor_first)
                    q=counts[str(bps)];q['comparisons']+=1
                    if str(literal)!=str(factor_first):
                        q['lexical_differences']+=1
                        if len(examples)<6:examples.append(dict(notional=str(notional),bps=bps,literal=str(literal),factor_first=str(factor_first)))
    result=dict(schema='batch017-independent-Decimal50-fee-equivalence/v1',status='PASS_EXACT_NUMERIC_ZERO_ERROR',precision=50,rounding='ROUND_HALF_EVEN',per_fee_bps=counts,total_comparisons=sum(x['comparisons'] for x in counts.values()),synthetic_coefficient_count=len(coefficient),scale_exponents=powers,examples=examples,reason='For these frozen integer bps, the rate is an exact finite decimal. Under normal exponent bounds, multiplication then exact power-of-ten division and multiplication by the exact predivided rate have the same rounded 50-significant-digit numerical value. Decimal coefficient/exponent representation can retain different trailing zeros; neither operation quantizes. This bounded executable check includes 50-digit and halfway-shaped coefficients over scales -500 to +500; it is not a proof for Decimal overflow/subnormal arithmetic outside the research range.',contract_interpretation='No explicit requirement found that independent oracles with equivalent algebra must produce identical decimal text. Exact Decimal numerical equality is checked here; engine replay serialization remains separately byte-exact.',historical_strategy_runs=0,new_controls=0,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    p=ROOT/'review/independent/decimal-fee-equivalence-v1.json'
    with p.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(result))
if __name__=='__main__':main()
