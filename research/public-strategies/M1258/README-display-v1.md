# M1258 已审轻量展示派生

本次只保存已有研究的公开展示派生，新增历史执行、控制和行情请求均为 0。[原 README](README.md)、[原主账](M1258-core-ledger.md)、[原决策](decision-log.md)及 C0 中的 19 个冻结对象保留原字节；本文件不修改原研究结论。

- [展示记录](artifacts/20261003-public-display-prep/graph-record.json)
- [展示详情](artifacts/20261003-public-display-prep/graph-detail.json)
- [25 点采样曲线](artifacts/20261003-public-display-prep/base-nav-sampled.json)
- [派生证据清单](artifacts/20261003-public-display-prep/public-display-manifest.json)
- [原字节独审回执](artifacts/20261003-public-display-review/review.safe.json)与[来源/交付外清单](artifacts/20261003-public-display-review/DELIVERY-MANIFEST.json)
- [本次决策](decision-log-display-v1.md)与[publication revision 3 记录](publication-history/revision-v3.json)

来源固定于 Lab `2a2e33e0de2b4897d6ccb460e72dcb5e73aa4153`，原 publication v1 SHA256 `a6a38fc7270c56741c756dcd1219d534e51bf1fe89ac5f59067da0c44a360d81`。导出校验该提交 37 个公开对象（157863B）与 C0 19 项，不随当前工作树或后续清单变化重新选源。此前含核心恢复回执的 publication v2 原字节保存在 [v2 清单](publication-history/v2/publication-manifest.json)，本次只追加 revision 3。

manifest 类型为 `PUBLIC_DERIVED_DISPLAY_MANIFEST`，schema 为 `quantgraph-public-derived-display-manifest/v2`，profile 为 `DAILY_SAMPLED_APPROVED_DETAIL_V1`。保留 Graph `HYPOTHESIS`、研究 `HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED`及执行 `ADAPTED_EXECUTION_PROXY`，不提升为来源核实或严格复现。

原 25 点（首日加 24 个 UTC 月末）已是初始资金倍数，直接保留；731 是完整原日频指标的观察数，不是显示点数。不二次除以 100000、不插值、不从 25 点重算完整回撤。原四配置结果及月度汇总保留；fee0/fee20 仅映射为显示键 0/20，delay2 的原生周期为日。

原研究实际运行 4 个策略配置及 1 个新买入持有控制，控制采用 100% 含买入费的现金预算，区别于 M1358 的 95% 费前名义规则；本次派生新增运行和控制均为 0。原 null 值保留。公开 private-output-manifest 只作 opaque 对象哈希校验，不解析、读取其引用的私有 NAV 或账户文件。

生成时的 `STAGED_NOT_IMPORTED` / `STAGED_NOT_PUBLISHED` 保留为冻结状态。Lab Git 保存不表示 Graph 20 条已适配、绑定实体版本或 Site 已激活。record/detail/manifest 排除循环哈希，外清单固定全部四个候选。detail 中 `transport_binding` 是来源执行身份六字段，与 Site/D1 上传 envelope 的六字段合同不同；此处不运行 Site transport。

## 离线重建

四个脚本放在同一目录，使用兄弟模块定位，不依赖原临时准备路径；仅 Python 标准库与本地 Git 对象，无行情请求或回测。

| 文件 | SHA256 |
| --- | --- |
| [export_m1258.py](scripts/public-display-v2/export_m1258.py) | `35d95b7513561f1127a418233cea718d51a1cc7cba8f71627dee04146e57a4ab` |
| [verify_m1258.py](scripts/public-display-v2/verify_m1258.py) | `4021b3515adbe6d69ea7b8f0145fc018dc121a658c27b737efa6842cd85f83bf` |
| [frozen_export.py](scripts/public-display-v2/frozen_export.py) | `266c93afa0829b0e504b2e008e1ed0ae1b43a4b5fd2869ffaeb047e41fba3128` |
| [common_public_display.py](scripts/public-display-v2/common_public_display.py) | `f5a8536676f1575f55adcf3b286ba92c198a01c070399250fbf933f8937c9c13` |

两个 helper 保留 Lab `f6d2431bc5c727d6525851a4e6c80b2a2acede33` 中 M0287 `scripts/public-display-v2/export.py` / `common_public_display.py` 原字节，只复用安全读取、哈希、编码及检查函数，不调用旧三 ID 或四 ID 导出入口，也不改共享回测内核。

在仓库根目录执行，输出父目录须存在；原输出目录和回执均不可覆盖，磁盘保留至少 5 GiB：

```sh
display_root="$(mktemp -d)"
PYTHONDONTWRITEBYTECODE=1 python research/public-strategies/M1258/scripts/public-display-v2/export_m1258.py --lab-repo . --output "$display_root/first"
PYTHONDONTWRITEBYTECODE=1 python research/public-strategies/M1258/scripts/public-display-v2/verify_m1258.py --lab-repo . --first "$display_root/first" --rebuild "$display_root/rebuild" --receipt "$display_root/check.json"
```

验证器会生成第二份 fresh 输出，比较 5 文件（4 候选加外清单）、原值和 21 个拒绝边界。独审单独复跑了回执中列出的 6 个守卫；这两个数量不混称。当前 Git 四候选还应与上述独审清单中各自 SHA256/bytes 完全相符。
