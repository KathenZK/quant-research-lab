# 复现入口

在 Lab 根目录使用 `.venv/bin/python`。成功保留结果为 `artifacts/20260908-r1`，首次浮点严格相等核对的失败证据在 `artifacts/20260908`。默认拒绝覆盖已有回放或分析。

独立复跑依次执行以下脚本，均添加同一个全新 `--run-id replay_01`（若已有则另取名称）：

1. `research/asset-portfolios/1d-ma7-atr14-long-short-audit/scripts/run_audit.py`
2. `research/asset-portfolios/1d-ma7-atr14-long-short-audit/scripts/analyze.py`
3. `research/asset-portfolios/1d-ma7-atr14-long-short-audit/scripts/audit_paths.py`
4. `research/asset-portfolios/1d-ma7-atr14-long-short-audit/scripts/build_report.py`

复跑仍读取本主题冻结合同及 Lab 共享湖，不跟随最新指针。输入由 `load_inputs → require_research_startup` 返回；其他脚本仅读取本主题保留结果。原主题的结果文件只作哈希固定的对拍参考，不作为新主题行情源。`baseline_engine.py` 仅调用冻结指标与原多头执行函数，不调用下载入口。报告生成器可从已保留的分析表重建。

专项测试：`.venv/bin/python -m pytest research/asset-portfolios/1d-ma7-atr14-long-short-audit/scripts/test_engine.py -q`。结果输入和运行时代码分别固定 SHA256；全市场回放另含原版对拍、独立空头账本、前缀与逐笔结算检查。

## 适用性规律审计

依次使用 `applicability_features.py`、`analyze_applicability.py`、`build_applicability_report.py`。前两步拒绝覆盖 `artifacts/applicability-20260908` 的已有运行或分析。独立复跑应在新的研究副本中保留冻结合同与原回放依赖，不删除已有输出；报告可以从保留的统计表重建。

`applicability_features.py` 再次走登记的可信输入入口，严格核对本主题原有完整历史回放，然后附加入场前/年初前的指标与成交额特征。分析器只读取本主题已保留特征及年度结果。没有执行新的筛选策略；六条件和检验标准事前固定在 `specs/applicability-contract-20260908.json`。五个新专项测试位于 `test_applicability.py`。
