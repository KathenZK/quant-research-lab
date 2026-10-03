# M1347：比特币月末窗口

research_classification: strategy_family

本家族按已冻结 catalog 假设研究 BTCUSDT 现货日线：UTC 连续日历每月倒数第三日收盘发买入意图，新月第三日收盘发卖出意图。成交采用下一日开盘或预先指定的延迟两根代理，满仓预算包含买费。原网页与作者实现尚未独立验证，严格复现计数为 0。

本页为收益前冻结入口，当前只有规则、代码及人工合成证据；不声称历史结果或远端完整私有备份已完成。后续结果以新增版本文档交付，不覆盖本页。

- [家族主账](M1347-core-ledger.md)
- [规则与公开来源字段](source/catalog-public-fields.json)
- [协议](specs/protocol-v1.json)与[决策记录](decision-log.md)
- [实现与恢复入口](scripts/README.md)

研究分类保持 `HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED` / `ADAPTED_EXECUTION_PROXY`。日历、市场实例、仓位及下一开盘执行都是明确研究假设；本窗口已被反复使用，不是样本外。
