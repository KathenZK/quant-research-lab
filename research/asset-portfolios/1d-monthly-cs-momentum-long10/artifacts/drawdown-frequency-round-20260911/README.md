# 2026-09-11：Top10回撤来源、扩大退出与周频

家族BIN-1D-MCSM-L10。[主报告](../../diagnostics/binance-1d-mcsm-drawdown-frequency-round-20260911.md)负责完整结论；本页用于定位方法、输入、明细和验收，不是生产授权。全部历史已经揭示，不标为盲测。

## 已完成研究与交付验收

原四账户的回撤窗口、304个月/28个年度和逐腿现金已独立复核。X5/X10八条新账户已完成，先复现原S1，再按相同254个额外估值时点比较；456/700条退出计划、282个新增prior活动目标及同步open均核过。价格与观察资金费分别从100,000 USDT独立回放，每边手续费0.1%，滑点0.04%及0.08%；BNX/VIDT原条件终止估价保持不变。

频率分支八条预定比较已分别裁定：75个月的B0同期/M28、各4/8bp共四条价格账完整；W28/W7各两成本共四条缺价停止。独立核账复现四条完整账户的10,688个净值时点、5,556条净额交易、3,000腿、300个月及年度现金，也复现四条失败账户的同一个最早缺价时点。不把八条计划算成八条已完成收益。资金新名单超出原估值范围，资金现金不可用，不填0、不补交易价代理。

## 这轮最重要的已证结果

| 76月、2020-03-01至2026-07-01 UTC、每边滑点0.04% | 累计收益 | 年化 | 最大回撤 |
| --- | ---: | ---: | ---: |
| X5价格对照 | +2,991.81% | 71.92% | -88.45% |
| X5含观察资金费估算 | +14,080.41% | 118.66% | -87.49% |
| X10价格对照 | +200.68% | 18.99% | -91.57% |
| X10含观察资金费估算 | +231.89% | 20.86% | -87.33% |

X5首次信号退出原触发币与当时7日最弱五币的并集，余下继续S1；X10首次信号清篮子，当月均不补仓。X5含费原盈利腿/最高76腿利润保留78.01%/82.58%，低于S1的96.03%/98.64%，2022仍亏74.20%；含费终值只比S1高约3.03%。X10只保留最高76腿36.21%，不采用该全清表达。两者仍不能实盘。

原含费基线的最大回撤从2021-11-26至2023-09-01，权益损失4,776,236.30 USDT：价格损失4,764,264.21，资金净收57,597.45，手续费49,692.53、滑点19,877.01。同期BTC/ETH跌56.05%/63.66%。过去数据估计的市场相关价格损失约237.53万、剩余约267.59万，另有边界/样本不足部分；这是统计拆分，不是因果归属或已经完成的对冲回测。广谱池有缺价日，不拼接伪完整指数。

频率比较单独固定2020-04-01 00:15至2026-07-01 00:15 UTC、75个月，初始100,000 USDT、每边手续费0.1%，下表均不计算资金费：

| 策略与每边滑点 | 实际状态 | 累计收益 | 年化 | 最大回撤 |
| --- | --- | ---: | ---: | ---: |
| B0原日历月榜、月换，4bp | 完整价格账 | +1,428.03% | 54.71% | -95.43% |
| B0原日历月榜、月换，8bp | 完整价格账 | +1,352.47% | 53.46% | -95.57% |
| M28过去28日榜、月换，4bp | 完整价格账 | +2,210.85% | 65.30% | -96.51% |
| M28过去28日榜、月换，8bp | 完整价格账 | +2,094.10% | 63.94% | -96.62% |
| W28过去28日榜、周换，4/8bp | KEEP缺价停止 | 不可用 | 不可用 | 不可用 |
| W7过去7日榜、周换，4/8bp | BZRX缺价停止 | 不可用 | 不可用 | 不可用 |

M28多赚但回撤更深，而且仍是月换仓，不能用它回答周换是否更好。W28/W7各327次事前换仓名单可供查看，但账户回放未覆盖全期；计划名单和失败前核查净值都不是完整实测持仓盈亏。

## 固定方法和输入

- [本轮合同](../../specs/binance-1d-mcsm-drawdown-frequency-round-20260911.md)，SHA256 `aa38d87cf3cb374d4f587faf3660586950986bfa2a25813e851d65c28862d2d4`。
- [组合内容检查](bundle-check.json)：固定`binance.v3.research_inputs.v2`及其原manifest/内容指纹；文件一致不代替研究窗口或实盘通过。
- 原760腿持仓SHA256 `2765cc3fade0b8c571871c5e2bfff88ad6e5bc65198a5fff35e261afa6df61e4`；原生mark优先资金表SHA256 `fc57b942e14ab29007256326404c698f379d24988a0da274fe4434b0d9c70990`。原97,421个观察事件不等于完整资金日历。
- [前轮完成材料](../mechanism-round-20260910/completion.json)及其旧文件哈希保留；旧脚本、会计内核、原输入/回测和源数据未改。新增普通成交资格只看此前已闭合00:00 bar，参考价为00:15 open，不使用目标bar未来成交量。

## 明细与验收入口

| 目录/文件 | 内容 |
| --- | --- |
| [drawdown/summary.json](drawdown/summary.json) | 原四账峰谷、恢复期、月份与现金核对 |
| [drawdown/window-summary.json](drawdown/window-summary.json) | 精确窗口现金、BTC/ETH参照及统计市场相关/剩余损益 |
| [drawdown/monthly-details.parquet](drawdown/monthly-details.parquet) · [yearly-details.parquet](drawdown/yearly-details.parquet) | 原四账每月币种与盈亏、年度汇总 |
| [drawdown/holding-legs.parquet](drawdown/holding-legs.parquet) · [monthly-boundary-costs.parquet](drawdown/monthly-boundary-costs.parquet) | 实际持仓数量、逐腿现金与单列净额边界费用 |
| [broader-exit/summary.json](broader-exit/summary.json) | X5/X10八账、成本压力和利润保留 |
| [X5退出计划](broader-exit/x5-exit-plan.parquet) · [X10退出计划](broader-exit/x10-exit-plan.parquet) | 先于新执行补证/账户结果固定的退出名单及时间 |
| [broader-exit/all-plans-frozen.json](broader-exit/all-plans-frozen.json) · [execution-ready.json](broader-exit/execution-ready.json) | 新prior活动补证的锁定请求与逐目标结果 |
| [X5含费月表](broader-exit/estimated_center-x5-4bp/monthly.csv) · [年表](broader-exit/estimated_center-x5-4bp/yearly.csv) · [逐腿](broader-exit/estimated_center-x5-4bp/holding-legs.parquet) | 同类路径包含全部price_only/estimated_center、x5/x10和4/8bp账户 |
| [broader-exit/postrun-integrity.json](broader-exit/postrun-integrity.json) | 原S1精确复现、132个产物/源哈希和本地预算检查 |
| [weekly/summary.json](weekly/summary.json) | 四条B0/M28完成价格账、四条W28/W7缺价停止；资金现金均不可用 |
| [weekly/holding-windows.parquet](weekly/holding-windows.parquet) | 事前固定的持仓计划，不因存在计划就叫已完成实际账户 |
| [weekly/B0-4bp/monthly.parquet](weekly/B0-4bp/monthly.parquet) · [年度摘要](weekly/B0-4bp/summary.json) · [leg-price-pnl.parquet](weekly/B0-4bp/leg-price-pnl.parquet) | 同类路径包含B0/M28、4/8bp完整账户；逐腿数量与全持仓区间价格盈亏，不把整腿现金塞进退出月份 |
| [independent-audit/drawdown-summary.json](independent-audit/drawdown-summary.json) | 原回撤/月年现金独立核对 |
| [independent-audit/breadth-summary.json](independent-audit/breadth-summary.json) | 扩大退出八账和日收盘规则独立核对 |
| [independent-audit/weekly-summary.json](independent-audit/weekly-summary.json) · [审核说明](independent-audit/weekly-README.md) | 四条完整频率账与四条最早缺价分别独立裁定，不跨失败点拼接收益 |
| [completion.json](completion.json) · [qa.json](qa.json) | 全轮最终完成、测试与文件哈希验收入口；以实际记录为准 |

[生成与审核脚本导航](../../scripts/README.md)。用户工作簿为[每月持仓盈亏与年度比较](../../../../../outputs/mcsm-20260911-drawdown-frequency/Top10_月度持仓盈亏与年度比较_20260911.xlsx)，已从研究输出生成，最终视觉和内容验收见上述记录。20条方案/成本记录中16条完整、4条失败；包含1,212个月、112个年度、12,120条持仓腿。954条频率换仓明细中，300条属于已完成月度账户，654条只是W28/W7各327次的事前选币计划，收益/盈亏不可用，不按成本重复计划。该文件不新增行情读取或实盘订单。

## 月份、费用与资金不可用

76月原/退出组按每月00:15换仓后至下月00:15换仓后，结束月包含下一次边界交易费用；首月还含最初建仓费用。下一月新币的开仓费用单列月总账，不强行塞给当月未持有的币。逐腿数量是月初实际模型数量；`entry_boundary_fee_paid`仅展示本次实际交易，不得与已经计入前一月的费用重复相加。

本轮76月年度汇总按上述月账复利，年界为00:15，区别于前轮报告采用的00:00年界；这可能带来小幅年度差异，但不改变任何旧全期账户。75月频率组按自然月00:00市值变化，首期和终期为实际00:15，跨月持仓不全部算到平仓月份。两组不能直接按相同“月份”混比。

价格对照里的资金现金显示不可用，表示没有计算完整资金收益，绝不表示历史资金费为0。含观察资金费估算也不是精确实盘净收益；资金日历、PIT、终止估值、容量、保证金/强平/ADL限制仍保留。

## BZRX与KEEP缺价说明

[原因核查](independent-audit/bzrx-missing-endpoint-cause.md)记录：W7固定2021-12-13入场、2021-12-20预定退出，而[Binance官方公告](https://www.binance.com/en/support/announcement/detail/dff27dc6bcbb432c902bcbea5e24ddfa)确认BZRX期货于2021-12-19 02:00 UTC自动结算并下架。公告解释了端点为何不存在，不提供此次实际结算价格或现金；本轮不拿其他成交价猜结算，不映射OOKI，不删腿救全期结果。

[KEEP原因核查](independent-audit/keep-missing-endpoint-cause.md)记录：W28/W7的固定计划均包含2022-02-14入场、2月21日预定退出的KEEP，而[Binance官方公告](https://www.binance.com/en/support/announcement/detail/96698a6a80f64cb1ae27f813032bfaa9)确认KEEP期货于2022-02-15 02:00 UTC自动结算并下架。不能把KEEP期货映射成T或按现货兑换比例续算；实际结算价格和现金仍未知。

真正最早失败并非只看预定退出日：W7在2021-12-20 00:00 UTC估值时缺BZRX的12月19日日K；W28在2022-02-16 00:00 UTC估值时缺KEEP的2月15日日K。主回放错误中的日期表示缺失日K标签，独立审核另外记录了需要它的账户估值时刻。两者各成本版本均在该点停止；不据此判断周频盈利或亏损。

## 本地保留与预算

本轮总预算100MiB：drawdown与broader-exit各15MiB、weekly40MiB，其余留给独立验收、报告和工作簿。X5/X10分支结束时约8.13MiB，最终全轮用量以completion为准。家族既有体积已达C-externalize，不复制原日线/分钟大包或旧全套账户，不将大型本地输出加入普通Git。

本目录的计划、投影、月年/逐腿表和工作簿均有固定脚本/源哈希，可按原输入重建；保留原始实现失败与修复经过，不把失败当已成功结果。未获迁移/删除授权，不移动或清理历史资料。
