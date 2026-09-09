# 2026-09-08 生命周期诊断的价格输入留证

这不是回测结果或新的湖数据集，而是本轮 `require_research_startup` 返回帧的可再生列投影。输入固定为 `binance.v3.research_inputs.v2` 中的 1d v2，全 874 个观测库存代码；包含混合资产及历史合约，不等于当前活跃名单、历史 PIT 或可交易性证明。

本轮价格请求全部通过：7 个批次、874 / 874 标的，640,378 行。587,106 行可用于其所在连续段，53,272 行无效记录原样保留，未删行后拼接。请求是 `[2019-09-09T00:00:00Z, 2026-09-05T00:00:00Z)`，回看 1 根、未来 0 根；下游构造更长特征或标签仍须自行检查整段窗口。

- [冻结请求](../../specs/lifecycle-input-request-20260908.json)
- [价格加载器](../../scripts/load_binance_1d_mcsm_lifecycle_inputs_20260908.py)
- [输入摘要、指纹与逐批证据入口](summary.json)
- [逐标的覆盖与原 API 帧投影哈希](symbol-coverage.csv)
- [本轮返回日线投影](daily-returned-frames.parquet)
- [独立 QA](independent-input-qa.json)：18 项通过，包括全部 874 标的的 Parquet 往返投影哈希、段内逐日连续性、有效性 mask 和 5 项请求篡改拒绝测试。
- [QA 脚本](../../scripts/verify_binance_1d_mcsm_lifecycle_inputs_20260908.py)

## 保留与重建

Parquet 为 18,009,769 字节（约 17.18 MiB），属于 B-review 级可再生本地数据集。保留原因是把下游诊断唯一绑定到本次治理入口实际返回的帧，不需反复复制或绕过入口重读行情湖。完整 Parquet 不应加入普通 Git；只保留本轮一个完整投影，后续轮次不要无界复制。所有旧证据保持不变，不自动执行删除。

在仓库根重建时使用新目录，加载器拒绝覆盖已有留证：

```bash
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/load_binance_1d_mcsm_lifecycle_inputs_20260908.py --run-id lifecycle-inputs-20260908-rebuild
```

复核本轮已保存对象：

```bash
uv run python research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/verify_binance_1d_mcsm_lifecycle_inputs_20260908.py
```

本轮 Parquet SHA256 为 `3565255edeafcdc5dd3083191b820d2302f993e4ac89679bd812e43601e7049a`。加载脚本、冻结请求、启动核心、catalog 和分段读取器哈希记录在 `summary.json`；每次启动再次核验固定 bundle 全部组件内容指纹。下游读取本产物时须核验摘要所指请求、帧及报告哈希，而不是把过去的成功报告当作访问其他湖路径或旧缓存的许可证。

价格诊断通过不认证资金费、成本、执行时序、历史身份、PIT、实盘或策略收益。`funding_window_verified`、`pit_universe_proven`、`tradability_proven`、`strategy_approved` 均为 false。
