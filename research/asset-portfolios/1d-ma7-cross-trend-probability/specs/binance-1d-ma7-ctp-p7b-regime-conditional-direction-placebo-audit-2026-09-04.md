# BIN-1D-MA7-CTP P7B 市场状态条件下 MA7 穿越方向安慰剂审计合同

- Family：`Binance-1D-MA7-Cross-Trend-Probability`（`BIN-1D-MA7-CTP`）
- Experiment：`P7B Regime-Conditional Cross Direction Placebo Audit`
- 中文名：`市场状态条件下 MA7 穿越方向安慰剂审计`
- 日期：`2026-09-04`
- `research_id`：`BIN-1D-MA7-CTP-P7B-2026-09-04`
- `schema_version`：`p7b.v1`
- 主状态：`explore / diagnostic-only / placebo-audit / not promoted / not live-ready`
- 合同锁状态：`FROZEN_BEFORE_P7B_REGIME_OUTCOME_READ`
- 与 P7 / P7A 关系：P7A 之后的独立 sidecar diagnostic；不训练机器学习模型，不使用 B0，不依赖 P7 的模型重建结果。P7 的 `DATA_OR_REPRODUCTION_FAILURE` 不阻止本研究。

本研究是在已经观察过总体 P7A 安慰剂分解及部分 P6 六格历史后进行的 targeted diagnostic，不具有新盲测属性。2025+ 一律标记 `ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS`。

## 1. 唯一研究问题

P7A 已确认总体上：

```text
REAL MA7 success ≈ 31.9700%
Same-cross random-side ≈ 31.0272%
Date-matched non-cross random-side ≈ 29.9074%
MA7 directional edge ≈ +0.9428 pp
```

该 directional edge 的 95% block-bootstrap CI 覆盖 0，因此总体上不能确认 MA7 Cross direction 具有稳定预测价值。

P7B 只回答：这个接近 0 的总体 directional edge，是否被不同市场状态互相抵消？必须把下面两个问题拆开，禁止混谈。

### 问题 A：`REGIME_DIRECTIONAL_DRIFT`

牛市本来做多、熊市本来做空，是否本身就比随机方向更容易成功？这与 MA7 无关。

### 问题 B：`REGIME_CONDITIONAL_MA7_INCREMENT`

在同一 regime、同一 UTC 日、同一未来路径上，MA7 Cross 方向是否提供超越该 regime 普通 non-cross 同侧漂移的额外信息？

主结论指标只能是问题 B。

禁止把 “牛市 Up Cross 成功率看起来更高” 直接写成 “MA7 在牛市有效”。

## 2. 允许与禁止的输入

允许读取：

1. CATL P0R donor directional modeling panel（SQL `asset <> HYPE/USDT:USDT`）。
2. CATL P0R feature blocks / summary / manifest。
3. 本家族 P1–P6 冻结 identity / data audit / summary / manifest，仅用于 REAL MA7 事件身份、entry、ATR、label 与 P6 regime parity。
4. P7A 冻结 dual-side outcome、real-event parity、candidate universe audit、summary / manifest / 合同；用于复用或确定性恢复 `hypothetical_long_*` / `hypothetical_short_*`。
5. P6 冻结预测中的 `market_state` / `six_grid` / `raw_market_breadth_ma30` / `raw_btc_price_side_ma30`，仅作 regime parity；禁止把 B0/M0/M1 分数当研究输入。
6. P0 / P0R / P1–P6 / P7A 合同与已冻结诊断报告。

禁止：

- 任何 `binance_1d_ma7_ctp_p7_*` artifact（P7A 除外）、P7 B0 reconstruction、feature decomposition 或 fail-closed placeholder。
- 训练任何 ML、使用 B0 score、调 MA7、搜 regime / breadth threshold、搜最好年份或币种。
- 读取 `asset_slug_partition=hype_usdt_usdt`。
- 网络下载。
- 修改 P0–P7A 冻结产物、family README、core ledger、decision log、`research/README.md`、`research/asset-portfolios/README.md`、artifacts README。
- 创建交易策略、账户权益、Sharpe、CAGR、MDD、杠杆优化或 live spec。

## 3. Canonical 事件与标签（不得另造）

完全继承 P7A / P0R / P1–P6：

```text
feature_known_at = event_day + 1 UTC day
entry_ts = feature_known_at
entry_ref = entry_ts 对应完整 1h K 线 open
atr_anchor = event-day ATR14
horizon = 20D
TP = +2.0 ATR    SL = -1.0 ATR
same-hour double touch -> adverse-first -> success = 0
timeout -> success = 0
leverage = 1.0
fee = 0.001 / fill
slippage = 0.0004 / fill
round-trip cost = 0.0028
```

REAL MA7 Cross 必须使用 P7A 已验证的 canonical event identity：

```text
probe_raw_ma7_cross_dir = true
AND model_eligible_entry_p0r = true
AND asset <> HYPE/USDT:USDT
AND official_real（pre-2025 全部合格 Cross；2025+ 与 P5 主加密 validation 对齐）
```

2025+ 主加密 parity 锚点：

```text
2025+ = 46,892
2025   = 32,111
2026   = 14,781
HYPE   = 0
HYPER  存在
canonical_event_id_hash        = fe219526ac66de871cecae9907df01e0e1bfb90ca7ec5db899a542bb50794a6c
canonical_event_id_hash_2025+  = f9743f3a1ed7c0afc0c54c0899b8496439ae785315cf44a6b0209acb856a1a84
```

P7A dual-side outcome 文件哈希（复用前必须核验）：

```text
artifacts/binance_1d_ma7_ctp_p7a_dual_side_outcomes.parquet
sha256 = d0bed3c2e16bced53ef25358d3bef83a05c051aa6bfaf4b40260f58c89c298c8
```

对任意 eligible asset-date：

```text
random_side_success = 0.5 * long_success + 0.5 * short_success
random_side_net     = 0.5 * long_net     + 0.5 * short_net
```

主结果必须复用或确定性恢复 P7A 的 `hypothetical_long_success` / `hypothetical_short_success` 及对应 net。若 identity 或 counterfactual 对不上：全局 `DATA_OR_REPRODUCTION_FAILURE`。

## 4. 主 Market Regime（冻结，禁止事后重定义）

继承 P6 已冻结定义。主分析不得创造新 regime，不得搜索 threshold。

```text
raw_breadth = 当日合格 donor 中 close > SMA30 的比例
btc_side    = +1 if BTC close > BTC SMA30
              -1 if BTC close < BTC SMA30
```

P0R 市场字段是方向对齐字段，必须还原：

```text
raw_breadth = dir_market_breadth_ma30_p0r      if side == long
raw_breadth = 1 - dir_market_breadth_ma30_p0r  if side == short
btc_side    = dir_btc_price_side_ma30          if side == long
btc_side    = -dir_btc_price_side_ma30         if side == short
```

然后：

```text
BULL    = raw_breadth >= 0.60 AND btc_side > 0
BEAR    = raw_breadth <= 0.40 AND btc_side < 0
MIXED   = 其余已知状态
UNKNOWN = 必要状态缺失
```

所有 regime 变量必须在 event-day 完整 UTC 收盘时已经知道：`feature_known_at == entry_ts == ts + 1 day`。不得使用未来数据定义 regime。

优先从 canonical donor panel 确定性重算，再与 P6 frozen `market_state` / `six_grid` 做 parity。同一 UTC 日 long/short 还原必须一致。若 regime parity 无法通过：`DATA_OR_REPRODUCTION_FAILURE`。

`UNKNOWN` 单独审计，不并入 `MIXED`，不进入六格主统计。

## 5. 六个固定主格子

不得事后创造新格子。即使主假设只关注 BULL_UP / BEAR_DOWN，六格必须全部展示。

```text
BULL_UP     BULL_DOWN
BEAR_UP     BEAR_DOWN
MIXED_UP    MIXED_DOWN
```

- `UP` = MA7 upward Cross，REAL side = LONG
- `DOWN` = MA7 downward Cross，REAL side = SHORT

## 6. 第一层：Same-Cross Directional Edge

对每个格子，保持完全相同的 asset / date / regime / ATR / entry / future path，只比较真实 Cross direction 与 random direction。

```text
CROSS_DIRECTIONAL_EDGE
= REAL_CROSS_SIDE_SUCCESS - SAME_CROSS_RANDOM_SIDE_SUCCESS
```

同时报告 REAL_SIDE vs OPPOSITE_SIDE_COUNTERFACTUAL。数学关系：

```text
REAL - RANDOM_SIDE = 0.5 * (REAL - OPPOSITE)
```

opposite-side 只作直观辅助，不是独立检验。

## 7. 第二层：Regime 本身的方向优势

对每一个 Cross cell，在完全相同 UTC date 上寻找 eligible non-cross asset-day。必须按 Cross 日期加权，禁止 “全部 Bull Cross vs 全部 Bull Non-Cross” 的全局混比。

例如 BULL_UP：

```text
n_bull_up_cross[d] = 日期 d 上 BULL_UP Cross 数量
baseline = SUM(n_bull_up_cross[d] * bull_noncross_metric[d]) / SUM(n_bull_up_cross[d])
```

```text
REGIME_LONG_DRIFT  = NONCROSS_LONG_SUCCESS  - NONCROSS_RANDOM_SIDE_SUCCESS
REGIME_SHORT_DRIFT = NONCROSS_SHORT_SUCCESS - NONCROSS_RANDOM_SIDE_SUCCESS
```

这回答：牛市本来做多、熊市本来做空，是不是本身就有优势。不能把这部分算到 MA7 头上。

若某日 Cross>0 但 non-cross 池为空，该日不进入 incremental 分母，并计入 coverage 审计。若主格子因此无法可靠构建 date-matched baseline：`DATA_OR_REPRODUCTION_FAILURE`。

## 8. 主指标：`REGIME_CONDITIONAL_MA7_INCREMENT`

```text
BULL_UP_INCREMENTAL_EDGE
=
(BULL_UP_REAL_LONG - BULL_UP_RANDOM_SIDE)
-
(BULL_NONCROSS_LONG - BULL_NONCROSS_RANDOM_SIDE)
```

```text
BEAR_DOWN_INCREMENTAL_EDGE
=
(BEAR_DOWN_REAL_SHORT - BEAR_DOWN_RANDOM_SIDE)
-
(BEAR_NONCROSS_SHORT - BEAR_NONCROSS_RANDOM_SIDE)
```

若 Cross directional edge 等于 Regime directional drift，则 incremental = 0，正确结论是：这是该 regime 本身的方向优势，不是 MA7 Cross 的增量信息。

## 9. Primary Hypotheses（读 outcome 前预注册）

### H1 Bull continuation

```text
BULL_UP_INCREMENTAL_EDGE > 0
```

### H2 Bear continuation

```text
BEAR_DOWN_INCREMENTAL_EDGE > 0
```

### H3 Regime Alignment Effect

```text
ALIGNED         = BULL_UP + BEAR_DOWN
COUNTER_REGIME  = BULL_DOWN + BEAR_UP
REGIME_ALIGNMENT_EFFECT
= aligned_incremental_edge - counter_incremental_edge
```

aligned / counter 使用事件加权。研究假设：`REGIME_ALIGNMENT_EFFECT > 0`。

反趋势格子 `BULL_DOWN` / `BEAR_UP` 必须完整展示，不得隐藏。

## 10. 年份、样本不均衡与稳健性

至少输出：`pre-2022`、`2022`、`2023`、`2024`、`2025`、`2026`、`2025+`。每个时期报告 BULL_UP incremental、BEAR_DOWN incremental、alignment effect。2025+ 必须标记 `ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS`，不能称为新 OOS。一个所谓 regime conditional edge，不能只由单一年份贡献。

每个 regime / 格子报告：event count、unique dates、unique assets、month count、28D block count。BEAR_DOWN 若样本量显著少于 BULL_UP，必须报告 power / CI 宽度。

### Volatility / Liquidity matched robustness（次于主 Date-Matched）

主分析仍然是纯 Date-Matched。额外固定稳健性：

```text
vol_metric = atr_to_entry_p0r          # event 时点已知
liq_metric = liquidity_rank_pct_p0r    # event 时点已知
同日 eligible asset-day 截面 percentile
冻结 tertile 边界：0 / 1/3 / 2/3 / 1
```

在同日期 non-cross 中进一步匹配 vol tertile × liq tertile，得到 `DATE_REGIME_VOL_LIQ_MATCHED_NONCROSS`，再计算 BULL_UP incremental、BEAR_DOWN incremental、alignment。不得按结果重调边界。

### Secondary regime strength（不得代替主分析）

```text
Strong Bull = raw_breadth >= 0.70 AND BTC > SMA30
Strong Bear = raw_breadth <= 0.30 AND BTC < SMA30
```

只允许回答更极端 regime 下 effect 是否增强。标记 `SECONDARY_REGIME_STRENGTH_SENSITIVITY`。禁止搜索 0.65 / 0.75 / 0.80。

### 连续 Breadth 诊断

冻结 bins：`0–20%`、`20–40%`、`40–60%`、`60–80%`、`80–100%`。分别计算 UP Cross 与 DOWN Cross 的 directional edge。只作为形状诊断，不得根据结果创建新 threshold。

## 11. 统计推断

28-day UTC 日历块 bootstrap：`n=2000`，`seed=20260901`。日期块内所有币共同保留；Cross / Non-Cross paired；一个 replicate 中所有比较共享相同 block draw；每个 replicate 完整重算；不把同日币种当 iid。

主统计 family：

1. `BULL_UP_INCREMENTAL_EDGE`
2. `BEAR_DOWN_INCREMENTAL_EDGE`
3. `REGIME_ALIGNMENT_EFFECT`

执行 raw p-value、Benjamini-Hochberg q-value、95% CI。

六格 individual incremental edge 作为完整 secondary family，也执行 BH。

## 12. 经济结果

成功率是主标签。同时报告 net return mean / median、positive net return rate、favorable-first、adverse-first、timeout、funding mean。差值同样做 Cross real vs Cross random vs Non-cross same side。必须注明：event net return 不是账户级 portfolio return。

## 13. Concentration / Leave-One-Out

对 `BULL_UP`、`BEAR_DOWN`、`ALIGNED` 检查按月、28D block、asset、calendar date 贡献。至少：

```text
leave-one-month-out
leave-one-28D-block-out
leave-one-asset-out
exclude BTC/ETH
```

防止某个牛市月份制造全部 edge。

## 14. Verdict 集合（只能选一个）

1. `DATA_OR_REPRODUCTION_FAILURE`
2. `NO_REGIME_CONDITIONAL_DIRECTIONAL_EDGE`
3. `REGIME_DRIFT_EXPLAINS_APPARENT_EDGE`
4. `BULL_ONLY_CONDITIONAL_EDGE`
5. `BEAR_ONLY_CONDITIONAL_EDGE`
6. `REGIME_ALIGNED_DIRECTIONAL_EDGE_SUPPORTED`
7. `REGIME_EFFECT_TEMPORALLY_UNSTABLE`

`REGIME_ALIGNED_DIRECTIONAL_EDGE_SUPPORTED` 只有同时满足以下全部条件才能使用：

1. BULL_UP incremental edge > 0；
2. BEAR_DOWN incremental edge > 0；
3. REGIME_ALIGNMENT_EFFECT > 0；
4. 主 bootstrap CI 支持；
5. BH 后仍支持；
6. 多数年份同号；
7. vol/liquidity matched 后没有消失；
8. 不是单个月或单个 28D block 驱动。

即使该项成立，也只能写 “MA7 directional information is conditional on market regime”。禁止写 profitable / live-ready / deployable / production strategy。

停止规则：parity 失败立即停止机制解释；不得根据结果改 Bull/Bear 定义、创造新格子、开交易策略、改写 P6 或 P7A verdict、修改 P7 文件。

## 15. HYPE

`HYPE/USDT:USDT` 不读取原始分区，不进入 event / regime donor / placebo / 统计 / 图表。`HYPER/USDT:USDT` 必须保留。自动断言：`HYPE rows == 0` 且 `HYPER rows > 0`。本轮不做 HYPE reveal。

## 16. 共享文档

本轮不修改 family README、core ledger、decision log、顶层 research README、asset-portfolios README、artifacts README。登记步骤写入独立 deferred-registration 文件。
