# 产物索引

本轮结论只使用修复后的运行。完整解释见[最终报告](../diagnostics/final-report-20260908.md)，生成命令、依赖及锚点见[复现说明](../scripts/README.md)。二进制与大表留在本地忽略目录，没有加入普通Git。

| 阶段 | 可审计入口 | 用途 |
| --- | --- | --- |
| 启动 | [目标激活证明](goal-activation.json)、[源码/目录状态](startup-provenance.json) | 用户目标、正式Lab与worktree边界 |
| P0 | [输入汇总](p0-inputs-20260908/summary.json)、[覆盖](p0-inputs-20260908/coverage.csv)、[连续段](p0-inputs-20260908/segments.csv)、[帧清单](p0-inputs-20260908/frame-manifest.json) | 874代码、可信入口报告、返回帧与内容SHA；原请求和报告在该运行目录 |
| 参考重现 | [对拍报告](reference-parity-20260908-r1/report.json)、[2928项差异](reference-parity-20260908-r1/parity.csv) | 244币×4基线×3成本 |
| 开发锁 | [结果](p1-development-20260908-r1/results.csv)、[选择锁](p1-development-20260908-r1/selection-lock.json)、[锁字段澄清](p1-development-20260908-r1/selection-lock-clarification.json) | 74币、10候选；C3最佳失败对照 |
| 主评估 | [逐币窗口结果](p1-evaluation-20260908-r1/results.csv)、[全部逐笔](p1-evaluation-20260908-r1/trades.csv.gz)、[近期切片](p1-evaluation-20260908-r1/recent-slices.csv)、[完成标志](p1-evaluation-20260908-r1/completed.json) | 主窗、年度、隔离组、全部可用连续段；main-paths内保留全部206份路径 |
| P2回放 | [17配置声明](p2-applicability-20260908-r2/started.json)、[逐币结果](p2-applicability-20260908-r2/results.csv)、[逐笔](p2-applicability-20260908-r2/trades.csv.gz)、[月收益](p2-applicability-20260908-r2/monthly-returns.csv.gz) | 八筛选、邻域、纯方向、半仓、延迟；真实切换与费用 |
| P3统计 | [主广度](p3-statistics-20260908-r1/main-breadth.csv)、[人群裁决](p3-statistics-20260908-r1/population-verdict.json)、[隔离验证](p3-statistics-20260908-r1/isolated-validation.csv) | 相同分母、比例与区间 |
| P3增量 | [反手配对](p3-statistics-20260908-r1/reversal-paired.csv)、[筛选敏感性](p3-statistics-20260908-r1/filter-and-sensitivity.csv)、[18项系数](p3-statistics-20260908-r1/controlled-feature-associations.csv)、[拆分](p3-statistics-20260908-r1/split-and-regression-audit.json) | 特征、方向与年份控制；筛选表默认比较双向C3 |
| P3分解 | [方向/状态](p3-statistics-20260908-r1/direction-regime-trades.csv)、[块区间](p3-statistics-20260908-r1/asset-month-block-bootstrap.csv)、[八股全部结果](p3-statistics-20260908-r1/eight-stock-short-history.csv) | 解释层、时间依赖与股票短窗 |
| P5补充 | [同方向筛选对照](p5-final-evidence-20260908/short-filter-controlled-comparison.csv)、[配对块区间](p5-final-evidence-20260908/short-filter-block-bootstrap.csv)、[严格失败项](p5-final-evidence-20260908/strict-gate-failures.csv)、[年度/成本/集中度](p5-final-evidence-20260908/C3-annual-cost-direction-concentration.csv)、[最终证据验算](p5-final-evidence-20260908/completed.json) | 剥离仅做空贡献，不新增候选或重选 |
| 资金 | [范围报告](funding-scope-20260908/report.json)、[逐币状态](funding-scope-20260908/symbol-funding-status.csv) | 完整日历及身份未验证，不补零 |
| 官方来源 | [HTTP收据](official-source-review/official-sources-receipts.json)、[SEC收据](official-source-review/sec-eight-stock-receipts.json)、[交易所元数据](official-source-review/exchangeInfo-20260908.json) | 当前身份与官方发布来源，非历史PIT库存 |
| 股票基本面 | [发行人](stock-fundamentals-availability-20260908/issuer-coverage.csv)、[按时可用字段](stock-fundamentals-availability-20260908/daily-pit-availability.csv)、[汇总](stock-fundamentals-availability-20260908/report.json) | 原accession接收时间及修订边界 |
| 图形 | [交易路径HTML](p4-trade-paths-20260908/MA7多空趋势_交易路径.html)、[载荷校验](p4-trade-paths-20260908/verification.json)、[浏览器/语法记录](p4-trade-paths-20260908/browser-and-syntax-check.json) | 14案例197笔；视觉验收受限 |
| 验算 | [30项测试](engine-tests-final.txt)、[独立每日账本报告](final-replay-verification-20260908/report.json)、[逐项误差](final-replay-verification-20260908/daily-ledger-checks.csv) | 因果、费用、本金、mask、统计与真实前缀 |
| 源码与归档 | [计算源码清单](source-snapshots/20260908-computation/manifest.json)、[最终核验](delivery-20260908.json)、[消费者检查](consumer-check-final.json)、[同步清单](sync-manifest.json) | 原计算版本、最终源文件与交付完整性 |

## 保留的失败尝试

- [首次真实参考失败](reference-parity-console.txt)：浮点求和改变严格MA等值边界；修复后才接受结果。
- [初次开发无效标记](p1-development-20260908/INVALIDATED.json)、[初次评估无效标记](p1-evaluation-20260908/INVALIDATED.json)、[首次筛选](p2-applicability-20260908/INVALIDATED.json)、[筛选r1](p2-applicability-20260908-r1/INVALIDATED.json)：全部保留，禁止解释为有效结果或额外参数搜索。
- 首次筛选月表拼写、统计依赖缺失、segment-id类型问题的控制台与测试输出保留；[修复说明](../diagnostics/implementation-repair-20260908.md)给出前后边界。
- p3-statistics-r1内早期临时生成的short-filter-controlled-comparison只作历史留证；正式可复现方向对照以P5表和final_evidence.py为准。
