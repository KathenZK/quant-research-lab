# BTC-1D-M0216-SMA-CROSS Core Ledger

## Family Identity

- 身份：原表 M0216；Binance BTCUSDT spot / 1d；SMA11/20 交叉，源风控门。
- 本次 ID：M0216-BTCUSDT-SMA11-20-SOURCE-GATE-20261003。没有登记可晋级 Vx。
- 边界：真实数据的来源锚定假设回测；不等于严格复现，不等于 BTC/EUR PRICE_SMA。

## Current State

`explore / not promoted / not live-ready`；未触及 runner。

| Version | Status | 结论 | Evidence |
| --- | --- | --- | --- |
| 20261003-first-replay（未登记Vx） | explore | 731日、3成交；源门停机不平仓；总收益351.05%落后同成本买入持有442.23%，最大回撤25.70% | [报告](diagnostics/M0216-20261003.md) |

## Shared Assumptions

[规格](specs/M0216-first-replay.json)固定31日预热、2023–2024历史窗口、下一开盘、8bps手续费、2bps滑点及95%现金。无做空/杠杆/资金费、无期末强平。历史曝光未知，不声称未看样本外。

## Evidence Map

[结果清单](artifacts/20261003-first-replay/result-manifest.json) · [独立验证](artifacts/20261003-first-replay/validation.json) · [输入验收](artifacts/20261003-first-replay/input-manifest.json)。

下一步只可另立变体检验风险语义修复与新窗口；不得覆盖当前冻结证据或据此晋级。
