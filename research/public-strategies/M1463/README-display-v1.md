# M1463 已审轻量展示派生 v1

本次只追加已独审的公开展示派生、可复建脚本及 [publication v2](publication-manifest.v2.json)。[原 README](README.md)、[主账](M1463-core-ledger.md)、[原决策](decision-log.md)、C0、49项原公开payload及 [publication v1](publication-manifest.v1.json) 全部保留原字节。本次新增历史执行、控制与行情请求均为0。

- [展示记录](artifacts/20261003-public-display-prep/graph-record.json)、[详情](artifacts/20261003-public-display-prep/graph-detail.json)、[25点曲线](artifacts/20261003-public-display-prep/base-nav-sampled.json)、[派生manifest](artifacts/20261003-public-display-prep/public-display-manifest.json)。
- [原字节独审回执](artifacts/20261003-public-display-review/review.safe.json)、[两ID交付清单](artifacts/20261003-public-display-review/DELIVERY-MANIFEST.json)、[精确8文件清单](artifacts/20261003-public-display-review/EXACT-8-FILES.json)。两ID共用清单保留独审原字节，不代表本家族新增8配置。
- [本次决策](decision-log-display-v1.md)。

来源固定 Lab `683fe124f70c0f5b1e36af20ad68256c4a83e180`。manifest为 `PUBLIC_DERIVED_DISPLAY_MANIFEST`、schema `quantgraph-public-derived-display-manifest/v2`、profile `DAILY_SAMPLED_APPROVED_DETAIL_V1`，每ID有单独source_contract防止规则混用。布林20/2收盘上破上轨做多、下穿中轨退出；只保留原10个公开字段，内部“别名来源”值不补回，仅保留既有排除原因及公开别名链接。

原Graph `HYPOTHESIS`、研究 `HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED` 与执行 `ADAPTED_EXECUTION_PROXY` 分别保留。strict0、来源与作者runtime未核、PIT未证明、2023–2024为已曝光窗口，不声明独立OOS。

每ID保留25个已归一化公开点及原drawdown，731是原日频指标观察数。不再除100000、不插值、不从25点重算指标。原4策略配置、0新控制；复用已验M1258满仓含费买入持有控制，100000USDT、Decimal50、8bps费+2bps滑点、日线lag1/lag2均保持。两ID只有同一个被复用控制，合计8原配置/0新控制。轻量来源没有逐月收益数组，monthly=null并声明不可用，不伪造24个月数值；基准曲线仍为空。

仅读取每ID10个明确公开角色（含publication/summary/detail/record/protocol/C0/rules/catalog/controlreference/release），不读取私有731日NAV、完整账户日志、ZIP或private-output-manifest正文。原公开detail中的private-result hash仅保留为source_lineage，不冒充派生manifest或读取许可。完整49项旧清单通过固定Git身份保持；本次导出不声称读取全部96个旧union正文。

record/detail绑定派生manifest，外DELIVERY再绑定候选，避免自引用hash。所有冻结 `STAGED_NOT_IMPORTED` / `STAGED_NOT_PUBLISHED` 保持原值；Git保存不代表Graph22已适配、绑定实体revision或Site激活。六字段来源绑定不改变Site/D1传输，原用户批注不触及。

## 离线复建

四脚本在同目录，以兄弟模块相对定位。两个helper原字节冻结，只调用安全读取/哈希/编码/扫描函数，不调用历史导出或回测入口。每个家族保留相同完整脚本副本，以便独立定位；导出器显式只接收M1396/M1463这对固定源。

| 文件 | SHA256 |
| --- | --- |
| [export_catalog_pair.py](scripts/public-display-v2/export_catalog_pair.py) | `8e6acc4cd4c2c30cc2cf5aecaec5f1231697f7935176042416e33bb633f5c64b` |
| [verify_catalog_pair.py](scripts/public-display-v2/verify_catalog_pair.py) | `00f269bcf90f37ec08eac5b22140054cf042bad38232ac4b6ab8c9695342dd4b` |
| [common_public_display.py](scripts/public-display-v2/common_public_display.py) | `f5a8536676f1575f55adcf3b286ba92c198a01c070399250fbf933f8937c9c13` |
| [frozen_export.py](scripts/public-display-v2/frozen_export.py) | `266c93afa0829b0e504b2e008e1ed0ae1b43a4b5fd2869ffaeb047e41fba3128` |

在仓库根目录运行，输出父目录须存在且两个输出目录/回执不得存在；保留至少5GiB余量：

```sh
PYTHONDONTWRITEBYTECODE=1 python research/public-strategies/M1463/scripts/public-display-v2/export_catalog_pair.py --lab-repo . --output /tmp/catalog-pair-display-first
PYTHONDONTWRITEBYTECODE=1 python research/public-strategies/M1463/scripts/public-display-v2/verify_catalog_pair.py --lab-repo . --first /tmp/catalog-pair-display-first --rebuild /tmp/catalog-pair-display-rebuild --receipt /tmp/catalog-pair-display-check.json
```

最终脚本两次fresh输出9文件（8候选+DELIVERY）逐byte一致；75个作者负例通过。独审另行重建并实际复跑15个边界，未将作者75项冒称独立复跑。无需临时绝对依赖或新网络数据；原候选bytes/sha固定于两份交付清单。后续Graph22适配须在root确认本次远端公开pin后另行进行。
