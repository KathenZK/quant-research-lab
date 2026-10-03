---
research_classification: strategy_family
---

# M1358

[中文研究报告](M1358.md) · [研究主账](M1358-core-ledger.md) · [决策历史](decision-log.md)

当前版本C0-v2 / ADAPTED。1ID、4预定配置、0新增控制、strict0。旧v1在历史前失败保留；当前执行入口见[scripts/V2.md](scripts/V2.md)。

[实际远端核心恢复](recovery/remote-core-v1/M1358-remote-core-recovery.safe.json)与[恢复命令](recovery/remote-core-v1/REMOTE-CORE-RESTORE.md)：从已取回的Git代码重建22个结果文件及清单逐字节一致；依赖同指纹合法行情缓存，不保证公共数据源永久可用。完整私有ZIP尚未保存到Library，此缺口与Git核心恢复分别记录。

## 已审展示派生（2026-10-03）

仅使用已公开的首日与24个UTC月末，共25点；指标覆盖原731日，未访问私有日净值、不插值、不重算完整回撤。保留Graph HYPOTHESIS与研究ADAPTED两个口径，lag2为日。

[结构化记录](artifacts/20261003-public-display-prep/graph-record.json)、[详情](artifacts/20261003-public-display-prep/graph-detail.json)、[派生manifest](artifacts/20261003-public-display-prep/public-display-manifest.json)、[轻量曲线](artifacts/20261003-public-display-prep/base-nav-sampled.json)与[可重建工具及独审清单](../M0287/scripts/public-display-v2/README.md)作为附加公开证据保存。manifest类型为PUBLIC_DERIVED_DISPLAY_MANIFEST/v2，生成时STAGED_NOT_IMPORTED状态原样冻结；此处不声明Graph默认16条已适配或Site已部署。新增回测0、控制0、严格复现0；C0与原结果未改。
