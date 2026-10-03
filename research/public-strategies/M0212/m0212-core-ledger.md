# M0212-VOLUME-CONTRACTION 主账

- 稳定ID M0212，家族M0212-VOLUME-CONTRACTION；Binance BTCUSDT spot / UTC1d，量缩下跌后短时持有。
- 规则归因来自协调者合法读取原表；X原链接正常读取为空，非全文验证。日频BTC、时间锚、EMA种子、下一开盘和仓位为假设。
- 当前状态 `explore / not promoted / not live-ready`，无runner/生产交接。

| 版本 | 身份和状态 | 实际结果 | 决策 |
| --- | --- | --- | --- |
| M0212-BTCUSDT-VOLUME-CONTRACTION-NEXTOPEN-20261003 | 初版决策日锚，额外延迟历史诊断，frozen | 基准0.68%，回撤20.75% | 原样保留，不作为主规则解释 |
| M0212-BTCUSDT-VOLUME-CONTRACTION-EXECUTION-ANCHOR-V2-20261003 | 执行日锚标准化，explore | 基准29.46%，回撤22.72%；lag2为−12.29% | 不晋升，成交时点敏感且落后买持 |

合计1研究ID、2冻结实现、8策略配置首次执行、2基准；恢复重跑不新增研究执行数。无严格复现，无未曝光OOS。四组配置均在各自查看结果前登记；V2是在V1结果已曝光后按协调者时间语义纠正，不能隐藏前次搜索。

详细逻辑/数据/成本见[规格](specs/M0212-execution-anchor-v2.json)，判断、失败场景和恢复命令见[报告](diagnostics/M0212-20261003.md)。下一关口：作者原文、时间锚与实际执行证明、独立未曝光样本；不得在当前曲线上追调退出天数冒充原策略。
