# Binance-1D-Monthly-Cross-Sectional-Momentum-Long10

## 2026-09-24 每周Top10已完整补证回测

每周一买上一完整周涨幅Top10，每币10%，不加MA120。2020-06-01至2026-07-01同日起步73个月、每边手续费0.10%+滑点0.04%、不含资金费、条件终止价下：周频累计**+64.51%**、年化**8.53%**、最大回撤**-97.42%**；同期月频**+925.13% / 46.63% / -95.43%**。318次周榜和8条成本/终止情景独立核对一致。BZRX/KEEP/COCOS/MEMEFI官方指数材料补回，首次失败保留，旧结果不改；不是已验证永续净收益。周频不采纳为实盘候选。[报告](diagnostics/binance-1d-mcsm-weekly-top10-20260924.md) · [318周名单与盈亏](artifacts/weekly-top10-20260924/terminal-complete/weekly-holdings-and-pnl.md) · [73个月与持币](artifacts/weekly-top10-20260924/terminal-complete/monthly-holdings-and-pnl.md) · [年度](artifacts/weekly-top10-20260924/terminal-complete/yearly-results.md) · [材料](artifacts/weekly-top10-20260924/README.md)

下文周频“缺价未完成”保留为2026-09-11当时状态，不能替代本轮已完成的73个月条件价格结论；本轮未重跑旧75个月W28。

## 2026-09-11 MA120单规则检查

已按用户指定完成Top10 + MA120入场/日线收盘跌破退出，不加其他规则。原76月、10万USDT、单边费0.1%和滑点0.04%下，价格收益从原+912.33%降至**+156.46%**，最大回撤仍**-90.47%**；含已有资金费估算从+10,084.17%降至**+576.05%**，最大回撤**-80.00%**。8条账户及全部信号独立重算一致。价格最高76个盈利月持仓漏买29个，其中22个不足120日历史；大赢家利润仅保留48.65%。当前完整规则不实盘，不把这次结果等同于所有均线退出无效。[报告](diagnostics/binance-1d-mcsm-ma120-round-20260911.md) · [固定规则](specs/binance-1d-mcsm-ma120-round-20260911.md) · [全部月度持仓与盈亏](artifacts/ma120-round-20260911/monthly-holdings-and-pnl.md) · [年度表](artifacts/ma120-round-20260911/yearly-results.md)

## 2026-09-11 最新研究：回撤来源、退出更多币与周频

原四条账户的回撤与月/年现金拆分、X5/X10八条新账户已完成并独立核对。原含费估算基线最大回撤来自2021-11-26至2023-09-01：权益少477.62万USDT，其中价格损失476.43万，资金费反而净收5.76万；同期BTC/ETH跌56.05%/63.66%。市场相关与剩余价格损益的统计拆分见报告，不能把全部损失都当市场下跌，也不能把回归剩余直接当选币Alpha。

在原76月、初始10万USDT、每边手续费0.1%与滑点0.04%下，首次信号退出最弱五币X5的价格收益 **+2,991.81% / 最大回撤-88.45%**，含观察资金费估算 **+14,080.41% / 最大回撤-87.49%**；首次信号全部退出X10只有 **+200.68% / -91.57%**、含费 **+231.89% / -87.33%**。X5含费原盈利腿/最高76腿利润保留78.01%/82.58%，低于S1的96.03%/98.64%，2022年仍亏74.20%；不实盘、不将X5当参数最优值。

频率比较固定为2020-04-01 00:15至2026-07-01 00:15 UTC的75个月，实际完成B0/M28、各4/8bp共四条价格账；W28/W7的四条周频账因下架币缺价停止。相同10万USDT、每边手续费0.1%与滑点0.04%、不计资金费时，同期B0累计+1,428.03%、最大回撤-95.43%；M28累计+2,210.85%、最大回撤-96.51%。M28仍是月换仓，只把榜单改成过去28日，不能当作周频收益。周频还没有全期收益结论：W7先缺BZRX、W28先缺KEEP估值，官方自动结算时刻可核，但结算价未知，不删腿、不补零或映射新币。[BZRX核查](artifacts/drawdown-frequency-round-20260911/independent-audit/bzrx-missing-endpoint-cause.md) · [KEEP核查](artifacts/drawdown-frequency-round-20260911/independent-audit/keep-missing-endpoint-cause.md)

入口：[本轮报告](diagnostics/binance-1d-mcsm-drawdown-frequency-round-20260911.md) · [固定方法](specs/binance-1d-mcsm-drawdown-frequency-round-20260911.md) · [本轮材料与逐月/年度明细](artifacts/drawdown-frequency-round-20260911/README.md)。旧账户、输入和被固定哈希的代码不改；下列历史记录保留原轮次语境。76月月/年表按月初00:15换仓后至下一月换仓后；75月频率表按自然月00:00估值、首尾00:15，不能直接混比。

- 别名：`BIN-1D-MCSM-L10`
- 市场：Binance USD-M USDT 永续，UTC `1d`
- 机制：每月 1 日等权做多上一个完整日历月涨幅最高的 10 个合资格合约，持有一个月，不做空；本轮参考执行为 UTC 00:15 open
- 当前状态：`explore / diagnostic-only / not promoted / not live-ready`
- 最新机制研究：2026-09-10 实际完成相似币对照、事前72小时资金费、固定20/7/2单币退出三项。单币退出含费估算收益 **+13,663.98%**（原生价优先基线+10,084.17%），MDD **-91.92%**（原-93.43%）；不计资金费 **+1,679.84%**（原+912.33%）。保留约96%正腿/99%大赢家利润，但2022年仍亏83.21%，不实盘。负资金费入场门槛不采用。[三项研究报告](diagnostics/binance-1d-mcsm-mechanism-round-20260910.md)
- 资金来源核查保留：2026-09-10 独立重算原四账户，未发现资金费方向、重复、数量倍率或复利错误；官方类型 API 核到16,211/97,421笔，因HTTP403未完成全量。3,695笔原生mark优先基线为+10,084.17%，仍非精确实盘净收益。[资金复核](diagnostics/binance-1d-mcsm-funding-recheck-20260910.md)
- 原账户：2026-09-09 的 76 月连续账户保留，状态 `EXPLORATORY_ESTIMATED_ACCOUNT_NOT_VERIFIED_NET`。100,000 USDT 在中心估算中变为 **10,185,430.84 USDT**，总收益 **+10,085.43%**、CAGR **107.53%**、日末及换仓边界最大回撤 **-93.43%**；不是精确净收益或实盘通过。见[原报告](diagnostics/binance-1d-mcsm-baseline-estimate-20260909.md)。
- 四场景总收益：不含资金费的价格对照 **+912.33%**；资金费中心/不利/有利估算 **+10,085.43% / +9,647.72% / +10,199.47%**。三种资金情景不是全历史真实净收益的置信区间或数学上下界，不能把价格账当作永续净收益。[最终摘要](artifacts/baseline-estimate-20260909/accounts/summary.json)
- 输入修复：官方确认 LIT 从 Litentry 换成 Lighter、AERGO 旧合约终止后重新上线；跨身份/跨合约形成资格分别按原排序补为 2026-01 Q、2025-05 LAYER，其他 758 腿不变。修复前价格账只留对照，不当最终基线。
- 执行裁决：旧绩效保持 `PERFORMANCE_INVALIDATED`；本轮估算利润显著为正，但完整历史资金日历、精确 mark/终止价、全池 PIT 与强平/成交均未认证。此前双弱退出不采纳，本轮没有优化参数，不晋升、不交接生产。

## 边界

这是独立 long-only 家族，不覆盖 [`BIN-1D-MCSM-LS3`](../1d-monthly-cs-momentum-ls3/README.md)。Binance 原生 USD-M 股票/TradFi 永续与加密永续一样按点时上市历史进入合约池，不做资产类别排除；外部现货美股全市场不属于本家族。

## 入口

- 最新报告：[资金费收益复核](diagnostics/binance-1d-mcsm-funding-recheck-20260910.md) · [原连续账户估算 B0E](diagnostics/binance-1d-mcsm-baseline-estimate-20260909.md)
- 本轮计划与证据：[检查计划](specs/binance-1d-mcsm-funding-recheck-20260910.md) · [独立账目](artifacts/funding-recheck-20260910/accounting/summary.json) · [部分官方来源](artifacts/funding-recheck-20260910/combined-sources/summary.json) · [原生价优先对照](artifacts/funding-recheck-20260910/native-replay/summary.json)
- 最新契约：[连续账户估算](specs/binance-1d-mcsm-baseline-estimate-20260909.md) · [身份修正](specs/baseline-estimate-identity-correction-20260909.md)
- 最终证据：[四场景账户](artifacts/baseline-estimate-20260909/accounts/summary.json) · [身份修正版输入](artifacts/baseline-estimate-20260909/inputs-identity-corrected/README.md) · [资金费输入](artifacts/baseline-estimate-20260909/funding-identity-corrected/summary.json)
- 核验范围：[最终 QA 与失败尝试保留](notes/baseline-estimate-qa-20260909.md)，局部测试/独立复算通过不等于全仓或实盘通过
- 前次严格核验：[基线验证 B0](diagnostics/binance-1d-mcsm-baseline-verification-20260908.md)，当时 `BASELINE_NOT_VERIFIED` 与精确输入缺口保留，不被本轮估算覆盖
- 前轮报告：[生命周期与资金费研究](diagnostics/binance-1d-mcsm-lifecycle-funding-round-20260908.md)
- 前轮契约：[固定账户语义与日级检验](specs/binance-1d-mcsm-lifecycle-funding-round-20260908.md)
- 主账：[binance-1d-mcsm-l10-core-ledger.md](binance-1d-mcsm-l10-core-ledger.md)
- 契约：[specs/binance-1d-mcsm-long10-diagnostic-contract-2026-08-18.md](specs/binance-1d-mcsm-long10-diagnostic-contract-2026-08-18.md)
- 诊断：[diagnostics/binance-1d-mcsm-long10-diagnostic-2026-08-18.md](diagnostics/binance-1d-mcsm-long10-diagnostic-2026-08-18.md)
- 宽度诊断：[diagnostics/binance-1d-mcsm-long-breadth-diagnostic-2026-08-19.md](diagnostics/binance-1d-mcsm-long-breadth-diagnostic-2026-08-19.md)
- 风险与缓冲诊断：[diagnostics/binance-1d-mcsm-long10-risk-buffer-diagnostic-2026-08-19.md](diagnostics/binance-1d-mcsm-long10-risk-buffer-diagnostic-2026-08-19.md)
- 正收益与现金缺口诊断：[diagnostics/binance-1d-mcsm-long10-positive-cash-diagnostic-2026-08-19.md](diagnostics/binance-1d-mcsm-long10-positive-cash-diagnostic-2026-08-19.md)
- 可实盘化与执行审计：[diagnostics/binance-1d-mcsm-long10-liveability-audit-2026-08-20.md](diagnostics/binance-1d-mcsm-long10-liveability-audit-2026-08-20.md)
- 赚钱效应与领涨延续诊断：[diagnostics/binance-1d-mcsm-money-effect-continuation-diagnostic-2026-08-20.md](diagnostics/binance-1d-mcsm-money-effect-continuation-diagnostic-2026-08-20.md)
- 赚钱效应冻结合同：[specs/binance-1d-mcsm-money-effect-continuation-diagnostic-contract-2026-08-20.md](specs/binance-1d-mcsm-money-effect-continuation-diagnostic-contract-2026-08-20.md)
- 执行语义修复合同：[specs/binance-1d-mcsm-long10-execution-repair-contract-2026-08-20.md](specs/binance-1d-mcsm-long10-execution-repair-contract-2026-08-20.md)
- 决策：[decision-log.md](decision-log.md)
- 脚本：[scripts/README.md](scripts/README.md)
- 产物：[artifacts/README.md](artifacts/README.md)
