# HYPE-5M-PBTR-V6.2.1 live halted incident（2026-09-03）

## 结论

待用户决定：重启 / 修正最小名义值 / 退出 pilot

Lab 不推断启停，不修改 quant-runner。

## Runner 配置

| 字段 | 值 |
| --- | --- |
| instance | `hype-pullback-live` |
| strategy_id | `HYPE-5M-PBTR-V6.2.1` |
| kind | `hype_pullback` |
| mode | `live` |
| lock approval_level | `tiny_live_pilot` |
| lock enabled_allowed | `true` |
| approval_expires_at | `2026-12-24T00:00:00Z`（`a5a3b2a` 续期） |
| 并行 dry-run | `hype-pullback-dry-run` 仍授权 |

## 观察窗口与来源

- 来源：服务器 `platform.sqlite3` `events` 表只读查询（用户 2026-09-03 转述）。Lab 未登录操作服务器。
- 健康：`strategy_health.status=halted`
- 自 `2026-08-19T21:31Z` 无新事件
- live 服务本身 `active`，`NRestarts=0`

## 事件链

| 时间 (UTC) | 事件 | 摘要 |
| --- | --- | --- |
| `2026-08-19T21:20Z` | `cycle_error` | `order notional 8.951468 is below Binance minimum 50` |
| `2026-08-19T21:25Z` | `cycle_error` | `pending entry order not found by clientOrderId` |
| `2026-08-19T21:30Z` | `cycle_error` | `pending entry order not found by clientOrderId` |
| 随后 | `runner_started` ×3 | 三次启动事件 |
| `2026-08-19T21:31Z` 起 | 无新事件 | 健康状态保持 `halted` |

## 信号 / 订单 / 成交

本次 incident 未抽取完整开平仓对账表。已知失败点为入场名义低于 Binance 最小 50 USDT，以及随后 pending entry 按 `clientOrderId` 找不到。无新成交事件。

## 费用 / 滑点

未在本次窗口结算；无新 fill。

## 事件（重启、缺 K、拒单）

- 策略健康 `halted`；systemd live 服务仍 `active`、`NRestarts=0`。
- 未报告缺 K。
- 拒单/错误见上表 `cycle_error`。

## keep / stop / adjust

待用户决定：重启 / 修正最小名义值 / 退出 pilot
