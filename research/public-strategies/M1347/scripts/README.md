# M1347 实现及验证入口

`signals.py` 只用 `calendar.monthrange` 与 UTC bar-open 日期生成标记；`oracle.py` 独立用 ordinal 和下月首日相减核对。没有价格指标、阈值或指标种子。

`kernel_loader.py` 每次载入均核验 `specs/kernel-pin.json` 的四个对象，包括 README、manifest、engine、verify_account。调用冻结 `catalog-daily-cash/v1`，账户实现不复制到本家族。`run_replay.py` 沿用既有四配置输出结构；`verify_replay.py` 消费独立日历特征并调用冻结独立账户校验器，无策略回放。

运行环境固定在 [environment-lock](../specs/environment-lock.json)，线程环境变量均为 1。常用命令（路径由执行者提供）如下：

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python research/public-strategies/M1347/scripts/check_synthetic.py --fixture-dir NEW_PRIVATE_SYNTHETIC --output NEW_PRIVATE_RECEIPT.json
python research/public-strategies/M1347/scripts/rebuild_input.py --raw EXISTING_FIXED_RAW --reference EXACT_INPUT.csv --receipt NEW_INPUT_QA.json
```

以上人工价格合成与真实输入质量验证分别执行；输入质量检查不计算策略特征或收益。首轮 95 项合成覆盖 400 年公历、全账户、prefix/future、缺失与损坏输入拒绝、完整 24 月和期末库存。单根截断合成会触发原 numpy 样本方差警告；其 Sharpe 按冻结原函数为空，正式窗口恒为 731 日，不改变内核来隐藏警告。

实际回放另要求 root 提供 `ROOT_APPROVED_HISTORY_AFTER_INDEPENDENT_QA` gate，精确绑定本 ID C0、代码 commit、独立代码回执及已验控制。此处不给自签放行文件。

```bash
python research/public-strategies/M1347/scripts/run_replay.py --input EXACT_INPUT.csv --output NEW_RESULTS --root-gate ROOT_RELEASE.json
python research/public-strategies/M1347/scripts/verify_replay.py --input EXACT_INPUT.csv --results RESULTS --output NEW_QA.json
python research/public-strategies/M1347/scripts/check_causality.py --input EXACT_INPUT.csv --root-gate ROOT_RELEASE.json --output NEW_CAUSAL_QA.json
python research/public-strategies/M1347/scripts/restore_run.py --input EXACT_INPUT.csv --root-gate ROOT_RELEASE.json --results RESULTS --destination NEW_FRESH_DIR
```

恢复复制全部 C0 对象、固定共享内核、输入和独立放行证据到新目录，重建 30 个结果对象加 manifest，逐字节比较。要求预装锁定运行环境；本地恢复不等于远端或 Library 完整备份。50 原档重建不联网；远端 core 的输入重建权限与私有包状态由协调者单独记录。

严格账户字段为原 Decimal 文本；独立 numeric 补充审计只接受精确 Decimal 相等。收益、回撤和 Sharpe 等统计沿用冻结 numpy 实现及 stdlib 独立校验，不重新搜索统计口径。
