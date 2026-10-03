# Catalog daily cash v2：可选持仓期限

本版本仅最小扩展共享日线账户层，不计算ROC或其他信号、不运行策略历史。父版本v1的fill_order/reconcile/metrics及已有文件原字节保留；默认policy=None时完整JSON、六类CSV及统计输出与v1一致。M1346/M1270继续v1，预期消费者M1349需独审及自身C0后使用v2。

## API

```python
policy = {"max_completed_closes": 25}
result = engine.simulate(rows, features, case, start=31, execution_policy=policy)
columns = engine.output_columns("nav", execution_policy=policy)
receipt = verifier.verify_account(rows, results_dir, spec, independent_raw_events,
                                  execution_policy=policy)
```

policy只能为None或只含正整数max_completed_closes的dict；bool、float、字符串、0、负值、额外字段拒绝。默认None保留原行为和原字段；NAV/DEC常量仍为默认schema，启用policy的消费者必须用output_columns选择列。输出kind限nav/fills/pending/decisions/monthly/roundtrips。

M1349信号适配器只负责原始ROC25严格低于−0.10的entry，raw_exit恒0；不能在适配器重放影子持仓或模拟期限。一般policy允许原有raw_exit更早退出，但绝不自行生成ROC恢复退出或其他信号。

## 实际账户生命周期

- 实际BUY在open e成交后，计数重置0；该根close只要实际仍持多就增到1。待成交BUY和取消的BUY不计持仓。
- 第25个持仓close，即e+24，锁存强制exit。effective_entry置0、effective_exit置1，调用原reconcile保留最早sell due。
- 因此lag1卖于e+25 open，lag2卖于e+26 open；lag2等待中计数可到26，最初trigger index保持不变。持续entry不能撤销或推迟强制sell。
- 实际SELL才清除计数、锁存与trigger；同一open不再入场。该日后续close若原始entry仍真，可排下一开盘BUY。
- 数据在触发或due前结束则保留实际持仓/终端挂单，不强平、不读取窗口外价格。

只有policy启用时，NAV新增held_completed_bars、mandatory_exit_latched、mandatory_exit_trigger_index；decisions再新增effective_entry、effective_exit、exit_reason（time25/一般timeN、signal或空），原raw_entry/raw_exit完全保留。summary新增execution_policy和三个terminal生命周期字段。事件/fill等原schema保持，结合close decisions可解释forced exit，原始信号没有被伪造为timeexit。

独立verifier不导入engine或状态函数，用实际BUY索引计算j−buy_index+1，独立锁存及撤单/账本推进，逐字段核对生命周期、挂单、账户、月报、往返及统计。沿用原冻结731评估日/762输入/4配置范围；传入同一policy为明确调用契约。caller仍须独立核原始指标/信号，本内核不能代替策略指标验证。

## 合成验证

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python research/_shared-kernels/catalog-daily-cash/v2/tests/test_lifecycle.py --output NEW_RECEIPT.json
```

22组检查：9种非法policy、20套默认JSON+六CSV/指标字节兼容、实际buy后计时、lag1/2截止、持续entry锁存、消失信号保留BUY、取消未成交BUY、早退后重入重置、无warmup持仓、limit1、36组prefix/future及完整独立账户。人工762bar/4配置验证2924日状态、224成交、96月；污染计数字段被独立verifier拒绝。没有市场文件、网络或新增研究trial/control。回执见tests/synthetic-receipt.json。

API/实现待root安排独审后消费方才可pin。准确源文件hash见manifest.json；本变更不发布、不改原family/global治理，根README-versions索引治理兼容由root集成。
