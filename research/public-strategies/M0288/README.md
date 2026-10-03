# M0288：PatternRecognition 日线形态策略

已完成 1 个稳定 ID、4 个策略配置与 1 个买持对照，并从重新下载的数据独立恢复出 10 个逐字节一致文件。严格复现 0；状态为 HYPOTHESIS / explore / DIAGNOSTIC_ONLY / not promoted。

BTC/USDT 现货 2023–2024 诊断：基准配置收益 180.61%，日末最大回撤 23.12%，22 笔往返；买持收益 441.55%。额外延迟一天后收益降至 117.10%，不支持优于持有或直接部署的结论。

- [完整中文报告](diagnostics/M0288-20261003.md)
- [主账](m0288-core-ledger.md)与[决策记录](decision-log.md)
- [运行前冻结规格](specs/M0288-first-replay.json)、[源码预审检查点](specs/source-preflight-checkpoint.json)
- [结果汇总](artifacts/20261003-first-replay/summary.json)、[成交](artifacts/20261003-first-replay/base-trades.csv)、[日净值](artifacts/20261003-first-replay/base-daily-nav-light.csv)
- [独立验证](artifacts/20261003-first-replay/independent-validation.json)与[重新下载恢复验证](artifacts/20261003-first-replay/recovery-validation.json)
- [重建操作](diagnostics/rebuild-20261003.md)、[许可与公开边界](ATTRIBUTION.md)

原作者类未修改，使用完整 Freqtrade 2026.9 参考引擎；作者原始运行环境和标的池未知。Graph 结构化记录已准备，定义绑定、活动数据库导入和站点部署均未执行。全局索引、allowlist、远端保存由协调者统一处理。
