# Graph 现站导出与发布阻塞诊断

审计 Graph 基线 `6b3b221f` 的源码；只读检查，没有获取凭证、读取个人批注、修改权限或访问被拒通道。实际模型ID和reasoning effort未暴露，均UNKNOWN。

## 缺哪些组件

1. **私有runtime**：`catalog.sqlite`（完整catalog实体/定义版本和执行绑定），以及 `corpus-research.sqlite`（保留执行版本、指标、曲线和血缘）。`ResearchWorkView.summary()` 必须存在且 `unbound_execution_versions == 0`；source-native的M编号不能自动等于Graph的definition revision。当前仓库只有 `datasets/public/releases/*/quantgraph.sqlite` 公共发行样例，不是用户私有catalog。完整runtime初始化还可复制 ingestion/jobs/factor-studies/personal/source-links 等库；本次不以空库或公共样例冒充恢复。
2. **现站不可变基线资源**：导出器需要按先后顺序的 `--baseline-root`；明确读取 `/catalog/manifest.json`、`/catalog/meta.json`、`/data/manifest.json` 及其引用的catalog详情和历史implementation对象。它逐字节保留旧实验投影。没有这些资源就不能安全合并新详情、比较页和定义身份。
3. **激活父版本**：`--parent-batch` 必须对应现站current batch，以compare-and-swap避免覆盖并行更新。版本8/active/custom元数据不能替代这个批次ID。
4. **发布通道**：现有 `scripts/site_sync.py` 的status/upload/feedback都通过stdin接收平台服务授权；参数要求显式 `--confirmed-owner-private`。上次Sites元数据只有custom访问描述，不能凭此确认owner-private；用户又禁止读取/创建凭证，因此没有执行该通道。这里并未证明用户账号没有Sites权限，只是当前约束下没有可用且已验证的发布途径。
5. **源码部署通道**：`scripts/stage_sites.py` 要求已打开的原Site checkout、匹配项目的 `.openai/hosting.json`、固定基线assets和Git目录；会改写staging内容及hosting配置。本执行器没有该私有checkout，本次也没有启动此写操作。

## 有无仓库支持的只读导出

有离线导出路线：`scripts/export_research_site.py --runtime <已校验副本> --baseline-root <旧到新基线> --output <全新目录> --parent-batch <current>`。它不请求网络、不激活站点，产生有sha256/字节数的不可变对象、分批manifest和receipt。`CorpusResearch` 的读取使用SQLite `mode=ro`，缺库直接失败。

但整个导出器**不是严格文件系统只读**：`CatalogRepository`/`PersonalCatalogRepository` 构造会建目录、设置WAL并执行CREATE TABLE IF NOT EXISTS。因此应在一致性备份出的runtime副本上运行，保留原始数据库不动。当前缺数据库和基线，无法实际导出本次用户站点；不能只用独立策略record生成空的替代站点。

可立即继续的是Lab本地策略结果及Graph字段兼容投影，附当前路径索引；它们没有定义绑定/导入/激活回执。补齐已授权私有组件后，按既有导出器合并详情与比较视图，保持原UI及批注overlay，不新增孤立研究栏目。

## 代码证据

- Graph `scripts/export_research_site.py:52`：离线导出、基线资源和不可变写入；`:94`：runtime及定义绑定门；`:233`：研究基线；`:364`：父批次链；`:426`：CLI。
- Graph `graph/corpus_research.py:24`、`:586`：研究库名和只读连接；`graph/catalog.py:23`：初始化写入行为；`graph/research_views.py:141`：未绑定执行统计。
- Graph `scripts/site_sync.py:198`：授权/owner-private参数；`scripts/stage_sites.py:54`：原项目checkout校验；`sites/README.md`：原React UI、不可变数据同步、批注持久overlay和访问前提。

本诊断不输出任何批注、私有catalog内容、凭证或Site服务头。

## 后续只读进展

通过Sites原生只读数据库接口已核实D1表名，并只读取qg_settings中的active_batch；因此父批次值已取得，不再列作未知。没有读取qg_feedback/qg_notes或凭证，未修改数据库/权限。Sites版本接口还返回版本8的归档指纹和文件引用：164536320字节、19885文件。此归档可能提供构建基线，但本执行器通用download_file上限32MiB，尚未取得归档字节，不能据元数据声称恢复成功；未绕限制或猜下载URL。精确站点身份/归档引用/父批次保存在私有协调记录，不加入公开Git。

仍缺已验证私有runtime及可读取的完整基线字节、可用的源码/服务发布通道。当前接口只读能力并不等于可写发布权限。Graph最终可查看仍是任务目标；Git提交、Graph导入、站点激活必须有各自回执，不能因PR存在就称已上站。
