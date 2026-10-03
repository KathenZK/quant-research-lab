# M0274 · GodStra · 原生12h阻塞研究包

**状态：BLOCKED / HYPOTHESIS / DIAGNOSTIC_ONLY。真实策略回测0次，严格复现0条。收益、交易数、净值及买持均为未计算，不是零收益/零交易结论。**

这是公开catalog原ID M0274的独立研究，不新增策略ID，不改作者阈值、不补缺失行情、不缩短评价窗。

- [独立中文策略报告](M0274-report.md)：规则、原理、假设、数据QA、因果反例及失败场景
- [主账](M0274-core-ledger.md)与[决策日志](decision-log.md)
- [原规则](specs/source-rules-v1.json)、[收益前计划](specs/pre-performance-plan-v1.json)、[阻塞诊断冻结](specs/blocked-diagnostic-freeze-v1.json)、[曝光记录](specs/exposure-v1.json)
- [输入逐对象摘要与独立QA](artifacts/partial-input-independent-qa-v1.json)、[完整输入门禁](artifacts/input-gates-v1.json)、[下载失败](artifacts/capture-failure-v1.json)
- [合成因果反例](artifacts/synthetic-causality-v1.json)、[独立复核一致性](artifacts/independent-synthetic-comparison-v1.json)、[当前结果状态](artifacts/results-status-v1.json)
- [重建及恢复说明](REPRODUCE.md)、[离线恢复回执](artifacts/offline-recovery-v1.json)、[Graph兼容记录](artifacts/graph-record.json)
- [代码许可](CODE-LICENSE.md)与[数据归因及使用限制](DATA-LICENSE.md)分开说明

## 两项独立阻塞

1. 计划25个月原生BTCUSDT现货12h输入，已抓取并独立验证2022-12至2024-01的14月854行。2024-02 ZIP访问被拒，尚缺670行。完整窗口QA及第二轮网络重建没有通过
2. 保留原样的 ta 0.11.0 `add_all_ta_features(fillna=True)` 在确定性合成输入中有11个特征随未来追加而改写历史值，违反本次冻结的完整管线因果门控。未删除这些列或修改初始化。选用KST列的合成变化发生在预热内，不据此断言真实评价信号受污染

完整第三方源码、原始行情、网页全文、大曲线、私有Graph detail均不在公开包内。`publication-manifest.json`逐文件列出公开候选及SHA256；远端保存与异地恢复由协调者另行验收，本地文件不代表已备份。
