# Binance OHLCV 成交额差异追溯 R3（2026-09-03）

本轮不覆盖 [第二轮 RCA](binance-ohlcv-volume-rca-2026-09-03.md)。容差与第二轮相同，事先冻结，不事后扩大。
独立 4h 重聚不调用 `resample_cte_sql` / `aggregate_complete_bars`。
新派生聚合正确 ≠ 旧 1h 差异已解释。缺本地 raw 记 `UNRESOLVED`，本轮不下载补证。

## 事先冻结的容差

| field | abs | rel |
| --- | --- | --- |
| open | 0 | 0 |
| high | 0 | 0 |
| low | 0 | 0 |
| close | 0 | 0 |
| volume | 1e-09 | 1e-12 |
| quote_volume | 1e-06 | 1e-10 |
| trade_count | 0 | 0 |
| vwap | 1e-08 | 1e-10 |

## 独立 15m 重聚 vs 已发布 derived 4h

| symbol | independent_complete_4h | published_4h | matched | only_independent | only_published | open_mismatches | open_max_abs | open_max_rel | high_mismatches | high_max_abs | high_max_rel | low_mismatches | low_max_abs | low_max_rel | close_mismatches | close_max_abs | close_max_rel | volume_mismatches | volume_max_abs | volume_max_rel | quote_volume_mismatches | quote_volume_max_abs | quote_volume_max_rel | trade_count_mismatches | trade_count_max_abs | trade_count_max_rel | vwap_mismatches | vwap_max_abs | vwap_max_rel |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTC/USDT:USDT | 15253 | 15253 | 15253 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1.74623e-10 | 6.1905e-16 | 0 | 3.8147e-06 | 6.0993e-16 | 0 | 0 | 0 | 0 | 8.73115e-11 | 9.5621e-16 |
| ETH/USDT:USDT | 14776 | 14776 | 14776 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1.86265e-09 | 5.85344e-16 | 0 | 3.8147e-06 | 5.91596e-16 | 0 | 0 | 0 | 0 | 3.18323e-12 | 8.56303e-16 |
| SOL/USDT:USDT | 12994 | 12994 | 12994 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5.58794e-09 | 5.16515e-16 | 0 | 1.90735e-06 | 6.02927e-16 | 0 | 0 | 0 | 0 | 1.13687e-13 | 8.30852e-16 |
| BNB/USDT:USDT | 14326 | 14326 | 14326 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1.86265e-09 | 6.13838e-16 | 0 | 9.53674e-07 | 5.89429e-16 | 0 | 0 | 0 | 0 | 9.09495e-13 | 8.6178e-16 |
| TRX/USDT:USDT | 14452 | 14452 | 14452 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2.38419e-07 | 5.99727e-16 | 0 | 0 | 0 | 0 | 1.66533e-16 | 6.46059e-16 |
| HYPE/USDT:USDT | 2709 | 2709 | 2709 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3.72529e-09 | 5.4493e-16 | 0 | 2.38419e-07 | 5.9787e-16 | 0 | 0 | 0 | 0 | 5.68434e-14 | 8.3553e-16 |

裁决：`published derived 4h matches independent 15m complete-bucket sums within predeclared tolerances`

## 重叠完整小时：15m quote_volume 求和 vs legacy 1h 原生 quote_volume

| symbol | overlap_complete_hours | quote_volume_mismatches | quote_volume_max_abs | quote_volume_max_rel | volume_max_abs | native_1h_vs_close_x_volume_max_abs | native_1h_equals_proxy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BTC/USDT:USDT | 28641 | 8 | 2.75827e+08 | 2.83723 | 3959.7 | 4.51627e+08 | False |
| ETH/USDT:USDT | 18974 | 2 | 3.61058e+08 | 8.80729 | 142412 | 8.34645e+08 | False |
| SOL/USDT:USDT | 18984 | 2 | 4.12043e+07 | 3.40834 | 232509 | 2.09834e+08 | False |
| BNB/USDT:USDT | 18983 | 2 | 1.90454e+07 | 14.9881 | 31704.4 | 7.0578e+07 | False |
| TRX/USDT:USDT | 17985 | 4 | 1.05766e+06 | 1.05766e+18 | 6.44906e+06 | 4.88086e+07 | False |
| HYPE/USDT:USDT | 10955 | 0 | 1.19209e-07 | 3.0669e-16 | 9.31323e-10 | 5.40587e+07 | False |

实质差异小时数：`18`。分类计数：`{"SOURCE_REVISION": 9, "SEMANTIC_DIFFERENCE_WITH_LOCAL_RAW_EVIDENCE": 4, "RAW_1H_EQUALS_FIRST_15M_COMPONENT": 4, "PROXY_FIELD": 1}`。

## 逐小时追溯

| symbol | ts_utc | abs_err | classification | raw_15m_missing | raw_1h_missing |
| --- | --- | --- | --- | --- | --- |
| BTC/USDT:USDT | 2023-11-10T15:00:00+00:00 | 7.51247e+07 | SOURCE_REVISION | False | False |
| BTC/USDT:USDT | 2024-03-28T10:00:00+00:00 | 9677.11 | SOURCE_REVISION | False | False |
| BTC/USDT:USDT | 2024-03-28T11:00:00+00:00 | 1.61262e+07 | SOURCE_REVISION | False | False |
| BTC/USDT:USDT | 2024-03-28T12:00:00+00:00 | 5861.37 | SOURCE_REVISION | False | False |
| BTC/USDT:USDT | 2023-11-10T16:00:00+00:00 | 5.3432e+07 | SOURCE_REVISION | False | False |
| BTC/USDT:USDT | 2024-10-28T20:00:00+00:00 | 1.11789e+08 | SEMANTIC_DIFFERENCE_WITH_LOCAL_RAW_EVIDENCE | False | False |
| BTC/USDT:USDT | 2024-03-27T12:00:00+00:00 | 3.31149e+07 | SOURCE_REVISION | False | False |
| BTC/USDT:USDT | 2024-10-28T21:00:00+00:00 | 2.75827e+08 | RAW_1H_EQUALS_FIRST_15M_COMPONENT | False | False |
| ETH/USDT:USDT | 2024-10-28T20:00:00+00:00 | 1.97426e+07 | SEMANTIC_DIFFERENCE_WITH_LOCAL_RAW_EVIDENCE | False | False |
| ETH/USDT:USDT | 2024-10-28T21:00:00+00:00 | 3.61058e+08 | RAW_1H_EQUALS_FIRST_15M_COMPONENT | False | False |
| SOL/USDT:USDT | 2024-10-28T20:00:00+00:00 | 8.95911e+06 | SEMANTIC_DIFFERENCE_WITH_LOCAL_RAW_EVIDENCE | False | False |
| SOL/USDT:USDT | 2024-10-28T21:00:00+00:00 | 4.12043e+07 | RAW_1H_EQUALS_FIRST_15M_COMPONENT | False | False |
| BNB/USDT:USDT | 2024-10-28T20:00:00+00:00 | 2.33767e+06 | SEMANTIC_DIFFERENCE_WITH_LOCAL_RAW_EVIDENCE | False | False |
| BNB/USDT:USDT | 2024-10-28T21:00:00+00:00 | 1.90454e+07 | RAW_1H_EQUALS_FIRST_15M_COMPONENT | False | False |
| TRX/USDT:USDT | 2025-01-14T15:00:00+00:00 | 236490 | SOURCE_REVISION | False | False |
| TRX/USDT:USDT | 2025-01-14T13:00:00+00:00 | 543732 | SOURCE_REVISION | False | False |
| TRX/USDT:USDT | 2024-10-28T20:00:00+00:00 | 1.05766e+06 | PROXY_FIELD | False | False |
| TRX/USDT:USDT | 2024-10-28T21:00:00+00:00 | 165045 | SOURCE_REVISION | False | False |

## Blockers

- legacy native 1h quote_volume mismatches 15m sums; see hour classifications, not a blanket semantic claim

旧源裁决：`explained_with_local_evidence`。

机器结果：[binance_ohlcv_volume_rca_r3_2026-09-03.json](../artifacts/binance_ohlcv_volume_rca_r3_2026-09-03.json)；
六资产表：[binance_ohlcv_volume_rca_r3_six_asset_2026-09-03.csv](../artifacts/binance_ohlcv_volume_rca_r3_six_asset_2026-09-03.csv)；
小时追溯：[binance_ohlcv_volume_rca_r3_hour_trace_2026-09-03.csv](../artifacts/binance_ohlcv_volume_rca_r3_hour_trace_2026-09-03.csv)；
组成 K 线：[binance_ohlcv_volume_rca_r3_components_2026-09-03.csv](../artifacts/binance_ohlcv_volume_rca_r3_components_2026-09-03.csv)。
