# BIN-1D-MA7-CTP 冻结口径

> 2026-08-31。`explore / diagnostic-only / not promoted / not live-ready`。本合同在看结果前冻结；阈值不按结果回改。

## 研究问题

BTC/ETH/BNB/SOL 永续日K在收盘穿越 SMA7 之后，发生一段顺向趋势的条件概率是多少？加上同向斜率、成交额放大、以及穿越前 7/30/60/90 日最大上涨/回撤比之后，概率如何变化？

## 数据

- Binance USD-M perpetual；`BTC/USDT:USDT`、`ETH/USDT:USDT`、`BNB/USDT:USDT`、`SOL/USDT:USDT`。
- 完整 UTC 日K，由 24 根已闭合 `1h` 聚合；来源 `binance_futures_kline_api_direct` feature 层 `data/features/binance_1d_ma7_rsi6_dapml_p0/`。
- 只用 `is_closed=true`；区间内缺日即失败。
- 各币用自己的上市日到数据终点；共同窗口从 `2020-09-15` 起；最近 365 日只作审计。

## 事件

- `SMA7[t] = mean(close[t-6:t])`。
- 多头穿越：`close[t-1] < SMA7[t-1]` 且 `close[t] > SMA7[t]`。空头镜像。等号不算穿越。
- 斜率：`(SMA7[t]-SMA7[t-1])/ATR7[t]`；符号过滤要求同向；硬门槛 `0.02`。
- 放量：当日 `quote_volume` / 近 20 日中位数；门槛 `1.2 / 1.5 / 2.0`，主看 `1.5`。
- 前置路径只用 `t-W…t-1` 收盘。最大回撤与最大上涨按收盘路径的峰值/谷值；`R = 最大上涨 / 最大回撤`。

## 标签

- 主标签 `trend_20`：穿越日收盘为原点，穿越前 ATR7 为尺度，随后 20 个收盘先到顺向 `+2 ATR`，且未先到反向 `-1 ATR`。
- 辅标签：`mfe2_20`、`win_20`、`persist_5`、`recross_ge_5`。
- 无手续费、滑点、资金费、下一开盘成交。不是账户回测。

## 全市场宇宙附录

同日冻结，不改事件/标签/过滤器。只换数据宇宙。

- 数据：`data/cache/binance_perp_1d_from_15m`。Binance USD-M 永续 Vision 月档 `15m` 聚合成 UTC 日K；月档优先，`overlay_date_partitions.parquet` 只补月档没有的日子。
- 面板：`2020-01-01` 至 `2026-06-30`。切断是为了避免 7 月以后只剩少数大币、把全市场样本悄悄缩小。
- 完整日：`bars_15m=96` 且 `all_closed=true`。每个合约至少 120 个完整日才入选。
- 完整日按时间顺序当作 session 序列，与 TPSA 相同；不把不完整日插回日历再 `asfreq`。
- 剔除稳定币、指数合约（与 MCSM 相同）以及美股代币化标的（与 TPSA 相同）。
- 最近 365 日锚定面板终点 `2026-06-30`，只作审计。
- 四币 API 小时K聚合（终点 2026-08-09）与本缓存不是同一数据源，大币数字只作量级对照，不逐笔对账。

## 非目标

不搜索阈值，不登记版本，不写入 runner，不把条件概率当成扣成本后的胜率。
