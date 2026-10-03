# PUBLIC-M0220-BTC-MOMENTUM Core Ledger

## Family Identity

- 稳定ID M0220；变体 `M0220-BTCUSDT-WEEKLY20EMA-LOWTRAIL-20261003`。
- Binance BTCUSDT spot / UTC日线，已完成UTC周EMA20、日EMA20/ATR5、最高low跟踪止损。
- 作者源码锁版，原catalog冲突另列；种子、周映射、含费现金预算和滑点使本轮为HYPOTHESIS，不是平台严格复现。

## Current State

`explore / not promoted / not live-ready`；不登记可晋级Vx，没有生产runner/实盘。

| Version | Status | 结论 | Evidence |
| --- | --- | --- | --- |
| 20261003-first-replay | explore | 617日、58成交；收益98.27%、回撤26.96%；同窗持有239.73%、回撤26.15% | [报告](diagnostics/M0220-20261003.md) |

## Shared Assumptions

[规格](specs/M0220-first-replay.json)：20完整周预热，Apr24首决策/Apr25首成交；初始10,000、100%现金含手续费、单边10bps费+2bps滑点。跟踪止损依前日谨慎、当前ATR，只抬高，收盘触发下一真实open市价，不是盘中stop。窗口已经曝光。

## Evidence Map

[验证](artifacts/20261003-first-replay/validation.json) · [输入引用](artifacts/20261003-first-replay/input-reference.json) · [冻结清单](artifacts/20261003-first-replay/result-manifest.json) · [重建](diagnostics/rebuild-20261003.md) · [署名](SOURCE-ATTRIBUTION.md)。

下一门槛：原TradingView逐bar映射比对、更早预热和新窗口。任何改动另立冻结版本，不能覆盖当前结果或据当前回报晋级。
