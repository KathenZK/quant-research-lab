# BTC-1D-M0215-RSI2-SNAPBACK Core Ledger

## Family Identity

- 原表稳定 ID：M0215；本次变体 `M0215-BTCUSDT-RSI2-WILDER-20261003`。
- Binance BTCUSDT / spot / 1d UTC。RSI2<10 进场，昨日收盘突破两日前最高价离场。
- 边界：只测原列 BTC/ETH/XRP/LTC/ADA 中 BTC；Wilder 种子、市场、仓位、成本、日期属于显式假设，不登记严格复现或可晋级 Vx。

## Current State

`explore / not promoted / not live-ready`；没有 runner 或实盘动作。

| Version | Status | 结论 | Evidence |
| --- | --- | --- | --- |
| 20261003-first-replay（未登记Vx） | explore | 731日、72成交；收益56.63%，回撤19.53%；同成本持有442.23%，延迟后收益28.37% | [报告](diagnostics/M0215-20261003.md) |

## Shared Assumptions

[规格](specs/M0215-first-replay.json)冻结 Wilder RSI2、95%现金、8bps费用、2bps滑点、下一开盘、长仓无杠杆，无期末强平。原始完整规则未经直接原帖复核，原帖返回403。窗口非未看样本外。

## Evidence Map

[独立验证](artifacts/20261003-first-replay/validation.json) · [输入引用](artifacts/20261003-first-replay/input-reference.json) · [结果清单](artifacts/20261003-first-replay/result-manifest.json) · [复建](diagnostics/rebuild-20261003.md)。

下一门槛是合法复核原帖、原五币篮子与其他市场阶段；只有另建冻结变体才可扩展，不覆盖本次。
