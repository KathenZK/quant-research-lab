---
schema_version: "1.0"
spec_role: lab_handoff
family_id: HYPE-EMA-TB
main_status: registered
spec_status: draft
strategy_id: HYPE-EMA-TB-V39
runner_kind: hype_ema_tb
peer_spec: crates/quant-runner/src/runner/strategies/hype_ema_tb/HYPE-EMA-TB-V39-SPEC.md
approval_level_max: none
---

# HYPE-EMA-TB-V39 Live Spec（同事验证版，非实盘批准）

规格 id：`HYPE-EMA-TB-V39-LIVE-SPEC-2026-07-09`

Family：`HYPE-EMA-Trend-Breakout`（alias：`HYPE-EMA-TB`）

Version：`HYPE-EMA-TB-V39`

Status：`registered / not promoted / not live-ready`；本文是未实现的 runner handoff proposal，不代表 promotion 状态。

## 先读结论

本文档用于把 `HYPE-EMA-TB-V39` 导出为同事可实现、可复现、可对拍的 runner handoff spec。它不是实盘批准书，也不是 dry-run 启动批准。

`V39` 是 `V35` 的温和消融改进版：

```text
V39 = V35
    + long_vol_min: 0.25 -> 0.35
    + short_target_atr_pct: 0.018 -> 0.022
    + 移除冗余空头 1h EMA 确认
    + 保留 max_hold_bars=384 作为实盘异常兜底
```

当前 `/Users/ZK/OpenCode/quant-runner` **没有** `HYPE-EMA-TB-V39` 对应 runner kind、module 或 runner-side SPEC。建议新增 kind 为 `hype_ema_tb`，但该值在本文档创建时尚不存在，不能直接粘贴进当前 runner 配置运行。

## 身份与边界

| 项 | 值 |
| --- | --- |
| Full family name | `HYPE-EMA-Trend-Breakout` |
| Alias | `HYPE-EMA-TB` |
| Version | `HYPE-EMA-TB-V39` |
| Parent version | `HYPE-EMA-TB-V35` |
| Exchange | Binance |
| Market | USD-M perpetual |
| CCXT symbol | `HYPE/USDT:USDT` |
| Raw exchange symbol | `HYPEUSDT` |
| Timeframe | `15m` |
| Timezone | UTC |
| Candle requirement | 只使用已闭合 K 线 |
| Current runner repository | `/Users/ZK/OpenCode/quant-runner` |
| Proposed runner strategy kind | `hype_ema_tb`（当前 runner 尚未实现） |
| Proposed runner strategy module | `crates/quant-runner/src/runner/strategies/hype_ema_tb/mod.rs` |
| Proposed runner SPEC | `crates/quant-runner/src/runner/strategies/hype_ema_tb/HYPE-EMA-TB-V39-SPEC.md` |
| Lab core ledger | `../hype-ema-tb-core-ledger.md` |
| Canonical research spec | `../specs/hype-trend-strategy-v39-spec.md` |

不要用裸 `V39` 判断策略身份；本文只对应 Binance HYPEUSDT 永续 `15m` 的 `HYPE-EMA-Trend-Breakout` 家族。

## 状态与 blocker

当前状态保持：`registered / not promoted / not live-ready`。

进入 runner dry-run 前至少需要完成：

- 在 `quant-runner` 新增 `StrategyKindName::HypeEmaTb`，序列化值 `hype_ema_tb`。
- 新增 runner module、replay、状态机、风险状态和 runner-side SPEC。
- Python 研究脚本与 runner 对拍：特征、信号、入场、TP/SL、indicator exit、timeout、逐笔交易路径。
- 验证门禁 3/4/5：Monte Carlo（默认 `mc3`+`mc4`）、压力测试（执行完整性优先）、相位/K 线切分边界（见现行 [strategy-validation-gates.md](../../../../docs/research-governance/strategy-validation-gates.md)）。
- live-executable 审计：真实下单时序、reduce-only TP/SL、重启恢复、missing-bar fail-closed、kill switch、订单冲突、交易所对账。
- 跨所迁移或同窗执行审计（至少 Binance native 与目标执行所/账户口径对齐）。

## 数据与质量要求

研究回测使用 Binance USD-M futures HYPEUSDT `15m` 标准 raw/normalized 数据湖：

| 项 | 值 |
| --- | --- |
| 数据窗口 | `2025-05-30 10:30 UTC` 至 `2026-07-08 05:30 UTC` |
| 已闭合 K 线 | `38765` |
| missing 15m bars | `0` |
| duplicate ts | `0` |
| invalid OHLC rows | `0` |
| critical nulls | `0` |
| raw/normalized max diff | `0` |
| source | `binance_futures_kline_api` |
| funding rows | `3670` |

runner 最低输入字段：

```text
ts, open, high, low, close, volume, quote_volume, trade_count, vwap, is_closed
```

硬要求：

- `ts` 必须是 UTC，表示该 `15m` K 线开盘时间。
- 只允许已闭合 K 线参与指标、信号、MFE、indicator exit、timeout 更新。
- 若最近一根 Binance K 线未闭合，必须丢弃后再计算。
- 缺 K、重复 K、非法 OHLC、关键字段空值、raw/normalized 不一致时，runner 必须 fail-closed：停止新开仓，保留已有保护单/按风控处理持仓。
- 实盘启动建议预加载至少 `2500` 根已闭合 `15m` K；研究回测 warmup 为 `1600` 根，runner 多加载是为了覆盖 ATR672、EMA384、1h ADX21 与恢复后状态稳定。

## 成本与资金费

研究回测成本：

| 参数 | 值 | 说明 |
| --- | ---: | --- |
| `trade_cost_rate` | `0.00085` | 每 fill 成本，表示手续费与 4 bps adverse slippage 合并口径 |
| round trip | `0.00170` | 入场一次 + 出场一次 |
| funding | included | Binance funding rate 对齐持仓区间 |

live runner 必须使用真实成交价、真实手续费和真实 funding 记账。`0.00085` 只用于研究复现、dry-run 估算和验收对照。

## 参数总表

### 当前 quant-runner 公共字段

这些字段来自当前 `StrategyInstanceConfig`，是 runner 配置中已经存在的公共字段。`kind=hype_ema_tb` 当前尚未实现，必须由同事先扩展 runner。

| 字段 | 建议值 | 说明 |
| --- | --- | --- |
| `name` | `hype-ema-tb-v39-dry-run` | runner 实例名 |
| `enabled` | `false` | 验证完成前默认关闭 |
| `group` | `validation` | 建议验证组 |
| `kind` | `hype_ema_tb` | 建议新增；当前 runner 尚不支持 |
| `mode` | `dry_run` | 先做 dry-run / replay，不允许直接 live |
| `symbol` | `HYPE/USDT:USDT` | Binance USD-M HYPE 永续 |
| `timeframe` | `15m` | 固定 `15m` |
| `account_id` | `dryrun` | 示例账号；同事可按环境替换 |
| `state_dir` | `/home/admin/quant-runner/state/hype-ema-tb-v39-dry-run` | 必须与其它策略不同 |
| `leverage` | `3` | 必须不低于策略最大 allocation `3.0` |
| `margin_mode` | `isolated` | 隔离保证金 |
| `warmup_bars` | `2500` | runner 预加载闭合 K 数 |
| `dry_run_notional_usdt` | `10.0` | dry-run 示例名义本金 |
| `live_confirm` | `false` | live 前必须显式改为 true，并补齐 credentials |

### 建议新增的 V39 策略字段

这些是 `hype_ema_tb` module 应实现的策略字段名。若 runner 侧采用不同字段名，必须同步更新本文档和 runner-side SPEC。

| 字段 | 值 | 说明 |
| --- | ---: | --- |
| `strategy_id` | `HYPE-EMA-TB-V39` | 事件、状态、订单前缀中使用的策略身份 |
| `side` | `both` | 多空双向 |
| `entry_delay_bars` | `2` | K0 close 出信号，K2 open 入场 |
| `research_warmup_bars` | `1600` | 研究回测开始交易的 warmup |
| `ema_fast` | `96` | 15m EMA fast |
| `ema_slow` | `384` | 15m EMA slow |
| `adx_window` | `28` | 15m ADX/DI window |
| `atr_window` | `672` | 15m ATR window，用于 sizing 与 TP/SL |
| `volume_window` | `192` | 15m volume rolling mean window |
| `h1_adx_window` | `21` | 1h ADX/DI window |
| `long_adx_min` | `28.0` | 多头 15m ADX 门槛 |
| `short_adx_min` | `36.0` | 空头 15m ADX 门槛 |
| `long_vol_min` | `0.35` | `volume_surge >= 0.35` |
| `short_vol_min` | `0.50` | `volume_surge >= 0.50` |
| `h1_long_adx_min` | `18.0` | 多头 1h ADX 门槛，严格大于 |
| `long_use_ema_spread` | `true` | 多头要求 `EMA96/EMA384 - 1 > 0` |
| `long_use_h1_di` | `true` | 多头要求 `h1_plus_di > h1_minus_di` |
| `short_use_ema_spread` | `true` | 空头要求 `EMA96/EMA384 - 1 < 0` |
| `short_use_h1_ema` | `false` | V39 删除冗余空头 1h EMA 确认 |
| `long_target_atr_pct` | `0.020` | 多头 sizing 目标 ATR% |
| `short_target_atr_pct` | `0.022` | 空头 sizing 目标 ATR% |
| `max_allocation` | `3.0` | 最大名义敞口倍数 |
| `take_profit_atr` | `5.0` | 固定 entry ATR 止盈距离 |
| `hard_stop_atr` | `7.0` | 固定 entry ATR 硬止损距离 |
| `adx_exit` | `22.0` | indicator exit 的 ADX 阈值 |
| `delayed_bars` | `3` | ADX 弱势连续确认根数 |
| `disable_after_mfe_atr` | `1.5` | MFE 达到该值后永久关闭 indicator exit |
| `max_hold_bars` | `384` | 96 小时 timeout 兜底 |
| `profit_floor_enabled` | `false` | V39 不启用 profit floor |
| `trailing_stop_enabled` | `false` | V39 不启用 trailing stop |
| `same_bar_priority` | `stop_first` | 同一根 K 同时触发 TP/SL 时按 stop 优先 |
| `cooldown_bars` | `0` | 无额外冷却 |
| `same_bar_reentry` | `false` | 同一根 K 出场后不重入 |

## 指标定义

所有指标只能使用已收盘 K。

### True Range 与 ATR672

```text
previous_close[t] = close[t-1]
TR[t] = max(
  high[t] - low[t],
  abs(high[t] - previous_close[t]),
  abs(low[t] - previous_close[t])
)
ATR672[t] = rolling_mean(TR, window=672, min_periods=672)
```

### EMA 与 spread

```text
EMA(span) = close.ewm(span=span, adjust=false, min_periods=span).mean()
ema_spread[t] = EMA96[t] / EMA384[t] - 1
```

### ADX / DI

使用 Wilder/EWM 口径：

```text
up_move[t] = high[t] - high[t-1]
down_move[t] = low[t-1] - low[t]
plus_dm[t] = up_move[t] if up_move[t] > down_move[t] and up_move[t] > 0 else 0
minus_dm[t] = down_move[t] if down_move[t] > up_move[t] and down_move[t] > 0 else 0
alpha = 1 / window
atr_w = EWM(TR, alpha=alpha, adjust=false, min_periods=window)
plus_di = 100 * EWM(plus_dm, alpha=alpha, adjust=false, min_periods=window) / atr_w
minus_di = 100 * EWM(minus_dm, alpha=alpha, adjust=false, min_periods=window) / atr_w
dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
adx = EWM(dx, alpha=alpha, adjust=false, min_periods=window)
```

15m 使用 `window=28`；1h 使用 `window=21`。

### Volume Surge

```text
volume_ma192[t] = rolling_mean(volume, window=192, min_periods=192)
volume_surge[t] = volume[t] / volume_ma192[t] - 1
```

注意：`volume_surge=0.35` 等价于 `RVOL=1.35`。runner 侧字段应使用 `volume_surge` 或清楚注明转换，避免把 `0.35` 误解成 `RVOL=0.35`。

### 1h 特征对齐

从已收盘 15m K 聚合 1h：

```text
resample(rule="1h", label="left", closed="left")
open = first
high = max
low = min
close = last
volume = sum
```

计算 1h ADX/DI 后必须 `shift(1)`，再 forward-fill 到 15m：

```text
h1_features = compute_on_1h_closed_bars(...).shift(1)
h1_aligned = h1_features.reindex(index_15m, method="ffill")
```

这意味着任意 15m bar 只能看到上一根已经完成的 1h bar，不能使用当前未完成 1h bar。

## 信号规则

信号在 K0 收盘确认。若同一根 K 同时出现多空信号，冲突取消，不开仓。

### 多头信号

```text
long_signal[t] =
  ema_spread[t] > 0
  and adx28[t] >= 28
  and volume_surge192[t] >= 0.35
  and h1_adx21[t] > 18
  and h1_plus_di21[t] > h1_minus_di21[t]
```

### 空头信号

```text
short_signal[t] =
  ema_spread[t] < 0
  and adx28[t] >= 36
  and volume_surge192[t] >= 0.50
```

V39 不再要求空头 `h1_ema_spread < 0`。但 15m `ema_spread < 0` 必须保留；V39 全参数消融显示两个空头趋势确认同时移除会严重劣化。

## 入场状态机

```text
K0: 15m bar close 后确认 long_signal / short_signal
K1: 完整跳过，用于等待一个完整 bar，且 entry_atr 使用 K1 已完成 ATR672
K2: 若无持仓且无同 bar exit，按 K2 open 入场
```

入场条件：

- 当前无持仓。
- 当前 bar 没有刚刚执行 pending exit。
- K0 信号方向唯一。
- `entry_atr = ATR672[K1]` 有效且大于 0。
- `open[K2] > 0`。

入场价格研究口径为 `open[K2]`；live 必须使用真实 market fill，并记录 slippage。

## 仓位 sizing

```text
target_atr_pct = 0.020 if long else 0.022
entry_atr_pct = entry_atr / entry_price
allocation = min(3.0, target_atr_pct / entry_atr_pct)
```

含义：

- `allocation` 是相对权益的名义敞口倍数。
- Binance live 配置 `leverage` 必须至少为 `3`，否则高波动低 ATR 期间满 allocation 订单可能因保证金不足被拒。
- 不使用 drawdown scaling，不加仓，不 pyramiding。

## 出场状态机

### 固定 TP/SL

入场后立即定义固定 entry ATR bracket：

```text
take_price = entry_price + direction * 5.0 * entry_atr
hard_stop = entry_price - direction * 7.0 * entry_atr
```

研究回测 intrabar 检查：

- long：`low <= stop` 先触发 stop；否则 `high >= take` 触发 TP。
- short：`high >= stop` 先触发 stop；否则 `low <= take` 触发 TP。
- 同一根 K 同时触发时按 stop-first。

live runner 要求：

- 入场成交确认后立即放置 reduce-only TP/SL 保护单或等价风控。
- TP/SL 价格必须基于真实 entry fill price 和 entry ATR。
- 若交易所拒绝保护单，必须 fail-closed：撤销/平仓或停止继续加风险。

### Indicator Exit

收盘后维护 MFE：

```text
long_mfe_atr = max(high_since_entry - entry_price) / entry_atr
short_mfe_atr = max(entry_price - low_since_entry) / entry_atr
```

只有当 `mfe_atr < 1.5` 时，indicator exit 才有效：

```text
if mfe_atr < 1.5 and adx28[close_bar] < 22:
    weak_bars += 1
else:
    weak_bars = 0

if weak_bars >= 3:
    pending_exit = indicator_exit
```

`indicator_exit` 在下一根 15m open 执行。MFE 达到 `1.5ATR` 后，indicator exit 永久关闭；这不是 trailing stop，也不是 profit floor。

### Timeout

```text
if bars_held >= 384:
    pending_exit = timeout
```

`timeout` 在下一根 open 执行。当前样本中 `max_hold_bars=384` 触发 0 次，但实盘保留为异常兜底。

### 禁用项

V39 明确禁用：

- profit floor
- trailing stop
- break-even stop
- cooldown
- same-bar re-entry
- post-exit reverse / chain reverse
- V37/V39.1 early-long satellite

## 回测摘要

研究数据湖窗口 `2025-05-30 10:30 UTC` 至 `2026-07-08 05:30 UTC`：

| 版本 | full收益 | full maxDD | Sharpe | 交易数 | 胜率 | 90d收益 | 90d maxDD | 90d胜率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| V35 base | +8360.80% | -23.46% | 4.75 | 108 | 78.70% | +215.41% | -21.90% | 74.29% |
| V39 | +9969.45% | -23.46% | 4.81 | 107 | 79.44% | +217.53% | -21.90% | 77.14% |

标准分片：

| 窗口 | 收益 | maxDD | 交易数 |
| --- | ---: | ---: | ---: |
| 1d | +0.00% | +0.00% | 0 |
| 7d | +9.94% | -14.60% | 3 |
| 1m | +23.40% | -20.11% | 7 |
| 3m | +217.53% | -21.90% | 35 |
| 6m | +1802.57% | -22.58% | 68 |
| 1y | +11342.95% | -23.08% | 104 |
| full | +9969.45% | -23.46% | 107 |

逐边：

| 方向 | 笔数 | 盈利笔数 | 胜率 | 均笔收益 |
| --- | ---: | ---: | ---: | ---: |
| 多单 | 83 | 66 | 79.52% | +4.81% |
| 空单 | 24 | 19 | 79.17% | +5.59% |

## Runner TOML 草案

注意：当前 `quant-runner` 不能解析 `kind = "hype_ema_tb"`。此 TOML 是同事实现 runner kind 后的目标配置草案，默认关闭。

```toml
[[strategies]]
name = "hype-ema-tb-v39-dry-run"
enabled = false
group = "validation"
kind = "hype_ema_tb"
mode = "dry_run"
symbol = "HYPE/USDT:USDT"
timeframe = "15m"
account_id = "dryrun"
state_dir = "/home/admin/quant-runner/state/hype-ema-tb-v39-dry-run"
leverage = 3
margin_mode = "isolated"
warmup_bars = 2500
dry_run_notional_usdt = 10.0
live_confirm = false

# Proposed strategy-specific fields.
# If quant-runner implements strategy params as Rust defaults instead of TOML fields,
# these exact values still belong in HYPE-EMA-TB-V39-SPEC.md and parity tests.
# [strategies.hype_ema_tb]
# strategy_id = "HYPE-EMA-TB-V39"
# entry_delay_bars = 2
# research_warmup_bars = 1600
# ema_fast = 96
# ema_slow = 384
# adx_window = 28
# atr_window = 672
# volume_window = 192
# h1_adx_window = 21
# long_adx_min = 28.0
# short_adx_min = 36.0
# long_vol_min = 0.35
# short_vol_min = 0.50
# h1_long_adx_min = 18.0
# long_use_ema_spread = true
# long_use_h1_di = true
# short_use_ema_spread = true
# short_use_h1_ema = false
# long_target_atr_pct = 0.020
# short_target_atr_pct = 0.022
# max_allocation = 3.0
# take_profit_atr = 5.0
# hard_stop_atr = 7.0
# adx_exit = 22.0
# delayed_bars = 3
# disable_after_mfe_atr = 1.5
# max_hold_bars = 384
# profit_floor_enabled = false
# trailing_stop_enabled = false
# same_bar_priority = "stop_first"
# cooldown_bars = 0
# same_bar_reentry = false
```

## 同事验证清单

### 1. Runner 实现检查

- `StrategyKindName` 增加 `HypeEmaTb`，serde 值为 `hype_ema_tb`。
- `strategies/mod.rs` 注册新 module。
- `StrategyInstanceConfig::strategy_id()` 返回 `HYPE-EMA-TB-V39`。
- `expected_market()` 限定 `HYPE/USDT:USDT` + `15m`。
- `max_live_allocation()` 返回 `3.0`。
- `min_runtime_bars()` 至少 `1600`，建议 `2500`。
- runner-side SPEC 链接回本文档。

### 2. 指标对拍

用同一段 Binance HYPEUSDT `15m` K：

- `ATR672`
- `EMA96`、`EMA384`、`ema_spread`
- `ADX28`、`+DI28`、`-DI28`
- `volume_surge192`
- 1h resample 后 `h1_adx21`、`h1_plus_di21`、`h1_minus_di21`
- `long_signal`、`short_signal`

容差建议：

- 浮点指标最大绝对误差小于 `1e-9` 或解释语言差异。
- 信号布尔序列必须逐 bar 一致。
- 首批 20 笔交易路径必须 entry/exit ts、direction、reason 一致；价格差异只能来自 live fill，不应来自状态机。

### 3. 交易路径对拍

必须对拍：

- K0/K1/K2 入场延迟。
- `entry_atr = ATR672[K1]`。
- `allocation = min(3.0, target_atr_pct / entry_atr_pct)`。
- TP/SL stop-first。
- `mfe_atr >= 1.5` 后关闭 indicator exit。
- `ADX < 22` 连续 3 根后下一根 open 退出。
- `max_hold_bars=384` timeout 兜底。
- 出场后同一根 K 不重入。

### 4. live-executable 审计

V39 若进入 dry-run 或 live 前，必须补：

- 入场 market order 与 reduce-only TP/SL 保护单原子性审计。
- TP/SL 挂单价格 precision、min notional、tick/step size 对齐。
- 保护单拒绝、部分成交、订单取消、连接中断后的 fail-closed 行为。
- 重启恢复：从交易所真实仓位、open orders、local state 重建状态。
- missing-bar / stale candle：停止新开仓，不用补假 K。
- funding 与手续费入账检查。
- DingTalk 或等价告警：入场、出场、保护单失败、数据断流、runner 重启。
- kill switch：手动暂停新开仓、撤保护单、平仓流程。

## 当前不纳入本 spec 的内容

- `HYPE-EMA-TB-V39.1` 的 V37 early-long 卫星。
- `V38` profit floor。
- 2026-07-09 trailing stop 诊断中的任何 trailing 变体。
- `ema_slow=512` 观察项。
- 空头 `fast_adx36_v05` 结构观察项。
- Hyperliquid/OKX 跨所执行版 `V36`。

这些都不是 `HYPE-EMA-TB-V39` live spec 的一部分。

## 证据链接

- 主账：`../hype-ema-tb-core-ledger.md`
- 决策记录：`../decision-log.md`
- 研究侧规格：`../specs/hype-trend-strategy-v39-spec.md`
- V35 全参数消融与 V39 登记：`../notes/hype-ema-tb-v35-full-ablation-recent-tune-2026-07-08.md`
- V39 全参数消融：`../ablations/hype-ema-tb-v39-full-ablation-2026-07-08.md`
- V39 trailing stop 诊断：`../diagnostics/hype-ema-tb-v39-trailing-stop-diagnostic-2026-07-09.md`
- 复现脚本：`../scripts/research_hype_ema_tb_v35_full_ablation_recent_tune.py`
- V39 消融脚本：`../scripts/research_hype_ema_tb_v39_full_ablation.py`

## 最终状态建议

本文完成的是 `registered -> live spec draft` 的规格导出，不代表已通过门禁 0–5 与 live-executable promotion review，也不改变当前 `registered` 状态。

建议状态仍为：

```text
HYPE-EMA-TB-V39: registered / not promoted / not dry-run / not live-ready
```

同事可据此实现 runner 和做 parity validation；只有 runner 实现、对拍、门禁与 live-executable 审计补齐后，才允许讨论 dry-run 或 live。
