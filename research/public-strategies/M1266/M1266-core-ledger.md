# M1266 核心账本

## 版本身份

- 本地run：M1266-catalog-batch019-20261003-v1
- 批次：019，初次冻结历史试验为4策略配置及1新控制
- 分类：ADAPTED_SOURCE_CORRECTED_VARIANT / HYPOTHESIS_EXECUTION_PROXY
- strict_reproductions=0，trusted=false，OOS=false，PIT=UNKNOWN
- 原市场：BTCUSD / Bitfinex Cash / 2020–2021；适配市场：BTCUSDT / Binance spot / UTC日线 / 2023–2024
- [来源](https://www.quantconnect.com/forum/discussion/11340/btc-3-emas-strategy/)，选用修正版附件；原作者承认挑选展示区间
- 100预热、731评估；初始100000 USDT；信号时90%名义固定数量、无成交缩量

## 当前状态和结论

历史计算及独立复核已PASS；公开allowlist与协调者验收待完成，accepted=false。未设置实体revision、未执行Graph整合、未激活Site，也未增加全局已验收数量。

base总收益60.13%、CAGR26.50%、最大回撤−19.13%、Sharpe1.0360；声明控制总收益419.02%。base只持仓193/731日，较小回撤不足以推出策略优越性。delay2收益78.21%仅是冻结敏感性。fee0/fee20/delay2均无独立匹配控制。

## 证据入口

- [报告及所有配置](M1266.md)
- [规则与运算顺序](specs/operational-rules-v1.json)
- [结构化指标](artifacts/20261003-batch019-v1/metrics.json)
- [决策记录](decision-log.md)

全精度、全部特征与账户/交易流水、完整来源与可恢复输入保留在私有证据包；此处只放轻量摘要和25点显示投影。后续独立验收应追加记录并保持历史证据可追溯。
