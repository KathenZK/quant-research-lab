# M0293：ReinforcedAverageStrategy，EMA 交叉与高周期均线过滤

已在执行端完成1个稳定ID、4个预定配置及1个买持对照，待协调者独立验收。基准2023–2024收益55.73%、4h收盘最大回撤28.85%、日Sharpe0.903；买持441.87%。额外延迟一根收益101.16%，显示执行时点敏感，不能事后替换基准。HYPOTHESIS / explore / DIAGNOSTIC_ONLY / untrusted；严格复现0，未晋级。

- [完整逐策略报告](diagnostics/M0293-20261003.md)、[主账](m0293-core-ledger.md)、[决策记录](decision-log.md)
- [冻结契约](specs/M0293-first-replay.json)、[收益前曝光](specs/exposure.json)、[来源与许可](ATTRIBUTION.md)
- [汇总](artifacts/20261003-first-replay/results/summary.json)、[731点日末净值](artifacts/20261003-first-replay/base-nav-light.csv)、[逐笔成交](artifacts/20261003-first-replay/results/base-trades.csv)
- [原始类校验](artifacts/20261003-first-replay/original-source-validation.json)、[独立账户](artifacts/20261003-first-replay/independent-validation.json)、[因果性](artifacts/20261003-first-replay/causality-validation.json)、[恢复](artifacts/20261003-first-replay/local-recovery.json)
- [恢复指南](diagnostics/rebuild-20261003.md)、[Graph兼容记录](artifacts/20261003-first-replay/graph-record.json)

仅离线复用已审4h行情，新增行情请求0。前413根评价K线因48h SMA50预热不足保留NaN、不入场，评价起点不后移。原ID保留，各成本/延迟配置不计新策略。Graph文件尚未绑定活动定义、导入或部署。
