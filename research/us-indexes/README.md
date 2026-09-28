# US Indexes Research Index

本目录存放美国股票价格指数及其跨指数研究。价格指数不可直接下单；指数研究不得静默解释为 ETF、期货、期权或 total-return 产品的可执行结论。


## 状态

本目录家族状态列写 `见顶层`，以 [research/README.md](../README.md) 为准。

| Directory | 状态 |
| --- | --- |
| [1d-ma7-shared-parameter-transfer/](1d-ma7-shared-parameter-transfer/README.md) | 见顶层 |
| [1d-nasdaq100-ma7-regime-continuation/](1d-nasdaq100-ma7-regime-continuation/README.md) | 见顶层 |

## 当前研究线

- `US-Indexes-1D-MA7-Shared-Parameter-Transfer`（`USI-1D-MA7-SP-XFER`）：[1d-ma7-shared-parameter-transfer/](1d-ma7-shared-parameter-transfer/README.md)。把 BTC/ETH 共享 `SMA7/ATR7` 参数零调参应用于 Yahoo `^GSPC` 和 `^IXIC`；两者 combined 均远逊 buy-and-hold，成本后失败，`explore / not promoted / not live-ready`。主账：[us-indexes-1d-ma7-sp-xfer-core-ledger.md](1d-ma7-shared-parameter-transfer/us-indexes-1d-ma7-sp-xfer-core-ledger.md)。
- `Nasdaq100-1D-MA7-Regime-Continuation`（`NDX100-1D-MA7-RC`）：[1d-nasdaq100-ma7-regime-continuation/](1d-nasdaq100-ma7-regime-continuation/README.md)。P0 Massive 历史权限受阻；Y1 历史覆盖 `81.18%`。Y3 突破前结构图谱发现多头有效候选集中于“深回撤后早期修复/空头趋势反转”，10–40D 增量保持且不只由 gap 驱动；低波底座、牛市浅回踩和空头延续假设不支持。仍是当前成分回填的 hypothesis generation，`explore / diagnostic-only / not promoted / not live-ready`。主账：[ndx100-1d-ma7-rc-core-ledger.md](1d-nasdaq100-ma7-regime-continuation/ndx100-1d-ma7-rc-core-ledger.md)。
