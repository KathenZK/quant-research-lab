# M0317 mabStra 原默认参数诊断

本条目保留原6973目录的稳定ID M0317，作者 Masoud Azizi（Mablue）。仅研究 BTCUSDT 现货原生4h，评价2023至2024年，2022年12月只作指标预热。

结论：原默认参数产生几乎持续入场的条件，指标卖出区间自相矛盾，不能据此还原作者要求超优化后的策略。主情景净收益304.99%、最大4h收盘回撤32.71%、日Sharpe1.787，均落后相同95%资金预算的买持。保留 `HYPOTHESIS / DIAGNOSTIC_ONLY / strict_reproductions=0`，不晋升。

## 核心区别

- 四位小数的实际默认值为买入 `(0.2950,2.2545)`、卖出 `(2.8144,1.5459)`，全部严格不等式；不交换阈值，不钳制到超优化范围，不调参
- SMA使用收盘价，周期7、14、28。评价4386根K线全部满足买入条件，卖出条件全假
- 保留ROI分钟阶梯0:59.8%、644:16.6%、3269:11.5%、7289:0，以及固定止损−12.8%；源码未覆盖trailing，核实框架默认False
- 原类未配置订单类型，框架默认limit/GTC。本诊断明确另加market成交代理、95%含费预算、8bps单边费、2bps单边不利滑点、次根开盘执行，不声称原生limit队列复现
- ROI只在可观察4h开盘重选档位，档内保持；绝不用档位生效前的全根最高价。2023年3月24日12:00桶在14:00恢复开盘代理成交，08:00桶风险区间截止11:26:59.999

## 文档入口

- [独立研究报告](diagnostics/M0317-default-replay-report.md)
- [主账](M0317-core-ledger.md)与[决策日志](decision-log.md)
- [冻结协议](specs/protocol.json)、[样本曝光](specs/exposure.json)、[源码溯源](specs/source-manifest.json)
- [复现步骤](REPRODUCE.md)与[许可归属](ATTRIBUTION.md)
- [结果摘要](artifacts/results/summary.json)、[25点月末净值](artifacts/results/month-end-nav-light.csv)、[201条主情景成交](artifacts/results/base-trades.csv)
- [独立验证](artifacts/independent-real-result-audit.json)、[本地恢复](artifacts/local-recovery.json)、[轻量Graph记录](artifacts/graph-record.json)
- 公开文件以 [publication-manifest.json](publication-manifest.json) 的 `public_allowlist` 为准。该manifest自排除，但本身也是需要保存的公开候选

本地C2是冻结诊断实例的验证，不代表全框架、PIT、严格最终性、订单簿可成交性或OOS通过。C3远端保存及回读由唯一协调者执行。大曲线、raw行情、完整第三方源码和私有Graph detail不纳入公开清单。
