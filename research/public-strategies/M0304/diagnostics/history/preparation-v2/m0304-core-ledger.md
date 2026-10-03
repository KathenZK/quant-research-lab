# PUBLIC-M0304-STRATEGY002 主账

| 字段 | 当前记录 |
| --- | --- |
| 稳定ID / 家族 | M0304 / PUBLIC-M0304-STRATEGY002 |
| 版本 | M0304-BTCUSDT-5M-PLAN-20261003 |
| 当前状态 | BLOCKED_SOURCE_INPUT，事前计划与合成公式准备 |
| 保真度 / 可信度 | HYPOTHESIS / DIAGNOSTIC_ONLY / trusted=false |
| 策略与框架 | 固定源码与完整属性已核；作者runtime UNKNOWN；仅参考框架默认 |
| 计划窗口 | 2024日历年，2023年12月预热；availability-selected，非OOS |
| 原始输入 | 首CHECKSUM tunnel403；complete source objects=0，raw QA未通过 |
| 实际历史运行 | 策略配置0；对照0；严格复现0 |
| 计划配置 | 4策略配置+1同窗buyhold，均未运行 |
| 执行C0 | 未通过；完整历史执行/账本引擎未实现 |
| 绩效/独立账本 | 不存在；没有Decimal交易核验或历史净值恢复声明 |
| 本地恢复边界 | 仅准备包哈希与合成公式验证可恢复；不等同raw或收益恢复 |
| 晋升/生产 | 否 / 无runner动作 |

证据：[报告](diagnostics/source-and-blocker-report.md)、[计划](specs/pre-run-plan.json)、[源码](specs/source-manifest.json)、[合成](artifacts/synthetic-formula-validation.json)、[阻塞](artifacts/data-recovery-blocker-safe.json)、[决策](decision-log.md)。
