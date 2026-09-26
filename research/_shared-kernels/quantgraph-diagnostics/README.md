# QuantGraph 研究统计诊断内核

通用收益序列统计，不读取行情、不产生仓位、不授权策略晋级。

| 版本 | 文件 | SHA256 | 消费方 |
|---|---|---|---|
| v1 | [metrics.py](v1/metrics.py) | `32b96a286e5a70a458e7cf2c0194ad802107c37415e4264bc0e46a8c3f2fb593` | platform/quantgraph-integration |

v1 已冻结，修复须创建 v2 并更新消费方。PBO 保留未 purge 限制；DSR 使用
IID 近似且有效试验数由调用方提供；不把全部高度相关变体数默认为独立试验数。

原始方法：[PBO](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)、
[DSR](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)。
