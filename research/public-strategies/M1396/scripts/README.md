# M1396 scripts

信号仅在signals.py；oracle.py用Fraction独立计算，不调用信号函数。共享[日线内核](../../../_shared-kernels/catalog-daily-cash/README.md) v1由specs/kernel-pin.json逐文件SHA锁定；不调用其他strategy runner。独立账户验证另写代码并逐字段检查NAV/fills/pending/months/roundtrips，统计使用stdlib对numpy。

check_synthetic.py及check_causality.py --synthetic只读人工价格。rebuild_input.py只读50既有原始对象，无网络、无指标/收益。run_replay.py在真实输入读取/特征计算前要求root gate及当前C0全部文件hash；不存在默认放行。

环境：OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1，Python/包符合specs/environment-lock.json。历史运行由root给--root-gate，四cases只有策略，不运行新control。restore_run.py是授权后的新目录本地重建，不等于异地备份。
