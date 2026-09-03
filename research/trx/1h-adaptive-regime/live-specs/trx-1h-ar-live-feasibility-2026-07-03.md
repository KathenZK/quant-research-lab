---
schema_version: "1.0"
spec_role: live_feasibility
family_id: TRX-1H-AR
strategy_id: TRX-1H-AR-LIVE-FEASIBILITY-2026-07-03
spec_status: active
---

# TRX-1H-Adaptive-Regime 实盘可行性审计 - 2026-07-03

## 结论

`NO-GO / not promoted / not live-ready`。领先观察值的下一根开盘 + 即时保护单状态机在工程上可实现，但策略没有通过 prefit 硬门槛，最近三个月 locked OOS 也亏损；仓库中没有生产 runner，因此不能交付为 live、paper-live、dry-run、handoff 或 candidate。

- 审计对象：`ENS__TRX_1H_AR_N131875__TRX_1H_AR_N129128`。
- components：`TRX_1H_AR_N131875+TRX_1H_AR_N129128`。
- baseline 已按 trades / annual / DD / win 四字段逐窗口精确复现第一性结果。

## 执行压力

| Scenario | Full annual | Full DD | Full win | OOS annual | OOS DD | OOS win | OOS trades | Pass |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `baseline_k1` | `4.077x` | `-19.84%` | `86.54%` | `0.844x` | `-11.42%` | `75.00%` | `8` | `False` |
| `delay_k2` | `2.504x` | `-34.46%` | `82.18%` | `0.799x` | `-11.05%` | `75.00%` | `8` | `False` |
| `slippage_8bps` | `2.456x` | `-24.74%` | `81.37%` | `0.407x` | `-24.62%` | `62.50%` | `8` | `False` |
| `delay_k2_slippage_8bps` | `2.208x` | `-34.84%` | `81.19%` | `0.757x` | `-11.55%` | `75.00%` | `8` | `False` |
| `fee_15bps_slippage_8bps` | `2.044x` | `-31.19%` | `81.37%` | `0.363x` | `-25.75%` | `62.50%` | `8` | `False` |

## 订单时序

- `K` 完整闭合后计算信号，`K+1 open` 发送市价单；不使用 K 内未来信息。
- 成交后立即提交 reduce-only stop-market；fixed TP 使用 reduce-only take-profit-market。trailing 只使用已闭合 K 的 high/low 更新，并从下一根 K 生效。
- 同 K stop/target 双触发按 stop-first；open 跳过 stop 时按首个可成交 open 加不利滑点退出。
- 单仓、不加仓；ensemble 冲突按 prefit score 冻结优先级，不读取 OOS 排序。

## 合约过滤器与运行控制

- `tickSize=0.00001`，按最后 close `0.31702` 约 `0.315 bps/tick`；`stepSize=1`，`MIN_NOTIONAL=5 USDT`。价格按方向保守取整，数量向下取整。
- 每次启动必须核对 `TRXUSDT` 状态、过滤器、账户 position mode、杠杆与 margin type；本次只有快照，没有假定它永久不变。
- 缺 K、时钟漂移、资金费/行情陈旧时禁止新开仓；重启先以交易所仓位和保护单为真相源恢复状态。
- 必须有最大账户回撤、单笔风险、连续下单失败、保护单丢失和数据陈旧 kill switch；当前仓库未实现这些生产能力。

## 最终边界

工程可执行不等于策略可实盘。由于性能 gate 和 OOS gate 均失败，不生成 live spec。后续主账登记的 `TRX-1H-Adaptive-Regime-V1` 为 diagnostic baseline，`TRX-1H-Adaptive-Regime-V2` 为 V1 逐交易等价的 clean 参数版本；二者都不改变本审计的 `NO-GO / not live-ready` 结论。

## 产物

- `research/trx/1h-adaptive-regime/artifacts/trx_1h_live_feasibility_2026-07-03.json`
