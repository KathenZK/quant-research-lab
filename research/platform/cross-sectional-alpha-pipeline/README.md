# Cross-Sectional Alpha Research Pipeline

本目录保存 `quant-research-lab` 横截面 Alpha 研究平台的仓库级审计与落地契约，不是一个策略家族，也不登记、晋升或覆盖任何现有 CTA/HYPE 研究。

## 当前结论

- 审计日期：`2026-08-18`
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
