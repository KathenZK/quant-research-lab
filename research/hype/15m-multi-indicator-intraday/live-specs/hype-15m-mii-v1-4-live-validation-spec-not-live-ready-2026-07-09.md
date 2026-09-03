---
schema_version: "1.0"
spec_role: lab_handoff
family_id: HYPE-15M-MII
main_status: registered
spec_status: draft
strategy_id: HYPE-15M-MII-V1.4
runner_kind: hype_mii
peer_spec: crates/quant-runner/src/runner/strategies/hype_mii/HYPE-15M-MII-V1.4-SPEC.md
approval_level_max: none
---

# HYPE-15M-MII-V1.4 Live Validation Spec（非实盘批准）2026-07-09

Family：`HYPE-15M-Multi-Indicator-Intraday`（alias：`HYPE-15M-MII`）

Version：`HYPE-15M-MII-V1.4`

Parent version：`HYPE-15M-MII-V1.3`

Status：`validation handoff / not implemented in runner / not dry-run / not live-ready`

## 先读结论

这份文件是给同事验证和 runner 对拍用的 `HYPE-15M-MII-V1.4` live validation spec，不是 live 批准书，也不是 dry-run handoff。

`V1.4` 完全沿用 `V1.3` 的 RSI/MACD 入场、ATR bracket 出场、Binance 成本和固定 `2.5x` 权益暴露，只把成交量过滤改为：

```text
min_rvol96: 1.0 -> 0.85
```

当前 [`/Users/ZK/OpenCode/quant-runner`](file:///Users/ZK/OpenCode/quant-runner) dry-run 仍是 `HYPE-15M-MII-V1.3`。同事验证 `V1.4` 时，不得直接假设现有 runner 已经运行 `V1.4`；必须先实现或参数化 `min_rvol96=0.85`，再做指标、信号、逐笔交易路径和订单时序对拍。

## 身份与边界

| 项 | 值 |
| --- | --- |
| Full family name | `HYPE-15M-Multi-Indicator-Intraday` |
| Alias | `HYPE-15M-MII` |
| Version | `HYPE-15M-MII-V1.4` |
| Parent | `HYPE-15M-MII-V1.3` |
| Exchange | `Binance` |
| Market | `USD-M perpetual` |
| Raw exchange symbol | `HYPEUSDT` |
| CCXT symbol | `HYPE/USDT:USDT` |
| Timeframe | `15m` |
| Timezone | UTC |
| Candle requirement | 只使用已闭合 K |
| Runner repository | [`/Users/ZK/OpenCode/quant-runner`](file:///Users/ZK/OpenCode/quant-runner) |
| Expected runner kind | `hype_mii`（若复用 V1.3 runner，需要把配置或默认参数改为 `min_rvol96=0.85`） |
| Current runner status | 尚未实现为独立 V1.4 dry-run |
| Current dry-run version | `HYPE-15M-MII-V1.3` |
| Core ledger | [`../hype-15m-mii-core-ledger.md`](../hype-15m-mii-core-ledger.md) |
| V1.4 parameter spec | [`../specs/hype-15m-mii-v1-4-parameter-spec-not-live-ready-2026-07-08.md`](../specs/hype-15m-mii-v1-4-parameter-spec-not-live-ready-2026-07-08.md) |
| TP/SL neighborhood report | [`../notes/hype-15m-mii-v1-4-tp-sl-neighborhood-2026-07-09.md`](../notes/hype-15m-mii-v1-4-tp-sl-neighborhood-2026-07-09.md) |

不要用裸 `V1.4` 判断策略身份；它只在 `HYPE-15M-MII` 家族内有效，不属于 `HYPE-EMA-Crossover`、`HYPE-EMA-Trend-Breakout`、`HYPE-Candle-Count-Reversal` 或 `HYPE-15M-Pullback-Trail`。

## 数据要求

### 研究回测输入

标准数据湖口径：

| 项 | 值 |
| --- | --- |
| Exchange | `binance` |
| Market type | `perp` / USD-M futures |
| Symbol | `HYPEUSDT` |
| Timeframe | `15m` |
| Standard data lake window | `2025-05-30T10:30:00+00:00` 到 `2026-07-08T05:30:00+00:00` |
| Rows | `38,765` |
| Quality gate | `True` |
| Required checks | gap、duplicate、critical null、invalid OHLC、open bar、raw/normalized mismatch 均不得有 blocker |

最低字段：

- `ts`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `is_closed`
- `exchange`
- `symbol`
- `market_type`
- `timeframe`
- `source`

实盘或 replay 输入必须丢弃未闭合 K。若最近一根 K 未闭合，禁止把它用于信号、指标、止盈止损距离或状态恢复。

### Recent API 验证输入

最近窗口验证可使用 Binance futures public kline API，但必须在报告中显式记录：

- API 拉取时间。
- UTC 首尾时间。
- row count。
- 是否丢弃未闭合 K。
- gap、duplicate、critical null、invalid OHLC 检查结果。

Recent API 只能用于当期 sanity check，不替代标准数据湖证据。

## 参数总表

### 市场与 runner

| 参数 | 值 | 说明 |
| --- | ---: | --- |
| `kind` | `hype_mii` | 预期复用 `HYPE-15M-MII` runner kind；需确认 V1.4 参数已生效。 |
| `strategy_id` | `HYPE-15M-MII-V1.4` | 事件、日志、状态和订单标签中应明确版本。 |
| `symbol` | `HYPE/USDT:USDT` | Binance USD-M HYPE 永续。 |
| `timeframe` | `15m` | 固定 15 分钟 K。 |
| `warmup_bars` | `2500` | 必须足够覆盖 `ATR96`、`RVOL96`、MACD 和 RSI warmup。 |
| `cycle_delay_seconds` | `3.0` | 新 K 闭合后等待再处理，降低数据未稳定风险。 |
| `mode` | `dry_run` 或 replay | `V1.4` 当前不得直接 live。 |

### 信号与过滤

| 参数 | 值 | 说明 |
| --- | ---: | --- |
| `side` | `both` | 多空双向。 |
| `rsi_window` | `7` | 使用 `RSI(7)` 反转。 |
| `rsi_long_cross` | `40.0` | `RSI7` 从下向上穿越 `40` 触发多头候选。 |
| `rsi_short_cross` | `60.0` | `RSI7` 从上向下穿越 `60` 触发空头候选。 |
| `macd_fast` | `12` | MACD 快 EMA span。 |
| `macd_slow` | `26` | MACD 慢 EMA span。 |
| `macd_signal` | `9` | MACD signal EMA span。 |
| `min_dir_macd` | `0.0` | 方向化 `MACD histogram` 必须非负。 |
| `min_atr_pct96` | `0.0075` | 仅当 `ATR96% >= 0.75%` 时允许交易。 |
| `max_atr_pct96` | `0.028` | 仅当 `ATR96% <= 2.80%` 时允许交易。 |
| `min_rvol96` | `0.85` | `V1.4` 相对 `V1.3` 的唯一入场参数变化。 |
| `h1_confirm` | `false` | 不启用 1h 方向确认。 |
| `rsi14_band` | `false` | 不启用 RSI14 区间过滤。 |
| `cooldown_bars` | `0` | 无额外冷却；单仓状态阻止重叠开仓。 |

### 出场、暴露与成本

| 参数 | 值 | 说明 |
| --- | ---: | --- |
| `exit_kind` | `atr_fixed_bracket` | 入场时设置一次性固定 TP/SL。 |
| `atr_window_for_exit` | `96` | 使用信号 K 的 `ATR96%`。 |
| `tp_atr_mult` | `1.25` | 止盈距离为 `1.25 * ATR96%`。 |
| `sl_atr_mult` | `5.0` | 止损距离为 `5.0 * ATR96%`。 |
| `timeout_bars` | `24` | 最长持有 24 根 `15m` K，约 6 小时。 |
| `trailing` | `false` | 不移动止损，不使用 trailing stop。 |
| `same_bar_priority` | `stop_first` | 同一根 K 同时触发止盈止损时按止损优先。 |
| `exposure` | `2.5` | 固定 `2.5x` 权益暴露；不是交易所整数杠杆。 |
| `leverage` | `3` | Binance 交易所整数杠杆设置建议；实际 sizing 由 `exposure` 控制。 |
| `margin_mode` | `isolated` | 隔离保证金。 |
| `fee_rate_per_fill` | `0.001` | Binance 研究成本：每 fill `0.1000%`。 |
| `slippage_per_fill` | `0.0004` | Binance 研究滑点：每 fill `4 bps`。 |
| `round_trip_cost` | `0.0028` | 一进一出合计成本：`0.28%`。 |
| `funding` | 未计入 | 永续资金费是 live 前 blocker。 |

## 指标定义

所有指标只能使用信号 K `t` 收盘时已经可见的数据。禁止使用入场 K 或未来 K 更新入场信号、过滤条件或 bracket。

### True Range

```text
previous_close[t] = close[t-1]
TR[t] = max(
  high[t] - low[t],
  abs(high[t] - previous_close[t]),
  abs(low[t] - previous_close[t])
)
```

### RSI(7)

验证时必须先确认 Python 研究脚本与 runner 使用同一 RSI 口径。研究规格目标口径为 Wilder/EWM：

```text
delta[t] = close[t] - close[t-1]
gain[t] = max(delta[t], 0)
loss[t] = max(-delta[t], 0)
avg_gain = EWM(gain, alpha=1/7, adjust=false, min_periods=7)
avg_loss = EWM(loss, alpha=1/7, adjust=false, min_periods=7)
RSI7 = 100 - 100 / (1 + avg_gain / avg_loss)
```

已知风险：当前 `quant-runner` 的历史 `rsi()` 实现曾使用 rolling mean 口径而非 Wilder/EWM。若同事复用 runner，必须把 `RSI7` 数值、raw cross 数量、最终信号和逐笔交易路径与 Python 研究脚本对拍；未对齐前，不得声明 `V1.4` 验证通过。

### MACD(12,26,9)

```text
ema12 = EWM(close, span=12, adjust=false, min_periods=12)
ema26 = EWM(close, span=26, adjust=false, min_periods=26)
macd = ema12 - ema26
macd_signal = EWM(macd, span=9, adjust=false, min_periods=9)
macd_hist = macd - macd_signal
```

方向过滤：

```text
long requires macd_hist[t] >= 0
short requires macd_hist[t] <= 0
```

### ATR96%

`ATR96` 是 96 根 `15m` K 的 true range 均值，约 24 小时窗口；不是 96 小时 ATR。

```text
atr96[t] = rolling_mean(TR, window=96, min_periods=96)
atr_pct96[t] = atr96[t] / close[t]
```

### RVOL96

```text
rvol96[t] = volume[t] / rolling_mean(volume, window=96, min_periods=96)
```

`V1.4` 使用：

```text
rvol96[t] >= 0.85
```

## 信号逻辑

在闭合信号 K `t` 上计算：

```text
long_raw[t] = RSI7[t] > 40 and RSI7[t-1] <= 40
short_raw[t] = RSI7[t] < 60 and RSI7[t-1] >= 60
```

方向化过滤：

```text
direction = +1 for long_raw
direction = -1 for short_raw

macd_filter = macd_hist[t] * direction >= 0
atr_filter = 0.0075 <= atr_pct96[t] <= 0.028
rvol_filter = rvol96[t] >= 0.85

candidate_entry = raw_signal and macd_filter and atr_filter and rvol_filter
```

若同一根 K 同时出现多空 raw signal，必须视为实现异常或需要显式优先级；正常 RSI cross 逻辑下不应同根同时触发。

## Bracket 计算

Bracket 使用信号 K `t` 已知的 `ATR96%`。不要使用入场后任何高低点或未来 K 更新 bracket。

```text
dynamic_atr_pct = atr_pct96[t]
take_profit_pct = dynamic_atr_pct * 1.25
stop_pct = dynamic_atr_pct * 5.0
```

研究回测：

```text
entry_price = open[t + entry_delay_bars]
```

Live 或 dry-run runner：

```text
entry_price = actual_market_fill_price or dry-run fill proxy
```

目标价和止损价：

```text
if direction == +1:
  take_profit_price = entry_price * (1 + take_profit_pct)
  stop_price = entry_price * (1 - stop_pct)

if direction == -1:
  take_profit_price = entry_price * (1 - take_profit_pct)
  stop_price = entry_price * (1 + stop_pct)
```

## 执行时序

### 研究主口径 K+1

```text
signal_i = index of closed candle t
entry_delay_bars = 1
entry_i = signal_i + 1
entry_ts = ts[entry_i]
entry_price = open[entry_i]
```

即闭合 K `t` 确认信号，下一根 `15m` K 的 open 入场。

### 延迟压力测试 K+2

```text
entry_delay_bars = 2
entry_i = signal_i + 2
```

`K+2` 用于延迟压力测试，不是主执行承诺。验证报告必须同时输出 K+1 和 K+2。

### Runner 口径

若 runner 在最新闭合 K 被处理后用 market order 入场，则它不是严格研究 K+1 open。验证时必须单独记录：

- 信号 K close 时间。
- runner 实际触发时间。
- market fill 或 dry-run proxy fill。
- 相对 K+1 open 的偏差。
- bracket 是否用实际 fill price 计算。

## 单仓与状态机

规则：

- 同一策略实例同一时间只能有一笔仓位。
- 若 `state.position` 非空，不允许响应新信号。
- 开仓后记录 `signal_ts`、`entry_ts`、`entry_price`、`quantity`、`target_price`、`stop_price`、`timeout_bars`。
- dry-run/replay 可用 candle high/low 模拟 bracket 是否触发。
- live 模式必须挂 reduce-only TP 和 stop-market SL；任一 bracket 腿挂单失败时，必须撤销另一腿并 emergency reduce。
- timeout 到达后取消未成交 bracket，并用市价减仓。

同 K 冲突：

```text
if stop_hit and target_hit:
  exit_reason = both_hit_stop_first
  exit_price = stop_price
```

## 收益计算

研究回测按权益暴露缩放单笔净收益：

```text
raw_return = direction * (exit_price / entry_price - 1)
round_trip_cost = fee_per_fill + entry_slippage + fee_per_fill + exit_slippage
net_trade_return = exposure * (raw_return - round_trip_cost)
```

`V1.4` 成本参数：

```text
exposure = 2.5
fee_per_fill = 0.001
entry_slippage = 0.0004
exit_slippage = 0.0004
round_trip_cost = 0.0028
```

资金费未计入，不能把研究净收益当成可实盘收益。

## 预期回放指标

标准数据湖（`2025-05-30T10:30:00Z` 到 `2026-07-08T05:30:00Z`，quality gate `True`）：

| 入场 | 交易数 | 总收益 | 最大回撤 | 胜率 | Profit Factor |
| --- | ---: | ---: | ---: | ---: | ---: |
| `K+1` | `232` | `978.36%` | `-24.70%` | `84.91%` | `2.237` |
| `K+2` | `239` | `535.54%` | `-38.30%` | `83.26%` | `1.780` |

Recent Binance API（2026-07-09 报告口径，K+1）：

| 窗口 | 交易数 | 总收益 | 最大回撤 | 胜率 | Profit Factor |
| --- | ---: | ---: | ---: | ---: | ---: |
| `最近90d` | `46` | `51.61%` | `-19.78%` | `86.96%` | `1.911` |
| `最近30d` | `15` | `16.65%` | `-12.34%` | `86.67%` | `2.308` |

注意：recent API 窗口会随拉取时间变化；同事验证时应优先复现标准数据湖全样本，再把 recent API 作为当日 sanity check。

## TP/SL 复核结论

`V1.4` baseline 保持：

```text
tp_atr_mult = 1.25
sl_atr_mult = 5.0
```

`2026-07-08` 粗网格和 `2026-07-09` 细邻域搜索均未找到可替换 baseline 的 TP/SL 组合。最近窗口较强的 `TP=1.4 / SL=3.0` 已按用户指示登记为 `HYPE-15M-MII-V1.4A`，但它不是 `V1.4 baseline` 参数：

| 配置 | 全样本 K+1 收益 | 全样本 K+1 回撤 | 全样本 K+1 胜率 | recent 90d K+1 | recent 30d K+1 | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `TP=1.25 / SL=5.0` | `978.36%` | `-24.70%` | `84.91%` | `51.61%` | `16.65%` | `V1.4 baseline` |
| `V1.4A TP=1.4 / SL=3.0` | `584.90%` | `-32.85%` | `78.72%` | `78.82%` | `27.09%` | 已登记观察变体，不替换 baseline |

## 同事验证清单

验证通过前，至少要输出以下材料：

- 数据质量报告：标准数据湖和 recent API 的首尾时间、rows、gap、duplicate、null、invalid OHLC、open bar、raw/normalized mismatch。
- 指标对拍：`RSI7`、`MACD histogram`、`ATR96%`、`RVOL96` 的逐 K 对比，至少覆盖首批信号前后、最近 90d 和随机切片。
- 信号漏斗：raw RSI cross、ATR/RVOL/MACD 过滤后信号数、最终多空信号数。
- 逐笔路径对拍：K+1 与 K+2 的 `signal_ts`、`entry_ts`、方向、entry、TP、SL、exit、exit_reason、raw_return、net_return。
- 单仓检查：不允许重叠仓位，不允许持仓时响应新信号。
- 同 K 冲突检查：同时触发 TP/SL 时必须 stop-first。
- Runner 对拍：runner replay 与 Python 研究脚本的信号、bracket、出场原因和收益差异。
- 执行差异报告：runner market fill proxy 相对 K+1 open 的偏差。
- 成本压力：至少复核默认 Binance 成本（fee `0.001`/fill、slippage `4 bps`/fill），并额外做更差滑点压力。
- 资金费回放：未完成前不得 live。
- 运行安全：missing-bar fail-closed、重启恢复、交易所对账、kill switch、bracket 挂单失败应急减仓。

## 禁止项

- 禁止把本文件解释为 live approval。
- 禁止在未完成指标/路径对拍前把 `V1.4` 标记为 `dry-run handoff`、`paper-live`、`candidate` 或 `live`。
- 禁止把 `V1.4A` 的 `TP=1.4 / SL=3.0` 当成 `V1.4 baseline`。
- 禁止使用未闭合 K 生成信号或更新 stop/TP。
- 禁止用未来 K 的 ATR、RVOL、MACD 或 RSI 修改入场决策。
- 禁止省略 Binance 成本；默认成本为手续费 `0.001`/fill、滑点 `4 bps`/fill。
- 禁止在 bracket 任一腿挂单失败时继续裸仓运行。

## 证据链接

- 主账：[`../hype-15m-mii-core-ledger.md`](../hype-15m-mii-core-ledger.md)
- 决策日志：[`../decision-log.md`](../decision-log.md)
- V1.4 参数规格：[`../specs/hype-15m-mii-v1-4-parameter-spec-not-live-ready-2026-07-08.md`](../specs/hype-15m-mii-v1-4-parameter-spec-not-live-ready-2026-07-08.md)
- V1.4A 参数规格：[`../specs/hype-15m-mii-v1-4a-parameter-spec-not-live-ready-2026-07-09.md`](../specs/hype-15m-mii-v1-4a-parameter-spec-not-live-ready-2026-07-09.md)
- V1.4 TP/SL 粗网格：[`../notes/hype-15m-mii-v1-4-tp-sl-grid-2026-07-08.md`](../notes/hype-15m-mii-v1-4-tp-sl-grid-2026-07-08.md)
- V1.4 TP/SL 邻域搜索：[`../notes/hype-15m-mii-v1-4-tp-sl-neighborhood-2026-07-09.md`](../notes/hype-15m-mii-v1-4-tp-sl-neighborhood-2026-07-09.md)
- V1.4 亏损环境过滤：[`../notes/hype-15m-mii-v1-4-loss-regime-filters-2026-07-08.md`](../notes/hype-15m-mii-v1-4-loss-regime-filters-2026-07-08.md)
- V1.4 动态止损：[`../notes/hype-15m-mii-v1-4-dynamic-stop-2026-07-09.md`](../notes/hype-15m-mii-v1-4-dynamic-stop-2026-07-09.md)
- 标准数据湖 TP/SL 邻域 CSV：[`../artifacts/hype_15m_mii_v1_4_tp_sl_neighborhood_standard_2026-07-09.csv`](../artifacts/hype_15m_mii_v1_4_tp_sl_neighborhood_standard_2026-07-09.csv)
- Recent API TP/SL 邻域 CSV：[`../artifacts/hype_15m_mii_v1_4_tp_sl_neighborhood_recent_2026-07-09.csv`](../artifacts/hype_15m_mii_v1_4_tp_sl_neighborhood_recent_2026-07-09.csv)
