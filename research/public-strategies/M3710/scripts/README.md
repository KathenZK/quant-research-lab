# M3710 代码入口

`signals.py` 只计算完整 canonical SMA20 状态；`oracle.py` 用 Fraction 实现独立的逐步十进制舍入。共享适配器校验 full 831/100，输出同一 762/31 账户视图，任何视图都不重新播种指标。`dependencies.py` 每次检查全部固定依赖字节后加载共享模块，无生产路径覆盖。

人工合成命令（已匹配 Python，令 `python` 指向环境锁中的解释器）：

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python scripts/check_indicator_synthetic.py --output NEW_INDICATOR_RECEIPT.json
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python scripts/check_gates.py --fixture-dir NEW_GATE_DIR --output NEW_GATE_RECEIPT.json
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python scripts/check_synthetic.py --fixture-dir NEW_SYNTHETIC_DIR --output NEW_SYNTHETIC_RECEIPT.json
```

仅 `check_synthetic.py` 提供显式 `--synthetic-dependency-root`，用于正式依赖合入前只读固定共享工作树；它内部只创建人工价格。真实 `run_replay.py` 没有该覆盖选项。原内核 ddof=1 在单日人工前缀会产生自由度警告；未修改内核或静默更换统计。

将来获准后：`run_replay.py --input INPUT --output NEW_RESULTS --root-gate ROOT_RELEASE`。在读取输入前验证磁盘余量、精确 C0、独立代码审查与 root gate。执行锁定四配置、0 新基准；输出 37 payload 加 manifest 共 38 文件，包括 full/view 特征、账户视图、完整索引映射及每个配置的净值、决定、意图、成交、月报、往返交易和汇总。所有完整行情与账户输出仅私有。

`verify_replay.py` 用独立 Fraction 特征、共享独立 Decimal50 账户校验和另外的索引运算审计；`check_causality.py` 仅在 root gate 后验证历史特征前缀与未来扰动，不重跑账户。`restore_run.py` 将已冻结代码、依赖及输入复制到新目录、新进程重放一次，再与独立保留的原 reference 逐字节比较；不会把新输出用作自身参考。

`rebuild_input.py` 只做离线数据恢复：按固定 56 个 ZIP/CHECKSUM 的字节及 CRC，从 853 原始行显式选择 831 行，调用共享输入验证器，不计算指标。原始行情与论坛/论文全文不公开；许可、PIT 与可用性限制见家族说明。

C0 前的合成结果不放行真实研究。`gates.REQUIRED_C0_PATHS` 为不可缩小的精确冻结集合，缺任何必要对象都失败；不得用草案 C0 或缺失的独审回执跳过。
