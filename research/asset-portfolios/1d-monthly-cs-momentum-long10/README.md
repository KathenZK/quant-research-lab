# Binance-1D-Monthly-Cross-Sectional-Momentum-Long10

- 别名：`BIN-1D-MCSM-L10`
- 市场：Binance USD-M USDT 永续，UTC `1d`
- 机制：每月 1 日等权做多上一个完整日历月涨幅最高的 10 个合资格合约，持有一个月，不做空；本轮参考执行为 UTC 00:15 open
- 当前状态：`explore / diagnostic-only / not promoted / not live-ready`
- 最新研究：2026-09-09 已补出 76 月连续账户，状态 `EXPLORATORY_ESTIMATED_ACCOUNT_NOT_VERIFIED_NET`。100,000 USDT 在含观察资金费的中心估算中变为 **10,185,430.84 USDT**，总收益 **+10,085.43%**、CAGR **107.53%**、日末及换仓边界最大回撤 **-93.43%**；不是精确净收益或实盘通过。见[本轮报告](diagnostics/binance-1d-mcsm-baseline-estimate-20260909.md)。
- 四场景总收益：不含资金费的价格对照 **+912.33%**；资金费中心/不利/有利估算 **+10,085.43% / +9,647.72% / +10,199.47%**。三种资金情景不是全历史真实净收益的置信区间或数学上下界，不能把价格账当作永续净收益。[最终摘要](artifacts/baseline-estimate-20260909/accounts/summary.json)
- 输入修复：官方确认 LIT 从 Litentry 换成 Lighter、AERGO 旧合约终止后重新上线；跨身份/跨合约形成资格分别按原排序补为 2026-01 Q、2025-05 LAYER，其他 758 腿不变。修复前价格账只留对照，不当最终基线。
- 执行裁决：旧绩效保持 `PERFORMANCE_INVALIDATED`；本轮估算利润显著为正，但完整历史资金日历、精确 mark/终止价、全池 PIT 与强平/成交均未认证。此前双弱退出不采纳，本轮没有优化参数，不晋升、不交接生产。

## 边界

这是独立 long-only 家族，不覆盖 [`BIN-1D-MCSM-LS3`](../1d-monthly-cs-momentum-ls3/README.md)。Binance 原生 USD-M 股票/TradFi 永续与加密永续一样按点时上市历史进入合约池，不做资产类别排除；外部现货美股全市场不属于本家族。

## 入口

- 最新报告：[连续账户估算 B0E](diagnostics/binance-1d-mcsm-baseline-estimate-20260909.md)
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
