# HYPE-1D-MA7-ABT-V7.1 Dry-run 首笔闭合对账 2026-09-07

## 结论

第一笔 dry-run 多单已平。原因是 OAPP（`long_mfe_fraction_trail_exit`），实现净盈约 **+2.12% / +0.21 USDT**。实例现为空仓。keep。这是 1/5 闭合样本，不能当作 `dry-run -> live` 对账完成。

## 来源

- 远程账本：`admin@47.80.57.36:/home/admin/quant-runner/state/platform/platform.sqlite3`
- 实例：`hype-1d-ma7-abt-v7-1-dry-run` / `HYPE-1D-MA7-ABT-V7.1` / `dry_run`
- 数据：[`hype_1h_prospective_sync_2026-09-07.json`](../artifacts/hype_1h_prospective_sync_2026-09-07.json) 至 2026-09-07 07:00 UTC
- 快照：[`hype_1d_ma7_abt_v7_1_dry_run_closed_trade_2026-09-07.json`](../artifacts/hype_1d_ma7_abt_v7_1_dry_run_closed_trade_2026-09-07.json)

## 观察窗

2026-08-13 空仓启动 → 2026-09-07 08:00 UTC。该实例 1 笔 closed，0 笔 open。

## 实际开平

| 字段 | 值 |
| --- | --- |
| trade_id | `HYPE-1D-MA7-ABT-V7.1-2026-08-29T00:00:00+00:00` |
| 入场 | 2026-08-30 00:00 UTC / 83.412 / `ma7_reclaim_long` |
| 出场 | 记录 `exit_ts` 2026-09-06 00:00 UTC；实际 fill 事件 2026-09-06 **01:00** UTC |
| 出场价 | 85.347（raw avg 85.381 − 4 bps） |
| 原因 | `long_mfe_fraction_trail_exit` |
| 持有 | 7 个完整日；日线 MFE 收盘 2026-09-03 / 87.459（+4.85%） |
| 数量 / 入场名义 | 0.119 / 9.926 USDT |
| 毛利 | +0.230 USDT / **+2.32%** |
| 估计手续费 | 0.020 USDT（双边 10 bps） |
| 净利 | 账本 `net_pnl_usdt` 为空；按毛利−费用为 **+0.210 USDT / +2.12%** |

## 与研究对照

Sep 4 / Sep 5 连续两日收盘仍低于峰值收盘的 10% MFE 回吐线，V7.1 应在下一 UTC 开盘 OAPP 离场。研究窗末日是 2026-09-06，回放把同一根开盘记成 `terminal_flatten @ 85.381`，时点与参考开盘价与 runner 一致，原因字段被窗截断覆盖。

## 事件 / 事故

- 2026-09-06 00:00 UTC `cycle_error`：`missing Binance kline at 2026-09-06 00:00:00 UTC`。湖里该小时 K 存在（开 85.381）。出场因此推迟到 01:00。
- 01:00 fill 仍用 00:00 开盘 85.381 减 4 bps，价格未漂到 01:00 开盘 85.361。该小时最低 84.641、最高 86.378。
- 平仓后 PEHC shadow 仍在（剩余 7 日，峰值 close 87.977）；`cooldown_remaining=1`；无新仓。
- 平仓后 2026-09-06 最高 89.666、收盘 87.985。若持有到查询时 1h 收盘 86.364，价格变动约 +3.54%。这不改变 OAPP 合同。

## keep / stop / adjust

keep。观察门仍是至少 90 天或 5 笔闭合交易。本笔方向/原因/参考开盘匹配，但存在 1 小时缺 K 延迟与账本净利空值，线上开平仓对账未完成。
