# 三方向结果复核证据（2026-09-09）

本目录属于 `diagnostic_topic`，保存针对已完成三方向任务的独立复核，不登记策略、不改变原家族裁决、不构成实盘或运行授权。总说明见 [结果独立复核](../../diagnostics/three-line-independent-review-2026-09-09.md)。

原冻结输入与结果仍在 `/Users/ZK/.codex/worktrees/5f41/quant-strategy-lab`；原 TPSA 输入仍在主仓库原家族，精确路径和指纹见 [来源记录](retained-accountants/verification.json)。本次没有迁移三家族或改写其清单。下列分项报告为独立审计员当次报告的原样归档，其中 `/tmp` 为实际执行地点；长期证据已经对应保存到本目录及脚本目录，不依赖临时文件继续存在才能阅读结论。

| 内容 | 留存位置 |
| --- | --- |
| A 独立报告 | [a-independent-review.md](a-independent-review.md) |
| B 独立报告 | [b-independent-review.md](b-independent-review.md) |
| C 独立报告 | [c-independent-review.md](c-independent-review.md) |
| 原交付清单、10份上下文及已有核验脚本重跑记录 | [verification.json](retained-accountants/verification.json) |
| A 原生数据、信号、12账户独立核验 | [independent-checks.json](a/independent-checks.json) |
| A 单次 VNQ 开关敏感度 | [boundary-sensitivity.json](a/boundary-sensitivity.json)，两个账户全账在 `a/trend_12m_risk10/` 与 `a/trend_12m_boundary_sensitivity/` |
| B 模型、10账户和逐事件复算摘要 | [review_recalculation.json](b/review_recalculation.json) |
| B 原标签日期权重与年度原始计数 | [admission_decomposition.json](b/admission_decomposition.json) |
| B 24,141 条事件及未解析状态 | [independent_event_shadow.csv](b/independent_event_shadow.csv) |
| B 月度入场分解 | [monthly_admission_diagnostic.csv](b/monthly_admission_diagnostic.csv) |
| B 三账户逐事件对应 | [主账户](b/ML_p040_admitted_join.csv)、[全部事件对照](b/ALL_EVENTS_admitted_join.csv)、[哈希对照](b/HASH20_EVENTS_admitted_join.csv) |
| C 原生资金费、报价、币量、mark high 与抓取轮次独立复核 | [review_results.json](c/review_results.json) |
| 本次新增报告、脚本及证据指纹 | [review-manifest.json](review-manifest.json) |

本次脚本按实际执行内容原样归档：

- [只读验证原交付并重定向已有核验输出](../../scripts/three-line-review-20260909/verify_frozen_delivery.py)。
- [A 全账户独立核验](../../scripts/three-line-review-20260909/a_check_a.py)、[A 隔离单点敏感度](../../scripts/three-line-review-20260909/a_boundary_sensitivity.py)。
- [B 模型/账户/逐事件复算](../../scripts/three-line-review-20260909/b_recalculate.py)、[B 日期分解](../../scripts/three-line-review-20260909/b_admission.py)。
- [C 原生金额复算](../../scripts/three-line-review-20260909/c_recalculate.py)。

脚本输入是上述精确冻结目录，输出保持原 `/tmp` 路径。B日期分解依赖先执行B逐事件复算；A单点敏感度在内存修改一次开关，不写原源码。依赖和执行环境见原报告及原家族环境记录；这些脚本是该快照的审计工具，不是通用策略引擎。运行会更新临时输出，不应再把更新后的文件误认为本次已pin产物。

已有四组核验脚本的本次输出在 `retained-accountants/`，此类重跑不同于独立重写模型训练/策略引擎。新增A/B/C复算提供了额外独立实现证据。原任务的全引擎重放只是已留存记录，本次没有宣称重新执行所有训练与完整重放。

新增逐事件、日期权重及VNQ单点结果均在原结果揭示之后产生，角色是故障归因/口径敏感度，不能当成新独立OOS、参数优化获胜或可交易收益。
