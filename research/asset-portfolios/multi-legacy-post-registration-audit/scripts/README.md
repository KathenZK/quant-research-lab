# 复现入口

在仓库根使用 `.venv/bin/python`。所有输出归本主题；旧家族脚本仅作为原实现导入，禁止运行它们的搜索/主程序。

1. `prepare_inputs.py`：冻结6币15m/1h范围，通过完整启动接口，返回帧保存为带哈希的研究输入；资金事件另行核验保存，不声称全覆盖。
2. `prepare_marks.py`：辅助标记价格REST快照，保留官方原响应、时间网格和OHLC检查；不伪称catalog成交价数据。
3. `hype_legacy_replay.py`：HYPE CC、EMA-X、EMA-TB、MII与组合的最新版本。
4. `hype_other_replay.py`：其他HYPE有固定规则的家族，命令行按case运行。
5. `other_assets_replay.py`：5币1h最新冻结策略与固定压力场景；配置从原模块/spec恢复，缺优先级时核对两种顺序的逐笔一致性。
6. `ensemble_replay.py`：六币1h组合固定的ETH V3、SOL V2及其他原成分，按原账户阻塞规则。
7. 其他 `other_assets_*` 和 `hype_other_*`：恢复固定观察、审计/补充回放；具体机器产物记有来源和参数。
8. `build_report.py`：汇总结果与前30天/后段，不按成绩选策略。

原参考、配置和输入均有单独SHA256；重新复现须核对本次pin，不能自动切换“当前默认数据”。

2026-09-11版本比较的独立入口：

1. `prepare_iteration_inputs.py`：重新完成正式研究启动，将实际返回价格保存到本轮目录并与前次快照逐值核对；`iteration_common.py`绑定这些输入。
2. `prepare_iteration_scope.py`：固定14组对照和3组不能配对的原因，不能根据结果更换版本。
3. `compare_cc_versions.py`、`compare_ema_versions.py`、`compare_ar_mmtf_versions.py`：三个分组的固定版本与账户情景，输出逐笔交易、净值、月表、参数和来源。
4. `build_iteration_report.py`、`plot_iteration_results.py`：汇总101条结果和14组对照，生成总报告与两幅图。
5. `review_ema_iteration_independent.py`、`verify_iteration_ar_mmtf_independent.py`、`review_cc_iteration_independent.py`：交叉独立验证，验收结果位于本轮目录的`acceptance_*_independent.json`。
6. `review_iteration_aggregate.py`、`finalize_iteration_archive.py`：检查最终汇总与文件链接，保存本轮归档哈希。保留9月10日原结果，MMTF错误的复现及更正另行落档。

## 全仓排序，2026-09-11

- `replay_repository_additions_20260911.py`：日线、高周期及BTC/ETH固定组合，复用原引擎和本次已核验输入。
- `replay_repository_transfers_20260911.py`：原固定迁移、PIC V2、MII代表配置和海龟原诊断模型。
- `probe_repository_inputs_20260911.py`：保留MU、原22币及LS3整池输入范围检查；失败不放宽后直接继续。
- `replay_repository_new_inputs_20260911.py`：MU与Generic MA7原22币，读检查返回并保存的价格帧及单独标注的资金事件。
- `build_repository_ranking_20260911.py`：全仓覆盖、三种排序、仅登记版本排序和独立HTML页面。
- `verify_repository_ranking_20260911.py`：数字对应与排序复核，另独立计算两组高收益观察的现金变化及回撤。

运行记录保存在 `../artifacts/repository_ranking_20260911/final_replay_execution.json`。不调用原搜索入口、不覆盖原策略、不操作生产。
