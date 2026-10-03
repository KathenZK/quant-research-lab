# M1346 已审公开展示派生 v1

本次仅追加已独审的轻量展示、可复建脚本与[本次公开来源清单](publication-manifest.display-v1.json)。[原README](README.md)、[主账](M1346-core-ledger.md)、[原决策](decision-log.md)、C0和原12项家族文件保持原字节；三家族原36文件及当前共享62文件均保留。原08e6共享59项已在主干追加3项治理文件，原README另存README-original-dot009.md；该既有映射保持不变。新增历史执行、控制和行情请求均为0。

- [展示记录](artifacts/20261003-public-display-prep/graph-record.json)、[详情](artifacts/20261003-public-display-prep/graph-detail.json)、[25点曲线](artifacts/20261003-public-display-prep/base-nav-sampled.json)、[派生manifest](artifacts/20261003-public-display-prep/public-display-manifest.json)。
- [独审回执](artifacts/20261003-public-display-review/review.safe.json)、[三ID交付清单](artifacts/20261003-public-display-review/DELIVERY-MANIFEST.json)、[精确12文件清单](artifacts/20261003-public-display-review/EXACT-12-FILES.json)。共同清单覆盖M1346/M1349/M1270，不代表本家族新增12配置。
- [本次决策](decision-log-display-v1.md)。

固定来源 Lab `08e6ab4a49a808f53f06e509f06cb2c453f007d5`。此前没有逐ID publication manifest，本次 `publication-manifest.display-v1.json` 是新建的 `APPROVED_PUBLIC_DISPLAY_SOURCE_INVENTORY`，只列本次选定的11个公开来源角色和14个新增payload，不冒称历史全量研究清单。其25个payload不包含自身；跨三ID去重后来源为25个Git对象（33个角色），新增payload为42个，另有3个本次manifest。当前98个文件以基线 `420a0532a57b89b57045bf3e1ddb062e263edf44` 的Git对象身份保持，原95个来源对象按上述既有映射保持；仅读取所选公开源正文，不声明重读全部95项内容。

所选来源锁为 `SELECTED_APPROVED_GIT_SOURCE_LOCK_NOT_PUBLICATION_MANIFEST`；[冻结锁](scripts/public-display-v2/selected-public-source-lock.json)的字节/哈希/路径全部校验。C0仅重验所选6个冻结角色指纹，不冒称重建全部历史依赖。规则协议使用真实 `root-frozen-rules.json` 的哈希，标记 `FROZEN_RULE_CONTRACT_NOT_INVENTED_PROTOCOL_FILE`，没有捏造协议文件。

展示manifest的类型为 `PUBLIC_DERIVED_DISPLAY_MANIFEST`、schema为 `quantgraph-public-derived-display-manifest/v2`、profile为 `DAILY_SAMPLED_APPROVED_DETAIL_V1`。本ID独立source_contract为 `CATALOG_CLOSE25_LEVEL_FULLCASH_REUSED_CONTROL_V1`。25日收盘level规则，保留原入场、离场与全额含费资金配置。

原11个catalog字段和规则保留；原Graph `HYPOTHESIS`、研究 `HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED` 与执行 `ADAPTED_EXECUTION_PROXY` 分别保留。严格复现为0、来源runtime未核、PIT未证明；2023–2024为已曝光窗口，不称独立OOS。

25个曲线点直接来自已公开、已归一化的原点；731是原指标观察数。不再次除100000，不插值，不从采样点重算指标。每ID原4配置；三ID合计12原配置、本次0新运行和0新控制。共同复用同一个已验M1258满仓含费买入持有base控制（8bps费用+2bps滑点），没有fee0/20匹配成本控制。成本别名fee0/fee20转为0/20，full与原2023-2024值完全一致；额外延迟单位为日。未公开策略月收益数组保留monthly=null，不补造数值；原公开基准月度投影可保留。

不读取或发布原始行情、私有731日NAV、完整账户日志、ZIP及私有inventory正文。旧公开detail中的private-result hash只保留为历史lineage，不能作为派生manifest或读取许可。派生manifest不哈希自身、record和detail，外DELIVERY绑定12个候选字节，避免循环。

候选和外清单中的原 `STAGED_NOT_IMPORTED` / `STAGED_NOT_PUBLISHED_PENDING_INDEPENDENT_REVIEW` 保持冻结原值；后续独审PASS见独立回执。Git保存不代表已绑定Graph实体revision、Graph导入或Site激活；不修改六字段传输、UI或用户批注。

## 离线复建

五个文件位于同目录，脚本使用兄弟模块相对定位。每家族保存同一套完整冻结副本；导出仅接受这三个固定ID，仅git show读取选定源，不抓取新数据、不调用回测入口。

| 文件 | SHA256 |
| --- | --- |
| [export_dot009.py](scripts/public-display-v2/export_dot009.py) | `ef92d7cb7238163a72f696d785112a77ea3bda280bc3509cd10ce9cbd8cd0b05` |
| [verify_dot009.py](scripts/public-display-v2/verify_dot009.py) | `03fd86370414ce78271712589c9586dedb0527e3cc659c440394f16107a04377` |
| [common_public_display.py](scripts/public-display-v2/common_public_display.py) | `f5a8536676f1575f55adcf3b286ba92c198a01c070399250fbf933f8937c9c13` |
| [frozen_export.py](scripts/public-display-v2/frozen_export.py) | `266c93afa0829b0e504b2e008e1ed0ae1b43a4b5fd2869ffaeb047e41fba3128` |
| [selected-public-source-lock.json](scripts/public-display-v2/selected-public-source-lock.json) | `4379e8c4897b9ae8d3eeaaf3a467549a71abd79600026b2da463a7f682b3d9f1` |

在仓库根执行；输出父目录须存在，输出与回执路径必须未存在，磁盘保留至少5GiB。示例路径只存本地复建结果：

```sh
PYTHONDONTWRITEBYTECODE=1 python research/public-strategies/M1346/scripts/public-display-v2/export_dot009.py --lab-repo . --output /tmp/dot009-display-first
PYTHONDONTWRITEBYTECODE=1 python research/public-strategies/M1346/scripts/public-display-v2/verify_dot009.py --lab-repo . --first /tmp/dot009-display-first --rebuild /tmp/dot009-display-rebuild --receipt /tmp/dot009-display-check.json
```

已审导出器两次fresh产生13文件（12候选+DELIVERY）逐byte一致。作者49项边界检查与独立审核另行执行的14项负例分开统计；独审包含实际metricValue的0/null展示检查，但没有浏览器或Site部署验证。本次提交后仍需root窄审和远端保存；后续Graph适配另按精确远端pin推进。
