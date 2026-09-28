# 保留产物

本目录只保存BIN-1D-MTCS本轮可审计产物。输入快照是本家族可信API返回帧的留证，不是供其他家族使用的行情事实源。

输入、统计和账户产物分离，避免事件标签被误当账户收益。价格/统计/账户均只对应冻结合同和重复历史，资金费未填0，无实盘许可。

| 阶段 | 入口 | 内容与裁决角色 |
| --- | --- | --- |
| P0可信价格 | [启动汇总](p0-inputs/summary.json)、[帧清单](p0-inputs/frame-manifest.json)、[覆盖](p0-inputs/coverage.csv) | 652个请求、648个返回、4个短历史；每次请求与官方启动收据、保存帧和内容哈希留存 |
| P1固定机会 | [汇总](p1-research/summary.json)、[全部机会](p1-research/opportunities.csv.gz)、[panel清单](p1-research/panel-manifest.json) | 事前信号与未来标签分开，未成熟和已知中断保留 |
| P1描述 | [10组均值](p1-research/point-summary.csv)、[逐币](p1-research/per-asset.csv)、[逐期](p1-research/time-slices.csv)、[贡献](p1-research/contributions.csv) | 逐币/年份/尾部解释用，不从中新增确认赢家 |
| 原IF统计失败 | [原报告](p1-statistics/report.json)、[近似审计](p1-statistics/approximation-audit.csv) | 原46项近似均不合格；区间保留但不用于裁决 |
| 完整算法预验收 | [预验收报告](p1-statistics-exact-parity-r1/report.json) | 原2048组起点、完整比率逐复制对拍；不产生经济推断 |
| 完整统计修复 | [报告](p1-statistics-exact-r1/report.json)、[区间](p1-statistics-exact-r1/intervals.csv)、[裁决](p1-statistics-exact-r1/unit-decisions.csv)、[参考对拍](p1-statistics-exact-r1/reference-parity.csv)、[模拟误差](p1-statistics-exact-r1/monte-carlo-half-audit.csv) | 固定46指标、每块百万次完整重算、60/120日包络；原复制分块、种子/检查点/源码/输入哈希全部留存 |
| P2捕获 | [完成](p2-capture/completed.json)、[持仓](p2-capture/trades.csv.gz)、[分段账户](p2-capture/summary.csv)、[聚合](p2-capture/aggregate.csv)、[权益清单](p2-capture/equity-manifest.json) | 10单元×2成本；659个独立段，13,180账户；资金有限、截尾与非正权益边界明确 |
| 真实复现 | [重建收据](reconstruction-audit.json)、[独立资金审计](p2-independent-audit.json) | 全面板重建、直接算术/截断检查；全持仓和摘要对账、日权益抽查 |
| 路径说明 | [图](path-illustration/continuation-paths.png)、[同队列数据](path-illustration/fixed-cohort-paths.csv)、[收据](path-illustration/receipt.json) | 结果后的描述性图，不增加检验或退出机制 |
| 最终决策 | [机器摘要](decision-summary.json)、[研究报告](../diagnostics/research-report-20260908.md) | 候选/规则未达目标/证据不足及下一步范围 |
| 交付 | [可信消费者初检](consumer-preflight.json)、[正式Lab交付复核](consumer-delivery-check.json)、[测试收据](validation-tests.json)、[交付收据](delivery-verification.json)、[同步清单](sync-manifest.json) | 本家族文件完整性和正式Lab一致性；全仓其他已知门禁错误不冒称PASS |

[研究复现步骤](../scripts/README.md)。完整统计的分块文件是可复核抽样结果而非新的行情数据；保存的panel和API返回帧同样不得替代其他家族的可信启动。
