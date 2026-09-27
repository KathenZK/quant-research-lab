# Platform v2 验收与真实研究阻断

本轮结论：`INSUFFICIENT_EVIDENCE / NOT_PROMOTED`。5813 条真实来源记录经过私有认证 HTTP 接口导入候选筛选；严格解析 202 条，形成 28 个概念、41 个模板。合格模板 0、入选 0；最低要求 100、目标 200，缺口分别为 100 和 200。没有真实回测、OOS、晋级制品或 paper/live 批准。

统计依据：[候选聚合快照](../artifacts/platform-v2/candidate-summary.json)。该快照不包含原文、来源 URL 或私有记录 ID。完整候选只存于忽略的 artifacts/local；输入原始 archive 摘要与 [v1 契约](../specs/pipeline-v1.md) 相同。当前 parser 为 grok-rule-v3.1，5813/5813 projection READY，stale=0。

## 准入与排序

5611 条缺完整 AST，先留在规则 review；其余 202 条全部缺已审核研究许可、来源证据、执行契约和数据可用性证据。每个阻塞项按变体去重计数，一个变体可同时触发多个阻塞项。公开信息可访问不等于获得研究使用授权，BOT_DERIVED 标签也不能替代来源核验。

候选按模板分组。同模板参数、资产变体共用 experiment_family_id，不作为独立假设。先补齐尚未覆盖的概念，再按可研究程度和参数枚举惩罚选择；收益不参与评分。选中网格只包含通过门槛的变体。minimum_shortfall 与 target_shortfall 分开报告。

## 前 20 个真实研究结果摘要

当前没有可列出的合格策略。请求数量 20，实际启动 0，完成真实回测 0，完成 OOS 0，研究验证通过 0、失败 0（未启动，不能记作 20 次经济失败）。准入失败记录 5813 条；两种失败含义必须区分。

| 内容 | 实际状态 |
|---|---|
| Strategy concept/template/variant 与 experiment_family_id | 未建立研究实验；来源分组保留于候选快照 |
| parameter_grid / trial_count | 仅待审网格；真实 trial_count=0 |
| data_source / symbols / period / IS / OOS | NOT_STARTED；尚无获准使用且验证完整的数据契约 |
| transaction_cost / slippage | NOT_FROZEN；不借用其他策略参数 |
| CAGR / Sharpe / Sortino / Calmar / MDD / Turnover / Win Rate | null，NO_ELIGIBLE_CANDIDATES |
| walk-forward / plateau / DSR / PBO | null，NO_REAL_TRIAL_RETURNS |
| ResearchEvidence 真实回写 | 0；无真实结果可提交 |
| promotion artifacts / paper approved / live approved | 0 / 0 / 0 |

独立数值基准不是市场研究：[DSR 语义](../../../../docs/research/DSR.md)、[PBO 语义](../../../../docs/research/PBO.md)。v1 内核冻结保留，v2 修正 CSCV split 数量与 moment 接口。DSR 对照论文三组数值、固定收益向量和 vectorbt v0.28.5；PBO 对照论文、独立 SciPy 固定矩阵、完整 split 与并列政策。本轮没有运行第三方 R 的 PBO 包，不能把独立 oracle 写成外部包对拍。

## 后续顺序（沿用原 roadmap）

1. P2：对 25 类 review 规则逐类补严格语法与反例；当前 202 未达到 1000。源规则不完整与实现缺口分开记录，不能猜 AST。
2. P5/P6：获得可审核的来源、研究许可和数据证据，明确每个执行契约；本地审核记录绑定 semantic hash，规则变更使旧审核失效。补证后重新生成候选，不自动延用本轮名单。
3. P7：若至少有 20 个合格独立模板，先冻结数据、成本、IS/OOS、试验网格，再真实回测；不足则按实际数量继续报告。
4. P8：真实运行结束后通过 research:write 回写 immutable ResearchEvidence；提交状态不等于独立验收或因子归因成立。
5. P9：只有明确的人审决定可生成晋级制品。离线验证通过仍需 Runner 自有授权，当前不接入运行入口。

工程和数学测试通过不能解除上述证据阻断。
