# Binance-1H-Adaptive-Regime-Multi-Asset-Ensemble

- Full family name：`Binance-1H-Adaptive-Regime-Multi-Asset-Ensemble`（别名 `BIN-1H-AR-MAE`）
- 市场/周期：Binance USD-M Futures perpetual `1h`；sleeve：`TRXUSDT` / `SOLUSDT` / `HYPEUSDT` / `ETHUSDT` / `BTCUSDT` / `BNBUSDT`
- 机制：六个单资产 `1h` adaptive-regime 最新登记版本的账户级组合；各 sleeve 冻结交易路径不变，组合层只做持仓/资金规则。
- 当前状态：`V1 dry-run / not live-ready`

## 边界

本目录是跨资产组合研究线，不改变成分家族版本身份。V1 成分：`TRX-1H-AR-V3`、`SOL-1H-AR-V2`、`HYPE-1H-AR-V4`、`ETH-1H-AR-V3`、`BTC-1H-AR-V4`、`BNB-1H-AR-V3`。

## 入口

- 主账：[binance-1h-ar-mae-core-ledger.md](binance-1h-ar-mae-core-ledger.md)
- 决策记录：[decision-log.md](decision-log.md)
- V1 完整复现规格：[binance-1h-ar-mae-v1-full-reproduction-spec-2026-07-07.md](specs/binance-1h-ar-mae-v1-full-reproduction-spec-2026-07-07.md)
- V1 简版规格：[binance-1h-ar-mae-v1-single-position-spec-2026-07-07.md](specs/binance-1h-ar-mae-v1-single-position-spec-2026-07-07.md)
- runner-tracking：[binance-1h-ar-mae-v1-runner-status.md](runner-tracking/binance-1h-ar-mae-v1-runner-status.md)

压缩前 README 全文与 notes 清单见 [decision-log.md](decision-log.md) 2026-09-03 条目与主账 Evidence Map。
