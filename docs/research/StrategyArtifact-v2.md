# StrategyArtifact v2 离线交接契约

单向数据流是 QuantGraph → Lab → Runner。Lab 与 Runner 保存相同的 JSON Schema；QuantGraph 没有下发 Runner 的接口。

v2 明确 producer=quant-strategy-lab、strategy_variant_id、research_run_id、code_hash、config_hash、parameters、market、universe、data_requirements、risk_limits、execution_config、validation_summary，以及 promotion_status、approved_at、approved_by、approval_reference。代码和配置摘要必须匹配实际字节；绑定配置必须与制品声明逐字段一致。

RESEARCH_ONLY 在结构上可表达，但离线入场校验拒绝；APPROVED_FOR_PAPER 只允许 paper，APPROVED_FOR_LIVE 只允许 live。未来时间、缺批准人、失败验证、非有限费用和配置篡改均拒绝。校验器不生成批准、不验证批准人的组织身份、不启动运行；实际执行继续由 Runner 的 manifest/lock 和人审门禁控制。

contracts/fixtures-v2 仅含不可交易的合成契约样例；其中占位批准不代表任何真实批准。真实 promotion artifacts、paper/live approvals 本轮均为 0。现有 v1 接口保留，v2 尚未替换运行链路。
