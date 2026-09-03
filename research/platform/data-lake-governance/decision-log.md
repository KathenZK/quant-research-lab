# Decision Log — Binance-OHLCV-Data-Lake-Governance

## 2026-09-02 — 启动 Binance OHLCV 身份治理

决策：把 Binance 数据流固定为 `raw → accepted normalized 15m → versioned derived 1h/4h/1d → family cache → research artifacts`；当前 normalized 1h 登记为 `PARTIAL_SCOPE_LEGACY`，公共日K与 MA7 RC 面板登记为 `FAMILY_CACHE`。本轮只做非破坏性治理，不覆盖旧 parquet，不重跑策略。

证据：[身份契约](specs/binance-ohlcv-dataset-identity-contract-2026-09-02.md)、[data-lake-spec](../../../docs/data-lake-spec.md)。

## 2026-09-02 — 治理基础就绪

决策：现场审计、scope gate、cache sidecar、15m→1h/4h/1d 发布与对账均完成，状态 `GOVERNANCE_FOUNDATION_READY`。legacy 1h 不能再经新入口冒充 `FULL_MARKET`。旧 parquet 未改写。不把该状态解释为策略通过。

证据：[现场审计](diagnostics/binance-ohlcv-dataset-inventory-2026-09-02.md)、[对账](diagnostics/binance-ohlcv-reconciliation-2026-09-02.md)、[P0R-DATA 交接](specs/binance-4h-ma7-rc-p0r-data-handoff-2026-09-02.md)。

## 2026-09-03 — 第二轮可信读取门禁收口

决策：基础设施记 `READY`，15m 与 `from_15m.v1` 全量 SQL `PASS`，消费者仍 `PARTIAL`。不以笼统 READY 覆盖 legacy 1h、家族缓存和未迁移历史脚本。不把本轮解释为策略通过，也不外推 4H 全市场结论。

证据：[第二轮契约](specs/binance-ohlcv-round2-trusted-load-contract-2026-09-03.md)、[验收](diagnostics/binance-ohlcv-round2-acceptance-2026-09-03.md)、[SQL 审计](diagnostics/binance-ohlcv-trusted-quality-audit-2026-09-03.md)、[成交额追溯](diagnostics/binance-ohlcv-volume-rca-2026-09-03.md)。

## 2026-09-03 — 第三轮可信读取与截止契约

决策：Round 3 基础设施门禁记 `READY`；15m 与 `from_15m.v1` 行质量 `PASS` 但历史覆盖为内部缺口；4h 全市场研究 `gap_policy=reject` 为 `UNFIT`；消费者仍 `PARTIAL`；legacy 1h `quote_volume` 已按小时追溯但仍保留机器 blocker。不把本轮解释为策略通过，不发布生产新版本，不自动开始 4h MA7 研究。

证据：[第三轮契约](specs/binance-ohlcv-round3-trusted-load-contract-2026-09-03.md)、[验收](diagnostics/binance-ohlcv-round3-acceptance-2026-09-03.md)、[问题矩阵](diagnostics/binance-ohlcv-round3-issue-matrix-2026-09-03.md)、[SQL 审计 R3](diagnostics/binance-ohlcv-trusted-quality-audit-r3-2026-09-03.md)、[成交额追溯 R3](diagnostics/binance-ohlcv-volume-rca-r3-2026-09-03.md)。
