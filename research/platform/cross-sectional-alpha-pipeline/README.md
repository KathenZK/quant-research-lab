# Cross-Sectional Alpha Research Pipeline

research_classification: diagnostic_topic

本目录保存 `quant-strategy-lab` 横截面 Alpha 研究平台的仓库级审计与落地契约，不是一个策略家族，也不登记、晋升或覆盖任何现有 CTA/HYPE 研究。

## 2026-09-25 实际落地

- [下一阶段建议复核与数据描述更正](diagnostics/next-research-suggestions-review-20260925.md)：资金费事件已含大部分结算mark_price，旧316个主动成交原始归档仍可核验；下一步转向真实观察与单一增量假设，不扩大工具建设。
- [自包含结果报告](diagnostics/implementation-results-20260925.md)：相对强弱边界修复、独立账户、净持仓接口、874代码数据能力、120条曝光记录，以及 HYPE MA7-CAR V3 本地独立/离线恢复。
- [研究记录协议与用法](specs/research-records-protocol-20260925.md) · [事前落地契约](specs/implementation-contract-20260925.md)。后续新增实验先登记已看窗口；候选需保留实际输入/模型并恢复验收。
- 验收：164项定向测试通过；本轮入口检查通过；全仓检查另有73项其他路径问题。三币固定范围价格通过但完整资金费日历未证明，因此没有启动新净收益实验或实际前瞻观察。
- 本轮是离线研究组件和证据恢复完成，不代表全平台工业化、策略晋升或线上状态改变。

## 当前结论

- 以下为原始平台审计，日期：`2026-08-18`；本轮进展见上方2026-09-25记录。
- 审计基线 commit：`0afcd245b89b`
- 总体判定：`PARTIAL / NOT INDUSTRIAL-READY`
- 当前最可复用资产：数据湖质量内核、因子注册与版本、Binance 全市场 `15m` 档案、旧 `BIN-1H-MHCSML` 的 point-in-time panel / 标签 / purged walk-forward / allocator 参考实现。
- 当前首要缺口：有效期化 instrument master、可复用 panel/dataset/diagnostics API、统一实验注册、neutralization、真实成本与 capacity、alpha library/combination，以及 Hyperliquid 全市场历史数据。

## 文档入口

- [完整 readiness audit](cross-sectional-alpha-pipeline-readiness-audit-2026-08-18.md)
- [Gap matrix](gap-matrix.md)
- [三阶段 roadmap](roadmap.md)
- [第一个 baseline 实验规格](baseline-experiment-v0.md)

这些文档只冻结“平台改造与首个基线”的研究合同。任何策略绩效、版本登记和 promotion 必须在相应策略家族内另行完成。
