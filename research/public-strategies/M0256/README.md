# M0256：AverageStrategy，BTC现货4h EMA8/21

已完成1个ID的4配置及1买持对照。2023–2024基准收益218.06%、4h最大回撤幅度23.98%、日Sharpe1.799；买持441.87%，没有相对持有优势证据。HYPOTHESIS / explore / DIAGNOSTIC_ONLY / untrusted；严格复现0，未晋级、未实盘。

- [完整逐策略报告](diagnostics/M0256-20261003.md)
- [主账](m0256-core-ledger.md)
- [冻结规格](specs/M0256-first-replay.json)与[exposure](specs/exposure.json)
- [汇总](artifacts/20261003-first-replay/results/summary.json)、[日末基准净值](artifacts/20261003-first-replay/base-nav-light.csv)、[成交](artifacts/20261003-first-replay/results/base-trades.csv)
- [独立验证](artifacts/20261003-first-replay/independent-validation.json)、[因果测试](artifacts/20261003-first-replay/causality-validation.json)、[实际本地恢复](artifacts/20261003-first-replay/local-recovery.json)
- [恢复步骤与公开边界](diagnostics/rebuild-20261003.md)、[许可](ATTRIBUTION.md)、[决策记录](decision-log.md)

源EMA8/21、volume>0、ROI50%、stop−20%均保留，无hyperopt。原框架执行器未运行，历史窗已曝光。已知停市的14:00恢复代理只在合成测试触发，本历史五配置该桶均无单。Graph兼容文件已生成，不等于已绑定或部署。全局登记、远端、Library与Graph集成由协调者处理。
