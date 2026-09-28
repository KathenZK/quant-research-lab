# 策略状态术语表

本文件统一主账、索引与机器 `main_status` 字段的主状态。研究正文、结论和状态补充说明可自然表达，不使用封闭词表限制措辞。

## 事实来源

- 家族主账记录版本身份、研究状态、决策和证据；README 是定位入口。
- active SPEC 是实现合同；机器字段遵循 [Lab SPEC schema](schemas/lab-live-spec-frontmatter.schema.json)。
- quant-runner 的配置、生成锁、服务状态和运行账本分别提供实例授权与实际运行证据；授权存在不等于服务正在运行。Lab 不维护另一份实例授权 manifest。

文档冲突时核对相应事实来源，记录和修复差异。研究结论、缺失证据或 CI 失败不能代替用户的运行变更授权。

## 主状态定义

| 主状态 | 含义 |
| --- | --- |
| `explore` | 正在探索或诊断，尚未登记冻结版本 |
| `registered` | 已登记并固定版本身份，不代表可交易或已授权运行 |
| `live spec` | 已准备 runner 交接规格，等待实现或授权；可选中间态 |
| `dry-run` | 在 quant-runner 中获授权的模拟执行；实际是否运行需查看服务/账本 |
| `live` | 获授权的真实资金执行；资金边界与运行事实由 runner 记录 |
| `NO-GO` | 基于研究或运行证据作出不再推进该版本的决定，主账记录原因 |
| `archived` | 已封存、只作历史保留的研究线 |

每个版本的结构化主状态只有一个。家族存在多个版本时分别记录；`main_status` 不填散文或多个标签。研究说“NO-GO”可以是单项结论，不自动改变版本主状态或关闭 runner；正式状态变更在主账与 decision log 中记录依据。

## 记录方式

- “登记 / 冻结 / 命名为 Vx”固定身份并更新主账，通常使用 `registered`，不包含晋升或运行授权。
- `registered -> dry-run` 可以直达；涉及 live 准入时核验 [状态迁移要求](strategy-validation-gates.md)。不因一次日常诊断自动启动这一流程。
- 主账记录正式状态变化，索引给出简短状态或指向主账；两级索引不要求逐字复述同一说明。
- `not promoted`、`not live-ready`、`candidate`、`diagnostic-only`、`blocked` 等可以用于解释角色、证据或限制；不要用它们冒充机器主状态或暗示不存在的运行许可。
- `handoff` 表示交接，机器 overlay 按 schema 填写；`PASS / FAIL / PENDING / MISSING_EVIDENCE` 是证据结论，不能单独证明策略通过或已上线。
- 真实下单统一归入 `live`，模拟执行归入 `dry-run`；runner 配置字段 `dry_run` 与叙事 `dry-run` 的拼写区别保留。

已有文档保留当时语境，不批量改写历史标签。重开已停止或封存的研究时记录新的依据与版本关系；不覆盖原决策和证据。
