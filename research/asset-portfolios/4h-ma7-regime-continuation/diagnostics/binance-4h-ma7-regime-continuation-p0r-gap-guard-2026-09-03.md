# BIN-4H-MA7-RC P0R-GAP-GUARD 验收报告（2026-09-03）

## 结论先行

- **缺口保护是否实现并通过测试：`PASS`。** 15 个合成反例全部通过真实函数调用；不依赖本地行情。
- **连续样本是否保持原结果：`PASS`。** BTC 最长连续段上，新旧 `enrich_outcomes` 的 first-hit、recross、survival、短 horizon gross/MFE 一致。
- **有多少研究样本受到缺口影响：** 全量盘点已完成。事件候选 `4,405,573` 条；主观察 `first_hit_30` 有效 `4,389,839`（`99.64%`），内部缺口 `5,298`（`0.12%`），尾部不足 `10,436`（`0.24%`）。这不是全库 K 线缺失率，也不能据此声称“缺口不影响策略”。
- **完整研究还有哪些独立 blocker：** P0R-DATA 全市场绩效尚未写出；正年度门槛不可达；horizon `p_value` 被 cluster 覆盖。本轮不修复。

本轮结论只覆盖缺口保护。不是策略有效，不是全研究通过，不可以上线。家族保持 `explore / diagnostic-only / not promoted / not live-ready`。

## 冻结与范围

- 补充契约：[binance-4h-ma7-regime-continuation-p0r-gap-guard-contract-2026-09-03.md](../specs/binance-4h-ma7-regime-continuation-p0r-gap-guard-contract-2026-09-03.md)
- 配置 SHA256：`71306a2b45471f1e8e24fcd0d6a621a94c95be7bc83e65a69c2fa6faa61bd67d`
- 输入：`binance.perp.ohlcv.4h.from_15m.v1`、`binance.perp.ohlcv.1h.from_15m.v1`；截止 `2026-08-24T08:00:00Z`
- 未覆盖任何 P0 / P0R-DATA 产物。父文件 hash 校验全部 `unchanged`：[binance_4h_ma7_rc_p0r_gap_guard_parent_hash_check_2026-09-03.json](../artifacts/binance_4h_ma7_rc_p0r_gap_guard_parent_hash_check_2026-09-03.json)
- 未下载或补齐行情，未改 raw / normalized / 已发布 derived v1，未调 MA/ATR/入场/退出/币池/成本。

## 实现要点

入口：[research_binance_4h_ma7_regime_continuation_p0r_gap_guard.py](../scripts/research_binance_4h_ma7_regime_continuation_p0r_gap_guard.py)；辅助实现：[binance_4h_ma7_rc_gap_guard.py](../scripts/binance_4h_ma7_rc_gap_guard.py)。

保留 `add_indicators()` 按连续 4h 段重置 SMA/ATR。信号成立与未来可观测分开。`ma7_recross_bars` / `same_side_survival_bars` 改走真实时间网格；缺口后反穿只进诊断字段。各指标、各 horizon 单独有效；主口径分母不含不完整样本。重复时间戳和错网格拒绝为坏输入。

```text
uv run pytest tests/test_binance_4h_ma7_regime_continuation_p0r_gap_guard.py
uv run python research/asset-portfolios/4h-ma7-regime-continuation/scripts/research_binance_4h_ma7_regime_continuation_p0r_gap_guard.py --run
```

## 测试

文件：[test_binance_4h_ma7_regime_continuation_p0r_gap_guard.py](../../../../tests/test_binance_4h_ma7_regime_continuation_p0r_gap_guard.py)。结果：`15 passed`。覆盖连续一致、预热重算、入场不顺延、中途缺口、短长 horizon 分离、尾部不足、缺 1h 路径、缺口后反穿、跨币种/phase、分母不含失败化不完整样本、资金费与行情分列、坏输入拒绝。

## 真实窗口验证

现场确认，不硬编码缺口答案。证据：[binance_4h_ma7_rc_p0r_gap_guard_verify_2026-09-03.json](../artifacts/binance_4h_ma7_rc_p0r_gap_guard_verify_2026-09-03.json)

- 连续窗口：`BTC/USDT:USDT`，`2019-09-08T20:00:00Z`–`2026-08-24T04:00:00Z`，`15,249` 根 4h。新旧对照无 mismatch。
- AERGO：`2025-04-15T20:00:00Z` 之后缺 3 根，`2025-04-16T12:00:00Z` 恢复。以缺口前一根为信号 bar 时，主口径 `internal_gap`、survival 为 NaN；缺口后反穿只记诊断 `recross_after_gap_bars=10`。

## 缺口影响盘点（全量已完成）

只统计候选、连续性和窗口可用性。未跑完整收益、bootstrap 或显著性。互斥主因 checksum 全部通过。

事件候选 `4,405,573`（含全部 MA 与 phase）；同侧非穿越对照 `1,158,125`（仅原生 0h，与 P0 对照定义一致）。PIT 池 4h bar `1,490,563`，其中指标预热不足 `3,232`（bar 级，不是事件损失率）。已形成事件的 `indicator_warmup_insufficient` 为 0。

| 样本 | 指标 | 候选 | 有效 | 内部缺口 | 尾部不足 | 有效率 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| events | first_hit_30 | 4405573 | 4389839 | 5298 | 10436 | 99.64% |
| events | ma7_recross_survival_30 | 4405573 | 4403215 | 1157 | 1201 | 99.95% |
| events | gross_return_1 | 4405573 | 4404455 | 285 | 833 | 99.97% |
| events | gross_return_30 | 4405573 | 4389402 | 5366 | 10805 | 99.63% |
| events | mfe_mae_1 | 4405573 | 4405573 | 0 | 0 | 100% |
| events | mfe_mae_30 | 4405573 | 4389839 | 5298 | 10436 | 99.64% |
| controls | first_hit_30 | 1158125 | 1153670 | 1517 | 2938 | 99.62% |
| controls | ma7_recross_survival_30 | 1158125 | 1157601 | 304 | 220 | 99.95% |

事件 `first_hit_30` 分侧：long 候选 `2,200,148` / 内部缺口 `2,828`；short 候选 `2,205,425` / 内部缺口 `2,470`。分 phase 的内部缺口约 `1,294`–`1,398`，没有单 phase 独占。年份上内部缺口主要在 2022（`4,741`），尾部不足主要在 2026（`9,731`，贴近冻结截止）。

明细：[by_metric](../artifacts/binance_4h_ma7_rc_p0r_gap_guard_inventory_by_metric_2026-09-03.csv)、[by_direction](../artifacts/binance_4h_ma7_rc_p0r_gap_guard_inventory_by_direction_2026-09-03.csv)、[by_year](../artifacts/binance_4h_ma7_rc_p0r_gap_guard_inventory_by_year_2026-09-03.csv)、[by_phase](../artifacts/binance_4h_ma7_rc_p0r_gap_guard_inventory_by_phase_2026-09-03.csv)、[by_symbol](../artifacts/binance_4h_ma7_rc_p0r_gap_guard_inventory_by_symbol_2026-09-03.csv)、[summary](../artifacts/binance_4h_ma7_rc_p0r_gap_guard_inventory_summary_2026-09-03.json)。

## 独立 blocker（本轮不修复）

- 完整年度窗口仍只统计 2023–2025，PASS 却要求至少四个正年度。
- horizon 表 cluster `p_value` 覆盖 bootstrap `p_value`。
- P0R-DATA 全市场绩效结果尚未写出。后续完整研究必须使用本轮缺口保护，而不是无保护的 `enrich_outcomes`。

读取门禁：catalog `FULL_MARKET` 通过，无降级。
