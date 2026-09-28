"""Self-contained Chinese applicability report from frozen audit tables."""
from pathlib import Path
import json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/applicability-20260908'
NAMES={'long':'原版多头','short':'只做空','both':'双向等待','reverse':'信号反手'}
F={'trend_aligned':'顺着MA60方向','momentum_aligned':'顺着过去30日涨跌','efficiency30':'高单边程度 对 低单边程度','chop30':'少穿越 对 多穿越','atr_pct':'低波动 对 高波动','liquidity30':'高成交额 对 低成交额'}
LEGS={'long_long':'原版多头','short_short':'只做空','both_long':'双向等待中的多单','both_short':'双向等待中的空单','reverse_long':'反手中的多单','reverse_short':'反手中的空单'}


def fmt(x,suffix='%',signed=True):
    return '—' if pd.isna(x) else (f'{x:+.2f}' if signed else f'{x:.2f}')+suffix


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows])


def build():
    x=json.loads((OUT/'analysis.json').read_text());source=json.loads((OUT/'feature-summary.json').read_text())
    d=pd.read_csv(OUT/'entry-feature-contrasts.csv');d.period=d.period.astype(str)
    a=pd.read_csv(OUT/'annual-asset-type-atlas.csv');p=pd.read_csv(OUT/'coin-year-persistence.csv')
    stability=pd.read_csv(OUT/'rule-stability.csv');types=pd.read_csv(OUT/'annual-type-stability.csv')
    liquidity=a.loc[a.variant.eq('short')&a.feature.eq('liquidity90')&a.group.eq('日成交额>=1000万美元')&a.year.ge(2021)]
    liqrows=[[int(r.year),int(r.n),fmt(r.median_return_pct),fmt(r.profitable_pct,signed=False),fmt(r.median_mdd_pct,signed=False),fmt(r.delta_vs_baseline_median_pp,' 个百分点'),int(r.bankrupt)] for r in liquidity.itertuples()]
    bull=a.loc[a.variant.eq('long')&a.feature.eq('trend_state')&a.group.eq('上涨且MA60上行')&a.year.ge(2024)]
    bullrows=[[int(r.year),int(r.n),fmt(r.median_return_pct),fmt(r.baseline_median_return_pct)] for r in bull.itertuples()]
    er=d.loc[d.scope.eq('raw')&d.leg.eq('short_short')&d.feature.eq('efficiency30')&d.period.isin(['all','2024','2025','2026'])]
    errows=[[r.period,int(r.a_trades),int(r.b_trades),fmt(r.a_mean_return_pct),fmt(r.b_mean_return_pct),fmt(r.effect_pp,' 个百分点'),f'[{r.ci_low:+.2f}, {r.ci_high:+.2f}]',int(r.a_bankruptcies),int(r.b_bankruptcies)] for r in er.itertuples()]
    persistence=[]
    for v in NAMES:
        for r in p.loc[p.variant.eq(v)&p.previous_year.ge(2021)].itertuples():
            persistence.append([NAMES[v],f'{r.previous_year}→{r.next_year}',int(r.pairs),f'{r.spearman_rho:+.3f}',f'{r.selected_next_complete}/{r.selected_total}',fmt(r.next_median_prior_top),fmt(r.next_median_others)])
    comparisons=[]
    for leg in LEGS:
        for key in F:
            g=d.loc[d.leg.eq(leg)&d.feature.eq(key)&d.scope.eq('raw')].set_index('period')
            s=stability.loc[stability.leg.eq(leg)&stability.feature.eq(key)].iloc[0]
            vals=[fmt(g.loc[y,'effect_pp'],' pp')+(' *' if not g.loc[y,'adequate'] else '') for y in ['2024','2025','2026']]
            comparisons.append([LEGS[leg],F[key],*vals,'通过相对关联检查' if s.robust_association_screen else '未通过','通过' if s.positive_log_profit_candidate else '未通过'])
    candidates=[]
    for _,r in types.loc[types.positive_median_all_three].iterrows():
        candidates.append([NAMES[r.variant],r['group'],*[fmt(r[f'{y}_median'])+f"（{r[f'{y}_n']:.0f}币）" for y in [2024,2025,2026]],'是' if r.above_unfiltered_median_all_three else '否'])
    text=f'''# MA7–ATR14 到底适合什么标的：币种与入场状态审计

2026-09-08；Binance USDT 永续、UTC 日线。状态：`explore / diagnostic-only / not promoted / not live-ready`。

## 结论先说

能总结条件性规律，但目前不能给出可靠的固定币种白名单。证据比“只要强势币就有效”更具体：**原多头依赖随后出现的大幅上涨；空头有一些跨年的相对优势线索；双向合并和反手仍没有稳定盈利的标的类型。** 少数币赚钱，不足以给整套策略认定“弱有效”。

本次新增审计中，六类特征 × 六个实际交易方向分支，共 36 项检查，只有 2 项通过预先规定的跨年相对关联检查：只做空和反手空单都在“前30日单边程度较低”时，相对高单边程度样本更好。但 **0 项同时满足三段审计年均正算术/对数收益条件**。这表示发现了一些“相对少亏/相对更好”的规律，未证明相应过滤后策略可稳定赚钱。

币种年度层面，最值得保留的候选是：**年初之前成交较活跃的币，用只做空版本**。2024、2025、2026 年收益中位数均为正，也均略高于同样具有完整前置数据的未筛选样本；但它在 2021、2023 年分别亏约 41%、36%，不是全天候优势。三个最近年度筛选增量仅约 0.48–2.01 个百分点，并不大。

## 可说与不可说的规律

| 标的/状态 | 本轮证据 | 可用程度 |
| --- | --- | --- |
| 后来大幅上涨的币 × 原多头 | ZEC/HYPE 等案例及上一轮涨幅分组支持，仍可能漏趋势 | 已知结果下的路径解释，不能提前选币 |
| 年初成交活跃 × 只做空 | 最近三段年度中位数为正且略优于未筛选；更早上涨年仍亏损 | 候选，需要另行验证执行后的增量 |
| 过去30日走势非常单边 × 空头入场 | 后续平均空单收益低于低单边程度组，三段年度同方向 | 相对不利的入场状态；不能推断必亏 |
| 年初价格在MA60上方且MA60上行 × 多头 | 最近三段都略优于未筛选，但2025、2026仍亏 | 更好不等于有效盈利 |
| 去年表现最好的币 | 多头名次几乎不持续；空头有较弱持续性且存在反例 | 不足以建立稳定币种名单 |
| 仅凭低波动、少穿越、近30日顺势 | 未形成满足本轮完整条件的稳定盈利筛选 | 不能写成已验证的规则 |

这些行不是经过回测的联合条件。不能把“成交活跃 + 下行阶段 + 某个ER阈值”自行拼在一起后宣称已经验证。

## 1. 成交活跃的币，空头表现有弱线索

定义在看结果前固定：每年开始前90天，每日 USDT 成交额的中位数至少 **1,000 万美元**。只用年初以前的数据，不拿当年的成交量定义组别。评价仍是原固定只做空策略的完整年度/YTD 回放，未改变任何交易。

{table(['目标年份','币数','收益中位数','盈利比例','最大回撤中位数','相对同前置数据未筛选样本','经济本金耗尽数'],liqrows)}

2026 仅到 9 月 4 日。未筛选基准也要求具备同样的前置历史；因此它不同于上一轮“全部完整年度币”的分母。低成交额一侧在2021只有14个币，2022没有样本，不能把这两年的组间差异当成有力证据。2024/2025/2026高成交额组为153/199/137币，对照组为20/43/276币。

高成交额组2026仍有一个经济本金耗尽的标的 H，已保留，未删除以提高结果。收益中位数 +3.13% 伴随回撤中位数32.44%，也未计资金费率，所以这个线索不足以给出可实盘交易的建议。“成交额”也不等同于市值、盘口深度或可承载资金量。

另有几组最近三个年度中位数为正，但并未每年都优于未筛选样本。完整保留，避免只展示一个好看的组：

{table(['版本','年初已知特征组','2024','2025','2026至9月4日','三年均优于未筛选'],candidates)}

## 2. 空头不是前期走势越单边越有效

ER30 定义为：过去30日收盘对数价格的净位移绝对值，除以这30日每天对数价格变化绝对值之和。越接近1，前期走势越单边；越接近0，前期往返越多。**它不包含上涨/下跌方向，也不表示波动小。**

入场信号收盘时分组：高ER ≥0.25；低ER <0.10。中间组不参与这组极端对照，但原交易全部保留。以下是只做空分支的自然退出交易，已扣每边手续费0.10%和滑点0.04%；用实际入场前状态，不含未来走势。

{table(['入场期间','高ER交易数','低ER交易数','高ER每笔平均','低ER每笔平均','高减低','差值95%探索区间','高ER本金耗尽','低ER本金耗尽'],errows)}

合并历史中，低ER组平均每笔 +1.47%，高ER组 −2.43%，差约3.90个百分点。按入场月份对齐后差异方向仍在，去除已经点名的九币、以及去除经济异常段和 USDC/PAXG/XAUT 的敏感性也同方向。反手版的空单有相似的相对关系；双向等待空单的合并区间仍跨零。

但不能把低ER写成已证明的盈利信号：低ER只做空在2024每笔均值仍为 −0.19%，而且2025/2026各保留一次本金耗尽。每个年度的差值区间都跨零，只有合并区间不跨零。年度方向一致加合并证据属于探索性相对关联，未经过全套多重检验或未见数据确认。

它提示“看到明显单边走势后再接空信号，未必更有利”。究竟是趋势成熟、反弹还是挤空导致，不能由这个无方向指标单独确认。低ER组也没有重新执行一套过滤后的交易策略；从原账本挑出交易的统计不能代替重新回放。

## 3. 提前看起来强势的币，多头只是相对好一些

年初上一根收盘高于MA60，且MA60高于20日前的MA60，属于“上涨且MA60上行”组。这个条件已知于目标年开始前。

{table(['目标年份','币数','强势组原多头收益中位数','同前置历史未筛选中位数'],bullrows)}

2025强势组中位数 −55.17%，虽然比未筛选的 −59.58% 少亏，却远不能称为有效。2026同样如此。只取年初过去30天上涨的币，也出现类似情况：2025、2026收益中位数仍分别为 −48.54%、−10.07%。

这与ZEC/HYPE后来赚钱并不矛盾：事后大涨分组与入场前能识别的强势状态是不同问题。本轮没有发现可据此指定“永远适合原多头”的币种属性。

## 4. 去年赚钱的币，明年还靠谱吗

先用**全部上一年完整COIN样本**确定收益前25%的门槛，再检查下一年覆盖；不能先挑出下一年仍有完整数据的币，再倒过来定义上一年的赢家。以下收益仅统计两年都完整的对应币，缺失、部分历史和未完整存续的数量另外保留。

{table(['版本','年份配对','完整配对数','收益排名相关','上年前25%次年完整/全部','上年前25%次年收益中位数','其余币次年中位数'],persistence)}

多头跨年相关大约 −0.02 至 +0.07，基本没有稳定的币种排名。空头近期几组约 +0.10 至 +0.20，存在较弱持续性；例如2024年前25%的币在2025完整配对样本中中位数 +39.62%，其他币 +24.31%。但2021→2022相关为 −0.23，上年赢家下一年反而更差，不能把最近几组顺利解释成永久属性。

2025年前25%空头币共75个，2026只有65个具备完整窗口，9个只有部分窗口、1个无有效窗口。表中 +13.81% 不代表全部75个历史选中币的组合可得收益，也不是PIT认证的选币回测。

## 5. 全部预先规定的入场状态检查

差值均为A组减B组的每笔算术收益，单位百分点（pp）；不是策略复利收益。A组依次为顺MA60方向、顺过去30日涨跌、高ER、少穿越、低ATR、高成交额；B组为对应反侧/对照。星号表示任一侧未满足至少30笔、10币、5个入场月份，不能据该格解释跨年规律。

{table(['交易分支','A对B','2024','2025','2026','跨年相对关联检查','三年正算术/对数收益条件'],comparisons)}

相对关联检查要求三个审计年样本够、差值同方向、合并双向聚类区间不跨零、各年按入场月份对齐后同方向，以及两项合并敏感性同方向。月份对齐是用于识别共同市场阶段影响的补充，不替代总事件筛选问题。2/36通过相对关联检查，0/36通过更进一步的正收益条件。这不是证明其他特征绝对无用，只说明这六个固定定义尚未提供足够证据。

## 输入、时序、统计与边界

- 沿用 SMA7、Wilder ATR14、1.5ATR、约1倍固定数量仓位、下一开盘成交、前一收盘已知止损和原反手规则。原版及四版本收益不重写、不搜参。
- 重新通过 Lab 固定组合 `binance.v3.research_inputs.v2` 读取683个代码（652 COIN、31 UNKNOWN），包括量能；与上一轮本主题每个完整历史分段的价格、时间、有效掩码逐项相等。共{source['full_history_trades']:,}笔原交易全部对应。
- 入场特征只用信号日收盘，至少90根连续有效日线；年度特征只用上一年12月31日，过去90个有效ATR观测另需ATR预热。缺口、零成交、短历史不填充。年度特征缺失有显式分母：2024/2025/2026完整年样本206/298/474币，其中173/242/413币满足本次全部前置特征。
- 特征有效的COIN自然退出账本包含{x['coin_feature_valid_natural_trades']:,}笔交易，保留{x['raw_trade_labels_including_bankruptcies']}笔本金耗尽；其中2020年以后的合并主对照实际使用{x['purges'][0]['eligible']:,}笔。多空/反手分支之间有重复或相互关联的事件，不能当成独立新增样本。
- 各年度只纳入当年入场且退出早于年度末的标签；跨年退出剔除以免借用下一年的结果。强制末端估值不冒充自然退出，另保留含末端标签的敏感性。
- 本轮算术均值包含−100%损失；有本金耗尽时，该组平均对数收益记为不可用，绝不删掉归零记录后宣称复利有效。上一轮原多头规律审计主要报告对数差值，不能将两次数字混成同一统计量。
- 不确定性用500次“币种权重×入场月份权重”的独立Poisson乘积重采样；保留全部252个期间/分支/敏感性对照。它是探索性相关结构处理，不是精确因果检验，也未证明全套多重检验后的显著性。[Owen与Eckles方法来源](https://arxiv.org/abs/1106.2125)。
- 所有历史已经揭示，无盲样本外；没有执行新的过滤策略、联合条件、选币组合或实盘。未认证完整历史身份/PIT、资金费率和真实标记价格强平。空方在负资金费率时可能付费，因此这里不称为全成本净收益。[Binance资金费率说明](https://www.binance.com/en/support/faq/detail/360033525031)。

## 下一步的范围应当很小

如果继续，只保留“年初成交活跃的空头池”和“空头避开高ER状态”这两条候选，分别验证其对完整交易路径的增量，再看未揭示时间。不能把二者未经检验地拼接，也不应继续在这批历史上扩大阈值搜索。本轮不建立币种白名单，不把ZEC/HYPE/UNI等历史赢家写入执行条件。

## 可复核证据

5项新增专项检查和20项文档检查通过；661个历史足够长的标的完成前缀及未来价格/成交额扰动检查，所有保留分段的原价与有效掩码逐项相等。前一轮多空回放的1,346个文件与更早多头研究的1,357个文件均保持原样。本主题可信入口通过；仓库全局仍有6条其他主题既有读取登记问题，未宣称全仓库通过。

- [本轮验证记录](../artifacts/applicability-20260908/validation.json)
- [分析合同](../specs/applicability-contract-20260908.json)
- [重新读取与逐段核对结果](../artifacts/applicability-20260908/feature-summary.json)
- [全部入场条件、样本量和探索区间](../artifacts/applicability-20260908/entry-feature-contrasts.csv)
- [36项条件稳定性检查](../artifacts/applicability-20260908/rule-stability.csv)
- [所有年度币种类型结果](../artifacts/applicability-20260908/annual-asset-type-atlas.csv)
- [年度类型跨年比较](../artifacts/applicability-20260908/annual-type-stability.csv)
- [币种排名持续性与缺失覆盖](../artifacts/applicability-20260908/coin-year-persistence.csv)
- [逐笔入场前特征及原始损益](../artifacts/applicability-20260908/trade-features.csv.gz)
- [年度前置特征覆盖](../artifacts/applicability-20260908/annual-feature-coverage.csv)
- [输入与特征指纹](../artifacts/applicability-20260908/feature-manifest.json)
'''
    text=text.replace('万美元','万 USDT')
    path=ROOT/'diagnostics/applicability-report-20260908.md';path.write_text(text);print(path)


if __name__=='__main__':build()
