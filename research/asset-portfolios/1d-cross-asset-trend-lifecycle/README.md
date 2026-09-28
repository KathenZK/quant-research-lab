# Binance-1D-Cross-Asset-Trend-Lifecycle

- Alias：`BIN-1D-CATL`
- 市场：Binance USD-M USDT 永续合约全市场历史点位集合
- 周期：完整 UTC 日 K；future path 由 normalized `15m` 重聚合闭合 `1h` 后计算
- 机制：构建跨资产可比较的日频因果特征、long/short 方向 landmark、entry/continuation first-hit 标签，为后续趋势生命周期学习准备数据集。
- 当前状态：`explore / diagnostic-only / not promoted / not live-ready`
- P0 裁决：`DATASET_READY_FOR_MODELING_RESEARCH`
- P0R 裁决：`MODELING_INPUT_READY`；P1 只能使用物理排除 HYPE 的 donor panel。
- P1 Entry 裁决：`LEARNABLE_BUT_NOT_INCREMENTAL_BEYOND_MA`。
- P1 Continuation 裁决：`LEARNABLE_BUT_NOT_INCREMENTAL_BEYOND_MA`。
- 碰撞警告：本家族不是 `HYPE-1D-MA7-Machine-Learning-Trend`，不修改 HYPE P0-P8/V7.1；MA7/MA30/MA60 只作特征和诊断探针，不构成策略规则。

入口：

- [Core ledger](binance-1d-catl-core-ledger.md)
- [Decision log](decision-log.md)
- [P0 冻结合同](specs/binance-1d-catl-p0-dataset-label-atlas-contract-2026-08-31.md)
- [P0 数据质量报告](diagnostics/binance-1d-catl-p0-data-quality-2026-08-31.md)
- [P0 标签分布报告](diagnostics/binance-1d-catl-p0-label-distribution-2026-08-31.md)
- [P0R 修复合同](specs/binance-1d-catl-p0r-modeling-input-repair-contract-2026-08-31.md)
- [P0R 修复报告](diagnostics/binance-1d-catl-p0r-modeling-input-repair-2026-08-31.md)
- [P1 冻结合同](specs/binance-1d-catl-p1-donor-walk-forward-modeling-contract-2026-08-31.md)
- [P1 Entry 报告](diagnostics/binance-1d-catl-p1-entry-model-2026-08-31.md)
- [P1 Continuation 报告](diagnostics/binance-1d-catl-p1-continuation-model-2026-08-31.md)
- [P1 建模审计](diagnostics/binance-1d-catl-p1-modeling-audit-2026-08-31.md)
- [P1 Cursor 完整提示词](prompts/binance-1d-catl-p1-walk-forward-modeling-cursor-prompt-2026-08-31.md)
- [字段字典](artifacts/binance_1d_catl_p0_field_dictionary.md)
- [Artifact index](artifacts/README.md)
