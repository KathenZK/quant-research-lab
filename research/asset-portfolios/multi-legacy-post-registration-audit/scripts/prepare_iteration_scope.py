"""Record comparable families and concrete reasons for unpaired versions."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[4]
FAMILY=Path(__file__).resolve().parents[1]
OUT=FAMILY/'artifacts/iteration_comparison_20260911'

def main():
    rows=[]
    for group,families in {
        'ema':['HYPE-EMA-X','HYPE-EMA-TB','HYPE-15M-MII','HYPE-15M-TB-MII-ENS'],
        'cc':['HYPE-CC'],
        'ar_mmtf':[f'{a}-1H-AR' for a in ['BTC','ETH','SOL','BNB','TRX','HYPE']]+['HYPE-15M-MMTF','HYPE-1H-MMTF','HYPE-30M-Keltner'],
    }.items():
        rows += [{'family':family,'group':group,'status':'PLANNED_VERSION_COMPARISON'} for family in families]
    rows += [
        {'family':'HYPE-15M-MDTP','status':'NO_EARLIER_REGISTERED_PAIR','version':'V1',
         'reason':'主表只有首个登记V1；之后的campaign successor是不同研究机制，不制造一个未曾冻结的简单版。',
         'evidence':'research/hype/15m-multidimensional-trend-pyramiding/hype-15m-mdtp-core-ledger.md'},
        {'family':'Binance-1H-AR-MAE','status':'NO_EARLIER_REGISTERED_PAIR','version':'V1',
         'reason':'组合主表只有V1；本轮改为分别比较六个原单币AR家族的V1和最终版本，不把组合拆成新策略当作早期版。',
         'evidence':'research/asset-portfolios/1h-adaptive-regime-multi-asset-ensemble/binance-1h-ar-mae-core-ledger.md'},
        {'family':'Binance-15M-AS6S','status':'EARLY_VERSION_CONFIGURATION_MISSING','earliest':'V1','latest':'V6',
         'reason':'V1文字规格只保留九条腿的名称和暴露，五条15m腿完整StrategyConfig内嵌于已删除的JSON。源冻结脚本依赖的选择JSON同样缺失，目标冻结文件没有Git历史。V6虽在上一轮从runner恢复，但不能用V6参数替代V1，也不重新搜索一个早期赢家。',
         'missing':['research/asset-portfolios/15m-asset-specific-six-strategy-selector/artifacts/'+n for n in ['binance_as6s_future_oos_freeze_2026-07-14.json','binance_hybrid_asset_specific_account_2026-07-14.json','binance_15m_as6s_reused_holdout_2026-07-14.json']],
         'evidence':'research/asset-portfolios/15m-asset-specific-six-strategy-selector/specs/binance-as6s-future-oos-freeze-2026-07-14.md'},
    ]
    for row in rows:
        if 'evidence' in row:
            p=ROOT/row['evidence']
            row['evidence_exists']=p.exists()
            if p.exists():row['evidence_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        for missing in row.get('missing',[]):
            assert not (ROOT/missing).exists(), f'Expected missing item now exists: {missing}'
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'scope.json').write_text(json.dumps({'scope':'上一轮16组主版本中的14个有版本演化家族，另检查AS6S早期恢复；不包括无唯一冻结版本的全部研究观察',
        'primary_start':'2026-07-23T00:00:00Z','end':'2026-09-05T15:00:00Z','rows':rows},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'families':len(rows),'planned_comparisons':14,'unpaired':3},ensure_ascii=False))

if __name__=='__main__':main()
