# StrategyArtifact v2 离线交接契约

单向数据流是 quant-knowledge-graph → quant-research-lab → quant-runner。知识层没有下发运行层的接口。本页描述研究端的离线校验，不保证未修改的运行端支持新增仓库身份。

新制品使用 producer=quant-research-lab；v2 明确 producer、strategy_variant_id、research_run_id、code_hash、config_hash、parameters、market、universe、data_requirements、risk_limits、execution_config、validation_summary，以及 promotion_status、approved_at、approved_by、approval_reference。代码和配置摘要必须匹配实际字节；绑定配置必须与制品声明逐字段一致。

RESEARCH_ONLY 在结构上可表达，但离线入场校验拒绝；APPROVED_FOR_PAPER 只允许 paper，APPROVED_FOR_LIVE 只允许 live。未来时间、缺批准人、失败验证、非有限费用和配置篡改均拒绝。校验器不生成批准、不验证批准人的组织身份、不启动运行；实际执行继续由 Runner 的 manifest/lock 和人审门禁控制。

contracts/fixtures-v2 仅含不可交易的合成契约样例；其中占位批准不代表任何真实批准。真实 promotion artifacts、paper/live approvals 本轮均为 0。现有 v1 接口保留，v2 尚未替换运行链路。

仓库改名兼容：研究端校验接受 `quant-research-lab` 和历史别名 `quant-strategy-lab`，不改写输入。旧合成制品及其 code/config 摘要原样保留；新增 `synthetic-artifact-renamed.json` 验证新身份和相同的拒绝规则。未迁移的外部消费者可能仍只接受旧 producer；本次不修改 quant-runner，也不把新身份校验通过解释为运行端已接受。详见 [迁移说明](../repository-name-migration.md)。
