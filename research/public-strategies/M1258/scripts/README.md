# M1258 脚本

全部脚本是本 ID 的独立研究实现，不调用旧策略 runner，也不新增共享平台。`run_replay.py` 的指标及账户采用 Decimal50；`verify_replay.py` 用 Fraction 独立构造 Wilder 与跨线，另写 Decimal 账户、事件、月度和 stdlib 统计。numpy 指标公式沿用 M0216 / M1358 已明确的初始锚点、365/n 与样本标准差口径，仅公式复用。

`rebuild_input.py` 根据冻结 50 对象离线校验并重建 canonical，源自 M1358 远端恢复的规范化方法，不导入旧策略。`check_synthetic.py` 仅人工价格；`check_causality.py` 在 C0 后核 prefix / future mutation，不计额外研究配置。`restore_run.py` 在全新目录复制固定代码和输入，并精确比较 37 个输出与清单。

运行环境要求 `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1`，Python 和包必须匹配 [环境锁](../specs/environment-lock.json)。无网络调用。历史运行须经过独立 C0 门禁。全部输入、完整账户和特征只写调用者指定的私有输出目录。
