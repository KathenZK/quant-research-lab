---
schema_version: "1.0"
spec_role: lab_handoff
strategy_id: HYPE-5M-PBTR-V6.2.1
family_id: HYPE-5M-PBTR
main_status: live
runner_kind: hype_pullback
spec_status: active
peer_spec: crates/quant-runner/src/runner/strategies/hype_pullback/HYPE-5M-PBTR-V6.2.1-SPEC.md
approval_level_max: tiny_live_pilot
---

# HYPE-5M-PBTR-V6.2.1 实盘复现规格

规格 id：`HYPE-5M-PBTR-V6.2.1-LIVE-SPEC`

Family id：`HYPE-5M-PBTR`

状态：`live / tiny-live-pilot`，并行保留独立 `dry-run` 实例。tiny-live-pilot 授权截至 `2026-12-24T00:00:00Z` 复核；本文档用于完整复现策略与核对订单行为，不是生产 sizing 或扩资批准。

创建时间：2026-06-30

## 目标

本文档把 `HYPE-5M-PBTR-V6.2.1` 的全部可执行参数、信号时序、订单规则、回测口径和实盘审计要求写成单一规格。实现者不应从旧 `V2/V3/V4` live spec 继承 delayed trailing、`min_hold_bars` 或 stale stop-price 成交逻辑。

核心机制：

```text
Binance HYPEUSDT 永续 5m 已收盘 K
-> 计算 EMA/ATR/HTF spread/方向收益
-> long leg 与 short leg 分别产生 pullback-reclaim 信号
-> 对信号做方向收益质量过滤
-> 组合层严格单仓，同一信号 K 多空冲突时 long 优先
-> 信号 K 收盘后，下一根 5m K open 入场
-> 入场后立即存在固定 TP/SL bracket
-> TP/SL 或 timeout open 退出
```

## 统一 execution / venue 契约（2026-07-12 代码迁移）

本节只同步 `quant-runner` 执行架构，不修改 V6.2.1 的信号、参数、固定 bracket、
timeout、成本假设或状态：

- dry-run 与 live 必须走同一 execution 状态机：稳定 client ID、submit 前先持久化
  order intent、`pending/tracked` 恢复、按实际 fill 建仓、TP/SL 保护单、兄弟单撤销、
  timeout exit、reconcile、fail-closed 与 platform ledger。
- `mode=live` 的 venue 是 Binance REST + User Data Stream；stream 丢失或事件缺口由
  REST 对账补齐，对账不干净时禁止新增风险。
- `mode=dry_run` 的 venue 是独立持久化模拟交易所，状态文件固定落在实例目录下的
  `simulated_venue.json`（即 `state/<instance>/simulated_venue.json`）。模拟 entry、
  fill、保护单、撤单与 exit 也必须走完整订单生命周期，不能直接改策略 position。
- `platform.execution.enabled` 已删除；live V1 fallback 已删除。不得通过旧开关或旧
  executor 绕开本契约。
- 新配置与旧二进制不组成可运行回滚对；live 发布必须 flat/无挂单/无 open trade，
  先停止 service，再同步配置和匹配 artifact。失败后保持停止，只允许 forward fix
  或 `origin/main` revert commit + 匹配 artifact，禁止 binary-only rollback。
- execution pause 只能通过先拿 runner lock、再完成 venue/local/protection reconcile
  的 `risk-resume` 清除；禁止直接编辑状态 JSON。
- strict replay/parity 继续使用隔离路径，不读取或改写 simulated/live venue 状态；
  execution 迁移本身不得改变既有 parity 结论。
- 统一 execution 已于 `2026-07-13T04:25Z` 随 dry-run/live 双服务切换部署；
  live 发布前后均 reconcile=`match` 且 flat，没有新增 PBTR fill。promotion、
  parity 与 live-readiness 状态全部不变。
- 运行稳定性补充契约（Runner `e69589f`，已于 `2026-07-13 21:03 CST`
  部署 live）：Binance transient timeout、
  429、5xx 或短暂 user-stream 断开必须关闭新开仓闸并重试，但不能退出进程或停止
  已有持仓的撤单、保护、reconcile 与平仓；只有 clean snapshot 确认 mismatch
  才进入持久 fail-closed，仍需 `risk-resume`。订单 POST 继续禁止盲重试。
- 2026-07-14 Runner workspace 已把 `hype_pullback` 迁入通用
  `StrategyDriver -> TargetPosition -> execution kernel`（尚未部署）。Driver
  输出信号 K `ATR14` 的绝对 TP/SL 距离，execution kernel 必须在真实 entry fill
  后加减该固定距离；不得按 decide 参考价换算百分比，以免改变 V6.2.1 bracket。
- 中心 `RuntimeModel` 已删除，Driver factory 由 `catalog.rs` 注册。此代码迁移
  不改变 signal、next-open、TOML、state path、allocation、费用、滑点、timeout、
  live notional 或恢复语义，也不构成增资、promotion 或 parity 结论。

实现状态见
[2026-07-11 runner tracking（含 2026-07-12 未部署迁移补记）](../runner-tracking/hype-5m-pbtr-runner-2026-07-11.md)。

## 策略身份

| 字段 | 值 |
| --- | --- |
| Canonical name | `HYPE-5M-PBTR-V6.2.1` |
| 来源 | V6.2 full parameter ablation 的 `long_htf_threshold_0p0` |
| 交易所 | Binance USD-M Futures |
| 合约 | `HYPEUSDT` perpetual，CCXT 风格 `HYPE/USDT:USDT` |
| 时间级别 | `5m` |
| K 线时间 | UTC，`ts` 表示该 5m K 的开盘时间 |
| 持仓模型 | 同一时间只允许一个策略持仓，不加仓，不反手 |
| 回测横向比较杠杆 | fixed `3x` |
| 实盘建议杠杆 | `1x` 或极小 notional，直到订单审计通过 |
| 信号时序 | 第 `t` 根 K 收盘确认信号，最早第 `t+1` 根 open 入场 |
| 出口模型 | 入场即固定 TP/SL + time exit |
| trailing stop | 禁用，`trail_atr=0.0` |
| min hold | 无，入场 K 起 bracket 即有效 |

## 成本口径

研究回放使用观察到的 live-cost 常数：

| 成本项 | 值 |
| --- | ---: |
| `FEE_RATE_PER_FILL` | `3.0578 / 7374.2110 = 0.0004146` |
| `ENTRY_SLIPPAGE_RATE` | `10.73 bps = 0.001073` |
| `EXIT_SLIPPAGE_RATE` | `-2.64 bps = -0.000264` |

回测价格：

```text
entry_price = open[entry_i] * (1 + side * ENTRY_SLIPPAGE_RATE)
exit_price = raw_exit_price * (1 - side * EXIT_SLIPPAGE_RATE)
net_ret_1x = side * (exit_price / entry_price - 1) - FEE_RATE_PER_FILL * (1 + exit_price / entry_price)
net_ret_3x = net_ret_1x * 3
```

其中：

```text
side = +1 表示 long
side = -1 表示 short
```

实盘 PnL 必须使用真实成交价和真实手续费。上述常数只用于研究复现和回测验收。

## 数据要求

输入 K 线至少包含：

```text
ts, open, high, low, close, volume, quote_volume, trade_count
```

硬要求：

- 只使用已收盘 5m K 线。
- `ts` 必须是 UTC，严格 `5min` 连续递增。
- 重复 `ts` 必须去重，保留最新一行。
- 缺失 K、非法 OHLC、关键字段空值时停止生成新信号。
- 不允许用未闭合 K 更新 EMA、ATR、HTF spread、信号、TP/SL 或 timeout。
- 实盘启动建议预加载至少 `2000` 根已收盘 K；为完全复现研究结果，应加载本地完整 HYPE 5m 历史。

数据质量审计基准：

```text
2026-06-30 审计数据范围：2025-05-30T10:30:00Z -> 2026-06-30T06:15:00Z
rows = 113998
missing_bars = 0
duplicate_ts = 0
invalid_ohlc = 0
critical_nulls = 0
```

## 指标定义

所有指标都在已收盘 K 上计算。

### EMA

使用 pandas 兼容语义：

```text
EMA(span) = close.ewm(span=span, adjust=false, min_periods=span).mean()
```

V6.2.1 必需周期：

```text
EMA21, EMA34, EMA55, EMA96, EMA144, EMA384
```

### True Range 与 ATR14

```text
prev_close = close.shift(1)
TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
ATR14 = rolling_mean(TR, window=14, min_periods=14)
```

### HTF Spread

这里的 HTF 不是重采样 1h K，而是 5m 序列上的慢 EMA 价差：

```text
htf_spread = EMA96 - EMA384
```

### Directional Return

```text
ret48 = close / close.shift(48) - 1
ret192 = close / close.shift(192) - 1
```

对某个信号方向：

```text
dir_ret48_bps = side * ret48 * 10000
dir_ret192_bps = side * ret192 * 10000
```

这些都是历史收益，不是未来收益。

## Leg 参数

### Long Leg

| 参数 | 值 |
| --- | ---: |
| `enabled` | `true` |
| `side` | `long` |
| `ema_fast` | `21` |
| `ema_slow` | `55` |
| `pullback_buffer` | `0.01` |
| `require_candle` | `false` |
| `htf_threshold` | `0.0` |
| `quality_window` | `192` |
| `quality_threshold` | `788.123` |
| `tp_atr` | `2.5` |
| `sl_atr` | `7.0` |
| `trail_atr` | `0.0` |
| `time_exit_bars` | `36` |

Long signal on closed bar `i`:

```text
direction = +1 if EMA21[i] - EMA55[i] > 0 else 0
touched = low[i] <= EMA21[i] * (1 + 0.01)
reclaimed = close[i] > EMA21[i]
htf_ok = EMA96[i] - EMA384[i] >= 0.0
quality_ok = ret192[i] * 10000 >= 788.123
long_signal[i] = +1 if direction and touched and reclaimed and finite(ATR14[i]) and htf_ok and quality_ok
```

`require_candle=false`，所以 long 不要求 `close > open`。

### Short Leg

| 参数 | 值 |
| --- | ---: |
| `enabled` | `true` |
| `side` | `short` |
| `ema_fast` | `34` |
| `ema_slow` | `144` |
| `pullback_buffer` | `0.0` |
| `require_candle` | `false` |
| `htf_threshold` | `null` |
| `quality_window` | `48` |
| `quality_threshold` | `400.0` |
| `tp_atr` | `1.5` |
| `sl_atr` | `2.0` |
| `trail_atr` | `0.0` |
| `time_exit_bars` | `48` |

Short signal on closed bar `i`:

```text
direction = -1 if EMA34[i] - EMA144[i] < 0 else 0
touched = high[i] >= EMA34[i] * (1 - 0.0)
reclaimed = close[i] < EMA34[i]
htf_ok = true
quality_ok = (-1) * ret48[i] * 10000 >= 400.0
short_signal[i] = -1 if direction and touched and reclaimed and finite(ATR14[i]) and quality_ok
```

`require_candle=false`，所以 short 不要求 `close < open`。

## 相邻信号抑制

每个 leg 在两处执行同方向相邻信号抑制：

1. raw signal 构造后。
2. quality filter 应用后。

精确规则：

```text
if signal[i] != 0 and signal[i] == signal[i - 1]:
    signal[i] = 0
```

这个规则只抑制紧邻上一根 K 的同方向信号。中间隔着一根或多根 `0` 的同方向信号不会被抑制。

## 组合层规则

组合参数：

| 参数 | 值 |
| --- | --- |
| `priority` | `long_first` |
| `one_position_only` | `true` |
| `cooldown_bars` | `0` |

构造事件：

```text
events = all nonzero long_signal and short_signal
sort by (signal_i, priority)
priority long_first means same signal_i: long before short
```

回放/实盘单仓规则：

```text
blocked_until = -1
for event in events:
    entry_i = signal_i + 1
    if entry_i <= blocked_until:
        skip signal
    else:
        open trade and hold until exit_i
        blocked_until = exit_i
```

实盘等价：

- 任何本策略持仓或未完成入场单存在时，不处理新信号。
- 不加仓，不反手。
- 持仓完全关闭、交易所持仓和本地状态对齐后，才允许处理后续新信号。

## 入场执行

信号 bar：`K0 = bar[signal_i]`

入场 bar：`K1 = bar[signal_i + 1]`

回测：

```text
entry_i = signal_i + 1
entry_price = open[entry_i] * (1 + side * ENTRY_SLIPPAGE_RATE)
signal_atr = ATR14[signal_i]
```

实盘：

- `K0` 确认收盘后立即提交市价单或激进限价单。
- 使用真实成交均价作为 `entry_price`。
- 若入场订单没有在预期时间内成交，取消订单并记录 missed signal。
- 入场幂等 key 建议：`HYPE-5M-PBTR-V6.2.1:{signal_ts}:{side}:entry`。

## Bracket 价格

入场成交后立即计算并提交 reduce-only TP/SL：

```text
target_price = entry_price + side * tp_atr * signal_atr
stop_price = entry_price - side * sl_atr * signal_atr
```

Long:

```text
target = entry_price + 2.5 * ATR14[signal_i]
stop = entry_price - 7.0 * ATR14[signal_i]
timeout = 36 bars
```

Short:

```text
target = entry_price - 1.5 * ATR14[signal_i]
stop = entry_price + 2.0 * ATR14[signal_i]
timeout = 48 bars
```

订单建议：

- TP 使用 reduce-only limit order。
- SL 使用 reduce-only stop-market order。
- 两张订单必须带本地 OCO 关系。任一侧成交后，立即取消另一侧。
- 若交易所原生 bracket/OCO 不可靠，必须由策略进程维护并在重启后恢复。
- 如果入场后 bracket 下单失败，不得继续开新仓；应立即尝试补挂保护单或触发人工/风控处理。

## 回测退出优先级

对每笔交易，从 `entry_i` 开始逐根扫描到 `entry_i + time_exit_bars`，包含端点。

每根 bar 的判断顺序必须精确如下：

```text
1. 如果 open 已穿越 stop：
   raw_exit_price = open[bar_i]
   reason = "stop_gap_open"
   exit

2. 如果 open 已穿越 target：
   raw_exit_price = target_price
   reason = "target_gap_or_open"
   exit

3. 如果 bar_i == entry_i + time_exit_bars：
   raw_exit_price = open[bar_i]
   reason = "time_open"
   exit

4. 计算 high/low 是否触及 stop 与 target。

5. 如果同一根 K 同时触及 stop 与 target：
   raw_exit_price = stop_price
   reason = "both_hit_stop_first"
   exit

6. 如果只触及 stop：
   raw_exit_price = stop_price
   reason = "stop_market"
   exit

7. 如果只触及 target：
   raw_exit_price = target_price
   reason = "target"
   exit
```

触发函数：

```text
long stop touched: low <= stop_price
long target touched: high >= target_price
long stop crossed at open: open <= stop_price
long target crossed at open: open >= target_price

short stop touched: high >= stop_price
short target touched: low <= target_price
short stop crossed at open: open >= stop_price
short target crossed at open: open <= target_price
```

`bars_held`：

```text
bars_held = exit_i - entry_i + 1
```

注意：timeout 是 `time_exit_bars` 之后那根 bar 的 open 平仓。例如 long `time_exit_bars=36`，从 `entry_i` 开始，若没有 TP/SL，计划在 `entry_i + 36` 的 open 平仓。

## 实盘 Timeout

实盘必须为每笔持仓设置计划 timeout：

```text
timeout_at = entry_bar_open_ts + time_exit_bars * 5 minutes
```

到达 `timeout_at` 时：

1. 对账当前持仓。
2. 取消未成交 TP/SL 或至少标记为即将撤销。
3. 发送 reduce-only market close。
4. 成交后取消所有残留 reduce-only exit orders。
5. 记录 `reason = time_open` 或实盘等价原因。

如果系统只在 K 收盘回调里运行，会比研究回测晚一根 K，不能视为完全复现。

## 状态持久化字段

每次信号、订单和成交事件都应 append-only 记录。最少字段：

```text
strategy_id = HYPE-5M-PBTR-V6.2.1
symbol = HYPEUSDT
timeframe = 5m
mode = dry_run | live
signal_ts
signal_i_or_ts
side
source_leg = long | short
ema_fast
ema_slow
pullback_buffer
htf_threshold
quality_window
quality_threshold
signal_atr14
ret48
ret192
dir_ret48_bps
dir_ret192_bps
htf_spread
entry_order_id
entry_order_type
entry_submit_ts
entry_fill_ts
entry_price
entry_qty
target_price
stop_price
target_order_id
stop_order_id
timeout_at
exit_order_id
exit_ts
exit_price
exit_reason
gross_ret
fee
net_ret
cancel_target_ts
cancel_stop_ts
position_before
position_after
last_processed_closed_candle_ts
blocked_until_ts
reconcile_status
error_code
raw_exchange_response
```

Runner 配置 `mode` 只有 `dry_run | live` 两态。tiny-live-pilot 由 lock `approval_level=tiny_live_pilot` 与 `approval_expires_at` 表达，不是第三种 mode。

幂等 key：

```text
entry_key = "HYPE-5M-PBTR-V6.2.1:{signal_ts}:{side}:entry"
target_key = "HYPE-5M-PBTR-V6.2.1:{entry_fill_ts}:{side}:target:{target_price}"
stop_key = "HYPE-5M-PBTR-V6.2.1:{entry_fill_ts}:{side}:stop:{stop_price}"
timeout_key = "HYPE-5M-PBTR-V6.2.1:{entry_fill_ts}:{side}:timeout"
```

## 重启恢复

进程启动时：

1. 读取本地持久化状态。
2. 获取 Binance 当前 `HYPEUSDT` 持仓。
3. 获取所有未成交订单。
4. 若交易所空仓但本地有持仓，标记本地持仓为外部关闭，并取消残留 exit orders。
5. 若交易所有仓但本地无仓，停止开新仓并要求人工对账。
6. 若交易所和本地都有同一持仓，重建 TP/SL/timeout 状态。
7. 若 TP 或 SL 缺失，立即补挂 reduce-only exit order。
8. 若 TP/SL 数量多于一组，停止交易并人工清理。
9. 对账干净前不得处理新信号。

## 实盘主循环

```text
while service_running:
    wait until latest Binance 5m candle is confirmed closed
    fetch candles through latest closed candle
    validate data continuity and OHLC fields
    compute EMA/ATR/HTF/ret features on closed candles
    reconcile exchange position and local state

    if position is open:
        check whether target/stop/timeout already handled by exchange or scheduler
        repair missing reduce-only exit orders if needed
        persist audit state
        continue

    if any stale entry/exit order exists:
        cancel or reconcile it
        do not open a new trade in the same loop unless state is clean

    compute latest long_signal and short_signal
    choose event by long_first priority if both exist
    if no signal:
        persist last_processed_closed_candle_ts
        continue

    if signal_ts already processed:
        continue

    submit entry order
    if filled:
        compute target/stop from actual fill and ATR14[signal_i]
        submit reduce-only TP and SL immediately
        schedule timeout_at
        persist full state
    else:
        cancel stale entry order
        record missed signal
```

## 参考伪代码

```text
function build_leg_signal(frame, leg):
    ema_fast = EMA(leg.ema_fast)
    ema_slow = EMA(leg.ema_slow)
    atr14 = ATR14
    spread = ema_fast - ema_slow

    if leg.side == "long":
        direction = +1 where spread > 0 else 0
        touched = low <= ema_fast * (1 + leg.pullback_buffer)
        reclaimed = close > ema_fast
    else:
        direction = -1 where spread < 0 else 0
        touched = high >= ema_fast * (1 - leg.pullback_buffer)
        reclaimed = close < ema_fast

    signal = direction where direction != 0 and touched and reclaimed and finite(atr14)

    if leg.htf_threshold is not null:
        htf_ok = direction * (EMA96 - EMA384) >= leg.htf_threshold
        signal = signal where htf_ok else 0

    signal = suppress_adjacent_same_direction(signal)

    if leg.quality_window is not null:
        ret = close / close.shift(leg.quality_window) - 1
        quality = signal * ret * 10000 >= leg.quality_threshold
        signal = signal where quality else 0
        signal = suppress_adjacent_same_direction(signal)

    return signal
```

```text
function simulate_or_manage_trade(signal_i, side, leg):
    entry_i = signal_i + 1
    signal_atr = ATR14[signal_i]
    entry_price = open[entry_i] * (1 + side * ENTRY_SLIPPAGE_RATE)
    target = entry_price + side * leg.tp_atr * signal_atr
    stop = entry_price - side * leg.sl_atr * signal_atr

    for bar_i in range(entry_i, entry_i + leg.time_exit_bars + 1):
        if crossed_stop(open[bar_i], stop, side):
            exit(open[bar_i], "stop_gap_open")
        if crossed_target(open[bar_i], target, side):
            exit(target, "target_gap_or_open")
        if bar_i == entry_i + leg.time_exit_bars:
            exit(open[bar_i], "time_open")

        stop_hit = touched_stop(high[bar_i], low[bar_i], stop, side)
        target_hit = touched_target(high[bar_i], low[bar_i], target, side)
        if stop_hit and target_hit:
            exit(stop, "both_hit_stop_first")
        if stop_hit:
            exit(stop, "stop_market")
        if target_hit:
            exit(target, "target")
```

## 回归验收数值

### 2026-06-29 全参数消融口径

使用 `research_hype_5m_pbtr_v6_2_1_full_ablation.py` 当日输出：

| 指标 | 期望 |
| --- | ---: |
| trades | `219` |
| total return fixed 3x | `+1022.25%` |
| PF | `1.804` |
| win rate | `64.38%` |
| payoff | `0.998` |
| max DD | `-22.35%` |
| OOS trades / PF | `15 / 1.439` |
| short trades / PF | `53 / 1.764` |

### 2026-06-30 实盘可行性审计口径

使用已闭合数据到 `2026-06-30T06:15Z`：

| 口径 | trades | total | PF | DD | reason counts |
| --- | ---: | ---: | ---: | ---: | --- |
| baseline stop-first | `220` | `+1054.07%` | `1.813` | `-22.35%` | `target=129, time_open=72, stop_market=19` |
| bracket delay 1 bar | `220` | `+1030.87%` | `1.803` | `-23.73%` | `target=128, time_open=72, stop_market=17, stop_gap_open=2, target_gap_or_open=1` |

附加验收：

```text
feature causality checks = 91
feature causality failures = 0
same-bar TP/SL both-hit count = 0
baseline stop/target open-gap exits = 0
entry-bar bracket touched = 3
```

如果实现使用同一份 K 线和同一成本口径却不能接近上述数值，不得交给实盘。

## 实盘审计 Gate

允许行为：

- `dry_run`
- `paper`
- `tiny-notional live audit`

不允许行为：

- 直接生产 sizing。
- 使用 fixed `3x` 真实仓位。
- 忽略 bracket 下单失败继续开仓。
- 使用未闭合 K 信号。
- 用旧 V2/V3/V4 delayed trailing 或 min-hold 逻辑替换本策略。

至少累计 `30-50` 笔订单审计后再评估：

```text
signal_ts 与本地重算一致
entry fill 与预期 K1 open 偏差可解释
TP/SL 在 entry fill 后立即存在
单边成交后另一边能可靠取消
timeout market close 按计划触发
重启后能恢复持仓和 exit orders
实际手续费/滑点没有系统性超出预期
SQLite 或审计日志可完整复盘每笔交易
```

暂停条件：

```text
出现任何未保护持仓
出现任何无法解释的多仓/反手/加仓
bracket 下单或撤单连续失败
本地状态与交易所状态无法自动对齐
K 线缺口或未闭合 K 被用于信号
```

## 参考材料

- 主账：`../hype-5m-pullback-trail-core-ledger.md`
- 全参数消融：`../ablations/hype-5m-pbtr-v6-2-1-full-parameter-ablation-2026-06-29.md`
- 实盘可行性审计：`../diagnostics/hype-5m-pbtr-v6-2-1-live-feasibility-audit-2026-06-30.md`
- V6.2.1 ablation script：`../scripts/research_hype_5m_pbtr_v6_2_1_full_ablation.py`
- V6.2.1 feasibility audit script：`../scripts/research_hype_5m_pbtr_v6_2_1_live_feasibility_audit.py`
- V6.2 base ablation script：`../scripts/research_hype_5m_pbtr_v6_2_full_ablation.py`
- V6 executable search source：`../scripts/research_hype_5m_pbtr_v6_live_executable_search.py`

## Runner 实现绑定（2026-07-14，未部署）

当前 quant-runner 实现为 `StrategyDriver -> TargetPosition -> execution kernel`。
Driver 声明 `5m HYPE` 行情依赖和 ATR14 绝对保护距离；执行核在实际 fill 后解析
TP/SL，并统一处理 stable client ID、订单持久化、reconcile 与通知。策略模块通过
`inventory` 自注册，不存在 PBTR runtime 分支。此实现变更不修改本规格参数、
tiny-live-pilot 边界或 promotion 结论；部署前仍需按本文件执行验收。
非零新仓 target 只能 `NextOpen`；任何 side/symbol/allocation 替换都必须使用
persisted `AfterFlat`，不提供隐式仓内 resize。
