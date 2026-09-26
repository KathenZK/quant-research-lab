# 研究联通 V1 契约

范围：读取 QuantGraph 私有候选，按 structural template 聚合 experiment_family_id，
保留 source_strategy_ids、完整参数 AST、planned_trial_count 和实际 trial_count。
同结构的参数/资产变体共用研究族；来源数量不当作独立假设数量。

候选准入必须同时具备：完整已解析规则、独立来源验证、明确 research_allowed 与许可记录、
可用数据、完整执行时序/成本/复权/缺失政策。缺任一项仍 BLOCKED。
目标 200 个、最低 100 个，最多 300 个；不为凑数放宽标准。
本轮只做候选筛选，没有授权自动决定任何来源的许可或填补策略执行规则。

真实数据范围：GrokBot 原始快照 5813 条；原始 archive SHA256 为
`c9d6e7de6e876fcd75678085aebe5c88e94a4d8932a39565a5cad96fa0418954`。
内容从 API 按页读取，不复制入研究仓库；完整候选仅可保存至 artifacts/local（忽略）。
公开持久证据仅包含聚合统计。

结果 schema 保留 in-sample/OOS/walk-forward/Monte Carlo、turnover/costs/drawdown、
Sharpe/Sortino/Calmar/stability、IC/RankIC/ICIR、PBO/DSR/参数稳健区间。
未计算值为 null 并附 NOT_COMPUTED 原因。PBO 使用全体同族 trial returns，不能只上传胜者。
DSR 输入非年化 Sharpe 和明确的有效试验数；相关性与 IID 近似限制必须披露。
PBO/DSR 是诊断，不替代本仓库既有验证门禁。

工程示例预先固定随机种子 20260926、256 个时间点、8 条合成收益流、前后各128点，
walk-forward 只报告后半段两个64点固定窗口；它不进行重新训练或优化。
无真实行情、成交或盈利结论；费用与资金费未模拟，不输出“完整净收益”声明。
真实研究 trial_count=0，示例 trial_count=8，两者分开统计。

制品格式为 [StrategyArtifact schema](../../../../src/strategy_lab/knowledge/strategy_artifact.schema.json)。
只有外部已批准的完整字段可导出，文件只写新路径且返回 SHA256。
APPROVED_FOR_PAPER 是研究制品状态，不是 runner 实例运行授权。
Live 字段保留兼容，但本版不接受 live 导出/启用。已有 Lab/runner 门禁仍然有效。
