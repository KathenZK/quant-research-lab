---
research_classification: diagnostic_topic
---

# 早期策略落档后盈利复核

回答“当时确定的策略，之后继续按原规则运行还能否赚钱”。本主题比较不同家族最后落档的规则，不建立新策略版本，也不改变任何原策略或生产实例。

- [最新：早期版与最终版同段比较](diagnostics/iteration-comparison-20260911.md)：14组对照，7组收益提高、6组下降、1组持平；重点展开HYPE 15分钟10/8反转的5个版本。共101条预定情景结果，保存原仓位和高滑点对照。
- [本轮全部情景](artifacts/iteration_comparison_20260911/all_results.csv) · [14组固定对照](artifacts/iteration_comparison_20260911/paired_results.csv) · [本轮比较规则](specs/iteration-comparison-20260911.md)。
- [9月10日结果报告](diagnostics/report-20260910.md)：保留当时完整对照、测试起点、成本和限制；其中HYPE 15m MMTF的−14.22%已更正为−14.15%，见[更正说明](diagnostics/correction-mmtf-rvol-20260911.md)。
- [研究规则](specs/contract-20260910.md)：版本选择、日期、数据、初始空仓与期末结算。
- [全部结果](artifacts/all_results.csv) · [覆盖清单](artifacts/coverage_inventory.json)。
- [价格与资金费输入审计](artifacts/inputs/manifest.json)；[辅助官方标记价格](artifacts/inputs/marks/manifest.json)。
- [脚本说明](scripts/README.md) · [决策记录](decision-log.md)。

收益包含原手续费和滑点，现有资金费资料调整值仍为估计。日期之后的回放不是实盘成交记录，也没有据此启停服务。
