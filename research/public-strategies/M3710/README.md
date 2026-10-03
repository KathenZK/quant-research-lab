---
research_classification: strategy_family
---

# M3710｜比特币 SMA20 状态择时

本家族实现目录转述的日线状态规则：收盘价高于包含当日收盘价的 20 日简单均线时持 BTC，否则持现金。采用固定的 Binance BTCUSDT 现货研究实例，属于 `HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED / ADAPTED_EXECUTION_PROXY`；严格复现数为 0，`trusted=false`，评价窗口不是样本外。

当前仅完成代码准备与人工合成验证。尚未运行 M3710 历史指标、账户或回测；实际历史执行需要共享适配器独立验收和远端指纹、完整 C0、独立代码审查及 root 对精确 C0 的单独放行。当前源码不可据合成 PASS 自行扩量。

- [逐策略说明](M3710.md)：来源、规则、执行假设和研究限制。
- [家族主账](M3710-core-ledger.md)、[决策记录](decision-log.md)。
- [冻结来源规则副本](specs/root-rules-v1.json)、[执行规格](specs/protocol-v1.json)。
- [脚本与验证说明](scripts/README.md)。

100000 USDT 单一现金账户、100% 含费预算、现金零收益和次日开盘代理均是研究适配。复用既有 M1258 基准，4 个策略配置、0 个新对照；不能把该基准称为 fee0/fee20/delay2 的匹配成本对照。原始行情、全量曲线和账户日志保留私有。临时磁盘及本地合成恢复不代表远端备份成功。
