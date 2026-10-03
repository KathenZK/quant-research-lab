# M2903 收益前实现

`signals.py` 只负责完整canonical EMA20事件；`oracle.py` 用Fraction逐运算Decimal50舍入独立比对，不调用信号实现。`kernel_loader.py` 按精确hash消费旧cash v1。`check_synthetic.py` / `check_causality.py` 只生成确定性人工序列，不接受市场输入。

当前 `run_replay.py` 已按公布接口接线，但缺少正式C0和独审适配层pin，因此历史入口关闭。待实际代码独审后完成集成测试，不能把此draft作为执行版本。`-O` 在读门禁或输入前拒绝。

合成命令使用已固定Python环境，设置OMP_NUM_THREADS=1、OPENBLAS_NUM_THREADS=1；`--output`、`--fixture-dir` 必须是不存在的新私有路径。测试生成完整人工账本，不公开，不计策略运行。

共享input/view已合并远端43becf3c，独审receipt与代码hash精确pin；实际wrapper合成/映射/输入拒绝及freshprocess通过。下一步正式C0和独审后仍需root单独放行；无历史运行。
