# Binance OHLCV Data Lake Governance

- Full family name：`Binance-OHLCV-Data-Lake-Governance`
- Alias：`BIN-OHLCV-DLG`
- 范围：Binance USD-M perp OHLCV 身份、scope gate、cache sidecar 与 15m→1h/4h/1d 标准衍生；不是策略家族。
- 当前状态：组合 v2 统一绑定价格 V3、高周期 v2、费率 v2，并提供研究启动门禁；费率历史覆盖与消费者迁移仍 `PARTIAL`，不宣称完整 PIT 或策略 PASS。分项见主账。

## 边界

- 不删除、不移动、不覆盖现有 raw / normalized / cache parquet。
- 当前 normalized `1h` 是 `PARTIAL_SCOPE_LEGACY`，不能当全市场事实源。
- 家族面板缓存不是标准 OHLCV，也不能当其他家族的输入。
- 新研究启动与使用边界的唯一规范：[data-lake-spec.md](../../../docs/data-lake-spec.md) 第 19 节；历史版本语义见第 16–18 节。

## 入口

- 主账：[binance-ohlcv-dlg-core-ledger.md](binance-ohlcv-dlg-core-ledger.md)
- 决策记录：[decision-log.md](decision-log.md)
- 当前组合：[选择指针](specs/current-research-inputs.json) · [固定 v2 清单](specs/binance-v3-research-input-bundle-v2.json) · [发布契约](specs/binance-v3-research-input-bundle-v2-2026-09-07.md)
- 启动检查：[规范第 19 节](../../../docs/data-lake-spec.md) · [价格请求示例](specs/research-startup-price-example-v2.json) · [交接验收](diagnostics/binance-research-bundle-v2-startup-2026-09-07.md)
- 资金费率 v2：[契约](specs/binance-funding-v3-inputs-v2-2026-09-07.md) · [验收与使用边界](diagnostics/binance-funding-v3-inputs-v2-2026-09-07.md) · [机器验收](artifacts/binance_funding_v3_inputs_v2_20260907/acceptance.json)
- 历史价格发布与旧组合（绑定费率 v1）：[契约](specs/binance-v3-research-inputs-v1-2026-09-07.md) · [治理报告](diagnostics/binance-v3-research-inputs-v1-2026-09-07.md)
- 15m V3：[契约](specs/binance-15m-history-v3-contract-2026-09-06.md) · [全历史治理验收](diagnostics/binance-15m-history-v3-closeout-2026-09-06.md)
- 15m V2：[刷新契约](specs/binance-15m-refresh-v2-contract-2026-09-05.md) · [验收与未完成项](diagnostics/binance-15m-refresh-v2-acceptance-2026-09-06.md)
- 历史治理 R1–R3、身份、SQL 与消费者迁移证据：[主账 Evidence Map](binance-ohlcv-dlg-core-ledger.md#evidence-map)
- 4H P0R 交接：[specs/binance-4h-ma7-rc-p0r-data-handoff-2026-09-02.md](specs/binance-4h-ma7-rc-p0r-data-handoff-2026-09-02.md)
- 产物：[artifacts/README.md](artifacts/README.md)
- 规范：[../../../docs/data-lake-spec.md](../../../docs/data-lake-spec.md)
