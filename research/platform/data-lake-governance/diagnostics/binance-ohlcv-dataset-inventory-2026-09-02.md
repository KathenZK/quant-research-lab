# Binance OHLCV 数据湖现场目录审计

- 生成时间：`2026-09-02T14:49:15.204326+00:00`
- 来源裁决：`binance_perp_15m_priority_union_v1`（Vision monthly 优先于 Futures API；未列入来源不进入 trusted union）
- 本报告只描述现场身份与覆盖，不改变策略假设。

## 分层结论

```text
Binance 原始来源 → raw → accepted normalized 15m
                 → versioned derived 1h/4h/1d
                 → family cache
                 → research artifacts
```

normalized 1h 登记为 `PARTIAL_SCOPE_LEGACY`，不得因 distinct symbol 数量被当成全市场。

## 数据集登记

| dataset_id | layer | status | 文件 | 字节 | 物理行 | 业务键 | 重复键 | symbols | 起止 UTC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `binance.perp.ohlcv.15m.normalized.v1` | normalized | `TRUSTED_BASE` | 8913 | 3074680503 | 60546466 | 60372827 | 173639 | 854 | 2019-09-08T17:45:00+00:00 → 2026-08-24T23:45:00+00:00 |
| `binance.perp.ohlcv.1h.normalized.legacy` | normalized | `PARTIAL_SCOPE_LEGACY` | 4758 | 74343047 | 399679 | 398729 | 950 | 543 | 2022-02-26T00:00:00+00:00 → 2026-08-28T10:00:00+00:00 |
| `binance.perp.ohlcv.1h.from_15m.v1` | derived | `TRUSTED_DERIVED` | 69781 | 1110388019 | 15066337 | 15066337 | 0 | 853 | 2019-09-08T18:00:00+00:00 → 2026-08-24T23:00:00+00:00 |
| `binance.perp.ohlcv.4h.from_15m.v1` | derived | `TRUSTED_DERIVED` | 19118 | 285724909 | 3766251 | 3766251 | 0 | 853 | 2019-09-08T20:00:00+00:00 → 2026-08-24T20:00:00+00:00 |
| `binance.perp.ohlcv.1d.from_15m.v1` | derived | `TRUSTED_DERIVED` | 7214 | 66105439 | 627283 | 627283 | 0 | 853 | 2019-09-09T00:00:00+00:00 → 2026-08-24T00:00:00+00:00 |
| `binance.perp.ohlcv.1d.cache.from_15m` | cache | `FAMILY_CACHE` | 158 | 19022786 | 589254 | n/a | n/a | 790 | 2019-09-08T00:00:00 → 2026-08-06T00:00:00 |
| `binance.perp.panel.1d.ma7_rc.p0` | cache | `FAMILY_CACHE` | 1 | 75592270 | 586612 | n/a | n/a | 790 | None → None |
| `binance.perp.panel.1d.ma7_rc.p3` | cache | `FAMILY_CACHE` | 1 | 165698032 | 627283 | n/a | n/a | 853 | None → None |

## 逐数据集说明

### `binance.perp.ohlcv.15m.normalized.v1`

- layer / timeframe：`normalized` / `15m`
- 物理路径：`/Users/ZK/OpenCode/quant-strategy-lab/data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m`
- 状态 / 声明 scope：`TRUSTED_BASE` / `FULL_MARKET`
- 来源裁决：priority union v1: binance_vision_kline_monthly over binance_futures_kline_api; unlisted sources are excluded, not trusted
- 是否可重建：`False`
- 是否标准 OHLCV：`True`
- builder：`None`
- 行级来源：
  - `binance_vision_kline_monthly`：58123384 行，832 个代码，2020-01-01T00:00:00+00:00 → 2026-07-31T23:45:00+00:00
  - `binance_futures_kline_api`：2316617 行，696 个代码，2019-09-08T17:45:00+00:00 → 2026-08-24T23:45:00+00:00
  - `binance_ccxt`：106465 行，1 个代码，2023-05-07T08:45:00+00:00 → 2026-05-20T08:45:00+00:00
- 每年有效 symbol 数：`{'2019': 2, '2020': 81, '2021': 139, '2022': 163, '2023': 254, '2024': 385, '2025': 613, '2026': 827}`
- P0 union `< 2026-07-01T00:00:00Z`：56358042 行 / 790 个代码；相对已知值 Δ rows `0`、Δ symbols `0`
- P3 union `< 2026-08-25T00:00:00Z`：60266362 行 / 853 个代码；相对已知值 Δ rows `0`、Δ symbols `0`
- critical_null_rows：`106465`
- unclosed_rows：`0`
- illegal_ohlc_rows：`0`
- short_snapshot_symbols：`68`
- long_history_365d_symbols：`534`

### `binance.perp.ohlcv.1h.normalized.legacy`

- layer / timeframe：`normalized` / `1h`
- 物理路径：`/Users/ZK/OpenCode/quant-strategy-lab/data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h`
- 状态 / 声明 scope：`PARTIAL_SCOPE_LEGACY` / `PARTIAL`
- 来源裁决：legacy mixed 1h partitions; majority of codes are 2026-07 snapshots; not a full-market history
- 是否可重建：`False`
- 是否标准 OHLCV：`True`
- builder：`None`
- 行级来源：
  - `binance_fapi_kline_freeze_gap`：222708 行，530 个代码，2026-07-01T00:00:00+00:00 → 2026-07-18T15:00:00+00:00
  - `binance_futures_kline_api`：82693 行，6 个代码，2024-07-30T10:00:00+00:00 → 2026-08-28T10:00:00+00:00
  - `binance_fapi_kline_prospective_oos`：55560 行，530 个代码，2026-07-18T16:00:00+00:00 → 2026-07-23T00:00:00+00:00
  - `binance_vision_kline_monthly_overlap_repair`：31086 行，5 个代码，2023-05-27T00:00:00+00:00 → 2026-06-30T23:00:00+00:00
  - `binance_vision_kline_daily_gap_repair`：7632 行，52 个代码，2022-02-26T00:00:00+00:00 → 2023-03-29T23:00:00+00:00
- 每年有效 symbol 数：`{'2022': 51, '2023': 3, '2024': 5, '2025': 6, '2026': 530}`
- critical_null_rows：`0`
- unclosed_rows：`0`
- illegal_ohlc_rows：`0`
- short_snapshot_symbols：`537`
- long_history_365d_symbols：`6`
- classification_note：`PARTIAL_SCOPE_LEGACY: distinct symbol count is not full-market history`

### `binance.perp.ohlcv.1h.from_15m.v1`

- layer / timeframe：`derived` / `1h`
- 物理路径：`/Users/ZK/OpenCode/quant-strategy-lab/data/derived/datasets/binance_perp_1h_from_15m_v1`
- 状态 / 声明 scope：`TRUSTED_DERIVED` / `FULL_MARKET`
- 来源裁决：resampled from accepted 15m priority union v1; mixed-source bars use composite: sources
- 是否可重建：`True`
- 是否标准 OHLCV：`True`
- builder：`research/platform/data-lake-governance/scripts/build_binance_derived_ohlcv_from_15m.py`
- 已发布：15,066,337 行 / 853 个代码 / 排除不完整桶 513 / 混合来源 1 根；详见 `_MANIFEST.json`

- layer / timeframe：`derived` / `4h`
- 物理路径：`/Users/ZK/OpenCode/quant-strategy-lab/data/derived/datasets/binance_perp_4h_from_15m_v1`
- 状态 / 声明 scope：`TRUSTED_DERIVED` / `FULL_MARKET`
- 来源裁决：resampled from accepted 15m priority union v1; mixed-source bars use composite: sources
- 是否可重建：`True`
- 是否标准 OHLCV：`True`
- builder：`research/platform/data-lake-governance/scripts/build_binance_derived_ohlcv_from_15m.py`
- 已发布：3,766,251 行 / 853 个代码 / 排除不完整桶 795 / 混合来源 1 根；详见 `_MANIFEST.json`

- layer / timeframe：`derived` / `1d`
- 物理路径：`/Users/ZK/OpenCode/quant-strategy-lab/data/derived/datasets/binance_perp_1d_from_15m_v1`
- 状态 / 声明 scope：`TRUSTED_DERIVED` / `FULL_MARKET`
- 来源裁决：resampled from accepted 15m priority union v1; mixed-source bars use composite: sources
- 是否可重建：`True`
- 是否标准 OHLCV：`True`
- builder：`research/platform/data-lake-governance/scripts/build_binance_derived_ohlcv_from_15m.py`
- 已发布：627,283 行 / 853 个代码 / 排除不完整桶 880 / 混合来源 1 根；详见 `_MANIFEST.json`

- layer / timeframe：`cache` / `1d`
- 物理路径：`/Users/ZK/OpenCode/quant-strategy-lab/data/cache/binance_perp_1d_from_15m`
- 状态 / 声明 scope：`FAMILY_CACHE` / `FAMILY_PANEL`
- 来源裁决：month parquet preferred over date=* overlay; not canonical OHLCV
- 是否可重建：`True`
- 是否标准 OHLCV：`False`
- builder：`research/asset-portfolios/1d-monthly-cs-momentum-ls3/scripts/research_binance_1d_mcsm_ls3.py`
- monthly_rows：`581549`
- overlay_rows：`7705`
- overlap_keys：`1658`
- month_first_effective_keys：`587596`
- complete_days_96_closed：`586771`

### `binance.perp.panel.1d.ma7_rc.p0`

- layer / timeframe：`cache` / `1d`
- 物理路径：`/Users/ZK/OpenCode/quant-strategy-lab/data/cache/binance-1d-ma7-rc-p0`
- 状态 / 声明 scope：`FAMILY_CACHE` / `FAMILY_PANEL`
- 来源裁决：family research panel with indicators/labels; not standard OHLCV
- 是否可重建：`True`
- 是否标准 OHLCV：`False`
- builder：`research/asset-portfolios/1d-ma7-regime-continuation/scripts/research_binance_1d_ma7_regime_continuation.py`

### `binance.perp.panel.1d.ma7_rc.p3`

- layer / timeframe：`cache` / `1d`
- 物理路径：`/Users/ZK/OpenCode/quant-strategy-lab/data/cache/binance-1d-ma7-rc-p3`
- 状态 / 声明 scope：`FAMILY_CACHE` / `FAMILY_PANEL`
- 来源裁决：family research panel with indicators/labels; not standard OHLCV
- 是否可重建：`True`
- 是否标准 OHLCV：`False`
- builder：`research/asset-portfolios/1d-ma7-regime-continuation/scripts/run_binance_1d_ma7_regime_p3_confirmatory.py`

## 消费者

详见 [binance_ohlcv_consumers_2026-09-02.csv](../artifacts/binance_ohlcv_consumers_2026-09-02.csv)。
逐 symbol 起止见 [binance_ohlcv_symbol_spans_2026-09-02.csv](../artifacts/binance_ohlcv_symbol_spans_2026-09-02.csv)。

## 已知数字差异

- 15m 文件数与 P0/P3 union 行数/symbols 与任务简述完全一致；15m 字节为 3,074,680,503（约 2.86 GiB），任务简述约 2.9GB，差异来自粗略估计。
- 1h 文件 4,758、物理行 399,679、代码 543 与简述一致；字节 74,343,047 vs 约 76MB。
- 15m `(symbol, ts)` 跨源重复 173,639 行，`within_source` 重复为 0；`binance_ccxt` 106,465 行存在 critical null，且不进入 trusted union。
- 公共日K 完整日 586,771，大于 P0 的 586,612，因为缓存含 `2026-07-01` 之后的完整日。
- 衍生行数以各数据集 `_MANIFEST.json` 为准。

若现场数字与任务简述不同，以本报告 JSON / manifest 为准，不得静默沿用旧数字。

