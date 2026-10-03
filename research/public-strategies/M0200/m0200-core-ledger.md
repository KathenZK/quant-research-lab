# BTC-1D-M0200-CONNORS-RSI2 主账

- 家族：BTCUSDT / Binance spot / UTC 1d；MA200 趋势内 RSI2 超卖回归 MA5。
- 版本：M0200-BTCUSDT-RSI2-NEXTOPEN-20261003，`explore / not promoted / not live-ready`。
- 不等同作者原市场或当日收盘成交，不与 M0216 双均线家族合并。
- 本次 4 个预声明策略配置，1 个基准；严格复现 0，无实盘或 runner 操作。

| 版本 | 状态 | 结果 | 证据与决定 |
| --- | --- | --- | --- |
| M0200-BTCUSDT-RSI2-NEXTOPEN-20261003 | explore | 基准19.09%，回撤22.14%；额外延迟为负 | [报告](diagnostics/M0200-20261003.md)：不晋升，执行假设不稳健 |

输入沿用已验 hash 的 BTCUSDT 现货762日；评估519日，无 OOS 声明。成本8bps+2bps滑点、95%现金配置、无借贷或资金费率；假设细节见[规格](specs/M0200-first-replay.json)。数据仅个人非生产研究，衍生物许可见 artifacts/20261003-first-replay/LICENSE.md。下一关口为来源验证、可实现成交规则与未曝光样本，不能据本结果追调延迟或阈值。
