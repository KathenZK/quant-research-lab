# MA7-BTG 复现说明

这些脚本只服务本家族，不是active package或跨家族共享内核。权威规则为[冻结合同](../specs/research-contract-p1-20260908.md)；正式结果固定为P1-development-r1、P1-evaluation-r1、P2-r2、P3-r1及P5。任何带INVALIDATED标记的目录只作失败证据。

## 环境、源码与输入

实际环境：Python3.13.0、NumPy2.4.4、pandas3.0.2、DuckDB1.5.2、PyArrow24.0.0、SciPy1.18.0、pytest9.0.3，statsmodels未安装。精确记录在[输入启动记录](../artifacts/p0-inputs-20260908/started.json)。不要静默安装/升级以绕过SHA或重现失败。

正式Lab为`/Users/ZK/OpenCode/quant-strategy-lab`，数据根为该目录的`data/`，可信接口来自该目录的`src/`；独立worktree只承载本家族实现。实际依赖Python为正式Lab的`.venv/bin/python`。当前家族相对目录为`research/asset-portfolios/1d-ma7-bidirectional-trend-generalization/`。

[source-pins](../specs/source-pins-20260908.json)固定正式数据接口与旧基线SHA；[输入请求](../specs/input-request-20260908.json)固定874代码、bundle和时间；[返回帧清单](../artifacts/p0-inputs-20260908/frame-manifest.json)同时保留压缩文件SHA与pandas内容SHA。策略读取返回帧前逐项验哈希，按连续段重算特征；不会读另一个家族cache。

唯一已解释的启动pin变动为消费者注册文件新增本家族3个入口；移除且仅移除这3段后精确重建启动SHA，见[登记差异](../artifacts/registry-pin-delta.json)。数据接口和原基线pin不放宽。最终文档/源文件/输入验证可运行`verify_delivery.py`；它会更新本轮同名验收记录，不重跑或覆盖候选收益。

实际主计算源码另保存在[计算源码快照](../artifacts/source-snapshots/20260908-computation/manifest.json)。交付时只补充输出目录参数和锁元数据措辞，策略引擎不改；可用快照与运行started/completed中的SHA核对原版本。当前入口允许新run-id以免覆盖归档。统计表复现要保留随机种子与循环顺序； gzip时间戳不必逐字相同，CSV内容和pandas帧哈希应一致。

## 从正式Lab运行

下面命令写入新的repro目录；已经存在则停止，不能删除原结果重跑。按顺序运行，前一步完成后才执行依赖它的步骤。每次研究运行的命令参数/源码哈希及完成标志均保存在对应目录。

```bash
MA7_FAMILY=/Users/ZK/OpenCode/quant-strategy-lab/research/asset-portfolios/1d-ma7-bidirectional-trend-generalization
MA7_PY=/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python
"$MA7_PY" "$MA7_FAMILY/scripts/audit_inputs.py" --run-id repro-inputs
```

这一步重新调用可信入口并验证全内容。将repro-inputs与固定p0-inputs的每个symbol的`dataframe_hash`逐项比较；必须874个完全相同。压缩文件SHA可能因gzip写入时间不同而不同，不能因此替换内容SHA检验。若接口pin或bundle不一致，停止并报告版本漂移，不能回退直接读湖或补洞。后续计算仍读取固定p0-inputs原始返回帧；前一步比对用于证明它可以从可信入口重建，不把自建快照作为其他研究的事实源。

```bash
"$MA7_PY" "$MA7_FAMILY/scripts/verify_reference.py" --run-id repro-reference
"$MA7_PY" -m pytest "$MA7_FAMILY/scripts/test_engine.py" -q
"$MA7_PY" "$MA7_FAMILY/scripts/run_research.py" development --run-id repro-development
"$MA7_PY" "$MA7_FAMILY/scripts/run_research.py" evaluation --run-id repro-evaluation --selection-dir repro-development
"$MA7_PY" "$MA7_FAMILY/scripts/run_applicability.py" --run-id repro-applicability --selection-dir repro-development
"$MA7_PY" "$MA7_FAMILY/scripts/statistical_review.py" --run-id repro-statistics --evaluation-dir repro-evaluation --applicability-dir repro-applicability --selection-dir repro-development
"$MA7_PY" "$MA7_FAMILY/scripts/final_evidence.py" --run-id repro-final-evidence --evaluation-dir repro-evaluation --applicability-dir repro-applicability
"$MA7_PY" "$MA7_FAMILY/scripts/verify_final_replays.py" --run-id repro-ledgers --evaluation-dir repro-evaluation
"$MA7_PY" "$MA7_FAMILY/scripts/render_trade_paths.py" --run-id repro-paths --evaluation-dir repro-evaluation --selection-dir repro-development
```

验收锚点：开发结果SHA为`f1d3a55779850cb25912051284b2e724a0e8473c71ad74285f3ce27a02bcda0f`，评估结果SHA为`0b9daaafe44dac5a83c73b6f1a49c7f8a0460e6b21cf54adcb694e0818c656f4`，筛选结果SHA为`40589a2dde6ff203d45bbacbd0defcd2429e641b16a40b51a4bcd1f598d8988a`。它们指`results.csv`，不是带运行时间的JSON。选择仍为C3；205个主币每候选一行；主窗C3正收益34、严格7；244币×4×3参考差<=1e−8。任何不一致先报告复现失败，不解释新机制或改参数。

默认脚本共计算740开发结果、36310评估结果、7735后续配置结果；每结果内部重跑费用场景。大型逐笔文件包含年度/主窗/部分段等重复回放，不能直接把全文件交易条数当独立样本量。统计分析只取available_segment自然退出后再做互斥资产/时间筛选。

## 官方基本面、资金与图形复现

```bash
"$MA7_PY" "$MA7_FAMILY/scripts/audit_funding_scope.py" --run-id repro-funding
"$MA7_PY" "$MA7_FAMILY/scripts/audit_stock_fundamentals.py" --run-id repro-stock-fundamentals
```

资金脚本重新走受信入口；预期完整主窗日历数0，并保留net startup身份材料拒绝。基本面脚本重算保留的SEC原始JSON，字段应714日、628个一致年度字段日。实时重下载SEC/API可能出现新申报，属于新的来源快照，不能覆盖本次16份原始JSON；全部URL和HTTP状态见[官方收据](../artifacts/official-source-review/official-sources-receipts.json)、[SEC收据](../artifacts/official-source-review/sec-eight-stock-receipts.json)。

HTML载荷需要14案例、197笔交易、唯一交易ID、合法端点；验算结果见[verification](../artifacts/p4-trade-paths-20260908/verification.json)。生成结果自包含无CDN。语法检查已执行；当前浏览器URL策略拒绝本地文件，未完成视觉验收，不使用其他浏览器/localhost绕过。

## 归档边界

`sync_to_lab.py`只同步本家族拥有文件。每次先比对正式Lab上次manifest的SHA，目标未知变化立即停止；不删除文件，不覆盖其他家族。研究/资产索引和消费者注册采用单独定点编辑，不能复制整个脏仓库。

约523MiB归档包含输入帧、不可抹去的初版失败证据、官方JSON、逐笔及路径。两个评估逐笔gzip各约137MiB，不进入普通Git；详细保留/可逆外置方案见[交付验收](../diagnostics/delivery-verification-20260908.md)。复现目录只用于独立核验，不应无限累积新历史调参轮次；本次没有移除、外置、购买或公开上传任何数据。
