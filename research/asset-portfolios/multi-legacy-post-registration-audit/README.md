---
research_classification: diagnostic_topic
---

# 早期策略落档后盈利复核

回答“当时确定的策略，之后继续按原规则运行还能否赚钱”。本主题比较不同家族最后落档的规则，不建立新策略版本，也不改变任何原策略或生产实例。

- **全仓定稿后排序（2026-09-11）**：[三榜交互页面](artifacts/repository_ranking_20260911/index.html) · [完整报告](diagnostics/repository-ranking-20260911.md) · [全仓清单及未入榜原因](diagnostics/repository-coverage-20260911.md)。清点133个家族/主题，另列公开100条；完成54家族117方案，新增72方案。已登记最终版24方案中8正、15负、1无交易，Keltner V3收益第一。未登记观察及同收盘成交诊断可另选查看，不能据其高收益称作已采纳最终版。月度LS3整池输入检查失败，仍无后续账户结果；本页不宣称每个目录均已完成回测。
- [本次计算约定](specs/repository-post-freeze-ranking-20260911.md) · [结果对应及独立账户计算复核](artifacts/repository_ranking_20260911/verification.json)。复核仅证明所列检查，不代表所有原引擎、资金费完整性或实盘执行已经验证。
- **结论更正：撤回助手此前给出的整份主观研究优先级。** Keltner V3在登记主表累计收益及本轮共同窗口两种基础情景中均排第一，不能因为未声明的低回撤偏好将其笼统降级。已知MMTF参数错误、CC执行歧义和各类未核准项分别列在[结论复核与更正](diagnostics/conclusion-review-20260911.md)。旧报告保留历史内容，涉及评价时以更正说明为准。
- [早期版与最终版同段比较](diagnostics/iteration-comparison-20260911.md)：14组对照，7组收益提高、6组下降、1组持平；重点展开HYPE 15分钟10/8反转的5个版本。共101条预定情景结果，保存原仓位和高滑点对照。
- [本轮全部情景](artifacts/iteration_comparison_20260911/all_results.csv) · [14组固定对照](artifacts/iteration_comparison_20260911/paired_results.csv) · [本轮比较规则](specs/iteration-comparison-20260911.md)。
- [9月10日结果报告](diagnostics/report-20260910.md)：保留当时完整对照、测试起点、成本和限制；其中HYPE 15m MMTF的−14.22%已更正为−14.15%，见[更正说明](diagnostics/correction-mmtf-rvol-20260911.md)。
- [研究规则](specs/contract-20260910.md)：版本选择、日期、数据、初始空仓与期末结算。
- [全部结果](artifacts/all_results.csv) · [覆盖清单](artifacts/coverage_inventory.json)。
- [价格与资金费输入审计](artifacts/inputs/manifest.json)；[辅助官方标记价格](artifacts/inputs/marks/manifest.json)。
- [脚本说明](scripts/README.md) · [决策记录](decision-log.md)。

收益包含原手续费和滑点，现有资金费资料调整值仍为估计。日期之后的回放不是实盘成交记录，也没有据此启停服务。
