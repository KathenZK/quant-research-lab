# Multi-Asset-1D-Small-Account-Slow-Trend

- 完整家族名：`Multi-Asset-1D-Small-Account-Slow-Trend`；别名：`XA-1D-SAST`。
- 交易面：7 只美元 ETF，月末决策、下个交易时点成交，初始本金 10,000 美元，整股、多头/现金、无账户融资。
- 机制：12 个月总回报正向过滤；事前同池 10% 波动预算只减仓，月频更新；固定等权、同风险静态与 SPY 对照。
- 边界：独立于旧 EWMAC/传统期货 TSMOM 家族；不继承旧收益、相关性或空头危机保护。PDBC 基金收益不能冒充逐合约期货表现。
- 主状态：`explore / not promoted / not live-ready`；未登记可投资版本、未建立 runner 实例。
- 本轮裁决：`NO_GO_PREDECLARED_ECONOMIC_INCREMENT`。12M 层 CAGR 3.65%、回撤 14.50%，对照同风险静态 CAGR 6.06%、回撤 18.57%；风险改善伴随 2.41 个百分点年化收益损失，未达到事前允许的 1 个百分点上限。只否定本轮趋势增量，不否定跨市场慢组合。

## 入口

- [核心主账](xa-1d-sast-core-ledger.md) · [决策日志](decision-log.md)
- [首轮完整报告](diagnostics/p0-account-study-2026-09-08.md)
- [原冻结契约](specs/p0-contract.json) · [无收益曝光的数据可用性补充](specs/data-admissibility.json) · [曝光记录](specs/exposure-log.md)
- [官方产品/执行来源](diagnostics/official-execution-sources-2026-09-08.md)
- [产物清单](artifacts/README.md) · [一键复现](scripts/README.md)

共同有效数据为 2015-12-01 至 2026-09-04；账户从 2017-03-01 开始，另含 2017-02-28 的 10,000 美元种子行。早期 PDBC 33 个零成交日使原请求窗口启动失败，未用回填/删标的解决。全部历史为复用诊断，2025+ 不是新盲 OOS。
