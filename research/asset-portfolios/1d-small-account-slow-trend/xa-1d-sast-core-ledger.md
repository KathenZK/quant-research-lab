# Multi-Asset-1D-Small-Account-Slow-Trend Core Ledger

## Family Identity

- Full family name：`Multi-Asset-1D-Small-Account-Slow-Trend`
- Alias：`XA-1D-SAST`
- 市场/周期：美国上市美元 ETF，日线账户、月末信号；SPY、EFA、VNQ、IEF、TLT、GLD、PDBC。
- 核心问题：约 10,000 美元现金账户，12M 慢趋势层能否在分散/风险缩放之外提供足够经济增量。
- 防串线：新独立家族，不继承 EWMAC、传统期货 TSMOM、加密 TSMOM 的策略身份、参数或绩效。

## Current State

- 主状态：`explore / not promoted / not live-ready`。
- 当前观察：`P0-2026-09-08`，已完成首轮账户研究，未登记版本。
- 经济裁决：`NO_GO_PREDECLARED_ECONOMIC_INCREMENT`；只否定本轮 12M 层的增量。
- Runner / dry-run / live：均无；本工作区没有下单、划转、启停生产实例。
- 实际缺口：发行人全历史精确分配/支付日、真实开盘成交与券商费用/权限、用户税籍；历史已经揭示。
- 下一决策：保留静态对照证据，若继续先独立固定静态小账户执行核验，不通过改门槛或选 10M 救本轮结果。

## Version Rules

- P0 为冻结的探索对象和数据/代码快照，不是登记版本或 promotion。
- 后续任何规则、工具、风险预算、成本优惠或精确公司行动替换，都需要新对象与曝光记录；旧输出不得覆盖为“原对象成功”。
- 若未来合格候选需要登记，另更新版本表；运行授权只在 runner 侧成立。

## Observation Table

| Observation | Status | Role | Frozen evidence | Decision |
| --- | --- | --- | --- | --- |
| P0-2026-09-08 | explore / not promoted / not live-ready | 12M/月频/7ETF/整股/现金结算 | [契约](specs/p0-contract.json)、[账户报告](diagnostics/p0-account-study-2026-09-08.md)、[summary](artifacts/summary.json) | 本轮增量 NO-GO；CAGR 3.65% / MDD 14.50%，静态同风险 6.06% / 18.57% |

## Shared Assumptions

- 数据：新抓取原生 Yahoo 日线与分配事件，仅限显式诊断输入；有效日历 2015-12-01 起。
- 账户：2017-02-28 种子 10,000 美元；2017-03-01 至 2026-09-04；2393 个交易日，无外部资金流。
- 成本：每单 max($1,$0.005/股) + 0.5 bps 余量，基础单边 5 bps 不利滑点；现金 0% 利息。
- 执行：过去月末收盘决策；销售 T+3/T+2/T+1 分段、排除银行假日；买入在已结算资金内，整股并保留现金。
- 分配：除息日应收，60 天后现金释放；90 天与 30% 分配预扣敏感性。
- 曝光：全历史复用诊断，2025+ `ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS`。

## Evidence Map

- [规则/成本/评价契约](specs/p0-contract.json)
- [数据启动失败与有效片段补充](specs/data-admissibility.json)
- [执行来源核查](diagnostics/official-execution-sources-2026-09-08.md)
- [首轮报告与净值图](diagnostics/p0-account-study-2026-09-08.md)
- [原生清单与哈希](artifacts/raw-manifest.json) · [全产物指纹](artifacts/hashes.json)
- [导出账本算术核验](artifacts/exported-ledger-arithmetic-audit.json) · [人工可算与真实例子](artifacts/real-trade-and-distribution-checks.json)
- [复现入口](scripts/README.md) · [独立环境](artifacts/environment.json)
