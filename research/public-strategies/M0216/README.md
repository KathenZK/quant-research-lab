---
research_classification: strategy_family
---
# BTC 日频 M0216 双均线来源回放

状态：`explore / not promoted / not live-ready`。原表稳定 ID M0216；独立机制为 SMA11/20 交叉与来源风控门，区别于 BTC/EUR PRICE_SMA 家族。不继承其他家族的参数或市场。

[主账](m0216-core-ledger.md) · [逐策略报告](diagnostics/M0216-20261003.md) · [冻结规格](specs/M0216-first-replay.json) · [决策记录](decision-log.md)。

代码位于 scripts；本地冻结输入、日净值、成交、独立验证、来源和环境指纹位于 artifacts/20261003-first-replay。公开Git排除完整输入与大部分曲线，只含基准净值、成交和汇总；按重建配方取得输入并验hash后才可恢复运行。该目录的数据及衍生物单独适用 CC BY-NC-SA 4.0，见其 LICENSE.md；不授权生产使用。Graph 导出遵循现有详情记录结构，尚未部署。
