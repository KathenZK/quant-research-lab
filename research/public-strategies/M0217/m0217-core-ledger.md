# BTC-1D-M0217-VOLATILITY-BREAKOUT Core Ledger

## Family Identity

原表稳定 ID M0217。Binance BTCUSDT 现货、UTC 日线。昨日收盘加 0.8 倍昨日振幅作为日内突破买入门槛；触发当天收盘退出。原帖不可读，昨日振幅、当天退出及 BTCUSDT 皆为显式假设；不等同作者严格原策略。

## Current State

`explore / not promoted / not live-ready`；没有生产授权或 runner 操作。

| Version | Status | 结论 | Evidence |
| --- | --- | --- | --- |
| M0217-BTCUSDT-PREVIOUS-RANGE-08-SAME-DAY-20261003（未登记 Vx） | explore / HYPOTHESIS | 731 日、210 往返；基准收益 36.89%，每边费用 20bps 时亏损 15.25%；成本脆弱 | [逐策略报告](diagnostics/M0217-20261003.md) |

## Shared Assumptions

[规格](specs/M0217-first-replay.json)：95%现金名义金额，8bps手续费与2bps滑点各按单边；0/20bps手续费敏感性固定滑点2bps。无做空、杠杆或日内止损。2023–2024已曝光历史窗口，不能称未看样本外。

## Evidence Map

[结果指纹](artifacts/20261003-first-replay/result-manifest.json) · [独立核验](artifacts/20261003-first-replay/validation.json) · [本地重建比较](artifacts/20261003-first-replay/local-recovery.json)。

后续先解决作者规则和成交路径不确定性，另立冻结变体或新窗口，不能改写当前结果。
