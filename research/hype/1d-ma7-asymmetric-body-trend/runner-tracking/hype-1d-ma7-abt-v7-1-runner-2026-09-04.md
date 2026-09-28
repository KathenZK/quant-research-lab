# HYPE-1D-MA7-ABT-V7.1 Dry-run 开仓观察 2026-09-04

## 结论

`hype-1d-ma7-abt-v7-1-dry-run` 已开出第一笔自然多单，且截至 2026-09-04 12:00 UTC 仍持有。这不是闭合交易对账，也不能当作 `dry-run -> live` 门禁通过。keep。

## 来源

- 远程账本：`admin@47.80.57.36:/home/admin/quant-runner/state/platform/platform.sqlite3`
- 实例：`hype-1d-ma7-abt-v7-1-dry-run` / `HYPE-1D-MA7-ABT-V7.1` / `dry_run`
- 服务：`quant-runner-dryrun` 周期日志 `event=holding`
- 研究对照：同步后 exact V7.1 CONTROL 回放；数据至 [`hype_1h_prospective_sync_2026-09-04.json`](../artifacts/hype_1h_prospective_sync_2026-09-04.json)
- 快照：[`hype_1d_ma7_abt_v7_1_dry_run_open_trade_2026-09-04.json`](../artifacts/hype_1d_ma7_abt_v7_1_dry_run_open_trade_2026-09-04.json)

## 观察窗

- Dry-run 自 2026-08-13 空仓启动，不重建 2026-08-09 研究路径多头。
- 本报告抽取窗：2026-08-13 → 2026-09-04 12:00 UTC。
- 库内该实例交易：1 笔 open，0 笔 closed。
- 最后完整 UTC 日：2026-09-03；1h 湖最新收盘：2026-09-04 11:00 UTC / 87.231。

## 实际开仓

| 字段 | 值 |
| --- | --- |
| trade_id | `HYPE-1D-MA7-ABT-V7.1-2026-08-29T00:00:00+00:00` |
| side / status | long / open |
| signal_ts | 2026-08-29 00:00 UTC |
| entry_ts | 2026-08-30 00:00 UTC |
| reason | `ma7_reclaim_long` |
| 成交价 | 83.4123516（参考 `current_contract_price` 83.379 + 4 bps） |
| 数量 / 名义 | 0.119 / 9.926 USDT |
| 信号日 MA7 / ATR7 | 81.726 / 5.477 |
| 当前 1h trail | 79.795（2026-09-04 00:00 `abt_trailing_stop_update`） |
| bars_held | 5 个完整日 |
| 相对最新 1h 收盘 | 约 +4.6% 价格变动，未实现盈亏未入账 |

## 与研究回放对照

研究 exact V7.1 在 2026-08-16 OAPP 平仓后，下一笔也是 2026-08-29 收盘 reclaim、2026-08-30 00:00 开多。日线开盘参考价 83.368；runner 用当时合约价，相对日开约 +5.3 bps，其中 4 bps 为默认滑点。方向、信号日、成交时点、原因一致。

回放把窗口末日 2026-09-03 记成 `terminal_flatten @ 81.881`，这是研究窗截断，不是 runner 平仓。实例此时仍 `holding`。

## 事件 / 事故

- 无重启、缺 K、拒单记录进入本报告。
- 2026-09-04 00:00 UTC 绑定新 stop（`execution_v2_order_bound` / `role=stop_loss` / `status=NEW`），属策略管理的 trail 更新。
- Live 实例仍禁用；本报告不改变 runner 授权。

## keep / stop / adjust

keep。观察门仍是至少 90 天或 5 笔闭合交易；当前 0 笔闭合，线上开平仓对账未完成。
