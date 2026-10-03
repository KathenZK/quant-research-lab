# PUBLIC-M0214-SMA-HA Core Ledger

## Family Identity

- 稳定ID：M0214；变体 `M0214-BTCUSDT-SMA10-20-HA-CROSS-LONG-20261003`。
- Binance BTCUSDT spot / 1d UTC；SMA10/20趋势过滤、价格上穿SMA10、平均K转绿。
- 原表含做空相反和可选Bend10。本轮删除做空并关闭Bend10，定为ADAPTATION；不声称补全原策略或登记可晋级Vx。

## Current State

`explore / not promoted / not live-ready`；没有交易、runner或部署动作。

| Version | Status | 结论 | Evidence |
| --- | --- | --- | --- |
| 20261003-first-replay（未登记Vx） | explore | 731日、24笔成交；收益43.89%、回撤11.74%；持有442.23%，延迟收益28.52% | [报告](diagnostics/M0214-20261003.md) |

## Shared Assumptions

[规格](specs/M0214-first-replay.json)固定价格fresh cross与HA转绿同日、95%现金、8bps费、2bps滑点、真实下一开盘成交。HA仅用于信号。历史窗口已经曝光，不是未看样本外。

## Evidence Map

[输入引用](artifacts/20261003-first-replay/input-reference.json) · [结果指纹](artifacts/20261003-first-replay/result-manifest.json) · [验证](artifacts/20261003-first-replay/validation.json) · [重建](diagnostics/rebuild-20261003.md)。

下一门槛：合法原文核验、独立窗口及原双向适配数据。任何语义/方向/参数扩展另立冻结版本，不覆盖本次证据。
