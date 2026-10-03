# M0315 · UniversalMACD

research_classification: strategy_family  
稳定 ID：M0315；家族：PUBLIC-M0315-UNIVERSAL-MACD；状态：HYPOTHESIS / explore，未晋升。

一句话：当 5 分钟快慢 EMA 的比值落入原作者给出的负区间时买入，保留原代码为空的卖出区间，靠递减 ROI 和宽止损退出。

2024 年 BTCUSDT 现货诊断：4 个预定策略配置、1 个同窗买持，严格复现 0。基准配置 +8.3399%、全 5 分钟收盘净值最大回撤 10.0628%，7 笔完整交易；同窗买持 +115.0304%。账户独立核验与本地离线恢复通过，远端备份未验证。

- [中文完整研究报告](diagnostics/M0315-20261003.md)
- [主账](m0315-core-ledger.md) · [决策记录](decision-log.md)
- [冻结协议](specs/M0315-first-replay.json) · [来源清单](specs/source-manifest.json) · [曝光记录](specs/exposure.json)
- [离线重建步骤](diagnostics/rebuild-20261003.md) · [许可与来源](ATTRIBUTION.md)
- [结果摘要](artifacts/20261003-first-replay/results/summary.json) · [Graph 兼容记录](artifacts/20261003-first-replay/graph-record.json)

原始行情、完整 5 分钟净值、信号和原作者源码保留在私有恢复材料；仓库仅保留经审轻量证据。Graph 文件是集成输入，未绑定定义、未导入网站、未部署。
