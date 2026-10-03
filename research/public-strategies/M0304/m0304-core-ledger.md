# PUBLIC-M0304-STRATEGY002 主账

| 字段 | 最新记录 |
| --- | --- |
| 稳定ID / 家族 | M0304 / PUBLIC-M0304-STRATEGY002 |
| origin run / variant | M0304-20261003-calendar2024-v1 / M0304-BTCUSDT-5M-STRATEGY002-LIMIT-20261003 |
| 当前状态 | DIAGNOSTIC_EXECUTED_AND_INDEPENDENTLY_AUDITED，不晋升 |
| 保真度 / 可信度 | HYPOTHESIS / DIAGNOSTIC_ONLY / trusted=false |
| 窗口 | 2024日历年；2023年12月预热；availability-selected，非OOS |
| 数据恢复 | 同源第二次获准尝试成功；39源对象与114336行QA、独立字节重建通过；首403原证据保留 |
| C0 | 12:47:57.712661 UTC冻结；12:50:14.681680 UTC独立审核放行；收益前无历史账户结果 |
| 实际研究计数 | 1策略ID；4预注册配置+1对照；搜索0；严格复现0；clean重复恢复不算新配置 |
| 基准结果 | 总收益−2.1551%，全5m MDD12.8746%，日Sharpe−0.1627，24轮 |
| 同窗buyhold | +115.0304%，全5m MDD32.0211%，95%含费预算，末尾mark |
| 独立真实审计 | 171fills、527040bar marks；Decimal及全bar指标PASS |
| 恢复 | 新复制冻结代码+独立raw重建CSV，22文件一致，summary仅排除RSS |
| 明确保留语义 | exit_profit_only=true，fee-aware严格>0开盘决策门控；trailing_stop=false；限价进出/市价止损 |
| 结论 | 本窗口全部预注册策略配置亏损，无收益优势证据；不因高胜率晋升 |
| 原作者/PIT/finality/tradability | 未证明；不作为live-ready、严格复现或OOS证据 |
| 生产/Graph | 无runner动作、无自动Graph导入/绑定/部署 |

证据：[最新报告](diagnostics/execution-v1-report.md)、[冻结协议](specs/execution-v1/protocol.json)、[完整结果](artifacts/execution-v1/summary.json)、[独立审核](artifacts/execution-v1/independent-historical-ledger-audit.json)、[恢复](diagnostics/execution-v1-recovery.md)。

[最初阻塞主账原字节](diagnostics/history/preparation-v2/m0304-core-ledger.md)与[原manifest](diagnostics/history/preparation-v2/publication-manifest-preparation-v2.json)保留。历史preparation-pin记录当时路径/字节，不代表后来当前入口未变化；执行C0和原冻结代码/证据不改。
