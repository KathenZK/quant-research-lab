# M0275 · Heracles · BTC现货4h

**结论：本次固定假设回放跑通并经独立复核，但没有显示优于同标的买入持有的证据。**

- 原目录稳定ID：M0275；原策略：Mablue / Masoud Azizi 的 Heracles，非其他 Keltner 策略
- 分类：`HYPOTHESIS`；输入 `DIAGNOSTIC_ONLY`、非 trusted；严格复现数 **0**，未晋升、未实盘
- 评价：2023-01-01 至 2025-01-01（UTC，末端不含）；预热2022年12月
- 基础：10万USDT、95%含买入费预算、单仓做多、8bps单边手续费、2bps单边滑点、下一根开盘代理成交
- 策略净收益 **+287.62%**，最大回撤 **35.59%**，日收益 Sharpe **1.729**；同仓位/成本买持 **+441.87% / 29.65% / 2.006**
- 源码参数 `buy_params` 的shift为 **15/9**；原分钟ROI **0:59.8%、644:16.6%、3269:11.5%、7289:0%**，价格止损 **−25.6%**
- 两大执行差异：AgeFilter100天采用历史存在证据的单币代理；分钟ROI在可观察4h开盘选档，桶内跨档延至下一有效开盘

## 从这里读

1. [独立研究报告](diagnostics/M0275-20261003.md)：规则、理论、结果、失败场景与边界
2. [主账](m0275-core-ledger.md) / [决策日志](decision-log.md)
3. [冻结协议](specs/protocol.json) / [曝光登记](specs/exposure.json) / [C1指纹](artifacts/C1-freeze-receipt.json)
4. [轻量指标](artifacts/results/metrics.csv) / [月末归一化净值](artifacts/results/month-end-nav-light.csv) / [基础交易账](artifacts/results/base-trades.csv)
5. [独立完整决策审核](artifacts/independent-real-result-audit.json) / [风险时钟审核](artifacts/independent-risk-evidence-audit.json) / [恢复回执](artifacts/local-recovery.json)
6. [重建说明](diagnostics/rebuild-20261003.md) / [Graph兼容记录](artifacts/graph-record.json) / [公开文件清单](publication-manifest.json)
7. [许可与归因](ATTRIBUTION.md)：软件与Binance数据衍生内容分别处理

C0来源输入、C1收益前冻结、C2校验均完成。C3远端保存/读回由协调者另行办理；本地恢复不是异地备份。只计1个策略ID、1个固定策略实例、4个策略配置和1个买持对照，敏感性配置不算新策略。
