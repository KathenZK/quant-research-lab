# 结果与核对记录

先读[中文报告](../diagnostics/research-report-20260909.md)。本目录包含本轮已完成的原始结果、复算证据及事后解释，不能把解释表当作新策略验证。

| 目录或文件 | 内容 |
| --- | --- |
| [p0-inputs/](p0-inputs/) | 652请求、648有效资产的新日线帧、数据入口返回、连续段与质量核对、内容指纹 |
| [research-20260909/](research-20260909/) | 生产结果：面板、1658候选、19896单位机会、逐日记录、12账户、4档配对表、联合统计、完成哈希清单 |
| [interpretation/](interpretation/) | 从保留产物导出的均值/胜率/年份与最高贡献删除解释；不重跑规则 |
| [capture-gap-explanation/](capture-gap-explanation/) | 等待分解、最大回撤持仓路径与说明；结果产生后的诊断 |
| [funding/](funding/) | 现有资金费的完整窗口检查、真实价格与代理价格分列、事件现金和覆盖；不是全历史账户净收益 |
| [audit-research-20260909/receipt.json](audit-research-20260909/receipt.json) | 独立重建全部候选、机会、12账户与主要统计的全量收据 |
| [statistics-independent.json](statistics-independent.json) | 两种块长各10000次显式抽样的独立核对 |
| [funding-independent-verification.json](funding-independent-verification.json) | 资金费逐项独立核对 |
| [pre-result-tests-final.log](pre-result-tests-final.log) | 收益计算前最终83项测试和48个子项通过；此前日志保留历史状态 |
| [trusted-consumer-final-check-20260909/receipt.json](trusted-consumer-final-check-20260909/receipt.json) | 新脚本精确入口登记与定向检查；全库仍有5项原有其它家族失败，不能称全库通过 |
| [trusted-consumer-plot-final-check-20260909/receipt.json](trusted-consumer-plot-final-check-20260909/receipt.json) | 包括最后绘图脚本的登记复查；本轮0项失败、原5项未变，旧收据不覆盖 |

文件完整性以[生产完成清单](research-20260909/completed.json)、[计算前清单](../specs/computation-lock.json)、资金费与独立审计各自清单为准。本文及中文解释报告不在固定生产代码中。真实资金费缺失不填零；正常空仓收益0与未知损益分开。
