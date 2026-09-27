# QuantGraph 研究统计诊断内核

通用收益序列统计，不读取行情、不产生仓位、不授权策略晋级。

| 版本 | 文件 | SHA256 | 消费方 |
|---|---|---|---|
| v1 | [metrics.py](v1/metrics.py) | `32b96a286e5a70a458e7cf2c0194ad802107c37415e4264bc0e46a8c3f2fb593` | platform/quantgraph-integration |
| v2 | [metrics.py](v2/metrics.py) | `f562a427036b10b679fcbba9ebccba2aba614aaa8a8d818751262471c1792c8d` | reference validation / platform-v2 |

v1 已冻结，修复须创建 v2 并更新消费方。PBO 保留未 purge 限制；DSR 使用
IID 近似且有效试验数由调用方提供；不把全部高度相关变体数默认为独立试验数。

原始方法：[PBO](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)、
[DSR](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)。

v2 新增 moment 接口、逐 split 输出和精确组合数量；v1 原样保留。数学语义：[DSR](../../../docs/research/DSR.md)、[PBO](../../../docs/research/PBO.md)。
