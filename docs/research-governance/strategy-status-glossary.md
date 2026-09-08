# 策略状态术语表与状态机

本文件是全仓库策略版本状态词的唯一定义来源。core ledger、README、diagnostics、live specs 引用状态词时必须使用本表中的标签；发明新状态词前先更新本文件。

## 2026-09-03 修订摘要

- **dry-run 以 runner lock 为准**：该版本在 quant-runner lock 中存在 `mode=dry_run` 且 `enabled_allowed=true` 的实例，即为 `dry-run` 主状态，无论 promotion review / 硬门禁是否完成。
- **registered 可直达 dry-run**：条件为用户显式授权、runner 实现完成、指标对拍或 smoke 通过、同一变更建立 `runner-tracking/`。
- **live spec 改为可选中间态**：交接规格已写而 runner 尚未实现或尚未授权时可写 `live spec`；不再是 dry-run 的必经前置。
- **硬门禁后移到 dry-run -> live**：门禁 0–4 与 live-executable 审计与线上开平仓对账并列，作为进入 `live` 的条件。
- **不另设 observer**：runner 观察实例 = `dry-run` 主状态，不另设 observer 状态或 overlay；历史文档中的 “dry-run observer” 按 `dry-run` 理解。

## 权威边界与冲突处理

三类事实各有唯一权威，不得互相替代：

1. 本术语表定义主状态、合法组合与状态迁移。
2. 家族 core ledger 是家族/版本身份与当前状态的叙事真源；asset/顶层索引是路由投影。
3. `quant-runner` 是实例运行与授权的唯一真源；实际运行/停止事实只以其代码、配置、生成锁、服务状态和运行账本为准。Lab 不保存实例授权 manifest。

active SPEC 是研究侧实现合同，不是状态或实例授权源。术语表、core ledger、索引或 active SPEC 冲突时，阻止新的 promotion 或交接并修复研究权威源；不得据此自动停止、禁用或降级 runner 实例。任何运行状态变化必须由用户明确决定并在 `quant-runner` 执行。

“登记 / 记录 / 冻结 / 命名为 Vx”只固定版本身份并更新 core ledger，默认进入 `registered`，不包含任何 promotion。只有明确提出目标状态的 “promote / 晋升 / 进入 dry-run / 上线”才是状态迁移请求，并须满足对应门禁。

## 状态机总览

主状态只有下面这些：研究侧 2 个、promotion 侧 3 个，外加两个终态（`archived` 与 dry-run/live 后的 `NO-GO`）：

```text
explore（无版本号）
   │ 用户要求登记 Vx
   ▼
registered
   │ 用户显式授权 + runner 实现完成 + 对拍/smoke + 同一变更建立 runner-tracking/
   │ 可直达 dry-run（live spec 为可选中间态，不是必经前置）
   ├─ 交接规格已写、runner 尚未实现或尚未授权 ─► live spec ─► dry-run
   └──────────────────────────────────────────────────────► dry-run
                                                              │ 硬门禁 0–4 + live-executable
                                                              │ + 线上开平仓对账 + 运维审计
                                                              ▼
                                                             live
```

未满足 dry-run 准入时停留在 `registered` / `explore`，并写 `not promoted / not live-ready`。已进入 dry-run 但硬门禁或 live-executable 未完成时写 `dry-run / not live-ready`，不得进入 `live`。只有 dry-run 或 live 已运行并给出负面 runner 观察/实盘证据后，才允许写 NO-GO。研究线不再推进且无意重开时，任一阶段可以封存为 archived（终态，重开视同新研究线）。

`audit` 不再是主状态。审计报告、脚本文件名和 promotion review 仍可使用 audit / 审计描述验证动作，但不得把版本状态写成 `audit`。登记 `registered` 时只固定身份并记录门禁缺口。写 `live spec` 或进入 `dry-run` 不要求一次性完成硬门禁；硬门禁与 live-executable 审计在 `dry-run -> live` 时核验。

promotion 状态只有 `live spec`、`dry-run`、`live` 三个；`handoff` 是可叠加在其上的移交标签，不是独立状态。进入 `live` 前必须完成 live-executable 审计与硬门禁 0–4（见 [live-executable-strategy-research.mdc](../../.cursor/rules/live-executable-strategy-research.mdc)、[lab-runner-handoff.mdc](../../.cursor/rules/lab-runner-handoff.mdc) 与 [strategy-validation-gates.md](strategy-validation-gates.md)）。`dry-run` 只要求用户显式授权、runner 可复现、对拍或 smoke 通过、以及 `runner-tracking/` 建立。本仓库不定义额外的模拟盘阶段；模拟盘/仿真运行统一称为 `dry-run`，真实下单归入 `live`。runner 观察实例 = `dry-run` 主状态，不另设 observer 状态或 overlay。

## 主状态定义

| 主状态 | 含义 | 准入条件 |
| --- | --- | --- |
| `explore` | 搜索、诊断进行中，未登记版本 | 无；不可被引用为"策略" |
| `registered` | 用户要求登记的冻结版本（基线或观察值），仅固定研究身份 | core ledger 已更新版本表、参数、证据链接；不代表策略可行 |
| `live spec` | 已写出 runner 交接规格，等待/正在 quant-runner 实现或等待用户授权启用；可选中间态，不是 dry-run 必经前置 | 身份已冻结；参数/状态机可被 runner 复现；满足 `lab-runner-handoff.mdc` 交接规格必备字段；core ledger 链接该规格。不要求硬门禁或 live-executable 审计已完成 |
| `dry-run` | 该版本在 quant-runner lock 中存在 `mode=dry_run` 且 `enabled_allowed=true` 的实例（模拟盘，不下真实订单），即为 dry-run 主状态，无论 promotion review 是否完成 | 用户显式授权；runner 实现完成；指标对拍或 smoke 通过；进入 dry-run 的同一变更中建立 `runner-tracking/`。`registered -> dry-run` 为合法直达迁移 |
| `live` | 真实资金运行 | 已核验 [strategy-validation-gates.md](strategy-validation-gates.md) 硬门禁 0–4 与 live-executable 审计；dry-run 的 runner 观察证据达标；已完成线上开平仓对账且无未解决的重大偏差；资金费、盘口滑点、订单失败处理已审计；decision log 记录批准；资金边界由子账户资金、runner 配置或上线 decision log 管理，策略 spec 不强制写 live notional |
| `NO-GO` | dry-run 或 live 后的最终否决状态 | 必须有 `runner-tracking/`、dry-run 对账或真实订单证据；记录否决原因，重开需新证据并写 decision log |
| `archived` | 研究线已封存：不再推进、不再复现，仅作历史证据保留 | decision log 记录封存原因；封存不需要负面 runner 观察证据；重开视同新研究线 |

`handoff` / "交接版本"：把规格与实现移交给人或其他系统维护的动作标签，可叠加在 `live spec` 及之后的主状态上；要求双向链接的 SPEC 齐备、参数一致性验证记录在案。`handoff` 不是独立主状态。

runner 观察实例 = `dry-run` 主状态，不另设 observer 状态或 overlay。历史文档中的 “dry-run observer” 按 `dry-run` 理解。外部非本仓库 runner 的历史观察仍用结果标签 `external-observation`，不得写成 observer。

`candidate` 不是主状态，也不是 promotion 状态。新文档可以把它作为研究角色词使用，例如参数候选、候选观察行、`registered candidate`；但不得写成独立状态，也不得用来暗示 live-ready 或可跳过 `dry-run` / `live` 门禁。若用户要求把候选登记为版本，主状态应写 `registered`，`candidate` 只作为角色修饰。

## 机器字段映射

| 叙事概念 | 机器字段 | 合法值 / 约束 |
| --- | --- | --- |
| 主状态 | core ledger、Lab live SPEC `main_status` | `explore`、`registered`、`live spec`、`dry-run`、`live`、`NO-GO`、`archived` |
| runner 模式与授权 | quant-runner config / generated lock | `dry_run`、`live`、enabled 等实际字段只在 runner 仓库维护 |
| 实际运行状态 | runner config / generated lock / service / runtime ledger | 判断实例正在运行、停止或使用哪个策略的唯一事实来源 |
| 对拍证据状态 | 标准 parity artifact `conclusion` 或报告备注 | `PASS`：对拍通过，可作为推进证据；`FAIL`：对拍失败，阻止新 promotion；`PENDING`：对拍尚未完成，阻止新 promotion，不自动改变 runner；`MISSING_EVIDENCE`：规范证据缺失，阻止新 promotion，不自动改变 runner |
| overlay | Lab live SPEC `overlays` | 可包含 `handoff`；不是 `main_status`。不设 observer overlay |
| 非晋升后缀 | 叙事 `not promoted` | 只可修饰 `explore` 或 `registered`，不写入 `main_status` |
| 未达 live 后缀 | 叙事 `not live-ready` | 可修饰 `explore`、`registered`、`live spec`、`dry-run`，不写入 `main_status` |
| 终态 | ledger `main_status` | `NO-GO` 或 `archived`；不得与历史 runner 状态并列为第二主状态 |
| 索引转发 | 资产 README 状态列 | 可写 `见顶层`，表示与 [`research/README.md`](../../research/README.md) 对应行完全相同 |

`dry-run / not promoted` 是自相矛盾组合：`dry-run` 已是 promotion 状态。`dry-run / NO-GO` 也非法，因为同一时刻出现两个主状态；否决后只写 `NO-GO`，历史 dry-run 事实放在 runner tracking 或历史备注。相同规则适用于 `live / NO-GO`。runner 配置中的 `dry_run` 使用下划线，叙事主状态始终写 `dry-run`。

## 修饰词（不是主状态）

以下词只能作为主状态的修饰或备注，单独出现不构成状态：

| 修饰词 | 含义 | 允许搭配的主状态 |
| --- | --- | --- |
| `baseline` | 基线锚点 | `explore`、`registered` |
| `candidate` | 参数候选或候选观察行 | `explore`、`registered` |
| `observation` | 微调观察值 | `explore`、`registered` |
| `clean-equivalent` | 与 parent 逐笔等价的参数精简版（需 trade signature 一致证据，且不提供新增收益证据） | `explore`、`registered` |
| `forward-test required` | 状态推进依赖 `runner-tracking/` 下尚不存在的报告；口头描述不算证据 | `dry-run`、`live` |
| `tiny-live-pilot` | 真实下单只用于执行审计；资金必须在专用子账户内隔离，并在 quant-runner 配置或上线 decision log 中记录授权、资金边界和到期时间。不是 production sizing | `live` |
| `not promoted` | 尚未进入 promotion 状态 | `explore`、`registered` |
| `not live-ready` | 尚不满足 `live` 准入；不是最终否决 | `explore`、`registered`、`live spec`、`dry-run` |

历史文档中的 `diagnostic baseline`、`diagnostic observation`、`clean-equivalent observation`、`audit observation`、`audit candidate` 或 `audit` 状态等旧标签，按验证动作或 `registered baseline/observation`、`registered / not promoted / not live-ready` 理解，不需要批量改写。历史文档中若在 dry-run 前使用了 `NO-GO`，按新口径理解为 `not promoted / not live-ready`，除非同一文档明确引用了 dry-run/live runner 观察证据；顶层/资产索引已把这类标签归一为 `HARD-GATE-FAILED`，不把主状态改成 `NO-GO`。

## Overlay 标签（不是主状态）

| Overlay | 含义 | 允许搭配的主状态 |
| --- | --- | --- |
| `handoff` | 规格与实现已移交给人或其他系统维护 | `live spec`、`dry-run`、`live` |

## 结果标签（result labels）

结果标签记录研究结论或证据健康度，不是主状态，不能单独出现在索引状态列。主状态仍必须是上表七词之一。

| 结果标签 | 含义 | 允许搭配的主状态 |
| --- | --- | --- |
| `diagnostic-only` | 诊断/机制探查，尚未形成可晋升策略 | `explore`、`registered` |
| `HARD-GATE-FAILED` | 验证门禁硬项或等价失败（超额/消融/OOS/MC/压力/live-executable/搜索无通过项）；不是 `NO-GO`（后者需要 dry-run/live runner 证据） | `explore`、`registered`、`archived` |
| `TRANSFER_FAIL` | 零调参/固定参数跨资产迁移未通过。是 `HARD-GATE-FAILED` 在迁移场景的特化；索引可写本标签或 `HARD-GATE-FAILED`，不得再发明 `transfer FAIL` 等变体 | `explore`、`registered` |
| `research-line-closed` | 本机制研究线已关闭，无意在同一假设上继续搜参；目录若也不再维护应升为 `archived` | `explore`、`registered` |
| `raw-unaccepted` | 数据源或窗口未通过 data-quality 准入，不得当作已接受研究输入 | `explore` |
| `DATA_SCOPE_INCOMPLETE` | 数据宇宙/覆盖不足，现有结论不得外推全市场 | `explore` |
| `formula-invalidated` | 因公式或实现错误撤销历史绩效 | `explore`、`archived` |
| `validation-failed` | 冻结契约的 validation 段未通过，该版本不得晋升 | `explore`、`registered` |
| `goal-complete` | 预先写明的 Goal/搜索合同已执行完毕（无论成败）；不是 promotion | `explore`、`registered`、`archived` |
| `external-observation` | 外部 runner 的历史观察，不是本仓库 quant-runner 授权 | `explore`、`registered`、`dry-run`、`live` |
| `platform-audit` | 研究平台或数据治理审计结论，不是策略绩效 | `explore`、`archived` |
| `PASS` | 对拍通过（见机器字段映射） | `registered`、`live spec`、`dry-run`、`live` |
| `FAIL` | 对拍失败（见机器字段映射） | `registered`、`live spec`、`dry-run`、`live` |
| `PENDING` | 对拍尚未完成（见机器字段映射） | `registered`、`live spec`、`dry-run`、`live` |
| `MISSING_EVIDENCE` | 规范证据缺失，或复现/对账尚未完成（见机器字段映射） | `explore`、`registered`、`live spec`、`dry-run` |

旧写法归一：`research line closed` → `research-line-closed`；`validation failed` → `validation-failed`；`Goal complete` → `goal-complete`；`raw unaccepted` → `raw-unaccepted`。quant-runner 语境下的 `observer` / `dry-run observer` → `dry-run`；外部 runner 历史观察 → `external-observation`。`target failed`、搜索无通过项、机制失败等散文失败结论 → `HARD-GATE-FAILED`。dry-run 前索引里的 `NO-GO` → `HARD-GATE-FAILED`，主状态保持 `explore` 或 `registered`。

## 索引转发

| 标签 | 含义 |
| --- | --- |
| `见顶层` | 仅用于资产 README 状态列，表示与顶层 [`research/README.md`](../../research/README.md) 对应家族行的状态字符串完全相同 |

## 禁止的状态词

新文档与索引状态列不得使用：

- `paper-live`
- `sim-paper`
- `blocked`
- `audit / not promoted`
- `audit only`
- `live candidate`
- `dry-run candidate`
- `promotion candidate`
- `runner-observer`

## 使用规则

- 状态词必须与完整 family name + 版本号一起出现，例如 `HYPE-15M-MII-V1.3：dry-run / forward-test required`。
- 一个版本同一时刻只有一个主状态；可以叠加修饰词，不可同时挂两个主状态。
- `not promoted` 只能修饰 `explore` 或 `registered`；`not live-ready` 可延续到 `live spec` 或 `dry-run`，但不得与 `live` 或 `NO-GO` 并存。
- 状态迁移（升级或降级）必须写入家族 `decision-log.md`，并同步更新 core ledger 与 asset/顶层索引中的状态标签。
- 新的 `live` 准入要求经过 `dry-run` 并完成硬门禁与 live-executable 审计；缺失时记录缺口，不声明准入通过。既有实例的授权和运行状态按 runner 如实记录，不能由文档缺口自动推断降级。`live spec` 与 `dry-run` 不以完整 promotion review 为前置；`registered -> dry-run` 合法。
- 硬门禁或 live-executable 失败时不推进 `live`：仍在 dry-run 的版本写 `dry-run / not live-ready`，尚未授权 runner 的已登记版本写 `registered / not promoted / not live-ready`，未登记研究线写 `explore / not promoted / not live-ready`。既有 live 实例发现问题时记录证据和处置建议，运行变更由用户明确决定。
- dry-run 前不得给出 `NO-GO`；只能写 `not promoted / not live-ready`，并说明缺什么证据、什么新增证据可以重开。
- 索引状态列只允许主状态、修饰词、结果标签、overlay、版本号、家族名与 `见顶层`；散文结论下沉到主账或 decision-log。
- 不另设 observer 状态或 overlay；runner 观察实例写 `dry-run`。
