# BIN-1D-MA7-CER P0 无方向价格扩张事件审计合同

- Family：`Binance-1D-MA7-Cross-Expansion-Regime`（`BIN-1D-MA7-CER`）
- Experiment：`P0 Direction-Agnostic Expansion Event Audit`
- 中文名：`MA7 穿越后的无方向价格扩张事件审计`
- 日期：`2026-09-04`
- `research_id`：`BIN-1D-MA7-CER-P0-2026-09-04`
- `schema_version`：`cer.p0.v1`
- 主状态：`explore / diagnostic-only / not promoted / not live-ready`
- 合同锁状态：`FROZEN_BEFORE_P0_EXPANSION_OUTPUT_READ`
- 与旧家族关系：独立新家族。不是 `BIN-1D-MA7-CTP` 的 P8。不得继承“MA7 穿越方向具有预测意义”的假设。旧家族只作历史背景与数据工程参考。

本轮在看任何 Cross vs placebo 数字之前冻结。不得根据结果改 horizon、改 matching、改 ATR、加权合成 Expansion Score、训练模型或创建交易策略。

## 1. 唯一研究问题

只回答：

> 发生 MA7 Cross 后，未来价格是否比同日期普通 non-cross asset-day 更容易进入显著的 expansion / directional movement 状态？

完全不预测 LONG / SHORT。不得把 `上穿 = long`、`下穿 = short` 当作成功条件。Cross direction 只作描述性元数据。主 outcome 必须 `direction-agnostic`。

## 2. 本阶段禁止

- 机器学习（LightGBM / Logistic Regression / XGBoost / 任何 sklearn 模型）
- 增加因子、调 MA 参数、优化 threshold
- 创建交易策略、账户权益、Sharpe、CAGR、MDD
- 把多个 outcome 加权成综合 Expansion Score
- 根据结果挑选最好 horizon 当主结论
- 读取 `HYPE/USDT:USDT` 原始分区
- 修改旧 `BIN-1D-MA7-CTP` 产物或 verdict

## 3. 冻结输入

允许：

1. CATL P0R donor panel：`../1d-cross-asset-trend-lifecycle/artifacts/p0r_donor_directional_modeling_panel/**/*.parquet`（SQL `asset <> HYPE/USDT:USDT`）
2. CATL P0 asset-day feature panel：仅读取 P0R 允许清单中的 `asset_slug_partition`，永不读取 `hype_usdt_usdt`
3. CATL P0R summary / manifest / feature blocks
4. 旧家族 P5 冻结预测，仅用于 canonical Cross event identity 对账
5. P6 已冻结 BULL/BEAR/MIXED 规则（breadth 0.60/0.40 + BTC MA30 侧），只作描述性稳健性

禁止：

- 任何 `binance_1d_ma7_ctp_p7_*` 产物作为输入（P7A 只作背景阅读，本轮不读取其 parquet）
- 网络下载
- 把 P0R 的 `label_entry_success_20d` / directional MFE/MAE 当作主 outcome

## 4. Cross event identity

复用 P7A / P5 已验证口径：

```text
probe_raw_ma7_cross_dir = true
AND model_eligible_entry_p0r = true
AND asset <> HYPE/USDT:USDT
AND not known TradFi
AND future_path_complete_20d = true   # 进入官方样本的资格；各 horizon 另要求该 horizon 完整
```

2025+ 必须与 P5 冻结主加密验证集对齐：

```text
2025+ = 46,892
2025   = 32,111
2026   = 14,781
HYPE   = 0
HYPER  存在
```

`official_real`：`ts < 2025-01-01` 的合格 Cross，或 `ts >= 2025-01-01` 且落在 P5 2025+ 验证 identity 中。

若 identity / `entry_ref` / `atr_anchor` 无法对齐：全局 `DATA_OR_REPRODUCTION_FAILURE`。

Cross direction（up = long probe，down = short probe）只保存为元数据，不得进入成功定义。

Known TradFi base symbols 与 P5/P6/P7A 相同。

## 5. 时序与 ATR 锚点

```text
T0            = 完整 UTC 日，收盘发生严格 SMA7 Cross
feature_known_at = T0 + 1 UTC day
entry_ts      = 下一 UTC 日 00:00
entry_ref     = 该小时/日开盘价（冻结 P0R entry_ref）
atr_anchor    = T0 日 ATR14（冻结 P0R atr_anchor）
```

未来窗口只使用 T0 之后的完整 UTC 日：

```text
horizon H 的未来日 = T+1, T+2, ..., T+H
要求 ts[T+H] - ts[T0] == H calendar days
```

ATR 归一化只用事件时点 `atr_anchor`，不得用未来 ATR。

## 6. Outcome 定义（全部为 label / diagnostic，禁止当特征）

主 horizon：`5D`。次要：`1D, 3D, 10D, 20D`。不得改主 horizon。

### 6.1 Maximum absolute excursion

```text
MFE_up   = (max_future_high - entry_ref) / atr_anchor
MFE_down = (entry_ref - min_future_low) / atr_anchor
max_abs_excursion = max(MFE_up, MFE_down)
```

报告 mean / median / p75 / p90 / p95 / p99。主对比指标：`Δ median` 与 `Δ mean`。BH 主检验使用 `Δ mean`。

### 6.2 Future range expansion

```text
future_range = (max_future_high - min_future_low) / atr_anchor
```

### 6.3 Realized volatility expansion（仅 3/5/10/20D）

日对数收益：`r_t = log(close[t] / close[t-1])`，完整日序列。

```text
future_rv_H = sqrt(sum_{k=1..H} r_{T+k}^2)
pre_rv_H    = sqrt(sum_{k=0..H-1} r_{T-k}^2)   # 结束于 T0 收盘，事件前已知
vol_expansion_ratio = future_rv_H / pre_rv_H
```

`pre_rv_H <= 0` 或非有限 → NaN。1D 不做 realized vol。不用未来参数年化。

### 6.4 Path efficiency（仅 3/5/10/20D）

```text
path_efficiency =
  abs(close[T+H] - entry_ref)
  /
  ( abs(close[T+1] - entry_ref) + sum_{k=2..H} abs(close[T+k] - close[T+k-1]) )
```

分母 ≤ 0 → NaN。范围近似 0–1。

### 6.5 Directional excursion dominance

```text
a = max(MFE_up, MFE_down)
b = min(MFE_up, MFE_down)
dominance = a / (a + b)    if (a + b) > 1e-12 else NaN
```

范围 0.5–1。不要求预知方向。

### 6.6 Absolute terminal move

```text
abs_terminal = abs(close[T+H] - entry_ref) / atr_anchor
```

与 max excursion 分开报告。

## 7. Pre vs post 与 lagging 检验

主窗口 5D：

```text
pre_event_range_5d  = (max high - min low) over {T-4,...,T0} / atr_anchor
post_event_range_5d = future_range_5d
pre_event_vol_5d    = pre_rv_5
post_event_vol_5d   = future_rv_5
post_pre_range_ratio = post / pre
post_pre_vol_ratio   = post / pre
```

Lagging 对照：

```text
pre_tminus3_to_t0_range = range over {T-3,T-2,T-1,T0} / atr_anchor
t0_day_range            = (high[T0] - low[T0]) / atr_anchor
post_tplus1_to_tplus5   = future_range_5d
```

若 T-3→T0 相对 placebo 显著扩张，而 T+1→T+5 无增量，裁决倾向 `CROSS_IS_LAGGING_EXPANSION_MARKER`。

## 8. Placebo

日期权重必须等于真实 Cross 的 `n_cross[d]`。禁止全历史无日期匹配的 Cross vs Non-Cross 作为主结论。

| 组 | 名称 | 角色 |
| --- | --- | --- |
| A | `DATE_MATCHED_NON_CROSS` | 主 baseline：同日合格 non-cross 均值，按 `n_cross[d]` 加权 |
| B | `SAME_ASSET_RANDOM_NON_CROSS_DATE` | 同资产其他合格 non-cross 日的精确期望（资产均值） |
| C | `DATE_AND_VOL_MATCHED_NON_CROSS` | 同日且 `volatility_state_p0r` 相同 |
| D | `DATE_LIQUIDITY_VOL_MATCHED_NON_CROSS` | 同日且 vol bucket + liquidity tertile 相同；稳健性 |

`volatility_state_p0r` 已是 prior-only 因果分位，不得用未来波动匹配。Liquidity tertile：`liquidity_rank_pct_p0r` 以冻结切点 `1/3, 2/3` 分成 low/mid/high。

Placebo 样本不得含 Cross。B 组优先 exact expectation；另做 Monte Carlo `n=500`、`seeds=2026090400..2026090899` 作实现校验，容差相对 exact 的均值绝对差 `<= 0.02` ATR（excursion）或相对 `<= 0.01`（ratio/efficiency）。超差视为实现错误。

## 9. Event-time study

偏移 `k = -20,...,-1,0,+1,...,+20`。T0 为 Cross 日。每日本分母一律用事件 `atr_anchor`：

1. ATR-normalized daily range `(high-low)/atr_anchor`
2. 日 realized vol 代理 `|log ret|`
3. 绝对收益 `|close/prev_close - 1|`
4. `quote_volume`（不未来归一化）
5. 截至当日的路径效率（仅 k>0；k≤0 用回溯窗口）

曲线：Cross vs date-matched non-cross。不得用未来归一化参数。

## 10. 分层

- 年份：pre-2022、2022、2023、2024、2025、2026。主要求多数年份同号。
- 方向：up-cross / down-cross 只比较无方向 expansion 是否不同，禁止解释成方向预测。
- 市场状态：P6 冻结 BULL/BEAR/MIXED，只问 effect 是否只存在于单一 regime。不得寻优。

## 11. 统计推断

```text
28-day UTC calendar block bootstrap
n = 2000
seed = 20260901
```

block 内所有资产一起保留；Cross/placebo 配对；不把同日币种当 iid。完整重算指标。

BH 主 family（仅预注册 5D、相对 A）：

1. max absolute excursion（Δ mean）
2. future range（Δ mean）
3. realized vol expansion ratio（Δ mean）
4. path efficiency（Δ mean）
5. absolute terminal move（Δ mean）

其他 horizon 为 secondary sensitivity，不替代主结论。

同时报告 Cross 值、placebo 值、绝对差、相对差、95% CI、标准化效应（日期配对 `mean(Δ_d)/sd(Δ_d)` 与事件层 pooled Cohen d，并注明非 iid）。

经济意义冻结：`|Δ median max_abs_excursion_5d| >= 0.20 ATR` 且相对差 `>= 10%` 才可称“有实际意义”。更小的稳定差最多进入 `WEAK_EXPANSION_MARKER`。

## 12. Verdict（只能选一个）

1. `DATA_OR_REPRODUCTION_FAILURE`
2. `NO_EXPANSION_EDGE` → 本 family STOP
3. `CROSS_IS_LAGGING_EXPANSION_MARKER` → STOP 或仅保留 descriptive
4. `WEAK_EXPANSION_MARKER`
5. `EXPANSION_EVENT_SUPPORTED`（须同时满足：5D 多个预注册 outcome 同向；增量不只来自 Cross 当日已发生运动；date-matched 后仍在；vol-matched 后仍在；多数年份同号；28D bootstrap 支持；effect size 有实际意义）

即使第 5 项，也不得写 profitable / directional / tradable / live-ready。

## 13. P1 路由

仅 `EXPANSION_EVENT_SUPPORTED`，或非常接近且 effect size 有意义的 `WEAK_EXPANSION_MARKER`，才推荐 P1。P1 仍不得立刻做方向预测。若为 `NO_EXPANSION_EDGE` 或 `CROSS_IS_LAGGING_EXPANSION_MARKER`，明确停止整条 MA7 研究路线。

## 14. HYPE

`HYPE/USDT:USDT` 不读取原始分区，不进 Cross、placebo、统计、图表。`HYPER/USDT:USDT` 必须保留。测试：`HYPE rows == 0` 且 `HYPER rows > 0`。
