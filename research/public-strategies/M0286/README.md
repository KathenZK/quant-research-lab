# M0286：MultiMa，多周期 TEMA 排列

已完成 1 个稳定 ID、4 个预定配置和 1 个买持对照。基准 2023–2024 收益 38.13%、4h 收盘最大回撤 10.67%、日 Sharpe 1.147，22 次完整交易；同口径买持 441.87%。HYPOTHESIS / explore / DIAGNOSTIC_ONLY / untrusted，严格复现 0，未晋级、未实盘。

- [独立逐策略报告](diagnostics/M0286-20261003.md)、[主账](m0286-core-ledger.md)、[决策记录](decision-log.md)
- [冻结规格](specs/M0286-first-replay.json)、[曝光记录](specs/exposure.json)、[来源和许可](ATTRIBUTION.md)
- [汇总](artifacts/20261003-first-replay/results/summary.json)、[日末轻量净值](artifacts/20261003-first-replay/base-nav-light.csv)、[逐笔成交](artifacts/20261003-first-replay/results/base-trades.csv)
- [原始类校验](artifacts/20261003-first-replay/original-source-validation.json)、[独立账户](artifacts/20261003-first-replay/independent-validation.json)、[因果性](artifacts/20261003-first-replay/causality-validation.json)、[恢复](artifacts/20261003-first-replay/local-recovery.json)
- [重建指南](diagnostics/rebuild-20261003.md)、[Graph 兼容记录](artifacts/20261003-first-replay/graph-record.json)

源码参数 4/15/12/68、ROI 分钟表、−34.5% 止损及无追踪止损保留。31 日预热不足以覆盖长 TEMA，NaN 和部分卖出比较可用的行为保留；分钟 ROI 采用事先冻结的开盘阶梯近似，未使用原框架执行器。Graph 文件尚未绑定活动定义、导入或部署。
