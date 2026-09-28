---
schema_version: "1.0"
spec_role: external_reproduction
family_id: HYPE-1D-MA7-ABT
strategy_id: HYPE-1D-MA7-ABT-V7.1
spec_status: active
document_type: external_reproduction_spec
intended_audience: "同事及其AI；假设只拿到本文档，没有本地仓库、脚本、artifact或历史报告"
version: HYPE-1D-MA7-ABT-V7.1
status: "registered / not promoted / not live-ready"
approval_level_max: none
created_utc: "2026-08-11"
---

# HYPE-1D-MA7-Asymmetric-Body-Trend V7.1 外部复现规格

本文是自包含复现规格。读者只需要本文档即可实现独立回测或 runner 原型；不要依赖任何本地文件、仓库脚本、artifact、主账或内部路径。

状态口径：`HYPE-1D-MA7-ABT-V7.1` 是已登记研究版本，但不是 live-ready，不构成 dry-run/live 授权。若用于小额真实资金观察，必须先完成独立实现、离线逐笔对拍、线上开平仓对账、资金边界和 kill switch。

## 版本身份

| 字段 | 值 |
| --- | --- |
| Full name | `HYPE-1D-MA7-Asymmetric-Body-Trend-V7.1` |
| Alias | `HYPE-1D-MA7-ABT-V7.1` |
| Market | Binance USD-M Futures |
| Symbol | `HYPEUSDT` perpetual；CCXT symbol 可写作 `HYPE/USDT:USDT` |
| Main timeframe | UTC `1d` closed bars |
| Intraday replay timeframe | UTC `1h` bars |
| Default exposure | fixed target `1x` account equity per entry |
| Portfolio rule | one symbol, one position, no pyramiding |
| Position sides | long and short |
| Version relation | V7.1 与 V7 交易路径完全相同，只删除 dormant/schema-only 参数 |

## 数据要求

使用 Binance USD-M futures 公共数据或等价数据源。最小字段如下。

Daily `1d` candles:

| Field | Meaning |
| --- | --- |
| `open_time` | UTC candle open timestamp in milliseconds or ISO time |
| `open` | candle open |
| `high` | candle high |
| `low` | candle low |
| `close` | candle close |
| `volume` | base volume；本策略不使用，但建议保留 |
| `close_time` | UTC candle close timestamp |

Hourly `1h` candles:

| Field | Meaning |
| --- | --- |
| `open_time`, `open`, `high`, `low`, `close`, `close_time` | 用于 intraday stop / trailing / drawdown replay |

Funding:

| Field | Meaning |
| --- | --- |
| `funding_time` | Binance funding timestamp |
| `funding_rate` | funding rate charged/received during the position |

Public API examples:

- Daily/Hourly klines: Binance USD-M futures `/fapi/v1/klines` with `symbol=HYPEUSDT`, `interval=1d` or `1h`.
- Funding history: Binance USD-M futures `/fapi/v1/fundingRate` with `symbol=HYPEUSDT`.

Backtest acceptance window:

| Field | Value |
| --- | --- |
| Start | `2025-05-31T00:00:00+00:00` |
| End | `2026-08-06T00:00:00+00:00` |
| Daily bars | `432` |
| Warmup | At least `30` complete daily bars before first signal decision |

Data quality gates:

- All signal decisions must use only closed daily bars. Never use same-day incomplete high/low/close for entry signals.
- Daily bar timestamps must be strictly increasing UTC opens with no duplicates.
- OHLC must satisfy `low <= open <= high` and `low <= close <= high`.
- Missing daily bars invalidate new entries until data is repaired.
- Hourly bars must cover any open position interval. Missing hourly data invalidates stop/trailing replay for that interval.
- Funding accrues only while a position is open, using the exchange funding timestamps.

## Cost Model

Use these costs by default:

| Cost | Value |
| --- | ---: |
| Fee | `0.001` of filled notional per fill |
| Slippage | `0.0004` adverse per fill |
| Stress slippage | `0.0008` adverse per fill |
| Funding | Real Binance funding rate, charged/received by position side |

For long fills:

- Entry fill = reference open price * `(1 + slippage)`.
- Exit fill = reference exit price * `(1 - slippage)`.

For short fills:

- Entry fill = reference open price * `(1 - slippage)`.
- Exit fill = reference exit price * `(1 + slippage)`.

Fees are paid on both entry and exit notional. Funding is included in headline acceptance metrics.

## Indicators

All indicators below are computed from closed daily bars unless explicitly stated.

### SMA7

`SMA7[t] = mean(close[t-6], close[t-5], ..., close[t])`

Use `min_periods=7`. Before `SMA7` exists, no signal is allowed.

### ATR7

True range:

```text
TR[t] = max(
  high[t] - low[t],
  abs(high[t] - close[t-1]),
  abs(low[t] - close[t-1])
)
```

`ATR7[t] = mean(TR[t-6], ..., TR[t])`

Use `min_periods=7`. ATR is used for slope thresholds, MA distance buffers, hard stops and trailing references.

### RSI6

Use Wilder RSI with length `6`.

```text
delta[t] = close[t] - close[t-1]
gain[t] = max(delta[t], 0)
loss[t] = max(-delta[t], 0)
avg_gain[t] = Wilder_RMA(gain, length=6)
avg_loss[t] = Wilder_RMA(loss, length=6)
RS[t] = avg_gain[t] / avg_loss[t]
RSI6[t] = 100 - 100 / (1 + RS[t])
```

Wilder RMA after initialization:

```text
RMA[t] = (RMA[t-1] * (length - 1) + value[t]) / length
```

Use the first simple average over 6 values as initialization. If `avg_loss=0` and `avg_gain>0`, RSI is `100`; if both are zero, RSI is neutral `50`.

## Frozen Parameters

```json
{
  "risk": {
    "target_leverage": 1.0,
    "allow_pyramiding": false
  },
  "indicators": {
    "ma_kind": "sma",
    "ma_length": 7,
    "atr_length": 7,
    "rsi_length": 6
  },
  "long": {
    "side": 1,
    "entry_mode": "reclaim",
    "slope_lookback": 1,
    "slope_min_atr": 0.02,
    "confirm_days": 1,
    "entry_buffer_atr": 0.0,
    "exit_confirm_days": 1,
    "exit_buffer_atr": 0.75,
    "trail_atr": 1.5,
    "max_hold_days": 90,
    "cooldown_days": 2
  },
  "short": {
    "side": -1,
    "entry_mode": "reclaim",
    "slope_lookback": 2,
    "slope_min_atr": 0.02,
    "confirm_days": 1,
    "entry_buffer_atr": 0.1,
    "exit_confirm_days": 1,
    "exit_buffer_atr": 0.75,
    "slope_exit_lookback": 1,
    "hard_stop_atr": 1.5,
    "trail_atr": 4.0,
    "max_hold_days": 20,
    "cooldown_days": 3
  },
  "oapp": {
    "arm_id": "V6_OAPP",
    "entry": {
      "kind": "off"
    },
    "long_exit": {
      "mode": "fraction",
      "activation_atr": 0.5,
      "giveback": 0.1,
      "confirm_days": 2
    },
    "short_exit": {
      "mode": "off"
    },
    "short_rsi": {
      "threshold": 20.0,
      "days": 2
    },
    "roundtrip_guard": 0.0028
  },
  "pehc": {
    "arm_id": "PEHC_294",
    "enabled": true,
    "entry_enabled": true,
    "expiry_days": 8,
    "slope_threshold": null,
    "chase_cap_atr": "INF",
    "execution": "next_utc_open"
  }
}
```

## Entry Logic

Evaluate entries only when flat and after applying same-side cooldowns. A cooldown decrements once per daily bar after an exit. Same-side entry is blocked while that side's cooldown is positive. Opposite-side entries are not blocked by the exited side's cooldown.

Long native entry at daily bar `t`:

```text
long_reclaim =
  close[t-1] <= SMA7[t-1]
  and close[t] > SMA7[t] + long.entry_buffer_atr * ATR7[t]

long_slope =
  SMA7[t] - SMA7[t - long.slope_lookback]
  >= long.slope_min_atr * ATR7[t]

long_entry_signal[t] =
  long_reclaim
  and long_slope
  and indicators_are_available
  and long_cooldown_left == 0
```

Short native entry at daily bar `t`:

```text
short_reclaim =
  close[t-1] >= SMA7[t-1]
  and close[t] < SMA7[t] - short.entry_buffer_atr * ATR7[t]

short_slope =
  SMA7[t] - SMA7[t - short.slope_lookback]
  <= -short.slope_min_atr * ATR7[t]

short_entry_signal[t] =
  short_reclaim
  and short_slope
  and indicators_are_available
  and short_cooldown_left == 0
```

Execution timing:

- Signal is decided after the daily bar `t` is closed.
- Native entry is filled at the next UTC daily open, bar `t+1`.
- Fill price includes adverse slippage and fee.
- Position size targets `1.0 * account_equity` notional at entry.

## Exit Logic

Exit checks run while a position is open. When multiple exit reasons occur at the same timestamp, use the earliest timestamp. If multiple daily-close reasons occur on the same daily bar, prefer protective/trailing state first, then OAPP, then side-specific MA exit, then max-hold.

### Common Position State

Persist at minimum:

- side: `+1` long or `-1` short;
- entry timestamp and entry price;
- quantity;
- bars held;
- highest close since entry for long trailing/OAPP;
- lowest close since entry for short trailing reference;
- MFE since entry;
- cooldown counters;
- PEHC shadow state, if any.

### Long Exits

Long MA hysteresis exit:

```text
long_ma_exit[t] =
  close[t] < SMA7[t] - long.exit_buffer_atr * ATR7[t]
```

Because `long.exit_confirm_days = 1`, one closed daily bar is enough. Fill at next UTC daily open.

Long trailing protection:

```text
long_trailing_stop[t] =
  max_close_since_entry - long.trail_atr * ATR7[t]
```

Use hourly bars to detect intraday stop touch after the stop reference is known. If hourly `low <= stop_price`, exit at the stop price with adverse slippage and fee.

Long OAPP profit protection:

```text
long_mfe_price = max_close_since_entry - entry_price
long_activation = long_mfe_price >= oapp.long_exit.activation_atr * ATR7[t]
long_giveback_fraction =
  (max_close_since_entry - close[t]) / max(max_close_since_entry - entry_price, small_number)

long_oapp_condition[t] =
  long_activation
  and long_giveback_fraction >= oapp.long_exit.giveback
  and estimated_roundtrip_return >= oapp.roundtrip_guard
```

Because `oapp.long_exit.confirm_days = 2`, require two consecutive closed daily bars satisfying the OAPP condition. Fill at next UTC daily open. In historical trade labels this reason is `long_mfe_fraction_trail_exit`.

Long max-hold exit:

```text
bars_held >= long.max_hold_days
```

Fill at next UTC daily open.

### Short Exits

Short MA hysteresis exit:

```text
short_ma_exit[t] =
  close[t] > SMA7[t] + short.exit_buffer_atr * ATR7[t]
```

Because `short.exit_confirm_days = 1`, one closed daily bar is enough. Fill at next UTC daily open.

Short slope exit:

```text
short_slope_exit[t] =
  SMA7[t] - SMA7[t - short.slope_exit_lookback] >= 0
```

With `short.slope_exit_lookback = 1`, a short may exit when the one-day MA7 down-slope disappears. Fill at next UTC daily open. In historical trade labels this reason is `ma7_slope_exit`.

Short hard stop:

```text
short_hard_stop = entry_price + short.hard_stop_atr * ATR7_at_entry
```

Use hourly bars to detect intraday touch. If hourly `high >= short_hard_stop`, exit at stop price with adverse slippage and fee. Historical V7.1 did not rely on this as a dominant exit, but it is retained as risk protection.

Short trailing protection:

```text
short_trailing_stop[t] =
  min_close_since_entry + short.trail_atr * ATR7[t]
```

Use hourly bars to detect intraday touch. If hourly `high >= stop_price`, exit at stop price with adverse slippage and fee.

Short RSI take-profit:

```text
short_rsi_condition[t] =
  RSI6[t] <= oapp.short_rsi.threshold
  and RSI6[t-1] <= oapp.short_rsi.threshold
  and estimated_roundtrip_return >= oapp.roundtrip_guard
```

Because `oapp.short_rsi.days = 2`, require two consecutive closed daily RSI6 values at or below `20`. Fill at next UTC daily open. Historical label: `short_rsi_take_profit`.

Short max-hold exit:

```text
bars_held >= short.max_hold_days
```

Fill at next UTC daily open. Historical label: `max_hold`.

## PEHC Handoff Logic

PEHC means Profit-Exit Handoff Continuity. It is a state handoff overlay, not a separate alpha model.

In V7.1, PEHC is enabled and materially creates short entries after an exited long trend leaves a virtual continuation state. It does not pyramid and does not open a same-direction top-up.

State model:

1. When a long exits by profit/trailing/protective logic and the account is flat, create a virtual long shadow with origin timestamp, prior entry price, highest close, stop reference and expiry counter.
2. Track that virtual long for up to `8` daily bars.
3. If the virtual long's stop is hit while the actual account remains flat, test a short handoff opportunity.
4. Handoff requires:
   - account is flat;
   - PEHC has not expired;
   - short-side MA location passes at the recheck point;
   - no finite chase cap blocks the trade, because `chase_cap_atr = INF`;
   - no extra slope threshold is required, because `slope_threshold = null`.
5. If accepted, enter short at the configured execution point, normally the next UTC open. For intraday protective-stop handoff, the historical engine can close the long and open the short at the same stop event timestamp if the recheck is satisfied.
6. Consume the shadow state after acceptance, expiry, or native signal cancellation.

PEHC must persist its origin timestamp, expiry, stop reference, highest close, pending delayed recheck and consumed/cancelled state. On restart, never reconstruct PEHC state from current price alone.

## Backtest Accounting

Equity starts at `1.0`. For each trade:

```text
target_notional = equity_before_entry * target_leverage
quantity = target_notional / slipped_entry_price

long_gross_pnl = quantity * (slipped_exit_price - slipped_entry_price)
short_gross_pnl = quantity * (slipped_entry_price - slipped_exit_price)

fees = 0.001 * abs(quantity * slipped_entry_price)
     + 0.001 * abs(quantity * slipped_exit_price)

funding_pnl = sum(position_notional_at_funding_time * funding_rate * side_sign_adjustment)

net_pnl = gross_pnl - fees + funding_pnl
equity_after_exit = equity_before_entry + net_pnl
```

Funding sign convention:

- Long pays positive funding and receives negative funding.
- Short receives positive funding and pays negative funding.

Drawdown acceptance uses chronological hourly replay while positions are open. Daily equity-only drawdown is not sufficient.

## Acceptance Metrics

The following numbers are the reproduction target for the full window at `1x`, with fee `0.001`, slippage `4 bps`, and funding included.

| Metric | Value |
| --- | ---: |
| Net return | `+711.05%` |
| Equity multiple | `8.1105x` |
| Chronological 1h MDD | `-18.39%` |
| Daily extreme MDD | `-20.27%` |
| Annualized return | `+486.22%` |
| Closed trades | `20` |
| Long trades | `10` |
| Short trades | `10` |
| Win rate | `85.00%` |
| Profit factor | `17.51` |
| Sharpe | `3.25` |
| Exposure | `40.75%` |
| Turnover multiple | `119.48x` |
| Cost as initial equity | `16.73%` |
| Funding as initial equity | `-1.35%` |
| Max marked leverage | `1.17x` |
| Worst intraday timestamp | `2026-05-16T11:00:00+00:00` |

Stress checks:

| Check | Net return | 1h MDD | Trades | Win rate | PF | Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Base, 4 bps slippage, funding on | `+711.05%` | `-18.39%` | `20` | `85.00%` | `17.51` | `3.25` |
| 8 bps slippage, funding on | `+698.76%` | `-18.52%` | `20` | `85.00%` | `17.07` | `3.23` |
| 4 bps slippage, funding off | `+714.43%` | `-18.44%` | `20` | `85.00%` | `17.50` | `3.26` |
| Signal lag plus 1 day | `+267.56%` | `-26.46%` | `22` | `68.18%` | `5.11` | `2.39` |

Recent slices are audit-only, anchored to dataset end:

| Window | Daily index window | Net return | 1h MDD | Trades | Win rate | Sharpe | Exposure |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `1d` | `[431, 432]` | `0.00%` | `0.00%` | `0` | `NA` | `NA` | `0.00%` |
| `7d` | `[425, 432]` | `0.00%` | `0.00%` | `0` | `NA` | `NA` | `0.00%` |
| `1m` | `[402, 432]` | `+6.16%` | `-9.11%` | `1` | `100.00%` | `2.03` | `68.97%` |
| `3m` | `[342, 432]` | `+72.14%` | `-12.66%` | `4` | `100.00%` | `3.64` | `52.81%` |
| `6m` | `[252, 432]` | `+110.43%` | `-18.39%` | `6` | `83.33%` | `2.91` | `40.78%` |
| `1y` | `[67, 432]` | `+426.86%` | `-18.39%` | `16` | `81.25%` | `3.03` | `39.30%` |

Cold-flat blocks, 8 equal 54-day windows:

| Block | Daily index window | Net return | 1h MDD | Trades |
| ---: | --- | ---: | ---: | ---: |
| 0 | `[0, 54]` | `+34.51%` | `-10.41%` | `4` |
| 1 | `[54, 108]` | `+24.00%` | `-16.42%` | `2` |
| 2 | `[108, 162]` | `+33.80%` | `-13.61%` | `5` |
| 3 | `[162, 216]` | `+44.78%` | `-7.93%` | `3` |
| 4 | `[216, 270]` | `+20.47%` | `-13.14%` | `1` |
| 5 | `[270, 324]` | `+22.24%` | `-15.97%` | `2` |
| 6 | `[324, 378]` | `+40.78%` | `-12.66%` | `2` |
| 7 | `[378, 432]` | `+24.74%` | `-8.52%` | `2` |

Expected block summary: `8/8` positive cold-flat windows, compounded cold-flat return about `+735.55%`, worst block MDD about `-16.42%`.

## Trade Anchors

All timestamps are UTC. Prices are pre-cost reference prices from the reconstructed trade path; final accounting applies slippage, fees and funding.

| # | Side | Entry time | Entry | Exit time | Exit | Bars | Exit reason | Net return | Net PnL |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- | ---: | ---: |
| 1 | long | `2025-06-10T00:00:00+00:00` | `38.848000` | `2025-06-13T00:00:00+00:00` | `40.520000` | `3` | `long_mfe_fraction_trail_exit` | `+3.77%` | `0.037749` |
| 2 | long | `2025-06-28T00:00:00+00:00` | `36.623000` | `2025-07-06T00:00:00+00:00` | `39.137000` | `8` | `long_mfe_fraction_trail_exit` | `+6.26%` | `0.064944` |
| 3 | long | `2025-07-10T00:00:00+00:00` | `40.671000` | `2025-07-16T00:00:00+00:00` | `47.865000` | `6` | `long_mfe_fraction_trail_exit` | `+17.09%` | `0.188434` |
| 4 | short | `2025-07-18T00:00:00+00:00` | `45.589000` | `2025-08-03T00:00:00+00:00` | `36.898000` | `16` | `short_rsi_take_profit` | `+19.23%` | `0.248274` |
| 5 | long | `2025-08-27T00:00:00+00:00` | `48.796000` | `2025-09-14T00:00:00+00:00` | `54.457000` | `18` | `long_mfe_fraction_trail_exit` | `+10.44%` | `0.160676` |
| 6 | long | `2025-09-18T00:00:00+00:00` | `57.767000` | `2025-09-20T18:00:00+00:00` | `54.675357` | `2` | `protective_stop` | `-5.97%` | `-0.101563` |
| 7 | short | `2025-09-20T18:00:00+00:00` | `54.653000` | `2025-10-01T00:00:00+00:00` | `45.221000` | `11` | `ma7_slope_exit` | `+17.59%` | `0.281190` |
| 8 | short | `2025-10-15T00:00:00+00:00` | `39.393000` | `2025-10-19T00:00:00+00:00` | `36.862000` | `4` | `ma7_slope_exit` | `+6.12%` | `0.115104` |
| 9 | long | `2025-10-24T00:00:00+00:00` | `40.199000` | `2025-11-01T00:00:00+00:00` | `43.684000` | `8` | `long_mfe_fraction_trail_exit` | `+8.28%` | `0.165226` |
| 10 | short | `2025-11-03T00:00:00+00:00` | `42.443000` | `2025-11-11T00:00:00+00:00` | `41.444000` | `8` | `ma7_slope_exit` | `+2.31%` | `0.049790` |
| 11 | short | `2025-11-21T00:00:00+00:00` | `37.542000` | `2025-11-23T00:00:00+00:00` | `29.977000` | `2` | `short_rsi_take_profit` | `+19.91%` | `0.439877` |
| 12 | short | `2025-12-06T00:00:00+00:00` | `30.965000` | `2025-12-19T00:00:00+00:00` | `22.459000` | `13` | `short_rsi_take_profit` | `+27.46%` | `0.727579` |
| 13 | short | `2025-12-24T00:00:00+00:00` | `23.956000` | `2025-12-25T00:00:00+00:00` | `25.156000` | `1` | `ma7_slope_exit` | `-5.27%` | `-0.177996` |
| 14 | long | `2026-01-27T00:00:00+00:00` | `24.930000` | `2026-01-30T01:00:00+00:00` | `30.112071` | `3` | `protective_stop` | `+20.47%` | `0.654977` |
| 15 | long | `2026-03-01T00:00:00+00:00` | `31.204000` | `2026-03-21T00:00:00+00:00` | `39.528000` | `20` | `long_mfe_fraction_trail_exit` | `+26.16%` | `1.008442` |
| 16 | short | `2026-03-23T00:00:00+00:00` | `38.342000` | `2026-03-29T00:00:00+00:00` | `39.462000` | `6` | `ma7_slope_exit` | `-3.11%` | `-0.151140` |
| 17 | long | `2026-05-15T00:00:00+00:00` | `44.125000` | `2026-05-28T00:00:00+00:00` | `57.747000` | `13` | `long_mfe_fraction_trail_exit` | `+30.68%` | `1.445600` |
| 18 | short | `2026-06-05T00:00:00+00:00` | `64.439000` | `2026-06-14T00:00:00+00:00` | `60.682000` | `9` | `ma7_slope_exit` | `+5.60%` | `0.344915` |
| 19 | long | `2026-07-03T00:00:00+00:00` | `66.926000` | `2026-07-08T00:00:00+00:00` | `69.187000` | `5` | `long_mfe_fraction_trail_exit` | `+2.96%` | `0.192495` |
| 20 | short | `2026-07-12T00:00:00+00:00` | `66.743000` | `2026-08-01T00:00:00+00:00` | `52.559000` | `20` | `max_hold` | `+21.15%` | `1.415935` |

## Minimal Implementation Skeleton

```python
for t in daily_bar_indices:
    update_closed_daily_indicators(t)
    process_hourly_stops_between_previous_daily_open_and_current_daily_open()

    if position_is_open:
        update_bars_held()
        update_mfe_and_trailing_state()
        reason = first_exit_reason_at_close(t)
        if reason:
            schedule_exit_at_next_daily_open(reason)
        continue

    update_pehc_shadow_if_any(t)
    handoff = pehc_handoff_signal_if_any(t)
    if handoff:
        schedule_entry_at_next_daily_open(side=-1, source="pehc")
        continue

    if long_entry_signal(t):
        schedule_entry_at_next_daily_open(side=+1, source="native_reclaim")
    elif short_entry_signal(t):
        schedule_entry_at_next_daily_open(side=-1, source="native_reclaim")
```

Operational safety for any live or paper runner:

- Persist state before placing orders and after receiving fills.
- Reject duplicate processing for the same daily bar.
- Do not trade if the last daily candle is not confirmed closed.
- Do not trade if actual exchange position disagrees with persisted state.
- Stop new entries on missing data, rejected orders, balance mismatch or restart recovery failure.

## Reproduction Tolerance

An independent implementation is considered close enough only if all are true:

- Full-window closed trade count is exactly `20`.
- First and last trade anchors match the table above.
- At least `18/20` trade entry timestamps and exit timestamps match exactly.
- Net return is within `±1.0 percentage point` of `+711.05%`.
- 1h chronological MDD is within `±0.5 percentage point` of `-18.39%`.
- 8 bps stress remains above `+690%` net return and below `-19.5%` MDD.

If timestamps differ but headline metrics match, treat that as a bug until the entry/exit timing difference is explained. This strategy is path-sensitive.
