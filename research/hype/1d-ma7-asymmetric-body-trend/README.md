# HYPE-1D-MA7-Asymmetric-Body-Trend

- Full family name：`HYPE-1D-MA7-Asymmetric-Body-Trend`（别名 `HYPE-1D-MA7-ABT`）
- 市场/周期：Binance USD-M `HYPEUSDT` perpetual，UTC `1d`
- 机制：固定 `SMA7` 的非对称日线趋势状态机（reclaim / 迟滞 / OAPP / PEHC）。
- 当前状态：`V7.1 dry-run / not live-ready`；`V1–V7 registered / TRANSFER_FAIL / HARD-GATE-FAILED / not promoted / not live-ready`

## 边界

- 固定 `SMA7`、`1x`、非加仓；不是 `HYPE-1D-Pyramiding-Trend`、`HYPE-1D-Multi-Horizon-EMA-Forecast` 或无订单的 `Binance-1D-MA7-Deviation-Continuation`。
- “MA7 不穿过实体”的字面版与方向性反转版必须同时保留，不得静默改写。
- 多空分离及后继失败分支是 diagnostic，不能把已揭示历史上的盈利候选当作 OOS 或 promotion 证据。

## 入口

- 主账：[hype-1d-ma7-abt-core-ledger.md](hype-1d-ma7-abt-core-ledger.md)
- 决策记录：[decision-log.md](decision-log.md)
- V7.1 规格：[hype-1d-ma7-abt-v7-1-spec.md](specs/hype-1d-ma7-abt-v7-1-spec.md)
- V7.1 Lab live spec：[hype-1d-ma7-abt-v7-1-lab-live-spec.md](live-specs/hype-1d-ma7-abt-v7-1-lab-live-spec.md)
- 产物说明：[artifacts/README.md](artifacts/README.md)

压缩前 README 全文与完整证据链接清单见 [decision-log.md](decision-log.md) 2026-09-03 条目。
