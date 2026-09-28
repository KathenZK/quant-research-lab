# Binance OHLCV 成交量/成交额差异追溯（2026-09-03）

本报告修正 [2026-09-02 对账](binance-ohlcv-reconciliation-2026-09-02.md) 中把
`1h 成交额再求和不等于 15m 成交额直接求和` 单独当成根因的写法。同一交易范围、同一字段语义、同一时间桶的**原生成交额应可加**；浮点误差按下表事先声明的容差量化，不事后放宽。

独立验证路径使用 `date_trunc('hour') - (hour % 4)` 的 4h 分桶，不调用 `resample_cte_sql` / `aggregate_complete_bars`。

## 事先声明的容差

| 字段 | abs | rel |
| --- | --- | --- |
| `open` | 0.0 | 0.0 |
| `high` | 0.0 | 0.0 |
| `low` | 0.0 | 0.0 |
| `close` | 0.0 | 0.0 |
| `volume` | 1e-09 | 1e-12 |
| `quote_volume` | 1e-06 | 1e-10 |
| `trade_count` | 0.0 | 0.0 |
| `vwap` | 1e-08 | 1e-10 |

`close × volume` 只作为对照代理，不当作原生成交额。

## 独立 15m 重聚 vs 已发布 derived 4h

| symbol | independent_complete_4h | published_4h | matched | only_independent | only_published | open_mismatches | open_max_abs | open_max_rel | high_mismatches | high_max_abs | high_max_rel | low_mismatches | low_max_abs | low_max_rel | close_mismatches | close_max_abs | close_max_rel | volume_mismatches | volume_max_abs | volume_max_rel | quote_volume_mismatches | quote_volume_max_abs | quote_volume_max_rel | trade_count_mismatches | trade_count_max_abs | trade_count_max_rel | vwap_mismatches | vwap_max_abs | vwap_max_rel |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTC/USDT:USDT | 15253 | 15253 | 15253 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1.74623e-10 | 6.36795e-16 | 0 | 7.62939e-06 | 7.97328e-16 | 0 | 0 | 0 | 0 | 8.73115e-11 | 8.68723e-16 |
| ETH/USDT:USDT | 14776 | 14776 | 14776 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1.39698e-09 | 6.80784e-16 | 0 | 3.8147e-06 | 6.21569e-16 | 0 | 0 | 0 | 0 | 4.54747e-12 | 1.06095e-15 |
| SOL/USDT:USDT | 12994 | 12994 | 12994 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 7.45058e-09 | 5.19597e-16 | 0 | 1.43051e-06 | 5.54737e-16 | 0 | 0 | 0 | 0 | 1.42109e-13 | 8.44825e-16 |
| BNB/USDT:USDT | 14326 | 14326 | 14326 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1.86265e-09 | 6.05192e-16 | 0 | 9.53674e-07 | 5.78338e-16 | 0 | 0 | 0 | 0 | 9.09495e-13 | 9.28258e-16 |
| TRX/USDT:USDT | 14452 | 14452 | 14452 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2.38419e-07 | 6.08436e-16 | 0 | 0 | 0 | 0 | 1.66533e-16 | 6.57831e-16 |
| HYPE/USDT:USDT | 2709 | 2709 | 2709 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3.72529e-09 | 5.80947e-16 | 0 | 2.38419e-07 | 5.31633e-16 | 0 | 0 | 0 | 0 | 4.26326e-14 | 8.16765e-16 |

## 重叠完整小时：15m 原生成交额求和 vs legacy 1h 原生 quote_volume

| symbol | overlap_complete_hours | quote_volume_mismatches | quote_volume_max_abs | quote_volume_max_rel | volume_max_abs | native_1h_vs_close_x_volume_max_abs | native_1h_equals_proxy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BTC/USDT:USDT | 28641 | 8 | 2.75827e+08 | 2.83723 | 3959.7 | 4.51627e+08 | False |
| ETH/USDT:USDT | 18974 | 2 | 3.61058e+08 | 8.80729 | 142412 | 8.34645e+08 | False |
| SOL/USDT:USDT | 18984 | 2 | 4.12043e+07 | 3.40834 | 232509 | 2.09834e+08 | False |
| BNB/USDT:USDT | 18983 | 2 | 1.90454e+07 | 14.9881 | 31704.4 | 7.0578e+07 | False |
| TRX/USDT:USDT | 17985 | 4 | 1.05766e+06 | 1.05766e+18 | 6.44906e+06 | 4.88086e+07 | False |
| HYPE/USDT:USDT | 10955 | 0 | 5.96046e-08 | 2.82995e-16 | 9.31323e-10 | 5.40587e+07 | False |

## 公共日K缓存完整日 vs canonical 1d（含成交字段）

公共日K缓存 schema **没有** `volume` / `trade_count`，只有 `quote_volume`。
因此成交量与成交笔数无法对账，记为 `NOT_IN_CACHE_SCHEMA`，不是 0 mismatch。
`quote_volume` 使用事先声明的 abs+rel 容差（不是只看 abs）。

{
  "complete_cache_days": 586771.0,
  "matched_days": 586771.0,
  "quote_volume_mismatches": 0.0,
  "quote_volume_max_abs": 3.814697265625e-05,
  "quote_volume_max_rel": 1.7679924204297635e-15,
  "ohlc_mismatches": 0.0,
  "volume_column_in_cache": false,
  "trade_count_column_in_cache": false,
  "volume_comparison": "NOT_IN_CACHE_SCHEMA",
  "trade_count_comparison": "NOT_IN_CACHE_SCHEMA",
  "cache_schema": [
    "sym_key",
    "base_asset",
    "day",
    "open",
    "high",
    "low",
    "close",
    "quote_volume",
    "bars_15m",
    "all_closed"
  ]
}

## 裁决

- 独立重聚 vs 已发布 derived：`published derived 4h matches independent 15m complete-bucket sums within predeclared tolerances`
- legacy 1h `quote_volume` 与同时段 15m `quote_volume` 之和在容差外大量不一致时，分类为**来源/字段语义不同**（Vision/API 1h K 线的成交额不是 15m 成交额的可加汇总，也不是 `close×volume` 代理）。P0R-DATA 与新研究必须使用 15m 衍生 `quote_volume`。
- 历史报告中的 mismatch 表仍保留；本文件是更正说明，不覆盖 2026-09-02 证据。

机器结果：[binance_ohlcv_volume_rca_2026-09-03.json](../artifacts/binance_ohlcv_volume_rca_2026-09-03.json)；
六资产表：[binance_ohlcv_volume_rca_six_asset_2026-09-03.csv](../artifacts/binance_ohlcv_volume_rca_six_asset_2026-09-03.csv)；
下钻：[binance_ohlcv_volume_rca_drilldown_2026-09-03.csv](../artifacts/binance_ohlcv_volume_rca_drilldown_2026-09-03.csv)。
