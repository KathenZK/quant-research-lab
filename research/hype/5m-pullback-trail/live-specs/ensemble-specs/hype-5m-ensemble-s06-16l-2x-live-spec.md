---
schema_version: "1.0"
spec_role: ensemble_component
family_id: HYPE-5M-PBTR
component_id: HYPE-5M-ENS-S06
spec_status: draft
---

# HYPE-5M-ENS-S06: 16 子腿 / 2x 实盘代码规格

Family id: `HYPE-5M-PBTR`

状态：研究候选规格，不是已晋升线上版本。本文用于让 AI 直接生成实盘代码骨架和策略逻辑；上线前必须另做 dry-run、风控和交易所复核。

## 策略摘要

- `combo_id`: `16legs_2x`
- 标的：Binance USDT 永续 `HYPE/USDT:USDT`
- K 线：`5m`
- 回测区间：`2025-06-01 00:00:00 UTC` 到 `2026-06-01 00:00:00 UTC`，右开区间。
- 样本切分：IS 到 `2026-03-01 00:00:00 UTC`，OOS 从 `2026-03-01` 到 `2026-06-01`。
- 策略结构：按排名扫描 `16` 条精筛子腿，单仓执行。
- 名义杠杆：`2x`
- 方向偏好：只做空为主，含少量多空双向子腿
- 费用假设：每边 `0.04%`；滑点假设：每边 `0.01%`。

## 回测指标

| 区间 | 日期 | 交易数 | 年化倍数 | 权益倍数 | 最大回撤 | 胜率 | 均笔收益 | 最差单笔 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 全样本 | 2025-06-01 到 2026-06-01 | 839 | 23.34x | 23.29x | -15.29% | 85.46% | 0.38% | -6.75% |
| IS | 2025-06-01 到 2026-03-01 | 669 | 39.10x | 15.49x | -15.26% | 85.05% | 0.42% | -6.75% |
| OOS | 2026-03-01 到 2026-06-01 | 170 | 5.05x | 1.50x | -15.29% | 87.06% | 0.25% | -5.67% |

## 子腿列表

本策略使用 `artifacts/hype_5m_ensemble_combo_legs.csv` 的前 `16` 条子腿。

| 排名 | 子腿 | 方向 | 入场形态 | EMA 快/慢 | 止损/止盈 ATR | 最长持有 | 附加过滤 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `HYPE_5M_C0410` | 只做空 | EMA 偏离回归 | 96/384 | 6.00 / 1.00 | 24 | `dir_htf >= 0.400894`<br>`regime_age >= 237`<br>`dir_roc48 >= -0.0156456` |
| 2 | `HYPE_5M_C0355` | 只做空 | EMA 偏离回归 | 21/96 | 4.00 / 0.75 | 12 | `dir_rsi14 <= 42.8616`<br>`rvol96 >= 1.09099`<br>`bb_width_z192 >= -0.272972` |
| 3 | `HYPE_5M_C0332` | 只做空 | 布林回归 | 12/96 | 6.00 / 1.00 | 24 | `abs_dist_ema >= 0.00407984`<br>`dir_htf <= 0.719235`<br>`dir_htf >= 0.299252` |
| 4 | `HYPE_5M_C0337` | 只做空 | EMA 偏离回归 | 12/96 | 4.00 / 0.75 | 12 | `dir_macd <= -0.0844885`<br>`adx14 <= 34.3165`<br>`dir_htf >= 0.195978` |
| 5 | `HYPE_5M_C0230` | 多空都可 | EMA 偏离回归 | 96/384 | 6.00 / 1.00 | 24 | `rvol96 >= 2.02105`<br>`chop14 >= 42.8604`<br>`atr_pct_96 <= 0.00686405` |
| 6 | `HYPE_5M_C0412` | 只做空 | EMA 偏离回归 | 96/384 | 10.00 / 1.50 | 48 | `regime_age >= 423`<br>`atr_ratio_14_96 >= 1.04502`<br>`atr_pct_96 <= 0.00517933` |
| 7 | `HYPE_5M_C0350` | 只做空 | 布林回归 | 21/96 | 6.00 / 1.00 | 24 | `dir_obv48 <= -0.059556`<br>`eff96 >= 0.0248574`<br>`chop14 <= 58.697` |
| 8 | `HYPE_5M_C0409` | 只做空 | EMA 偏离回归 | 96/384 | 4.00 / 0.75 | 12 | `dir_roc24 <= -0.022666`<br>`dir_roc48 >= -0.0313703`<br>`dir_obv48 <= 0.0179734` |
| 9 | `HYPE_5M_C0356` | 只做空 | EMA 偏离回归 | 21/96 | 6.00 / 1.00 | 24 | `dir_roc24 >= -0.00900665`<br>`eff96 <= 0.0728804`<br>`dir_obv48 <= 0.106727` |
| 10 | `HYPE_5M_C0404` | 只做空 | 布林回归 | 96/384 | 6.00 / 1.00 | 24 | `bb_pos20 >= 0.924606`<br>`dir_cmf20 >= -0.0379452`<br>`regime_age >= 153` |
| 11 | `HYPE_5M_C0374` | 只做空 | EMA 偏离回归 | 34/144 | 6.00 / 1.00 | 24 | `dir_roc24 >= -0.00750176`<br>`dir_htf <= 0.636709`<br>`dir_rsi14 >= 37.7801` |
| 12 | `HYPE_5M_C0194` | 多空都可 | EMA 偏离回归 | 34/144 | 6.00 / 1.00 | 24 | `dir_roc24 >= -0.00771336`<br>`rvol96 >= 1.21405`<br>`eff96 <= 0.0716425` |
| 13 | `HYPE_5M_C0368` | 只做空 | 布林回归 | 34/144 | 6.00 / 1.00 | 24 | `adx14 <= 14.4393`<br>`dir_rsi14 <= 45.2232`<br>`dir_dist_ema <= -0.00270912` |
| 14 | `HYPE_5M_C0175` | 多空都可 | EMA 偏离回归 | 21/96 | 4.00 / 0.75 | 12 | `adx14 >= 28.6404`<br>`abs_dist_ema <= 0.00754398`<br>`bb_width_z192 <= 0.924234` |
| 15 | `HYPE_5M_C0392` | 只做空 | EMA 偏离回归 | 55/192 | 6.00 / 1.00 | 24 | `bb_width_z192 >= 1.22592`<br>`adx14 >= 23.5332`<br>`dir_roc24 >= -0.0201859` |
| 16 | `HYPE_5M_C0391` | 只做空 | EMA 偏离回归 | 55/192 | 4.00 / 0.75 | 12 | `adx14 >= 25.7821`<br>`dir_roc96 <= -0.0196469`<br>`dir_roc48 <= -0.00131883` |

## 子腿共享参数

| 参数 | 值 |
| --- | --- |
| `donchian` | `48` |
| `roc_window` | `24` |
| `min_regime_age` | `0` |
| `max_regime_age` | `768` |
| `breakout_buffer` | `0.0` |
| `pullback_buffer` | `0.005` |
| `max_dist_ema` | `0.12` |
| `min_dir_roc` | `-0.01` |
| `min_dir_rsi` | `42.0` |
| `max_dir_rsi` | `80.0` |
| `min_adx` | `0.0` |
| `max_chop` | `100.0` |
| `max_atr_ratio` | `2.0` |
| `min_rvol` | `0.0` |
| `min_dir_cmf` | `-0.3` |
| `require_macd` | `False` |
| `require_obv` | `False` |
| `require_htf` | `True` |
| `min_efficiency` | `0.0` |
| `trail_atr` | `0.0` |
| `min_hold_bars` | `0` |
| `exit_ema` | `0` |
| `cooldown_bars` | `6` |

## 指标计算定义

所有信号必须只使用已经收盘的 5m K 线。实盘代码至少预热 `800` 根 5m K，低于预热长度时不允许开仓。

- `EMA(span)`: `close.ewm(span=span, adjust=False, min_periods=span).mean()`；本批子腿用到 `12/21/34/55/96/144/192/384`。
- `ATR14/28/96/288`: `TR` 的简单滚动均值；`TR=max(high-low, abs(high-prev_close), abs(low-prev_close))`。
- `atr_ratio_14_96 = ATR14 / ATR96`；`atr_pct_96 = ATR96 / close`。
- `RSI14/28`: Wilder 风格 `ewm(alpha=1/window, adjust=False, min_periods=window)`。
- `MACD histogram`: `EMA12 - EMA26 - signal(EMA9)`。
- `CMF20`: 20 根 K 的 Chaikin Money Flow，分母为 20 根成交量滚动和。
- `OBV slope48`: `OBV.diff(48) / volume.rolling(96).sum()`。
- `Bollinger position`: 中轨 `SMA20`，标准差 `STD20`，`bb_pos20=(close-(mid-2*std))/(4*std)`。
- `bb_width_z192`: `bb_width20=4*std/mid` 后做 192 根滚动 z-score。
- `chop14`: 14 根 Choppiness Index。
- `eff96`: `abs(close.pct_change(96)) / rolling_sum(abs(close.pct_change()), 96)`。
- `rvol96`: `volume / volume.rolling(96).mean()`。
- `htf_spread`: `EMA96 - EMA384`，作为高阶趋势确认，不是真正 1h 重采样。
- `roc24/48/96`: `close.pct_change(window)`。
- `ADX14`: Wilder 风格 `+DI/-DI/DX` 后再 EWM 平滑。
- `regime_age`: 当前非零 EMA 方向已经持续的 5m bar 数。

方向归一化特征：

- `direction = sign(EMAfast - EMAslow)`。
- `side_mode=short` 时只允许 `direction=-1`；`side_mode=both` 时允许 `direction=1/-1`。
- `dir_rocN = direction * rocN`。
- `dir_rsi14 = RSI14` if `direction=1` else `100 - RSI14`。
- `dir_macd = direction * macd_hist`。
- `dir_cmf20 = direction * cmf20`。
- `dir_obv48 = direction * obv_slope48`。
- `dir_htf = direction * htf_spread`。
- `abs_dist_ema = abs(close / EMAfast - 1)`。
- `dir_dist_ema = direction * (close / EMAfast - 1)`。

## 信号生成

### 组合层规则

本策略是一个 one-position ensemble：同一时间全局最多持有一笔仓位。每根 5m K 收盘后，按子腿排名从小到大扫描信号；如果多个子腿同一根 K 同时触发，只接受排名最靠前的子腿。已有仓位未平时，忽略所有新信号。

必须持久化这些状态：

- 当前仓位：`side / leg_rank / entry_ts / entry_price / stop_price / target_price / bars_held`。
- 每条子腿的 cooldown 截止 bar；本批子腿统一 `cooldown_bars=6`。
- 已处理过的 `(signal_ts, side)`，用于防止重启后重复开仓。

### 子腿通用过滤

每条子腿先计算自己的 `EMAfast/EMAslow` 和方向，然后必须满足：

- `direction != 0`。
- `0 <= regime_age <= 768`。
- `abs(close / EMAfast - 1) <= 0.12`。
- 因为本批只保留回归类子腿，所以 `dir_roc24 >= -0.03`。
- `dir_rsi14 <= 80`。
- `ADX14 >= 0`。
- `chop14 <= 100`。
- `atr_ratio_14_96 <= 2.0`。
- `rvol96 >= 0`。
- `dir_cmf20 >= -0.3`。
- `eff96 >= 0`。
- `require_htf=True`，所以 `dir_htf > 0`。

### 入场形态

`ema_deviation_revert`：

- 做多：`direction > 0`，`close / EMAfast - 1 <= -0.005`，且收盘价大于开盘价。
- 做空：`direction < 0`，`close / EMAfast - 1 >= 0.005`，且收盘价小于开盘价。

`bb_reversion`：

- 做多：`direction > 0`，`bb_pos20 <= 0.25`，且收盘价大于开盘价。
- 做空：`direction < 0`，`bb_pos20 >= 0.75`，且收盘价小于开盘价。

通过通用过滤和入场形态后，还必须通过该子腿自己的附加过滤条件。附加过滤条件见下方“子腿逐条规格”。

### 相邻重复信号抑制

单条子腿如果连续两根 bar 给出同方向信号，只保留第一根。实盘实现可以用 `last_leg_signal_side` 和上一根 bar 是否触发来复现。

## 买入/开仓规则

信号在 bar `t` 收盘后确认，回测在下一根 bar `t+1` 的开盘价成交。实盘代码没有“未来开盘价”，所以执行建议是：确认 bar 收盘后立即用市价单或可配置的 aggressive limit 单开仓，并把订单类型做成配置项。

- 做多开仓：买入 HYPE 永续；回测成交价为 `next_open * (1 + 0.0001)`。
- 做空开仓：卖出开空 HYPE 永续；回测成交价为 `next_open * (1 - 0.0001)`。
- 手续费假设：每边 `0.04%`。
- 滑点假设：每边 `0.01%`。
- 名义仓位：`position_notional = account_equity * strategy_leverage`。
- 数量：`quantity = position_notional / entry_price`，再按 Binance 精度和最小名义额截断。
- 建议实盘使用 isolated margin，并额外设置账户级最大亏损、最大名义仓位和熔断阈值；这些不是本回测的一部分。

## 持有规则

开仓后不加仓、不反手、不处理其他子腿的新信号。每根新 5m K 收盘或撮合事件后维护：

- 初始止损距离：`stop_atr * ATR14(signal_bar)`。
- 初始止盈距离：`tp_atr * ATR14(signal_bar)`。
- 本批子腿 `trail_atr=0`，所以没有移动止损。
- 本批子腿 `exit_ema=0`，所以没有 EMA 平仓。
- 持仓时间达到该子腿 `max_hold_bars` 时，按当前 bar 收盘价平仓。

## 卖出/平仓规则

做多：

- 止损价：`entry_price - stop_atr * ATR14(signal_bar)`。
- 止盈价：`entry_price + tp_atr * ATR14(signal_bar)`。
- 平仓方向：卖出 reduce-only。

做空：

- 止损价：`entry_price + stop_atr * ATR14(signal_bar)`。
- 止盈价：`entry_price - tp_atr * ATR14(signal_bar)`。
- 平仓方向：买入 reduce-only。

同一根 K 同时碰到止损和止盈时，回测按“止损优先”。实盘代码应同时挂 reduce-only 止损/止盈保护单；本地账务回放或风控审计也按止损优先对齐研究口径。

平仓后：

- 清空全局仓位。
- 触发该子腿 `cooldown_bars=6` 的冷却期。
- 记录 `exit_reason` 为 `stop / target / time / ema_exit`；本批理论上不会出现 `ema_exit`。

## 子腿逐条规格

### L01 `HYPE_5M_C0410`

- `refined_name`: `HYPE_5M_C0410__dir_htf_ge_0.400894&regime_age_ge_237&dir_roc48_ge_-0.0156456`
- 方向：只做空
- 入场形态：EMA 偏离回归
- 趋势 EMA：`EMA96` vs `EMA384`。
- 风控参数：`stop_atr=6.00`，`tp_atr=1.00`，`trail_atr=0.00`，`max_hold_bars=24`。
- 附加过滤：
  - `dir_htf >= 0.400894`
  - `regime_age >= 237`
  - `dir_roc48 >= -0.0156456`

### L02 `HYPE_5M_C0355`

- `refined_name`: `HYPE_5M_C0355__dir_rsi14_le_42.8616&rvol96_ge_1.09099&bb_width_z192_ge_-0.272972`
- 方向：只做空
- 入场形态：EMA 偏离回归
- 趋势 EMA：`EMA21` vs `EMA96`。
- 风控参数：`stop_atr=4.00`，`tp_atr=0.75`，`trail_atr=0.00`，`max_hold_bars=12`。
- 附加过滤：
  - `dir_rsi14 <= 42.8616`
  - `rvol96 >= 1.09099`
  - `bb_width_z192 >= -0.272972`

### L03 `HYPE_5M_C0332`

- `refined_name`: `HYPE_5M_C0332__abs_dist_ema_ge_0.00407984&dir_htf_le_0.719235&dir_htf_ge_0.299252`
- 方向：只做空
- 入场形态：布林回归
- 趋势 EMA：`EMA12` vs `EMA96`。
- 风控参数：`stop_atr=6.00`，`tp_atr=1.00`，`trail_atr=0.00`，`max_hold_bars=24`。
- 附加过滤：
  - `abs_dist_ema >= 0.00407984`
  - `dir_htf <= 0.719235`
  - `dir_htf >= 0.299252`

### L04 `HYPE_5M_C0337`

- `refined_name`: `HYPE_5M_C0337__dir_macd_le_-0.0844885&adx14_le_34.3165&dir_htf_ge_0.195978`
- 方向：只做空
- 入场形态：EMA 偏离回归
- 趋势 EMA：`EMA12` vs `EMA96`。
- 风控参数：`stop_atr=4.00`，`tp_atr=0.75`，`trail_atr=0.00`，`max_hold_bars=12`。
- 附加过滤：
  - `dir_macd <= -0.0844885`
  - `adx14 <= 34.3165`
  - `dir_htf >= 0.195978`

### L05 `HYPE_5M_C0230`

- `refined_name`: `HYPE_5M_C0230__rvol96_ge_2.02105&chop14_ge_42.8604&atr_pct_96_le_0.00686405`
- 方向：多空都可
- 入场形态：EMA 偏离回归
- 趋势 EMA：`EMA96` vs `EMA384`。
- 风控参数：`stop_atr=6.00`，`tp_atr=1.00`，`trail_atr=0.00`，`max_hold_bars=24`。
- 附加过滤：
  - `rvol96 >= 2.02105`
  - `chop14 >= 42.8604`
  - `atr_pct_96 <= 0.00686405`

### L06 `HYPE_5M_C0412`

- `refined_name`: `HYPE_5M_C0412__regime_age_ge_423&atr_ratio_14_96_ge_1.04502&atr_pct_96_le_0.00517933`
- 方向：只做空
- 入场形态：EMA 偏离回归
- 趋势 EMA：`EMA96` vs `EMA384`。
- 风控参数：`stop_atr=10.00`，`tp_atr=1.50`，`trail_atr=0.00`，`max_hold_bars=48`。
- 附加过滤：
  - `regime_age >= 423`
  - `atr_ratio_14_96 >= 1.04502`
  - `atr_pct_96 <= 0.00517933`

### L07 `HYPE_5M_C0350`

- `refined_name`: `HYPE_5M_C0350__dir_obv48_le_-0.059556&eff96_ge_0.0248574&chop14_le_58.697`
- 方向：只做空
- 入场形态：布林回归
- 趋势 EMA：`EMA21` vs `EMA96`。
- 风控参数：`stop_atr=6.00`，`tp_atr=1.00`，`trail_atr=0.00`，`max_hold_bars=24`。
- 附加过滤：
  - `dir_obv48 <= -0.059556`
  - `eff96 >= 0.0248574`
  - `chop14 <= 58.697`

### L08 `HYPE_5M_C0409`

- `refined_name`: `HYPE_5M_C0409__dir_roc24_le_-0.022666&dir_roc48_ge_-0.0313703&dir_obv48_le_0.0179734`
- 方向：只做空
- 入场形态：EMA 偏离回归
- 趋势 EMA：`EMA96` vs `EMA384`。
- 风控参数：`stop_atr=4.00`，`tp_atr=0.75`，`trail_atr=0.00`，`max_hold_bars=12`。
- 附加过滤：
  - `dir_roc24 <= -0.022666`
  - `dir_roc48 >= -0.0313703`
  - `dir_obv48 <= 0.0179734`

### L09 `HYPE_5M_C0356`

- `refined_name`: `HYPE_5M_C0356__dir_roc24_ge_-0.00900665&eff96_le_0.0728804&dir_obv48_le_0.106727`
- 方向：只做空
- 入场形态：EMA 偏离回归
- 趋势 EMA：`EMA21` vs `EMA96`。
- 风控参数：`stop_atr=6.00`，`tp_atr=1.00`，`trail_atr=0.00`，`max_hold_bars=24`。
- 附加过滤：
  - `dir_roc24 >= -0.00900665`
  - `eff96 <= 0.0728804`
  - `dir_obv48 <= 0.106727`

### L10 `HYPE_5M_C0404`

- `refined_name`: `HYPE_5M_C0404__bb_pos20_ge_0.924606&dir_cmf20_ge_-0.0379452&regime_age_ge_153`
- 方向：只做空
- 入场形态：布林回归
- 趋势 EMA：`EMA96` vs `EMA384`。
- 风控参数：`stop_atr=6.00`，`tp_atr=1.00`，`trail_atr=0.00`，`max_hold_bars=24`。
- 附加过滤：
  - `bb_pos20 >= 0.924606`
  - `dir_cmf20 >= -0.0379452`
  - `regime_age >= 153`

### L11 `HYPE_5M_C0374`

- `refined_name`: `HYPE_5M_C0374__dir_roc24_ge_-0.00750176&dir_htf_le_0.636709&dir_rsi14_ge_37.7801`
- 方向：只做空
- 入场形态：EMA 偏离回归
- 趋势 EMA：`EMA34` vs `EMA144`。
- 风控参数：`stop_atr=6.00`，`tp_atr=1.00`，`trail_atr=0.00`，`max_hold_bars=24`。
- 附加过滤：
  - `dir_roc24 >= -0.00750176`
  - `dir_htf <= 0.636709`
  - `dir_rsi14 >= 37.7801`

### L12 `HYPE_5M_C0194`

- `refined_name`: `HYPE_5M_C0194__dir_roc24_ge_-0.00771336&rvol96_ge_1.21405&eff96_le_0.0716425`
- 方向：多空都可
- 入场形态：EMA 偏离回归
- 趋势 EMA：`EMA34` vs `EMA144`。
- 风控参数：`stop_atr=6.00`，`tp_atr=1.00`，`trail_atr=0.00`，`max_hold_bars=24`。
- 附加过滤：
  - `dir_roc24 >= -0.00771336`
  - `rvol96 >= 1.21405`
  - `eff96 <= 0.0716425`

### L13 `HYPE_5M_C0368`

- `refined_name`: `HYPE_5M_C0368__adx14_le_14.4393&dir_rsi14_le_45.2232&dir_dist_ema_le_-0.00270912`
- 方向：只做空
- 入场形态：布林回归
- 趋势 EMA：`EMA34` vs `EMA144`。
- 风控参数：`stop_atr=6.00`，`tp_atr=1.00`，`trail_atr=0.00`，`max_hold_bars=24`。
- 附加过滤：
  - `adx14 <= 14.4393`
  - `dir_rsi14 <= 45.2232`
  - `dir_dist_ema <= -0.00270912`

### L14 `HYPE_5M_C0175`

- `refined_name`: `HYPE_5M_C0175__adx14_ge_28.6404&abs_dist_ema_le_0.00754398&bb_width_z192_le_0.924234`
- 方向：多空都可
- 入场形态：EMA 偏离回归
- 趋势 EMA：`EMA21` vs `EMA96`。
- 风控参数：`stop_atr=4.00`，`tp_atr=0.75`，`trail_atr=0.00`，`max_hold_bars=12`。
- 附加过滤：
  - `adx14 >= 28.6404`
  - `abs_dist_ema <= 0.00754398`
  - `bb_width_z192 <= 0.924234`

### L15 `HYPE_5M_C0392`

- `refined_name`: `HYPE_5M_C0392__bb_width_z192_ge_1.22592&adx14_ge_23.5332&dir_roc24_ge_-0.0201859`
- 方向：只做空
- 入场形态：EMA 偏离回归
- 趋势 EMA：`EMA55` vs `EMA192`。
- 风控参数：`stop_atr=6.00`，`tp_atr=1.00`，`trail_atr=0.00`，`max_hold_bars=24`。
- 附加过滤：
  - `bb_width_z192 >= 1.22592`
  - `adx14 >= 23.5332`
  - `dir_roc24 >= -0.0201859`

### L16 `HYPE_5M_C0391`

- `refined_name`: `HYPE_5M_C0391__adx14_ge_25.7821&dir_roc96_le_-0.0196469&dir_roc48_le_-0.00131883`
- 方向：只做空
- 入场形态：EMA 偏离回归
- 趋势 EMA：`EMA55` vs `EMA192`。
- 风控参数：`stop_atr=4.00`，`tp_atr=0.75`，`trail_atr=0.00`，`max_hold_bars=12`。
- 附加过滤：
  - `adx14 >= 25.7821`
  - `dir_roc96 <= -0.0196469`
  - `dir_roc48 <= -0.00131883`

## 消融实验

消融使用同一份 `2025-06-01` 到 `2026-06-01` Binance HYPE 5m 数据、同一费用滑点、同一 one-position 组合逻辑；只改变被测试的组件。`年化变化 / 回撤变化 / 胜率变化` 都是相对本策略 baseline 的变化。

### 杠杆消融

| 测试杠杆 | 达标 | 交易数 | 年化倍数 | 最大回撤 | 胜率 | 年化变化 | 回撤变化 | 胜率变化 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.5x | 否 | 839 | 10.75x | -11.63% | 85.46% | -12.60 | +3.66% | +0.00% |
| 2x | 是 | 839 | 23.34x | -15.29% | 85.46% | +0.00 | +0.00% | +0.00% |
| 2.5x | 是 | 839 | 50.29x | -18.85% | 85.46% | +26.95 | -3.56% | +0.00% |

### 执行门槛消融

`取消单仓门槛` 是把所有去重后的子腿信号按时间顺序计入权益曲线；它用于观察单仓约束的贡献，不代表真实账户可以无成本无限并发。

| 执行模型 | 达标 | 交易数 | 年化倍数 | 最大回撤 | 胜率 | 年化变化 | 回撤变化 | 胜率变化 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 单仓执行 | 是 | 839 | 23.34x | -15.29% | 85.46% | +0.00 | +0.00% | +0.00% |
| 取消单仓门槛 | 是 | 998 | 51.56x | -16.74% | 86.57% | +28.22 | -1.45% | +1.11% |

### 删除单条子腿消融

| 删除腿 | 删除对象 | 删除后达标 | 交易数 | 年化倍数 | 最大回撤 | 胜率 | 年化变化 | 回撤变化 | 胜率变化 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `HYPE_5M_C0410` | 是 | 800 | 24.85x | -15.26% | 86.12% | +1.50 | +0.03% | +0.67% |
| 2 | `HYPE_5M_C0355` | 否 | 809 | 19.45x | -15.62% | 85.04% | -3.89 | -0.32% | -0.42% |
| 3 | `HYPE_5M_C0332` | 否 | 817 | 19.09x | -15.78% | 85.43% | -4.25 | -0.49% | -0.02% |
| 4 | `HYPE_5M_C0337` | 否 | 827 | 19.65x | -15.42% | 85.25% | -3.69 | -0.13% | -0.21% |
| 5 | `HYPE_5M_C0230` | 否 | 740 | 15.09x | -15.01% | 85.41% | -8.25 | +0.29% | -0.05% |
| 6 | `HYPE_5M_C0412` | 否 | 813 | 17.74x | -15.42% | 85.36% | -5.60 | -0.13% | -0.10% |
| 7 | `HYPE_5M_C0350` | 是 | 809 | 22.42x | -15.42% | 85.66% | -0.92 | -0.13% | +0.20% |
| 8 | `HYPE_5M_C0409` | 是 | 808 | 20.54x | -15.07% | 85.40% | -2.80 | +0.23% | -0.06% |
| 9 | `HYPE_5M_C0356` | 是 | 822 | 20.13x | -15.26% | 85.28% | -3.21 | +0.03% | -0.18% |
| 10 | `HYPE_5M_C0404` | 是 | 807 | 21.27x | -15.26% | 85.25% | -2.08 | +0.03% | -0.20% |
| 11 | `HYPE_5M_C0374` | 是 | 827 | 23.26x | -15.26% | 85.61% | -0.08 | +0.03% | +0.15% |
| 12 | `HYPE_5M_C0194` | 否 | 796 | 17.81x | -14.37% | 85.30% | -5.53 | +0.92% | -0.16% |
| 13 | `HYPE_5M_C0368` | 否 | 776 | 19.74x | -14.20% | 85.57% | -3.60 | +1.09% | +0.11% |
| 14 | `HYPE_5M_C0175` | 是 | 800 | 22.69x | -15.42% | 85.75% | -0.65 | -0.13% | +0.29% |
| 15 | `HYPE_5M_C0392` | 是 | 822 | 20.25x | -15.42% | 85.16% | -3.09 | -0.13% | -0.30% |
| 16 | `HYPE_5M_C0391` | 否 | 811 | 19.69x | -15.29% | 85.08% | -3.65 | -0.00% | -0.38% |

## AI 生成实盘代码检查清单

- `compute_features(candles)` 必须完全按本文指标公式实现，并只使用已收盘 K 线。
- `build_leg_signal(leg, frame)` 必须返回 `-1 / 0 / 1`，并实现相邻重复信号抑制。
- `select_ensemble_signal(signals)` 必须按 `leg_rank` 优先级选择第一条信号。
- `open_position()` 必须记录子腿编号、信号时间、入场时间、ATR14、止损价、止盈价和杠杆。
- `manage_position()` 必须优先处理止损，再处理止盈，再处理时间止损。
- 所有订单必须带幂等 key，例如 `combo_id + signal_ts + side + leg_rank`。
- 重启后必须从持久化状态恢复当前仓位、冷却状态和已处理 signal key。
- 不允许在未完成 warmup、指标为 NaN、K 线缺失、交易所时间漂移过大或仓位状态不一致时开新仓。

## 研究风险

这 7 个组合是 2025-06-01 到 2026-06-01 的 Binance HYPE 5m 样本内研究结果。它们满足当前回测目标，但高度依赖精筛过滤、组合选择和 one-position 执行门槛。上线前至少需要独立时间段复核、交易所复制、实盘 dry-run、资金费率和强平风险建模。
