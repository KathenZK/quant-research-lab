---
document_type: external_reproduction_spec
intended_audience: 独立量化研究员、审计 AI、可复现性评审者
family: Binance-1D-MA7-Cross-Trend-Probability
alias: BIN-1D-MA7-CTP
scope: P0-P6 研究过程、结果、缺陷、修复与结论边界
as_of: 2026-09-04
status: explore / diagnostic-only / not promoted / not live-ready
---

# BIN-1D-MA7-CTP P0–P6 外部审查与复现规格

## 0. 给审查者的最短结论

这条研究线提出的问题是：Binance 永续合约日线收盘穿越 SMA7 后，裸事件约有 30% 的概率在下一日开盘后的 20 日内先走出顺向 `+2 ATR`，机器学习能否从所有穿越事件里挑出更高概率的事件。

截至 2026-09-04，最能被现有证据支持的结论是：

1. “裸 MA7 穿越的趋势发生率约 30%”得到大样本历史统计支持，但早期 P0 与后续 P1–P6 的标签口径有变化，不能把两者当成逐行相同的实验。
2. 固定的 69 特征逻辑回归 `R_B0_69` 在已观察历史中表现出弱的总体事件排序：严格 pre-2025 前向 OOF AUC 约 `0.5716`，2025+ 复用验证 AUC `0.5589`；2025+ 裸成功率 `31.72%`，年度 Top10 成功率 `35.11%`，提升 `3.39pp`。
3. 这个结果不能证明它已经是可交易策略。没有账户级资本约束、并发持仓、完整成交撮合、组合风险、容量、权益曲线或真正未揭示 OOS；2025+ 已被多轮研究观察，只能叫复用验证。
4. RSI6、完整闭合周线、删除波动组、流动性、MA30、跨市场和 funding 块均没有在预先约定的统计门槛下证明稳定增量。
5. P6 证明的是更窄的命题：在“同一天、同一方向”内，B0 没有证明能挑出更好的币，市场状态交互 M1 反而更弱。P6 不能逻辑上推翻 B0 对“跨日期、跨市场环境的全部事件”进行弱排序的结果。
6. 因此，把整条 MA7 路径判为“完全无效”过强；把它称为“已找到可上线的机器学习策略”也不成立。当前最准确状态是：`存在弱的总体事件筛选线索，但没有同日选币证明、没有新增特征增量、没有新盲测、没有策略级证据`。

对本档案的建议总评词为：`RELIABLE_WITH_MATERIAL_LIMITATIONS`。内部结果在 P5 修复后具有较强可重复性；外部有效性、未来稳定性和可交易性仍未得到证明。

## 1. 审查对象和禁止混淆项

### 1.1 研究对象

| 字段 | 固定值 |
| --- | --- |
| 家族名 | `Binance-1D-MA7-Cross-Trend-Probability` |
| 短名 | `BIN-1D-MA7-CTP` |
| 市场 | Binance USD-M USDT perpetual |
| 信号周期 | 完整 UTC 日线 |
| 事件 | 日收盘由 SMA7 一侧穿到另一侧 |
| 预测时点 | 事件日完整收盘后，即下一 UTC 日 `00:00` |
| 预测目标 | 下一日开盘后 20 日内是否先到顺向 `+2 ATR14`，且未先到逆向 `-1 ATR14` |
| 模型目标 | 穿越事件发生趋势的条件概率排序 |
| 当前参考模型 | `R_B0_69`，pooled direction-aligned L2 Logistic Regression |
| 当前状态 | `explore / diagnostic-only / not promoted / not live-ready` |

### 1.2 不属于本研究的内容

本研究不是所有 asset-day 的一般涨跌预测，不研究没有发生 MA7 穿越的日期，不是持续持仓模型，不是退出或反手机制，不是 HYPE 专属策略，不是账户组合回测，也不是生产 runner。

本研究只回答“穿越已经发生后，哪些事件更可能成功”。如果复现者把非穿越日期加入负样本，目标就从条件概率问题变成了不同的分类问题，应直接判定 `OBJECTIVE_MISALIGNED`。

### 1.3 HYPE 隔离

`HYPE/USDT:USDT` 在建模、市场宽度、训练、校准、阈值、验证和报告统计中必须为 0 行，并且不得先读取后过滤。`HYPER/USDT:USDT` 是另一个资产，必须保留。这个边界用于保留一个独立资产揭示机会；截至 P6 没有自动执行 HYPE reveal。

## 2. 证据等级与最终结论边界

### 2.1 可认为已经成立

- 大样本历史里，MA7 穿越后出现所定义顺向趋势的裸概率大约为三成。
- `R_B0_69` 在 2022–2024 前向 OOF 和 2025+ 复用验证中均有高于随机的弱排序点估计。
- 2025+ 的总体排序显著弱于开发期 Top10 表现，且月度、28 日块、方向和年份存在不稳定。
- RSI6、已闭合周线和已测试的上下文块没有统计确认的稳定增量。
- B0 在同日同方向内没有证明额外选币能力；M1 市场状态交互没有改善 B0。
- 当前产物只支持事件级诊断，不能支持上线、实盘、资金配置或收益承诺。

### 2.2 只能视为线索

- B0 的 2025+ AUC `0.5589` 可能代表可泛化的微弱信息，也可能包含多轮研究复用、市场结构变化和幸存者/数据范围影响。
- B0 的高分尾部在部分年份和方向较强，但 2025 和 2026 的冻结阈值收益方向相反。
- 个别市场状态与方向格子的点估计较好，但 P6 没有完成足以支持六格局部部署的独立新 OOS 证明。
- 事件标签净收益均值有时为正，但中位数经常为负；均值由右尾少数大幅盈利事件抬高。

### 2.3 现有证据不能支持

- “模型已经把 30% 稳定提高到 40% 以上并可实盘。”
- “P2 的 41% Top10 就是 2025+ 实际验证成功率。”
- “P6 证明所有 MA7 机器学习价值都来自市场行情。”
- “P6 证明 MA7 研究路径已被判死刑。”
- “Top5 表示每天选 5 个币”或“Top1 表示每天选 1 个币”。本研究里的 Top1/5/10 是样本排名前 `1%/5%/10%`。
- “事件标签净收益等于账户收益。”事件之间可重叠，没有资本占用和组合约束。

## 3. 数据复现合同

### 3.1 必要原始数据

复现 P1–P6 至少需要：

| 数据 | 必需字段 | 时间含义 |
| --- | --- | --- |
| 15 分钟 K 线 | symbol, open_time, open, high, low, close, volume, quote_volume, trade_count, close_time | 只接受已闭合 K 线 |
| 1 小时 K 线 | 可由 15 分钟聚合；字段同上 | 用于下一开盘入场和 20 日 first-hit 标签 |
| funding | symbol, fundingTime, fundingRate | 按真实发生时间累计到事件退出时点 |
| 合约元数据 | symbol, pair, contractType, status, quoteAsset, onboardDate | 建立 USD-M USDT perpetual 历史宇宙 |

公开数据入口可以使用 Binance USD-M Futures REST：

- `GET https://fapi.binance.com/fapi/v1/exchangeInfo`
- `GET https://fapi.binance.com/fapi/v1/klines`
- `GET https://fapi.binance.com/fapi/v1/fundingRate`
- 历史批量数据使用 `https://data.binance.vision/` 的 USD-M Futures 月度/日度归档。

仅使用当前 `exchangeInfo` 会漏掉历史退市合约，不能精确复现历史动态宇宙。审查者必须拥有历史合约清单或从历史归档扫描出曾存在的所有 USD-M USDT perpetual。若做不到，应把宇宙复现记为 `PARTIAL_UNIVERSE_REPRODUCTION`，不能把样本差异归因于模型代码。

### 3.2 日线构造

1. 每个 UTC 小时必须由 4 根已闭合 15 分钟 K 线组成。
2. 每个 UTC 日必须由 24 个完整小时组成。
3. 日线时间戳 `ts` 表示当天 `00:00 UTC`，聚合范围为 `[ts, ts+1 day)`。
4. `open` 取第一根 15 分钟 K 线开盘，`high` 取最大值，`low` 取最小值，`close` 取最后一根收盘，`volume`、`quote_volume`、`trade_count` 求和。
5. 不完整日不得用前值填充，也不得进入事件或滚动特征。
6. 当前正式数据上限为 `ts < 2026-05-31 00:00:00 UTC`，最大日线特征日为 `2026-05-30`。

### 3.3 funding 处理

同一个 `symbol + fundingTime` 若存在重复记录，先对 `fundingRate` 求均值去重。日级 funding 为该 UTC 日内所有 funding rate 之和。事件净收益从 `entry_ts` 到实际退出时点按闭区间查找已记录 funding 并求和。缺失 funding 不做推测填充，按已有记录求和，并必须报告缺失边界。

### 3.4 资产宇宙和资格

资产基础要求为 USD-M、USDT 报价、永续合约。早期全市场 scout 排除以下 base symbol：

- 稳定币或法币类：`USDC, BUSD, TUSD, USDP, FDUSD, DAI, SUSD, EUR, AEUR, GBP, AUD, BRL, USD1, USDE, XUSD, BFUSD`
- 指数类：`BLUEBIRD, DOTECO, FOOTBALL`
- 已知美股代币类：`AAPL, AMZN, COIN, CRCL, GOOGL, HOOD, META, MSFT, MSTR, NVDA, PLTR, TSLA`

P5 主加密验证进一步把以下已知 TradFi base 排除出主统计，只保留为不支持的诊断：

`AAPL, AMZN, COIN, CRCL, GOOGL, HOOD, META, MSFT, MSTR, NVDA, PLTR, QQQ, SPX, SPY, TSLA, TSM, UBER, XAG, XAU, XPD, XPT`。

逐资产逐日资格：

```text
complete_day = 24 个完整小时且每小时 4 根闭合 15m
listing_age_days = ts - 该资产第一个完整日
complete_days_30d = 以 ts 为时间索引，对 complete_day 做 trailing 30D 时间窗求和
continuity_30d = complete_days_30d / min(30, listing_age_days + 1)
quote_volume_30d = quote_volume 的 trailing 30D 时间窗均值，min_periods=1

tradable_marker_p0 =
    complete_day
    AND listing_age_days >= 60
    AND continuity_30d >= 0.95
    AND quote_volume_30d 有限
    AND quote_volume_30d > 0
```

P0R 数据质量资格：

```text
base_model_eligible_p0r =
    tradable_marker_p0
    AND entry_ref > 0
    AND atr_anchor > 0
    AND atr_anchor / entry_ref <= 0.50
    AND abs(ret_1d) <= 3.00

model_eligible_entry_p0r =
    base_model_eligible_p0r
    AND future_path_complete_20d
```

`abs(ret_1d) > 3.00` 被视为价格尺度异常，`atr_anchor/entry_ref > 0.50` 被视为经济尺度异常。两者是数据质量门，不允许根据模型结果回调。

### 3.5 市场宽度的 point-in-time 计算

每个日期只用当日 `tradable_marker_p0=true` 且物理排除 HYPE 的 donor：

```text
pit_universe_size = 当日合格资产数
market_breadth_above_ma7 = mean(close > SMA7)
market_breadth_above_ma30 = mean(close > SMA30)
market_up_ratio_1d = mean(ret_1d > 0)
market_ret_1d_dispersion = sample_std(ret_1d)
market_ret_7d_median = median(ret_7d)
market_ret_30d_median = median(ret_30d)
liquidity_rank_pct = 当日 quote_volume_30d 的 percent rank
```

非合格 donor 的 `liquidity_rank_pct` 必须为空。波动状态按每个资产、每个日期之前的历史单独计算：至少 30 个过去的 `atr14_pct`；低于等于过去 33.33% 分位为 `low`，低于等于过去 66.67% 分位为 `mid`，否则为 `high`；不足 30 个历史值为 `insufficient_history`。当前日不得参与分位数拟合。

## 4. 事件、标签与事件净收益

### 4.1 基础指标

对每个资产按有效日顺序计算：

```text
SMA_n[t] = mean(close[t-n+1 : t])，min_periods=n
TR[t] = max(
    high[t] - low[t],
    abs(high[t] - close[t-1]),
    abs(low[t] - close[t-1])
)
ATR_n[t] = mean(TR[t-n+1 : t])，min_periods=n
atr_n_pct[t] = ATR_n[t] / close[t]
ret_nd[t] = close[t] / close[t-n] - 1
```

正式 P1–P6 使用 `ATR14` 作为事件屏障尺度，不是早期 P0 的 `ATR7`。

### 4.2 实际 P1–P6 穿越实现

实际事件代码为：

```text
long_cross[t] = close[t] > SMA7[t] AND close[t-1] <= SMA7[t-1]
short_cross[t] = close[t] < SMA7[t] AND close[t-1] >= SMA7[t-1]
```

每个 `asset + ts` 最多一个方向。`side_sign=+1` 表示 long，`side_sign=-1` 表示 short。

重要审计差异：最早 P0 冻结文字写的是前一日也必须严格 `<` 或 `>`，等号不算穿越；P1–P6 继承的实际实现却在前一日使用 `<=` 或 `>=`。浮点收盘恰好等于七日均线的事件预计很少，但这是合同与实现的语义差异。外部复现必须同时统计：

```text
equality_boundary_rows = count(close[t-1] == SMA7[t-1])
```

若该数量非零，应分别给出严格口径与实际口径的样本及指标差异，不能静默忽略。

### 4.3 已知时点与入场参考

事件日 `ts` 的完整日线在 `ts+1 day 00:00 UTC` 才已知：

```text
feature_known_at = ts + 1 day
entry_ts = feature_known_at
entry_ref = entry_ts 对应完整 1h K 线的 open
atr_anchor = ATR14[ts]
```

本研究允许 `feature_known_at == entry_ts`，含义是在 UTC 边界用刚闭合的前一日数据、按下一小时开盘参考价入场。P3 曾错误要求 `feature_known_at < entry_ts`，因此停止；P3R 修复为允许相等。

### 4.4 20 日 first-hit 标签

要求从 `entry_ts` 起连续存在 `20 × 24 = 480` 根完整小时 K 线。对 long：

```text
favorable_path[h] = (hourly_high[h] - entry_ref) / atr_anchor
adverse_path[h] = (entry_ref - hourly_low[h]) / atr_anchor
```

对 short：

```text
favorable_path[h] = (entry_ref - hourly_low[h]) / atr_anchor
adverse_path[h] = (hourly_high[h] - entry_ref) / atr_anchor
```

分别查找第一个 `favorable_path >= 2.0` 和第一个 `adverse_path >= 1.0` 的小时，小时序号从 1 开始。裁决：

```text
若 favorable_hour < adverse_hour: favorable_first, success=true
若 adverse_hour < favorable_hour: adverse_first, success=false
若二者同一小时: ambiguous_same_hour, success=false
若 480 小时内只有 favorable: favorable_first, success=true
若 480 小时内只有 adverse: adverse_first, success=false
若二者都没有: timeout, success=false
```

同小时双触发按止损先到处理，是保守假设。小时 OHLC 无法知道同小时内部真实路径，因此不能把它描述为精确撮合。

主标签：

```text
label_entry_success_20d = 1[result == favorable_first]
label_end_ts_20d = entry_ts + 20 days
```

### 4.5 事件净收益

参数：

| 参数 | 数值 |
| --- | ---: |
| 杠杆 | `1.0` |
| 单次成交手续费 | `0.0010` |
| 单次成交滑点 | `0.0004` |
| 双边总成本 | `2 × (0.0010 + 0.0004) = 0.0028` |
| 顺向屏障 | `+2 ATR14` |
| 逆向屏障 | `-1 ATR14` |
| 最长持有 | `20 days` |

价格收益：

```text
favorable_first: price_return = +2 * atr_anchor / entry_ref
adverse_first or ambiguous_same_hour: price_return = -1 * atr_anchor / entry_ref
timeout: price_return = side_sign * (terminal_close / entry_ref - 1)

funding_return = -side_sign * funding_sum(entry_ts through exit_ts)
label_entry_net_return = price_return + funding_return - 0.0028
```

入场时等价于同时放置固定的顺向 `2 ATR14` 和逆向 `1 ATR14` 屏障，之后不移动。没有 trailing stop，没有分批止盈，也没有单独的 gap-open 撮合：若某小时开盘已经越过屏障，代码仍通过该小时 high/low 判定命中，并按精确屏障收益记账，而不是按真实 gap open 价格成交。没有盘口冲击模型。事件净收益只是统一经济排序诊断，不是账户成交回测。

### 4.6 组合和仓位边界

每个事件按独立 1 倍名义资金计算。不同资产、不同日期和相互重叠的 20 日事件不共享资金池；没有最大持仓数、同日仲裁、风险平价、波动缩放、保证金、强平、容量和再平衡规则。因此任何 Sharpe、最大回撤、年化收益或账户权益都不能从这些事件均值直接推导。

## 5. 69 个 B0 特征的完整定义

### 5.1 方向对齐约定

任何有方向的原始量 `x` 使用：

```text
dir_x = side_sign * x
```

区间位置和极值距离按 long/short 镜像。字段前缀 `t1_` 表示同一资产同一方向面板的前一个有效日值，由 `shift(1)` 得到；它不保证是前一个日历日，因此审查者必须同时验证原始日线连续性。

数值缺失只用当前训练折中位数填充。分类 `t1_volatility_state_p0r` 只用训练折观察到的类别 one-hot；验证出现未知类别时所有已知类别列为 0。预处理拟合不得使用验证行。

### 5.2 G1：前一日 MA7 状态，12 个

1. `t1_dir_close_ma7_dist_atr`
2. `t1_dir_ma7_slope_1d_atr`
3. `t1_dir_ma7_slope_3d_atr`
4. `t1_dir_ma7_slope_5d_atr`
5. `t1_dir_ma7_slope_change_3d`
6. `t1_dir_ma7_slope_accel_5d`
7. `t1_days_since_ma7_cross`
8. `t1_ma7_cross_count_7d`
9. `t1_ma7_cross_count_14d`
10. `t1_dir_price_side_ma7`
11. `t1_dir_favorable_run_days`
12. `t1_dir_opposite_run_days`

定义：

```text
close_ma7_dist_atr = (close - SMA7) / ATR14
ma7_slope_kd_atr = (SMA7[t] - SMA7[t-k]) / (k * ATR14[t]), k in {1,3,5}
ma7_slope_change_3d = ma7_slope_1d_atr[t] - ma7_slope_1d_atr[t-3]
ma7_slope_accel_5d = slope1[t] - 2*slope1[t-2] + slope1[t-4]
above_ma7 = 1 if close > SMA7 else 0
dir_price_side_ma7 = side_sign * (2*above_ma7-1)
days_since_ma7_cross = 穿越当日为 0，之后每个有效日加 1
ma7_cross_count_nd = 最近 n 个有效日发生任一方向 MA7 穿越的次数，min_periods=1
up_run_days = 当前连续 close[t] > close[t-1] 的有效日数量
down_run_days = 当前连续 close[t] < close[t-1] 的有效日数量
long favorable_run=up_run, opposite_run=down_run
short favorable_run=down_run, opposite_run=up_run
```

### 5.3 G2：事件日几何，13 个

1. `dir_close_ma7_dist_atr`
2. `dir_ma7_slope_1d_atr`
3. `dir_ma7_slope_3d_atr`
4. `dir_ma7_slope_5d_atr`
5. `dir_ma7_slope_change_3d`
6. `dir_ma7_slope_accel_5d`
7. `large_cross_degree_atr`
8. `dir_ret_1d`
9. `daily_range_atr`
10. `body_atr`
11. `dir_close_location`
12. `dir_favorable_wick_atr`
13. `dir_adverse_wick_atr`

定义：

```text
large_cross_degree_atr = max(
    abs((close-SMA7)/ATR14),
    abs((close-SMA14)/ATR14),
    abs((close-SMA30)/ATR14),
    abs((close-SMA60)/ATR14)
)
daily_range_atr = (high-low)/ATR14
body_atr = abs(close-open)/ATR14
raw_close_location = (close-low)/(high-low)
dir_close_location = raw_close_location for long, 1-raw_close_location for short
lower_wick = (min(open,close)-low)/ATR14
upper_wick = (high-max(open,close))/ATR14
favorable_wick = lower_wick for long, upper_wick for short
adverse_wick = upper_wick for long, lower_wick for short
```

`large_cross_degree_atr` 虽被归入事件几何，实际包含 SMA14/30/60 距离。审查者不应把 B0 描述成“只含 MA7 的纯模型”。

### 5.4 G3：波动状态，11 个

1. `atr7_pct`
2. `atr14_pct`
3. `atr30_pct`
4. `atr14_to_atr30`
5. `atr7_to_atr30`
6. `t1_atr7_pct`
7. `t1_atr14_pct`
8. `t1_atr30_pct`
9. `t1_atr14_to_atr30`
10. `t1_atr7_to_atr30`
11. `t1_volatility_state_p0r`

```text
atr14_to_atr30 = ATR14 / ATR30
atr7_to_atr30 = ATR7 / ATR30
```

分类波动状态使用第 3.5 节的逐资产 prior-only expanding 分位数。

### 5.5 G4：成交活跃度，5 个

1. `volume_to_7d`
2. `quote_volume_to_7d`
3. `volume_to_30d`
4. `quote_volume_to_30d`
5. `volume_change_1d`

```text
volume_to_nd = volume[t] / mean(volume[t-n+1:t])，min_periods=n
quote_volume_to_nd = quote_volume[t] / mean(quote_volume[t-n+1:t])，min_periods=n
volume_change_1d = volume[t] / volume[t-1] - 1
```

### 5.6 G5：前一日动量与位置，21 个

字段：

- `t1_dir_ret_{1,3,7,14,30,60}d`，6 个。
- `t1_dir_range_pos_{3,7,14,30,60}d`，5 个。
- `t1_dir_distance_to_favorable_extreme_{3,7,14,30,60}d_atr`，5 个。
- `t1_dir_distance_from_adverse_extreme_{3,7,14,30,60}d_atr`，5 个。

对窗口 `n in {3,7,14,30,60}`：

```text
rolling_high_n = max(high, n)，min_periods=n
rolling_low_n = min(low, n)，min_periods=n
raw_range_pos_n = (close-rolling_low_n)/(rolling_high_n-rolling_low_n)
long dir_range_pos = raw_range_pos
short dir_range_pos = 1-raw_range_pos

distance_to_high_n_atr = (rolling_high_n-close)/ATR14
distance_to_low_n_atr = (close-rolling_low_n)/ATR14

long favorable extreme = rolling_high, adverse extreme = rolling_low
short favorable extreme = rolling_low, adverse extreme = rolling_high
```

### 5.7 G6：前一日路径状态，7 个

1. `t1_path_efficiency_7d`
2. `t1_path_efficiency_14d`
3. `t1_path_efficiency_30d`
4. `t1_path_efficiency_60d`
5. `t1_shock_day`
6. `t1_sideways_state`
7. `t1_reexpansion_state`

```text
path_efficiency_nd =
    abs(close[t]-close[t-n]) /
    sum(abs(close[i]-close[i-1]), i=t-n+1 through t)
    min_periods=n

shock_day = abs(ret_1d) > 2 * rolling_std(ret_1d, 30, min_periods=20)
sideways_state = atr7_to_atr30 < 0.75 AND path_efficiency_14d < 0.35
reexpansion_state = atr7_to_atr30 > 1.25 AND path_efficiency_7d > 0.45
```

六组数量恒等式为 `12 + 13 + 11 + 5 + 21 + 7 = 69`。字段顺序必须保持 G1、G2、G3 的当前字段、G4、G5、G6、G3 的五个 `t1_` 数值和分类波动状态这一已冻结顺序；外部实现只要列名映射一致，逻辑回归列顺序改变不会改变数学结果，但哈希身份会改变。

## 6. P5 新特征的完整定义

### 6.1 Wilder RSI6，10 个

```text
delta[t] = close[t]-close[t-1]
gain[t] = max(delta[t],0)
loss[t] = max(-delta[t],0)

第 6 个 delta 后：
avg_gain6 = 前 6 个 gain 的算术均值
avg_loss6 = 前 6 个 loss 的算术均值

之后：
avg_gain6[t] = (5*avg_gain6[t-1]+gain[t])/6
avg_loss6[t] = (5*avg_loss6[t-1]+loss[t])/6
RSI6 = 100 - 100/(1+avg_gain6/avg_loss6)
```

边界：`avg_loss=0, avg_gain>0` 时 RSI=100；两者均为 0 时 RSI=50。

```text
centered = (RSI6-50)/50
dir_rsi6_centered = side_sign*centered
dir_rsi6_delta_1d = side_sign*(RSI6[t]-RSI6[t-1])/100
dir_rsi6_delta_3d = side_sign*(RSI6[t]-RSI6[t-3])/100
long recovery = (RSI6[t]-rolling_min(RSI6,5))/100
short recovery = (rolling_max(RSI6,5)-RSI6[t])/100
long cross50 = RSI6[t]>50 AND RSI6[t-1]<=50
short cross50 = RSI6[t]<50 AND RSI6[t-1]>=50
```

两个 5 日 RSI 极值滚动窗均为 `min_periods=1`。

五个当日字段为 `dir_rsi6_centered`、`dir_rsi6_delta_1d`、`dir_rsi6_delta_3d`、`dir_rsi6_recovery_from_5d_adverse_extreme`、`dir_rsi6_cross_50`；再取各自前一有效日形成五个 `t1_` 字段，共 10 个。

### 6.2 完整 UTC 周线，11 个

周从 Monday `00:00 UTC` 开始，到下一 Monday `00:00 UTC` 才可用。只有由 7 个完整 UTC 日组成的周才能生成特征。日线事件以 `weekly_feature_known_at <= feature_known_at` 做 as-of join；任何大于关系都是 `WEEKLY_LOOKAHEAD_CONTAMINATION`。

```text
weekly_open = 周一日线 open
weekly_high = 七日 high 最大值
weekly_low = 七日 low 最小值
weekly_close = 周日日线 close
weekly_TR = max(high-low, abs(high-prev_week_close), abs(low-prev_week_close))
WATR6 = mean(weekly_TR,6)，min_periods=6
w_ret_nw = weekly_close[t]/weekly_close[t-n]-1, n in {1,4,12}
w_SMA4 = mean(weekly_close,4)，min_periods=4
w_SMA13 = mean(weekly_close,13)，min_periods=13
```

固定字段：

```text
dir_w_ret_1w = side_sign*w_ret_1w
dir_w_ret_4w = side_sign*w_ret_4w
dir_w_ret_12w = side_sign*w_ret_12w
dir_w_close_sma4_dist_watr6 = side_sign*(weekly_close-w_SMA4)/WATR6
dir_w_close_sma13_dist_watr6 = side_sign*(weekly_close-w_SMA13)/WATR6
dir_w_sma4_slope_1w_watr6 = side_sign*(w_SMA4[t]-w_SMA4[t-1])/WATR6
dir_w_sma13_slope_1w_watr6 = side_sign*(w_SMA13[t]-w_SMA13[t-1])/WATR6
dir_w_ma4_ma13_alignment = side_sign*sign(w_SMA4-w_SMA13)
w_atr6_pct = WATR6/weekly_close
w_path_efficiency_12w = abs(close[t]-close[t-12]) / sum(abs(weekly_close.diff()),12)
weekly_history_13w_complete = 1 if 13 个所需完整周全部存在 else 0
```

周线数值缺失不删除事件，只由当前训练折中位数填充。

## 7. 模型、切分、校准和统计

### 7.1 B0 模型

```text
LogisticRegression(
    penalty="l2",
    C=1.0,
    solver="lbfgs",
    max_iter=1000,
    random_state=20260901
)
```

这是 pooled 模型：long 和 short 共用一套系数，所有有方向特征都已镜像对齐。`asset`、绝对价格、entry、ATR、任何未来路径和标签不得进入 X。

参考执行环境为 Python `3.13.0`、pandas `3.0.2`、NumPy `2.4.4`、scikit-learn `1.9.0`、DuckDB `1.5.2`、PyArrow `24.0.0`、LightGBM `4.6.0`。核心数学结果不应依赖操作系统，但完全相同的浮点末位和 Parquet 类型需要记录依赖版本。

### 7.2 开发折

| Fold | 验证开始 | 验证结束，不含 | P5 严格训练 n | P5 验证 n |
| --- | --- | --- | ---: | ---: |
| D1 | 2022-01-01 | 2023-01-01 | 9,376 | 10,452 |
| D2 | 2023-01-01 | 2024-01-01 | 19,838 | 14,145 |
| D3 | 2024-01-01 | 2025-01-01 | 33,416 | 18,052 |

每折训练行同时满足：

```text
event_ts < fold_start
label_end_ts_20d < fold_start
```

验证行满足 `fold_start <= event_ts < fold_end`。严禁随机交叉验证。最终 pre-2025 重训只用 `label_end_ts_20d < 2025-01-01` 的 52,563 行。

### 7.3 概率校准

raw probability 是主排序分数。Platt 校准对裁剪到 `[1e-6,1-1e-6]` 的 raw probability 做 logit 后拟合一元逻辑回归。

- D1 没有更早完整 OOF，保持 raw。
- D2 校准器只使用到 D2 开始前标签已结束的 D1 OOF，共 9,924 行。
- D3 校准器只使用到 D3 开始前标签已结束的 D1+D2 OOF，共 23,502 行。
- 最终 2025+ 校准器只使用完整 pre-2025 OOF。
- 阈值的拟合概率空间和应用概率空间必须相同。

P5 原始实现曾违反后两项，后来已修复并重跑。raw AUC 和 raw Top10 点估计没有因此改变。

### 7.4 排名定义

- 开发 Top10：每个 fold 内部按 raw probability 排名前 10%，再合并。
- 2025+ year-relative Top10：2025 和 2026 各自排名前 10%，再合并。
- pooled Top10：整个 2025+ 一起排名前 10%，它与 year-relative 集合不同。
- Top1/Top5/Top10 表示前 1%/5%/10%，不是固定币数。
- 并列时按 score 降序，随后 `asset`、`ts`、`side` 升序作 outcome-blind 打破。

### 7.5 统计

主要比较使用 28 个 UTC 日为一个时间块的 paired block bootstrap：

| 参数 | 固定值 |
| --- | ---: |
| 重采样次数 | 2,000 |
| block length | 28 days |
| seed | 20260901 |
| 配对方式 | 所有候选共享同一组日期块 draw |
| 重算方式 | 每次在完整重采样事件集合上重新计算 AUC、PR-AUC、Top 比率和净收益 |
| 多重比较 | 五个挑战者做 Benjamini-Hochberg |

不能先对单块计算非线性 AUC/Top10 再平均“块贡献”。P5 原始 CI 曾使用这种错误方式，后来改成完整事件集重采样。

## 8. P0–P6 研究过程

### 8.1 P0：确认问题是否存在

P0 先在 BTC、ETH、BNB、SOL 以及后续全市场 scout 中统计 MA7 穿越后的趋势发生率。全市场历史 scout 使用 2020-01-01 至 2026-06-30 的旧缓存，653 个合格合约、577,890 个完整资产日，得到：

| 口径 | 事件数 | 成功数 | 成功率 | 95% CI |
| --- | ---: | ---: | ---: | ---: |
| 全部穿越 | 111,918 | 34,072 | 30.4% | [30.2%, 30.7%] |
| long | 55,919 | 16,383 | 29.3% | 未作为主 CI 锚点 |
| short | 55,999 | 17,689 | 31.6% | 未作为主 CI 锚点 |

简单过滤的结果：同向斜率 `>=0.02` 成功率约 `32.5%`，成交额放大 `>=1.5` 约 `28.6%`，组合约 `31.0%`，前置 30 日路径比同向约 `29.0%`。这些规则没有把 30% 稳定提高到明显更高水平。

P0 的价值是证明“30% 基础事件 + 尝试筛选”这个问题真实存在。它不能作为 P1–P6 的精确基线，因为 P0 主标签以穿越日收盘、ATR7 和未来日收盘 first-hit 为口径，不含下一开盘、小时 high/low、手续费、滑点和 funding；P1–P6 则使用第 4 节的下一开盘、ATR14、小时 first-hit 标签。

### 8.2 P0R：修复正式建模输入

P0R 物理排除 HYPE，重算 prior-only 波动状态、point-in-time 市场聚合和流动性排名，并加入价格尺度资格。方向化 donor panel 有 1,128,880 行、732 个资产，时间从 2019-09-09 到 2026-05-30；HYPE 为 0，HYPER 有 806 个方向行。

从中筛出实际 MA7 穿越、入场资格和完整 20 日未来路径后，P1 事件面板有 101,187 行、655 个资产，时间从 2019-11-27 到 2026-05-10；pre-2025 有 54,137 行。最终严格训练进一步要求标签在 2025 前结束，得到 52,563 行。

### 8.3 P1：复杂模型第一次尝试

P1 使用 long/short 分头 LightGBM 为主，并有 pooled 对照，尝试 MA7 状态、事件几何、波动、成交量、路径和市场上下文。主要问题不是完全没有信号，而是开发与后续历史差距大：

P1 LightGBM 共同参数为 `objective=binary, metric=auc, learning_rate=0.03, n_estimators=1500, bagging_fraction=1.0, bagging_freq=0, deterministic=true, force_col_wise=true, n_jobs=8, random_state=20260901`，early stopping 为 100 轮。四个复杂度候选分别为：

| 候选 | num_leaves | max_depth | min_data_in_leaf | feature_fraction | lambda_l2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| L1 | 7 | 3 | 250 | 0.75 | 1.0 |
| L2 | 15 | 4 | 500 | 0.75 | 3.0 |
| L3 | 31 | 5 | 500 | 0.75 | 5.0 |
| L4 | 31 | 6 | 1,000 | 0.90 | 8.0 |

long 最终使用 L3、F2 context、固定 50 轮；short 使用 L2、F3 full-market、固定 99 轮。这个分头选择本身增加了研究自由度，也是后续 P2 改回 pooled 简单模型的原因之一。

| 指标 | 数值 |
| --- | ---: |
| 2025+ long AUC | 0.5232 |
| 2025+ short AUC | 0.5314 |
| 2025+ system AUC | 0.5202 |
| system AUC 95% CI | [0.4400, 0.6012] |
| 2025+ Top10 成功率 | 33.60% |
| 2025+ 基础成功率 | 31.73% |
| 2025+ Top10 uplift | +1.87pp |
| 2026 system AUC | 0.4753 |

P1 裁决为不稳定。它说明复杂模型很容易学习历史时期和多空差异，却没有形成可靠的跨期排序。

### 8.4 P2：改为 pooled、简单、可解释模型

P2 把 long/short 方向镜像后合并，比较常数、斜率、简化特征逻辑回归和小型 LightGBM，最终选择 `F1_LOGIT`，也就是后来 B0 的 69 特征 L2 逻辑回归。

| 指标 | P2 数值 |
| --- | ---: |
| D1 AUC | 0.5945 |
| D2 AUC | 0.5598 |
| D3 AUC | 0.5715 |
| OOF AUC | 0.567264 |
| OOF AUC 95% CI | [0.539441, 0.593605] |
| OOF Top10 成功率 | 40.74% |
| OOF 基础成功率 | 31.86% |
| OOF Top10 uplift | +8.88pp |
| Top10 uplift 95% CI | [4.30pp, 13.05pp] |
| F1 相对 MA7 核心 F0 的 AUC diff | +0.0210 |
| F1-F0 AUC diff 95% CI | [-0.0050, 0.0453] |

P2 的 `40.74%` 是 2022–2024 开发 OOF 的 fold-relative Top10，不是 2025+。P2 没有输出 2025+ 预测。因为 F1 相对最小 MA7 核心 F0 的增量 CI 跨 0，裁决为 `SIGNAL_EXPLAINED_BY_MA7_CORE`：有弱排序，但不能证明复杂路径字段贡献了稳定新增信息。

### 8.5 P3：错误时间不等式触发停止

P3 原合同要求 `feature_known_at < entry_ts`，但本研究的定义是事件日刚闭合时 `feature_known_at == entry_ts`，因此所有 52,563 行都违反了错误合同。P3 没有训练模型，裁决 `DATA_BLOCK_NOT_READY`。

这是规格错误，不是发现数据偷看。P3 的正确处理是停止，而不是偷偷改变时间字段。

### 8.6 P3R：修复时间边界，审计上下文增量

P3R 将允许条件修复为 `feature_known_at <= entry_ts`，并冻结五个候选：B0、流动性块、MA30 上下文、跨市场/BTC、funding。结果：

- B0 严格 OOF AUC 约 `0.5716`。
- 流动性块 B1 相对 B0 AUC diff `+0.0006`，95% CI `[-0.00165, 0.00276]`。
- 跨市场块 B3 相对 B0 AUC diff `+0.00295`，95% CI `[-0.0261, 0.0337]`。
- 所有新增块均未通过确认增量门槛。

裁决为 `SUGGESTIVE_CONTEXT_INCREMENT_ONLY`。上下文可能有线索，但没有足够证据替代或扩展 B0。

### 8.7 P4：69 特征消融与压缩

P4 将 B0 冻结成 G1–G6 六组，分别做删除消融、单组诊断，并预注册两个压缩候选：

| 模型 | 特征数 | 相对 B0 AUC diff | 相对 B0 Top10 diff | 结果 |
| --- | ---: | ---: | ---: | --- |
| `R_FULL_B0_69` | 69 | 0 | 0 | 参考 |
| `M_EVENT_25` | 25 | -0.0345 | +0.49pp | 非劣门失败 |
| `M_EVENT_VOL_36` | 36 | -0.0208 | -1.76pp | 非劣门失败 |

B0 D1–D3 macro AUC `0.5799`，fold-relative Top10 成功率 `41.62%`。删除 G4 成交活跃度后 Top10 diff 为 `-1.38pp`，多重比较 q=`0.009`，因此 G4 被标为开发期必要证据；这不等于 G4 单组可以独立交易。裁决 `FULL_B0_REMAINS_REFERENCE`。

### 8.8 P5：RSI6、完整周线和 2025+ 复用验证

P5 在读标签与 2025+ 表现前冻结六个候选：

| 候选 | 特征数 | 含义 |
| --- | ---: | --- |
| `R_B0_69` | 69 | P4 参考 |
| `C_NO_G3_58` | 58 | 删除 11 个波动字段 |
| `C_B0_PLUS_RSI_79` | 79 | B0 + RSI6 |
| `C_B0_PLUS_WEEKLY_80` | 80 | B0 + 完整周线 |
| `C_B0_PLUS_RSI_WEEKLY_90` | 90 | B0 + RSI6 + 周线 |
| `C_NO_G3_PLUS_RSI_WEEKLY_79` | 79 | 删除 G3 + RSI6 + 周线 |

数据审计：严格 pre-2025 52,563 行、338 个资产、long/short 为 26,237/26,326，事件日 2019-11-27 至 2024-12-10，最大 label end 为 2024-12-31。2025+ 主加密验证 46,892 行，其中 2025 为 32,111、2026 为 14,781；seen/new asset 行数为 29,274/17,618。另有 100 个已知 TradFi 事件，仅作不支持诊断。

周线因果审计：99,555 个开发加验证事件中，`weekly_feature_known_at < feature_known_at` 86,136 行，等于 13,419 行，大于 0 行，缺失 0 行。

2025+ 主结果：

| 候选 | AUC | PR-AUC | Top10 成功率 | uplift | Top10 净均值 | Top10 净中位数 | AUC diff 95% CI | Top10 diff 95% CI | BH q |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 | 0.5589 | 0.3499 | 35.11% | +3.39pp | +0.23% | -5.70% | reference | reference | reference |
| no G3 | 0.5614 | 0.3541 | 37.01% | +5.29pp | +0.99% | -5.16% | [-0.0099, 0.0162] | [-0.83pp, 4.66pp] | 0.898 |
| B0 + RSI | 0.5551 | 0.3491 | 36.13% | +4.42pp | +0.49% | -5.53% | [-0.0124, 0.0044] | [-2.17pp, 4.34pp] | 0.898 |
| B0 + weekly | 0.5640 | 0.3528 | 36.15% | +4.44pp | +0.41% | -5.67% | [-0.0042, 0.0148] | [-0.92pp, 2.13pp] | 0.898 |
| B0 + RSI + weekly | 0.5602 | 0.3518 | 36.62% | +4.91pp | +0.60% | -5.54% | [-0.0095, 0.0125] | [-1.68pp, 4.28pp] | 0.898 |
| no G3 + RSI + weekly | 0.5599 | 0.3542 | 37.82% | +6.10pp | +1.07% | -5.15% | [-0.0133, 0.0165] | [-1.80pp, 7.22pp] | 0.898 |

所有增量 CI 跨 0，没有候选通过确认增量或尾部专家门槛。B0 分层：

| 子样本 | AUC | 子样本内部 Top10 成功率 |
| --- | ---: | ---: |
| 2025 | 0.5629 | 34.40% |
| 2026 | 0.5529 | 36.65% |
| long | 0.5659 | 38.91% |
| short | 0.5521 | 31.36% |
| seen assets | 0.5613 | 36.10% |
| new assets | 0.5550 | 33.31% |
| 20 日 non-overlap | 0.5665 | 37.90% |

B0 Bottom10 成功率 `21.59%`，Top-Bottom 差 `13.52pp`。17 个月中 2 个月 AUC 低于 0.5；18 个 28 日块中 3 块 AUC 低于 0.5；Top10 事件净均值有 8/17 个月、9/18 块为负。

P5 原始输出被独立验收发现三项实质缺陷：

1. 非线性指标 CI 错误地先算单块贡献再平均。
2. D2/D3 Platt 校准用了折起点时标签尚未完成的 OOF 行。
3. 冻结阈值和应用概率混用了不同校准空间。

修复不改变问题、样本、标签、候选、特征和切分；重跑后 challenger 结论仍不显著。另修复 manifest 自引用和测试覆盖。验收时 54 个目标测试通过，manifest 的 24 个条目哈希匹配。最终裁决 `NO_NEW_INCREMENT_B0_REMAINS_REFERENCE`。

### 8.9 P5 后验 Top1/Top5 补充统计

在用户追问后，对 B0 2025+ 年度全局排名作了补充重算：

| 排名 | n | 成功率 | 相对 31.72% 裸成功率 uplift | 事件净收益均值 |
| --- | ---: | ---: | ---: | ---: |
| Top1 | 470 | 36.383% | +4.668pp | +1.143% |
| Top5 | 2,346 | 34.868% | +3.152pp | +0.0555% |
| Top10 | 4,691 | 35.110% | +3.394pp | +0.228% |

Top1/Top5 是 P5 完成后的后验补充统计，不是 P5 合同内的主门禁，也没有单独保存完整 bootstrap 置信区间。它们只能帮助理解排序形状，不能作为晋升证据。Top1 没有明显高于 Top10，说明分数顶端未呈现稳定单调的概率跃升。

### 8.10 P6：市场环境、方向和同日选币归因

P6 的问题不是再次判断“全部事件能否排序”，而是拆解 B0 的 AUC 是否主要来自日期、市场环境或方向，并测试同一天同一方向内能否选出更好的币。

市场状态：

```text
raw_breadth = 当日合格 donor 中 close > SMA30 的比例
btc_side = +1 if BTC close > BTC SMA30 else -1
BULL = raw_breadth >= 0.60 AND btc_side > 0
BEAR = raw_breadth <= 0.40 AND btc_side < 0
MIXED = 其余已知状态
UNKNOWN = breadth 或 BTC 状态缺失
six_grid = market_state × {LONG, SHORT}
```

比较三个模型：

| 模型 | 输入 |
| --- | --- |
| `R_B0_69` | 已冻结 B0 raw probability |
| `M0_MARKET_ONLY` | 六格 one-hot，不含币自身结构 |
| `M1_B0_X_SIDE_X_REGIME` | B0 probability 的 logit、六格 one-hot、B0 logit 与五个非参考格交互 |

M1 第二层训练只能使用时间前向的第一层 B0 OOF 分数，不能使用同一训练行的 in-sample B0。M0/M1 均为 L2 Logistic Regression，`C=1.0, solver=lbfgs, max_iter=1000, seed=20260901`。

整体 2025+：

| 模型 | AUC | PR-AUC | 年度 Top5 成功率 | Top5 uplift |
| --- | ---: | ---: | ---: | ---: |
| B0 | 0.5589 | 0.3499 | 34.63% | +2.91pp |
| M0 | 0.5175 | 0.3257 | 31.98% | +0.27pp |
| M1 | 0.5410 | 0.3404 | 33.86% | +2.14pp |

同日同方向 Top5 主检验只保留当日同方向至少 20 个事件，选择数量为 `ceil(5% × 当日同方向事件数)`，并与相同数量的当日同方向等概率随机选择期望比较：

| 模型 | 合格 day-side 组 | 入选 n | 入选成功率 | 随机期望 | 成功率差 | 入选净均值 | 随机净均值 | 净差 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 | 504 | 2,393 | 31.7175% | 31.8648% | -0.1473pp | +0.0495% | +0.0737% | -0.0242pp |
| M0 | 504 | 2,393 | 31.8648% | 31.8648% | 0 | +0.0737% | +0.0737% | 0 |
| M1 | 504 | 2,393 | 30.5056% | 31.8648% | -1.3592pp | -0.2933% | +0.0737% | -0.3670pp |

B0 成功率差 95% CI 约 `[-1.5268pp, +1.3089pp]`，BH q=`0.880`。M1 成功率差 95% CI 约 `[-2.6758pp, +0.1470pp]`，BH q=`0.261`。M1 相对 B0 成功率差 `-1.2119pp`，CI `[-2.2506pp, -0.2645pp]`，raw p=`0.014`、BH q=`0.084`；净收益差约 `-0.3428pp`，CI `[-0.6993pp, -0.0421pp]`。

B0 同日同方向 Top5 的六格点估计全部展示如下；这些格子没有获得足够的独立多重比较与新 OOS 支持，不能挑选其中好看的格子部署：

| 六格 | 入选 n | B0 成功率 | 同日随机期望 | 差值 |
| --- | ---: | ---: | ---: | ---: |
| BEAR_LONG | 609 | 33.4975% | 31.4588% | +2.0387pp |
| BEAR_SHORT | 583 | 26.7581% | 30.6088% | -3.8507pp |
| BULL_LONG | 268 | 38.0597% | 33.2277% | +4.8320pp |
| BULL_SHORT | 219 | 22.8311% | 27.8013% | -4.9703pp |
| MIXED_LONG | 341 | 30.4985% | 32.1965% | -1.6980pp |
| MIXED_SHORT | 373 | 38.3378% | 35.5940% | +2.7438pp |

历史冻结阈值使用 pre-2025 OOF raw score 的 95 分位：

| 模型/时期 | 阈值 | n | 覆盖率 | 成功率 | 事件净均值 |
| --- | ---: | ---: | ---: | ---: | ---: |
| B0 development OOF | 0.510070 | 42,649 | 5.0013% | 42.1003% | +1.5745% |
| B0 2025+ | 0.510070 | 46,892 | 2.8790% | 36.3704% | +0.4221% |
| B0 2025 | 0.510070 | 32,111 | 2.6128% | 33.1347% | -0.5073% |
| B0 2026 | 0.510070 | 14,781 | 3.4571% | 41.6830% | +1.9480% |
| M1 2025+ | 0.452006 | 46,892 | 2.5889% | 33.0313% | -0.1952% |

这组冻结阈值结果正好说明结论边界：B0 对跨日期全部事件仍有弱筛选点估计，但 2025 和 2026 表现方向明显不同；在同日同方向内没有额外选币证明。P6 官方窄裁决为 `MARKET_OR_SIDE_VALUE_ONLY`，但把它扩张解释成“B0 的全部价值都只是市场行情”并不严谨，因为 M0 整体 AUC 只有 `0.5175`，低于 B0 的 `0.5589`，且 P6 同日检验有意消除了日期/方向层面的排序来源。

P6 没有合格未揭示 OOS，状态为 `PENDING_FRESH_OOS`。P6 合同要求六格完整统计、多重比较与 power 说明，当前实现的主要总体与同日检验可复算，但局部六格结论的覆盖仍不足以支持任何局部上线。

## 9. 为什么 P2 看起来比 P5/P6 好

P2 的 Top10 成功率约 40.74%，P5 的 2025+ Top10 只有 35.11%，主要有四个原因：

1. P2 是 2022–2024 的开发 OOF，虽然每行是样本外预测，但研究者已经在这段历史上选择过特征、模型和问题表达；它不是最终未触碰测试。
2. P2 Top10 按 D1/D2/D3 各折内部排名，P5 按 2025 和 2026 各年内部排名，样本状态和排名集合不同。
3. 2025+ 的市场结构、资产组成和方向分布不同；17,618 行来自开发期未见过的新资产。
4. 开发期对候选和解释进行了多轮迭代，存在研究者自由度；越靠后的验证越接近真实泛化能力，通常会回落。

这不表示 P2 “造假”，而表示 P2 的证据等级是开发性前向 OOF，P5 是复用验证，两者不能直接当成同一考试分数。

## 10. 已知可靠性风险

| 风险 | 严重度 | 对结论的影响 | 外部审查要求 |
| --- | --- | --- | --- |
| P0 与 P1–P6 标签变化 | 高 | 30.4% 与后续 31% 基线只是同类问题，不是同一逐行标签 | 分开复现，禁止直接拼接 |
| 穿越等号合同/实现差异 | 中 | 可能改变少量边界事件 | 报告 equality rows 和敏感性 |
| 2025+ 多轮复用 | 高 | 不能称 fresh blind OOS | 明确标 `ITERATIVE_REUSED_VALIDATION_2025_PLUS` |
| 历史动态宇宙 | 高 | 只用当前 exchangeInfo 会产生幸存者偏差 | 使用历史合约清单并对账 |
| 旧 scout 数据缓存 | 中 | 早期全市场数字不应作为 canonical 训练来源 | 新复现从公开原始数据重建 |
| 事件高度重叠 | 高 | 常规独立同分布 CI 会过窄 | 使用日期块 bootstrap 和 non-overlap 诊断 |
| 同小时双触发 | 中 | OHLC 无法确定真实先后 | 固定按止损先到并报告数量 |
| funding 缺失 | 中 | 影响事件净收益，不影响二元标签 | 报告缺失率，禁止默认为数据完整 |
| Top 尾部中位数为负 | 高 | 正均值不代表多数事件盈利 | 同时报均值、中位数和尾部 |
| 无账户组合模拟 | 高 | 无法推导年化和回撤 | 禁止策略级表述 |
| P6 六格局部证据不全 | 中 | 不能部署局部格子 | 新 OOS 前仅作描述 |
| 多次研究选择 | 高 | 单次 p 值低估整体研究自由度 | 最终只能做一次固定模型前瞻确认 |
| P1/P2 旧 manifest 漂移 | 低到中 | 当前测试文件与旧清单的 bytes/SHA256 不同；科学产物条目未发现漂移 | 不把 P1/P2 manifest 称为全量闭合，按结果产物单独核验 |

2026-09-04 的全量 manifest 扫描结果：P1 的 16 个条目中只有 P1 测试文件同时发生 bytes 和 SHA256 漂移；P2 的 12 个条目中只有 P2 测试文件发生同类漂移；P3 的 7 个、P3R 的 13 个、P4 的 16 个、P5 的 24 个、P6 的 24 个条目全部匹配。该问题不改变已保存预测和指标，但意味着 P1/P2 的旧 manifest 不能被描述成当前仓库全量哈希闭合。

## 11. 外部 AI 审查任务书

审查者应独立回答以下问题，并为每项给出 `PASS / PARTIAL / FAIL / NOT_VERIFIABLE`：

### 11.1 数据与时间

1. 是否只使用已闭合 15m、完整小时和完整 UTC 日。
2. 是否建立历史动态合约宇宙，而不是今天仍在交易的合约集合。
3. 是否物理排除 HYPE，同时保留 HYPER。
4. 是否所有市场宽度、分位数、填充、标准化和 one-hot 都是 point-in-time。
5. 是否 `feature_known_at <= entry_ts`，并且没有任何未来数据进入特征。
6. 是否训练行 `label_end < validation_start`。
7. 是否周线只有完整周，且 known-at 不晚于事件特征时点。

### 11.2 事件与标签

1. 是否只保留实际 MA7 穿越事件。
2. 是否报告严格穿越和实际含等号前界实现的差异。
3. 是否用下一 UTC 小时开盘作为 `entry_ref`。
4. 是否用事件日 ATR14 作为固定屏障尺度。
5. 是否扫描 480 根连续小时 K 线。
6. 是否将同小时双触发判失败。
7. 是否 timeout 使用第 480 小时 close。
8. 是否按真实持有期累计 funding 并扣除 0.28% 双边成本。

### 11.3 模型与统计

1. 是否精确复现 69 个 B0 特征且标签/身份字段不进入 X。
2. 是否按 D1/D2/D3 前向切分，而不是 shuffle CV。
3. 是否所有预处理仅拟合训练折。
4. 是否区分 raw 排序与 calibrated probability。
5. 是否用完整重采样事件集计算 28 日块 paired bootstrap。
6. 是否区分 fold-relative、year-relative、pooled、same-day same-side 和 frozen-threshold 选择。
7. 是否对多候选比较做 BH 校正。
8. 是否同时报告 AUC、PR-AUC、Top 成功率、uplift、净均值、净中位数、方向、年份、月度、non-overlap 和新旧资产。

### 11.4 解释

审查者必须分别裁决以下四个命题，不得合成一句“策略有效/无效”：

1. `BASE_RATE_EXISTS`：裸 MA7 穿越约 30% 趋势发生率是否可靠。
2. `GLOBAL_EVENT_RANKING_VALUE`：B0 是否对所有事件具有可重复的弱排序。
3. `SAME_DAY_COIN_SELECTION_VALUE`：B0 是否在同日同方向内能选币。
4. `TRADABLE_STRATEGY_VALUE`：是否有足够证据形成账户级可交易策略。

基于当前证据，本档案的预期裁决是：

| 命题 | 预期裁决 |
| --- | --- |
| BASE_RATE_EXISTS | PASS_WITH_LABEL_DEFINITION_CAVEAT |
| GLOBAL_EVENT_RANKING_VALUE | PARTIAL_WEAK_SIGNAL_NEEDS_FRESH_OOS |
| SAME_DAY_COIN_SELECTION_VALUE | NOT_DEMONSTRATED |
| TRADABLE_STRATEGY_VALUE | FAIL_NOT_TESTED |

## 12. 复现接受锚点

外部实现若使用相同历史数据快照，应满足：

### 12.1 样本锚点

| 锚点 | 预期值 |
| --- | ---: |
| P0 全市场 scout 完整日 | 577,890 |
| P0 全市场 scout 合格合约 | 653 |
| P0 全市场 scout 穿越事件 | 111,918 |
| P0 全市场 scout 成功率 | 30.4% |
| P0R directional rows | 1,128,880 |
| P0R donor assets | 732 |
| P1 全事件 | 101,187 |
| P1 pre-2025 events | 54,137 |
| 最终严格 pre-2025 | 52,563 |
| 严格 long / short | 26,237 / 26,326 |
| P5 OOF predictions | 42,649 |
| P5 2025+ 主加密 | 46,892 |
| P5 2025 / 2026 | 32,111 / 14,781 |
| HYPE rows | 0 |

### 12.2 指标锚点

| 锚点 | 预期值 | 建议容差 |
| --- | ---: | ---: |
| B0 strict OOF AUC | 0.5716 左右 | 0.0005 |
| B0 2025+ AUC | 0.558856 | 0.0001 |
| B0 2025+ PR-AUC | 0.349857 | 0.0001 |
| 2025+ base success | 0.317154 | 0.0001 |
| B0 year-relative Top10 n | 4,691 | 0 |
| B0 year-relative Top10 success | 0.351098 | 0.0001 |
| B0 Top10 uplift | 0.033944 | 0.0001 |
| B0 Top10 net mean | 0.002283 | 0.0001 |
| B0 Top10 net median | -0.057025 | 0.0001 |
| B0 20d non-overlap AUC | 0.566503 | 0.0001 |
| P6 same-day B0 success delta | -0.001473 | 0.0001 |
| P6 same-day M1 success delta | -0.013592 | 0.0001 |
| P6 B0 frozen threshold | 0.510070 | 0.000001 |
| P6 B0 2025+ threshold coverage | 0.028790 | 0.0001 |

不同 Binance 修订快照、历史宇宙或 funding 完整度可能造成细小差异。若样本数差异超过 1%，应先解释数据范围和宇宙，不应直接比较模型指标。

### 12.3 首尾事件锚点

严格 OOF 排序后的前两行：

| fold | asset | side | event ts | feature/entry ts | entry_ref | ATR14 | label end | result | net | raw p | calibrated p |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: |
| D1 | AAVE/USDT:USDT | long | 2022-01-01 | 2022-01-02 | 266.35 | 26.8157142857 | 2022-01-22 | adverse_first | -0.1046784843 | 0.4302400901 | 0.4302400901 |
| D1 | ALICE/USDT:USDT | long | 2022-01-01 | 2022-01-02 | 13.364 | 1.2838571429 | 2022-01-22 | adverse_first | -0.1000683286 | 0.2103962568 | 0.2103962568 |

严格 OOF 排序后的末两行：

| fold | asset | side | event ts | feature/entry ts | entry_ref | ATR14 | label end | result | net | raw p | calibrated p |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: |
| D3 | OM/USDT:USDT | long | 2024-12-10 | 2024-12-11 | 4.01618 | 0.4355671429 | 2024-12-31 | adverse_first | -0.1128238530 | 0.6058556271 | 0.4182213197 |
| D3 | ONDO/USDT:USDT | long | 2024-12-10 | 2024-12-11 | 1.732 | 0.2115214286 | 2024-12-31 | adverse_first | -0.1061335761 | 0.4236109044 | 0.3392146910 |

2025+ 主加密排序后的前两行：

| asset | side | event ts | feature/entry ts | entry_ref | ATR14 | label end | result | net | raw p | calibrated p | frozen selected |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- |
| 1000LUNC/USDT:USDT | long | 2025-01-01 | 2025-01-02 | 0.11226 | 0.0097600000 | 2025-01-22 | adverse_first | -0.0918410298 | 0.3625010526 | 0.3396062027 | false |
| 1000RATS/USDT:USDT | long | 2025-01-01 | 2025-01-02 | 0.06425 | 0.0070671429 | 2025-01-22 | favorable_first | +0.2119921927 | 0.3188945616 | 0.3202147619 | false |

2025+ 主加密排序后的末两行：

| asset | side | event ts | feature/entry ts | entry_ref | ATR14 | label end | result | net | raw p | calibrated p | frozen selected |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- |
| ZEN/USDT:USDT | short | 2026-05-09 | 2026-05-10 | 7.039 | 0.5550000000 | 2026-05-30 | favorable_first | +0.1558053941 | 0.1838748516 | 0.2529353583 | false |
| 币安人生/USDT:USDT | long | 2026-05-09 | 2026-05-10 | 0.38755 | 0.0397171429 | 2026-05-30 | favorable_first | +0.2009955379 | 0.6975071496 | 0.4917517901 | true |

### 12.4 立即否决条件

出现任一项时，不应继续解释模型成绩：

- HYPE 行数不为 0，或 HYPER 被错误删除。
- 非 MA7 穿越事件进入训练或验证。
- 任何特征、填充、标准化、校准或二层分数使用未来标签。
- 周线 known-at 晚于日线 feature known-at。
- 训练行 label end 不早于验证开始。
- 不完整 20 日路径被赋予主标签。
- 随机 CV 替代时间前向切分。
- 把 2025+ 称为首次盲测。
- 把事件均值包装成账户回测。

## 13. 对“是否还值得研究”的专业回答

现有证据不支持继续在已揭示历史上无限增加技术指标。这样做最可能提高历史拟合，不会提高结论可信度。

若继续，唯一合理对象是已经冻结的 B0，而不是再开几十个特征分支。应执行低成本、无资金风险的前瞻 shadow validation：每天事件日闭合后记录 B0 raw score、冻结阈值、市场状态和拟执行选择；20 日标签成熟后才能入库；期间不得改模型、阈值、特征、宇宙和评价规则。预先要求足够的独立日期块、long/short 稳定、成功率增量和事件净收益同时为正，然后一次性裁决。

若前瞻结果仍只有 AUC 约 0.55、Top 尾部提升约 3pp 且经济收益不稳定，这条线应停止作为独立策略研究；B0 可降级为别的趋势策略中的微弱风险过滤因子。若前瞻结果稳定复现并通过成本与组合模拟，才进入策略工程阶段。

机器学习在这里的价值不是保证把 30% 变成很高胜率，而是用严格 OOS 判断“历史里看似有用的 69 个条件，未来是否仍能把概率向上推一点”。当前答案是：历史上推了一点，但证据还不足以把这点优势兑换成可靠策略。

## 14. 附录：仓库内校验（非复现依赖）

本节只帮助拥有原仓库的审查者定位证据；前面所有规范与结论不得依赖本节才能成立。

### 14.1 入口与主账

- [家族 README](../README.md)
- [家族主账](../binance-1d-ma7-ctp-core-ledger.md)
- [决策记录](../decision-log.md)
- [产物索引](../artifacts/README.md)

### 14.2 合同与报告

- [P0 冻结合同](binance-1d-ma7-cross-trend-probability-contract-2026-08-31.md)
- [P1 合同](binance-1d-ma7-ctp-p1-cross-conditioned-entry-model-contract-2026-09-01.md)
- [P1 报告](../diagnostics/binance-1d-ma7-ctp-p1-cross-conditioned-entry-model-2026-09-01.md)
- [P2 合同](binance-1d-ma7-ctp-p2-pooled-minimal-stability-contract-2026-09-01.md)
- [P2 报告](../diagnostics/binance-1d-ma7-ctp-p2-pooled-minimal-stability-2026-09-01.md)
- [P3 合同](binance-1d-ma7-ctp-p3-context-feature-block-audit-contract-2026-09-01.md)
- [P3 报告](../diagnostics/binance-1d-ma7-ctp-p3-context-feature-block-audit-2026-09-01.md)
- [P3R 合同](binance-1d-ma7-ctp-p3r-time-boundary-repair-context-feature-block-audit-contract-2026-09-02.md)
- [P3R 报告](../diagnostics/binance-1d-ma7-ctp-p3r-context-feature-block-audit-2026-09-02.md)
- [P4 合同](binance-1d-ma7-ctp-p4-core-factor-ablation-compression-contract-2026-09-02.md)
- [P4 报告](../diagnostics/binance-1d-ma7-ctp-p4-core-factor-ablation-compression-2026-09-02.md)
- [P5 合同](binance-1d-ma7-ctp-p5-oscillator-weekly-validation-contract-2026-09-02.md)
- [P5 报告](../diagnostics/binance-1d-ma7-ctp-p5-oscillator-weekly-validation-2026-09-02.md)
- [P5 独立验收](../diagnostics/binance-1d-ma7-ctp-p5-independent-acceptance-audit-2026-09-02.md)
- [P6 合同](binance-1d-ma7-ctp-p6-market-regime-side-conditional-ranking-contract-2026-09-03.md)
- [P6 报告](../diagnostics/binance-1d-ma7-ctp-p6-market-regime-side-conditional-ranking-2026-09-03.md)
- [P6 prospective OOS 协议](binance-1d-ma7-ctp-p6-prospective-oos-confirmation-protocol-2026-09-03.md)

### 14.3 关键机器可读产物

- [P4 因子组身份](../artifacts/binance_1d_ma7_ctp_p4_factor_group_spec.json)
- [P5 feature spec](../artifacts/binance_1d_ma7_ctp_p5_feature_spec.json)
- [P5 data audit](../artifacts/binance_1d_ma7_ctp_p5_data_audit.json)
- [P5 strict OOF predictions](../artifacts/binance_1d_ma7_ctp_p5_pre2025_oof_predictions.parquet)
- [P5 2025+ predictions](../artifacts/binance_1d_ma7_ctp_p5_validation_2025_plus_predictions.parquet)
- [P5 paired comparisons](../artifacts/binance_1d_ma7_ctp_p5_paired_comparisons.parquet)
- [P5 summary](../artifacts/binance_1d_ma7_ctp_p5_summary.json)
- [P5 manifest](../artifacts/binance_1d_ma7_ctp_p5_manifest.json)
- [P6 config](../artifacts/binance_1d_ma7_ctp_p6_config.json)
- [P6 exposure ledger](../artifacts/binance_1d_ma7_ctp_p6_exposure_ledger.json)
- [P6 predictions](../artifacts/binance_1d_ma7_ctp_p6_predictions.parquet)
- [P6 market state metrics](../artifacts/binance_1d_ma7_ctp_p6_market_state_metrics.parquet)
- [P6 selection metrics](../artifacts/binance_1d_ma7_ctp_p6_selection_metrics.parquet)
- [P6 paired bootstrap stats](../artifacts/binance_1d_ma7_ctp_p6_paired_bootstrap_stats.parquet)
- [P6 summary](../artifacts/binance_1d_ma7_ctp_p6_summary.json)

### 14.4 实现入口

- [P0 全市场 scout](../scripts/research_binance_1d_ma7_cross_trend_probability_all_market.py)
- [P1](../scripts/run_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py)
- [P2](../scripts/run_binance_1d_ma7_ctp_p2_pooled_minimal_stability.py)
- [P3](../scripts/run_binance_1d_ma7_ctp_p3_context_feature_block_audit.py)
- [P3R](../scripts/run_binance_1d_ma7_ctp_p3r_time_boundary_repair_context_feature_block_audit.py)
- [P4](../scripts/run_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py)
- [P5](../scripts/run_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py)
- [P6](../scripts/run_binance_1d_ma7_ctp_p6_market_regime_side_conditional_ranking.py)

### 14.5 仓库内核验顺序

1. 先校验 P5、P6 manifest 中每个产物的 SHA256。
2. 核对 P4 69 字段顺序哈希 `7035d35f094fb021f04731f539d0d21495b13530e1980af881b3cef71f27b51b`。
3. 核对 P5 验收文档 SHA256 `a006b65db69ad9b7709032a85575c5da43f4c9bc45ff3bb653c608593a6bc552`。
4. 逐行复算第 12.3 节的首尾锚点。
5. 重跑研究文档一致性测试和 P2–P6 目标测试。
6. 最后才解释 AUC、Top 成功率和事件净收益。

2026-09-04 实际执行上述研究文档一致性测试以及 P1–P6 目标测试共 97 项，96 项通过；唯一失败是 P1 manifest 仍要求旧 P1 测试文件为 16,315 bytes，而当前文件为 16,309 bytes。独立 manifest 扫描还发现 P2 测试文件与其旧清单不一致。P3、P3R、P4、P5、P6 manifest 全匹配。此处保留失败事实，不重写旧清单掩盖历史漂移。
