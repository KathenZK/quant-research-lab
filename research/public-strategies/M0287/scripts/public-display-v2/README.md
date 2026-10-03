# 三条已审展示派生的离线重建

此目录只导出 M0287、M0289、M1358 已有公开结果的展示文件，不执行回测、不获取行情、不改 Graph 默认清单、不调用 Site。输入固定为 Lab `dba8d1d64318f9909cdcfd3bc9c382842a1a742b`；需要本地 Git 已持有该对象，脚本不会自行联网。每个来源按原 publication manifest 的路径、字节数、SHA256 验证。

- [export.py](export.py) SHA256 `266c93afa0829b0e504b2e008e1ed0ae1b43a4b5fd2869ffaeb047e41fba3128`：经过独审的三 ID 包装器，按明确的原生 5m / 日频采样 profile 导出。
- [common_public_display.py](common_public_display.py) SHA256 `f5a8536676f1575f55adcf3b286ba92c198a01c070399250fbf933f8937c9c13`：固定来源提交中 M0253 `scripts/export_dot006_display.py` 的原字节副本，保留历史身份；仅导入安全读取、哈希、编码与曲线转换 helper。包装器显式设置来源提交，不调用 helper 的旧四 ID 导出入口。此处不是新回测内核，也不修改原脚本。
- [verify.py](verify.py)：核对三 ID、12 原配置、757 个展示点、12 个独审候选字节、13 个重建文件、当前 publication manifests 和原冻结证据，运行 18 个拒绝边界用例。

从仓库根目录运行（仅 Python 标准库与 Git；不依赖原准备目录）：

```bash
display_root="$(mktemp -d)"
python research/public-strategies/M0287/scripts/public-display-v2/export.py --lab-repo . --output "$display_root/first"
python research/public-strategies/M0287/scripts/public-display-v2/export.py --lab-repo . --output "$display_root/rebuild"
python research/public-strategies/M0287/scripts/public-display-v2/verify.py --lab-repo . --preview "$display_root/first" --rebuild "$display_root/rebuild" --receipt "$display_root/check.json"
```

输出目录必须不存在，父目录必须存在；保留至少 5 GiB 空余。原数据、已有导出目录及验收回执均不覆盖。三个脚本必须保留在同一目录；helper 用兄弟模块定位，换工作区可原样重建。

[独审回执](../../artifacts/20261003-public-display-review/independent-review.safe.json)、[精确 12 文件清单](../../artifacts/20261003-public-display-review/EXACT-12-FILES.json)、[来源和交付清单](../../artifacts/20261003-public-display-review/DELIVERY-MANIFEST.json) 保留原字节。独审复跑其中 8 项守卫；18 项是准备者自查数量，不混称为独审全跑。

所有新 manifest 明示 `PUBLIC_DERIVED_DISPLAY_MANIFEST` / `quantgraph-public-derived-display-manifest/v2`，不是原私有结果清单。record/detail 绑定派生 manifest 哈希；manifest 不反向哈希 record/detail，外层交付清单统一固定 12 文件，避免循环依赖。`STAGED_NOT_IMPORTED` / `STAGED_NOT_PUBLISHED` 是生成时状态；Git 保存不等于 Graph 绑定或 Site 激活，因此不重写这组冻结字节。

M0287、M0289 各保留 366 个日收盘点，NAV 为原 USDT 权益除以 100000，不以首样本重定基；原全 5m 回撤单列。M0289 四配置零交易与 Sharpe null 原样保留。M1358 仅保留已获准的首日加 24 个 UTC 月末点（共 25 点），指标仍取原 731 日统计，不能从采样线反算完整回撤或插值成日净值。M1358 Graph `HYPOTHESIS` 与研究 `ADAPTED_EXECUTION_PROXY` 分列，lag2 单位是日；其 95% 费前名义和另付 USDT 手续费不与另两条的含买入费预算混淆。此导出未读取 M1358 私有日净值。

新增研究运行 0、控制 0、严格复现 0。既有 M0311/M0216 基准摘要按哈希复用，不制造基准曲线。下一步 Graph 适配须明确支持 v2 profiles、采样数量与全样本指标区别，并在另行验收后绑定真实 active entity/revision；本目录不声明现有 16 条默认适配器已兼容。
