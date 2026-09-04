# BIN-1D-MA7-CTP P7 时间漂移、分数单调性与概率校准归因审计

- 状态：`explore / diagnostic-only / not promoted / not live-ready`
- 全局 verdict：`DATA_OR_REPRODUCTION_FAILURE`
- P8 唯一推荐分支：`E`，停止历史优化，进入冻结观察。
- 2025+ 数据角色：`ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS`，不是 strict OOS / blind holdout。

## 结论先行

P7 复现了样本量、HYPE/HYPER 隔离、TradFi 排除和固定 raw 阈值等锚点，但未能把 `R_B0_69` 确定性重建到 `1e-8`：最大 raw probability 误差为 `0.00928714`。按合同，本轮停止所有漂移机制解释，不能回答“为什么 2025 差、2026 好”的模型机制问题。

## 锚点表

| 样本 | n | threshold n | threshold success | threshold net |
| --- | ---: | ---: | ---: | ---: |
| Development OOF | 42649 | 2133 | 42.10% | 1.57% |
| 2025 | 32111 | 839 | 33.13% | -0.51% |
| 2026 | 14781 | 511 | 41.68% | 1.95% |

## 不能得出的结论

- 不能确认固定分数箱单调性或最高分尾部可靠性。
- 不能确认排序失效、校准失效或 regime 条件信号。
- 不能确认 feature/universe shift 对年度差异有解释力。
- 不能确认 P6 的 `MARKET_OR_SIDE_VALUE_ONLY` 是可交易机制。
- 不能确认任何 live-ready、dry-run 或 promotion 结论。

## 审计解释

当前 P5 脚本 hash 与 P5 manifest 一致，但用该脚本重新执行 P5 development B0 OOF，仍与冻结预测最大相差 `0.00928714`；final 2025+ 重建最大相差 `0.000207733`。P7 没有权限改写 P5/P6 frozen predictions，也不能用已看 2025+ 结果重新拟合 B0，因此唯一合规 verdict 是 `DATA_OR_REPRODUCTION_FAILURE`。

## 证据文件

- [summary](../artifacts/binance_1d_ma7_ctp_p7_summary.json)
- [anchor parity](../artifacts/binance_1d_ma7_ctp_p7_anchor_parity.json)
- [model reconstruction](../artifacts/binance_1d_ma7_ctp_p7_model_reconstruction.json)
- [modeling audit](binance-1d-ma7-ctp-p7-modeling-audit-2026-09-04.md)
