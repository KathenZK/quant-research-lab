# GOLD 研究入口

本目录维护黄金及其可交易衍生品的独立研究家族。现货、ETF、期货单合约与连续期货
不是同一个执行面；任何迁移必须保留市场、合约、换月和成本边界。

| Family | Alias | Directory | 机制 | 状态 |
| --- | --- | --- | --- | --- |
| `GOLD-1D-Multi-Speed-TSMOM` | `GOLD-1D-MS-TSMOM` | [1d-multi-speed-tsmom/](1d-multi-speed-tsmom/README.md) · [主账](1d-multi-speed-tsmom/gold-1d-ms-tsmom-core-ledger.md) | 月末 `sign(1M/3M/12M)` 等权，60-day COM EWMA 风险缩放 | 见顶层 |

当前只有这一条黄金研究线。数据身份与证据边界以家族主账和诊断报告为准。
