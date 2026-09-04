# BIN-1D-MA7-CTP P7A 安慰剂基础成功率与屏障几何归因审计合同

- Family：`Binance-1D-MA7-Cross-Trend-Probability`（`BIN-1D-MA7-CTP`）
- Experiment：`P7A Placebo Base-Rate and Barrier Geometry Audit`
- 中文名：`安慰剂基础成功率与屏障几何归因审计`
- 日期：`2026-09-04`
- `research_id`：`BIN-1D-MA7-CTP-P7A-2026-09-04`
- `schema_version`：`p7a.v1`
- 主状态：`explore / diagnostic-only / placebo-audit / not promoted / not live-ready`
- 合同锁状态：`FROZEN_BEFORE_P7A_PLACEBO_OUTPUT_READ`
- 与 P7 关系：独立 sidecar diagnostic；不读取、不依赖、不修改任何 `binance_1d_ma7_ctp_p7_*` 产物。

本轮目的是解释已经观察到的约 30% first-hit 正样本率，不是假装进行新的 blind OOS，不训练模型，不寻找新因子，不优化参数，不形成交易规则。

## 1. 唯一研究问题

截至 P6，正式研究观察到 MA7 Cross 在 `+2 ATR14 / -1 ATR14 / 20D first-hit` 标签下裸成功率约为 30%～32%。

必须拆开三个信息来源，回答：

1. **Barrier Base Rate**：完全不利用 MA7 方向时，该标签天然产生多高的 success rate？
2. **Cross Timing / Movement Effect**：发生 Cross 的 `asset × date` 是否本身更容易出现足够大的未来单边运动？
3. **MA7 Directional Edge**：Cross 发生后，MA7 指出的方向是否比随机 Long/Short 更容易先碰 `+2 ATR`？

禁止把 `label positive rate` 直接称为 `trend probability`，除非第 3 层被证据支持。

## 2. 理论 sanity check（不得替代实证）

对连续、零漂移、对称 Brownian motion，从 0 出发先碰 `+a` 而非 `-b` 的概率为 `b/(a+b)`。因此 `a=2, b=1` 时 `P=1/3≈33.333%`。

这只是几何直觉。真实 crypto 存在 drift、跳跃、波动聚集、趋势/均值回复、ATR 缩放、20D timeout、小时 OHLC 离散、同小时双触、funding 与资产/日期依赖。最终结论必须来自 Binance 历史路径上的 empirical placebo，不得把 33.33% 当作真实 benchmark。

## 3. 冻结输入（仅 P0–P6 / CATL P0R / canonical 原始数据）

允许读取：

1. CATL P0R donor directional modeling panel：`../1d-cross-asset-trend-lifecycle/artifacts/p0r_donor_directional_modeling_panel/**/*.parquet`
2. CATL P0R feature blocks / summary / manifest
3. CATL P0 脚本中的 first-hit 实现（`result_from_hours`、`hit_net_return`、funding 累计）
4. CATL P0 冻结小时路径：`../1d-cross-asset-trend-lifecycle/artifacts/_catl_p0_hourly_from_15m.parquet`（仅用于敏感性与 label parity；查询时 `symbol <> HYPE/USDT:USDT`，资产允许清单来自 P0R，永不把 HYPE 列入）
5. CATL P0 规范化 funding：`data/normalized/funding_rates/exchange=binance/market_type=perp`（SQL 排除 HYPE 符号）
6. 本家族 P1–P6 冻结预测 / data audit / summary / manifest，仅用于 REAL MA7 事件 identity、entry、ATR、label parity
7. P0 / P0R / P1–P6 合同与已冻结诊断报告

禁止：

- 任何 `binance_1d_ma7_ctp_p7_*` artifact、report、summary、prediction、config 或中间结果
- 根据 P7 结论设计 P7A
- 读取 `asset_slug_partition=hype_usdt_usdt`
- 网络下载
- 修改 P0–P7 冻结产物、family README、core ledger、decision log、`research/README.md`、`research/asset-portfolios/README.md`、artifacts README

## 4. Canonical 标签（不得另造近似 label）

完全继承 P0R / P1–P6：

```text
feature_known_at = event_day + 1 UTC day
entry_ts = feature_known_at
entry_ref = entry_ts 对应完整 1h K 线 open
atr_anchor = event day ATR14
horizon = 480 × 1h = 20 days
TP = +2.0 ATR    SL = -1.0 ATR
same-hour double touch -> adverse-first -> success = 0
timeout -> success = 0
leverage = 1.0
fee = 0.001 / fill
slippage = 0.0004 / fill
round-trip cost = 0.0028
funding = 真实路径累计；net = price_ret - side_sign * funding_sum - 0.0028
```

主结果的 success / net / first-hit 分类直接使用 P0R 已冻结 `label_entry_success_20d`、`label_entry_result`、`label_entry_net_return`，不重新发明 20D 主标签。

敏感性网格必须调用 CATL P0 同一套 `result_from_hours` / `hit_net_return`，在相同 entry/ATR/未来路径上改 TP/SL/horizon。不得把 1h first-hit 改成 daily close。

## 5. REAL_MA7_CROSS 事件身份

冻结历史 event identity 优先。正式样本：

```text
probe_raw_ma7_cross_dir = true
AND model_eligible_entry_p0r = true
AND asset <> HYPE/USDT:USDT
```

每个 `asset × ts` 最多一行真实方向。主统计排除 known TradFi（与 P5/P6 相同名单）。`HYPER/USDT:USDT` 必须保留。

2025+ 主加密 parity 锚点（以 P5 冻结 artifact 为准）：

```text
2025+ = 46,892
2025   = 32,111
2026   = 14,781
HYPE   = 0
HYPER  存在
```

若事件 identity、entry_ref、ATR14 或 canonical 20D label 无法对齐：全局 `DATA_OR_REPRODUCTION_FAILURE`，停止机制解释。

## 6. Dual-side counterfactual（只用于 outcome audit）

对每个 placebo-eligible `asset × event_date`，在完全相同的 date / asset / ATR14 / entry_ref / future path 下计算：

```text
hypothetical_long_success, hypothetical_long_net_return
hypothetical_short_success, hypothetical_short_net_return
```

这些字段禁止进入任何模型。主 placebo 使用精确随机期望，不靠扔硬币：

```text
expected_random_side_success = 0.5 * long_success + 0.5 * short_success
expected_random_side_net_return = 0.5 * long_net + 0.5 * short_net
```

Eligible asset-day：P0R 上 long 与 short 均 `model_eligible_entry_p0r` 且 `future_path_complete_20d`。

## 7. Placebo 组（预注册）

| 组 | 名称 | 定义 |
| --- | --- | --- |
| A | `REAL_MA7_CROSS` | 冻结真实 Cross 方向 |
| B | `SAME_CROSS_ASSET_DATE_RANDOM_SIDE_EXPECTATION` | 同一 Cross asset-date，50/50 精确期望 |
| C | `DATE_MATCHED_ELIGIBLE_RANDOM_SIDE_EXPECTATION` | 同日全部 eligible asset-day 的 50/50 均值，按 `n_real_cross[d]` 加权 |
| D | `DATE_MATCHED_NON_CROSS_RANDOM_SIDE_EXPECTATION` | 同日 non-cross eligible，50/50，按 `n_real_cross[d]` 加权 |
| E | `DATE_MATCHED_NON_CROSS_1D_MOMENTUM` | non-cross；`ret_1d>0 -> LONG`，`<0 -> SHORT`，`==0` 排除；日期加权同上 |
| F | `DATE_MATCHED_NON_CROSS_MA7_SIDE` | non-cross；`close>SMA7 -> LONG`，`< -> SHORT`，`==` 排除；仅用事件日 close/SMA7 |

主分解：

```text
BARRIER_DATE_BASE = Group D
CROSS_MOVEMENT_EFFECT = Group B - Group D
MA7_DIRECTIONAL_EDGE = Group A - Group B
TOTAL_OBSERVED_SUCCESS = Group A
```

日期加权禁止改成全局 asset-day 平均。

## 8. 分层与敏感性

必须按 LONG/SHORT 与时期输出：full canonical history、pre-2025、2022、2023、2024、2025、2026、2025+。小样本年份仍报告 count 并标记不确定性。重点看 edge 与 movement 是否跨年同号。

主实验固定 `TP=+2 / SL=-1 / 20D`。额外预注册、不改主结果：

屏障网格（同一 asset-day / entry / ATR / path）：

```text
(+1.0,-1.0), (+1.5,-1.0), (+2.0,-1.0), (+2.5,-1.0), (+3.0,-1.0)
(+2.0,-0.5), (+2.0,-1.5), (+2.0,-2.0)
```

Timeout 网格（固定 +2/-1）：`5D, 10D, 20D, 40D`。40D 仅统计未来路径完整的子集，并报告有效 N。

## 9. Monte Carlo 验证（不是主推断）

对 `SAME_CROSS_ASSET_DATE_RANDOM_SIDE` 与 `DATE_MATCHED_NON_CROSS_RANDOM_SIDE`：

```text
N = 500
seeds = 2026090400 ... 2026090899
```

每轮真正随机 side / 随机抽取当日 non-cross eligible asset（不放回；若 `n_cross[d] > pool` 则有放回，并计入审计）。MC mean 应收敛到 exact expectation。预注册容差：success rate 绝对差 `<= 0.002`（0.20 pp）。超差视为实现错误，停止解释。

## 10. 统计推断

主检验（28 日 UTC 日历块 bootstrap，`n=2000`，`seed=20260901`）：

1. MA7 Directional Edge = A − B
2. Cross Movement Effect = B − D
3. Total MA7 vs Non-Cross Random = A − D

一个 block 内所有日期、资产、方向共同保留；三次比较共用同一 replicate；每次用日期充分统计量完整重建 metric；不得把事件当 iid，不得先对月份均值再 bootstrap 月份。

报告 point、bootstrap mean、p2.5、p97.5、effective replicates、non-finite replicates。三次主检验使用 Bonferroni `α=0.05/3` 与 BH-FDR；裁决以 95% 百分位 CI 是否覆盖 0 为主。

经济意义预注册：`|edge| >= 2.0 pp` 且 CI 不含 0 才可考虑 `MA7_DIRECTIONAL_EDGE_SUPPORTED` 的强度门槛；更小的显著差最多进入 `MA7_DIRECTIONAL_EDGE_WEAK`。

## 11. 收益口径

各组报告 success、favorable/adverse/ambiguous/timeout 比例、gross mean、funding mean、cost、net mean/median、positive net ratio。P7A 是 label/base-rate audit，不是账户回测。禁止 Sharpe、CAGR、portfolio equity、MDD、杠杆优化。

## 12. Verdict 集合（只能选一个）

1. `DATA_OR_REPRODUCTION_FAILURE`
2. `PLACEBO_EXPLAINS_BASE_RATE`
3. `CROSS_MOVEMENT_EFFECT_WITHOUT_DIRECTIONAL_EDGE`
4. `MA7_DIRECTIONAL_EDGE_WEAK`
5. `MA7_DIRECTIONAL_EDGE_SUPPORTED`

即使第 5 项，也只能写 “MA7 Cross direction contains detectable information”，禁止 profitable / live-ready / deployable / high-probability trend system。

停止规则：parity 失败立即停止解释；MC 超差立即停止解释；不得根据结果改 ATR/TP/SL/horizon、挑年、挑币、挑 regime、开 P8、改写 P6 verdict、修改 P7 文件。

## 13. HYPE

`HYPE/USDT:USDT` 不进入真实事件、placebo universe、日期均值、random side、barrier/timeout、任何统计或图表。原始分区不得先读后滤。`HYPER/USDT:USDT` 必须保留。本轮不做 HYPE reveal。

## 14. 共享文档

本轮不修改 family README、core ledger、decision log、顶层 research README、asset-portfolios README、artifacts README。登记步骤写入独立 deferred-registration 文件，待 P7 窗口结束后再合并。
