# Binance OHLCV Data Lake Governance

- Full family name：`Binance-OHLCV-Data-Lake-Governance`
- Alias：`BIN-OHLCV-DLG`
- 范围：Binance USD-M perp OHLCV 身份、scope gate、cache sidecar 与 15m→1h/4h/1d 标准衍生；不是策略家族。
- 当前状态：15m `history.v3` 为统一输入，配套高周期 `from_15m.v2` 已发布并验收；费率续治理独立发布 `v3_inputs.v2`，事件歧义清零、V3 全部代码有观测，但历史结算覆盖仍 `PARTIAL_COVERAGE`。身份仅实施保守有效性门禁，不宣称完整 PIT。旧版本保留，消费者仍 `PARTIAL`。分项见主账。

## 边界

- 不删除、不移动、不覆盖现有 raw / normalized / cache parquet。
- 当前 normalized `1h` 是 `PARTIAL_SCOPE_LEGACY`，不能当全市场事实源。
- 家族面板缓存不是标准 OHLCV，也不能当其他家族的输入。
- 新研究必须显式 cutoff 与 `gap_policy=reject|contiguous_segments`；4h 全市场 `reject` 为 `UNFIT`。

## 入口

- 主账：[binance-ohlcv-dlg-core-ledger.md](binance-ohlcv-dlg-core-ledger.md)
- 决策记录：[decision-log.md](decision-log.md)
- 资金费率 v2：[契约](specs/binance-funding-v3-inputs-v2-2026-09-07.md) · [验收与使用边界](diagnostics/binance-funding-v3-inputs-v2-2026-09-07.md) · [机器验收](artifacts/binance_funding_v3_inputs_v2_20260907/acceptance.json)
- V3 统一输入：[契约](specs/binance-v3-research-inputs-v1-2026-09-07.md) · [治理报告](diagnostics/binance-v3-research-inputs-v1-2026-09-07.md) · [机器清单](artifacts/binance_v3_research_inputs_v1_20260907/research_input_bundle.json)
- 15m V3：[契约](specs/binance-15m-history-v3-contract-2026-09-06.md) · [全历史治理验收](diagnostics/binance-15m-history-v3-closeout-2026-09-06.md)
- 15m V2：[刷新契约](specs/binance-15m-refresh-v2-contract-2026-09-05.md) · [验收与未完成项](diagnostics/binance-15m-refresh-v2-acceptance-2026-09-06.md)
- 第 3 轮契约：[specs/binance-ohlcv-round3-trusted-load-contract-2026-09-03.md](specs/binance-ohlcv-round3-trusted-load-contract-2026-09-03.md)
- 第 3 轮验收：[diagnostics/binance-ohlcv-round3-acceptance-2026-09-03.md](diagnostics/binance-ohlcv-round3-acceptance-2026-09-03.md)
- 使用示例：[docs/data-lake-spec.md](../../../docs/data-lake-spec.md) 第 16–18 节
- 第 2 轮契约：[specs/binance-ohlcv-round2-trusted-load-contract-2026-09-03.md](specs/binance-ohlcv-round2-trusted-load-contract-2026-09-03.md)
- 身份契约：[specs/binance-ohlcv-dataset-identity-contract-2026-09-02.md](specs/binance-ohlcv-dataset-identity-contract-2026-09-02.md)
- 现场审计：[diagnostics/binance-ohlcv-dataset-inventory-2026-09-02.md](diagnostics/binance-ohlcv-dataset-inventory-2026-09-02.md)
- 成交额追溯 R3：[diagnostics/binance-ohlcv-volume-rca-r3-2026-09-03.md](diagnostics/binance-ohlcv-volume-rca-r3-2026-09-03.md)
- 全量 SQL 质量 R3：[diagnostics/binance-ohlcv-trusted-quality-audit-r3-2026-09-03.md](diagnostics/binance-ohlcv-trusted-quality-audit-r3-2026-09-03.md)
- 消费者迁移 R3：[diagnostics/binance-ohlcv-consumer-migration-r3-2026-09-03.md](diagnostics/binance-ohlcv-consumer-migration-r3-2026-09-03.md)
- 4H P0R 交接：[specs/binance-4h-ma7-rc-p0r-data-handoff-2026-09-02.md](specs/binance-4h-ma7-rc-p0r-data-handoff-2026-09-02.md)
- 产物：[artifacts/README.md](artifacts/README.md)
- 规范：[../../../docs/data-lake-spec.md](../../../docs/data-lake-spec.md)
