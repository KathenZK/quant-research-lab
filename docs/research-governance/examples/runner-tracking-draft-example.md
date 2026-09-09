> **示例，非证据。** 由 `/tmp` 端到端夹具库生成，不是任何真实家族的正式 runner-tracking 报告，不得作为门禁证据。

# EXAMPLE-DRAFT-V0 Runner Tracking DRAFT

> 状态：`DRAFT` / pending evidence review。本文件由脚本生成；**来源追溯、缺项补齐、逐笔对账和差异复核完成前，保持 DRAFT，不作为门禁证据**。
> `TODO(unverified)` 表示缺项或未验证；本报告不证明复核已完成，也不代表实盘启停授权。
>
> 家族：`hype-5m-pullback-trail`
> 实例：`example-dry-run`
> 生成时间（UTC）：`2026-09-03T10:08:05Z`
> 生成命令：`QUANT_RUNNER_LEDGER_DB=/tmp/lab-sync-e2e-ledger.sqlite3 scripts/lab_sync/sync_to_lab.sh /Users/ZK/OpenCode/quant-runner/configs/dryrun.toml example-dry-run 2026-09-03-e2e-fixture /tmp/lab-sync-e2e-5m-pullback-trail`

## 源命令 / DB 快照

- 生成命令：`QUANT_RUNNER_LEDGER_DB=/tmp/lab-sync-e2e-ledger.sqlite3 scripts/lab_sync/sync_to_lab.sh /Users/ZK/OpenCode/quant-runner/configs/dryrun.toml example-dry-run 2026-09-03-e2e-fixture /tmp/lab-sync-e2e-5m-pullback-trail`
- Runner config：`/Users/ZK/OpenCode/quant-runner/configs/dryrun.toml`
- Ledger DB：`/tmp/lab-sync-e2e-ledger.sqlite3`
- status JSON：`/tmp/lab-sync-e2e-5m-pullback-trail/artifacts/runner-tracking/2026-09-03-e2e-fixture/example-dry-run_2026-09-03-e2e-fixture_status.json`
- trades JSON：`/tmp/lab-sync-e2e-5m-pullback-trail/artifacts/runner-tracking/2026-09-03-e2e-fixture/example-dry-run_2026-09-03-e2e-fixture_trades.json`
- events JSON：`/tmp/lab-sync-e2e-5m-pullback-trail/artifacts/runner-tracking/2026-09-03-e2e-fixture/example-dry-run_2026-09-03-e2e-fixture_events.json`

| 文件 | SHA256 |
| --- | --- |
| `example-dry-run_2026-09-03-e2e-fixture_status.json` | `742cefe316f3684d1245e59985f60efa44e3a7955b2ad4803ebc3c91188e337e` |
| `example-dry-run_2026-09-03-e2e-fixture_trades.json` | `86a79f3dfe3f09890f95420bdc9d3cf84fbc479b64d6cb671ae6dd023cc409b5` |
| `example-dry-run_2026-09-03-e2e-fixture_events.json` | `65edff4f3934fdd8ca1575e260b3b05dccd4ee9a8aba9ece99caa65a76f87cb7` |

## 观察窗口

- observation label：`2026-09-03-e2e-fixture`
- 健康更新时间：`2026-09-03T00:01:00Z`
- 窗口起止（待核对）：TODO(unverified)

## Runner 配置摘要

- instance：`example-dry-run`
- strategy_id：`EXAMPLE-DRAFT-V0`
- mode：`dry_run`
- symbol：`HYPEUSDT`
- timeframe：`5m`
- health status：`ok`
- position_open：`false`
- kind / leverage / notional / 账户：TODO(unverified)

## 信号 / bar 时间戳

- last_signal_ts：`2026-09-02T23:55:00Z`
- last_bar_ts：`2026-09-03T00:00:00Z`
- last_signal_side：`1`
- 事件 bar_ts 样本：`2026-09-03T00:00:00Z, 2026-09-02T23:50:00Z`
- signal 事件 ts 样本：`2026-09-02T23:55:00Z`

## 开平仓对账

交易行 `1`，其中已平仓 `1`。CLI `ledger-trades` 不输出 `signal_ts` / 费用 / 订单号；缺项写 TODO(unverified)。

| trade_id | 预期回测入场 | 预期回测出场 | 实际开仓 ts | 实际平仓 ts | 方向 | 数量 | 名义 | 成交价（入） | 成交价（出） | 标记/参考价 | 费用 | 滑点估计 | 订单或事件 ID | match/mismatch |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `trade-1` | TODO(unverified) | TODO(unverified) | `2026-09-02T23:55:00Z` | `2026-09-03T00:05:00Z` | `long` | `1.0` | `10.0` | `10.0` | `10.2` | TODO(unverified) | `0.01` | TODO(unverified) | `ord-1` | TODO(unverified) |

- 预期回测进出场：TODO(unverified)
- 标记/参考价：TODO(unverified)
- 费用（fill 事件样本）：`0.01`
- 滑点估计 vs 回测假设：TODO(unverified)
- 订单/事件 ID 样本：`ord-1`
- 成交价样本：`10.2`
- match/mismatch 结论：TODO(unverified)

## 费用 / 滑点 vs 回测假设

- 实现费用：`0.01`
- 回测费用假设：TODO(unverified)
- 实现滑点：TODO(unverified)
- 回测滑点假设：TODO(unverified)

## 信号 / 指标对拍偏差

TODO(unverified)

## 事件（重启、缺 K、拒单）

Cycle errors：`1`。

| 时间 | 事件类型 | 事件 ID | payload |
| --- | --- | --- | --- |
| `2026-09-03T00:06:00Z` | `cycle_error` | `3` | `{"error": "fixture"}` |

## keep / stop / adjust

- keep：
- stop：
- adjust：
