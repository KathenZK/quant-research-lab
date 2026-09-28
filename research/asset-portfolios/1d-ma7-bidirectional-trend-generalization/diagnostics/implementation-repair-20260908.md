# 严格均线穿越的复现修复

首次24项合成测试通过，但在全部真实244币的旧基线对拍中，1INCH 多头收益与冻结值出现4.830069846个百分点差异。已停止解释原运行，并给初次开发、主回放和筛选运行添加 `INVALIDATED.json`；原文件保留，不覆盖。

原因是本机 Python 3.13 的 `sum(list[float])` 使用补偿求和，而对 NumPy 标量使用内置sum产生不同的末位舍入。严格小于/大于的MA7穿越在恰等边界会改变交易。旧引擎使用 Python float 列表；新特征函数原先直接求和 NumPy 切片。修复仅使指标数值算法与冻结参考一致，不改SMA7、ATR14、候选、成本、分母或选择准则。

修复后完整244币×4基线×3成本共2928项收益对拍通过，默认交易数与回撤也逐项通过，容差仍为1e-8。真实1INCH边界新增专项回归测试，25项测试通过。证据：[首次失败](../artifacts/reference-parity-console.txt)、[完整对拍](../artifacts/reference-parity-20260908-r1/report.json)、[逐项差异](../artifacts/reference-parity-20260908-r1/parity.csv)、[修复后测试](../artifacts/engine-tests-r1.txt)。

开发候选重新运行并重新锁定，验证与筛选只能消费修复后的锁；以前锁已揭示这一事实保留，整个研究仍为复用历史诊断，不升级为盲测。首次筛选运行还发现月度产物变量拼写错误，在保存完成标志前中断并修复；属于工程重跑，不是新的参数尝试。证据：[首次筛选日志](../artifacts/p2-applicability-console.txt)。

最终元数据审阅发现：r1锁的自动字段 `unrevealed_in_this_family` 仍沿用首次运行文本，范围过宽。准确表述是“锁在修复版验证计算之前”，而无效版结果已经部分揭示。原锁不覆盖，另存[字段澄清](../artifacts/p1-development-20260908-r1/selection-lock-clarification.json)，并修正以后重跑的元数据措辞；不改交易计算或选择结果。原计算源码保存在[计算源码快照](../artifacts/source-snapshots/20260908-computation/)。

统计阶段还遇到未安装statsmodels、segment-id误当整数两项工程问题：没有安装或降级环境，以NumPy/SciPy实现两维聚类协方差，并改用真实字符串段身份；首次失败输出保留。最终[30项测试](../artifacts/engine-tests-final.txt)包含协方差退化为单聚类的手算对照及BH校正已知值。最终[真实回放验算](../artifacts/final-replay-verification-20260908/report.json)对206份主路径的2060本逐笔账独立重建3216120个每日权益点，另做1236项真实数据前缀检查，均通过。
