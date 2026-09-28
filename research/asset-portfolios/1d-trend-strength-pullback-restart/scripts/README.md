# 执行与复现

本目录仅为BIN-1D-TSPR一次性入口及审计；多资产引擎/统计/会计位于[冻结共享v1](../../../_shared-kernels/trend-strength-pullback-restart/v1/README.md)，manifest SHA256=`9b8575fb3c3bfd59b314bb805bb6f1cfdba4c26655c01dfb59b09f8e46dd0209`。

研究运行时：`/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python`。正式来源根与数据根分别为`/Users/ZK/OpenCode/quant-strategy-lab`及其`data/`，由[输入请求](../specs/input-request.json)、[源码pin](../specs/source-pins.json)和[计算锁](../specs/computation-lock.json)共同约束。输入使用本家族新P0返回帧，没有旧家族panel回退。

| 顺序 | 入口 | 作用 |
|---|---|---|
| P0 | [audit_inputs.py](audit_inputs.py)、[verify_p0_inputs.py](verify_p0_inputs.py) | 两阶段可信启动、全部返回帧及过去窗口核验 |
| P1 | [run_research.py](run_research.py) | 固定状态、标签、矩阵、共同样本路径 |
| P1核验 | [verify_research.py](verify_research.py) | 全源行、方向状态、未来标签及前缀独立公式 |
| 联合推断 | [run_statistics.py](run_statistics.py) | 24维共同日期60/120日块，不接受替代参数 |
| 统计核验 | [audit_statistics_outputs.py](audit_statistics_outputs.py) | 不导入生产统计内核，重核点/支持/复制/区间/裁决 |
| P2 | [run_capture.py](run_capture.py) | 8组×两成本，单币单段不重叠20日持有 |
| P2核验 | [audit_capture.py](audit_capture.py) | 独立资金公式、全部机会接续及分层日权益 |
| 解释导出 | [export_contributions.py](export_contributions.py)、[render_findings.py](render_findings.py) | 固定贡献删除与静态图，不增加候选 |
| 交付 | [sync_to_lab.py](sync_to_lab.py) | 仅拥有文件、冲突拒绝、逐文件哈希 |

首次运行按P0→P1→统计/P2→各自审计执行；统计和P2可在P1完成后并行。生产入口拒绝覆盖已保留产物；统计支持同身份检查点恢复。再次研究须保留现有证据，用独立副本/新运行身份，不能清空旧产物或更改冻结v1。新定义使用新版本并重新冻结。

本轮105项合成测试及5项子测试通过，见[结果前检查](../artifacts/pre-result-verification.json)。P0已冻结的入口有两处显式路径导入顺序E402例外；其余本轮冻结代码ruff检查通过。

绘图使用应用Python 3.12与任务临时目录`/tmp/codex-tspr-report-plotdeps`中的matplotlib，未改研究环境；解析版本见[依赖日志](../artifacts/render-dependency-install.log)。图只读冻结CSV，含pyarrow面板的贡献表由原研究Python导出。初次环境失败见[运行说明](../artifacts/interpretation/render-runtime-receipt.json)；最终[制图收据](../artifacts/interpretation-figures/receipt.json)与[贡献收据](../artifacts/interpretation-tables/receipt.json)均完成。

[结论](../diagnostics/research-report-20260908.md) · [主账](../binance-1d-tspr-core-ledger.md) · [产物索引](../artifacts/README.md)
