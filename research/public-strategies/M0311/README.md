# M0311 · TechnicalExampleStrategy

research_classification: strategy_family  
家族：PUBLIC-M0311-TECHNICAL-EXAMPLE-CMF；分类：**ADAPTED / ADAPTED_EXECUTION_PROXY**；状态：失败诊断，不晋升。

一句话：CMF21 为负时持有、转正时退出，附加 1% ROI 与 5% 止损；原限价订单改为明确声明的下一开盘／市价式风险退出代理。

2024 BTCUSDT 现货：4 个预定策略配置与 1 个同窗买持，严格复现 0。基础代理收益 −99.995765%，零手续费配置仍为 −75.217829%；不是原限价策略的已证实收益。源码信号、独立账户、因果、本地一次恢复通过，均不意味着策略通过。

- [独立中文报告](diagnostics/M0311-20261003.md) · [主账](m0311-core-ledger.md) · [决策记录](decision-log.md)
- [冻结协议](specs/M0311-first-replay.json) · [公开来源说明](specs/source-description.json) · [来源哈希](specs/source-manifest.json)
- [复现入口](diagnostics/rebuild-20261003.md) · [结果摘要](artifacts/20261003-first-replay/results/summary.json)
- [Graph 兼容记录](artifacts/20261003-first-replay/graph-record.json) · [许可](ATTRIBUTION.md)

原始行情、完整 5m 净值和全部成交均私有；公开成交文件明确为样本。未更新全局索引、未部署网站、未声明远端备份成功。
