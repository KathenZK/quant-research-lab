# BIN-4H-MA7-RC P0R-GAP-GUARD 补充契约（2026-09-03）

- 家族：`Binance-4H-MA7-Regime-Continuation`（`BIN-4H-MA7-RC`）
- 观察：`P0R-GAP-GUARD`，同一家族的研究实现修正；不是新家族，不是 `V1`，不登记、不晋升。
- 状态：`explore / diagnostic-only / not promoted / not live-ready`
- 冻结时间：`2026-09-03T11:15:00Z`（**先冻结规则，再看真实样本受影响比例**）
- 配置：[../configs/binance-4h-ma7-regime-continuation-p0r-gap-guard.json](../configs/binance-4h-ma7-regime-continuation-p0r-gap-guard.json)
- 配置 SHA256：`71306a2b45471f1e8e24fcd0d6a621a94c95be7bc83e65a69c2fa6faa61bd67d`
- 输入 manifest：[../artifacts/binance_4h_ma7_rc_p0r_gap_guard_dataset_manifest_2026-09-03.json](../artifacts/binance_4h_ma7_rc_p0r_gap_guard_dataset_manifest_2026-09-03.json)
- 输入 manifest SHA256：`2af83bfaee7632ba3b77e4c4e08d104e492620d62c86b3515d586537e4c3a823`
- 父观察：[P0R-DATA 合同](binance-4h-ma7-regime-continuation-p0r-data-contract-2026-09-03.md)；机制父本：[P0 合同](binance-4h-ma7-regime-continuation-p0-contract-2026-09-02.md)

本文件只冻结**行情缺口处理、指标有效性和统计分母**。不得改 MA 长度、ATR、入场、退出、持有期、币池、成本或资金费参数。不得覆盖任何 P0 / P0R-DATA 冻结合同、配置、脚本或已有产物。

## 为什么需要本观察

已核对现有实现：

1. [`add_indicators()`](../scripts/research_binance_4h_ma7_regime_continuation_p0.py) 已按 `symbol × phase_hour` 用真实 4h 间隔切段，并在每段内重算 SMA/ATR/`ATR_scale`。本观察必须保留，不得改成“只要满 7 行就跨缺口滚动”。
2. [`build_event_candidates()`](../scripts/research_binance_4h_ma7_regime_continuation_p0.py) 已要求穿越前后两根及下一根入场 K 线同属一段且 `next_ts = ts + 4h`。合法信号不因未来缺口被删除。
3. [`enrich_outcomes()`](../scripts/research_binance_4h_ma7_regime_continuation_p0.py) 的 `ma7_recross_bars` / `same_side_survival_bars` 仍按数组位置向后切片，会跨过内部缺口把后续段当成同一趋势。
4. first-hit 与 MFE/MAE 已要求完整 1h 网格；固定期 **gross** 只要终点 4h open 存在就会计算，中间缺 K 仍可能被当成完整路径。
5. `build_first_hit_stats` 已剔除 `incomplete_future`；但年度 / phase / MA 对照 / 近期分片用 `label == favorable_first` 对**全部事件**求平均，不完整样本被算进分母，等价于失败。

## 时间戳语义（全部 `ts` 为开盘时间）

| 字段 | 含义 |
| --- | --- |
| `ts` / `signal_bar_open_ts` | 确认穿越的那根 4h 的开盘 |
| `signal_ts` | 该 4h 收盘 = `ts + 4h` |
| `entry_ts` | 下一根 4h 开盘；时钟上等于 `signal_ts` |
| `entry_price` | `open[entry_ts]` |
| 固定期 H 的平仓时点 | `entry_ts + H*4h` 的 4h open |
| first-hit 1h 窗口 | `[entry_ts, entry_ts + 120h)`，共 120 根连续 1h |
| horizon H 的 MFE/MAE | `[entry_ts, entry_ts + H*4h)`，共 `4*H` 根连续 1h |
| horizon H 的主口径 gross | `entry_ts + k*4h`，`k=0..H`，共 `H+1` 根连续 4h open |
| recross / survival | 信号 bar 之后 `k=1..30` 的 4h open |

## 连续性与坏输入

- 按 `symbol`、`phase_hour` 分组，按真实时间戳判断连续性。4h 相邻必须相差 4 小时；1h 相邻必须相差 1 小时。
- 缺口之后重新预热该段全部所需指标：`SMA5/7/10/42`、`TR`、`ATR20`、`ATR_scale=ATR20[t-1]`。不插值、不前向填充、不用后面的数据补齐缺口。
- 穿越前后两根及下一根入场 K 线必须符合原冻结时序；入场 K 线缺失时不得顺延到更晚的 K 线。
- 信号是否成立与未来结果是否可观测必须分开：未来缺口不删除当时已经合法的信号。
- 重复时间戳、非单调时间、未落在对应 timeframe 网格、间隔不是步长整数倍：视为**坏输入并拒绝**，不得记成普通缺口。

内部缺口：所需期望时点缺失，且同一 `symbol/phase/grid` 之后还有更晚的 K 线。  
尾部不足 / 右删失：所需窗口超出该网格最后一根或冻结截止，且之后没有更晚的 K 线。

## 按指标分别判定有效

不能用一个全局有效标记覆盖所有指标。短 horizon 完整、长 horizon 遇到缺口时，只使长 horizon 失效。

- **first-hit**：必须完整 120 根 1h；同小时双障碍仍 adverse-first。不完整记 `incomplete_future`，**不得进入成功/失败分母**。
- **MFE/MAE(H)**：必须完整 `4*H` 根 1h。
- **gross(H) 主口径**：必须完整 `H+1` 根 4h。仅起止价格存在但中间缺行情的收益，只允许写入诊断字段 `gross_return_{H}_endpoints_only`，不得进入主均值。
- **net(H)**：主口径 gross 有效且 `(entry_ts, exit_ts]` 资金费完整。资金费缺失与行情缺口分列；缺失不得填 0。
- **recross / survival**：在连续 4h 段上行走。缺口处标记观察中断，不能记成趋势结束，也不能记成成功持续到 30。NaN 均线不得当成“尚未反穿”。缺口后才出现的反穿不得确认为缺口前趋势的结束点。主统计只使用完整窗口（连续路径上观察到反穿，或连续 30 根且均线有限、未反穿）。中断前已观察长度只进诊断字段，不得当作完整持续时长求均值。

事件组与同侧非穿越对照组使用相同规则。

## 互斥主因（事先冻结，不得按盘点结果改序）

多标签可同时为真。互斥主因按下列优先级取第一个命中，保证候选数可对账：

1. `entry_bar_missing`
2. `indicator_warmup_insufficient`
3. `internal_gap`
4. `path_1h_missing`（4h 所需窗口完整，但依赖的 1h 路径不完整）
5. `right_censor_cutoff`
6. `indicator_undefined`
7. `funding_missing`
8. `complete`

`path_1h_missing` 只用于依赖 1h 的指标。4h 指标若网格有洞，主因是 `internal_gap` 或 `right_censor_cutoff`。

## 汇总分母

各指标分母只含该指标有效样本。`first_hit_label != favorable_first` 不能把不完整样本算成失败。比较双方使用对应有效样本及原分层权重。必须同时保留候选总数、有效数、中断/排除数。

本轮不改 PASS 门槛，不修 P0R-DATA 已记录的“正年度不可达”和 “`p_value` 被覆盖”。不运行完整收益研究、bootstrap 或晋升。

## 本轮允许的运行

- 合成回归测试（不依赖本地行情）。
- 只读真实连续窗口与真实缺口窗口验证。
- 冻结配置下的缺口影响盘点：只统计候选事件、连续性和窗口可用性。

若全量盘点未完成，验收报告必须写“未完成”，不得用抽样冒充全市场。
