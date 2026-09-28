"""从已完成固定产物生成中文研究报告，不计算新的候选或检验。"""
from pathlib import Path
import datetime as dt
import hashlib
import json

import pandas as pd

FAMILY=Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((FAMILY/path).read_text())


def main():
    stat=load('artifacts/p1-statistics-exact-r1/report.json')
    capture=load('artifacts/p2-capture/completed.json')
    reconstruction=load('artifacts/reconstruction-audit.json')
    assert stat['status']=='COMPLETED' and stat['bootstrap_reps']==1_000_000
    assert capture['output_contract_checks_passed'] and reconstruction['status']=='PASS'
    points=pd.read_csv(FAMILY/'artifacts/p1-research/point-summary.csv').set_index('group')
    intervals=pd.read_csv(FAMILY/'artifacts/p1-statistics-exact-r1/intervals.csv')
    env=intervals.loc[intervals.block_days.eq('envelope')].set_index(['unit','metric'])
    agg=pd.read_csv(FAMILY/'artifacts/p2-capture/aggregate.csv')
    agg=agg.loc[agg.cost.eq('base')].set_index('group')
    decisions={r['unit']:r for r in stat['units']}
    counts=pd.Series([r['status'] for r in stat['units']]).value_counts().to_dict()
    names={'U_LONG':'20日方向·多','U_SHORT':'20日方向·空','M_LONG':'MA7全部·多','M_SHORT':'MA7全部·空',
           'S1_LONG':'已有方向推进·多','S1_SHORT':'已有方向推进·空','S2_LONG':'新方向候选·多',
           'S2_SHORT':'新方向候选·空','S3_LONG':'回撤后重启·多','S3_SHORT':'回撤后重启·空'}
    status={'HISTORICAL_CANDIDATE':'达标历史候选','RULE_NOT_SUPPORTED':'该规则未达目标',
            'INSUFFICIENT_EVIDENCE':'证据不足','INFERENCE_UNRELIABLE':'推断不可靠'}
    primary=[]
    ci=[]
    accounts=[]
    for u,p in points.iterrows():
        primary.append(f"| {names[u]} | {int(p.complete20):,} | {p.q20:+.3f} | {p.delta_q20:+.3f} | {p.l20:+.3f} | {p.delta_l20:+.3f} | {status.get(decisions[u]['status'],decisions[u]['status'])} |")
        row=[]
        for m in ('Q20','Delta20','L20','DeltaLate'):
            z=env.loc[(u,m)]
            row.append(f"[{z.lower:+.3f}, {z.upper:+.3f}]")
        ci.append(f"| {names[u]} | "+' | '.join(row)+' |')
        a=agg.loc[u]
        accounts.append(f"| {names[u]} | {p.mean_return20:.2%} | {p.base_event_mean_after_fee_slippage:.2%} | {a.terminal_mark_return_median_entered_segments:.2%} | {int(a.segments_with_intraday_insolvency_breach)}/{int(a.segments_with_entries)} |")
    candidate=stat['selected_historical_candidate']
    s2l=points.loc['S2_LONG','opportunities']/points.loc['M_LONG','opportunities']
    s2s=points.loc['S2_SHORT','opportunities']/points.loc['M_SHORT','opportunities']
    reliable=stat['all_primary_reliable']
    decision_text='没有达标历史候选；本轮不进入候选确认或实盘准备。' if candidate is None else f'唯一冻结候选为{candidate}，仅为历史候选；仍须新时间确认，未进入实盘准备。'
    count_text='、'.join(f"{v}个{status.get(k,k)}" for k,v in counts.items())
    failure_details=[]
    for unit,decision in decisions.items():
        if decision['status']!='RULE_NOT_SUPPORTED':
            continue
        for metric in ('Q20','Delta20','L20','DeltaLate'):
            z=env.loc[(unit,metric)]
            threshold=0 if metric in ('L20','DeltaLate') else .25
            fails=(z.upper<=0) if threshold==0 else (z.upper<threshold)
            if fails:
                failure_details.append(f"{names[unit]}的{metric}区间上界为{z.upper:+.4f}，未达到{threshold:.2f}ATR门槛")
    failed_text='；'.join(failure_details)+'。' if failure_details else '没有任何具体规则被可靠区间排除至最低效应以下；未达候选要求的结果仍按证据不足处理。'
    report=f'''# 中期趋势延续：这次究竟发现了什么

2026-09-08｜Binance-1D-Medium-Term-Continuation-State｜BIN-1D-MTCS

**{decision_text}** 10个固定单元的裁决为：{count_text}。本轮的有效发现是：MA7穿越混合了不同的价格状态；过去已有同向推进的穿越及回撤后重启，在本历史样本中，其Q20与后半程位移的均值点估计高于新方向启动候选。这不是对所有组间差异的独立统计确认，这些差异还不能直接变成一个足够强、可稳定捕获的事前识别器。

研究目标始终是“在当时识别某标的某方向具有中期延续性的机会”。本轮不是要求每个币都盈利，也不要求同日跑赢其他币。逐币、年度和账户表用于解释边界，不能代替这个主问题。

## 1. 对原来想法的直接回答

**研究方向有依据，MA7只能承担局部观察入口。** 已有趋势研究支持检验过去价格信息的预测价值，不能保证任意币、任意周期或任意穿越都有效。如果此前把跨市场长期证据讲成“每个币一旦出现趋势就会继续”，这个说法过强。[文献与命题边界](literature-boundary.md)。

**你的K线观察抓到了一个值得拆分的问题。** MA7多头穿越中{s2l:.2%}、空头穿越中{s2s:.2%}在此前20日并没有沿新信号方向推进。把它们和已有同向趋势放在一起，检验的是混合问题。MA7整体弱，不足以否定已有趋势延续。

**这10个固定状态定义尚未证明能在本研究范围内识别出达到预定强度的中期延续机会。** 正的后续均值、比其他状态好、比同币一般机会有增量、达到预定强度、可用有限资金交易，是逐层增加的要求。本轮四个必要指标全部固定后再计算，结果见下表。事后挑ETH、HYPE或历史收益最好的代码，会新增一次未经确认的选择；不作为解决办法。

## 2. 本次具体检验了什么

使用648个具有合资格历史的观测加密标的，价格范围从2019年起至2026-09-05完整收盘。全库存652个COIN中4个因不足60根连续日K排除；不按收益选池。全部历史已被研究流程揭示，不能称盲测或新样本外。

每个收盘只使用过去信息：U是过去20日涨跌方向；M是严格穿越MA7；S1是M且此前20日、5日均同向；S2是M且此前20日未同向；S3是M且此前20日同向、最近5日回撤。它们只表示这些具体方向条件，**还不是一个经验证的“强趋势”定义**。每类多空各一，共10个单元；没有新增指标、最优均线、币种专用参数或退出搜索。

信号收盘确认，下一根开盘参与，观察第20根收盘。Q20是有方向的价格位移，除以信号日ATR14；L20是第5日至第20日的追加位移。Δ20/Δlate分别比较同币同方向、同评估范围的全部合资格日，并按入选事件的币种构成标准化。这个对照允许利用市场方向环境，不要求市场中性或同日选币alpha。

冻结成功条件：Q20与Δ20同时区间下界超过0.25ATR，L20与Δlate下界超过0。S组若进一步宣称“筛选比MA7有足够附加价值”，还要求Δfilter下界超过0.25。**0.25ATR是预先约定的最低研究效应，并不等于一切较小效应不存在。** [研究合同](../specs/research-contract.md)、[统计合同](../specs/statistics-contract.md)。

## 3. 主结果与可作出的裁决

以下均为完整20日标签事件。正数表示沿信号方向推进；所有数字单位为ATR。

| 固定单元 | 完整事件 | Q20 | Δ20 | L20 | Δlate | 按冻结合同裁决 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
{chr(10).join(primary)}

完整重算状态：`{stat['inference_status']}`，全部主指标计算可靠性为`{reliable}`；状态分布为`{json.dumps(counts,ensure_ascii=False)}`。这里的“可靠性”只表示通过本轮数值与抽样检查，不是所有统计假设和市场外推已经得到证明。

46项指标采用同时95%的Bonferroni区间；对同一日历时间块保留全部币，60日和120日各完整重算1,000,000次，下面取两者较宽包络。上界排除最低效应，才说这条具体规则没有达到目标；区间跨越门槛则是证据不足。不能将后者简化为“趋势不存在”。

| 固定单元 | Q20区间 | Δ20区间 | L20区间 | Δlate区间 |
| --- | --- | --- | --- | --- |
{chr(10).join(ci)}

原始46项、分块区间、附加筛选价值和裁决原因见[完整统计报告](../artifacts/p1-statistics-exact-r1/report.json)、[区间表](../artifacts/p1-statistics-exact-r1/intervals.csv)、[裁决表](../artifacts/p1-statistics-exact-r1/unit-decisions.csv)。逐币/逐年不是另外确认的发现，不从中挑显著赢家。

具体排除依据：{failed_text} 这些裁决排除的是本合同要求的最低增量，并不等于相应方向任何正收益都不存在。

模拟精度诊断中，裸MA7多头Δ20上界距0.25门槛约0.0618ATR，两半复制给出的上界差最多约0.00116ATR；该次最低增量排除没有贴着模拟噪声边界。所有指标两半区间端点的最大差约0.0154ATR。这里精确的是逐复制计算，区间覆盖仍受重采样假设和非平稳性限制；2,474日仅相当于约41个60日长度或21个120日长度，不能把这些商数当成已证明独立的市场阶段数。

## 4. 为什么K线上看得到趋势，整体检验却较弱

第一，入口混合。S1、S3的两方向Q20与后半程L20点估计均正，S2两方向Q20均负。固定完整20日队列的每日均值路径如下，各天用同一批事件，没有用变化的样本数制造曲线。图是结果后的解释，不是额外统计检验或退出方案。

![固定20日队列的均值路径](../artifacts/path-illustration/continuation-paths.png)

第二，平均表现和增量不同。S1多头Q20约0.290ATR，但比同币一般方向机会只多约0.125ATR；十组Δ20点估计最大约0.187ATR，均小于冻结0.25。小的真实优势仍可能存在，本轮没有把它证成足以使用的优势。

第三，时间环境和尾部很重要。S3多头在2021年Q20约1.900、2022年约−1.203，2025和2026年也为负。S1、S3多头仅2024年2月与11月的正贡献和便超过各自全期净贡献。这不是把好月份删掉后重新测试；它说明大量跨币事件可能来自同几次行情，事件数远大于独立市场经历数。

第四，“好币”尚不能作为稳定身份。ETH的S3多头在该历史表表现较强，BTC的同组绝对Q20为正但相对对照改善为负；HYPE部分S组仅数次事件。事后按这些收益名单选币，既可能选择市场阶段，也可能选择偶然尾部。这里不要求多数币成功，只要求任何拟投入使用的单币发现有独立确认。[逐币/时期与贡献解释](p1-economic-interpretation.md)。

## 5. 能不能赚到这些趋势的钱

本轮只测固定20日持有。下表的“事件均值”允许机会重叠；“账户”则每个币每个连续价格段独立从1开始，只在空仓时进场、期间忽略新信号、固定数量持有。账户段长不同，不把中位数视为统一年化回报，不把不同段拼成一条策略净值。

费用假设是每次实际成交名义额的0.10%手续费、0.04%不利滑点；另做0.08%滑点压力检查。资金费未完整核验，以下**不是完整净收益**。账户期末标记还可能包括未完成持仓或停止账快照。

| 固定单元 | 事件毛收益均值 | 事件手续费滑点后均值 | 有入场段期末资金标记收益中位数 | 盘中非正权益段/有入场段 |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(accounts)}

裸MA7的事件均值扣手续费滑点后两方向均略负。S1/S3的事件均值较好，但事件平均数没有自动兑现为稳定资金增长。S1多头原始收益均值约+2.42%，中位数约−4.19%；S2空头胜率约57.83%，均值却约−1.46%。这说明胜率不能代替期望，均值也不能代替资金能否承受损失。

S1空头的有入场段期末标记中位数约+3.08%，同时630个有入场段中110个触及盘中非正权益，61个发生收盘停账。模型保留未截断损失，不伪造交易所强平或止损成交，故这种路径不能认证可执行。多头则有不同程度的大回撤。

S1多头平均最大浮盈约3.538ATR，而第20日平均保留约0.290ATR。**事后峰值不是当时可知的退出价格**；这里不能推导出“加个止盈就能赚回来”。同样，20日固定持有捕获不好，也不能否定所有可执行退出机制。现在先保留这个失败位置，不追加止损止盈搜索。[捕获独立审计](p2-independent-audit.md)、[资金段表](../artifacts/p2-capture/summary.csv)、[完整持仓记录](../artifacts/p2-capture/trades.csv.gz)。

## 6. 数据、统计和复现还限制了什么

597,968行中有510,856个过去合资格日，其中497,748个具有完整20日标签；2,763个因已知中断/截尾不能评价，10,345个在截止时尚未成熟。648个输入标的中642个具有至少一个完整20日标签，统计的完整标签日期轴为2,474日。所有事前机会保留在机会表中，不当成0收益，也不被未来完整性提前筛选。缺失比例较小仍不能保证退市等尾部无偏。

当前观测库存和分类没有完整历史PIT证明，完整研究期的资金费窗口也未获证明。已有资金事件不等于应有事件完整。价格层发现可以保留，全成本与可交易性仍未验证。[数据与资金费边界](data-scope-and-funding.md)。

初次影响函数近似不合格：大量复制无法修正随机分母造成的线性化误差。它的区间全部保留但不参与裁决。本次按原合同允许的精度修复，完整重算所有分母、资产权重及对照均值，保持信号、标签、门槛、46项分母和basic区间不变。[修复合同](../specs/statistics-exact-computation-repair.md)、[原近似审计](statistics-approximation-audit.md)、[2048次完整参考对拍](../artifacts/p1-statistics-exact-r1/reference-parity.csv)。

真实输入重建覆盖全部648币、597,968行全部列，逐项完全一致；另直接核算1,956条价格/时点关系并做预定身份/覆盖位置的未来截断检查。资金独立审计核对全部225,998条持仓、13,180个分段账户和20条汇总，并抽查7,673行日权益。测试和复现通过说明结果计算可追溯，不证明经济假设为真。[重建收据](../artifacts/reconstruction-audit.json)、[验证与交付](validation-and-delivery.md)。

## 7. 该继续什么，停止什么

本轮结论是对**10个粗粒度方向/MA7状态定义**的有限裁决。{decision_text} 不把没有历史候选改写为整个中期趋势命题已经被否定，也不从不确定结果里强选一条去做未来功效承诺。

应停止在这份已揭示历史上继续挑“MA7适用币”、调均线长度或用最优退出救均值。它们都会把新的选择藏在旧结果后面；本轮不自动扩搜索。

如果后续继续原经济问题，一个可以单独预注册的最小待证分支是：**在不依赖MA7穿越的机会全集中，用预先限定的、按波动标准化的过去趋势强度描述标的当时的状态，检验后半程延续是否随事前强度稳定提高。** 本轮只有涨跌符号条件，尚未测试这种强度关系；这是下一条待证假设，不是本轮已经发现的有效规则，也没有证据保证脱离MA7必然更好。先冻结一种强度定义、有限分组、20日主期限、同币对照和新时间确认方式，再看结果；既有历史只能用于探索与功效可行性。若预注册的关系不存在或只在揭示后挑选的币/月有效，应停止该定义下的识别路径；这不否定全部非单调或其他状态关系，也不授权事后更换分组挽救结果。

基础成本、数据可得性和风险约束继续前置；出现可冻结的方向性候选后，再投入完整持仓与执行验证。即使最终固定持有不适用，也不能以事后最高点替代可执行退出。原目标所需的是可复现的条件优势，而不是保证每次延续或追求漂亮的一条回测曲线。

本轮不注册交易版本、不晋升、不启动实盘或未来自动观察。全部结果为`explore / diagnostic-only / not promoted / not live-ready`，已揭示历史身份保持不变。

## 8. 复核入口

- [冻结研究合同](../specs/research-contract.md)与[用户目标](../specs/user-objective.md)
- [全部产物索引](../artifacts/README.md)与[复现步骤](../scripts/README.md)
- [主账](../binance-1d-mtcs-core-ledger.md)与[决策记录](../decision-log.md)

报告生成时间：{dt.datetime.now(dt.timezone.utc).isoformat()}。所有表格从已完成产物读取，不新增研究参数。
'''
    target=FAMILY/'diagnostics/research-report-20260908.md'
    if target.exists():
        raise FileExistsError(target)
    target.write_text(report)
    summary={'status':'BOUNDED_RESEARCH_COMPLETE','historical_candidate':candidate,
             'unit_status_counts':counts,'all_primary_numerically_reliable':reliable,
             'history_status':'ITERATIVE_REUSED_DIAGNOSTIC','new_time_confirmation':False,
             'fullcost_verified':False,'live_ready':False,'source_report':'p1-statistics-exact-r1/report.json',
             'report_sha256':hashlib.sha256(report.encode()).hexdigest(),
             'completed_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    (FAMILY/'artifacts/decision-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
