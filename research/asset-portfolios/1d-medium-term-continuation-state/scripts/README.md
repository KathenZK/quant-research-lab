# 执行与复现

本目录脚本仅服务BIN-1D-MTCS。实际数据接口来自正式Lab，数据根显式固定，不读取其他家族缓存。

- [冻结合同](../specs/research-contract.md)
- [输入请求](../specs/input-request.json)
- [源码与运行环境pin](../specs/source-pins.json)

Python使用正式Lab虚拟环境。以下命令在本家族目录运行；已存在的正式产物不得删除或覆盖。原运行在独立worktree完成后，按[同步清单](../artifacts/sync-manifest.json)逐文件同步正式Lab。数据湖没有被本轮写入。

## 先复核已保存结果

先读[最终报告](../diagnostics/research-report-20260908.md)、[真实重建收据](../artifacts/reconstruction-audit.json)、[捕获独立审计](../diagnostics/p2-independent-audit.md)及[统计参考对拍](../artifacts/p1-statistics-exact-r1/reference-parity.csv)。

运行必要测试：

```sh
/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python -m pytest -q scripts/test_engine.py scripts/test_capture.py scripts/test_statistics.py scripts/test_statistics_exact.py
```

[独立资金审计](audit_p2_retained.py)只读保留输出，已有审计收据存在时比较而不覆盖。读取持仓CSV后须把退出时间列显式解析为日期，字面NaT才成为日期缺失，不能直接对字符串判空。

```sh
/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python scripts/audit_p2_retained.py
```

[真实重建脚本](verify_reconstruction.py)对全部输入帧重建全部列，另有直接价格/时间算术及未来截断检查；它拒绝覆盖既有收据。已有证据可直接读收据；需再执行时使用独立家族副本保留这次记录，不能删除原收据来伪造首次运行。

## 原始执行链

下列为本次实际执行命令。除完整统计检查点入口可恢复同身份运行外，其余研究阶段拒绝已有产物目录。新一轮完整复现须选新run-id并显式传递上一阶段ID，原结果和失败均保留。

```sh
/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python scripts/audit_inputs.py
/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python scripts/run_research.py
/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python scripts/run_statistics.py
/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python scripts/run_statistics_exact.py --parity-only
/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python scripts/run_statistics_exact.py
/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python scripts/run_capture.py
```

- [P0入口](audit_inputs.py)：默认p0-inputs；先backward=1调查，再backward=60/forward=0可信启动，只保存第二次返回。
- [P1入口](run_research.py)：`--input-run`指定P0，`--run-id`指定新P1；不按未来标签有效性删掉事前信号。
- [初次统计](run_statistics.py)：`--panel-run`及`--run-id`。初次IF近似验收失败是必须保留的记录，区间不得用于裁决。
- [完整统计](run_statistics_exact.py)：`--panel-run`、`--original-run`及`--run-id`；默认每个60/120日块各1,000,000次，固定种子20260908。相同身份中断可用原命令恢复；输入、源码、配置或分块哈希不符会拒绝。复制分块和原2048完整参考全部保留。
- [捕获入口](run_capture.py)：`--panel-dir`指定P1、`--run-id`指定输出。10单元×2成本；各连续段独立资金，不串财富，不把资金费补0。

当前脚本的正式运行依赖[原源码pin](../specs/source-pins.json)与各运行的独立执行收据。P1 panel哈希、原合同、源码保持一致才可解释本次结果。脚本通过不表示数据可以在其他家族中绕过可信入口使用。

## 说明性图表与报告

[路径图脚本](render_path_diagnostic.py)只画同一完整20日队列的均值路径，20日期末与固定P1点估计核对。数据导出使用Lab Python的`--export-only`；绘图使用含pandas和Matplotlib的独立Python环境加`--render-only`。本次图表环境位于临时目录，未修改Lab虚拟环境；数据导出和图表各有哈希收据。图表生成不新增推断或退出候选。

[报告生成](write_report.py)只消费已完成统计与捕获产物，拒绝覆盖原报告。[交付核验](verify_delivery.py)核对运行哈希、测试收据、必要文档与本家族链接。[同步脚本](sync_to_lab.py)只同步本家族拥有文件；正式Lab有未知修改时拒绝覆盖，不执行删除。

## 输入与结论限制

完整历史PIT、资金费、历史订单成交和保证金强平均未完整验证，见[数据范围](../diagnostics/data-scope-and-funding.md)。所有2019–2026历史是重复使用的诊断；0.25ATR门槛、20日主期限、46项同时比较不能在结果后放宽。只读复现不构成新样本确认。
