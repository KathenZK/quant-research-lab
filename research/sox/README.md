# SOX Research Index

本目录存放 PHLX Semiconductor Index（Yahoo `^SOX`）及其可交易代理的单资产研究。指数本身不可直接下单；指数数据研究不得静默写成 ETF、期货或期权的可执行结论。


## 状态

本目录家族状态列写 `见顶层`，以 [research/README.md](../README.md) 为准。

| Directory | 状态 |
| --- | --- |
| [1d-ma7-asset-specific-search/](1d-ma7-asset-specific-search/README.md) | 见顶层 |
| [1d-ma7-separated-trend-transfer/](1d-ma7-separated-trend-transfer/README.md) | 见顶层 |

## 当前研究线

- `SOX-1D-MA7-Separated-Trend-Transfer`（`SOX-1D-MA7-ST-XFER`）：[1d-ma7-separated-trend-transfer/](1d-ma7-separated-trend-transfer/README.md)。把 `HYPE-1D-MA7-Asymmetric-Body-Trend-V1` 零调参迁移到 Yahoo `^SOX` 日线；全历史组合亏损、长期超额失败，`explore / not promoted / not live-ready`。主账：[sox-1d-ma7-st-xfer-core-ledger.md](1d-ma7-separated-trend-transfer/sox-1d-ma7-st-xfer-core-ledger.md)。
- `SOX-1D-MA7-Asset-Specific-Search`（`SOX-1D-MA7-AS-SEARCH`）：[1d-ma7-asset-specific-search/](1d-ma7-asset-specific-search/README.md)。共享参数控制、SOX development-only 搜索与 MA20 零调参替换；MA20 改善回撤但仍无长期超额，`explore / not promoted / not live-ready`。主账：[sox-1d-ma7-as-search-core-ledger.md](1d-ma7-asset-specific-search/sox-1d-ma7-as-search-core-ledger.md)。
