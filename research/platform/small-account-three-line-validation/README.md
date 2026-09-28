---
research_classification: diagnostic_topic
---
# 10,000 美元账户三方向首轮验证

本主题整合三条独立研究，不建立组合策略身份，不将各自 10,000 美元的账户相加。

- 研究日期：2026-09-08。
- 用户条件：总本金约 10,000 美元，可接受 20%–30% 回撤，允许非加密市场；该区间不是未来回撤保证。
- 完成定义：A 跨市场慢速多头/现金、B TPSA 多头账户、C BTC/ETH 两种 carry 均完成实际验证或给出有证据的具体阻塞，独立验收后给出唯一下一优先项。
- 边界：历史复用诊断；不宣称新盲 OOS、不恢复旧封存研究、不授权实盘或生产变更。

## 入口

- [最终结果、同本金比较与唯一下一优先项](diagnostics/three-line-results-2026-09-08.md)
- [根代理独立验收与重放入口](diagnostics/independent-acceptance-2026-09-08.md)
- [事前比较及独立验收契约](specs/program-contract-2026-09-08.md)
- [决策记录](decision-log.md)
- [上下文来源清单](artifacts/context-source-manifest.json)
- [机器比较](artifacts/comparison.json) · [独立验收结果](artifacts/independent-acceptance.json)
- [下一补证任务边界](specs/next-priority-static-account.md)

三方向首轮完成；无合格候选。A 12M趋势层增量失败，B固定账户NO-GO且净数据/执行阻塞，C未验证可执行净利润。唯一下一优先项为A同池静态低频账户的发行人分配与执行准入补证；当前静态对照不自动晋升。

各家族入口：[A](../../asset-portfolios/1d-small-account-slow-trend/README.md)、[B](../../asset-portfolios/1d-tpsa-long-account/README.md)、[C](../../asset-portfolios/8h-btceth-small-account-carry/README.md)。每个账本独立以10,000美元开始，历史复用、数据边界和运行权限仍按各家族材料判断。
