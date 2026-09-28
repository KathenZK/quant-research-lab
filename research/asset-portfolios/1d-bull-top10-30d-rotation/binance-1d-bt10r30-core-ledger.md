# Binance-1D-Bull-Top10-30D-Rotation Core Ledger

## Family Identity

- Binance USDT永续 / 日线选币 / 固定30日持有；`BIN-1D-BT10R30`。
- 牛市下买过去30日Top10，等权；独立于4H RSI/ATR与日历月Top10家族。

## Current State

- `explore / diagnostic-only / not promoted / not live-ready`。
- P0两种规则回放完成：完整轮次支持继续检验简单动量，但BNX终止/结算事件导致完整账户路径未贯通，账户证据为`DATA_OR_REPRODUCTION_FAILURE`。
- 下一门：核验真实结算价值后按原规则复跑完整资金链，再做新未来验证；不把完整轮次均值接成复利账户。funding、PIT和实际订单执行尚未验证。

## Version Rules

- P0仅为观察，不是V1，不触发晋升。

## Version Table

| 观察 | 状态 | 规则 | 证据 | 决定 |
| --- | --- | --- | --- | --- |
| P0 | explore / diagnostic-only | 牛市组33个完整30日轮次均值+10.92%、中位数+2.20%；无牛市对照72轮均值+1.30%，均扣手续费与4bps滑点、未扣funding | [契约](specs/p0-contract.md) · [报告](diagnostics/p0-results-2026-09-07.md) | 轮次证据保留；BNX结算阻塞全账户，不登记、不晋升 |

## Shared Assumptions

- 组合v2日线与4H，UTC 00:00信号、04:00执行；每边0.1%手续费与4/8bps滑点，未扣funding。

## Evidence Map

- [配置](specs/p0-config.json) · [产物](artifacts/README.md)
- [逐轮统计](artifacts/p0-20260907/round-summary.csv) · [账户路径状态](artifacts/p0-20260907/summary.json) · [验算](artifacts/p0-20260907/acceptance.json)
